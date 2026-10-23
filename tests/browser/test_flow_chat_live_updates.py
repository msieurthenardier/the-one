"""Live Chats list and connector chats (sortie 05).

Leg 2 (``live-list``, criteria 1 and 4): the server pushes ``sessions_changed``
when a write changes what the list shows, so an open list follows connector
chats, other tabs, deletes and purges without moving the user.

Leg 1 (criterion 3): a web turn on a chat a connector also writes keeps both
writers' messages (DD4, DD8).

The connector turn is driven for real through the stub seam
(``POST /api/_test/stub/inbound``). The browser has the chat open (so the web
session cache holds the pre-connector history), a second inbound DM runs a
connector turn, then the browser sends: without the turn-start re-sync the
web save writes its stale history over the connector's messages.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import re
import threading
import time

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import StubConnectorApp, seed_session, stub_inbound
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

MOCK_REPLY = "Mock response from the mock provider."


def _stored_text(base: str, sid: str) -> list[str]:
    r = httpx.get(f"{base}/api/chat/sessions/{sid}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    out: list[str] = []
    for m in r.json()["messages"]:
        c = m.get("content")
        out.append(c if isinstance(c, str) else str(c))
    return out


def test_web_turn_after_a_connector_turn_keeps_the_connector_messages(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    base = app.base_url

    stub_inbound(base, app.connector_id, "first dm", app.peer_id, app.peer_name)
    sessions = httpx.get(
        f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5.0
    ).json()
    rows = [s for s in sessions if s["title"] == f"DM: {app.peer_name}"]
    assert len(rows) == 1, sessions
    sid = rows[0]["id"]

    _nav.goto(page, base, "chats")
    _chats.open_chat(page, sid)

    stub_inbound(base, app.connector_id, "second dm", app.peer_id, app.peer_name)
    # Leg 3: the open chat re-joins when the connector turn ends; a send during
    # that join would be ignored (the text stays in the composer), so wait for it.
    # The server's cached session is still the pre-connector one: the leg-1 case.
    expect(page.locator(".messages")).to_contain_text("second dm", timeout=10000)

    box = page.locator('[data-testid="chat-input"]')
    box.fill("web message")
    box.press("Enter")

    deadline = time.monotonic() + 20
    texts: list[str] = []
    while time.monotonic() < deadline:
        texts = _stored_text(base, sid)
        if "web message" in texts and texts[-1] == MOCK_REPLY:
            break
        page.wait_for_timeout(250)

    assert "first dm" in texts, texts
    assert "second dm" in texts, texts
    assert "web message" in texts, texts
    # Connector turns 1 and 2, then the web turn: three mock replies.
    assert texts.count(MOCK_REPLY) == 3, texts


# ── Leg 2: the live list ─────────────────────────────────────────────────────

PUSH_TIMEOUT = 10000


def _stub_sid(base: str, title: str) -> str:
    sessions = httpx.get(
        f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5.0
    ).json()
    rows = [s for s in sessions if s["title"] == title]
    assert len(rows) == 1, sessions
    return rows[0]["id"]


def test_a_connector_chat_appears_without_moving_an_idle_list(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    _nav.goto(page, app.base_url, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    expect(_chats.chat_rows(page)).to_have_count(0)

    stub_inbound(app.base_url, app.connector_id, "hello", app.peer_id, app.peer_name)

    expect(_chats.chat_rows(page)).to_have_count(1, timeout=PUSH_TIMEOUT)
    # No auto-open: idle, welcome still shown, route unchanged.
    assert (_chats.session_state(page) or {}).get("name") == "idle"
    expect(_chats.welcome(page)).to_be_visible()
    _nav.expect_route(page, "chats")


def test_a_push_leaves_an_open_chat_and_its_composer_alone(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    stub_inbound(app.base_url, app.connector_id, "first", app.peer_id, app.peer_name)
    sid = _stub_sid(app.base_url, f"DM: {app.peer_name}")

    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, sid)
    expect(_chats.chat_rows(page)).to_have_count(1)
    box = page.locator('[data-testid="chat-input"]')
    box.fill("half-typed")

    stub_inbound(
        app.base_url,
        app.connector_id,
        "other",
        app.peer2_id,
        app.peer2_name,
        channel_id=app.peer2_id,
    )

    expect(_chats.chat_rows(page)).to_have_count(2, timeout=PUSH_TIMEOUT)
    state = _chats.session_state(page) or {}
    assert (state.get("name"), state.get("id")) == ("joined", sid)
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    expect(box).to_have_value("half-typed")


def test_a_chat_started_in_another_page_appears(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    _nav.goto(page, app.base_url, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)

    other = page.context.new_page()
    try:
        _nav.goto(other, app.base_url, "chats")
        _chats.start_chat(other, app.agent_name)
        sid = _chats.send_first(other, "from the other page")
        expect(_chats.chat_row(page, sid)).to_be_visible(timeout=PUSH_TIMEOUT)
    finally:
        other.close()


def test_a_chat_deleted_in_another_page_disappears(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    stub_inbound(app.base_url, app.connector_id, "one", app.peer_id, app.peer_name)
    stub_inbound(
        app.base_url, app.connector_id, "two", app.peer2_id, app.peer2_name, channel_id=app.peer2_id
    )
    older = _stub_sid(app.base_url, f"DM: {app.peer_name}")

    _nav.goto(page, app.base_url, "chats")
    expect(_chats.chat_rows(page)).to_have_count(2, timeout=8000)

    other = page.context.new_page()
    try:
        _nav.goto(other, app.base_url, "chats")
        expect(_chats.chat_row(other, older)).to_be_visible(timeout=8000)
        _chats.chat_row(other, older).hover()
        _chats.chat_row_delete(other, older).click()
        _chats.chat_row_delete(other, older).click()
        expect(_chats.chat_row(other, older)).to_have_count(0, timeout=8000)
        expect(_chats.chat_row(page, older)).to_have_count(0, timeout=PUSH_TIMEOUT)
        expect(_chats.chat_rows(page)).to_have_count(1)
    finally:
        other.close()


def test_an_armed_delete_survives_a_push(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    stub_inbound(app.base_url, app.connector_id, "one", app.peer_id, app.peer_name)
    stub_inbound(
        app.base_url, app.connector_id, "two", app.peer2_id, app.peer2_name, channel_id=app.peer2_id
    )
    older = _stub_sid(app.base_url, f"DM: {app.peer_name}")

    _nav.goto(page, app.base_url, "chats")
    expect(_chats.chat_rows(page)).to_have_count(2, timeout=8000)
    row = page.locator("li").filter(has=_chats.chat_row(page, older))
    row.hover()
    _chats.chat_row_delete(page, older).click()
    expect(row).to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=2000)

    # Another writer (a second page's start would do the same) adds a chat.
    seed_session(app.base_url, app.agent_name, "Pushed in", "2030-01-01T00:00:00+00:00")
    expect(_chats.chat_rows(page)).to_have_count(3, timeout=PUSH_TIMEOUT)
    expect(page.locator("li").filter(has=_chats.chat_row(page, older))).to_have_class(
        re.compile(r"\bconfirm-delete\b")
    )


# ── Leg 3: the open connector chat follows its turns ─────────────────────────

MESSAGES = ".messages"
THINKING = '[data-testid="thinking-indicator"]'


def _set_delay(app: StubConnectorApp, ms: int) -> None:
    r = httpx.put(
        f"{app.base_url}/api/providers/{app.provider_id}",
        json={"config": {"delay_ms": ms}},
        headers=auth_headers_for(app.base_url),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text


def _background_dm(app: StubConnectorApp, text: str) -> threading.Thread:
    t = threading.Thread(
        target=stub_inbound,
        args=(app.base_url, app.connector_id, text, app.peer_id, app.peer_name),
        kwargs={"timeout": 30.0},
        daemon=True,
    )
    t.start()
    return t


def _join_mid_turn(page: Page, app: StubConnectorApp, sid: str) -> None:
    """Reload the chat until a join answers while the connector turn runs."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        _nav.goto(page, app.base_url, f"chats/{_nav.seg(sid)}")
        try:
            expect(page.locator(THINKING)).to_be_visible(timeout=2500)
            return
        except AssertionError:
            continue
    raise AssertionError("never joined while the connector turn was running")


