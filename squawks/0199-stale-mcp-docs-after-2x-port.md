# Squawk 0199: Stale MCP docs after the mcp 2.x port

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
Mission 29 Flight 1 moved the MCP client to `mcp==2.3.0` on `httpx2`. A few docs still describe the old state, and the new dual HTTP stack has no written rule (found in the flight debrief):
- `the_one/mcp/__init__.py`'s module docstring still says the client wraps "mcp==1.27.0".
- `the_one/mcp/transports/streamable_http.py::_probe_auth_posture`'s docstring still says "a bare `httpx` POST". It now uses `httpx2`.
- `CLAUDE.md` says the `requires_bwrap` set is 12 tests; it is now 41 passed and 3 skipped.
- `the_one/agents.md` has no dual-HTTP-stack rule. It should say that `the_one/mcp/` and the two OAuth flow drivers in `api.py` use `httpx2` while the rest of the app uses `httpx`. It should also record the patch-target gotcha: `patch("…api.httpx.AsyncClient")` silently stops intercepting the `httpx2` drivers.

## Evidence
- `the_one/mcp/__init__.py` docstring: "thin async wrapper around mcp==1.27.0 SDK".
- `pytest -m requires_bwrap` at `06e1e39`: 41 passed, 3 skipped (Flight 1 debrief).
- `tests/test_mcp_httpx_guard.py` enforces the httpx ban under `the_one/mcp/`, but no prose states the rule.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
