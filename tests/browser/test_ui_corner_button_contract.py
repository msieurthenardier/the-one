# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Engine-parametrized contract tests for ``App.ui.cornerButton`` (M36 F3 L2): the 48px violet
tile button the GleepGlorp assistant sits behind at the corner of the app shell.

Markup and ARIA, the handle (``setExpanded``, ``setHidden``, ``focus``), the anchored 48px
geometry (24px from the bottom-right of the positioned container), the token colours, the house
focus ring, click and real Enter and Space activation, and the option errors. Chromium and WebKit
through ``engine_page`` + ``load_harness`` (no app spawn); ``contracts-controls`` lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

MOUNT_JS = """(opts) => {
  window.__clicks = 0;
  const root = document.getElementById('harness-root');
  const frame = document.createElement('div');
  frame.id = 'frame';
  frame.style.cssText = 'position: relative; width: 600px; height: 400px;';
  const other = document.createElement('button');
  other.textContent = 'Elsewhere';
  other.setAttribute('data-testid', 'cb-other');
  frame.appendChild(other);
  const b = App.ui.cornerButton(Object.assign({
    ariaLabel: 'Ask the assistant', icon: 'bot', controls: 'panel', testid: 'cb',
    onClick: () => { window.__clicks += 1; },
  }, opts || {}));
  frame.appendChild(b.el);
  root.appendChild(frame);
  window.__b = b;
  return true;
}"""


def _mount(page: Page, opts: str = "{}", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT_JS})({opts})")


def _throws(page: Page, expr: str) -> str:
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


def test_markup_and_aria(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => {
          const el = window.__b.el;
          const svg = el.querySelector('svg');
          return {
            tag: el.tagName, type: el.getAttribute('type'), cls: el.className,
            label: el.getAttribute('aria-label'), expanded: el.getAttribute('aria-expanded'),
            controls: el.getAttribute('aria-controls'), testid: el.dataset.testid,
            svgHidden: svg.getAttribute('aria-hidden'), text: el.textContent,
            handle: Object.keys(window.__b).sort(),
          };
        }"""
    )
    assert out["tag"] == "BUTTON" and out["type"] == "button"
    assert out["cls"] == "ui-corner-button"
    assert out["label"] == "Ask the assistant"
    assert out["expanded"] == "false" and out["controls"] == "panel"
    assert out["testid"] == "cb" and out["svgHidden"] == "true" and out["text"] == ""
    assert out["handle"] == ["el", "focus", "setExpanded", "setHidden"]


def test_requires_a_label_and_an_icon(engine_page: Page) -> None:
    _mount(engine_page)
    assert "ariaLabel is required" in _throws(engine_page, "App.ui.cornerButton({icon: 'bot'})")
    assert "icon is required" in _throws(engine_page, "App.ui.cornerButton({ariaLabel: 'x'})")


def test_set_expanded_and_set_hidden(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    btn = p.get_by_test_id("cb")
    p.evaluate("() => window.__b.setExpanded(true)")
    expect(btn).to_have_attribute("aria-expanded", "true")
    p.evaluate("() => window.__b.setExpanded(false)")
    expect(btn).to_have_attribute("aria-expanded", "false")
    p.evaluate("() => window.__b.setHidden(true)")
    expect(btn).to_be_hidden()
    expect(p.get_by_role("button", name="Ask the assistant")).to_have_count(0)
    p.evaluate("() => window.__b.setHidden(false)")
    expect(btn).to_be_visible()


def test_can_start_expanded_and_hidden(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{expanded: true, hidden: true}")
    btn = p.get_by_test_id("cb")
    expect(btn).to_have_attribute("aria-expanded", "true")
    expect(btn).to_be_hidden()


def test_is_a_48px_tile_anchored_24px_from_the_bottom_right(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    box = p.evaluate(
        """() => {
          const b = document.querySelector('[data-testid=cb]').getBoundingClientRect();
          const f = document.getElementById('frame').getBoundingClientRect();
          return {w: b.width, h: b.height, right: f.right - b.right, bottom: f.bottom - b.bottom,
                  z: getComputedStyle(document.querySelector('[data-testid=cb]')).zIndex};
        }"""
    )
    assert box["w"] == 48 and box["h"] == 48
    assert box["right"] == 24 and box["bottom"] == 24
    assert box["z"] == "9"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_colours_come_from_the_accent_fill_tokens(engine_page: Page, theme: str) -> None:
    p = engine_page
    _mount(p, theme=theme)
    out = p.evaluate(
        """() => {
          const b = document.querySelector('[data-testid=cb]');
          const probe = document.createElement('div');
          const root = document.getElementById('harness-root');
          root.appendChild(probe);
          probe.style.background = 'var(--accent-fill)';
          probe.style.color = 'var(--fg-on-accent-fill)';
          const want = getComputedStyle(probe);
          const got = getComputedStyle(b);
          return {bg: got.backgroundColor === want.backgroundColor,
                  fg: got.color === want.color};
        }"""
    )
    assert out == {"bg": True, "fg": True}


def test_keyboard_focus_shows_the_house_ring(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("cb-other").focus()
    p.keyboard.press("Tab")
    assert p.evaluate("() => document.activeElement.dataset.testid") == "cb"
    ring = p.evaluate(
        "() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineWidth, s.outlineOffset]; }"
    )
    assert ring == ["solid", "2px", "2px"]


def test_handle_focus_moves_focus_to_the_button(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__b.focus()")
    assert p.evaluate("() => document.activeElement.dataset.testid") == "cb"


@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_click_enter_and_space_activate(engine_page: Page, key: str) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("cb").click()
    assert p.evaluate("() => window.__clicks") == 1
    p.evaluate("() => window.__b.focus()")
    p.keyboard.press(key)
    assert p.evaluate("() => window.__clicks") == 2
