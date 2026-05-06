"""MCP source editor browser tests (Studio nav).

Originally `test_flow_admin_mcp_editor.py` (M07 F1 L6 — admin nav);
relocated to studio post-F2 retrofit because MCP sources are user-managed
entities, not system settings. URL hash + section host changed from
`#admin/mcp-sources/...` + `.area-admin` to `#studio/mcp-sources/...` +
`.area-studio`. Editor behavior contract is unchanged.

Covers:
- Create stdio source via the form; tile appears in grid
- Create streamable-http source with OAuth client config; round-trip
  preserves all OAuth fields
- Edit stdio source preserves unchanged secrets via per-key __MASKED__
- Edit streamable-http source: change one secret, leave another untouched;
  changed-one is overwritten + unchanged-one preserved
- Delete stdio source via App.confirmDelete two-click flow
- Delete streamable-http source via App.confirmDelete two-click flow
- Dirty Back surfaces App.confirmDialog; Cancel keeps the editor mounted
- Type change swaps transport-specific field visibility + kv label +
  OAuth section
- Save with empty kv key row silently skips that row (no "" key persisted)
"""

from __future__ import annotations

import re

import httpx
import pytest
from playwright.sync_api import Page, expect

# ── Helpers ──────────────────────────────────────────────────────────────


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(f"{base_url}/api/mcp-sources", json=payload, timeout=5.0)
    assert r.status_code in (200, 201), f"seed failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _get_source(base_url: str, sid: str) -> dict:
    r = httpx.get(f"{base_url}/api/mcp-sources/{sid}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _list_sources(base_url: str) -> list[dict]:
    r = httpx.get(f"{base_url}/api/mcp-sources", timeout=5.0)
    assert r.status_code == 200
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_create_stdio_source(app_clean: str, page: Page) -> None:
    """Fill the create form for a stdio source, save, see it in the grid."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("github-mcp")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command"]').fill("github-mcp")

    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).not_to_be_disabled()
    save_btn.click()

    # Save flash + create→edit transition: Danger Zone now visible.
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    # Back to grid.
    page.locator('[data-testid="back-mcp-source-btn"]').click()
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    expect(page.locator('[data-testid="mcp-source-card"]', has_text="github-mcp")).to_be_visible()


@pytest.mark.browser
def test_create_streamable_http_source_with_oauth(app_clean: str, page: Page) -> None:
    """Create streamable-http with OAuth, edit, verify all OAuth fields round-trip."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("remote-mcp")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")

    # OAuth fields
    page.locator('[data-field="oauth-issuer-url"]').fill("https://auth.example.com")
    page.locator('[data-field="oauth-client-id"]').fill("client-abc")
    page.locator('[data-field="oauth-redirect-uri"]').fill("http://127.0.0.1:53682/callback")
    page.locator('[data-field="oauth-client-secret"]').fill("super-secret-value")

    # OAuth scopes chip-list — type Enter to add a chip
    scope_input = page.locator('[data-field="oauth-scopes"].chip-list-editor .chip-list-input')
    scope_input.fill("read")
    scope_input.press("Enter")
    scope_input.fill("write")
    scope_input.press("Enter")

    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    # Verify via API: OAuth fields stored, client_secret encrypted (masked tail).
    sources = _list_sources(app_clean)
    assert len(sources) == 1
    src = sources[0]
    assert src["name"] == "remote-mcp"
    assert src["type"] == "streamable-http"
    assert src["config"]["url"] == "https://example.com/mcp"
    oauth = src["config"]["oauth"]
    assert oauth["issuer_url"] == "https://auth.example.com"
    assert oauth["client_id"] == "client-abc"
    assert oauth["redirect_uri"] == "http://127.0.0.1:53682/callback"
    assert set(oauth["scopes"]) == {"read", "write"}
    # client_secret was 18 chars → masked tail "***...alue".
    assert src["secrets"]["oauth_client_secret"] == "***...alue"


