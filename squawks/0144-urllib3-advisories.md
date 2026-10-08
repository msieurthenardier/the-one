# Squawk 0144: urllib3 2.7.0 has three published advisories

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
`pip-audit` reports urllib3 2.7.0 (PYSEC-2026-4175, -4176, -4177; fixed in 2.8.0). urllib3 is a transitive *runtime* dependency (via requests/httpx-adjacent packages), so it ships in the Windows build. The dev venv also flags pip 26.1.1 and virtualenv 21.5.0 (tooling only), and its editable install still reports `the-one 0.10.2` against the project's 0.10.3. Found by routine maintenance 2026-10-08 (finding #17).

## Evidence
- `uv.lock` resolves urllib3 2.7.0; `pyproject.toml` dev extra floor `urllib3>=2.7.0`
- `pip-audit`: 15 advisories across pip, urllib3, virtualenv

## Corrective Action
Raised the dev-extra urllib3 floor in `pyproject.toml` from `>=2.7.0` to `>=2.8.0` (closes PYSEC-2026-4175/4176/4177) and ran `uv lock --upgrade-package urllib3 --upgrade-package cryptography --upgrade-package usearch`. Lock moves: urllib3 2.7.0 -> 2.8.0, cryptography 50.0.0 -> 50.0.2, usearch 2.26.2 -> 2.26.4; no other package moved in `uv.lock`. Locally (nothing committed): `uv sync --frozen --all-extras`, upgraded pip and virtualenv in the venv (virtualenv 21.5.0 -> 21.14.6, with python-discovery 1.4.2 -> 1.6.1), and reinstalled the editable package, which now reports the-one 0.10.3.

## Verification
- `uv lock --check`: clean (137 packages resolved).
- `pip-audit` against the venv: "No known vulnerabilities found" (the-one itself skipped, not on PyPI).
- `scripts/run-tests.sh tests/test_ollama_library.py tests/test_provider_api.py -x --timeout 60`: 294 passed.
- Full unit suite deferred to the batch-end run by the Flight Director. No Python changed.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
