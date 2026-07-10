"""Tests for message codec round-trip serialization."""

from __future__ import annotations

import json

import pytest

from the_one.db.codec import (
    _content_block_from_dict,
    _content_block_to_dict,
    _tool_result_to_dict,
    decode_messages,
    encode_messages,
    message_from_dict,
    message_to_dict,
    messages_to_ui_events,
    thinking_display_text,
)
from the_one.llm.base import (
    ContentBlock,
    ImageContent,
    Message,
    Role,
    TextContent,
    ThinkingBlock,
    TokenUsage,
    ToolCall,
    ToolResult,
)


class TestCodecRoundTrip:
    def test_simple_user_message(self) -> None:
        msgs = [Message.user("hello")]
        result = decode_messages(encode_messages(msgs))
        assert len(result) == 1
        assert result[0].role == Role.USER
        assert result[0].content == "hello"

    def test_assistant_with_content(self) -> None:
        msgs = [Message.assistant("hi there")]
        result = decode_messages(encode_messages(msgs))
        assert result[0].role == Role.ASSISTANT
        assert result[0].content == "hi there"

    def test_assistant_with_tool_calls(self) -> None:
        tc = ToolCall(id="tc-1", name="read_file", arguments={"path": "/tmp/x"})
        msgs = [Message.assistant("", tool_calls=[tc])]
        result = decode_messages(encode_messages(msgs))
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0].id == "tc-1"
        assert result[0].tool_calls[0].name == "read_file"
        assert result[0].tool_calls[0].arguments == {"path": "/tmp/x"}

    def test_tool_result(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="file contents here")
        msgs = [Message.tool(tr)]
        result = decode_messages(encode_messages(msgs))
        assert result[0].role == Role.TOOL
        assert result[0].tool_result is not None
        assert result[0].tool_result.tool_call_id == "tc-1"
        assert result[0].tool_result.content == "file contents here"
        assert result[0].tool_result.is_error is False

    def test_tool_result_error(self) -> None:
        tr = ToolResult(tool_call_id="tc-2", content="boom", is_error=True)
        msgs = [Message.tool(tr)]
        result = decode_messages(encode_messages(msgs))
        assert result[0].tool_result.is_error is True

    def test_token_usage(self) -> None:
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        msgs = [Message.assistant("ok", usage=usage)]
        result = decode_messages(encode_messages(msgs))
        assert result[0].usage is not None
        assert result[0].usage.input_tokens == 100
        assert result[0].usage.output_tokens == 50

    def test_empty_list(self) -> None:
        result = decode_messages(encode_messages([]))
        assert result == []

    def test_complex_tool_arguments(self) -> None:
        tc = ToolCall(
            id="tc-3",
            name="shell",
            arguments={"command": "echo 'hello \"world\"'", "timeout": 30, "nested": {"a": [1, 2]}},
        )
        msgs = [Message.assistant("", tool_calls=[tc])]
        result = decode_messages(encode_messages(msgs))
        assert result[0].tool_calls[0].arguments["nested"] == {"a": [1, 2]}

    def test_multi_message_conversation(self) -> None:
        msgs = [
            Message.system("You are helpful"),
            Message.user("Hi"),
            Message.assistant("Hello!", usage=TokenUsage(input_tokens=10, output_tokens=5)),
            Message.user("Do something"),
            Message.assistant("", tool_calls=[ToolCall(id="t1", name="shell", arguments={})]),
            Message.tool(ToolResult(tool_call_id="t1", content="done")),
            Message.assistant("All done"),
        ]
        result = decode_messages(encode_messages(msgs))
        assert len(result) == 7
        assert result[0].role == Role.SYSTEM
        assert result[4].tool_calls[0].name == "shell"
        assert result[5].tool_result.content == "done"


class TestMessagesToUIEvents:
    def test_skips_system_messages(self) -> None:
        msgs = [Message.system("You are helpful")]
        assert messages_to_ui_events(msgs) == []

    def test_user_message(self) -> None:
        msgs = [Message.user("hello")]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        assert events[0] == {"type": "user", "content": "hello", "source": "restored"}

    def test_user_message_list_content_projects_to_string(self) -> None:
        """M16 F12 L08: an image-bearing USER message (list[ContentBlock])
        MUST project through content_to_text — a raw dataclass list reaching
        the WS ``content`` key would crash ``json.dumps`` (no custom encoder)
        on session join/replay, killing the WS unhandled (see app.py
        ``_send_to_session``).
        """
        msg = Message(
            role=Role.USER,
            content=[
                TextContent(text="what is this?"),
                ImageContent(media_type="image/png", data="abc"),
            ],
        )
        events = messages_to_ui_events([msg])
        assert len(events) == 1
        assert events[0]["content"] == "what is this? [image]"
        assert isinstance(events[0]["content"], str)

    def test_user_message_image_only_list_content_projects_to_string(self) -> None:
        """Image-only (no text) list content also projects to a string —
        the ``[image]`` placeholder, not an empty string or a crash."""
        msg = Message(role=Role.USER, content=[ImageContent(media_type="image/png", data="abc")])
        events = messages_to_ui_events([msg])
        assert events[0]["content"] == "[image]"

    def test_assistant_text(self) -> None:
        msgs = [Message.assistant("hi there")]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        assert events[0] == {"type": "assistant", "content": "hi there"}

    def test_assistant_tool_calls(self) -> None:
        tc1 = ToolCall(id="tc-1", name="read_file", arguments={"path": "/tmp/x"})
        tc2 = ToolCall(id="tc-2", name="shell", arguments={"cmd": "ls"})
        msgs = [Message.assistant("", tool_calls=[tc1, tc2])]
        events = messages_to_ui_events(msgs)
        assert len(events) == 2
        # F5 L02: tool_call events now carry parent_message_id + tool_call_id.
        # Both tool_calls belong to the same assistant turn → same parent_message_id.
        assert events[0] == {
            "type": "tool_call",
            "name": "read_file",
            "arguments": {"path": "/tmp/x"},
            "parent_message_id": "replay-msg-0",
            "tool_call_id": "tc-1",
        }
        assert events[1] == {
            "type": "tool_call",
            "name": "shell",
            "arguments": {"cmd": "ls"},
            "parent_message_id": "replay-msg-0",
            "tool_call_id": "tc-2",
        }

    def test_assistant_with_both_text_and_tool_calls(self) -> None:
        tc = ToolCall(id="tc-1", name="read_file", arguments={"path": "/tmp/x"})
        msgs = [Message.assistant("Let me check that", tool_calls=[tc])]
        events = messages_to_ui_events(msgs)
        assert len(events) == 2
        assert events[0] == {"type": "assistant", "content": "Let me check that"}
        # F5 L02: tool_call carries discriminator
        assert events[1] == {
            "type": "tool_call",
            "name": "read_file",
            "arguments": {"path": "/tmp/x"},
            "parent_message_id": "replay-msg-0",
            "tool_call_id": "tc-1",
        }

    def test_tool_result(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="file contents here")
        msgs = [Message.tool(tr)]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        # F5 L02: tool_result carries discriminator. No preceding assistant
        # turn in this fixture → parent_message_id is None (the "unattributed"
        # edge case documented in the leg artifact).
        assert events[0] == {
            "type": "tool_result",
            "content": "file contents here",
            "is_error": False,
            "parent_message_id": None,
            "tool_call_id": "tc-1",
        }

    def test_tool_result_error(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="boom", is_error=True)
        msgs = [Message.tool(tr)]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        # F5 L02: tool_result carries discriminator
        assert events[0] == {
            "type": "tool_result",
            "content": "boom",
            "is_error": True,
            "parent_message_id": None,
            "tool_call_id": "tc-1",
        }

    def test_empty_list(self) -> None:
        assert messages_to_ui_events([]) == []

    def test_full_conversation(self) -> None:
        msgs = [
            Message.system("You are helpful"),
            Message.user("Hi"),
            Message.assistant("Hello!"),
            Message.user("Read a file"),
            Message.assistant(
                "Sure", tool_calls=[ToolCall(id="t1", name="read_file", arguments={"path": "/x"})]
            ),
            Message.tool(ToolResult(tool_call_id="t1", content="file data")),
            Message.assistant("Here's the file content"),
        ]
        events = messages_to_ui_events(msgs)
        assert len(events) == 7
        # system skipped
        assert events[0] == {"type": "user", "content": "Hi", "source": "restored"}
        assert events[1] == {"type": "assistant", "content": "Hello!"}
        assert events[2] == {"type": "user", "content": "Read a file", "source": "restored"}
        assert events[3] == {"type": "assistant", "content": "Sure"}
        # F5 L02: tool_call + tool_result carry discriminator; index 4 is
        # the assistant w/ tool_calls, so parent_message_id is "replay-msg-4".
        assert events[4] == {
            "type": "tool_call",
            "name": "read_file",
            "arguments": {"path": "/x"},
            "parent_message_id": "replay-msg-4",
            "tool_call_id": "t1",
        }
        assert events[5] == {
            "type": "tool_result",
            "content": "file data",
            "is_error": False,
            "parent_message_id": "replay-msg-4",
            "tool_call_id": "t1",
        }
        assert events[6] == {"type": "assistant", "content": "Here's the file content"}


