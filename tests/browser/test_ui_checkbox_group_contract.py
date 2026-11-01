# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.checkboxGroup`` (M33 F1 L9).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

DAYS = """() => {
  window.__ch = [];
  const g = App.ui.checkboxGroup({
    legend: 'Days', value: ['b'], testid: 'cg',
    onChange: (v) => window.__ch.push(v),
    options: [
      {value: 'a', label: 'Mon', testid: 'cg-a'},
      {value: 'b', label: 'Tue', testid: 'cg-b'},
      {value: 'c', label: 'Wed', testid: 'cg-c'},
    ],
  });
  window.__g = g;
  document.getElementById('harness-root').appendChild(g.el);
  return true;
}"""


def _mount(page: Page) -> None:
    load_harness(page, "dark")
    page.evaluate(DAYS)


def test_structure_and_names(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => { const el = window.__g.el;
          return {tag: el.tagName, cls: el.className, tid: el.getAttribute('data-testid'),
                  legend: el.firstElementChild.tagName, legendText: el.firstElementChild.textContent,
                  boxes: el.querySelectorAll('input[type=checkbox]').length,
                  value: window.__g.value()}; }"""
    )
    assert out["tag"] == "FIELDSET" and out["cls"] == "ui-checkbox-group"
    assert out["tid"] == "cg" and out["legend"] == "LEGEND" and out["legendText"] == "Days"
    assert out["boxes"] == 3 and out["value"] == ["b"]
    assert engine_page.get_by_role("group", name="Days").count() == 1
    assert engine_page.get_by_role("checkbox", name="Tue").is_checked()


def test_value_in_option_order_and_set_value_is_silent(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_role("checkbox", name="Wed").check()
    p.get_by_role("checkbox", name="Mon").check()
    assert p.evaluate("() => window.__g.value()") == ["a", "b", "c"]
    assert p.evaluate("() => window.__ch") == [["b", "c"], ["a", "b", "c"]]
    p.evaluate("() => { window.__g.setValue(['c', 'zzz']); }")
    assert p.evaluate("() => window.__g.value()") == ["c"]
    assert len(p.evaluate("() => window.__ch")) == 2  # silent


def test_keyboard_tab_and_space(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__g.focus()")
    p.keyboard.press("Space")
    assert p.evaluate("() => window.__g.value()") == ["a", "b"]
    p.keyboard.press("Tab")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "cg-b"
    p.keyboard.press("Tab")
    p.keyboard.press("Space")
    assert p.evaluate("() => window.__g.value()") == ["a", "b", "c"]


def test_set_disabled(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__g.setDisabled(true)")
    assert p.evaluate(
        "() => Array.from(window.__g.el.querySelectorAll('input')).every((i) => i.disabled)"
    )
    p.evaluate("() => window.__g.setDisabled(false)")
    assert not p.get_by_role("checkbox", name="Mon").is_disabled()


def test_missing_legend_or_options_throws(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    for src in (
        "App.ui.checkboxGroup({options:[{value:'a',label:'A'}]})",
        "App.ui.checkboxGroup({legend:'L'})",
        "App.ui.checkboxGroup({legend:'L', options:[{value:'a',label:'A'},{value:'a',label:'B'}]})",
    ):
        msg = engine_page.evaluate(
            "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
            src,
        )
        assert msg.startswith("App.ui.checkboxGroup"), src


def test_destroy_stops_on_change(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__g.destroy()")
    p.get_by_role("checkbox", name="Mon").check()
    assert p.evaluate("() => window.__ch") == []


DAY_TOGGLES = """() => {
  window.__ch = [];
  const names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const letters = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
  const vals = [6, 0, 1, 2, 3, 4, 5];  // the app's 0 = Monday ... 6 = Sunday, shown Sunday first
  const g = App.ui.checkboxGroup({
    legend: 'Repeat on', variant: 'days', value: [0], testid: 'dg',
    onChange: (v) => window.__ch.push(v),
    options: names.map((n, i) => ({value: vals[i], label: n, short: letters[i], testid: 'dg-' + vals[i]})),
  });
  window.__g = g;
  document.getElementById('harness-root').appendChild(g.el);
  return true;
}"""


def test_days_variant_structure_and_names(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    p = engine_page
    p.evaluate(DAY_TOGGLES)
    assert p.get_by_role("group", name="Repeat on").count() == 1
    out = p.evaluate(
        """() => { const el = window.__g.el;
          return {cls: el.className, boxes: el.querySelectorAll('input[type=checkbox]').length,
                  letters: Array.from(el.querySelectorAll('.ui-day-letter')).map(e => [e.textContent, e.getAttribute('aria-hidden')]),
                  value: window.__g.value()}; }"""
    )
    assert out["cls"] == "ui-checkbox-group ui-checkbox-group--days" and out["boxes"] == 7
    assert [x[0] for x in out["letters"]] == list("SMTWTFS") and all(
        x[1] == "true" for x in out["letters"]
    )
    assert out["value"] == [0]
    for name in ("Sunday", "Monday", "Saturday"):
        assert p.get_by_role("checkbox", name=name, exact=True).count() == 1
    assert p.get_by_role("checkbox", name="Monday").is_checked()


def test_days_variant_value_contract_and_keyboard(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    p = engine_page
    p.evaluate(DAY_TOGGLES)
    p.get_by_role("checkbox", name="Sunday").check()
    p.get_by_role("checkbox", name="Friday").check()
    assert p.evaluate("() => window.__g.value()") == [6, 0, 4]  # option order is Sunday first
    p.evaluate("() => window.__g.setValue([2, 99])")
    assert p.evaluate("() => window.__g.value()") == [2]
    assert len(p.evaluate("() => window.__ch")) == 2  # setValue is silent
    p.evaluate("() => window.__g.focus()")
    p.keyboard.press("Space")
    assert p.get_by_role("checkbox", name="Sunday").is_checked()
    p.evaluate("() => window.__g.setDisabled(true)")
    assert p.get_by_role("checkbox", name="Sunday").is_disabled()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_days_variant_checked_is_visible_without_colour_alone(
    engine_page: Page, theme: str
) -> None:
    load_harness(engine_page, theme)
    p = engine_page
    p.evaluate(DAY_TOGGLES)
    on = p.evaluate(
        """() => { const l = (v) => document.querySelector('[data-testid=dg-' + v + ']').closest('label');
          const a = getComputedStyle(l(0)), b = getComputedStyle(l(1));
          return {onW: a.fontWeight, offW: b.fontWeight, onBg: a.backgroundColor, offBg: b.backgroundColor,
                  onShadow: a.boxShadow, offShadow: b.boxShadow, w: l(0).getBoundingClientRect().width,
                  radius: a.borderRadius}; }"""
    )
    assert on["onBg"] != on["offBg"]
    assert (
        int(on["onW"]) > int(on["offW"]) and on["onShadow"] != "none" and on["offShadow"] == "none"
    )
    assert on["w"] == 32 and on["radius"] in ("50%", "16px")
    # The visible focus ring is drawn on the circle when the native input has keyboard focus.
    p.keyboard.press("Tab")
    ring = p.evaluate(
        """() => { const l = document.activeElement.closest('label'); const s = getComputedStyle(l);
          return {style: s.outlineStyle, width: s.outlineWidth}; }"""
    )
    assert ring["style"] != "none" and ring["width"] != "0px"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_days_variant_checked_disabled_looks_disabled(engine_page: Page, theme: str) -> None:
    load_harness(engine_page, theme)
    p = engine_page
    p.evaluate(DAY_TOGGLES)
    p.get_by_role("checkbox", name="Sunday").check()
    read = """() => { const s = getComputedStyle(
        document.querySelector('[data-testid=dg-0]').closest('label'));
        return s.backgroundColor + '|' + s.color; }"""
    enabled = p.evaluate(read)
    p.evaluate("() => window.__g.setDisabled(true)")
    disabled = p.evaluate(read)
    assert enabled != disabled
    p.evaluate("() => window.__g.setDisabled(false)")
    assert p.evaluate(read) == enabled
