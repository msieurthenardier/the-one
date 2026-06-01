# Flight Debrief: Hierarchical Allowlist Axes + Snake_Case Identifier Rename (F11 prereq)

**Date**: 2026-05-31
**Flight**: [Hierarchical Allowlist Axes + Snake_Case Identifier Rename](flight.md)
**Status**: completed
**Duration**: 2026-05-29 (planning + L1-L4 land as `eb7f04d`) → 2026-05-30 (post-land L5 extension + push as `9f4df4a` / PR #81 merge) → 2026-05-31 (debrief)
**Legs Completed**: 5 of 5 (L1 snake-case-identifier-rename, L2 acl-extraction-and-symmetric-paths-convention, L3 storage-shape-v24-migration-and-acl-semantics, L4 ui-discoverable-dropdown-and-per-peer-dm-toggle, L5 hierarchical-server-parent-ui)

## Outcome Assessment

### Objectives Achieved

F12 reshaped the connector allowlist substrate end-to-end. The five flat-axis storage layout (`peers, channels, guilds, roles, dm_admission`) became a structured-tuple-with-hierarchy shape: `peers: list[{id, dm_allowed}]` (per-peer DM gate consumed under `dm_admission="admin-approved"`); `channels: list[{guild_id, channel_id}]` and `roles: list[{guild_id, role_id}]` (server-scoped tuples; wildcard `"*"` channel_id / role_id sentinel for "all of this guild"); `guilds: list[str]` (unchanged); `dm_admission` Literal value renamed `"allowlisted-peers-only"` → `"admin-approved"` (operator-vocabulary alignment). `_acl.py:admits_inbound` was extracted into `_admits_inbound_dm` + `_admits_inbound_guild` dispatcher (the 5-axes-tipping-point concern F10 debrief flagged), and the L1 mechanical rename closed F11's snake_case identifier residue (~35 def renames + ~292 hit sites across Python, Markdown, and browser tests, plus 2 test filenames via `git mv` and the `idx_pending_approvals_account_peer_status` index name bundled into v24).

The flight landed two schema migrations in a single PR (v24 for the structured-tuple row-rewrite + Literal rename + index rename + per-agent `connector_acls` parallel rewrite; v25 for orphan deletion + Pydantic validator tightening to reject null guild_id post-v25). The `two-symmetric-paths-in-acl` convention was codified in `the_one/agents.md` M11 section as F11 debrief recommendation #5 asked for; L3's structured-tuple lookup + L5's wildcard semantics both touched `admits_inbound` AND `admits_outbound` in lockstep, validating the convention's discipline.

The L1-L4 plan held exactly as designed. L5 was a post-land extension triggered by the operator's reaction to seeing the flat three-section L4 layout — substrate became Server-as-parent (channels + roles nested under server rows; cascade-delete on server removal; wildcard sentinels for empty server rows). L4's legacy-entry indicator + 2 of its browser tests became dead code one leg later (deleted in L5).

### Mission Criteria Advanced

This flight does not close a mission criterion directly. It is a substrate-stabilization flight that supports criterion #19 (daily-driver robustness) indirectly by:
- structurally preventing the name-collision admission class of bugs filed at F10 L5 HAT (channel `#general` in Server A vs Server B can no longer be conflated at the storage layer);
- closing the F10-filed "Hierarchical allowlist axes" Known Issue and the F11-filed "snake_case identifier rename residue" Known Issue (both marked `[x]` in mission.md);
- aligning operator-facing vocabulary across UI + API + storage + agents.md before F13's audit-log inspector and F14's HAT script consume the same surfaces.

### Checkpoints Met

All 5 leg-level checkpoints in `flight.md` are checked off. The flight-level completion checklist is fully checked except "Code merged" (was unchecked at debrief start) — this debrief flips it after verifying merge commit `9f4df4a` on main. Mission outline F12 entry is marked `[x]` with the post-land summary.

---

## What Went Well

**The L1-L2-L3-L4 leg sequence held without revision.** Each leg's stated atomicity boundary held against verification (L1 backend-only; L2 `_acl.py` + `agents.md`; L3 substrate + ACL helpers; L4 frontend + browser tests). The cycle-1 collapse of the originally-separate L3 (storage) + L5 (ACL semantics) into one atomic leg avoided the bridge-code transient state the architect predicted — splitting them would have left tests against the new shape without the ACL semantic that respects it.

**F11 debrief methodology lessons applied faithfully across the flight.** Lesson #1 (grep-gate-scope-is-a-design-decision) drove L1's explicit corpus + pattern + allowed-residue enumeration; Phase 5c grep recon confirmed enumeration accuracy at implementation time including the `_seed_connector_account` 11-call-site correction that became part of the spec. Lesson #5 (two-symmetric-paths-in-acl convention) was codified in L2 as a named M11 convention. Lesson #3 (separate test-surface from production-surface recon) drove L3's catalog of 7 production peer-list consumer sites + ~30 fixture sites. Lesson #4 (Phase 5c architect cycle for grep-gate flights) was structured into every leg.

**The L2 extraction landed as a clean structural no-op.** `_acl.py` grew 484 → 575 LOC; the 169 existing ACL test sites passed unchanged; comment blocks were preserved verbatim in both helpers per the implementer's "readability favors the verbose form" rationale; the new dispatcher body is ~12 lines. The architect's two-phase refactor reasoning (extract-then-modify, smaller diff per leg, each reviewable independently) paid off: L3's mutations landed against a stable structure rather than a 240-line monolith.

**The 12-cell DM Composition Cross-Product Matrix is exemplary substrate-test discipline.** Each cell in `tests/test_connectors_acl.py::TestDmAdmissionCompositionMatrix` carries a rationale string; parametrize ids are descriptive (`cell_03_None_all_True_out`); the test exercises the actual composition rule rather than shape-pinning. The cycle-1 cell-#3 revision (peers-axis denies FIRST under `dm_admission=all`) is documented inline. The 8-cell `TestHierarchicalAxisWildcardMatrix` extends the same discipline to wildcard semantics across both ACL directions. This is the substrate-test-matrix-by-default pattern F11 debrief recommended; it now has a concrete precedent.

**The translator-helper-at-test-module-top pattern kept the L3 fixture-update diff modest.** `_to_v24_shape` + `_to_v24_agent_acl` (in `tests/test_connectors_acl.py`, `test_connectors_routing.py`, `test_connectors_commands.py`, mirrored as `_to_v24_allowlist` in `tests/browser/seeders.py`) wrap flat-shape fixture data at call time so existing fixtures stayed readable. ~30 sites were updated without sweep-renaming each entry.

**The column-aware-index-create-for-rewind-paths fix in v21's migration block.** L3 surfaced and resolved in-leg an anomaly where the v21 block's `CREATE INDEX IF NOT EXISTS idx_pending_approvals_account_peer_status` failed on the `test_v7_strips_removed_tool_names` rewind+rerun path (v24 dropped the old-named index; v21's re-create referenced the post-v23-renamed column). The fix split v21's `executescript` into the `CREATE TABLE` half + a Python-guarded `CREATE INDEX` consulting `PRAGMA table_info(pending_approvals)` to choose old-vs-new branch. Worth standardizing as a migration pattern.

**The mid-execution-pivot for L5 worked without artifact corruption.** Operator surfaced the hierarchical-UI alignment request after L1-L4 committed locally as `eb7f04d`; per `/agentic-workflow` mid-execution-pivot guidance, flight status was flipped `landed` → `in-flight`, L5 was added to flight.md + Completion Checklist, an FD note recorded the decision, and the L5 leg artifact captured the live spec. The flight ultimately landed with all 5 legs in a single PR (#81 / `9f4df4a`) without amending prior commits — L5 is a separate commit on top.

**`docker-compose.yml` operator-local-state discipline held across all 5 legs.** The operator's M11 F7 L12 HAT env vars stayed unstaged in every leg's implementation; explicit `git add <files>` (never `git add .` / `-A`) preserved local dev state out of every F12 commit. Five flights deep of this discipline; it now reliably scales.

**Test metrics improved or held across every dimension.** Backend wall-clock 254s (F11) → 246s (F12, −3.1%). Browser wall-clock ~530s (F11) → 509s (F12, −3.9%). Zero new flakes; zero new errors; the only persistent warning is the F11-filed aiosqlite teardown class (1 warning observed this run, same root-cause family as F11 L3 fixed elsewhere). The +34 backend tests (2749 → 2783) and +12 browser tests (431 → 443) added real coverage (5 v24 + 3 v25 + 12 DM-composition + 8 wildcard + 4 validator-rejection + 7 hierarchical-UI + per-peer DM toggle + per-agent overlay omission), not shape-pinning.

---

## What Could Be Improved

### Process

- **The hierarchical UI shape went through three iterations** (F10 L5 HAT framing: Servers⊃Channels⊃Users → F12 planning: global-peers + Servers⊃Channels/Roles flat-three-sections → L5: Servers-as-parent with channels and roles nested). The L4→L5 churn was driven by the operator's reaction to *seeing* the flat result, not by reasoning about it abstractly. **Recommendation**: when a UI shape is in scope at flight planning, attach a verbal mockup or rough wireframe to the flight design ("here's what the operator will see when this lands"). The cost is low; the benefit is collapsing L4+L5 into one design conversation.

- **L4 enumerated 4 frontend files; implementation touched 6.** The L4 implementer's justification ("connectors-tab.js is the per-agent overlay since agent-editor.js delegates to it; studio.js's collect path + connector-form-discord.js's registry bridge must flow structured tuples end-to-end") is sound — but the leg spec's "agent-editor.js — per-agent overlay" line was semantically incorrect at design time. **Recommendation**: phrase frontend leg spec file lists semantically ("the per-agent overlay surface, wherever it lives") rather than as a literal enumeration; verify file ownership at recon before committing to leg atomicity boundaries.

- **L3 made an in-leg recon discovery the spec didn't anticipate**: the spec's "Pre-v24 TestSchemaVN classes stay untouched (Category A)" carve-out collided with the v21/v22/v23 fresh-DB tests' post-state assertions (those tests pass through full `ensure_schema` which now runs v24, so their head-of-suite assertions had to update to the post-v24 shape). The Category A discipline was honored correctly — only post-state assertions updated; pre-v24 seeded data + decode-test shapes preserved — but the spec didn't predict this collision. **Recommendation**: codify the "Category A only shields seeded-data-decode tests, not fresh-DB-through-full-ensure_schema tests" learning as a methodology note for future migration legs.

### Technical

- **`_acl.py` LOC growth is approaching the F10-flagged "edge of readable" line again, at the helper level.** 484 (pre-F12) → 575 (post-L2) → ~720 (post-L3) → **740** (post-L5). The L2 extraction reduced per-function complexity by splitting the 240-line `admits_inbound` body into two helpers — but L3 added composition-chain logic and L5 added wildcard semantics, so each helper now carries 3 admission axes plus wildcards. **F13 (audit-log inspector instrumentation) and F14 (HAT script hooks) will almost certainly touch this file.** Schedule an axis-level extraction (peers-helper / channels-helper / roles-helper composing into `_admits_inbound_dm` and `_admits_inbound_guild`) before F14, OR fold into a near-term routine-maintenance pass. Don't do this proactively unless a concrete bug surfaces — the convention is codified to make the lockstep updates discipline-driven now — but track it.

- **The per-agent `peers[*].dm_allowed` field is a footgun in waiting.** Schema migration v24 stores `dm_allowed` on per-agent peer entries for "structural uniformity," but the L3 DM Composition Truth Table explicitly does not consult it (DM admission is account-scope only). The UI in `connectors-tab.js` correctly omits the per-agent DM toggle + renders the "DM admission is account-scope only" note. But the storage field exists, validators accept it, and the migration defaults it to `true`. A future engineer reading the per-agent ACL fixture will reasonably assume the field is consulted somewhere. **Recommendation**: either remove the field from per-agent storage at the next ACL-touching flight (v26 migration that strips it + validator + UI cleanup), OR commit a `# WARNING: NOT CONSULTED BY ACL` comment to the validator + a `structural-uniformity-vs-semantic-uniformity` note in agents.md.

- **`connector-editor.js` is at ~4450 LOC with both `_mountAllowlistAxisEditor` (L4 flat 3-section mount) and `_mountAllowlistHierarchicalEditor` (L5 server-as-parent mount) resident.** A debrief-time grep would confirm whether the flat mount is still called from any path (legacy-account UI fallback?). If purely dead post-L5, schedule its removal. If still load-bearing for non-Discord connector types, document the boundary in a new `agents.md` block describing when each mount is used.

- **Translator helpers (`_to_v24_shape`, `_to_v24_agent_acl`, L5's `DEFAULT_TEST_GUILD_ID`) appeared in 4+ test files** (`tests/test_connectors_acl.py`, `tests/test_connectors_routing.py`, `tests/test_connectors_commands.py`, `tests/browser/seeders.py`) doing the same shape-evolution work. **Recommendation**: extract a `tests/_acl_shape_helpers.py` (or `tests/fixtures/acl.py`) shared module before F13 lands. Drops ~50 LOC of duplication and gives future migrations a single point to extend.

### Documentation

- **The v25 orphan-deletion behavior is documented in the leg artifact and the migration body comment, but not in the M11 agents.md section.** A future contributor reading agents.md will see the `two-symmetric-paths-in-acl` convention but no record of "v25 enforces non-null guild_id post-migration." Worth a one-line addition to the M11 section or to the schema.py module docstring.

- **The L1 grep-gate's allowed-residue list expanded in-leg by 3 files** (`_stub.py:23`, `_connector_types.py:24`, `models.py:120` — historical-narration sites that the L1 spec's filter didn't explicitly cover, even though they were semantically equivalent to the `agents.md:671` + `README.md:312` exceptions). L1 noted this in the flight log and suggested L2/L3 fold the filter. Not actually folded; left as residual non-blocking note. Worth either (a) updating the grep-gate filter in any future rename-flight spec template, or (b) converting those 3 sites to use the `connectors` table name with a footnote.

---

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Post-land L5 extension after L1-L4 already committed locally as `eb7f04d`. | Operator's reaction to the flat L4 three-section UI drove the hierarchical-UI alignment request. Not a planning miss on the data shape; a legitimate UI iteration the operator couldn't reason about abstractly until they saw the result. | Yes — when a UI shape is in scope at flight planning, attach a verbal mockup. The mid-execution-pivot guidance in `/agentic-workflow` worked cleanly for the procedural side; the meta-lesson is on flight design, not execution. |
| L4 frontend file count was 4 (spec) vs 6 (implementation) — `connectors-tab.js` + `studio.js` + `connector-form-discord.js` added at implementation time. | Per-agent overlay save path + Discord registry bridge had to flow structured tuples end-to-end for L3 storage compatibility. | Yes — phrase frontend leg spec file lists semantically ("the per-agent overlay surface") rather than literally; verify file ownership at recon. |
| L3 updated v21/v22/v23 TestSchemaVN fresh-DB post-state assertions despite the spec's "Pre-v24 TestSchemaVN classes stay untouched (Category A)" carve-out. | Those tests pass through full `ensure_schema` which now runs v24; their post-state assertions had to reflect v24's shape. Pre-v24 seeded data + decode-test shapes preserved correctly. | Yes — codify the "Category A only shields seeded-data-decode tests, not fresh-DB-through-full-ensure_schema tests" learning as a methodology note for migration legs. |
| L3 split v21's `executescript` into `CREATE TABLE` + Python-guarded `CREATE INDEX` consulting `PRAGMA table_info(pending_approvals)` to handle the v7-strip rewind+rerun path. | v24 dropped the old-named index; v21's re-create referenced the post-v23-renamed column on rewind paths. | Yes — standardize as `column-aware-index-create-for-rewind-paths` pattern in agents.md or schema.py module docstring. |
| L1's allowed-residue list expanded in-leg by 3 historical-narration sites the spec's filter didn't explicitly cover. | Spec's filter pipeline only excluded `schema.py` + `test_db_migration.py` + `agents.md:671` + `README.md:312`; 3 semantically-equivalent sites in `_stub.py`, `_connector_types.py`, `models.py` slipped through. | Yes — rename-flight spec templates should include "all historical-narration sites about prior renames" as a category in the allowed-residue enumeration, not just explicit per-line citations. |
| L5 resumed from a partially-implemented state (a prior spawn had landed substantial production code but was interrupted before reconciling 10 pre-existing L4 browser tests against the new hierarchical layout). | Resume pattern: inspect committed state at session start, identify completed surfaces, complete remaining work without re-doing. | Already standardized (F11 codified the partial-implementer-rejection-then-retry pattern); this is the same shape applied to a different interruption mode. |

---

## Key Learnings

**Architect cycle-1 leg-merge decisions are load-bearing.** Cycle-1 collapsed the originally-separate L3 (storage) + L5 (ACL semantics) into one atomic leg because adding `dm_allowed` to storage requires the ACL helpers to consume it in lockstep. The collapse was right — splitting would have left tests against the new shape without the ACL semantic that respects it. F12 then ALSO added a new (different) L5 post-land, so the final leg count was 4 → 5, but the cycle-1 merge survived intact. Trust the architect cycle-1 verdict on leg-merge questions; the bridge-code argument matters.

**UI shape decisions benefit from concrete artifacts at planning time.** The hierarchical-UI question went through three iterations (F10 L5 HAT, F12 planning, L5). The operator's pivot at L4-land wasn't a planning failure — they hadn't formed an opinion about the UI shape until they saw the flat three-section result. A verbal mockup ("here's what the operator will see") at F12 planning could have surfaced the server-as-parent preference earlier. Cheaper than the L4→L5 churn even at low fidelity.

**Codified conventions actually get applied.** F11 debrief recommendation #5 (`two-symmetric-paths-in-acl`) was added to agents.md in L2; L3 + L5 both honored it (channel-tuple lookup in both directions; wildcard semantics in both directions). Three flights deep of paying the lockstep cost; the convention now has a precedent and a mechanism. The right time to codify is when 3+ instances have surfaced — promotion at recommendation #N where N is the third instance.

**Structural uniformity ≠ semantic uniformity.** The per-agent `peers[*].dm_allowed` mirror demonstrates this: the field is stored uniformly (parallel shape across account-scope and per-agent), but the semantic is intentionally scoped (ACL consults it only at account-scope). Uniform storage with non-uniform consumption is a footgun pattern. Future ACL evolutions should declare which uniformity is wanted; this might become a named M11 convention if a second instance surfaces.

**Translator helpers in test files scale to substrate-shape evolution.** L3's `_to_v24_shape` + L5's `DEFAULT_TEST_GUILD_ID` defaults kept fixture diffs modest across 30+ sites. Pattern: when a substrate shape evolves, add a per-test-file (or shared-module) translator that wraps flat fixtures at call time; existing test code stays readable; future shape evolutions extend the translator rather than sweeping fixtures again.

**Migration anomalies surface at unusual code paths.** The v7-strip rewind+rerun path in `test_v7_strips_removed_tool_names` is not a path operators ever exercise — it's a pytest fixture path that strips tool-names from an ancient schema state and re-runs `ensure_schema`. But it's the path that surfaced the v21 `CREATE INDEX` failure when v24 dropped the old-named index. Migration recon needs to walk these rewind paths, not just the linear-from-fresh paths.

---

## Recommendations

1. **Resolve the per-agent `peers[*].dm_allowed` ambiguity at the next ACL-touching flight.** Either remove the field with a v26 migration that strips it (parallel UI + validator + agent/config.py cleanup), OR commit an explicit `# WARNING: NOT CONSULTED BY ACL` comment to the validator + a named `structural-uniformity-vs-semantic-uniformity` convention in agents.md M11. Don't leave it as a live footgun.

2. **Schedule an `_acl.py` axis-level extraction before F14 (HAT script flight).** The file is at 740 LOC; each of the two `_admits_inbound_dm` / `_admits_inbound_guild` helpers carries 3 admission axes plus wildcard logic plus per-agent overlay handling. Extract a `_axis_admits_peer(allowlist, peer_id)` / `_axis_admits_channel(allowlist, channel_id, guild_id)` / `_axis_admits_role(allowlist, member_roles_set, guild_id)` set of helpers, composing into the two direction-specific dispatchers. The peers-axis duplication across the two helpers becomes a single seam. **Don't do this proactively unless a concrete bug surfaces; track it as a routine-maintenance candidate.**

3. **Extract a shared `tests/_acl_shape_helpers.py` (or `tests/fixtures/acl.py`) module before F13.** Consolidate the `_to_v24_shape`, `_to_v24_agent_acl`, `_to_v24_allowlist` (browser seeders), `DEFAULT_TEST_GUILD_ID` helpers from 4+ test files into one place. Drops ~50 LOC of duplication; gives future schema migrations a single point to extend.

4. **For F13/F14 planning, attach a rough UI sketch or verbal mockup whenever a UI shape is in scope.** F12's L4→L5 churn was driven by the operator's reaction to the flat layout rather than abstract design conversation. Cheapest preventive measure for the next UI-shape-in-flight is "describe what the operator will see when this lands" at flight planning. Methodology nudge for the Flight Director, not a hard process change.

5. **Codify two patterns surfaced in this flight as named conventions in `the_one/agents.md` M11 section** (or Project-wide section if more broadly applicable):
   - `column-aware-index-create-for-rewind-paths` — for migrations that DROP+CREATE indexes whose columns evolved in prior migrations: split `executescript` into `CREATE TABLE` + Python-guarded `CREATE INDEX` consulting `PRAGMA table_info` to choose old-vs-new column branch (precedent: L3's fix to v21's block for v7-strip-test rewind path).
   - `test-translator-helpers-for-shape-evolution` — when a substrate shape evolves, add a translator at test-module top (or shared module) that wraps flat fixtures at call time; existing test code stays readable; future shape evolutions extend the translator rather than sweeping fixtures (precedent: L3's `_to_v24_shape` and L5's seeders update).

---

## Action Items

- [x] **Mission outline updates** (already done during L5 land): Flight 12 marked `[x]` in `mission.md` with the post-land summary; both F10 + F11 carry-forward Known Issues marked `[x]`.
- [x] **Flight status transition**: `landed` → `completed` (this debrief). Code merged at commit `9f4df4a` (PR #81). Completion checklist flipped fully.
- [ ] **Pre-existing browser test failures (unchanged from pre-F10)**: `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` and `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`. Still unaddressed; carried into F13. Routine-maintenance candidate or fold into next browser-touching flight.
- [ ] **Per-agent `peers[*].dm_allowed` field disposition**: decide at next ACL-touching flight planning (likely F13 if audit-log inspector touches `_acl.py`, otherwise routine-maintenance).
- [ ] **`_acl.py` axis-level extraction**: track as a routine-maintenance candidate; do not pre-empt unless a concrete bug surfaces. Re-evaluate at F14 planning.
- [ ] **Shared test-fixture translator module**: extract before F13 lands or as F13's first leg's prereq sub-step.
- [ ] **Codify 2 new conventions in `agents.md`**: `column-aware-index-create-for-rewind-paths` + `test-translator-helpers-for-shape-evolution`. Fold into F13's first leg's docs-sweep, or land as a standalone routine-maintenance commit.
- [ ] **aiosqlite event-loop-closed teardown warning (F11 carry-forward)**: 1 warning observed in this run at `TestSchemaV17::test_v17_fresh_db_includes_agents_connector_ids_column` teardown. F11 debrief's "apply L3 fixture-redesign pattern" recommendation was correctly re-classified by F12 recon as not-applicable (the `test_db_migration.py` fixture is already async). Real fix needs investigation (warning filter / library version / fixture restructure). Routine-maintenance pass.

---

## Test Metrics

| Metric | F8 land | F9 land | F10 land | F11 land | **F12 land** |
|--------|---------|---------|----------|----------|--------------|
| Backend tests passed | 2669 | 2721 (+52) | 2733 (+12) | 2749 (+16) | **2783 (+34)** |
| TestSchemaV24 (new) | — | — | — | — | +6 (5 spec + 1 cycle-1 round-trip) |
| TestSchemaV25 (new) | — | — | — | — | +3 |
| TestDmAdmissionCompositionMatrix (new) | — | — | — | — | +12 (cross-product) |
| TestHierarchicalAxisWildcardMatrix (new) | — | — | — | — | +8 (L5 wildcard) |
| TestAllowlistGuildIdRequired (new) | — | — | — | — | +4 (L5 validator) |
| Browser tests passed | — | +6 | +7 | 431 (+0 net) | **443 (+12)** |
| Browser tests new (hierarchical-server-rows) | — | — | — | — | +7 |
| Browser tests new (per-peer DM toggle) | — | — | — | — | +5 (7 net of 2 L5-retired) |
| Backend skipped | 4 | 4 | 4 | 4 | **4** |
| Backend errors / failures | 0-13 (intermittent) | 13 / 0 | 13 / 0 | 0 / 0 | **0 / 0** |
| Backend wall-clock (full suite) | ~150s | ~250s | ~257s | 254s | **246s (−3.1% vs F11)** |
| Browser wall-clock | — | — | — | ~530s | **509s (−3.9% vs F11)** |
| Browser failures | — | — | 0 | 2 (pre-existing main, not F11-caused) | **2 (same; not F12-caused)** |
| New flakes observed | — | — | Zero | Zero | **Zero** |
| `aiosqlite` event-loop-closed teardown warnings | — | — | — | 2 | **1** (same class; root-cause investigation deferred to routine-maintenance) |

Wall-clock moved in the right direction across both suites despite +34 backend tests and +12 browser tests added. The test-throughput regression M10 debrief flagged (14.4 → 12.5 t/s) is not the dominant signal anymore — F12 added meaningful coverage without slowing the suites. The 0 errors / 0 failures streak from F11 holds; the partial aiosqlite warning class persists as a library-internal quirk with no behavior impact and an open routine-maintenance ticket.

---

## Methodology Feedback

**`/agentic-workflow` mid-execution-pivot guidance worked at this scale.** L1-L4 committed locally as `eb7f04d`; the operator's L5 request flipped flight status `landed` → `in-flight` and added L5 to flight.md without amending prior commits or rewriting the L1-L4 framing. L5 landed as a separate commit on top; both commits + L5's history are preserved in the PR. The guidance handled a mid-flight pivot cleanly without artifact corruption.

**`/agentic-workflow` Phase 2d defer-commits worked at L1-L4 batch scale (50 files / 5707 ins / 522 del as `eb7f04d`).** Reviewer (Haiku) verified the full diff against acceptance criteria + grep gates in a single pass. Same pattern F11 codified — scales to 5707-insert diffs.

**`/flight` Phase 5c architect cycle for grep-gate flights** (F11 debrief recommendation #2) was applied at L1 and at L4. Both Phase 5c cycles surfaced real corrections — L1's `_seed_connector_account` 11-call-site recount; L4's browser-test file enumeration including the conditional-render-verification surface. The discipline is now demonstrated across two flights; the recommendation can be considered codified-by-practice.

**The L2 → L3 sequencing pattern (extract first, then modify) compounded F12's leg discipline.** L2 was a structural no-op (484 → 575 LOC; zero test changes); L3 then mutated against stable structure. The same pattern was applied implicitly at L1 (rename first, no behavior change; subsequent legs work against renamed identifiers). Worth naming: `mechanical-prereq-leg-before-semantic-changes`. F11 used the same shape (L1 backend rename → L2 frontend rename → L3 housekeeping); F12 confirmed it.

**The post-land extension shape is a real `/agentic-workflow` mode that benefits from explicit documentation.** F12's L5-after-L4-committed was the second post-land extension this mission (after F4's mid-execution UX hotfix scope-add). Both worked; both required the FD to update flight.md mid-execution + add the new leg artifact + flip flight status backward. The mid-execution-pivot guidance addresses this but is not loud about it; consider promoting it to a named subsection in `/agentic-workflow` SKILL.md.

**The `/flight-debrief` single-flight default fit F12 cleanly.** F12 has a unified design and a unified outcome (substrate reshape + UX alignment); no need for the combined-debrief shape from F9+F10. Debrief artifact at `flight-debrief.md`; covers L1-L5 as a single arc.
