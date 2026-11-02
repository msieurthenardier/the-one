# Leg: agent-save-keeps-model

**Status**: completed
**Flight**: [Data safety and routine observability](../flight.md)

## Objective
An agent Save pressed while the model list is still loading (or after it failed to load) sends the stored model, never `llm_model: ""`, so the agent's stored model is not cleared (squawk 0228).

## Context
- Added to this flight at the Mission 34 Flight 1 debrief (operator decision 2026-11-02). Squawk 0228 is `open` with Disposition "Routed" to this leg.
- **The defect.** `static/js/areas/studio/general-tab.js::setAgent` resets `#studio-model` to one disabled placeholder (`'Select a provider first'`, value `""`). The controller then calls `wire_` (`agent-model-picker.js::wireEditorEvents`), which sets `modelSelect.dataset.pendingValue = cfg.llm_model` and calls `fetchModelsForProvider(cfg.provider_config_id)`. Until `GET /api/providers/{id}/models` returns, the select's value is `""`, and `agent-form-data.js::collectFormData` reads the select's value, so a Save in that window sends `llm_model: ""`. The failure path (`.catch`) also replaces the options with one disabled `'Failed to load models'` option of value `""`, so a Save after a failed load clears the model too.
- **Design call (Flight Director, leg design): keep the stored model selected while loading**, not "disable Save until the list loads".
  - Disabling Save is a new operator-visible behaviour, which the mission constraint ("no new behaviour visible to the operator beyond the log lines and the preserved peers") forbids without an amendment. It also blocks saving an unrelated edit when a provider is slow or down.
  - Keeping the stored model selected changes only what the select shows during the load window: the stored model's id instead of an empty placeholder. That is the stored value the operator already has, which the flight note says fits the constraint.
- **The rule.**
  - **Loading** (`fetchModelsForProvider` with a provider id and a non-empty `currentVal`, i.e. `pendingValue || selectEl.value`): before the fetch, set the select's options to one selected, enabled option `currentVal` (label: the id itself; the "Loading models…" line beside it is unchanged). With no `currentVal` (a new agent, or a provider with no stored model) keep today's placeholder.
  - **Loaded:** unchanged (the list, the stored or carried value selected, or `(custom)` when absent).
  - **Failed:** with a `currentVal`, keep it as the one selected option and show "Failed to load models" in the loading line (`.model-loading`) instead of as the option's text. With no `currentVal`, today's disabled "Failed to load models" option stays.
  - **Aborted** (provider switched mid-flight): unchanged (the next fetch paints).
  - **Provider switch:** the change handler already carries the current model in `pendingValue`; the loading option then shows it, and Save during that load sends the carried model with the new provider, which is what the loaded state would show as `(custom)` anyway.
- **Dirty state.** The controller takes the snapshot after `wire_` (`renderEditor_`: `wire_(data, isCreate, agent); state.snapshot = getFormSnapshot();`, and the same in `patchEditor_`), and `fetchModelsForProvider` runs synchronously inside `wire_`, so the loading option is in place before the snapshot and the form reads clean while loading. Verify it; the success path's existing re-snapshot when clean stays.
- **Existing pins.** `tests/browser/test_flow_agents_focus_after.py::test_save_before_the_first_model_list_lands` holds the models route and saves; it asserts the form settles clean but not the PUT body. Grep `tests/browser/` for `"Failed to load models"`, `"Select a provider first"` and `#studio-model` value assertions taken during loading, and update any pin the new rule breaks in this leg (rename over delete).
- **0229.** After the fix, re-run `test_flow_agents_focus_after.py::test_agent_save_never_steals_focus_the_user_moved` 10 times isolated and record the result in squawk 0229 (its suspected link to 0228); 0229 stays open unless a root cause is shown.

## Design Review
2026-11-02, Developer (Sonnet), cycle 1: **approve with changes**. Verified: the snapshot is taken after the synchronous loading change on first open, patch and provider change; `collectFormData` reads only `value`; no other caller of `fetchModelsForProvider`; no existing test pins the loading or failure texts in the agent editor. Applied: AC2 asserts the form is clean after a failed load (a dirty-state change from today), AC2b provider switch with a failed load (accepted semantics), AC4 made concrete (create mode, no existing pin) plus an option-count check after loading, the comment location in `setAgent`. In AC1 capture the PUT with a URL filter (`/api/agents/`). No second cycle: no design change.

## Inputs
- Legs 1–3 landed (no shared files).
- Squawks 0228 (`open`, routed here) and 0229 (`open`).

## Outputs
- `agent-model-picker.js::fetchModelsForProvider` (loading and failure paths); `general-tab.js`: the comment in `setAgent` ("until it lands the select shows its placeholder") updated.
- Browser tests in `tests/browser/test_flow_agents_focus_after.py` or `test_flow_agent_general_tab.py` (`agents` lane).
- `the_one/agents.md` agent editor / model picker paragraph: one sentence on the loading rule.
- Squawk 0228: Corrective Action and Verification written, status `completed`, `**Completed**: 2026-11-02`, Sign-Off left for the flight review. Squawk 0229: a dated line with the 10-run result.

