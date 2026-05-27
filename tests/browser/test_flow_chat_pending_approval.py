"""Browser test for M11 F9 L4 — chat-ui-pending-approval banner.

Verifies that:
- A connector-context session with a seeded pending_approvals row
  renders an interactive pending-approval banner on session join via
  the merged history stream (``_restore_session`` + codec projection).
- Clicking Approve POSTs to L3's approve endpoint, the buttons are
  replaced with an ``approved`` status badge, and the connector
  account's allowlist gains the peer_id.
- Clicking Dismiss on a fresh pending row POSTs to L3's dismiss
  endpoint and surfaces a ``dismissed`` badge (no allowlist mutation).
- Dedup: when the same approval_id is re-emitted (replay + live), the
  banner does NOT double-render in the DOM.

Fixtures (``app_with_data_dir``, ``_free_port``, ``_wait_for_ready``)
mirror ``tests/browser/test_flow_chat_peer_attribution.py``. The
``_seed_*`` helpers INSERT directly via sync sqlite3 because the test
runner process is outside the app subprocess; SQLite file-locking
handles the read-after-write cross-process. Pending-approval rows are
seeded via SQLite (no API endpoint to create them — they are inserted
only by the inbound dispatcher in production); the L3 approve/dismiss
endpoints are exercised via the Approve/Dismiss button clicks themselves.
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

import httpx
import pytest
from browser.seeders import seed_connector_account, seed_mock_agent, seed_mock_provider
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

    Mirrors the duplicate fixture in ``test_flow_chat_peer_attribution.py``
    — the conftest ``app_clean`` fixture hides ``data_dir`` inside its
    body, but this test needs the path to seed connector + session +
    pending_approvals rows directly via SQLite.
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


def _seed_connector_session(
    data_dir: Path,
    *,
    session_id: str,
    agent_name: str,
    title: str,
    connector_account_id: str,
    peer_id: str,
) -> None:
    """INSERT a chat_sessions row pinned to a connector account + peer.

    Mirrors the 13-column INSERT in
    ``tests/browser/test_flow_chat_session_list_source_badge.py:158`` —
    fully populated keying tuple so ``_restore_session``'s merge path
    sees ``connector_account_id`` and ``peer_id`` non-None.
    """
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at,"
            " platform, connector_account_id, channel_id, thread_id, peer_id,"
            " session_metadata, last_inbound_at"
            ") VALUES (?, ?, ?, ?, datetime('now'), datetime('now'),"
            " ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                agent_name,
                title,
                "[]",
                "stub",
                connector_account_id,
                "channel-1",
                None,
                peer_id,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_pending_approval(
    data_dir: Path,
    *,
    approval_id: str,
    connector_account_id: str,
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
            " id, connector_account_id, peer_id, peer_name, preview,"
            " received_at, status, resolved_at"
            ") VALUES (?, ?, ?, ?, ?, datetime('now'), ?, NULL)",
            (
                approval_id,
                connector_account_id,
                peer_id,
                peer_name,
                preview,
                status,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _allowlist_peers(base_url: str, account_id: str) -> list[str]:
    """Fetch the connector account and return its peer allowlist."""
    r = httpx.get(f"{base_url}/api/connector-accounts/{account_id}", timeout=5.0)
    assert r.status_code == 200, r.text
    config = r.json().get("config") or {}
    allowlist = config.get("allowlist") or {}
    return list(allowlist.get("peers") or [])


@pytest.mark.browser
def test_pending_approval_banner_renders_on_session_join(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """A connector-context session with a seeded pending approval row
    renders the banner on session join — peer name + preview + two
    interactive buttons."""
    base_url, data_dir = app_with_data_dir

    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)
    account_id = seed_connector_account(base_url, name="Test Stub")

    session_id = str(uuid.uuid4())
    approval_id = uuid.uuid4().hex
    peer_id = "peer-render"
    _seed_connector_session(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        title="pending approval test",
        connector_account_id=account_id,
        peer_id=peer_id,
    )
    _seed_pending_approval(
        data_dir,
        approval_id=approval_id,
        connector_account_id=account_id,
        peer_id=peer_id,
        peer_name="Alice",
        preview="hello bot please help",
    )

    page.goto(f"{base_url}#chat/sessions/{session_id}")

    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )
    banner = page.locator('[data-testid="pending-approval-banner"]')
    expect(banner).to_have_count(1, timeout=5000)
    # Approval id matches the seeded value.
    expect(banner).to_have_attribute("data-approval-id", approval_id)
    expect(banner).to_have_attribute("data-connector-account-id", account_id)
    # Peer name + preview are rendered.
    expect(banner.locator(".msg-pending-approval-peer-name")).to_have_text("Alice")
    expect(banner.locator(".msg-pending-approval-preview")).to_have_text(
        "hello bot please help"
    )
    # Two action buttons present.
    expect(banner.locator('[data-testid="pending-approval-approve"]')).to_have_count(1)
    expect(banner.locator('[data-testid="pending-approval-dismiss"]')).to_have_count(1)
    # No badge yet (still pending).
    expect(banner.locator('[data-testid="pending-approval-badge"]')).to_have_count(0)


@pytest.mark.browser
def test_pending_approval_approve_click_updates_status_and_allowlist(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """Clicking Approve replaces buttons with the ``approved`` badge and
    adds the peer to the connector account's allowlist (verified via
    a follow-up GET against the connector accounts API)."""
    base_url, data_dir = app_with_data_dir

    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)
    account_id = seed_connector_account(base_url, name="Approve Test Stub")

    session_id = str(uuid.uuid4())
    approval_id = uuid.uuid4().hex
    peer_id = "peer-approve-flow"
    _seed_connector_session(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        title="approve flow",
        connector_account_id=account_id,
        peer_id=peer_id,
    )
    _seed_pending_approval(
        data_dir,
        approval_id=approval_id,
        connector_account_id=account_id,
        peer_id=peer_id,
        peer_name="Bob",
        preview="please approve me",
    )

    # Sanity precondition: allowlist does NOT yet include the peer.
    assert peer_id not in _allowlist_peers(base_url, account_id)

    page.goto(f"{base_url}#chat/sessions/{session_id}")
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )

    banner = page.locator('[data-testid="pending-approval-banner"]')
    expect(banner).to_have_count(1, timeout=5000)
    banner.locator('[data-testid="pending-approval-approve"]').click()

    # Status badge appears with 'approved'; buttons are gone.
    badge = banner.locator('[data-testid="pending-approval-badge"]')
    expect(badge).to_have_count(1, timeout=5000)
    expect(badge).to_have_text("approved")
    expect(banner.locator('[data-testid="pending-approval-approve"]')).to_have_count(0)
    expect(banner.locator('[data-testid="pending-approval-dismiss"]')).to_have_count(0)

    # Server-side mutation: the peer is now on the allowlist.
    assert peer_id in _allowlist_peers(base_url, account_id)


@pytest.mark.browser
def test_pending_approval_dismiss_click_updates_status(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """Clicking Dismiss surfaces the ``dismissed`` badge. Allowlist is
    not mutated."""
    base_url, data_dir = app_with_data_dir

    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)
    account_id = seed_connector_account(base_url, name="Dismiss Test Stub")

    session_id = str(uuid.uuid4())
    approval_id = uuid.uuid4().hex
    peer_id = "peer-dismiss-flow"
    _seed_connector_session(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        title="dismiss flow",
        connector_account_id=account_id,
        peer_id=peer_id,
    )
    _seed_pending_approval(
        data_dir,
        approval_id=approval_id,
        connector_account_id=account_id,
        peer_id=peer_id,
        peer_name="Carol",
        preview="please dismiss me",
    )

    initial_peers = _allowlist_peers(base_url, account_id)

    page.goto(f"{base_url}#chat/sessions/{session_id}")
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )

    banner = page.locator('[data-testid="pending-approval-banner"]')
    expect(banner).to_have_count(1, timeout=5000)
    banner.locator('[data-testid="pending-approval-dismiss"]').click()

    badge = banner.locator('[data-testid="pending-approval-badge"]')
    expect(badge).to_have_count(1, timeout=5000)
    expect(badge).to_have_text("dismissed")
    expect(banner.locator('[data-testid="pending-approval-approve"]')).to_have_count(0)
    expect(banner.locator('[data-testid="pending-approval-dismiss"]')).to_have_count(0)

    # Allowlist unchanged.
    assert _allowlist_peers(base_url, account_id) == initial_peers


@pytest.mark.browser
def test_pending_approval_dedup_replay_then_live_broadcast(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """Dispatch a synthetic live ``pending-approval`` WS event whose
    ``approval_id`` matches the replay-emitted banner. The frontend's
    ``seenApprovalIds`` Set should skip the re-render, leaving exactly
    one banner in the DOM.

    The synthetic WS dispatch is simulated by directly invoking the
    chat.js dispatch path: we evaluate a script in the page context
    that calls ``ws.dispatchEvent`` with a MessageEvent carrying the
    same JSON shape the dispatcher emits at
    ``_inbound.py:dispatch_inbound``. This isolates the dedup contract
    from the dispatcher's emit side (which is tested separately in
    backend tests).
    """
    base_url, data_dir = app_with_data_dir

    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)
    account_id = seed_connector_account(base_url, name="Dedup Test Stub")

    session_id = str(uuid.uuid4())
    approval_id = uuid.uuid4().hex
    peer_id = "peer-dedup-flow"
    _seed_connector_session(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        title="dedup flow",
        connector_account_id=account_id,
        peer_id=peer_id,
    )
    _seed_pending_approval(
        data_dir,
        approval_id=approval_id,
        connector_account_id=account_id,
        peer_id=peer_id,
        peer_name="Dana",
        preview="dedup preview",
    )

    page.goto(f"{base_url}#chat/sessions/{session_id}")
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )

    banner = page.locator('[data-testid="pending-approval-banner"]')
    expect(banner).to_have_count(1, timeout=5000)

    # Simulate a duplicate live WS broadcast of the SAME approval_id.
    # The chat.js onmessage handler reads from the WebSocket; we fake
    # it by dispatching a synthetic MessageEvent on the live WS object.
    # The handler reads JSON.parse(event.data) so we encode the same
    # canonical event shape from _inbound.py:443.
    duplicate_payload = {
        "type": "pending-approval",
        "approval_id": approval_id,
        "peer_name": "Dana",
        "peer_id": peer_id,
        "preview": "dedup preview",
        "received_at": "2099-01-01T00:00:00Z",
        "connector_account_id": account_id,
        "status": "pending",
    }
    page.evaluate(
        """payload => {
            const chat = window.App.areas.find(a => a.id === 'chat');
            if (!chat) throw new Error('chat area not registered');
            const ws = chat._ws && chat._ws();
            if (!ws) throw new Error('no live ws on chat area');
            ws.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(payload) }));
        }""",
        duplicate_payload,
    )

    # Still exactly one banner — dedup tripped.
    expect(banner).to_have_count(1)
