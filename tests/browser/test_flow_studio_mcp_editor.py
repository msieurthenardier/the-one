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
- A dirty close (the breadcrumb's root link) surfaces App.confirmDialog;
  Cancel keeps the editor mounted
- Type change swaps transport-specific field visibility + kv label +
  OAuth section
- Save with empty kv key row silently skips that row (no "" key persisted)
"""

from __future__ import annotations

import json
import re

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect

# ── Helpers ──────────────────────────────────────────────────────────────


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(
        f"{base_url}/api/mcp-sources", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code in (200, 201), f"seed failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _get_source(base_url: str, sid: str) -> dict:
    r = httpx.get(
        f"{base_url}/api/mcp-sources/{sid}", timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _list_sources(base_url: str) -> list[dict]:
    r = httpx.get(f"{base_url}/api/mcp-sources", timeout=5.0, headers=auth_headers_for(base_url))
    assert r.status_code == 200
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────


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

    # The Refresh connection row is left-aligned with the editor's stacked
    # fields (HAT: it was indented by the legacy .field-row label gutter).
    refresh_box = page.locator('[data-testid="mcp-test-connection"]').bounding_box()
    name_box = page.locator('[data-field="name"]').bounding_box()
    assert refresh_box is not None and name_box is not None
    assert abs(refresh_box["x"] - name_box["x"]) <= 2, (refresh_box, name_box)

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
    expect(page.locator(".mcp-stdio-only").first).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator(".mcp-streamable-http-only").first).to_have_class(
        re.compile(r"\bis-hidden\b")
    )
    expect(page.locator(".kv-section-title")).to_have_text("Environment Variables")

    # Switch to streamable-http
    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(page.locator(".mcp-stdio-only").first).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator(".mcp-streamable-http-only").first).not_to_have_class(
        re.compile(r"\bis-hidden\b")
    )
    expect(page.locator(".kv-section-title")).to_have_text("Custom Headers")


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
    rows = page.locator(".mcp-kv-table tbody tr.mcp-kv-row")
    expect(rows).to_have_count(2)
    # Populate the first row only.
    rows.nth(0).locator(".kv-key-input").fill("DEBUG")
    rows.nth(0).locator(".kv-value-input").fill("1")
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
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")

    section = page.locator('[data-testid="mcp-sandbox-section"]')
    expect(section).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(section.locator('[data-field="sandbox-network-allowed"]')).to_be_visible()
    expect(
        section.locator('[data-field="sandbox-writable-paths"].chip-list-editor')
    ).to_be_visible()


@pytest.mark.browser
def test_sandbox_section_hidden_for_streamable_http_mode(app_clean: str, page: Page) -> None:
    """Selecting streamable-http hides the Sandbox section."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("streamable-http")

    section = page.locator('[data-testid="mcp-sandbox-section"]')
    expect(section).to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_sandbox_section_visibility_toggles_on_transport_switch(app_clean: str, page: Page) -> None:
    """Switch type stdio→streamable-http→stdio; Sandbox section follows."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
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
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("sandbox-stdio")
    page.locator('[data-field="type"]').select_option("stdio")
    # F9 L2 vibing: dropdown defaults to `uvx`; no explicit command needed.

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
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "sandboxed",
            "type": "stdio",
            "config": {
                "command": "x",
                "sandbox": {"network_allowed": True, "writable_paths": ["/x"]},
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("/x")


@pytest.mark.browser
def test_sandbox_empty_defaults_for_new_stdio_source(app_clean: str, page: Page) -> None:
    """New stdio source: checkbox checked (network-on by default) + chip-list empty.

    F9 L2 vibing: the lazy-install runtimes shipped in L2 D2 (uvx, npx,
    pipx run) all REQUIRE network egress on first spawn to fetch packages
    from PyPI/npm. Defaulting `network_allowed=False` was a footgun — a
    fresh stdio source's first Refresh would fail. The form-default flips
    to `True` for new sources only; existing sources preserve their
    stored value.
    """
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(0)


@pytest.mark.browser
def test_sandbox_save_emits_explicit_defaults(app_clean: str, page: Page) -> None:
    """New stdio source saved without touching Sandbox section emits explicit defaults.

    F9 L2 vibing: form-default for new sources is ``network_allowed=True``
    so lazy-install runtimes can fetch their packages on first spawn.
    """
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("default-sandbox")
    page.locator('[data-field="type"]').select_option("stdio")
    # F9 L2 vibing: dropdown defaults to `uvx`; no explicit command needed.
    # Do NOT touch the Sandbox section.

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    sandbox_cfg = sources[0]["config"].get("sandbox")
    # Explicit defaults emitted (NOT omitted) — matches L1b validator
    # contract. ``network_allowed`` defaults to True for new sources
    # (F9 L2 vibing default flip); ``writable_paths`` stays empty.
    assert sandbox_cfg == {"network_allowed": True, "writable_paths": []}


@pytest.mark.browser
def test_streamable_http_source_has_no_sandbox_key(app_clean: str, page: Page) -> None:
    """streamable-http source created via the editor has no config.sandbox."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
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
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "edit-toggle",
            "type": "stdio",
            "config": {"command": "x", "sandbox": {"network_allowed": False, "writable_paths": []}},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(save_btn).to_be_disabled()

    page.locator('[data-field="sandbox-network-allowed"]').check()
    expect(save_btn).not_to_be_disabled()


@pytest.mark.browser
def test_sandbox_chip_add_remove_marks_form_dirty(app_clean: str, page: Page) -> None:
    """Adding/removing a sandbox writable_paths chip marks the form dirty."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "edit-chips",
            "type": "stdio",
            "config": {"command": "x", "sandbox": {"network_allowed": False, "writable_paths": []}},
            "secrets": {},
        },
    )

    # The editor mounts only after GET /api/mcp-sources resolves (deep-link
    # hydration waits on the list); under load that response can outlast a
    # fixed 8s `expect`. Wait for the app's fetch activity to go quiet first.
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
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
    chips.nth(0).locator(".chip-remove").click()
    # Save still enabled (form still dirty: list now has /extra not just nothing).
    expect(save_btn).not_to_be_disabled()


@pytest.mark.browser
def test_sandbox_cancel_revert_restores_state(app_clean: str, page: Page) -> None:
    """Edit existing source's sandbox state then Cancel — fields restore."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "edit-revert",
            "type": "stdio",
            "config": {
                "command": "x",
                "sandbox": {"network_allowed": True, "writable_paths": ["/x"]},
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Pre-cancel state: checkbox checked, single chip /x.
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    initial_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(initial_chips).to_have_count(1)

    # Mutate: uncheck + remove the chip.
    page.locator('[data-field="sandbox-network-allowed"]').uncheck()
    initial_chips.first.locator(".chip-remove").click()
    after_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(after_chips).to_have_count(0)

    cancel_btn = page.locator('[data-testid="cancel-mcp-source-btn"]')
    expect(cancel_btn).not_to_be_disabled()
    cancel_btn.click()

    # Post-cancel: checkbox checked again, /x chip restored.
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    restored_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(restored_chips).to_have_count(1)
    expect(restored_chips.first).to_contain_text("/x")


# ── F9 L1: KV-table polish (empty-state thead hide + studio toggle/trash) ──


@pytest.mark.browser
def test_kv_thead_hidden_when_table_is_empty(app_clean: str, page: Page) -> None:
    """Empty kv-table → thead has `is-hidden` class (column headers not rendered).

    Newly-created streamable-http source with no headers/secrets should land in
    edit-mode with zero kv-rows; the column headers (Key/Value/Sensitive) must
    NOT be visible in this empty state.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "empty-kv",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    rows = page.locator(".mcp-kv-table tbody tr.mcp-kv-row")
    expect(rows).to_have_count(0)
    thead = page.locator('[data-testid="mcp-kv-thead"]')
    expect(thead).to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_kv_thead_reveals_when_first_row_added(app_clean: str, page: Page) -> None:
    """Adding the first kv row reveals the thead; removing it hides it again."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reveal-thead",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    thead = page.locator('[data-testid="mcp-kv-thead"]')
    expect(thead).to_have_class(re.compile(r"\bis-hidden\b"))

    # Add a row → thead loses is-hidden.
    page.locator('[data-testid="kv-add-row-btn"]').click()
    expect(page.locator(".mcp-kv-table tbody tr.mcp-kv-row")).to_have_count(1)
    expect(thead).not_to_have_class(re.compile(r"\bis-hidden\b"))

    # Remove the row → thead returns to is-hidden.
    page.locator(".mcp-kv-table tbody tr.mcp-kv-row .kv-remove-row-btn").click()
    expect(page.locator(".mcp-kv-table tbody tr.mcp-kv-row")).to_have_count(0)
    expect(thead).to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_kv_sensitive_header_carries_info_icon_with_tooltip(app_clean: str, page: Page) -> None:
    """The Sensitive column header has an info-icon button with the
    encrypted-at-rest tooltip in its title attr (a11y mirror in aria-label).
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "info-icon-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {"X-Api-Key": "abc1234567"},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    info_btn = page.locator('[data-testid="mcp-kv-sensitive-info"]')
    expect(info_btn).to_be_visible()
    title = info_btn.get_attribute("title") or ""
    assert "encrypted at rest" in title.lower(), title


@pytest.mark.browser
def test_kv_remove_row_uses_trash_icon(app_clean: str, page: Page) -> None:
    """Per-row remove control renders the trash icon (Lucide trash glyph),
    not a text button or close-x icon. The `kv-remove-row-btn` class is
    preserved as the click target."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "trash-icon-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp", "headers": {"X-Plain": "v"}},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    remove_btn = page.locator(".mcp-kv-table tbody tr.mcp-kv-row .kv-remove-row-btn").first
    expect(remove_btn).to_be_visible()
    # Trash icon SVG is rendered inside the button (no text content).
    expect(remove_btn.locator("svg")).to_be_visible()


@pytest.mark.browser
def test_kv_sensitive_toggle_reuses_studio_switch_pattern(app_clean: str, page: Page) -> None:
    """The per-row Sensitive control is the studio iOS-style toggle
    (`tool-enable-switch` + track), not a bare checkbox. Clicking the
    track flips the underlying input.checked state."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "toggle-sensitive-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp", "headers": {"X-Plain": "v"}},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    row = page.locator(".mcp-kv-table tbody tr.mcp-kv-row").first
    sensitive_label = row.locator(".mcp-kv-sensitive-switch")
    expect(sensitive_label).to_be_visible()
    # Track element exists (CSS-rendered toggle thumb relies on it).
    expect(sensitive_label.locator(".tool-enable-switch-track")).to_be_visible()

    checkbox = row.locator("input.kv-sensitive-checkbox")
    expect(checkbox).not_to_be_checked()
    # Click the visible label/track to toggle (the input itself is opacity:0).
    sensitive_label.click()
    expect(checkbox).to_be_checked()


@pytest.mark.browser
def test_custom_headers_section_lands_below_tools_section(app_clean: str, page: Page) -> None:
    """For streamable-http sources, the Custom Headers section appears
    BELOW the Tools section in DOM order (F9 L1 reorder). The section
    title text is the `kv-section-title` "Custom Headers"."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "section-order-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Both section titles must exist; Tools must precede Custom Headers in
    # document order.
    tools_title = page.locator(".editor-section.mcp-tools-section .section-title")
    headers_title = page.locator(".kv-section-title")
    expect(tools_title).to_have_text("Tools")
    expect(headers_title).to_have_text("Custom Headers")

    # DOM-order check via JS: Node.compareDocumentPosition returns 4
    # (FOLLOWING) when `tools` is followed by `headers` in document order.
    same_order = page.evaluate(
        "() => {"
        "  var t = document.querySelector('.editor-section.mcp-tools-section .section-title');"
        "  var h = document.querySelector('.kv-section-title');"
        "  if (!t || !h) return false;"
        "  return !!(t.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_FOLLOWING);"
        "}"
    )
    assert same_order, "Custom Headers section must come after Tools section in DOM order"


# ── F9 L1 (vibing): persisted tools cache + Reset connection button ───────


@pytest.mark.browser
def test_cached_tools_render_on_initial_mount(app_clean: str, page: Page) -> None:
    """A streamable-http source with config._cache populated renders the
    Tools section pre-populated WITHOUT clicking Refresh, plus a "Last
    updated" relative-time line.

    Seed via the API including a `_cache` block (POST does not strip it).
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "cached-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [
                        {"name": "echo", "description": "echo back", "input_schema": {}},
                        {"name": "shout", "description": "shout it", "input_schema": {}},
                    ],
                    "capabilities": {
                        "tools": {},
                        "resources": None,
                        "prompts": None,
                        "logging": None,
                        "completions": None,
                        "tasks": None,
                    },
                    # 30 seconds in the past → "just now" (diffSec < 60).
                    "last_updated": __import__("time").time() - 30,
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Tools list rendered without clicking Refresh.
    tool_items = page.locator('[data-testid="mcp-tools-list"] .mcp-tool-item')
    expect(tool_items).to_have_count(2)
    expect(page.locator('[data-testid="mcp-test-status"]')).to_contain_text("Server exposes")

    # "Last updated" line visible with relative-time format.
    last_updated = page.locator('[data-testid="mcp-tools-last-updated"]')
    expect(last_updated).to_be_visible()
    expect(last_updated).to_contain_text("Last updated:")
    # F9 L1 (vibing polish): the label lives inside the connection-actions
    # row (next to Refresh/Reset), not above the Tools list. Locking that
    # placement here so future re-renders keep it associated with the
    # controls that drive its value.
    nested = page.locator('.mcp-connection-actions [data-testid="mcp-tools-last-updated"]')
    expect(nested).to_have_count(1)


@pytest.mark.browser
def test_last_updated_renders_relative_time_format(app_clean: str, page: Page) -> None:
    """The "Last updated" line uses coarse relative-time strings (just now,
    N minutes ago, N hours ago) — not absolute timestamps."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "relative-time-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [{"name": "t", "description": "", "input_schema": {}}],
                    "capabilities": {"tools": {}},
                    # 7 minutes ago.
                    "last_updated": __import__("time").time() - 7 * 60,
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    last_updated = page.locator('[data-testid="mcp-tools-last-updated"]')
    expect(last_updated).to_be_visible()
    text = last_updated.inner_text()
    # Coarse format: "Last updated: 7 minutes ago" (or similar).
    assert "Last updated:" in text
    assert "minute" in text or "minutes" in text, text


# ── Squawk 0010: server_info websiteUrl / icon src scheme allow-list ──────


@pytest.mark.browser
def test_server_info_website_and_icon_reject_unsafe_schemes(app_clean: str, page: Page) -> None:
    """serverInfo.websiteUrl and icons[0].src come straight from the MCP
    server's initialize() response — an untrusted third party. A hostile
    javascript: websiteUrl must never become a live href, and a non-http
    icon src must never become a live <img src>: the <img> is dropped
    entirely, and the website row falls back to inert text so the operator
    can still see what the server claimed without it being clickable.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "hostile-server-info-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "server_info": {
                        "name": "hostile",
                        "title": "Hostile Server",
                        "websiteUrl": "javascript:alert(document.cookie)",
                        "icons": [{"src": "javascript:alert(1)", "mimeType": "image/png"}],
                    },
                    "capabilities": {"tools": {}},
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    section = page.locator('[data-testid="mcp-server-info-section"]')
    expect(section).to_be_visible()

    # Icon: hostile src never reaches an <img> element — dropped entirely,
    # not rendered with a neutered/placeholder src.
    expect(section.locator("img.mcp-server-icon")).to_have_count(0)

    # websiteUrl: no <a> element carries the hostile scheme; the raw string
    # still renders as inert text.
    website = section.locator(".mcp-server-website")
    expect(website).to_be_visible()
    expect(website.locator("a")).to_have_count(0)
    expect(website).to_contain_text("javascript:alert(document.cookie)")


@pytest.mark.browser
def test_server_info_website_and_icon_allow_https(app_clean: str, page: Page) -> None:
    """The allow-list isn't a blanket drop — a benign https: websiteUrl and
    icon src still render as a live link/image."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "benign-server-info-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "server_info": {
                        "name": "benign",
                        "title": "Benign Server",
                        "websiteUrl": "https://example.com/about",
                        "icons": [{"src": "https://example.com/icon.png", "mimeType": "image/png"}],
                    },
                    "capabilities": {"tools": {}},
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    section = page.locator('[data-testid="mcp-server-info-section"]')
    expect(section).to_be_visible()

    icon = section.locator("img.mcp-server-icon")
    expect(icon).to_have_count(1)
    expect(icon).to_have_attribute("src", "https://example.com/icon.png")

    link = section.locator(".mcp-server-website a")
    expect(link).to_have_count(1)
    expect(link).to_have_attribute("href", "https://example.com/about")


# ── Squawk 0102: Server section repaints after Refresh connection ────────


@pytest.mark.browser
def test_server_info_section_repaints_after_refresh(app_clean: str, page: Page) -> None:
    """A Refresh connection that brings back a new serverInfo version must
    repaint the Server section in place — without the operator leaving and
    re-entering the editor (squawk 0102: the section was mount-only, so it
    kept the old version while the tools list repainted).

    Seeds a source with no cache, so the first Refresh exercises the
    insert-above-Tools path and the second exercises the replace path.
    /test/connect and the success-handler's per-id GET refetch are stubbed
    (same pattern as test_reset_button_reappears_after_post_oauth_refresh);
    the GET serves whatever version the "server" currently reports. Initial
    mount reads the LIST endpoint, so the per-id stub only answers the
    post-refresh refetch.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "server-info-repaint",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    real_source = _get_source(app_clean, sid)
    reported = {"version": "0.3.0"}

    def handle_get(route):
        refreshed = json.loads(json.dumps(real_source))
        refreshed["config"]["_cache"] = {
            "tools": [{"name": "echo", "description": "", "input_schema": {}}],
            "server_info": {"name": "sonos", "title": "Sonos MCP", "version": reported["version"]},
            "capabilities": {"tools": {}},
            "last_updated": "2026-09-30T00:00:00Z",
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(refreshed))

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "ok",
                    "tools": [{"name": "echo", "description": "", "input_schema": {}}],
                    "capabilities": {"tools": {}},
                }
            ),
        )

    page.route(f"**/api/mcp-sources/{sid}", handle_get)
    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    refresh_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(refresh_btn).to_be_visible(timeout=8000)
    section = page.locator('[data-testid="mcp-server-info-section"]')
    expect(section).to_have_count(0)

    # First refresh: section is inserted, above the Tools section.
    refresh_btn.click()
    expect(section).to_have_count(1, timeout=4000)
    expect(section.locator(".mcp-server-version-line")).to_contain_text("v0.3.0")
    expect(page.locator(".mcp-server-info-section + .mcp-tools-section")).to_have_count(1)

    # The server is upgraded; refresh again without leaving the editor.
    reported["version"] = "0.5.0"
    expect(refresh_btn).not_to_be_disabled(timeout=4000)
    refresh_btn.click()
    expect(section.locator(".mcp-server-version-line")).to_contain_text("v0.5.0", timeout=4000)
    expect(section).to_have_count(1)
    expect(section.locator(".mcp-server-version-line")).not_to_contain_text("0.3.0")


@pytest.mark.browser
def test_reset_button_hidden_for_stdio_source(app_clean: str, page: Page) -> None:
    """stdio sources never show the Reset connection button (no OAuth concept)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "stdio-source",
            "type": "stdio",
            "config": {"command": "x"},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_reset_button_hidden_for_streamable_http_without_oauth(app_clean: str, page: Page) -> None:
    """A streamable-http source with no OAuth state shows Delete but not Reset."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "no-oauth",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_reset_button_visible_for_streamable_http_with_oauth(app_clean: str, page: Page) -> None:
    """A streamable-http source with OAuth state (access_token + dcr_credentials
    persisted) shows the Reset connection button alongside Delete."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "with-oauth",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_reset_button_two_step_confirmation(app_clean: str, page: Page) -> None:
    """First click on Reset arms the confirm-delete state (label flips,
    `confirm-delete` class is added); second click commits the DELETE
    and re-renders the editor with the Tools section back to empty-state
    and the Reset button hidden."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-two-step",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [{"name": "t", "description": "", "input_schema": {}}],
                    "capabilities": {"tools": {}},
                    "last_updated": __import__("time").time() - 30,
                },
            },
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    reset_btn = page.locator('[data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)

    # Pre-click: cached tools render.
    expect(page.locator('[data-testid="mcp-tools-list"] .mcp-tool-item')).to_have_count(1)

    # First click arms.
    reset_btn.click()
    expect(reset_btn).to_have_text(re.compile(r"Confirm Reset\?", re.IGNORECASE))
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    # Second click commits.
    reset_btn.click()

    # After re-render: Reset button is gone (no more OAuth state) and the
    # Tools section collapsed to its empty-state placeholder.
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0, timeout=5000)
    expect(page.locator('[data-testid="mcp-test-status"]')).to_contain_text("Click", timeout=5000)
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_hidden()


@pytest.mark.browser
def test_reset_mcp_connection_confirm_lapse_is_visually_distinct(
    app_clean: str, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the connection Reset
    confirm (`mcp-server-editor.js:1321`) is distinguishable on screen from
    one that was never armed, past the real 3s `revertMs` — and, since
    reverting here does NOT navigate away, the reverted control is still
    reachable to observe."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-lapse-me",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    reset_btn = page.locator('[data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)
    expect(reset_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    reset_btn.click()
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(reset_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(reset_btn).to_have_text("Reset connection")
    # The connection was never actually reset (no commit fired). OAuth-managed
    # keys (access_token, dcr_credentials) are always stripped from the GET
    # response body (api.py's OAUTH_MANAGED_SECRET_KEYS visibility filter),
    # so `oauth_active` — not raw secret presence — is the observable here.
    src = _get_source(app_clean, sid)
    assert src["oauth_active"] is True


# ── F9 L1 (vibing follow-up): Reset button placement + post-OAuth visibility +
#                              auto-run-on-create ─────────────────────────


@pytest.mark.browser
def test_reset_button_renders_in_connection_block_not_danger_zone(
    app_clean: str, page: Page
) -> None:
    """The Reset connection button is rendered next to Refresh in the
    Connection block (paired secondary action), NOT inside the Danger Zone.
    Reset is a reversible operation (just re-OAuth) and doesn't belong
    among destructive actions.

    Asserted invariants:
    - Reset button is a descendant of `.mcp-connection-actions` (the
      flex group that pairs it with Refresh).
    - Reset button is NOT a descendant of `.editor-section.danger-zone`.
    - Refresh button precedes Reset button in document order (visual
      hierarchy: primary → secondary).
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-placement",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_be_visible(timeout=8000)

    # Reset is inside the connection-actions cluster.
    expect(
        page.locator('.mcp-connection-actions [data-testid="reset-mcp-connection-btn"]')
    ).to_have_count(1)

    # Reset is NOT inside the Danger Zone block.
    expect(
        page.locator('.editor-section.danger-zone [data-testid="reset-mcp-connection-btn"]')
    ).to_have_count(0)

    # Refresh precedes Reset in document order (within the same actions
    # cluster). compareDocumentPosition returns FOLLOWING (4) when
    # `refresh` is followed by `reset` in the DOM.
    refresh_precedes_reset = page.evaluate(
        "() => {"
        "  var refresh = document.querySelector('[data-testid=\"mcp-test-connection\"]');"
        "  var reset = document.querySelector('[data-testid=\"reset-mcp-connection-btn\"]');"
        "  if (!refresh || !reset) return false;"
        "  return !!(refresh.compareDocumentPosition(reset) & Node.DOCUMENT_POSITION_FOLLOWING);"
        "}"
    )
    assert refresh_precedes_reset, "Refresh must precede Reset in document order"


@pytest.mark.browser
def test_reset_button_two_step_confirmation_in_connection_block(app_clean: str, page: Page) -> None:
    """The two-step confirmation flow on the Reset button is unchanged
    after the placement move: first click flips the label to "Confirm
    Reset?" and adds the `confirm-delete` class; second click commits."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-two-step-connection-block",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    reset_btn = page.locator('.mcp-connection-actions [data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)

    # First click arms.
    reset_btn.click()
    expect(reset_btn).to_have_text(re.compile(r"Confirm Reset\?", re.IGNORECASE))
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    # Second click commits → re-render with no OAuth state, button hides.
    reset_btn.click()
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0, timeout=5000)


@pytest.mark.browser
def test_reset_button_reappears_after_post_oauth_refresh(app_clean: str, page: Page) -> None:
    """After the Reset → Refresh-with-OAuth cycle, the Reset button must
    reappear without a page reload once /test/connect lands ok.

    Simulates the bug scenario:
    1. Source starts WITHOUT OAuth state → Reset button hidden.
    2. Operator clicks Refresh → /test/connect stub returns ok (we
       cannot drive a real OAuth popup in a browser test, so we stub
       the response). BEFORE the response lands, we mutate the seeded
       source server-side to add OAuth state — simulating what the
       real OAuth flow would do (write tokens via the SDK's callback
       handler).
    3. The success-callback refetches GET /api/mcp-sources/{id}; the
       refetched response carries oauth_active=true; the Reset button
       gets injected into the DOM.

    The auto-popup branch is NOT exercised by this test because driving
    a real OAuth flow requires an in-repo OAuth fixture (deferred per
    flight log). What this test verifies is the targeted UI behavior:
    after a successful /test/connect that flips oauth_active, the Reset
    button appears without reload.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-post-oauth",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},  # no OAuth state initially
        },
    )

    # Stub the per-id GET endpoint to return oauth_active=true so the
    # success-handler refetch sees the post-OAuth state. (We can't drive
    # the real OAuth flow in a browser test without an OAuth fixture —
    # what matters is that the success-callback's refetch + Reset-button
    # injection fires when oauth_active flips from false to true.)
    #
    # The initial mount fetches sources via the LIST endpoint
    # (/api/mcp-sources), not per-id, so the per-id stub only activates
    # for the post-test-connect refetch — exactly what we want.
    real_source = httpx.get(
        f"{app_clean}/api/mcp-sources/{sid}", timeout=5.0, headers=auth_headers_for(app_clean)
    ).json()
    post_oauth_get = dict(real_source)
    post_oauth_get["oauth_active"] = True

    test_connect_payload = {
        "status": "ok",
        "tools": [{"name": "echo", "description": "", "input_schema": {}}],
        "capabilities": {
            "tools": {},
            "resources": None,
            "prompts": None,
            "logging": None,
            "completions": None,
            "tasks": None,
        },
    }

    def handle_get(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(post_oauth_get),
        )

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(test_connect_payload),
        )

    page.route(f"**/api/mcp-sources/{sid}", handle_get)
    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_visible(timeout=8000)

    # Pre-Refresh: no OAuth state → no Reset button.
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0)

    # Click Refresh → success-handler issues a GET refetch → the stub
    # returns oauth_active=true → Reset button gets injected into the
    # connection-actions cluster.
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible(timeout=4000)
    # After the success callback's GET resolves, the Reset button appears
    # without requiring a page reload.
    expect(
        page.locator('.mcp-connection-actions [data-testid="reset-mcp-connection-btn"]')
    ).to_be_visible(timeout=4000)


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
    expect(page.locator('[data-testid="mcp-tools-list"] .mcp-tool-item')).to_have_count(1)
    expect(page.locator('[data-testid="mcp-test-status"]')).to_contain_text("Server exposes")


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
    """F9 L2 D1: stdio sources DO expose the Refresh button now (post-D1),
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
    expect(page.locator(".editor-section.mcp-tools-section")).to_have_count(1)
    # Auto-run did NOT fire for stdio: status panel still shows the
    # empty-state prompt asking the operator to click Refresh manually.
    status_panel = page.locator('[data-testid="mcp-test-status"]')
    expect(status_panel).to_be_visible()
    expect(status_panel).to_contain_text("Click")
    expect(status_panel).to_contain_text("Refresh connection")
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


# ─── F9 L2 vibing: stdio command-runtime dropdown ───────────────────────


@pytest.mark.browser
def test_stdio_command_runtime_default_selection_is_uvx(app_clean: str, page: Page) -> None:
    """New stdio source: dropdown defaults to `uvx`, the Custom-command
    free-text field is hidden, and the helper text under args reads the
    uvx hint."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")

    runtime = page.locator('[data-testid="mcp-command-runtime"]')
    expect(runtime).to_be_visible()
    expect(runtime).to_have_value("uvx")

    # Custom row is hidden (uvx is a canonical runtime).
    custom_row = page.locator(".mcp-command-custom-row")
    expect(custom_row).to_have_class(re.compile(r"\bis-hidden\b"))

    # Helper text reflects uvx hint copy.
    hint = page.locator('[data-testid="mcp-command-hint"]')
    expect(hint).to_be_visible()
    expect(hint).to_contain_text("package name")
    expect(hint).to_contain_text("Fetched")


