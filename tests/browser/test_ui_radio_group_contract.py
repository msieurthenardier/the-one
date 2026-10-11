# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.radioGroup`` (M28 F2 L2).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

THREE = """() => {
  window.__ch = [];
  const g = App.ui.radioGroup({
    legend: 'Pick one', value: 'b', testid: 'rg',
    onChange: (v) => window.__ch.push(v),
    options: [
      {value: 'a', label: 'Alpha', description: 'First option', testid: 'rg-a'},
      {value: 'b', label: 'Beta', description: 'Second option', testid: 'rg-b'},
      {value: 'c', label: 'Gamma', testid: 'rg-c'},
    ],
  });
  window.__g = g;
  const start = document.createElement('button'); start.id = 'start'; start.textContent = 'start';
  const root = document.getElementById('harness-root');
  root.appendChild(start); root.appendChild(g.el);
  return true;
}"""


def _mount(page: Page, js: str = THREE):
    load_harness(page, "dark")
    return page.evaluate(js)


def _throws(page: Page, expr: str) -> str:
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


def _checked_wrappers(page: Page) -> int:
    return page.evaluate("() => document.querySelectorAll('.ui-radio-option.is-checked').length")


def test_structure_and_accessible_names(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => { const g = window.__g, el = g.el;
          const opt = el.querySelector('.ui-radio-option');
          return {tag: el.tagName, cls: el.className, tid: el.getAttribute('data-testid'),
                  legend: el.firstElementChild.tagName,
                  kids: Array.from(opt.children).map((c) => c.className.split(' ')[0]),
                  inTid: g.input('a').getAttribute('data-testid'),
                  own: g.input('a').hasAttribute('data-ui-own-label'),
                  name: g.input('a').name === g.input('b').name && g.input('a').name.length > 0,
                  desc: document.getElementById(g.input('a').getAttribute('aria-describedby')).textContent,
                  noDesc: !g.input('c').hasAttribute('aria-describedby'),
                  slotEmpty: g.optionEl('a').childNodes.length}; }"""
    )
    assert out["tag"] == "FIELDSET" and out["cls"] == "ui-radio-group" and out["tid"] == "rg"
    assert out["legend"] == "LEGEND"
    assert out["kids"] == ["ui-radio-label", "field-hint", "ui-radio-slot"]
    assert out["inTid"] == "rg-a" and out["own"] and out["name"] and out["noDesc"]
    assert out["desc"] == "First option" and out["slotEmpty"] == 0
    group = p.get_by_role("group", name="Pick one")
    expect(group).to_have_count(1)
    for label in ("Alpha", "Beta", "Gamma"):
        expect(group.get_by_role("radio", name=label, exact=True)).to_have_count(1)
    expect(p.get_by_role("radio", name="Alpha")).to_have_accessible_description("First option")
    assert_controls_labelled_and_described(p, "#harness-root")


def test_initial_value_and_value_not_among_options(engine_page: Page) -> None:
    _mount(engine_page)
    assert engine_page.evaluate("() => window.__g.value()") == "b"
    out = engine_page.evaluate(
        """() => { const g = App.ui.radioGroup({legend: 'L', value: 'zzz', options: [{value: 'a', label: 'A'}]});
          return g.value(); }"""
    )
    assert out is None


def test_keyboard_tab_arrows_space_and_checked_class(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.focus("#start")
    p.keyboard.press("Tab")
    focused = p.evaluate(
        "() => document.activeElement.id || document.activeElement.getAttribute('data-testid')"
    )
    if focused == "start":
        pytest.skip("Tab did not move focus in this engine")
    if focused != "rg-b":
        # Some engines skip radios on Tab; fall back to the group's own focus().
        p.evaluate("() => window.__g.focus()")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "rg-b"
    p.keyboard.press("ArrowDown")
    assert p.evaluate("() => window.__g.value()") == "c"
    assert _checked_wrappers(p) == 1
    p.keyboard.press("ArrowUp")
    assert p.evaluate("() => window.__g.value()") == "b"
    assert _checked_wrappers(p) == 1
    p.keyboard.press("ArrowUp")
    assert p.evaluate("() => window.__g.value()") == "a"
    assert _checked_wrappers(p) == 1
    assert p.evaluate("() => window.__ch") == ["c", "b", "a"]
    # Space on a focused unchecked radio checks it.
    p.evaluate("() => window.__g.input('c').focus()")
    p.keyboard.press("Space")
    assert p.evaluate("() => window.__g.value()") == "c"
    assert p.evaluate("() => window.__ch") == ["c", "b", "a", "c"]
    assert _checked_wrappers(p) == 1


def test_click_calls_on_change_once(engine_page: Page) -> None:
    _mount(engine_page)
    engine_page.get_by_role("radio", name="Alpha").click()
    assert engine_page.evaluate("() => window.__ch") == ["a"]
    assert _checked_wrappers(engine_page) == 1


def test_api_semantics(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => { const g = window.__g;
          g.setValue('c');
          const silent = window.__ch.length === 0 && g.value() === 'c';
          g.setValue('nope');
          const unknownNoop = g.value() === 'c';
          g.setValue(null);
          const cleared = g.value() === null && document.querySelectorAll('.ui-radio-option.is-checked').length === 0;
          g.setDescription('c', 'Now described');
          const cInput = g.input('c');
          const made = document.getElementById(cInput.getAttribute('aria-describedby')).textContent;
          g.setDescription('a', '');
          const removed = !g.input('a').hasAttribute('aria-describedby') && !g.el.querySelector('.ui-radio-option .field-hint:empty');
          g.setDescription('zzz', 'x');
          const btn = document.createElement('button'); btn.textContent = 'Slot button';
          g.optionEl('b').appendChild(btn);
          return {silent, unknownNoop, cleared, made, removed, noOpt: g.optionEl('zzz'), noInput: g.input('zzz'),
                  slotIsDiv: g.optionEl('b').className};
        }"""
    )
    assert out == {
        "silent": True, "unknownNoop": True, "cleared": True, "made": "Now described",
        "removed": True, "noOpt": None, "noInput": None, "slotIsDiv": "ui-radio-slot",
    }  # fmt: skip
    expect(engine_page.get_by_role("radio", name="Beta", exact=True)).to_have_count(1)


