"""Canary for the pywebview 5.4 Cocoa facts macOS dock mode relies on (M32 F3 DD3/DD4).

Reads ``webview/platforms/cocoa.py`` with ``ast`` (present in every install, any OS)
and never imports it: that import calls ``NSApplication.sharedApplication()``. A
pywebview bump that changes any of these facts fails here, not on a contributor's Mac.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def cocoa_tree() -> ast.Module:
    spec = importlib.util.find_spec("webview")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("pywebview is not installed")
    path = Path(next(iter(spec.submodule_search_locations))) / "platforms" / "cocoa.py"
    assert path.is_file(), f"{path} missing"
    return ast.parse(path.read_text(encoding="utf-8"))


def _classes(node: ast.AST) -> dict[str, ast.ClassDef]:
    return {n.name: n for n in ast.walk(node) if isinstance(n, ast.ClassDef)}


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _calls(node: ast.AST) -> set[str]:
    return {_dotted(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}


def _browser_view(tree: ast.Module) -> ast.ClassDef:
    return _classes(tree)["BrowserView"]


def test_app_delegate_defines_terminate_but_not_reopen(cocoa_tree):
    methods = _methods(_classes(_browser_view(cocoa_tree))["AppDelegate"])
    assert "applicationShouldTerminate_" in methods
    assert "applicationShouldHandleReopen_hasVisibleWindows_" not in methods


def test_window_should_close_calls_should_close_which_fires_closing(cocoa_tree):
    classes = _classes(_browser_view(cocoa_tree))
    wsc = _methods(classes["WindowDelegate"])["windowShouldClose_"]
    assert "BrowserView.should_close" in _calls(wsc)
    should_close = _methods(_browser_view(cocoa_tree))["should_close"]
    assert any(c.endswith("events.closing.set") for c in _calls(should_close))


def test_window_will_close_stops_the_app_and_posts_no_event(cocoa_tree):
    wwc = _methods(_classes(_browser_view(cocoa_tree))["WindowDelegate"])["windowWillClose_"]
    calls = _calls(wwc)
    assert "BrowserView.app.stop_" in calls
    assert "BrowserView.app.abortModal" in calls
    assert not any("postEvent" in c or "otherEventWithType" in c for c in calls)


def test_keydown_q_branch_calls_app_stop(cocoa_tree):
    keydown = _methods(_classes(_browser_view(cocoa_tree))["WebKitHost"])["keyDown_"]
    found = False
    for node in ast.walk(keydown):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and any(isinstance(c, ast.Constant) and c.value == "q" for c in node.test.comparators)
        ):
            found = any(
                _dotted(c.func) == "BrowserView.app.stop_"
                for stmt in node.body
                for c in ast.walk(stmt)
                if isinstance(c, ast.Call)
            )
    assert found, "WebKitHost.keyDown_ no longer maps Cmd-Q to BrowserView.app.stop_"


def test_app_menu_binds_quit_to_terminate_with_key_q(cocoa_tree):
    menu = _methods(_browser_view(cocoa_tree))["_add_app_menu"]
    for node in ast.walk(menu):
        if isinstance(node, ast.Call) and _dotted(node.func).endswith(
            "addItemWithTitle_action_keyEquivalent_"
        ):
            consts = [a.value for a in node.args if isinstance(a, ast.Constant)]
            if consts[-2:] == ["terminate:", "q"]:
                return
    pytest.fail("_add_app_menu no longer binds terminate: to q")


def test_browser_view_init_allocates_the_app_delegate_class_attribute(cocoa_tree):
    init = _methods(_browser_view(cocoa_tree))["__init__"]
    assert "BrowserView.AppDelegate.alloc" in _calls(init)


def test_restore_calls_deminiaturize_directly(cocoa_tree):
    restore = _methods(_browser_view(cocoa_tree))["restore"]
    calls = _calls(restore)
    assert "self.window.deminiaturize_" in calls
    assert not any("callAfter" in c for c in calls)


def _handler_names(init: ast.FunctionDef, method: str) -> set[str]:
    """String names passed as the last argument to ``<...>.<method>(obj, name)``."""
    names: set[str] = set()
    for node in ast.walk(init):
        if isinstance(node, ast.Call) and _dotted(node.func).endswith(method):
            last = node.args[-1] if node.args else None
            if isinstance(last, ast.Constant) and isinstance(last.value, str):
                names.add(last.value)
    return names


def test_browser_view_init_registers_the_two_native_message_handlers(cocoa_tree):
    """The shell removes exactly these (native_bridge.COCOA_HANDLERS, M35 F2 L8 DD13)."""
    init = _methods(_browser_view(cocoa_tree))["__init__"]
    assert _handler_names(init, "addScriptMessageHandler_name_") == {"jsBridge", "browserDelegate"}


def test_browser_view_init_keeps_the_webview_attribute_the_removal_reads(cocoa_tree):
    init = _methods(_browser_view(cocoa_tree))["__init__"]
    targets = {_dotted(t) for n in ast.walk(init) if isinstance(n, ast.Assign) for t in n.targets}
    assert "self.webview" in targets
