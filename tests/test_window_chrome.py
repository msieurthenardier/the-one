# ruff: noqa: N802  (fakes mirror .NET member names)
"""Units for the_one.interfaces.desktop.chrome (M25 F5 L2). No Windows calls:
every GUI/Win32 seam is injected or monkeypatched."""

from __future__ import annotations

import json
import logging
import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from the_one.interfaces.desktop import chrome

# ── palette pin ──────────────────────────────────────────────────────────────

_TOKEN_FOR = {
    "caption": "--surface",
    "text": "--fg",
    "text_inactive": "--fg-muted",
    "border": "--border",
    "bg": "--bg",
    "fg_secondary": "--fg-secondary",
}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_palette_equals_tokens_css(theme: str) -> None:
    from tests._ui_guard_helpers import normalize_css_color, parse_tokens_css_theme_blocks

    tokens = parse_tokens_css_theme_blocks()[theme]
    for key, token in _TOKEN_FOR.items():
        assert normalize_css_color(chrome.PALETTE[theme][key]) == normalize_css_color(
            tokens[token]
        ), f"{theme}.{key} drifted from {token}"
    assert set(chrome.PALETTE[theme]) == set(_TOKEN_FOR)


# ── pure functions ───────────────────────────────────────────────────────────


def test_colorref_is_bgr() -> None:
    assert chrome.colorref("#17181c") == 0x001C1817
    assert chrome.colorref("#ffffff") == 0x00FFFFFF
    assert chrome.colorref("#ff0000") == 0x000000FF


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("active", [True, False])
def test_attribute_plan_modern_build(theme: str, active: bool) -> None:
    plan = chrome.attribute_plan(theme, active, 26100)
    assert [(n, a) for n, a, _ in plan] == [
        ("dark_mode", 20),
        ("border", 34),
        ("caption", 35),
        ("text", 36),
    ]
    values = {n: v for n, _, v in plan}
    pal = chrome.PALETTE[theme]
    assert values["dark_mode"] == (1 if theme == "dark" else 0)
    assert values["border"] == chrome.colorref(pal["border"])
    assert values["caption"] == chrome.colorref(pal["caption"])
    assert values["text"] == chrome.colorref(pal["text" if active else "text_inactive"])
    assert [a for _, a, _ in plan].count(36) == 1


def test_attribute_plan_old_build_dark_mode_only() -> None:
    assert chrome.attribute_plan("dark", True, 19045) == [("dark_mode", 20, 1)]
    assert chrome.attribute_plan("light", False, 21999) == [("dark_mode", 20, 0)]


def test_attribute_plan_none_build_is_empty() -> None:
    assert chrome.attribute_plan("dark", True, None) == []


def test_windows_build_off_windows_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "getwindowsversion", raising=False)
    assert chrome.windows_build() is None


def test_windows_build_reads_platform_version(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.SimpleNamespace(platform_version=(10, 0, 26100))
    monkeypatch.setattr(sys, "getwindowsversion", lambda: fake, raising=False)
    assert chrome.windows_build() == 26100


def test_os_theme_without_winreg_is_dark(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "winreg", None)  # import raises ImportError
    assert chrome.os_theme() == "dark"


@pytest.mark.parametrize("value,expected", [(1, "light"), (0, "dark")])
def test_os_theme_reads_apps_use_light_theme(
    monkeypatch: pytest.MonkeyPatch, value: int, expected: str
) -> None:
    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=lambda root, path: "key",
        QueryValueEx=lambda key, name: (value, 4),
        CloseKey=lambda key: None,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert chrome.os_theme() == expected


def test_os_theme_unreadable_value_is_dark(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any) -> Any:
        raise OSError("no key")

    fake = types.SimpleNamespace(HKEY_CURRENT_USER=object(), OpenKey=boom)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert chrome.os_theme() == "dark"


def _debug_records(caplog: pytest.LogCaptureFixture, needle: str) -> list[Any]:
    return [
        r
        for r in caplog.records
        if r.name == chrome.log.name and r.levelno == logging.DEBUG and needle in r.getMessage()
    ]


def test_os_theme_failure_is_logged_at_debug_with_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_a: Any) -> Any:
        raise OSError("no key")

    fake = types.SimpleNamespace(HKEY_CURRENT_USER=object(), OpenKey=boom)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    caplog.set_level(logging.DEBUG, logger=chrome.log.name)
    assert chrome.os_theme() == "dark"
    recs = _debug_records(caplog, "OS theme detection failed")
    assert len(recs) == 1
    assert recs[0].exc_info and isinstance(recs[0].exc_info[1], OSError)


