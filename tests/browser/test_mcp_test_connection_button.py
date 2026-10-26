"""Browser tests for the F6.5 L3 Refresh-connection button in the MCP source editor.

Tests the Refresh-connection button (renamed from "Test connection" at F9 L1)
that appears in edit-mode for streamable-http sources. Verifies button
visibility, click behavior, and result panel rendering.

Because driving a real OAuth popup flow from Playwright is complex (requires
a popup window fixture and real OAuth server), these tests use the simplified
approach described in the leg's Step 5 fallback guidance:
  - Verify button renders for streamable-http sources in edit-mode
  - Verify button is absent in create-mode
  - Verify button is absent for stdio sources
  - Verify button click triggers the test connection API and renders a result
    (mocked via httpx interceptor or direct endpoint call with a source that
    has no creds, expecting an error response from the endpoint)

Any browser-test compromises are documented in the flight log Anomalies section.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(
        f"{base_url}/api/mcp-sources", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code in (200, 201), f"seed failed: {r.status_code} {r.text}"
    return r.json()["id"]


@pytest.mark.browser
def test_test_connection_button_visible_for_streamable_http_edit_mode(
    app_clean: str, page: Page
) -> None:
    """Test button renders only in edit-mode for streamable-http sources."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "test-btn-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # M31 F5 L08b (B2): Test is the header's button, with a play icon before the
    # label; the data-testid hook stays "mcp-test-connection".
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible()
    expect(test_btn).to_have_text("Test")
    expect(test_btn.locator("svg")).to_be_visible()

    # The result area is hidden at rest (the status line says "Not connected");
    # the Tools section carries the empty-state hint, and the list is hidden until
    # the first successful Test.
    expect(page.locator('[data-testid="mcp-test-status"]')).to_be_hidden()
    expect(page.locator('[data-testid="mcp-connection-status"]')).to_contain_text("Not connected")
    expect(page.locator(".mcp-tools-empty")).to_have_text("Press Test to load this server's tools.")
    tools_list = page.locator('[data-testid="mcp-tools-list"]')
    expect(tools_list).to_be_hidden()


