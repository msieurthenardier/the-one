# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.trace`` (M31 F6 L04, flight DD4), its
``find`` and ``thinking`` sub-entries: the per-turn "Tool activity" disclosure. Roles and
names, keyboard toggling, ``append`` and ``count``, both chevron and count styles, ``find``
re-wrapping a node a previous handle built, and the thinking disclosure. Chromium and
WebKit through ``engine_page`` + ``load_harness``; falls in the ``contracts-chat`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _mount(page: Page, opts: str = "{}") -> None:
    load_harness(page)
    page.evaluate(
        """(opts) => {
          window.__t = App.ui.trace(Object.assign({id: 'm1', testid: 'tr-root'}, opts));
          document.getElementById('harness-root').appendChild(__t.el);
          window.__tool = (text) => {
            const n = document.createElement('div');
            n.className = 'ui-message ui-message--tool';
            n.textContent = text;
            return n;
          };
        }""",
        json.loads(opts),
    )


def test_structure_roles_and_the_accessible_name(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    assert page.evaluate("() => __t.el.className") == "ui-trace"
    assert page.evaluate("() => __t.el.getAttribute('data-parent-msg-id')") == "m1"
    assert page.evaluate("() => __t.el.firstChild.tagName") == "DETAILS"
    assert page.evaluate("() => __t.el.querySelector('summary').className") == "ui-trace-toggle"
    summary = page.get_by_role("group").locator("summary")
    expect(summary).to_have_attribute("aria-label", "Tool activity, 0 items")
    assert (
        page.evaluate("() => __t.el.querySelector('.ui-trace-count').getAttribute('aria-hidden')")
        == "true"
    )
    assert page.evaluate("() => __t.count()") == 0


def test_append_updates_count_and_name_singular_then_plural(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    summary = page.locator("summary")
    page.evaluate("() => __t.append(__tool('one'))")
    expect(summary).to_have_attribute("aria-label", "Tool activity, 1 item")
    expect(page.locator(".ui-trace-count")).to_have_text("1")
    page.evaluate("() => __t.append(__tool('two'))")
    expect(summary).to_have_attribute("aria-label", "Tool activity, 2 items")
    assert page.evaluate("() => __t.count()") == 2
    page.evaluate("() => { __t.append(null); }")  # nothing to append
    assert page.evaluate("() => __t.count()") == 2


def test_keyboard_toggles_the_native_details(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("() => __t.append(__tool('one'))")
    page.locator("summary").focus()
    assert page.evaluate("() => __t.el.querySelector('details').open") is False
    page.keyboard.press("Enter")
    page.wait_for_function("() => __t.el.querySelector('details').open === true")
    page.keyboard.press("Space")
    page.wait_for_function("() => __t.el.querySelector('details').open === false")


def test_dot_count_style_and_a_custom_label(engine_page: Page) -> None:
    page = engine_page
    _mount(page, '{"countStyle": "dot", "label": "Tool activity"}')
    assert page.evaluate("() => __t.el.className") == "ui-trace ui-trace--count-dot"
    assert page.evaluate("() => __t.el.querySelector('.ui-trace-count')") is None
    expect(page.locator(".ui-trace-label")).to_have_text("Tool activity · 0")
    page.evaluate(
        "() => { __t.append(__tool('a')); __t.append(__tool('b')); __t.append(__tool('c')); __t.append(__tool('d')); }"
    )
    expect(page.locator(".ui-trace-label")).to_have_text("Tool activity · 4")
    # the accessible name is the same either way
    expect(page.locator("summary")).to_have_attribute("aria-label", "Tool activity, 4 items")


def test_icon_chevron_replaces_the_css_triangle(engine_page: Page) -> None:
    page = engine_page
    _mount(page, '{"chevron": "icon"}')
    assert page.evaluate("() => __t.el.className") == "ui-trace ui-trace--icon-chevron"
    assert page.locator(".ui-trace-chevron svg").count() == 1
    assert page.evaluate(
        "() => getComputedStyle(__t.el.querySelector('summary'), '::before').content"
    ) in ("none", "normal")
    default = page.evaluate(
        "() => { const t = App.ui.trace({id: 'x'}); document.getElementById('harness-root').appendChild(t.el); return getComputedStyle(t.el.querySelector('summary'), '::before').content; }"
    )
    assert default not in ("none", "normal")


def test_unknown_options_throw(engine_page: Page) -> None:
    load_harness(engine_page)
    err = engine_page.evaluate(
        "() => { const out = []; for (const o of [{chevron: 'x'}, {countStyle: 'x'}]) { try { App.ui.trace(o); out.push(null); } catch (e) { out.push(e.message); } } return out; }"
    )
    assert "unknown chevron" in err[0] and "unknown countStyle" in err[1]


def test_empty_trace_degenerate_cases(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.__t = App.ui.trace({});
          document.getElementById('harness-root').appendChild(__t.el);
        }"""
    )
    assert page.evaluate("() => __t.el.hasAttribute('data-parent-msg-id')") is False
    assert page.evaluate("() => __t.count()") == 0
    assert page.evaluate("() => __t.el.querySelector('.ui-trace-body').children.length") == 0


def test_find_rewraps_the_same_node_and_keeps_the_count(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        "() => { __t.append(__tool('one')); window.__root = document.getElementById('harness-root'); }"
    )
    out = page.evaluate(
        """() => {
          const h = App.ui.trace.find(__root, 'm1');
          const before = h.count();
          h.append(__tool('two'));
          return {same: h.el === __t.el, before, after: h.count(), orig: __t.count(),
                  name: __t.el.querySelector('summary').getAttribute('aria-label'),
                  miss: App.ui.trace.find(__root, 'nope'), none: App.ui.trace.find(null, 'm1')};
        }"""
    )
    assert out == {
        "same": True,
        "before": 1,
        "after": 2,
        "orig": 2,
        "name": "Tool activity, 2 items",
        "miss": None,
        "none": None,
    }


def test_find_is_scoped_to_the_trace_not_the_thinking_disclosure(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    out = page.evaluate(
        """() => {
          const th = App.ui.trace.thinking({parentId: 'm2', body: 'x'});
          __root = document.getElementById('harness-root');
          __root.appendChild(th.el);
          return {thinking: App.ui.trace.find(__root, 'm2'), trace: App.ui.trace.find(__root, 'm1') !== null};
        }"""
    )
    assert out == {"thinking": None, "trace": True}


def test_find_rewraps_a_dot_style_node(engine_page: Page) -> None:
    page = engine_page
    _mount(page, '{"countStyle": "dot", "label": "Work"}')
    page.evaluate("() => { __t.append(__tool('a')); }")
    page.evaluate(
        "() => { const h = App.ui.trace.find(document.getElementById('harness-root'), 'm1'); h.append(__tool('b')); }"
    )
    expect(page.locator(".ui-trace-label")).to_have_text("Work · 2")
    expect(page.locator("summary")).to_have_attribute("aria-label", "Work, 2 items")


def test_destroy_never_removes_content_and_is_idempotent(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("() => { __t.append(__tool('one')); __t.destroy(); __t.destroy(); }")
    assert page.evaluate("() => __t.count()") == 1
    assert page.evaluate("() => __t.el.isConnected") is True
    page.evaluate("() => __t.append(__tool('late'))")  # a spent handle appends nothing
    assert page.evaluate("() => __t.count()") == 1


def test_thinking_disclosure_structure_toggle_and_empty_body(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          window.__a = App.ui.trace.thinking({body: 'First line\\nSecond', parentId: 'm9', testid: 'th-a'});
          window.__b = App.ui.trace.thinking({testid: 'th-b', label: 'Reasoning'});
          root.appendChild(__a.el); root.appendChild(__b.el);
        }"""
    )
    a = page.get_by_test_id("th-a")
    assert a.evaluate("(n) => n.tagName") == "DETAILS"
    assert a.evaluate("(n) => n.className") == "ui-trace-thinking"
    assert a.evaluate("(n) => n.getAttribute('data-parent-msg-id')") == "m9"
    expect(a.locator("summary")).to_have_text("Thinking")
    assert a.evaluate("(n) => n.open") is False
    a.locator("summary").focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => __a.el.open === true")
    assert (
        page.evaluate("() => __a.el.querySelector('.ui-trace-thinking-body').textContent")
        == "First line\nSecond"
    )
    b = page.get_by_test_id("th-b")
    assert b.evaluate("(n) => n.hasAttribute('data-parent-msg-id')") is False
    expect(b.locator("summary")).to_have_text("Reasoning")
    assert page.evaluate("() => __b.el.querySelector('.ui-trace-thinking-body').textContent") == ""
    page.evaluate("() => { __a.destroy(); __a.destroy(); }")


def test_a_long_unbroken_tool_name_does_not_overflow_the_body(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          const frame = document.createElement('div');
          frame.style.cssText = 'display: flex; flex-direction: column; width: 300px;';
          window.__t = App.ui.trace({id: 'm1'});
          const m = App.ui.message({role: 'tool', text: 'x'.repeat(200)});
          __t.append(m.el);
          __t.el.querySelector('details').open = true;
          frame.appendChild(__t.el);
          document.getElementById('harness-root').appendChild(frame);
          window.__frame = frame;
        }"""
    )
    assert page.evaluate("() => __t.el.scrollWidth <= __frame.clientWidth + 1") is True
