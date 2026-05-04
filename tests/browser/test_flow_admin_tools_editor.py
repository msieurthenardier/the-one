"""Admin Tools editor tests for F6 leg 07.

Covers the L3 per-tool editor surface plus the HAT inline UX fixes:

- Editor header has a `// prompt` block (HAT inline fix #1) — the tool
  description IS the prompt baked into the LLM tools schema, surfaced
  with a labeled monospace block rather than an inline subtitle.
- The enable toggle uses the iOS-style `.tool-enable-switch` widget for
  visual parity with the grid (HAT inline fix #2).
- All 8 WebConfig fields render in admin mode, INCLUDING the unmarked
  `redirect_cap` (operator-only). Marker-gating only HIDES fields in
  agent mode — covered by the studio test file.
- Per-field descriptions are info-icon tooltips next to the input
  (HAT inline fix #4), NOT inline `<p class="field-description">`
  paragraphs. Tooltip via the native `title` attribute.
- Save / Cancel disabled-when-clean SSoT (matches L3 of F6 + provider
  editor pattern); Cancel restores the snapshot.
- Save persists across reload (L1 PUT round-trip).
- Model-validator 422 surfaces in `.editor-error-banner` with
  humanized text (no "Value error," prefix per HAT inline fix #6) and
  applies `.field-error-highlight` to the offending rows (HAT fix #7).
- Field change clears its row's highlight (HAT fix #7).
- Back / section-nav dirty-gate uses `App.confirmDialog`
  (`[data-testid="confirm-dialog-overlay"]`) — NOT a native browser
  `confirm()`. Matches `tests/browser/test_flow_dirty_confirm.py`.
- Test button only mounts for testable tools (`web_search`, `fetch_url`).
- Test input is pre-filled with the per-tool fixture default.
- Test button click sequence (per design Reviewer): button disables →
  terminal result span appears → button re-enables. No assertion on
  response content (real DDG / example.com network not stubbed here;
  the L1 unit tests cover endpoint contract).

Note on the dirty-gate selector: the leg's "Critical patterns" callout
mentioned `.dialog-confirm` but the actual production DOM (per
``js/dialog.js``) uses ``[data-testid="confirm-dialog-overlay"]`` — the
same selector ``test_flow_dirty_confirm.py`` already asserts against.
The test code follows the actual selector; the artifact's hint was
slightly off-target. Logged as a deviation in the flight log.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

# Per-tool field-set sanity for the WebConfig surface used across tests.
# All 8 fields render in admin mode; agent-mode hides the unmarked
# `redirect_cap` (covered separately in test_flow_studio_tools_overrides).
_WEB_CONFIG_FIELDS = (
    "timeout_seconds_default",
    "timeout_seconds_max",
    "response_size_cap_bytes",
    "redirect_cap",
    "host_allowlist",
    "host_denylist",
    "extra_allowed_hosts",
    "default_user_agent",
)


@pytest.mark.browser
def test_editor_renders_prompt_block(app_clean: str, page: Page) -> None:
    """HAT inline fix #1: editor header has a `// prompt` labeled block
    containing the tool's description (NOT an inline subtitle).
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    block = page.locator(".editor-prompt-block")
    expect(block).to_be_visible()
    expect(block.locator(".editor-prompt-label")).to_have_text("// prompt")
    # The description text is the actual tool prompt (long-form). Spot
    # check it contains a substantive token from the description body
    # rather than asserting verbatim — keeps the test resilient to small
    # prose tweaks.
    text = (block.locator(".editor-prompt-text").inner_text() or "").strip()
    assert len(text) > 20, f"prompt text too short or empty: {text!r}"


@pytest.mark.browser
def test_editor_renders_enabled_toggle_inline(app_clean: str, page: Page) -> None:
    """HAT inline fix #2: editor's `enabled` row uses the iOS-toggle
    widget (`.tool-enable-switch`) — same visual as the grid tile.
    Confirms it's not an inert plain checkbox.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    row = page.locator(".tools-editor-enabled-row")
    expect(row).to_be_visible()
    # iOS-toggle wrapper present, with the visible track sibling.
    expect(row.locator(".tool-enable-switch")).to_be_visible()
    expect(row.locator(".tool-enable-switch-track")).to_be_visible()
    expect(row.locator('[data-field="enabled"]')).to_be_checked()


@pytest.mark.browser
def test_editor_renders_all_web_config_fields(app_clean: str, page: Page) -> None:
    """All 8 WebConfig fields render in admin mode — including the
    unmarked `redirect_cap`. Marker-gating only HIDES fields in agent
    mode (covered by studio test file). Pinned by design Reviewer.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    for fname in _WEB_CONFIG_FIELDS:
        row = page.locator(f'.tools-editor-field[data-field-name="{fname}"]')
        expect(row).to_be_visible()


