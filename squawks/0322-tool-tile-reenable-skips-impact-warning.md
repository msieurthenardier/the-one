# Squawk 0322: Re-enabling a built-in tool from its Settings tile adds agent notices with no impact warning

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
Sortie 07 shows the agents a save would narrow before Settings › Built-in tools saves a tightening. That warning runs only on the tool editor's Save. The tile switch sends an `enabled`-only PUT with no impact check. Notices are scoped to enabled tools, so re-enabling a tool can surface new agent notices with no warning first. This is the gap accepted under DD8 (sortie 07 debrief, Action Items). The fix: run the existing impact check before an enabling toggle, and confirm the same way the editor does when it returns agents.

## Evidence
- `the_one/interfaces/web/static/js/areas/admin/tools-page.js` toggle — `body: JSON.stringify({ enabled: newEnabled })`, no `/impact` call.
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js::impactMessage`, and the `/impact` fetch there: the editor's Save path.
- `the_one/interfaces/web/api.py::tool_config_impact` (`POST /api/tools/configs/{name}/impact`).
- `sorties/07-agent-tool-overrides/legs/05-notice-surfaces.md` — "Known gap, accepted under DD8".

## Corrective Action
`tools-page.js` `handleToolToggle`: an enabling toggle first POSTs `{enabled: true}` to the existing `/api/tools/configs/{name}/impact`; with no agents it proceeds as before (now `applyToggle`); with agents it opens the same `App.confirmDialog` pattern as the editor ("Turning on {tool} affects N agents", list, "Turn on anyway" / "Cancel"); Cancel re-renders the tile so the tool stays off. A failed preview does not block (the PUT is the gate). The dialog body is the editor's `impactMessage`, moved to module scope in `tools-editor.js` and shared as `App.admin.toolsImpact.message`. No server change.

## Verification
Done: `test_turning_a_tool_on_lists_the_agents_it_narrows_first` and `test_turning_a_tool_on_that_narrows_nobody_has_no_dialog` in `tests/browser/test_flow_admin_tools_impact.py` (the first falsified: with the check short-circuited it fails). The `settings-tools` files `test_flow_admin_tools_grid`, `_grid_library`, `_editor_save`, `_impact` and `test_flow_settings_items` pass, and the static guards pass. The full `settings-tools` lane and `make test-unit` are left for the Flight Director's gate.

Review fixes: `tools-page.js` renders the list right after setting `toolsInFlight` (the switch is disabled while the preview is held) and again after the preview settles, so the grid's held-focus logic returns focus to the switch before the dialog opens; the switch is passed as the dialog's `opener` (`App.confirmDialog` supports `opts.opener`, `dialog.js` unchanged). `test_turning_a_tool_on_lists_the_agents_it_narrows_first` now holds the impact request, asserts the switch is disabled, then enabled with the dialog up, and focused after Cancel; falsified by removing the early render (fails). `tests/test_nav_guard_static.py` now allows `tools-page.js` as an `App.confirmDialog` caller (3 pass). Impact (5) and grid (12) browser files pass.

`tests/test_nav_guard_static.py` now allows `tools-page.js` as a confirm-dialog caller.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-` (this includes the `settings-tools` lane and the full `make test-unit` the Developer left to the gate).

Follow-ups logged from the reviews: squawk 0365 (focus return for mouse users on Safari, and a late dialog after leaving the page) and squawk 0366 (no browser tests for Esc, a failed impact preview, or focus after "Turn on anyway").

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues. The Accessibility Reviewer (Sonnet) raised minors; these were fixed (the review fixes above), and a second review confirmed.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
