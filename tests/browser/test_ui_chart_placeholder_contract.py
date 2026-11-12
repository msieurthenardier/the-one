# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.chart.placeholder`` and
``App.ui.thinking.dots`` (M35 F1 L1, flight DD8): the card that holds a streaming chart's place
(label, dots, glimmering title and plot shaped by the chart type, a "Show source" disclosure),
and the reusable spinner dots it shares with ``App.ui.thinking``. Chromium and WebKit through
``engine_page`` + ``load_harness`` (no app spawn); falls in the ``contracts-chat`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

COUNT_JS = """() => {
  window.__live = new Set();
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  window.setInterval = (fn, ms) => { const id = si(fn, ms); window.__live.add(id); return id; };
  window.clearInterval = (id) => { window.__live.delete(id); ci(id); };
}"""

SHAPES = {
    "bar": "bars",
    "line": "line",
    "area": "line",
    "scatter": "line",
    "pie": "disc",
    "sparkline": "row",
}


def _load(page: Page, reduced: bool = False, clock: bool = False) -> None:
    page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
    if clock:
        page.clock.install()
    load_harness(page)
    page.evaluate(COUNT_JS)


def _mount(page: Page, opts: str = "{}") -> None:
    page.evaluate(
        """(opts) => {
          window.__p = App.ui.chart.placeholder(Object.assign({testid: 'ph'}, opts));
          document.getElementById('harness-root').appendChild(__p.el);
        }""",
        json.loads(opts),
    )


def _shape(page: Page) -> str:
    return page.evaluate(
        "() => __p.el.querySelector('.ui-chart-ph-shape').getAttribute('data-shape')"
    )


def test_structure_label_dots_and_source_disclosure(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    root = page.get_by_test_id("ph")
    expect(root.locator(".ui-chart-ph-label")).to_have_text("Rendering chart")
    # no live region of its own: the chat log announces it (notice convention)
    assert root.locator('[role="status"], [aria-live]').count() == 0
    dots = root.locator(".ui-thinking-dots")
    assert dots.get_attribute("aria-hidden") == "true"
    assert root.locator(".ui-chart-ph-title.ui-chart-ph-glimmer").count() == 1
    assert _shape(page) == "generic"
    source = page.get_by_test_id("ph-source")
    assert source.evaluate("el => el.tagName") == "DETAILS"
    assert source.evaluate("el => el.open") is False
    assert source.locator("summary").text_content() == "Show source"
    assert source.locator("pre").count() == 1


@pytest.mark.parametrize("kind,shape", sorted(SHAPES.items()))
def test_the_plot_is_shaped_by_the_type(engine_page: Page, kind: str, shape: str) -> None:
    page = engine_page
    _load(page)
    _mount(page, f'{{"type": "{kind}"}}')
    assert _shape(page) == shape
    expect(page.get_by_test_id("ph").locator(".ui-chart-ph-label")).to_have_text(
        f"Rendering {kind} chart"
    )
    assert page.get_by_test_id("ph").get_attribute("data-type") == kind


def test_set_type_swaps_in_place_once_per_real_change(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    page.evaluate(
        "() => { window.__slot = __p.el.querySelector('.ui-chart-ph-shape'); window.__root = __p.el; }"
    )
    page.evaluate("() => __p.setType('bar')")
    assert _shape(page) == "bars"
    assert page.evaluate(
        "() => __p.el === __root && __p.el.querySelector('.ui-chart-ph-shape') !== __slot"
    )
    page.evaluate(
        "() => { window.__bars = __p.el.querySelector('.ui-chart-ph-shape'); __p.setType('bar'); }"
    )
    assert page.evaluate("() => __p.el.querySelector('.ui-chart-ph-shape') === __bars")
    # line, area and scatter share a shape: switching between them keeps the nodes
    page.evaluate("() => __p.setType('line')")
    assert _shape(page) == "line"
    page.evaluate(
        "() => { window.__line = __p.el.querySelector('.ui-chart-ph-shape'); __p.setType('area'); }"
    )
    assert page.evaluate("() => __p.el.querySelector('.ui-chart-ph-shape') === __line")
    expect(page.get_by_test_id("ph").locator(".ui-chart-ph-label")).to_have_text(
        "Rendering area chart"
    )
    for bad in ("'donut'", "null", "undefined", "5"):
        page.evaluate(f"() => __p.setType({bad})")
        assert _shape(page) == "generic"
        expect(page.get_by_test_id("ph").locator(".ui-chart-ph-label")).to_have_text(
            "Rendering chart"
        )


def test_set_source_updates_the_code_well_in_place(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    page.evaluate(
        "() => { window.__pre = __p.el.querySelector('pre'); __p.setSource('{\"type\": \"ba'); }"
    )
    assert page.get_by_test_id("ph-source").locator("pre").text_content() == '{"type": "ba'
    page.evaluate('() => __p.setSource(\'{"type": "bar", "x"\')')
    assert page.evaluate("() => __p.el.querySelector('pre') === __pre")
    assert page.get_by_test_id("ph-source").locator("pre").text_content() == '{"type": "bar", "x"'
    page.evaluate("() => __p.setSource(null)")
    assert page.get_by_test_id("ph-source").locator("pre").text_content() == ""
    page.evaluate("() => __p.setSource('<b>x</b>')")
    assert page.get_by_test_id("ph-source").locator("pre b").count() == 0


def test_source_testid_can_be_overridden(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page, '{"sourceTestid": "custom-source"}')
    assert page.get_by_test_id("custom-source").count() == 1
    assert page.get_by_test_id("ph-source").count() == 0


def test_glimmer_animates_and_reduced_motion_makes_it_static(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page, '{"type": "bar"}')
    read = "() => [...document.querySelectorAll('.ui-chart-ph-glimmer')].map(n => getComputedStyle(n).animationName)"
    names = page.evaluate(read)
    assert len(names) >= 2 and set(names) == {"ui-chart-glimmer"}
    assert page.evaluate("() => __live.size") == 1
    page.emulate_media(reduced_motion="reduce")
    assert set(page.evaluate(read)) == {"none"}


def test_reduced_motion_dots_are_static_with_no_interval(engine_page: Page) -> None:
    page = engine_page
    _load(page, reduced=True, clock=True)
    _mount(page)
    assert page.evaluate("() => __live.size") == 0
    page.clock.run_for(500)
    assert page.evaluate("() => __p.el.querySelector('.ui-thinking-dots').textContent") == " …"


def test_destroy_stops_the_dots_removes_nothing_and_is_idempotent(engine_page: Page) -> None:
    page = engine_page
    _load(page, clock=True)
    _mount(page)
    page.clock.run_for(130)
    assert page.evaluate("() => __live.size") == 1
    page.evaluate("() => { __p.destroy(); __p.destroy(); }")
    assert page.evaluate("() => __live.size") == 0
    assert page.evaluate("() => __p.el.isConnected") is True
    page.evaluate("() => __p.setType('pie')")  # a destroyed placeholder ignores updates
    assert _shape(page) == "generic"


def test_detaching_the_placeholder_stops_its_interval(engine_page: Page) -> None:
    page = engine_page
    _load(page, clock=True)
    _mount(page)
    page.clock.run_for(130)
    assert page.evaluate("() => __live.size") == 1
    page.evaluate("() => __p.el.remove()")
    page.clock.run_for(130)
    assert page.evaluate("() => __live.size") == 0


# --- App.ui.thinking.dots (the factored piece) ---------------------------------------------


def test_dots_is_a_standalone_piece_with_one_interval_each(engine_page: Page) -> None:
    page = engine_page
    _load(page, clock=True)
    page.evaluate(
        """() => {
          window.__a = App.ui.thinking.dots();
          window.__b = App.ui.thinking.dots();
          document.getElementById('harness-root').append(__a.el, __b.el);
        }"""
    )
    assert page.evaluate("() => __live.size") == 2
    assert page.evaluate(
        "() => [__a.el.className, __a.el.getAttribute('aria-hidden'), __a.el.tagName]"
    ) == [
        "ui-thinking-dots",
        "true",
        "SPAN",
    ]
    before = page.evaluate("() => __a.el.textContent")
    page.clock.run_for(130)
    after = page.evaluate("() => __a.el.textContent")
    assert after.startswith(" ") and after.strip() and after != before
    page.evaluate("() => { __a.destroy(); __a.destroy(); }")
    assert page.evaluate("() => __live.size") == 1
    assert page.evaluate("() => __a.el.isConnected") is True
    page.evaluate("() => __b.el.remove()")
    page.clock.run_for(130)
    assert page.evaluate("() => __live.size") == 0


def test_dots_never_attached_keep_ticking_and_reduced_motion_is_static(engine_page: Page) -> None:
    page = engine_page
    _load(page, clock=True)
    page.evaluate("() => { window.__d = App.ui.thinking.dots(); }")
    page.clock.run_for(500)
    assert page.evaluate("() => __live.size") == 1
    _load(page, reduced=True, clock=True)
    page.evaluate("() => { window.__d = App.ui.thinking.dots(); }")
    assert page.evaluate("() => __live.size") == 0
    assert page.evaluate("() => __d.el.textContent") == " …"


def test_custom_label_and_source_label(engine_page: Page) -> None:
    """M35 F2 L2: `label` and `sourceLabel` replace the chart defaults; a type still sniffs."""
    page = engine_page
    _load(page)
    _mount(page, '{"label": "Building widget", "sourceLabel": "Widget source"}')
    root = page.get_by_test_id("ph")
    expect(root.locator(".ui-chart-ph-label")).to_have_text("Building widget")
    # the code well names itself only once it overflows: fill it past its short height
    page.evaluate("() => __p.setSource(Array(200).fill('line').join('\\n'))")
    expect(root.locator("pre")).to_have_attribute("aria-label", "Widget source")
    # an explicit label wins over the type-derived one
    page.evaluate("() => __p.setType('bar')")
    expect(root.locator(".ui-chart-ph-label")).to_have_text("Building widget")
    assert _shape(page) == "bars"


def test_generic_shape_ignores_the_type(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page, '{"shape": "generic", "label": "Building widget"}')
    assert _shape(page) == "generic"
    page.evaluate("() => { window.__slot = __p.el.querySelector('.ui-chart-ph-shape'); }")
    for kind in ("'bar'", "'pie'", "'line'", "null"):
        page.evaluate(f"() => __p.setType({kind})")
        assert _shape(page) == "generic"
        assert page.evaluate("() => __p.el.querySelector('.ui-chart-ph-shape') === __slot")
        expect(page.get_by_test_id("ph").locator(".ui-chart-ph-label")).to_have_text(
            "Building widget"
        )
    assert page.get_by_test_id("ph").get_attribute("data-type") is None
    # even a typed generic placeholder never sniffs a chart type
    _mount(page, '{"shape": "generic", "type": "pie"}')
    assert _shape(page) == "generic"


def test_dots_style_does_not_depend_on_the_thinking_root(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(
        """() => {
          window.__d = App.ui.thinking.dots();
          document.getElementById('harness-root').appendChild(__d.el);
          window.__t = App.ui.thinking({testid: 't'});
          document.getElementById('harness-root').appendChild(__t.el);
        }"""
    )
    style = "(el) => { const s = getComputedStyle(el); return [s.display, s.fontSize]; }"
    alone = page.evaluate(f"() => ({style})(__d.el)")
    inside = page.evaluate(f"() => ({style})(__t.el.querySelector('.ui-thinking-dots'))")
    assert alone == inside
    assert alone[0] == "inline"
    assert page.evaluate("() => __t.el.querySelectorAll('.ui-thinking-dots').length") == 1
