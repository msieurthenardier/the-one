"""macOS dock mode, Phase A (M32 F3 leg 4): the decision core, the terminate worker,
the AppKit seams (faked), and the darwin ``window_control`` mappings.

No AppKit/objc import anywhere: every seam is replaced.
"""

# ruff: noqa: N802
from __future__ import annotations

import itertools
import logging
import sys
import threading
from unittest.mock import MagicMock

import pytest

from the_one.interfaces.desktop import macos_dock, window_control
from the_one.interfaces.desktop.macos_dock import DockView, TerminateWorker
from the_one.interfaces.desktop.session_state import SessionState, state

# -- decision tables ---------------------------------------------------------------


def _views():
    for rq, bo, hw, tp, hs, nw in itertools.product([False, True], repeat=6):
        yield DockView(rq, bo, hw, tp, hs, nw)


def test_on_close_table():
    for v in _views():
        if v.really_quit:
            want = "allow"
        elif v.has_window:
            want = "hide"
        else:
            want = "hide" if v.native_window else "allow"
        assert macos_dock.on_close(v) == want, v


def test_on_close_named_cases():
    assert macos_dock.on_close(DockView(really_quit=True, has_window=True)) == "allow"
    assert macos_dock.on_close(DockView(has_window=True)) == "hide"
    assert macos_dock.on_close(DockView(booting=True, native_window=True)) == "hide"
    assert macos_dock.on_close(DockView(booting=True)) == "allow"


def test_on_reopen_table():
    for v in _views():
        if v.really_quit or v.terminate_pending:
            want = "ignore"
        elif v.booting and not v.has_window:
            want = "defer"
        else:
            want = "show"
        assert macos_dock.on_reopen(v) == want, v
    assert macos_dock.on_reopen(DockView(booting=True, has_window=True)) == "show"


def test_on_terminate_table_and_reply_codes():
    for v in _views():
        if v.terminate_pending:
            want = "already-pending"
        elif not v.has_server:
            want = "reply-now"
        else:
            want = "drain-then-reply"
        assert macos_dock.on_terminate(v) == want, v
    assert macos_dock.terminate_reply_code("reply-now") == 1
    assert macos_dock.terminate_reply_code("drain-then-reply") == 2
    assert macos_dock.terminate_reply_code("already-pending") == 2


def test_snapshot_reads_state():
    st = SessionState()
    st.really_quit = True
    st.desktop_window = object()
    st.server = object()
    st.mark_terminate_pending()
    v = macos_dock.snapshot(st, native_window=True)
    assert v == DockView(True, False, True, True, True, True)


# -- TerminateWorker -------------------------------------------------------------------


class _Rig:
    def __init__(self, boot_ok=True, drain_exc=None, reply_fails=0):
        self.events: list[str] = []
        self.boot_ok = boot_ok
        self.drain_exc = drain_exc
        self.reply_fails = reply_fails
        self.t = 100.0

    def clock(self):
        return self.t

    def worker(self):
        def boot_wait(timeout):
            self.events.append(f"boot_wait({timeout})")
            return self.boot_ok

        def drain():
            self.events.append("drain")
            if self.drain_exc:
                raise self.drain_exc

        def flush():
            self.events.append("flush")

        def reply():
            self.events.append("reply")
            if self.reply_fails:
                self.reply_fails -= 1
                raise RuntimeError("no main thread")

        return TerminateWorker(
            reply, drain, boot_wait, flush, clock=self.clock,
            sleep=lambda s: self.events.append(f"sleep({s})"),
        )  # fmt: skip


def test_worker_order_boot_wait_drain_flush_reply(caplog):
    rig = _Rig()
    with caplog.at_level(logging.INFO, logger="the_one.interfaces.desktop.shell"):
        rig.worker().run()
    assert rig.events == ["boot_wait(5.0)", "drain", "flush", "reply"]
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs.index("terminate: reply sending") > msgs.index("terminate: drain started")
    assert any(m.startswith("terminate: drain done") for m in msgs)


def test_worker_boot_bound_is_five_and_total_inside_takeover_bound():
    from the_one.interfaces.desktop import takeover

    assert macos_dock.BOOT_WAIT_BOUND == 5.0
    assert macos_dock.BOOT_WAIT_BOUND + 60.0 < takeover._TAKEOVER_WAIT_BOUND


