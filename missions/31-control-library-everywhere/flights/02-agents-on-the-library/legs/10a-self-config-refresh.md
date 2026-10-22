# Leg: self-config-refresh

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Fix DD9-3, test first: a self-configuration change must no longer discard unsaved agent-editor edits. The Self-configuration tab leaves leg 06a's interim rebuild list. It returns a handle, takes `setAgent(agent)`, and refetches its own data after its actions, instead of being torn down and rebuilt by the editor. There is no library conversion and no file split in this leg; those are legs 10b and 10c.

## Context
- **Flight decisions:** DD6 (mount once, patch), DD9-3, DD10.
- **The design review** split the old leg 10 into this leg (behaviour), 10b (a mechanical split) and 10c (the library conversion). That was cycle 1, 2026-10-21. Cycle 2 reworked this leg against the 06b and 07b handle contracts. The security-sensitive behaviour change is reviewed apart from the rewrite.
- **Legs 06a-09 have landed.** Read their flight-log entries, especially:
  - 06a: identity, `patch`, `rebuildPanels`, and the slot key `currentData_().key`;
  - 06b: General's `setAgent` is a **full revert**. It resets every field and the model select, then re-wires the picker, which refetches the model list;
  - 07b: the MCPs handle `{setAgent, setSources, destroy}`. `setAgent` is also a revert. `setSources` reconciles tiles by id (see 07b's addenda from this leg's review).
- **Today** (re-locate by symbol):
  - `agent-data.js` `_refreshAgentAfterSelfConfigurationChange(name)` invalidates the `agents` store, refetches the MCP sources cache and the agent, replaces the row in `self._agents`, then calls `ctx.onSelfConfigChanged(updated)`. These go through it: enable, disable, approval mode, approve, override, dismiss and restore. Credential mint, rotate and revoke do not (`self-configuration-tab.js` about `:410`).
  - `studio.js` (about `:242`) wires `onSelfConfigChanged` to `agentsListMod.doSelect(updated)`, which reaches `patch`. That rebuilds the panels on the interim list and resets the snapshot, so typed edits and `state.dirty` are lost.
  - `renderSelfConfigurationTab` returns nothing. `agent-editor.js` `rebuildPanels` keeps only `h.general`.
  - The tab keeps a module-level `pendingAction` bridge (about `:89-105`, `:568-574`). Each action stores a message, and the rebuild focuses `self-configuration-action-status` with it. Most success paths do nothing locally and rely on the rebuild.
  - `fetchPendingCount` is passed but never used. It appears at `agent-editor.js:112`, `agent-editor-controller.js:217`, `agent-data.js:173,504` and in the tab's header comment (`:34`).
  - `state.snapshot` is `JSON.stringify(collectFormData())` (`agent-form-data.js:25`). It includes `mcp_source_ids` in tile DOM order, and `mcp_overrides`.
  - `manage.disable` cascade-revokes every external credential and supersedes the pending revisions. Today's rebuild hid any token reveal as a side effect.
- **What each write changes:**

  | Action | Agent record | Sources | Tab data |
  |---|---|---|---|
  | enable / disable | `mcp_source_ids` (the loopback id added or removed) | a source row created or deleted | status, revisions (disable supersedes them), external credentials (disable revokes them) |
  | approval mode | `self_revision_requires_approval` | — | status |
  | approve, override, restore | `description` or `system_prompt` | — | revisions |
  | dismiss | — | — | revisions |

  The enabled flag is not on the agent record. It comes from `fetchStatus`.

