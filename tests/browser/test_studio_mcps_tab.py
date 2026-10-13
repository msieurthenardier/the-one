"""Browser tests for the Agent-editor MCPs tab (F8 L3+L4 flows).

Rewritten against post-M08-F4-rebrand markup in M17 F1 L02: each MCP
source renders as a tile (`.mcp-source-tile`,
data-testid="mcp-source-row-{id}") with an attach toggle
(mcp-source-toggle-{id}) on row 1, an expand button
(mcp-source-expand-{id}) that toggles `aria-expanded` on the tile, and a
collapsible tools body (mcp-source-details-body-{id}) holding the
per-tool checkboxes (mcp-tool-toggle-{id}-{tool}). The pre-rebrand
`<details class="tool-row-overrides">` panel this file used to assert is
gone; expansion is now button + `aria-expanded` + `hidden`-attr body.

Tests cover:
  1. Attach a source via toggle → save → reload → still attached.
  2. Detach via toggle → save → reload → no longer attached.
  3. Per-tool toggle (expand tile first) → save → reload → preserved.
  4. (removed — see note at former test 4 site)
  5. Empty state when no MCP sources are registered.
  6. Hash routing: deep-link auto-expands the right source tile.
  7. Auth-required inline notice (no popup).
  8. App.areas array-shape lock-test.
  9. Auth-required notice uses source name, not DB id.

Tests 3, 6, 7, 9 use page.route() to mock /api/mcp-sources/{id}/test/connect.
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect

# ── Helpers ────────────────────────────────────────────────────────────────


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(
        f"{base_url}/api/mcp-sources", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code in (200, 201), f"seed mcp-source failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _seed_agent(base_url: str, name: str, payload: dict) -> dict:
    payload = dict(payload)
    payload["name"] = name
    r = httpx.post(
        f"{base_url}/api/agents", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code in (200, 201), f"seed agent failed: {r.status_code} {r.text}"
    return r.json()


def _get_agent(base_url: str, name: str) -> dict:
    r = httpx.get(f"{base_url}/api/agents/{name}", timeout=5.0, headers=auth_headers_for(base_url))
    assert r.status_code == 200, f"get agent failed: {r.status_code} {r.text}"
    return r.json()


def _navigate_to_agent_mcps_tab(page: Page, base_url: str, agent_name: str) -> None:
    _nav.goto(page, base_url, f"agents/{_nav.seg(agent_name)}/mcps")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _mock_tools_connect(page: Page, source_id: str, tools: list[dict]) -> None:
    """Register a page.route() mock for /test/connect that returns the given tools."""
    stub_payload = {
        "status": "ok",
        "tools": tools,
        "capabilities": {
            "tools": {},
            "resources": None,
            "prompts": None,
            "logging": None,
            "completions": None,
            "tasks": None,
        },
    }

    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route(f"**/api/mcp-sources/{source_id}/test/connect", handler)


def _expand_source_tile(page: Page, source_id: str) -> None:
    """Click the source tile's expand button (lazy-loads the tools body)."""
    tile = page.locator(f'[data-testid="mcp-source-row-{source_id}"]')
    expect(tile).to_be_visible(timeout=4000)
    page.locator(f'[data-testid="mcp-source-expand-{source_id}"]').click()
    # Expansion is signalled via aria-expanded on the tile (+ un-hidden body).
    expect(tile).to_have_attribute("aria-expanded", "true", timeout=2000)
    expect(page.locator(f'[data-testid="mcp-source-details-body-{source_id}"]')).to_be_visible()


# ── Test 1: Attach via toggle → save → reload → still attached ──────────────


