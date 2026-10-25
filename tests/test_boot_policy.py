"""``BootPolicy`` (Mission 32, Flight 4, leg 2 phase 2a, DD1).

The decision table pins each flag's value per platform (the old ``sys.platform``
branches, written as data), the lazy selection through ``state.policy``, the
window-control routes reading the policy with no ``run()``, and the tray-hide
``visible`` fix (AC8).
"""

from __future__ import annotations

import dataclasses
import sys
from unittest.mock import MagicMock

import pytest

from the_one.interfaces.desktop import boot_policy, window_control
from the_one.interfaces.desktop.boot_policy import (
    LINUX,
    MACOS,
    OTHER,
    WINDOWS,
    BootPolicy,
    TrayPlan,
)
from the_one.interfaces.desktop.session_state import SessionState, state

# flag -> (windows, linux, macos, other)
TABLE = {
    "webview_assumed_present": (True, False, True, False),
    "first_launch_platform": ("win32", "linux", "darwin", "other"),
    "initial_tray_mode": (None, None, "dock", None),
    "splash_border": (True, False, False, False),
    "splash_blocked_in_quit_states": (False, False, True, False),
    "quit_in_boot_stops_without_destroy": (False, False, True, False),
    "wait_for_page_before_show": (False, False, True, False),
    "native_show_fallback": (True, False, False, False),
    "publish_quit_left_to_terminate": (False, False, True, False),
    "boot_error_terminates": (False, False, True, False),
    "installs_dock": (False, False, True, False),
    "runs_path_s": (False, False, True, False),
    "browser_fallback_notification": (False, True, False, False),
    "native_visibility": (False, False, True, False),
    "quit_after_loop_stopped_answers_window": (False, False, True, False),
    "quit_via_dock_terminate": (False, False, True, False),
    "focus_via_dock": (False, False, True, False),
}
POLICIES = (WINDOWS, LINUX, MACOS, OTHER)
TRAYS = (
    TrayPlan(skip=False, detect=False, records_tray_mode=False),
    TrayPlan(skip=False, detect=True, records_tray_mode=True),
    TrayPlan(skip=True, detect=False, records_tray_mode=False),
    TrayPlan(skip=False, detect=False, records_tray_mode=False),
)


@pytest.mark.parametrize("flag", sorted(TABLE))
def test_decision_table(flag):
    assert tuple(getattr(p, flag) for p in POLICIES) == TABLE[flag]


def test_tray_plan_per_policy():
    assert tuple(p.tray for p in POLICIES) == TRAYS


def test_the_table_covers_every_field():
    fields = {f.name for f in dataclasses.fields(BootPolicy)}
    assert fields == set(TABLE) | {"name", "tray"}


def test_other_matches_the_old_fall_through_and_is_not_linux():
    # gi probe, plain tray build, re-raise on a show failure, no notification
    assert OTHER.webview_assumed_present is False
    assert OTHER.tray == TrayPlan(skip=False, detect=False, records_tray_mode=False)
    assert OTHER.native_show_fallback is False
    assert OTHER.browser_fallback_notification is False
    assert OTHER.tray != LINUX.tray


def test_the_policy_is_frozen_data():
    with pytest.raises(dataclasses.FrozenInstanceError):
        WINDOWS.name = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("win32", WINDOWS),
        ("darwin", MACOS),
        ("linux", LINUX),
        ("linux2", LINUX),
        ("freebsd14", OTHER),
        ("cygwin", OTHER),
    ],
)
def test_current_selects_by_platform(monkeypatch, platform, expected):
    monkeypatch.setattr(sys, "platform", platform)
    assert boot_policy.current() is expected


