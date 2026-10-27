# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.telemetry`` (M31 F6 L04, flight DD4): the
context-usage readout. Role and name, ``update`` / ``setMax`` / ``reset``, the thresholds (a
pair, and a function that changes between updates), focus expansion and the resting
opacity. Chromium and WebKit through ``engine_page`` + ``load_harness``; falls in the
``contracts-chat`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

READ_JS = """() => {
  const q = (s) => __t.el.querySelector(s);
  const vals = Array.from(__t.el.querySelectorAll('.ui-telemetry-details .ui-telemetry-value')).map((n) => n.textContent);
  return {vals, pct: q('.ui-telemetry-pct').textContent, pctClass: q('.ui-telemetry-pct').className,
          barWidth: q('.ui-telemetry-bar').style.width, barClass: q('.ui-telemetry-bar').className,
          name: __t.el.getAttribute('aria-label')};
}"""


def _mount(page: Page, js_opts: str = "{}") -> None:
    load_harness(page)
    page.evaluate(
        """(src) => {
          window.__t = App.ui.telemetry(Object.assign({testid: 'tl-root'}, eval('(' + src + ')')));
          document.getElementById('harness-root').appendChild(__t.el);
        }""",
        js_opts,
    )


def test_role_name_tab_stop_and_initial_state(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    root = page.get_by_role("status", name="Token usage")
    expect(root).to_have_count(1)
    expect(root).to_have_attribute("tabindex", "0")
    out = page.evaluate(READ_JS)
    assert (
        out["vals"] == ["0", "0", "0", "0"] and out["pct"] == "0%" and out["barWidth"] in ("", "0%")
    )
    assert out["pctClass"] == "ui-telemetry-pct"
    assert (
        page.evaluate("() => __t.el.querySelectorAll('.ui-telemetry-row[aria-hidden=true]').length")
        == 4
    )
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement === __t.el") is True


def test_update_formats_tokens_and_sets_bar_and_name(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        "() => __t.update({input_tokens: 1234, output_tokens: 2500000, context_tokens: 500, max_context_tokens: 1000})"
    )
    out = page.evaluate(READ_JS)
    assert out["vals"] == ["1.2k", "2.5M", "500", "1.0k"]
    assert out["pct"] == "50%" and out["barWidth"] == "50%"
    assert out["name"] == "Token usage: 50% of context"
    assert page.evaluate("() => App.ui.telemetry.formatTokens(999)") == "999"


def test_warn_and_crit_states_carry_a_non_colour_phrase(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("() => __t.update({context_tokens: 75, max_context_tokens: 100})")
    out = page.evaluate(READ_JS)
    assert out["pctClass"].endswith("ui-telemetry-pct--warn") and out["barClass"].endswith(
        "ui-telemetry-bar--warn"
    )
    assert out["name"] == "Token usage: 75% of context, approaching limit"
    page.evaluate("() => __t.update({context_tokens: 95, max_context_tokens: 100})")
    out = page.evaluate(READ_JS)
    assert out["pctClass"].endswith("ui-telemetry-pct--crit") and out["barClass"].endswith(
        "ui-telemetry-bar--crit"
    )
    assert out["name"] == "Token usage: 95% of context, context nearly full"


def test_thresholds_pair_and_a_function_read_on_every_update(engine_page: Page) -> None:
    page = engine_page
    _mount(page, "{thresholds: {warn: 10, crit: 20}}")
    page.evaluate("() => __t.update({context_tokens: 15, max_context_tokens: 100})")
    assert page.evaluate(READ_JS)["pctClass"].endswith("--warn")
    _mount(page, "{thresholds: () => window.__th}")
    page.evaluate(
        "() => { window.__th = {warn: 70, crit: 90}; __t.update({context_tokens: 50, max_context_tokens: 100}); }"
    )
    assert page.evaluate(READ_JS)["pctClass"].endswith("ui-telemetry-pct")
    page.evaluate(
        "() => { window.__th = {warn: 40, crit: 45}; __t.update({context_tokens: 50, max_context_tokens: 100}); }"
    )
    assert page.evaluate(READ_JS)["pctClass"].endswith("--crit")
    page.evaluate(
        "() => { window.__th = undefined; __t.update({context_tokens: 95, max_context_tokens: 100}); }"
    )
    assert page.evaluate(READ_JS)["pctClass"].endswith(
        "--crit"
    )  # missing thresholds fall back to 70 / 90


def test_set_max_touches_only_max_and_percentage(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        "() => __t.update({input_tokens: 10, output_tokens: 20, context_tokens: 50, max_context_tokens: 0})"
    )
    assert page.evaluate(READ_JS)["pct"] == "0%"
    page.evaluate("() => __t.setMax(200)")
    out = page.evaluate(READ_JS)
    assert (
        out["vals"] == ["10", "20", "50", "200"]
        and out["pct"] == "25%"
        and out["barWidth"] == "25%"
    )
    page.evaluate("() => __t.setMax(0)")  # degenerate: no maximum
    out = page.evaluate(READ_JS)
    assert (
        out["vals"][3] == "0" and out["pct"] == "0%" and out["name"] == "Token usage: 0% of context"
    )
    page.evaluate("() => __t.setMax(40)")  # more context than the window caps at 100
    assert page.evaluate(READ_JS)["pct"] == "100%"


def test_reset_zeroes_everything_and_the_name(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        "() => __t.update({input_tokens: 10, output_tokens: 20, context_tokens: 95, max_context_tokens: 100})"
    )
    page.evaluate("() => __t.reset()")
    out = page.evaluate(READ_JS)
    assert (
        out["vals"] == ["0", "0", "0", "0"] and out["pct"] == "0%" and out["barWidth"] in ("", "0%")
    )
    assert out["name"] == "Token usage: 0% of context" and out["barClass"] == "ui-telemetry-bar"
    page.evaluate("() => __t.setMax(100)")  # reset also forgot the retained context count
    assert page.evaluate(READ_JS)["pct"] == "0%"


def test_update_with_missing_fields_and_no_data(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("() => { __t.update({input_tokens: 5}); __t.update(null); }")
    out = page.evaluate(READ_JS)
    assert out["vals"] == ["5", "0", "0", "0"]


def test_focus_expands_the_details_and_lifts_the_opacity(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        "() => __t.update({input_tokens: 1, output_tokens: 2, context_tokens: 3, max_context_tokens: 10})"
    )
    state = "() => { const d = __t.el.querySelector('.ui-telemetry-details'); return [getComputedStyle(__t.el).opacity, getComputedStyle(d).opacity, d.getBoundingClientRect().width]; }"
    rest = page.evaluate(state)
    assert rest[0] == "0.7" and rest[1] == "0" and rest[2] == 0
    page.evaluate("() => __t.el.focus()")
    page.wait_for_function(
        "() => getComputedStyle(__t.el).opacity === '1' && getComputedStyle(__t.el.querySelector('.ui-telemetry-details')).opacity === '1'"
    )
    assert page.evaluate(state)[2] > 0
    page.evaluate("() => __t.el.blur()")
    page.wait_for_function("() => getComputedStyle(__t.el).opacity === '0.7'")


def test_destroy_makes_every_method_a_no_op_and_is_idempotent(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        "() => { __t.update({input_tokens: 7}); __t.destroy(); __t.destroy(); __t.update({input_tokens: 9}); __t.setMax(5); __t.reset(); }"
    )
    assert page.evaluate(READ_JS)["vals"][0] == "7"
    assert page.evaluate("() => __t.el.isConnected") is True


def test_inside_a_narrow_row_it_does_not_overflow(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          const row = document.createElement('div');
          row.style.cssText = 'display: flex; justify-content: flex-end; width: 400px;';
          window.__t = App.ui.telemetry({testid: 'tl-root'});
          row.appendChild(__t.el);
          document.getElementById('harness-root').appendChild(row);
          __t.update({input_tokens: 999999999, output_tokens: 999999999, context_tokens: 999999999, max_context_tokens: 1000000000});
          __t.el.focus();
          window.__row = row;
        }"""
    )
    page.wait_for_function(
        "() => getComputedStyle(__t.el.querySelector('.ui-telemetry-details')).opacity === '1'"
    )
    assert page.evaluate("() => __row.scrollWidth <= __row.clientWidth + 1") is True
    assert json.dumps(page.evaluate("() => __t.el.getAttribute('data-testid')")) == '"tl-root"'
