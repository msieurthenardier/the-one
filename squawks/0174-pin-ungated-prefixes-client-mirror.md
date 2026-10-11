# Squawk 0174: `UNGATED_PREFIXES` in the agent drawer is a hand-kept copy with no parity pin

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
`static/js/areas/chat/agent-drawer.js` hard-codes `UNGATED_PREFIXES = ['mcp__', 'kb__']`, mirroring `the_one/agent/config.py::UNGATED_TOOL_PREFIXES`, and no test pins them together. `whitelistExempt` in `tool-categories.js` *is* pinned by `tests/test_tool_categories.py`. A new prefix added server-side would silently mis-render the drawer.

## Evidence
`agent-drawer.js:~95`; `config.py:~17`. The fix: move the prefixes into `App.toolCategories` beside `whitelistExempt` and pin them in `test_tool_categories.py`, or add a parity test. The longer-term server-sent gating policy is a maintenance item, not this squawk.

Logged from the Mission 28 flight debriefs.

## Corrective Action
Added a frozen `ungatedPrefixes` to `App.toolCategories` (tool-categories.js, beside `whitelistExempt`). `agent-drawer.js` and `studio.js` now read it; no literals remain. tool-categories.js loads (index.html:59) before agent-drawer.js (:70) and studio.js (:84). `tests/test_tool_categories.py` pins `ungatedPrefixes` to `UNGATED_TOOL_PREFIXES` and bans the literal in both client files.

## Verification
Unit: test_tool_categories, test_ui_guards, test_token_definitions pass. Browser: test_flow_chat_drawer, test_flow_studio_time_tool, test_flow_settings_date_time pass (53). ruff clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
