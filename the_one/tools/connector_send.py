"""Built-in platform-send tool — the agent-side outbound entry point.

Mission 10 Flight 4 Leg 2. Registered in :data:`the_one.tools.builtins._TOOL_CLASSES`
so it surfaces in the existing built-in-tools admin grid; operator
enable/disable lives at :class:`ToolConfigRepository.enabled`.

The tool delivers content to the external platform via the F1 pool's
``acquire`` → ``client.send`` path. Validation in :meth:`execute`
covers shape (the JSON Schema layer is permissive at the LLM boundary
but defensive validation here protects the pool from malformed inputs)
and account-scope (``target.account_id`` must be in the agent's attached
set). Channel/per-agent ACLs are consulted at execute time via a
per-call account fetch (M10 F6 L3); default-permit on absence.

M10 F6 L7 HAT — allowlist/ACL semantic redesign (canonical home of
the pure-function ACL logic is :mod:`the_one.connectors._acl`, since
M10 F7 L2; this module delegates to ``admits_outbound``):
  * Account-scope ``allowlist.channels = []`` now PERMITS all channels
    (was: deny everyone). The "empty = unrestricted" rule applies on
    both the account-scope axis and per-agent ACL ``None``/inherit case.
  * Per-agent ``channels: None`` inherits account-scope.
  * Per-agent ``channels: []`` is the "DMs-only" sentinel — F8 will
    ship DM classification; until then this fails closed on outbound.
  * Per-agent ``channels: [items]`` narrows to those channels.

Success returns a :data:`PLATFORM_SEND_OK_PREFIX`-prefixed string that
the F4-leg-4 dispatcher visibility-tagger consumes to decide
``visibility=None`` on the tool_result message. Failure returns a
standard ``[error] ...`` envelope.
"""

from __future__ import annotations

from typing import Any

from the_one.connectors import PLATFORM_SEND_OK_PREFIX
from the_one.connectors._pool import acquire as pool_acquire
from the_one.connectors._pool import connector_acquire
from the_one.connectors.base import OutboundTarget
from the_one.connectors.errors import ConnectorClientError, ConnectorRegistrationError
from the_one.tools.base import Tool


