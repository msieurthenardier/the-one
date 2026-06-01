"""Per-agent and account-scope ACL admission — pure functions.

M10 F07 L2: extracts the per-axis tri-state admission logic that the
platform-send tool's outbound execute path (F6 L3) had inlined, and
adds the symmetric inbound counterpart that the F7 dispatcher
consumes after picking an agent.

M11 F12 L3: structured-tuple storage for peers / channels / roles
landed (v24 migration). All helpers consume structured dicts:

  - ``peers`` (account-scope): ``list[{id: str, dm_allowed: bool}]``
  - ``peers`` (per-agent, post-F13 L2): ``list[{id: str}]`` —
    ``dm_allowed`` is REJECTED at this scope (F12 footgun retirement)
  - ``channels``: ``list[{guild_id: str | None, channel_id: str}]``
  - ``roles``: ``list[{guild_id: str | None, role_id: str}]``

Plus the ``dm_admission`` Literal value rename
``"allowlisted-peers-only"`` → ``"admin-approved"``.

Two functions, both pure (no I/O, no repository access):

- :func:`admits_outbound` — account-scope channels intersected with
  per-agent channels. F6 HAT-redesigned "empty list = unrestricted"
  semantic on the account-scope channels axis. Per-agent
  ``channels: []`` is the DMs-only sentinel (fail-closed pending F8
  DM classification).
- :func:`admits_inbound` — covers BOTH peers AND channels axes at
  both scopes. Designed for use by the dispatcher's per-agent
  admission check.

**Per-axis semantic framing — narrowing vs defaulting** (codifies the
F6 HAT-redesign rule and extends it consistently to the per-agent
peers axis):

- **Account-scope axes are DEFAULTING anchors.** ``allowlist`` absent
  → unrestricted; ``allowlist.{peers,channels} = []`` → unrestricted
  (HAT-redesigned: empty list at this scope means "no explicit list",
  not "explicitly nobody"); non-empty list → subset.
- **Per-agent axes are NARROWING modifiers.** ``None`` → inherit
  account-scope (no narrowing); non-empty list → narrows to listed
  items (intersected with account-scope); ``[]`` → the strongest
  narrowing signal: "no items on this axis." For channels axis: DMs-
  only fail-closed pending F8. For peers axis: no peer admitted via
  this agent on this account.

The asymmetry between scopes for the SAME axis is intentional and
follows the framing — account-scope ``[]`` means "no explicit list";
per-agent ``[]`` means "explicitly no items." See M10 F7 L2 leg
artifact for the full rationale and the dedicated regression test.

**Reason-string vocabulary**:

- Outbound channel reasons use the verb **"reachable"** — verbatim
  from F6, locked by exact-equality assertions in
  ``tests/test_connector_send_tool.py``. Cannot be changed without
  updating those tests.
- Inbound reasons (this leg) use the verb **"admitted"**. New
  vocabulary; not back-compat-constrained.

The divergence is a F6-back-compat reality, not a vocabulary
preference. The dispatcher audit-log (F7 L5) and the Studio surfaces
(F7 L7) should pick one verb deliberately and stay consistent.

All deny paths return ``(False, reason)`` where ``reason`` is a
short operator-readable string suitable for embedding into the
``[error] [constraint] ...`` envelope at the call site.
"""

from __future__ import annotations

from typing import Any

from the_one.connectors.base import InboundEnvelope
from the_one.db.models import Connector

__all__ = [
    "admits_outbound",
    "admits_inbound",
    "admits_dm_peer",
    "_default_not_dm",
    "_default_no_mention",
]


def _default_not_dm(envelope: InboundEnvelope) -> bool:
    """Sentinel fallback for the ``is_dm`` plugin hook.

    Returned by ``getattr(plugin, "is_dm", _default_not_dm)`` at the
    inbound-routing consult site for plugins that do not implement the
    optional ``is_dm`` extension. Returning ``False`` preserves the
    historical fail-closed behavior of the DMs-only ACL branch for
    plugins (e.g. the test-only stub) without a DM-classification hook.

    Mirrors F6's :func:`_default_permit` shape (named module-level
    callable returning the default outcome — see ``agents.md`` §
    ``optional-plugin-hook-via-getattr-sentinel``).
    """
    return False


