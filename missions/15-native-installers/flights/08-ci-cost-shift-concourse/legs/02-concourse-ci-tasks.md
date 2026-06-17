# Leg: concourse-ci-tasks

**Status**: completed
**Flight**: [CI cost-shift — move day-to-day CI to local Concourse](../flight.md)

## Objective

Author the standalone Concourse **task files** under `ci/tasks/` that reproduce every
routine GitHub Actions CI lane on the `the-one` Concourse team — each independently green
via `fly -t the-one execute -c ci/tasks/<x>.yml -i repo=.` against the working tree — with
the bwrap lane running from a **non-`/tmp` checkout** so the kernel-enforced `requires_bwrap`
suite passes unmodified (the Leg-1 spike proved the only failures were a Concourse
`/tmp`-workspace artifact, not containment).

## Context

- **Leg 1 (GATE) resolved DD4 = GREEN** — bwrap IS viable on the shared linux worker, so this
  leg authors `ci/tasks/bwrap.yml`. Required strategy (flight log → Leg Progress): image
  `python:3.11`, a venv **outside `/tmp`** (`/opt/venv`), and **privileged** execution (the
  worker blocks *unprivileged* userns).
- **Why the 10 MCP `requires_bwrap` tests failed on Concourse — and the fix.** In host mode
  (`minimal_rootfs=False`, the default for the MCP integration tests) the bwrap backend emits
  `--ro-bind / /` (full host rootfs, read-only) **then** `--tmpfs /tmp`
  (`bubblewrap.py` host-mode ordering). So any path **under `/tmp`** is wiped inside the
  sandbox — and `test_mcp_sandbox_integration.py` derives **both** the spawned MCP server's
  `cwd` (→ bwrap `--chdir`) **and** its `PYTHONPATH` (→ `--setenv`) from
  `_PROJECT_ROOT = Path(__file__).resolve().parent.parent` (the repo root). On GitHub the repo
  root is `/home/runner/work/…` (not under `/tmp`) so it survives the overlay; on Concourse it
  is `/tmp/build/…/repo`, which the `--tmpfs /tmp` overlay erases. **The principled fix is to
  run the bwrap lane from a checkout that is NOT under `/tmp`** — copy the `repo` input to e.g.
  `/opt/the-one` and run pytest from there, so `_PROJECT_ROOT` resolves outside `/tmp` and the
  full RO bind makes it visible inside the sandbox. This reproduces the exact condition that
  makes the suite green on GitHub. **No test-code change** — the tests are not buggy; the
  Concourse `/tmp/build` workspace location is the anomaly, so we adapt the CI environment.
  (Modifying the tests' `_PROJECT_ROOT`/PYTHONPATH would be a higher-risk change to honor a
  workspace invariant the tests don't actually violate — they assume a non-`/tmp` checkout,
  which relocation restores.)
- **Only `bwrap.yml` needs relocation.** The `lint`/`test`/`browser` tasks run their pytest
  process directly (no bwrap sandbox), so the `/tmp/build` workspace is fine for them — only
  the **bwrap-spawned subprocesses** hit `--tmpfs /tmp`. Keep the relocation isolated to
  `bwrap.yml`.
- **The goldfinch task-file pattern is the template** (`~/projects/goldfinch/ci/tasks/*.yml`):
  `platform:` + `image_resource` (registry-image) + `inputs: [{name: repo}]` + a `run:` block;
  each task runnable via `fly execute -c … -i repo=.` and as a pipeline task (Leg 3 reuses the
  files).
