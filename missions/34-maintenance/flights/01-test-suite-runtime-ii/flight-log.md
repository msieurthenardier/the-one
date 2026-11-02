# Flight Log: Test-suite runtime II

**Flight**: [Test-suite runtime II](flight.md)

## Summary
Landed 2026-11-02 on branch `flight/01-test-suite-runtime-ii` (from `main` at `4b3dbb19`). Unit tier 437.46 s → 229.33 s (target ≤340 s) with no test removed; flakes 0303 and 0304 fixed; lanes re-budgeted from a quiet-host run (`agent-tabs` 510 s, `chats-transcript` 390 s); full-gate target 43 min recorded. One unrecorded load flake accepted and logged as squawk 0305.

---

## Leg Progress

### Leg 1 `unit-per-test-cost` — landed (2026-11-02)

**Result (AC1).** Solo reading, start load 0.22, no other test process, the baseline command: **8577 passed, 12 skipped in 229.33 s** (wall 242.98 s), against the HEAD baseline 8574 passed, 12 skipped in 437.46 s (wall 459 s): **-208 s, 52% under the 340 s target**. The +3 passes are the new `tests/test_api_app_guard.py` tests. Junit: `scratchpad/after1.xml`. The stop-rule reading "after steps a and b" was not taken separately: steps a-e were all done before the first full reading, and the one reading is far inside the target, so the rule was moot.

**AC7.** `ruff check` and `ruff format --check` clean on `the_one/ tests/ scripts/ evals/`. `THE_ONE_TEST_NETNS=1` unit run through `scripts/run-tests.sh` with an explicit `-m 'not browser and not live and not pixel'` (which also selects the `requires_bwrap` tests): 8614 passed, 19 skipped (the 15 netns skips + 3 bwrap skips per the CLAUDE.md note, +1 timing-conditional self-skip), 0 failed, 239 s. The plain default-`addopts` reading is the 12-skip run above.

