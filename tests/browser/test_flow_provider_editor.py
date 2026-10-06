"""Provider editor shape + behavior tests for F6 leg 03.

Covers the canonical editor scaffold (header / form-actions / sections),
disabled-SSoT for Save/Cancel, dirty tracking, Cancel revert vs navigate,
Danger Zone presence, Test button gating, agent-usage hard-block, and the
api-key eye toggle.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _seed_anthropic_provider(
    base_url: str, *, name: str = "Claude", thinking_enabled: bool = False
) -> str:
    """POST an anthropic provider via /api/providers and return its id.

    Used by the Extended-thinking toggle tests (F10-06) that need an existing
    anthropic provider in edit mode (Save starts disabled → toggling the
    checkbox must flip it enabled, guarding the checkbox-aware dirty patch)."""
    payload = {
        "name": name,
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-ant-seedkey1234",
        "config": {"thinking_enabled": thinking_enabled},
    }
    r = httpx.post(
        f"{base_url}/api/providers", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 201, f"seed_anthropic_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _seed_openai_compatible_provider(
    base_url: str,
    *,
    name: str = "compat-orig",
    provider_base_url: str = "https://orig.example.com/v1",
) -> str:
    """POST an openai-compatible provider (base_url + api_key both editable in
    the UI) and return its id. Used by the H1/subtitle re-render regression
    (F7-01): openai-compatible shows the Base URL field so a single save can
    edit BOTH the Name (drives the H1) and the Base URL (drives the subtitle)."""
    payload = {
        "name": name,
        "type": "openai-compatible",
        "base_url": provider_base_url,
        "api_key": "sk-compat-seedkey1234",
    }
    r = httpx.post(
        f"{base_url}/api/providers", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 201, f"seed_openai_compatible_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


# ── Header / scaffold ────────────────────────────────────────────────────


@pytest.mark.browser
def test_editor_renders_canonical_header_in_edit_mode(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".area-admin .editor-header")).to_be_visible(timeout=8000)
    expect(page.locator(".editor-title")).to_have_text("mock")
    # Subtitle includes provider type. base_url for mock is empty string so we
    # only assert the type token is present.
    expect(page.locator(".editor-subtitle")).to_contain_text("mock")


@pytest.mark.browser
def test_editor_renders_canonical_header_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    # Create mode omits the subtitle paragraph entirely.
    expect(page.locator(".editor-subtitle")).to_have_count(0)


@pytest.mark.browser
def test_header_rerenders_title_and_subtitle_on_edit_save(app_clean: str, page: Page) -> None:
    """F7-01 regression: on an edit→edit save the editor stays mounted, so the
    display-only header (H1 + `type · base_url` subtitle) must be re-rendered
    from the saved provider. Editing BOTH Name and Base URL and saving must
    update the H1 AND the subtitle in place — no reload. Guards the pre-existing
    header-desync fix (both fields are editable; a Name-only re-render would
    leave the subtitle stale by the identical mechanism)."""
    provider_id = _seed_openai_compatible_provider(app_clean)
    _nav.goto(page, app_clean, f"settings/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("compat-orig", timeout=8000)
    expect(page.locator(".editor-subtitle")).to_contain_text("orig.example.com")
    # Edit both the Name (drives the H1) and the Base URL (drives the subtitle).
    page.locator("#pf-name").fill("compat-edited")
    page.locator("#pf-base-url").fill("https://edited.example.com/v1")
    save_btn = page.locator(".save-btn")
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    # No reload: the header must reflect the saved values in place.
    expect(page.locator(".editor-title")).to_have_text("compat-edited")
    expect(page.locator(".editor-subtitle")).to_contain_text("edited.example.com")
    # And the old values must be gone (catches a stale-node no-op).
    expect(page.locator(".editor-title")).not_to_have_text("compat-orig")
    expect(page.locator(".editor-subtitle")).not_to_contain_text("orig.example.com")


@pytest.mark.browser
def test_editor_action_cluster_order_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    # Back is retired (M25 F3 L5b): the cluster opens with the unsaved caption.
    expect(page.locator(".form-actions .cancel-btn")).to_be_visible(timeout=8000)
    expect(page.locator(".form-actions .back-btn")).to_have_count(0)
    first = page.locator('.form-actions > [data-testid="editor-unsaved"]:first-child')
    expect(first).to_have_count(1)
    expect(page.locator(".form-actions .save-btn")).to_be_visible()
    expect(page.locator(".form-actions .test-provider-btn")).to_be_visible()
    expect(page.locator(".form-actions .editor-error")).to_have_count(1)


@pytest.mark.browser
def test_editor_action_cluster_order_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".form-actions .cancel-btn")).to_be_visible(timeout=8000)
    expect(page.locator(".form-actions .back-btn")).to_have_count(0)
    expect(page.locator(".form-actions .save-btn")).to_be_visible()
    # No Test button in create mode.
    expect(page.locator(".form-actions .test-provider-btn")).to_have_count(0)
    expect(page.locator(".form-actions .editor-error")).to_have_count(1)


# ── Save / Cancel disabled-SSoT ──────────────────────────────────────────


@pytest.mark.browser
def test_save_and_cancel_disabled_when_clean(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_save_and_cancel_enabled_when_dirty(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    page.locator("#pf-name").fill("mock-edited")
    expect(page.locator(".save-btn")).not_to_be_disabled()
    expect(page.locator(".cancel-btn")).not_to_be_disabled()


@pytest.mark.browser
def test_cancel_reverts_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    page.locator("#pf-name").fill("mock-edited")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator("#pf-name")).to_have_value("mock")
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_create_cancel_navigates_to_grid_when_dirty(app_clean: str, page: Page) -> None:
    """Cancel on a dirty create form discards it and returns to the page root
    (replace, no dialog); with no row to return to, focus goes to "Add
    provider" (M25 F3 L5b, DD8)."""
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-name").fill("typed-name")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    expect(page.locator(".area-admin .page-title")).to_have_text("Providers")
    _nav.expect_route(page, "settings/providers")
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_focused()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)


