"""An editor header's secondary actions sit in a "More actions" menu below 768px.

(Sortie 21 HAT feature.)

The agent editor's Chat is a button at 768px and wider and an item of the ``editor-more-btn`` menu
below. Choosing it starts the same pending chat; with a dirty editor the leave guard's Stay returns
focus to the visible control (the menu trigger at narrow). Cancel and Save stay buttons. The
contract-level cases (modes, focus, destroy) are in ``test_ui_editor_contract.py``.
Falls in the ``layout`` lane (``test_flow_narrow_*``).
"""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SMALL = {"width": 624, "height": 321}
MORE = '[data-testid="editor-more-btn"]'
CHAT_ITEM = '[data-testid="agent-chat-btn-menu-item"]'
CHAT_BTN = '[data-testid="agent-chat-btn"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'


def _open_editor(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(name)}")
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)


def test_chat_is_in_the_more_actions_menu_and_starts_a_chat(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    assert name is not None
    page.set_viewport_size(SMALL)
    _open_editor(page, base, name)
    expect(page.locator(MORE)).to_be_visible(timeout=8000)
    expect(page.locator(CHAT_BTN)).to_have_count(0)
    order = page.evaluate(
        """() => Array.from(document.querySelector('.editor-header .form-actions').children)
             .map((c) => c.getAttribute('data-testid') || c.className.split(' ')[0])"""
    )
    assert order == ["editor-unsaved", "ui-menu-wrap", "cancel-agent-btn", "save-agent-btn"]
    # Cancel and Save are visible buttons, nothing sticks out past the right edge.
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_visible()
    box = page.evaluate(
        "() => [document.querySelector('[data-testid=save-agent-btn]')"
        ".getBoundingClientRect().right, innerWidth,"
        " document.documentElement.scrollWidth - document.documentElement.clientWidth]"
    )
    assert box[0] <= box[1] and box[2] <= 0, box
    # Record what chatWith is handed: the opener must be the visible control (the trigger).
    page.evaluate(
        """() => { const orig = App.chat.chatWith; window.__openers = [];
          App.chat.chatWith = function (n, o) {
            window.__openers.push(o && o.opener && o.opener.dataset.testid);
            return orig.apply(this, arguments); }; }"""
    )
    page.locator(MORE).click()
    expect(page.get_by_role("menu", name="More actions")).to_be_visible()
    expect(page.get_by_role("menuitem")).to_have_count(1)
    expect(page.locator(CHAT_ITEM)).to_have_text("Chat")
    page.locator(CHAT_ITEM).click()
    assert page.evaluate("() => window.__openers") == ["editor-more-btn"]
    _nav.expect_route(page, f"chats/~new/{_nav.seg(name)}", timeout=8000)
    _chats.expect_chat(page, name, title="New chat")


def test_chat_from_a_dirty_editor_returns_focus_to_the_more_trigger_on_stay(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    assert name is not None
    page.set_viewport_size(SMALL)
    _open_editor(page, base, name)
    desc = page.locator('[data-field="description"]')
    desc.fill("an unsaved edit")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    page.locator(MORE).click()
    page.locator(CHAT_ITEM).click()
    expect(page.locator(DIALOG)).to_have_count(1)
    page.locator(STAY).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/general")
    expect(desc).to_have_value("an unsaved edit")
    expect(page.locator(MORE)).to_be_focused()


def test_widening_brings_the_chat_button_back_and_narrowing_the_menu(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    assert name is not None
    page.set_viewport_size({"width": 1000, "height": 700})
    _open_editor(page, base, name)
    expect(page.locator(CHAT_BTN)).to_be_visible()
    expect(page.locator(MORE)).to_have_count(0)
    page.locator(CHAT_BTN).focus()
    page.set_viewport_size(SMALL)
    expect(page.locator(MORE)).to_be_focused()
    expect(page.locator(CHAT_BTN)).to_have_count(0)
    page.set_viewport_size({"width": 1000, "height": 700})
    expect(page.locator(CHAT_BTN)).to_be_visible()
    expect(page.locator(MORE)).to_have_count(0)


def test_create_mode_has_no_more_actions_menu(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    page.set_viewport_size(SMALL)
    _nav.goto(page, base, "agents/~new")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator(MORE)).to_have_count(0)
