# Leg: fill-client

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective

A fill reaches the agent editor in the window whose drawer sent the turn,
as unsaved edits the operator reviews and saves.
- The drawer that sent the turn:
  - claims the fill;
  - opens the agent editor (new or existing);
  - waits for it to settle;
  - writes the values as unsaved edits, keeping any field the operator has
    changed and not saved;
  - marks each filled control with a quiet note;
  - reports the outcome.
- Every chat instance showing the conversation draws a receipt for the
  fill (Chats read-only).
- **Fill now** retries a fill that did not apply.
- Focus never moves.

**Two parts, each its own Developer pass, run in order** (design review
cycle 1 suggested the split as a reviewable boundary):
- **Part A, the receipts:** the frame feed, `fill-receipts.js`, ordering
  with the proposal cards, `noteFlag` gaining `fill`, and the Fill now
  button calling a stub hook.
- **Part B, applying:** the ready seam, the picker accessor,
  `agent-editor-fill.js`, the `name` handle, the focus suppression, the
  applier (queue, claim, navigate, write, outcome) and Fill now wired to
  it.

Part A lands first, and Part B builds on it. Both are in batch B.

## Context

- **The design is flight DD7, plus DD6's statuses and Leg 5's "Hand-off to
  Leg 6"** (`legs/05-fill-server.md`).
- **The server contract** (Leg 5, landed):
  - **Frames.** `fill_requested` and `fill_changed`, each `{type,
    session_id, fill: view}`, go to every socket bound to the chat. The
    `proposals_snapshot` frame also carries `fills: [view]`
    (`the_one/gleepglorp/proposals/events.py` ~:58-71).
  - **View keys.** `id, kind, action, agent_name, status, outcome {kept,
    reason}, untrusted, untrusted_sources, created_at, claimed_at,
    resolved_at, tool_call_id, values, changes, base, labels, title,
    field_count, target_gone, stale`.
    - `values` are the stored field names with ids; they are the **twelve
      allowed keys**:
      - `name` (create only), `description`, `system_prompt`;
      - `provider_config_id`, `llm_model`;
      - `enabled_tools`, `disabled_tools` (tool names);
      - `mcp_source_ids`, `kb_ids`;
      - `rich_visuals`, `max_iterations`, `chat_history_retention_days`.
    - `changes`, `base` and `labels` are the display forms.
  - **Routes.**
    - `POST /api/gleepglorp/fills/{id}/claim` returns `{fill, claim}`, or a
      409 `{error: "claimed", status}`.
    - `POST .../outcome` takes `{claim, status: filled|partly_filled|
      not_filled, kept, reason: in_chats|stay|editor_unavailable|
      target_gone|null}`. `kept` is a non-empty subset of the `changes`
      keys for `partly_filled`.
