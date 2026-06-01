# Flight Debrief: Audit-log inspector + per-connector inference config + slash-command HAT

**Date**: 2026-06-01
**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](flight.md)
**Status**: landed (transition to `completed` pending operator confirmation)
**Duration**: 2026-05-31 → 2026-06-01 (single intensive session)
**Legs Completed**: 6 of 6 (L1-L5 clean; L6 PARTIAL — completed-with-deferral)

## Outcome Assessment

### Objectives Achieved

F13 closed two of its three M11 mission criteria cleanly and surfaced the substrate work needed to close the third:

- **Criterion #12** (mentions-aware response policy operator surface) — **CLOSED.** L1-L4 relocated inference LLM configuration from `Settings.inference_*` (env-var, no UI) onto `connector.config.inference_provider_config_id` + `inference_model` (per-connector, Studio UI). The L4 post-land enhancement added a provider-aware model dropdown sourced from `GET /api/providers/{id}/models` with `(custom)` fallback for persisted-but-not-enumerated values, mirroring the chat agent-editor's pattern. Verified end-to-end via `/behavior-test connector-inference-provider-config-roundtrip` (PASS 8/8 on `2026-05-31-23-56-31`).

- **Criterion #15** (audit-log inspector) — **CLOSED.** L5 shipped the Chat UI per-session Routing audit collapsible panel below the message list. Backend exposes `session_metadata` via the `GET /api/chat/sessions/{id}` detail endpoint (only — shared `_session_summary()` helper untouched) AND both WS `session_joined` payload builders (`_build_session_joined_ok` + `_build_session_joined_degraded`). Per-entry expansion renders raw fields including nested `policy` dict for `policy-silent` dispositions; 4 disposition badge classes (stepped/command-intercepted/no-eligible/policy-silent) with distinct color tokens. Verified end-to-end via `/behavior-test audit-log-inspector-renders-routing-entries` (PASS 7/7 on `2026-05-31-23-56-31`).

- **Criterion #10** (slash command verification) — **STAYS OPEN.** L6 HAT walk surfaced four pre-existing ACL/slash-sync defects that BLOCK a full HAT pass; filed as a single cluster Known Issue for the follow-on flight. `/whoami` confirmed PASS (operator post-HAT); `/new` + `/reset` expected PASS (don't use `_permitted_agents`); `/agents` + `/talk_to` BLOCKED on Bug D; `/help` expected PARTIAL.

### Mission Criteria Advanced

| # | Criterion | Status pre-F13 | Status post-F13 |
|---|-----------|---------------|-----------------|
| #10 | All 6 slash commands validated against real Discord | `[ ]` | `[ ]` (3 of 6 verified or expected PASS; 2 BLOCKED on cluster; 1 PARTIAL) |
| #12 | Mentions-aware response policy operator surface | `[ ]` | `[x]` |
| #15 | Audit-log inspector | `[ ]` | `[x]` |

Plus three F12 carry-forward debrief items folded into L1+L2:
- Shared test-fixture translator module `tests/_acl_shape_helpers.py` (L1)
- Two new `agents.md` M11 conventions (`column-aware-index-create-for-rewind-paths`, `test-translator-helpers-for-shape-evolution`) (L1)
- Per-agent `peers[*].dm_allowed` footgun retirement via v26 migration + strict Pydantic validator (L2)

## What Went Well

- **L2/L3 split (architect cycle-1)** — Splitting substrate (v26 migration + Pydantic validators) from runtime (Settings removal + dispatcher refactor + test_connectors_inference.py rework) gave each leg its own atomicity boundary while preserving the v26 commit-boundary dependency via Phase 2d batched commit. Each leg was independently reviewable. This pattern should be a named convention for flights where one substrate change implies large test-module cull/rewrite work.

- **L1's mechanical-prereq-leg discipline paid off twice** — Once at L1 (extracting `tests/_acl_shape_helpers.py` consolidating helpers from 4 files, structural no-op preserved 2783 baseline), then again at L2 when retiring per-agent `dm_allowed` required a one-helper edit instead of 4 file edits. Second-degree validation of the F11/F12 `mechanical-prereq-leg-before-semantic-changes` convention.