# ---------------------------------------------------------------------------
# F5 L3 — ToolResult.metadata round-trip
# ---------------------------------------------------------------------------


def test_tool_result_metadata_round_trip() -> None:
    """A2: metadata round-trips through serializer + inline deserializer.

    The serializer (``_tool_result_to_dict``) writes ``metadata`` ONLY
    when non-None; the inline deserializer in ``message_from_dict``
    reads it back via ``.get("metadata")`` (default None).
    """
    metadata = {
        "is_auth_required": True,
        "source_id": "s1",
        "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
        "tool_call_id": "t1",
    }
    tr = ToolResult(tool_call_id="t1", content="auth required", metadata=metadata)

    # Round-trip through the serializer + inline deserializer
    serialized = _tool_result_to_dict(tr)
    assert serialized["metadata"] == metadata

    msg_dict = {"role": "tool", "content": "auth required", "tool_result": serialized}
    msg = message_from_dict(msg_dict)
    assert msg.role == Role.TOOL
    assert msg.tool_result is not None
    assert msg.tool_result.metadata == metadata

    # Also verify full encode/decode round-trip
    msgs = [Message.tool(tr)]
    result = decode_messages(encode_messages(msgs))
    assert result[0].tool_result is not None
    assert result[0].tool_result.metadata == metadata


def test_tool_result_legacy_no_metadata_round_trip() -> None:
    """A2: legacy rows without `metadata` key deserialize with metadata=None.

    The serializer omits ``metadata`` when None to avoid bloating
    historical rows; the deserializer must accept input dicts that
    lack the key entirely (legacy rows pre-L3 + post-L3 success-path
    rows).
    """
    # Construct a legacy-style dict (no `metadata` key)
    legacy_dict = {
        "role": "tool",
        "content": "ok",
        "tool_result": {
            "tool_call_id": "t1",
            "content": "ok",
            "is_error": False,
            # No "metadata" key — represents a pre-L3 stored row.
        },
    }
    msg = message_from_dict(legacy_dict)
    assert msg.tool_result is not None
    assert msg.tool_result.metadata is None

    # Also: a None-metadata ToolResult round-trips with no metadata key
    tr = ToolResult(tool_call_id="t1", content="ok")  # default metadata=None
    serialized = _tool_result_to_dict(tr)
    assert "metadata" not in serialized


# ---------------------------------------------------------------------------
# F5 L02 — parent_message_id + tool_call_id discriminator on projected events
# ---------------------------------------------------------------------------


class TestMessagesToUiEventsDiscriminator:
    """messages_to_ui_events emits a paired parent_message_id + tool_call_id
    discriminator on every tool_call and tool_result event, derived
    structurally from the index of the most recent preceding
    Role.ASSISTANT with tool_calls. Replay-side ids use the
    ``"replay-msg-N"`` namespace (codec has no Session reference).
    """

    def test_single_turn_tool_call_and_result_share_parent_id(self) -> None:
        tc = ToolCall(id="tc-1", name="read_file", arguments={"path": "/tmp/x"})
        tr = ToolResult(tool_call_id="tc-1", content="hi")
        msgs = [
            Message.user("read /tmp/x"),
            Message.assistant("", tool_calls=[tc]),
            Message.tool(tr),
        ]
        events = messages_to_ui_events(msgs)
        tc_events = [e for e in events if e["type"] == "tool_call"]
        tr_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tc_events) == 1
        assert len(tr_events) == 1
        # Both carry the discriminator pair
        assert tc_events[0]["parent_message_id"] is not None
        assert tc_events[0]["tool_call_id"] == "tc-1"
        assert tr_events[0]["parent_message_id"] is not None
        assert tr_events[0]["tool_call_id"] == "tc-1"
        # Same parent_message_id ties the tool_call to its tool_result
        assert tc_events[0]["parent_message_id"] == tr_events[0]["parent_message_id"]
        # Replay namespace prefix
        assert tc_events[0]["parent_message_id"].startswith("replay-msg-")

    def test_multi_turn_groups_distinct_parent_ids_with_cross_wiring(self) -> None:
        """Three assistant turns interleaved with tool results: each
        tool_result groups under ITS OWN turn's tool_call, not another
        turn's. Catches "tool_result-1 grouped with assistant-2" cross-
        wiring bugs that a simple distinct-id check would miss.
        """
        msgs = [
            Message.user("first"),
            Message.assistant("", tool_calls=[ToolCall(id="t1", name="shell", arguments={})]),
            Message.tool(ToolResult(tool_call_id="t1", content="done1")),
            Message.user("second"),
            Message.assistant("", tool_calls=[ToolCall(id="t2", name="shell", arguments={})]),
            Message.tool(ToolResult(tool_call_id="t2", content="done2")),
            Message.user("third"),
            Message.assistant("", tool_calls=[ToolCall(id="t3", name="shell", arguments={})]),
            Message.tool(ToolResult(tool_call_id="t3", content="done3")),
        ]
        events = messages_to_ui_events(msgs)
        tc_events = [e for e in events if e["type"] == "tool_call"]
        tr_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tc_events) == 3
        assert len(tr_events) == 3
        # Distinct parent ids across turns
        parent_ids = {e["parent_message_id"] for e in tc_events}
        assert len(parent_ids) == 3
        # Cross-wiring: each tool_result groups under its OWN turn
        for i in range(3):
            assert tr_events[i]["parent_message_id"] == tc_events[i]["parent_message_id"]
            assert tr_events[i]["tool_call_id"] == f"t{i + 1}"
            assert tc_events[i]["tool_call_id"] == f"t{i + 1}"
        # And the cross-turn pairing is genuinely wrong (sanity check
        # the test's discriminating power): turn-1's tool_result must
        # NOT match turn-2's tool_call parent
        assert tr_events[0]["parent_message_id"] != tc_events[1]["parent_message_id"]