def test_worker_replies_after_boot_timeout(caplog):
    rig = _Rig(boot_ok=False)
    with caplog.at_level(logging.WARNING, logger="the_one.interfaces.desktop.shell"):
        rig.worker().run()
    assert rig.events[-3:] == ["drain", "flush", "reply"]
    assert any("did not stop within" in r.getMessage() for r in caplog.records)


def test_worker_replies_when_drain_raises():
    rig = _Rig(drain_exc=RuntimeError("boom"))
    rig.worker().run()
    assert rig.events == ["boot_wait(5.0)", "drain", "flush", "reply"]


def test_worker_retries_reply_once():
    rig = _Rig(reply_fails=1)
    rig.worker().run()
    assert rig.events[-3:] == ["reply", "sleep(0.5)", "reply"]


def test_worker_does_not_hold_state_lock_while_draining():
    held: list[bool] = []

    def drain():
        got = state.lock.acquire(blocking=False)
        held.append(not got)
        if got:
            state.lock.release()

    TerminateWorker(lambda: None, drain, lambda t: True, lambda: None).run()
    assert held == [False]


def test_worker_start_runs_on_a_daemon_thread():
    done = threading.Event()
    w = TerminateWorker(done.set, lambda: None, lambda t: True, lambda: None)
    th = w.start()
    assert done.wait(5) and th.daemon
    th.join(5)


def test_flush_log_handlers_flushes_without_closing():
    h = MagicMock(spec=logging.Handler)
    lg = logging.getLogger()
    lg.addHandler(h)
    try:
        macos_dock.flush_log_handlers()
    finally:
        lg.removeHandler(h)
    h.flush.assert_called()
    h.close.assert_not_called()


# -- session_state additions -------------------------------------------------------------


def test_begin_quit_sets_flags_and_returns_window_once():
    st = SessionState()
    win = object()
    st.desktop_window = win
    assert st.begin_quit() is win
    assert st.really_quit and st.quit_requested
    assert st.begin_quit() is None  # geometry saved once


def test_begin_quit_without_window_returns_none():
    st = SessionState()
    assert st.begin_quit() is None
    assert st.really_quit and st.quit_requested


def test_mark_terminate_pending_once():
    st = SessionState()
    assert st.mark_terminate_pending() is True
    assert st.terminate_pending
    assert st.mark_terminate_pending() is False


def test_reset_clears_terminate_pending_and_loop_stopped():
    st = SessionState()
    st.mark_terminate_pending()
    st.loop_stopped = True
    st.reset()
    assert st.terminate_pending is False and st.loop_stopped is False


# -- darwin window_control mappings ------------------------------------------------------------


@pytest.fixture
def darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    calls: list = []
    monkeypatch.setattr(macos_dock, "terminate_app", lambda: calls.append("terminate_app"))
    monkeypatch.setattr(macos_dock, "activate", lambda w: calls.append(("activate", w)))
    monkeypatch.setattr(macos_dock, "native_visible", lambda w: calls.append(("vis", w)) or True)
    return calls


def test_darwin_quit_window_tag_terminates_not_on_quit(darwin):
    session = MagicMock()
    state.session, state.desktop_window = session, object()
    assert window_control.quit_desktop() == "window"
    assert darwin == ["terminate_app"]
    session._on_quit.assert_not_called()


def test_darwin_quit_booting_tag_terminates(darwin):
    state.session, state.booting = MagicMock(), True
    assert window_control.quit_desktop() == "booting"
    assert darwin == ["terminate_app"]
    assert state.quit_requested is True


def test_darwin_quit_browser_tag_unchanged(darwin):
    server = MagicMock(should_exit=False)
    state.browser_server = server
    assert window_control.quit_desktop() == "browser"
    assert server.should_exit is True and darwin == []


def test_darwin_quit_serve_mode_none(darwin):
    assert window_control.quit_desktop() is None and darwin == []


def test_darwin_quit_already_is_window_without_second_terminate(darwin):
    state.session, state.desktop_window, state.really_quit = MagicMock(), object(), True
    assert window_control.quit_desktop() == "window"
    assert darwin == []


def test_darwin_quit_after_loop_stopped_does_nothing(darwin):
    state.session, state.desktop_window, state.loop_stopped = MagicMock(), object(), True
    assert window_control.quit_desktop() == "window"
    assert darwin == [] and state.really_quit is False


