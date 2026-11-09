# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.chart`` (M35 F1 L1, flight DD2-DD5, DD7, DD9):
the format validator against the shared corpus, the number formatters, the drawn chart for
every type and optional key, its structure and accessible names, layout after attach, the
tooltip by pointer and keyboard, the "Show data" table, theme repaint through CSS alone, and the
``block`` entry point. Assertions are about structure, names, classes and table contents; never
pixel positions (text measurement differs by engine and font). Chromium and WebKit through
``engine_page`` + ``load_harness`` (no app spawn); falls in the ``contracts-chat`` lane.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

CORPUS = Path(__file__).resolve().parent.parent / "fixtures" / "charts"
VALID = {p.name: p.read_text(encoding="utf-8") for p in sorted((CORPUS / "valid").glob("*.json"))}
INVALID = {
    p.name: p.read_text(encoding="utf-8")
    for p in sorted((CORPUS / "invalid").glob("*.json"))
    if p.name != "expected.json"
}
EXPECTED = json.loads((CORPUS / "invalid" / "expected.json").read_text(encoding="utf-8"))
NUMBER_ROWS = json.loads((CORPUS / "number-format.json").read_text(encoding="utf-8"))

# One file per type for the structure tests.
TYPE_FILES = {
    "bar": "bar-all-keys.json",
    "line": "line-null-gaps.json",
    "area": "area-stacked.json",
    "scatter": "scatter-log-x-reference.json",
    "pie": "pie-minimal.json",
}

MOUNT_JS = """(args) => {
  const r = App.ui.chart.parse(args.source);
  if (!r.ok) return r.message;
  const frame = document.createElement('div');
  frame.id = 'frame';
  frame.style.width = args.width + 'px';
  window.__c = App.ui.chart({spec: r.spec, testid: 'c'});
  frame.appendChild(__c.el);
  document.getElementById('harness-root').appendChild(frame);
  return null;
}"""


def _mount(page: Page, source: str, width: int = 640, theme: str = "dark") -> None:
    load_harness(page, theme)
    err = page.evaluate(MOUNT_JS, {"source": source, "width": width})
    assert err is None, err


def _laid_out(page: Page) -> None:
    expect(page.locator('[data-testid="c"] svg')).to_have_attribute("data-width", "614")


def test_parse_accepts_every_valid_corpus_file_and_refuses_with_the_exact_sentence(
    engine_page: Page,
) -> None:
    page = engine_page
    load_harness(page)
    results = page.evaluate(
        """(files) => {
          const out = {};
          for (const [name, text] of Object.entries(files)) {
            const r = App.ui.chart.parse(text);
            out[name] = r.ok ? null : r.message;
          }
          return out;
        }""",
        {**VALID, **INVALID},
    )
    for name in VALID:
        assert results[name] is None, f"{name}: {results[name]}"
    for name in INVALID:
        assert results[name] == EXPECTED[name], name


def test_parse_normalises_and_never_throws(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """() => {
          const odd = ['', 'null', '[]', '{', '{}', '"x"', '0', undefined, null, '{"type":null}'];
          const msgs = odd.map(s => App.ui.chart.parse(s).ok);
          const spec = App.ui.chart.parse('{"type":"bar","x":{"values":["a"]},"series":[{"values":[1]}]}').spec;
          return {msgs, stacked: spec.stacked, scale: spec.y.scale, axis: spec.series[0].axis, y2: spec.y2};
        }"""
    )
    assert out["msgs"] == [False] * 10
    assert (out["stacked"], out["scale"], out["axis"], out["y2"]) == (False, "linear", "left", None)


@pytest.mark.parametrize("value,unit,tick,full", NUMBER_ROWS)
def test_number_formatters_match_the_corpus(
    engine_page: Page, value: float, unit: str, tick: str, full: str
) -> None:
    page = engine_page
    if not page.evaluate("() => !!window.App && !!App.ui && !!App.ui.chart"):
        load_harness(page)
    got = page.evaluate(
        "([v, u]) => [App.ui.chart.formatTick(v, u), App.ui.chart.formatFull(v, u)]", [value, unit]
    )
    assert got == [tick, full]


