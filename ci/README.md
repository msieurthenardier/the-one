# the-one CI on local Concourse

CI runs on the **local Concourse** instance (`http://localhost:8080`, team `the-one`)
instead of GitHub Actions, to conserve GitHub Actions minutes. GitHub Actions
`lint.yml` and `test.yml` are disabled (manual `workflow_dispatch` only — break-glass
fallback). `release.yml` (the `v*`-tag release path: audit, version gate, the three
platform builds, publish) owns official releases.

**Pre-merge gate (GitHub Actions):** `pr-lint.yml` runs on every `pull_request`
targeting `main` — `ruff check` + `ruff format --check` + a release-closure `pip-audit`,
all fail-on-nonzero. This restores automated pre-merge verification (maintenance
report 2026-07-10 finding C1: 10 PRs had merged with no automated gate) without
re-enabling the heavy lanes (test/browser/windows/bwrap) on PR triggers — those stay
cost-shifted to post-merge Concourse. See "Pre-merge lint + audit gate" below for the
pip-audit policy.

Pipeline UI: `http://localhost:8080/teams/the-one/pipelines/the-one`.

## What runs where

| Check | Task file | GH Actions equivalent |
|---|---|---|
| Lint (ruff check + format) | `ci/tasks/lint.yml` | "lint" job (`lint.yml`, break-glass) + `pr-lint.yml` "lint" job (pre-merge, PRs) |
| Release-closure pip-audit | — | `pr-lint.yml` "pip-audit" job (pre-merge, PRs) |
| Full default test suite | `ci/tasks/test.yml` | "test" job (`test.yml`) |
| Browser tests (Playwright, every lane in sequence, Chromium + WebKit) | `ci/tasks/browser.yml` | "browser" job (`test.yml`) |
| Windows curated subset (~427 tests) | `ci/tasks/windows-tests.yml` | "windows" job (`test.yml`) |
| bwrap sandbox tests (privileged) | `ci/tasks/bwrap.yml` | "bwrap" job (`test.yml`) |
| Windows installer build + MinIO publish | `build-windows-installer` job (pipeline) | `release.yml` → `windows-packages.yml` (v\* tag only) |

All five CI tasks run in parallel (`in_parallel`, `fail_fast: false`) as a single `ci`
job. The browser task is a single task that runs `scripts/run-tests.sh --parallel 1`:
every canonical browser lane, one after another (no lane list lives in CI, so it cannot
drift from the local lanes; `tests/test_run_tests_lanes.py` pins that). Its CI time is
**unmeasured until the first post-merge build**; locally the first eight lanes sum to about
2240 s sequential (a ninth lane, `providers`, joined in sortie 02). On Concourse the full browser suite runs on **every push to `main`** — the
path-filter that rationed it on GitHub Actions (minutes cost) is gone (DD5). None of
these five lanes run on GitHub Actions PR triggers — `pr-lint.yml` (lint + pip-audit
only) is the only pre-merge GH Actions gate; the heavy lanes stay post-merge on
Concourse.

## Installs, caches and the concurrency policy (M26 F1 L5)

