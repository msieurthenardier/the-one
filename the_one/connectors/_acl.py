"""Per-agent and account-scope ACL admission — pure functions.

M10 F07 L2: extracts the per-axis tri-state admission logic that the
platform-send tool's outbound execute path (F6 L3) had inlined, and
adds the symmetric inbound counterpart that the F7 dispatcher
consumes after picking an agent.

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

from the_one.connectors.base import InboundEnvelope
from the_one.db.models import ConnectorAccount

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
    account: ConnectorAccount,
    agent_acl: dict[str, list[str] | None] | None,
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
    """
    # M10 F8 L8 — guilds/roles deliberately not consulted on outbound;
    # the kwargs are accepted for signature uniformity. See docstring.
    del guild_id, member_roles
    account_id = account.id
    # Account-scope channels axis.
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and channel_id not in allowed_channels:
            return (
                False,
                f"channel_id {channel_id!r} "
                f"is not reachable on account {account_id!r}",
            )
    # Per-agent channels axis.
    if agent_acl is not None:
        agent_channels = agent_acl.get("channels")
        if agent_channels is None:
            pass  # inherit account-scope
        elif agent_channels == []:
            # Per-agent DMs-only sentinel: ``[]`` means "no non-DM
            # channels admitted; DMs only." The plugin-resolved
            # ``is_dm`` bool decides the branch — permit if the target
            # is a DM, else deny.
            if is_dm:
                return True, ""
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r} (DMs-only override; "
                f"target is not a DM)",
            )
        elif channel_id not in agent_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r}",
            )
    return True, ""


