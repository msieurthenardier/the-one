# Flight: Pairing, Allowlists, and Per-Agent ACLs

**Status**: in-flight
**Mission**: [Bi-directional Communication Connectors](../../mission.md)

## Contributing to Criteria

- [ ] Mission #4 — Unknown senders gated by a pairing or allowlist mechanism; approval state survives restart
- [ ] Mission #6 — A connector account can be attached to any number of agents through Studio; inbound routes to exactly one of the attached agents per the operator-configured routing rules (F6 establishes attachment + per-agent ACLs; F7 adds the multi-agent routing rules layer)
- [ ] Mission #15 — `platform-send` can only target connector accounts the calling agent is attached to AND only conversation locations the agent has access to per the allowlist/ACL resolution that governs inbound routing
- [ ] Mission #28 — The Admin connector-account surface, the Studio connector-attach surface, the doctor probe, and the in-Chat connector-session view all meet M04/M06 design-language quality bar without alignment-flight rework (F6 lands the Studio connector-attach surface)
- [ ] Mission #29 — Each layer of the integration has automated coverage proving its contract (F6 adds: pairing/allowlist gating, per-agent ACL resolution)

---

## Pre-Flight

### Objective

Land the gating substrate for connector-attached agents end-to-end: an optional `resolve(account, envelope)` plugin hook returning `Permit | NeedsPairing | Deny`, a two-scope allowlist model (account-level peer/channel admission on `connector_accounts.config` + per-agent ACL on `AgentConfig`), a DM-pairing flow for unknown senders via a peer-side `PAIR <code>` prefix, the operator-facing Studio surfaces for both scopes, the resolver consultations at both the inbound dispatcher and the platform-send tool's outbound site, and the narrow-primitive `append_to_session_metadata` writer that records audit outcomes. As a parallel scope item, close the F5 carry-forward live-broadcast visibility gap on the WS-typed path. The stub plugin's existing F1–F5 contract is unchanged; the new resolver hook is optional (absent → default Permit). F8 (Discord) is the first real-platform consumer. No agent-loop changes — all gating happens at the connector subsystem's boundary.

### Open Questions

- [x] **Pairing state persistence shape** → see Design Decisions ("Account config as the persistence shape (account-scope) + AgentConfig column (per-agent ACL)")
- [x] **Pairing flow mechanism** → see Design Decisions ("Peer-side PAIR prefix")
- [x] **Resolver outcome shape** → see Design Decisions ("Three outcomes: Permit / NeedsPairing / Deny")
- [x] **Resolver discovery (Protocol vs. hook)** → see Design Decisions ("Optional plugin hook via getattr")
- [x] **Outbound resolver injection** → see Design Decisions ("Per-call repository fetch + ACL kwarg")
- [x] **`session_metadata` writer primitive** → see Design Decisions ("New narrow primitive `append_to_session_metadata`")
- [x] **Per-agent ACL persistence** → see Design Decisions ("On `AgentConfig.connector_acls`")
- [x] **Edit-surface split (intra-Studio)** → see Design Decisions ("Account-scope on Connectors detail page; per-agent ACL on Agent Editor Connectors tab")
- [x] **Live-broadcast WS-typed visibility closure** → see Design Decisions ("Fold F5 carry-forward into F6 via pre-step USER tagging at the live broadcast dict-literal")
- [x] **HAT closer** → see Design Decisions ("Required HAT")
- [ ] **Routing precedence when multiple agents attach to one account** — F6 builds the per-agent ACL primitive; F7 owns the multi-agent routing rules. F6 dispatcher must pick SOME agent when an inbound permits multiple ACLs — temporary single-agent assumption: pick first-attached or only-attached. Document the F7 hand-off point in the inbound-gating leg.
- [ ] **Pairing code regeneration semantics** — does regenerating invalidate prior code immediately, or grace-window? Default: immediate invalidation. Already-paired peers are unaffected (their `peer_id` persists in the allowlist; the code only gates first-contact). Confirm during HAT.

### Design Decisions