def test_os_theme_close_key_failure_is_logged_and_value_kept(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def bad_close(_k: Any) -> None:
        raise OSError("close failed")

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=lambda root, path: "key",
        QueryValueEx=lambda key, name: (1, 4),
        CloseKey=bad_close,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    caplog.set_level(logging.DEBUG, logger=chrome.log.name)
    assert chrome.os_theme() == "light"
    recs = _debug_records(caplog, "CloseKey failed")
    assert len(recs) == 1 and recs[0].exc_info


# ── persistence ──────────────────────────────────────────────────────────────


def test_save_load_round_trip(tmp_path: Path) -> None:
    chrome.save_theme(tmp_path, "light")
    assert json.loads((tmp_path / "window-chrome.json").read_text()) == {"theme": "light"}
    assert chrome.load_theme(tmp_path) == "light"
    chrome.save_theme(tmp_path, "dark")
    assert chrome.load_theme(tmp_path) == "dark"


def test_load_missing_corrupt_invalid(tmp_path: Path) -> None:
    assert chrome.load_theme(tmp_path) is None
    f = tmp_path / "window-chrome.json"
    f.write_text("{not json")
    assert chrome.load_theme(tmp_path) is None
    f.write_text(json.dumps({"theme": "blue"}))
    assert chrome.load_theme(tmp_path) is None
    f.write_text(json.dumps(["dark"]))
    assert chrome.load_theme(tmp_path) is None


def test_save_is_atomic_no_partial_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chrome.save_theme(tmp_path, "dark")

    def boom(*_a: Any) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(chrome.os, "replace", boom)
    with pytest.raises(OSError):
        chrome.save_theme(tmp_path, "light")
    # The old file is intact and no temp file is left behind.
    assert chrome.load_theme(tmp_path) == "dark"
    assert [p.name for p in tmp_path.iterdir()] == ["window-chrome.json"]


# ── state, fakes ─────────────────────────────────────────────────────────────


class FakeForm:
    def __init__(self) -> None:
        self.IsDisposed = False
        self.IsHandleCreated = True


class FakeWindow:
    def __init__(self) -> None:
        self.native = FakeForm()


@pytest.fixture()
def win(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Windows-mode chrome with every seam faked. Records DWM calls."""
    calls: list[tuple[int, int, int]] = []
    monkeypatch.setattr(chrome, "_native_enabled", lambda: True)
    monkeypatch.setattr(chrome, "windows_build", lambda: 26100)
    monkeypatch.setattr(chrome, "_hwnd_of", lambda form: 0xABC)
    monkeypatch.setattr(chrome, "_dwm_set", lambda h, a, v: (calls.append((h, a, v)), 0)[1])
    handlers: dict[str, Any] = {}
    monkeypatch.setattr(
        chrome,
        "_subscribe_activation",
        lambda form, a, d: handlers.update(activated=a, deactivate=d),
    )

    def sync_invoke(form: Any, fn: Any) -> str:
        fn()
        return "done"

    monkeypatch.setattr(chrome, "_invoke_ui", sync_invoke)
    ns = types.SimpleNamespace(calls=calls, handlers=handlers, window=FakeWindow())
    return ns


def _text_value(calls: list[tuple[int, int, int]]) -> int:
    return [v for _, a, v in calls if a == 36][-1]


def test_request_before_enable_is_not_persisted(tmp_path: Path) -> None:
    out = chrome.request("dark")
    assert out == {"theme": "dark", "desktop": False, "tinted": False}
    assert chrome.snapshot()["requested"] == "dark"
    assert list(tmp_path.iterdir()) == []


def test_request_after_enable_persists_only_on_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome.enable(tmp_path)
    writes: list[str] = []
    real = chrome.save_theme
    monkeypatch.setattr(chrome, "save_theme", lambda d, t: (writes.append(t), real(d, t))[1])
    assert chrome.request("light")["desktop"] is True
    assert chrome.load_theme(tmp_path) == "light"
    chrome.request("light")
    chrome.request("dark")
    assert writes == ["light", "dark"]


def test_request_unwritable_file_is_logged_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome.enable(tmp_path)

    def boom(*_a: Any) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(chrome, "save_theme", boom)
    assert chrome.request("dark")["theme"] == "dark"


def test_lock_is_not_held_during_save_theme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome.enable(tmp_path)
    seen: list[bool] = []

    def fake_save(_d: Any, _t: str) -> None:
        seen.append(chrome._lock.locked())

    monkeypatch.setattr(chrome, "save_theme", fake_save)
    chrome.request("light")
    assert seen == [False]
    chrome.request("light")
    assert seen == [False]


def test_interleaved_requests_persist_the_latest_theme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome.enable(tmp_path)
    real = chrome.save_theme
    first_in = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def slow_save(d: Any, t: str) -> None:
        calls.append(t)
        if len(calls) == 1:
            first_in.set()
            assert release.wait(5)
        real(d, t)

    monkeypatch.setattr(chrome, "save_theme", slow_save)
    t1 = threading.Thread(target=chrome.request, args=("light",))
    t1.start()
    assert first_in.wait(5)
    t2 = threading.Thread(target=chrome.request, args=("dark",))
    t2.start()
    release.set()
    t1.join(5)
    t2.join(5)
    assert not t1.is_alive() and not t2.is_alive()
    assert chrome.load_theme(tmp_path) == "dark"
    assert chrome.snapshot()["requested"] == "dark"


def test_enable_reads_persisted_theme(tmp_path: Path, win: Any) -> None:
    chrome.save_theme(tmp_path, "dark")
    chrome.enable(tmp_path)
    writes: list[str] = []
    real = chrome.save_theme
    win.calls.clear()
    chrome.save_theme = lambda d, t: (writes.append(t), real(d, t))[1]  # type: ignore[assignment]
    try:
        chrome.request("dark")
    finally:
        chrome.save_theme = real  # type: ignore[assignment]
    assert writes == []  # equals the persisted value: no write


def test_post_before_registration_is_applied_at_registration(win: Any) -> None:
    out = chrome.request("dark")
    assert out["tinted"] is False and win.calls == []
    assert chrome.register(win.window, "light") is True
    # The requested theme beat the launch theme.
    assert [v for _, a, v in win.calls if a == 35] == [chrome.colorref("#17181c")]
    assert chrome.snapshot()["last_applied"]["theme"] == "dark"


def test_register_without_request_uses_launch_theme(win: Any) -> None:
    chrome.register(win.window, "light")
    assert [v for _, a, v in win.calls if a == 35] == [chrome.colorref("#fafafa")]
    assert [v for _, a, v in win.calls if a == 20] == [0]


def test_request_after_register_applies_with_active_state(win: Any) -> None:
    chrome.register(win.window, "light")
    win.calls.clear()
    out = chrome.request("dark")
    assert out["tinted"] is True
    assert _text_value(win.calls) == chrome.colorref("#ededf0")


def test_theme_change_while_inactive_uses_text_inactive(win: Any) -> None:
    chrome.register(win.window, "light")
    win.handlers["deactivate"](object(), object())
    win.calls.clear()
    chrome.request("dark")
    assert _text_value(win.calls) == chrome.colorref("#85878f")
    win.handlers["activated"](object(), object())
    assert _text_value(win.calls) == chrome.colorref("#ededf0")
    assert chrome.snapshot()["active"] is True


def test_activation_handlers_never_raise(win: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    chrome.register(win.window, "light")

    def boom(*_a: Any) -> Any:
        raise RuntimeError("dwm")

    monkeypatch.setattr(chrome, "_dwm_set", boom)
    win.handlers["deactivate"]()
    win.handlers["activated"](1, 2)


def test_lock_is_free_during_the_ui_invoke(win: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []

    def invoke(form: Any, fn: Any) -> str:
        seen.append(chrome._lock.locked())
        fn()
        return "done"

    monkeypatch.setattr(chrome, "_invoke_ui", invoke)
    chrome.register(win.window, "light")
    chrome.request("dark")
    assert seen == [False, False]


@pytest.mark.parametrize("order", [("light", "dark"), ("dark", "light")])
def test_racing_requests_leave_latest_applied(
    win: Any, monkeypatch: pytest.MonkeyPatch, order: tuple[str, str]
) -> None:
    chrome.register(win.window, "light")
    win.calls.clear()
    queued: list[Any] = []

    def deferred(form: Any, fn: Any) -> str:
        queued.append(fn)
        return "pending"

    monkeypatch.setattr(chrome, "_invoke_ui", deferred)
    # Both requests are recorded before either UI-thread function runs.
    chrome.request(order[0])
    chrome.request(order[1])
    for fn in queued:
        fn()
    assert chrome.snapshot()["last_applied"]["theme"] == order[1]
    assert chrome.snapshot()["pending"] is False


def test_reset_clears_everything(win: Any, tmp_path: Path) -> None:
    chrome.enable(tmp_path)
    chrome.register(win.window, "dark")
    chrome.request("light")
    chrome.deregister()
    chrome.reset()
    snap = chrome.snapshot()
    assert snap["enabled"] is False and snap["registered"] is False
    assert snap["requested"] is None and snap["last_applied"] is None
    assert snap["active"] is True and snap["pending"] is False
    assert chrome._s.closing is False and chrome._s.req_seq == 0


def test_deregister_stops_applies_and_is_idempotent(win: Any) -> None:
    chrome.register(win.window, "light")
    win.calls.clear()
    chrome.deregister()
    chrome.deregister()
    out = chrome.request("dark")
    assert out["tinted"] is False
    assert win.calls == []


# ── the BeginInvoke path ─────────────────────────────────────────────────────


def _fake_system(monkeypatch: pytest.MonkeyPatch) -> None:
    sysmod = types.ModuleType("System")

    class _Func:
        def __class_getitem__(cls, _t: Any) -> Any:
            return lambda fn: fn

    sysmod.Func = _Func  # type: ignore[attr-defined]
    sysmod.Type = object  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "System", sysmod)


def test_invoke_that_raises_is_a_logged_skip(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _fake_system(monkeypatch)

    class Form:
        InvokeRequired = True

        def BeginInvoke(self, _d: Any) -> Any:
            raise RuntimeError("handle gone")

    with caplog.at_level("WARNING"):
        assert chrome._invoke_ui(Form(), lambda: None) == "error"
    assert "BeginInvoke failed" in caplog.text


def test_invoke_never_completing_is_pending_within_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_system(monkeypatch)
    monkeypatch.setattr(chrome, "_UI_WAIT_MS", 50)
    waits: list[int] = []

    class Handle:
        def WaitOne(self, ms: int) -> bool:
            waits.append(ms)
            return False

    class Form:
        InvokeRequired = True
        ended = False

        def BeginInvoke(self, _d: Any) -> Any:
            return types.SimpleNamespace(AsyncWaitHandle=Handle())

        def EndInvoke(self, _ar: Any) -> None:
            Form.ended = True

    assert chrome._invoke_ui(Form(), lambda: None) == "pending"
    assert waits == [50] and Form.ended is False


def test_invoke_completed_calls_end_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_system(monkeypatch)
    ended: list[Any] = []

    class Form:
        InvokeRequired = True

        def BeginInvoke(self, d: Any) -> Any:
            d()
            h = types.SimpleNamespace(WaitOne=lambda ms: True)
            return types.SimpleNamespace(AsyncWaitHandle=h)

        def EndInvoke(self, ar: Any) -> None:
            ended.append(ar)

    ran: list[int] = []
    assert chrome._invoke_ui(Form(), lambda: ran.append(1)) == "done"
    assert ran == [1] and len(ended) == 1


def test_invoke_on_the_ui_thread_runs_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_system(monkeypatch)

    class Form:
        InvokeRequired = False

    ran: list[int] = []
    assert chrome._invoke_ui(Form(), lambda: ran.append(1)) == "done"
    assert ran == [1]


def test_timeout_reports_pending_and_snapshot_pending(
    win: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome.register(win.window, "light")
    queued: list[Any] = []
    monkeypatch.setattr(chrome, "_invoke_ui", lambda form, fn: (queued.append(fn), "pending")[1])
    out = chrome.request("dark")
    assert out["tinted"] == "pending"
    assert chrome.snapshot()["pending"] is True
    queued[0]()  # the UI thread gets to it
    assert chrome.snapshot()["pending"] is False
    assert chrome.snapshot()["last_applied"]["theme"] == "dark"


def test_closing_or_disposed_form_gives_no_invoke(
    win: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome.register(win.window, "light")
    calls: list[int] = []
    monkeypatch.setattr(chrome, "_invoke_ui", lambda f, fn: (calls.append(1), "done")[1])
    win.window.native.IsDisposed = True
    assert chrome.request("dark")["tinted"] is False
    win.window.native.IsDisposed = False
    chrome.deregister()
    assert chrome.request("light")["tinted"] is False
    assert calls == []


def test_win32_exception_in_the_ui_function_is_recorded(
    win: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    chrome.register(win.window, "light")

    def boom(*_a: Any) -> Any:
        raise RuntimeError("win32 exploded")

    monkeypatch.setattr(chrome, "_hwnd_of", boom)
    with caplog.at_level("WARNING"):
        out = chrome.request("dark")
    assert out["tinted"] is False
    la = chrome.snapshot()["last_applied"]
    assert "win32 exploded" in la["error"]
    assert "apply raised" in caplog.text


def test_non_zero_hresult_is_not_tinted(win: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    chrome.register(win.window, "light")
    monkeypatch.setattr(chrome, "_dwm_set", lambda h, a, v: -2147024809 if a == 35 else 0)
    assert chrome.request("dark")["tinted"] is False
    assert chrome.snapshot()["last_applied"]["results"]["caption"] == -2147024809


def test_register_off_windows_never_touches_native() -> None:
    class Boom:
        @property
        def native(self) -> Any:
            raise AssertionError("native read off Windows")

    assert chrome.register(Boom(), "dark") is False
    assert chrome.request("light") == {"theme": "light", "desktop": False, "tinted": False}


def test_snapshot_shape(win: Any) -> None:
    chrome.register(win.window, "light")
    snap = chrome.snapshot()
    assert set(snap) == {
        "enabled",
        "registered",
        "requested",
        "launch_theme",
        "persisted",
        "active",
        "build",
        "supported",
        "pending",
        "last_applied",
    }
    assert snap["build"] == 26100 and snap["supported"] is True
    assert set(snap["last_applied"]) == {
        "theme",
        "active",
        "results",
        "error",
        "queued_at",
        "applied_at",
    }


def test_apply_splash_border_sets_only_the_border(
    win: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Handle:
        def ToInt64(self) -> int:
            return 77

    w = types.SimpleNamespace(native=types.SimpleNamespace(Handle=Handle()))
    chrome.apply_splash_border(w, "dark")
    assert win.calls == [(77, 34, chrome.colorref("#26272c"))]


def test_apply_splash_border_never_raises(win: Any) -> None:
    chrome.apply_splash_border(object(), "dark")  # no .native


def test_native_show_raises_when_it_cannot_complete(
    win: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chrome, "_invoke_ui", lambda f, fn: "pending")
    with pytest.raises(RuntimeError):
        chrome.native_show(win.window)


def test_native_show_runs_show_then_activate(win: Any) -> None:
    order: list[str] = []
    form = types.SimpleNamespace(
        Show=lambda: order.append("Show"), Activate=lambda: order.append("Activate")
    )
    chrome.native_show(types.SimpleNamespace(native=form))
    assert order == ["Show", "Activate"]


def test_threads_requesting_concurrently_do_not_deadlock(win: Any) -> None:
    chrome.register(win.window, "light")
    threads = [
        threading.Thread(target=chrome.request, args=("dark" if i % 2 else "light",))
        for i in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in threads)
    assert chrome.snapshot()["pending"] is False
