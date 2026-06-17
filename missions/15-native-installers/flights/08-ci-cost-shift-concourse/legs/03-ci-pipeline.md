# Leg: ci-pipeline

**Status**: completed
**Flight**: [CI cost-shift — move day-to-day CI to local Concourse](../flight.md)

## Objective

Wire the five `ci/tasks/*.yml` (Leg 2) into a single unified **`the-one`** Concourse pipeline
— a `ci` job (git on `main`, `trigger: true`, `in_parallel` over the tasks, `fail_fast: false`)
plus a `build-windows-installer` job (`passed: [ci]`, reusing `windows-installer-build.yml`
unchanged) — with team-level Vault secrets so it resolves the git key + MinIO creds, then cut
over reversibly (pause, don't destroy, the live `windows-installer` pipeline) leaving the live
green-build-on-main + old-pipeline teardown as documented post-merge verification.

## Context

- **Goldfinch is the template** (`~/projects/goldfinch/ci/pipeline.yml` + `set-pipeline.sh`):
  a `git` resource on `main` with `private_key: ((git-key.private_key))`, a `ci` job
  (`get: repo, trigger: true` → `in_parallel { fail_fast: false }` over `repo/ci/tasks/<x>.yml`),
  and build job(s) gated `passed: [ci]` that `put` to an `s3` (MinIO) resource.
- **DD6 — one unified `the-one` pipeline.** Replaces the standalone `windows-installer` pipeline.
- **Two pre-existing pipelines on the team (FD recon — flight log):**
  - **`the-one` (id 15)** is a **stale Docker-era** deploy/test/rollback pipeline (runs the suite
    via `docker run … playwright/python` against `((docker-host))`; last build `deploy/19` on
    **2026-04-23**, dormant ~2 months, predates F1's Docker retirement). Setting the unified
    pipeline under the name `the-one` **overwrites this dead pipeline** — desirable cleanup.
    Confirm no recent activity before overwriting (already true: nothing since 2026-04-23).
  - **`windows-installer` (id 17)** is the **live** installer pipeline (build #23 today). It is
    **paused** (not destroyed) during this leg, and torn down post-merge once the unified
    pipeline proves green (avoids destroying a working pipeline before its replacement is proven,
    and avoids a post-merge double-build of the installer).
- **DD6 — team-level Vault secrets.** The existing pipeline references **two** Vault secrets,
  `((github-deploy-key.private_key))` and `((minio.{access_key,secret_key,endpoint,bucket}))`,
  currently at `concourse/the-one/windows-installer/{github-deploy-key,minio}`. A pipeline named
  `the-one` resolves `((x))` from `concourse/the-one/the-one/x` then team-level `concourse/the-one/x`
  — **not** the `windows-installer`-scoped path. So the two secrets must be **promoted to
  team-level** (`concourse/the-one/github-deploy-key`, `concourse/the-one/minio`) — the only option
  under which both the old and new pipelines resolve simultaneously (no dead window during cutover).
  **Keep the secret NAMES identical** (`github-deploy-key`, `minio`) — the new pipeline uses
  `((github-deploy-key.private_key))`, NOT goldfinch's `((git-key.private_key))`; a rename would
  break the still-live `windows-installer` pipeline mid-cutover. Promotion is a path move only.
  `concourse-local/.vault-seeds.json` must also be updated **before the in-memory dev Vault next
  restarts**, or the unified pipeline silently loses its git key (goldfinch's hard-won lesson) —
  use the goldfinch README's `node -e` seed-update snippet, adjusted to the team-level paths.
- **Privilege:** the `bwrap` task step in the `ci` job MUST carry `privileged: true` (Leg-1 GREEN:
  the worker blocks unprivileged userns). The other task steps are unprivileged.
- **Sensitive-step boundary:** Vault secret promotion + the `.vault-seeds.json` edit are
  **credential operations on shared infra and a *different* repo (`concourse-local`)**. These,
  plus the live pipeline mutations (overwrite stale `the-one`, pause `windows-installer`), are
  gated behind an **operator checkpoint** — the Flight Director presents the exact commands and
  the operator authorizes/performs them. The committable artifacts (pipeline YAML + helper) are
  authored autonomously first.
- **Commit-timing reality:** the `git` resource pulls *pushed* refs, and this flight batches its
  commit at the end (files not yet on `main` or a pushed branch). So a *live green `ci` build*
  cannot be produced during this leg — it is **post-merge** verification, exactly as the flight's
  own Verification section frames it ("push a trivial commit to main → the `ci` job runs green").
  This leg's success = pipeline set + secrets resolvable + old pipeline paused + config validated.

## Inputs

- Leg 2 landed: `ci/tasks/{lint,test,browser,windows-tests,bwrap}.yml` exist and are green standalone.
- `fly -t the-one` session valid; linux + windows workers up.
- Existing `ci/tasks/windows-installer-build.yml` (reused unchanged) + Vault secrets at
  `concourse/the-one/windows-installer/*`.

## Outputs

- `ci/the-one.pipeline.yml` — the unified pipeline (committed; one git resource, inline MinIO publish).
- `ci/set-pipeline.sh` — goldfinch-parity helper (committed).
- Vault secrets `github-deploy-key` + `minio` promoted to team-level `concourse/the-one/*` (live
  infra; originals left in place; operator-authorized).
- `concourse-local/.vault-seeds.json` updated to persist them (different repo; operator-authorized).
- Live state: unified `the-one` pipeline **set + unpaused**; `windows-installer` pipeline **paused**.
- *(post-merge, documented not done here)*: first green `ci` build on `main`, installer to MinIO,
  then destroy the paused `windows-installer` pipeline.

## Acceptance Criteria

- [x] `ci/the-one.pipeline.yml` authored on the goldfinch template: a `git` resource on `main`
      (`((github-deploy-key.private_key))` — the existing name), a `ci` job
      (`get: repo, trigger: true` → `in_parallel { fail_fast: false }` over the 5 task files), and
      a `build-windows-installer` job (`get: repo, trigger: true, passed: [ci]` → `task: build file:
      repo/ci/tasks/windows-installer-build.yml` unchanged → an **inline `minio/mc` publish-to-minio
      task** copied verbatim from `windows-installer.pipeline.yml`, NOT an `s3` put resource). The
      `bwrap` task step carries `privileged: true` (with an explanatory comment).
- [x] `fly -t the-one validate-pipeline -c ci/the-one.pipeline.yml` passes (config valid).
- [x] `ci/set-pipeline.sh` mirrors goldfinch (wraps `fly set-pipeline -p the-one`, no secrets in-file).
- [x] **(operator-authorized)** Vault secrets resolvable at team-level `concourse/the-one/*`; the
      `the-one` pipeline's `repo` resource checks successfully (git key resolves) after set+unpause.
- [x] **(operator-authorized)** `concourse-local/.vault-seeds.json` updated with the team-level
      entries (persists across the in-memory Vault restart).
- [x] **(operator-authorized)** The unified `the-one` pipeline is **set + unpaused** (overwriting
      the stale id-15 Docker pipeline — confirmed dormant since 2026-04-23); the `windows-installer`
      pipeline is **paused**.
- [x] The post-merge verification + old-pipeline teardown are recorded in the flight log as
      explicit post-landing steps (not silently dropped).

## Verification Steps

- `fly -t the-one validate-pipeline -c ci/the-one.pipeline.yml` → ok.
- After set+unpause: `fly -t the-one pipelines` shows `the-one` unpaused and `windows-installer`
  paused; `fly -t the-one check-resource -r the-one/repo` succeeds (git key resolves from the
  promoted team-level secret).
- `fly -t the-one get-pipeline -p the-one` shows the unified CI config (not the old Docker jobs).
- The flight log documents: post-merge → `ci` green on main + installer in MinIO → destroy `windows-installer`.

## Implementation Guidance

**Phase A — author artifacts (autonomous):**
1. Write `ci/the-one.pipeline.yml`. **One resource**: `repo` git on `main` with
   `private_key: ((github-deploy-key.private_key))` (the existing secret name — do NOT use
   goldfinch's `git-key`). **No `s3` resource** — the existing `minio.endpoint` Vault value is a
   bare `host:port` (no `http://`), which an `s3` resource rejects; the inline `minio/mc` task
   builds the URL itself and works as-is, so reuse it. Jobs: `ci` (`get: repo trigger:true` →
   `in_parallel {fail_fast:false}` over `repo/ci/tasks/{lint,test,browser,windows-tests,bwrap}.yml`;
   **`bwrap` step gets `privileged: true`** + a `# bwrap: privileged required — see ci/tasks/bwrap.yml`
   comment), and `build-windows-installer` (`get: repo, trigger: true, passed: [ci]` → `task: build
   file: repo/ci/tasks/windows-installer-build.yml` (unchanged) → the **inline `publish-to-minio`
   task** copied verbatim from `windows-installer.pipeline.yml` (`minio/mc` image, `MC_HOST_minio`
   from `((minio.*))`, `mc cp installer/the-one-setup-*.exe`)). `trigger: true` on the build job's
   `get: repo` preserves DD3 auto-on-main. Header comment per goldfinch convention.
2. Write `ci/set-pipeline.sh` (copy goldfinch's; `TARGET=the-one`, `PIPELINE=the-one`, `-c ci/the-one.pipeline.yml`).
3. `fly -t the-one validate-pipeline -c ci/the-one.pipeline.yml`.

**Phase B — operator checkpoint (credential + cutover; presented by the FD, operator authorizes):**
4. Promote the **two** secrets (`github-deploy-key`, and the single `minio` kv with its four fields)
   from `concourse/the-one/windows-installer/{github-deploy-key,minio}` to team-level
   `concourse/the-one/{github-deploy-key,minio}` (leave the originals in place so the still-live
   `windows-installer` pipeline keeps resolving — no rename, no dead window). Update
   `concourse-local/.vault-seeds.json` with the same two team-level entries (before the next Vault
   restart), using the goldfinch README's seed-update snippet adjusted to these paths.
5. `bash ci/set-pipeline.sh --non-interactive` (overwrites the stale id-15 `the-one` pipeline) then
   `fly -t the-one unpause-pipeline -p the-one`.
6. `fly -t the-one check-resource -r the-one/repo` → confirms the git key resolves.
7. `fly -t the-one pause-pipeline -p windows-installer` (reversible; prevents post-merge double-build).
8. Record the post-merge steps in the flight log.

## Edge Cases

- **Stale `the-one` overwrite**: confirm no builds since 2026-04-23 before `set-pipeline` clobbers
  it. If it has unexpectedly run recently, STOP and escalate (someone may depend on the deploy job).
- **Secret resolution failure** after set+unpause (`check-resource` red): the promotion didn't take
  or the seed/path is wrong — fix before pausing the old pipeline (keep the working pipeline live
  until the new one's resource checks green). This is the DD6 "no dead window" guarantee in action.
- **Vault restart between set and seed-update**: update `.vault-seeds.json` promptly; an in-memory
  dev-Vault restart wipes live-set secrets (goldfinch README lesson).
- **Don't destroy `windows-installer` this leg**: pause only. Destruction is post-merge-after-green
  (the spec's "destroy once unified is green" — green is a post-merge condition here).
- **`fly set-pipeline` validates YAML but does NOT fetch `repo/ci/tasks/*` at set time** — they
  resolve at *build* time, so setting succeeds even though the tasks aren't on `main` yet. The first
  build (post-merge) is what exercises them.

## Files Affected

- `ci/the-one.pipeline.yml`, `ci/set-pipeline.sh` — new (committed).
- `~/projects/concourse-local/.vault-seeds.json` — updated (separate repo; operator-authorized;
  committed in concourse-local, not in this flight's commit).
- `missions/.../flight-log.md` — leg progress + post-merge verification steps.
- Live Concourse/Vault state (not files): secrets promoted; `the-one` set+unpaused; `windows-installer` paused.

---

## Post-Completion Checklist

- [x] `ci/the-one.pipeline.yml` + `ci/set-pipeline.sh` authored; `validate-pipeline` passes
- [x] (operator-authorized) secrets promoted team-level + `.vault-seeds.json` updated
- [x] (operator-authorized) `the-one` set+unpaused (stale pipeline overwritten); `windows-installer` paused
- [x] `check-resource -r the-one/repo` green (git key resolves)
- [x] Post-merge verification + `windows-installer` teardown recorded in the flight log
- [x] Set this leg's status to `landed` (commit deferred to end-of-flight batch)
