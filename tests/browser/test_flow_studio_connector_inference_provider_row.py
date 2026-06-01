"""Studio connector-editor inference-provider/model rows (M11 F13 L4).

Pin five UI surfaces against regression:

1. Conditional render under ``always_listen=true`` (rows visible).
2. Hidden under ``always_listen=false`` (rows not visible).
3. Provider dropdown populates from ``GET /api/providers``.
4. Selecting provider + entering model + save round-trips through
   ``connector.config``.
5. Clearing the provider selection + model saves ``null`` (defaults
   back to routed-agent-LLM fallback per the L3 dispatcher contract).
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import (
    seed_connector,
    seed_mock_provider,
)
from playwright.sync_api import Page, expect


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connectors/{account_id}", timeout=5.0)
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
    """Seeded with always_listen=true → both rows visible."""
    account_id = seed_connector(
        app_clean,
        name="Visible-Inference Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    expect(page.locator('[data-testid="connector-config-inference-provider-select"]')).to_be_visible(timeout=4000)
    expect(page.locator('[data-testid="connector-config-inference-model-input"]')).to_be_visible(timeout=4000)


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
    assert "Use routed agent" in placeholder_text, f"expected fallback hint; got {placeholder_text!r}"


# ── Test 4: select provider + model → save round-trips ───────────────────


@pytest.mark.browser
def test_inference_provider_and_model_save_roundtrip(app_clean: str, page: Page) -> None:
    """Select provider + enter model + save → GET shows the persisted values."""
    p1_id = seed_mock_provider(app_clean, name="provider-roundtrip")
    account_id = seed_connector(
        app_clean,
        name="Roundtrip-Inference Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    expect(sel.locator(f'option[value="{p1_id}"]')).to_be_attached(timeout=5000)
    sel.select_option(value=p1_id)

    model_input = page.locator('[data-testid="connector-config-inference-model-input"]')
    model_input.fill("gpt-4o-mini")

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
    """Seeded with non-null inference config → select placeholder + clear model + save → null/null."""
    p1_id = seed_mock_provider(app_clean, name="provider-to-clear")
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
    sel.select_option(value="")  # placeholder

    model_input = page.locator('[data-testid="connector-config-inference-model-input"]')
    expect(model_input).to_have_value("qwen2.5:7b")
    model_input.fill("")

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    cfg = after.get("config") or {}
    assert cfg.get("inference_provider_config_id") is None, (
        f"expected inference_provider_config_id=None; got {cfg}"
    )
    assert cfg.get("inference_model") is None, (
        f"expected inference_model=None; got {cfg}"
    )
