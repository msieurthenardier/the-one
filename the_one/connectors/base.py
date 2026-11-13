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

from the_one.db.models import ChatSession, Connector
from the_one.encryption import Encryptor
from the_one.visuals.outbound import OutboundImage  # noqa: F401  (canonical import + re-export)


@dataclass(frozen=True, slots=True)
class InboundEnvelope:
    """A message received from the external platform, normalized for the pipeline.

    ``is_dm`` and ``mentions_bot`` are set by the platform client's own
    translation layer (design review 2026-08-31) — the inbound pipeline
    never infers them from ``channel_id`` shape.

    ``peer_username`` (Mission 23 Flight 4 DD-1f/DD-4) is an OPTIONAL,
    defaulted, additive field — a platform-supplied handle distinct from
    ``peer_name`` (a display name; names collide, usernames disambiguate
    in the directory). Discord fills it from ``author.username``, the
    stub test seam passes it through as an optional body field, Telegram
    (leg 2) fills it from ``from.username``; a direct construction site
    that doesn't have one leaves the default ``None``.
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
    peer_username: str | None = None
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


def keying_to_target(session: ChatSession) -> SendTarget | None:
    """DD-8 (Mission 23 Flight 4, Flight 3 debrief debt): the single keying
    authority mapping a ``chat_sessions`` row's keying columns to a
    :data:`SendTarget`. Consumed by
    ``tools/connector_send.py::SendToPlatformChannelTool._resolve_default_target``
    and mirrored by ``connectors/inbound.py::resolve_session``'s own
    keying (that function looks UP an existing row by these same columns
    rather than building a ``SendTarget``, so it stays a separate,
    reference-only consumer — no shared call, per the DD-8 rationale).

    Mirrors ``resolve_session``'s keying semantics: ``channel_id`` (not
    ``peer_id``) is the session's primary keying column, so a
    channel_id-bearing session — DM or not — resolves to a
    :class:`ChannelTarget` (with ``thread_id`` passthrough); ``peer_id``
    alone (no ``channel_id``) resolves to a :class:`PeerTarget`.

    Returns ``None`` for a non-connector-bound session (``connector_id``
    unset) AND for the degenerate connector-bound-but-keyless case
    (``connector_id`` set, but neither ``channel_id`` nor ``peer_id`` —
    shouldn't occur via ``resolve_session`` in practice, but this helper
    must not guess). Both collapse to the same ``None`` return so a caller
    renders its own "not bound to a platform conversation" error for
    either — the error-path handoff DD-8's design review pinned.
    """
    if session.connector_id is None:
        return None
    if session.channel_id is not None:
        return ChannelTarget(
            connector_id=session.connector_id,
            channel_id=session.channel_id,
            thread_id=session.thread_id,
        )
    if session.peer_id is not None:
        return PeerTarget(connector_id=session.connector_id, peer_id=session.peer_id)
    return None


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


class VisualUploadError(ConnectorClientError):
    """Raised by an optional ``send_visual`` ONLY when nothing of the reply was posted.

    The platform answered 4xx before anything went out, so the caller may resend the text
    fallback once without duplicating anything (M35 F3 DD7/DD8). Once the text has been
    posted, a failed image is the client's own per-image fallback, never this error; a 5xx
    or a transport error is a plain ``ConnectorClientError`` and is never resent.
    """


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
    #
    # Two more OPTIONAL methods, found the same way (M35 F3 DD8):
    #   ``send_visual(target, content, images: Sequence[OutboundImage]) -> SendResult``
    #       sends the text with drawn chart images; ``SendResult.details`` may carry
    #       ``{"images_sent": n, "images_failed": m}``. It raises ``VisualUploadError`` ONLY
    #       when nothing of the reply was posted (a 4xx before anything went out); a failure
    #       after the text was posted is the client's own per-image fallback, and any other
    #       failure is a plain ``ConnectorClientError`` (never resent).
    #   ``send_visual_fallback(target, content) -> SendResult``
    #       the text resend after a ``VisualUploadError``, under the client's clamped
    #       per-call 429 policy; without it the helper uses ``send``.


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
