# Leg: local-lane-parallelism

**Status**: completed
**Flight**: [Test-suite runtime](../flight.md)

## Objective
`scripts/run-tests.sh --parallel 3` runs every browser lane three at a time within the recorded host budget, so the full local gate (unit, then parallel browser) measures 20 minutes or less. It must do this with the same pass set as a sequential run, and leave no orphaned process on timeout or interrupt.

## Context
- **Flight decision "Host concurrency policy"** (operator, 2026-10-08):
  - Locally, 3 browser lanes run concurrently.
  - The unit suite always runs outside the concurrent set.
  - A local gate and a CI build never run at the same time.
  - One lane was measured at about 1.15 GB and 3–4 cores on the 20-core / 16 GB WSL host.
- **Flight decision "Gate targets":** full local gate ≤20 min, unit ≤300 s, and every lane has a recorded time budget.
- **Mission constraint "Lane partition invariant":** the union of lanes is always the whole browser suite, and `tests/test_run_tests_lanes.py` stays green.
- **Prior legs:**
  - Leg 1 took the unit lane to about 221 s wall.
  - Legs 2–3 re-measured the sequential browser lanes. The per-lane numbers from the flight log's "Leg 3" AC7 table are the input to the rebalance here; use them, not the 2026-10-08 figures.
- **Change from the flight spec.** The flight's Verification named a behavior test, `parallel-lanes-stay-green`, to be authored at this leg. The Flight Director replaced it with the scripted pass-set comparison in AC6. The property ("concurrent lanes produce the sequential pass set across repeated runs") is fully decidable from junit output, with no judgement about a live UI, so an Executor/Validator pair would add cost without adding observation. Recorded in the flight log's Decisions.

## Inputs
- `scripts/run-tests.sh` (220 lines). It provides:
  - `--lane` and `--list`;
  - lane globs (`chats_pat`, `library_pat` with 7 files, `studio_pat`, `settings_pat`, `contracts_pat`) and `shared` as the complement;
  - a `setsid` process group, a `setsid` watchdog at `TEST_TIMEOUT`, and an EXIT trap that group-kills both;
  - the `THE_ONE_TEST_NETNS=1` `unshare -rn` wrapper.
- `tests/test_run_tests_lanes.py`:
  - `LANES` (6 lanes);
  - the disjointness, union and contracts-exactness tests;
  - the `--list` exit-code tests.
- `Makefile`:
  - `test` runs one pytest over `tests/`, mixing unit and browser.
  - `test-unit`.
  - `test-browser` runs one sequential pytest over `tests/browser/`.
- CLAUDE.md's Testing section, "Per-area browser test lanes" and the `TEST_TIMEOUT=3600` guidance.

## Outputs
- One or more new lanes split out of `shared`, and from `library` if needed, so that each lane's sequential time is about 450 s or less.
- `run-tests.sh --parallel N`, plus `--plan` to print the schedule without running.
- A per-lane budget table in `run-tests.sh`, shown in `--help` and checked in the parallel summary.
- `make test-browser` uses `--parallel 3`.
- A new `make gate` runs `test-unit`, then `test-browser`, never concurrently.
- `make test` is unchanged. With `addopts` it is effectively the unit tier, so changing it would silently add about 15 minutes to an existing habit.
- `make test`'s help text is corrected to say what it runs.
- CLAUDE.md records the budgets and the host policy.
- The flight log records the trial and the gate measurement.

