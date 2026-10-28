# Squawk 0279: The MCP editor's Save may render disabled on a dirty form right after a save

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*
A browser test in the `mcp` lane: save, then edit a field at once (without waiting for the toast), then assert Save is enabled. Hold the save response with `page.route` so the window can be reached deterministically.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
