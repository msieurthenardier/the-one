"""Message serialization — encode/decode Message dataclasses to/from JSON."""

from __future__ import annotations

import json
from typing import Any

from the_one.llm.base import Message, Role, TokenUsage, ToolCall, ToolResult


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
    )


def encode_messages(messages: list[Message]) -> str:
    """Serialize a list of Messages to a JSON string."""
    return json.dumps([message_to_dict(m) for m in messages])


def decode_messages(data: str) -> list[Message]:
    """Deserialize a JSON string back into a list of Messages."""
    return [message_from_dict(d) for d in json.loads(data)]


def messages_to_ui_events(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert stored Messages to UI event format for session replay.

    F5 L3: ``tool_result.metadata`` is intentionally NOT projected here.
    Pause state is in-memory only; replay shows historical
    ``auth_required`` tool_msgs as informational text without the
    Login-required affordance. See ``Agent`` class docstring.
    """
    events: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == Role.SYSTEM:
            continue
        elif msg.role == Role.USER:
            events.append({"type": "user", "content": msg.content, "source": "restored"})
        elif msg.role == Role.ASSISTANT:
            if msg.content:
                events.append({"type": "assistant", "content": msg.content})
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    events.append({"type": "tool_call", "name": tc.name, "arguments": tc.arguments})
        elif msg.role == Role.TOOL:
            if msg.tool_result:
                events.append(
                    {
                        "type": "tool_result",
                        "content": msg.tool_result.content,
                        "is_error": msg.tool_result.is_error,
                    }
                )
    return events
