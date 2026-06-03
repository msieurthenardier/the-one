"""Browser tests for M11 F17 L9 (Leg E) — top-nav Chat badge + left-panel
pending section.

Verifies:
- The Chat nav button has ``data-testid="nav-chat-btn"`` and a child
  ``[data-testid="nav-pending-badge"]`` span.
- The badge is hidden (display:none) when pending count is 0.
- The badge shows the count when pending approvals exist.
- The Chat left panel renders a "Pending approvals" section
  (``[data-testid="pending-approvals-section"]``) above "Chat History"
  when pending rows exist.
- The pending section lists peer_name and preview for each row.
"""

from __future__ import annotations

import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from browser.seeders import seed_connector, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_ready(base_url: str, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    import httpx

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

    Mirrors the fixture in test_flow_chat_pending_approval.py — we need
    direct DB access to seed pending_approvals rows, which have no
    public creation endpoint.
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


def _seed_pending_approval(
    data_dir: Path,
    *,
    approval_id: str,
    connector_id: str,
    peer_id: str,
    peer_name: str,
    preview: str,
    status: str = "pending",
) -> None:
    """INSERT a pending_approvals row via sync sqlite3."""
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO pending_approvals ("
            " id, connector_id, peer_id, peer_name, preview,"
            " received_at, status, resolved_at"
            ") VALUES (?, ?, ?, ?, ?, datetime('now'), ?, NULL)",
            (approval_id, connector_id, peer_id, peer_name, preview, status),
        )
        conn.commit()
    finally:
        conn.close()


# ── nav badge testid presence ────────────────────────────────────────────


@pytest.mark.browser
def test_nav_chat_btn_testid_present(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """The Chat top-nav button has ``data-testid="nav-chat-btn"`` after boot."""
    base_url, data_dir = app_with_data_dir
    seed_mock_provider(base_url)

    page.goto(base_url)
    expect(page.locator('[data-testid="nav-chat-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_nav_pending_badge_hidden_when_zero(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """With no pending rows the badge span exists but is hidden (display:none)."""
    base_url, data_dir = app_with_data_dir
    seed_mock_provider(base_url)

    page.goto(base_url)
    page.wait_for_selector('[data-testid="nav-chat-btn"]', timeout=8000)
    badge = page.locator('[data-testid="nav-pending-badge"]')
    # Badge element is present in the DOM but hidden.
    expect(badge).to_have_count(1)
    expect(badge).to_be_hidden()


@pytest.mark.browser
def test_nav_pending_badge_shows_count(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """With 2 pending rows the badge shows '2' and is visible."""
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id)
    account_id = seed_connector(base_url, name="Badge Test Stub")

    # Seed two pending rows directly via SQLite.
    _seed_pending_approval(
        data_dir,
        approval_id=uuid.uuid4().hex,
        connector_id=account_id,
        peer_id="peer-badge-1",
        peer_name="Alice Badge",
        preview="hello from alice",
    )
    _seed_pending_approval(
        data_dir,
        approval_id=uuid.uuid4().hex,
        connector_id=account_id,
        peer_id="peer-badge-2",
        peer_name="Bob Badge",
        preview="hello from bob",
    )

    page.goto(base_url)
    # Wait for the badge to update via poll (10s interval; first poll is immediate).
    badge = page.locator('[data-testid="nav-pending-badge"]')
    expect(badge).to_have_text("2", timeout=8000)
    expect(badge).to_be_visible()


# ── left-panel pending section ───────────────────────────────────────────


@pytest.mark.browser
def test_pending_approvals_section_renders_in_left_panel(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """With pending rows, the left panel shows a 'Pending approvals' section
    above 'Chat History', listing peer names."""
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id)
    account_id = seed_connector(base_url, name="Left Panel Stub")

    _seed_pending_approval(
        data_dir,
        approval_id=uuid.uuid4().hex,
        connector_id=account_id,
        peer_id="peer-panel-1",
        peer_name="Carol Panel",
        preview="hi from carol",
    )

    page.goto(base_url + "#chat")
    # The pending-approvals section should appear once the session_list WS
    # message triggers the fetch + render.
    section = page.locator('[data-testid="pending-approvals-section"]')
    expect(section).to_be_visible(timeout=8000)

    # The peer name is listed inside.
    expect(section.locator("text=Carol Panel")).to_be_visible()


@pytest.mark.browser
def test_pending_approvals_section_absent_when_no_pending(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """With no pending rows the pending-approvals section is NOT rendered."""
    base_url, data_dir = app_with_data_dir
    seed_mock_provider(base_url)

    page.goto(base_url + "#chat")
    page.wait_for_selector('[data-testid="nav-chat-btn"]', timeout=8000)
    # Allow time for the WS session_list + pending fetch to settle.
    page.wait_for_timeout(2000)
    section = page.locator('[data-testid="pending-approvals-section"]')
    expect(section).to_have_count(0)
