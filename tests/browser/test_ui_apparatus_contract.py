"""Contract tests for the UI test apparatus itself (M25 F1 L1, AC9).

Proves the shared label/description resolver and the disk harness in Chromium and
WebKit on synthetic DOM, before any library code exists. Falls in the ``shared``
lane (no area-lane glob matches this name).
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import (
    assert_controls_labelled_and_described,
    collect_label_failures,
)
from browser._ui_engines import load_harness
from browser.design_tokens import DARK, LIGHT
from playwright.sync_api import Page

pytestmark = pytest.mark.browser


def _mount(page: Page, html: str) -> None:
    load_harness(page)
    page.evaluate("(h) => { document.getElementById('harness-root').innerHTML = h; }", html)


NAME = "control has no accessible name"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<input id=a>", [NAME]),
        ('<button><svg width="8" height="8"></svg></button>', [NAME]),
        (
            "<label for=i>L</label><input id=i aria-describedby=ghost>",
            ['aria-describedby references missing id "ghost"'],
        ),
        (
            "<input id=i aria-label=L aria-labelledby=ghost>",
            ['aria-labelledby references missing id "ghost"'],
        ),
        (
            "<span id=e></span><input id=i aria-labelledby=e>",
            ['aria-labelledby target "e" has empty text', NAME],
        ),
        (
            '<button aria-expanded="true" aria-controls=popup>Open</button>',
            ['aria-controls references missing id "popup"'],
        ),
    ],
    ids=[
        "unnamed-input",
        "icon-only-button",
        "dangling-describedby",
        "dangling-labelledby",
        "empty-labelledby",
        "dangling-controls-expanded",
    ],
)
def test_resolver_flags(engine_page: Page, html: str, expected: list[str]) -> None:
    _mount(engine_page, html)
    failures = collect_label_failures(engine_page, "#harness-root")
    assert len(failures) == len(expected), failures
    for failure, rule in zip(failures, expected, strict=True):
        assert failure.endswith(" :: " + rule), failure
    with pytest.raises(AssertionError) as exc:
        assert_controls_labelled_and_described(engine_page, "#harness-root")
    for failure in failures:
        assert failure in str(exc.value)


@pytest.mark.parametrize(
    "html",
    [
        "<label for=i>Name</label><input id=i aria-describedby=h><span id=h>Hint</span>",
        "<div role=menu><div role=menuitem tabindex=-1>Rename</div></div>",
        '<button aria-expanded="false" aria-controls=popup>Open</button>',
        '<button aria-label="Close"><svg width="8" height="8"></svg></button>',
    ],
    ids=[
        "labelled-with-describedby",
        "content-named-menuitem",
        "controls-collapsed",
        "aria-label-icon-button",
    ],
)
def test_resolver_passes(engine_page: Page, html: str) -> None:
    _mount(engine_page, html)
    assert collect_label_failures(engine_page, "#harness-root") == []
    assert_controls_labelled_and_described(engine_page, "#harness-root")


def test_resolver_fails_on_zero_matches(engine_page: Page) -> None:
    _mount(engine_page, "<input aria-label=x>")
    failures = collect_label_failures(engine_page, "#does-not-exist")
    assert failures == ['root selector "#does-not-exist" matched no element']
    with pytest.raises(AssertionError, match="matched no element"):
        assert_controls_labelled_and_described(engine_page, "#does-not-exist")


@pytest.mark.parametrize(("theme", "tokens"), [("dark", DARK), ("light", LIGHT)])
def test_harness_themes_from_tokens(engine_page: Page, theme: str, tokens: dict[str, str]) -> None:
    load_harness(engine_page, theme)
    assert engine_page.evaluate("document.querySelector('style').textContent").startswith("@layer")
    bg = engine_page.evaluate(
        "getComputedStyle(document.getElementById('harness-root')).backgroundColor"
    )
    h = tokens["bg"].lstrip("#")
    expected = "rgb({}, {}, {})".format(*(int(h[i : i + 2], 16) for i in (0, 2, 4)))
    assert bg == expected
