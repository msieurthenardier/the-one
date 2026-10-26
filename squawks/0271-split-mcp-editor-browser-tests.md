# Squawk 0271: Split the 4,920-line MCP editor browser test file by concern

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
`tests/browser/test_flow_studio_mcp_editor.py` is 4,920 lines: 149 test functions, 178 tests after parametrisation, and 45 module-level helpers. It is the entire `mcp` lane.

The lane ran 490-507 s against a 630 s budget at Mission 31 Flight 5's close. One file cannot be spread across lanes, so the next growth lands directly on the budget. Its helpers can't be reused by other files either.

Split it by concern into several files with a shared helper module, for example stdio and fields, env and headers, sign-in and OAuth, status and tools, create/delete/flash. That lets `mcp` become two balanced lanes if needed.

The operator approved logging it at the Flight 5 debrief (Recommendation 5).

## Evidence
- `wc -l tests/browser/test_flow_studio_mcp_editor.py` gives 4920.
- `scripts/run-tests.sh` has `mcp_pat=('test_flow_studio_mcp_editor.py')`.
- Final gate on `448ba82`: `mcp` wall 507 s, budget 630.
- A lane split, if made, updates `scripts/run-tests.sh` (lane list, budgets), `tests/test_run_tests_lanes.py` and CLAUDE.md's lane bullets and budget table.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