def _default_no_mention(envelope: InboundEnvelope) -> bool:
    """Sentinel fallback for the ``is_mention`` plugin hook.

    Returned by ``getattr(plugin, "is_mention", _default_no_mention)``
    at the F7 policy-gate consult site (L8) for plugins that do not
    implement the optional ``is_mention`` extension. Returning
    ``False`` preserves the gate's silent-by-default branch for
    plugins without a mention concept (webhook-driven future
    connectors, the test stub).

    Mirrors :func:`_default_not_dm` (named module-level callable
    returning the default outcome — see ``agents.md`` §
    ``optional-plugin-hook-via-getattr-sentinel``). Added M11 F7 L1
    alongside the ``DiscordPlugin.is_mention`` opt-in implementation;
    the consult site itself lands at F7 L8.
    """
    return False


def admits_outbound(
    account: Connector,
    agent_acl: dict[str, Any] | None,
    channel_id: str,
    *,
    is_dm: bool = False,
    guild_id: str | None = None,
    member_roles: list[str] | None = None,
) -> tuple[bool, str]:
    """Check whether outbound to ``channel_id`` on ``account`` is permitted.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny.
    ``reason`` is suitable for embedding directly after the
    ``[error] [constraint] `` envelope prefix.

    Per-axis tri-state per the module docstring. Account-scope channels
    intersected with per-agent channels.

    ``is_dm`` participates only in the per-agent DMs-only branch
    (``agent_channels == []``): if the caller signals the target is a
    DM, the branch permits; otherwise it denies. Default ``False``
    preserves pre-F8 fail-closed behavior for callers that have not
    resolved the DM-truth at the consult site.

    **Outbound DM-truth posture (F8 L6)** — the F4 platform-send tool
    has ``(account, channel_id, thread_id)`` at outbound time but no
    inbound envelope context. It therefore omits ``is_dm`` (or passes
    ``False``); the DMs-only branch then denies. F10 hardening can
    add a plugin-level outbound DM determination if HAT surfaces the
    need (e.g. ``plugin.is_dm_target(target)``).

    **M10 F8 L8 — guilds/roles axes accepted but NOT consulted on
    outbound.** The F4 platform-send tool has no envelope context, so
    there is no ``guild_id`` or ``member_roles`` to evaluate at outbound
    time. The kwargs are accepted for signature uniformity with
    :func:`admits_inbound` (a future call site could pass them); the
    body silently ignores them. This is consistent with the F6
    channel-axis fallback rationale — outbound runs with the subset of
    axes that have target-side meaning. F10 hardening can revisit if
    HAT surfaces concrete needs (e.g. a plugin-resolved
    ``send_target_guild_id``).

    **Outbound channel-tuple match semantic — LOCKED (M11 F12 L3, extended L5)**:
    outbound matches by ``channel_id`` ALONE, ignoring the per-entry
    ``guild_id``. The F4 platform-send tool has no envelope ``guild_id``
    context at outbound time, so we cannot validate a guild_id
    constraint. This is symmetric to inbound's wildcard-``channel_id``-
    handling — both branches honor backward-compat with operator-curated
    allowlists. If a future flight needs strict outbound guild-binding,
    it should add a plugin-resolved ``send_target_guild_id`` (cycle-1
    finding #5; locked decision per F12 L3 spec).

    **Wildcard sentinel (M11 F12 L5)** — a channel entry with
    ``channel_id == "*"`` means "any channel of this guild" at the
    storage level. Because outbound matches by ``channel_id`` alone
    (ignoring ``guild_id``), the wildcard simply admits ANY ``channel_id``
    whenever a wildcard entry exists in the list. The hierarchical
    Server-as-parent UI emits this sentinel when a server row is added
    without explicit channel narrowing.
    """
    # M10 F8 L8 — guilds/roles deliberately not consulted on outbound;
    # the kwargs are accepted for signature uniformity. See docstring.
    del guild_id, member_roles
    account_id = account.id
    # Account-scope channels axis (M11 F12 L3 structured tuples; match
    # by channel_id ALONE per the locked outbound semantic above).
    # M11 F12 L5 — ``channel_id == "*"`` is the wildcard sentinel that
    # admits any channel_id.
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and not any(
            c["channel_id"] == "*" or c["channel_id"] == channel_id
            for c in allowed_channels
        ):
            return (
                False,
                f"channel_id {channel_id!r} "
                f"is not reachable on account {account_id!r}",
            )
    # Per-agent channels axis (same structured-tuple shape; same
    # wildcard handling).
    if agent_acl is not None:
        agent_channels = agent_acl.get("channels")
        if agent_channels is None:
            pass  # inherit account-scope
        elif agent_channels == []:
            # Per-agent channels axis is explicitly empty: permit DMs, deny everything else.
            if is_dm:
                return True, ""
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r} (per-agent "
                f"channels axis is explicitly empty)",
            )
        elif not any(
            c["channel_id"] == "*" or c["channel_id"] == channel_id
            for c in agent_channels
        ):
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r}",
            )
    return True, ""


