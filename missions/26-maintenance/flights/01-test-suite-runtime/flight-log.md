# Flight Log: Test-suite runtime

**Flight**: [Test-suite runtime](flight.md)

## Summary
Not started.

---

## Leg Progress

### Leg 1: unit-template-db (landed)

- Added `tests/_schema_template.py` (`template_path`, `copy_template`, `connect_template_db`, `connect_template_memory`): one template built by the real `ensure_schema` per process in a build thread, `journal_mode=DELETE`, temp dir removed at exit.
- Added `tests/test_schema_template.py` (8 tests): template shape, copy independence, equivalence with a fresh replay (versions, `sqlite_master`, all non-`schema_version` rows including FTS shadow tables, foreign_key_list/index_list/table_info), and an `ast`-based call-site guard.
- Converted 48 form-1 fixtures mechanically (side connection + `ensure_schema`), `isolated_db`, three `:memory:` sites (`test_key_reconcile`, `test_provider_repository`, `test_kb_retrieval`), and form-3 sites (`test_lifespan._isolated_data_dir`, `test_chat_history_purge`, `test_web_session_reaper`, `test_self_configuration_surface`): pre-seed `settings.db_path` with `copy_template`; direct `init_db()` / `ensure_schema()` calls removed (production lifespan still runs `ensure_schema` against the current-version file).
- `PRAGMA synchronous=OFF` added to every replaying connection in `test_db_migration.py` (100) and `test_schema.py` (2). Assertions unchanged.
- `CLAUDE.md` Testing section: one paragraph added.
- Allow-list (`ALLOWED_DIRECT_CALLERS`, 5 entries): `tests/test_db_migration.py`, `tests/test_schema.py`, `tests/test_db_connection.py` (real migration/connection path), `tests/_schema_template.py`, `tests/test_schema_template.py` (self-exempt).
- **Measured (AC9)**, `THE_ONE_TEST_NETNS=1`, sequential, `-m 'not browser and not live and not pixel and not requires_bwrap'`: **5616 passed, 12 skipped, 201.67 s** (wall about 221 s including collection) vs 697 s baseline; target of 300 s met without the session-wide synchronous fallback. Skips are the same 12 (10 Windows, 2 root-only permission). Pass count: current `main` collects 5608 passing tests (the 5598 baseline predates 10 added tests); +8 new guard tests = 5616. No test deleted, skipped or xfailed.
- Slowest after the change (`--durations=10`): `test_mcp_pool::test_drain_timeout_handles_stuck_worker` 10.0 s call; two `test_timeout_clipped_to_max` 2.0 s each; `test_kb_watcher` real-watch 1.9 s; three `test_kb_manager` teardowns 1.7-1.8 s; remaining are PTY and bench timeouts at 1.4-1.7 s. No fixture setup remains in the top 10.

### Leg 2: browser-template-db (landed)

- `tests/browser/conftest.py::_spawn_app` gains keyword `seed_db: bool = True`; after `data_dir.mkdir()` and before `Popen` it calls `copy_template(data_dir / "the-one.db")`. Docstring updated. Import `from tests._schema_template import copy_template`.
- AC2: `tests/browser/test_app_fixture.py::test_seeded_server_does_not_replay_migrations` compares the live server database's `schema_version` rows (version, `applied_at`) to the template's; equal means no replay.
- **AC3 audit: no caller needed `seed_db=False`.** Grep used: `grep -rn "the-one.db\|schema_version\|first.run\|first_run\|fresh install\|migrate_json" tests/browser/*.py` plus a read of every `_spawn_app(` caller (conftest x4, `test_app_spawn_credential_wiring`, `test_markdown`, `test_flow_oauth_callback_cross_site`, `test_flow_context_overlay_thresholds`, `test_flow_provider_ollama_pull`). The only `the-one.db` users (`test_flow_chat_visibility_distinction`, `test_flow_chat_peer_attribution`, `test_flow_provider_plan_signin`, `test_studio_self_configuration_queue`/`_history`) write via sqlite3 after the server is up; none seeds legacy JSON or asserts first-run database state.
- **AC4:** chats 168 passed / 0 skipped (twice); settings 214 passed / 0 skipped; all `_spawn_app` caller files plus `test_app_fixture.py` 138 passed. Unit guards (`test_schema_template`, `test_run_tests_lanes`, `test_nav_helper`) green; `ruff check` and `ruff format --check` clean.
- **AC5 (chats, `--durations-min=0.05`, same flags and `agg.py`):**

  | | 2026-10-08 baseline | leg 2 run 1 | leg 2 run 2 |
  |---|---|---|---|
  | summed setup phases >=0.05 s | 132 s | 138 s | 127 s |
  | pytest time | 261 s | 280 s | 265 s |
  | script wall | 272 s | 297 s | 281 s |

  The lane-level change is inside run-to-run noise (setup 127-138 s against 132 s). A direct A/B of `_spawn_app` to server-ready (3 alternating pairs, otherwise idle host): unseeded 1.39 / 1.28 / 1.23 s, seeded 1.08 / 1.16 / 1.01 s, so about 0.2 s saved per start (mean 1.30 to 1.08 s). That is about half the 0.4 s the plan expected; over about 936 starts it projects to about 3 minutes sequential, not 5-6.

### Leg 3: browser-quick-wins (landed)

