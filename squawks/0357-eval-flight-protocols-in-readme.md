# Squawk 0357: document the eval-flight protocols in evals/README.md

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: —

## Report
Sortie 15 (Notes as memories) used three eval practices that `evals/README.md` does not describe. Each will be needed again by the next prompt or scenario change (sortie 15 debrief, recommendation 4):
1. **The two-step same-scenario-set gate.** When a change alters the scenario set and the prompt together, `compare` refuses a cross-set comparison. The fix:
   1. Run the new scenario set on `main`'s unchanged prompt and record it as a scratch baseline (`baseline` plus `derive-bars --size-ratio 1.0`).
   2. Compare the new prompt's run against that scratch baseline.
   3. Unchanged sets still compare against their committed baselines.
2. **A hard-failure and noise protocol, declared before the runs.** A failing hold cell is repeated twice on each prompt (n=20) before it is accepted. The repeats are then folded into the baseline or the cell is marked, and the reading is written down before the result is seen.
3. **Evidence durability.** `evals/runs/` is gitignored, and a scratch worktree can be removed. Every number a gate decision rests on (scratch-baseline cells, repeat runs, transcripts another flight will cite) is written in full in the flight log.

Expected: a short subsection near "## Convention" in `evals/README.md` covering the three, with sortie 15 as the worked example. No code change.

## Evidence
- `evals/baseline.py::check_comparable` — "refusing to compare: the scenarios fingerprints differ from the baseline's".
- `sorties/15-notes-as-memories/flight.md` DD4 (the gate) and DD6 (accepted hard failures), and its `flight-debrief.md` "What Could Be Improved › Process": the gate evidence (`gate-newset-platform`, the `main`-prompt repeat runs) was lost with the scratch worktree.
- `evals/README.md` "## Convention" mentions "A changed scenario set requires a same-prompt re-baseline" but not how to gate a change that moves both.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*
