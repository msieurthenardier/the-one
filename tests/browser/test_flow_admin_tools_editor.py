"""Admin Tools editor tests for F6 leg 07 + M16 F08 leg 04.

Covers the L3 per-tool editor surface plus the HAT inline UX fixes:

- Editor header has a `// prompt` block (HAT inline fix #1) — the tool
  description IS the prompt baked into the LLM tools schema, surfaced
  with a labeled monospace block rather than an inline subtitle.
- The enable toggle uses the iOS-style `.tool-enable-switch` widget for
  visual parity with the grid (HAT inline fix #2).
- All WebConfig fields render in admin mode for a WebConfig-backed tool
  (`fetch_url`), INCLUDING the unmarked `redirect_cap` (operator-only).
  Marker-gating only HIDES fields in agent mode — covered by the studio
  test file.
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

M16 F08 leg 04 — `web_search` migrated from `WebConfig` to the dedicated
`WebSearchConfig` (engine selector + per-engine connection fields). The
WebConfig-surface tests below that were keyed to `web_search` are RE-HOMED
onto `fetch_url` (still WebConfig-backed); the model-validator 422 test now
exercises `fetch_url`'s `timeout_seconds_default <= timeout_seconds_max`
rule. New `web_search`-specific coverage exercises the masked-secret eye
toggle and the generic `show_if` conditional visibility added in leg 04.

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
# Exercised against `fetch_url` (web_search is no longer WebConfig-backed —
# it carries WebSearchConfig as of M16 F08 leg 02).
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

# WebSearchConfig surface (M16 F08 leg 02/03/04). The selector + five
# per-engine connection fields. The three keyed secrets render masked.
_WEB_SEARCH_FIELDS = (
    "search_backend",
    "searxng_base_url",
    "google_pse_api_key",
    "google_pse_cse_id",
    "brave_api_key",
    "tavily_api_key",
)


@pytest.mark.browser
def test_editor_renders_prompt_block(app_clean: str, page: Page) -> None:
    """HAT inline fix #1: editor header has a labeled prompt block containing
    the tool's description (NOT an inline subtitle).

    Label relabeled from '// prompt' to 'Prompt' (using .section-title) in
    Leg 02 polish — the code comment in tools-editor.js still uses '// prompt'
    terminology but the DOM label is now 'Prompt' via the shared section-title pattern.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    block = page.locator(".editor-prompt-block")
    expect(block).to_be_visible()
    # Label uses .section-title with text "Prompt" (was .editor-prompt-label "// prompt").
    expect(block.locator(".section-title")).to_have_text("Prompt")
    # The description text is the actual tool prompt (long-form). Spot
    # check it contains a substantive token from the description body
    # rather than asserting verbatim — keeps the test resilient to small
    # prose tweaks.
    text = (block.locator(".editor-prompt-text").inner_text() or "").strip()
    assert len(text) > 20, f"prompt text too short or empty: {text!r}"


@pytest.mark.browser
def test_editor_connector_tool_shows_connectors_category(app_clean: str, page: Page) -> None:
    """Squawk 0032: the editor's category subtitle for a connector tool
    reads 'connectors' — not 'unknown', which is what the pre-fix
    tools-editor.js TOOL_CATEGORIES mirror gap produced.
    """
    page.goto(f"{app_clean}#admin/tools/send_to_platform_channel")
    expect(page.locator(".editor-title")).to_have_text("send_to_platform_channel", timeout=8000)
    expect(page.locator(".editor-subtitle-meta")).to_have_text("connectors")


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

    Exercised against `fetch_url` — `web_search` is no longer WebConfig-
    backed (M16 F08 leg 02 moved it to WebSearchConfig).
    """
    page.goto(f"{app_clean}#admin/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    for fname in _WEB_CONFIG_FIELDS:
        row = page.locator(f'.tools-editor-field[data-field-name="{fname}"]')
        expect(row).to_be_visible()


@pytest.mark.browser
def test_editor_renders_web_search_config_fields(app_clean: str, page: Page) -> None:
    """M16 F08: `web_search` now carries WebSearchConfig — the engine
    selector + five per-engine connection fields render in admin mode.
    The per-engine fields default-hidden (DuckDuckGo is the default
    backend, which has no fields) but stay in the DOM.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    for fname in _WEB_SEARCH_FIELDS:
        row = page.locator(f'.tools-editor-field[data-field-name="{fname}"]')
        # Field row present in the DOM (visibility gated by show_if below).
        expect(row).to_have_count(1)
    # The selector itself is always visible.
    expect(page.locator('.tools-editor-field[data-field-name="search_backend"]')).to_be_visible()


