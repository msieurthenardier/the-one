# Squawk 0371: "Forget tools list" comes back still armed after it is used once

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: 2026-11-17

## Report
In the Library MCP server editor, the operator pressed "Forget tools list" on several HTTP servers. The button disappeared, which is expected while there is no cached tools list. The operator then pressed Test, the tools loaded again, and the button still did not return. It has stayed gone on those servers since.

Expected: once a Test has reloaded the tools list of an HTTP server with no sign-in, "Forget tools list" is shown again, at rest (not armed).

Reproduce (reported, not yet reproduced by the crew): open an HTTP server that shows "Forget tools list", press it twice (arm, confirm), then press Test and wait for the tools. The button should be visible and read "Forget tools list".

One defect on this path is confirmed by reading: the success path of the delete never reverts the two-step confirm, so the button is hidden while still armed. Reading does not explain why the button stays hidden after a Test; the first step is to reproduce that in a browser against a real Test (not a seeded cache).

Narrowed on 2026-11-17, after the reproduction: against a real fixture server with no sign-in the button does come back after a Test, but still armed ("Forget tools list?", one click commits). This squawk covers that confirmed defect only. The operator's symptom, the button staying hidden after a Test, did not reproduce and is carried as squawk 0373.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-status.js::updateButtons` — Forget is shown for `type === 'streamable-http'`, `oauth_active !== true` and a `_cache` with `auth_posture` or `tools`; `syncButton` only toggles `hidden` on the button built once.
- `mcp-connection-status.js::runDelete` — the `.catch` calls `revert()`; the success branch never does, so `.confirm-delete` and the "Forget tools list?" label stay on the hidden button (`ui/confirm.js`: only `revert()` removes them). When the button is shown again it is still armed, and one click commits.
- `mcp-connection-status.js::recordLocally` and `syncFromServer` — after a clean Test the local cache gets `tools`, then the refetched record replaces it; by reading, both should show the button again.
- `tests/browser/test_flow_studio_mcp_editor_status.py::test_forget_tools_list_patches_in_place` — ends when the button hides; no test covers Forget, then Test, then the button's return.
- `the_one/interfaces/web/api.py::reset_mcp_connection` — the one route behind both Reset and Forget: it drops `_cache`, strips the sign-in secrets and forgets the remembered protocol revision.

## Corrective Action
`mcp-connection-status.js::runDelete` now calls `revert()` in its success branch (after the identity guard, before the record is cleared), so the Forget (and Reset) button is put back at rest, "Forget tools list" with no `.confirm-delete`, before it is hidden. A button that is shown again therefore needs the normal two clicks. The fix stays inside the editor's connection-status module; `App.ui.confirm` is untouched.

Not explained: the reported "stays hidden after Test". In a real browser run against the real rich fixture MCP server (`tests.fixtures.mcp.rich_http_server --mode ok`, no sign-in), Forget then Test showed the button again after the Test. It was visible but armed ("Forget tools list?", class `confirm-delete`), which is the confirmed defect. The "never returns" variant did not reproduce, so no cause is claimed for it; it is carried as squawk 0373, whose first step is to read the server record (`GET /api/mcp-sources/{id}`: `oauth_active`, `config._cache`) on an affected server.

## Verification
- Added `test_forget_then_test_brings_the_button_back_at_rest` (with a `real_http_server` fixture, a subprocess of the rich fixture server on a free loopback port) to `tests/browser/test_flow_studio_mcp_editor_status.py`: Test, Forget twice, Test again, then the button is visible, reads "Forget tools list" and is not `confirm-delete`.
- Falsified: without the fix it failed on the label ("Forget tools list?", class `confirm-delete`); with the fix the file passes (33 passed).
- Static guards `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_ownership`: 419 passed. ruff check and format clean.
- `mcp-connection` lane (`THE_ONE_TEST_NETNS=1`, `-x --timeout 60`): 95 passed, exit 0, as the Developer reported.

## Sign-Off
**Reviewer**: independent Reviewer (Haiku tier: the diff touches no security-sensitive surface), who confirmed the diff with `[HANDOFF:confirmed]` on 2026-11-17 with no blocking issues. It re-ran the test file (33 passed), the static guards (419 passed) and ruff; it did not re-run the `mcp-connection` lane or the falsification. Two non-blocking notes on the new fixture are carried as squawk 0374. One residual it could not prove either way: if the editor ever shows a different server while a delete is in flight, the early return skips the revert; no such rebind exists today.
**Verdict**: confirmed
**Commit**: the `squawk/0371` commit on `squawk/0371-forget-tools-list-returns-armed`
