"""Clock times and day groups follow the operator's time zone (M28 F2 L1, DD1).

The browser is Pacific/Pago_Pago (UTC-11) and the operator zone is Pacific/Kiritimati
(UTC+14), 25 hours apart, so every instant is on a different calendar day in the two.
The page clock is fixed (``page.clock.set_fixed_time``, before ``goto``) at
2026-06-15T12:00Z: Kiritimati reads Tue Jun 16 02:00, Pago Pago Mon Jun 15 01:00.
``page.clock.install()`` is never used: it would break ``_nav.wait_settled``.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.conftest import credentialed_context
from browser.seeders import (
    SeededApp,
    seed_mock_agent,
    seed_mock_provider,
    seed_note,
    seed_session,
)
from playwright.sync_api import Browser, Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message

pytestmark = pytest.mark.browser

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
KIRITIMATI = "Pacific/Kiritimati"
PAGO = "Pacific/Pago_Pago"

_LIST_JS = """
() => Array.from(document.querySelectorAll('[data-testid="chats-list"] .ui-list-pane-group'))
  .filter((g) => !g.hidden)
  .map((g) => [g.querySelector('.ui-list-pane-caption').textContent,
    Array.from(g.querySelectorAll('li')).map((li) => [
      li.querySelector('.ui-list-pane-label').textContent,
      (li.querySelector('.ui-list-pane-time') || {textContent: ''}).textContent])])
"""

KIR_LIST = [
    ["Today", [["Chat A", "1:30 AM"], ["Chat B", "12:30 AM"]]],
    ["Yesterday", [["Chat C", "Mon"]]],
]
PAGO_LIST = [
    ["Today", [["Chat A", "12:30 AM"]]],
    ["Yesterday", [["Chat B", "Sun"], ["Chat C", "Sun"]]],
]


@pytest.fixture
def zone_app(app_with_data_dir: tuple[str, Path]) -> tuple[SeededApp, Path]:
    base, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base)
    agent = seed_mock_agent(base, provider_id)
    r = httpx.put(
        f"{base}/api/time-settings",
        json={"mode": "zone", "zone": KIRITIMATI},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    seeded = SeededApp(base_url=base, provider_id=provider_id, agent_name=agent)
    msgs_list = [
        Message.user("hello", created_at="2026-06-15T11:30:00+00:00"),
        Message.assistant("hi there"),
    ]
    msgs_list[1].created_at = "2026-06-15T11:31:00+00:00"
    msgs = encode_messages(msgs_list)
    # Chat A carries the replayed messages (stamped).
    seed_session(base, agent, "Chat A", "2026-06-15T11:30:00+00:00", messages=msgs)
    seed_session(base, agent, "Chat B", "2026-06-15T10:30:00+00:00")
    seed_session(base, agent, "Chat C", "2026-06-15T09:00:00+00:00")
    seed_note(data_dir, agent, "A dated note.", created_at="2026-06-15T09:00:00+00:00")
    return seeded, data_dir


@pytest.fixture
def zpage(browser: Browser, zone_app: tuple[SeededApp, Path]) -> Any:
    context = credentialed_context(browser, zone_app[0].base_url, timezone_id=PAGO)
    page = context.new_page()
    page.clock.set_fixed_time(NOW)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.errors = errors  # type: ignore[attr-defined]
    try:
        yield page
    finally:
        context.close()


def _list(page: Page) -> list[Any]:
    return page.evaluate(_LIST_JS)


def _expect_list(page: Page, want: list[Any]) -> None:
    for _ in range(40):
        if _list(page) == want:
            return
        page.wait_for_timeout(100)
    assert _list(page) == want


def _stamps(page: Page) -> list[str]:
    return page.locator(".msg-attribution-ts").all_inner_texts()


def _expect_stamps(page: Page, want: list[str]) -> None:
    for _ in range(40):
        if _stamps(page) == want:
            return
        page.wait_for_timeout(100)
    assert _stamps(page) == want


def test_list_attribution_and_notes_follow_the_operator_zone(
    zone_app: tuple[SeededApp, Path], zpage: Page
) -> None:
    seeded, _data_dir = zone_app
    base, agent = seeded.base_url, seeded.agent_name
    page = zpage
    _nav.goto_settled(page, base, "chats")
    assert page.evaluate("() => App.time.zone()") == KIRITIMATI
    expect(_chats.chat_rows(page)).to_have_count(3, timeout=8000)
    _expect_list(page, KIR_LIST)
    # A cold #chats joins the newest session: Chat A's replayed attributions.
    _chats.expect_chat(page, agent, title="Chat A")
    _expect_stamps(page, ["1:30 AM", "1:31 AM"])

    # Changing the zone re-labels the list and the stamps without a reload.
    page.evaluate(f"() => App.time.setZone('{PAGO}')")
    _expect_list(page, PAGO_LIST)
    _expect_stamps(page, ["12:30 AM", "12:31 AM"])
    page.evaluate(f"() => App.time.setZone('{KIRITIMATI}')")
    _expect_list(page, KIR_LIST)

    # The notes "when" label, and the self-unsubscribing listener across a tab switch.
    _nav.goto_settled(page, base, f"agents/{_nav.seg(agent)}/rules-and-notes")
    expect(page.locator('[data-testid="notes-row-time"]')).to_have_text("Jun 15", timeout=8000)
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-testid="tab-rules-and-notes"]').click()
    expect(page.locator('[data-testid="notes-row-time"]')).to_have_text("Jun 15", timeout=8000)
    page.evaluate(
        """() => {
          window.__adds = 0;
          const wrap = document.querySelector('[data-testid="notes-section"] .rules-list-wrap');
          new MutationObserver((rs) => rs.forEach((r) => { window.__adds += r.addedNodes.length; }))
            .observe(wrap, {childList: true});
        }"""
    )
    page.evaluate(f"() => App.time.setZone('{PAGO}')")
    expect(page.locator('[data-testid="notes-row-time"]')).to_have_text("Jun 14", timeout=8000)
    assert page.evaluate("() => window.__adds") == 1
    assert page.errors == []  # type: ignore[attr-defined]


def test_boot_waits_at_most_two_seconds_for_the_time_zone(
    zone_app: tuple[SeededApp, Path], zpage: Page
) -> None:
    base = zone_app[0].base_url
    page = zpage
    held: list[Any] = []
    page.route("**/api/time-settings", lambda route: held.append(route))
    # Plain goto + expect, never goto_settled/wait_settled: they would wait on the held fetch.
    _nav.goto(page, base, "chats")
    expect(_chats.chat_rows(page)).to_have_count(3, timeout=3000 + 5000)
    # The router started and the list rendered in the browser zone (Pago Pago).
    _expect_list(page, PAGO_LIST)
    assert held
    held[0].continue_()
    _expect_list(page, KIR_LIST)