- **What the code has today** (`S` = `static/js/areas/studio`, `C` =
  `static/js/areas/chat`; checked by the recon and by design review cycle
  1):
  - **Editor mount and patch.**
    - `S/agent-editor-controller.js::renderEditor` (~:171) keys the slot
      `create` / `edit:{name}`.
    - `patchEditor_` (~:208-218) calls `h.patch`, which runs
      `general.setAgent` and each tab's `setAgent`. That **resets every
      value to the stored one** and re-takes the snapshot
      (`agent-editor.js` ~:349-376). So a patch always wipes unsaved fill
      values.
  - **The controller is per area init**,
    `App.studio.agentEditorController.create(ctx)`, built lazily when the
    Studio area first mounts (`app.js` ~:165 `mountArea`). There is no
    `App.studio.agentEditor` namespace. The follow module keeps a
    module-level `activeHandle` (`agent-editor-follow.js`).
  - **Async loads.**
    - `agents-list.js::doSelect` (~:322-423): early returns come before
      `selectSeq` is bumped (~:327-328); its `Promise.all(...).then(...)`
      has a stale return and no rejection handler.
    - `doEnterCreateMode` (~:445-490) returns early when create is already
      open, and calls `focusNameField()` at ~:486.
    - `areas/studio.js`: `_refresh` (~:570) is `loadAll(true).then(doSelect)`
      with a `.catch`; `activate` (~:681); and there is the init path,
      `state.bootLoad`.
    - The editor stays mounted when the operator leaves Agents with a
      clean editor. Re-entering runs `activate` → `_refresh` → `doSelect` →
      `patchEditor_`.
  - **The model list.** `agent-model-picker.js::fetchModelsForProvider`
    (~:100-196) never rejects. On success it re-takes `state.snapshot` when
    `!state.dirty` (~:175-196). `state.dirty` changes only in
    `checkDirty()` (`agent-form-data.js` ~:31-35), and the handles write
    silently. The mount-time fetch's promise is discarded
    (`wireEditorEvents`, ~:270-278).
  - **The handles.**
    - **`general-tab.js`** (handle ~:429-444): `setField` (~:327-334)
      covers description, system_prompt, max_iterations,
      chat_history_retention_days and rich_visuals, with no name.
      `nameInput` (~:76) is written only by `setAgent`. `setModel`
      (~:338-353) sets `pendingValue`, and the caller then calls
      `picker.fetchModelsForProvider`. `placeNote` (~:355-368) appends,
      and has no `name` host.
    - **Tabs** (`TAB_GROUPS` follow ~:46-50) have `followMap`,
      `followMapFor`, `followSet` and `followPlace`, all silent.
      - **Tools:** `enabledSetFor` (`tools-tab.js` ~:117-131) uses
        `enabled_tools` as a whitelist when non-null and ignores
        `disabled_tools` for non-exempt tools. Save (`agent-form-data.js`
        ~:150-164) stores whichever form is shorter.
      - **MCP:** it skips ids missing from its entries. Follow refreshes
        and calls `setSources` first (~:279-288).
      - **Knowledge:** `followMap()` is `null` until its list loads.
  - **Follow's dirty test.** `dirtyGroup_` (~:152-154, closed over in
    `create`) compares form snapshot to baseline per group. The tab-item
    test is inline in `applyTabGroup_` (~:200-201). The module exports
    only `{create, GROUPS}`. `applyAgent_` rebases (~:251), which a fill
    must never do. `drawNotes_` (~:110-148) redraws approved notes at every
    `afterMount`, removing only its own testid.
  - **Routing.**
    - `App.router.go(route, {opener})` resolves `false` on Stay, and also
      when the router hasn't started or the target isn't a route
      (`router.js` ~:766).
    - It joins a pending guard decision and overrides its target
      (~:768-773).
    - Resolving `true` does not mean the editor has mounted.
  - **The chat side.**
    - `C/turn-frames.js::handle` (~:75-222) ignores unknown frames.
    - `state.ownTurn[sid]` (`instance.js` ~:120) is set at `send.js` ~:79
      and `session-flow.js` ~:354, and cleared at `turn-frames.js`
      ~:173/~:207 and `session-flow.js` ~:66-72. It is set synchronously at
      send, by the sending instance only, and is not on `ctx`.
  - **Proposal cards.** `C/proposal-cards.js`:
    - anchors after the turn group of `tool_call_id` (~:442-452);
    - orders cards by `proposal.id` in `isBoundary` (~:432-438);
    - uses literal, unprefixed testids, even in the drawer, because the
      `gg-` prefix comes only from the construct-time sweep
      (`instance.js` ~:89-98).
  - **Library and config.**
    - `App.ui.noteFlag` (`js/ui/feedback.js` ~:198) throws for subjects
      other than `note`, `routine` and `proposal`. Its contract test pins
      that error (`tests/browser/test_ui_feedback_contract.py` ~:531-542),
      and its catalogue row is `docs/ui-control-inventory.md` ~:77.
    - The dev flag is `App.config.dev_mode` (`app.js` ~:205-235).
    - The bot glyph is `App.ui.util.icon('bot')`.
  - **The 800-line cap** applies to `areas/**.js`
    (`tests/test_area_module_size.py:21`). New code goes in new modules.

## Design decisions (within DD7; cycle 1 corrections folded in)

1. **Who applies.** Only a **drawer** instance applies, and only for a
   `fill_requested` whose `session_id` equals its bound session while it
   owns the turn.
   - Ownership is read-only `ctx.send.ownsTurn(sid)` (a new accessor over
     `state.ownTurn`).
   - The Chats instance and any other drawer draw receipts only.
   - A snapshot never applies.
