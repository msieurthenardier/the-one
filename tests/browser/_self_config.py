"""Helpers for the Self-configuration tab's two switches (M31 F2 L10c).

The switches are ``App.ui.toggle`` (a visually hidden ``role=switch`` input and a
drawn track), so a test finds one by its accessible name and clicks the track.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

ENABLE_SWITCH = "Let this agent edit its description and system prompt"
APPROVAL_SWITCH = "Require approval for prompt edits"


def switch(page: Page, name: str) -> Locator:
    """The switch input with this accessible name."""
    return page.get_by_role("switch", name=name)


PROMPT_WAITING = "self-config-prompt-waiting"
PROMPT_HISTORY = "revision-history-details"
ROUTINES_WAITING = "self-config-routines-waiting"
ROUTINES_HISTORY = "self-config-routines-history-details"


def expander(page: Page, testid: str) -> Locator:
    """A card expander's ``<details>`` (M33 F4 L06)."""
    return page.locator(f'[data-testid="{testid}"]')


def open_expander(page: Page, testid: str) -> Locator:
    """Open a card expander through its summary (a no-op when it is already open).

    The expanders are collapsed by default; the "Waiting for approval" one is hidden while
    nothing waits, so this also asserts it is there.
    """
    details = expander(page, testid)
    expect(details).to_be_visible(timeout=8000)
    if details.get_attribute("open") is None:
        details.locator("> summary").click()
    expect(details).to_have_attribute("open", "")
    return details


def click_switch(page: Page, name: str) -> None:
    """Click the named switch's drawn track (the input itself is visually hidden)."""
    switch(page, name).locator("xpath=ancestor::label[1]").locator(".ui-toggle-track").click()
