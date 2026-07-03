"""Message serialization — encode/decode Message dataclasses to/from JSON."""

from __future__ import annotations

import json
from typing import Any

from the_one.db.models import PendingApproval
from the_one.llm.base import (
    Message,
    Role,
    ThinkingBlock,
    TokenUsage,
    ToolCall,
    ToolResult,
)

# M08 F6 L02: shared projection-time truncation for tool_result.content.
# Applied at every consumer that surfaces tool content to a client (live
# WS broadcast in app._broadcast_one + app._process_and_broadcast, HTTP API
# result_messages, replay via messages_to_ui_events). DB persistence stays
# full-fidelity — encode_messages / decode_messages do NOT truncate.
MAX_TOOL_RESULT_INLINE_CONTENT = 4000


def truncate_for_event(content: Any) -> str:
    """Cap tool_result.content for projection to clients.

    Single source of truth for the projection-time truncation contract.
    DB persistence is unaffected — truncation is a "what we hand to
    clients" concern, not a "what we keep" concern.

    Non-string content (e.g. structured dicts/lists returned by L10
    channel-context tools) is JSON-stringified before truncation.
    Mirrors 12.l: the agent serializer normalizes for the LLM, this
    normalizes for telemetry/event projection. ToolResult.content is
    annotated `str` but not runtime-enforced, so tools occasionally
    hand us dicts; coerce here rather than crash the projection path.

    Note: slicing is by code-point (str), not byte. A content with
    multi-codepoint sequences (emoji ZWJ joiners, combining marks) may
    slice mid-sequence at the cap boundary. This matches the prior
    per-site slicing behavior; this helper only aligns the cap.

    M11 F8 L2 update — post-L2 reachability: this defensive branch is
    no longer reached by normal flow because ``ToolResult.__post_init__``
    JSON-normalizes non-str content at construction. The branch remains
    as belt-and-suspenders that defends the projection path if the L2
    invariant ever loosens or a caller passes a non-``ToolResult.content``
    value directly. See ``the_one/agents.md`` → ``provider-shape-portability``.
    """
    if not isinstance(content, str):
        content = json.dumps(content)
    return content[:MAX_TOOL_RESULT_INLINE_CONTENT]


def _tool_call_to_dict(tc: ToolCall) -> dict[str, Any]:
    return {"id": tc.id, "name": tc.name, "arguments": tc.arguments}


def _thinking_block_to_dict(tb: ThinkingBlock) -> dict[str, Any]:
    # Two-level guard (do NOT "harmonize"): the FIELD-level emit in
    # message_to_dict uses a TRUTHY guard (`if msg.thinking:`) to keep the
    # byte-identity tripwire green (empty list → no key). The SUB-KEY guards
    # here use `is not None` so a legitimately-empty-but-present value (e.g. an
    # empty-string signature) round-trips verbatim and the stored dict equals
    # the Anthropic content-block shape for Leg 03 replay. Flattening either
    # guard breaks one of those two invariants.
    d: dict[str, Any] = {"type": tb.type}
    if tb.thinking is not None:
        d["thinking"] = tb.thinking
    if tb.signature is not None:
        d["signature"] = tb.signature
    if tb.data is not None:
        d["data"] = tb.data
    return d


def _thinking_block_from_dict(d: dict[str, Any]) -> ThinkingBlock:
    return ThinkingBlock(
        type=d["type"],
        thinking=d.get("thinking"),
        signature=d.get("signature"),
        data=d.get("data"),
    )


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
    # M16 F10 L01 (DD1): emit thinking with a TRUTHY guard — a structural
    # sibling of tool_calls above, NOT the is-not-None optionals below. An
    # empty list emits no key, so the byte-identity tripwire stays green and
    # legacy rows decode unchanged. Deliberately outside the
    # emit-when-non-none convention (see the Message.thinking field comment).
    if msg.thinking:
        d["thinking"] = [_thinking_block_to_dict(tb) for tb in msg.thinking]
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
    # M11 F07 L02: emit channel_id only when non-None. Pre-F7 rows had
    # no channel_id key; preserve byte-identical legacy shape. Mirrors
    # the peer_name pattern above.
    if msg.channel_id is not None:
        d["channel_id"] = msg.channel_id
    # M11 F07 L02: emit channel_name only when non-None. Same back-compat
    # discipline as channel_id above; the pair travels together but each
    # independently emits only when set (cold-pool case: id resolved but
    # name not yet cached).
    if msg.channel_name is not None:
        d["channel_name"] = msg.channel_name
    return d


