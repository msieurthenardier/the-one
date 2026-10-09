# Squawk 0156: Agent editor model picker drops the chosen model on a provider switch

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-09

## Report
In the agent editor, choosing a model under one provider and then switching the Provider select to another leaves the Model select empty ("Choose a model" selected). The code that surfaces a carried-over value as a visible "(custom)" option (`fetchModelsForProvider`) never sees the old value on a provider switch, so a model the new provider does not list is silently lost instead of flagged. The "(custom)" fallback does work for a saved value (`dataset.pendingValue`), which is the only path that reaches it.

Reproduce: open a new agent, pick an OpenRouter provider and `anthropic/claude-3.5-sonnet`, then switch Provider to an Ollama provider. Expected per the code comment ("carried-over value ... visible '(custom)' option"): `anthropic/claude-3.5-sonnet (custom)` stays selected. Observed: Model value is `""`.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` `wireEditorEvents`: the provider `change` handler runs `modelEl.selectedIndex = 0` before `fetchModelsForProvider`, which then reads `currentVal = selectEl.dataset.pendingValue || selectEl.value` and gets `""`.
- `tests/browser/test_flow_studio_openrouter_picker.py::test_picker_preserves_value_across_type_switch_as_custom` (rewritten in Mission 26 F01 L03) pins only what holds today and notes this squawk.

## Corrective Action
`the_one/interfaces/web/static/js/areas/studio.js`, `wireEditorEvents` provider `change` handler: before `modelEl.selectedIndex = 0`, the current model value is captured into `modelEl.dataset.pendingValue` (or the key deleted when the value is empty). `fetchModelsForProvider` already reads `dataset.pendingValue || value` and deletes `pendingValue` after a successful list, so a model the new provider does not list now surfaces as a selected "(custom)" option, and the carried value is consumed by that fetch (same lifecycle as the saved-value path).

Tests: `tests/browser/test_flow_studio_openrouter_picker.py::test_picker_preserves_value_across_type_switch_as_custom` restored to the intended contract (custom + selected after the switch; listed and selected after switching back); new `test_picker_stale_carried_value_does_not_resurface` (A, away, back, B, away -> B custom, no A). Both stub the Ollama `/models` response, since no Ollama daemon runs in the test environment (the real fetch fails and the editor shows "Failed to load models").

Observation, not changed: when the new provider's model fetch fails, the failure path replaces the select and the carried value is dropped; out of scope here.

## Verification
- Picker file: 8 passed with the fix. Falsified: with the capture disabled, both new/restored tests failed (6 others passed); fix restored.
- Agents lane (`--lane agents -q`): 156 passed.
- Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`): 261 passed.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the self-configuration credential-isolation tests and a CI install script). Confirmed the `pendingValue` lifecycle: it is cleared on fetch success, and the next `change` deletes it after a failed fetch, so a stale value cannot resurface. The saved-value path is unchanged. Picker file 8 passed, static guards 261 passed. A non-blocking note: a rapid A→B→C switch before B's fetch completes drops (never resurrects) the carried value.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-09` on branch `squawk/turnaround-2026-10-09`
