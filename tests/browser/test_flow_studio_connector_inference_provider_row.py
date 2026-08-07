"""Studio connector-editor inference-provider/model rows (M11 F13 L4 + F14 L4).

Pin UI surfaces against regression:

1. Conditional render under ``always_listen=true`` (rows visible).
2. Hidden under ``always_listen=false`` (rows not visible).
3. Provider dropdown populates from ``GET /api/providers``.
4. Selecting provider + model + save round-trips through ``connector.config``.
5. Clearing the provider selection + model saves ``null`` (defaults back to
   routed-agent-LLM fallback per the L3 dispatcher contract).

F14 L4 model-dropdown backfill (``populateInferenceModelDropdown`` +
``wireInferenceModelRepopulate``, connector-editor.js:3329-3431):

6. populate — provider with ``config={"models":[...]}`` populates the model
   ``<select>`` with those options.
7. race-guard — switching provider A→B while A's model fetch is in flight
   cancels the stale fetch (mirrors test_flow_studio_openrouter_picker.py:177-207).
8. custom-fallback — a persisted model NOT in the provider's list surfaces as a
   selected ``"{value} (custom)"`` option (connector-editor.js:3420-3423).
9. no-provider placeholder — provider unset → disabled "Select a provider first".
10. GUI-clear synthetic change — clearing the provider fires a synthetic change
    so Save re-enables (F13 recapture regression target).

The model field is a ``<select>`` (``connector-config-inference-model-select``,
connector-editor.js:556-558), NOT an input — the F13 L4-enhancement swapped it.
A ``type=="mock"`` provider's ``GET /api/providers/{id}/models`` returns
``config["models"]`` directly (api.py:3576-3586; default ``["mock-default"]``),
so a seeded mock provider self-serves models with no ``page.route()`` stub —
except the race-guard test, which routes the endpoint to control timing.
"""

from __future__ import annotations

import time

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from browser.seeders import (
    seed_connector,
    seed_mock_provider,
)
from playwright.sync_api import Page, expect

