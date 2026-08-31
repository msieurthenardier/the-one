# Flight: Channel Contract

**Status**: landed
**Mission**: [Connector Reset](../../mission.md)

## Contributing to Criteria
- [x] Connector credentials remain Fernet-encrypted at rest, masked in every response, and enrolled in `POST /api/encryption/rotate` — flight-end review verified Fernet at rest, MCP-pattern masking, rotation stop+restart with fresh-row re-fetch (tested)
- [x] Admission is a flat allowlist plus one-time TTL pairing code; unknown sender gets total silence, nothing persisted (behavior-test checkpoints 3–4, both runs); no engagement gate/ACL overlay/approval queue exists
- [x] A connector serves one default agent with an optional flat channel→agent map (DD-4 authorization matrix enforced and tested); no routing engine, rules, or audit log
- [x] *(retained, verified via behavior test)* Unified history with peer attribution, operator-only distinction, and top-level peer-visible tool results; operator messages never reach the platform (run 2026-08-31-22-43-08, 7/7)
- [x] *(running count)* Python 1,060 / 1,500 flight (1,060 / 3,000 mission); JS ~675 / 1,000 mission ceiling (flight-end recount; FD-accepted over the 650 flight target)
- [x] *(partial)* Five docs rewritten; forbidden-term greps clean (flight-end review re-verified)

---

## Pre-Flight

### Objective

Rebuild the connector subsystem's platform-agnostic core on the seams Flight 1 kept: one Protocol (`connect` / `disconnect` / `send` / `doctor` / optional `history` + an inbound callback), a registry, a listener manager (one long-lived task per enabled connector, reconnect with backoff, lifespan start/stop), and an inbound pipeline — flat allowlist admission, one-time pairing code, DM/mention/always-listen reply policy, `/new` interception, session resolution on the kept keying columns with the continuation window, dispatch to the connector's default agent (or channel→agent map entry). Re-attach the send tool as a plain operator-enabled built-in and add the small last-N history tool. Expose minimal CRUD + doctor + pairing routes over the kept table, a minimal Studio form, and the in-process stub plugin that proves the whole contract end-to-end in a behavior test — all in ≤1,500 Python lines.

### Open Questions
- [x] Send tool availability model → DD-4
- [x] Pairing code shape → DD-3
- [x] Flight 2 real-environment verification → DD-10
- [x] (from mission planning) agent binding, history tool, commands → mission Resolved Questions 3–5

### Design Decisions

**DD-1 — Package layout, five small modules**: recreate `the_one/connectors/` as `base.py` (the Protocol + inbound envelope dataclass), `registry.py` (type→plugin factory, `register_for_test`), `manager.py` (listener task lifecycle: start per enabled connector at lifespan startup, reconnect with jittered backoff, drain on shutdown; also holds transient pairing codes), `inbound.py` (admission → pairing → `/new` intercept → session resolution → agent dispatch → reply), `stub.py` (in-process test plugin).
- Rationale: mirrors the shape the 2026-08 research brief found in Hermes/nanobot — thin channel layer, one small client per platform; each module has one job.
- Envelope note (design review 2026-08-31): the inbound envelope carries **explicit `is_dm` and `mentions_bot` booleans** set by the platform client — DM/mention detection is the client's translation job, never a `channel_id` naming convention the pipeline infers from. The stub sets them directly.
- Trade-off: none material; the ceiling forces the discipline.

