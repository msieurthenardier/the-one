"""Browser flow: Studio model picker for OpenRouter (datalist combobox).

Covers:
- Selecting an openrouter provider renders an <input> + <datalist>, not a
  <select>, and the datalist populates with the seeded model entries.
- A model whose supported_parameters lacks 'tools' shows the .cap-chip-no-tools
  chip in the capabilities panel.
- A model with empty supported_parameters renders no chip (fail-open).
- Switching provider types (ollama → openrouter → ollama → openrouter) leaves
  exactly one #studio-model element in the DOM at each step.

The synthetic model list is injected via the THE_ONE_OPENROUTER_TEST_MODELS_JSON
env var so no live OpenRouter network call is needed.  See conftest.py for the
``app_with_openrouter_models`` and ``app_with_two_providers`` fixtures.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_openrouter_picker_renders_datalist(
    app_with_openrouter_models,
    page: Page,
) -> None:
    """Selecting an openrouter provider renders <input list=…> + <datalist>
    (not <select>), and the datalist is populated with the seeded models."""
    base_url = app_with_openrouter_models.base_url
    provider_id = app_with_openrouter_models.provider_id

    page.goto(f"{base_url}#studio")
    page.locator('[data-testid="new-agent-btn-empty"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)

    page.locator("#studio-provider").select_option(provider_id)

    # Datalist should populate (the fetch hits /api/providers/{id}/models)
    expect(page.locator("#studio-model-list option")).to_have_count(
        3,
        timeout=8000,  # 3 seeded models
    )

    # Element must be <input>, NOT <select>
    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "INPUT", f"expected INPUT element, got {tag!r}"

    # Datalist must contain the seeded model ids
    values = page.eval_on_selector_all("#studio-model-list option", "els => els.map(e => e.value)")
    assert "anthropic/claude-3.5-sonnet" in values
    assert "no-tools-model" in values
    assert "empty-caps-model" in values


@pytest.mark.browser
def test_studio_openrouter_no_tools_chip(
    app_with_openrouter_models,
    page: Page,
) -> None:
    """Selecting a model without 'tools' in supported_parameters renders the
    .cap-chip-no-tools chip in the capabilities panel."""
    base_url = app_with_openrouter_models.base_url
    provider_id = app_with_openrouter_models.provider_id

    page.goto(f"{base_url}#studio")
    page.locator('[data-testid="new-agent-btn-empty"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model-list option")).to_have_count(3, timeout=8000)

    # Select the model that has max_tokens but NOT tools.
    page.locator("#studio-model").fill("no-tools-model")
    page.locator("#studio-model").dispatch_event("change")

    # The capabilities panel should render a "no tools" chip.
    chip = page.locator(".cap-chip-no-tools")
    expect(chip).to_be_visible(timeout=3000)


@pytest.mark.browser
def test_studio_openrouter_tools_model_no_no_tools_chip(
    app_with_openrouter_models,
    page: Page,
) -> None:
    """Selecting a model that HAS 'tools' in supported_parameters does NOT
    render the .cap-chip-no-tools chip."""
    base_url = app_with_openrouter_models.base_url
    provider_id = app_with_openrouter_models.provider_id

    page.goto(f"{base_url}#studio")
    page.locator('[data-testid="new-agent-btn-empty"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model-list option")).to_have_count(3, timeout=8000)

    # This model has ["tools", "reasoning"] — no "no tools" chip expected.
    page.locator("#studio-model").fill("anthropic/claude-3.5-sonnet")
    page.locator("#studio-model").dispatch_event("change")

    # Auto-retrying assertion: chip must be absent (or disappear within timeout).
    expect(page.locator(".cap-chip-no-tools")).to_have_count(0, timeout=2000)


@pytest.mark.browser
def test_studio_openrouter_empty_caps_no_chip(
    app_with_openrouter_models,
    page: Page,
) -> None:
    """A model with empty supported_parameters renders no capability chip
    (fail-open: unknown capabilities → no chip, not 'no tools')."""
    base_url = app_with_openrouter_models.base_url
    provider_id = app_with_openrouter_models.provider_id

    page.goto(f"{base_url}#studio")
    page.locator('[data-testid="new-agent-btn-empty"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model-list option")).to_have_count(3, timeout=8000)

    page.locator("#studio-model").fill("empty-caps-model")
    page.locator("#studio-model").dispatch_event("change")

    # Fail-open: auto-retrying assertion — no chip for unknown / empty caps.
    expect(page.locator(".cap-chip-no-tools")).to_have_count(0, timeout=2000)


@pytest.mark.browser
def test_studio_picker_lifecycle_on_type_switch(
    app_with_two_providers,
    page: Page,
) -> None:
    """Switching ollama → openrouter → ollama → openrouter leaves exactly
    one #studio-model element in the DOM after each switch.

    Verifies that swapModelPicker() uses replaceWith() correctly and no
    duplicate or orphan elements accumulate across provider type changes.
    """
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]

    page.goto(f"{base_url}#studio")
    # Wait for the Studio area to initialize (page-header visible = Studio mounted).
    expect(page.locator(".page-title")).to_have_text("Agents", timeout=8000)
    empty_btn = page.locator('[data-testid="new-agent-btn-empty"]')
    expect(empty_btn).to_be_visible(timeout=5000)
    empty_btn.click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)

    sequence = [
        (ollama_id, "SELECT"),
        (openrouter_id, "INPUT"),
        (ollama_id, "SELECT"),
        (openrouter_id, "INPUT"),
    ]

    for prov_id, expected_tag in sequence:
        page.locator("#studio-provider").select_option(prov_id)
        # Auto-retrying assertion: exactly one #studio-model element after DOM settles.
        expect(page.locator("#studio-model")).to_have_count(1, timeout=2000)

        actual_tag = page.evaluate("document.getElementById('studio-model').tagName")
        assert actual_tag == expected_tag, (
            f"After switching to provider {prov_id!r}: expected {expected_tag}, got {actual_tag!r}"
        )
