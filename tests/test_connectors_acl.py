"""ACL pure-function tests for F7 L2's ``connectors/_acl.py`` —
``admits_outbound`` and ``admits_inbound``.

Pins the per-axis tri-state matrix at both scopes (account-scope +
per-agent), plus the DMs-only-channels sentinel and the
explicit-empty-peers-axis deny. Outbound reasons are byte-identical
to what ``tools/connector_send.py`` formerly produced — the F6
``test_connector_send_tool.py`` integration tests continue
to assert on these strings, so any drift here breaks F6 regression.

The asymmetry test
(``test_account_scope_peers_empty_is_unrestricted_but_per_agent_peers_empty_is_deny``)
pins the per-axis-semantic-framing decision against silent
unification. The ``agent_acl = {}`` equivalence test pins the
empty-dict-equals-None invariant against silent drift.
"""

from __future__ import annotations

import pytest

from the_one.connectors._acl import (
    AdmissionContext,
    _default_no_mention,
    _default_not_dm,
)
from the_one.connectors._acl import admits_inbound as _admits_inbound_real
from the_one.connectors._acl import admits_outbound as _admits_outbound_real
from the_one.connectors.base import InboundEnvelope
from the_one.db.models import Connector
from tests._acl_shape_helpers import (
    DEFAULT_TEST_GUILD_ID,
    _to_v24_agent_acl,
    _to_v24_shape,
)


def admits_inbound(account, agent_acl, peer_id, channel_id, **kwargs):
    """Test wrapper — translates flat-shape ``agent_acl`` to the v24
    structured-tuple shape before invoking the real helper.

    Lets the existing test fixtures keep using the readable flat shape
    (``peers: list[str]``) post-F12; the production helper consumes
    structured dicts post-v24. The translator is a no-op when the input
    is already structured.

    M11 F12 L5 — when ``guild_id`` is not explicitly passed AND the
    test isn't a DM-context test (``is_dm`` either absent or False),
    default to ``DEFAULT_TEST_GUILD_ID`` to match the fixture-default
    guild_id assigned by ``_to_v24_shape`` for bare-string channel/role
    entries. This keeps existing inbound fixtures readable without
    sweeping every test body to add a ``guild_id=`` kwarg.

    M11 F14 L8 — the real ``admits_inbound`` now takes a frozen
    ``AdmissionContext`` instead of loose positional/kwarg facts
    (option-b: this flat-shape wrapper stays as the flat→context
    adapter so the ~30+ existing flat call sites need no change). The
    wrapper CONSUMES ``is_dm`` / ``guild_id`` / ``member_roles`` from
    ``kwargs`` into the context and forwards ONLY ``(account, v24_acl,
    ctx)`` — it must NOT pass the now-consumed kwargs onward (the new
    signature has no such parameters and would ``TypeError``). The
    ``DEFAULT_TEST_GUILD_ID`` default still applies here at the wrapper
    layer (NOT in ``from_envelope``); under ``is_dm=True`` it is
    suppressed so ``guild_id`` stays ``None`` for the DM-context
    fixtures."""
    is_dm = kwargs.get("is_dm", False)
    guild_id = kwargs.get("guild_id")
    if not is_dm and "guild_id" not in kwargs:
        guild_id = DEFAULT_TEST_GUILD_ID
    ctx = AdmissionContext(
        peer_id=peer_id,
        channel_id=channel_id,
        is_dm=is_dm,
        guild_id=guild_id,
        member_roles=kwargs.get("member_roles", []),
    )
    return _admits_inbound_real(
        account, _to_v24_agent_acl(agent_acl), ctx
    )


def admits_outbound(account, agent_acl, channel_id, **kwargs):
    """Test wrapper — same flat-shape translation as
    :func:`admits_inbound` (see its docstring)."""
    return _admits_outbound_real(
        account, _to_v24_agent_acl(agent_acl), channel_id, **kwargs
    )


def _account(allowlist: dict | None = None) -> Connector:
    """Minimal ``Connector`` fixture builder.

    Builds a stub-shaped account with an optional ``allowlist`` under
    ``config``. ``allowlist=None`` produces ``config = {}`` (the
    operator-cleared / never-set case).

    M11 F12 L3 — fixtures continue using the flat shape (``peers``,
    ``channels``, ``roles`` as ``list[str]``) for readability; the
    helper translates to the structured-tuple shape at build time so
    the Pydantic validator accepts the result.
    """
    config: dict = {}
    if allowlist is not None:
        config["allowlist"] = _to_v24_shape(allowlist)
    return Connector(
        id="acc-1",
        name="test",
        type="stub",
        config=config,
        secrets={},
    )


# ─────────────────────────────────────────────────────────────────
# admits_outbound
# ─────────────────────────────────────────────────────────────────


