# ruff: noqa: E501  (inline JS snippets and selectors are evaluated verbatim)
"""A routine run in the chat (M33 F1 L7, flight DD7 and DD10).

The message is the routine's (a user-side bubble attributed to the routine's name with a
"Routine" chip, no "[routine] " prefix, ``data-routine-id``), an open chat treats a routine
turn as in flight (thinking line, Stop works, sends are held, ``done`` ends it), and the agent
drawer shows the chat's routine as a fact plus a read-only Routines group. Frames are
injected through ``_chats.emit_frame`` (the real ``ws.onmessage`` path); no run happens.
Chromium; falls in the ``chats-transcript`` lane.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message

pytestmark = pytest.mark.browser

RID = "r-morning-1"


def _routine(base: str, agent: str, name: str, **over: object) -> dict:
    body = {
        "name": name,
        "prompt": "say hi",
        "schedule": {"kind": "daily", "time": "09:00"},
        "target": {"kind": "new"},
        **over,
    }
    r = httpx.post(
        f"{base}/api/agents/{agent}/routines",
        json=body,
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _seed_routine_chat(app: SeededApp, with_meta: bool = True) -> str:
    msgs = [
        Message.user("Check the weather", routine_id=RID, routine_name="Morning brief"),
        Message.assistant("Sunny."),
    ]
    return seed_session(
        app.base_url,
        app.agent_name,
        "routine chat",
        "2026-10-27T09:00:00+00:00",
        messages=encode_messages(msgs),
        session_metadata=(
            {
                "routine": {
                    "id": RID,
                    "name": "Morning brief",
                    "last_run_at": "2026-10-27T09:00:00+00:00",
                }
            }
            if with_meta
            else None
        ),
    )


def _open(page: Page, app: SeededApp, sid: str) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, app.base_url, "chats")
    _chats.open_chat(page, sid)


def test_replayed_routine_message_is_the_routines(app_with_agent: SeededApp, page: Page) -> None:
    sid = _seed_routine_chat(app_with_agent)
    _open(page, app_with_agent, sid)
    bubble = _chats.messages(page, "user")
    expect(bubble).to_have_count(1)
    expect(bubble).to_have_attribute("data-routine-id", RID)
    expect(bubble).to_have_text("RoutineCheck the weather")
    expect(bubble.locator(".ui-message-marker-chip .chip")).to_have_text("Routine")
    assert "[routine]" not in bubble.inner_text()
    attr = bubble.locator("xpath=following-sibling::*[1]")
    expect(attr).to_contain_text("Morning brief")
    expect(attr).not_to_contain_text("You")
    assert "ui-message-attribution--you" in (attr.get_attribute("class") or "")
    assert bubble.evaluate("el => getComputedStyle(el).alignSelf") == "flex-end"


def test_live_routine_frame_marks_the_chat_in_flight(app_with_agent: SeededApp, page: Page) -> None:
    sid = _seed_routine_chat(app_with_agent)
    other = seed_session(
        app_with_agent.base_url, app_with_agent.agent_name, "other", "2026-10-26T09:00:00+00:00"
    )
    frames = _chats.chat_frames(page)
    _open(page, app_with_agent, sid)
    stop = page.locator('[data-testid="chat-stop-btn"]')
    expect(stop).to_be_hidden()

    # A frame for another chat changes nothing.
    _chats.emit_frame(
        page,
        {
            "type": "user",
            "content": "elsewhere",
            "source": "routine",
            "routine_id": "x",
            "routine_name": "Other",
            "session_id": other,
        },
    )
    expect(page.locator('[data-testid="thinking-indicator"]')).to_have_count(0)
    expect(stop).to_be_hidden()

    _chats.emit_frame(
        page,
        {
            "type": "user",
            "content": "Run now",
            "source": "routine",
            "routine_id": RID,
            "routine_name": "Morning brief",
            "session_id": sid,
        },
    )
    live = _chats.messages(page, "user").last
    expect(live).to_have_attribute("data-routine-id", RID)
    expect(live).to_contain_text("Run now")
    assert "[routine]" not in live.inner_text()
    expect(page.locator('[data-testid="thinking-indicator"]')).to_be_visible()
    expect(stop).to_be_visible()
    expect(stop).to_be_enabled()
    # Sends are held.
    box = page.locator('[data-testid="chat-input"]')
    box.fill("while you run")
    box.press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_be_visible()
    assert not [f for f in frames if "message" in f]
    # done ends the routine turn; the held message goes out as an own turn.
    frames.clear()
    _chats.emit_frame(page, {"type": "done"})
    page.wait_for_timeout(400)
    sent = [f for f in frames if f.get("message") == "while you run"]
    assert len(sent) == 1


def test_stop_sends_cancel_during_a_routine_run(app_with_agent: SeededApp, page: Page) -> None:
    sid = _seed_routine_chat(app_with_agent)
    frames = _chats.chat_frames(page)
    _open(page, app_with_agent, sid)
    _chats.emit_frame(
        page,
        {
            "type": "user",
            "content": "go",
            "source": "routine",
            "routine_id": RID,
            "routine_name": "Morning brief",
            "session_id": sid,
        },
    )
    stop = page.locator('[data-testid="chat-stop-btn"]')
    expect(stop).to_be_enabled()
    page.locator('[data-testid="chat-input"]').fill("my draft")
    stop.click()
    page.wait_for_timeout(400)
    assert any(f.get("action") == "cancel" for f in frames)


def test_done_returns_the_chat_to_idle(app_with_agent: SeededApp, page: Page) -> None:
    sid = _seed_routine_chat(app_with_agent)
    _open(page, app_with_agent, sid)
    _chats.emit_frame(
        page,
        {
            "type": "user",
            "content": "go",
            "source": "routine",
            "routine_id": RID,
            "routine_name": "Morning brief",
            "session_id": sid,
        },
    )
    stop = page.locator('[data-testid="chat-stop-btn"]')
    expect(stop).to_be_visible()
    _chats.emit_frame(page, {"type": "done"})
    expect(stop).to_be_hidden()
    expect(page.locator('[data-testid="thinking-indicator"]')).to_have_count(0)


def test_non_routine_sources_keep_their_prefix(app_with_agent: SeededApp, page: Page) -> None:
    sid = _seed_routine_chat(app_with_agent)
    _open(page, app_with_agent, sid)
    _chats.emit_frame(page, {"type": "user", "content": "hello", "source": "api"})
    last = _chats.messages(page, "user").last
    expect(last).to_contain_text("[api] hello")
    assert last.get_attribute("data-routine-id") is None
    assert last.locator(".ui-message-marker-chip").count() == 0


def test_drawer_shows_the_routine_fact_and_group(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _routine(base, agent, "Zeta weekly")
    _routine(base, agent, "Alpha daily")
    off = _routine(base, agent, "Mid off")
    r = httpx.put(
        f"{base}/api/agents/{agent}/routines/{off['id']}",
        json={"enabled": False},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    sid = _seed_routine_chat(app_with_agent)
    _open(page, app_with_agent, sid)

    fact = page.locator('[data-testid="chat-drawer-routine"]')
    expect(fact).to_contain_text("Morning brief · last ran ")
    expect(fact).to_have_text(
        re.compile(r"^Morning brief · last ran [A-Z][a-z]{2}( \d+)? \d{1,2}:\d{2} [AP]M$")
    )
    items = page.locator('[data-testid="chat-drawer-routine-item"]')
    expect(items).to_have_count(3)
    names = items.locator(".chat-drawer-item-name").all_inner_texts()
    assert names == ["Alpha daily", "Mid off", "Zeta weekly"]
    metas = items.locator(".chat-drawer-item-meta").all_inner_texts()
    assert metas[0].startswith("Next ") and metas[1] == "Off" and metas[2].startswith("Next ")
    group = page.locator('[data-testid="chat-drawer-uses"] [data-group="routines"]')
    expect(group.locator("a, button")).to_have_count(0)
    groups = page.locator('[data-testid="chat-drawer-uses"] .chat-drawer-group')
    order = groups.evaluate_all("els => els.map(e => e.dataset.group)")
    assert order.index("routines") == order.index("notes") + 1


def test_drawer_has_no_fact_without_routine_metadata_and_none_when_empty(
    app_with_agent: SeededApp, page: Page
) -> None:
    sid = _seed_routine_chat(app_with_agent, with_meta=False)
    _open(page, app_with_agent, sid)
    expect(page.locator('[data-testid="chat-drawer-facts"]')).to_be_visible()
    expect(page.locator('[data-testid="chat-drawer-routine"]')).to_have_count(0)
    group = page.locator('[data-testid="chat-drawer-uses"] [data-group="routines"]')
    expect(group).to_contain_text("None")


def test_routine_fact_does_not_leak_to_another_chat(app_with_agent: SeededApp, page: Page) -> None:
    sid = _seed_routine_chat(app_with_agent)
    plain = seed_session(
        app_with_agent.base_url, app_with_agent.agent_name, "plain", "2026-10-26T09:00:00+00:00"
    )
    _open(page, app_with_agent, sid)
    expect(page.locator('[data-testid="chat-drawer-routine"]')).to_have_count(1)
    _chats.open_chat(page, plain)
    expect(page.locator('[data-testid="chat-drawer-routine"]')).to_have_count(0)
