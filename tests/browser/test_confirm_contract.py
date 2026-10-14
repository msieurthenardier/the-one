"""Browser test: `App.confirmDelete`'s own arm/commit/lapse/revert contract
(`the_one/interfaces/web/static/js/confirm.js`), independent of any one
call site.

Mission 24 Flight 7 confirm-lapse leg, AC-9a: the helper has no "area" of
its own — it is a shared helper reached by 13 call sites across 8 files,
spanning the `studio`, `system`, and `chat` browser lanes (leg AC-9). This
is the one test of the CONTRACT itself, deliberately named so it falls to
the `shared` complement lane (it matches none of `test_flow_studio_*`,
`test_studio_*`, `test_mcp_*`, `test_flow_agent_*`, `test_flow_admin_*`,
`test_flow_provider_*`, `test_flow_chat*`, `test_flow_new_chat.py`, etc.) —
what actually puts `shared` in scope for this leg, not a miscategorised
existing test.

Exercises the helper directly via `page.evaluate` against a synthetic
`<button>` built on any loaded page (`confirm.js` is loaded globally, see
`index.html`) — no call site's markup or wiring is involved, so this pins
the CONTRACT rather than any one integration.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


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


@pytest.mark.browser
def test_first_click_arms_second_click_commits(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
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


@pytest.mark.browser
def test_capture_discipline_only_first_click_captures_original_title(
    app_clean: str, page: Page
) -> None:
    """confirm.js's own header comment: capturing on every call would
    record the placeholder ('Confirm delete?') on the second click, and a
    subsequent revert would overwrite the operator's data."""
    page.goto(app_clean)
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


@pytest.mark.browser
def test_lapse_is_visually_distinct_and_clears_on_next_interaction(
    app_clean: str, page: Page
) -> None:
    """AC-4/AC-7: a lapsed control carries `.confirm-lapsed`, distinct from
    both never-armed and committed, restores the ORIGINAL title (not the
    placeholder), and the cue clears on the control's next interaction —
    the helper's only definition of "next interaction"."""
    page.goto(app_clean)
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


@pytest.mark.browser
def test_revertfn_success_path_never_marks_lapse(app_clean: str, page: Page) -> None:
    """AC-6a: `revert()` is the SAME function handed to callers as
    `revertFn` — invoked on a transport failure AND (per
    `system-page.js:87-91`'s precedent) on a caller's SUCCESS path. Neither
    must ever mark `.confirm-lapsed` — only the timer's own expiry callback
    does that, and this test never lets the timer fire."""
    page.goto(app_clean)
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


@pytest.mark.browser
def test_revert_is_idempotent(app_clean: str, page: Page) -> None:
    """AC-8: revert() is safe to call more than once — callers invoke it
    from a `.catch`, and a second call must not throw or corrupt state."""
    page.goto(app_clean)
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


@pytest.mark.browser
def test_missing_title_element_does_not_throw(app_clean: str, page: Page) -> None:
    """Edge case: `titleEl` missing. The helper already guards
    `if (titleEl)` for the title-restore path; the lapse cue lives on
    `itemEl` itself and must not assume `titleEl` exists either."""
    page.goto(app_clean)
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
