"""End-to-end flow tests: provider editor dirty-state + App.confirmDialog modal (F6 leg 04).

Mirrors test_flow_dirty_confirm.py (F5 leg 04 studio dirty-confirm tests) for
the provider editor's navigation gates (the breadcrumb's "Library" link, a rail
destination, beforeunload). The provider editor opens in the Library detail pane
(sortie 02; it opened under the Settings tiles before) and Back is retired: the
item header's breadcrumb link (``_lists.close_item``) is the close, routed
through the same leave guard.

Covers:

- Breadcrumb-when-clean does not show dialog.
- Breadcrumb-when-dirty shows dialog; cancel keeps editor; confirm closes it.
- Rail-destination-when-clean does not show dialog.
- Rail-destination-when-dirty shows dialog; cancel keeps editor; confirm
  navigates (the rail's Settings goes to Appearance, ``_nav.open_destination``).
- A rail destination from the Library root (no editor) does not show dialog even
  after a prior dirty-then-discard cycle (the studio mirror reset).
- Save resets dirty (a subsequent close has no dialog).
- Cancel button resets dirty in edit mode (revert + close has no dialog).
- Dialog Escape dismisses; Enter activates the focused Stay (M25 F2 L2, DD6);
  Tab to Continue then Enter confirms.
- beforeunload listener: synthetic event with dirty=True → defaultPrevented;
  with dirty=False → not defaultPrevented.
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

# Poll window for the confirm dialog appearing after a trigger — see the same
# constant in test_flow_dirty_confirm.py. App.confirmDialog appends the overlay
# synchronously (dialog.js), so there is no earlier sync point; under full-suite
# / same-lane load the click→handler→append chain is delayed by event-loop
# scheduling and can overrun a tight expect timeout. A generous window is the
# root-cause-aligned remedy (this file previously used timeouts as low as 3s,
# which flaked under the F5 `system` browser lane's back-to-back load).
_DIALOG_TIMEOUT = 8000


def _open_editor(page: Page, app: SeededApp) -> None:
    """Navigate to the provider editor and wait for the Name input to mount."""
    _nav.goto(page, app.base_url, f"library/providers/{_nav.seg(app.provider_id)}")
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
def test_breadcrumb_when_clean_no_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """The breadcrumb when clean does NOT open dialog; closes the editor at once."""
    _open_editor(page, app_with_provider)
    _lists.close_item(page)
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator("#pf-name")).to_have_count(0, timeout=5000)
    expect(_lists.list_row(page, "library/providers", "mock")).to_be_visible()
    _nav.expect_route(page, "library")


@pytest.mark.browser
def test_breadcrumb_when_dirty_shows_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """The breadcrumb when dirty opens the App.confirmDialog modal."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    _lists.close_item(page)
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(
        timeout=_DIALOG_TIMEOUT
    )


@pytest.mark.browser
def test_breadcrumb_dialog_cancel_keeps_editor(app_with_provider: SeededApp, page: Page) -> None:
    """Cancel ('Stay') in the breadcrumb-dirty dialog keeps the editor + URL."""
    _open_editor(page, app_with_provider)
    initial_route = _nav.current_route(page)
    _make_dirty(page)
    _lists.close_item(page)
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=_DIALOG_TIMEOUT)

    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_be_visible()
    _nav.expect_route(page, initial_route)


@pytest.mark.browser
def test_breadcrumb_dialog_confirm_closes_the_editor(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Confirm ('Continue') in the breadcrumb-dirty dialog closes the editor;
    the list stays."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    _lists.close_item(page)
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=_DIALOG_TIMEOUT)

    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator("#pf-name")).to_have_count(0, timeout=5000)
    expect(_lists.list_row(page, "library/providers", "mock")).to_be_visible()
    _nav.expect_route(page, "library")


@pytest.mark.browser
def test_rail_destination_when_clean_no_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """A rail destination click when the editor is clean does NOT open dialog."""
    _open_editor(page, app_with_provider)
    _nav.open_destination(page, "settings")
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    _nav.expect_route(page, "settings/appearance")


