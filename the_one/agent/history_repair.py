"""Keep a message history valid: every tool call has a result (squawk 0353).

A turn cancelled while a tool is running leaves an assistant message whose
``tool_calls`` have no ``Role.TOOL`` result after them, and providers reject
every later request on such a history. ``Agent`` (frozen) cannot repair that
itself, so the web and connector layers call ``repair_unanswered_tool_calls``
where a history is loaded, a turn starts and a cancelled turn is saved.
"""

from __future__ import annotations

from the_one.llm.base import Message, Role, ToolResult

INTERRUPTED_TOOL_RESULT = "The tool call was interrupted before it returned a result."


def repair_unanswered_tool_calls(messages: list[Message]) -> int:
    """Give every unanswered assistant tool call a synthetic error result.

    Works in place on ``messages`` and returns how many results it added. A call
    counts as answered when any ``Role.TOOL`` message in the list carries its id
    (an auth-required placeholder is such a result), so a call is never answered
    twice and a valid list is left alone (idempotent). Each synthetic result goes
    directly after the existing results of its assistant message, in call order.

    Do not call this while an ``Agent`` holds ``_deferred_tool_calls`` for a live
    auth pause: ``resume_after_auth`` is about to answer the deferred calls.
    """
    answered = {
        m.tool_result.tool_call_id
        for m in messages
        if m.role == Role.TOOL and m.tool_result is not None
    }
    added = 0
    i = 0
    while i < len(messages):
        msg = messages[i]
        i += 1
        if msg.role != Role.ASSISTANT or not msg.tool_calls:
            continue
        # Skip past this message's own results (they follow it directly).
        end = i
        while end < len(messages) and messages[end].role == Role.TOOL:
            end += 1
        missing = [tc for tc in msg.tool_calls if tc.id not in answered]
        if not missing:
            i = end
            continue
        synthetic = [
            Message.tool(
                ToolResult(tool_call_id=tc.id, content=INTERRUPTED_TOOL_RESULT, is_error=True)
            )
            for tc in missing
        ]
        messages[end:end] = synthetic
        answered.update(tc.id for tc in missing)
        added += len(synthetic)
        i = end + len(synthetic)
    return added
