"""Focus after an in-place agent-editor action (M25 F6 L1b, flight DD2).

A keyboard user (focus on the button, then Enter) who saves, cancels or creates
must not lose focus to <body>: it lands on the editor's `.editor-title`.
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

TITLE = ".editor-title"


def _press(page: Page, testid: str) -> None:
    btn = page.locator(f'[data-testid="{testid}"]')
    expect(btn).to_be_enabled()
    btn.focus()
    page.keyboard.press("Enter")


def _open_agent(app: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app.base_url, f"agents/{_nav.seg(app.agent_name)}")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_visible(timeout=8000)


def test_agent_save_leaves_focus_on_the_title(app_with_agent: SeededApp, page: Page) -> None:
    _open_agent(app_with_agent, page)
    page.locator('[data-field="description"]').fill("changed by the focus test")
    _press(page, "save-agent-btn")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_agent_cancel_leaves_focus_on_the_title(app_with_agent: SeededApp, page: Page) -> None:
    _open_agent(app_with_agent, page)
    page.locator('[data-field="description"]').fill("to be reverted")
    _press(page, "cancel-agent-btn")
    expect(page.locator('[data-testid="cancel-agent-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_agent_create_leaves_focus_on_the_new_editors_title(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "agents")
    _lists.agents_new(page)
    page.locator('[data-field="name"]').fill("focus-agent")
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=5000)
    page.locator("#studio-model").select_option("mock-default")
    page.locator('[data-field="description"]').fill("made by the focus test")
    _press(page, "save-agent-btn")
    _nav.expect_route(page, "agents/focus-agent/general")
    expect(page.locator(TITLE)).to_have_text("focus-agent", timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_agent_save_never_steals_focus_the_user_moved(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_agent(app_with_agent, page)
    page.locator('[data-field="description"]').fill("held save")
    hold: list = []

    def _hold(route) -> None:  # noqa: ANN001
        hold.append(route)

    page.route(f"**/api/agents/{app_with_agent.agent_name}", _hold, times=1)
    _press(page, "save-agent-btn")
    page.wait_for_timeout(300)
    assert hold, "the PUT was not held"
    # A control outside the re-rendered editor: the user's focus survives the
    # re-render, so the helper must leave it alone.
    page.locator('[data-testid="agents-filter"]').focus()
    hold[0].continue_()
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled(timeout=8000)
    page.wait_for_timeout(800)
    expect(page.locator('[data-testid="agents-filter"]')).to_be_focused()
