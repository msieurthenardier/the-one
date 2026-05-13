"""End-to-end flow tests: cross-area dirty-gate (F4 L5).

Covers the confirmLeave hook on the area descriptor consumed by
app.js:switchTo before deactivating the outgoing area. Both admin and
studio expose the hook (admin shipped in F3 L06; studio gains parity in
F4 L05). One parametrized test file amortizes fixture setup across both
areas.

Test matrix (2 base tests × 2 areas):
  - dirty_editor_topbar_cancel_keeps_state
  - dirty_editor_topbar_confirm_navigates_cleanly

Both parametrize across (area_id, fixture_name, editor_setup, dirty_helper).
"""

from __future__ import annotations

import urllib.parse

import pytest
from browser.seeders import SeededApp  # plus any area-specific helpers
from playwright.sync_api import Page, expect


# Per-area setup helpers — these abstract over the differences between
# admin's provider-editor entry path and studio's agent-editor entry path
# so the parametrized tests can run the same body for both.

def _setup_studio_editor(page: Page, app: SeededApp) -> None:
    """Navigate to studio + open the seeded agent in the editor.

    Waits for `.section-nav[aria-label="Agent Studio sections"]` rather than
    the `.section-nav-header` element, which is not rendered because studio.js
    omits the `header:` option (sidebar header suppressed; topbar area button
    already names the area). Falls through to entity-tile click when the editor
    is still hidden (bare #studio/agents grid view — no auto-selection).
    """
    page.goto(f"{app.base_url}#studio")
    # Wait for the section-nav to mount (signals studio area init complete).
    expect(
        page.locator('.section-nav[aria-label="Agent Studio sections"]')
    ).to_be_visible(timeout=8000)
    editor_hidden = page.evaluate(
        "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
    )
    if editor_hidden:
        page.locator("button.entity-tile").first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)


def _setup_admin_editor(page: Page, app: SeededApp) -> None:
    """Deep-link directly to admin provider editor — avoids tile-click
    ordering nondeterminism. Mirrors test_flow_provider_dirty_confirm.py:30's
    direct-hash-route pattern."""
    page.goto(f"{app.base_url}#admin/providers/{app.provider_id}")
    # Wait for the admin section-nav to mount (signals admin area init complete).
    expect(
        page.locator('.section-nav[aria-label="System sections"]')
    ).to_be_visible(timeout=8000)
    # The provider-editor's Name field (#pf-name) is the canonical
    # always-rendered signal — it appears for every provider type. Admin
    # uses ID selectors; studio's agent-editor uses data-field selectors.
    expect(page.locator('#pf-name')).to_be_visible(timeout=8000)


def _dirty_studio_form(page: Page) -> None:
    """Type into the studio agent-editor description field."""
    desc = page.locator('[data-field="description"]')
    desc.click()
    desc.fill("dirty edit " + str(id(page))[:6])


def _dirty_admin_form(page: Page) -> None:
    """Type into the admin provider-editor's Name field. Same selector as
    test_flow_provider_dirty_confirm.py:36's `name_input = page.locator("#pf-name")`
    — always-rendered text input on every provider type. (Admin's
    provider editor uses ID selectors; studio's tabbed agent editor uses
    data-field selectors. Both patterns coexist in the codebase.)"""
    name_field = page.locator('#pf-name')
    name_field.click()
    name_field.fill("dirty edit " + str(id(page))[:6])


# Parametrize across both areas. Each parametrize entry pairs a name with
# its setup + dirty helpers + cross-area target. The setup signature
# differs slightly between areas (admin needs the provider_id from the
# fixture); the test body uses functools.partial-style helpers in setup
# to abstract over this.
AREA_MATRIX = [
    pytest.param(
        "studio",
        "app_with_agent",
        # studio setup takes just base_url
        lambda page, app: _setup_studio_editor(page, app),
        _dirty_studio_form,
        "admin",
        id="studio",
    ),
    pytest.param(
        "admin",
        "app_with_provider",
        # admin setup needs the provider_id for the direct deep-link
        lambda page, app: _setup_admin_editor(page, app),
        _dirty_admin_form,
        "studio",
        id="admin",
    ),
]


@pytest.mark.browser
@pytest.mark.parametrize("area,fixture_name,setup,dirty,target", AREA_MATRIX)
def test_dirty_editor_topbar_cancel_keeps_state(
    request, area, fixture_name, setup, dirty, target, page: Page
) -> None:
    """Cross-area topbar click while dirty → confirm dialog → cancel →
    URL rolls back to source area, editor still mounted."""
    seeded = request.getfixturevalue(fixture_name)

    setup(page, seeded)
    dirty(page)

    topbar_target = page.locator(f'#app-topbar .app-picker-button[data-area="{target}"]')
    topbar_target.click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()
    page.locator('[data-testid="modal-cancel-btn"]').click()

    expect(overlay).to_have_count(0)
    # URL rolled back to source area (app.js rolls back to the area root via
    # priorHash — the sub-state written by replaceSub may differ from the
    # full editor URL, but the area prefix is always correct after cancel).
    current_hash = page.evaluate("location.hash")
    assert current_hash.startswith(f"#{area}"), \
        f"Expected hash to start with #{area} after cancel, got {current_hash}"
    # The target-area content panel must NOT be active (we cancelled, so we
    # stayed on the source area). Wait briefly for any async transitions.
    expect(
        page.locator(f'#main-content .content-panel.area-{target}.active')
    ).to_have_count(0)
    # Source-area content panel should be active (cancel kept us here).
    expect(
        page.locator(f'#main-content .content-panel.area-{area}.active')
    ).to_be_visible(timeout=3000)


@pytest.mark.browser
@pytest.mark.parametrize("area,fixture_name,setup,dirty,target", AREA_MATRIX)
def test_dirty_editor_topbar_confirm_navigates_cleanly(
    request, area, fixture_name, setup, dirty, target, page: Page
) -> None:
    """Cross-area topbar click while dirty → confirm dialog → confirm →
    URL is target area → return to source area → no stale editor mount."""
    seeded = request.getfixturevalue(fixture_name)

    setup(page, seeded)
    dirty(page)

    page.locator(f'#app-topbar .app-picker-button[data-area="{target}"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()
    page.locator('[data-testid="modal-confirm-btn"]').click()

    expect(overlay).to_have_count(0)
    # URL is target area.
    target_hash = page.evaluate("location.hash")
    assert target_hash.startswith(f"#{target}"), \
        f"Expected hash to start with #{target}, got {target_hash}"

    # Return to source area via topbar.
    page.locator(f'#app-topbar .app-picker-button[data-area="{area}"]').click()

    # No dialog should appear on the return navigation (the original dirty
    # editor is GONE; the source area should re-mount clean — verifies the
    # stale-then guard).
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)

    # Source-area content panel is active (wait for DOM transition).
    expect(
        page.locator(f'#main-content .content-panel.area-{area}.active')
    ).to_be_visible(timeout=5000)
