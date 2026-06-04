"""Multi-agent routing resolution engine — pure function.

M10 F07 L4: walks the routing rules on a connector account's
``config["routing"]`` and picks an attached agent for an inbound
envelope. The 5-step algorithm (override → rule-walk → default →
first-eligible-alphabetical → no-eligible) is the dispatcher's
single source of truth for "given this inbound, which agent handles
it?"

Pure — no I/O. The caller (F7 L5 dispatcher) is responsible for:

- resolving ``eligible_attached_agents`` via
  :meth:`SQLiteAgentStore.list_by_connector` (F7 L3),
- passing ``account`` and ``envelope`` from the dispatch context,
- passing ``session_metadata`` (the chat session's full metadata
  dict; the engine reads ``session_metadata.get("routing_override")``
  for Step 1).

**5-step algorithm**:

1. **Override** — if ``session_metadata["routing_override"]`` is a
   non-empty string AND that agent is in ``eligible_attached_agents``
   AND :func:`admits_inbound` permits, return it. Otherwise fall
   through.

2. **Rule-walk** — iterate ``account.config["routing"]["rules"]`` in
   operator-declared order. For each rule, check the scope-to-envelope
   match (see Scope-match semantics below), then verify the rule's
   target agent is eligible-and-permitted. First non-skipped rule wins.

3. **Per-account default** — if ``config["routing"]["default"]`` is a
   non-empty string AND that agent is eligible-and-permitted, return
   it. Otherwise fall through.

4. **First-eligible-alphabetical** — iterate ``eligible_attached_agents``
   (caller pre-sorted alphabetically). Return the first agent whose
   per-agent ACL admits. Reason ``"first-eligible"``.

5. **No-eligible** — every agent denied (or list empty). Return
   ``RoutingDecision(agent=None, reason="no-eligible-agent")``. F7 L5
   dispatcher emits the "No agents available for this conversation."
   peer-facing message via the system-outbound path.

**Scope-match semantics** (F7 L4 ships a plugin-agnostic semantic;
F8 / F9 plugins MAY narrow it via future plugin hooks):

Each rule's ``match`` is a ``list[str]`` of one or more values; the
rule fires if ANY listed value matches the envelope's corresponding
field (set-membership / OR semantics).

- ``channel`` — matches when ``envelope.channel_id`` is in
  ``rule.match``, regardless of thread_id. A thread message inside a
  matched channel still matches a channel rule UNLESS an earlier
  thread rule wins.
- ``thread`` — matches when ``envelope.thread_id is not None AND
  envelope.thread_id`` is in ``rule.match``. Top-level (non-thread)
  envelopes never match a thread rule.
- ``dm`` — matches when ``envelope.thread_id is None AND
  envelope.peer_id`` is in ``rule.match``. The "no thread" condition
  is the closest plugin-agnostic proxy for "this is a DM, not a guild
  channel." F8 / F9 plugins that distinguish DMs more precisely can
  refine this in their plugin layer.
- ``peer`` — matches when ``envelope.peer_id`` is in ``rule.match``,
  regardless of channel_id / thread_id.

**ACL admission** — every step that returns an agent (override,
rule-walk, default, first-eligible) verifies the picked agent's
``connector_acls[account.id]`` admits the envelope via
:func:`the_one.connectors._acl.admits_inbound`. Per-axis tri-state
semantic per F7 L2.

**Routing override** — F7 L6's ``/talk-to`` handler writes
``session_metadata["routing_override"] = "<slug>"`` via F7 L5's
``set_session_metadata_key`` primitive. F7 L6's ``/new`` / ``/reset``
handler discards the override implicitly by starting a new session.

Used by F7 L5 dispatcher integration. F7 L7 Studio editor authors
``config["routing"]``; this engine consumes the validated shape.

**Audit-log single-winner semantic (M10 F8 L1 clarification).** A
SINGLE :class:`RoutingDecision` is emitted per ``dispatch_inbound``
invocation. The audit-log entry that lands in
``session_metadata["routing"]`` captures the eventual winner's
``agent``, ``match``, ``reason``, ``scope``, ``rule_index``, and
``disposition`` — rules that were considered and skipped (because
their target agent was ACL-denied, no longer attached, or unknown)
are NOT enumerated alongside the winner. The F7 flight spec's
language about a "chain of skipped candidates" was post-hoc
reconciled in F8 L1: the shipped engine emits the winner only, and
the single-winner shape is the contract. A richer chain-audit (e.g.
listing every candidate the engine walked past, with its
skip-reason) is **deferred to F10 hardening** — operator UX
requirements there will drive whether the audit-entry shape grows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from the_one.agent.config import AgentConfig
from the_one.connectors._acl import AdmissionContext, admits_inbound
from the_one.connectors.base import InboundEnvelope
from the_one.db.models import Connector

__all__ = ["RoutingDecision", "resolve_routing"]


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """The output of :func:`resolve_routing`.

    Carries the picked agent (or ``None`` on no-eligible) plus the
    metadata F7 L5's audit-log writer needs (which step picked it,
    which rule index matched, the matched scope and the envelope value
    that hit).

    **Scope-uniformity invariant** — ``scope`` is ALWAYS a non-empty
    string for every path (``"channel"`` / ``"thread"`` / ``"dm"`` /
    ``"peer"`` for rule-walk; ``"override"`` / ``"default"`` /
    ``"first-eligible"`` / ``"no-eligible-agent"`` for non-rule
    paths). This lets F7 L5's audit-log renderer write
    ``f"reason={d.reason}, scope={d.scope}"`` without a None branch.
    Do NOT "simplify" this back to ``scope=None`` for non-rule paths
    — the renderer relies on the uniformity.

    **``match`` semantics** — the SINGLE envelope value that triggered
    the rule (e.g. ``envelope.channel_id`` for a ``channel`` rule), not
    the rule's full match list. This makes the audit log read clearly
    ("the rule fired because channel was C2") even when the rule's
    match list contains multiple values. ``None`` on non-rule paths.
    """

    agent: str | None
    rule_index: int | None
    scope: str | None
    match: str | None
    reason: str


def _agent_admits(
    account: Connector,
    agent_config: AgentConfig,
    envelope: InboundEnvelope,
    plugin: Any | None = None,
) -> bool:
    """ACL admission helper — wraps :func:`admits_inbound` for the
    agent's per-account ACL.

    Per L2 docstring: per-agent ACL inner dict is keyed by
    ``account.id`` in :attr:`AgentConfig.connector_acls`.

    ``plugin`` is the resolved :class:`ConnectorPlugin` instance for
    ``account.type`` (the F8 dispatcher already resolves it via
    :func:`the_one.connectors.registry.resolve`). The plugin's
    optional ``is_dm`` hook is consulted via the
    ``optional-plugin-hook-via-getattr-sentinel`` convention to
    resolve DM-truth for the envelope; the resolved bool is threaded
    into :func:`admits_inbound` so the per-agent DMs-only branch can
    permit DM envelopes. ``plugin=None`` (defensive fallback;
    shouldn't happen in practice — the dispatcher always resolves it)
    short-circuits to :func:`_default_not_dm`, preserving pre-F8
    fail-closed behavior.
    """
    agent_acl: dict[str, list[str] | None] | None = None
    if agent_config.connector_acls is not None:
        agent_acl = agent_config.connector_acls.get(account.id)
    # M11 F14 L8 — the envelope-derived admission facts (is_dm via the
    # plugin hook, guild_id + member_roles from envelope.raw) are now
    # bundled into a frozen AdmissionContext by from_envelope, which
    # owns the derivation formerly inlined here (and shared verbatim
    # with the command-handler's secondary admission).
    admits, _reason = admits_inbound(
        account,
        agent_acl,
        AdmissionContext.from_envelope(envelope, plugin),
    )
    return admits


def _scope_matches(
    rule_scope: str,
    rule_match: list[str],
    envelope: InboundEnvelope,
) -> str | None:
    """Check whether a rule's scope matches the envelope.

    ``rule_match`` is a non-empty list of values (set-membership / OR
    semantics — the rule fires if ANY listed value matches the
    envelope's corresponding field).

    Returns the envelope value that triggered the match (e.g.
    ``envelope.channel_id`` for a ``channel`` rule) on success, or
    ``None`` if the rule does not match. The returned value is what
    :class:`RoutingDecision.match` carries downstream — the audit log
    records the value that hit, not the full rule list.

    See module docstring for the per-scope semantics. The unknown-scope
    branch returns ``None`` defensively — the L2 validator rejects
    unknown scopes at write time, so this branch is unreachable from
    persisted configs but guards against direct-construct test
    artifacts and future-plugin-introduced scope strings the engine
    doesn't know about.
    """
    if rule_scope == "channel":
        if envelope.channel_id in rule_match:
            return envelope.channel_id
        return None
    if rule_scope == "thread":
        if envelope.thread_id is not None and envelope.thread_id in rule_match:
            return envelope.thread_id
        return None
    if rule_scope == "dm":
        if envelope.thread_id is None and envelope.peer_id in rule_match:
            return envelope.peer_id
        return None
    if rule_scope == "peer":
        if envelope.peer_id in rule_match:
            return envelope.peer_id
        return None
    return None  # unknown scope — defensive; validator should reject


def resolve_routing(
    account: Connector,
    envelope: InboundEnvelope,
    eligible_attached_agents: list[AgentConfig],
    session_metadata: dict[str, Any] | None,
    plugin: Any | None = None,
) -> RoutingDecision:
    """Pick an attached agent for ``envelope`` per the 5-step algorithm.

    See module docstring for the algorithm and scope-match semantics.

    **Precondition** — ``eligible_attached_agents`` MUST be alphabetically
    ordered by ``name``. Pass the output of
    :meth:`SQLiteAgentStore.list_by_connector` unmodified (F7 L3
    landed that helper with the ``ORDER BY name`` already enforced).
    Step 4 returns the FIRST element by input order whose ACL admits —
    passing a non-alphabetized list breaks the
    first-eligible-alphabetical semantic the dispatcher's audit log
    promises.

    ``plugin`` is the resolved :class:`ConnectorPlugin` instance for
    ``account.type``. F8 L6 added it so :func:`_agent_admits` can
    consult the plugin's optional ``is_dm`` hook for the per-agent
    DMs-only ACL branch. Default ``None`` preserves pre-F8 behavior
    for callers that haven't been updated (the consult site short-
    circuits to :func:`_default_not_dm`, which returns ``False`` —
    the historical fail-closed semantic).
    """
    agents_by_name: dict[str, AgentConfig] = {a.name: a for a in eligible_attached_agents}

    # Step 1 — Override.
    override = (session_metadata or {}).get("routing_override")
    if isinstance(override, str) and override:
        candidate = agents_by_name.get(override)
        if candidate is not None and _agent_admits(account, candidate, envelope, plugin):
            return RoutingDecision(
                agent=override,
                rule_index=None,
                scope="override",
                match=None,
                reason="override",
            )
        # Otherwise fall through.

    # Step 2 — Rule-walk.
    routing = account.config.get("routing") or {}
    rules = routing.get("rules") or []
    for i, rule in enumerate(rules):
        matched_value = _scope_matches(rule["scope"], rule["match"], envelope)
        if matched_value is None:
            continue
        candidate = agents_by_name.get(rule["agent"])
        if candidate is None:
            continue
        if not _agent_admits(account, candidate, envelope, plugin):
            continue
        return RoutingDecision(
            agent=rule["agent"],
            rule_index=i,
            scope=rule["scope"],
            match=matched_value,
            reason="rule-match",
        )

    # Step 3 — Per-account default.
    default = routing.get("default")
    if isinstance(default, str) and default:
        candidate = agents_by_name.get(default)
        if candidate is not None and _agent_admits(account, candidate, envelope, plugin):
            return RoutingDecision(
                agent=default,
                rule_index=None,
                scope="default",
                match=None,
                reason="default",
            )
        # Otherwise fall through.

    # Step 4 — First-eligible-alphabetical.
    for agent_config in eligible_attached_agents:
        if _agent_admits(account, agent_config, envelope, plugin):
            return RoutingDecision(
                agent=agent_config.name,
                rule_index=None,
                scope="first-eligible",
                match=None,
                reason="first-eligible",
            )

    # Step 5 — No-eligible.
    return RoutingDecision(
        agent=None,
        rule_index=None,
        scope="no-eligible-agent",
        match=None,
        reason="no-eligible-agent",
    )
