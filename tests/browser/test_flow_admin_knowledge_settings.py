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


def _flip(page: Page) -> None:
    """Click the watch switch through its label (the input is visually hidden)."""
    page.locator(".ui-toggle-label").filter(
        has=page.locator('[data-testid="knowledge-watch-enabled-toggle"]')
    ).click()


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
    expect(page.locator('[data-testid="knowledge-embedding-backend"]')).to_have_text(
        "Local (bundled)"
    )
    expect(page.locator('[data-testid="knowledge-embedding-model"]')).to_have_text(
        "potion-retrieval-32M"
    )
    expect(page.locator('[data-testid="knowledge-embedding-dim"]')).to_have_text("512")
    expect(page.locator('[data-testid="knowledge-vector-store-backend"]')).to_have_text("USearch")
    expect(page.locator('[data-testid="knowledge-vector-store-dtype"]')).to_have_text(
        "16-bit float"
    )

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
    expect(page.locator('[data-testid="knowledge-chunking-note"]')).to_contain_text("from now on")
    expect(page.locator('[data-testid="knowledge-monitoring-note"]')).to_contain_text(
        "as soon as you save"
    )


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

    _flip(page)  # off
    expect(save_btn).to_be_enabled()
    save_btn.click()
    expect(page.locator('[data-testid="knowledge-settings-flash"]')).to_contain_text(
        "Saved", timeout=8000
    )

    page.reload()
    expect(page.locator('[data-testid="knowledge-watch-enabled-toggle"]')).not_to_be_checked(
        timeout=8000
    )

    _flip(page)  # on
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
    expect(page.locator('[data-testid="knowledge-size-chars-error"]')).to_have_count(0)


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
    expect(overlap_error).to_have_count(0)
    expect(save_btn).to_be_enabled()

    overlap_input.fill("501")
    expect(overlap_error).to_contain_text("500")
    expect(save_btn).to_be_disabled()

    # Cross-field: fix overlap back to the (now-valid) boundary, then shrink
    # size_chars so the SAME overlap value becomes invalid without touching
    # the overlap field again.
    overlap_input.fill("500")
    expect(overlap_error).to_have_count(0)
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

    # A plain-string detail has no field: it reads at the editor level (the shell's error).
    error = page.locator('[data-testid="knowledge-settings-error"]')
    expect(error).to_contain_text("must not exceed 50%", timeout=8000)
    expect(error).not_to_contain_text("422")
    expect(page.locator('[data-testid="knowledge-settings-flash"]')).to_have_text("")


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


# ── Leg 10 (M31 F4): DD8-14 to DD8-18, A18-A24, B15 ────────────────────────

SIZE = '[data-testid="knowledge-size-chars-input"]'
OVERLAP = '[data-testid="knowledge-overlap-chars-input"]'
INTERVAL = '[data-testid="knowledge-reconcile-interval-input"]'
SAVE = '[data-testid="knowledge-settings-save-btn"]'
CANCEL = '[data-testid="knowledge-settings-cancel-btn"]'
FLASH = '[data-testid="knowledge-settings-flash"]'
HOLD_PUT_JS = """() => {
  window.__puts = 0;
  window.__release = null;
  const real = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    if (String(url).indexOf('/api/knowledge-settings') !== -1 && opts && opts.method === 'PUT') {
      window.__puts += 1;
      return new Promise(function (resolve) {
        window.__release = function () { resolve(real(url, opts)); };
      });
    }
    return real(url, opts);
  };
}"""


@pytest.mark.browser
def test_hints_are_in_the_inputs_accessible_descriptions(app_clean: str, page: Page) -> None:
    """DD8-14: each hint is linked to its input by aria-describedby."""
    _goto_knowledge(app_clean, page)
    expect(page.locator(SIZE)).to_have_accessible_description("200 to 2000 characters.")
    expect(page.locator(OVERLAP)).to_have_accessible_description("At most half the chunk size.")
    expect(page.locator(INTERVAL)).to_have_accessible_description("10 seconds to 24 hours")


