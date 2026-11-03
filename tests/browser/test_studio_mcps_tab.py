# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Browser tests for the Agent-editor Tools tab (F8 L3+L4 flows).

Rewritten against post-M08-F4-rebrand markup in M17 F1 L02: each MCP
source renders as an `App.ui.groupTile` (
data-testid="mcp-source-row-{id}") with an attach toggle
(mcp-source-toggle-{id}) on row 1, an expand button
(mcp-source-expand-{id}) that toggles `aria-expanded` on itself, and a
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
import time

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser._self_config import ENABLE_SWITCH, click_switch
from browser.seeders import SeededApp
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


def _wait_surface_id(base_url: str, name: str, exclude: tuple[str, ...] = ()) -> str:
    """Poll until the agent's loopback surface source is attached; return its id."""
    deadline = time.monotonic() + 10
    while True:
        ids = [i for i in _get_agent(base_url, name)["mcp_source_ids"] if i not in exclude]
        if ids:
            return ids[0]
        assert time.monotonic() < deadline, f"no surface source attached to {name!r} within 10 s"
        time.sleep(0.1)


def _navigate_to_agent_mcps_tab(page: Page, base_url: str, agent_name: str) -> None:
    _nav.goto(page, base_url, f"agents/{_nav.seg(agent_name)}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
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


def _click_switch(toggle) -> None:
    """Click a library switch the way a person does: its label, not the hidden input."""
    toggle.locator("xpath=ancestor::label[1]").click()


def _expand_source_tile(page: Page, source_id: str) -> None:
    """Click the source tile's expand button (lazy-loads the tools body)."""
    tile = page.locator(f'[data-testid="mcp-source-row-{source_id}"]')
    expect(tile).to_be_visible(timeout=4000)
    expand = page.locator(f'[data-testid="mcp-source-expand-{source_id}"]')
    expand.click()
    # Expansion is signalled via aria-expanded on the expand button (+ un-hidden body).
    expect(expand).to_have_attribute("aria-expanded", "true", timeout=2000)
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
    expect(toggle).to_have_count(1, timeout=4000)
    expect(toggle).not_to_be_checked()

    # A real click on the switch (the library control's label), not a scripted flip.
    _click_switch(toggle)
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
    _nav.goto(page, app_clean, "agents/attach-test-agent/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
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

    # A real click on the switch (the library control's label), not a scripted flip.
    _click_switch(toggle)
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
    _nav.goto(page, app_clean, "agents/detach-test-agent/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
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
    _nav.goto(page, app_clean, f"agents/toggle-test-agent/tools/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    # Deep-link auto-expands the source tile.
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_attribute(
        "aria-expanded", "true", timeout=4000
    )
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
    """Visit #studio/agents/{name}/tools/{source-id} → details panel auto-expands."""
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

    _nav.goto(page, app_clean, f"agents/deeplink-agent/tools/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )

    # Source tile should be auto-expanded.
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_attribute(
        "aria-expanded", "true", timeout=4000
    )

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
def test_mcp_error_headline_follows_the_transport(app_clean: str, page: Page) -> None:
    """A18 (leg 08b): the generic connection failure has one headline per transport, and
    "did not respond" ends "then try again." (the editor's Test and the tab's refresh)."""
    _nav.goto(page, app_clean, "agents")
    page.wait_for_function("window.App && window.App.mcpErrorMessage")
    stdio = "The server's command didn't start or stopped. Open Technical details for its output."
    http = (
        "Couldn't connect to this server. Check that it's running and that its address and "
        "headers are right, then try again."
    )
    for transport, want in (("stdio", stdio), ("streamable-http", http), (None, http)):
        got = page.evaluate(
            "([raw, t]) => window.App.mcpErrorMessage(raw, t ? {transport: t} : undefined)",
            [_OPERATOR_ERROR, transport],
        )
        assert got["headline"] == want, (transport, got)
    # The probe's class-less transport failure (api.py `_probe_auth_posture`, HAT) reads as a
    # connection failure, not the catch-all, and keeps its raw text as the detail.
    for transport, want in (("streamable-http", http), (None, http), ("stdio", stdio)):
        got = page.evaluate(
            "([raw, t]) => window.App.mcpErrorMessage(raw, t ? {transport: t} : undefined)",
            ["connection probe failed", transport],
        )
        assert got["headline"] == want, (transport, got)
        assert got["detail"] == "connection probe failed"
    slow = page.evaluate(
        "() => window.App.mcpErrorMessage('MCPConnectionError: server did not respond within 30 s')"
    )
    assert (
        slow["headline"]
        == "The server didn't respond in time. Check that it's running, then try again."
    )
    # No other wording still tells the operator to "Refresh" a button that is now Test.
    assert "Refresh" not in http + stdio + slow["headline"]


@pytest.mark.browser
def test_mcp_error_text_is_one_size_in_the_tab_and_the_editor(app_clean: str, page: Page) -> None:
    """A18: the same error block reads at one size in both hosts (body-sm)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "a18-size-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(app_clean, "a18-size-agent", {"description": "test"})
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": _OPERATOR_ERROR}),
        ),
    )
    probe = "el => parseFloat(getComputedStyle(el).fontSize)"
    _navigate_to_agent_mcps_tab(page, app_clean, "a18-size-agent")
    _expand_source_tile(page, sid)
    tab_err = page.locator(f'[data-testid="mcp-tools-error-{sid}"]')
    expect(tab_err).to_be_visible(timeout=4000)
    tab_size = tab_err.evaluate(probe)

    _nav.goto(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="mcp-test-connection"]').click()
    editor_err = page.locator('[data-testid="mcp-connection-error"]')
    expect(editor_err).to_be_visible(timeout=8000)
    assert editor_err.evaluate(probe) == tab_size == 12.0


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


# ── DD9-1 (M31 F2 L07b): collapsing an expanded source ──────────────────────


@pytest.mark.browser
def test_collapse_expanded_source_drops_route_segment_dd9_1(app_clean: str, page: Page) -> None:
    """Expand then collapse a source: no page error, the expand button reports
    collapsed, the body is hidden and the route drops the source segment.

    Before the fix the collapse called the undefined ``_parseSourceIdFromHash``
    (a ``pageerror``) and ``onSelectedSourceChange(null)`` never ran, so the route
    kept ``/{source-id}``.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "dd91-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _seed_agent(app_clean, "dd91-agent", {"description": "test", "mcp_source_ids": [sid]})
    _mock_tools_connect(page, sid, [{"name": "t1", "description": "d", "input_schema": {}}])
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    _navigate_to_agent_mcps_tab(page, app_clean, "dd91-agent")
    _expand_source_tile(page, sid)
    _nav.expect_route(page, f"agents/dd91-agent/tools/{_nav.seg(sid)}")

    expand = page.locator(f'[data-testid="mcp-source-expand-{sid}"]')
    expand.click()
    expect(expand).to_have_attribute("aria-expanded", "false", timeout=2000)
    expect(page.locator(f'[data-testid="mcp-source-details-body-{sid}"]')).to_be_hidden()
    _nav.expect_route(page, "agents/dd91-agent/tools")
    assert errors == [], errors


# ── M31 F2 L07b: the Tools tab on the control library ────────────────────────

SAVE = '[data-testid="save-agent-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
TOOLS_AB = [
    {"name": "tool_a", "description": "tool a", "input_schema": {}},
    {"name": "tool_b", "description": "tool b", "input_schema": {}},
]


def _seed_source(base: str, name: str) -> str:
    return _seed_mcp_source(
        base,
        {
            "name": name,
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )


def _tool(page: Page, sid: str, name: str):
    return page.locator(f'[data-testid="mcp-tool-toggle-{sid}-{name}"]')


def _edit_description(page: Page, text: str) -> None:
    """Dirty the form from the General tab, then return to the Tools tab."""
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill(text)
    page.locator('[data-testid="tab-tools"]').click()


def _click_row(page: Page, sid: str, name: str) -> None:
    """A real click on a tool row's label (its checkbox input is the row's only control)."""
    _tool(page, sid, name).locator("xpath=ancestor::label[1]").click()


@pytest.mark.browser
def test_tile_shape_switch_refresh_and_chips(app_clean: str, page: Page) -> None:
    sid = _seed_source(app_clean, "shape-source")
    _seed_agent(app_clean, "shape-agent", {"description": "t", "mcp_source_ids": [sid]})
    _navigate_to_agent_mcps_tab(page, app_clean, "shape-agent")

    master = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    expect(master).to_have_attribute("role", "switch")
    expect(master).to_have_attribute("data-mcp-source-id", sid)
    expect(master).to_be_checked()
    # The accessible name is reachable by role.
    expect(page.get_by_role("switch", name="Attach shape-source")).to_have_count(1)

    refresh = page.locator(f'[data-testid="mcp-refresh-tools-btn-{sid}"]')
    expect(refresh).to_have_text("Refresh")
    expect(refresh).to_have_attribute("aria-label", "Refresh tools for shape-source")
    box = refresh.bounding_box()
    assert box is not None and round(box["height"]) == 24, box

    tile = page.locator(f'[data-testid="mcp-source-row-{sid}"]')
    expect(tile.locator(".ui-group-tile-chip").nth(1)).to_have_text("http")
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_text("Tools▸")


@pytest.mark.browser
def test_real_clicks_dirty_the_form(app_clean: str, page: Page) -> None:
    """A click on the master or on a tool row enables Save and shows the caption."""
    sid = _seed_source(app_clean, "dirty-source")
    _seed_agent(app_clean, "dirty-agent", {"description": "t"})
    _mock_tools_connect(page, sid, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "dirty-agent")
    expect(page.locator(SAVE)).to_be_disabled()

    master = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    _click_switch(master)
    expect(master).to_be_checked()
    expect(page.locator(SAVE)).to_be_enabled()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    _click_switch(master)
    expect(page.locator(SAVE)).to_be_disabled(timeout=3000)

    _expand_source_tile(page, sid)
    expect(_tool(page, sid, "tool_a")).to_be_checked(timeout=6000)
    _click_row(page, sid, "tool_a")
    expect(_tool(page, sid, "tool_a")).not_to_be_checked()
    expect(page.locator(SAVE)).to_be_enabled()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    # The count follows the row, once (a duplicate listener would not change it).
    tile = page.locator(f'[data-testid="mcp-source-row-{sid}"]')
    expect(tile.locator(".ui-group-tile-chip").nth(0)).to_have_text("1 / 2 enabled")
    # Tool rows never change the master.
    expect(master).not_to_be_checked()


@pytest.mark.browser
def test_save_patches_the_tab_in_place_and_matches_the_server(app_clean: str, page: Page) -> None:
    sid = _seed_source(app_clean, "patch-source")
    _seed_agent(app_clean, "patch-agent", {"description": "t", "mcp_source_ids": [sid]})
    _mock_tools_connect(page, sid, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "patch-agent")
    _expand_source_tile(page, sid)
    expect(_tool(page, sid, "tool_b")).to_be_checked(timeout=6000)

    page.evaluate(
        """sid => { document.querySelector('[data-testid="mcp-source-row-' + sid + '"]').dataset.marker = 'same'; }""",
        sid,
    )
    _click_row(page, sid, "tool_b")
    with page.expect_response(
        lambda r: "/api/agents/patch-agent" in r.url and r.request.method == "PUT"
    ) as resp_info:
        page.locator(SAVE).click()
    assert resp_info.value.status == 200
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)

    agent = _get_agent(app_clean, "patch-agent")
    assert agent["mcp_overrides"]["patch-source"]["disabled_tools"] == ["tool_b"]
    # Same tile node, still expanded, group mode and checked states from the server.
    tile = page.locator(f'[data-testid="mcp-source-row-{sid}"]')
    expect(tile).to_have_attribute("data-marker", "same")
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_attribute(
        "aria-expanded", "true"
    )
    group = page.locator(f'[data-testid="mcp-tools-checkbox-group-{sid}"]')
    expect(group).to_have_attribute("data-mcp-tool-mode", "denylist")
    expect(_tool(page, sid, "tool_a")).to_be_checked()
    expect(_tool(page, sid, "tool_b")).not_to_be_checked()
    expect(tile.locator(".ui-group-tile-chip").nth(0)).to_have_text("1 / 2 enabled")


@pytest.mark.browser
def test_set_agent_recomputes_mode_and_checked_states(app_clean: str, page: Page) -> None:
    """A stored allowlist flips the group to allowlist mode on the next patch, and a
    Cancel restores the stored selection, on the same nodes."""
    sid = _seed_source(app_clean, "mode-source")
    _seed_agent(
        app_clean,
        "mode-agent",
        {
            "description": "t",
            "mcp_source_ids": [sid],
            "mcp_overrides": {"mode-source": {"enabled_tools": ["tool_a"]}},
        },
    )
    _mock_tools_connect(page, sid, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "mode-agent")
    _expand_source_tile(page, sid)
    group = page.locator(f'[data-testid="mcp-tools-checkbox-group-{sid}"]')
    expect(group).to_have_attribute("data-mcp-tool-mode", "allowlist")
    expect(_tool(page, sid, "tool_a")).to_be_checked(timeout=6000)
    expect(_tool(page, sid, "tool_b")).not_to_be_checked()

    _click_row(page, sid, "tool_b")
    expect(_tool(page, sid, "tool_b")).to_be_checked()
    page.locator('[data-testid="cancel-agent-btn"]').click()
    expect(_tool(page, sid, "tool_b")).not_to_be_checked(timeout=4000)
    expect(page.locator(SAVE)).to_be_disabled()

    # The server flips the mode (denylist now); a Save patches the group to it.
    httpx.put(
        f"{app_clean}/api/agents/mode-agent",
        json={
            "name": "mode-agent",
            "description": "t",
            "mcp_source_ids": [sid],
            "mcp_overrides": {"mode-source": {"disabled_tools": ["tool_a"]}},
        },
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    ).raise_for_status()
    _edit_description(page, "t2")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    agent = _get_agent(app_clean, "mode-agent")
    mode = "allowlist" if "enabled_tools" in agent["mcp_overrides"]["mode-source"] else "denylist"
    expect(group).to_have_attribute("data-mcp-tool-mode", mode)


@pytest.mark.browser
def test_payload_round_trip_is_unchanged(app_clean: str, page: Page) -> None:
    """mcp_source_ids and the tool allow/deny lists on Save follow the DOM as before."""
    s1 = _seed_source(app_clean, "rt-one")
    s2 = _seed_source(app_clean, "rt-two")
    _seed_agent(app_clean, "rt-agent", {"description": "t", "mcp_source_ids": [s1]})
    _mock_tools_connect(page, s1, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "rt-agent")
    _expand_source_tile(page, s1)
    expect(_tool(page, s1, "tool_a")).to_be_checked(timeout=6000)
    _click_row(page, s1, "tool_a")
    _click_switch(page.locator(f'[data-testid="mcp-source-toggle-{s2}"]'))

    with page.expect_request(
        lambda r: "/api/agents/rt-agent" in r.url and r.method == "PUT"
    ) as req_info:
        page.locator(SAVE).click()
    body = json.loads(req_info.value.post_data or "{}")
    assert sorted(body["mcp_source_ids"]) == sorted([s1, s2])
    assert body["mcp_overrides"] == {"rt-one": {"disabled_tools": ["tool_a"]}}


@pytest.mark.browser
def test_refresh_patches_rows_by_tool_name_per_mode(app_clean: str, page: Page) -> None:
    sid = _seed_source(app_clean, "refresh-source")
    _seed_agent(app_clean, "refresh-agent", {"description": "t", "mcp_source_ids": [sid]})
    _mock_tools_connect(page, sid, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "refresh-agent")
    _expand_source_tile(page, sid)
    expect(_tool(page, sid, "tool_a")).to_be_checked(timeout=6000)
    _click_row(page, sid, "tool_a")  # an unsaved choice
    page.evaluate(
        """sid => { document.querySelector('[data-testid="mcp-tool-toggle-' + sid + '-tool_a"]').dataset.marker = 'kept'; }""",
        sid,
    )

    # Refresh returns {tool_a, tool_c}: tool_a keeps its unsaved state, tool_b goes, a
    # new tool takes the denylist default (checked).
    page.unroute_all()
    _mock_tools_connect(
        page,
        sid,
        [
            {"name": "tool_a", "description": "tool a", "input_schema": {}},
            {"name": "tool_c", "description": "tool c", "input_schema": {}},
        ],
    )
    page.locator(f'[data-testid="mcp-refresh-tools-btn-{sid}"]').click()
    expect(_tool(page, sid, "tool_c")).to_be_checked(timeout=6000)
    expect(_tool(page, sid, "tool_b")).to_have_count(0)
    expect(_tool(page, sid, "tool_a")).not_to_be_checked()
    expect(_tool(page, sid, "tool_a")).to_have_attribute("data-marker", "kept")
    tile = page.locator(f'[data-testid="mcp-source-row-{sid}"]')
    expect(tile.locator(".ui-group-tile-chip").nth(0)).to_have_text("1 / 2 enabled")


@pytest.mark.browser
def test_refresh_new_tool_is_unchecked_in_allowlist_mode(app_clean: str, page: Page) -> None:
    sid = _seed_source(app_clean, "refresh-allow-source")
    _seed_agent(
        app_clean,
        "refresh-allow-agent",
        {
            "description": "t",
            "mcp_source_ids": [sid],
            "mcp_overrides": {"refresh-allow-source": {"enabled_tools": ["tool_a"]}},
        },
    )
    _mock_tools_connect(page, sid, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "refresh-allow-agent")
    _expand_source_tile(page, sid)
    expect(_tool(page, sid, "tool_a")).to_be_checked(timeout=6000)
    page.unroute_all()
    _mock_tools_connect(
        page, sid, [*TOOLS_AB, {"name": "tool_c", "description": "", "input_schema": {}}]
    )
    page.locator(f'[data-testid="mcp-refresh-tools-btn-{sid}"]').click()
    expect(_tool(page, sid, "tool_c")).to_have_count(1, timeout=6000)
    expect(_tool(page, sid, "tool_c")).not_to_be_checked()
    expect(_tool(page, sid, "tool_a")).to_be_checked()


@pytest.mark.browser
def test_refresh_error_keeps_rows_then_success_clears_it(app_clean: str, page: Page) -> None:
    sid = _seed_source(app_clean, "err-source")
    _seed_agent(app_clean, "err-agent", {"description": "t", "mcp_source_ids": [sid]})
    _mock_tools_connect(page, sid, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "err-agent")
    _expand_source_tile(page, sid)
    expect(_tool(page, sid, "tool_a")).to_be_visible(timeout=6000)

    page.unroute_all()
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": _OPERATOR_ERROR}),
        ),
    )
    refresh = page.locator(f'[data-testid="mcp-refresh-tools-btn-{sid}"]')
    refresh.click()
    err = page.locator(f'[data-testid="mcp-tools-error-{sid}"]')
    expect(err).to_be_visible(timeout=4000)
    expect(_tool(page, sid, "tool_a")).to_be_visible()  # the rows stay
    refresh.click()
    expect(page.locator(f'[data-testid="mcp-tools-error-{sid}"]')).to_have_count(1, timeout=4000)

    page.unroute_all()
    _mock_tools_connect(page, sid, TOOLS_AB)
    refresh.click()
    expect(page.locator(f'[data-testid="mcp-tools-error-{sid}"]')).to_have_count(0, timeout=4000)


@pytest.mark.browser
def test_refresh_on_collapsed_tile_expands_and_fetches_once(app_clean: str, page: Page) -> None:
    sid = _seed_source(app_clean, "collapsed-refresh")
    _seed_agent(app_clean, "collapsed-refresh-agent", {"description": "t", "mcp_source_ids": [sid]})
    calls = {"n": 0}

    def handler(route) -> None:
        calls["n"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "ok", "tools": TOOLS_AB, "capabilities": {"tools": {}}}),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handler)
    _navigate_to_agent_mcps_tab(page, app_clean, "collapsed-refresh-agent")
    page.locator(f'[data-testid="mcp-refresh-tools-btn-{sid}"]').click()
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_attribute(
        "aria-expanded", "true", timeout=3000
    )
    expect(_tool(page, sid, "tool_a")).to_be_visible(timeout=6000)
    _nav.expect_route(page, f"agents/collapsed-refresh-agent/tools/{_nav.seg(sid)}")
    assert calls["n"] == 1, calls


@pytest.mark.browser
def test_self_configuration_enable_then_save_keeps_the_surface(app_clean: str, page: Page) -> None:
    _seed_agent(app_clean, "sc-keep-agent", {"description": "t"})
    _nav.goto(page, app_clean, "agents/sc-keep-agent/self-configuration")
    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).not_to_be_checked(timeout=8000)
    click_switch(page, ENABLE_SWITCH)
    expect(toggle).to_be_checked(timeout=8000)
    surface = _wait_surface_id(app_clean, "sc-keep-agent")

    # The Tools tab shows no tile for the surface (sortie 08), so the Save below
    # builds its mcp_source_ids without it; the server carries the attachment.
    page.locator('[data-testid="tab-tools"]').click()
    expect(page.locator('[data-testid="mcp-empty-state"]')).to_be_visible(timeout=8000)
    expect(page.locator(f'[data-source-id="{surface}"]')).to_have_count(0)
    _edit_description(page, "t2")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    assert surface in _get_agent(app_clean, "sc-keep-agent")["mcp_source_ids"]

    # A Save from the General tab keeps it attached too, and the tab still reads on.
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("t2b")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    assert surface in _get_agent(app_clean, "sc-keep-agent")["mcp_source_ids"]
    page.locator('[data-testid="tab-self-configuration"]').click()
    expect(toggle).to_be_checked(timeout=8000)

    # Disable, then Save: the deleted id is not sent back.
    page.locator('[data-testid="tab-self-configuration"]').click()
    click_switch(page, ENABLE_SWITCH)
    expect(toggle).not_to_be_checked(timeout=8000)
    page.locator('[data-testid="tab-tools"]').click()
    expect(page.locator('[data-testid="mcp-empty-state"]')).to_be_visible(timeout=8000)
    _edit_description(page, "t3")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    assert surface not in _get_agent(app_clean, "sc-keep-agent")["mcp_source_ids"]


