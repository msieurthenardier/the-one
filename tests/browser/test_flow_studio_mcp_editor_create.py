# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""MCP source editor browser tests: create, edit, delete and the create-form Save.

Split from test_flow_studio_mcp_editor.py (squawk 0271); shared helpers live in
browser/_mcp_editor.py."""

from __future__ import annotations

import json
import re

import pytest
from browser import _lists, _nav
from browser._mcp_editor import (
    _get_source,
    _kv_key,
    _kv_row_by_key,
    _kv_rows,
    _kv_title,
    _kv_val,
    _list_sources,
    _seed_mcp_source,
)
from playwright.sync_api import Page, expect

# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_mcp_created_toast_survives_the_remount(app_clean: str, page: Page) -> None:
    """DD5: the toast belongs to the page, so the create -> edit remount cannot take it."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("toast-mcp")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("echo")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    page.wait_for_timeout(200)
    expect(page.locator(".app-flash")).to_have_text("MCP server created")
    expect(page.locator(".app-flash")).to_be_visible()


@pytest.mark.browser
def test_create_stdio_source(app_clean: str, page: Page) -> None:
    """Fill the create form for a stdio source, save, see it in the Library list."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("github-mcp")
    page.locator('[data-field="type"]').select_option("stdio")
    # F9 L2 vibing: command is now a dropdown with `uvx` selected by
    # default. Switch to Custom… and fill the legacy free-text input so
    # this test continues to exercise the Custom-escape save path.
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("github-mcp")

    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).not_to_be_disabled()
    save_btn.click()

    # Save flash + create→edit transition: Danger Zone now visible, and the
    # new row is in the Library list beside the editor (M25 F3 L4a).
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    _lists.expect_selected(page, "library/mcp", "github-mcp")

    # Close to the section root through the breadcrumb's "MCP servers" link
    # (M25 F3 L4b retired Back).
    _lists.close_item(page)
    expect(_lists.library_start(page)).to_be_visible(timeout=5000)
    expect(_lists.list_row(page, "library/mcp", "github-mcp")).to_be_visible()


@pytest.mark.browser
def test_edit_stdio_source_preserves_unchanged_secrets(app_clean: str, page: Page) -> None:
    """Edit only the name; per-key __MASKED__ preserves stored secret."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "GH",
            "type": "stdio",
            "config": {"command": "github-mcp", "env": {}},
            "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # The connection status row is left-aligned with the editor's stacked fields
    # (HAT: it was indented by the legacy .field-row label gutter).
    status_box = page.locator('[data-testid="mcp-connection-status"]').bounding_box()
    name_box = page.locator('[data-field="name"]').bounding_box()
    assert status_box is not None and name_box is not None
    assert abs(status_box["x"] - name_box["x"]) <= 2, (status_box, name_box)

    # Sensitive env var pre-fills with the masked tail (***...alue).
    kv_value = page.get_by_label("Value, row 1", exact=True)
    expect(kv_value).to_have_value("***...alue")

    # Change ONLY the name
    page.locator('[data-field="name"]').fill("GH-renamed")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    # Wait for save flash.
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    src = _get_source(app_clean, sid)
    assert src["name"] == "GH-renamed"
    # Stored secret preserved — masked tail still matches.
    assert src["secrets"]["GITHUB_TOKEN"] == "***...alue"


