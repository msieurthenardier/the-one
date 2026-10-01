# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Reusable DD8 dialog-rule checks (M25 F1 L2).

Each ``check_*`` takes a Playwright ``page`` and a :class:`DialogAdapter` and
raises ``AssertionError`` on failure; the message and the returned observation
dict carry the layer counts seen, so a Flight 2 failure against the real wrapper
reads clearly. The adapter is the seam: ``tests/browser/test_ui_dialog_rule.py``
points it at the test-only harness (``_dialog_rule.js``); Flight 2 builds an
adapter for the real wrapper and its real CSS and runs the same checks.

Fixture contract (every adapter's ``setup`` must produce it): openers
``dr-open-a`` and ``dr-open-t`` on the page, ``dr-open-b`` inside dialog A;
dialogs ``dr-dialog-a``, ``dr-dialog-b``, ``dr-dialog-t`` (the only transient
one) and ``dr-confirm``; an outside button ``dr-outside`` whose clicks are
counted in ``window.__outsideClicks``. ``FIXTURE_HTML`` / ``FIXTURE_STYLE``
provide that markup.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from playwright.sync_api import Page

FIXTURE_STYLE = """
body { margin: 0; font-family: sans-serif; }
[data-testid=dr-outside] { position: fixed; right: 12px; bottom: 12px; width: 120px; height: 40px; }
dialog { width: 320px; padding: 0; }
dialog > div { padding: 16px; }
"""

FIXTURE_HTML = """
<button data-testid="dr-open-a">Open A</button>
<button data-testid="dr-open-t">Open chooser</button>
<button data-testid="dr-outside">Outside</button>
<dialog data-testid="dr-dialog-a" id="dr-dlg-a" aria-label="Dialog A"><div>
  <p>Dialog A</p><button data-testid="dr-open-b">Open B</button>
  <button data-testid="dr-a-other">Other</button></div></dialog>
<dialog data-testid="dr-dialog-b" id="dr-dlg-b" aria-label="Dialog B"><div>
  <p>Dialog B</p><button data-testid="dr-b-ok">OK</button></div></dialog>
<dialog data-testid="dr-dialog-t" id="dr-dlg-t" aria-label="Chooser"><div>
  <p>Chooser</p><button data-testid="dr-t-pick">Pick</button></div></dialog>
<dialog data-testid="dr-confirm" id="dr-dlg-confirm" aria-label="Confirm"><div>
  <p>Sure?</p><button data-testid="dr-confirm-yes">Yes</button>
  <button data-testid="dr-confirm-no">No</button></div></dialog>
"""

TRANSIENT_OPENERS = {"dr-open-t"}


@dataclass(frozen=True)
class DialogAdapter:
    """The seam between these checks and the dialog implementation under test.

    ``setup(page)`` builds the fixture page and wires the openers.
    ``open(page, opener_testid, transient=False, via="mouse")`` activates an
    opener with a REAL click (``via="mouse"``) or a real keyboard Enter
    (``via="keyboard"``).
    ``close_topmost(page)`` and ``open_confirm_programmatic(page)`` call the
    implementation directly (the latter with no user activation).
    ``backdrop_css`` is the rule under test (the harness supplies its own; the
    real wrapper's adapter supplies ``""`` because the app ships the rule) and
    ``backdrop_token`` names the custom property that must colour the backdrop.
    """

    name: str
    setup: Callable[[Page], None]
    open: Callable[..., None]
    close_topmost: Callable[[Page], None]
    open_confirm_programmatic: Callable[[Page], None]
    backdrop_css: str
    backdrop_token: str


def layers(page: Page) -> int:
    return page.evaluate("() => document.querySelectorAll('dialog[open]').length")


def open_ids(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('dialog[open]')).map(d => d.dataset.testid)"
    )


def active_testid(page: Page) -> str | None:
    return page.evaluate("() => document.activeElement && document.activeElement.dataset.testid")


def _expect_layers(page: Page, expected: int, step: str, seen: list[int]) -> None:
    count = layers(page)
    seen.append(count)
    assert count == expected, (
        f"{step}: expected {expected} open layer(s), observed {count} ({open_ids(page)}); "
        f"layer counts so far {seen}"
    )


