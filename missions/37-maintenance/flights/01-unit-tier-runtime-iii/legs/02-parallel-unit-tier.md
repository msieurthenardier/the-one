# Leg: parallel-unit-tier

**Status**: completed
**Flight**: [Unit-tier runtime III](../flight.md)

## Objective
Run the unit tier in parallel with pytest-xdist, so it finishes under 400 s on this host with no new flakes and no change in what is tested.

## Context
- **Decision gate** (flight DD, "Measure before cutting"). Leg 1 landed at about 465-483 s, with the host loaded. Its cuts are worth about 20-25 s. The profile shows the remaining cost spread thinly: call time 337 s, setup 74 s, no fixture dominating. No serial cut list reaches 400 s, so the flight's conditional step applies: xdist.
- **History.** Mission 34 Flight 1 deferred xdist with the reason "the remaining work is made parallel-safe first ... port, PTY and process-global fixtures carry flake risk" (`missions/34-maintenance/flights/01-test-suite-runtime-ii/flight.md:33-34`). The 2026-10-30 report deferred it again, to be re-measured after Mission 34. That precondition is now met: two rounds of per-test cost work have been done.
- **Host.** 20 cores, 15 GB RAM. Host policy (CLAUDE.md "Testing") still holds: the unit tier never runs concurrently with browser lanes. xdist only parallelises within the unit run.
- **What is already per-process, and so safe per worker:**
  - the schema template (`tests/_schema_template.py::template_path`, "One migrated SQLite template per pytest process");
  - `shared_app()` (`tests/_api_app.py`, `functools.cache`).
- **The known hazard.** `tests/conftest.py` sets `THE_ONE_DATA_DIR` with `os.environ.setdefault(..., tempfile.mkdtemp(...))` at import time. xdist workers inherit the controller's environment, so every worker would get the same data directory. Every worker must get its own.

## Inputs
- Leg 1's changes, uncommitted on the flight branch.
- `pyproject.toml` `[project.optional-dependencies] dev` (line 179), which has no pytest-xdist. `uv.lock` is the lockfile.
- `Makefile:224-226`, the `test-unit` target. `scripts/run-tests.sh` passes extra arguments through to pytest.

## Outputs
- pytest-xdist in the `dev` extra, with `uv.lock` updated.
- `make test-unit` runs with `-n <N>`. N is chosen by measurement and recorded. Opting out of parallel runs is documented.
- Per-worker isolation for every process-global resource that tests share.
- Tests that cannot run in parallel are serialised by a marker or an `xdist_group`, never skipped.
- Documentation: the CLAUDE.md "Testing" bullets, and the `the_one/agents.md` runtime and budget notes.

