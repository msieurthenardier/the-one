# Squawk 0415: Three GitHub workflows run with the default token scope

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

`lint.yml`, `test.yml` and `pr-lint.yml` have no `permissions:` block, so their jobs get the repository's default `GITHUB_TOKEN` scope. They only check out code and run ruff, the audit and tests, so `contents: read` is enough. `pr-lint.yml` runs on every pull request and on a weekly schedule. Found by the 2026-11-24 routine maintenance (CI/CD Reviewer).

## Evidence
- `grep -L "permissions:"` lists `.github/workflows/lint.yml`, `test.yml` and `pr-lint.yml`.
- `release.yml` and the three package workflows already set `contents: read` at the top level.

## Corrective Action
*(written at completion)*

## Verification
All three workflows set `permissions: contents: read` at the top level. The next pull request's `pr-lint` run passes. If a workflow test pins the workflow files, it passes too.
