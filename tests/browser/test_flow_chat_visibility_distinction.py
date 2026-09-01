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

import sqlite3
import uuid
from pathlib import Path

import pytest
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import OPERATOR_VISIBILITY, Message, ToolCall, ToolResult

# `app_with_data_dir` (Mission 20 / Flight 1 / Leg 3): formerly a local
# fixture duplicated verbatim across 8 `test_flow_*.py` files, now
# consolidated onto the shared `_spawn_app` path in `browser/conftest.py`
# — pytest auto-discovers it from the directory conftest, no import needed.


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


def _seed_connector_session_with_messages(
    data_dir: Path,
    *,
    session_id: str,
    agent_name: str,
    messages_json: str,
) -> None:
    """Like ``_seed_session_with_messages`` but also sets ``platform`` —
    the column ``Session.platform`` restores from (``_restore_session`` /
    ``_get_or_restore_session``), which the M23 F02 L03 promoted-tool-
    result fix gates on. A row seeded via ``_seed_session_with_messages``
    (platform left NULL) is a web-native session as far as the fix is
    concerned, even though its messages carry connector-shaped fields —
    this helper is the connector-attached counterpart.
    """
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at, platform"
            ") VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?)",
            (session_id, agent_name, "connector tool-result promotion test", messages_json, "stub"),
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
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)

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
    user_has_class = user_bubble.evaluate("el => el.classList.contains('msg-operator-only')")
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
        f"expected >= 1 .msg-operator-only-label span (on assistant), got {label_count}"
    )
    assert labels.first.text_content() == "[operator-only]"

    # Assertion 3: tool bubble does NOT carry the operator-only class.
    # The codec emits tool_result events with the persisted visibility tag;
    # this tool message has visibility=None so its class set lacks the marker.
    tool_bubble = page.locator(".msg.tool").first
    expect(tool_bubble).to_be_visible(timeout=2000)
    has_operator_class = tool_bubble.evaluate("el => el.classList.contains('msg-operator-only')")
    assert has_operator_class is False, (
        ".msg.tool unexpectedly carries .msg-operator-only — codec or render "
        "path is leaking visibility=None as operator"
    )

    # Sanity: the operator-only bubbles also carry the data-visibility hook
    # (stashed by renderMessage when opts.visibility is truthy).
    has_dataset = operator_only.first.evaluate("el => el.dataset.visibility")
    assert has_dataset == "operator", f"expected data-visibility='operator', got {has_dataset!r}"


