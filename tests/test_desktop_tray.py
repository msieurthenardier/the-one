"""Mocked-GUI unit tests for the system-tray and close-to-tray feature.

pystray, Pillow (PIL), and webview are NOT installed on this host.  All three
are mocked via sys.modules injection — the same pattern used by
test_desktop_shell.py for webview.

Do NOT import pystray, PIL, or webview at module top level.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest


# ── Event capture helper ──────────────────────────────────────────────────────

class _EventCapture:
    """Simple stand-in for pywebview's event attribute.

    Supports ``+=`` operator to register handlers, and calling the instance
    invokes all registered handlers.

    pywebview's Event uses ``__iadd__`` to register handlers, so we need a
    real object (not a MagicMock) whose ``__iadd__`` is well-defined.
    """

    def __init__(self) -> None:
        self._handlers: list[Callable] = []

    def __iadd__(self, handler: Callable) -> "_EventCapture":
        self._handlers.append(handler)
        return self

    def fire(self, *args, **kwargs):
        """Invoke all registered handlers and return the last result."""
        result = None
        for h in self._handlers:
            result = h(*args, **kwargs)
        return result

    @property
    def registered(self) -> list[Callable]:
        return list(self._handlers)


def _make_mock_window() -> tuple[MagicMock, _EventCapture]:
    """Return (mock_window, closing_event) where closing_event captures += calls."""
    mock_window = MagicMock()
    closing_event = _EventCapture()
    mock_window.events.closing = closing_event
    return mock_window, closing_event


# ── shared mock-module fixtures ───────────────────────────────────────────────


@pytest.fixture()
def pystray_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a MagicMock for 'pystray' into sys.modules."""
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "pystray", mock)
    return mock


@pytest.fixture()
def pil_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a MagicMock for 'PIL' and 'PIL.Image' into sys.modules."""
    pil = MagicMock()
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", pil.Image)
    return pil


@pytest.fixture()
def webview_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a MagicMock for 'webview' into sys.modules."""
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock)
    return mock


@pytest.fixture()
def tray_module(pystray_mock: MagicMock, pil_mock: MagicMock):
    """Return a freshly-reloaded desktop.tray module with pystray+PIL mocked."""
    import the_one.interfaces.desktop.tray as tray_mod

    importlib.reload(tray_mod)
    return tray_mod


@pytest.fixture()
def shell_module(
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    webview_mock: MagicMock,
):
    """Return a freshly-reloaded desktop.shell module with all GUI mocks in place.

    Also resets module-level lifecycle state (_really_quit, _desktop_window) so
    tests start from a clean slate regardless of order.
    """
    import the_one.interfaces.desktop.shell as shell_mod

    importlib.reload(shell_mod)
    return shell_mod


# ── tray.py: lazy-import / icon-path ─────────────────────────────────────────


def test_tray_module_imports_without_pystray_installed() -> None:
    """Importing desktop.tray without pystray in sys.modules must not raise.

    The module uses lazy imports (inside functions), so importing the module
    itself succeeds even when pystray and PIL are absent.
    """
    # Ensure the modules are absent, then import.
    for name in ("pystray", "PIL", "PIL.Image"):
        sys.modules.pop(name, None)

    # This must not raise ImportError.
    import the_one.interfaces.desktop.tray  # noqa: F401 — side-effect import test


def test_icon_path_exists() -> None:
    """The brand PNG that build_tray loads must exist in the repository."""
    import the_one.interfaces.web as _web_pkg

    icon_path = Path(_web_pkg.__file__).parent / "static" / "brand" / "gleepglorp_icon.png"
    assert icon_path.exists(), f"Brand icon not found at {icon_path}"


# ── tray.py: build_tray ───────────────────────────────────────────────────────


def test_build_tray_returns_icon_with_show_and_quit(
    tray_module: Any,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
) -> None:
    """build_tray() creates a pystray.Icon with Show and Quit menu items."""
    on_show = MagicMock()
    on_quit = MagicMock()

    # build_tray calls pystray.Icon(...) — the mock records the call.
    icon = tray_module.build_tray(on_show=on_show, on_quit=on_quit)

    # pystray.Icon was called once.
    pystray_mock.Icon.assert_called_once()

    # Menu was built with two items.
    pystray_mock.Menu.assert_called_once()
    menu_call_args = pystray_mock.Menu.call_args[0]  # positional args to Menu()
    assert len(menu_call_args) == 2, "Menu should have exactly two items (Show, Quit)"

    # First item is Show (default=True), second is Quit.
    show_item_call = pystray_mock.MenuItem.call_args_list[0]
    quit_item_call = pystray_mock.MenuItem.call_args_list[1]

    assert show_item_call.args[0] == "Show"
    assert show_item_call.args[1] is on_show
    assert show_item_call.kwargs.get("default") is True

    assert quit_item_call.args[0] == "Quit"
    assert quit_item_call.args[1] is on_quit


