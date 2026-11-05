"""Squawk 0191: the Library section list has one source, LIBRARY_GROUPS."""

import re
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/js/areas/studio"
SECTIONS = ("providers", "knowledge", "mcp-sources", "connectors", "secrets")


def _lit(section: str) -> str:
    return rf"""(===|==)\s*['"]{re.escape(section)}['"]"""


def test_group_table_entries_have_sections():
    src = (STUDIO / "library-pane.js").read_text()
    table = src[src.index("var LIBRARY_GROUPS = [") : src.index("window.App.studio.libraryGroups")]
    assert table.count("{ id:") == 5
    assert len(re.findall(r"\bsection: '[a-z-]+'", table)) == 5


def test_is_library_section_derives_from_table():
    src = (STUDIO / "library-pane.js").read_text()
    body = src[src.index("function isLibrarySection") : src.index("function libraryGroupFor")]
    for section in SECTIONS:
        assert not re.search(_lit(section), body), section
    assert "libraryGroupFor(" in body


def test_studio_route_derives_root_list_from_table():
    src = (STUDIO / "studio-route.js").read_text()
    assert "App.studio.libraryGroups" in src
    for section in SECTIONS:
        assert not re.search(r"sub\s*" + _lit(section), src), section
