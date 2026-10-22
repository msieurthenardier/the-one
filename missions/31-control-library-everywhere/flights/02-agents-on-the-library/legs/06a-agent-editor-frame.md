# Leg: agent-editor-frame

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Rebuild the agent editor's **frame** on the library. The frame is the header on `App.ui.editorShell` (Chat through `extra`), the tab strip and panels on `App.ui.tabs`, and the editor mount on a `mountSlot`. The leg also defines the editor's identity and remount policy, with an explicit `patch(agent)` for same-identity updates.

General and the other five tabs keep their current builders, mounted inside their panels. Leg 06b rebuilds General, and legs 07-10 rebuild the other tabs. `agent-editor.js` ends with zero sinks and zero allowance rows.

## Context
- **Flight decisions:** DD2 (`mountSlot`), DD3 (`tabs`), DD6 (mount once and patch, reached incrementally, see below), DD7, DD10.
- **The design review** (2026-10-21, two cycles) split the old leg 06 into this leg and 06b, and set the policy below.
- **Legs 01-05 have landed:**
  - the studio split (`agent-editor-controller.js` owns `renderEditor`, `setActiveTab`, cancel/delete/purge/test and `save`; `agent-form-data.js` owns `collectFormData`, `getFormSnapshot` and `checkDirty`; `agent-model-picker.js` owns `wireEditorEvents`, the picker and the VRAM check; `agents-list.js` owns `doSelect`);
  - leg 04's controls;
  - leg 05's `mountSlot`, confirm announcement and toggletip.

  Read the actual signatures, especially `App.ui.tabs`'s id options. It must produce tab ids `agent-tab-{id}` and panel ids `agent-tab-panel-{id}`; if the factory cannot, add an option in this leg with a contract case.
- **Today** (re-locate by symbol): `agent-editor.js` builds the header and tablist as one HTML string. The breadcrumb and the `App.ui.button` Chat button are added afterwards, and `App.tabs` drives the tabs. Testids: `tab-*`, `save-agent-btn`, `cancel-agent-btn`, `editor-breadcrumb-link`, `agent-chat-btn`. `renderEditor` rebuilds every tab on every call. `checkDirty` sweeps `.save-btn`, `.cancel-btn` and `.editor-unsaved` directly. The `_selectedAgentLoaded` load-error node is inserted as a DOM sibling. The save-blocked rule is squawk 0090.

## Acceptance Criteria
- [ ] **The header** is built with `App.ui.editorShell`:
  - the breadcrumb `{label: 'Agents', href}` with today's text;
  - the title (the agent name, or "New agent") and the subtitle (the description);
  - Cancel and Save/Create with today's testids, and `enabledWhenClean` in create mode only;
  - `extra: [the Chat button]` (`agent-chat-btn`, saved agents only);
  - the inline error.

  **There is no shell Test button.** The agent's Test stays in the General panel next to the provider fields (06b).