2. **A per-window queue.** Fills apply strictly one at a time, in id order.
   A claim 409 skips the fill silently, whether it is `replaced`, already
   claimed elsewhere, or final.
3. **The ready seam lives in the fill module, not on the controller.**
   - `S/agent-editor-fill.js` keeps a module-level registry. The
     controller registers its handle when created, as follow's
     `activeHandle` does.
   - `App.studio.agentEditorFill.whenSettled(key, {timeoutMs})` first
     waits for a controller to register (the Studio area inits on the
     navigation to Agents). It then resolves `true` once all of these hold
     together, re-checked after a microtask:
     - **(a) the slot key** equals `key`;
     - **(b) the router** is on `agents` at that route;
     - **(c) no Studio load is pending:**
       - The counter is incremented in `doSelect` and `doEnterCreateMode`
         **after** their early-return guards. It is decremented on settle,
         on reject and on the stale return; add a rejection handler.
       - `_refresh` and `state.bootLoad` count too.
     - **(d) the picker's new `modelsSettled()`** is true. It is backed by
       an in-flight count in `fetchModelsForProvider`, so the mount-time
       fetch is seen.
       - The count goes up at entry and down exactly once, through a
         `.then(done, done)` on the returned promise.
       - That covers the early returns (no select, no provider), an abort,
         a `live()` or active-provider drop, and a failure.
   - It resolves `false` at the timeout. The default is 10000 ms, and a
     test override, `window.__ggFillSettleTimeoutMs`, is read only when
     `App.config.dev_mode`.
4. **Navigation.**
   - **The target** is `#agents/~new` for a create, and
     `#agents/{agent_name}` for a change.
   - **No navigation only when** the slot key equals the target's key
     **and** the router's current route is that editor on `agents`. Then it
     selects the General tab through the editor's own tab control.
     Otherwise it calls `App.router.go(target, {opener})`, with `opener`
     the drawer composer input.
   - **If a leave-guard dialog is already open** (`App.ui.modal.anyOpen()`
     or the router is deciding), the fill does not navigate. It reports
     `stay`, and Fill now remains.
   - **`go` resolving `false`** reports `stay`.
   - **The create-focus suppression** is a one-shot
     `App.studio.agentsList.suppressNextCreateFocus()`. It is consumed by
     `doEnterCreateMode` in place of `focusNameField()`, and **always
     cleared** by the applier in a `finally` after `go` and `whenSettled`
     (`clearCreateFocusSuppression()`). Stay, an already-open create form
     or a superseded navigation can therefore never leak it to the next
     New agent.
5. **Availability before writing (all or nothing).**
   - After settling and before any write, it checks that everything the
     fill needs is there:
     - the knowledge tab's `followMap()` is non-null when `kb_ids` is
       present;
     - every `mcp_source_ids` id is in the MCP entries after a refresh and
       `setSources`;
     - a change's editor holds the agent.
   - If anything is missing, nothing is written and the result is
     `not_filled` / `editor_unavailable`, or `target_gone` for a missing
     agent. Skipped keys are therefore never possible.
