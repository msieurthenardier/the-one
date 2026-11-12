"""Guard: nothing in ``the_one/`` uses what removing pywebview's native bridge breaks.

Since Mission 35 Flight 2 leg 8 (DD13) the desktop shell removes pywebview's native
message handlers (``jsBridge``, and ``browserDelegate`` on Cocoa) from the main
window so a sandboxed widget frame cannot reach them. Everything that travels over
those handlers stops working: ``js_api`` / ``expose`` calls, ``evaluate_js`` with a
callback, ``window.dom`` events (and easy-drag), and ``window.alert`` on GTK. This
test fails on any new use, so the next person learns why before it silently breaks.

Python is scanned with ``ast`` (comments and strings ignored); the static JS and the
inline scripts of ``index.html`` with comments stripped. No ``.md`` is scanned.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests import _source_scan

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "the_one"
STATIC = PKG / "interfaces" / "web" / "static"

WHY = (
    "pywebview's native message handlers are removed from the desktop main window so a "
    "widget frame cannot reach them (Mission 35 F2 L8, DD13); {what} would stop working "
    "there. See SECURITY-MODEL.md 'Live visuals'."
)

_JS_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_JS_LINE = re.compile(r"(?<![:\w'\"`\\])//[^\n]*")
_JS_PATTERNS = {
    "window.pywebview.api": re.compile(r"window\.pywebview\.api\b"),
    "window.dom": re.compile(r"(?<![\w$])window\.dom\b"),
    "alert(": re.compile(r"(?<![\w.$])alert\("),
    "print(": re.compile(r"(?<![\w.$])print\("),
}
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


def strip_js_comments(src: str) -> str:
    return _JS_LINE.sub("", _JS_BLOCK.sub("", src))


def python_violations(source: str, label: str = "") -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        where = f"{label}:{node.lineno}"
        if any(kw.arg == "js_api" for kw in node.keywords):
            found.append(f"{where} js_api= keyword")
        if name == "expose" and isinstance(func, ast.Attribute):
            found.append(f"{where} .expose(")
        if name == "evaluate_js" and (
            len(node.args) > 1 or any(kw.arg == "callback" for kw in node.keywords)
        ):
            found.append(f"{where} evaluate_js with a callback")
    return found


def js_violations(src: str, label: str = "") -> list[str]:
    clean = strip_js_comments(src)
    return [f"{label}: {what}" for what, pattern in _JS_PATTERNS.items() if pattern.search(clean)]


def test_no_python_use_of_the_removed_bridge():
    hits: list[str] = []
    for path in _source_scan.py_files(PKG):
        hits += python_violations(_source_scan.text(path), str(path.relative_to(REPO)))
    assert not hits, WHY.format(what="; ".join(hits))


def test_no_static_js_use_of_the_removed_bridge():
    hits: list[str] = []
    for path in _source_scan.static_js_files(STATIC / "js"):
        hits += js_violations(_source_scan.text(path), str(path.relative_to(REPO)))
    index = _source_scan.text(STATIC / "index.html")
    for body in _INLINE_SCRIPT.findall(index):
        hits += js_violations(body, "index.html (inline script)")
    assert not hits, WHY.format(what="; ".join(hits))


# -- the scanners themselves (so a pass is not vacuous) ---------------------------


def test_python_scanner_catches_each_form_and_ignores_comments():
    src = (
        "import webview\n"
        "# window.evaluate_js('x', cb)\n"
        "webview.create_window('t', 'u', js_api=Api())\n"
        "w.expose(f)\n"
        "w.evaluate_js('x', cb)\n"
        "w.evaluate_js('x', callback=cb)\n"
        "w.evaluate_js('x')\n"
    )
    hits = python_violations(src, "f.py")
    assert len(hits) == 4
    assert not python_violations("# js_api=1\nw.evaluate_js('x')\ns = 'w.expose(f)'\n")


def test_js_scanner_catches_each_form_and_ignores_comments_and_lookalikes():
    for bad in (
        "window.pywebview.api.go()",
        "window.dom.foo",
        "alert('x')",
        "print()",
        "x = 1; alert(2)",
    ):
        assert js_violations(bad), bad
    for ok in (
        "// alert('x')",
        "/* window.dom */ var a = 1;",
        "App.ui.alert(1)",
        "myalert(1)",
        "obj.print()",
        "var u = 'http://x'; // window.pywebview.api",
        "window.pywebview && window.pywebview.state",
    ):
        assert not js_violations(ok), ok
