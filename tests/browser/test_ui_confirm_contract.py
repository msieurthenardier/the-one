# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Browser test: `App.confirmDelete`'s own arm/commit/lapse/revert contract
(`the_one/interfaces/web/static/js/ui/confirm.js`), independent of any one
call site.

Mission 24 Flight 7 confirm-lapse leg, AC-9a: the helper has no "area" of
its own — it is a shared helper reached by 14 call sites across 8 files. This
is the one test of the CONTRACT itself.

M31 F1 L4: the helper moved into the control library as `App.ui.confirm`
(`App.confirmDelete` is the same function) and this file joined the `contracts`
lane, running in Chromium and WebKit through `engine_page` + `load_harness`.

Exercises the helper directly via `page.evaluate` against a synthetic
`<button>` built on the disk harness (`ui/confirm.js` is loaded from
`index.html`) — no call site's markup or wiring is involved, so this pins
the CONTRACT rather than any one integration.
"""

from __future__ import annotations

import re

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _mount_fixture(page: Page) -> None:
    """Build a synthetic itemEl with a [data-confirm-title] child, matching
    the shape every real call site provides, but tied to none of them."""
    page.evaluate(
        """
        () => {
          document.body.innerHTML =
            '<button id="probe"><span data-confirm-title>Original Title</span></button>';
        }
        """
    )


def test_first_click_arms_second_click_commits(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    _mount_fixture(page)

    calls = page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          var calls = [];
          window.App.confirmDelete(el, function (itemEl, revertFn) {
            calls.push('committed');
          });
          return {
            afterFirst: {
              armed: el.classList.contains('confirm-delete'),
              title: el.querySelector('[data-confirm-title]').textContent,
              calls: calls.slice()
            }
          };
        }
        """
    )
    assert calls["afterFirst"]["armed"] is True
    assert calls["afterFirst"]["title"] == "Confirm delete?"
    assert calls["afterFirst"]["calls"] == []

    result = page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          var calls = [];
          window.App.confirmDelete(el, function (itemEl, revertFn) {
            calls.push('committed');
          });
          return { armed: el.classList.contains('confirm-delete'), calls: calls };
        }
        """
    )
    assert result["calls"] == ["committed"], (
        "second click within the window must commit exactly once"
    )


def test_capture_discipline_only_first_click_captures_original_title(engine_page: Page) -> None:
    """ui/confirm.js's own header comment: capturing on every call would
    record the placeholder ('Confirm delete?') on the second click, and a
    subsequent revert would overwrite the operator's data."""
    page = engine_page
    load_harness(page)
    _mount_fixture(page)

    original = page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          var revertFn;
          window.App.confirmDelete(el, function () {}); // arm
          window.App.confirmDelete(el, function (itemEl, r) { revertFn = r; }); // commit
          revertFn(); // simulate a transport-failure rollback
          return el.querySelector('[data-confirm-title]').textContent;
        }
        """
    )
    assert original == "Original Title", (
        f"revert() restored {original!r} — capture discipline regressed "
        "(should be the pre-arm title, not the 'Confirm delete?' placeholder)"
    )


def test_lapse_is_visually_distinct_and_clears_on_next_interaction(engine_page: Page) -> None:
    """AC-4/AC-7: a lapsed control carries `.confirm-lapsed`, distinct from
    both never-armed and committed, restores the ORIGINAL title (not the
    placeholder), and the cue clears on the control's next interaction —
    the helper's only definition of "next interaction"."""
    page = engine_page
    load_harness(page)
    _mount_fixture(page)

    page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          window.App.confirmDelete(el, function () {}, { revertMs: 1500 });
        }
        """
    )
    probe = page.locator("#probe")
    expect(probe).to_have_class(re.compile(r"\bconfirm-delete\b"))

    # Past the (shortened, test-only) revertMs: lapsed, not never-armed.
    expect(probe).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=6000)
    expect(probe).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(probe.locator("[data-confirm-title]")).to_have_text("Original Title")

    # Next interaction (a fresh arm) clears the lapse cue. This synthetic
    # fixture has no click LISTENER wired (unlike every real call site) —
    # invoke confirmDelete directly again, the same "next call to
    # confirmDelete for this itemEl" the helper itself defines as the
    # clearing trigger.
    page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          window.App.confirmDelete(el, function () {}, { revertMs: 1500 });
        }
        """
    )
    expect(probe).to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(probe).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))


