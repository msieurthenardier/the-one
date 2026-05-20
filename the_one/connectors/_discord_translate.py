"""Pure-function helper translating ``discord.Message`` → ``InboundEnvelope``.

M10 F8 L4 — sole entry point: :func:`_translate_discord_message_to_envelope`.

Lives in its own module (NOT inline in ``_discord.py``) per F7 debrief
Key Learning #1: pure-function modules with ``__all__`` are easier to
unit-test against recorded fixtures than against a connected gateway.
Mirrors the F7 L1 precedent at :mod:`the_one.connectors._commands` —
single private exported function, module-level ``__all__``, no I/O, no
logging beyond what the dataclass construction would do on its own,
deterministic on input.

**Thread/channel convention (revised at L4 cycle-1 design review)**:

- Top-level guild text-channel message: ``channel_id = message.channel.id``,
  ``thread_id = None``.
- Thread message: ``channel_id = message.channel.parent.id`` (PARENT
  channel), ``thread_id = message.channel.id`` (the thread's own id).
- DM channel: ``channel_id = message.channel.id`` (the DM channel id),
  ``thread_id = None``.

This preserves F3's ``(channel_id, thread_id)`` lookup tuple semantics
at ``_session.py:146-151`` ("this thread belongs to channel C"). The
earlier "redundant-channel_id" convention from the cycle-0 draft was
rejected at cycle-1.

**``raw`` dict contents**: ``is_dm`` (consumed by L6's DM-classification
hook), ``guild_id``, ``attachments`` (raw SDK dicts; pretty-printing
deferred to a later hardening leg), ``member_roles`` (string-cast role
ids — ``[]`` in DM context where ``author`` is ``User`` not ``Member``),
and ``discord_message`` (the raw SDK object reference, for any L5+
handler that needs richer access).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from the_one.connectors.base import InboundEnvelope

if TYPE_CHECKING:
    import discord

__all__ = ("_translate_discord_message_to_envelope",)


def _translate_discord_message_to_envelope(
    message: "discord.Message",
    account_id: str,
) -> InboundEnvelope:
    """Translate a ``discord.Message`` to the canonical :class:`InboundEnvelope`.

    Pure function: no I/O, no side effects, deterministic on input.

    ``channel_id`` / ``thread_id`` follow the F3-aligned convention
    described in the module docstring: for thread messages the
    ``channel_id`` is the PARENT channel id and ``thread_id`` is the
    thread's id; for guild text channels and DMs the ``channel_id`` is
    the channel's own id and ``thread_id`` is ``None``.

    ``peer_name`` uses ``message.author.display_name`` (NOT
    ``.name`` / ``.global_name``) — display_name reflects guild
    nickname when present and falls back to the global username, so
    it matches what peers see in the UI.

    Imports of :mod:`discord` are deferred to call time (``TYPE_CHECKING``
    block at module scope; ``import discord`` inside the function body
    so the module-level import graph stays clean and tests can pass
    synthetic mock-message objects without the SDK being installed).
    """
    import discord  # local import — see docstring

    channel = message.channel
    channel_type = getattr(channel, "type", None)
    is_thread = channel_type in (
        discord.ChannelType.public_thread,
        discord.ChannelType.private_thread,
    )
    is_dm = channel_type == discord.ChannelType.private

    if is_thread:
        # Thread: channel_id is the PARENT channel id (preserves F3's
        # "this thread belongs to channel C" semantic); thread_id is the
        # thread's own id.
        parent = channel.parent
        channel_id_str = str(parent.id) if parent is not None else str(channel.id)
        thread_id_str: str | None = str(channel.id)
    else:
        # Guild text channel OR DM: channel_id is the channel's own id;
        # thread_id is None.
        channel_id_str = str(channel.id)
        thread_id_str = None

    guild = getattr(message, "guild", None)
    guild_id_str: str | None = str(guild.id) if guild is not None else None

    attachments_raw = []
    for a in getattr(message, "attachments", ()) or ():
        # ``discord.Attachment.to_dict`` is the SDK-canonical projection.
        # Fall back to the attachment object itself when ``to_dict`` is
        # absent (test fixtures may pass plain dicts directly).
        to_dict = getattr(a, "to_dict", None)
        attachments_raw.append(to_dict() if callable(to_dict) else a)

    # ``message.author.roles`` exists on ``Member`` instances but NOT on
    # ``User`` (DMs and webhook messages). ``getattr`` with empty-default
    # collapses both branches.
    roles = getattr(message.author, "roles", []) or []
    member_roles = [str(r.id) for r in roles]

    return InboundEnvelope(
        platform="discord",
        account_id=account_id,
        channel_id=channel_id_str,
        thread_id=thread_id_str,
        peer_id=str(message.author.id),
        peer_name=message.author.display_name,
        text=message.content or "",
        raw={
            "is_dm": is_dm,
            "guild_id": guild_id_str,
            "attachments": attachments_raw,
            "member_roles": member_roles,
            "discord_message": message,
        },
    )
