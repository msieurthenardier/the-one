"""Built-in platform-send tool — the agent-side outbound entry point.

Mission 23 Flight 2 Leg 1 (DD-4). Registered like every other built-in in
``tools/builtins.py`` — no factory carve-out, no auto-attach; the agent
loop (``agent/core.py``, ``agent/factory.py``) is untouched. Authorization
is binding-derived and evaluated at ``execute()`` time against the live
``Connector`` row: a channel target is only sendable by the agent that
would RECEIVE inbound from it (``channel_map`` entry, else
``default_agent``); a DM target is only sendable by ``default_agent``, and
only to an allowlisted peer. ``channel_map`` never applies to DM targets.

``SEND_TO_PLATFORM_CHANNEL_TOOL_NAME`` and ``PLATFORM_SEND_OK_PREFIX`` are
the single source of truth for the two literals ``llm/base.py``'s
``tag_post_step_visibility`` also needs (Flight 1 debrief landmine) — a
pin test (``tests/test_connector_send_tool.py``) asserts the two modules
agree, since ``llm/base.py`` does not import ``tools/`` (layering).

**DD-11 (Mission 23 Flight 3, mid-flight amendment)**: ``target`` is
OPTIONAL. When omitted, :meth:`SendToPlatformChannelTool._resolve_default_target`
resolves a target from ``current_chat_session_id`` (`agent/_context.py`) →
the current ``chat_sessions`` row's keying columns via
``connectors/base.py::keying_to_target`` (Mission 23 Flight 4 DD-8
extraction — this used to be an independent inline implementation; it now
consumes the shared helper, behavior-preserving). A non-connector session
or no session context at all is a clear error, never a guess. The
resolved default is folded into the SAME dict shape an explicit ``target``
argument takes, so it flows through the existing parsing +
binding-derived authorization below completely unchanged — a defaulted
target is authorized exactly like an explicit one.
"""

from __future__ import annotations

from typing import Any

from the_one.connectors.base import (
    ChannelTarget,
    ConnectorClientError,
    PeerTarget,
    keying_to_target,
)
from the_one.tools.base import Tool

SEND_TO_PLATFORM_CHANNEL_TOOL_NAME = "send_to_platform_channel"
PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"


