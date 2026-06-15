"""Direct tests for ``the_one.platform.interpreter``.

The async tests below use ``async def`` rather than ``asyncio.run`` so the
project's ``asyncio_mode = "auto"`` pytest-asyncio config runs each in a
fresh event loop. ``asyncio.run`` closes the main thread's event loop on
exit, which breaks downstream tests that rely on
``asyncio.get_event_loop().run_until_complete(...)``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from the_one.platform import env as env_mod
from the_one.platform import interpreter as interp_mod
from the_one.platform.interpreter import (
    _PYTHON_OVERRIDE_ENV,
    FrozenInterpreterError,
    resolve_python,
    run_python,
)


def _freeze(monkeypatch: pytest.MonkeyPatch, bundle: str = "/bundle") -> None:
    monkeypatch.setattr(env_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(env_mod.sys, "_MEIPASS", bundle, raising=False)


class TestResolvePython:
    def test_returns_non_empty_string(self) -> None:
        result = resolve_python()
        assert isinstance(result, str)
        assert result != ""


class TestResolvePythonFrozen:
    """M15 F5 L1 (DD3): when frozen, resolve a real external interpreter, never
    ``sys.executable`` (which is the frozen app)."""

    def test_resolves_from_path_when_frozen(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        _freeze(monkeypatch)
        monkeypatch.delenv(_PYTHON_OVERRIDE_ENV, raising=False)
        fake = tmp_path / "python3"
        fake.write_text("#!/bin/sh\n")
        fake.chmod(0o755)
        # ``which`` resolves ``python3`` against whatever PATH the cleaned env
        # carries; stub it to return our fake.
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            lambda cmd, path=None: str(fake) if cmd == "python3" else None,
        )
        result = resolve_python()
        assert result == str(fake.resolve())

    def test_honors_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        _freeze(monkeypatch)
        custom = tmp_path / "mypython"
        custom.write_text("#!/bin/sh\n")
        custom.chmod(0o755)
        monkeypatch.setenv(_PYTHON_OVERRIDE_ENV, str(custom))
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            lambda cmd, path=None: str(custom) if cmd == str(custom) else None,
        )
        assert resolve_python() == str(custom.resolve())

    def test_raises_actionable_non_docker_error_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _freeze(monkeypatch)
        monkeypatch.delenv(_PYTHON_OVERRIDE_ENV, raising=False)
        monkeypatch.setattr(interp_mod.shutil, "which", lambda cmd, path=None: None)
        with pytest.raises(FrozenInterpreterError) as exc:
            resolve_python()
        msg = str(exc.value).lower()
        assert "install python" in msg or "set the_one_python" in msg
        assert "docker" not in msg

    def test_non_frozen_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        # Falls back to sys.executable — a real, non-empty path.
        assert resolve_python() != ""


class TestRunPython:
    async def test_happy_path(self) -> None:
        stdout, stderr, returncode = await run_python("print(2+2)", timeout=5)
        assert stdout.strip() == b"4"
        assert stderr == b""
        assert returncode == 0

    async def test_nonzero_exit_propagates(self) -> None:
        _, _, returncode = await run_python("import sys; sys.exit(3)", timeout=5)
        assert returncode == 3

    async def test_timeout_raises_and_is_prompt(self) -> None:
        start = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            await run_python("import time; time.sleep(5)", timeout=0.1)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"run_python timeout took {elapsed:.3f}s; kill+reap likely broken"
