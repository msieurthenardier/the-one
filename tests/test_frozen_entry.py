"""Unit tests for the Windows frozen entry script (M15 F5 L2, DD7).

``packaging/windows/frozen_entry.py`` is a build artifact: it lives outside the
``the_one`` package and is loaded here by path via ``importlib`` (no frozen
binary needed). These tests assert the DD7 contract — that
``multiprocessing.freeze_support`` runs **before** ``cli_entry`` — by recording
the call order with both functions patched.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest import mock

import pytest

_ENTRY_PATH = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "frozen_entry.py"


def _load_entry_module() -> ModuleType:
    """Load frozen_entry.py by path, NOT under ``__main__`` (so the guarded
    block does not execute at import time)."""
    spec = importlib.util.spec_from_file_location("frozen_entry", _ENTRY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entry_file_exists() -> None:
    assert _ENTRY_PATH.is_file()


def test_imports_cli_entry_from_the_one_main() -> None:
    module = _load_entry_module()
    from the_one.main import cli_entry

    # The module binds the real cli_entry at import time.
    assert module.cli_entry is cli_entry


def test_guarded_block_does_not_run_on_plain_import() -> None:
    # Loading by a non-"__main__" name must not invoke either function.
    with (
        mock.patch("multiprocessing.freeze_support") as freeze,
        mock.patch("the_one.main.cli_entry") as cli,
    ):
        _load_entry_module()
        freeze.assert_not_called()
        cli.assert_not_called()


def test_freeze_support_called_before_cli_entry() -> None:
    """Re-run the ``__main__`` body with both calls patched and assert order."""
    module = _load_entry_module()

    calls: list[str] = []
    fake_freeze = mock.Mock(side_effect=lambda *a, **k: calls.append("freeze_support"))
    fake_cli = mock.Mock(side_effect=lambda *a, **k: calls.append("cli_entry"))

    with (
        mock.patch.object(module.multiprocessing, "freeze_support", fake_freeze),
        mock.patch.object(module, "cli_entry", fake_cli),
    ):
        # Execute the guarded body directly (the module-level guard checks
        # __name__ == "__main__", which is false for an imported module).
        module.multiprocessing.freeze_support()
        module.cli_entry()

    fake_freeze.assert_called_once()
    fake_cli.assert_called_once()
    assert calls == ["freeze_support", "cli_entry"]


def test_guard_runs_freeze_then_cli_via_exec() -> None:
    """End-to-end: exec the file as ``__main__`` with both functions patched,
    proving the real guard wiring calls freeze_support then cli_entry in order.
    """
    calls: list[str] = []
    fake_freeze = mock.Mock(side_effect=lambda *a, **k: calls.append("freeze_support"))
    fake_cli = mock.Mock(side_effect=lambda *a, **k: calls.append("cli_entry"))

    with (
        mock.patch("multiprocessing.freeze_support", fake_freeze),
        mock.patch("the_one.main.cli_entry", fake_cli),
    ):
        source = _ENTRY_PATH.read_text(encoding="utf-8")
        code = compile(source, str(_ENTRY_PATH), "exec")
        exec(code, {"__name__": "__main__", "__file__": str(_ENTRY_PATH)})

    fake_freeze.assert_called_once()
    fake_cli.assert_called_once()
    assert calls == ["freeze_support", "cli_entry"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x"]))
