"""macOS dock mode, Phase B (M32 F3 leg 4): the ``shell.py`` wiring and ``install``.

``sys.platform`` is patched to ``darwin`` and every ``macos_dock`` AppKit seam is
replaced; nothing imports ``objc``. The harness mirrors ``tests/test_desktop_shell.py``.
"""

# ruff: noqa: N802
from __future__ import annotations

import logging
import os
import sys
from threading import Thread as _RealThread
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from the_one.interfaces.desktop import chrome, macos_dock, takeover, window_control
from the_one.interfaces.desktop.session_state import state

pytestmark = pytest.mark.usefixtures("stub_desktop_host")


@pytest.fixture()
def webview_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock)
    return mock


@pytest.fixture()
def seams(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the AppKit seams and os._exit with recorders."""
    calls: list[tuple] = []
    ns = SimpleNamespace(calls=calls)
    monkeypatch.setattr(macos_dock, "install", lambda s: calls.append(("install",)) or "subclass")
    monkeypatch.setattr(macos_dock, "order_out", lambda w: calls.append(("order_out", w)))
    monkeypatch.setattr(macos_dock, "terminate_app", lambda: calls.append(("terminate_app",)))
    monkeypatch.setattr(macos_dock, "flush_log_handlers", lambda: calls.append(("flush",)))
    monkeypatch.setattr(os, "_exit", lambda code: calls.append(("exit", code)))
    return ns


def _splash() -> MagicMock:
    splash = MagicMock()
    splash.events.shown.wait.return_value = True
    splash.events.loaded.__iadd__.side_effect = lambda handler: splash.events.loaded
    splash.events.loaded.is_set.return_value = False
    return splash


def _run(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    start_effect: Any = None,
    wait_effect: Any = None,
    create_effect: Any = None,
    loaded_is_set: Any = False,
    run_boot: bool = False,
    loaded_bound: float = 0.05,
    graceful: Any = None,
    platform: str = "darwin",
    splash_bound: float = 5.0,
) -> SimpleNamespace:
    import the_one.interfaces.desktop.shell as shell

    monkeypatch.setattr(shell.settings, "data_dir", tmp_path)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(chrome, "os_theme", lambda: "dark")
    monkeypatch.setattr(chrome, "register", lambda w, t: None)
    splash, main = _splash(), MagicMock()
    main.events.loaded.__iadd__.side_effect = lambda handler: main.events.loaded  # keep self
    if callable(loaded_is_set):
        main.events.loaded.is_set.side_effect = loaded_is_set
    elif isinstance(loaded_is_set, list):  # a scripted sequence; the last value repeats
        seq = list(loaded_is_set)
        main.events.loaded.is_set.side_effect = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
    else:
        main.events.loaded.is_set.return_value = loaded_is_set
    webview_mock.create_window.side_effect = create_effect or [splash, main]
    monkeypatch.setattr(macos_dock, "BOOT_WAIT_BOUND", 0.05)
    monkeypatch.setattr(shell, "MAIN_LOADED_BOUND", loaded_bound)
    monkeypatch.setattr(shell, "SPLASH_LOADED_BOUND", splash_bound)
    monkeypatch.setattr(shell, "SPLASH_SETTLE", 0.0)

    def _start(*args, **kwargs):
        if start_effect is not None:
            start_effect(*args, **kwargs)
        if run_boot:  # _boot runs inside the loop, before webview.start returns
            webview_mock.create_window.side_effect = create_effect or [main]
            args[0]()

    webview_mock.start.side_effect = _start
    ns = SimpleNamespace(shell=shell, splash=splash, main=main)
    gs = graceful or MagicMock()
    ns.graceful = gs
    with patch.object(takeover, "_select_port", return_value=(8484, False)):
        with patch.object(shell, "_webview_available", return_value=True):
            with patch.object(shell, "_graceful_shutdown", gs):
                with patch.object(shell, "_wait_until_serving", side_effect=wait_effect):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=MagicMock()):
                            with patch("threading.Thread", return_value=MagicMock()):
                                ns.error = None
                                try:
                                    shell.run_desktop()
                                except Exception as exc:  # noqa: BLE001
                                    ns.error = exc
    return ns


# -- run(): dock mode set-up -----------------------------------------------------


def test_dock_tray_mode_and_install_precede_webview_start(
    webview_mock, tmp_path, monkeypatch, seams
):
    seen = {}

    def _start(*a, **k):
        seen["tray_mode"] = state.tray_mode
        seen["installed_first"] = seams.calls[:1] == [("install",)]

    _run(webview_mock, tmp_path, monkeypatch, start_effect=_start)
    assert seen == {"tray_mode": "dock", "installed_first": True}


def test_no_pystray_on_darwin_boot(webview_mock, tmp_path, monkeypatch, seams):
    monkeypatch.delitem(sys.modules, "pystray", raising=False)
    build = MagicMock()
    monkeypatch.setattr("the_one.interfaces.desktop.tray.build_tray", build)
    ns = _run(webview_mock, tmp_path, monkeypatch, run_boot=True)
    assert ns.error is None
    build.assert_not_called()
    assert "pystray" not in sys.modules
    assert state.desktop_window is ns.main or state.tray_mode == "dock"


def test_prime_called_once_after_begin_boot(webview_mock, tmp_path, monkeypatch, seams):
    seen = []
    monkeypatch.setattr(
        "the_one.platform.env.prime_login_shell_path",
        lambda *a, **k: seen.append((state.booting, state.server)) or "not applicable",
    )
    _run(webview_mock, tmp_path, monkeypatch)
    assert seen == [(True, None)]  # booting set, server not started yet


def test_prime_not_called_on_the_is_ours_branch(webview_mock, tmp_path, monkeypatch, seams):
    import the_one.interfaces.desktop.shell as shell

    prime = MagicMock()
    monkeypatch.setattr("the_one.platform.env.prime_login_shell_path", prime)
    with patch.object(takeover, "_select_port", return_value=(8484, True)):
        with patch.object(takeover, "_takeover", return_value=(8484, True)):
            shell.run_desktop()
    prime.assert_not_called()


def test_server_and_thread_cleared_after_run(webview_mock, tmp_path, monkeypatch, seams):
    seen = {}

    def _start(*a, **k):
        seen["server"] = state.server
        seen["thread"] = state.thread

    _run(webview_mock, tmp_path, monkeypatch, start_effect=_start)
    assert seen["server"] is not None and seen["thread"] is not None
    assert state.server is None and state.thread is None


# -- path S ----------------------------------------------------------------------


def test_path_s_ordered_sequence(webview_mock, tmp_path, monkeypatch, seams):
    import the_one.interfaces.desktop.shell as shell

    order = seams.calls
    win = MagicMock()
    monkeypatch.setattr(
        shell.DesktopSession, "_save_current_geometry", lambda self, w: order.append(("save", w))
    )

    def _start(*a, **k):
        state.desktop_window = win  # a published window
        state.boot_stopped.set()
        order.append(("start-returns", state.loop_stopped))

    ns = _run(
        webview_mock,
        tmp_path,
        monkeypatch,
        start_effect=_start,
        graceful=MagicMock(side_effect=lambda s, t: order.append(("drain",))),
    )
    assert ns.error is None
    names = [c[0] for c in order]
    assert names == ["install", "start-returns", "order_out", "save", "drain", "flush", "exit"]
    assert order[1] == ("start-returns", False)
    assert state.loop_stopped is True and state.really_quit is True
    assert state.quit_requested is True  # a still-running _boot stops
    assert order[-1] == ("exit", 0)


def test_path_s_with_only_the_splash_saves_nothing(webview_mock, tmp_path, monkeypatch, seams):
    import the_one.interfaces.desktop.shell as shell

    saved = []
    monkeypatch.setattr(
        shell.DesktopSession, "_save_current_geometry", lambda s, w: saved.append(w)
    )
    monkeypatch.setattr(macos_dock, "BOOT_WAIT_BOUND", 0.01)
    _run(webview_mock, tmp_path, monkeypatch)  # start returns at once, no window published
    assert saved == []
    assert ("exit", 0) in seams.calls  # exits even though the boot never stopped


def test_path_s_waits_on_boot_stopped_before_exit(webview_mock, tmp_path, monkeypatch, seams):
    waited = []
    real = state.boot_stopped
    monkeypatch.setattr(macos_dock, "BOOT_WAIT_BOUND", 0.01)

    class _Ev:
        def wait(self, timeout=None):
            waited.append(timeout)
            return False

        def clear(self):
            real.clear()

        def set(self):
            real.set()

        def is_set(self):
            return real.is_set()

    monkeypatch.setattr(state, "boot_stopped", _Ev())
    _run(webview_mock, tmp_path, monkeypatch)
    assert waited == [0.05]


# -- _on_closing in dock mode ----------------------------------------------------


@pytest.fixture()
def closing(monkeypatch, tmp_path):
    import the_one.interfaces.desktop.shell as shell

    monkeypatch.setattr(shell.settings, "data_dir", tmp_path)
    state.reset()
    state.tray_mode = "dock"
    monkeypatch.setattr(window_control, "_is_gtk_backend", lambda: False)
    monkeypatch.setattr(chrome, "deregister", MagicMock())
    return shell.DesktopSession()


def test_dock_close_hides_a_published_window_without_notice(closing, monkeypatch):
    notes = []
    monkeypatch.setattr("the_one.interfaces.desktop.tray.notify", lambda *a: notes.append(a))
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    state.desktop_window = win
    assert closing._on_closing() is False  # cancel the destroy
    win.hide.assert_called_once()
    assert notes == []


def test_dock_close_before_publish_hides_the_native_window(closing):
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    closing._window = win
    assert closing._on_closing() is False
    win.hide.assert_called_once()


def test_dock_close_with_no_window_allows(closing):
    assert closing._on_closing() is True


def test_dock_close_after_really_quit_allows(closing):
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    state.desktop_window = win
    state.really_quit = True
    assert closing._on_closing() is True
    win.hide.assert_not_called()


def test_dock_failed_hide_allows(closing):
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    win.hide.side_effect = RuntimeError("boom")
    state.desktop_window = win
    assert closing._on_closing() is True


# -- _destroy_splash suppression and _boot's darwin abort/error ------------------


@pytest.mark.parametrize("flag", ["terminate_pending", "really_quit", "loop_stopped"])
def test_splash_destroy_is_suppressed_by_each_flag(
    webview_mock, tmp_path, monkeypatch, seams, flag
):
    def _start(*a, **k):
        pass

    # the flag is set before the boot's backstop would destroy the splash
    original = macos_dock.snapshot  # unused; keeps the seam list honest

    def _wait(*a, **k):
        setattr(state, flag, True)

    ns = _run(
        webview_mock,
        tmp_path,
        monkeypatch,
        wait_effect=_wait,
        loaded_is_set=True,
        run_boot=True,
    )
    assert original is macos_dock.snapshot
    ns.splash.destroy.assert_not_called()


def test_splash_still_destroyed_on_a_normal_darwin_boot(webview_mock, tmp_path, monkeypatch, seams):
    ns = _run(webview_mock, tmp_path, monkeypatch, loaded_is_set=True, run_boot=True)
    assert ns.error is None
    ns.splash.destroy.assert_called_once()
    assert state.boot_stopped.is_set()  # set on success too


def test_boot_abort_on_darwin_sets_boot_stopped_and_destroys_nothing(
    webview_mock, tmp_path, monkeypatch, seams
):
    def _quit(*a, **k):
        state.begin_quit()  # what the terminate callback does first

    ns = _run(webview_mock, tmp_path, monkeypatch, wait_effect=_quit, run_boot=True)
    assert ns.error is None
    assert state.boot_stopped.is_set()
    ns.splash.destroy.assert_not_called()
    ns.main.destroy.assert_not_called()
    webview_mock.create_window.assert_called_once()  # the main window was never created
    assert ("terminate_app",) not in seams.calls


def test_boot_error_on_darwin_calls_terminate_once(webview_mock, tmp_path, monkeypatch, seams):
    ns = _run(
        webview_mock,
        tmp_path,
        monkeypatch,
        wait_effect=RuntimeError("never ready"),
        run_boot=True,
    )
    assert isinstance(ns.error, RuntimeError)
    assert seams.calls.count(("terminate_app",)) == 1
    ns.splash.destroy.assert_not_called()
    assert state.boot_stopped.is_set()


def test_boot_error_with_terminate_pending_does_not_terminate_again(
    webview_mock, tmp_path, monkeypatch, seams
):
    def _fail(*a, **k):
        state.terminate_pending = True
        raise RuntimeError("never ready")

    ns = _run(webview_mock, tmp_path, monkeypatch, wait_effect=_fail, run_boot=True)
    assert isinstance(ns.error, RuntimeError)
    assert ("terminate_app",) not in seams.calls
    assert state.boot_stopped.is_set()


# -- the main window waits for its page before it is shown (HAT P1) --------------


def _show_recorder(monkeypatch):
    import the_one.interfaces.desktop.shell as shell_mod

    order: list[str] = []
    monkeypatch.setattr(shell_mod.window_control, "_show_window", lambda w: order.append("show"))
    monkeypatch.setattr(shell_mod.window_control, "_mark_visible", lambda: None)
    return order


def _macos_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("macos: main")]


def test_darwin_shows_main_only_after_loaded(webview_mock, tmp_path, monkeypatch, seams, caplog):
    caplog.set_level("INFO")
    order = _show_recorder(monkeypatch)
    # False x3 then True: the wait polls, shows only once loaded; step 4a then dismisses
    ns = _run(
        webview_mock,
        tmp_path,
        monkeypatch,
        loaded_is_set=[False, False, False, True],
        run_boot=True,
        loaded_bound=5.0,
    )
    assert ns.error is None
    assert order == ["show"]
    assert ns.main.events.loaded.is_set.call_count >= 4
    ns.splash.destroy.assert_called_once()
    lines = _macos_lines(caplog)
    assert len(lines) == 1 and lines[0].startswith("macos: main window shown after page load (")


def test_darwin_fallback_shows_after_the_bound(webview_mock, tmp_path, monkeypatch, seams, caplog):
    caplog.set_level("INFO")
    order = _show_recorder(monkeypatch)
    ns = _run(webview_mock, tmp_path, monkeypatch, loaded_is_set=False, run_boot=True)
    assert ns.error is None
    assert order == ["show"]
    assert _macos_lines(caplog) == [
        "macos: main window shown after the 0.05s fallback (page not loaded)"
    ]


def test_darwin_quit_during_the_wait_stops_without_showing(
    webview_mock, tmp_path, monkeypatch, seams, caplog
):
    caplog.set_level("INFO")
    order = _show_recorder(monkeypatch)
    calls = {"n": 0}

    def _is_set():
        calls["n"] += 1
        if calls["n"] == 2:
            state.begin_quit()  # what the terminate callback does first
        return False

    ns = _run(
        webview_mock, tmp_path, monkeypatch, loaded_is_set=_is_set, run_boot=True, loaded_bound=30.0
    )
    assert ns.error is None
    assert order == []  # never shown
    assert _macos_lines(caplog) == []
    assert state.boot_stopped.is_set()
    ns.splash.destroy.assert_not_called()
    ns.main.destroy.assert_not_called()
    assert ("terminate_app",) not in seams.calls


# -- install and the delegate callbacks ------------------------------------------


@pytest.fixture()
def fresh_install(monkeypatch):
    monkeypatch.setattr(macos_dock, "_ACTIVITY_TOKEN", None)
    monkeypatch.setattr(macos_dock, "_INSTALLED_ROUTE", None)


def test_install_stores_the_activity_token_at_module_level(fresh_install, monkeypatch):
    token = object()
    monkeypatch.setattr(macos_dock, "_install_delegate", lambda s: "subclass")
    monkeypatch.setattr(macos_dock, "_begin_activity", lambda: token)
    assert macos_dock.install(object()) == "subclass"
    assert macos_dock._ACTIVITY_TOKEN is token


def test_install_runs_once_and_logs_the_route(fresh_install, monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(macos_dock, "_install_delegate", lambda s: calls.append(1) or "subclass")
    monkeypatch.setattr(macos_dock, "_begin_activity", lambda: object())
    with caplog.at_level(logging.INFO, logger="the_one.interfaces.desktop.shell"):
        macos_dock.install(object())
        macos_dock.install(object())
    assert calls == [1]
    assert any("route=subclass" in r.getMessage() for r in caplog.records)


def test_install_survives_an_activity_failure(fresh_install, monkeypatch):
    monkeypatch.setattr(macos_dock, "_install_delegate", lambda s: "subclass")
    monkeypatch.setattr(macos_dock, "_begin_activity", MagicMock(side_effect=RuntimeError))
    assert macos_dock.install(object()) == "subclass"
    assert macos_dock._ACTIVITY_TOKEN is None


class _Session:
    def __init__(self):
        self._window = None
        self.saved = []
        self.drained = []

    def _save_current_geometry(self, w):
        self.saved.append(w)

    def _drain(self, server, thread):
        self.drained.append((server, thread))


@pytest.fixture()
def terminate_env(monkeypatch):
    state.reset()
    monkeypatch.setattr(chrome, "deregister", MagicMock())
    workers = []

    class _W:
        def __init__(self, **kw):
            self.kw = kw
            workers.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(macos_dock, "TerminateWorker", _W)
    return workers


def test_handle_terminate_drains_and_returns_later(terminate_env):
    sess, win = _Session(), object()
    state.server, state.thread, state.desktop_window = "srv", "thr", win
    assert macos_dock.handle_terminate(sess) == macos_dock.NS_TERMINATE_LATER
    assert state.terminate_pending and state.really_quit and state.quit_requested
    assert sess.saved == [win]  # geometry read in the callback, before returning
    (w,) = terminate_env
    assert w.started and w.kw["reply"] is macos_dock.reply_to_terminate
    w.kw["drain"]()
    assert sess.drained == [("srv", "thr")]


def test_handle_terminate_twice_starts_one_worker(terminate_env):
    sess = _Session()
    state.server, state.thread = "srv", "thr"
    assert macos_dock.handle_terminate(sess) == macos_dock.NS_TERMINATE_LATER
    assert macos_dock.handle_terminate(sess) == macos_dock.NS_TERMINATE_LATER
    assert len(terminate_env) == 1


def test_handle_terminate_window_client_replies_now(terminate_env):
    assert macos_dock.handle_terminate(_Session()) == macos_dock.NS_TERMINATE_NOW
    assert terminate_env == [] and not state.terminate_pending


def test_handle_terminate_unpublished_window_skips_the_save(terminate_env):
    sess = _Session()
    state.server, state.thread = "srv", "thr"
    macos_dock.handle_terminate(sess)
    assert sess.saved == []


def test_handle_terminate_never_raises(terminate_env, monkeypatch):
    monkeypatch.setattr(macos_dock, "snapshot", MagicMock(side_effect=RuntimeError))
    assert macos_dock.handle_terminate(_Session()) == macos_dock.NS_TERMINATE_NOW


def test_handle_reopen_shows_a_published_window(monkeypatch):
    state.reset()
    shown = []
    monkeypatch.setattr(macos_dock, "activate", lambda w: shown.append(w))
    state.desktop_window = win = object()
    assert macos_dock.handle_reopen(_Session(), True) is False
    assert shown == [win]


def test_handle_reopen_ignores_during_quit_and_defers_booting(monkeypatch):
    state.reset()
    shown = []
    monkeypatch.setattr(macos_dock, "activate", lambda w: shown.append(w))
    state.booting = True  # no published window: defer
    macos_dock.handle_reopen(_Session(), False)
    state.booting = False
    state.desktop_window = object()
    state.terminate_pending = True
    macos_dock.handle_reopen(_Session(), False)
    assert shown == []


def test_reopen_signature_prefers_the_protocol_and_strips_offsets():
    class _Proto:
        def descriptionForInstanceMethod_(self, sel):
            return (sel, b"B24@0:8@16B20")

    objc = SimpleNamespace(protocolNamed=lambda n: _Proto())
    assert macos_dock._reopen_signature(objc) == b"B@:@B"


def test_reopen_signature_falls_back_to_type_constants():
    objc = SimpleNamespace(
        protocolNamed=lambda n: (_ for _ in ()).throw(RuntimeError),
        _C_NSBOOL=b"B",
        _C_ID=b"@",
        _C_SEL=b":",
    )
    assert macos_dock._reopen_signature(objc) == b"B@:@B"


def test_a_dock_close_state_route_reports_dock(closing):
    assert window_control.window_state()["tray"] == "dock"


# -- squawk 0261: the darwin splash stays hidden until its own `loaded` ----------


def _splash_loaded_handler(splash):
    """The handler subscribed to ``splash.events.loaded`` (``+=`` recorded as a call)."""
    return splash.events.loaded.__iadd__.call_args.args[0]


def test_darwin_splash_is_created_hidden_and_not_shown_before_loaded(
    webview_mock, tmp_path, monkeypatch, seams
):
    seen = {}
    holder = {}

    def _start(*a, **k):  # the loop is "running": the splash exists, hidden
        splash = holder["ns_splash"]
        seen["before"] = splash.show.call_count
        handler = _splash_loaded_handler(splash)
        handler()  # the splash's own `loaded`
        seen["after"] = splash.show.call_count
        handler()  # idempotent
        seen["again"] = splash.show.call_count

    _run(
        webview_mock,
        tmp_path,
        monkeypatch,
        start_effect=_start,
        create_effect=_capture_splash(holder),
    )
    assert webview_mock.create_window.call_args_list[0].kwargs["hidden"] is True
    assert seen == {"before": 0, "after": 1, "again": 1}


def _capture_splash(holder):
    created = []

    def _make(*a, **k):
        w = MagicMock()
        if not created:
            w = _splash()
            holder["ns_splash"] = w
        created.append(w)
        return w

    return _make


def test_darwin_splash_bound_shows_it_when_loaded_never_comes(
    webview_mock, tmp_path, monkeypatch, seams
):
    import threading

    shown = threading.Event()
    reached = []

    def _wait(*a, **k):  # runs in _boot, after the bound thread started
        reached.append(shown.wait(5))

    holder = {}

    def _make(*a, **k):
        w = _splash() if "s" not in holder else MagicMock()
        if "s" not in holder:
            w.show.side_effect = lambda: shown.set()
            holder["s"] = w
        return w

    ns = _run(
        webview_mock,
        tmp_path,
        monkeypatch,
        run_boot=True,
        splash_bound=0.05,
        wait_effect=_wait,
        loaded_is_set=False,
        loaded_bound=0.01,
        create_effect=_make,
    )
    assert reached == [True]  # the bound, not `loaded`, showed it
    assert holder["s"].show.call_count == 1
    assert ns.error is None


def test_darwin_splash_not_shown_after_it_was_destroyed(webview_mock, tmp_path, monkeypatch, seams):
    ns = _run(webview_mock, tmp_path, monkeypatch, loaded_is_set=True, run_boot=True)
    # main loaded first: the splash is destroyed while still hidden, never shown
    ns.splash.destroy.assert_called_once()
    ns.splash.show.assert_not_called()
    _splash_loaded_handler(ns.splash)()  # a late splash `loaded` after the destroy
    ns.splash.show.assert_not_called()


def test_darwin_splash_not_shown_after_the_main_window_is_shown(
    webview_mock, tmp_path, monkeypatch, seams
):
    # main's page never reports loaded: it is shown at the fallback bound and the splash
    # is neither destroyed nor closed, so only the `_main_shown` guard can stop the show
    ns = _run(
        webview_mock, tmp_path, monkeypatch, run_boot=True, loaded_is_set=False, loaded_bound=0.01
    )
    assert ns.error is None
    ns.main.show.assert_called()
    ns.splash.destroy.assert_not_called()
    _splash_loaded_handler(ns.splash)()
    ns.splash.show.assert_not_called()


def test_darwin_splash_not_shown_once_a_quit_was_requested(
    webview_mock, tmp_path, monkeypatch, seams
):
    seen = {}

    def _start(*a, **k):
        with state.lock:
            state.quit_requested = True  # only quit_was_requested() sees this
        seen["blocked_flags"] = (state.terminate_pending, state.really_quit, state.loop_stopped)
        _splash_loaded_handler(holder["s"])()

    holder = {}

    def _make(*a, **k):
        if "s" in holder:
            return MagicMock()
        holder["s"] = _splash()
        return holder["s"]

    _run(webview_mock, tmp_path, monkeypatch, start_effect=_start, create_effect=_make)
    assert seen["blocked_flags"] == (False, False, False)
    holder["s"].show.assert_not_called()


def test_darwin_splash_concurrent_show_attempts_show_once(
    webview_mock, tmp_path, monkeypatch, seams
):
    import threading
    import time

    holder = {}

    def _make(*a, **k):
        if "s" in holder:
            return MagicMock()
        w = holder["s"] = _splash()
        w.show.side_effect = lambda: time.sleep(0.05)  # widen the race window
        return w

    def _start(*a, **k):
        handler = _splash_loaded_handler(holder["s"])
        barrier = threading.Barrier(2)

        def _go():
            barrier.wait()
            handler()

        threads = [_RealThread(target=_go) for _ in range(2)]  # _run patches threading.Thread
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    _run(webview_mock, tmp_path, monkeypatch, start_effect=_start, create_effect=_make)
    assert holder["s"].show.call_count == 1


def test_darwin_bound_thread_start_failure_shows_the_splash_directly(
    webview_mock, tmp_path, monkeypatch, seams
):
    import the_one.interfaces.desktop.shell as shell

    def _boom(target):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(shell, "_start_daemon", _boom)
    holder = {}

    def _make(*a, **k):
        if "s" in holder:
            return MagicMock()
        holder["s"] = _splash()
        return holder["s"]

    ns = _run(
        webview_mock,
        tmp_path,
        monkeypatch,
        run_boot=True,
        loaded_is_set=True,
        create_effect=_make,
    )
    assert ns.error is None
    assert state.boot_stopped.is_set()
    holder["s"].show.assert_called_once_with()


@pytest.mark.parametrize("platform", ["win32", "linux", "freebsd13"])
def test_other_policies_keep_the_visible_splash(
    webview_mock, tmp_path, monkeypatch, seams, platform
):
    ns = _run(webview_mock, tmp_path, monkeypatch, platform=platform)
    assert webview_mock.create_window.call_args_list[0].kwargs["hidden"] is False
    # no loaded subscription, no show: today's behaviour
    ns.splash.events.loaded.__iadd__.assert_not_called()
    ns.splash.show.assert_not_called()
