"""Built-in ``fetch_channel_history`` tool — last-N platform messages (DD-8).

Calls the OPTIONAL ``ConnectorClient.history`` hook (discovered via
``getattr``, not declared on the Protocol — plugins without it get a
clean "not supported" result). Same binding-derived authorization as
``connector_send.py`` — an agent may only read history for a target it
could also send to.
"""

from __future__ import annotations

from typing import Any

from the_one.connectors.base import ChannelTarget, ConnectorClientError, PeerTarget
from the_one.tools.base import Tool

FETCH_CHANNEL_HISTORY_TOOL_NAME = "fetch_channel_history"


class FetchChannelHistoryTool(Tool):
    """Fetch the last N messages from a platform channel or DM, when supported."""

    name = FETCH_CHANNEL_HISTORY_TOOL_NAME
    summary = "Reads recent messages from a chat platform channel."
    description = (
        "Fetch the most recent messages from an external platform channel "
        "or DM this agent is bound to. Not every connector supports "
        "history — a clean message is returned when it doesn't."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "object",
                "properties": {
                    "connector_id": {"type": "string"},
                    "channel_id": {"type": ["string", "null"]},
                    "peer_id": {"type": ["string", "null"]},
                },
                "required": ["connector_id"],
            },
            "limit": {"type": "integer", "description": "Max messages to return.", "default": 20},
        },
        "required": ["target"],
    }

    async def execute(self, target: Any = None, limit: Any = 20, **_extra: Any) -> str:  # type: ignore[override]
        if not isinstance(target, dict):
            return "[error] target must be an object"
        connector_id = target.get("connector_id")
        if not isinstance(connector_id, str) or not connector_id:
            return "[error] target.connector_id must be a non-empty string"
        channel_id = target.get("channel_id") or None
        peer_id = target.get("peer_id") or None
        if bool(channel_id) == bool(peer_id):
            return "[error] target must set exactly one of channel_id or peer_id"
        if not isinstance(limit, int) or limit <= 0:
            limit = 20

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
            history_target: Any = ChannelTarget(connector_id=connector_id, channel_id=channel_id)
        else:
            authorized_agent = connector.config.get("default_agent")
            allowlist_peers = (connector.config.get("allowlist") or {}).get("peers") or []
            if peer_id not in allowlist_peers:
                return f"[error] [constraint] peer_id {peer_id!r} is not on the allowlist"
            history_target = PeerTarget(connector_id=connector_id, peer_id=peer_id)

        if not authorized_agent or self._agent_name != authorized_agent:
            return (
                f"[error] [constraint] agent {self._agent_name!r} is not authorized for "
                f"connector {connector_id!r} on this target"
            )

        manager = get_manager()
        client = manager.client_for(connector_id) if manager is not None else None
        if client is None:
            return f"[error] [constraint] connector {connector_id!r} is not connected"

        history_fn = getattr(client, "history", None)
        if history_fn is None:
            return f"[not supported] connector {connector_id!r} does not support history"
        try:
            messages = await history_fn(history_target, limit)
        except ConnectorClientError as exc:
            return f"[error] {type(exc).__name__}: {exc}"
        if not messages:
            return "No messages found."
        lines = [f"{m.peer_name} ({m.ts}): {m.content}" for m in messages]
        return "\n".join(lines)