@pytest.mark.browser
def test_header_has_breadcrumb_and_no_back(app_with_provider: SeededApp, page: Page) -> None:
    """Replaces the Back-always-enabled test (M25 F3 L5b retired Back): the
    header's breadcrumb reads "Settings / Providers", its "Providers" segment
    links to the page root, and no Back control exists."""
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    crumb = page.locator(".editor-header-text > .editor-breadcrumb:first-child")
    expect(crumb).to_have_text("Settings / Providers", timeout=8000)
    link = crumb.locator('[data-testid="editor-breadcrumb-link"]')
    expect(link).to_have_text("Providers")
    expect(link).to_have_attribute("href", _nav.href("settings/providers"))
    expect(page.locator(".back-btn")).to_have_count(0)
    # An h2 since the flight-end review: the Settings page header owns the one h1.
    expect(page.locator("h2.editor-title")).to_have_attribute("tabindex", "-1")
    expect(page.locator(".content-panel.active h1")).to_have_count(1)


# ── Danger Zone ──────────────────────────────────────────────────────────


@pytest.mark.browser
def test_danger_zone_renders_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    expect(page.locator(".section-title.danger-zone-title")).to_have_text("Danger Zone")
    expect(page.locator('[data-testid="delete-provider-btn"]')).to_be_visible()


@pytest.mark.browser
def test_danger_zone_omitted_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    expect(page.locator(".editor-section.danger-zone")).to_have_count(0)


@pytest.mark.browser
def test_delete_two_step_confirm(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    # First click arms the button. No agents use this provider, so no
    # hard-block.
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))
    # Second click actually deletes: back to the page root; the table had one
    # row, so focus goes to "Add provider" (M25 F3 L5b, DD8).
    delete_btn.click()
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "settings/providers")
    expect(page.locator('[data-testid="providers-empty"]')).to_be_visible()
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_focused()