@pytest.mark.browser
def test_typing_during_a_held_save_is_kept_and_saves_once(app_clean: str, page: Page) -> None:
    """DD8-15: Save is busy while the PUT is out (no second PUT), the fields stay live,
    and the response never overwrites what was typed meanwhile."""
    _goto_knowledge(app_clean, page)
    page.evaluate(HOLD_PUT_JS)
    save = page.locator(SAVE)
    page.locator(SIZE).fill("1200")
    expect(save).to_be_enabled()
    save.click()
    expect(save).to_be_disabled()
    page.wait_for_function("() => window.__puts === 1")

    # Typing during the request: the field takes it and Save stays busy.
    page.locator(OVERLAP).fill("120")
    expect(page.locator(OVERLAP)).to_have_value("120")
    expect(save).to_be_disabled()

    page.evaluate("() => window.__release()")
    # The response lands: the saved value is the baseline, the newer typing is kept and
    # dirty, so Save is enabled again for it.
    expect(page.locator(FLASH)).to_contain_text("Saved", timeout=8000)
    expect(page.locator(OVERLAP)).to_have_value("120")
    expect(page.locator(SIZE)).to_have_value("1200")
    expect(save).to_be_enabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    assert page.evaluate("() => window.__puts") == 1


@pytest.mark.browser
def test_a_second_save_inside_three_seconds_keeps_its_error(app_clean: str, page: Page) -> None:
    """DD8-16: the 'Saved.' timer is cleared by the next attempt, so it never wipes a
    later attempt's error."""
    _goto_knowledge(app_clean, page)
    page.locator(SIZE).fill("1200")
    page.locator(SAVE).click()
    expect(page.locator(FLASH)).to_contain_text("Saved", timeout=8000)

    def fulfill_422(route):
        route.fulfill(
            status=422,
            content_type="application/json",
            body='{"detail": "The settings were refused."}',
        )

    page.route("**/api/knowledge-settings", fulfill_422)
    page.locator(SIZE).fill("1300")
    page.locator(SAVE).click()
    error = page.locator('[data-testid="knowledge-settings-error"]')
    expect(error).to_contain_text("The settings were refused", timeout=8000)
    expect(page.locator(FLASH)).to_have_text("")
    page.wait_for_timeout(3600)
    expect(error).to_contain_text("The settings were refused")


@pytest.mark.browser
def test_focus_returns_after_save(app_clean: str, page: Page) -> None:
    """DD8-17: a keyboard Save leaves focus on the page, not on <body>."""
    _goto_knowledge(app_clean, page)
    page.locator(SIZE).fill("1200")
    page.locator(SAVE).focus()
    page.keyboard.press("Enter")
    expect(page.locator(FLASH)).to_contain_text("Saved", timeout=8000)
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(".editor-title")).to_be_focused(timeout=3000)


@pytest.mark.browser
def test_server_422_on_a_field_shows_on_that_field(app_clean: str, page: Page) -> None:
    """DD8-18: a field-level 422 names its field (replacing the hint) and clears when
    that field is edited."""
    _goto_knowledge(app_clean, page)

    def fulfill_422(route):
        route.fulfill(
            status=422,
            content_type="application/json",
            body=(
                '{"detail": [{"type": "less_than_equal", "loc": ["size_chars"],'
                ' "msg": "Input should be less than or equal to 1900"}]}'
            ),
        )

    page.route("**/api/knowledge-settings", fulfill_422)
    page.locator(SIZE).fill("1500")
    page.locator(SAVE).click()
    error = page.locator('[data-testid="knowledge-size-chars-error"]')
    expect(error).to_have_text("Must be at most 1900", timeout=8000)
    expect(page.locator(SIZE)).to_have_accessible_description("Must be at most 1900")
    # The error replaces the hint (A21); the other fields are untouched.
    expect(page.get_by_text("200 to 2000 characters.")).to_have_count(0)
    expect(page.locator('[data-testid="knowledge-overlap-chars-error"]')).to_have_count(0)
    expect(page.locator('[data-testid="knowledge-settings-error"]')).to_have_count(0)
    # Editing the field clears the server's error and brings the hint back.
    page.locator(SIZE).fill("1400")
    expect(error).to_have_count(0)
    expect(page.get_by_text("200 to 2000 characters.")).to_have_count(1)


