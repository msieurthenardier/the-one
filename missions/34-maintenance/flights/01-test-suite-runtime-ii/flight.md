# Flight: Test-suite runtime II

**Status**: landed
**Mission**: [Post-Mission-33 Maintenance](../../mission.md)

## Contributing to Criteria
- [x] Unit tier at or below 340 s (the work escalated from squawks 0222 and 0234). *(#1)*
- [x] Browser lanes inside their budgets; flake waits replaced; gate target recorded. *(#2)*

---

## Pre-Flight

### Objective
Bring the unit tier from 430 s back to 340 s or less. Bring every browser lane back inside a budget read from a quiet host. Do both without losing coverage. The unit work removes per-test costs that grew after Mission 26:
- per-test app builds in the API-client tests;
- a per-test evals harness;
- AST guards that re-walk the source tree;
- real timeouts;
- real-subprocess tests.

The browser work re-reads the lane budgets and replaces the fixed waits behind the recurring load flakes.

### Open Questions
N/A. This is a maintenance flight. The targets were set at the [2026-10-30 review](../../../../maintenance/2026-10-30.md). Mechanism choices are listed under Technical Approach.

### Design Decisions

**Target: unit ≤340 s in this flight, standing target ≤300 s**: 340 s is what the profiled fixes are projected to reach without xdist (Tools Inspector: 320–340 s).
- Rationale: it is a fixed bar the profile supports. xdist is re-measured only after it (deferred item #5).
- Trade-off: the standing 300 s target is not met by this flight alone.

**No xdist in this flight**: the remaining work is made parallel-safe first.
- Rationale: CPU is about 50% idle, so xdist could reach a 150–200 s ceiling. But the port, PTY and process-global fixtures carry flake risk, and the recurring flakes are already load-sensitive.
- Trade-off: the larger win is deferred.

### Citation Audit

Verified at `e33e8657` by the 2026-10-30 inspectors; spot-checked by the Flight Director:

| Citation | Status |
|---|---|
| `tests/test_provider_api.py::client` (L59-60) — function-scoped async client per test (16.1 s setup over 203 tests) | verified |
| `tests/test_db_api.py::client` (L23) — function-scoped async client per test (14.5 s setup over 188 tests) | verified |
| `tests/test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` (L1100) — 10.0 s call on a real drain timeout | verified |
| `tests/test_ui_ownership.py::test_ownership_matches_allowance` (L265), `::test_total_uses_are_exact` (L344) — 6.0 s each, each re-walks the static tree | verified |
| `tests/test_evals_scenarios.py` (module fixture at L75) and `test_evals_outcomes.py` — 21.5 s / 21.4 s per file | verified (timings), fixture shape to re-read at leg design |
| `scripts/run-tests.sh` budget table (L62+) and the quiet-host rule comment (L64) | verified |
| Mission 26 flight merge `e049be0d` (the post-M26 baseline: 5616 passed, 201.67 s under netns) | verified |

Re-audit at leg design time; line numbers drift.

### Prerequisites
- [x] A quiet host for each timing reading: 1-minute load below about 1.0 and no other test process.
- [x] Sortie 07 is not running its gate at the same time (it shares the host).

### Pre-Flight Checklist
- [x] All open questions resolved (N/A, maintenance flight)
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified (at leg start)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**Baseline.** The 2026-10-30 profile: 8387 passed, 12 skipped, 429.95 s pytest and 462 s wall.
- **Phases:** call 294 s, setup 91 s, teardown 17 s, collection about 28 s.
- **Command:** `python -m pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap' -p no:cacheprovider --durations=0 --junitxml=...`, solo, load 0.20.
- **Re-measurement:** every leg ends with that command, run solo, and records per-file deltas in the flight log.

**1. `unit-per-test-cost` (#1; escalated from 0222 and 0234).** Work in order of measured payoff, re-measuring after each step.
- **a. Locate the app-build cost first.**
  - Time one `client` fixture build at HEAD and at the M26 merge (`e049be0d`) with a scratch `git worktree`.
  - If one later change (lifespan, factory, middleware) added most of the roughly 80 ms, fix that change.
  - Otherwise move the API-client tests to a module-scoped app with a per-test database reset copied from the template. The files are `test_provider_api`, `test_db_api`, `test_connector_routes`, `test_routines_api`, `test_self_configuration_api`, `test_api_name_rule` and `test_time_settings_api` (about 600 tests, about 60 s of setup). Projected saving: 35–50 s.
  - The reset must cover every process-global those tests can see. List them in the leg.
- **b. Evals tests** (`test_evals_scenarios`, `_outcomes`, `_harness`, `_routines`; about 61 s). Share the harness and scratch-directory construction at module scope. Projected saving: 25–35 s.
- **c. Source-scanning guards** (`test_ui_ownership`, `test_desktop_split_guard` and similar). Cache each tree walk in a session fixture. Projected saving: 12–15 s.
- **d. Real timeouts** (`test_mcp_pool::test_drain_timeout_handles_stuck_worker` at 10 s, `test_mcp_test_connection_negotiation::test_unreachable_url_fails_fast…` at 5 s, the stale-token tests at about 4 s). Inject the timeout constant. Audit the largest of the 213 `sleep` calls in 68 files. Projected saving: 15–25 s.
- **e. Real-subprocess tests** (`test_pty_session` 14.5 s, `test_cli_quit` 8.9 s, `test_unused_selectors_script`). Keep one real smoke test each and script the rest, naming the covering test for each change. Projected saving: 10–15 s.
- **Done when:** the unit tier is ≤340 s in a solo re-measurement.
  - Record the before and after per file.
  - Record the result in the flight log and link it from 0222/0234's Disposition.

**2. `browser-lane-budgets-and-flakes` (#2).**
- **Replace the fixed waits** behind the recurring load-sensitive flakes with condition waits: 0168, 0187, 0201, 0204 (`test_row_delete_arms_confirms_and_focuses_the_neighbour`), 0229 (re-test after 0228 lands) and 0249 (OAuth popup). Read each squawk's evidence first, since some may already be closed.
- **Then re-budget.** Run one quiet-host `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3` and re-budget, under squawk 0259's rule, every lane that moved more than 15%.
- **Record** a full-gate target (unit plus browser) in CLAUDE.md beside the lane table, as measured plus headroom, with the reading it came from.
- **Watch** `test_detail_view_indexing_poll_reindex_and_search` (squawk 0241's "indexed: 2").

### Checkpoints
- [x] Leg 1a: the app-build cost is located (revert vs module-scoped app decided)
- [x] Unit ≤340 s
- [x] Quiet-host `--parallel 3` run green (one flake accepted, squawk 0305); budgets updated

### Adaptation Criteria

**Divert if**:
- A module-scoped app cannot be reset completely for a test module. Keep that module per-test and record why.
- The unit tier is still above 340 s after steps a–e. Re-plan with xdist as a separate leg.

**Acceptable variations**:
- Reordering steps b–e, or dropping one whose measured payoff is under 5 s.
- Fixing a flake by deleting a duplicate test that another test already covers (named in the log).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `unit-per-test-cost` - Locate the app-build cost; hoist API-client and evals fixtures; cache guard scans; inject timeouts; trim real-subprocess tests. Unit ≤340 s.
- [x] `browser-lane-budgets-and-flakes` - Condition waits for the recurring flakes; quiet-host re-budget; record the full-gate target.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated (CLAUDE.md lane table and gate target; agents.md fixture conventions if a new shared fixture pattern lands)

### Verification
- The solo unit command from the baseline reports ≤340 s with the same pass count plus any new tests, and the same 12 skips.
- A quiet-host `--parallel 3` run ends with `PARALLEL_RESULT rc=0` and no `OVER BUDGET` lane.
