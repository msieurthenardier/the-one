"""End-to-end flow tests: provider editor dirty-state + App.confirmDialog modal (F6 leg 04).

Mirrors test_flow_dirty_confirm.py (F5 leg 04 studio dirty-confirm tests) for
the provider editor's three navigation gates (Back, section-nav, beforeunload).

Covers:

- Back-when-clean does not show dialog.
- Back-when-dirty shows dialog; cancel keeps editor; confirm navigates to grid.
- Section-nav-when-clean does not show dialog.
- Section-nav-when-dirty shows dialog; cancel keeps editor; confirm navigates.
- Section-nav from grid (no editor) does not show dialog even after a prior
  dirty-then-discard cycle (orchestrator's mirror reset).
- Save resets dirty (subsequent Back has no dialog).
- Cancel button resets dirty in edit mode (revert + Back has no dialog).
- Dialog Escape dismisses; Enter confirms.
- beforeunload listener: synthetic event with dirty=True → defaultPrevented;
  with dirty=False → not defaultPrevented.
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _open_editor(page: Page, app: SeededApp) -> None:
    """Navigate to the provider editor and wait for the Name input to mount."""
    page.goto(f"{app.base_url}#admin/providers/{app.provider_id}")
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)


def _make_dirty(page: Page) -> None:
    """Type into the Name field to mark the form dirty."""
    name_input = page.locator("#pf-name")
    name_input.click()
    name_input.fill("dirty-edit")
    # Wait for Save to enable as the dirty-flip signal (synchronous from the
    # input event, but Playwright's expect is the safe poll).
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_enabled()


@pytest.mark.browser
def test_back_when_clean_no_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """Back when clean does NOT open dialog; navigates to grid immediately."""
    _open_editor(page, app_with_provider)
    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_back_when_dirty_shows_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """Back when dirty opens the App.confirmDialog modal."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=3000)


@pytest.mark.browser
def test_back_dialog_cancel_keeps_editor(app_with_provider: SeededApp, page: Page) -> None:
    """Cancel ('Stay') in the Back-dirty dialog keeps the editor + URL."""
    _open_editor(page, app_with_provider)
    initial_hash = page.evaluate("location.hash")
    _make_dirty(page)
    page.locator('[data-testid="back-provider-btn"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_be_visible()
    assert page.evaluate("location.hash") == initial_hash


@pytest.mark.browser
def test_back_dialog_confirm_navigates_to_grid(app_with_provider: SeededApp, page: Page) -> None:
    """Confirm ('Continue') in the Back-dirty dialog navigates to the grid."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('[data-testid="back-provider-btn"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_section_nav_when_clean_no_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """Section-nav click when editor is clean does NOT open dialog."""
    _open_editor(page, app_with_provider)
    page.locator('.section-nav-item[data-section="general"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    assert page.evaluate("location.hash") == "#admin/general"


@pytest.mark.browser
def test_section_nav_when_dirty_shows_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """Section-nav click when editor is dirty opens the modal."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('.section-nav-item[data-section="general"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=3000)


@pytest.mark.browser
def test_section_nav_dialog_cancel_keeps_editor(app_with_provider: SeededApp, page: Page) -> None:
    """Stay on the section-nav dialog keeps the editor + hash."""
    _open_editor(page, app_with_provider)
    initial_hash = page.evaluate("location.hash")
    _make_dirty(page)
    page.locator('.section-nav-item[data-section="general"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_be_visible()
    assert page.evaluate("location.hash") == initial_hash


@pytest.mark.browser
def test_section_nav_dialog_confirm_navigates_to_system(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Continue on the section-nav dialog navigates to System."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('.section-nav-item[data-section="general"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(overlay).to_have_count(0)
    assert page.evaluate("location.hash") == "#admin/general"


@pytest.mark.browser
def test_section_nav_from_grid_no_dialog_after_prior_discard(
    app_with_provider: SeededApp, page: Page
) -> None:
    """After Back-dirty-discard returns to grid, section-nav from grid does
    NOT show a dialog (orchestrator mirror is reset on doHandleBack)."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('[data-testid="back-provider-btn"]').click()
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)
    # Now navigate from the grid to System — no dialog because no editor.
    page.locator('.section-nav-item[data-section="general"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    assert page.evaluate("location.hash") == "#admin/general"


@pytest.mark.browser
def test_save_resets_dirty(app_with_provider: SeededApp, page: Page) -> None:
    """Successful Save clears dirty; subsequent Back does not show dialog."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('[data-testid="save-provider-btn"]').click()
    # Save flash signals success; then the editor stays mounted in edit mode.
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled(timeout=5000)

    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)


@pytest.mark.browser
def test_cancel_button_resets_dirty_in_edit(app_with_provider: SeededApp, page: Page) -> None:
    """Cancel button reverts form + clears dirty; subsequent Back has no dialog."""
    _open_editor(page, app_with_provider)
    original_name = page.locator("#pf-name").input_value()
    _make_dirty(page)
    page.locator('[data-testid="cancel-provider-btn"]').click()
    expect(page.locator("#pf-name")).to_have_value(original_name)
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled()

    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)


@pytest.mark.browser
def test_dialog_escape_cancels(app_with_provider: SeededApp, page: Page) -> None:
    """Escape closes the dialog without confirming; hash + editor preserved."""
    _open_editor(page, app_with_provider)
    initial_hash = page.evaluate("location.hash")
    _make_dirty(page)
    page.locator('[data-testid="back-provider-btn"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.keyboard.press("Escape")
    expect(overlay).to_have_count(0)
    assert page.evaluate("location.hash") == initial_hash
    expect(page.locator(".editor-title")).to_be_visible()


@pytest.mark.browser
def test_dialog_enter_confirms(app_with_provider: SeededApp, page: Page) -> None:
    """Enter confirms the dialog (focus on Cancel; Enter binding is global)."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('[data-testid="back-provider-btn"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.keyboard.press("Enter")
    expect(overlay).to_have_count(0)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_beforeunload_listener_prevents_when_dirty(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Synthetic beforeunload when dirty has defaultPrevented = True."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)

    prevented = page.evaluate(
        """() => {
            const e = new Event('beforeunload', { cancelable: true });
            window.dispatchEvent(e);
            return e.defaultPrevented;
        }"""
    )
    assert prevented is True


@pytest.mark.browser
def test_beforeunload_listener_does_not_prevent_when_clean(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Synthetic beforeunload when clean has defaultPrevented = False."""
    _open_editor(page, app_with_provider)

    prevented = page.evaluate(
        """() => {
            const e = new Event('beforeunload', { cancelable: true });
            window.dispatchEvent(e);
            return e.defaultPrevented;
        }"""
    )
    assert prevented is False