@pytest.mark.browser
def test_set_sources_keeps_an_expanded_unsaved_tile(app_clean: str, page: Page) -> None:
    sid = _seed_source(app_clean, "keep-source")
    _seed_agent(app_clean, "keep-agent", {"description": "t", "mcp_source_ids": [sid]})
    _mock_tools_connect(page, sid, TOOLS_AB)
    _navigate_to_agent_mcps_tab(page, app_clean, "keep-agent")
    _expand_source_tile(page, sid)
    expect(_tool(page, sid, "tool_a")).to_be_checked(timeout=6000)
    page.evaluate(
        """sid => { document.querySelector('[data-testid="mcp-source-row-' + sid + '"]').dataset.marker = 'same'; }""",
        sid,
    )
    _click_row(page, sid, "tool_a")

    # Enabling self-configuration adds no tile (sortie 08): the surface is never shown.
    page.locator('[data-testid="tab-self-configuration"]').click()
    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).not_to_be_checked(timeout=8000)
    click_switch(page, ENABLE_SWITCH)
    expect(toggle).to_be_checked(timeout=8000)
    surface = _wait_surface_id(app_clean, "keep-agent", exclude=(sid,))

    page.locator('[data-testid="tab-tools"]').click()
    expect(page.locator(f'[data-testid="mcp-source-row-{sid}"]')).to_be_visible(timeout=8000)
    expect(page.locator(f'[data-source-id="{surface}"]')).to_have_count(0)
    tile = page.locator(f'[data-testid="mcp-source-row-{sid}"]')
    expect(tile).to_have_attribute("data-marker", "same")
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_attribute(
        "aria-expanded", "true"
    )
    # (A same-identity patch also re-derives every row from the stored agent, as General
    # does, so the unsaved choice itself is not asserted here: the synthetic test below
    # pins setSources alone.)


