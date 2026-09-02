# Squawk 0033: Pin the stop-before-start invariant behind _run's permanent-failure return

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

## Report

`ConnectorManager._run` returns on `PermanentConnectorFailure` WITHOUT popping its
`_ListenerEntry` from `self._listeners` — documented as correct because every recovery
path (`update_connector` PUT, rotation-restart hook) calls `stop()` before `start()`.
That is an implicit multi-file invariant with no test enforcing it: a future third
recovery path that calls `start()` without `stop()` would silently no-op (start's
early-return on a tracked id) and strand a permanently-failed listener. Add one
assertion-level test pinning the invariant (start-after-permanent-failure without stop
does not produce a live listener / stop-then-start does), or at minimum comment
cross-references at both call sites.

## Evidence

- `the_one/connectors/manager.py::_run` — permanent-failure `return` + the "correct
  today because every recovery path calls stop() before start()" comment
- Call sites relying on it: `interfaces/web/api.py::update_connector` (stop+start),
  rotation-restart hook (same file)
- Raised by the Flight 3 debrief (2026-09-02), Developer interview

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
