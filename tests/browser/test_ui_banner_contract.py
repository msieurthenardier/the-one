# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.banner`` (M31 F4 L04a). Chromium and WebKit;
``contracts-controls``."""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

MOUNT = """(opts) => {
  window.__b = App.ui.banner(opts);
  document.getElementById('harness-root').appendChild(window.__b.el);
  return true;
}"""


def _mount(page: Page, opts: str) -> None:
    load_harness(page)
    page.evaluate(f"({MOUNT})({opts})")


def _throws(page: Page, opts: str) -> str:
    return page.evaluate(
        f"() => {{ try {{ App.ui.banner({opts}); return ''; }} catch (e) {{ return e.message; }} }}"
    )


def test_defaults_and_dom_shape(engine_page: Page) -> None:
    _mount(engine_page, "{text: 'Heads up', testid: 'bn'}")
    out = engine_page.evaluate(
        "() => [__b.el.tagName, __b.el.className, __b.el.getAttribute('role'), __b.el.textContent, __b.el.getAttribute('data-testid'), __b.el.hasAttribute('data-empty')]"
    )
    assert out == ["DIV", "banner banner-info ui-banner", "note", "Heads up", "bn", False]


@pytest.mark.parametrize("tone", ["info", "warning", "error"])
def test_tones(engine_page: Page, tone: str) -> None:
    _mount(engine_page, f"{{tone: '{tone}', text: 'x', className: 'extra-one'}}")
    assert (
        engine_page.evaluate("() => __b.el.className")
        == f"banner banner-{tone} ui-banner extra-one"
    )


def test_role_and_live_rules(engine_page: Page) -> None:
    load_harness(engine_page)
    for opts, role in [
        ("{role: 'status'}", "status"),
        ("{role: 'alert'}", "alert"),
        ("{live: 'alert'}", "alert"),
        ("{live: 'status'}", "status"),
        ("{live: 'alert', role: 'alert'}", "alert"),
    ]:
        assert engine_page.evaluate(f"() => App.ui.banner({opts}).el.getAttribute('role')") == role
    assert "tone" in _throws(engine_page, "{tone: 'loud'}")
    assert "role" in _throws(engine_page, "{role: 'region'}")
    assert "live" in _throws(engine_page, "{live: 'polite'}")
    assert "contradicts" in _throws(engine_page, "{live: 'alert', role: 'status'}")


def test_set_children_actions_and_visibility(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{text: 'Base', actions: [Object.assign(document.createElement('button'), {textContent: 'Undo'})], hidden: true}",
    )
    assert engine_page.evaluate("() => __b.el.hidden") is True
    engine_page.evaluate("() => __b.show()")
    assert engine_page.get_by_role("note").is_visible()
    engine_page.evaluate("() => { __b.hide(); }")
    assert engine_page.evaluate("() => __b.el.hidden") is True
    engine_page.evaluate(
        "() => { __b.show(); __b.set('Changed'); __b.setChildren([Object.assign(document.createElement('b'), {textContent: ' bold'})]); }"
    )
    out = engine_page.evaluate(
        "() => [__b.el.textContent, Array.from(__b.el.childNodes).map((n) => n.nodeName), __b.el.querySelector('.ui-banner-actions button').textContent]"
    )
    assert out[0] == "Changed boldUndo"
    assert out[1] == ["#text", "B", "DIV"]  # text, children, then the actions
    engine_page.evaluate("() => __b.setChildren([])")
    assert engine_page.evaluate("() => Array.from(__b.el.childNodes).map((n) => n.nodeName)") == [
        "#text",
        "DIV",
    ]


def test_children_option(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{children: [Object.assign(document.createElement('a'), {textContent: 'link', href: '#x'})]}",
    )
    assert engine_page.get_by_role("link", name="link").count() == 1


def test_persistent_live_mode_collapses_when_empty(engine_page: Page) -> None:
    _mount(engine_page, "{live: 'alert', tone: 'error', testid: 'live'}")
    el = "() => { const r = __b.el.getBoundingClientRect(), c = getComputedStyle(__b.el); return [r.height, c.paddingTop, c.borderLeftWidth, __b.el.hasAttribute('data-empty'), __b.el.getAttribute('role'), document.body.contains(__b.el)]; }"
    assert engine_page.evaluate(el) == [0, "0px", "0px", True, "alert", True]
    engine_page.evaluate("() => __b.set('Cannot delete')")
    h = engine_page.evaluate(el)
    assert h[0] > 20 and h[3] is False
    assert engine_page.get_by_role("alert").inner_text() == "Cannot delete"
    engine_page.evaluate("() => __b.set('')")
    assert engine_page.evaluate(el)[:4] == [0, "0px", "0px", True]


def test_live_with_children_is_not_empty(engine_page: Page) -> None:
    _mount(engine_page, "{live: 'status'}")
    engine_page.evaluate("() => __b.setChildren([document.createElement('span')])")
    assert engine_page.evaluate("() => __b.el.hasAttribute('data-empty')") is False
    engine_page.evaluate("() => __b.setChildren([])")
    assert engine_page.evaluate("() => __b.el.hasAttribute('data-empty')") is True


@pytest.mark.parametrize("tone", ["info", "warning", "error"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_looks_like_legacy_banner_markup(engine_page: Page, tone: str, theme: str) -> None:
    load_harness(engine_page, theme)
    out = engine_page.evaluate(
        """(tone) => {
          const root = document.getElementById('harness-root');
          const legacy = document.createElement('div');
          legacy.className = 'banner banner-' + tone; legacy.textContent = 'Same text';
          root.appendChild(legacy);
          const b = App.ui.banner({tone: tone, text: 'Same text'});
          root.appendChild(b.el);
          const props = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'borderLeftWidth', 'borderLeftColor', 'borderTopWidth', 'color', 'backgroundImage', 'fontSize', 'lineHeight', 'borderTopRightRadius', 'borderTopLeftRadius'];
          const pick = (e) => props.map((p) => getComputedStyle(e)[p]);
          return {a: pick(legacy), b: pick(b.el), h: [legacy.getBoundingClientRect().height, b.el.getBoundingClientRect().height]};
        }""",
        tone,
    )
    assert out["a"] == out["b"]
    assert out["h"][0] == out["h"][1] > 0
