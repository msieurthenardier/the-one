# Squawk 0409: The drawer helper's router waits belong in `_nav.py`, and one wait is duplicated

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-24

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
- `wait_router_started(page, timeout=15000)` and `wait_router(page, route, timeout=15000)` moved
  into `tests/browser/_nav.py` as public helpers, behaviour unchanged. They were only called inside
  `_drawer.py` (no other callers), so no re-export is kept there.
- `_drawer.wait_socket` now calls `_nav.wait_router_started`. `boot()` waits for the router once:
  with `connected=True` it calls `wait_socket` (which already waits for the router to start) and
  then only `_nav.expect_route`; with `connected=False` it calls `_nav.wait_router`.

## Verification
The router-commit wait lives in `_nav.py` and `_drawer.py` calls it. `boot()` waits for the router
once. The `gleepglorp-chat` and `gleepglorp-fill` lanes pass, and
`tests/test_nav_helper.py` passes.

Run 2026-11-24 (`THE_ONE_TEST_NETNS=1`): `tests/test_nav_helper.py` 83 passed; lane
`gleepglorp-chat` 83 passed; `gleepglorp-fill` 45 passed; `gleepglorp-kinds` 102 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), batch review of squawks 0403, 0404, 0405, 0407, 0408, 0409 and 0410
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-24` on squawk/turnaround-2026-11-24
