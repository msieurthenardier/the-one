"""Post-step visibility tagging for connector-attached sessions.

M10 F05 L03: factored out of ``the_one.connectors._inbound.dispatch_inbound``
so the F5 L4 WS-storage-edge shim can apply the SAME rules when an
operator types into a connector-attached session from the Chat UI.
The rules are identical for both call sites — the only difference
is the entry-point USER message's default visibility, which the
caller sets at construction time BEFORE invoking ``agent.step``.

Tagging rules (preserved verbatim from F4 L4):

- ``Role.USER`` messages at or after ``pre_step_len`` are SKIPPED.
  The peer-inbound dispatcher constructs USER with ``visibility=None``
  (peer-visible); the operator-input WS shim constructs USER with
  ``visibility=OPERATOR_VISIBILITY``. Either way, the post-step
  pass doesn't touch the USER message — its visibility is the
  caller's contract.
- ``Role.TOOL`` whose parent ``tool_call.name == "send_to_platform_channel"``
  AND content starts with ``PLATFORM_SEND_OK_PREFIX`` → ``visibility=None``
  (peer-visible — the platform-send tool already pushed the content
  to peers).
- Everything else → ``OPERATOR_VISIBILITY`` (assistant text +
  intermediate tool calls/results stay operator-only).
- Messages at indices ``< pre_step_len`` (the pre-existing history)
  are NEVER touched.

The hard-coded ``"send_to_platform_channel"`` literal matches the
built-in tool's registered name (F4 L1-2). Promoting to a constant
is deferred — out of scope for this refactor leg.
"""

from __future__ import annotations

from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
from the_one.llm.base import Message, Role


def tag_post_step_visibility(
    messages: list[Message],
    pre_step_len: int,
) -> None:
    """Apply post-step visibility rules to messages appended by ``agent.step``.

    Mutates ``messages`` in place. Returns None. Caller is
    responsible for tagging the entry-point USER message at
    construction time (BEFORE ``agent.step``); this helper does
    not touch it.

    ``pre_step_len`` is the length of ``messages`` BEFORE the
    ``agent.step`` call. The helper iterates ``messages[pre_step_len:]``
    and applies the rules in the module docstring.
    """
    new_msgs = messages[pre_step_len:]
    tool_call_names: dict[str, str] = {}
    for msg in new_msgs:
        if msg.role == Role.ASSISTANT:
            for tc in msg.tool_calls:
                tool_call_names[tc.id] = tc.name
    for msg in new_msgs:
        if msg.role == Role.USER:
            continue
        is_successful_platform_send = (
            msg.role == Role.TOOL
            and msg.tool_result is not None
            and tool_call_names.get(msg.tool_result.tool_call_id)
            == "send_to_platform_channel"
            and msg.content.startswith(PLATFORM_SEND_OK_PREFIX)
        )
        msg.visibility = (
            None if is_successful_platform_send else OPERATOR_VISIBILITY
        )
