"""Tests for the connector subsystem foundation (mission 10 flight 01)."""

from __future__ import annotations

import dataclasses

import pytest

from the_one.connectors import (
    OPERATOR_VISIBILITY,
    PLATFORM_SEND_OK_PREFIX,
    ConnectorAuthRequired,
    ConnectorClient,
    ConnectorClientError,
    ConnectorConfigError,
    ConnectorConnectionError,
    ConnectorPlugin,
    ConnectorRateLimitError,
    ConnectorRegistrationError,
    ConnectorRegistry,
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
    SendResult,
    SessionKey,
)
from the_one.connectors.registry import (
    _registry,
    clear_for_test,
    register,
    register_builtin_connectors,
    register_for_test,
    resolve,
    restore_to_baseline_for_test,
    types,
)


@pytest.fixture
def clean_registry():
    """Reset the production registry to its production-shaped baseline before and after each test.

    Uses ``restore_to_baseline_for_test`` so the test starts where production
    starts (in flight 1: empty; in flight 8+: with discord pre-registered).
    Tests that want a TRULY empty registry post-fixture can call
    ``clear_for_test()`` after the fixture sets up.
    """
    restore_to_baseline_for_test()
    yield
    restore_to_baseline_for_test()


class TestConnectorExceptions:
    """The 6-type exception hierarchy."""

    def test_subclassing_chain(self) -> None:
        """Every leaf inherits from ConnectorClientError, which inherits from Exception."""
        for cls in (
            ConnectorConfigError,
            ConnectorConnectionError,
            ConnectorAuthRequired,
            ConnectorRegistrationError,
            ConnectorRateLimitError,
        ):
            assert issubclass(cls, ConnectorClientError), cls
        assert issubclass(ConnectorClientError, Exception)

    def test_config_error_message(self) -> None:
        exc = ConnectorConfigError(account_id="a1", validation_message="missing BOT_TOKEN")
        assert "a1" in str(exc)
        assert "missing BOT_TOKEN" in str(exc)
        # single-sentence: no newlines
        assert "\n" not in str(exc)

    def test_connection_error_constructible_plain(self) -> None:
        exc = ConnectorConnectionError("gateway timeout")
        assert "gateway timeout" in str(exc)

    def test_auth_required_carries_account_id(self) -> None:
        exc = ConnectorAuthRequired(account_id="a1", account_name="My Bot")
        assert exc.account_id == "a1"
        assert exc.account_name == "My Bot"
        assert "a1" in str(exc)

    def test_auth_required_account_name_optional(self) -> None:
        exc = ConnectorAuthRequired(account_id="a1")
        assert exc.account_name is None

    def test_registration_error(self) -> None:
        exc = ConnectorRegistrationError(type_name="discord", reason="already registered")
        assert "discord" in str(exc)
        assert "already registered" in str(exc)

    def test_rate_limit_with_retry_hint(self) -> None:
        exc = ConnectorRateLimitError(account_id="a1", retry_after_seconds=12.5)
        assert exc.retry_after_seconds == 12.5
        assert "12.5" in str(exc)

    def test_rate_limit_no_retry_hint(self) -> None:
        exc = ConnectorRateLimitError(account_id="a1")
        assert exc.retry_after_seconds is None
        assert "no retry hint" in str(exc)


class _MinimalPlugin:
    """In-test class that structurally satisfies :class:`ConnectorPlugin`.

    NO inheritance — structural satisfaction per agents.md convention.
    """

    async def connect(self, account, encryptor):  # noqa: ANN001  (test stub)
        return _MinimalClient()

    async def disconnect(self, client):  # noqa: ANN001
        return None

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="stub", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
        )


class _MinimalClient:
    """In-test class that structurally satisfies :class:`ConnectorClient`."""

    def is_alive(self) -> bool:
        return True

    async def send(self, target, content):  # noqa: ANN001  (test stub)
        return SendResult(platform_message_id=None, details={})


class _PluginMissingConnect:
    """Plugin stub missing the ``connect`` method — must FAIL isinstance check."""

    async def disconnect(self, client):  # noqa: ANN001
        return None

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="x", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(platform="x", account_id="x", channel_id="x")


