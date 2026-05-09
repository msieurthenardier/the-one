"""Browser tests for the F6.5 L3 Test Connection button in the MCP source editor.

Tests the Test connection button that appears in edit-mode for streamable-http
sources. Verifies button visibility, click behavior, and result panel rendering.

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

    # Test connection button visible in edit-mode for streamable-http.
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible()
    expect(test_btn).to_have_text("Test connection")

    # Tools section: status div renders the empty-state prompt; tools list
    # is hidden until the first successful Test click. (L4 UX restructure
    # replaced the prior single `mcp-test-result` panel with the two
    # status/list testids; see flight log L4 entry.)
    status_panel = page.locator('[data-testid="mcp-test-status"]')
    expect(status_panel).to_be_visible()
    expect(status_panel).to_contain_text("Click")
    expect(status_panel).to_contain_text("Test connection")
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