@pytest.mark.parametrize("kind", sorted(TYPE_FILES))
def test_structure_and_names_for_each_type(engine_page: Page, kind: str) -> None:
    page = engine_page
    _mount(page, VALID[TYPE_FILES[kind]])
    _laid_out(page)
    fig = page.get_by_test_id("c")
    assert fig.evaluate("el => el.tagName") == "FIGURE"
    assert page.evaluate("() => __c.el.firstElementChild.tagName") == "FIGCAPTION"
    plot = page.get_by_test_id("c-plot")
    assert plot.get_attribute("role") == "group"
    assert plot.get_attribute("tabindex") == "0"
    name = plot.get_attribute("aria-label")
    assert name.endswith(", chart values")
    desc = plot.get_attribute("aria-describedby")
    assert "arrow keys" in page.locator(f"#{desc}").text_content()
    svg = plot.locator("svg")
    assert svg.get_attribute("role") == "img"
    label = svg.get_attribute("aria-label")
    assert label.lower().startswith(kind), label
    # Text is laid out at its true size: the viewBox is the pixel box, never scaled.
    assert svg.get_attribute("viewBox") == "0 0 614 240"
    # Show data: a closed plain disclosure holding a real table.
    data = page.get_by_test_id("c-data")
    assert data.evaluate("el => el.tagName") == "DETAILS"
    assert data.evaluate("el => el.open") is False
    assert data.locator("summary").text_content() == "Show data"
    assert data.locator("table").count() == 1
    assert data.locator("thead th").count() >= 2


def test_summary_label_for_a_line_chart(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["line-null-gaps.json"])
    _laid_out(page)
    assert (
        page.get_by_test_id("c-plot").locator("svg").get_attribute("aria-label")
        == "Line chart, Sensor readings, 09 to 14, 2 series"
    )
    assert (
        page.get_by_test_id("c-plot").get_attribute("aria-label") == "Sensor readings, chart values"
    )


