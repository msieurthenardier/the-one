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