def test_revertfn_success_path_never_marks_lapse(engine_page: Page) -> None:
    """AC-6a: `revert()` is the SAME function handed to callers as
    `revertFn` — invoked on a transport failure AND (per
    `system-page.js:87-91`'s precedent) on a caller's SUCCESS path. Neither
    must ever mark `.confirm-lapsed` — only the timer's own expiry callback
    does that, and this test never lets the timer fire."""
    page = engine_page
    load_harness(page)
    _mount_fixture(page)

    result = page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          var revertFn;
          window.App.confirmDelete(el, function () {}, { revertMs: 60000 }); // arm, long timer
          window.App.confirmDelete(el, function (itemEl, r) { revertFn = r; }); // commit
          // Simulate a caller's SUCCESS path invoking revertFn (system-page.js
          // precedent) well before the timer could ever fire.
          revertFn();
          return {
            armed: el.classList.contains('confirm-delete'),
            lapsed: el.classList.contains('confirm-lapsed'),
            title: el.querySelector('[data-confirm-title]').textContent
          };
        }
        """
    )
    assert result["armed"] is False
    assert result["lapsed"] is False, "a successful commit's revertFn() must never mark lapse"
    assert result["title"] == "Original Title"


def test_revert_is_idempotent(engine_page: Page) -> None:
    """AC-8: revert() is safe to call more than once — callers invoke it
    from a `.catch`, and a second call must not throw or corrupt state."""
    page = engine_page
    load_harness(page)
    _mount_fixture(page)

    result = page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          var revertFn;
          window.App.confirmDelete(el, function () {});
          window.App.confirmDelete(el, function (itemEl, r) { revertFn = r; });
          revertFn();
          revertFn(); // second call — must not throw
          return {
            armed: el.classList.contains('confirm-delete'),
            lapsed: el.classList.contains('confirm-lapsed'),
            title: el.querySelector('[data-confirm-title]').textContent
          };
        }
        """
    )
    assert result == {"armed": False, "lapsed": False, "title": "Original Title"}


def test_missing_title_element_does_not_throw(engine_page: Page) -> None:
    """Edge case: `titleEl` missing. The helper already guards
    `if (titleEl)` for the title-restore path; the lapse cue lives on
    `itemEl` itself and must not assume `titleEl` exists either."""
    page = engine_page
    load_harness(page)
    page.evaluate("() => { document.body.innerHTML = '<button id=\"probe\"></button>'; }")

    result = page.evaluate(
        """
        () => {
          var el = document.getElementById('probe');
          var threw = false;
          try {
            window.App.confirmDelete(el, function () {}, { revertMs: 30 });
          } catch (e) {
            threw = true;
          }
          return { threw: threw, armed: el.classList.contains('confirm-delete') };
        }
        """
    )
    assert result["threw"] is False
    assert result["armed"] is True

    probe = page.locator("#probe")
    expect(probe).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=2000)
    expect(probe).to_have_class(re.compile(r"\bconfirm-lapsed\b"))


def test_alias_is_the_same_function(engine_page: Page) -> None:
    load_harness(engine_page)
    assert engine_page.evaluate("() => App.confirmDelete === App.ui.confirm") is True


def test_arms_commits_and_lapses_on_summary_and_li(engine_page: Page) -> None:
    """Unmigrated callers: the KB folder `<summary>` and chat-row `<li>`."""
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """
        async () => {
          const res = {};
          for (const tag of ['summary', 'li']) {
            const host = document.createElement(tag === 'li' ? 'ul' : 'details');
            const node = document.createElement(tag);
            const t = document.createElement('span');
            t.setAttribute('data-confirm-title', '');
            t.textContent = 'Name';
            node.appendChild(t);
            host.appendChild(node);
            document.getElementById('harness-root').appendChild(host);
            const calls = [];
            App.ui.confirm(node, () => calls.push('x'), {revertMs: 60});
            const armed = node.classList.contains('confirm-delete');
            const label = t.textContent;
            await new Promise((r) => setTimeout(r, 150));
            const lapsed = node.classList.contains('confirm-lapsed') &&
              !node.classList.contains('confirm-delete') && t.textContent === 'Name';
            App.ui.confirm(node, () => calls.push('commit'), {revertMs: 60000});
            App.ui.confirm(node, () => calls.push('commit'), {revertMs: 60000});
            res[tag] = {armed, label, lapsed, calls};
          }
          return res;
        }
        """
    )
    for tag in ("summary", "li"):
        assert out[tag] == {
            "armed": True, "label": "Confirm delete?", "lapsed": True, "calls": ["commit"],
        }  # fmt: skip


def test_armed_button_looks_armed_even_while_hovered(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """
        () => {
          const root = document.getElementById('harness-root');
          const st = document.createElement('style');
          st.textContent = '*, *::before, *::after { transition: none !important; }';
          document.head.appendChild(st);
          for (const cls of ['btn-outlined-primary', 'btn-muted-destructive']) {
            const b = document.createElement('button');
            b.type = 'button';
            b.id = 'b-' + cls;
            b.className = cls;
            b.innerHTML = '<span data-confirm-title>Go</span>';
            root.appendChild(b);
          }
        }
        """
    )
    for cls in ("btn-outlined-primary", "btn-muted-destructive"):
        btn = page.locator(f"#b-{cls}")
        before = btn.evaluate("e => getComputedStyle(e).borderTopColor")
        btn.evaluate("e => App.ui.confirm(e, function () {}, {revertMs: 60000})")
        page.mouse.move(0, 0)
        armed = btn.evaluate(
            "e => ({bg: getComputedStyle(e).backgroundColor, bc: getComputedStyle(e).borderTopColor})"
        )
        assert armed["bc"] != before, cls
        danger = page.evaluate(
            "() => { const d = document.createElement('div'); d.style.color = 'var(--status-danger)';"
            " document.getElementById('harness-root').appendChild(d); const c = getComputedStyle(d).color; d.remove(); return c; }"
        )
        assert armed["bg"] == danger, cls
        btn.hover()
        hovered = btn.evaluate(
            "e => ({bg: getComputedStyle(e).backgroundColor, bc: getComputedStyle(e).borderTopColor})"
        )
        assert hovered == armed, (cls, hovered, armed)
        btn.focus()
        assert btn.evaluate("e => getComputedStyle(e).backgroundColor") == armed["bg"]
