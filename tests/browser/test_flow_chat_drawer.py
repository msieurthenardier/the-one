# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""The agent drawer on Chats (M25 F4 L6; flight DD7, DD15 A13, A20, A21; reference
spec 5.7): ``areas/chat/agent-drawer.js`` filling the static ``#chat-drawer`` shell
slot through ``App.ui.drawer``.

Push open by default at 1280 and 1440 (a 320px sibling of ``<main>``), overlay
closed by default at 1024 (over the chat pane's right, the toggle still on top);
the toggle's ``aria-pressed`` and Escape; the facts (model, the provider's display
name, the Chats count with connector sessions); "What it can use" (the knowledge
base, the MCP server with its tool count, the self-configuration loopback source
skipped, the built-in categories with their effective counts, self-configuration
On/Off, a failed load shown per group); the client's ``is_tool_enabled`` parity
with ``AgentConfig``; Open agent settings with the Agents filter cleared; the
default and deleted agents with no link; persistence across a reload and a resize;
hidden off Chats and while idle; landmarks and the resolver (AC16). Chromium; falls
in the ``chats`` lane (``test_flow_chat*``).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from browser import _chats, _lists, _nav
from browser._a11y_resolvers import collect_label_failures
from browser._credential_registry import auth_headers_for
from browser.seeders import (
    SeededApp,
    enable_notes,
    seed_knowledge_base,
    seed_mcp_source,
    seed_mock_agents,
    seed_note,
    seed_session,
    seed_tool_config,
)
from playwright.sync_api import Page, expect

from the_one.agent.config import AgentConfig

pytestmark = pytest.mark.browser

DRAWER = '[data-testid="chat-drawer"]'
TOGGLE = '[data-testid="chat-drawer-toggle"]'
SETTINGS = '[data-testid="chat-drawer-settings-link"]'
FACTS = '[data-testid="chat-drawer-facts"]'
USES = '[data-testid="chat-drawer-uses"]'
NOTE = '[data-testid="chat-drawer-note"]'

# The drawer's geometry and state in one read.
_GEOMETRY_JS = """() => {
  const d = document.getElementById('chat-drawer');
  const r = d.getBoundingClientRect(), s = getComputedStyle(d);
  const m = document.getElementById('main-content').getBoundingClientRect();
  const row = document.querySelector('.app-shell-row').getBoundingClientRect();
  const ch = document.querySelector('[data-testid="chat-header"]').getBoundingClientRect();
  const dh = d.querySelector('.ui-drawer-header').getBoundingClientRect();
  const t = document.querySelector('[data-testid="chat-drawer-toggle"]');
  return {hidden: d.hidden, mode: d.dataset.mode, position: s.position, display: s.display,
          left: r.left, right: r.right, top: r.top - row.top, bottom: r.bottom, w: r.width,
          mainW: m.width, mainRight: m.right, vw: innerWidth, rowBottom: row.bottom,
          chatHeaderBottom: ch.bottom, drawerHeaderBottom: dh.bottom, drawerHeaderH: dh.height,
          pressed: t.getAttribute('aria-pressed'), controls: t.getAttribute('aria-controls'),
          toggleHidden: t.hidden, shadow: s.boxShadow};
}"""

# The element on top at the toggle's centre (is the toggle clickable?).
_TOGGLE_ON_TOP_JS = """() => {
  const t = document.querySelector('[data-testid="chat-drawer-toggle"]').getBoundingClientRect();
  const e = document.elementFromPoint(t.left + t.width / 2, t.top + t.height / 2);
  const b = e && e.closest('button');
  return b ? b.getAttribute('data-testid') : null;
}"""


def _geometry(page: Page) -> dict:
    return page.evaluate(_GEOMETRY_JS)


def _open_pending(page: Page, base: str, agent: str, width: int, height: int = 800) -> None:
    page.set_viewport_size({"width": width, "height": height})
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)


def _group(page: Page, group: str):
    return page.locator(f'{USES} [data-group="{group}"]')


def _group_items(page: Page, group: str) -> list[str]:
    return page.evaluate(
        """(g) => Array.from(document.querySelectorAll(
             '[data-testid="chat-drawer-uses"] [data-group="' + g + '"] li')).map((li) => li.innerText.replace(/\\s+/g, ' ').trim())""",
        group,
    )


