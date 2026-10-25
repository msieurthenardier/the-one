"""Cross-tab theme synchronization regression test (M17 F2 L3).

theme.js installs a ``window.addEventListener('storage', ...)`` listener
so a theme preference set in ONE tab propagates live to every other open
tab of the app. Both directions are covered:

- **set**: writing ``theme-preference`` in tab A fires ``storage`` in
  tab B (value change) → B reapplies and re-renders its toggle.
- **unset**: choosing Auto REMOVES the key, so the event arrives in B
  with ``newValue === null`` → B must degrade to auto (NOT keep the
  stale explicit theme).

Apparatus notes (leg design decisions):

- Both pages come from the SAME BrowserContext via
  ``page.context.new_page()`` — ``storage`` events never cross browser
  contexts (separate localStorage partitions), so ``browser.new_context()``
  would vacuously pass nothing.
- The context pins ``color_scheme="no-preference"`` (see conftest
  ``page`` fixture). Measured ground truth (this leg): Chromium under
  that emulation MATCHES ``(prefers-color-scheme: light)`` — the
  no-preference state was dropped from the spec — so theme.js's auto
  resolves to **light** (the "neither matches → dark" canonical default
  is unreachable in this harness). The sequence is therefore
  dark → auto, which makes the null-path observable as a light←dark
  flip.
- Tab A is driven through the Appearance page's real theme control (click
  the radio), not ``App.theme.set`` — realism over convenience.
- Assertions on tab B cover BOTH ``data-theme`` AND the mounted
  toggle's checked state: ``data-theme`` alone would still pass if the
  listener forgot to dispatch ``theme-preference-changed`` (the mounted
  toggle would silently desync).
- ``expect`` web-first assertions poll — storage event delivery is
  async; no fixed sleeps.
"""

from __future__ import annotations

import pytest
from browser import _nav
from playwright.sync_api import Page, expect


def _toggle_option(page: Page, pref: str):
    return page.locator(f'[data-testid="theme-option-{pref}"]')


@pytest.mark.browser
def test_theme_set_and_unset_propagate_across_tabs(app_clean: str, page: Page) -> None:
    """A theme chosen in tab A applies live in tab B; choosing Auto in A
    (key removal → storage newValue === null) reverts B to auto."""
    # Tab A — the driving tab, on the Appearance page (theme control mounted;
    # the System/General page's Appearance block until M25 F3 leg 5a).
    page_a = page
    _nav.goto(page_a, app_clean, "settings/appearance")
    expect(_toggle_option(page_a, "auto")).to_be_visible()

    # Tab B — SAME BrowserContext (shared localStorage; storage events
    # do not cross contexts). Also on the Appearance page so the receiving
    # tab has a mounted toggle whose checked state we can assert.
    page_b = page_a.context.new_page()
    try:
        _nav.goto(page_b, app_clean, "settings/appearance")
        expect(_toggle_option(page_b, "auto")).to_be_visible()

        # Baseline: no stored preference; auto resolves LIGHT under the
        # harness's color-scheme emulation (see module docstring) — in
        # both tabs.
        expect(page_a.locator("html")).to_have_attribute("data-theme", "light")
        expect(page_b.locator("html")).to_have_attribute("data-theme", "light")

        # ── Direction 1: SET propagates ────────────────────────────────
        # Drive tab A via the real Appearance-page control.
        _toggle_option(page_a, "dark").click()
        expect(page_a.locator("html")).to_have_attribute("data-theme", "dark")

        # Tab B: document theme reapplied from the storage event...
        expect(page_b.locator("html")).to_have_attribute("data-theme", "dark")
        # ...AND the mounted toggle re-checked (proves the listener also
        # dispatched theme-preference-changed, not just apply()).
        expect(_toggle_option(page_b, "dark")).to_be_checked()
        expect(_toggle_option(page_b, "auto")).not_to_be_checked()

        # ── Direction 2: UNSET propagates (newValue === null path) ─────
        # Auto REMOVES the localStorage key in tab A.
        _toggle_option(page_a, "auto").click()
        expect(page_a.locator("html")).to_have_attribute("data-theme", "light")

        # Tab B must degrade to auto (resolved light), not keep dark.
        expect(page_b.locator("html")).to_have_attribute("data-theme", "light")
        expect(_toggle_option(page_b, "auto")).to_be_checked()
        expect(_toggle_option(page_b, "dark")).not_to_be_checked()
    finally:
        page_b.close()
