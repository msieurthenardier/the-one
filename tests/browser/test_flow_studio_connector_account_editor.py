"""Studio Connector Account editor flow tests (M10 F2 L6).

Mirrors `test_flow_studio_mcp_editor.py` for the connector-account
editor. Covers create-form rendering, edit-form rendering, type-select
population, masked-secret round-trip, idle_timeout_seconds round-trip,
and the Danger-Zone delete affordance.

The tests rely on the StubPlugin being registered server-side as the
`stub` connector type — see `conftest.py`'s
``THE_ONE_REGISTER_STUB_CONNECTOR=1`` env-var wiring.
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import seed_connector_account
from playwright.sync_api import Page, expect


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connector-accounts/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _list_accounts(base_url: str) -> list[dict]:
    r = httpx.get(f"{base_url}/api/connector-accounts", timeout=5.0)
    assert r.status_code == 200
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_create_form_renders_all_sections(app_clean: str, page: Page) -> None:
    """Create-mode: header, Connection, Credentials, Lifecycle present;
    Test Connection + Danger Zone absent."""
    page.goto(f"{app_clean}#studio/connector-accounts/new")
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Connection section.
    expect(page.locator('[data-testid="connector-account-name-input"]')).to_be_visible()
    expect(page.locator('[data-testid="connector-account-type-select"]')).to_be_visible()
    # Credentials section table.
    expect(page.locator('[data-testid="connector-account-secrets-table"]')).to_be_attached()
    # Lifecycle section idle-timeout input.
    expect(page.locator('[data-testid="connector-account-idle-timeout-input"]')).to_be_visible()
    # Test Connection section is edit-mode only — absent in create-mode.
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_have_count(0)
    # Danger Zone is edit-mode only.
    expect(page.locator('[data-testid="delete-connector-account-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_edit_form_renders_all_sections(app_clean: str, page: Page) -> None:
    """Edit-mode: every section including Test Connection + Danger Zone."""
    account_id = seed_connector_account(app_clean, name="Stub Bot")
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-testid="connector-account-name-input"]')).to_be_visible()
    # In edit-mode the type field renders as a read-only input.
    expect(page.locator('[data-testid="connector-account-type-readonly"]')).to_be_visible()
    expect(page.locator('[data-testid="connector-account-secrets-table"]')).to_be_attached()
    expect(page.locator('[data-testid="connector-account-idle-timeout-input"]')).to_be_visible()
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="delete-connector-account-btn"]')).to_be_visible()


@pytest.mark.browser
def test_type_select_populates_from_types_endpoint(app_clean: str, page: Page) -> None:
    """The type <select> shows the 'stub' option fetched from /types."""
    page.goto(f"{app_clean}#studio/connector-accounts/new")
    expect(page.locator('[data-testid="connector-account-type-select"]')).to_be_visible(
        timeout=8000
    )

    options = page.locator('[data-testid="connector-account-type-select"] option')
    # First option is the disabled "Select a connector type" placeholder
    # (stub IS registered via conftest's env-var seam), then 'stub'.
    values = options.evaluate_all("els => els.map(e => e.value)")
    assert "stub" in values, f"expected 'stub' in option values, got {values}"


@pytest.mark.browser
def test_create_and_test_creates_account_and_transitions_to_edit_mode(
    app_clean: str, page: Page
) -> None:
    """Fill the create form → Create & Test → both calls fire → URL is
    in edit-mode → the new tile is visible after Back to grid."""
    page.goto(f"{app_clean}#studio/connector-accounts/new")
    expect(page.locator('[data-testid="connector-account-type-select"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-account-name-input"]').fill("Created Bot")
    page.locator('[data-testid="connector-account-type-select"]').select_option("stub")
    # Idle timeout.
    page.locator('[data-testid="connector-account-idle-timeout-input"]').fill("60")

    # Click "Create & Test" — fires POST then POST /test/connect.
    create_btn = page.locator('[data-testid="create-and-test-connector-account-btn"]')
    expect(create_btn).not_to_be_disabled()
    create_btn.click()

    # After create+probe completes, the editor remounts in edit-mode.
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)
    # URL transitioned to edit-mode (carries the new id).
    new_hash = page.evaluate("location.hash")
    assert new_hash.startswith("#studio/connector-accounts/"), f"unexpected hash {new_hash!r}"
    assert new_hash != "#studio/connector-accounts/new"

    # Back to grid → the new tile is visible.
    page.locator('[data-testid="back-connector-account-btn"]').click()
    expect(
        page.locator('[data-testid="connector-account-card"]', has_text="Created Bot")
    ).to_be_visible(timeout=5000)


@pytest.mark.browser
def test_edit_with_unchanged_secret_preserves_stored_value(
    app_clean: str, page: Page
) -> None:
    """Save without touching a secret → backend keeps the stored value."""
    account_id = seed_connector_account(
        app_clean,
        name="Token Bot",
        secrets={"BOT_TOKEN": "real_secret_value_xyz"},
    )
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    # Secret pre-fills with the masked tail (last-4 of the plaintext).
    secret_input = page.locator(".secret-value-input").first
    expect(secret_input).to_have_value("***..._xyz")

    # Touch the name to mark dirty (cancel/save are disabled until dirty).
    page.locator('[data-testid="connector-account-name-input"]').fill("Token Bot Renamed")
    save_btn = page.locator('[data-testid="save-connector-account-btn"]')
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["name"] == "Token Bot Renamed"
    # Stored secret preserved — masked tail still matches the original
    # plaintext suffix (last 4 chars).
    assert after["secrets"]["BOT_TOKEN"] == "***..._xyz"


@pytest.mark.browser
def test_edit_name_only_save_preserves_secrets(app_clean: str, page: Page) -> None:
    """Change name only → list reflects new name → secret untouched."""
    account_id = seed_connector_account(
        app_clean,
        name="Original Name",
        secrets={"API_KEY": "preserved_value_abcd"},
    )
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="connector-account-name-input"]').fill("Renamed")
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    accounts = _list_accounts(app_clean)
    by_id = {a["id"]: a for a in accounts}
    assert by_id[account_id]["name"] == "Renamed"
    assert by_id[account_id]["secrets"]["API_KEY"] == "***...abcd"


@pytest.mark.browser
def test_edit_change_a_secret_updates_backend(app_clean: str, page: Page) -> None:
    """Replace a secret value → backend stores the new value."""
    account_id = seed_connector_account(
        app_clean,
        name="Secret Bot",
        secrets={"BOT_TOKEN": "old_value_xxxx"},
    )
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    new_token = "fresh_token_zzzz"
    secret_input = page.locator(".secret-value-input").first
    secret_input.fill(new_token)
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    # Masked tail reflects the NEW token's last 4 chars.
    assert after["secrets"]["BOT_TOKEN"] == "***...zzzz"


@pytest.mark.browser
def test_edit_idle_timeout_set_to_value(app_clean: str, page: Page) -> None:
    """Set idle_timeout_seconds to 60 → backend persists 60."""
    account_id = seed_connector_account(app_clean, name="TTL Bot")
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="connector-account-idle-timeout-input"]').fill("60")
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["idle_timeout_seconds"] == 60


@pytest.mark.browser
def test_edit_idle_timeout_cleared_persists_null(app_clean: str, page: Page) -> None:
    """Clear idle_timeout_seconds input → backend persists null."""
    account_id = seed_connector_account(
        app_clean,
        name="Clearable TTL",
        idle_timeout_seconds=120,
    )
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    idle_input = page.locator('[data-testid="connector-account-idle-timeout-input"]')
    expect(idle_input).to_have_value("120")
    idle_input.fill("")
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["idle_timeout_seconds"] is None


@pytest.mark.browser
def test_edit_idle_timeout_zero_surfaces_validation_error(
    app_clean: str, page: Page
) -> None:
    """idle_timeout_seconds=0 → backend 422 → editor surfaces inline."""
    account_id = seed_connector_account(app_clean, name="Zero TTL Bot")
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="connector-account-idle-timeout-input"]').fill("0")
    page.locator('[data-testid="save-connector-account-btn"]').click()

    # Error span should display a non-empty error referencing the bound.
    error_el = page.locator('[data-testid="connector-account-editor-error"]')
    expect(error_el).not_to_be_empty(timeout=8000)


@pytest.mark.browser
def test_delete_from_danger_zone_removes_tile(app_clean: str, page: Page) -> None:
    """Two-click Delete fires DELETE → tile gone from grid."""
    account_id = seed_connector_account(app_clean, name="Deletable Bot")
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="delete-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    delete_btn = page.locator('[data-testid="delete-connector-account-btn"]')
    # First click — arms the confirm-delete state.
    delete_btn.click()
    # Second click — fires DELETE.
    delete_btn.click()

    # Editor unmounts, grid renders without the deleted tile.
    expect(page.locator(".empty-canvas")).to_be_visible(timeout=8000)
    accounts = _list_accounts(app_clean)
    assert account_id not in {a["id"] for a in accounts}


@pytest.mark.browser
def test_back_when_dirty_prompts_confirm_dialog(app_clean: str, page: Page) -> None:
    """Back button while dirty → confirm dialog appears; Stay keeps the editor."""
    account_id = seed_connector_account(app_clean, name="Dirty Bot")
    page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="connector-account-name-input"]').fill("Dirty Bot Edited")
    # Click Back — should surface the unsaved-changes confirm dialog.
    page.locator('[data-testid="back-connector-account-btn"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=4000)
