# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""The Library list beside a detail pane (M25 F3 leg 4a, DD5/DD8).

Library is one grouped ``App.ui.listPane`` (Knowledge bases, MCP servers,
Connectors; testid ``library-list``) with an Add menu, beside the detail pane
that hosts the three editors. Covers:

* AC1 -- groups, A-Z order, icons, meta from ``App.usage`` (agent counts, MCP
  tool counts, connector ``default_agent`` + ``channel_map`` de-duplicated),
  group empty lines, no section nav; agent counts never read "0" while loading;
* AC2 -- the Add menu: each item opens its ``~new``; never clipped by the aside
  at 1440x900 or 1024x768 (``align: 'end'``, every item's inset corners);
* AC3 -- each editor beside the list (selected row), a dirty editor plus a row
  click asks once, delete replaces to the section root and moves focus (DD8),
  and the list follows create / rename / delete with no reload;
* AC4 -- knowledge-base create opens the new item (squawk 0101): the form,
  "Name is required." under Name, one POST, the replaced route, the selected row, the
  announced name and the folder field's focus; Cancel returns to the root;
* AC5 -- connector URLs: cold deep links, a dead id healing, save-create with no
  navigation and no hydrate, Cancel by mode;
* AC6 -- the empty detail state per section, the group scroll, no grid markup,
  and no empty-state flash on a cold item link;
* loading and failure: no "No ... yet." flash before data arrives, and a failed
  collection reads "Couldn't load {group}." (a last-good list stays).

Leg 4b (the editors' chrome, DD2/DD8):

* AC1 -- each editor's breadcrumb "Library / {Group}" (edit and ``~new``), the
  first child of ``.editor-header-text`` with one h1 and no Back; the
  knowledge-base breadcrumb survives a Save re-mount and the poll keeps running;
* AC2/AC5b -- the group link closes each type to its section root and focuses
  the item's row; a dirty editor asks once (Stay focuses the link); the
  knowledge-base ``~new`` form's link;
* AC3 -- the unsaved indicator on the three editors and the ``~new`` form;
* AC4 -- create opens the item for each type, with the preservation checks and
  no prompt on the next row click.

The flight's behavior-gate fix (list-and-detail L6): the MCP and connector
create forms' Cancel is enabled from first render, typed into or not, and
abandons creation (DD8: no dialog, a replace to the section root, focus on the
group's first row, else Add); on a clean open item it stays disabled.

Chromium only. Falls in the ``library`` lane (``library_pat`` in
``scripts/run-tests.sh``).
"""

from __future__ import annotations

import json
import re
import time as _time

import pytest
from browser import _lists, _nav
from browser.seeders import (
    SeededApp,
    seed_agent_with_attachments,
    seed_connector,
    seed_knowledge_base,
    seed_mcp_source,
)
from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.browser

LIST = '[data-testid="library-list"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
ANNOUNCER = '[data-testid="route-announcer"]'


def _rows(page: Page):
    return page.locator(f"{LIST} li:not([hidden]) > .ui-list-pane-row")


def _row_texts(page: Page) -> list[list[str]]:
    """[label, meta] per visible row, in list order."""
    return page.evaluate(
        """(sel) => Array.from(document.querySelectorAll(sel + ' li:not([hidden]) > .ui-list-pane-row'))
            .map((r) => [r.querySelector('.ui-list-pane-label').textContent,
                         (r.querySelector('.ui-list-pane-meta') || {textContent: ''}).textContent.trim()])""",
        LIST,
    )


def _focused_label(page: Page) -> str | None:
    return page.evaluate(
        "() => { const a = document.activeElement; const r = a && a.closest && a.closest('.ui-list-pane-row');"
        " return r ? r.querySelector('.ui-list-pane-label').textContent : (a && a.getAttribute('data-testid')); }"
    )


def _ready(page: Page, base: str, route: str) -> None:
    _nav.goto_settled(page, base, route)
    expect(page.locator(f"{LIST} .ui-list-pane-caption").first).to_be_visible(timeout=8000)


def _confirm_delete(page: Page, testid: str) -> None:
    btn = page.locator(f'[data-testid="{testid}"]')
    expect(btn).to_be_visible(timeout=8000)
    btn.click()
    expect(btn).to_have_class(re.compile(r"\bconfirm-delete\b"))
    btn.click()


class _Hold:
    """Hold matching requests until released (state, not timing)."""

    def __init__(self, page: Page, pattern: str, predicate=None) -> None:  # noqa: ANN001
        self.routes: list[Route] = []
        self.page = page
        self.released = False
        self.predicate = predicate or (lambda req: req.method == "GET")
        page.route(pattern, self._handle)

    def _handle(self, route: Route) -> None:
        if self.released or not self.predicate(route.request):
            route.continue_()
        else:
            self.routes.append(route)

    def wait_held(self, n: int = 1, timeout: float = 8000) -> None:
        left = timeout
        while len(self.routes) < n and left > 0:
            self.page.wait_for_timeout(50)
            left -= 50
        assert len(self.routes) >= n, "no request held"

    def release(self) -> None:
        self.released = True
        while self.routes:
            self.routes.pop(0).continue_()


def _seed_full(app: SeededApp) -> dict[str, str]:
    """2 knowledge bases, 2 MCP servers and 1 connector, with attachments:
    "Alpha KB" on two agents, "alpha-mcp" (3 cached tools) on one, and a
    connector whose default_agent repeats in its channel_map."""
    base = app.base_url
    kb_z = seed_knowledge_base(base, "Zeta KB")
    kb_a = seed_knowledge_base(base, "Alpha KB")
    mcp_z = seed_mcp_source(base, "zeta-mcp")
    mcp_a = seed_mcp_source(base, "alpha-mcp", tools=["read", "write", "list"])
    seed_agent_with_attachments(
        base, app.provider_id, "kb-user-1", kb_ids=[kb_a], mcp_source_ids=[mcp_a]
    )
    seed_agent_with_attachments(base, app.provider_id, "kb-user-2", kb_ids=[kb_a])
    conn = seed_connector(
        base,
        "Team chat",
        default_agent="kb-user-1",
        channel_map={"100": "kb-user-1", "200": "kb-user-2"},
    )
    return {"kb_a": kb_a, "kb_z": kb_z, "mcp_a": mcp_a, "mcp_z": mcp_z, "conn": conn}


# ── AC1: the list ───────────────────────────────────────────────────────────


def test_groups_order_sorting_icons_and_meta(app_with_agent: SeededApp, page: Page) -> None:
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library")
    lib = page.locator(LIST)
    expect(lib.locator(".ui-list-pane-title")).to_have_text("Library")
    expect(lib.locator(".ui-list-pane-intro")).to_have_text(
        "Things agents can use. Attach them from an agent’s Knowledge and MCPs tabs."
    )
    expect(lib.locator('[data-testid="library-add-btn"]')).to_have_text("Add")
    expect(lib.locator(".ui-list-pane-caption")).to_have_text(
        ["Model providers", "Knowledge bases", "MCP servers", "Connectors"]
    )
    # No filter and no count on the Library list.
    expect(lib.locator("input[type=search]")).to_have_count(0)
    expect(lib.locator(".ui-list-pane-total")).to_have_count(0)
    # The meta waits for the agents list; it then reads the seeded attachments.
    expect(_rows(page).nth(1).locator(".ui-list-pane-meta")).to_have_text("2 agents", timeout=8000)
    texts = _row_texts(page)
    # The first group is the seeded mock provider, with its type badge and the
    # count of the agents that use it (every seeded agent does).
    assert texts[0][0] == "mock" and re.fullmatch(r"\d+ agents?", texts[0][1]), texts
    assert texts[1:] == [
        ["Alpha KB", "2 agents"],
        ["Zeta KB", "0 agents"],
        ["alpha-mcp", "3 tools · 1 agent"],
        ["zeta-mcp", "Not connected · 0 agents"],
        ["Team chat", "2 agents"],  # default_agent and the channel_map duplicate count once
    ]
    # Rows are links to their item routes, with the kept card testids.
    for name, dest, testid in (
        ("mock", "library/providers", "provider-card"),
        ("Alpha KB", "library/knowledge", "knowledge-base-card"),
        ("alpha-mcp", "library/mcp", "mcp-source-card"),
        ("Team chat", "library/connectors", "connector-card"),
    ):
        row = _lists.list_row(page, dest, name)
        expect(row).to_have_attribute("data-testid", testid)
        assert (row.get_attribute("href") or "").startswith(_nav.href(dest) + "/")
    # Icons: aria-hidden SVGs, one per type (sparkles, database, server, plug).
    icons = page.evaluate(
        """(sel) => Array.from(document.querySelectorAll(sel + ' .ui-list-pane-row')).map((r) => {
            const svg = r.querySelector('.ui-list-pane-icon svg');
            return svg ? {hidden: svg.getAttribute('aria-hidden'), shape: svg.innerHTML.slice(0, 20)} : null; })""",
        LIST,
    )
    assert all(i and i["hidden"] == "true" for i in icons), icons
    assert len({icons[i]["shape"] for i in (0, 1, 3, 5)}) == 4, icons
    # The meta is part of the row's accessible name (visible text in the link).
    # (the Local badge follows the meta: B6, ledger row 27).
    expect(
        page.get_by_role("link", name="alpha-mcp 3 tools · 1 agent Local", exact=True)
    ).to_have_count(1)
    # No section nav.
    expect(page.locator(".area-studio .section-nav")).to_have_count(0)
    expect(page.get_by_role("navigation", name="Library sections")).to_have_count(0)


def test_group_empty_lines(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    seed_knowledge_base(base, "Only KB")
    _ready(page, base, "library/knowledge")
    lines = page.locator(f"{LIST} .ui-list-pane-group-empty")
    expect(lines).to_have_text(["No MCP servers yet.", "No connectors yet."])
    expect(_rows(page)).to_have_count(2)  # the seeded provider and "Only KB"


def test_agent_counts_never_read_zero_while_agents_load(
    app_with_agent: SeededApp, page: Page
) -> None:
    """With the agents list held, rows show only what is known (no "0 agents"),
    and the counts fill in when it lands -- without changing any row's height
    (the meta line is reserved, so a scrolled-in group never shifts)."""
    base = app_with_agent.base_url
    _seed_full(app_with_agent)
    hold = _Hold(page, re.compile(r".*/api/agents$"))
    _nav.goto(page, base, "library")
    hold.wait_held()
    expect(_rows(page)).to_have_count(6, timeout=8000)
    assert _row_texts(page) == [
        ["mock", ""],
        ["Alpha KB", ""],
        ["Zeta KB", ""],
        ["alpha-mcp", "3 tools"],
        ["zeta-mcp", "Not connected"],
        ["Team chat", ""],
    ]
    heights = "(sel) => Array.from(document.querySelectorAll(sel + ' .ui-list-pane-row')).map((r) => r.getBoundingClientRect().height)"
    before = page.evaluate(heights, LIST)
    hold.release()
    expect(_rows(page).nth(1).locator(".ui-list-pane-meta")).to_have_text("2 agents", timeout=8000)
    expect(_rows(page).nth(5).locator(".ui-list-pane-meta")).to_have_text("2 agents")
    after = page.evaluate(heights, LIST)
    assert len(before) == len(after) == 6
    assert all(abs(a - b) <= 0.5 for a, b in zip(before, after, strict=True)), (before, after)
    # The reserved line is not part of any row's accessible name.
    expect(page.get_by_role("link", name="Alpha KB 2 agents")).to_have_count(1)


# ── B6: connection state and Local / Remote badge on the MCP rows (M31 F5 L11) ──

NOW = _time.time()
# name -> (seed kwargs, meta first part, badge, state)
MCP_STATES = {
    "st-connected": (
        {"tools": ["a", "b", "c"], "last_check": {"status": "ok", "at": NOW}},
        "3 tools",
        "Local",
        "connected",
    ),
    "st-preflight": ({"tools": ["a"]}, "1 tool", "Local", "connected"),
    "st-none": ({}, "Not connected", "Local", "none"),
    "st-remote-none": (
        {"type": "streamable-http", "url": "https://example.com/mcp"},
        "Not connected",
        "Remote",
        "none",
    ),
    "st-error": (
        {
            "type": "streamable-http",
            "url": "https://example.com/mcp",
            "tools": ["a", "b"],
            "last_check": {"status": "error", "at": NOW},
        },
        "Couldn't connect",
        "Remote",
        "error",
    ),
    "st-signin": (
        {
            "type": "streamable-http",
            "url": "https://example.com/mcp",
            "tools": ["a", "b", "c", "d"],
            "last_check": {"status": "auth_required", "at": NOW},
        },
        "Sign-in needed",
        "Remote",
        "signin",
    ),
}
STATE_WORDS = {
    "connected": "Connected",
    "none": "Not connected",
    "error": "Couldn't connect",
    "signin": "Sign-in needed",
}


def _seed_states(base: str) -> dict[str, str]:
    return {
        name: seed_mcp_source(base, name, **kw) for name, (kw, _m, _b, _s) in MCP_STATES.items()
    }


def _mcp_row(page: Page, name: str):
    return _lists.list_row(page, "library/mcp", name)


def test_mcp_rows_show_state_and_badge(app_clean: str, page: Page) -> None:
    """Every state's meta and the Local / Remote badge; an errored or signed-out
    row hides a cached tool count (FD decision); the badge kind follows the type (local / remote)."""
    _seed_states(app_clean)
    _ready(page, app_clean, "library")
    for name, (_kw, meta, badge, _state) in MCP_STATES.items():
        row = _mcp_row(page, name)
        expect(row.locator(".ui-list-pane-meta")).to_have_text(f"{meta} · 0 agents", timeout=8000)
        expect(row.locator(".badge")).to_have_text(badge)
        kind = "local" if badge == "Local" else "remote"
        expect(row.locator(".badge")).to_have_class(re.compile(rf"\bbadge--{kind}\b"))
        if meta in ("Couldn't connect", "Sign-in needed"):
            assert "tool" not in row.locator(".ui-list-pane-meta").inner_text()
    # The meta and the badge are part of the row's accessible name.
    expect(
        page.get_by_role("link", name="st-error Couldn't connect · 0 agents Remote", exact=True)
    ).to_have_count(1)


def test_mcp_row_state_stays_while_agents_load(app_clean: str, page: Page) -> None:
    _seed_states(app_clean)
    hold = _Hold(page, re.compile(r".*/api/agents$"))
    _nav.goto(page, app_clean, "library")
    hold.wait_held()
    for name, (_kw, meta, badge, _state) in MCP_STATES.items():
        row = _mcp_row(page, name)
        expect(row.locator(".ui-list-pane-meta")).to_have_text(meta, timeout=8000)
        expect(row.locator(".badge")).to_have_text(badge)
    hold.release()
    expect(_mcp_row(page, "st-none").locator(".ui-list-pane-meta")).to_have_text(
        "Not connected · 0 agents", timeout=8000
    )


def test_library_row_and_editor_status_line_agree(app_clean: str, page: Page) -> None:
    """DD6: one derivation, two readers. For each seeded server read the row's
    state first, open the editor (no connection check fires: only a create
    auto-runs a Test), then compare the status line's state."""
    ids = _seed_states(app_clean)
    connects: list[str] = []
    page.on("request", lambda r: connects.append(r.url) if "/test/connect" in r.url else None)
    _ready(page, app_clean, "library")

    def state_of(text: str) -> str:
        for state, word in STATE_WORDS.items():
            if state != "connected" and text.startswith(word):
                return state
        return (
            "connected" if re.match(r"\d+ tools?\b", text) or text.startswith("Connected") else "?"
        )

    for name, (_kw, _meta, _badge, state) in MCP_STATES.items():
        row = _mcp_row(page, name)
        expect(row.locator(".ui-list-pane-meta")).not_to_have_text(re.compile(r"^\s*$"))
        row_state = state_of(row.locator(".ui-list-pane-meta").inner_text())
        _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(ids[name])}")
        status = page.locator('[data-testid="mcp-connection-status"]')
        expect(status).to_be_visible(timeout=8000)
        expect(status).to_have_text(re.compile(rf"^{re.escape(STATE_WORDS[state])}"))
        assert row_state == state_of(status.inner_text()) == state, (name, row_state)
    assert connects == [], connects


# ── AC2: the Add menu ───────────────────────────────────────────────────────


@pytest.mark.parametrize("viewport", [(1440, 900), (1024, 768)], ids=["1440", "1024"])
def test_add_menu_is_not_clipped(app_clean: str, page: Page, viewport: tuple[int, int]) -> None:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    _ready(page, app_clean, "library/knowledge")
    page.locator('[data-testid="library-add-btn"]').click()
    expect(page.locator('[data-testid="library-add-knowledge"]')).to_be_visible()
    out = page.evaluate(
        """() => {
          const aside = document.getElementById('app-sidebar').getBoundingClientRect();
          return ['library-add-provider', 'library-add-knowledge', 'library-add-mcp',
                  'library-add-connector'].map((tid) => {
            const el = document.querySelector(`[data-testid="${tid}"]`);
            const r = el.getBoundingClientRect();
            const inside = r.left >= aside.left - 0.5 && r.right <= aside.right + 0.5 &&
                           r.top >= aside.top - 0.5 && r.bottom <= aside.bottom + 0.5;
            const corners = [[r.left + 2, r.top + 2], [r.right - 2, r.top + 2],
                             [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2]];
            const hits = corners.map(([x, y]) => { const h = document.elementFromPoint(x, y);
                                                   return !!h && (h === el || el.contains(h)); });
            return {tid, inside, hits, width: r.width};
          });
        }"""
    )
    for item in out:
        assert item["inside"], item
        assert all(item["hits"]), item
    assert (
        page.locator('[data-testid="library-add-knowledge"]')
        .locator("xpath=..")
        .get_attribute("class")
        .find("ui-menu-align-end")
        != -1
    )
    expect(page.get_by_role("menuitem")).to_have_text(
        ["Model provider", "Knowledge base", "MCP server", "Connector"]
    )


def test_add_menu_items_open_their_create_routes(app_with_agent: SeededApp, page: Page) -> None:
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.library_add(page, "knowledge")
    expect(page.locator('[data-testid="kb-create-name-input"]')).to_be_focused()
    _lists.library_add(page, "mcp")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    _lists.library_add(page, "connectors")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    # Choosing the create form that is already open only refocuses its first
    # field: no navigation, no prompt, even when it is dirty.
    name = page.locator('[data-field="name"]')
    name.fill("half")
    before = page.evaluate("history.length")
    page.locator('[data-testid="library-add-btn"]').click()
    page.locator('[data-testid="library-add-connector"]').click()
    expect(name).to_be_focused()
    expect(name).to_have_value("half")
    expect(page.locator(DIALOG)).to_have_count(0)
    assert page.evaluate("history.length") == before
    # Escape closes the menu and returns focus to the trigger.
    trigger = page.locator('[data-testid="library-add-btn"]')
    trigger.click()
    expect(page.locator('[data-testid="library-add-mcp"]')).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator('[data-testid="library-add-mcp"]')).to_be_hidden()
    expect(trigger).to_be_focused()


# ── AC3: editors beside the list ────────────────────────────────────────────


def test_each_editor_opens_beside_the_list(app_with_agent: SeededApp, page: Page) -> None:
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    for dest, name, probe in (
        ("library/knowledge", "Alpha KB", '[data-testid="kb-name-input"]'),
        ("library/mcp", "alpha-mcp", '[data-testid="save-mcp-source-btn"]'),
        ("library/connectors", "Team chat", '[data-testid="save-connector-btn"]'),
    ):
        _lists.open_item(page, dest, name)
        expect(page.locator(probe)).to_be_visible(timeout=8000)
        _lists.expect_selected(page, dest, name)
        expect(page.locator(LIST)).to_be_visible()
        # One h1 in the detail pane: the editor's own.
        expect(page.locator(".studio-section-content h1")).to_have_count(1)


@pytest.mark.parametrize(
    ("dest", "name", "other", "field"),
    [
        ("library/knowledge", "Alpha KB", "Zeta KB", '[data-testid="kb-name-input"]'),
        ("library/mcp", "alpha-mcp", "zeta-mcp", '[data-field="name"]'),
        ("library/connectors", "Team chat", "Alpha KB", '[data-field="name"]'),
    ],
    ids=["knowledge", "mcp", "connector"],
)
def test_dirty_editor_row_click_asks_once_and_stay_keeps_the_edit(
    app_with_agent: SeededApp, page: Page, dest: str, name: str, other: str, field: str
) -> None:
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.open_item(page, dest, name)
    edit = page.locator(field).first
    expect(edit).to_be_visible(timeout=8000)
    edit.fill(name + " edited")
    page.wait_for_function("() => App.nav.isDirty()")
    route = _nav.current_route(page)
    other_dest = "library/knowledge" if other.endswith("KB") else "library/mcp"
    _lists.list_row(page, other_dest, other).click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    page.wait_for_timeout(300)
    expect(page.locator(DIALOG)).to_have_count(0)  # asked once
    _nav.expect_route(page, route)
    expect(edit).to_have_value(name + " edited")


def test_delete_each_type_replaces_to_the_root_and_moves_focus(
    app_with_agent: SeededApp, page: Page
) -> None:
    """DD8: replace to the section root (no new history entry), the row leaves,
    and focus goes to the next row in list order (across groups), else the
    previous one."""
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")

    # Knowledge base: the next row is the next one in its group.
    _lists.open_item(page, "library/knowledge", "Alpha KB")
    before = page.evaluate("history.length")
    _confirm_delete(page, "delete-knowledge-base-btn")
    _nav.expect_route(page, "library", timeout=8000)
    expect(_lists.list_row(page, "library/knowledge", "Alpha KB")).to_have_count(0, timeout=8000)
    expect(_lists.library_start(page)).to_be_visible()
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.closest('.ui-list-pane-row')"
    )
    assert _focused_label(page) == "Zeta KB"
    assert page.evaluate("history.length") == before

    # MCP server: the last of its group -> the next row is in the next group.
    _lists.open_item(page, "library/mcp", "zeta-mcp")
    _confirm_delete(page, "delete-mcp-source-btn")
    _nav.expect_route(page, "library", timeout=8000)
    expect(_lists.list_row(page, "library/mcp", "zeta-mcp")).to_have_count(0, timeout=8000)
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.closest('.ui-list-pane-row')"
    )
    assert _focused_label(page) == "Team chat"

    # Connector: the last row of the list -> the previous row.
    _lists.open_item(page, "library/connectors", "Team chat")
    _confirm_delete(page, "delete-connector-btn")
    _nav.expect_route(page, "library", timeout=8000)
    expect(_lists.list_row(page, "library/connectors", "Team chat")).to_have_count(0, timeout=8000)
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.closest('.ui-list-pane-row')"
    )
    assert _focused_label(page) == "alpha-mcp"
    expect(page.locator(f"{LIST} .ui-list-pane-group-empty")).to_have_text(["No connectors yet."])