class SendToPlatformChannelTool(Tool):
    """Send a message to the external platform conversation this agent is bound to."""

    name = SEND_TO_PLATFORM_CHANNEL_TOOL_NAME
    summary = "Sends a message to a chat platform channel."
    description = (
        "Send a message to an external platform (Discord, etc. via a "
        "configured connector). Your plain-text replies in this session "
        "do NOT auto-reach the platform — only calling this tool "
        "delivers content to peers. Target EITHER a channel "
        "(connector_id + channel_id, optional thread_id) OR a DM "
        "(connector_id + peer_id) — never both; omit target entirely to "
        "send to the platform conversation this session is bound to "
        "(resolved from the session's own connector/channel/peer "
        "binding — errors if this session isn't bound to one). You may "
        "DM any allowlisted peer, including one you have not exchanged a "
        "message with yet (unprompted first contact is in-contract, "
        "bounded by the connector's allowlist)."
    )
    # DD-11: ``content`` is declared FIRST — ``required`` must be a prefix
    # of declared property order (``test_tool_base.py``'s
    # ``TestBuiltinRequiredFirstAgreesWithDeclarationOrder``, the
    # declaration-order positional-binding invariant for degraded models).
    # Now that only ``content`` is required, it has to lead; ``target``
    # (optional) follows.
    parameters = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The message body to deliver."},
            "target": {
                "type": "object",
                "description": (
                    "Explicit destination. Omit this field entirely to send "
                    "to the platform conversation this session is bound to."
                ),
                "properties": {
                    "connector_id": {"type": "string"},
                    "channel_id": {"type": ["string", "null"]},
                    "thread_id": {"type": ["string", "null"]},
                    "peer_id": {"type": ["string", "null"]},
                },
                "required": ["connector_id"],
            },
        },
        "required": ["content"],
    }

    async def _resolve_default_target(self) -> dict[str, Any] | str:
        """DD-11: resolve an omitted ``target`` from the current session's
        platform binding. Returns either a dict shaped like an explicit
        ``target`` argument (so the caller can fall straight into the
        existing parsing/authorization path) or an ``[error] ...`` string.
        """
        from the_one.agent._context import current_chat_session_id
        from the_one.db.connection import get_connection
        from the_one.db.repositories import ChatSessionRepository

        session_id = current_chat_session_id.get()
        if session_id is None:
            return "[error] [constraint] no target given and no active session context"

        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        try:
            session = await chat_repo.get(session_id)
        except KeyError:
            return "[error] [constraint] no target given and no active session context"

        # DD-8 extraction: the keying decision itself lives in
        # ``keying_to_target`` (``connectors/base.py``) — a ``None`` covers
        # BOTH the non-connector-bound case and the degenerate
        # connector-bound-but-keyless case, and this call site renders the
        # one error string for either (the error-path handoff pinned at
        # design review).
        target = keying_to_target(session)
        if target is None:
            return (
                "[error] [constraint] this session is not bound to a platform "
                "conversation; pass target explicitly"
            )
        if isinstance(target, ChannelTarget):
            return {
                "connector_id": target.connector_id,
                "channel_id": target.channel_id,
                "thread_id": target.thread_id,
            }
        return {"connector_id": target.connector_id, "peer_id": target.peer_id}

    async def execute(self, target: Any = None, content: Any = None, **_extra: Any) -> str:  # type: ignore[override]
        if target is None:
            resolved = await self._resolve_default_target()
            if isinstance(resolved, str):
                return resolved
            target = resolved

        if not isinstance(target, dict):
            return "[error] target must be an object"
        connector_id = target.get("connector_id")
        if not isinstance(connector_id, str) or not connector_id:
            return "[error] target.connector_id must be a non-empty string"
        channel_id = target.get("channel_id") or None
        peer_id = target.get("peer_id") or None
        thread_id = target.get("thread_id") or None
        if bool(channel_id) == bool(peer_id):
            return "[error] target must set exactly one of channel_id or peer_id"
        if not isinstance(content, str):
            return "[error] content must be a string"

        from the_one.config import settings
        from the_one.connectors.manager import get_manager
        from the_one.db.connection import get_connection
        from the_one.db.repositories import ConnectorRepository
        from the_one.encryption import get_encryptor

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        repo = ConnectorRepository(conn, encryptor)
        try:
            connector = await repo.get(connector_id)
        except KeyError:
            return f"[error] [constraint] connector_id {connector_id!r} not found"

        if channel_id is not None:
            channel_map = connector.config.get("channel_map") or {}
            authorized_agent = channel_map.get(channel_id) or connector.config.get("default_agent")
            send_target: Any = ChannelTarget(
                connector_id=connector_id, channel_id=channel_id, thread_id=thread_id
            )
        else:
            authorized_agent = connector.config.get("default_agent")
            allowlist_peers = (connector.config.get("allowlist") or {}).get("peers") or []
            if peer_id not in allowlist_peers:
                return f"[error] [constraint] peer_id {peer_id!r} is not on the allowlist"
            send_target = PeerTarget(connector_id=connector_id, peer_id=peer_id)

        if not authorized_agent or self._agent_name != authorized_agent:
            return (
                f"[error] [constraint] agent {self._agent_name!r} is not authorized to "
                f"send via connector {connector_id!r} for this target"
            )

        manager = get_manager()
        client = manager.client_for(connector_id) if manager is not None else None
        if client is None:
            return f"[error] [constraint] connector {connector_id!r} is not connected"

        try:
            result = await client.send(send_target, content)
        except ConnectorClientError as exc:
            return f"[error] {type(exc).__name__}: {exc}"

        dest = (
            f"{connector_id}:{channel_id}"
            if channel_id is not None
            else f"{connector_id} DM {peer_id}"
        )
        msg_id = result.platform_message_id
        return f"{PLATFORM_SEND_OK_PREFIX} sent to {dest}: {content!r} (msg_id={msg_id})"
