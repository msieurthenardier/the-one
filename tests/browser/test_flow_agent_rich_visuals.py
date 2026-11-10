"""The General tab's Rich visuals switch and the drawer line (M35 F1 L03, flight DD11).

The switch is a form field saved by Save (not an immediate post); the drawer shows it
read-only. Falls in the ``agents`` lane via the ``test_flow_agent_*`` glob (it matches
none of the ``agent-tabs`` or ``agent-routines`` globs).
"""

from __future__ import annotations

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SAVE = '[data-testid="save-agent-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
SWITCH = '[data-testid="agent-rich-visuals-toggle"]'
DRAWER_GROUP = '[data-testid="chat-drawer-uses"] [data-group="rich-visuals"]'


def _open(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/general")
    expect(page.locator('[data-field="name"]')).to_be_attached(timeout=8000)
    expect(page.locator("#studio-model")).to_have_value("mock-default", timeout=8000)


def _flip(page: Page) -> None:
    # The native input is visually hidden; the label is the click target.
    page.locator(f"label:has({SWITCH})").click()


def test_new_agent_switch_is_on(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_provider.base_url, "agents/~new")
    expect(page.locator(SWITCH)).to_be_attached(timeout=8000)
    expect(page.locator(SWITCH)).to_be_checked()
    expect(page.locator(SWITCH)).to_have_attribute("role", "switch")


def test_the_hint_names_charts_and_widgets(app_with_provider: SeededApp, page: Page) -> None:
    # M35 F2 L7: the hint widens with the prompt; scoped to the Rich visuals toggle's own row.
    _nav.goto(page, app_with_provider.base_url, "agents/~new")
    expect(page.locator(SWITCH)).to_be_attached(timeout=8000)
    row = page.locator(f"div.ui-toggle:has({SWITCH})")
    expect(row).to_contain_text(
        "Tell this agent it can answer with charts and widgets. When it's off, the agent "
        "isn't told, but any chart or widget in its replies is still shown."
    )


def test_off_saves_persists_and_the_drawer_shows_off(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open(page, base, agent)
    expect(page.locator(SWITCH)).to_be_checked()
    expect(page.locator(SAVE)).to_be_disabled()
    _flip(page)
    expect(page.locator(SWITCH)).not_to_be_checked()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    stored = httpx.get(
        f"{base}/api/agents/{_nav.seg(agent)}", headers=auth_headers_for(base), timeout=5
    ).json()
    assert stored["rich_visuals"] is False

    page.reload()
    _open(page, base, agent)
    expect(page.locator(SWITCH)).not_to_be_checked()

    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    expect(page.locator(DRAWER_GROUP).locator("h4")).to_have_text("Rich visuals", timeout=8000)
    expect(page.locator(DRAWER_GROUP).locator("p")).to_have_text("Off")


def test_flip_and_flip_back_is_clean(app_with_agent: SeededApp, page: Page) -> None:
    _open(page, app_with_agent.base_url, app_with_agent.agent_name)
    _flip(page)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    _flip(page)
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(SWITCH)).to_be_checked()


def test_agent_seeded_without_the_field_shows_on(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    stored = httpx.get(
        f"{base}/api/agents/{_nav.seg(agent)}", headers=auth_headers_for(base), timeout=5
    ).json()
    assert stored["rich_visuals"] is True
    _open(page, base, agent)
    expect(page.locator(SWITCH)).to_be_checked()
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    expect(page.locator(DRAWER_GROUP).locator("p")).to_have_text("On", timeout=8000)