# ---------------------------------------------------------------------------
# M16 F10 L05 — thinking display text + thinking event projection
# ---------------------------------------------------------------------------


class TestThinkingDisplayText:
    """``thinking_display_text`` is the single source of truth for the UI's
    human-readable reasoning string, shared by the codec projection and the
    live broadcast (app.py). Concatenates ``type=="thinking"`` text; a
    redacted-only turn yields a marker; no thinking yields ``""``.
    """

    def test_joins_thinking_blocks_in_order(self) -> None:
        blocks = [
            ThinkingBlock(type="thinking", thinking="first", signature="sig1"),
            ThinkingBlock(type="thinking", thinking="second", signature="sig2"),
        ]
        assert thinking_display_text(blocks) == "first\n\nsecond"

    def test_no_thinking_yields_empty(self) -> None:
        assert thinking_display_text([]) == ""

    def test_thinking_block_with_no_text_is_skipped(self) -> None:
        # A type=="thinking" block whose .thinking is None/"" contributes
        # nothing; with no other text it degrades to "" (not a marker).
        blocks = [ThinkingBlock(type="thinking", thinking=None)]
        assert thinking_display_text(blocks) == ""

    def test_redacted_only_yields_marker(self) -> None:
        blocks = [ThinkingBlock(type="redacted_thinking", data="opaque")]
        assert thinking_display_text(blocks) == "[reasoning redacted]"

    def test_mixed_thinking_and_redacted_prefers_text(self) -> None:
        blocks = [
            ThinkingBlock(type="thinking", thinking="visible reasoning", signature="s"),
            ThinkingBlock(type="redacted_thinking", data="opaque"),
        ]
        assert thinking_display_text(blocks) == "visible reasoning"

    def test_never_leaks_signature_or_data(self) -> None:
        blocks = [ThinkingBlock(type="thinking", thinking="text", signature="SECRET")]
        assert "SECRET" not in thinking_display_text(blocks)


class TestMessagesToUiEventsThinking:
    """``messages_to_ui_events`` projects a ``thinking`` event in the ASSISTANT
    branch — after the assistant-content event, before the tool_call events —
    ONLY when there is displayable reasoning. No-thinking turns are unchanged.
    """

    def test_thinking_event_emitted_with_joined_text(self) -> None:
        msgs = [
            Message.assistant(
                "the answer",
                thinking=[
                    ThinkingBlock(type="thinking", thinking="step one", signature="s1"),
                    ThinkingBlock(type="thinking", thinking="step two", signature="s2"),
                ],
            )
        ]
        events = messages_to_ui_events(msgs)
        assert len(events) == 2
        assert events[0] == {"type": "assistant", "content": "the answer"}
        # Thinking event AFTER the assistant content event, carries parent id.
        assert events[1] == {
            "type": "thinking",
            "content": "step one\n\nstep two",
            "parent_message_id": "replay-msg-0",
        }

    def test_no_thinking_emits_no_thinking_event(self) -> None:
        msgs = [Message.assistant("plain answer")]
        events = messages_to_ui_events(msgs)
        assert events == [{"type": "assistant", "content": "plain answer"}]
        assert not any(e["type"] == "thinking" for e in events)

    def test_redacted_only_projects_marker(self) -> None:
        msgs = [
            Message.assistant(
                "answer",
                thinking=[ThinkingBlock(type="redacted_thinking", data="opaque")],
            )
        ]
        events = messages_to_ui_events(msgs)
        thinking_events = [e for e in events if e["type"] == "thinking"]
        assert len(thinking_events) == 1
        assert thinking_events[0]["content"] == "[reasoning redacted]"

    def test_empty_content_thinking_plus_tool_calls_turn(self) -> None:
        """Criterion #1's core shape: a turn with empty content but thinking +
        a tool call. No assistant-content event fires; the thinking event is
        emitted FIRST, then the tool_call events — ordering preserved.
        """
        tc = ToolCall(id="tc-1", name="read_file", arguments={"path": "/x"})
        msgs = [
            Message.assistant(
                "",
                tool_calls=[tc],
                thinking=[ThinkingBlock(type="thinking", thinking="reason", signature="s")],
            )
        ]
        events = messages_to_ui_events(msgs)
        # No assistant-content event (empty content).
        assert not any(e["type"] == "assistant" for e in events)
        assert len(events) == 2
        assert events[0] == {
            "type": "thinking",
            "content": "reason",
            "parent_message_id": "replay-msg-0",
        }
        assert events[1] == {
            "type": "tool_call",
            "name": "read_file",
            "arguments": {"path": "/x"},
            "parent_message_id": "replay-msg-0",
            "tool_call_id": "tc-1",
        }

    def test_thinking_carries_visibility_on_replay(self) -> None:
        from the_one.connectors import OPERATOR_VISIBILITY

        msg = Message.assistant(
            "answer",
            thinking=[ThinkingBlock(type="thinking", thinking="reason", signature="s")],
        )
        msg.visibility = OPERATOR_VISIBILITY
        events = messages_to_ui_events([msg])
        thinking_events = [e for e in events if e["type"] == "thinking"]
        assert len(thinking_events) == 1
        assert thinking_events[0]["visibility"] == OPERATOR_VISIBILITY

    def test_no_thinking_full_conversation_byte_identical(self) -> None:
        """Regression tripwire: a no-thinking conversation projects exactly as
        it did before L05 — no thinking events, no shape drift.
        """
        msgs = [
            Message.system("You are helpful"),
            Message.user("Hi"),
            Message.assistant("Hello!"),
            Message.assistant(
                "Sure", tool_calls=[ToolCall(id="t1", name="read_file", arguments={"path": "/x"})]
            ),
            Message.tool(ToolResult(tool_call_id="t1", content="file data")),
        ]
        events = messages_to_ui_events(msgs)
        assert not any(e["type"] == "thinking" for e in events)


# ---------------------------------------------------------------------------
# M08 F6 L02 — projection-time truncation of tool_result.content
# ---------------------------------------------------------------------------


