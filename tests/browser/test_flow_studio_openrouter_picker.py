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

import re
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
    "no tools" chip in the capabilities panel."""
    base_url = app_with_openrouter_models.base_url
    provider_id = app_with_openrouter_models.provider_id

    _nav.goto(page, base_url, "agents")
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)

    page.locator("#studio-model").select_option("no-tools-model")

    chip = page.locator(".model-capabilities").get_by_text("no tools", exact=True)
    expect(chip).to_be_visible(timeout=3000)
    expect(chip).to_have_attribute("title", re.compile("does not support tool calling"))


@pytest.mark.browser
def test_studio_openrouter_tools_model_no_no_tools_chip(
    app_with_openrouter_models,
    page: Page,
) -> None:
    """Selecting a model that HAS 'tools' in supported_parameters does NOT
    render the "no tools" chip."""
    base_url = app_with_openrouter_models.base_url
    provider_id = app_with_openrouter_models.provider_id

    _nav.goto(page, base_url, "agents")
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(provider_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)

    page.locator("#studio-model").select_option("anthropic/claude-3.5-sonnet")

    expect(page.locator(".model-capabilities").get_by_text("no tools", exact=True)).to_have_count(
        0, timeout=2000
    )


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

    expect(page.locator(".model-capabilities").get_by_text("no tools", exact=True)).to_have_count(
        0, timeout=2000
    )


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


@pytest.mark.browser
def test_picker_preserves_value_across_type_switch_as_custom(
    app_with_two_providers,
    page: Page,
) -> None:
    """Switching provider carries the chosen model across as a visible
    "(custom)" option when the new provider does not list it, and shows it as
    a normal listed model again when switching back (squawk 0156).

    Sequence:
      1. Select OpenRouter, pick "anthropic/claude-3.5-sonnet".
      2. Switch to Ollama (which doesn't list that id): the id is present as
         "<id> (custom)" and selected.
      3. Switch back to OpenRouter: the id is a real listed model, selected,
         never labelled "(custom)".
    """
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]
    chosen = "anthropic/claude-3.5-sonnet"

    # No Ollama daemon runs in the test environment, so serve it a model list
    # that does not contain the OpenRouter ids.
    page.route(
        f"**/api/providers/{ollama_id}/models",
        lambda route: route.fulfill(
            json=[{"id": "llama3", "name": "llama3"}],
        ),
    )

    _nav.goto(page, base_url, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator(f'#studio-model option[value="{chosen}"]')).to_have_count(1, timeout=8000)
    page.locator("#studio-model").select_option(chosen)
    expect(page.locator("#studio-model")).to_have_value(chosen, timeout=2000)

    page.locator("#studio-provider").select_option(ollama_id)
    custom = page.locator(f'#studio-model option[value="{chosen}"]')
    expect(custom).to_have_text(f"{chosen} (custom)", timeout=8000)
    expect(page.locator("#studio-model")).to_have_value(chosen)

    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)
    labels = page.eval_on_selector_all(
        f'#studio-model option[value="{chosen}"]', "els => els.map(e => e.textContent)"
    )
    assert labels == [chosen], labels
    expect(page.locator("#studio-model")).to_have_value(chosen)


@pytest.mark.browser
def test_picker_stale_carried_value_does_not_resurface(
    app_with_two_providers,
    page: Page,
) -> None:
    """A carried-over value is consumed by the fetch it was captured for: pick
    A, switch away and back, pick B, switch again -> B (custom), never A."""
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]
    a = "anthropic/claude-3.5-sonnet"
    b = "no-tools-model"
    # No Ollama daemon runs in the test environment, so serve it a model list
    # that does not contain the OpenRouter ids.
    page.route(
        f"**/api/providers/{ollama_id}/models",
        lambda route: route.fulfill(
            json=[{"id": "llama3", "name": "llama3"}],
        ),
    )

    _nav.goto(page, base_url, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    _lists.agents_new(page)

    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator(f'#studio-model option[value="{a}"]')).to_have_count(1, timeout=8000)
    page.locator("#studio-model").select_option(a)

    page.locator("#studio-provider").select_option(ollama_id)
    expect(page.locator(f'#studio-model option[value="{a}"]')).to_have_text(
        f"{a} (custom)", timeout=8000
    )

    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)
    page.locator("#studio-model").select_option(b)
    expect(page.locator("#studio-model")).to_have_value(b)

    page.locator("#studio-provider").select_option(ollama_id)
    expect(page.locator(f'#studio-model option[value="{b}"]')).to_have_text(
        f"{b} (custom)", timeout=8000
    )
    expect(page.locator("#studio-model")).to_have_value(b)
    assert page.locator(f'#studio-model option[value="{a}"]').count() == 0
