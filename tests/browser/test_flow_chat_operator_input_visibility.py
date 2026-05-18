"""Browser test for M10 F05 L07 — chat operator-input visibility e2e.

Verifies the L4 ``ws-storage-edge`` shim's write path end-to-end
through the browser: when the operator types a turn into a
connector-attached session (a session with ``platform`` set), the
persisted USER + ASSISTANT messages carry ``visibility="operator"``
and — after a refresh that forces the codec replay path — render with
the ``msg-operator-only`` class + ``[operator-only]`` label.

The negative-control test exercises the same flow on a web-native
session (``platform`` unset) and confirms the resulting bubbles do NOT
carry the operator-only marker.

Test strategy:
- Spawn a fresh app subprocess (custom fixture exposes ``data_dir``
  so we can seed ``chat_sessions`` rows directly into the SQLite DB).
- Seed a provider + agent via the existing API seeders.
- Seed ONE session row (connector-attached for the happy path; web-
  native for the negative control) with an empty ``messages`` JSON
  array — the test drives the first turn.
- Deep-link to ``#chat/sessions/<id>``, type a message, submit, wait
  for the deterministic mock-provider reply, then refresh and
  re-navigate to force the codec replay path.
- Assert DOM shape via Playwright ``locator`` / ``evaluate``.

Per user-global rule (no committed snapshot baselines), these tests
use DOM-shape assertions only.

Known L5 limitation acknowledged: live-broadcast events do not yet
carry ``visibility``. The L4 storage-edge shim tags the persisted
messages AFTER ``agent.step`` completes; the refresh + re-navigate
exercises the codec replay path that carries the tag through to the
render. The L5 leg log documented this and the L7 leg artifact
explicitly designs the test to respect it.
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
    directly via SQLite.
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
    connector_account_id: str | None,
    channel_id: str | None,
    thread_id: str | None,
    peer_id: str | None,
) -> None:
    """INSERT a chat_sessions row directly via sqlite3.

    Mirrors the 13-column INSERT in
    ``the_one/db/repositories.py:726-750`` (``ChatSessionRepository.create``);
    the test uses a sync sqlite3 connection because it executes against
    the subprocess's DB file from outside the process. Empty
    ``messages`` JSON array — the test drives the first turn.
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
                platform,
                connector_account_id,
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


def _drive_one_turn(
    page: Page,
    *,
    base_url: str,
    agent_name: str,
    session_id: str,
) -> None:
    """Deep-link, type, submit, wait for mock reply. Common to both tests.

    Uses the verified selectors from
    ``tests/browser/test_flow_chat.py:33-34`` for the input + send button
    and the deterministic mock-provider reply text from
    ``tests/browser/test_flow_chat.py:44``
    (``"Mock response from the mock provider."``).
    """
    page.goto(f"{base_url}#chat/sessions/{session_id}")

    # Wait for chrome to mount with the seeded agent's badge.
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )

    # Type + submit the operator's turn.
    page.locator('[data-testid="chat-input"]').fill("hello")
    page.locator('[data-testid="chat-send-btn"]').click()

    # Wait for the deterministic mock-provider reply to render.
    expect(
        page.locator(
            '[data-testid="message"].assistant',
            has_text="Mock response from the mock provider.",
        )
    ).to_be_visible(timeout=30_000)

    # Send button re-enables after the `done` event — this is the
    # cleanest signal that the storage-edge shim has had a chance to
    # tag the persisted messages with ``visibility="operator"``.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10_000)