class TestConnectorPluginProtocol:
    def test_minimal_plugin_satisfies_protocol(self) -> None:
        assert isinstance(_MinimalPlugin(), ConnectorPlugin)

    def test_plugin_missing_method_fails_check(self) -> None:
        assert not isinstance(_PluginMissingConnect(), ConnectorPlugin)

    def test_plugin_does_not_inherit_from_protocol(self) -> None:
        """Structural satisfaction means no inheritance."""
        assert ConnectorPlugin not in _MinimalPlugin.__mro__


class TestConnectorClientProtocol:
    def test_minimal_client_satisfies_protocol(self) -> None:
        assert isinstance(_MinimalClient(), ConnectorClient)

    def test_client_missing_is_alive_fails_check(self) -> None:
        class _NoMethod:
            pass

        assert not isinstance(_NoMethod(), ConnectorClient)

    def test_client_missing_send_fails_check(self) -> None:
        """After F4 widening, a client missing ``send`` fails the Protocol check.

        Mirrors ``test_plugin_missing_method_fails_check`` for the
        client-side widening. Locks the runtime_checkable semantic:
        method-name presence on the object at isinstance time, so
        clients written against the pre-F4 1-method shape will fail
        the widened check at runtime.
        """

        class _OnlyAlive:
            def is_alive(self) -> bool:
                return True

        assert not isinstance(_OnlyAlive(), ConnectorClient)


class TestConnectorPackageExports:
    def test_canonical_and_re_exports_resolve_to_same_object(self) -> None:
        """Convenience re-export is `is`-identical to the canonical import."""
        from the_one.connectors import ConnectorPlugin as ViaPackage
        from the_one.connectors.base import ConnectorPlugin as ViaCanonical

        assert ViaPackage is ViaCanonical

        from the_one.connectors import ConnectorClientError as ExcViaPackage
        from the_one.connectors.errors import ConnectorClientError as ExcViaCanonical

        assert ExcViaPackage is ExcViaCanonical

        from the_one.connectors import SendResult as SRViaPackage
        from the_one.connectors.base import SendResult as SRViaCanonical

        assert SRViaPackage is SRViaCanonical

    def test_supporting_types_round_trip(self) -> None:
        """Dataclass types are constructible and frozen."""
        env = InboundEnvelope(
            platform="stub",
            account_id="a1",
            channel_id="c1",
            thread_id=None,
            peer_id="p1",
            peer_name="Peer One",
            text="hi",
            raw={},
        )
        # Frozen — assignment must raise FrozenInstanceError specifically.
        with pytest.raises(dataclasses.FrozenInstanceError):
            env.text = "edited"  # type: ignore[misc]

        target = OutboundTarget(channel_id="c1")
        assert target.thread_id is None

        key = SessionKey(platform="stub", account_id="a1", channel_id="c1")
        # Hashable — usable as dict key.
        d = {key: "value"}
        assert d[SessionKey(platform="stub", account_id="a1", channel_id="c1")] == "value"

        rpt = DoctorReport(status="ok", message="ok", details={})
        assert rpt.status == "ok"

    def test_inbound_envelope_is_hashable_despite_dict_field(self) -> None:
        """InboundEnvelope.raw is excluded from hash via field(hash=False, compare=False)
        so the envelope is hashable on its scalar fields. Bare frozen+slots
        with a dict field constructs but blows up on hash() — locked here."""
        env = InboundEnvelope(
            platform="stub",
            account_id="a1",
            channel_id="c1",
            thread_id=None,
            peer_id="p1",
            peer_name="Peer One",
            text="hi",
            raw={"large": "payload"},
        )
        # Must not raise.
        h = hash(env)
        # Two envelopes that differ only in raw payload share the same hash
        # because raw is excluded from compare/hash.
        env2 = InboundEnvelope(
            platform="stub",
            account_id="a1",
            channel_id="c1",
            thread_id=None,
            peer_id="p1",
            peer_name="Peer One",
            text="hi",
            raw={"different": "payload"},
        )
        assert hash(env2) == h
        assert env == env2  # compare=False on raw means raw doesn't participate in __eq__

    def test_doctor_report_is_hashable_despite_dict_field(self) -> None:
        """DoctorReport.details is excluded from hash + eq — same contract
        as InboundEnvelope.raw."""
        rpt = DoctorReport(status="ok", message="connected", details={"token": "***"})
        h = hash(rpt)
        rpt2 = DoctorReport(status="ok", message="connected", details={"different": "x"})
        assert hash(rpt2) == h
        assert rpt == rpt2

    def test_send_result_is_hashable_despite_dict_field(self) -> None:
        """SendResult.details is excluded from hash + eq — same contract
        as InboundEnvelope.raw and DoctorReport.details. Bare frozen+slots
        with a dict field constructs but blows up on hash() without the
        ``field(hash=False, compare=False)`` discipline — locked here."""
        r = SendResult(platform_message_id="msg-1", details={"k": "v"})
        h = hash(r)  # must not raise
        r2 = SendResult(platform_message_id="msg-1", details={"different": "x"})
        # Same hash and equal — details doesn't participate in identity.
        assert hash(r2) == h
        assert r == r2
        # Frozen — assignment raises FrozenInstanceError specifically.
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.platform_message_id = "edited"  # type: ignore[misc]

    def test_send_result_accepts_none_platform_message_id(self) -> None:
        """``platform_message_id: str | None`` permits None for platforms
        that don't return a native message id. Pins the permissivity that
        leg 2's SendToPlatformChannelTool.execute() exploits."""
        r = SendResult(platform_message_id=None, details={})
        assert r.platform_message_id is None
        assert r.details == {}

    def test_platform_send_ok_prefix_constant(self) -> None:
        """The PLATFORM_SEND_OK_PREFIX literal is the cross-module contract.

        Produced by ``SendToPlatformChannelTool.execute()`` (F4 leg 2);
        consumed by the dispatcher's visibility-tagger (F4 leg 4) to
        decide ``visibility=None`` on the resulting tool_result message.
        """
        assert PLATFORM_SEND_OK_PREFIX == "[platform-send-ok]"

    def test_sync_method_falsely_satisfies_async_protocol(self) -> None:
        """Document a known runtime_checkable limitation: ``isinstance(obj,
        ConnectorPlugin)`` checks method NAMES only — a class with a sync
        ``def connect(...)`` (non-async) falsely passes the check. Real
        type errors surface at call time when ``await plugin.connect(...)``
        rejects a non-coroutine return. This test exists to make the
        known-limitation visible in the test suite so a future reader
        understands isinstance is necessary-but-not-sufficient."""

        class _SyncConnectStub:
            def connect(self, account, encryptor):  # NOTE: sync, not async
                return _MinimalClient()

            async def disconnect(self, client):
                return None

            async def doctor(self, account, encryptor):
                return DoctorReport(status="ok", message="x", details={})

            def normalize_session_key(self, inbound):
                return SessionKey(
                    platform=inbound.platform,
                    account_id=inbound.account_id,
                    channel_id=inbound.channel_id,
                )

        # Falsely passes — documenting the limitation, not endorsing it.
        assert isinstance(_SyncConnectStub(), ConnectorPlugin)


