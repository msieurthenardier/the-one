# Leg: tile-on-the-table

**Status**: completed
**Flight**: [Per-agent MCP credentials](../flight.md)

## Objective
Rebuild the agent Tools tab's MCP tile credentials section on `App.ui.keyValueTable`, exactly as in the operator-approved rendered mockup (DD12):
- a locked table of effective headers or environment variables, with an "overridden" pill;
- an action row of status text, **Override headers** and **Test**;
- after Override, the Library's editable table, with the action row **Cancel**, **Save** and **Test**;
- the tile's Save writes immediately through leg 5's targeted route.

The agent editor's main Save stops carrying credentials, Refresh is removed, and the leg 3 per-row UI and its testids are retired. The browser tests and the behavior spec are rewritten to match.

## Context
- DD12 in `../flight.md` (with its "Mockup review changes") and the approved mockup are the design. The mockup page is `scratchpad/dd12-mockup/mockup.html` (served on 8491 during the HAT); its screenshots are in the flight log's approval entry. Read DD12 first.
- **Leg 5 provides:**
  - the server `plain_names` field (unmasked in agent responses; the merge prunes it; omitted keeps it; `Authorization` is never plain);
  - `PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials` (accepts an unattached source and returns the updated agent);
  - `App.ui.keyValueTable` options `readOnly`, `lockBy`, `onBeforeRemove`, `markerBy`/`markerLabel` and `removableBy`, with `setRow` re-evaluating them.
  
  Read the leg 5 flight-log entry for what actually landed.
- The DD12 scoped design review (flight log) gives the row model and payload mapping this leg follows.
- **What stays from leg 3:**
  - the status line (`setStatusImpl`, its texts, generation guard and polite region);
  - the test triggers (switch-on, first expand, Test, after a Save);
  - the AC6 list choice (a credentialed agent never sees the shared list);
  - `hasStoredCredential`, `splitItems` and `placeSaveErrors`;
  - the handle used by `mcps-tab.js`.
- **Security-sensitive:** no stored sensitive value is ever rendered. A non-sensitive per-agent value is shown in clear by design (DD12).

## Inputs
- Leg 5 landed and committed.
- The HAT instance (8486) and the mockup server (8491) are in use; don't touch them.

## Acceptance Criteria

