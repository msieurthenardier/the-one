# Squawk 0153: The lockfile still pins virtualenv 21.5.0, with four advisories

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
After the 2026-10-08 turnaround merged, `uv sync --frozen --all-extras` restored virtualenv 21.5.0 from `uv.lock`, and `pip-audit` again reports PYSEC-2026-4011…4014 (fixed in 21.7.x). Squawk 0144's "pip-audit clean" verification held only because its Developer had upgraded virtualenv in the venv outside the lock. The lockfile was never changed for it. virtualenv is dev tooling (pulled in by `pre-commit` in the dev extra) and does not ship in the Windows build, so this is servicing, not a runtime exposure.

## Evidence
- `uv.lock` — `name = "virtualenv"`, `version = "21.5.0"`, a dependency of `pre-commit`
- `.venv/bin/pip-audit` after a frozen sync: four virtualenv advisories; urllib3 clean at 2.8.0

## Corrective Action
Ran `uv lock --upgrade-package virtualenv`. Only two `uv.lock` entries moved: virtualenv 21.5.0 -> 21.14.5 and its dependency python-discovery 1.4.2 -> 1.6.1. `pyproject.toml` untouched. Lesson for audits: verify after `uv sync --frozen`, never on a hand-upgraded venv.

## Verification
On a lock-synced venv (`uv sync --frozen --all-extras`, which installed virtualenv 21.14.5 and python-discovery 1.6.1): `pip-audit` reports no virtualenv advisory; `uv lock --check` clean; `pre-commit run --all-files` passes (ruff, ruff format).

Out-of-scope finding: the same `pip-audit` run reports pip 26.1.1 (locked in `uv.lock`) against PYSEC-2026-196 (fix 26.1.2) and PYSEC-2026-3721 (fix 26.2), each listed twice. Not addressed here; needs its own squawk.

## Sign-Off

**Reviewer**: independent Reviewer (Haiku tier: dev-tooling lockfile only). It confirmed exactly two `version =` lines moved (virtualenv 21.5.0 → 21.14.5, python-discovery 1.4.2 → 1.6.1), `uv lock --check` clean, and no virtualenv advisory from `pip-audit` on a lock-synced venv. The remaining pip advisories are tracked as squawk 0154.
**Verdict**: confirmed (`[HANDOFF:confirmed]` on substance; the Reviewer's two "changes requested" were the Status/Sign-Off fields, which the Flight Director writes at close-out)
**Commit**: `squawk: turnaround 2026-10-08 (2)` on branch `squawk/turnaround-2026-10-08-2`
