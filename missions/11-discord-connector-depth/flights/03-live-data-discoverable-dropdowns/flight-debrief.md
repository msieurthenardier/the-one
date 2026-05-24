# Flight Debrief: Live-Data Discoverable Dropdowns

**Date**: 2026-05-22
**Flight**: [Live-Data Discoverable Dropdowns](flight.md)
**Status**: landed
**Duration**: 2026-05-22 (single-session execution)
**Legs Completed**: 7 of 7 (L1, L2, L3, L4, L5, L6a, L6b, L7) — L7 HAT 8/10 PASS + 1 deferred + 1 partial

## Outcome Assessment

### Objectives Achieved

F3 closed two M11 mission criteria contributed-to:
- **Allowlist editor swaps free-form chip-lists for searchable dropdowns** sourced from the live bot view, with vocabulary substitution (`Users`/`Channels`/`Servers`/`Roles` for Discord vs `peers`/`channels`/`groups`/`roles` at the substrate). 4 axes, all live against gleepglorp.
- **Routing-rules editor's match-value input uses the same searchable-dropdown data source** with scope→axis mapping (channel/thread → channels, dm/peer → peers).

The substrate (L3 hook + L4 cache + API) generalizes cleanly to future Slack/Matrix connectors. The Studio dispatch (L5 component + L6a/L6b registry-mediated mounts) preserves the M10 chip-list fallback for stub-type accounts byte-identically — the regression contract held.

### Mission Criteria Advanced

| M11 criterion | Status after F3 |
|---|---|
| #3 — allowlist editor: searchable dropdowns + live-bot-view + stale-entry indicator | ✅ structurally complete; ⏸ stale-entry indicator deferred to operator-side verification |
| #4 — routing-rules editor: searchable-dropdown match values | ✅ closed; structural "operator typed `#channel-name`, got 'No agents available'" failure mode prevented |
| #14 — operator-editable per-account system-prompt directive | (closed earlier at F2) |
| #16 — pool-keying refactor closes M10 critical action | (closed earlier at F2) |
| #18 — fifteen-minute fresh-operator walkthrough | Substrate-ready; UX gaps in this debrief threaten this criterion (see UX-Debt Accumulation below) |
| #19 — full working-day daily-driver | Substrate-ready; pool-warming friction (HAT anomaly #1) breaks the cold-restart path |

## What Went Well

- **Race-safety invariants held against real Discord traffic.** L4's "do NOT touch `last_activity`" rule, `prior_cache` read inside the re-acquired lock, identity check on `client`, and `_shutting_down` bail-after-re-acquire — all four design-time-discovered (cycle-1) decisions held during the HAT walk. `test_refresh_loop_does_not_touch_last_activity` is the durable pin.
- **Architect-checklist methodology continued to catch HIGH-severity issues at cycle-1.** Every leg in F3 had cycle-1 catches that the cycle-0 design missed. Same posture as F1 and F2. The methodology is operationally tuned.
- **L1-codification convention extends gracefully.** F3 L1 added `primitive-rename-test-classification` + `flight-spec-dom-order-audit`; F3 L5 closed the n=4 → n=5 citation drift on `optional-registry-entry-hook` (silently broken since F2 L4). The leg-1 codification pattern is now n=3 of its own use across F1/F2/F3.
- **F2 browser-tier hang is RESOLVED.** F2 debrief documented the studio browser tier as hanging past 480s. F3's full suite ran cleanly in 658s combined (191.5s non-browser + 466.78s browser). Container restart at F3 + clean F3 fixture additions appear to have cleared the stuck state. **Watch this — may recur.**
- **L2 closed a 3-flight-deep chronic-debt cluster.** All 3 `status:'ok'` tests in `test_connector_test_connection_button.py` were updated to assert hidden details panel per the M07 inspector-convention production shape; all 7 tests pass first run.
- **F3 introduced zero new test regressions across +45 added tests.** All 7 carry-forward failures are pre-existing (4 LLM-flaky AIAT cluster from M10 F8; 3 chronic UI tests from F1 debrief).
- **L5 component LOC ceiling held via the documented tighten-or-extract loop.** First cut 750 LOC → tightened to 648 (consolidated GET+POST fetch handlers into one `_doFetch` helper). The flight Adaptation Criteria worked as designed.
- **The L6a + L6b split held.** Architect cycle-1 recommended NOT merging. Final ship: L6a allowlist (~85 LOC + tests), L6b routing+overlay (~163 LOC + tests). Merging would have crossed atomic-leg-pattern's "single coherent surface" threshold.

