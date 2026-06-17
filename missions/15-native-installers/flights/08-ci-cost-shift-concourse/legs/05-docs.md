# Leg: docs

**Status**: completed
**Flight**: [CI cost-shift — move day-to-day CI to local Concourse](../flight.md)

## Objective

Document the new CI topology: author `ci/README.md` (what-runs-where, the pre-push `fly execute`
gate, on-demand installer builds, Vault/team-secret + windows-worker notes, the MinIO
external-DNS-by-IP gotcha) and update the stale CI references in `CLAUDE.md` / `the_one/agents.md`
so they describe Concourse-primary CI rather than GitHub Actions.

## Context

- **Goldfinch `~/projects/goldfinch/ci/README.md` is the template** — but the-one differs in
  specifics that MUST be reflected accurately (do not copy goldfinch's values blindly):
  - Team / fly target / pipeline are all **`the-one`**; UI at
    `http://localhost:8080/teams/the-one/pipelines/the-one`.
  - **5 CI lanes** in the `ci` job: `lint`, `test`, `browser`, `windows-tests`, `bwrap` — the
    `bwrap` task step runs **`privileged: true`** (worker blocks unprivileged userns; Leg 1).
  - `build-windows-installer` is **auto-on-`main`** (`trigger: true` + `passed: [ci]`) — NOT manual
    like goldfinch's build jobs — reusing `windows-installer-build.yml` + an **inline `minio/mc`
    publish task** (NOT an s3 resource).
  - **MinIO**: because the-one publishes via the inline `mc` task, `((minio.endpoint))` is a **bare
    `host:port`** (`172.19.0.5:9000`, no `http://`) — the task builds the `http://…` URL itself.
    (This is the OPPOSITE of goldfinch's s3-resource requirement for a full-URL endpoint — call out
    the difference so a reader doesn't "fix" it.) The IP-not-`minio`-service-name gotcha still
    applies (Concourse task containers use external DNS).
  - **Secrets are team-level** at `concourse/the-one/{github-deploy-key,minio}` (promoted in Leg 3
    from the `windows-installer/*` paths; originals left in place). Vault is in-memory →
    reseeded from `concourse-local/.vault-seeds.json` (already contains the team-level entries).
  - **Windows-worker quirks (Leg 2):** the Concourse windows worker runs PowerShell with no
    Git-Bash on PATH (so `windows-tests.yml` prepends `C:\Program Files\Git\usr\bin` + sets
    `HOME=$USERPROFILE`), and runs as the **system account** (so
    `test_build_tool_profile_default_allowlist` is `--deselect`'d — a path-case artifact, not a
    real failure; still covered on the linux `test` lane).
  - **bwrap relocation (Leg 2):** `bwrap.yml` copies the checkout to `/opt/the-one` before running,
    because the Concourse workspace is under `/tmp` which bwrap's `--tmpfs /tmp` shadows.
- **Pre-push gate**: `fly -t the-one execute -c ci/tasks/<x>.yml -i repo=.` (the **bwrap** lane needs
  `-p`: `fly -t the-one execute -p -c ci/tasks/bwrap.yml -i repo=.`). `-i repo=.` uploads the
  **working tree** (NOT gitignore-aware) — advise a clean tree (no stray `.venv/`/`dist/`).
- **Stale doc references to fix** (found by FD grep):
  - `CLAUDE.md:40` — "The same `ruff check …` run in CI (`.github/workflows/lint.yml`) on every PR
    and on pushes to `main`." → now lint runs on **Concourse**; the GH `lint.yml` is dispatch-only.
  - `CLAUDE.md:176` — "(Inside CI … the `test.yml` jobs call `python -m pytest` directly …)" → CI is
    now Concourse (`ci/tasks/*` run bare pytest in ephemeral task containers); the GH `test.yml` is a
    dispatch-only break-glass. Keep the ephemeral-runner rationale, repoint it at Concourse.
  - Check `the_one/agents.md` for CI/operator-workflow references that name GitHub Actions and
    update them too.
- **DD5 note for the README**: on Concourse the full browser suite runs on **every** `main` push
  (no path-filter, no release-gated tier — that rationing only existed for Actions minutes).

## Inputs

- Legs 1-4 landed: `ci/tasks/*`, `ci/the-one.pipeline.yml`, `ci/set-pipeline.sh` exist; GH workflows
  cut over; the unified pipeline is live (Leg 3 flight-log entry has the exact state + secret paths).

## Outputs

- `ci/README.md` — new (the-one-accurate, modeled on goldfinch).
- `CLAUDE.md` — CI references updated (lines ~40, ~176) + a pointer to `ci/README.md`.
- `the_one/agents.md` — any CI references updated (if present).

## Acceptance Criteria

- [x] `ci/README.md` exists with: (1) a **what-runs-where** table (the 5 CI lanes + their task
      files + their old GH-Actions equivalent; the installer build); (2) the **pre-push `fly execute`
      gate** (incl. the bwrap `-p` caveat and the working-tree-upload note); (3) **auto-CI on `main`**
      (the `ci` job, `trigger: true`); (4) **on-demand installer** (`fly trigger-job -j
      the-one/build-windows-installer` and/or ad-hoc `fly execute`); (5) **Vault/secrets** (team-level
      paths, in-memory reseed, the bare-`host:port` MinIO endpoint + IP-not-service-name gotcha, with
      the explicit note that the-one uses the inline `mc` task so a full-URL endpoint is NOT wanted);
      (6) the **windows-worker quirks** + **bwrap relocation/privileged** notes.
- [x] `CLAUDE.md` no longer claims lint/test run on GitHub Actions per-PR; it points to `ci/README.md`
      for the CI topology and notes the GH workflows are dispatch-only break-glass.
- [x] `the_one/agents.md` CI references (if any) updated to match.
- [x] No invented facts — every claim matches the actual `ci/` files + the Leg 3 live state. Cross-
      check against the real files, not memory.

## Verification Steps

- `ci/README.md` renders as valid Markdown; its task-file names, secret paths, fly target, and the
  MinIO endpoint detail match `ci/the-one.pipeline.yml` + `ci/tasks/*` + the flight log exactly.
- `grep -rniE "github actions|\.github/workflows/(lint|test)" CLAUDE.md the_one/agents.md` shows no
  remaining claim that routine lint/test run on Actions (only the dispatch-only/break-glass framing).
- `git diff` is docs-only (`ci/README.md`, `CLAUDE.md`, `the_one/agents.md`).

## Implementation Guidance

1. Author `ci/README.md` from the goldfinch template, substituting the-one specifics from Context
   (5 lanes, privileged bwrap, inline-mc MinIO with bare-host:port endpoint, team-level secrets,
   windows-worker quirks, bwrap `/opt/the-one` relocation, DD5 full-browser-on-main, post-merge
   `windows-installer` teardown). Include the **post-merge verification** (first green `ci` on main +
   installer to MinIO, then destroy the paused `windows-installer` pipeline) so the README is the
   single source of truth for finishing the cutover.
2. Edit `CLAUDE.md:40` and `CLAUDE.md:176` to repoint at Concourse (+ a one-line "CI runs on local
   Concourse — see `ci/README.md`" pointer near the test/lint guidance). Preserve the surrounding
   rationale; change only the now-false "runs on GitHub Actions per PR/push" claims.
3. Grep `the_one/agents.md` for CI / GitHub-Actions references and update any that are now false.
4. Keep all edits **docs-only** — no code, no workflow, no pipeline changes in this leg.

## Edge Cases

- **Don't contradict the still-true bits**: the GH workflows still EXIST (break-glass, dispatch-only)
  and `windows-installer.yml` (the `v*` release) is still the live release path — say "dispatch-only
  fallback," not "deleted."
- **MinIO endpoint**: do NOT document the goldfinch "endpoint must be a full URL" rule — the-one's
  inline `mc` task wants the bare `host:port`. Documenting the wrong rule would cause a future
  "fix" that breaks publish.
- **Pixel/marker exclusions** (`CLAUDE.md:188`, `pyproject.toml addopts`) are marker-based and apply
  equally on Concourse — no change needed there; don't churn it.

## Files Affected

- `ci/README.md` — new.
- `CLAUDE.md` — CI references updated.
- `the_one/agents.md` — CI references updated (if present).
- `missions/.../flight-log.md` — leg progress entry.

---

## Post-Completion Checklist

- [x] `ci/README.md` authored, accurate against the real `ci/` files + Leg 3 live state
- [x] `CLAUDE.md` + `the_one/agents.md` CI references corrected; pointer to `ci/README.md` added
- [x] `git diff` is docs-only
- [x] Flight log updated with the leg progress entry
- [x] Set this leg's status to `landed` (commit deferred to end-of-flight batch)
