# Leg: ci-split-and-locked-installs

**Status**: completed
**Flight**: [Test-suite runtime](../flight.md)

## Objective
CI runs the browser work as 3 resource-limited tasks driven by `scripts/run-tests.sh --lane`, with WebKit only where `contracts` runs. Every CI task installs from `uv.lock` through `uv sync --frozen`, with Concourse caches. Documentation-only pushes trigger no build. pip-audit runs weekly and at tag time. This completes squawk 0107.

## Context
- **This leg merges the flight's planned legs 5 (`ci-lane-split`) and 6 (`ci-locked-deps`).** The Flight Director recorded the decision in the flight log's Decisions.
  - Both rewrite the same `ci/tasks/*.yml` install and run blocks.
  - Both are verified by the same `fly execute` task runs, which take about 10 minutes each per browser task. Two legs would pay for those runs twice.
  - Neither needs a mid-leg human decision; the flight already chose caches over a baked image.
- **Flight decisions:**
  - **Host concurrency policy.** CI runs 3 browser tasks, each with `cpu`/`memory` limits. A local gate and a CI build never run at the same time.
  - **Install mechanism.** Option (b), `uv sync --frozen` per task with Concourse `caches:`, because an image registry would add operational load on the shared host.
- **Divert condition** (flight spec): if CI resource limits cannot be expressed on the local Concourse workers, stop and report.
- **Environment, checked by the Flight Director at design time:**
  - `fly` 8.1.0 is installed and the `the-one` target (team `the-one`, `http://localhost:8080`) has a live token, so `fly validate-pipeline` and `fly -t the-one execute` work from an agent shell. The 2026-10-08 inspection could not reach it; that is no longer true.
  - Running a `fly execute` browser task loads this same host. **Never run one while a local test run is going, and never run two browser tasks at once.**
- **Leg 4's lanes.** Leg 4's lanes and budgets (flight log, "Leg 4") define the lane-to-task assignment.
- **Current CI** (`ci/the-one.pipeline.yml`, `ci/tasks/*.yml`):
  - The `ci` job runs 5 `in_parallel` tasks: lint, test, browser, windows-tests and bwrap (privileged).
  - Every task runs `pip install -e ".[all-llms,dev]"` from scratch, except lint, which pins `ruff==0.15.15`, the same as `uv.lock`'s 0.15.15.
  - The `repo` git resource has no `paths` or `ignore_paths`.
  - `build-windows-installer` gets `repo` with `passed: [ci]`.
- **The pre-merge gate stays.** `.github/workflows/pr-lint.yml` (ruff plus the release-closure pip-audit) runs on PRs only. Squawk 0107 asks for a scheduled audit whose failure is visible.

## Inputs
- `ci/the-one.pipeline.yml`, `ci/set-pipeline.sh`, `ci/README.md`
- `ci/tasks/{lint,test,browser,bwrap,windows-tests}.yml`. Not in scope: `windows-installer-build.yml` and `windows-vector-bench.yml`, which are ad-hoc and release builds.
- `.github/workflows/pr-lint.yml` (the `pip-audit` job and its `uv export` closure) and `.github/workflows/windows-installer.yml` (`v*` tags).
- `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py`. **This leg depends on leg 4 having landed:** it needs leg 4's lanes, `--plan` and budget table, and does not start before then.
- `uv.lock`, `pyproject.toml`
- `squawks/0107-*.md`

## Outputs
- `ci/tasks/browser.yml` is replaced by three task files, for example `browser-1.yml`…`browser-3.yml`, or one parametrized file with a `LANES` param per task. Each:
  - runs its lanes through `scripts/run-tests.sh --lane <lane>` and fails if any lane fails;
  - carries `container_limits`;
  - installs WebKit, and sets `THE_ONE_REQUIRE_WEBKIT=1`, only in the task that runs `contracts`.
- Every Linux task (`test`, the browser tasks, `bwrap`, `lint`) installs with `uv sync --frozen` from `uv.lock`, using task `caches:` for the uv cache and, in the browser tasks, the Playwright browsers.
  - `windows-tests` does the same on Windows. If that cannot be made to work on the Windows worker within the leg, it stays on pip and the reason is recorded as a deviation.
- The `repo` resource gains `ignore_paths` for documentation-only paths.
- A weekly scheduled pip-audit, a tag-time pip-audit, and squawk 0107 completed.
- A unit test pins that the browser tasks' lanes are exactly the set of `run-tests.sh` lanes.
- `ci/README.md` and the browser task headers state measured durations and the concurrency policy.

