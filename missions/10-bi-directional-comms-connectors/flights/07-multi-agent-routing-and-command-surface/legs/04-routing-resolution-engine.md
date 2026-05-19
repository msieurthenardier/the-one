# Leg: routing-resolution-engine

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Land the pure-function routing engine in a new module `the_one/connectors/_routing.py`. The engine exports `resolve_routing(account, envelope, eligible_attached_agents, session_metadata) -> RoutingDecision` implementing the 5-step algorithm: (1) override-from-session_metadata; (2) rule-walk against `config["routing"]["rules"]`; (3) per-account default agent; (4) first-eligible-alphabetical attached agent; (5) no-eligible deny. ACL admission via L2's `admits_inbound` pure function. No dispatcher integration (L5), no command parsing (L1 + L5), no Studio surface (L7). F1–F7 (post-L3) regression suite passes byte-identically.

## Context

This is the fourth F7 leg. Per Design Decisions in `flight.md`:

- **"Account-config persistence with ordered rule list"** — routing rules live at `connector_accounts.config["routing"]["rules"]` as a list of `{scope, match, agent}` dicts in operator-declared order. L2 validated the shape.
- **"Specificity-then-order precedence"** — the engine walks the list top-to-bottom; first match wins. No precedence baked into code.
- **"Silent fallback through alphabetically-ordered eligible-attached-agent list"** — when no rule matches and no default is set, fall back to the first agent (alphabetical) in `eligible_attached_agents` whose ACL admits the envelope. If zero eligible, return `RoutingDecision(agent=None, reason="no-eligible-agent")`.
- **"Peer-issued routing override via session-scoped persistence"** — when `/talk-to <slug>` succeeds at L6, the dispatcher writes `session_metadata["routing_override"] = "<slug>"`. The engine consults this FIRST; short-circuits if the override points to an eligible agent. (If the override points to an INELIGIBLE agent — slug missing, ACL denies, no longer attached — the engine ignores the override and falls through to rule-walk. Audit-logged in L5.)
- **L4 unblocks L5** — the dispatcher integration (L5) wires the engine into `connectors/_inbound.dispatch_inbound`, replacing L3's transitional helper with the engine's pick.

Key learnings from prior legs:

- L1: parser is pure; `runtime_checkable` stdlib limitation noted; not relevant here.
- L2: `admits_inbound` is the per-axis-tri-state pure function the engine consults for ACL admission. Reason-string vocabulary is "admitted" (inbound). Per-axis framing: account-scope axes are DEFAULTING anchors (`[]` = unrestricted); per-agent axes are NARROWING modifiers (`[]` = strongest deny).
- L3: `SQLiteAgentStore.list_by_connector_account(account_id) -> list[AgentConfig]` is the canonical inverse-query for "all agents attached to this account." The engine receives `eligible_attached_agents` as input (caller-resolved) — keeps the engine pure (no I/O).

## Inputs

What exists before this leg runs:

- `the_one/connectors/_acl.py` exporting `admits_inbound(account, agent_acl, peer_id, channel_id) -> tuple[bool, str]`. Pure function; per-axis tri-state.
- `the_one/connectors/base.py` exporting `InboundEnvelope` dataclass with `platform / account_id / channel_id / thread_id / peer_id / peer_name / text / raw` fields.
- `the_one/db/models.py:ConnectorAccount` carries `.config: dict[str, Any]` where `config["routing"]` is the validated `{"rules": list[...], "default": str | None}` shape per L2.
- `the_one/agent/config.py:AgentConfig` carries `.name: str`, `.connector_account_ids: list[str]`, `.connector_acls: dict[str, dict[str, list[str] | None]] | None`.
- `the_one/db/repositories.py:SQLiteAgentStore.list_by_connector_account(account_id)` returns the alphabetically-ordered list of attached agents. L4 consumes the output but does NOT call this directly — L5's dispatcher resolves the list and passes it to the engine.
- F1–F7 (post-L3) test suite green: 404 tests pass for the connector + tool + repository regression.
- No existing `_routing.py`, `resolve_routing`, or `RoutingDecision` symbols anywhere in `the_one/` or `tests/` (grep verified).

