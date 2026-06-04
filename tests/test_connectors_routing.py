"""Routing-engine tests for F7 L4's ``connectors/_routing.py``.

Pins the 5-step algorithm:

1. Override from ``session_metadata["routing_override"]``.
2. Rule-walk against ``config["routing"]["rules"]`` in declared order.
3. Per-account default agent.
4. First-eligible-alphabetical attached agent.
5. No-eligible deny.

Plus scope-match semantics (channel / thread / dm / peer); ACL
admission via :func:`admits_inbound`; ``RoutingDecision`` dataclass
surface (frozen, slotted, equal, hashable, canonical-import
identity).

Inline minimal fixtures — mirrors ``tests/test_connectors_acl.py``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tests._acl_shape_helpers import _to_v24_shape
from the_one.agent.config import AgentConfig
from the_one.connectors._routing import RoutingDecision, resolve_routing
from the_one.connectors.base import InboundEnvelope
from the_one.db.models import Connector


def _account(
    *,
    account_id: str = "acct-test",
    allowlist: dict | None = None,
    routing: dict | None = None,
) -> Connector:
    """Build a minimal Connector with optional allowlist/routing."""
    config: dict = {}
    if allowlist is not None:
        config["allowlist"] = _to_v24_shape(allowlist)
    if routing is not None:
        config["routing"] = routing
    return Connector(
        id=account_id,
        name="Test Account",
        type="stub",
        config=config,
        secrets={},
    )


def _envelope(
    *,
    channel_id: str = "ch-1",
    thread_id: str | None = None,
    peer_id: str = "peer-1",
    account_id: str = "acct-test",
) -> InboundEnvelope:
    return InboundEnvelope(
        platform="stub",
        account_id=account_id,
        channel_id=channel_id,
        thread_id=thread_id,
        peer_id=peer_id,
        peer_name="Alice",
        text="hello",
        raw={},
    )


def _agent(
    name: str,
    *,
    connector_ids: list[str] | None = None,
    connector_acls: dict | None = None,
) -> AgentConfig:
    return AgentConfig(
        name=name,
        provider_config_id="mock-provider",
        llm_model="mock",
        connector_ids=(connector_ids if connector_ids is not None else ["acct-test"]),
        connector_acls=connector_acls,
    )


# ─────────────────────────────────────────────────────────────────
# RoutingDecision dataclass surface
# ─────────────────────────────────────────────────────────────────


class TestRoutingDecision:
    """Pin ``RoutingDecision``'s dataclass surface: frozen, slotted,
    equal, hashable, canonical-import identity."""

    def test_construct_with_all_fields(self) -> None:
        d = RoutingDecision(
            agent="alice",
            rule_index=0,
            scope="channel",
            match="C1",
            reason="rule-match",
        )
        assert d.agent == "alice"
        assert d.rule_index == 0
        assert d.scope == "channel"
        assert d.match == "C1"
        assert d.reason == "rule-match"

    def test_frozen_mutation_raises(self) -> None:
        d = RoutingDecision(
            agent="alice",
            rule_index=0,
            scope="channel",
            match="C1",
            reason="rule-match",
        )
        with pytest.raises(FrozenInstanceError):
            d.agent = "bob"  # type: ignore[misc]

    def test_equality_and_hashability(self) -> None:
        d1 = RoutingDecision(
            agent="alice",
            rule_index=0,
            scope="channel",
            match="C1",
            reason="rule-match",
        )
        d2 = RoutingDecision(
            agent="alice",
            rule_index=0,
            scope="channel",
            match="C1",
            reason="rule-match",
        )
        d3 = RoutingDecision(
            agent="bob",
            rule_index=0,
            scope="channel",
            match="C1",
            reason="rule-match",
        )
        assert d1 == d2
        # Hashable (frozen + slots + scalar fields).
        assert hash(d1) == hash(d2)
        assert {d1, d2, d3} == {d1, d3}

    def test_slots_blocks_attribute_addition(self) -> None:
        """``slots=True`` means no ``__dict__`` — confirms the dataclass
        is truly slotted (mirrors the type-level surface guarantee).
        Combined with ``frozen=True`` setting any attribute (including
        an unlisted one) raises — exact exception type is interpreter-
        defined (``FrozenInstanceError`` / ``TypeError`` /
        ``AttributeError`` per implementation), so assert via the
        slot-level introspection instead."""
        d = RoutingDecision(
            agent="alice",
            rule_index=0,
            scope="channel",
            match="C1",
            reason="rule-match",
        )
        assert not hasattr(d, "__dict__")
        assert RoutingDecision.__slots__ == (
            "agent",
            "rule_index",
            "scope",
            "match",
            "reason",
        )

    def test_canonical_import_identity(self) -> None:
        """``RoutingDecision.__module__`` pins the canonical import
        path — mirrors ``_default_permit``'s assertion in
        ``test_connectors_resolver.py``."""
        assert RoutingDecision.__module__ == "the_one.connectors._routing"


# ─────────────────────────────────────────────────────────────────
# resolve_routing — 5-step algorithm matrix
# ─────────────────────────────────────────────────────────────────


class TestResolveRouting:
    """Pin the 5-step algorithm matrix + scope-match semantics."""

    # ── Step 1 — Override ─────────────────────────────────────────

    def test_step1_override_with_eligible_agent_short_circuits(self) -> None:
        """Override pointing to an eligible agent returns immediately —
        no rule-walk, no default consultation."""
        alice = _agent("alice")
        bob = _agent("bob")
        # Add a rule that would route to bob if we fell through.
        account = _account(
            routing={
                "rules": [
                    {"scope": "channel", "match": ["ch-1"], "agent": "bob"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(),
            [alice, bob],
            {"routing_override": "alice"},
        )
        assert decision == RoutingDecision(
            agent="alice",
            rule_index=None,
            scope="override",
            match=None,
            reason="override",
        )

    def test_step1_override_to_ineligible_agent_falls_through_to_rule_walk(
        self,
    ) -> None:
        """Override to an agent NOT in eligible_attached_agents → fall
        through; the rule-walk's first match wins."""
        alice = _agent("alice")
        bob = _agent("bob")
        account = _account(
            routing={
                "rules": [
                    {"scope": "channel", "match": ["ch-1"], "agent": "bob"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(),
            [alice, bob],
            # "charlie" not in eligible list → override ignored.
            {"routing_override": "charlie"},
        )
        assert decision.agent == "bob"
        assert decision.reason == "rule-match"
        assert decision.rule_index == 0
        assert decision.scope == "channel"
        assert decision.match == "ch-1"

    def test_step1_override_to_acl_denied_agent_falls_through(self) -> None:
        """Override pointing to an attached agent whose per-agent ACL
        denies → fall through."""
        # alice is attached but per-agent ACL denies on the peers axis.
        alice = _agent(
            "alice",
            connector_acls={"acct-test": {"peers": [], "channels": None}},
        )
        bob = _agent("bob")
        account = _account(
            routing={
                "rules": [
                    {"scope": "peer", "match": ["peer-1"], "agent": "bob"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(),
            [alice, bob],
            {"routing_override": "alice"},
        )
        assert decision.agent == "bob"
        assert decision.reason == "rule-match"

    def test_step1_override_empty_string_falls_through(self) -> None:
        """Override is ``""`` → fall through (no agent named ``""``)."""
        alice = _agent("alice")
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alice],
            {"routing_override": ""},
        )
        # Falls through to step 4 (no routing config; alice is eligible).
        assert decision.agent == "alice"
        assert decision.reason == "first-eligible"

    def test_step1_session_metadata_none_falls_through(self) -> None:
        """``session_metadata=None`` → step 1 skipped via
        ``(session_metadata or {})``; falls through to step 4."""
        alice = _agent("alice")
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alice],
            None,
        )
        assert decision.agent == "alice"
        assert decision.reason == "first-eligible"

    def test_step1_override_non_string_falls_through(self) -> None:
        """Defensive: ``routing_override`` is not a string (e.g. ``42``
        from a malformed write) → ``isinstance`` guard skips step 1."""
        alice = _agent("alice")
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alice],
            {"routing_override": 42},
        )
        assert decision.agent == "alice"
        assert decision.reason == "first-eligible"

    # ── Step 2 — Rule-walk: scope-match semantics ─────────────────

    def test_step2_channel_rule_matches(self) -> None:
        """Single channel rule, envelope's channel_id matches → rule
        wins; rule_index pinned."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {"scope": "channel", "match": ["ch-1"], "agent": "alice"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(account, _envelope(), [alice], None)
        assert decision == RoutingDecision(
            agent="alice",
            rule_index=0,
            scope="channel",
            match="ch-1",
            reason="rule-match",
        )

    def test_step2_thread_rule_matches(self) -> None:
        """Single thread rule, envelope's thread_id matches → rule wins."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {"scope": "thread", "match": ["T1"], "agent": "alice"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(thread_id="T1"),
            [alice],
            None,
        )
        assert decision.agent == "alice"
        assert decision.reason == "rule-match"
        assert decision.scope == "thread"
        assert decision.match == "T1"
        assert decision.rule_index == 0

    def test_step2_thread_rule_skipped_for_non_thread_envelope(self) -> None:
        """``envelope.thread_id is None`` → thread rule is skipped;
        falls through to step 4."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {"scope": "thread", "match": ["T1"], "agent": "alice"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(thread_id=None),
            [alice],
            None,
        )
        assert decision.reason == "first-eligible"
        assert decision.agent == "alice"

    def test_step2_dm_rule_matches_top_level_conversation(self) -> None:
        """``envelope.thread_id is None AND peer_id == match`` → dm
        rule wins."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {"scope": "dm", "match": ["peer-1"], "agent": "alice"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(thread_id=None, peer_id="peer-1"),
            [alice],
            None,
        )
        assert decision.agent == "alice"
        assert decision.reason == "rule-match"
        assert decision.scope == "dm"
        assert decision.match == "peer-1"

    def test_step2_dm_rule_skipped_for_thread_envelope(self) -> None:
        """``envelope.thread_id is not None`` → dm rule is skipped
        even when peer_id matches; falls through."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {"scope": "dm", "match": ["peer-1"], "agent": "alice"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(thread_id="T1", peer_id="peer-1"),
            [alice],
            None,
        )
        assert decision.reason == "first-eligible"
        assert decision.agent == "alice"

    @pytest.mark.parametrize(
        "thread_id",
        [None, "T1"],
        ids=["non_thread_envelope", "thread_envelope"],
    )
    def test_step2_peer_rule_matches_regardless_of_channel(self, thread_id: str | None) -> None:
        """Peer rule matches on ``peer_id`` regardless of
        channel_id / thread_id. Parameterized to pin the "regardless of
        channel_id/thread_id" claim explicitly across both shapes."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {"scope": "peer", "match": ["peer-1"], "agent": "alice"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(
                channel_id="ch-different",
                thread_id=thread_id,
                peer_id="peer-1",
            ),
            [alice],
            None,
        )
        assert decision.agent == "alice"
        assert decision.reason == "rule-match"
        assert decision.scope == "peer"
        assert decision.match == "peer-1"

    def test_step2_channel_rule_matches_thread_message_in_matched_channel(
        self,
    ) -> None:
        """A thread message inside a matched channel still matches a
        channel rule UNLESS an earlier thread rule won. Pins the
        docstring claim."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {"scope": "channel", "match": ["C1"], "agent": "alice"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(
            account,
            _envelope(channel_id="C1", thread_id="T1"),
            [alice],
            None,
        )
        assert decision.agent == "alice"
        assert decision.reason == "rule-match"
        assert decision.scope == "channel"
        assert decision.match == "C1"

    def test_step2_unknown_scope_rule_skipped(self) -> None:
        """Defensive: an unknown-scope rule (would be rejected by the
        L2 validator at write time, but constructible via
        ``model_construct``) is skipped by ``_scope_matches``; falls
        through. Pins the unknown-scope branch."""
        alice = _agent("alice")
        # Bypass the L2 validator with model_construct.
        account = Connector.model_construct(
            id="acct-test",
            name="Test Account",
            type="stub",
            config={
                "routing": {
                    "rules": [
                        {"scope": "weird", "match": ["x"], "agent": "alice"},
                    ],
                    "default": None,
                }
            },
            secrets={},
        )
        decision = resolve_routing(account, _envelope(), [alice], None)
        # Falls through past step 2 to step 4 (no default).
        assert decision.agent == "alice"
        assert decision.reason == "first-eligible"

    def test_step2_multi_value_match_fires_for_each_listed_value(self) -> None:
        """A rule with ``match: ["C1", "C2"]`` fires for envelopes whose
        ``channel_id`` is EITHER ``"C1"`` OR ``"C2"`` — the per-rule
        match list has set-membership / OR semantics. ``decision.match``
        records the SINGLE envelope value that hit, not the full list."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [
                    {
                        "scope": "channel",
                        "match": ["C1", "C2"],
                        "agent": "alice",
                    },
                ],
                "default": None,
            }
        )
        # Hits via C1.
        decision_c1 = resolve_routing(
            account,
            _envelope(channel_id="C1"),
            [alice],
            None,
        )
        assert decision_c1.agent == "alice"
        assert decision_c1.reason == "rule-match"
        assert decision_c1.scope == "channel"
        assert decision_c1.match == "C1"
        # Hits via C2 — same rule, different envelope value.
        decision_c2 = resolve_routing(
            account,
            _envelope(channel_id="C2"),
            [alice],
            None,
        )
        assert decision_c2.agent == "alice"
        assert decision_c2.reason == "rule-match"
        assert decision_c2.scope == "channel"
        assert decision_c2.match == "C2"
        # Misses both values → falls through to first-eligible.
        decision_miss = resolve_routing(
            account,
            _envelope(channel_id="C3"),
            [alice],
            None,
        )
        assert decision_miss.reason == "first-eligible"

    def test_step2_first_match_wins_in_declared_order(self) -> None:
        """Two channel rules both could match; the FIRST declared wins;
        rule_index = 0."""
        alice = _agent("alice")
        bob = _agent("bob")
        account = _account(
            routing={
                "rules": [
                    {"scope": "channel", "match": ["ch-1"], "agent": "alice"},
                    {"scope": "channel", "match": ["ch-1"], "agent": "bob"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(account, _envelope(), [alice, bob], None)
        assert decision.agent == "alice"
        assert decision.rule_index == 0
        assert decision.reason == "rule-match"

    def test_step2_rule_with_ineligible_agent_skipped(self) -> None:
        """Rule's ``agent`` is not in eligible_attached_agents → rule
        skipped; next rule wins."""
        alice = _agent("alice")
        bob = _agent("bob")
        account = _account(
            routing={
                "rules": [
                    # "charlie" is not attached → skipped.
                    {"scope": "channel", "match": ["ch-1"], "agent": "charlie"},
                    {"scope": "channel", "match": ["ch-1"], "agent": "bob"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(account, _envelope(), [alice, bob], None)
        assert decision.agent == "bob"
        assert decision.rule_index == 1
        assert decision.reason == "rule-match"

    def test_step2_rule_with_acl_denied_agent_skipped(self) -> None:
        """Rule's target agent is attached but ACL denies → rule
        skipped; next rule wins."""
        # alice attached but per-agent ACL denies on peers axis.
        alice = _agent(
            "alice",
            connector_acls={"acct-test": {"peers": [], "channels": None}},
        )
        bob = _agent("bob")
        account = _account(
            routing={
                "rules": [
                    {"scope": "channel", "match": ["ch-1"], "agent": "alice"},
                    {"scope": "channel", "match": ["ch-1"], "agent": "bob"},
                ],
                "default": None,
            }
        )
        decision = resolve_routing(account, _envelope(), [alice, bob], None)
        assert decision.agent == "bob"
        assert decision.rule_index == 1
        assert decision.reason == "rule-match"

    # ── Step 3 — Per-account default ──────────────────────────────

    def test_step3_default_returns_when_no_rules_match(self) -> None:
        """``config["routing"]["default"] = "alice"``; alice is
        eligible + ACL permits → default wins."""
        alice = _agent("alice")
        bob = _agent("bob")
        account = _account(
            routing={
                # Rule won't match this envelope.
                "rules": [
                    {"scope": "channel", "match": ["ch-different"], "agent": "bob"},
                ],
                "default": "alice",
            }
        )
        decision = resolve_routing(account, _envelope(), [alice, bob], None)
        assert decision == RoutingDecision(
            agent="alice",
            rule_index=None,
            scope="default",
            match=None,
            reason="default",
        )

    def test_step3_default_ineligible_falls_through_to_first_eligible(
        self,
    ) -> None:
        """Default points to an unattached agent → falls through to
        step 4."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [],
                "default": "charlie",  # unattached
            }
        )
        decision = resolve_routing(account, _envelope(), [alice], None)
        assert decision.agent == "alice"
        assert decision.reason == "first-eligible"

    def test_step3_default_acl_denied_falls_through(self) -> None:
        """Default is attached but ACL denies → falls through to step 4."""
        # alice's default would match if not for ACL deny.
        alice = _agent(
            "alice",
            connector_acls={"acct-test": {"peers": [], "channels": None}},
        )
        bob = _agent("bob")
        account = _account(
            routing={
                "rules": [],
                "default": "alice",
            }
        )
        decision = resolve_routing(account, _envelope(), [alice, bob], None)
        # alice denied; falls through to first-eligible (which skips alice
        # and lands bob).
        assert decision.agent == "bob"
        assert decision.reason == "first-eligible"

    def test_step3_default_none_falls_through(self) -> None:
        """``config["routing"]["default"] is None`` → falls through."""
        alice = _agent("alice")
        account = _account(
            routing={
                "rules": [],
                "default": None,
            }
        )
        decision = resolve_routing(account, _envelope(), [alice], None)
        assert decision.agent == "alice"
        assert decision.reason == "first-eligible"

    # ── Step 4 — First-eligible-alphabetical ──────────────────────

    def test_step4_first_eligible_alphabetical(self) -> None:
        """Eligible list ``[alpha, beta, charlie]``; all ACL-permit →
        alpha returned with reason ``"first-eligible"``."""
        alpha = _agent("alpha")
        beta = _agent("beta")
        charlie = _agent("charlie")
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alpha, beta, charlie],
            None,
        )
        assert decision == RoutingDecision(
            agent="alpha",
            rule_index=None,
            scope="first-eligible",
            match=None,
            reason="first-eligible",
        )

    def test_step4_skips_acl_denied_agents(self) -> None:
        """Eligible list ``[alpha, beta, charlie]``; alpha denied; beta
        permitted → beta returned."""
        alpha = _agent(
            "alpha",
            connector_acls={"acct-test": {"peers": [], "channels": None}},
        )
        beta = _agent("beta")
        charlie = _agent("charlie")
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alpha, beta, charlie],
            None,
        )
        assert decision.agent == "beta"
        assert decision.reason == "first-eligible"

    # ── Step 5 — No-eligible ──────────────────────────────────────

    def test_step5_no_eligible_when_all_denied(self) -> None:
        """Eligible list ``[alpha]``; ACL denies → ``agent=None``;
        reason ``"no-eligible-agent"``."""
        alpha = _agent(
            "alpha",
            connector_acls={"acct-test": {"peers": [], "channels": None}},
        )
        decision = resolve_routing(_account(), _envelope(), [alpha], None)
        assert decision == RoutingDecision(
            agent=None,
            rule_index=None,
            scope="no-eligible-agent",
            match=None,
            reason="no-eligible-agent",
        )

    def test_step5_no_eligible_when_list_empty(self) -> None:
        """Eligible list ``[]`` → no-eligible."""
        decision = resolve_routing(_account(), _envelope(), [], None)
        assert decision.agent is None
        assert decision.reason == "no-eligible-agent"
        assert decision.scope == "no-eligible-agent"

    # ── Fall-through composition cases ────────────────────────────

    def test_no_routing_config_falls_through_to_step4(self) -> None:
        """``account.config = {}`` (no routing key) → bypass steps 2-3
        → step 4 first-eligible-alphabetical."""
        alpha = _agent("alpha")
        beta = _agent("beta")
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alpha, beta],
            None,
        )
        assert decision.agent == "alpha"
        assert decision.reason == "first-eligible"

    def test_routing_rules_empty_list_falls_through_to_default(self) -> None:
        """``config["routing"] = {"rules": [], "default": "alice"}`` →
        step 2 trivially yields nothing → step 3 default."""
        alice = _agent("alice")
        bob = _agent("bob")
        account = _account(
            routing={
                "rules": [],
                "default": "alice",
            }
        )
        decision = resolve_routing(account, _envelope(), [alice, bob], None)
        assert decision.agent == "alice"
        assert decision.reason == "default"


# ─────────────────────────────────────────────────────────────────
# M10 F8 L6 — ``_agent_admits`` plugin ``is_dm`` consult
# ─────────────────────────────────────────────────────────────────


class _IsDmPlugin:
    """Test-only plugin stub exposing only the ``is_dm`` hook.

    Mirrors the F8 L6 ``DiscordPlugin.is_dm`` shape (sync callable on
    ``InboundEnvelope``). Other Protocol methods are absent — the
    ``getattr`` sentinel consult site only reaches for ``is_dm`` so
    the routing engine doesn't trip on the missing surface.
    """

    def __init__(self, result: bool) -> None:
        self._result = result

    def is_dm(self, envelope: InboundEnvelope) -> bool:
        return self._result


class _NoHooksPlugin:
    """Test-only plugin stub that does NOT implement ``is_dm``.

    Mirrors the test-only stub plugin's shape — the consult site
    falls back to :func:`_default_not_dm` (returning False) so the
    DMs-only branch keeps its historical fail-closed semantic for
    plugins without the optional hook.
    """


class TestAgentAdmitsIsDmHook:
    """F8 L6 — ``_agent_admits`` consults ``plugin.is_dm`` for the
    per-agent DMs-only ACL branch."""

    def test_plugin_with_is_dm_true_permits_dms_only_branch(self) -> None:
        """Eligible list ``[alpha]`` with DMs-only ACL
        (``channels: []``); plugin reports ``is_dm=True`` → step-4
        first-eligible permits alpha (the DMs-only branch flips from
        deny to permit)."""
        alpha = _agent(
            "alpha",
            connector_acls={"acct-test": {"peers": None, "channels": []}},
        )
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alpha],
            None,
            plugin=_IsDmPlugin(result=True),
        )
        assert decision.agent == "alpha"
        assert decision.reason == "first-eligible"

    def test_plugin_without_is_dm_denies_dms_only_branch(self) -> None:
        """Eligible list ``[alpha]`` with DMs-only ACL
        (``channels: []``); plugin does NOT implement ``is_dm`` →
        :func:`_default_not_dm` fallback returns False → DMs-only
        branch denies → no-eligible. Pins the F8 back-compat
        invariant: pre-F8 plugins (e.g. the test-only stub) keep
        their historical fail-closed behavior byte-identically."""
        alpha = _agent(
            "alpha",
            connector_acls={"acct-test": {"peers": None, "channels": []}},
        )
        decision = resolve_routing(
            _account(),
            _envelope(),
            [alpha],
            None,
            plugin=_NoHooksPlugin(),
        )
        assert decision.agent is None
        assert decision.reason == "no-eligible-agent"


# ─────────────────────────────────────────────────────────────────
# M10 F8 L8 — ``_agent_admits`` threads guild_id + member_roles
# ─────────────────────────────────────────────────────────────────


def _envelope_with_guild(
    *,
    guild_id: str | None,
    member_roles: list[str],
    channel_id: str = "ch-1",
    peer_id: str = "peer-1",
    account_id: str = "acct-test",
) -> InboundEnvelope:
    """Builder for an envelope whose ``raw`` carries the L4-populated
    ``guild_id`` and ``member_roles`` keys that L8 reads."""
    return InboundEnvelope(
        platform="stub",
        account_id=account_id,
        channel_id=channel_id,
        thread_id=None,
        peer_id=peer_id,
        peer_name="Alice",
        text="hello",
        raw={"guild_id": guild_id, "member_roles": member_roles},
    )


class TestAgentAdmitsThreadsGuildIdAndMemberRoles:
    """L8 — ``_routing._agent_admits`` reads
    ``envelope.raw["guild_id"]`` and ``envelope.raw["member_roles"]``
    and passes them into :func:`admits_inbound`. Pins the integration:
    an account-scope ``guilds`` restriction must take effect at the
    routing-engine layer, not just at the pure-function layer."""

    def test_routing_consults_guild_id_from_envelope_raw(self) -> None:
        """Account-scope ``guilds=["G1"]`` + envelope ``guild_id="G2"``
        → ACL denies → no eligible. Pins the L8 threading."""
        alpha = _agent("alpha")
        account = _account(
            allowlist={
                "peers": [],
                "channels": [],
                "guilds": ["G1"],
            }
        )
        envelope = _envelope_with_guild(
            guild_id="G2",
            member_roles=[],
        )
        decision = resolve_routing(account, envelope, [alpha], None)
        # G2 not in allowlist → ACL denies → no eligible agent.
        assert decision.agent is None
        assert decision.reason == "no-eligible-agent"

    def test_routing_consults_member_roles_from_envelope_raw(self) -> None:
        """Account-scope ``roles=[{guild_id="G1", role_id="R1"}]`` +
        envelope ``member_roles=[]`` → ACL denies → no eligible. Pins
        the L8 threading on the roles axis.

        M11 F12 L5 — the role entry must carry a non-null guild_id
        matching the envelope's guild_id; pass the structured tuple
        directly to bypass the flat-string fixture default."""
        alpha = _agent("alpha")
        account = _account(
            allowlist={
                "peers": [],
                "channels": [],
                "roles": [{"guild_id": "G1", "role_id": "R1"}],
            }
        )
        envelope = _envelope_with_guild(
            guild_id="G1",
            member_roles=[],
        )
        decision = resolve_routing(account, envelope, [alpha], None)
        assert decision.agent is None
        assert decision.reason == "no-eligible-agent"

    def test_routing_admits_when_guild_and_roles_match(self) -> None:
        """Sanity pin — account-scope guilds + roles both restrict but
        envelope matches both → admit (first-eligible-alphabetical).

        M11 F12 L5 — pass the structured-tuple role entry directly so
        the entry's guild_id matches the envelope's "G1"."""
        alpha = _agent("alpha")
        account = _account(
            allowlist={
                "peers": [],
                "channels": [],
                "guilds": ["G1"],
                "roles": [{"guild_id": "G1", "role_id": "R1"}],
            }
        )
        envelope = _envelope_with_guild(
            guild_id="G1",
            member_roles=["R1"],
        )
        decision = resolve_routing(account, envelope, [alpha], None)
        assert decision.agent == "alpha"
        assert decision.reason == "first-eligible"

    def test_routing_envelope_without_guild_keys_defaults_safely(self) -> None:
        """Pre-L8 envelopes (or test envelopes that don't populate
        ``guild_id`` / ``member_roles``) → ``raw.get`` returns None /
        empty list → ACL evaluates as "unrestricted on these axes" when
        the account does not restrict either axis. Pins the back-compat
        wiring: the threading does NOT introduce a regression for
        pre-L8 inbound payloads."""
        alpha = _agent("alpha")
        # Empty raw — no guild_id, no member_roles populated.
        envelope = InboundEnvelope(
            platform="stub",
            account_id="acct-test",
            channel_id="ch-1",
            thread_id=None,
            peer_id="peer-1",
            peer_name="Alice",
            text="hello",
            raw={},
        )
        decision = resolve_routing(_account(), envelope, [alpha], None)
        assert decision.agent == "alpha"
        assert decision.reason == "first-eligible"