def admits_dm_peer(
    account: Connector,
    agent_acl: dict[str, Any] | None,
    peer_id: str,
) -> tuple[bool, str]:
    """Check whether reading DM history with ``peer_id`` on ``account`` is permitted.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny. The
    sibling of :func:`admits_outbound` for the peer axis — M11 F7 L10
    introduces it for the ``fetch_dm_history`` built-in tool, which gates
    on the per-(account, agent, peer) axis rather than the channel axis.

    M11 F12 L3 — peers entries are structured dicts (account-scope:
    ``{id, dm_allowed}``; per-agent post-F13 L2: ``{id}`` only — the
    F12 footgun was retired); this helper consults only the ``id``
    field at both scopes (DM-history reads are not gated by the
    per-peer ``dm_allowed`` toggle — that toggle gates inbound DM
    admission at account scope only, not outbound history reads).

    Per-axis tri-state per the module docstring, applied to the peers
    axis at both scopes:

    - Account-scope ``allowlist.peers`` absent → unrestricted; ``[]`` →
      unrestricted; non-empty list and ``peer_id`` not in it → deny.
    - Per-agent ``peers`` is ``None`` → inherit account-scope; ``[]`` →
      deny (explicit-empty narrowing: no peer admitted via this agent
      on this account — NOT a DMs-only sentinel; the DMs-only sentinel
      is ``channels=[]`` per the module docstring); non-empty list and
      ``peer_id`` not in it → deny.

    Reason strings use the verb **"admitted"** (mirrors
    :func:`admits_inbound`'s vocabulary; not back-compat-constrained by
    the F6 outbound exact-equality assertions in
    ``tests/test_connector_send_tool.py``).
    """
    account_id = account.id
    # Account-scope peers axis (M11 F12 L3 structured-dict consumption).
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        allowed_peers = allowlist.get("peers", [])
        if allowed_peers and not any(
            p["id"] == peer_id for p in allowed_peers
        ):
            return (
                False,
                f"peer_id {peer_id!r} is not admitted on account "
                f"{account_id!r}",
            )
    # Per-agent peers axis (same structured-dict shape).
    if agent_acl is not None:
        agent_peers = agent_acl.get("peers")
        if agent_peers is None:
            pass  # inherit account-scope
        elif agent_peers == []:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r} (per-agent peers axis is "
                f"explicitly empty)",
            )
        elif not any(p["id"] == peer_id for p in agent_peers):
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r}",
            )
    return True, ""