## Acceptance Criteria
- [ ] **The DD9-3 tests.** Tests 1 and 3 are written first and fail on the pre-fix tree (record both runs). Tests 2, 4 and 5 are regression guards that pass both before and after.
  1. Open a saved agent with self-configuration enabled. Type into the General system prompt (dirty), switch to Self-configuration and toggle approval mode. Assert:
     - the typed text is still in the field;
     - `.editor-unsaved` shows and Save is enabled;
     - the approval mode changed (the status line and `GET .../self-configuration`).
  2. Enable self-configuration on a clean agent, edit the description, then Save. The stored `mcp_source_ids` still contains the loopback source.
  3. **Conflict** (the operator's choice, 2026-10-21: keep the typing, with a note). Set approval mode on, with a pending description revision. Type a different description (dirty), then approve the revision. Assert:
     - the description field still holds the typed text;
     - a status line in General (`agent-stored-value-changed`) reads "The stored description changed. Save will replace it with your text." (for the system prompt: "The stored system prompt changed. …");
     - the form is still dirty;
     - the untouched system prompt field took the stored value, if it changed;
     - Save stores the typed text;
     - the note clears on Save, on Cancel, and on a new identity.
  4. **Clean field.** With the description untouched, approve a description revision. Assert:
     - the field shows the approved value, with no note;
     - the header subtitle shows it;
     - the form is clean.
  5. Disable self-configuration, then Save. The deleted loopback id is not in the stored `mcp_source_ids`.
- [ ] **The fix: `onSelfConfigChanged(updated)` moves to the controller.** `agent-editor-controller.js` exports it, and `studio.js` wires `agentData`'s callback to it instead of `doSelect`.
  - **Guard.** It acts on the editor only when all of these hold:
    - `self._activeSection === 'agents'`;
    - the slot is mounted with key `'edit:' + updated.name` (`currentData_()`);
    - no Save is in flight (`state.saving`, or the save-block flag the controller already uses).

    Otherwise it replaces `self._selectedAgent` when the name matches, and re-renders the list row only.
  - **Never:** it does not touch `selectSeq`, `state.dirty` or `_selectedAgentLoaded`. It does not call `doSelect`, `patch`, `General.setAgent` or `MCPs.setAgent`, and it does not remount.
  - **Always:** it sets `self._selectedAgent = updated` and re-renders the list row.
  - **Per tab, through handles:**
    - **General** gets two new handle methods, added in this leg:
      - `general.applyStored({description, system_prompt})` writes the new stored value into **clean** fields only. A field is clean when its DOM value equals its value in the snapshot baseline. It returns the names of the fields left dirty.
      - `general.setStoredChangeNote(fields | null)` shows or hides the note (`App.ui.status`, testid `agent-stored-value-changed`).
      - General's `setAgent` clears the note. That covers Save and Cancel, and a remount covers a new identity. The controller re-checks the note on every input, through the dirty callback, and hides it once the field is clean again.
    - **The header:** `shell.setSubtitle(updated.description)` runs when the description changed.
    - **MCPs:** `mcps.setSources(self._allMcpSources, updated.name)` (07b). The surface tile appears or disappears, and the other tiles keep their unsaved state.
    - **Self-configuration:** `selfConfig.setAgent(updated)`.
- [ ] **The snapshot rebase.** If the form was clean before the change, set `state.snapshot = getFormSnapshot()` after the tab updates. If it was dirty, parse the baseline JSON and change it key by key:
  - `description` and `system_prompt`: set each to its new stored value;
  - `mcp_source_ids`: add or remove the surface id at its DOM position;
  - `mcp_overrides`: on disable, drop the surface's entry.

  Then stringify it back and call `checkDirty()`. Key order survives the round trip.
- [ ] **The Self-configuration tab handle.**
  - **`{setAgent, destroy}`** is returned from `renderSelfConfigurationTab`. The frame keeps it in `h.selfConfig`. `patch` calls `setAgent`; `rebuildPanels` and Cancel skip the tab; the slot's destroy calls `destroy`.
  - **`setAgent(agent)`** stores the record for later call-time reads, and updates the approval-mode state from `self_revision_requires_approval`. It does not rebuild, and it does not read an enabled flag (the record has none).
  - **`destroy()`** bumps the tab's generation counter and hides the token reveal.
  - **`pendingAction` becomes mount-local**, since nothing crosses a render any more. This also lets leg 10b move it without a module-level variable.
- [ ] **Local refetches after success**, each behind the tab's generation counter, so a late response for an older request or mount is dropped:
  - **enable/disable:** status, revisions, and `renderExternalState(enabled)`. On disable this hides the token reveal, because the credentials were revoked.
  - **approval mode:** the local status only.
  - **approve, override, dismiss, restore:** revisions (the queue and the history).
- [ ] **Focus.** On success, the action's message is written to `self-configuration-action-status` and focus moves there **before** the refetch, so removing the focused card cannot drop focus to `body`. A refetch never moves focus. A stale or failed action does not move focus (as today).
- [ ] **The token reveal's lifetime.** A same-identity Save no longer clears it. This is intended, and recorded in agents.md. Disable, a new identity and `destroy` clear it. Leg 10c adds tab deactivation.
- [ ] **Clean-up:**
  - the success-path comments that say "studio.js re-renders the tab" are corrected;
  - `fetchPendingCount` is removed at every site listed above.
- [ ] **Security behaviour is unchanged:**
  - approve stays fail-closed against staleness;
  - `?override=true` is sent only from the explicit override button;
  - restore targets only `applied` revisions;
  - credential mint, rotate and revoke still skip `onSelfConfigChanged`.
- [ ] **A patch test.** Open the history `<details>`, then make a same-identity General Save. Assert it is the same `<details>` node and still open, and that no `GET /api/agents/{name}/self-configuration*` request was made during the Save.
- [ ] **Tests:** these pass:
  - the four self-configuration files: `test_studio_self_configuration_tab.py`, `_queue`, `_history` and `_external`. Their enable and disable MCPs-tab tests now go through `setSources`;
  - the five DD9-3 tests;
  - `test_flow_dirty_confirm.py`, `test_flow_agent_editor_frame.py` and `test_studio_mcps_tab.py`.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks (no new rows); the `agents` and `routing` lanes under netns.
- [ ] **Docs:** `the_one/agents.md` gets the DD9-3 behaviour: the controller's `onSelfConfigChanged` with its guard, the clean/dirty field rule and the note, the snapshot rebase, the tab handle, the reveal lifetime, and the updated interim rebuild list.

## Verification Steps
- The DD9-3 tests: 1 and 3 fail on the pre-fix tree, and all five pass after (both runs logged).
- `grep -n "doSelect" the_one/interfaces/web/static/js/areas/studio.js` no longer shows the `onSelfConfigChanged` wiring.
- `grep -rn "fetchPendingCount" the_one/interfaces/web/static/js` returns nothing.
- The lanes above.

## Implementation Guidance
1. Write the five DD9-3 tests and run them on the current tree.
2. Return the tab's handle and wire `h.selfConfig`. Make `pendingAction` mount-local, and add the local refetches with focus first. Take the tab off the interim list.
3. Add General's `applyStored` and `setStoredChangeNote`. Move `onSelfConfigChanged` into the controller, with the guard, the per-tab calls and the snapshot rebase.
4. Run the four self-configuration files after each step.

## Edge Cases
- **Another agent selected, another section, or the editor destroyed when the refresh lands:** the slot-key guard fails, so only the list row updates.
- **A Save in flight when the refresh lands:** the editor is not touched. The Save's own response reaches `patch`, which runs General's and MCPs' `setAgent` from the saved record.
- **Create mode:** the tab shows its save-first notice, so no self-configuration action is possible.
- **Disable while the MCPs tab is dirty:** `setSources` removes only the surface tile. The other unsaved MCP choices stay.
- **A rename between the action and its response:** the slot key no longer matches, so only the list updates.
- **Restore with `side=base`** changes the same two fields, so the same rules apply.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/{agent-editor-controller,agent-editor,agent-data,self-configuration-tab,general-tab,agent-form-data}.js`, and `areas/studio.js` (the wiring).
- New browser tests, for example `tests/browser/test_studio_self_configuration_dirty.py` (the `agents` lane, through the existing `test_studio_*` glob).
- `the_one/agents.md`.

## Citation Audit
Checked at writing and at the cycle-2 review (2026-10-21, on the post-06a tree with 06b in progress):
- `agent-data.js` `_refreshAgentAfterSelfConfigurationChange` (`:101-120`), with `fetchPendingCount` at `:173,504`;
- `studio.js:242`;
- `agent-editor.js:112` and `rebuildPanels`;
- `agent-editor-controller.js:217`;
- `agent-form-data.js:25`;
- `self-configuration-tab.js`: `pendingAction` (`:105`, `:568-574`), the credential-path skip (about `:410`);
- `general-tab.js:254-273` (06b's `setAgent`, still in progress);
- `api.py` `update_agent` (no `mcp_source_ids` preserve).

Re-verify by symbol at leg start, since legs 06b-09 land in between.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
