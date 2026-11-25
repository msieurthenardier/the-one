# Squawk 0415: Three GitHub workflows run with the default token scope

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

`lint.yml`, `test.yml` and `pr-lint.yml` have no `permissions:` block, so their jobs get the repository's default `GITHUB_TOKEN` scope. They only check out code and run ruff, the audit and tests, so `contents: read` is enough. `pr-lint.yml` runs on every pull request and on a weekly schedule. Found by the 2026-11-24 routine maintenance (CI/CD Reviewer).

## Evidence
- `grep -L "permissions:"` lists `.github/workflows/lint.yml`, `test.yml` and `pr-lint.yml`.
- `release.yml` and the three package workflows already set `contents: read` at the top level.

## Corrective Action
Read all three workflows: no job uses PR comments, check writes, or any token-writing action (checkout, setup-python, ruff, pip-audit, pytest only). Added a top-level `permissions: contents: read` block (before `concurrency:`) to `.github/workflows/lint.yml`, `test.yml` and `pr-lint.yml`.

## Verification
All three workflows set `permissions: contents: read` at the top level (grep confirms one block in each). `.venv/bin/python -m pytest tests/test_packaging_locked_closure.py tests/test_release_workflow.py -x --timeout 120 -q` passes (part of a 143-passed run). The next pull request's `pr-lint` run is still to be observed. This turnaround's own PR runs it.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; CI token surface), batch review of squawks 0411-0419
**Verdict**: confirmed. No job needs a write scope: the workflows use only checkout, setup-python, ruff, pip-audit and pytest, with no `gh` calls and no secrets.
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