@pytest.mark.browser
def test_delete_blocked_when_provider_in_use(app_with_agent: SeededApp, page: Page) -> None:
    """Provider with an agent attached must hard-block (no confirm flow).

    Hard-block message lives in a sibling banner below the button, NOT
    in the button text — keeps the button compact when agent-name lists
    are long. Button stays at "Delete Provider" but is disabled. F6 HAT
    refinement.
    """
    _nav.goto(
        page, app_with_agent.base_url, f"settings/providers/{_nav.seg(app_with_agent.provider_id)}"
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    delete_btn.click()
    # Hard-block message banner reveals + names the blocking agent.
    blocked_msg = page.locator('[data-testid="delete-blocked-message"]')
    expect(blocked_msg).to_be_visible(timeout=5000)
    expect(blocked_msg).to_contain_text("Used by:")
    assert app_with_agent.agent_name is not None
    expect(blocked_msg).to_contain_text(app_with_agent.agent_name)
    # Button itself stays at "Delete Provider" but is disabled.
    expect(delete_btn).to_be_disabled()
    expect(delete_btn).to_contain_text("Delete Provider")


@pytest.mark.browser
def test_delete_confirm_lapse_is_visually_distinct(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the Danger Zone
    provider-delete confirm — the no-agent-usage arming path
    (`provider-editor.js:946`) — is distinguishable on screen from one
    that was never armed, past the real 3s `revertMs`."""
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_contain_text("Delete Provider")
    # Never committed: still on the editor, provider still there.
    _nav.expect_route(page, f"settings/providers/{_nav.seg(app_with_provider.provider_id)}")


@pytest.mark.browser
def test_delete_confirm_lapse_via_fail_open_path_is_visually_distinct(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Same as above, but reached via the network-failure fail-open arming
    path (`provider-editor.js:951`) — the agent-usage pre-gate fetch
    itself fails, so the button arms anyway. Both arming paths feed the
    same shared `App.confirmDelete`, so the lapse cue is identical."""
    page.route(
        f"**/api/providers/{app_with_provider.provider_id}/agents",
        lambda route: route.abort("failed"),
    )
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE), timeout=5000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_contain_text("Delete Provider")


# ── Test button ──────────────────────────────────────────────────────────


@pytest.mark.browser
def test_test_button_omitted_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    expect(page.locator('[data-testid="test-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_test_button_visible_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_test_result_uses_canonical_class(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    test_btn = page.locator('[data-testid="test-connection-btn"]')
    expect(test_btn).to_be_visible(timeout=8000)
    test_btn.click()
    # Mock provider returns ok; result rendered as .test-result-ok inside .test-result.
    expect(page.locator(".test-result .test-result-ok")).to_be_visible(timeout=5000)


# ── API-key eye toggle ──────────────────────────────────────────────────


@pytest.mark.browser
def test_api_key_eye_toggle(app_clean: str, page: Page) -> None:
    """Open the create editor, switch type to openai (api-key field shown), toggle eye."""
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("openai")
    api_key = page.locator("#pf-api-key")
    expect(api_key).to_have_attribute("type", "password")
    eye = page.locator(".api-key-eye")
    eye.click()
    expect(api_key).to_have_attribute("type", "text")
    eye.click()
    expect(api_key).to_have_attribute("type", "password")


# ── Context Window (num_ctx) field — F09-05 polish ───────────────────────


@pytest.mark.browser
def test_num_ctx_field_shown_for_ollama_with_default_prefill(app_clean: str, page: Page) -> None:
    """Selecting the ollama type reveals a required Context Window field
    pre-filled with the default window (32768)."""
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("ollama")
    num_ctx = page.locator("#pf-num-ctx")
    expect(num_ctx).to_be_visible()
    expect(num_ctx).to_have_value("32768")
    expect(num_ctx).to_have_attribute("type", "number")
    expect(num_ctx).to_have_attribute("required", "")
    # Canonical label text (no longer the parenthetical num_ctx form).
    expect(page.locator('label[for="pf-num-ctx"]')).to_have_text("Context Window")


@pytest.mark.browser
def test_num_ctx_field_hidden_for_non_ollama(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("openai")
    expect(page.locator(".admin-pf-num-ctx")).to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_num_ctx_info_icon_tooltip(app_clean: str, page: Page) -> None:
    """The description is a focusable info-icon button (title= tooltip) with a
    visually-hidden span wired via aria-describedby — mirrors the
    field-info-icon pattern used by the tools editor."""
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("ollama")
    desc = (
        "A larger window allows longer conversations but will slow down on "
        "partial-GPU setups because fewer layers fit in VRAM"
    )
    icon = page.locator(".admin-pf-num-ctx .field-info-icon")
    expect(icon).to_be_visible()
    expect(icon).to_have_attribute("title", desc)
    expect(icon).to_have_attribute("aria-describedby", "pf-num-ctx-desc")
    expect(page.locator("#pf-num-ctx-desc")).to_have_text(desc)
    expect(page.locator("#pf-num-ctx")).to_have_attribute("aria-describedby", "pf-num-ctx-desc")


# ── Extended thinking (config.thinking_enabled) toggle — F10-06 ──────────


@pytest.mark.browser
def test_thinking_toggle_shown_for_anthropic_unchecked_by_default(
    app_clean: str, page: Page
) -> None:
    """Selecting the anthropic type reveals an Extended-thinking checkbox,
    unchecked by default (off-by-default: operator opts in)."""
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic")
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("type", "checkbox")
    expect(toggle).not_to_be_checked()
    expect(page.locator('label[for="pf-thinking-enabled"]')).to_have_text("Extended thinking")


@pytest.mark.browser
def test_thinking_toggle_hidden_for_non_anthropic(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("openai")
    expect(page.locator(".admin-pf-thinking-enabled")).to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_thinking_toggle_info_icon_tooltip(app_clean: str, page: Page) -> None:
    """The description is a focusable info-icon button (title= tooltip) with a
    visually-hidden span wired via aria-describedby — mirrors the num_ctx
    field-info-icon a11y idiom."""
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic")
    desc = (
        "When on, a model reasons step-by-step before answering "
        "(adaptive thinking). Requires Claude Sonnet 4.6 or newer."
    )
    icon = page.locator(".admin-pf-thinking-enabled .field-info-icon")
    expect(icon).to_be_visible()
    expect(icon).to_have_attribute("title", desc)
    expect(icon).to_have_attribute("aria-describedby", "pf-thinking-enabled-desc")
    expect(page.locator("#pf-thinking-enabled-desc")).to_have_text(desc)
    expect(page.locator("#pf-thinking-enabled")).to_have_attribute(
        "aria-describedby", "pf-thinking-enabled-desc"
    )


@pytest.mark.browser
def test_thinking_toggle_flips_save_from_disabled_to_enabled(app_clean: str, page: Page) -> None:
    """Toggling the checkbox on an existing (clean) anthropic provider marks
    the form dirty (Save flips from disabled → enabled). Directly guards the
    [high] checkbox-aware getFormSnapshot patch — fails loudly if the snapshot
    ignores .checked."""
    provider_id = _seed_anthropic_provider(app_clean, thinking_enabled=False)
    _nav.goto(page, app_clean, f"settings/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).to_be_visible()
    expect(toggle).not_to_be_checked()
    # Clean form → Save disabled.
    expect(page.locator(".save-btn")).to_be_disabled()
    toggle.check()
    # Checkbox toggle must mark the form dirty.
    expect(page.locator(".save-btn")).not_to_be_disabled()
    expect(page.locator(".cancel-btn")).not_to_be_disabled()


@pytest.mark.browser
def test_thinking_toggle_saves_and_reopens_checked(app_clean: str, page: Page) -> None:
    """Toggle on + Save + reload → the checkbox re-renders checked (edit-load
    reflects the stored config.thinking_enabled)."""
    provider_id = _seed_anthropic_provider(app_clean, thinking_enabled=False)
    _nav.goto(page, app_clean, f"settings/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).not_to_be_checked()
    toggle.check()
    save_btn = page.locator(".save-btn")
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    # Reload the editor from scratch → the stored value must round-trip.
    _nav.goto(page, app_clean, f"settings/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    expect(page.locator("#pf-thinking-enabled")).to_be_checked()


@pytest.mark.browser
def test_thinking_toggle_cancel_reverts(app_clean: str, page: Page) -> None:
    """Cancel after toggling reverts the checkbox to its snapshot state
    (checkbox-aware Cancel-revert patch)."""
    provider_id = _seed_anthropic_provider(app_clean, thinking_enabled=False)
    _nav.goto(page, app_clean, f"settings/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).not_to_be_checked()
    toggle.check()
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator("#pf-thinking-enabled")).not_to_be_checked()
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()