**Locked installs.** Every task installs from `uv.lock` with `uv sync --locked`
(`--extra all-llms --extra dev`; lint `--extra dev` only), in the pinned image
`ghcr.io/astral-sh/uv:0.9.30-python3.11-bookworm` (the `0.10.0-python3.11-bookworm`
tag does not exist). `--locked` installs exactly the lock and errors when `uv.lock` is
stale against `pyproject.toml` ("The lockfile at `uv.lock` needs to be updated, but
`--locked` was provided"), so a forgotten relock fails CI; `--frozen` would install
silently. Tools run from the synced `.venv` (`PYTHON=.venv/bin/python` for
`run-tests.sh`). `bwrap` builds its venv inside `/opt/the-one`. `windows-tests`
(no uv image on the Windows worker) pip-installs `uv==0.9.30` into the choco Python 3.11,
runs `uv sync --locked` with `UV_PYTHON` set to it (`UV_PYTHON_DOWNLOADS=never`), and runs
pytest from `.venv\Scripts\python.exe`.

**Caches.** `uv-cache` (all Linux tasks) and, in the browser task, `playwright-browsers`
are Concourse task `caches:`. They are per worker, per job and per task step NAME, so
renaming a task drops its cache. They do not persist across one-off `fly execute`
builds, so `fly execute` install times are cold; the first pipeline build fills the
caches and a second build shows the cached times. The cache volume is mounted `noexec`
(a browser spawned from it fails with EACCES): Playwright downloads into it and the
task runs the browsers from a copy under `/opt/pw`. The task also forces apt to IPv4
(the workers have no IPv6 route; one build failed with "Network is unreachable").

**Concurrency policy.** CI runs ONE browser task, whose lanes run one after another, so
at most one browser lane runs at a time. A local gate (`make gate`, which runs three
lanes at once) and a CI build never run at the same time on this host. **There are no
`container_limits` on any task, on purpose:** the local Concourse workers reject them
(runc: `cannot enter cgroupv2 "/sys/fs/cgroup/garden" with domain controllers -- it is
in threaded mode`, on both linux workers, for memory alone, cpu alone or both), so a
task that sets them fails at container creation. `tests/test_run_tests_lanes.py` fails
if one is added; re-add them only after the workers' cgroup layout is fixed. Memory is
the real constraint: a three-task browser trial exhausted the host (about 12.6 GB of
Shmem in Docker Desktop's VM, load near 140) and took Concourse down, which is why CI
runs a single browser task. Watch host memory during the first post-merge build.

**`ignore_paths`.** The `repo` resource ignores `missions/**`, `sorties/**`,
`squawks/**`, `maintenance/**`, `service-reports/**` and `.flightops/**`: flight logs,
debriefs, squawks and maintenance reports trigger no build. `docs/` and `*.md` are NOT
ignored, because unit tests read `docs/*.md` and repository Markdown (for example
`tests/test_ui_control_inventory.py` and the testid-registry guards), so a doc-only
change can break CI and must still trigger. A mixed commit (code plus flight artifacts)
still triggers, and the build tests the whole tree at that commit.
`build-windows-installer` takes the same `repo` with `passed: [ci]`, so an ignored
commit triggers neither job; the installer is built from the last commit that passed
`ci`.

**Scheduled audit.** `pr-lint.yml` also runs `pip-audit` weekly (Mondays 06:17 UTC) and
on `workflow_dispatch`; `lint` stays PR-only (squawk 0107). A scheduled failure is
visible through GitHub's failed-workflow notification, which goes to the user who last
edited the cron line, and GitHub disables scheduled workflows after 60 days with no
repository activity. `release.yml` runs the same audit as a job its three builds
`needs:`, so a finding fails a `v*` release before any build time is spent.

## Measured times

`fly execute`, cold caches, one task at a time (2026-10-08). Install is the
`uv sync --locked` step; wall includes the image pull.

| Task | Result | Install step | Wall |
|---|---|---|---|
| `lint` | passed | 26 s | 2m56s |
| `bwrap` (`-p`) | 41 passed, 3 expected skips | 38 s | 1m17s |
| `test` | 5620 passed, 1 failed, 12 skipped | 37 s | 6m31s |

The one `test` failure was `test_self_configuration_surface.py::TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain`
(an MCP initialize timeout); it passes when its file runs alone in the same container
and has not failed locally. The browser task's CI time is **unmeasured**; the first
post-merge build is its measurement.

## Pre-merge lint + audit gate

`.github/workflows/pr-lint.yml` triggers `on: pull_request` (branches: `[main]`) and
runs two jobs, both fail-on-nonzero:

- **lint** — `ruff check the_one/ tests/ scripts/ evals/` + `ruff format --check the_one/ tests/ scripts/ evals/`,
  pinned to the same `ruff==0.15.15` version as `ci/tasks/lint.yml` (parity with the
  Concourse lane).
- **pip-audit** — audits the **release dependency closure**: `uv export --no-dev
  --no-emit-project --extra gui --extra all-llms --format requirements-txt` (the
  closure the Windows installer actually ships — `build.ps1` installs
  that locked closure; excludes dev/toolchain deps and the editable self-entry) fed to
  `pip-audit --disable-pip -r`. `--disable-pip` audits the pinned+hashed export
  as written with no resolver/dry-run install — needed because the gui extra's linux
  marker pulls `pycairo` (via `pywebview[gtk]`), which can't metadata-build on the
  runner and isn't part of the shipped artifact anyway. The extras were added
  2026-07-28 after pillow's advisories (gui-extra-only, so invisible to the previous
  base-runtime-only export) were caught by a full-venv audit instead of this gate.
  This is a **deliberate policy change** from the existing `make audit` target
  (`Makefile:229-231`, `pip-audit --skip-editable || true`, warn-only): the PR gate
  is blocking. It stays green while the release closure is clean and only re-reddens
  when a new CVE appears in it — the intended signal. Dev-only findings (e.g.
  `msgpack` via pip-audit's own `cachecontrol` dependency, or the `pip` toolchain
  itself) are out of scope by construction (`--no-dev` excludes them), not
  suppressed via an ignore-list.

## Daily use

### 1. Pre-push gate against your local working tree

Runs the exact CI task on the Concourse worker against your **current files**
(committed or not). `-i repo=.` uploads the working tree — not git-archive — so
**use a clean tree (a fresh export without `.venv/`)** (no stray `.venv/`, `dist/`, `build/` directories) to avoid
uploading large artifacts to the worker.

```bash
fly -t the-one execute -c ci/tasks/lint.yml          -i repo=.
fly -t the-one execute -c ci/tasks/test.yml          -i repo=.
fly -t the-one execute -c ci/tasks/browser.yml       -i repo=.
fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.
fly -t the-one execute -p -c ci/tasks/bwrap.yml      -i repo=.
```

> **bwrap requires `-p`** (`--privileged`). The shared linux worker blocks
> unprivileged user namespaces; a privileged container grants the nested userns
> capability that bubblewrap requires. `fly execute -p` is the pre-push equivalent;
> the pipeline task step carries `privileged: true`.

### 2. Automatic CI on every push to `main`

The `ci` job has a `git` resource on `main` (`trigger: true`) and runs all five tasks
in parallel. Watch it at `http://localhost:8080/teams/the-one/pipelines/the-one`.

The `build-windows-installer` job auto-triggers after `ci` passes (`trigger: true` +
`passed: [ci]`) — so a successful CI run on `main` automatically builds and publishes
the installer to MinIO. `ci/tasks/windows-installer-build.yml` installs the exported
release closure into a fresh per-build `venv` (M24 F02 L06) rather than the
persistent `C:\Python311` base interpreter, because the Windows worker runs tasks
uncontainerised and that interpreter's site-packages survive across builds — build
606657 shipped a stale `hf_xet` package that way. The venv alone isn't sufficient,
though: `pip install -r <uv export>` still needs `--no-deps` (build 606698, AC-15) —
without it, pip walks each package's own declared requirements in hash-checking
mode, huggingface-hub's wheel metadata still declares `hf-xet` even though the
closure correctly excludes it, and pip refuses to install ANYTHING rather than
skipping just that one package. Every native step from `pip install --upgrade
pip` through the PyInstaller freeze now also checks `$LASTEXITCODE`, since PowerShell's `$ErrorActionPreference = "Stop"` doesn't apply
to native-executable exit codes — that gap is how build 606657's failed install went
unnoticed in the first place.

### 3. On-demand installer build

To trigger an installer build manually (e.g. from a branch after a standalone
`fly execute` of the windows build task):

```bash
# Trigger the pipeline job (runs after the current ci build):
fly -t the-one trigger-job -j the-one/build-windows-installer -w

# Or build ad-hoc against your working tree (output to local dir, no MinIO):
fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out
```

The installer lands in the MinIO bucket `the-one-installers`. Browse via the MinIO
console at `http://localhost:9001` (minioadmin / minioadmin), or:

```bash
docker exec concourse-local-minio-1 \
  mc ls --recursive local/the-one-installers
```

## Setup / maintenance

### Set or update the pipeline

```bash
bash ci/set-pipeline.sh
fly -t the-one unpause-pipeline -p the-one
```

Or with `--non-interactive` to skip the apply prompt:

```bash
bash ci/set-pipeline.sh --non-interactive
```

### Secrets (Vault)

Concourse resolves `((var.field))` from the **in-memory dev-Vault** at team-level
paths `concourse/the-one/<var>`:

| Vault path | Fields | Used by |
|---|---|---|
| `concourse/the-one/github-deploy-key` | `private_key` (read-only SSH deploy key) | `repo` git resource — SSH clone of the private repo |
| `concourse/the-one/minio` | `access_key`, `secret_key`, `endpoint`, `bucket` | inline `minio/mc` publish task in `build-windows-installer` |

> **MinIO endpoint is a bare `host:port` — no scheme.** The `((minio.endpoint))`
> Vault value is `172.19.0.20:9000` (no `http://`). The inline `minio/mc` publish
> task builds the URL itself: `MC_HOST_minio="http://${MINIO_KEY}:${MINIO_SECRET}@${MINIO_ENDPOINT}"`.
> Do NOT add `http://` to the Vault value — the task would produce a double-scheme
> URL (`http://http://...`) and fail to connect.
>
> **(Note for readers coming from goldfinch)**: goldfinch uses an `s3` resource
> which requires a full-URL endpoint. The-one uses the inline `mc` task instead, so
> the rule is the OPPOSITE — bare `host:port` is correct here.

> **IP, not the compose service name.** Concourse task containers use external DNS
> (8.8.8.8) and are NOT on the compose network, so `minio` does not resolve inside
> them. Use the compose-network IP, `172.19.0.20`: a static address in
> concourse-local's reserved block, pinned in
> `~/projects/concourse-local/docker-compose.yml`, so it does not move on
> `docker compose down/up` and the Vault value needs no re-pointing.

> **The Vault dev server is in-memory** — secrets are lost on container restart.
> They are reseeded from `~/projects/concourse-local/.vault-seeds.json` on startup.
> The two team-level entries (`concourse/the-one/github-deploy-key` and
> `concourse/the-one/minio`) are already in the seed file. Any secret added live
> **must also be added to the seed file** or it will vanish on the next restart.
>
> The seed-file entrypoint writes each field to a temp file and passes `field=@file`
> to `vault kv put` — so multiline values (e.g. the SSH deploy key PEM) round-trip
> correctly.

These secrets were promoted to team-level (`concourse/the-one/*`) during Flight 8 Leg 3
from the old per-pipeline paths (`concourse/the-one/windows-installer/*`). The originals
were left in place (no rename) so there was no dead window during cutover. The seed file
already contained the team-level entries ahead of the live promotion.

### bwrap lane: privileged task + /opt relocation

The `bwrap` task step in the pipeline carries `privileged: true` (the shared linux worker
blocks unprivileged user namespaces; privileged grants the nested userns capability
bubblewrap requires). See `ci/tasks/bwrap.yml` for the full rationale comment.

The task also **relocates the checkout to `/opt/the-one`** before install and run. The
Concourse workspace lives under `/tmp/build/<id>/repo/` — and bwrap's `--tmpfs /tmp`
overlay shadows everything under `/tmp` inside the sandbox. Moving the checkout to
`/opt/the-one` (outside `/tmp`) ensures `_PROJECT_ROOT` resolves to a path that is
visible inside the sandbox, reproducing the GitHub Actions `/home/runner/work/...`
condition. The venv is built by `uv sync --locked` inside `/opt/the-one` (`/opt/the-one/.venv`), so
the editable install points there, for the same reason.

### Windows-worker quirks

The Concourse Windows worker runs **PowerShell** under the **system account**:

1. **No Git-Bash on PATH.** GitHub Actions Windows runners use `shell: bash` (Git-Bash),
   which provides POSIX tools (`true`, `sleep`, etc.) and sets `HOME`. The
   `windows-tests.yml` task compensates by prepending
   `C:\Program Files\Git\usr\bin` to `PATH` and setting `HOME=$USERPROFILE` explicitly.

2. **System-account path-case mismatch.** `test_build_tool_profile_default_allowlist`
   is `--deselect`'d on the Concourse Windows lane. The Concourse worker runs as the
   system account, where `Path("~").expanduser()` returns a lowercase `system32` path
   (from `USERPROFILE`) but `Path.resolve()` returns the NTFS-canonical uppercase
   `System32`. The test compares the two; they agree on a user account (as on GitHub
   Actions) but not on the system account. This is a worker-environment artifact, not
   a Windows-behavior or logic gap. The same test runs and passes on the linux `test`
   lane (full suite, 3178 passed).

### Post-merge verification + windows-installer teardown

Once the flight PR merges to `main` (the commit carries `ci/tasks/*` +
`ci/the-one.pipeline.yml`):

1. The `the-one/ci` job auto-triggers on the merge commit → confirm it goes **green**
   across all five tasks (lint / test / browser / windows-tests / bwrap).
2. `build-windows-installer` auto-runs (`passed: [ci]`) → confirm the `.exe` lands in
   MinIO (`the-one-installers`).
3. **Destroy the paused `windows-installer` pipeline** so only the unified pipeline
   auto-builds on `main`:
   ```bash
   fly -t the-one destroy-pipeline -p windows-installer -n
   ```
4. If the `ci` build is red post-merge, the paused `windows-installer` pipeline is the
   rollback (unpause it) while the unified pipeline is fixed:
   ```bash
   fly -t the-one unpause-pipeline -p windows-installer
   ```
