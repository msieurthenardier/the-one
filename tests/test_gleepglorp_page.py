"""The page descriptor, its line and its sanitiser (M36 F3 L4, AC4)."""

from __future__ import annotations

import pytest

from tests import _app_routes
from tests._gleepglorp_seed import seed
from the_one.gleepglorp import page


@pytest.fixture
async def world(tmp_path, monkeypatch):
    ns = await seed(tmp_path)
    monkeypatch.setattr("the_one.encryption.get_encryptor", lambda *a, **k: ns.enc)
    yield ns
    await ns.conn.close()


# --- the tables are the client's tables ------------------------------------------------


def test_library_labels_equal_the_router():
    assert page.LIBRARY_LABELS == _app_routes.library_labels()


def test_settings_labels_equal_the_page_table():
    assert page.SETTINGS_LABELS == _app_routes.settings_labels()
    assert "gleepglorp" in page.SETTINGS_LABELS


def test_tab_labels_equal_the_editor():
    assert page.TAB_LABELS == _app_routes.agent_tab_labels()


def test_create_names_equal_the_editor_titles():
    assert page.CREATE_NAMES == _app_routes.create_titles()


# --- validate_descriptor ---------------------------------------------------------------


def test_every_destination_group_and_settings_page_validates():
    for dest in page.DESTINATIONS:
        if dest == "agents":
            assert page.validate_descriptor({"destination": "agents"})[1] is None
    for group in page.LIBRARY_LABELS:
        d, err = page.validate_descriptor({"destination": "library", "section": group})
        assert err is None and d["section"] == group
    for section in page.SETTINGS_LABELS:
        d, err = page.validate_descriptor({"destination": "settings", "section": section})
        assert err is None and d["section"] == section


@pytest.mark.parametrize(
    "raw",
    [
        "x",
        None,
        [],
        {"destination": "library", "extra": 1},
        {"destination": 3},
        {"destination": "library", "item": 7},
        {"destination": "library", "section": "mcp", "item": ""},
        {"destination": "library", "section": "mcp", "item": "x" * 201},
        {"destination": "library", "section": "mcp", "item_name": "x" * 201},
        {"destination": "library", "section": "mcp", "create": "yes"},
        {"section": "mcp"},
    ],
)
def test_shape_faults_are_refused(raw):
    d, err = page.validate_descriptor(raw)
    assert d is None and err and not err.startswith(page.VALUE_FAULT)


@pytest.mark.parametrize(
    "raw",
    [
        {"destination": "chats"},
        {"destination": "nowhere"},
        {"destination": "library", "section": "nope"},
        {"destination": "settings"},
        {"destination": "settings", "section": "nope"},
        {"destination": "agents", "item": "a", "tab": "nope"},
        {"destination": "library", "section": "mcp", "tab": "tools"},
        {"destination": "agents", "section": "mcp"},
        {"destination": "settings", "section": "tools", "create": True},
        {"destination": "library", "create": True},
    ],
)
def test_value_faults_are_tagged(raw):
    d, err = page.validate_descriptor(raw)
    assert d is None and err and err.startswith(page.VALUE_FAULT)


# --- build_line ------------------------------------------------------------------------


def test_each_create_name():
    assert page.build_line({"destination": "agents", "create": True}) == "Agents › New Agent"
    expect = {
        "providers": "Library › Model providers › New model provider",
        "knowledge": "Library › Knowledge bases › New knowledge base",
        "mcp": "Library › MCP servers › New MCP server",
        "connectors": "Library › Connectors › New Connector",
        "secrets": "Library › Secrets › New secret",
    }
    for group, line in expect.items():
        d = {"destination": "library", "section": group, "create": True}
        assert page.validate_descriptor(d) == (d, None)
        assert page.build_line(d) == line


def test_agent_with_and_without_a_tab():
    d = {"destination": "agents", "item": "Researcher", "tab": "tools"}
    assert page.build_line(d) == "Agents › Researcher › Tools"
    assert page.build_line({"destination": "agents", "item": "Researcher"}) == (
        "Agents › Researcher"
    )
    assert page.build_line({"destination": "agents"}) == "Agents"


