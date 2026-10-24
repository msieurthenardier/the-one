# Leg: macos-probe-run

**Status**: completed
**Flight**: [Choose the packaging toolchain](../flight.md)

## Objective
Read the hosted macOS probe run (dispatched by the Flight Director), score each candidate against the DD2 gates as far as the runner allows, and record the macOS rows of the Evidence Table. If a failure has a contained recipe fix, prepare that fix for a second run. The second run is the last one the budget allows, and only the Flight Director, with the operator's go, dispatches it.

## Context
- **The run:** the Flight Director merged PR #305 (the `.github/`-only workflows) to `main`, and dispatched `gh workflow run packaging-probe-macos.yml --ref flight/01-choose-packaging-toolchain -f candidates="A B"`. The run ID and URL are in the flight log's Flight Director Notes.
- **Budget:** at most 2 macOS jobs this flight (DD6). This is job 1. **This leg never dispatches**, and never pushes or opens PRs.
- **What the run can and cannot prove** (DD6):
  - It can prove `doctor` (strict scoring), gate 2 (the toolcache or a system Python, never the bundle), `serve` start-up, the data-dir path (`~/Library/Application Support/the-one/`), the signatures, and the sizes.
  - It cannot prove the window, the Dock behaviour or single-instance. Those are contributor-verified in Flight 3.
- **Read the `macos-probe-prepare` entry in the flight log first.** It has the per-candidate command listing, the residual risks, and the paper items. Confirm or refute each residual risk from the logs:
  - B's stub `sys.executable`, `sys.frozen`, argv forwarding, and stdout reaching the terminal;
  - whether `BRIEFCASE_MAIN_MODULE` works;
  - A's pyobjc hidden imports;
  - the FSEvents file watcher, embedding and window-chrome gates;
  - whether `codesign --verify --deep --strict` fails on A, a known PyInstaller sealing quirk that is data, not a script bug.

## Inputs
- The run's logs artifact (`gh run download <run-id> --dir $M32_EVIDENCE/macos/run-1/`) and the job log (`gh run view <run-id> --log > …/job.log`). Read-only `gh` use is allowed.
- The workflow and scripts as committed at `f6a546e`.

## Outputs
- `$M32_EVIDENCE/macos/run-1/` with the downloaded artifact and job log (not committed).
- The flight log:
  - a `### macos-probe-run` entry;
  - macOS rows in the Evidence Table (per candidate: G1 strict, G2, `serve`/live, data dir, signature, size, build time, and notes; the window columns N/A, labelled "contributor, Flight 3");
  - each residual risk marked confirmed or refuted with a log excerpt.
- **Only if needed:** a contained fix under `packaging/` (or a workflow fix), uncommitted, with a written case for a second run: what failed, why the fix is contained, what the second run would add to the decision, and its expected cost.

## Acceptance Criteria
- [ ] **AC1 — Evidence downloaded and cited.** The run ID, URL, conclusion and wall time are logged. The artifact and the job log are saved under `$M32_EVIDENCE/macos/run-1/`.
- [ ] **AC2 — Per-candidate scoring.** For A and B, each check `macos-checks.sh` ran is recorded as PASS, FAIL or not reached, with a log excerpt. Gate 1 is scored by the strict rule: window chrome's `skipped (not Windows)` is the only allowed skip.
- [ ] **AC3 — Residual risks resolved.** Each residual risk in the Context list is marked confirmed, refuted or unobservable, with its excerpt.
- [ ] **AC4 — Every failure classified.** Each FAIL is either:
  - (a) **a recipe or script defect with a contained fix**: the fix is written and linted (`actionlint`, `shellcheck`, `ruff` as applicable), and the second-run case is written; or
  - (b) **a candidate limitation**, recorded as evidence for the decision with no fix.

  If nothing failed, or every failure is (b), the log says no second run is needed.
- [ ] **AC5 — The Evidence Table is updated** with the macOS rows, and the upkeep notes are updated with anything macOS added to either candidate: files, the spec, entries, config, patches.
- [ ] **AC6 — Nothing outward-facing.** No dispatch, push, PR or commit. `git status` shows changes only under `packaging/`, `.github/workflows/` (only if a workflow fix is in the second-run case) and `missions/`.

## Verification Steps
- AC1: `gh run view <id> --json conclusion,createdAt,updatedAt,url`; `ls $M32_EVIDENCE/macos/run-1/`.
- AC2-AC5: the flight-log entry and the Evidence Table.
- AC6: `git status --porcelain`.

## Implementation Guidance
1. Read the flight log (the `macos-probe-prepare` entry and the Flight Director Notes with the run ID). Download the artifact and job log.
2. Read `SUMMARY.txt` per candidate, then the detailed logs. Score each check (AC2), and work through the residual risks (AC3).
3. Classify the failures (AC4). Prefer (b) when the fix would need an app change beyond the DD4 patch scope, or a design call; those belong to Flight 3. Choose (a) only when one more run would materially change the decision (for example, a candidate's gate 1 never ran because of a script bug).
4. Update the Evidence Table and the upkeep notes. Update the flight log, and set the leg to `landed`.

## Edge Cases
- **The run was cancelled or hit the job cap**: the logs artifact still uploads (the upload step runs `always()`). Score what ran, and mark the rest "not reached". Name the step that consumed the time.
- **The artifact is missing** (an upload failure or a quota problem): use the job log (`gh run view --log`), and record the artifact problem.
- **A candidate is red only because of a codesign strict-verify quirk**: score the signature check as data, not as a gate failure. Gate 1 and gate 2 decide.

## Files Affected
- The flight log (always).
- Only for an AC4(a) fix: `packaging/**`, and possibly `.github/workflows/packaging-probe-macos.yml`. A workflow fix applies on the flight branch only, because `--ref` runs the branch's copy, so no new PR to `main` is needed unless the trigger or inputs change.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked on 2026-10-23 at `f6a546e`: the workflow's `always()` upload step and its final fail-on-FAIL step, `macos-checks.sh` (the check list, the `tl` wrapper, the `rc=` lines), and the leg 04 flight-log entry's residual-risk list.