- **L5's routing-audit panel earned its keep at L6 within hours of landing.** When `/agents` returned "No agents available", the routing entry's `disposition: command-intercepted` + `agent: Sonos Agent` told us in one look that the dispatcher path was healthy and the bug was in the command handler's secondary admission re-check. Without the panel, isolating the bug would have required DB introspection or log digging. **This is exactly the operator-debug use case the leg was scoped for, and it earned its keep on the first real bug.**

- **Behavior tests caught a real product bug that unit tests missed.** The L4 enhancement's `recapture` regression (no-provider branch unconditionally re-baselining the dirty-tracker, breaking GUI clear+save) was missed by all 5 of `test_flow_studio_connector_inference_provider_row.py`'s unit browser tests but surfaced cleanly by the L4 behavior test's Step 7. The Witnessed pattern with `[mixed-frame]` HTTP probes reached a dirty-tracker race that DOM-snapshot assertions structurally can't reach. **This is the canonical case for behavior-test investment.**

- **Phase 2d batched commit shape worked.** `20615fc` (L1-L5 autonomous batch, 40 files, +7362/-590) was reviewable as one diff; `533e806` (L6 HAT report + cluster Known Issue) stayed semantically separated; `6c7e80e` (L6 refinement after `/whoami` confirmation) was small and focused. Three commits, each coherent. The L6 HAT report didn't tangle with the autonomous-leg diff.

- **Recon-revealed scope adjustments handled cleanly.** L3's test target was revised mid-flight from `2784 ± 2` to `2794 ± 2` because the architect-cycle-1 cull estimate (10-12 tests) was ~5x off — recon found only 2 tests structurally needed culling. The flight's Adaptation Criteria pre-authorized this variance ("L3 may discover that test_connectors_inference.py's settings-path tests have already been partially rewritten...") so the designer revised without re-planning. Velocity cost: zero.

- **L4 enhancement (operator-directed mid-flight scope expansion)** was absorbed cleanly via in-flight follow-up under the existing L4 acceptance criteria, with the design rationale documented in flight-log Session Notes per the immutability discipline. The behavior-test spec was updated in lockstep (Steps 2/4/7 reworded; Step 8 added for `(custom)` fallback verification).

## What Could Be Improved

### Process

- **L4 in-flight scope expansion lacks structured rationale capture.** The L4 enhancement (text input → provider-aware dropdown) was operator-directed post-L4-behavior-test. The leg artifact was correctly not rewritten (immutability discipline), but the enhancement's design rationale — `(custom)` fallback semantics, race-guard via `_connectorModelsActiveProviderId`, `recaptureSnapshot()` discipline — lives only in flight-log Session Notes prose. If a future flight touches `populateInferenceModelDropdown`, the maintainer has to reverse-engineer the contract from code + flight-log. **Recommendation**: when in-flight scope expansion happens, append a structured "Post-land enhancement" subsection to the leg artifact with its own mini-ACs, even though the leg status stays `landed`. Preserves immutability of the original AC set while giving downstream maintainers a structured place to find the enhancement contract.

- **L5 leg-design cycle-1 missed a citation to a non-existent file.** `realtime.py:_session_joined_payload` was cited but no such file exists; the real builders are `_build_session_joined_ok` + `_build_session_joined_degraded` in `app.py`. Caught only because the Flight Director ran a pre-confirm grep before spawning the implementor. **Recommendation**: add "Citation-Audit grep-verification" as a mandatory Phase 5c gate item for substrate-touching legs — every `file:line` citation in the leg artifact must be verified to exist via `git grep -n "<symbol>" <file>` *during cycle-1 review*, not just inspected for plausibility.

- **L2's AC-2/AC-6 "TWO hits" grep was off-by-divergence vs verbatim helper code.** The literal grep produced 4 functional hits + 3 docstring examples = 7 total; the spec's design intent ("each helper KEEPS `dm_allowed`") was satisfied; the literal count was authored before the verbatim Implementation Guidance §2 code body was finalized. **Pattern observation** (second occurrence per flight-log Anomalies): ACs that assert a global literal count on grep against helper-body branch structure are fragile. ACs should count emit-sites-per-helper or assert design-intent-preserved, not total file count. Worth a callout in the behavior-test AUTHORING guidance.