@pytest.mark.browser
def test_set_sources_alone_keeps_expanded_unsaved_tile_and_swaps_empty_state(
    app_clean: str, page: Page
) -> None:
    """setSources reconciles by id on its own: the same node, expanded state and unsaved
    row choice survive; no surface is ever shown, the agent's own included (sortie 08); an
    emptied list shows the empty state and a new source brings the list back."""
    page.goto(app_clean)
    page.wait_for_function("!!(window.App && window.App.studio && window.App.studio.renderMcpsTab)")
    out = page.evaluate(
        """async () => {
          const mk = (id, extra) => Object.assign({id, name: 'n-' + id, type: 'streamable-http',
            config: {_cache: {tools: [{name: 'ta', description: ''}, {name: 'tb', description: ''}]}}}, extra || {});
          const panel = document.createElement('div');
          document.body.appendChild(panel);
          const agent = {name: 'me', mcp_source_ids: ['s1'], mcp_overrides: {}};
          const h = App.studio.renderMcpsTab(panel, agent, [mk('s1')], {onChange() {}});
          const tile = panel.querySelector('[data-testid=mcp-source-row-s1]');
          tile.querySelector('.ui-group-tile-expand').click();
          const ta = panel.querySelector('[data-mcp-tool-toggle=ta]');
          ta.click();
          const surface = mk('sc', {name: 'self-configuration', config: {self_configuration: {agent: 'me'}}});
          const other = mk('sx', {name: 'self-configuration', config: {self_configuration: {agent: 'you'}}});
          h.setSources([mk('s1'), surface, other], 'me');
          const res = {};
          res.sameNode = panel.querySelector('[data-testid=mcp-source-row-s1]') === tile;
          res.expanded = tile.querySelector('.ui-group-tile-expand').getAttribute('aria-expanded');
          res.taChecked = panel.querySelector('[data-mcp-tool-toggle=ta]').checked;
          res.ids = Array.from(panel.querySelectorAll('[data-source-id]')).map((n) => n.dataset.sourceId);
          res.scToggle = !!panel.querySelector('[data-mcp-source-id=sc]');
          h.setSources([surface], 'me');
          res.afterSurfaceOnly = Array.from(panel.querySelectorAll('[data-source-id]')).map((n) => n.dataset.sourceId);
          res.surfaceOnlyEmpty = !!panel.querySelector('[data-testid=mcp-empty-state]');
          h.setSources([], 'me');
          res.empty = !!panel.querySelector('[data-testid=mcp-empty-state]');
          h.setSources([mk('s2')], 'me');
          res.back = Array.from(panel.querySelectorAll('[data-source-id]')).map((n) => n.dataset.sourceId);
          res.emptyGone = !panel.querySelector('[data-testid=mcp-empty-state]');
          h.destroy();
          panel.remove();
          return res;
        }"""
    )
    assert out["sameNode"] is True
    assert out["expanded"] == "true"
    assert out["taChecked"] is False
    assert out["ids"] == ["s1"]
    assert out["scToggle"] is False
    assert out["afterSurfaceOnly"] == []
    assert out["surfaceOnlyEmpty"] is True
    assert out["empty"] is True
    assert out["back"] == ["s2"]
    assert out["emptyGone"] is True


