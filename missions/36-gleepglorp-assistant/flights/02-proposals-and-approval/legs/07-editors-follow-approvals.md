# Leg: editors-follow-approvals

**Status**: completed
**Flight**: [Proposals and approval](../flight.md)

## Objective
When a proposal is approved, the app follows the change in the agents list,
the chat drawer and the agent editor's General tab.

The editor:
- takes new values into controls the operator has not edited;
- keeps any unsaved edit, with today's caption;
- marks each control that changed with board option A's quiet note. The note
  also shows when the operator comes back to Agents after approving.

Leg 8 extends this to the Tools, MCP and Knowledge tabs, and to the Rules and
Routines reloads.

## Context
- Flight DD10 (as amended), the Mockups (editor option A and the unsaved-edit
  sibling screen), and the mission criterion: "An editor that is open on the
  changed item shows the new values without a reload, and an unsaved edit
  there is never overwritten silently".
- **The design review split this leg in two** (the flight's acceptable
  variation). This leg is the core plus the General tab. Leg 8,
  `tabs-follow-approvals`, does the other tabs on the same mechanism.
- **The signal comes from two places** (Legs 4 and 6):
  - the server broadcasts `config_changed {kind: agent | rule | routine,
    agent, fields, session_id, proposal_id, at}` to every socket after an
    apply;
  - the window that clicked Approve has the applied `proposal` view in the
    response.

  Legs 4 and 6 are being built in parallel batches, so the detail shape above
  is fixed here as the contract both dispatch sites produce.
- **Same-window reality.** The leave guard (`App.nav` `studio` source) asks
  before leaving a dirty agent editor. So in one window, the path is: approve
  in Chats, then go back to Agents.
  - Studio `activate` → `_refresh` → `loadAll(true)` → `doSelect`
    (`studio.js:570-580`, `agents-list.js:329-420`) fetches the agent and
    re-patches the editor in full (`patchEditor_`, which calls `setAgent`), so
    the values are already new.
  - This leg adds the notes, drawn from a record that every mount reads.
  - Live follow-through with unsaved edits applies to a second window, and to
    Flight 3's overlay, which will put a chat beside every page.