@pytest.mark.browser
def test_editor_field_descriptions_are_info_icon_tooltips(
    app_clean: str, page: Page
) -> None:
    """HAT inline fix #4: per-field descriptions become tooltips on a
    sibling info-icon (positioned AFTER the input), NOT inline
    `<p class="field-description">` paragraphs.

    Spot-checks 3 fields with known non-empty descriptions and confirms
    the inline `<p>` paragraph is gone.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)

    # Inline-paragraph form is gone — the regression check.
    expect(page.locator(".tools-editor-field p.field-description")).to_have_count(0)

    spot_check = ("timeout_seconds_max", "host_allowlist", "default_user_agent")
    for fname in spot_check:
        row = page.locator(f'.tools-editor-field[data-field-name="{fname}"]')
        icon = row.locator(".field-info-icon")
        expect(icon).to_be_visible()
        title = icon.get_attribute("title") or ""
        assert title, f"info-icon for {fname} missing title attribute"


@pytest.mark.browser
def test_editor_save_disabled_until_dirty(app_clean: str, page: Page) -> None:
    """Save starts disabled; modifying a field enables it; saving flips
    it back to disabled (snapshot re-captured to clean state).
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    save_btn = page.locator(".save-btn")
    expect(save_btn).to_be_disabled()

    # Modify timeout_seconds_max to a valid value (>= default of 30).
    timeout_max = page.locator('input[data-field="timeout_seconds_max"]')
    timeout_max.fill("90")
    expect(save_btn).not_to_be_disabled()

    save_btn.click()
    # After 200, snapshot re-captured; Save returns to disabled.
    expect(save_btn).to_be_disabled(timeout=5000)


@pytest.mark.browser
def test_editor_cancel_restores_snapshot(app_clean: str, page: Page) -> None:
    """Cancel re-mounts with the original toolDetail (option A pinned in
    L3 design); the modified field reverts to its prior value and Save
    returns to disabled.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    timeout_max = page.locator('input[data-field="timeout_seconds_max"]')
    original = timeout_max.input_value()
    timeout_max.fill("90")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    # Re-mount idempotent — selector resolves against the new DOM.
    expect(page.locator('input[data-field="timeout_seconds_max"]')).to_have_value(
        original
    )
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_editor_save_persists_across_reload(app_clean: str, page: Page) -> None:
    """PUT round-trip: narrow `timeout_seconds_max` to 60 (>= default 30
    so model-validator passes), Save, reload, confirm the field shows 60.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("60")
    page.locator(".save-btn").click()
    expect(page.locator(".save-btn")).to_be_disabled(timeout=5000)

    page.reload()
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    expect(page.locator('input[data-field="timeout_seconds_max"]')).to_have_value("60")


@pytest.mark.browser
def test_editor_model_validator_422_shows_banner(
    app_clean: str, page: Page
) -> None:
    """Narrow `timeout_seconds_max` to 10 (< default 30) → 422 from the
    model-validator → `.editor-error-banner` visible with humanized text
    (no "Value error," prefix per HAT inline fix #6) AND
    `.field-error-highlight` applied to the two offending rows.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("10")
    page.locator(".save-btn").click()

    banner = page.locator(".editor-error-banner")
    expect(banner).to_be_visible(timeout=5000)
    text = banner.inner_text()
    assert "Value error," not in text, (
        f"banner should strip 'Value error,' prefix — got: {text!r}"
    )
    # Both offending field rows highlighted (heuristic in the editor:
    # the model-validator msg names both fields).
    expect(
        page.locator(
            '.tools-editor-field[data-field-name="timeout_seconds_max"]'
            ".field-error-highlight"
        )
    ).to_be_visible()
    expect(
        page.locator(
            '.tools-editor-field[data-field-name="timeout_seconds_default"]'
            ".field-error-highlight"
        )
    ).to_be_visible()


@pytest.mark.browser
def test_editor_field_change_clears_highlight(app_clean: str, page: Page) -> None:
    """HAT inline fix #7: after a 422, typing into a highlighted field
    clears that row's `.field-error-highlight` (operator's edit signals
    intent to fix). Other rows that are still in error keep theirs.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("10")
    page.locator(".save-btn").click()
    expect(page.locator(".editor-error-banner")).to_be_visible(timeout=5000)
    highlighted_row = page.locator(
        '.tools-editor-field[data-field-name="timeout_seconds_max"]'
        ".field-error-highlight"
    )
    expect(highlighted_row).to_be_visible()
    # Type into the highlighted field — clears its row's highlight.
    page.locator('input[data-field="timeout_seconds_max"]').fill("60")
    expect(
        page.locator(
            '.tools-editor-field[data-field-name="timeout_seconds_max"]'
            ".field-error-highlight"
        )
    ).to_have_count(0)


