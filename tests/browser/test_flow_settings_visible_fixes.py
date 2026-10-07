"""Flight 6 leg 1a (visible-fixes): the Settings-side fixes.

* DD4 (squawks 0112, 0081) -- a 422 on the provider create form reads as
  "field: message" in ``.editor-error``, never "[object Object]";
* DD3 (squawk 0116) -- the Settings tiles' name never overlaps its badge, in
  both themes at 1024 and 1440 wide, and a short name is not truncated early;
* squawk 0114 -- every ``field-info-icon`` has an accessible name;
* DD10 -- the provider's model list is headed "Available models" with one line
  of help, and its rows are plain information.

Falls in the ``settings`` lane (``test_flow_settings_*``).
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser import _lists, _nav
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

LONG_NAME = "a-very-long-provider-name-" + "x" * 90


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
    _nav.goto(page, app_clean, "settings/providers/~new")
    page.locator("#pf-type").select_option("openai-compatible")
    page.locator("#pf-name").fill("p1")
    page.locator("#pf-base-url").fill("https://example.com/v1")
    page.locator("#pf-api-key").fill("sk-abc")
    page.locator(".save-btn").click()
    err = page.locator(".editor-error")
    expect(err).to_contain_text("body.base_url: Field required", timeout=8000)
    expect(err).not_to_contain_text("[object Object]")


# ── DD3: tile title row ──────────────────────────────────────────────────


def _overlap(page: Page, tile_sel: str, name_sel: str, badge_sel: str) -> dict:
    return page.evaluate(
        """([t, n, b]) => {
          const tile = document.querySelector(t);
          const name = tile.querySelector(n).getBoundingClientRect();
          const badge = tile.querySelector(b).getBoundingClientRect();
          const tr = tile.getBoundingClientRect();
          return {
            overlap: name.right > badge.left + 0.5 && name.left < badge.right &&
                     name.bottom > badge.top && name.top < badge.bottom,
            badgeInside: badge.right <= tr.right + 0.5 && badge.left >= tr.left,
            nameRight: name.right, badgeLeft: badge.left,
          };
        }""",
        [tile_sel, name_sel, badge_sel],
    )


@pytest.mark.browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [1024, 1440])
def test_tile_name_never_overlaps_badge(
    app_clean: str, page: Page, scheme: str, width: int
) -> None:
    page.emulate_media(color_scheme=scheme)
    page.set_viewport_size({"width": width, "height": 900})
    _seed(app_clean, LONG_NAME)
    _seed(app_clean, "short")
    _nav.goto(page, app_clean, "settings/providers")
    expect(_lists.providers_list(page).get_by_role("listitem")).to_have_count(2, timeout=8000)
    long_tile = '.provider-tile:has(a[title^="a-very-long"])'
    r = _overlap(page, long_tile, ".provider-tile-link", ".provider-tile-badge")
    assert not r["overlap"], r
    assert r["badgeInside"], r
    short = page.locator('.provider-tile:has(a[title="short"]) .provider-tile-link')
    assert short.evaluate("e => e.scrollWidth <= e.clientWidth"), "short name truncated early"

    # Tools: a long tool name (the DOM text is swapped; the names are fixed).
    _nav.goto(page, app_clean, "settings/tools")
    tile = page.locator('[data-testid="tool-card"]').first
    expect(tile).to_be_visible(timeout=8000)
    short_fits = tile.locator(".tool-tile-link").evaluate("e => e.scrollWidth <= e.clientWidth")
    assert short_fits, "short tool name truncated early"
    page.evaluate(
        "(n) => { document.querySelector('[data-testid=\"tool-card\"] .tool-tile-link')"
        ".textContent = n; }",
        "an_extremely_long_tool_name_" + "y" * 90,
    )
    r = _overlap(page, '[data-testid="tool-card"]', ".tool-tile-link", ".admin-tool-badge")
    assert not r["overlap"], r
    assert r["badgeInside"], r


# ── 0114: info icons are named ───────────────────────────────────────────


@pytest.mark.browser
def test_provider_info_icons_have_accessible_names(app_clean: str, page: Page) -> None:
    pid = _seed(app_clean, "ollama-ish", "ollama")
    _nav.goto(page, app_clean, f"settings/providers/{_nav.seg(pid)}")
    icons = page.locator("button.field-info-icon")
    expect(icons.first).to_be_attached(timeout=8000)
    assert icons.count() >= 1
    for i in range(icons.count()):
        assert (icons.nth(i).get_attribute("aria-label") or "").strip(), i
        assert icons.nth(i).get_attribute("title")
        # Named once: the label carries the hint, so no second description.
        assert icons.nth(i).get_attribute("aria-describedby") is None, i


@pytest.mark.browser
def test_tools_editor_info_icons_have_accessible_names(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/tools")
    _lists.open_tool(page, "web_search")
    icons = page.locator("button.field-info-icon")
    expect(icons.first).to_be_attached(timeout=8000)
    for i in range(icons.count()):
        assert icons.nth(i).get_attribute("aria-describedby") is None, i
    assert_controls_labelled_and_described(page, ".settings-item")


# ── DD10: the Models list label ──────────────────────────────────────────


@pytest.mark.browser
def test_provider_models_section_is_labelled_available_models(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto(
        page, app_with_provider.base_url, f"settings/providers/{app_with_provider.provider_id}"
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
