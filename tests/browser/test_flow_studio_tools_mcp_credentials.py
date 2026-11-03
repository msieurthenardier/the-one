"""Browser tests for the per-agent MCP credential section of the agent Tools tab
(sortie 09 leg 3, DD1, DD4, DD10): row states, edit transitions and their focus, the
exact save payload, the list a tile shows, and when a tile tests.

`/test/agent` is mocked with `page.route` and its request bodies are checked; the
PUT bodies are read from the real request, so the write shape is the one the server gets.
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect

SAVE = '[data-testid="save-agent-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
TOOLS_AB = [
    {"name": "tool_a", "description": "tool a", "input_schema": {}},
    {"name": "tool_b", "description": "tool b", "input_schema": {}},
]
OK_CAPS = {"tools": {}}


# ── Helpers ────────────────────────────────────────────────────────────────


def _post(base: str, path: str, payload: dict) -> dict:
    r = httpx.post(f"{base}{path}", json=payload, timeout=8.0, headers=auth_headers_for(base))
    assert r.status_code in (200, 201), f"POST {path} failed: {r.status_code} {r.text}"
    return r.json()


def _get_agent(base: str, name: str) -> dict:
    r = httpx.get(f"{base}/api/agents/{name}", timeout=8.0, headers=auth_headers_for(base))
    assert r.status_code == 200, r.text
    return r.json()


def _seed_keyed(base: str, name: str = "keyed", *, org: bool = True) -> str:
    """An http source with a server header `X-Org: acme` and a blank `X-Api-Key`."""
    config: dict = {"url": "https://example.com/mcp"}
    if org:
        config["headers"] = {"X-Org": "acme"}
    return _post(
        base,
        "/api/mcp-sources",
        {
            "name": name,
            "type": "streamable-http",
            "config": config,
            "secrets": {"X-Api-Key": ""},
        },
    )["id"]


def _seed_plain(base: str, name: str = "plain") -> str:
    return _post(
        base,
        "/api/mcp-sources",
        {
            "name": name,
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )["id"]


def _seed_agent(base: str, name: str, **fields) -> dict:
    return _post(base, "/api/agents", {"name": name, "description": "t", **fields})


def _tid(page: Page, testid: str):
    return page.locator(f'[data-testid="{testid}"]')


def _row(page: Page, sid: str, name: str):
    return _tid(page, f"mcp-agent-cred-row-{sid}-{name}")


def _state(page: Page, sid: str, name: str):
    return _tid(page, f"mcp-agent-cred-state-{sid}-{name}")


def _btn(page: Page, role: str, sid: str, name: str):
    return _tid(page, f"mcp-agent-cred-{role}-{sid}-{name}")


def _status(page: Page, sid: str):
    return _tid(page, f"mcp-agent-cred-status-{sid}")


def _focused_testid(page: Page) -> str | None:
    return page.evaluate("() => document.activeElement && document.activeElement.dataset.testid")


def _mock_agent_test(page: Page, sid: str, bodies: list | None = None, tools=None, payload=None):
    result = payload or {"status": "ok", "tools": tools or TOOLS_AB, "capabilities": OK_CAPS}

    def handler(route):
        if bodies is not None:
            bodies.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(result))

    page.route(f"**/api/mcp-sources/{sid}/test/agent", handler)


def _open_tools(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/tools")
    expect(_tid(page, "tab-tools")).to_have_attribute("aria-selected", "true", timeout=8000)


def _expand(page: Page, sid: str) -> None:
    expand = _tid(page, f"mcp-source-expand-{sid}")
    expect(expand).to_be_visible(timeout=6000)
    expand.click()
    expect(expand).to_have_attribute("aria-expanded", "true", timeout=3000)


def _click_switch(toggle) -> None:
    toggle.locator("xpath=ancestor::label[1]").click()


def _save_put(page: Page, agent: str) -> dict:
    with page.expect_request(
        lambda r: f"/api/agents/{agent}" in r.url and r.method == "PUT"
    ) as info:
        page.locator(SAVE).click()
    return json.loads(info.value.post_data or "{}")


def _credentialed(base: str, name: str, sid: str, source_name: str, entry: dict, **extra) -> None:
    _seed_agent(base, name, mcp_source_ids=[sid], mcp_overrides={source_name: entry}, **extra)


# ── The section and its rows ───────────────────────────────────────────────


@pytest.mark.browser
def test_section_shows_each_row_state_and_never_a_value(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "states-agent",
        sid,
        "keyed",
        {"headers": {"X-Org": "org-secret-value-123"}, "bearer_token": "bearer-secret-value-456"},
    )
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "states-agent")
    _expand(page, sid)

    section = _tid(page, f"mcp-agent-cred-section-{sid}")
    expect(section).to_be_visible()
    expect(section.locator(".section-title")).to_have_text("Headers for this agent")
    # In order: the section, the status line, the tool rows.
    order = page.evaluate(
        """(sid) => {
          const sel = '[data-testid="mcp-source-details-body-' + sid + '"]';
          const body = document.querySelector(sel);
          const names = (el) => Array.from(el.children).map(c => c.className.split(' ')[0]);
          return [names(body), names(body.firstElementChild)];
        }""",
        sid,
    )
    assert order[0] == ["mcp-agent-cred", "", "mcp-tool-group"], order
    assert order[1] == ["editor-section", "mcp-agent-cred-status"], order
    expect(_state(page, sid, "X-Org")).to_have_text("Set for this agent")
    expect(_state(page, sid, "X-Api-Key")).to_have_text("Set per agent · missing")
    expect(_state(page, sid, "Authorization")).to_have_text("Set for this agent")
    # A stored value is never shown, anywhere in the page.
    html = page.content()
    assert "org-secret-value-123" not in html
    assert "bearer-secret-value-456" not in html
    # Each row is a labelled group named by the header, and every button names it.
    expect(_row(page, sid, "X-Org")).to_have_attribute("role", "group")
    expect(_row(page, sid, "X-Org")).to_have_attribute("aria-label", "X-Org")
    expect(_btn(page, "replace", sid, "X-Org")).to_have_attribute("aria-label", "Replace X-Org")
    expect(_btn(page, "reset", sid, "X-Org")).to_have_attribute(
        "aria-label", "Use the server value for X-Org"
    )
    expect(_btn(page, "set", sid, "X-Api-Key")).to_have_attribute(
        "aria-label", "Set X-Api-Key for this agent"
    )
    expect(_btn(page, "reset", sid, "Authorization")).to_have_attribute(
        "aria-label", "Remove Authorization"
    )
    expect(_status(page, sid)).to_have_attribute("role", "status")


@pytest.mark.browser
def test_server_value_row_and_the_signin_row(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "server-agent", mcp_source_ids=[sid])

    def patch_sources(route):
        resp = route.fetch()
        data = resp.json()
        for s in data:
            s["oauth_active"] = True
        route.fulfill(response=resp, json=data)

    page.route("**/api/mcp-sources?*", patch_sources)
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "server-agent")
    _expand(page, sid)
    expect(_state(page, sid, "X-Org")).to_have_text("Server value")
    expect(_btn(page, "set", sid, "X-Org")).to_be_visible()
    expect(_state(page, sid, "Authorization")).to_have_text("Supplied by the server's sign-in")
    expect(_row(page, sid, "Authorization").locator("button")).to_have_count(0)


@pytest.mark.browser
def test_stdio_source_shows_environment(app_clean: str, page: Page) -> None:
    sid = _post(
        app_clean,
        "/api/mcp-sources",
        {
            "name": "stdio-keyed",
            "type": "stdio",
            "config": {"command": "echo", "args": [], "env": {"MODE": "fast"}},
            "secrets": {"API_KEY": ""},
        },
    )["id"]
    _seed_agent(app_clean, "stdio-agent", mcp_source_ids=[sid])
    bodies: list = []
    _mock_agent_test(page, sid, bodies)
    _open_tools(page, app_clean, "stdio-agent")
    _expand(page, sid)
    section = _tid(page, f"mcp-agent-cred-section-{sid}")
    expect(section.locator(".section-title")).to_have_text("Environment for this agent")
    expect(_state(page, sid, "MODE")).to_have_text("Server value")
    expect(_state(page, sid, "API_KEY")).to_have_text("Set per agent · missing")
    expect(_tid(page, f"mcp-agent-cred-add-{sid}")).to_have_text("Add variable")
    expect(_status(page, sid)).to_have_text("Needs a value for API_KEY")
    _btn(page, "set", sid, "API_KEY").click()
    _tid(page, f"mcp-agent-cred-input-{sid}-API_KEY").fill("env-secret-1")
    put = _save_put(page, "stdio-agent")
    assert put["mcp_overrides"] == {"stdio-keyed": {"env": {"API_KEY": "env-secret-1"}}}
    assert "headers" not in put["mcp_overrides"]["stdio-keyed"]


# ── Edit transitions: event, announcement, focus ───────────────────────────


@pytest.mark.browser
def test_set_cancel_and_undo_move_focus_and_announce(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(app_clean, "focus-agent", sid, "keyed", {"headers": {"X-Org": "org-val-0001"}})
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "focus-agent")
    _expand(page, sid)
    live = _tid(page, f"mcp-agent-cred-live-{sid}")

    # Set for this agent -> the input takes focus; Cancel returns to the button.
    _btn(page, "set", sid, "X-Api-Key").click()
    inp = _tid(page, f"mcp-agent-cred-input-{sid}-X-Api-Key")
    expect(inp).to_be_focused()
    expect(inp).to_have_attribute("aria-label", "Value for X-Api-Key")
    expect(inp).to_have_attribute("type", "password")
    expect(_btn(page, "cancel", sid, "X-Api-Key")).to_have_attribute(
        "aria-label", "Cancel editing X-Api-Key"
    )
    expect(_tid(page, f"mcp-agent-cred-reveal-{sid}-X-Api-Key")).to_have_attribute(
        "aria-label", "Show value for X-Api-Key"
    )
    inp.fill("typed-value-1")
    expect(page.locator(SAVE)).to_be_enabled()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    _btn(page, "cancel", sid, "X-Api-Key").click()
    expect(_btn(page, "set", sid, "X-Api-Key")).to_be_focused()
    expect(page.locator(SAVE)).to_be_disabled()
    expect(live).to_have_text("X-Api-Key unchanged")

    # Erasing the typed value while editing a stored name leaves the form clean.
    _btn(page, "replace", sid, "X-Org").click()
    expect(_tid(page, f"mcp-agent-cred-input-{sid}-X-Org")).to_be_focused()
    _tid(page, f"mcp-agent-cred-input-{sid}-X-Org").fill("abc")
    expect(page.locator(SAVE)).to_be_enabled()
    _tid(page, f"mcp-agent-cred-input-{sid}-X-Org").fill("")
    expect(page.locator(SAVE)).to_be_disabled()
    _btn(page, "cancel", sid, "X-Org").click()
    expect(_btn(page, "replace", sid, "X-Org")).to_be_focused()

    # Use server value -> "Server value · on save", focus on Undo; Undo restores.
    _btn(page, "reset", sid, "X-Org").click()
    expect(_state(page, sid, "X-Org")).to_have_text("Server value · on save")
    expect(_btn(page, "undo", sid, "X-Org")).to_be_focused()
    expect(live).to_have_text("X-Org will use the server value when you save")
    expect(page.locator(SAVE)).to_be_enabled()
    _btn(page, "undo", sid, "X-Org").click()
    expect(_state(page, sid, "X-Org")).to_have_text("Set for this agent")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(live).to_have_text("X-Org restored")


@pytest.mark.browser
def test_add_header_focus_cancel_and_empty_row(app_clean: str, page: Page) -> None:
    sid = _seed_plain(app_clean)
    _seed_agent(app_clean, "add-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "add-agent")
    _expand(page, sid)
    expect(_tid(page, f"mcp-agent-cred-empty-{sid}")).to_have_text("This server sets no headers.")

    add = _tid(page, f"mcp-agent-cred-add-{sid}")
    add.click()
    name_input = _tid(page, f"mcp-agent-cred-name-{sid}-new-1")
    expect(name_input).to_be_focused()
    expect(_tid(page, f"mcp-agent-cred-empty-{sid}")).to_have_count(0)
    # An empty new row adds nothing: the form stays clean.
    expect(page.locator(SAVE)).to_be_disabled()
    name_input.fill("X-New")
    expect(page.locator(SAVE)).to_be_disabled()
    _btn(page, "cancel", sid, "new-1").click()
    expect(add).to_be_focused()
    expect(_row(page, sid, "new-1")).to_have_count(0)

    add.click()
    _tid(page, f"mcp-agent-cred-name-{sid}-new-2").fill("X-New")
    _tid(page, f"mcp-agent-cred-input-{sid}-new-2").fill("new-secret-1")
    put = _save_put(page, "add-agent")
    assert put["mcp_overrides"] == {"plain": {"headers": {"X-New": "new-secret-1"}}}


# ── The exact PUT body ─────────────────────────────────────────────────────


@pytest.mark.browser
def test_put_bodies_mask_unchanged_names_and_leave_removed_ones_out(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "put-agent",
        sid,
        "keyed",
        {"headers": {"X-Org": "org-val-0001", "X-Api-Key": "key-val-00002"}},
    )
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "put-agent")
    _expand(page, sid)
    # Replace one: the other keeps its mask.
    _btn(page, "replace", sid, "X-Api-Key").click()
    _tid(page, f"mcp-agent-cred-input-{sid}-X-Api-Key").fill("brand-new-key-3")
    put = _save_put(page, "put-agent")
    assert put["mcp_overrides"]["keyed"]["headers"] == {
        "X-Org": "__MASKED__",
        "X-Api-Key": "brand-new-key-3",
    }
    assert "bearer_token" not in put["mcp_overrides"]["keyed"]
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)

    # Remove one: it is left out.
    _btn(page, "reset", sid, "X-Org").click()
    put = _save_put(page, "put-agent")
    assert put["mcp_overrides"]["keyed"]["headers"] == {"X-Api-Key": "__MASKED__"}
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)

    # Remove the last: headers is null.
    _btn(page, "reset", sid, "X-Api-Key").click()
    put = _save_put(page, "put-agent")
    assert put["mcp_overrides"]["keyed"]["headers"] is None
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    stored = (_get_agent(app_clean, "put-agent")["mcp_overrides"] or {}).get("keyed") or {}
    assert not stored.get("headers")


@pytest.mark.browser
def test_authorization_row_clears_a_stored_bearer_token(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "bearer-agent",
        sid,
        "keyed",
        {"bearer_token": "bearer-token-value-1"},
    )
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "bearer-agent")
    _expand(page, sid)
    expect(_state(page, sid, "Authorization")).to_have_text("Set for this agent")
    _btn(page, "replace", sid, "Authorization").click()
    _tid(page, f"mcp-agent-cred-input-{sid}-Authorization").fill("Bearer replaced-token-2")
    put = _save_put(page, "bearer-agent")
    assert put["mcp_overrides"]["keyed"]["headers"] == {"Authorization": "Bearer replaced-token-2"}
    assert put["mcp_overrides"]["keyed"]["bearer_token"] is None
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)

    # Removing it later leaves no Authorization at all.
    _btn(page, "reset", sid, "Authorization").click()
    put = _save_put(page, "bearer-agent")
    assert put["mcp_overrides"]["keyed"]["headers"] is None


@pytest.mark.browser
def test_stored_spelling_is_sent_for_an_unchanged_or_replaced_name(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "case-agent",
        sid,
        "keyed",
        {"headers": {"x-api-key": "lowercase-key-0001", "x-org": "lowercase-org-0002"}},
    )
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "case-agent")
    _expand(page, sid)
    # One row per name, the server's spelling on the row.
    expect(_row(page, sid, "X-Api-Key")).to_have_count(1)
    expect(_state(page, sid, "X-Api-Key")).to_have_text("Set for this agent")
    _btn(page, "replace", sid, "X-Api-Key").click()
    _tid(page, f"mcp-agent-cred-input-{sid}-X-Api-Key").fill("spelled-new-value-1")
    put = _save_put(page, "case-agent")
    assert put["mcp_overrides"]["keyed"]["headers"] == {
        "x-api-key": "spelled-new-value-1",
        "x-org": "__MASKED__",
    }


@pytest.mark.browser
def test_open_and_close_stays_clean(app_clean: str, page: Page) -> None:
    sid = _seed_plain(app_clean, "clean-src")
    _seed_agent(app_clean, "clean-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "clean-agent")
    expect(page.locator(SAVE)).to_be_disabled()
    expand = _tid(page, f"mcp-source-expand-{sid}")
    _expand(page, sid)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_be_visible(timeout=6000)
    expect(page.locator(SAVE)).to_be_disabled()
    expand.click()
    expect(expand).to_have_attribute("aria-expanded", "false")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(UNSAVED)).to_have_text("")
    # A later dirty check (an edit and its undo elsewhere in the form) still reads clean:
    # loading the rows did not turn "no entry" into "{}" in the saved payload.
    page.locator('[data-testid="tab-general"]').click()
    desc = page.locator('[data-field="description"]')
    original = desc.input_value()
    desc.fill("x")
    expect(page.locator(SAVE)).to_be_enabled()
    desc.fill(original)
    expect(page.locator(SAVE)).to_be_disabled()


@pytest.mark.browser
def test_a_credential_edit_on_an_unloaded_tile_keeps_the_stored_filters(
    app_clean: str, page: Page
) -> None:
    kid = _seed_keyed(app_clean, "filtered")
    _seed_agent(
        app_clean,
        "filter-agent",
        mcp_source_ids=[kid],
        mcp_overrides={"filtered": {"disabled_tools": ["tool_b"]}},
    )
    _mock_agent_test(page, kid)
    _open_tools(page, app_clean, "filter-agent")
    _expand(page, kid)
    expect(_status(page, kid)).to_have_text("Needs a value for X-Api-Key")
    expect(_tid(page, f"mcp-tool-toggle-{kid}-tool_a")).to_have_count(0)
    _btn(page, "set", kid, "X-Api-Key").click()
    _tid(page, f"mcp-agent-cred-input-{kid}-X-Api-Key").fill("filter-key-0001")
    put = _save_put(page, "filter-agent")
    assert put["mcp_overrides"]["filtered"] == {
        "disabled_tools": ["tool_b"],
        "headers": {"X-Api-Key": "filter-key-0001"},
    }
    stored = _get_agent(app_clean, "filter-agent")["mcp_overrides"]["filtered"]
    assert stored["disabled_tools"] == ["tool_b"]


# ── When a tile tests, and which list it shows ─────────────────────────────


@pytest.mark.browser
def test_switch_on_tests_at_once_with_the_unsaved_values(app_clean: str, page: Page) -> None:
    sid = _seed_plain(app_clean, "switch-src")
    _seed_agent(app_clean, "switch-agent")
    bodies: list = []
    _mock_agent_test(page, sid, bodies)
    _open_tools(page, app_clean, "switch-agent")
    toggle = _tid(page, f"mcp-source-toggle-{sid}")
    _click_switch(toggle)
    expect(_tid(page, f"mcp-source-expand-{sid}")).to_have_attribute("aria-expanded", "true")
    expect(_status(page, sid)).to_have_text("Connected · 2 tools", timeout=6000)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_be_visible()
    assert bodies == [{"agent": "switch-agent", "overrides": None}], bodies
    assert _focused_testid(page) == f"mcp-source-toggle-{sid}"

    # A second expand never tests again.
    expand = _tid(page, f"mcp-source-expand-{sid}")
    expand.click()
    expand.click()
    page.wait_for_timeout(300)
    assert len(bodies) == 1, bodies


@pytest.mark.browser
def test_switch_on_reports_a_missing_value_without_a_request(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "needs-agent")
    bodies: list = []
    _mock_agent_test(page, sid, bodies)
    _open_tools(page, app_clean, "needs-agent")
    _click_switch(_tid(page, f"mcp-source-toggle-{sid}"))
    expect(_status(page, sid)).to_have_text("Needs a value for X-Api-Key")
    expect(_state(page, sid, "X-Api-Key")).to_have_text("Set per agent · missing")
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_have_count(0)
    page.wait_for_timeout(300)
    assert bodies == []

    # Typing the value, then Test, sends the unsaved values.
    _btn(page, "set", sid, "X-Api-Key").click()
    _tid(page, f"mcp-agent-cred-input-{sid}-X-Api-Key").fill("typed-key-0001")
    _tid(page, f"mcp-agent-cred-test-{sid}").click()
    expect(_status(page, sid)).to_have_text(
        "Connected with this agent's values · 2 tools", timeout=6000
    )
    assert bodies == [
        {"agent": "needs-agent", "overrides": {"headers": {"X-Api-Key": "typed-key-0001"}}}
    ], bodies
    # Refresh forces a new request, too.
    _tid(page, f"mcp-refresh-tools-btn-{sid}").click()
    expect(_status(page, sid)).to_have_text(
        "Connected with this agent's values · 2 tools", timeout=6000
    )
    assert len(bodies) == 2


@pytest.mark.browser
def test_a_stale_result_is_dropped_after_off_and_on(app_clean: str, page: Page) -> None:
    sid = _seed_plain(app_clean, "stale-src")
    _seed_agent(app_clean, "stale-agent")
    held: list = []
    calls = {"n": 0}

    def handler(route):
        calls["n"] += 1
        if calls["n"] == 1:
            held.append(route)  # the first result stays in flight
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "ok",
                    "tools": [{"name": "fresh", "description": "f", "input_schema": {}}],
                    "capabilities": OK_CAPS,
                }
            ),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/agent", handler)
    _open_tools(page, app_clean, "stale-agent")
    toggle = _tid(page, f"mcp-source-toggle-{sid}")
    _click_switch(toggle)
    expect(_status(page, sid)).to_have_text("Testing…")
    # Off: a result still in flight is dropped.
    _click_switch(toggle)
    held[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"status": "ok", "tools": TOOLS_AB, "capabilities": OK_CAPS}),
    )
    page.wait_for_timeout(500)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_have_count(0)
    expect(_status(page, sid)).not_to_contain_text("Connected")
    # On again: a new test; only its result is shown.
    _click_switch(toggle)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-fresh")).to_be_visible(timeout=6000)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_have_count(0)
    expect(_status(page, sid)).to_have_text("Connected · 1 tool")


@pytest.mark.browser
def test_a_credentialed_agent_is_never_shown_the_shared_list(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(app_clean, "own-agent", sid, "keyed", {"headers": {"X-Api-Key": "own-key-0001"}})
    _seed_agent(app_clean, "shared-agent", mcp_source_ids=[sid])
    bodies: list = []
    _mock_agent_test(
        page, sid, bodies, tools=[{"name": "own_tool", "description": "o", "input_schema": {}}]
    )

    def with_shared_cache(route):
        resp = route.fetch()
        data = resp.json()
        for s in data:
            s.setdefault("config", {})["_cache"] = {
                "tools": [{"name": "shared_tool", "description": "s", "input_schema": {}}]
            }
        route.fulfill(response=resp, json=data)

    page.route("**/api/mcp-sources?*", with_shared_cache)

    # A plain agent sees the shared list, without a request.
    _open_tools(page, app_clean, "shared-agent")
    _expand(page, sid)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-shared_tool")).to_be_visible(timeout=6000)
    assert bodies == []

    # A credentialed agent with no list of its own tests on the first expand and sees
    # only its own tools.
    _open_tools(page, app_clean, "own-agent")
    expect(_status(page, sid)).to_have_text("Not listed with this agent's values yet")
    _expand(page, sid)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-own_tool")).to_be_visible(timeout=6000)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-shared_tool")).to_have_count(0)
    assert bodies == [{"agent": "own-agent", "overrides": None}], bodies


@pytest.mark.browser
def test_a_stored_per_agent_list_shows_without_a_request_and_survives_a_save(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    entry = {"headers": {"X-Api-Key": "cache-key-0001"}}
    _credentialed(app_clean, "cache-agent", sid, "keyed", entry)
    cache = {sid: {"tools": TOOLS_AB, "fetched_at": "2026-11-03T10:00:00+00:00"}}
    bodies: list = []
    _mock_agent_test(page, sid, bodies)

    def with_cache(route):
        resp = route.fetch()
        data = resp.json()
        data["mcp_tool_cache"] = cache
        route.fulfill(response=resp, json=data)

    def route_agent(route):
        if route.request.method in ("GET", "PUT"):
            with_cache(route)
        else:
            route.continue_()

    page.route("**/api/agents/cache-agent", route_agent)
    _open_tools(page, app_clean, "cache-agent")
    tile = _tid(page, f"mcp-source-row-{sid}")
    expect(tile.locator(".ui-group-tile-chip").nth(0)).to_have_text("2 / 2 enabled", timeout=6000)
    expect(_status(page, sid)).to_have_text("Last checked with this agent's values · 2 tools")

    # A save of an unrelated field keeps the list (the list route has no cache). The tile
    # has not been opened, so its count comes from the cache, not from loaded rows.
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("changed description")
    _save_put(page, "cache-agent")
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    page.locator('[data-testid="tab-tools"]').click()
    expect(tile.locator(".ui-group-tile-chip").nth(0)).to_have_text("2 / 2 enabled")
    expect(_status(page, sid)).to_have_text("Last checked with this agent's values · 2 tools")
    _expand(page, sid)
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_be_visible()
    assert bodies == []


@pytest.mark.browser
def test_save_retests_a_changed_tile_with_the_saved_values(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "retest-agent", mcp_source_ids=[sid])
    bodies: list = []
    _mock_agent_test(page, sid, bodies)
    _open_tools(page, app_clean, "retest-agent")
    _expand(page, sid)
    expect(_status(page, sid)).to_have_text("Needs a value for X-Api-Key")
    _btn(page, "set", sid, "X-Api-Key").click()
    _tid(page, f"mcp-agent-cred-input-{sid}-X-Api-Key").fill("retest-key-0001")
    page.locator(SAVE).click()
    expect(_state(page, sid, "X-Api-Key")).to_have_text("Set for this agent", timeout=8000)
    expect(_status(page, sid)).to_have_text(
        "Connected with this agent's values · 2 tools", timeout=8000
    )
    assert bodies == [{"agent": "retest-agent", "overrides": None}], bodies
    expect(page.locator(SAVE)).to_be_disabled()