class TestMessagesToUiEventsTruncation:
    """``messages_to_ui_events`` caps ``tool_result.content`` at the shared
    ``MAX_TOOL_RESULT_INLINE_CONTENT`` constant.

    DB persistence is full-fidelity (covered elsewhere) — this class
    pins the PROJECTION-time truncation invariant. The same helper
    drives the live-broadcast + HTTP-API sites in
    ``the_one.interfaces.web.app``; alignment across all three sites
    is exercised in ``tests/test_tool_result_truncation_alignment.py``.
    """

    def test_tool_result_content_truncated_to_max(self) -> None:
        from the_one.db.codec import MAX_TOOL_RESULT_INLINE_CONTENT

        msg_over = Message(
            role=Role.TOOL,
            tool_result=ToolResult(
                tool_call_id="tc-1",
                content="x" * (MAX_TOOL_RESULT_INLINE_CONTENT + 1000),
            ),
        )
        events = messages_to_ui_events([msg_over])
        assert len(events) == 1
        assert events[0]["type"] == "tool_result"
        assert len(events[0]["content"]) == MAX_TOOL_RESULT_INLINE_CONTENT
        assert events[0]["content"] == "x" * MAX_TOOL_RESULT_INLINE_CONTENT

    def test_tool_result_content_at_cap_unchanged(self) -> None:
        from the_one.db.codec import MAX_TOOL_RESULT_INLINE_CONTENT

        msg_at = Message(
            role=Role.TOOL,
            tool_result=ToolResult(
                tool_call_id="tc-2",
                content="y" * MAX_TOOL_RESULT_INLINE_CONTENT,
            ),
        )
        events = messages_to_ui_events([msg_at])
        assert len(events[0]["content"]) == MAX_TOOL_RESULT_INLINE_CONTENT

    def test_tool_result_content_under_cap_unchanged(self) -> None:
        msg_under = Message(
            role=Role.TOOL,
            tool_result=ToolResult(tool_call_id="tc-3", content="hi"),
        )
        events = messages_to_ui_events([msg_under])
        assert events[0]["content"] == "hi"

    def test_db_persistence_full_fidelity_unchanged(self) -> None:
        """DB round-trip preserves full content; truncation is projection-only."""
        from the_one.db.codec import MAX_TOOL_RESULT_INLINE_CONTENT

        long_content = "z" * (MAX_TOOL_RESULT_INLINE_CONTENT + 4000)
        msgs = [
            Message(
                role=Role.TOOL,
                tool_result=ToolResult(tool_call_id="tc-4", content=long_content),
            )
        ]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].tool_result is not None
        assert rt[0].tool_result.content == long_content
        assert len(rt[0].tool_result.content) == MAX_TOOL_RESULT_INLINE_CONTENT + 4000


# ---------------------------------------------------------------------------
# M10 F03 L02 — Message.visibility round-trip + projection
# ---------------------------------------------------------------------------


class TestMessageVisibilityCodec:
    """``Message.visibility`` round-trips through ``message_to_dict`` ↔
    ``message_from_dict``: the key is emitted only when non-None,
    deserialization defaults to None when the key is absent (back-compat
    with every pre-F3 session row).
    """

    def test_message_to_dict_emits_visibility_when_non_none(self) -> None:
        msg = Message(role=Role.USER, content="hi", visibility="operator")
        d = message_to_dict(msg)
        assert d["visibility"] == "operator"

    def test_message_to_dict_omits_visibility_when_none(self) -> None:
        msg = Message(role=Role.USER, content="hi", visibility=None)
        d = message_to_dict(msg)
        assert "visibility" not in d

    def test_message_from_dict_restores_visibility(self) -> None:
        d = {"role": "user", "content": "hi", "visibility": "operator"}
        msg = message_from_dict(d)
        assert msg.visibility == "operator"

    def test_message_from_dict_back_compat_no_visibility_key(self) -> None:
        """Pre-F3 JSON had no visibility key — deserialize must default to None."""
        d = {"role": "user", "content": "hi"}
        msg = message_from_dict(d)
        assert msg.visibility is None

    def test_full_round_trip_tagged(self) -> None:
        msgs = [Message.user("hi", visibility="operator")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].visibility == "operator"

    def test_full_round_trip_untagged(self) -> None:
        msgs = [Message.user("hi")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].visibility is None


# ---------------------------------------------------------------------------
# M11 F06 L01 — Message.peer_name round-trip
# ---------------------------------------------------------------------------


class TestMessagePeerNameCodec:
    """``Message.peer_name`` round-trips through ``message_to_dict`` ↔
    ``message_from_dict``: the key is emitted only when non-None,
    deserialization defaults to None when the key is absent (back-compat
    with every pre-F6 session row).
    """

    def test_message_to_dict_emits_peer_name_when_non_none(self) -> None:
        msg = Message(role=Role.USER, content="hi", peer_name="alice")
        d = message_to_dict(msg)
        assert d["peer_name"] == "alice"

    def test_message_to_dict_omits_peer_name_when_none(self) -> None:
        msg = Message(role=Role.USER, content="hi", peer_name=None)
        d = message_to_dict(msg)
        assert "peer_name" not in d

    def test_message_from_dict_restores_peer_name(self) -> None:
        d = {"role": "user", "content": "hi", "peer_name": "alice"}
        msg = message_from_dict(d)
        assert msg.peer_name == "alice"

    def test_message_from_dict_back_compat_no_peer_name_key(self) -> None:
        """Pre-F6 JSON had no peer_name key — deserialize must default to None."""
        d = {"role": "user", "content": "hi"}
        msg = message_from_dict(d)
        assert msg.peer_name is None

    def test_full_round_trip_with_peer_name(self) -> None:
        msgs = [Message.user("hi", peer_name="alice")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].peer_name == "alice"

    def test_full_round_trip_without_peer_name(self) -> None:
        msgs = [Message.user("hi")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].peer_name is None

    def test_message_user_default_peer_name_is_none(self) -> None:
        """``Message.user`` defaults peer_name to None (kwarg-only contract)."""
        assert Message.user("hi").peer_name is None

    def test_message_user_kwarg_sets_peer_name(self) -> None:
        """``Message.user`` threads peer_name kwarg into the constructor."""
        assert Message.user("hi", peer_name="alice").peer_name == "alice"

    def test_round_trip_with_peer_name_and_visibility(self) -> None:
        """Both new optional fields compose: peer_name and visibility
        round-trip independently (cross-cutting back-compat check — neither
        field interferes with the other's encode/decode site).
        """
        msgs = [Message.user("hi", peer_name="alice", visibility="operator")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].peer_name == "alice"
        assert rt[0].visibility == "operator"


# ---------------------------------------------------------------------------
# M11 F07 L02 — Message.channel_id round-trip
# ---------------------------------------------------------------------------


class TestMessageChannelIdCodec:
    """``Message.channel_id`` round-trips through ``message_to_dict`` ↔
    ``message_from_dict``: the key is emitted only when non-None,
    deserialization defaults to None when the key is absent (back-compat
    with every pre-F7 session row). Mirrors ``TestMessagePeerNameCodec``.
    """

    def test_full_round_trip_with_channel_id(self) -> None:
        msgs = [Message.user("hi", channel_id="123456789")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].channel_id == "123456789"

    def test_message_from_dict_back_compat_no_channel_id_key(self) -> None:
        """Pre-F7 JSON had no channel_id key — deserialize must default to None."""
        d = {"role": "user", "content": "hi"}
        msg = message_from_dict(d)
        assert msg.channel_id is None

    def test_message_user_default_channel_id_is_none(self) -> None:
        """``Message.user`` defaults channel_id to None (kwarg-only contract).

        L3's dispatcher binding relies on this default — it constructs the
        user Message without channel_id then post-step-mutates it via
        ``bind_channel_context``. Breaking the default to a sentinel would
        change the codec's emit-when-non-None shape for every user turn.
        """
        assert Message.user("hi").channel_id is None

    def test_round_trip_with_channel_id_and_peer_name(self) -> None:
        """Both optional fields compose: channel_id and peer_name round-trip
        independently (cross-cutting back-compat check — neither field
        interferes with the other's encode/decode site).
        """
        msgs = [Message.user("hi", channel_id="123456789", peer_name="alice")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].channel_id == "123456789"
        assert rt[0].peer_name == "alice"


