# Squawk 0154: The lockfile pins pip 26.1.1, with two advisories

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
A lock-synced `pip-audit` (squawk 0153's verification) still reports pip 26.1.1: PYSEC-2026-196 (fixed in 26.1.2) and PYSEC-2026-3721 (fixed in 26.2). pip is locked as a dependency of `pip-api`, which pip-audit pulls into the dev extra, so this is dev tooling and does not ship. It has the same root as 0153: 0144's audit ran on a hand-upgraded venv, which hid the locked versions.

## Evidence
- `uv.lock` — `name = "pip"`, `version = "26.1.1"`, depended on by `pip-api`
- `.venv/bin/pip-audit` after `uv sync --frozen --all-extras`: two pip advisories, each listed twice

## Corrective Action
Ran `uv lock --upgrade-package pip`: pip 26.1.1 -> 26.2.1. Only pip's `version =` line changed in `uv.lock` (plus its sdist/wheel url and hash lines); no other package moved. `pyproject.toml` untouched.

## Verification
`uv sync --frozen --all-extras` installed pip 26.2.1; `.venv/bin/pip-audit` reports "No known vulnerabilities found" (only the unauditable local `the-one` skipped); `uv lock --check` clean; `pre-commit run --all-files` passes.

## Sign-Off

**Reviewer**: independent Reviewer (Haiku tier: dev-tooling lockfile only). It confirmed that only pip's `version =` line moved (26.1.1 → 26.2.1), `uv lock --check` is clean, and `pip-audit` reports no known vulnerabilities on a lock-synced venv. The Flight Director re-ran `pre-commit run --all-files` (passed).
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk/0154: pip 26.2.1 in uv.lock` on branch `squawk/0154-pip-advisories-in-lockfile`
