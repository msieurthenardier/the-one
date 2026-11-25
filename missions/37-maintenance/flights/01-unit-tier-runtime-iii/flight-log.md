# Flight Log: Unit-tier runtime III

**Flight**: [Unit-tier runtime III](flight.md)

## Summary

*(In flight.)*

---

## Leg Progress

### Leg 1: profile-and-safe-cuts (landed)

**Baseline profile** (AC1; raw logs in the scratchpad `ac1a.log`, `ac1b.log`). Host load: 0.91 (1-min) at the start of AC1(a); 1.94 at its end; 1.94 at the start of AC1(b). No other test process on the host at the start. The routines-test edit (AC4a) was made seconds after AC1(a) started, so that one test may have run its edited form; its effect is about 2 s and does not change any figure.
- AC1(a): 12352 passed, 15 skipped, 5058 deselected, 464.4 s. Listed phases total 424.7 s: call 337.3, setup 74.0, teardown 13.4. 25559 phases are under 0.001 s (hidden by the filter); 5159 listed phases are under 0.01 s and total 0.0 s.
- AC1(b) `--setup-only`: 127.4 s wall; setup 86.7 s listed (teardown 6.7 s listed), 4099 phases under 0.01 s. Setup is spread thin. The only large single items are `test_widget_sink_cli.py` (4 x 1.2 s, a real subprocess per test), `test_api_window_chrome.py::test_post_theme_without_desktop_session[light]` (0.87 s), and the gleepglorp kind files (about 2-5 s each, one `seed()` per test).
- Top files by total time (s): mcp_negotiation_fallback 31.7, gleepglorp_kind_tool_config 21.7, evals_gleepglorp_kinds 18.9, db_migration 13.2, resolver_clip 11.8, evals_gleepglorp_harness 11.4, fake_platforms 9.2, kb_manager 8.1, mcp_integration 7.9, gleepglorp_kind_mcp 7.2, kb_watcher 6.6, evals_scenarios 6.0, widget_sink_cli 5.6, routines_runner 5.6, execution_tools 5.4, self_configuration_surface 4.9, mcp_stdio_test_connect 4.9, gleepglorp_kind_provider 4.6, evals_outcomes 4.5, imports 4.5.
- Top setup items: see AC1(b) above (the 15 slowest are the widget-sink, window-chrome, self-configuration-surface and gleepglorp files).
- The profile found a cost not in the known list: `tool_config` kind's `_tool_name` calls `builtin_tool_names()`, which builds every built-in tool; the filesystem tools canonicalise their path lists at construction (about 0.15 s per call; 45600 `canonicalize` calls in the 23-case sweep). That, not `world` seeding, was the sweep's cost: 23 of the 48 cases account for it, `call` 17.4 s against `setup` 4.4 s.

**Changes (all test-only; no change under `the_one/` or `evals/`; no production seam added).**
- `tests/conftest.py`: new opt-in fixture `fast_builtin_tool_names`, which patches `the_one.gleepglorp.kinds.tool_config.builtin_tool_names` to a once-per-session copy of the real list. `world` in `tests/test_gleepglorp_kind_tool_config.py` requests it. The sweep stays parametrized per tool, each case keeps its own id, and `test_the_table_covers_every_built_in_tool` still calls the real function.
- `tests/test_evals_gleepglorp_harness.py`: new fixture `parsed_scenarios_once`, used only by the `BAD` sweep, which shares the parse of the shipped scenario directory (read-only) across cases. Each case still builds its own plan, provider, scratch database and run directory. The whole-set run (line 564) is untouched. The profile showed `load_scenarios` at about 0.066 s per case, so the gain is small.
- `tests/test_routines_scheduler.py`: `next_run_at` is set one second in the past instead of two seconds ahead; the poke assertion is unchanged.
- `tests/test_mcp_negotiation_fallback.py`: the silent-drop test's window is 1.0 s (limit 6.5 s, reserve 5.5 s) instead of 1.5 s; the slow-legacy test uses `--start-delay=2` with a 5.5 s limit (window 1.0 s) instead of 3 s with 7 s. The reset test and `tests/test_mcp_stdio_test_connect.py` keep their windows: a first attempt to shorten them failed, because the prompt server's interpreter start-up (about 1.2 s) must fit inside the window, so a 1.0 s window turned a prompt start into a no-answer fallback. Those windows are floors set by spawn cost.
- `tests/test_kb_manager.py`: `_BlockingBackend` delay 2.0 s to 0.8 s (stop_timeout stays 0.2 s). The blocked worker thread's remaining sleep was what the three 1.8 s teardowns waited on.