6. **Writing** (`agent-editor-fill.js::apply(view)` → `{written, kept}`),
   in this order:
   1. **The allowlist.** Only the twelve keys are accepted. Any other key
      is ignored, with one console warning per fill.
   2. **Which groups are operator-dirty.** A group, or a tab item, counts
      as the operator's when **both** hold:
      - its current value differs from the snapshot (follow's
        `dirtyGroup_`, moved to module scope and exported with the
        tab-item test);
      - it differs from the value the last fill wrote there.

      The fill record keeps the written values per key and item for this
      reason, so a second fill or a Fill now never takes a first fill's
      values for the operator's.
   3. **Kept.** A dirty group is kept, and listed in `kept` (its stored
      keys present in `values`), unless the fill's value equals its current
      value. Then it is neither written nor kept.
   4. **The non-model General fields** go through `setField`, including the
      new `name` branch for create mode, which writes `nameInput` and
      clears the name error.
   5. **Tools.** A fill never widens the stored whitelist. Merge the
      editor's stored agent (or `{}`) with `values`:
      - **`disabled_tools` and no `enabled_tools`:**
        - With a stored whitelist (non-null `enabled_tools`), keep it as
          that whitelist minus the fill's `disabled_tools`. Exempt tools go
          through `disabled_tools`, as `enabledSetFor` does.
        - With a stored `enabled_tools` of null, keep it null and use the
          fill's `disabled_tools`.
      - **`enabled_tools` only:** keep the stored `disabled_tools` for the
        exempt tools.
      - Then call `followMapFor(cfg)`, then `followSet` for the items that
        are not kept. `enabled_tools: []` means none enabled.
   6. **MCP and Knowledge.** Build the id → bool map from `values` over the
      tab's `followMap()`, then `followSet` for the items that are not kept.
   7. **The model group last.** First resolve the pair:
      - `providerId` is `values.provider_config_id` if present, else the
        editor's current `providerSelect.value`;
      - `model` is `values.llm_model` if present, else the current model.

      A model-only fill then keeps the provider, and a provider-only fill
      keeps the model. Call `setModel(providerId, model)`, then
      **`checkDirty()` synchronously**, then **await**
      `fetchModelsForProvider(providerId)`. `state.dirty` is then already
      true when the list lands, so the picker's re-take is skipped.
      Writing the model before `checkDirty` would let the re-take rebase
      it as clean. This is cycle 1's high issue.
   8. **Finish** with `checkDirty()`, then the fill module's own note
      draw. The apply triggers no `afterMount`, so it must draw directly.
      Never touch `state.snapshot`.

   **The outcome** follows from `written` and `kept`:
   - `written` non-empty and `kept` empty: `filled`.
   - `kept` non-empty: `partly_filled`.
   - Both empty: every value already matched, so `filled` with field count
     0. Leave the receipt's wording to it.
7. **Notes.** The record is `{key, at, values: {storedKey|tab:item:
   writtenValue}}`.
   - **Drawing:** the controller's `afterMount` calls the fill module's
     `afterMount` beside follow's (~:201, ~:217). It removes
     `[data-testid="agent-filled-note"]` itself (idempotent), then draws
     a note for each recorded key **whose control still holds the recorded
     value**.
   - **The note:** "Filled by GleepGlorp · {formatClock}" with the bot
     icon. It goes in via `general.placeNote`, with a new `name` host on
     the name field, or via `followPlace`.
   - **Approved notes:** they coexist, because `placeNote` appends.
   - **The record is cleared:**
     - in `patchEditor_` (a patch resets every value);
     - on a successful Save;
     - on Cancel;
     - on the slot's destroy or key change (`slot.mount` destroy, ~:182-186).
8. **The receipts** (`C/fill-receipts.js`, wired beside `proposalCards`).
   - **The feed:** `turn-frames.js` gains `fill_requested` and
     `fill_changed` branches, gated on `session_id === boundId()`. The
     `proposals_snapshot` branch also feeds `data.fills`.
   - **Testids are literal and unprefixed**, as on the proposal cards:
     `fill-receipt` with `data-status` and `data-fill-id`, and its buttons
     `fill-receipt-fill-now` and `fill-receipt-show-form`. Tests tell the
     instances apart by container (`#gleepglorp-drawer`).
   - **One shared order with the proposal cards.** Within a turn group,
     cards and receipts are ordered by:
     1. the DOM position of their anchoring `[data-tool-call-id]`;
     2. then `created_at`;
     3. then kind and id.

     An element with no `tool_call_id`, or with no anchor found, goes
     after the anchored ones, in `created_at` order. Both modules' boundary
     checks use one small shared helper for this. The proposal-only order
     by `proposal.id` is replaced by this key; for proposals alone it
     gives the same order, which A2 and the existing proposal tests pin.
   - **Timing:** a new receipt is held while the turn is busy, then drawn on
     `turnEnded`.
   - **States:**
     - **`sent` / `applying`:** "Filling the form…".
     - **`filled`:** "Form filled", the title, "{n} fields", "Not saved",
       the "Check this" flag with its sources when `untrusted`
       (`noteFlag` subject `fill`), and Show the form (a guarded go to the
       target).
     - **`partly_filled`:** "Form partly filled" plus "You had changed
       {labels} and not saved them, so I left them."
     - **`not_filled`:** "Form not filled" plus the reason, and Fill now
       (not for `target_gone`):
       - `in_chats`: "You were in Chats when it arrived."
       - `stay`: "You chose to stay on the page you were editing."
       - `editor_unavailable`: "The agent editor could not open."
       - `target_gone`: "That agent no longer exists."
     - **`replaced`:** "Replaced by a newer fill.", with no actions.
     - **Stale fields:** a receipt offering Fill now with a non-empty
       `stale` adds "Changed since GleepGlorp filled it: {labels}."
   - **Fill now is offered:**
     - on `not_filled`;
     - on `sent`, when this window is not applying it;
     - on `applying`, when this window is not applying it and `claimed_at`
       is more than 120 s old (the server lease; the applying window went
       away). A claim 409 there shows "Still being applied in another
       window.".
   - **Fill now is drawer-only.** In Chats a receipt has no buttons.
   - **The hook surface** is defined in Part A: the instance config's
     optional `fillHooks = {fillNow(view), isApplying(id)}`, defaulting to
     a no-op and `false`. Only the drawer passes it, in Part B.
     - Part A's receipts read `isApplying` and call `fillNow`.
     - Claiming and enqueueing live entirely in Part B's `fillNow`. A Part
       A click with the default hook therefore does nothing and can never
       strand a fill in `applying`.