## Acceptance Criteria
- [ ] **AC1 — Save during load keeps the model.** A browser test holds `**/api/providers/*/models`, opens an agent with a stored model, edits the description, presses Save, and asserts the captured PUT body's `llm_model` equals the stored model (`page.expect_request` + `post_data_json`); after releasing the route, `GET /api/agents/{name}` still has the stored model. Falsified: with the loading-option change removed (by editing) the test fails with `llm_model: ""`.
- [ ] **AC2 — Save after a failed load keeps the model.** The models route answers 500; the select shows the stored model selected, the loading line reads "Failed to load models"; Save sends the stored model. With no edit, the form reads clean after the failure (Save disabled, no `editor-unsaved` caption): today a failed load reads dirty because the select moved to `""`, and the fix removes that. Falsified the same way.
- [ ] **AC2b — provider switch, failed load.** Switch the agent from provider A to B with B's models route answering 500: the select keeps A's model as the one selected option and Save sends it with B (accepted: the same value the loaded state would show as `(custom)`; the server accepts any non-empty model string, as today for `(custom)`).
- [ ] **AC3 — clean while loading.** With the route held, the editor shows Save disabled and no `editor-unsaved` caption (the form is clean), and the select's value is the stored model.
- [ ] **AC4 — no stored model.** A new agent (create mode, `#agents/~new`, models route held) shows the select at `""` with "Select a provider first" or today's equivalent while loading; and with a 500 shows today's "Failed to load models" option. No existing test pins this (review grep), so add one. And one new test that reaches the loaded state after the loading option asserts the option count matches the loaded list (no leftover loading option).
- [ ] **AC5 — existing behaviour.** `test_flow_agents_focus_after.py`, `test_flow_agent_general_tab.py`, `test_flow_studio_openrouter_picker.py` and the provider-switch `(custom)` test (squawk 0156; grep `custom`) pass, updated only where they pinned the old loading/failure text, each update named in the flight log.
- [ ] **AC6 — suites green.** `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents` passes; the static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`) pass; `make test-unit` passes (not concurrently with a browser run).
- [ ] **AC7 — records.** agents.md sentence; squawk 0228 completed with Corrective Action and Verification; 0229's 10-run result recorded; flight log entry.

## Verification Steps
- AC1–AC5: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/<file>::<test> -x`; falsify AC1 and AC2 by editing; then the `agents` lane.
- 0229: a shell loop of 10 isolated runs recording each exit code.
- AC6/AC7: the commands above; read the docs and squawks.

## Implementation Guidance
1. Read `fetchModelsForProvider`, `wireEditorEvents`, `general-tab.js::setAgent` and `agent-form-data.js::collectFormData` end to end.
2. In `fetchModelsForProvider`, after computing `currentVal` and the `!providerId` early return, when `currentVal` is non-empty set `selectEl.replaceChildren(optionNode(currentVal, currentVal, { selected: true }))` before the fetch. Keep `pendingValue` as is (the success path consumes it).
3. In `.catch` (non-abort, live): with `currentVal`, keep or re-set the single selected `currentVal` option and set `loadingEl.textContent = 'Failed to load models'`; without, today's code.
4. Write the AC1/AC2/AC3 tests first against HEAD to see them fail, then the fix. AC4 may be covered by existing tests; name them.
5. Update the comment in `setAgent` (above its `replaceChildren`), agents.md, the squawks and the flight log.

## Edge Cases
- `currentVal` with characters that need escaping: `optionNode` sets `value` via DOM, so no escaping issue; the existing `CSS.escape` in the success path stays.
- The provider select is empty (no providers): the `!providerId` branch is unchanged.
- A stale fetch arriving after a provider switch is dropped by the existing `_activeProviderId` guard; the loading option of the newer fetch stays.
- The VRAM check (`checkVramForModel`) reads the select's value; with the stored model selected during load it may run against it, which is what it does once the list lands. No change needed; note if a test shows otherwise.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/agent-model-picker.js` (and the `general-tab.js` comment)
- `tests/browser/test_flow_agents_focus_after.py` and/or `tests/browser/test_flow_agent_general_tab.py`; any test pinning the old texts
- `the_one/agents.md`; `squawks/0228-*.md`, `squawks/0229-*.md`; the flight log

## Citation Audit
Checked at `b497312f` (Flight Director, 2026-11-02): `general-tab.js::setAgent` :332 with `modelSelect.replaceChildren(option('', 'Select a provider first', { disabled: true, selected: true }))` and `delete modelSelect.dataset.pendingValue` — verified. `agent-model-picker.js::fetchModelsForProvider` :101 (`var currentVal = selectEl.dataset.pendingValue || selectEl.value;` :117, the success path's `(custom)` option and re-snapshot when `!state.dirty`, the `.catch` failure option `'Failed to load models'`) — verified; `wireEditorEvents` :219 sets `pendingValue = cfg.llm_model` then calls `fetchModelsForProvider` :263-265 — verified. `agent-editor-controller.js` `wire_(data, isCreate, agent); state.snapshot = getFormSnapshot();` :242-245 and in `patchEditor_` :254-260 — verified. `test_flow_agents_focus_after.py::test_save_before_the_first_model_list_lands` :151 asserts settle-clean, not the PUT body — verified.
