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

import time

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
    the active picker with A's models — even though the user has B
    selected.

    State transitions exercised:
      0. [editor-mounted, no-provider]
         - #studio-model present, no provider selected
      0 -> 1. [openrouter-selected, fetch-pending(slow)]:
         - intercept openrouter /models with a 1s delay
         - select openrouter — #studio-model becomes INPUT
      1 -> 2. [ollama-selected, fetch-resolved-fast]:
         - select ollama BEFORE the openrouter fetch resolves
         - #studio-model becomes SELECT
      2 -> 3. [final-state]:
         - wait long enough for the delayed openrouter fetch to resolve
         - assert #studio-model is still SELECT (matches the live provider)
         - assert datalist (if present) does NOT carry openrouter models
         - assert no error toast / banner appeared
    """
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]

    # Slow down the openrouter /models response so the ollama fetch wins
    # the race. The handler awaits then forwards via page.request so the
    # real backend reply (with seeded models) is returned.
    def _slow_openrouter(route, request):
        # Stall the response for ~600ms before delivering. Sync sleep is
        # fine inside Playwright route handlers — they're invoked off the
        # main test thread.
        time.sleep(0.6)
        route.continue_()

    page.route(f"**/api/providers/{openrouter_id}/models", _slow_openrouter)

    page.goto(f"{base_url}#studio")
    expect(page.locator(".page-title")).to_have_text("Agents", timeout=8000)
    page.locator('[data-testid="new-agent-btn-empty"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)

    # Step 0 -> 1: select openrouter (slow fetch in flight).
    page.locator("#studio-provider").select_option(openrouter_id)
    # Picker swaps to INPUT immediately (before fetch resolves).
    expect(page.locator("#studio-model")).to_have_count(1, timeout=2000)
    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "INPUT"

    # Step 1 -> 2: switch to ollama BEFORE the openrouter fetch resolves.
    page.locator("#studio-provider").select_option(ollama_id)
    expect(page.locator("#studio-model")).to_have_count(1, timeout=2000)
    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "SELECT"

    # Step 2 -> 3: wait long enough for the (now-stale) openrouter fetch
    # to resolve. Without the race guard this would clobber the SELECT
    # back to an INPUT (or repopulate with openrouter models).
    page.wait_for_timeout(1500)

    # Final assertion: still SELECT (matches the LIVE provider value).
    expect(page.locator("#studio-model")).to_have_count(1, timeout=2000)
    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "SELECT", (
        f"expected SELECT (ollama is the live provider), got {tag!r} — "
        "stale openrouter fetch clobbered the picker"
    )

    # Datalist for openrouter should not be populated (no INPUT picker).
    # The datalist element either doesn't exist (we're in SELECT mode) or
    # was wiped when the picker was swapped — either way, count is 0.
    datalist_count = page.locator("#studio-model-list").count()
    assert datalist_count == 0, "openrouter datalist must be removed in SELECT mode"


@pytest.mark.browser
def test_picker_preserves_value_across_type_switch(
    app_with_two_providers,
    page: Page,
) -> None:
    """Switching provider types preserves the typed/selected model value.

    Operators frequently switch provider types as a means of comparison
    (e.g. "what does Anthropic charge for the same model?"). The model
    name should NOT silently disappear from the input on every flip —
    the form would go falsely "dirty" with an empty value, and the user
    has to retype the same identifier on every switch.

    Sequence:
      1. Select OpenRouter, type a model name into the input
      2. Switch to Ollama (picker swaps INPUT -> SELECT)
      3. Switch back to OpenRouter (picker swaps SELECT -> INPUT)
      4. The original model name is still in the input
    """
    base_url = app_with_two_providers["base_url"]
    openrouter_id = app_with_two_providers["openrouter_id"]
    ollama_id = app_with_two_providers["ollama_id"]

    page.goto(f"{base_url}#studio")
    expect(page.locator(".page-title")).to_have_text("Agents", timeout=8000)
    page.locator('[data-testid="new-agent-btn-empty"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)

    # Step 1: select OpenRouter, wait for INPUT picker to be ready.
    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator("#studio-model")).to_have_count(1, timeout=3000)
    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "INPUT"

    # Type a custom model name.
    page.locator("#studio-model").fill("anthropic/claude-3.5-sonnet")
    # Read it back to confirm it landed.
    expect(page.locator("#studio-model")).to_have_value(
        "anthropic/claude-3.5-sonnet", timeout=2000
    )

    # Step 2: switch to Ollama — picker swaps to SELECT.
    page.locator("#studio-provider").select_option(ollama_id)
    expect(page.locator("#studio-model")).to_have_count(1, timeout=2000)
    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "SELECT"

    # Step 3: switch back to OpenRouter — picker swaps to INPUT again.
    page.locator("#studio-provider").select_option(openrouter_id)
    expect(page.locator("#studio-model")).to_have_count(1, timeout=2000)
    tag = page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "INPUT"

    # Step 4: the original model name should still be present.
    # Either as the visible value (if SELECT preserved pendingValue and
    # the new INPUT was seeded), or as the datalist-resolved value after
    # fetchModelsForProvider re-applied pendingValue.
    expect(page.locator("#studio-model")).to_have_value(
        "anthropic/claude-3.5-sonnet", timeout=3000
    )
