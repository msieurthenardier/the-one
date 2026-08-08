"""Browser test for M10 F05 L07 — chat-session-list-source-badge e2e.

Verifies that the session list renders the ``.session-item-source`` badge
on connector-attached sessions (with the ``session-item-source--{platform}``
typed modifier) and OMITS the badge entirely on web-native sessions.

Test strategy:
- Spawn a fresh app subprocess (custom fixture exposes the data_dir so
  we can seed chat_sessions rows directly into the SQLite DB).
- Seed a provider + agent via the existing API seeders.
- INSERT two ``chat_sessions`` rows via direct sqlite3:
  - Row A: web-native (all seven connector-keying columns NULL).
  - Row B: connector-attached (``platform="stub"``,
    ``connector_id="stub-acct-1"``, ``channel_id="C1"``,
    ``thread_id=NULL``, ``peer_id="P1"``, ``session_metadata=NULL``,
    ``last_inbound_at=NULL``).
- Boot the page, navigate to chat, wait for the session list, and
  assert the DOM shape: connector row has ``.session-item-source`` +
  ``.session-item-source--stub`` with text ``"stub"``; web-native row
  has no ``.session-item-source`` child.

Per user-global rule (no committed snapshot baselines), this test uses
DOM-shape assertions only.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path

import pytest
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

# `app_with_data_dir` (Mission 20 / Flight 1 / Leg 3): formerly a local
# fixture duplicated verbatim across 8 `test_flow_*.py` files, now
# consolidated onto the shared `_spawn_app` path in `browser/conftest.py`
# — pytest auto-discovers it from the directory conftest, no import needed.


def _seed_session(
    data_dir: Path,
    *,
    session_id: str,
    agent_name: str,
    title: str,
    platform: str | None,
    connector_id: str | None,
    channel_id: str | None,
    thread_id: str | None,
    peer_id: str | None,
) -> None:
    """INSERT a chat_sessions row directly via sqlite3.

    Mirrors the 13-column INSERT in
    ``the_one/db/repositories.py:726-750`` (``ChatSessionRepository.create``);
    the test uses a sync sqlite3 connection because it executes against
    the subprocess's DB file from outside the process. The session has
    an empty ``messages`` JSON array — the only thing under test here
    is the session-list projection / source-badge render.
    """
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at,"
            " platform, connector_id, channel_id, thread_id, peer_id,"
            " session_metadata, last_inbound_at"
            ") VALUES (?, ?, ?, ?, datetime('now'), datetime('now'),"
            " ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                agent_name,
                title,
                "[]",
                platform,
                connector_id,
                channel_id,
                thread_id,
                peer_id,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.browser
def test_session_list_renders_source_badge_for_connector_attached_row(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """Connector-attached row shows the ``.session-item-source`` badge.

    Acceptance criteria coverage (per leg 07):
    - Connector-attached row shows ``.session-item-source`` AND
      ``.session-item-source--stub`` with text ``"stub"``.
    - Web-native row shows NO ``.session-item-source`` element.
    """
    base_url, data_dir = app_with_data_dir

    # Seed provider + agent via API (same path as app_with_agent fixture).
    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)

    web_sid = str(uuid.uuid4())
    connector_sid = str(uuid.uuid4())

    # Web-native row: all seven connector-keying columns NULL.
    _seed_session(
        data_dir,
        session_id=web_sid,
        agent_name=agent_name,
        title="web-native session",
        platform=None,
        connector_id=None,
        channel_id=None,
        thread_id=None,
        peer_id=None,
    )
    # Connector-attached row: platform="stub", channel_id/peer_id set,
    # thread_id NULL (the channel-only DM shape per L1 precedents).
    _seed_session(
        data_dir,
        session_id=connector_sid,
        agent_name=agent_name,
        title="connector-attached session",
        platform="stub",
        connector_id="stub-acct-1",
        channel_id="C1",
        thread_id=None,
        peer_id="P1",
    )

    # Open the chat area. The default landing area is chat; the session
    # list mounts as part of the chat chrome.
    page.goto(base_url)

    # Wait for the session list to render both seeded rows.
    expect(
        page.locator(f'.session-list .list-item:has(button[data-id="{web_sid}"])')
    ).to_be_visible(timeout=8000)
    expect(
        page.locator(f'.session-list .list-item:has(button[data-id="{connector_sid}"])')
    ).to_be_visible(timeout=8000)

    # Connector-attached row: assert badge presence, class modifier, text.
    connector_row = page.locator(f'.session-list .list-item:has(button[data-id="{connector_sid}"])')
    badge = connector_row.locator(".session-item-source")
    expect(badge).to_have_count(1)
    expect(badge).to_have_text("stub")
    expect(badge).to_have_class(re.compile(r"\bsession-item-source--stub\b"))

    # Web-native row: assert NO .session-item-source child element.
    web_row = page.locator(f'.session-list .list-item:has(button[data-id="{web_sid}"])')
    expect(web_row).to_be_visible()
    expect(web_row.locator(".session-item-source")).to_have_count(0)
