# Leg: browser-lane-budgets-and-flakes

**Status**: completed
**Flight**: [Test-suite runtime II](../flight.md)

## Objective
Replace the fixed waits and unguarded reads behind the open load flakes with condition waits, then re-budget every browser lane from one quiet-host `--parallel 3` run and record a full-gate target in CLAUDE.md.

## Context
- Flight Technical Approach step 2 (#2). Mission constraint: host policy (at most 3 lanes concurrently, the unit suite outside the concurrent set, readings only from a quiet host — squawk 0259's rule, CLAUDE.md "Quiet-host rule").
- **The flake list moved since the flight was written** (Flight Director, at leg design, 2026-11-02):
  - 0168, 0187, 0201, 0204 and 0249 are already `completed`; their fixes replaced the waits. Nothing to do.
  - **0303** (deferred to this leg by sortie 07): `tests/browser/test_studio_mcps_tab.py` reads `_get_agent(...)["mcp_source_ids"]` once, right after the Self-configuration switch shows checked, before the loopback surface is attached — `:1100` (`test_self_configuration_enable_then_save_keeps_the_surface`) and `:1143` (`test_set_sources_keeps_an_expanded_unsaved_tile`). `IndexError` under load. `agents` lane.
  - **0304** (deferred to this leg by sortie 07): `tests/browser/test_flow_agent_routines.py::test_run_now_conflict_shows_inline_message` (`:667`; 4 s mock delay set at `:669`, the 409 sentence read at `:679`) races the tab refresh; `tests/browser/test_flow_agent_routines_form.py::test_immediately_runs_a_repeating_routine_at_once` (`:1373`) depends on `_wait_runs` (`:1327`), a fixed 40 × 500 ms poll. `agent-routines` lane. Reproduces on the base.
  - **0229** says "re-test after 0228 lands". 0228 (Save before the model list loads stores an empty model) is an open **product** defect that needs a design choice (disable Save vs keep the stored model as an option), so it is out of this flight's scope and has not landed. 0229 stays open as the known-flake record; this leg only records whether it recurred in the re-budget run.
  - **0241**: watch `tests/browser/test_flow_studio_knowledge_inventory.py::test_detail_view_indexing_poll_reindex_and_search` ("indexed: 2"); it fails only on an unlocked fresh install, so in this venv it should pass. Record its result.
- The lane budget table lives in `scripts/run-tests.sh` (source of truth) and is mirrored in CLAUDE.md's "Lane time budgets" table; `tests/test_run_tests_lanes.py` pins that every canonical lane appears once in the budget table.
- CLAUDE.md's `make gate` "about 18 minutes measured" line predates Missions 27–33 and is stale.
- Leg 1 (`unit-per-test-cost`) gives the unit reading this leg's full-gate target adds to the browser reading.

## Inputs
- Leg 1 landed (its unit reading is in the flight log).
- Squawks 0303, 0304 (`deferred`), 0229, 0241 (`open`).

## Outputs
- Condition waits in `test_studio_mcps_tab.py` and the two routines test files.
- `scripts/run-tests.sh` budget table and CLAUDE.md lane table re-budgeted where a lane moved more than 15%; a full-gate target line in CLAUDE.md.
- Squawks 0303 and 0304 completed (Corrective Action, Verification, Sign-Off left for the Flight Director's review/commit); 0229 and 0241 get a dated note.
- Flight log entry with the run's `PARALLEL_RESULT` line, start load and per-lane table.

## Acceptance Criteria
- [ ] **AC1 — 0303 fixed.** Both reads poll for the surface id (a bounded `expect.poll`/deadline loop over `_get_agent`, or waiting on the switch's request response) before indexing; no fixed sleep. Each of the two tests passes 10 isolated runs in a row and a full `--lane agents` run.
- [ ] **AC2 — 0304 fixed.** `test_run_now_conflict_shows_inline_message` clicks Run now only after the in-progress run is observable (e.g. the row shows "Running…", or the run is held), then asserts the 409 sentence; `_wait_runs` polls to a deadline (time-based, not a fixed iteration count) and its callers' assertions are unchanged. Each test passes 10 isolated runs in a row and three `--lane agent-routines` runs.
- [ ] **AC3 — no product change.** The diff touches no file under `the_one/`. If a fix turns out to need one, stop and signal `[BLOCKED:product-change-needed]`.
- [ ] **AC4 — quiet-host re-budget.** One `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 PYTHON=.venv/bin/python bash scripts/run-tests.sh --parallel 3 --tb=short` run, started at 1-minute load below about 1.0 with no other test process, ends `PARALLEL_RESULT rc=0`. A failing test is triaged by the gate-flake rule (isolated re-run; a known squawk flake that passes isolated is accepted and named); a non-flake failure blocks the leg. Every lane whose measured time moved more than 15% from CLAUDE.md's "measured" column gets budget = measured × 1.25 rounded up to 30 s, in both `scripts/run-tests.sh` and CLAUDE.md's table; lanes within 15% keep their budget. No lane is `OVER BUDGET` against the new table.
- [ ] **AC5 — full-gate target recorded.** CLAUDE.md states, beside the lane table: the full local gate's measured time (Leg 1's final solo unit reading plus this run's `--parallel 3` total), a target of measured plus about 15% headroom rounded to the minute, and the readings and loads it came from; the stale `make gate` "about 18 minutes measured" line is replaced with the new reading.
- [ ] **AC6 — records.** The flight log has the `PARALLEL_RESULT` line, start load, the per-lane measured/old budget/new budget table, the 0229 and 0241 test results from the run, and the 0303/0304 repeat-run counts. Squawks 0303 and 0304 are marked `completed` with Corrective Action and Verification; 0229 and 0241 gain a dated line with this run's result and stay `open`.
- [ ] **AC7 — suites green.** `tests/test_run_tests_lanes.py` passes; `ruff check`/`ruff format --check` clean on `tests/ scripts/`.

## Verification Steps
- AC1/AC2: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/<file>::<test> -x` ten times (a shell loop recording each exit code), then the named lanes.
- AC3: `git diff --name-only` against the leg's start shows no `the_one/` path from this leg.
- AC4: `uptime` and `ps` before the run; read the `--parallel` summary and `PARALLEL_RESULT`.
- AC5–AC7: read CLAUDE.md, the flight log and the squawk files; run the unit test and ruff.

## Implementation Guidance
1. **0303.** Add one small helper in `test_studio_mcps_tab.py` that polls `_get_agent` until an id other than the seeded one is present (deadline about 10 s), and use it at both sites (`:1100`, `:1143`; re-grep, lines drift). Run each test 10× isolated, then `--lane agents`.
2. **0304.** In `test_run_now_conflict_shows_inline_message`, wait for the row's in-progress state before clicking Run now (read the routines row testids in `areas/studio/` for the "Running…" text; keep the 4 s mock delay or raise it if the wait needs it). Rewrite `_wait_runs` to loop to a monotonic deadline (keep about 20 s total) using `page.wait_for_timeout` between polls. Run each test 10× isolated, then `--lane agent-routines` three times.
3. **Wait for a quiet host**, then the single `--parallel 3` run (AC4). Do not run anything else meanwhile. If it fails on a non-flake, stop and report.
4. **Re-budget and record** (AC4–AC6): update `scripts/run-tests.sh`'s table and CLAUDE.md's table and its prose paragraph of re-budget history (one sentence for this reading, in the existing style); replace the stale `make gate` line; add the full-gate target.
5. **Squawks**: write 0303/0304 Corrective Action and Verification, status `completed`, `**Completed**: 2026-11-02`; leave Sign-Off for the flight review. Add dated notes to 0229 and 0241.

## Edge Cases
- **The re-budget run hits 0229**: record it as 0229 (isolated re-run must pass), do not fix it here.
- **A lane exceeds 1.3× its old budget**: re-budget it like any other moved lane, and say so in the flight log; do not split lanes in this leg.
- **Load rises mid-run** from something outside your control: record the end load; if the start load was quiet the reading stands, per squawk 0259's rule.
- **WebKit fails to launch**: under `THE_ONE_REQUIRE_WEBKIT=1` that fails the contracts lanes; fix the environment (`bash scripts/setup-webkit-userland.sh`) rather than dropping the flag.

## Files Affected
- `tests/browser/test_studio_mcps_tab.py`, `tests/browser/test_flow_agent_routines.py`, `tests/browser/test_flow_agent_routines_form.py`
- `scripts/run-tests.sh` (budget table), `CLAUDE.md` (lane table, re-budget sentence, gate line, target)
- `squawks/0303-*.md`, `squawks/0304-*.md`, `squawks/0229-*.md`, `squawks/0241-*.md`, the flight log

## Citation Audit
Checked at `4b3dbb19` (Flight Director, 2026-11-02): `test_studio_mcps_tab.py:1100` `surface = _get_agent(app_clean, "sc-keep-agent")["mcp_source_ids"][0]` and `:1143` `surface = [i for i in _get_agent(app_clean, "keep-agent")["mcp_source_ids"] if i != sid][0]` — verified; `test_flow_agent_routines.py:667` `def test_run_now_conflict_shows_inline_message`, `:669` `_set_delay(..., 4000)`, `:679` `routine-error` — verified; `test_flow_agent_routines_form.py:1327` `_wait_runs` (`for _ in range(40)` … `page.wait_for_timeout(500)`) and `:1373` `test_immediately_runs_a_repeating_routine_at_once` — verified. Squawk statuses: 0168/0187/0201/0204/0249 completed, 0303/0304 deferred, 0228/0229/0241 open — verified.