9. **`noteFlag`** accepts the subject `fill` with its own wording. The
   throw message, the doc comment, the catalogue row and the contract test
   all change.

## Acceptance Criteria

**Test apparatus** (both parts):
- `seeders.seed_gleepglorp_fill(...)` inserts a row by sync sqlite3, as
  `seed_gleepglorp_proposal` does (`tests/browser/seeders.py` ~:586-640).
- The drawer helpers `_RECORD`, `_DELIVER` and the drawer socket index
  move from `tests/browser/test_flow_gleepglorp_drawer_chat.py` to
  `tests/browser/_drawer.py`. That is a refactor; the drawer tests keep
  passing.
- **The live path:** a real drawer send with the mock provider's
  `delay_ms` keeps the turn open (precedent ~:190). A seeded fill's
  `fill_requested` is then delivered into the drawer socket, and the claim
  and outcome use the real routes.
- New flow tests go in `tests/browser/test_flow_gleepglorp_fill.py`
  (`shared` lane).

### Part A (receipts)

- **A1 — Live and reload.**
  - A delivered `fill_requested` draws a `fill-receipt` after the turn
    group of its `tool_call_id`, held until the turn ends.
  - `fill_changed` updates it in place through every status: applying,
    then each final state. Each state's text is pinned.
  - After a reload, the snapshot's `fills` draw the same receipts.
- **A2 — Mixed order.** A proposal and a fill made in one turn keep their
  tool-call order, live and after a reload, whichever frame arrived first.
  `tests/browser/test_flow_chat_proposals.py` passes unchanged.
- **A3 — The flag.** An untrusted fill shows the "Check this" flag with its
  sources.
- **A4 — Read-only in Chats.** The same conversation opened in Chats draws
  the receipts with no buttons. In the drawer, Fill now shows for:
  - `not_filled`, other than `target_gone`;
  - a `sent` fill;
  - an `applying` fill whose `claimed_at` is more than 120 s old.

  With a test-stubbed `fillHooks`, a click calls `fillNow` with the view.
  With the default hook it does nothing and sends no request. `filled`
  shows Show the form, which navigates through the guard.
- **A5 — `noteFlag({subject: 'fill'})`** renders its wording in Chromium
  and WebKit, and an unknown subject still throws.

### Part B (applying)

- **B1 — Settle, then write.**
  - From Library, with the drawer open, a change fill for agent A opens the
    editor and shows every filled value.
  - They remain after the activate re-patch, because `whenSettled` waits
    for it: write after the last patch.
  - The unsaved caption shows and Save is enabled.
  - The same holds when A's editor is mounted but the operator is on
    Library (it must navigate), and when A's editor is open on Agents
    (no navigation: `App.router.current()` is unchanged).