- **AC1 (one-server redirect table).** `test_router_core.py::test_redirect_row_on_boot` (35 params) is now `test_redirect_rows_on_boot`: one `app_clean` server, a fresh `page.context.new_page()` per row (init script added per page, closed in `finally`), all four old assertions kept per row, plus `.content-panel.active[data-destination]` equals the route's first segment. Failures are collected and asserted once, listing every `(legacy, route)` with what was seen. The fixture page's first `goto` lands the session cookie in the shared context (see Anomalies); the per-row pages reuse it.
  - **Falsification:** changed `("#studio/knowledge", "library/knowledge")` to expect `library/mcp`; the test failed with "redirect rows failed:" and a line naming that `(legacy, route)` pair and the observed first-write url; reverted (file restored from a copy; diff shows only the intended change).
- **AC2 (five candidates).**
  - `test_flow_admin_navigation.py::test_admin_redirect_root_to_appearance`: **deleted**. Appearance title after a legacy `#admin` load and route `settings/appearance` are pinned by `test_flow_admin_settings_nav.py::test_legacy_general_hashes_redirect_directly` (loop item `admin`: title "Appearance", `expect_route`, `_assert_never_general`, first write is the replaceState to Appearance); the table row `("#admin", "settings/appearance")` pins replaceState/seq/no-push/history length and `data-destination == settings`.
  - `test_flow_admin_navigation.py::test_admin_legacy_system_redirects_to_appearance`: **deleted**; same coverage as above through loop item `admin/system` and table rows `#admin/system`, `#admin/system/x`.
  - `test_flow_hash_routing.py::test_studio_root_redirects_to_agents`: **deleted**. "Agents panel visible" is pinned by the table's `data-destination == agents` check on row `("#studio", "agents")` (the active destination panel is the agents panel); "route is `agents`" by that row's first replaceState to `#agents`. (`test_nav_guard.py::test_legacy_hash_link_in_content_redirects_and_is_guarded` untouched.)
  - `test_flow_admin_settings_nav.py::test_settings_general_redirects_on_a_cold_load` (3 params): **collapsed** to one test looping the 3 routes on one server, fresh page each; all assertions (title, route, replaceState-first, no push, nav selected, `_assert_never_general`) kept per route.
  - `test_flow_admin_settings_nav.py::test_legacy_general_hashes_redirect_directly` (3 params): **collapsed** the same way; the typed-legacy-hash-after-boot rewrite is kept per legacy form.
