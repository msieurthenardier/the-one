# Leg: delete-agent-dialog

**Status**: completed
**Flight**: [Deleting an agent deletes its chats](../flight.md)

## Objective
The General tab's "Delete agent" opens a modal confirmation that names the agent and its chat count. Delete stays disabled until the operator ticks "I understand this will delete all of this agent's chat history". Deleting then runs the cascading delete from leg 1.

## Context
- Read the flight's DD5, DD6 and DD8 (UI documents) first. Option A is the operator-approved mockup, drawn in DD6.
- Leg 1 is landed in the working tree: `DELETE /api/agents/{name}` returns `{"status": "ok", "chats_deleted": N}` and deletes the chats. The UI-driven delete tests in lanes `agents` and `routing` still click the old two-step and are this leg's to move. The lane `chats` tests were moved by leg 1.
- The worktree `/home/cprch/projects/the-one-sortie-20` has its own venv, now Python 3.12 (it was 3.13 during leg 1). Leg 1 is landed and uncommitted in this tree; touch its files only where this leg's criteria require.
- No control-library change: the dialog is a composition that owns its buttons (precedent: `static/js/areas/studio/routines-custom-recurrence.js:162-200`), opened from the danger zone's existing `beforeArm` hook. `static/js` here means `the_one/interfaces/web/static/js`.
- The Purge action keeps its two-step. So does every other entity's delete; the string "Confirm delete?" is used by many of them, so search by the testid `delete-agent-btn`, not by that string.

## Inputs
- `static/js/areas/studio/general-tab.js:226-257`: the danger zone with Purge (`purge-history-btn`) and Delete (`delete-agent-btn`, `onConfirm(revert) → callbacks.onDelete(revert)`).
- `static/js/areas/studio/agent-editor-controller.js:339-373`: `handleDeleteEditor(revertFn)`, with the DD8 focus and navigation after a delete.
- `static/js/ui/editor.js:373+`: `App.ui.dangerZone`, whose `beforeArm(proceed)` runs on the first click and arms only if `proceed()` is called (`:417-425`).
- `static/js/ui/modal.js` (`footerEnd`, `initialFocus`, `testid`, `onClose`, `close()`; Escape and `cancel` close it), `static/js/ui/choice.js` (`App.ui.checkbox`), `static/js/ui/button.js` (`variant: 'danger'`), `static/js/store.js` (`App.store.get(name, {force})`, `invalidate`).
- How `index.html` loads area scripts: find where `routines-custom-recurrence.js` or `general-tab.js` is listed, and add the new file the same way.

