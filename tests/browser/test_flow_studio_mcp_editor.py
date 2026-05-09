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
    kv-label changes."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")
    # Command field visible; URL field hidden; kv label = "Environment Variables".
    expect(page.locator('.mcp-stdio-only').first).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.mcp-streamable-http-only').first).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.kv-section-title')).to_have_text("Environment Variables")

    # Switch to streamable-http
    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(page.locator('.mcp-stdio-only').first).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.mcp-streamable-http-only').first).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('.kv-section-title')).to_have_text("Custom Headers")


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


# ── F3 L5b: Sandbox section ───────────────────────────────────────────────


@pytest.mark.browser
def test_sandbox_section_renders_for_stdio_mode(app_clean: str, page: Page) -> None:
    """Selecting stdio reveals the Sandbox section with checkbox + chip-list."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")

    section = page.locator('[data-testid="mcp-sandbox-section"]')
    expect(section).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(section.locator('[data-field="sandbox-network-allowed"]')).to_be_visible()
    expect(section.locator('[data-field="sandbox-writable-paths"].chip-list-editor')).to_be_visible()


@pytest.mark.browser
def test_sandbox_section_hidden_for_streamable_http_mode(app_clean: str, page: Page) -> None:
    """Selecting streamable-http hides the Sandbox section."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("streamable-http")

    section = page.locator('[data-testid="mcp-sandbox-section"]')
    expect(section).to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_sandbox_section_visibility_toggles_on_transport_switch(app_clean: str, page: Page) -> None:
    """Switch type stdio→streamable-http→stdio; Sandbox section follows."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    section = page.locator('[data-testid="mcp-sandbox-section"]')

    page.locator('[data-field="type"]').select_option("stdio")
    expect(section).not_to_have_class(re.compile(r"\bis-hidden\b"))

    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(section).to_have_class(re.compile(r"\bis-hidden\b"))

    page.locator('[data-field="type"]').select_option("stdio")
    expect(section).not_to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_sandbox_save_round_trip(app_clean: str, page: Page) -> None:
    """Set network_allowed=true + writable_paths=[/data,/cache]; save; API GET round-trips."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("sandbox-stdio")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command"]').fill("x")

    # Toggle network_allowed checkbox (use check() to be explicit).
    page.locator('[data-field="sandbox-network-allowed"]').check()
    # Add two writable paths via the chip-list input.
    paths_input = page.locator(
        '[data-field="sandbox-writable-paths"].chip-list-editor .chip-list-input'
    )
    paths_input.fill("/data")
    paths_input.press("Enter")
    paths_input.fill("/cache")
    paths_input.press("Enter")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    sandbox_cfg = sources[0]["config"].get("sandbox")
    assert sandbox_cfg is not None
    assert sandbox_cfg["network_allowed"] is True
    assert sandbox_cfg["writable_paths"] == ["/data", "/cache"]


@pytest.mark.browser
def test_sandbox_edit_round_trip_populates_fields(app_clean: str, page: Page) -> None:
    """Pre-seed source with sandbox config; open in edit; fields populated."""
    sid = _seed_mcp_source(app_clean, {
        "name": "sandboxed",
        "type": "stdio",
        "config": {
            "command": "x",
            "sandbox": {"network_allowed": True, "writable_paths": ["/x"]},
        },
        "secrets": {},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("/x")


@pytest.mark.browser
def test_sandbox_empty_defaults_for_new_stdio_source(app_clean: str, page: Page) -> None:
    """New stdio source: checkbox unchecked + chip-list empty."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")
    expect(page.locator('[data-field="sandbox-network-allowed"]')).not_to_be_checked()
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(0)


@pytest.mark.browser
def test_sandbox_save_emits_explicit_defaults(app_clean: str, page: Page) -> None:
    """New stdio source saved without touching Sandbox section emits explicit defaults."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("default-sandbox")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command"]').fill("x")
    # Do NOT touch the Sandbox section.

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    sandbox_cfg = sources[0]["config"].get("sandbox")
    # Explicit defaults emitted (NOT omitted) — matches L1b validator contract.
    assert sandbox_cfg == {"network_allowed": False, "writable_paths": []}


@pytest.mark.browser
def test_streamable_http_source_has_no_sandbox_key(app_clean: str, page: Page) -> None:
    """streamable-http source created via the editor has no config.sandbox."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("remote-no-sandbox")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    assert "sandbox" not in sources[0]["config"]


@pytest.mark.browser
def test_sandbox_checkbox_toggle_marks_form_dirty(app_clean: str, page: Page) -> None:
    """Toggling the sandbox checkbox enables Save (form dirty)."""
    sid = _seed_mcp_source(app_clean, {
        "name": "edit-toggle",
        "type": "stdio",
        "config": {"command": "x", "sandbox": {"network_allowed": False, "writable_paths": []}},
        "secrets": {},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(save_btn).to_be_disabled()

    page.locator('[data-field="sandbox-network-allowed"]').check()
    expect(save_btn).not_to_be_disabled()


@pytest.mark.browser
def test_sandbox_chip_add_remove_marks_form_dirty(app_clean: str, page: Page) -> None:
    """Adding/removing a sandbox writable_paths chip marks the form dirty."""
    sid = _seed_mcp_source(app_clean, {
        "name": "edit-chips",
        "type": "stdio",
        "config": {"command": "x", "sandbox": {"network_allowed": False, "writable_paths": []}},
        "secrets": {},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(save_btn).to_be_disabled()

    paths_input = page.locator(
        '[data-field="sandbox-writable-paths"].chip-list-editor .chip-list-input'
    )
    paths_input.fill("/data")
    paths_input.press("Enter")
    expect(save_btn).not_to_be_disabled()

    # Remove the chip we just added — form remains dirty (different from
    # the initial empty-list snapshot? actually equal, so back to clean).
    # Re-add a different chip then remove to verify remove fires dirty.
    paths_input.fill("/extra")
    paths_input.press("Enter")
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(2)
    # Remove /data (first chip)
    chips.nth(0).locator('.chip-remove').click()
    # Save still enabled (form still dirty: list now has /extra not just nothing).
    expect(save_btn).not_to_be_disabled()


@pytest.mark.browser
def test_sandbox_cancel_revert_restores_state(app_clean: str, page: Page) -> None:
    """Edit existing source's sandbox state then Cancel — fields restore."""
    sid = _seed_mcp_source(app_clean, {
        "name": "edit-revert",
        "type": "stdio",
        "config": {
            "command": "x",
            "sandbox": {"network_allowed": True, "writable_paths": ["/x"]},
        },
        "secrets": {},
    })

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Pre-cancel state: checkbox checked, single chip /x.
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    initial_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(initial_chips).to_have_count(1)

    # Mutate: uncheck + remove the chip.
    page.locator('[data-field="sandbox-network-allowed"]').uncheck()
    initial_chips.first.locator('.chip-remove').click()
    after_chips = page.locator(
        '[data-field="sandbox-writable-paths"].chip-list-editor .chip'
    )
    expect(after_chips).to_have_count(0)

    cancel_btn = page.locator('[data-testid="cancel-mcp-source-btn"]')
    expect(cancel_btn).not_to_be_disabled()
    cancel_btn.click()

    # Post-cancel: checkbox checked again, /x chip restored.
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    restored_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(restored_chips).to_have_count(1)
    expect(restored_chips.first).to_contain_text("/x")
