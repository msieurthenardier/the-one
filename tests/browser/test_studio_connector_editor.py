"""Studio Connector-editor form flow tests (Mission 23 Flight 2 Leg 2, DD-9).

Covers: empty-state CTA, create → masked-token redisplay (the round-trip
the backend's `_looks_masked` contract exists to protect), doctor (no
plugin registered — the NORM this flight, Discord lands Flight 3), and
pairing-code generation. Kept small — the end-to-end stub round-trip
(create → pair → message → reply) is leg 3's behavior test's job, not
this browser lane's.

M25 F3 L4a: connectors are rows of the Library list and routed
(``#library/connectors/~new`` and ``/{id}``); the grid and its "New
Connector" CTA are retired, so the create form opens from the Library list's
Add menu (``_lists.library_add``). Leg 4b retired the interim Back: the item
header breadcrumb's "Connectors" link (``_lists.close_item``) returns to the
section root.
"""

from __future__ import annotations

import re

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _open_create_form(page: Page, base: str) -> None:
    """The connector create form, through the Library list's Add menu."""
    _nav.goto_settled(page, base, "library/connectors")
    _lists.library_add(page, "connectors")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_connectors_empty_inventory_shows_empty_state(app_clean: str, page: Page) -> None:
    """No connectors: the group's empty line and the section root's empty state,
    whose action opens the create form (the grid's CTA is retired)."""
    _nav.goto_settled(page, app_clean, "library/connectors")
    empty = _lists.library_empty_state(page, "connectors")
    expect(empty).to_be_visible(timeout=8000)
    expect(empty).to_contain_text("Links to chat platforms such as Discord")
    expect(
        page.locator(
            '[data-testid="library-list"] .ui-list-pane-group-empty', has_text="No connectors yet."
        )
    ).to_be_visible()
    page.locator('[data-testid="library-empty-connectors-add"]').click()
    _nav.expect_route(page, "library/connectors/~new")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_create_connector_shows_masked_token_on_redisplay(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Create a connector with a real token; after save, the token field
    redisplays the MASKED shape, never the plaintext — the same contract
    `tests/test_api_secret_mask_roundtrip.py` pins at the API layer."""
    _open_create_form(page, app_with_agent.base_url)

    save_btn = page.locator('[data-testid="save-connector-btn"]')

    page.locator('[data-field="name"]').fill("Browser Test Connector")
    page.locator('[data-field="type"]').select_option("discord")
    page.locator('[data-field="token"]').fill("real-plaintext-secret-value")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)

    save_btn.click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    token_value = page.locator('[data-field="token"]').input_value()
    assert token_value != "real-plaintext-secret-value"
    assert "real-plaintext-secret-value" not in page.content()


@pytest.mark.browser
def test_studio_connector_doctor_reports_plugin_failure_without_token(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Doctor on a "discord" connector (the browser lane's only creatable
    type without the stub gate, and the type leg 1 unconditionally
    registers in production) with no token configured renders the real
    plugin's own failure report, never a crash.

    RENAMED and re-aimed (Mission 23 Flight 3 Leg 3, AC-5): this test
    originally pinned the pre-Discord "no plugin registered" doctor path
    for a discord-typed connector. Leg 1's unconditional production
    Discord registration falsified that premise — the real plugin now
    answers with its own no-token failure instead. Stub-with-gate-closed
    was considered as the re-aim target and found unimplementable: stub
    creatability and stub plugin registration share the SAME dual gate
    (`api.py` `_creatable_connector_types` vs `app.py`'s startup hook), so
    with the gate closed the "stub" type isn't even selectable in this
    form — the browser lane never opens `THE_ONE_STUB_TEST_ENDPOINT`. This
    test instead targets the state the lane CAN reach: a tokenless
    discord-typed connector, asserting the failed status + message SHAPE
    (not exact prose) per the leg's design.
    """
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Doctor Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    doctor_btn = page.locator('[data-testid="connector-doctor-btn"]')
    expect(doctor_btn).to_be_visible(timeout=8000)
    doctor_btn.click()

    result = page.locator('[data-testid="connector-doctor-result"]')
    expect(result).to_contain_text("failed", timeout=8000)
    expect(result).to_contain_text("token", timeout=8000)


@pytest.mark.browser
def test_studio_connector_create_form_shows_no_status_led(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0045, pinned decision #1: the auto-probe (and its LED) is an
    edit-mode-only affordance — there is nothing to probe until the
    connector exists, so the create form must not render the LED at all."""
    _open_create_form(page, app_with_agent.base_url)

    expect(page.locator('[data-testid="connector-status-led"]')).to_have_count(0)


@pytest.mark.browser
def test_studio_connector_status_led_reflects_doctor_result_on_open(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0045: opening an EXISTING connector auto-probes doctor once
    (no polling, no manual click) and reflects the result on the header
    LED — the operator's "auto green dot". A tokenless discord connector
    deterministically fails doctor (same plugin behavior the existing
    manual-doctor test pins), which maps to the `indicator-led--danger`
    state and a non-empty accessible label."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("LED Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    # Re-open fresh from the list — the clearest "opening an existing
    # connector" trigger, independent of the post-save auto-transition.
    _lists.close_item(page)
    _nav.expect_route(page, "library/connectors")
    _lists.open_item(page, "library/connectors", "LED Test Connector")

    led = page.locator('[data-testid="connector-status-led"]')
    expect(led).to_be_visible(timeout=8000)
    assert (led.get_attribute("aria-label") or "").strip() != ""

    expect(led).to_have_class("indicator-led indicator-led--danger", timeout=8000)
    assert (led.get_attribute("aria-label") or "").strip() == "Not connected"


@pytest.mark.browser
def test_studio_connector_enabled_checkbox_default_checked_and_persists(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-10 (Mission 23 Flight 3 Leg 2, DD-6): Enabled checkbox defaults to
    checked; saving without touching it omits ``config.enabled`` (sparse-
    config pattern) — reopening the saved connector shows it still checked."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Enabled Default Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)

    checkbox = page.locator('[data-field="enabled"]')
    expect(checkbox).to_be_visible(timeout=8000)
    expect(checkbox).to_be_checked()

    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    _lists.close_item(page)
    _nav.expect_route(page, "library/connectors")
    _lists.open_item(page, "library/connectors", "Enabled Default Connector")
    expect(page.locator('[data-field="enabled"]')).to_be_checked(timeout=8000)


@pytest.mark.browser
def test_studio_connector_enabled_checkbox_unchecked_persists_disabled(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Unchecking the Enabled checkbox saves ``enabled: false``; editing a
    disabled connector shows it unchecked (the checked-state trap: the
    render must key off ``!== false``, never a truthy check)."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Disabled Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-field="enabled"]').uncheck()

    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="enabled"]')).not_to_be_checked()

    _lists.close_item(page)
    _nav.expect_route(page, "library/connectors")
    _lists.open_item(page, "library/connectors", "Disabled Connector")
    expect(page.locator('[data-field="enabled"]')).not_to_be_checked(timeout=8000)


@pytest.mark.browser
def test_studio_connector_pairing_code_generation(app_with_agent: SeededApp, page: Page) -> None:
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Pairing Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    pairing_btn = page.locator('[data-testid="connector-pairing-btn"]')
    expect(pairing_btn).to_be_visible(timeout=8000)
    pairing_btn.click()

    result = page.locator('[data-testid="connector-pairing-result"]')
    expect(result).to_contain_text("Expires", timeout=8000)


@pytest.mark.browser
def test_studio_connector_pairing_code_is_selectable_and_copyable(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0043: the generated code must land in its own element (not
    fused into the surrounding "Code: ... (expires ...)" prose, which the
    operator could not select/copy) and carry a labelled copy affordance."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Copyable Pairing Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    pairing_btn = page.locator('[data-testid="connector-pairing-btn"]')
    expect(pairing_btn).to_be_visible(timeout=8000)
    pairing_btn.click()

    result = page.locator('[data-testid="connector-pairing-result"]')
    code_el = page.locator('[data-testid="connector-pairing-code"]')
    expect(code_el).to_be_visible(timeout=8000)

    code_text = code_el.text_content() or ""
    assert code_text.strip() != ""
    # The code's own element holds just the code — not the whole prose
    # string ("Code: ... (expires ...)") the surrounding status text used
    # to fuse it into.
    assert "expires" not in code_text.lower()
    assert code_text.strip() in (result.text_content() or "")

    copy_btn = page.locator('[data-testid="connector-pairing-copy-btn"]')
    expect(copy_btn).to_be_visible()
    assert (copy_btn.get_attribute("aria-label") or "").strip() != ""


@pytest.mark.browser
def test_studio_connector_setup_steps_shown_per_type(app_with_agent: SeededApp, page: Page) -> None:
    """Squawk 0046: selecting a connector type on the CREATE form (where a
    first-timer needs it most) renders a short static per-type step list —
    each list names the one thing that silently breaks that platform's
    setup (Discord: Message Content intent; Telegram: /setprivacy privacy
    mode) — plus a plain-text reference naming the full walkthrough doc's
    path (not a link: only `/static` is mounted, so an `<a href="docs/...">`
    would 404 — see squawk 0046's Corrective Action)."""
    _open_create_form(page, app_with_agent.base_url)

    steps = page.locator('[data-testid="connector-setup-steps"]')
    expect(steps).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("discord")
    discord_list = page.locator('[data-testid="connector-setup-steps-list-discord"]')
    expect(discord_list).to_be_visible(timeout=8000)
    expect(discord_list).to_contain_text("Message Content Intent")

    page.locator('[data-field="type"]').select_option("telegram")
    telegram_list = page.locator('[data-testid="connector-setup-steps-list-telegram"]')
    expect(telegram_list).to_be_visible(timeout=8000)
    expect(telegram_list).to_contain_text("/setprivacy")

    doc_ref = page.locator('[data-testid="connector-setup-steps-doc-ref"]')
    expect(doc_ref).to_be_visible()
    doc_ref_text = doc_ref.text_content() or ""
    assert "docs/connector-setup.md" in doc_ref_text
    # Regression guard for the dead-link review fix: this must NOT be an
    # anchor pointing at an unmounted path (only `/static` is mounted; see
    # squawk 0046's Corrective Action).
    assert doc_ref.evaluate("el => el.tagName") != "A"


@pytest.mark.browser
def test_delete_connector_confirm_lapse_is_visually_distinct(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the Danger Zone
    connector-delete confirm (`connector-editor.js:599`) is distinguishable
    on screen from one that was never armed, past the real 3s `revertMs`."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Lapse Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    delete_btn = page.locator('[data-testid="delete-connector-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_have_text("Delete Connector")


@pytest.mark.browser
def test_connector_rename_updates_the_editor_title(app_clean: str, page: Page) -> None:
    """Squawk 0126: the h1 follows an edit save's new name without re-opening."""
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Before rename")
    _nav.goto_settled(page, app_clean, "library/connectors")
    _lists.open_item(page, "library/connectors", "Before rename")
    title = page.locator(".editor-title")
    expect(title).to_have_text("Before rename", timeout=8000)
    page.locator('[data-field="name"]').fill("After rename")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(title).to_have_text("After rename", timeout=8000)
