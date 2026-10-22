# Squawk 0228: Save pressed before the model list loads stores an empty model

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-21
**Completed**: —

## Report
If Save is pressed on the agent editor after the editor appears but before `GET /api/providers/{id}/models` has returned, the request carries `llm_model: ""`. The model select still holds its placeholder, so the agent's stored model is cleared. This is pre-existing: the same happens at `HEAD` (9369fcc), before Mission 31 Flight 2's General-tab rewrite. It is easiest to hit on a slow provider (Ollama, OpenRouter) or a loaded host.

A plausible fix is to keep Save disabled until the first model list for the current provider has loaded (or failed). Another is to keep the stored model as a selected option while the list is loading. Pick one and pin it with a test that holds the models response.

## Evidence
- Found on 2026-10-21 while investigating a one-off agents-lane failure: the request body of a Save made inside the window shows `llm_model: ""`.
- The pins that hold `/api/providers/*/models`: `tests/browser/test_flow_agents_focus_after.py::test_save_before_the_first_model_list_lands` (it asserts the form settles clean, not the request body).
- The code: `the_one/interfaces/web/static/js/areas/studio/agent-model-picker.js` (`wireEditorEvents`, the model fetch and `pendingValue`) and `agent-form-data.js` `collectFormData` (it reads the select's value).

## Corrective Action
*(written at completion)*

## Verification
- A browser test that holds the models response and presses Save sees either Save disabled, or a PUT body with the stored `llm_model`, never `""`.
- `test_flow_agents_focus_after.py` and `test_flow_agent_general_tab.py` pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