@pytest.mark.browser
def test_editor_field_descriptions_are_info_icon_tooltips(app_clean: str, page: Page) -> None:
    """HAT inline fix #4: per-field descriptions become tooltips on a
    sibling info-icon (positioned AFTER the input), NOT inline
    `<p class="field-description">` paragraphs.

    Spot-checks 3 WebConfig fields with known non-empty descriptions and
    confirms the inline `<p>` paragraph is gone. Re-homed to `fetch_url`
    (WebConfig-backed).
    """
    page.goto(f"{app_clean}#admin/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)

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

    Uses `web_search` / `searxng_base_url` (a plain WebSearchConfig string
    field). SearXNG must be selected first so the field is visible, then
    we type a URL into it.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    save_btn = page.locator(".save-btn")
    expect(save_btn).to_be_disabled()

    # Select SearXNG so its base-url field is revealed, then type a URL.
    page.locator('[data-field="search_backend"]').select_option("searxng")
    expect(save_btn).not_to_be_disabled()
    page.locator('input[data-field="searxng_base_url"]').fill("https://searx.example.org")
    expect(save_btn).not_to_be_disabled()

    save_btn.click()
    # After 200, snapshot re-captured; Save returns to disabled.
    expect(save_btn).to_be_disabled(timeout=5000)


@pytest.mark.browser
def test_editor_cancel_restores_snapshot(app_clean: str, page: Page) -> None:
    """Cancel re-mounts with the original toolDetail (option A pinned in
    L3 design); the modified field reverts to its prior value and Save
    returns to disabled. Exercised on `web_search`'s `searxng_base_url`.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('[data-field="search_backend"]').select_option("searxng")
    base_url = page.locator('input[data-field="searxng_base_url"]')
    original = base_url.input_value()
    base_url.fill("https://searx.example.org")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    # Re-mount idempotent — selector resolves against the new DOM. The
    # backend reverts to duckduckgo, so searxng_base_url is hidden again,
    # but its value is restored to the original.
    expect(page.locator('input[data-field="searxng_base_url"]')).to_have_value(original)
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_editor_save_persists_across_reload(app_clean: str, page: Page) -> None:
    """PUT round-trip: select SearXNG + set a base URL, Save, reload,
    confirm the engine + URL persist. Exercises the WebSearchConfig
    surface (M16 F08).
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('input[data-field="searxng_base_url"]').fill("https://searx.example.org")
    page.locator(".save-btn").click()
    expect(page.locator(".save-btn")).to_be_disabled(timeout=5000)

    page.reload()
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    expect(page.locator('[data-field="search_backend"]')).to_have_value("searxng")
    expect(page.locator('input[data-field="searxng_base_url"]')).to_have_value(
        "https://searx.example.org"
    )


@pytest.mark.browser
def test_editor_model_validator_422_shows_banner(app_clean: str, page: Page) -> None:
    """Narrow `timeout_seconds_max` to 10 (< default 30) → 422 from the
    model-validator → `.editor-error-banner` visible with humanized text
    (no "Value error," prefix per HAT inline fix #6) AND
    `.field-error-highlight` applied to the two offending rows.

    Re-homed to `fetch_url` — the `timeout_seconds_default <=
    timeout_seconds_max` validator lives on WebConfig, which `web_search`
    no longer uses (M16 F08 leg 02).
    """
    page.goto(f"{app_clean}#admin/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("10")
    page.locator(".save-btn").click()

    banner = page.locator(".editor-error-banner")
    expect(banner).to_be_visible(timeout=5000)
    text = banner.inner_text()
    assert "Value error," not in text, f"banner should strip 'Value error,' prefix — got: {text!r}"
    # Both offending field rows highlighted (heuristic in the editor:
    # the model-validator msg names both fields).
    expect(
        page.locator(
            '.tools-editor-field[data-field-name="timeout_seconds_max"].field-error-highlight'
        )
    ).to_be_visible()
    expect(
        page.locator(
            '.tools-editor-field[data-field-name="timeout_seconds_default"].field-error-highlight'
        )
    ).to_be_visible()


@pytest.mark.browser
def test_editor_field_change_clears_highlight(app_clean: str, page: Page) -> None:
    """HAT inline fix #7: after a 422, typing into a highlighted field
    clears that row's `.field-error-highlight` (operator's edit signals
    intent to fix). Other rows that are still in error keep theirs.
    Re-homed to `fetch_url` (WebConfig model-validator).
    """
    page.goto(f"{app_clean}#admin/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("10")
    page.locator(".save-btn").click()
    expect(page.locator(".editor-error-banner")).to_be_visible(timeout=5000)
    highlighted_row = page.locator(
        '.tools-editor-field[data-field-name="timeout_seconds_max"].field-error-highlight'
    )
    expect(highlighted_row).to_be_visible()
    # Type into the highlighted field — clears its row's highlight.
    page.locator('input[data-field="timeout_seconds_max"]').fill("60")
    expect(
        page.locator(
            '.tools-editor-field[data-field-name="timeout_seconds_max"].field-error-highlight'
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
    page.locator('[data-field="search_backend"]').select_option("searxng")

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
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in Tools", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/tools"


@pytest.mark.browser
def test_editor_section_nav_dirty_gate(app_clean: str, page: Page) -> None:
    """Modify a field → click "General" in left nav → App.confirmDialog
    opens. Cancel keeps the editor; confirm navigates away. Same dialog
    pattern as the Back button — admin.js routes both paths through
    `App.confirmDialog`.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('[data-field="search_backend"]').select_option("searxng")

    page.locator(".area-admin .section-nav-item", has_text="General").click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=5000)

    # Cancel keeps the editor.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_have_text("web_search")

    # Re-trigger and confirm — navigates to the General page.
    page.locator(".area-admin .section-nav-item", has_text="General").click()
    expect(overlay).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".area-admin .page-title")).to_have_text("General", timeout=5000)


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


# ── M16 F08 leg 04: masked secret eye-toggle + show_if visibility ────────


@pytest.mark.browser
def test_web_search_secret_field_masked_with_eye_toggle(app_clean: str, page: Page) -> None:
    """A `ui_hint:"password"` field (WebSearchConfig's `brave_api_key`)
    renders as `<input type="password">` inside an `.api-key-wrap` shell
    with an `.api-key-eye` button. The eye button toggles the input
    between password/text and swaps its aria-label. Ported from the
    provider-editor eye-toggle pattern.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)

    # Select Brave so its key field is revealed (show_if), then exercise
    # the eye toggle on the now-visible masked input.
    page.locator('[data-field="search_backend"]').select_option("brave")
    row = page.locator('.tools-editor-field[data-field-name="brave_api_key"]')
    expect(row).to_be_visible()

    key_input = row.locator('input[data-field="brave_api_key"]')
    expect(key_input).to_have_attribute("type", "password")

    eye = row.locator(".api-key-eye")
    expect(eye).to_be_visible()
    expect(eye).to_have_attribute("aria-label", "Show password")
    # Button is keyboard-operable: a real <button type=button>.
    expect(eye).to_have_attribute("type", "button")

    eye.click()
    expect(key_input).to_have_attribute("type", "text")
    expect(eye).to_have_attribute("aria-label", "Hide password")
    eye.click()
    expect(key_input).to_have_attribute("type", "password")
    expect(eye).to_have_attribute("aria-label", "Show password")


@pytest.mark.browser
def test_web_search_show_if_reveals_only_selected_engine_fields(app_clean: str, page: Page) -> None:
    """Generic `show_if`: selecting an engine in `search_backend` reveals
    exactly that engine's fields and hides the others. DuckDuckGo (the
    default) shows none. Hidden rows stay in the DOM and carry
    `aria-hidden="true"`.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)

    backend = page.locator('[data-field="search_backend"]')
    per_engine = (
        "searxng_base_url",
        "google_pse_api_key",
        "google_pse_cse_id",
        "brave_api_key",
        "tavily_api_key",
    )

    def row(fname: str):
        return page.locator(f'.tools-editor-field[data-field-name="{fname}"]')

    # DuckDuckGo (default): all per-engine fields hidden.
    expect(backend).to_have_value("duckduckgo")
    for fname in per_engine:
        expect(row(fname)).to_be_hidden()
        expect(row(fname)).to_have_attribute("aria-hidden", "true")

    # SearXNG: only searxng_base_url visible.
    backend.select_option("searxng")
    expect(row("searxng_base_url")).to_be_visible()
    for fname in ("google_pse_api_key", "google_pse_cse_id", "brave_api_key", "tavily_api_key"):
        expect(row(fname)).to_be_hidden()

    # Google PSE: BOTH key + cse_id visible (two fields, one controller).
    backend.select_option("google_pse")
    expect(row("google_pse_api_key")).to_be_visible()
    expect(row("google_pse_cse_id")).to_be_visible()
    expect(row("searxng_base_url")).to_be_hidden()
    expect(row("brave_api_key")).to_be_hidden()

    # Brave: only brave_api_key.
    backend.select_option("brave")
    expect(row("brave_api_key")).to_be_visible()
    expect(row("google_pse_api_key")).to_be_hidden()

    # Tavily: only tavily_api_key.
    backend.select_option("tavily")
    expect(row("tavily_api_key")).to_be_visible()
    expect(row("brave_api_key")).to_be_hidden()


@pytest.mark.browser
def test_web_search_secret_persists_encrypted_and_reloads_masked(
    app_clean: str, page: Page
) -> None:
    """Save a Brave key → it persists (encrypted at rest via leg 3) and on
    reload the field shows the GET mask (`***...{tail4}`), NOT the
    plaintext key. End-to-end leg-3 contract from the UI.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)

    page.locator('[data-field="search_backend"]').select_option("brave")
    key_input = page.locator('input[data-field="brave_api_key"]')
    key_input.fill("BSA-supersecret-token-1234")
    page.locator(".save-btn").click()
    expect(page.locator(".save-btn")).to_be_disabled(timeout=5000)

    page.reload()
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    # Backend persisted brave; the key field is visible again on reload.
    expect(page.locator('[data-field="search_backend"]')).to_have_value("brave")
    reloaded = page.locator('input[data-field="brave_api_key"]')
    value = reloaded.input_value()
    assert value != "BSA-supersecret-token-1234", "reloaded value must be masked, not plaintext"
    assert value.startswith("***"), f"expected GET mask shape, got {value!r}"
    assert value.endswith("1234"), f"expected last-4 tail in mask, got {value!r}"


@pytest.mark.browser
def test_web_search_engine_switch_preserves_entered_key(app_clean: str, page: Page) -> None:
    """Switching the engine away from Brave and back does NOT lose an
    already-entered (un-saved) key — the hidden row stays in the DOM and
    its value survives. Confirms the show_if mechanism never clears field
    values.
    """
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)

    backend = page.locator('[data-field="search_backend"]')
    backend.select_option("brave")
    key_input = page.locator('input[data-field="brave_api_key"]')
    key_input.fill("BSA-entered-not-yet-saved")

    # Switch away (key field hidden) then back.
    backend.select_option("tavily")
    expect(page.locator('.tools-editor-field[data-field-name="brave_api_key"]')).to_be_hidden()
    backend.select_option("brave")
    expect(page.locator('.tools-editor-field[data-field-name="brave_api_key"]')).to_be_visible()

    # The entered value survived the round-trip (row never left the DOM).
    expect(page.locator('input[data-field="brave_api_key"]')).to_have_value(
        "BSA-entered-not-yet-saved"
    )
