"""Route announcer, document title and dialog-open hardening (M25 F2 flight review).

Router contract tests (literal route text is fine here; the migration guard
exempts ``tests/browser/test_router_*.py``).

* ``#route-announcer`` is one visually-hidden polite live region
  (``role=status``). It is written on a commit that changes destination, section
  or item -- never on boot, never on a ``sync`` (a tab switch).
* ``document.title`` follows every commit (boot included) and every sync.
* A ``showModal()`` that throws must not leave ``App.confirmDialog.isOpen()``
  stuck true, which would make every later navigation resolve Stay.
"""

from __future__ import annotations

import pytest
from browser import _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

BRAND = "GleepGlorp AI"
ANNOUNCER = '[data-testid="route-announcer"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'

# Counts every write to the announcer (text or child changes).
_COUNT_JS = """
(() => {
  window.__announceWrites = 0;
  new MutationObserver(recs => { window.__announceWrites += recs.length; })
    .observe(document.querySelector('[data-testid="route-announcer"]'),
             { childList: true, characterData: true, subtree: true });
})();
"""


def _writes(page: Page) -> int:
    return page.evaluate("window.__announceWrites")


def test_announcer_is_a_polite_status_region_and_empty_at_boot(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "chats")
    region = page.locator(ANNOUNCER)
    expect(region).to_have_count(1)
    expect(region).to_have_attribute("role", "status")
    expect(region).to_have_attribute("aria-live", "polite")
    expect(region).to_have_class("visually-hidden")
    expect(region).to_have_text("")  # boot's first commit is not announced
    expect(page).to_have_title(f"Chats · {BRAND}")


def test_rail_navigation_announces_and_titles_each_destination(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "chats")
    page.evaluate(_COUNT_JS)
    region = page.locator(ANNOUNCER)

    _nav.open_destination(page, "agents")
    expect(region).to_have_text("Agents")
    expect(page).to_have_title(f"Agents · {BRAND}")

    _nav.open_destination(page, "library")
    expect(region).to_have_text("Library — Knowledge")
    expect(page).to_have_title(f"Library — Knowledge · {BRAND}")

    _nav.open_destination(page, "settings")
    expect(region).to_have_text("Settings — General")
    expect(page).to_have_title(f"Settings — General · {BRAND}")

    page.locator(".area-admin .section-nav-item", has_text="Providers").click()
    expect(region).to_have_text("Settings — Providers")
    expect(page).to_have_title(f"Settings — Providers · {BRAND}")

    _nav.open_destination(page, "chats")
    expect(region).to_have_text("Chats")
    expect(page).to_have_title(f"Chats · {BRAND}")
    assert _writes(page) >= 5


def test_opening_an_item_announces_it_and_a_tab_switch_does_not(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.evaluate(_COUNT_JS)
    region = page.locator(ANNOUNCER)

    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/general")
    expect(region).to_have_text(f"Agents — {name}")
    expect(page).to_have_title(f"Agents — {name} · {BRAND}")
    # Settle: nothing else writes the region while we compare counts below.
    page.wait_for_function("window.__announceWrites >= 1")
    before = _writes(page)

    # A tab switch is a sync (same destination and item): title only, no announcement.
    other = page.locator('[role="tab"]:not([data-testid="tab-general"])').first
    tab_id = other.get_attribute("data-testid")
    other.click()
    page.wait_for_function(
        "t => (location.hash.split('/')[2] || '') !== 'general' && !!t", arg=tab_id
    )
    expect(region).to_have_text(f"Agents — {name}")
    assert _writes(page) == before
    expect(page).to_have_title(f"Agents — {name} · {BRAND}")


def test_show_modal_failure_does_not_leave_dialog_count_stuck(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    route = _nav.current_route(page)
    desc = page.locator('[data-field="description"]')
    desc.click()
    desc.fill("dirty edit")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()

    # The next showModal() throws once.
    page.evaluate(
        """() => {
          const orig = HTMLDialogElement.prototype.showModal;
          HTMLDialogElement.prototype.showModal = function () {
            HTMLDialogElement.prototype.showModal = orig;
            throw new Error('showModal boom');
          };
        }"""
    )
    _nav.open_destination(page, "library")
    # The failed open resolves Stay and leaves nothing pending or counted.
    page.wait_for_function("() => !App.router.isDeciding()")
    assert page.evaluate("App.confirmDialog.isOpen()") is False
    assert page.evaluate("App.nav.isPending()") is False
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, route)

    # A later navigation is not stuck as Stay: the dialog opens, Continue leaves.
    _nav.open_destination(page, "library")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    assert page.evaluate("App.confirmDialog.isOpen()") is False
