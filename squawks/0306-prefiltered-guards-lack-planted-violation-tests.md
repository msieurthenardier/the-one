# Squawk 0306: the pre-filtered source-scan guards have no test that they still fire

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
Mission 34 Flight 1 sped up four source-scan guards by checking a cheap substring before running the expensive scan. Each pre-filter was argued exact at review: it should never skip a file the full scan would flag. No test proves it, so a later edit to a needle list could quietly turn a guard into one that never fires. Add one test per guard that plants a violation in a temp tree (or a crafted source string) and expects the guard to report it through the pre-filtered path.

## Evidence
- `tests/test_ui_ownership.py:189` — `if name not in content:  # a token match needs the substring: skip the regex`, and `:209` (`name not in selector`).
- `tests/test_desktop_split_guard.py:250-255` — `needles = {SHELL_PACKAGE} | fixtures` … `if not any(needle in source for needle in needles):`.
- `tests/test_mcp_httpx_guard.py:84` — `if not any(word in source for word in (*_REMOVED_MODULES, *_REMOVED_NAMES)):`.
- `tests/test_schema_template.py:126` — `if "ensure_schema" not in source and "init_db" not in source:`.
- Flight debrief: `missions/34-maintenance/flights/01-test-suite-runtime-ii/flight-debrief.md`, Recommendation 3.

## Corrective Action
*(written at completion)*

## Verification
- Each new test fails when its guard's pre-filter is edited to skip the planted file (falsified by editing, then restored by editing), and passes as written.
- `make test-unit` passes; the four guard files stay within their current timings.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