def check_stacked_escape(page: Page, adapter: DialogAdapter) -> dict:
    """(a) Two dialogs opened by real clicks; each real Escape peels one layer."""
    adapter.setup(page)
    seen: list[int] = []
    adapter.open(page, "dr-open-a")
    _expect_layers(page, 1, "after opening A", seen)
    adapter.open(page, "dr-open-b")
    _expect_layers(page, 2, "after opening B over A", seen)
    page.keyboard.press("Escape")
    _expect_layers(page, 1, "after first Escape", seen)
    assert open_ids(page) == ["dr-dialog-a"], (
        f"first Escape peeled the wrong layer: {open_ids(page)}"
    )
    page.keyboard.press("Escape")
    _expect_layers(page, 0, "after second Escape", seen)
    return {"check": "stacked-escape", "layers": seen}


def check_programmatic_confirm(page: Page, adapter: DialogAdapter) -> dict:
    """(b) A confirm opened programmatically over a click-opened modal (no user
    activation in between: the CloseWatcher-grouping case); each Escape peels one."""
    adapter.setup(page)
    seen: list[int] = []
    adapter.open(page, "dr-open-a")
    _expect_layers(page, 1, "after opening A", seen)
    adapter.open_confirm_programmatic(page)
    _expect_layers(page, 2, "after programmatic confirm", seen)
    page.keyboard.press("Escape")
    _expect_layers(page, 1, "after first Escape", seen)
    assert open_ids(page) == ["dr-dialog-a"], (
        f"first Escape peeled the wrong layer: {open_ids(page)}"
    )
    page.keyboard.press("Escape")
    _expect_layers(page, 0, "after second Escape", seen)
    return {"check": "programmatic-confirm", "layers": seen}


def check_focus_restore(page: Page, adapter: DialogAdapter, via: str) -> dict:
    """(c) Focus returns to the opener after a mouse (or keyboard) open + Escape,
    and to the inner opener after a stacked peel."""
    adapter.setup(page)
    seen: list[int] = []
    adapter.open(page, "dr-open-a", via=via)
    _expect_layers(page, 1, f"after {via} open", seen)
    page.keyboard.press("Escape")
    _expect_layers(page, 0, "after Escape", seen)
    focused = page.evaluate(
        "() => document.activeElement === document.querySelector('[data-testid=dr-open-a]')"
    )
    assert focused, (
        f"focus not restored to the opener after a {via} open; active={active_testid(page)}"
    )
    adapter.open(page, "dr-open-a", via=via)
    adapter.open(page, "dr-open-b", via=via)
    _expect_layers(page, 2, "after stacked open", seen)
    page.keyboard.press("Escape")
    inner = page.evaluate(
        "() => document.activeElement === document.querySelector('[data-testid=dr-open-b]')"
    )
    assert inner, (
        f"focus not restored to the inner opener after a peel; active={active_testid(page)}"
    )
    page.keyboard.press("Escape")
    _expect_layers(page, 0, "after final Escape", seen)
    return {"check": f"focus-restore-{via}", "layers": seen}


def check_backdrop_clicks(page: Page, adapter: DialogAdapter) -> dict:
    """(d) A backdrop click closes a transient dialog but not a confirm."""
    adapter.setup(page)
    seen: list[int] = []
    adapter.open(page, "dr-open-t", transient=True)
    _expect_layers(page, 1, "after opening the transient chooser", seen)
    page.mouse.click(5, 5)  # outside every dialog: lands on the backdrop
    _expect_layers(page, 0, "after a backdrop click on the transient chooser", seen)
    adapter.open(page, "dr-open-a")
    adapter.open_confirm_programmatic(page)
    _expect_layers(page, 2, "after opening A and a confirm", seen)
    page.mouse.click(5, 5)
    _expect_layers(page, 2, "after a backdrop click on the confirm (must NOT close)", seen)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    _expect_layers(page, 0, "after cleanup", seen)
    return {"check": "backdrop-clicks", "layers": seen}


