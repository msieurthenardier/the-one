"""Sortie 20 L02: the agent Delete confirmation dialog (General tab danger zone).

Delete agent opens a dialog that names the agent and its chat count; Delete stays disabled until
the acknowledgement is ticked; deleting runs the cascading delete. AC1 to AC8 of the leg.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

OPENER = '[data-testid="delete-agent-btn"]'
DIALOG = '[data-testid="delete-agent-dialog"]'
ACK = '[data-testid="delete-agent-ack-checkbox"]'
CONFIRM = '[data-testid="delete-agent-confirm-btn"]'
CANCEL = '[data-testid="delete-agent-cancel-btn"]'
ACK_LABEL = "I understand this will delete all of this agent's chat history"
SESSIONS_URL = "**/api/chat/sessions"


def _open_editor(page: Page, base: str, name: str) -> None:
    from browser import _lists

    _nav.goto_settled(page, base, "agents")
    _lists.open_item(page, "agents", name)
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled(timeout=8000)


def _chats_of(base: str, name: str) -> list[dict]:
    r = httpx.get(f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return [s for s in r.json() if s.get("agent_name") == name]


def _agent_exists(base: str, name: str) -> bool:
    r = httpx.get(f"{base}/api/agents", headers=auth_headers_for(base), timeout=5.0)
    return any(a["name"] == name for a in r.json())


def _seed_chats(base: str, name: str, n: int) -> None:
    for i in range(n):
        seed_session(base, name, f"chat {i}", "2026-01-01T10:00:00+00:00")


def _open_dialog(page: Page) -> None:
    page.locator(OPENER).click()
    expect(page.locator(DIALOG)).to_be_visible(timeout=8000)


def test_opens_without_arming_and_shows_the_count(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _seed_chats(base, name, 3)
    other = seed_mock_agent(base, app_with_agent.provider_id, name="other-agent")
    _seed_chats(base, other, 2)
    _open_editor(page, base, name)

    btn = page.locator(OPENER)
    btn.click()
    # A second click while the count is being read opens nothing more.
    btn.dispatch_event("click")  # no pointer: leaves the dialog's focus alone
    dialog = page.locator(DIALOG)
    expect(dialog).to_be_visible(timeout=8000)
    expect(page.locator(DIALOG)).to_have_count(1)
    # Not armed: no confirm class, label unchanged.
    expect(btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(btn).to_have_text("Delete agent")

    expect(dialog).to_contain_text(f'Delete "{name}"?')
    expect(dialog).to_contain_text(
        "This deletes the agent and its 3 chats, with every message in them. This can't be undone."
    )
    expect(dialog.locator("label")).to_have_text(ACK_LABEL)
    # Footer order: Cancel, then Delete.
    buttons = dialog.locator(
        '[data-testid="delete-agent-cancel-btn"], [data-testid="delete-agent-confirm-btn"]'
    )
    expect(buttons.nth(0)).to_have_attribute("data-testid", "delete-agent-cancel-btn")
    expect(buttons.nth(1)).to_have_attribute("data-testid", "delete-agent-confirm-btn")
    expect(page.locator(CONFIRM)).to_have_class(re.compile(r"\bbtn-muted-destructive\b"))
    # Cancel has the focus.
    expect(page.locator(CANCEL)).to_be_focused()


def test_message_for_one_chat_none_and_unreadable(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    other = seed_mock_agent(base, app_with_agent.provider_id, name="roomy")
    _seed_chats(base, other, 1)
    _open_editor(page, base, name)

    # No chats.
    _open_dialog(page)
    expect(page.locator(DIALOG)).to_contain_text(
        "This deletes the agent. It has no chats. This can't be undone."
    )
    page.locator(CANCEL).click()
    expect(page.locator(DIALOG)).to_have_count(0)

    # One chat (singular).
    _seed_chats(base, name, 1)
    _open_dialog(page)
    expect(page.locator(DIALOG)).to_contain_text("This deletes the agent and its 1 chat, with")
    page.locator(CANCEL).click()
    expect(page.locator(DIALOG)).to_have_count(0)

    # The count read fails: the message drops the number.
    def fail_sessions(route) -> None:  # noqa: ANN001
        if route.request.method == "GET":
            route.fulfill(status=500, json={"detail": "boom"})
        else:
            route.continue_()

    page.route(SESSIONS_URL, fail_sessions)
    _open_dialog(page)
    expect(page.locator(DIALOG)).to_contain_text(
        "This deletes the agent and all of its chats, with every message in them."
    )
    page.unroute(SESSIONS_URL, fail_sessions)


def test_delete_is_gated_by_the_acknowledgement(app_with_agent: SeededApp, page: Page) -> None:
    """Disabled on open (also with no chats), enabled when ticked, disabled when unticked."""
    _open_editor(page, app_with_agent.base_url, app_with_agent.agent_name)
    _open_dialog(page)
    confirm = page.locator(CONFIRM)
    expect(confirm).to_be_disabled()
    # The disabled state is announced: aria-describedby points at the message.
    desc_id = confirm.get_attribute("aria-describedby")
    assert desc_id
    expect(page.locator(f"#{desc_id}")).to_contain_text("This deletes the agent")
    page.locator(ACK).check()
    expect(confirm).to_be_enabled()
    page.locator(ACK).uncheck()
    expect(confirm).to_be_disabled()


def test_escape_cancel_and_backdrop_send_nothing(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _seed_chats(base, name, 2)
    _open_editor(page, base, name)
    deletes: list[str] = []
    page.on("request", lambda r: deletes.append(r.url) if r.method == "DELETE" else None)

    _open_dialog(page)
    # A backdrop click does nothing.
    page.locator(".modal-overlay").click(position={"x": 4, "y": 4})
    expect(page.locator(DIALOG)).to_be_visible()

    page.keyboard.press("Escape")
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator(OPENER)).to_be_focused()

    _open_dialog(page)
    page.locator(ACK).check()
    page.locator(CANCEL).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator(OPENER)).to_be_focused()

    assert deletes == []
    assert _agent_exists(base, name)
    assert len(_chats_of(base, name)) == 2


def test_success_flashes_the_response_count_and_removes_the_chats(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The flash uses chats_deleted, not the count read when the dialog opened."""
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _seed_chats(base, name, 2)
    _open_editor(page, base, name)
    _open_dialog(page)
    expect(page.locator(DIALOG)).to_contain_text("its 2 chats")
    # A chat arrives after the dialog opened: the delete takes it too.
    _seed_chats(base, name, 1)
    page.evaluate(
        "() => { window.__inv = []; const f = App.store.invalidate; "
        "App.store.invalidate = (n) => { window.__inv.push(n); return f(n); }; }"
    )

    page.locator(ACK).check()
    resp_ctx = page.expect_response(
        lambda r: "/api/agents/" in r.url and r.request.method == "DELETE"
    )
    with resp_ctx as info:
        page.locator(CONFIRM).click()
    assert info.value.json()["chats_deleted"] == 3
    expect(page.locator(DIALOG)).to_have_count(0)
    flash = page.locator(".app-flash-region .app-flash")
    expect(flash).to_have_text(f"Deleted {name} and 3 chats.", timeout=8000)
    page.wait_for_function("() => ['sessions','agents'].every(n => window.__inv.includes(n))")
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible(timeout=8000)
    assert not _agent_exists(base, name)
    assert _chats_of(base, name) == []