- **The socket gap.** A window opened straight into Agents has no chat socket
  until Chats is visited (`app.js:155-166`, `chat.js:613-627`), so that window
  does not follow live. It picks the change up on the next Agents activation
  or a reload. Accepted for Flight 2 (the operator dropped multi-window
  steps, and Flight 3's overlay connects on every page). It is recorded in the
  flight log and in `the_one/agents.md`.
- **Lazy init.** Studio initialises on its first activation. A listener that
  lives in studio does not exist when the operator approves before ever
  opening Agents. So the record and its de-duplication live in a small eager
  module.
- **Today's precedent** is `agent-editor-selfconfig.js`:
  - `onSelfConfigChanged` checks the `live` guard (no section term: a hidden
    editor is patched too) and `wasClean`.
  - `recheckStoredNote_` compares `JSON.parse(getFormSnapshot())[k]` with
    `JSON.parse(state.snapshot)[k]`.
  - `general-tab.js::applyStored` and the panel note
    (`agent-stored-value-changed`: "The stored {label} changed. Save will
    replace it with your text.").
- **Size:** `agent-editor-controller.js` is at 798 of 800 lines, so it is split
  first. Never condense lines.

## Inputs
- `static/js/areas/studio/`:
  - `agent-editor-controller.js` (`onSaveError_`/`showToolOverrideErrors_`
    ~100-188, `saveInFlight` closure ~197, `wire_`/`renderEditor`/
    `patchEditor_` ~224-283, `buildCallbacks_` ~285-374, save, `cancelEdit`);
  - `agent-editor-selfconfig.js`;
  - `general-tab.js` (`applyStored` 302-316, the note 219-222 and 320-345, the
    Behavior fields 193-207, `setAgent`);
  - `agent-model-picker.js` (`wireEditorEvents`, `fetchModelsForProvider`,
    `pendingValue`);
  - `agent-form-data.js` (`collectFormData` keys, `getFormSnapshot`,
    `checkDirty`);
  - `agent-data.js` (`_refreshAgentAfterSelfConfigurationChange` 147-168);
  - `studio-event-bus.js` (`App.studio.eventBus`, a wrapper over `document`
    CustomEvent with no `off`);
  - `studio-subscriptions.js`, `agents-list.js`.
- `static/js/areas/chat/socket.js` (the pre-gate handlers, ~115-131) and
  `agent-drawer.js` (`refreshNotes`, `refreshRoutines`; rules load on open).
- `static/index.html` (script order: `socket.js` ~105, `studio-event-bus.js`
  ~107, the controller ~157).
- `static/js/store.js`, `router.js::href`, `time.js::formatClock`.

## Outputs
- **`static/js/approvals.js` (new, eager):** `App.approvals`, with
  `record(detail)`, `forAgent(name)`, `clear(name)`, a capped
  de-duplication set, and `CONFIG_CHANGED`.
- **The controller split** into `agent-editor-save-errors.js` and
  `agent-editor-callbacks.js`, with no behaviour change.
- **`agent-editor-follow.js` (new):** the listener, the store and drawer
  refresh, the central apply for the General fields, and the notes drawing.
  Its wiring lives in this module, never in added controller lines.
- **The dispatch** from the socket's pre-gate `config_changed` handler, and
  one call in Leg 6's `proposal-cards.js`: `App.approvals.record(detail)` on
  an `applied` approve response. Leg 6 is built first, so this leg adds that
  line.
- **Drawer:** `refreshRules`.
- **Tests and docs.**

## Acceptance Criteria
1. **Split first, with no behaviour change.**
   - Move `onSaveError_` and `showToolOverrideErrors_` to
     `agent-editor-save-errors.js`, and `buildCallbacks_` to
     `agent-editor-callbacks.js`. Each is a `create(ctx)` with getters,
     including one for the `saveInFlight` closure. Their `<script>` tags go
     before the controller.
   - The controller ends at about 620 lines; the flight log records the
     before and after counts.
   - The `agents` and `agent-tabs` lanes are green after the split alone,
     before any other change.
2. **The eager record.** `static/js/approvals.js` loads before `socket.js`.
   - **`App.approvals.record(detail)`:**
     - Returns `false` for a `proposal_id` already seen. The set is capped at
       200, dropping the oldest.
     - Otherwise it merges the change into `byAgent[detail.agent].fields[f] =
       {at, session_id}` for each field. A rule or routine kind is recorded
       under the key `'rules'` or `'routines'`.
     - Then it calls `App.store.invalidate('agents')` and emits
       `App.studio.eventBus.emit(App.approvals.CONFIG_CHANGED, detail)` when
       the bus exists (it is only called at runtime).
   - **`forAgent(name)`** returns the record. **`clear(name)`** empties it.
   - **Detail contract:** `{kind, agent, fields: [stored field names],
     session_id, proposal_id, at}`.
   - **Callers:**
     - the socket's pre-gate handler for `config_changed` (this leg), which
       runs whether or not a chat is joined;
     - Leg 6's card, on an `applied` approve response. This leg adds that
       call to `proposal-cards.js`.
3. **Lists and drawer** (the follow module, registered once at studio init,
   because the bus has no `off`; it looks up the live editor handle at event
   time):
   - When Agents is active, a forced `App.store.get('agents', {force: true})`
     refreshes the list and subtitles.
   - The chat drawer, when open on that agent, runs `refreshRules` (new, like
     `refreshRoutines`), `refreshRoutines`, or the agent facts for `kind:
     agent`. Its handler lives in the chat area and listens to the same bus
     event.
4. **The live apply** for the General fields. When the editor is open on that
   agent, the existing guard holds (`handle && key === 'edit:'+name &&
   !saveInFlight()`) and `kind == "agent"`:
   1. Fetch the agent fresh. Use a new sibling of
      `_refreshAgentAfterSelfConfigurationChange` that returns the agent; the
      self-configuration path is untouched.
   2. **Decide clean or dirty centrally**, per field group touched by the
      event: `cur = JSON.parse(getFormSnapshot())`, `base =
      JSON.parse(state.snapshot)`, and a group is dirty when
      `JSON.stringify(cur[k]) !== JSON.stringify(base[k])` for any of its
      keys. The groups:
      - `description`;
      - `system_prompt`;
      - `{provider_config_id, model}` (one group: dirty if either key is
        dirty);
      - `max_iterations`;
      - `chat_history_retention_days`;
      - `rich_visuals`.
   3. **Clean group:** write the new value through the General tab's plain
      setters, then rebase from the DOM: `base[k] =
      JSON.parse(getFormSnapshot())[k]` for each key of the group.
      - For a provider change, the model list refetches with `pendingValue`
        set to the new model, and the rebase runs after the refetch resolves.
      - The `rich_visuals` toggle uses its silent `setChecked`.
   4. **Dirty group:** write the new value, read the keys from the DOM into
      `base`, then write the operator's value back. Add the group's label to
      the panel note, using the existing template and `recheckStoredNote_`.
   5. Run `checkDirty()`.

   - **No feedback:** no focus move and no announcement. The notes are static
     captions.
   - **Hidden editor:** live apply may run while the operator is on Chats,
     since the guard has no section term. The next `activate` re-patches, and
     the notes come back from the record.
   - **During a Save:** an approval that arrives while a Save is in flight is
     not deferred. The record and the next mount cover it, as the
     self-configuration path does.
   - **Other kinds and fields:** a `kind` of rule or routine, and the agent
     fields of Leg 8 (tools, MCP, knowledge), are Leg 8's. This leg updates
     only the list and drawer for them.
5. **The notes (board option A).** Each control that holds an approved value
   shows a caption under it: "Changed by a change you approved in a GleepGlorp
   chat · {h:mm AM/PM} · Open chat".
   - **Markup:** `App.time.formatClock`; the "Open chat" link is
     `App.router.href({destination: 'chats', id: session_id})` (the
     `routine-recent-run-chat` precedent); the caption is styled with
     `--fg-tertiary` in `css/studio.css`, area-owned; testid
     `agent-approved-change-note` with `data-field`.
   - **When drawn:** from `App.approvals.forAgent(name)`, at every editor mount
     and patch (after `wire_` and `patchEditor_`, through the follow module's
     hook on the mount), and after every live apply. So the full re-patch on
     `activate` never wipes them.
   - **Mount points:** each General field's note sits directly under that
     field's control. Leg 8 defines the mount points for tiles and tabs.
   - **Cleared:** `App.approvals.clear(name)` on a successful Save or on
     Cancel of that agent (hooked on the existing save success and
     `cancelEdit` paths). A page reload drops the record anyway.
6. **The return path.** In one window: approve in Chats, then open Agents on
   that agent for the first time in this window (studio not yet initialised).
   The new values show, each changed General control has its note, and there
   is no unsaved-edit caption.
7. **Tests:** `tests/browser/test_flow_agent_editor_follows_approval.py`, added
   to `agent_tabs_pat` in `scripts/run-tests.sh`. Each test visits Chats first
   so the socket is alive, opens the agent in Agents, and then either:
   - approves a seeded proposal through the Leg 4 route (httpx with
     credentials), so the server's broadcast arrives live; or
   - calls `App.approvals.record(detail)` directly, for the second-window
     cases. These depend only on the detail contract, so this leg can be
     tested before Leg 6.

   Covered cases:
   - clean description, model, max iterations and `rich_visuals` take new
     values with notes;
   - a dirty prompt keeps the operator's text with the panel note, while a
     clean description beside it updates;
   - `editor-unsaved` stays correct;
   - the return path, with studio not yet initialised, shows the notes;
   - the notes clear on Save and on Cancel;
   - an event for another agent changes nothing;
   - a duplicate event (response plus frame) acts once.

   **Falsify:** drop the dirty check, and the prompt text is lost; drop the
   de-duplication.

   **Also run:** the static guards, `tests/test_area_module_size.py`,
   `tests/test_ui_guards.py` (testids registered) and
   `tests/test_run_tests_lanes.py`.

   **Lanes,** one at a time: `agents`, `agent-tabs`, `agent-routines`,
   `chats`.
8. **Docs:** `the_one/agents.md` gains "Editors follow approved changes (M36
   F2 L7)", covering the record, the event, the central clean/dirty rule, the
   notes and the socket gap. Register the testid.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_area_module_size.py tests/test_run_tests_lanes.py tests/test_store_static.py -x --timeout 60`
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents`,
  then `--lane agent-tabs`, `--lane agent-routines` and `--lane chats`, one at a
  time.
- `THE_ONE_TEST_NETNS=1 make test-unit`.

## Implementation Guidance
1. **Split the controller,** run `agents` and `agent-tabs`, and record the
   line counts.
2. **`approvals.js`:** its script tag, and the socket pre-gate handler.
3. **The follow module:** the listener, the list and drawer refresh, the
   central apply, the notes drawn at mount (hooked through the module, never
   by adding controller lines), and clearing.
4. **The drawer's `refreshRules`.**
5. **Testids, tests, lanes, docs.**

## Edge Cases
- **The agent was renamed** between the proposal and the event. The event
  carries the current name.
- **An unrelated agent is open:** only the list refreshes.
- **An agent create:** the list gains the row, and no editor is open on it.
- **The model list fetch fails:** the model keeps `pendingValue` as today, and
  the rebase reads whatever the DOM holds.
- **The provider is dirty but the model clean, or the reverse:** the pair is
  one group, so it is dirty and the operator's pair is kept.

## Files Affected
- `static/js/approvals.js` (new); `static/index.html` (script tags).
- `static/js/areas/studio/`:
  - `agent-editor-controller.js` (the split);
  - new `agent-editor-save-errors.js`, `agent-editor-callbacks.js` and
    `agent-editor-follow.js`;
  - `general-tab.js` (plain setters where missing);
  - `agent-data.js` (the sibling fetch).
- `static/js/areas/chat/socket.js`, `agent-drawer.js`.
- `css/studio.css`, `docs/ui-testid-registry.md`, `scripts/run-tests.sh`.
- `tests/browser/test_flow_agent_editor_follows_approval.py`.
- `the_one/agents.md`.

## Citation Audit
From the design survey and the design review on the working tree (Legs 1-2
landed, Leg 3 in progress; no studio files touched).
- `agent-editor-controller.js` (798 lines):
  - `onSaveError_` at ~100-188 is called only from `save`;
  - `saveInFlight` is a closure at ~197;
  - `buildCallbacks_` is at ~285-374.

  Verified by the review.
- `studio.js:570-580` `activate` → `_refresh` → `loadAll(true)` → `doSelect`;
  `agents-list.js:329-420` fetches the agent and re-patches it in full —
  verified (review).
- `studio-event-bus.js`: a `document` CustomEvent wrapper with no `off`,
  loaded at `index.html:107` after `socket.js` at :105 — verified (review).
- `agent-editor-selfconfig.js` `recheckStoredNote_` (the JSON snapshot compare),
  the `live` guard with no section term (comment at ~84-88) — verified.
- `general-tab.js` `applyStored` 302-316, the note 219-222 and 320-345 —
  verified.
- `agent-form-data.js` `collectFormData` keys (`provider_config_id`, `model`,
  `max_iterations`, `chat_history_retention_days`, `rich_visuals`,
  `enabled_tools`, `disabled_tools`, `mcp_source_ids`, `kb_ids`, …) —
  verified (review).
- `app.js:155-166` (lazy area init) and `chat.js:613-627` (the socket connects
  on activate and is kept on deactivate) — verified.
- **Design review** (Developer, Sonnet), approve with changes. Folded in:
  - the record needed an eager owner (high);
  - the notes must be drawn at every mount (high);
  - a central clean/dirty decision replaces per-tab return values (high);
  - the split into this leg and Leg 8;
  - the event bus;
  - the controller split's line count;
  - the de-duplication's owner;
  - hidden-editor apply;
  - no deferral during Save.

  No second cycle: the reviewer's own mechanisms.
