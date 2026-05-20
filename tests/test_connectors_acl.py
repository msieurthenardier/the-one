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
        """`[]` at per-agent = DMs-only fail-closed (F8-deferred)."""
        admits, reason = admits_outbound(
            _account(), {"peers": None, "channels": []}, "C1"
        )
        assert admits is False
        assert reason == (
            "channel_id 'C1' is not reachable for this agent on account "
            "'acc-1' (DMs-only override; DM classification lands in F8)"
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
        the inbound verb ("admitted")."""
        admits, reason = admits_inbound(
            _account(), {"peers": None, "channels": []}, "P1", "C1"
        )
        assert admits is False
        assert reason == (
            "channel_id 'C1' is not admitted for this agent on account "
            "'acc-1' (DMs-only override; DM classification lands in F8)"
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