def test_list_follows_create_rename_and_delete_without_reload(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    seed_knowledge_base(base, "Rename me")
    _ready(page, base, "library/knowledge")
    page.evaluate("() => { window.__noReload = true; }")

    # Rename a knowledge base: the row follows the save.
    _lists.open_item(page, "library/knowledge", "Rename me")
    page.locator('[data-testid="kb-name-input"]').fill("Renamed KB")
    page.locator('[data-testid="save-knowledge-btn"]').click()
    expect(_lists.list_row(page, "library/knowledge", "Renamed KB")).to_be_visible(timeout=8000)
    expect(_lists.list_row(page, "library/knowledge", "Rename me")).to_have_count(0)
    _lists.expect_selected(page, "library/knowledge", "Renamed KB")

    # Create an MCP server: the row appears, selected.
    _lists.library_add(page, "mcp")
    page.locator('[data-field="name"]').fill("fresh-mcp")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("fresh-mcp")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    _lists.expect_selected(page, "library/mcp", "fresh-mcp")

    # Delete it: the row leaves.
    _confirm_delete(page, "delete-mcp-source-btn")
    expect(_lists.list_row(page, "library/mcp", "fresh-mcp")).to_have_count(0, timeout=8000)
    assert page.evaluate("() => window.__noReload") is True


# ── AC4: knowledge-base create (squawk 0101) ────────────────────────────────


def test_kb_create_form_opens_the_new_knowledge_base(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    seed_knowledge_base(base, "Existing KB")
    _ready(page, base, "library/knowledge")
    _lists.library_add(page, "knowledge")

    # The form: its own header (breadcrumb + the pane's only h1), the hint,
    # Create enabled, Cancel.
    pane = page.locator(".studio-section-content")
    expect(pane.locator(".editor-breadcrumb")).to_have_text("Library / Knowledge bases")
    expect(pane.locator("h1")).to_have_count(1)
    expect(pane.locator("h1.editor-title")).to_have_text("New knowledge base")
    create = page.locator('[data-testid="kb-create-submit-btn"]')
    expect(create).to_be_enabled()
    expect(page.locator('[data-testid="kb-create-cancel-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="kb-create-name-hint"]')).to_be_hidden()
    # The create form selects no row.
    expect(page.locator(f'{LIST} [aria-current="page"]')).to_have_count(0)

    posts: list[str] = []
    page.on(
        "request",
        lambda r: (
            posts.append(r.url)
            if r.method == "POST" and r.url.endswith("/api/knowledge-bases")
            else None
        ),
    )
    create.click()
    # The empty-name error sits under the Name field (M31 F3 HAT decision);
    # the form-level line is for server failures only.
    name_input = page.locator('[data-testid="kb-create-name-input"]')
    expect(page.locator('[data-testid="kb-create-name-error"]')).to_have_text("Name is required.")
    expect(name_input).to_have_attribute("aria-invalid", "true")
    expect(page.locator('[data-testid="kb-create-error"]')).to_have_text("")
    assert posts == []

    # The POST is held: Create stays disabled while it is in flight.
    hold = _Hold(page, re.compile(r".*/api/knowledge-bases$"), lambda req: req.method == "POST")
    page.locator('[data-testid="kb-create-name-input"]').fill("Brand new KB")
    before = page.evaluate("history.length")
    create.click()
    hold.wait_held()
    expect(create).to_be_disabled()
    page.evaluate("() => document.querySelector('[data-testid=\"kb-create-submit-btn\"]').click()")
    hold.release()

    # The new knowledge base opens: replaced route, selected row, name spoken,
    # focus in the folder field.
    page.wait_for_function(
        "p => location.hash.startsWith(p) && !location.hash.endsWith('/~new')",
        arg=_nav.href("library/knowledge") + "/",
        timeout=8000,
    )
    expect(page.locator(".studio-section-content .editor-title")).to_have_text(
        "Brand new KB", timeout=8000
    )
    assert len(posts) == 1, posts
    assert page.evaluate("history.length") == before
    _lists.expect_selected(page, "library/knowledge", "Brand new KB")
    expect(page.locator(ANNOUNCER)).to_have_text("Library — Knowledge bases — Brand new KB")
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_focused(timeout=8000)
    assert page.evaluate("App.nav.isDirty()") is False


def test_kb_create_cancel_returns_to_the_root(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    seed_knowledge_base(base, "First KB")
    _ready(page, base, "library/knowledge")
    before = page.evaluate("history.length")
    _lists.library_add(page, "knowledge")
    page.locator('[data-testid="kb-create-name-input"]').fill("Never made")
    page.wait_for_function("() => App.nav.isDirty()")
    page.locator('[data-testid="kb-create-cancel-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible()
    assert page.evaluate("App.nav.isDirty()") is False
    assert page.evaluate("history.length") == before + 1  # the Add push, then a replace
    # Focus: the first row of the knowledge-base group.
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.closest('.ui-list-pane-row')"
    )
    assert _focused_label(page) == "First KB"


# ── AC5: connector URLs ─────────────────────────────────────────────────────


def test_connector_cold_deep_link_selects_its_row_without_flash(
    app_with_agent: SeededApp, page: Page
) -> None:
    ids = _seed_full(app_with_agent)
    page.add_init_script(
        """(() => { window.__emptyFlash = false;
          new MutationObserver(() => {
            if (document.querySelector('[data-testid="library-start"]')) window.__emptyFlash = true;
          }).observe(document, {childList: true, subtree: true}); })();"""
    )
    _nav.goto_settled(page, app_with_agent.base_url, f"library/connectors/{_nav.seg(ids['conn'])}")
    expect(page.locator(".editor-title")).to_have_text("Team chat", timeout=8000)
    _lists.expect_selected(page, "library/connectors", "Team chat")
    _nav.expect_route(page, f"library/connectors/{_nav.seg(ids['conn'])}")
    assert page.evaluate("window.__emptyFlash") is False


def test_connector_dead_id_heals_to_the_root(app_with_agent: SeededApp, page: Page) -> None:
    _seed_full(app_with_agent)
    _nav.goto_settled(page, app_with_agent.base_url, "library/connectors/no-such-connector")
    _nav.expect_route(page, "library", timeout=8000)
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => { const s = App.areas.find((a) => a.id === 'studio');"
        " return s._pendingConnectorId === null && s._pendingConnectorFormMode === null; }"
    )


def test_connector_save_create_syncs_the_url_with_no_navigation(
    app_with_agent: SeededApp, page: Page
) -> None:
    _ready(page, app_with_agent.base_url, "library/connectors")
    _lists.library_add(page, "connectors")
    page.locator('[data-field="name"]').fill("Saved connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.get_by_role("switch", name="Enabled").locator("xpath=ancestor::label").click()
    page.evaluate(
        """() => { const s = App.areas.find((a) => a.id === 'studio'); window.__hydrates = 0;
          const orig = s.hydrateState; s.hydrateState = function () { window.__hydrates += 1; return orig.apply(this, arguments); }; }"""
    )
    before = page.evaluate("history.length")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    page.wait_for_function(
        "p => location.hash.startsWith(p) && !location.hash.endsWith('/~new')",
        arg=_nav.href("library/connectors") + "/",
        timeout=8000,
    )
    expect(page.locator(ANNOUNCER)).to_have_text("Library — Connectors — Saved connector")
    _lists.expect_selected(page, "library/connectors", "Saved connector")
    assert page.evaluate("window.__hydrates") == 0
    assert page.evaluate("history.length") == before
    assert page.evaluate("App.nav.isDirty()") is False


def test_connector_cancel_reverts_in_edit_and_returns_on_create(
    app_with_agent: SeededApp, page: Page
) -> None:
    ids = _seed_full(app_with_agent)
    route = f"library/connectors/{_nav.seg(ids['conn'])}"
    _ready(page, app_with_agent.base_url, route)
    name = page.locator('[data-field="name"]')
    expect(name).to_have_value("Team chat", timeout=8000)
    name.fill("Team chat edited")
    page.wait_for_function("() => App.nav.isDirty()")
    page.locator('[data-testid="cancel-connector-btn"]').click()
    expect(page.locator('[data-field="name"]')).to_have_value("Team chat", timeout=8000)
    _nav.expect_route(page, route)
    assert page.evaluate("App.nav.isDirty()") is False
    expect(page.locator(DIALOG)).to_have_count(0)

    _lists.library_add(page, "connectors")
    page.locator('[data-field="name"]').fill("Abandoned")
    page.locator('[data-testid="cancel-connector-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible()
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.closest('.ui-list-pane-row')"
    )
    assert _focused_label(page) == "Team chat"


# ── AC6: empty states, group scroll ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "copy", "probe"),
    [
        (
            "knowledge",
            "Folders of your documents that agents can search.",
            '[data-testid="kb-create-name-input"]',
        ),
        (
            "mcp",
            "Tool servers that use the Model Context Protocol",
            '[data-testid="save-mcp-source-btn"]',
        ),
        (
            "connectors",
            "Links to chat platforms such as Discord",
            '[data-testid="save-connector-btn"]',
        ),
    ],
)
def test_section_root_empty_state(
    app_with_agent: SeededApp, page: Page, kind: str, copy: str, probe: str
) -> None:
    _ready(page, app_with_agent.base_url, f"library/{kind}")
    empty = _lists.library_start(page)
    expect(empty).to_be_visible(timeout=8000)
    expect(empty).to_contain_text(copy)
    # No grid markup in the detail pane (AC6). A NEGATIVE check on the retired
    # tile classes: the class is built from parts so the retired-selector guard,
    # which fences tests that DRIVE retired surfaces, does not read it as one.
    tile = "entity" + "-tile"
    grid_markup = (
        f".studio-section-content .{tile}, .studio-section-content .{tile}-grid, "
        ".studio-section-content .page-header"
    )
    assert page.evaluate("sel => document.querySelectorAll(sel).length", grid_markup) == 0
    page.locator(f'[data-testid="library-start-{kind}-add"]').click()
    _nav.expect_route(page, f"library/{kind}/~new")
    expect(page.locator(probe)).to_be_visible(timeout=8000)


def test_library_root_leaves_the_list_scrolled_to_the_top(
    app_with_agent: SeededApp, page: Page
) -> None:
    """There is one root and no per-section group scroll (DD2): the `scroll to
    group at a section root` branch is gone. A cold `#library`, a bare section
    alias and a return to the root all leave the list at the top."""
    base = app_with_agent.base_url
    for i in range(24):
        seed_knowledge_base(base, f"KB {i:02d}")
    seed_mcp_source(base, "far-mcp")
    seed_connector(base, "Far connector")
    body = '[data-testid="library-list"] .ui-list-pane-body'
    for route in ("library", "library/mcp"):  # the second is the alias
        _ready(page, base, route)
        expect(_rows(page).first).to_be_visible(timeout=8000)
        page.wait_for_timeout(300)
        _nav.expect_route(page, "library")
        assert page.evaluate(f"() => document.querySelector('{body}').scrollTop") == 0, route


@pytest.mark.parametrize("kind", ["knowledge", "mcp"])
def test_cold_item_link_never_flashes_the_empty_state(
    app_with_agent: SeededApp, page: Page, kind: str
) -> None:
    ids = _seed_full(app_with_agent)
    item = ids["kb_a"] if kind == "knowledge" else ids["mcp_a"]
    page.add_init_script(
        """(() => { window.__emptyFlash = false;
          new MutationObserver(() => {
            if (document.querySelector('[data-testid="library-start"]')) window.__emptyFlash = true;
          }).observe(document, {childList: true, subtree: true}); })();"""
    )
    _nav.goto_settled(page, app_with_agent.base_url, f"library/{kind}/{_nav.seg(item)}")
    probe = (
        '[data-testid="kb-name-input"]'
        if kind == "knowledge"
        else '[data-testid="save-mcp-source-btn"]'
    )
    expect(page.locator(probe)).to_be_visible(timeout=8000)
    _lists.expect_selected(
        page, f"library/{kind}", "Alpha KB" if kind == "knowledge" else "alpha-mcp"
    )
    assert page.evaluate("window.__emptyFlash") is False


# ── Loading and failure ─────────────────────────────────────────────────────


def test_no_empty_line_flash_before_data_arrives(app_with_agent: SeededApp, page: Page) -> None:
    """While one collection is still loading the list stays in its loading
    state: no group reads "No ... yet." before the data says so."""
    seed_knowledge_base(app_with_agent.base_url, "Held KB")
    hold = _Hold(page, re.compile(r".*/api/mcp-sources$"))
    _nav.goto(page, app_with_agent.base_url, "library")
    hold.wait_held()
    lib = page.locator(LIST)
    expect(lib).to_be_visible(timeout=8000)
    expect(lib.locator(".ui-list-pane-empty .ui-empty-title")).to_have_text(
        "Loading library…", timeout=8000
    )
    page.wait_for_timeout(300)
    expect(lib.locator(".ui-list-pane-group-empty")).to_have_count(0)
    expect(lib.locator(".ui-list-pane-row")).to_have_count(0)
    hold.release()
    expect(lib.locator(".ui-list-pane-group-empty")).to_have_text(
        ["No MCP servers yet.", "No connectors yet."], timeout=8000
    )
    expect(_lists.list_row(page, "library/knowledge", "Held KB")).to_be_visible()


def test_a_failed_collection_reads_couldnt_load(app_with_agent: SeededApp, page: Page) -> None:
    seed_knowledge_base(app_with_agent.base_url, "Fine KB")

    def fail(route: Route) -> None:
        if route.request.method == "GET":
            route.fulfill(status=500, body="boom")
        else:
            route.continue_()

    page.route(re.compile(r".*/api/connectors$"), fail)
    _nav.goto_settled(page, app_with_agent.base_url, "library")
    lib = page.locator(LIST)
    expect(
        lib.locator(".ui-list-pane-group-empty", has_text="Couldn’t load connectors.")
    ).to_be_visible(timeout=8000)
    expect(_lists.list_row(page, "library/knowledge", "Fine KB")).to_be_visible()
    expect(lib.locator(".ui-list-pane-group-empty", has_text="No MCP servers yet.")).to_be_visible()


def test_a_failed_refresh_keeps_the_last_good_rows(app_with_agent: SeededApp, page: Page) -> None:
    seed_connector(app_with_agent.base_url, "Stale connector")
    _ready(page, app_with_agent.base_url, "library/connectors")
    expect(_lists.list_row(page, "library/connectors", "Stale connector")).to_be_visible(
        timeout=8000
    )

    failed: list[str] = []

    def fail(route: Route) -> None:
        if route.request.method == "GET":
            failed.append(route.request.url)
            route.fulfill(status=500, body="boom")
        else:
            route.continue_()

    page.route(re.compile(r".*/api/connectors$"), fail)
    # A trip to Chats and back: studio activate force-gets the collections.
    _nav.open_destination(page, "chats")
    expect(_nav.destination_panel(page, "chats")).to_be_visible(timeout=8000)
    _nav.open_destination(page, "library")
    page.wait_for_function("() => App.store.peek('connectors').ok === false", timeout=8000)
    assert failed
    expect(_lists.list_row(page, "library/connectors", "Stale connector")).to_be_visible()
    expect(page.locator(f"{LIST} .ui-list-pane-group-empty", has_text="load")).to_have_count(0)


# ── Leg 4b: the editors' chrome (DD2, DD8) ──────────────────────────────────
#
# Every Library item header carries the breadcrumb "Library / {Group}" whose
# "Library" segment links to ``#library`` (``editor-breadcrumb-link``; Back is
# retired), and the stable "Unsaved changes" caption. Creating each type opens
# the item without tearing its editor down.

CRUMB = {"knowledge": "Knowledge bases", "mcp": "MCP servers", "connectors": "Connectors"}
ITEM = {"knowledge": "Alpha KB", "mcp": "alpha-mcp", "connectors": "Team chat"}
NEW_TITLE = {
    "knowledge": "New knowledge base",
    "mcp": "New MCP server",
    "connectors": "New Connector",
}
TITLE = ".studio-section-content h1.editor-title"
UNSAVED = '.studio-section-content [data-testid="editor-unsaved"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'


def _crumb(page: Page) -> dict | None:
    """The detail pane's item header breadcrumb (its first line), read at once."""
    return page.evaluate(
        """() => { const pane = document.querySelector('.studio-section-content');
          const t = pane.querySelector('.editor-header-text');
          const f = t && t.firstElementChild; const a = f && f.querySelector('a');
          return f && {cls: f.className, text: f.textContent, link: a && a.textContent,
            href: a && a.getAttribute('href'), testid: a && a.getAttribute('data-testid'),
            linkFirst: !!a && f.firstChild === a, h1: pane.querySelectorAll('h1').length,
            underline: a && getComputedStyle(a).textDecorationLine,
            back: pane.querySelectorAll('.back-btn').length}; }"""
    )


def _expected_crumb(kind: str) -> dict:
    return {
        "cls": "editor-breadcrumb",
        "text": "Library / " + CRUMB[kind],
        "link": "Library",
        "href": _nav.href("library"),
        "testid": "editor-breadcrumb-link",
        "linkFirst": True,
        "h1": 1,
        "underline": "underline",  # at rest, not colour alone (the flight-end review)
        "back": 0,
    }


def _asked_once(page: Page) -> None:
    page.wait_for_timeout(300)
    expect(page.locator(DIALOG)).to_have_count(0)


def _count_hydrates(page: Page) -> None:
    page.evaluate(
        """() => { const s = App.areas.find((a) => a.id === 'studio'); window.__hydrates = 0;
          const orig = s.hydrateState; s.hydrateState = function () { window.__hydrates += 1; return orig.apply(this, arguments); }; }"""
    )


def _wait_item_route(page: Page, kind: str) -> None:
    """The create route moved to the new item (``/{id}``, not ``~new``)."""
    page.wait_for_function(
        "p => location.hash.startsWith(p) && !location.hash.endsWith('/~new')",
        arg=_nav.href(f"library/{kind}") + "/",
        timeout=8000,
    )


def _mark(page: Page, selector: str, value: str) -> None:
    page.evaluate(
        "([sel, v]) => { document.querySelector(sel).dataset.keep = v; }", [selector, value]
    )


def _mark_of(page: Page, selector: str) -> str | None:
    return page.evaluate(
        "sel => { const n = document.querySelector(sel); return n ? (n.dataset.keep || null) : 'gone'; }",
        selector,
    )


# AC1: breadcrumbs.


def test_each_editor_shows_its_breadcrumb_in_edit_and_create_modes(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The first child of ``.editor-header-text``: "Library / {Group}" with the
    "Library" a link to ``#library`` (DOM-built, ``App.router.href``); one h1 in
    the pane and no Back, in edit mode and on each ``~new`` form."""
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    for kind in ("knowledge", "mcp", "connectors"):
        _lists.open_item(page, f"library/{kind}", ITEM[kind])
        expect(page.locator(TITLE)).to_have_text(ITEM[kind], timeout=8000)
        assert _crumb(page) == _expected_crumb(kind), kind
        _lists.library_add(page, kind)
        expect(page.locator(TITLE)).to_have_text(NEW_TITLE[kind], timeout=8000)
        assert _crumb(page) == _expected_crumb(kind), kind + " ~new"


def test_kb_breadcrumb_survives_a_save_in_place_and_the_poll_keeps_running(
    app_with_agent: SeededApp, page: Page
) -> None:
    # M31 F3 L05a: Save patches the mounted frame in place (no remount), so the
    # breadcrumb node marked before the Save is the same node after it (before
    # 05a this asserted the opposite: a remount built a new header).
    base = app_with_agent.base_url
    kb = seed_knowledge_base(base, "Remount KB")
    _ready(page, base, "library/knowledge")
    _lists.open_item(page, "library/knowledge", "Remount KB")
    expect(page.locator(TITLE)).to_have_text("Remount KB", timeout=8000)
    _mark(page, ".studio-section-content .editor-breadcrumb", "first-mount")
    page.locator('[data-testid="kb-name-input"]').fill("Remounted KB")
    page.locator('[data-testid="save-knowledge-btn"]').click()
    expect(page.locator(TITLE)).to_have_text("Remounted KB", timeout=8000)
    assert _crumb(page) == _expected_crumb("knowledge")
    assert _mark_of(page, ".studio-section-content .editor-breadcrumb") == "first-mount"
    # The status poll still runs after the Save (one 5s tick).
    with page.expect_request(
        lambda r: r.url.endswith(f"/api/knowledge-bases/{kb}/status"), timeout=8000
    ):
        pass


# AC2 / AC5b: the group link closes the item; focus goes to its row (DD8).


@pytest.mark.parametrize("kind", ["knowledge", "mcp", "connectors"])
def test_breadcrumb_link_closes_the_item_and_focuses_its_row(
    app_with_agent: SeededApp, page: Page, kind: str
) -> None:
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.open_item(page, f"library/{kind}", ITEM[kind])
    expect(page.locator(TITLE)).to_have_text(ITEM[kind], timeout=8000)
    before = page.evaluate("history.length")
    _lists.close_item(page)
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_lists.list_row(page, f"library/{kind}", ITEM[kind])).to_be_focused(timeout=8000)
    expect(page.locator(f'{LIST} [aria-current="page"]')).to_have_count(0)
    assert page.evaluate("history.length") == before + 1  # a pushed go(), like a row click
    assert page.evaluate("App.nav.isDirty()") is False


def test_breadcrumb_link_on_a_dirty_editor_asks_once(app_with_agent: SeededApp, page: Page) -> None:
    """Stay keeps the edit and the URL, and focus returns to the link; Continue
    closes to the root and focus goes to the item's row (after nav.js focuses
    <main>, so the row lands last)."""
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.open_item(page, "library/mcp", "alpha-mcp")
    name = page.locator('[data-field="name"]')
    expect(name).to_have_value("alpha-mcp", timeout=8000)
    name.fill("alpha-mcp edited")
    page.wait_for_function("() => App.nav.isDirty()")
    route = _nav.current_route(page)

    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _asked_once(page)
    _nav.expect_route(page, route)
    expect(name).to_have_value("alpha-mcp edited")
    expect(_lists.breadcrumb_link(page)).to_be_focused()

    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    expect(_lists.list_row(page, "library/mcp", "alpha-mcp")).to_be_focused(timeout=8000)
    _asked_once(page)
    assert page.evaluate("App.nav.isDirty()") is False


def test_kb_create_form_breadcrumb_link_returns_to_the_root(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The ``~new`` form's "Knowledge bases" link: clean, it closes at once and
    focus goes to the group's first row (a create form has no row of its own);
    dirty, it asks once."""
    base = app_with_agent.base_url
    seed_knowledge_base(base, "First KB")
    _ready(page, base, "library/knowledge")
    posts: list[str] = []
    page.on(
        "request",
        lambda r: (
            posts.append(r.url) if r.method == "POST" and "/knowledge-bases" in r.url else None
        ),
    )
    _lists.library_add(page, "knowledge")
    expect(page.locator(TITLE)).to_have_text(NEW_TITLE["knowledge"], timeout=8000)
    _lists.close_item(page)
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_lists.list_row(page, "library/knowledge", "First KB")).to_be_focused(timeout=8000)

    _lists.library_add(page, "knowledge")
    field = page.locator('[data-testid="kb-create-name-input"]')
    field.fill("Half made")
    page.wait_for_function("() => App.nav.isDirty()")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _asked_once(page)
    _nav.expect_route(page, "library/knowledge/~new")
    expect(field).to_have_value("Half made")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    expect(_lists.list_row(page, "library/knowledge", "First KB")).to_be_focused(timeout=8000)
    _asked_once(page)
    assert page.evaluate("App.nav.isDirty()") is False
    assert posts == []


# AC3: the unsaved indicator -- shows on an edit, clears on Save, Cancel or
# Continue, and is a stable node (toggled, never re-created, within a mount).


def _expect_unsaved(page: Page, text: str) -> None:
    expect(page.locator(UNSAVED)).to_have_text(text, timeout=8000)


def _continue_to_row(page: Page, dest: str, name: str) -> None:
    _lists.list_row(page, dest, name).click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(page.locator(TITLE)).to_have_text(name, timeout=8000)


def test_unsaved_indicator_on_the_knowledge_base_detail(
    app_with_agent: SeededApp, page: Page
) -> None:
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.open_item(page, "library/knowledge", "Alpha KB")
    expect(page.locator(TITLE)).to_have_text("Alpha KB", timeout=8000)
    expect(page.locator(UNSAVED)).to_have_attribute("role", "status")
    _expect_unsaved(page, "")
    _mark(page, UNSAVED, "stable")
    name = page.locator('[data-testid="kb-name-input"]')
    name.fill("Alpha KB edited")
    _expect_unsaved(page, "Unsaved changes")
    page.locator('[data-testid="cancel-knowledge-btn"]').click()
    _expect_unsaved(page, "")
    assert _mark_of(page, UNSAVED) == "stable"
    # Save patches the detail in place (M31 F3 L05a): its header goes clean.
    name.fill("Alpha KB saved")
    _expect_unsaved(page, "Unsaved changes")
    page.locator('[data-testid="save-knowledge-btn"]').click()
    expect(page.locator(TITLE)).to_have_text("Alpha KB saved", timeout=8000)
    _expect_unsaved(page, "")
    # Continue (a row click while dirty) opens the other item, clean.
    page.locator('[data-testid="kb-name-input"]').fill("Alpha KB again")
    _expect_unsaved(page, "Unsaved changes")
    _continue_to_row(page, "library/knowledge", "Zeta KB")
    _expect_unsaved(page, "")
    assert page.evaluate("App.nav.isDirty()") is False


def test_unsaved_indicator_on_the_knowledge_base_create_form(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    seed_knowledge_base(base, "First KB")
    _ready(page, base, "library/knowledge")
    _lists.library_add(page, "knowledge")
    expect(page.locator(TITLE)).to_have_text(NEW_TITLE["knowledge"], timeout=8000)
    expect(page.locator(UNSAVED)).to_have_attribute("role", "status")
    _expect_unsaved(page, "")
    _mark(page, UNSAVED, "stable")
    field = page.locator('[data-testid="kb-create-name-input"]')
    field.fill("Typed")
    _expect_unsaved(page, "Unsaved changes")
    field.fill("")
    _expect_unsaved(page, "")
    assert _mark_of(page, UNSAVED) == "stable"
    # Cancel: the form goes (and its caption with it).
    field.fill("Typed again")
    _expect_unsaved(page, "Unsaved changes")
    page.locator('[data-testid="kb-create-cancel-btn"]').click()
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    expect(page.locator(UNSAVED)).to_have_count(0)
    # Save (Create): the new knowledge base opens, clean.
    _lists.library_add(page, "knowledge")
    page.locator('[data-testid="kb-create-name-input"]').fill("Created KB")
    _expect_unsaved(page, "Unsaved changes")
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    expect(page.locator(TITLE)).to_have_text("Created KB", timeout=8000)
    _expect_unsaved(page, "")
    # Continue from a dirty form: the row's item opens, clean.
    _lists.library_add(page, "knowledge")
    page.locator('[data-testid="kb-create-name-input"]').fill("Abandoned KB")
    _expect_unsaved(page, "Unsaved changes")
    _continue_to_row(page, "library/knowledge", "First KB")
    _expect_unsaved(page, "")
    assert page.evaluate("App.nav.isDirty()") is False


def test_unsaved_indicator_on_the_mcp_editor(app_with_agent: SeededApp, page: Page) -> None:
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.open_item(page, "library/mcp", "alpha-mcp")
    expect(page.locator(TITLE)).to_have_text("alpha-mcp", timeout=8000)
    expect(page.locator(UNSAVED)).to_have_attribute("role", "status")
    _expect_unsaved(page, "")
    _mark(page, UNSAVED, "stable")
    name = page.locator('[data-field="name"]')
    name.fill("alpha-mcp edited")
    _expect_unsaved(page, "Unsaved changes")
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()  # edit mode: reverts in place
    expect(name).to_have_value("alpha-mcp")
    _expect_unsaved(page, "")
    # An edit save keeps the editor: the same caption node clears.
    name.fill("alpha-mcp saved")
    _expect_unsaved(page, "Unsaved changes")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(_lists.list_row(page, "library/mcp", "alpha-mcp saved")).to_be_visible(timeout=8000)
    _expect_unsaved(page, "")
    assert _mark_of(page, UNSAVED) == "stable"
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_disabled()
    name.fill("alpha-mcp again")
    _expect_unsaved(page, "Unsaved changes")
    _continue_to_row(page, "library/mcp", "zeta-mcp")
    _expect_unsaved(page, "")
    assert page.evaluate("App.nav.isDirty()") is False


def test_unsaved_indicator_on_the_connector_editor(app_with_agent: SeededApp, page: Page) -> None:
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.open_item(page, "library/connectors", "Team chat")
    expect(page.locator(TITLE)).to_have_text("Team chat", timeout=8000)
    expect(page.locator(UNSAVED)).to_have_attribute("role", "status")
    _expect_unsaved(page, "")
    _mark(page, UNSAVED, "stable")
    name = page.locator('[data-field="name"]')
    name.fill("Team chat saved")
    _expect_unsaved(page, "Unsaved changes")
    assert _mark_of(page, UNSAVED) == "stable"
    # An edit save keeps the editor: the caption clears and Save disables.
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(_lists.list_row(page, "library/connectors", "Team chat saved")).to_be_visible(
        timeout=8000
    )
    _expect_unsaved(page, "")
    assert _mark_of(page, UNSAVED) == "stable"
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_disabled()
    assert page.evaluate("App.nav.isDirty()") is False
    # Cancel in edit mode re-renders from the saved row: clean.
    name.fill("Team chat edited")
    _expect_unsaved(page, "Unsaved changes")
    page.locator('[data-testid="cancel-connector-btn"]').click()
    expect(page.locator('[data-field="name"]')).to_have_value("Team chat saved", timeout=8000)
    _expect_unsaved(page, "")
    page.locator('[data-field="name"]').fill("Team chat again")
    _expect_unsaved(page, "Unsaved changes")
    _continue_to_row(page, "library/knowledge", "Alpha KB")
    _expect_unsaved(page, "")
    assert page.evaluate("App.nav.isDirty()") is False


# Behavior-gate fix (list-and-detail L6): Cancel on a create form abandons it
# (DD8), so it is enabled from first render, typed into or not. Edit mode is
# unchanged: Cancel reverts, and is disabled while the item is clean.

_CREATE_FORM = {
    "mcp": ("New MCP server", "cancel-mcp-source-btn", "first-mcp"),
    "connectors": ("New Connector", "cancel-connector-btn", "First connector"),
}


@pytest.mark.parametrize(
    ("kind", "with_row"),
    [("mcp", True), ("mcp", False), ("connectors", True), ("connectors", False)],
    ids=[
        "mcp-focuses-first-row",
        "mcp-focuses-add",
        "connector-focuses-first-row",
        "connector-focuses-add",
    ],
)
def test_cancel_on_a_pristine_create_form_abandons_it(
    app_with_agent: SeededApp, page: Page, kind: str, with_row: bool
) -> None:
    """Nothing typed: Cancel is enabled; it opens no dialog, replaces the route
    with the section root, shows its empty state and focuses the group's first
    row, else Add (DD8)."""
    base = app_with_agent.base_url
    title, cancel_testid, row_name = _CREATE_FORM[kind]
    if with_row:
        if kind == "mcp":
            seed_mcp_source(base, row_name)
        else:
            seed_connector(base, row_name)
    _ready(page, base, f"library/{kind}")
    _lists.library_add(page, kind)
    expect(page.locator(TITLE)).to_have_text(title, timeout=8000)
    cancel = page.locator(f'[data-testid="{cancel_testid}"]')
    expect(cancel).to_be_enabled()  # nothing typed
    _expect_unsaved(page, "")
    assert page.evaluate("App.nav.isDirty()") is False
    before = page.evaluate("history.length")
    cancel.click()
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    expect(page.locator(TITLE)).to_have_count(0)
    _lists.expect_none_selected(page, f"library/{kind}")
    if with_row:
        expect(_lists.list_row(page, f"library/{kind}", row_name)).to_be_focused()
    else:
        expect(page.locator('[data-testid="library-add-btn"]')).to_be_focused()
    assert page.evaluate("history.length") == before  # replaced, not pushed
    expect(page.locator("dialog[open]")).to_have_count(0)
    expect(page.locator(DIALOG)).to_have_count(0)


def test_mcp_create_form_cancel_stays_enabled_when_the_form_is_clean_again(
    app_with_agent: SeededApp, page: Page
) -> None:
    """An edit undone on the MCP create form leaves it clean (Create disabled,
    no caption) but Cancel enabled. (The connector form has no clean-again
    state: its dirty mark is one-way.)"""
    _ready(page, app_with_agent.base_url, "library/mcp")
    _lists.library_add(page, "mcp")
    expect(page.locator(TITLE)).to_have_text("New MCP server", timeout=8000)
    name = page.locator('[data-field="name"]')
    cancel = page.locator('[data-testid="cancel-mcp-source-btn"]')
    name.fill("x")
    _expect_unsaved(page, "Unsaved changes")
    expect(cancel).to_be_enabled()
    name.fill("")
    _expect_unsaved(page, "")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_disabled()
    expect(cancel).to_be_enabled()
    cancel.click()
    _nav.expect_route(page, "library")
    expect(page.locator(TITLE)).to_have_count(0, timeout=8000)
    expect(page.locator("dialog[open]")).to_have_count(0)


@pytest.mark.parametrize(
    ("kind", "name", "cancel_testid"),
    [
        ("mcp", "alpha-mcp", "cancel-mcp-source-btn"),
        ("connectors", "Team chat", "cancel-connector-btn"),
    ],
    ids=["mcp", "connector"],
)
def test_cancel_on_a_clean_open_item_stays_disabled(
    app_with_agent: SeededApp, page: Page, kind: str, name: str, cancel_testid: str
) -> None:
    """Edit mode is unchanged: disabled while clean, enabled by an edit, and
    disabled again once Cancel has reverted it in place."""
    _seed_full(app_with_agent)
    _ready(page, app_with_agent.base_url, "library/knowledge")
    _lists.open_item(page, f"library/{kind}", name)
    expect(page.locator(TITLE)).to_have_text(name, timeout=8000)
    cancel = page.locator(f'[data-testid="{cancel_testid}"]')
    expect(cancel).to_be_disabled()
    route = _nav.current_route(page)
    page.locator('[data-field="name"]').fill(name + " edited")
    expect(cancel).to_be_enabled()
    cancel.click()
    expect(page.locator('[data-field="name"]')).to_have_value(name, timeout=8000)
    expect(page.locator(f'[data-testid="{cancel_testid}"]')).to_be_disabled()
    _nav.expect_route(page, route)


# AC4: create opens the item (DD8 per-type checks).


def test_kb_save_create_opens_the_item_and_a_row_click_does_not_prompt(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Knowledge base: a replace ``go`` from ``~new`` (leg 4a). The new detail
    mounts with its breadcrumb, the row is selected, the name is announced,
    ``history.length`` is unchanged, and ``dirty`` is clear, so the next row
    click opens with no prompt."""
    base = app_with_agent.base_url
    seed_knowledge_base(base, "Existing KB")
    _ready(page, base, "library/knowledge")
    _lists.library_add(page, "knowledge")
    page.locator('[data-testid="kb-create-name-input"]').fill("Made KB")
    page.wait_for_function("() => App.nav.isDirty()")
    before = page.evaluate("history.length")
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    _wait_item_route(page, "knowledge")
    expect(page.locator(TITLE)).to_have_text("Made KB", timeout=8000)
    expect(page.locator('[data-testid="kb-name-input"]')).to_have_value("Made KB")
    _lists.expect_selected(page, "library/knowledge", "Made KB")
    expect(page.locator(ANNOUNCER)).to_have_text("Library — Knowledge bases — Made KB")
    assert page.evaluate("history.length") == before
    assert _crumb(page) == _expected_crumb("knowledge")
    _expect_unsaved(page, "")
    assert page.evaluate("App.nav.isDirty()") is False
    _lists.list_row(page, "library/knowledge", "Existing KB").click()
    expect(page.locator(TITLE)).to_have_text("Existing KB", timeout=8000)
    _asked_once(page)


@pytest.mark.parametrize("connect", ["tools", "auth_required"])
def test_mcp_save_create_keeps_the_editor_and_its_connect_state(
    app_with_agent: SeededApp, page: Page, connect: str
) -> None:
    """MCP server: save-create keeps the editor's render path and ``sync``s the
    URL to the id. Nothing tears the editor down after the create's own
    create-to-edit render: the auto-run Refresh result (the Test result, or an
    OAuth "Sign in" consent prompt) survives the URL change, the announcement
    and the list reload. The MCP editor has no tabs, so the Test result is the
    transient state checked."""
    base = app_with_agent.base_url
    seed_mcp_source(base, "other-mcp")
    payload = (
        {
            "status": "ok",
            "tools": [
                {"name": "echo", "description": "", "input_schema": {}},
                {"name": "ping", "description": "", "input_schema": {}},
            ],
        }
        if connect == "tools"
        else {"status": "auth_required", "consent_url": "https://example.com/oauth/authorize?x=1"}
    )
    page.route(
        "**/api/mcp-sources/*/test/connect",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload)
        ),
    )
    _ready(page, base, "library/mcp")
    _lists.library_add(page, "mcp")
    expect(page.locator(TITLE)).to_have_text(NEW_TITLE["mcp"], timeout=8000)
    page.locator('[data-field="name"]').fill("fresh-http")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")
    page.wait_for_function("() => App.nav.isDirty()")
    _count_hydrates(page)
    before = page.evaluate("history.length")
    page.locator('[data-testid="save-mcp-source-btn"]').click()

    _wait_item_route(page, "mcp")
    expect(page.locator(ANNOUNCER)).to_have_text("Library — MCP servers — fresh-http")
    _lists.expect_selected(page, "library/mcp", "fresh-http")
    # M31 F5 L08b: a success hides the result area (the status line says Connected and
    # Tools lists the tools), so the tools list is the state; the area is still marked.
    state = (
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
        if connect == "tools"
        else page.locator('[data-testid="mcp-consent-btn"]')
    )
    if connect == "tools":
        expect(state).to_have_count(2, timeout=8000)
    else:
        expect(state).to_be_visible(timeout=8000)
    header = ".studio-section-content .editor-header"
    status = '.studio-section-content [data-testid="mcp-test-status"]'
    _mark(page, header, "kept")
    _mark(page, status, "kept")
    _nav.wait_settled(page)
    page.wait_for_timeout(300)
    assert [_mark_of(page, header), _mark_of(page, status)] == ["kept", "kept"]
    if connect == "tools":
        expect(state).to_have_count(2)
        expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible()
    else:
        expect(state).to_be_visible()
    route = _nav.current_route(page)
    assert route.startswith("library/mcp/") and not route.endswith("~new"), route
    assert page.evaluate("window.__hydrates") == 0
    assert page.evaluate("history.length") == before
    assert page.evaluate("App.nav.isDirty()") is False
    _expect_unsaved(page, "")
    assert _crumb(page) == _expected_crumb("mcp")
    _lists.list_row(page, "library/mcp", "other-mcp").click()
    expect(page.locator(TITLE)).to_have_text("other-mcp", timeout=8000)
    _asked_once(page)


def test_connector_save_create_keeps_its_fields_and_pairing_state(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Connector: save-create keeps the editor's render path and ``sync``s the URL
    to the id. The fields stay populated with what was entered, and a pairing
    code generated right after the create survives (nothing re-renders the
    editor again)."""
    base = app_with_agent.base_url
    agent = app_with_agent.agent_name
    seed_connector(base, "Other connector")
    _ready(page, base, "library/connectors")
    _lists.library_add(page, "connectors")
    expect(page.locator(TITLE)).to_have_text(NEW_TITLE["connectors"], timeout=8000)
    fields = {
        "name": "Fresh connector",
        "allowlist_peers": "peer-1",
        "allowlist_channels": "chan-1",
        "always_listen": "chan-1",
    }
    for field, value in fields.items():
        page.locator(f'[data-field="{field}"]').fill(value)
    page.locator('[data-field="default_agent"]').select_option(agent)
    page.locator('[data-testid="connector-channel-map-add-btn"]').click()
    map_row = page.locator('[data-testid="connector-channel-map-row"]')
    map_row.locator('[data-testid="connector-channel-map-channel"]').fill("chan-2")
    map_row.locator('[data-testid="connector-channel-map-agent"]').fill(agent)
    page.get_by_role("switch", name="Enabled").locator("xpath=ancestor::label").click()
    page.wait_for_function("() => App.nav.isDirty()")
    _count_hydrates(page)
    before = page.evaluate("history.length")
    page.locator('[data-testid="save-connector-btn"]').click()

    _wait_item_route(page, "connectors")
    expect(page.locator(ANNOUNCER)).to_have_text("Library — Connectors — Fresh connector")
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    _lists.expect_selected(page, "library/connectors", "Fresh connector")
    for field, value in fields.items():
        expect(page.locator(f'[data-field="{field}"]')).to_have_value(value)
    expect(page.locator('[data-field="default_agent"]')).to_have_value(agent)
    expect(map_row.locator('[data-testid="connector-channel-map-channel"]')).to_have_value("chan-2")
    expect(map_row.locator('[data-testid="connector-channel-map-agent"]')).to_have_value(agent)
    expect(page.locator('[data-field="enabled"]')).not_to_be_checked()
    assert page.evaluate("window.__hydrates") == 0
    assert page.evaluate("history.length") == before
    assert page.evaluate("App.nav.isDirty()") is False
    _expect_unsaved(page, "")
    assert _crumb(page) == _expected_crumb("connectors")

    page.locator('[data-testid="connector-pairing-btn"]').click()
    result = page.locator('[data-testid="connector-pairing-result"]')
    expect(result).to_contain_text("Expires", timeout=8000)
    pairing = '.studio-section-content [data-testid="connector-pairing-result"]'
    _mark(page, pairing, "kept")
    _nav.wait_settled(page)
    page.wait_for_timeout(300)
    assert _mark_of(page, pairing) == "kept"
    expect(result).to_contain_text("Expires")
    route = _nav.current_route(page)
    assert route.startswith("library/connectors/") and not route.endswith("~new"), route
    _lists.list_row(page, "library/connectors", "Other connector").click()
    expect(page.locator(TITLE)).to_have_text("Other connector", timeout=8000)
    _asked_once(page)
