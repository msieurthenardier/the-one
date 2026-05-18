"""Unit tests for ``the_one.connectors.visibility.tag_post_step_visibility``.

M10 F05 L03: focused tests for the shared post-step visibility-tagging
helper extracted from the F4 L4 dispatcher inline walk. The dispatcher's
end-to-end tests in ``tests/test_connectors_inbound.py`` (and the e2e
suites) remain the byte-identical regression net for the
dispatcher-integration path; this file exercises the helper at a single
seam with synthetic ``Message`` lists so the rules block has fast,
isolated coverage that leg 4's WS-storage-edge shim can rely on.
"""

from __future__ import annotations

from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
from the_one.connectors.visibility import tag_post_step_visibility
from the_one.llm.base import Message, ToolCall, ToolResult

# ─── Rule coverage ──────────────────────────────────────────────────────


def test_user_messages_keep_default_visibility() -> None:
    """USER messages at or after ``pre_step_len`` are SKIPPED — the helper
    does not touch ``msg.visibility`` for them. The caller's
    construction-time tagging stands.
    """
    user_peer = Message.user("from peer", visibility=None)
    user_operator = Message.user("from operator", visibility=OPERATOR_VISIBILITY)
    messages = [user_peer, user_operator]

    tag_post_step_visibility(messages, pre_step_len=0)

    # USER messages are unchanged — the helper did not overwrite either.
    assert messages[0].visibility is None
    assert messages[1].visibility == OPERATOR_VISIBILITY


def test_assistant_text_gets_operator_visibility() -> None:
    """Assistant text-only message (no tool_calls) → OPERATOR_VISIBILITY.

    Default branch — the assistant reply during a connector turn is
    operator-only in the Chat UI's two-layer rendering.
    """
    assistant = Message.assistant("hello operator")
    messages = [assistant]

    tag_post_step_visibility(messages, pre_step_len=0)

    assert messages[0].visibility == OPERATOR_VISIBILITY


def test_assistant_with_tool_calls_gets_operator_visibility() -> None:
    """Assistant message carrying tool_calls → OPERATOR_VISIBILITY.

    Intermediate tool-issuing assistant messages stay operator-only
    regardless of which tool is being called.
    """
    tc = ToolCall(id="tc-1", name="send_to_platform_channel", arguments={})
    assistant = Message.assistant("", tool_calls=[tc])
    messages = [assistant]

    tag_post_step_visibility(messages, pre_step_len=0)

    assert messages[0].visibility == OPERATOR_VISIBILITY


def test_tool_result_of_non_platform_send_gets_operator_visibility() -> None:
    """TOOL message whose parent tool_call name is NOT
    ``send_to_platform_channel`` → OPERATOR_VISIBILITY.
    """
    tc = ToolCall(id="tc-1", name="read_file", arguments={})
    assistant = Message.assistant("", tool_calls=[tc])
    tool_msg = Message.tool(
        ToolResult(tool_call_id="tc-1", content="file contents")
    )
    messages = [assistant, tool_msg]

    tag_post_step_visibility(messages, pre_step_len=0)

    assert messages[0].visibility == OPERATOR_VISIBILITY
    assert messages[1].visibility == OPERATOR_VISIBILITY


def test_tool_result_of_platform_send_with_success_prefix_gets_none() -> None:
    """TOOL message whose parent tool_call IS ``send_to_platform_channel``
    AND whose content starts with ``PLATFORM_SEND_OK_PREFIX`` →
    ``visibility=None`` (peer-visible — the platform-send tool already
    pushed the content to peers).
    """
    tc = ToolCall(id="tc-1", name="send_to_platform_channel", arguments={})
    assistant = Message.assistant("", tool_calls=[tc])
    tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc-1",
            content=f"{PLATFORM_SEND_OK_PREFIX} hello peer",
        )
    )
    messages = [assistant, tool_msg]

    tag_post_step_visibility(messages, pre_step_len=0)

    # Assistant that requested the call → OPERATOR (default branch).
    assert messages[0].visibility == OPERATOR_VISIBILITY
    # Tool_result for the successful platform-send → None (peer-visible).
    assert messages[1].visibility is None


def test_tool_result_of_platform_send_without_success_prefix_gets_operator() -> None:
    """TOOL message whose parent tool_call IS ``send_to_platform_channel``
    but whose content does NOT start with the success prefix (error case)
    → OPERATOR_VISIBILITY. A failed platform-send doesn't leak to peers
    because it didn't reach them.
    """
    tc = ToolCall(id="tc-1", name="send_to_platform_channel", arguments={})
    assistant = Message.assistant("", tool_calls=[tc])
    tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc-1",
            content="error: rate-limited",
            is_error=True,
        )
    )
    messages = [assistant, tool_msg]

    tag_post_step_visibility(messages, pre_step_len=0)

    assert messages[0].visibility == OPERATOR_VISIBILITY
    assert messages[1].visibility == OPERATOR_VISIBILITY


# ─── Mutation semantics ──────────────────────────────────────────────────


def test_helper_mutates_in_place() -> None:
    """Helper returns None and mutates the caller's list in place.

    Identity of the list object is preserved; visibility attributes are
    overwritten on the same Message instances the caller holds.
    """
    assistant = Message.assistant("reply")
    messages = [assistant]
    list_id = id(messages)
    msg_id = id(messages[0])

    result = tag_post_step_visibility(messages, pre_step_len=0)

    assert result is None
    assert id(messages) == list_id
    assert id(messages[0]) == msg_id
    assert messages[0].visibility == OPERATOR_VISIBILITY


def test_messages_before_pre_step_len_are_untouched() -> None:
    """Messages at indices ``< pre_step_len`` (the pre-existing history)
    MUST NOT have their visibility modified. Seeded with a deliberate
    sentinel value to detect any accidental overwrite.
    """
    sentinel = "sentinel-do-not-touch"
    pre_user = Message.user("old peer message", visibility=sentinel)
    pre_assistant = Message.assistant("old reply", visibility=sentinel)
    new_assistant = Message.assistant("new reply")
    messages = [pre_user, pre_assistant, new_assistant]

    tag_post_step_visibility(messages, pre_step_len=2)

    # Pre-step messages: untouched.
    assert messages[0].visibility == sentinel
    assert messages[1].visibility == sentinel
    # New (post-step) assistant message: tagged operator.
    assert messages[2].visibility == OPERATOR_VISIBILITY
