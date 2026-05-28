"""In-process stub plugin + client — cross-flight regression fixture.

This stub is the canonical end-to-end test fixture for Mission 10. Flights
2-10 import :class:`StubPlugin` and register it via
:func:`the_one.connectors.registry.register_for_test` to exercise their
own pipelines without invoking real platform APIs.

Distinct from the narrow ``_StubPlugin`` / ``_StubClient`` helpers in
:mod:`tests.test_connectors_pool` (leg 5/6 deliverables, which test pool
internals only) and ``_MinimalPlugin`` / ``_MinimalClient`` in
:mod:`tests.test_connectors` (leg 3/4 deliverables, which test the protocol
and registry surfaces). The stub here has class-level recording buffers and
scenario knobs that those narrow helpers don't carry — appropriate for
cross-flight integration tests, overkill for internal-protocol tests.

Underscore-prefixed module (private API). NOT registered via
:func:`the_one.connectors.registry.register_builtin_connectors` — tests
register it explicitly via :func:`register_for_test`. Production code MUST
NOT import this module.

The ``'stub'`` type name is reserved for tests. Production flights register
real connector types (``'discord'`` in Flight 8, the second platform in
Flight 9). Schema v13 has no CHECK constraint on ``connector_accounts.type``
(the v23 rename to ``connectors`` happens post-v13),
so persisting a ``'stub'``-typed account in tests works at the DB layer.
"""

from __future__ import annotations

from typing import ClassVar

from the_one.connectors.base import (
    ConnectorClient,
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
    SendResult,
    SessionKey,
)
from the_one.db.models import Connector
from the_one.encryption import Encryptor