@pytest.mark.browser
def test_test_connection_button_absent_in_create_mode(app_clean: str, page: Page) -> None:
    """Test button is NOT rendered in create-mode (source has no id yet)."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Test button must NOT appear in create-mode.
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_have_count(0)


@pytest.mark.browser
def test_test_connection_button_present_for_stdio_source(app_clean: str, page: Page) -> None:
    """F9 L2 D1: Refresh-connection button DOES render for stdio sources.

    Inverted from the prior "absent for stdio" assertion: stdio Test
    connection support shipped as a structural prerequisite for L2's
    create+test workflow, mirroring streamable-http's surface (capability
    flags + collapsible schemas + Last-updated label all share one render
    path now). The stdio backend dispatch is a transient-client lifecycle
    — no OAuth, no popup — so the Reset button stays absent (gated by
    hasOAuthState which is false for stdio).
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "stdio-source",
            "type": "stdio",
            "config": {"command": "github-mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # F9 L2 D1: Test visible for stdio sources too (the same status row and Tools hint).
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible()
    expect(test_btn).to_have_text("Test")
    expect(test_btn.locator("svg")).to_be_visible()

    expect(page.locator('[data-testid="mcp-test-status"]')).to_be_hidden()
    expect(page.locator(".mcp-tools-empty")).to_have_text("Press Test to load this server's tools.")
    tools_list = page.locator('[data-testid="mcp-tools-list"]')
    expect(tools_list).to_be_hidden()

    # Reset button still absent for stdio (no OAuth state).
    reset_btn = page.locator('[data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_have_count(0)


@pytest.mark.browser
def test_test_connection_button_click_shows_result(app_clean: str, page: Page) -> None:
    """Clicking the Test button disables it and shows a result panel response.

    This test seeds a streamable-http source that has no dcr_credentials and
    no access_token. The endpoint will attempt Phase B (kick OAuth flow) and
    since the URL doesn't resolve to a real MCP server, it will either return
    an error or timeout (with _TEST_CONNECT_TIMEOUT=15s in the app).

    We verify:
    - Button becomes disabled on click
    - Result panel becomes visible with "Testing connection..." text
    - Eventually the result panel shows some response (error is fine — it
      proves the round-trip happened)

    Note: The actual OAuth popup flow is NOT tested here because it requires
    a running OAuth server fixture. That path is covered by L4 HAT (live
    Cloudflare API MCP test). This test verifies the UI mechanics only.

    ANOMALY (documented in flight log): The full popup-flow browser test
    (Phase 1 → popup → Phase 2 → tools list) requires an in-repo OAuth
    fixture that auto-consents. The existing browser test pattern
    (test_oauth_modal_flow.py) synthesizes WS events directly without a real
    OAuth server. For the Test button, the equivalent synthetic approach
    would require injecting a fake /api/mcp-sources/{id}/test/connect
    response into the running app, which is harder to do without a dedicated
    fixture. We test the button render + click mechanics here; the full
    popup-flow is verified in L4 HAT (live test, human-verified).
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "test-btn-click-source",
            "type": "streamable-http",
            "config": {"url": "https://invalid-host.example-does-not-exist.com/mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible(timeout=8000)

    # Pre-click: the result area is hidden and the tools list is hidden.
    status_panel = page.locator('[data-testid="mcp-test-status"]')
    tools_list = page.locator('[data-testid="mcp-tools-list"]')
    expect(status_panel).to_be_hidden()
    expect(tools_list).to_be_hidden()

    # Squawk 0216: hold the /test/connect response so the transient state is
    # asserted before the (instant, in a loopback namespace) failure can replace it.
    held: list = []
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: held.append(route) if route.request.method == "POST" else route.fallback(),
    )

    # Click the button.
    test_btn.click()

    # Button should be disabled immediately (concurrent-Test guard).
    expect(test_btn).to_be_disabled()

    # The result area reads "Testing connection…" (note: ellipsis character U+2026,
    # not three ASCII dots) until the response lands.
    expect(status_panel).to_have_text("Testing connection…")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(20)
    assert held, "the /test/connect request was not held"
    held[0].continue_()

    # Wait for the result to update (endpoint responds with error or auth_required).
    # The endpoint will fail quickly since the URL is unreachable, but we give it
    # up to 20s to avoid flakiness in slow environments. We don't assert on the
    # specific error message — just that the status panel updated away from
    # "Testing connection…" and the button is re-enabled (settle() ran).
    page.wait_for_function(
        "() => {"
        "  var el = document.querySelector('[data-testid=\"mcp-test-status\"]');"
        "  var btn = document.querySelector('[data-testid=\"mcp-test-connection\"]');"
        "  return el && el.textContent !== 'Testing connection\\u2026' && btn && !btn.disabled;"
        "}",
        timeout=20000,
    )

    # Status panel has some non-empty text that's not the in-progress text.
    status_text = status_panel.inner_text()
    assert status_text != "Testing connection…"
    assert len(status_text.strip()) > 0

    # Button is re-enabled (settle() ran on terminal state).
    expect(test_btn).not_to_be_disabled()


# ─── F8 L2: Tools-polish browser tests ────────────────────────────────────
# These tests use page.route() to mock /api/mcp-sources/{id}/test/connect with
# a synthetic JSON payload so the UI renders without a real MCP server.
#
# PATTERN (first use of page.route() in this codebase — referenceable for L3):
#   1. Seed a real source via _seed_mcp_source (so the page loads its edit form).
#   2. Register a route handler with page.route() BEFORE page.goto() so the
#      interceptor is in place when the page loads and the user clicks Test.
#   3. The handler calls route.fulfill(status=..., content_type=..., body=...)
#      synchronously — no await needed (Playwright Python sync API).
#   4. Assert the rendered DOM after clicking the Test connection button.
#
# Use route.fulfill(body=json.dumps(...)) rather than route.fulfill(json={...})
# because the sync Playwright API (1.x) doesn't always support the `json=`
# keyword shorthand. Passing `body` + `content_type` is explicit and portable.


@pytest.mark.browser
def test_capability_flags_render_for_announced_capabilities(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """L2.1: the server-info panel's capability flags list only announced keys.

    The editor mounts the Server section from ``source.config._cache`` (the
    API drops an operator-supplied ``_cache``, so the cache is seeded the way
    /test/connect persists it: straight into the source row). Asserts the
    rendered "Offers" fact names exactly the announced
    (non-null) capabilities and none of the un-announced ones.
    """
    app_clean, data_dir = app_with_data_dir
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "polish-cap-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    cache = {
        "tools": [],
        "server_info": {"name": "cap-server", "version": "1.2.3"},
        "capabilities": {
            "tools": {},
            "resources": {},
            "prompts": None,
            "logging": None,
            "completions": None,
            "tasks": None,
        },
    }
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        row = conn.execute("SELECT config FROM mcp_sources WHERE id = ?", (sid,)).fetchone()
        config = json.loads(row[0])
        config["_cache"] = cache
        conn.execute("UPDATE mcp_sources SET config = ? WHERE id = ?", (json.dumps(config), sid))
        conn.commit()
    finally:
        conn.close()

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    section = page.locator('[data-testid="mcp-server-info-section"]')
    expect(section).to_be_visible(timeout=4000)
    offers = section.locator('[data-testid="mcp-server-offers"] dd')
    expect(offers).to_be_visible()
    # Positive assertions: tools and resources were non-null -> rendered, capitalised.
    expect(offers).to_have_text("Tools, Resources")
    # Negative assertions: prompts/logging/completions/tasks were null -> not rendered.
    offers_text = offers.inner_text().lower()
    for absent in ("prompts", "logging", "completions", "tasks"):
        assert absent not in offers_text


@pytest.mark.browser
def test_input_schema_renders_pretty_json_in_tool_body(app_clean: str, page: Page) -> None:
    """L2.3 (updated for Leg 03): input_schema renders as an always-visible <pre> in the tool body.

    Leg 03 MCP polish replaced the nested nested schema <details> with a
    labeled "Input Schema" section directly in the tool body. No inner collapsible click
    is needed — expanding the outer tool <details> reveals the <pre> immediately.

    Stubs /test/connect to return one tool with a non-empty input_schema.
    Expands the outer tool <details> and asserts the <pre> body contains
    the exact pretty-printed JSON.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "polish-schema-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    stub_payload = {
        "status": "ok",
        "tools": [{"name": "echo", "description": "echo back", "input_schema": schema}],
        "capabilities": {
            "tools": {},
            "resources": None,
            "prompts": None,
            "logging": None,
            "completions": None,
            "tasks": None,
        },
    }

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="mcp-test-connection"]').click()

    # Wait for the tools list to render.
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible(timeout=4000)

    # Expand the outer tool <details> to reveal the Input Schema section body.
    outer_details = page.locator('[data-testid="mcp-tool-item"]').first
    outer_details.locator("summary").click()

    # Leg 03: schema is always-visible as a <pre> inside the labeled Input Schema section.
    # No inner collapsible click needed.
    pre = page.locator('[data-testid="mcp-tool-schema"]')
    expect(pre).to_be_visible(timeout=4000)
    expected_json = json.dumps(schema, indent=2)
    expect(pre).to_have_text(expected_json)


@pytest.mark.browser
def test_empty_input_schema_does_not_render_schema_details(app_clean: str, page: Page) -> None:
    """L2.4 (negative): tools with input_schema: {} do NOT get a nested schema view.

    Stubs /test/connect to return one tool with an empty dict input_schema.
    Expands the outer tool <details> and asserts the schema block is absent.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "polish-empty-schema-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    stub_payload = {
        "status": "ok",
        "tools": [{"name": "echo", "description": "echo back", "input_schema": {}}],
        "capabilities": {
            "tools": {},
            "resources": None,
            "prompts": None,
            "logging": None,
            "completions": None,
            "tasks": None,
        },
    }

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="mcp-test-connection"]').click()

    # Wait for the tools list to render.
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible(timeout=4000)

    # Expand the outer tool <details> — schema toggle must NOT appear.
    outer_details = page.locator('[data-testid="mcp-tool-item"]').first
    outer_details.locator("summary").click()

    # Negative assertion: empty input_schema → no schema block, only the empty note.
    expect(page.locator('[data-testid="mcp-tool-schema"]')).to_have_count(0)
    expect(outer_details).to_contain_text("No input schema.")
