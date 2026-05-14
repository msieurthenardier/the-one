"""Tests for message codec round-trip serialization."""

from __future__ import annotations

from the_one.db.codec import (
    _tool_result_to_dict,
    decode_messages,
    encode_messages,
    message_from_dict,
    messages_to_ui_events,
)
from the_one.llm.base import Message, Role, TokenUsage, ToolCall, ToolResult


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
