"""Per-platform desktop boot rules, as data (Mission 32, Flight 4, leg 2, DD1).

``shell.py`` and ``window_control.py`` used to read ``sys.platform`` at 21 sites
to decide how the window boots, hides and quits. Those decisions live here as
flags on one ``BootPolicy`` per platform; the shell and window control read the
flags and still do all the work. This module is pure data and imports only the
standard library: it holds no reference to ``macos_dock``, ``desktop_host``,
``tray``, ``chrome`` or pywebview, so ``session_state`` can import it without a
cycle, and every native call stays where a test already patches it.

``current()`` is the ONE place that reads the platform. ``session_state.state``
calls it lazily on first read of ``state.policy`` and ``state.reset()`` clears
it, so a test that patches the platform and then resets sees the new policy.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import NamedTuple


class TrayPlan(NamedTuple):
    """How the launch sequence decides the tray.

    ``skip``: no tray at all (the dock stands in; pystray is never imported).
    ``detect``: probe for a StatusNotifier or X11 tray first, and start none when
    the probe says there is none. ``records_tray_mode``: write the outcome to
    ``state.tray_mode`` (the detected mode, or ``"failed"``).
    """

    skip: bool
    detect: bool
    records_tray_mode: bool


@dataclass(frozen=True)
class BootPolicy:
    """One platform's boot and window-control decisions. ``name`` is for logs and
    tests only; code never branches on it."""

    name: str
    # _webview_available: True when the backend is assumed present (no gi probe).
    webview_assumed_present: bool
    # First-launch sizing: the platform string window_state.first_launch_size takes.
    first_launch_platform: str
    # The tray mode set before the loop starts (None leaves it undecided).
    initial_tray_mode: str | None
    tray: TrayPlan
    # Windows: tint the splash's border before its first show.
    splash_border: bool
    # macOS: the splash must not be destroyed while a terminate drains, after the
    # loop stopped, after a failed boot, or once a quit was requested.
    splash_blocked_in_quit_states: bool
    # macOS: a quit seen by _boot stops without a destroy (the terminate path owns it).
    quit_in_boot_stops_without_destroy: bool
    # macOS: keep the main window hidden until its page has loaded (bounded).
    wait_for_page_before_show: bool
    # Windows: a failed show() falls back to the native show.
    native_show_fallback: bool
    # macOS: a quit that arrives at publish time is left to the terminate path.
    publish_quit_left_to_terminate: bool
    # macOS: a boot error asks the app to terminate instead of destroying windows.
    boot_error_terminates: bool
    # macOS: install the dock delegate before the loop starts.
    installs_dock: bool
    # macOS: after the loop returns, run the path-S exit.
    runs_path_s: bool
    # Linux: the browser fallback also posts a desktop notification.
    browser_fallback_notification: bool
    # window_control: visibility, quit and focus.
    native_visibility: bool  # macOS reads the dock's native visible state
    quit_after_loop_stopped_answers_window: bool  # macOS path S
    quit_via_dock_terminate: bool  # macOS path T
    focus_via_dock: bool  # macOS activates through the dock


_NO_TRAY = TrayPlan(skip=True, detect=False, records_tray_mode=False)
_DETECT_TRAY = TrayPlan(skip=False, detect=True, records_tray_mode=True)
_PLAIN_TRAY = TrayPlan(skip=False, detect=False, records_tray_mode=False)

WINDOWS = BootPolicy(
    name="windows",
    webview_assumed_present=True,
    first_launch_platform="win32",
    initial_tray_mode=None,
    tray=_PLAIN_TRAY,
    splash_border=True,
    splash_blocked_in_quit_states=False,
    quit_in_boot_stops_without_destroy=False,
    wait_for_page_before_show=False,
    native_show_fallback=True,
    publish_quit_left_to_terminate=False,
    boot_error_terminates=False,
    installs_dock=False,
    runs_path_s=False,
    browser_fallback_notification=False,
    native_visibility=False,
    quit_after_loop_stopped_answers_window=False,
    quit_via_dock_terminate=False,
    focus_via_dock=False,
)

LINUX = BootPolicy(
    name="linux",
    webview_assumed_present=False,
    first_launch_platform="linux",
    initial_tray_mode=None,
    tray=_DETECT_TRAY,
    splash_border=False,
    splash_blocked_in_quit_states=False,
    quit_in_boot_stops_without_destroy=False,
    wait_for_page_before_show=False,
    native_show_fallback=False,
    publish_quit_left_to_terminate=False,
    boot_error_terminates=False,
    installs_dock=False,
    runs_path_s=False,
    browser_fallback_notification=True,
    native_visibility=False,
    quit_after_loop_stopped_answers_window=False,
    quit_via_dock_terminate=False,
    focus_via_dock=False,
)

MACOS = BootPolicy(
    name="macos",
    webview_assumed_present=True,
    first_launch_platform="darwin",
    initial_tray_mode="dock",
    tray=_NO_TRAY,
    splash_border=False,
    splash_blocked_in_quit_states=True,
    quit_in_boot_stops_without_destroy=True,
    wait_for_page_before_show=True,
    native_show_fallback=False,
    publish_quit_left_to_terminate=True,
    boot_error_terminates=True,
    installs_dock=True,
    runs_path_s=True,
    browser_fallback_notification=False,
    native_visibility=True,
    quit_after_loop_stopped_answers_window=True,
    quit_via_dock_terminate=True,
    focus_via_dock=True,
)

# Any other platform reproduces the old fall-through exactly: the gi probe, a
# plain tray build (no detection, no tray_mode write), a re-raise when show()
# fails and no browser-fallback notification. Linux differs on several of these,
# so it cannot stand in for it.
OTHER = BootPolicy(
    name="other",
    webview_assumed_present=False,
    first_launch_platform="other",
    initial_tray_mode=None,
    tray=_PLAIN_TRAY,
    splash_border=False,
    splash_blocked_in_quit_states=False,
    quit_in_boot_stops_without_destroy=False,
    wait_for_page_before_show=False,
    native_show_fallback=False,
    publish_quit_left_to_terminate=False,
    boot_error_terminates=False,
    installs_dock=False,
    runs_path_s=False,
    browser_fallback_notification=False,
    native_visibility=False,
    quit_after_loop_stopped_answers_window=False,
    quit_via_dock_terminate=False,
    focus_via_dock=False,
)


def current() -> BootPolicy:
    """The policy for the platform at this moment (the only platform read)."""
    platform = sys.platform
    if platform == "win32":
        return WINDOWS
    if platform == "darwin":
        return MACOS
    if platform.startswith("linux"):
        return LINUX
    return OTHER
