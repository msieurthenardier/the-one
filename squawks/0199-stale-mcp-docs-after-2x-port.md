# Squawk 0199: Stale MCP docs after the mcp 2.x port

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-12

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
- `the_one/mcp/__init__.py` docstring: now describes the client as a wrapper around "mcp 2.x" (Mission 29 Flight 2 leg 1, with the `_HANDSHAKE_OFFER_VERSION` rename).
- `_probe_auth_posture` docstring: rewritten in leg 3 (DD9). It states the request is made with `httpx2` and describes the four verdicts (`no_auth`, `oauth`, `unexpected_status`, `error`).
- `CLAUDE.md` `requires_bwrap` count: corrected in leg 1 to the measured set (44 collected); leg 3 re-measured it (see the flight log).
- `the_one/agents.md` dual-HTTP-stack rule and the patch-target gotcha: already at the "`httpx2`, not `httpx`, under `the_one/mcp/` (DD4)" bullet; leg 3 adds the patch-target note for tests that stub the driver's client next to a real `httpx2` client, and documents negotiation, era memory, the probe verdicts and the flow drivers.

## Verification
- Leg 3: `tests/test_auth_posture_probe.py` pins the four verdicts; `grep -n "bare .httpx. POST" the_one/mcp/transports/streamable_http.py` is empty; `grep -n "1.27" the_one/mcp/__init__.py` is empty.
- `ruff check` / `ruff format --check` on `the_one/ tests/ scripts/` and `make test-unit` pass (flight log, `### auto-negotiation-api`).

## Sign-Off
*(written at completion)*
**Reviewer**: flight review, Mission 29 Flight 2 (Sonnet)
**Verdict**: confirmed
**Commit**: flight/2 code commit (Mission 29 Flight 2)
