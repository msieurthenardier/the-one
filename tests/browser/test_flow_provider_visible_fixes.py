"""Flight 6 leg 1a (visible-fixes), the provider-editor half; moved to the
``providers`` lane and the Library routes in sortie 02 (Settings has no Providers
page now). The tools half stays in ``test_flow_settings_visible_fixes.py``.

* DD4 (squawks 0112, 0081) -- a 422 on the provider create form reads as
  "field: message" in ``.editor-error``, never "[object Object]";
* squawk 0114 -- every ``field-info-icon`` has an accessible name;
* DD10 -- the provider's model list is headed "Available models" with one line
  of help, and its rows are plain information.

Falls in the ``providers`` lane (``test_flow_provider_*``).
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _seed(base_url: str, name: str, type_: str = "openai-compatible") -> str:
    r = httpx.post(
        f"{base_url}/api/providers",
        json={
            "name": name,
            "type": type_,
            "base_url": "https://example.com/v1",
            "api_key": "sk-seedkey1234",
        },
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── DD4: the form shows a 422 legibly ────────────────────────────────────


@pytest.mark.browser
def test_provider_create_422_is_flattened_in_the_error_area(app_clean: str, page: Page) -> None:
    def fulfil(route):
        route.fulfill(
            status=422,
            content_type="application/json",
            body=json.dumps(
                {"detail": [{"loc": ["body", "base_url"], "msg": "Field required", "type": "x"}]}
            ),
        )

    page.route(
        "**/api/providers", lambda r: fulfil(r) if r.request.method == "POST" else r.continue_()
    )
    _nav.goto(page, app_clean, "library/providers/~new")
    page.locator("#pf-type").select_option("openai-compatible")
    page.locator("#pf-name").fill("p1")
    page.locator("#pf-base-url").fill("https://example.com/v1")
    page.locator("#pf-api-key").fill("sk-abc")
    page.locator(".save-btn").click()
    err = page.locator(".editor-error")
    expect(err).to_contain_text("body.base_url: Field required", timeout=8000)
    expect(err).not_to_contain_text("[object Object]")


# ── 0114: info icons are named ───────────────────────────────────────────


@pytest.mark.browser
def test_provider_info_icons_have_accessible_names(app_clean: str, page: Page) -> None:
    pid = _seed(app_clean, "ollama-ish", "ollama")
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(pid)}")
    icons = page.locator("button.field-info-icon")
    expect(icons.first).to_be_attached(timeout=8000)
    assert icons.count() >= 1
    for i in range(icons.count()):
        assert (icons.nth(i).get_attribute("aria-label") or "").strip(), i
        # Press-only toggletip (squawk 0221): no hover title; it controls a bubble.
        assert icons.nth(i).get_attribute("title") is None, i
        assert icons.nth(i).get_attribute("aria-expanded") == "false", i
        assert icons.nth(i).get_attribute("aria-controls"), i
        # Named once: the label carries the hint, so no second description.
        assert icons.nth(i).get_attribute("aria-describedby") is None, i


# ── DD10: the Models list label ──────────────────────────────────────────


@pytest.mark.browser
def test_provider_models_section_is_labelled_available_models(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto(
        page, app_with_provider.base_url, f"library/providers/{app_with_provider.provider_id}"
    )
    section = page.locator(".editor-section:has(.provider-models)")
    expect(section.locator(".section-title")).to_have_text("Available models", timeout=8000)
    help_line = section.locator('[data-testid="provider-models-help"]')
    expect(help_line).to_contain_text("Each agent chooses one of these in its Model section.")
    link = help_line.locator("a")
    expect(link).to_have_text("Agents")
    expect(link).to_have_attribute("href", _nav.href("agents"))
    item = section.locator(".admin-pf-model-item").first
    expect(item).to_be_visible(timeout=8000)
    assert item.evaluate("e => getComputedStyle(e).cursor") == "default"
