# Squawk 0033: Pin the stop-before-start invariant behind _run's permanent-failure return

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-02

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

Test-and-comments only — no manager behavior change, per squawk scope.

1. Added `test_start_after_permanent_failure_is_noop_until_stop` to
   `tests/test_connectors_manager.py`. It drives `StubPlugin` to raise
   `PermanentConnectorFailure` on connect, then asserts: the listener
   task finishes but the `_ListenerEntry` stays in `_listeners`; a bare
   `start()` on the same id is a no-op (no new `connect` call, no live
   client); `stop()` then `start()` clears the stale entry and produces
   a live listener again. This pins the exact contract the two recovery
   paths in `api.py` depend on.
2. Added a one-line cross-reference comment at both call sites in
   `the_one/interfaces/web/api.py` that rely on stop-before-start —
   `update_connector`'s PUT restart (~line 2869) and the rotation-restart
   hook (~line 4877) — each pointing back to the invariant documented on
   `ConnectorManager._run`'s `PermanentConnectorFailure` branch in
   `the_one/connectors/manager.py`.

No production code paths changed; `_run`'s permanent-failure return still
leaves the entry in place exactly as before.

## Verification

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connectors_manager.py -x --timeout 30`
→ 15 passed (14 pre-existing + 1 new), 0.75s.

## Sign-Off
**Reviewer**: independent batch Reviewer (Haiku), squawk/turnaround-2026-09-02
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-02 batch commit (PR follows)