def test_darwin_quit_terminate_failure_returns_none(darwin, monkeypatch):
    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(macos_dock, "terminate_app", boom)
    state.session, state.desktop_window = MagicMock(), object()
    assert window_control.quit_desktop() is None


def test_darwin_focus_window_activates(darwin):
    win = object()
    state.desktop_window = win
    assert window_control.focus_window("tok") is True
    assert darwin == [("activate", win)]


def test_darwin_focus_window_false_when_activate_raises(darwin, monkeypatch):
    def boom(w):
        raise RuntimeError("x")

    monkeypatch.setattr(macos_dock, "activate", boom)
    state.desktop_window = object()
    assert window_control.focus_window() is False


def test_darwin_window_visible_reads_native(darwin):
    win = object()
    state.desktop_window = win
    assert window_control.window_visible() is True
    assert darwin == [("vis", win)]


def test_darwin_window_visible_none_without_window(darwin):
    assert window_control.window_visible() is None and darwin == []


def test_chrome_register_deregister_unchanged_on_darwin(darwin):
    from the_one.interfaces.desktop import chrome

    win = MagicMock()
    assert chrome.register(win, "dark") is False  # off Windows: stores only
    win.native.assert_not_called()
    chrome.deregister()  # neither touches AppKit nor raises off Windows


# -- seams -----------------------------------------------------------------------------


class _NSWin:
    def __init__(self, mini=False, visible=True):
        self.mini, self.visible, self.log = mini, visible, []

    def isMiniaturized(self):
        return self.mini

    def deminiaturize_(self, s):
        self.log.append("deminiaturize")

    def makeKeyAndOrderFront_(self, s):
        self.log.append("front")

    def isVisible(self):
        if isinstance(self.visible, Exception):
            raise self.visible
        return self.visible


def test_activate_runs_on_main_thread_via_call_after(monkeypatch):
    nswin = _NSWin(mini=True)
    app = MagicMock()
    queued: list = []
    monkeypatch.setattr(macos_dock, "_call_after", lambda fn, *a: queued.append((fn, a)))
    monkeypatch.setattr(macos_dock, "_nsapp", lambda: app)
    macos_dock.activate(MagicMock(native=nswin))
    assert nswin.log == []  # nothing ran on the caller's thread
    fn, a = queued[0]
    fn(*a)
    assert nswin.log == ["deminiaturize", "front"]
    app.activateIgnoringOtherApps_.assert_called_once_with(True)


def test_native_visible_direct_read():
    assert macos_dock.native_visible(MagicMock(native=_NSWin(visible=False))) is False


def test_native_visible_falls_back_to_call_after(monkeypatch):
    nswin = _NSWin()
    calls = iter([RuntimeError("off main"), True])

    def isv():
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    nswin.isVisible = isv
    monkeypatch.setattr(macos_dock, "_call_after", lambda fn, *a: fn(*a))
    assert macos_dock.native_visible(MagicMock(native=nswin)) is True


def test_native_visible_none_on_failure_and_timeout(monkeypatch):
    nswin = _NSWin(visible=RuntimeError("x"))
    monkeypatch.setattr(macos_dock, "_call_after", lambda fn, *a: fn(*a))
    assert macos_dock.native_visible(MagicMock(native=nswin)) is None
    monkeypatch.setattr(macos_dock, "_call_after", lambda fn, *a: None)  # never runs
    monkeypatch.setattr(macos_dock, "_VISIBLE_READ_TIMEOUT", 0.05)
    assert macos_dock.native_visible(MagicMock(native=nswin)) is None


def test_terminate_app_and_reply_go_through_call_after(monkeypatch):
    app = MagicMock()
    monkeypatch.setattr(macos_dock, "_call_after", lambda fn, *a: fn(*a))
    monkeypatch.setattr(macos_dock, "_nsapp", lambda: app)
    macos_dock.terminate_app()
    app.terminate_.assert_called_once_with(None)
    macos_dock.reply_to_terminate(True)
    app.replyToApplicationShouldTerminate_.assert_called_once_with(True)


def test_importing_macos_dock_does_not_import_appkit():
    import subprocess

    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, the_one.interfaces.desktop.macos_dock;"
         "print(any(m in sys.modules for m in ('objc','AppKit','PyObjCTools')))"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert out == "False"