def test_boot_policy_imports_only_the_standard_library():
    import ast
    import inspect

    mods = set()
    for node in ast.walk(ast.parse(inspect.getsource(boot_policy))):
        if isinstance(node, ast.Import):
            mods.update(n.name.split(".")[0] for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            mods.add((node.module or "").split(".")[0])
    assert mods <= {"__future__", "sys", "dataclasses", "typing"}, mods


# -- lazy selection through state --------------------------------------------


def test_state_policy_is_lazy_and_reset_clears_it(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert state._policy is None
    assert state.policy is WINDOWS
    monkeypatch.setattr(sys, "platform", "darwin")
    assert state.policy is WINDOWS  # chosen once, no mid-run flip
    state.reset()
    assert state._policy is None
    assert state.policy is MACOS


def test_a_fresh_state_does_not_share_the_policy():
    assert SessionState()._policy is None


def test_window_control_reads_the_policy_with_no_run(monkeypatch):
    """Routes called in serve mode / tests (no ``run()``) see a patched platform."""
    monkeypatch.setattr(sys, "platform", "darwin")
    state.reset()
    win = MagicMock()
    state.desktop_window = win
    seen = []
    monkeypatch.setattr(
        window_control.macos_dock, "native_visible", lambda w: seen.append(w) or True
    )
    assert window_control.window_visible() is True
    assert seen == [win]

    monkeypatch.setattr(sys, "platform", "win32")
    state.reset()
    state.desktop_window = win
    state.tracked_visible = False
    assert window_control.window_visible() is False  # tracked, not native
    assert seen == [win]


def test_run_binds_the_policy_once_after_its_reset(monkeypatch):
    from the_one.interfaces.desktop import shell

    monkeypatch.setattr(sys, "platform", "darwin")
    state.policy = WINDOWS  # a stale policy must not survive run()'s reset
    seen = []

    def _stop(host, port):
        seen.append(state._policy)
        raise RuntimeError("stop")

    monkeypatch.setattr(shell.takeover, "_select_port", _stop)
    with pytest.raises(RuntimeError):
        shell.DesktopSession().run()
    assert seen == [MACOS]
    assert state.tray_mode == "dock"


# -- AC8: close-to-tray clears the tracked visibility -------------------------


@pytest.fixture
def shell_session(monkeypatch):
    from the_one.interfaces.desktop import notice, shell, tray

    monkeypatch.setattr(notice, "notice_shown", lambda: True)
    monkeypatch.setattr(tray, "notify", lambda *a, **k: None)
    monkeypatch.setattr(window_control, "_is_gtk_backend", lambda: False)
    win = MagicMock()
    state.desktop_window = win
    sess = shell.DesktopSession()
    sess._icon = MagicMock()
    return sess, win


def test_close_to_tray_marks_hidden_then_every_show_path_marks_visible(shell_session, monkeypatch):
    sess, win = shell_session
    state.tracked_visible = True
    assert sess._close_to_tray() is True
    win.hide.assert_called_once()
    assert state.tracked_visible is False
    assert window_control.window_visible() is False

    sess._on_show(sess._icon)  # the tray Show callback
    assert state.tracked_visible is True
    assert window_control.window_visible() is True

    assert sess._close_to_tray() is True
    assert state.tracked_visible is False
    window_control._show_window(win)  # the boot show
    assert state.tracked_visible is True

    assert sess._close_to_tray() is True
    assert state.tracked_visible is False
    assert window_control.focus_window() is True  # single-instance focus
    assert state.tracked_visible is True


def test_a_failed_hide_leaves_tracked_visibility_alone(shell_session):
    sess, win = shell_session
    win.hide.side_effect = RuntimeError("boom")
    state.tracked_visible = True
    assert sess._close_to_tray() is False
    assert state.tracked_visible is True


def test_no_tray_hide_goes_through_mark_hidden(monkeypatch):
    marks = []
    monkeypatch.setattr(window_control, "_mark_hidden", lambda: marks.append(1))
    monkeypatch.setattr(window_control.notice, "no_tray_notice_shown", lambda: True)
    state.desktop_window = MagicMock()
    assert window_control._no_tray_hide() is True
    assert marks == [1]
