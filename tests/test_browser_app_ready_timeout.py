"""Squawk 0438: the browser fixtures' spawn-ready timeout default and override."""

from __future__ import annotations

import pytest
from browser import _app_ready

ENV = _app_ready.APP_READY_TIMEOUT_ENV


def test_default_is_45_seconds() -> None:
    assert _app_ready.app_ready_timeout({}) == 45.0


def test_env_override_parses_as_seconds() -> None:
    assert _app_ready.app_ready_timeout({ENV: "90"}) == 90.0
    assert _app_ready.app_ready_timeout({ENV: " 12.5 "}) == 12.5


def test_empty_value_means_unset() -> None:
    assert _app_ready.app_ready_timeout({ENV: ""}) == 45.0


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "nan", "inf"])
def test_bad_value_fails_loudly(bad: str) -> None:
    with pytest.raises(ValueError, match=ENV):
        _app_ready.app_ready_timeout({ENV: bad})


def test_env_none_reads_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV, "77")
    assert _app_ready.app_ready_timeout() == 77.0
    monkeypatch.delenv(ENV, raising=False)
    assert _app_ready.app_ready_timeout() == 45.0


def _conftest_src() -> str:
    from pathlib import Path

    return (Path(__file__).parent / "browser" / "conftest.py").read_text()


def test_conftest_uses_the_helper_at_both_sites() -> None:
    """The default and the spawn call both come from the helper, so they cannot drift."""
    import re

    src = _conftest_src()
    assert "timeout: float | None = None" in src
    assert "timeout=15.0" not in src
    spawn = src[src.index("def _spawn_app(") :]
    assert re.search(r"^\s*ready_timeout = app_ready_timeout\(\)$", spawn, re.M)
    assert "_wait_for_ready(base_url, proc=proc, timeout=ready_timeout)" in spawn


def test_spawn_resolves_the_timeout_before_popen() -> None:
    """A bad env value must fail before the uvicorn child exists (no orphan)."""
    src = _conftest_src()
    spawn = src[src.index("def _spawn_app(") :]
    assert "ready_timeout = app_ready_timeout()" in spawn
    assert spawn.index("ready_timeout = app_ready_timeout()") < spawn.index("subprocess.Popen(")
