# Squawk 0366: the tool toggle's impact dialog has no browser tests for Esc, a failed preview, or focus after "Turn on anyway"

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
Squawk 0322 added the impact dialog to the Built-in tools toggle. Its browser tests cover the dialog listing agents, Cancel, the focus after Cancel, and a toggle that narrows nobody. Three paths were read by two reviewers but have no test:
1. Esc on the dialog (the tool stays off, focus returns to the switch).
2. A failed impact preview (the toggle must fall through to the save, because the PUT is the gate).
3. Focus after "Turn on anyway".

Add a browser test for each in `tests/browser/test_flow_admin_tools_impact.py`, and falsify each by removing the behaviour it pins.

## Evidence
- `tests/browser/test_flow_admin_tools_impact.py` has `test_turning_a_tool_on_lists_the_agents_it_narrows_first` and `test_turning_a_tool_on_that_narrows_nobody_has_no_dialog` only for the toggle.
- `the_one/interfaces/web/static/js/areas/admin/tools-page.js::handleToolToggle` is the code path (the dialog, the failed-preview fallthrough and `applyToggle`).
- Squawk 0322 Corrective Action and Verification.
