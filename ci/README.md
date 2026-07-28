# the-one CI on local Concourse

CI runs on the **local Concourse** instance (`http://localhost:8080`, team `the-one`)
instead of GitHub Actions, to conserve GitHub Actions minutes. GitHub Actions
`lint.yml` and `test.yml` are disabled (manual `workflow_dispatch` only — break-glass
fallback). `windows-installer.yml` (the `v*`-tag release path) is **untouched** and
still owns official releases.

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
| Browser tests (Playwright) | `ci/tasks/browser.yml` | "browser" job (`test.yml`) |
| Windows curated subset (~427 tests) | `ci/tasks/windows-tests.yml` | "windows" job (`test.yml`) |
| bwrap sandbox tests (privileged) | `ci/tasks/bwrap.yml` | "bwrap" job (`test.yml`) |
| Windows installer build + MinIO publish | `build-windows-installer` job (pipeline) | `windows-installer.yml` (v\* tag only) |

All five CI lanes run in parallel (`in_parallel`, `fail_fast: false`) as a single `ci`
job. The browser lane is the long pole (~9 min on Concourse, vs ~15 min on GH shared
runners). On Concourse the full browser suite runs on **every push to `main`** — the
path-filter that rationed it on GitHub Actions (minutes cost) is gone (DD5). None of
these five lanes run on GitHub Actions PR triggers — `pr-lint.yml` (lint + pip-audit
only) is the only pre-merge GH Actions gate; the heavy lanes stay post-merge on
Concourse.

## Pre-merge lint + audit gate

`.github/workflows/pr-lint.yml` triggers `on: pull_request` (branches: `[main]`) and
runs two jobs, both fail-on-nonzero:

- **lint** — `ruff check the_one/ tests/` + `ruff format --check the_one/ tests/`,
  pinned to the same `ruff==0.15.15` version as `ci/tasks/lint.yml` (parity with the
  Concourse lane).
- **pip-audit** — audits the **release dependency closure**: `uv export --no-dev
  --no-emit-project --extra gui --extra all-llms --format requirements-txt` (the
  closure the Windows installer actually ships — `windows-installer.yml` installs
  `.[gui,all-llms]`; excludes dev/toolchain deps and the editable self-entry) fed to
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
**use a clean tree** (no stray `.venv/`, `dist/`, `build/` directories) to avoid
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

The `ci` job has a `git` resource on `main` (`trigger: true`) and runs all five lanes
in parallel. Watch it at `http://localhost:8080/teams/the-one/pipelines/the-one`.

The `build-windows-installer` job auto-triggers after `ci` passes (`trigger: true` +
`passed: [ci]`) — so a successful CI run on `main` automatically builds and publishes
the installer to MinIO.

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
> Vault value is `172.19.0.5:9000` (no `http://`). The inline `minio/mc` publish
> task builds the URL itself: `MC_HOST_minio="http://${MINIO_KEY}:${MINIO_SECRET}@${MINIO_ENDPOINT}"`.
> Do NOT add `http://` to the Vault value — the task would produce a double-scheme
> URL (`http://http://...`) and fail to connect.
>
> **(Note for readers coming from goldfinch)**: goldfinch uses an `s3` resource
> which requires a full-URL endpoint. The-one uses the inline `mc` task instead, so
> the rule is the OPPOSITE — bare `host:port` is correct here.

> **IP, not the compose service name.** Concourse task containers use external DNS
> (8.8.8.8) and are NOT on the compose network, so `minio` does not resolve inside
> them. Use the compose-network IP (`172.19.0.5`, or whatever `docker inspect` reports
> for the minio container). If `docker compose down/up` reassigns the IP, update the
> Vault value:
>
> ```bash
> # Via MCP:
> # set_secret concourse/the-one/minio endpoint=<new-ip:9000>
>
> # Via fly:
> # fly -t the-one set-team ... (or edit .vault-seeds.json and reseed)
> ```

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
condition. The venv is also installed at `/opt/venv` (not in the repo input) for the
same reason.

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
   across all five lanes (lint / test / browser / windows-tests / bwrap).
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
