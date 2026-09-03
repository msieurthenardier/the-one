"""``DiscordPlugin`` — ``ConnectorPlugin``/``ConnectorClient`` Protocol
implementation, envelope translation, and per-account gateway state
(DD-1..DD-4). Type-keyed singleton, the ``StubPlugin._live`` shape:
``_state`` is an account-id-keyed dict, not per-instance.

DD-4 was amended mid-flight (2026-09-01, operator-approved, live-gate
checkpoint 2): self/webhook messages still drop unconditionally, but a
message from any OTHER bot author is dropped only when that bot's id is
absent from ``config.allowlist.peers`` — an allowlisted bot peer is
translated exactly like a human peer. See ``flight.md`` DD-4 for the full
rationale.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

from the_one.connectors.base import (
    ConnectorClientError,
    DoctorReport,
    HistoryMessage,
    InboundCallback,
    InboundEnvelope,
    PeerTarget,
    PermanentConnectorFailure,
    SendResult,
    SendTarget,
)
from the_one.connectors.discord._gateway import GatewayConnection
from the_one.connectors.discord._rest import DEFAULT_BASE_URL, RestClient
from the_one.db.models import Connector
from the_one.encryption import Encryptor

logger = logging.getLogger(__name__)

# Discord channel types (only the ones DM/thread detection needs).
_CHANNEL_TYPE_DM = 1
_CHANNEL_TYPE_GROUP_DM = 3
_CHANNEL_TYPE_ANNOUNCEMENT_THREAD = 10
_CHANNEL_TYPE_PUBLIC_THREAD = 11
_CHANNEL_TYPE_PRIVATE_THREAD = 12
_DM_TYPES = frozenset({_CHANNEL_TYPE_DM, _CHANNEL_TYPE_GROUP_DM})
_THREAD_TYPES = frozenset(
    {_CHANNEL_TYPE_ANNOUNCEMENT_THREAD, _CHANNEL_TYPE_PUBLIC_THREAD, _CHANNEL_TYPE_PRIVATE_THREAD}
)


@dataclass
class _AccountState:
    """One entry per connected Discord account (the ``StubPlugin._live``
    shape). Survives across reconnects within the process — a fresh
    ``GatewayConnection`` is built per attempt, but reads/writes this same
    object, so ``last_seq``/``session_id``/``resume_gateway_url`` persist."""

    session_id: str | None = None
    resume_gateway_url: str | None = None
    last_seq: int | None = None
    bot_user_id: str | None = None
    # Channel-type cache, unbounded growth acceptable at personal-bot
    # scale (edge case, noted deliberately — no LRU).
    channel_type_cache: dict[str, int] = field(default_factory=dict)
    failure: str | None = None
    client: "DiscordClient | None" = None
    # DD-4 amendment (2026-09-01): the connector's `config.allowlist.peers`
    # at last connect, used to admit an allowlisted bot peer past the
    # foreign-bot drop below. Populated fresh in `connect()` on every
    # (re)connect, so a PUT-driven allowlist change takes effect on the
    # listener restart the PUT already performs — no separate live-update
    # path needed.
    allowlist_peers: frozenset[str] = field(default_factory=frozenset)


async def _resolve_channel_type(
    state: _AccountState, rest: RestClient, channel_id: str, connector_id: str
) -> int:
    """Fetches (and caches) a channel's type — and, on the cache-miss fetch
    only, opportunistically captures its name into the directory (DD-1d,
    DD-4). The cache-miss gate is load-bearing for AC-5's honesty
    contract, not incidental: since ``channel_type_cache`` lives on
    ``_AccountState`` and survives reconnects for the life of the process
    (its own documented contract — see the field above), a channel's name
    is captured AT MOST ONCE PER PROCESS LIFETIME. A rename is observed
    only after a process restart clears the cache — a deliberate,
    honestly-stated trade-off (live rename-tracking would need a fetch
    cadence this leg does not add), not a bug.

    This function is only reached from ``_translate_message_create``
    AFTER its self/webhook/unallowlisted-foreign-bot drop checks —  so a
    channel whose only traffic so far was dropped bot/self messages has
    never hit this path, and its directory entry (like its
    ``channel_type_cache`` entry) is captured on the first QUALIFYING
    message, not the channel's first message ever.
    """
    cached = state.channel_type_cache.get(channel_id)
    if cached is not None:
        return cached
    channel = await rest.get_channel(channel_id)
    ctype = channel.get("type", 0)
    state.channel_type_cache[channel_id] = ctype
    await _upsert_channel_directory(connector_id, channel_id, channel, ctype)
    return ctype


async def _upsert_channel_directory(
    connector_id: str, channel_id: str, channel: dict[str, Any], ctype: int
) -> None:
    """DD-4 (cycle-2 decision, made at flight level not deferred): channel
    entries are DELIBERATELY NOT admission-gated — plugin-side channel
    observation records any channel the bot can see, allowlisted or not.
    A stated asymmetry with the peer path: channel names are
    operator-domain metadata (the operator invited the bot into the
    guild; rooms are not people, so no third-party-silence concern), and
    the bound agent is ALREADY authorized to send to any channel of its
    connector (Flight 2's bound-agent rule), so naming visible channels
    grants zero new reach.

    A DM/group-DM ``Get Channel`` response carries no ``"name"`` (DMs
    aren't named) — skipping the upsert when absent both keeps DMs out of
    the (channel-only) directory kind and honors the "never an
    empty-string name in the directory" invariant; a real guild channel
    or thread always carries one. Threads store the DD-4 thread shape:
    ``platform_id`` = the thread's own send-addressable channel id (as
    ``channel_id`` already is for a thread, per ``_translate_message_
    create``'s ``thread_id`` assignment), ``thread_id`` alongside it.

    Best-effort: any failure here (e.g. schema/connection issues in an
    environment that never touched the DB before) is logged and
    swallowed — a directory-observation hiccup must never break message
    translation, mirroring this module's self/webhook/foreign-bot drop
    philosophy of never taking the inbound pipeline down over a
    connector-layer concern.
    """
    # Squawk 0040: a group DM (type=3) differs in shape from a 1:1 DM
    # (type=1) -- Discord's schema carries a "name" key that is nullable
    # rather than simply absent when the group has no custom name set.
    # ``.get("name")`` yields ``None`` for both shapes, so both hit this
    # same falsy-name skip -- pinned deliberately, not an oversight.
    name = channel.get("name")
    if not name:
        return
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorDirectoryRepository

    thread_id = channel_id if ctype in _THREAD_TYPES else None
    try:
        conn = await get_connection()
        await ConnectorDirectoryRepository(conn).upsert(
            connector_id=connector_id,
            kind="channel",
            platform_id=channel_id,
            thread_id=thread_id,
            display_name=name,
            username=None,
        )
    except Exception:
        logger.exception(
            "discord plugin: channel-directory upsert failed for connector %s channel %s",
            connector_id,
            channel_id,
        )


async def _translate_message_create(
    state: _AccountState, rest: RestClient, d: dict[str, Any], connector_id: str
) -> Any | None:
    """MESSAGE_CREATE -> ``InboundEnvelope`` (DD-4), or ``None`` to drop."""
    if state.bot_user_id is None:
        # MESSAGE_CREATE arriving before READY has finished processing —
        # drop cleanly rather than dispatch with an unknown bot id (edge
        # case: mentions_bot would be wrong).
        return None
    author = d.get("author") or {}
    author_id = author.get("id")
    if author_id == state.bot_user_id or d.get("webhook_id"):
        return None  # self/webhook authored — loop-prevention drop, unconditional (DD-4).
    if author.get("bot") and author_id not in state.allowlist_peers:
        # Foreign bot not on `config.allowlist.peers` — dropped (DD-4
        # amendment, 2026-09-01: was a blanket any-bot drop; an
        # allowlisted bot peer now falls through and is translated below
        # exactly like a human peer, subject to the pipeline's own
        # `is_admitted` allowlist check as usual).
        return None
    channel_id = d.get("channel_id", "")
    ctype = await _resolve_channel_type(state, rest, channel_id, connector_id)
    mentions = d.get("mentions") or []
    peer_name = author.get("global_name") or author.get("username") or "unknown"
    return InboundEnvelope(
        platform="discord",
        connector_id=connector_id,
        channel_id=channel_id,
        thread_id=channel_id if ctype in _THREAD_TYPES else None,
        peer_id=author.get("id", ""),
        peer_name=peer_name,
        text=d.get("content", ""),
        is_dm=ctype in _DM_TYPES,
        mentions_bot=any(m.get("id") == state.bot_user_id for m in mentions),
        # DD-1f/DD-4 (Mission 23 Flight 4): the directory disambiguation
        # field — Discord's own handle, distinct from the display-name
        # ``peer_name`` above (which prefers ``global_name``).
        peer_username=author.get("username"),
        raw=d,
    )


class DiscordClient:
    """Live per-account connection — structurally satisfies ``ConnectorClient``."""

    def __init__(
        self, gw: GatewayConnection, rest: RestClient, task: asyncio.Task, account_id: str
    ) -> None:
        self._gw = gw
        self._rest = rest
        self._task = task
        self.account_id = account_id

    def is_alive(self) -> bool:
        return self._gw.is_alive() and not self._task.done()

    def sever_for_test(self) -> None:
        """OPTIONAL hook (DD-7, AC-1) — discovered via ``getattr(client,
        "sever_for_test", None)`` from the dual-gated sever route, the same
        optional-hook pattern ``history`` uses. Lives ONLY on the Discord
        client (not the Protocol, not the stub); a one-line delegate to
        ``GatewayConnection.sever_for_test`` — see its docstring for the
        abrupt-abort mechanics."""
        self._gw.sever_for_test()

    async def _resolve_channel_id(self, target: SendTarget) -> str:
        if isinstance(target, PeerTarget):
            channel = await self._rest.create_dm(target.peer_id)
            return channel["id"]
        return target.channel_id

    async def send(self, target: SendTarget, content: str) -> SendResult:
        channel_id = await self._resolve_channel_id(target)
        message = await self._rest.create_message(channel_id, content)
        return SendResult(platform_message_id=str(message.get("id", "")), details={})

    async def history(self, target: SendTarget, limit: int) -> list[HistoryMessage]:
        channel_id = await self._resolve_channel_id(target)
        raw = await self._rest.get_channel_messages(channel_id, limit=limit)
        out = []
        for m in raw:
            author = m.get("author") or {}
            out.append(
                HistoryMessage(
                    peer_id=author.get("id", ""),
                    peer_name=author.get("global_name") or author.get("username") or "unknown",
                    content=m.get("content", ""),
                    ts=m.get("timestamp", ""),
                )
            )
        return out


class DiscordPlugin:
    """Type-keyed singleton — production ``ConnectorPlugin`` for Discord."""

    def __init__(
        self,
        *,
        gateway_url: str | None = None,
        rest_base_url: str = DEFAULT_BASE_URL,
        reidentify_delay: Any = None,
        rest_transport: Any = None,
    ) -> None:
        # Test seams (DD-8): a real Discord instance never sets these —
        # the gateway URL comes from Get Gateway Bot, the delay is
        # Discord's recommended 1-5s random jitter, and ``rest_transport``
        # (an ``httpx`` transport) is how a test mocks REST without a live
        # call — forwarded verbatim to every ``RestClient`` this plugin
        # builds.
        self._gateway_url_override = gateway_url
        self._rest_base_url = rest_base_url
        self._reidentify_delay = reidentify_delay
        self._rest_transport = rest_transport
        self._state: dict[str, _AccountState] = {}

    def _state_for(self, account_id: str) -> _AccountState:
        return self._state.setdefault(account_id, _AccountState())

    def _new_rest_client(self, token: str) -> RestClient:
        kwargs: dict[str, Any] = {}
        if self._rest_transport is not None:
            kwargs["transport"] = self._rest_transport
        return RestClient(token, base_url=self._rest_base_url, **kwargs)

    async def connect(
        self, account: Connector, encryptor: Encryptor, on_inbound: InboundCallback
    ) -> DiscordClient:
        """See ``GatewayConnection``'s docstring for the close-code-policy
        timing rule this implements (AC-4's accepted one-cycle latency for
        a mid-session permanent close)."""
        state = self._state_for(account.id)
        state.failure = None  # lifecycle rule: cleared unconditionally at the top.
        # DD-4 amendment: refresh from the current config on every connect
        # (see `_AccountState.allowlist_peers` docstring for the
        # restart-picks-up-changes rationale).
        state.allowlist_peers = frozenset(
            (account.config.get("allowlist") or {}).get("peers") or []
        )
        token = account.secrets["token"]
        rest = self._new_rest_client(token)

        async def _default_url() -> str:
            return self._gateway_url_override or await rest.get_gateway_url()

        gw = GatewayConnection(
            token=token,
            state=state,
            default_url_provider=_default_url,
            reidentify_delay=self._reidentify_delay,
        )

        async def _on_dispatch(t: str, d: dict[str, Any]) -> None:
            if t != "MESSAGE_CREATE":
                return
            envelope = await _translate_message_create(state, rest, d, account.id)
            if envelope is not None:
                await on_inbound(envelope)

        ready_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        # `bot_user_id`/`channel_type_cache` are captured directly inside
        # `GatewayConnection.run()`'s READY handling (synchronously, before
        # `ready_future` resolves) — NOT read back out of `ready_info`
        # here, which would race a MESSAGE_CREATE dispatched immediately
        # after READY (edge case). `ready_info` still carries the raw
        # payload for any future informational use.
        ready_info: dict[str, Any] = {}
        task = asyncio.create_task(gw.run(_on_dispatch, ready_future, ready_info))
        try:
            await ready_future
        except PermanentConnectorFailure as exc:
            state.failure = str(exc)
            with contextlib.suppress(Exception):
                await task
            await rest.aclose()
            raise
        except Exception:
            with contextlib.suppress(Exception):
                await task
            await rest.aclose()
            raise

        client = DiscordClient(gw, rest, task, account.id)
        state.client = client
        return client

    async def disconnect(self, client: "DiscordClient") -> None:
        """Idempotent — safe to call on an already-disconnected client."""
        await client._gw.close()
        if not client._task.done():
            client._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await client._task
        with contextlib.suppress(Exception):
            await client._rest.aclose()
        state = self._state.get(client.account_id)
        if state is not None and state.client is client:
            state.client = None

    async def doctor(self, account: Connector, encryptor: Encryptor) -> DoctorReport:
        state = self._state_for(account.id)
        if state.failure is not None:
            return DoctorReport(
                status="failed", message=f"permanently failed: {state.failure}", details={}
            )
        token = account.secrets.get("token")
        if not token:
            return DoctorReport(status="failed", message="no bot token configured", details={})
        rest = self._new_rest_client(token)
        try:
            me = await rest.get_current_user()
        except ConnectorClientError as exc:
            return DoctorReport(status="failed", message=f"REST check failed: {exc}", details={})
        finally:
            await rest.aclose()
        gateway_alive = state.client is not None and state.client.is_alive()
        status = "ok" if gateway_alive else "degraded"
        message = "gateway connected" if gateway_alive else "REST reachable; gateway not connected"
        return DoctorReport(
            status=status,
            message=message,
            details={"bot_user": me.get("username"), "gateway_connected": gateway_alive},
        )
