# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.notice`` (M31 F6 L04, flight DD4): a
transcript line, muted or danger, that is not a live region. Chromium and WebKit through
``engine_page`` + ``load_harness`` (no app spawn); falls in the ``contracts-chat`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _mount(page: Page, opts: str) -> None:
    load_harness(page)
    page.evaluate(
        """(opts) => {
          window.__n = App.ui.notice(Object.assign({testid: 'n-root'}, opts));
          document.getElementById('harness-root').appendChild(__n.el);
        }""",
        json.loads(opts),
    )


def test_muted_is_the_default_and_text_is_set_as_text(engine_page: Page) -> None:
    _mount(engine_page, '{"body": "<b>not html</b>"}')
    node = engine_page.get_by_test_id("n-root")
    expect(node).to_have_text("<b>not html</b>")
    assert engine_page.evaluate("() => __n.el.className") == "ui-notice ui-notice--muted"
    assert engine_page.evaluate("() => __n.el.querySelectorAll('b').length") == 0


def test_tones_differ_in_colour_and_unknown_tone_throws(engine_page: Page) -> None:
    page = engine_page
    _mount(page, '{"body": "Quiet"}')
    muted = page.evaluate("() => getComputedStyle(__n.el).color")
    page.evaluate(
        "() => { const d = App.ui.notice({tone: 'danger', body: 'Bad', testid: 'n-bad'}); document.getElementById('harness-root').appendChild(d.el); }"
    )
    danger = page.evaluate(
        "() => getComputedStyle(document.querySelector('[data-testid=n-bad]')).color"
    )
    assert muted != danger
    assert (
        page.evaluate("() => document.querySelector('[data-testid=n-bad]').className")
        == "ui-notice ui-notice--danger"
    )
    err = page.evaluate(
        "() => { try { App.ui.notice({tone: 'loud'}); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown tone" in err


def test_not_a_live_region(engine_page: Page) -> None:
    _mount(engine_page, '{"body": "Line"}')
    attrs = engine_page.evaluate(
        "() => ({role: __n.el.getAttribute('role'), live: __n.el.getAttribute('aria-live'), tab: __n.el.getAttribute('tabindex')})"
    )
    assert attrs == {"role": None, "live": None, "tab": None}


def test_set_replaces_with_text_node_or_empties(engine_page: Page) -> None:
    page = engine_page
    _mount(page, '{"body": "First"}')
    page.evaluate(
        "() => { const b = document.createElement('a'); b.href = '#x'; b.textContent = 'Link'; __n.set(b); }"
    )
    expect(page.get_by_role("link", name="Link")).to_have_count(1)
    page.evaluate("() => __n.set('Second')")
    expect(page.get_by_test_id("n-root")).to_have_text("Second")
    assert page.evaluate("() => __n.el.children.length") == 0
    page.evaluate("() => __n.set(null)")
    expect(page.get_by_test_id("n-root")).to_have_text("")


def test_no_body_and_a_long_unbroken_word_stay_inside(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          const frame = document.createElement('div');
          frame.style.cssText = 'display: flex; flex-direction: column; width: 240px;';
          window.__empty = App.ui.notice({testid: 'n-empty'});
          window.__long = App.ui.notice({body: 'x'.repeat(200), testid: 'n-long'});
          frame.appendChild(__empty.el); frame.appendChild(__long.el);
          document.getElementById('harness-root').appendChild(frame);
          window.__frame = frame;
        }"""
    )
    assert page.evaluate("() => __empty.el.textContent") == ""
    assert page.evaluate("() => __long.el.scrollWidth <= __frame.clientWidth + 1") is True


def test_destroy_is_safe_to_repeat(engine_page: Page) -> None:
    page = engine_page
    _mount(page, '{"body": "Stay"}')
    page.evaluate("() => { __n.destroy(); __n.destroy(); }")
    expect(page.get_by_test_id("n-root")).to_have_text("Stay")