### Technical

- **Architect-cycle test-delta estimates need a "construction-count vs semantic-pinning-count" distinction.** L3's "10-12 culls" estimate counted `Settings(...)` construction sites as if each were a cullable semantic pin; recon revealed only 2 sites were structurally doomed (the partial-pairing tests). The other 17 were mechanical signature rewrites that preserved semantic coverage. Apply this distinction in future flights with substrate-removal legs.

- **L4 enhancement landed without unit tests for `populateInferenceModelDropdown`.** The behavior test caught the recapture regression; without it, the bug would have shipped. **Debt**: backfill 2-3 browser tests covering Ollama few-model render, OpenRouter many-model render, `(custom)` fallback, no-provider clear-and-save flow, and mid-fetch provider-switch race-guard.

- **Bug D (the `_commands.py:_permitted_agents` missing-kwargs bug)** was latent for ~10 days post-F12 (F12 widened `admits_inbound` to require structured-tuple-allowlist kwargs; `_permitted_agents` at `_commands.py:108` stayed F7-shape). The F12 architect-cycle didn't grep `_acl.py`'s public-API call-sites. **The architectural debt is an API contract drift**: callers of `admits_inbound` weren't migrated in lockstep with the substrate widening. **Refactor opportunity**: `admits_inbound` should take a **single envelope/context object** rather than positional + keyword args, so the type system surfaces any missing-context call sites at static-analysis time. The envelope already carries all the fields; the function should just take it.

- **`ChatSessionRepository.update` silently drops `session_metadata`** on PUT. The L5 backend tests fell back to `set_session_metadata_key`; the L5 behavior-test spec's seeding instructions had to use direct aiosqlite UPDATE because the documented PUT-or-SQLite path's PUT half doesn't work. Worth either widening `.update` to cover all 13 columns OR adding an explicit "PUT does not round-trip session_metadata" docstring at `api.py:3222`.

- **uvicorn `--reload` doesn't reload Pydantic class objects when their source module changes.** The L6 Bug A diagnostic walk surfaced this: `agent/config.py` had the new L2 validator on disk, the running uvicorn worker still held the OLD `AgentConfig` class object with its frozen Pydantic schema. Full container restart fixed it. **This is an operations gotcha** — worth documenting in CLAUDE.md so future flights touching Pydantic validators know to restart vs reload.

### Documentation

