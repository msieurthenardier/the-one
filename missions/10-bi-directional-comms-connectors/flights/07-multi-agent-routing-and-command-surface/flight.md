# Flight: Multi-Agent Routing and the Platform-Side Command Surface

**Status**: landed
**Mission**: [Bi-directional Communication Connectors](../../mission.md)

## Contributing to Criteria

- [ ] Mission #6 — A connector account can be attached to any number of agents; inbound routes to exactly one of the attached agents per operator-configured routing rules (F6 landed attachment + per-agent ACL; F7 lands the routing layer)
- [ ] Mission #20 — Each connector-attached session's routing decision is logged in session metadata so the operator can see why each session went to which agent
- [ ] Mission #21 — A platform-side command surface lets peers invoke a small well-defined set of commands (list, switch, identify, new session, help); commands gated by per-(agent, peer) and per-(agent, channel) permissions composing with the connector-account-level allowlist
- [ ] Mission #22 — The command surface is a connector-agnostic primitive — adding a new connector inherits the full command set without re-implementing the parser, the permission checks, or the help text
- [ ] Mission #28 — Studio surfaces meet the M04/M06 design-language quality bar (F7 adds the Routing Rules editor on the connector account)
- [ ] Mission #29 — Each layer has automated coverage (F7 adds: routing-rule resolution, command parsing + execution, command-permission gating, audit-log routing entries)

---

## Pre-Flight

### Objective

Layer multi-agent routing and the platform-side command surface on the F6 gating substrate. When N agents attach to one connector account, an inbound message resolves to exactly one of them via three composing layers: (i) operator-configured **default routing rules** stored on the connector account (per-channel, per-thread, per-DM, per-(account, peer), and a per-account default agent); (ii) **peer-issued command override** via `/talk-to <agent>`; (iii) the **per-agent ACL gating** F6 established (a route to an agent the peer is not permitted to invoke is invalid and falls back). Commands are a connector-agnostic primitive — six commands ship in v1 (`/agents /talk-to /whoami /new /reset /help`); a text-prefix parser is the v1 mechanism; an additive `CommandHandler` Protocol is the future extension point for platform-native slash-command registration (F8 Discord, F9 Slack). Commands are dispatched system-side: a command-only inbound short-circuits agent.step, emits its response via the plugin's outbound adapter directly, and is independent of the platform-send tool's operator-disable state. Routing decisions write to `chat_sessions.session_metadata["routing"]` via the F6 `append_to_session_metadata` primitive — no schema migration. The dispatcher's F6 single-agent assumption (caller passes `agent_name` to `dispatch_inbound`) is substituted in this flight: routing decides which agent. As a parallel scope item, fold the F6 carry-forward backlog into a single leg (pairing-prefix unit tests + F8 marker source-code comment). No agent-loop changes.

### Open Questions

- [x] **Routing-rule schema and storage** → see Design Decisions ("Account-config persistence with ordered rule list")
- [x] **Routing-rule precedence** → see Design Decisions ("Specificity-then-order precedence")
- [x] **Command vocabulary v1** → see Design Decisions ("Six commands, two as aliases")
- [x] **Command intercept ordering relative to F6 gates** → see Design Decisions ("Post-resolver, post-routing, post-ACL, pre-command-parse, pre-lock")
- [x] **Command outbound path** → see Design Decisions ("System outbound via pool_acquire + client.send")
- [x] **CommandHandler Protocol shape** → see Design Decisions ("Single-method `CommandHandler` Protocol")
- [x] **Dispatcher signature change + cascade strategy** → see Design Decisions ("Drop `agent_name` param; mechanical rename leg lands first")
- [x] **Unreachable-agent UX + fallback ordering** → see Design Decisions ("Silent fallback through alphabetically-ordered eligible-attached-agent list")
- [x] **Routing audit key + key-name uniformity** → see Design Decisions ("`session_metadata['routing']` — F6 key-name uniformity")
- [x] **Studio surfaces** → see Design Decisions ("Connector account Routing Rules editor only — no Agent Editor work")
- [x] **HAT closer** → see Design Decisions ("Optional lightweight HAT — single-surface scope")
- [x] **ACL admission as pure function** → see Design Decisions / Technical Approach L2 ("Pre-commit to extracting `connectors/_acl.py`")
- [x] **`set_session_metadata_key` vs overload `append_to_session_metadata`** → see Design Decisions ("Sibling primitive")
- [x] **Inverse-query mechanism for attached agents** → see Design Decisions ("`AgentConfigRepository.list_by_connector_account`")
- [ ] **Default-routing-rule shape detail: thread separate from channel?** — Defer to leg 2 design. F3 session-key normalization decides whether threads share the parent channel session or split. Routing-rule shape mirrors that decision so a thread-scoped rule is meaningful iff sessions split on thread. L2 design consults `connectors/_session.py` (or wherever the F3 normalization lives) before settling the scope enum.
- [ ] **`/new` vs `/reset` semantic — alias or distinct?** — Default per Design Decisions: `/new` is canonical (start fresh `chat_sessions` row via `session_metadata["ended_at"]` write + F3 `resolve_session` touch), `/reset` is alias. Confirm at HAT or revisit in M10 mission debrief if operator wants distinct semantics (e.g. `/reset` clears agent context without starting a new session — would require an agent-loop touch and is out of scope).

### Design Decisions

**Account-config persistence with ordered rule list**: Routing rules ride on the existing `connector_accounts.config: dict[str, Any]` column under a new reserved key `config["routing"]`. Schema:

```python
config["routing"] = {
    "rules": [
        {"scope": "channel", "match": "<channel_id>", "agent": "<slug>"},
        {"scope": "thread",  "match": "<thread_id>",  "agent": "<slug>"},
        {"scope": "dm",      "match": "<peer_id>",    "agent": "<slug>"},
        {"scope": "peer",    "match": "<peer_id>",    "agent": "<slug>"},
        # ... in operator-declared order ...
    ],
    "default": "<slug>" | None,  # account-level fallback; null = use first-eligible-attached
}
```

- Rationale: Mirrors F6's `config["allowlist"]` / `config["pairing"]` reserved-key pattern; no schema migration; Pydantic validator extends F6's `_validate_config_reserved_keys` to recognize `"routing"`. The ordered list is the operator-authored precedence — the dispatcher walks it in order, returning the first match.
- Trade-off: Operator-controlled ordering is more flexible than a fixed scope-precedence ladder but slightly easier to misconfigure. Mitigation: Studio editor surfaces the order explicitly and the dispatcher's audit-log entry records which rule index matched.

**Specificity-then-order precedence**: When the operator authors rules, the Studio editor stores them in the order the operator declared. The dispatcher walks the list top-to-bottom and the first match wins. Recommended (but not enforced) ordering: `thread` > `channel` > `dm` > `peer`. The `config["routing"]["default"]` is the per-account fallback. If no rule matches AND no default is set, fall back to the first-eligible-attached-agent (the first agent in `connector_account.attached_agents` ordering whose per-agent ACL admits this peer).
- Rationale: Operator-authored order is the simplest mental model; doesn't bake precedence opinions into code. Studio editor surfaces a "Move up / Move down" affordance so order is visible and editable.
- Trade-off: An operator who doesn't understand "first match wins" can produce rules whose later-listed entries are never consulted. Mitigation: Studio editor previews the resolution against a sample envelope (deferred to L6 scope decision); the dispatcher's audit-log entry pins the matched rule index for debugging.

