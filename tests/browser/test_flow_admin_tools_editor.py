"""Admin Tools editor tests for F6 leg 07 + M16 F08 leg 04.

Covers the L3 per-tool editor surface plus the HAT inline UX fixes:

- Editor header has a `// prompt` block (HAT inline fix #1) — the tool
  description IS the prompt baked into the LLM tools schema, surfaced
  with a labeled monospace block rather than an inline subtitle.
- The enable toggle uses the iOS-style switch (`App.ui.toggle`; formerly the legacy
  `.tool-enable-switch`) for
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
- Breadcrumb / Settings-nav-link dirty-gate uses `App.confirmDialog`
  (`[data-testid="confirm-dialog-overlay"]`) — NOT a native browser
  `confirm()`. Matches `tests/browser/test_flow_dirty_confirm.py`. (Since M25
  F3 leg 5b the editor opens below the tool list and Back is retired: the
  item header's "Settings / Built-in tools" breadcrumb link closes it.)
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

import json
import re

import pytest
from browser import _lists, _nav
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
    # The editor mounts only once GET /api/tools/configs/web_search resolves;
    # under load that response can take longer than a fixed 8s `expect`. Wait
    # for the app's own fetch activity to go quiet (state-driven), then assert.
    _nav.goto_settled(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    # M31 F4 L07a (A14): the prompt is its own section below the header, a code block.
    block = page.locator('.settings-item .editor-section:has(> .section-title:text-is("Prompt"))')
    expect(block).to_be_visible()
    expect(block.locator(".section-title")).to_have_text("Prompt")
    # The description text is the actual tool prompt (long-form). Spot
    # check it contains a substantive token from the description body
    # rather than asserting verbatim — keeps the test resilient to small
    # prose tweaks.
    text = (block.locator("pre.code-block").inner_text() or "").strip()
    assert len(text) > 20, f"prompt text too short or empty: {text!r}"


@pytest.mark.browser
def test_editor_connector_tool_shows_connectors_category(app_clean: str, page: Page) -> None:
    """Squawk 0032: the editor's category subtitle for a connector tool
    reads 'Connectors' (the category's display name, A13) — not 'unknown',
    which is what the pre-fix tools-editor.js TOOL_CATEGORIES mirror gap produced.
    """
    _nav.goto(page, app_clean, "settings/tools/send_to_platform_channel")
    expect(page.locator(".editor-title")).to_have_text("send_to_platform_channel", timeout=8000)
    expect(page.locator(".settings-item .editor-subtitle")).to_have_text("Connectors")


@pytest.mark.browser
def test_editor_renders_enabled_toggle_inline(app_clean: str, page: Page) -> None:
    """HAT inline fix #2: the `enabled` control is the library switch (the same look as
    the grid tile's), a `role=switch` named "Enabled for all agents" (M31 F4 L07a, DD8-4)."""
    _nav.goto(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    switch = page.get_by_role("switch", name="Enabled for all agents")
    expect(switch).to_be_checked()
    expect(switch).to_have_attribute("data-field", "enabled")
    expect(page.locator(".settings-item .ui-toggle .ui-toggle-track")).to_be_visible()


@pytest.mark.browser
def test_editor_renders_all_web_config_fields(app_clean: str, page: Page) -> None:
    """All 8 WebConfig fields render in admin mode — including the
    unmarked `redirect_cap`. Marker-gating only HIDES fields in agent
    mode (covered by studio test file). Pinned by design Reviewer.

    Exercised against `fetch_url` — `web_search` is no longer WebConfig-
    backed (M16 F08 leg 02 moved it to WebSearchConfig).
    """
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
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
    _nav.goto(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    for fname in _WEB_SEARCH_FIELDS:
        row = page.locator(f'.tools-editor-field[data-field-name="{fname}"]')
        # Field row present in the DOM (visibility gated by show_if below).
        expect(row).to_have_count(1)
    # The selector itself is always visible.
    expect(page.locator('.tools-editor-field[data-field-name="search_backend"]')).to_be_visible()


@pytest.mark.browser
def test_editor_field_descriptions_are_info_button_toggletips(app_clean: str, page: Page) -> None:
    """HAT inline fix #4, since M31 F4 L07a (ledger row 41): per-field descriptions are
    press-to-open toggletips on an info button beside the label, not hover `title`
    tooltips and not inline `<p class="field-description">` paragraphs.

    Spot-checks 3 WebConfig fields with known non-empty descriptions. Re-homed to
    `fetch_url` (WebConfig-backed).
    """
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)

    # Inline-paragraph form is gone — the regression check.
    expect(page.locator(".tools-editor-field p.field-description")).to_have_count(0)

    spot_check = ("timeout_seconds_max", "host_allowlist", "default_user_agent")
    for fname in spot_check:
        row = page.locator(f'.tools-editor-field[data-field-name="{fname}"]')
        icon = row.locator("button.field-info-icon")
        expect(icon).to_be_visible()
        assert not icon.get_attribute("title"), f"{fname}: no hover title any more"
        assert (icon.get_attribute("aria-label") or "").startswith("More information")
        icon.click()
        bubble = row.locator(".ui-info-bubble")
        expect(bubble).to_be_visible()
        # The live region is filled one tick after the bubble opens (announced once).
        expect(bubble).not_to_have_text("", timeout=3000)
        assert len((bubble.inner_text() or "").strip()) > 10, f"{fname}: empty description"
        icon.click()
        expect(bubble).to_be_hidden()


@pytest.mark.browser
def test_editor_save_disabled_until_dirty(app_clean: str, page: Page) -> None:
    """Save starts disabled; modifying a field enables it; saving flips
    it back to disabled (snapshot re-captured to clean state).

    Uses `web_search` / `searxng_base_url` (a plain WebSearchConfig string
    field). SearXNG must be selected first so the field is visible, then
    we type a URL into it.
    """
    _nav.goto(page, app_clean, "settings/tools/web_search")
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
    _nav.goto(page, app_clean, "settings/tools/web_search")
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
    _nav.goto(page, app_clean, "settings/tools/web_search")
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
def test_editor_model_validator_422_shows_at_editor_level(app_clean: str, page: Page) -> None:
    """Narrow `timeout_seconds_max` to 10 (< default 30) → 422 from the
    model-validator (loc `[]`, so it names no field) → the editor-level error
    with humanized text (no "Value error," prefix per HAT inline fix #6). Since
    M31 F4 L07b there is no banner and no heuristic row highlight (DD3, ledger
    row 11): a model-level error is shown once, at editor level.

    Re-homed to `fetch_url` — the `timeout_seconds_default <=
    timeout_seconds_max` validator lives on WebConfig, which `web_search`
    no longer uses (M16 F08 leg 02).
    """
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    page.locator('input[data-field="timeout_seconds_max"]').fill("10")
    page.locator(".save-btn").click()

    error = page.locator(".settings-item .editor-error")
    expect(error).to_contain_text("timeout_seconds_default", timeout=5000)
    text = error.inner_text()
    assert "Value error," not in text, f"error should strip 'Value error,' prefix — got: {text!r}"
    expect(page.locator(".editor-error-banner")).to_have_count(0)
    expect(page.locator(".settings-item [aria-invalid='true']")).to_have_count(0)


@pytest.mark.browser
def test_editor_field_error_names_its_field_and_clears_on_change(
    app_clean: str, page: Page
) -> None:
    """HAT inline fix #7, retargeted (M31 F4 L07b): a 422 whose `loc` names a field puts
    its humanised message on that field with `aria-invalid`; typing into the field
    clears it. (The row highlight class is retired.)"""
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    page.locator('input[data-field="redirect_cap"]').fill("-1")
    page.locator(".save-btn").click()
    field = page.locator('input[data-field="redirect_cap"]')
    expect(field).to_have_attribute("aria-invalid", "true", timeout=5000)
    row = page.locator('.tools-editor-field[data-field-name="redirect_cap"]')
    expect(row).to_contain_text("Must be 0 or more")
    expect(page.locator(".field-error-highlight")).to_have_count(0)
    field.fill("2")
    expect(field).not_to_have_attribute("aria-invalid", "true")
    expect(row).not_to_contain_text("Must be 0 or more")


@pytest.mark.browser
def test_editor_breadcrumb_dirty_gate(app_clean: str, page: Page) -> None:
    """Modify a field → click the breadcrumb's "Built-in tools" link →
    App.confirmDialog opens ([data-testid="confirm-dialog-overlay"], NOT
    native browser confirm). Cancel keeps the editor mounted; confirm closes
    it and the list stays (renamed from the Back-button test, M25 F3 leg 5b).
    """
    _nav.goto(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('[data-field="search_backend"]').select_option("searxng")

    _lists.close_item(page)
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=5000)

    # Cancel keeps the editor.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_have_text("web_search")

    # Re-trigger and confirm — closes the editor; the list stays.
    _lists.close_item(page)
    expect(overlay).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools")
    expect(_lists.list_row(page, "settings/tools", "web_search")).to_be_visible()
    _nav.expect_route(page, "settings/tools")


@pytest.mark.browser
def test_editor_settings_nav_dirty_gate(app_clean: str, page: Page) -> None:
    """Modify a field → click "Appearance" in the Settings nav →
    App.confirmDialog opens. Cancel keeps the editor; confirm navigates away.
    Same dialog as the breadcrumb link: both are routed leaves the router's
    leave guard (App.nav) asks about once.
    """
    _nav.goto(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('[data-field="search_backend"]').select_option("searxng")

    _lists.settings_nav_link(page, "appearance").click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=5000)

    # Cancel keeps the editor.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".editor-title")).to_have_text("web_search")

    # Re-trigger and confirm — navigates to the Appearance page.
    _lists.settings_nav_link(page, "appearance").click()
    expect(overlay).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".area-admin .page-title")).to_have_text("Appearance", timeout=5000)


