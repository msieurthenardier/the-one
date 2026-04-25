# Mission Debrief: LLM Provider Management

**Date**: 2026-04-25
**Mission**: [LLM Provider Management](mission.md)
**Status**: completed
**Duration**: 2026-04-23 → 2026-04-25 (~3 days, 5 work sessions)
**Flights Completed**: 5 of 5 (all landed and completed)

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| Users can add, edit, remove provider configurations through Admin | ✓ Met | F2 delivered the full CRUD UI; F4 added deletion protection |
| Multiple instances of the same provider type can coexist with distinct configs | ✓ Met | Validated in F1 backend, surfaced in F2 UI |
| API credentials encrypted at rest, key auto-generated, rotate function | ✓ Met | F1 baseline; F3 hardened rotation atomicity; F5 made rotation crash-safe end-to-end |
| Discovers available models by querying provider APIs after credentials verified | ✓ Met | F2 delivered model discovery; F4 unified the activate-refresh convention |
| Users can verify provider connectivity before saving | ✓ Met | F2 added the Test Connection button; F5 normalized the error taxonomy |
| Manages model loading on Ollama at runtime, concurrent models, VRAM warnings | ✓ Met | F3 delivered model lifecycle and VRAM-aware UX |
| Studio agent editor uses dynamic dropdowns | ✓ Met | F2 replaced free-text with provider/model selection |
| System degrades gracefully when provider unreachable / model unavailable | ✓ Met | F5 introduced session health classification + UI |
| First-start flow guides user to set up at least one provider | ✓ Met | F4 delivered the three-state setup banner |

### Overall Outcome

The mission delivered fully against its stated outcome. Per the user's debrief: *"I think we did it."* The system moved from env-var-cemented LLM config with three hardcoded provider classes to a fully data-driven, encrypted, per-instance provider registry with model lifecycle, health classification, and graceful UI degradation. None of the original 5-flight tentative breakdown had to be split, merged, or aborted.

The architectural baseline at mission close is markedly stronger than at mission start: encrypted credentials with crash-safe rotation, four provider types coexisting under a single config-to-runtime indirection, model lifecycle with VRAM awareness, health-classified UX, full removal of LLM env-var dependencies. The architectural debt accrued is mostly small and well-documented; the one structural item worth flagging upward (singleton DB connection lifecycle policy) was already present pre-mission and was held within tolerance, not made worse.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F1: Provider Data Model & Persistence | completed | Fernet encryption, `LLMProviderRepository`, schema v3, REST CRUD, key rotation, env-vars removed |
| F2: Provider Management UI | completed | Admin Integrations area with type-specific forms, model discovery, Test Connection; Studio agent editor migrated to dropdowns |
| F3: Ollama Model Lifecycle | completed | Native Ollama API integration; pull/delete/load/unload; VRAM monitoring; auto-load on chat start; rotation atomicity fix |
| F4: Agent Integration & Hardening | completed | Shared `App` namespace JS utils; URL normalization unified; provider deletion protection; first-start three-state banner |
| F5: Resilience & Verification | completed | Crash-safe key rotation; session health classification (`agent_deleted`, `provider_missing`); HAT-driven schema v5 + C-lite session reactivity; backend cleanup |

## What Went Well