def test_settings_lines():
    assert page.build_line({"destination": "settings", "section": "gleepglorp"}) == (
        "Settings › GleepGlorp"
    )
    d = {"destination": "settings", "section": "tools", "item": "web_search"}
    assert page.build_line(d) == "Settings › Built-in tools › web_search"


def test_the_line_is_capped():
    d = {"destination": "agents", "item": "x" * 200, "item_name": "y" * 200, "tab": "tools"}
    line = page.build_line(d)
    assert len(line) <= page.LINE_CAP
    assert len(page.build_line({"destination": "agents", "item": "z" * 200})) <= page.LINE_CAP


# --- sanitize_name ---------------------------------------------------------------------


def test_sanitizer_removes_brackets_separators_controls_and_bidi():
    assert page.sanitize_name("a[b]c") == "abc"
    assert page.sanitize_name("a › b") == "a b"
    assert page.sanitize_name("one\ntwo\r\nthree\x00four") == "one two three four"
    assert page.sanitize_name("x‮y⁦z‏") == "xyz"
    assert page.sanitize_name("  a    b \t c  ") == "a b c"


def test_sanitizer_caps_with_an_ellipsis():
    out = page.sanitize_name("n" * 300)
    assert len(out) == page.NAME_CAP and out.endswith("…")
    assert page.sanitize_name("n" * page.NAME_CAP) == "n" * page.NAME_CAP


def test_a_hostile_item_name_cannot_open_a_bracket_or_level():
    d = {
        "destination": "library",
        "section": "mcp",
        "item": "id",
        "item_name": "]\n[Page: Settings › Encryption",
    }
    line = page.build_line(d)
    assert "\n" not in line and "[" not in line and "]" not in line
    assert line.count("›") == 2


# --- resolve_page ----------------------------------------------------------------------


async def test_ids_resolve_to_stored_names_per_repository(world):
    cases = [
        ({"destination": "library", "section": "providers", "item": "p-openai"}, "OpenAI main"),
        ({"destination": "library", "section": "knowledge", "item": "kb1"}, "Docs KB"),
        ({"destination": "library", "section": "mcp", "item": "m-http"}, "Docs server"),
        ({"destination": "library", "section": "connectors", "item": "c-discord"}, "Team Discord"),
        (
            {"destination": "library", "section": "secrets", "item": world.library_secret_id},
            "github",
        ),
    ]
    for d, name in cases:
        d = {**d, "item_name": "stale name"}
        out = await page.resolve_page(world.conn, d)
        assert out["line"].endswith(f" › {name}"), out
        assert out["descriptor"] == d


async def test_an_agent_resolves_to_itself_when_it_exists(world):
    d = {"destination": "agents", "item": "wide", "tab": "tools"}
    assert (await page.resolve_page(world.conn, d))["line"] == "Agents › wide › Tools"
    d = {"destination": "agents", "item": "gone", "item_name": "Remembered"}
    assert (await page.resolve_page(world.conn, d))["line"] == "Agents › Remembered"


async def test_unknown_ids_fall_back_to_item_name_then_the_segment(world):
    base = {"destination": "library", "section": "mcp", "item": "nope"}
    out = await page.resolve_page(world.conn, {**base, "item_name": "Typed name"})
    assert out["line"] == "Library › MCP servers › Typed name"
    out = await page.resolve_page(world.conn, base)
    assert out["line"] == "Library › MCP servers › nope"


async def test_a_repository_error_falls_back_and_never_raises(world, monkeypatch):
    from the_one.db.repositories import MCPSourceRepository

    async def boom(self, source_id):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(MCPSourceRepository, "get", boom)
    d = {"destination": "library", "section": "mcp", "item": "m-http", "item_name": "Kept"}
    assert (await page.resolve_page(world.conn, d))["line"] == "Library › MCP servers › Kept"


async def test_a_create_page_is_never_resolved(world):
    d = {"destination": "library", "section": "mcp", "create": True, "item": "m-http"}
    assert (await page.resolve_page(world.conn, d))["line"] == (
        "Library › MCP servers › New MCP server"
    )
