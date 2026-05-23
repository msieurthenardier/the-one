# Flight Debrief: UX Hotfixes from F3 Debrief

**Date**: 2026-05-23
**Flight**: [UX Hotfixes from F3 Debrief](flight.md)
**Status**: landed
**Duration**: 2026-05-23 (single-session execution; planning + 4 legs + HAT fold-in in one /agentic-workflow run)
**Legs Completed**: 4 of 4 (L1 codifications + L2 A1/C1 + L3 A2 + L4 HAT with fold-in fix)

## Outcome Assessment

### Objectives Achieved

F4 was the operator-requested intervention to arrest UX-debt accumulation. The flight closed:

- **A1** (Test Connection warms pool): `api.py:test_connector_connection` now calls `account_acquire` after `plugin.doctor()` succeeds; envelope grows `details.pool_warmed` + `details.pool_warm_error`; partial-success contract preserved (warmup failure does NOT escalate doctor's `status='ok'`).
- **A2** (per-agent overlay checkbox-mode label resolver): `connectors-tab.js:_renderAccountTile` grows lazy-per-tile label cache; checkbox-rows display friendly Discord labels (`#gleepglorp-text`) instead of raw snowflakes; stub/404/network-error all preserve raw-id fallback.
- **C1** (5-flights-deep test-text-drift chronic): one-line fix in `test_edit_session_continuation_round_trip`. Closed; chronic-UI cluster now down 3→2.
- **L4 fold-in** (HAT-discovered UX gap): cross-component `connector-account-pool-warmed` CustomEvent so mounted dropdowns auto-refresh after Test Connection succeeds. This closed A1's user-visible promise that L2 alone left incomplete.
- **L1 codifications**: 4 new `agents.md` Project-wide conventions (`pool-warming-entrypoints-are-finite-and-named`, `frozen-snapshot-for-cross-lock-read`, `slot-getter-bridge-for-dropdown-collect-path`, `two-concurrent-callers-reasoning`) + 2 project-side recon-discipline fallbacks (`cross-flight-ux-debt-reconciliation`, `touched-surface-ux-debt-folding`).
- **M11 criterion-coverage seed**: `missions/11-discord-connector-depth/criterion-coverage.md` created with 19 rows mapping each M11 criterion to evidence + status + last-touched. Realises M10 debrief recommendation #5.
- **F3 flight.md correction-as-annotation**: one-line note under F3's Status block documenting the L4 design-time assumption correction; F3 body byte-identical as a snapshot.

### Mission Criteria Advanced

| M11 criterion | Status after F4 |
|---|---|
| #18 — fresh operator under fifteen minutes | `partially-closed-by-F4` — A1 closes the cold-start dropdown 404 friction; A2 closes the checkbox-mode raw-ID identification gap; both HAT-verified at L4. Operational walkthrough at mission-end gates final close. |
| #19 — full working-day daily-driver | `partially-closed-by-F4` — A1 + L4-fold-in close the cold-restart dropdown auto-refresh path. Full-day robust HAT gates final close (F10). |
| #2 — vocabulary substitution | seed left at `open`; **debrief flag**: should be `partially-closed-by-F1+F3` per Architect catch on status-vocabulary gap. Vocabulary either extends to compound predecessors or row 2 gets updated to `partially-closed-by-F3` (under-reports F1 work). |

## What Went Well

- **The HAT-gated commit ordering earned its keep at L4.** Had L1-L3 committed separately and HAT been a post-commit pass, the staleness gap would have either landed as a follow-up PR (commit noise) or escalated to a Known UX Gap (deferring the operator-facing fix). The flight-log Anomalies entry captures this; promote to `/agentic-workflow` skill prompt as documented rationale for the per-flight-batched-review default.
- **`cross-flight-ux-debt-reconciliation` discipline had its n=1 application in F4 itself.** The Recon Report (`flight-log.md:11-29`) walked F3 debrief items R1-R11 and classified each as "in-scope-for-this-flight" / "out-of-scope-with-reason" / "structurally-blocked-by-X." This produced a tight, defensible flight scope and explicit deferral list (R3/C3/C5a/b/mission-control items). The discipline arrested accumulation rather than just surfacing new gaps.
- **L1-codification-first leg ordering is now n=4** (F1/F2/F3/F4) — strong enough precedent to default for any flight that surfaces conventions during planning. The mechanical benefit (subsequent legs invoke conventions by name) paid off every time, including for L4's runtime decision to cite `pool-warming-entrypoints-are-finite-and-named` as the natural-extension justification for the CustomEvent pattern.
- **Architect cycle-1 catches prevented design-time bugs from reaching code.** L1's MED criterion-coverage row 2 catch dropped the compound-status prefill. L2's HIGH catch on the `_entries` vs `_pool` symbol name prevented runtime AttributeErrors across 5 test sites. L3's drift catches were cosmetic (line-number wording). All caught at cycle-1; no cycle-2 needed; no review loops > 2.
- **The L4 fold-in fix landed without scope creep.** ~20 source LOC in 2 JS files + 1 new browser test, citing the existing convention (no new ones introduced for n=1). Self-detaching listener via `!document.body.contains(state.root)` accepted as bounded leak surface with the trade-off documented inline. Operator-facing UX promise closed.
- **0 F4-introduced test regressions.** Combined 2899 pass / 6 fail / 42 skip in ~717s. The 6 failures are all carry-forward chronics (4 AIAT cluster + 2 chronic UI tests). C1 closed the 3rd chronic UI test (`test_edit_session_continuation_round_trip`), so the chronic-UI cluster trajectory is healthy.
- **The HAT-discovered UX gap was a real bug, not a spec gap.** The L4 spec was deliberately lightweight per HAT convention; the Adaptation Criteria explicitly allocated for fold-in. The lightness was the feature, not the bug.
- **F3 flight.md correction-as-annotation pattern shipped cleanly.** L4 body byte-identical; annotation under Status block; precedent now usable for any future cross-flight correction.

## What Could Be Improved

### Process

- **L2's design contract did not enumerate the UI-side propagation of warmup success.** L2's spec covered the server side (placement-after-doctor, partial-success isolation, envelope fields, three tests) but did not enumerate "Test Connection success → propagate the warmup signal to dependent UI components" as a UI-side design contract. The cycle-1 architect caught the partial-success error-surface isolation but did not walk "who else cares that the pool just got warmed?" — the L4 HAT caught the gap empirically instead. **Methodology fix**: extend the architect-checklist application of `pool-warming-entrypoints-are-finite-and-named` to require enumeration of UI consumers of warm state + verification each has a re-fetch trigger after the warmup entrypoint fires. (Important; not Critical — the HAT-before-commit framework caught the gap before it shipped.)
- **L2 leg author drafted with the wrong pool dict symbol** (`_entries` vs `_pool`). The HIGH-severity cycle-1 catch had the leg author walk 4 ACs + 3 test bodies + an import precedent. The natural recon discipline ("grep cited symbols against actual code at leg-design time") would have prevented this. **Methodology candidate**: an extension of `flight-spec-dom-order-audit` to "symbol-name-audit at leg-design" — but n=1 today; await second citation.
- **The criterion-coverage status vocabulary did not accommodate compound predecessors.** The seed left M11 row 2 (vocabulary substitution) at `open` despite F1 + F3 shipping vocabulary in many surfaces, because `partially-closed-by-F1+F3` was not in the vocabulary. The architect surfaced this; the design-review resolution dropped the prefill (safer call). **Debrief actionable**: either extend the vocabulary at this debrief or update row 2 to `partially-closed-by-F3` (under-reports F1; pragmatic).

### Technical

- **CustomEvent pattern: hardcoded event-name string in two source files.** No central constant; rename requires grep-and-replace across both files plus the test file. With one consumer pair this is acceptable; with three or four it becomes a maintenance hazard. **Trigger for refactor**: n=2 consumers OR a third file referencing the event name.
- **Self-detaching event listener has a small leak surface.** Acknowledged in the source comment. The handler removes itself only on the *next* event after DOM removal — between removal and the next event, the closure holds a reference to `state` (with `state.root` already detached). Operator-realistic risk is low (Studio tabs are coarse-grained, not rapid-mount), but worth a defensive pattern lift if a second `document.addEventListener` site emerges.
- **Broad `except Exception` in `api.py:test_connector_connection` warmup block** reduces signal on production failures. `pool_warm_error: str(exc)` captures the message but not the exception class. F9 stale-entry work may need to discriminate `ConnectorClientError` (recoverable, prompt operator) from `ConnectorRegistrationError` (config bug, surface differently) — the field shape would need to extend to carry class name. Acceptable today (field is informational only); flag for F9's surface-design phase.
- **`_labelCache = {}` conflates three distinct failure modes** (404 cold pool, 503 no-hook, network error) into one fallback path. From the operator's perspective, raw-id display is identical regardless of cause. The L3 leg's `_labelCacheFetchOk = false` flag idea was REJECTED at cycle-1 as YAGNI with explicit handoff to F9. That trade-off is sound and properly documented.
- **`_DISCOVERABLE_PAYLOAD` shape duplicated across three test files** (`test_flow_studio_per_agent_overlay_dropdown.py`, `test_flow_studio_per_agent_overlay_label_resolver.py`, `test_flow_studio_connector_discoverable_dropdown.py`). Modest fixture drift risk if the L4 endpoint schema evolves. Routine-maintenance candidate; not flight-blocking.
- **Lifespan-listener-warmup race makes cold-pool HAT non-deterministic.** On fresh container restart, the timing window between page-mount and warmup-completion determines whether the operator sees the 404 or the 200. F4 worked around it (first walkthrough caught the 404; second used the longer wait-until-ready loop). Future HATs that need to verify cold-state behaviors face the same race. **Future flight consideration**: a test-only API to evict a single warm pool entry or force-cold a pool entry would enable reliable cold-state HAT verification.

### Documentation

- **Plugin-author guide for connectors** (F3 debrief recommendation #1): NOT touched in F4. F4's scope was tight per the intervention framing — connector-form-registry public contract consolidation is correctly out-of-scope. Still open as F3 debrief Action Item; carry forward to F5+ or routine-maintenance.
- **The L4 CustomEvent pattern lacks a one-line top-comment callout.** Per the n=2 threshold, it is correctly NOT a convention today. But a one-line note in `connector-account-editor.js` and `discoverable-dropdown.js`'s top comments naming the contract (event name + payload shape) would be cheaper than reading the leg artifact for a future author. Low-effort; should land at F5 if F5 touches either file.
- **Criterion-coverage maintenance contract is untested in the wild.** F4 itself does not update its own row contributions (correct per the seed-vs-debrief-update split). This debrief is the contract's first real exercise. If this debrief fails to update rows #18 + #19 (and the row 2 vocabulary call), the contract is dead-letter. **Self-fulfilling**: see Action Items below.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| L4 HAT surfaced UX gap → folded inline into L4 commit (new CustomEvent cross-component pattern) | F4 Adaptation Criteria explicitly mandated fold-in OR Known UX Gap escalation (NOT F8/F10 deferral); the gap was operator-facing closure of A1's UX promise | **Yes — process pattern**: HAT-before-commit + Adaptation Criteria mandating fold-in is the framework that catches design-incomplete-but-spec-complete gaps before they ship. Promote rationale to `/agentic-workflow` skill prompt. |
| L4 spec was deliberately lightweight ("interactive HAT — no code implementation") but the HAT triggered a Developer spawn + commit | Lightness was DESIGN choice per HAT convention; Adaptation Criteria pre-allocated for fold-in | **No** — situational; HAT leg specs SHOULD stay lightweight, with Adaptation Criteria carrying the slack. Document only. |
| Container required `playwright install chromium` + `playwright install-deps chromium` for browser tests | Pre-existing tooling state; not introduced by this flight | **No** — tooling drift, not flight content. Routine-maintenance / Makefile candidate. |

## Key Learnings

1. **HAT-gated commit ordering converts HAT-discovered UX gaps from "follow-up PR" to "in-flight fold-in."** F4 is the n=1 proof. The framework worked exactly as designed.
2. **L1-codification-first leg ordering pays off both at code-time AND at runtime-decision-time.** L4's fold-in cited the L1-codified `pool-warming-entrypoints-are-finite-and-named` as the natural-extension justification. Codifying conventions first creates design vocabulary that survives unplanned scope changes.
3. **Spec completeness ≠ design completeness.** A spec can be complete on the server side (L2) yet leave a UI-side gap (A1's user-visible promise). Architect checklists must extend with "who else cares about this state change?" prompts for state-mutating entrypoints.
4. **The status vocabulary of a criterion-coverage map should accommodate compound predecessors.** Forcing F4 to drop row 2's prefill rather than expand the vocabulary led to silent under-reporting. The maintenance contract's first real exercise (this debrief) is the right time to fix the vocabulary or formally accept the trade-off.
5. **CustomEvent cross-component pattern is sound at n=1 but creates three architectural-debt surfaces** (hardcoded strings, self-detach hack, no centralization). Wait for n=2 before lifting to a shared studio event-bus — but flag the surfaces now so F5+ designs can either reuse the pattern or trigger the lift deliberately.
6. **Lifespan-listener-warmup race is a non-deterministic surface for HAT.** Future flights needing cold-state HATs should plan for a test-only force-cold mechanism, not just `make restart`.
7. **`cross-flight-ux-debt-reconciliation` is now operationally proven.** F4's Recon Report walked F3 debrief items explicitly and produced a defensible scope. The discipline should be promoted from project-side fallback to a real `/flight` skill-prompt prereq before F5.

## Test Metrics

Run on F4 HEAD (`216a2ad`) inside the `the-one` container, 2026-05-23.

| Tier | Pass | Fail | Skip | Wall |
|------|------|------|------|------|
| Non-browser (`-m "not browser"`) | 2478 | 4 | 7 | 226.5s |
| Browser (`-m browser`) | 421 | 2 | 35 | 490.9s |
| **Combined** | **2899** | **6** | **42** | **~717s** |

### Comparison vs prior flights

| Flight | Combined pass | Failures | Wall |
|---|---|---|---|
| M10 F8 baseline | 2331 | 10 | n/a |
| F1 | 2804 | 10 | 610s |
| F2 | ~2834 | 4 non-browser; browser hung >480s | n/a |
| F3 | 2879 | 7 | ~658s |
| **F4** | **2899** | **6** | **~717s** |

### Failure breakdown (all 6 carry-forward; 0 F4-introduced regressions)

**AIAT cluster** (4 fail; now 5 flights deep): `test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step` — signature `Agent 'default' has no provider configured`. Fixture issue; routine-maintenance candidate.

**Chronic UI tests** (2 fail; now 6 flights deep — DOWN from 3 because C1 closed `test_edit_session_continuation_round_trip`):
- `tests/browser/test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` — test expects 4 tabs; prod has 5.
- `tests/browser/test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` — visibility class drift.

### Key timing observations

- **+20 net pass (2879 → 2899)** — F4 added 7 new tests (3 + 3 + 1) plus 3 modified existing tests in `TestConnectorAccountDoctor` that extended cleanly; healthy delta.
- **Failures down 7 → 6** because C1 closed the 5-flights-deep `test_edit_session_continuation_round_trip` chronic. Trajectory on chronic-UI cluster is positive.
- **Wall +59s (658 → 717), ~9% slower** — browser tier grew +24s absorbing 4 new browser tests; non-browser tier 226.5s in-family with priors. Per-test marginal cost; nothing pathological.
- **F2-era browser-tier-hang risk did not recur** — F3 noted "watch for recurrence"; F4 ran cleanly at 490.9s.
- **AIAT cluster signature stable across 5 flights** — fixture issue, not regression.

## Recommendations

### Critical — close before F5 lands

1. **Update M11 criterion-coverage.md** per the maintenance contract this debrief is the first to exercise:
   - Row #18 + #19 → `partially-closed-by-F4` with evidence pointers to L2 + L3 + L4-fold-in + L4 HAT outcomes.
   - Row #2 → resolve the vocabulary gap. Either (a) extend the status vocabulary to support `partially-closed-by-Fn+Fm` compound predecessors and mark row #2 accordingly, or (b) update row #2 to `partially-closed-by-F3` (under-reports F1 but uses existing vocabulary). **Pragmatic recommendation**: (b) at this debrief; (a) as a separate methodology update if the pattern repeats.
   - `Last touched` column updated to F4 for any row changed.

### Important — F5+ design considerations

2. **Extend the architect-checklist application of `pool-warming-entrypoints-are-finite-and-named`** to require enumeration of UI consumers of warm state + verification each has a re-fetch trigger after the warmup entrypoint fires. This would have caught L2's UI-side gap at design review rather than at HAT.

3. **The CustomEvent cross-component pattern is sound at n=1; don't reflexively adopt it at F5.** F5 (peer-name attribution) likely surfaces similar cross-component freshness concerns. Diagnose freshness needs per surface — lazy-on-expand fetches (like L3's label cache) are immune to staleness that mount-once components face. If F5 produces a second instance, codify a `cross-component-event-bus-naming` convention (or extend `pool-warming-entrypoints-are-finite-and-named`) and lift the pattern to a shared `App.studio.eventBus` utility addressing the three architectural-debt surfaces (hardcoded strings, self-detach hack, no centralization).

4. **Cite the new L1 conventions explicitly at F5 design.** `pool-warming-entrypoints-are-finite-and-named`, `two-concurrent-callers-reasoning`, `cross-flight-ux-debt-reconciliation`, and `touched-surface-ux-debt-folding` are now binding. F5's recon report should walk F4 debrief items as a `cross-flight-ux-debt-reconciliation` application.

5. **If F5 touches `_renderAccountTile`** — the L3 closure-scoped helpers (`_labelCache`, `_ensureLabelCache`, `_applyLabelsToCheckboxes`) are load-bearing. Reuse or extend in-place; do not fork.

6. **If F5 touches `discoverable-dropdown.js`** — the `state.poolWarmHandler` self-detach contract must be preserved. If multiple new handlers get added to `state`, the cleanup logic should iterate all of them. Consider a `state._eventHandlers = {}` map pattern if a second handler emerges.

7. **If F5 touches `test_connector_connection`** — the `details.pool_warmed` / `details.pool_warm_error` envelope shape is now a contract pinned by 3 tests + the chrome-MCP HAT recipe + the L4 event listener. Don't remove fields without updating downstream consumers.

### Methodology — promote to mission-control skills

8. **Promote `cross-flight-ux-debt-reconciliation` from project-side fallback to a real `/flight` skill-prompt prereq** before F5. F4 proved the discipline operationally; the project-side note in `agents.md` is the binding fallback but the primary destination is the skill prompt.

9. **Add to `/agentic-workflow` skill prompt: documented rationale for per-flight-batched-review default** — citing F4 L4 fold-in as the n=1 reference for why HAT-before-commit catches design-incomplete-but-spec-complete gaps.

10. **Add to `/flight-debrief` skill prompt: status-vocabulary gaps surface as silent under-reporting** — citing F4 row #2 as the n=1 example. The debrief should explicitly check for compound-predecessor situations and either extend the vocabulary or accept the under-report.

### Important — refactoring opportunities (defer unless trigger fires)

11. **CustomEvent pattern → shared studio bus** when a second consumer emerges (n=2 trigger).
12. **`_labelCache` helpers → reusable cache utility** if a second tile-local async cache emerges.
13. **`_DISCOVERABLE_PAYLOAD` shape → shared `tests/browser/fixtures/discoverable_entities.py`** to prevent fixture drift.
14. **Lift `_xxxValues` getter pattern** (carryover from F3 debrief) — F4 did not touch; carry forward.
15. **Lift axis vocabulary** (carryover from F3 debrief) — F4 did not touch; carry forward.
16. **Remove `_RegistryEntry.account_type=""` backwards-compat default** (carryover from F3 debrief) — F4 did not touch; carry forward.

### Routine-maintenance candidates

17. **AIAT 4-test cluster** — `@pytest.mark.skip` or seed AIAT fixture with default provider. Now 5 flights deep.
18. **Chronic UI tests** (2 remaining: `test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`) — update tests to match prod. Now 6 flights deep.
19. **L4 doc-only `prior_cache` race-safety** (carryover from F3 debrief).
20. **Container playwright install one-off** — should be in `make rebuild` or Dockerfile.

## Action Items

### Immediate (before F5 planning)

- [ ] Update `missions/11-discord-connector-depth/criterion-coverage.md` rows #2, #18, #19 per Critical recommendation #1.
- [ ] Add a one-line comment in `connector-account-editor.js:renderTestConnectionBanner` and `discoverable-dropdown.js:discoverableDropdown` naming the `connector-account-pool-warmed` event contract (event name + `detail: {accountId}` payload).
- [ ] F5 architect briefing: cite the new L1 conventions explicitly at F5 design; honor the L3 + L4 contracts listed in recommendations #5/#6/#7.

### Methodology (before F5 planning)

- [ ] Surface to mission-control: promote `cross-flight-ux-debt-reconciliation` to `/flight` skill prereq.
- [ ] Surface to mission-control: document HAT-before-commit rationale in `/agentic-workflow` skill prompt.
- [ ] Surface to mission-control: `/flight-debrief` should check for status-vocabulary gaps producing silent under-reporting.

### Near-term (before F6)

- [ ] Plug the F4 PR #72 merge sequencing decision (stacked behind F3 PR #71 today).
- [ ] Test for cross-component event listener leak path (DOM removed before event fires; self-detach on subsequent event).
- [ ] Test for multi-axis tile single-flight contract (expand 2 checkbox-mode axes; assert one GET).

### Routine-maintenance candidates (slot for `/routine-maintenance` or fold into next touched-surface flight)

- [ ] C3 AIAT cluster — fixture fix.
- [ ] C5a/b chronic UI tests — update to match prod.
- [ ] Plugin-author guide for connectors (F3 carryover).
- [ ] Unify `_xxxValues` getter pattern (F3 carryover).
- [ ] Lift axis vocabulary to `App.studio.connectorAxes` constant (F3 carryover).
- [ ] Remove `_RegistryEntry.account_type=""` backwards-compat default (F3 carryover).
- [ ] L4 `prior_cache` force-interleaving test (F3 carryover).
- [ ] Shared `tests/browser/fixtures/discoverable_entities.py` for `_DISCOVERABLE_PAYLOAD`.
- [ ] Container playwright install one-off → `make rebuild` or Dockerfile.
