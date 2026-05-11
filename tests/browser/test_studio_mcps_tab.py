"""Browser tests for the F8 L3+L4 Agent-editor MCPs tab.

Tab matches the built-in Tools tab pattern: each MCP source is a
`tool-row` with an attach toggle on the summary line, and a sibling
`<details class="tool-row-overrides">` panel that shows per-tool
checkboxes + credential override fields when expanded.

Tests cover:
  1. Attach a source via toggle → save → reload → still attached.
  2. Detach via toggle → save → reload → no longer attached.
  3. Per-tool toggle (open details panel first) → save → reload → preserved.
  4. Credential override (__MASKED__ round-trip).
  5. Empty state when no MCP sources are registered.
  6. Hash routing: deep-link auto-expands the right `<details>` panel.
  7. Auth-required inline notice (no popup).
  8. App.areas array-shape lock-test.

Tests 3, 4, 6, 7 use page.route() to mock /api/mcp-sources/{id}/test/connect.
"""

from __future__ import annotations

import json

import httpx
import pytest
from playwright.sync_api import Page, expect


# ── Helpers ────────────────────────────────────────────────────────────────


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(f"{base_url}/api/mcp-sources", json=payload, timeout=5.0)
    assert r.status_code in (200, 201), f"seed mcp-source failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _seed_agent(base_url: str, name: str, payload: dict) -> dict:
    payload = dict(payload)
    payload["name"] = name
    r = httpx.post(f"{base_url}/api/agents", json=payload, timeout=5.0)
    assert r.status_code in (200, 201), f"seed agent failed: {r.status_code} {r.text}"
    return r.json()


def _get_agent(base_url: str, name: str) -> dict:
    r = httpx.get(f"{base_url}/api/agents/{name}", timeout=5.0)
    assert r.status_code == 200, f"get agent failed: {r.status_code} {r.text}"
    return r.json()


def _navigate_to_agent_mcps_tab(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}/mcps")
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


def _open_details_panel(page: Page, source_id: str) -> None:
    """Click the details panel's summary so it expands (lazy-loads body)."""
    details = page.locator(f'[data-testid="mcp-source-details-{source_id}"]')
    expect(details).to_be_visible(timeout=4000)
    # Click the summary inside the details. Playwright's locator.click() on
    # <details><summary> works because summary is the click target by default.
    details.locator("summary").click()
    # Confirm expansion via the [open] attribute.
    expect(details).to_have_attribute("open", "", timeout=2000)


# ── Test 1: Attach via toggle → save → reload → still attached ──────────────


