# Squawk 0320: `windows_test_copy.py` hard-codes `C:\Python311`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-24 (administrative closure, already fixed)

## Report
Squawk 0135 raised the project floor to Python 3.12. `scripts/windows_test_copy.py` (around lines 59-60) still hard-codes `C:\Python311` as the interpreter on the operator's Windows desktop, and its test mocks the same path. Make the interpreter path configurable, or default it to 3.12, and document it.

## Evidence
- Batch review of turnaround 2026-11-02-2 (candidate 1).
- `tests/test_windows_test_copy.py`.

## Corrective Action
The default was moved to Python 3.12 by Mission 35 Flight 2 (`f76efdd3`, found with `git log -S'Python312'`). `scripts/windows_test_copy.py` now reads `PYTHON_WIN = "/mnt/c/Python312/python.exe"`. No `311` remains in the script or its test. This closure made no change.

## Verification
- The script finds a 3.12 interpreter on the operator's desktop, or takes one as an option. The default is 3.12, and Mission 36 Flight 3's WebView2 checks ran through it.
- Its unit tests pass.
- The 2026-11-24 routine maintenance's Squawk Verifier confirmed the path at HEAD.

## Sign-Off
**Reviewer**: Squawk Verifier agent (Sonnet), 2026-11-24 routine maintenance; administrative closure by the Flight Director
**Verdict**: already fixed; closed with no code change
**Commit**: `f76efdd3` (the fix); closure recorded with the 2026-11-24 maintenance report
