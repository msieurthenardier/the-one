# Flight: CI cost-shift — move day-to-day CI to local Concourse

**Status**: completed
**Mission**: [Native Desktop Installers](../../mission.md)

> **Reframes the placeholder Flight 8 ("Windows release pipeline (CI/CD)").** The
> tag-driven Windows release already shipped in F5 (`windows-installer.yml` builds the
> Inno installer → GitHub Release on a `v*` tag) and works. So the *release-pipeline*
> half of the old F8 is done. What remains — and what this flight does — is the **cost**
> problem: the project has **exhausted its GitHub Actions minutes**, and the day-to-day
> test/lint/browser/windows CI (which runs on every PR and main push) is the consumer.
> This flight moves that routine CI to the **local Concourse `the-one` team** (free,
> self-hosted) and finalizes the GitHub side as **release-only** (the `v*`-tag installer
> workflow), reserving the remaining/restored Actions minutes for official builds. The
> old F8 "full browser suite as a release-gated tier" idea is **superseded** — see DD5.

## Contributing to Criteria
- [ ] The app builds, runs, and is **tested host-natively in CI**; the developer `pip`
      install path remains supported and the existing test suite passes. *(This flight
      keeps that CI green while relocating it from GitHub Actions to local Concourse — the
      product's Docker-independence is unchanged; only the CI host moves.)*
- [ ] Pushing a release tag causes the Windows installer to be **built automatically and
      published** as a downloadable release artifact. *(This flight protects that criterion
      by reserving Actions minutes for the tag-release path and leaving `windows-installer.yml`
      as the sole active GitHub workflow.)*

---

## Pre-Flight

### Objective

Shift the routine CI suite (lint, full pytest suite, browser tests, the Windows-relevant
test subset, and — spike permitting — the kernel-enforced `requires_bwrap` lane) from
GitHub Actions to the local Concourse `the-one` team, so PRs and main pushes no longer
consume GitHub Actions minutes. Mirror the proven **goldfinch** model: a Concourse `ci`
job auto-runs on every push to `main`; per-PR gating is a documented **pre-push
`fly execute -c ci/tasks/<x>.yml -i repo=.`** against the working tree (no per-PR
automation, no `github-pr-resource`). GitHub Actions retains **only** the `v*`-tag
Windows release workflow. The existing Concourse `windows-installer` build stays
auto-on-`main`; ad-hoc installer builds (e.g. from a PR branch) are manual/on-demand.

### Open Questions
- [x] How does Concourse observe PRs / report status? → **DD1** (goldfinch push-to-main
      model; pre-push `fly execute`; no PR resource).
- [x] How aggressive should installer builds on PRs be? → **DD3** (manual/on-demand for
      branches; auto-on-`main` preserved).
- [x] Can a Concourse worker run the kernel-enforced `requires_bwrap` lane? → **DD4**
      (spike-gated — Leg 1 decides; fall back to keeping that one job on Actions).
- [x] Where do the new pipeline's Vault secrets (git deploy key, MinIO creds) live —
      reuse the existing `windows-installer` pipeline path, promote to team-level, or
      re-seed under a unified pipeline name? → resolved in Leg 3 (see Prerequisites).

### Design Decisions

**DD1 — PR observation: goldfinch push-to-main model (no PR resource).**
- Choice: The Concourse `ci` job's `git` resource tracks `main` with `trigger: true` and
  runs automatically on every push to `main`. Per-PR gating is the developer running
  `fly -t the-one execute -c ci/tasks/<x>.yml -i repo=.` against the working tree before
  pushing. No `github-pr-resource`, no GitHub status callbacks.
- Rationale: Identical to the model the operator already ran successfully in goldfinch;
  zero new resource-type dependency; zero GitHub coupling (no token, no API calls). The
  whole point is to *stop* touching GitHub for routine CI.
- Trade-off: No automatic ✅/❌ check in the GitHub PR UI; the per-PR gate is a manual
  pre-push step the developer must remember. Accepted (operator decision 2026-06-17).

**DD2 — GitHub Actions retention: release-only.**
- Choice: Disable the `pull_request` + `push: main` triggers on `lint.yml` and `test.yml`
  by converting them to `workflow_dispatch`-only (manual fallback, kept on disk and
  correct so they can be re-enabled or run by hand if Concourse is down). Leave
  `windows-installer.yml` (the `v*`-tag release) **untouched** — it is the sole
  auto-active GitHub workflow.
- Rationale: Mirrors goldfinch's treatment of `ci.yml`. Keeping the workflows as
  manual-dispatch fallbacks (rather than deleting them) preserves a break-glass path and
  the documented test inventory.
- Trade-off: The workflows linger as dead-on-arrival-until-dispatched files; a reader must
  understand they're intentionally trigger-disabled (a header comment will say so).

**DD3 — Installer builds: auto-on-`main` preserved, manual/on-demand for branches.**
- Choice: The Windows installer continues to build automatically on every push to `main`
  (today's `windows-installer.pipeline.yml` behavior), now expressed as a
  `build-windows-installer` job gated `passed: [ci]` so it only freezes a commit that
  passed the suite. Ad-hoc installer builds from a PR branch / working tree are
  **manual**: `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out`
  (or `fly trigger-job`). No auto-build on every PR push.
- Rationale: Honors the operator's original "installers … on main" (keep auto-on-main)
  and the "manual / on-demand" answer for the PR case (don't tie up the single Windows
  worker freezing every PR commit ~10 min). Gating on `passed: [ci]` means main never
  freezes a red commit.
- Trade-off: An installer from an in-flight PR branch requires a deliberate manual step.
  Accepted (operator decision 2026-06-17).

**DD4 — `requires_bwrap` lane: spike-gated port (Leg 1 decides).**
- Choice: Before wiring the bwrap lane into the Concourse `ci` job, **Leg 1 runs a
  throwaway `fly execute` spike** to confirm a Concourse worker can run *kernel-enforced*
  bwrap (privileged container / unprivileged-userns available; `-m requires_bwrap` passes
  with real containment, not graceful-degrade passthrough). If the spike is **green**, the
  bwrap lane moves to Concourse (`ci/tasks/bwrap.yml`); if **red**, the single `bwrap` job
  **stays on GitHub Actions** (a cheap 1× ubuntu job) and `test.yml` is trimmed to that
  job only.
- Rationale: Directly applies the **F7 debrief's top lesson** — *a real-environment spike
  must exercise the exact runtime surface the design depends on, and run **before** the
  dependent leg, not be discovered at integration*. bwrap-on-a-CI-worker is precisely an
  unverified-runtime premise (Concourse worker container privilege + AppArmor
  `kernel.apparmor_restrict_unprivileged_userns` posture are not knowable from a config
  read).
- Trade-off: If the spike fails, "move *all* CI off Actions" is not fully achieved — one
  1× ubuntu job remains. Acceptable: the goal is conserving minutes, and that lone job is
  the cheapest tier; the heavy consumers (full suite, ~15-min browser, 2× Windows subset)
  all move regardless.

**DD5 — Browser suite: run the full suite on `main`, drop the path-filter tier.**
- Choice: On Concourse the full browser suite (`-m browser tests/browser/`, ~15 min, the
  current CI long pole) runs as a task in the `ci` job on **every** push to `main` — no
  path-filter, no separate "release-gated tier."
- Rationale: The GitHub `test.yml` path-filter (`^(the_one/interfaces/web/|tests/browser/|pyproject\.toml$)`)
  and the old F8
  "browser-as-release-tier" idea both existed **solely to ration Actions minutes**. On
  free self-hosted Concourse that rationale evaporates: run the full suite every main
  push, get full signal, delete the path-filter complexity. This **supersedes** the
  placeholder F8 release-gated-browser-tier intent.
- Trade-off: Each main push spends ~15 min of the shared home-Concourse Windows/linux
  worker time. Main pushes are post-merge (infrequent) and PRs don't trigger Concourse
  (DD1), so contention with other teams (goldfinch/epipen) on the shared instance is
  bounded. Browser provisioning (`playwright install --with-deps chromium`) runs as root
  in the debian-based `python:3.11` task image.

**DD6 — Unify into one Concourse pipeline (goldfinch parity).**
- Choice: Replace the standalone `windows-installer` pipeline with a single `the-one`
  pipeline holding: a `ci` job (in-parallel lint/test/browser/windows-subset[/bwrap]) and
  a `build-windows-installer` job (`passed: [ci]`). One pipeline = one place to look,
  matching goldfinch's `ci`+`build-*` shape.
- Rationale: Single source of truth; the installer build gates on the same `ci` that
  gates everything else.
- Trade-off: Vault secret paths are pipeline-name-scoped. **Default: promote the git-key
  and MinIO secrets to team-level (`concourse/the-one/*`)** — it is the only option under
  which *both* the old `windows-installer` pipeline and the new unified pipeline resolve
  their secrets simultaneously, so there is no dead window during cutover (re-seeding under
  a new pipeline name breaks the old pipeline's `concourse/the-one/windows-installer/*`
  references the moment it's renamed). Either way the `concourse-local` `.vault-seeds.json`
  **must be updated before the in-memory dev Vault next restarts** (the goldfinch README's
  hard-won lesson: live secrets are lost on restart unless seeded). Handled in Leg 3. If
  unifying proves fiddly, the fallback is keeping two pipelines (existing `windows-installer`
  untouched + a new `ci` pipeline) — same outcome, two dashboards.

### Prerequisites
- [x] Concourse `the-one` team reachable and a current `fly -t the-one login` session
      (the F7 run hit an expired session → MCP/team context dropped to `main`).
- [x] A **linux** Concourse worker (for lint/test/browser/bwrap tasks) and the existing
      **windows** worker (already used by `windows-installer-build.yml`) are available on
      the shared `concourse-local` instance.
- [x] Vault secrets resolvable by the unified pipeline: the read-only git deploy key and
      MinIO creds — currently at `concourse/the-one/windows-installer/*`. **Default: promote
      to team-level `concourse/the-one/*`** (lets the old and new pipelines coexist during
      cutover — see DD6); **also update `concourse-local/.vault-seeds.json`** *before* the
      in-memory Vault next restarts, or the unified pipeline silently loses its git key.
- [x] `the_one` installs cleanly on a stock `python:3.11` image via
      `pip install -e ".[all-llms,dev]"` (+ `[gui]` only where a task needs it) — verified
      per-task by `fly execute` in Leg 2 before any pipeline wiring.

### Pre-Flight Checklist
- [x] All open questions resolved (the Vault-path question resolves in Leg 3)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Port each GitHub Actions job to a standalone Concourse **task file** under `ci/tasks/`
(the goldfinch pattern: each task is independently runnable via
`fly execute -c ci/tasks/<x>.yml -i repo=.`, and also referenced as a task in the
pipeline). Linux tasks use a `python:3.11` `registry-image` and `pip install -e
".[all-llms,dev]"`; the browser task adds `playwright install --with-deps chromium`; the
Windows-subset task runs on the `platform: windows` worker via choco `python311` (reusing
the `windows-installer-build.yml` toolchain pattern). Tasks run **bare `python -m pytest`**
(not the local group-kill wrapper) — Concourse task containers are ephemeral per build, so
orphaned uvicorn/Chromium children die with the container, exactly as the GitHub `test.yml`
header documents for ephemeral runners.

A single Concourse pipeline (`the-one`) wires a `ci` job (git resource on `main`,
`trigger: true`, `in_parallel` over the task files, `fail_fast: false` so one red task
doesn't mask others) plus a `build-windows-installer` job (`passed: [ci]`, folding in the
existing `windows-installer-build.yml` task → MinIO `put`). The GitHub side is then cut
over: `lint.yml`/`test.yml` → `workflow_dispatch`-only; `windows-installer.yml` left
intact. Finally a `ci/README.md` documents what-runs-where, the pre-push `fly execute`
gate, the on-demand installer build, and the Vault/secrets/worker notes (goldfinch README
as the template).

### Checkpoints
- [x] **Leg 1 spike result recorded** in the flight log: kernel-enforced bwrap on a
      Concourse worker is GREEN (port it) or RED (keep on Actions).
- [x] Every `ci/tasks/<x>.yml` passes standalone via `fly execute -i repo=.` against the
      current working tree.
- [ ] The `the-one` pipeline is set + unpaused; a real `ci` build (triggered by a push to
      `main` or a manual run) goes **green** end-to-end.
- [ ] `build-windows-installer` produces an installer and publishes it to MinIO,
      `passed: [ci]`; the old standalone `windows-installer` pipeline is **destroyed** (no
      double auto-build on `main`).
- [ ] Opening/updating a PR triggers **no** `lint`/`test` (full-suite) GitHub Actions runs
      (the single `bwrap` job may remain on the RED path); a `v*` tag still triggers
      `windows-installer.yml`.
- [x] `ci/README.md` documents the pre-push `fly execute` gate and on-demand installer.

### Adaptation Criteria

**Divert if**:
- The Leg 1 bwrap spike is red **and** the operator wants kernel-enforced bwrap fully off
  Actions anyway → escalate (options: provision a privileged/dedicated bwrap worker, or
  accept the documented gap of skipping kernel-enforced bwrap in CI).
- A Concourse worker cannot install/run the suite on `python:3.11` (native-dep surprise:
  pywinpty on the windows worker, Chromium libs on linux) that can't be resolved by image
  choice or `--with-deps` → re-scope the affected lane (keep it on Actions) and record it.

**Acceptable variations**:
- Keeping two pipelines (existing `windows-installer` untouched + a new `ci`) instead of
  unifying (DD6 fallback), if the Vault re-seed proves fiddly.
- Task image choice (e.g. a slimmer or pre-provisioned image) so long as the task stays
  runnable via `fly execute -i repo=.`.
- Folding the docs leg into the cutover leg if it stays small.

### Legs

> **Note:** Tentative; planned and created one at a time as the flight progresses.

- [x] `bwrap-feasibility-spike` — **(GATE)** `fly execute` a throwaway bwrap task on a
      Concourse worker and confirm `-m requires_bwrap` passes with **real kernel
      containment (not graceful-degrade passthrough)** in the *exact image + interpreter
      layout* the lane will use. The GH job's containment only works because the interpreter
      resolves back into `/usr` (a system-python venv, `test.yml:132-141`) — a naive
      `python:3.11` task with bubblewrap installed could pass a shallow `which bwrap` yet
      still fail kernel containment *or* boxed-mode `minimal_rootfs` execvp (the same
      `/opt`-interpreter trap setup-python hit). So the spike must also **decide the
      image/venv strategy**, not just emit GO/NO-GO. Record the result + chosen strategy in
      the flight log. Decides DD4.
- [x] `concourse-ci-tasks` — author the task files, each green standalone via
      `fly execute -c … -i repo=.`:
      - `ci/tasks/{lint,test,browser}.yml` — **linux**, `python:3.11` registry-image,
        `pip install -e ".[all-llms,dev]"`, bare `python -m pytest`; `browser` adds
        `playwright install --with-deps chromium` (root in the debian image).
      - `ci/tasks/windows-tests.yml` — **`platform: windows`**, a *PowerShell + choco
        `python311`* task modeled on `ci/tasks/windows-installer-build.yml` (NOT a linux
        task — the windows worker has no Git-Bash; quote the extras spec for PowerShell, and
        re-list the ~427-test OS-divergent file set from `test.yml:104-116`). Smoke it via a
        dedicated `fly execute` before pipeline wiring (single shared windows worker).
      - `ci/tasks/bwrap.yml` — **only iff the Leg-1 spike was GREEN**, in the spike's chosen
        image/venv layout.
- [x] `ci-pipeline` — set the unified `the-one` pipeline: a `ci` job (git on `main`,
      `trigger: true`, `in_parallel { fail_fast: false }` over the task files) + a
      `build-windows-installer` job (`get: repo / passed: [ci]`) that **reuses the existing
      `ci/tasks/windows-installer-build.yml` unchanged** (only the surrounding job +
      `passed:` gate + MinIO `put` are new — the proven Windows build is not rewritten).
      Promote the Vault secrets to team-level + update `.vault-seeds.json` (Prereqs/DD6);
      unpause; prove a green `ci` build and a MinIO-published installer; then **destroy the
      old standalone `windows-installer` pipeline** so two pipelines don't both auto-build on
      `main` (double windows-worker contention).
- [x] `github-actions-cutover` — leave `windows-installer.yml` intact; then, by spike result:
      - **GREEN (bwrap ported):** convert *both* `lint.yml` and `test.yml` to
        `workflow_dispatch`-only.
      - **RED (bwrap stays on Actions):** `lint.yml` → `workflow_dispatch`-only; `test.yml`
        keeps its `pull_request`/`push:main` trigger but is **trimmed to the single `bwrap`
        job** (everything else now lives on Concourse).
      Verify: opening/updating a PR triggers no `lint`/`test` (full-suite) Actions runs.
- [x] `docs` — `ci/README.md` (what-runs-where table, pre-push `fly execute` gate,
      on-demand installer, Vault/team-secret + windows-worker notes, the MinIO
      external-DNS-by-IP gotcha) + update any CI references in `README.md`/`CLAUDE.md`/
      `agents.md`.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [ ] Concourse `ci` build green on `main`; installer published to MinIO
- [ ] GitHub Actions no longer triggered by PRs/pushes (release workflow intact)
- [x] Documentation updated (`ci/README.md`)

### Verification

This is an infrastructure flight — verification is by **observing real pipeline behavior**,
not a behavior test:
1. Push a trivial commit to `main` (or manually trigger) → the Concourse `ci` job runs and
   goes **green** across lint/test/browser/windows-subset[/bwrap].
2. `build-windows-installer` runs `passed: [ci]` and the `.exe` lands in MinIO
   (`mc ls`/console at `:9001`).
3. Open a throwaway PR (or push a branch) → GitHub **Actions tab shows no new `lint`/`test`
   runs**; `fly execute -c ci/tasks/test.yml -i repo=.` against the working tree passes
   (the pre-push gate works).
4. `windows-installer.yml` is unchanged and still declares the `v*`-tag trigger (the release
   path is intact; it will run once the GitHub billing block is cleared — out of scope here).
