"""Unit tests for ``the_one.connectors.post_step_metadata`` —
``tag_post_step_visibility`` (relocated from
``the_one.connectors.visibility`` at M11 F7 L1) and ``bind_peer_name``
(extracted from the M11 F6 L3 inline mutation at ``_inbound.py:663``).

History:

- M10 F05 L03 — original ``test_connectors_visibility_helper.py`` for
  the shared post-step visibility-tagging helper extracted from the
  F4 L4 dispatcher inline walk. The dispatcher's end-to-end tests in
  ``tests/test_connectors_inbound.py`` (and the e2e suites) remain
  the byte-identical regression net for the dispatcher-integration
  path; this file exercises the mutators at a single seam with
  synthetic ``Message`` lists so the rules block has fast, isolated
  coverage that the F5 L4 WS-storage-edge shim and the F7 L3
  channel-context binding can rely on.
- M11 F7 L1 — renamed from ``test_connectors_visibility_helper.py``
  to ``test_connectors_post_step_metadata.py`` alongside the n=3
  lift of the post-step mutators into a shared module. Added
  ``bind_peer_name`` coverage (four cases: USER-touch, non-USER-
  skip, None-peer_name semantic, AssertionError on wrong role).
"""

from __future__ import annotations

import pytest

from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
from the_one.connectors.base import DiscoverableEntities, DiscoverableEntity
from the_one.connectors.post_step_metadata import (
    bind_channel_context,
    bind_peer_name,
    resolve_channel_name,
    tag_post_step_visibility,
)
from the_one.llm.base import Message, ToolCall, ToolResult

# ─── tag_post_step_visibility: rule coverage ───────────────────────────


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


# ─── tag_post_step_visibility: mutation semantics ──────────────────────


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


# ─── bind_peer_name: M11 F7 L1 extracted from _inbound.py:663 ──────────


def test_bind_peer_name_binds_on_user_message_at_pre_step_len() -> None:
    """``bind_peer_name`` writes ``peer_name`` onto
    ``messages[pre_step_len]`` when that message is ``Role.USER``.

    This is the canonical case: ``Agent.step`` appends a USER
    message at the start of its loop, and the dispatcher binds the
    envelope's ``peer_name`` onto it post-step.
    """
    pre_user = Message.user("previous turn", peer_name="Bob")
    new_user = Message.user("new turn")
    messages = [pre_user, new_user]

    bind_peer_name(messages, pre_step_len=1, peer_name="Alice")

    # The USER message at pre_step_len picks up the peer_name.
    assert messages[1].peer_name == "Alice"
    # Pre-step history is untouched.
    assert messages[0].peer_name == "Bob"


def test_bind_peer_name_does_not_touch_non_user_messages_above_pre_step_len() -> None:
    """``bind_peer_name`` addresses ``messages[pre_step_len]`` exclusively;
    later messages (assistant replies, tool results) appended in the
    same turn are NOT touched.

    Pins the composition complement of ``tag_post_step_visibility``
    (which skips USER and touches everything else): the two mutators
    address disjoint slices and cannot conflict.
    """
    new_user = Message.user("new turn")
    assistant_reply = Message.assistant("reply")
    messages = [new_user, assistant_reply]

    bind_peer_name(messages, pre_step_len=0, peer_name="Alice")

    assert messages[0].peer_name == "Alice"
    # The assistant message later in the turn is NOT touched
    # (the dataclass default for ``peer_name`` is ``None``).
    assert messages[1].peer_name is None


def test_bind_peer_name_accepts_none_peer_name() -> None:
    """``peer_name=None`` is allowed: non-Discord plugins with no
    peer_name concept emit ``working_envelope.peer_name=None`` and
    the field stays at the dataclass default (``None``).

    Pins the no-op-semantically branch: assertion passes (role is
    USER), assignment writes ``None``, no exception.
    """
    new_user = Message.user("new turn")
    messages = [new_user]

    bind_peer_name(messages, pre_step_len=0, peer_name=None)

    assert messages[0].peer_name is None


def test_bind_peer_name_asserts_when_message_is_not_user() -> None:
    """``bind_peer_name`` asserts ``messages[pre_step_len].role ==
    Role.USER`` at runtime.

    This pins the agents.md-codified invariant
    (``post-step-dispatcher-message-metadata-binding`` composition
    rule on defensive ``assert`` pairing) so the contract survives
    ``python -O`` (which strips the runtime assert).
    """
    assistant = Message.assistant("not a user message")
    messages = [assistant]

    with pytest.raises(AssertionError):
        bind_peer_name(messages, pre_step_len=0, peer_name="Alice")


