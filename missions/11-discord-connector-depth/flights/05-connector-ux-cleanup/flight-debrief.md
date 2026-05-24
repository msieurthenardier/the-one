# Flight Debrief: Connector UX Cleanup

**Date**: 2026-05-24
**Flight**: [Connector UX Cleanup](flight.md)
**Status**: landed
**Duration**: 2026-05-23 (planning + L1-L5 commit) → 2026-05-24 (L6 8-round HAT + commit + debrief)
**Legs Completed**: 6 of 6 (L1 + L2 + L3 + L4 + L5 + L6 — L6 iterated through 8 HAT rounds)

## Outcome Assessment

### Objectives Achieved

F5 was operator-requested UX cleanup of cumulative connector-editor debt before F6 (peer-name attribution). The flight closed:

- **L1**: Form controls re-classed to canonical sdcon primitives (Intents → `.checkbox-primary`; Auto-relay → `tool-enable-switch`; text inputs → `.field-input`; selects → `.field-select`; Type-dropdown placeholder suppressed post-pick).
- **L2**: Test Connection + Invite folded inside Connection section as footer-row (mirrors MCP `mcp-test-row` placement).
- **L3**: Runtime config moved General → Access-and-Routing tab via new optional `renderRuntimeConfigFields` registry hook; verbose `<small>` blocks replaced with `.field-info-icon` tooltips; "Servers" disambiguated (Discord-context = "Scope to servers"; GUILDS intent = "Server info"); Auto-relay label rewritten "Auto-relay peer replies to platform" → "Auto-reply to platform messages".
- **L4**: Per-axis containment on agent's Connectors tab via `.connector-acl-axis-body` border-left + padding + surface-elevated background; empty Selected entries chip container hidden via `hidden` attribute + companion specificity-override CSS rule.
- **L5**: Element-by-element sweep of 6 surfaces (~85 elements enumerated); 0 inline fixes needed; 5 deferrals to future UX maturity mission (D1-D5).
- **L6**: 8 rounds of operator-driven HAT iteration:
  - **R1**: Type-placeholder `hidden` attr; Lifecycle relabels + reorder; create-mode runtime-config preservation via shared `_renderRuntimeConfigBody` helper; Bot Token 3-column layout.
  - **R2**: Intents fieldset → "Receive messages from:" label + sentence-case checkboxes; Servers ↔ "Scope to servers" disambiguation; Advanced → always-visible "Additional Config"; Bot status verb-options.
  - **R3**: Info-icons refactored OUT of label cells into sibling position; 3-column rhythm propagated to Runtime Config + Access sections.
  - **R4**: Section reorg — Discord → Access → Routing → Session (was Lifecycle → Runtime Config → Allowlist → Routing rules); friendly description under each terse header via new `.section-description` primitive.
  - **R5**: Section-level pre-probe banner + Refresh button at Access top; per-axis Refresh + pre-probe hints dropped; new `connector-account-discoverable-refresh-requested` event channel; Routing Default-agent info-icon.
  - **R6**: Intra-Access banner→Peers gap reduced 12px → 8px to match inter-axis baseline.
  - **R7**: Duplicate "Discord probe ok" status block removed; Invite section → 3-column with icon-only Copy + Refresh; banner Refresh always visible; banner copy rewritten "Refresh connection to populate the discoverable lists."
  - **R8**: System Prompt Directive section removed from General tab; 3 substrate directives collapsed to 2 (OFF directive hedged "if the `send_to_platform_channel` tool is available"); operator-editable override removed (mission criterion #14 partially reverted); effective directive shown as styled codeblock under Auto-reply toggle in Session, reactive to toggle state.

### Mission Criteria Advanced

| M11 criterion | Status after F5 |
|---|---|
| #1 — Discord-shaped form | `closed-by-F1+F5` (F5 re-styled to design language) |
| #2 — Discord-shaped vocabulary | `closed-by-F5` (verbose technical labels → human-friendly + info-icon tooltips) |
| #14 — operator-editable system-prompt directive | **closed-by-F2 → PARTIALLY REVERTED by F5 L6 R8** (per operator decision; substrate defaults visible in styled codeblock, but per-account operator override removed) |
| #18 — fresh operator under fifteen minutes | `partially-closed-by-F5` (cumulative UX polish reduces visual friction; HAT iterated 8 rounds) |
| #19 — full working-day daily-driver | `partially-closed-by-F5` (operational consistency between MCP editor + connector editor) |

## What Went Well

- **The "primitives-first → section-shape → sweep → HAT" leg ordering was vindicated.** L1's re-classing landed the primitive vocabulary L2/L3 then referenced unchanged. L5 sweeping post-L1-L4 state (not pre-flight state) caught cross-cutting consistency invisible at planning time. No leg re-ordered; no leg sharded.
- **Chrome MCP for in-flight verification throughout L1-L5** (not just HAT) caught visual issues at leg-design tightening. The L4 computed-style probe via `evaluate_script` confirmed `getComputedStyle === "none"` actually fires — much stronger verification than "the test passes." Methodology improvement over F4's HAT-only Chrome MCP usage is unambiguously positive.
- **`cross-flight-ux-debt-reconciliation` discipline had its n=2 operational proof.** F5's Recon Report classified all 10 enumerated items with no drift, no surprises. Discipline now has enough weight to graduate from project-side fallback to `/flight` skill prereq.
- **Architect cycle-1 catches prevented design-time bugs from reaching code.** L1's HIGH on `_entries` vs `_pool` symbol drift; L3's HIGH on create-mode regression (preserved via shared `_renderRuntimeConfigBody`); L4's HIGH on `[hidden]` specificity override + extending-not-duplicating existing CSS rule. All caught at cycle-1; no cycle-2 needed; no review loops > 1.
- **`_renderRuntimeConfigBody` shared helper for create-mode + edit-mode** is a clean single-source-of-truth. Sustained through R5's "hide create-mode runtime config" round-1 fold-in without re-introducing duplication.
- **Two event channels coexist cleanly.** `connector-account-pool-warmed` (F4 auto-on-Test-Connection-success) and `connector-account-discoverable-refresh-requested` (F5 R5 manual-from-section-banner) listened side-by-side with distinct dispatch semantics. R5's "auto vs manual gets its own named channel" discipline avoids the "one event channel grows N implicit meanings" anti-pattern.
- **The 3-column field-row pattern propagated consistently** across Lifecycle / Discord / Access / Routing sections (pixel-identical alignment confirmed by L5 sweep: label-left=280, info-icon-left=392, field-left=418).
- **HAT-as-leg with 8 rounds scaled.** The same-leg inline-fold-in pattern stayed atomic; no L7 or follow-up PR opened. Cumulative-debt cleanup naturally produces escalating-tightening rounds (row → IA → affordance → criterion); F5 R1-R8 demonstrated this is sustainable.
- **L5 sweep produced zero inline fixes** — every visible element on 6 surfaces mapped to existing primitives or was captured as a deferral. The abort threshold of ~25 LOC was never approached. The "NO new UI components built" operator constraint held perfectly.
- **0 cycle-2 design reviews needed** across L1-L5 — every leg's cycle-1 fix was spec-tightening (wording / AC / symbol-name), never structural rework.

## What Could Be Improved

### Process

- **L6 LOC budget was a "small-tweak" budget; reality was IA-tier consolidation work.** The spec's "(TBD; expected zero) inline fixes" framing turned out to be very wrong — operator surfaced 6 fixes in R1, 5 in R2, ~5 in R4, 3 in R5, etc. The "expected zero" framing was misleading; operator's actual working pattern is "use HAT to iterate until satisfied" rather than "use HAT to confirm landed work." **Methodology fix**: for cleanup-of-cumulative-debt flights, HAT spec should explicitly budget for multi-round escalating-tightening (~5-8 rounds) rather than single-issue confirmation. For single-feature flights, single HAT round budget remains right.
- **L3's HIGH create-mode regression was catchable at flight design time IF the recon explicitly enumerated "where else does this code render?".** The flight-design assumption was "edit-mode is the dominant path"; cycle-1 surfaced create-mode invariant. Worth codifying: *for any move/relabel item, enumerate ALL render call sites + ALL test references at recon time.*
- **L4's HIGH on `[hidden]` specificity override required CSS dive at planning.** The leg correctly identified "toggle `hidden` attribute" as the fix; what was invisible at planning was that `.area-studio .chip-list-editor { display: flex }` at specificity 0,0,2,0 overrides UA `[hidden] { display: none }` at 0,0,1,0. Worth codifying: *for any `[attribute]`-toggle approach, audit the existing rule's specificity before assuming UA defaults apply.*

### Technical

- **3-column "label | info-icon | field" pattern is now load-bearing across 4+ section sites without being a codified primitive.** This is n≥4, well past the F4-codification-threshold of n=2. Operator explicitly flagged for capture. Each application re-invents the pattern via inline `.field-row.admin-pf-row` + manual sibling ordering — fragile against future changes. **Highest-priority lift candidate.**
- **Two-event-channel approach is now at n=2** (`pool-warmed` from F4 + `refresh-requested` from F5 R5). Per F4 debrief's own "wait for n=2 before lifting to shared bus" trigger, the studio event-bus lift is overdue. Not within F5 scope, but is a routine-maintenance candidate.
- **Python+JS duplicated directive defaults (KEEP-IN-SYNC comments)** are a sound trade-off at R8's minimal-scope simplification. Become technical debt if a future round picks up the surface for per-type variants, i18n, or length caps. The API-endpoint route is the natural inflection point at that time.
- **CSS budget grew dramatically** as iteration deepened: `studio.css` ~400 lines diff, `admin.css` ~16 lines. The growth is justified per leg, but the per-leg LOC budgets in the spec under-estimated cumulative CSS growth by ~5x. Worth surfacing as a "CSS budget is round-cumulative, not per-leg" methodology note.
- **R8 reverted mission criterion #14** (operator-editable directive). Architecturally the right call — the F2 capability was carrying complexity disproportionate to operator value, R8 deleted ~470 lines net. **Creates methodology debt**: a closed criterion can be re-opened. Right response is not to forbid re-evaluation but to make the lifecycle explicit. Worth tracking in mission-criteria-coverage map with "closed → partially-reverted in F5" annotation.
- **The directive defaults Python+JS duplication has no automated cross-check.** If they drift, nothing catches it. ~10 LOC test would close this.

### Documentation

- **Design-language catalog is incomplete.** Operator's "reusable components underutilization" observation is the meta-issue: primitives that SHOULD exist don't. L5 sweep's 5 deferrals (D1-D5) plus the 3-column pattern and the section-level banner pattern map to ~5 missing primitives. This is **future-UX-maturity-mission framing**, not F5 retroactive scope.
- **`agents.md` info-icon convention not yet codified.** The `title=` + `aria-describedby` + visually-hidden sibling pattern is de-facto codified at every connector + MCP info-icon site. Worth promoting to explicit project-wide convention.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| L6 went 8 HAT rounds (vs spec's "small-tweak" budget) | Operator-driven escalating-tightening cadence for cumulative-debt cleanup; each round exposed the next consistency tier | **Process pattern**: cumulative-debt flights → budget multi-round HAT (5-8 rounds); single-feature flights → single HAT round. |
| L6 R8 reverted mission criterion #14 | Operator-directed simplification; F2 capability carrying complexity disproportionate to value | **Methodology pattern**: closed criteria CAN be re-evaluated; mission-criteria-coverage map should track lifecycle (closed → partially-reverted, etc.) explicitly. |
| L6 R5 introduced section-level banner (new compound assembly) | Operator-flagged per-axis Refresh+pre-probe-hint duplication; banner consolidates as single section-level affordance | **No** (assembly, not primitive); flag in deferral list for future UX mission if n=2 emerges. |
| L6 R3 lifted info-icons OUT of label into sibling position | Cycle-1 reviewer pinned Lifecycle as the canonical 3-column pattern; Runtime Config diverged | **Already a project-wide convention** per L5 sweep cross-cutting findings. Worth a `agents.md` Project-wide entry. |
| Python+JS directive defaults duplicated (KEEP-IN-SYNC comments) | R8 simplification scope; matches pre-R8 same-duplication pattern | **No** (minimum-viable for scope); inflection point is API-endpoint at next surface-pickup. |

## Key Learnings

1. **HAT-as-leg scales for cumulative-debt cleanup.** F5 R1-R8 demonstrated that multi-round escalating-tightening (row → IA → affordance → criterion) is a sustainable HAT cadence when the flight's scope IS "iterate until UX is satisfactory." F4's single-fold-in cycle was right for hotfix work; F5's 8-round cycle was right for cleanup work. Heuristic: flight scope == "cleanup of cumulative debt" → budget multi-round HAT.
2. **Chrome MCP for in-flight verification throughout (not just HAT) is the methodology baseline now.** Caught L4's computed-style invariant; caught L5's element-by-element coverage; caught HAT round-by-round visual rhythm. The F4 → F5 methodology improvement is durable and should be the F6+ default.
3. **n=2 codification triggers compound across flights.** F4 introduced 1 cross-component event channel; F5 added a second. The "lift to shared bus" threshold is now met. Same threshold will hit other patterns (3-column row, icon-only button, reactive codeblock, section-level banner) at varying rates — future-flight-author should default to "check the F4+F5 deferral lists for emerging n=2 candidates."
4. **Spec-completeness ≠ design-completeness, again.** L3's create-mode regression was visible at design review (cycle-1 catch). L4's CSS specificity invariant required dive. Two distinct "what the spec missed" surfaces in the same flight; both caught at cycle-1; both produced architecture (shared helper / specificity-override rule) rather than band-aid. The architect-checklist should grow: *for any code-move, enumerate ALL render call sites; for any `[attribute]`-toggle, audit specificity vs existing rules.*
5. **CSS budget compounds across rounds.** F5's per-leg CSS budgets under-estimated cumulative CSS growth by ~5x. Methodology note: *CSS LOC budgets should be flight-level, not per-leg, in cleanup flights.*
6. **Closed mission criteria can be re-evaluated.** R8 partially-reverted #14 with operator approval. The right response is explicit lifecycle tracking (the M11 mission-criteria-coverage map should grow a status column reflecting oscillation), not a "criteria are immutable once closed" rule.
7. **The design-language catalog is the next bottleneck.** Operator flagged "reusable components underutilization" — the surface diagnosis. Root cause: primitives that should exist don't (3-column row, section-level banner, reactive-codeblock-on-toggle, data-table+drag-handle, mcp-source-tile family, discoverable-dropdown composite). A future UX maturity mission is the right home.

## Test Metrics

Run on F5 HEAD post-debrief test-fix (commit pending), inside the `the-one` container, 2026-05-24.

| Tier | Pass | Fail | Skip | Wall |
|------|------|------|------|------|
| Non-browser (`-m "not browser"`) | 2472 | 4 | 7 | 237.6s |
| Browser (`-m browser`) | 418 | 2 | 35 | 476.2s |
| **Combined** | **2890** | **6** | **42** | **~714s** |

### Comparison vs prior flights

| Flight | Combined pass | Failures | Wall |
|---|---|---|---|
| M10 F8 baseline | 2331 | 10 | n/a |
| F1 | 2804 | 10 | 610s |
| F2 | ~2834 | 4 | n/a |
| F3 | 2879 | 7 | ~658s |
| F4 | 2899 | 6 | ~717s |
| **F5** | **2890** | **6** | **~714s** |

### Failure breakdown (all 6 carry-forward; 0 F5-introduced regressions after debrief test fix)

**AIAT cluster** (4 fail; now 6 flights deep): `test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step` — `Agent 'default' has no provider configured`. Fixture issue; routine-maintenance candidate.

**Chronic UI tests** (2 fail; now 7 flights deep): `test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`. Routine-maintenance candidate.

### Test count delta vs F4 (-9 net pass, +1 fewer fail)

- R8's deletion of `TestConnectorOperatorDirectiveCollection` (3 tests) + 4 `_CONNECTOR_TOOL_DISABLED_DIRECTIVE` dispatch tests = -7 from non-browser tier.
- R8 added 4 new directive-dispatch tests + 4 new directive-section-removed-from-General tests + 6 new R8 tests = +14 elsewhere.
- Browser: 13 pre-R8 directive tests → 10 post-R8 directive tests = -3 net browser.
- 1 NEW failure (`test_e2e_disabled_state_inbound_received_no_outbound`) introduced by R8's deletion sweep missing the e2e test → fixed at debrief time; assertion was checking deleted-directive substring; behavioral contract (no outbound when tool disabled) preserved by the existing `StubPlugin.outbound_records == []` check.

### Key timing observations

- **Wall time essentially unchanged** vs F4 (~714s vs ~717s); no per-test runtime regression from F5 work.
- **F2-era browser-tier-hang risk did not recur**.
- **The pre-existing invite-section anomaly** (`test_pre_probe_hint_visible_url_hidden` failing due to `.connector-invite-url-wrap` `display: flex` overriding `[hidden]`) was fixed during L6 round-8 commit — same-pattern fix L4 applied to chips container.

## Recommendations

### Critical — before F6 lands

1. **Update M11 criterion-coverage.md** for F5 contributions:
   - Row #1 (Discord-shaped form): now `closed-by-F1+F5` with evidence pointers.
   - Row #2 (vocabulary substitution): `closed-by-F5` (verbose technical → human-friendly via L3 + L6 R2).
   - Row #14 (operator-editable directive): **`closed-by-F2 → partially-reverted by F5 L6 R8`** with explicit annotation.
   - Rows #18 + #19: `partially-closed-by-F5` with HAT-validated evidence.
   - Verify the criterion-coverage status vocabulary supports the "closed → partially-reverted" lifecycle notation; if not, this F5 debrief is the methodology trigger to extend the vocabulary.
2. **Add the L5 sweep deferrals D6 + D7** to `sweep-coverage.md` so they're queued for the future UX maturity mission:
   - **D6** — 3-column field-row primitive codification (n=4+; load-bearing; operator-flagged).
   - **D7** — Reusable components underutilization observation (design-language catalog is incomplete).
3. **The new test failure** (`test_e2e_disabled_state_inbound_received_no_outbound`) — already fixed at debrief time (5 LOC; prompt-substring side-check removed; behavioral check preserved). Verify the fix is in the committed state.

### Important — F6 (peer-name attribution) design considerations

4. **Cite the new 3-column field-row convention explicitly at F6 design.** F6's UI changes (if any) MUST follow it. Any new label-bearing row uses `<label>` + `<button.field-info-icon>` + `<field>` as three flat siblings inside `.field-row.admin-pf-row`. Future flight author should default to this pattern.
5. **F6's `_renderAccountTile` touches** must account for the L4 `.connector-acl-axis-body` containment (border-left + padding + surface-elevated bg). The F4 L3 closure-scoped helpers (`_labelCache`, `_ensureLabelCache`, `_applyLabelsToCheckboxes`) remain load-bearing.
6. **R8 simplification means F6 doesn't need to handle per-account directive override.** One fewer surface to consider in the peer-name attribution flow.
7. **If F6 touches the directive surface** (peer-name might appear in the prompt context), the Python+JS directive-defaults duplication becomes the API-endpoint inflection point.

### Methodology — promote to mission-control skills

8. **Promote `cross-flight-ux-debt-reconciliation` from project-side fallback to `/flight` skill prereq.** n=2 operational proof in F5 (after n=1 in F4). The discipline produces a tight, defensible flight scope and explicit deferral list at planning time.
9. **Add to `/agentic-workflow` skill prompt: rationale for in-flight Chrome MCP verification.** F4's HAT-only Chrome MCP usage was good; F5's in-flight-throughout usage is the durable improvement. Add to default agent-spawn prompts for implementing legs that touch UI.
10. **Add to `/flight` skill prompt: HAT round-budget by flight scope.** Cumulative-debt cleanup flights should budget 5-8 escalating-tightening rounds; single-feature flights should budget 1-2 small-tweak rounds. Spec language at flight-design time should be calibrated accordingly.
11. **Add to `/flight-debrief` skill prompt: closed-mission-criterion re-evaluation lifecycle.** When a flight reverts (partially or fully) a previously-closed mission criterion, the debrief should explicitly track the lifecycle change in the mission-criteria-coverage map.

### Important — refactoring opportunities

12. **Lift 3-column field-row to design-language primitive** (highest priority; n=4+; ~30-50 LOC primitive deletes ~150+ LOC inline boilerplate across `connector-form-discord.js` + `connector-account-editor.js`; forces resolution of 2 non-blocking a11y observations from cycle-1).
13. **Lift cross-component CustomEvent strings to shared studio events module** (n=2 met; per F4's own trigger).
14. **Add Python+JS directive-defaults cross-check test** (~10 LOC; closes silent-drift surface).
15. **Codify info-icon convention in `agents.md` Project-wide.** Already de-facto codified; convention promotion is the cheap formalization.

### Routine-maintenance candidates (carryforward + new)

- **AIAT 4-test cluster** — fixture fix (now 6 flights deep).
- **Chronic UI tests** — 2 remaining; update to match prod (now 7 flights deep).
- **`_xxxValues` getter pattern unification** (F3 carryover).
- **Axis vocabulary constant lift** (F3 carryover).
- **`_RegistryEntry.account_type=""` backwards-compat default removal** (F3 carryover).
- **Plugin-author guide for connectors** (F3 + F4 carryover).
- **F5 NEW**: studio event-bus lift (n=2 trigger met).
- **F5 NEW**: 3-column field-row primitive codification (would close D6).
- **F5 NEW**: Python+JS directive-defaults cross-check test.

## Action Items

### Immediate (before F6 planning)

- [ ] Update `missions/11-discord-connector-depth/criterion-coverage.md` rows #1, #2, #14, #18, #19 per Critical recommendation #1. Extend status vocabulary to support "closed → partially-reverted" lifecycle notation.
- [ ] Append D6 (3-column field-row codification) + D7 (reusable components underutilization) to `sweep-coverage.md` deferral list.
- [ ] Verify the `test_e2e_disabled_state_inbound_received_no_outbound` test fix is committed in F5's commit chain.
- [ ] F6 architect briefing: cite the new conventions (3-column field-row, info-icon-as-sibling, two-event-channel discipline); note the L4 containment + L5 sweep findings.

### Methodology (before F6 planning)

- [ ] Surface to mission-control: promote `cross-flight-ux-debt-reconciliation` to `/flight` skill prereq.
- [ ] Surface to mission-control: document in-flight Chrome MCP verification in `/agentic-workflow` skill prompt.
- [ ] Surface to mission-control: HAT round-budget calibrated by flight scope in `/flight` skill prompt.
- [ ] Surface to mission-control: closed-criterion re-evaluation lifecycle in `/flight-debrief` skill prompt.

### Near-term (before F7)

- [ ] Studio event-bus lift (n=2 trigger met).
- [ ] 3-column field-row primitive codification (D6) — could be a small dedicated flight or fold into a future UI-touching flight.
- [ ] Python+JS directive-defaults cross-check test.

### Routine-maintenance candidates

- [ ] C3 AIAT cluster — fixture fix (6 flights deep).
- [ ] C5a/b chronic UI tests — update to match prod (7 flights deep).
- [ ] Plugin-author guide for connectors (F3+F4 carryover).
- [ ] Unify `_xxxValues` getter pattern (F3 carryover).
- [ ] Lift axis vocabulary to `App.studio.connectorAxes` constant (F3 carryover).
- [ ] Remove `_RegistryEntry.account_type=""` backwards-compat default (F3 carryover).
- [ ] L4 `prior_cache` force-interleaving test (F3 carryover).
- [ ] Shared `tests/browser/fixtures/discoverable_entities.py` (F4 carryover).
- [ ] Container playwright install one-off (F4 carryover).

## Future UX Maturity Mission scope (operator-flagged)

The operator explicitly called out: "*Making the 3 column label | info icon | field a durable pattern in the design language and across pages. It's also apparent that we haven't fully utilized reusable components which leads to a lot of rework.*"

This is the right framing for a dedicated **UX maturity mission** post-M11 (or interleaved if it blocks other mission progress). Scope candidates:

- **Codify missing primitives** in the design-language module:
  - 3-column field-row (n=4+; operator-flagged)
  - Section-level banner (LED + status + action button)
  - Reactive-code-block-on-toggle
  - Icon-only buttons (Copy + Refresh shape)
  - Expandable-tile (`mcp-source-tile` family — D4)
  - Discoverable-dropdown composite (D1)
  - Data-table + drag-handle pair (D2 + D5)
  - Attached-agents empty-state (D3)
- **Migrate existing surfaces to consume the primitives** (connector editor + MCP editor + per-agent overlay).
- **Establish design-language adherence as a planning checklist item** for future UX-touching flights.

This is a flight-sized scope adding ~7 new design-language primitives plus migration. F5's L5 sweep already produced the catalog (D1-D5 + the operator-flagged D6+D7); the mission would be primitive-creation + migration.
