"""Message serialization — encode/decode Message dataclasses to/from JSON."""

from __future__ import annotations

import json
from typing import Any

from the_one.llm.base import Message, Role, TokenUsage, ToolCall, ToolResult

# M08 F6 L02: shared projection-time truncation for tool_result.content.
# Applied at every consumer that surfaces tool content to a client (live
# WS broadcast in app._broadcast_one + app._process_and_broadcast, HTTP API
# result_messages, replay via messages_to_ui_events). DB persistence stays
# full-fidelity — encode_messages / decode_messages do NOT truncate.
MAX_TOOL_RESULT_INLINE_CONTENT = 4000


def truncate_for_event(content: str) -> str:
    """Cap tool_result.content for projection to clients.

    Single source of truth for the projection-time truncation contract.
    DB persistence is unaffected — truncation is a "what we hand to
    clients" concern, not a "what we keep" concern.

    Note: slicing is by code-point (str), not byte. A content with
    multi-codepoint sequences (emoji ZWJ joiners, combining marks) may
    slice mid-sequence at the cap boundary. This matches the prior
    per-site slicing behavior; this helper only aligns the cap.
    """
    return content[:MAX_TOOL_RESULT_INLINE_CONTENT]


def _tool_call_to_dict(tc: ToolCall) -> dict[str, Any]:
    return {"id": tc.id, "name": tc.name, "arguments": tc.arguments}


def _tool_result_to_dict(tr: ToolResult) -> dict[str, Any]:
    d: dict[str, Any] = {
        "tool_call_id": tr.tool_call_id,
        "content": tr.content,
        "is_error": tr.is_error,
    }
    # F5 L3: include `metadata` only when non-None — avoid bloating
    # historical rows with an explicit null key.
    if tr.metadata is not None:
        d["metadata"] = tr.metadata
    return d


def _usage_to_dict(u: TokenUsage) -> dict[str, Any]:
    return {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}


def message_to_dict(msg: Message) -> dict[str, Any]:
    """Serialize a Message dataclass to a plain dict."""
    d: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
    if msg.tool_calls:
        d["tool_calls"] = [_tool_call_to_dict(tc) for tc in msg.tool_calls]
    if msg.tool_result is not None:
        d["tool_result"] = _tool_result_to_dict(msg.tool_result)
    if msg.usage is not None:
        d["usage"] = _usage_to_dict(msg.usage)
    # M10 F03 L02: emit visibility only when non-None. Pre-F3 rows had
    # no visibility key; preserve that shape for back-compat and
    # storage efficiency. Mirrors the tool_result.metadata pattern above.
    if msg.visibility is not None:
        d["visibility"] = msg.visibility
    # M11 F06 L01: emit peer_name only when non-None. Pre-F6 rows had no
    # peer_name key; preserve that shape for back-compat and storage
    # efficiency. Mirrors the visibility pattern above and the
    # tool_result.metadata pattern in _tool_result_to_dict.
    if msg.peer_name is not None:
        d["peer_name"] = msg.peer_name
    return d


def message_from_dict(d: dict[str, Any]) -> Message:
    """Deserialize a plain dict back into a Message dataclass."""
    tool_calls = [
        ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
        for tc in d.get("tool_calls", [])
    ]
    tool_result = None
    if "tool_result" in d:
        tr = d["tool_result"]
        tool_result = ToolResult(
            tool_call_id=tr["tool_call_id"],
            content=tr["content"],
            is_error=tr.get("is_error", False),
            metadata=tr.get("metadata"),  # F5 L3: None when absent (legacy rows)
        )
    usage = None
    if "usage" in d:
        u = d["usage"]
        usage = TokenUsage(
            input_tokens=u.get("input_tokens", 0),
            output_tokens=u.get("output_tokens", 0),
        )
    return Message(
        role=Role(d["role"]),
        content=d.get("content", ""),
        tool_calls=tool_calls,
        tool_result=tool_result,
        usage=usage,
        # M10 F03 L02: visibility — None on legacy rows without the key.
        visibility=d.get("visibility"),
        # M11 F06 L01: peer_name — None on pre-F6 rows without the key.
        peer_name=d.get("peer_name"),
    )


def encode_messages(messages: list[Message]) -> str:
    """Serialize a list of Messages to a JSON string."""
    return json.dumps([message_to_dict(m) for m in messages])


