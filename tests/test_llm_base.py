"""Tests for ``the_one.llm.base`` — currently scoped to the
``build_user_message_content`` helper that L4 ships.

M11 F7 L4: closes F6 Rec #4 / M11 criterion #13. The helper centralises
the four absence variants of the peer_name + channel_name inline-prefix
projection that all three provider adapters (and OpenRouter via
OpenAIProvider inheritance) call from ``_to_api_message``.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from the_one.llm.base import (
    ContentBlock,
    ImageContent,
    Message,
    Role,
    TextContent,
    ToolResult,
    build_user_message_content,
    content_to_text,
)


class TestBuildUserMessageContent:
    def test_build_user_message_content_with_both_fields(self) -> None:
        msg = Message.user("hi", peer_name="alice", channel_name="general")
        assert build_user_message_content(msg) == "[from alice in #general]: hi"

    def test_build_user_message_content_with_peer_name_only(self) -> None:
        msg = Message.user("hi", peer_name="alice")
        assert build_user_message_content(msg) == "[from alice]: hi"

    def test_build_user_message_content_with_channel_name_only(self) -> None:
        msg = Message.user("hi", channel_name="general")
        assert build_user_message_content(msg) == "[in #general]: hi"

    def test_build_user_message_content_with_neither(self) -> None:
        # Both None → byte-identical to legacy payload (pre-F6 + pre-F7).
        msg = Message.user("hi")
        assert build_user_message_content(msg) == "hi"

    def test_build_user_message_content_with_empty_string_peer_name(self) -> None:
        # Empty string is NOT None; per the
        # ``message-additive-back-compat-via-emit-when-non-none`` convention
        # it round-trips as-is. Rendering the bracket with an empty name is
        # the contracted shape, not the helper's concern.
        msg = Message.user("hi", peer_name="", channel_name="general")
        assert build_user_message_content(msg) == "[from  in #general]: hi"

    def test_build_user_message_content_with_assistant_role_returns_unchanged(self) -> None:
        # Defensive: the helper should never be called on a non-USER message
        # by the provider adapters (the user-role branch is the only call
        # site), but the safety branch prevents accidental leakage if a
        # future caller violates the contract.
        msg = Message(role=Role.ASSISTANT, content="hi", peer_name="alice")
        assert build_user_message_content(msg) == "hi"


class TestContentBlockConstruction:
    """M16 F12 L01 (DD2): TextContent + ImageContent dataclasses."""

    def test_text_content_holds_text(self) -> None:
        block = TextContent(text="hello")
        assert block.text == "hello"
        assert isinstance(block, ContentBlock)

    def test_image_content_with_data_only(self) -> None:
        block = ImageContent(media_type="image/png", data="Zm9v")
        assert block.media_type == "image/png"
        assert block.data == "Zm9v"
        assert block.url is None
        assert isinstance(block, ContentBlock)

    def test_image_content_with_url_only(self) -> None:
        block = ImageContent(media_type="image/png", url="https://example.com/a.png")
        assert block.data is None
        assert block.url == "https://example.com/a.png"

    def test_image_content_with_both_data_and_url_allowed(self) -> None:
        # Edge case: "at least one" guard, not "exactly one" — provider
        # mapping prefers `data` (base64 universal), decided at L04-L06.
        block = ImageContent(media_type="image/png", data="Zm9v", url="https://example.com/a.png")
        assert block.data == "Zm9v"
        assert block.url == "https://example.com/a.png"

    def test_image_content_requires_data_or_url(self) -> None:
        """M18 F02 L01: the guard uses an explicit ``raise AssertionError``
        rather than a bare ``assert`` statement — a bare ``assert`` is
        stripped under ``python -O``, which would silently construct a
        useless data-less/url-less ``ImageContent``. Mirrors
        ``TestMessageContentAssert`` below (``Message.__post_init__``'s
        own explicit-raise convention)."""
        with pytest.raises(AssertionError):
            ImageContent(media_type="image/png")


class TestMessageUserFactoryAcceptsBlockList:
    """M16 F12 L01: ``Message.user()`` widened to str | list[ContentBlock]."""

    def test_user_factory_accepts_block_list(self) -> None:
        blocks: list[ContentBlock] = [
            TextContent(text="look at this"),
            ImageContent(media_type="image/png", data="Zm9v"),
        ]
        msg = Message.user(blocks)
        assert msg.content == blocks
        assert msg.role == Role.USER


class TestMessageContentAssert:
    """M16 F12 L01 (DD3): conditional assert — str always OK; list[ContentBlock]
    OK only on Role.USER; anything else raises AssertionError via explicit
    ``raise`` (not a bare ``assert``, so the role guard survives ``-O``)."""

    def test_str_content_on_any_role_is_fine(self) -> None:
        for role in Role:
            Message(role=role, content="hi")

    def test_user_role_block_list_is_fine(self) -> None:
        Message(role=Role.USER, content=[TextContent(text="hi")])

    def test_empty_block_list_on_user_is_allowed(self) -> None:
        # Lenient-by-design: the assert validates shape + role, not content
        # semantics — mirrors the empty-str precedent.
        Message(role=Role.USER, content=[])

    def test_block_list_on_assistant_role_raises(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.ASSISTANT, content=[TextContent(text="hi")])

    def test_block_list_on_system_role_raises(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.SYSTEM, content=[TextContent(text="hi")])

    def test_block_list_on_tool_role_raises(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.TOOL, content=[TextContent(text="hi")])

    def test_list_of_junk_raises(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.USER, content=["not a block"])

    def test_non_str_non_list_content_raises(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.USER, content=42)


class TestBuildUserMessageContentBlockList:
    """M16 F12 L01 (DD4): list[ContentBlock] content is shape-aware — a
    separate prepended TextContent prefix block, never merged into the
    user's own blocks."""

    def test_list_content_with_both_fields_prepends_prefix_block(self) -> None:
        blocks = [TextContent(text="hi"), ImageContent(media_type="image/png", data="x")]
        msg = Message.user(list(blocks), peer_name="alice", channel_name="general")
        result = build_user_message_content(msg)
        assert result == [TextContent(text="[from alice in #general]:"), *blocks]

    def test_list_content_with_peer_name_only_prepends_prefix_block(self) -> None:
        blocks = [TextContent(text="hi")]
        msg = Message.user(list(blocks), peer_name="alice")
        result = build_user_message_content(msg)
        assert result == [TextContent(text="[from alice]:"), *blocks]

    def test_list_content_with_channel_name_only_prepends_prefix_block(self) -> None:
        blocks = [TextContent(text="hi")]
        msg = Message.user(list(blocks), channel_name="general")
        result = build_user_message_content(msg)
        assert result == [TextContent(text="[in #general]:"), *blocks]

    def test_list_content_with_neither_omits_prefix_block(self) -> None:
        blocks = [TextContent(text="hi"), ImageContent(media_type="image/png", data="x")]
        msg = Message.user(list(blocks))
        result = build_user_message_content(msg)
        assert result == blocks

    def test_list_content_with_neither_returns_a_copy_not_the_same_list(self) -> None:
        blocks = [TextContent(text="hi")]
        msg = Message.user(blocks)
        result = build_user_message_content(msg)
        assert result == blocks
        assert result is not msg.content

    def test_empty_list_content_with_neither_returns_empty_list(self) -> None:
        msg = Message.user([])
        assert build_user_message_content(msg) == []

    def test_empty_list_content_with_prefix_returns_just_the_prefix_block(self) -> None:
        msg = Message.user([], peer_name="alice")
        assert build_user_message_content(msg) == [TextContent(text="[from alice]:")]


