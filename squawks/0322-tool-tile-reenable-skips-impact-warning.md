# Squawk 0322: Re-enabling a built-in tool from its Settings tile adds agent notices with no impact warning

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
Sortie 07 shows the agents a save would narrow before Settings › Built-in tools saves a tightening. That warning runs only on the tool editor's Save. The tile switch sends an `enabled`-only PUT with no impact check. Notices are scoped to enabled tools, so re-enabling a tool can surface new agent notices with no warning first. This is the gap accepted under DD8 (sortie 07 debrief, Action Items). The fix: run the existing impact check before an enabling toggle, and confirm the same way the editor does when it returns agents.

## Evidence
- `the_one/interfaces/web/static/js/areas/admin/tools-page.js` toggle — `body: JSON.stringify({ enabled: newEnabled })`, no `/impact` call.
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js::impactMessage`, and the `/impact` fetch there: the editor's Save path.
- `the_one/interfaces/web/api.py::tool_config_impact` (`POST /api/tools/configs/{name}/impact`).
- `sorties/07-agent-tool-overrides/legs/05-notice-surfaces.md` — "Known gap, accepted under DD8".

## Corrective Action
*(written at completion)*

## Verification
- Before an enabling toggle runs, the browser test in `settings-tools` lists each agent the change would narrow.
- Cancelling the dialog leaves the tool off.
- A toggle that narrows no agent shows no dialog.
- `make test-unit` and the `settings-tools` lane pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
