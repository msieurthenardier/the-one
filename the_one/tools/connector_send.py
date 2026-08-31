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
"""

from __future__ import annotations

from typing import Any

from the_one.connectors.base import ChannelTarget, ConnectorClientError, PeerTarget
from the_one.tools.base import Tool

SEND_TO_PLATFORM_CHANNEL_TOOL_NAME = "send_to_platform_channel"
PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"


class SendToPlatformChannelTool(Tool):
    """Send a message to the external platform conversation this agent is bound to."""

    name = SEND_TO_PLATFORM_CHANNEL_TOOL_NAME
    description = (
        "Send a message to an external platform (Discord, etc. via a "
        "configured connector). Your plain-text replies in this session "
        "do NOT auto-reach the platform — only calling this tool "
        "delivers content to peers. Target EITHER a channel "
        "(connector_id + channel_id, optional thread_id) OR a DM "
        "(connector_id + peer_id) — never both. You may DM any "
        "allowlisted peer, including one you have not exchanged a "
        "message with yet (unprompted first contact is in-contract, "
        "bounded by the connector's allowlist)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "object",
                "properties": {
                    "connector_id": {"type": "string"},
                    "channel_id": {"type": ["string", "null"]},
                    "thread_id": {"type": ["string", "null"]},
                    "peer_id": {"type": ["string", "null"]},
                },
                "required": ["connector_id"],
            },
            "content": {"type": "string", "description": "The message body to deliver."},
        },
        "required": ["target", "content"],
    }

    async def execute(self, target: Any = None, content: Any = None, **_extra: Any) -> str:  # type: ignore[override]
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
