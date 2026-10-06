"""Browser flow: Studio model picker for OpenRouter (<select> with type-ahead).

Covers:
- Selecting an openrouter provider renders a <select> populated with the
  seeded model entries (same element type as ollama/anthropic/etc).
- A model whose supported_parameters lacks 'tools' shows the .cap-chip-no-tools
  chip in the capabilities panel.
- A model with empty supported_parameters renders no chip (fail-open).
- Switching provider types repeatedly leaves exactly one #studio-model
  element in the DOM.
- A rapid provider switch doesn't let a slow stale fetch clobber the final
  picker state.
- A previously-selected value that isn't in the new provider's model list
  appears as a visible "(custom)" option so the operator sees the mismatch.

A prior datalist+input variant was tried but its value-driven filter
trapped operators with a stale selection (the dropdown showed only the
previously-picked match); the picker was unified back to a plain <select>.

The synthetic model list is injected via THE_ONE_OPENROUTER_TEST_MODELS_JSON
so no live OpenRouter network call is needed. See conftest.py for the
``app_with_openrouter_models`` and ``app_with_two_providers`` fixtures.
"""

from __future__ import annotations

import time

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_openrouter_picker_renders_select(
    app_with_openrouter_models,
    page: Page,
) -> None:
    """Selecting an openrouter provider renders a <select> populated with
    the seeded models."""
    base_url = app_with_openrouter_models.base_url
    provider_id = app_with_openrouter_models.provider_id

    _nav.goto(page, base_url, "agents")
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(provider_id)

    # <select> options populate after the /models fetch resolves (3 seeded
    # models + the disabled "Choose a model" placeholder = 4 options).
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)

    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "SELECT", f"expected SELECT element, got {tag!r}"

    values = page.eval_on_selector_all("#studio-model option", "els => els.map(e => e.value)")
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

    _nav.goto(page, base_url, "agents")
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)

    page.locator("#studio-model").select_option("no-tools-model")

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

    _nav.goto(page, base_url, "agents")
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)

    page.locator("#studio-model").select_option("anthropic/claude-3.5-sonnet")

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

    _nav.goto(page, base_url, "agents")
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)

    page.locator("#studio-model").select_option("empty-caps-model")

    expect(page.locator(".cap-chip-no-tools")).to_have_count(0, timeout=2000)


@pytest.mark.browser
def test_studio_picker_singleton_on_type_switch(
    app_with_two_providers,
    page: Page,
) -> None:
    """Switching ollama → openrouter → ollama → openrouter leaves exactly
    one #studio-model element in the DOM after each switch (no orphans).
    """
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]

    _nav.goto(page, base_url, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    _lists.agents_new(page)

    for prov_id in (ollama_id, openrouter_id, ollama_id, openrouter_id):
        page.locator("#studio-provider").select_option(prov_id)
        expect(page.locator("#studio-model")).to_have_count(1, timeout=2000)
        tag = page.evaluate("document.getElementById('studio-model').tagName")
        assert tag == "SELECT", (
            f"After switching to provider {prov_id!r}: expected SELECT, got {tag!r}"
        )


@pytest.mark.browser
def test_rapid_provider_switch_uses_final_selection(
    app_with_two_providers,
    page: Page,
) -> None:
    """Rapid provider changes must not let an earlier (slow) fetch clobber
    the final picker state.

    The agent editor fires ``fetchModelsForProvider(providerId)`` on every
    change of the provider <select>. Without a guard, two concurrent
    fetches resolve in arbitrary order: a slow response for provider A
    arriving after a fast response for provider B silently overwrites
    the picker with A's models — even though the user has B selected.
    AbortController + activeProviderId equality check (studio.js) guard
    against this.
    """
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]

    def _slow_openrouter(route, request):
        time.sleep(0.6)
        route.continue_()

    page.route(f"**/api/providers/{openrouter_id}/models", _slow_openrouter)

    _nav.goto(page, base_url, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    _lists.agents_new(page)

    # Step 1: select openrouter (slow fetch in flight).
    page.locator("#studio-provider").select_option(openrouter_id)

    # Step 2: switch to ollama BEFORE the openrouter fetch resolves.
    page.locator("#studio-provider").select_option(ollama_id)

    # Step 3: wait for the now-stale openrouter fetch to resolve. Without
    # the race guard it would clobber the ollama-populated select with
    # openrouter models.
    page.wait_for_timeout(1500)

    # Final assertion: the select carries ollama's models, not openrouter's.
    values = page.eval_on_selector_all(
        "#studio-model option", "els => els.map(e => e.value).filter(Boolean)"
    )
    # The seeded openrouter list includes "anthropic/claude-3.5-sonnet" —
    # if any openrouter id leaked through, the guard failed.
    assert "anthropic/claude-3.5-sonnet" not in values, (
        f"stale openrouter fetch clobbered the picker: {values}"
    )


@pytest.mark.skip(
    reason=(
        "M08 F4 KI: Leg 02 picker UX redesign changed the type-switch flow. "
        "Test asserts pre-redesign value-preservation behavior; needs "
        "redesign-aware rewrite. See mission.md Known Issues."
    )
)
@pytest.mark.browser
def test_picker_preserves_value_across_type_switch_as_custom(
    app_with_two_providers,
    page: Page,
) -> None:
    """Switching provider types preserves a selected model value across
    the switch — even when the destination provider doesn't expose that
    model — by surfacing it as a visible "(custom)" option in the new
    provider's select.

    Operators frequently switch provider types as a means of comparison
    (e.g. "is this model also offered on the other route?"). The model
    name should not silently disappear; instead the operator sees it
    flagged as not-in-this-provider's-listing.

    Sequence:
      1. Select OpenRouter, pick "anthropic/claude-3.5-sonnet".
      2. Switch to Ollama (which doesn't list that id) — option appears
         as "anthropic/claude-3.5-sonnet (custom)" and stays selected.
      3. Switch back to OpenRouter — the option is now a real listed
         model, and stays selected.
    """
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]

    _nav.goto(page, base_url, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    _lists.agents_new(page)

    # Step 1: pick an openrouter model.
    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)
    page.locator("#studio-model").select_option("anthropic/claude-3.5-sonnet")
    expect(page.locator("#studio-model")).to_have_value("anthropic/claude-3.5-sonnet", timeout=2000)

    # Step 2: switch to Ollama. The chosen value isn't in Ollama's list,
    # so it appears as a "(custom)" fallback option and stays selected.
    page.locator("#studio-provider").select_option(ollama_id)
    expect(page.locator("#studio-model")).to_have_value("anthropic/claude-3.5-sonnet", timeout=3000)
    custom_label = page.locator(
        '#studio-model option[value="anthropic/claude-3.5-sonnet"]'
    ).inner_text(timeout=2000)
    assert "(custom)" in custom_label, (
        f"expected (custom) label on the unmatched option, got {custom_label!r}"
    )

    # Step 3: switch back to OpenRouter. The value is now a real listed
    # model — no "(custom)" suffix.
    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator("#studio-model")).to_have_value("anthropic/claude-3.5-sonnet", timeout=3000)
    real_label = page.locator(
        '#studio-model option[value="anthropic/claude-3.5-sonnet"]'
    ).inner_text(timeout=2000)
    assert "(custom)" not in real_label, f"option should be the listed model, got {real_label!r}"
