"""Tests for ``the_one/connectors/_discord_translate.py``.

M10 F8 L4 — pure-function translation tests. Synthetic mock
``discord.Message`` objects exercise the helper in isolation; no SDK
gateway, no network. Each scenario pins a single behavior of the
:func:`_translate_discord_message_to_envelope` helper against the
``InboundEnvelope`` shape declared at ``the_one/connectors/base.py``.

Discord's ``ChannelType`` constants are stubbed onto a fake ``discord``
module the helper imports lazily (``import discord`` inside the
function body), so we monkeypatch ``the_one.connectors._discord_translate``
to read our stub.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from the_one.connectors import _discord_translate as translate_mod
from the_one.connectors._discord_translate import (
    _translate_discord_message_to_envelope,
)


# ─────────────────────────────────────────────────────────────────
# Stub ``discord`` module (mirrors the surface the helper touches)
# ─────────────────────────────────────────────────────────────────


class _StubChannelType:
    """Sentinel enum-likes covering the three channel types the helper inspects."""

    text = "text"
    public_thread = "public_thread"
    private_thread = "private_thread"
    private = "private"


class _StubDiscordModule:
    ChannelType = _StubChannelType


@pytest.fixture(autouse=True)
def _patch_discord_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the local ``import discord`` site inside the helper.

    The helper does ``import discord`` inside the function body, so the
    interpreter resolves ``discord`` via the normal import machinery. We
    install our stub into ``sys.modules`` under the name ``discord`` so
    the in-function import binds to our stub.
    """
    import sys

    monkeypatch.setitem(sys.modules, "discord", _StubDiscordModule)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _make_role(role_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=role_id)


