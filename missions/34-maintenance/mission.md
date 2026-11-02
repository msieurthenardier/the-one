# Mission: Post-Mission-33 Maintenance

**Status**: active

## Outcome

Resolve codebase health issues identified in maintenance report
[2026-10-30](../../maintenance/2026-10-30.md). After this mission:

- the verification gate is cheap again;
- a stale connector editor can no longer silently drop a paired peer;
- an unattended routine run can be reconstructed from the logs alone;
- frequent routines do not make every open tab rebuild hidden UI;
- the dead code the inspection found is gone.

## Context

The 2026-10-30 inspection was triggered by the close of
[Mission 33](../33-routines/mission.md). It covers Missions 26–33 and sorties
02–06. Nothing was Critical, and the M33 security surfaces traced sound. Eight
findings were Action Required. This mission takes the ones that do not collide
with sortie 07 (agent tool overrides, planned on branch
`sortie/07-agent-tool-overrides`). Sortie 07 edits the agent routes,
`_restore_session` and `tools/resolver.py`, so the owned-fields, agent-PUT,
router-split and restore-split findings (#3, #4 agent half, #6, #7) wait for it.
The operator chose to fly sortie 07 first. This mission's legs do not touch its
files, so the order is not forced.

The gate, measured on a quiet host (load 0.20):

| Gate | Now | After Mission 26 | Target |
|---|---|---|---|
| Unit | 430 s, 8387 tests, about 51 ms per test | about 190 s, 5625 tests, about 30 ms per test | ≤340 s for this mission (the standing target is ≤300 s) |
| Browser | 1955 s, 17 lanes (M33 F4 close) | 1101 s | lanes back inside budget; target recorded |
| Full local gate | about 35 min | 18.4 min | stated in the flight |

Of the unit growth, about 82 s comes from test count and about 182 s from
per-test cost. The per-test cost is spread across:

- the evals tests (about 61 s);
- a per-test app build in the API-client tests (about 60 s of setup);
- real timeouts;
- AST guards that re-walk the source tree;
- real-subprocess tests.

The squawk-sized findings from the same report are handled beside this mission
as squawks 0295–0300, not here.

## Success Criteria

- [x] **Unit tier at or below 340 s.** Measured solo on a quiet host with the
  same command and flags as the 2026-10-30 profile, with no test deleted, skipped
  or xfailed to get there. It carries the work escalated from squawks 0222 and 0234. *(#1)*
- [x] **Browser lanes inside their budgets.**
  - Every lane's budget is re-read from a quiet-host `--parallel 3` run
    (squawk 0259's rule).
  - The fixed waits behind the recurring load flakes are replaced by
    condition waits.
  - A full-gate target is recorded in CLAUDE.md. *(#2)*
- [x] **A stale connector save keeps a paired peer.**
  - A peer paired between an editor's load and its Save is still stored after
    the Save.
  - A regression test performs that sequence. *(#4, squawk 0288)*
- [x] **Routine runs are reconstructable from the log.** The app log records
  each of these at INFO:
  - the scheduler's decision for each due routine (spawn, catch-up, missed,
    still-running skip, advance);
  - each run's outcome and reason;
  - each proposal approval and dismissal;
  - each purge sweep's full result. *(#12)*
- [x] **Session pushes cost less.**
  - The chat agent drawer does not rebuild on a sessions push while it is
    hidden, or when its chat count is unchanged.
  - A sessions push is JSON-encoded once, however many sockets receive it.
    *(#11)*
- [ ] **Dead code removed.**
  - The definite dead code the inspection listed is deleted.
  - `Encryptor.rotate_key` and the unused `ToolConfigRepository.list_all` are
    deleted, with their coverage moved to the code that is really used.
  - No live code is removed. *(#24, #25)*

## Stakeholders

- **Operator / maintainer.**
  - Every leg pays the gate.
  - Routine runs happen while nobody watches, so the log is the only record
    once the 30-day purge runs.
  - Connector pairing is how platform peers reach agents.

## Constraints

- **Do not touch sortie 07's files:** `api.py::create_agent`/`update_agent` and
  `_agent_response`, `app.py::_restore_session`, `tools/resolver.py`,
  `connectors/inbound.py:480-483`, the Tools tab and `tools-editor.js`. Flight 2's connector leg
  edits `update_connector` in `api.py` only.
- **No coverage loss.** A test may be collapsed or removed only when another test
  fails on the same regression. Each removal is named in the flight log with the
  test that covers it.
- **Isolation unchanged.** A shared fixture must reset every piece of state its
  tests can see. If a reset cannot be proven complete for a module, that module
  keeps its per-test fixture.
- **Host policy.** At most 3 browser lanes run concurrently. The unit suite stays
  outside the concurrent set. Timing readings count only from a quiet host
  (squawk 0259's rule).
- **No new behaviour visible to the operator** beyond the log lines and the
  preserved peers. The pushed-session-list cap is an open operator decision and
  is out of scope.

## Environment Requirements

- **Host install.** The existing `.venv` (Python 3.11+, uv, ruff, pytest,
  Playwright Chromium and WebKit).
- **Browser lanes.** Run them through `scripts/run-tests.sh` with
  `THE_ONE_TEST_NETNS=1` on this WSL2 host.
- **Baseline.** The 2026-10-30 unit profile (junit and per-file aggregation are
  summarised in the report), measured solo with `-m 'not browser and not live and
  not pixel and not requires_bwrap' -p no:cacheprovider --durations=0`.

## Open Questions

N/A. The targets and scope were decided by the operator at the 2026-10-30 review.
Mechanism choices are left to leg design and listed in each flight's Technical
Approach.

## Known Issues

- [ ] Whether the roughly 80 ms per-test app build in the API-client tests
  existed at Mission 26 was not measured, because the inspection's suite-running
  agent stalled. Leg 1 should time one fixture build at the M26 merge before
  choosing between a revert and a module-scoped app.
- [ ] `test_detail_view_indexing_poll_reindex_and_search` reads "indexed: 2"
  under a fresh, unlocked install (squawk 0241). Watch it during Leg 2.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: [Test-suite runtime II](flights/01-test-suite-runtime-ii/flight.md): unit-tier per-test cost, browser lane budgets and flake waits.
- [x] Flight 2: [Data safety and routine observability](flights/02-data-safety-and-routine-observability/flight.md): connector peers survive a stale save, routine logging, cheaper session pushes.
- [ ] Flight 3: [Dead code](flights/03-dead-code/flight.md): the definite-dead sweep, then the unused rotation and repository methods.
