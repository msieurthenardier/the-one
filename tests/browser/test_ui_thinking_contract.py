# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.thinking`` (M31 F6 L04, flight DD4): the
ephemeral "the model is working" line. Classes, tones, the dot animation, reduced motion,
``settle`` and the interval's lifetime (counted through a wrapped ``setInterval``). Chromium
and WebKit through ``engine_page`` + ``load_harness``; falls in the ``contracts-chat`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# Wraps setInterval and clearInterval so a test can count the live intervals.
COUNT_JS = """() => {
  window.__live = new Set();
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  window.setInterval = (fn, ms) => { const id = si(fn, ms); window.__live.add(id); return id; };
  window.clearInterval = (id) => { window.__live.delete(id); ci(id); };
}"""


def _load(page: Page, reduced: bool = False) -> None:
    page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
    page.clock.install()
    load_harness(page)
    page.evaluate(COUNT_JS)


def _mount(page: Page, opts: str = "{}") -> None:
    page.evaluate(
        """(opts) => {
          window.__t = App.ui.thinking(Object.assign({testid: 't-root'}, opts));
          document.getElementById('harness-root').appendChild(__t.el);
        }""",
        json.loads(opts),
    )


def test_classes_label_testid_and_the_dots_animate(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page, '{"label": "Thinking…"}')
    root = page.get_by_test_id("t-root")
    assert page.evaluate("() => __t.el.className") == "ui-message ui-message--assistant ui-thinking"
    expect(root.locator(".ui-thinking-text")).to_have_text("Thinking…")
    assert (
        page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').getAttribute('aria-hidden')")
        == "true"
    )
    before = page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').textContent")
    page.clock.run_for(130)
    after = page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').textContent")
    assert after.strip() and after != before
    assert page.evaluate("() => __live.size") == 1


def test_default_label_is_the_old_wording_and_the_look_is_italic_muted(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    expect(page.locator(".ui-thinking-text")).to_have_text("thinking")
    style = page.evaluate(
        "() => { const s = getComputedStyle(__t.el); return [s.fontStyle, s.alignSelf]; }"
    )
    assert style[0] == "italic"


def test_system_tone_is_the_centred_loading_line(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(
        """() => {
          const frame = document.createElement('div');
          frame.style.cssText = 'display: flex; flex-direction: column; width: 400px;';
          window.__t = App.ui.thinking({label: 'Loading model', tone: 'system', testid: 't-sys'});
          frame.appendChild(__t.el);
          document.getElementById('harness-root').appendChild(frame);
        }"""
    )
    assert page.evaluate("() => __t.el.className") == "ui-message ui-message--system ui-thinking"
    style = page.evaluate(
        "() => { const s = getComputedStyle(__t.el); return [s.fontStyle, s.alignSelf]; }"
    )
    assert style == ["normal", "center"]
    err = page.evaluate(
        "() => { try { App.ui.thinking({tone: 'x'}); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown tone" in err


def test_reduced_motion_is_read_once_and_starts_no_interval(engine_page: Page) -> None:
    page = engine_page
    _load(page, reduced=True)
    _mount(page)
    assert page.evaluate("() => __live.size") == 0
    assert page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').textContent") == " …"
    page.clock.run_for(500)
    assert page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').textContent") == " …"


def test_settle_replaces_contents_keeps_the_node_and_stops_the_timer(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(
        """() => {
          const frame = document.createElement('div');
          window.__t = App.ui.thinking({label: 'Loading model', tone: 'system', testid: 't-sys'});
          window.__node = __t.el;
          frame.appendChild(__t.el);
          document.getElementById('harness-root').appendChild(frame);
        }"""
    )
    page.evaluate("() => __t.settle('Model loaded.')")
    assert page.evaluate("() => __t.el === __node && __node.isConnected") is True
    assert page.evaluate("() => __node.textContent") == "Model loaded."
    assert page.evaluate("() => __node.className") == "ui-message ui-message--system"
    assert page.evaluate("() => __node.children.length") == 0
    assert page.evaluate("() => __live.size") == 0
    page.evaluate("() => __t.settle('Again')")  # repeating is harmless
    assert page.evaluate("() => __node.textContent") == "Again"


def test_interval_stops_after_connected_then_disconnected_but_not_before(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate("() => { window.__t = App.ui.thinking({testid: 't-root'}); }")
    page.clock.run_for(500)  # built, never attached: it keeps ticking
    assert page.evaluate("() => __live.size") == 1
    page.evaluate("() => document.getElementById('harness-root').appendChild(__t.el)")
    page.clock.run_for(130)
    assert page.evaluate("() => __live.size") == 1
    page.evaluate("() => __t.el.remove()")
    page.clock.run_for(130)
    assert page.evaluate("() => __live.size") == 0


def test_destroy_stops_the_interval_and_is_idempotent(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    page.evaluate("() => { __t.destroy(); __t.destroy(); }")
    assert page.evaluate("() => __live.size") == 0
    assert page.evaluate("() => __t.el.isConnected") is True  # destroy never removes the node
    text = page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').textContent")
    page.clock.run_for(500)
    assert page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').textContent") == text