def decode_messages(data: str) -> list[Message]:
    """Deserialize a JSON string back into a list of Messages."""
    return [message_from_dict(d) for d in json.loads(data)]


def messages_to_ui_events(
    messages: list[Message],
    *,
    index_offset: int = 0,
) -> list[dict[str, Any]]:
    """Convert stored Messages to UI event format for session replay.

    F5 L02: every ``tool_call`` and ``tool_result`` event carries a
    paired ``parent_message_id`` + ``tool_call_id`` discriminator.
    ``parent_message_id`` is derived structurally from the index of
    the most recent preceding ``Role.ASSISTANT`` message with
    ``tool_calls`` — matching the projection rule on the live
    broadcast side (``app.py: _broadcast_one`` +
    ``_process_and_broadcast``). The frontend (L03) groups events by
    ``parent_message_id`` into per-turn trace shells.

    Replay-side ids use the namespace prefix ``"replay-msg-N"`` (the
    codec is pure dataclass→dict and has no access to ``session.id``);
    live-broadcast ids use ``f"{session.id}-msg-N"``. The namespaces
    are disjoint by construction so the frontend's opaque-key grouping
    cannot falsely merge live and replay events when both exist in a
    single ``session.history`` (this happens after ``_restore_session``
    rebinds history to replay events on join, then subsequent live
    ``add_event`` calls append live-shaped events). If a future
    refactor changes the live-side id format (e.g. switches to a
    turn-counter), this codec MUST be updated symmetrically — they
    are coupled by the grouping contract, even though the strings
    need not be identical.

    F5 L3: ``tool_result.metadata`` is intentionally NOT projected here.
    Pause state is in-memory only; replay shows historical
    ``auth_required`` tool_msgs as informational text without the
    Login-required affordance. See ``Agent`` class docstring. The L02
    discriminator preserves this carve-out — only the discriminator
    fields are added; ``metadata`` is still dropped.

    F5 L6: ``index_offset`` (keyword-only, default 0) shifts the
    ``enumerate(messages)`` index used to build ``parent_message_id``
    so the dispatcher can project a POST-STEP SLICE
    (``agent.messages[pre_step_len:]``) and still get
    ``parent_message_id`` values unique within the session's lifetime.
    Without this, two consecutive inbound turns whose slice starts at
    index 0 with an assistant-with-tool_calls would both emit
    ``replay-msg-0`` and the frontend's opaque-key grouping would
    bucket the second turn's tool_call/tool_result events into the
    first turn's trace shell. Callers that pass the full messages
    list (``_restore_session`` / ``_get_or_restore_session``) leave
    ``index_offset`` at the default 0 — byte-identical to pre-L6
    behavior.
    """
    events: list[dict[str, Any]] = []
    current_parent_id: str | None = None
    for relative_i, msg in enumerate(messages):
        i = relative_i + index_offset
        if msg.role == Role.SYSTEM:
            continue
        # M10 F03 L02: visibility tag flows into every event derived from
        # this message. Absent key when source visibility is None — frontends
        # treat absent === platform-visible.
        vis = {"visibility": msg.visibility} if msg.visibility is not None else {}
        # M11 F06 L02: peer_name flows ONLY into Role.USER events (peer_name
        # is meaningful only on user-role messages — assistant/tool messages
        # leave the field at its default None by construction). Absent key
        # when source peer_name is None — frontends treat absent === no peer
        # attribution (operator-typed or non-connector session).
        peer = {"peer_name": msg.peer_name} if msg.peer_name is not None else {}
        if msg.role == Role.USER:
            events.append(
                {"type": "user", "content": msg.content, "source": "restored", **vis, **peer}
            )
        elif msg.role == Role.ASSISTANT:
            if msg.content:
                events.append({"type": "assistant", "content": msg.content, **vis})
            if msg.tool_calls:
                current_parent_id = f"replay-msg-{i}"
                for tc in msg.tool_calls:
                    events.append(
                        {
                            "type": "tool_call",
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "parent_message_id": current_parent_id,
                            "tool_call_id": tc.id,
                            **vis,
                        }
                    )
        elif msg.role == Role.TOOL:
            if msg.tool_result:
                events.append(
                    {
                        "type": "tool_result",
                        "content": truncate_for_event(msg.tool_result.content),
                        "is_error": msg.tool_result.is_error,
                        "parent_message_id": current_parent_id,
                        "tool_call_id": msg.tool_result.tool_call_id,
                        **vis,
                    }
                )
    return events