**Account-config persistence for account-scope state**: Pairing code + account-scope allowlist (peers + channels) ride on the existing `connector_accounts.config: dict[str, Any]` column under reserved keys `config["pairing"]` and `config["allowlist"]`. No schema migration for these.
- Rationale: M10 explicitly designed `config` as schema-loose (`db/models.py:134`) so per-platform fields can grow without migrations; account-scope allowlist + pairing are operator-managed connector state, exactly the shape `config` is for.
- Trade-off: SQL-side queryability is harder than a relational shape. Mitigation: the operator UI is the authoritative inspector; no batch-query use case in F6 scope.

**AgentConfig column for per-agent ACL**: A new `AgentConfig.connector_acls: dict[str, dict[str, list[str]]] | None` field mirrors the `mcp_overrides` precedent. The dict is keyed by `account_id`; the value is `{"peers": [...], "channels": [...]}`. An account_id absent from the dict = "inherit account-scope" (no restriction). v18 schema migration adds the corresponding `connector_acls` column to the `agents` table. Round-trips through `SQLiteAgentStore.save` / `_row_to_config` exactly the way F4 L5 round-trips `connector_account_ids`.
- Rationale: Per-agent ACL belongs to the (account × agent) intersection. AgentConfig is the natural home for per-agent state that addresses an external resource by id (mirroring `mcp_overrides`). Reverse-lookup ("which agents have ACL rows for this account?") becomes a SQL query against the agents table rather than scanning JSON in every account row.
- Trade-off: Yes, F6 ships a v18 migration. The F4 debrief lesson at rec #1 ("when a leg adds a Pydantic field intended to persist, the migration is in the SAME leg, not a future one") informs leg 1c — the migration co-lands with the Pydantic field, not in a future maintenance leg.

**Peer-side PAIR prefix**: Unknown peers self-pair by sending a message prefixed `PAIR <code> <message>`. Connector strips the prefix on successful pair, persists the peer_id, and processes the cleaned message. Mirrors openclaw's pattern.
- Rationale: Lowest-friction path for the peer; doesn't block the platform inbound on operator availability. The operator does NOT need to sit at the console to approve each new peer — they hand out the code out-of-band and pairings happen asynchronously.
- Trade-off: A leaked pairing code is a credential. Mitigation: code is regenerable from the account detail page; regeneration invalidates prior code immediately; pairings already made survive.