## Acceptance Criteria
- [ ] **AC1. The browser work is split into 3 tasks.**
  - The `ci` job's `in_parallel` has 3 browser tasks in place of `browser`.
  - **Recipe.** Each task runs its assigned lanes in sequence, with `TEST_TIMEOUT=3600` and `PYTHON=.venv/bin/python` (the venv `uv sync` built in `repo/.venv`):

    ```
    set +e; rc=0; for l in $LANES; do bash scripts/run-tests.sh --lane "$l" --tb=short --timeout=300 || rc=$?; done; exit $rc
    ```

    The task's `bash -ceu` must not abort the loop, so turn off `-e` around it.
  - **No `-x`, on purpose.** CI wants the full failure surface; the per-test `--timeout` bounds hangs.
  - Lanes are assigned so the three tasks' summed leg 4 budgets are as even as possible.
  - `contracts` is in exactly one task. That task alone runs `playwright install --with-deps chromium webkit` and sets `THE_ONE_REQUIRE_WEBKIT=1`; the other two install `chromium` only.
  - `THE_ONE_DEV_MODE` may be dropped from task env: `tests/browser/conftest.py` sets it per spawned server.
  - Prefer **one parametrized `ci/tasks/browser.yml`** with a `LANES` param (and a `WEBKIT` param), used three times in the pipeline under three task names. That keeps the AC2 test simple.
- [ ] **AC2. CI lanes cannot drift from the local lanes.** A unit test (in `tests/test_run_tests_lanes.py`) parses the browser task files and asserts:
  - the multiset of lanes they run equals the canonical lane set, with each lane exactly once. The canonical set is the one leg 4's `run-tests.sh --plan` prints; the aliases `chat`, `studio` and `system` are never included;
  - only the task with `contracts` installs WebKit or sets `THE_ONE_REQUIRE_WEBKIT`.
- [ ] **AC3. Resource limits are set and proven.**
  - Each browser task's config has `container_limits` with a `memory` hard limit and a `cpu` value.
    - Memory: 3 GiB suggested, with more for the task running `contracts` (Chromium plus WebKit), for example 4 GiB.
    - An OOM shows as a lane exiting 137 and the kernel's OOM message in the task log. Record the observed peak if it is visible.
  - Watch for Chromium's 64 MB `/dev/shm` in containers. Playwright's Chromium already passes `--disable-dev-shm-usage` by default; confirm the first run shows no shared-memory crashes.
  - A one-off `fly execute` of one browser task prints the cgroup's effective limits (`memory.max`; `cpu.max` or `cpu.weight`) at the start of its run, and the flight log records them.
  - **Divert if** the worker ignores `container_limits`, for example `memory.max` reads `max`.
  - If `cpu` turns out to be a relative weight, not a cap, record that as the measured semantics. A hard CPU cap is not required; a memory cap is.
- [ ] **AC4. Every task installs from the lockfile.** `test`, the browser tasks, `bwrap` and `lint` all:
  - install with **`uv sync --locked`**, with `--extra all-llms --extra dev`. Lint uses `--extra dev` only.
    - The project declares dev tools as the optional-dependency **extra** `dev`, not a dependency group, so `--only-dev` and `--group dev` are wrong.
    - `--locked` installs exactly `uv.lock` **and** errors when the lock is out of date with `pyproject.toml`, so a forgotten relock fails CI instead of being silently ignored, which `--frozen` would do.
  - run tools from that environment (`uv run --frozen …` or the synced `.venv`);
  - use a pinned image that provides uv, for example `ghcr.io/astral-sh/uv:<pinned-version>-python3.11-bookworm`, or install a pinned uv;
  - carry `caches:` for the uv cache and, in the browser tasks, `PLAYWRIGHT_BROWSERS_PATH`.

  - No task runs `pip install -e`. `uv sync` installs the project itself, editable.
  - **Stale-lock demonstration.** In a scratch copy, raise a floor in `pyproject.toml` without relocking. Show that `uv sync --locked` errors, and record the error.
  - **`bwrap`** keeps its privileged copy-to-`/opt` pattern. It runs `uv sync --locked` **inside `/opt/the-one`**, so the editable path points there, rather than building the venv in `repo/` and copying it.
  - **Tools run from the synced environment:** `PYTHON=.venv/bin/python` for `run-tests.sh`, and `.venv/bin/<tool>` or `uv run --locked` elsewhere. `python3` on the image's `PATH` is not the venv.
