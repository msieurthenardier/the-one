"""The F6 L5 shared tools-form-helpers module is gone (M31 F5 L06, DD11).

Its last consumer, the MCP editor's string-built chip lists, moved onto ``App.ui.chipList``.
"""

from __future__ import annotations

from pathlib import Path

import the_one.interfaces.web.app as web_app

# Resolve the prod static dir from the package source — independent of CWD.
_STATIC_DIR = Path(web_app.__file__).parent / "static"


class TestToolsFormHelpersGone:
    def test_file_is_gone(self) -> None:
        assert not (_STATIC_DIR / "js" / "areas" / "admin" / "tools-form-helpers.js").exists()

    def test_index_does_not_reference_it(self) -> None:
        index = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "tools-form-helpers" not in index
        assert "adminFormHelpers" not in index

    def test_no_script_uses_the_helper_namespace(self) -> None:
        for path in (_STATIC_DIR / "js").rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            assert "adminFormHelpers" not in text, path
            assert "renderChipListEditor" not in text, path