# ── tray.py: notify wrapper ───────────────────────────────────────────────────


def test_notify_calls_icon_notify_with_correct_arg_order(tray_module: Any) -> None:
    """notify(icon, message, title) → icon.notify(message, title).

    The argument order is important: message is the body, title is the balloon
    title (matching pystray's Icon.notify(message, title=None) signature).
    """
    icon = MagicMock()
    tray_module.notify(icon, "body text", "balloon title")
    icon.notify.assert_called_once_with("body text", "balloon title")


# ── notice.py ────────────────────────────────────────────────────────────────


def test_notice_shown_false_before_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """notice_shown() returns False when no marker file exists."""
    import the_one.interfaces.desktop.notice as notice_mod

    monkeypatch.setattr(notice_mod, "_marker_path", lambda: tmp_path / ".close_to_tray_notice_shown")
    assert notice_mod.notice_shown() is False


def test_notice_shown_true_after_mark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After mark_notice_shown(), notice_shown() returns True."""
    import the_one.interfaces.desktop.notice as notice_mod

    marker = tmp_path / ".close_to_tray_notice_shown"
    monkeypatch.setattr(notice_mod, "_marker_path", lambda: marker)

    notice_mod.mark_notice_shown()
    assert notice_mod.notice_shown() is True
    assert marker.exists()


def test_mark_notice_shown_creates_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mark_notice_shown() creates data_dir (and parents) if missing."""
    import the_one.interfaces.desktop.notice as notice_mod

    # Use a nested path that definitely doesn't exist yet.
    deep_dir = tmp_path / "a" / "b" / "c"
    marker = deep_dir / ".close_to_tray_notice_shown"
    monkeypatch.setattr(notice_mod, "_marker_path", lambda: marker)

    assert not deep_dir.exists()
    notice_mod.mark_notice_shown()
    assert deep_dir.exists()
    assert marker.exists()


# ── shell.py: closing handler ─────────────────────────────────────────────────


