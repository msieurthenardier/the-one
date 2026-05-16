"""M08 F6 L02 — cross-projection-site truncation alignment for tool_result.content.

Pins the invariant that a SINGLE ``ToolResult.content`` value > the shared
``MAX_TOOL_RESULT_INLINE_CONTENT`` cap produces an identical truncated
``content`` string across all three projection consumers:

  (a) the WS-broadcast ``tool_result`` event emitted by
      ``_process_and_broadcast`` (the line-858 site in ``app.py``,
      live broadcast),
  (b) the HTTP-API ``result_messages`` entry returned by
      ``_process_and_broadcast`` (the line-868 site in ``app.py``),
  (c) the replay projection produced by
      ``the_one.db.codec.messages_to_ui_events`` (the line-144 site).

Pre-L02 the three sites diverged (2000 / 2000 / 4000 / untruncated).
Post-L02 they share ``truncate_for_event`` from ``the_one.db.codec``.
This integration-style test guards against future per-site drift by
exercising the FULL ``_process_and_broadcast`` path (not isolated
projector calls) so that any rewiring inside that function which
bypasses the helper would be caught.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

from the_one.db.codec import (
    MAX_TOOL_RESULT_INLINE_CONTENT,
    messages_to_ui_events,
)
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import Session, _process_and_broadcast
from the_one.llm.base import Message, ToolCall, ToolResult


class _LLMShim:
    max_context_tokens = 128_000


class _StubAgent:
    """Minimal stub Agent — yields a scripted assistant + tool_result pair.

    Mirrors the ``StubAgent`` pattern in
    ``tests/test_app_websocket_pause_resume.py`` but trimmed to the
    fields actually consumed by ``_process_and_broadcast``.
    """

    def __init__(self, step_messages: list[Message]) -> None:
        self._step_messages = step_messages
        self.messages: list[Message] = []
        self._deferred_tool_calls = None
        self.llm = _LLMShim()

    async def step(
        self,
        user_input: str,  # noqa: ARG002
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002 — F7 L04: widened signature
    ) -> AsyncIterator[Message]:
        for m in self._step_messages:
            yield m


async def test_tool_result_content_truncated_identically_across_projection_sites(
    monkeypatch,
) -> None:
    """A single >cap tool_result.content yields identical truncated strings on
    (WS broadcast, HTTP API result_messages, codec replay projection)."""
    # Stub external side effects ``_process_and_broadcast`` triggers.
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))

    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    over_cap_len = MAX_TOOL_RESULT_INLINE_CONTENT + 1000
    raw_content = "x" * over_cap_len

    pre_assistant = Message.assistant(
        "",
        tool_calls=[ToolCall(id="tc-align", name="some_tool", arguments={})],
    )
    tool_msg = Message.tool(ToolResult(tool_call_id="tc-align", content=raw_content))
    agent = _StubAgent(step_messages=[pre_assistant, tool_msg])
    session = Session(
        id="cs-truncation",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-14T00:00:00+00:00",
    )

    # Site (a) + (b): WS-broadcast event + HTTP-API result_messages
    result_messages = await _process_and_broadcast(session, "drive")

    ws_tool_results = [p for p in captured if p.get("type") == "tool_result"]
    assert len(ws_tool_results) == 1, (
        f"expected exactly one broadcast tool_result event; got {len(ws_tool_results)}"
    )
    ws_content = ws_tool_results[0]["content"]

    api_tool_entries = [m for m in result_messages if m.get("role") == "tool"]
    assert len(api_tool_entries) == 1, (
        f"expected exactly one HTTP-API tool entry; got {len(api_tool_entries)}"
    )
    api_content = api_tool_entries[0]["content"]

    # Site (c): codec replay projection on the equivalent Message
    replay_events = messages_to_ui_events([tool_msg])
    replay_tool_results = [e for e in replay_events if e["type"] == "tool_result"]
    assert len(replay_tool_results) == 1
    replay_content = replay_tool_results[0]["content"]

    # Alignment: all three projection sites emit the SAME string
    assert ws_content == api_content == replay_content, (
        "tool_result.content projections diverged across WS / HTTP-API / replay "
        f"(ws_len={len(ws_content)}, api_len={len(api_content)}, "
        f"replay_len={len(replay_content)})"
    )

    # Cap: all three are exactly MAX_TOOL_RESULT_INLINE_CONTENT long
    assert len(ws_content) == MAX_TOOL_RESULT_INLINE_CONTENT
    assert len(api_content) == MAX_TOOL_RESULT_INLINE_CONTENT
    assert len(replay_content) == MAX_TOOL_RESULT_INLINE_CONTENT

    # And byte-equal to the canonical truncated form
    assert ws_content == "x" * MAX_TOOL_RESULT_INLINE_CONTENT
