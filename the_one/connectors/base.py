"""Connector plugin contract — Protocol, inbound envelope, send targets.

Platform-agnostic core (Mission 23 Flight 2, DD-1). Implementations
satisfy the Protocols structurally (``the_one/agents.md`` →
``structural-Protocol-satisfaction``) — no inheritance required. This is
a deliberately SMALL contract: no ACL/routing/command/discoverable-entity
surface (that was the pre-reset design; DD-1..DD-11 strip it).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from the_one.db.models import Connector
from the_one.encryption import Encryptor


@dataclass(frozen=True, slots=True)
class InboundEnvelope:
    """A message received from the external platform, normalized for the pipeline.

    ``is_dm`` and ``mentions_bot`` are set by the platform client's own
    translation layer (design review 2026-08-31) — the inbound pipeline
    never infers them from ``channel_id`` shape.
    """

    platform: str
    connector_id: str
    channel_id: str
    thread_id: str | None
    peer_id: str
    peer_name: str
    text: str
    is_dm: bool
    mentions_bot: bool
    raw: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True, slots=True)
class ChannelTarget:
    """A channel-keyed send destination."""

    connector_id: str
    channel_id: str
    thread_id: str | None = None


@dataclass(frozen=True, slots=True)
class PeerTarget:
    """A peer-keyed DM send destination. ``channel_map`` never applies here (DD-4)."""

    connector_id: str
    peer_id: str


SendTarget = ChannelTarget | PeerTarget


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: Literal["ok", "degraded", "failed"]
    message: str
    details: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True, slots=True)
class SendResult:
    platform_message_id: str | None
    details: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    """One message returned by the OPTIONAL ``ConnectorClient.history`` hook (DD-8)."""

    peer_id: str
    peer_name: str
    content: str
    ts: str


class ConnectorClientError(Exception):
    """Raised by a plugin's send/doctor/history on a platform-side failure."""


class PermanentConnectorFailure(ConnectorClientError):  # noqa: N818  (leg-1 contract name; subclass of ConnectorClientError)
    """Raised by ``ConnectorPlugin.connect`` when the platform closes the
    connection with a non-reconnectable code (Discord: 4004 authentication
    failed; 4010-4014 shard/intent misconfiguration) — a condition
    backoff-and-retry can never resolve.

    ``ConnectorManager._connect_once`` re-raises this ahead of its
    catch-all ``except Exception`` (which would otherwise swallow it as an
    ordinary connect failure), and ``ConnectorManager._run`` catches it
    narrowly: logs, and STOPS retrying — the listener task ends instead of
    backing off forever on a token that will never become valid. Any other
    close code or connect failure follows the manager's normal backoff +
    reconnect path, unchanged. Defined here (contract-level, not in the
    Discord subpackage) so future platforms (e.g. Telegram) inherit the
    same stop-retrying channel.
    """


@runtime_checkable
class ConnectorClient(Protocol):
    """Live per-account connection. One instance per running listener task."""

    def is_alive(self) -> bool:
        """Cheap liveness check, polled by the manager's supervisor loop."""
        ...

    async def send(self, target: SendTarget, content: str) -> SendResult: ...

    # ``history(target, limit) -> list[HistoryMessage]`` is OPTIONAL
    # (DD-8) — discovered via ``getattr(client, "history", None)``, NOT
    # declared on this Protocol, so plugins that don't implement it
    # aren't forced to carry a stub method.


InboundCallback = Callable[[InboundEnvelope], Awaitable[None]]


@runtime_checkable
class ConnectorPlugin(Protocol):
    """Type-level adapter for a third-party communication platform.

    ``connect`` receives an ``on_inbound`` callback; the plugin's gateway
    listener (spawned internally — see ``agent/factory.py``'s module
    docstring on gateway-listener spawn) invokes it for every inbound
    message. ``connect`` returns once the listener is live; it does NOT
    block for the connection's lifetime.
    """

    async def connect(
        self,
        account: Connector,
        encryptor: Encryptor,
        on_inbound: InboundCallback,
    ) -> ConnectorClient: ...

    async def disconnect(self, client: ConnectorClient) -> None:
        """Idempotent teardown — calling on an already-disconnected client MUST NOT raise."""
        ...

    async def doctor(self, account: Connector, encryptor: Encryptor) -> DoctorReport: ...