def _run_desktop_with_tray(
    shell_module: Any,
    webview_mock: MagicMock,
    tray_mod: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    fake_build_tray=None,
    mock_window=None,
    closing_event=None,
) -> tuple[MagicMock, _EventCapture]:
    """Helper: run shell_module.run_desktop() with mocks wired, return (window, closing_event).

    If ``fake_build_tray`` is provided it is installed as the build_tray patch.
    If the caller already patched tray_mod.build_tray before calling this helper,
    pass ``fake_build_tray=None`` (the default) and the existing patch is kept.
    If neither is set, a default no-op icon is used.
    """
    if mock_window is None or closing_event is None:
        mock_window, closing_event = _make_mock_window()

    monkeypatch.setattr(shell_module.settings, "data_dir", tmp_path)
    webview_mock.create_window.return_value = mock_window

    if fake_build_tray is not None:
        monkeypatch.setattr(tray_mod, "build_tray", fake_build_tray)
    # else: caller either patched it already, or we let the real build_tray run
    # (which would fail without pystray — so callers that need tray wiring must
    #  patch tray_mod.build_tray themselves before calling this helper).

    with patch.object(shell_module, "_select_port", return_value=(8484, False)):
        with patch.object(shell_module, "_webview_available", return_value=True):
            with patch.object(shell_module, "_graceful_shutdown"):
                with patch.object(shell_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server") as _mock_srv_cls:
                            _mock_srv_cls.return_value = MagicMock()
                            with patch("threading.Thread") as _mock_thread_cls:
                                _mock_thread_cls.return_value = MagicMock()
                                shell_module.run_desktop()

    return mock_window, closing_event


def test_closing_handler_hides_window_and_returns_false(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The closing handler hides the window and returns False when _really_quit=False.

    Tests the core close-to-tray path: window hide() is called, and False is
    returned to cancel the destroy.
    """
    import the_one.interfaces.desktop.notice as notice_mod
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()

    # Pre-mark notice so the notify path doesn't add noise.
    marker = tmp_path / ".close_to_tray_notice_shown"
    monkeypatch.setattr(notice_mod, "_marker_path", lambda: marker)
    marker.touch()

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert len(closing_event.registered) == 1, "_on_closing must be registered once"

    # Simulate the user clicking X — _really_quit is False.
    result = closing_event.fire()

    assert result is False, "Handler must return False to cancel the close"
    mock_window.hide.assert_called_once()


def test_closing_handler_returns_true_when_really_quit(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The closing handler returns True (allow destroy) when _really_quit is set."""
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()
    mock_icon = MagicMock()
    monkeypatch.setattr(tray_mod, "build_tray", lambda **kw: mock_icon)

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert len(closing_event.registered) == 1

    # Simulate Quit having set the flag.
    shell_module._really_quit = True

    result = closing_event.fire()
    assert result is True, "Handler must return True when _really_quit is set"
    mock_window.hide.assert_not_called()


def test_closing_handler_returns_true_on_hide_failure(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing handler returns True (allow close) when hide() raises.

    pywebview's Event.set() swallows handler exceptions — a raise would be
    silently ignored and the cancel return value lost, destroying the window.
    Mitigation: we catch the exception and return True (deterministic close).
    """
    import the_one.interfaces.desktop.notice as notice_mod
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()
    mock_window.hide.side_effect = RuntimeError("hide failed")

    # Pre-mark notice as shown.
    marker = tmp_path / ".close_to_tray_notice_shown"
    monkeypatch.setattr(notice_mod, "_marker_path", lambda: marker)
    marker.touch()

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert len(closing_event.registered) == 1

    # hide() will raise — handler must catch it and return True.
    result = closing_event.fire()
    assert result is True


# ── shell.py: first-run notice ────────────────────────────────────────────────


def test_first_run_notice_shown_once_then_silent(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First close-to-tray calls notify; subsequent closes are silent."""
    import the_one.interfaces.desktop.notice as notice_mod
    import the_one.interfaces.desktop.tray as tray_mod

    marker = tmp_path / ".close_to_tray_notice_shown"
    monkeypatch.setattr(notice_mod, "_marker_path", lambda: marker)

    mock_window, closing_event = _make_mock_window()
    mock_icon = MagicMock()
    monkeypatch.setattr(tray_mod, "build_tray", lambda **kw: mock_icon)

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert len(closing_event.registered) == 1

    # First close — notify should be called once.
    closing_event.fire()
    mock_icon.notify.assert_called_once()
    assert marker.exists(), "Marker file must be created after first close"

    # Second close — notify should NOT be called again.
    mock_window.hide.reset_mock()
    closing_event.fire()
    mock_icon.notify.assert_called_once()  # still only once total


def test_first_run_notice_notify_arg_order(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """notify() is called as notify(icon, message, title) — correct arg order."""
    import the_one.interfaces.desktop.notice as notice_mod
    import the_one.interfaces.desktop.tray as tray_mod

    marker = tmp_path / ".close_to_tray_notice_shown"
    monkeypatch.setattr(notice_mod, "_marker_path", lambda: marker)

    mock_window, closing_event = _make_mock_window()
    mock_icon = MagicMock()
    captured_notify_calls: list = []

    def _fake_notify(icon, message, title):
        captured_notify_calls.append((icon, message, title))

    monkeypatch.setattr(tray_mod, "build_tray", lambda **kw: mock_icon)
    monkeypatch.setattr(tray_mod, "notify", _fake_notify)

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        mock_window=mock_window, closing_event=closing_event,
    )

    closing_event.fire()

    assert len(captured_notify_calls) == 1
    captured_icon, captured_message, captured_title = captured_notify_calls[0]
    assert captured_icon is mock_icon
    assert "system tray" in captured_message.lower()
    assert "GleepGlorp" in captured_title


# ── shell.py: Quit teardown ───────────────────────────────────────────────────


def test_quit_sets_really_quit_stops_icon_destroys_window(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quit callback: sets _really_quit, stops icon, destroys window — in order."""
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()
    captured_on_quit = None

    def _fake_build_tray(*, on_show, on_quit):
        nonlocal captured_on_quit
        captured_on_quit = on_quit
        return MagicMock()

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        fake_build_tray=_fake_build_tray,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert captured_on_quit is not None

    mock_icon = MagicMock()
    call_order: list[str] = []

    def _icon_stop():
        call_order.append("stop")

    def _window_destroy():
        call_order.append("destroy")

    mock_icon.stop.side_effect = _icon_stop
    mock_window.destroy.side_effect = _window_destroy

    captured_on_quit(mock_icon)

    assert shell_module._really_quit is True
    mock_icon.stop.assert_called_once()
    mock_window.destroy.assert_called_once()
    assert call_order == ["stop", "destroy"], (
        "icon.stop() must precede window.destroy() so the non-daemon thread exits first"
    )


def test_quit_icon_stop_raises_but_destroy_still_called(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if icon.stop() raises, window.destroy() is still called."""
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()
    captured_on_quit = None

    def _fake_build_tray(*, on_show, on_quit):
        nonlocal captured_on_quit
        captured_on_quit = on_quit
        return MagicMock()

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        fake_build_tray=_fake_build_tray,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert captured_on_quit is not None
    mock_icon = MagicMock()
    mock_icon.stop.side_effect = RuntimeError("stop raised")

    # stop() raises — destroy() must still be called.
    captured_on_quit(mock_icon)

    mock_window.destroy.assert_called_once()


def test_quit_stop_called_even_when_destroy_raises(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """icon.stop() is called even when window.destroy() raises.

    run_detached() spawns a non-daemon thread.  If stop() is not called before
    destroy() raises, the non-daemon thread is left alive and the process never
    exits.  stop() must run before destroy() in all cases.

    Note: the guard in the implementation is around stop() (try/except), and
    stop() is called *before* destroy() — this test verifies stop() was called
    before the exception from destroy() propagates up through on_quit.
    """
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()
    mock_window.destroy.side_effect = RuntimeError("destroy failed")
    captured_on_quit = None

    def _fake_build_tray(*, on_show, on_quit):
        nonlocal captured_on_quit
        captured_on_quit = on_quit
        return MagicMock()

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        fake_build_tray=_fake_build_tray,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert captured_on_quit is not None
    mock_icon = MagicMock()

    # destroy() raises — the exception propagates (expected) but stop() must
    # have been called first (the whole point: stop cannot be skipped).
    with pytest.raises(RuntimeError, match="destroy failed"):
        captured_on_quit(mock_icon)

    mock_icon.stop.assert_called_once()


# ── shell.py: tray-unavailable degrade ───────────────────────────────────────


def test_tray_failure_no_closing_handler_registered(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If tray construction raises, no closing handler is registered.

    The window's X then uses pywebview's default destroy — F4 fallback.
    The app must NOT crash.
    """
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()

    # Make build_tray raise — simulating "no tray backend".
    monkeypatch.setattr(tray_mod, "build_tray", MagicMock(side_effect=RuntimeError("no backend")))

    monkeypatch.setattr(shell_module.settings, "data_dir", tmp_path)
    webview_mock.create_window.return_value = mock_window

    with patch.object(shell_module, "_select_port", return_value=(8484, False)):
        with patch.object(shell_module, "_webview_available", return_value=True):
            with patch.object(shell_module, "_graceful_shutdown"):
                with patch.object(shell_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server") as _mock_srv_cls:
                            _mock_srv_cls.return_value = MagicMock()
                            with patch("threading.Thread") as _mock_thread_cls:
                                _mock_thread_cls.return_value = MagicMock()
                                # Must not raise.
                                shell_module.run_desktop()

    assert len(closing_event.registered) == 0, (
        "closing handler must NOT be registered when tray construction fails"
    )


def test_show_callback_calls_window_show_and_restore(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Show tray-menu callback calls window.show() and window.restore()."""
    import the_one.interfaces.desktop.tray as tray_mod

    mock_window, closing_event = _make_mock_window()
    captured_on_show = None

    def _fake_build_tray(*, on_show, on_quit):
        nonlocal captured_on_show
        captured_on_show = on_show
        return MagicMock()

    _run_desktop_with_tray(
        shell_module, webview_mock, tray_mod, monkeypatch, tmp_path,
        fake_build_tray=_fake_build_tray,
        mock_window=mock_window, closing_event=closing_event,
    )

    assert captured_on_show is not None
    mock_icon = MagicMock()
    captured_on_show(mock_icon)

    mock_window.show.assert_called_once()
    mock_window.restore.assert_called_once()