## What Could Be Improved

### Process

- **Cross-flight UX-debt reconciliation is missing from Reconnaissance Reports.** F3's recon table walked the F2 debrief items (R1-R17) but did NOT walk the M10 mission-debrief deferred-UX items. The M10 debrief still carries 8 open UX items that no F1/F2/F3 recon has cross-checked.
- **Touched-surface UX-debt folding is not enforced.** F3 L6b touched `connectors-tab.js` (per-agent overlay) but did NOT inspect the checkbox-mode rendering for UX gaps. The L6b leg artifact explicitly carved checkbox-mode OUT of scope because "no chip-list to convert" — the leg stopped at the dispatch-pattern layer rather than walking the operator-end-to-end task.
- **HAT step deferrals lack explicit follow-up commitments.** L7 step 8 (stale-entry indicator) was deferred to operator-side Discord action; no AC enforces when/how it gets verified. The step's verification path required three coordinated operator-side actions that the leg design didn't budget for.
- **Recon should default-walk L1 codifications as binding constraints at cycle-0.** Two of F3's three cycle-1 HIGH catches (L2 test-cluster scope; L3 Protocol-widening direction) would have been cycle-0-discoverable if the architect had treated the L1-codified conventions as a checklist at cycle-0 rather than at cycle-1.

### Technical

- **Three near-identical getter conventions** (`_allowlistValues`, `_routingMatchValues`, `_overlayChipValues`) installed on different slot types. The pattern is durable but the per-surface naming is debt. Recommend unifying as a single shared helper `_installCollectGetter(slotEl, fn)` and naming convention.
- **Axis vocabulary appears in JS at 3+ sites.** L6a allowlist mapping + L6b routing scope→axis mapping + L6b per-agent overlay mapping. Should lift to a shared `App.studio.connectorAxes` constant.
- **`_RegistryEntry.account_type=""` default is backwards-compat scaffolding.** Two direct-construct test sites (`tests/test_oauth_start_endpoint.py:105`, `tests/test_connectors_pool.py:479`) rely on it. Future `_RegistryEntry` refactors must keep the empty-string filter or migrate those tests.
- **L4 `prior_cache`-read-inside-the-lock race-safety contract is doc-only.** No test forces an interleaving of two refresh paths. Acceptable per leg artifact's stated trade-off but listed here for future readers.
- **AbortController fetch-race pattern in `discoverable-dropdown.js` could be lifted to a shared studio helper.** Other studio fetch surfaces (Test Connection, doctor probe) could benefit.

### Documentation

- **Plugin-author's guide for `enumerate_discoverable_entities`** does not exist. When M12 adds a second connector (Slack/Matrix), the author needs a one-page reference; currently the L3 leg artifact is the only source.
- **`Test Connection ≠ pool-warm` mental model is undocumented.** The L4 design explicitly assumed they were coupled and that assumption is wrong; either fix the code (action item) or document the actual separation.
- **Mission-criteria coverage map for M11 is not maintained as a living artifact.** M10 mission-debrief recommendation #5 ("Add `criterion → evidence/test` map as a mandatory mission artifact") has gone un-actioned. F3's mission-criteria status is only knowable by reading 3 flight artifacts + the mission.

## UX-Debt Accumulation (Operator's Lead Concern)

The operator's stated concern — *"UX fixes are being pushed off and accumulating, the UX is quite poor"* — is **substantiated by the artifact trail**. Both crew debrief agents converged on this independently.

### Net UX-debt position at F3 close

**Worse than at F3 start.** F3 added two new HIGH-severity UX items to the deferred queue, partially closed one M10 UX item (B8 routing-rules dropdown), did NOT retire any of the 8 open M10 UX items.

### F3-discovered, deferred to follow-up

