# Leg: hosted-build-run

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Prove the release build environment: dispatch `linux-packages.yml` on the flight branch, read its gate summary, and compare what the hosted runner built against the local rehearsal build. The point is that the bundle the release runner produces is the one the flight measured (debrief recommendation 3, DD2, DD10).

## Context
- **Flight DDs:** DD10 (the dispatch, the 6-run cap, the matrix), DD2 (the pinned container is the same locally and hosted).
- **Leg 9 results:** the workflow was rehearsed by execution, which caught three defects before any dispatch. The rehearsal build is `0.11.9.dev12` (`$HOME/the-one-m32-build/f2/runner-rehearsal/m32-build/`). Residual risk: two of the four matrix cells (deb/ubuntu-26.04 and appimage/debian-13) had never run, and the runner's disk and Docker facts were unmeasured.
- **The outward steps were done by the Flight Director under the operator's flight-planning approval (2026-10-24, "Yes to all three"):**
  - the flight branch pushed at `2fdfaa3`;
  - the stub PR #310 merged to `main` (`ea5d8c0`), with lint and pip-audit green;
  - run 1 dispatched: `40127933969`.
- **This is a mixed leg:** the dispatch and reading are the Flight Director's; the artifact comparison is a Developer spawn.

## Acceptance Criteria
- [x] **AC1** — a dispatched run is green:
  - `build` passes, with the audit line `PASS`;
  - all four `checks` cells pass, deb cells with G3 and single-instance PASS;
  - `summary` lists four score lines.

  Runs used are within the 6-dispatch cap, each recorded with its id, duration and failure cause.
- [x] **AC2** — the runner facts are recorded from the `Runner evidence` step: OS, Docker version, free disk, CPU and memory. The billed minutes come from `gh run view --json` or the job durations.
- [x] **AC3** — the hosted packages match the local build:
  - the hosted `.deb` and AppImage are downloaded;
  - the extracted bundle's file list is diffed against a local container build of the **same commit and version**: `packaging/linux/build.sh --version <the run's version>` at the run's commit;
  - the differences are explained, or there are none;
  - the bundle audit lines are compared;
  - the bundled fallback library versions are compared.
- [x] **AC4** — one hosted `.deb` and one hosted AppImage pass the local baseline gate suite (`packaging/linux/checks/gates.sh` on `ubuntu-26.04-baseline` and `debian-13-baseline`, `--display wslg`). That covers the stock-desktop window path the hosted bare matrix does not.

## Verification Steps
- `gh run view <id>`; the artifacts; the diff and gate outputs in the flight log.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
