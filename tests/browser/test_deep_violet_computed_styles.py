# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Computed-style contract for the deep-violet treatment (M25 F1 L3, DD6/DD7).

Mounts one button per variant (plus size / icon modifiers), a checked and an
unchecked checkbox, and on / off admin and studio toggles, then asserts the
computed colours, sizes and padding against the DD6 values and the
``design_tokens.py`` mirror, in Chromium and WebKit, both themes. Reduced motion
is emulated so hover reads are not mid-transition. Falls in the ``shared`` lane.
"""

from __future__ import annotations

import re

import pytest
from browser._ui_engines import load_harness
from browser.design_tokens import DARK, LIGHT
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

THEMES = ("dark", "light")
TRANSPARENT = "rgba(0, 0, 0, 0)"

MOUNT_JS = """() => {
  const root = document.getElementById('harness-root');
  const svg = '<svg viewBox="0 0 24 24" width="24" height="24"><path d="M5 12h14"/></svg>';
  const btn = (id, cls, extra) =>
    `<button type="button" id="${id}" class="${cls}" ${extra || ''}>Label</button>`;
  const ibtn = (id, cls) =>
    `<button type="button" id="${id}" class="${cls}" aria-label="icon">${svg}</button>`;
  root.innerHTML = `
    <div>
      ${btn('b-primary', 'btn-filled-primary')}
      ${btn('b-secondary', 'btn-outlined-primary')}
      ${btn('b-ghost', 'btn-ghost')}
      ${btn('b-danger', 'btn-muted-destructive')}
      ${btn('b-sm', 'btn-filled-primary btn-sm')}
      ${btn('b-lg', 'btn-filled-primary btn-lg')}
      ${btn('b-save', 'btn-filled-primary save-btn')}
      ${btn('b-delete', 'btn-muted-destructive delete-btn')}
      ${ibtn('b-icon', 'btn-ghost btn-icon')}
      ${ibtn('b-icon-sm', 'btn-ghost btn-icon btn-sm')}
      <input type="checkbox" id="cb-off" class="checkbox-primary">
      <input type="checkbox" id="cb-on" class="checkbox-primary" checked>
    </div>
    <div class="area-admin">
      <label class="tool-enable-switch"><input type="checkbox" id="sw-admin-off"><span class="tool-enable-switch-track" id="tr-admin-off"></span></label>
      <label class="tool-enable-switch"><input type="checkbox" id="sw-admin-on" checked><span class="tool-enable-switch-track" id="tr-admin-on"></span></label>
    </div>
    <div class="area-studio">
      <label class="tool-enable-switch"><input type="checkbox" id="sw-studio-on" checked><span class="tool-enable-switch-track" id="tr-studio-on"></span></label>
      <div class="tool-actions"><button type="button" id="b-compact" class="btn-outlined-primary">Compact</button></div>
      <label class="tool-row"><input type="checkbox" class="tool-toggle" id="ts-off"><span class="tool-switch" id="tsw-off"></span></label>
      <label class="tool-row"><input type="checkbox" class="tool-toggle" id="ts-on" checked><span class="tool-switch" id="tsw-on"></span></label>
    </div>`;
  return true;
}"""

STYLE_JS = """([sel, pseudo]) => {
  const cs = getComputedStyle(document.querySelector(sel), pseudo || null);
  return {
    bg: cs.backgroundColor, color: cs.color, border: cs.borderTopColor,
    borderR: cs.borderRightColor, fontSize: cs.fontSize, weight: cs.fontWeight,
    height: cs.height, width: cs.width, padding: cs.padding, radius: cs.borderTopLeftRadius,
  };
}"""


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


def _style(page: Page, sel: str, pseudo: str | None = None) -> dict:
    return page.evaluate(STYLE_JS, [sel, pseudo])


def _setup(page: Page, theme: str) -> dict:
    page.emulate_media(reduced_motion="reduce")
    load_harness(page, theme)
    page.evaluate(MOUNT_JS)
    return DARK if theme == "dark" else LIGHT


def _var_px(page: Page, name: str) -> str:
    return page.evaluate(
        "(n) => { const e = document.createElement('div'); e.style.fontSize = `var(${n})`;"
        " document.getElementById('harness-root').appendChild(e);"
        " const v = getComputedStyle(e).fontSize; e.remove(); return v; }",
        name,
    )


@pytest.mark.parametrize("theme", THEMES)
def test_button_variants_at_rest(engine_page: Page, theme: str) -> None:
    t = _setup(engine_page, theme)
    expect = {
        "#b-primary": (_rgb(t["accent_fill"]), _rgb(t["fg_on_accent_fill"]), TRANSPARENT),
        "#b-secondary": (_rgb(t["surface_elevated"]), _rgb(t["fg"]), _rgb(t["border"])),
        "#b-ghost": (TRANSPARENT, _rgb(t["fg_secondary"]), TRANSPARENT),
        "#b-danger": (TRANSPARENT, _rgb(t["status_danger"]), _rgb(t["status_danger_muted"])),
    }
    for sel, (bg, color, border) in expect.items():
        s = _style(engine_page, sel)
        assert s["bg"] == bg, (sel, "bg", s)
        assert s["color"] == color, (sel, "color", s)
        assert s["border"] == border, (sel, "border", s)
        # Shared geometry/label (DD6).
        assert s["height"] == "32px", (sel, s)
        assert s["padding"] == "0px 12px", (sel, s)
        assert s["fontSize"] == "13px", (sel, s)
        assert s["weight"] == "500", (sel, s)
        assert s["radius"] == _var_px(engine_page, "--radius-sm"), (sel, s)
    # Primary never carries the old accent fill (a retune of --accent must not move it).
    assert _style(engine_page, "#b-primary")["bg"] != _rgb(t["accent"]) or theme == "light"


@pytest.mark.parametrize("theme", THEMES)
def test_button_hover_states(engine_page: Page, theme: str) -> None:
    t = _setup(engine_page, theme)
    engine_page.hover("#b-primary")
    s = _style(engine_page, "#b-primary")
    assert s["bg"] == _rgb(t["accent_fill_hover"]), s
    assert s["color"] == _rgb(t["fg_on_accent_fill"]), s
    assert (
        engine_page.evaluate("() => getComputedStyle(document.querySelector('#b-primary')).opacity")
        == "1"
    )

    engine_page.hover("#b-secondary")
    s = _style(engine_page, "#b-secondary")
    assert s["border"] == _rgb(t["border_strong"]), s
    assert s["bg"] == _rgb(t["surface_elevated"]), s  # hover changes only the border

    engine_page.hover("#b-ghost")
    s = _style(engine_page, "#b-ghost")
    assert s["bg"] == _rgb(t["surface_elevated"]), s
    assert s["color"] == _rgb(t["fg"]), s

    engine_page.hover("#b-danger")
    s = _style(engine_page, "#b-danger")
    m = re.match(r"rgba\((\d+), (\d+), (\d+), ([0-9.]+)\)", s["bg"])
    assert m and float(m.group(4)) > 0, s  # soft danger wash appears on hover only
    assert f"rgb({m.group(1)}, {m.group(2)}, {m.group(3)})" == _rgb(t["status_danger"]), s
    assert s["border"] == _rgb(t["status_danger_muted"]), s  # hover changes only the fill


@pytest.mark.parametrize("theme", THEMES)
def test_size_modifiers_and_icon_buttons(engine_page: Page, theme: str) -> None:
    _setup(engine_page, theme)
    sm = _style(engine_page, "#b-sm")
    assert (sm["height"], sm["padding"], sm["weight"]) == ("24px", "0px 8px", "500"), sm
    assert sm["fontSize"] == _var_px(engine_page, "--font-size-tiny"), sm
    lg = _style(engine_page, "#b-lg")
    assert (lg["height"], lg["padding"], lg["fontSize"], lg["weight"]) == (
        "36px",
        "0px 20px",
        "13px",
        "500",
    ), lg

    icon = _style(engine_page, "#b-icon")
    assert (icon["width"], icon["height"], icon["padding"]) == ("32px", "32px", "0px"), icon
    svg = _style(engine_page, "#b-icon svg")
    assert (svg["width"], svg["height"]) == ("16px", "16px"), svg
    isml = _style(engine_page, "#b-icon-sm")
    assert (isml["width"], isml["height"], isml["padding"]) == ("24px", "24px", "0px"), isml
    svg = _style(engine_page, "#b-icon-sm svg")
    assert (svg["width"], svg["height"]) == ("14px", "14px"), svg
    # svg in a standard button is 16px
    engine_page.evaluate(
        "() => document.getElementById('b-primary').insertAdjacentHTML('afterbegin', '<svg width=\"24\" height=\"24\"></svg>')"
    )
    svg = _style(engine_page, "#b-primary svg")
    assert (svg["width"], svg["height"]) == ("16px", "16px"), svg


@pytest.mark.parametrize("theme", THEMES)
def test_override_reconciliation(engine_page: Page, theme: str) -> None:
    _setup(engine_page, theme)
    for sel in ("#b-save", "#b-delete"):
        s = _style(engine_page, sel)
        assert s["padding"] == "0px 12px", (sel, s)
        assert s["fontSize"] == "13px", (sel, s)
    assert _style(engine_page, "#b-delete")["radius"] == _var_px(engine_page, "--radius-sm")
    # Documented compact-row exception keeps its compact size.
    c = _style(engine_page, "#b-compact")
    assert c["padding"] == "3px 10px", c
    assert c["fontSize"] == _var_px(engine_page, "--font-size-caption"), c


@pytest.mark.parametrize("theme", THEMES)
def test_checkbox_and_toggles(engine_page: Page, theme: str) -> None:
    t = _setup(engine_page, theme)
    off = _style(engine_page, "#cb-off")
    assert off["border"] == _rgb(t["control_border"]), off
    on = _style(engine_page, "#cb-on")
    assert on["bg"] == _rgb(t["accent_fill"]) and on["border"] == _rgb(t["accent_fill"]), on
    tick = _style(engine_page, "#cb-on", "::after")
    assert tick["borderR"] == _rgb(t["fg_on_accent_fill"]), tick

    for track, thumb_bg, track_bg in (
        ("#tr-admin-off", t["control_thumb"], t["control_border"]),
        ("#tr-admin-on", t["control_thumb"], t["accent_fill"]),
        ("#tr-studio-on", t["control_thumb"], t["accent_fill"]),
        ("#tsw-off", t["control_thumb"], t["control_border"]),
        ("#tsw-on", t["control_thumb"], t["accent_fill"]),
    ):
        assert _style(engine_page, track)["bg"] == _rgb(track_bg), track
        assert _style(engine_page, track, "::after")["bg"] == _rgb(thumb_bg), track
