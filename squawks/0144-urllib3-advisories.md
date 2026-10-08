# Squawk 0144: urllib3 2.7.0 has three published advisories

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
`pip-audit` reports urllib3 2.7.0 (PYSEC-2026-4175, -4176, -4177; fixed in 2.8.0). urllib3 is a transitive *runtime* dependency (via requests/httpx-adjacent packages), so it ships in the Windows build. The dev venv also flags pip 26.1.1 and virtualenv 21.5.0 (tooling only), and its editable install still reports `the-one 0.10.2` against the project's 0.10.3. Found by routine maintenance 2026-10-08 (finding #17).

## Evidence
- `uv.lock` resolves urllib3 2.7.0; `pyproject.toml` dev extra floor `urllib3>=2.7.0`
- `pip-audit`: 15 advisories across pip, urllib3, virtualenv

## Corrective Action
*(written at completion)* Expected: raise the urllib3 floor to `>=2.8.0` and `uv lock --upgrade-package urllib3`. Patch-level cryptography 50.0.2 and usearch 2.26.4 may ride along. Refresh pip and virtualenv in the venv and reinstall the editable package (local only, nothing committed).

## Verification
`uv lock --check` clean; `pip-audit` shows no urllib3 advisory; `make test-unit` green.

## Sign-Off
*(written at completion)*