def _make_attachment(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(to_dict=lambda: payload)


def _make_author(
    *,
    author_id: int = 4242,
    display_name: str = "Alice",
    is_bot: bool = False,
    roles: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    kwargs: dict[str, Any] = {
        "id": author_id,
        "display_name": display_name,
        "bot": is_bot,
    }
    # Conditionally attach roles so the "DM author lacks roles" scenario
    # can simulate a ``User`` (vs ``Member``) instance accurately.
    if roles is not None:
        kwargs["roles"] = roles
    return SimpleNamespace(**kwargs)


def _make_guild_channel(channel_id: int = 1001) -> SimpleNamespace:
    return SimpleNamespace(id=channel_id, type=_StubChannelType.text, parent=None)


def _make_thread_channel(
    *,
    thread_id: int = 2002,
    parent_channel_id: int = 1001,
    thread_kind: str = _StubChannelType.public_thread,
) -> SimpleNamespace:
    parent = SimpleNamespace(id=parent_channel_id, type=_StubChannelType.text)
    return SimpleNamespace(id=thread_id, type=thread_kind, parent=parent)


def _make_dm_channel(channel_id: int = 9999) -> SimpleNamespace:
    return SimpleNamespace(id=channel_id, type=_StubChannelType.private, parent=None)


def _make_message(
    *,
    author: SimpleNamespace,
    channel: SimpleNamespace,
    content: str = "hello there",
    attachments: list[SimpleNamespace] | None = None,
    guild_id: int | None = 7777,
) -> SimpleNamespace:
    guild = SimpleNamespace(id=guild_id) if guild_id is not None else None
    return SimpleNamespace(
        author=author,
        channel=channel,
        content=content,
        attachments=list(attachments or []),
        guild=guild,
    )


# ─────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────


def test_guild_text_channel_translation() -> None:
    """Top-level guild text-channel message → envelope with channel_id set, thread_id None."""
    author = _make_author(roles=[_make_role(11), _make_role(22)])
    channel = _make_guild_channel(channel_id=1001)
    msg = _make_message(author=author, channel=channel, content="hi")

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.platform == "discord"
    assert env.account_id == "acct-1"
    assert env.channel_id == "1001"
    assert env.thread_id is None
    assert env.peer_id == "4242"
    assert env.peer_name == "Alice"
    assert env.text == "hi"
    assert env.raw["is_dm"] is False
    assert env.raw["guild_id"] == "7777"
    assert env.raw["member_roles"] == ["11", "22"]
    assert env.raw["discord_message"] is msg


def test_thread_translation_pins_parent_channel_id_convention() -> None:
    """Thread message: channel_id = PARENT channel id; thread_id = thread's id."""
    author = _make_author()
    channel = _make_thread_channel(thread_id=2002, parent_channel_id=1001)
    msg = _make_message(author=author, channel=channel, content="threaded reply")

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    # The F3-aligned convention: channel_id stays at the parent, thread_id
    # carries the thread's own id. The (channel_id, thread_id) tuple at
    # _session.py:146-151 then disambiguates the binding inside the
    # parent channel.
    assert env.channel_id == "1001"
    assert env.thread_id == "2002"


def test_private_thread_translation() -> None:
    """Private threads follow the same channel_id/thread_id rule as public threads."""
    author = _make_author()
    channel = _make_thread_channel(
        thread_id=3003,
        parent_channel_id=1001,
        thread_kind=_StubChannelType.private_thread,
    )
    msg = _make_message(author=author, channel=channel, content="psst")

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.channel_id == "1001"
    assert env.thread_id == "3003"


def test_dm_translation_sets_is_dm_and_clears_guild() -> None:
    """DM channel: is_dm=True, guild_id=None, channel_id = DM channel id, thread_id None."""
    author = _make_author()  # no .roles attribute when not a Member
    channel = _make_dm_channel(channel_id=9999)
    msg = _make_message(
        author=author, channel=channel, content="dm content", guild_id=None
    )

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.channel_id == "9999"
    assert env.thread_id is None
    assert env.raw["is_dm"] is True
    assert env.raw["guild_id"] is None
    # author has no ``.roles`` attribute → empty list (NOT a crash).
    assert env.raw["member_roles"] == []


def test_empty_text_image_only_message() -> None:
    """Image-only message (empty content): envelope.text == "" is acceptable."""
    author = _make_author()
    channel = _make_guild_channel()
    attachment = _make_attachment({"id": "att-1", "filename": "img.png"})
    msg = _make_message(author=author, channel=channel, content="", attachments=[attachment])

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.text == ""
    # And the attachments dropped into raw verbatim via to_dict().
    assert env.raw["attachments"] == [{"id": "att-1", "filename": "img.png"}]


def test_peer_name_uses_display_name_not_global_name() -> None:
    """peer_name reads display_name (the guild-nickname-aware value)."""
    # Even when the underlying user has a different .name/global_name, the
    # helper must use display_name so it matches what peers see in the UI.
    author = SimpleNamespace(
        id=4242,
        display_name="Nick-in-server",
        name="raw-username",  # SDK exposes this too but we IGNORE it.
        bot=False,
        roles=[],
    )
    channel = _make_guild_channel()
    msg = _make_message(author=author, channel=channel)

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.peer_name == "Nick-in-server"


def test_attachments_captured_in_raw() -> None:
    """Attachments land in raw['attachments'] as the SDK to_dict projection."""
    author = _make_author()
    channel = _make_guild_channel()
    msg = _make_message(
        author=author,
        channel=channel,
        attachments=[
            _make_attachment({"id": "a-1", "filename": "first.png"}),
            _make_attachment({"id": "a-2", "filename": "second.txt"}),
        ],
    )

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.raw["attachments"] == [
        {"id": "a-1", "filename": "first.png"},
        {"id": "a-2", "filename": "second.txt"},
    ]


def test_member_roles_empty_when_no_guild_context() -> None:
    """DM messages have no member-roles surface — ``getattr`` collapses to []."""
    # Author is a User (no .roles attribute) — DM context.
    author = SimpleNamespace(id=4242, display_name="Alice", bot=False)
    channel = _make_dm_channel()
    msg = _make_message(author=author, channel=channel, guild_id=None)

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.raw["member_roles"] == []


def test_raw_carries_discord_message_reference() -> None:
    """The raw SDK message object is preserved in raw['discord_message']."""
    author = _make_author()
    channel = _make_guild_channel()
    msg = _make_message(author=author, channel=channel)

    env = _translate_discord_message_to_envelope(msg, account_id="acct-1")

    assert env.raw["discord_message"] is msg


def test_helper_is_pure_function_no_mutation() -> None:
    """The helper does not mutate its inputs."""
    author = _make_author(roles=[_make_role(11)])
    channel = _make_guild_channel()
    attachments = [_make_attachment({"id": "att-1"})]
    msg = _make_message(author=author, channel=channel, attachments=attachments)

    # Snapshot the input identities + attribute values.
    pre_author_id = author.id
    pre_attachments_len = len(msg.attachments)
    pre_channel_id = channel.id

    _translate_discord_message_to_envelope(msg, account_id="acct-1")
    _translate_discord_message_to_envelope(msg, account_id="acct-2")

    # No mutation.
    assert author.id == pre_author_id
    assert len(msg.attachments) == pre_attachments_len
    assert channel.id == pre_channel_id
