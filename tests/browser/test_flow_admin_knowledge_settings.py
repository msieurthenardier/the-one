"""Administration → Knowledge settings panel (M24 F06 L04, DD-7 / L4-D1..D6).

Covers the leg's acceptance criteria (AC-1 through AC-9):

- AC-1: reachable at `#admin/knowledge` (since M25 F2
  `#settings/knowledge-indexing`, the "Knowledge indexing" page since M25 F3
  leg 5a) including on a full page load; other categories still route.
- AC-2: renders current values for all four editable settings and for the
  read-only embedding/vector-store records.
- AC-3: editing and saving persists — verified via a subsequent `GET`, not
  by trusting the rendered form.
- AC-4: embedding/vector-store are read-only with a stated reason; no
  control attempts to change either.
- AC-5: the panel states chunking is future-indexing-only and monitoring is
  live.
- AC-6: client-side bounds (200-2000 / 10-86400 / floor(size/2) for
  overlap), including the cross-field re-evaluation when `size_chars`
  changes.
- AC-7: a server 422 that arrives anyway renders its `detail` text, not a
  bare status code (exercised via a routed 422, since the client mirrors
  the server's bounds exactly by design — L4-D3 — so no client-valid /
  server-invalid daylight exists to trigger this organically).
- AC-8: `monitoring.watch_enabled` toggles and is reflected by a subsequent
  `GET`.
- AC-9: dirty-confirm on navigate-away with unsaved changes; no dialog when
  clean (L4-D4).
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect


def _goto_knowledge(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/knowledge-indexing")
    expect(page.locator(".page-title")).to_have_text("Knowledge indexing", timeout=8000)
    expect(page.locator('[data-testid="knowledge-size-chars-input"]')).to_have_value(
        "1000", timeout=8000
    )


@pytest.mark.browser
def test_knowledge_category_reachable_on_full_page_load(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/knowledge-indexing")
    expect(page.locator(".page-title")).to_have_text("Knowledge indexing", timeout=8000)
    _nav.expect_route(page, "settings/knowledge-indexing")
    expect(_lists.settings_nav_link(page, "knowledge-indexing")).to_be_visible()
    _lists.expect_settings_selected(page, "knowledge-indexing")


@pytest.mark.browser
def test_other_categories_still_route(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/appearance")
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=8000)
    _nav.goto(page, app_clean, "settings/prompts")
    expect(page.locator(".page-title")).to_have_text("Prompts", timeout=8000)
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".page-title")).to_have_text("Built-in tools", timeout=8000)
    _nav.goto(page, app_clean, "settings/knowledge-indexing")
    expect(page.locator(".page-title")).to_have_text("Knowledge indexing", timeout=8000)


@pytest.mark.browser
def test_panel_renders_defaults_and_readonly_sections(app_clean: str, page: Page) -> None:
    _goto_knowledge(app_clean, page)

    expect(page.locator('[data-testid="knowledge-overlap-chars-input"]')).to_have_value("150")
    expect(page.locator('[data-testid="knowledge-watch-enabled-toggle"]')).to_be_checked()
    expect(page.locator('[data-testid="knowledge-reconcile-interval-input"]')).to_have_value("300")

    # Read-only records (AC-2, AC-4).
    expect(page.locator('[data-testid="knowledge-embedding-backend"]')).to_have_text("local")
    expect(page.locator('[data-testid="knowledge-embedding-model"]')).to_have_text(
        "potion-retrieval-32M"
    )
    expect(page.locator('[data-testid="knowledge-embedding-dim"]')).to_have_text("512")
    expect(page.locator('[data-testid="knowledge-vector-store-backend"]')).to_have_text("usearch")
    expect(page.locator('[data-testid="knowledge-vector-store-dtype"]')).to_have_text("f16")

    # Stated reasons, not disabled inputs (AC-4) — no <input>/<select> in
    # either read-only section.
    embedding_section = page.locator('[data-testid="knowledge-settings-embedding-section"]')
    expect(
        embedding_section.locator('[data-testid="knowledge-embedding-readonly-reason"]')
    ).to_be_visible()
    assert embedding_section.locator("input, select").count() == 0
    vs_section = page.locator('[data-testid="knowledge-settings-vector-store-section"]')
    expect(
        vs_section.locator('[data-testid="knowledge-vector-store-readonly-reason"]')
    ).to_be_visible()
    assert vs_section.locator("input, select").count() == 0

    # AC-5: application-semantics notes on screen.
    expect(page.locator('[data-testid="knowledge-chunking-note"]')).to_contain_text("future")
    expect(page.locator('[data-testid="knowledge-monitoring-note"]')).to_contain_text("immediately")


@pytest.mark.browser
def test_edit_and_save_persists_across_reload(app_clean: str, page: Page) -> None:
    """AC-3: a subsequent GET (via reload, re-reading the rendered form
    against the server) returns the edited values."""
    _goto_knowledge(app_clean, page)

    size_input = page.locator('[data-testid="knowledge-size-chars-input"]')
    overlap_input = page.locator('[data-testid="knowledge-overlap-chars-input"]')
    interval_input = page.locator('[data-testid="knowledge-reconcile-interval-input"]')
    save_btn = page.locator('[data-testid="knowledge-settings-save-btn"]')

    expect(save_btn).to_be_disabled()

    size_input.fill("1200")
    overlap_input.fill("100")
    interval_input.fill("600")
    expect(save_btn).to_be_enabled()

    save_btn.click()
    expect(page.locator('[data-testid="knowledge-settings-flash"]')).to_contain_text(
        "Saved", timeout=8000
    )
    expect(save_btn).to_be_disabled()

    # Read back through a fresh GET via full reload (AC-3 verification path).
    page.reload()
    expect(page.locator('[data-testid="knowledge-size-chars-input"]')).to_have_value(
        "1200", timeout=8000
    )
    expect(page.locator('[data-testid="knowledge-overlap-chars-input"]')).to_have_value("100")
    expect(page.locator('[data-testid="knowledge-reconcile-interval-input"]')).to_have_value("600")


@pytest.mark.browser
def test_watch_enabled_toggle_persists(app_clean: str, page: Page) -> None:
    """AC-8: watch_enabled can be toggled off and back on, reflected by a
    subsequent GET."""
    _goto_knowledge(app_clean, page)

    toggle = page.locator('[data-testid="knowledge-watch-enabled-toggle"]')
    save_btn = page.locator('[data-testid="knowledge-settings-save-btn"]')
    expect(toggle).to_be_checked()

    toggle.click()  # off
    expect(save_btn).to_be_enabled()
    save_btn.click()
    expect(page.locator('[data-testid="knowledge-settings-flash"]')).to_contain_text(
        "Saved", timeout=8000
    )

    page.reload()
    expect(page.locator('[data-testid="knowledge-watch-enabled-toggle"]')).not_to_be_checked(
        timeout=8000
    )

    page.locator('[data-testid="knowledge-watch-enabled-toggle"]').click()  # on
    expect(save_btn).to_be_enabled()
    save_btn.click()
    expect(page.locator('[data-testid="knowledge-settings-flash"]')).to_contain_text(
        "Saved", timeout=8000
    )
    page.reload()
    expect(page.locator('[data-testid="knowledge-watch-enabled-toggle"]')).to_be_checked(
        timeout=8000
    )


@pytest.mark.browser
def test_size_chars_out_of_range_refused_client_side(app_clean: str, page: Page) -> None:
    _goto_knowledge(app_clean, page)
    size_input = page.locator('[data-testid="knowledge-size-chars-input"]')
    save_btn = page.locator('[data-testid="knowledge-settings-save-btn"]')

    size_input.fill("100")  # below 200
    expect(page.locator('[data-testid="knowledge-size-chars-error"]')).to_contain_text("200")
    expect(save_btn).to_be_disabled()

    size_input.fill("5000")  # above 2000
    expect(page.locator('[data-testid="knowledge-size-chars-error"]')).to_contain_text("2000")
    expect(save_btn).to_be_disabled()

    size_input.fill("1500")  # back in range
    expect(page.locator('[data-testid="knowledge-size-chars-error"]')).to_be_hidden()


@pytest.mark.browser
def test_reconcile_interval_out_of_range_refused_client_side(app_clean: str, page: Page) -> None:
    _goto_knowledge(app_clean, page)
    interval_input = page.locator('[data-testid="knowledge-reconcile-interval-input"]')
    save_btn = page.locator('[data-testid="knowledge-settings-save-btn"]')

    interval_input.fill("5")  # below 10
    expect(page.locator('[data-testid="knowledge-reconcile-interval-error"]')).to_contain_text("10")
    expect(save_btn).to_be_disabled()

    interval_input.fill("90000")  # above 86400
    expect(page.locator('[data-testid="knowledge-reconcile-interval-error"]')).to_contain_text(
        "86400"
    )
    expect(save_btn).to_be_disabled()


@pytest.mark.browser
def test_overlap_bound_is_floor_and_cross_field(app_clean: str, page: Page) -> None:
    """AC-6: overlap_chars must not exceed floor(size_chars / 2) — tested at
    the boundary, not the middle — and the check re-evaluates when
    size_chars changes, not only on overlap edits."""
    _goto_knowledge(app_clean, page)
    size_input = page.locator('[data-testid="knowledge-size-chars-input"]')
    overlap_input = page.locator('[data-testid="knowledge-overlap-chars-input"]')
    overlap_error = page.locator('[data-testid="knowledge-overlap-chars-error"]')
    save_btn = page.locator('[data-testid="knowledge-settings-save-btn"]')

    # size_chars = 1001 -> floor(1001/2) = 500. 500 is allowed, 501 is not.
    size_input.fill("1001")
    overlap_input.fill("500")
    expect(overlap_error).to_be_hidden()
    expect(save_btn).to_be_enabled()

    overlap_input.fill("501")
    expect(overlap_error).to_contain_text("500")
    expect(save_btn).to_be_disabled()

    # Cross-field: fix overlap back to the (now-valid) boundary, then shrink
    # size_chars so the SAME overlap value becomes invalid without touching
    # the overlap field again.
    overlap_input.fill("500")
    expect(overlap_error).to_be_hidden()
    expect(save_btn).to_be_enabled()

    size_input.fill("200")  # floor(200/2) = 100 < 500
    expect(overlap_error).to_contain_text("100")
    expect(save_btn).to_be_disabled()


@pytest.mark.browser
def test_server_422_renders_detail_text(app_clean: str, page: Page) -> None:
    """AC-7: a server 422 that arrives anyway renders its `detail` text, not
    a bare status code. The client mirrors the server's bounds exactly
    (L4-D3), so this is exercised via a routed response rather than an
    organic client-valid/server-invalid gap — there is no legitimate
    client-valid input that the server would 422, so `page.route()`
    interception is the ONLY way to exercise this render path at all. Do
    not "simplify" this to an unrouted save expecting a real 422; there is
    no such input by design."""
    _goto_knowledge(app_clean, page)

    def fulfill_422(route):
        route.fulfill(
            status=422,
            content_type="application/json",
            body='{"detail": "overlap_chars (999) must not exceed 50% of size_chars (1000)"}',
        )

    page.route("**/api/knowledge-settings", fulfill_422)

    size_input = page.locator('[data-testid="knowledge-size-chars-input"]')
    size_input.fill("1500")
    page.locator('[data-testid="knowledge-settings-save-btn"]').click()

    flash = page.locator('[data-testid="knowledge-settings-flash"]')
    expect(flash).to_contain_text("must not exceed 50%", timeout=8000)
    expect(flash).not_to_contain_text("422")


@pytest.mark.browser
def test_load_failure_renders_error_state_not_empty_form(app_clean: str, page: Page) -> None:
    """Edge case: a failed GET renders a load-failure banner rather than an
    empty form that would save defaults over stored values."""

    def fulfill_500(route):
        route.fulfill(status=500, content_type="application/json", body='{"detail": "boom"}')

    page.route("**/api/knowledge-settings", fulfill_500)
    _nav.goto(page, app_clean, "settings/knowledge-indexing")

    expect(page.locator('[data-testid="knowledge-settings-load-error"]')).to_be_visible(
        timeout=8000
    )
    expect(page.locator('[data-testid="knowledge-settings-save-btn"]')).to_be_disabled()


@pytest.mark.browser
def test_dirty_confirm_on_navigate_away(app_clean: str, page: Page) -> None:
    """AC-9: navigating away with unsaved changes raises the confirm
    dialog; navigating away with no changes does not (L4-D4).

    Returns to Knowledge with a second `page.goto()` (a same-document fragment
    navigation back to an already-visited route). The router's current route
    updates on every URL write, so a hashchange back to a route the area has
    already left is treated as a real traversal, not "already there".
    """
    _goto_knowledge(app_clean, page)

    # Clean navigation away — no dialog.
    _lists.settings_nav_link(page, "appearance").click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=8000)

    _goto_knowledge(app_clean, page)
    page.locator('[data-testid="knowledge-size-chars-input"]').fill("1200")
    expect(page.locator('[data-testid="knowledge-settings-save-btn"]')).to_be_enabled()

    _lists.settings_nav_link(page, "appearance").click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=8000)

    # Cancel keeps us on Knowledge indexing with the edit intact.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".page-title")).to_have_text("Knowledge indexing")
    expect(page.locator('[data-testid="knowledge-size-chars-input"]')).to_have_value("1200")

    # Confirm proceeds to Appearance.
    _lists.settings_nav_link(page, "appearance").click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=8000)
