"""``remove_native_handlers`` (Mission 35, Flight 2, leg 8, DD13).

Each backend's call, the thread hop, idempotence, the failure paths and the
``native_bridge`` field of ``GET /api/window/state``. Fakes stand in for the GTK and
Cocoa modules (neither is importable on every host), patched in ``sys.modules`` so
the function's lazy imports find them.
"""

from __future__ import annotations

import logging
import sys
import threading
import types
from unittest.mock import MagicMock

import pytest

from the_one.interfaces.desktop import macos_dock, native_bridge, window_control
from the_one.interfaces.desktop.session_state import state


def _run_on_other_thread(job):
    """A UI-thread stand-in that is not the calling thread."""
    box = []

    def _go():
        box.append(threading.current_thread())
        job()

    t = threading.Thread(target=_go)
    t.start()
    t.join(5)
    return box[0]


def _fake_gtk(monkeypatch, manager):
    gtkmod = types.ModuleType("webview.platforms.gtk")
    view = types.SimpleNamespace(manager=manager)
    gtkmod.BrowserView = types.SimpleNamespace(instances={"uid-1": view})
    gtkmod.glib = types.SimpleNamespace(idle_add=lambda fn: _run_on_other_thread(fn))
    monkeypatch.setitem(sys.modules, "webview.platforms.gtk", gtkmod)
    return gtkmod


def _fake_cocoa(monkeypatch, controller):
    cocoamod = types.ModuleType("webview.platforms.cocoa")
    config = types.SimpleNamespace(userContentController=lambda: controller)
    view = types.SimpleNamespace(webview=types.SimpleNamespace(configuration=lambda: config))
    cocoamod.BrowserView = types.SimpleNamespace(instances={"uid-1": view})
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", cocoamod)


@pytest.fixture()
def window():
    return types.SimpleNamespace(uid="uid-1")


def test_gtk_unregisters_jsbridge_on_the_ui_thread(monkeypatch, window):
    manager = MagicMock()
    seen = []
    manager.unregister_script_message_handler.side_effect = lambda n: seen.append(
        (n, threading.current_thread())
    )
    _fake_gtk(monkeypatch, manager)
    monkeypatch.setattr(native_bridge, "_backend", lambda: "gtk")

    # like production: called from a ``loaded`` handler thread, never the main thread
    out = []
    caller = threading.Thread(
        target=lambda: out.append(native_bridge.remove_native_handlers(window))
    )
    caller.start()
    caller.join(5)
    assert out == ["removed"]
    assert state.native_bridge == "removed"
    assert [n for n, _ in seen] == ["jsBridge"]
    assert seen[0][1] is not caller  # it hopped to the UI thread


def test_gtk_on_the_main_thread_runs_inline(monkeypatch):
    ran = []
    native_bridge._gtk_hop(lambda: ran.append(threading.current_thread()))
    assert ran == [threading.current_thread()]


def test_cocoa_removes_both_handlers_through_the_main_thread_hop(monkeypatch, window):
    controller = MagicMock()
    _fake_cocoa(monkeypatch, controller)
    monkeypatch.setattr(native_bridge, "_backend", lambda: "cocoa")
    hops = []
    monkeypatch.setattr(
        macos_dock, "_call_after", lambda fn, *a: hops.append(_run_on_other_thread(fn))
    )

    assert native_bridge.remove_native_handlers(window) == "removed"
    names = [c.args[0] for c in controller.removeScriptMessageHandlerForName_.call_args_list]
    assert names == ["jsBridge", "browserDelegate"]
    assert len(hops) == 1


def test_other_backends_are_not_applicable(monkeypatch, window):
    monkeypatch.setattr(native_bridge, "_backend", lambda: "other")
    assert native_bridge.remove_native_handlers(window) == "not-applicable"
    assert state.native_bridge == "not-applicable"


def test_backend_detection(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(renderer="gtkwebkit2"))
    assert native_bridge._backend() == "gtk"
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(renderer="edgechromium"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert native_bridge._backend() == "other"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert native_bridge._backend() == "cocoa"


def test_a_second_call_is_a_no_op_that_keeps_removed(monkeypatch, window):
    manager = MagicMock()
    _fake_gtk(monkeypatch, manager)
    monkeypatch.setattr(native_bridge, "_backend", lambda: "gtk")
    assert native_bridge.remove_native_handlers(window) == "removed"
    assert native_bridge.remove_native_handlers(window) == "removed"
    assert manager.unregister_script_message_handler.call_count == 1


def test_a_raising_job_is_failed_logged_and_never_raises(monkeypatch, window, caplog):
    manager = MagicMock()
    manager.unregister_script_message_handler.side_effect = RuntimeError("renamed in 6.0")
    _fake_gtk(monkeypatch, manager)
    monkeypatch.setattr(native_bridge, "_backend", lambda: "gtk")
    with caplog.at_level(logging.ERROR):
        assert native_bridge.remove_native_handlers(window) == "failed"
    assert state.native_bridge == "failed"
    assert any("renamed in 6.0" in r.getMessage() for r in caplog.records)


def test_a_job_that_never_runs_is_failed_after_the_bound(monkeypatch, window, caplog):
    monkeypatch.setattr(native_bridge, "_backend", lambda: "gtk")
    monkeypatch.setattr(native_bridge, "_gtk_hop", lambda job: None)  # dropped on the floor
    monkeypatch.setattr(native_bridge, "JOB_BOUND", 0.05)
    with caplog.at_level(logging.ERROR):
        assert native_bridge.remove_native_handlers(window) == "failed"
    assert state.native_bridge == "failed"


def test_a_missing_window_instance_is_failed(monkeypatch):
    _fake_gtk(monkeypatch, MagicMock())
    monkeypatch.setattr(native_bridge, "_backend", lambda: "gtk")
    assert native_bridge.remove_native_handlers(types.SimpleNamespace(uid="nope")) == "failed"


def test_window_state_reports_native_bridge_pending_then_the_result():
    state.reset()
    body = window_control.window_state()
    assert body["native_bridge"] == "pending"
    state.native_bridge = "removed"
    assert window_control.window_state()["native_bridge"] == "removed"
