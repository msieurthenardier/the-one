"""Version takeover (DD13), M32 F2 L05 phase B: driven through the named seams.

The takeover code lives in ``desktop.takeover`` (M32 F3 DD1), so every seam is patched there."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import the_one.interfaces.desktop.shell as shell
import the_one.interfaces.desktop.takeover as takeover

# dpkg's order (``dpkg --compare-versions``, run once on the dev host, with ``~`` for
# our ``.dev``): 0.11.8 < 0.11.9~dev1 < 0.11.9; dev3 < dev4; dev9 < dev10.
OLDER_PAIRS = [
    ("0.11.8", "0.11.9.dev1"),
    ("0.11.9.dev1", "0.11.9"),
    ("0.11.8", "0.11.9"),
    ("0.11.9.dev3", "0.11.9.dev4"),
    ("0.11.9.dev9", "0.11.9.dev10"),
    ("0.9.0", "0.11.0"),
    ("0.11.9", "1.0.0"),
]


@pytest.mark.parametrize(("a", "b"), OLDER_PAIRS)
def test_comparator_matches_dpkg(a: str, b: str) -> None:
    assert takeover._is_older(a, b) is True
    assert takeover._is_older(b, a) is False


@pytest.mark.parametrize("junk", [None, "", "abc", "1.2", "1.2.3rc1", "1.2.3+local", "1.2.3.dev"])
def test_comparator_unknown_is_not_older(junk) -> None:
    assert takeover._is_older(junk, "1.0.0") is False
    assert takeover._is_older("0.1.0", junk if junk else "x") is False


def test_comparator_equal_is_not_older() -> None:
    assert takeover._is_older("0.11.9.dev3", "0.11.9.dev3") is False


class Seams:
    """Stub every takeover seam; records focus posts and notices, fakes the clock."""

    def __init__(self, monkeypatch, *, running, answer, alive_polls=2, reselect=(8484, False)):
        self.t = 0.0
        self.focus = 0
        self.notices: list = []
        self.alive_polls = alive_polls  # None -> never exits
        self.polls = 0
        self.quit_calls = 0
        mp = monkeypatch
        mp.setattr(takeover, "__version__", "0.11.9.dev8")
        mp.setattr(takeover, "_running_version", lambda h, p: running)

        def rq(h, p):
            self.quit_calls += 1
            return answer

        mp.setattr(takeover, "_request_quit", rq)
        mp.setattr(takeover, "_pid_alive", self._alive)
        mp.setattr(takeover, "_now", lambda: self.t)
        mp.setattr(takeover, "_sleep", self._sleep)
        mp.setattr(takeover, "_post_focus", self._focus)
        mp.setattr(takeover, "_select_port", lambda h, p, *a, **k: reselect)
        mp.setattr(takeover.desktop_host, "send_notification", lambda *a: self.notices.append(a))

    def _alive(self, pid):
        self.polls += 1
        return self.alive_polls is None or self.polls <= self.alive_polls

    def _sleep(self, s):
        self.t += s

    def _focus(self, h, p):
        self.focus += 1


OK = {"status": 200, "body": {"quit": True, "pid": 4242, "state": "window"}}


def test_older_accepted_waits_then_starts(monkeypatch) -> None:
    s = Seams(monkeypatch, running="0.11.9.dev7", answer=OK)
    assert takeover._takeover("127.0.0.1", 8490) == (8484, False)
    assert s.quit_calls == 1 and s.focus == 0 and s.notices == []


def test_older_slow_exit_shows_updating_notice_once(monkeypatch) -> None:
    s = Seams(monkeypatch, running="0.11.9.dev7", answer=OK, alive_polls=20)
    assert takeover._takeover("127.0.0.1", 8490)[1] is False
    assert len(s.notices) == 1 and "Updating" in s.notices[0][1]


def test_older_server_only_no_wait_no_focus(monkeypatch) -> None:
    ans = {"status": 200, "body": {"quit": False, "pid": 1, "state": None}}
    s = Seams(monkeypatch, running="0.11.9.dev7", answer=ans)
    assert takeover._takeover("127.0.0.1", 8490) == (8490, True)
    assert s.focus == 0 and s.polls == 0


def test_older_404_focuses_immediately(monkeypatch) -> None:
    s = Seams(monkeypatch, running="0.11.8", answer={"status": 404, "body": None})
    assert takeover._takeover("127.0.0.1", 8490) == (8490, True)
    assert s.focus == 1 and s.polls == 0


def test_older_401_logs_distinctly_no_focus(monkeypatch, caplog) -> None:
    s = Seams(monkeypatch, running="0.11.8", answer={"status": 401, "body": None})
    with caplog.at_level("WARNING"):
        assert takeover._takeover("127.0.0.1", 8490) == (8490, True)
    assert s.focus == 0 and "different credential" in caplog.text


def test_older_never_exits_focuses_at_bound(monkeypatch) -> None:
    s = Seams(monkeypatch, running="0.11.9.dev7", answer=OK, alive_polls=None)
    assert takeover._takeover("127.0.0.1", 8490) == (8490, True)
    assert s.focus == 1 and s.t >= takeover._TAKEOVER_WAIT_BOUND


def test_older_connection_error_focuses(monkeypatch) -> None:
    s = Seams(monkeypatch, running="0.11.9.dev7", answer=None)
    assert takeover._takeover("127.0.0.1", 8490) == (8490, True)
    assert s.focus == 1


@pytest.mark.parametrize("running", ["0.11.9.dev8", "0.12.0", None, "garbage"])
def test_same_newer_unknown_focuses(monkeypatch, running) -> None:
    s = Seams(monkeypatch, running=running, answer=OK)
    assert takeover._takeover("127.0.0.1", 8490) == (8490, True)
    assert s.focus == 1 and s.quit_calls == 0


def test_pid_alive_never_os_kill_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    import types

    class Fn:
        argtypes = None
        restype = None

        def __call__(self, *a):
            return 0

    k = types.SimpleNamespace(OpenProcess=Fn(), WaitForSingleObject=Fn(), CloseHandle=Fn())
    wt = types.SimpleNamespace(DWORD=1, BOOL=2, HANDLE=3)
    fake = types.SimpleNamespace(windll=types.SimpleNamespace(kernel32=k), wintypes=wt)
    monkeypatch.setitem(sys.modules, "ctypes.wintypes", wt)
    monkeypatch.setitem(sys.modules, "ctypes", fake)
    with patch("os.kill", side_effect=AssertionError("os.kill on win32")):
        assert takeover._pid_alive(123) is False
    assert k.OpenProcess.argtypes == [1, 2, 1] and k.OpenProcess.restype == 3
    assert k.CloseHandle.argtypes == [3] and k.WaitForSingleObject.restype == 1


def test_pid_alive_posix(monkeypatch) -> None:
    import os

    assert takeover._pid_alive(os.getpid()) is True
    with patch("os.kill", side_effect=ProcessLookupError):
        assert takeover._pid_alive(999999) is False


def test_activation_token_env(monkeypatch) -> None:
    monkeypatch.delenv("XDG_ACTIVATION_TOKEN", raising=False)
    monkeypatch.delenv("DESKTOP_STARTUP_ID", raising=False)
    assert takeover._activation_token() is None
    monkeypatch.setenv("DESKTOP_STARTUP_ID", "abc_TIME123")
    assert takeover._activation_token() == "abc_TIME123"
    monkeypatch.setenv("XDG_ACTIVATION_TOKEN", "has space")
    assert takeover._activation_token() is None


def test_run_desktop_restarts_after_takeover(monkeypatch) -> None:
    """is_ours -> takeover says start: run() proceeds past the focus-and-exit return."""

    class StopRunError(Exception):
        pass

    def boom(*a, **k):
        raise StopRunError

    monkeypatch.setattr(takeover, "_select_port", lambda h, p, *a, **k: (p, True))
    monkeypatch.setattr(takeover, "_takeover", lambda h, p: (p, False))
    monkeypatch.setattr(shell.uvicorn, "Server", lambda *a, **k: MagicMock())
    monkeypatch.setattr(shell.threading, "Thread", boom)
    with pytest.raises(StopRunError):
        shell.run_desktop()


@pytest.mark.parametrize("bad", [True, False, 0, -5, "42", 4.0, None])
def test_takeover_rejects_invalid_pid(monkeypatch, bad) -> None:
    ans = {"status": 200, "body": {"quit": True, "pid": bad, "state": "window"}}
    s = Seams(monkeypatch, running="0.11.9.dev7", answer=ans)
    assert takeover._takeover("127.0.0.1", 8490) == (8490, True)
    assert s.focus == 1 and s.polls == 0