- **AC3.** `LEGACY_URL_TESTS` and the `_nav.py` docstring list lose the three deleted tests (7 remain). `tests/test_nav_helper.py::test_legacy_url_tests_are_well_formed` had a sanity floor of `>= 8`; lowered to `>= 7` (see Deviations).
- **AC4.** `_wait_for_ready` sleeps 0.03 s (conftest line 159); timeout and early-exit unchanged.
- **AC5 (stale skips).** `test_advanced_section_visible_with_disabled_inputs` deleted (no `data-testid="advanced-collapsible"` anywhere in `static/`; only the unrelated self-configuration history `<details>` class remains). `test_capability_flags_render_for_announced_capabilities` rewritten with `app_with_data_dir`: the source is created through the API (which drops an operator `_cache`), then its `_cache` (server info plus capabilities) is written into the source row with `sqlite3`, the way `/test/connect` persists it; the editor's Server section shows `.mcp-capability-flags` with only the announced keys. `test_picker_preserves_value_across_type_switch_as_custom` rewritten: the old contract does not hold in the current UI, so squawk **0156** was logged (see below). No "deferred"/"Flight 6" skip reasons remain in `tests/browser/`.
- **Squawk 0156** (open, routine): the agent editor's provider-change handler sets `selectedIndex = 0` before `fetchModelsForProvider` reads the current value, so a model chosen under one provider is silently dropped on a switch (Model value becomes empty) instead of carried over as a "(custom)" option; the "(custom)" fallback only fires for a saved value. The rewritten test asserts what is pinnable (Ollama's list replaces OpenRouter's; the old id is never offered as a real Ollama model, and if carried it is labelled "(custom)"; switching back lists it as a real model with no "(custom)"), and its docstring names the squawk.
- **AC6.** CLAUDE.md "Expected unit skip count" gains the `THE_ONE_TEST_NETNS=1` sentence (12 even on a quiet host, root-only permission tests skip under uid 0).
- **Checks.** Targeted run (router_core, admin_navigation, admin_settings_nav, hash_routing, nav_guard): 97 passed. Picker/MCP-button/agent-tabs files: 26 passed, no skip lines. Unit tier (`test_nav_helper`, `test_run_tests_lanes`, `test_schema_template`): 85 passed. `ruff check tests/` and `ruff format --check tests/` clean.
- **AC7 (full sequential re-measure; same flags as the 2026-10-08 baseline, `THE_ONE_TEST_NETNS=1`, `TEST_TIMEOUT=3600`, `THE_ONE_REQUIRE_WEBKIT=1` for contracts; all six lanes rc=0, zero failures):**

  | lane | baseline pass/skip | now pass/skip | arithmetic | wall base -> now (s) | setup base -> now (s) |
  |---|---|---|---|---|---|
  | chats | 168/0 | 168/0 | no change | 272 -> 253 | 132 -> 110 |
  | agents | 153/2 | 155/0 | -1 deleted (agent_tabs advanced); +1 openrouter picker skip->pass; +1 `test_loadall_rejects_on_tools_json_500` (already in HEAD, not this leg; see Anomalies) | 370 -> 333 | 178 -> 149 |
  | library | 153/1 | 154/0 | +1 MCP capability-flags skip->pass | 522 -> 483 | 173 -> 140 |
  | settings | 214/0 | 208/0 | -2 deleted admin_navigation; -2 and -2 from collapsing two 3-param tests to one each | 411 -> 364 | 227 -> 177 |
  | contracts | 672/3 | 672/3 | no change | 184 -> 186 | 60 -> 61 |
  | shared | 465/0 | 431/0 | -34 (35 redirect params -> 1 test); -1 deleted `test_studio_root_redirects_to_agents`; +1 `test_seeded_server_does_not_replay_migrations` (leg 2) | 729 -> 611 | 365 -> 264 |
  | **total** | 1825/6 | 1788/3 | skips drop by exactly the 3 stale tests | **2488 -> 2230 (-258 s, -10.4%)** | **1135 -> 901 (-234 s)** |

  Setup sums are the `agg.py` phase sums (>= 0.05 s). The 258 s total is the combined leg 2 + leg 3 saving against the baseline; the two are not separable from this one run (leg 2's per-start saving was measured at about 0.2 s, leg 3 removed 34 + 5 server starts and shortened the ready poll), so the figure is below the flight's 5-6 minute leg-2-plus-leg-3 projection from the report.

### Leg 4: local-lane-parallelism (landed)

- **Rebalance (AC1).** `routing` (`test_router_*`, `test_nav_guard*`, `test_store*`; 8 files) taken out of `shared`, and `library` split into `library` (knowledge inventory, connector editor, library focus, MCP navigation, MCP test button) and `mcp` (MCP editor, Library list). `contracts` untouched. Sequential estimates from leg 3's per-file junit times (wall = junit x ~1.06): routing ~405 s, settings 364, agents 333, mcp ~260, chats 253, library ~230, shared ~210, contracts 186 (total ~2240). Longest lane is under 450 s sequential. `LANES` in `tests/test_run_tests_lanes.py` now lists eight.
- **`scripts/run-tests.sh`.** `--parallel N`, `--plan`, `--help`; lane resolution factored into `resolve_lane`; budget table `BUDGET` (printed by `--help`). Parallel children are `setsid bash "$0" --lane <lane> -p no:cacheprovider <args> --junitxml=<dir>/<lane>.xml`, stale `.xml/.log/.pgids` removed before launch, lane pids refilled with `wait -n -p` (fallback `ps`-poll loop below bash 5.1). Parent traps: USR1 exit 137, INT 130, TERM 143, EXIT runs TERM-first cleanup (TERM live children, wait up to 5 s, KILL child groups and every pgid in `.pgids`). Parent watchdog and child watchdog are `sleep 1` loops (parent-gone check; child also checks `RUN_TESTS_PARENT_PID` and writes `<lane>.pgids.parent-died`). Exit code: 137 if any lane was 137/143, else the first failing lane's code in schedule order; a lane with rc 0 and a missing or empty XML fails.
- **Unit tests** (`tests/test_run_tests_lanes.py`, 10 -> 14 tests): exits-2 cases, `--plan` lists each canonical lane once with a numeric, descending budget, `--help` lists lanes and policy, and a fake-`PYTHON` end-to-end run that pins that children never get `--parallel`/`--plan`/`--lane`, args pass through, and the exit-code rules (rc 1, 137, missing XML).
- **Makefile.** `test-browser` is `run-tests.sh --parallel 3 --tb=short`; new `gate` (`test-unit` then `test-browser`); `test` help text corrected. CLAUDE.md: lane list, budget table, host policy, canonical commands.
- **AC3 manual checks** (`THE_ONE_TEST_NETNS=1`, `--parallel 3`, parent launched with default SIGINT disposition, processes identified by the `.pgids` files, the children's pids and the watchdog's cmdline, 21 live processes in those sessions/groups before each action):
  - (a) SIGINT to the parent at ~60 s: parent exit 130 (`parallel run aborted (exit 130) after 69s`), 0 processes left in any recorded group or session 10 s later, no `.pgids` file remained.
  - (b) SIGKILL to the parent at ~60 s: 0 processes left 10 s later (the children's watchdogs logged "parent process gone — killed process group"), the parent's own watchdog gone, no `.pgids` file remained; the three `.pgids.parent-died` markers stay in the lane directory by design.
  - (c) `TEST_TIMEOUT=90`: parent gone at ~95 s with `PARALLEL_RESULT rc=137`, 0 processes left, no `.pgids`.
- **AC6 (pass set vs leg 3's sequential run, `(classname, name, outcome)`):** reference 1791 entries (1788 passed, 3 skipped); run 1 and run 2 both 1791 (1788 / 3) with no entry only in either side: EQUAL twice. No flake in either run, so the divert condition did not trigger.
- **AC7 gate** (`THE_ONE_TEST_NETNS=1`, `THE_ONE_REQUIRE_WEBKIT=1`, `TEST_TIMEOUT=3600`; unit via `make test-unit`, browser via `make test-browser`, one after the other, quiet host):

  | step | wall |
  |---|---|
  | unit (5621 passed, 12 skipped) | 188 s (pytest 176 s) |
  | browser `--parallel 3`, run 1 | 913 s (runner total 912 s) |
  | **gate total (run 1)** | **1101 s = 18.4 min, target of 20 min met** |
  | browser `--parallel 3`, run 2 (AC6 only) | 881 s |
  | 2026-10-08 baseline | 697 s unit + 2488 s browser = ~53 min |

  | lane | files | sequential (leg 3 basis) | parallel wall run 1 | run 2 | budget (measured run 1 + 25%, up to 30 s) |
  |---|---|---|---|---|---|
  | routing | 8 | ~405 | 479 | 448 | 600 |
  | settings | 18 | 364 | 430 | 401 | 540 |
  | agents | 21 | 333 | 394 | 370 | 510 |
  | chats | 20 | 253 | 271 | 267 | 360 |
  | mcp | 2 | ~260 | 279 | 279 | 360 |
  | library | 5 | ~230 | 233 | 233 | 300 |
  | shared | 20 | ~210 | 222 | 219 | 300 |
  | contracts | 16 | 186 | 203 | 200 | 270 |

  No lane was over its provisional budget in either run. Lanes slow by roughly 6-20% under three-way concurrency; the three starting lanes (routing, settings, agents) are the long pole, so the schedule ends with the short lanes filling in (contracts started at +709 s).
- Squawks: none logged.

### Leg 5: ci-split-and-locked-installs (landed, narrowed scope)

- **Outcome.** The three-task browser split was NOT shipped. CI has ONE browser task running `scripts/run-tests.sh --parallel 1 --tb=short --timeout=300` (every canonical lane in sequence; `TEST_TIMEOUT=5400`, `PYTHON=.venv/bin/python`, chromium + webkit, `THE_ONE_REQUIRE_WEBKIT=1`). No lane list lives in CI. Its CI time is **unmeasured** until the first post-merge build. See Decisions and Deviations.
- **AC3 divert, resolved by operator decision.** Any `container_limits` (memory alone, cpu alone, both) fails at container creation on BOTH linux workers: `runc create failed: unable to apply cgroup configuration: cannot enter cgroupv2 "/sys/fs/cgroup/garden" with domain controllers -- it is in threaded mode` (busybox probes, builds 689513, 689515, 689516, and `browser.yml`). Operator dropped limits; a unit pin fails if any `ci/tasks/*.yml` adds them. Observed cgroup values inside a task (no limits): `cpu.max max 100000`, `cpu.weight 100`, no `memory.max`.
- **Image.** `ghcr.io/astral-sh/uv:0.10.0-python3.11-bookworm` does not exist; pinned `0.9.30-python3.11-bookworm` (host uv 0.10.0).
- **Locked installs (AC4).** `test`, `lint`, `bwrap`, `browser` use `uv sync --locked` (`--extra all-llms --extra dev`; lint `--extra dev`), `uv-cache` task cache, `UV_LINK_MODE=copy`, `UV_NO_PROGRESS=1`; the browser task also caches `playwright-browsers`. `bwrap` builds its venv inside `/opt/the-one`. `windows-tests` stays on pip (not validated on the Windows worker; see Deviations).
- **Stale lock (AC4).** Raising `httpx>=0.27` to `>=0.28.0` in a scratch `pyproject.toml` without relocking: `uv sync --locked` exits 1: "The lockfile at `uv.lock` needs to be updated, but `--locked` was provided. To update the lockfile, run `uv lock`." `uv sync --frozen` on the same copy exits 0 and installs silently.
- **`fly execute` results (AC6, cold caches, one at a time):**

  | Task | Result | Install step | Wall |
  |---|---|---|---|
  | `lint` | passed | 26 s | 2m56s (image pull included) |
  | `bwrap` (`-p`) | 41 passed, 3 skipped (expected) | 38 s | 1m17s |
  | `test` | 5620 passed, 1 failed, 12 skipped | 37 s | 6m31s |
  | `browser` | NOT RUN to completion (see below) | 31-35 s | n/a |

  Browser trial findings, all folded into `browser.yml`: (1) the cache volume is mounted `noexec`, so a Chromium spawned from the Playwright cache fails with EACCES (every browser test errored in a 4.5-minute run); the task now copies the cache to `/opt/pw` to run. (2) `apt` over IPv6 failed with "Network is unreachable" (build 689665, 7m39s); the task forces IPv4. (3) A later `fly execute` upload timed out (500 on the volume stream-in). (4) The final three-task trial exhausted host memory (Shmem about 12.6 GB in Docker Desktop's VM, load about 140) and Concourse went down; no browser lane completed in CI, and the copy-to-`/opt/pw` and IPv4 changes are therefore untested end to end.
- **Pipeline (AC5).** `repo` resource `ignore_paths`: `missions/** sorties/** squawks/** maintenance/** service-reports/** .flightops/**`; `docs/` and `*.md` still trigger. `fly validate-pipeline` passed for the three-task version; the final single-task pipeline was only YAML-parsed (no `fly` after Concourse went down).
- **Unit pins** (`tests/test_run_tests_lanes.py`, 13 tests pass; ruff clean): the pipeline has exactly one browser step, whose script runs `run-tests.sh --parallel 1`, names no lane and no `--lane`, installs chromium+webkit and sets `THE_ONE_REQUIRE_WEBKIT=1`; no `ci/tasks/*.yml` has `container_limits`; four tasks use `uv sync --locked` with no `pip install`.
- **AC7.** `pr-lint.yml`: weekly cron (Mondays 06:17 UTC) and `workflow_dispatch`; `lint` PR-only; `pip-audit` on all three triggers. `windows-installer.yml`: `pip-audit` job, build `needs:` it. `actionlint` not installed (YAML parses). Squawk 0107 completed.
- **Docs (AC8).** `ci/README.md` and `ci/tasks/browser.yml` header updated (one browser row, locked installs and caches, `ignore_paths`, concurrency policy and the memory finding, measured times, browser time unmeasured).

#### Post-merge operator checklist (AC8)

1. Run `ci/set-pipeline.sh`.
2. First pipeline build: confirm the `browser` task is green, WebKit launches (no WebKit skips, `THE_ONE_REQUIRE_WEBKIT=1`), and record its wall time (the long pole) and install-step time. Watch host memory during this build.
3. Watch whether `test_self_configuration_surface.py::TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain` fails again in the `test` task (it failed once under CI load, passed alone, and has not failed locally).
4. Run a second build and record the cached install times (the first fills the caches); confirm the Playwright cache copy to `/opt/pw` works on a cache hit.
5. Push a flight-artifact-only commit and confirm no build triggers.
6. Trigger the `pr-lint` workflow once through `workflow_dispatch`; confirm `pip-audit` runs and `lint` is skipped.
7. Follow-up (separate): validate a uv install on the Windows worker; fix the workers' cgroup layout so `container_limits` can be used.

## Flight review fixes

- `scripts/run-tests.sh`: TEST_TIMEOUT default is now per mode (1200 s single, 2400 s `--parallel`), set after argument parsing and exported; an explicit caller value wins. `--plan` prints the effective value; pinned by `test_parallel_default_timeout_is_2400_and_caller_value_wins`.
- `ci/tasks/browser.yml`: lane logs go to `$PWD/lane-logs`; on a non-zero exit the logs of the lanes named in `PARALLEL_RESULT failed=` are printed, then the original code is returned.
- `tests/_schema_template.py`: `mem` is closed if `backup` raises. Squawk 0107 sign-off updated.

## Anomalies (leg 5)

- **Unresolved:** `tests/test_self_configuration_surface.py::TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain` failed once in the CI `test` task (`MCPConnectionError: MCP server did not respond within 30 seconds during initialize`, 5620 passed / 1 failed). The same file alone in the same container passed (11 passed) and the test passes in local `make test-unit`. Seen once in CI, never locally; the first post-merge build is the next data point (checklist item 3).
- A `fly execute` upload to a worker failed once with a 500 (`stream-in ... timeout awaiting response headers`) before the memory exhaustion.

## Anomalies (leg 2)

- The measured per-start saving (about 0.2 s) is lower than the report's 0.37-0.59 s `init_db` estimate, and a single chats lane (about 60 starts) cannot resolve it from noise. The full sequential re-measure at the end of leg 3 is the real test.


## Anomalies (leg 3)

- **Fresh pages in the fixture context are unauthenticated until the fixture page's first `goto`.** The `page` fixture wraps `goto` to land the session cookie lazily; a `context.new_page()` taken first has neither the cookie nor the wrapped `goto`. My first version of the table test therefore ran 35 rows each waiting out the default wait, and the run only looked hung. Fixed by booting the fixture page once (`_boot(page, app_clean)` / `page.goto(app_clean)`) before the loop, which is now commented in the tests.
- **A pytest `--timeout` did not interrupt that hang** (Playwright's sync API blocks the signal-based timeout); the lane's `TEST_TIMEOUT` group kill did.
- **Agents lane has +1 test not caused by this leg:** `test_flow_studio_loadall_error.py::test_loadall_rejects_on_tools_json_500` is in HEAD (commit 5ddf8fb) but absent from the baseline run; arithmetic above accounts for it.
- The squawk 0156 defect: see the Leg 3 entry.

## Anomalies (leg 4)

- Bash starts background (`&`) jobs with SIGINT ignored, and an ignored-on-entry signal cannot be trapped, so the AC3(a) interrupt check only reflects a real Ctrl-C when the parent starts with the default SIGINT disposition (the check launched it from Python with `SIGINT` reset). A parent started as a shell background job ignores SIGINT; it still handles TERM and the timeout.
- A crashed or parent-killed lane leaves `<lane>.pgids.parent-died` (a marker) in the lane directory; only `.pgids` files are removed by a lane's own cleanup.
- `shellcheck` is not installed on the host; `bash -n` passed.


---

## Decisions

- **CI browser concurrency: 1 task, not 3 (operator, 2026-10-08).** This changes the flight's "Host concurrency policy" for CI. Local stays at 3 lanes.
  - **What happened.** During leg 5's one-at-a-time `fly execute` trials, the host ran out of memory: about 0 GB of 15 GB available, Shmem 12.6 GB held in Docker Desktop's VM, IO pressure 97%, load average about 140.
  - **Recovery.** The operator killed Docker Desktop, after which Shmem fell to 32 MB.
  - **Decision.** With `container_limits` unavailable on the workers (see Deviations), the operator judged 3 concurrent CI browser tasks too many. CI runs a single browser task: every lane in sequence through `scripts/run-tests.sh --parallel 1`, so CI still uses the local lane definitions and the runner's exit-code rules. Long pole about 40 min, as before.
  - **What leg 5 keeps:** locked installs and the flight-artifact `ignore_paths` filter.
  - **Where the memory went is not settled.** The Shmem build-up happened with only one build at a time running, so worker storage held in memory (build volumes and images retained between builds) is a likely contributor regardless of concurrency. Relayed to the operator as a `concourse-local` follow-up.
  - **No further browser `fly execute` trials in this flight.** The browser task is verified at the operator's first post-merge pipeline build.

- **Legs 5 and 6 merged into one leg, `05-ci-split-and-locked-installs` (Flight Director, 2026-10-08).**
  - Both rewrite the same `ci/tasks/*.yml` install and run blocks.
  - Both are verified by the same `fly execute` task runs, about 10 min per browser task, which two legs would pay for twice.
  - Neither has a mid-leg human decision: caches over a baked image is already decided.
  - Leg 7 (`module-scoped-server`, conditional) becomes leg 06 if it flies.
  - Also changed since the flight plan: Concourse is reachable from an agent shell (`fly` 8.1.0, target `the-one`), so CI tasks are verified by `fly execute` inside the leg. Only `set-pipeline`, the green build on `main` and the doc-only check remain post-merge operator steps.

- **Leg 4 verification swap (Flight Director, 2026-10-08).** The flight spec planned a behavior test, `parallel-lanes-stay-green`. It is replaced by a scripted junit pass-set comparison across two concurrent runs against the sequential run (leg 4 AC6). The property is fully decidable from junit output and needs no observation of a live UI, so an Executor/Validator pair would add cost without adding evidence. The leg 4 design review concurred.

---

## Deviations

- **Leg 5 (operator decisions):** `container_limits` dropped (workers reject them: cgroup v2 threaded mode); ONE browser task running `run-tests.sh --parallel 1` instead of three parametrized tasks (the three-task trial exhausted host memory); `windows-tests` left on pip because a uv install was never validated on the Windows worker (follow-up: validate `pip install uv==0.9.30` + `uv sync --locked` there); browser-task CI time unmeasured; Playwright cache is noexec so the task runs browsers from a copy under `/opt/pw` (untested on a cache hit).

- **Leg 5 AC3 divert, operator disposition: drop `container_limits` (2026-10-08).**
  - **What happened.** The local Concourse Linux workers reject any `container_limits` at container creation: `runc create failed: ... cannot enter cgroupv2 "/sys/fs/cgroup/garden" with domain controllers -- it is in threaded mode`. It was reproduced with busybox probes (memory alone, cpu alone, both) on both workers.
  - **Decision.** The operator chose to drop the limits. Host protection now rests on the cap of 3 browser tasks plus the "local gate and CI never at the same time" policy.
  - **What is unchanged.** The leg artifact is not rewritten (legs are immutable in flight). AC3 is recorded as unmet with this accepted deviation. The leg's other criteria stand.
  - **Follow-up for `concourse-local`, outside this repo.** The workers' cgroup v2 `garden` group is in threaded mode. Fixing it would let a later change restore per-task memory caps. This is relayed to the operator at flight landing.

- **Leg 3 touched `tests/test_nav_helper.py`** (not in the leg's Files Affected): `test_legacy_url_tests_are_well_formed` asserted `len(LEGACY_URL_TESTS) >= 8`, and the leg's own deletions leave 7. The floor is a sanity check, not a pinned set, so it was lowered to 7.
- The `test_mcp_test_connection_button` rewrite seeds `_cache` by `sqlite3` into the source row rather than purely "through the API", because the API deliberately drops an operator-supplied `_cache` (`api.py` update/create paths); this matches how other browser tests seed rows (`app_with_data_dir`).

---

## Anomalies

---

### Flight Director Notes

- **2026-10-08: flight start.**
  - Crew file `.flightops/agent-crews/leg-execution.md` loaded and valid.
  - Branch `flight/01-test-suite-runtime` cut from `main` at `16e91d7`.
  - Mission moved `planning` → `active`; flight moved `ready` → `in-flight`.
  - Prerequisite check:
    - squawk 0136 is completed (#240);
    - Concourse is reachable by the operator, which matters only from leg 5 on.
- **Leg 1 `unit-template-db`, tiered HIGH.**
  - It changes shared test infrastructure used by about 50 unit files.
  - It introduces a cache: the schema template.
    - Source of truth: `ensure_schema`.
    - Rebuild trigger: one build per pytest process.
    - Staleness: none within a session; the AC3 guard proves equivalence.
  - Its divert condition, hidden per-database state, would show up only as a test outcome change.
  - A Developer design review comes before implementation.
- **Leg 1 design review (Developer, Sonnet): "approve with changes"**, no high-severity issues. All points were applied:
  - The AC6 guard is now an `ast.Call` walk. A regex would flag `_fake_init_db` and docstrings.
  - The allow-list is scoped to about 10 entries.
  - AC3 compares the FTS5 shadow tables and `sqlite_sequence` as ordinary tables.
  - The build connection closes inside its own thread loop.
  - `connect_template_memory()` is offered as an option.
  - `test_provider_api.py`'s second fixture, `plan_env`, is named.
  - A step 3a projection checkpoint was added, with a named fallback: session-wide `synchronous=OFF`. The reviewer measured one replay at 0.446 s, 0.052 s with `synchronous=OFF`, against about 1 ms for a copy.
  - The leg states what happens if the target is still missed: record it and land, and the miss feeds leg 7's conditional trigger.
- **No second design-review cycle.** The changes clarify and constrain; none changes the design.
- Leg 1 → `ready`.
- **Leg 1 landed (Developer, Sonnet).**
  - The unit lane takes 201.67 s (about 221 s wall), against the 697 s baseline and the ≤300 s target.
  - FD check of the pass-count drift: `--collect-only` with the unit marker set gives 5620 on `main` and 5628 on the branch, a difference of exactly the 8 new guard tests. So 5616 passed + 12 skipped = 5628 is consistent.
- **Leg 2 `browser-template-db`, tiered LOW.**
  - It is one additive change in `_spawn_app` that reuses leg 1's guarded helper.
  - It has an opt-out keyword for empty-directory tests.
  - No interface consumed outside the test tree changes.
  - No design review; the flight-end Reviewer covers it.
- **Leg 2 landed (Developer, Sonnet).**
  - The per-start A/B shows about 0.2 s saved, against the 0.4 s expected. That projects to about 3 min across about 936 starts.
  - The chats-lane change is within noise.
  - AC5 required a measurement, not a threshold, so the leg stands.
  - The remaining server boot is about 1.0–1.15 s of import and lifespan. Only leg 7 (module-scoped server) addresses that. Whether leg 7 flies is decided after leg 4's measured gate.
- **Leg 3 `browser-quick-wins`, tiered LOW.**
  - It is test-only work within established patterns.
  - Coverage risk from the deletions is contained by AC2's per-assertion pin rule and the flight-end Reviewer.
  - Design-time check: 3 of the 5 "duplicates" assert more than the redirect. The leg encodes this, and expects two of them to be collapsed rather than deleted.
  - No design review.
- **Leg 4 `local-lane-parallelism`, tiered HIGH.**
  - It changes shared tooling that every leg and operator uses.
  - It changes process-lifecycle and kill semantics, the orphan-Chromium class of defect `run-tests.sh` exists to prevent.
  - The design review ran read-only, with no test runs, because leg 3's timed measurement was in progress.
- **Leg 4 design review 1 (Developer, Sonnet): "approve with changes"**, with two high-severity issues.
  - **Issue 1:** SIGKILLing a child group skips the child's EXIT trap and orphans its pytest group. The fix is TERM-first cleanup, published `.pgids`, and a parent watchdog that signals rather than kills.
  - **Issue 2:** a bare `wait -n` can return on the watchdog job and abort under `set -e`. The fix is `wait -n -p` over the lane pids only, with an `rc=$?` capture and a fallback for bash older than 5.1.
  - **Also applied:**
    - a parent-death guard for a SIGKILLed parent;
    - `make gate` as a new target, leaving `make test` unchanged (it is the unit tier under `addopts`);
    - gate run = AC6 run 1, with budgets filled in as a data edit pinned by the `--plan` test;
    - argument-parsing rules;
    - `-p no:cacheprovider` for the children;
    - a missing or empty lane XML counts as failure;
    - a machine-readable `PARALLEL_RESULT` line.
  - **Reviewer's judgement on the behavior-test swap:** replacing it with a scripted junit comparison is sound, provided skips compare as skips.
  - A second review pass follows, because AC3 changed substantively.
- **Leg 4 design review 2 (Developer, Sonnet): "approve with changes".** The two high-severity issues:
  1. The parent's own watchdog `sleep` survives a SIGKILLed parent.
  2. Implementation step 2 still described the pre-review mechanism: bare `wait -n`, group-KILL, and the "existing watchdog pattern". That was an FD editing miss.
- **Also applied:**
  - USR1 as the timeout signal, so the exit code is 137;
  - handling for an empty `wait -p` variable;
  - `.pgids` written in two atomic appends and deleted on a clean exit;
  - stale lane files removed before launch;
  - a guard marker, so a parent-death kill is not reported as a timeout;
  - 137/143 labelled "timeout or killed".
- **No third review.** Both highs had exact prescriptions from the reviewer and were applied verbatim, and AC3's three manual checks (SIGINT, SIGKILL, timeout) verify the result empirically. Leg 4 → `ready`.
- **Leg 4 is held until leg 3 lands.** It needs leg 3's per-lane timings and sequential junit files, and it must not load the host during leg 3's measurement.
- **Leg 3 landed (Developer, Sonnet).**
  - Sequential browser total: 2230 s against 2488 s (−258 s, legs 2+3 combined). All six lanes passed. The skip count dropped by exactly the 3 stale tests.
  - Squawk 0156 was logged (the model picker drops its value on a provider switch), deferred, and stays outside this flight's scope.
  - The Developer used `pkill -f` once against its own hung run, against the spawn instructions.
    - The FD found no stray `pytest`, `uvicorn` or Chromium process after landing.
    - This is the second occurrence this cycle.
    - The cause it reported (`pytest --timeout` not interrupting a Playwright wait) is part of what leg 4's runner hardening addresses.
- **Leg 4 projection before start.**
  - 2230 s across 3 slots is at least 743 s ideal, before contention. Add about 221 s of unit, and the gate comes to about 16–20 min.
  - It is borderline for the ≤20 min target. The rebalance has to keep the longest lane well under 743 s × contention.
  - If AC7 misses, leg 7 flies.
- **Leg 5 `ci-split-and-locked-installs`, tiered HIGH.**
  - It changes CI triggers, the release audit, and every CI task's install path.
  - Design review 1 (Developer, Sonnet, read-only): "approve with changes", with three high-severity issues:
    1. lint's install flag (dev deps are an optional-dependency extra, not a dependency group);
    2. the leg depends on leg 4's `--plan`, which had not landed;
    3. the interpreter was unspecified (`PYTHON=.venv/bin/python`).
  - **Also applied:**
    - `TEST_TIMEOUT=3600` and a `set +e` chaining recipe;
    - `--locked` instead of `--frozen`, because `--frozen` silently ignores a stale lock, which inverted the planned demonstration;
    - a per-name cache note;
    - more memory for the contracts task;
    - the lint job gated to `pull_request` once a schedule is added;
    - the tag-time audit as a `needs:` job;
    - a second post-merge build to measure cache hits.
  - **Scope change to `ignore_paths`:** narrowed to the flight-artifact directories only. Unit tests read `docs/*.md` and repo Markdown, so ignoring `docs/` or `*.md` could let a doc-only change break CI silently. The FD grep confirmed no test reads a flight-artifact directory.
  - **No second review.** The fixes are the reviewer's own prescriptions, and none changes the design. Leg 5 → `ready`.
  - Blocked on two things: leg 4 landing, and an operator `fly -t the-one login`, because the token expired before the review.
- **Operator re-logged in to `fly` target `the-one`.**
  - `fly -t the-one workers` lists 2 Linux workers and `windows-worker`, all running.
  - The Linux workers share this host, so the "never during a local test run" rule for `fly execute` stands.
  - Leg 5 now waits only on leg 4.
- **Leg 4 landed (Developer, Sonnet).**
  - Gate: unit 188 s, browser `--parallel 3` 913 s, total **1101 s (18.4 min)**, against the ~53 min baseline and the ≤20 min target.
  - AC6: two parallel runs both match leg 3's sequential pass set exactly (1791 entries).
  - AC3: the SIGINT, SIGKILL and timeout checks each left 0 processes.
  - The FD confirmed no stray `pytest`, `uvicorn` or Chromium process after landing.
- **Leg 7 (`module-scoped-server`, conditional) is NOT flown.**
  - Its trigger was "the local gate still over 20 min, or a lane over its budget". The gate measured 18.4 min, and every lane was within its budget in run 1.
  - Margin to the target is about 1.6 min. The next debrief should compare against the budget table, not only flight-to-flight, and fly leg 7's design as a future sortie if the gate crosses 20 min.
- **Leg 5 started.** Leg 4 has landed, and the operator re-logged in to `fly`.
- **Leg 5 landed (Developer, Sonnet), on the narrowed scope.**
  - One browser task running `--parallel 1`, locked installs, flight-artifact `ignore_paths`, a weekly and tag-time pip-audit, squawk 0107 completed.
  - `windows-tests` was reverted to pip (deviation).
  - The browser task has never completed under CI. It is verified at the first post-merge pipeline build (operator checklist).
- **All autonomous legs landed (1–5; leg 7 not needed).** Flight review is next.
  - Reviewer tier: **Sonnet**. The diff touches the CI pipeline and the release audit gate, a supply-chain surface, as well as `run-tests.sh`'s process-kill lifecycle. That is beyond the crew file's Haiku default for non-security diffs.
- **Flight review (Reviewer, Sonnet): `[HANDOFF:confirmed]`.**
  - `make test-unit`: 5626 passed, 10 skipped (no netns).
  - Targeted browser files: 69 passed.
  - Lint is clean.
  - Two should-fix items: the parallel `TEST_TIMEOUT` default was dead code (the 1200 s global ran first), and the CI browser task lost failed-lane logs. Plus two nits.
  - All four were fixed by a Developer and confirmed by a Sonnet re-review, which exercised the CI failure-dump block against a stub.
  - Review cycles: 1 review plus 1 scoped re-review.
- **Legs 1–5 → `completed`.** Leg 7 was not flown.
- **Flight landed (2026-10-08).**
  - Code commit `fd14a86`; PR #247.
  - Documentation check: the flight-end Reviewer confirmed CLAUDE.md (lanes, budgets, `make gate`, policy, netns skip note) and `ci/README.md` against the code.
  - Flight → `landed`, checked off in the mission.
  - **Carried to the debrief:**
    - the post-merge operator checklist (Leg 5);
    - the unresolved one-off CI failure of `test_live_surface_connection_evicted_before_general_drain`;
    - follow-ups for `concourse-local`: the cgroup v2 threaded `garden` group that blocks `container_limits`, and worker storage memory (Shmem build-up during `fly execute` trials);
    - validating a uv install on `windows-worker`;
    - squawk 0156;
    - the 1.6 min margin under the 20 min gate.