| # | Issue | Severity | Recommended path |
|---|---|---|---|
| A1 | **Test Connection does NOT warm the pool.** Dropdowns 404 with pre-probe hint immediately after Test Connection succeeds. L4 design explicitly assumed Test Connection populated the pool via lifespan-warmup; the assumption is structurally false. The operator sees green Test-Connection LED + 404 dropdown = cognitive dissonance. | HIGH (substrate-contract reversal at UX layer) | Wire Test Connection click handler to also call `account_acquire(account_id)`. ~10 LOC. **Fix BEFORE F4 or as F3.1 hotfix.** |
| A2 | **Per-agent overlay checkbox-mode shows raw Discord snowflake IDs** (e.g. `1506831630923333722`) instead of friendly labels (`#gleepglorp-text`). Confirmed at `connectors-tab.js:507`. | HIGH (operator literally cannot identify which UI element refers to which entity) | Inject discoverable-entities-cache label-resolver against checkbox-mode renderer. ~30-50 LOC. **Fix in F4 or in conjunction with A1.** |
| A3 | **Stale-entry indicator never operator-verified live.** L7 step 8 deferred; API contract pinned by tests but DOM rendering loop not walked. | MEDIUM | Either (a) script the kick via discord.py second-bot in F8 HAT, or (b) accept API-test as sufficient + document a manual verification step in the M11 mission criteria coverage map. |
| A4 | **Scope-change in routing-rules clears match values.** L6b's "simpler semantics" decision; operator's work is lost if they change scope. | LOW-MED | Toast hint at scope-change, or preserve when axis mapping is unchanged. |
| A5 | **No filter-narrowing hint visible below 1000 entries.** Naive render in L5 means large guilds (hundreds of channels) render naïvely. | LOW (theoretical; no live encounter against gleepglorp) | Defer until HAT against a large guild surfaces it. |

### M10-discovered, still deferred (cross-checked from M10 mission-debrief)