def test_disabled_option_is_not_set(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => { const g = App.ui.radioGroup({legend: 'D', value: 'a', options: [
            {value: 'a', label: 'A'}, {value: 'b', label: 'B', disabled: true}]});
          document.getElementById('harness-root').appendChild(g.el);
          g.setValue('b');
          return {v: g.value(), cls: g.el.querySelectorAll('.ui-radio-option')[1].className}; }"""
    )
    assert out["v"] == "a" and "is-disabled" in out["cls"]


def test_two_groups_without_names_do_not_interfere(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => { const mk = () => App.ui.radioGroup({legend: 'G', value: 'x', options: [{value: 'x', label: 'X'}, {value: 'y', label: 'Y'}]});
          const g1 = mk(), g2 = mk();
          const root = document.getElementById('harness-root');
          root.appendChild(g1.el); root.appendChild(g2.el);
          g1.setValue('y');
          return [g1.value(), g2.value(), g1.input('x').name !== g2.input('x').name]; }"""
    )
    assert out == ["y", "x", True]


def test_focus_method_prefers_checked_then_first_enabled(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => { const g = window.__g; g.focus();
          const a = document.activeElement === g.input('b');
          g.setValue(null);
          const g2 = App.ui.radioGroup({legend: 'F', options: [{value: 'p', label: 'P', disabled: true}, {value: 'q', label: 'Q'}]});
          document.getElementById('harness-root').appendChild(g2.el);
          g2.focus();
          return [a, document.activeElement === g2.input('q')]; }"""
    )
    assert out == [True, True]


def test_focus_ring_on_keyboard_focus(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.focus("#start")
    p.keyboard.press("Tab")
    if p.evaluate("() => document.activeElement.type") != "radio":
        # WebKit's Tab skips radios; reach the group programmatically, then
        # let a real key event move the selection (and the focus ring with it).
        p.evaluate("() => window.__g.focus()")
    p.keyboard.press("ArrowDown")
    info = p.evaluate(
        """() => { const el = document.activeElement; const s = getComputedStyle(el);
          return {fv: el.matches(':focus-visible'), style: s.outlineStyle, w: parseFloat(s.outlineWidth)}; }"""
    )
    if p.context.browser.browser_type.name == "webkit" and not info["fv"]:
        # WebKit does not report :focus-visible for a script-reached radio after
        # an arrow key, so assert the shipped rule itself instead.
        rule = p.evaluate(
            """() => { for (const sh of document.styleSheets) { let rules; try { rules = sh.cssRules; } catch (e) { continue; }
              const walk = (list) => { for (const r of list) { if (r.cssRules && !r.selectorText) { const f = walk(r.cssRules); if (f) return f; }
                else if (r.selectorText && r.selectorText.includes('.ui-radio-input:focus-visible')) return r.style.outline; } return null; };
              const found = walk(rules); if (found) return found; } return null; }"""
        )
        assert rule and "2px solid" in rule
        return
    assert info["fv"] is True and info["style"] != "none" and info["w"] >= 2


def test_forced_colors_keep_checked_card_distinguishable(engine_page: Page) -> None:
    if engine_page.context.browser.browser_type.name != "chromium":
        pytest.skip(
            "WebKit has no forced-colors emulation in Playwright; asserted in chromium only"
        )
    _mount(engine_page)
    engine_page.emulate_media(forced_colors="active")
    out = engine_page.evaluate(
        """() => { const sig = (v) => { const s = getComputedStyle(window.__g.input(v).closest('.ui-radio-option'));
            return [s.borderTopStyle, s.borderTopColor, s.borderTopWidth].join('|'); };
          return {on: sig('b'), off: sig('a')}; }"""
    )
    assert out["on"] != out["off"]
    assert out["on"].startswith("solid|")


def test_destroy_removes_the_listener(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__g.destroy()")
    p.get_by_role("radio", name="Alpha").click()
    p.get_by_role("radio", name="Gamma").focus()
    p.keyboard.press("ArrowUp")
    assert p.evaluate("() => window.__ch") == []
    assert p.evaluate("() => document.contains(window.__g.el)") is True


def test_validation_throws(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    assert (
        _throws(p, "App.ui.radioGroup({options: [{value: 'a', label: 'A'}]})")
        == "App.ui.radioGroup: legend is required"
    )
    assert _throws(p, "App.ui.radioGroup({legend: 'L', options: []})") != ""
    assert _throws(p, "App.ui.radioGroup({legend: 'L'})") != ""
    assert _throws(p, "App.ui.radioGroup({legend: 'L', options: [{label: 'A'}]})") != ""
    assert _throws(p, "App.ui.radioGroup({legend: 'L', options: [{value: 'a'}]})") != ""
    assert (
        _throws(
            p,
            "App.ui.radioGroup({legend: 'L', options: [{value: 'a', label: 'A'}, {value: 'a', label: 'B'}]})",
        )
        == "App.ui.radioGroup: duplicate value"
    )