@pytest.mark.browser
def test_stdio_command_runtime_switching_updates_hint_and_saves(app_clean: str, page: Page) -> None:
    """Switching the dropdown selection updates the helper text and the
    saved (command, args) pair splits a 2-token runtime per option (b).

    `pipx run` saves as command='pipx', args=['run', ...userArgs] —
    NOT command='pipx run' verbatim, which would FileNotFoundError on
    spawn (the dropdown literal is not a binary)."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("pipx-source")
    page.locator('[data-field="type"]').select_option("stdio")

    page.locator('[data-field="command-runtime"]').select_option("pipx run")
    hint = page.locator('[data-testid="mcp-command-hint"]')
    expect(hint).to_contain_text("Alternative to uvx")

    # Custom row stays hidden for canonical runtimes.
    expect(page.locator(".mcp-command-custom-row")).to_have_class(re.compile(r"\bis-hidden\b"))

    # Add a user arg via the chip-list (the package name).
    args_input = page.locator('[data-field="args"].chip-list-editor .chip-list-input')
    args_input.fill("mcp-server-time")
    args_input.press("Enter")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    cfg = sources[0]["config"]
    # Option (b): command is just `pipx`; args carry the implicit `run`
    # plus the operator's typed args.
    assert cfg["command"] == "pipx"
    assert cfg["args"] == ["run", "mcp-server-time"]


@pytest.mark.browser
def test_stdio_command_runtime_pipx_run_round_trip_collapses_to_dropdown(
    app_clean: str, page: Page
) -> None:
    """Pre-seed a source with command='pipx', args=['run', ...]; reopening
    the editor collapses that pair back into the `pipx run` dropdown
    selection, and the chip-list shows only the operator's args (the
    implicit `run` is stripped from the displayed chips)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "pipx-roundtrip",
            "type": "stdio",
            "config": {
                "command": "pipx",
                "args": ["run", "mcp-server-time"],
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Dropdown re-collapses to the `pipx run` literal.
    expect(page.locator('[data-field="command-runtime"]')).to_have_value("pipx run")
    # Custom-command row is hidden (canonical runtime).
    expect(page.locator(".mcp-command-custom-row")).to_have_class(re.compile(r"\bis-hidden\b"))

    # Args chip-list shows ONLY the operator's package name — the
    # implicit `run` is hidden from the editable chips.
    chips = page.locator('[data-field="args"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("mcp-server-time")


@pytest.mark.browser
def test_stdio_command_runtime_custom_escape_round_trips(app_clean: str, page: Page) -> None:
    """Selecting Custom… reveals the free-text input. Operator types a
    bare command; save persists it to config.command verbatim; reopen
    the source and the dropdown lands on Custom… with the saved value
    restored to the free-text field."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("custom-cmd-source")
    page.locator('[data-field="type"]').select_option("stdio")

    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    custom_row = page.locator(".mcp-command-custom-row")
    expect(custom_row).not_to_have_class(re.compile(r"\bis-hidden\b"))

    page.locator('[data-testid="mcp-command-custom"]').fill("bash /app/foo.sh")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    assert sources[0]["config"]["command"] == "bash /app/foo.sh"
    sid = sources[0]["id"]

    # Reload the editor; dropdown should land on Custom… with the saved
    # value visible in the free-text field.
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="command-runtime"]')).to_have_value("__custom__")
    expect(page.locator(".mcp-command-custom-row")).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('[data-testid="mcp-command-custom"]')).to_have_value("bash /app/foo.sh")


@pytest.mark.browser
def test_stdio_command_runtime_round_trip_canonical_uvx(app_clean: str, page: Page) -> None:
    """Pre-seed a source with config.command='uvx' (matches one of the
    canonical runtime literals); reopening the editor lands the dropdown
    on `uvx` selected, the Custom-command row is hidden, and the
    free-text field is empty (no leakage of the canonical literal into
    Custom…)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "uvx-canonical",
            "type": "stdio",
            "config": {"command": "uvx", "args": ["mcp-server-time"]},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="command-runtime"]')).to_have_value("uvx")
    expect(page.locator(".mcp-command-custom-row")).to_have_class(re.compile(r"\bis-hidden\b"))
    # Free-text input stays empty when dropdown is on a canonical runtime.
    expect(page.locator('[data-testid="mcp-command-custom"]')).to_have_value("")
    # Operator's args still surface in the chip-list.
    chips = page.locator('[data-field="args"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("mcp-server-time")


@pytest.mark.browser
def test_stdio_command_runtime_round_trip_custom_value(app_clean: str, page: Page) -> None:
    """Pre-seed a source with config.command='bash /app/x.sh' (no
    canonical match); reopening lands the dropdown on Custom… with the
    saved value populated in the free-text input."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "custom-bash-source",
            "type": "stdio",
            "config": {"command": "bash /app/x.sh"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="command-runtime"]')).to_have_value("__custom__")
    expect(page.locator(".mcp-command-custom-row")).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('[data-testid="mcp-command-custom"]')).to_have_value("bash /app/x.sh")


@pytest.mark.browser
def test_stdio_command_runtime_npx_y_save_split(app_clean: str, page: Page) -> None:
    """Selecting `npx -y` and saving splits the literal into
    command='npx', args=['-y', ...userArgs] (option (b) per leg spec).
    The implicit `-y` lives in args; the saved command is just `npx`."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("npx-y-source")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("npx -y")

    # Add a user arg via the chip-list (the package name).
    args_input = page.locator('[data-field="args"].chip-list-editor .chip-list-input')
    args_input.fill("@modelcontextprotocol/server-everything")
    args_input.press("Enter")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    cfg = sources[0]["config"]
    # Option (b): command is just `npx`; args carry the implicit `-y`
    # plus the operator's typed args.
    assert cfg["command"] == "npx"
    assert cfg["args"] == ["-y", "@modelcontextprotocol/server-everything"]


@pytest.mark.browser
def test_stdio_command_runtime_npx_y_round_trip_collapses_to_dropdown(
    app_clean: str, page: Page
) -> None:
    """Pre-seed a source with command='npx', args=['-y', ...]; reopening
    the editor collapses that pair back into the `npx -y` dropdown
    selection, and the chip-list shows only the operator's args (the
    implicit `-y` is stripped from the displayed chips)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "npx-y-roundtrip",
            "type": "stdio",
            "config": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-everything"],
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Dropdown re-collapses to the `npx -y` literal.
    expect(page.locator('[data-field="command-runtime"]')).to_have_value("npx -y")
    # Custom-command row is hidden (canonical runtime).
    expect(page.locator(".mcp-command-custom-row")).to_have_class(re.compile(r"\bis-hidden\b"))

    # Args chip-list shows ONLY the operator's package name — the
    # implicit `-y` is hidden from the editable chips.
    chips = page.locator('[data-field="args"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("@modelcontextprotocol/server-everything")


_DELAY_MCP_LIST_JS = """
(() => {
  const orig = window.fetch.bind(window);
  window.fetch = (u, ...a) => {
    const s = String((u && u.url) || u);
    if (/\\/api\\/mcp-sources(\\?|$)/.test(s)) {
      return new Promise((r) => setTimeout(() => r(orig(u, ...a)), 10000));
    }
    return orig(u, ...a);
  };
})();
"""


@pytest.mark.browser
def test_deep_linked_editor_mounts_after_slow_list_fetch(app_clean: str, page: Page) -> None:
    """A deep-linked MCP editor mounts only after GET /api/mcp-sources resolves.

    With that list held for 10s the editor still mounts (the app waits, it does
    not drop the pending id), and goto_settled returns only once it has.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "slow-list",
            "type": "stdio",
            "config": {"command": "x", "env": {}},
            "secrets": {},
        },
    )
    page.add_init_script(_DELAY_MCP_LIST_JS)
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=1000)


