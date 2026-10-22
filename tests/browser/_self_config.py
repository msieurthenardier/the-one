"""Helpers for the Self-configuration tab's two switches (M31 F2 L10c).

The switches are ``App.ui.toggle`` (a visually hidden ``role=switch`` input and a
drawn track), so a test finds one by its accessible name and clicks the track.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page

ENABLE_SWITCH = "Enable self-configuration"
APPROVAL_SWITCH = "Require approval for self-revisions"


def switch(page: Page, name: str) -> Locator:
    """The switch input with this accessible name."""
    return page.get_by_role("switch", name=name)


def click_switch(page: Page, name: str) -> None:
    """Click the named switch's drawn track (the input itself is visually hidden)."""
    switch(page, name).locator("xpath=ancestor::label[1]").locator(".ui-toggle-track").click()
