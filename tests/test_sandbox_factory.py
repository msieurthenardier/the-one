"""Unit tests for get_sandbox_backend() factory (F3 leg 2).

Covers:
  * Selection matrix — four branches (test-bypass, non-Linux, bwrap-missing,
    bubblewrap) via monkeypatching sys.platform, shutil.which, and env vars.
  * PassthroughSandbox never-raises guarantee off-Linux.
  * Log-once behaviour — selection log fires exactly once regardless of how many
    times the factory is called; reset between tests via a fixture.

All tests are synchronous and pure-unit (no real subprocess, no bwrap binary
required).  Monkeypatching uses the object form
``monkeypatch.setattr(factory_module.sys, "platform", ...)`` / ``shutil`` to
match the established pattern in test_sandbox_bubblewrap.py and
test_mcp_stdio_sandbox.py — this requires factory.py to ``import sys`` and
``import shutil`` at module level so the patched object is the one the factory
reads.
"""

from __future__ import annotations

import logging

import pytest

import the_one.platform.sandbox.factory as factory_module
from the_one.platform.sandbox.bubblewrap import BubblewrapSandbox
from the_one.platform.sandbox.factory import _reset_selection_log_state, get_sandbox_backend
from the_one.platform.sandbox.passthrough import PassthroughSandbox


@pytest.fixture(autouse=True)
def _reset_log_guard() -> None:
    """Reset the factory's log-once guard before each test.

    Without this, a test that asserts "log fires once" may see zero records
    because an earlier test in the same process already populated the guard.
    The autouse scope here is function-level, so every test starts clean.
    """
    _reset_selection_log_state()


@pytest.fixture()
def _linux_bwrap_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate Linux with bwrap present and no test-bypass env vars."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)


# ---------------------------------------------------------------------------
# Selection matrix
# ---------------------------------------------------------------------------


def test_factory_returns_bubblewrap_on_linux_with_bwrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux + bwrap present + no test-bypass → BubblewrapSandbox."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    backend = get_sandbox_backend()
    assert isinstance(backend, BubblewrapSandbox)


def test_factory_returns_passthrough_on_non_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-Linux host → PassthroughSandbox regardless of bwrap PATH."""
    monkeypatch.setattr(factory_module.sys, "platform", "darwin")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    backend = get_sandbox_backend()
    assert isinstance(backend, PassthroughSandbox)


def test_factory_returns_passthrough_on_linux_bwrap_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux + bwrap missing → PassthroughSandbox."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: None)
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    backend = get_sandbox_backend()
    assert isinstance(backend, PassthroughSandbox)


def test_factory_returns_passthrough_on_test_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Double-flag test bypass → PassthroughSandbox (highest priority)."""
    # Even on Linux with bwrap present, the bypass wins
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")

    backend = get_sandbox_backend()
    assert isinstance(backend, PassthroughSandbox)


def test_factory_no_bypass_when_only_one_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only ONE test flag set — not a bypass; Linux+bwrap-present → BubblewrapSandbox."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    backend = get_sandbox_backend()
    assert isinstance(backend, BubblewrapSandbox)


# ---------------------------------------------------------------------------
# PassthroughSandbox never-raises guarantee
# ---------------------------------------------------------------------------


def test_passthrough_never_raises_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """PassthroughSandbox constructs and prepare_spawn runs without raising off-Linux."""
    monkeypatch.setattr(factory_module.sys, "platform", "darwin")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: None)
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    backend = get_sandbox_backend()
    assert isinstance(backend, PassthroughSandbox)

    from the_one.platform.sandbox.base import SandboxProfile

    # Must not raise regardless of profile fields
    spec = backend.prepare_spawn(
        SandboxProfile(
            writable_paths=["/some/path"],
            network_allowed=True,
            readonly_overlay_paths=["/some/path/.secret"],
        ),
        "/usr/bin/env",
        ["python3", "-c", "pass"],
        {"PATH": "/usr/bin", "HOME": "/home/u"},
        cwd="/tmp",
    )
    assert spec.command == "/usr/bin/env"
    assert spec.args == ["python3", "-c", "pass"]
    assert spec.env == {"PATH": "/usr/bin", "HOME": "/home/u"}
    assert spec.cwd == "/tmp"


# ---------------------------------------------------------------------------
# Log-once behaviour
# ---------------------------------------------------------------------------


def test_factory_logs_once_bubblewrap(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Bubblewrap selection is logged once (INFO); second call suppressed."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    with caplog.at_level(logging.INFO, logger="the_one.platform.sandbox.factory"):
        get_sandbox_backend()
        get_sandbox_backend()

    records = [r for r in caplog.records if "bubblewrap" in r.message.lower()]
    assert len(records) == 1, (
        f"Expected exactly 1 bubblewrap log record; got {len(records)}: {records}"
    )
    assert records[0].levelno == logging.INFO


def test_factory_logs_once_passthrough_non_linux(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-Linux passthrough selection is logged once (INFO); second call suppressed."""
    monkeypatch.setattr(factory_module.sys, "platform", "darwin")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: None)
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    with caplog.at_level(logging.INFO, logger="the_one.platform.sandbox.factory"):
        get_sandbox_backend()
        get_sandbox_backend()

    records = [r for r in caplog.records if "non-linux" in r.message.lower()]
    assert len(records) == 1, (
        f"Expected exactly 1 non-linux log record; got {len(records)}: {records}"
    )
    assert records[0].levelno == logging.INFO


def test_factory_logs_warning_when_bwrap_missing_on_linux(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Linux + bwrap missing → WARNING logged (enforcement expected but absent)."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: None)
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    with caplog.at_level(logging.WARNING, logger="the_one.platform.sandbox.factory"):
        get_sandbox_backend()
        get_sandbox_backend()

    records = [r for r in caplog.records if "bwrap missing" in r.message.lower()]
    assert len(records) == 1, (
        f"Expected exactly 1 bwrap-missing WARNING; got {len(records)}: {records}"
    )
    assert records[0].levelno == logging.WARNING


def test_factory_logs_once_test_bypass(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test-bypass passthrough selection is logged once (INFO)."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")

    with caplog.at_level(logging.INFO, logger="the_one.platform.sandbox.factory"):
        get_sandbox_backend()
        get_sandbox_backend()

    records = [r for r in caplog.records if "test-bypass" in r.message.lower()]
    assert len(records) == 1, (
        f"Expected exactly 1 test-bypass log record; got {len(records)}: {records}"
    )
    assert records[0].levelno == logging.INFO


# ---------------------------------------------------------------------------
# backend.name attribute
# ---------------------------------------------------------------------------


def test_factory_backend_name_bubblewrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selected BubblewrapSandbox has name == 'bubblewrap'."""
    monkeypatch.setattr(factory_module.sys, "platform", "linux")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    backend = get_sandbox_backend()
    assert backend.name == "bubblewrap"  # type: ignore[union-attr]


def test_factory_backend_name_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selected PassthroughSandbox has name == 'passthrough'."""
    monkeypatch.setattr(factory_module.sys, "platform", "darwin")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _: None)
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    backend = get_sandbox_backend()
    assert backend.name == "passthrough"  # type: ignore[union-attr]