@pytest.mark.browser
def test_edit_streamable_http_source_changes_one_secret(app_clean: str, page: Page) -> None:
    """Two sensitive headers; change one, leave the other untouched.

    The unchanged one routes via __MASKED__ → backend preserves the
    ciphertext. The changed one routes as plaintext → backend overwrites.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "remote",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp", "headers": {}},
            "secrets": {
                "Authorization": "Bearer-original-aaaa",
                "X-Api-Key": "original-bbbb-key",
            },
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Identify which row is which by inspecting the key inputs.
    rows = _kv_rows(page)
    expect(rows).to_have_count(2)

    # Find the Authorization row by key text and change its value.
    _kv_val(_kv_row_by_key(page, "Authorization")).fill("Bearer-NEW-cccc")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    src = _get_source(app_clean, sid)
    # Authorization: 16 chars → ***...cccc (last 4)
    assert src["secrets"]["Authorization"] == "***...cccc"
    # X-Api-Key untouched: 17 chars → ***...-key (last 4 of "original-bbbb-key")
    assert src["secrets"]["X-Api-Key"] == "***...-key"


@pytest.mark.browser
def test_delete_stdio_source(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "delete-me",
            "type": "stdio",
            "config": {"command": "x"},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    # First click arms.
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))
    # Second click commits.
    delete_btn.click()
    # Land on the section root; the row is gone.
    expect(_lists.library_start(page)).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library")
    # HAT: the toast outlives the closed editor (it is flashed to the page, not the editor).
    expect(page.locator(".app-flash").filter(has_text="MCP server deleted")).to_be_visible(
        timeout=3000
    )
    expect(page.locator('[data-testid="mcp-source-card"]')).to_have_count(0)
    assert _list_sources(app_clean) == []


@pytest.mark.browser
def test_delete_streamable_http_source(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "delete-remote",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))
    delete_btn.click()
    expect(_lists.library_start(page)).to_be_visible(timeout=5000)
    assert _list_sources(app_clean) == []


@pytest.mark.browser
def test_delete_mcp_source_confirm_lapse_is_visually_distinct(app_clean: str, page: Page) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the Danger Zone MCP
    server delete confirm (`mcp-server-editor.js:1270`) is distinguishable
    on screen from one that was never armed, past the real 3s `revertMs`."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "delete-lapse-me",
            "type": "stdio",
            "config": {"command": "x"},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    # Still on the editor (not reverted-then-navigated) and never deleted.
    assert sid in [s["id"] for s in _list_sources(app_clean)]


@pytest.mark.browser
def test_dirty_breadcrumb_close_confirm_dialog(app_clean: str, page: Page) -> None:
    """Dirty editor + the breadcrumb's root link (Back is retired, M25 F3 L4b)
    → confirmDialog; Cancel keeps editor mounted."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Make the form dirty.
    page.locator('[data-field="name"]').fill("typed-name")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).not_to_be_disabled()

    # Click the breadcrumb's "MCP servers" link; modal appears.
    _lists.close_item(page)
    expect(page.locator(".modal-overlay")).to_be_visible(timeout=5000)
    # Cancel (Stay) — editor stays mounted.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(page.locator(".modal-overlay")).to_have_count(0)
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible()
    # Field value preserved.
    expect(page.locator('[data-field="name"]')).to_have_value("typed-name")


@pytest.mark.browser
def test_type_change_swaps_field_visibility(app_clean: str, page: Page) -> None:
    """Switch type stdio→streamable-http: command hidden, url visible,
    kv-label changes."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")
    # Command field visible; URL field hidden; kv label = "Environment Variables".
    expect(page.locator(".mcp-stdio-only").first).to_be_visible()
    expect(page.locator(".mcp-streamable-http-only").first).to_be_hidden()
    expect(_kv_title(page)).to_have_text("Environment variables")

    # Switch to streamable-http
    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(page.locator(".mcp-stdio-only").first).to_be_hidden()
    expect(page.locator(".mcp-streamable-http-only").first).to_be_visible()
    expect(_kv_title(page)).to_have_text("Headers")
    expect(page.get_by_test_id("mcp-kv-table")).to_have_accessible_name("Headers")


@pytest.mark.browser
def test_save_with_empty_kv_key_row_silently_skips(app_clean: str, page: Page) -> None:
    """Add an empty kv row PLUS a populated row; save; only the populated
    row persists. Empty key is dropped at partition time."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("test-skip-empty")
    page.locator('[data-field="type"]').select_option("stdio")
    # F9 L2 vibing: dropdown defaults to `uvx`; no explicit command needed.

    # Add two empty rows.
    add_btn = page.locator('[data-testid="kv-add-row-btn"]')
    add_btn.click()
    add_btn.click()
    rows = _kv_rows(page)
    expect(rows).to_have_count(2)
    # Populate the first row only.
    _kv_key(rows.nth(0)).fill("DEBUG")
    _kv_val(rows.nth(0)).fill("1")
    # Leave the second row entirely empty.

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    assert sources[0]["config"].get("env") == {"DEBUG": "1"}
    # Empty-key row was NOT persisted.
    assert "" not in sources[0]["config"].get("env", {})
    assert "" not in sources[0].get("secrets", {})