## Acceptance Criteria
- [ ] **AC1. Rebalance.**
  - New lane(s) take the long pole out of `shared`: `test_router_*`, `test_nav_guard*`, `test_store*`, and others as the numbers require. The suggested name is `routing`; the Developer picks names.
  - If `library` is still over about 450 s sequential (by leg 3's measurement), split it too.
  - Every new lane:
    - is a named glob or explicit list in `run-tests.sh`;
    - is in the `--lane` usage and error text;
    - is in `tests/test_run_tests_lanes.py::LANES`;
    - is excluded from `shared`'s complement.
  - The partition tests pass.
- [ ] **AC2. The parallel runner exists.** `scripts/run-tests.sh --parallel N` (N ≥ 1, no `--lane`) runs every browser lane, at most N at a time.
  - **Child runs.** Each lane runs as its own child `run-tests.sh --lane <lane> -p no:cacheprovider` invocation. It keeps that path's own process group, watchdog and netns wrapper, and is launched under `setsid`.
  - **Schedule.** Lanes start longest-budget-first.
  - **Output.** Each lane writes its output to `<dir>/<lane>.log` and a junit file to `<dir>/<lane>.xml`.
    - `<dir>` is `$TEST_LANE_DIR` if set, else a fresh `mktemp -d`. The path is printed at start and in the summary.
  - **Arguments.** Extra pytest args pass through to every lane.
  - **Waiting for lanes.** Use `wait -n -p <var> "${lane_pids[@]}"`, which needs bash ≥ 5.1; this host has 5.2.21. The rules:
    - Pass the lane pids only, never the watchdog's.
    - Capture the exit code as `rc=0; wait … || rc=$?`, so `set -e` cannot abort.
    - Map pid → lane.
    - When `BASH_VERSINFO` is older than 5.1, fall back to a `kill -0` poll loop with `wait "$pid"`.
  - **Exit code.**
    - The parent exits 0 only if every lane exited 0.
    - A lane rc of 137 or 143 (timed out or killed) counts as a **timeout**, and the parent then exits 137.
    - Otherwise the parent exits with the non-zero code of the **first failing lane in schedule order**, which is deterministic.
    - A lane the parent killed counts as non-zero.
    - The parent never exits 0 while a lane failed.
    - A lane whose junit XML is missing or empty counts as failed, even with rc 0.
  - **Summary.** At the end it prints one line per lane: exit code, wall seconds, budget, and `OVER BUDGET` when wall > budget. Over budget is a warning; it does not fail the run. It also prints the total wall time and the log directory, even on failure.
  - **Machine-readable last line:** `PARALLEL_RESULT rc=<n> total=<s>s lanes=<k> failed=<comma list or ->`, for scripts to parse.
- [ ] **AC3. Nothing outlives the runner.** A SIGKILL cannot be trapped, and a child's pytest and watchdog groups sit in other sessions, so the cleanup is TERM-first and pgid-aware.
  - **Recording pgids.** Each child publishes its pytest pgid and watchdog pgid. When the env var `RUN_TESTS_PGID_FILE` is set, the child writes those to it, as `<dir>/<lane>.pgids`.
  - **Parent cleanup** on EXIT, INT or TERM:
    1. Send SIGTERM to every live child. The child's `trap 'exit 143' TERM` runs its EXIT trap, which group-kills its pytest and its watchdog.
    2. Wait up to 5 s.
    3. SIGKILL any child group still alive, plus every pgid recorded in the `.pgids` files.
  - **Parent timeout.** The parent's watchdog sends USR1 to the parent, never SIGKILL first. The parent's USR1 trap exits **137**, and its EXIT trap runs the cleanup. The parent's watchdog exits on its own when the parent is gone (a `kill -0` loop), so a SIGKILLed parent leaves no orphaned `sleep`.
  - **Parent-death guard.** When `RUN_TESTS_PARENT_PID` is set (the parent sets it for each child), the child's watchdog also checks every second that the parent is alive. If the parent is gone (SIGKILLed: an agent tool timeout, or a closed terminal), it group-kills the child's pytest group and exits. Children therefore never outlive a parent that was SIGKILLed.
  - **Manual checks**, recorded in the flight log with `ps` evidence that no `pytest`, `uvicorn`, `chromium`, `node` or `sleep` from the run remains within about 10 s:
    - (a) start `--parallel 3` and send SIGINT to the parent after about 60 s;
    - (b) start it again and send **SIGKILL** to the parent after about 60 s;
    - (c) start it with `TEST_TIMEOUT=90`; the run exits 137.

    Find the processes by the run's session ids or the `.pgids` files, never with `pkill` or a pattern. After each check, no `.pgids` file from a cleanly exited lane remains, and in (b) the parent's own watchdog `sleep` is gone too.
- [ ] **AC4. Arguments are validated, and `--plan` dry-runs.**
  - `--parallel N`, `--parallel=N` and `--plan` are consumed in the existing `while/case` loop, so they never reach pytest.
  - Each of these exits 2 with a usage message:
    - `--parallel` with `--lane`;
    - `--parallel 0`, a non-integer, or a missing value;
    - `--plan` without `--parallel`.
  - `--parallel N --plan` prints the schedule (lane order and budgets) and exits 0 without running pytest.
  - Unit tests in `tests/test_run_tests_lanes.py` cover the exits-2 cases.
  - They also check that `--plan` lists every canonical lane exactly once (aliases never) with a numeric budget. That test is what pins the budget table, so no placeholder can land.
  - The `--lane` usage and unknown-lane error texts list the new lanes.
- [ ] **AC5. Budgets and policy are recorded.**
  - **Where:** a lane → budget-seconds table in `run-tests.sh`. It is printed by `--help`, which is new or extended: `--help` prints usage, lanes, budgets and the host policy.
  - **How budgets are set:** each lane's budget is its wall time measured in the AC7 parallel run, plus about 25% headroom, rounded up to 30 s.
  - **CLAUDE.md, Testing section:**
    - replace the "~38 min" per-lane prose with the new lane list and budget table;
    - state the host policy: 3 local lanes, unit outside the concurrent set, local gate and CI never at the same time;
    - make `make test-browser` (now parallel) the canonical full-browser command, and `make gate` the full local gate;
    - say that `make test` is the unit tier under `addopts`;
    - keep the `TEST_TIMEOUT` guidance consistent: the parallel parent's timeout bounds the whole run.
  - **Lane list:** the "Per-area browser test lanes" list includes each new lane.
- [ ] **AC6. The concurrent trial matches the sequential pass set.**
  - Run `--parallel 3` twice, one run after the other, never overlapping, with `THE_ONE_TEST_NETNS=1` and `THE_ONE_REQUIRE_WEBKIT=1`. Both runs pass.
  - **Run 1 is the browser half of the AC7 gate measurement.** Run 2 follows it.
  - Compare the set of `(classname, name, outcome)` from each run's junit files, where `outcome` is passed, skipped or failed, so skips compare as skips. It must equal the set from leg 3's sequential run; the Flight Director gives that junit location in the spawn prompt.
  - A missing or empty lane XML is a failure, not an empty set. The comparison runs through a small script kept in the scratch area. Its result (counts, and any difference) is recorded in the flight log.
  - **Divert condition (flight spec):** if a pass set differs or a new flake appears in more than one run, stop. Log each flake as a squawk, fall back to `--parallel 2`, re-run, and report it in the `[LAND:leg]` summary.
- [ ] **AC7. The gate is measured.**
  - On a quiet host, run `make gate`'s two halves in sequence under `THE_ONE_TEST_NETNS=1`: unit, then `--parallel 3`. The `--parallel 3` half is AC6 run 1.
  - **Target: 20 minutes or less in total.**
  - Record the unit wall time, the browser parallel wall time, per-lane walls with their budgets, and the total, against the 2026-10-08 baseline (697 s unit, 2488 s browser, about 53 min).
  - If the gate is over 20 minutes, land anyway with the number recorded. The Flight Director decides leg 7 on it.

## Verification Steps
- **AC1, AC4:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_run_tests_lanes.py -x --timeout 60`, then `bash scripts/run-tests.sh --parallel 3 --plan`.
- **AC2, AC5:** read the code, and check `bash scripts/run-tests.sh --help`. The summary output of the AC6 runs shows the per-lane lines.
- **AC3:** the manual interrupt check. Record the `ps` evidence summary in the flight log.
- **AC6:** run the two trials in the background, each to its own `TEST_LANE_DIR`, then run the comparison script.
- **AC7:** the measured run. Its summary output is pasted (condensed) into the flight log.

## Implementation Guidance
1. **Rebalance first (AC1).** Use leg 3's per-file timings (its `agg.py` output) to pick the files that leave `shared`.
   - Aim for 7 or 8 lanes whose sequential times are roughly even and at most about 450 s.
   - Keep `contracts` intact; it is required with WebKit.
   - Update `LANES` and the partition tests.
2. **Restructure `run-tests.sh` without breaking the single-lane path.** AC2 and AC3 are the spec; this step only orders the work.
   - Factor the lane-file resolution into a function that `--plan` can call.
   - The parallel mode re-invokes `"$0" --lane <lane> -p no:cacheprovider <args> --junitxml=<dir>/<lane>.xml` under `setsid`, with its output redirected to `<dir>/<lane>.log`. Pass `RUN_TESTS_PARENT_PID` and `RUN_TESTS_PGID_FILE` in its environment.
     - It never forwards `--parallel`, `--plan` or another `--lane` to a child; a unit test pins this.
     - Before launching a lane, `rm -f` that lane's `.xml`, `.log` and `.pgids`, so a reused `TEST_LANE_DIR` cannot satisfy the missing-XML rule with a stale file.
   - Refill slots with `wait -n -p` over the lane pids only, per AC2, including the fallback for bash older than 5.1. Handle an empty `-p` variable: the wait was interrupted by a trap.
   - **Signals and traps (AC3):**
     - **Timeout:** USR1, with `trap 'timed_out=1; exit 137' USR1`.
     - **Interrupt or stop:** `trap 'exit 130' INT` and `trap 'exit 143' TERM`, as today.
     - **EXIT:** the trap runs the TERM-first cleanup: TERM each live child, wait up to 5 s, then KILL the child groups and every pgid still listed in a `.pgids` file.
   - **Parent watchdog (new shape; the existing `kill -KILL` pattern is not reused).** It runs under `setsid`, as a loop of `sleep 1`.
     - When `kill -0 $parent` fails, it exits, so it never outlives a SIGKILLed parent.
     - When the elapsed time reaches `TEST_TIMEOUT`, it sends USR1 to the parent, and SIGKILLs the parent only if the parent is still alive 15 s later.
   - **Child watchdog** (the single-lane path). The same `sleep 1` loop shape, with an elapsed counter against `TEST_TIMEOUT` plus the parent-death check when `RUN_TESTS_PARENT_PID` is set.
     - On a parent-death kill, it first writes a marker file next to the pgids file, or logs a line, so the child does not report "TIMEOUT".
     - Outside parallel mode it behaves exactly as today: KILL the pytest group at `TEST_TIMEOUT`.
   - **`.pgids`.** The child appends its pytest pgid right after `pgid=$!`, and its watchdog pgid right after launching the watchdog. Each append is one atomic `printf … >>` line. The child's EXIT trap deletes the file after its own cleanup, so only crashed or still-live lanes leave one. That also avoids SIGKILLing a reused pid later.
   - **Timeouts.** Each child's `TEST_TIMEOUT` equals the parent's, so the parent's watchdog is the binding cap.
   - **Labelling.** A lane rc of 137 or 143 is labelled "timeout or killed" in the summary. An OOM kill also yields 137.
   - Keep `set -euo pipefail` safe.
3. **Budget table and `--help` (AC5).**
   - Before the measured runs, fill the table with provisional budgets from leg 3's sequential numbers plus 25%.
   - After AC7 and AC6 run 1, replace them with measured-plus-25% values. That is a pure data edit, verified by the `--plan` unit test, with no further full run.
4. **Makefile.**
   - `test-browser` becomes `run-tests.sh --parallel 3 --tb=short`. With per-lane logs, `-v` only bloats them; keep it if a log reader needs it.
   - Add `gate`: `$(MAKE) test-unit` then `$(MAKE) test-browser`.
   - Leave `test` alone, apart from correcting its help text.
   - Keep `_ensure-playwright`.
   - `test-pixel` stays sequential.
5. **Run the gate, then the second trial run** (AC7 and AC6), last, on the final code, in the background, polling logs. Then make the budget data edit.

## Edge Cases
- **Residual risk.** A parent SIGKILLed before it has spawned its children's watchdogs could still leak. The parent-death guard covers every state after spawn. Document the residual window in a comment.
- **A lane fails fast.** The other lanes keep running; there is no fail-fast across lanes. The summary shows it, and the exit code is non-zero.
- **`-x` passed through.** It applies within each lane, which is fine.
- **Ctrl-C during `wait -n`.** The trap must still group-kill children. Test it in AC3.
- **netns per lane.** Each child calls `unshare -rn` itself, so lanes get separate namespaces. Ports are random per test anyway.
- **Memory.** 3 lanes at about 1.15 GB each fit the 16 GB host. Do not raise the default above 3; that is the operator's policy.
- **WebKit.** `THE_ONE_REQUIRE_WEBKIT=1` in the environment affects only the contracts files, so passing it to every lane is harmless.
- **The `--lane` alias forms** (`chat`, `studio`, `system`) are not scheduled by `--parallel`. It schedules only the canonical lanes, so no file runs twice.

## Files Affected
- `scripts/run-tests.sh`
- `tests/test_run_tests_lanes.py`
- `Makefile` (`test-browser`, new `gate`, `test` help text)
- `CLAUDE.md` (Testing: lanes, budgets, policy, canonical commands)
- `missions/26-maintenance/flights/01-test-suite-runtime/flight-log.md`

## Citation Audit
Checked against the working tree at `16e91d7` plus the uncommitted legs 1–3:

| Citation | Status |
|---|---|
| `scripts/run-tests.sh`: `--lane`/`--list` parse loop; lane pattern arrays (`library_pat` has 7 files, including `test_flow_studio_library_focus.py`); `shared` complement; `setsid` group, `setsid` watchdog, EXIT trap; `THE_ONE_TEST_NETNS` `unshare -rn` | verified |
| `tests/test_run_tests_lanes.py:21` `LANES` (6); disjoint, union, contracts and `--list` exit-2 tests | verified |
| `Makefile:216–217` `test` (one pytest over `tests/`, which `addopts` reduces to the unit tier); `:220–222` `test-unit`; `:225–227` `test-browser` (sequential `-m browser tests/browser/`); `:232` `test-pixel` | verified |
| `run-tests.sh:57` and `:125`: the `--list` usage text and the unknown-lane error text name the lanes | verified |
| No `ci/` file calls `make test`, `make test-browser` or `run-tests.sh` (only a comment in `.github/workflows/test.yml`) | verified (design review) |