| # | Issue | Severity | Status |
|---|---|---|---|
| B1 | **`peer_name` data-model thread-through (Bug C; 6 surfaces).** Inbound platform messages show only `peer_id` to agents and Chat UI attribution. | **CRITICAL per M10 debrief** | **Still deferred.** M11 F4 ("peer-name attribution") is the named flight; **NOT YET PLANNED.** This is now the most-deferred-CRITICAL item across both missions. |
| B4 | Live-traffic multi-agent routing HAT against real Discord. | HIGH | Still deferred. M11 F8 scope. |
| B5 | Real-platform DM pairing HAT. | HIGH | Still deferred. M11 F8/M12 scope. |
| B6 | Rate-limiting + backpressure live-load HAT (M10 criterion #23 NOT MET). | HIGH | Still deferred. F8/F9 scope. |
| B7 | Audit-log inspector UI for `session_metadata["routing"]`. | MEDIUM | Still deferred. M11 F7 named. |
| B9 | Plugin-handler-timeout, ephemeral slash-command responses, idle-eviction exemption for listener entries. | MEDIUM | Still deferred. |
| B10 | Chip-input placeholders not vocabulary-substituted (chip-list fallback for stub-type accounts retains generic placeholders). | LOW | F10 Alignment scope. Partially-mooted at dropdown surface (vocab substituted in L5). |
| B11 | Discord create-form visual rhythm cramped (intent checkboxes, Guilds + Presence). | LOW | F10 Alignment scope. |

### Cross-flight chronic carry-forwards

| # | Issue | Severity | Age | Path |
|---|---|---|---|---|
| C1 | `test_edit_session_continuation_round_trip` — test expects `"Distinct from the pool idle timeout"`; source says `"Inbound continues the same chat session within this window."` | LOW (one-line fix) | **5 flights deep** (since F1 debrief) | **Land in F4 L1 or routine-maintenance.** |
| C2 | Routing-rules scope-selection mental model: operator must know `channel` vs `peer` scope maps to different axes. | LOW-MED | M10 F8 + F3 L6b | Tooltip on scope dropdown. |
| C3 | AIAT 4-test cluster (`test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step`). Signature: `Agent 'default' has no provider configured`. | LOW (fixture gap; not UX) | **4 flights deep** | Routine-maintenance: skip with `@pytest.mark.skip(reason=...)` or seed a provider in the AIAT fixture. |
| C5a | `test_tablist_renders_with_three_tabs` (test expects 3-4 tabs; prod has 5). | LOW | F1+ | Routine-maintenance. |
| C5b | `test_studio_section_round_trip_preserves_agent_selection`. | LOW | F1+ | Routine-maintenance. |

### Root cause of the accumulation pattern

The artifact trail surfaces a 4-step structural pattern:

1. **HAT or operator-feedback discovers a UX issue.**
2. **The issue gets logged as deferred** to a perpetually-future flight ("F8 HAT," "F10 Alignment," "follow-on Discord-depth mission," etc.).
3. **A subsequent flight DOES touch the same code surface.**
4. **But the deferred UX item is NOT folded in** because (a) the flight's contributing-criteria framing is narrow, and (b) the prior deferral signal lives in a debrief artifact the new flight's recon doesn't cross-check.

F3 is the n=1 trigger for breaking the pattern at the methodology layer. The recommendations below are calibrated to that.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| L4 introduced `_DiscoverableCacheSnapshot` frozen-triple-dataclass (not in cycle-0 design) | Cycle-1 caught read-side race when handler reads multi-field cache state outside lock | **Yes** — pattern `frozen-snapshot-for-cross-lock-read` |
| L5 dropped scroll-virtualization → naive render (not in cycle-0 design) | Cycle-1 LOC-budget re-estimate (300-400 → 500-800 → tightened to 648) | **No** — situational de-scope; trade-off documented in Adaptation Criteria |
| L6a/L6b added `_xxxValues` getter pattern (not in cycle-0 designs) | Cycle-1 caught chip-list vs dropdown chip-shape incompatibility in `collectAllowlistFromContainer` text-node walk | **Yes** — pattern `slot-getter-bridge-for-dropdown-collect-path`; unify the 3 per-surface names |
| L7 step 8 (stale-entry indicator) deferred to operator action | Verification path required 3 operator-side Discord actions not budgeted at design time | **Process change** — HAT steps requiring operator-side actions must be explicitly marked at design time with a deferred-by-design AC |
| Container restart required to pick up F3 Python code | `_RegistryEntry` pre-F3 entries had `account_type=""` and were sweep-filtered; combined with 30-min TTL idle eviction | **No** — expected behavior per `lifespan-wiring-same-leg-as-installation`; document in deployment runbook |

## Key Learnings

1. **The architecture-UX dichotomy is real and is being pushed too hard.** F1-F3 each shipped substrate-correct work and accumulated small UX deficits. By F4-F5-F6 the cumulative drift will be material. M11 mission criterion #18 ("fresh operator under fifteen minutes") and #19 ("full working day daily-driver") **structurally depend** on closing the deferred-UX queue. Substrate excellence is necessary but not sufficient.

2. **Test Connection is the wrong primitive to assume warms the pool.** The L4 design conflated `plugin.doctor()` (which Test Connection calls) with `account_acquire` (which actually populates `_pool`). The grep `grep -n "account_acquire" the_one/interfaces/web/api.py` at design time would have returned zero hits in the Test Connection handler. This is a checklist gap the F1+F2 codified Architect-checklist did not catch.

3. **L1 codifications work but need cycle-0 enforcement.** F1 codified `optional-plugin-hook-via-getattr-sentinel` and `optional-registry-entry-hook`; F2 codified `lifespan-wiring-same-leg-as-installation` and `atomic-leg-pattern`. Each had to be re-applied via cycle-1 review rather than treated as binding constraints at cycle-0. The next-best discipline: at cycle-0, the architect walks the L1 codifications and explicitly accept-or-defer each.

4. **Cycle-1 race-reasoning has limits.** L4's three race-safety catches are at the edge of pre-HAT race-reasoning. Two concurrent invocations through a helper are not naturally modeled by a sketch-based cycle-0 design. The discipline of "two concurrent callers" should join "grep cited symbols / walk paths / verify constants" in the Architect checklist.

5. **The "fold into F8/F10/follow-on-mission" pattern is the structural source of UX-debt accumulation.** F8 (HAT script) and F10 (Alignment) are perpetually-future flights. As long as deferring to them is the path of least resistance, the queue grows. **Concrete cure**: any flight that adds an item to F8 or F10 scope MUST also propose a near-term partial fix.

6. **`_RegistryEntry.account_type=""` default is technical-debt-by-design**, deliberately introduced to preserve direct-construct test sites. This is the right call (small, named, contained), but it should be removed when F4+ touches the pool — track in the M11 known-debt list.

## Recommendations

### Critical — methodology changes to arrest UX-debt accumulation

1. **Add `cross-flight-ux-debt-reconciliation` as a Reconnaissance Report requirement.** Every flight's recon must include a section walking the prior 2-3 flight debriefs' AND the parent mission-debrief's deferred-UX items, classifying each as "in-scope-for-this-flight" / "out-of-scope-with-reason" / "structurally-blocked-by-X." Codify in `/flight` skill.

2. **Codify `touched-surface-ux-debt-folding`.** When a flight touches a code surface (file or component), the architect must enumerate all open UX-debt items against that surface from prior debriefs and either fold them in or explicitly state why they're left. F3 touched `connectors-tab.js` and missed A2 (raw-id labels) — this convention would have caught it at design review.

3. **Codify `pool-warming-entrypoints-are-finite-and-named` and audit all uses.** The L4 design's "Test Connection warms the pool" assumption was undetectable at design review because the architect cited the lifespan-warmup precedent without grepping the Test Connection click handler. Future flights touching pool-warming must explicitly enumerate the entrypoints and validate the operator's expected trigger lands on one.

4. **Add a UX-acceptance-test gate to flight scoping.** Every flight artifact's Design section includes a "Operator E2E flow" subsection that walks the operator's full task from button-click through verification. The walk surfaces transitions like Test Connection → pool warming that current design treats as out-of-band.

5. **Make F10 (Alignment) non-optional, OR require each flight's debrief to inventory deferred UX items and re-classify them.** F10's `(optional)` marker creates a structural incentive to defer UX polish to a flight that may never happen.

### Important — near-term UX fixes (before F4 or as F3.1 hotfix)

6. **Fix A1 (Test Connection warms pool)**. Smallest, highest-impact UX fix surfaced by F3. ~10 LOC. Closes the substrate-contract reversal between L4 design and operator experience. **Strong recommendation: ship as F3.1 hotfix, not deferred to F4.**

7. **Fix A2 (per-agent overlay checkbox-mode labels)**. ~30-50 LOC. Closes operator-cannot-identify-checkbox-target UX gap. Fold into F4 or pair with A1 as a sibling F3.1 hotfix.

8. **Fix C1 (`test_edit_session_continuation_round_trip`)**. One-line fix. 5 flights deep. Pin in F4 L1 or routine-maintenance.

### Important — refactoring opportunities

9. **Unify the `_xxxValues` getter pattern** into a shared `_installCollectGetter(slotEl, fn)` helper. The three per-surface variants in L6a/L6b are mechanical near-duplicates.

10. **Lift the axis vocabulary** (`peers`/`channels`/`groups`/`roles`) to a shared `App.studio.connectorAxes` constant. Currently duplicated at 3+ JS sites.

11. **Lift `_doFetch` AbortController pattern** to a shared studio fetch helper if a second consumer emerges.

### Methodology — codify new conventions in agents.md

12. **`frozen-snapshot-for-cross-lock-read`** (L4 `_DiscoverableCacheSnapshot` pattern). n=1; codify on the "first n=1 by methodology-promotion" precedent (per `registry-dispatch-create-mode-AC` shape).

13. **`slot-getter-bridge-for-dropdown-collect-path`** (L6a/L6b pattern). n=3 within F3.

14. **`stub-fixture-extension-via-plugin-connect`** (L3 + L4 pattern). n=2.

15. **`pool-warming-entrypoints-are-finite-and-named`** (L4-design-miss prevention). n=1 by methodology-promotion.

16. **`two-concurrent-callers-reasoning`** Architect-checklist extension. n=3 within L4 alone.

### Methodology — promote M11 F8 (HAT-script flight) priority

17. The F2 debrief recommended "promote F8 once F3-F5 ship." F3 is shipped. **Recommend bumping F8 ahead of F4 if the operator wants to fix the chronic browser-test cluster AND automate the HAT walk simultaneously.** F8's `discord.py`-as-second-bot capability would also unblock A3 (stale-entry verification) without operator-side action.

### Mission-scope amendment

18. **Add "shippable UX" as an explicit M11 success criterion** with per-flight gates. Promote the current criterion #18 ("operator under fifteen minutes") from a final-validation-gate to a per-flight UX-acceptance-test gate.

19. **Maintain a `criterion → evidence/test` map** as a continuously-updated M11 artifact (per the M10 mission-debrief recommendation that has gone un-actioned).

## Action Items

### Immediate (before F4)

- [ ] **A1 hotfix: Test Connection calls `account_acquire`** — ~10 LOC; closes the substrate-contract reversal between L4 design and operator experience
- [ ] **A2 hotfix: per-agent overlay checkbox-mode label resolver** — ~30-50 LOC; closes the operator-cannot-identify-checkbox-target gap
- [ ] **C1 fix: update `test_edit_session_continuation_round_trip`** — one-line; 5 flights deep
- [ ] **Plan M11 F4** (peer-name attribution; Bug C; CRITICAL per M10 debrief — most-deferred-CRITICAL item; named but not yet planned)

### Methodology (before F4 planning)

- [ ] Codify `cross-flight-ux-debt-reconciliation` requirement in `/flight` skill's recon section
- [ ] Codify `touched-surface-ux-debt-folding` requirement in `/flight` skill's design section
- [ ] Codify `pool-warming-entrypoints-are-finite-and-named` in `agents.md` Project-wide
- [ ] Codify `frozen-snapshot-for-cross-lock-read` in `agents.md` Project-wide
- [ ] Codify `slot-getter-bridge-for-dropdown-collect-path` in `agents.md` Project-wide
- [ ] Codify `two-concurrent-callers-reasoning` Architect-checklist extension in mission-control's `/leg` design-review prompt
- [ ] Start `criterion → evidence/test` map as a living M11 artifact

### Mission scope

- [ ] **Promote M11 F8 ahead of F4** if operator wants chronic-browser-test cluster fix + HAT automation simultaneously
- [ ] **Add "shippable UX" success criterion** to M11 with per-flight UX-acceptance-test gate
- [ ] **Decide F10 fate**: non-optional, OR require per-flight UX-deferral inventory

### Routine maintenance candidates

- [ ] C3: AIAT 4-test cluster — `@pytest.mark.skip` or seed AIAT fixture with default provider
- [ ] C5a/b: `test_tablist_renders_with_three_tabs` + `test_studio_section_round_trip_preserves_agent_selection` — update tests to match prod
- [ ] L4 doc-only `prior_cache` race-safety — add a force-interleaving test
- [ ] Unify `_xxxValues` getter pattern into `_installCollectGetter`
- [ ] Lift axis vocabulary to `App.studio.connectorAxes` constant
- [ ] Remove `_RegistryEntry.account_type=""` backwards-compat default once direct-construct test sites are migrated

### Documentation

- [ ] Plugin-author's guide for `enumerate_discoverable_entities` (M12 dependency)
- [ ] Document `Test Connection ≠ pool-warm` mental model in connector-account-editor top-comment (if A1 not landed) OR remove the L4 design's stale assumption (if A1 landed)

## Test Metrics

Suite ran 2026-05-22 post-L7 HAT.

| Tier | Pass | Fail | Skip | Wall |
|------|------|------|------|------|
| Non-browser (`--ignore=tests/browser -m "not pixel"`) | 2463 | 4 | 7 | 191.5s |
| Browser (`-m browser`) | 416 | 3 | 35 | 466.78s |
| **Combined** | **2879** | **7** | **42** | **~658s** |

### Comparison vs prior flights

| Flight | Combined pass | Failures | Wall |
|---|---|---|---|
| M10 F8 baseline | 2331 | 10 | n/a |
| F1 | 2804 | 10 | 610s |
| F2 | ~2834 | 4 non-browser; browser hung >480s | n/a |
| **F3** | **2879** | **7** | **~658s** |

### Failure breakdown (all 7 carry-forward; 0 F3-introduced regressions)

**AIAT cluster** (4 fail; 4 flights deep; LLM-fixture flakes):
- `tests/test_aiat.py::test_basic_chat`
- `tests/test_aiat.py::test_tool_use_file_read`
- `tests/test_aiat.py::test_self_awareness`
- `tests/test_aiat.py::test_multi_step`

Signature: `Agent 'default' has no provider configured`. Documented across M10 F8 → M11 F1 → F2 → F3.

**Chronic UI tests** (3 fail; 5 flights deep):
- `tests/browser/test_flow_studio_connector_account_editor.py::test_edit_session_continuation_round_trip` — text drift; one-line fix
- `tests/browser/test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` — test expects 3-4 tabs; prod has 5
- `tests/browser/test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` — visibility class drift

### Key timing observations

- **F2 browser-tier hang RESOLVED.** F2 debrief documented browser-tier hanging past 480s; F3 ran cleanly at 466.78s. Container restart at F3 + clean F3 fixture additions likely cleared stuck state. **Watch for recurrence.**
- **F3 added +45 tests; +75 net pass (vs F2's ~2834)** with no regression.
- **Combined ~658s wall** is roughly 8% above F1's 610s. The combined-runner increase aligns with the new browser test files L5 contributed (7 dropdown + 1 registry + 6 allowlist + 6 routing + 2 overlay = ~22 new browser tests). Acceptable.
