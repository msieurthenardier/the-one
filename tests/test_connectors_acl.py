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

from the_one.connectors._acl import admits_inbound, admits_outbound
from the_one.db.models import ConnectorAccount


def _account(allowlist: dict | None = None) -> ConnectorAccount:
    """Minimal ``ConnectorAccount`` fixture builder.

    Builds a stub-shaped account with an optional ``allowlist`` under
    ``config``. ``allowlist=None`` produces ``config = {}`` (the
    operator-cleared / never-set case).
    """
    config: dict = {}
    if allowlist is not None:
        config["allowlist"] = allowlist
    return ConnectorAccount(
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
            "'acc-1' (DMs-only override; target is not a DM)"
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
            "'acc-1' (DMs-only override; target is not a DM)"
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
        acc = _account(allowlist={"peers": ["P1"], "channels": []})
        admits, reason = admits_inbound(acc, None, "P1", "C1")
        assert admits is True
        assert reason == ""

    def test_account_peers_subset_denies_non_member(self) -> None:
        acc = _account(allowlist={"peers": ["P1"], "channels": []})
        admits, reason = admits_inbound(acc, None, "P2", "C1")
        assert admits is False
        assert reason == "peer_id 'P2' is not admitted on account 'acc-1'"

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
            "'acc-1' (DMs-only override; envelope is not a DM)"
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
            "'acc-1' (DMs-only override; envelope is not a DM)"
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
        # Non-member of peers → deny on both paths with same reason.
        assert admits_inbound(acc, {}, "P2", "C1") == admits_inbound(
            acc, None, "P2", "C1"
        )
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
        """**DM-with-guild-restriction posture** — when the guilds axis
        is non-empty and the envelope is a DM (``guild_id=None``), the
        check denies. The operator narrowed to specific guilds; DMs are
        out-of-scope. Documented edge case pinned per L8 spec."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "guilds": ["G1"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", guild_id=None,
        )
        assert admits is False
        assert "guild_id None is not admitted on account 'acc-1'" == reason

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
        """Peer has no roles (DM context or unrolled peer) and the
        allowlist is non-empty → deny. Documented consistency with
        the per-axis subset semantic."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1"],
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "C1", member_roles=[],
        )
        assert admits is False
        assert "peer roles do not overlap" in reason

    def test_account_roles_member_roles_none_denies_when_restricted(self) -> None:
        """``member_roles=None`` (default kwarg / caller did not
        populate) is equivalent to ``[]`` for the overlap check.
        Pin to prevent silent ``None``→``set()`` drift."""
        acc = _account(allowlist={
            "peers": [], "channels": [], "roles": ["R1"],
        })
        admits, reason = admits_inbound(acc, None, "P1", "C1")
        assert admits is False

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