def test_plot_name_without_a_title(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-minimal.json"])
    _laid_out(page)
    assert page.get_by_test_id("c-plot").get_attribute("aria-label") == "Chart values"


def test_sparkline_is_a_compact_row(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["sparkline-titled-unit.json"])
    fig = page.get_by_test_id("c")
    assert fig.get_attribute("data-chart-type") == "sparkline"
    assert fig.locator("svg").count() == 1
    assert fig.locator("svg").get_attribute("role") == "img"
    assert (
        fig.locator("svg").get_attribute("aria-label")
        == "Sparkline, Daily revenue, from $1,200 to $2,100, 6 values"
    )
    assert fig.locator('[role="group"], details, table, ul.ui-chart-legend').count() == 0
    assert fig.locator("path.ui-chart-spark").count() == 1
    assert int(fig.locator("svg").get_attribute("height")) == 32


def test_minimal_sparkline_has_no_caption(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["sparkline-minimal.json"])
    assert page.get_by_test_id("c").locator("figcaption").count() == 0


def test_legend_rules(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-minimal.json"])  # one unnamed series: no legend
    assert page.get_by_test_id("c").locator(".ui-chart-legend").count() == 0
    _mount(page, VALID["pie-zero-slice.json"])  # a pie lists its slices
    assert page.get_by_test_id("c").locator(".ui-chart-legend-name").all_text_contents() == [
        "Kept",
        "Dropped",
        "Pending",
    ]
    _mount(page, VALID["bar-stacked.json"])
    assert page.get_by_test_id("c").locator(".ui-chart-legend-name").all_text_contents() == [
        "Support",
        "Sales",
        "Billing",
    ]


def test_bars_lines_areas_and_points_are_drawn_and_painted_by_series_classes(
    engine_page: Page,
) -> None:
    page = engine_page
    _mount(page, VALID["bar-stacked.json"])
    _laid_out(page)
    bars = page.get_by_test_id("c").locator("rect.ui-chart-bar")
    assert bars.count() == 8  # 3 + 3 + 3 minus one null
    classes = set()
    for i in range(bars.count()):
        cls = bars.nth(i).get_attribute("class")
        classes.update(c for c in cls.split() if c.startswith("ui-chart-series-"))
    assert classes == {"ui-chart-series-1", "ui-chart-series-2", "ui-chart-series-3"}
    _mount(page, VALID["area-stacked.json"])
    _laid_out(page)
    assert page.get_by_test_id("c").locator("path.ui-chart-area").count() >= 3
    _mount(page, VALID["scatter-minimal.json"])
    _laid_out(page)
    assert page.get_by_test_id("c").locator("circle.ui-chart-point").count() == 5
    _mount(page, VALID["pie-minimal.json"])
    _laid_out(page)
    assert page.get_by_test_id("c").locator(".ui-chart-slice").count() == 4


def test_zero_pie_slice_is_kept_in_the_table_but_not_drawn(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["pie-zero-slice.json"])
    _laid_out(page)
    fig = page.get_by_test_id("c")
    assert fig.locator(".ui-chart-slice").count() == 2
    assert fig.locator("tbody tr").count() == 3
    assert fig.locator("tbody tr").nth(1).locator("td").text_content() == "0"


def test_bar_zero_rule_and_log_scale_ticks(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-minimal.json"])
    _laid_out(page)
    ticks = page.get_by_test_id("c").locator("text.ui-chart-tick").all_text_contents()
    assert "0" in ticks  # bars include 0
    _mount(page, VALID["line-log-scale.json"])
    _laid_out(page)
    ticks = page.get_by_test_id("c").locator("text.ui-chart-tick").all_text_contents()
    for expected in ("1 ms", "10 ms", "100 ms", "1k ms", "10k ms"):
        assert expected in ticks, ticks


def test_dual_axes_have_right_hand_ticks_and_labels(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-all-keys.json"])
    _laid_out(page)
    fig = page.get_by_test_id("c")
    right = fig.locator('text.ui-chart-tick[text-anchor="start"]').all_text_contents()
    assert right and all("%" in t for t in right), right
    labels = fig.locator("text.ui-chart-axis-label").all_text_contents()
    assert "Revenue" in labels and "Margin" in labels and "Quarter" in labels
    # three reference lines (y, y2, x) drawn as dashed ref lines with labels
    assert fig.locator("line.ui-chart-ref").count() == 3
    assert fig.locator("text.ui-chart-ref-label").all_text_contents() == [
        "Target",
        "Margin goal",
        "Launch",
    ]
    # a mixed line series is drawn as a line
    assert fig.locator("path.ui-chart-line").count() == 1


def test_line_series_beyond_the_fourth_get_a_dash_pattern(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["line-many-series-dashes.json"])
    _laid_out(page)
    lines = page.get_by_test_id("c").locator("path.ui-chart-line")
    assert lines.count() == 8
    dashed = [("ui-chart-dash-" in (lines.nth(i).get_attribute("class") or "")) for i in range(8)]
    assert dashed == [False] * 4 + [True] * 4


def test_null_gaps_break_a_line_and_are_empty_table_cells(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["line-null-gaps.json"])
    _laid_out(page)
    fig = page.get_by_test_id("c")
    # North has gaps at hours 10 and 13: three segments, two of them single points
    paths = fig.locator("path.ui-chart-line.ui-chart-series-1")
    assert paths.count() == 1  # only the segment with two or more points draws a path
    cells = fig.locator("tbody tr").nth(1).locator("td").all_text_contents()
    assert cells[0] == ""  # North at 10


def test_table_has_units_and_the_reference_list(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-all-keys.json"])
    _laid_out(page)
    data = page.get_by_test_id("c-data")
    headers = data.locator("thead th").all_text_contents()
    assert headers == ["Quarter", "Revenue", "Margin"]
    first = data.locator("tbody tr").first
    assert first.locator("th").text_content() == "Q1"
    assert first.locator("td").all_text_contents() == ["$120,000", "31 %"]
    assert data.locator("ul.ui-chart-notes li").all_text_contents() == [
        "Reference line: Target, $150,000",
        "Reference line: Margin goal, 35 %",
        "Reference line: Launch, Q3",
    ]
    # the table scrolls in its own bounded box
    wrap = data.locator(".ui-chart-table-wrap")
    assert wrap.evaluate("el => getComputedStyle(el).overflowY") == "auto"


def test_scatter_table_has_a_row_per_point(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["scatter-log-x-reference.json"])
    _laid_out(page)
    data = page.get_by_test_id("c-data")
    assert data.locator("thead th").all_text_contents() == ["Series", "Payload", "Time"]
    assert data.locator("tbody tr").count() == 9


def test_layout_waits_for_attach_and_follows_width_changes(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """(src) => {
          const r = App.ui.chart.parse(src);
          window.__c = App.ui.chart({spec: r.spec, testid: 'c'});  // built detached
          const frame = document.createElement('div');
          frame.id = 'frame';
          frame.style.width = '500px';
          window.__frame = frame;
          document.getElementById('harness-root').appendChild(frame);
        }""",
        VALID["line-minimal.json"],
    )
    page.wait_for_timeout(100)
    assert page.evaluate("() => __c.el.querySelector('svg').getAttribute('data-width')") is None
    page.evaluate("() => __frame.appendChild(__c.el)")
    expect(page.locator('[data-testid="c"] svg')).to_have_attribute("data-width", "474")
    page.evaluate("() => { __frame.style.width = '800px'; }")
    expect(page.locator('[data-testid="c"] svg')).to_have_attribute("data-width", "774")
    assert page.get_by_test_id("c").locator("svg").get_attribute("viewBox") == "0 0 774 240"


def test_zero_width_container_waits_then_draws(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["line-minimal.json"], width=0)
    page.wait_for_timeout(100)
    assert page.evaluate("() => __c.el.querySelector('svg').getAttribute('data-width')") is None
    page.evaluate("() => { document.getElementById('frame').style.width = '400px'; }")
    expect(page.locator('[data-testid="c"] svg')).to_have_attribute("data-width", "374")


def test_destroy_stops_layout_and_is_idempotent(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["line-minimal.json"])
    _laid_out(page)
    page.evaluate("() => { __c.destroy(); __c.destroy(); }")
    page.evaluate("() => { document.getElementById('frame').style.width = '300px'; }")
    page.wait_for_timeout(150)
    assert page.evaluate("() => __c.el.querySelector('svg').getAttribute('data-width')") == "614"
    # destroy before layout is a no-op too
    load_harness(page)
    page.evaluate(
        """(src) => { const c = App.ui.chart({spec: App.ui.chart.parse(src).spec}); c.destroy(); c.destroy(); }""",
        VALID["line-minimal.json"],
    )


RO_PATCH = """() => {
  window.__ro = {observed: 0, disconnected: 0};
  const Orig = window.ResizeObserver;
  window.ResizeObserver = function (cb) {
    const o = new Orig(cb);
    const od = o.disconnect.bind(o), ob = o.observe.bind(o);
    o.disconnect = () => { __ro.disconnected++; od(); };
    o.observe = (t) => { __ro.observed++; ob(t); };
    return o;
  };
}"""


def test_the_observer_is_disconnected_on_destroy(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(RO_PATCH)
    err = page.evaluate(MOUNT_JS, {"source": VALID["line-minimal.json"], "width": 640})
    assert err is None
    _laid_out(page)
    assert page.evaluate("() => __ro.observed") == 1
    assert page.evaluate("() => __ro.disconnected") == 0
    page.evaluate("() => __c.destroy()")
    assert page.evaluate("() => __ro.disconnected") == 1


def test_the_observer_is_disconnected_when_the_drawn_chart_is_detached(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(RO_PATCH)
    err = page.evaluate(MOUNT_JS, {"source": VALID["line-minimal.json"], "width": 640})
    assert err is None
    _laid_out(page)
    page.evaluate("() => document.getElementById('frame').remove()")
    page.wait_for_function("() => __ro.disconnected === 1")


def test_pointer_hover_shows_the_tooltip_with_full_values(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-all-keys.json"])
    _laid_out(page)
    tip = page.get_by_test_id("c-tooltip")
    assert tip.get_attribute("aria-hidden") == "true"
    expect(tip).to_be_hidden()
    box = page.get_by_test_id("c-plot").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.4, box["y"] + 120)
    expect(tip).to_be_visible()
    text = tip.text_content()
    assert "Q" in text and "$" in text and "%" in text
    page.mouse.move(box["x"] - 20, box["y"] - 20)
    expect(tip).to_be_hidden()


def test_live_node_announces_keyboard_reading_only(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-all-keys.json"])
    _laid_out(page)
    live = page.get_by_test_id("c-live")
    assert live.get_attribute("aria-live") == "polite"
    assert live.get_attribute("aria-atomic") == "true"
    assert page.get_by_test_id("c-tooltip").get_attribute("aria-hidden") == "true"
    box = page.get_by_test_id("c-plot").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.4, box["y"] + 120)
    expect(page.get_by_test_id("c-tooltip")).to_be_visible()
    assert live.text_content() == ""
    page.get_by_test_id("c-plot").focus()
    page.keyboard.press("ArrowRight")
    text = live.text_content()
    assert text.startswith("Q2: ") and "$" in text and "%" in text
    page.keyboard.press("Escape")
    assert live.text_content() == ""


def test_keyboard_moves_between_positions(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-all-keys.json"])
    _laid_out(page)
    tip = page.get_by_test_id("c-tooltip")
    page.get_by_test_id("c-plot").focus()
    expect(tip).to_be_visible()
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "Q1"
    assert tip.locator(".ui-chart-tooltip-value").all_text_contents() == ["$120,000", "31 %"]
    page.keyboard.press("ArrowRight")
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "Q2"
    page.keyboard.press("End")
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "Q4"
    page.keyboard.press("ArrowRight")
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "Q4"
    page.keyboard.press("Home")
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "Q1"
    page.keyboard.press("ArrowLeft")
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "Q1"
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    # a null value reads as "No data"
    assert tip.locator(".ui-chart-tooltip-value").all_text_contents()[1] == "No data"
    page.keyboard.press("Escape")
    expect(tip).to_be_hidden()
    page.keyboard.press("ArrowRight")
    expect(tip).to_be_visible()
    page.get_by_test_id("c-plot").blur()
    expect(tip).to_be_hidden()


def test_pie_and_scatter_keyboard_positions(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["pie-minimal.json"])
    _laid_out(page)
    page.get_by_test_id("c-plot").focus()
    tip = page.get_by_test_id("c-tooltip")
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "Firefox"
    assert tip.locator(".ui-chart-tooltip-value").text_content() == "18 % (18%)"
    _mount(page, VALID["scatter-minimal.json"])
    _laid_out(page)
    page.get_by_test_id("c-plot").focus()
    page.keyboard.press("End")
    assert tip.locator(".ui-chart-tooltip-title").text_content() == "5"


def test_series_paint_from_tokens_and_repaint_on_a_theme_change(engine_page: Page) -> None:
    page = engine_page
    _mount(page, VALID["bar-minimal.json"])
    _laid_out(page)
    read = """() => {
      const bar = document.querySelector('[data-testid=c] rect.ui-chart-bar');
      return [getComputedStyle(bar).fill, getComputedStyle(document.getElementById('harness-root')).getPropertyValue('--chart-1').trim()];
    }"""
    dark_fill, dark_token = page.evaluate(read)
    assert dark_token == "#a78bfa"
    assert dark_fill == "rgb(167, 139, 250)"
    page.evaluate(
        "() => document.getElementById('harness-root').setAttribute('data-theme', 'light')"
    )
    light_fill, light_token = page.evaluate(read)
    assert light_token == "#6d28d9"
    assert light_fill == "rgb(109, 40, 217)"
    # the very same nodes repainted: nothing was re-rendered
    assert page.evaluate("() => document.querySelectorAll('[data-testid=c]').length") == 1


def test_block_returns_the_chart_for_a_valid_spec(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """(src) => {
          const node = App.ui.chart.block(src, {testid: 'b', closed: true});
          document.getElementById('harness-root').appendChild(node);
          return [node.tagName, node.getAttribute('data-testid')];
        }""",
        VALID["bar-minimal.json"],
    )
    assert out == ["FIGURE", "b"]


def test_block_error_notice_with_the_source_under_technical_details(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """(src) => {
          document.getElementById('harness-root').appendChild(App.ui.chart.block(src, {testid: 'b'}));
        }""",
        INVALID["series-length-mismatch.json"],
    )
    err = page.get_by_test_id("b-error")
    assert err.get_attribute("class") == "ui-notice ui-notice--danger"
    assert err.locator(".ui-chart-error-head").text_content() == "Couldn't draw this chart."
    assert (
        err.locator(".ui-chart-error-reason").text_content()
        == 'Series "2024" has 11 values, but the x axis has 12.'
    )
    details = err.locator("details")
    assert details.locator("summary").text_content() == "Technical details"
    assert details.evaluate("el => el.open") is False
    assert details.locator("pre").text_content() == INVALID["series-length-mismatch.json"]


def test_block_cut_off_notice_is_muted(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          document.getElementById('harness-root').appendChild(App.ui.chart.block('{"type": "bar", "x": {"val', {testid: 'b', closed: false}));
        }"""
    )
    err = page.get_by_test_id("b-error")
    assert err.get_attribute("class") == "ui-notice ui-notice--muted"
    assert (
        err.locator(".ui-chart-error-head").text_content()
        == "This chart was cut off before it finished."
    )
    assert err.locator(".ui-chart-error-reason").count() == 0
    assert err.locator("details pre").text_content() == '{"type": "bar", "x": {"val'


def test_block_never_throws(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """() => ['', null, undefined, 5, '{"type":"bar"}', '{"type":"bar","x":{"values":["a"]},"series":[{"values":[1]}]}'].map(
          s => { try { return App.ui.chart.block(s).nodeType; } catch (e) { return 'threw: ' + e.message; } })"""
    )
    assert out == [1] * 6


LAYOUT_JS = """(args) => {
  window.__layouts = 0;
  const frame = document.createElement('div');
  frame.id = 'frame';
  frame.style.width = args.width + 'px';
  document.getElementById('harness-root').appendChild(frame);
  window.__b = App.ui.chart.block(args.source, {testid: 'c', onLayout: () => { window.__layouts++; }});
  if (args.attach) frame.appendChild(__b);
  return null;
}"""


def test_on_layout_fires_after_first_layout_and_on_width_changes(engine_page: Page) -> None:
    """AC10: onLayout fires after the first layout and again on a width change, once the figure
    is attached; the root carries the stable data-chart-type."""
    page = engine_page
    load_harness(page)
    page.evaluate(LAYOUT_JS, {"source": VALID["bar-all-keys.json"], "width": 640, "attach": True})
    page.wait_for_function("() => window.__layouts >= 1")
    assert page.get_by_test_id("c").get_attribute("data-chart-type") == "bar"
    first = page.evaluate("() => window.__layouts")
    page.evaluate("() => { document.getElementById('frame').style.width = '420px'; }")
    page.wait_for_function("(n) => window.__layouts > n", arg=first)


def test_on_layout_waits_for_attach_and_is_a_noop_once_detached(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(LAYOUT_JS, {"source": VALID["bar-all-keys.json"], "width": 640, "attach": False})
    page.wait_for_timeout(150)
    assert page.evaluate("() => window.__layouts") == 0
    page.evaluate("() => document.getElementById('frame').appendChild(__b)")
    page.wait_for_function("() => window.__layouts >= 1")
    page.evaluate("() => { __b.remove(); window.__layouts = 0; }")
    page.evaluate("() => { document.getElementById('frame').style.width = '300px'; }")
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__layouts") == 0


def test_on_layout_fires_once_for_a_sparkline(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        LAYOUT_JS,
        {
            "source": '{"type":"sparkline","series":[{"values":[1,3,2,5]}]}',
            "width": 300,
            "attach": True,
        },
    )
    page.wait_for_function("() => window.__layouts >= 1")
    page.wait_for_timeout(150)
    assert page.evaluate("() => window.__layouts") == 1


def test_chart_text_is_never_html(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        '{"type":"bar","title":"<img src=x onerror=alert(1)>","x":{"values":["<b>a</b>"]},"series":[{"name":"<i>s</i>","values":[1]}]}',
    )
    _laid_out(page)
    fig = page.get_by_test_id("c")
    assert fig.locator("img, b, i").count() == 0
    assert "<img" in fig.locator(".ui-chart-title").text_content()
