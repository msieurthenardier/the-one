# Leg: agent-tools-on-fields

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Move the agent editor's Tools tab and `agent-form-data.js` onto the shared field module built in leg 05b, then delete `tool-override-fields.js` and its alias. Along the way:
- inline boolean labels (A10, ledger row 10);
- humanised custom preset values (A8, row 8);
- client-side validation of agent number overrides, which blocks the agent Save;
- a fix so an override on a setting that leg 05a hid is never dropped;
- squawk 0223's rule kept.

Split from leg 05b at its design review (2026-10-23).

## Context
- **Flight decisions:** DD13 (amended), DD5, DD7, DD11.
- **Today's agent-side code:**
  - `tools-tab.js:155` calls `App.studio.toolOverrideFields.render`, and `:167-171` warns on a stored override for a field the schema no longer marks as overridable;
  - `agent-form-data.js` about `:211-245` walks `[data-tool-override-tool][data-tool-override-field]` through `App.adminFormHelpers.readFieldValue`, builds the "loaded tools" set (squawk 0223), and keeps never-opened tools' stored overrides;
  - the dead MCP override walk follows (`:247-262`).
- **The hidden-override hole (05b design review issue 2).** For every *loaded* tool, the walk rebuilds `overrides[toolName]` from the rendered fields only. A field hidden by 05a's `config_fields` never renders, so opening that tool's Overrides panel and saving would **drop** its stored override (the same class of defect as squawks 0223 and 0248).
  - **Fix:** for each loaded tool, carry over every stored override key that has no rendered field.
  - Silently: it stays stored and still applies at resolve time, and it is recorded in `agents.md`.
  - Test-first: store an override on `delete_file`'s `read_size_cap_bytes` through the API, open the panel, change another field, save; the stored key survives.
- **Blocking the agent Save** (05b review issue 3). `collectFormData()` (`agent-form-data.js:85`) must stay pure: it also feeds `checkDirty` and the snapshot.
  - Add `formData.blockingError()`, which returns the first invalid override field (its message and control) from the live handles, or `null`.
  - In `agent-editor-controller.js` `save()` (about `:519`), call it right after `collectFormData()`, for create and edit. If it is non-null:
    - `setEditorError_` (about `:77`, `shell.setError`) with a message naming the tool and the field;
    - open that tool's Overrides `<details>`;
    - focus the control;
    - return before `focusAfter.begin` and the fetch.
  - The field shows its error live on change, and clears it when the value becomes valid.
- **Inline booleans** change the agent tab's layout (ledger row 10): check the `agent-tabs` tests that find a boolean through `.field-group` and retarget them to the role.

## Inputs
- Leg 05b landed (`static/js/areas/shared/tool-config-fields.js`, both modes tested on a harness).

## Outputs
- `tools-tab.js` on `App.toolConfigFields` in agent mode; `agent-form-data.js` reading through `App.toolConfigFields.readValue`, carrying hidden overrides over, with the dead MCP walk deleted (`var mcpOverrides = {}` kept); `formData.blockingError()` and its use in `save()`.
- `static/js/areas/studio/tool-override-fields.js` deleted, with its `index.html` tag; the `App.studio.toolOverrideFields` alias gone. `test_flow_studio_tool_override_fields.py:44` retargeted to the new path.
- Tests (`agent-tabs` lane), each failing first where it fixes something:
  - the hidden-override carry-over;
  - agent number validation ("1.5", "12abc", blank, "12"), including a collapsed panel: the Save opens it and focuses the field, and no PUT is sent;
  - squawk 0223 (a description-only Save sends no `tool_overrides`; opening one tool's panel keeps the others' stored overrides);
  - A8 and A10 on the tab.
- Captures of `agent-tools`, compared with the before set (rows 8, 10, 28 and the 05a rows).

## Acceptance Criteria
1. `git grep -n "toolOverrideFields\|tool-override-fields" the_one/ tests/` finds no live reference. `App.adminFormHelpers.readFieldValue` has no caller under `areas/studio/`.
2. **The hidden-override carry-over** is test-proven: the test fails before, passes after.
3. **Agent number validation:** "1.5" and "12abc" each show "Enter a whole number." on the field with `aria-invalid`. Save then sends no PUT, shows the editor error naming the tool and the field, opens the panel if it was collapsed, and focuses the field. Blank is skipped. "12" sends 12.
4. **Squawk 0223's rule holds** (its existing tests pass unchanged, plus the two cases above).
5. **The agent tab behaves as before** apart from ledger rows 8, 10 and 28 and the 05a text. The `agent-tabs` and `agents` lanes pass, with assertions retargeted only for those rows.
6. The unit tier, the static guards (no sinks, no allowance rows in the new or changed files), the line guard and the `index.html` order test pass.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_area_module_size.py tests/test_index_asset_cache_busting.py -q -x --timeout 120`.
- Lanes `agent-tabs` and `agents` under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- The capture compare; `make test-unit` once.

## Implementation Guidance
1. The carry-over test and fix first (the data-loss risk).
2. Switch `agent-form-data.js` to `readValue`, and delete the MCP walk.
3. Switch `tools-tab.js`, with the inline boolean and A8.
4. Agent number validation and `blockingError` in `save()`, test-first.
5. Delete the old module and alias; retarget the path test.

## Edge Cases
- **The console warning at `tools-tab.js:167-171`:** keep it for a field that is in the schema but not overridable. It cannot fire for a 05a-hidden field (that field is not in `schema.properties`). Record this.
- **An invalid value in a panel the operator then collapses:** `blockingError` still finds it (the handles are live while the tool is loaded).
- **Create mode:** the same `blockingError` path applies before the POST.

## Files Affected
- `static/js/areas/studio/tools-tab.js`, `agent-form-data.js`, `agent-editor-controller.js`, `static/js/areas/studio/tool-override-fields.js` (deleted), `static/index.html`.
- `tests/browser/test_flow_studio_tool_override_fields.py`, `test_flow_studio_tools_overrides.py`, `test_flow_studio_tool_overrides_preserved.py`, `test_flow_studio_tools_tab_patch.py`, `test_flow_studio_time_tool.py` (as needed), plus new tests in `agent-tabs` (an `agent_tabs_pat` glob match: name them `test_flow_studio_tools_*`).
- `the_one/agents.md`, CLAUDE.md (one sentence on the shared module), the flight log.

## Citation Audit
- `tools-tab.js:155`, `:167-171`; `agent-form-data.js` about `:211-262`: verified (FD read and grep).
- `agent-form-data.js:85` `collectFormData` and its uses at `:26`; `agent-editor-controller.js` about `:519` `save()`, about `:77` `setEditorError_`: from the 05b design review.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
