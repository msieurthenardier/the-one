# Leg: eval-runs-and-baselines

**Status**: completed
**Flight**: [Notes as memories](../flight.md)

> Backported: written on 2026-11-13 from the work in PR #364.

## Objective
Prove the wording with the evals and record the new baselines (DD4, DD5, DD6). This leg spends plan quota and local-model time and changes no product code except through DD1's revision.

## Context
- The design is the flight's DD4, DD5 and DD6.
- All runs are n=20 on the default models `haiku`, `qwen3-4b` and `lfm3`, one set at a time.
- Run directories (`evals/runs/`) are gitignored. Only the baselines are committed.

## Steps, as run
1. **First wording, old scenario set, against `m35f2b`** (`notes-{platform,routines,visuals,widgets}-n20`, prompt `2aee8815…`). Platform: 3 hard failures (DD1). Routines, visuals and widgets: no hard failures. All size gates passed.
2. **Revision** of `NOTES_HEADING` (DD1), agreed by the operator.
3. **`main`'s prompt, new scenario set** (scratch worktree at `0ce374f0`, `main-newset-platform-n20`, prompt `1825808f…`). Recorded as the scratch gate baseline `gate-newset-platform`, with `derive-bars --size-ratio 1.0`.
4. **Revised wording, all four sets** (`notes2-*-n20`, prompt `1d02c156…`). Platform was compared against step 3; the other sets against `m35f2b-*`.
5. **Repeat runs** of haiku `rule-beats-note` (n=20, twice per prompt) to read the step 4 hard failure (DD6).
6. **Baselines**: `baseline notes-{set} evals/runs/notes2-{set}-n20` and `derive-bars --size-ratio 1.0` for each set. The freeze pin moved to `notes-platform.json`, and the baseline lines in `CLAUDE.md` and `evals/README.md` were updated.

## Acceptance Criteria
- [x] Platform compare: no regression in `notes-proactive` or `notes-stale`, and no new safety failure. Every hard failure is explained and accepted (DD6).
- [x] Routines, visuals and widgets compares: no hard failures.
- [x] Size gates: all pass.
- [x] Four `notes-*` baselines are committed, and their `fingerprints.prompt` equals `measure-prompt` on the branch.
- [x] `tests/test_evals_freeze.py` passes against `notes-platform.json`.

## Outcome
The readings are in the flight log, "Leg 2: eval-runs-and-baselines".
