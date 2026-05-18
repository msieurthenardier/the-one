"""Browser test for M10 F05 L05 — chat-ui-render-visibility-distinction.

Verifies that messages persisted with ``Message.visibility == "operator"``
render with the ``msg-operator-only`` class and an inline
``[operator-only]`` label, while peer-visible messages render without
either.

Test strategy:
- Spawn a fresh app subprocess (custom fixture exposes the data_dir so
  we can seed a chat_sessions row directly into the SQLite DB).
- Seed a provider + agent via the existing API seeders.
- Programmatically build a mixed-visibility ``messages`` blob via the
  codec's ``encode_messages`` (no hand-crafted JSON) and INSERT a
  chat_sessions row carrying those messages.
- Boot the page, navigate to the seeded session via WS join, wait for
  rendering, assert DOM shape via Playwright ``locator``/``evaluate``.

Per user-global rule (no committed snapshot baselines), this test
uses DOM-shape assertions only.

Known limitation acknowledged by F05 L05 design: live-broadcast
``assistant_chunk`` / ``assistant`` / ``user`` / ``tool_*`` events
do not yet carry the ``visibility`` key (the storage-edge shim runs
AFTER ``agent.step`` completes; live broadcasts emit inline within
the step). The render-side channel is wired and forwards
``data.visibility`` regardless — when a follow-on leg lands
live-broadcast tagging the marker will appear in real time. This
test exercises the replay path (which the codec already tags
correctly via ``messages_to_ui_events`` at
``the_one/db/codec.py:154``).
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
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

from the_one.connectors import OPERATOR_VISIBILITY
from the_one.db.codec import encode_messages
from the_one.llm.base import Message, ToolResult


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

    The conftest ``app_clean`` fixture hides ``data_dir`` inside its body,
    but this test needs the path to seed a chat_sessions row directly via
    SQLite. Mirrors ``app_clean``'s spawn logic; teardown is identical.
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


def _seed_session_with_messages(
    data_dir: Path,
    *,
    session_id: str,
    agent_name: str,
    messages_json: str,
) -> None:
    """INSERT a chat_sessions row directly via sqlite3.

    Uses a synchronous sqlite3 connection (not the app's aiosqlite layer)
    because this runs in the test runner process; the subprocess opens
    the DB lazily and reads it through the WS join path. SQLite's
    file-locking handles the read-after-write across processes.
    """
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            (session_id, agent_name, "operator visibility test", messages_json),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.browser
def test_chat_renders_operator_visibility_distinction(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """A seeded session with mixed visibility renders the operator marker.

    Acceptance criteria coverage:
    - ``.msg-operator-only`` count >= 2 (USER + ASSISTANT, both tagged).
    - ``.msg-operator-only-label`` count >= 2 with text ``[operator-only]``.
    - The TOOL bubble (visibility=None) lacks the operator-only class.
    """
    base_url, data_dir = app_with_data_dir

    # Seed provider + agent via API (same path as app_with_agent fixture).
    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)

    # Build a mixed-visibility messages blob via Message + the codec —
    # never hand-craft the JSON.
    msgs = [
        Message.system("you are a test agent"),
        Message.user("hello bot", visibility=OPERATOR_VISIBILITY),
        Message.assistant("hi operator", visibility=OPERATOR_VISIBILITY),
        # Peer-visible TOOL for the assertion contrast — visibility=None means
        # the codec omits the ``visibility`` key, which the JS treats as
        # platform-visible (no marker, byte-identical render).
        Message.tool(
            ToolResult(tool_call_id="tc1", content="tool output", is_error=False),
            visibility=None,
        ),
    ]
    encoded = encode_messages(msgs)

    session_id = str(uuid.uuid4())
    _seed_session_with_messages(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        messages_json=encoded,
    )

    # Deep-link to the seeded session. The hash route triggers a WS join
    # which calls _restore_session → messages_to_ui_events → renderHistory.
    page.goto(f"{base_url}#chat/sessions/{session_id}")

    # Wait for the chat chrome (deep-link path renders straight into chrome).
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=8000
    )

    # Wait for messages to actually render — at least one .msg bubble.
    expect(page.locator(".msg").first).to_be_visible(timeout=5000)

    # Assertion 1: at least 1 operator-only bubble (the ASSISTANT).
    # M10 F05 L08 HAT: the marker (class + label) is suppressed on
    # .msg.user bubbles — the operator knows what they typed, so the
    # marker is noise on their own messages. The marker still applies
    # to assistant + tool bubbles.
    operator_only = page.locator(".msg-operator-only")
    operator_count = operator_only.count()
    assert operator_count >= 1, (
        f"expected >= 1 .msg-operator-only bubble (assistant), got {operator_count}"
    )

    # Assertion 1b: the user bubble does NOT carry the marker — it
    # has visibility=operator persisted (verified via data-visibility)
    # but the JS suppresses the class + label per the L8 HAT decision.
    user_bubble = page.locator(".msg.user").first
    user_has_class = user_bubble.evaluate(
        "el => el.classList.contains('msg-operator-only')"
    )
    assert user_has_class is False, (
        "user bubble unexpectedly carries .msg-operator-only — the "
        "F5 L8 HAT decision suppresses the marker on the operator's "
        "own user bubbles."
    )
    user_dataset = user_bubble.evaluate("el => el.dataset.visibility")
    assert user_dataset == "operator", (
        f"user bubble's data-visibility should still be 'operator' "
        f"(visibility tag persisted), got {user_dataset!r}"
    )

    # Assertion 2: matching label spans with pinned text content.
    labels = page.locator(".msg-operator-only-label")
    label_count = labels.count()
    assert label_count >= 1, (
        f"expected >= 1 .msg-operator-only-label span (on assistant), "
        f"got {label_count}"
    )
    assert labels.first.text_content() == "[operator-only]"

    # Assertion 3: tool bubble does NOT carry the operator-only class.
    # The codec emits tool_result events with the persisted visibility tag;
    # this tool message has visibility=None so its class set lacks the marker.
    tool_bubble = page.locator(".msg.tool").first
    expect(tool_bubble).to_be_visible(timeout=2000)
    has_operator_class = tool_bubble.evaluate(
        "el => el.classList.contains('msg-operator-only')"
    )
    assert has_operator_class is False, (
        ".msg.tool unexpectedly carries .msg-operator-only — codec or render "
        "path is leaking visibility=None as operator"
    )

    # Sanity: the operator-only bubbles also carry the data-visibility hook
    # (stashed by renderMessage when opts.visibility is truthy).
    has_dataset = operator_only.first.evaluate("el => el.dataset.visibility")
    assert has_dataset == "operator", (
        f"expected data-visibility='operator', got {has_dataset!r}"
    )
