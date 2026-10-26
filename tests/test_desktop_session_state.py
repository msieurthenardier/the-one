"""``SessionState`` (Mission 32, Flight 3, DD1): the desktop lifecycle flags and the
critical sections that guard them.

The autouse ``_reset_desktop_session_state`` fixture in ``tests/conftest.py`` resets
the process-wide instance around every test; these tests build their own instances
where the lock or the identity matters.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from the_one.interfaces.desktop.session_state import SessionState, state


def test_defaults():
    st = SessionState()
    assert st.really_quit is False
    assert st.desktop_window is None
    assert st.tray_mode is None
    assert st.session is None
    assert st.tracked_visible is None
    assert st.booting is False
    assert st.quit_requested is False
    assert st.browser_server is None
    assert st.server is None and st.thread is None
    assert st.boot_stopped.is_set() is False
    assert st._policy is None  # the policy is unset until first read
    assert isinstance(st.lock, type(threading.Lock()))


def test_reset_restores_every_field_in_place():
    st = SessionState()
    lock, event = st.lock, st.boot_stopped
    st.really_quit = True
    st.desktop_window = object()
    st.tray_mode = "indicator"
    st.session = object()
    st.tracked_visible = False
    st.booting = True
    st.quit_requested = True
    st.browser_server = object()
    st.server, st.thread = object(), object()
    st.boot_stopped.set()
    _ = st.policy
    st.reset()
    assert vars(st).keys() == vars(SessionState()).keys()
    assert st.really_quit is False and st.desktop_window is None and st.tray_mode is None
    assert st.session is None and st.tracked_visible is None
    assert st.booting is False and st.quit_requested is False and st.browser_server is None
    assert st.server is None and st.thread is None
    assert st.boot_stopped.is_set() is False
    assert st._policy is None
    # the same lock and event objects: reset never rebinds them
    assert st.lock is lock and st.boot_stopped is event


def test_module_instance_is_never_rebound_by_reset():
    before = state
    state.really_quit = True
    state.reset()
    from the_one.interfaces.desktop import session_state

    assert session_state.state is before and state.really_quit is False


def test_begin_boot_and_clear_booting():
    st = SessionState()
    st.begin_boot()
    assert st.booting is True and not st.lock.locked()
    st.clear_booting()
    assert st.booting is False and not st.lock.locked()


def test_quit_was_requested_reads_the_flag():
    st = SessionState()
    assert st.quit_was_requested() is False
    st.quit_requested = True
    assert st.quit_was_requested() is True and not st.lock.locked()


def test_publish_window_publishes_clears_booting_and_returns_the_quit_flag():
    st = SessionState()
    st.booting = True
    win = object()
    assert st.publish_window(win) is False
    assert st.desktop_window is win and st.booting is False
    st.booting = True
    st.quit_requested = True
    assert st.publish_window(win) is True  # the caller runs _on_quit after the lock
    assert st.booting is False and not st.lock.locked()


def test_claim_browser_server_wins_unless_a_quit_was_recorded():
    st = SessionState()
    st.booting = True
    server = object()
    assert st.claim_browser_server(server) is True
    assert st.browser_server is server and st.booting is False
    st2 = SessionState()
    st2.booting = True
    st2.quit_requested = True
    assert st2.claim_browser_server(server) is False
    assert st2.browser_server is None and st2.booting is False  # cleared either way


def test_release_browser_server():
    st = SessionState()
    st.browser_server = object()
    st.release_browser_server()
    assert st.browser_server is None and not st.lock.locked()


def test_request_quit_nothing_to_quit():
    st = SessionState()
    assert st.request_quit() == (None, None)
    st.session = MagicMock()  # a session with no window, boot or fallback server
    assert st.request_quit() == (None, None)
    assert st.quit_requested is False


def test_request_quit_window_returns_the_session_after_unlock():
    st = SessionState()
    session = MagicMock()
    st.session, st.desktop_window = session, object()
    tag, got = st.request_quit()
    assert (tag, got) == ("window", session)
    assert not st.lock.locked()
    session._on_quit.assert_not_called()  # the caller runs it, outside the lock


def test_request_quit_already_when_really_quit_is_set():
    st = SessionState()
    st.session, st.desktop_window, st.really_quit = MagicMock(), object(), True
    assert st.request_quit() == ("already", None)


def test_request_quit_booting_records_the_request():
    st = SessionState()
    st.booting = True
    assert st.request_quit() == ("booting", None)
    assert st.quit_requested is True
    assert st.request_quit() == ("booting", None)  # idempotent


def test_request_quit_browser_drains_the_server_under_the_lock():
    st = SessionState()
    seen: list[bool] = []

    class Server:
        @property
        def should_exit(self):
            return False

        @should_exit.setter
        def should_exit(self, value):
            seen.append(st.lock.locked())

    st.browser_server = Server()
    assert st.request_quit() == ("browser", None)
    assert seen == [True]  # as before the split: set under the lock


def test_request_quit_window_published_without_a_session_falls_through():
    st = SessionState()
    st.desktop_window = object()  # no session: not a quittable window
    st.booting = True
    assert st.request_quit() == ("booting", None)