# ---------------------------------------------------------------------------
# M11 F07 L02 — Message.channel_name round-trip
# ---------------------------------------------------------------------------


class TestMessageChannelNameCodec:
    """``Message.channel_name`` round-trips through ``message_to_dict`` ↔
    ``message_from_dict``: the key is emitted only when non-None,
    deserialization defaults to None when the key is absent (back-compat
    with every pre-F7 session row). Mirrors ``TestMessagePeerNameCodec``.
    """

    def test_full_round_trip_with_channel_name(self) -> None:
        msgs = [Message.user("hi", channel_name="general")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].channel_name == "general"

    def test_message_from_dict_back_compat_no_channel_name_key(self) -> None:
        """Pre-F7 JSON had no channel_name key — deserialize must default to None."""
        d = {"role": "user", "content": "hi"}
        msg = message_from_dict(d)
        assert msg.channel_name is None

    def test_message_user_default_channel_name_is_none(self) -> None:
        """``Message.user`` defaults channel_name to None (kwarg-only contract).

        L3's dispatcher binding relies on this default — it constructs the
        user Message without channel_name then post-step-mutates it via
        ``bind_channel_context``. Breaking the default to a sentinel would
        change the codec's emit-when-non-None shape for every user turn.
        """
        assert Message.user("hi").channel_name is None

    def test_round_trip_with_channel_name_and_peer_name(self) -> None:
        """Both optional fields compose: channel_name and peer_name round-trip
        independently (cross-cutting back-compat check — neither field
        interferes with the other's encode/decode site).
        """
        msgs = [Message.user("hi", channel_name="general", peer_name="alice")]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].channel_name == "general"
        assert rt[0].peer_name == "alice"


# ---------------------------------------------------------------------------
# M16 F10 L01 — Message.thinking round-trip (structured extended-thinking
# blocks; truthy-guarded list sibling of tool_calls, NOT the emit-when-non-none
# convention)
# ---------------------------------------------------------------------------


class TestMessageThinkingCodec:
    """``Message.thinking`` round-trips through ``message_to_dict`` ↔
    ``message_from_dict`` as a list of ``ThinkingBlock``s, modeled on
    ``tool_calls``: the ``"thinking"`` key is emitted only when the list is
    non-empty (TRUTHY guard), and deserialization defaults to an empty list
    when the key is absent (back-compat with every pre-F10 session row).
    Signatures and redacted ``data`` survive verbatim; the stored block dict
    equals the Anthropic content-block shape (only set sub-keys) so Leg 03
    replay can hand it back with no re-mapping.
    """

    def test_emit_when_non_empty(self) -> None:
        """A message with one thinking block encodes a ``"thinking"`` key."""
        msg = Message.assistant(
            "answer",
            thinking=[ThinkingBlock(type="thinking", thinking="reasoning")],
        )
        d = message_to_dict(msg)
        assert d["thinking"] == [{"type": "thinking", "thinking": "reasoning"}]

    def test_omit_when_empty(self) -> None:
        """``Message.assistant("hi")`` (empty thinking) has no ``"thinking"`` key."""
        d = message_to_dict(Message.assistant("hi"))
        assert "thinking" not in d

    def test_signature_preservation(self) -> None:
        """A ``type="thinking"`` block round-trips ``thinking`` + ``signature``
        verbatim (the signature MUST survive or the follow-up turn 400s)."""
        block = ThinkingBlock(type="thinking", thinking="let me think", signature="sig-abc-123")
        rt = decode_messages(encode_messages([Message.assistant("ok", thinking=[block])]))
        assert len(rt[0].thinking) == 1
        got = rt[0].thinking[0]
        assert got.type == "thinking"
        assert got.thinking == "let me think"
        assert got.signature == "sig-abc-123"
        assert got.data is None

    def test_redacted_round_trip(self) -> None:
        """A ``type="redacted_thinking"`` block preserves ``data`` and leaves
        ``thinking``/``signature`` at ``None`` (omitted from the stored dict)."""
        block = ThinkingBlock(type="redacted_thinking", data="opaque-blob")
        d = message_to_dict(Message.assistant("ok", thinking=[block]))
        assert d["thinking"] == [{"type": "redacted_thinking", "data": "opaque-blob"}]
        rt = decode_messages(encode_messages([Message.assistant("ok", thinking=[block])]))
        got = rt[0].thinking[0]
        assert got.type == "redacted_thinking"
        assert got.data == "opaque-blob"
        assert got.thinking is None
        assert got.signature is None

    def test_back_compat_no_thinking_key(self) -> None:
        """Pre-F10 JSON had no thinking key — deserialize must default to []."""
        msg = message_from_dict({"role": "assistant", "content": "hi"})
        assert msg.thinking == []

    def test_message_assistant_default_thinking_is_empty(self) -> None:
        """``Message.assistant`` defaults thinking to an empty list (kwarg-only)."""
        assert Message.assistant("hi").thinking == []

    def test_full_round_trip_through_list_codec(self) -> None:
        """A multi-block thinking message round-trips through the list codec."""
        blocks = [
            ThinkingBlock(type="thinking", thinking="step 1", signature="s1"),
            ThinkingBlock(type="redacted_thinking", data="blob"),
        ]
        rt = decode_messages(encode_messages([Message.assistant("done", thinking=blocks)]))
        assert [b.type for b in rt[0].thinking] == ["thinking", "redacted_thinking"]
        assert rt[0].thinking[0].signature == "s1"
        assert rt[0].thinking[1].data == "blob"

    def test_empty_string_signature_survives(self) -> None:
        """An empty-but-present signature round-trips verbatim (sub-key guard is
        ``is not None``, not truthiness)."""
        block = ThinkingBlock(type="thinking", thinking="", signature="")
        d = message_to_dict(Message.assistant("ok", thinking=[block]))
        assert d["thinking"] == [{"type": "thinking", "thinking": "", "signature": ""}]
        rt = decode_messages(encode_messages([Message.assistant("ok", thinking=[block])]))
        assert rt[0].thinking[0].thinking == ""
        assert rt[0].thinking[0].signature == ""

    def test_mixed_content_thinking_and_tool_calls(self) -> None:
        """The criterion-#1 turn shape: a single Message carrying content +
        thinking + tool_calls simultaneously round-trips all three, each
        emitting on its own independent guard with no cross-interference."""
        tc = ThinkingBlock(type="thinking", thinking="reason", signature="sig")
        call = ToolCall(id="tc-1", name="search", arguments={"q": "x"})
        msg = Message.assistant("here is the answer", tool_calls=[call], thinking=[tc])
        d = message_to_dict(msg)
        assert d["content"] == "here is the answer"
        assert d["thinking"] == [{"type": "thinking", "thinking": "reason", "signature": "sig"}]
        assert d["tool_calls"] == [{"id": "tc-1", "name": "search", "arguments": {"q": "x"}}]
        rt = decode_messages(encode_messages([msg]))
        assert rt[0].content == "here is the answer"
        assert rt[0].thinking[0].signature == "sig"
        assert rt[0].tool_calls[0].id == "tc-1"

    def test_unknown_future_type_round_trips(self) -> None:
        """Forward-compat: a block with an unrecognized ``type`` round-trips its
        ``type`` plus whatever set sub-fields it carries without dropping —
        locks in the free-``str`` ``type`` property (no enum)."""
        block = ThinkingBlock(type="some_future_kind", thinking="t", signature="s", data="d")
        d = message_to_dict(Message.assistant("ok", thinking=[block]))
        assert d["thinking"] == [
            {"type": "some_future_kind", "thinking": "t", "signature": "s", "data": "d"}
        ]
        rt = decode_messages(encode_messages([Message.assistant("ok", thinking=[block])]))
        got = rt[0].thinking[0]
        assert got.type == "some_future_kind"
        assert got.thinking == "t"
        assert got.signature == "s"
        assert got.data == "d"

    def test_thinking_bearing_message_still_omits_empty_optionals(self) -> None:
        """Belt-and-suspenders: the tripwire's invariant still holds for a
        thinking-bearing assistant message — an assistant message with ONLY a
        thinking block emits exactly ``{"role", "content", "thinking"}`` (no
        stray empty optional keys). The real tripwire at the module bottom
        (``test_encode_emits_no_keys_when_all_optional_fields_default``) stays
        untouched; this guards the composed shape."""
        msg = Message.assistant("hi", thinking=[ThinkingBlock(type="thinking", thinking="r")])
        d = message_to_dict(msg)
        assert sorted(d.keys()) == ["content", "role", "thinking"]