def admits_inbound(
    account: Connector,
    agent_acl: dict[str, Any] | None,
    peer_id: str,
    channel_id: str,
    *,
    is_dm: bool = False,
    guild_id: str | None = None,
    member_roles: list[str] | None = None,
) -> tuple[bool, str]:
    """Check whether inbound from ``peer_id`` in ``channel_id`` on
    ``account`` is permitted to invoke this agent.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny.

    **DM-with-guild-restriction posture (M11 F10 L1)** — DMs are
    orthogonal to guild-context restrictions. The ``is_dm`` parameter
    gates which axes get consulted:

      - ``is_dm=True`` consults only the **peers** axis (account-scope
        + per-agent), the account-scope **``dm_admission``** axis
        (``Literal["none", "admin-approved", "all"]`` — renamed in
        M11 F12 L3 from ``"allowlisted-peers-only"``), the per-peer
        ``dm_allowed`` field (account-scope; consulted only under the
        ``"admin-approved"`` policy mode per the F12 L3 Truth Table),
        and the per-agent **``admit_dms``** axis (``bool | None``,
        opt-out sentinel — ``False`` denies; ``True``/``None`` defer
        to the account-scope ``dm_admission`` + per-peer composition).
      - ``is_dm=False`` consults the **peers / channels / guilds /
        roles** axes per the established 4-axis ACL semantics.

    This inverts the F8 L8 documented "DMs out-of-scope under guild
    restriction" posture (which conflated guild-channel restriction
    with DM-admission scope); F10 L1 splits them per the F9 L8 HAT
    findings.

    Used by F7 L5 dispatcher AFTER the routing engine (F7 L4) picks an
    agent, to verify the picked agent's per-agent ACL admits this
    (peer, channel, guild, roles) combination. F6's plugin resolver
    hook handles account-scope first-contact pairing — this function
    is the per-agent admission layer that composes on top.

    ``is_dm`` is the envelope-resolved DM-truth (defaults to ``False``
    for callers that have not resolved DM-truth — preserves pre-F8
    fail-closed behavior on the channels-axis path). The routing
    engine's :func:`_agent_admits` consults the plugin's optional
    ``is_dm`` hook via the ``optional-plugin-hook-via-getattr-sentinel``
    convention and passes the resolved bool here.

    **M10 F8 L8 — guilds and roles axes** (only consulted when
    ``is_dm=False``). ``guild_id`` is the envelope-resolved guild
    identifier (str) or ``None`` for DMs and other guildless contexts.
    ``member_roles`` is the envelope-resolved list of role IDs the peer
    holds in the guild (empty list for DMs). Both axes follow the
    per-axis tri-state semantic (see module docstring +
    ``per-axis-tri-state-override`` in agents.md):

      - axis absent from ``allowlist`` / ``agent_acl`` → unrestricted
      - axis is ``[]`` → unrestricted on this axis at account-scope;
        explicit-empty narrowing at per-agent scope
      - axis is ``[items]`` → subset (must match for admit)

    **Roles overlap semantic** — if the ``roles`` axis is non-empty,
    admit iff ``set(member_roles) & set(allowlist['roles'])`` is
    non-empty (any-of overlap). Empty ``member_roles`` against a
    non-empty ``roles`` axis denies (peer has no roles, role-
    restricted account denies — consistent with the per-axis subset
    semantic).

    **Internal structure (F12 L2)** — this function is a thin
    dispatcher consulting ``is_dm`` and delegating to one of two
    private helpers (:func:`_admits_inbound_dm` for the DM-context
    branches, :func:`_admits_inbound_guild` for the guild-context
    branches). The extraction is structurally a no-op; the helpers
    own their own input prep (``account_id`` derivation, ``allowlist``
    lookup, ``member_roles_set`` computation). See the
    ``two-symmetric-paths-in-acl`` convention in ``agents.md`` for
    the cross-path discipline.
    """
    if is_dm:
        return _admits_inbound_dm(
            account, agent_acl, peer_id, channel_id
        )
    return _admits_inbound_guild(
        account,
        agent_acl,
        peer_id,
        channel_id,
        guild_id=guild_id,
        member_roles=member_roles,
    )