@pytest.mark.browser
def test_library_editor_connection_error_plain_headline(app_clean: str, page: Page) -> None:
    """DD19: Test connection's error shows a plain headline with the raw text
    under a collapsed "Technical details"; no "✗ Error:" prefix."""
    raw_error = (
        "MCPConnectionError: MCP connect failed: cancelled during initialize "
        "(cross-task cleanup deadlock; original cause likely transport error or "
        "malformed initial response): Cancelled via cancel scope 29abb186b90"
    )
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "dd19-lib-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": raw_error}),
        ),
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="mcp-test-connection"]').click()

    status_panel = page.locator('[data-testid="mcp-test-status"]')
    err = status_panel.locator('[data-testid="mcp-connection-error"]')
    expect(err).to_be_visible(timeout=4000)
    expect(err).to_contain_text("Couldn't connect to this server.")
    expect(status_panel).not_to_contain_text("✗ Error")
    # WCAG 4.1.3: the error is announced when it is inserted.
    expect(err).to_have_attribute("role", "alert")
    assert err.locator("details").evaluate("el => el.open") is False
    expect(err.locator("summary")).to_have_text("Technical details")
    expect(err.locator('[data-testid="mcp-error-raw"]')).not_to_be_visible()
    err.locator("summary").click()
    assert err.locator('[data-testid="mcp-error-raw"]').inner_text() == raw_error


