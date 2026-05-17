# Flight Debrief: Connector Plugin Contract and Lifecycle Foundation

**Date**: 2026-05-16
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](flight.md)
**Status**: landed (transitioning to `completed` after this debrief)
**Duration**: planning → ready (cf17f40, 2026-05-16) → in-flight → landed (f687187, 2026-05-16)
**Legs Completed**: 8 of 8

## Outcome Assessment

### Objectives Achieved

The flight's stated objective — "stand up the connectors subsystem as a peer to `the_one/mcp/` and `the_one/tools/`, ship the SDK and a no-op stub that exercises the entire contract end-to-end so subsequent flights only fill in platform specifics" — is met. The deliverables:

- New package `the_one/connectors/` (7 files) with the 4-method `ConnectorPlugin` Protocol, 1-method `ConnectorClient` Protocol, 4 frozen-slotted supporting dataclasses, 6 typed exceptions, the type registry, the per-(agent, account) lifecycle pool with idle-TTL reaper and `shutdown_drain`, and the in-process stub plugin.
- v13 + v14 schema migrations: `connector_accounts` table with encrypted secrets; the `name` column landed in v14 (caught at leg-2 planning — discussed below).
- Rotation transaction at `interfaces/web/api.py:rotate_encryption_key` extended to cover three corpora atomically (LLM api_key + MCP secrets + connector_accounts secrets); rollback test pins the all-or-nothing semantics.
- FastAPI lifespan extended; drain order locked at `pty → mcp → connector → oauth → db` (regression test in `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order`).
- Documentation: connector-type six-layer coordination checklist in `agents.md` (parallel to provider-type); Connector subsystem decisions section in `agents.md`; new `connectors/README.md` paralleling `mcp/README.md`.
- 72 new tests; 0 regressions; ~9,464 line insertions across 32 files in one commit (`f687187`).

### Mission Criteria Advanced

This flight is foundational — it advances every "Contributing to Criteria" bullet in `flight.md`. Coverage as confirmed by the end-of-flight Reviewer:

| Criterion | How advanced |
|---|---|
| "Single connector-plugin contract that is the only file any future connector author needs to satisfy" | `connectors/base.py` ships `ConnectorPlugin` + `ConnectorClient` Protocols; future `AllowlistResolver` and `CommandHandler` (Flights 6/7) will land in the same file |
| "Per-connector-account override of credentials supported through the resolver pattern" | `connector_accounts` table + `ConnectorAccountRepository` with reference-not-copy encryptor; rotation propagates via `install_key` |
| "Credentials never appear in plaintext outside the encryption boundary" | Rotation extended to three corpora atomically; rollback test verifies; `_ciphertext_to_secrets` tolerantly handles `InvalidToken` (migration residue) without exposing plaintext |
| "Persistent connections managed by per-(agent, connector-account) lifecycle pool with idle-TTL reaping and transparent respawn, integrated into FastAPI lifespan" | `connectors/_pool.py` + lifespan wiring in `interfaces/web/app.py` |
| "Failures isolated to the connector layer ... do not take the chat session down" | 6-type exception hierarchy; idempotent-pop-on-failure in `acquire` verified by `test_concurrent_acquire_with_failure_pops_once` |
| "Each layer ... automated coverage proving its contract" | `tests/test_connectors_e2e.py::test_e2e_full_lifecycle` is the regression baseline Flights 2-10 inherit |

## What Went Well

