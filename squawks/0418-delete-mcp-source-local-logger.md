# Squawk 0418: `delete_mcp_source` creates its own logger beside the module's

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

The `delete_mcp_source` route imports `logging` inside the function and makes a local `_log`, though `api.py` already has the module `logger`, with `logging` imported at the top. The pattern is duplicated and inconsistent. Found by the 2026-11-24 routine maintenance (Python Inspector).

## Evidence
- `the_one/interfaces/web/api.py` (about lines 3250-3252): `import logging` / `_log = logging.getLogger(__name__)` inside `delete_mcp_source`.
- The module logger is defined near line 184.

## Corrective Action
*(written at completion)*

## Verification
The local import and `_log` are gone, and the route uses `logger`. The route's existing tests pass, and ruff is clean.
