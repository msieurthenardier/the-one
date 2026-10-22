"""The one built-in tool category table (M25 F4 L6, flight DD7, leg AC9).

``static/js/tool-categories.js`` (``App.toolCategories``) replaced three hand-kept
copies (``studio.js``'s per-agent Tools tab table and the two ``admin/tools-*.js``
maps), all of which had missed M23 F4 L3's ``find_platform_destination``. These
guards keep it complete against ``the_one/tools/builtins.py::_TOOL_CLASSES`` (a
new built-in cannot be silently uncategorised: it would show in no Settings tab
and no Tools-tab tile), keep the three consumers on the shared table, and keep
its script tag ahead of them.
"""

from __future__ import annotations

import re
from pathlib import Path

from the_one.tools.builtins import _TOOL_CLASSES

STATIC = Path(__file__).resolve().parent.parent / "the_one" / "interfaces" / "web" / "static"
JS = STATIC / "js"
TABLE_JS = JS / "tool-categories.js"
INDEX = STATIC / "index.html"

_ROW = re.compile(r"\{ id: '([a-z]+)', label: '([^']+)', tools: \[([^\]]*)\] \}")


def parse_table(text: str) -> list[tuple[str, str, list[str]]]:
    """``[(slug, label, [tool, ...]), ...]`` from the file's ``var TABLE = [...]``."""
    start = text.index("var TABLE = [")
    block = text[start : text.index("];", start)]
    rows = _ROW.findall(block)
    return [(slug, label, re.findall(r"'([a-z_]+)'", tools)) for slug, label, tools in rows]


def table_tools(rows: list[tuple[str, str, list[str]]]) -> list[str]:
    return [tool for _, _, tools in rows for tool in tools]


def test_table_lists_every_builtin_exactly_once() -> None:
    tools = table_tools(parse_table(TABLE_JS.read_text()))
    assert len(tools) == len(set(tools)), "a tool is in two categories"
    missing = sorted(set(_TOOL_CLASSES) - set(tools))
    stale = sorted(set(tools) - set(_TOOL_CLASSES))
    assert not missing, f"built-ins with no category in tool-categories.js: {missing}"
    assert not stale, f"tool-categories.js names tools that are not built-ins: {stale}"


def test_the_connector_lookup_tool_is_categorised() -> None:
    """M23 F4 L3's lookup tool, missing from all three former copies."""
    rows = {slug: tools for slug, _, tools in parse_table(TABLE_JS.read_text())}
    assert rows["connectors"] == [
        "send_to_platform_channel",
        "fetch_channel_history",
        "find_platform_destination",
    ]


def test_categories_and_labels_in_tab_order() -> None:
    rows = parse_table(TABLE_JS.read_text())
    assert [(slug, label) for slug, label, _ in rows] == [
        ("filesystem", "Filesystem"),
        ("execution", "Execution"),
        ("web", "Web"),
        ("connectors", "Connectors"),
        ("time", "Time"),
    ]


def test_whitelist_exempt_matches_the_server_constant() -> None:
    from the_one.agent.config import WHITELIST_EXEMPT_TOOLS

    m = re.search(r"var whitelistExempt = Object\.freeze\(\[([^\]]*)\]\)", TABLE_JS.read_text())
    assert m, "whitelistExempt not found in tool-categories.js"
    assert sorted(re.findall(r"'([a-z_]+)'", m.group(1))) == sorted(WHITELIST_EXEMPT_TOOLS)


def test_ungated_prefixes_match_the_server_constant() -> None:
    from the_one.agent.config import UNGATED_TOOL_PREFIXES

    m = re.search(r"var ungatedPrefixes = Object\.freeze\(\[([^\]]*)\]\)", TABLE_JS.read_text())
    assert m, "ungatedPrefixes not found in tool-categories.js"
    assert sorted(re.findall(r"'([a-z_]+)'", m.group(1))) == sorted(UNGATED_TOOL_PREFIXES)


def test_no_client_literal_copies_of_the_ungated_prefixes() -> None:
    # M31 F2 L03: the ungated-prefix read moved to agent-form-data.js and renderEditor to
    # agent-editor-controller.js; the literal-copy check covers both.
    for rel in (
        "areas/studio.js",
        "areas/studio/agent-form-data.js",
        "areas/studio/agent-editor-controller.js",
        "areas/chat/agent-drawer.js",
    ):
        assert "'mcp__', 'kb__'" not in (TABLE_JS.parent / rel).read_text(), rel


def test_the_guard_catches_a_missing_and_a_stale_tool() -> None:
    """Falsification of the completeness guard: a table missing a built-in, or
    naming a non-built-in, is caught (so a green run means a complete table)."""
    text = TABLE_JS.read_text()
    dropped = text.replace(", 'find_platform_destination'", "")
    assert dropped != text
    assert set(table_tools(parse_table(dropped))) != set(_TOOL_CLASSES)
    extra = text.replace("'web_search'", "'web_search', 'not_a_tool'")
    assert "not_a_tool" in set(table_tools(parse_table(extra))) - set(_TOOL_CLASSES)


def test_the_three_consumers_read_the_shared_table() -> None:
    for rel, shape in (
        # M31 F2 L03: renderEditor (its Tools-tab callback) moved to the controller.
        ("areas/studio/agent-editor-controller.js", "byCategory"),
        ("areas/admin/tools-grid.js", "categoryOf"),
        ("areas/admin/tools-editor.js", "categoryOf"),
    ):
        text = (JS / rel).read_text()
        assert f"App.toolCategories.{shape}" in text, rel
        # No local copy is left: neither shape's literal entries.
        assert "'Filesystem': [" not in text, rel
        assert not re.search(r"^\s*read_file:\s*'filesystem'", text, re.MULTILINE), rel
    grid = (JS / "areas/admin/tools-grid.js").read_text()
    assert "App.toolCategories.order" in grid and "App.toolCategories.labels" in grid


def test_the_table_loads_before_its_consumers() -> None:
    srcs = re.findall(r'<script src="/static/js/([^"]+)"></script>', INDEX.read_text())
    at = srcs.index("tool-categories.js")
    for consumer in (
        "areas/studio.js",
        # M31 F2 L03: the four editor modules load after the table, before studio.js.
        "areas/studio/agent-form-data.js",
        "areas/studio/agent-model-picker.js",
        "areas/studio/agent-editor-controller.js",
        "areas/studio/agents-list.js",
        "areas/admin/tools-grid.js",
        "areas/admin/tools-editor.js",
        "areas/chat/agent-drawer.js",
    ):
        assert at < srcs.index(consumer), consumer
