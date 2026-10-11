# Squawk 0174: `UNGATED_PREFIXES` in the agent drawer is a hand-kept copy with no parity pin

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
`static/js/areas/chat/agent-drawer.js` hard-codes `UNGATED_PREFIXES = ['mcp__', 'kb__']`, mirroring `the_one/agent/config.py::UNGATED_TOOL_PREFIXES`, and no test pins them together. `whitelistExempt` in `tool-categories.js` *is* pinned by `tests/test_tool_categories.py`. A new prefix added server-side would silently mis-render the drawer.

## Evidence
`agent-drawer.js:~95`; `config.py:~17`. The fix: move the prefixes into `App.toolCategories` beside `whitelistExempt` and pin them in `test_tool_categories.py`, or add a parity test. The longer-term server-sent gating policy is a maintenance item, not this squawk.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