@pytest.mark.browser
def test_operator_input_yields_operator_visibility_on_connector_session(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """A typed turn on a connector-attached session is tagged operator-only.

    After typing + reply + refresh, both the USER and ASSISTANT bubbles
    carry the ``msg-operator-only`` class and the ``[operator-only]``
    label.

    Acceptance criteria coverage (per leg 07):
    - Operator types into a connector-attached session AND refreshes.
    - Resulting USER + ASSISTANT bubbles have ``msg-operator-only``
      class + ``[operator-only]`` label.
    """
    base_url, data_dir = app_with_data_dir

    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)

    session_id = str(uuid.uuid4())
    _seed_session(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        title="connector-attached operator-input test",
        platform="stub",
        connector_account_id="stub-acct-1",
        channel_id="C1",
        thread_id=None,
        peer_id="P1",
    )

    _drive_one_turn(
        page,
        base_url=base_url,
        agent_name=agent_name,
        session_id=session_id,
    )

    # Refresh + re-navigate to force the codec replay path. Live
    # broadcasts do not yet carry visibility (known L5 limitation);
    # the storage-edge shim has tagged the persisted messages by now,
    # so the codec's ``messages_to_ui_events`` projection will surface
    # the operator marker on replay.
    page.reload()
    page.goto(f"{base_url}#chat/sessions/{session_id}")
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )

    # At least one of each bubble must render on replay.
    expect(page.locator('[data-testid="message"].user').last).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="message"].assistant').last).to_be_visible(timeout=8000)

    # M10 F05 L08 HAT: the operator-only marker (class + label) is
    # suppressed on .msg.user bubbles — the operator knows what they
    # typed, the marker is visual noise on their own messages. The
    # underlying visibility tag is still persisted (verified via
    # dataset.visibility) so the contract that operator-typed
    # messages stay local is unbroken; only the visual presentation
    # is different. The marker still applies to assistant bubbles.
    user_bubble = page.locator('[data-testid="message"].user').last
    user_has_class = user_bubble.evaluate(
        "el => el.classList.contains('msg-operator-only')"
    )
    assert user_has_class is False, (
        "user bubble unexpectedly carries .msg-operator-only — the "
        "F5 L8 HAT decision suppresses the marker on the operator's "
        "own typed messages."
    )
    expect(user_bubble).to_have_attribute("data-visibility", "operator")

    assistant_bubble = page.locator('[data-testid="message"].assistant').last
    expect(assistant_bubble).to_have_class(re.compile(r"\bmsg-operator-only\b"))
    expect(assistant_bubble.locator(".msg-operator-only-label")).to_have_text(
        "[operator-only]"
    )


@pytest.mark.browser
def test_operator_input_yields_no_operator_visibility_on_web_session(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """Negative control: a typed turn on a web-native session is NOT tagged.

    The web-native session (no ``platform`` set) bypasses the L4
    storage-edge shim's visibility tagging. After typing + reply +
    refresh, neither the USER nor the ASSISTANT bubble carries the
    ``msg-operator-only`` class.

    Acceptance criteria coverage (per leg 07):
    - In a parallel web-native session, the typed turn has NO
      ``msg-operator-only`` markers (back-compat regression net).
    """
    base_url, data_dir = app_with_data_dir

    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)

    session_id = str(uuid.uuid4())
    _seed_session(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        title="web-native operator-input negative-control",
        platform=None,
        connector_account_id=None,
        channel_id=None,
        thread_id=None,
        peer_id=None,
    )

    _drive_one_turn(
        page,
        base_url=base_url,
        agent_name=agent_name,
        session_id=session_id,
    )

    # Refresh + re-navigate to force the codec replay path (parity
    # with the connector-session test even though we expect no
    # visibility tagging — symmetric flow makes the comparison clean).
    page.reload()
    page.goto(f"{base_url}#chat/sessions/{session_id}")
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )

    expect(page.locator('[data-testid="message"].user').last).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="message"].assistant').last).to_be_visible(timeout=8000)

    # Use the robust ``classList.contains`` evaluate pattern (mirrors
    # L5's pattern at
    # ``tests/browser/test_flow_chat_visibility_distinction.py:245-247``)
    # rather than substring matching, which would false-positive on
    # composite classNames.
    user_bubble = page.locator('[data-testid="message"].user').last
    user_has_operator = user_bubble.evaluate(
        "el => el.classList.contains('msg-operator-only')"
    )
    assert user_has_operator is False, (
        "web-native user bubble unexpectedly carries .msg-operator-only — "
        "storage-edge shim is tagging non-connector sessions"
    )

    assistant_bubble = page.locator('[data-testid="message"].assistant').last
    assistant_has_operator = assistant_bubble.evaluate(
        "el => el.classList.contains('msg-operator-only')"
    )
    assert assistant_has_operator is False, (
        "web-native assistant bubble unexpectedly carries .msg-operator-only — "
        "storage-edge shim is tagging non-connector sessions"
    )

    # Sanity: no operator-only labels anywhere in the message log.
    expect(page.locator(".msg-operator-only-label")).to_have_count(0)