def _admits_inbound_dm(
    account: Connector,
    agent_acl: dict[str, Any] | None,
    peer_id: str,
    channel_id: str,
) -> tuple[bool, str]:
    """Handles the DM-context branches of :func:`admits_inbound` (``is_dm=True``).

    Per the ``dms-orthogonal-to-guild-restriction`` convention
    (``agents.md``), DMs consult only the peers axis (account-scope +
    per-agent), the account-scope ``dm_admission`` axis, and the
    per-agent ``admit_dms`` axis. Channels / guilds / roles axes are
    intentionally skipped.

    **M11 F12 L3 — DM Composition Truth Table (operator-confirmed)**:

    ``admit_dm = (admit_dms is not False)
              AND (peer in allowlist)
              AND (dm_admission == "all" OR
                   (dm_admission == "admin-approved" AND
                    peer.dm_allowed == true))``

    Where:

      - ``admit_dms`` is the per-agent opt-out (``bool | None``;
        ``False`` short-circuits to deny; ``True`` / ``None`` defer
        to the account-scope composition).
      - ``peer in allowlist`` is the peers-axis membership check
        (account-scope; structured-dict id match per F12 L3).
      - ``dm_admission`` is the account-scope DM-admission policy
        Literal (``"none"`` / ``"admin-approved"`` / ``"all"``).
      - ``peer.dm_allowed`` is the per-peer (account-scope) DM
        toggle introduced by F12 L3; ONLY consulted under the
        ``"admin-approved"`` policy mode. Under ``"all"`` it is
        ignored; under ``"none"`` admission is denied regardless.

    **Per-agent peers entries DO NOT carry a ``dm_allowed`` field**
    (F13 L2 — F12 footgun retirement; the v26 migration strips the
    field from stored data and the Pydantic validator at
    ``the_one/agent/config.py:_validate_connector_acls`` REJECTS it
    post-v26). DM admission is decided at the account-scope per-peer
    ``dm_allowed`` only. If a future flight wants per-agent DM
    granularity (e.g. "this peer can DM agent A but not agent B"),
    that requires a substrate change.

    Private helper — callers outside ``_acl.py`` should consult
    :func:`admits_inbound` (the public dispatcher) directly.
    """
    del channel_id  # DM path does not consult the channels axis.
    account_id = account.id

    # Per-agent admit_dms — deny short-circuit (composition rule
    # factor 1: admit_dms is not False).
    if agent_acl is not None:
        admit_dms = agent_acl.get("admit_dms")
        if admit_dms is False:
            return (
                False,
                f"DM denied: agent admit_dms is False on account "
                f"{account_id!r}",
            )

    # Account-scope.
    allowlist = account.config.get("allowlist")
    peer_entry: dict[str, Any] | None = None
    if allowlist is not None:
        allowed_peers = allowlist.get("peers", [])
        # Locate the structured peer entry (composition rule factor 2:
        # peer in allowlist; structured-dict id match per F12 L3).
        peer_entry = next(
            (p for p in allowed_peers if p["id"] == peer_id), None
        )
        # Peers-axis membership: if peers is non-empty AND the peer is
        # not in it, deny BEFORE consulting dm_admission (precedence
        # per F12 L3 cycle-1 cell-#3 clarification).
        if allowed_peers and peer_entry is None:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted on account "
                f"{account_id!r}",
            )

        # M11 F10 L1 + M11 F12 L3 — DM-context branch.
        # ``dm_admission`` gates DM admission orthogonally to
        # channels/guilds/roles (which restrict guild-context messages).
        dm_admission = allowlist.get("dm_admission", "admin-approved")
        if dm_admission == "none":
            # Composition rule factor 3a: dm_admission == "all" OR
            # "admin-approved" — "none" fails this regardless.
            return (
                False,
                f"DM denied: account {account_id!r} dm_admission is "
                f"'none'",
            )
        if dm_admission == "admin-approved":
            # Composition rule factor 3b: admin-approved requires
            # peer in allowlist AND peer.dm_allowed == true.
            if peer_entry is None:
                # admin-approved + no peers (or peer not in non-empty
                # peers — but that branch already returned above) →
                # deny (no one approved yet under this policy).
                return (
                    False,
                    f"DM denied: account {account_id!r} dm_admission "
                    f"is 'admin-approved' and peer not in allowlist",
                )
            if not peer_entry.get("dm_allowed", False):
                return (
                    False,
                    f"DM denied: peer {peer_id!r} has dm_allowed=false "
                    f"under admin-approved policy on account "
                    f"{account_id!r}",
                )
        # dm_admission == "all": ignore per-peer dm_allowed; admit
        # (peers-axis check above already enforced the allowlist
        # membership when peers is non-empty).

    # Per-agent.
    if agent_acl is not None:
        # Peers axis (always consulted — tri-state semantic preserved).
        # Structured-dict id match per F12 L3.
        agent_peers = agent_acl.get("peers")
        if agent_peers is None:
            pass  # inherit account-scope
        elif agent_peers == []:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r} (per-agent peers axis is "
                f"explicitly empty)",
            )
        elif not any(p["id"] == peer_id for p in agent_peers):
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r}",
            )
        # admit_dms already deny-short-circuited above. admit_dms is
        # None (inherit) or True (explicit-affirm — same effect as
        # inherit when account-scope permits): fall through. The
        # account-scope ``dm_admission`` gate above already validated
        # DM admissibility; per-agent channels/guilds/roles axes are
        # intentionally skipped for DMs under the orthogonal posture.
    return True, ""