- **B2 — Every field type.** One fill carries description, system prompt,
  provider plus model, `enabled_tools`, MCP ids, KB ids, rich visuals,
  step limit and retention. Each control shows the value, with the model
  selected after the list loads.
  - **Cancel** restores every stored value.
  - **Save** stores them, and the API read-back matches. The tools check
    compares the **effective enabled set**.
  - A create fill also fills the name.
  - A `disabled_tools`-only fill against a stored whitelist turns the
    named tools off. A tool outside the stored whitelist stays off.
- **B3 — The model group.**
  - **Provider plus model:** a fill that carries both leaves the editor
    dirty after the list loads, and Cancel restores the stored pair. This
    pins the write order.
  - **Model only:** keeps the stored provider and selects the new model.
  - **Provider only:** keeps the current model id under the new provider.
  - **Deleted provider:** a fill whose provider has since been deleted
    still writes the model, under "Unknown provider (id)".
- **B4 — The operator's edits win.** With the operator's unsaved system
  prompt, a fill of `system_prompt` and `description`:
  - writes only the description;
  - posts `partly_filled` with `kept: ["system_prompt"]`;
  - gets a receipt naming "System prompt".

  A toggled tab item is kept the same way.
- **B5 — Two overlapping fills.** Fill 1 writes the description, then
  fill 2 changes the description again. Fill 2 writes it and is `filled`,
  not `partly_filled`. Fill now on a filled fill behaves the same way.