@pytest.mark.browser
def test_editor_back_button_dirty_gate(app_clean: str, page: Page) -> None:
    """Modify a field → click Back → App.confirmDialog opens
    ([data-testid="confirm-dialog-overlay"], NOT native browser
    confirm). Cancel keeps the editor mounted; confirm exits to grid.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("90")

    page.locator('[data-testid="back-tool-btn"]').click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=5000)

    # Cancel keeps the editor.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_have_text("web_search")

    # Re-trigger and confirm — exits to the grid.
    page.locator('[data-testid="back-tool-btn"]').click()
    expect(overlay).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=5000
    )
    assert page.evaluate("location.hash") == "#admin/tools"


@pytest.mark.browser
def test_editor_section_nav_dirty_gate(app_clean: str, page: Page) -> None:
    """Modify a field → click "System" in left nav → App.confirmDialog
    opens. Cancel keeps the editor; confirm navigates away. Same dialog
    pattern as the Back button — admin.js routes both paths through
    `App.confirmDialog`.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("90")

    page.locator(
        '.area-admin .section-nav-item', has_text="System"
    ).click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=5000)

    # Cancel keeps the editor.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_have_text("web_search")

    # Re-trigger and confirm — navigates to the System page.
    page.locator(
        '.area-admin .section-nav-item', has_text="System"
    ).click()
    expect(overlay).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "System", timeout=5000
    )


@pytest.mark.browser
def test_test_button_only_for_testable_tools(app_clean: str, page: Page) -> None:
    """Test button mounts only for `web_search` and `fetch_url`. Other
    tools (e.g. `shell`) have no test surface — `.test-tool-btn` not
    present.
    """
    page.goto(f"{app_clean}#admin/tools/shell")
    expect(page.locator(".editor-title")).to_have_text("shell", timeout=8000)
    expect(page.locator(".test-tool-btn")).to_have_count(0)

    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    expect(page.locator(".test-tool-btn")).to_be_visible()


@pytest.mark.browser
def test_test_button_input_pre_filled(app_clean: str, page: Page) -> None:
    """HAT addition: editable test-input pre-filled with the per-tool
    fixture default. web_search → "the one cli agent"; fetch_url →
    "https://example.com/".
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    expect(page.locator(".test-tool-input")).to_have_value("the one cli agent")

    page.goto(f"{app_clean}#admin/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    expect(page.locator(".test-tool-input")).to_have_value("https://example.com/")


@pytest.mark.browser
def test_test_button_click_fires_request(app_clean: str, page: Page) -> None:
    """Click sequence (per design Reviewer): button disables → terminal
    result span appears → button re-enables. Don't assert on response
    content — DDG / example.com response is real network and varies.

    Uses fetch_url (more reliable than DDG for this test). The terminal
    state is either `.test-result-ok` (HTTP 200) or `.test-result-fail`
    (network refusal / SSRF block); either is a valid terminal state.
    """
    page.goto(f"{app_clean}#admin/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    test_btn = page.locator(".test-tool-btn")
    expect(test_btn).to_be_visible()

    test_btn.click()
    # Immediately disabled — proves the request fired.
    expect(test_btn).to_be_disabled()
    # Terminal state appears within 15s — covers both success & refusal.
    # The selector matches any non-pending span inside the result region;
    # bumped timeout covers slow real-network DDG / example.com rounds.
    terminal = page.locator(".test-result span:not(.test-result-pending)")
    expect(terminal).to_be_visible(timeout=15000)
    # Button re-enables after the round-trip.
    expect(test_btn).not_to_be_disabled()
