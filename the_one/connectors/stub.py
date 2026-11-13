"""In-process stub plugin — the cross-flight regression fixture.

Registered by tests via ``registry.register_for_test("stub", StubPlugin())``,
never in production. Records outbound sends for assertions and exposes
:meth:`StubPlugin.push_inbound` so tests can drive the inbound pipeline
without a real platform. Class-level buffers (mirrors the pre-reset
fixture) — tests MUST call :meth:`StubPlugin.reset_for_test` between
cases (an autouse fixture typically does this).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from the_one.connectors.base import (
    ConnectorClientError,
    DoctorReport,
    HistoryMessage,
    InboundCallback,
    InboundEnvelope,
    OutboundImage,
    SendResult,
    SendTarget,
)
from the_one.db.models import Connector
from the_one.encryption import Encryptor


class StubVisualRecord(tuple):
    """An outbound record of a ``send_visual``: ``(target, content)`` plus ``.images``.

    A tuple subclass so every existing reader (unpacking, indexing, ``==`` against a plain
    pair, slicing) keeps working; note ``==`` ignores ``.images``, so tests on a visual
    record assert ``.images`` explicitly.
    """

    images: tuple[OutboundImage, ...]

    def __new__(cls, target: SendTarget, content: str, images: Sequence[OutboundImage]):
        rec = tuple.__new__(cls, (target, content))
        rec.images = tuple(images)
        return rec


class StubClient:
    """In-process :class:`ConnectorClient` — structurally satisfies the Protocol."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    async def send(self, target: SendTarget, content: str) -> SendResult:
        if StubPlugin.send_should_raise is not None:
            raise StubPlugin.send_should_raise
        StubPlugin.outbound_records.append((target, content))
        return SendResult(platform_message_id="stub-msg-id", details={})

    async def send_visual(
        self, target: SendTarget, content: str, images: Sequence[OutboundImage]
    ) -> SendResult:
        if StubPlugin.send_should_raise is not None:
            raise StubPlugin.send_should_raise
        if StubPlugin.send_visual_should_raise is not None:
            raise StubPlugin.send_visual_should_raise
        StubPlugin.outbound_records.append(StubVisualRecord(target, content, images))
        return SendResult(
            platform_message_id="stub-msg-id",
            details={"images_sent": len(images), "images_failed": 0},
        )

    async def history(self, target: SendTarget, limit: int) -> list[HistoryMessage]:
        return list(StubPlugin.history_response)[:limit]


class StubPlugin:
    """In-process :class:`ConnectorPlugin` — cross-flight regression fixture."""

    connect_calls: ClassVar[list[str]] = []
    disconnect_calls: ClassVar[list[StubClient]] = []
    outbound_records: ClassVar[list[tuple[SendTarget, str] | StubVisualRecord]] = []
    history_response: ClassVar[list[HistoryMessage]] = []

    connect_should_fail: ClassVar[BaseException | None] = None
    send_should_raise: ClassVar[BaseException | None] = None
    send_visual_should_raise: ClassVar[BaseException | None] = None
    doctor_response: ClassVar[DoctorReport | None] = None

    # account_id -> on_inbound callback, bound at connect() time.
    _live: ClassVar[dict[str, tuple[StubClient, InboundCallback]]] = {}

    @classmethod
    def reset_for_test(cls) -> None:
        cls.connect_calls = []
        cls.disconnect_calls = []
        cls.outbound_records = []
        cls.history_response = []
        cls.connect_should_fail = None
        cls.send_should_raise = None
        cls.send_visual_should_raise = None
        cls.doctor_response = None
        cls._live = {}

    async def connect(
        self,
        account: Connector,
        encryptor: Encryptor,
        on_inbound: InboundCallback,
    ) -> StubClient:
        StubPlugin.connect_calls.append(account.id)
        if StubPlugin.connect_should_fail is not None:
            raise StubPlugin.connect_should_fail
        client = StubClient(account.id)
        StubPlugin._live[account.id] = (client, on_inbound)
        return client

    async def disconnect(self, client: "StubClient") -> None:
        StubPlugin.disconnect_calls.append(client)
        StubPlugin._live.pop(client.account_id, None)
        client._alive = False

    async def doctor(self, account: Connector, encryptor: Encryptor) -> DoctorReport:
        if StubPlugin.doctor_response is not None:
            return StubPlugin.doctor_response
        return DoctorReport(status="ok", message="stub connector reachable", details={})

    @classmethod
    async def push_inbound(cls, account_id: str, envelope: InboundEnvelope) -> None:
        """Simulate the platform delivering ``envelope`` to a connected account.

        Raises :class:`ConnectorClientError` if ``account_id`` has no live
        connection (i.e. :meth:`connect` was never called or has since
        disconnected) — tests should ``connect`` first.
        """
        live = cls._live.get(account_id)
        if live is None:
            raise ConnectorClientError(f"stub account {account_id!r} is not connected")
        _client, on_inbound = live
        await on_inbound(envelope)

    @classmethod
    def mark_dead(cls, account_id: str) -> None:
        """Flip the live client's ``is_alive()`` to False — drives manager reconnect tests."""
        live = cls._live.get(account_id)
        if live is not None:
            live[0]._alive = False
