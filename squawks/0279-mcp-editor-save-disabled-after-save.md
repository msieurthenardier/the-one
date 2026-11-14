# Squawk 0279: The MCP editor's Save may render disabled on a dirty form right after a save

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: 2026-11-14

## Report
In the M31 F6 HAT-close run of `mcp-sensitive-headers-round-trip`, the capture `step-8-edited.png` showed this, taken right after the previous save while its toast was still showing:
- the form reads "Unsaved changes";
- Cancel is enabled;
- Save renders in the pale disabled colour.

Step 5's capture of a dirty form showed Save enabled, and the run passed, because step 8 clicks Cancel, not Save. Reproduce it first:
- it may be a transition caught mid-way;
- it may instead be a window after a save in which Save does not follow the dirty state, for example a busy flag cleared late.

If it does not reproduce, close the squawk with the evidence.

## Evidence
- Run log: `tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-28-14-36-06.md`, Orchestrator Notes ("Save looks disabled while the form is dirty"). The capture itself was ephemeral evidence and is gone; re-running step 8 reproduces the sequence.
- The editor is `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` on `App.ui.editorShell`. The dirty and busy state reach Save through the shell.

## Corrective Action
Not reproducible as a state defect; no product code changed. In `mcp-server-editor.js` the save path calls `reportDirty(isDirty())` then `setSaving(false)` synchronously on the response, and the shell (`ui/editor.js`) derives Save as `busy || !(dirty || cleanSave)` and Cancel as `busy || !(dirty || cleanCancel)`. The reported capture (Save pale, Cancel enabled, "Unsaved changes" shown) is not a reachable state of that formula (Cancel enabled implies not busy, dirty implies Save enabled). The likely cause is the capture landing inside the 250 ms `--motion-base` colour transition on `.btn-filled-primary` / `.btn-outlined-primary` as Save left its disabled style.

## Verification
Added `test_edit_right_after_a_save_keeps_save_enabled` (`tests/browser/test_flow_studio_mcp_editor_kv_chips.py`): holds the PUT, asserts Save is disabled in flight, releases it, edits at once with the toast showing, and asserts "Unsaved changes" with Save and Cancel enabled. It passes without any fix (as expected for a non-defect; so not falsifiable) and pins the behaviour. That test is the browser test the plan asked for: it saves, edits at once without waiting for the toast, holds the save response with `page.route`, and asserts Save is enabled.

The state cannot occur: Save and Cancel share one condition. The one regression test added passes without any fix, so it could not be falsified.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-` (this includes the `mcp` lane).

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