@pytest.mark.browser
def test_page_header_holds_cancel_save_and_the_intro(app_clean: str, page: Page) -> None:
    """A19 and B15: Cancel and Save sit in the page header with the unsaved caption, and
    the page has an intro line."""
    _goto_knowledge(app_clean, page)
    header = page.locator(".page-header")
    expect(header.locator(CANCEL)).to_be_visible()
    expect(header.locator(SAVE)).to_be_visible()
    expect(header.locator(CANCEL)).to_be_disabled()
    expect(header.locator(SAVE)).to_be_disabled()
    expect(page.locator('[data-testid="knowledge-settings-intro"]')).to_be_visible()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    # Cancel sits left of Save, both at the header's right edge.
    c = header.locator(CANCEL).bounding_box()
    s = header.locator(SAVE).bounding_box()
    h = header.bounding_box()
    assert c["x"] < s["x"]
    assert abs((s["x"] + s["width"]) - (h["x"] + h["width"])) <= 40
    page.locator(SIZE).fill("1200")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(header.locator(CANCEL)).to_be_enabled()


@pytest.mark.browser
def test_cancel_restores_the_baseline_and_the_guard_goes_quiet(app_clean: str, page: Page) -> None:
    """Cancel patches every field back, clears errors, resets the echo and revalidates;
    leaving afterwards raises no prompt (onDirtyChange fires on the Cancel edge)."""
    _goto_knowledge(app_clean, page)
    page.locator(SIZE).fill("100")
    page.locator(INTERVAL).fill("3600")
    _flip(page)
    expect(page.locator('[data-testid="knowledge-size-chars-error"]')).to_be_visible()
    expect(page.locator('[data-testid="knowledge-reconcile-interval-echo"]')).to_have_text("1 hour")
    page.locator(CANCEL).click()
    expect(page.locator(SIZE)).to_have_value("1000")
    expect(page.locator(INTERVAL)).to_have_value("300")
    expect(page.locator('[data-testid="knowledge-watch-enabled-toggle"]')).to_be_checked()
    expect(page.locator('[data-testid="knowledge-size-chars-error"]')).to_have_count(0)
    expect(page.locator('[data-testid="knowledge-reconcile-interval-echo"]')).to_have_text(
        "5 minutes"
    )
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(CANCEL)).to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    expect(page.locator(".editor-title")).to_be_focused(timeout=3000)
    _lists.settings_nav_link(page, "appearance").click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=8000)


@pytest.mark.browser
def test_sections_have_one_rule_and_sentence_case_titles(app_clean: str, page: Page) -> None:
    """A18: each section draws one rule (its title's), no section border."""
    _goto_knowledge(app_clean, page)
    titles = page.locator(
        '[data-testid^="knowledge-settings-"][data-testid$="-section"] > .section-title'
    )
    assert titles.all_text_contents() == ["Chunking", "Monitoring", "Embedding", "Vector store"]
    rules = page.evaluate(
        """() => [...document.querySelectorAll(
          '[data-testid^="knowledge-settings-"][data-testid$="-section"]')].map(s => ({
            border: getComputedStyle(s).borderTopWidth,
            rule: getComputedStyle(s.querySelector('.section-title'), '::after').height,
          }))"""
    )
    assert len(rules) == 4
    for r in rules:
        assert r == {"border": "0px", "rule": "1px"}, rules


@pytest.mark.browser
def test_watch_switch_is_the_library_switch_on_one_line(app_clean: str, page: Page) -> None:
    """A20 (ledger row 40): the library switch, label and track on one line, and it
    saves only through Save."""
    _goto_knowledge(app_clean, page)
    toggle = page.locator('[data-testid="knowledge-watch-enabled-toggle"]')
    expect(toggle).to_have_attribute("role", "switch")
    label = page.locator(".ui-toggle-label").filter(has=toggle)
    expect(label).to_contain_text("Watch registered folders for changes")
    box = label.bounding_box()
    assert box["height"] < 40, box
    assert page.locator(".tool-enable-switch").count() == 0
    _flip(page)
    expect(page.locator(SAVE)).to_be_enabled()
    # Not saved until Save: a reload still reads the stored value.
    page.reload()
    expect(page.locator('[data-testid="knowledge-watch-enabled-toggle"]')).to_be_checked(
        timeout=8000
    )