## Outputs

What exists after this leg completes:

- `the_one/connectors/_routing.py` (NEW) exporting:
  - `RoutingDecision` — frozen-slotted dataclass with fields `agent: str | None`, `rule_index: int | None`, `scope: str | None`, `match: str | None`, `reason: str`. (Carries the matched-rule metadata for L5's audit log.)
  - `resolve_routing(account, envelope, eligible_attached_agents, session_metadata) -> RoutingDecision` — pure function, no I/O.
- `tests/test_connectors_routing.py` (NEW) pinning the 5-step algorithm + edge cases.
- F1–F7 (post-L3) regression suite passes byte-identically; `tests/test_connectors_routing.py` adds new tests on top.

## Acceptance Criteria

- [ ] `the_one/connectors/_routing.py` ships and exports `RoutingDecision`:
  - `@dataclass(frozen=True, slots=True)`.
  - Fields: `agent: str | None` (None on no-eligible), `rule_index: int | None` (the index into `config["routing"]["rules"]` if a rule matched; None for override / default / first-eligible / no-eligible), `scope: str | None` (the matched rule's scope, e.g. `"channel"`; `"override"` / `"default"` / `"first-eligible"` / `"no-eligible-agent"` for non-rule paths — single string for renderer uniformity), `match: str | None` (the matched rule's `match` value; None for non-rule paths), `reason: str` (one of `"rule-match"`, `"override"`, `"default"`, `"first-eligible"`, `"no-eligible-agent"`).
  - `__all__ = ["RoutingDecision", "resolve_routing"]`. Private to the connector subsystem; NOT re-exported from `__init__.py` (mirrors `_pairing.py` / `_acl.py` pattern).
- [ ] `resolve_routing(account, envelope, eligible_attached_agents, session_metadata) -> RoutingDecision` pure function with this contract:
  - Signature: `resolve_routing(account: ConnectorAccount, envelope: InboundEnvelope, eligible_attached_agents: list[AgentConfig], session_metadata: dict[str, Any] | None) -> RoutingDecision`. `eligible_attached_agents` is alphabetically ordered (caller's responsibility — L5 passes the output of `list_by_connector_account`).
  - Pure: no I/O, no repository calls, no clock reads. Reads only its arguments.
  - **Step 1 — Override**: if `session_metadata` is non-None and `session_metadata.get("routing_override")` is a non-empty string AND there exists an agent in `eligible_attached_agents` whose `.name == override` AND `admits_inbound(account, agent.connector_acls and agent.connector_acls.get(account.id), envelope.peer_id, envelope.channel_id)` returns `(True, ...)`, return `RoutingDecision(agent=<override>, rule_index=None, scope="override", match=None, reason="override")`. If the override points to an agent that's NOT in `eligible_attached_agents` OR is ACL-denied OR is the empty string, fall through to Step 2.
  - **Step 2 — Rule-walk**: iterate `account.config.get("routing", {}).get("rules", [])` in order with enumerated index. For each rule `{scope, match, agent}`:
    - Skip if the rule's scope doesn't match the envelope. Scope-to-envelope-field mapping: `"channel"` → `envelope.channel_id`; `"thread"` → `envelope.thread_id` (None envelope thread_id never matches any thread rule); `"dm"` → `envelope.thread_id is None AND envelope.peer_id == rule.match` (the "thread_id is None" condition is the plugin-agnostic proxy for "top-level conversation, not a thread"; F8/F9 plugins MAY narrow this later via a plugin hook); `"peer"` → `envelope.peer_id` regardless of channel.
    - Skip if the rule's `agent` name is NOT in `eligible_attached_agents`.
    - Skip if `admits_inbound(...)` denies for the rule's target agent.
    - First non-skipped rule wins: return `RoutingDecision(agent=<rule.agent>, rule_index=i, scope=<rule.scope>, match=<rule.match>, reason="rule-match")`.
    - **DM-rule scope-match detail**: the leg ships a simple, F3-consistent semantic for `dm` rules — `dm` matches when `envelope.thread_id is None` (i.e. a top-level conversation, not a thread). The rule's `match` is compared against `envelope.peer_id`. For the stub plugin this works because the stub doesn't distinguish DM vs guild — F8 / F9 plugins MAY narrow this later by exposing a `is_dm(envelope) -> bool` plugin method, but L4 ships a plugin-agnostic semantic. **`thread` rule scope-match**: matches when `envelope.thread_id is not None AND envelope.thread_id == rule.match`. **`channel` rule scope-match**: matches when `envelope.channel_id == rule.match` (regardless of thread_id — a thread message in a matched channel still matches the channel rule UNLESS an earlier thread rule won).
  - **Step 3 — Per-account default**: if `account.config.get("routing", {}).get("default")` is a non-empty string AND there exists an agent in `eligible_attached_agents` whose `.name == default` AND `admits_inbound(...)` permits, return `RoutingDecision(agent=<default>, rule_index=None, scope="default", match=None, reason="default")`. If the default is None / empty / not-in-eligible / ACL-denied, fall through to Step 4.
  - **Step 4 — First-eligible-alphabetical**: iterate `eligible_attached_agents` in input order (caller pre-sorted alphabetically). Return the first agent where `admits_inbound(...)` permits as `RoutingDecision(agent=<name>, rule_index=None, scope="first-eligible", match=None, reason="first-eligible")`.
  - **Step 5 — No-eligible**: if every agent in `eligible_attached_agents` is ACL-denied (or the list is empty), return `RoutingDecision(agent=None, rule_index=None, scope="no-eligible-agent", match=None, reason="no-eligible-agent")`. Used by L5 to emit the "No agents available for this conversation." peer-facing error via the system-outbound path.
- [ ] `tests/test_connectors_routing.py` (NEW) lands and passes. Test classes (style mirrors `tests/test_connectors_acl.py` — type-level surface tests + inline minimal fixtures):
  - `TestRoutingDecision` — dataclass surface: frozen, slotted, equality, hashability; field defaults.
  - `TestResolveRouting` — 5-step algorithm matrix:
    - `test_step1_override_with_eligible_agent_short_circuits` — override pointing to an eligible agent returns immediately.
    - `test_step1_override_to_ineligible_agent_falls_through_to_rule_walk` — override pointing to an agent not in `eligible_attached_agents` falls through; rule-walk's first match wins.
    - `test_step1_override_to_acl_denied_agent_falls_through` — override to an attached agent whose `agent_acl` denies → falls through.
    - `test_step1_override_empty_string_falls_through` — override is `""` → falls through.
    - `test_step1_session_metadata_none_falls_through` — `session_metadata=None` → no override consulted.
    - `test_step2_channel_rule_matches` — single channel rule, envelope's channel_id matches → rule wins; rule_index pinned.
    - `test_step2_thread_rule_matches` — single thread rule, envelope's thread_id matches → rule wins.
    - `test_step2_thread_rule_skipped_for_non_thread_envelope` — envelope.thread_id is None → thread rule skipped.
    - `test_step2_dm_rule_matches_top_level_conversation` — envelope.thread_id is None AND peer_id matches → dm rule wins.
    - `test_step2_dm_rule_skipped_for_thread_envelope` — envelope.thread_id is not None → dm rule skipped.
    - `test_step2_peer_rule_matches_regardless_of_channel` — peer_id matches regardless of channel_id / thread_id (parameterized across non-thread AND thread envelopes — pins "regardless of channel_id / thread_id" claim).
    - `test_step2_channel_rule_matches_thread_message_in_matched_channel` — `channel_id="C1"`, `thread_id="T1"`, rule `{scope:"channel", match:"C1"}` → channel rule wins; pins "a thread message inside a matched channel still matches a channel rule" docstring claim.
    - `test_step2_unknown_scope_rule_skipped` — construct an account with `config["routing"]["rules"] = [{"scope": "weird", ...}]` (bypass validator via direct `ConnectorAccount.model_construct` or hand-built dict); engine skips the unknown-scope rule; falls through to step 3/4. Pins the defensive `_scope_matches` unknown-scope branch.
    - `test_step2_first_match_wins_in_declared_order` — two channel rules both could match; the first declared wins; rule_index = 0.
    - `test_step2_rule_with_ineligible_agent_skipped` — rule's `agent` is not in eligible_attached_agents → rule skipped; next rule wins.
    - `test_step2_rule_with_acl_denied_agent_skipped` — rule's target agent is attached but ACL denies → rule skipped; next rule wins.
    - `test_step3_default_returns_when_no_rules_match` — `config["routing"]["default"] = "alice"`; alice is eligible + ACL permits → default wins.
    - `test_step3_default_ineligible_falls_through_to_first_eligible` — default points to an unattached agent → falls through.
    - `test_step3_default_acl_denied_falls_through` — default is attached but ACL denies → falls through.
    - `test_step3_default_none_falls_through` — `config["routing"]["default"] is None` → falls through.
    - `test_step4_first_eligible_alphabetical` — eligible list `[alpha, beta, charlie]`; all ACL-permit → alpha returned with reason "first-eligible".
    - `test_step4_skips_acl_denied_agents` — eligible list `[alpha, beta, charlie]`; alpha denied; beta permitted → beta returned.
    - `test_step5_no_eligible_when_all_denied` — eligible list `[alpha]`; ACL denies → `agent=None`, reason "no-eligible-agent".
    - `test_step5_no_eligible_when_list_empty` — eligible list `[]` → no-eligible.
    - `test_no_routing_config_falls_through_to_step4` — `account.config = {}` (no routing key) → bypass steps 2-3 → step 4 first-eligible-alphabetical.
    - `test_routing_rules_empty_list_falls_through_to_default` — `config["routing"] = {"rules": [], "default": "alice"}` → step 2 trivially yields nothing → step 3 default.
  - At least 23 tests covering the matrix above. Each uses inline `_account(...)` and `_envelope(...)` minimal fixtures.
- [ ] Pure-function discipline: no `import sqlite3`, no `import aiosqlite`, no `from the_one.db` repository imports inside `_routing.py`. Only `ConnectorAccount` (model type), `AgentConfig` (model type), `InboundEnvelope` (model type), and `admits_inbound` (pure function from `_acl.py`) imported. `grep -n "import\|from" the_one/connectors/_routing.py` should show ONLY type-only and pure-function imports.
- [ ] Module docstring cites M10 F7 L4; documents the 5-step algorithm; mirrors `_acl.py`'s tone; documents the DM-rule scope-match semantic explicitly so F8 / F9 plugin authors know what to expect when they extend routing rules.
- [ ] F1–F7 (post-L3) regression suite passes byte-identically PLUS the new routing tests:
  ```
  docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'
  ```
  Expected: prior 404 + ~27 new routing tests (24 in `TestResolveRouting` + 4-5 in `TestRoutingDecision`) = ~431+ passed.

## Verification Steps

How to confirm each criterion is met:

**Engine algorithm** (in `tests/test_connectors_routing.py`):

- Each of the 5 steps has at least one happy-path test + at least one fall-through test (override-falls-through-to-rule-walk; rule-walk-falls-through-to-default; default-falls-through-to-first-eligible; first-eligible-falls-through-to-no-eligible).
- Rule-walk tests cover all four scopes (`channel`, `thread`, `dm`, `peer`) + the scope-skip cases (thread rule against a non-thread envelope; dm rule against a thread envelope).
- First-match-wins is pinned by a test where two rules could both match and the FIRST declared wins.
- ACL-denied rule skipping is pinned.
- `RoutingDecision.rule_index` is pinned for rule-match cases (must equal the index in the operator-declared list).

**Dataclass surface** (in `TestRoutingDecision`):

- `RoutingDecision(agent="alice", rule_index=0, scope="channel", match="C1", reason="rule-match")` constructs; all fields equal the input.
- Frozen + slotted: mutation raises `FrozenInstanceError`.
- Equality + hashability: two equal RoutingDecisions are `==`; can be used in a set.
- `RoutingDecision.__module__ == "the_one.connectors._routing"` — canonical-import identity pin.

**Pure-function discipline**:

- `grep -n "^import\|^from" the_one/connectors/_routing.py` shows only type-only imports + `admits_inbound` from `_acl.py`.
- No `await` in the function body — `resolve_routing` is a synchronous pure function.

**Regression**:

- `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'` — full suite green; new tests bring the count to ~427.

## Implementation Guidance

### 1. New module `the_one/connectors/_routing.py`

```python
"""Multi-agent routing resolution engine — pure function.

M10 F07 L4: walks the routing rules on a connector account's
``config["routing"]`` and picks an attached agent for an inbound
envelope. The 5-step algorithm (override → rule-walk → default →
first-eligible-alphabetical → no-eligible) is the dispatcher's
single source of truth for "given this inbound, which agent handles
it?"

Pure — no I/O. The caller (F7 L5 dispatcher) is responsible for:
- resolving ``eligible_attached_agents`` via
  :meth:`SQLiteAgentStore.list_by_connector_account` (F7 L3),
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

- ``channel`` — matches when ``envelope.channel_id == rule.match``,
  regardless of thread_id. A thread message inside a matched channel
  still matches a channel rule UNLESS an earlier thread rule wins.
- ``thread`` — matches when ``envelope.thread_id is not None AND
  envelope.thread_id == rule.match``. Top-level (non-thread)
  envelopes never match a thread rule.
- ``dm`` — matches when ``envelope.thread_id is None AND
  envelope.peer_id == rule.match``. The "no thread" condition is the
  closest plugin-agnostic proxy for "this is a DM, not a guild
  channel." F8 / F9 plugins that distinguish DMs more precisely can
  refine this in their plugin layer.
- ``peer`` — matches when ``envelope.peer_id == rule.match``,
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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from the_one.agent.config import AgentConfig
from the_one.connectors._acl import admits_inbound
from the_one.connectors.base import InboundEnvelope
from the_one.db.models import ConnectorAccount


__all__ = ["RoutingDecision", "resolve_routing"]


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """The output of :func:`resolve_routing`.

    Carries the picked agent (or ``None`` on no-eligible) plus the
    metadata F7 L5's audit-log writer needs (which step picked it,
    which rule index matched, the matched scope and match string).

    **Scope-uniformity invariant** — ``scope`` is ALWAYS a non-empty
    string for every path (``"channel"`` / ``"thread"`` / ``"dm"`` /
    ``"peer"`` for rule-walk; ``"override"`` / ``"default"`` /
    ``"first-eligible"`` / ``"no-eligible-agent"`` for non-rule
    paths). This lets F7 L5's audit-log renderer write
    ``f"reason={d.reason}, scope={d.scope}"`` without a None branch.
    Do NOT "simplify" this back to ``scope=None`` for non-rule paths
    — the renderer relies on the uniformity.
    """

    agent: str | None
    rule_index: int | None
    scope: str | None
    match: str | None
    reason: str


def _agent_admits(
    account: ConnectorAccount,
    agent_config: AgentConfig,
    envelope: InboundEnvelope,
) -> bool:
    """ACL admission helper — wraps :func:`admits_inbound` for the
    agent's per-account ACL.

    Per L2 docstring: per-agent ACL inner dict is keyed by
    ``account.id`` in :attr:`AgentConfig.connector_acls`.
    """
    agent_acl: dict[str, list[str] | None] | None = None
    if agent_config.connector_acls is not None:
        agent_acl = agent_config.connector_acls.get(account.id)
    admits, _reason = admits_inbound(
        account, agent_acl, envelope.peer_id, envelope.channel_id
    )
    return admits


def _scope_matches(
    rule_scope: str,
    rule_match: str,
    envelope: InboundEnvelope,
) -> bool:
    """Check whether a rule's scope matches the envelope.

    See module docstring for the per-scope semantics.
    """
    if rule_scope == "channel":
        return envelope.channel_id == rule_match
    if rule_scope == "thread":
        return (
            envelope.thread_id is not None
            and envelope.thread_id == rule_match
        )
    if rule_scope == "dm":
        return (
            envelope.thread_id is None
            and envelope.peer_id == rule_match
        )
    if rule_scope == "peer":
        return envelope.peer_id == rule_match
    return False  # unknown scope — defensive; validator should reject


def resolve_routing(
    account: ConnectorAccount,
    envelope: InboundEnvelope,
    eligible_attached_agents: list[AgentConfig],
    session_metadata: dict[str, Any] | None,
) -> RoutingDecision:
    """Pick an attached agent for ``envelope`` per the 5-step algorithm.

    See module docstring for the algorithm and scope-match semantics.

    **Precondition** — ``eligible_attached_agents`` MUST be alphabetically
    ordered by ``name``. Pass the output of
    :meth:`SQLiteAgentStore.list_by_connector_account` unmodified (F7 L3
    landed that helper with the ``ORDER BY name`` already enforced).
    Step 4 returns the FIRST element by input order whose ACL admits —
    passing a non-alphabetized list breaks the
    first-eligible-alphabetical semantic the dispatcher's audit log
    promises.
    """
    agents_by_name: dict[str, AgentConfig] = {
        a.name: a for a in eligible_attached_agents
    }

    # Step 1 — Override.
    override = (session_metadata or {}).get("routing_override")
    if isinstance(override, str) and override:
        candidate = agents_by_name.get(override)
        if candidate is not None and _agent_admits(account, candidate, envelope):
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
        if not _scope_matches(rule["scope"], rule["match"], envelope):
            continue
        candidate = agents_by_name.get(rule["agent"])
        if candidate is None:
            continue
        if not _agent_admits(account, candidate, envelope):
            continue
        return RoutingDecision(
            agent=rule["agent"],
            rule_index=i,
            scope=rule["scope"],
            match=rule["match"],
            reason="rule-match",
        )

    # Step 3 — Per-account default.
    default = routing.get("default")
    if isinstance(default, str) and default:
        candidate = agents_by_name.get(default)
        if candidate is not None and _agent_admits(account, candidate, envelope):
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
        if _agent_admits(account, agent_config, envelope):
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
```

### 2. New test file `tests/test_connectors_routing.py`

Mirror `tests/test_connectors_acl.py`'s style. Inline minimal fixtures:

```python
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

from the_one.agent.config import AgentConfig
from the_one.connectors._routing import RoutingDecision, resolve_routing
from the_one.connectors.base import InboundEnvelope
from the_one.db.models import ConnectorAccount


def _account(
    *,
    account_id: str = "acct-test",
    allowlist: dict | None = None,
    routing: dict | None = None,
) -> ConnectorAccount:
    """Build a minimal ConnectorAccount."""
    config: dict = {}
    if allowlist is not None:
        config["allowlist"] = allowlist
    if routing is not None:
        config["routing"] = routing
    return ConnectorAccount(
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
    connector_account_ids: list[str] | None = None,
    connector_acls: dict | None = None,
) -> AgentConfig:
    return AgentConfig(
        name=name,
        provider_config_id="mock-provider",
        llm_model="mock",
        connector_account_ids=connector_account_ids or ["acct-test"],
        connector_acls=connector_acls,
    )


# ... test classes follow ...
```

Then `TestRoutingDecision` (4-5 tests) and `TestResolveRouting` (23+ tests per Acceptance Criteria).

### 3. Order of file edits

1. `the_one/connectors/_routing.py` (new) — define `RoutingDecision`, `_scope_matches`, `_agent_admits`, `resolve_routing`.
2. `tests/test_connectors_routing.py` (new) — pin behavior.
3. Run: `docker exec the-one pytest tests/test_connectors_routing.py -x --timeout 30 -v`.
4. Full regression: `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'`.

### 4. Things NOT in scope for this leg

- Dispatcher integration (L5).
- Command parsing in the dispatcher (L1 parsing landed; L5 wires).
- `set_session_metadata_key` primitive (L5).
- Command handlers (L6).
- Studio Routing Rules editor (L7).
- agents.md routing-convention documentation (deferred to L5 or L7; L4 is type-level surface only).

## Edge Cases

- **Empty `eligible_attached_agents` list**: step 4 trivially yields no eligible; step 5 returns `agent=None`.
- **`session_metadata` is `None`** (no chat session yet, or caller passes None explicitly): step 1 skipped via `(session_metadata or {})`. Falls through to step 2.
- **`session_metadata["routing_override"]` is non-string** (e.g. `42` from a malformed write): `isinstance(override, str)` guard skips step 1.
- **`account.config["routing"]` missing OR `None`** (operator explicitly cleared the routing config, or never wrote one): `account.config.get("routing") or {}` collapses to `{}`; rule-walk yields nothing; default lookup yields nothing; falls through to Step 4. The L2 validator REJECTS `rules=None` post-write, so `routing.get("rules") or []` is defensive against an impossible (but harmless) state — a future reader should not infer that `rules=None` is a real persistable shape.
- **`account.config["routing"]["default"]` is `None` OR empty string**: step 3 falls through to step 4.
- **Rule with scope `"dm"` and envelope has `thread_id="t1"`**: `_scope_matches` returns False; rule skipped.
- **Rule with scope `"thread"` and envelope has `thread_id=None`**: `_scope_matches` returns False; rule skipped.
- **Rule references an agent that's not in `eligible_attached_agents`**: rule is skipped via the `agents_by_name.get(...)` lookup returning `None`. The audit log (L5) will NOT see this rule's index — the next eligible rule wins. (If the operator authored a rule pointing to a since-removed agent, the routing silently routes elsewhere; L5's audit shows the next rule's index. This is the correct UX — F7 does not warn about stale rule references at routing time; Studio editor in L7 SHOULD warn at edit time.)
- **All rules skipped + default ineligible + no first-eligible**: step 5 returns no-eligible. L5's dispatcher emits the peer-facing "No agents available" error via the system-outbound path AND audit-logs the no-eligible decision.
- **Unknown scope** in a rule (shouldn't happen post-L2 validator, but defensive): `_scope_matches` returns False; rule skipped.

## Files Affected

- `the_one/connectors/_routing.py` (NEW) — `RoutingDecision` dataclass + `resolve_routing` pure function + `_agent_admits` / `_scope_matches` private helpers.
- `tests/test_connectors_routing.py` (NEW) — pin 5-step algorithm + scope-match semantics + dataclass surface.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

## Citation Audit

Citations verified against current code at leg design time:

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/connectors/_acl.py:admits_inbound` | OK | Landed in L2; signature `(account, agent_acl, peer_id, channel_id) -> tuple[bool, str]` verified |
| `the_one/connectors/base.py:InboundEnvelope` | OK | Frozen dataclass with platform/account_id/channel_id/thread_id/peer_id/peer_name/text/raw fields |
| `the_one/db/models.py:ConnectorAccount.config` | OK | Carries `routing` reserved key (L2 validator) |
| `the_one/agent/config.py:AgentConfig` | OK | `.name`, `.connector_account_ids`, `.connector_acls` fields all present |
| `the_one/db/repositories.py:SQLiteAgentStore.list_by_connector_account` | OK | Landed in L3; caller (L5 dispatcher) uses output as `eligible_attached_agents` |
| `tests/test_connectors_acl.py` (test-style mirror) | OK | Pattern confirmed: inline minimal fixtures + per-class organization |

6 in-leg-artifact code-location citations verified against current code at leg design time.
