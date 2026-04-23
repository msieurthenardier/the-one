"""Tests for message codec round-trip serialization."""

from __future__ import annotations

from the_one.db.codec import decode_messages, encode_messages
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