@pytest.mark.browser
def test_error_replaces_the_hint_and_overlap_checks_its_own_limit(
    app_clean: str, page: Page
) -> None:
    """A21: an error replaces the hint, and the overlap is checked against its limit even
    while the chunk size is itself invalid."""
    _goto_knowledge(app_clean, page)
    hint = page.locator('[data-testid="knowledge-overlap-hint"]')
    expect(hint).to_have_text("At most half the chunk size.")
    page.locator(SIZE).fill("100")  # invalid: below 200
    page.locator(OVERLAP).fill("80")  # over floor(100 / 2) = 50
    overlap_error = page.locator('[data-testid="knowledge-overlap-chars-error"]')
    expect(overlap_error).to_contain_text("50")
    expect(hint).to_have_count(0)
    expect(page.locator(SIZE)).to_have_accessible_description(
        "Chunk size must be between 200 and 2000."
    )
    page.locator(OVERLAP).fill("40")
    expect(overlap_error).to_have_count(0)
    expect(hint).to_have_text("At most half the chunk size.")


@pytest.mark.browser
@pytest.mark.parametrize(
    ("typed", "echo"),
    [
        ("900", "15 minutes"),
        ("3600", "1 hour"),
        ("86400", "1 day"),
        ("90", "1 minute 30 seconds"),
        ("45", "45 seconds"),
        ("", ""),
        ("5", ""),
    ],
)
def test_interval_is_echoed_humanised(app_clean: str, page: Page, typed: str, echo: str) -> None:
    """A22: the hint states the range in words and the value is echoed beside the field;
    blank or invalid shows no echo."""
    _goto_knowledge(app_clean, page)
    page.locator(INTERVAL).fill(typed)
    echo_el = page.locator('[data-testid="knowledge-reconcile-interval-echo"]')
    if echo:
        expect(echo_el).to_have_text(echo)
    else:
        expect(echo_el).to_have_text("")


@pytest.mark.browser
def test_read_only_values_are_humanised_with_plain_notes(app_clean: str, page: Page) -> None:
    """A23 and A24: friendly values, the model id kept, plain wording."""
    _goto_knowledge(app_clean, page)
    expect(page.locator('[data-testid="knowledge-embedding-backend"]')).to_have_text(
        "Local (bundled)"
    )
    expect(page.locator('[data-testid="knowledge-vector-store-backend"]')).to_have_text("USearch")
    expect(page.locator('[data-testid="knowledge-vector-store-dtype"]')).to_have_text(
        "16-bit float"
    )
    for testid in (
        "knowledge-embedding-readonly-reason",
        "knowledge-vector-store-readonly-reason",
        "knowledge-chunking-note",
        "knowledge-monitoring-note",
    ):
        text = page.locator(f'[data-testid="{testid}"]').inner_text()
        assert "Read-only:" not in text and "operator" not in text, (testid, text)


ADMIN_REFRESH = "() => App.areas.find((a) => a.id === 'admin')._refresh()"


@pytest.mark.browser
def test_clean_refresh_remounts_and_a_dirty_one_keeps_edits(app_clean: str, page: Page) -> None:
    """A clean _refresh re-mounts the page from a fresh GET, dropping 'Saved.'
    deliberately; a dirty one leaves the edits alone."""
    _goto_knowledge(app_clean, page)
    page.locator(SIZE).fill("1200")
    page.locator(SAVE).click()
    expect(page.locator(FLASH)).to_contain_text("Saved", timeout=8000)
    page.evaluate(ADMIN_REFRESH)
    expect(page.locator(FLASH)).to_have_text("")
    expect(page.locator(SIZE)).to_have_value("1200", timeout=8000)
    # Dirty: a refresh does not touch the edit.
    page.locator(SIZE).fill("1300")
    page.evaluate(ADMIN_REFRESH)
    page.wait_for_timeout(300)
    expect(page.locator(SIZE)).to_have_value("1300")
    expect(page.locator(SAVE)).to_be_enabled()
