# Mission: Post-Mission-25 Maintenance

**Status**: active

## Outcome

Resolve codebase health issues identified in maintenance report
[2026-10-08](../../maintenance/2026-10-08.md). The verification gate stops being
the bottleneck on every leg:

- the unit lane runs in 300 s or less;
- a full local gate (unit plus every browser lane) runs in 20 minutes or less;
- CI's browser work no longer runs as one serial ~40-minute task;
- CI no longer runs for documentation-only pushes.

Every test keeps its current coverage.

## Context

The 2026-10-08 inspection was triggered by the close of
[Mission 25](../25-workbench-navigation/mission.md). It measured the gate on a
quiet host with no failures:

| Gate | Time | Notes |
|---|---|---|
| Unit | 697 s | 5598 tests. Past the 600 s threshold the operator set after Mission 22 |
| Browser | 41.5 min | 1831 items, run as six lanes in sequence |
| Full gate | about 53 min | Paid on every leg |

The causes are measured:

- **Unit fixture setup** takes about 75% of the unit lane. Every test database
  replays all 46 migrations from v0, with an fsync per commit. That cost grows
  with each new migration.
- **Per-test server churn** takes about 52% of the browser lanes: 936 uvicorn
  starts and stops, and each server replays the same migrations again.
- **Deleting redundant tests** would save only about 1.5 minutes, so it is not
  the lever. The redundancy found here is collapsed inside the flight.

CI makes it worse:

- `ci/tasks/browser.yml` runs the whole browser suite as one serial task.
- Every task reinstalls unlocked dependencies from scratch, ignoring `uv.lock`.
- No path filters exist, so each flight-log or debrief push costs a full run
  plus an installer build.
- All of this runs on the operator's own machine.

The squawk-sized findings from the same report are handled beside this
mission as squawks 0143–0152, not here.

## Success Criteria

- [ ] **Unit tier on a template database.**
  - Unit-tier fixtures build their database from a session-scoped migrated
    template instead of replaying every migration per test.
  - `test_db_migration.py` keeps the real from-v0 path.
  - A guard test pins that the template matches a fresh `ensure_schema`.
  - Measured result: the unit lane takes 300 s or less. *(#1)*
- [ ] **Browser servers seeded from the template.**
  - Every browser-test server starts from a pre-seeded template database and
    replays no migrations at boot.
  - Measured browser setup time drops accordingly. *(#2)*
- [ ] **Browser quick wins.**
  - The 35-row legacy-redirect table runs on one server.
  - The 5 duplicate redirect tests are removed.
  - The ready-poll interval is tightened.
  - The 3 long-skipped browser tests are deleted or rewritten, so none is left
    skipped as "deferred". *(#6, #7)*
- [ ] **Local browser lanes run in parallel.**
  - `scripts/run-tests.sh` runs the browser lanes 3 at a time, with the unit
    suite outside the concurrent set.
  - The `shared` lane is rebalanced so no lane exceeds its recorded time budget.
  - The partition-invariant test covers any new lane.
  - A concurrent trial run matches the sequential pass set.
  - The full local gate measures 20 minutes or less. *(#3 local)*
- [ ] **CI split and filtered.**
  - CI runs the browser work as 3 resource-limited tasks driven by
    `run-tests.sh --lane`, with WebKit installed and required only for the
    contracts task.
  - Documentation-only pushes (`missions/`, `sorties/`, `squawks/`,
    `maintenance/`, `.flightops/`, `docs/`, `*.md`) trigger no CI run.
  - CI documentation states measured durations. *(#3 CI, #12, #13)*
- [ ] **CI installs from the lockfile.**
  - CI tasks install from the locked dependency set, through a baked image or
    Concourse caches, instead of an unlocked from-scratch install.
  - pip-audit runs on a schedule and at tag time, not only on PRs. *(#11, squawk 0107)*
- [ ] **Policy recorded.** The host concurrency policy and a per-lane time budget
  are recorded where future debriefs will compare against them:
  - local: 3 lanes;
  - CI: 3 limited tasks;
  - the local gate and CI never run at the same time.

## Stakeholders

- **Operator / maintainer.** Every flight runs this gate on every leg, and the
  ~53-minute cost has been compounding since Mission 25. CI and the local gate
  share the operator's machine.

## Constraints

- **No coverage loss.** A test may be collapsed (several cases on one server) or
  removed only when another test fails on the same regression. Each removal is
  named in the flight log with the test that covers it.
- **Real migration path stays real.** `test_db_migration.py` and any test that
  builds a partial or old-version database stay on the real path.
- **Isolation unchanged** for every test that is not explicitly opted into
  something new. No per-test reset seam (R7b) in this mission.
- **Shared-host budget.** Local parallelism is 3 lanes. CI browser tasks carry
  `cpu`/`memory` limits. The policy is that a local gate and a CI build do not
  run at the same time.
- **Lane partition invariant.** The union of lanes is always the whole browser
  suite, and `tests/test_run_tests_lanes.py` stays green.
- **Out of scope:** the local Concourse stack's own configuration lives outside
  this repo (`~/projects/concourse-local`), and its port-binding and MinIO
  credential fix (#14) is an operator task.

## Environment Requirements

- **Host install.** The existing Python 3.11+ install (`.venv`) with `uv`, ruff,
  pytest and Playwright (Chromium and WebKit).
- **Browser lanes.** Run them through `scripts/run-tests.sh` with
  `THE_ONE_TEST_NETNS=1` on this WSL2 host and `TEST_TIMEOUT=3600`.
- **CI legs.** These need the local Concourse (`fly`) and the operator to set the
  pipeline. The CI/CD reviewer could not reach Concourse from the agent shell.
- **Timing baselines.** `maintenance/2026-10-08.md`, measured sequentially on a
  quiet host.

## Open Questions

N/A — the gate-time targets and the host concurrency policy were decided by the
operator during the 2026-10-08 review. Mechanism choices left open are listed in
the flight's Technical Approach.

## Known Issues

- [ ] Flakes 0134 and 0136 are unit-tier and load-sensitive. Keep the unit suite
  outside any concurrent browser set. 0136 is fixed by the next squawk
  turnaround.
- [ ] Concourse could not be reached from an agent shell during the inspection,
  so CI durations are inferred from config, not measured.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [ ] Flight 1: [Test-suite runtime](flights/01-test-suite-runtime/flight.md):
  template databases, browser quick wins, local lane parallelism, CI split and
  locked installs, plus a conditional shared-server leg.