# ── Helpers ──────────────────────────────────────────────────────────────


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(
        f"{base_url}/api/connectors/{account_id}", timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _open_connector_editor_access_tab(page: Page, base_url: str, account_id: str) -> None:
    page.goto(f"{base_url}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-access-and-routing"]').click()


# ── Test 1: rows hidden under always_listen=false ─────────────────────────


@pytest.mark.browser
def test_inference_rows_hidden_when_always_listen_off(app_clean: str, page: Page) -> None:
    """Seeded with always_listen=false (default) → rows not visible."""
    account_id = seed_connector(app_clean, name="Hidden-Inference Bot")
    _open_connector_editor_access_tab(page, app_clean, account_id)

    rows = page.locator('[data-testid="connector-inference-rows-container"]')
    # The wrapper may exist in the DOM with the ``hidden`` attribute.
    # Playwright's not_to_be_visible resolves true for hidden-attr OR
    # display:none OR removed-from-DOM.
    expect(rows).not_to_be_visible(timeout=4000)


# ── Test 2: rows visible under always_listen=true ─────────────────────────


@pytest.mark.browser
def test_inference_rows_visible_when_always_listen_on(app_clean: str, page: Page) -> None:
    """Seeded with always_listen=true → both rows visible.

    The model field is a ``<select>`` (``connector-config-inference-model-select``),
    not an input — repaired from the F13 L4-enhancement stale fixture.
    """
    account_id = seed_connector(
        app_clean,
        name="Visible-Inference Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    expect(
        page.locator('[data-testid="connector-config-inference-provider-select"]')
    ).to_be_visible(timeout=4000)
    expect(page.locator('[data-testid="connector-config-inference-model-select"]')).to_be_visible(
        timeout=4000
    )


# ── Test 3: dropdown populates from /api/providers ───────────────────────


@pytest.mark.browser
def test_inference_provider_dropdown_populates_from_api(app_clean: str, page: Page) -> None:
    """Seeded with 2 mock providers → dropdown lists both + empty placeholder."""
    p1_id = seed_mock_provider(app_clean, name="provider-alpha")
    p2_id = seed_mock_provider(app_clean, name="provider-beta")
    account_id = seed_connector(
        app_clean,
        name="Populated-Dropdown Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    expect(sel).to_be_visible(timeout=4000)
    # Wait for async population.
    expect(sel.locator(f'option[value="{p1_id}"]')).to_be_attached(timeout=5000)
    expect(sel.locator(f'option[value="{p2_id}"]')).to_be_attached(timeout=5000)
    # Empty-state placeholder is the first option.
    placeholder = sel.locator('option[value=""]').first
    expect(placeholder).to_be_attached()
    placeholder_text = placeholder.text_content() or ""
    assert "Use routed agent" in placeholder_text, (
        f"expected fallback hint; got {placeholder_text!r}"
    )


# ── Test 4: select provider + model → save round-trips ───────────────────


@pytest.mark.browser
def test_inference_provider_and_model_save_roundtrip(app_clean: str, page: Page) -> None:
    """Select provider + pick model + save → GET shows the persisted values.

    Repaired from the F13 L4-enhancement stale fixture: the model field is a
    ``<select>``, so we ``.select_option(...)`` a value the seeded mock provider
    actually serves (``config={"models":[...]}``) — otherwise the option would
    not exist to select.
    """
    p1_id = seed_mock_provider(
        app_clean,
        name="provider-roundtrip",
        config={"models": ["gpt-4o-mini", "gpt-4o"]},
    )
    account_id = seed_connector(
        app_clean,
        name="Roundtrip-Inference Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    expect(sel.locator(f'option[value="{p1_id}"]')).to_be_attached(timeout=5000)
    sel.select_option(value=p1_id)

    model_sel = page.locator('[data-testid="connector-config-inference-model-select"]')
    # The model select repopulates async from the provider's /models endpoint;
    # wait for the served option to attach before selecting it.
    expect(model_sel.locator('option[value="gpt-4o-mini"]')).to_be_attached(timeout=5000)
    model_sel.select_option(value="gpt-4o-mini")

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    cfg = after.get("config") or {}
    assert cfg.get("inference_provider_config_id") == p1_id, (
        f"expected inference_provider_config_id={p1_id!r}; got {cfg}"
    )
    assert cfg.get("inference_model") == "gpt-4o-mini", (
        f"expected inference_model='gpt-4o-mini'; got {cfg}"
    )


# ── Test 5: clearing selection saves null ────────────────────────────────


@pytest.mark.browser
def test_inference_provider_clear_saves_null(app_clean: str, page: Page) -> None:
    """Seeded with non-null inference config → clear provider + save → null/null.

    Repaired from the F13 L4-enhancement stale fixture: the model field is a
    ``<select>``. The seeded provider serves the persisted model so it renders
    as a real selected option; clearing the provider resets the model select to
    the "Select a provider first" placeholder.
    """
    p1_id = seed_mock_provider(
        app_clean,
        name="provider-to-clear",
        config={"models": ["qwen2.5:7b"]},
    )
    account_id = seed_connector(
        app_clean,
        name="Clear-Inference Bot",
        config={
            "always_listen": True,
            "inference_provider_config_id": p1_id,
            "inference_model": "qwen2.5:7b",
        },
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    # Wait for population to finish so the selected option reflects the persisted value.
    expect(sel.locator(f'option[value="{p1_id}"][selected]')).to_be_attached(timeout=5000)

    model_sel = page.locator('[data-testid="connector-config-inference-model-select"]')
    expect(model_sel).to_have_value("qwen2.5:7b", timeout=5000)

    sel.select_option(value="")  # placeholder → fires synthetic change on model select

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    cfg = after.get("config") or {}
    assert cfg.get("inference_provider_config_id") is None, (
        f"expected inference_provider_config_id=None; got {cfg}"
    )
    assert cfg.get("inference_model") is None, f"expected inference_model=None; got {cfg}"


# ── Test 6 (F14 L4 a): model select populates from provider /models ──────


@pytest.mark.browser
def test_inference_model_select_populates_from_provider(app_clean: str, page: Page) -> None:
    """Provider with config={"models":[...]} → model select gets those options.

    Exercises populateInferenceModelDropdown's fetch→options path against the
    self-serving mock /models endpoint (api.py:3576-3586).
    """
    p1_id = seed_mock_provider(
        app_clean,
        name="provider-with-models",
        config={"models": ["m1", "m2"]},
    )
    account_id = seed_connector(
        app_clean,
        name="ModelPopulate Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    expect(sel.locator(f'option[value="{p1_id}"]')).to_be_attached(timeout=5000)
    sel.select_option(value=p1_id)

    model_sel = page.locator('[data-testid="connector-config-inference-model-select"]')
    expect(model_sel.locator('option[value="m1"]')).to_be_attached(timeout=5000)
    expect(model_sel.locator('option[value="m2"]')).to_be_attached(timeout=5000)
    # Both served models present beyond the "— No model —" placeholder.
    values = page.eval_on_selector_all(
        '[data-testid="connector-config-inference-model-select"] option',
        "els => els.map(e => e.value).filter(Boolean)",
    )
    assert set(values) >= {"m1", "m2"}, f"expected served models in select; got {values}"


# ── Test 7 (F14 L4 b): race-guard cancels a stale model fetch ────────────


@pytest.mark.browser
def test_inference_model_select_race_guard_cancels_stale_fetch(app_clean: str, page: Page) -> None:
    """Switch provider A→B while A's /models is in flight → A's models absent.

    Mirrors test_flow_studio_openrouter_picker.py:177-207 verbatim in shape:
    route A's /models endpoint with a 0.6s sleep then ``route.continue_()``,
    select A (slow fetch in flight), switch to B before it resolves, wait for
    the stale fetch to land, then assert A's disjoint models never clobbered
    B's. The AbortController + activeProviderId equality check
    (connector-editor.js:3362-3401) guards against the stale overwrite.
    """
    a_id = seed_mock_provider(
        app_clean,
        name="provider-A-slow",
        config={"models": ["alpha-only-1", "alpha-only-2"]},
    )
    b_id = seed_mock_provider(
        app_clean,
        name="provider-B-fast",
        config={"models": ["beta-only-1", "beta-only-2"]},
    )
    account_id = seed_connector(
        app_clean,
        name="RaceGuard Bot",
        config={"always_listen": True},
    )

    def _slow_a(route, request):
        time.sleep(0.6)
        route.continue_()

    page.route(f"**/api/providers/{a_id}/models", _slow_a)

    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    expect(sel.locator(f'option[value="{a_id}"]')).to_be_attached(timeout=5000)
    expect(sel.locator(f'option[value="{b_id}"]')).to_be_attached(timeout=5000)

    # Step 1: select A (slow fetch in flight).
    sel.select_option(value=a_id)
    # Step 2: switch to B BEFORE A's fetch resolves.
    sel.select_option(value=b_id)
    # Step 3: wait for the now-stale A fetch to resolve. Without the race guard
    # it would clobber the B-populated select with A's models.
    page.wait_for_timeout(1500)

    values = page.eval_on_selector_all(
        '[data-testid="connector-config-inference-model-select"] option',
        "els => els.map(e => e.value).filter(Boolean)",
    )
    # A's models are disjoint from B's — if any A id leaked, the guard failed.
    assert "alpha-only-1" not in values and "alpha-only-2" not in values, (
        f"stale provider-A fetch clobbered the model select: {values}"
    )
    # And B's models did land.
    assert "beta-only-1" in values, f"expected provider-B models; got {values}"


# ── Test 8 (F14 L4 c): custom-fallback for a non-enumerated model ────────


@pytest.mark.browser
def test_inference_model_select_custom_fallback(app_clean: str, page: Page) -> None:
    """Persisted model NOT in the provider's list → selected "{value} (custom)".

    The provider serves ["m1","m2"] but the connector persists "not-listed";
    populateInferenceModelDropdown (connector-editor.js:3420-3423) preserves the
    operator's saved value as a selected custom option rather than wiping it.
    """
    p1_id = seed_mock_provider(
        app_clean,
        name="provider-custom",
        config={"models": ["m1", "m2"]},
    )
    account_id = seed_connector(
        app_clean,
        name="CustomModel Bot",
        config={
            "always_listen": True,
            "inference_provider_config_id": p1_id,
            "inference_model": "not-listed-model",
        },
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    model_sel = page.locator('[data-testid="connector-config-inference-model-select"]')
    # On mount, wireInferenceModelRepopulate populates for the persisted
    # provider; the non-enumerated value surfaces as "{value} (custom)".
    custom_opt = model_sel.locator('option[value="not-listed-model"]')
    expect(custom_opt).to_be_attached(timeout=5000)
    expect(custom_opt).to_have_text("not-listed-model (custom)", timeout=5000)
    # It is the selected value.
    expect(model_sel).to_have_value("not-listed-model", timeout=5000)


# ── Test 9 (F14 L4 d): no-provider placeholder ───────────────────────────


@pytest.mark.browser
def test_inference_model_select_no_provider_placeholder(app_clean: str, page: Page) -> None:
    """No provider selected → model select shows disabled "Select a provider first"."""
    # Seed a provider so the provider dropdown has options, but leave the
    # connector's inference provider unset.
    seed_mock_provider(app_clean, name="provider-unused", config={"models": ["m1"]})
    account_id = seed_connector(
        app_clean,
        name="NoProvider Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    model_sel = page.locator('[data-testid="connector-config-inference-model-select"]')
    expect(model_sel).to_be_visible(timeout=4000)
    placeholder = model_sel.locator('option[value=""]').first
    expect(placeholder).to_have_text("Select a provider first")
    # Placeholder is disabled and the select carries no model value.
    assert placeholder.get_attribute("disabled") is not None, "placeholder should be disabled"
    expect(model_sel).to_have_value("")


# ── Test 10 (F14 L4 e): GUI-clear fires synthetic change → Save re-enables ─


@pytest.mark.browser
def test_inference_provider_gui_clear_fires_synthetic_change(app_clean: str, page: Page) -> None:
    """Clearing the provider via the GUI re-enables Save (F13 recapture target).

    When the operator clears a persisted provider via the select, the model
    select dispatches a synthetic ``change`` event (connector-editor.js:3385) so
    the dirty-tracker sees the edit vs the persisted baseline and Save re-enables.
    """
    p1_id = seed_mock_provider(
        app_clean,
        name="provider-gui-clear",
        config={"models": ["qwen2.5:7b"]},
    )
    account_id = seed_connector(
        app_clean,
        name="GuiClear Bot",
        config={
            "always_listen": True,
            "inference_provider_config_id": p1_id,
            "inference_model": "qwen2.5:7b",
        },
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    # Wait for the persisted provider to be the selected option (mount settled).
    expect(sel.locator(f'option[value="{p1_id}"][selected]')).to_be_attached(timeout=5000)

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    # Pristine mount → Save disabled.
    expect(save_btn).to_be_disabled(timeout=4000)

    # GUI clear the provider.
    sel.select_option(value="")

    # The synthetic change on the model select propagates to the dirty-tracker;
    # Save becomes enabled.
    expect(save_btn).not_to_be_disabled(timeout=4000)
    # The model select reset to the no-provider placeholder.
    model_sel = page.locator('[data-testid="connector-config-inference-model-select"]')
    expect(model_sel).to_have_value("")
