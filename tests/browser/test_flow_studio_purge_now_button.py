"""End-to-end flow test: Purge-now button in the General-tab Danger Zone (M13 F2 leg 02).

Covers the DOM-level placement + arm wiring of the "Purge now" control added
alongside the Delete agent button in the General tab's Danger Zone:

- The purge button renders in the Danger Zone for existing agents, with
  data-testid="purge-history-btn" and a [data-confirm-title] "Purge now" span.
- It is textually distinct from Delete agent (an operator cannot confuse
  "wipe history" with "delete the agent").
- Clicking once ARMS via App.confirmDelete — the [data-confirm-title] label
  swaps to "Confirm purge?" — without firing the DELETE. (The full two-step
  confirm -> history-gone flow is owned by the behavior test, NOT duplicated
  here; this test clicks exactly ONCE.)
"""

from __future__ import annotations

import re

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect


def _wait_editor_ready(page: Page) -> None:
    """Wait for the agent editor (General tab) to be the visible main-panel child.

    Bare `#agents` shows the list beside an empty detail pane, with no agent
    auto-selected; click the first list row to mount the editor, then wait for
    the General tab to
    be active (handles the L5 async editor-mount race).
    """
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    editor_hidden = page.evaluate(
        "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
    )
    if editor_hidden:
        _lists.first_row(page, "agents").click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


@pytest.mark.browser
def test_purge_button_present_in_danger_zone(app_with_agent: SeededApp, page: Page) -> None:
    """Purge-now button renders in the Danger Zone, distinct from Delete agent."""
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    purge_btn = page.locator('[data-testid="purge-history-btn"]')
    delete_btn = page.locator('[data-testid="delete-agent-btn"]')

    # Both live inside the Danger Zone section.
    danger_zone = page.locator(".danger-zone")
    expect(danger_zone).to_be_visible()
    expect(danger_zone.locator('[data-testid="purge-history-btn"]')).to_have_count(1)
    expect(danger_zone.locator('[data-testid="delete-agent-btn"]')).to_have_count(1)

    expect(purge_btn).to_be_visible()

    # The purge button carries a [data-confirm-title] span reading "Purge now".
    purge_title = purge_btn.locator("[data-confirm-title]")
    expect(purge_title).to_have_text("Purge now")

    # Textually distinct from Delete agent — no operator confusion.
    purge_text = (purge_btn.inner_text() or "").strip()
    delete_text = (delete_btn.inner_text() or "").strip()
    assert purge_text != delete_text, (
        f"Purge ({purge_text!r}) must be text-distinct from Delete ({delete_text!r})"
    )


@pytest.mark.browser
def test_purge_button_arms_on_single_click(app_with_agent: SeededApp, page: Page) -> None:
    """A single click ARMS the purge button — label swaps to 'Confirm purge?'.

    Clicks exactly ONCE: a second click would fire the real DELETE. The
    fire -> history-gone flow is the behavior test's responsibility.
    """
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    purge_btn = page.locator('[data-testid="purge-history-btn"]')
    purge_title = purge_btn.locator("[data-confirm-title]")
    expect(purge_title).to_have_text("Purge now")

    # Single click arms via App.confirmDelete — label swaps, no DELETE fired.
    purge_btn.click()

    expect(purge_title).to_have_text("Confirm purge?")
    # App.confirmDelete adds the shared armed-state class on arm.
    expect(purge_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))


@pytest.mark.browser
def test_purge_button_confirm_lapse_is_visually_distinct(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the Purge-now confirm
    (`studio.js:2116`) is distinguishable on screen from one that was never
    armed, past the real 3s `revertMs`. This test only exercises the timeout
    path, which never reaches `onConfirm` at all (a completed purge reverts
    the button itself: see `test_purge_button_returns_to_normal_after_purge`)."""
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    purge_btn = page.locator('[data-testid="purge-history-btn"]')
    purge_title = purge_btn.locator("[data-confirm-title]")
    expect(purge_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    purge_btn.click()
    expect(purge_title).to_have_text("Confirm purge?")
    expect(purge_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(purge_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(purge_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(purge_title).to_have_text("Purge now")


@pytest.mark.browser
def test_danger_zone_is_two_stacked_rows_purge_first(app_with_agent: SeededApp, page: Page) -> None:
    """Operator layout (M33 F4 HAT): Purge row first, then Delete row, each with a heading and
    a description, the button text and test ids unchanged."""
    _nav.goto(page, app_with_agent.base_url, "agents")
    _wait_editor_ready(page)
    rows = page.locator(".danger-zone .danger-zone-row")
    expect(rows).to_have_count(2)
    expect(rows.nth(0).locator(".danger-zone-row-heading")).to_have_text("Purge chats and history")
    expect(rows.nth(0).locator(".danger-zone-row-desc")).to_have_text(
        "Deletes this agent's chats, its routines' run history and its finished approval "
        "history. The agent, its routines, rules, notes and any changes still waiting for "
        "approval are kept."
    )
    expect(rows.nth(0).locator('[data-testid="purge-history-btn"]')).to_have_text("Purge now")
    expect(rows.nth(1).locator(".danger-zone-row-heading")).to_have_text("Permanently delete agent")
    expect(rows.nth(1).locator('[data-testid="delete-agent-btn"]')).to_have_text("Delete agent")
    tops = [r.bounding_box()["y"] for r in rows.all()]
    assert tops[0] < tops[1], tops  # stacked, Purge above Delete


@pytest.mark.browser
def test_purge_button_returns_to_normal_after_purge(app_with_agent: SeededApp, page: Page) -> None:
    """F-G-1: after a completed purge the button reads "Purge now" again (not armed)."""
    base_url = app_with_agent.base_url
    seed_session(base_url, app_with_agent.agent_name, "to be purged", "2026-01-01T10:00:00+00:00")
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)
    purge_btn = page.locator('[data-testid="purge-history-btn"]')
    purge_title = purge_btn.locator("[data-confirm-title]")
    purge_btn.click()
    expect(purge_title).to_have_text("Confirm purge?")
    purge_btn.click()
    expect(page.locator(".app-flash")).to_contain_text("Deleted 1 chat and its history.")
    expect(purge_title).to_have_text("Purge now")
    expect(purge_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(purge_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
