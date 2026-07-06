# Flight: Hardening & Mission-End Acceptance

**Status**: ready
**Mission**: [UI Redesign — Clean, Professional, Consistent](../../mission.md)

## Contributing to Criteria

> This is the ACCEPTANCE flight — it VERIFIES and CHECKS all nine SC boxes in mission.md with cited evidence.

- [ ] SC1 · SC2 · SC3 · SC4 · SC5 · SC6 · SC7 · SC8 · SC9 — all verified to mission-end here.

---

## Pre-Flight

### Objective

Close the mission: fix the two deferred cross-area items (the `.cap-chip` last eyebrow, the pre-existing provider-editor H1-desync), close the SC2 contrast-completeness hole, bring the docs fully current (SC9), run the one owed behavior gate (chat-roundtrip DARK) + the SC8 perf re-run against the pinned baseline, run the full suites, and perform the **SC1-SC9 mission-end verification with cited evidence — checking every SC box in mission.md**. Then the mission debrief. No new surfaces; this is verification + hardening + acceptance.

### Scope corrections from the acceptance survey (important — several feared unknowns are already closed)

- **SC6 is ALREADY satisfied** (Flight 1): grep confirms ZERO module-level skips in tests/browser/; the 5 modules were re-enabled at F1 and the two "unexplained-hang" modules (test_flow_agent_crud, test_flow_provider_setup) re-enabled cleanly (the residual failure was a `:has()` empty-grid CTA-hidden locator issue, fixed test-side — not a hang; the hang was the F5-L01 SQLite-isolation fix). The 6 remaining skips are PER-TEST, predate M17, and are OUTSIDE SC6's "no module-level skips" clause. F7 = run the full suite to confirm ~532+ green + no NEW module skips.
- **SC8 is fully specified**: harness `App.perf` (perf.js, gated by `?perf=1`); pinned baseline `missions/17-ui-redesign/perf-baseline.md` (Scenario 1: 50 cycles × chat→studio→admin→chat = 150 hash transitions; heap +6.55% vs ≤+20% budget; `area-switch.full` p50 0.10ms vs ≤50ms). Re-run Scenario 1 EXACTLY (the baseline's "Comparison rule for Flight 7" — different cycle count/method = "not comparable"), compare % to +6.55%/+20%.

### Design Decisions

**Consistency fixes (Leg 1):**
- **`.cap-chip` un-scoped quiet** (the last eyebrow; SC1/SC3 consistency): the rule at admin.css:144 is ALREADY un-scoped (no `.area-admin` prefix) — it carries `text-transform:uppercase` + `letter-spacing:0.5px` (the last uppercase eyebrow, inconsistent with the F5/F6-quieted provider/tool badges). Quiet it (drop uppercase + letter-spacing; keep size/padding/the `.chip` base + per-state `.cap-chip-no-tools` danger ink) — ONE un-scoped rule change covering BOTH the admin Ollama panel AND studio's model picker (`renderCapabilityChips`, shared via `window.App.admin`). Re-verify admin + studio lanes both themes. NOTE: SC1's literal banned-list is effects/markers/pixel-font (not uppercase chips), so `.cap-chip` is a CONSISTENCY quiet (matching the other quieted badges), not an SC1-effect violation — frame it that way.
- **H1-header/Name-field desync fix** (pre-existing, F6-behavior-gate-caught): CONFIRMED pre-existing (git blame — provider-editor.js:41-58 header block is commit 156a4d98, 2026-04-28; the save→no-re-render decision at admin.js:319/335-337 predates F6). **Re-render the WHOLE header text block (title + subtitle), not just `.editor-title`** (architect P4): the `.editor-subtitle` (provider-editor.js:55-56) is built from `provider.type · provider.base_url` — BOTH editable in edit mode — so a base_url/type edit leaves the subtitle stale by the identical mechanism. Fix: in the edit→edit save success path, re-render the header title + subtitle from the `updated` provider that `onSaveSuccess(updated,…)` already receives. LOW RISK confirmed (architect): `.editor-title`/`.editor-subtitle` are display-only nodes, invisible to `getFormSnapshot`/dirty tracking (which reads `data-field` inputs) — rewriting header textContent doesn't threaten snapshot/dirty logic. Add an assertion-level regression check; the mandatory system-provider-config re-run (P1) is the behavior-level proof.
- **aiosqlite `TestSchemaV17` warning disposition** (F1 carry-forward, owner F7-or-debrief): a single-location "event loop is closed" teardown-timing warning in tests/test_db_migration.py::TestSchemaV17 (not a failure; 0 failing). DECIDE: a small teardown-loop-alignment fix if low-risk, else explicit "accept + document" in the flight log. Not a blocker.

**SC2 contrast-completeness — CSS-DRIVEN, not mirror-driven (Leg 2; architect P2):** the audit gates a CURATED set of fg-role tokens × ladder surfaces both themes; completeness is asserted by docstring prose, not code. **The completeness assertion MUST enumerate from `tokens.css` (the source of truth), NOT the mirror** — the mirror-sync guard (test_ui_guards.py:346) is strictly mirror→CSS, so a new literal-hex fg token added to tokens.css but NOT the mirror slips both nets silently (exactly the "did we forget a token" hole SC2 must close). Drive it off `parse_tokens_css_theme_blocks()` (exists): enumerate literal-hex `--fg*/--accent*/--status*/--code-block*` tokens from tokens.css, assert each is either gated in test_design_tokens_a11y.py OR in a documented exclusion allow-list. **The documented-exclusion approach is correct** (architect-confirmed): contrast is only defined for a fg-on-bg PAIR, so structural tokens (border/hairline, nav-bg, hover-surface, focus-ring color, `--accent-translucent` raw, standalone `--surface-tool`) have no standalone ratio — they're "accounted-for via documented exclusion," not gated. (Alternatively/additionally: upgrade the mirror-sync guard to BIDIRECTIONAL — every CSS literal-hex token must appear in the mirror — then close over the mirror soundly.) Keep the `--fg-faint` 3.0-4.5 deliberate exception. This makes SC2's "ALL palette tokens with documented exceptions" machine-true.

**SC9 docs currency (Leg 2):** agents.md "## Design system" (v3, lines 1243-1279) + the design-gallery sections + CLAUDE.md are largely current. Confirm + top up: the coverage sentence matches the final F3-F6 gates; the `.field-group` vocabulary + the shared `.field-group-label`; the static+runtime label-guard pattern (the F6 methodology asset); the `.section-title` element-scoped convention (F6); and add a CLAUDE.md testing note: **reviewers use canonical `make test-unit`, never `-m live`** (the test_aiat.py→8484 trap). Eyeball each gallery section renders the shipped v3 primitives.

**Mission-end acceptance (Leg 3):**
- **SC7 — the owed runs (acceptance re-run rule, architect P1)**: **a cited prior-flight behavior run is valid for a mission-end SC7 check ONLY if no code the gate exercises changed between that run and the final tree.** F7's Leg-1 diffs land inside two gated surfaces, so citing their pre-fix runs would check a box against code that no longer exists:
  - **chat-roundtrip DARK** — RUN (light passed F4; dark was deferred to this gate). Also confirm the spec exercises the stop button + streaming (SC4 needs it — see below).
  - **system-provider-config** — **MUST RE-RUN** (both themes): F7's H1 fix edits provider-editor.js, the core of this gate's surface — the re-run is also the behavior-level proof the H1 fix works. Non-negotiable.
  - **studio-agent-crud** — **RE-RUN dark** (min): F7's `.cap-chip` quiet changes the rendered studio model-picker (studio.js:1747) + agent tiles (studio.js:1383) this gate exercises.
  - **connector-editor-keyboard-a11y** — CITE the F5 7/7 run (F7 touches nothing it exercises — legitimate cite).
  - Re-run shell-navigation-smoke as a final regression smoke.
  - All behavior runs FD-sequenced on 8485, never overlapping; a REAL Accessibility Validator for the a11y checkpoints.
- **SC8 — perf (architect P3 — PORT TRAP)**: re-run baseline Scenario 1 matching the pinned method byte-for-byte EXCEPT the target port. **The baseline doc hardcodes `8484` — that is the operator's PROD packaged app (`the-one-app.exe`); the branch runs on 8485.** RUN ON 8485 (override the literal 8484; 8484-as-prod is precisely why the baseline is a valid pre-redesign anchor, but the re-run must measure the BRANCH). `?perf=1`, 50 cycles/150 transitions, 2s settle, byte-precise heap capture; record `performance.memory` precision + the branch build's `App.config.version` (baseline was 0.2.15). **Pre-run smoke**: confirm `App.perf.enabled===true` AND `App.perf.summary()` returns a populated `area-switch.full` before trusting the delta. Compare `usedJSHeapSize` growth % to the +6.55% anchor and the ≤+20% budget; `area-switch.full` p50 to ≤50ms. If growth >+20% → DIVERT (investigate before checking SC8). Write the result into a F7 perf-result note.
- **Full suites**: `make test-unit` (canonical — NEVER `-m live`) + full `make test-browser` (confirm ~532+ green, zero module skips, the 6 per-test skips accounted-for) + the token/contrast/guard suites. Apply the flake disposition.
- **SC1-SC9 mission-end verification**: for EACH criterion, state the evidence and CHECK its box in mission.md:
  - **SC1** (0 active alien remnants — the machine-guard `test_no_retired_design_vocabulary_in_css` green + the .cap-chip quiet; box-check states the basis is the CSS-vocabulary guard + prior-flight per-surface visual work, no fresh full visual sweep in F7 — architect note).
  - **SC2** (full-palette audit both themes + the new CSS-driven completeness assertion + documented non-text exclusions).
  - **SC3** (one vocabulary, no per-area variants — the .cap-chip cross-area quiet is the final proof; the field-group vocabulary shared across areas).
  - **SC4** (architect 2nd-pass: chat-roundtrip covers only 2 of 4 clause-groups — cite the rest, don't check on the round-trip alone). SC4 = turn distinction + streaming/stop/scroll-awareness + legible markdown AND code-block + tool-traces-collapsed. Evidence map: **streaming + stop + turn-distinction + inline markdown** — the chat-roundtrip dark RUN (stop witnessed mid-stream, a11y not-ignored); **code-block rendering** — `tests/browser/test_markdown.py` + `test_flow_markdown_chat.py` + F4 leg-03 (composer-streaming-codeblocks); **tool-trace collapsed-until-expanded** — `test_flow_chat_thinking_disclosure.py` + F4 leg-04 verification; **scroll-position awareness** — F4 chat-reading-layout + leg-04 verification (note: chat-roundtrip explicitly puts "jump-to-latest" out of scope; the smart-auto-scroll from M08 F6 is the landed behavior). Check SC4 citing ALL these, not the round-trip alone.
  - **SC5** (keyboard/AT — connector-a11y 7/7 [cited] + the chip-list runtime `label[for]` guard + focus-visible both themes).
  - **SC6** (0 module skips + full browser green) — for "healthier than before" cite the NET ADDITIONS: 5 modules re-enabled (F1), the new guard suites (testid registry, innerHTML-sink freeze, banned-token, mirror-sync, runtime chip-list label resolver), expanded contrast/token parametrization, the test-count delta (3681→~3781 unit; 478→565 browser). LOG each of the 6 per-test skips with its rationale (all M08-era, outside the module-skip clause) so "accounted-for" is documented.
  - **SC7** (three area gates green both themes — per the P1 re-run rule: chat-roundtrip dark RUN + system-provider-config RE-RUN + studio-agent-crud dark RE-RUN + connector-a11y cited).
  - **SC8** (perf within budget vs baseline, measured on 8485).
  - **SC9** (docs describe v3).
- **Theme-sync-unset Known Issue disposition** (architect Q9 — mission.md Known Issues, "assign to Flight 2"): confirm the multi-tab "Auto restore doesn't propagate" bug was fixed in F2 OR is a documented-accepted known issue — close the loose end explicitly (not an SC blocker, but an unresolved mission-scoped defect otherwise).
- **Final guard audit**: sink baseline, testid registry, all-guard-allowance, banned-token guard, **the mirror-sync guard, AND the F6 runtime chip-list `label[for]` guard** (both load-bearing mission-introduced invariants) — all green + honest.

### Prerequisites

- [x] Flights 1-6 completed (all surfaces re-skinned)
- [x] Acceptance survey done (SC6 already-closed confirmed; SC8 baseline located; .cap-chip + H1 loci found; SC2 gap identified; docs assessed; behavior-spec states inventoried)
- [x] 8485 dev instance + `make up` for the perf run

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Leg 1 (consistency fixes) → Leg 2 (SC2 completeness + SC9 docs) → Leg 3 (mission-end acceptance: perf + the owed dark behavior run + full suites + SC1-SC9 verification + box-checking). Behavior gate + perf run are FD-orchestrated/sequenced (never overlap on 8485). A real Accessibility Validator is spun up for the a11y checkpoints (the crew's base one is disabled).

### Checkpoints

- [ ] (L1) `.cap-chip` quieted (un-scoped, both lanes both themes); H1-desync full-header fix + regression check; aiosqlite disposition
- [ ] (L2) SC2 CSS-driven completeness assertion green + documented exclusions; SC9 docs current
- [ ] (L3a) SC8 perf Scenario 1 re-run on 8485 within budget vs +6.55%/+20%; chat-roundtrip DARK PASSES; system-provider-config + studio-agent-crud-dark RE-RUN green; shell-nav re-smoke
- [ ] (L3b) Full suites green (unit canonical + browser 532+/0 module-skips + token/contrast/guards); final guard audit (incl. mirror-sync + runtime chip-list); theme-sync-unset disposition
- [ ] (L3b) SC1-SC9 all verified with cited evidence; the 9 boxes checked in mission.md

### Adaptation Criteria

**Divert if**: the SC8 perf re-run shows heap growth >+20% (investigate the regression before checking SC8 — the whole mission's perf verdict); or the chat-roundtrip dark run fails a real regression (fix before checking SC4/SC7); or the H1-desync fix proves non-trivial (it's small per the survey — if it cascades, scope it and log).

**Acceptable variations**: the exact aiosqlite disposition (fix vs document); whether SC2 completeness lands as an assertion vs a documented allow-list (prefer the assertion).

### Legs

> **Note:** Tentative; created one at a time.

- [ ] `consistency-fixes` - .cap-chip un-scoped quiet + H1-desync full-header (title+subtitle) re-render fix (+ regression check) + aiosqlite disposition; re-verify admin/studio/chat/system lanes
- [ ] `sc2-completeness-and-docs` - SC2 CSS-driven contrast-completeness assertion + documented non-text exclusions; SC9 docs currency (agents.md/gallery/CLAUDE.md incl. the static+runtime guard pattern + section-title convention + the never-`-m live` note)
- [ ] `3a-empirical` - the exclusive-instance judgment-bearing measurements, FD-sequenced on 8485 (never overlapping): SC8 perf Scenario 1 re-run (on 8485, vs the +6.55%/+20% baseline) + the behavior runs — chat-roundtrip DARK + system-provider-config RE-RUN (both themes) + studio-agent-crud dark RE-RUN + shell-nav smoke; real Accessibility Validator
- [ ] `3b-verdict` - full suites (unit canonical + full browser 532+/0-module-skips + token/contrast/guards) + final guard audit (incl. mirror-sync + runtime chip-list) + SC1-SC9 verification with cited evidence (consuming Leg-3a's settled measurements) + theme-sync-unset known-issue disposition + CHECK the 9 SC boxes in mission.md

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] All suites passing (unit canonical + full browser + token/contrast/guards)
- [ ] Flight log updated
- [ ] Documentation current (SC9)
- [ ] All 9 SC boxes checked in mission.md with cited evidence

### Verification

Every mission SC verified with cited evidence and its box checked; the two deferred fixes closed; SC2 completeness machine-true; the chat-roundtrip dark gate green (completing the SC7 both-theme sweep); SC8 perf within budget vs the pinned baseline; full suites green with zero module skips; docs describe v3. The mission is ready for the operator's review of the completed (unmerged) branch.
