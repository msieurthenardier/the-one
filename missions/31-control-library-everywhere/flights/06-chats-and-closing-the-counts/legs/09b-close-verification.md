# Leg: close-verification

**Status**: planning
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Verify the whole flight before the HAT:
- the after captures of every surface in the before set, each difference mapped to a ledger row and judged against it (DD12);
- the quiet-host lane re-budget, including the provisional `contracts-chat` lane (DD15);
- the full gate;
- the mission-close behavior-spec sweep and the new `agent-step-limit-notice` spec, run on a dedicated dev instance.

## Context
- **Flight decisions:** DD12 (captures), DD15 (lanes, the specs) and the standing rules (DD13).
- **The before set** is `$HOME/.cache/the-one-ui-capture/m31-f6-before` (leg 01: 172 images, 43 surfaces, a pinned clock and zone, pixel-identical across two runs). The capture tool's chat surfaces were retargeted in legs 05a and 05c.
- **The ledger** (flight log, rows 1-42 and any added since) is the list of approved differences.
- **Lanes:** sixteen lanes since leg 04. `contracts-chat`'s 300 s budget is provisional. The re-budget rules: a quiet host only (squawk 0259's rule), measured time plus 25% rounded up to 30 s for a lane that moved more than 15% or ran over 1.3×, and a split for any lane over 1.3× its new budget.
- **The behavior specs:**
  - the mission-close sweep: `chat-roundtrip`, `start-a-chat`, `list-and-detail`, `workbench-navigation`, `shell-navigation-smoke`, `jump-to-palette` and `studio-agent-crud`;
  - the new spec: `agent-step-limit-notice` (draft, from leg 06).

  The sweep runs through the behavior-test skill, which the Flight Director drives (Executor and Validator crew). This leg's Developer prepares the instance and the evidence; the FD runs the specs.
- **Production safety:** a dedicated dev instance on a non-default port, a scratch data dir under `$HOME`, started from a scratch working directory, stopped by PID (CLAUDE.md "Behavior-test credential convention").

## Inputs
- Leg 09a landed (the counts at zero, the docs final), uncommitted, or batch B5 in progress.

## Outputs
- **The after set** at `$HOME/.cache/the-one-ui-capture/m31-f6-after`, the same surfaces, widths and themes as the before set. The flight log records:
  - a PIL `ImageChops` comparison table: surface, variant, differs yes/no, the ledger row(s) it maps to;
  - for each mapped difference, a separate judgement of whether it matches what the row promised (DD12; Flight 4's lesson that explained is not correct);
  - any unmapped difference, which is fixed or raised.
- **The quiet-host re-budget:**
  - one `--parallel 3` run under the quiet-host procedure (leg 01's, including `[BLOCKED:host-not-quiet]`);
  - the `PARALLEL_RESULT` line, start load and per-lane times in the flight log;
  - budgets updated by the rules (`contracts-chat` replaces its provisional 300 s) in `scripts/run-tests.sh` and CLAUDE.md, with `tests/test_run_tests_lanes.py` passing;
  - CLAUDE.md's whole-run time sentence updated.
- **The full gate:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` passes. The quiet-host run above may serve as its browser half if it ran after the unit tier with no change between them. The unit counts and the expected skip count are recorded.
- **The specs:** the FD runs the seven sweep specs and `agent-step-limit-notice` on a dedicated dev instance.
  - The run logs land under `tests/behavior/<slug>/runs/`.
  - Each spec's Status and Last Run line is updated; `agent-step-limit-notice` goes from `draft` to `active` on a pass.
  - A failing step is fixed (a new commit) and re-run, or accepted by the operator as a known issue and recorded.
- **Squawks:** every squawk this flight carries (0185, 0215, 0249, 0259, 0269, 0270, 0271, 0272) has its corrective action and verification recorded, ready for the flight-end sign-off.

## Acceptance Criteria
- [ ] The after set exists, and every difference from the before set maps to a ledger row, with its judgement recorded. No unmapped difference remains.
- [ ] The quiet-host run has rc=0, and no lane is over its (new) budget. Both tables agree (grep), and `tests/test_run_tests_lanes.py` passes.
- [ ] `make gate` passes.
- [ ] All eight behavior specs pass, or their failures are fixed and re-run, or accepted by the operator. The run logs are committed with the flight.
- [ ] Every flight squawk has its corrective action and verification text.

## Verification Steps
1. `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f6-after --surfaces <the before set's 43>`, then a PIL comparison script in the session scratchpad.
2. **The quiet-host procedure,** then `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`.
3. `make test-unit` (before or after, never during).
4. **The behavior-test runs** (FD-driven).

## Implementation Guidance
1. **The after set and its ledger mapping** first. Fix any unmapped difference before the gate.
2. **The unit tier**, then the quiet-host browser run, which serves as the gate; then the re-budget.
3. **Hand the instance details to the FD** for the spec sweep. The leg lands when the sweep is done.

## Edge Cases
- **A capture difference caused by a deliberate ledger row on another surface** (for example the flash region, row 37, on an editor surface) maps to that row.
- **A noisy host** voids the budget reading only. The gate result still counts if every lane passed.
- **A spec step that quotes old text** (a re-author the earlier legs missed) is re-authored deliberately and re-run, never edited at the run.

## Files Affected
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, CLAUDE.md (budgets, the run-time sentence).
- `tests/behavior/*.md` (Status and Last Run lines), the new run logs, the squawks, the flight log.

## Citation Audit
- The before set's path and counts: leg 01's flight-log entry.
- The re-budget rules: CLAUDE.md "Lane time budgets", squawk 0259.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
