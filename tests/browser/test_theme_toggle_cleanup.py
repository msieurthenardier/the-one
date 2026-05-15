"""Regression test for the H1 theme-toggle document-listener leak.

M08 F7 L03 fix: `theme.js` previously stored its cleanup closure on the
container element as `container._themeListenerCleanup`. When admin's
`system-page.js` re-rendered by rewriting its host `innerHTML`, the old
container was discarded, the expando went with it, and the document-level
`theme-preference-changed` listener was orphaned. After N admin renders
the document held N listeners, all of them firing on every theme change.

The fix moves cleanup to a module-scoped `_activeThemeListenerCleanup`
variable. This test simulates the H1 scenario directly in the browser:

  1. Render the toggle into container1 (inside a host element).
  2. Rewrite the host's `.innerHTML` to discard container1 (mirrors what
     `system-page.js` does on each admin re-render — container1 is now a
     detached subtree, retained only by closures).
  3. Render the toggle into a fresh container2 inside the same host.
  4. Dispatch `theme-preference-changed`.
  5. Assert ONLY container2's `.admin-theme-option.active` reflects the
     new preference. Container1, being detached, must NOT have its
     listener still firing — under the buggy code, container1's
     update-active-option callback would still run and toggle classes on
     its (orphan) buttons.

The detached container1 is kept alive in a JS variable so its DOM state
remains inspectable; in production the GC would reap it once H1 is fixed.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_theme_toggle_cleanup_survives_container_replacement(
    app_clean: str, page: Page
) -> None:
    """After re-rendering the toggle into a fresh container post-innerHTML
    rewrite, dispatching THEME_EVENT must update ONLY the new container."""
    # Land on any route — theme.js is loaded in <head> of index.html for
    # every hash route, so App.theme.renderToggle is wired before any
    # area-page boot. Using the chat root (default landing) keeps boot
    # minimal compared to admin sub-pages.
    page.goto(app_clean)

    # Confirm App.theme.renderToggle is available before running the
    # scenario. theme.js loads synchronously in <head>, so by the time
    # `goto` resolves (document parsed) it should already be on App.
    page.wait_for_function(
        "typeof window.App === 'object' && window.App.theme "
        "&& typeof window.App.theme.renderToggle === 'function'",
        timeout=10000,
    )

    # Run the regression scenario entirely in-page. The script returns a
    # dict so we can assert on both containers' states in one round-trip.
    result = page.evaluate(
        """
        () => {
          // Set a known starting preference.
          window.App.theme.set('light');

          // Build host element and first container.
          const host = document.createElement('div');
          host.id = '__theme_cleanup_host__';
          document.body.appendChild(host);
          const c1 = document.createElement('div');
          host.appendChild(c1);

          // First render — under buggy code this attaches listener #1.
          window.App.theme.renderToggle(c1, {});

          // Detach c1 by rewriting host.innerHTML (mirrors system-page.js).
          // c1 is now detached but still referenced by this closure, so it
          // remains inspectable. Its buttons are unchanged.
          host.innerHTML = '';
          // Sanity: c1 is no longer in the document tree.
          const c1Attached = document.body.contains(c1);

          // Fresh container, fresh render. Under the fix, the prologue's
          // module-scoped cleanup invokes listener #1's removeEventListener
          // BEFORE wiring listener #2 — so listener #1 is gone.
          const c2 = document.createElement('div');
          host.appendChild(c2);
          window.App.theme.renderToggle(c2, {});

          // Snapshot c1's active option BEFORE the dispatch so we can
          // confirm the dispatch did not mutate it.
          const c1ActiveBefore = c1.querySelector('.admin-theme-option.active');
          const c1ActiveBeforePref = c1ActiveBefore
            ? c1ActiveBefore.getAttribute('data-theme-pref')
            : null;

          // Dispatch THEME_EVENT directly — set() also dispatches, but
          // dispatching by hand isolates this test from the set() flow and
          // matches the leg's acceptance-criteria phrasing.
          document.dispatchEvent(
            new CustomEvent('theme-preference-changed', { detail: { pref: 'dark' } })
          );

          // c1 should be UNCHANGED — its listener was cleaned up.
          const c1ActiveAfter = c1.querySelector('.admin-theme-option.active');
          const c1ActiveAfterPref = c1ActiveAfter
            ? c1ActiveAfter.getAttribute('data-theme-pref')
            : null;

          // c2 should reflect the new 'dark' preference.
          const c2Active = c2.querySelector('.admin-theme-option.active');
          const c2ActivePref = c2Active ? c2Active.getAttribute('data-theme-pref') : null;

          // Clean up DOM mutation so it doesn't leak into subsequent tests.
          host.remove();

          return {
            c1Attached,
            c1ActiveBeforePref,
            c1ActiveAfterPref,
            c2ActivePref,
          };
        }
        """
    )

    # Container1 was detached by the innerHTML rewrite.
    assert result["c1Attached"] is False, "c1 should be detached after host.innerHTML rewrite"

    # Container1's active option must NOT have changed in response to the
    # dispatch. If the buggy code were still in place, c1's orphan listener
    # would have flipped its active state to 'dark'.
    assert result["c1ActiveBeforePref"] == result["c1ActiveAfterPref"], (
        f"c1 active option changed across dispatch "
        f"(before={result['c1ActiveBeforePref']!r}, "
        f"after={result['c1ActiveAfterPref']!r}); "
        "the per-container listener was NOT cleaned up — H1 has regressed."
    )

    # Container2 must have updated to reflect the dispatched preference.
    assert result["c2ActivePref"] == "dark", (
        f"c2 active option is {result['c2ActivePref']!r}, expected 'dark'; "
        "the new renderToggle's listener did not fire."
    )