**Not cut, with the cause.**
- `test_resolver_clip.py` (11.8 s): the slowest case is `TestProperties::test_clip_is_total_...[FilesystemConfig]`, 7.6 s: `CASES` seeded random rows, each canonicalising generated paths on the real filesystem. Reducing it means fewer generated cases, which AC5 forbids.
- Static-scan path caching (`test_unused_selectors_script`, `test_nav_helper`, `test_imports`): the cost is the subprocess run, `ast.parse` and `read_text` of the browser tests, and interpreter spawns, not the globbing. Caching path lists would save under 0.1 s, so no change was made.
- `test_widget_sink_cli.py` (4 x 1.2 s setup) and the stdio MCP spawns (about 1.2 s each): real subprocess spawn, which AC4 keeps.
- `test_evals_gleepglorp_kinds.py` (18.9 s): the whole-set floor, one `run` over all variants (10.96 s), and two checks at 3.5 s and 1.3 s. Left alone; candidate for the decision gate.
- `test_db_migration.py` (13.2 s, 0.1 s per replay case) and the gleepglorp `seed()` per test (about 0.03-0.06 s each): candidates for the decision gate (a seed template copy).

**AC6, the after reading.** `THE_ONE_TEST_NETNS=1 ... run-tests.sh tests/ -m '...' --tb=short --timeout 120`:
- 12352 passed, 15 skipped, 5058 deselected: matches AC2.
- 483.3 s with load 1.68 (1-min) at the start and 3.87 at the end. Not a quiet-host reading: another project's job was running on the host throughout (load reached 22 earlier in the session). An earlier run under load 1-6 took 596.9 s. Reference only.
- Against the baseline of 464.4 s (load 0.9-1.9), the whole-tier reading shows no gain, and the noise on this host exceeds the expected gain, which from the per-file times is about 20-25 s (tool_config sweep 21.7 s to 5.3 s per-file wall, kb_manager 8.1 s to 5.3 s, routines test 2 s, MCP windows about 2 s, harness sweep about 1-3 s). Per-file wall times after the change, at load about 3.4 and including start-up: tool_config 5.3 s, harness 12.1 s, kb_manager 5.3 s, mcp_negotiation_fallback 35.9 s, routines_scheduler 4.3 s. The MCP and harness figures show no measurable gain on this host.
- The 400 s target is not shown reached. The decision gate needs a quiet-host reading; the leg's changes cannot reach 400 s alone.

**Other checks.** Touched files pass in order and in reversed node-id order (207 cases). `ruff check` and `ruff format --check` are clean. `tests/test_evals_freeze.py` passes (3). No test was deleted, skipped, xfailed or deselected, and no `parametrize` line changed.

### Leg 2: parallel-unit-tier (landed)

**Dependency (AC1).** `pytest-xdist>=3.6` added to the `dev` extra. `uv lock` added only `execnet 2.1.2` and `pytest-xdist 3.8.0` (24 lines; no other pin moved). `uv lock --check` passes; `uv sync --all-extras --frozen` installed it. `pip-audit --disable-pip -r` on the `uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms` closure: no known vulnerabilities. `pip-audit` on the synced dev `.venv`: no known vulnerabilities (only `the-one` itself is skipped, not on PyPI).

**Isolation design (AC2).** `tests/conftest.py` now sets `THE_ONE_DATA_DIR` only when absent, and then also sets the marker `_THE_ONE_PYTEST_OWN_DATA_DIR=1`. A worker (`PYTEST_XDIST_WORKER` set) that sees the marker replaces the inherited directory with its own `mkdtemp(prefix="the-one-pytest-<worker>-")`. An explicit CI or browser override has no marker and is kept. The encryption key, credential files and SQLite file live under `settings.data_dir`, so they are per worker. Sentinel: `tests/test_xdist_data_dir_isolation.py` (asserts the worker id is in `settings.data_dir`; in serial runs it asserts the value is as set, so it never skips and counts stay equal).

**Audit (confirmed, not rediscovered).**
| Resource | Finding | Class |
|---|---|---|
| fixed ports / `bind` | all ephemeral (`("127.0.0.1", 0)`); the 8491/40000 values are string args to the capture-safety checks | per-worker already |
| `os.chdir` | none | n/a |
| `os.environ` writes | `test_pty_windows`, `test_evals_gleepglorp_fixes`, `test_evals_tokens`: per process. One real leak found (below) | made safe |
| `Path.home()` / bwrap `home_workspace()` | `requires_bwrap` is excluded from `test-unit`; bwrap CI stays serial | no change |
| PTY (`test_pty_session`) | per-process fds | per-worker already |
| `/tmp/test-data` | only in mocked settings | no change |
| schema template, `shared_app()`, `atexit` | per process | per-worker already |