## Acceptance Criteria
- [ ] **AC1, dependency.**
  - `pytest-xdist` (a pinned lower bound, as the other dev deps do) is added to the `dev` extra.
  - `uv lock --check` passes after `uv lock`, and `uv sync --all-extras --frozen` installs it.
  - The release-closure `pip-audit` (the `uv export --frozen` form in `.github/workflows/release.yml`'s audit job) is clean. The release closure excludes dev extras, so also run `pip-audit` on the dev environment and record the result.
  - Uv is at `~/.local/bin/uv`. Run `pip-audit` against the synced `.venv`, not through `uv run`.
  - The `uv.lock` diff adds only `pytest-xdist` and `execnet`, and is reviewed in the flight log. If `uv lock` bumps unrelated pins, revert those by re-locking with `--upgrade-package` limited to xdist, or report them instead.
- [ ] **AC2, per-worker isolation.**
  - Each worker gets its own `THE_ONE_DATA_DIR` (the design is in step 2), and the serial run behaves as before.
  - A new sentinel test asserts that when `PYTEST_XDIST_WORKER` is set, `settings.data_dir` contains the worker id. It protects the isolation against a later conftest edit.
  - The encryption key and the credential files live under `settings.data_dir`, so they are per worker too. The flight log says so.
  - Any other shared temp path, home path, port or process-global file the suite uses is per-worker, or its tests are serialised.
  - The audit and its findings are recorded in the flight log.
- [ ] **AC3, serialised tests.**
  - Tests that are not parallel-safe, such as those binding fixed ports, using PTYs, or changing `os.environ`, cwd or global files outside `monkeypatch`, run in one group (`--dist loadgroup` with `xdist_group`, or an equivalent marker).
  - Each one is listed in the flight log with its reason.
  - No test is skipped or deselected to make parallel runs pass.
- [ ] **AC4, same coverage.** A parallel run reports the same counts as a serial run of the same tree under `THE_ONE_TEST_NETNS=1`. Leg 1 left 12352 passed, 15 skipped and 5058 deselected, plus this leg's new tests; 15 skips is the expected netns count. Re-derive the serial count on this tree first (AC7 can serve).
- [ ] **AC5, stable.**
  - Three consecutive parallel runs of `make test-unit` (with `THE_ONE_TEST_NETNS=1`) all pass, with identical counts.
  - Any failure seen in those runs is fixed at its cause, not retried away, and the three runs are restarted.
- [ ] **AC6, fast.** The parallel tier's wall time is under 400 s on each of the three runs. The host load is recorded at the start and end of each. N is chosen by trying at least two values (for example 4 and 8), each recorded.
- [ ] **AC7, the serial path still works.** `make test-unit` with `-n 0`, or the documented opt-out, still passes. This is how a reader debugs one failure without workers.
- [ ] **AC8, documented.**
  - CLAUDE.md "Testing" states the parallel default, the opt-out, and that the unit tier is still never run concurrently with browser lanes.
  - `the_one/agents.md` records the new reading next to the history in the "Host policy" bullet.
  - CLAUDE.md stays lean (squawk 0397): at most two short bullets.
- [ ] **AC9, everything outside `test-unit` and `gate` is unchanged.**
  - The browser lanes in `scripts/run-tests.sh` do not pass `-n`, and `make test-browser`'s command is unchanged.
  - `make test` (bare `pytest` under `addopts`) stays serial. So do the CI tasks (`ci/tasks/test.yml`, `ci/tasks/bwrap.yml`) and `windows-tests.yml`. Only `make test-unit`, and `make gate` through it, gets `-n`.
  - `tests/test_run_tests_lanes.py` and `tests/test_evals_cli.py` pass. The latter reads CLAUDE.md and the Makefile.
- [ ] **AC10, lint and freeze.**
  - `ruff check` and `ruff format --check` are clean on `the_one/ tests/ scripts/ evals/`.
  - `tests/test_evals_freeze.py` passes.

## Verification Steps
- **AC1:** the `pyproject.toml` diff, `uv lock --check`, and the pip-audit output in the flight log.
- **AC2 and AC3:** read the isolation code and the serialised list in the flight log.
- **AC4, AC5 and AC6:** the three runs' summary lines and timings in the flight log.
- **AC7:** the serial run's summary line.
- **AC8:** the doc diffs.
- **AC9:** the `scripts/run-tests.sh` diff (none expected for lanes), plus the lane tests.

## Implementation Guidance
1. **Add the dependency.** Use the project's uv workflow: edit `pyproject.toml`, then run `uv lock` and `uv sync --all-extras --frozen` into the repo `.venv`. Never use `uv run --with-editable` (CLAUDE.md). Commit nothing.
2. **Give each worker its own data directory first.** Edit `tests/conftest.py`'s module-level block, keeping it above every `the_one` import.
   - When conftest makes its own `mkdtemp` (because no explicit `THE_ONE_DATA_DIR` was set), also set a marker such as `_THE_ONE_PYTEST_OWN_DATA_DIR=1`.
   - When `PYTEST_XDIST_WORKER` is set and that marker is present, always assign a fresh `mkdtemp(prefix=f"the-one-pytest-{worker}-")`. The inherited value is then just the controller's own temp directory.
   - An explicit CI or browser override has no marker, so it is kept.
   - Extend the long comment with this reasoning.
   - Add the AC2 sentinel test.
3. **Audit for process-global resources.** Grep `tests/` (excluding `tests/browser/`) for:
   - fixed ports and `socket.bind`;
   - `os.chdir`;
   - `os.environ[` writes outside `monkeypatch`;
   - `Path.home()` or `~` writes;
   - fixed `/tmp` paths;
   - PTY spawns;
   - `@requires_bwrap` sandboxes (`home_workspace()` from `tests/_sandbox_fixtures.py`; check it is per-worker unique);
   - module-level caches that write files.

   Classify each one as per-worker already, made per-worker, or serialised.

   The design review pre-filled most of this, so confirm rather than rediscover:
   - **`@requires_bwrap` / `home_workspace()`:** excluded from `test-unit` by `-m`, and the bwrap CI task stays serial, so no change.
   - **Port binds:** all ephemeral (`bind(("127.0.0.1", 0))`, as in `test_desktop_shell.py` and `test_mcp_library_test_missing_values.py`).
   - **`os.chdir`:** none.
   - **`os.environ` writes:** only these. They are per-process under xdist, so check them only for worker ordering:
     - `test_pty_windows.py:364-365` (check it restores);
     - `test_evals_gleepglorp_fixes.py:411,766`;
     - the `setdefault` in `test_evals_tokens.py`.
   - **`atexit`:** only in `_schema_template.py`, which is per-process.
   - **`/tmp/test-data`:** only in mocked settings.
4. **First parallel run.** Run with `-n 4 --dist load` in the background, without `-x`, so you see every failure. Use `--dist loadgroup` only if a real `xdist_group` exists. `loadfile` would unbalance the run, because `test_mcp_negotiation_fallback` alone takes about 32 s. Fix each failure at its cause, then re-run.
4a. **Timing failures.** Grep the failures for timing causes: windows, timeouts, drain waits and scheduler ticks, for example `test_mcp_negotiation_fallback`, `test_mcp_stdio_test_connect`, `test_kb_manager` and `test_routines_scheduler`. Leg 1 showed that some windows are floors set by spawn cost. The fix is a wider window or a load-independent assertion. Never a retry, and never serialisation unless you name a shared resource.
5. **Pick N.** Try N=4 and N=8. Choose the smallest N that clears 400 s with margin, and record both readings.
6. **Wire it in.**
   - `Makefile` `test-unit`: add `-n <N> --dist load`, or the chosen mode. Keep `-v` or switch to `-q`; xdist interleaves `-v` output, so read the summary line. Add an override, for example `UNIT_WORKERS ?= <N>`, so `make test-unit UNIT_WORKERS=0` runs serially.
   - `make gate` inherits the change.
   - Leave the browser targets unchanged.
7. **Prove stability.** Do the three consecutive runs (AC5 and AC6), then the serial run (AC7).
8. **Update the docs** (AC8). Then run `tests/test_run_tests_lanes.py`, `tests/test_evals_freeze.py` and ruff.
9. **Record it** in the flight log under "Leg 2" before `[LAND:leg]`.

## Edge Cases
- **pytest-timeout with xdist.** `--timeout` works per worker. `scripts/run-tests.sh` runs pytest with `setsid [unshare -rn] python -m pytest "$@"` (lines 605-620). The `-n` arguments pass straight through, workers are children in the same process group, so the group kill reaps them, and execnet uses pipes, so the netns wrapper is fine. That much was verified by reading. Still confirm after a run that no `python` worker processes survive.
- **`-x` with xdist.** It stops scheduling after the first failure, but workers may finish their current test. That is fine.
- **Tests that read the run's own output or pytest internals** (for example `tests/test_run_tests_lanes.py` or collection-count tests). Check they still pass under `-n`.
- **Module-level `tempfile.mkdtemp` in other conftests or helpers.** These are per-process, so already per-worker.
- **Load from another project on this host.** Record it next to each reading. If the host stays loaded, take the AC6 readings when the 1-minute load is below about 2, and say so in the log.
- **Flakes that only appear in parallel** are fixed at their cause. Never serialise a test just because it flaked, unless its cause is a shared resource that is then named.

## Files Affected
- `pyproject.toml` (dev extra) and `uv.lock`
- `tests/conftest.py` (per-worker data directory, and any other isolation)
- tests needing `xdist_group` markers, and the marker registration in `pyproject.toml` if needed
- `Makefile` (`test-unit`)
- `CLAUDE.md` ("Testing", two bullets at most) and `the_one/agents.md` ("Host policy" reading)

## Citation Audit
- `tests/conftest.py:36-37`: `os.environ.setdefault("THE_ONE_TEST_MODE", "1")` and `os.environ.setdefault("THE_ONE_DATA_DIR", tempfile.mkdtemp(prefix="the-one-pytest-"))`, at module level. Verified.
- `tests/_schema_template.py::template_path`: "One migrated SQLite template per pytest process", `tempfile.mkdtemp`, process-global `_template`. Verified.
- `pyproject.toml:179`: the `dev` extra lists pytest, pytest-asyncio and pytest-timeout, with no xdist. Verified.
- `Makefile:224-226`: `test-unit` runs `scripts/run-tests.sh tests/ -m '...' -v --tb=short`. Verified.
- `missions/34-maintenance/flights/01-test-suite-runtime-ii/flight.md:33-34`: the "No xdist" rationale. Verified.
- Host: `nproc` 20, 15 GB RAM. Verified, 2026-11-25.
- **Design review** (Sonnet, 2026-11-25): approve with changes, with four medium and four low issues. All are folded in:
  - an explicit data-directory design;
  - `run-tests.sh` worker reaping, verified by reading;
  - a numbered timing-failure step;
  - a pre-filled audit of process-global resources;
  - a review of the `uv.lock` diff;
  - the test count re-derived on this tree;
  - CI and `make test` stay serial;
  - `--dist load` by default.

  Answers to its questions:
  - only `test-unit`, and `gate` through it, get `-n`;
  - a reading at load below about 2, with the load recorded, is acceptable for AC6, and the closing-gate leg takes the quiet reading;
  - the controller leaking one data directory per run is acceptable, as it is today.