## Outputs
- A new `static/js/areas/studio/agent-delete-dialog.js` (exposing, for example, `App.studio.agentDeleteDialog.open({name, opener, onDeleted})`; the name is at the Developer's discretion), loaded in the page.
- `general-tab.js`, `agent-editor-controller.js` rewired; the guide, the testid registry and the behavior spec text updated; browser tests added and moved.

## Acceptance Criteria
- [ ] **AC1 (opening).** One click on `delete-agent-btn` opens the dialog without arming the button (it gains no `confirm-delete` class, and its label does not change).
  - A second click on the opener while the count is being read opens nothing more (one dialog).
  - The Purge button's two-step behaves exactly as before (its existing tests pass unchanged).
- [ ] **AC2 (content, Option A).** The dialog (`testid` `delete-agent-dialog` on the modal) has:
  - the title `Delete "{name}"?`;
  - the message from DD6's four cases (more than one chat, one chat, no chats, count unreadable), with the count from a fresh `App.store.get('sessions', {force: true})` filtered by `agent_name === name`;
  - the checkbox `delete-agent-ack-checkbox`, labelled exactly "I understand this will delete all of this agent's chat history";
  - in the footer, Cancel (`delete-agent-cancel-btn`) and Delete (`delete-agent-confirm-btn`, variant `danger`), in that order.
- [ ] **AC3 (the gate).** Delete is `disabled` on open, enabled when the box is ticked, and disabled again when it is unticked. The checkbox is required at 0 chats too. Delete's disabled state is announced: it has an `aria-describedby` pointing at the message or the checkbox, as the provider delete does.
- [ ] **AC4 (focus and dismissal).** Cancel has focus on open. Escape or Cancel closes the dialog with no request sent, and the agent and its chats are unchanged (assert through the API). Focus returns to `delete-agent-btn`. A backdrop click does nothing.
- [ ] **AC5 (success).** With the box ticked, Delete:
  - disables Delete and the checkbox while the request runs;
  - closes the dialog first;
  - invalidates the `sessions` and `agents` store entries;
  - runs the existing post-delete `loadAll`, navigation to the Agents root and focus to the nearest row (M25 DD8; the existing assertions in `test_flow_agents_list.py` for that focus must still hold);
  - flashes "Deleted {name} and N chats." ("1 chat" for one, "Deleted {name}." for zero), with N from the response's `chats_deleted`.

  Afterwards the agent's chats are gone from the Chats list (assert through the UI or the API).
- [ ] **AC6 (failure).** When the request fails (intercept it with a Playwright route returning 500 with a `detail`), the dialog stays open, an error flash shows the detail inside it, and Delete and the checkbox are enabled again. A retry that succeeds then behaves as AC5.
- [ ] **AC7 (Escape mid-request).** With the request held (a Playwright route that waits), Escape closes the dialog. When the request then completes, the navigation and flash of AC5 still happen; the flash lands in the page region.
- [ ] **AC8 (row description).** The Delete row's description reads: "Deletes the agent with all of its chats, routines, rules, notes and settings. This can't be undone." The Purge row is unchanged.
- [ ] **AC9 (tests moved).** Every browser test that deleted an agent through the old arm-and-commit is moved to the dialog: tick, then Delete.
  - lane `agents`: `test_flow_agent_crud.py`, `test_flow_agents_list.py`, `test_flow_agent_general_tab.py`, `test_flow_studio_purge_now_button.py` (only where it touches `delete-agent-btn`);
  - lane `routing`: `test_store.py`, `test_nav_guard.py`.

  The old lapse test (the arm timing out) for the agent delete is rewritten in place as a dialog-cancel test (rename, not delete-and-re-add). Re-grep `delete-agent-btn` across `tests/`, `scripts/` and `tests/behavior/` before landing; the list above is from `8decdebf`.
- [ ] **AC10 (new tests).** A new or extended flow test file in lane `agents` covers AC1 to AC8. If it is a new file, confirm its lane with `scripts/run-tests.sh --lane agents --list`; a new file outside every glob lands in `shared`. Give it the `agents` glob only if that is how the lane is defined, and run `tests/test_run_tests_lanes.py` either way.
- [ ] **AC11 (UI rules).**
  - The area writes no class owned by a `js/ui` control and uses no HTML-string sink (`tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`).
  - `tests/test_ui_control_inventory.py` passes. If it requires a row for the new composition, add one modelled on the "Agent picker (a composition, not a factory)" row.
  - The static guards pass: `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`.
- [ ] **AC12 (documents).**
  - `docs/ui-testid-registry.md`: `delete-agent-btn` now opens the dialog; rows for the four new ids.
  - The GleepGlorp guide `the_one/gleepglorp/guide/agents.md` "Purge and delete": Delete asks in a dialog, says how many chats it will delete, needs the box ticked, and deletes the chats with the agent; Purge still asks in place. `tests/test_gleepglorp_guide.py` passes.
  - `the_one/agents.md` (the General tab danger zone, around `:2572`): the dialog.
  - `tests/behavior/studio-agent-crud.md`: its delete steps describe the dialog. It is not run.
- [ ] **AC13 (gates).** Green, one at a time, nothing else on the host:
  - the lanes `agents` and `routing` (`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>`);
  - the unit-tier UI guards above and `tests/test_gleepglorp_guide.py`;
  - the lint pair on `the_one/ tests/ scripts/ evals/`.

## Verification Steps
- AC1 to AC8: browser flow tests (`tests/browser/_nav.py` for navigation, never raw hashes; the credential helpers the browser fixtures already provide).
- **Falsification** (report yes or no for each):
  1. drop the checkbox's `onChange` enabling → the AC3 test fails;
  2. call `proceed()` in `beforeArm` → the AC1 "not armed" assertion fails;
  3. flash the pre-read count instead of `chats_deleted` → an AC5 test whose count changes between open and delete fails. To make one, add a chat through the API after the dialog opens.
- AC9 and AC13: the two lanes, alone on the host.

## Implementation Guidance
1. **Re-grep** `delete-agent-btn` in `tests/`, `scripts/`, `docs/`, `tests/behavior/` and `the_one/`, and note anything new in the flight log.
2. **The dialog module**: build the body (message `p`, checkbox) and the footer (`App.ui.button`s in a container passed as `footerEnd`). Open `App.ui.modal({title, body, footerEnd, initialFocus: cancelBtn, testid: 'delete-agent-dialog', onClose})`. The checkbox's `onChange` sets `deleteBtn.disabled`. On Delete:
   - disable Delete and the checkbox;
   - `fetch('/api/agents/' + encodeURIComponent(name), {method: 'DELETE'})`;
   - on `ok`: `modal.close()`, then call the controller's `onDeleted(body)`;
   - on error: show the flash and re-enable both.

   The controller does the store invalidation, `loadAll`, navigation, focus and flash, so the Escape-mid-request path (AC7) reaches them too. When Escape closed the dialog early, the success path's `close()` is a no-op (`modal.js:349-351`).
3. **`general-tab.js`**: the Delete action becomes `beforeArm: function () { if (callbacks.onDelete) callbacks.onDelete(button); }` (pass the opener; do not call `proceed`). Check whether `dangerZone` requires `onConfirm`, and keep a harmless one if it does. Update the description (AC8).
4. **`agent-editor-controller.js`**: `handleDeleteEditor` opens the dialog. The existing success body (DD8 focus index read before the request, `invalidate`, `loadAll`, `discardOpen_`, `replaceWithAgentsRoot_`, `focusAgentRowNear`) moves into the dialog's `onDeleted`, with `App.store.invalidate('sessions')` and the flash added. The `revertFn` path goes away: nothing is armed.
5. Load the new script in `index.html` next to the other studio area scripts.
6. Tests (AC9, AC10), documents (AC12), gates (AC13).

## Citation Audit
Checked at `8decdebf`:
- `general-tab.js:226-257`: the danger zone actions, as quoted in Inputs.
- `agent-editor-controller.js:339-373`: `handleDeleteEditor`.
- `ui/button.js`: variants `primary | secondary | ghost | danger`.
- `ui/choice.js`: `App.ui.checkbox(opts)` returns `{el, control, setChecked, ...}`.
- `dialog.js:91`: the danger-variant precedent.
- `delete-agent-btn` consumers: `tests/browser/test_store.py`, `test_flow_studio_purge_now_button.py`, `test_flow_agent_crud.py`, `test_flow_agents_list.py`, `test_flow_agent_general_tab.py`, `test_nav_guard.py`; `tests/behavior/studio-agent-crud.md`; `docs/ui-testid-registry.md`; `general-tab.js`.

All present.
