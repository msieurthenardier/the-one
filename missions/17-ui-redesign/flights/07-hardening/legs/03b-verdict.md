# Leg: 3b-verdict

**Status**: completed
**Flight**: [Hardening & Mission-End Acceptance](../flight.md)

## Objective

The mission-end VERDICT leg: run the full suites + final guard audit, dispose of the theme-sync-unset known issue, perform the SC1-SC9 mission-end verification with cited evidence (consuming Leg 3a's settled measurements), populate the flight-log SC-evidence ledger, and CHECK the 9 SC boxes in mission.md.

## Scope

- **Full suites** (synchronous): `make test-unit` (CANONICAL — never `-m live`; expect ~3782/0-fail) + full `make test-browser` (confirm ~532+ green, ZERO module-level skips, the 6 per-test skips accounted-for) + the token/contrast/a11y/guard suites. Record counts + wall-clock; apply the flake disposition.
- **Final guard audit**: confirm ALL green + honest — sink baseline (DYNAMIC_SINK_BASELINE), testid registry sync, all-guard-allowance, banned-token guard (`test_no_retired_design_vocabulary_in_css`), mirror-sync guard, AND the F6 runtime chip-list `label[for]` resolver (`test_flow_chiplist_label_resolver.py`). All are load-bearing mission-introduced invariants.
- **Theme-sync-unset known-issue disposition**: grep mission.md Known Issues for the multi-tab "Auto restore doesn't propagate" bug (assigned to F2). Confirm it was fixed in F2 (check F2 artifacts/tests) OR record an explicit "documented-accepted known issue" disposition. Close the loose end.
- **SC1-SC9 mission-end verification** — for EACH, state the cited evidence, then CHECK its box in mission.md AND tick the F1-F7 Contributing-to-Criteria annotations:
  - **SC1** — `test_no_retired_design_vocabulary_in_css` green (machine-enforced 0 alien remnants) + the F7 `.cap-chip` quiet (last eyebrow) + the per-flight visual passes (basis: CSS-guard + prior visual work, no fresh full F7 sweep).
  - **SC2** — the full-palette audit both themes + the NEW CSS-driven completeness assertion (`test_sc2_every_fg_role_token_is_gated_or_exempt`, probe-tested) + the documented non-text exclusions + the `--fg-faint` deliberate exception.
  - **SC3** — one vocabulary, no per-area variants: the `.cap-chip` cross-area quiet (final proof) + the `.field-group` vocabulary shared across areas + the badge/button/field/tab/modal primitives.
  - **SC4** — cite the CROSS-SOURCE evidence (not the round-trip alone): chat-roundtrip both themes (streaming + Stop witnessed mid-stream + turn distinction + inline markdown); `test_markdown.py`/`test_flow_markdown_chat.py` + F4 leg-03 (code-block); `test_flow_chat_thinking_disclosure.py` + F4 leg-04 (tool-trace collapsed-until-expanded); F4 chat-reading-layout + leg-04 (scroll-position awareness — smart-auto-scroll landed; jump-to-latest explicitly out of scope).
  - **SC5** — connector-editor-keyboard-a11y 7/7 (F5, cited — surface untouched by F7) + the chip-list `label[for]` runtime guard + 2px accent `:focus-visible` both themes + landmark/skip-link preserved.
  - **SC6** — 0 module-level skips (grep-confirmed) + full browser green; "healthier than before" = the net additions (5 modules re-enabled at F1, the new guard suites: testid registry / innerHTML-sink freeze / banned-token / mirror-sync / runtime chip-list, expanded contrast/token parametrization, unit 3681→3782 + browser 478→~565); LOG each of the 6 per-test skips with its M08-era rationale.
  - **SC7** — three area gates green BOTH themes per the re-run rule: chat-roundtrip (light F4 + dark F7), system-provider-config (F6 + F7 re-run both), studio-agent-crud (F5 both + F7 dark re-run), connector-a11y 7/7 (F5, cited).
  - **SC8** — retained-heap +0.99% (forced-GC, no leak) + latency p50 0.10ms (≤50ms); cite the perf-result-f7.md verdict INCLUDING the raw +23% → diagnosed GC-timing/denominator-artifact reasoning (transparent for operator).
  - **SC9** — agents.md design section v3 (F7 top-up) + gallery v3 + CLAUDE.md v3 + the never-`-m live` note.
- **Populate the flight-log SC-evidence ledger** (the "Mission-End SC Verification" section) with each SC + its cited evidence.

## Acceptance Criteria

- [x] Full suites green (unit canonical **3782 passed/0-fail** 5:31 + browser **566 passed/0-fail/0 module-skips** 12:44 + token/contrast/guards); wall-clock recorded; no flake disposition needed (zero failures, clean single runs)
- [x] Final guard audit: all 6 guard families green + honest (sink `test_no_new_dynamic_innerhtml_sinks`, registry `test_testids_in_source_are_registered` w/ empty `KNOWN_DEAD_SELECTORS`, all-guard-allowance `CLIP_PATH_POLYGON_ALLOWANCE={}`, banned-token `test_no_retired_design_vocabulary_in_css`, mirror-sync `test_design_token_mirror_in_sync`, runtime chip-list `test_flow_chiplist_label_resolver.py`)
- [x] theme-sync-unset known issue disposed — **F2 L3-fixed confirmed** (`theme.js` `newValue===null`→auto; regression test `test_theme_cross_tab_sync.py` green); mission.md Known Issue annotated RESOLVED
- [x] SC1-SC9 each verified with cited evidence in the flight-log ledger ("Mission-End SC Verification")
- [x] The 9 SC boxes CHECKED in mission.md (+ the F1-F7 Contributing-to-Criteria annotations ticked)
- [x] ruff clean; git status clean of snapshots (`__snapshots__` gitignored)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry + SC-evidence ledger; leg `landed`; checked off in flight.md
