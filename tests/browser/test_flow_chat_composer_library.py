"""The chat composer side on the library (M31 F6 L05a; flight DD7, DD11 1, B6, B13, A5-A7).

Focus after an agent pick (0.1), the deleted-agent chat (a library banner and a blocked
composer whose Attach is disabled, 0.3), the staged-image and queued chips on ``App.ui.chip``
(named remove buttons, 24px targets), and the empty state's centred text column (B6).
Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import base64

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

INPUT = '[data-testid="chat-input"]'
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_a_picker_pick_moves_focus_to_the_message_box(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    expect(page.locator(INPUT)).to_be_focused()


def test_a_deleted_agents_chat_is_blocked_with_a_library_banner(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    agent = seed_mock_agent(base, app_with_provider.provider_id, name="soon-gone")
    sid = seed_session(base, agent, "Old chat", "2026-01-01T10:00:00Z")
    r = httpx.delete(f"{base}/api/agents/{agent}", headers=auth_headers_for(base), timeout=5)
    assert r.status_code in (200, 204), r.text
    _nav.goto(page, base, "chats")
    _chats.open_chat(page, sid)
    banner = page.locator(".area-chat .ui-banner")
    expect(banner).to_contain_text("This agent has been deleted")
    assert banner.get_attribute("role") == "status"
    assert "banner-warning" in (banner.get_attribute("class") or "")
    expect(page.locator(INPUT)).to_be_disabled()
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_disabled()
    expect(page.locator('[data-testid="chat-attach-btn"]')).to_be_disabled()
    assert page.locator(".area-chat .chat-session-banner").count() == 0


def test_the_banner_clears_when_another_chat_opens_and_send_follows_busy(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Clearing the banner re-enables the input and Attach, and Send follows busy (a running
    turn keeps it disabled)."""
    base = app_with_provider.base_url
    pid = seed_mock_provider(
        base, name="slow", config={"response": {"content": "ok"}, "delay_ms": 4000}
    )
    slow = seed_mock_agent(base, pid, name="slowpoke")
    gone = seed_mock_agent(base, app_with_provider.provider_id, name="gone")
    sid = seed_session(base, gone, "Old chat", "2026-01-01T10:00:00Z")
    r = httpx.delete(f"{base}/api/agents/{gone}", headers=auth_headers_for(base), timeout=5)
    assert r.status_code in (200, 204), r.text
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, slow)
    _chats.send_first(page, "go")
    send = page.locator('[data-testid="chat-send-btn"]')
    expect(send).to_be_disabled()
    expect(page.locator('[data-testid="chat-stop-btn"]')).to_be_visible()
    _chats.open_chat(page, sid)
    expect(page.locator(".area-chat .ui-banner")).to_be_visible()
    # back to the busy chat: no banner, input and Attach enabled, Send disabled while busy
    page.locator('[data-testid="chat-row"]').filter(has_text="New chat").first.click()
    expect(page.locator(".area-chat .ui-banner")).to_be_hidden()
    expect(page.locator(INPUT)).to_be_enabled()
    expect(page.locator('[data-testid="chat-attach-btn"]')).to_be_enabled()
    expect(send).to_be_disabled()


def test_the_staged_image_chip_names_its_remove_button_and_is_a_24px_target(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    page.locator('[data-testid="chat-image-input"]').set_input_files(
        files=[{"name": "dot.png", "mimeType": "image/png", "buffer": _PNG}]
    )
    chip = page.locator('[data-testid="chat-attachment"]')
    expect(chip).to_have_count(1)
    btn = page.get_by_role("button", name="Remove staged image 1")
    expect(btn).to_have_count(1)
    box = btn.bounding_box()
    assert box is not None and round(box["width"]) == 24 and round(box["height"]) == 24
    assert "chip" in (chip.get_attribute("class") or "")
    assert chip.get_attribute("data-attachment-index") == "0"
    assert page.locator("button.chip-remove").count() == 0


def test_the_queued_chip_reads_queued_with_a_cancel_button(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    pid = seed_mock_provider(
        base, name="slow", config={"response": {"content": "ok"}, "delay_ms": 4000}
    )
    agent = seed_mock_agent(base, pid, name="slowpoke")
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    _chats.send_first(page, "first")
    box = page.locator(INPUT)
    box.fill("second message")
    box.press("Enter")
    chip = page.locator('[data-testid="pending-queued"]')
    expect(chip).to_be_visible()
    expect(chip).to_contain_text("Queued")
    assert "Queued:" not in chip.inner_text()
    expect(chip).to_contain_text("second message")
    cancel = page.get_by_role("button", name="Cancel queued message")
    expect(cancel).to_have_count(1)
    region = page.locator('[data-testid="pending-queued-region"]')
    assert region.get_attribute("aria-live") == "polite"
    cancel.click()
    expect(chip).to_have_count(0)
    expect(region).to_be_hidden()


def test_the_empty_states_text_column_is_centred(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    welcome = page.locator('[data-testid="chat-welcome"]')
    expect(welcome).to_be_visible()
    out = page.evaluate(
        """() => {
          const w = document.querySelector('[data-testid="chat-welcome"]').getBoundingClientRect();
          const mid = (n) => { const r = n.getBoundingClientRect(); return r.left + r.width / 2; };
          const q = (s) => document.querySelector(s);
          return {
            pane: w.left + w.width / 2,
            greetingAlign: getComputedStyle(q('.chat-welcome-greeting')).textAlign,
            promptAlign: getComputedStyle(q('.chat-welcome-prompt')).textAlign,
            button: mid(q('[data-testid="chat-empty-new-btn"]')),
            mascot: mid(q('[data-testid="chat-welcome-mascot"]')),
          };
        }"""
    )
    assert out["greetingAlign"] == "center" and out["promptAlign"] == "center"
    assert abs(out["button"] - out["pane"]) <= 2, out
    assert abs(out["mascot"] - out["pane"]) <= 2, out