@pytest.mark.browser
def test_attach_source_persists(app_clean: str, page: Page) -> None:
    """Toggle a source attached, save, reload, verify it's still attached."""
    sid = _seed_mcp_source(app_clean, {
        "name": "attach-test-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })
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
    toggle.evaluate("el => { el.checked = !el.checked; el.dispatchEvent(new Event('change', {bubbles: true})); }")
    expect(toggle).to_be_checked(timeout=2000)

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    save_btn.click()
    expect(save_btn).to_be_disabled(timeout=5000)

    agent = _get_agent(app_clean, "attach-test-agent")
    assert sid in agent.get("mcp_source_ids", []), \
        f"Expected {sid} in mcp_source_ids, got: {agent.get('mcp_source_ids')}"

    page.reload()
    page.goto(f"{app_clean}#studio/agents/attach-test-agent/mcps")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    toggle2 = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    expect(toggle2).to_have_count(1, timeout=4000)
    expect(toggle2).to_be_checked()


# ── Test 2: Detach via toggle → save → reload → no longer attached ──────────


@pytest.mark.browser
def test_detach_source_persists(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(app_clean, {
        "name": "detach-test-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })
    _seed_agent(app_clean, "detach-test-agent", {
        "description": "test",
        "mcp_source_ids": [sid],
    })

    _navigate_to_agent_mcps_tab(page, app_clean, "detach-test-agent")

    toggle = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    expect(toggle).to_have_count(1, timeout=4000)
    expect(toggle).to_be_checked()

    # Toggle is visually hidden behind the .tool-switch span (mirrors built-in
    # Tools tab); set checked state + fire change event programmatically so the
    # mcps-tab.js change listener runs and the form dirties.
    toggle.evaluate("el => { el.checked = !el.checked; el.dispatchEvent(new Event('change', {bubbles: true})); }")
    expect(toggle).not_to_be_checked(timeout=2000)

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    with page.expect_response(lambda r: "/api/agents/detach-test-agent" in r.url and r.request.method == "PUT") as resp_info:
        save_btn.click()
    resp = resp_info.value
    assert resp.status == 200, f"PUT failed: {resp.status} {resp.text()}"
    expect(save_btn).to_be_disabled(timeout=5000)

    agent = _get_agent(app_clean, "detach-test-agent")
    assert sid not in agent.get("mcp_source_ids", []), \
        f"Expected {sid} absent from mcp_source_ids, got: {agent.get('mcp_source_ids')}"

    page.reload()
    page.goto(f"{app_clean}#studio/agents/detach-test-agent/mcps")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    toggle2 = page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')
    expect(toggle2).to_have_count(1, timeout=4000)
    expect(toggle2).not_to_be_checked()


# ── Test 3: Per-tool toggle → save → reload → toggles preserved ─────────────


@pytest.mark.browser
def test_per_tool_toggle_persists(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(app_clean, {
        "name": "toggle-test-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })
    _seed_agent(app_clean, "toggle-test-agent", {
        "description": "test",
        "mcp_source_ids": [sid],
    })

    tools_payload = [
        {"name": "tool_a", "description": "tool a", "input_schema": {}},
        {"name": "tool_b", "description": "tool b", "input_schema": {}},
    ]
    _mock_tools_connect(page, sid, tools_payload)

    _navigate_to_agent_mcps_tab(page, app_clean, "toggle-test-agent")

    # Open the details panel — that lazy-loads the per-tool checkboxes.
    _open_details_panel(page, sid)

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
    page.goto(f"{app_clean}#studio/agents/toggle-test-agent/mcps/{sid}")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    # Deep-link auto-opens the details panel.
    details = page.locator(f'[data-testid="mcp-source-details-{sid}"]')
    expect(details).to_have_attribute("open", "", timeout=4000)
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
    expect(empty).to_contain_text("Add one in MCP Sources")

    link = empty.locator("a")
    expect(link).to_have_attribute("href", "#studio/mcp-sources")


# ── Test 6: Hash routing — deep-link auto-expands details ─────────────────────


@pytest.mark.browser
def test_hash_routing_deep_link(app_clean: str, page: Page) -> None:
    """Visit #studio/agents/{name}/mcps/{source-id} → details panel auto-expands."""
    sid = _seed_mcp_source(app_clean, {
        "name": "deeplink-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })
    _seed_agent(app_clean, "deeplink-agent", {
        "description": "test",
        "mcp_source_ids": [sid],
    })

    _mock_tools_connect(page, sid, [
        {"name": "list_repos", "description": "list repos", "input_schema": {}},
    ])

    page.goto(f"{app_clean}#studio/agents/deeplink-agent/mcps/{sid}")
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )

    # Details panel should be open.
    details = page.locator(f'[data-testid="mcp-source-details-{sid}"]')
    expect(details).to_have_attribute("open", "", timeout=4000)

    # Tools should load from mocked endpoint.
    expect(page.locator(f'[data-testid="mcp-tool-toggle-{sid}-list_repos"]')).to_be_visible(timeout=6000)


# ── Test 7: Auth-required inline notice — no popup ────────────────────────────


@pytest.mark.browser
def test_auth_required_inline_notice_no_popup(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(app_clean, {
        "name": "auth-required-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })
    _seed_agent(app_clean, "auth-required-agent", {
        "description": "test",
        "mcp_source_ids": [sid],
    })

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
    _open_details_panel(page, sid)

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
    assert "mcp-sources" in href, f"Link should point to mcp-sources, got: {href}"
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
    sid = _seed_mcp_source(app_clean, {
        "name": "test_source_friendly_name",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })
    _seed_agent(app_clean, "name-id-test-agent", {
        "description": "test",
        "mcp_source_ids": [sid],
    })

    def handle_auth_required(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "status": "auth_required",
                "consent_url": "https://idp.example.com/oauth/authorize",
            }),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_auth_required)

    _navigate_to_agent_mcps_tab(page, app_clean, "name-id-test-agent")
    _open_details_panel(page, sid)

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