@pytest.mark.browser
def test_edit_stdio_source_preserves_unchanged_secrets(app_clean: str, page: Page) -> None:
    """Edit only the name; per-key __MASKED__ preserves stored secret."""
    sid = _seed_mcp_source(app_clean, {
        "name": "GH",
        "type": "stdio",
        "config": {"command": "github-mcp", "env": {}},
        "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Sensitive env var pre-fills with the masked tail (***...alue).
    kv_value = page.locator('.kv-value-input[data-field="kv-value"]').first
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
    sid = _seed_mcp_source(app_clean, {
        "name": "remote",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp", "headers": {}},
        "secrets": {
            "Authorization": "Bearer-original-aaaa",
            "X-Api-Key": "original-bbbb-key",
        },
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Identify which row is which by inspecting the key inputs.
    rows = page.locator(".mcp-kv-table tbody tr.mcp-kv-row")
    expect(rows).to_have_count(2)

    # Find the Authorization row by key text and change its value.
    n_rows = rows.count()
    for i in range(n_rows):
        key_val = rows.nth(i).locator(".kv-key-input").input_value()
        if key_val == "Authorization":
            rows.nth(i).locator(".kv-value-input").fill("Bearer-NEW-cccc")
            break

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    src = _get_source(app_clean, sid)
    # Authorization: 16 chars → ***...cccc (last 4)
    assert src["secrets"]["Authorization"] == "***...cccc"
    # X-Api-Key untouched: 17 chars → ***...-key (last 4 of "original-bbbb-key")
    assert src["secrets"]["X-Api-Key"] == "***...-key"


@pytest.mark.browser
def test_delete_stdio_source(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(app_clean, {
        "name": "delete-me",
        "type": "stdio",
        "config": {"command": "x"},
        "secrets": {},
    })
    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    # First click arms.
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))
    # Second click commits.
    delete_btn.click()
    # Land back on the grid; tile is gone.
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    assert _list_sources(app_clean) == []


@pytest.mark.browser
def test_delete_streamable_http_source(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(app_clean, {
        "name": "delete-remote",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })
    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))
    delete_btn.click()
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    assert _list_sources(app_clean) == []


@pytest.mark.browser
def test_dirty_back_confirm_dialog(app_clean: str, page: Page) -> None:
    """Dirty editor + Back → confirmDialog; Cancel keeps editor mounted."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Make the form dirty.
    page.locator('[data-field="name"]').fill("typed-name")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).not_to_be_disabled()

    # Click Back; modal appears.
    page.locator('[data-testid="back-mcp-source-btn"]').click()
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
    kv-label changes, OAuth section reveals."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")
    # Command field visible; URL field hidden; kv label = "Environment Variables".
    expect(page.locator('.mcp-stdio-only').first).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.mcp-streamable-http-only').first).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.kv-section-title')).to_have_text("Environment Variables")
    expect(page.locator('[data-testid="mcp-oauth-section"]')).to_have_class(re.compile(r"\bis-hidden\b"))

    # Switch to streamable-http
    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(page.locator('.mcp-stdio-only').first).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.mcp-streamable-http-only').first).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.kv-section-title')).to_have_text("Custom Headers")
    expect(page.locator('[data-testid="mcp-oauth-section"]')).not_to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_save_with_empty_kv_key_row_silently_skips(app_clean: str, page: Page) -> None:
    """Add an empty kv row PLUS a populated row; save; only the populated
    row persists. Empty key is dropped at partition time."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("test-skip-empty")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command"]').fill("x")

    # Add two empty rows.
    add_btn = page.locator('[data-testid="kv-add-row-btn"]')
    add_btn.click()
    add_btn.click()
    rows = page.locator('.mcp-kv-table tbody tr.mcp-kv-row')
    expect(rows).to_have_count(2)
    # Populate the first row only.
    rows.nth(0).locator('.kv-key-input').fill("DEBUG")
    rows.nth(0).locator('.kv-value-input').fill("1")
    # Leave the second row entirely empty.

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    assert sources[0]["config"].get("env") == {"DEBUG": "1"}
    # Empty-key row was NOT persisted.
    assert "" not in sources[0]["config"].get("env", {})
    assert "" not in sources[0].get("secrets", {})