**Six commands, two as aliases**: v1 ships `/agents`, `/talk-to <slug>`, `/whoami`, `/new`, `/reset`, `/help`.
- `/agents` — list agents the peer is permitted to invoke on this account (filtered by per-agent ACL + account-scope allowlist).
- `/talk-to <slug>` — switch the active routing for this conversation to the named agent within the peer's permissions. Succeeds → confirmation message; fails (ACL denies, unknown slug) → explicit error to the peer.
- `/whoami` — respond with the currently active agent for this conversation.
- `/new` — start a new `chat_sessions` row for this conversation key (the existing key continues to resolve, but the OLD session's `last_inbound_at` is no longer the bind target — the next inbound creates a fresh session via the F3 lifecycle path).
- `/reset` — alias for `/new`. Same behavior.
- `/help` — list available commands with one-line descriptions, filtered for the peer's permissions.

Rationale: Mission Open Question 3 proposes this exact minimum. Aliasing `/reset → /new` avoids semantic ambiguity (operator question whether `/reset` should "clear agent memory in-session" — that's an agent-loop concern, out of M10 scope).

**Post-resolver, post-routing, post-ACL, pre-command-parse, pre-lock intercept ordering**: At `connectors/_inbound.py`, the dispatcher composition becomes:

1. Pool acquire → account load → plugin resolve (existing F1-F2)
2. `resolve_session` (existing F3) — materializes `chat_sessions` row
3. **Resolver consult (F6)** — `getattr(plugin, "resolve", _default_permit)`; three-arm branch
4. **Routing rules consult (F7, NEW)** — `resolve_routing(account, envelope, eligible_attached_agents, session_metadata)` → returns picked agent name + matched-rule index + scope + match + reason. Routing happens BEFORE command parse so commands without an agent target (`/agents`, `/help`) still have a routed agent identity for system-outbound pool acquisition.
5. **Per-agent ACL inbound check (F7, NEW)** — verify the picked agent's `connector_acls[account_id]` admits this (peer, channel); if denied, fall back through eligible-attached-agent list per the unreachable-agent UX
6. **Audit-log the routing decision** — `append_to_session_metadata(session_id, "routing", {...})`
7. **Command parse + intercept (F7, NEW)** — `_parse_command(envelope.text)` → if recognized, dispatch to command handler (handler has access to the routed agent identity from step 4); emit response via the system-outbound path (see "System outbound via pool_acquire + client.send" below); short-circuit (NO agent.step, NO per-session lock).
8. Per-session lock (existing F3) → agent build → `agent.step` (existing F4) — only reached if step 7 did not intercept.

Rationale: Routing runs before command parse so every command response has a defined system-outbound identity (the routed agent's pool client). Commands that DO operate on routing semantics (`/talk-to`, `/whoami`) consult the routing decision from step 4 directly. Per-agent ACL gating happens AFTER routing picks because routing might pick an agent the peer can't invoke — F6 ACL is the final gate, and a denied routing decision falls back through the eligible-attached-agent list.

**System outbound via pool_acquire + client.send (commands bypass platform-send tool, share the pool path)**: Command responses emit through the same `pool_acquire(agent_name, account_id) → client.send(target, content)` path the platform-send tool uses (`tools/connector_send.py:219-227`), but invoked dispatcher-internally rather than via the tool registry. The `agent_name` keying the pool acquire is the **routed agent name** from the routing-engine decision in step 4 — so pool warmth stays consistent with the inbound dispatch path (the routed agent already has a pool entry from F1's per-(agent, account) lifecycle). The tool registry, the resolver re-consultation, and the platform-send-tool-disabled gate are all bypassed.
- Rationale: Commands must work even when the operator has disabled the platform-send tool (Mission #14 dual-state). They are operator-facing UX, not agent-generated content. Sharing the `pool_acquire → client.send` path with the platform-send tool keeps the connection-lifecycle invariant (one pool entry per (agent, account)) intact; using the routed agent's pool identity is what `send_to_platform_channel` already does in F4. The audit trail records command emissions distinctly via `session_metadata["routing"]` entries with `reason: "command-response"` so the operator can tell them apart from agent-emitted platform messages.
- Trade-off: Adds a dispatcher-internal call site to the pool path. Mitigation: the path is narrow (dispatcher → `pool_acquire` → `client.send`, no tool registry, no resolver re-consultation, no per-call account fetch — the account is already in scope), and L4's tests pin the contract against the stub plugin's outbound client.

**Single-method `CommandHandler` Protocol via structural satisfaction (additive, optional)**: `connectors/base.py` gains a single-method `CommandHandler` Protocol: `async def handle_command(envelope, command_name, args) -> CommandResponse | None`. v1 commands are NOT routed through it — the dispatcher's built-in text-prefix parser handles all six against the stub plugin. The Protocol is the **additive** extension point for plugins that want to register platform-native commands (Discord slash commands via Interactions API, Slack slash commands via app manifest). A plugin that returns `None` from `handle_command` falls through to the built-in handler. F8 Discord plugin will implement the Protocol to register slash commands; the built-in text-prefix path remains the fallback.
- Rationale: Mission Open Question 6 explicitly defers per-platform slash-command registration to additive enhancements. A single-method optional Protocol is the right shape because there is exactly one current consumer pattern (route an inbound command through to the plugin's platform-native handler). The `list_commands` method the original draft predicted is speculative — F8's Discord plugin will reveal whether it's actually needed (e.g. for slash-command registration manifests) and is the right place to add it. Closes the F1 forward-reference at 5 docstring sites.
- Trade-off: Two outbound paths per connector (built-in text-prefix + plugin-native slash). Mitigation: both terminate at the same dispatcher command-handler functions; only the discovery/parse phase differs.
- Pattern choice (Protocol-widening vs optional-hook-via-getattr-sentinel): with one method, the two patterns are equivalent in cost. Picking explicit Protocol declaration here because `handle_command` has a non-trivial signature (`InboundEnvelope` + parsed args + return ADT) that benefits from a single point of documentation in `base.py`. The F6 `resolve` precedent (getattr sentinel) remains the right call for single-method hooks with simpler signatures.

**Drop `agent_name` from `dispatch_inbound` signature — mechanical rename leg lands first**: `connectors/_inbound.dispatch_inbound(agent_name: str, account: ConnectorAccount, envelope: InboundEnvelope, ...)` becomes `dispatch_inbound(account: ConnectorAccount, envelope: InboundEnvelope, ...)`. Routing decides which agent. The single-agent assumption F6 left in place (caller passes the agent name) is the explicit hand-off point — F7 closes it.
- Rationale: F6 debrief named the hand-off; F7 owns the substitution. The dispatcher's contract becomes "given an account and an envelope, dispatch correctly" — the caller (the plugin's inbound adapter) doesn't need to know agent topology.
- Trade-off: ~56 test-fixture call sites cascade (verified: `grep -rn "dispatch_inbound\s*(" tests/`). This is an order of magnitude past the original "if cascade > ~5 fixtures, split" threshold. Mitigation: pre-commit to splitting the integration into TWO legs — **L3 (mechanical rename)**: introduces the new `dispatch_inbound(account, envelope, ...)` signature; internally derives the target agent via a transitional helper `_resolve_single_attached_agent_or_first_alphabetical(account)` (the F6 "first-attached or only-attached" assumption made explicit and named). Call sites mechanically migrate to the new signature. **L5 (integration)**: routing engine + command intercept replace the transitional helper; the helper is removed.
- **Fixture-audit step in L3 design** (NOT optional): Before the leg ships, audit all ~56 call sites and partition into three buckets — (a) single-attached-agent fixtures where the helper's alphabetical-first picks the same agent the test passed (helper is byte-correct); (b) multi-attached-agent fixtures where the test-passed agent happens to BE the alphabetical-first (helper is byte-correct); (c) multi-attached-agent fixtures where the test-passed agent is NOT the alphabetical-first (helper changes behavior — these fixtures must be migrated to either set `session_metadata["routing_override"] = <test-passed agent>` or reduce the account fixture to single-attached). The L3 spec records the count per bucket; if bucket (c) > 0, the leg also performs the bucket-(c) fixture migration before the rename can claim byte-identical regression.

**Silent fallback through alphabetically-ordered eligible-attached-agent list**: When `resolve_routing` picks an agent that fails the per-agent ACL inbound check (the peer is not permitted, OR the agent is no longer attached, OR the agent slug doesn't exist), the dispatcher falls back to the next agent in the **alphabetically-ordered list of attached agents** whose ACL admits this peer. The fallback is audit-logged with the original failed pick (rule_index, scope, match, reason). If no eligible agent exists, the dispatcher emits an explicit error to the peer via the system-outbound path: `"No agents available for this conversation."` and short-circuits agent.step.
- Inverse-query mechanism: F7 enumerates attached agents by scanning agents whose `AgentConfig.connector_account_ids` contains the account id. L3 design picks between (a) adding `AgentConfigRepository.list_by_connector_account(account_id)` helper (lifts the iteration to the repository layer; one method, one test), or (b) scan-all + filter in `_routing.py` (no repository change; fewer cross-layer dependencies). Default per spec: (a) — adding a repository helper keeps the routing engine pure and gives F8/F9 a clean reuse path.
- Rationale: There is no inherent ordering on the inverse relationship `AgentConfig.connector_account_ids → account`. Alphabetical-by-agent-slug is deterministic, operator-inspectable, and stable across restarts. Silent fallback matches "peers expect a response" UX; explicit error on zero-eligible matches "make the dead-end visible" UX. Audit-log preserves the operator's ability to debug "why did this conversation get agent X instead of Y."
- Trade-off: Alphabetical ordering is not operator-controllable; an operator wanting "agent X first" must rely on default-routing rules + `/talk-to`. Acceptable for F7 — fallback ordering is a tie-breaker, not a primary UX surface. Studio Chat session inspector (out of F7 scope; future work) can surface the audit-log.

**Peer-issued routing override via session-scoped persistence + sibling primitive `set_session_metadata_key`**: When a peer issues `/talk-to <slug>`, the override persists for the duration of the `chat_sessions` row. The implementation: write `session_metadata["routing_override"] = "<slug>"` at the time of command execution; `resolve_routing` reads this key first and short-circuits the rule-walk if present. A subsequent `/talk-to <other>` overwrites it; `/new` (which starts a new session) discards it implicitly via the new session having empty `session_metadata`.
- A new sibling narrow primitive `ChatSessionRepository.set_session_metadata_key(session_id, key, value)` lands in L5. F6's `append_to_session_metadata` was designed for append semantics (the audit-log list); `routing_override` is a single-value set (last-writer-wins). Overloading the append primitive with a `value_kind: Literal["list-append", "set"]` parameter or magic key names would be worse than a sibling — both primitives stay narrow and composable.
- **Concurrency posture (last-writer-wins, by design)**: Two concurrent `/talk-to` inbounds for the same session land in non-deterministic order; the last writer's intent wins silently. This is the **correct** semantic for an override ("most recent operator/peer intent wins") and is documented at the primitive's call site. F6's audit append has a different posture (preserve both entries on race); the two primitives differ deliberately. The race-on-concurrent-pairing F6 debrief flagged on `config.allowlist.peers` is a separate primitive (account-config UPDATE) and a separate concurrency concern.
- Rationale: A peer who explicitly says "talk to X" expects subsequent messages to go to X until they explicitly switch again. Session-scoped persistence matches the "this conversation" mental model.
- Trade-off: `session_metadata` now has THREE write sites (F6 `audit` list-append, F7 `routing` list-append, F7 `routing_override` set). Two primitives, two semantics — clear separation.

**Routing audit key — `session_metadata["routing"]`, list-append semantics, F6 key-name uniformity, disposition field**: Each routing decision (initial route, fallback, command-driven switch, command response) appends one entry to `session_metadata["routing"]`. Entry shape: `{"ts": iso, "agent": slug, "rule_index": int | None, "scope": "channel|thread|dm|peer|default|override|fallback", "match": str | null, "reason": "rule-match" | "default" | "override" | "fallback-ACL-deny" | "command-response" | ..., "disposition": "stepped" | "command-intercepted" | "no-eligible"}`. Sibling to F6's `session_metadata["audit"]`; key names (`ts`, `reason`) mirror F6's entry shape for renderer uniformity (F6's audit entries use `ts` per `_inbound.py:253-256`).
- The `disposition` field is written AFTER the command-parse step (step 7 in the composition order) so the audit log distinguishes (i) "routed-and-stepped" — the picked agent actually ran agent.step; (ii) "command-intercepted" — the picked agent's pool identity was used for the system-outbound but agent.step did NOT run; (iii) "no-eligible" — no agent was picked, error emitted to peer. Without this, an operator reading the audit log would see "routed to alice" for a `/talk-to bob` inbound and incorrectly conclude alice ran the step.
- Rationale: F6's `append_to_session_metadata` is the canonical writer; routing uses a different top-level key but the same primitive. No schema migration.
- Trade-off: Routing list grows linearly with conversation length. Acceptable — `session_metadata` is operator-debugging data, not hot-path data. F10 hardening can compact if growth becomes pathological. Note that a `/talk-to` inbound writes TWO entries (one for the routing decision with `disposition: command-intercepted`, one for the override write with `reason: override-set`) — operator-debug surface should expect paired entries.

**Studio surfaces — connector account Routing Rules editor only, no Agent Editor work**: F7 adds ONE new section to the Studio Connectors detail page: a "Routing Rules" editor that lets the operator author the ordered rule list and the per-account default. The Agent Editor Connectors tab (F6) gains NO new UI — routing rules live on the account, not the agent. The Studio editor mirrors the F6 chip-list + attached-agents idiom; rules are rendered as table rows with scope/match/agent columns and Move-up/Move-down actions.
- Rationale: Routing rules are account-scoped (an account's rules apply to all attached agents). Per-agent ACL is the only agent-scoped routing concern, and F6 already ships it.
- Trade-off: The operator glances at the connector account to see routing; the agent editor doesn't show "where does inbound to this agent come from." Mitigation: the F6 attached-agents table on the connector account already lists "which agents this account routes to" (the inverse view).

**Optional lightweight HAT — single-surface scope**: F7 adds one Studio surface (Routing Rules editor). The other F7 deliverables (command parsing, routing engine, dispatcher integration) are exercised via unit tests against the stub plugin; they cannot be end-to-end HAT'd because the stub is `register_for_test`-only (per F6 debrief K3). HAT scope: the Routing Rules editor (design-language audit + flow-end CRUD) and visual confirmation of audit-log entries in `session_metadata` (operator can inspect via Studio's existing session-detail view if there is one; otherwise read the DB).
- Rationale: F6 HAT surfaced 18+ design-language defects on three Studio surfaces; F7's one new surface should be ~3-5 iterations max. Skip HAT entirely would leave a Studio surface unvalidated against operator UX.
- Trade-off: Adds 1-2 hours of operator wall-clock time. Acceptable.

**F6 carry-forward bundle as a single leg**: F6 debrief flagged two small follow-ups that share the F7 surface (the dispatcher + the connector-send tool): (i) add `tests/test_pairing_prefix.py` with ~6 whitespace/case-sensitivity cases (`_pairing.py` is adjacent to `_commands.py`, which F7 introduces); (ii) add `# F8: DM-classification consult lands here` source-code marker at `tools/connector_send.py:202`. Both are sub-1-hour edits; bundling them into a single leg follows the flight skill's "bundle small items that share the same surface area" guidance. The connector-account-editor.js Enable-toggle scan stays in `/routine-maintenance` scope (different file, different surface).
- Rationale: Closes two F6 action items without scattering tiny commits.
- Trade-off: A small risk that bundling delays one of them if the other slips. Mitigation: leg is small enough to ship in one cycle.

### Prerequisites

- [ ] F6 landed and merged to main (verified: commit `b38f60f flight/06: debrief + close`)
- [ ] `connector_accounts.config` column + `_validate_config_reserved_keys` validator exist (F6 L1b — verified at `db/models.py`)
- [ ] `AgentConfig.connector_acls` + v18 migration + `connector_account_ids` persistence (F4 L5 + F6 L1c — verified at `agent/config.py:184`, `db/repositories.py`)
- [ ] `chat_sessions.session_metadata` TEXT column exists (F3 — verified at `db/schema.py:610`)
- [ ] `ChatSessionRepository.append_to_session_metadata` narrow primitive (F6 L2 — verified at `db/repositories.py:846-885`)
- [ ] `connectors/_inbound.dispatch_inbound` composition site (F6 — verified at `_inbound.py:78`; routing + command intercept insert post-resolve-session, pre-resolver-consult)
- [ ] `connectors/_pairing._validate_pairing_prefix` is the prior art for text-prefix parsing (F6 L2 — verified at `_pairing.py:18-41`)
- [ ] Stub plugin exists for end-to-end test fixture (`the_one/connectors/_stub.py` — F1)
- [ ] CommandHandler forward-references at 5 sites (F1 — verified, all five docstring locations identified for reframing in L1)
- [ ] Per-agent ACL inbound enforcement not yet wired (F6 wired outbound only — F7 L4 wires inbound; the per-agent ACL data structure is already persisted)
- [ ] No prior routing or command parsing scaffolding in the codebase (grep verified zero hits beyond docstring forward-refs)
- [ ] Project's optional-Protocol-via-structural-satisfaction convention is codified in agents.md (verified — F6 documents `optional-plugin-hook-via-getattr-sentinel` and F1 documents `protocol-widening-for-required-capability`; F7's CommandHandler choice picks Protocol-widening since it has multiple methods)

### Pre-Flight Checklist

- [ ] All open questions resolved (2 deferred to per-leg design: thread-vs-channel rule scope shape; `/new` vs `/reset` semantic confirmation at HAT)
- [ ] Design decisions documented (13 decisions)
- [ ] Prerequisites verified against current code
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach

F7 is **command-surface scaffolding first, routing primitives second, mechanical dispatcher rename third, routing engine fourth, dispatcher integration fifth, command implementations sixth, Studio seventh, F6 carry-forward eighth, HAT last**:

1. **CommandHandler Protocol + text-prefix command parser + stub-plugin handler** (leg 1). Declare single-method `CommandHandler` Protocol in `connectors/base.py` (`async def handle_command(envelope, command_name, args) -> CommandResponse | None`); close the 5 F1 forward-reference sites by replacing prediction-language with citation-language. New module `connectors/_commands.py` exporting `_parse_command(text: str) -> tuple[str, list[str], str] | None` — mirrors `_pairing._validate_pairing_prefix` shape. Stub plugin does NOT implement `CommandHandler` (preserves F1-F6 byte-identical regression); the dispatcher's built-in path handles all six v1 commands against the stub.

2. **Routing rules schema + ACL pure-function extraction** (leg 2). Two scope items in the same leg because they together establish the routing primitives the engine and the dispatcher will compose:
   - (i) Extend `_validate_config_reserved_keys` on `ConnectorAccount` (`db/models.py`) to recognize the `"routing"` reserved key. Schema: `{"rules": list[RoutingRule], "default": str | None}` where `RoutingRule = {"scope": Literal["channel", "thread", "dm", "peer"], "match": str, "agent": str}`. Pydantic validators enforce: scope ∈ allowed set; match non-empty; agent slug shape (matches existing `AgentConfig.name` validator). Repository round-trip via the existing JSON column — no schema migration.
   - (ii) Extract per-agent ACL admission as a pure function into a new module `connectors/_acl.py` (or `connectors/_admission.py` — L2 design picks the final name). Move the F6 outbound channels check from `tools/connector_send.py:195-217` to the new module; export it as `admits_outbound(account, agent_acls, target_channel) -> tuple[bool, str]`. Add the inbound counterpart `admits_inbound(account, agent_acls, peer_id, channel_id) -> tuple[bool, str]` covering both peers AND channels axes plus the DMs-only `[]` sentinel. F6's outbound caller becomes a one-line delegation; behavior byte-identical for existing tests.
   - Tests: routing-rule shape pinned (valid round-trip, invalid scope rejects, missing field rejects, empty rule list permitted); ACL admission both axes (peers + channels + DMs-only sentinel + per-agent override of account-scope) with the F6 outbound tests still passing byte-identically.

3. **Inverse-query repository helper + L4a mechanical dispatcher rename** (leg 3). Two scope items because they unblock the routing engine (L4) and the integration (L5) atomically:
   - (i) `AgentConfigRepository.list_by_connector_account(account_id: str) -> list[AgentConfig]` (or similar method name — L3 design picks). Returns agents whose `connector_account_ids` contains `account_id`. Tests: returns empty for unknown account; returns alphabetically-ordered list of attached agents for known account; round-trips through SQLite.
   - (ii) Mechanical rename of `dispatch_inbound` signature. Introduce `async def dispatch_inbound(account, envelope, ...)` (new signature, no `agent_name` first param). Internally calls a transitional `_resolve_single_attached_agent_or_first_alphabetical(account)` helper (the F6 "first-attached or only-attached" assumption made explicit and named). All ~56 test-fixture call sites migrate mechanically to the new signature. Old signature retained as a thin wrapper for the duration of L3 ONLY (deleted in L5 after the integration lands). Tests: F6 dispatcher tests pass byte-identically under the new signature; the transitional helper has its own unit tests pinning the alphabetical-first-attached semantic.

4. **Routing resolution engine** (leg 4). New pure-function module `connectors/_routing.py` exporting `resolve_routing(account, envelope, eligible_attached_agents, session_metadata) -> RoutingDecision`. `RoutingDecision = {"agent": str | None, "rule_index": int | None, "scope": str, "match": str | None, "reason": str}`. Algorithm:
   - (i) If `session_metadata.get("routing_override")` is set and points to an eligible agent → return it (`reason: "override"`).
   - (ii) Walk `account.config["routing"]["rules"]` in operator-declared order; first match whose `agent` is in `eligible_attached_agents` returns (`reason: "rule-match"`, `rule_index: int`).
   - (iii) If no rule matches, use `account.config["routing"]["default"]` if set and eligible (`reason: "default"`).
   - (iv) If no default, return first agent in `eligible_attached_agents` (alphabetical) whose ACL admits (`reason: "first-eligible"`).
   - (v) If zero eligible, return `RoutingDecision(agent=None, reason="no-eligible-agent")`.
   - ACL admission via L2's pure function. Tests cover all 5 algorithm steps + override-with-ineligible-fallback edge case + thread-scope rule when F3 sessions split on thread.

5. **Inbound dispatcher integration** (leg 5). Wire L1's parser + L4's routing engine into `dispatch_inbound`. Composition order per Design Decisions. Add system-outbound path for command responses via `pool_acquire(routed_agent_name, account_id) → client.send(target, response_text)` — same path the platform-send tool uses (`tools/connector_send.py:219-227`) but invoked dispatcher-internally with function-local imports for cycle-break. Sibling primitive `ChatSessionRepository.set_session_metadata_key` lands here. Audit-log routing decisions via `append_to_session_metadata("routing", ...)`. Remove the transitional `_resolve_single_attached_agent_or_first_alphabetical` helper from L3. Tests: routing-rule match dispatches correctly; routing override dispatches correctly; fallback on ACL-deny dispatches correctly; zero-eligible emits "No agents available" error via system-outbound; command-only message short-circuits agent.step; routing audit-log entries present with paired entries for `/talk-to`.

6. **Six command implementations** (leg 6). Pure-function command handlers in `connectors/_commands.py`:
    - `handle_agents(account, peer_id, eligible_attached_agents) -> str` — list permitted agents.
    - `handle_talk_to(account, peer_id, agent_slug, session_id, eligible_attached_agents, session_metadata_writer) -> str` — set `routing_override`; return confirmation or peer-facing error.
    - `handle_whoami(account, session_id, session_metadata) -> str` — read current effective agent (consult override + last-routing-audit-entry).
    - `handle_new(session_id, repository) -> str` — write `session_metadata["ended_at"] = <iso>` on current session; the F3 `resolve_session` is taught (in this leg or in F3 follow-on — L6 design picks) to treat sessions with `ended_at` set as not-current and create a fresh row on next inbound. **If touching F3 `resolve_session` is required**, that touch is L6's responsibility; the spec acknowledges this as the one F3 ripple in F7.
    - `handle_reset` — alias for `handle_new`.
    - `handle_help(account, peer_id, eligible_attached_agents) -> str` — list available commands filtered for the peer.
    All handlers are pure (no side effects beyond the explicit `session_metadata_writer` and `repository` injections). Tests: each command's happy path + each command's denied path (`/talk-to` to unknown agent; `/talk-to` to ACL-denied agent; `/agents` lists permitted agents only).

7. **Studio Routing Rules editor on connector account** (leg 7). New section on `studio/connector-account-editor.js` between the Allowlist section (F6) and the Attached Agents table (F6). Per-rule editor: scope dropdown (channel/thread/dm/peer) + match input + agent dropdown (sourced from attached agents). Order is operator-controlled via Move-up/Move-down buttons. Per-account default-agent dropdown. New API endpoint OR extension of `PUT /api/connector-accounts/{id}` to round-trip `config["routing"]` — L7 design picks. Mirrors F6 chip-list + attached-agents idiom. Cycle-1 design review applies the F7 design-language uptake audit gate (F6 debrief rec #1): grep for new custom selectors, challenge each, mandate existing primitives where possible.

8. **F6 carry-forward bundle** (leg 8). (i) `tests/test_pairing_prefix.py` — ~6 cases pinning `_validate_pairing_prefix` whitespace + case-sensitivity claims. (ii) `# F8: DM-classification consult lands here` source-code marker at `tools/connector_send.py:202`. Both small; bundled into a single leg. Genuinely orthogonal to L1-L7 — could land first if review-state pressure favors.

9. **Optional HAT closer** (leg 9). Operator-driven verification of the Routing Rules editor (rule authoring, ordering, default agent, save round-trip, design-language audit pass-through). Verify routing audit-log entries appear in `session_metadata` via DB inspection. Inherits F6's "fix issues inline" HAT pattern.

**Key non-modifications**:

- Agent loop (`agent/core.py`, `agent/factory.py` agent-loop logic) — unchanged. F7 only changes the dispatcher signature; the factory's `create(agent_name)` path is unchanged.
- Database schema — no v19 migration. Routing rides on `connector_accounts.config` JSON; routing audit + override ride on `chat_sessions.session_metadata` JSON.
- `Message.visibility` field — unchanged.
- Stub plugin's existing F1-F6 contract — unchanged. F7 does NOT add `CommandHandler` to the stub; the dispatcher's built-in path covers all six commands.
- `ConnectorPlugin` Protocol — unchanged. `CommandHandler` is a SEPARATE Protocol (additive, not widening).
- `ToolProvider` Protocol — unchanged. F7 routing has nothing to do with `ToolProvider` (commands bypass the tool registry entirely).
- F6 `resolve` hook + outcomes — unchanged. F7 routing is downstream of F6's three-arm branch.
- `_validate_pairing_prefix` and the F6 pairing flow — unchanged.

### Checkpoints

- [ ] `CommandHandler` Protocol (single-method) declared in `connectors/base.py`; 5 forward-reference docstring sites reframed; `_parse_command` text-prefix parser ships; F1-F6 regression tests pass byte-identically
- [ ] `connector_accounts.config["routing"]` Pydantic validator + JSON round-trip; ACL admission extracted to `connectors/_acl.py` covering peers + channels + DMs-only sentinel; F6 outbound delegation byte-identical
- [x] `SQLiteAgentStore.list_by_connector_account(account_id)` ships; `dispatch_inbound` signature mechanically renamed (no `agent_name` first param); transitional helper in place; 55 fixture call sites migrated
- [ ] `resolve_routing` pure function ships; all 5 algorithm steps (override → rule-walk → default → first-eligible → zero-eligible) pinned by tests
- [ ] Inbound dispatcher integrates routing engine + command intercept + per-agent ACL inbound gating; system-outbound via `pool_acquire → client.send`; sibling `set_session_metadata_key` primitive ships; routing audit entries logged; transitional helper from L3 removed
- [ ] Six command implementations ship; each happy path + each denied path pinned by tests; `/new` mechanism via `session_metadata["ended_at"]` + F3 `resolve_session` touch
- [ ] Studio Routing Rules editor renders on connector account detail page; rule CRUD + order + default round-trips through API; design-language audit gate passes (cycle-1 review)
- [ ] F6 carry-forward bundle: `tests/test_pairing_prefix.py` lands; `# F8:` marker present at `connector_send.py:202`
- [ ] HAT pass (optional but recommended)

### Adaptation Criteria

**Divert if**:
- L2 design discovers that routing-schema + ACL-extraction together exceeds ~3 hours of work. Mitigation: split into 2a (routing schema + validator only) and 2b (ACL extraction + F6 outbound delegation only); both ship independently, L3 unblocked by either.
- L6 surfaces that the F3 `resolve_session` touch for `/new` is more invasive than expected (e.g. requires a schema migration to support `ended_at` indexing). Mitigation: ship v1 with weak `/new` semantics (clear `routing_override` only, no actual new session) and capture the strong-semantic-`/new` requirement as a Known Issue for a future mission. The L6 verification clause explicitly accepts EITHER strong-`/new` (preferred, with F3 touch) OR weak-`/new` (acceptable, with Known Issue logged).
- The `pool_acquire → client.send` system-outbound path for commands surfaces an unforeseen pool-keying issue (e.g. the routed agent has no pool entry yet because no agent.step has run for this account). Mitigation: L5 design walks the pool acquisition path; if the pool needs a system-acquire shortcut (acquire without the agent.step warm-up cycle), that's a small additive change to the pool helper.
- Routing-rule ordering surfaces a UX defect at HAT — operator cannot reason about precedence without a preview. Mitigation: leg 7 adds a minimal "rule simulator" affordance (paste a sample channel_id, see which rule matches) inline; if scope expands, defer to F10.
- The `/new` and `/reset` semantic confusion surfaces a need for distinct semantics (e.g. `/reset` should clear agent context in-place — agent-loop touch). Mitigation: HAT escalates to operator; if confirmed, defer to a future mission and ship v1 as alias-only with clear `/help` text.

**Acceptable variations**:
- Per-leg design review may surface symmetric shims, additional test fixtures, or doc updates that fit the leg's scope. F6 precedent: these are added inline, documented in the flight log as deviations.
- L2 may pick `_acl.py` vs `_admission.py` (or another final module name) — the choice is recorded in the flight log; the contract is the pure-function shape.
- L3 may pick the exact name of `AgentConfigRepository.list_by_connector_account` (e.g. `list_attached_agents`, `find_by_connector_account`) — the contract is alphabetical-ordered return.
- L5 may pick whether to inline-define `set_session_metadata_key` in `repositories.py` or extract a small sibling module — either acceptable; default is inline alongside `append_to_session_metadata`.
- L7 may pick new endpoint `PUT /api/connector-accounts/{id}/routing` vs extending `PUT /api/connector-accounts/{id}` to round-trip `config["routing"]`. Either acceptable.
- L8 is genuinely independent of L1-L7; could land first if review-state pressure favors. Acceptable.
- HAT (L9) may be skipped if L7 design-language audit produces zero defects on cycle-1 review AND the operator confirms zero-iteration confidence. Default: HAT runs.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `command-handler-protocol-and-parser` (1) — single-method `CommandHandler` Protocol in `connectors/base.py`; close 5 F1 forward-reference sites with citation-language; `connectors/_commands.py` with `_parse_command` text-prefix parser mirroring `_validate_pairing_prefix` shape; tests pin parser; F1-F6 regression byte-identical
- [x] `routing-schema-and-acl-extraction` (2) — `connector_accounts.config["routing"]` Pydantic shape + validator extension; extract per-agent ACL admission into `connectors/_acl.py` covering both peers + channels axes plus DMs-only sentinel; F6 outbound caller becomes one-line delegation; JSON round-trip; tests pin shape and ACL behavior; no schema migration
- [x] `inverse-query-helper-and-dispatcher-rename` (3) — `SQLiteAgentStore.list_by_connector_account(account_id)` helper; mechanical rename of `dispatch_inbound` signature (drop `agent_name`); transitional `_resolve_single_attached_agent_or_first_alphabetical` helper in place for one leg; all 55 test-fixture call sites migrate; F6 dispatcher tests pass byte-identically
- [x] `routing-resolution-engine` (4) — `connectors/_routing.py` pure function `resolve_routing`; algorithm: override → rule-walk → default → first-eligible-attached → zero-eligible; uses L2's ACL admission; uses L3's inverse-query helper; tests cover all 5 algorithm steps + edge cases
- [x] `inbound-dispatcher-integration` (5) — wire routing engine + command parse + per-agent ACL inbound gating into `dispatch_inbound`; system-outbound path via `pool_acquire → client.send` for command responses; sibling primitive `set_session_metadata_key`; audit-log routing decisions; remove L3's transitional helper; tests pin composition + audit-log entries
- [x] `command-implementations` (6) — six command handlers (`handle_agents`, `handle_talk_to`, `handle_whoami`, `handle_new`, `handle_reset`, `handle_help`); each pure-function (with explicit injections); `/new` mechanism via `session_metadata["ended_at"]` + F3 `resolve_session` touch (one F3 ripple, scoped to this leg); `/reset` is alias for `/new`; tests cover happy + denied paths
- [x] `studio-routing-rules-editor` (7) — new section on `connector-account-editor.js` between Allowlist and Attached Agents; per-rule editor; order via Move-up/Move-down; per-account default; API round-trip; cycle-1 design-language uptake audit (F6 debrief rec #1)
- [x] `f6-carry-forward-bundle` (8) — `tests/test_pairing_prefix.py` (~6 cases); `# F8: DM-classification consult lands here` marker at `tools/connector_send.py:202` (post-L2 the marker target moved to `_acl.py`'s DMs-only branches); genuinely orthogonal
- [ ] `hat-and-alignment` *(optional)* — Operator-driven verification of Routing Rules editor + audit-log entries; inline fixes per F6 HAT-as-catch-all pattern. **Deferred to post-commit** — runs interactively after the PR opens.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (unit + browser)
- [ ] Documentation updated:
  - [ ] `agents.md` Connector subsystem section adds routing + command-surface conventions (per-axis-tri-state-override codification per F6 debrief rec #3 is independently scoped; F7 contributes routing conventions)
  - [ ] `connectors/README.md` updates §4 (optional hooks) to include `CommandHandler` as a Protocol example alongside the `resolve` hook example
  - [ ] CommandHandler forward-reference docstrings (5 sites) replaced with citation-language post-L1
- [ ] Mission Open Question 3 resolved (routing precedence + command vocab)
- [ ] Mission Open Question 6 resolved (text-prefix v1; slash-command additive via CommandHandler)
- [ ] F6 follow-ups closed: pairing-prefix tests, F8 marker

### Verification

The flight achieves its objective when:

1. **Multi-agent routing**: with N agents attached to one connector account and operator-authored rules, an inbound resolves to exactly one agent per the precedence (override → rule-walk → default → first-eligible-alphabetical); routing decisions are persisted in `session_metadata["routing"]` for audit.
2. **Command surface — six commands**: `/agents`, `/talk-to <slug>`, `/whoami`, `/new`, `/reset` (alias), `/help` all work against the stub plugin via dispatcher tests; commands emit responses via the system-outbound `pool_acquire → client.send` path (NOT via `send_to_platform_channel`); commands work even when platform-send tool is operator-disabled.
3. **Permission composition**: `/agents` lists ACL-permitted agents only; `/talk-to` to an ACL-denied or unknown agent returns an explicit peer-facing error; `/help` lists commands filtered for the peer's permissions.
4. **Unreachable-agent UX**: a routing pick that fails per-agent ACL silently falls back to the next eligible agent (alphabetical) with an audit-log entry; zero-eligible emits "No agents available for this conversation." to the peer via the system-outbound path.
5. **Dispatcher signature substitution**: `dispatch_inbound` no longer takes `agent_name`; ~56 test-fixture call sites migrated; the F6 hand-off documented in the F6 debrief is closed.
6. **ACL admission as pure function**: `connectors/_acl.py` covers both peers and channels axes plus DMs-only sentinel; F6 outbound delegates to it byte-identically; F7 inbound consults it post-routing.
7. **CommandHandler Protocol (single-method)**: declared and documented; stub does NOT implement it; built-in text-prefix path handles v1; F8 Discord can additively register slash commands by satisfying the Protocol.
8. **Studio Routing Rules editor**: operator can author rules, reorder them, set a default agent, and round-trip through API; design-language audit gate passes cycle-1 (F6 debrief rec #1 in practice).
9. **F6 carry-forward closed**: pairing-prefix tests pin the helper's claims; F8 marker present.
10. **Regression posture**: F1-F6 test suites pass byte-identically; agent loop unchanged; no schema migration; no `ConnectorPlugin` Protocol widening; no `ToolProvider` Protocol widening; no agent-config field additions; stub plugin's F1-F6 contract byte-identical.