**Three-outcome resolver shape**: The resolver returns `Permit | NeedsPairing(reason) | Deny(reason)`. The hook signals SHAPE (the resolver's read of the situation); the dispatcher validates the pairing code and decides Permit-vs-Deny within `NeedsPairing`.
- Rationale: Keeps the hook pure (per-plugin) while letting the dispatcher own pairing-code validation (cross-plugin). Future plugins can identify pairing attempts however they want (text prefix, slash command, OAuth callback) without leaking validation into the hook.
- Trade-off: Three outcomes is more verbose than a boolean; pays for itself via the audit-log + future-proofing path.

**Optional plugin hook via getattr** (resolver discovery): The dispatcher resolves the resolver via `getattr(plugin, "resolve", _default_permit)` — same convention as F3's `display_channel` codified in agents.md `optional-plugin-hook-via-getattr-sentinel`. A plugin that does not implement `resolve` is consulted via `_default_permit` (always returns `Permit`), preserving F1-F5 stub-driven test behavior byte-identically.
- Rationale: Conservative regression posture. Future plugins opt INTO gating by implementing the hook; the F8 Discord plugin's `resolve` will be the first non-default consumer. No isinstance check, no `ConnectorRegistrationError` failure mode for missing-resolver — a connector without a resolver is a connector that doesn't gate, which matches the F1 stub's intent.
- Trade-off: Less typesafe than a separate Protocol. Mitigation: the convention is codified; future plugin authors find it via the existing precedent.

**Per-call repository fetch + ACL kwarg** (outbound resolver injection): `SendToPlatformChannelTool.__init__` gains a `connector_acls: dict[str, dict] | None` constructor kwarg (passed by `AgentFactory.create()` from `config.connector_acls`); `execute()` fetches `account.config["allowlist"]` via `ConnectorAccountRepository.get(account_id)` at call time (function-local import — mirrors `_inbound.py:104-110` convention). The same default-permit semantics apply: an account with no `config["allowlist"]` and an agent with no `connector_acls[account_id]` entry → permit.
- Rationale: No `ToolProvider` Protocol widening (deferred to F8 if a third factory-kwarg case actually emerges). One extra DB read per outbound is acceptable; F4 already incurs one for the pool acquire. Stale-snapshot risk avoided by reading account state at send time.
- Trade-off: Per-call account fetch is observably slower than a constructor-injected snapshot. Acceptable for F6; F10 hardening can profile and optimize if needed.

**New narrow primitive `ChatSessionRepository.append_to_session_metadata`** (audit log writer): Leg 2 ships `async def append_to_session_metadata(self, session_id: str, key: str, value: Any) -> None` that SELECTs current `session_metadata`, merges `{key: value}` (deep-merge if the existing key is dict-typed and the new value is dict-typed), and UPDATEs the single column. Mirrors `update_last_inbound` at `db/repositories.py:807-836`.
- Rationale: `ChatSessionRepository.update()` at `db/repositories.py:758-772` explicitly excludes `session_metadata` from its round-trip — F6 is the first in-place writer (F3 created via `create()` only; F7 was assumed to be the first mutator). The narrow primitive matches the project's "one column, one primitive" pattern.
- Trade-off: F7 will need a sibling primitive for routing-decision logs (likely the same primitive, different key). Fine — F6's primitive is the canonical writer.

**Intra-Studio edit-surface split**:
- **Studio → Connectors → {account detail}**: pairing code generation/regeneration + account-scope allowlist (peers + channels) + read-only summary of attached agents with ACL counts and deep-links to Agent Editor.
- **Studio → Agent Editor → {agent} → Connectors tab (NEW)**: attach/detach checkboxes (mirrors MCPs tab) + per-agent ACL editing (peers + channels) for each attached account.
- Rationale: Account-scope state belongs to the account; per-agent ACL belongs to the (account × agent) intersection. Both Connectors and MCP Servers live under Studio's sidebar (post-F2 relocation per `studio.js:236,441`); the F6 split is intra-Studio between the Connectors registry page and the Agent Editor's per-agent tab.
- Trade-off: Operator needs to glance at two surfaces to see the full picture for a multi-agent account. Mitigation: the Connectors detail page shows a read-only summary of per-agent ACLs with deep-links.

**Empty-ACL inheritance**: A per-agent ACL with the account_id ABSENT from `connector_acls` (or present with empty `peers` and empty `channels`) means "inherit account-scope" (no agent-level restriction). A non-empty ACL means "intersect: agent reaches peer/channel ONLY IF both account-scope AND agent-ACL permit."
- Rationale: Default-permissive on attachment matches operator intuition ("I attached this agent, so it can talk to whoever the account talks to"). Explicit restriction is opt-in.
- Trade-off: An empty ACL row reads ambiguously at a glance. Mitigation: UI labels: "no restrictions — inherits account-scope" when empty; explicit list rows when populated.

**Fold F5 live-broadcast gap into F6 via pre-step USER tagging at the live broadcast dict-literal**: At `interfaces/web/app.py:_process_and_broadcast`, the live broadcast emits a raw dict event `{"type": "user", "content": ..., "source": ...}` at line 817-819 BEFORE `agent.step` runs. F6 leg 6 injects `"visibility": OPERATOR_VISIBILITY` into THAT dict when `session.platform is not None`, mirroring the codec's projection rule at `db/codec.py:173-176`. The post-step Message-level tagging at `app.py:1003-1004` is unchanged (it's the refresh path; leg 6 is the live path). The two sites are independent.
- Rationale: Single-site change; matches the existing codec projection rule; closes a documented operator-visible UX gap with no agent-loop change. The architect's framing correction (dict-literal, not Message-level) is captured in the leg-6 scope.
- Trade-off: Adds a leg to F6. Acceptable.