def test_an_open_connector_chat_shows_a_new_turn_without_a_reload(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    stub_inbound(app.base_url, app.connector_id, "first dm", app.peer_id, app.peer_name)
    sid = _stub_sid(app.base_url, f"DM: {app.peer_name}")
    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, sid)
    box = page.locator('[data-testid="chat-input"]')
    box.fill("half-typed")
    box.focus()

    stub_inbound(app.base_url, app.connector_id, "second dm", app.peer_id, app.peer_name)

    expect(page.locator(MESSAGES)).to_contain_text("second dm", timeout=PUSH_TIMEOUT)
    expect(page.locator(MESSAGES).get_by_text(MOCK_REPLY)).to_have_count(2)
    state = _chats.session_state(page) or {}
    assert (state.get("name"), state.get("id")) == ("joined", sid)
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    expect(box).to_have_value("half-typed")
    expect(box).to_be_focused()


def test_joining_mid_turn_clears_the_thinking_indicator_after_the_turn(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    stub_inbound(app.base_url, app.connector_id, "first dm", app.peer_id, app.peer_name)
    sid = _stub_sid(app.base_url, f"DM: {app.peer_name}")
    _set_delay(app, 6000)
    worker = _background_dm(app, "slow dm")
    try:
        _join_mid_turn(page, app, sid)
        expect(page.locator(THINKING)).to_be_hidden(timeout=20000)
        expect(page.locator(MESSAGES)).to_contain_text("slow dm", timeout=5000)
        state = _chats.session_state(page) or {}
        assert (state.get("name"), state.get("id")) == ("joined", sid)
        expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()
    finally:
        worker.join(timeout=30)


def test_a_message_sent_during_a_mid_turn_join_is_held_then_delivered(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    stub_inbound(app.base_url, app.connector_id, "first dm", app.peer_id, app.peer_name)
    sid = _stub_sid(app.base_url, f"DM: {app.peer_name}")
    _set_delay(app, 5000)
    worker = _background_dm(app, "slow dm")
    try:
        _join_mid_turn(page, app, sid)
        box = page.locator('[data-testid="chat-input"]')
        box.fill("web message")
        box.press("Enter")  # Send is disabled while busy: Enter holds it
        expect(page.locator('[data-testid="pending-queued"]')).to_be_visible(timeout=3000)

        expect(page.locator('[data-testid="pending-queued"]')).to_be_hidden(timeout=20000)
        deadline = time.monotonic() + 30
        texts: list[str] = []
        while time.monotonic() < deadline:
            texts = _stored_text(app.base_url, sid)
            if "web message" in texts and texts[-1] == MOCK_REPLY:
                break
            page.wait_for_timeout(250)
        assert "slow dm" in texts and "web message" in texts, texts
        assert texts.index("slow dm") < texts.index("web message"), texts
        assert texts.count(MOCK_REPLY) == 3, texts
    finally:
        worker.join(timeout=40)


def test_a_re_join_keeps_an_unpinned_reader_where_they_were(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    filler = "\n\n".join(f"filler line {i}" for i in range(120))
    stub_inbound(app.base_url, app.connector_id, filler, app.peer_id, app.peer_name)
    sid = _stub_sid(app.base_url, f"DM: {app.peer_name}")
    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, sid)
    log = page.locator(MESSAGES)
    expect(log).to_contain_text("filler line 119")
    page.evaluate("document.querySelector('.messages').scrollTop = 200")
    page.wait_for_function("document.querySelector('.messages').scrollTop === 200")

    stub_inbound(app.base_url, app.connector_id, "tail dm", app.peer_id, app.peer_name)

    expect(log).to_contain_text("tail dm", timeout=PUSH_TIMEOUT)
    top, dist = page.evaluate(
        """() => { const m = document.querySelector('.messages');
                   return [m.scrollTop, m.scrollHeight - m.scrollTop - m.clientHeight]; }"""
    )
    assert abs(top - 200) <= 40, top
    assert dist > 200, dist  # the last message is not pinned into view
