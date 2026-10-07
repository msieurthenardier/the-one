# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.focusAfter`` (M25 F6 L1b, flight DD2): the
shared focus-after-an-in-place-action helper. It is not an ``App.ui`` factory, so the harness
does not load it; the test injects ``static/js/focus-after.js`` itself. Chromium and WebKit
through ``engine_page`` (no app spawn); falls in the ``contracts`` lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import STATIC_DIR, load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

SETUP_JS = """() => {
  const root = document.getElementById('harness-root');
  root.innerHTML = '';
  const mk = (id, tag) => { const e = document.createElement(tag || 'button'); e.id = id; e.textContent = id; root.appendChild(e); return e; };
  mk('btn'); mk('other'); mk('title', 'h2').tabIndex = -1;
}"""


@pytest.fixture
def fa(engine_page: Page) -> Page:
    load_harness(engine_page)
    engine_page.add_script_tag(path=str(STATIC_DIR / "js" / "focus-after.js"))
    engine_page.evaluate(SETUP_JS)
    return engine_page


def active(page: Page) -> str:
    return page.evaluate(
        "document.activeElement && (document.activeElement.id || document.activeElement.tagName)"
    )


def settle(page: Page) -> None:
    page.wait_for_timeout(60)


def start(page: Page, focus: bool = True) -> None:
    """Begin a token on #btn (focused or not), kept on window.__t."""
    page.evaluate(
        "(f) => { const b = document.getElementById('btn'); if (f) b.focus(); window.__t = App.focusAfter.begin(b); }",
        focus,
    )


def test_null_token_and_no_focus_are_noops(fa: Page) -> None:
    assert fa.evaluate("App.focusAfter.restore(null, document.getElementById('title'))") is False
    start(fa, focus=False)
    assert (
        fa.evaluate("App.focusAfter.restore(window.__t, document.getElementById('title'))") is False
    )
    settle(fa)
    assert active(fa) == "BODY"


def test_restores_when_the_control_is_disabled_in_place(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('btn').disabled = true")
    assert (
        fa.evaluate("App.focusAfter.restore(window.__t, document.getElementById('title'))") is True
    )
    settle(fa)
    assert active(fa) == "title"


def test_restores_when_the_control_was_removed(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('btn').remove()")
    assert (
        fa.evaluate("App.focusAfter.restore(window.__t, () => document.getElementById('title'))")
        is True
    )
    settle(fa)
    assert active(fa) == "title"


def test_function_target_resolved_when_the_timer_fires(fa: Page) -> None:
    start(fa)
    fa.evaluate(
        """() => {
          document.getElementById('btn').disabled = true;
          App.focusAfter.restore(window.__t, () => document.getElementById('late'));
          const late = document.createElement('button'); late.id = 'late';
          document.getElementById('harness-root').appendChild(late);
        }"""
    )
    settle(fa)
    assert active(fa) == "late"


def test_never_steals_from_another_enabled_element(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('other').focus()")
    assert (
        fa.evaluate("App.focusAfter.restore(window.__t, document.getElementById('title'))") is False
    )
    settle(fa)
    assert active(fa) == "other"


def test_focus_moved_during_the_timer_is_respected(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('btn').disabled = true")
    fa.evaluate(
        "() => { App.focusAfter.restore(window.__t, document.getElementById('title')); document.getElementById('other').focus(); }"
    )
    settle(fa)
    assert active(fa) == "other"


def test_superseded_token_does_not_restore(fa: Page) -> None:
    start(fa)
    fa.evaluate("window.__t2 = App.focusAfter.begin(document.getElementById('btn'))")
    fa.evaluate("document.getElementById('btn').disabled = true")
    assert (
        fa.evaluate("App.focusAfter.restore(window.__t, document.getElementById('title'))") is False
    )
    assert (
        fa.evaluate("App.focusAfter.restore(window.__t2, document.getElementById('title'))") is True
    )
    settle(fa)
    assert active(fa) == "title"


def test_cancel_invalidates_tokens(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('btn').disabled = true")
    fa.evaluate("App.focusAfter.cancel()")
    assert (
        fa.evaluate("App.focusAfter.restore(window.__t, document.getElementById('title'))") is False
    )
    settle(fa)
    assert active(fa) == "BODY"


def test_cancel_after_restore_before_the_timer_cancels_the_focus(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('btn').disabled = true")
    fa.evaluate(
        "() => { App.focusAfter.restore(window.__t, document.getElementById('title')); App.focusAfter.cancel(); }"
    )
    settle(fa)
    assert active(fa) == "BODY"


def test_disabled_or_detached_target_is_left_alone(fa: Page) -> None:
    start(fa)
    fa.evaluate(
        "document.getElementById('btn').disabled = true; document.getElementById('other').disabled = true"
    )
    fa.evaluate("App.focusAfter.restore(window.__t, document.getElementById('other'))")
    settle(fa)
    assert active(fa) == "BODY"
    fa.evaluate(
        "document.getElementById('other').disabled = false; document.getElementById('btn').disabled = false"
    )
    start(fa)
    fa.evaluate(
        """() => {
          const t = document.getElementById('title');
          document.getElementById('btn').disabled = true;
          App.focusAfter.restore(window.__t, () => { const el = t; el.remove(); return el; });
        }"""
    )
    settle(fa)
    assert active(fa) == "BODY"


def test_defer_then_flush_runs_once(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('btn').disabled = true")
    fa.evaluate("App.focusAfter.defer(window.__t, () => document.getElementById('title'))")
    settle(fa)
    assert active(fa) == "BODY"  # parked, nothing yet
    assert fa.evaluate("App.focusAfter.flush()") is True
    settle(fa)
    assert active(fa) == "title"
    assert fa.evaluate("App.focusAfter.flush()") is False


def test_cancel_clears_a_deferred_token(fa: Page) -> None:
    start(fa)
    fa.evaluate("document.getElementById('btn').disabled = true")
    fa.evaluate(
        "App.focusAfter.defer(window.__t, () => document.getElementById('title')); App.focusAfter.cancel()"
    )
    assert fa.evaluate("App.focusAfter.flush()") is False
    settle(fa)
    assert active(fa) == "BODY"