def _facts(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => { const out = {}; const dl = document.querySelector('[data-testid="chat-drawer-facts"]');
                   const dts = dl.querySelectorAll('dt');
                   dts.forEach((dt) => { out[dt.textContent] = dt.nextElementSibling.textContent; });
                   return out; }"""
    )


def _provider(base: str, name: str, ptype: str = "mock") -> str:
    r = httpx.post(
        f"{base}/api/providers",
        json={"name": name, "type": ptype, "base_url": "", "config": {}},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _agent(base: str, body: dict) -> str:
    payload = {"llm_model": "mock-default", "system_prompt": "You are a test agent."}
    payload.update(body)
    r = httpx.post(f"{base}/api/agents", json=payload, headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 201, r.text
    return r.json()["name"]


# ── Modes: push at 1280 and 1440, overlay at 1024 (AC4, AC5) ────────────────


@pytest.mark.parametrize("width", [1280, 1440])
def test_push_mode_is_open_by_default_and_lines_up_with_the_chat_header(
    app_with_agent: SeededApp, page: Page, width: int
) -> None:
    _open_pending(page, app_with_agent.base_url, app_with_agent.agent_name, width)
    expect(page.locator(DRAWER)).to_be_visible()
    g = _geometry(page)
    assert (g["mode"], g["position"], g["display"]) == ("push", "static", "flex"), g
    # A 320px flex sibling after <main>: main yields the width (72 rail, 300 list).
    assert g["w"] == 320 and g["right"] == g["vw"] and g["left"] == g["mainRight"], g
    assert g["mainW"] == width - 72 - 300 - 320, g  # 588 at 1280
    assert g["top"] == 0 and g["bottom"] == g["rowBottom"], g
    assert g["shadow"] == "none", g
    # A21: the drawer header is 48px and its hairline meets the chat header's.
    assert g["drawerHeaderH"] == 48 and g["drawerHeaderBottom"] == g["chatHeaderBottom"], g
    # AC5: the toggle.
    assert (g["pressed"], g["controls"], g["toggleHidden"]) == ("true", "chat-drawer", False), g
    toggle = page.locator(TOGGLE)
    expect(toggle).to_have_accessible_name("Show this chat's agent")
    expect(toggle).to_have_class("btn-ghost btn-icon chat-drawer-toggle")
    assert toggle.evaluate("t => t === t.parentElement.lastElementChild")  # at the header's end
    assert toggle.evaluate("t => getComputedStyle(t).marginLeft !== '0px'")  # margin-left: auto
    expect(page.get_by_role("complementary", name="This chat's agent")).to_be_visible()


def test_overlay_mode_is_closed_by_default_and_the_toggle_stays_on_top(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_pending(page, app_with_agent.base_url, app_with_agent.agent_name, 1024, 768)
    expect(page.locator(TOGGLE)).to_be_visible()
    g = _geometry(page)
    assert g["hidden"] is True and g["pressed"] == "false", g
    assert g["mainW"] == 1024 - 72 - 300, g  # 652, not covered on arrival
    page.locator(TOGGLE).click()
    expect(page.locator(DRAWER)).to_be_visible()
    g = _geometry(page)
    assert (g["mode"], g["position"]) == ("overlay", "absolute"), g
    # Over the chat pane's right: top 0, right 0, bottom 0 of the shell row.
    assert (
        g["w"] == 320 and g["right"] == 1024 and g["top"] == 0 and g["bottom"] == g["rowBottom"]
    ), g
    assert g["mainW"] == 652, g  # the pane keeps its width under the overlay
    assert g["shadow"] != "none" and g["pressed"] == "true", g
    # No scrim, no outside-click close; the toggle is still the top element.
    page.locator('[data-testid="chat-input"]').click(force=True)
    expect(page.locator(DRAWER)).to_be_visible()
    assert page.evaluate(_TOGGLE_ON_TOP_JS) == "chat-drawer-toggle"
    page.locator(TOGGLE).click()
    expect(page.locator(DRAWER)).to_be_hidden()
    assert _geometry(page)["pressed"] == "false"


def test_toggle_and_escape_close_with_focus_back_on_the_toggle(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_pending(page, app_with_agent.base_url, app_with_agent.agent_name, 1280)
    toggle = page.locator(TOGGLE)
    drawer = page.locator(DRAWER)
    expect(drawer).to_be_visible()
    toggle.click()
    expect(drawer).to_be_hidden()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    assert _geometry(page)["mainW"] == 1280 - 72 - 300  # main takes the width back
    toggle.click()
    expect(drawer).to_be_visible()
    expect(toggle).to_have_attribute("aria-pressed", "true")
    # Escape with focus inside the drawer closes it; focus returns to the toggle.
    page.locator(SETTINGS).focus()
    page.keyboard.press("Escape")
    expect(drawer).to_be_hidden()
    expect(toggle).to_be_focused()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    stored = page.evaluate("() => localStorage.getItem('chat-drawer-open')")
    assert json.loads(stored) == {"push": False, "overlay": False}


def test_open_state_persists_per_mode_across_reload_and_resize(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_pending(page, base, agent, 1440, 900)
    drawer, toggle = page.locator(DRAWER), page.locator(TOGGLE)
    expect(drawer).to_be_visible()
    toggle.click()  # push: closed
    expect(drawer).to_be_hidden()
    page.reload()
    _nav.expect_route(page, f"chats/~new/{_nav.seg(agent)}", timeout=8000)
    expect(toggle).to_be_visible(timeout=8000)
    expect(drawer).to_be_hidden()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    # Across 1280: the overlay's own state (closed by default), then open it.
    page.set_viewport_size({"width": 1024, "height": 768})
    page.wait_for_function(
        "() => document.getElementById('chat-drawer').dataset.mode === 'overlay'"
    )
    expect(drawer).to_be_hidden()
    toggle.click()
    expect(drawer).to_be_visible()
    assert json.loads(page.evaluate("() => localStorage.getItem('chat-drawer-open')")) == {
        "push": False,
        "overlay": True,
    }
    page.reload()
    expect(toggle).to_be_visible(timeout=8000)
    expect(drawer).to_be_visible()
    assert _geometry(page)["mode"] == "overlay"
    # Back to push: its persisted (closed) state applies.
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_function("() => document.getElementById('chat-drawer').dataset.mode === 'push'")
    expect(drawer).to_be_hidden()
    expect(toggle).to_have_attribute("aria-pressed", "false")


# ── The facts (AC6, AC7) ────────────────────────────────────────────────────


def test_header_badge_and_facts_with_the_provider_name_and_chats_count(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    provider = _provider(base, "Claude Max")
    agent = _agent(
        base,
        {
            "name": "Gardener",
            "provider_config_id": provider,
            "llm_model": "garden-model-1",
            "description": "Plans the vegetable beds.",
        },
    )
    _agent(base, {"name": "Other", "provider_config_id": provider})
    seed_session(base, agent, "Beds", "2026-09-01T10:00:00+00:00")
    seed_session(base, agent, "DM: someone", "2026-09-02T10:00:00+00:00", platform="discord")
    seed_session(base, "Other", "Not counted", "2026-09-03T10:00:00+00:00")
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)  # pending: the drawer shows the pending agent
    drawer = page.locator(DRAWER)
    expect(drawer.locator("h2")).to_have_text("Gardener")
    badge = drawer.locator(".chat-drawer-head .badge")
    expect(badge).to_have_text("mock")  # A20: the provider TYPE
    expect(badge).to_have_class("badge badge--mock")
    expect(drawer.locator(".chat-drawer-description")).to_have_text("Plans the vegetable beds.")
    expect(page.locator(FACTS)).to_be_visible()
    # Chats counts the connector session too (DD4), not the other agent's.
    page.wait_for_function(
        "() => (document.querySelector('[data-testid=\"chat-drawer-facts\"]') || {}).textContent.indexOf('Chats2') !== -1"
    )
    assert _facts(page) == {"Model": "garden-model-1", "Provider": "Claude Max", "Chats": "2"}
    styles = page.evaluate(
        """() => { const d = document.getElementById('chat-drawer');
          const name = getComputedStyle(d.querySelector('.chat-drawer-name'));
          const desc = getComputedStyle(d.querySelector('.chat-drawer-description'));
          const dt = getComputedStyle(d.querySelector('dt')), dd = d.querySelectorAll('dd');
          const probe = (v) => { const s = document.createElement('span'); s.style.color = 'var(' + v + ')';
            d.appendChild(s); const c = getComputedStyle(s).color; s.remove(); return c; };
          return {nameSize: name.fontSize, nameWeight: name.fontWeight, descSize: desc.fontSize,
                  descColor: desc.color === probe('--fg-secondary'), dtColor: dt.color === probe('--fg-muted'),
                  modelFont: getComputedStyle(dd[0]).fontFamily, providerFont: getComputedStyle(dd[1]).fontFamily,
                  bg: getComputedStyle(d).backgroundColor === (() => { const s = document.createElement('span');
                    s.style.backgroundColor = 'var(--surface)'; d.appendChild(s); const c = getComputedStyle(s).backgroundColor; s.remove(); return c; })()};
        }"""
    )
    assert (styles["nameSize"], styles["nameWeight"], styles["descSize"]) == (
        "13px",
        "600",
        "12px",
    ), styles
    assert styles["descColor"] and styles["dtColor"] and styles["bg"], styles
    assert "Geist Mono" in styles["modelFont"] and "Geist Mono" not in styles["providerFont"], (
        styles
    )
    # The first send makes a third chat; the count follows the `sessions` store.
    _chats.send_first(page, "hello")
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"chat-drawer-facts\"]').textContent.indexOf('Chats3') !== -1",
        timeout=10000,
    )


# ── What it can use (AC8) ───────────────────────────────────────────────────


def test_what_it_can_use_lists_the_attachments_and_the_effective_built_ins(
    app_with_provider: SeededApp, page: Page
) -> None:
    base, provider = app_with_provider.base_url, app_with_provider.provider_id
    kb = seed_knowledge_base(base, "Team wiki")
    seed_knowledge_base(base, "Not attached")
    mcp = seed_mcp_source(base, "GitHub", tools=[f"t{i}" for i in range(12)])
    cold = seed_mcp_source(base, "Cold server")  # tools never loaded: no count
    agent = _agent(
        base,
        {
            "name": "Researcher",
            "provider_config_id": provider,
            "kb_ids": [kb],
            "mcp_source_ids": [mcp, cold],
            "disabled_tools": ["shell", "python_exec", "web_search"],
        },
    )
    r = httpx.post(
        f"{base}/api/agents/{agent}/self-configuration", headers=auth_headers_for(base), timeout=5
    )
    assert r.status_code == 200, r.text
    ids = httpx.get(f"{base}/api/agents/{agent}", headers=auth_headers_for(base), timeout=5).json()[
        "mcp_source_ids"
    ]
    assert len(ids) == 3  # the loopback source is attached, and must be skipped
    seed_tool_config(base, "read_file", enabled=False)  # globally off
    bare = _agent(
        base,
        {"name": "Bare", "provider_config_id": provider, "enabled_tools": ["read_file", "glob"]},
    )

    _open_pending(page, base, agent, 1440, 900)
    expect(page.locator(USES).locator("h3")).to_have_text("What it can use")
    expect(_group(page, "self-configuration").locator("p")).to_have_text("On", timeout=8000)
    expect(_group(page, "tools").locator("li")).to_have_count(5, timeout=8000)
    assert _group_items(page, "knowledge") == ["Team wiki"]
    assert _group_items(page, "mcp") == ["Cold server", "GitHub 12 tools"]
    assert _group_items(page, "tools") == [
        "Filesystem 8 of 9",  # read_file is off for every agent
        "Execution 4 of 6",  # shell and python_exec are off for this agent
        "Web 3 of 4",  # web_search
        "Connectors 3 of 3",  # find_platform_destination included (AC9)
        "Time 1 of 1",  # current_time (M28)
    ]
    labels = page.locator(f"{USES} h4").all_inner_texts()
    assert labels == [
        "Rules",
        "Notes",
        "Routines",
        "Knowledge bases",
        "MCP servers",
        "Built-in tools",
        "Self-configuration",
    ]

    # An agent with nothing attached: "None", self-configuration Off, and a
    # whitelist that leaves one effective built-in (glob; read_file is off).
    _chats.pick(page, bare)
    expect(page.locator(DRAWER).locator("h2")).to_have_text("Bare")
    expect(_group(page, "self-configuration").locator("p")).to_have_text("Off", timeout=8000)
    expect(_group(page, "knowledge").locator("p")).to_have_text("None")
    expect(_group(page, "mcp").locator("p")).to_have_text("None")
    expect(_group(page, "tools").locator("li")).to_have_count(2)
    # current_time is exempt from the whitelist (M28), so it stays.
    assert _group_items(page, "tools") == ["Filesystem 1 of 9", "Time 1 of 1"]


def test_a_failed_load_shows_couldnt_load_for_that_group_only(
    app_with_agent: SeededApp, page: Page
) -> None:
    def fail(route) -> None:
        route.fulfill(status=500, body='{"detail": "boom"}', content_type="application/json")

    page.route("**/api/tools/configs", fail)
    page.route("**/self-configuration", fail)
    _open_pending(page, app_with_agent.base_url, app_with_agent.agent_name, 1440, 900)
    expect(_group(page, "tools").locator("p")).to_have_text("Couldn't load", timeout=8000)
    expect(_group(page, "self-configuration").locator("p")).to_have_text("Couldn't load")
    expect(_group(page, "knowledge").locator("p")).to_have_text("None")
    expect(_group(page, "mcp").locator("p")).to_have_text("None")
    assert _facts(page)["Model"] == "mock-default"


def test_one_tools_fetch_per_open(app_with_agent: SeededApp, page: Page) -> None:
    """One GET /api/tools/configs and one self-configuration GET per drawer open;
    a store notification re-renders without refetching."""
    seen: list[str] = []
    page.on(
        "request",
        lambda req: (
            seen.append(req.url)
            if req.url.split("?")[0].endswith(("/api/tools/configs", "/self-configuration"))
            else None
        ),
    )
    _open_pending(page, app_with_agent.base_url, app_with_agent.agent_name, 1440, 900)
    expect(_group(page, "self-configuration").locator("p")).to_have_text("Off", timeout=8000)
    expect(_group(page, "tools").locator("li")).to_have_count(5)
    page.wait_for_timeout(300)
    assert len(seen) == 2, seen
    page.evaluate("() => App.store.prime('sessions', App.store.peek('sessions').value || [])")
    page.wait_for_timeout(300)
    assert len(seen) == 2, seen
    page.locator(TOGGLE).click()  # close
    page.locator(TOGGLE).click()  # a new open: one more of each
    expect(_group(page, "self-configuration").locator("p")).to_have_text("Off", timeout=8000)
    page.wait_for_timeout(300)
    assert len(seen) == 4, seen


def test_client_is_tool_enabled_matches_agent_config(app_with_agent: SeededApp, page: Page) -> None:
    """AC8's built-ins-only effective logic is AgentConfig.is_tool_enabled
    reimplemented client-side: pinned case by case against the Python."""
    _nav.goto(page, app_with_agent.base_url, "chats")
    page.wait_for_function("() => !!(window.App && App.chat && App.chat.agentDrawer)")
    configs = [
        {"enabled_tools": None, "disabled_tools": []},
        {"enabled_tools": None, "disabled_tools": ["shell", "mcp__gh__issues", "kb__wiki__search"]},
        {"enabled_tools": [], "disabled_tools": []},
        {"enabled_tools": ["read_file", "shell"], "disabled_tools": ["shell"]},
        {"enabled_tools": ["read_file"], "disabled_tools": ["kb__wiki__search"]},
        {"enabled_tools": ["read_file"], "disabled_tools": []},
        {"enabled_tools": None, "disabled_tools": ["current_time"]},
        {"enabled_tools": ["read_file"], "disabled_tools": ["current_time"]},
    ]
    names = [
        "read_file",
        "shell",
        "web_search",
        "current_time",
        "mcp__gh__issues",
        "kb__wiki__search",
        "kb__other__search",
    ]
    for cfg in configs:
        expected = [AgentConfig(name="x", **cfg).is_tool_enabled(n) for n in names]
        got = page.evaluate(
            "([cfg, names]) => names.map((n) => App.chat.agentDrawer.isToolEnabled(cfg, n))",
            [cfg, names],
        )
        assert got == expected, (cfg, got, expected)


# ── Open agent settings (AC10, AC12) ────────────────────────────────────────


def test_open_agent_settings_goes_to_the_agent_with_the_filter_cleared(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    names = seed_mock_agents(base, app_with_provider.provider_id, 30)
    target = names[-2]  # "agent 29": far down the list
    page.set_viewport_size({"width": 1280, "height": 720})
    # The Agents list exists (and survives the visit to Chats) with a filter
    # that hides the target.
    _nav.goto(page, base, "agents")
    expect(_lists.first_row(page, "agents")).to_be_visible(timeout=8000)
    _lists.filter_agents(page, "agent 0")
    expect(_lists.list_row(page, "agents", target)).to_be_hidden()
    _nav.open_destination(page, "chats")
    _chats.start_chat(page, target)
    settings = page.locator(SETTINGS)
    expect(settings).to_have_text("Open agent settings")
    expect(settings).to_have_class("btn-outlined-primary chat-drawer-settings")
    settings.click()
    _nav.expect_route(page, f"agents/{_nav.seg(target)}/general", timeout=8000)
    expect(page.locator('[data-testid="agents-filter"]')).to_have_value("")
    _lists.expect_selected(page, "agents", target)
    row = _lists.item_link(page, "agents", target)
    expect(row).to_be_visible()
    # Scrolled into view inside the list body.
    inside = row.evaluate(
        """(r) => { const b = r.closest('.ui-list-pane-body').getBoundingClientRect(), x = r.getBoundingClientRect();
                    return x.top >= b.top - 0.5 && x.bottom <= b.bottom + 0.5; }"""
    )
    assert inside, "the selected row is not scrolled into view"
    # Off Chats the drawer is hidden and <main> has its full width again.
    expect(page.locator(DRAWER)).to_be_hidden()
    assert _geometry_main_full(page)


def _geometry_main_full(page: Page) -> bool:
    return page.evaluate(
        "() => document.getElementById('main-content').getBoundingClientRect().right === innerWidth"
        " && document.getElementById('chat-drawer').hidden"
    )


def test_clear_agent_filter_is_a_safe_no_op_before_studio_exists(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    page.wait_for_function("() => !!(window.App && App.chat && App.chat.agentDrawer)")
    assert page.evaluate("() => App.areas.find((a) => a.id === 'studio')._setActiveSection") is None
    page.evaluate("() => App.studio.clearAgentFilter()")  # no throw, nothing to clear


# ── Default, deleted and loading agents (AC11) ──────────────────────────────


def test_deleted_and_default_agents_show_no_settings_link(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    gone = seed_session(base, "gone-agent", "Orphaned chat", "2026-09-02T10:00:00+00:00")
    default = seed_session(base, None, "Default chat", "2026-09-01T10:00:00+00:00")
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, f"chats/{_nav.seg(gone)}")
    page.wait_for_function(
        "(id) => { const a = App.areas.find((x) => x.id === 'chat'); const s = a._sessionState(); return s.name === 'joined' && s.id === id; }",
        arg=gone,
    )
    drawer = page.locator(DRAWER)
    expect(drawer.locator("h2")).to_have_text("gone-agent")
    expect(page.locator(NOTE)).to_have_text("This agent no longer exists")
    expect(page.locator(SETTINGS)).to_be_hidden()
    expect(page.locator(USES)).to_have_count(0)
    expect(drawer.locator(".chat-drawer-head .badge")).to_be_hidden()
    assert _facts(page) == {"Chats": "1"}
    _chats.open_chat(page, default)
    expect(drawer.locator("h2")).to_have_text("Default agent")
    expect(page.locator(NOTE)).to_have_text("The default agent")
    expect(page.locator(SETTINGS)).to_be_hidden()
    assert (
        drawer.locator(".ui-drawer-footer").evaluate("f => getComputedStyle(f).display") == "none"
    )


def test_agents_store_not_loaded_is_loading_never_deleted(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A joined chat whose agent the `agents` store has not loaded reads
    "Loading…" with no link, never "This agent no longer exists"; once the
    store loads, the agent. (The chat area joins after its agents read
    settles, so a FAILED read is how the store stays unloaded.)"""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    sid = seed_session(base, agent, "Unloaded agents", "2026-09-02T10:00:00+00:00")
    gate = {"fail": True}

    def agents(route) -> None:
        if gate["fail"]:
            route.fulfill(status=500, body='{"detail": "boom"}', content_type="application/json")
        else:
            route.continue_()

    page.route("**/api/agents", agents)
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, f"chats/{_nav.seg(sid)}")
    page.wait_for_function(
        "(id) => { const a = (App.areas || []).find((x) => x.id === 'chat');"
        " return !!(a && a._sessionState) && a._sessionState().name === 'joined' && a._sessionState().id === id; }",
        arg=sid,
        timeout=10000,
    )
    assert page.evaluate("() => App.store.peek('agents').loaded") is False
    expect(page.locator(NOTE)).to_have_text("Loading…")
    expect(page.locator(SETTINGS)).to_be_hidden()
    expect(page.locator(DRAWER).locator("h2")).to_be_hidden()
    gate["fail"] = False
    page.evaluate("() => App.store.get('agents', {force: true})")
    expect(page.locator(DRAWER).locator("h2")).to_have_text(agent, timeout=8000)
    expect(page.locator(SETTINGS)).to_be_visible()
    expect(page.locator(NOTE)).to_have_count(0)