# ---------------------------------------------------------------------------
# M16 F12 L02 — Message.content as list[ContentBlock] round-trip (multimodal
# USER-only content; the DD2 fork the codec pays for — dataclass content
# blocks aren't JSON-serializable, so the opaque str passthrough is widened
# with an isinstance-dispatched block codec, mirroring the ThinkingBlock
# precedent on the encode side but deliberately departing on decode: an
# unrecognized block type RAISES rather than silently dropping (F10 Rec 5)).
# ---------------------------------------------------------------------------


class TestContentBlockCodec:
    """``Message.content`` round-trips as either ``str`` (byte-identical,
    unchanged) or ``list[ContentBlock]`` (each block encoded/decoded via
    ``_content_block_to_dict``/``_content_block_from_dict``)."""

    def test_str_content_byte_identical(self) -> None:
        """The str path is untouched — same behavior as every pre-F12 test."""
        msg = Message.user("hello world")
        d = message_to_dict(msg)
        assert d["content"] == "hello world"
        rt = decode_messages(encode_messages([msg]))
        assert rt[0].content == "hello world"

    def test_list_content_round_trip_all_block_shapes(self) -> None:
        """A USER message with [TextContent, ImageContent(data=...),
        ImageContent(url=...)] survives message_to_dict -> json.dumps ->
        json.loads -> message_from_dict equal to the original."""
        blocks: list[ContentBlock] = [
            TextContent(text="what is this?"),
            ImageContent(media_type="image/png", data="YmFzZTY0ZGF0YQ=="),
            ImageContent(media_type="image/jpeg", url="https://example.com/pic.jpg"),
        ]
        msg = Message.user(blocks)
        d = message_to_dict(msg)
        assert d["content"] == [
            {"type": "text", "text": "what is this?"},
            {"type": "image", "media_type": "image/png", "data": "YmFzZTY0ZGF0YQ=="},
            {"type": "image", "media_type": "image/jpeg", "url": "https://example.com/pic.jpg"},
        ]
        # Full round-trip through the JSON encode/decode boundary.
        json_str = json.dumps([d])
        rt = [message_from_dict(rd) for rd in json.loads(json_str)]
        assert rt[0].content == blocks

    def test_encode_decode_via_helpers_round_trip(self) -> None:
        """encode_messages -> decode_messages round-trips list content equal
        to the original, using the module's own JSON boundary."""
        blocks: list[ContentBlock] = [
            TextContent(text="see attached"),
            ImageContent(media_type="image/png", data="abc123"),
        ]
        msg = Message.user(blocks)
        rt = decode_messages(encode_messages([msg]))
        assert rt[0].content == blocks

    def test_image_content_data_only(self) -> None:
        """data-only ImageContent emits/decodes without a url key."""
        block = ImageContent(media_type="image/png", data="abc123")
        d = _content_block_to_dict(block)
        assert d == {"type": "image", "media_type": "image/png", "data": "abc123"}
        assert _content_block_from_dict(d) == block

    def test_image_content_url_only(self) -> None:
        """url-only ImageContent emits/decodes without a data key."""
        block = ImageContent(media_type="image/png", url="https://example.com/x.png")
        d = _content_block_to_dict(block)
        assert d == {
            "type": "image",
            "media_type": "image/png",
            "url": "https://example.com/x.png",
        }
        assert _content_block_from_dict(d) == block

    def test_image_content_both_data_and_url(self) -> None:
        """Both data and url set -> both emitted, both decoded."""
        block = ImageContent(media_type="image/png", data="abc123", url="https://example.com/x.png")
        d = _content_block_to_dict(block)
        assert d == {
            "type": "image",
            "media_type": "image/png",
            "data": "abc123",
            "url": "https://example.com/x.png",
        }
        assert _content_block_from_dict(d) == block

    def test_empty_list_content_round_trips(self) -> None:
        """Empty list content encodes to [] and decodes to [] (matches L01's
        lenient empty-list on the dataclass side)."""
        msg = Message.user([])
        d = message_to_dict(msg)
        assert d["content"] == []
        rt = decode_messages(encode_messages([msg]))
        assert rt[0].content == []

    def test_unknown_block_type_raises_on_decode(self) -> None:
        """An unrecognized block type on decode RAISES rather than being
        silently dropped (F10 Rec 5 anti-pattern — content blocks are user
        data with no safe default target, unlike the permissive thinking-type
        decode)."""
        with pytest.raises(ValueError, match="unknown content block type"):
            _content_block_from_dict({"type": "video", "url": "https://example.com/v.mp4"})

    def test_unknown_block_type_raises_through_message_from_dict(self) -> None:
        """The raise propagates through the full message_from_dict path, not
        just the block-level helper."""
        raw = {
            "role": "user",
            "content": [{"type": "video", "url": "https://example.com/v.mp4"}],
        }
        with pytest.raises(ValueError, match="unknown content block type"):
            message_from_dict(raw)

    def test_legacy_str_content_decodes(self) -> None:
        """A legacy dict with plain str content (no blocks, pre-F12 shape)
        decodes unchanged — the back-compat case."""
        msg = message_from_dict({"role": "user", "content": "just text"})
        assert msg.content == "just text"

    def test_legacy_missing_content_key_decodes_to_empty_str(self) -> None:
        """No content key at all -> default "" (pre-existing behavior,
        untouched by the list branch)."""
        msg = message_from_dict({"role": "assistant"})
        assert msg.content == ""

    def test_list_content_on_non_user_role_raises_on_decode(self) -> None:
        """A persisted list-content dict on a non-USER role raises via
        Message.__post_init__'s role guard on decode — the codec relies on
        the dataclass invariant (DD3), not its own role check."""
        raw = {
            "role": "assistant",
            "content": [{"type": "text", "text": "hi"}],
        }
        with pytest.raises(AssertionError, match="only valid on USER messages"):
            message_from_dict(raw)