def message_from_dict(d: dict[str, Any]) -> Message:
    """Deserialize a plain dict back into a Message dataclass."""
    tool_calls = [
        ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
        for tc in d.get("tool_calls", [])
    ]
    # M16 F10 L01 (DD1): reconstruct thinking blocks; legacy rows have no
    # "thinking" key → empty list (back-compat), mirroring tool_calls above.
    thinking = [_thinking_block_from_dict(tb) for tb in d.get("thinking", [])]
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
        thinking=thinking,
        tool_result=tool_result,
        usage=usage,
        # M10 F03 L02: visibility — None on legacy rows without the key.
        visibility=d.get("visibility"),
        # M11 F06 L01: peer_name — None on pre-F6 rows without the key.
        peer_name=d.get("peer_name"),
        # M11 F07 L02: channel_id — None on pre-F7 rows without the key.
        channel_id=d.get("channel_id"),
        # M11 F07 L02: channel_name — None on pre-F7 rows without the key.
        channel_name=d.get("channel_name"),
    )


def encode_messages(messages: list[Message]) -> str:
    """Serialize a list of Messages to a JSON string."""
    return json.dumps([message_to_dict(m) for m in messages])


def decode_messages(data: str) -> list[Message]:
    """Deserialize a JSON string back into a list of Messages."""
    return [message_from_dict(d) for d in json.loads(data)]


def thinking_display_text(blocks: list[ThinkingBlock]) -> str:
    """Human-readable reasoning for the UI. Concatenates ``type=="thinking"``
    text; a redacted-only turn yields a marker; no thinking yields ``""``.
    Signatures/data never reach the client.

    M16 F10 L05: single source of truth for the ``thinking`` event's display
    text, used by BOTH the codec replay projection (``messages_to_ui_events``)
    and the live broadcast (``app._process_and_broadcast``).
    """
    texts = [tb.thinking for tb in blocks if tb.type == "thinking" and tb.thinking]
    if texts:
        return "\n\n".join(texts)
    if any(tb.type == "redacted_thinking" for tb in blocks):
        return "[reasoning redacted]"
    return ""


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
        # M11 F07 L03: channel_id + channel_name flow ONLY into Role.USER
        # events (same Role-gating as peer_name — channel context is meaningful
        # only on connector-inbound user-role messages; operator-typed turns
        # and assistant/tool messages leave the fields at their dataclass
        # default ``None``). Each spread is independently conditional so a
        # USER message with channel_id but no resolved channel_name still
        # emits ``channel_id`` (the partial-absence path the L4 provider
        # projection must handle gracefully). The single projection site
        # covers BOTH replay (``_restore_session``) AND live broadcast
        # (``_inbound.py:dispatch_inbound`` → ``broadcast_to_session``) for
        # the connector-inbound path; ``app.py:_process_and_broadcast``
        # handles operator-typed input and is NOT touched by this projection.
        channel_id_spread = {"channel_id": msg.channel_id} if msg.channel_id is not None else {}
        channel_name_spread = (
            {"channel_name": msg.channel_name} if msg.channel_name is not None else {}
        )
        if msg.role == Role.USER:
            events.append(
                {
                    "type": "user",
                    "content": msg.content,
                    "source": "restored",
                    **vis,
                    **peer,
                    **channel_id_spread,
                    **channel_name_spread,
                }
            )
        elif msg.role == Role.ASSISTANT:
            if msg.content:
                events.append({"type": "assistant", "content": msg.content, **vis})
            # M16 F10 L05: project captured thinking as a ``thinking`` event —
            # AFTER the assistant-content event, BEFORE the tool_call events —
            # only when there is displayable reasoning text. No-thinking turns
            # emit no event and stay byte-identical to the pre-L05 projection.
            _thinking_text = thinking_display_text(msg.thinking)
            if _thinking_text:
                events.append(
                    {
                        "type": "thinking",
                        "content": _thinking_text,
                        "parent_message_id": f"replay-msg-{i}",
                        **vis,
                    }
                )
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


def pending_approvals_to_ui_events(
    rows: list[PendingApproval],
) -> list[dict[str, Any]]:
    """Convert PendingApproval rows to UI event dicts.

    M11 F9 L4. Used by ``_restore_session`` and
    ``_build_session_joined_degraded`` to merge pending-approval banners
    into the per-session history stream when the session has connector
    context (``connector_id is not None and peer_id is not None``).

    The output event shape is identical to the live-broadcast event the
    dispatcher emits at ``the_one/connectors/_inbound.py`` (F9 L2). The
    two emit sites are independent (this projection runs on restore;
    the dispatcher's hand-built dict runs on inbound); they MUST stay
    in sync or the frontend will see drift between live and replay.
    Verified by browser tests covering both paths.

    L4 deliberately does NOT refactor L2's dispatcher emit to consume
    this projection function — the two emit sites are coupled by their
    event shape but kept independently inlined to avoid re-running L2's
    test surface. A future routine-maintenance pass can consolidate.
    """
    return [
        {
            "type": "pending-approval",
            "approval_id": row.id,
            "peer_name": row.peer_name,
            "peer_id": row.peer_id,
            "preview": row.preview,
            "received_at": row.received_at,
            "connector_id": row.connector_id,
            "status": row.status,
        }
        for row in rows
    ]
