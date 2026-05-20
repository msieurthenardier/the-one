"""Studio Connector editor flow tests (M10 F2 L6; F5 L8 HAT-rename).

Mirrors `test_flow_studio_mcp_editor.py` for the connector-account
editor. Covers create-form rendering, edit-form rendering, type-select
population, masked-secret round-trip, idle_timeout_seconds round-trip,
and the Danger-Zone delete affordance.

F5 L8 HAT-rename: hash route is now `#studio/connectors/...`. The
idle-timeout + continuation inputs are dropdowns offering a fixed
ladder of operator-friendly preset values (5m / 15m / 30m / 1h / 4h /
1d / 1w); the continuation field also offers "Never (always continue)"
representing null. Tests use `select_option(...)` against the ladder
values.

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


def _activate_access_and_routing_tab(page: Page) -> None:
    """M10 F7 L9 HAT: edit-mode renders a two-tab layout. The
    Lifecycle, Allowlist, and Routing rules sections live behind the
    "Access and Routing" tab. Tests that need to interact with those
    sections must click the tab first so the panel is visible /
    actionable. Create mode renders flat (no tabs), so this helper is
    only needed in edit-mode flows.
    """
    page.locator('[data-testid="tab-access-and-routing"]').click()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_create_form_renders_all_sections(app_clean: str, page: Page) -> None:
    """Create-mode: header, Connection, Credentials, Lifecycle present;
    Test Connection + Danger Zone absent."""
    page.goto(f"{app_clean}#studio/connectors/new")
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
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-testid="connector-account-name-input"]')).to_be_visible()
    # In edit-mode the type field renders as a read-only input.
    expect(page.locator('[data-testid="connector-account-type-readonly"]')).to_be_visible()
    expect(page.locator('[data-testid="connector-account-secrets-table"]')).to_be_attached()
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="delete-connector-account-btn"]')).to_be_visible()
    # M10 F7 L9 HAT: Lifecycle lives in the "Access and Routing" tab.
    # Attached check (it's in the DOM regardless of which tab is
    # active); visibility requires activating the tab.
    expect(page.locator('[data-testid="connector-account-idle-timeout-input"]')).to_be_attached()
    _activate_access_and_routing_tab(page)
    expect(page.locator('[data-testid="connector-account-idle-timeout-input"]')).to_be_visible()


@pytest.mark.browser
def test_type_select_populates_from_types_endpoint(app_clean: str, page: Page) -> None:
    """The type <select> shows the 'stub' option fetched from /types."""
    page.goto(f"{app_clean}#studio/connectors/new")
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
    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="connector-account-type-select"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-account-name-input"]').fill("Created Bot")
    page.locator('[data-testid="connector-account-type-select"]').select_option("stub")
    # Idle timeout dropdown — pick the 5-minute (300s) preset from the
    # F5 L8 HAT ladder. The previous free-form input accepted arbitrary
    # values; the dropdown's value attribute holds the seconds-int.
    page.locator('[data-testid="connector-account-idle-timeout-input"]').select_option("300")

    # Click "Create & Test" — fires POST then POST /test/connect.
    create_btn = page.locator('[data-testid="create-and-test-connector-account-btn"]')
    expect(create_btn).not_to_be_disabled()
    create_btn.click()

    # After create+probe completes, the editor remounts in edit-mode.
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)
    # URL transitioned to edit-mode (carries the new id).
    new_hash = page.evaluate("location.hash")
    assert new_hash.startswith("#studio/connectors/"), f"unexpected hash {new_hash!r}"
    assert new_hash != "#studio/connectors/new"

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
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
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
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
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
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
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
    """Select 5-minute ladder option → backend persists 300 seconds.

    F5 L8 HAT: the free-form numeric input was replaced with a dropdown
    offering a fixed value ladder. We select the smallest preset (300s)
    to round-trip through PUT and verify backend storage.
    """
    account_id = seed_connector_account(app_clean, name="TTL Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    # M10 F7 L9 HAT: Lifecycle is behind the Access and Routing tab.
    _activate_access_and_routing_tab(page)
    page.locator('[data-testid="connector-account-idle-timeout-input"]').select_option("300")
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["idle_timeout_seconds"] == 300


@pytest.mark.browser
def test_edit_idle_timeout_custom_value_renders_as_disabled_option(
    app_clean: str, page: Page
) -> None:
    """A persisted value that isn't on the ladder renders as a "Custom: Xs"
    selected option so the operator can see the stored value without
    overwriting it.

    F5 L8 HAT: the ladder offers 300/900/1800/3600/14400/86400/604800.
    A seeded 120-second value is off-ladder and round-trips as Custom.
    """
    account_id = seed_connector_account(
        app_clean,
        name="Custom TTL",
        idle_timeout_seconds=120,
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    # M10 F7 L9 HAT: Lifecycle lives in the Access and Routing tab.
    _activate_access_and_routing_tab(page)
    idle_input = page.locator('[data-testid="connector-account-idle-timeout-input"]')
    # The currently-selected option value is the persisted "120" carried by
    # the synthesized custom option (selected attribute is set in the HTML).
    expect(idle_input).to_have_value("120")


@pytest.mark.browser
def test_edit_idle_timeout_default_persists_null(app_clean: str, page: Page) -> None:
    """Selecting the "Use default" option (empty value) → backend persists null."""
    account_id = seed_connector_account(
        app_clean,
        name="Clearable TTL",
        idle_timeout_seconds=86400,  # ladder value so the dropdown selects it
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    # M10 F7 L9 HAT: Lifecycle lives in the Access and Routing tab.
    _activate_access_and_routing_tab(page)
    idle_input = page.locator('[data-testid="connector-account-idle-timeout-input"]')
    expect(idle_input).to_have_value("86400")
    # Select the "Use default" sentinel (empty value → null payload).
    idle_input.select_option("")
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["idle_timeout_seconds"] is None


@pytest.mark.browser
def test_edit_continuation_never_persists_null(app_clean: str, page: Page) -> None:
    """The continuation dropdown includes a "Never (always continue)"
    option that serializes to null — distinct from "Use default" but
    sharing the same null payload (the API field is nullable).

    F5 L8 HAT: ensures the __NEVER__ sentinel collapses to null on the wire.
    """
    account_id = seed_connector_account(
        app_clean,
        name="Always-On Bot",
        session_continuation_seconds=3600,
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    # M10 F7 L9 HAT: Lifecycle lives in the Access and Routing tab.
    _activate_access_and_routing_tab(page)
    cont_input = page.locator('[data-testid="connector-account-continuation-input"]')
    expect(cont_input).to_have_value("3600")
    cont_input.select_option("__NEVER__")
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["session_continuation_seconds"] is None


@pytest.mark.browser
def test_delete_from_danger_zone_removes_tile(app_clean: str, page: Page) -> None:
    """Two-click Delete fires DELETE → tile gone from grid."""
    account_id = seed_connector_account(app_clean, name="Deletable Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
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
def test_edit_session_continuation_round_trip(app_clean: str, page: Page) -> None:
    """Fill session_continuation_seconds → save → reopen → value round-trips.

    Also asserts the helper text is visible and contains the disambiguating
    language that distinguishes the continuation window from the pool idle
    timeout (M10 F03 L05 acceptance criterion).
    """
    account_id = seed_connector_account(app_clean, name="Continuation Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    # M10 F7 L9 HAT: Lifecycle lives in the Access and Routing tab.
    _activate_access_and_routing_tab(page)

    # Both Lifecycle inputs present and visually adjacent.
    expect(page.locator('[data-testid="connector-account-idle-timeout-input"]')).to_be_visible()
    cont_input = page.locator('[data-testid="connector-account-continuation-input"]')
    expect(cont_input).to_be_visible()

    # Helper text under the continuation input disambiguates from pool-TTL.
    cont_hint = page.locator('[data-testid="connector-account-continuation-hint"]')
    expect(cont_hint).to_be_visible()
    expect(cont_hint).to_contain_text("Distinct from the pool idle timeout")

    # Select the 1-hour (3600s) ladder option and save.
    # F5 L8 HAT: dropdown replaces the free-form numeric input.
    cont_input.select_option("3600")
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    # Backend persisted the value.
    after = _get_account(app_clean, account_id)
    assert after["session_continuation_seconds"] == 3600

    # Reopen the editor — go back to grid first, then click the card so the
    # router fully re-mounts the editor (a same-URL navigate is a no-op).
    page.locator('[data-testid="back-connector-account-btn"]').click()
    card = page.locator(
        '[data-testid="connector-account-card"]', has_text="Continuation Bot"
    )
    expect(card).to_be_visible(timeout=5000)
    card.click()
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)
    expect(
        page.locator('[data-testid="connector-account-continuation-input"]')
    ).to_have_value("3600")


@pytest.mark.browser
def test_back_when_dirty_prompts_confirm_dialog(app_clean: str, page: Page) -> None:
    """Back button while dirty → confirm dialog appears; Stay keeps the editor."""
    account_id = seed_connector_account(app_clean, name="Dirty Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="connector-account-name-input"]').fill("Dirty Bot Edited")
    # Click Back — should surface the unsaved-changes confirm dialog.
    page.locator('[data-testid="back-connector-account-btn"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=4000)
