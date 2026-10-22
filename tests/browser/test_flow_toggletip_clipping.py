"""Toggletip clipping (M31 F2 L11, carried from leg 05).

The info bubble (`.ui-info-bubble`) is absolutely positioned inside its `.ui-info`
wrapper.  An editor pane that scrolls (or clips) its content must not cut an open
bubble off: its rect has to lie inside the rect of every ancestor whose overflow
is not `visible` (and inside the viewport).
"""

from __future__ import annotations

import urllib.parse

import pytest
from browser import _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

_CLIP_CHECK = """(sel) => {
  const btn = document.querySelector(sel);
  const bubble = document.getElementById(btn.getAttribute('aria-controls'));
  const b = bubble.getBoundingClientRect();
  const clips = [];
  for (let n = bubble.parentElement; n && n !== document.documentElement; n = n.parentElement) {
    const cs = getComputedStyle(n);
    if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
      const r = n.getBoundingClientRect();
      clips.push({cls: n.className, l: r.left, t: r.top, r: r.right, b: r.bottom,
        ox: cs.overflowX, oy: cs.overflowY});
    }
  }
  return {bubble: {l: b.left, t: b.top, r: b.right, b: b.bottom}, clips,
    vw: innerWidth, vh: innerHeight};
}"""


def _assert_not_clipped(page: Page, selector: str) -> None:
    info = page.evaluate(_CLIP_CHECK, selector)
    b = info["bubble"]
    assert b["r"] > b["l"] and b["b"] > b["t"]
    assert b["l"] >= -0.5 and b["r"] <= info["vw"] + 0.5
    assert b["t"] >= -0.5 and b["b"] <= info["vh"] + 0.5
    for c in info["clips"]:
        # An ancestor that is only as tall as the bubble's own wrapper cannot clip it
        # when it does not clip that axis; any clipping ancestor must contain the bubble.
        assert b["l"] >= c["l"] - 0.5 and b["r"] <= c["r"] + 0.5, c
        assert b["t"] >= c["t"] - 0.5 and b["b"] <= c["b"] + 0.5, c


@pytest.mark.browser
def test_provider_editor_info_bubble_is_not_clipped(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("ollama")
    icon = page.locator(".admin-pf-num-ctx .field-info-icon")
    expect(icon).to_be_visible()
    icon.click()
    expect(icon).to_have_attribute("aria-expanded", "true")
    expect(page.locator(f"#{icon.get_attribute('aria-controls')}")).to_be_visible()
    _assert_not_clipped(page, ".admin-pf-num-ctx .field-info-icon")


@pytest.mark.browser
def test_agent_editor_info_bubble_is_not_clipped(app_with_agent: SeededApp, page: Page) -> None:
    agent = urllib.parse.quote(app_with_agent.agent_name or "")
    _nav.goto(page, app_with_agent.base_url, f"agents/{_nav.seg(agent)}/tools")
    tile = page.locator('.ui-group-tile[data-category="Web"]')
    expect(tile).to_be_visible(timeout=8000)
    tile.locator(".ui-group-tile-expand").click()
    row = tile.locator("details.ui-tool-row").first
    row.locator(".ui-tool-row-affordance").click()
    icon = row.locator("button.field-info-icon").first
    expect(icon).to_be_visible(timeout=8000)
    icon.click()
    expect(icon).to_have_attribute("aria-expanded", "true")
    _assert_not_clipped(page, ".ui-tool-row[open] button.field-info-icon")