**Locked view**
- [ ] AC1. An expanded MCP tile shows a section titled exactly as the Library's (`mcp-env-headers.js::titleFor`: "Headers", or "Environment variables" for stdio), with no button in the section header. It holds a `keyValueTable` with `readOnly: true`, Key and Value columns only, one row per **effective** name:
  - the server's names first, in their order;
  - then this agent's own names A-Z;
  - an `Authorization` row when `oauth_active` or a `bearer_token` is stored.
  
  Values:
  - a stored sensitive agent value shows its mask string as returned by the API;
  - a stored non-sensitive agent value shows in clear;
  - a server value shows as the Library shows it (a plain config value in clear, a secret's mask, or empty);
  - an empty value shows the `value` placeholder.
  
  Rows this agent overrides carry the **"overridden"** pill (`markerBy`). The locked view has no eye button, no Sensitive column, no trash and no "+ Add row".
- [ ] AC2. The action row is the status text on the left, then **Override headers** ("Override environment variables" for stdio) and **Test**, using the Library editor's button kinds (secondary Override and Test, Test with its play icon). **Refresh is removed.** The status texts and their precedence are unchanged from leg 3 ("Testing…", "Connected with this agent's values · N tools", "Needs a value for X", the error headline, the sign-in note, "Not listed with this agent's values yet", "Last checked …").

**Unlocked view**
- [ ] AC3. **Override headers** swaps in the editable table, built with the same column definitions as the Library: Key, Value (`secret`), Sensitive toggle with the info button, trash and "+ Add row". Those definitions, plus `SENSITIVE_INFO` and `MASKED_SENTINEL`, are extracted into a shared helper (suggested `App.studio.mcpEditor.shared`) that `mcp-env-headers.js` also uses, with no behaviour change for the Library (its tests pass untouched).
  - A server row's key is read-only (`lockBy: 'key'`). The sign-in `Authorization` row is fully locked (`lockBy: 'row'`).
  - A server row with no override has an empty value (placeholder `value`) and a disabled trash (`removableBy`).
  - An overridden row shows its stored mask (sensitive) or clear value (non-sensitive), with its Sensitive toggle set from `plain_names`.
  - Trash on an overridden server row returns it to the server value (`onBeforeRemove` cancels the splice and `setRow`s it back). Trash on an agent-only row removes it.
  - Toggling a stored sensitive row to non-sensitive clears its value (the Library's `clearOnUnmask`), so the operator retypes it.
  - `Authorization` can't be made non-sensitive: its toggle is locked on.
  
  The action row becomes **Cancel**, **Save** and **Test** (secondary, primary, secondary). Focus moves to the first editable value input on unlock.
- [ ] AC4. **Save** sends this tile's payload to `PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials`:
  - the full name set: an unchanged sensitive name as `__MASKED__` under its stored spelling, a non-sensitive name as its clear text, a changed value as the new text;
  - an empty value on a server row and a removed row are left out;
  - `headers: null` / `env: null` when none remain;
  - `bearer_token: null` when `Authorization` changes over a stored bearer;
  - `plain_names` listing the non-sensitive names, or `null`.
  
  On success the tile rebases on the returned agent (including `mcp_tool_cache`), locks, announces "Saved" through its live status, re-runs the test once with `overrides: null`, and moves focus to the Override button. On a 422 the messages land on their rows through `table.setError` (`loc` name to row index at call time; unplaced ones go to the section error). The table stays unlocked and focus goes to the first refused field.
  
  Save is disabled while nothing has changed, and for an agent that has never been saved (create mode), where a one-line note says "Save the agent first to set its own headers."
- [ ] AC5. **Cancel** restores the baseline and locks; focus returns to Override. **Test** while unlocked runs `/test/agent` with the unsaved payload (leg 3 behaviour); while locked, with `overrides: null`.

**Integration**
- [ ] AC6. `agent-form-data.js` no longer merges credential payloads into the main Save's `mcp_overrides`. The main PUT carries tool filters only, plus the leg 3 stored-filter copy rule and the empty-entry drop, and the server's omitted-keeps rule preserves the credentials and `plain_names`.
  - An unlocked tile with unsaved edits registers as a dirty source with the editor's leave guard (`App.nav`), so leaving asks once. It doesn't enable the main Save.
  - `setAgent` (select, main Save, Cancel) discards unsaved tile edits and locks.
  - Opening, looking and closing a tile leaves everything clean.
- [ ] AC7. `mcps-tab.js` mounts the new section and wires the trio and Override; its leg 3 hooks (`credentialPayloads`, `afterSave`, `showCredentialErrors`) are removed or replaced as the new flow requires. `agent-editor-controller.js` stays at or under 800 lines; its credential-save hooks are removed where the main Save no longer carries credentials. The leg 3 per-row code is deleted from `mcp-agent-credentials.js`: `pend`/`news`, `computeRows`, `buildRow`, the per-row buttons, the states and "Add header". The `.mcp-agent-cred-row*` CSS is deleted. Every `areas/` module stays under 800 lines.

**Testids, tests, spec, docs**
- [ ] AC8. Testids:
  - **Kept:** `mcp-agent-cred-section-`, `-status-`, `-test-`, `-error-`, `-live-`.
  - **New:** `mcp-agent-cred-override-{id}`, `mcp-agent-cred-save-{id}`, `mcp-agent-cred-cancel-{id}`, `mcp-agent-cred-table-{id}`, `mcp-agent-cred-add-{id}`.
  - **Retired:** every per-row leg 3 testid (`-state-`, `-set-`, `-replace-`, `-reset-`, `-undo-`, `-reveal-`, `-name-`, `-input-`, `-row-`, `-row-error-`, `-empty-`, the old `-add-` if its meaning changed) and `mcp-refresh-tools-btn-`. They move to `docs/ui-testid-registry.md`'s "Retired testids" table **and** to `RETIRED_SELECTORS` in `tests/test_nav_helper.py`, in this leg.
  
  Rows are addressed through the table's `rowDataset` (for example `data-name`).
- [ ] AC9. `tests/browser/test_flow_studio_tools_mcp_credentials.py` is rewritten (lane `agent-tabs`). It covers:
  - the locked view (rows, pill, masks, clear plain value, no eye/toggle/trash);
  - Override and Cancel (baseline restored, focus);
  - set a value, then Save: the exact targeted-route body, the post-save re-test, the pill and the lock;
  - non-sensitive round trip (the value shown in clear after a reload);
  - trash on an overridden server row (back to the server value), on an agent-only row (removed), and disabled trash on a non-overridden server row;
  - Add row;
  - the Authorization toggle locked;
  - a 422 placed on its row;
  - Save disabled in create mode;
  - the main Save not carrying credentials (PUT body);
  - the leave guard with unsaved tile edits;
  - stdio "Environment variables";
  - switch-on test and generation guard (kept from leg 3);
  - a credentialed agent never shown the shared list (kept).
  
  `tests/browser/test_studio_mcps_tab.py` is updated for Refresh's removal, and nothing is weakened.
- [ ] AC10. `tests/behavior/per-agent-mcp-credentials.md` steps 4, 5, 6, 7 and 11 are re-authored around Override, typing into the table, the tile's Save, and reading the locked table (masked value plus "overridden" pill) instead of the state text. Step 6's Save is the tile's. Each changed step names its testids. The other steps keep their wording. The Validator's spec follow-ups from the last run are folded in where they apply: the pre-save state, the cached wording, the `editor-unsaved` observable, and the global mock response.
- [ ] AC11. `the_one/agents.md`: the Tools-tab half of the sortie 09 block and the MCPs-tab paragraph describe the DD12 tile, the targeted save, the main Save no longer carrying credentials, and Refresh's removal. `CLAUDE.md`'s tile sentence is updated. The flight log has the leg's entry.
- [ ] AC12. Gates:
  - the static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_ownership`, `test_ui_emitted_classes`, `test_area_module_size`, `test_store_static`, `test_nav_helper`);
  - the full `THE_ONE_TEST_NETNS=1 make test-unit`;
  - the full browser gate on a quiet host: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`, rc=0 or one failure that passes isolated and is logged;
  - ruff.
  
  Record the `PARALLEL_RESULT` line and budget notes.

## Checkpoint
16 ACs, so a mid-leg checkpoint commit:
- **Part A:** AC1-AC7 and AC8, with the rewritten test file's core cases green on `agent-tabs` and `agents`. The Flight Director commits.
- **Part B:** AC9's remaining cases, AC10, AC11 and AC12.

## Implementation Guidance
1. Read:
   - the approved mockup HTML (it shows the exact factory options and DOM adjustments the design needs);
   - leg 5's landed factory options;
   - `mcp-env-headers.js` (columns, partition, `remaskAfterSave`);
   - the current `mcp-agent-credentials.js`, `mcps-tab.js` and `agent-form-data.js`.
2. Extract the shared column builder; switch `mcp-env-headers.js` to it; run the `mcp` lane.
3. Rewrite the section module around a row model `{_rid, key, value, sensitive, _originalMasked, _server, _agent, _serverSet, overridden, lock, removable}`, following the DD12 review's payload mapping. Keep the public handle the tab uses where it still applies.
4. Wire the trio and Override in `mcps-tab.js`; remove Refresh; drop the credential merge from `agent-form-data.js`; register the leave-guard dirty source.
5. Retire the testids, rewrite the tests, re-author the spec, write the docs, then run the gates (background, one at a time; parallel gate on a quiet host).

## Edge Cases
- **The tile Save on a source switched on but not yet attached by a main Save:** allowed (leg 5's route accepts it), and the override persists. If the operator then discards the main form, the override stays stored for an unattached source (harmless; existing behaviour).
- **A store refresh while unlocked:** never reaches `setAgent` (leg 3 finding), so edits survive.
- **Two tiles unlocked at once:** each has its own Save; independent.
- **The narrow race** with a concurrent main Save: accepted (leg 5).
- **A non-sensitive value that looks like a mask:** dropped by the merge (documented in leg 5).

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-agent-credentials.js` (rewrite), `mcps-tab.js`, `agent-form-data.js`, `agent-data.js` (route call), `agent-editor-controller.js` (hooks), `mcp-env-headers.js` (shared builder), the shared editor module, `css/studio.css`
- `tests/browser/test_flow_studio_tools_mcp_credentials.py` (rewrite), `tests/browser/test_studio_mcps_tab.py`, `tests/test_nav_helper.py`
- `docs/ui-testid-registry.md`, `tests/behavior/per-agent-mcp-credentials.md`, `the_one/agents.md`, `CLAUDE.md`

## Citation Audit
Re-check every citation after leg 5 lands: its factory option names, `setRow` behaviour, the route path and response shape. The leg 3 module structure was cited from its landing report and code review (flight log).

---

## Design review changes (binding; they override the AC text above where they differ)
From the Developer design review (2026-11-04), with the Flight Director's calls on its questions. Leg 5 was committed at `56057a65`; re-run the Citation Audit against it.

1. **The tile's Save rebases only that tile** (`entry.cred.setAgent(saved)` and the tab's `currentAgent`), **never** the tab-level `mcps-tab.js::setAgent`/`patchEntry`. Those reset the attach switch and the tool rows from the stored agent, which would drop an unsaved attach or tool edit. New AC9 case: an unsaved attach switch and an unsaved tool check both survive a tile Save.
2. **The controller's copies follow a tile Save.**
   - A callback from the tab to the editor (for example `cb.onCredentialsSaved(updatedAgent)`), implemented in `agent-data.js` (the controller is at 792 of 800 lines), merges `mcp_overrides` and `mcp_tool_cache` into `self._selectedAgent` and the `self._agents` entry, as the existing `found.mcp_tool_cache = …` copy does, then calls `App.store.invalidate('agents')`.
   - The post-save re-test (`overrides: null`) reads the updated `currentAgent`, so the credentialed list choice holds.
3. **Authorization (Flight Director calls).**
   - On a source with `oauth_active`: **no** `Authorization` row in the table, locked or unlocked. A one-line note under the table reads "Authorization is supplied by this server's sign-in."
   - Elsewhere, an `Authorization` row (a stored `bearer_token`, a server-defined name, or a typed key matching `authorization` case-insensitively, re-evaluated on input) has an editable value and its Sensitive toggle **locked on**.
   - This needs one new factory value, **`lockBy: 'toggle'`**: the toggle is disabled and checked, and the rest stays editable. It is added in this leg with an engine-parametrised contract test and a catalogue update; `setRow` re-evaluates it.
   - The tile never puts `Authorization` in `plain_names`.
4. **Main Save, main Cancel and tile edits (Flight Director call).**
   - A dirty, unlocked tile is **left alone** by the main Save and the main Cancel, since credentials aren't part of that PUT. `patch`/`setAgent` skip a dirty unlocked tile's credentials section; the tool rows and switches rebase as today.
   - A clean tile rebases normally.
   - Only a new identity (another agent, a remount) discards tile edits, and the tile-level leave-guard source asks first.
5. **The leave guard.**
   - Register a **separate** `App.nav` source id (for example `'studio-mcp-tiles'`), with `isDirty = editorOpen && mcpsTab()?.anyDirty()` and a no-op `discard` (teardown already discards). Register it once, at studio level, beside the existing source (`studio.js:~702`), reaching the tab through the existing getter.
   - Remove the `onChange()` call from the credentials change path in `mcps-tab.js` (~415), so tile edits never enable the main Save.
6. **Dead main-Save credential code** is deleted, which also frees controller lines:
   - the `mcp_override` branch of `onSaveError_` (`splitItems`/`placeSaveErrors`, controller ~109-125);
   - `credIds` and the `afterSave` call (~590-591, ~734);
   - the `credentialPayloads` loop and the stored-filter copy rule in `agent-form-data.js` (~325-343).
   
   The empty-entry drop stays. `placeSaveErrors`/`splitItems` survive only if the tile's own 422 handling uses them. Context's "stays" list is superseded by this item.
7. **Shared helper.**
   - Extract into `mcpEditor.shared` (`mcp-editor-shared.js`): `titleFor`, `hintFor`, `rowsFromSource`, the column-definition builder, `SENSITIVE_INFO` and `MASKED_SENTINEL` (already there).
   - The builder takes testids from the caller and carries no Library testids. Update that file's header comment ("no DOM, stateless": the builder uses `App.ui` lazily).
   - **Load order:** `index.html` loads `mcp-agent-credentials.js` (~106) before `mcp-editor-shared.js` (~127). Read the helper lazily inside `create()`, or reorder the tags (and check any test pinning the order).
   - AC1's server-order rule is `rowsFromSource`.
8. **Testids** (this replaces AC8's list).
   - **Retire only:** `mcp-agent-cred-state-`, `-set-`, `-replace-`, `-reset-`, `-undo-`, `-reveal-`, `-name-`, `-input-`, `-row-`, `-row-error-`, `-empty-` and `mcp-refresh-tools-btn-`.
   - **Not retired**, since the names are reused for the new controls: `mcp-agent-cred-cancel-` and `mcp-agent-cred-add-`. `RETIRED_SELECTORS` matches by left boundary, so retiring them would break the new ids.
   - **Registry:** remove the live parametric rows for the retired prefixes, add rows for `-override-`, `-save-`, `-table-` (and update `-cancel-`/`-add-`), and move `mcp-refresh-tools-btn-` from the live table (~613) to the retired table. `tests/test_ui_guards.py` fails on a registered prefix with no build site, and on a built prefix that isn't registered.
   - **Convention:** the registry note says a retired id can't sit under a live family prefix. Retire the **exact full prefixes** above (each ends with its own segment); if the guard still objects, report it rather than weakening it.
9. **Rows addressing.** `rowDataset` is evaluated once, at row creation. Give every row a stable `data-rid` (the tile's `_rid`) through `rowDataset` and address rows by it in tests. Server rows also carry `data-name`.
10. **Mapping rules.**
    - A 422 `loc` name maps to its row case-insensitively for headers (exactly for env).
    - An unchanged stored sensitive name is sent as `__MASKED__` under the **stored override's** spelling, even when its row shows the server's spelling.
    - Emptying an overridden server row's value reverts to the server value: the name is omitted from the payload.
    - A typed key that duplicates another row's name (case-insensitively for headers) gets a row error, "This name is already in the table.", and Save is disabled until it's fixed.
    - Before `setRow` disables a focused remove button (trash on an overridden server row reverting it), move focus to that row's value input (accessibility review of leg 5).
11. **Create mode.** The tile reads `agentName == null` as create mode. Test and Override stay usable; Save is disabled with the note. Edge Cases gains: a new, never-saved agent can no longer carry credentials in its first Save (a change from leg 3, by design).
12. **`test_studio_mcps_tab.py`:** the Refresh dependencies (~844-851, ~1007-1087, and the clicks at ~1018/1047/1071) are re-driven with **Test**, keeping the merge-on-reload checks rather than deleting them. Keep `.mcp-agent-cred-status`/`-status-actions` CSS (`studio.css:~223-230`); delete `.mcp-agent-cred-row*` (~206-222).
13. **Housekeeping.**
    - The Checkpoint's "16 ACs" is 12.
    - AC10's follow-ups are from `tests/behavior/per-agent-mcp-credentials/runs/2026-11-04-00-59-35.md`.
    - Fix the leg 5 style nits in `ui/key-value-table.js` (the long line at ~250, the missing space at ~535).
    - Fix the pre-existing ruff E501 in the rewritten test file.
14. **Checkpoint (revised).**
    - **Part A:** the shared extraction; the module rewrite (locked and unlocked tables, trio, Override, tile Save and Cancel, `lockBy: 'toggle'` with its contract test); the tab and editor wiring (items 1, 2, 4, 5, 6); the testid and registry edits (item 8); and the new test file's core cases.
    - **Part B:** the remaining AC9 cases, AC10, AC11 and AC12.