def test_success_flash_for_zero_chats(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    _open_editor(page, app_with_agent.base_url, name)
    _open_dialog(page)
    page.locator(ACK).check()
    page.locator(CONFIRM).click()
    expect(page.locator(".app-flash-region .app-flash")).to_have_text(
        f"Deleted {name}.", timeout=8000
    )


def test_failure_keeps_the_dialog_open_and_a_retry_succeeds(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _seed_chats(base, name, 1)
    _open_editor(page, base, name)
    _open_dialog(page)

    failed: list[bool] = []

    def fail_once(route) -> None:  # noqa: ANN001
        if route.request.method == "DELETE" and not failed:
            failed.append(True)
            route.fulfill(status=500, json={"detail": "disk on fire"})
        else:
            route.fallback()

    page.route("**/api/agents/*", fail_once)
    page.locator(ACK).check()
    page.locator(CONFIRM).click()
    flash = page.locator(f"{DIALOG} .app-flash")
    expect(flash).to_have_text("disk on fire", timeout=8000)
    expect(page.locator(DIALOG)).to_be_visible()
    expect(page.locator(CONFIRM)).to_be_enabled()
    expect(page.locator(ACK)).to_be_enabled()
    assert _agent_exists(base, name)

    page.locator(CONFIRM).click()
    expect(page.locator(DIALOG)).to_have_count(0, timeout=8000)
    expect(page.locator(".app-flash-region .app-flash")).to_have_text(
        f"Deleted {name} and 1 chat.", timeout=8000
    )
    assert not _agent_exists(base, name)


def test_escape_while_the_request_runs_still_navigates_and_flashes(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _seed_chats(base, name, 2)
    _open_editor(page, base, name)
    _open_dialog(page)

    held: list = []

    def hold(route) -> None:  # noqa: ANN001
        if route.request.method == "DELETE":
            held.append(route)
        else:
            route.fallback()

    page.route("**/api/agents/*", hold)
    page.locator(ACK).check()
    page.locator(CONFIRM).click()
    # While the request runs, Delete and the checkbox are disabled.
    expect(page.locator(CONFIRM)).to_be_disabled()
    expect(page.locator(ACK)).to_be_disabled()
    page.wait_for_function("() => true")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held
    page.keyboard.press("Escape")
    expect(page.locator(DIALOG)).to_have_count(0)
    # The opener stays guarded while the request is in flight: a click opens no second dialog.
    page.locator(OPENER).dispatch_event("click")
    page.wait_for_timeout(600)
    expect(page.locator(DIALOG)).to_have_count(0)

    held[0].continue_()
    expect(page.locator(".app-flash-region .app-flash")).to_have_text(
        f"Deleted {name} and 2 chats.", timeout=8000
    )
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible(timeout=8000)
    assert not _agent_exists(base, name)


STATUS = f"{DIALOG} [role='status']"


def _hold_deletes(page: Page) -> list:
    held: list = []

    def hold(route) -> None:  # noqa: ANN001
        if route.request.method == "DELETE":
            held.append(route)
        else:
            route.fallback()

    page.route("**/api/agents/*", hold)
    return held


def _wait_held(page: Page, held: list) -> None:
    for _ in range(50):
        if held:
            return
        page.wait_for_timeout(100)
    raise AssertionError("the DELETE never reached the route")


def test_running_moves_focus_to_cancel_announces_and_failure_focuses_delete(
    app_with_agent: SeededApp, page: Page
) -> None:
    """WCAG 2.4.3 / 4.1.3: focus stays in the dialog, 'Deleting...' is announced while running."""
    _open_editor(page, app_with_agent.base_url, app_with_agent.agent_name)
    _open_dialog(page)
    held = _hold_deletes(page)
    page.locator(ACK).check()
    page.locator(CONFIRM).focus()  # the focus is on the control that is about to disable
    page.keyboard.press("Enter")
    expect(page.locator(CONFIRM)).to_be_disabled()
    expect(page.locator(CANCEL)).to_be_focused()
    expect(page.locator(STATUS)).to_have_text("Deleting…")
    expect(page.locator(DIALOG)).to_have_attribute("aria-busy", "true")
    _wait_held(page, held)

    held[0].fulfill(status=500, json={"detail": "disk on fire"})
    expect(page.locator(f"{DIALOG} .app-flash")).to_have_text("disk on fire", timeout=8000)
    expect(page.locator(CONFIRM)).to_be_enabled()
    expect(page.locator(CONFIRM)).to_be_focused()
    expect(page.locator(STATUS)).to_have_text("")
    expect(page.locator(DIALOG)).not_to_have_attribute("aria-busy", "true")


def test_opener_is_free_again_after_an_escaped_request_fails(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_editor(page, app_with_agent.base_url, app_with_agent.agent_name)
    _open_dialog(page)
    held = _hold_deletes(page)
    page.locator(ACK).check()
    page.locator(CONFIRM).click()
    _wait_held(page, held)
    page.keyboard.press("Escape")
    expect(page.locator(DIALOG)).to_have_count(0)
    held[0].fulfill(status=500, json={"detail": "disk on fire"})
    expect(page.locator(".app-flash-region .app-flash")).to_have_text("disk on fire", timeout=8000)
    # The failure settled the request: the opener works again.
    _open_dialog(page)
