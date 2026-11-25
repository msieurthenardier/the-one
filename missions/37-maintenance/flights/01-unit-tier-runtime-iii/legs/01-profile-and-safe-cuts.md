# Leg: profile-and-safe-cuts

**Status**: completed
**Flight**: [Unit-tier runtime III](../flight.md)

## Objective
Attribute the unit tier's time at a fine grain, make the safe cuts that change no behaviour (those the 2026-11-24 report found, and those the profile finds), and record readings before and after.

## Context
- **Target** (flight DD): under 400 s on a quiet host, with no test deleted, skipped or xfailed. The standing target is 500 s (squawk 0403).
- **Starting point:** `main` reads about 470 s. Roughly 70 s must come out.
- **A miss is acceptable.** "Still over 400 s" is an acceptable result for this leg. It routes to the decision gate: a conditional-cuts leg designed after this one lands.
- **Why profile first:** the 2026-11-24 profile used `--durations-min=0.5`, which hid about 290 s of short phases. The roundtable withdrew the claim that a fixture tax causes them.
- **Known costs:**
  - Mission 36 Flight 5's three sweep files hold about 50 of their 97 s. These are `test_gleepglorp_kind_tool_config.py` 20.7 s, `test_evals_gleepglorp_kinds.py` 16.6 s, and `test_evals_gleepglorp_harness.py` 12.2 s.
  - The tails at 0.5 s or more:
    - `test_mcp_negotiation_fallback.py`, about 30 s;
    - `test_resolver_clip.py`, 9.8 s;
    - `test_unused_selectors_script.py`, 3.4 s;
    - `test_nav_helper.py` and `test_imports.py`, about 1.2-1.4 s each;
    - `test_kb_manager.py`, three teardowns of about 1.8 s;
    - `test_routines_scheduler.py::test_once_routine_runs_without_waiting_for_the_tick`, 2.1 s.
- **Async fixtures:** pytest-asyncio runs with `asyncio_mode = "auto"` and the default function loop scope (`pyproject.toml:213`). Module-scoped async fixtures are therefore out of scope for this leg.

