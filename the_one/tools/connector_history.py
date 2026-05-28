"""Built-in channel-context tools — the agent-side history read entry points.

M11 F7 L10 per Flight DD §10. Four tools registered in
:data:`the_one.tools.builtins._TOOL_CLASSES` so they surface in the
built-in-tools admin grid; operator enable/disable lives at
:class:`ToolConfigRepository.enabled`.

The tools resolve the current chat session's connector account via the
:data:`the_one.agent.context.current_chat_session_id` ContextVar
(set by the WebSocket message handler and inherited into the inbound
dispatcher's task tree), look up the session row to read its
``connector_id``, resolve the plugin via the registry, and
acquire the live :class:`ConnectorClient` via
:func:`the_one.connectors._pool.account_acquire`.

Per-agent ACLs gate read access on a per-axis basis (DD §10):

- :class:`FetchChannelHistoryTool` and :class:`FetchThreadHistoryTool`
  gate on the **channel** axis via
  :func:`the_one.connectors._acl.admits_outbound` (the channel-axis
  ACL admission helper). Channel-axis is symmetric for read and
  write — the same axis that determines outbound reachability
  determines inbound visibility.
- :class:`FetchDmHistoryTool` gates on the **peer** axis via
  :func:`the_one.connectors._acl.admits_dm_peer` (L10's new
  peer-axis admission helper — channel-axis ``admits_outbound`` is
  not the right shape for DM reads since the peer identity is the
  authorization subject, not the channel).
- :class:`ListVisibleChannelsTool` does not gate (the F3 cache of
  ``DiscoverableEntities`` is already account-scope-narrowed at refresh
  time; the per-agent ACL does not further filter what the tool can
  *see*, only what the tool can *act* on through the gate tools).

Two new optional plugin hooks (per
``optional-plugin-hook-via-getattr-sentinel``):

- ``fetch_history(client, channel_id, thread_id, limit) -> list[FetchedMessage]``
- ``fetch_dm_history(client, peer_id, limit) -> list[FetchedMessage]``

Discovered via ``getattr(plugin, "fetch_history", None)`` /
``getattr(plugin, "fetch_dm_history", None)``. ``None`` (plugin
doesn't implement) → tool returns
``[{"error": "this plugin does not support history fetch"}]``.
:class:`ListVisibleChannelsTool` reuses the F3
``enumerate_discoverable_entities`` hook; cache snapshot is preferred
(faster, doesn't hit rate limits) with a live-hook fallback when the
cache is empty.

The four error envelopes the tools emit (per Flight DD §10 / leg
``## Edge Cases``):

- Outside-connector (``current_chat_session_id`` is None OR session
  row has no ``connector_id`` OR session lookup raises):
  ``[{"error": "this tool is only available in a connector-attached session"}]``.
- ACL-denied (any axis): ``[{"error": "agent not permitted to read
  <axis> X: <reason>"}]``.
- Plugin hook missing:
  ``[{"error": "this plugin does not support history fetch"}]`` for
  the three fetch tools;
  ``{"error": "this plugin does not support entity enumeration",
  "peers": [], "channels": [], "groups": [], "roles": []}`` for the
  visible-channels tool.
- Plugin hook exception:
  ``[{"error": f"fetch_history failed: <ExcType>: <exc>"}]`` (or the
  ``fetch_dm_history`` analogue).

Each error envelope is the single-element list-of-dict with an
``error`` key (or, for the dict-returning :class:`ListVisibleChannelsTool`,
a dict with ``error`` plus four empty axes so callers can read the
dict shape unconditionally).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from the_one.tools.base import Tool


class FetchChannelHistoryTool(Tool):
    """Fetch recent messages from a channel the bot can see."""

    name = "fetch_channel_history"
    description = (
        "Fetch recent messages from a channel the bot can see. "
        "Returns a list of message dicts (peer_id, peer_name, content, "
        "ts, thread_id) ordered most-recent-last. Respects the agent's "
        "channel ACL — denied channels return a single-element list "
        "containing an error dict."
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": (
                    "Platform-native channel id (Discord channel "
                    "snowflake, Slack channel id) to fetch from. "
                    "Typically obtained from the inbound envelope's "
                    "channel_id or from a list_visible_channels call."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of messages to fetch. Default 20."
                ),
                "default": 20,
            },
        },
        "required": ["channel_id"],
    }

    def __init__(
        self,
        config: Any = None,
        cross_configs: dict[type, object] | None = None,
        agent_name: str | None = None,
        connector_ids: list[str] | None = None,
        connector_acls: dict[str, dict[str, list[str] | None]] | None = None,
    ) -> None:
        super().__init__(config, cross_configs, agent_name)
        self._connector_ids: list[str] = connector_ids or []
        self._connector_acls: dict[str, dict[str, list[str] | None]] | None = (
            connector_acls
        )

    async def execute(  # type: ignore[override]
        self,
        channel_id: Any = None,
        limit: Any = 20,
        **_extra: Any,
    ) -> list[dict[str, Any]]:
        # **_extra defensively swallows unexpected kwargs from the LLM
        # tool-call dispatch — same convention as connector_send.py.
        if not isinstance(channel_id, str) or not channel_id:
            return [{"error": "channel_id must be a non-empty string"}]
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            limit = 20

        ctx = await _resolve_connector_account_context()
        if ctx is None:
            return _outside_connector_error_list()
        account, plugin, client = ctx

        from the_one.connectors._acl import admits_outbound

        agent_acl = _agent_acl_for(self._connector_acls, account.id)
        admits, reason = admits_outbound(account, agent_acl, channel_id)
        if not admits:
            return [
                {
                    "error": (
                        f"agent not permitted to read channel "
                        f"{channel_id}: {reason}"
                    )
                }
            ]

        hook = getattr(plugin, "fetch_history", None)
        if hook is None:
            return [{"error": "this plugin does not support history fetch"}]

        try:
            messages = await hook(client, channel_id, None, limit)
        except Exception as exc:  # noqa: BLE001 — plugin error surface
            return [
                {"error": f"fetch_history failed: {type(exc).__name__}: {exc}"}
            ]

        return [asdict(m) for m in messages]


class FetchThreadHistoryTool(Tool):
    """Fetch recent messages from a thread within a channel."""

    name = "fetch_thread_history"
    description = (
        "Fetch recent messages from a thread inside a channel the bot "
        "can see. Returns a list of message dicts (peer_id, peer_name, "
        "content, ts, thread_id) ordered most-recent-last. Respects the "
        "agent's channel ACL on the parent channel — denied threads "
        "return a single-element list containing an error dict."
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": (
                    "Platform-native channel id that contains the "
                    "thread. ACL admission is checked against this id."
                ),
            },
            "thread_id": {
                "type": "string",
                "description": (
                    "Platform-native thread id to fetch from."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of messages to fetch. Default 20."
                ),
                "default": 20,
            },
        },
        "required": ["channel_id", "thread_id"],
    }

    def __init__(
        self,
        config: Any = None,
        cross_configs: dict[type, object] | None = None,
        agent_name: str | None = None,
        connector_ids: list[str] | None = None,
        connector_acls: dict[str, dict[str, list[str] | None]] | None = None,
    ) -> None:
        super().__init__(config, cross_configs, agent_name)
        self._connector_ids: list[str] = connector_ids or []
        self._connector_acls: dict[str, dict[str, list[str] | None]] | None = (
            connector_acls
        )

    async def execute(  # type: ignore[override]
        self,
        channel_id: Any = None,
        thread_id: Any = None,
        limit: Any = 20,
        **_extra: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(channel_id, str) or not channel_id:
            return [{"error": "channel_id must be a non-empty string"}]
        if not isinstance(thread_id, str) or not thread_id:
            return [{"error": "thread_id must be a non-empty string"}]
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            limit = 20

        ctx = await _resolve_connector_account_context()
        if ctx is None:
            return _outside_connector_error_list()
        account, plugin, client = ctx

        from the_one.connectors._acl import admits_outbound

        agent_acl = _agent_acl_for(self._connector_acls, account.id)
        admits, reason = admits_outbound(account, agent_acl, channel_id)
        if not admits:
            return [
                {
                    "error": (
                        f"agent not permitted to read channel "
                        f"{channel_id}: {reason}"
                    )
                }
            ]

        hook = getattr(plugin, "fetch_history", None)
        if hook is None:
            return [{"error": "this plugin does not support history fetch"}]

        try:
            messages = await hook(client, channel_id, thread_id, limit)
        except Exception as exc:  # noqa: BLE001 — plugin error surface
            return [
                {"error": f"fetch_history failed: {type(exc).__name__}: {exc}"}
            ]

        return [asdict(m) for m in messages]


class FetchDmHistoryTool(Tool):
    """Fetch recent messages from a direct-message conversation with a peer."""

    name = "fetch_dm_history"
    description = (
        "Fetch recent messages from the direct-message conversation "
        "with a specific peer the bot can DM. Returns a list of "
        "message dicts (peer_id, peer_name, content, ts, thread_id — "
        "thread_id is always null for DMs) ordered most-recent-last. "
        "Respects the agent's peer ACL — denied peers return a "
        "single-element list containing an error dict."
    )
    parameters = {
        "type": "object",
        "properties": {
            "peer_id": {
                "type": "string",
                "description": (
                    "Platform-native peer id (Discord user snowflake, "
                    "Slack user id) to read the DM thread for."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of messages to fetch. Default 20."
                ),
                "default": 20,
            },
        },
        "required": ["peer_id"],
    }

    def __init__(
        self,
        config: Any = None,
        cross_configs: dict[type, object] | None = None,
        agent_name: str | None = None,
        connector_ids: list[str] | None = None,
        connector_acls: dict[str, dict[str, list[str] | None]] | None = None,
    ) -> None:
        super().__init__(config, cross_configs, agent_name)
        self._connector_ids: list[str] = connector_ids or []
        self._connector_acls: dict[str, dict[str, list[str] | None]] | None = (
            connector_acls
        )

    async def execute(  # type: ignore[override]
        self,
        peer_id: Any = None,
        limit: Any = 20,
        **_extra: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(peer_id, str) or not peer_id:
            return [{"error": "peer_id must be a non-empty string"}]
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            limit = 20

        ctx = await _resolve_connector_account_context()
        if ctx is None:
            return _outside_connector_error_list()
        account, plugin, client = ctx

        from the_one.connectors._acl import admits_dm_peer

        agent_acl = _agent_acl_for(self._connector_acls, account.id)
        admits, reason = admits_dm_peer(account, agent_acl, peer_id)
        if not admits:
            return [
                {
                    "error": (
                        f"agent not permitted to read peer "
                        f"{peer_id}: {reason}"
                    )
                }
            ]

        hook = getattr(plugin, "fetch_dm_history", None)
        if hook is None:
            return [{"error": "this plugin does not support history fetch"}]

        try:
            messages = await hook(client, peer_id, limit)
        except Exception as exc:  # noqa: BLE001 — plugin error surface
            return [
                {
                    "error": (
                        f"fetch_dm_history failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
                }
            ]

        return [asdict(m) for m in messages]


class ListVisibleChannelsTool(Tool):
    """List the peers/channels/groups/roles the bot can see on the
    attached connector account.

    Reads the F3 ``DiscoverableEntities`` cache snapshot from the pool
    when available (preferred — faster, doesn't hit rate limits); falls
    back to a live invocation of the plugin's
    ``enumerate_discoverable_entities`` hook when the cache is empty
    (cold pool entry, first refresh not yet landed). Returns an
    axis-keyed dict ``{"peers": [...], "channels": [...], "groups":
    [...], "roles": [...]}`` where each entry is a dict ``{"id": str,
    "label": str, "group": str | None, "metadata": dict}`` — the
    :class:`the_one.connectors.base.DiscoverableEntity` shape passed
    through ``dataclasses.asdict``. The ``fetched_at`` timestamp on
    :class:`DiscoverableEntities` is intentionally omitted from the
    tool's response (the LLM doesn't need it).
    """

    name = "list_visible_channels"
    description = (
        "List the peers, channels, groups, and roles the bot can see "
        "on the attached connector account. Returns a dict with four "
        "keys: peers, channels, groups, roles — each a list of entity "
        "dicts (id, label, group, metadata). Use the returned ids in "
        "subsequent fetch_channel_history / fetch_thread_history / "
        "fetch_dm_history / send_to_platform_channel calls."
    )
    parameters = {
        "type": "object",
        "properties": {},
    }

    def __init__(
        self,
        config: Any = None,
        cross_configs: dict[type, object] | None = None,
        agent_name: str | None = None,
        connector_ids: list[str] | None = None,
        connector_acls: dict[str, dict[str, list[str] | None]] | None = None,
    ) -> None:
        super().__init__(config, cross_configs, agent_name)
        self._connector_ids: list[str] = connector_ids or []
        self._connector_acls: dict[str, dict[str, list[str] | None]] | None = (
            connector_acls
        )

    async def execute(self, **_extra: Any) -> dict[str, Any]:  # type: ignore[override]
        ctx = await _resolve_connector_account_context()
        if ctx is None:
            return _outside_connector_error_dict()
        account, plugin, client = ctx

        # Prefer the cache snapshot (F3 L4 refresh sweep keeps it warm);
        # fall back to a live invocation when the entry exists but the
        # first refresh hasn't landed (cold-start race) or when the
        # account entry isn't pooled yet.
        from the_one.connectors._pool import _get_account_cache_snapshot

        snapshot = await _get_account_cache_snapshot(account.id)
        entities = snapshot.cache if snapshot is not None else None

        if entities is None:
            hook = getattr(plugin, "enumerate_discoverable_entities", None)
            if hook is None:
                return _no_enumerate_hook_error_dict()
            try:
                # The hook is sync in current plugins (see Discord at
                # ``_discord.py:1704``), but the contract is "callable
                # returning DiscoverableEntities"; we don't await here.
                entities = hook(client)
            except Exception as exc:  # noqa: BLE001 — plugin error surface
                return {
                    "error": (
                        f"enumerate_discoverable_entities failed: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    "peers": [],
                    "channels": [],
                    "groups": [],
                    "roles": [],
                }
            if entities is None:
                return _no_enumerate_hook_error_dict()

        return {
            "peers": [asdict(e) for e in entities.peers],
            "channels": [asdict(e) for e in entities.channels],
            "groups": [asdict(e) for e in entities.groups],
            "roles": [asdict(e) for e in entities.roles],
        }


# ── Module-private helpers ──────────────────────────────────────────


def _agent_acl_for(
    connector_acls: dict[str, dict[str, list[str] | None]] | None,
    account_id: str,
) -> dict[str, list[str] | None] | None:
    """Look up the per-agent ACL for ``account_id``.

    Returns ``None`` when ``connector_acls`` itself is ``None`` or when
    the account isn't keyed in the dict — the ACL helpers treat ``None``
    as "no per-agent narrowing; inherit account-scope" per the F7 L2
    convention.
    """
    if connector_acls is None:
        return None
    return connector_acls.get(account_id)


def _outside_connector_error_list() -> list[dict[str, Any]]:
    """Single-element error list for the three fetch tools when there is
    no connector-attached session in the current async context.

    Covers the L10 ``## Edge Cases`` triplet: ``current_chat_session_id``
    is None; session has no ``connector_id``; session lookup
    raised. All three converge to the same operator-facing message —
    the LLM either hallucinated calling the tool in a non-connector
    context or the session row is malformed; in either case the tool
    cannot proceed.
    """
    return [
        {"error": "this tool is only available in a connector-attached session"}
    ]


def _outside_connector_error_dict() -> dict[str, Any]:
    """Sibling of :func:`_outside_connector_error_list` for the dict-
    returning :class:`ListVisibleChannelsTool`. Carries the four empty
    axes so callers can read the dict shape unconditionally without
    branching on the ``error`` key first.
    """
    return {
        "error": "this tool is only available in a connector-attached session",
        "peers": [],
        "channels": [],
        "groups": [],
        "roles": [],
    }


def _no_enumerate_hook_error_dict() -> dict[str, Any]:
    """Error dict for :class:`ListVisibleChannelsTool` when the resolved
    plugin doesn't implement ``enumerate_discoverable_entities``.
    Carries the four empty axes for shape uniformity (see
    :func:`_outside_connector_error_dict`)."""
    return {
        "error": "this plugin does not support entity enumeration",
        "peers": [],
        "channels": [],
        "groups": [],
        "roles": [],
    }


async def _resolve_connector_account_context() -> (
    tuple[Any, Any, Any] | None
):
    """Resolve ``(account, plugin, client)`` for the current chat session.

    Returns ``None`` when any of the following holds:

    - ``current_chat_session_id`` ContextVar is unset (tool called from
      a non-connector context — REST handler, CLI, etc.).
    - ``ChatSessionRepository.get(session_id)`` raises (session row was
      deleted between dispatch and tool execution — extremely narrow
      race; defended for robustness).
    - The resolved session row has no ``connector_id`` (this
      session was created via the local Chat UI, not by a connector
      dispatch).
    - The connector account lookup, plugin resolve, or pool acquire
      raises (account deleted, plugin unregistered, gateway down — all
      transient or misconfiguration failure modes the tool surfaces as
      an outside-connector error so the LLM gets a single
      operator-readable error envelope rather than a stack trace).

    Function-local imports mirror the
    :mod:`the_one.tools.connector_send` precedent: the connectors/db
    boundary is repeatedly traversed at execute time and the function-
    local imports prevent the tools module from accumulating direct
    imports across that boundary.
    """
    from the_one.agent._context import current_chat_session_id

    session_id = current_chat_session_id.get()
    if session_id is None:
        return None

    from the_one.config import settings
    from the_one.connectors import registry as connector_registry
    from the_one.connectors._pool import account_acquire
    from the_one.db.connection import get_connection
    from the_one.db.repositories import (
        ChatSessionRepository,
        ConnectorRepository,
    )
    from the_one.encryption import get_encryptor

    try:
        conn = await get_connection()
        session_repo = ChatSessionRepository(conn)
        try:
            session = await session_repo.get(session_id)
        except KeyError:
            return None
        account_id = session.connector_id
        if not account_id:
            return None

        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorRepository(conn, encryptor)
        try:
            account = await acc_repo.get(account_id)
        except KeyError:
            return None

        try:
            plugin = connector_registry.resolve(account.type)
        except Exception:  # noqa: BLE001 — registry / type failures all collapse
            return None

        try:
            client = await account_acquire(account_id)
        except Exception:  # noqa: BLE001 — pool acquire failures all collapse
            return None
    except Exception:  # noqa: BLE001 — defensive outer net (db unavailable, etc.)
        return None

    return account, plugin, client
