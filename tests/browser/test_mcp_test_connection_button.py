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

import httpx
import json
import pytest
from playwright.sync_api import Page, expect


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(f"{base_url}/api/mcp-sources", json=payload, timeout=5.0)
    assert r.status_code in (200, 201), f"seed failed: {r.status_code} {r.text}"
    return r.json()["id"]


@pytest.mark.browser
def test_test_connection_button_visible_for_streamable_http_edit_mode(
    app_clean: str, page: Page
) -> None:
    """Test button renders only in edit-mode for streamable-http sources."""
    sid = _seed_mcp_source(app_clean, {
        "name": "test-btn-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # F9 L1: Refresh-connection button visible in edit-mode for streamable-http.
    # The data-testid hook stays "mcp-test-connection" (stable selector); the
    # visible label changed to "Refresh connection" with a refresh icon.
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible()
    expect(test_btn).to_contain_text("Refresh connection")
    # Refresh icon sits inline before the label.
    expect(test_btn.locator("svg")).to_be_visible()

    # Tools section: status div renders the empty-state prompt; tools list
    # is hidden until the first successful Refresh click. (L4 UX restructure
    # replaced the prior single `mcp-test-result` panel with the two
    # status/list testids; see flight log L4 entry.)
    status_panel = page.locator('[data-testid="mcp-test-status"]')
    expect(status_panel).to_be_visible()
    expect(status_panel).to_contain_text("Click")
    expect(status_panel).to_contain_text("Refresh connection")
    tools_list = page.locator('[data-testid="mcp-tools-list"]')
    expect(tools_list).to_be_hidden()


@pytest.mark.browser
def test_test_connection_button_absent_in_create_mode(
    app_clean: str, page: Page
) -> None:
    """Test button is NOT rendered in create-mode (source has no id yet)."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Test button must NOT appear in create-mode.
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_have_count(0)


@pytest.mark.browser
def test_test_connection_button_absent_for_stdio_source(
    app_clean: str, page: Page
) -> None:
    """Test button is NOT rendered for stdio sources (only streamable-http)."""
    sid = _seed_mcp_source(app_clean, {
        "name": "stdio-source",
        "type": "stdio",
        "config": {"command": "github-mcp"},
        "secrets": {},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Test button must NOT appear for stdio sources.
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_have_count(0)


@pytest.mark.browser
def test_test_connection_button_click_shows_result(
    app_clean: str, page: Page
) -> None:
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
    sid = _seed_mcp_source(app_clean, {
        "name": "test-btn-click-source",
        "type": "streamable-http",
        "config": {"url": "https://invalid-host.example-does-not-exist.com/mcp"},
        "secrets": {},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible(timeout=8000)

    # L4 UX restructure: the prior single `mcp-test-result` panel was split
    # into a `mcp-test-status` div (always visible; carries status text) and
    # a `mcp-tools-list` div (hidden until tools render). Pre-click, the
    # status div carries the empty-state prompt; tools list is hidden.
    status_panel = page.locator('[data-testid="mcp-test-status"]')
    tools_list = page.locator('[data-testid="mcp-tools-list"]')
    expect(status_panel).to_be_visible()
    expect(tools_list).to_be_hidden()

    # Click the button.
    test_btn.click()

    # Button should be disabled immediately (concurrent-Test guard).
    expect(test_btn).to_be_disabled()

    # Status panel should update to "Testing connection…" (note: ellipsis
    # character U+2026, not three ASCII dots).
    expect(status_panel).to_have_text("Testing connection…")

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
    app_clean: str, page: Page
) -> None:
    """L2.1: capability flags show the spec-defined keys whose values are non-null.

    Stubs /test/connect to return capabilities with tools+resources announced
    (non-null) and prompts/logging/completions/tasks as None. Asserts the
    rendered .mcp-capability-flags one-liner contains exactly the announced
    capabilities and none of the un-announced ones.
    """
    sid = _seed_mcp_source(app_clean, {
        "name": "polish-cap-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })

    stub_payload = {
        "status": "ok",
        "tools": [{"name": "echo", "description": "echo back", "input_schema": {}}],
        "capabilities": {
            "tools": {},
            "resources": {},
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

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    test_btn.click()

    flags = page.locator(".mcp-capability-flags")
    expect(flags).to_be_visible(timeout=4000)
    # Positive assertions: tools and resources were non-null → rendered.
    expect(flags).to_contain_text("tools")
    expect(flags).to_contain_text("resources")
    # Negative assertions: prompts/logging/completions/tasks were null → not rendered.
    flags_text = flags.inner_text()
    assert "prompts" not in flags_text
    assert "logging" not in flags_text
    assert "completions" not in flags_text
    assert "tasks" not in flags_text


@pytest.mark.browser
def test_input_schema_collapsible_renders_pretty_json(
    app_clean: str, page: Page
) -> None:
    """L2.3: input_schema renders inside a nested <details>; opens to show pretty JSON.

    Stubs /test/connect to return one tool with a non-empty input_schema.
    Expands the outer tool <details>, then the inner schema <details>, and
    asserts the <pre> body contains the exact pretty-printed JSON.
    """
    sid = _seed_mcp_source(app_clean, {
        "name": "polish-schema-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })

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

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="mcp-test-connection"]').click()

    # Wait for the tools list to render.
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible(timeout=4000)

    # Expand the outer tool <details> to reveal the nested schema toggle.
    outer_details = page.locator(".mcp-tool-item").first
    outer_details.locator(".mcp-tool-summary").click()

    # The nested schema <details> and its summary should now be visible.
    schema_summary = page.locator(".mcp-tool-schema-summary")
    expect(schema_summary).to_be_visible(timeout=4000)

    # Click to expand the schema <details>.
    schema_summary.click()

    # The <pre> content block should become visible with the exact JSON.
    pre = page.locator(".mcp-tool-schema-content")
    expect(pre).to_be_visible()
    expected_json = json.dumps(schema, indent=2)
    expect(pre).to_have_text(expected_json)


@pytest.mark.browser
def test_empty_input_schema_does_not_render_schema_details(
    app_clean: str, page: Page
) -> None:
    """L2.4 (negative): tools with input_schema: {} do NOT get a nested schema view.

    Stubs /test/connect to return one tool with an empty dict input_schema.
    Expands the outer tool <details> and asserts .mcp-tool-schema is absent.
    """
    sid = _seed_mcp_source(app_clean, {
        "name": "polish-empty-schema-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })

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

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="mcp-test-connection"]').click()

    # Wait for the tools list to render.
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible(timeout=4000)

    # Expand the outer tool <details> — schema toggle must NOT appear.
    outer_details = page.locator(".mcp-tool-item").first
    outer_details.locator(".mcp-tool-summary").click()

    # Negative assertion: empty input_schema → no .mcp-tool-schema element.
    expect(page.locator(".mcp-tool-schema")).to_have_count(0)
