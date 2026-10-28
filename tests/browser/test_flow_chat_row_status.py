"""The Chats list's per-row activity: working ring and new-reply dot (M31 F6 L10b).

The server reports ``busy`` and ``turn_seq`` on every session row and pushes the
list when a turn starts and ends (web and connector turns alike); the client turns
those into a row indicator. The connector turns run through the stub seam; the
mock provider's ``delay_ms`` makes "working" observable.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import re
import threading

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import StubConnectorApp, stub_inbound
from playwright.sync_api import Locator, Page, expect

pytestmark = pytest.mark.browser

PUSH = 10000
WORKING = ".ui-list-pane-activity--working"
NEW = ".ui-list-pane-activity--new"
ANY = ".ui-list-pane-activity--working, .ui-list-pane-activity--new"


def _set_delay(app: StubConnectorApp, ms: int) -> None:
    r = httpx.put(
        f"{app.base_url}/api/providers/{app.provider_id}",
        json={"config": {"delay_ms": ms}},
        headers=auth_headers_for(app.base_url),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text


def _sid(base: str, title: str) -> str:
    rows = httpx.get(
        f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5.0
    ).json()
    hit = [s for s in rows if s["title"] == title]
    assert len(hit) == 1, rows
    return hit[0]["id"]


def _dm(app: StubConnectorApp, text: str, peer: int = 1) -> threading.Thread:
    pid, pname = (app.peer_id, app.peer_name) if peer == 1 else (app.peer2_id, app.peer2_name)
    t = threading.Thread(
        target=stub_inbound,
        args=(app.base_url, app.connector_id, text, pid, pname),
        kwargs={"timeout": 30.0, "channel_id": None if peer == 1 else pid},
        daemon=True,
    )
    t.start()
    return t


def _two_chats(app: StubConnectorApp) -> tuple[str, str]:
    stub_inbound(app.base_url, app.connector_id, "hi a", app.peer_id, app.peer_name)
    stub_inbound(
        app.base_url, app.connector_id, "hi b", app.peer2_id, app.peer2_name,
        channel_id=app.peer2_id,
    )  # fmt: skip
    return (_sid(app.base_url, f"DM: {app.peer_name}"), _sid(app.base_url, f"DM: {app.peer2_name}"))


def _li(page: Page, sid: str) -> Locator:
    return page.locator("li").filter(has=_chats.chat_row(page, sid))


def test_a_connector_turn_in_another_chat_works_then_leaves_a_new_reply_dot(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    a, b = _two_chats(app)
    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, b)
    expect(_li(page, a).locator(ANY)).to_have_count(0)

    _set_delay(app, 3000)
    worker = _dm(app, "slow a")
    try:
        expect(_li(page, a).locator(WORKING)).to_have_count(1, timeout=PUSH)
        expect(_chats.chat_row(page, a)).to_contain_text("Working")
        expect(_li(page, b).locator(ANY)).to_have_count(0)  # the open chat, idle
        expect(_li(page, a).locator(NEW)).to_have_count(1, timeout=20000)
        expect(_li(page, a).locator(WORKING)).to_have_count(0)
        expect(_chats.chat_row(page, a)).to_contain_text("New reply")
        # Opening the chat clears the dot (and never leaves one on the open chat).
        _chats.open_chat(page, a)
        expect(_li(page, a).locator(ANY)).to_have_count(0)
    finally:
        worker.join(timeout=30)


def test_a_turn_into_the_open_chat_leaves_no_dot_after_navigating_away(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    a, b = _two_chats(app)
    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, a)
    _set_delay(app, 2500)
    worker = _dm(app, "slow a")
    try:
        # The open chat shows the working ring too.
        expect(_li(page, a).locator(WORKING)).to_have_count(1, timeout=PUSH)
        expect(_li(page, a).locator(WORKING)).to_have_count(0, timeout=20000)
        expect(_li(page, a).locator(NEW)).to_have_count(0)
        _chats.open_chat(page, b)
        expect(_li(page, a).locator(ANY)).to_have_count(0)
        page.wait_for_timeout(500)
        expect(_li(page, a).locator(ANY)).to_have_count(0)
    finally:
        worker.join(timeout=30)


def test_a_web_turn_from_another_tab_works_then_lights_the_dot(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    a, b = _two_chats(app)
    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, b)

    other = page.context.new_page()
    try:
        _set_delay(app, 3000)
        _nav.goto(other, app.base_url, "chats")
        _chats.open_chat(other, a)
        box = other.locator('[data-testid="chat-input"]')
        box.fill("web hello")
        box.press("Enter")
        expect(_li(page, a).locator(WORKING)).to_have_count(1, timeout=PUSH)
        expect(_li(page, a).locator(NEW)).to_have_count(1, timeout=20000)
        expect(_li(page, b).locator(ANY)).to_have_count(0)
        # The tab that ran the turn had the chat open: no dot there.
        expect(_li(other, a).locator(ANY)).to_have_count(0)
    finally:
        other.close()


def test_the_pending_row_shows_no_activity(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    _two_chats(app)
    _nav.goto(page, app.base_url, "chats")
    _chats.start_chat(page, app.agent_name)
    pending = _chats.pending_row(page)
    expect(pending).to_be_visible()
    expect(pending.locator(".ui-list-pane-activity")).to_have_count(1)  # the reserved slot
    expect(pending.locator(ANY)).to_have_count(0)
    expect(pending).not_to_contain_text("Working")
    expect(pending).not_to_contain_text("New reply")


def test_an_armed_delete_survives_a_busy_flip_and_the_indicator_updates(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    app = app_with_stub_connector
    a, b = _two_chats(app)
    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, b)
    _set_delay(app, 6000)
    li = _li(page, a)
    li.hover()
    _chats.chat_row_delete(page, a).click()
    expect(li).to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=2000)
    worker = _dm(app, "slow a")
    try:
        expect(li.locator(WORKING)).to_have_count(1, timeout=PUSH)
        expect(_li(page, a)).to_have_class(re.compile(r"\bconfirm-delete\b"))
    finally:
        worker.join(timeout=30)


def test_the_activity_state_machine_handles_restarts_and_stale_rows(
    app_with_stub_connector: StubConnectorApp, page: Page
) -> None:
    _nav.goto(page, app_with_stub_connector.base_url, "chats")
    out = page.evaluate(
        """() => {
          const a = App.chat.activity.create();
          const row = (id, seq, busy) => ({id, turn_seq: seq, busy: !!busy});
          const log = [];
          const st = (r, open) => log.push(a.stateFor(r, open));
          // The first observe baselines silently.
          a.observe([row('s', 'x:3'), row('t', 'x:0')], null);
          st(row('s', 'x:3'), null);                       // null
          // A later finished turn lights; busy shows working; the open chat never does.
          a.observe([row('s', 'x:4'), row('t', 'x:0')], null);
          st(row('s', 'x:4'), null);                       // new
          st(row('s', 'x:4', true), null);                 // working
          st(row('s', 'x:4'), 's');                        // null (open)
          // A stale refetch never lowers the count.
          a.observe([row('s', 'x:3')], null);
          st(row('s', 'x:3'), null);                       // new
          // A row first seen after baselining counts from 0.
          a.observe([row('s', 'x:4'), row('u', 'x:1')], null);
          st(row('u', 'x:1'), null);                       // new
          // Opening clears it and keeps it clear.
          a.observe([row('s', 'x:4'), row('u', 'x:1')], 'u');
          st(row('u', 'x:1'), null);                       // null
          // A restart (new epoch): silent re-baseline, even though n went down...
          a.observe([row('s', 'y:0'), row('u', 'y:0')], null);
          st(row('s', 'y:0'), null);                       // null
          // ...and later turns still light.
          a.observe([row('s', 'y:1'), row('u', 'y:0')], null);
          st(row('s', 'y:1'), null);                       // new
          st(row('u', 'y:0'), null);                       // null
          return log;
        }"""
    )
    assert out == [None, "new", "working", None, "new", "new", None, None, "new", None], out
