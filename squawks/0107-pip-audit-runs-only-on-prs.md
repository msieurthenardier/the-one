# Squawk 0107: The release pip-audit gate runs only on PRs, so new advisories surface at release time

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-30
**Completed**: 2026-10-08

## Report

Advisories published against unchanged pins are found only when some PR happens
to run `pr-lint.yml`. That usually means the release PR, where they block the
release. The v0.9.1 release PR (#215) was blocked this way by 12 pyjwt
advisories (squawk 0103), and anyio before it (squawk 0083). A scheduled audit
of `main` would surface them between releases.

## Evidence

- `.github/workflows/pr-lint.yml` — `on: pull_request: branches: [main]` only; the `pip-audit` job exports the release closure from `uv.lock` and fails on findings.

## Corrective Action

Chose the GitHub-side option: `.github/workflows/pr-lint.yml` gains a weekly `schedule:` (Mondays 06:17 UTC) and `workflow_dispatch:`. The `pip-audit` job runs on all three triggers; the `lint` job is guarded with `if: github.event_name == 'pull_request'` so it stays PR-only. A scheduled failure is visible through GitHub's failed-workflow notification to the user who last edited the cron line (documented in `ci/README.md`, with the 60-day inactivity disable caveat). `.github/workflows/windows-installer.yml` also gains the same release-closure audit as a separate `pip-audit` job that the build job `needs:`, so a finding fails a `v*` release before any Windows build time is spent. Considered, not chosen: a Concourse job (would be invisible outside the host). Original suggestion, for reference: add a `schedule:` trigger (weekly) plus `workflow_dispatch` to the audit job, or
add an equivalent job to the local Concourse pipeline (see `ci/README.md` for
which CI owns what). A scheduled failure must be visible, not silent.

## Verification

Both workflows parse as YAML and the job/trigger structure was read back (`actionlint` is not installed on the host). The audit command and export are unchanged from the PR gate, which already runs them. The live check is the post-merge step: trigger `pr-lint` once through `workflow_dispatch` and confirm the `pip-audit` job runs and `lint` is skipped.

## Sign-Off

**Reviewer**: flight-end Reviewer (Sonnet), Mission 26 Flight 1
**Verdict**: confirmed by the flight-end review (config and verification section read back; the live `workflow_dispatch` check remains a post-merge step)
**Commit**: flight/01-test-suite-runtime, flight commit