class StubClient:
    """In-process :class:`ConnectorClient` — structurally satisfies the Protocol."""

    def __init__(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    async def send(
        self,
        target: OutboundTarget,
        content: str,
    ) -> SendResult:
        """Record the outbound on :class:`StubPlugin` and return a fixed result.

        Mirrors :meth:`StubPlugin.connect`'s failure-injection pattern: when
        :attr:`StubPlugin.send_should_raise` is set, raise it INSTEAD of
        recording / returning. Otherwise append ``(target, content)`` to
        :attr:`StubPlugin.outbound_records` via
        :meth:`StubPlugin.record_outbound` and return a fixed
        :class:`SendResult` with ``platform_message_id="stub-msg-id"``.
        """
        if StubPlugin.send_should_raise is not None:
            raise StubPlugin.send_should_raise
        StubPlugin.record_outbound(target, content)
        return SendResult(platform_message_id="stub-msg-id", details={})


class StubPlugin:
    """In-process :class:`ConnectorPlugin` — cross-flight regression fixture.

    Class-level recording buffers and scenario knobs let tests assert what
    flowed through and inject failure scenarios. Each test that uses the
    stub MUST call :meth:`reset_for_test` (or rely on an autouse fixture
    that does so) to prevent cross-test state leakage.
    """

    # ── Recording buffers (class-level) ────────────────────────────────
    connect_calls: ClassVar[list[tuple[str, str]]] = []
    """List of ``(account.id, account.type)`` tuples; one per :meth:`connect` call."""

    disconnect_calls: ClassVar[list[ConnectorClient]] = []
    """List of clients passed to :meth:`disconnect`.

    Typed as :class:`ConnectorClient` (the Protocol), not :class:`StubClient`,
    because that's the parameter type on :meth:`disconnect`. At runtime
    the appended values are always :class:`StubClient` instances in this
    stub, but the buffer type matches the contract.
    """

    doctor_calls: ClassVar[list[tuple[str, str]]] = []
    """List of ``(account.id, account.type)`` tuples; one per :meth:`doctor` call."""

    inbound_records: ClassVar[list[InboundEnvelope]] = []
    """Inbound envelopes pushed via :meth:`push_inbound` (test helper)."""

    outbound_records: ClassVar[list[tuple[OutboundTarget, str]]] = []
    """``(target, content)`` tuples pushed via :meth:`record_outbound` (test helper).

    Flight 4 will land the real platform-send tool that produces these
    records; until then, tests call :meth:`record_outbound` directly to
    simulate the tool's behaviour.
    """

    # ── Scenario knobs (class-level) ───────────────────────────────────
    doctor_response: ClassVar[DoctorReport | None] = None
    """When set, :meth:`doctor` returns this instead of a default success report."""

    connect_should_fail: ClassVar[BaseException | None] = None
    """When set, :meth:`connect` raises this instead of returning a client."""

    doctor_should_raise: ClassVar[BaseException | None] = None
    """When set, :meth:`doctor` raises this INSTEAD of returning a
    :class:`DoctorReport`. Tests use it to drive the
    ``ConnectorClientError`` path of the doctor-probe endpoint
    (mirrors :attr:`connect_should_fail`). :meth:`reset_for_test`
    clears this between tests.
    """

    send_should_raise: ClassVar[BaseException | None] = None
    """When set, :meth:`StubClient.send` raises this INSTEAD of recording
    the outbound and returning a :class:`SendResult`. Tests use it to
    drive the failure path of the platform-send tool (mirrors
    :attr:`connect_should_fail` semantics). :meth:`reset_for_test`
    clears this between tests.
    """

    # ── Test-side helpers ──────────────────────────────────────────────
    @classmethod
    def reset_for_test(cls) -> None:
        """Reset all class-level state. Call from an autouse fixture."""
        cls.connect_calls = []
        cls.disconnect_calls = []
        cls.doctor_calls = []
        cls.inbound_records = []
        cls.outbound_records = []
        cls.doctor_response = None
        cls.connect_should_fail = None
        cls.doctor_should_raise = None
        cls.send_should_raise = None

    @classmethod
    def push_inbound(cls, envelope: InboundEnvelope) -> None:
        """Simulate the plugin's gateway receiving an inbound message.

        In production this would be driven by the platform's event loop
        (Discord gateway dispatch, Slack Socket Mode receive, etc.).
        Tests push directly to exercise the downstream dispatch.
        """
        cls.inbound_records.append(envelope)

    @classmethod
    def record_outbound(cls, target: OutboundTarget, content: str) -> None:
        """Simulate the agent dispatching outbound through this plugin.

        Flight 4's platform-send tool will produce these records when it
        lands; until then, tests call this directly to simulate the
        tool's behaviour.
        """
        cls.outbound_records.append((target, content))

    # ── Protocol surface ──────────────────────────────────────────────
    async def connect(
        self,
        account: Connector,
        encryptor: Encryptor,
    ) -> StubClient:
        type(self).connect_calls.append((account.id, account.type))
        if type(self).connect_should_fail is not None:
            raise type(self).connect_should_fail
        return StubClient()

    async def disconnect(self, client: ConnectorClient) -> None:
        type(self).disconnect_calls.append(client)
        # Stub-specific: the production ConnectorClient Protocol has no
        # writable `_alive` field; this stub's StubClient does, so flip it
        # when disconnect is called to make `is_alive()` return False.
        if isinstance(client, StubClient):
            client._alive = False

    async def doctor(
        self,
        account: Connector,
        encryptor: Encryptor,
    ) -> DoctorReport:
        type(self).doctor_calls.append((account.id, account.type))
        if type(self).doctor_should_raise is not None:
            raise type(self).doctor_should_raise
        if type(self).doctor_response is not None:
            return type(self).doctor_response
        return DoctorReport(
            status="ok",
            message="stub probe ok",
            details={},
        )

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
            thread_id=inbound.thread_id,
            peer_id=inbound.peer_id,
        )

    def display_channel(self, envelope: InboundEnvelope) -> str:
        """Render a human-readable channel label for session-title derivation.

        OPTIONAL hook accessed via ``getattr`` by
        :func:`the_one.connectors._session._derive_title`. Real plugins
        can return platform-native labels (e.g. ``"#engineering"`` for
        Discord guild channels, ``"@alice"`` for Slack DMs). The stub
        returns a synthetic label encoding the channel id.

        See ``the_one/connectors/README.md`` "Optional hooks" section
        for the convention.
        """
        return f"stub:{envelope.channel_id}"