# ─── Sortie 04: honest sign-in (the link block; a null popup is not a failure) ───

_CONSENT_URL = "https://idp.example.com/authorize?state=ST&client_id=x"
_OK_TOOLS = {
    "status": "ok",
    "tools": [{"name": "echo", "description": "", "input_schema": {}}],
    "capabilities": {"tools": {}},
}


def _seed_oauth_source(base_url: str, name: str) -> str:
    return _seed_mcp_source(
        base_url,
        {
            "name": name,
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )


def _stub_signin_routes(page: Page, base_url: str, sid: str) -> dict:
    """First /test/connect answers auth_required, later ones ok; the per-id GET
    (the editor's token poll) reports ``has_access_token`` from ``state``."""
    state = {"token": False, "connects": 0, "polls": 0}
    real = _get_source(base_url, sid)

    def handle_connect(route):
        state["connects"] += 1
        body = (
            {"status": "auth_required", "consent_url": _CONSENT_URL}
            if state["connects"] == 1
            else _OK_TOOLS
        )
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def handle_get(route):
        if route.request.method != "GET":
            return route.continue_()
        state["polls"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({**real, "has_access_token": state["token"]}),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_connect)
    page.route(re.compile(rf".*/api/mcp-sources/{re.escape(sid)}$"), handle_get)
    return state


def _open_editor(page: Page, base_url: str, sid: str) -> None:
    _nav.goto_settled(page, base_url, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_null_popup_shows_link_block_keeps_polling_and_lists_tools(
    app_clean: str, page: Page
) -> None:
    """window.open -> null (the desktop webview, or a popup blocker) shows the link
    block and keeps waiting; once the token lands the tools list with no re-test."""
    sid = _seed_oauth_source(app_clean, "null-popup")
    state = _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate(
        "() => { window.__opens = []; window.open = (u) => { __opens.push(u); return null; }; }"
    )

    page.locator('[data-testid="mcp-test-connection"]').click()
    url_input = page.locator('[data-testid="mcp-consent-link-url"]')
    expect(url_input).to_have_value(_CONSENT_URL, timeout=8000)
    anchor = page.locator('[data-testid="mcp-consent-link-open"]')
    expect(anchor).to_have_attribute("href", _CONSENT_URL)
    expect(anchor).to_have_attribute("target", "_blank")
    expect(anchor).to_have_attribute("rel", "noopener noreferrer")
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(status).not_to_contain_text("Popup blocked")
    expect(status).to_contain_text("Awaiting sign-in")
    assert page.evaluate("() => window.__opens") == [_CONSENT_URL]

    state["token"] = True
    expect(status).to_contain_text("Server exposes", timeout=10000)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible()
    assert state["connects"] == 2


@pytest.mark.browser
def test_status_live_region_exists_empty_before_its_first_text(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "live-region")
    _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate(
        """() => {
          window.open = () => null;
          window.__seen = [];
          new MutationObserver((muts) => {
            for (const m of muts) for (const n of m.addedNodes) {
              if (n.nodeType === 1 && n.classList.contains('mcp-consent-status-text')) {
                window.__seen.push({role: n.getAttribute('role'), text: n.textContent});
              }
            }
          }).observe(document.body, {childList: true, subtree: true});
        }"""
    )
    page.locator('[data-testid="mcp-test-connection"]').click()
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(status).to_contain_text("Awaiting sign-in", timeout=8000)
    seen = page.evaluate("() => window.__seen")
    assert seen and seen[0] == {"role": "status", "text": ""}


@pytest.mark.browser
def test_success_after_sign_in_moves_focus_from_the_block_to_refresh(
    app_clean: str, page: Page
) -> None:
    sid = _seed_oauth_source(app_clean, "focus-success")
    state = _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate("() => { window.open = () => null; }")
    page.locator('[data-testid="mcp-test-connection"]').click()
    anchor = page.locator('[data-testid="mcp-consent-link-open"]')
    expect(anchor).to_be_visible(timeout=8000)
    anchor.focus()
    expect(anchor).to_be_focused()
    state["token"] = True
    expect(page.locator('[data-testid="mcp-test-status"]')).to_contain_text(
        "Server exposes", timeout=10000
    )
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_focused()


@pytest.mark.browser
def test_link_block_survives_status_text_and_popup_closing(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "popup-closes")
    state = _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate(
        "() => { window.__p = { closed: false, close() { this.closed = true; } };"
        " window.open = () => window.__p; }"
    )
    page.locator('[data-testid="mcp-test-connection"]').click()
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible(timeout=8000)
    page.evaluate("() => { window.__p.closed = true; }")
    expect(status).to_contain_text("Finalizing sign-in", timeout=8000)
    # The status text changed; the block is still there, and polling goes on
    # well past the old 3s popup-close grace window.
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible()
    polls = state["polls"]
    page.wait_for_timeout(4000)
    assert state["polls"] > polls + 2
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible()
    state["token"] = True
    expect(status).to_contain_text("Server exposes", timeout=10000)


@pytest.mark.browser
def test_failed_sign_in_removes_the_block_and_offers_retry(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "signin-fails")
    _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate("() => { window.open = () => null; }")
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible(timeout=8000)
    page.evaluate(
        "() => window.postMessage({type: 'mcp-oauth-result', status: 'failed',"
        " description: 'denied'}, window.location.origin)"
    )
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(status).to_contain_text("Sign-in failed: denied", timeout=8000)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)
    expect(page.locator('[data-testid="mcp-consent-btn"]')).to_be_visible()


@pytest.mark.browser
def test_credentials_rejected_renders_plain_headline(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "rejected-key")
    raw = (
        "MCPCredentialsRejected: rejected-key rejected the configured credentials (401). "
        "Check the headers for this MCP server in Library › MCP servers, or the agent's "
        "MCPs tab if it overrides them."
    )
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": raw}),
        ),
    )
    _open_editor(page, app_clean, sid)
    page.locator('[data-testid="mcp-test-connection"]').click()
    err = page.locator('[data-testid="mcp-connection-error"]')
    expect(err).to_contain_text(
        "The server rejected the configured credentials. Check the headers on this MCP server.",
        timeout=8000,
    )
    expect(page.locator('[data-testid="mcp-consent-btn"]')).to_have_count(0)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)


@pytest.mark.browser
def test_non_web_consent_url_opens_nothing_and_renders_no_link(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "unsafe-consent")
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "auth_required", "consent_url": "javascript:alert(1)"}),
        ),
    )
    _open_editor(page, app_clean, sid)
    page.evaluate(
        "() => { window.__opens = []; window.open = (u) => { __opens.push(u); return null; }; }"
    )
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator(".consent-link-unsafe")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-consent-link-open"]')).to_have_count(0)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)
    assert page.evaluate("() => window.__opens") == []
