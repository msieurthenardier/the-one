# Leg: library-close

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Close the flight:
- confirm and record zero sinks and zero ownership-allowance rows on every Library-half file;
- review the unused-selector report for `studio.css` and `components.css`, and remove what this flight left dead;
- recheck the single-consumer library options;
- take the after captures;
- re-measure and re-budget the browser lanes, splitting `library` by the 1.3× rule if needed;
- bring the catalogue, the testid registry, CLAUDE.md and `the_one/agents.md` up to date;
- check every behavior spec this flight touched;
- run the full gate.

**This leg adds no library option and changes no control.** If it finds that it must, it stops and is re-tiered high (DD11).

## Context
- **Flight DD2** (captures, the ledger, the unused-selector script), **DD7** (the ledger feeds the HAT), **DD10** (lanes, specs), **DD11**. **Verification** (flight.md): the target files and allowances.
- **Flight 2 debrief recommendations:** recheck the single-consumer options at this flight's close (`compactIcon`, `master.describedBy`, `master.tristate:false`/`dataset`, `dangerZone.beforeArm`; plus this flight's new options); merge `emptyState` `plain`/`flush` only if a third variant appears (record the decision either way).
- **The ledger** in the flight log has rows from legs 01-08. The HAT (leg 10) is derived from it, so it must be complete and each row must cite its DD.

## Inputs
- Legs 01-08 landed.

## Outputs
- **Counts.** A table in the flight log: for each of `knowledge-*.js`, `knowledge-glue.js`, `connector-editor.js`, `connector-glue.js`, `mcp-glue.js` and `library-pane.js`, the `HTML_SINK_ALLOWANCE` and `OWNERSHIP_ALLOWANCE` rows (all zero), plus the whole-app totals before and after this flight (187 rows / 409 uses and 46 sinks at the start).
- **Dead CSS.** `python scripts/unused_selectors.py css/studio.css css/components.css` is run and reviewed. Every knowledge, connector or disclosure-related unused token is removed, or recorded with a reason (still used by the MCP editor, a runtime prefix, …). The report's before and after counts are recorded.
- **Single-consumer options.** For each library option with one consumer (list them by grepping the call sites), record "now N consumers" or "still one: keep, because …". No option is removed in this leg.
- **After captures.** `python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f3-after/` covers the same surfaces as the before set, in both themes. Each before/after pair is compared and every visible difference is matched to a ledger row. A difference with no row is a defect: it is fixed in a separate fix pass that the Flight Director decides, or recorded for the HAT.
- **Lanes.**
  - A full `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` must exit 0, with unit then `--parallel 3` browser.
  - Each lane's time is recorded against its budget.
  - A lane over 1.3× its budget is split by the Flight 2 rule. For `library`, split out `knowledge` (`test_flow_studio_knowledge_*`) as a new explicit-list lane: `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, CLAUDE.md.
  - Every lane is re-budgeted at measured plus 25%, rounded up to 30 s, where it moved by more than 15%.
  - CLAUDE.md's table matches the script.
- **Catalogue** (`docs/ui-control-inventory.md`):
  - the disclosure, key-value table and clearable-input rows are complete, with consumers;
  - the chip, status, editorShell, copyField and menu rows list the new options;
  - the "KB item menu" and "Key-value table" rows are no longer "not yet defined";
  - the stale rows the cross-cutting survey found are cleaned: the studio pill `.tool-toggle`/`.tool-switch` row, the "compact row actions" row, the stale pull/refresh rows, and the `.tool-enable-switch` row's consumer list (now without the connector);
  - the "not yet defined" count is recorded.
- **Registry** (`docs/ui-testid-registry.md`): `tests/test_ui_guards.py` passes. The retired table and `RETIRED_SELECTORS` cover any id retired in this flight.
- **Docs:**
  - CLAUDE.md: the "Control library (`App.ui`)" paragraph gains this flight's controls; the Library list and detail paragraph notes that the knowledge and connector editors patch in place; the lane table;
  - `the_one/agents.md`: the knowledge modules, the editor-contract section's new consumers (the knowledge and connector handles' `destroy` and identity keys), and the control-library section;
  - the mission's Known Issues: the alias counts after this flight.
- **Behavior specs:** `list-and-detail.md`, `kb-studio-round-trip.md`, `stub-connector-round-trip.md` and `jump-to-palette.md` step 7 are read against the landed UI. Each step that names a changed selector or text is amended, or recorded as already amended by its leg.
- **The flight log:** the leg entry; the completed ledger, marking each row "HAT item" or "approved by DD"; and in-progress lines.

## Acceptance Criteria
- [ ] The counts table is in the flight log, and every Library-half file shows zero sinks and zero allowance rows.
- [ ] The unused-selector report has been reviewed, and its before and after counts and the dispositions are recorded.
- [ ] The single-consumer option list is recorded.
- [ ] After captures exist for every before surface in both themes, and each visible difference maps to a ledger row (or is listed as a HAT item or defect).
- [ ] `make gate` (netns and WebKit) exits 0, with lane times recorded. No lane is over 1.3× its budget after any split, and CLAUDE.md's table matches `scripts/run-tests.sh`.
- [ ] The catalogue, registry, CLAUDE.md, `agents.md` and the mission's Known Issues are updated. `tests/test_ui_control_inventory.py`, `tests/test_ui_guards.py` and `tests/test_run_tests_lanes.py` pass.
- [ ] The behavior-spec check is recorded.
- [ ] No file under `js/ui/` and no `components.css` control section changes in this leg, apart from deleting dead CSS. `git diff` of this leg is limited to docs, tests, `scripts/run-tests.sh`, dead-CSS deletions and the flight log.

## Verification Steps
- The commands above, and `git diff --stat`, reviewed against the last criterion.

## Implementation Guidance
1. Log a start line.
2. The counts.
3. Dead CSS.
4. The options.
5. Captures and the ledger match.
6. The gate and lanes.
7. Docs, catalogue and registry.
8. Specs.
9. The flight log.

## Edge Cases
- **A capture difference with no ledger row:** do not fix it in this leg. Record it, and the Flight Director decides on a fix pass or a HAT item.
- **A flaky lane in the gate:** re-run the failure in isolation (the gate-flake triage rule). Known squawk flakes (0229, 0230) are recorded and accepted.

## Files Affected
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `CLAUDE.md`, `the_one/agents.md`, `missions/31-control-library-everywhere/mission.md` (Known Issues)
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` (if a lane splits)
- `css/studio.css`, `css/components.css` (dead rules only)
- `tests/behavior/*.md` (amendments)
- The flight log

## Citation Audit
Drafted at `332496d`. Its inputs are the landed legs' flight-log entries, so it is checked against them before this leg goes `ready`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