**Changes made.**
- a. `tests/_api_app.py` (new): `shared_app()` (`functools.cache`, built lazily) plus `check_isolation()`; autouse `_shared_app_isolation` in `tests/conftest.py` runs the check after every test (AC3 deviation from the leg text: the check runs from one autouse fixture rather than in each handing-out fixture's teardown, because 43 fixtures hand the app out and the autouse check covers all of them, also for tests that call `shared_app()` inline). 43 files migrated (provider_api 2 sites, self_configuration_external 2 sites). Kept on their own app (allowlisted in `tests/test_api_app_guard.py`): `test_api_config_sandbox`, `test_encryption_status`, `test_self_configuration_surface`, `test_oauth_callback_gate` (as designed) and **three not on the design list**: `test_tools_admin_grid_assets`, `test_tools_test_button_assets`, `test_tools_admin_editor_assets` (they `mount("/static")` on the app; found when the diff showed the mount and put back). No `patch("...api.<handler>")` hits and no `/openapi.json` reads on a shared app were found. `test_seam_routes_403_sweep`'s docstring named the pattern and tripped the regex guard; reworded.
- b. `tests/_evals_helpers.py::evals_isolation` seeds the run's scratch DB from the schema template (patches `the_one.db.init_db` to `copy_template(settings.db_path)` then run the real `init_db`); `test_evals_env` and `test_evals_run_smoke` set `EVALS_REAL_MIGRATIONS = True` and keep real migrations. The larger part of the saving: `evals/fixtures.py::FixtureServer` ran `serve_forever()` at the default 0.5 s poll interval, so each run's `stop()` waited about 0.35 s; it now uses `poll_interval=0.02` (a dev tool, behaviour identical). Evals files (11) 66.9 s to 19.0 s in isolation.
- c. `tests/_source_scan.py` (new: cached `py_files`, `text`, `static_js_files`). `test_ui_ownership`: `measure()` cached and a substring pre-check before each regex (exact; 12.8 s to 0.7 s). `test_desktop_split_guard`: skip files whose text lacks `the_one.interfaces.desktop` and every conftest shell fixture name (exact: every shell reference spells the package or uses such a fixture) (5.5 s to 0.3 s). `test_mcp_httpx_guard` and `test_schema_template` pre-filter on the words a hit must contain and share the cached reads.
- d. Timeouts as module attributes read at call time: `_pool._WORKER_TEARDOWN_TIMEOUT_SECONDS` (10 s; `test_drain_timeout_handles_stuck_worker`, now 0.2 s and a measured `< 5 s` assertion instead of `wait_for`, which could not fail), `streamable_http._PROBE_TIMEOUT_SECONDS` (5 s; `_probe_auth_posture(timeout=None)` resolves it at call time; unreachable-URL test 0.3 s), `MCP_DEFAULT_TIMEOUT_SECONDS` in the two stale-token tests (3 s to 1.5 s). Test-owned `http.server`s (`tests/fixtures/oauth/__init__.py::OAuthASStub`, `test_cli_quit.py`) use `serve_forever(poll_interval=0.02)`: the default 0.5 s made every `shutdown()` wait (stale-token pair 7.7 s to 3.2 s, `test_cli_quit` 8.2 s to 0.9 s, `test_mcp_signin_detection` 7.9 s to 2.0 s).
- e. `pty_unix._CLOSE_GRACE_SECONDS` (1 s SIGTERM grace in the passthrough `close()`; an interactive bash ignores SIGTERM, so every PTY test waited the whole second); `test_pty_session` autouse fixture shrinks it to 0.05 s (14.5 s to 3.9 s). `test_cli_quit` was step d's poll interval, not subprocess scripting. `test_unused_selectors_script::test_cli_runs_and_exits_zero` (2.3 s, one real subprocess smoke): dropped, measured payoff under 5 s. Step f (property tests) not touched.

**Falsification (AC3, AC4, AC6).**

| Test / check | Falsified |
|---|---|
| AC3 isolation check (temporary test set `shared_app().state.x = 1`) | yes: teardown error "changed by a test: ['state']" |
| AC4 guard (temporary file with both patterns) | yes: guard failed naming the file |
| `test_drain_timeout_handles_stuck_worker` (constant 100) | yes: failed, 30 s drain vs `< 5 s` |
| `test_unreachable_url_fails_fast_without_constructing_a_client` (100) | yes: failed at the 20 s pytest timeout |
| both stale-token tests (100) | yes: both failed at the 8 s pytest timeout |
| `test_pty_session` close tests (100) | yes: `test_close_kills_subprocess` did not finish within 6 s / 60 s; the hung pytest PID was killed by recorded PID |

All reverted by editing.

**Collapsed tests.** None. No test deleted, skipped or xfailed.

**Per-file before/after (junit seconds, setup + call + teardown; baseline `4b3dbb19` vs after).** Totals: 421.8 s to 215.7 s of test time.

| file | before | after | tests |
|---|---|---|---|
| test_evals_outcomes | 21.9 | 3.7 | 45 |
| test_evals_scenarios | 21.4 | 4.6 | 34 |
| test_provider_api | 18.7 | 2.6 | 220 |
| test_db_api | 16.8 | 2.6 | 189 |
| test_pty_session | 14.5 | 3.9 | 16 |
| test_ui_ownership | 12.8 | 0.7 | 22 |
| test_mcp_pool | 11.5 | 1.5 | 29 |
| test_resolver_clip | 10.3 | 10.4 | 61 |
| test_evals_harness | 10.2 | 1.1 | 14 |
| test_db_migration | 9.8 | 9.4 | 151 |
| test_evals_routines | 8.9 | 1.5 | 24 |
| test_kb_manager | 8.6 | 8.2 | 29 |
| test_cli_quit | 8.2 | 0.9 | 23 |
| test_mcp_negotiation_fallback | 8.1 | 7.9 | 19 |
| test_mcp_signin_detection | 7.9 | 2.0 | 45 |
| test_mcp_test_connection_stale_tokens | 7.7 | 3.2 | 2 |
| test_routines_api | 6.9 | 1.4 | 71 |
| test_kb_watcher | 6.8 | 6.8 | 39 |
| test_mcp_test_connection_negotiation | 6.8 | 0.7 | 19 |
| test_self_configuration_api | 5.5 | 1.1 | 56 |
| test_desktop_split_guard | 5.5 | 0.3 | 49 |
| test_execution_tools | 5.5 | 5.5 | 44 |
| test_credential_gate | 4.8 | 3.5 | 83 |
| test_evals_fingerprint | 4.7 | 1.7 | 6 |
| test_evals_tokens | 4.3 | 1.9 | 24 |
| test_discord_gateway | 4.2 | 4.3 | 13 |
| test_bench_vector_store | 4.1 | 3.6 | 19 |
| test_imports | 4.1 | 4.0 | 7 |
| test_routines_scheduler | 4.1 | 4.1 | 45 |
| test_self_configuration_surface | 4.1 | 3.7 | 11 |

Step savings (approximate, from the per-file differences): a about 60 s (API files), b about 55 s, c about 28 s, d about 25 s, e about 11 s, plus diffuse poll-interval effects.

**Notes.** Left untouched as payoff-limited or by design: `test_resolver_clip` property test (step f, not needed), `test_db_migration`, `test_kb_watcher` (real migrations / watcher), `test_kb_manager` teardowns (1.8 s x3), `test_execution_tools` timeout tests (2 s x2), `test_routines_scheduler` (2.2 s), `test_mcp_negotiation_fallback`: each under the 5 s audit bar individually; candidates if the standing 300 s target is pursued (now 229 s, already under). Production files touched (all constants/params read at call time, behaviour unchanged): `the_one/mcp/_pool.py`, `the_one/mcp/transports/streamable_http.py`, `the_one/platform/pty_unix.py`, `evals/fixtures.py`. Docs: `the_one/agents.md` "The shared API app", CLAUDE.md "Testing" note.

### Leg 2 `browser-lane-budgets-and-flakes` — landed (2026-11-02)

**Changes Made.** Test-only; no file under `the_one/` touched by this leg (the four `the_one/` paths in the tree are Leg 1's).
- 0303: `_wait_surface_id` in `tests/browser/test_studio_mcps_tab.py` (10 s monotonic deadline polling `GET /api/agents/{name}`), used at both reads.
- 0304: `test_run_now_conflict_shows_inline_message` waits for a run row with `outcome == "running"` (10 s deadline) before clicking Run now (first attempt tested `not outcome`, which never matches the stored `"running"`, and failed 0/10; corrected before any counted run); `_wait_runs` loops to a 20 s monotonic deadline.
- Budgets: `scripts/run-tests.sh` `agent-tabs` 390 to 510, `chats-transcript` 330 to 390; CLAUDE.md lane table (all measured values refreshed), re-budget sentence, `make gate` line and a "Full-gate target" paragraph.

**Quiet-host run.** `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 ... run-tests.sh --parallel 3 --tb=short`, start load 0.23 (1-min; 0.60 when polled before launch), no other test process; end load 2.08 (1-min, decaying from a 5.7 peak under the three lanes):

`PARALLEL_RESULT rc=1 total=2027s lanes=17 failed=chats-transcript`

The one failure was `tests/browser/test_flow_chat_transcript_library.py::test_continue_sends_exactly_one_message_and_the_button_goes` ("expected 1 `chat-step-limit`, resolved to 2"). Triage per the gate-flake rule: it passed 3 of 3 isolated and the whole `chats-transcript` lane re-run passed (97 passed, 229 s). It is **not a recorded squawk** (no squawk names it) and touches nothing Leg 1 changed; accepted as an unrecorded load flake and **flagged for the Flight Director to log**. AC4 asks for `rc=0`; this run is `rc=1` for that one accepted flake.

| lane | measured (s) | old measured | change | old budget | new budget |
|---|---|---|---|---|---|
| routing | 564 | 555 | +2% | 720 | 720 |
| agents | 512 | 499 | +3% | 630 | 630 |
| contracts-controls | 509 | 463 | +10% | 600 | 600 |
| chats | 370 | 329 | +12% | 420 | 420 |
| library | 348 | 361 | -4% | 420 | 420 |
| providers | 363 | 361 | +1% | 420 | 420 |
| shared | 362 | 361 | 0% | 420 | 420 |
| knowledge | 308 | 319 | -3% | 420 | 420 |
| agent-tabs | 407 | 293 | +39% | 390 | **510** (OVER BUDGET before) |
| mcp-connection | 291 | 301 | -3% | 390 | 390 |
| settings | 286 | 271 | +6% | 360 | 360 |
| chats-transcript | 291 | 250 | +16% | 330 | **390** |
| mcp | 268 | 263 | +2% | 330 | 330 |
| settings-tools | 271 | 263 | +3% | 330 | 330 |
| contracts-overlay | 246 | 241 | +2% | 330 | 330 |
| agent-routines | 245 | 236 | +4% | 300 | 300 |
| contracts-chat | 61 | 71 | -14% | 90 | 90 |

Two lanes moved more than 15% and were re-budgeted (measured x 1.25 rounded up to 30 s). No lane exceeds 1.3x its new budget; against the new table no lane is over budget. `chats-transcript`'s 291 s is from the lane that held the failing test (a failure does not shorten it much; the re-run measured 229 s, so the reading is conservative).

**Full-gate target.** Unit 229.33 s (Leg 1) + browser 2027 s = 2256 s (about 38 minutes); target 43 minutes (+15%). In CLAUDE.md.

**Repeat runs.** 0303: both tests 10/10 isolated; `agents` lane passed (174) in the parallel run. 0304: both tests 10/10 isolated; `agent-routines` lane 83 passed three times (parallel run, then two solo runs). 0229: did not recur (focus-after files in `agents`, `settings-tools`, `providers`, `contracts-overlay` all passed); 0241: `test_detail_view_indexing_poll_reindex_and_search` passed (`knowledge` lane 65 passed).

**Suites.** `tests/test_run_tests_lanes.py` 18 passed; `ruff check` and `ruff format --check` clean on `tests/ scripts/`. New tests: none (condition-wait fixes to existing tests); falsified: no (race fixes).

**Notes.** Squawks 0303/0304 are `completed` with Sign-Off left for the flight review; 0229/0241 got dated lines and stay `open`. The slower lanes (`agent-tabs` +39%) reflect tests added in Missions 33 and sortie 07 since the last reading, not this leg.

---

## Decisions

### Step 1a resolved at design: share the app object, not a module-scoped app with a DB reset
**Context**: The flight asked Leg 1a to time the per-test API app build at HEAD and at the M26 merge, then choose between a revert and a module-scoped app with a per-test database reset.
**Decision**: Measured at `4b3dbb19`, `FastAPI(); app.include_router(router)` costs 53–56 ms per build (122 routes; `api.py` decorated routes 93 at `e049be0d`, 108 now). No single change caused it, so there is nothing to revert. The app object holds no per-test state (DB connection and encryptor are injected per test by `patch` on `api` module globals; the one app-state read is `request.app.state.execution_sandbox`), so the leg shares the app object and keeps the DB, encryptor and patches per test. Files that touch app state, middleware or `dependency_overrides` keep their own app.
**Impact**: No database reset is needed, so the mission's "isolation unchanged" constraint is met by construction and enforced by a post-test check (Leg 1 AC3).

---

## Flight Director Notes

- 2026-11-02: Phase file `.flightops/agent-crews/leg-execution.md` loaded (valid: Crew, Interaction Protocol, Prompts). Mission 34 moved `planning` → `active` (its first flight is starting); flight `ready` → `in-flight`. Branch `flight/01-test-suite-runtime-ii` created from `main` at `4b3dbb19`.
- 2026-11-02: Host quiet at start (load 0.08, no test process). Re-measuring the unit tier at `4b3dbb19` with the 2026-10-30 baseline command, solo, because sortie 07 and the turnaround added tests since the 430 s profile.
- 2026-11-02: Leg 1 `unit-per-test-cost` tiered **high-risk**: a shared test fixture across about 49 files (the mission's isolation constraint) and patchable production timeout constants. Design review by a Developer before implementation; review held until the baseline run finishes so no test run perturbs the reading.
- 2026-11-02: Baseline at `4b3dbb19`, solo, start load 0.08: 8574 passed, 12 skipped in 437.46 s (wall 459 s; call 306.7 s, setup 85.8 s, teardown 16.9 s). AC1 needs about 97 s off. Per-file table in the leg's "Baseline at HEAD".
- 2026-11-02: Leg 1 design review (Developer, Sonnet): approve with changes; 0 high, 4 medium, 2 low. Central claim (shareable app object) confirmed. All six applied: AC3's snapshot set (exception handlers, `app.router.routes`, startup/shutdown lists, lifespan context; lazily built middleware stack excluded); AC4's regex (both `FastAPI(` and `include_router((api_)?router`, `tests/_*.py` helpers included, allowlist kept in the guard file, false negatives named); `test_api_config_sandbox.py` named as do-not-migrate; an explicit stop rule after steps a+b (more than 20 s short → `[BLOCKED:unit-target-short]`, re-plan with xdist); AC6 falsification per injected timeout; the check runs in the handing-out helper's teardown. Reviewer's questions answered in the leg: allowlist lives in the guard; per-file allowlist only, no per-fixture exceptions. No second review: the changes refine criteria the reviewer itself specified and add no new mechanism. Leg 1 → `ready`.
- 2026-11-02: Leg 1 `unit-per-test-cost` signalled `[LAND:leg]`: 229.33 s solo (start load 0.22; 8577 passed, 12 skipped) against 437.46 s at HEAD and the 340 s target; the stop rule never applied. Production files touched for call-time constants: `the_one/mcp/_pool.py`, `the_one/mcp/transports/streamable_http.py`, `the_one/platform/pty_unix.py`, `evals/fixtures.py`. Points flagged for the flight review: the source-scan pre-filters are claimed exact but not test-proven; `test_drain_timeout_handles_stuck_worker` was rewritten to an elapsed-time assertion; the isolation check runs from an autouse conftest fixture rather than each fixture's teardown (a deviation from the leg text that the reviewer should judge); 8 allowlisted files (three `mount("/static")` asset files beyond the design list); the netns run used an explicit `-m` (19 skips = 15 + 3 bwrap + 1 timing self-skip). Host clean after the leg (no stray test process). legs_completed = 1 of 2.
- 2026-11-02: Leg 2 `browser-lane-budgets-and-flakes` designed from the current squawk state (0168/0187/0201/0204/0249 already completed; 0303 and 0304 deferred to this leg by sortie 07; 0229 waits on product defect 0228, out of scope; 0241 watched). Tiered **low-risk**: test-only condition waits in three browser files plus the budget table and CLAUDE.md, within established patterns, no product change (AC3 blocks on one). No design review; the flight-end Reviewer covers the code. Leg 2 → `ready`.
- 2026-11-02: Leg 2 `browser-lane-budgets-and-flakes` signalled `[LAND:leg]`. Quiet-host run `PARALLEL_RESULT rc=1 total=2027s lanes=17 failed=chats-transcript` (start load 0.23, end 2.08); the one failure, `test_flow_chat_transcript_library.py::test_continue_sends_exactly_one_message_and_the_button_goes`, passed 3/3 isolated and in a full lane re-run. **Flight Director call:** AC4 accepted under the gate-flake rule (isolated re-run clears it; unrelated to the flight's files). The failure had no squawk, so it is logged as **squawk 0305** (routine, deferred; revisit at the next turnaround or the next flight touching the chat transcript). Re-budgeted `agent-tabs` 390 → 510 s and `chats-transcript` 330 → 390 s; full-gate target 43 min recorded in CLAUDE.md. legs_completed = 2 of 2.
- 2026-11-02: Flight review: Reviewer tier **Sonnet**, because the diff touches `the_one/platform/pty_unix.py` (the PTY session teardown that also ends sandboxed shells) and `the_one/mcp/_pool.py`. No UI change in the flight, so no Accessibility Reviewer.
- 2026-11-02: Flight review (Reviewer, Sonnet): `[HANDOFF:confirmed]`, no blocking issues; it re-ran `make test-unit` (8577 passed, 12 skipped, 229.5 s) and judged all four source-scan pre-filters exact and the autouse isolation fixture equivalent to or better than the leg's helper-teardown design. Non-blocking notes and dispositions: (1) the isolation snapshot does not catch an in-place route swap at constant count or a handler swap under an existing key — accepted, no test does either; (2) the AC4 guard's documented false negatives — accepted for a ratchet; (3) Leg 2's `rc=1` reading — already a Flight Director call (above, squawk 0305), carried to the debrief; (4) CLAUDE.md's "against about 37 minutes sequential before it" reads as if Mission 34 came before the sequential figure — reworded in the commit pass. One review cycle. Legs 1 and 2 → `completed`.