class TestAdmitsOutbound:
    """Per-axis tri-state matrix for outbound admission."""

    # ── Account-scope channels axis ───────────────────────────────

    def test_account_allowlist_absent_admits(self) -> None:
        admits, reason = admits_outbound(_account(), None, "C1")
        assert admits is True
        assert reason == ""

    def test_account_channels_empty_admits_any_channel(self) -> None:
        """HAT-redesigned: `[]` at account-scope = unrestricted."""
        acc = _account(allowlist={"peers": [], "channels": []})
        admits, reason = admits_outbound(acc, None, "C-anything")
        assert admits is True
        assert reason == ""

    def test_account_channels_subset_admits_member(self) -> None:
        acc = _account(allowlist={"peers": [], "channels": ["C1"]})
        admits, reason = admits_outbound(acc, None, "C1")
        assert admits is True
        assert reason == ""

    def test_account_channels_subset_denies_non_member(self) -> None:
        acc = _account(allowlist={"peers": [], "channels": ["C1"]})
        admits, reason = admits_outbound(acc, None, "C2")
        assert admits is False
        assert reason == "channel_id 'C2' is not reachable on account 'acc-1'"

    # ── Per-agent channels axis (with permissive account-scope) ──

    def test_per_agent_acl_none_inherits_account_scope(self) -> None:
        admits, reason = admits_outbound(_account(), None, "C1")
        assert admits is True
        assert reason == ""

    def test_per_agent_channels_none_inherits(self) -> None:
        admits, reason = admits_outbound(
            _account(), {"peers": None, "channels": None}, "C1"
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_channels_empty_is_dms_only_sentinel(self) -> None:
        """`[]` at per-agent = DMs-only sentinel. Without ``is_dm=True``
        the default-fail-closed semantic holds (preserves pre-F8
        behavior for callers that don't resolve DM-truth)."""
        admits, reason = admits_outbound(
            _account(), {"peers": None, "channels": []}, "C1"
        )
        assert admits is False
        assert reason == (
            "channel_id 'C1' is not reachable for this agent on account "
            "'acc-1' (per-agent channels axis is explicitly empty)"
        )

    def test_per_agent_channels_empty_with_is_dm_true_permits(self) -> None:
        """F8 L6 — DMs-only sentinel + ``is_dm=True`` flips the branch
        from deny to permit. The reason string is empty on admit
        (per :func:`admits_outbound`'s admit contract)."""
        admits, reason = admits_outbound(
            _account(),
            {"peers": None, "channels": []},
            "C1",
            is_dm=True,
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_channels_empty_with_is_dm_false_denies(self) -> None:
        """F8 L6 — DMs-only sentinel + ``is_dm=False`` (explicit) is
        byte-identical to the default-no-kwarg deny path. Pins the
        explicit-False behavior so a future "default to True" refactor
        doesn't silently flip the back-compat semantic."""
        admits, reason = admits_outbound(
            _account(),
            {"peers": None, "channels": []},
            "C1",
            is_dm=False,
        )
        assert admits is False
        assert reason == (
            "channel_id 'C1' is not reachable for this agent on account "
            "'acc-1' (per-agent channels axis is explicitly empty)"
        )

    def test_per_agent_channels_subset_admits_member(self) -> None:
        admits, reason = admits_outbound(
            _account(), {"peers": None, "channels": ["C1"]}, "C1"
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_channels_subset_denies_non_member(self) -> None:
        admits, reason = admits_outbound(
            _account(), {"peers": None, "channels": ["C1"]}, "C2"
        )
        assert admits is False
        assert reason == (
            "channel_id 'C2' is not reachable for this agent on account 'acc-1'"
        )

    # ── Intersection (account-scope + per-agent both apply) ───────

    def test_intersection_admits_when_in_both(self) -> None:
        acc = _account(allowlist={"peers": [], "channels": ["C1", "C2"]})
        admits, reason = admits_outbound(
            acc, {"peers": None, "channels": ["C2"]}, "C2"
        )
        assert admits is True
        assert reason == ""

    def test_intersection_denies_when_in_account_but_not_per_agent(self) -> None:
        acc = _account(allowlist={"peers": [], "channels": ["C1", "C2"]})
        admits, reason = admits_outbound(
            acc, {"peers": None, "channels": ["C2"]}, "C1"
        )
        assert admits is False
        # Per-agent denies (account-scope would admit) — reason reflects
        # the per-agent axis.
        assert reason == (
            "channel_id 'C1' is not reachable for this agent on account 'acc-1'"
        )

    def test_intersection_denies_when_in_per_agent_but_not_account(self) -> None:
        """Account-scope is the gate; per-agent narrows further. Account
        deny pre-empts the per-agent permit."""
        acc = _account(allowlist={"peers": [], "channels": ["C1"]})
        admits, reason = admits_outbound(
            acc, {"peers": None, "channels": ["C2"]}, "C2"
        )
        assert admits is False
        assert reason == "channel_id 'C2' is not reachable on account 'acc-1'"

    # ── Equivalence pins ──────────────────────────────────────────

    def test_agent_acl_empty_dict_equivalent_to_none(self) -> None:
        """``agent_acl = {}`` produces the same ``(bool, reason)`` as
        ``agent_acl = None`` — the empty-dict case must NOT silently
        narrow."""
        acc = _account(allowlist={"peers": [], "channels": ["C1"]})
        assert admits_outbound(acc, {}, "C1") == admits_outbound(acc, None, "C1")
        assert admits_outbound(acc, {}, "C2") == admits_outbound(acc, None, "C2")

    def test_no_config_and_no_acl_admits_anything(self) -> None:
        """Default-permit: empty config + no per-agent ACL admits."""
        admits, reason = admits_outbound(_account(), None, "C-anything")
        assert admits is True
        assert reason == ""


# ─────────────────────────────────────────────────────────────────
# admits_inbound
# ─────────────────────────────────────────────────────────────────


class TestAdmitsInbound:
    """Per-axis tri-state matrix for inbound admission, BOTH axes
    (peers + channels) at BOTH scopes (account + per-agent)."""

    # ── Account-scope peers axis ──────────────────────────────────

    def test_account_allowlist_absent_admits(self) -> None:
        admits, reason = admits_inbound(_account(), None, "P1", "C1")
        assert admits is True
        assert reason == ""

    def test_account_peers_empty_admits_any_peer(self) -> None:
        """HAT-redesigned: `[]` at account-scope peers = unrestricted."""
        acc = _account(allowlist={"peers": [], "channels": []})
        admits, reason = admits_inbound(acc, None, "P-anything", "C-anything")
        assert admits is True
        assert reason == ""

    def test_account_peers_subset_admits_member(self) -> None:
        """M11 F16 L1 — admission in the guild path no longer depends on
        the account-scope peers axis (it is DM-only now). P1 admits
        because the channels axis is unrestricted (``[]``), not because
        P1 is in the peers list."""
        acc = _account(allowlist={"peers": ["P1"], "channels": []})
        admits, reason = admits_inbound(acc, None, "P1", "C1")
        assert admits is True
        assert reason == ""

    def test_account_peers_subset_denies_non_member(self) -> None:
        """M11 F16 L1 — INVERTED. The account-scope peers axis is now
        DM-only; in the guild path a non-listed peer (P2) is ADMITTED
        when the channels axis permits (here ``[]`` = unrestricted).
        This is the primary RED-before / GREEN-after pin for the
        peers-DM-only fix."""
        acc = _account(allowlist={"peers": ["P1"], "channels": []})
        admits, reason = admits_inbound(acc, None, "P2", "C1")
        assert admits is True
        assert reason == ""

    def test_account_peers_dm_only_guild_admits_but_channels_still_gate(
        self,
    ) -> None:
        """M11 F16 L1 — trade-off boundary. With a populated account
        peers axis AND a populated channels axis, a non-listed peer is
        ADMITTED in the guild path on a listed channel (peers no longer
        gates guild) — but a non-listed channel for that same peer is
        still DENIED (the channels axis still gates). Guards that
        removing the peers gate did not weaken the channels gate."""
        acc = _account(allowlist={"peers": ["P1"], "channels": ["C1"]})
        # Non-listed peer P2 on listed channel C1 → admitted.
        admits, reason = admits_inbound(acc, None, "P2", "C1")
        assert admits is True
        assert reason == ""
        # Same non-listed peer P2 on non-listed channel C2 → still denied
        # by the channels axis.
        admits, reason = admits_inbound(acc, None, "P2", "C2")
        assert admits is False
        assert reason == "channel_id 'C2' is not admitted on account 'acc-1'"

    def test_account_peers_dm_context_still_denies_non_member(self) -> None:
        """M11 F16 L1 / M11 F17 L8 (Leg D) — DM admission is the
        account-scope peers axis's sole remaining job. A DM from a
        non-listed peer under a populated peers list is still DENIED
        under the default ``admin-approved`` policy. Reason string
        updated post-v28: dm_admission gate fires first (not peers
        membership guard)."""
        acc = _account(allowlist={"peers": ["P1"], "channels": []})
        admits, reason = admits_inbound(
            acc, None, "P2", "C1", is_dm=True
        )
        assert admits is False
        assert reason == (
            "DM denied: account 'acc-1' dm_admission is "
            "'admin-approved' and peer not in allowlist"
        )

    # ── Account-scope channels axis ───────────────────────────────

    def test_account_channels_empty_admits_any_channel(self) -> None:
        acc = _account(allowlist={"peers": [], "channels": []})
        admits, reason = admits_inbound(acc, None, "P1", "C-anything")
        assert admits is True
        assert reason == ""

    def test_account_channels_subset_admits_member(self) -> None:
        acc = _account(allowlist={"peers": [], "channels": ["C1"]})
        admits, reason = admits_inbound(acc, None, "P1", "C1")
        assert admits is True
        assert reason == ""

    def test_account_channels_subset_denies_non_member(self) -> None:
        acc = _account(allowlist={"peers": [], "channels": ["C1"]})
        admits, reason = admits_inbound(acc, None, "P1", "C2")
        assert admits is False
        assert reason == "channel_id 'C2' is not admitted on account 'acc-1'"

    # ── Per-agent peers axis ──────────────────────────────────────

    def test_per_agent_acl_none_inherits(self) -> None:
        admits, reason = admits_inbound(_account(), None, "P1", "C1")
        assert admits is True
        assert reason == ""

    def test_per_agent_peers_none_inherits(self) -> None:
        admits, reason = admits_inbound(
            _account(), {"peers": None, "channels": None}, "P1", "C1"
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_peers_empty_denies_any_peer(self) -> None:
        """`[]` at per-agent peers = explicit-empty deny (peers-axis
        analog of channels' DMs-only sentinel)."""
        admits, reason = admits_inbound(
            _account(), {"peers": [], "channels": None}, "P1", "C1"
        )
        assert admits is False
        assert reason == (
            "peer_id 'P1' is not admitted for this agent on account 'acc-1' "
            "(per-agent peers axis is explicitly empty)"
        )

    def test_per_agent_peers_subset_admits_member(self) -> None:
        admits, reason = admits_inbound(
            _account(), {"peers": ["P1"], "channels": None}, "P1", "C1"
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_peers_subset_denies_non_member(self) -> None:
        admits, reason = admits_inbound(
            _account(), {"peers": ["P1"], "channels": None}, "P2", "C1"
        )
        assert admits is False
        assert reason == (
            "peer_id 'P2' is not admitted for this agent on account 'acc-1'"
        )

    # ── Per-agent channels axis (with permissive peers) ──────────

    def test_per_agent_channels_none_inherits(self) -> None:
        admits, reason = admits_inbound(
            _account(), {"peers": None, "channels": None}, "P1", "C1"
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_channels_empty_is_dms_only_sentinel(self) -> None:
        """Inbound uses the same DMs-only wording as outbound but with
        the inbound verb ("admitted"). Without ``is_dm=True`` the
        default-fail-closed semantic holds (preserves pre-F8
        behavior for callers that don't resolve DM-truth)."""
        admits, reason = admits_inbound(
            _account(), {"peers": None, "channels": []}, "P1", "C1"
        )
        assert admits is False
        assert reason == (
            "channel_id 'C1' is not admitted for this agent on account "
            "'acc-1' (per-agent channels axis is explicitly empty)"
        )

    def test_per_agent_channels_empty_with_is_dm_true_permits(self) -> None:
        """F8 L6 — DMs-only sentinel + ``is_dm=True`` flips the
        inbound branch from deny to permit. The reason string is
        empty on admit."""
        admits, reason = admits_inbound(
            _account(),
            {"peers": None, "channels": []},
            "P1",
            "C1",
            is_dm=True,
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_channels_empty_with_is_dm_false_denies(self) -> None:
        """F8 L6 — DMs-only sentinel + ``is_dm=False`` (explicit) is
        byte-identical to the default-no-kwarg deny path. Pins
        explicit-False behavior so a future "default to True" refactor
        doesn't silently flip the back-compat semantic."""
        admits, reason = admits_inbound(
            _account(),
            {"peers": None, "channels": []},
            "P1",
            "C1",
            is_dm=False,
        )
        assert admits is False
        assert reason == (
            "channel_id 'C1' is not admitted for this agent on account "
            "'acc-1' (per-agent channels axis is explicitly empty)"
        )

    def test_per_agent_channels_subset_admits_member(self) -> None:
        admits, reason = admits_inbound(
            _account(), {"peers": None, "channels": ["C1"]}, "P1", "C1"
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_channels_subset_denies_non_member(self) -> None:
        admits, reason = admits_inbound(
            _account(), {"peers": None, "channels": ["C1"]}, "P1", "C2"
        )
        assert admits is False
        assert reason == (
            "channel_id 'C2' is not admitted for this agent on account 'acc-1'"
        )

    # ── Asymmetry pin ─────────────────────────────────────────────

    def test_account_scope_peers_empty_is_unrestricted_but_per_agent_peers_empty_is_deny(
        self,
    ) -> None:
        """Pin the per-axis semantic framing: account-scope `[]` =
        unrestricted (HAT-redesigned defaulting anchor); per-agent `[]`
        = deny (narrowing modifier's "no items" signal). This test
        prevents a future "let's unify the semantics" refactor from
        silently flipping behavior."""
        # Account-scope: peers = [] → unrestricted on peers axis.
        acc = _account(allowlist={"peers": [], "channels": []})
        admits, reason = admits_inbound(acc, None, "P-anything", "C1")
        assert admits is True
        assert reason == ""

        # Per-agent: peers = [] → DENY (axis explicitly empty).
        admits, reason = admits_inbound(
            acc, {"peers": [], "channels": None}, "P-anything", "C1"
        )
        assert admits is False
        assert reason == (
            "peer_id 'P-anything' is not admitted for this agent on account "
            "'acc-1' (per-agent peers axis is explicitly empty)"
        )

    def test_account_peers_inert_in_guild_but_per_agent_peers_narrows(
        self,
    ) -> None:
        """M11 F16 L1 — the account-vs-per-agent peers asymmetry. The
        account allowlist carries a populated ``peers`` key (and an empty
        ``channels`` axis → vacuously admits; guilds/roles absent →
        likewise unrestricted) and the per-agent overlay narrows peers to
        P2. A guild message from P3 is DENIED by the PER-AGENT axis, NOT
        by the account axis: the account peers axis is inert in the guild
        path even when populated, while the per-agent overlay still
        narrows guild routing. The reason-substring assertions pin that
        the deny comes from the per-agent axis (and explicitly NOT the
        bare account axis), so the test cannot pass on the wrong reason.

        (The Connector validator requires both ``peers`` and ``channels``
        keys on any present allowlist, so ``channels: []`` expresses the
        "channels axis vacuously admits" intent — empty list at account
        scope = unrestricted per the HAT-redesign.)"""
        acc = _account(allowlist={"peers": ["P1"], "channels": []})
        admits, reason = admits_inbound(
            acc, {"peers": ["P2"], "channels": None}, "P3", "C1"
        )
        assert admits is False
        # Deny attributed to the per-agent axis…
        assert "is not admitted for this agent" in reason
        # …and NOT to the bare account axis (self-documenting negative —
        # guards against the account-axis or channels-axis reason).
        assert "is not admitted on account" not in reason

    # ── agent_acl = {} equivalence pin ────────────────────────────

    def test_agent_acl_empty_dict_equivalent_to_none(self) -> None:
        """``agent_acl = {}`` produces the same ``(bool, reason)`` as
        ``agent_acl = None`` — the empty-dict case must NOT silently
        narrow on either axis."""
        acc = _account(allowlist={"peers": ["P1"], "channels": ["C1"]})
        # Member of both account-scope subsets → admit on both paths.
        assert admits_inbound(acc, {}, "P1", "C1") == admits_inbound(
            acc, None, "P1", "C1"
        )
        # M11 F16 L1 — guild path no longer consults account-scope peers,
        # so a non-member of peers now ADMITS in the guild path (channels
        # axis permits C1). Equivalence still holds (both admit).
        assert admits_inbound(acc, {}, "P2", "C1") == admits_inbound(
            acc, None, "P2", "C1"
        )
        # M11 F16 L1 — the genuine peers-deny equivalence case moves to
        # DM context, where the account-scope peers axis still gates: a
        # non-member of peers denies on both paths with the same reason.
        assert admits_inbound(
            acc, {}, "P2", "C1", is_dm=True
        ) == admits_inbound(acc, None, "P2", "C1", is_dm=True)
        # Non-member of channels → deny on both paths with same reason.
        assert admits_inbound(acc, {}, "P1", "C2") == admits_inbound(
            acc, None, "P1", "C2"
        )

    # ── Both axes denied: peers-first short-circuit ────────────────

    def test_both_axes_denied_short_circuits_on_peers(self) -> None:
        """When BOTH peers and channels would deny, the function
        returns the peers-axis reason (first check)."""
        admits, reason = admits_inbound(
            _account(),
            {"peers": ["P1"], "channels": ["C1"]},
            "P-bad",
            "C-bad",
        )
        assert admits is False
        # Peers axis reported (not channels).
        assert "peer_id 'P-bad'" in reason
        assert "channel_id" not in reason


# ─────────────────────────────────────────────────────────────────
# M10 F8 L8 — guilds + roles axes
# ─────────────────────────────────────────────────────────────────


class TestAdmitsInboundGuildsAxis:
    """Per-axis tri-state for the ``guilds`` axis (L8 extension)."""

    # ── Account-scope guilds axis ────────────────────────────────

    def test_account_guilds_absent_admits_any_guild(self) -> None:
        """Axis absent (``allowlist`` 2-key shape, no guilds key) →
        unrestricted on guilds. Back-compat with pre-L8 rows."""
        acc = _account(allowlist={"peers": [], "channels": []})
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", guild_id="G-anything",
        )
        assert admits is True
        assert reason == ""

    def test_account_guilds_empty_admits_any_guild(self) -> None:
        """Axis ``[]`` = unrestricted on this axis at account-scope
        (HAT-redesigned defaulting anchor — same shape as peers)."""
        acc = _account(allowlist={"peers": [], "channels": [], "guilds": []})
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", guild_id="G-anything",
        )
        assert admits is True
        assert reason == ""

    def test_account_guilds_subset_admits_member(self) -> None:
        acc = _account(allowlist={
            "peers": [], "channels": [], "guilds": ["G1", "G2"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", guild_id="G1",
        )
        assert admits is True
        assert reason == ""

    def test_account_guilds_subset_denies_non_member(self) -> None:
        acc = _account(allowlist={
            "peers": [], "channels": [], "guilds": ["G1"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", guild_id="G2",
        )
        assert admits is False
        assert "guild_id 'G2' is not admitted on account 'acc-1'" == reason

    def test_account_guilds_restrictive_denies_dm_envelope(self) -> None:
        """**F8 L8 DM-with-guild-restriction posture (is_dm=False path)** —
        when the guilds axis is non-empty and the envelope is a DM
        (``guild_id=None``) AND the caller has not resolved DM-truth
        (``is_dm=False`` default), the guild check denies. Pre-F10 the
        only reachable DM-envelope path; post-F10 it persists for
        callers that haven't threaded ``is_dm=True``.
        """
        acc = _account(allowlist={
            "peers": [], "channels": [], "guilds": ["G1"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", guild_id=None,
        )
        assert admits is False
        assert "guild_id None is not admitted on account 'acc-1'" == reason

    def test_account_guilds_restrictive_admits_dm_when_dm_admission_permits(
        self,
    ) -> None:
        """**M11 F10 L1 orthogonal-DM-admission posture** — same setup
        as the prior test but with ``is_dm=True`` and account-scope
        ``dm_admission="all"`` + ``peers=["P1"]``. Under L1, DMs SKIP
        the guilds axis and consult ``dm_admission`` instead → admit.
        Pins that guild-axis restriction is orthogonal to DM admission
        under the new posture.
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "guilds": ["G1"],
            "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", is_dm=True, guild_id=None,
        )
        assert admits is True
        assert reason == ""

    # ── Per-agent guilds axis ────────────────────────────────────

    def test_per_agent_guilds_none_inherits_account_scope(self) -> None:
        """``None`` on per-agent guilds → inherit account-scope (no
        narrowing). Mirrors the peers-axis precedent."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "guilds": ["G1"],
        })
        admits, reason = admits_inbound(
            acc,
            {"peers": None, "channels": None, "guilds": None},
            "P1", "C1", guild_id="G1",
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_guilds_empty_is_deny(self) -> None:
        """Per-agent ``[]`` = explicit-empty narrowing (deny) —
        consistent with the peers-axis asymmetry pin."""
        admits, reason = admits_inbound(
            _account(),
            {"peers": None, "channels": None, "guilds": []},
            "P1", "C1", guild_id="G1",
        )
        assert admits is False
        assert "per-agent guilds axis is explicitly empty" in reason

    def test_per_agent_guilds_subset_narrows_further(self) -> None:
        """Account-scope admits G1/G2; per-agent narrows to G1 only.
        G2 inbound → deny."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "guilds": ["G1", "G2"],
        })
        admits, reason = admits_inbound(
            acc,
            {"peers": None, "channels": None, "guilds": ["G1"]},
            "P1", "C1", guild_id="G2",
        )
        assert admits is False
        assert "guild_id 'G2' is not admitted for this agent" in reason


class TestAdmitsInboundRolesAxis:
    """Per-axis tri-state for the ``roles`` axis (L8 extension)."""

    # ── Account-scope roles axis ─────────────────────────────────

    def test_account_roles_absent_admits_any_member_roles(self) -> None:
        """Axis absent → unrestricted; even empty ``member_roles``
        admits. Back-compat with pre-L8 rows."""
        acc = _account(allowlist={"peers": [], "channels": []})
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", member_roles=[],
        )
        assert admits is True
        assert reason == ""

    def test_account_roles_empty_admits_any_member_roles(self) -> None:
        """Axis ``[]`` = unrestricted on this axis at account-scope."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": [],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", member_roles=["R-anything"],
        )
        assert admits is True
        assert reason == ""

    def test_account_roles_overlap_admits(self) -> None:
        """Any-of overlap — peer holds R1, allowlist requires R1|R2 →
        admit."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1", "R2"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", member_roles=["R1", "R3"],
        )
        assert admits is True
        assert reason == ""

    def test_account_roles_no_overlap_denies(self) -> None:
        """Peer holds R3; allowlist requires R1|R2 → deny (no overlap)."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1", "R2"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", member_roles=["R3"],
        )
        assert admits is False
        assert "peer roles do not overlap" in reason
        assert "on account 'acc-1'" in reason

    def test_account_roles_empty_member_roles_denies_when_restricted(self) -> None:
        """Peer has no roles (caller did not pass ``is_dm=True``) and
        the allowlist is non-empty → deny. Documented consistency with
        the per-axis subset semantic. Pre-F10 the only reachable DM
        path on the roles axis; post-F10 it persists for ``is_dm=False``
        callers.
        """
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", member_roles=[],
        )
        assert admits is False
        assert "peer roles do not overlap" in reason

    def test_account_roles_empty_member_roles_admits_dm_when_dm_admission_permits(
        self,
    ) -> None:
        """**M11 F10 L1 orthogonal-DM-admission posture** — same setup
        as the prior test but with ``is_dm=True`` + ``dm_admission="all"``
        + peer allowlisted. DMs SKIP the roles axis under L1; admit.
        Pins that the roles-axis restriction is irrelevant for DMs.
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "roles": ["R1"],
            "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", is_dm=True, member_roles=[],
        )
        assert admits is True
        assert reason == ""

    def test_account_roles_member_roles_none_denies_when_restricted(self) -> None:
        """``member_roles=None`` (default kwarg / caller did not
        populate) is equivalent to ``[]`` for the overlap check.
        Pin to prevent silent ``None``→``set()`` drift.
        """
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1"],
        })
        admits, reason = admits_inbound(acc, None, "P1", "C1")
        assert admits is False

    def test_account_roles_member_roles_none_admits_dm_when_dm_admission_permits(
        self,
    ) -> None:
        """**M11 F10 L1 orthogonal-DM-admission posture** — same setup
        as the prior test but with ``is_dm=True`` + ``dm_admission="all"``
        + peer allowlisted. DMs SKIP the roles axis under L1; the
        missing ``member_roles`` is irrelevant. Admit.
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "roles": ["R1"],
            "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", is_dm=True,
        )
        assert admits is True
        assert reason == ""

    # ── Per-agent roles axis ─────────────────────────────────────

    def test_per_agent_roles_none_inherits_account_scope(self) -> None:
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1"],
        })
        admits, reason = admits_inbound(
            acc,
            {"peers": None, "channels": None, "roles": None},
            "P1", "C1", member_roles=["R1"],
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_roles_empty_is_deny(self) -> None:
        """Per-agent ``[]`` = explicit-empty narrowing (deny)."""
        admits, reason = admits_inbound(
            _account(),
            {"peers": None, "channels": None, "roles": []},
            "P1", "C1", member_roles=["R1"],
        )
        assert admits is False
        assert "per-agent roles axis is explicitly empty" in reason

    def test_per_agent_roles_subset_narrows_further(self) -> None:
        """Account-scope admits R1/R2; per-agent narrows to R1 only.
        Peer with only R2 → deny."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1", "R2"],
        })
        admits, reason = admits_inbound(
            acc,
            {"peers": None, "channels": None, "roles": ["R1"]},
            "P1", "C1", member_roles=["R2"],
        )
        assert admits is False
        assert "peer roles do not overlap" in reason
        assert "for this agent" in reason


class TestAdmitsInboundDmAdmissionAxis:
    """M11 F10 L1 / M11 F17 L8 (Leg D) — DM-admission axis tests.

    Post-v28 simplified model: gate on ``dm_admission`` FIRST (no
    per-peer ``dm_allowed`` flag; no pre-admission peers membership
    check under ``"all"``).

      - ``dm_admission="none"`` → deny all DMs regardless of list
      - ``dm_admission="all"`` → admit any DM (list irrelevant)
      - ``dm_admission="admin-approved"`` → admit iff peer in list

    The 9-cell matrix covers:
      - ``dm_admission`` ∈ {``"none"``, ``"admin-approved"``, ``"all"``}
      - ``allowed_peers`` state ∈ {peer-on-list, peer-not-on-list, empty}
    """

    # ── dm_admission = "none" ────────────────────────────────────

    def test_dm_admission_none_peer_on_allowlist_denies(self) -> None:
        """``dm_admission="none"`` + peer on list → deny via the
        dm_admission gate (checked before peers membership).
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "dm_admission": "none",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == (
            "DM denied: account 'acc-1' dm_admission is 'none'"
        )

    def test_dm_admission_none_peer_not_on_allowlist_denies(self) -> None:
        """``dm_admission="none"`` + peer not on list → deny via the
        dm_admission gate (dm_admission checked before list membership
        post-v28; reason is now the dm_admission deny, not a peers-axis deny).
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "dm_admission": "none",
        })
        admits, reason = admits_inbound(
            acc, None, "P2", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == (
            "DM denied: account 'acc-1' dm_admission is 'none'"
        )

    def test_dm_admission_none_peers_empty_denies(self) -> None:
        """``dm_admission="none"`` + empty peers list → deny via the
        dm_admission gate.
        """
        acc = _account(allowlist={
            "peers": [], "channels": [], "dm_admission": "none",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == (
            "DM denied: account 'acc-1' dm_admission is 'none'"
        )

    # ── dm_admission = "admin-approved" (post-v28: in-list == can-DM)

    def test_dm_admission_admin_approved_peer_on_allowlist_admits(
        self,
    ) -> None:
        """``dm_admission="admin-approved"`` + peer on list → admit
        (in-list == can-DM; no per-peer toggle needed post-v28).
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [],
            "dm_admission": "admin-approved",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is True
        assert reason == ""

    def test_dm_admission_admin_approved_peer_not_on_allowlist_denies(
        self,
    ) -> None:
        """``dm_admission="admin-approved"`` + peer not on list → deny."""
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [],
            "dm_admission": "admin-approved",
        })
        admits, reason = admits_inbound(
            acc, None, "P2", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == (
            "DM denied: account 'acc-1' dm_admission is "
            "'admin-approved' and peer not in allowlist"
        )

    def test_dm_admission_admin_approved_peers_empty_denies(
        self,
    ) -> None:
        """``dm_admission="admin-approved"`` + empty list → deny
        (no peer approved yet).
        """
        acc = _account(allowlist={
            "peers": [], "channels": [],
            "dm_admission": "admin-approved",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == (
            "DM denied: account 'acc-1' dm_admission is "
            "'admin-approved' and peer not in allowlist"
        )

    # ── dm_admission = "all" ─────────────────────────────────────

    def test_dm_admission_all_peer_on_allowlist_admits(self) -> None:
        """``dm_admission="all"`` + peer on list → admit."""
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is True
        assert reason == ""

    def test_dm_admission_all_peer_not_on_allowlist_admits(self) -> None:
        """``dm_admission="all"`` + peer NOT on list → admit.

        Post-v28: ``"all"`` skips the peers membership check entirely.
        A non-listed peer is still admitted under ``"all"``
        (changed from pre-v28 where the peers-axis-precedence denied
        non-listed peers even under ``"all"``).
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P2", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is True
        assert reason == ""

    def test_dm_admission_all_peers_empty_admits(self) -> None:
        """``dm_admission="all"`` + empty list → admit."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is True
        assert reason == ""


class TestAdmitsInboundPerAgentAdmitDms:
    """M11 F10 L1 — per-agent ``admit_dms`` axis tests.

    ``admit_dms`` is the per-agent opt-out sentinel for DMs:
      - ``False`` → deny DMs even when account-scope ``dm_admission``
        permits
      - ``True`` or ``None`` (default / absent) → inherit account-scope
    """

    def test_per_agent_admit_dms_false_overrides_account_admit(
        self,
    ) -> None:
        """Account ``dm_admission="all"`` + per-agent ``admit_dms=False``
        + ``is_dm=True`` → deny via the per-agent admit_dms gate.
        """
        acc = _account(allowlist={
            "peers": [], "channels": [], "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc,
            {"peers": None, "channels": None, "admit_dms": False},
            "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == (
            "DM denied: agent admit_dms is False on account 'acc-1'"
        )

    def test_per_agent_admit_dms_false_irrelevant_for_guild_messages(
        self,
    ) -> None:
        """Account ``dm_admission="none"`` + per-agent ``admit_dms=False``
        + ``is_dm=False`` → admit (admit_dms is DM-only — the dm-
        admission gate at account scope is also skipped when not a DM).
        Guild-context messages are unaffected by per-agent admit_dms.
        """
        acc = _account(allowlist={
            "peers": [], "channels": [], "dm_admission": "none",
        })
        admits, reason = admits_inbound(
            acc,
            {"peers": None, "channels": None, "admit_dms": False},
            "P1", "C1", is_dm=False,
            guild_id="G1", member_roles=["R1"],
        )
        assert admits is True
        assert reason == ""

    def test_per_agent_admit_dms_none_inherits_account(self) -> None:
        """Account ``dm_admission="all"`` + per-agent ``admit_dms=None``
        + ``is_dm=True`` → admit (None inherits; account-scope permits).
        """
        acc = _account(allowlist={
            "peers": [], "channels": [], "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc,
            {"peers": None, "channels": None, "admit_dms": None},
            "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is True
        assert reason == ""


class TestAdmitsOutboundAcceptsButIgnoresGuildsRoles:
    """L8 outbound posture — accepts the new kwargs for signature
    uniformity but does NOT consult them (no envelope context at the
    F4 platform-send tool's call site)."""

    def test_outbound_ignores_guild_id_even_when_account_restricts(self) -> None:
        """Account-scope ``guilds`` axis is irrelevant on outbound —
        even when the operator restricts to G1, an outbound call
        passing ``guild_id="G-other"`` still admits if the channels
        axis would permit. Pins the L8 "outbound has no envelope"
        rationale."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "guilds": ["G1"],
        })
        admits, reason = admits_outbound(
            acc, None, "C1", guild_id="G-other",
        )
        assert admits is True
        assert reason == ""

    def test_outbound_ignores_member_roles_even_when_account_restricts(self) -> None:
        """Symmetric to the guild check — roles axis is not consulted
        on outbound."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1"],
        })
        admits, reason = admits_outbound(
            acc, None, "C1", member_roles=[],
        )
        assert admits is True
        assert reason == ""


# ─────────────────────────────────────────────────────────────────
# Sentinel fallbacks (M11 F7 L1)
# ─────────────────────────────────────────────────────────────────


def _envelope_for_sentinel() -> InboundEnvelope:
    """Minimal envelope for sentinel-fallback unit tests.

    The sentinels ignore the envelope entirely (they are constant-
    returning fallbacks), so the field values are not load-bearing
    on their return value. The fixture exists to prove the call
    shape itself does not raise.
    """
    return InboundEnvelope(
        platform="stub",
        account_id="acct-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        peer_name="Alice",
        text="hi",
        raw={},
    )


def test_default_not_dm_returns_false() -> None:
    """``_default_not_dm`` returns ``False`` for any envelope —
    preserves the historical fail-closed behavior of the DMs-only ACL
    branch for plugins (e.g. the test-only stub) without a DM-
    classification hook.
    """
    assert _default_not_dm(_envelope_for_sentinel()) is False


def test_default_no_mention_returns_false() -> None:
    """``_default_no_mention`` returns ``False`` for any envelope —
    preserves the F7 policy gate's silent-by-default branch for
    plugins (e.g. the test-only stub) without a mention concept.

    Mirrors :func:`test_default_not_dm_returns_false` — see
    ``agents.md`` § ``optional-plugin-hook-via-getattr-sentinel``.
    """
    assert _default_no_mention(_envelope_for_sentinel()) is False


# ─────────────────────────────────────────────────────────────────
# M11 F12 L3 — DM Composition Cross-Product Matrix
# ─────────────────────────────────────────────────────────────────


class TestDmAdmissionCompositionMatrix:
    """6-cell cross-product matrix pinning the simplified DM Composition
    at ``_admits_inbound_dm`` per M11 F17 L8 (Leg D).

    Post-v28 model: ``dm_allowed`` per-peer flag retired. Axes:
      - ``admit_dms`` ∈ {None, False, True} — per-agent opt-out
      - ``dm_admission`` ∈ {"all", "none", "admin-approved"} —
        account-scope policy
      - ``in_allowlist`` ∈ {True, False} — whether the inbound peer is
        in the account-scope peers list

    Simplified composition:
      ``admit_dm = (admit_dms is not False)
                AND (dm_admission == "all"
                     OR (dm_admission == "admin-approved" AND peer in list))``

    Under ``"all"`` the peers membership check is SKIPPED — a non-listed
    peer is admitted. Under ``"admin-approved"`` in-list == can-DM.
    """

    # Cells: (admit_dms, dm_admission, in_allowlist, expected, test_id, rationale)
    _MATRIX_CELLS = [
        (None, "all", True, True,
         "cell_01_None_all_in", "all + in list → admit"),
        (None, "all", False, True,
         "cell_02_None_all_out",
         "all + NOT in list → admit (peers list irrelevant under all)"),
        (None, "none", True, False,
         "cell_03_None_none_in", "none always denies"),
        (None, "admin-approved", True, True,
         "cell_04_None_apv_in",
         "happy path: in list + admin-approved → admit"),
        (None, "admin-approved", False, False,
         "cell_05_None_apv_out",
         "not in list + admin-approved → deny"),
        (False, "all", True, False,
         "cell_06_False_all_in",
         "admit_dms=False short-circuits regardless of policy"),
    ]

    @pytest.mark.parametrize(
        ("admit_dms", "dm_admission", "in_allowlist", "expected"),
        [
            pytest.param(*cell[:4], id=cell[4])
            for cell in _MATRIX_CELLS
        ],
    )
    def test_dm_composition_matrix_cell(
        self,
        admit_dms: bool | None,
        dm_admission: str,
        in_allowlist: bool,
        expected: bool,
    ) -> None:
        """One cell of the simplified 6-cell cross-product matrix.

        Constructs an account with a single bare ``{"id": "P1"}`` peer.
        If ``in_allowlist=True`` the inbound peer is ``P1``; otherwise
        ``P-other`` (list non-empty but peer not in it).
        """
        allowlist = {
            "peers": ["P1"],
            "channels": [],
            "dm_admission": dm_admission,
        }
        account = _account(allowlist=allowlist)
        inbound_peer = "P1" if in_allowlist else "P-other"

        agent_acl: dict | None = None
        if admit_dms is not None:
            agent_acl = {
                "peers": None,
                "channels": None,
                "admit_dms": admit_dms,
            }

        admits, _ = admits_inbound(
            account, agent_acl, inbound_peer, "C-dm", is_dm=True
        )
        assert admits is expected, (
            f"cell admit_dms={admit_dms} dm_admission={dm_admission!r} "
            f"in_allowlist={in_allowlist}: "
            f"expected={expected} got={admits}"
        )


class TestHierarchicalAxisWildcardMatrix:
    """M11 F12 L5 — wildcard sentinel cells on the channels + roles
    axes. Extends the cross-product matrix with ``channel_id="*"`` and
    ``role_id="*"`` cases that the hierarchical Server-as-parent UI
    emits when a server row is added without explicit narrowing.

    Per the L5 wildcard semantic locked in the leg spec:

    - ``channel_id == "*"`` admits ANY ``envelope.channel_id`` whose
      envelope ``guild_id`` matches the entry's ``guild_id``. Outbound
      ignores ``guild_id`` (locked L3 semantic), so the wildcard
      admits unconditionally for channels.
    - ``role_id == "*"`` admits ANY peer with ANY ``member_roles``
      (including the empty list) whose envelope ``guild_id`` matches
      the entry's ``guild_id``. The wildcard short-circuits the
      overlap check at the per-guild scope.
    """

    # ── Channels-axis wildcard cells ───────────────────────────────

    def test_channel_wildcard_matching_guild_admits_any_channel(
        self,
    ) -> None:
        """channels=[{guild_id="A", channel_id="*"}],
        envelope.guild_id="A", envelope.channel_id="X" → admit."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [{"guild_id": "A", "channel_id": "*"}],
        })
        admits, _ = admits_inbound(
            acc, None, "P1", "X", guild_id="A",
        )
        assert admits is True

    def test_channel_wildcard_non_matching_guild_denies(self) -> None:
        """channels=[{guild_id="A", channel_id="*"}],
        envelope.guild_id="B", envelope.channel_id="X" → deny (still
        guild-scoped — the wildcard is per-guild, not global)."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [{"guild_id": "A", "channel_id": "*"}],
        })
        admits, _ = admits_inbound(
            acc, None, "P1", "X", guild_id="B",
        )
        assert admits is False

    def test_channel_wildcard_mixed_explicit_and_wildcard_other_guild(
        self,
    ) -> None:
        """channels=[{guild_id="A", channel_id="X"},
                   {guild_id="B", channel_id="*"}],
        envelope.guild_id="A", envelope.channel_id="Y" → deny (X is
        the only A-scoped explicit; wildcard only admits B-scoped)."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [
                {"guild_id": "A", "channel_id": "X"},
                {"guild_id": "B", "channel_id": "*"},
            ],
        })
        admits, _ = admits_inbound(
            acc, None, "P1", "Y", guild_id="A",
        )
        assert admits is False

    def test_channel_wildcard_outbound_admits_unconditionally(
        self,
    ) -> None:
        """Outbound matches by channel_id alone (locked L3 semantic);
        the ``"*"`` wildcard simply admits any channel_id when present
        in the list."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [{"guild_id": "A", "channel_id": "*"}],
        })
        admits, _ = admits_outbound(acc, None, "C-any-channel")
        assert admits is True

    # ── Roles-axis wildcard cells ──────────────────────────────────

    def test_role_wildcard_matching_guild_admits_empty_member_roles(
        self,
    ) -> None:
        """roles=[{guild_id="A", role_id="*"}],
        envelope.guild_id="A", member_roles=[] → admit (wildcard
        short-circuits overlap)."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [],
            "roles": [{"guild_id": "A", "role_id": "*"}],
        })
        admits, _ = admits_inbound(
            acc, None, "P1", "C1",
            guild_id="A", member_roles=[],
        )
        assert admits is True

    def test_role_wildcard_non_matching_guild_denies(self) -> None:
        """roles=[{guild_id="A", role_id="*"}],
        envelope.guild_id="B", member_roles=["R1"] → deny (the wildcard
        is per-guild scoped)."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [],
            "roles": [{"guild_id": "A", "role_id": "*"}],
        })
        admits, _ = admits_inbound(
            acc, None, "P1", "C1",
            guild_id="B", member_roles=["R1"],
        )
        assert admits is False

    def test_role_wildcard_admits_any_member_roles(self) -> None:
        """roles=[{guild_id="A", role_id="*"}],
        envelope.guild_id="A", member_roles=["R-arbitrary"] → admit."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [],
            "roles": [{"guild_id": "A", "role_id": "*"}],
        })
        admits, _ = admits_inbound(
            acc, None, "P1", "C1",
            guild_id="A", member_roles=["R-arbitrary"],
        )
        assert admits is True

    # ── Per-agent overlay wildcard ─────────────────────────────────

    def test_per_agent_channel_wildcard_admits_in_guild(self) -> None:
        """Per-agent overlay: channels=[{guild_id="A", channel_id="*"}]
        admits any envelope.channel_id when envelope.guild_id="A".
        Account-scope is left unrestricted on channels so the per-agent
        wildcard is the decisive gate."""
        acc = _account(allowlist={
            "peers": [],
            "channels": [],
        })
        admits, _ = admits_inbound(
            acc,
            {
                "peers": None,
                "channels": [{"guild_id": "A", "channel_id": "*"}],
            },
            "P1", "Z",
            guild_id="A",
        )
        assert admits is True


# ─────────────────────────────────────────────────────────────────
# M11 F17 L8 (Leg D) — F3a regression net
# ─────────────────────────────────────────────────────────────────


def test_f3a_approve_peer_then_dm_is_admitted() -> None:
    """Permanent regression net for the F16-parked Known Issue (F3a).

    The bug: ``dm_admission="admin-approved"`` + a peer approved via the
    UI (added as ``{id, dm_allowed:False}``) → DM gated at admission →
    ``no-eligible`` → "no agents available". The two-step (approve adds
    ``{id, dm_allowed:False}``, operator must flip a toggle) was confusing
    and blocked real-world use.

    Post-v28 fix: approve adds the peer as bare ``{id}`` (in-list ==
    can-DM). This test simulates the post-approve state: a connector with
    ``dm_admission="admin-approved"`` and ``peers=[{"id": "peer-1"}]``
    (bare, as the fixed approve handler now writes) → an inbound DM from
    ``"peer-1"`` is admitted.
    """
    # Post-fix allowlist: approved peer is bare {id} — this is what
    # ``approve_peer_approval`` in api.py now writes post-v28.
    account = _account(allowlist={
        "peers": ["peer-1"],     # _to_v24_shape translates to {"id": "peer-1"}
        "channels": [],
        "dm_admission": "admin-approved",
    })

    # Immediate DM from the approved peer — should be ADMITTED.
    admits, reason = admits_inbound(
        account, None, "peer-1", "dm-ch", is_dm=True
    )
    assert admits is True, (
        f"F3a regression: approved peer should be admitted immediately "
        f"under admin-approved; got denied with reason={reason!r}"
    )

    # A non-approved peer under admin-approved → still denied.
    admits2, reason2 = admits_inbound(
        account, None, "peer-other", "dm-ch", is_dm=True
    )
    assert admits2 is False
    assert "admin-approved" in reason2


# ─────────────────────────────────────────────────────────────────
# AdmissionContext.from_envelope construction (M11 F14 L8)
# ─────────────────────────────────────────────────────────────────


class _IsDmPlugin:
    """Test-only plugin stub exposing only the ``is_dm`` hook.

    Mirrors the F8 L6 ``DiscordPlugin.is_dm`` shape (sync callable on
    ``InboundEnvelope``); the ``getattr`` sentinel consult only reaches
    for ``is_dm``."""

    def __init__(self, result: bool) -> None:
        self._result = result

    def is_dm(self, envelope: InboundEnvelope) -> bool:
        return self._result


def _envelope(raw: dict) -> InboundEnvelope:
    """Minimal ``InboundEnvelope`` builder for construction tests.

    Populates only what the dataclass requires plus the ``raw`` payload
    under test (``guild_id`` / ``member_roles`` presence drives the
    assertions)."""
    return InboundEnvelope(
        platform="stub",
        account_id="acc-1",
        channel_id="C1",
        thread_id=None,
        peer_id="P1",
        peer_name="peer",
        text="hi",
        raw=raw,
    )


class TestAdmissionContextConstruction:
    """Pins ``AdmissionContext.from_envelope`` field derivation (L8)."""

    def test_is_dm_from_plugin_hook(self) -> None:
        """``is_dm`` is resolved via the plugin's ``is_dm`` hook, not a
        raw envelope read — a plugin reporting True yields is_dm=True
        even when ``raw`` carries no ``is_dm`` key."""
        env = _envelope({"guild_id": "G1", "member_roles": ["R1"]})
        ctx = AdmissionContext.from_envelope(env, _IsDmPlugin(True))
        assert ctx.is_dm is True
        # And the peer/channel identity flows straight through.
        assert ctx.peer_id == "P1"
        assert ctx.channel_id == "C1"

    def test_is_dm_plugin_none_falls_back_to_default_false(self) -> None:
        """``plugin=None`` falls back to ``_default_not_dm`` → False
        (pre-F8 fail-closed posture); a raw ``is_dm=True`` is ignored
        because derivation goes through the hook, not the raw dict."""
        env = _envelope({"is_dm": True})
        ctx = AdmissionContext.from_envelope(env, None)
        assert ctx.is_dm is False

    def test_guild_id_and_member_roles_from_raw(self) -> None:
        """``guild_id`` and ``member_roles`` are read from
        ``envelope.raw``; ``member_roles`` defaults to ``[]`` when the
        key is absent (pre-F8-L4 envelope), and ``guild_id`` to None."""
        env_full = _envelope({"guild_id": "G7", "member_roles": ["R1", "R2"]})
        ctx_full = AdmissionContext.from_envelope(env_full, None)
        assert ctx_full.guild_id == "G7"
        assert ctx_full.member_roles == ["R1", "R2"]

        env_bare = _envelope({})
        ctx_bare = AdmissionContext.from_envelope(env_bare, None)
        assert ctx_bare.guild_id is None
        assert ctx_bare.member_roles == []
