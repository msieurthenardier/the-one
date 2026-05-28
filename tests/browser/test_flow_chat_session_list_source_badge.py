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

import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_ready(base_url: str, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"App subprocess exited with code {proc.returncode} during startup"
            )
        try:
            r = httpx.get(f"{base_url}/api/info", timeout=1.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_exc = exc
        time.sleep(0.1)
    raise TimeoutError(f"App at {base_url} not ready within {timeout}s (last: {last_exc})")


@pytest.fixture
def app_with_data_dir(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Spawn a fresh app subprocess and yield ``(base_url, data_dir)``.

    Mirrors the local fixture in ``test_flow_chat_visibility_distinction.py``
    (L5). The shared ``app_with_agent`` fixture hides ``data_dir`` inside
    its body; this test needs the path to seed ``chat_sessions`` rows
    directly via SQLite. Teardown matches ``app_clean``'s SIGTERM pattern.
    """
    port = _free_port()
    data_dir = tmp_path / "the-one-data"
    data_dir.mkdir()

    env = os.environ.copy()
    env["THE_ONE_DATA_DIR"] = str(data_dir)
    env["THE_ONE_DEV_MODE"] = "true"
    env["THE_ONE_REGISTER_STUB_CONNECTOR"] = "1"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "the_one.interfaces.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{port}"

    try:
        _wait_for_ready(base_url, proc=proc, timeout=15.0)
    except (TimeoutError, RuntimeError):
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"App subprocess on port {port} did not become ready.\n"
            f"--- stdout ---\n{stdout.decode(errors='replace')}\n"
            f"--- stderr ---\n{stderr.decode(errors='replace')}"
        )

    try:
        yield base_url, data_dir
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


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
    connector_row = page.locator(
        f'.session-list .list-item:has(button[data-id="{connector_sid}"])'
    )
    badge = connector_row.locator(".session-item-source")
    expect(badge).to_have_count(1)
    expect(badge).to_have_text("stub")
    expect(badge).to_have_class(re.compile(r"\bsession-item-source--stub\b"))

    # Web-native row: assert NO .session-item-source child element.
    web_row = page.locator(
        f'.session-list .list-item:has(button[data-id="{web_sid}"])'
    )
    expect(web_row).to_be_visible()
    expect(web_row.locator(".session-item-source")).to_have_count(0)
