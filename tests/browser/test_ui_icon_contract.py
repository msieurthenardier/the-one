# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.icon`` (M31 F1 L2, DD6).

Runs in Chromium and WebKit through ``engine_page`` + ``load_harness`` (no app
spawn). Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

_MOUNT = """(opts) => {
  const svg = App.ui.icon('plus', opts);
  document.getElementById('harness-root').appendChild(svg);
  const r = svg.getBoundingClientRect();
  return {ctor: svg.constructor.name, ns: svg.namespaceURI,
          hidden: svg.getAttribute('aria-hidden'), focusable: svg.getAttribute('focusable'),
          cls: svg.getAttribute('class'), w: r.width, h: r.height,
          tabindex: svg.getAttribute('tabindex')};
}"""


def test_icon_is_a_hidden_svg_node(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(_MOUNT, None)
    assert out["ctor"] == "SVGSVGElement"
    assert out["ns"] == "http://www.w3.org/2000/svg"
    assert out["hidden"] == "true"
    assert out["cls"] == "ui-icon"


def test_icon_default_and_small_sizes_come_from_owned_classes(engine_page: Page) -> None:
    load_harness(engine_page)
    default = engine_page.evaluate(_MOUNT, None)
    small = engine_page.evaluate(_MOUNT, {"size": "sm"})
    assert (default["w"], default["h"]) == (16, 16)
    assert small["cls"] == "ui-icon ui-icon--sm"
    assert (small["w"], small["h"]) == (14, 14)


def test_icon_appends_class_name(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(_MOUNT, {"size": "sm", "className": "extra"})
    assert out["cls"] == "ui-icon ui-icon--sm extra"


def test_icon_throws_on_unknown_name(engine_page: Page) -> None:
    load_harness(engine_page)
    msg = engine_page.evaluate(
        "() => { try { App.ui.icon('nope-not-an-icon'); return ''; }"
        " catch (e) { return e.message; } }"
    )
    assert "unknown icon" in msg


def test_icon_is_not_focusable(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(_MOUNT, None)
    assert out["focusable"] == "false"
    assert out["tabindex"] is None
    engine_page.evaluate(
        "() => document.getElementById('harness-root').querySelector('svg').focus()"
    )
    active = engine_page.evaluate("() => document.activeElement && document.activeElement.nodeName")
    assert active != "svg"


def test_more_icon_is_a_hidden_svg(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        "() => { const n = App.ui.icon('more'); document.getElementById('harness-root').appendChild(n); return [n.tagName.toLowerCase(), n.getAttribute('aria-hidden'), n.getAttribute('focusable'), n.querySelectorAll('circle').length]; }"
    )
    assert out == ["svg", "true", "false", 3]