# ── Off Chats, idle, landmarks and the resolver (AC3, AC16) ─────────────────


def test_hidden_off_chats_and_while_idle(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)  # idle: no chat view
    expect(page.locator(DRAWER)).to_be_hidden()
    expect(page.locator(TOGGLE)).to_be_hidden()
    assert _geometry_main_full(page)
    _chats.start_chat(page, agent)
    expect(page.locator(DRAWER)).to_be_visible()
    for dest in ("agents", "library", "settings"):
        _nav.open_destination(page, dest)
        expect(_nav.destination_panel(page, dest)).to_be_visible(timeout=8000)
        expect(page.locator(DRAWER)).to_be_hidden()
        assert _geometry_main_full(page), dest
    _nav.open_destination(page, "chats")
    expect(page.locator(DRAWER)).to_be_visible(timeout=8000)  # the pending chat, still open


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_landmarks_and_resolver_with_the_drawer_open_and_while_idle(
    app_with_agent: SeededApp, page: Page, theme: str
) -> None:
    """AC16 and the cycle-2 aria-controls rule: the toggle's aria-controls
    resolves in every state (the drawer is never removed, only hidden), and no
    control is unnamed; the landmarks are main, the drawer's complementary,
    the rail's nav and the sidebar aside, each name unique."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    page.evaluate(f"App.theme.set('{theme}')")
    # Idle: the hidden toggle's aria-controls still resolves.
    assert page.locator(TOGGLE).count() == 1
    assert collect_label_failures(page, "body") == []
    _chats.start_chat(page, agent)
    expect(page.locator(DRAWER)).to_be_visible()
    expect(_group(page, "self-configuration").locator("p")).to_have_text("Off", timeout=8000)
    assert collect_label_failures(page, "body") == []
    landmarks = page.evaluate(
        """() => Array.from(document.querySelectorAll('main, aside, nav, [role=navigation], [role=complementary], [role=region], section[aria-label], section[aria-labelledby]'))
            .filter((n) => n.getClientRects().length)
            .map((n) => [n.getAttribute('role') || ({MAIN: 'main', ASIDE: 'complementary', NAV: 'navigation', SECTION: 'region'})[n.tagName],
                         n.getAttribute('aria-label') || ''])"""
    )
    pairs = sorted(tuple(x) for x in landmarks if x[0] != "region" or x[1])
    assert ("complementary", "This chat's agent") in pairs, pairs
    assert ("complementary", "Chats") in pairs and ("navigation", "Main") in pairs, pairs
    assert len(pairs) == len(set(pairs)), pairs
    expect(page.get_by_role("main")).to_have_count(1)
    expect(page.get_by_role("complementary", name="This chat's agent")).to_have_count(1)
    # "What it can use" is an h3 over plain groups: no region landmark in the
    # drawer (the Chats list pane's labelled <section> is the page's one).
    expect(page.locator(DRAWER).get_by_role("region")).to_have_count(0)


def test_the_drawer_subscribes_to_five_stores_and_releases_them_on_destroy(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC11: a drawer instance subscribes to `agents`, `providers`,
    `knowledge-bases`, `mcp-sources` and `sessions`, and `destroy()` releases
    every subscription (and its matchMedia listener) and empties its slot."""
    _nav.goto(page, app_with_agent.base_url, "chats")
    page.wait_for_function("() => !!(window.App && App.chat && App.chat.agentDrawer)")
    out = page.evaluate(
        """() => {
          const live = {};
          const sub = App.store.subscribe;
          App.store.subscribe = function (name, fn) {
            live[name] = (live[name] || 0) + 1;
            const off = sub.call(App.store, name, fn);
            return function () { live[name] -= 1; off(); };
          };
          const mql = window.matchMedia;
          let listeners = 0;
          window.matchMedia = function (q) {
            const m = mql.call(window, q);
            const add = m.addEventListener.bind(m), rem = m.removeEventListener.bind(m);
            m.addEventListener = function (t, f) { listeners += 1; add(t, f); };
            m.removeEventListener = function (t, f) { listeners -= 1; rem(t, f); };
            return m;
          };
          try {
            const slot = document.createElement('aside');
            slot.id = 'probe-drawer';
            const d = App.chat.agentDrawer.create({slot: slot});
            const during = Object.assign({}, live);
            const duringListeners = listeners;
            d.destroy();
            return {during, after: Object.assign({}, live), duringListeners, afterListeners: listeners,
                    kids: slot.children.length, hidden: slot.hidden};
          } finally {
            App.store.subscribe = sub;
            window.matchMedia = mql;
          }
        }"""
    )
    stores = ["agents", "knowledge-bases", "mcp-sources", "providers", "sessions"]
    assert sorted(out["during"]) == stores and set(out["during"].values()) == {1}, out
    assert set(out["after"].values()) == {0}, out
    assert (out["duringListeners"], out["afterListeners"]) == (1, 0), out
    assert out["kids"] == 0 and out["hidden"] is True, out