# ---------------------------------------------------------------------------
# M11 F07 L02 — channel-context composition (channel_id + channel_name
# alongside peer_name and visibility)
# ---------------------------------------------------------------------------


class TestMessageChannelContextCompositionCodec:
    """Cross-cutting composition tests: all four optional Message fields
    (visibility, peer_name, channel_id, channel_name) follow the
    ``message-additive-back-compat-via-emit-when-non-none`` convention and
    must each independently emit-when-non-None and decode-with-default
    without interference from the others.
    """

    def test_round_trip_with_all_optional_fields(self) -> None:
        """All four optional fields round-trip independently when set."""
        msgs = [
            Message.user(
                "hi",
                visibility="operator",
                peer_name="alice",
                channel_id="123456789",
                channel_name="general",
            )
        ]
        rt = decode_messages(encode_messages(msgs))
        assert rt[0].visibility == "operator"
        assert rt[0].peer_name == "alice"
        assert rt[0].channel_id == "123456789"
        assert rt[0].channel_name == "general"

    def test_encode_emits_no_keys_when_all_optional_fields_default(self) -> None:
        """A default ``Message.user("hi")`` encodes to ``{"role", "content"}``
        only — no optional keys (visibility, peer_name, channel_id,
        channel_name) appear when each is at its None default.

        This pins the back-compat invariant globally for the
        ``message-additive-back-compat-via-emit-when-non-none`` convention:
        a Message with no optional fields set encodes byte-identical to
        pre-M10-F3 (and pre-M11-F6, and pre-M11-F7) rows.

        TRIPWIRE: any new optional Message field added via the
        ``message-additive-back-compat-via-emit-when-non-none`` convention
        MUST update this expected-key-list in the same edit that bumps
        the ``n=N`` citation count in ``the_one/agents.md``. Do NOT
        "fix" the failing test by adding the new field to the expected
        list silently — that defeats the back-compat tripwire. The
        intentional coupling between this test and the convention's
        citation count is what keeps the tripwire load-bearing.
        """
        msg = Message.user("hi")
        d = message_to_dict(msg)
        assert sorted(d.keys()) == ["content", "role"]


class TestMessagesToUiEventsVisibility:
    """``messages_to_ui_events`` projects ``visibility`` into every event
    derived from a tagged Message — across all four event branches (user,
    assistant content, tool_call, tool_result). When source visibility is
    None, the key is absent from the projected event (frontends treat
    absent === platform-visible).
    """

    def test_projects_visibility_on_tagged_user_message(self) -> None:
        msgs = [Message.user("hi", visibility="operator")]
        events = messages_to_ui_events(msgs)
        assert events[0]["visibility"] == "operator"

    def test_omits_visibility_on_untagged_user_message(self) -> None:
        msgs = [Message.user("hi")]
        events = messages_to_ui_events(msgs)
        assert "visibility" not in events[0]

    def test_projects_visibility_on_assistant_content(self) -> None:
        msgs = [Message.assistant("hi there", visibility="operator")]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        assert events[0]["type"] == "assistant"
        assert events[0]["visibility"] == "operator"

    def test_projects_visibility_on_tool_call_event(self) -> None:
        tc1 = ToolCall(id="tc-1", name="read_file", arguments={"path": "/x"})
        tc2 = ToolCall(id="tc-2", name="shell", arguments={"cmd": "ls"})
        msgs = [
            Message.assistant("", tool_calls=[tc1, tc2], visibility="operator"),
        ]
        events = messages_to_ui_events(msgs)
        # Both tool_call events carry the tag
        tc_events = [e for e in events if e["type"] == "tool_call"]
        assert len(tc_events) == 2
        for ev in tc_events:
            assert ev["visibility"] == "operator"

    def test_projects_visibility_on_tool_result_event(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="done")
        msgs = [Message.tool(tr, visibility="operator")]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        assert events[0]["type"] == "tool_result"
        assert events[0]["visibility"] == "operator"

    def test_mixed_visibility_session(self) -> None:
        """One tagged + one untagged user message: present-and-absent keys."""
        msgs = [
            Message.user("operator-only", visibility="operator"),
            Message.user("public"),
        ]
        events = messages_to_ui_events(msgs)
        assert len(events) == 2
        assert events[0]["visibility"] == "operator"
        assert "visibility" not in events[1]

    def test_existing_assistant_text_event_shape_unchanged_when_untagged(self) -> None:
        """Pure addition: untagged events keep their pre-F3 shape exactly."""
        msgs = [Message.assistant("hi there")]
        events = messages_to_ui_events(msgs)
        assert events[0] == {"type": "assistant", "content": "hi there"}

    def test_existing_user_event_shape_unchanged_when_untagged(self) -> None:
        msgs = [Message.user("hello")]
        events = messages_to_ui_events(msgs)
        assert events[0] == {"type": "user", "content": "hello", "source": "restored"}

    def test_existing_tool_call_event_shape_unchanged_when_untagged(self) -> None:
        tc = ToolCall(id="tc-1", name="read_file", arguments={"path": "/x"})
        msgs = [Message.assistant("", tool_calls=[tc])]
        events = messages_to_ui_events(msgs)
        assert events[0] == {
            "type": "tool_call",
            "name": "read_file",
            "arguments": {"path": "/x"},
            "parent_message_id": "replay-msg-0",
            "tool_call_id": "tc-1",
        }

    def test_existing_tool_result_event_shape_unchanged_when_untagged(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="done")
        msgs = [Message.tool(tr)]
        events = messages_to_ui_events(msgs)
        assert events[0] == {
            "type": "tool_result",
            "content": "done",
            "is_error": False,
            "parent_message_id": None,
            "tool_call_id": "tc-1",
        }