- [ ] **AC5. Flight-artifact-only pushes trigger nothing.**
  - The `repo` resource has `ignore_paths` covering exactly the flight-artifact directories: `missions/`, `sorties/`, `squawks/`, `maintenance/`, `service-reports/` and `.flightops/`. Use the form the git resource documents, e.g. `missions/**` or `missions/`. Check its docs for this resource version.
  - **`docs/` and `*.md` are NOT ignored.** Unit tests read `docs/*.md` and repo Markdown, for example `tests/test_ui_control_inventory.py` and the testid-registry guards, so a doc-only change can break CI. It must still trigger.
    - The FD confirmed at design time that no test reads a flight-artifact directory: grep of `tests/` for those paths outside comments.
    - The pushes this rule exists for are flight logs, debriefs, squawks and maintenance reports, all of which live in these directories.
  - `build-windows-installer` gets the same `repo` resource with `passed: [ci]`, so an ignored commit triggers neither job. The installer is then built from the last commit that passed `ci`. Say so in the README.
  - The README states that a mixed commit (code plus flight artifacts) still triggers, and that the build tests the whole tree at that commit.
- [ ] **AC6. The pipeline validates and every changed task runs green.**
  - `fly validate-pipeline -c ci/the-one.pipeline.yml` passes.
  - Each changed Linux task runs green through `fly -t the-one execute -c <task> -i repo=<clean export of the working tree>`, one at a time, never during a local test run. The `-p` flag applies to bwrap. The clean export avoids uploading `.venv`; use `git stash`-free means such as `git ls-files -co --exclude-standard | rsync --files-from`, or a `git worktree` of a temp commit.
  - The flight log records each task's wall time and its install-step time.
  - Expected: caches do not persist across one-off `fly execute` builds, so install times here are cold and prove nothing about caching. Cache correctness and steady-state times are checked post-merge (AC8).
  - Task caches are per worker, per job and per task step **name**. Each of the three browser tasks therefore has its own Playwright and uv caches, and renaming a task drops its cache. Say so in the README.
- [ ] **AC7. pip-audit runs weekly and at release.**
  - `pr-lint.yml` gains `schedule:` (weekly cron) and `workflow_dispatch:` triggers.
    - The `lint` job gets `if: github.event_name == 'pull_request'`, so it stays PR-only.
    - The `pip-audit` job runs on all three triggers.
  - **The README says how failures surface:** a scheduled failure is visible through GitHub's failure notification, which goes to the user who last edited the cron line. GitHub disables scheduled workflows after 60 days with no repository activity.
  - `windows-installer.yml` runs the same release-closure audit as a separate job that the build job `needs:`, so a finding fails the release before any build time is spent.
  - Squawk 0107 is marked completed, with the corrective action and verification written. Its sign-off is "flight-end Reviewer, Mission 26 Flight 1".
- [ ] **AC8. Docs, and the operator handoff.**
  - **`ci/README.md`:**
    - the task table, with three browser rows and their lanes;
    - lockfile installs and caches;
    - `ignore_paths`;
    - the concurrency policy (3 limited browser tasks; the local gate and CI never at the same time);
    - the measured `fly execute` times from AC6.
  - **`ci/tasks/browser*.yml` headers** state their lanes and measured time.
  - **The flight log** gets a **post-merge operator checklist**, for the Flight Director to carry to landing:
    1. run `ci/set-pipeline.sh`;
    2. one green build, recording the long pole;
    3. **a second build**, recording the cached install times; the first build fills the caches;
    4. push a flight-artifact-only commit and confirm no build;
    5. trigger the pip-audit workflow once through `workflow_dispatch`.

## Verification Steps
- **AC1, AC2, AC4, AC5:** read the YAML, then run `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_run_tests_lanes.py -x --timeout 60`.
- **AC3, AC6:** the `fly execute` runs, with their output summarized in the flight log.
- **AC4 stale lock:** in a scratch copy, raise a floor in `pyproject.toml` without relocking, then run `uv sync --frozen`, which errors. Record the error.
- **AC5:** `fly validate-pipeline` plus a read. The live check is the AC8 post-merge checklist.
- **AC7:** read both workflows. Optionally run `actionlint` if it is installed.