@pytest.mark.browser
def test_chat_promotes_delivered_tool_result_out_of_accordion(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """M23 F02 L03 (behavior-test fix #2): on a connector-attached session,
    a PEER-VISIBLE tool result (e.g. a successful ``send_to_platform_channel``
    call) renders as a top-level bubble outside the "Tool activity"
    accordion, while an OPERATOR-ONLY tool result stays collapsed inside it.

    Regression test for behavior-test run 2026-08-31-21-37-14 checkpoint 7:
    the `[platform-send-ok]` result was correctly tagged peer-visible but
    imperceivable — buried in a collapsed accordion with no default-visible
    cue.

    Seeds two assistant/tool-call/tool-result turns on a connector-attached
    (``platform="stub"``) session:
    - turn 1: an internal, OPERATOR-ONLY tool call + result — stays fully
      collapsed inside its trace shell (2 items).
    - turn 2: a ``send_to_platform_channel`` tool call (operator-only, like
      every tool CALL) whose RESULT is peer-visible (``visibility=None``,
      the successful-send tag) — the call stays in its trace shell (1 item,
      the result is NOT there); the result renders as a standalone
      top-level bubble, visible without expanding anything.
    """
    base_url, data_dir = app_with_data_dir

    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)

    msgs = [
        Message.system("you are a test agent"),
        Message.user("please send it", peer_name="peer-1"),
        # Turn 1: an internal tool call + result — both operator-only.
        Message.assistant(
            "",
            tool_calls=[ToolCall(id="tc-internal", name="some_internal_tool", arguments={})],
            visibility=OPERATOR_VISIBILITY,
        ),
        Message.tool(
            ToolResult(tool_call_id="tc-internal", content="internal result", is_error=False),
            visibility=OPERATOR_VISIBILITY,
        ),
        # Turn 2: the platform-send call (operator-only) whose result is
        # peer-visible (visibility=None) — the delivered content.
        Message.assistant(
            "",
            tool_calls=[
                ToolCall(
                    id="tc-send",
                    name="send_to_platform_channel",
                    arguments={
                        "target": {"connector_id": "conn-1", "peer_id": "peer-1"},
                        "content": "ping",
                    },
                )
            ],
            visibility=OPERATOR_VISIBILITY,
        ),
        Message.tool(
            ToolResult(
                tool_call_id="tc-send",
                content="[platform-send-ok] sent to conn-1 DM peer-1: 'ping' (msg_id=1)",
                is_error=False,
            ),
            visibility=None,
        ),
    ]
    encoded = encode_messages(msgs)

    session_id = str(uuid.uuid4())
    _seed_connector_session_with_messages(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        messages_json=encoded,
    )

    page.goto(f"{base_url}#chat/sessions/{session_id}")
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)
    expect(page.locator(".msg").first).to_be_visible(timeout=5000)

    # Both tool calls always route through a trace shell (they're never the
    # successful-send exception themselves) — two turns, two shells.
    trace_shells = page.locator('[data-testid="trace-shell"]')
    expect(trace_shells).to_have_count(2, timeout=5000)

    # Turn 1's shell: both the call and its result stayed collapsed inside.
    first_body_count = trace_shells.nth(0).locator(".trace-body .msg").count()
    assert first_body_count == 2, (
        f"expected turn 1's trace shell to hold 2 collapsed items (call + "
        f"operator-only result), got {first_body_count}"
    )

    # Turn 2's shell: only the call — the delivered result was diverted out.
    second_body_count = trace_shells.nth(1).locator(".trace-body .msg").count()
    assert second_body_count == 1, (
        f"expected turn 2's trace shell to hold only the tool CALL (1 item) "
        f"— the peer-visible result must not collapse into it, got {second_body_count}"
    )
    trace2_text = trace_shells.nth(1).locator(".trace-body").text_content()
    assert "platform-send-ok" not in (trace2_text or ""), (
        "the delivered tool result leaked into the collapsed accordion "
        "instead of being promoted to a top-level bubble"
    )

    # The delivered result is a DIRECT CHILD of .messages (top-level,
    # sibling to the trace shells and other bubbles) — not nested inside
    # any trace shell — and visible without expanding anything.
    delivered = page.locator(".messages > .msg.tool")
    expect(delivered).to_have_count(1, timeout=5000)
    expect(delivered).to_be_visible()
    delivered_text = delivered.text_content() or ""
    assert delivered_text.startswith("[platform-send-ok]"), (
        f"expected the promoted bubble's text to start with the delivered "
        f"prefix, got {delivered_text!r}"
    )
    has_operator_class = delivered.evaluate("el => el.classList.contains('msg-operator-only')")
    assert has_operator_class is False, (
        "the promoted (peer-visible) tool result must not carry "
        ".msg-operator-only"
    )

    # It gets an attribution row like a delivered message, per the fix's
    # "rendered like a delivered message" requirement.
    delivered_attribution = delivered.evaluate(
        "el => { const n = el.nextElementSibling; "
        "return n ? { cls: n.className, text: n.textContent } : null; }"
    )
    assert delivered_attribution is not None, (
        "the promoted tool result should be followed by an attribution "
        "row, like an ordinary assistant reply"
    )
    assert "from-agent" in delivered_attribution["cls"], (
        f"expected the attribution row to use the 'from-agent' side, "
        f"got cls={delivered_attribution['cls']!r}"
    )
