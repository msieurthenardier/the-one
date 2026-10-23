# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.clearableInput`` (M31 F3 L03b, squawk 0100):
a text input with an explicit in-field clear button.

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

MOUNT = """() => {
  window.__ev = {input: 0, clear: 0, doc: 0};
  window.__c = App.ui.clearableInput({label: 'Filter', testid: 'ci', clearTestid: 'ci-x',
    onClear: () => { window.__ev.clear += 1; }, onInput: () => { window.__ev.input += 1; }});
  const f = App.ui.field({label: 'Filter', control: __c.input, host: __c.el, labelHidden: false});
  document.getElementById('harness-root').appendChild(f.el);
  document.addEventListener('keydown', () => { window.__ev.doc += 1; });
  return true;
}"""


def _mount(page: Page) -> None:
    load_harness(page)
    page.evaluate(MOUNT)


def test_clear_button_visibility_and_name(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    x = page.get_by_test_id("ci-x")
    expect(x).to_be_hidden()
    page.get_by_test_id("ci").press_sequentially("abc")
    expect(x).to_be_visible()
    expect(page.get_by_role("button", name="Clear Filter")).to_have_count(1)
    expect(page.get_by_role("textbox", name="Filter")).to_have_count(1)
    out = page.evaluate(
        "() => [__c.input.type, __c.input.className, __c.el.className, __c.button.type]"
    )
    assert out == ["text", "field-input ui-clearable-input", "ui-clearable", "button"]
    page.evaluate("() => __c.setValue('x')")
    expect(x).to_be_visible()
    page.evaluate("() => __c.setValue('')")
    expect(x).to_be_hidden()


def test_pointer_click_clears_fires_input_once_and_keeps_focus(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.get_by_test_id("ci").press_sequentially("abc")
    page.evaluate("() => { window.__ev.input = 0; return true; }")
    page.get_by_test_id("ci-x").click()
    out = page.evaluate(
        "() => ({v: __c.input.value, ev: __ev, focus: document.activeElement === __c.input, hidden: __c.button.hidden})"
    )
    assert out["v"] == "" and out["focus"] is True and out["hidden"] is True
    assert out["ev"]["input"] == 1 and out["ev"]["clear"] == 1


def test_escape_clears_when_text_and_passes_through_when_empty(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    inp = page.get_by_test_id("ci")
    inp.press_sequentially("abc")
    page.evaluate("() => { window.__ev.doc = 0; window.__ev.input = 0; return true; }")
    inp.press("Escape")
    out = page.evaluate(
        "() => ({v: __c.input.value, ev: __ev, focus: document.activeElement === __c.input})"
    )
    assert out["v"] == "" and out["focus"] is True
    assert out["ev"] == {"input": 1, "clear": 1, "doc": 0}
    inp.press("Escape")
    assert page.evaluate("() => __ev.doc") == 1
    assert page.evaluate("() => __ev.clear") == 1


def test_escape_during_composition_does_not_clear(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.get_by_test_id("ci").press_sequentially("abc")
    out = page.evaluate(
        """() => {
          const e = new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true, isComposing: true});
          __c.input.dispatchEvent(e);
          return {v: __c.input.value, prevented: e.defaultPrevented};
        }"""
    )
    assert out == {"v": "abc", "prevented": False}


def test_no_overlap_height_parity_and_tab_order(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        """() => {
          const plain = App.ui.textInput({testid: 'plain'});
          document.getElementById('harness-root').appendChild(plain);
          __c.setValue('a very long value that would otherwise run under the clear button');
          const after = document.createElement('button'); after.id = 'after'; after.textContent = 'after';
          document.getElementById('harness-root').appendChild(after);
        }"""
    )
    out = page.evaluate(
        """() => {
          const pad = parseFloat(getComputedStyle(__c.input).paddingInlineEnd);
          return {pad, btn: __c.button.getBoundingClientRect().width,
                  h: __c.input.getBoundingClientRect().height,
                  plainH: document.querySelector('[data-testid=plain]').getBoundingClientRect().height};
        }"""
    )
    assert out["pad"] >= out["btn"] > 0
    assert out["h"] == out["plainH"]
    page.get_by_test_id("ci").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement === __c.button") is True
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.getAttribute('data-testid')") == "plain"


def test_destroy_stops_toggling_and_no_document_listeners(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          const calls = [];
          const add = EventTarget.prototype.addEventListener;
          EventTarget.prototype.addEventListener = function (t) {
            if (this === document || this === window || this === document.body) calls.push(t);
            return add.apply(this, arguments);
          };
          window.__calls = calls;
          window.__c = App.ui.clearableInput({label: 'F', testid: 'ci', clearTestid: 'ci-x'});
          document.getElementById('harness-root').appendChild(__c.el);
          EventTarget.prototype.addEventListener = add;
        }"""
    )
    assert page.evaluate("() => __calls.length") == 0
    page.evaluate("() => __c.destroy()")
    page.get_by_test_id("ci").press_sequentially("abc")
    assert page.evaluate("() => __c.button.hidden") is True
