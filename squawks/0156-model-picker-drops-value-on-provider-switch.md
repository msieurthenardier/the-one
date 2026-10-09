# Squawk 0156: Agent editor model picker drops the chosen model on a provider switch

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
In the agent editor, choosing a model under one provider and then switching the Provider select to another leaves the Model select empty ("Choose a model" selected). The code that surfaces a carried-over value as a visible "(custom)" option (`fetchModelsForProvider`) never sees the old value on a provider switch, so a model the new provider does not list is silently lost instead of flagged. The "(custom)" fallback does work for a saved value (`dataset.pendingValue`), which is the only path that reaches it.

Reproduce: open a new agent, pick an OpenRouter provider and `anthropic/claude-3.5-sonnet`, then switch Provider to an Ollama provider. Expected per the code comment ("carried-over value ... visible '(custom)' option"): `anthropic/claude-3.5-sonnet (custom)` stays selected. Observed: Model value is `""`.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` `wireEditorEvents`: the provider `change` handler runs `modelEl.selectedIndex = 0` before `fetchModelsForProvider`, which then reads `currentVal = selectEl.dataset.pendingValue || selectEl.value` and gets `""`.
- `tests/browser/test_flow_studio_openrouter_picker.py::test_picker_preserves_value_across_type_switch_as_custom` (rewritten in Mission 26 F01 L03) pins only what holds today and notes this squawk.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
