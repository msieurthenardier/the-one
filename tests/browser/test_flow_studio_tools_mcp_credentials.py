"""Browser tests for the per-agent MCP credential section of the agent Tools tab
(sortie 09 leg 6, DD12): the locked table of effective headers, Override and Cancel, the
tile's own Save through the targeted route, the list a tile shows and when it tests.

`/test/agent` is mocked with `page.route` and its request bodies are checked; the PUT
bodies are read from the real request, so the write shape is the one the server gets.
Rows are addressed by the table's `data-name` (server rows) or by position.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect

SAVE = '[data-testid="save-agent-btn"]'
CANCEL = '[data-testid="cancel-agent-btn"]'
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


def _credentialed(base: str, name: str, sid: str, source_name: str, entry: dict, **extra) -> None:
    _seed_agent(base, name, mcp_source_ids=[sid], mcp_overrides={source_name: entry}, **extra)


def _tid(page: Page, testid: str):
    return page.locator(f'[data-testid="{testid}"]')


def _table(page: Page, sid: str):
    return _tid(page, f"mcp-agent-cred-table-{sid}")


def _trs(page: Page, sid: str):
    return _table(page, sid).locator("tr.ui-kv-row")


def _tr(page: Page, sid: str, name: str):
    """A server row (they carry `data-name`)."""
    return _table(page, sid).locator(f'tr.ui-kv-row[data-name="{name}"]')


def _key(tr):
    return tr.locator("td").nth(0).locator("input")


def _value(tr):
    return tr.locator("td").nth(1).locator("input").first


def _toggle(tr):
    return tr.locator("td").nth(2).locator("input")


def _trash(tr):
    return tr.get_by_role("button", name=re.compile(r"^Remove"))


def _pill(tr):
    return tr.locator(".ui-kv-marker")


def _status(page: Page, sid: str):
    return _tid(page, f"mcp-agent-cred-status-{sid}")


def _btn(page: Page, role: str, sid: str):
    return _tid(page, f"mcp-agent-cred-{role}-{sid}")


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


def _tile_save(page: Page, sid: str) -> dict:
    """Click the tile's Save; return the targeted route's request body."""
    with page.expect_request(
        lambda r: (
            r.method == "PUT" and "/mcp-overrides/" in r.url and r.url.endswith("/credentials")
        )
    ) as info:
        _btn(page, "save", sid).click()
    return json.loads(info.value.post_data or "{}")


def _main_save_put(page: Page, agent: str) -> dict:
    with page.expect_request(
        lambda r: f"/api/agents/{agent}" in r.url and r.method == "PUT" and "/mcp-" not in r.url
    ) as info:
        page.locator(SAVE).click()
    return json.loads(info.value.post_data or "{}")


# ── The locked view ────────────────────────────────────────────────────────


@pytest.mark.browser
def test_locked_table_shows_effective_rows_pills_and_never_a_value(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "locked-agent",
        sid,
        "keyed",
        {
            "headers": {"X-Org": "org-secret-value-123", "X-Extra": "extra-clear-1"},
            "bearer_token": "bearer-secret-value-456",
            "plain_names": ["X-Extra"],
        },
    )
    stored = _get_agent(app_clean, "locked-agent")["mcp_overrides"]["keyed"]
    org_mask = stored["headers"]["X-Org"]
    bearer_mask = stored["bearer_token"]
    assert org_mask != "org-secret-value-123"
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "locked-agent")
    _expand(page, sid)

    section = _tid(page, f"mcp-agent-cred-section-{sid}")
    expect(section.locator(".section-title")).to_have_text("Headers")
    # No button in the section header; the action row is status, Override, Test.
    expect(section.locator(".section-title").locator("xpath=..").locator("button")).to_have_count(0)
    expect(_btn(page, "override", sid)).to_have_text("Override headers")
    expect(_btn(page, "test", sid)).to_be_visible()
    expect(_btn(page, "save", sid)).to_be_hidden()
    expect(_btn(page, "cancel", sid)).to_be_hidden()
    expect(page.get_by_role("button", name=re.compile("Refresh"))).to_have_count(0)

    # Rows: the server's names in its order, then this agent's own A-Z.
    expect(_trs(page, sid)).to_have_count(4)
    keys = [_key(_trs(page, sid).nth(i)).input_value() for i in range(4)]
    assert keys == ["X-Org", "X-Api-Key", "Authorization", "X-Extra"], keys
    org, api, auth, extra = (_trs(page, sid).nth(i) for i in range(4))
    expect(_value(org)).to_have_value(org_mask)
    expect(_value(api)).to_have_value("")
    expect(_value(api)).to_have_attribute("placeholder", "value")
    expect(_value(auth)).to_have_value(bearer_mask)
    expect(_value(extra)).to_have_value("extra-clear-1")
    # The "overridden" pill on the rows this agent overrides, none on the server's own.
    for tr in (org, auth, extra):
        expect(_pill(tr)).to_have_text("overridden")
        expect(_pill(tr)).to_be_visible()
    expect(_pill(api)).to_be_hidden()
    # Read-only: no eye, no Sensitive column, no trash, no Add row.
    expect(_table(page, sid).locator("input")).to_have_count(8)
    assert all(
        _table(page, sid).locator("input").nth(i).get_attribute("readonly") is not None
        for i in range(8)
    )
    expect(_table(page, sid).get_by_role("button")).to_have_count(0)
    expect(_table(page, sid).get_by_role("columnheader")).to_have_count(2)
    expect(_tid(page, f"mcp-agent-cred-add-{sid}")).to_have_count(0)
    # A stored sensitive value is never shown, anywhere in the page.
    html = page.content()
    for secret in ("org-secret-value-123", "bearer-secret-value-456"):
        assert secret not in html
        assert secret not in page.evaluate(
            "() => Array.from(document.querySelectorAll('input')).map(i => i.value).join('|')"
        )


@pytest.mark.browser
def test_stdio_source_shows_environment_variables(app_clean: str, page: Page) -> None:
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
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "stdio-agent")
    _expand(page, sid)
    expect(_tid(page, f"mcp-agent-cred-section-{sid}").locator(".section-title")).to_have_text(
        "Environment variables"
    )
    expect(_btn(page, "override", sid)).to_have_text("Override environment variables")
    expect(_trs(page, sid)).to_have_count(2)
    expect(_value(_tr(page, sid, "MODE"))).to_have_value("fast")
    expect(_status(page, sid)).to_have_text("Needs a value for API_KEY")
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "API_KEY")).fill("env-secret-1")
    body = _tile_save(page, sid)
    assert body == {"env": {"API_KEY": "env-secret-1"}, "plain_names": None}


@pytest.mark.browser
def test_signin_source_shows_no_authorization_row_only_a_note(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "signin-agent", mcp_source_ids=[sid])

    def patch_sources(route):
        resp = route.fetch()
        data = resp.json()
        for s in data:
            s["oauth_active"] = True
        route.fulfill(response=resp, json=data)

    page.route("**/api/mcp-sources?*", patch_sources)
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "signin-agent")
    _expand(page, sid)
    note = _tid(page, f"mcp-agent-cred-oauth-note-{sid}")
    expect(note).to_have_text("Authorization is supplied by this server's sign-in.")
    expect(_trs(page, sid)).to_have_count(2)
    expect(_tr(page, sid, "Authorization")).to_have_count(0)
    _btn(page, "override", sid).click()
    expect(_trs(page, sid)).to_have_count(2)
    expect(_tr(page, sid, "Authorization")).to_have_count(0)
    expect(note).to_be_visible()


# ── Override and Cancel ────────────────────────────────────────────────────


@pytest.mark.browser
def test_override_unlocks_the_library_table_and_cancel_restores_the_baseline(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(app_clean, "focus-agent", sid, "keyed", {"headers": {"X-Org": "org-val-000001"}})
    org_mask = _get_agent(app_clean, "focus-agent")["mcp_overrides"]["keyed"]["headers"]["X-Org"]
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "focus-agent")
    _expand(page, sid)
    live = _tid(page, f"mcp-agent-cred-live-{sid}")

    _btn(page, "override", sid).click()
    # Cancel, Save (primary) and Test; Override is gone. Focus is on the first value input.
    expect(_btn(page, "override", sid)).to_be_hidden()
    expect(_btn(page, "cancel", sid)).to_be_visible()
    expect(_btn(page, "save", sid)).to_be_visible()
    expect(_btn(page, "save", sid)).to_be_disabled()
    expect(_btn(page, "test", sid)).to_be_visible()
    org, api = _tr(page, sid, "X-Org"), _tr(page, sid, "X-Api-Key")
    expect(_value(org)).to_be_focused()
    expect(live).to_have_text("Editing headers for this agent")
    # The Library table's columns, Key, Value, Sensitive and the remove column; Add row.
    expect(_table(page, sid).get_by_role("columnheader")).to_have_count(4)
    expect(_tid(page, f"mcp-agent-cred-add-{sid}")).to_have_text("+ Add row")
    # Server keys are read-only; an overridden row shows its mask and can be removed, a server
    # row with no override starts empty with a disabled trash.
    expect(_key(org)).not_to_be_editable()
    expect(_key(api)).not_to_be_editable()
    expect(_value(org)).to_have_value(org_mask)
    expect(_value(api)).to_have_value("")
    expect(_value(api)).to_have_attribute("placeholder", "value")
    expect(_trash(org)).to_be_enabled()
    expect(_trash(api)).to_be_disabled()
    expect(_toggle(org)).to_be_checked()

    _value(api).fill("typed-value-0001")
    expect(_btn(page, "save", sid)).to_be_enabled()
    expect(_pill(api)).to_be_visible()
    expect(_trash(api)).to_be_enabled()
    # The tile's edits never reach the editor's own dirty state.
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(UNSAVED)).to_have_text("")

    _btn(page, "cancel", sid).click()
    expect(_btn(page, "override", sid)).to_be_focused()
    expect(live).to_have_text("Changes discarded")
    expect(_btn(page, "save", sid)).to_be_hidden()
    expect(_value(_tr(page, sid, "X-Api-Key"))).to_have_value("")
    expect(_pill(_tr(page, sid, "X-Api-Key"))).to_be_hidden()
    expect(_value(_tr(page, sid, "X-Org"))).to_have_value(org_mask)
    # Unlocking again starts from the baseline, and editing then undoing reads clean.
    _btn(page, "override", sid).click()
    expect(_value(_tr(page, sid, "X-Api-Key"))).to_have_value("")
    _value(_tr(page, sid, "X-Api-Key")).fill("abc")
    expect(_btn(page, "save", sid)).to_be_enabled()
    _value(_tr(page, sid, "X-Api-Key")).fill("")
    expect(_btn(page, "save", sid)).to_be_disabled()


@pytest.mark.browser
def test_trash_on_an_overridden_server_row_returns_to_the_server_value(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "trash-agent",
        sid,
        "keyed",
        {"headers": {"X-Org": "org-val-000001", "X-Own": "own-val-0000001"}},
    )
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "trash-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    org = _tr(page, sid, "X-Org")
    expect(_trs(page, sid)).to_have_count(3)
    # Server row: the row stays at the server's value with a disabled trash; focus moves to
    # its value input.
    _trash(org).click()
    expect(_trs(page, sid)).to_have_count(3)
    expect(_value(org)).to_have_value("acme")   # the server's own value, not empty (H6)
    expect(_toggle(org)).not_to_be_checked()
    expect(_trash(org)).to_be_disabled()
    expect(_pill(org)).to_be_hidden()
    expect(_value(org)).to_be_focused()
    # Agent-only row: removed.
    own = _trs(page, sid).nth(2)
    expect(_key(own)).to_have_value("X-Own")
    _trash(own).click()
    expect(_trs(page, sid)).to_have_count(2)
    body = _tile_save(page, sid)
    assert body == {"headers": None, "plain_names": None}


@pytest.mark.browser
def test_add_row_is_sensitive_by_default_and_duplicates_block_save(
    app_clean: str, page: Page
) -> None:
    sid = _seed_plain(app_clean)
    _seed_agent(app_clean, "add-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "add-agent")
    _expand(page, sid)
    expect(_trs(page, sid)).to_have_count(0)
    _btn(page, "override", sid).click()
    add = _tid(page, f"mcp-agent-cred-add-{sid}")
    add.click()
    row = _trs(page, sid).nth(0)
    expect(_key(row)).to_be_focused()
    expect(_toggle(row)).to_be_checked()
    _key(row).fill("X-New")
    _value(row).fill("new-secret-001")
    add.click()
    row2 = _trs(page, sid).nth(1)
    _key(row2).fill("x-new")
    _value(row2).fill("other-secret-02")
    expect(row2).to_contain_text("This name is already in the table.")
    expect(_btn(page, "save", sid)).to_be_disabled()
    _key(row2).fill("X-Other")
    expect(row2).not_to_contain_text("This name is already in the table.")
    expect(_btn(page, "save", sid)).to_be_enabled()
    body = _tile_save(page, sid)
    assert body == {
        "headers": {"X-New": "new-secret-001", "X-Other": "other-secret-02"},
        "plain_names": None,
    }


# ── Authorization ──────────────────────────────────────────────────────────


@pytest.mark.browser
def test_authorization_keeps_an_editable_value_with_the_toggle_locked_on(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(app_clean, "bearer-agent", sid, "keyed", {"bearer_token": "bearer-token-value-1"})
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "bearer-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    auth = _trs(page, sid).nth(2)
    expect(_key(auth)).to_have_value("Authorization")
    expect(_toggle(auth)).to_be_checked()
    expect(_toggle(auth)).to_be_disabled()
    expect(_value(auth)).to_be_editable()
    # Unchanged: a bearer is kept (nothing sent for it).
    _value(_tr(page, sid, "X-Api-Key")).fill("api-key-value-01")
    body = _tile_save(page, sid)
    assert body == {"headers": {"X-Api-Key": "api-key-value-01"}, "plain_names": None}
    # Replace it: the new value goes in headers and the stored bearer is cleared.
    _btn(page, "override", sid).click()
    auth = _trs(page, sid).nth(2)
    _value(auth).fill("Bearer replaced-token-2")
    body = _tile_save(page, sid)
    assert body["headers"]["Authorization"] == "Bearer replaced-token-2"
    assert body["bearer_token"] is None
    assert body["plain_names"] is None


@pytest.mark.browser
def test_a_typed_authorization_key_locks_its_toggle(app_clean: str, page: Page) -> None:
    sid = _seed_plain(app_clean)
    _seed_agent(app_clean, "auth-typed-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "auth-typed-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _tid(page, f"mcp-agent-cred-add-{sid}").click()
    row = _trs(page, sid).nth(0)
    _key(row).fill("X-Thing")
    expect(_toggle(row)).to_be_enabled()
    _key(row).fill("authorization")
    expect(_toggle(row)).to_be_disabled()
    expect(_toggle(row)).to_be_checked()
    _key(row).fill("X-Thing")
    expect(_toggle(row)).to_be_enabled()


# ── The tile's Save ────────────────────────────────────────────────────────


@pytest.mark.browser
def test_set_a_value_then_save_writes_through_the_targeted_route_and_retests(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "set-agent", mcp_source_ids=[sid])
    bodies: list = []
    _mock_agent_test(page, sid, bodies)
    _open_tools(page, app_clean, "set-agent")
    _expand(page, sid)
    expect(_status(page, sid)).to_have_text("Needs a value for X-Api-Key")
    assert bodies == []
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("set-key-value-0001")
    body = _tile_save(page, sid)
    assert body == {"headers": {"X-Api-Key": "set-key-value-0001"}, "plain_names": None}
    # Locked again, focus on Override, announced, the row overridden, the value masked.
    live = _tid(page, f"mcp-agent-cred-live-{sid}")
    expect(_btn(page, "override", sid)).to_be_focused(timeout=8000)
    expect(live).to_have_text("Saved")
    expect(_btn(page, "save", sid)).to_be_hidden()
    api = _tr(page, sid, "X-Api-Key")
    expect(_pill(api)).to_be_visible()
    expect(_value(api)).not_to_have_value("set-key-value-0001")
    expect(_value(api)).not_to_have_value("")
    # One re-test with the saved values (overrides: null), then its result.
    expect(_status(page, sid)).to_have_text(
        "Connected with this agent's values · 2 tools", timeout=8000
    )
    assert bodies == [{"agent": "set-agent", "overrides": None}], bodies
    stored = _get_agent(app_clean, "set-agent")["mcp_overrides"]["keyed"]
    assert list(stored["headers"]) == ["X-Api-Key"]
    assert "set-key-value-0001" not in page.content()
    # The editor's own Save was never involved.
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(UNSAVED)).to_have_text("")


@pytest.mark.browser
def test_a_non_sensitive_value_round_trips_in_clear(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "plain-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "plain-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    org = _tr(page, sid, "X-Org")
    _value(org).fill("acme-clear-text")
    _toggle(org).uncheck()  # a typed value stays (only a stored mask is cleared)
    expect(_value(org)).to_have_value("acme-clear-text")
    body = _tile_save(page, sid)
    assert body == {"headers": {"X-Org": "acme-clear-text"}, "plain_names": ["X-Org"]}
    expect(_value(_tr(page, sid, "X-Org"))).to_have_value("acme-clear-text")
    page.reload()  # the route names the source, so its tile opens by itself
    expect(_tid(page, f"mcp-source-expand-{sid}")).to_have_attribute(
        "aria-expanded", "true", timeout=8000
    )
    expect(_value(_tr(page, sid, "X-Org"))).to_have_value("acme-clear-text")
    _btn(page, "override", sid).click()
    expect(_toggle(_tr(page, sid, "X-Org"))).not_to_be_checked()


@pytest.mark.browser
def test_a_tile_save_keeps_an_unsaved_attach_and_tool_check_and_the_main_save_sends_no_credentials(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "survive-agent")
    bodies: list = []
    _mock_agent_test(page, sid, bodies)
    _open_tools(page, app_clean, "survive-agent")
    toggle = _tid(page, f"mcp-source-toggle-{sid}")
    _click_switch(toggle)  # an unsaved attach: it expands and finds a value missing
    expect(toggle).to_be_checked()
    expect(_status(page, sid)).to_have_text("Needs a value for X-Api-Key")
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("survive-key-0001")
    _btn(page, "test", sid).click()
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_be_visible(timeout=8000)
    assert bodies[-1] == {
        "agent": "survive-agent",
        "overrides": {"headers": {"X-Api-Key": "survive-key-0001"}, "plain_names": None},
    }, bodies
    tool_a = _tid(page, f"mcp-tool-toggle-{sid}-tool_a")
    tool_a.uncheck()  # an unsaved tool edit
    expect(page.locator(SAVE)).to_be_enabled()

    _tile_save(page, sid)
    expect(_btn(page, "override", sid)).to_be_focused(timeout=8000)
    # Both unsaved edits survive the tile's Save, and the main Save is still pending.
    expect(toggle).to_be_checked()
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).not_to_be_checked()
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_b")).to_be_checked()
    expect(page.locator(SAVE)).to_be_enabled()
    expect(_status(page, sid)).to_have_text(
        "Connected with this agent's values · 2 tools", timeout=8000
    )
    assert _get_agent(app_clean, "survive-agent")["mcp_source_ids"] == []

    # The main Save carries the attach and the tool filter, and no credential key.
    put = _main_save_put(page, "survive-agent")
    assert sid in put["mcp_source_ids"]
    assert put["mcp_overrides"] == {"keyed": {"disabled_tools": ["tool_a"]}}, put["mcp_overrides"]
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    stored = _get_agent(app_clean, "survive-agent")["mcp_overrides"]["keyed"]
    assert stored["disabled_tools"] == ["tool_a"]
    assert list(stored["headers"]) == ["X-Api-Key"]  # kept by the server's omitted-keeps rule


@pytest.mark.browser
def test_the_main_save_of_a_credentialed_agent_keeps_its_credentials(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "main-agent",
        sid,
        "keyed",
        {"headers": {"X-Api-Key": "main-key-value-1"}, "disabled_tools": ["tool_b"]},
    )
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "main-agent")
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("changed description")
    put = _main_save_put(page, "main-agent")
    for entry in (put.get("mcp_overrides") or {}).values():
        assert "headers" not in entry and "env" not in entry and "bearer_token" not in entry
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    stored = _get_agent(app_clean, "main-agent")["mcp_overrides"]["keyed"]
    assert list(stored["headers"]) == ["X-Api-Key"]
    assert stored["disabled_tools"] == ["tool_b"]


@pytest.mark.browser
@pytest.mark.parametrize("action", ["save", "cancel"])
def test_the_main_save_and_cancel_leave_an_unsaved_unlocked_tile_alone(
    app_clean: str, page: Page, action: str
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, f"main-{action}-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, f"main-{action}-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("unsaved-main-0001")
    # A harmless General change so the editor's own Save and Cancel are enabled.
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill(f"changed by {action}")
    _tid(page, "tab-tools").click()
    expect(_tid(page, "tab-tools")).to_have_attribute("aria-selected", "true")
    if action == "save":
        _main_save_put(page, f"main-{action}-agent")
        expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    else:
        page.locator(CANCEL).click()
        expect(page.locator(CANCEL)).to_be_disabled(timeout=8000)
    _tid(page, "tab-tools").click()
    expect(_tid(page, "tab-tools")).to_have_attribute("aria-selected", "true")
    expect(_btn(page, "save", sid)).to_be_visible()
    expect(_value(_tr(page, sid, "X-Api-Key"))).to_have_value("unsaved-main-0001")
    assert not (_get_agent(app_clean, f"main-{action}-agent")["mcp_overrides"] or {}).get("keyed")


@pytest.mark.browser
def test_a_failed_save_with_no_row_to_blame_returns_focus_to_save(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "focus-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    page.route(
        "**/mcp-overrides/*/credentials",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body=json.dumps({"detail": "Boom."})
        ),
    )
    _open_tools(page, app_clean, "focus-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("focus-key-00001")
    _btn(page, "save", sid).click()
    expect(_tid(page, f"mcp-agent-cred-error-{sid}")).to_be_visible(timeout=8000)
    expect(_btn(page, "save", sid)).to_be_focused()


@pytest.mark.browser
def test_a_real_422_lands_on_its_row_with_focus(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "refuse-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "refuse-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _tid(page, f"mcp-agent-cred-add-{sid}").click()
    row = _trs(page, sid).nth(2)
    # A control character is not allowed in a header value: the server refuses the value.
    _key(row).fill("X-Good-Name")
    _value(row).fill("some-value-01\x01")
    _btn(page, "save", sid).click()
    err = row.locator("[role=alert]")
    expect(err).to_have_count(1, timeout=8000)
    expect(err).not_to_be_empty()
    assert "some-value-01" not in (err.text_content() or "")
    expect(_value(row)).to_be_focused()
    expect(_value(row)).to_have_attribute("aria-invalid", "true")
    # Still unlocked, nothing stored.
    expect(_btn(page, "save", sid)).to_be_visible()
    assert not (_get_agent(app_clean, "refuse-agent")["mcp_overrides"] or {}).get("keyed")


@pytest.mark.browser
def test_a_refused_header_name_lands_on_the_key_input(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "refuse-name-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "refuse-name-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _tid(page, f"mcp-agent-cred-add-{sid}").click()
    row = _trs(page, sid).nth(2)
    _key(row).fill("Bad Header")
    _value(row).fill("x")
    _btn(page, "save", sid).click()
    err = row.locator("td").nth(0).locator("[role=alert]")
    expect(err).to_have_count(1, timeout=8000)
    expect(err).not_to_be_empty()
    assert row.locator("td").nth(1).locator("[role=alert]").count() == 0
    expect(_key(row)).to_be_focused()
    expect(_key(row)).to_have_attribute("aria-invalid", "true")


@pytest.mark.browser
def test_a_422_loc_name_matches_its_header_row_case_insensitively(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "loc-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)

    def refuse(route):
        route.fulfill(
            status=422,
            content_type="application/json",
            body=json.dumps(
                {
                    "detail": [
                        {"loc": ["mcp_overrides", "keyed", "headers", "x-api-key"], "msg": "no"}
                    ]
                }
            ),
        )

    page.route("**/mcp-overrides/*/credentials", refuse)
    _open_tools(page, app_clean, "loc-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    row = _tr(page, sid, "X-Api-Key")
    _value(row).fill("some-value-02")
    _btn(page, "save", sid).click()
    expect(row.locator("[role=alert]")).to_have_count(1, timeout=8000)
    expect(_value(row)).to_be_focused()


@pytest.mark.browser
def test_emptying_an_overridden_server_value_reverts_to_the_server_value(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _credentialed(
        app_clean,
        "empty-agent",
        sid,
        "keyed",
        {"headers": {"X-Org": "org-val-000001", "X-Api-Key": "key-val-0000001"}},
    )
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "empty-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    org = _tr(page, sid, "X-Org")
    expect(_pill(org)).to_be_visible()
    _value(org).fill("")
    body = _tile_save(page, sid)
    assert list(body["headers"]) == ["X-Api-Key"], body
    expect(_btn(page, "override", sid)).to_be_focused(timeout=8000)
    expect(_pill(_tr(page, sid, "X-Org"))).to_be_hidden()
    stored = _get_agent(app_clean, "empty-agent")["mcp_overrides"]["keyed"]
    assert list(stored["headers"]) == ["X-Api-Key"]


@pytest.mark.browser
def test_an_unchanged_server_row_keeps_the_server_value_and_sends_no_override(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "h6-keep", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "h6-keep")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    org = _tr(page, sid, "X-Org")
    # The server's value shows (no blank, no placeholder), no pill, trash disabled.
    expect(_value(org)).to_have_value("acme")
    expect(_pill(org)).to_be_hidden()
    expect(_trash(org)).to_be_disabled()
    expect(_btn(page, "save", sid)).to_be_disabled()
    # Override then Cancel with no change reads clean and restores the same view.
    _btn(page, "cancel", sid).click()
    expect(_value(_tr(page, sid, "X-Org"))).to_have_value("acme")
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("h6-key-value-001")
    body = _tile_save(page, sid)
    assert body == {"headers": {"X-Api-Key": "h6-key-value-001"}, "plain_names": None}, body
    stored = _get_agent(app_clean, "h6-keep")["mcp_overrides"]["keyed"]
    assert list(stored["headers"]) == ["X-Api-Key"]
    expect(_value(_tr(page, sid, "X-Org"))).to_have_value("acme")
    expect(_pill(_tr(page, sid, "X-Org"))).to_be_hidden()


@pytest.mark.browser
def test_editing_a_server_row_value_overrides_it(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "h6-edit", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "h6-edit")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    org = _tr(page, sid, "X-Org")
    _value(org).fill("other-org")
    expect(_pill(org)).to_be_visible()
    expect(_trash(org)).to_be_enabled()
    expect(_btn(page, "save", sid)).to_be_enabled()
    # Clearing it means no override (no pill; the value is left out of a Save).
    _value(org).fill("")
    expect(_pill(org)).to_be_hidden()
    expect(_trash(org)).to_be_disabled()
    _value(org).fill("other-org")
    body = _tile_save(page, sid)
    assert body == {"headers": {"X-Org": "other-org"}, "plain_names": ["X-Org"]}, body
    expect(_pill(_tr(page, sid, "X-Org"))).to_be_visible()
    expect(_value(_tr(page, sid, "X-Org"))).to_have_value("other-org")


@pytest.mark.browser
def test_two_unlocked_tiles_save_independently(app_clean: str, page: Page) -> None:
    sid1 = _seed_keyed(app_clean, "keyed-one")
    sid2 = _seed_keyed(app_clean, "keyed-two")
    _seed_agent(app_clean, "two-agent", mcp_source_ids=[sid1, sid2])
    _mock_agent_test(page, sid1)
    _mock_agent_test(page, sid2)
    _open_tools(page, app_clean, "two-agent")
    _expand(page, sid1)
    _expand(page, sid2)
    _btn(page, "override", sid1).click()
    _btn(page, "override", sid2).click()
    _value(_tr(page, sid1, "X-Api-Key")).fill("one-key-value-001")
    _value(_tr(page, sid2, "X-Api-Key")).fill("two-key-value-002")
    body = _tile_save(page, sid1)
    assert body == {"headers": {"X-Api-Key": "one-key-value-001"}, "plain_names": None}
    # Tile two is still unlocked with its own unsaved edit; tile one is locked.
    expect(_btn(page, "save", sid1)).to_be_hidden()
    expect(_btn(page, "save", sid2)).to_be_enabled()
    expect(_value(_tr(page, sid2, "X-Api-Key"))).to_have_value("two-key-value-002")
    body = _tile_save(page, sid2)
    assert body == {"headers": {"X-Api-Key": "two-key-value-002"}, "plain_names": None}
    stored = _get_agent(app_clean, "two-agent")["mcp_overrides"]
    assert list(stored["keyed-one"]["headers"]) == ["X-Api-Key"]
    assert list(stored["keyed-two"]["headers"]) == ["X-Api-Key"]


@pytest.mark.browser
def test_save_is_disabled_for_an_agent_that_has_never_been_saved(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _mock_agent_test(page, sid)
    _nav.goto(page, app_clean, "agents/~new")
    _tid(page, "tab-tools").click()
    expect(_tid(page, "tab-tools")).to_have_attribute("aria-selected", "true", timeout=8000)
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("create-key-0001")
    expect(_btn(page, "save", sid)).to_be_disabled()
    expect(_tid(page, f"mcp-agent-cred-create-note-{sid}")).to_have_text(
        "Save the agent first to set its own headers."
    )
    expect(_btn(page, "test", sid)).to_be_enabled()
    # The reason Save is off is linked to it (WCAG 3.3.1).
    note_id = f"mcp-agent-cred-create-note-{sid}"
    expect(_btn(page, "save", sid)).to_have_attribute("aria-describedby", note_id)
    expect(page.locator(f"#{note_id}")).to_have_count(1)


@pytest.mark.browser
def test_leaving_with_unsaved_tile_edits_asks_once(app_clean: str, page: Page) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "guard-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "guard-agent")
    _expand(page, sid)
    # Opening, looking and closing a tile stays clean: no dialog on leaving.
    _btn(page, "override", sid).click()
    _btn(page, "cancel", sid).click()
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("guard-key-00001")
    page.locator('[data-testid="rail-library"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(1)
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(_value(_tr(page, sid, "X-Api-Key"))).to_have_value("guard-key-00001")
    page.locator('[data-testid="rail-library"]').click()
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    assert not (_get_agent(app_clean, "guard-agent")["mcp_overrides"] or {}).get("keyed")


DIALOG = '[data-testid="confirm-dialog-overlay"]'


@pytest.mark.browser
def test_continue_discards_the_tile_edits_and_the_guard_does_not_return(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "discard-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "discard-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _tid(page, f"mcp-agent-cred-add-{sid}").click()
    row = _trs(page, sid).last
    _key(row).fill("X-Org")
    expect(row).to_contain_text("This name is already in the table.")
    rows_before = _trs(page, sid).count()
    page.locator('[data-testid="rail-chats"]').click()
    expect(page.locator(DIALOG)).to_have_count(1)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator('[data-testid="rail-chats"]')).to_have_attribute("aria-current", "page")
    # No second prompt on the next move.
    page.locator('[data-testid="rail-library"]').click()
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator('[data-testid="rail-library"]')).to_have_attribute("aria-current", "page")
    # Back on the tab the tile is locked with the saved rows only.
    _nav.set_route(page, "agents/discard-agent/tools")
    expect(_tid(page, "tab-tools")).to_have_attribute("aria-selected", "true", timeout=8000)
    _expand(page, sid)
    expect(_btn(page, "override", sid)).to_be_visible()
    expect(_btn(page, "save", sid)).to_be_hidden()
    assert _trs(page, sid).count() < rows_before
    expect(_table(page, sid)).not_to_contain_text("This name is already in the table.")


@pytest.mark.browser
def test_a_general_edit_and_a_tile_edit_ask_once_and_continue_discards_both(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "both-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid)
    _open_tools(page, app_clean, "both-agent")
    _expand(page, sid)
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("both-key-000001")
    page.locator('[data-testid="tab-general"]').click()
    desc = page.locator('[data-field="description"]')
    desc.fill("changed description")
    page.locator('[data-testid="rail-library"]').click()
    expect(page.locator(DIALOG)).to_have_count(1)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(0)
    page.locator('[data-testid="rail-chats"]').click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.set_route(page, "agents/both-agent/tools")
    expect(_tid(page, "tab-tools")).to_have_attribute("aria-selected", "true", timeout=8000)
    _expand(page, sid)
    expect(_btn(page, "override", sid)).to_be_visible()
    page.locator('[data-testid="tab-general"]').click()
    expect(page.locator('[data-field="description"]')).to_have_value("t")


# ── When a tile tests, and which list it shows ─────────────────────────────


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
def test_switch_on_reports_a_missing_value_and_test_sends_the_unsaved_values(
    app_clean: str, page: Page
) -> None:
    sid = _seed_keyed(app_clean)
    _seed_agent(app_clean, "needs-agent")
    bodies: list = []
    _mock_agent_test(page, sid, bodies)
    _open_tools(page, app_clean, "needs-agent")
    _click_switch(_tid(page, f"mcp-source-toggle-{sid}"))
    expect(_status(page, sid)).to_have_text("Needs a value for X-Api-Key")
    expect(_tid(page, f"mcp-tool-toggle-{sid}-tool_a")).to_have_count(0)
    page.wait_for_timeout(300)
    assert bodies == []

    # Typing the value, then Test, sends the unsaved values; the line follows the typing.
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("typed-key-0001")
    expect(_status(page, sid)).to_have_text("")  # the "Needs a value" line follows the typing
    _btn(page, "test", sid).click()
    expect(_status(page, sid)).to_have_text(
        "Connected with this agent's values · 2 tools", timeout=6000
    )
    assert bodies == [
        {
            "agent": "needs-agent",
            "overrides": {"headers": {"X-Api-Key": "typed-key-0001"}, "plain_names": None},
        }
    ], bodies
    # Cancel discards the typed value; the locked table has a value missing again.
    _btn(page, "cancel", sid).click()
    _btn(page, "test", sid).click()
    expect(_status(page, sid)).to_have_text("Needs a value for X-Api-Key")
    assert len(bodies) == 1, bodies


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
def test_a_failed_test_is_announced_once(app_clean: str, page: Page) -> None:
    sid = _seed_plain(app_clean)
    _seed_agent(app_clean, "once-agent", mcp_source_ids=[sid])
    _mock_agent_test(page, sid, payload={"status": "error", "error": "ConnectionError: refused"})
    _open_tools(page, app_clean, "once-agent")
    _expand(page, sid)
    err = _tid(page, f"mcp-tools-error-{sid}")
    expect(err).to_have_count(1, timeout=8000)
    expect(_status(page, sid)).to_contain_text("Couldn't connect")
    # The alert block carries the announcement; the status words are not a second live region.
    expect(err).to_have_attribute("role", "alert")
    # The status region keeps role=status but is silent (aria-live off) while it shows the error.
    expect(_status(page, sid)).to_have_attribute("role", "status")
    expect(_status(page, sid)).to_have_attribute("aria-live", "off")
    # A later status is written once the region is polite again: record aria-live at each write.
    page.evaluate(
        """(sid) => {
            const el = document.querySelector('[data-testid="mcp-agent-cred-status-' + sid + '"]');
            window.__liveAtWrite = [];
            new MutationObserver(() => {
                window.__liveAtWrite.push([el.textContent, el.getAttribute('aria-live')]);
            }).observe(el, { childList: true, characterData: true, subtree: true });
        }""",
        sid,
    )
    _mock_agent_test(page, sid)
    _btn(page, "test", sid).click()
    expect(_status(page, sid)).to_contain_text("Connected", timeout=8000)
    writes = page.evaluate("() => window.__liveAtWrite")
    assert writes and all(live == "polite" for _text, live in writes), writes
