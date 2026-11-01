"""Inbound pipeline: admission → pairing → ``/new`` → reply policy →
session resolution → per-session-locked agent dispatch → auto-reply
mechanical fallback (DD-1, DD-3, DD-5, DD-6, DD-10). Platform gateway
listeners (spawned inside ``plugin.connect``) call :func:`dispatch_inbound`
for every message they receive; the manager's
:meth:`ConnectorManager._connect_once` wires this as the ``on_inbound``
callback for production connectors.

Explicitly OUT of scope (superseded by DD-2/DD-4/DD-6, unlike the
pre-reset ``_inbound.py``): no per-agent ACL, no routing engine, no
routing/audit log, no command-handler protocol beyond the single ``/new``
interception, no engagement-inference LLM gate.
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from the_one.agent._context import (
    TurnContext,
    TurnPeer,
    current_chat_session_id,
    current_turn,
)
from the_one.agent.factory import (
    AgentNotFoundError,
    ProviderNotConfiguredError,
    ProviderNotFoundError,
    get_factory,
)
from the_one.connectors.base import (
    ChannelTarget,
    InboundEnvelope,
    PeerTarget,
    SendTarget,
)
from the_one.connectors.delivery import (  # noqa: F401  (STEP_LIMIT_LINE re-exported)
    STEP_LIMIT_LINE,
    deliver_final_reply,
    send_step_limit_line,
)
from the_one.db.codec import decode_messages, encode_messages
from the_one.db.models import ChatSession, Connector, now_iso
from the_one.llm.base import Message, Role, tag_post_step_visibility
from the_one.sessions import broadcast_to_session, track_turn

if TYPE_CHECKING:
    from the_one.connectors.manager import ConnectorManager

logger = logging.getLogger(__name__)

_DEFAULT_CONTINUATION_SECONDS = 86400  # 24 hours
_CONTINUATION_ENV_VAR = "THE_ONE_SESSION_CONTINUATION_SECONDS"

# DD-10 (Mission 23 Flight 3, mid-flight amendment): the auto-reply skip
# rule needs the same two literals ``llm/base.py``'s
# ``tag_post_step_visibility`` hardcodes — the tool name and the
# platform-send success prefix, canonically owned by
# ``the_one/tools/connector_send.py``. Inlined here rather than imported:
# ``the_one/tools/`` depends on ``the_one/connectors/`` (``connector_send.py``
# imports ``ChannelTarget``/``ConnectorClientError``/``PeerTarget`` from
# ``connectors/base.py``), so ``connectors/`` importing back from ``tools/``
# would form a cycle — the same "assert, not import" layering call
# ``llm/base.py`` documents at its own inline-literal site. Agreement
# between all three copies (this module, ``llm/base.py``,
# ``tools/connector_send.py``) is pinned by
# ``tests/test_connector_send_tool.py::test_shared_constants_pin_inbound_literals``.
_SEND_TO_PLATFORM_CHANNEL_TOOL_NAME = "send_to_platform_channel"
_PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"


def _resolve_continuation_seconds(override: int | None = None) -> int:
    """Explicit ``override`` (per-connector) → env var (read at call time) → default."""
    if override is not None:
        return override
    raw = os.environ.get(_CONTINUATION_ENV_VAR)
    if raw is None:
        return _DEFAULT_CONTINUATION_SECONDS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an int; falling back to %d",
            _CONTINUATION_ENV_VAR,
            raw,
            _DEFAULT_CONTINUATION_SECONDS,
        )
        return _DEFAULT_CONTINUATION_SECONDS


def is_continuable(row: ChatSession, continuation_seconds: int, now: datetime) -> bool:
    """True when ``row`` may take another message: no ``/new`` ``ended_at`` sentinel,
    a parseable ``last_inbound_at`` (naive reads as UTC) younger than the window."""
    metadata = row.session_metadata or {}
    if "ended_at" in metadata or row.last_inbound_at is None:
        return False
    try:
        last = datetime.fromisoformat(row.last_inbound_at)
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last).total_seconds() < continuation_seconds


def is_admitted(connector: Connector, envelope: InboundEnvelope) -> bool:
    """Flat allowlist admission (DD-2/DD-3): peer OR channel on the allowlist."""
    allowlist = connector.config.get("allowlist") or {}
    peers = allowlist.get("peers") or []
    channels = allowlist.get("channels") or []
    return envelope.peer_id in peers or envelope.channel_id in channels


def should_reply(connector: Connector, envelope: InboundEnvelope) -> bool:
    """DD-6: reply iff DM, mention, or an always-listen channel. No engine."""
    if envelope.is_dm:
        return True
    if envelope.mentions_bot:
        return True
    always_listen = connector.config.get("always_listen") or []
    return envelope.channel_id in always_listen


async def _pair_peer(connector: Connector, peer_id: str, repo) -> None:
    """Append ``peer_id`` to ``allowlist.peers`` and persist (DD-3)."""
    config = dict(connector.config)
    allowlist = dict(config.get("allowlist") or {})
    peers = list(allowlist.get("peers") or [])
    if peer_id not in peers:
        peers.append(peer_id)
    allowlist["peers"] = peers
    config["allowlist"] = allowlist
    await repo.update(connector.model_copy(update={"config": config}))


async def _handle_new(connector: Connector, envelope: InboundEnvelope, chat_repo) -> None:
    """``/new``: write the ``ended_at`` sentinel on the matching session, if any."""
    existing = await chat_repo.find_most_recent_by_external_key(
        platform=envelope.platform,
        connector_id=connector.id,
        channel_id=envelope.channel_id,
        thread_id=envelope.thread_id,
    )
    if existing is not None:
        await chat_repo.set_session_metadata_key(existing.id, "ended_at", now_iso())


async def _session_title(envelope: InboundEnvelope, connector: Connector, dir_repo=None) -> str:
    """DD-7 (Mission 23 Flight 4): a channel session titles from the
    directory's ``display_name`` when an entry exists at CREATION time
    (a later directory update does NOT retro-rename an existing session —
    stated trade-off); else the raw channel id, as before. DM sessions are
    unchanged — the peer name was always known directly from the
    envelope, no directory lookup needed. ``dir_repo=None`` (test/back-
    compat callers that don't pass one) falls back to the pre-DD-7
    behavior unconditionally.
    """
    if envelope.is_dm:
        return f"DM: {envelope.peer_name}"
    if dir_repo is not None:
        entry = await dir_repo.get(connector.id, "channel", envelope.channel_id)
        if entry is not None:
            return entry.display_name
    return envelope.channel_id


async def resolve_session(
    envelope: InboundEnvelope,
    connector: Connector,
    chat_repo,
    dir_repo=None,
    *,
    agent_name: str,
) -> ChatSession:
    """Map an inbound envelope to its ``chat_sessions`` row (DD-5).

    Keyed on ``(platform, connector_id, channel_id, thread_id)``;
    ``peer_id`` is stored but not part of the lookup. Reuses the most
    recent matching row when within the continuation window AND it
    carries no ``/new``-written ``ended_at`` sentinel; otherwise creates
    a fresh row.

    ``dir_repo`` (Mission 23 Flight 4 DD-7, OPTIONAL — defaults ``None``
    for existing callers/tests that don't need directory-named titles) is
    threaded through to :func:`_session_title` for a fresh session's
    title only; it plays no role in the reuse lookup above.
    """
    continuation = _resolve_continuation_seconds(override=connector.session_continuation_seconds)
    existing = await chat_repo.find_most_recent_by_external_key(
        platform=envelope.platform,
        connector_id=connector.id,
        channel_id=envelope.channel_id,
        thread_id=envelope.thread_id,
    )
    if existing is not None and is_continuable(existing, continuation, datetime.now(timezone.utc)):
        return existing

    current_iso = now_iso()
    title = await _session_title(envelope, connector, dir_repo)
    new_session = ChatSession(
        id=uuid.uuid4().hex,
        agent_name=agent_name,
        title=title,
        messages="[]",
        created_at=current_iso,
        updated_at=current_iso,
        platform=envelope.platform,
        connector_id=connector.id,
        channel_id=envelope.channel_id,
        thread_id=envelope.thread_id,
        peer_id=envelope.peer_id,
        session_metadata=None,
        last_inbound_at=current_iso,
    )
    await chat_repo.create(new_session)
    return new_session


def _bind_peer_name(messages: list[Message], pre_step_len: int, peer_name: str) -> None:
    """Bind ``peer_name`` onto the USER message ``agent.step`` appended.

    Mirrors the pre-reset ``connectors/post_step_metadata.py::bind_peer_name``
    (removed whole-cloth in the Mission 23 Flight 1 backend-removal, along
    with the rest of that package) — the flight's own constraint forbids
    modifying ``agent/core.py`` to accept ``peer_name`` at message-append
    time, so the dispatcher binds it onto the just-appended message
    afterward, inside the same per-session lock ``dispatch_inbound`` already
    holds for the call. Without this, ``Message.user(envelope.text)`` (built
    internally by ``Agent.step``) always carries ``peer_name=None``, and the
    Chat UI has no attribution to render — the peer's inbound text becomes
    visually indistinguishable from the operator's own words.

    **Touches**: ``Role.USER`` only — the single message at
    ``messages[pre_step_len]``. **Skips**: every other role — this is the
    composition complement of :func:`the_one.llm.base.tag_post_step_visibility`,
    which skips ``Role.USER`` and touches every other role; the two mutators
    address disjoint slices of ``messages[pre_step_len:]`` and cannot
    conflict by construction.

    Asserts ``messages[pre_step_len].role == Role.USER`` so a future
    ``agent.step`` regression that fails to append a USER message surfaces
    here, not at the next consumer.
    """
    assert messages[pre_step_len].role == Role.USER, (
        "agent.step must append a Role.USER message at pre_step_len"
    )
    messages[pre_step_len].peer_name = peer_name


def _reply_target(envelope: InboundEnvelope, connector_id: str) -> SendTarget:
    """The originating target: a ``PeerTarget`` for a DM, else a ``ChannelTarget``."""
    if envelope.is_dm:
        return PeerTarget(connector_id, envelope.peer_id)
    return ChannelTarget(connector_id, envelope.channel_id, envelope.thread_id)


async def _send_step_limit_line(
    envelope: InboundEnvelope, connector_id: str, manager: "ConnectorManager"
) -> None:
    """M31 F6 leg 06 (DD8): tell the peer the agent stopped at its step limit.

    A neutral plain line to the same target and client as auto-delivery. NEVER
    raises (it runs after the persist, and a failure here must not cost the
    stored turn); with no client or on a send failure it is logged and dropped.
    Not stored: ``encode_messages`` has already run.
    """
    await send_step_limit_line(_reply_target(envelope, connector_id), connector_id, manager)


async def _auto_deliver_reply(
    messages: list[Message],
    pre_step_len: int,
    envelope: InboundEnvelope,
    connector_id: str,
    manager: "ConnectorManager",
) -> None:
    """DD-10: mechanically deliver the turn's final assistant text to the
    ORIGINATING target, so a reply reaches the peer independent of the
    model's tool-calling reliability.

    Called AFTER :func:`_bind_peer_name` and
    :func:`the_one.llm.base.tag_post_step_visibility` have run for this
    turn — every new message is already tagged ``OPERATOR_VISIBILITY``
    except a successful platform-send tool result, which
    ``tag_post_step_visibility`` already left peer-visible.

    Skip rule (no double-send): if any message at or after
    ``pre_step_len`` is a ``Role.TOOL`` result whose parent tool call is
    ``send_to_platform_channel`` and whose content starts with the
    platform-send success prefix, the agent already spoke to the platform
    deliberately this turn — no auto-delivery, full stop (even if that
    tool-send targeted a DIFFERENT channel; DD-10's recorded trade-off).

    Otherwise, the turn's FINAL ``Role.ASSISTANT`` message is the
    candidate. Non-empty text content is delivered via
    ``manager.client_for(connector_id).send()`` to
    ``PeerTarget(connector_id, peer_id)`` (DM) or
    ``ChannelTarget(connector_id, channel_id, thread_id)`` (channel). On
    success the message's ``visibility`` is flipped to ``None``
    (peer-visible) IN PLACE — the caller persists ``messages`` right
    after this returns, so the stored history reflects the delivery. On
    any failure (no live client, ``ConnectorClientError``, or any other
    exception from ``send()``) the failure is logged and
    ``visibility`` is left as ``tag_post_step_visibility`` set it
    (operator-only) — no retry, no raise; the caller's persist still
    happens.
    """
    await deliver_final_reply(
        messages, pre_step_len, _reply_target(envelope, connector_id), connector_id, manager
    )


def _resolve_agent_name(connector: Connector, envelope: InboundEnvelope) -> str | None:
    """DD-2: channel_map entry for a channel target, else default_agent. DMs
    never consult channel_map — the default agent is the sole DM recipient."""
    if not envelope.is_dm:
        channel_map = connector.config.get("channel_map") or {}
        mapped = channel_map.get(envelope.channel_id)
        if mapped:
            return mapped
    return connector.config.get("default_agent")


async def dispatch_inbound(
    connector_id: str,
    envelope: InboundEnvelope,
    *,
    manager: "ConnectorManager",
) -> None:
    """Run one inbound envelope through the full pipeline.

    Errors at the connector-load stage are logged and swallowed — a
    connector-layer failure does not take the agent runtime down.
    ``factory.create`` / ``agent.step`` errors are also caught and logged
    here (the manager's ``on_inbound`` wrapper provides a second layer of
    the same defense; both are kept since this function has direct unit
    test coverage that does not go through the manager).
    """
    from the_one.config import settings
    from the_one.db.connection import get_connection
    from the_one.db.repositories import (
        ChatSessionRepository,
        ConnectorDirectoryRepository,
        ConnectorRepository,
    )
    from the_one.encryption import get_encryptor

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    conn_repo = ConnectorRepository(conn, encryptor)
    chat_repo = ChatSessionRepository(conn)
    dir_repo = ConnectorDirectoryRepository(conn)

    try:
        connector = await conn_repo.get(connector_id)
    except KeyError:
        logger.warning("dispatch_inbound: connector %s not found", connector_id)
        return

    if not is_admitted(connector, envelope):
        # Unknown sender: silence, nothing persisted — EXCEPT the one
        # narrow case of a correct pairing code, which persists the
        # allowlist append and nothing else (DD-3).
        if envelope.is_dm and manager.consume_pairing_code(connector_id, envelope.text.strip()):
            await _pair_peer(connector, envelope.peer_id, conn_repo)
        return

    # DD-4 (Mission 23 Flight 4): record every ADMITTED envelope's peer
    # into the directory — immediately after admission, BEFORE the
    # ``/new`` and ``should_reply`` early returns below, so a peer who
    # says ``/new`` or speaks in a channel the reply policy ignores is
    # still observed (design review 2026-09-02: "every admitted envelope"
    # means every admitted envelope). The silence guarantee for
    # UNadmitted traffic holds because the admission check above already
    # returned. Fallback chain mirrors the edge case: peer_name, else the
    # platform-supplied username, else the raw peer id — never an
    # empty-string name in the directory.
    display_name = envelope.peer_name or envelope.peer_username or envelope.peer_id
    await dir_repo.upsert(
        connector_id=connector_id,
        kind="peer",
        platform_id=envelope.peer_id,
        thread_id=None,
        display_name=display_name,
        username=envelope.peer_username,
    )

    if envelope.text.strip() == "/new":
        await _handle_new(connector, envelope, chat_repo)
        return

    if not should_reply(connector, envelope):
        return

    agent_name = _resolve_agent_name(connector, envelope)
    if not agent_name:
        logger.warning("dispatch_inbound: connector %s has no default_agent", connector_id)
        return

    factory = get_factory()
    if factory is None:
        logger.warning("dispatch_inbound: no application factory installed; dropping inbound")
        return

    session_row = await resolve_session(
        envelope, connector, chat_repo, dir_repo, agent_name=agent_name
    )

    try:
        async with track_turn(session_row.id) as turn:
            await chat_repo.update_last_inbound(session_row.id, now_iso())
            try:
                agent = await factory.create(agent_name)
            except (AgentNotFoundError, ProviderNotFoundError, ProviderNotConfiguredError):
                logger.exception("dispatch_inbound: failed to build agent %r", agent_name)
                return
            except Exception:
                # Any other build failure (sortie 07 DD7): logged with the agent name;
                # there is no reply to the peer.
                logger.exception("dispatch_inbound: failed to build agent %r", agent_name)
                return

            db_session = await chat_repo.get(session_row.id)
            stored = decode_messages(db_session.messages)
            if stored:
                non_system = [m for m in stored if m.role != Role.SYSTEM]
                agent.messages = agent.messages[:1] + non_system

            turn.ran = True
            pre_step_len = len(agent.messages)
            hit_step_limit = False
            token = current_chat_session_id.set(session_row.id)
            # M27 F2 DD5: the peer whose message starts this turn (notes taint/origin).
            turn_token = current_turn.set(
                TurnContext(
                    peer=TurnPeer(
                        platform=envelope.platform,
                        connector_id=connector_id,
                        peer_id=envelope.peer_id,
                        peer_name=envelope.peer_name,
                    ),
                    session_id=session_row.id,
                )
            )
            try:
                async for _ in agent.step(envelope.text):
                    pass
                # DD8 F2: capture once, right after the turn's own loop.
                hit_step_limit = bool(agent.stopped_at_step_limit)
                _bind_peer_name(agent.messages, pre_step_len, envelope.peer_name)
                tag_post_step_visibility(agent.messages, pre_step_len)
                await _auto_deliver_reply(
                    agent.messages, pre_step_len, envelope, connector_id, manager
                )
                encoded = encode_messages(agent.messages)
                updated = db_session.model_copy(update={"messages": encoded})
                await chat_repo.update(updated)
            except Exception:
                logger.exception(
                    "dispatch_inbound: agent.step failed for session %s", session_row.id
                )
            else:
                # After the persist, so a send failure can never cost the turn.
                if hit_step_limit:
                    await _send_step_limit_line(envelope, connector_id, manager)
            finally:
                current_turn.reset(turn_token)
                current_chat_session_id.reset(token)
    finally:
        # DD5: tell the chat's subscribers the stored history may have changed,
        # after the lock is released (every exit path once a session is resolved).
        with contextlib.suppress(Exception):
            await broadcast_to_session(
                session_row.id, {"type": "session_updated", "session_id": session_row.id}
            )