# ── The Rules group (M27 F1 L2; flight DD7) ──────────────────────────────────


def _add_rule(base: str, agent: str, text: str, enabled: bool = True) -> str:
    r = httpx.post(
        f"{base}/api/agents/{agent}/rules",
        json={"text": text, "enabled": enabled},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_rules_group_lists_enabled_rules_in_order_with_off_count_and_no_edit_link(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _add_rule(base, agent, "Always answer in French.")
    _add_rule(base, agent, "Never mention the weather.", enabled=False)
    long_text = "Keep every reply short. " * 15  # well past two lines
    _add_rule(base, agent, long_text.strip())

    _open_pending(page, base, agent, 1440, 900)
    group = _group(page, "rules")
    expect(group.locator("h4")).to_have_text("Rules")
    rows = group.locator('[data-testid="chat-drawer-rule"]')
    expect(rows).to_have_count(2, timeout=8000)
    assert _group_items(page, "rules")[0] == "Always answer in French."
    expect(rows.nth(1)).to_have_attribute("title", long_text.strip())
    assert group.locator('ul[data-testid="chat-drawer-rules"]').count() == 1
    assert group.locator("ol").count() == 0
    # The Rules group is the first group in "What it can use".
    first = page.locator(f"{USES} .chat-drawer-group").first
    expect(first).to_have_attribute("data-group", "rules")
    # The long rule is clamped to two lines.
    clamped = page.evaluate(
        """() => { const e = document.querySelectorAll('[data-testid="chat-drawer-rule"] .chat-drawer-rule-text')[1];
                   return e.scrollHeight > e.clientHeight; }"""
    )
    assert clamped
    expect(group.locator('[data-testid="chat-drawer-rules-off"]')).to_have_text("1 off")

    # Read-only (M27 F3 L2): no edit link in the group; Open agent settings is
    # the way to the editor.
    expect(group.locator("a, button")).to_have_count(0)


def test_rules_group_says_no_rules_when_none_or_none_enabled(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_pending(page, base, agent, 1440, 900)
    group = _group(page, "rules")
    expect(group.locator("p.chat-drawer-none")).to_have_text("No rules", timeout=8000)
    expect(group.locator('[data-testid="chat-drawer-rules-off"]')).to_have_count(0)

    # Only disabled rules: "No rules" and "1 off" together.
    _add_rule(base, agent, "Disabled one.", enabled=False)
    page.reload()
    _chats.start_chat(page, agent)
    group = _group(page, "rules")
    expect(group.locator("p.chat-drawer-none")).to_have_text("No rules", timeout=8000)
    expect(group.locator('[data-testid="chat-drawer-rules-off"]')).to_have_text("1 off")


def test_rules_group_404_is_no_rules_and_500_is_couldnt_load(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.route(
        "**/api/agents/*/rules",
        lambda route: route.fulfill(
            status=404, body='{"detail": "nope"}', content_type="application/json"
        ),
    )
    _open_pending(page, base, agent, 1440, 900)
    expect(_group(page, "rules").locator("p")).to_have_text("No rules", timeout=8000)

    page.unroute("**/api/agents/*/rules")
    page.route(
        "**/api/agents/*/rules",
        lambda route: route.fulfill(
            status=500, body='{"detail": "boom"}', content_type="application/json"
        ),
    )
    page.reload()
    _chats.start_chat(page, agent)
    expect(_group(page, "rules").locator("p")).to_have_text("Couldn't load", timeout=8000)
    expect(_group(page, "knowledge").locator("p")).to_have_text("None")


# ── The Notes group (M27 F2 L3; flight DD10) ─────────────────────────────────


@pytest.fixture
def notes_app(app_with_data_dir: tuple[str, Path]) -> tuple[SeededApp, Path]:
    base, data_dir = app_with_data_dir
    provider_id = _provider(base, "notes-drawer-provider")
    agent = _agent(base, {"name": "notes-drawer-agent", "provider_config_id": provider_id})
    return SeededApp(base_url=base, provider_id=provider_id, agent_name=agent), data_dir


def _stored_notes(base: str, agent: str) -> list[dict]:
    r = httpx.get(f"{base}/api/agents/{agent}/notes", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()["notes"]


def test_notes_group_off_shows_kept_count_and_follows_rules(
    notes_app: tuple[SeededApp, Path], page: Page
) -> None:
    app, data_dir = notes_app
    base, agent = app.base_url, app.agent_name
    seed_note(data_dir, agent, "Kept one.")
    seed_note(data_dir, agent, "Kept two.")
    _open_pending(page, base, agent, 1440, 900)
    group = _group(page, "notes")
    expect(group.locator("h4")).to_have_text("Notes", timeout=8000)
    expect(group.locator('[data-testid="chat-drawer-notes-off"]')).to_have_text("Off")
    expect(group.locator('[data-testid="chat-drawer-notes-kept"]')).to_have_text("2 kept")
    expect(group.locator('[data-testid="chat-drawer-notes-item"]')).to_have_count(0)
    # The Notes group is the sibling right after Rules.
    order = page.evaluate(
        """() => Array.from(document.querySelectorAll('[data-testid="chat-drawer-uses"] .chat-drawer-group')).map((g) => g.dataset.group)"""
    )
    assert order[:2] == ["rules", "notes"], order


def test_notes_group_lists_notes_with_origin_and_the_warning_flag(
    notes_app: tuple[SeededApp, Path], page: Page
) -> None:
    app, data_dir = notes_app
    base, agent = app.base_url, app.agent_name
    enable_notes(base, agent)
    sid = seed_session(base, agent, "Trip planning", "2026-01-01T09:00:00+00:00")
    seed_note(data_dir, agent, "Likes window seats.", session_id=sid, label="Trip planning")
    long_text = "A very long note that keeps going. " * 10
    seed_note(
        data_dir,
        agent,
        long_text.strip(),
        untrusted=True,
        sources=["fetch_url", "peer:peer-1"],
        origin_kind="connector",
        platform="discord",
        peer_name="Sam",
    )
    seed_note(data_dir, agent, "<b>x</b>", origin_kind="other")
    _open_pending(page, base, agent, 1440, 900)
    group = _group(page, "notes")
    items = group.locator('[data-testid="chat-drawer-notes-item"]')
    expect(items).to_have_count(3, timeout=8000)
    expect(items.nth(0)).not_to_contain_text("[1]")
    expect(items.nth(0)).to_have_attribute("data-number", "1")
    assert page.locator('[data-testid="chat-drawer-notes"] .chat-drawer-note-number').count() == 0
    assert (
        page.evaluate(
            """() => getComputedStyle(document.querySelector('[data-testid="chat-drawer-notes-item"]')).display"""
        )
        == "list-item"
    )
    expect(items.nth(0)).to_contain_text("Likes window seats.")
    expect(items.nth(0)).to_contain_text("Trip planning")
    expect(items.nth(1)).to_contain_text("discord \u00b7 Sam")
    expect(items.nth(1)).to_have_attribute("title", long_text.strip())
    flag = items.nth(1).locator('[data-testid="chat-drawer-notes-flag"]')
    sentence = (
        "Check this note: it was written after content that didn't come from you "
        "(fetch_url, peer:peer-1). It may have been planted."
    )
    expect(flag).to_have_attribute("title", sentence)
    expect(flag).to_have_attribute("aria-label", sentence)
    expect(flag).to_have_attribute("role", "img")
    expect(flag.locator("svg")).to_have_count(1)
    # The chip text is gone.
    expect(items.nth(1)).not_to_contain_text("Check this")
    expect(items.nth(0).locator('[data-testid="chat-drawer-notes-flag"]')).to_have_count(0)
    # Markup in a note is literal text.
    expect(items.nth(2)).to_contain_text("<b>x</b>")
    assert items.nth(2).locator("b").count() == 0
    expect(items.nth(2)).to_contain_text("Outside a chat")
    clamped = page.evaluate(
        """() => { const e = document.querySelectorAll('[data-testid="chat-drawer-notes-item"] .chat-drawer-note-text')[1];
                   return e.scrollHeight > e.clientHeight; }"""
    )
    assert clamped


def test_notes_group_is_read_only_no_delete_clear_or_edit_controls(
    notes_app: tuple[SeededApp, Path], page: Page
) -> None:
    app, data_dir = notes_app
    base, agent = app.base_url, app.agent_name
    enable_notes(base, agent)
    seed_note(data_dir, agent, "One.")
    seed_note(data_dir, agent, "Two.", untrusted=True, sources=["fetch_url"])
    _open_pending(page, base, agent, 1440, 900)
    group = _group(page, "notes")
    expect(group.locator('[data-testid="chat-drawer-notes-item"]')).to_have_count(2, timeout=8000)
    # No buttons or links anywhere in the Notes group, and none of the old words.
    expect(group.locator("a, button")).to_have_count(0)
    text = group.inner_text()
    for word in ("Delete", "Clear all", "Edit notes"):
        assert word not in text, text
    # Neither does the Rules group; the only way to the editor is the footer.
    expect(_group(page, "rules").locator("a, button")).to_have_count(0)
    expect(page.locator(SETTINGS)).to_be_visible()
    assert len(_stored_notes(base, agent)) == 2


def test_notes_group_without_a_session_has_no_pending_section(
    notes_app: tuple[SeededApp, Path], page: Page
) -> None:
    app, data_dir = notes_app
    base, agent = app.base_url, app.agent_name
    enable_notes(base, agent)
    seed_note(data_dir, agent, "Plain.")
    _open_pending(page, base, agent, 1440, 900)  # a pending chat: no session id
    group = _group(page, "notes")
    expect(group.locator('[data-testid="chat-drawer-notes-item"]')).to_have_count(1, timeout=8000)
    expect(group.locator('[data-testid="chat-drawer-notes-pending-head"]')).to_have_count(0)
    expect(group.locator('[data-testid="chat-drawer-notes-pending"]')).to_have_count(0)


def test_notes_group_pending_section_follows_the_open_chats_prompt(
    notes_app: tuple[SeededApp, Path], page: Page
) -> None:
    app, data_dir = notes_app
    base, agent = app.base_url, app.agent_name
    enable_notes(base, agent)
    seed_note(data_dir, agent, "In the prompt.")
    _open_pending(page, base, agent, 1440, 900)
    sid = _chats.send_first(page, "hello")  # builds the session with note 1 in its prompt
    group = _group(page, "notes")
    items = group.locator(
        '[data-testid="chat-drawer-notes"] [data-testid="chat-drawer-notes-item"]'
    )
    expect(items).to_have_count(1, timeout=8000)
    seed_note(data_dir, agent, "Saved later.", untrusted=True, sources=["fetch_url"])
    # The panel refreshes on a reopen of the drawer; here a rejoin is not yet
    # needed: toggling the drawer closed and open re-fetches.
    page.locator(TOGGLE).click()
    page.locator(TOGGLE).click()
    head = group.locator('[data-testid="chat-drawer-notes-pending-head"]')
    expect(head).to_have_text("Pending \u00b7 used from the next chat", timeout=8000)
    pending = group.locator(
        '[data-testid="chat-drawer-notes-pending"] [data-testid="chat-drawer-notes-item"]'
    )
    expect(pending).to_have_count(1)
    expect(pending).to_contain_text("Saved later.")
    expect(pending.locator('[data-testid="chat-drawer-notes-flag"]')).to_have_count(1)
    expect(items).to_have_count(1)
    # Pending text is muted, not faded: the colour differs, the opacity does not.
    muted = page.evaluate(
        """() => { const a = document.querySelector('[data-testid="chat-drawer-notes-pending"] .chat-drawer-note-text');
                   const b = document.querySelector('[data-testid="chat-drawer-notes"] .chat-drawer-note-text');
                   return [getComputedStyle(a).color !== getComputedStyle(b).color, getComputedStyle(a).opacity]; }"""
    )
    assert muted == [True, "1"], muted
    # A rejoin rebuilds the prompt: the note moves to the in-use list.
    page.reload()
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    expect(items).to_have_count(2, timeout=10000)
    expect(head).to_have_count(0)


def test_notes_group_refreshes_live_when_the_agent_saves_a_note(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, _data_dir = app_with_data_dir
    r = httpx.post(
        f"{base}/api/providers",
        json={
            "name": "notes-live-provider",
            "type": "mock",
            "base_url": "",
            "config": {
                "response": {
                    "content": "Saved.",
                    "tool_calls": [
                        {"id": "c1", "name": "save_note", "arguments": {"text": "Live saved note."}}
                    ],
                }
            },
        },
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    agent = _agent(
        base,
        {"name": "notes-live-agent", "provider_config_id": r.json()["id"], "max_iterations": 2},
    )
    enable_notes(base, agent)
    _open_pending(page, base, agent, 1440, 900)
    sid = _chats.send_first(page, "please remember something")
    group = _group(page, "notes")
    pending = group.locator(
        '[data-testid="chat-drawer-notes-pending"] [data-testid="chat-drawer-notes-item"]'
    )
    # No reopen of the panel: the live tool result re-fetched it.
    expect(pending).to_have_count(1, timeout=15000)
    expect(pending).to_contain_text("Live saved note.")
    expect(group.locator('[data-testid="chat-drawer-notes-empty"]')).to_have_count(0)
    # After a rejoin (reload the chat route) the prompt carries it: in use.
    page.reload()
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    expect(
        group.locator('[data-testid="chat-drawer-notes"] [data-testid="chat-drawer-notes-item"]')
    ).to_have_count(1, timeout=10000)
    expect(group.locator('[data-testid="chat-drawer-notes-pending-head"]')).to_have_count(0)


def test_notes_group_empty_404_and_error(notes_app: tuple[SeededApp, Path], page: Page) -> None:
    app, _ = notes_app
    base, agent = app.base_url, app.agent_name
    enable_notes(base, agent)
    _open_pending(page, base, agent, 1440, 900)
    group = _group(page, "notes")
    expect(group.locator('[data-testid="chat-drawer-notes-empty"]')).to_have_text(
        "No notes yet", timeout=8000
    )
    expect(group.locator("a, button")).to_have_count(0)

    # A 404 reads "No notes yet"; any other failure is "Couldn't load".
    page.route(
        "**/api/agents/*/notes",
        lambda route: route.fulfill(
            status=404, body='{"detail": "nope"}', content_type="application/json"
        ),
    )
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    expect(_group(page, "notes").locator("p").first).to_have_text("No notes yet", timeout=8000)
    page.unroute("**/api/agents/*/notes")
    page.route(
        "**/api/agents/*/notes",
        lambda route: route.fulfill(
            status=500, body='{"detail": "boom"}', content_type="application/json"
        ),
    )
    page.reload()
    _chats.start_chat(page, agent)
    expect(_group(page, "notes").locator("p")).to_have_text("Couldn't load", timeout=8000)


def test_a_globally_disabled_current_time_has_no_time_line(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    seed_tool_config(base, "current_time", enabled=False)
    agent = _agent(base, {"name": "Clockless", "provider_config_id": app_with_provider.provider_id})
    _open_pending(page, base, agent, 1440, 900)
    expect(_group(page, "tools").locator("li").first).to_be_visible(timeout=8000)
    items = _group_items(page, "tools")
    assert not any(i.startswith("Time") for i in items), items
