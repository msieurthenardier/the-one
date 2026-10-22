# Squawk 0226: certifi has no CVE floor in pyproject.toml, so only uv.lock carries the 0224 fix

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-21
**Completed**: —

## Report
Squawk 0224 fixed certifi PYSEC-2026-4320 by moving `uv.lock` to certifi 2026.10.19, but `pyproject.toml` has no certifi floor. That breaks the project's dual-binding rule for CVE floors (the comment above the runtime CVE-floor block in `pyproject.toml`): a fix must also be an explicit floor, so that a resolve from the ranges lands on the fixed version. Examples are `pip install -e ".[gui,all-llms]"`, which `ci/tasks/windows-installer-build.yml:58` mentions, and CLAUDE.md's install command.

Add `certifi>=2026.10.19` to the runtime CVE-floor block, with a cited bullet like the others (transitive via requests/httpx; closes PYSEC-2026-4320), and re-lock if the floor changes the resolution.

## Evidence
- `pyproject.toml` on main (867cfeb): the runtime CVE-floor block (`# CVE floors (deps — some direct, most transitive — promoted to explicit floors …`) has no certifi line; `grep certifi pyproject.toml` is empty.
- Squawk 0224's Reviewer flagged this (2026-10-21).

## Corrective Action
*(written at completion)*

## Verification
- `grep -n certifi pyproject.toml` shows the floor and its comment bullet.
- `uv lock --check` passes. The release closure (`uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt`) audits clean with `pip-audit --disable-pip -r`.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
