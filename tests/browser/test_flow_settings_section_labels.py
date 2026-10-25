"""Flight 6 leg 4 (section-labels, DD13): the eyebrow-with-a-rule section header.

Probes the computed style of a provider editor's and a Built-in tools editor's
section titles, the danger-zone variant (text and rule in --status-danger), the
"Test connection" row (the rule runs past the info icon), and D2 (one rule per
section boundary: no editor-section divider under a title rule).

Falls in the ``settings`` lane (``test_flow_settings_*``).
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.design_tokens import DARK, LIGHT
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

PROBE_JS = """(sel) => {
  const n = document.querySelector(sel);
  const s = getComputedStyle(n), a = getComputedStyle(n, '::after');
  return {fontSize: s.fontSize, weight: s.fontWeight, transform: s.textTransform,
          spacing: parseFloat(s.letterSpacing), color: s.color, display: s.display,
          gap: s.columnGap, margin: s.margin,
          rule: {h: parseFloat(a.height), w: parseFloat(a.width), bg: a.backgroundColor,
                 content: a.content}};
}"""


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"


def _assert_eyebrow(out: dict, pal: dict, colour_key: str = "fg_tertiary") -> None:
    assert out["fontSize"] == "10px" and out["weight"] == "600", out
    assert out["transform"] == "uppercase" and abs(out["spacing"] - 0.8) <= 0.05, out
    assert out["color"] == _rgb(pal[colour_key]), out
    assert out["display"] == "flex" and out["gap"] == "10px", out
    assert out["rule"]["content"] != "none" and out["rule"]["h"] == 1 and out["rule"]["w"] > 0, out


@pytest.mark.browser
@pytest.mark.parametrize(("scheme", "pal"), [("dark", DARK), ("light", LIGHT)])
def test_provider_editor_section_titles_and_danger_zone(
    app_with_provider: SeededApp, page: Page, scheme: str, pal: dict
) -> None:
    page.emulate_media(color_scheme=scheme)
    _nav.goto(
        page, app_with_provider.base_url, f"library/providers/{app_with_provider.provider_id}"
    )
    sections = page.locator(".editor-section")
    expect(sections.first).to_be_visible(timeout=8000)
    page.evaluate(
        "() => { document.querySelectorAll('.editor-section > .section-title')"
        ".forEach((n, i) => n.setAttribute('data-probe', 'st' + i)); }"
    )
    first = page.evaluate(PROBE_JS, '[data-probe="st0"]')
    _assert_eyebrow(first, pal)
    assert first["margin"].startswith("0px 0px 10px"), first  # :first-child
    # The danger-zone title: text and rule in --status-danger.
    page.evaluate(
        "() => document.querySelector('.danger-zone-title').setAttribute('data-probe', 'dz')"
    )
    dz = page.evaluate(PROBE_JS, '[data-probe="dz"]')
    _assert_eyebrow(dz, pal, "status_danger")
    assert dz["rule"]["bg"] == _rgb(pal["status_danger"]), dz
    # D2: a section that opens with a title shows no divider.
    borders = page.evaluate(
        "() => Array.from(document.querySelectorAll('.editor-section'))"
        ".map((s) => getComputedStyle(s).borderTopWidth)"
    )
    assert len(borders) >= 2 and all(b == "0px" for b in borders), borders


@pytest.mark.browser
def test_tools_editor_title_row_rule_runs_past_the_icon(app_clean: str, page: Page) -> None:
    page.emulate_media(color_scheme="dark")
    _nav.goto(page, app_clean, "settings/tools")
    _lists.open_tool(page, "web_search")
    row = page.locator(".settings-item .ui-section-title-row")
    expect(row).to_be_visible(timeout=8000)
    t = page.evaluate(
        """() => {
          const row = document.querySelector('.settings-item .ui-section-title-row');
          const icon = row.querySelector('.field-info-icon').getBoundingClientRect();
          const text = row.querySelector('.section-title').getBoundingClientRect();
          const rr = row.getBoundingClientRect();
          const a = getComputedStyle(row, '::after');
          const own = getComputedStyle(row.querySelector('.section-title'), '::after');
          // the rule's box starts after the icon: row right edge minus its width
          return {ruleLeft: rr.right - parseFloat(a.width), ruleH: parseFloat(a.height),
                  iconRight: icon.right, iconLeft: icon.left, textRight: text.right,
                  ownContent: own.content};
        }"""
    )
    assert t["ruleH"] == 1 and t["ruleLeft"] >= t["iconRight"], t
    assert t["iconLeft"] - t["textRight"] < 16, t  # the icon stays beside the text
    assert t["ownContent"] == "none", t
    title = page.evaluate(
        "() => { const n = document.querySelector("
        "'.settings-item .ui-section-title-row .section-title');"
        " n.setAttribute('data-probe', 'row'); return true; }"
    )
    assert title
    out = page.evaluate(PROBE_JS, '[data-probe="row"]')
    assert out["fontSize"] == "10px" and out["transform"] == "uppercase", out
    # A Built-in tools section header (the Prompt title) has the same recipe.
    page.evaluate(
        "() => document.querySelector('.editor-section > .section-title')"
        ".setAttribute('data-probe', 'tt')"
    )
    _assert_eyebrow(page.evaluate(PROBE_JS, '[data-probe="tt"]'), DARK)
