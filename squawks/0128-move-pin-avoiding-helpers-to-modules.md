# Squawk 0128: Move formatClock and the MCP error helpers into their own modules

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-07

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
Moved `formatClock` out of `app.js` into new `static/js/time.js` (`App.time.formatClock`), and `mcpErrorMessage`/`buildMcpError` out of `areas/studio/mcps-tab.js` into new `static/js/mcp-error.js`; code and comments moved verbatim, globals unchanged. Both tags load right after `app.js` in `index.html`, before every consumer. Script-count pin raised 83 to 85 with a comment naming this squawk. Docs updated (CLAUDE.md Flight 6 alignment notes, `agents.md` DD19 and Chats-list time entries).

## Verification
Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_index_asset_cache_busting`): 265 passed. Browser (`-m browser`, netns): `test_flow_chat_list`, `test_studio_mcps_tab`, `test_mcp_test_connection_button`, `test_flow_studio_mcp_editor`, `test_flow_new_chat`, `test_flow_chat_peer_attribution`: 93 passed, 1 skipped. `make test-unit`: 5452 passed, 10 skipped. `ruff check` and `ruff format --check` clean.
Review fix: removed the duplicate pre-guard `window.App.*` assignments from `mcp-error.js`; re-run static guards plus `test_mcp_error_classes_pinned`: 268 passed; browser `test_mcp_test_connection_button` + `test_studio_mcps_tab`: 16 passed, 1 skipped.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean; review cycle 1 found one blocking issue (a duplicate pre-guard `window.App` assignment pair in `mcp-error.js`), fixed by a fix Developer and confirmed by a fresh re-review Reviewer
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
