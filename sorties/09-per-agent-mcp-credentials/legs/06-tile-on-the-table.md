# Leg: tile-on-the-table

**Status**: planning
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