def _admits_inbound_guild(
    account: Connector,
    agent_acl: dict[str, Any] | None,
    peer_id: str,
    channel_id: str,
    *,
    guild_id: str | None,
    member_roles: list[str] | None,
) -> tuple[bool, str]:
    """Handles the guild-context branches of :func:`admits_inbound` (``is_dm=False``).

    Consults the 4-axis ACL semantics (peers / channels / guilds /
    roles) per M10 F8 L8 at both account-scope and per-agent scope.

    **M11 F12 L3 — structured-tuple consumption**. The peers axis
    uses structured ``{id, dm_allowed}`` dicts at account-scope and
    bare ``{id}`` dicts at per-agent scope (post-F13 L2; per-agent
    peers no longer carry ``dm_allowed`` — that field lives only at
    account-scope per the F12 L3 DM Composition Truth Table, and the
    guild path doesn't consume ``dm_allowed`` at any scope). The
    channels axis uses structured ``{guild_id, channel_id}`` dicts —
    a channel admits when its ``guild_id``
    matches the envelope ``guild_id`` AND (``channel_id`` matches OR
    ``channel_id == "*"``; see wildcard semantic below). Roles follow
    the same guild-scoped rule.

    **M11 F12 L5 — wildcard sentinel + post-v25 non-null guild_id**.
    After the v25 migration + Pydantic-validator tightening, every
    channel/role entry has a non-null ``guild_id`` (the legacy
    null-``guild_id``-is-permissive rule is GONE). A channel entry
    with ``channel_id == "*"`` admits any channel whose envelope
    ``guild_id`` matches the entry's ``guild_id``. A role entry with
    ``role_id == "*"`` admits any peer with any role membership in
    that guild (in fact admits regardless of ``member_roles``
    membership — the wildcard short-circuits the overlap check at
    the per-guild scope). The hierarchical Server-as-parent UI
    emits these sentinels when a server row is added without
    explicit channel/role narrowing.

    Private helper — callers outside ``_acl.py`` should consult
    :func:`admits_inbound` (the public dispatcher) directly.
    """
    account_id = account.id
    member_roles_set = set(member_roles or [])
    # Account-scope.
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        # 1. Peers axis (M11 F12 L3 — structured-dict id match).
        allowed_peers = allowlist.get("peers", [])
        if allowed_peers and not any(
            p["id"] == peer_id for p in allowed_peers
        ):
            return (
                False,
                f"peer_id {peer_id!r} is not admitted on account "
                f"{account_id!r}",
            )

        # 2. Channels axis (M11 F12 L3 — structured tuples; M11 F12 L5
        # — wildcard ``channel_id == "*"`` admits any channel matching
        # the entry's ``guild_id`` against the envelope ``guild_id``).
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and not any(
            c["guild_id"] == guild_id
            and (c["channel_id"] == "*" or c["channel_id"] == channel_id)
            for c in allowed_channels
        ):
            return (
                False,
                f"channel_id {channel_id!r} is not admitted on account "
                f"{account_id!r}",
            )
        # M10 F8 L8 — account-scope guilds axis. Non-empty list
        # narrows to those guilds; ``guild_id=None`` (DM context)
        # against a non-empty list denies. (DMs take the dedicated
        # :func:`_admits_inbound_dm` helper; this path is for guild
        # messages.)
        allowed_guilds = allowlist.get("guilds", [])
        if allowed_guilds and guild_id not in allowed_guilds:
            return (
                False,
                f"guild_id {guild_id!r} is not admitted on account "
                f"{account_id!r}",
            )
        # M10 F8 L8 + M11 F12 L3 + M11 F12 L5 — account-scope roles
        # axis. Each entry is a structured ``{guild_id, role_id}`` dict.
        # Wildcard ``role_id == "*"`` admits unconditionally for any
        # ``member_roles`` (including the empty list) as long as the
        # entry's ``guild_id`` matches the envelope ``guild_id``.
        # Otherwise admit iff ``member_roles_set & {r.role_id for r in
        # allowed_roles where r.guild_id == guild_id}`` is non-empty.
        allowed_roles = allowlist.get("roles", [])
        if allowed_roles:
            admitted_role_ids = {
                r["role_id"]
                for r in allowed_roles
                if r["guild_id"] == guild_id
            }
            if not admitted_role_ids:
                # No role allowance for this guild → deny.
                return (
                    False,
                    f"peer roles do not overlap with admitted roles on "
                    f"account {account_id!r}",
                )
            if "*" not in admitted_role_ids and not (
                member_roles_set & admitted_role_ids
            ):
                return (
                    False,
                    f"peer roles do not overlap with admitted roles on "
                    f"account {account_id!r}",
                )
    # Per-agent.
    if agent_acl is not None:
        # Peers axis (M11 F12 L3 — structured-dict id match).
        agent_peers = agent_acl.get("peers")
        if agent_peers is None:
            pass  # inherit account-scope
        elif agent_peers == []:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r} (per-agent peers axis is "
                f"explicitly empty)",
            )
        elif not any(p["id"] == peer_id for p in agent_peers):
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r}",
            )

        # Per-agent channels axis (M11 F12 L3 — structured tuples;
        # M11 F12 L5 — wildcard ``channel_id == "*"`` admits any
        # channel matching the entry's ``guild_id``).
        agent_channels = agent_acl.get("channels")
        if agent_channels is None:
            pass  # inherit account-scope
        elif agent_channels == []:
            # Per-agent channels axis is explicitly empty: deny all guild-context messages on this account for this agent.
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this "
                f"agent on account {account_id!r} (per-agent channels "
                f"axis is explicitly empty)",
            )
        elif not any(
            c["guild_id"] == guild_id
            and (c["channel_id"] == "*" or c["channel_id"] == channel_id)
            for c in agent_channels
        ):
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this "
                f"agent on account {account_id!r}",
            )

        # M10 F8 L8 — per-agent guilds axis (unchanged from pre-L1).
        agent_guilds = agent_acl.get("guilds")
        if agent_guilds is None:
            pass  # inherit account-scope
        elif agent_guilds == []:
            return (
                False,
                f"guild_id {guild_id!r} is not admitted for this agent "
                f"on account {account_id!r} (per-agent guilds axis is "
                f"explicitly empty)",
            )
        elif guild_id not in agent_guilds:
            return (
                False,
                f"guild_id {guild_id!r} is not admitted for this agent "
                f"on account {account_id!r}",
            )

        # M10 F8 L8 + M11 F12 L3 — per-agent roles axis (structured
        # tuples; NULL guild_id permissive per the rule above).
        agent_roles = agent_acl.get("roles")
        if agent_roles is None:
            pass  # inherit account-scope
        elif agent_roles == []:
            return (
                False,
                f"peer roles do not overlap with admitted roles for "
                f"this agent on account {account_id!r} (per-agent "
                f"roles axis is explicitly empty)",
            )
        else:
            # M11 F12 L5 — wildcard ``role_id == "*"`` admits
            # unconditionally for any ``member_roles`` (including the
            # empty list) when the entry's ``guild_id`` matches the
            # envelope ``guild_id``. Otherwise overlap-required.
            admitted_role_ids = {
                r["role_id"]
                for r in agent_roles
                if r["guild_id"] == guild_id
            }
            if not admitted_role_ids:
                return (
                    False,
                    f"peer roles do not overlap with admitted roles for "
                    f"this agent on account {account_id!r}",
                )
            if "*" not in admitted_role_ids and not (
                member_roles_set & admitted_role_ids
            ):
                return (
                    False,
                    f"peer roles do not overlap with admitted roles for "
                    f"this agent on account {account_id!r}",
                )
    return True, ""