# ── Item 3: auto-run Refresh on create-form Save success ─────────────────


@pytest.mark.browser
def test_create_streamable_http_auto_runs_refresh(app_clean: str, page: Page) -> None:
    """After Save on the create form for a streamable-http source, the
    Refresh-connection code path fires automatically — operator does NOT
    need to click Refresh manually.

    Stubs /test/connect to return ok with one tool. Verifies the Tools
    section populates without any explicit Refresh click after Save.
    """
    # Stub /test/connect for any source id (we don't know the id pre-create).
    stub_payload = {
        "status": "ok",
        "tools": [{"name": "echo", "description": "auto-fired", "input_schema": {}}],
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

    page.route("**/api/mcp-sources/*/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("auto-refresh-source")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")

    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).not_to_be_disabled()
    save_btn.click()

    # Post-Save → editor re-renders in edit mode (Danger Zone visible).
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    # Auto-run Refresh fires immediately: tools list populates without
    # operator clicking Refresh.
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible(timeout=8000)
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1)
    expect(page.locator('[data-testid="mcp-test-status"]')).to_be_hidden()


@pytest.mark.browser
def test_create_streamable_http_auto_run_auth_required_does_not_open_popup(
    app_clean: str, page: Page
) -> None:
    """When the auto-run after Save returns auth_required, the UI must
    surface a "Sign in" consent button instead of opening the OAuth
    popup automatically — the Save click's user-gesture context is lost
    by the time auth_required surfaces, and popup blockers reject popups
    not driven by direct interaction.

    Spies on window.open to assert it is NOT called by the auto-run
    code path. Asserts the consent affordance (a button with
    data-testid="mcp-consent-btn") renders into the status panel.
    """
    stub_payload = {
        "status": "auth_required",
        "consent_url": "https://example.com/oauth/authorize?fake=1",
    }

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route("**/api/mcp-sources/*/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Spy on window.open BEFORE Save fires; record any invocation.
    page.evaluate(
        "() => { window.__popupOpens = 0; "
        "var orig = window.open; "
        "window.open = function () { window.__popupOpens += 1; return null; };"
        "window.__origOpen = orig; }"
    )

    page.locator('[data-field="name"]').fill("auto-auth-required")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")
    page.locator('[data-testid="save-mcp-source-btn"]').click()

    # Editor enters edit mode.
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    # Consent affordance surfaces.
    consent_btn = page.locator('[data-testid="mcp-consent-btn"]')
    expect(consent_btn).to_be_visible(timeout=8000)
    expect(consent_btn).to_have_text("Sign in")

    # window.open was NOT called by the auto-run path.
    popup_count = page.evaluate("() => window.__popupOpens")
    assert popup_count == 0, f"auto-run must not open popup; got {popup_count}"

    # Sortie 04: clicking "Sign in" is the user gesture; it shows the link block
    # (the stubbed window.open returns null, which is not an error) and tries
    # window.open exactly once.
    consent_btn.click()
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_value(
        "https://example.com/oauth/authorize?fake=1", timeout=8000
    )
    expect(page.locator('[data-testid="mcp-test-status"]')).not_to_contain_text("Popup blocked")
    assert page.evaluate("() => window.__popupOpens") == 1


@pytest.mark.browser
def test_create_streamable_http_auto_run_error_renders_inline(app_clean: str, page: Page) -> None:
    """When the auto-run after Save returns an error (bad config / bogus
    URL / etc.), the error renders inline in the status panel — operator
    sees what's wrong without clicking Refresh."""
    stub_payload = {"status": "error", "error": "transport unreachable"}

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route("**/api/mcp-sources/*/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("auto-error-source")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")
    page.locator('[data-testid="save-mcp-source-btn"]').click()

    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    # Error text surfaces in the status panel.
    expect(page.locator('[data-testid="mcp-test-status"]')).to_contain_text(
        "transport unreachable", timeout=8000
    )


@pytest.mark.browser
def test_create_stdio_does_not_attempt_auto_run(app_clean: str, page: Page) -> None:
    """F9 L2 D1: stdio sources DO expose the Test button now (post-D1),
    but the auto-run-on-create code path remains streamable-http-only per
    studio.js's gate. After save, the editor enters edit mode showing the
    Refresh button + empty Tools section, but the status panel still
    reads the empty-state prompt (auto-run did NOT fire — no
    "Testing connection…" / "✓ Connected" banner)."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("stdio-no-auto")
    page.locator('[data-field="type"]').select_option("stdio")
    # F9 L2 vibing: dropdown defaults to `uvx`; switch to Custom… so the
    # saved command preserves this test's "github-mcp" semantic value.
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("github-mcp")
    page.locator('[data-testid="save-mcp-source-btn"]').click()

    # Editor enters edit mode; Refresh button + Tools section render (D1).
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_have_count(1)
    expect(page.locator('[data-testid="mcp-tools-section"]')).to_have_count(1)
    # Auto-run did NOT fire for stdio: the result area is still hidden, the Tools
    # section still carries the hint asking the operator to press Test.
    expect(page.locator('[data-testid="mcp-test-status"]')).to_be_hidden()
    expect(page.locator(".mcp-tools-empty")).to_contain_text("Press Test")
    # Tools list stays hidden (no auto-run populated it).
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_hidden()


# ─── F9 L2 vibing: defense-in-depth resp.ok check ───────────────────────


@pytest.mark.browser
def test_test_connection_500_response_renders_useful_error(app_clean: str, page: Page) -> None:
    """A non-JSON 500 from /test/connect renders a useful error.

    F9 L2 vibing — the frontend's resp.ok check converts a 500 with HTML
    body into a structured Error('Server error 500 …') instead of letting
    resp.json() choke on "Unexpected token <". This test pins the
    operator-facing UX: the rendered status panel must contain the HTTP
    status (so the operator knows it's a server-side fault) AND a snippet
    of the body (so they have something to grep / report).

    Backend half of the same defense-in-depth (catch-all envelope in the
    helpers) is covered by test_mcp_stdio_test_connect.py. Both halves
    must hold for the contract to be solid; either alone would still
    leave a gap.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "broken-source",
            "type": "stdio",
            "config": {"command": "python", "args": ["-m", "x"]},
            "secrets": {},
        },
    )

    # Simulate FastAPI returning a 500 with an HTML body — this is the
    # exact shape that triggered the original "Unexpected token <" bug.
    html_500_body = (
        "<html><body><h1>Internal Server Error</h1>"
        "<p>asyncio.CancelledError leaked from teardown.</p></body></html>"
    )

    def handle_test_connect(route):
        route.fulfill(
            status=500,
            content_type="text/html",
            body=html_500_body,
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    test_btn.click()

    status_panel = page.locator('[data-testid="mcp-test-status"]')
    # The .catch handler renders "error block (headline + raw text under Technical details)" — the
    # message must include "Server error 500" (so the operator knows the
    # server side faulted) and NOT "Unexpected token" (the JSON parse
    # error that the resp.ok check is preventing).
    expect(status_panel).to_contain_text("Server error 500", timeout=4000)
    status_text = status_panel.inner_text()
    assert "Unexpected token" not in status_text, (
        f"resp.ok check should prevent JSON parse on HTML body; got: {status_text!r}"
    )

    # Test button is re-enabled (settle() ran on the .catch terminal state).
    expect(test_btn).not_to_be_disabled()