# ─── bind_channel_context: M11 F7 L3 ───────────────────────────────────


def test_bind_channel_context_binds_channel_id_and_channel_name() -> None:
    """``bind_channel_context`` writes both ``channel_id`` and
    ``channel_name`` onto ``messages[pre_step_len]`` when that
    message is ``Role.USER`` and both values are non-None.

    Canonical case: the envelope carries ``channel_id``, the F3 L4
    discoverable-entities cache resolved a ``channel_name``, and the
    dispatcher binds both onto the appended USER message post-step.
    """
    pre_user = Message.user("previous turn", channel_id="ch-old")
    new_user = Message.user("new turn")
    messages = [pre_user, new_user]

    bind_channel_context(
        messages,
        pre_step_len=1,
        channel_id="C123",
        channel_name="general",
    )

    # The USER message at pre_step_len picks up both fields.
    assert messages[1].channel_id == "C123"
    assert messages[1].channel_name == "general"
    # Pre-step history is untouched.
    assert messages[0].channel_id == "ch-old"
    assert messages[0].channel_name is None


def test_bind_channel_context_binds_channel_id_with_none_channel_name() -> None:
    """``channel_name=None`` is passed through as-is: the F3 L4 cache
    may be cold (snapshot None), uninitialized (cache None), or a
    miss (id not in cache.channels). The envelope still carries
    ``channel_id``, so the field is bound; ``channel_name`` stays None.

    Pins the partial-absence branch the L4 provider projection must
    handle gracefully.
    """
    new_user = Message.user("new turn")
    messages = [new_user]

    bind_channel_context(
        messages,
        pre_step_len=0,
        channel_id="C123",
        channel_name=None,
    )

    assert messages[0].channel_id == "C123"
    assert messages[0].channel_name is None


def test_bind_channel_context_raises_on_non_user_message() -> None:
    """``bind_channel_context`` asserts ``messages[pre_step_len].role ==
    Role.USER`` at runtime.

    Pins the agents.md-codified invariant
    (``post-step-dispatcher-message-metadata-binding`` composition
    rule on defensive ``assert`` pairing) so the contract survives
    ``python -O`` (which strips the runtime assert). Mirrors
    ``test_bind_peer_name_asserts_when_message_is_not_user`` — both
    USER-only mutators share the same defensive shape.
    """
    assistant = Message.assistant("not a user message")
    messages = [assistant]

    with pytest.raises(AssertionError):
        bind_channel_context(
            messages,
            pre_step_len=0,
            channel_id="C123",
            channel_name="general",
        )


def test_bind_channel_context_does_not_touch_non_user_messages() -> None:
    """``bind_channel_context`` addresses ``messages[pre_step_len]``
    exclusively; later messages (assistant replies, tool results)
    appended in the same turn are NOT touched.

    Pins the composition complement of ``tag_post_step_visibility``
    (which skips USER and touches everything else): the two mutators
    address disjoint slices and cannot conflict.
    """
    new_user = Message.user("new turn")
    assistant_reply = Message.assistant("reply")
    messages = [new_user, assistant_reply]

    bind_channel_context(
        messages,
        pre_step_len=0,
        channel_id="C123",
        channel_name="general",
    )

    assert messages[0].channel_id == "C123"
    assert messages[0].channel_name == "general"
    # The assistant message later in the turn is NOT touched
    # (the dataclass default for channel fields is ``None``).
    assert messages[1].channel_id is None
    assert messages[1].channel_name is None


# ─── resolve_channel_name: M11 F7 L3 helper ────────────────────────────


def test_resolve_channel_name_returns_label_on_match() -> None:
    """``resolve_channel_name`` walks ``cache.channels`` and returns
    the ``label`` of the entity whose ``id`` matches ``channel_id``.
    """
    cache = DiscoverableEntities(
        channels=[DiscoverableEntity(id="C123", label="general")]
    )
    assert resolve_channel_name(cache, "C123") == "general"


def test_resolve_channel_name_returns_none_on_miss() -> None:
    """When no channel entity matches ``channel_id``, the helper
    returns ``None`` (cache present but stale or platform-side
    channel created after the last refresh).
    """
    cache = DiscoverableEntities(
        channels=[DiscoverableEntity(id="C123", label="general")]
    )
    assert resolve_channel_name(cache, "C-missing") is None


def test_resolve_channel_name_returns_none_on_none_cache() -> None:
    """``cache=None`` (cold pool, plugin doesn't implement
    ``enumerate_discoverable_entities``, or the first refresh hasn't
    landed) → return ``None`` defensively without touching attributes.
    """
    assert resolve_channel_name(None, "C123") is None
