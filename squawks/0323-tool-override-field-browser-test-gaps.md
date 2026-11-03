# Squawk 0323: Three tool-override field behaviours are verified only by code read

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
Sortie 07's flight review accepted three field-state paths on the agent editor's Built-in tools tab as verified by code read only. Add a browser test for each:
1. **A plain text field** (not a number or chip list): edit makes it own, and clearing it returns it to inherited, written back on blur.
2. **Paste** into a number or text field: it makes the field own, the same as typing.
3. **A 422 shown on a field that is then emptied:** the error clears, the field returns to inherited, and the `aria-describedby` ids stay correct.

## Evidence
- `sorties/07-agent-tool-overrides/flight-log.md`, the flight review's non-blocking notes, item (c): "Test gaps: a plain text field, paste, and a 422 shown on a field that is then emptied. Each was verified by code read."
- `the_one/interfaces/web/static/js/areas/shared/tool-override-state.js::touch`.
- Existing coverage: `tests/browser/test_flow_studio_tool_override_state.py`.

## Corrective Action
*(written at completion)*

## Verification
- The three tests are in `tests/browser/test_flow_studio_tool_override_state.py`, in the `agent-tabs` lane.
- Each test is falsified: it fails with the behaviour it pins reverted.
- The `agent-tabs` lane passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
