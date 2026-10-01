"""Static source rules for the ``App.ui`` control library (M25 F1 L2, DD1/DD4/DD5).

The sink-token and testid-value rules live in ``test_ui_guards.py``; these cover
the rest of the file-level code rules: ES5 only, strict-mode IIFE, no app
globals, and the export idiom.
"""

from __future__ import annotations

import re

import pytest

from tests._ui_guard_helpers import UI_DIR

UI_FILES = sorted(UI_DIR.glob("*.js"))

_ES6 = re.compile(r"=>|\bclass\s+\w|\blet\s|\bconst\s|`")
_APP_GLOBAL = re.compile(r"\bApp\.(?!ui\b|icons\b)\w+")
_NAMESPACE_LINES = {
    "window.App = window.App || {};",
    "App.ui = App.ui || {};",
    "App.ui.util = App.ui.util || {};",
}
_UI_ASSIGN = re.compile(r"^\s*App\.ui\.(?!util\b)(\w+)\s*=")
_FACTORY_LINE = re.compile(r"^  App\.ui\.(\w+) = function \(opts\) \{$")


def test_ui_dir_has_the_four_spike_files() -> None:
    assert {f.name for f in UI_FILES} >= {"core.js", "button.js", "field.js", "list-pane.js"}


@pytest.mark.parametrize("path", UI_FILES, ids=lambda p: p.name)
def test_file_is_es5_strict_iife(path) -> None:
    text = path.read_text()
    assert text.startswith("(function () {\n  'use strict';\n"), path.name
    assert text.rstrip().endswith("})();"), path.name
    assert "window.App = window.App || {};" in text, path.name
    for lineno, line in enumerate(text.splitlines(), start=1):
        code = line.split("//")[0]
        assert not _ES6.search(code), f"{path.name}:{lineno}: ES2015+ syntax: {line.strip()}"


@pytest.mark.parametrize("path", UI_FILES, ids=lambda p: p.name)
def test_file_touches_no_app_globals(path) -> None:
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        code = line.split("//")[0]
        assert not _APP_GLOBAL.search(code), f"{path.name}:{lineno}: app global: {line.strip()}"


@pytest.mark.parametrize("path", UI_FILES, ids=lambda p: p.name)
def test_export_idiom(path) -> None:
    """The only non-function assignments to ``App.ui`` are the namespace lines;
    every factory is exactly ``App.ui.<name> = function (opts) {``."""
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if line.strip() in _NAMESPACE_LINES:
            continue
        if _UI_ASSIGN.match(line):
            assert _FACTORY_LINE.match(line), f"{path.name}:{lineno}: bad export: {line.strip()}"
