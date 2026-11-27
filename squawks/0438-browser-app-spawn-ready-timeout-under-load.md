# Squawk 0438: the browser fixtures' app-spawn ready wait (15 s) times out under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: 2026-11-27

## Report

In the squawk 0428 verification run (full browser gate, `--parallel 3`, load 8 to 20), 14 of 15 setup errors were `TimeoutError: App at http://127.0.0.1:<port> not ready within 15.0s`. That means the test's uvicorn subprocess did not answer `/api/live` within 15 s of spawn. This is before any `_nav` call, so it is not the 0428 class. All 14 passed when re-run in isolation at load 8. Under load, each one costs a whole test (setup error) and turns its lane red.

## Evidence
- `tests/browser/conftest.py::_wait_for_ready`: `timeout: float = 15.0` default. The spawn site (`tests/browser/conftest.py:283`) passes `timeout=15.0` explicitly. The function already fails fast if the subprocess exits, so a longer timeout only costs time when the app is genuinely slow to start, not on crashes.
- 0428 run record: `squawks/0428-nav-goto-has-no-boot-ready-wait.md`, Verification ("14 of the errors were `App subprocess ... not ready within 15.0s`").

## Corrective Action
The spawn-ready timeout is now one value, 45 s, overridable with `THE_ONE_TEST_APP_READY_TIMEOUT` (seconds). It lives in a new import-light helper, `tests/browser/_app_ready.py::app_ready_timeout()`, which a bad value (non-numeric, zero, negative, nan, inf) makes raise `ValueError` naming the variable; an empty value means unset. `tests/browser/conftest.py::_wait_for_ready` now defaults `timeout=None` to that helper, and the spawn site calls it too, so the two cannot drift. `_wait_for_ready` still raises at once if the subprocess exits, so crashes cost nothing extra.

Other readiness waits (no change):
- `tests/test_self_configuration_surface.py::_wait_ready` (10 s): an in-process uvicorn task on the test's own event loop, not a subprocess; a different class, left alone.
- `tests/test_desktop_shell.py`: a bare ASGI stub answers `/api/live` to exercise the launcher's own `_wait_until_serving`, which is product behaviour under test.
- `tests/test_operator_port_guard.py`: probes that the guard refuses a port; no spawn.
- `tests/test_nav_helper.py`: a source-text assertion, no wait.
- `tests/test_mcp_cache_cleanup.py`, `tests/test_fake_platforms.py`, `tests/test_logging_config.py`, `tests/test_window_state.py`, `tests/conftest.py`: no `/api/live` wait.

Documented in `the_one/agents.md` (browser test lanes, run policy). Pinned by `tests/test_browser_app_ready_timeout.py` (unit tier). `CLAUDE.md` is unchanged.

## Verification
- `ruff check tests/` clean; `ruff format --check tests/` clean (761 files).
- `tests/test_browser_app_ready_timeout.py`: 9 passed. Falsified: making a non-numeric value fall back to the default failed `test_bad_value_fails_loudly[abc]`; restored, 9 passed.
- `THE_ONE_TEST_NETNS=1 make test-unit` (load 20 to 23, from other work): 6 failed, 12393 passed, 15 skipped in 255.85 s. The failures were `test_mcp_pool::test_acquire_lazy_spawn_creates_worker_and_returns_client` (the known 0431 flake) and five in `tests/test_self_configuration_surface.py` (in-process server with a 10 s ready wait, untouched here). Both files re-run alone at load 23: 45 passed.
- `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 ... run-tests.sh --lane chats`: 178 passed in 473.68 s, start load about 23, end load 3.6. The fixtures spawn and run with the new default.

- Review fix: `_spawn_app` now resolves `ready_timeout = app_ready_timeout()` before `subprocess.Popen`, so a bad `THE_ONE_TEST_APP_READY_TIMEOUT` raises before any child exists (no orphaned uvicorn holding a port); the wait passes `timeout=ready_timeout`. New unit pins: `test_spawn_resolves_the_timeout_before_popen` (falsified by moving the call after `Popen`: it failed; restored), a tightened `test_conftest_uses_the_helper_at_both_sites` that pins the exact spawn-site shape, and `test_env_none_reads_os_environ` for the real `os.environ` path. The `agents.md` bullet moved to "Browser test lanes, budgets and run policy". A duplicated comment in `_spawn_app` was removed in a second review fix; the unit file passes with 11 tests and `ruff format --check tests/ the_one/` reports all 1042 files already formatted.
- Known failures seen under load, not caused here: the `test_mcp_pool` flake is squawk 0431; the `tests/test_self_configuration_surface.py` failures are logged as squawk 0439.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; test-only, no security-sensitive surface). Three passes: a first review, a re-review of the fix cycle, and a Flight Director check of the final one-line comment deletion.
**Verdict**: confirmed.
- The first review blocked on an orphaned uvicorn child when the env value was bad. That is fixed: the timeout is resolved before `Popen`, and a source-order test pins it, falsified.
- The re-review confirmed that no path between `Popen` and the `try` can raise. The parse rejects nan, zero, negatives and inf, and the `agents.md` bullet is placed correctly.
- The duplicated comment the re-review found is removed. The Flight Director verified that one copy remains.
- The "9 passed" in the Verification's second bullet is the count before the review fix; the file now has 11 tests, all passing.
- Final results: the unit tier gave 12401 passed and 15 skipped at load 17 to 20, and the `providers` lane gave 144 passed.

**Commit**: `squawk/0438: ...` on squawk/0438-app-spawn-ready-timeout
