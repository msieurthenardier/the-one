"""Behavioral constants and tool-call parsing for the agent loop."""

from __future__ import annotations

import json
import re
import uuid

from the_one.llm.base import ToolCall

# Direct-action patterns: map user intent to tool calls without LLM interpretation.
# Needed because small models often reach for shell instead of the right tool.
DIRECT_ACTIONS: list[tuple[re.Pattern[str], str, dict]] = [
    (
        re.compile(
            r"^(please\s+)?(restart|reboot|reload)\s+"
            r"(yourself|the agent|the container|the app)",
            re.I,
        ),
        "restart",
        {},
    ),
    (re.compile(r"^(please\s+)?(roll\s*back|undo\s+deploy)", re.I), "rollback", {}),
]

# The agent can call this to keep its turn. It's a signal, not a real tool.
CONTINUE_SCHEMA = {
    "name": "continue",
    "description": (
        "Call this when you're not done yet — you have more steps to take "
        "but need another turn to think or act. If you don't call this or "
        "any other tool, your turn ends and the user sees your response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Brief note to yourself about what you're doing next.",
            },
        },
        "required": [],
    },
}


def extract_tool_calls(text: str, valid_names: set[str]) -> list[ToolCall]:
    """Extract tool calls from JSON embedded in assistant text.

    Looks for patterns like:
      {"name": "tool_name", "arguments": {...}}
      {"name": "tool_name", "arguments": "string_arg"}
    Only extracts calls for tools that actually exist in the registry.
    """
    calls: list[ToolCall] = []
    # Match JSON objects that have "name" and "arguments" keys
    for match in re.finditer(r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:[^}]+\}', text):
        try:
            obj = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        name = obj.get("name", "")
        args = obj.get("arguments", {})
        if name not in valid_names:
            continue
        if isinstance(args, str):
            args = {"args": args}
        if not isinstance(args, dict):
            continue
        calls.append(ToolCall(
            id=f"extracted-{uuid.uuid4().hex[:8]}",
            name=name,
            arguments=args,
        ))
    return calls


def match_direct_action(user_input: str) -> tuple[str, dict] | None:
    """Match user input against direct-action patterns."""
    text = user_input.strip()
    for pattern, tool_name, kwargs in DIRECT_ACTIONS:
        if pattern.search(text):
            return tool_name, kwargs
    return None