@pytest.mark.browser
def test_expand_buttons_are_named_for_their_server(app_clean: str, page: Page) -> None:
    """A20 (ledger row 20): every Tools button carries its server's name, so no
    two share one; the visible text stays "Tools" or the count, and the button is
    no longer also described by the tile's name (the server is not read twice)."""
    unloaded = _seed_source(app_clean, "Docs search")
    other = _seed_source(app_clean, "Billing API")
    cached = _seed_mcp_source(
        app_clean,
        {
            "name": "Team calendar",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [{"name": f"t{i}", "description": ""} for i in range(3)],
                },
            },
            "secrets": {},
        },
    )
    _seed_agent(
        app_clean,
        "tools-name-agent",
        {"description": "t", "mcp_source_ids": [unloaded, other, cached]},
    )
    _navigate_to_agent_mcps_tab(page, app_clean, "tools-name-agent")

    sel = '[data-testid^="mcp-source-expand-"]'
    expect(page.locator(sel)).to_have_count(3)
    out = page.evaluate(
        """(sel) => Array.from(document.querySelectorAll(sel)).map((b) => ({
             label: b.getAttribute('aria-label'), text: b.textContent.replace('▸', ''),
             described: b.hasAttribute('aria-describedby')}))""",
        sel,
    )
    by_label = {o["label"]: o for o in out}
    assert set(by_label) == {
        "Tools for Docs search",
        "Tools for Billing API",
        "3 tools for Team calendar",
    }, out
    assert len(by_label) == len(out), "two Tools buttons share a name"
    assert by_label["Tools for Docs search"]["text"] == "Tools"
    assert by_label["3 tools for Team calendar"]["text"] == "3 tools"
    assert not any(o["described"] for o in out), out
    # The engine's own computed names.
    for name in by_label:
        expect(page.get_by_role("button", name=name, exact=True)).to_have_count(1)
    # Label in name: the accessible name starts with the visible text.
    assert all(label.startswith(o["text"]) for label, o in by_label.items())


