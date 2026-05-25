"""Tests for ``the_one.llm.base`` — currently scoped to the
``build_user_message_content`` helper that L4 ships.

M11 F7 L4: closes F6 Rec #4 / M11 criterion #13. The helper centralises
the four absence variants of the peer_name + channel_name inline-prefix
projection that all three provider adapters (and OpenRouter via
OpenAIProvider inheritance) call from ``_to_api_message``.
"""

from __future__ import annotations

from the_one.llm.base import Message, Role, build_user_message_content


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