class TestContentToText:
    """M16 F12 L03: ``content_to_text`` flattens content to a plain-text
    projection for str-only consumers (e.g. the inference classifier's
    history render). Dispatch is by ``isinstance``, not a type string."""

    def test_str_passthrough_unchanged(self) -> None:
        assert content_to_text("hello world") == "hello world"

    def test_empty_str_passthrough(self) -> None:
        assert content_to_text("") == ""

    def test_text_only_list_joins_with_single_space(self) -> None:
        blocks: list[ContentBlock] = [TextContent(text="hello"), TextContent(text="world")]
        assert content_to_text(blocks) == "hello world"

    def test_image_block_becomes_placeholder(self) -> None:
        blocks: list[ContentBlock] = [ImageContent(media_type="image/png", data="Zm9v")]
        assert content_to_text(blocks) == "[image]"

    def test_mixed_text_and_image_ordering_preserved(self) -> None:
        blocks: list[ContentBlock] = [
            TextContent(text="look at this"),
            ImageContent(media_type="image/png", data="Zm9v"),
            TextContent(text="cool right?"),
        ]
        assert content_to_text(blocks) == "look at this [image] cool right?"

    def test_empty_list_returns_empty_string(self) -> None:
        assert content_to_text([]) == ""


class TestMessageCreatedAt:
    """Fix: message-timestamp-on-replay. ``Message.created_at`` is None on
    the bare dataclass; ``Message.user``/``Message.assistant`` default it to
    ``_utcnow_iso()`` when the caller doesn't supply one explicitly.
    ``Message.system``/``Message.tool`` never set it (those roles render no
    attribution timestamp in the Chat UI).
    """

    def test_bare_message_created_at_is_none(self) -> None:
        assert Message(role=Role.USER, content="hi").created_at is None

    def test_user_factory_defaults_created_at_to_iso_string(self) -> None:
        msg = Message.user("hi")
        assert isinstance(msg.created_at, str)
        assert msg.created_at is not None
        # Round-trips through datetime.fromisoformat without raising —
        # confirms it's a well-formed ISO 8601 string (the format
        # _utcnow_iso() and Message.user/assistant emit).
        datetime.fromisoformat(msg.created_at)

    def test_user_factory_accepts_explicit_created_at(self) -> None:
        msg = Message.user("hi", created_at="2024-01-01T00:00:00+00:00")
        assert msg.created_at == "2024-01-01T00:00:00+00:00"

    def test_assistant_factory_defaults_created_at_to_iso_string(self) -> None:
        msg = Message.assistant("hi there")
        assert isinstance(msg.created_at, str)
        assert msg.created_at is not None
        datetime.fromisoformat(msg.created_at)

    def test_assistant_factory_accepts_explicit_created_at(self) -> None:
        msg = Message.assistant("hi there", created_at="2024-01-01T00:00:00+00:00")
        assert msg.created_at == "2024-01-01T00:00:00+00:00"

    def test_system_factory_leaves_created_at_none(self) -> None:
        assert Message.system("you are helpful").created_at is None

    def test_tool_factory_leaves_created_at_none(self) -> None:
        tr = ToolResult(tool_call_id="tc-1", content="done")
        assert Message.tool(tr).created_at is None