## Implementation Guidance
1. **Assign lanes to tasks.** Use the leg 4 budget table (`run-tests.sh --plan`) for a balanced 3-way split, and write the task files.
2. **Choose and pin the uv image tag.** Confirm the tag exists, for example with `docker manifest inspect` or by pulling through `fly execute`. Use a version no newer than the host's `uv --version` and at least two weeks old.
3. **Convert `test`, `lint` and `bwrap` to `uv sync --frozen`**, then the browser tasks. Set `UV_CACHE_DIR` and `PLAYWRIGHT_BROWSERS_PATH` to cache directories declared under `caches:`, and `UV_LINK_MODE=copy` (the cache sits on a different filesystem).
4. **`ignore_paths` and `validate-pipeline`.**
5. **The AC2 unit test.**
6. **The GitHub workflows (AC7)** and squawk 0107.
7. **`fly execute` runs (AC3, AC6).** One at a time, and only while no local test run is going. Start with `test.yml`, the cheapest, to shake out the install recipe, then the browser task with `contracts`, which also carries the limits print.
8. **Docs (AC8)** and the flight log.

## Edge Cases
- **`windows-tests` on the Windows worker.** uv is not on that worker. Install it with `choco install uv` or `pip install uv==<pin>` into the choco Python, then `uv sync --frozen`. Windows paths in `caches:` work the same way. If it cannot be validated with `fly execute` (the worker is the operator's desktop and may be offline), leave it on pip, and record the deviation and the follow-up.
- **`run-tests.sh` inside a container:** `setsid`, process groups and the watchdog work as on the host. Do not set `THE_ONE_TEST_NETNS`; container networking is not WSL mirrored.
- **`THE_ONE_DEV_MODE=true`**, which the old `browser.yml` set, is still needed. Browser fixtures set it per spawned server anyway, so check before dropping it.
- **`ignore_paths` scope.** A change to `the_one/agents.md`, `CLAUDE.md` or `docs/` still triggers CI, by design (AC5).
- **The Concourse token.** It had already expired by the time of the design review. The Flight Director has the operator log in before spawning this leg. If `fly` reports unauthorized mid-leg, stop and signal `[BLOCKED:fly-login]`. Never attempt a login yourself.

## Files Affected
- `ci/the-one.pipeline.yml`
- `ci/tasks/test.yml`, `lint.yml`, `bwrap.yml`, `windows-tests.yml`
- `ci/tasks/browser.yml`, replaced by the three browser tasks
- `ci/README.md`
- `.github/workflows/pr-lint.yml`, `.github/workflows/windows-installer.yml`
- `tests/test_run_tests_lanes.py`
- `squawks/0107-*.md`
- `missions/26-maintenance/flights/01-test-suite-runtime/flight-log.md`

## Citation Audit
Checked against the working tree at `16e91d7` plus the uncommitted legs 1–4:

| Citation | Status |
|---|---|
| `ci/the-one.pipeline.yml`: `repo` git resource with no `paths`; `ci` job `in_parallel` (`fail_fast: false`) with lint, test, browser, windows-tests and bwrap (`privileged: true`); `build-windows-installer` `passed: [ci]` | verified |
| `ci/tasks/browser.yml`: `python:3.11-bookworm`, `pip install -e`, `playwright install --with-deps chromium webkit`, `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_DEV_MODE=true python -m pytest -m browser tests/browser/` | verified |
| `ci/tasks/test.yml` and `bwrap.yml`: `python:3.11`, `pip install -e ".[all-llms,dev]"`; bwrap copies to `/opt/the-one` and uses `/opt/venv` | verified |
| `ci/tasks/lint.yml`: `pip install ruff==0.15.15`; `uv.lock` ruff is 0.15.15 | verified |
| `ci/tasks/windows-tests.yml`: choco `python311`, then `pip install -e` | verified |
| `.github/workflows/pr-lint.yml`: `on: pull_request` (main); `pip-audit` job with `uv export --no-dev --no-emit-project --extra gui --extra all-llms` | verified |
| `.github/workflows/windows-installer.yml`: `v*` tags | verified |
| `fly` 8.1.0 with target `the-one` reachable (`/api/v1/info` 200) | verified 2026-10-08; token since expired, so operator re-login is needed |
| `pyproject.toml:130` dev deps are `[project.optional-dependencies] dev`; no `[dependency-groups]` | verified (design review) |
| `tests/browser/conftest.py` sets `THE_ONE_DEV_MODE=true` per spawned server | verified (design review) |
