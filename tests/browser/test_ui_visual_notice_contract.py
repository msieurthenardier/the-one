# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.visualNotice`` (M35 F2 L2, flight DD14): the
notice a visual block shows when it cannot draw (a headline, an optional reason and a closed
"Technical details" disclosure holding the source). Chromium and WebKit through ``engine_page``
+ ``load_harness`` (no app spawn); falls in the ``contracts-chat`` lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _mount(page: Page, opts: dict) -> None:
    load_harness(page)
    page.evaluate(
        """(opts) => {
          window.__vn = App.ui.visualNotice(Object.assign({testid: 'vn'}, opts));
          document.getElementById('harness-root').appendChild(__vn.el);
        }""",
        opts,
    )


def test_danger_tone_headline_reason_and_details(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        {
            "tone": "danger",
            "headline": "Couldn't draw this.",
            "reason": "A reason sentence.",
            "source": '{"a": 1}',
            "sourceLabel": "Thing source",
        },
    )
    root = page.get_by_test_id("vn")
    assert root.get_attribute("class") == "ui-notice ui-notice--danger"
    assert root.locator(".ui-visual-notice-head").text_content() == "Couldn't draw this."
    assert root.locator(".ui-visual-notice-reason").text_content() == "A reason sentence."
    details = page.get_by_test_id("vn-details")
    assert details.evaluate("el => el.tagName") == "DETAILS"
    assert details.evaluate("el => el.open") is False
    assert details.locator("summary").text_content() == "Technical details"
    assert details.locator("pre").text_content() == '{"a": 1}'


def test_muted_tone_without_a_reason(engine_page: Page) -> None:
    page = engine_page
    _mount(page, {"tone": "muted", "headline": "Cut off.", "source": "abc"})
    root = page.get_by_test_id("vn")
    assert root.get_attribute("class") == "ui-notice ui-notice--muted"
    assert root.locator(".ui-visual-notice-head").text_content() == "Cut off."
    assert root.locator(".ui-visual-notice-reason").count() == 0


def test_details_testid_override_and_default(engine_page: Page) -> None:
    page = engine_page
    _mount(page, {"headline": "h", "source": "s", "detailsTestid": "custom-details"})
    expect(page.get_by_test_id("custom-details")).to_have_count(1)
    expect(page.get_by_test_id("vn-details")).to_have_count(0)


def test_source_is_shown_exactly_and_never_parsed(engine_page: Page) -> None:
    page = engine_page
    source = '<script>window.__pwn = 1</script>\n  <b>x</b>  "q" & more\n'
    _mount(
        page,
        {"headline": "<i>not html</i>", "reason": "<b>nor this</b>", "source": source},
    )
    root = page.get_by_test_id("vn")
    assert root.locator("pre").text_content() == source
    assert root.locator(".ui-visual-notice-head").text_content() == "<i>not html</i>"
    assert root.locator(".ui-visual-notice-reason").text_content() == "<b>nor this</b>"
    assert page.evaluate("() => window.__pwn === undefined")
    assert page.evaluate("() => __vn.el.querySelectorAll('script, b, i').length") == 0


def test_an_empty_source_does_not_throw(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    ok = page.evaluate(
        """() => {
          const h = App.ui.visualNotice({headline: 'h'});
          const g = App.ui.visualNotice({headline: 'h', source: null, tone: 'muted'});
          return h.el instanceof Element && g.el instanceof Element;
        }"""
    )
    assert ok is True
