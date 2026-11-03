# Squawk 0320: `windows_test_copy.py` hard-codes `C:\Python311`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
Squawk 0135 raised the project floor to Python 3.12. `scripts/windows_test_copy.py` (around lines 59-60) still hard-codes `C:\Python311` as the interpreter on the operator's Windows desktop, and its test mocks the same path. Make the interpreter path configurable, or default it to 3.12, and document it.

## Evidence
- Batch review of turnaround 2026-11-02-2 (candidate 1).
- `tests/test_windows_test_copy.py`.

## Corrective Action
*(written at completion)*

## Verification
- The script finds a 3.12 interpreter on the operator's desktop or takes one as an option.
- Its unit tests pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
