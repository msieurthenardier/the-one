# Flight Debrief: Connector Terminology Rename + Small-Housekeeping Fold-Ins

**Date**: 2026-05-29
**Flight**: [Connector Terminology Rename + Small-Housekeeping Fold-Ins](flight.md)
**Status**: completed
**Duration**: 2026-05-27 (planning kickoff) → 2026-05-29 (debrief; PR #80 draft)
**Legs Completed**: 3 of 3 (L1 backend-rename, L2 api-and-frontend-rename, L3 housekeeping-bundle) + 1 Phase 3 doc-sync commit

## Outcome Assessment

### Objectives Achieved

F11 landed the substrate rename `ConnectorAccount` → `Connector` across the operator-facing surfaces — Pydantic class, repository, SQLite schema (migration v23 row-rewrites parent table + 2 dependent tables + 2 indexes + JSON column), 14 API routes, 12 JS files across 4 selector families, 2 CSS files, 4 browser test file renames, 22 browser test selector sweeps, the `seed_connector` fixture rename, and 4 non-browser test files' hardcoded URL strings (151 occurrences). The 3 housekeeping items the F9+F10 combined debrief filed as F11-bound all landed: the `_acl.py` anachronistic deny block (both outbound + inbound) retired with parallel guilds/roles-axes phrasing; `the_one/agents.md` swept structurally (2 new M11 conventions promoted, per-axis-tri-state-override extended from 4 to 5 axes, 2 F9 API endpoint callouts added, F4-era prose pruned); `tests/test_provider_repository.py` async fixture redesigned, dropping the 13 teardown errors carried since F7.

The substrate landed as planned at the operator-touch layer, but the rename did NOT cover the Python snake_case identifier surface (~35 live function/method/class definitions, ~229 hit sites total). See "What Could Be Improved → Technical" and "Action Items" below.

### Mission Criteria Advanced

This flight closes no mission criterion directly. It is a substrate-stabilization flight inserted post-F9+F10 combined debrief; the rename aligns code vocabulary with operator mental model and the housekeeping closes carry-forward debt before F12 (hierarchical allowlist axes) adds further substrate surface. Indirect support for criterion #19 (daily-driver robustness): the asyncio teardown fix cleans the test-metrics signal so future debriefs detect regressions without 13 perennial-error noise.

### Checkpoints Met

All checkpoints across L1/L2/L3 + flight-level completion checklist flipped in the respective artifacts. The flight-spec leg checkboxes are all `[x]`; flight status flipped `in-flight` → `landed` at commit; this debrief flips `landed` → `completed`.

---

## What Went Well

**Architect cycles at flight design surfaced significant scope expansion before any leg executed.** Cycle-1 corrected the API route count (12 → architect found 12, plus 2 more F9 peer-approval routes for 14), corrected agents.md citations (5 → 13+), surfaced the FK column rename scope (~86 additional accessor sites), enumerated all 4 selector families (the L2 design's foundation), and reclassified the `test_provider_repository.py` asyncio fix as a fixture redesign rather than a surgical ordering tweak. Without cycle-1 the leg specs would have been materially incomplete.

**Per-leg Developer-as-Reviewer cycles (2 cycles each) caught 5 high-severity issues across the 3 legs** — all scope expansions necessary for atomicity, all caught at design review rather than discovered at implementation:
- L1: `the_one/connectors/README.md` missing from sweep; nuanced `test_db_migration.py` Category A/B rename strategy needed.
- L2: 4 non-browser test files with hardcoded URLs (54 — actually 151 — strings); `tests/browser/seeders.py` `seed_connector_account` rename with 22 callers; `the_one/db/models.py:495` docstring URL.
- L3: outbound `_acl.py:163-179` deny block (different string `"target is not a DM"`) + `tests/test_connector_send_tool.py:744-745` assertion (both missed by initial spec; symmetric to inbound but with distinct verbs/nouns per codebase convention).

**The L1/L2/L3 atomicity split worked cleanly.** L1 verified `git diff --name-only main -- 'the_one/interfaces/web/static/'` empty; L2 verified `grep -nE '"/connector-accounts' the_one/interfaces/web/api.py` zero; L3 verified `grep -rn "DMs-only override" the_one/ tests/` zero. Each leg's stated atomicity boundary held against verification.

**The "Notes for L2 designers" handoff pattern in L1's flight log was effective.** L1 explicitly flagged the 12 deferred `"Connector account not found"` API error-detail strings + the docstring URL path strings it deliberately preserved — L2's design picked them up natively, no rediscovery needed.

**`docker-compose.yml` discipline held.** Operator's local M11 F7 L12 HAT env vars (uncommitted `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL`) preserved out of all 4 F11 commits via `git add -u` + explicit `git restore --staged docker-compose.yml` discipline. Never used `git add .` / `-A` despite the temptation of a 100-file diff.

**Schema v23 re-entry guard** at `the_one/db/schema.py:1041-1148` (segment-level Python conditionals that skip rename ceremonies whose source table is missing OR whose target column is already renamed) was non-obvious correctness — handles the `TestSchemaV7::test_v7_strips_removed_tool_names` partial-shape re-entry scenario without conjuring `chat_sessions` / `pending_approvals` when those tables aren't seeded. Worth standardizing as a row-rewrite-migration pattern.

**The L3 housekeeping bundle's stated sub-item ordering (agents.md sweep FIRST, then surgical fixes) was right.** The prose changes shook out final rename residue before the deny-block + fixture-redesign edits landed; no late-stage drift surfaced.

**The agentic-workflow's defer-commits-to-Phase-2d shape served a 96-file diff well.** Reviewer (Haiku) verified the entire diff against acceptance criteria + grep gates in a single pass; commit landed as one coherent unit; PR diff is reviewable as a single semantic change rather than 3 partial states.

---

## What Could Be Improved

### Process

- **Recon-undercount discipline at flight design.** L1's "~280 Python sites" was close; L2's "~277 JS references" was close. But `test_db_api.py`'s hardcoded URL count was estimated at 10 and actually was **112** — order-of-magnitude miss. The miss surfaced only at L2's cycle-1 Developer review. **Recommendation**: when recon estimates a count for a `tests/` surface, run the literal grep and quote the actual figure (or actual+10%) — separate test-surface recon from production-surface recon rather than lumping them.

- **2-cycle design review caught most scope expansion but not all.** A 3rd cycle dedicated specifically to "run the flight's mechanical-verification grep against the live codebase and confirm the hit count matches the spec's expected scope" would have caught the snake_case identifier gap (see Technical below). Worth considering as a flight-design Phase 5c discipline for any flight whose verification gate is a grep pattern.

- **Operator's "8 shells running" intervention was a false alarm at the harness level** (no actual hanging tests; the indicator showed completed agent session entries). But the panic-then-diagnose flow worked well — diagnostic command from Bash tool confirmed `docker exec` / pytest process counts at zero, the panic resolved cleanly, the retry of the rejected implementing-Developer absorbed the prior agent's in-progress work. Worth a methodology note: when the operator surfaces a possible-hang signal, a short read-only diagnostic before any destructive remediation is the right shape.

### Technical

- **L1 grep-gate scope was too narrow.** AC #7's `git grep -E '\bConnectorAccount\b' the_one/ tests/` (PascalCase, word-boundary-both-sides) gave a clean 0-hit pass — but a wider grep `grep -rnE "ConnectorAccount|connector_account|connector-account|connectorAccount" the_one/ tests/` excluding `schema.py` returns **229 hits across 24 files including 35 live function/method/class definitions** that still carry the old vocabulary:
  - `the_one/db/repositories.py:89:async def list_by_connector_account` (called from `connectors/_inbound.py:364`, `interfaces/web/app.py:149`)
  - `the_one/tools/connector_history.py:526:async def _resolve_connector_account_context` (4 call sites in same file)
  - `the_one/interfaces/web/api.py` — 11 handler function names: `detach_agent_from_connector_account`, `_validate_connector_account_config`, `_connector_account_response`, `list_connector_accounts`, `list_connector_account_types`, `get_connector_account`, `create_connector_account`, `update_connector_account`, `delete_connector_account`, `generate_connector_account_pairing_code`, `list_attached_agents_for_connector_account`
  - 9 test classes: `TestConnectorAccountAPI`, `TestConnectorAccountConfigValidator`, `TestConnectorAccountPeerApprovals`, `TestConnectorAccountSessionContinuation`, `TestConnectorAccountRepository`, `TestConnectorAccountPairingCodeAndAttached`, `TestConnectorAccountDoctor`, `TestConnectorAccountRoundTrip`, `TestConnectorAccountConfigValidation`
  - Plus fixture `_seed_connector_account`, `test_rotate_connector_account_secrets`, `test_lifespan_warm_acquires_connector_accounts_per_account`, `test_fk_cascade_via_connector_account_delete`, 6 `test_list_by_connector_account_*` methods.

  This is **hybrid-vocabulary debt** — the exact pattern the flight's "Full Rename, No Back-Compat Shims" decision was designed to prevent. The decision held for one axis (no aliases) but failed on another (identifier-name surface). A future contributor reading `api.py` will see `async def create_connector_account(...)` returning a `Connector` and accessing `connector_id`. Filed to mission Known Issues; closes as F12 prereq per operator decision.

- **`idx_pending_approvals_account_peer_status` retains "account" in its identifier.** Flagged in the v23 migration comment as deliberate deferral ("index naming is internal SQLite metadata and not required for correctness here. L3 housekeeping is the appropriate venue if a cosmetic-rename pass is desired"). Same class of debt at a different surface; should fold into the same F12-prereq rename leg as the snake_case identifiers.

- **`aiosqlite` event-loop-closed teardown warnings (2 in the F11 backend rerun)** at `tests/test_db_migration.py::TestSchemaV17::test_v17_fresh_db_includes_agents_connector_ids_column` teardown. These are `PytestUnhandledThreadExceptionWarning`s from `aiosqlite/core.py` calling `loop.call_soon_threadsafe` after the test event loop closed — same root-cause family as the 13 errors L3 just fixed in `test_provider_repository.py` (sync fixture wrapping aiosqlite-open via `run_until_complete` under `asyncio_mode = "auto"`). Currently warnings; if a future pytest version promotes the class to errors, the migration test suite goes red. **Recommendation**: apply L3's fixture-redesign pattern in a near-term routine-maintenance pass or F12 prereq; grep `tests/` for the same sync+run_until_complete shape to enumerate the recurrence sites.

### Documentation

- **The README.md doc-sync was caught at Phase 3, not in the leg specs.** L1/L2/L3 didn't enumerate `README.md` as a touched surface; the Phase 3 documentation sweep found 2 stale `connector-account` references (lines 84 + 86) that became a separate commit (`d27ec1c`). Mostly fine — Phase 3 exists for this catch — but worth adding `README.md` to rename-flight checklists.

- **No mention in `CLAUDE.md` of the new F9 API endpoints** (until L3's agents.md sweep added them). The "must-know-before-touching" surface area for API endpoints lives in agents.md per L3 — but CLAUDE.md is the entry point for new contributors. Worth considering a 1-line pointer in CLAUDE.md to the agents.md API-endpoints subsection.

---

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L1's first implementing-Developer was rejected mid-stream (operator's "8 shells" panic) but had already written most files; retry absorbed the in-progress work seamlessly. | Harness rejection only halts the agent's reply; file edits persist. Retry pattern with explicit "already in-flight, don't re-flip status" framing closed cleanly. | Yes — codify that rejected implementing-agent work persists in the working tree and the retry should be aware of partial state rather than re-doing from scratch. |
| L2's recon undercounted `test_db_api.py` URL strings by 10x (estimated 10, actual 112). | Recon greps were not run literally against `tests/` separately from production code. | Yes — separate test-surface recon from production-surface recon; quote actual+10% as the spec's expected upper bound. |
| L3's `_acl.py` retirement was initially specced as 1 deny block (inbound only); cycle-1 surfaced the symmetric outbound block + `tests/test_connector_send_tool.py:744-745` assertion. | Initial recon focused on `admits_inbound`; `admits_outbound`'s parallel `agent_channels == []` branch and its DIFFERENT deny string (`"target is not a DM"` vs `"envelope is not a DM"`) wasn't enumerated. | Document the "two symmetric ACL paths (inbound + outbound) with parallel per-agent branches" as a substrate-shape note in agents.md; future ACL changes should touch both unless one is explicitly deferred. |
| L1's grep-gate AC scope was the PascalCase + column-accessor pattern only; snake_case function/method/class names were neither in-scope nor explicitly deferred. | The trade-off was made implicitly (the schema.py comment about index names shows the architect had the half-thought) but never elevated to a flight-level design decision. | **Critical**: rename flights' gate-grep patterns must be enumerated explicitly in the spec; surfaces the grep does NOT cover must be listed as "in-scope-additions" or "deliberately deferred — operator-confirmed cosmetic-only debt". |
| Phase 3 documentation sweep produced a separate commit (`d27ec1c` README doc-sync). | Leg specs didn't enumerate `README.md`. | Standardize: add `README.md` + `CLAUDE.md` to rename-flight checklists; spec one of the legs as the doc-sync home rather than catching at Phase 3. |

---

## Key Learnings

**Grep-gate scope is a flight-level design decision, not an implementation detail.** When the AC says `git grep <pattern>` returns 0, the spec is making a claim about which surfaces are guaranteed renamed and which are silently excluded. The trade-off (renaming `list_by_connector_account` ripples into 3 call sites + 6 docstring citations vs leaving it in hybrid vocabulary) is the kind of choice that should be in the Design Decisions section, not buried in regex word-boundary semantics. F11's `\bConnectorAccount\b` pattern made the hybrid-vocabulary choice implicitly across 35 definitions and ~229 sites.

**Two-symmetric-paths is a recurring substrate shape in `the_one/connectors/_acl.py`.** The outbound `admits_outbound` and inbound `admits_inbound` are mirror images at the per-agent block. Every leg touching ACL semantics has had to handle both (F8 L8 per-agent guilds/roles, F10 L1 dm_admission, F11 L3 deny-message retirement). Worth a substrate-shape note in agents.md so future ACL-touching legs default to enumerating both directions at recon.

**The atomic-leg-pattern + atomicity-boundary verification compose well at flight scale.** F11's 3-leg split with explicit atomicity-boundary checks at each handoff (verified by `git diff --name-only` against specific path prefixes) caught zero cross-contamination. The transient hybrid-vocabulary state between L1 and L2 (backend says `Connector`, URLs still say `connector-account`) lasted only across leg boundaries within a single flight branch — by the time the diff was reviewed, the hybrid had collapsed.

**Recon estimates for test surfaces are systematically optimistic.** `tests/` URL hardcoding counts undercounted by 10x; agents.md citation counts undercounted by 2-3x; JS reference counts undercounted by 10x at debrief but corrected at architect cycle-1. Pattern: production-code recon is close; test-surface + documentation-surface recon needs separate dedicated greps.

**Architect cycle-1 + Developer cycle-1 reviews are necessary AND together sufficient for caught-at-design-time scope issues at this flight scale** — but only when the recon discipline at flight design includes running the spec's verification grep against the live codebase. F11 didn't include that step; surfaces excluded by the grep's regex went unsurfaced until debrief.

**`docker-compose.yml`-style operator local state is preservable across multi-file commits with discipline.** Explicit `git add -u` + targeted `git add` of new untracked files + `git restore --staged` for any local-state file kept the operator's HAT env vars out of all 4 F11 commits. Worth codifying as a methodology note for any flight in a working tree with operator local state.

---

## Recommendations

1. **Codify "grep-gate-scope-is-a-design-decision" as a flight-design discipline.** For any flight whose AC includes `git grep <pattern>` returning N hits (typically 0), the spec must enumerate the surfaces the grep does NOT cover and explicitly mark them in-scope or deferred. Worth a 1-line addition to the `/flight` skill's "Acceptance Criteria" guidance.

2. **Add a Phase 5c architect cycle for grep-gate flights**: dedicated cycle that runs the spec's verification grep against the live codebase, records the hit count, and compares against the spec's expected hit count. Cycle-3 is justified only when this gap is real and the trade-off needs operator input.

3. **Add `README.md` and `CLAUDE.md` to rename-flight checklists**, with one of the legs explicitly owning the doc-sync. F11's Phase 3 catch worked, but the sweep should be in-scope from the start.

4. **Codify two-symmetric-paths-in-ACL substrate shape in agents.md**: any change to `admits_inbound` likely needs the symmetric change to `admits_outbound` (and vice versa). The flight's L3 cycle-1 finding made this concrete; pin as a named convention so the recon discipline is part of the substrate's documented shape.

5. **Apply L3's fixture-redesign pattern to remaining sync-fixture-wrapping-aiosqlite sites**, either as a near-term routine-maintenance pass or as an F12 prereq sub-step. The `aiosqlite` event-loop-closed warnings will become errors at some future pytest-asyncio version; the migration test suite's signal cleanliness benefits from closing the latent flakiness vector.

---

## Action Items

- [x] **Mission outline updates**: Flight 11 marked `[x]` in `mission.md`; flight status flipped `landed` → `completed`; carry-forward filed to mission Known Issues.
- [ ] **F12 prereq fold-in (operator-confirmed)**: complete the snake_case identifier rename as an atomic leg in F12's outline — `SQLiteAgentStore.list_by_connector_account` → `list_by_connector` (+ 3 production call sites + 6 docstring citations); 11 `_connector_account*` API handler names in `the_one/interfaces/web/api.py`; `_resolve_connector_account_context` + 4 call sites in `connector_history.py`; 9 test classes + fixture + test methods; `idx_pending_approvals_account_peer_status` index name. ~30 def renames, ~229 hit sites total. Mechanical; no behavior change.
- [ ] **Near-term routine-maintenance or F12 sub-step**: apply L3's async-fixture-redesign pattern to `tests/test_db_migration.py` (and any other sync-fixture-wrapping-aiosqlite sites surfaced by `grep -rn "run_until_complete\|get_event_loop" tests/`); close the `aiosqlite` event-loop-closed warning class before it becomes an error.
- [ ] **Pre-existing browser test failures**: `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` (expects 4 tabs, sees 5) and `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` are unaddressed on `main` since before F10. Tip-off that browser-test assertions drift as the UI evolves. File as routine-maintenance candidate or fold into the next browser-touching flight.
- [ ] **Methodology improvements (flight director-side)**: codify the 5 recommendations above into the `/flight` and `/leg` skill guidance for the next mission-control commit.

---

## Test Metrics

| Metric | F8 land | F9 land | F10 land | **F11 land** |
|--------|---------|---------|----------|--------------|
| Backend tests passed | 2669 | 2721 (+52) | 2733 (+12) | **2749 (+16)** |
| TestSchemaV23 (new) | — | — | — | +3 |
| `test_provider_repository.py` previously-erroring | 0-13 (intermittent) | 13 | 13 | **0 (fixed by L3 fixture redesign)** |
| Browser tests passed | — | +6 | +7 | **431 (no F11 additions; selector-sweep only)** |
| Backend skipped | 4 | 4 | 4 | 4 |
| Backend errors | 0-13 (intermittent) | 13 | 13 | **0** |
| Backend wall-clock (full suite, no `-x`) | ~150s | ~250s | ~257s | **254s** |
| Browser wall-clock | — | — | — | ~530s |
| Browser failures | — | — | 0 | 2 (both **pre-existing on `main`, not F11-caused**) |
| New flakes observed | — | — | Zero | Zero |
| `aiosqlite` event-loop-closed teardown warnings | — | — | — | 2 (warnings, not errors; same root-cause family as L3-fixed) |

Wall-clock at 254s tracks F10's 257s baseline within noise (−1.2%). The 13 carried errors flipping to 0 is the cleanest signal: the asyncio fixture redesign closed a chronic carry-forward without behavior change.

---

## Methodology Feedback

**`/agentic-workflow` defer-commits-to-Phase-2d worked at this scale.** 96 files / 3972 ins / 1875 del landed as a single atomic commit covering all 3 legs. Reviewer (Haiku) verified the full diff against acceptance criteria + grep gates in a single pass. PR reviewer sees one semantic change, not 3 partial states. The pattern scales.

**`/flight-debrief` single-flight default fit F11 cleanly.** F11 was a standalone flight (not a partial-HAT continuation like the F9+F10 combined debrief), so the default single-flight debrief shape was right. The combined-debrief shape from F9+F10 remains a valid one-off adaptation when partial-HAT findings directly drive a followup flight's scope.

**The cycle-1+cycle-2 design review cap held cleanly** — each leg had a cycle-1 finding that warranted cycle-2 verification, no cycle-3 was needed at any leg. The "consistency-only cycle-3 not needed" pattern from the F9+F10 debrief was respected (no cycle-3 spawned anywhere in F11).

**Operator's mid-flight interventions added value disproportionate to their cost.** The "8 shells" intervention surfaced a harness-UI-versus-real-process disambiguation (no actual hanging tests), and the read-only diagnostic before any destructive remediation avoided wasted work. Worth a methodology note: when operator surfaces a possible-hang signal, the first move is a read-only Bash diagnostic (`ps auxf`, `docker ps`), not an aggressive cleanup.

**Partial-implementer-rejection-then-retry pattern is a real failure mode.** When the operator rejected the first implementing-Developer mid-stream (after substantial file edits had already landed), the retry Developer found and integrated the in-progress work without re-doing it. This is preservable behavior — the harness rejection only halts the response, not the file edits — and the retry's prompt language ("don't re-flip status; absorb prior work") made it explicit. Worth codifying as an implementing-leg-Developer prompt template hint for any rejected-and-retried orchestration.