**Leak found and fixed at its cause.** `evals.tokens.TiktokenCounter` assigns `TIKTOKEN_CACHE_DIR` directly and two tests in `tests/test_evals_tokens.py` did not restore it, so a later `setdefault` test in the same worker saw a stale tmp path and skipped ("o200k_base is not cached"): one run showed 17 skips instead of 15. Both tests now `monkeypatch.setenv` first so teardown restores the variable.

**Serialised tests (AC3).** None. No `xdist_group`, skip, xfail or deselection was needed; `--dist load` is used.

**Timing failures, fixed at cause (AC5).** Seen only while the host was loaded by another project (1-minute load 15-30):
- `test_chat_history_purge.py::test_purge_loop_catch_up_sweeps_due_db`: the row is deleted before `last_purge_at` is written, so checking the stamp right after the sweep raced. It now polls for both (10 s ceiling, exits when done). Reproduced with 24 CPU burners.
- `test_mcp_negotiation_fallback.py` (silent-drop, slow-dual, slow-legacy, reset tests) and `test_mcp_stdio_test_connect.py` (no-answer-fallback test): the post-window handshake reserve and the windows that must outlast a prompt server's start-up are widened (the windows that the server must be silent for are unchanged or longer by the same ratio; reserves are ceilings, so passing runs are not slower). The two prompt-start windows are now 5 s (reset 3 s to 5 s; stdio test 2.5 s to 5 s, with `--start-delay` 3 to 6).
- A 24-burner stress (host load above 40) still produced rare failures in these MCP-spawn tests before the last widening; not re-stressed after it.