## Inputs
- `main` at `c3df3d73`: 12352 passed, 15 skipped in about 470 s (the 2026-11-25 turnaround's unit run, quiet).
- The unit selection, `make test-unit` (`Makefile:224-226`):
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/ -m 'not browser and not live and not pixel and not requires_bwrap' -v --tb=short`.
  `scripts/run-tests.sh` passes extra arguments through to pytest.

## Outputs
- A profile summary in the flight log:
  - the top 20 files by total time;
  - the top 15 fixtures by setup time;
  - the count and total of phases under 0.01 s;
  - the host load next to each reading.
- Test-only changes, plus any production seam that keeps today's behaviour by default, that cut time without dropping coverage.
- A before and after unit-tier reading in the flight log.

## Acceptance Criteria
- [ ] **AC1, the baseline profile.** Taken before any change, on a quiet host: 1-minute load below about 1.0, and no other test process.
  - (a) `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/ -m 'not browser and not live and not pixel and not requires_bwrap' --tb=short --timeout 120 --durations=0 --durations-min=0.001`. Do not pass `-x`.
  - (b) The same selection with `--setup-only`.
  - Both runs are summarised as in Outputs. Note that `--setup-only` skips test bodies and teardown, so its total is a setup-cost estimate, not a teardown figure. Raw logs stay in the scratchpad.
- [ ] **AC2, coverage is kept.**
  - No test is deleted, skipped, xfailed or deselected.
  - Every parametrize case keeps its own test id.
  - The pass count is 12352, plus any new tests, with 15 skipped under `THE_ONE_TEST_NETNS=1`.
- [ ] **AC3, the sweeps:**
  - (a) `test_each_tools_settable_set_is_exactly_the_table_plus_enabled` (`tests/test_gleepglorp_kind_tool_config.py:230`) stays parametrized over `SETTABLE`. Its cost per case goes down by making the function-scoped `world` fixture cheaper:
    - for example, seed from a session-built template copy;
    - or skip seeding the case doesn't use;
    - or confirm that `kinds.normalize` never writes, and share a read-only seed built once per session through a sync, file-level template.
  - (b) `test_each_safety_scenario_can_fail_offline` (`tests/test_evals_gleepglorp_harness.py:1108`, one `run` per `BAD` case) shares any setup the profile shows dominates, without sharing state between runs.
  - (c) `test_every_scenario_of_the_set_can_pass_offline` (line 564) is one `run(...)` over the whole set, so its time is the floor. Leave it unless the profile shows `evals_isolation` setup dominates.
  - Record each file's before and after time.
- [ ] **AC4, the waits:**
  - (a) `test_once_routine_runs_without_waiting_for_the_tick` (`tests/test_routines_scheduler.py:458`) sets `next_run_at` to a time already past, instead of `now + 2s`. The assertion stays: the poke starts the run without waiting for the tick.
  - (b) In `tests/test_mcp_negotiation_fallback.py` and the stdio-connect and tool-timeout tests, shorten only window, `--start-delay` and timeout values, through the existing seams (`_short_window`, line 74). Each window must stay long enough for the behaviour its docstring asserts.
  - Real subprocess spawn cost stays, so no shared server: each test asserts negotiation on its own connection.
  - No production behaviour changes. Any new production seam must default to today's behaviour, and is named in the flight log.
- [ ] **AC5, smaller cuts:**
  - The static-scan tests cache their file lists (paths only, not parsed content) per session.
  - The KB-manager tests use a short drain timeout.
  - The slowest `test_resolver_clip.py` test is identified from AC1, and is cut only if the cause allows it without dropping cases. Otherwise the cause is recorded.
- [ ] **AC6, the after reading:**
  - Use the same command as AC1(a) without the durations flags, on a quiet host, with the load recorded.
  - The pass count matches AC2.
  - The reading sits in the flight log next to the baseline, with the change per file for every touched file.
- [ ] **AC7, lint and freeze:**
  - `ruff check` and `ruff format --check` are clean on `the_one/`, `tests/`, `scripts/` and `evals/`.
  - `tests/test_evals_freeze.py` passes.

## Verification Steps
- **AC1:** the flight log entry "Leg 1: baseline profile", with the summaries, the load figures and the scratchpad log paths.
- **AC2:** compare the before and after pass and skip counts. Grep the diff for `skip`, `xfail`, `deselect`, and any `parametrize` lines that were removed or changed.
- **AC3 and AC5:** the per-file before and after times in the flight log.
- **AC4:**
  - grep the diff under `the_one/`, and confirm that any change there is a seam whose default keeps today's behaviour;
  - read each changed window against its docstring.
- **AC6:** the after reading in the flight log.
- **AC7:** the ruff output, and the freeze test result.

## Implementation Guidance

1. **Profile first.** Check `uptime` and `ps -ef | grep -E "pytest|run-tests"`. Run AC1(a) in the background and wait for its completion notification, then run AC1(b). Write a small analysis script in the scratchpad that sums the durations per file and per fixture.
2. **Pick the cuts from the data.** Weigh the profile's top items against the known list in Context. If the profile shows a large cost not in that list, cut it too, under the same rules.
3. **The sweeps (AC3).**
   - `world` (`tests/test_gleepglorp_kind_tool_config.py:52-75`) uses function-scoped `tmp_path` and `monkeypatch`, and patches `get_connection` and `settings.data_dir`. Keep it function-scoped.
   - Make building it cheaper. If seeding dominates, build the seeded database once per session as a file, synchronously, with `tmp_path_factory`, then copy it per test (the `copy_template` pattern in `tests/_schema_template.py`).
4. **Waits (AC4).** Make the routines test change first, since it is trivial. For the MCP files, read each test's docstring before changing a value.
5. **Small items (AC5).** Cache path lists in a session-scoped fixture or a module-level `functools.cache`. A test that creates files must not see a stale list.
6. **Check fixture changes for state leaks.** Run each touched file twice: once normally, and once with its node ids in reverse order (`-p no:cacheprovider`). `pytest-randomly` is not installed.
7. **Re-run the touched files** after each cut, with `-x --timeout 120`. Run `tests/test_evals_freeze.py` after any edit near `evals/` helpers.
8. **Take the after reading** (AC6) on a quiet host.
9. **Write it up.** Record everything in the flight log under a "Leg 1" entry before `[LAND:leg]`.

## Edge Cases
- **Real-time semantics:** a test that asserts "waits the whole window" keeps a window long enough for its assertion. Shorten the window, never the assertion.
- **Leakage:** a shared seed is copied per test, never written in place.
- **`evals/` is frozen.** The scoring modules (`harness.py`, `checks.py`, `outcomes.py`, `judge.py`) are pinned by `tests/test_evals_freeze.py`. Change tests only. If a speed-up needs an `evals/` change, stop and record it in the flight log for the decision gate.
- **A host that won't go quiet:** wait, or record the load and mark the reading as reference only.

## Files Affected
- `tests/test_gleepglorp_kind_tool_config.py`, `tests/test_evals_gleepglorp_harness.py` (possibly `tests/test_evals_gleepglorp_kinds.py`)
- `tests/test_routines_scheduler.py`, `tests/test_mcp_negotiation_fallback.py`, and the stdio-connect and tool-timeout tests
- `tests/test_unused_selectors_script.py`, `tests/test_nav_helper.py`, `tests/test_imports.py`, `tests/test_kb_manager.py`, `tests/test_resolver_clip.py`
- shared test helpers, if a session cache or template lives there
- `the_one/...`: only seams that keep today's behaviour by default, if any

## Citation Audit
- `tests/test_gleepglorp_kind_tool_config.py:230`: the `SETTABLE` parametrize. Its `world` fixture (lines 52-75) is function-scoped and uses `tmp_path` and `monkeypatch`. Verified (design review).
- `tests/test_evals_gleepglorp_harness.py:564`: one `run(...)` over the whole set. The `BAD` parametrize at line 1108 runs one `run` per case. Verified (design review).
- `tests/test_mcp_negotiation_fallback.py:74`: `_short_window` shortens the probe timeout, the no-answer floor and the handshake reserve. Tests spawn real stdio subprocesses. Verified.
- `tests/test_routines_scheduler.py:458`: `next_run_at = now + 2s` is set on purpose. Verified (design review).
- `tests/test_nav_helper.py:770`: `_STATIC_JS.rglob("*.js")`. Verified.
- `pyproject.toml:213`: `asyncio_mode = "auto"`, with no loop-scope override. Verified.
- `Makefile:224-226`, the `test-unit` command; `scripts/run-tests.sh` passes `"$@"` through (lines 617-620). Verified (design review).
- `pytest-randomly` and `pytest-xdist` are not in the `dev` extra (`pyproject.toml:179`). Verified (design review).
- **Design review, 2026-11-25:** "approve with changes", with four medium issues and four low. All are folded in above. The answers to its questions are:
  - each tool stays its own test id;
  - the loop scope is per function;
  - only window and delay timeouts count as waits, and spawn cost stays.
