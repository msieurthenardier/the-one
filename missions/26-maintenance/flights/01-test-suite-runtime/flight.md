# Flight: Test-suite runtime

**Status**: ready
**Mission**: [Post-Mission-25 Maintenance](../../mission.md)

## Contributing to Criteria
- [ ] Unit-tier fixtures use a session template database. The unit lane takes 300 s or less. *(#1)*
- [ ] Browser-test servers start from a pre-seeded template, with no migration replay at boot. *(#2)*
- [ ] Redirect table collapsed, duplicates removed, ready-poll tightened, no long-skipped "deferred" browser tests. *(#6, #7)*
- [ ] Local browser lanes run 3 at a time and are rebalanced. The full local gate takes 20 minutes or less. *(#3 local)*
- [ ] CI runs browser work as 3 limited tasks, installs WebKit only for contracts, and skips doc-only pushes. Durations are documented. *(#3 CI, #12, #13)*
- [ ] CI installs from the lockfile. pip-audit runs on a schedule and at tag time. *(#11, 0107)*
- [ ] The host concurrency policy and per-lane time budgets are recorded.

---

## Pre-Flight

### Objective
Cut the verification gate from about 53 minutes to 20 minutes or less, with no loss of coverage:
- **Unit tier:** stop rebuilding the schema for every test database.
- **Browser tier:** stop rebuilding it for every browser server, and run the browser lanes in parallel within a recorded host budget.
- **CI:** do the same in CI, which must also stop reinstalling unlocked dependencies and stop running for documentation-only pushes.

### Open Questions
N/A. This is a maintenance flight. The targets (a full gate of 20 minutes or less, a unit lane of 300 s or less) and the host concurrency policy were decided by the operator in the [2026-10-08 report](../../../../maintenance/2026-10-08.md). Mechanism choices left to leg design are listed under Technical Approach.

### Design Decisions

**Gate targets**: the full local gate takes 20 minutes or less, the unit lane 300 s or less, and every lane has a recorded time budget.
- Rationale: operator decision, 2026-10-08. A budget gives later debriefs a fixed bar to compare against. Comparing only with the previous flight is what let Mission 25's 2.5× growth pass unflagged.
- Trade-off: none.

**Host concurrency policy**: locally, 3 browser lanes run concurrently. CI runs 3 browser tasks, each with `cpu`/`memory` limits. A local gate and a CI build never run at the same time. The unit suite always runs outside the concurrent browser set.
- Rationale:
  - Operator decision, 2026-10-08.
  - One lane was measured at about 1.15 GB and 3–4 cores on the 20-core / 16 GB WSL host.
  - The Concourse workers run on the same machine.
  - Flakes 0134 and 0136 are unit-tier and sensitive to load.
- Trade-off: 4 lanes would save about 2 more minutes, but this leaves headroom.

**Template database, not a reset seam**: both tiers copy one migrated database per pytest session. No per-test reset seam (R7b) and no warm-spare servers (R8).
- Rationale:
  - `ensure_schema` generates no ids, keys or credentials, so a copied template is equivalent to a fresh replay.
  - A reset seam would have to clear module globals across 10+ subsystems, and no one can prove that list complete.
  - Server boot is CPU-bound, so a warm spare only moves the cost and loses its benefit when lanes run in parallel.
- Trade-off: per-test server starts remain (about 0.8 s each after the template). Leg 7 addresses them only if a target is still missed.

### Citation Audit

Verified against the working tree at `d7ff5cd` by the 2026-10-08 inspectors:

| Citation | Status |
|---|---|
| `tests/conftest.py::isolated_db` (~306) — builds a fresh DB and calls `ensure_schema` per test, resets the `_connection` singleton via monkeypatch | verified |
| `tests/test_db_api.py::client` (~23) — per-test fresh DB + `ensure_schema` | verified |
| `the_one/db/connection.py::init_db` (~68) — runs `ensure_schema` from the stored version on startup | verified |
| `the_one/db/connection.py::_connection` (~12) — process singleton | verified |
| `tests/browser/conftest.py::_spawn_app` / `_wait_for_ready` (~205) — fresh data_dir with only the credential; readiness polled at 0.1 s; teardown ceiling 10 s | verified |
| `tests/browser/test_router_core.py::test_redirect_row_on_boot` — 35 params, each on its own `app_clean` server | verified |
| `scripts/run-tests.sh` — `--lane`/`--list`, process-group kill, `THE_ONE_TEST_NETNS` wrapper | verified |
| `ci/tasks/browser.yml` — single `pytest -m browser tests/browser/`, `THE_ONE_REQUIRE_WEBKIT=1`, installs chromium+webkit | verified |
| `ci/the-one.pipeline.yml` — one `ci` job, 5 parallel tasks, `repo` resource with no `paths`/`ignore_paths`; installer gated `passed: [ci]` | verified |
| `ci/tasks/test.yml` et al. — `pip install -e ".[all-llms,dev]"` from scratch on `python:3.11` | verified |

Re-audit at leg design time; line numbers drift.

### Prerequisites
- [ ] Squawk 0136 (the kb-watcher drain-timing flake) completed, or explicitly carried. The unit suite stays outside the concurrent set in any case.
- [ ] Concourse is reachable by the operator (`fly`) for legs 5 and 6.

### Pre-Flight Checklist
- [x] All open questions resolved (N/A, maintenance flight)
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The legs follow the maintenance report's finding numbers. Baseline: the 2026-10-08 timing artifacts were taken sequentially on a quiet host with `THE_ONE_TEST_NETNS=1`. Unit took 697 s. The lanes took: chats 272 s, agents 370 s, library 522 s, settings 411 s, contracts 184 s, shared 729 s. **Every leg that changes timing ends with a re-measurement against that baseline, recorded in the flight log.**

**1. `unit-template-db` (#1).** This is the largest single payoff, about 450 s of the 524 s of setup. The report measured a fresh `ensure_schema` at 0.37–0.59 s, and about 56 files call it from about 235 sites.
- Build a session-scoped fixture that runs `ensure_schema` once into a `tmp_path_factory` file, written with `journal_mode=DELETE` and checkpointed so it is a single file.
- Add a `fresh_db(tmp_path)` helper that copies the template (`shutil.copyfile` or sqlite `backup()`) and connects with the same pragmas production uses.
- Swap it into `isolated_db`, `test_db_api.client` and the other per-test sites, file by file.
- Set `PRAGMA synchronous=OFF` wherever a test still replays migrations.
- Add a guard test: the template's `schema_version` equals `CURRENT_VERSION`, and every table's `table_info` matches a fresh `ensure_schema`.
- **Must not use the template:** `test_db_migration.py` and any test that seeds a partial or old-version database.
- **Optional:** class-scoped v(N-1) bases in `test_db_migration.py`. Saves about 15–20 s, and each per-version test keeps its own assertion.
- **Done when:** the unit lane takes 300 s or less with the same pass and skip counts.

**2. `browser-template-db` (#2).** Reuses leg 1's template machinery.
- `_spawn_app` copies the session's template into each `data_dir` before `Popen`, so `init_db`'s `ensure_schema` sees the current version and does nothing.
- Tests that start from a deliberately old or absent database keep their own path.
- **Expected saving:** about 0.4 s × 936 starts, roughly 5–6 min sequential.
- **Done when:** the per-start setup time is re-measured and recorded.

**3. `browser-quick-wins` (#6, #7, #8).**
- **Redirect table:** collapse `test_redirect_row_on_boot`'s 35 params into one test that loops the rows on one server. Either `page.goto` plus `_nav.expect_route` per row, or evaluate the router's resolver directly. A failure message must still name the failing row.
- **Duplicate redirect tests:** delete the 5 that the router table already pins. Update `_nav.LEGACY_URL_TESTS`, and record each removal with its covering row in the flight log.
  - `test_flow_admin_settings_nav::test_settings_general_redirects_on_a_cold_load` and `::test_legacy_general_hashes_redirect_directly`
  - `test_flow_admin_navigation::test_admin_redirect_root_to_appearance` and `::test_admin_legacy_system_redirects_to_appearance`
  - `test_flow_hash_routing::test_studio_root_redirects_to_agents`
  - Keep `test_nav_guard::test_legacy_hash_link_in_content_redirects_and_is_guarded`: it tests the guard, not the redirect.
- **Ready-poll:** in `_wait_for_ready`, poll at about 0.03 s instead of 0.1 s.
- **Stale skips:**
  - Delete `test_flow_agent_tabs.py::test_advanced_section_visible_with_disabled_inputs`; the feature is gone.
  - Rewrite `test_mcp_test_connection_button.py::test_capability_flags_render_for_announced_capabilities` against the server-info panel.
  - Rewrite `test_flow_studio_openrouter_picker.py::test_picker_preserves_value_across_type_switch_as_custom` against the current picker.
- **Docs:** amend CLAUDE.md's "Expected unit skip count" note. Under `THE_ONE_TEST_NETNS=1`, 12 skips is normal: two root-only permission tests skip because `unshare -rn` maps to uid 0. Say that this coverage is lost under netns.
- **Done when:** about 2 min is saved, and no "deferred" skips remain.

**4. `local-lane-parallelism` (#3, local).**
- **Rebalance:** move `test_router_*`, `test_nav_guard` and `test_store*`, the long pole of `shared`, into their own lane. Target: no lane over about 450 s. Add the lane to `scripts/run-tests.sh` and to the lane list in `tests/test_run_tests_lanes.py`, keeping the partition invariant.
- **Parallel runner:** add a concurrent mode to `run-tests.sh`, for example `--parallel 3` across all lanes.
  - Each lane keeps its own process group and netns wrapper, a log, and a junit file.
  - It aggregates the exit codes and prints per-lane wall times.
  - Killing it at `TEST_TIMEOUT` kills every lane's group.
  - It never includes the unit suite.
- **Trial:** run all browser lanes concurrently, and compare the pass set with a sequential run.
- **Budgets:** write each lane's time budget and the host concurrency policy into CLAUDE.md's Testing section and `scripts/run-tests.sh --help`. Make `make test-browser` use the parallel mode.
- **Done when:** the full local gate is measured at 20 minutes or less. The projection is about 13–15 min for 3 rebalanced lanes plus about 4 min of unit.

**5. `ci-lane-split` (#3 CI, #12, #13, C2).**
- **Tasks:** replace the single browser task with 3 tasks in the existing `in_parallel`. Each runs its assigned lanes through `scripts/run-tests.sh --lane`, so CI can never drift from the local lane definitions. Each task carries `cpu`/`memory` limits.
- **WebKit:** install it and set `THE_ONE_REQUIRE_WEBKIT=1` only in the task that runs `contracts`.
- **Path filters:** add `ignore_paths` to the `repo` resource for `missions/**`, `sorties/**`, `squawks/**`, `maintenance/**`, `service-reports/**`, `.flightops/**`, `docs/**` and top-level `*.md`. Check that the installer job's trigger follows.
- **Docs:** update the header of `ci/tasks/browser.yml` and the durations in `ci/README.md` with measured numbers, and record the "local gate and CI never at the same time" policy there.
- **Done when:** the operator sets the pipeline, and one green build shows the long pole at about 15 min or less.

**6. `ci-locked-deps` (#11, squawk 0107).**
- **Installs:** CI installs from `uv.lock`, not from floor pins. Leg design picks one of:
  - (a) a baked CI image with `uv sync --frozen --extra all-llms --extra dev`, the Playwright browsers and bubblewrap, rebuilt when `uv.lock` or `pyproject.toml` changes; or
  - (b) `uv sync --frozen` per task with Concourse `caches:` for the uv and `ms-playwright` directories.

  Prefer (b) if the image registry adds operational load on the shared host.
- **Audits:** pip-audit runs weekly (a Concourse `time` resource or a GitHub `schedule`) and in the tag-triggered release workflow. Complete squawk 0107 with this leg.
- **Done when:** the per-task install time is measured, and a deliberately stale lock entry can no longer change what CI tests.

**7. `module-scoped-server` (#4, R7a). CONDITIONAL.** Fly this leg only if, after legs 1–5, the measured local gate is still over 20 minutes or a lane is over its budget. Otherwise record the skip in the flight log.
- Add an opt-in `app_module` fixture: one server per test module, for read-only and navigation files.
- Add a per-test guard that fails the test if the server's state changed, for example table row counts through a dev-mode read, plus `data_dir` mtimes. "Read-only" is then enforced, not assumed.
- **Expected saving:** about 2–4 min of wall time.

### Checkpoints
- [ ] After leg 1: unit lane at 300 s or less, pass and skip counts unchanged.
- [ ] After leg 2–3: browser sequential total re-measured and recorded.
- [ ] After leg 4: full local gate at 20 minutes or less, from a concurrent trial whose pass set matches sequential.
- [ ] After leg 5–6: one green CI build with the split tasks, and a doc-only push that triggers nothing.

### Adaptation Criteria

**Divert if**:
- The template DB changes a test's outcome other than in timing. That would mean hidden per-database state. Stop and investigate before continuing.
- The concurrent trial shows a pass set that differs from sequential, or new flakes appear in more than one run. Fall back to 2 lanes, and log each flake as a squawk.
- CI resource limits cannot be expressed on the local Concourse workers.

**Acceptable variations**:
- The rebalance produces a different lane split than proposed, as long as each lane fits its budget and the partition invariant holds.
- Leg 6 picks caches over a baked image, or the reverse.
- The optional migration-test class bases in leg 1 are skipped.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `unit-template-db` - Session template DB for unit fixtures, `synchronous=OFF`, guard test (#1)
- [ ] `browser-template-db` - Pre-seed the template into `_spawn_app` data dirs (#2)
- [ ] `browser-quick-wins` - Redirect-table collapse, 5 duplicate deletions, ready-poll, stale skips, netns skip note (#6, #7, #8)
- [ ] `local-lane-parallelism` - Rebalance `shared`, 3-lane concurrent runner, budgets and policy (#3 local)
- [ ] `ci-lane-split` - 3 limited browser tasks via `--lane`, WebKit only in contracts, `ignore_paths`, measured docs (#3 CI, #12, #13)
- [ ] `ci-locked-deps` - Locked CI installs (image or caches), scheduled and tag-time pip-audit (#11, 0107)
- [ ] `module-scoped-server` *(conditional)* - Opt-in module server with unchanged-state guard (#4 R7a)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed (leg 7 flown or recorded as skipped)
- [ ] Code merged
- [ ] Tests passing: same pass set as the 2026-10-08 baseline, minus the named removals
- [ ] Documentation updated (CLAUDE.md Testing, `ci/README.md`, `run-tests.sh --help`)

### Verification
- **Re-measure the full gate on a quiet host**, in the configuration operators will actually use (unit, then 3 concurrent browser lanes), and record it in the flight log against the 2026-10-08 baseline:
  - unit at 300 s or less;
  - full gate at 20 minutes or less;
  - every lane within its budget.
- **Confirm the pass set:** every removed or collapsed test is named in the flight log with its covering test.
- **Confirm CI:** one green build with the split tasks, and a doc-only push that triggers no build.
- **Behavior test `parallel-lanes-stay-green`** (authored at leg 4 design): three concurrent browser lanes on the operator's host produce the sequential pass set across repeated runs.
