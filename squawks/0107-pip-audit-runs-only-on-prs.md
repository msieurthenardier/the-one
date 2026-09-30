# Squawk 0107: The release pip-audit gate runs only on PRs, so new advisories surface at release time

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-30
**Completed**: —

## Report

Advisories published against unchanged pins are found only when some PR happens
to run `pr-lint.yml`. That usually means the release PR, where they block the
release. The v0.9.1 release PR (#215) was blocked this way by 12 pyjwt
advisories (squawk 0103), and anyio before it (squawk 0083). A scheduled audit
of `main` would surface them between releases.

## Evidence

- `.github/workflows/pr-lint.yml` — `on: pull_request: branches: [main]` only; the `pip-audit` job exports the release closure from `uv.lock` and fails on findings.

## Corrective Action

*(written at completion)*

Add a `schedule:` trigger (weekly) plus `workflow_dispatch` to the audit job, or
add an equivalent job to the local Concourse pipeline (see `ci/README.md` for
which CI owns what). A scheduled failure must be visible, not silent.

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