- **Zero flight scope inversion.** Every divergence between flights was forward-evolutionary — F2 hardened F1's gaps, F3 consolidated F1/F2 plumbing, F4 extracted seams F2/F3 had been duplicating, F5 closed state-machine holes the prior flights had left open. No flight had to undo a prior flight's structural choice.
- **The `_PROVIDER_TYPE_MAP` indirection** (`factory.py:15-20`) is one of the strongest design moves in the mission. Bridging config-layer types to the runtime registry via a single dict — and intentionally aliasing `openai-compatible → ollama` rather than spawning a phantom provider class — kept the four-type system tight and tested.
- **Repository + injected Encryptor pattern** (`repositories.py:387-449`) made the encrypt-on-write/decrypt-on-read contract live at the storage boundary, so API-layer code never handled ciphertext except in the rotate endpoint (which had explicit reasons). Reuse-friendly, test-friendly, mirrors the four pre-existing repos.
- **Design-review-heavy methodology paid off in HAT.** Two-pass per-leg design review caught real correctness issues *before* implementation (e.g., F5 Leg 04 `test_update_preserves_masked_key` was passing for the wrong reason; the design review caught it). And F5's HAT caught two cross-layer bugs (FK CASCADE foreclosing `agent_deleted`; cached-Session snapshot blocking system-prompt edits) that no unit test could have surfaced. Both validate the per-leg design-review investment, not just optimistically running tests.
- **Test renames as documentation of intent shifts.** `test_cascade_delete_agent` → `test_agent_delete_does_not_cascade_to_sessions` (rename + invert assertion) makes the contract change reviewable and discoverable via `git blame`. Should be the standard pattern when a test's underlying intent reverses.
- **Mission-control-driven coordination held up across 5 flights.** Per user feedback: hierarchy was a help, not ceremony. Recent agentic-workflow churn-reduction (single review + commit at end of fast-variant) further cut friction without losing correctness or documentation.

## What Could Be Improved

### Process