**DD-2 — Connector config schema, minimal reserved keys**: `config` JSON carries `default_agent` (required to serve traffic), `channel_map` (optional `{channel_id: agent_name}`), `allowlist` (`{"peers": [...], "channels": [...]}`), `always_listen` (`[channel_id, ...]`). One small validator (tens of lines, not 430) on the kept `Connector` model; unknown keys rejected.
- Rationale: the binding direction flips here — connector→agent, in config, no schema change; honors the one-migration mission constraint.
- Trade-off: renaming/removing an agent leaves a dangling `default_agent` — doctor reports it rather than a validator forbidding it (agents are project-local; hard referential integrity isn't worth the coupling).

**DD-3 — Pairing: one-time code, in-memory, TTL 10 minutes**: `POST /api/connectors/{id}/pairing-code` generates a short random code held only in the manager's memory with an expiry; an unknown peer whose first DM is exactly the code is appended to `allowlist.peers` (persisted via the repository) and the code is consumed. Wrong or absent code → silence, nothing persisted, no counter. Restart invalidates outstanding codes.
- Rationale: one-time + TTL matches the silence-by-default posture; in-memory keeps failed attempts unpersistable by construction.
- Trade-off: a code doesn't survive an app restart — regenerate, acceptable for an operator-local tool.

**DD-4 — Send tool is a plain built-in the operator enables, with binding-derived authorization**: `send_to_platform_channel` (name preserved from the pre-reset contract) registers like every other built-in in `tools/builtins.py` (current constructor shape: `cls(cfg, cross_configs=..., agent_name=...)` — the tool receives the calling agent's name that way); the operator toggles it on the agent they bind. No factory carve-out, no auto-attach — the agent loop stays untouched. **Authorization** (design review 2026-08-31 — the pre-reset tool checked `account_id ∈ connector_ids`; the flipped binding needs the mirror): the tool's target is a tagged union — **channel-keyed** (`{connector, channel_id}`) or **peer-keyed DM** (`{connector, peer_id}`); `channel_map` never applies to DMs. For a channel target, `execute()` authorizes exactly the agent that would receive inbound from it — `channel_map[channel_id]` if mapped, else `default_agent`; for a DM target, the `default_agent` is the authorized sender and the peer must be on `allowlist.peers`. Refusals carry a clear error. One agent per conversation, in both directions; the channel map is thereby a send boundary for mapped channels, not routing-only. **"Speak first" is in-contract**: the agent may DM any allowlisted peer, including one it has never exchanged a message with — unprompted first contact is bounded by the allowlist, satisfying the mission's agent-initiated-send criterion. (DD-2 interaction, stated rather than inferred: a dangling `default_agent` after an agent rename means the send tool refuses all unmapped targets on that connector until the doctor-reported binding is fixed.) The tool resolves the manager → connector client → `send`, preserving visibility semantics via `tag_post_step_visibility` (`llm/base.py`); the `[platform-send-ok]` result-prefix contract is restored with it. Doctor warns when the bound agent lacks the tool.
- Rationale: honors "the agent loop is not modified"; without the check, any tool-enabled agent could reach any registered connector — untenable once Flight 4 gives one operator multiple connectors bound to different agents.
- Trade-off: an operator wanting a second agent to speak in a mapped channel must map it there — deliberate, symmetric with inbound.

**DD-5 — Session resolution resurrects the kept semantics, not the old module**: sessions key on the kept columns `(platform, connector_id, channel_id, COALESCE(thread_id,''))` with `peer_id` stored, honoring `session_continuation_seconds` and the `/new` `ended_at` sentinel. The resolver is rewritten small inside `inbound.py`, using the pre-reset `_session.py` (git history) as the reference for the reuse rules — behavior preserved, code not copied wholesale.
- Rationale: the keying and continuation window are two of the six kept pieces; the 197-line old module carried routing-era baggage the new pipeline doesn't need.
- Trade-off: subtle reuse-rule regressions are possible — covered by porting the old module's session tests' scenarios into the new tests.

**DD-6 — Reply policy is three conditions, no engine**: respond iff (a) `envelope.is_dm`, (b) `envelope.mentions_bot`, or (c) `channel_id ∈ always_listen` (explicit envelope flags per DD-1). `/new` is intercepted before dispatch (sole command; unknown `/foo` passes through to the agent as text).
- Rationale: mission criterion verbatim.
- Trade-off: none.

**DD-7 — Routes: seven, mirroring the provider-editor masking pattern**: `GET /api/connectors`, `GET/{id}`, `POST`, `PUT/{id}`, `DELETE/{id}`, `POST /{id}/test` (doctor), `POST /{id}/pairing-code`. Secrets masked with the established `__MASKED__` sentinel round-trip; encryption-rotation enrollment already holds (Flight 1 kept the SQL). DELETE stops the listener via the manager first.
- Rationale: smallest surface that makes the Studio form and doctor work; masking reuses the provider pattern verbatim.
- Trade-off: no status/observability endpoint this flight — doctor covers liveness; a richer status panel is Flight 5 (alignment) material if wanted.

**DD-8 — History tool calls an optional Protocol method**: `history(target, limit)` is optional on the Protocol; the last-N tool (`fetch_channel_history`, name preserved, ~40 lines) returns the platform's recent messages for the current channel/DM, or a clean "not supported" for plugins without it. Stub implements it trivially; Discord implements it in Flight 3.
- Rationale: mission Resolved Question 4; keeping it Protocol-optional stops Telegram/Flight 4 from being forced into it.
- Trade-off: none.

**DD-9 — Studio form: one file, within the remaining JS budget**: a `connector-editor` section registered like the other Studio sections — fields: name, type, enabled, token (masked), default agent (dropdown from the agents list), allowlist (peers + channels), always-listen channels, channel→agent map (simple key/value rows), doctor button, pairing-code button showing the generated code + expiry. Testids registered in `docs/ui-testid-registry.md` in the same leg (DD-7 discipline from Flight 1). Budget: the mission's ≤1,000 ceiling is measured at mission close as ALL connector-attributable JS — new files plus connector additions to shared files (`studio.js` section wiring, nav entry); this flight's ≤650 target is scoped the same way.
- Rationale: the old editor's 4,982 lines were ACL/routing/discoverable chrome; this is a CRUD form.
- Trade-off: no live-status polling, no discoverable dropdowns — deliberate.

**DD-10 — Acceptance via stub behavior test; apparatus audited on both axes**: behavior spec `stub-connector-round-trip` (authored this flight, draft at `tests/behavior/stub-connector-round-trip.md`) drives: create stub connector in Studio → generate pairing code → inject unknown-peer inbound (silence) → inject code (paired) → inject message (agent replies via stub) → operator types in the same session (never reaches stub) → agent uses send tool.
- **Act path**: a test-seam route `POST /api/_test/stub/inbound` **dual-gated** like purge-sweep — `settings.dev_mode` AND `THE_ONE_STUB_TEST_ENDPOINT=1` (second-pass design review 2026-08-31: this seam injects free text into a live agent loop with LLM calls and tool execution, purge-sweep's risk profile, not oauth/pending's inert-metadata one; the old `THE_ONE_REGISTER_STUB_CONNECTOR` name is fully absent and not resurrected) — consistent with the seam-hygiene rules from squawks 0020/0021; it injects inbound envelopes and the stub records outbound sends for reading. `GET /api/_test/stub/outbound` carries the same dual gate.
- **Observe path** (all existing or built this flight, cited): Chat UI unified history + visibility distinction (browser MCP — the two kept browser tests prove this surface renders); `GET /api/chat/sessions` for session keying fields (kept, `app.py` session projection); `GET /api/_test/stub/outbound` (new seam, same env gate) to assert what did/didn't reach the platform.
- Rationale: proves the whole contract without a live platform; the "operator message never reaches the platform" criterion is only honestly assertable via the stub's outbound record.
- Trade-off: two test-seam routes added — env-gated, swept by the existing seam-403 test conventions.

**DD-11 — Line budget is a leg-close checkpoint**: connector Python (package + both tools) counted at each leg's close against the ≤1,500 flight target; the mission's stop-and-split constraint applies. JS counted likewise against the ≤650 flight target.

### Prerequisites
- [x] Flight 1 merged to `main` (`138025e`); suite green (3,561 unit / four lanes)
- [x] Kept seams verified present on `main`: `Connector` model + `_CONNECTOR_TYPES ("discord","stub")`, `ConnectorRepository` CRUD (`db/repositories.py:632-724`), `ChatSession` keying fields + continuation semantics (`db/models.py:253-281`), `OPERATOR_VISIBILITY` + `tag_post_step_visibility` (`llm/base.py:147,:326`), rotation SQL over `connectors`
- [ ] Dev instance for behavior test: `THE_ONE_PORT=8485` + scratch `THE_ONE_DATA_DIR` with `dev_mode` on (never 8484 / default data dir). Note: the browser-test infra's `_spawn_app` allocates OS-random ports per run and is unrelated — the behavior test's manually-managed instance is not shared with it, by design
- [ ] Browser MCP (chrome-devtools) available for the behavior test's observe path
- [ ] No environment conflicts on 8485

### Pre-Flight Checklist
- [x] All open questions resolved (two design-review escalations settled by operator 2026-08-31: peer-keyed DM sends with allowlist-bounded first contact; dual-gated stub seam)
- [x] Design decisions documented (11 DDs; two Architect review cycles)
- [x] Prerequisites verified (dev-instance + browser-MCP items re-verified at execution start)
- [x] Validation approach defined (unit + lanes + `stub-connector-round-trip` behavior gate)
- [x] Legs defined (3: contract-core, routes-and-studio, behavior-gate-and-docs)

---

## In-Flight

### Technical Approach

Build order follows the dependency chain: contract core first (importable, unit-tested, stub-proven), then the HTTP/UI surface over it, then the end-to-end behavior gate. The old package at git ref `main~1^` (pre-Flight-1) is reference material for contracts being preserved (send tool semantics, session reuse rules, masking round-trip) — consulted, never copied wholesale. Config validation lives on the kept `Connector` model as one compact validator. `app.py` lifespan gains two small hooks (manager start after startup, manager drain in shutdown — placed so the MCP drain block `:396-418` is again untouched). Docs rewritten: `the_one/connectors/README.md` (the contract, ~short), the `agents.md` connector section, `README.md` architecture paragraph replacing the Flight-1 placeholder, `SECURITY-MODEL.md` connector wording.

### Checkpoints
- [x] Leg 1 lands: contract core + tools complete; stub round-trip covered in unit tests; `make test-unit` green; Python line count reported vs budget
- [x] Leg 2 lands: routes + Studio form + testid registry; all browser lanes green; JS line count reported vs budget
- [x] Leg 3 lands: `/behavior-test stub-connector-round-trip` passes (run 2, 7/7); docs rewritten; final line counts and lane results recorded

### Adaptation Criteria

**Divert if**:
- The Python count approaches 1,500 before the inbound pipeline is feature-complete — stop and split per the mission constraint rather than trimming admission/pairing correctness. **Leg 1 (`contract-core`) is the likely trip point** (design review 2026-08-31): it carries `manager.py` + `inbound.py`, whose pre-reset ancestors were the two heaviest modules (~1,231 and ~1,189 lines) even granting the ACL/routing/commands strip-out — watch its count mid-leg, not just at close
- Session-resolution parity with the pre-reset reuse rules can't be established from ported test scenarios — stop; the continuation window is a kept piece, not a rebuild candidate

**Acceptable variations**:
- Module boundaries within the package (merging `registry.py` into `base.py` etc.) if the result is smaller and clearer
- Studio form field layout/UX details within the testid + budget constraints

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `contract-core` - Protocol, registry, manager, inbound pipeline (admission/pairing//new/session/dispatch/reply policy), stub plugin, send tool + history tool re-attachment, config validator, lifespan hooks, unit tests, line-count checkpoint
- [x] `routes-and-studio` - Seven routes with masking, the two dev_mode-gated test seams (including the deliberate edit to `test_seam_routes_403_sweep.py`'s hardcoded `_EXPECTED_SEAMS` set — it does not auto-widen, by design), Studio form + testid registry + browser tests, JS line-count checkpoint
- [x] `behavior-gate-and-docs` - Finalize + run `stub-connector-round-trip` behavior test to pass, rewrite docs, final metrics

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification

- `make test-unit` and all four browser lanes green; no new skips/xfails.
- `/behavior-test stub-connector-round-trip` passes; run log committed.
- Line counts recorded in the flight log: connector Python ≤1,500 (flight) with the mission's 3,000 running total updated; connector JS ≤650 (flight) against the 1,000 ceiling.
- Masking round-trip: create/update with `__MASKED__` sentinel preserves the stored secret; rotation test still covers `connectors.secrets`.
- Greps: no `routing`, `acl`, `approval`, `engagement` terms in the new package or form; seam routes 403/absent outside the env gate (existing seam-sweep test extended).
