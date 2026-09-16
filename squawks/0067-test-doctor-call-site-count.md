# Squawk 0067: Stale `run_doctor(` call-site count in `tests/test_doctor.py` comments

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

## Report

Two comments in `tests/test_doctor.py` say there are 19 `run_doctor(` call
sites in the file; there are 21 (enumerated at the Flight 4 debrief). The
autouse stubs are file-scoped, not count-driven, so nothing misbehaves —
the figure is simply stale and will mislead the next reader who counts.

## Evidence

- `tests/test_doctor.py:38` — "every ``run_doctor(`` call in this file — there are 19, across 9 classes"
- `tests/test_doctor.py:67` — "there are 19 `run_doctor(` call sites" (the Flight 4 Leg 1 stub comment, copied from the first)
- `grep -c "run_doctor(" tests/test_doctor.py` minus comment/name matches → 21 (Flight 4 debrief, Developer interview)

## Corrective Action

*(written at completion)*

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition

*(only for deferred or escalated squawks)*