@pytest.mark.browser
def test_rail_destination_when_dirty_shows_dialog(app_with_provider: SeededApp, page: Page) -> None:
    """A rail destination click when the editor is dirty opens the modal."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    _nav.open_destination(page, "settings")
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(
        timeout=_DIALOG_TIMEOUT
    )


@pytest.mark.browser
def test_rail_destination_dialog_cancel_keeps_editor(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Stay on the Rail-destination dialog keeps the editor + hash."""
    _open_editor(page, app_with_provider)
    initial_route = _nav.current_route(page)
    _make_dirty(page)
    _nav.open_destination(page, "settings")
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=_DIALOG_TIMEOUT)

    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_be_visible()
    _nav.expect_route(page, initial_route)


@pytest.mark.browser
def test_rail_destination_dialog_confirm_navigates_to_appearance(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Continue on the Rail-destination dialog navigates to Appearance."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    _nav.open_destination(page, "settings")
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=_DIALOG_TIMEOUT)

    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(overlay).to_have_count(0)
    _nav.expect_route(page, "settings/appearance")


@pytest.mark.browser
def test_rail_destination_from_root_no_dialog_after_prior_discard(
    app_with_provider: SeededApp, page: Page
) -> None:
    """After a breadcrumb-dirty discard closes the editor, a rail destination
    from the Library root does NOT show a dialog (the orchestrator mirror is reset
    by the discard)."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    _lists.close_item(page)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator("#pf-name")).to_have_count(0, timeout=5000)
    # Now navigate from the Library root to Appearance — no dialog: no editor.
    _nav.open_destination(page, "settings")
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    _nav.expect_route(page, "settings/appearance")


@pytest.mark.browser
def test_save_resets_dirty(app_with_provider: SeededApp, page: Page) -> None:
    """Successful Save clears dirty; a subsequent close does not show dialog."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    page.locator('[data-testid="save-provider-btn"]').click()
    # Save flash signals success; then the editor stays mounted in edit mode.
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled(timeout=5000)

    _lists.close_item(page)
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator("#pf-name")).to_have_count(0, timeout=5000)


@pytest.mark.browser
def test_cancel_button_resets_dirty_in_edit(app_with_provider: SeededApp, page: Page) -> None:
    """Cancel button reverts form + clears dirty; a subsequent close has no dialog."""
    _open_editor(page, app_with_provider)
    original_name = page.locator("#pf-name").input_value()
    _make_dirty(page)
    page.locator('[data-testid="cancel-provider-btn"]').click()
    expect(page.locator("#pf-name")).to_have_value(original_name)
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled()

    _lists.close_item(page)
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)


@pytest.mark.browser
def test_dialog_escape_cancels(app_with_provider: SeededApp, page: Page) -> None:
    """Escape closes the dialog without confirming; hash + editor preserved."""
    _open_editor(page, app_with_provider)
    initial_route = _nav.current_route(page)
    _make_dirty(page)
    _lists.close_item(page)
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=_DIALOG_TIMEOUT)

    page.keyboard.press("Escape")
    expect(overlay).to_have_count(0)
    _nav.expect_route(page, initial_route)
    expect(page.locator(".editor-title")).to_be_visible()


@pytest.mark.browser
def test_dialog_enter_activates_focused_stay(app_with_provider: SeededApp, page: Page) -> None:
    """Enter activates the focused button, which is Stay by default (M25 F2 L2, DD6).

    Renamed and inverted from ``test_dialog_enter_confirms``: the global
    "Enter confirms" binding is gone. The dialog closes; the hash and editor stay.
    """
    _open_editor(page, app_with_provider)
    initial_route = _nav.current_route(page)
    _make_dirty(page)
    _lists.close_item(page)
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=_DIALOG_TIMEOUT)
    expect(page.locator('[data-testid="modal-cancel-btn"]')).to_be_focused()

    page.keyboard.press("Enter")
    expect(overlay).to_have_count(0)
    _nav.expect_route(page, initial_route)
    expect(page.locator(".editor-title")).to_be_visible()


@pytest.mark.browser
def test_dialog_tab_to_continue_then_enter_confirms(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Companion: Tab to Continue, then Enter, confirms and closes the editor."""
    _open_editor(page, app_with_provider)
    _make_dirty(page)
    _lists.close_item(page)
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=_DIALOG_TIMEOUT)

    page.keyboard.press("Tab")
    expect(page.locator('[data-testid="modal-confirm-btn"]')).to_be_focused()
    page.keyboard.press("Enter")
    expect(overlay).to_have_count(0)
    _nav.expect_route(page, "library")


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