- **M07's `_shutting_down` lesson applied from day one.** The connector pool ships without the test-isolation debt M07 carries — `_clear_for_test` resets `_shutting_down = False` AND `_reaper_task = None`. Architect verification: "structurally cleaner than MCP's." The fix is captured in agents.md Known Issues to ensure future flights respect it.
- **4-method `ConnectorPlugin` Protocol scope held.** The decision to defer `AllowlistResolver` and `CommandHandler` to Flights 6/7 as separate Protocols in the same file (rather than pre-committing all 6 methods on a single Protocol) preserved Flights 6/7's design freedom. Architect: "the right compromise on 'single contract file'."
- **Per-leg design review caught real bugs early.** The Developer-as-Reviewer cycle surfaced: dataclass-hashability with dict fields (leg 3), incorrect failure-injection test pattern (leg 1), registry-class YAGNI tightening (leg 4), missing `isinstance` defensive check in `resolve()` (leg 4), missing `name` column on `connector_accounts` (leg 2), `_connection` singleton reset for e2e isolation (leg 7). Each would have been a debug session later; each was caught at design-review time.
- **8-leg granularity was the right cut.** Specifically the leg-5/6 split (pool core vs reaper-and-drain) — leg 5 left `ttl_seconds=0` as a placeholder with an explicit handoff-signal test (`test_entry_ttl_seconds_placeholder_is_zero`); leg 6 flipped the test and locked the new contract. The handoff was clean.
- **Test trajectory: 1705 → 1774 (+69 tests, 0 regressions).** Lint clean throughout. Every per-leg run kept the full suite green before signaling `[HANDOFF:review-needed]`.
- **Documentation completeness.** `agents.md` gained the connector-type six-layer coordination checklist parallel to the provider-type one, plus the Connector subsystem decisions/invariants section with named Known Issues. `connectors/README.md` mirrors `mcp/README.md`. Future flights have anchored entry points.
- **End-of-flight batch review caught one drift.** Reviewer flagged a stale "v14 table-rename" reference in `_connector_types.py:12` (everywhere else had been renumbered to v15 after leg 2's name-column ALTER). Fixed inline before commit.

## What Could Be Improved

### Process

- **Pre-flight column-by-column mirror review missed the `name` column.** The flight's Technical Approach said `ConnectorAccount` would "mirror MCPSource shape" without enumerating columns; the v13 schema author shipped without `name`; leg 2 caught it and bumped to v14 + renumbered Flight 8's CHECK from v14 to v15. **Recommendation**: when a flight criterion says "mirror $existing_thing's shape," the architect's flight-design pass should produce a column-by-column / method-by-method mirror table as part of the review output.
- **Leg-7 fixture-path bug** (`tmp_path / "e2e.db"` vs `settings.db_path`) was a leg-spec quality issue, not an implementation surprise. The leg author wrote code samples touching `settings.data_dir` indirection without verifying the resolved path. **Recommendation**: leg authors must verify `settings.*` indirection resolutions when writing fixture code samples — `settings.db_path` is computed from `settings.data_dir`, not arbitrary.
- **Lifespan-wiring scope ambiguity.** The flight spec's leg-6 bullet said lifespan integration "documented in code but wired into `app.py` only in Flight 2"; the leg-6 artifact then required the wiring this flight, and the implementer correctly followed the leg. The flight.md text is now inconsistent with what shipped. **Recommendation**: when a leg artifact supersedes a flight bullet, patch the flight artifact at the supersession point — flight log alone is not enough.

### Technical

- **Encryption envelope is duplicated byte-for-byte** between `MCPSourceRepository._secrets_to_ciphertext`/`_ciphertext_to_secrets` (`db/repositories.py:301-326`) and `ConnectorAccountRepository._secrets_to_ciphertext`/`_ciphertext_to_secrets` (`db/repositories.py:456-479`) — 25 LoC × 2 = 50 LoC of pure duplication. **Recommendation**: lift to a shared `_encrypt_secrets_blob(encryptor, secrets) → str` / `_decrypt_secrets_blob(encryptor, ciphertext) → dict` pair in `db/repositories.py` before Flight 2 ships the admin REST surface (which would otherwise reproduce the pattern a third time on validation paths). Small, safe, 30-LoC refactor; behaviour-preserving.
- **`_evict_all_for_account` is shipped but not yet wired into rotation.** A warm pool entry whose plugin already pre-decrypted secrets and cached plaintext in its `ConnectorClient` would operate with stale credentials after rotation until idle-TTL eviction (30 min default). **Recommendation**: Flight 2 wires `await _evict_all_for_account(account_id)` for every connector_account in the rotation transaction. The per-account credential update path also needs it.
- **Untested edge cases** that matter for downstream flights:
  - **Rotation-while-pool-warm** — no test asserts `acquire → install_key → acquire (different account) → second acquire uses new key`. Flight 2's rotation surface should add this.
  - **Concurrent `shutdown_drain` + `acquire`** — if `acquire` is mid-`await _load_account()` (outside lock) and `shutdown_drain` fires, the in-flight acquire raises `RuntimeError` at the next lock acquisition. Correct behaviour, but unasserted.
  - **Reaper sweep during `shutdown_drain`** — gather-evict idempotence under double-firing isn't tested.
- **`last_activity` semantics rely on an unratified assumption.** `_RegistryEntry.last_activity` tracks "time since last `acquire()`," not "time since last platform activity." If Flight 3's inbound dispatcher caches `ConnectorClient` references outside the pool, the reaper will prematurely evict actively-used gateway connections. Already captured as Known Issue in `agents.md`; Flight 3 must ratify per-acquire-touch OR add an explicit `touch_activity(key)` API.
- **Function-local-import-to-break-load-cycle is now a 3-occurrence pattern** (mcp/_pool.py:196 for OAuth; db/repositories.py:398 for cache_cleanup; connectors/_pool.py:158-167 for repositories). **Recommendation**: codify as a named project convention in `agents.md`'s "Project Conventions" section.

### Documentation

- **`connectors/README.md` is missing a skeleton plugin example.** §3 says "real connectors will satisfy this Protocol" without sketching one. A 30-line "Skeleton for a Flight 8 plugin" code block would materially help Flight 8's first leg.
- **The `last_activity` index is missing from agents.md.** The Connector subsystem section explains the semantics but doesn't say where it's touched (`acquire`'s return block). One-line addition.
- **Flight 2 leg artifacts must explicitly cite the `__MASKED__` sentinel contract.** `repositories.py:447` documents that the repository deliberately doesn't handle it; Flight 2's admin REST routes own the API-edge implementation. Easy to miss without the citation.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| **Leg 2**: v14 ALTER added `name` column not anticipated by flight design | Mission criterion said "mirror MCPSource shape"; v13 schema omitted `name`. Caught at leg planning by reading MCPSource. Flight 8's CHECK migration renumbered v14 → v15. | **Yes** — architect's flight-design pass should produce explicit mirror tables for "mirror $existing" criteria |
| **Leg 5**: function-local DB imports in `_load_account` | Circular import surfaced at runtime: `_pool` → `db.repositories` → `agent` → `mcp.__init__` → mid-loading `db.repositories`. Mirrored `mcp/_pool.py:196`'s pattern. | **Yes** — third occurrence; codify as named convention in agents.md |
| **Leg 6**: lifespan wiring superseded "deferred to Flight 2" flight bullet | The leg spec required wiring; the function and its wiring belong together. Flight log documents the supersession; flight.md leg-6 bullet should be patched. | No (one-off) — but update flight.md to match what shipped |
| **Leg 7**: `tmp_path / "e2e.db"` → `settings.db_path` fixture fix | Leg author wrote arbitrary path; `get_connection()` resolves `settings.db_path = data_dir / "the-one.db"`. Schema written to wrong path was invisible to `get_connection`. | **Yes** — leg authors must verify `settings.*` indirection resolutions in fixture code samples |
| **Leg 7**: aiosqlite `close_connection()` in fixture teardown | Without it, the per-connection worker thread leaks; `RuntimeError: Event loop is closed` on later `call_soon_threadsafe`. Not predictable from flight design — execution-time discovery. | No — document in flight log; future tests inherit the pattern |
| **Pre-existing brittle tests patched** (`TestSchemaV8` hardcoded `CURRENT_VERSION == 12`; `TestMigrationV12` rewind only `=12`; `TestSchemaV13` column-set asserted v13 columns when v14 added `name`) | Each is a regression-loud-fail guard explicitly designed to fail on schema bump. Expected. | No — the brittle-loud-fail guards are working as designed; tracked in flight log under "Expected-and-tracked brittle-test updates" |
| **End-of-flight Reviewer caught `_connector_types.py:12` doc drift** (v14 → v15) | Other files updated during leg 2; this file's docstring missed the renumber. Fixed pre-commit. | No (one-off) — caught by the existing review cycle |

## Key Learnings

- **"Mirror $existing" mission criteria need column-by-column / method-by-method enumeration at flight-design time.** The v14 name-column miss is the canonical example. Architect's flight-design pass for any "mirror" criterion should produce a comparison table.
- **Per-leg design review with a fresh Developer agent catches real bugs early.** Pre-implementation review surfaced ~7 substantive issues across legs 1-7 that would otherwise have been debugged post-implementation. The pattern is paying for itself.
- **M07 test-isolation lessons are cheaper to apply on greenfield than to retrofit.** Connector pool ships clean; MCP pool's debt remains. Validate the assumption: the connector pool's `_clear_for_test` is now the canonical shape to retrofit MCP to during the eventual paydown flight.
- **Schema version renumbering must propagate everywhere.** The end-of-flight Reviewer caught one stale v14 reference in `_connector_types.py` after leg 2's renumber. Future flights renumbering migrations should add a renumber checklist: every docstring, every README, every flight-spec section.
- **The "single contract file" mission criterion is about the file, not the Protocol count.** Multiple Protocols in one `base.py` satisfy it. This frames the right boundary for Flights 6/7's additive Protocols.
- **Test metrics**: 1705 → 1774 (+69) in this flight; 1376 → 1774 (+398) since M07 F8 (Oct → now). Wall-clock 72.38s → 100.58s (+28s). Throughput essentially flat (17.6 vs 19.0 tests/s). No evidence of suite-wide slowdown; growth is dominated by new feature coverage. The 2 pre-existing `AsyncMock-never-awaited` warnings on `test_provider_api.py::TestModelDiscovery::test_ollama_models` persist from M07 and are owed a fix outside this flight.

## Recommendations

1. **Lift the Fernet envelope to a shared helper in `db/repositories.py`** before Flight 2 ships. `_secrets_to_ciphertext` / `_ciphertext_to_secrets` are byte-identical across `MCPSourceRepository` and `ConnectorAccountRepository` — 50 LoC of pure duplication. 30-LoC refactor; behaviour-preserving; prevents a third repetition when Flight 2 lands.
2. **Flight 2 must wire `_evict_all_for_account` into rotation AND per-account credential updates.** Without this, warm pool entries with cached plaintext secrets survive rotation by up to the idle TTL (30 min).
3. **Add a column-by-column mirror review step** to the architect's flight-design pass for any criterion that says "mirror $existing." The v14 name-column miss would have been caught upfront.
4. **Codify `function-local-import-to-break-load-cycle` as a named convention** in `agents.md`'s Project Conventions section. Three occurrences now; pattern is stable.
5. **Flight 3 must ratify the `last_activity` per-inbound-acquire contract.** The Known Issue in `agents.md` is the carry-forward; Flight 3's design must either commit to acquire-per-inbound semantics or add an explicit `touch_activity(key)` API.

## Action Items

- [ ] Patch `flight.md` leg-6 bullet to reflect that lifespan wiring shipped this flight (was "deferred to Flight 2")
- [ ] Add `function-local-import-to-break-load-cycle` convention to `the_one/agents.md` Project Conventions section
- [ ] Lift `_secrets_to_ciphertext` / `_ciphertext_to_secrets` to a shared helper in `db/repositories.py` (pre-Flight-2 maintenance work)
- [ ] Flight 2 leg artifact: include `_evict_all_for_account` wiring in rotation + per-account credential updates as explicit acceptance criteria
- [ ] Flight 2 leg artifact: cite the `__MASKED__` sentinel contract at `db/repositories.py:447` so API-edge implementation isn't missed
- [ ] Flight 3 leg artifact: include `last_activity` per-inbound-acquire ratification as a Design Decision (or amend with `touch_activity(key)` API)
- [ ] Flight 4 leg artifact: note the `ConnectorClient` Protocol-widening pattern for the outbound-send method (additive, structural-satisfaction non-breaking)
- [ ] Flight 10 (hardening) leg list: add untested edge cases — rotation-while-pool-warm, concurrent `shutdown_drain` + `acquire`, reaper sweep during `shutdown_drain`
- [ ] Add a "Skeleton for a real plugin" code block to `connectors/README.md` §3 (Protocol decomposition) before Flight 8 begins
- [ ] Fix the 2 pre-existing `AsyncMock-never-awaited` warnings on `test_provider_api.py::TestModelDiscovery::test_ollama_models` (carries forward from M07; not this flight's debt to clear but worth a maintenance ticket)
