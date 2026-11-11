"""Canary for the pywebview 5.4 GTK facts the native-bridge removal relies on (M35 F2 L8, DD13).

Reads ``webview/platforms/gtk.py`` with ``ast`` and never imports it (the import needs
``gi``). A pywebview bump that renames the handler or the ``manager`` attribute fails
here, not as a silent ``"failed"`` in ``GET /api/window/state``.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from the_one.interfaces.desktop import native_bridge


@pytest.fixture(scope="module")
def gtk_tree() -> ast.Module:
    spec = importlib.util.find_spec("webview")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("pywebview is not installed")
    path = Path(next(iter(spec.submodule_search_locations))) / "platforms" / "gtk.py"
    assert path.is_file(), f"{path} missing"
    return ast.parse(path.read_text(encoding="utf-8"))


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _init(tree: ast.Module) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BrowserView":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    return item
    raise AssertionError("BrowserView.__init__ not found")


def test_browser_view_init_registers_the_js_bridge_handler(gtk_tree):
    names = {
        n.args[0].value
        for n in ast.walk(_init(gtk_tree))
        if isinstance(n, ast.Call)
        and _dotted(n.func) == "self.manager.register_script_message_handler"
        and n.args
        and isinstance(n.args[0], ast.Constant)
    }
    assert names == set(native_bridge.GTK_HANDLERS) == {"jsBridge"}


def test_browser_view_init_keeps_the_manager_and_instances_the_removal_reads(gtk_tree):
    init = _init(gtk_tree)
    assigns = [n for n in ast.walk(init) if isinstance(n, ast.Assign)]
    targets = {_dotted(t) for n in assigns for t in n.targets}
    assert "self.manager" in targets
    subscripted = {
        _dotted(t.value) for n in assigns for t in n.targets if isinstance(t, ast.Subscript)
    }
    assert "BrowserView.instances" in subscripted