- **Bare `python -m pytest`, not the local group-kill wrapper** — Concourse task containers are
  ephemeral per build, so orphaned uvicorn/Chromium children die with the container (the GH
  `test.yml` header's ephemeral-runner rationale). Do NOT use `run-tests.sh`.
- **Default-suite deselection is in `pyproject.toml`** (`addopts = "-m 'not live and not browser
  and not pixel and not requires_bwrap and not discord_hat' --import-mode=importlib"`), so
  `python -m pytest tests/` is the correct full default-suite invocation — no extra `-m`. The
  `--import-mode=importlib` is picked up from the repo's `pyproject.toml` automatically.
- **Source GitHub lanes being ported:**
  - `lint.yml`: `pip install ruff==0.15.15`; `ruff check the_one/ tests/`; `ruff format --check the_one/ tests/`.
  - `test.yml::test`: `pip install -e ".[all-llms,dev]"`; `python -m pytest tests/ --timeout=300 --tb=short`.
  - `test.yml::browser`: `+ playwright install --with-deps chromium`; `THE_ONE_DEV_MODE=true python -m pytest -m browser tests/browser/ --timeout=300 --tb=short`.
  - `test.yml::windows` (lines 79-116): `windows-2022`, the **curated OS-divergent file list** — re-listed verbatim (see below).
  - `test.yml::bwrap` (lines 118-144): `-m requires_bwrap tests/` — ported per the GREEN strategy + relocation.

## Inputs

- `the-one` working tree; `fly -t the-one` session valid; linux + windows workers up.
- Leg 1 landed (DD4 = GREEN; strategy recorded in the flight log).
- `the_one` installs via `pip install -e ".[all-llms,dev]"` on `python:3.11`.

## Outputs

- `ci/tasks/lint.yml`, `ci/tasks/test.yml`, `ci/tasks/browser.yml` — **linux** tasks.
- `ci/tasks/windows-tests.yml` — **windows** task (PowerShell + choco `python311`).
- `ci/tasks/bwrap.yml` — **linux** task (privileged at the pipeline level; `/opt/venv`; runs
  from a relocated `/opt/the-one` checkout).
- *(unchanged)* `ci/tasks/windows-installer-build.yml` is reused as-is by Leg 3 — do NOT edit it.
- **No production/test source files change** in this leg.

## Acceptance Criteria

- [x] `ci/tasks/lint.yml` green standalone (`fly execute -c … -i repo=.`): `ruff check` +
      `ruff format --check` on `the_one/ tests/`, `ruff==0.15.15`, `python:3.11`.
- [x] `ci/tasks/test.yml` green standalone (default suite, `python -m pytest tests/`, bare
      invocation, `python:3.11`, `pip install -e ".[all-llms,dev]"`).
- [x] `ci/tasks/browser.yml` green standalone (`playwright install --with-deps chromium`,
      `-m browser tests/browser/`, `THE_ONE_DEV_MODE=true`). *(~15 min — the long pole.)*
- [x] `ci/tasks/windows-tests.yml` green standalone on the windows worker: PowerShell + choco
      `python311` (NOT a linux task), running the curated OS-divergent file set re-listed
      verbatim from `test.yml:104-116`; the `[...]` extras spec quoted for PowerShell.
- [x] `ci/tasks/bwrap.yml` green standalone via `fly -t the-one execute -p -c ci/tasks/bwrap.yml -i repo=.`:
      installs bubblewrap, relocates the checkout to `/opt/the-one`, builds `/opt/venv`, runs
      `-m requires_bwrap tests/` with `--log-cli-level=INFO`; the build log shows
      `sandbox backend: bubblewrap — tool spawns are sandboxed` and **all non-skipped
      `requires_bwrap` tests pass** (the 10 MCP failures the spike saw are gone — 2 tests in
      `test_mcp_sandbox_integration.py` are `@pytest.mark.skip` and are expected to remain
      skipped, not failed).
- [x] Every task file carries a header comment (goldfinch convention: what it mirrors + the two
      run modes) and references the `repo` input consistently. `bwrap.yml`'s header documents
      the **non-`/tmp` relocation rationale** and that the lane REQUIRES a privileged task step.

## Verification Steps

- For each of the 5 task files: the `fly execute` build result = succeeded.
- `bwrap.yml`: the log shows the `bubblewrap` backend line and a clean `requires_bwrap` run
  (no MCP-test failures; the 2 `@skip` tests skipped).
- `git status` shows only the 5 new `ci/tasks/*.yml` (and the flight-log/leg edits) — **no
  changes under `tests/` or `the_one/`**, confirming the relocation approach left source untouched.

## Implementation Guidance

1. **Author the linux `lint`/`test`/`browser` tasks** on the goldfinch template:
   `platform: linux`, `image_resource` → `registry-image` `python` tag `3.11`, `inputs: [repo]`,
   `run: { path: bash, args: [-ceu, "<script>"] }` with `cd repo` then the ported commands.
   `lint` only needs `pip install ruff==0.15.15` (not the whole project). `browser` adds
   `python -m playwright install --with-deps chromium` (root in the debian image — fine) and
   sets `THE_ONE_DEV_MODE=true`.
2. **Author `bwrap.yml` (linux, GREEN strategy + relocation):**
   - `apt-get update && apt-get install -y bubblewrap`
   - **Relocate the checkout out of `/tmp`**: `cp -a repo /opt/the-one` (the `repo` input lands
     under the build dir at `/tmp/build/…/repo`; `/opt/the-one` is outside `/tmp`, so the
     host-mode `--ro-bind / /` exposes it inside the sandbox and `--tmpfs /tmp` does not erase it).
   - `python -m venv /opt/venv`
   - `cd /opt/the-one && /opt/venv/bin/pip install -e ".[all-llms,dev]"` (editable `.pth` now
     points at `/opt/the-one`, also outside `/tmp`).
   - `cd /opt/the-one && /opt/venv/bin/python -m pytest -m requires_bwrap tests/ --timeout=300 --tb=short --log-cli-level=INFO`
     — chain the `cd` through the pytest call itself (a `bash -ceu` `&&` chain only persists CWD
     within that one compound command; a bare `pytest` on a later line would run from the task
     working dir and `_PROJECT_ROOT` would resolve elsewhere).
   - (Header note for the implementer: `conftest.py` sets `THE_ONE_DATA_DIR` under `/tmp` for the
     pytest *runner* process — harmless here, since the runner runs outside bwrap; only the
     bwrap-spawned subprocesses' paths must avoid `/tmp`, which relocation handles.)
   - The task file carries NO `privileged:` field — privilege comes from `fly execute -p` (smoke)
     and `privileged: true` on the **pipeline task step** (Leg 3). Header must state this.
3. **Author `windows-tests.yml`** modeled on `ci/tasks/windows-installer-build.yml`:
   `platform: windows`, `run: { path: powershell, args: [-NoProfile, -ExecutionPolicy, Bypass,
   -Command, "<script>"] }`. `choco install python311 -y --no-progress`; `& "C:\Python311\python.exe"
   -m pip install -e ".[all-llms,dev]"` (quote the `[...]` extras for PowerShell — see
   `windows-installer-build.yml`'s `& $py -m pip install -e ".[gui,all-llms]"`); then
   `& "C:\Python311\python.exe" -m pytest --timeout=300 --tb=short <curated file list>`. Re-list
   the EXACT set from `test.yml:104-116` (test_platform_paths/shell/interpreter/tempdirs,
   test_pty_dispatch/session/windows, test_filesystem_tools/helpers/config, test_config/config_data_dir,
   test_execution_tools/helpers/config, test_encryption, test_sandbox_factory/contract,
   test_logging_config). Smoke with its own `fly execute` before Leg 3 (single shared windows
   worker — be brief).
4. **Iterate each task to green via `fly execute`** before the leg is done — the standalone-green
   gate is the whole point of the task-file split. For the windows + bwrap tasks, mind the shared
   single workers (one shot each).

## Edge Cases

- **`bwrap.yml` relocation must precede install AND run** — if you `pip install -e` from
  `/tmp/build/…/repo` and only `cd /opt/the-one` to run, the editable `.pth` still points under
  `/tmp`. Install from `/opt/the-one` so both the install path and `_PROJECT_ROOT` are off `/tmp`.
- **`privileged` is not a task-config field**: it lives on the pipeline task step / `fly execute -p`.
  Do NOT put it in `bwrap.yml`.
- **PowerShell extras quoting**: `.[all-llms,dev]` must be quoted so PowerShell doesn't mangle the
  brackets/comma (the GH windows job used Git-Bash to dodge this; the choco task must quote).
- **`fly execute -i repo=.` uploads the working tree, not the git tree** — it does NOT honor
  `.gitignore`, so a local `.venv/`, `dist/`, or `__pycache__/` inflates the upload (slow, rarely
  fatal). Prefer a clean tree; note this in the task headers and (Leg 5) the `ci/README.md`.
- **browser image apt deps**: `playwright install --with-deps chromium` pulls its own apt deps as
  root — if the debian `python:3.11` image is missing a base lib, `--with-deps` installs it; if a
  surprise surfaces, record it (the flight's "native-dep surprise" divert criterion).
- **Shared worker contention**: the `windows-tests` smoke competes with the `windows-installer`
  pipeline for the single windows worker; the linux tasks compete with the existing pipelines —
  keep smokes single-shot.

## Files Affected

- `ci/tasks/lint.yml`, `ci/tasks/test.yml`, `ci/tasks/browser.yml`, `ci/tasks/windows-tests.yml`,
  `ci/tasks/bwrap.yml` — new.
- `missions/.../flight-log.md` — leg progress entry.
- *(No `tests/` or `the_one/` changes — the bwrap `/tmp` issue is solved by relocation in the task.)*

---

## Post-Completion Checklist

- [x] All acceptance criteria verified (every task file green standalone via `fly execute`)
- [x] `bwrap.yml` runs the full `requires_bwrap` suite green from `/opt/the-one` (no MCP failures)
- [x] No source files under `tests/` or `the_one/` changed
- [x] Flight log updated with the leg progress entry (per-task `fly execute` results)
- [x] Set this leg's status to `landed` (commit deferred to end-of-flight batch)
