# Squawk 0154: The lockfile pins pip 26.1.1, with two advisories

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
A lock-synced `pip-audit` (squawk 0153's verification) still reports pip 26.1.1: PYSEC-2026-196 (fixed in 26.1.2) and PYSEC-2026-3721 (fixed in 26.2). pip is locked as a dependency of `pip-api`, which pip-audit pulls into the dev extra, so this is dev tooling and does not ship. It has the same root as 0153: 0144's audit ran on a hand-upgraded venv, which hid the locked versions.

## Evidence
- `uv.lock` — `name = "pip"`, `version = "26.1.1"`, depended on by `pip-api`
- `.venv/bin/pip-audit` after `uv sync --frozen --all-extras`: two pip advisories, each listed twice

## Corrective Action
*(written at completion)* Expected: `uv lock --upgrade-package pip` to 26.2 or later, with only pip moving.

## Verification
`uv lock --check` clean; after `uv sync --frozen --all-extras`, `pip-audit` reports no advisory apart from the unauditable local package.

## Sign-Off
*(written at completion)*