@pytest.mark.browser
def test_test_button_only_for_testable_tools(app_clean: str, page: Page) -> None:
    """Test button mounts only for `web_search` and `fetch_url`. Other
    tools (e.g. `shell`) have no test surface — `test-tool-btn` not
    present.
    """
    _nav.goto(page, app_clean, "settings/tools/shell")
    expect(page.locator(".editor-title")).to_have_text("shell", timeout=8000)
    expect(page.locator('[data-testid="test-tool-btn"]')).to_have_count(0)

    _nav.goto(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    expect(page.locator('[data-testid="test-tool-btn"]')).to_be_visible()


@pytest.mark.browser
def test_test_button_input_pre_filled(app_clean: str, page: Page) -> None:
    """HAT addition: editable test-input pre-filled with the per-tool
    fixture default. web_search → "the one cli agent"; fetch_url →
    "https://example.com/".
    """
    _nav.goto(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    expect(page.locator("[data-test-param]")).to_have_value("the one cli agent")

    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    expect(page.locator("[data-test-param]")).to_have_value("https://example.com/")


@pytest.mark.browser
def test_test_button_click_fires_request(app_clean: str, page: Page) -> None:
    """Click sequence (per design Reviewer): button disables → terminal
    result appears → button re-enables. Don't assert on response content, only
    that a terminal state is reached (a real fetch fails or is refused under
    the test netns; either is a valid terminal state)."""
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    test_btn = page.locator('[data-testid="test-tool-btn"]')
    expect(test_btn).to_be_visible()

    test_btn.click()
    # Immediately disabled — proves the request fired.
    expect(test_btn).to_be_disabled()
    result = page.locator('[data-testid="test-result"]')
    expect(result).to_have_attribute(
        "data-state", re.compile("success|warning|danger"), timeout=15000
    )
    expect(test_btn).not_to_be_disabled()


# ── M31 F4 leg 07d: the Test section on the library (A15, A16) ───────────────

TEST_BTN = '[data-testid="test-tool-btn"]'
TEST_RESULT = '[data-testid="test-result"]'
TEST_DETAILS = '[data-testid="tool-test-details"]'
TEST_OUTPUT = '[data-testid="tool-test-output"]'


def _stub_test(page: Page, tool: str, status: int = 200, body: str = "", **payload) -> None:
    def handler(route):
        if status == 200 and not body:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
        else:
            route.fulfill(status=status, content_type="application/json", body=body)

    page.route(f"**/api/tools/configs/{tool}/test", handler)


def _payload(output: str, elapsed_ms: float, outcome: str) -> dict:
    return {"output": output, "elapsed_ms": elapsed_ms, "outcome": outcome}


def _run_test(page: Page) -> None:
    page.locator(TEST_BTN).click()
    expect(page.locator(TEST_BTN)).to_be_enabled(timeout=8000)


@pytest.mark.browser
def test_test_input_is_a_standard_field_with_the_button_on_its_line(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    field = page.locator("[data-test-param]")
    expect(field).to_have_value("https://example.com/")
    label = page.locator('label:has-text("URL")').first
    box_in, box_btn, box_label = (
        field.bounding_box(),
        page.locator(TEST_BTN).bounding_box(),
        label.bounding_box(),
    )
    assert box_in and box_btn and box_label
    assert 30 <= box_in["height"] <= 40, box_in  # the standard field height (about 34px)
    assert box_label["y"] + box_label["height"] <= box_in["y"] + 1, "the label is stacked above"
    mid = box_btn["y"] + box_btn["height"] / 2
    assert box_in["y"] <= mid <= box_in["y"] + box_in["height"], "the button is on the input's line"
    assert box_btn["x"] >= box_in["x"] + box_in["width"] - 1


@pytest.mark.browser
def test_each_outcome_has_a_fixed_headline_and_one_status_mark(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    result = page.locator(TEST_RESULT)
    timeout = "[error] Request timed out after 30s"
    blocked = "[error] [constraint] host 'example.com' is in host_denylist"
    cases = [
        (_payload("page body", 12.4, "ok"), "Returned a result (12 ms)", "success"),
        (_payload(blocked, 3.0, "blocked"), "Blocked by this tool's settings (3 ms)", "warning"),
        (_payload(timeout, 30001.0, "failed"), "Request failed", "danger"),
    ]  # fmt: skip
    for payload, headline, state in cases:
        page.unroute("**/api/tools/configs/fetch_url/test")
        _stub_test(page, "fetch_url", **payload)
        _run_test(page)
        expect(result).to_have_attribute("data-state", state)
        expect(result).to_have_text(headline)
        expect(result.locator(".indicator-led")).to_have_count(1)
        assert "\u2713" not in result.inner_text() and "\u2717" not in result.inner_text()
        assert result.get_attribute("aria-live") == "polite"  # announced politely, once


@pytest.mark.browser
def test_a_test_produces_exactly_one_live_announcement(app_clean: str, page: Page) -> None:
    """Flight review (a11y): the result's inner statuses are `live: off`, so one Test changes
    exactly one live region (the polite result container), never several."""
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    _stub_test(page, "fetch_url", **_payload("page body", 12.4, "ok"))
    page.evaluate(
        """() => {
          window.__liveHits = new Set();
          const effective = (node) => {
            for (let n = node.nodeType === 1 ? node : node.parentElement; n; n = n.parentElement) {
              const v = n.getAttribute('aria-live');
              if (v !== null) return v === 'off' ? null : n;
              const r = n.getAttribute('role');
              if (r === 'status' || r === 'alert') return n;
            }
            return null;
          };
          new MutationObserver((muts) => {
            for (const m of muts) {
              const r = effective(m.target);
              if (r) window.__liveHits.add(r.getAttribute('data-testid') || r.className);
            }
          }).observe(document.body, {subtree: true, childList: true, characterData: true});
        }"""
    )
    _run_test(page)
    expect(page.locator(TEST_RESULT)).to_have_attribute("data-state", "success")
    page.wait_for_timeout(300)
    hits = page.evaluate("Array.from(window.__liveHits)")
    assert hits == ["test-result"], hits


@pytest.mark.browser
def test_output_is_collapsed_opens_by_keyboard_and_shows_the_head(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    long_output = "HEADLINE" + "x" * 3000 + "TAILEND"
    _stub_test(page, "fetch_url", output=long_output, elapsed_ms=5.0, outcome="ok")
    _run_test(page)
    details = page.locator(TEST_DETAILS)
    expect(details).to_have_count(1)
    assert details.evaluate("e => e.open") is False
    expect(page.locator(TEST_OUTPUT)).to_be_hidden()
    summary = details.locator("summary")
    expect(summary).to_have_text("Technical details")
    summary.focus()
    page.keyboard.press("Enter")
    assert details.evaluate("e => e.open") is True
    text = page.locator(TEST_OUTPUT).inner_text()
    assert text.startswith("HEADLINE"), text[:20]
    assert "TAILEND" not in text
    assert text.rstrip().endswith("…"), text[-10:]
    assert len(text) < 2200


@pytest.mark.browser
def test_a_short_output_has_no_truncation_marker_and_an_empty_one_no_details(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    _stub_test(page, "fetch_url", output="short result", elapsed_ms=1.0, outcome="ok")
    _run_test(page)
    page.locator(TEST_DETAILS).locator("summary").click()
    assert page.locator(TEST_OUTPUT).inner_text() == "short result"
    page.unroute("**/api/tools/configs/fetch_url/test")
    _stub_test(page, "fetch_url", output="", elapsed_ms=1.0, outcome="ok")
    _run_test(page)
    expect(page.locator(TEST_RESULT)).to_have_attribute("data-state", "success")
    expect(page.locator(TEST_DETAILS)).to_have_count(0)


@pytest.mark.browser
def test_an_http_error_reads_request_failed_with_the_reason_under_details(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    _stub_test(page, "fetch_url", status=400, body='{"detail": "Tool x does not support testing"}')
    _run_test(page)
    expect(page.locator(TEST_RESULT)).to_have_text("Request failed")
    expect(page.locator(TEST_RESULT)).to_have_attribute("data-state", "danger")
    page.locator(TEST_DETAILS).locator("summary").click()
    expect(page.locator(TEST_OUTPUT)).to_contain_text("does not support testing")
    # A non-JSON 500 shows the status line instead.
    page.unroute("**/api/tools/configs/fetch_url/test")

    def html_500(route):
        route.fulfill(status=500, content_type="text/html", body="<html>oops</html>")

    page.route("**/api/tools/configs/fetch_url/test", html_500)
    _run_test(page)
    expect(page.locator(TEST_RESULT)).to_have_text("Request failed")
    page.locator(TEST_DETAILS).locator("summary").click()
    expect(page.locator(TEST_OUTPUT)).to_contain_text("500")


@pytest.mark.browser
def test_a_stale_test_result_writes_nothing_after_the_tool_changed(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    held: list = []

    def hold(route):
        held.append(route)

    page.route("**/api/tools/configs/fetch_url/test", hold)
    page.locator(TEST_BTN).click()
    for _ in range(200):
        if held:
            break
        page.wait_for_timeout(25)
    assert len(held) == 1
    _lists.item_link(page, "settings/tools", "web_search").click()
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    held[0].fulfill(
        status=200,
        content_type="application/json",
        body='{"output": "late", "elapsed_ms": 1, "outcome": "ok"}',
    )
    page.wait_for_timeout(200)  # the late response has been delivered to the page
    expect(page.locator(TEST_BTN)).to_be_enabled()
    expect(page.locator(TEST_RESULT)).to_have_text("")
    expect(page.locator(TEST_DETAILS)).to_have_count(0)


@pytest.mark.browser
def test_the_test_says_it_uses_the_saved_settings_only_while_dirty(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    hint = page.locator('[data-testid="test-saved-hint"]')
    expect(hint).to_be_hidden()
    page.locator('input[data-field="default_user_agent"]').fill("changed")
    expect(hint).to_be_visible()
    expect(hint).to_have_text("Tests the saved settings.")
    page.locator('[data-testid="cancel-tool-btn"]').click()
    expect(hint).to_be_hidden()


@pytest.mark.browser
def test_test_result_is_kept_on_save_and_cleared_on_a_cancel_that_changes_a_value(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    _stub_test(page, "fetch_url", output="fine", elapsed_ms=2.0, outcome="ok")
    _run_test(page)
    result = page.locator(TEST_RESULT)
    expect(result).to_have_text("Returned a result (2 ms)")
    page.locator('input[data-field="default_user_agent"]').fill("kept-by-save")
    page.locator('[data-testid="save-tool-btn"]').click()
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_disabled(timeout=5000)
    expect(result).to_have_text("Returned a result (2 ms)")  # Save keeps it
    page.locator('input[data-field="default_user_agent"]').fill("will-be-cancelled")
    page.locator('[data-testid="cancel-tool-btn"]').click()
    expect(result).to_have_text("")  # Cancel changed a value: the result no longer applies


# ── M16 F08 leg 04: masked secret eye-toggle + show_if visibility ────────


@pytest.mark.browser
def test_web_search_secret_field_masked_with_eye_toggle(app_clean: str, page: Page) -> None:
    """A `ui_hint:"password"` field (WebSearchConfig's `brave_api_key`)
    renders as `<input type="password">` inside an `.api-key-wrap` shell
    with an `.api-key-eye` button. The eye button toggles the input
    between password/text and swaps its aria-label. Ported from the
    provider-editor eye-toggle pattern.
    """
    _nav.goto(page, app_clean, "settings/tools/web_search")
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
    _nav.goto(page, app_clean, "settings/tools/web_search")
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
    _nav.goto(page, app_clean, "settings/tools/web_search")
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
    _nav.goto(page, app_clean, "settings/tools/web_search")
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


def _stored_tool_config(base_url: str, tool: str) -> dict:
    """GET /api/tools/configs/{tool} with the test instance's credential."""
    import httpx
    from browser._credential_registry import auth_headers_for

    r = httpx.get(
        f"{base_url}/api/tools/configs/{tool}",
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code == 200, f"GET {tool} failed: {r.status_code} {r.text}"
    return r.json()


def _denylist_save_round_trip(
    page: Page, base_url: str, tool: str, field: str, expected: list[str], toggle: str
) -> None:
    """Squawk 0248: a never-saved tool shows the built-in denylist as chips,
    and a Save that changes only another field stores those defaults, not `[]`."""
    assert _stored_tool_config(base_url, tool)["config"] == {}
    _nav.goto(page, base_url, f"settings/tools/{tool}")
    expect(page.locator(".editor-title")).to_have_text(tool, timeout=8000)

    chips = page.locator(f'[data-field="{field}"] .chip')
    expect(chips).to_have_count(len(expected))
    shown = page.evaluate(
        """(field) => App.toolConfigFields.readValue(
            document.querySelector('[data-field="' + field + '"]'))""",
        field,
    )
    assert shown == expected

    save_btn = page.locator(".save-btn")
    expect(save_btn).to_be_disabled()
    page.locator(f'input[data-field="{toggle}"]').check()
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(save_btn).to_be_disabled(timeout=5000)

    config = _stored_tool_config(base_url, tool)["config"]
    assert config[toggle] is True
    assert config[field] == expected, f"{tool}.{field} stored {config[field]!r}"


@pytest.mark.browser
def test_unsaved_filesystem_tool_shows_and_keeps_default_path_denylist(
    app_clean: str, page: Page
) -> None:
    # read_file, not move_file: move_file no longer shows allow_binary_files (05a, B6).
    from the_one.tools.filesystem import DEFAULT_PATH_DENYLIST

    _denylist_save_round_trip(
        page,
        app_clean,
        "read_file",
        "path_denylist",
        list(DEFAULT_PATH_DENYLIST),
        "allow_binary_files",
    )


@pytest.mark.browser
def test_unsaved_execution_tool_shows_and_keeps_default_command_denylist(
    app_clean: str, page: Page
) -> None:
    from the_one.tools.execution import DEFAULT_COMMAND_DENYLIST

    _denylist_save_round_trip(
        page,
        app_clean,
        "shell",
        "command_denylist",
        list(DEFAULT_COMMAND_DENYLIST),
        "sandbox_network_allowed",
    )


@pytest.mark.browser
@pytest.mark.parametrize("width", [1280, 1024])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_test_button_is_vertically_centred_on_its_input(
    app_clean: str, page: Page, width: int, theme: str
) -> None:
    """HAT step 5 (ledger 50): the Test connection button sat ~15px below its
    input. Their vertical centres agree within 1px at both widths and themes."""
    page.set_viewport_size({"width": width, "height": 900})
    _nav.goto(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    inp = page.locator("input[data-test-param]")
    btn = page.locator(TEST_BTN)
    expect(btn).to_be_visible()
    inp.scroll_into_view_if_needed()
    ib, bb = inp.bounding_box(), btn.bounding_box()
    assert ib is not None and bb is not None
    ic = ib["y"] + ib["height"] / 2
    bc = bb["y"] + bb["height"] / 2
    assert abs(ic - bc) <= 1, (ib, bb)