- **L4-enhancement design rationale missing from leg artifact** (covered above as a process gap with structural fix).
- **`ChatSessionRepository.update`'s fixed-column-list shape is undocumented** — adding a docstring + workaround pointer would help the next developer who hits the PUT-vs-repository surprise.
- **`RESERVED_CONFIG_KEYS` map in `connector-editor.js`** is the substrate-side preventer of kv-table-duplicate-controls hazards (F7 L12 precedent) but has no comment explaining the contract or why each key is reserved. Adding 2 inference keys made the map 6 entries with no rationale anywhere.
- **The 2 pre-existing browser test failures** (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`) have now persisted across F10 → F11 → F12 → F13 unaddressed (4-flight deferral). The deferral feels structural rather than incidental at this point.

## Test Metrics Trend (F8 → F13)

| Metric | F8 | F9 | F10 | F11 | F12 | **F13** |
|---|---|---|---|---|---|---|
| Backend passed | 2669 | 2721 (+52) | 2733 (+12) | 2749 (+16) | 2783 (+34) | **2796 (+13)** |
| Backend skipped | 4 | 4 | 4 | 4 | 4 | **4** |
| Backend wall (s) | 197 | ~250 | ~257 | 254 | 246 | **243** |
| Browser passed | — | +6 | +7 | 431 (+0) | 443 (+12) | **454 (+11)** |
| Browser wall (s) | — | — | — | ~530 | 509 | **~520** |
| Errors | 0 | 0 | 13 pre-existing | 0 (resolved L3) | 0 | **0** |
| Pre-existing browser fails | — | — | — | — | 2 (since pre-F10) | **2 (still)** |

**Notable observations**:
- Backend wall-clock improved slightly again (246s → 243s). Trend across F11 → F13 is monotonically faster despite +47 tests over the span; the throughput regression M10 debrief flagged is not the dominant signal anymore.
- Browser wall-clock crept back up by ~11s (509s → 520s) — accounted for by the 11 new browser-marked tests in F13 (L4 +5, L5 +6) at ~3.5s/test. In-line; not yet a concern.
- Skip list stable at 4. Deselect grew from 509 → 520 — accounted for by the +11 browser-marked tests deselected in non-`-m browser` runs.
- Zero new flakes from F13. The 2 pre-existing-main browser failures have persisted across F10 → F13 — see Documentation above.
- 3 warnings continue to be the `aiosqlite` event-loop-closed teardown class from F11 (`test_db_migration.py` `TestSchemaV17`). Still under routine-maintenance ticket; not yet promoted to errors by any pytest-asyncio version.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L3 test target revised `2784 → 2794` at design-time recon | architect-cycle-1 cull estimate counted construction-sites not semantic-pins; recon found 5x fewer cullable tests | **Yes** — authorize "recon-time target revision" in Adaptation Criteria for any substrate-removal leg |
| L4 mid-flight scope expansion (text input → dropdown) | operator-directed post-behavior-test; chat UI's sibling pattern (`studio.js:1720+`) was discoverable at planning time but not surfaced | **Partial** — when a new field has a known sibling pattern in the same app, planning should surface "use sibling pattern X or new shape Y" as an Open Question |
| L5 spec mis-cited `realtime.py:_session_joined_payload` (non-existent) | cycle-1 design review pass didn't run executable grep verification on cited file:line refs | **Yes** — add Citation-Audit grep-verification as a Phase 5c gate item |
| Phase 2d batched commit split L1-L5 from L6 | per protocol — Reviewer + commit deferred to after autonomous-legs; L6 HAT runs interactively + commits separately | Already standardized; this flight validated the pattern at scale |
| L6 HAT bookkeeping (3 commits: L1-L5 batch, L6 report, L6 refinement) | preserved semantic coherence per commit; the `/whoami` PASS revelation came after the initial L6 report | **Yes** — HAT-leg commits should be small and granular (one per substantive new finding) |

## Key Learnings

1. **L5's routing-audit panel + L6's bug hunt was the canonical "diagnostic surface as deliverable" moment.** Within hours of landing, the panel isolated Bug D to `_commands.py` by showing `disposition: command-intercepted`. The diagnostic value of L5 was operational immediately, not theoretical. **Codification candidate**: any flight that introduces a new dispatcher path, policy gate, or routing decision should consider shipping the inspector surface in the same flight.

2. **Behavior tests reach what unit tests don't.** The L4 enhancement's `recapture` regression was missed by 5 passing unit browser tests; caught by Step 7's GUI clear+save flow in the behavior test. The `[mixed-frame]` HTTP probe was the cross-check that distinguished "looks right" from "actually persisted". This validates the Witnessed pattern's structural advantage over single-agent assert chains.

3. **F7-era latent bugs surface under F12-shape pressure.** Bug D's call site (`_commands.py:108`) was correct against F7's flat-allowlist shape; F12 widened the substrate to require structured-tuple kwargs; nobody updated the consumer. The bug stayed silent for 10+ days because F12's tests didn't exercise the consumer (`_handle_agents`) against a structured-tuple allowlist. **Lesson**: every substrate-API widening flight should audit all consumer call sites and either update them in lockstep OR add a regression test that exercises each consumer against the new shape.

4. **uvicorn `--reload` is not a substitute for container restart when Pydantic schemas change.** The L6 Bug A diagnostic walk wasted ~10 minutes on a stale-Pydantic-class issue because the running worker held the OLD class object. Future flights touching Pydantic class definitions should explicitly call out "container restart required" in the leg's verification steps.

5. **Cluster Known Issues for HAT findings preserve the "solve as a unit" framing.** The 4-bug ACL/slash-sync cluster filed as a single mission.md entry (rather than 4 separate Known Issues) keeps the joint substrate-shape decisions visible together. The follow-on flight can plan a coherent L1-L4 attack on the cluster rather than spreading the fixes across multiple flights.

6. **Architect-cycle-1 should grep `_acl.py` public-API call-sites whenever ANY flight touches ACL substrate.** F12 widened `admits_inbound`; nobody grepped its 8+ call sites; Bug D shipped latent. A 1-minute grep at F12's architect-cycle would have caught it.

## Recommendations

1. **Address the 4-bug ACL/slash-sync cluster as the next flight's primary scope.** Plan 3-4 legs:
   - L1: Bug D + regression test (smallest, cleanest fix — `_permitted_agents` threads full envelope context; ~5-10 LOC + 1-2 new unit tests exercising `_handle_agents` against a structured-tuple allowlist).
   - L2: Bug B substrate semantic decision (sync reads `allowlist.guilds` vs auto-derive `config.guilds` from allowlist vs UI dual-write).
   - L3: Bug C Discord plugin `member_roles` plumbing (resolve guild-member roles from gateway events before dispatch).
   - L4: Bug B/C UI affordance (category vs text-channel pickability in the channel allowlist dropdown — exclude categories from the discoverable-entities response OR show them with a non-pickable visual marker).
   - L5 (optional): refactor `admits_inbound` to take a single envelope/context object so future API widenings surface call-site drift via type system.

2. **Backfill 2-3 browser tests for the L4-enhancement `populateInferenceModelDropdown`** (Ollama few-model, OpenRouter many-model, `(custom)` fallback, no-provider clear-and-save, mid-fetch race-guard). The behavior test catches the flow; a unit-level regression net is missing.

3. **Codify new agents.md M11 conventions** in the next maintenance pass (do not delay current flights):
   - `detail-endpoint-attaches-rich-payload` — F13 L5 + M10 F5 L4 precedents
   - `provider-aware-model-dropdown-with-custom-fallback` — F13 L4-enhancement + `studio.js:1720+` chat precedents
   - `in-memory-snapshot-from-db-restore` — F13 L5 `Session.session_metadata` + M10 F5 L4 `Session.platform` precedents
   - `diagnostic-surface-co-ships-with-decision-path` — F13 L5 routing-audit panel earning its keep at L6
   - `consumer-callsite-audit-on-public-api-signature-widening` — Bug D pattern preventer

4. **Make `/behavior-test` cache-cold by default** (`new_page` + `ignoreCache=true` reload as implicit Step 0). Specs can opt out for tests that need cache-warm state, but the default should be cache-cold. Would have saved the L5 run-1 false-FAIL diagnostic cycle (~30 min of orchestrator time + behavior-test-methodology doubt before chrome-devtools confirmed the implementation was correct).

5. **Address the 2 pre-existing browser test failures** that have persisted across F10 → F13. Either fold into the next browser-touching flight (F14 candidate) or schedule a focused routine-maintenance pass.

## Action Items

- [ ] Open follow-on flight to address the 4-bug ACL/slash-sync cluster (3-5 legs per Recommendation #1); criterion #10 closes at HAT re-run after this flight lands
- [ ] Backfill browser tests for `populateInferenceModelDropdown` (Recommendation #2) — could fold into the cluster-fix flight as a leg or stand-alone
- [ ] Codify 5 proposed M11 conventions in next maintenance pass (Recommendation #3)
- [ ] Update mission-control `/behavior-test` skill to default cache-cold (Recommendation #4) — separate change against the mission-control repo
- [ ] File the 2 pre-existing browser test failures as a routine-maintenance item OR fold into the next browser-touching flight (Recommendation #5)
- [ ] Add Citation-Audit grep-verification as Phase 5c gate item in mission-control `/leg` skill — separate change against the mission-control repo
- [ ] Add "construction-count vs semantic-pinning-count" distinction guidance for test-delta estimates in mission-control `/flight` skill — separate change against the mission-control repo
- [ ] Document `ChatSessionRepository.update`'s `session_metadata` drop behavior (docstring + workaround pointer) — small routine-maintenance item
- [ ] Add `RESERVED_CONFIG_KEYS` map contract docstring in `connector-editor.js` — small routine-maintenance item
- [ ] Add CLAUDE.md note about uvicorn `--reload` Pydantic class caching gotcha — small routine-maintenance item
- [ ] Mark draft PR #82 ready for review when ready (operator's call)
