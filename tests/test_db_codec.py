"""Tests for message codec round-trip serialization."""

from __future__ import annotations

import pytest

from the_one.db.codec import (
    _tool_result_to_dict,
    decode_messages,
    encode_messages,
    message_from_dict,
    message_to_dict,
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
            Message.user(
                "operator-and-alice", peer_name="alice", visibility="operator"
            ),
        ]
        events = messages_to_ui_events(msgs)
        assert len(events) == 3
        assert "peer_name" not in events[0]
        assert "visibility" not in events[0]
        assert events[1]["peer_name"] == "alice"
        assert "visibility" not in events[1]
        assert events[2]["peer_name"] == "alice"
        assert events[2]["visibility"] == "operator"


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
