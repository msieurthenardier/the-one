"""Studio Connector DM-admission allowlist-row tests (M11 F10 L2).

L2 adds a 3-value selector ("DM admission") to the account-scope
allowlist editor — a UI affordance for the dispatcher's
``account.config.allowlist.dm_admission`` field that L1 already wired
through the validator + dispatcher (substrate). The selector is
placed between the peers row and the channels row in
``renderAllowlistSection``; its value persists via the existing
``PUT /api/connector-accounts/{id}`` path.

Coverage:

- The new row renders with the account's persisted ``dm_admission``
  value preselected.
- Changing the selector marks the form dirty (Save button enables via
  the existing dirty-tracker mechanism).
- Save + GET round-trip persists the chosen value.
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


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_dm_admission_row_renders_with_account_value_preselected(
    app_clean: str, page: Page
) -> None:
    """Seed an account with ``dm_admission='all'``; navigate to the
    editor; expect the new row's <select> to have ``"all"`` selected."""
    account_id = seed_connector_account(
        app_clean,
        name="DM Admission All",
        type="stub",
        config={
            "allowlist": {
                "peers": [],
                "channels": [],
                "dm_admission": "all",
            }
        },
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Access and Routing tab hosts the allowlist section (L9 tabbed
    # layout); the editor mounts the section in the DOM at load but
    # only the active tab is visually present, so we switch tabs to
    # surface the new row for reliable assertions.
    page.locator('[data-testid="tab-access-and-routing"]').click()

    row = page.locator('[data-testid="connector-allowlist-dm-admission-row"]')
    expect(row).to_be_visible()

    select = page.locator(
        '[data-testid="connector-allowlist-dm-admission-select"]'
    )
    expect(select).to_be_visible()
    # The selected value matches the seeded ``dm_admission``.
    assert select.input_value() == "all", (
        f"expected preselected value 'all'; got {select.input_value()!r}"
    )

    # Sanity: all three options are present with the L1-Literal values.
    option_values = select.locator("option").evaluate_all(
        "els => els.map(e => e.value)"
    )
    assert option_values == ["none", "allowlisted-peers-only", "all"], (
        f"DM admission options drifted; got: {option_values!r}"
    )

    # Literal "DM admission" label text (no vocabulary substitution —
    # DM is universal across connector types).
    label = row.locator("label.connector-account-acl-fieldlabel")
    assert label.text_content().strip() == "DM admission", (
        f"expected literal 'DM admission' label; got: "
        f"{label.text_content()!r}"
    )


@pytest.mark.browser
def test_dm_admission_change_marks_form_dirty(
    app_clean: str, page: Page
) -> None:
    """Changing the DM-admission selector enables the Save button via
    the existing dirty-tracker mechanism — no new wiring required;
    ``collectAllowlistFromContainer``'s extended dict shape rides into
    the form snapshot for free."""
    account_id = seed_connector_account(
        app_clean,
        name="DM Admission Dirty",
        type="stub",
        config={
            "allowlist": {
                "peers": [],
                "channels": [],
                "dm_admission": "allowlisted-peers-only",
            }
        },
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    save_btn = page.locator('[data-testid="save-connector-account-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    # Pre-change: form is clean → Save is disabled.
    expect(save_btn).to_be_disabled()

    page.locator('[data-testid="tab-access-and-routing"]').click()

    select = page.locator(
        '[data-testid="connector-allowlist-dm-admission-select"]'
    )
    expect(select).to_be_visible()
    select.select_option("none")

    # Dirty-tracker fires → Save enables.
    expect(save_btn).not_to_be_disabled()


@pytest.mark.browser
def test_dm_admission_save_persists_value(
    app_clean: str, page: Page
) -> None:
    """Change the selector, click Save, then GET the account — the
    chosen value persists at ``config.allowlist.dm_admission``."""
    account_id = seed_connector_account(
        app_clean,
        name="DM Admission Persist",
        type="stub",
        config={
            "allowlist": {
                "peers": [],
                "channels": [],
                "dm_admission": "allowlisted-peers-only",
            }
        },
    )

    # Pre-state sanity: L1's validator already inserted the default for
    # the seeded shape (no migration race).
    before = _get_account(app_clean, account_id)
    assert before["config"]["allowlist"]["dm_admission"] == "allowlisted-peers-only"

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    save_btn = page.locator('[data-testid="save-connector-account-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)

    page.locator('[data-testid="tab-access-and-routing"]').click()
    select = page.locator(
        '[data-testid="connector-allowlist-dm-admission-select"]'
    )
    expect(select).to_be_visible()
    select.select_option("all")

    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    # Save success flash.
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["config"]["allowlist"]["dm_admission"] == "all", (
        f"DM-admission save did not persist; got: "
        f"{after['config']['allowlist']!r}"
    )
    # Sibling axes should remain unaffected by the dm_admission save.
    for axis in ("peers", "channels", "guilds", "roles"):
        assert axis in after["config"]["allowlist"], (
            f"sibling axis {axis!r} dropped at save; got: "
            f"{after['config']['allowlist']!r}"
        )
