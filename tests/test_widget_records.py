"""``clear_widget_records`` and its two call sites (Mission 35, Flight 2, leg 8, AC4).

A clean quit must not leave a widget hang-guard record for the next launch to read as
"stopped responding last time". The clear is bounded (a page frozen by a widget never
answers ``run_js``), never raises, and is skipped on the main thread.
"""

from __future__ import annotations

import logging
import threading
import time
from unittest.mock import MagicMock

from the_one.interfaces.desktop import macos_dock, widget_records
from the_one.interfaces.desktop.macos_dock import TerminateWorker
from the_one.interfaces.desktop.session_state import state


def _in_thread(fn):
    out: list = []
    t = threading.Thread(target=lambda: out.append(fn()))
    t.start()
    t.join(10)
    assert not t.is_alive()
    return out[0]


def test_the_script_clears_the_prefix_blocks_rewrites_and_uses_no_bridge():
    s = widget_records.CLEAR_SCRIPT
    assert "widget-running:" in s and "removeItem" in s
    assert "Storage.prototype.setItem" in s  # the tick rewrites its record every second
    for forbidden in ("webkit", "pywebview", "postMessage", "chrome.webview"):
        assert forbidden not in s


def test_a_worker_thread_runs_the_script_once_and_reports_cleared():
    win = MagicMock()
    assert _in_thread(lambda: widget_records.clear_widget_records(win)) == "cleared"
    win.run_js.assert_called_once_with(widget_records.CLEAR_SCRIPT)
    assert win.evaluate_js.call_count == 0  # never a callback form


def test_a_page_that_never_answers_times_out_and_the_quit_continues(caplog):
    release = threading.Event()
    win = MagicMock()
    win.run_js.side_effect = lambda script: release.wait(30)  # frozen by a widget
    try:
        t0 = time.monotonic()
        with caplog.at_level(logging.WARNING):
            result = _in_thread(lambda: widget_records.clear_widget_records(win, bound=0.1))
        assert result == "timeout"
        assert time.monotonic() - t0 < 2  # bounded: the quit is not held
        assert any("did not answer" in r.getMessage() for r in caplog.records)
    finally:
        release.set()  # the leaked daemon thread ends here (harmless at exit)


def test_a_raising_run_js_is_an_error_not_an_exception(caplog):
    win = MagicMock()
    win.run_js.side_effect = RuntimeError("window gone")
    with caplog.at_level(logging.WARNING):
        assert _in_thread(lambda: widget_records.clear_widget_records(win)) == "error"


def test_the_main_thread_is_skipped_because_run_js_would_deadlock_the_loop():
    win = MagicMock()
    assert widget_records.clear_widget_records(win) == "skipped"
    win.run_js.assert_not_called()


def test_no_window_is_a_no_op():
    assert widget_records.clear_widget_records(None) == "no-window"


def test_on_quit_clears_before_the_destroy(monkeypatch):
    import the_one.interfaces.desktop.shell as shell_mod

    order: list[str] = []
    monkeypatch.setattr(shell_mod.chrome, "deregister", lambda: None)
    monkeypatch.setattr(
        widget_records, "clear_widget_records", lambda w, bound=None: order.append("clear")
    )
    win = MagicMock()
    win.destroy.side_effect = lambda: order.append("destroy")
    state.desktop_window = win
    session = shell_mod.DesktopSession()
    session._save_current_geometry = lambda w: None
    session._on_quit(None)
    assert order == ["clear", "destroy"]


def test_terminate_worker_clears_between_the_boot_wait_and_the_drain():
    order: list[str] = []
    TerminateWorker(
        reply=lambda: order.append("reply"),
        drain=lambda: order.append("drain"),
        boot_wait=lambda t: order.append("boot") or True,
        log_flush=lambda: None,
        clear_records=lambda: order.append("clear"),
    ).run()
    assert order == ["boot", "clear", "drain", "reply"]


def test_terminate_worker_replies_even_when_the_clear_raises():
    order: list[str] = []

    def boom():
        raise RuntimeError("x")

    TerminateWorker(
        reply=lambda: order.append("reply"),
        drain=lambda: order.append("drain"),
        boot_wait=lambda t: True,
        log_flush=lambda: None,
        clear_records=boom,
    ).run()
    assert order == ["drain", "reply"]


def test_start_terminate_passes_the_clear_to_the_worker(monkeypatch):
    seen: dict = {}

    class _W:
        def __init__(self, **kw):
            seen.update(kw)

        def start(self):
            pass

    monkeypatch.setattr(macos_dock, "TerminateWorker", _W)
    monkeypatch.setattr("the_one.interfaces.desktop.chrome.deregister", lambda: None)
    state.desktop_window = MagicMock()
    cleared: list = []
    monkeypatch.setattr(
        widget_records, "clear_widget_records", lambda w, bound=None: cleared.append(w)
    )
    session = MagicMock()
    macos_dock._start_terminate(session)
    assert callable(seen["clear_records"])
    seen["clear_records"]()
    assert cleared == [state.desktop_window]
