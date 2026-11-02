# Squawk 0228: Save pressed before the model list loads stores an empty model

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-21
**Completed**: 2026-11-02

## Report
If Save is pressed on the agent editor after the editor appears but before `GET /api/providers/{id}/models` has returned, the request carries `llm_model: ""`. The model select still holds its placeholder, so the agent's stored model is cleared. This is pre-existing: the same happens at `HEAD` (9369fcc), before Mission 31 Flight 2's General-tab rewrite. It is easiest to hit on a slow provider (Ollama, OpenRouter) or a loaded host.

A plausible fix is to keep Save disabled until the first model list for the current provider has loaded (or failed). Another is to keep the stored model as a selected option while the list is loading. Pick one and pin it with a test that holds the models response.

## Evidence
- Found on 2026-10-21 while investigating a one-off agents-lane failure: the request body of a Save made inside the window shows `llm_model: ""`.
- The pins that hold `/api/providers/*/models`: `tests/browser/test_flow_agents_focus_after.py::test_save_before_the_first_model_list_lands` (it asserts the form settles clean, not the request body).
- The code: `the_one/interfaces/web/static/js/areas/studio/agent-model-picker.js` (`wireEditorEvents`, the model fetch and `pendingValue`) and `agent-form-data.js` `collectFormData` (it reads the select's value).

## Corrective Action
Chose to keep the stored model selected while the list loads (not to disable Save, which would be new operator-visible behaviour and block unrelated saves on a slow provider). `agent-model-picker.js::fetchModelsForProvider` now sets the select to one selected option holding the stored (or carried) model before the fetch, and on a failed load keeps it and shows "Failed to load models" in the loading line instead of replacing the option with an empty-valued one. With no model the placeholders are unchanged.

## Verification
- A browser test that holds the models response and presses Save sees either Save disabled, or a PUT body with the stored `llm_model`, never `""`.
- `test_flow_agents_focus_after.py` and `test_flow_agent_general_tab.py` pass.
- Done (Mission 34 Flight 2 Leg 4): five new tests in `test_flow_agents_focus_after.py` (held list, failed list, provider switch with a failed list, new agent). The Save-while-loading, failed-load and provider-switch tests failed before the fix (`llm_model: ""`) and pass after. `test_flow_agents_focus_after.py` 14 passed; the agents lane result is in the flight log.

## Sign-Off
**Reviewer**: Mission 34 Flight 2 flight Reviewer (Sonnet) and Accessibility Reviewer (Sonnet), 2026-11-02; fix-pass re-review (Haiku)
**Verdict**: confirmed (`[HANDOFF:confirmed]`), no blocking issues
**Commit**: the `flight/2` commit of Mission 34 Flight 2 (`agent-save-keeps-model` leg)

## Disposition
- **Routed** (2026-11-02, operator decision at the Mission 34 Flight 1 debrief): taken into [Mission 34 Flight 2](../missions/34-maintenance/flights/02-data-safety-and-routine-observability/flight.md) as leg `agent-save-keeps-model`. It is a silent data-loss path like the flight's connector-peer leg; the design call (disable Save vs keep the stored model) is settled at that leg's design. Squawk 0229 is re-tested after it lands.
