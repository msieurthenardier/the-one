# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.changeTable`` (M36 F2 L6, flight DD6): the
label / Now / Proposed table of the GleepGlorp proposal card. Chromium and WebKit through
``engine_page`` + ``load_harness`` (no app spawn); falls in the ``contracts-chat`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

LONG = "word " * 60  # 300 characters, over the default clamp of 160


def _mount(page: Page, opts: dict) -> None:
    load_harness(page)
    page.evaluate(
        """(opts) => {
          window.__t = App.ui.changeTable(Object.assign({testid: 't-root'}, opts));
          document.getElementById('harness-root').appendChild(__t.el);
        }""",
        opts,
    )


def test_one_column_has_label_cells_and_no_header_row(engine_page: Page) -> None:
    _mount(
        engine_page,
        {"rows": [{"label": "Name", "proposed": "Digest"}, {"label": "Model", "proposed": "m1"}]},
    )
    out = engine_page.evaluate(
        """() => ({
          tag: __t.el.tagName, tid: __t.el.getAttribute('data-testid'),
          thead: __t.el.querySelectorAll('thead').length,
          rowHeads: Array.from(__t.el.querySelectorAll('tbody th')).map(th => th.scope + ':' + th.textContent),
          cells: Array.from(__t.el.querySelectorAll('tbody tr')).map(tr => tr.children.length),
          cols: __t.el.getAttribute('data-columns')
        })"""
    )
    assert out["tag"] == "TABLE" and out["tid"] == "t-root" and out["cols"] == "1"
    assert out["thead"] == 0
    assert out["rowHeads"] == ["row:Name", "row:Model"]
    assert out["cells"] == [2, 2]


def test_two_columns_and_headers_are_column_headers(engine_page: Page) -> None:
    _mount(
        engine_page,
        {
            "columns": 2,
            "headers": ["Now", "Proposed"],
            "caption": "Current and proposed values",
            "rows": [{"label": "MCP servers", "now": "None", "proposed": "GitHub"}],
        },
    )
    page = engine_page
    out = page.evaluate(
        """() => ({
          heads: Array.from(__t.el.querySelectorAll('thead th')).map(th => th.scope + ':' + th.textContent),
          caption: __t.el.querySelector('caption').textContent,
          captionHidden: __t.el.querySelector('caption').classList.contains('visually-hidden'),
          cells: Array.from(__t.el.querySelectorAll('tbody td')).map(td => td.textContent)
        })"""
    )
    assert out["heads"] == ["col:Field", "col:Now", "col:Proposed"]
    assert out["caption"] == "Current and proposed values" and out["captionHidden"] is True
    assert out["cells"] == ["None", "GitHub"]
    # The accessible structure: a row header and both column headers name each value cell.
    expect(page.get_by_role("rowheader", name="MCP servers")).to_have_count(1)
    expect(page.get_by_role("columnheader", name="Proposed")).to_have_count(1)


def test_now_column_is_quieter_than_proposed(engine_page: Page) -> None:
    _mount(
        engine_page,
        {
            "columns": 2,
            "headers": ["Now", "Proposed"],
            "rows": [{"label": "A", "now": "x", "proposed": "y"}],
        },
    )
    colours = engine_page.evaluate(
        """() => {
          const tds = __t.el.querySelectorAll('tbody td');
          const probe = (v) => { const s = document.createElement('span'); s.style.color = v;
            document.getElementById('harness-root').appendChild(s); return getComputedStyle(s).color; };
          return {now: getComputedStyle(tds[0]).color, proposed: getComputedStyle(tds[1]).color,
                  secondary: probe('var(--fg-secondary)'), fg: probe('var(--fg)')};
        }"""
    )
    assert colours["now"] == colours["secondary"] and colours["proposed"] == colours["fg"]


def test_a_long_value_is_clamped_and_show_all_reveals_it(engine_page: Page) -> None:
    page = engine_page
    _mount(page, {"rows": [{"label": "Prompt", "proposed": LONG}]})
    more = page.get_by_test_id("t-root-more")
    expect(more).to_have_count(1)
    expect(more).to_have_accessible_name("Show all Prompt")
    assert more.get_attribute("aria-expanded") == "false"
    shown = page.evaluate("() => __t.el.querySelector('.ui-change-table-text').textContent")
    assert shown == LONG[:160] + "…"
    more.click()
    assert more.get_attribute("aria-expanded") == "true"
    assert page.evaluate("() => __t.el.querySelector('.ui-change-table-text').textContent") == LONG
    expect(more).to_have_accessible_name("Show less Prompt")
    more.click()
    assert more.get_attribute("aria-expanded") == "false"
    assert page.evaluate("() => __t.el.querySelector('.ui-change-table-text').textContent") == shown


def test_two_long_values_in_one_row_have_distinct_names_and_testids(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        {
            "columns": 2,
            "headers": ["Now", "Proposed"],
            "rows": [{"label": "Prompt", "now": LONG, "proposed": LONG + "x"}],
        },
    )
    now = page.get_by_test_id("t-root-more-now")
    proposed = page.get_by_test_id("t-root-more-proposed")
    expect(now).to_have_count(1)
    expect(proposed).to_have_count(1)
    expect(now).to_have_accessible_name("Show all Prompt (now)")
    expect(proposed).to_have_accessible_name("Show all Prompt (proposed)")
    assert now.get_attribute("data-column") == "now"
    assert proposed.get_attribute("data-column") == "proposed"
    now.click()
    expect(now).to_have_accessible_name("Show less Prompt (now)")
    expect(proposed).to_have_accessible_name("Show all Prompt (proposed)")
    assert proposed.get_attribute("aria-expanded") == "false"
    proposed.click()
    expect(proposed).to_have_accessible_name("Show less Prompt (proposed)")
    expect(now).to_have_accessible_name("Show less Prompt (now)")


def test_show_all_works_from_the_keyboard(engine_page: Page) -> None:
    page = engine_page
    _mount(page, {"rows": [{"label": "Prompt", "proposed": LONG}]})
    page.evaluate("() => __t.el.querySelector('button').focus()")
    page.keyboard.press("Enter")
    assert page.get_by_test_id("t-root-more").get_attribute("aria-expanded") == "true"
    page.keyboard.press("Space")
    assert page.get_by_test_id("t-root-more").get_attribute("aria-expanded") == "false"


def test_a_short_value_and_a_custom_clamp(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        {
            "clampChars": 10,
            "rows": [
                {"label": "Short", "proposed": "0123456789"},
                {"label": "Long", "proposed": "0123456789A"},
            ],
        },
    )
    assert page.get_by_test_id("t-root-more").count() == 1
    assert (
        page.evaluate("() => __t.el.querySelectorAll('tbody tr')[0].querySelector('button')")
        is None
    )


def test_set_replaces_the_rows_in_the_same_table(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        {
            "columns": 2,
            "headers": ["Now", "Proposed"],
            "rows": [{"label": "A", "now": "1", "proposed": "2"}],
        },
    )
    page.evaluate("() => { window.__same = __t.el; }")
    page.evaluate(
        "() => __t.set({rows: [{label: 'B', now: '3', proposed: '4'}, {label: 'C', now: '5', proposed: '6'}]})"
    )
    out = page.evaluate(
        """() => ({same: __t.el === window.__same,
          labels: Array.from(__t.el.querySelectorAll('tbody th')).map(t => t.textContent),
          heads: __t.el.querySelectorAll('thead th').length, cols: __t.el.getAttribute('data-columns')})"""
    )
    assert out == {"same": True, "labels": ["B", "C"], "heads": 3, "cols": "2"}
    page.evaluate("() => __t.set({columns: 1, headers: null, rows: [{label: 'D', proposed: 'x'}]})")
    out = page.evaluate(
        "() => ({heads: __t.el.querySelectorAll('thead').length, cells: __t.el.querySelectorAll('tbody td').length})"
    )
    assert out == {"heads": 0, "cells": 1}


def test_values_are_text_never_html(engine_page: Page) -> None:
    page = engine_page
    payload = '<img src=x onerror="window.__pwned = 1"><script>window.__pwned = 2</script>'
    _mount(
        page, {"rows": [{"label": "<b>Label</b>", "proposed": payload}], "caption": "<i>cap</i>"}
    )
    out = page.evaluate(
        """() => ({imgs: __t.el.querySelectorAll('img, script, b, i').length,
                   text: __t.el.querySelector('td').textContent, pwned: window.__pwned || null,
                   label: __t.el.querySelector('th').textContent})"""
    )
    assert out["imgs"] == 0 and out["pwned"] is None
    assert out["text"] == payload and out["label"] == "<b>Label</b>"


def test_mono_values_and_an_unknown_column_count(engine_page: Page) -> None:
    page = engine_page
    _mount(page, {"rows": [{"label": "Model", "proposed": "claude-x", "mono": True}]})
    mono = page.evaluate(
        "() => ({cls: __t.el.querySelector('td').className, family: getComputedStyle(__t.el.querySelector('td')).fontFamily})"
    )
    assert "ui-change-table-value--mono" in mono["cls"] and "mono" in mono["family"].lower()
    err = page.evaluate(
        "() => { try { App.ui.changeTable({columns: 3}); return null; } catch (e) { return e.message; } }"
    )
    assert err is not None and "columns" in err


def test_long_unbroken_values_stay_inside_a_narrow_table(engine_page: Page) -> None:
    page = engine_page
    _mount(page, {"rows": [{"label": "Prompt", "proposed": "x" * 120}]})
    page.evaluate("() => { document.getElementById('harness-root').style.width = '300px'; }")
    over = page.evaluate("() => __t.el.scrollWidth > __t.el.clientWidth + 1")
    assert over is False
    assert json.dumps(page.evaluate("() => __t.el.getBoundingClientRect().width <= 300")) == "true"