class TestMessagesToUiEventsPeerName:
    """``messages_to_ui_events`` projects ``peer_name`` ONLY onto user-role
    events. Assistant/tool branches are unaffected — peer_name is
    meaningful only on user-role messages, and the projection's per-branch
    spread is gated accordingly. Composes cleanly with the visibility
    projection (both keys spread independently from per-message dicts).
    """

    def test_projects_peer_name_on_user_message(self) -> None:
        msgs = [Message.user("hi", peer_name="alice")]
        events = messages_to_ui_events(msgs)
        assert events[0]["peer_name"] == "alice"

    def test_omits_peer_name_on_user_message_without_peer_name(self) -> None:
        msgs = [Message.user("hi")]
        events = messages_to_ui_events(msgs)
        assert "peer_name" not in events[0]

    def test_does_not_project_peer_name_on_assistant_event(self) -> None:
        # Direct constructor — paranoia: even if peer_name is somehow set
        # on a non-USER message, the projection MUST NOT propagate it.
        msgs = [Message(role=Role.ASSISTANT, content="hi there", peer_name="alice")]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        assert events[0]["type"] == "assistant"
        assert "peer_name" not in events[0]

    def test_does_not_project_peer_name_on_tool_call_event(self) -> None:
        tc1 = ToolCall(id="tc-1", name="read_file", arguments={"path": "/x"})
        msgs = [
            Message(
                role=Role.ASSISTANT,
                content="",
                tool_calls=[tc1],
                peer_name="alice",
            )
        ]
        events = messages_to_ui_events(msgs)
        tc_events = [e for e in events if e["type"] == "tool_call"]
        assert len(tc_events) == 1
        assert "peer_name" not in tc_events[0]

    def test_does_not_project_peer_name_on_tool_result_event(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="done")
        msgs = [
            Message(
                role=Role.TOOL,
                content="done",
                tool_result=tr,
                peer_name="alice",
            )
        ]
        events = messages_to_ui_events(msgs)
        assert len(events) == 1
        assert events[0]["type"] == "tool_result"
        assert "peer_name" not in events[0]

    def test_user_event_carries_both_peer_name_and_visibility(self) -> None:
        msgs = [Message.user("hi", peer_name="alice", visibility="operator")]
        events = messages_to_ui_events(msgs)
        assert events[0]["peer_name"] == "alice"
        assert events[0]["visibility"] == "operator"

    def test_mixed_user_messages_in_session(self) -> None:
        """Three user messages with different (peer_name, visibility) combos:
        keys present/absent independently per message."""
        msgs = [
            Message.user("plain"),
            Message.user("from-alice", peer_name="alice"),
            Message.user("operator-and-alice", peer_name="alice", visibility="operator"),
        ]
        events = messages_to_ui_events(msgs)
        assert len(events) == 3
        assert "peer_name" not in events[0]
        assert "visibility" not in events[0]
        assert events[1]["peer_name"] == "alice"
        assert "visibility" not in events[1]
        assert events[2]["peer_name"] == "alice"
        assert events[2]["visibility"] == "operator"


# ---------------------------------------------------------------------------
# M11 F07 L03 — channel_id + channel_name UI-event projection
# ---------------------------------------------------------------------------


class TestMessagesToUiEventsChannelContext:
    """``messages_to_ui_events`` projects ``channel_id`` and ``channel_name``
    ONLY onto user-role events. Assistant/tool branches are unaffected —
    channel context is meaningful only on connector-inbound user-role
    messages, and the projection's per-branch spread is gated to USER.
    Composes cleanly with the visibility and peer_name projections — all
    four keys spread independently from per-message dicts.

    The codec is the single projection site that covers BOTH replay (via
    ``_restore_session``) AND live broadcast (via the dispatcher's
    ``broadcast_to_session`` loop after persistence). Pinning the
    projection behavior here is therefore the load-bearing test for
    both paths.
    """

    def test_messages_to_ui_events_projects_channel_id_on_user_event(
        self,
    ) -> None:
        msgs = [Message.user("hi", channel_id="C123")]
        events = messages_to_ui_events(msgs)
        assert events[0]["channel_id"] == "C123"

    def test_messages_to_ui_events_projects_channel_name_on_user_event(
        self,
    ) -> None:
        msgs = [Message.user("hi", channel_name="general")]
        events = messages_to_ui_events(msgs)
        assert events[0]["channel_name"] == "general"

    def test_messages_to_ui_events_omits_channel_keys_when_none(self) -> None:
        """No channel context set → no ``channel_id`` / ``channel_name``
        keys in the event payload (mirror of the visibility / peer_name
        emit-when-non-None convention).
        """
        msgs = [Message.user("hi")]
        events = messages_to_ui_events(msgs)
        assert "channel_id" not in events[0]
        assert "channel_name" not in events[0]

    def test_messages_to_ui_events_does_not_project_channel_on_assistant_or_tool_events(
        self,
    ) -> None:
        """Even if a non-USER message somehow has channel fields populated
        (the dispatcher never does this — but the projection MUST be
        gated defensively against drift), the projection MUST NOT emit
        ``channel_id`` or ``channel_name`` onto assistant/tool events.
        """
        # Direct constructor — paranoia: channel fields on non-USER
        # messages should not propagate through the projection.
        msgs = [
            Message(
                role=Role.ASSISTANT,
                content="reply",
                channel_id="C123",
                channel_name="general",
            ),
            Message(
                role=Role.TOOL,
                content="done",
                tool_result=ToolResult(tool_call_id="tc-1", content="done"),
                channel_id="C123",
                channel_name="general",
            ),
        ]
        events = messages_to_ui_events(msgs)
        # Two events: one assistant + one tool_result.
        for event in events:
            assert event["type"] in ("assistant", "tool_result")
            assert "channel_id" not in event
            assert "channel_name" not in event


class TestMessageVisibilityClassmethodKwargs:
    """``visibility`` is keyword-only across all four ``Message`` classmethods.
    Positional passthrough is rejected (TypeError) to prevent F4/F5 dispatcher
    code from accidentally relying on positional drift.
    """

    def test_user_accepts_visibility_kwarg(self) -> None:
        msg = Message.user("hi", visibility="operator")
        assert msg.role == Role.USER
        assert msg.visibility == "operator"

    def test_user_default_visibility_is_none(self) -> None:
        assert Message.user("hi").visibility is None

    def test_user_rejects_positional_visibility(self) -> None:
        with pytest.raises(TypeError):
            Message.user("hi", "operator")  # type: ignore[misc]

    def test_system_accepts_visibility_kwarg(self) -> None:
        msg = Message.system("you are helpful", visibility="operator")
        assert msg.role == Role.SYSTEM
        assert msg.visibility == "operator"

    def test_system_default_visibility_is_none(self) -> None:
        assert Message.system("you are helpful").visibility is None

    def test_system_rejects_positional_visibility(self) -> None:
        with pytest.raises(TypeError):
            Message.system("hi", "operator")  # type: ignore[misc]

    def test_assistant_accepts_visibility_kwarg(self) -> None:
        msg = Message.assistant("hi", visibility="operator")
        assert msg.role == Role.ASSISTANT
        assert msg.visibility == "operator"

    def test_assistant_default_visibility_is_none(self) -> None:
        assert Message.assistant("hi").visibility is None

    def test_assistant_rejects_positional_visibility(self) -> None:
        # The 3 named positional slots are content, tool_calls, usage; a 4th
        # positional would be visibility. Keyword-only enforcement rejects it.
        with pytest.raises(TypeError):
            Message.assistant("hi", None, None, "operator")  # type: ignore[misc]

    def test_tool_accepts_visibility_kwarg(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="done")
        msg = Message.tool(tr, visibility="operator")
        assert msg.role == Role.TOOL
        assert msg.visibility == "operator"

    def test_tool_default_visibility_is_none(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="done")
        assert Message.tool(tr).visibility is None

    def test_tool_rejects_positional_visibility(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="done")
        with pytest.raises(TypeError):
            Message.tool(tr, "operator")  # type: ignore[misc]