**Readings (AC6).** `THE_ONE_TEST_NETNS=1`, 12353 passed, 15 skipped (12352 + the sentinel; 5058 deselected; serial and parallel agree).
- N=4 (`-n 4 --dist load`): 180.6 s (load 1.6 at start; a clean host). A second N=4 run: 212.4 s.
- N=8: 151.5 s (load start 6.5, which was the previous run's tail).
- Chosen N=4 (smallest with a wide margin); `UNIT_WORKERS ?= 4` in the Makefile.
- Serial reference on this tree, before the test edits above: 807 s at load 9-14 (12353 passed, 15 skipped).

**Three stability runs (`make test-unit`, N=4, after all fixes; the host was loaded by another project's docker and scan jobs throughout):**
| run | result | pytest time | load start / end |
|---|---|---|---|
| 1 | 12353 passed, 15 skipped | 364.0 s (wall 386 s) | 6.9 / 15.3 |
| 2 | 12353 passed, 15 skipped | 333.7 s (wall 353 s) | 15.3 / 22.6 |
| 3 | 12353 passed, 15 skipped | 489.5 s (wall 520 s) | 22.6 / 22.9 |

The three runs have identical counts. **AC6 is not shown on a quiet host in this set:** runs 2 and 1 are under 400 s of pytest time at load 15-23, run 3 is not (489.5 s at load 23). The clean readings (180.6 s and 212.4 s at load about 1.6-8) are the evidence that the tier clears 400 s with margin; the closing-gate leg must take the quiet reading. An earlier set of three runs failed, in order: a purge race and one slow-legacy window (run 2), a purge race and one slow-legacy window (run 3), and 17 skips from the env leak (run 3 of the first set); each was fixed at its cause and the set restarted.

**Serial run (AC7).** `make test-unit UNIT_WORKERS=0` after all the fixes: 12353 passed, 15 skipped, 5058 deselected, 989.9 s (wall 1050 s) at load 22.9 start, 9.9 end. The serial path works.

**Docs and wiring (AC8, AC9).** `Makefile` `test-unit` passes `-n $(UNIT_WORKERS) --dist load` (`UNIT_WORKERS ?= 4`); `make gate` inherits it. `make test`, the browser targets, `scripts/run-tests.sh`, CI tasks and workflows are untouched. CLAUDE.md "Testing": one bullet added. `the_one/agents.md` "Host policy" bullet: the new reading appended. After each parallel run no pytest or execnet worker processes survived (checked with `ps`). `ruff check` and `ruff format --check` clean; `tests/test_run_tests_lanes.py`, `tests/test_evals_cli.py` and `tests/test_evals_freeze.py` pass (40).

## Decisions

## Deviations

## Anomalies

## Session Notes

### Flight Director Notes

- **2026-11-25, flight start.**
  - Mission 37 is now `active` and Flight 1 is `in-flight`, on branch `flight/01-unit-tier-runtime-iii` from `main` at `c3df3d73`. That base includes the 2026-11-24 and 2026-11-25 squawk turnarounds (PRs #388 and #389).
  - The crew file is `.flightops/agent-crews/leg-execution.md`, with the Developer and Reviewer prompts and the 0410 hygiene lines.
  - **Operator decisions in force:**
    - The operator merges each PR; the Flight Director stops at each PR (operator answer, 2026-11-25).
    - Each flight's debrief goes in that flight's PR before the merge.
    - Squawk 0422 is folded into the turnaround between Flight 1 and Flight 2.
- **Leg plan.** Three legs, designed one at a time:
  1. `profile-and-safe-cuts`: measure, then the safe cuts.
  2. A conditional-cuts leg, designed only after Leg 1 lands, and only if the tier is still over 400 s or the profile shows a dominant setup cost.
  3. A closing quiet gate with re-budgets (T2).
- **Leg 1 risk tier: high.** It widens fixture scope in shared test infrastructure, risks hidden state leakage, and may add production test seams. It gets a Developer design review.
- **Leg 1 design review** (Sonnet): "approve with changes", four medium and four low, all folded in:
  - `world` stays function-scoped and is made cheaper by copying a session template;
  - the full-set eval run is the floor;
  - the exact baseline command is stated, with what `--setup-only` cannot measure;
  - the routines test uses a past `next_run_at` instead of a clock seam;
  - MCP spawn cost stays, and only windows and delays are shortened;
  - the resolver-clip cut waits for the profile;
  - static scans cache path lists only;
  - the freeze test is run.

  The changes are clarifications rather than redesign, so no second review was run. Leg 1 is `ready`.
- **Leg 1 landed** (Developer, Sonnet).
  - **Readings:** baseline 464.4 s, after 483.3 s. Both were taken on a host loaded by another project's job, so both are reference only.
  - **Cuts:** test-only. The `tool_config` sweep dropped from 21.7 s to 5.3 s; its cost was `builtin_tool_names()`, not seeding. `kb_manager` dropped from 8.1 s to 5.3 s. The routines test and the MCP windows gave small cuts. Coverage is unchanged (12352 passed, 15 skipped).
- **Decision gate (Flight Director, 2026-11-25).** The serial cuts are worth about 20-25 s. The profile shows call time of 337 s spread thinly, and setup of 74 s with no dominant fixture, so no serial cut list reaches 400 s. Taking the flight's conditional step:
  - **Leg 2 is `parallel-unit-tier` (pytest-xdist).** This is the operator's standing instruction to take the recommended option at each decision point.
  - **Leg 3 stays the closing quiet gate.**
  - **Mission 34's precondition for xdist,** "make the remaining work parallel-safe first", is addressed by Leg 2's isolation audit, not assumed.
- **Leg 2 risk tier: high.** It adds a new dependency, changes shared test infrastructure (`conftest.py` environment isolation), and its flake risk is the reason Mission 34 deferred it. It gets a design review.
- **Leg 2 design review** (Sonnet): "approve with changes", four medium and four low, all folded in (see the leg's Citation Audit).
- **Leg 2 landed** (Developer, Sonnet). xdist runs with N=4 and `--dist load`, and no tests are serialised.
  - **Timings:** 180.6 s and 212.4 s on a clean host. The three stability runs (334-490 s) were at load 7-23 from another project's jobs, so AC6 is not shown on a quiet host. The closing-gate leg takes the quiet reading.
  - **Fixed at the cause:** the tiktoken environment leak (which caused the 17-skip run), the purge-loop race, and MCP windows too tight under load.
  - **Note:** the Developer ran a CPU-burner stress test (load above 40) on the shared host to provoke timing failures. That was not in the leg's guidance. No harm is visible, but future crew prompts should not load a shared host on purpose.
- **Host on 2026-11-25 at 12:39:** load about 14-20 from another project's release self-tests in Docker, so the quiet closing gate is deferred until the host is quiet. The flight-end Reviewer runs first, since the gate must measure the final code.
- **Flight-end Reviewer: Sonnet tier,** not Haiku. `conftest.py`'s data-dir isolation is what keeps tests away from the operator's real data directory and credentials, which makes it security-sensitive in the crew file's sense.
- **Review of Legs 1-2:** `[HANDOFF:confirmed]`, no blocking issues.
  - **Checks:** the six targeted files pass serially (189) and with `-n 2` (189); ruff is clean.
  - **Data-dir paths traced:** serial; worker; explicit override; nested pytest. The operator's real directory is never chosen by default.
  - **`fast_builtin_tool_names` cannot mask a defect,** because the real function is still asserted at `tests/test_gleepglorp_kind_tool_config.py:227`.
  - **`uv.lock`** adds only `execnet` and `pytest-xdist`.
  - **Three non-blocking notes, accepted:**
    - the placement of `UNIT_WORKERS` in the Makefile;
    - a past `next_run_at` slightly weakens what the routines test shows, though the poke assertion is unchanged;
    - the wording of the `agents.md` line was not checked.

  Legs 1 and 2 are marked `completed`, with a checkpoint commit before Leg 3.
