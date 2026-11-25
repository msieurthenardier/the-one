# Squawk 0409: The drawer helper's router waits belong in `_nav.py`, and one wait is duplicated

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

Squawk 0406's fix added `wait_router` and `wait_router_started` to `tests/browser/_drawer.py`.
- `_nav.py` is the project's navigation helper (CLAUDE.md, "browser tests navigate through
  `_nav.py`"), so other browser files that load a page and act at once cannot reuse the wait
  without importing the drawer helper.
- On `boot()`'s path the "router started" wait runs twice: once inside `wait_socket()` and again
  in `wait_router()`.

Found by the Mission 36 Flight 5 debrief (Developer).

## Evidence
- `tests/browser/_drawer.py`: `boot` (line 118), `wait_router` (line 132, calls
  `wait_router_started` at line 134), `wait_socket` (line 138, calls `wait_router_started` at line
  146), `wait_router_started` (line 149).

## Corrective Action
*(written at completion)*

## Verification
The router-commit wait lives in `_nav.py` and `_drawer.py` calls it. `boot()` waits for the router
once. The `gleepglorp-chat` and `gleepglorp-fill` lanes pass, and
`tests/test_nav_helper.py` passes.
