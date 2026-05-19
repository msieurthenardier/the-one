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

from the_one.db.models import ConnectorAccount

__all__ = ["admits_outbound", "admits_inbound"]


def admits_outbound(
    account: ConnectorAccount,
    agent_acl: dict[str, list[str] | None] | None,
    channel_id: str,
) -> tuple[bool, str]:
    """Check whether outbound to ``channel_id`` on ``account`` is permitted.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny.
    ``reason`` is suitable for embedding directly after the
    ``[error] [constraint] `` envelope prefix.

    Per-axis tri-state per the module docstring. Account-scope channels
    intersected with per-agent channels.
    """
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
            # F8: DM classification lands here — replace this fail-closed deny with "permit if envelope is a DM; else deny."
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r} (DMs-only override; "
                f"DM classification lands in F8)",
            )
        elif channel_id not in agent_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r}",
            )
    return True, ""


def admits_inbound(
    account: ConnectorAccount,
    agent_acl: dict[str, list[str] | None] | None,
    peer_id: str,
    channel_id: str,
) -> tuple[bool, str]:
    """Check whether inbound from ``peer_id`` in ``channel_id`` on
    ``account`` is permitted to invoke this agent.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny.
    Both axes (peers AND channels) must permit. Peers checked first;
    short-circuit on first deny.

    Used by F7 L5 dispatcher AFTER the routing engine (F7 L4) picks an
    agent, to verify the picked agent's per-agent ACL admits this
    (peer, channel) combination. F6's plugin resolver hook handles
    account-scope first-contact pairing — this function is the
    per-agent admission layer that composes on top.
    """
    account_id = account.id
    # Account-scope peers axis.
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        allowed_peers = allowlist.get("peers", [])
        if allowed_peers and peer_id not in allowed_peers:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted on account "
                f"{account_id!r}",
            )
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and channel_id not in allowed_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not admitted on account "
                f"{account_id!r}",
            )
    # Per-agent peers axis.
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
        # Per-agent channels axis (same shape as outbound).
        agent_channels = agent_acl.get("channels")
        if agent_channels is None:
            pass  # inherit account-scope
        elif agent_channels == []:
            # F8: DM classification lands here — replace this fail-closed deny with "permit if envelope is a DM; else deny."
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this agent "
                f"on account {account_id!r} (DMs-only override; DM "
                f"classification lands in F8)",
            )
        elif channel_id not in agent_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this agent "
                f"on account {account_id!r}",
            )
    return True, ""