def admits_dm_peer(
    account: ConnectorAccount,
    agent_acl: dict[str, list[str] | None] | None,
    peer_id: str,
) -> tuple[bool, str]:
    """Check whether reading DM history with ``peer_id`` on ``account`` is permitted.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny. The
    sibling of :func:`admits_outbound` for the peer axis — M11 F7 L10
    introduces it for the ``fetch_dm_history`` built-in tool, which gates
    on the per-(account, agent, peer) axis rather than the channel axis.

    Per-axis tri-state per the module docstring, applied to the peers
    axis at both scopes (mirrors the peers-block in
    :func:`admits_inbound` at the account-scope at lines 251-259 and the
    per-agent scope at lines 287-304):

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
    # Account-scope peers axis (mirrors admits_inbound:251-259).
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        allowed_peers = allowlist.get("peers", [])
        if allowed_peers and peer_id not in allowed_peers:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted on account "
                f"{account_id!r}",
            )
    # Per-agent peers axis (mirrors admits_inbound:287-304).
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
        elif peer_id not in agent_peers:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r}",
            )
    return True, ""


def admits_inbound(
    account: ConnectorAccount,
    agent_acl: dict[str, list[str] | bool | None] | None,
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
        + per-agent), the new account-scope **``dm_admission``** axis
        (``Literal["none", "allowlisted-peers-only", "all"]``), and the
        new per-agent **``admit_dms``** axis (``bool | None``, opt-out
        sentinel — ``False`` denies; ``True``/``None`` defer to the
        account-scope ``dm_admission`` decision).
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
    """
    account_id = account.id
    member_roles_set = set(member_roles or [])
    # Account-scope.
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        # 1. Peers axis (always consulted — both DMs and guild messages
        #    need allowlist membership when peers is non-empty).
        allowed_peers = allowlist.get("peers", [])
        if allowed_peers and peer_id not in allowed_peers:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted on account "
                f"{account_id!r}",
            )

        # M11 F10 L1 — DM-context branch.
        # When ``is_dm=True``, channels/guilds/roles axes are skipped
        # (they restrict guild-context messages, not DMs).
        # ``dm_admission`` gates DM admission orthogonally.
        if is_dm:
            dm_admission = allowlist.get(
                "dm_admission", "allowlisted-peers-only"
            )
            if dm_admission == "none":
                return (
                    False,
                    f"DM denied: account {account_id!r} dm_admission is "
                    f"'none'",
                )
            if dm_admission == "allowlisted-peers-only":
                # peers axis above already enforced this when allowed_peers
                # was non-empty. If allowed_peers is empty AND
                # dm_admission is allowlisted-peers-only, no peer has
                # been approved yet: deny.
                if not allowed_peers:
                    return (
                        False,
                        f"DM denied: account {account_id!r} dm_admission "
                        f"is 'allowlisted-peers-only' and no peers are "
                        f"on the allowlist",
                    )
            # dm_admission == "all", OR "allowlisted-peers-only" with
            # the peer on the allowlist: fall through to per-agent check.
        else:
            # Guild-context branch: channels / guilds / roles consulted
            # exactly as pre-L1.
            allowed_channels = allowlist.get("channels", [])
            if allowed_channels and channel_id not in allowed_channels:
                return (
                    False,
                    f"channel_id {channel_id!r} is not admitted on account "
                    f"{account_id!r}",
                )
            # M10 F8 L8 — account-scope guilds axis. Non-empty list
            # narrows to those guilds; ``guild_id=None`` (DM context)
            # against a non-empty list denies. (DMs now take the
            # ``if is_dm:`` branch above; this path is for guild
            # messages.)
            allowed_guilds = allowlist.get("guilds", [])
            if allowed_guilds and guild_id not in allowed_guilds:
                return (
                    False,
                    f"guild_id {guild_id!r} is not admitted on account "
                    f"{account_id!r}",
                )
            # M10 F8 L8 — account-scope roles axis. Any-of overlap;
            # empty ``member_roles`` against a non-empty axis denies.
            allowed_roles = allowlist.get("roles", [])
            if allowed_roles and not (
                member_roles_set & set(allowed_roles)
            ):
                return (
                    False,
                    f"peer roles do not overlap with admitted roles on "
                    f"account {account_id!r}",
                )
    # Per-agent.
    if agent_acl is not None:
        # Peers axis (always consulted — tri-state semantic preserved).
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
        elif peer_id not in agent_peers:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r}",
            )

        # M11 F10 L1 — per-agent DM-context branch.
        if is_dm:
            admit_dms = agent_acl.get("admit_dms")
            if admit_dms is False:
                return (
                    False,
                    f"DM denied: agent admit_dms is False on account "
                    f"{account_id!r}",
                )
            # admit_dms is None (inherit) or True (explicit-affirm —
            # same effect as inherit when account-scope permits): fall
            # through. The account-scope ``dm_admission`` gate above
            # already validated DM admissibility; per-agent
            # channels/guilds/roles axes are intentionally skipped for
            # DMs under the new orthogonal posture.
        else:
            # Guild-context branch — channels / guilds / roles axes
            # consulted exactly as pre-L1. Each axis retains its
            # tri-state shape.

            # Per-agent channels axis (same shape as outbound).
            agent_channels = agent_acl.get("channels")
            if agent_channels is None:
                pass  # inherit account-scope
            elif agent_channels == []:
                # Pre-L1 this branch was the "DMs-only override"; DMs
                # now take the ``if is_dm:`` branch above, so this
                # branch only fires for guild-context messages. The
                # message text is preserved verbatim for back-compat
                # with the existing test pins (test_connectors_acl.py
                # ``test_per_agent_channels_empty_is_dms_only_sentinel``
                # and ``test_per_agent_channels_empty_with_is_dm_false_denies``)
                # which assert this exact byte-string. Operators who
                # want DMs-only-on-this-agent now express it via the
                # orthogonal account-scope ``dm_admission`` + per-agent
                # ``admit_dms`` mechanism.
                return (
                    False,
                    f"channel_id {channel_id!r} is not admitted for this "
                    f"agent on account {account_id!r} (DMs-only override; "
                    f"envelope is not a DM)",
                )
            elif channel_id not in agent_channels:
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

            # M10 F8 L8 — per-agent roles axis (unchanged from pre-L1).
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
            elif not (member_roles_set & set(agent_roles)):
                return (
                    False,
                    f"peer roles do not overlap with admitted roles for "
                    f"this agent on account {account_id!r}",
                )
    return True, ""
