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

from the_one.connectors._acl import (
    _default_no_mention,
    _default_not_dm,
    admits_inbound,
    admits_outbound,
)
from the_one.connectors.base import InboundEnvelope
from the_one.db.models import Connector


def _account(allowlist: dict | None = None) -> Connector:
    """Minimal ``Connector`` fixture builder.

    Builds a stub-shaped account with an optional ``allowlist`` under
    ``config``. ``allowlist=None`` produces ``config = {}`` (the
    operator-cleared / never-set case).
    """
    config: dict = {}
    if allowlist is not None:
        config["allowlist"] = allowlist
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
    """M11 F10 L1 — DM-admission axis tests.

    The axis is orthogonal to the channels/guilds/roles axes: when
    ``is_dm=True``, ``admits_inbound`` consults only the peers axis +
    the new account-scope ``dm_admission`` axis + the new per-agent
    ``admit_dms`` axis. The 9-cell matrix below covers the cartesian
    product of:

      - ``dm_admission`` ∈ {``"none"``, ``"allowlisted-peers-only"``,
        ``"all"``}
      - ``allowed_peers`` state ∈ {peer-on-allowlist, peer-not-on-
        allowlist, peers-list-empty}

    Each cell pins a specific deny / admit outcome and the reason
    string when denying.
    """

    # ── dm_admission = "none" ────────────────────────────────────

    def test_dm_admission_none_peer_on_allowlist_denies(self) -> None:
        """``dm_admission="none"`` + peer on allowlist → deny via the
        dm_admission gate (peers axis passed first).
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
        """``dm_admission="none"`` + peer not on allowlist → deny via
        the peers axis (the dm_admission gate would also deny; peers
        fires first).
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "dm_admission": "none",
        })
        admits, reason = admits_inbound(
            acc, None, "P2", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == "peer_id 'P2' is not admitted on account 'acc-1'"

    def test_dm_admission_none_peers_empty_denies(self) -> None:
        """``dm_admission="none"`` + empty peers list → deny via the
        dm_admission gate (empty peers doesn't restrict).
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

    # ── dm_admission = "allowlisted-peers-only" ──────────────────

    def test_dm_admission_allowlisted_peers_only_peer_on_allowlist_admits(
        self,
    ) -> None:
        """``dm_admission="allowlisted-peers-only"`` + peer on
        allowlist → admit (peers passes; dm_admission rule satisfied).
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [],
            "dm_admission": "allowlisted-peers-only",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is True
        assert reason == ""

    def test_dm_admission_allowlisted_peers_only_peer_not_on_allowlist_denies(
        self,
    ) -> None:
        """``dm_admission="allowlisted-peers-only"`` + peer not on
        allowlist → deny via the peers axis (peers axis fires first).
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [],
            "dm_admission": "allowlisted-peers-only",
        })
        admits, reason = admits_inbound(
            acc, None, "P2", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == "peer_id 'P2' is not admitted on account 'acc-1'"

    def test_dm_admission_allowlisted_peers_only_peers_empty_denies(
        self,
    ) -> None:
        """``dm_admission="allowlisted-peers-only"`` + empty peers
        list → deny via the dm_admission gate (no peer approved yet).
        """
        acc = _account(allowlist={
            "peers": [], "channels": [],
            "dm_admission": "allowlisted-peers-only",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == (
            "DM denied: account 'acc-1' dm_admission is "
            "'allowlisted-peers-only' and no peers are on the allowlist"
        )

    # ── dm_admission = "all" ─────────────────────────────────────

    def test_dm_admission_all_peer_on_allowlist_admits(self) -> None:
        """``dm_admission="all"`` + peer on allowlist → admit."""
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P1", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is True
        assert reason == ""

    def test_dm_admission_all_peer_not_on_allowlist_denies(self) -> None:
        """``dm_admission="all"`` + peer not on allowlist → deny via
        the peers axis (non-empty peers restricts even when
        dm_admission is "all"). Pins the peers-as-universal-gate
        invariant.
        """
        acc = _account(allowlist={
            "peers": ["P1"], "channels": [], "dm_admission": "all",
        })
        admits, reason = admits_inbound(
            acc, None, "P2", "dm-channel", is_dm=True,
            guild_id=None, member_roles=None,
        )
        assert admits is False
        assert reason == "peer_id 'P2' is not admitted on account 'acc-1'"

    def test_dm_admission_all_peers_empty_admits(self) -> None:
        """``dm_admission="all"`` + empty peers list → admit (peers
        empty doesn't restrict; dm_admission permits).
        """
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