@pytest.mark.browser
def test_attach_source_persists(app_clean: str, page: Page) -> None:
    """Toggle a source attached, save, reload, verify it's still attached."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "attach-test-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(app_clean, "attach-test-agent", {"description": "test"})

    _navigate_to_agent_mcps_tab(page, app_clean, "attach-test-agent")

    toggle = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    # Toggle checkbox is visually hidden behind the .tool-switch span (matches
    # built-in Tools tab pattern). Use force=True to click through visibility.
    expect(toggle).to_have_count(1, timeout=4000)
    expect(toggle).not_to_be_checked()

    # Toggle is visually hidden behind the .tool-switch span (mirrors built-in
    # Tools tab); set checked state + fire change event programmatically so the
    # mcps-tab.js change listener runs and the form dirties.
    toggle.evaluate(
        "el => { el.checked = !el.checked; "
        "el.dispatchEvent(new Event('change', {bubbles: true})); }"
    )
    expect(toggle).to_be_checked(timeout=2000)

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    save_btn.click()
    expect(save_btn).to_be_disabled(timeout=5000)

    agent = _get_agent(app_clean, "attach-test-agent")
    assert sid in agent.get("mcp_source_ids", []), (
        f"Expected {sid} in mcp_source_ids, got: {agent.get('mcp_source_ids')}"
    )

    page.reload()
    _nav.goto(page, app_clean, "agents/attach-test-agent/mcps")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    toggle2 = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    expect(toggle2).to_have_count(1, timeout=4000)
    expect(toggle2).to_be_checked()


# ── Test 2: Detach via toggle → save → reload → no longer attached ──────────


@pytest.mark.browser
def test_detach_source_persists(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "detach-test-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(
        app_clean,
        "detach-test-agent",
        {
            "description": "test",
            "mcp_source_ids": [sid],
        },
    )

    _navigate_to_agent_mcps_tab(page, app_clean, "detach-test-agent")

    toggle = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    expect(toggle).to_have_count(1, timeout=4000)
    expect(toggle).to_be_checked()

    # Toggle is visually hidden behind the .tool-switch span (mirrors built-in
    # Tools tab); set checked state + fire change event programmatically so the
    # mcps-tab.js change listener runs and the form dirties.
    toggle.evaluate(
        "el => { el.checked = !el.checked; "
        "el.dispatchEvent(new Event('change', {bubbles: true})); }"
    )
    expect(toggle).not_to_be_checked(timeout=2000)

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    with page.expect_response(
        lambda r: "/api/agents/detach-test-agent" in r.url and r.request.method == "PUT"
    ) as resp_info:
        save_btn.click()
    resp = resp_info.value
    assert resp.status == 200, f"PUT failed: {resp.status} {resp.text()}"
    expect(save_btn).to_be_disabled(timeout=5000)

    agent = _get_agent(app_clean, "detach-test-agent")
    assert sid not in agent.get("mcp_source_ids", []), (
        f"Expected {sid} absent from mcp_source_ids, got: {agent.get('mcp_source_ids')}"
    )

    page.reload()
    _nav.goto(page, app_clean, "agents/detach-test-agent/mcps")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    toggle2 = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    expect(toggle2).to_have_count(1, timeout=4000)
    expect(toggle2).not_to_be_checked()


# ── Test 3: Per-tool toggle → save → reload → toggles preserved ─────────────


@pytest.mark.browser
def test_per_tool_toggle_persists(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "toggle-test-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(
        app_clean,
        "toggle-test-agent",
        {
            "description": "test",
            "mcp_source_ids": [sid],
        },
    )

    tools_payload = [
        {"name": "tool_a", "description": "tool a", "input_schema": {}},
        {"name": "tool_b", "description": "tool b", "input_schema": {}},
    ]
    _mock_tools_connect(page, sid, tools_payload)

    _navigate_to_agent_mcps_tab(page, app_clean, "toggle-test-agent")

    # Expand the source tile — that lazy-loads the per-tool checkboxes.
    _expand_source_tile(page, sid)

    cb_a = page.locator(f'[data-testid="mcp-tool-toggle-{sid}-tool_a"]')
    expect(cb_a).to_be_visible(timeout=6000)
    expect(cb_a).to_be_checked()
    cb_b = page.locator(f'[data-testid="mcp-tool-toggle-{sid}-tool_b"]')
    expect(cb_b).to_be_checked()

    # Disable tool_b in denylist mode.
    cb_b.uncheck()

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    save_btn.click()
    expect(save_btn).to_be_disabled(timeout=5000)

    agent = _get_agent(app_clean, "toggle-test-agent")
    overrides = agent.get("mcp_overrides") or {}
    source_override = overrides.get("toggle-test-source", {})
    disabled_tools = source_override.get("disabled_tools", [])
    assert "tool_b" in disabled_tools, f"Expected tool_b in disabled_tools, got: {disabled_tools}"
    assert "tool_a" not in disabled_tools, f"tool_a should not be disabled, got: {disabled_tools}"

    # Reload + deep-link to auto-open the panel.
    page.reload()
    _mock_tools_connect(page, sid, tools_payload)
    _nav.goto(page, app_clean, f"agents/toggle-test-agent/mcps/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    # Deep-link auto-expands the source tile.
    tile = page.locator(f'[data-testid="mcp-source-row-{sid}"]')
    expect(tile).to_have_attribute("aria-expanded", "true", timeout=4000)
    cb_b_reload = page.locator(f'[data-testid="mcp-tool-toggle-{sid}-tool_b"]')
    expect(cb_b_reload).to_be_visible(timeout=6000)
    expect(cb_b_reload).not_to_be_checked()
    cb_a_reload = page.locator(f'[data-testid="mcp-tool-toggle-{sid}-tool_a"]')
    expect(cb_a_reload).to_be_checked()


# ── Test 4 (removed) ────────────────────────────────────────────────────────
#
# The credential-override `__MASKED__` round-trip browser test was removed
# during F8 L4 HAT. Per Anomaly A5 in the flight log, the agent-editor UI
# no longer renders bearer_token / headers / env override fields — those
# don't fit OAuth-source operators and a future flight will land a per-agent
# re-auth toggle. The backend `__MASKED__` round-trip is still tested at the
# API level in tests/test_oauth_test_connection_endpoint.py
# (test_test_connect_override_preserves_oauth_managed_secrets).


# ── Test 5: Empty state when no MCP sources ──────────────────────────────────


@pytest.mark.browser
def test_empty_state_when_no_sources(app_clean: str, page: Page) -> None:
    _seed_agent(app_clean, "empty-state-agent", {"description": "test"})

    _navigate_to_agent_mcps_tab(page, app_clean, "empty-state-agent")

    empty = page.locator('[data-testid="mcp-empty-state"]')
    expect(empty).to_be_visible(timeout=4000)
    expect(empty).to_contain_text("No MCP sources registered yet")
    expect(empty).to_contain_text("Add one in the Library.")

    link = empty.locator("a")
    # In-app links keep their legacy form until the item-history leg converts them;
    # either form reaches Library > MCP servers (the router redirects the legacy one).
    href = link.get_attribute("href")
    assert href in (_nav.href("library"), _nav.legacy_hash("library")), href


# ── Test 6: Hash routing — deep-link auto-expands details ─────────────────────


@pytest.mark.browser
def test_hash_routing_deep_link(app_clean: str, page: Page) -> None:
    """Visit #studio/agents/{name}/mcps/{source-id} → details panel auto-expands."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "deeplink-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(
        app_clean,
        "deeplink-agent",
        {
            "description": "test",
            "mcp_source_ids": [sid],
        },
    )

    _mock_tools_connect(
        page,
        sid,
        [
            {"name": "list_repos", "description": "list repos", "input_schema": {}},
        ],
    )

    _nav.goto(page, app_clean, f"agents/deeplink-agent/mcps/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )

    # Source tile should be auto-expanded.
    tile = page.locator(f'[data-testid="mcp-source-row-{sid}"]')
    expect(tile).to_have_attribute("aria-expanded", "true", timeout=4000)

    # Tools should load from mocked endpoint.
    expect(page.locator(f'[data-testid="mcp-tool-toggle-{sid}-list_repos"]')).to_be_visible(
        timeout=6000
    )


# ── Test 7: Auth-required inline notice — no popup ────────────────────────────


@pytest.mark.browser
def test_auth_required_inline_notice_no_popup(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "auth-required-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(
        app_clean,
        "auth-required-agent",
        {
            "description": "test",
            "mcp_source_ids": [sid],
        },
    )

    auth_required_payload = {
        "status": "auth_required",
        "consent_url": "https://idp.example.com/oauth/authorize",
    }

    def handle_auth_required(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(auth_required_payload),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_auth_required)

    popups = []
    page.on("popup", lambda p: popups.append(p))

    _navigate_to_agent_mcps_tab(page, app_clean, "auth-required-agent")
    _expand_source_tile(page, sid)

    notice = page.locator(f'[data-testid="mcp-auth-required-notice-{sid}"]')
    expect(notice).to_be_visible(timeout=6000)
    expect(notice).to_contain_text("needs Test/auth")
    # F9 L5: notice must show the human-readable source name, not the DB id.
    expect(notice).to_contain_text("auth-required-source")
    notice_text = notice.text_content() or ""
    assert sid not in notice_text.split('"')[0], (
        f"Notice text should not show the DB id '{sid}' as the label; got: {notice_text!r}"
    )

    auth_link = page.locator(f'[data-testid="mcp-auth-required-link-{sid}"]')
    expect(auth_link).to_be_visible()
    href = auth_link.get_attribute("href") or ""
    assert "mcp-sources" in href or "library/mcp" in href, (
        f"Link should point to the MCP servers section, got: {href}"
    )
    assert sid in href, f"Link should contain source id {sid}, got: {href}"

    page.wait_for_timeout(500)
    assert len(popups) == 0, f"Expected no popup, but got {len(popups)} popup(s)"


# ── Test 8: App.areas array-shape lock-test ──────────────────────────────────


@pytest.mark.browser
def test_app_areas_array_shape_lock(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.wait_for_load_state("domcontentloaded")

    result = page.evaluate("""
        () => ({
            isArray: Array.isArray(window.App.areas),
            length: window.App.areas.length,
            allHaveKeys: window.App.areas.every(
                function(a) { return 'id' in a && 'label' in a && 'order' in a; }
            ),
            studioFound: !!window.App.areas.find(function(a) { return a.id === 'studio'; }),
        })
    """)

    assert result["isArray"] is True, "App.areas must be an array"
    assert result["length"] > 0, "App.areas must be non-empty"
    assert result["allHaveKeys"] is True, "Every App.areas entry must have id, label, order"
    assert result["studioFound"] is True, "App.areas must contain the studio area descriptor"


# ── Test 9: Auth-required notice uses source name, not DB id ─────────────────


@pytest.mark.browser
def test_auth_required_notice_uses_source_name_not_id(app_clean: str, page: Page) -> None:
    """F9 L5: _renderAuthRequiredNotice must display the human-readable source
    name rather than the DB id when authentication is required.

    Uses a source named "test_source_friendly_name" so the DB id (a UUID or
    integer) is clearly distinct from the display label.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "test_source_friendly_name",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(
        app_clean,
        "name-id-test-agent",
        {
            "description": "test",
            "mcp_source_ids": [sid],
        },
    )

    def handle_auth_required(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "auth_required",
                    "consent_url": "https://idp.example.com/oauth/authorize",
                }
            ),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_auth_required)

    _navigate_to_agent_mcps_tab(page, app_clean, "name-id-test-agent")
    _expand_source_tile(page, sid)

    notice = page.locator(f'[data-testid="mcp-auth-required-notice-{sid}"]')
    expect(notice).to_be_visible(timeout=6000)

    notice_text = notice.text_content() or ""
    # The friendly name must appear in the notice text.
    assert "test_source_friendly_name" in notice_text, (
        f"Notice should contain source name 'test_source_friendly_name'; got: {notice_text!r}"
    )
    # The raw DB id must NOT appear as a bare label (it may appear inside the href
    # of the child link — that is correct — but not as visible text outside quotes).
    # Strip the link text ("Go to source settings") then check the remaining text.
    link_text = "Go to source settings"
    notice_without_link = notice_text.replace(link_text, "").strip()
    assert sid not in notice_without_link, (
        f"Notice label text should not expose DB id '{sid}'; got: {notice_without_link!r}"
    )


# ── DD19: plain-words connection errors ─────────────────────────────────────

_OPERATOR_ERROR = (
    "MCPConnectionError: MCP connect failed: cancelled during initialize "
    "(cross-task cleanup deadlock; original cause likely transport error or "
    "malformed initial response): Cancelled via cancel scope 29abb186b90"
)


@pytest.mark.browser
def test_mcp_error_message_helper_headlines(app_clean: str, page: Page) -> None:
    """App.mcpErrorMessage maps each class and known phrase to a plain headline
    and keeps the raw text as the detail, unchanged."""
    _nav.goto(page, app_clean, "agents")
    page.wait_for_function("window.App && window.App.mcpErrorMessage")
    cases = [
        (
            "MCPConnectionError: MCP connect failed: server did not respond within 30 seconds "
            "during initialize",
            "The server didn't respond in time.",
        ),
        (_OPERATOR_ERROR, "Couldn't connect to this server."),
        (
            "MCPVersionMismatch: x",
            "This server uses a protocol version the app doesn't support.",
        ),
        ("MCPCapabilityMissing: x", "This server doesn't offer the tools capability."),
        ("SandboxError: x", "The server couldn't start in its sandbox."),
        (
            "fetchMcpSourceTools: HTTP 500",
            "The app couldn't check this server (the request failed).",
        ),
        (
            "Server error 500 Internal Server Error: boom",
            "The app couldn't check this server (the request failed).",
        ),
        ("ValueError: weird", "Couldn't load this server's tools."),
        ("something unclassifiable", "Couldn't load this server's tools."),
        ("", "Couldn't load this server's tools."),
    ]
    for raw, headline in cases:
        got = page.evaluate("raw => window.App.mcpErrorMessage(raw)", raw)
        assert got["headline"].startswith(headline), (raw, got)
        assert got["detail"] == raw


@pytest.mark.browser
def test_mcps_tab_error_shows_plain_headline_and_details(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "dd19-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(app_clean, "dd19-agent", {"description": "test"})
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": _OPERATOR_ERROR}),
        ),
    )
    _navigate_to_agent_mcps_tab(page, app_clean, "dd19-agent")
    _expand_source_tile(page, sid)

    err = page.locator(f'[data-testid="mcp-tools-error-{sid}"]')
    expect(err).to_be_visible(timeout=4000)
    expect(err).to_contain_text("Couldn't connect to this server.")
    expect(err).not_to_contain_text("Error loading tools")
    # WCAG 4.1.3: the error is announced when it is inserted.
    expect(err).to_have_attribute("role", "alert")
    details = err.locator("details")
    assert details.evaluate("el => el.open") is False
    expect(err.locator("summary")).to_have_text("Technical details")
    expect(err.locator('[data-testid="mcp-error-raw"]')).not_to_be_visible()
    err.locator("summary").click()
    raw = err.locator('[data-testid="mcp-error-raw"]')
    expect(raw).to_be_visible()
    assert raw.inner_text() == _OPERATOR_ERROR


# ── Squawk 0080: a failed MCP source list fetch must not detach sources ─────


@pytest.mark.browser
def test_save_after_failed_mcp_sources_fetch_keeps_attachments(app_clean: str, page: Page) -> None:
    """The editor's per-mount MCP source refresh fails (500); saving an
    unrelated edit must leave the agent's stored mcp_source_ids intact."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "failed-fetch-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(
        app_clean,
        "failed-fetch-agent",
        {"description": "before", "mcp_source_ids": [sid]},
    )

    # Let the area's boot load through, then fail every later list request
    # (the agent editor's per-mount refresh).
    calls = {"n": 0}

    def handler(route) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            route.continue_()
        else:
            route.fulfill(status=500, body='{"detail": "boom"}', content_type="application/json")

    page.route("**/api/mcp-sources?include_agent_surfaces=1", handler)

    _nav.goto(page, app_clean, "agents/failed-fetch-agent")
    desc = page.locator('[data-field="description"]')
    expect(desc).to_have_value("before", timeout=8000)
    desc.fill("after")

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    with page.expect_response(
        lambda r: "/api/agents/failed-fetch-agent" in r.url and r.request.method == "PUT"
    ) as resp_info:
        save_btn.click()
    assert resp_info.value.status == 200, resp_info.value.text()
    assert calls["n"] >= 2, "the refresh request never hit the failing route"

    agent = _get_agent(app_clean, "failed-fetch-agent")
    assert agent["description"] == "after"
    assert agent.get("mcp_source_ids") == [sid], agent.get("mcp_source_ids")