**Required HAT closer**: F6 ends with a required HAT leg, not an optional alignment leg.
- Rationale: F6 touches operator-visible Studio surfaces (Connectors detail page, Agent Editor Connectors tab) AND adds operator-driven flows (pairing code generation, peer revocation). F5 debrief recommended HAT-required becomes default for operator-visible flights (rec #4).
- Trade-off: HAT requires operator wall-clock time. Acceptable; F5 HAT surfaced 4 issues automated tests couldn't have caught.

### Prerequisites

- [ ] F5 landed and merged to main (verified: `c345883 flight/05: Chat UI` on main)
- [ ] `connector_accounts` table with `config` column exists (F1 v13 + F2 v14 + F3 v16 — verified)
- [ ] `AgentConfig.connector_account_ids` and persistence round-trip exist (F4 L1 + L5 — verified at `agent/config.py:135`, `db/repositories.py:99-214`)
- [ ] `SendToPlatformChannelTool.execute` carries an explicit F6 hook-point at `tools/connector_send.py:131` (verified)
- [ ] Stub plugin exists for end-to-end test fixture (`the_one/connectors/_stub.py` — verified)
- [ ] `chat_sessions.session_metadata` column exists for audit logging (F3 L1 — verified; new in-place writer ships in leg 2 since `ChatSessionRepository.update()` excludes the column per `db/repositories.py:758-772`)
- [ ] Studio MCPs tab pattern exists for mirroring (`studio/mcps-tab.js:34` — verified; `studio.js:161` four-tab whitelist needs extension; `agent-editor.js:45-119` scaffolding needs new tab wiring — leg 5 walks every site)
- [ ] `optional-plugin-hook-via-getattr-sentinel` convention codified in agents.md from F3 (verified — F6 reuses it as the resolver-discovery pattern)
- [ ] No conflicting pairing/allowlist scaffolding in the codebase (grep verified zero hits)

### Pre-Flight Checklist

- [ ] All open questions resolved (2 remaining: F7 routing precedence hand-off, regenerate-code semantics — both deferred to per-leg design or HAT)
- [ ] Design decisions documented (10 decisions; 4 resolved during architect review cycle)
- [ ] Prerequisites verified against current code (recon report in flight-log)
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach

F6 is **gating substrate first, persistence + writers second, consumer sites third, UI fourth, regression closure fifth, HAT last**:

1. **Resolver hook + outcome types** (leg 1a). The `resolve(account, envelope)` optional plugin hook signature + the `Permit | NeedsPairing | Deny` outcome ADT in `connectors/base.py`. The hook is NOT a Protocol that plugins must satisfy — it's a `getattr`-discovered optional method, same convention as F3's `display_channel`. A `_default_permit` callable is the fallback. Stub plugin does NOT implement `resolve` (preserves F1-F5 byte-identical regression). Acceptance: import path + outcome construction + default-permit semantics + back-compat assertion (stub-driven F1-F5 tests pass byte-identically).

2. **Account-config schema for pairing + account-scope allowlist** (leg 1b). `config["pairing"] = {"code": str, "issued_at": iso}` and `config["allowlist"] = {"peers": list[str], "channels": list[str]}`. Pydantic validators land via a `@field_validator("config")` on `ConnectorAccount` that parses ONLY the reserved keys (the rest of `config` stays schema-loose per the F1 promise). The validator fires on `ConnectorAccount.model_validate(merged)` at `api.py:2218`; the read-from-DB path at `repositories.py:_row_to_model` constructs via direct kwargs so it skips the validator — leg 1b's design walks both paths and decides whether to add `model_validate` on read or accept one-sided validation. JSON round-trip is via `json.dumps(account.config)` / `json.loads(row["config"] or "{}")` at `db/repositories.py:515,538,564` — preserved without change.

3. **AgentConfig.connector_acls field + v18 migration** (leg 1c). Mirrors F4 L5 exactly: `connector_acls: dict[str, dict[str, list[str]]] | None` Pydantic field; v18 ALTER TABLE adds `agents.connector_acls TEXT` column; `SQLiteAgentStore.save` JSON-serializes; `_row_to_config` JSON-deserializes. Pydantic validators on the nested shape; absent `account_id` keys mean "inherit account-scope." The migration ships in the SAME leg as the field (F4 debrief rec #1 — methodology trap closure).

4. **Inbound gating + pairing flow + audit writer** (leg 2). Dispatcher consults `getattr(plugin, "resolve", _default_permit)(account, envelope)` after account-load + plugin-resolve. `NeedsPairing` outcome triggers pairing-prefix validation (dispatcher-side, against `account.config["pairing"]["code"]`) → on success: strip prefix, append peer_id to `account.config["allowlist"]["peers"]`, persist via account repository, append outcome to `session_metadata` via the NEW `ChatSessionRepository.append_to_session_metadata` narrow primitive. All three outcomes log to `session_metadata` for audit. Persistence survives process restart.

5. **Outbound gating** (leg 3). `SendToPlatformChannelTool.__init__` gains `connector_acls: dict[str, dict] | None = None`; `AgentFactory.create()` passes `config.connector_acls`. `execute()` does function-local-import on `ConnectorAccountRepository`, fetches `account = await acc_repo.get(account_id)`, consults: (i) `target.channel_id ∈ account.config["allowlist"]["channels"]` (or allowlist absent → permit); (ii) `target.channel_id ∈ self._connector_acls[account_id]["channels"]` (or account_id absent → inherit). Deny → existing `[error] [constraint] ...` envelope shape from F4. Permit → proceeds to existing pool_acquire + client.send.

6. **Studio Connectors detail page** (leg 4). Pairing code section (generate, copy, regenerate); account-scope allowlist editor (peers + channels lists with add/remove); read-only attached-agents summary with ACL counts + deep-links. New API endpoint OR `/api/connector-accounts/{id}` extension to support the reverse lookup ("which agents have `connector_account_ids` containing this id?") — leg 4 design picks. Quality bar = F5 HAT-class.

7. **Studio Agent Editor Connectors tab** (leg 5). New tab id `'connectors'` added to `studio.js:161` whitelist + `agent-editor.js:45-119` scaffolding (PANEL_IDS, tablist HTML, panel HTML). New module `studio/connectors-tab.js` mirroring `studio/mcps-tab.js:34`'s `renderMcpsTab` shape. Attach/detach checkboxes write `AgentConfig.connector_account_ids`; per-attached-account ACL editor writes `AgentConfig.connector_acls`. Empty ACL labeled "no restrictions — inherits account-scope" inline. Quality bar = F5 HAT-class.

8. **WS-typed pre-step USER tagging** (leg 6). At `_process_and_broadcast` in `interfaces/web/app.py` (around line 817-819), inject `"visibility": OPERATOR_VISIBILITY` into the `user_event` dict when `session.platform is not None`, BEFORE the live broadcast. The `session_locks[session.id]` taken at line 258 serializes this against `_inbound.py:155`'s `dispatch_inbound`, so there is no race. Closes F5 carry-forward documented in `interfaces/web/app.py` comments + F5 flight-log + F5 debrief action item. Update mission Known Issues to mark the live-broadcast asymmetry closed.

9. **Required HAT closer** (leg 7). Operator-driven verification of: pairing code generation + peer self-pairing flow (peer-side PAIR prefix), peer revocation, denied-peer behavior, account-scope allowlist editing, per-agent ACL editing, outbound channel ACL enforcement, the live-broadcast-WS-typed marker appearing immediately (no refresh needed). HAT inherits the F5 "required (not optional)" pattern.

**Key non-modifications**:

- Agent loop (`agent/core.py`, `agent/factory.py` agent-loop logic) — unchanged. F6 only adds factory-kwarg passing for `config.connector_acls`.
- Database schema for `connector_accounts` — no v18 migration on that table; F6 rides on the existing `config` column.
- `Message.visibility` field — unchanged shape; F6 leg 6 adds an additional tagging site at the WS broadcast dict (mirrors the F5 storage-edge shim pattern).
- Stub plugin's existing F1–F5 contract — unchanged. F6 does NOT add a `resolve` method to the stub; the dispatcher's `_default_permit` fallback covers it. (Tests that want to exercise the gating end-to-end will use `register_for_test`-style stub variants or monkeypatch the resolver at the dispatcher consult site.)
- `ConnectorPlugin` Protocol — unchanged. `resolve` is an OPTIONAL hook, not a Protocol method.
- `ToolProvider` Protocol — unchanged. The outbound resolver consultation rides through per-call account fetch, not a third factory-kwarg case. (Architect-review item from F4 debrief rec #4 → deferred to F8 if a third case emerges.)

### Checkpoints

- [x] Resolver hook + outcomes land; stub does NOT implement `resolve`; F1–F5 regression tests pass byte-identically (no behavior change when account.config has no allowlist)
- [x] `connector_accounts.config["pairing"]` / `["allowlist"]` round-trips through Pydantic validation + JSON serialization + DB write/read
- [x] `AgentConfig.connector_acls` + v18 migration + repository round-trip ship in a single leg
- [x] Inbound gating: unknown peer denied silently, paired peer permits, pairing prefix consumed and persisted, persistence survives restart, audit-log entries written via the new `append_to_session_metadata` primitive
- [x] Outbound gating: per-agent ACL denial returns `[error] [constraint]` envelope; permitted channel proceeds normally; no `ToolProvider` widening
- [x] Studio Connectors detail page renders pairing + account allowlist + read-only attached-agents summary; round-trips to API; design quality bar met
- [x] Studio Agent Editor Connectors tab renders attach + per-agent ACL; round-trips to API; design quality bar met
- [x] WS-typed user message live-broadcasts with `visibility=operator` immediately (no refresh) on connector-attached sessions; mission Known Issue closes
- [ ] HAT pass

### Adaptation Criteria

**Divert if**:
- The `getattr`-resolver-hook pattern surfaces an unforeseen typing issue (e.g. mypy can't narrow the optional callable cleanly through the dispatcher). Mitigation: fall back to a separate `AllowlistResolver` Protocol with isinstance check at the dispatch site — F4's `protocol-widening-for-required-capability` precedent.
- The `AgentConfig.connector_acls` v18 migration surfaces a backfill ambiguity (existing rows with NULL ACL — does NULL mean "inherit" or "deny all"?). Default per the design: NULL → inherit. Diversion only if HAT operator wants opt-in deny-by-default.
- HAT surfaces a flow that the architecture cannot accommodate without an agent-loop change. Diversion: stop, escalate, re-plan.
- The per-call account fetch in `SendToPlatformChannelTool.execute` introduces a measurable latency floor that breaks F4's existing send-tool tests. Diversion: snapshot the allowlist at construction time (option-ii fallback).

**Acceptable variations**:
- Per-leg design review may surface symmetric shims, additional test fixtures, or doc updates that fit the leg's scope. F5 precedent: these are added inline, documented in the flight log as deviations.
- The UI rendering details (column count, button placement, copy text) may vary from the walkthrough — the contract is the data flow + accessibility + design-token usage, not the pixel positions.
- The leg order MAY swap legs 4 and 5 if review-state pressure favors landing the Agent Editor tab first. Both legs are independent of each other and depend only on legs 1a/1b/1c.
- Leg 6 (WS pre-step USER tagging) is genuinely independent of legs 1a–5; it could land in parallel with the gating legs. The end-to-end test fixture for leg 6 depends on F3+F5 substrate already in main, NOT on F6 legs. Acceptable to land leg 6 first if it reduces review-state risk.
- Leg 4's API-shape decision (new reverse-lookup endpoint vs. extending `/api/agents` listing) MAY swing based on what's simpler given the existing `/api/agents` shape. Either is acceptable; leg 4 design picks.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `allowlist-resolver-hook-and-outcomes` (1a) — `resolve(account, envelope)` optional hook signature + `Permit | NeedsPairing | Deny` outcome ADT in `connectors/base.py`; `_default_permit` callable; back-compat regression assertion via stub-driven F1-F5 test suite
- [x] `account-config-pairing-and-allowlist-schema` (1b) — `config["pairing"]` + `config["allowlist"]` Pydantic shape + `@field_validator("config")` on `ConnectorAccount`; JSON round-trip; repository read/write integration tests
- [x] `agent-config-connector-acls-and-v18` (1c) — `AgentConfig.connector_acls` Pydantic field + v18 migration adding `agents.connector_acls TEXT` column + `SQLiteAgentStore.save` / `_row_to_config` JSON round-trip; mirrors F4 L5 exactly
- [x] `inbound-gating-pairing-and-audit` (2) — Dispatcher consults `getattr(plugin, "resolve", _default_permit)`; pairing-prefix validation + strip + persistence via account repository; new `ChatSessionRepository.append_to_session_metadata` narrow primitive; audit log entries for all three outcomes; tests: paired peer permits, unknown peer denies, valid pairing-prefix consumed + persisted (survives restart), invalid pairing-prefix denies, audit entries present in `session_metadata`
- [x] `outbound-gating` (3) — `SendToPlatformChannelTool.__init__` connector_acls kwarg; `execute()` per-call account fetch; allowlist + per-agent ACL consultation against `target.channel_id`; tests: denied channel returns `[error] [constraint]` envelope; permitted channel proceeds; account-scope-permit-but-agent-ACL-denies returns constraint; existing F4 account-scope tests pass byte-identically
- [x] `studio-connectors-account-surface` (4) — Pairing code section + account-scope allowlist editor + read-only attached-agents summary on Studio Connectors detail page (`studio/connector-account-editor.js`); API extension or new endpoint for the reverse lookup (leg-design picks); quality bar = F5 HAT-class
- [x] `studio-connectors-attach-tab` (5) — New Connectors tab on Studio Agent Editor (`studio/agent-editor.js` extension + new `studio/connectors-tab.js`) mirroring MCPs tab pattern; per-agent ACL editor; `studio.js:161` four-tab whitelist extension + agent-editor.js:45-119 PANEL_IDS / tablist / panel scaffolding; API: GET/PUT extends `/api/agents/{name}` to round-trip `connector_acls`; quality bar = F5 HAT-class
- [x] `ws-pre-step-visibility-tagging` (6) — Dict-literal injection at `interfaces/web/app.py:817-819` (NOT Message-level — the live broadcast emits a raw dict, mirrored from the codec's projection rule); closes F5 carry-forward action item; test: live-broadcasted user message on connector-attached session carries `visibility=operator` without refresh; mission Known Issue update
- [ ] `hat-and-alignment` *(REQUIRED)* — Operator-driven verification of all F6 surfaces and flows; deviations + inline fixes per F5 HAT-as-catch-all pattern

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (unit + browser)
- [ ] Documentation updated (`agents.md` if a new Project Convention crystallizes — e.g. `module-local-rebinding-isolates-callsite-patching` from F4 still uncodified at n=1; `connectors/README.md` for the gating architecture; per-flight test-suite metrics captured per F5 debrief rec #5)
- [ ] Mission Known Issue closed: live-broadcast WS-typed visibility asymmetry (currently buried in code comments + F5 flight-log)
- [ ] F4 → F6 ToolProvider Protocol widening item: deferred to F8 per per-call-account-fetch decision; documented for F8 awareness

### Verification

The flight achieves its objective when:

1. **Pairing flow**: an unknown peer on the stub plugin can self-pair via a `PAIR <code>` prefix; the persisted approval survives a process restart; subsequent messages from the same peer route normally without re-pairing; the audit log in `session_metadata` records the pairing event
2. **Two-scope gating**: an account-level allowlist gates peer admission; a non-empty per-agent ACL further intersects on (peer × agent) and (channel × agent); an account_id absent from `AgentConfig.connector_acls` inherits account-scope
3. **Outbound gating**: `SendToPlatformChannelTool.execute` rejects channels outside the calling agent's reachable set with the existing `[error] [constraint]` envelope shape; permitted channels proceed via the unchanged F4 outbound path
4. **Studio surfaces**: operator can generate a pairing code, manage account-scope allowlist, attach an account to an agent, edit per-agent ACL, and see the full picture across the two Studio pages with the read-only summary on the Connectors detail page
5. **Live-broadcast closure**: operator typing on a connector-attached chat session sees the `[operator-only]` marker immediately on their own bubble (no refresh); mission Known Issue closes
6. **HAT pass**: operator-driven verification on all surfaces and flows
7. **Regression posture**: F1–F5 test suites pass byte-identically; agent loop unchanged; no `ConnectorPlugin` Protocol widening; no `ToolProvider` Protocol widening
