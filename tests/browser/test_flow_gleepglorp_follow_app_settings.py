"""The Settings pages follow a change the operator approved in a GleepGlorp chat (M36 F5 L4b, flight
DD8, DD9 and DD14).

Knowledge indexing: with the page open, an approved ``app_settings`` change lands without a reload
or a re-mount: a clean field takes the stored value, a field the operator changed keeps their value
while its baseline moves, and a quiet note sits under each changed field.

Date and time: an approved zone change re-renders an open Date and time page (radio, chosen zone)
with one follow note after the zone radio group, cleared by the operator's next choice. The app's
own clock (``App.time``) moves in EVERY open window, whatever page it shows: the second-window test
approves through the route and watches the chat message times of a window on Chats, a rendered
time that subscribes through ``App.time.onChange`` (``areas/chat/instance.js``).

Most tests signal through ``App.approvals.record`` after changing the stored settings through the
API; the real-approval tests approve a seeded proposal through the route.

Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.conftest import credentialed_context
from browser.seeders import (
    seed_gleepglorp_proposal,
    seed_mock_agent,
    seed_mock_provider,
    seed_session,
)
from browser.test_flow_agent_editor_follows_approval import _visit_chats
from browser.test_flow_chat_proposals import _world
from playwright.sync_api import Browser, Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message

pytestmark = pytest.mark.browser

SIZE = '[data-testid="knowledge-size-chars-input"]'
OVERLAP = '[data-testid="knowledge-overlap-chars-input"]'
INTERVAL = '[data-testid="knowledge-reconcile-interval-input"]'
SAVE = '[data-testid="knowledge-settings-save-btn"]'
CANCEL = '[data-testid="knowledge-settings-cancel-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
K_NOTE = '[data-testid="knowledge-settings-approved-change-note"]'
D_NOTE = '[data-testid="date-time-approved-change-note"]'
MODE_ZONE = '[data-testid="date-time-mode-zone"]'
MODE_SYSTEM = '[data-testid="date-time-mode-system"]'
CHOSEN = '[data-testid="date-time-chosen"]'
KIRITIMATI = "Pacific/Kiritimati"
PAGO = "Pacific/Pago_Pago"
TOKYO = "Asia/Tokyo"
NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
_pid = [700]


def _auth(base: str) -> dict:
    return auth_headers_for(base)


def _signal(page: Page, target: str, fields: list[str]) -> None:
    _pid[0] += 1
    page.evaluate(
        "(d) => App.approvals.record(d)",
        {
            "kind": "app_settings",
            "target_id": target,
            "fields": fields,
            "session_id": "sess-approved",
            "proposal_id": _pid[0],
            "at": "2026-01-02T15:05:00+00:00",
        },
    )


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


def _put_knowledge(base: str, size: int, overlap: int, interval: int) -> None:
    r = httpx.put(
        f"{base}/api/knowledge-settings",
        json={
            "chunking": {"size_chars": size, "overlap_chars": overlap},
            "monitoring": {"watch_enabled": True, "reconcile_interval_seconds": interval},
        },
        headers=_auth(base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text


def _put_time(base: str, mode: str, zone: str | None) -> None:
    r = httpx.put(
        f"{base}/api/time-settings",
        json={"mode": mode, "zone": zone},
        headers=_auth(base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text


def _open_knowledge(page: Page, base: str) -> None:
    _nav.goto_settled(page, base, "settings/knowledge-indexing")
    expect(page.locator(SIZE)).not_to_have_value("", timeout=10000)
    expect(page.locator(UNSAVED)).to_have_text("")


# ── Knowledge indexing ───────────────────────────────────────────────────────


def test_an_approved_change_lands_in_a_clean_page_without_a_reload_with_notes(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _open_knowledge(page, base)
    page.evaluate("() => { window.__same_page = 1; }")
    _put_knowledge(base, 800, 100, 120)
    _signal(page, "knowledge-indexing", ["chunk_size_chars", "reconcile_interval_seconds"])
    expect(page.locator(SIZE)).to_have_value("800", timeout=8000)
    expect(page.locator(INTERVAL)).to_have_value("120")
    expect(page.locator(OVERLAP)).to_have_value("100")  # a clean field takes the stored value
    for field, control in (("chunk_size_chars", SIZE), ("reconcile_interval_seconds", INTERVAL)):
        note = f'{K_NOTE}[data-field="{field}"]'
        expect(page.locator(note)).to_have_count(1)
        assert _describes(page, control, note)
    expect(page.locator(UNSAVED)).to_have_text("")
    assert page.evaluate("() => window.__same_page") == 1


def test_a_dirty_field_keeps_the_operators_value_while_the_baseline_moves(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _open_knowledge(page, base)
    page.locator(SIZE).fill("900")
    _put_knowledge(base, 800, 100, 120)
    _signal(page, "knowledge-indexing", ["chunk_size_chars", "reconcile_interval_seconds"])
    expect(page.locator(INTERVAL)).to_have_value("120", timeout=8000)
    expect(page.locator(SIZE)).to_have_value("900")  # the operator's, kept
    expect(page.locator(f'{K_NOTE}[data-field="reconcile_interval_seconds"]')).to_have_count(1)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    page.locator(CANCEL).click()  # Cancel shows the approved (now baseline) values
    expect(page.locator(SIZE)).to_have_value("800")
    expect(page.locator(K_NOTE)).to_have_count(0)


def test_a_real_approval_reaches_the_open_knowledge_page(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    before = httpx.get(f"{w.base}/api/knowledge-settings", headers=_auth(w.base), timeout=5).json()
    old = before["chunking"]["size_chars"]
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="app_settings",
        agent_name=None,
        target_id="knowledge-indexing",
        changes={"chunk_size_chars": 800},
        base={"chunk_size_chars": old},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, "settings/knowledge-indexing")
    expect(page.locator(SIZE)).not_to_have_value("", timeout=10000)
    r = httpx.post(
        f"{w.base}/api/gleepglorp/proposals/{prop}/approve", headers=_auth(w.base), timeout=10
    )
    assert r.status_code == 200, r.text
    expect(page.locator(SIZE)).to_have_value("800", timeout=8000)
    expect(page.locator(f'{K_NOTE}[data-field="chunk_size_chars"]')).to_have_count(1, timeout=8000)


# ── Date and time ────────────────────────────────────────────────────────────


def test_an_approved_zone_change_rerenders_an_open_date_page_with_a_note_until_the_next_choice(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _put_time(base, "zone", KIRITIMATI)
    _nav.goto_settled(page, base, "settings/date-and-time")
    expect(page.locator(MODE_ZONE)).to_be_checked(timeout=10000)
    expect(page.locator(CHOSEN)).to_contain_text("Kiritimati")
    _put_time(base, "zone", TOKYO)
    _signal(page, "date-and-time", ["time_zone"])
    expect(page.locator(CHOSEN)).to_contain_text("Tokyo", timeout=8000)
    expect(page.locator(MODE_ZONE)).to_be_checked()
    expect(page.locator(D_NOTE)).to_have_count(1)
    assert _describes(page, MODE_ZONE, D_NOTE)
    assert _describes(page, MODE_SYSTEM, D_NOTE)
    assert page.evaluate("() => App.time.zone()") == TOKYO
    # The operator's next choice clears the note.
    page.locator(MODE_SYSTEM).check()
    expect(page.locator(D_NOTE)).to_have_count(0)


def test_an_approval_arriving_during_the_operators_save_does_not_void_its_saved_status(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    from browser._mcp_editor import _hold_requests

    base, _data = app_with_data_dir
    _put_time(base, "zone", KIRITIMATI)
    _nav.goto_settled(page, base, "settings/date-and-time")
    expect(page.locator(MODE_ZONE)).to_be_checked(timeout=10000)
    held = _hold_requests(page, "**/api/time-settings", "PUT")
    page.locator(MODE_SYSTEM).check()
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the operator's PUT never left the page"
    _put_time(base, "zone", TOKYO)
    _signal(page, "date-and-time", ["time_zone"])
    expect(page.locator(D_NOTE)).to_have_count(1, timeout=8000)
    held[0].continue_()
    expect(page.get_by_text("Saved. Agents now use the system time zone.")).to_be_visible(
        timeout=8000
    )


def test_a_time_zone_change_in_system_mode_shows_the_page_in_use_this_zone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    _put_time(w.base, "system", None)
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="app_settings",
        agent_name=None,
        target_id="date-and-time",
        changes={"time_zone_mode": "zone", "time_zone": TOKYO},
        base={"time_zone_mode": "system", "time_zone": None},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, "settings/date-and-time")
    expect(page.locator(MODE_SYSTEM)).to_be_checked(timeout=10000)
    r = httpx.post(
        f"{w.base}/api/gleepglorp/proposals/{prop}/approve", headers=_auth(w.base), timeout=10
    )
    assert r.status_code == 200, r.text
    expect(page.locator(MODE_ZONE)).to_be_checked(timeout=8000)
    expect(page.locator(CHOSEN)).to_contain_text("Tokyo")
    expect(page.locator(D_NOTE)).to_have_count(1)


def test_a_real_approval_moves_the_clock_in_every_window_whatever_page_it_shows(
    app_with_data_dir: tuple[str, Any], browser: Browser
) -> None:
    w = _world(app_with_data_dir)
    agent = "chatty"
    seed_mock_agent(w.base, seed_mock_provider(w.base, name="clock-mock"), agent)
    msgs = [
        Message.user("hello", created_at="2026-06-15T11:30:00+00:00"),
        Message.assistant("hi there"),
    ]
    msgs[1].created_at = "2026-06-15T11:31:00+00:00"
    seed_session(
        w.base, agent, "Chat A", "2026-06-15T11:30:00+00:00", messages=encode_messages(msgs)
    )
    _put_time(w.base, "zone", KIRITIMATI)
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="app_settings",
        agent_name=None,
        target_id="date-and-time",
        changes={"time_zone": PAGO},
        base={"time_zone": KIRITIMATI},
    )
    context = credentialed_context(browser, w.base, timezone_id=PAGO)
    try:
        date_page = context.new_page()
        chat_page = context.new_page()
        for p in (date_page, chat_page):
            p.clock.set_fixed_time(NOW)
        _nav.goto_settled(date_page, w.base, "settings/date-and-time")
        expect(date_page.locator(MODE_ZONE)).to_be_checked(timeout=10000)
        # The second window shows Chats: no Date and time page is mounted there.
        _nav.goto_settled(chat_page, w.base, "chats")
        stamp = chat_page.locator(".ui-message-attribution-ts")
        expect(stamp.first).to_have_text("1:30 AM", timeout=10000)
        fixed = "() => App.time.formatClock(new Date('2026-06-15T11:30:00Z'))"
        assert chat_page.evaluate("() => App.time.zone()") == KIRITIMATI
        assert chat_page.evaluate(fixed) == "1:30 AM"
        r = httpx.post(
            f"{w.base}/api/gleepglorp/proposals/{prop}/approve", headers=_auth(w.base), timeout=10
        )
        assert r.status_code == 200, r.text
        for p in (date_page, chat_page):
            p.wait_for_function(f"() => App.time.zone() === '{PAGO}'", timeout=10000)
        assert chat_page.evaluate(fixed) == "12:30 AM"
        # The subscriber: a chat message time re-renders in the new zone, with no reload.
        expect(stamp.first).to_have_text("12:30 AM", timeout=8000)
        expect(date_page.locator(D_NOTE)).to_have_count(1, timeout=8000)
        expect(chat_page.locator(D_NOTE)).to_have_count(0)
    finally:
        context.close()
