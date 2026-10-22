# Leg: general-tab

**Status**: landed
**Flight**: [Agents on the library](../flight.md)

## Objective
Rebuild the General tab, the model picker, Test and the danger zone from library controls, inside the frame that leg 06a built. Leave General mounted once per identity, patched through its handles on same-identity Save, Cancel and refresh. `general-tab.js` and `agent-model-picker.js` reach zero sinks and zero allowance rows.

## Context
- **Leg 06a's binding rework** (identity, `patch`, the interim rebuild of the other panels, dirty tracking staying DOM-based). Read 06a's artifact and its flight-log entry.
- **Flight decisions:** DD3 (dangerZone `actions`), DD7 (General), DD8 (Test, the danger zone, armed labels), DD10, DD11.
- **Today** (re-locate by symbol): `general-tab.js` builds fields `#studio-name`, `-description`, `-provider`, `-model`, `-system-prompt`, `-retention-days` and `-max-iterations` with `data-field` and the classes `field-input`, `field-textarea`, `field-select` and `field-input-short`. Number inputs carry `min`/`max`. The tab also has:
  - `.model-loading`, `.model-capabilities` and the VRAM warning;
  - Test (`test-provider-btn`) with `.test-result` (`test-provider-result`);
  - a danger zone with Delete Agent and Purge now, armed through `handleDeleteEditor(btn)`/`handlePurgeHistory(btn)`, which call `App.confirmDelete` themselves.

## Acceptance Criteria
- [ ] **Fields.** General uses `App.ui.field` with `textInput`, `textarea` and `select`, plus number inputs, keeping today's ids, `data-field`, classes, labels, hints and placeholders. `min`, `max` and `field-input-short` are set after construction if the factory has no option for them. Info buttons go where today has them.
- [ ] **Mount once.** General mounts once per identity. `setAgent(agent)` patches its values on same-identity Save, on Cancel (a revert) and on refresh. 06a's `patch` and Cancel call it, and General is removed from 06a's interim rebuild list.
  - **Provider and model are covered by `setAgent`:** setting the provider select triggers the model refetch with `dataset.pendingValue` set to the stored model, and it resets the VRAM warning and the capability line.
  - A test: change the provider, then Cancel. Both selects and the capability line are restored.
- [ ] **The model picker** patches the model `<select>` options with DOM, never `innerHTML`:
  - it keeps today's option set and order, `dataset.pendingValue` (squawk 0156) and the `selectedIndex` rules;
  - the capability line keeps the `.model-capabilities` class (`test_flow_studio_openrouter_picker.py` reads it) and `model-ctx-chip`;
  - the VRAM warning is a `status` warning line or the same element with today's text, cleared without `innerHTML`;
  - the stale-guards use the mount slot's `isCurrent`.
- [ ] **Test** stays in the General panel next to the provider fields, not in the shell header (06a).
  - It is an `App.ui.button` at DD8's standard size, with the play icon and the label "Test", keeping the testid `test-provider-btn` (no registry churn).
  - Its disabled state stays owned by the picker's `recomputeTestDisabled`: disabled when no provider is selected.
  - Create mode has no Test.
  - The result is an `App.ui.status` line keeping the testid `test-provider-result`, with `data-state` (`ok`, `warning`, `fail`, `pending`). This replaces the `.test-result-*` classes.
  - `test_flow_agent_tabs.py:275-296` is rewritten to assert `data-state`.
- [ ] **The danger zone** is `App.ui.dangerZone({actions: [Delete Agent, Purge now]})`:
  - `handleDeleteEditor`/`handlePurgeHistory` become `onConfirm(revert)` callbacks, with no second `confirmDelete` call. Delete has no `beforeArm`.
  - The armed labels are "Confirm delete?" and "Confirm purge?".
  - The `[data-confirm-title]` span, `confirm-delete` and `confirm-lapsed` stay (the library dangerZone keeps them; verify).
  - `test_flow_agent_crud.py` (about `:160-166`) and `test_flow_studio_purge_now_button.py` (`:65`, `:88`, `:94`, `:118`, `:123`) are updated for the label case and any selector change.
  - The `.delete-btn`/`.purge-history-btn` class hooks are removed where nothing uses them.
- [ ] **Dirty.** Each General control's change goes through the panel-mount wiring (06a), and `checkDirty` keeps reading the DOM.
- [ ] **Zero.** `general-tab.js` and `agent-model-picker.js` have no sinks and no allowance rows (lowered from the printed dicts, with any rise reasoned). Stale header comments in `general-tab.js` are removed.
- [ ] **Captures:** `agent-general` to `…/m31-f2-after-06/`. The differences are the DD8 Test and danger-zone treatment only; anything else is fixed.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the `agents`, `routing` and `shared` lanes under netns.

## Verification Steps
- `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML" the_one/interfaces/web/static/js/areas/studio/{general-tab,agent-model-picker}.js` returns nothing.
- The lanes above.

## Implementation Guidance
Fields first (with `setAgent`), then the picker, then Test, then the danger zone. Run `test_flow_agent_tabs.py`, `test_flow_studio_openrouter_picker.py`, `test_flow_agent_crud.py` and `test_flow_studio_purge_now_button.py` after each step.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/{general-tab,agent-model-picker,agent-editor-controller}.js`, `css/components.css` (dead hooks).
- `tests/browser/test_flow_agent_tabs.py`, `test_flow_agent_crud.py`, `test_flow_studio_purge_now_button.py`.
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`, `the_one/agents.md`.

## Citation Audit
From the leg 06 design review (2026-10-21, post-split tree).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
