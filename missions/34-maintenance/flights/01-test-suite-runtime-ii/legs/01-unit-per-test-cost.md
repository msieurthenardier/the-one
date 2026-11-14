# Leg: unit-per-test-cost

**Status**: completed
**Flight**: [Test-suite runtime II](../flight.md)

## Objective
Bring the unit tier to 340 s or less, measured solo with the baseline command, by removing per-test costs (a shared API app object, hoisted evals setup, cached source scans, injected timeouts, scripted subprocess tests) without deleting, skipping or xfailing coverage.

## Context
- Flight design decisions: target ≤340 s for this flight (standing ≤300 s); **no xdist** in this flight.
- Mission constraints: **no coverage loss** (a test is collapsed or removed only when another named test fails on the same regression, named in the flight log); **isolation unchanged** (a shared fixture must reset, or provably never hold, every piece of state its tests can see; a module whose reset cannot be proven keeps its per-test fixture); host policy (timing readings only from a quiet host: 1-minute load below about 1.0, no other test process).
- Sortie 07 (#346) and the 2026-11-01 turnaround (#347) merged after the 2026-10-30 profile and added tests, so the 430 s figure is stale. The Flight Director re-measured at `4b3dbb19` (see **Baseline at HEAD** below); that run is this leg's "before".
- This leg carries the work escalated from squawks 0222 and 0234.

### Step 1a is already located (Flight Director, at leg design)
The roughly 80 ms per-test "app build" is `FastAPI(); app.include_router(router)`. Measured at `4b3dbb19`: **53–56 ms per build** (router has 122 routes; `api.py` decorated routes grew from 93 at the M26 merge `e049be0d` to 108). No single later change added it; it grows with the route count. So the flight's fork "revert vs module-scoped app with per-test DB reset" resolves to a third, cheaper option: **share the app object, keep everything else per test.**
- The app object built by these fixtures holds no per-test state: each fixture's per-test state is the template DB connection and the encryptor, injected by `unittest.mock.patch("the_one.interfaces.web.api.get_connection" / "get_encryptor")`, which route handlers resolve at call time as module globals. Those stay per test, unchanged.
- The one app-attached state `api.py` reads is `request.app.state.execution_sandbox` (`api.py::` the handler around line 675 — `posture = getattr(request.app.state, "execution_sandbox", None)`). A test file that sets `app.state.*`, adds middleware, or uses `dependency_overrides` must **not** share the app. At design time these four files do one of those: `test_api_config_sandbox.py`, `test_encryption_status.py`, `test_self_configuration_surface.py`, `test_oauth_callback_gate.py` (re-check each at implementation; the grep was `dependency_overrides|app\.state|add_middleware`).
- About 49 test files build `FastAPI()` + `include_router(router)` (`grep -lE 'include_router\((api_)?router' tests/*.py`); `test_provider_api.py` (213 tests) and `test_db_api.py` (182) dominate.

## Baseline at HEAD
Solo run at `4b3dbb19`, 2026-11-02, start load 0.08, no other test process, the baseline command:
**8574 passed, 12 skipped in 437.46 s** (wall 459 s). Phases from `--durations=0`: call 306.7 s, setup 85.8 s, teardown 16.9 s. AC1 needs about **97 s** off.

Slowest files (junit time, setup + call + teardown):

| s | tests | file | step |
|---|---|---|---|
| 21.9 | 45 | `test_evals_outcomes` | b |
| 21.4 | 34 | `test_evals_scenarios` | b |
| 18.7 | 220 | `test_provider_api` | a |
| 16.8 | 189 | `test_db_api` | a |
| 14.5 | 16 | `test_pty_session` | e |
| 12.8 | 22 | `test_ui_ownership` | c |
| 11.5 | 29 | `test_mcp_pool` (10.0 s is one drain-timeout test) | d |
| 10.3 | 61 | `test_resolver_clip` (new in sortie 07; one property test 6.6 s) | see step f |
| 10.2 | 14 | `test_evals_harness` | b |
| 9.8 | 151 | `test_db_migration` | — (real migrations by design) |
| 8.9 | 24 | `test_evals_routines` | b |
| 8.6 | 29 | `test_kb_manager` (three teardowns at about 1.8 s each) | d |
| 8.2 | 23 | `test_cli_quit` | e |
| 8.1 | 19 | `test_mcp_negotiation_fallback` | d (audit) |
| 7.9 | 45 | `test_mcp_signin_detection` | d (audit) |
| 7.7 | 2 | `test_mcp_test_connection_stale_tokens` | d |
| 6.9 | 71 | `test_routines_api` | a |
| 6.8 | 39 | `test_kb_watcher` | — (real watcher by design) |
| 6.8 | 19 | `test_mcp_test_connection_negotiation` (5.0 s one test) | d |
| 5.5 | 56 | `test_self_configuration_api` | a |
| 5.5 | 49 | `test_desktop_split_guard` (5.5 s one test) | c |
| 5.5 | 44 | `test_execution_tools` (two `timeout_clipped_to_max` tests at about 2 s) | d |
| 4.7 | 6 | `test_evals_fingerprint` | b |
| 4.3 | 24 | `test_evals_tokens` | b |

Other single slow calls: `test_mcp_httpx_guard::test_no_code_uses_mcp_1x_only_names` 2.1 s and `test_schema_template::test_no_direct_schema_builds_outside_allow_list` 1.7 s (step c), `test_unused_selectors_script::test_cli_runs_and_exits_zero` 2.4 s (e), `test_routines_scheduler::test_once_routine_runs_without_waiting_for_the_tick` 2.2 s (d).

Full output: `/tmp/claude-1000/-home-<user>-projects-the-one/5bcc7a13-9d9b-42d0-995d-d093938fbb96/scratchpad/baseline-4b3dbb19.txt` and `.xml` (session-local; the flight log keeps the table).

## Inputs
- `main` at `4b3dbb19` on branch `flight/01-test-suite-runtime-ii`.
- `tests/_schema_template.py` (template DB), `tests/_credential_helpers.py::auth_headers`, `tests/_evals_helpers.py::evals_isolation`.
- The baseline junit/duration output at `/tmp/claude-1000/-home-<user>-projects-the-one/5bcc7a13-9d9b-42d0-995d-d093938fbb96/scratchpad/baseline-4b3dbb19.{xml,txt}`.

## Outputs
- `tests/_api_app.py` (new): the shared API app helper and its isolation check.
- The API-client fixtures in the migrated test files use it.
- Evals, source-scan, timeout and subprocess test changes per steps b–e.
- Flight log: before/after per file, each step's measured saving, every collapsed test with its covering test.
- Squawks 0222 and 0234: Disposition gains a link to the flight-log result.
- `the_one/agents.md` test conventions and CLAUDE.md "Testing": the shared-app rule.

## Acceptance Criteria
- [ ] **AC1 — unit tier ≤340 s.** The solo baseline command (Verification Steps) on a quiet host reports a pytest time ≤340 s; the pass count is the HEAD baseline's pass count plus any new tests minus only the named collapses; 12 skipped.
- [ ] **AC2 — shared API app.** `tests/_api_app.py` exposes one process-wide app (`FastAPI()` + `include_router(router)`, built once, e.g. `functools.cache`) and a fixture or context helper that tests use instead of building their own. Every test file that built `FastAPI()` + `include_router(router)` and does not touch app state, middleware or `dependency_overrides` uses it; per-test DB connections, encryptors and `patch(...)` calls stay per test exactly as before.
- [ ] **AC3 — isolation is checked, not assumed.** In the teardown of the fixture (or context helper) that hands out the shared app, a check compares the app with a snapshot taken at build time and fails if any of these changed: `app.state` (non-empty), `app.dependency_overrides` (non-empty), `app.user_middleware` (non-empty), `app.exception_handlers` (keys), `len(app.router.routes)`, `len(app.router.on_startup)`, `len(app.router.on_shutdown)`, `app.router.lifespan_context` (identity). `app.middleware_stack`, built lazily by Starlette on the first request, is expected to change and is not checked. A failing teardown assert shows as a test error, which is acceptable. A test that mutated the shared app was used to falsify the check (reported: falsified yes/no).
- [ ] **AC4 — the pattern cannot quietly regrow.** A unit test fails when a `tests/*.py` or `tests/_*.py` file other than `tests/_api_app.py` matches both `\bFastAPI\(` and `include_router\(\s*(api_)?router\b`, unless it is on an allowlist kept **in the guard test file**, each entry with a one-line reason. Files with a bare `FastAPI()` and no API router (e.g. `test_credential_gate.py`, `test_origin_allowlist.py`, `test_mcp_pool.py`) do not trip it. It reads file text with a regex (no AST walk) and costs under 0.5 s. Its docstring names its known false negatives (`api.router` through a module alias; an app built in a non-`tests/` helper). Falsified (yes/no).
- [ ] **AC5 — steps b–e attempted in payoff order, each measured.** For each of evals setup (b), source-scan guards (c), real timeouts (d) and real-subprocess tests (e): the change made and its measured saving, or "dropped: measured payoff under 5 s" (the flight's acceptable variation), is recorded in the flight log.
- [ ] **AC6 — no coverage loss.** No test is deleted, skipped or xfailed except a collapse/scripting change whose covering test is named in the flight log. Every injected timeout still exercises the timeout path: for each one, the Developer temporarily neutralizes the timeout handling by editing (or patches the constant very large), sees the test fail, and puts it back by editing; the flight log reports falsified yes/no per test. The constant is read at call time (a module attribute looked up inside the function), never captured as a default argument.
- [ ] **AC7 — suites green.** `make test-unit` and `THE_ONE_TEST_NETNS=1 make test-unit` pass (12 and 15 skips respectively, per CLAUDE.md's expected-skip note); `ruff check` and `ruff format --check` clean on `the_one/ tests/ scripts/ evals/`.
- [ ] **AC8 — records.** The flight log has the before/after per-file table (at least the 30 slowest files of the baseline), each step's saving, the final solo reading with its load average; squawks 0222 and 0234 Disposition link to it; agents.md and CLAUDE.md "Testing" state the shared-app rule.

## Verification Steps
- **AC1:** check `uptime` (1-minute load < 1.0) and `ps` (no other pytest), then
  `/usr/bin/time -f 'WALL %e s' .venv/bin/python -m pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap' -p no:cacheprovider --durations=0 -q --junitxml=<scratch>/after.xml`
  — read the pytest summary line (time, passed, skipped). Run solo; nothing else on the host.
- **AC2:** `grep -lE 'include_router\(' tests/*.py` — every hit is either `tests/_api_app.py`, an allowlisted file, or includes a different router.
- **AC3/AC4:** run the new tests; temporarily edit a test to set `shared_app.state.x = 1` (AC3) and add a raw `FastAPI()`+`include_router(router)` to a non-allowlisted file (AC4); each check fails; revert by editing.
- **AC5/AC6/AC8:** read the flight log entries.
- **AC7:** the commands as stated.

## Implementation Guidance

Re-measure solo after each step (or at least after a and after b–e together), and stop early once AC1 holds with margin — later steps are then optional but still recorded.

**Stop rule (the flight's Adaptation Criteria).** After steps a and b, measure solo and project the total from the remaining steps' estimates. If the projection is more than 20 s short of 340 s, stop, record the readings in the flight log, leave the leg `in-flight`, and signal `[BLOCKED:unit-target-short]` with the numbers: the Flight Director re-plans (xdist as a separate leg). Do not reach for step f or any coverage-reducing change to close a gap.

Rough budget at design (reviewer's estimate): a 40–60 s, b 30–50 s, c+d+e 25–40 s. Reaching 97 s needs most of it to land.

1. **a. Shared API app** (largest payoff; about 50 ms × the API-client tests).
   - Create `tests/_api_app.py`: a lazily built, cached (`functools.cache`) builder for `FastAPI()` + `include_router(router)` from `the_one.interfaces.web.api` — never built at import time — plus the AC3 snapshot-and-check. Hand it out through a context manager (or a fixture that yields it) whose exit runs the check, so a fixture that builds the app inline today (e.g. `test_provider_api.py`'s `client` at about L76 and `plan_env` at about L3311) wraps its existing body in it and the check runs in that fixture's teardown. Create the `ASGITransport` and `AsyncClient` per test, as now.
   - Migrate fixtures file by file. Keep each fixture's `connect_template_db`, encryptor and `patch(...)` context exactly; replace only the two app-building lines. Some files have more than one fixture building an app (e.g. `test_provider_api.py` builds at about L59 and L3293); migrate each.
   - Before migrating a file, grep it for `test_app.`/`app.state`/`dependency_overrides`/`add_middleware`/`include_router(` of any other router. Anything other than the plain pattern → leave the file on its own app and add it to the AC4 allowlist with the reason. Expected allowlist at design: `test_api_config_sandbox.py` (writes `app.state` and builds a full app with a lifespan — do not migrate it), `test_encryption_status.py`, `test_self_configuration_surface.py`, `test_oauth_callback_gate.py` (confirm each). The allowlist is per file; do not add per-fixture exceptions.
   - Also grep each migrated file for `patch("the_one.interfaces.web.api.<handler name>")`: routes bind handler functions at build time, so such a patch never reached a route before either; note any hit in the log rather than changing it.
   - Confirm the `openapi` grep hits (`test_kb_retrieval.py`, `test_openrouter_provider.py`, `test_provider_api.py`) are not `/openapi.json` reads on a shared app (`app.openapi_schema` is cached per app). If one is, that fixture keeps its own app.
   - `test_seam_routes_403_sweep.py` and `test_api_name_rule.py` walk `router.routes` directly; the walk needs no app, only their client fixtures migrate.
   - `ASGITransport(app=...)` with a shared app is fine: the transport holds no state across clients.
2. **b. Evals tests** (`test_evals_scenarios`, `_outcomes`, `_harness`, `_routines`).
   - Profile first with `--durations=0` on those files alone; find what each test builds (scratch data dirs, DB init through real migrations, scenario loading).
   - Hoist read-only construction to module scope (scenario loading, fixture trees). Keep `evals_isolation` per test: it resets process singletons (`db_connection._connection`, `vectors._store`, `settings.data_dir`, `HOME`). If a per-run scratch DB is built by replaying migrations, a template copy is acceptable only where the test does not assert on the migration path itself; changing code under `evals/` is allowed if its behaviour is identical (it is a dev tool, out of CI).
3. **c. Source-scan guards** (`test_ui_ownership` two tests at about 6 s each re-walk the static tree; `test_desktop_split_guard` and similar — find others from the baseline's slowest guards).
   - Cache each walk (file list and file text) once per session or module in one shared `tests/_source_scan.py` with `functools.cache`, so `test_ui_ownership`, `test_desktop_split_guard`, `test_mcp_httpx_guard` and `test_schema_template::test_no_direct_schema_builds_outside_allow_list` share it where they read the same trees. The guards must still read the working tree as of the run (session caching is fine: the tree does not change mid-run).
4. **d. Real timeouts.** `test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` (10 s real drain timeout), `test_mcp_test_connection_negotiation.py::test_unreachable_url_fails_fast_without_constructing_a_client` (about 5 s), the stale-token tests in `test_mcp_test_connection_stale_tokens.py` (about 4 s). Make the timeout constant patchable (a module-level constant read at call time, set by `monkeypatch.setattr`) and shrink it in the test; the test must still drive the timeout branch. Then audit the largest `asyncio.sleep`/`time.sleep` waits in the baseline's slowest calls (213 calls in 68 files at the inspection); replace a fixed wait with an event/condition only where the test's assertion is unchanged.
5. **e. Real-subprocess tests** (`test_pty_session` 14.5 s, `test_cli_quit` 8.9 s, `test_unused_selectors_script`). Keep at least one real end-to-end smoke test per file; script or call in-process the rest, naming the covering real test in the flight log for each changed test.
6. **f. Property tests (optional, only if AC1 is not yet met).** `test_resolver_clip.py::TestProperties` (new in sortie 07) spends 6.6 s in one parametrization. Lowering an example count or search budget reduces what the test explores, so it counts as coverage change: allowed only if the flight log states the old and new budget and why the smaller one still covers the property's input space (e.g. the field enumeration is exhaustive). Otherwise leave it.
7. **Re-measure, record, document** (AC1, AC8): final solo run; per-file before/after table in the flight log; 0222/0234 Disposition lines; agents.md (beside "Test databases come from the session template") and a one-line CLAUDE.md "Testing" note: API-client tests use `tests/_api_app.py`, not their own `FastAPI()`.

## Edge Cases
- **A test file patches something on `router` itself** (e.g. a route's dependency): sharing the app is unsafe because `include_router` copied the routes at build time — such a file keeps its own app (allowlist).
- **Tests that build the full `create_app()` app with a lifespan** are not this pattern; leave them unless the profile shows they matter, and then treat them as a separate decision recorded in the log.
- **pytest-asyncio loop scope:** the shared app object is loop-agnostic (no loop-bound state); do not make the DB connection or client module-scoped — they are loop-bound.
- **Order dependence:** a migrated file must pass when run alone and in the full suite; run a few migrated files with `-p no:randomly` absent/present as available, at least alone and together.
- **The 1-second native file-watch self-probe tests** may skip on a loaded host (CLAUDE.md skip-count note): a 14-skip reading on a loaded run is not a regression; the AC1 reading is from a quiet host.

## Files Affected
- `tests/_api_app.py` — new shared app helper and isolation check.
- `tests/test_*api*.py` and the other ~49 files listed by the grep — fixture app-building lines.
- `tests/test_api_app_guard.py` (or similar name) — AC4 guard.
- `tests/test_evals_*.py`, `tests/_evals_helpers.py`, possibly `evals/` — step b.
- `tests/test_ui_ownership.py`, other guards, possibly `tests/_source_scan.py` — step c.
- `the_one/mcp/pool.py` and MCP test-connection modules (timeout constants), their tests — step d.
- `tests/test_pty_session.py`, `tests/test_cli_quit.py`, `tests/test_unused_selectors_script.py` — step e.
- `the_one/agents.md`, `CLAUDE.md`, `squawks/0222-*.md`, `squawks/0234-*.md`, the flight log.

## Citation Audit
Checked against `4b3dbb19` at leg design (Flight Director, 2026-11-02): `api.py:675` `posture = getattr(request.app.state, "execution_sandbox", None)` — verified; `test_provider_api.py:60` `async def client(tmp_path)` and its second app-building fixture near L3293 — verified; `test_db_api.py:23` `client` — verified; `test_mcp_pool.py:1100` `test_drain_timeout_handles_stuck_worker` — verified; `test_mcp_test_connection_negotiation.py:256` `test_unreachable_url_fails_fast_without_constructing_a_client` — verified; `test_ui_ownership.py:265` / `:344` — verified; `tests/_evals_helpers.py:20` `evals_isolation` — verified. The flight's 0222/0234 statuses (`escalated`) — verified. Timings are from the HEAD baseline above, not the 2026-10-30 report.