def check_inertness(page: Page, adapter: DialogAdapter, tabs: int = 8) -> dict:
    """(e) While a modal is open, an outside button cannot be activated.

    Positive control first: Tab must reach the dialog's own buttons in this
    engine. If it never leaves the first button, fall back to focus() plus
    elementFromPoint evidence and record that, never passing vacuously."""
    adapter.setup(page)
    seen: list[int] = []
    adapter.open(page, "dr-open-a")
    _expect_layers(page, 1, "after opening A", seen)
    probe = """() => {
      const a = document.activeElement;
      if (!a || a === document.body || a === document.documentElement) return ['(body)', true];
      return [a.dataset.testid || a.tagName.toLowerCase(), !!a.closest('dialog[open]')];
    }"""
    steps = [page.evaluate(probe)]
    for _ in range(tabs):
        page.keyboard.press("Tab")
        steps.append(page.evaluate(probe))
    sequence = [name for name, _inside in steps]
    dialog_buttons = {"dr-open-b", "dr-a-other"}
    tab_reaches_buttons = len(dialog_buttons & set(sequence)) == len(dialog_buttons)
    box = page.locator("[data-testid=dr-outside]").bounding_box()
    assert box is not None
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.click(cx, cy)
    clicks = page.evaluate("() => window.__outsideClicks || 0")
    assert clicks == 0, f"outside button received {clicks} click(s) while a modal was open"
    _expect_layers(page, 1, "after clicking the outside button's centre", seen)
    hit = page.evaluate(
        "([x, y]) => { const e = document.elementFromPoint(x, y); return e && (e.dataset.testid || e.tagName); }",
        [cx, cy],
    )
    assert hit != "dr-outside", "elementFromPoint at the outside button still hits the button"
    note = ""
    if tab_reaches_buttons:
        # "(body)" is the engine handing focus to browser chrome, not a page element;
        # the dialog element itself is inside the dialog.
        escaped = [name for name, inside in steps if not inside]
        assert not escaped, f"Tab reached an element outside the open modal: {sequence}"
    else:
        note = f"Tab did not reach the dialog's buttons in this engine ({sequence}); used focus()"
        page.evaluate("() => document.querySelector('[data-testid=dr-outside]').focus()")
        assert active_testid(page) != "dr-outside", "focus() reached an inert outside button"
    page.keyboard.press("Escape")
    _expect_layers(page, 0, "after Escape", seen)
    return {
        "check": "inertness",
        "layers": seen,
        "tab_reaches_buttons": tab_reaches_buttons,
        "tab_sequence": sequence,
        "note": note,
    }


_LITERAL_PROBE = "rgb(1, 2, 3)"


def check_backdrop_colour(page: Page, adapter: DialogAdapter) -> dict:
    """(f) The backdrop's computed colour equals the resolved token value.

    Returns ``{"status": "unverifiable", ...}`` (never a pass) when the engine
    does not report ``::backdrop`` computed styles at all, proven by a literal
    control rule it also fails to report. A mismatch when the literal control IS
    reported is a real failure: the custom property did not reach ``::backdrop``."""
    adapter.setup(page)
    seen: list[int] = []
    page.add_style_tag(content="#dr-dlg-b::backdrop { background-color: " + _LITERAL_PROBE + "; }")
    expected = page.evaluate(
        """(token) => {
          const probe = document.createElement('div');
          probe.style.backgroundColor = 'var(' + token + ')';
          document.body.appendChild(probe);
          const value = getComputedStyle(probe).backgroundColor;
          probe.remove();
          return value;
        }""",
        adapter.backdrop_token,
    )
    adapter.open(page, "dr-open-a")
    _expect_layers(page, 1, "after opening A", seen)
    reported = page.evaluate(
        "() => getComputedStyle(document.querySelector('[data-testid=dr-dialog-a]'), '::backdrop').backgroundColor"
    )
    adapter.open(page, "dr-open-b")
    literal = page.evaluate(
        "() => getComputedStyle(document.querySelector('[data-testid=dr-dialog-b]'), '::backdrop').backgroundColor"
    )
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    _expect_layers(page, 0, "after cleanup", seen)
    result = {
        "check": "backdrop-colour",
        "layers": seen,
        "expected": expected,
        "reported": reported,
    }
    if literal != _LITERAL_PROBE:
        result["status"] = "unverifiable"
        result["reason"] = (
            f"engine does not report ::backdrop computed styles (literal control read {literal!r})"
        )
        return result
    assert expected not in ("", "rgba(0, 0, 0, 0)"), (
        f"token {adapter.backdrop_token} did not resolve"
    )
    assert reported == expected, (
        f"::backdrop colour {reported!r} != resolved {adapter.backdrop_token} {expected!r}: "
        "the custom property did not reach the backdrop"
    )
    result["status"] = "pass"
    return result
