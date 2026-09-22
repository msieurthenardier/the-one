# Squawk 0067: Stale `run_doctor(` call-site count in `tests/test_doctor.py` comments

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-17

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

Counted the real `run_doctor(` invocations with a small script (rather than
eyeballing `grep`) so comment lines and test-name substring matches would be
excluded programmatically: it walked every line containing `run_doctor(`,
dropped lines whose stripped text starts with `#` (the two comments at
lines 38/67), and dropped lines matching `def\s+\w*run_doctor\w*\(` (the
test method `test_skip_keeps_result_pass_in_run_doctor(self, ...)` at line
228, whose name+signature happens to contain the literal substring
`run_doctor(`). That left **21** real call sites — confirming the debrief's
figure, not the comments' stale 19.

The script then mapped each of the 21 call-site lines to the nearest
preceding `^class ` line to find which classes contain at least one
`run_doctor(` call. Result: **10** distinct classes
(`TestRunDoctorHost`, `TestRunDoctorFailures`, `TestProbeDesktopShell`,
`TestProbeLLMProviders`, `TestProbeModelCatalog`, `TestProbeUsearch`,
`TestProbeFts5`, `TestEmbeddingProbeGating`, `TestEmitEncodingSafety`,
`TestProbeFileWatcher`) — not the 9 the first comment claims. (The file
has 16 `class` statements total; the other 6 — `TestDetectRuntimes`,
`TestDispatch`, `TestUsearchAcceleration`, plus the three non-test helper
stub classes `_StubMatches`, `_StubIndex`, `_Fts5UnavailableConnection` —
contain no `run_doctor(` call.)

Updated both comments in `tests/test_doctor.py`:
- Line 38 (embedding-probe autouse fixture docstring comment): "there are
  19, across 9 classes" → "there are 21, across 10 classes"; and the
  derived "Patching a single \"host test\" would leave eighteen still
  paying for it" → "...leave twenty still paying for it" (18 = 19-1 was
  itself derived from the stale count, so it needed the same correction).
- Line 67 (file-watcher-probe autouse fixture docstring comment, the
  Flight 4 Leg 1 copy of the first): "there are 19 `run_doctor(` call
  sites" → "there are 21 `run_doctor(` call sites"; and its matching
  derived "the other eighteen paying for it" → "the other twenty paying
  for it".

No other files touched. Scope stayed inside `tests/test_doctor.py` and
this squawk artifact, per the squawk's scope gate.

## Verification

```
$ PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_doctor.py -x --timeout 60
...
collected 55 items
tests/test_doctor.py ................................................... [ 92%]
....                                                                     [100%]
============================== 55 passed in 2.45s ==============================

$ make lint
.venv/bin/python -m ruff check the_one/ tests/ scripts/
All checks passed!
```

## Sign-Off

**Reviewer**: batch Reviewer agent (Haiku tier — the diff is documentation, crew prompts and a test comment; no security-sensitive surface, per `.flightops/agent-crews/leg-execution.md`)
**Verdict**: confirmed
**Commit**: `7b85333`

## Disposition

*(only for deferred or escalated squawks)*