class SendToPlatformChannelTool(Tool):
    """Send a message to the external platform conversation this agent
    is attached to via a connector account."""

    name = "send_to_platform_channel"
    description = (
        "Send a message to the external platform conversation this "
        "agent is attached to (Discord, Slack, etc. via the configured "
        "connector account). Use this to reply to peer messages on the "
        "platform. Your plain-text replies in this session do NOT "
        "auto-reach the platform — only invocations of this tool "
        "deliver content to peers. The target identifies the "
        "destination (account_id from the attached set, channel_id "
        "from the inbound you're responding to, and an optional "
        "thread_id for thread-scoped replies)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": (
                            "The connector account id to send through. "
                            "Must be one of the accounts attached to "
                            "this agent."
                        ),
                    },
                    "channel_id": {
                        "type": "string",
                        "description": (
                            "Platform-native channel id (Discord "
                            "channel snowflake, Slack channel id). "
                            "Typically copied from the inbound "
                            "envelope this reply responds to."
                        ),
                    },
                    "thread_id": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional thread id for thread-scoped "
                            "replies. Null/absent posts in the channel."
                        ),
                    },
                },
                "required": ["account_id", "channel_id"],
            },
            "content": {
                "type": "string",
                "description": "The message body to deliver.",
            },
        },
        "required": ["target", "content"],
    }

    def __init__(
        self,
        config: Any = None,
        cross_configs: dict[type, object] | None = None,
        agent_name: str | None = None,
        connector_account_ids: list[str] | None = None,
        connector_acls: dict[str, dict[str, list[str] | None]] | None = None,
    ) -> None:
        # All kwargs default to None so `cls()` works on the
        # `/api/tools` introspection path (BuiltinToolProvider.get_tools
        # at builtins.py:104-105 constructs every tool zero-arg there).
        super().__init__(config, cross_configs, agent_name)
        self._connector_account_ids: list[str] = connector_account_ids or []
        self._connector_acls: dict[str, dict[str, list[str] | None]] | None = (
            connector_acls
        )

    async def execute(self, target: Any = None, content: Any = None, **_extra: Any) -> str:  # type: ignore[override]
        # `**_extra` defensively accepts unexpected kwargs from the LLM
        # tool-call dispatch — silently ignored. Matches the web/filesystem
        # tool convention; harder against schema-vs-call-time drift.
        # ── Target-shape validation ────────────────────────────────
        if not isinstance(target, dict):
            return "[error] target must be an object with account_id and channel_id"
        account_id = target.get("account_id")
        channel_id = target.get("channel_id")
        if not isinstance(account_id, str) or not account_id:
            return "[error] target.account_id must be a non-empty string"
        if not isinstance(channel_id, str) or not channel_id:
            return "[error] target.channel_id must be a non-empty string"
        thread_id = target.get("thread_id")
        if thread_id is not None and not isinstance(thread_id, str):
            return "[error] target.thread_id must be a string or null"
        # Coerce empty-string thread_id to None — operator intent is
        # "no thread" and downstream platforms reject empty thread ids.
        thread_id = thread_id or None
        if not isinstance(content, str):
            return "[error] content must be a string"

        # ── Account-scope validation ───────────────────────────────
        if account_id not in self._connector_account_ids:
            return (
                f"[error] [constraint] account_id {account_id!r} is "
                f"not attached to this agent"
            )

        # ── Channel + per-agent ACL consultation (M10 F6 L3) ───────
        # Function-local imports — adopted defensively by symmetry with
        # connectors/_inbound.py:130-142 (the existing precedent for the
        # connectors→db boundary). A cycle is NOT observed in tools/
        # connector_send.py's current import graph; the convention is
        # adopted prophylactically because per-call account fetches will
        # multiply this module's coupling to db.repositories over time.
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.db.repositories import ConnectorAccountRepository
        from the_one.encryption import get_encryptor

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        try:
            account = await acc_repo.get(account_id)
        except KeyError:
            return (
                f"[error] [constraint] account_id {account_id!r} "
                "not found"
            )

        # M10 F7 L2: ACL admission extracted to connectors/_acl.py — single
        # pure function consumed by both outbound (here) and inbound (F7 L5
        # dispatcher). Per-axis tri-state semantic unchanged from F6 L7 HAT.
        from the_one.connectors._acl import admits_outbound

        agent_acl: dict[str, list[str] | None] | None = (
            self._connector_acls.get(account_id)
            if self._connector_acls is not None
            else None
        )
        admits, reason = admits_outbound(account, agent_acl, channel_id)
        if not admits:
            return f"[error] [constraint] {reason}"

        # ── Pool acquire + client.send ─────────────────────────────
        # M10 F8 L11 HAT Fix #6: account-shared pool — the tool no
        # longer threads ``self._agent_name`` through the pool key.
        # All agents attached to one connector account share ONE
        # gateway connection, so multi-agent routing on a single
        # bot token works correctly (Discord rejects duplicate
        # IDENTIFY frames on the same token). The agent's identity
        # is still relevant for ACL evaluation above; just not for
        # the connector pool key.
        try:
            client = await connector_acquire(account_id)
        except (KeyError, ConnectorRegistrationError, ConnectorClientError, RuntimeError) as exc:
            return f"[error] {type(exc).__name__}: {exc}"

        target_obj = OutboundTarget(channel_id=channel_id, thread_id=thread_id)
        try:
            result = await client.send(target_obj, content)
        except ConnectorClientError as exc:
            return f"[error] {type(exc).__name__}: {exc}"

        thread_clause = f" (thread {thread_id})" if thread_id else ""
        return (
            f"{PLATFORM_SEND_OK_PREFIX} sent to "
            f"{account_id}:{channel_id}{thread_clause}: "
            f"{content!r} (msg_id={result.platform_message_id})"
        )
