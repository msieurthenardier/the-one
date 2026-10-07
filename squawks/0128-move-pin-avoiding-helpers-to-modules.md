# Squawk 0128: Move formatClock and the MCP error helpers into their own modules

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

Mission 25 Flight 6 put two shared helpers in files that were already loaded, to avoid raising the `index.html` script-count pin.
- **`App.time.formatClock`** lives in the app bootstrap.
- **`App.mcpErrorMessage` and `App.buildMcpError`** live in an Agents-tab file, but the Library's `mcp-server-editor.js` uses them. That works only by load order. This is a cross-area coupling.

Move them into their own modules and raise the pin deliberately. The globals stay the same, so there is no API change.

## Evidence

- `the_one/interfaces/web/static/js/app.js`: `function formatClock(d)` (about line 290) and `time: { formatClock: formatClock }` (about line 319).
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`: `window.App.mcpErrorMessage = …` and `window.App.buildMcpError = …` (about lines 655–656). The consumer is `areas/studio/mcp-server-editor.js`.
- The pin is in `tests/test_index_asset_cache_busting.py` (script count 83).
- The Flight 6 debrief, Technical and recommendation 2.

## Corrective Action
*(written at completion)*
New `static/js/time.js` and `static/js/mcp-error.js`, loaded before their consumers in `index.html`. The pin raised with a comment. Docs follow (CLAUDE.md, `agents.md`).

## Verification
The existing tests cover both helpers (`test_clock_formatter_edges`, the MCP error helper and surface tests). The chats, agents and library lanes, plus the static guards.

## Sign-Off
*(written at completion)*
