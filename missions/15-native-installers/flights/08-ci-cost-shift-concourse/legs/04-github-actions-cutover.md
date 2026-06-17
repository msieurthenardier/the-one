# Leg: github-actions-cutover

**Status**: completed
**Flight**: [CI cost-shift — move day-to-day CI to local Concourse](../flight.md)

## Objective

Finalize GitHub Actions as **release-only**: convert `lint.yml` and `test.yml` to
`workflow_dispatch`-only (kept on disk as break-glass fallbacks), leaving
`windows-installer.yml` (the `v*`-tag release) as the sole auto-active GitHub workflow — so PRs
and main pushes no longer consume Actions minutes.

## Context

- **DD4 resolved GREEN** (Leg 1): the bwrap lane ported to Concourse, so the **GREEN branch** of
  this leg applies — **both** `lint.yml` and `test.yml` become `workflow_dispatch`-only. (The RED
  branch — keep `test.yml` triggered but trimmed to a lone `bwrap` job — does NOT apply.)
- **Mirrors goldfinch's `ci.yml` treatment**: PR/push triggers disabled, workflow kept on disk as a
  manual break-glass + documented test inventory (DD2).
- **`windows-installer.yml` is left UNTOUCHED** — it declares the `v*`-tag trigger and is the
  official release path (mission constraint; F5). It will run once GitHub billing is restored.
- **Current triggers** (to be replaced):
  - `lint.yml` lines 3-6: `on: { pull_request:, push: { branches: [main] } }`.
  - `test.yml` lines 9-12: `on: { pull_request:, push: { branches: [main] } }` + a `concurrency:` block.
- **Verification timing**: the live "open a PR → no `lint`/`test` runs" check is **post-merge** (the
  new trigger blocks only take effect once these files are on `main`; pre-merge the old triggers
  still live on `main`, but Actions minutes are exhausted so nothing runs regardless). Recorded as a
  post-landing step, consistent with the flight's Verification section.

## Inputs

- `.github/workflows/{lint,test,windows-installer}.yml` exist with their current triggers.
- Legs 1-3 landed (Concourse now carries the routine CI).

## Outputs

- `lint.yml` and `test.yml` with `on: { workflow_dispatch: }` only + a header comment explaining
  the intentional trigger-disable (CI moved to Concourse; pre-push gate via `fly execute`).
- `windows-installer.yml` unchanged.

## Acceptance Criteria

- [x] `lint.yml` triggers on `workflow_dispatch` **only** — no `pull_request`, no `push`. Job body
      (ruff steps) unchanged. A header comment states it is intentionally manual-dispatch (routine
      lint runs on Concourse; this is a break-glass fallback).
- [x] `test.yml` triggers on `workflow_dispatch` **only** — no `pull_request`, no `push`. All 4 job
      bodies (`test`/`browser`/`windows`/`bwrap`) are **kept on disk unchanged** (documented test
      inventory + break-glass). The `concurrency:` block may stay (harmless under dispatch) or be
      removed with the now-unused `${{ github.ref }}` group — keep it for minimal churn unless it
      references a removed trigger field.
- [x] `windows-installer.yml` is **byte-for-byte unchanged** (`git diff` shows no change to it).
- [x] Both edited workflows remain valid YAML (GitHub Actions schema: `on: workflow_dispatch`).

## Verification Steps

- `git diff .github/workflows/lint.yml .github/workflows/test.yml` shows only the `on:` trigger
  blocks changed (+ header comments) — no job-body changes.
- `git status` shows `windows-installer.yml` unmodified.
- (Post-merge) Open a throwaway PR / push a branch → the GitHub **Actions tab shows no new
  `lint`/`test` runs**; a `v*` tag still triggers `windows-installer.yml`. Recorded as post-landing.

## Implementation Guidance

1. In `lint.yml`, replace the `on:` block (lines ~3-6) with:
   ```yaml
   # Routine lint runs on local Concourse (the-one pipeline). This workflow is kept as a
   # manual break-glass fallback only — its PR/push triggers were removed in M15 F8 to stop
   # consuming GitHub Actions minutes. Pre-push gate: fly -t the-one execute -c ci/tasks/lint.yml -i repo=.
   on:
     workflow_dispatch:
   ```
   The `concurrency:` block in `lint.yml` references `${{ github.ref }}` — harmless under dispatch;
   keep it. Leave the `jobs:` unchanged.
2. In `test.yml`, do the same: replace the `on:` block (lines ~9-12) with a `workflow_dispatch:`-only
   trigger + an analogous header comment (pre-push gate references `ci/tasks/test.yml` etc.). Keep
   all 4 jobs and the existing in-file header comment about ephemeral runners. Keep or drop the
   `concurrency:` block — keep for minimal churn.
3. Do NOT touch `windows-installer.yml`.
4. Confirm both files are valid YAML.

## Edge Cases

- **`workflow_dispatch` with no inputs** is valid (`on: { workflow_dispatch: }`) — an empty mapping
  is fine; do not invent inputs.
- **Don't delete the workflows** — DD2 keeps them on disk as break-glass + test inventory.
- **`concurrency` referencing `github.ref`** still resolves under `workflow_dispatch` (ref = the
  dispatched ref) — safe to keep.

## Files Affected

- `.github/workflows/lint.yml` — trigger → `workflow_dispatch`-only + header comment.
- `.github/workflows/test.yml` — trigger → `workflow_dispatch`-only + header comment.
- `missions/.../flight-log.md` — leg progress entry.

---

## Post-Completion Checklist

- [x] `lint.yml` + `test.yml` are `workflow_dispatch`-only; job bodies unchanged
- [x] `windows-installer.yml` byte-for-byte unchanged
- [x] Both workflows valid YAML
- [x] Flight log updated (incl. the post-merge "no PR runs" verification as a post-landing step)
- [x] Set this leg's status to `landed` (commit deferred to end-of-flight batch)
