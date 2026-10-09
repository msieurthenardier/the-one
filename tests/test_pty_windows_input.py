"""Line-ending normalization for the Windows PTY send path (squawk 0164).

ConPTY submits a line only on ``\\r``. ``pty_windows`` imports ``winpty`` at
module scope (Windows-only), so a stub is injected to make the pure helper
and the ``write`` payload testable on Linux.
"""

from __future__ import annotations

import importlib
import sys
import types

import pytest


@pytest.fixture
def pw(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "winpty", types.ModuleType("winpty"))
    sys.modules.pop("the_one.platform.pty_windows", None)
    mod = importlib.import_module("the_one.platform.pty_windows")
    yield mod
    sys.modules.pop("the_one.platform.pty_windows", None)
    import the_one.platform

    monkeypatch.delattr(the_one.platform, "pty_windows", raising=False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("echo hi", "echo hi\r\n"),
        ("echo hi\n", "echo hi\r\n"),
        ("echo hi\r", "echo hi\r\n"),
        ("echo hi\r\n", "echo hi\r\n"),
        ("echo hi\n\n\n", "echo hi\r\n"),
        ("a\nb", "a\r\nb\r\n"),
        ("a\r\nb\r\n", "a\r\nb\r\n"),
        ("a\rb", "a\r\nb\r\n"),
        ("a\n\nb\n", "a\r\n\r\nb\r\n"),
        ("", "\r\n"),
        ("\n", "\r\n"),
    ],
)
def test_normalize_submit(pw, raw: str, expected: str) -> None:
    assert pw._normalize_submit(raw) == expected


def test_no_bare_lf_or_cr_in_output(pw) -> None:
    out = pw._normalize_submit("a\nb\rc\r\nd")
    assert out.replace("\r\n", "") == "abcd"


def test_send_blocking_writes_what_it_is_given(pw) -> None:
    """``_send_blocking`` must not re-alter input; ``send`` normalizes once."""
    written: list[str] = []

    class FakeProc:
        def write(self, data: str) -> None:
            written.append(data)

    session = pw.WindowsPtySession.__new__(pw.WindowsPtySession)
    session._proc = FakeProc()
    session._read_until_idle_blocking = lambda **kw: b""
    session._send_blocking(pw._normalize_submit("echo hi"), 1.0)
    assert written == ["echo hi\r\n"]