- [ ] **The tabs** use `App.ui.tabs`, with today's labels and order, `data-tab-id` values, `tab-*` testids and ids `agent-tab-{id}`/`agent-tab-panel-{id}`. The `App.tabs` → `App.ui.tabs` change (`activate` → `select`) is made in `setActiveTab` and `state.tabHandle`. Deep links (`#agents/{name}/{tab}`) still select the tab.
- [ ] **Identity and the mount slot.** The identity key is (the saved agent's name, create-or-edit). The editor mounts through a `mountSlot` whose data carries the shell and tabs handles. Every async callback in the controller and the picker (model fetch, VRAM, test, save) checks `isCurrent`.
  - **New identity** (a different selection, create → edit, a **rename**, a delete): the slot remounts the editor and restores the active tab. The other tabs capture the agent name, so a rename must rebuild them.
  - **Same identity** (a Save without a rename, or a same-agent `doSelect` with a fresh object such as the self-config refresh or `activate`): the controller calls `patch(agent)`. In this leg `patch` does exactly this, in order:
    1. sets the shell title, subtitle and Chat visibility;
    2. updates the load-error node and the save-blocked state;
    3. rebuilds the content of **all six panels**, General included, by calling each tab's current entry function into its cleared panel (the interim: 06b switches General to patch-only, and legs 07-10 switch theirs);
    4. re-runs the per-panel listener wiring and the picker's `wireEditorEvents` for the rebuilt General;
    5. resets the snapshot: `state.snapshot = getFormSnapshot(); checkDirty();`.
  - **Cancel:** reverts by rebuilding all six panels from the stored agent (the same interim), then the snapshot reset. It does not remount the frame.
  - The active tab survives `patch`, Cancel and a rename.
- [ ] **Dirty tracking:**
  - `collectFormData` and `getFormSnapshot` stay DOM-based. Do not rewrite them; the library field controls keep their classes and `data-field`.
  - `checkDirty` replaces its `.save-btn`/`.cancel-btn`/`.editor-unsaved` sweep with `shell.setDirty(dirty)`, then **re-applies the save block** (squawk 0090) after every `setDirty` through a dedicated Save disable. It does **not** use `setBusy`, which would also disable Cancel. Cancel stays enabled under the block, as 0090 requires.
  - Change listeners are attached per panel, when the panel is built or rebuilt.
- [ ] **The load-error node** (`_selectedAgentLoaded` false) is a node in the frame (above the tabs, today's text and testid), shown or hidden by `patch` and by mount. It is no longer a sibling inserted by `renderEditor`.
- [ ] **Focus:**
  - `editorTitleEl_`/`saveBtnEl_` resolve from the current slot data's shell handles, so a rename remount or a Cancel re-resolves them;
  - `App.focusAfter.defer` for create → edit survives the slot swap;
  - after `patch`, focus returns where the action's focus-after rule puts it (Save → the title, as today);
  - the scroll position of a rebuilt panel may reset in this interim, which is acceptable and recorded.
- [ ] **Zero:** `agent-editor.js` has no sinks and no allowance rows (lowered from the printed dicts; any rise needs a reason). The `.studio-editor.is-hidden` host class is **untouched**: it is the shell host's class, outside this leg.
- [ ] **Tests:**
  - **Added:**
    - rename an agent, switch to Rules and notes, add a rule, and assert it is stored under the new name;
    - Save, then open Knowledge, and assert the current `kb_tool_names` rows show;
    - Cancel reverts General and another tab;
    - the active tab survives Save and a rename;
    - a `patch` test showing a same-identity Save leaves the frame (the shell header node) unremounted, is dirty → clean after save, and keeps the save-blocked state.
  - **Updated:** tab selectors (`.tablist`/`[role=tab]`, `test_flow_agents_scale.py:241`) only where the DOM changes. The shell keeps today's Save/Cancel/unsaved classes and testids.
  - **Unchanged and passing:** `test_flow_dirty_confirm.py`, `test_flow_cross_area_dirty_gate.py`, `test_agents_chat_action.py`, `test_flow_agents_focus_after.py`.
- [ ] **Captures:** `agent-general` (the frame is visible) to `…/m31-f2-after-06a/`, expecting no difference apart from the tab strip's library rendering (which must match). Anything else is fixed.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the `agents`, `routing` and `shared` lanes under netns; the contracts lane if a factory changed.
- [ ] **Docs:** `the_one/agents.md` gets the agent editor frame, the identity and `patch` policy, and the interim rebuild list (which tab leaves it in which leg).

## Verification Steps
- `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML" the_one/interfaces/web/static/js/areas/studio/agent-editor.js` returns nothing.
- The ownership and sink tests pass with `agent-editor.js` rowless.
- The lanes above.

## Implementation Guidance
1. Read the controller (`renderEditor`, `setActiveTab`, `cancelEdit`, `save`), `agents-list.js` `doSelect` (the same-agent path), `agent-form-data.js` `checkDirty`, and `agent-editor.js`.
2. Build the frame with the slot, then implement `patch` and Cancel as specified, then the dirty and save-block changes.
3. Tests, captures, allowances, docs.

## Edge Cases
- **Create mode:** no Chat button, Create instead of Save, Cancel enabled when clean, no danger zone (General's concern).
- **Deleting the current agent:** the slot is destroyed and the list moves on, as today.
- **A same-agent `doSelect` while dirty** (the self-config refresh) still reaches `patch` in this leg. Leg 10 fixes DD9-3, so dirty state is not preserved yet. Record this; leg 10's test proves the fix.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/{agent-editor,agent-editor-controller,agent-form-data,agents-list,agent-model-picker}.js`, possibly `js/ui/tabs.js` (an id option).
- New and updated agent-lane browser tests; `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`.
- `the_one/agents.md`.

## Citation Audit
From the leg 06 design review (2026-10-21; two cycles, on the post-split tree).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