@pytest.mark.browser
def test_tools_tab_group_tile_is_unchanged_by_the_expand_label_option(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The Built-in tools tab's group tile does not pass `expandLabel`: its
    expand button keeps its content-only name and its describedby."""
    _nav.goto(page, app_with_agent.base_url, f"agents/{app_with_agent.agent_name}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    out = page.evaluate(
        """() => Array.from(document.querySelectorAll('.ui-group-tile-expand')).map((b) => ({
             label: b.hasAttribute('aria-label'), described: b.hasAttribute('aria-describedby')}))"""
    )
    assert out and all(not o["label"] and o["described"] for o in out), out


# ── M33 F1 L06: one Tools tab, two sections ─────────────────────────────────

SAVE = '[data-testid="save-agent-btn"]'
BUILTIN_SECTION = '[data-testid="agent-tools-builtin-section"]'
MCP_SECTION = '[data-testid="agent-tools-mcp-section"]'


def _seed_http_source(base_url: str, name: str) -> str:
    return _seed_mcp_source(
        base_url,
        {
            "name": name,
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )


@pytest.mark.browser
def test_tools_tab_holds_built_in_and_mcp_sections_in_order(app_clean: str, page: Page) -> None:
    _seed_http_source(app_clean, "order-source")
    _seed_agent(app_clean, "order-agent", {"description": "t"})
    _navigate_to_agent_mcps_tab(page, app_clean, "order-agent")
    expect(page.locator(BUILTIN_SECTION)).to_be_visible(timeout=6000)
    expect(page.locator(MCP_SECTION)).to_be_visible()
    headings = page.locator(
        '[data-testid="agent-tab-panel-tools"], #agent-tab-panel-tools'
    ).locator("h2.section-title")
    expect(headings).to_have_text(["MCP servers", "Built-in tools"])
    # The MCP section sits above the built-in one (operator decision, M33 F4 HAT A2).
    assert page.evaluate(
        """() => {
          const a = document.querySelector('[data-testid="agent-tools-mcp-section"]');
          const b = document.querySelector('[data-testid="agent-tools-builtin-section"]');
          return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
        }"""
    )
    expect(page.locator(f"{BUILTIN_SECTION} .ui-group-tile").first).to_be_visible()
    expect(page.locator(f'{MCP_SECTION} [data-testid^="mcp-source-row-"]')).to_have_count(1)


@pytest.mark.browser
def test_one_save_covers_built_in_attach_and_mcp_tool_choices(app_clean: str, page: Page) -> None:
    sid = _seed_http_source(app_clean, "both-source")
    _seed_agent(app_clean, "both-agent", {"description": "t"})
    _mock_tools_connect(
        page,
        sid,
        [
            {"name": "tool_a", "description": "a", "input_schema": {}},
            {"name": "tool_b", "description": "b", "input_schema": {}},
        ],
    )
    _navigate_to_agent_mcps_tab(page, app_clean, "both-agent")
    # 1. a built-in tool
    page.locator(f"{BUILTIN_SECTION} .ui-group-tile-expand").first.click()
    first_tool = page.locator(f"{BUILTIN_SECTION} input[data-tool]").first
    tool_name = first_tool.get_attribute("data-tool")
    first_tool.locator("xpath=ancestor::label[1]").click()
    # 2. the MCP attach switch, 3. one MCP tool
    _click_switch(page.locator(f'[data-testid="mcp-source-toggle-{sid}"]'))
    _expand_source_tile(page, sid)
    cb = page.locator(f'[data-testid="mcp-tool-toggle-{sid}-tool_b"]')
    expect(cb).to_be_visible(timeout=6000)
    cb.uncheck()
    expect(page.locator(SAVE)).not_to_be_disabled(timeout=2000)
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    agent = _get_agent(app_clean, "both-agent")
    assert sid in agent["mcp_source_ids"]
    assert agent["mcp_overrides"]["both-source"]["disabled_tools"] == ["tool_b"]
    assert tool_name in (agent.get("disabled_tools") or []), agent


@pytest.mark.browser
def test_operator_disabled_tool_rebuild_leaves_the_mcp_section_intact(
    app_clean: str, page: Page
) -> None:
    from browser.seeders import seed_tool_config

    sid = _seed_http_source(app_clean, "iso-source")
    _seed_agent(app_clean, "iso-agent", {"description": "t"})
    _mock_tools_connect(page, sid, [{"name": "tool_a", "description": "a", "input_schema": {}}])
    _nav.goto(page, app_clean, f"agents/iso-agent/tools/{_nav.seg(sid)}")
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_attribute(
        "aria-expanded", "true", timeout=8000
    )
    expect(page.locator(f'[data-testid="mcp-tool-toggle-{sid}-tool_a"]')).to_be_visible(
        timeout=6000
    )
    # The operator disables a built-in tool elsewhere; re-selecting the open agent
    # re-fetches the operator state and patches in place, so the Built-in tools list
    # rebuilds with the new disabled set.
    seed_tool_config(app_clean, "read_file", enabled=False)
    _lists.list_row(page, "agents", "iso-agent").click()
    page.locator('[data-testid="tab-tools"]').click()
    page.locator(f"{BUILTIN_SECTION} .ui-group-tile-expand").first.click()
    expect(page.locator('.ui-tool-row[data-tool="read_file"]')).to_have_attribute(
        "title", "Disabled by operator", timeout=5000
    )
    expect(page.locator(f'[data-testid="mcp-source-expand-{sid}"]')).to_have_attribute(
        "aria-expanded", "true"
    )
    expect(page.locator(f'[data-testid="mcp-tool-toggle-{sid}-tool_a"]')).to_be_visible()
    expect(page.locator("h2.section-title", has_text="Built-in tools")).to_have_count(1)
    expect(page.locator("h2.section-title", has_text="MCP servers")).to_have_count(1)


@pytest.mark.browser
def test_legacy_mcps_hashes_redirect_to_tools(app_clean: str, page: Page) -> None:
    sid = _seed_http_source(app_clean, "redir-source")
    _seed_agent(app_clean, "redir-agent", {"description": "t"})
    _nav.goto(page, app_clean, "agents/redir-agent/general")
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    _nav.set_route(page, f"agents/redir-agent/mcps/{_nav.seg(sid)}")
    _nav.expect_route(page, f"agents/redir-agent/tools/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    _nav.set_route(page, "agents/redir-agent/mcps")
    _nav.expect_route(page, "agents/redir-agent/tools")
    # A legacy studio hash reaches the Tools form in one history entry.
    before = page.evaluate("history.length")
    page.evaluate(
        "h => { location.hash = h; }",
        _nav.legacy_hash(f"agents/redir-agent/mcps/{_nav.seg(sid)}"),
    )
    _nav.expect_route(page, f"agents/redir-agent/tools/{_nav.seg(sid)}")
    assert page.evaluate("history.length") - before <= 1