- **B6 — The notes.**
  - Each filled control has an `agent-filled-note` ("Filled by GleepGlorp
    · {time}", the bot icon) in create and edit mode.
  - An approved-change note on the same field still shows.
  - The notes are gone after Save, after Cancel, after the editor closes,
    and after a patch, which also resets the values.
  - A note whose control the operator then edits is not redrawn on the
    next `afterMount`.
- **B7 — Who applies.**
  - A second page in the same context, joined to the same drawer chat,
    draws the receipt and sends no claim. The second page opens its drawer
    so it re-joins the stored conversation.
  - The Chats instance never claims.
  - A fill delivered after `done` is not applied.
  - Two fills delivered together apply in id order: the second is claimed
    only after the first's outcome.
- **B8 — Not filled.**
  - **`in_chats`:** the operator is in Chats when the fill arrives.
  - **`stay`:** with a dirty Library editor, the leave guard asks once and
    Stay is chosen. Focus returns to the drawer composer.
  - **`stay`:** with a leave-guard dialog already open, the fill does not
    navigate.
  - **`target_gone`:** the agent was deleted.
  - **`editor_unavailable`:** the settle timeout is forced through the
    dev-mode seam, or an MCP id is unavailable.

  Nothing is written in any of these cases, and each receipt shows its
  reason.
- **B9 — Fill now.**
  - After an `in_chats` not-filled, on Agents, Fill now in the drawer
    claims and applies, and the receipt becomes "Form filled".
  - After a reload with a `sent` fill, Fill now works.
  - A stale field is named on the receipt.
- **B10 — Focus never moves.**
  - **A create fill** keeps focus on the drawer composer
    (`gg-chat-input`).
  - **The next ordinary New agent** focuses the name field, both after a
    successful create fill and after a Stay on one. This tests the
    `finally` clear.
  - **A change fill** leaves focus where it was.
- **B11 — The client allowlist.** A delivered view whose `values` also
  holds `secret_ids`, `tool_overrides` and `notes_enabled` writes none of
  them.

### Falsifications (each edited out, run, restored by editing, and recorded in the flight log)

- **Part A:**
  - the mixed-order rule (A2 fails);
  - the `session_id` gate on the new branches (a frame for another chat
    draws a receipt).
- **Part B:**
  - the pending counter (B1 fails);
  - the model write order, with `checkDirty` moved after the await (B3
    fails);
  - the last-written-value rule (B5 fails);
  - the dirty check (B4 fails);
  - the `ownsTurn` condition (B7 fails);
  - the allowlist (B11 fails);
  - the `finally` clear of the focus suppression (B10 fails).

## Assertion edits allowed

- **`tests/browser/test_ui_feedback_contract.py`**: no edit is expected.
  `test_note_flag_role_name_and_icon` (~:527-575) asserts only `"subject"
  in out["err"]`, so keep the word "subject" in the reworded throw
  message. Add the `fill` case as a new test.
- **Moving the drawer test helpers to `_drawer.py`** changes their import
  path, not any assertion.
- **Nothing else.** Any other failing assertion is a `[BLOCKED]` with the
  test and line.

## Verification Steps (each part)

1. Run the static guards: `tests/test_ui_guards.py`,
   `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`,
   `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`,
   `tests/test_ui_control_inventory.py`, `tests/test_area_module_size.py`,
   `tests/test_store_static.py`, the testid registry test, and ruff.
2. Run the unit tier once (`THE_ONE_TEST_NETNS=1`), recording the start
   `uptime`.
3. Run the browser lanes one at a time with `THE_ONE_TEST_NETNS=1` and
   `THE_ONE_REQUIRE_WEBKIT=1`:
   - **Part A:** `contracts-controls`, `chats-transcript`, `chats` and
     `shared`.
   - **Part B:** `agents`, `agent-tabs`, `routing` and `shared`.
4. Run that part's falsifications.

There is no full parallel run; the batch B end runs it.

## Edge Cases

- **A fill arrives while the drawer is closed** but its socket is bound,
  on Agents, Library or Settings. It still applies. The receipt is there
  when the drawer opens.
- **New chat pressed in the drawer mid-turn:** the binding moves, and later
  frames for the old chat no longer pass the gate. A fill already queued
  completes.
- **A change fill whose provider was deleted after the fill:** `setModel`
  shows "Unknown provider (id)". The fill is still written, and Save's
  validation reports it.
- **A create fill while a dirty create form is open (same key):** dirty
  groups are kept, as in B4.
- **The Studio area has never been opened in this window:** the navigation
  to Agents creates the controller, and `whenSettled` waits for its
  registration.

## Files Affected

- **New:**
  - `S/agent-editor-fill.js`;
  - `js/gleepglorp-drawer/fill.js` (the applier: queue, claim, Chats
    check, navigation, outcome, `fillNow`);
  - `C/fill-receipts.js`;
  - `tests/browser/_drawer.py`;
  - `tests/browser/test_flow_gleepglorp_fill.py`.
  - The new scripts are listed in `index.html` in load order.
- **Changed:**
  - **Studio:** the controller (registration, the fill `afterMount`, the
    clear in `patchEditor_` and on destroy), `agents-list.js` and
    `areas/studio.js` (the pending counter, the focus suppression),
    `agent-model-picker.js` (the in-flight count and `modelsSettled`),
    `general-tab.js` (the `name` in `setField` and its note host), and
    `agent-editor-follow.js` (`dirtyGroup_` and the tab-item test moved to
    module scope and exported; behaviour unchanged).
  - **Chat:** `instance.js` (`fillReceipts`, `ownsTurn`, the
    `onFillRequested` config hook), `turn-frames.js`, `proposal-cards.js`
    (the shared order) and `gleepglorp-drawer/chat.js` (the hook).
  - **Library:** `js/ui/feedback.js`.
  - **CSS** on tokens only.
  - **Seeders:** `tests/browser/seeders.py`.
  - **Docs and catalogues:** `docs/ui-testid-registry.md`,
    `docs/ui-control-inventory.md`, `the_one/agents.md` ("GleepGlorp
    fills, browser (M36 F3 L6)"), `CLAUDE.md` (one paragraph) and
    `SECURITY-MODEL.md` (the client allowlist; values arrive as unsaved
    edits, and only Save stores them).
- **Not touched:**
  - Python under `the_one/`, except docs;
  - `evals/`;
  - the prompt and the guide;
  - `agent/core.py`.

## Citation Audit (2026-11-20)

The citations come from an Explore recon, then re-checked by design review
cycle 1. That review corrected:
- `areas/studio.js` (not `S/studio.js`), with `_refresh` ~:570 and
  `activate` ~:681;
- no `App.studio.agentEditor` namespace;
- `App.config.dev_mode`, not `App.devMode`;
- the `isBoundary` id ordering ~:432-438;
- the testid prefix sweep at `instance.js` ~:89-98;
- the `noteFlag` contract test at `test_ui_feedback_contract.py` ~:531-542.

The other recon citations held.