class TestConnectorRegistry:
    """The connector type registry — class, module-level singleton, and test seams."""

    def test_register_and_resolve_round_trip(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        plugin = resolve("stub")
        assert isinstance(plugin, ConnectorPlugin)
        assert isinstance(plugin, _MinimalPlugin)

    def test_resolve_unknown_type_raises_registration_error(self, clean_registry) -> None:
        with pytest.raises(ConnectorRegistrationError) as excinfo:
            resolve("nonexistent")
        assert "nonexistent" in str(excinfo.value)
        assert excinfo.value.type_name == "nonexistent"

    def test_duplicate_register_raises_registration_error(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        with pytest.raises(ConnectorRegistrationError) as excinfo:
            register("stub", _MinimalPlugin)
        assert "already registered" in str(excinfo.value)
        assert excinfo.value.type_name == "stub"

    def test_types_returns_sorted(self, clean_registry) -> None:
        # ``clean_registry`` restores the production baseline which (post-
        # F8 L2) includes ``"discord"``. Clear it so this test exercises
        # only its own registrations.
        clear_for_test()
        register("zebra", _MinimalPlugin)
        register("alpha", _MinimalPlugin)
        register("mango", _MinimalPlugin)
        assert types() == ["alpha", "mango", "zebra"]

    def test_register_for_test_bypasses_collision_check(self, clean_registry) -> None:
        # ``clean_registry`` restores the production baseline which (post-
        # F8 L2) includes ``"discord"``. Clear it so this test exercises
        # only its own registrations.
        clear_for_test()
        register("stub", _MinimalPlugin)
        # register_for_test must NOT raise on duplicate.
        register_for_test("stub", _MinimalPlugin)
        assert types() == ["stub"]

    def test_clear_for_test_empties_registry(self, clean_registry) -> None:
        # ``clean_registry`` restores the production baseline which (post-
        # F8 L2) includes ``"discord"``. Clear it first so the test
        # exercises only its own registrations.
        clear_for_test()
        register("stub_a", _MinimalPlugin)
        register("stub_b", _MinimalPlugin)
        assert len(types()) == 2
        clear_for_test()
        # clear_for_test is a HARD clear — does not re-run register_builtin_connectors.
        # Post-F8 L2 the baseline contains ``"discord"``; the hard clear
        # differs from baseline restoration here.
        assert types() == []

    def test_restore_to_baseline_re_runs_builtin_discovery(self, clean_registry) -> None:
        # F8 L2 changed the baseline: ``register_builtin_connectors`` now
        # registers ``"discord"`` (and ``"stub"`` remains test-only). The
        # test seam ``restore_to_baseline_for_test`` clears the registry
        # then re-runs the hook, so the resulting set is exactly the
        # production builtins.
        register_for_test("stub", _MinimalPlugin)
        assert "stub" in types()
        restore_to_baseline_for_test()
        assert types() == ["discord"]

    def test_module_level_functions_delegate_to_singleton(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        # Singleton state reflects the module-level call.
        assert "stub" in _registry.types()
        # Each resolve returns a FRESH instance — no instance cache. Locks
        # the "no instance cache" contract in the leg's design.
        via_module = resolve("stub")
        via_singleton = _registry.resolve("stub")
        assert type(via_module) is type(via_singleton)
        assert via_module is not via_singleton

    def test_fresh_registry_isolated_from_singleton(self, clean_registry) -> None:
        # ``clean_registry`` restores the production baseline which (post-
        # F8 L2) includes ``"discord"``. Clear the singleton so the
        # isolation contract reads against an empty singleton.
        clear_for_test()
        fresh = ConnectorRegistry()
        fresh.register("stub", _MinimalPlugin)
        # Singleton unchanged.
        assert types() == []
        # Fresh has the registration.
        assert fresh.types() == ["stub"]

    def test_register_builtin_connectors_is_idempotent(self, clean_registry) -> None:
        # F8 L2 changed the body to ``register("discord", DiscordPlugin)``;
        # the hook uses a check-before-register guard so calling it
        # repeatedly does NOT raise. The pinned contract is "calling twice
        # leaves the registry in the same shape as calling once," which
        # ``restore_to_baseline_for_test`` relies on (it does clear +
        # re-run, so a non-idempotent hook would still work — but the
        # broader idempotency contract is what tests like
        # ``test_resolve_plugin_called_after_baseline_restore`` lean on).
        register_builtin_connectors()
        register_builtin_connectors()
        assert types() == ["discord"]

    def test_resolve_rejects_plugin_that_does_not_satisfy_protocol(self, clean_registry) -> None:
        """`resolve` defensively isinstance-checks the produced plugin against
        ConnectorPlugin. A class that doesn't structurally satisfy the
        Protocol raises ConnectorRegistrationError rather than handing back
        a non-conforming instance that surfaces deep in the lifecycle pool."""

        class _NotAPlugin:
            """No connect, no disconnect, no doctor, no normalize_session_key."""

            pass

        register_for_test("broken", _NotAPlugin)  # bypass register's static-check
        with pytest.raises(ConnectorRegistrationError) as excinfo:
            resolve("broken")
        assert "does not satisfy" in str(excinfo.value).lower()
        assert excinfo.value.type_name == "broken"


# ---------------------------------------------------------------------------
# M10 F03 L02 — OPERATOR_VISIBILITY constant
# ---------------------------------------------------------------------------


def test_operator_visibility_constant_value_and_export() -> None:
    """``OPERATOR_VISIBILITY`` is the single source of truth for the
    operator-visibility tag string. F3 L4 dispatcher, F4 platform-send tool,
    and F5 Chat-UI operator-input path all import this constant rather than
    duplicating the literal — typos like ``"opperator"`` are caught at
    import/IDE time instead of persisting silently in stored messages.
    """
    assert OPERATOR_VISIBILITY == "operator"
