# Squawk 0418: `delete_mcp_source` creates its own logger beside the module's

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

The `delete_mcp_source` route imports `logging` inside the function and makes a local `_log`, though `api.py` already has the module `logger`, with `logging` imported at the top. The pattern is duplicated and inconsistent. Found by the 2026-11-24 routine maintenance (Python Inspector).

## Evidence
- `the_one/interfaces/web/api.py` (about lines 3250-3252): `import logging` / `_log = logging.getLogger(__name__)` inside `delete_mcp_source`.
- The module logger is defined near line 184.

## Corrective Action
In `the_one/interfaces/web/api.py`, `delete_mcp_source` no longer does a local `import logging` or defines `_log`; its two `_log.warning` calls use the module `logger`. The module-level logger docstring that cited the local `_log` was updated to say it has moved.

## Verification
`tests/test_mcp_cache_cleanup.py` (the route's tests: refcount skip, unsupported runtime, delete 404) passes. `ruff check the_one/ tests/` and `ruff format --check the_one/ tests/` are clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0411-0419
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
