"""Provider editor shape + behavior tests for F6 leg 03.

Covers the canonical editor scaffold (header / form-actions / sections),
disabled-SSoT for Save/Cancel, dirty tracking, Cancel revert vs navigate,
Danger Zone presence, Test button gating, agent-usage hard-block, and the
api-key eye toggle.
"""

from __future__ import annotations

import re

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


# ── Header / scaffold ────────────────────────────────────────────────────


@pytest.mark.browser
def test_editor_renders_canonical_header_in_edit_mode(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".area-admin .editor-header")).to_be_visible(timeout=8000)
    expect(page.locator(".editor-title")).to_have_text("mock")
    # Subtitle includes provider type. base_url for mock is empty string so we
    # only assert the type token is present.
    expect(page.locator(".editor-subtitle")).to_contain_text("mock")


@pytest.mark.browser
def test_editor_renders_canonical_header_in_create_mode(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    # Create mode omits the subtitle paragraph entirely.
    expect(page.locator(".editor-subtitle")).to_have_count(0)


@pytest.mark.browser
def test_editor_action_cluster_order_in_edit_mode(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".form-actions .back-btn")).to_be_visible(timeout=8000)
    expect(page.locator(".form-actions .cancel-btn")).to_be_visible()
    expect(page.locator(".form-actions .save-btn")).to_be_visible()
    expect(page.locator(".form-actions .test-provider-btn")).to_be_visible()
    expect(page.locator(".form-actions .editor-error")).to_have_count(1)


@pytest.mark.browser
def test_editor_action_cluster_order_in_create_mode(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".form-actions .back-btn")).to_be_visible(timeout=8000)
    expect(page.locator(".form-actions .cancel-btn")).to_be_visible()
    expect(page.locator(".form-actions .save-btn")).to_be_visible()
    # No Test button in create mode.
    expect(page.locator(".form-actions .test-provider-btn")).to_have_count(0)
    expect(page.locator(".form-actions .editor-error")).to_have_count(1)


# ── Save / Cancel disabled-SSoT ──────────────────────────────────────────


@pytest.mark.browser
def test_save_and_cancel_disabled_when_clean(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_save_and_cancel_enabled_when_dirty(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    page.locator("#pf-name").fill("mock-edited")
    expect(page.locator(".save-btn")).not_to_be_disabled()
    expect(page.locator(".cancel-btn")).not_to_be_disabled()


@pytest.mark.browser
def test_cancel_reverts_in_edit_mode(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    page.locator("#pf-name").fill("mock-edited")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator("#pf-name")).to_have_value("mock")
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_create_cancel_navigates_to_grid_when_dirty(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-name").fill("typed-name")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_back_button_always_enabled(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".back-btn")).to_be_visible(timeout=8000)
    expect(page.locator(".back-btn")).not_to_be_disabled()


# ── Danger Zone ──────────────────────────────────────────────────────────


@pytest.mark.browser
def test_danger_zone_renders_in_edit_mode(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    expect(page.locator(".section-title.danger-zone-title")).to_have_text("Danger Zone")
    expect(page.locator('[data-testid="delete-provider-btn"]')).to_be_visible()


@pytest.mark.browser
def test_danger_zone_omitted_in_create_mode(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    expect(page.locator(".editor-section.danger-zone")).to_have_count(0)


@pytest.mark.browser
def test_delete_two_step_confirm(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    # First click arms the button. No agents use this provider, so no
    # hard-block.
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))
    # Second click actually deletes.
    delete_btn.click()
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_delete_blocked_when_provider_in_use(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Provider with an agent attached must hard-block (no confirm flow)."""
    page.goto(f"{app_with_agent.base_url}#admin/providers/{app_with_agent.provider_id}")
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    delete_btn.click()
    # Hard-block label includes the agent name.
    expect(delete_btn).to_contain_text("Used by:", timeout=5000)
    assert app_with_agent.agent_name is not None
    expect(delete_btn).to_contain_text(app_with_agent.agent_name)
    expect(delete_btn).to_be_disabled()


# ── Test button ──────────────────────────────────────────────────────────


@pytest.mark.browser
def test_test_button_omitted_in_create_mode(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    expect(page.locator('[data-testid="test-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_test_button_visible_in_edit_mode(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_test_result_uses_canonical_class(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    test_btn = page.locator('[data-testid="test-connection-btn"]')
    expect(test_btn).to_be_visible(timeout=8000)
    test_btn.click()
    # Mock provider returns ok; result rendered as .test-result-ok inside .test-result.
    expect(page.locator(".test-result .test-result-ok")).to_be_visible(timeout=5000)


# ── API-key eye toggle ──────────────────────────────────────────────────


@pytest.mark.browser
def test_api_key_eye_toggle(app_clean: str, page: Page) -> None:
    """Open the create editor, switch type to openai (api-key field shown), toggle eye."""
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("openai")
    api_key = page.locator("#pf-api-key")
    expect(api_key).to_have_attribute("type", "password")
    eye = page.locator(".api-key-eye")
    eye.click()
    expect(api_key).to_have_attribute("type", "text")
    eye.click()
    expect(api_key).to_have_attribute("type", "password")
