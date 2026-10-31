# Squawk 0300: Bump the dev-only virtualenv and msgpack locks past their CVEs

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
`pip-audit` reports 9 vulnerabilities in two locked packages. Both are dev or tool dependencies and neither ships in the packaged app (virtualenv comes in through pre-commit; msgpack through pip-audit's cachecontrol), so the risk is low, but the audit stays red until they move. From maintenance report 2026-10-30, finding #20.

## Evidence
- `uv.lock`: `virtualenv` 21.14.5 (CVE-2026-113714, -113715, -113717, -113718, -113720, -113722, -113723, -113725; fixed in 21.14.7-21.14.9).
- `uv.lock`: `msgpack` 1.2.1 (CVE-2026-114613; fixed in 1.2.3).
- `.venv/bin/pip-audit` run on 2026-10-30.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

`uv lock --upgrade-package virtualenv --upgrade-package msgpack` moves only those two (and any forced transitive) entries; `uv lock --check` passes; `pip-audit` reports neither package; `make test-unit` is green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