- **Cross-cutting infrastructure audits** are missing from the leg-design template. Three of F5's HAT-caught bugs (FK CASCADE, cached snapshot, container-rebuild data wipe) lived outside any individual leg's stated scope — in schema, cache lifecycle, and deployment config. Mission-control updates committed locally (state-machine reachability + cache freshness audits) address two of these; verification-command declaration for `/flight` prerequisite checks (#4 from F5 debrief) is still pending.
- **Stale prerequisite numbers.** F5 asserted "All 325 tests passing on current main" — actual was 317 + 2 collection errors. Caught manually at flight start. The `/flight` skill should run `pytest --co` against the named base commit, not trust a number from a previous debrief.
- **HAT optionality is wrong for state-machine flights.** F5's HAT was nominally optional but caught two real bugs. Any flight that touches state semantics across DB/cache/UI layers should treat HAT as required.
- **Container data persistence was discovered during HAT, not pre-flight.** A `/preflight-check` item that verifies the project's data store is bind-mounted/named-volume'd would catch this once for any project with persistent state.

### Technical

- **Singleton `aiosqlite` connection** (`db/connection.py`) is a known constraint that's fine at single-user scale and bites the moment any feature wants concurrent transactions. F5 had to add explicit `conn.rollback()` to the rotation endpoint because the singleton would otherwise leak uncommitted writes. Document the constraint; revisit if multi-tenant is ever in scope.
- **`_sessions: dict[str, Session]` grows forever** with no eviction. The C-lite rebuild-in-place pattern means we can't simply remove the dict — needs an explicit lifecycle policy (idle TTL, max-size, or restart-on-deploy reset). Becomes urgent if anyone runs long-lived bot sessions.
- **`httpx.AsyncClient` per call** on the auto-load path runs every chat message. Flagged twice across mission debriefs (F3, F5 architect). At current usage volume the connection-pooling overhead probably isn't worth it; revisit if frequency increases.
- **Inconsistent error taxonomy between `test_provider` (200/`status:error` for upstream, 500 for unexpected) and `list_provider_models` (502 across the board for upstream).** Both shipped in this mission; F5 normalized one axis but the two endpoints stayed semantically uneven. Future maintainer will hit this difference and ask why.
- **`admin.js` and `studio.js` form-rendering conventions diverge.** F4 extracted the *utility* seam (`App` namespace) but the *form-rendering pattern* itself remained uneven. Studio is 822 lines, Admin is 1188 — the vanilla-JS micro-shell is starting to feel cramped. Not yet a problem; will be one if a third forms-heavy area appears.

### Documentation

- **`the_one/agents.md` should grow several sections** establishing invariants future contributors will otherwise re-discover painfully:
  - C-lite session reactivity contract (rebuild-on-rejoin, no mid-message propagation, system-prompt-from-config-not-from-DB at `app.py:226-233`)
  - Schema design notes for v5 (intentional non-FK on `chat_sessions.agent_name`, with the FK-CASCADE incident as a permanent case study)
  - Encryption section update for `__MASKED__` sentinel and crash-safe rotation order
  - Provider type extension checklist (model_dump enum, `_PROVIDER_TYPE_MAP`, `TYPE_DEFAULTS`, `test_provider` branch, etc.)
  - The `App` namespace as the canonical seam for shared frontend utilities
- **`CLAUDE.md`** should mention the `__MASKED__` sentinel — it's a magic string that any future developer touching the provider edit form needs to know about, currently buried in `admin.js` and `api.py`.
- **README/deployment doc** should note the `the_one_data` named volume requirement for docker-compose. Discovered during F5 HAT.

## Lessons Learned

### Technical

1. **Schema FK choices must be audited against the application-layer state machine that consumes them.** A `ON DELETE CASCADE` on a referencing column will silently delete the row your design needs to keep. The F5 v5 migration adding free-text `agent_name` (no FK) is the canonical case study.
2. **Cache freshness ≠ cache validity.** "The cached object works" is not the same as "the cached object reflects current source." The C-lite rebuild-on-join fix corrects a snapshot pattern that conflated the two.
3. **System-prompt-from-config is the right invariant** for Mission 03's mental model ("editing the agent should affect future messages"). DB-stored system messages are intentionally discarded on session restore; future contributors will try to "fix" this without context.
4. **Sentinel/display-string disambiguation requires test scrutiny.** A `startswith("***")` check that uses display-format strings as sentinels is silently bivalent — tests can pass for the wrong reason (the F5 `test_update_preserves_masked_key` bug).
5. **Typed exceptions are worth the small refactor cost** when application-layer logic needs to disambiguate exception sources. The F5 follow-up commit (`AgentNotFoundError` / `ProviderNotFoundError` / `ProviderNotConfiguredError`) eliminated brittle message-substring matching at the cost of three two-line class definitions.

### Process

1. **HAT for state-machine flights is non-negotiable.** Two of F5's three real bugs were unit-untestable — they required end-to-end interaction (delete agent in Studio → click session in chat) to surface.
2. **Test renames over delete-and-readd.** When a test's underlying contract reverses, rename + invert assertion produces git-blame-discoverable intent. `test_cascade_delete_agent` → `test_agent_delete_does_not_cascade_to_sessions` is the model.
3. **Inline fixes during HAT need bounded scope.** F5 spawned focused Developer agents for each HAT-caught bug rather than expanding into ad-hoc surgery. Schema migration v5 and C-lite reactivity both shipped under this discipline.
4. **Decision-as-record is load-bearing.** The flight log's `## Decisions` section captures *why* of choices that diverged from leg specs. Future operators find these without reading the whole log. Carry forward.

### Domain

1. **The agent abstraction is a "snapshot factory" by default**, and that's not what users expect. Users expect "talking to the agent" to reflect the current agent config. C-lite (rebuild on rejoin) is the minimum reactivity needed for join-boundary consistency; C-medium (per-step rebuild) is over-correction without a concrete driver.
2. **Conversation context biases small-model behavior.** F5 HAT initially looked like a system-prompt bug because Ollama models with established pirate-context wouldn't switch to gangster-context even with the new prompt — the LLM was correctly receiving the new system message but ignoring it under in-context priming. Larger models followed the new prompt. Worth a docs note for users.

## Methodology Feedback

- **The mission/flight/leg hierarchy worked.** Across 5 flights and ~3 work-days, the structure provided clean handoffs between planning and execution, made debrief-feedback-loops productive (F5 explicitly closed F1-F4 debrief items), and let the user trust the process without micromanaging.
- **Recent agentic-workflow simplifications** (single review + commit at flight close, fast variant) reduced churn without losing correctness or documentation. The user explicitly noted continued interest in further speed improvements that don't sacrifice rigor.
- **Two-pass per-leg design review caught real bugs.** Should be the standard for any state-machine or cross-cutting change.
- **HAT optionality should be re-evaluated.** Marking HAT optional for state-machine flights is a false economy.
- **Mission-control updates committed during this session** address two F5 debrief recommendations:
  - State-machine reachability audit added to `/leg` Phase 2 + flight-design Architect prompt
  - Cache freshness contract added to same locations
  - These are committed locally; will be evaluated in practice for a few missions before publishing.

## Action Items

### Immediate (next 1-2 sessions)

- [ ] Fix Concourse autopilot pipeline — `ci/pipeline.yml`'s `urlopen` call silently no-ops on `{"error": "session_*"}` responses. Either reconfigure the autopilot session with a valid agent, or surface `result.get("error")` and alert. ~5 min.
- [ ] Update `the_one/agents.md` with the documentation gaps listed above (C-lite contract, schema notes, encryption updates, provider extension checklist, App namespace).
- [ ] Update `CLAUDE.md` with the `__MASKED__` sentinel mention.
- [ ] Update README/deployment doc with the `the_one_data` named volume requirement.

### Near-term (small follow-up flights or bundled in maintenance)

- [ ] Refactor `LLMProviderRepository.get` to raise `ProviderNotFoundError` directly (push the typed exception down from the factory boundary to the storage boundary).
- [ ] Rename `_get_or_restore_session` → `_rejoin_session`. Two-line wrapper after C-lite; current name suggests caching semantics that no longer hold.
- [ ] Remove `Encryptor.rotate_key` dead code (test-only, harmless to keep but documentation rot risk).
- [ ] Schema migration tests for v_n → v_n+1 paths (currently only fresh-DB migration is tested; F5 HAT was the only verification of v4→v5).
- [ ] WebSocket protocol shape tests (`session_joined` always carries `status`, etc.). Currently relies on `grep` and HAT.
- [ ] Replace `assert db is not None` in `_build_session_joined_degraded` with `if … raise` (asserts are stripped under `python -O`).

### Mission-Control methodology

- [x] State-machine reachability audit added to `/leg` Phase 2 + flight-design Architect prompt (committed db8ac2d, holding for in-practice validation before push).
- [x] Cache freshness contract audit added to same locations (same commit).
- [ ] `/flight` prerequisite verification — implement project-aware verification commands (`.flightops/preflight.md` or new section in `ARTIFACTS.md`) so flight prereqs are run, not asserted.
- [ ] Reconsider HAT optionality — make HAT required for any flight touching state-machine semantics across DB/cache/UI layers.
- [ ] `/preflight-check` should verify any project with persistent state has a bind-mount or named volume configured.

### Conditional / future flights

- [ ] C-medium per-step rebuild — DEFER until a concrete driver appears (model auto-escalation per task complexity, dynamic tool grants, or user reports of confusing edit-doesn't-apply-to-current-message UX).
- [ ] Connection pooling for `aiosqlite` — DEFER until multi-tenant or concurrent-write workloads emerge.
- [ ] `_sessions` dict eviction policy — DEFER until long-lived sessions or memory introspection becomes a concern.
- [ ] `httpx.AsyncClient` connection reuse on auto-load path — DEFER unless usage frequency increases meaningfully.

## Mission-Level Known Issues at Close

These cross flight boundaries; future flights touching these areas must coordinate with them:

- **C-lite mid-message limitation** (`app.py:178-243`): edits to agent config don't propagate within an already-joined session, only at next rejoin. Boundary contract, not a bug.
- **System-prompt-from-config invariant** (`app.py:226-233`): DB-stored system messages are intentionally discarded on restore. Any feature with multi-system-message conversations or mid-conversation prompt overrides will need to revisit.
- **Singleton aiosqlite connection** (`db/connection.py`): no concurrent transactions. F5 rotation endpoint had to compensate with explicit rollback.
- **`_sessions` dict has no eviction policy** (`app.py:99`): grows monotonically.
- **Concourse autopilot accepts degraded session as silent no-op** until pipeline is reconfigured.
- **No automated test for v_n → v_n+1 migration paths**: regression risk on schema migrations.
