# Leg: editor-split

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Split `js/areas/studio/mcp-server-editor.js` (2,153 lines) into the DD3 modules, each 800 lines or fewer, with **no behaviour change**:
- strings move unchanged;
- every sink and allowance use moves through leg 01's `MOVES` rule;
- every pin on the old file is retargeted to the module that now holds its code.

## Context
- **Flight decisions:** DD3 (the split), DD2 (`MOVES`), DD10 (standing rules). Flight 4's `admin.js` split (leg 02a, `areas/admin/tools-page.js`) is the precedent.
- **Every later leg builds on these module boundaries.** Legs 03-10 each migrate one module onto the library. Keep each module's surface obvious, and keep cross-module calls explicit, through `App.studio.mcpEditor.*`.
- **The function map** (code survey §1a). Paths are under `js/areas/studio/`; MSE is `mcp-server-editor.js`.

| Module (new unless noted) | Takes from MSE |
|---|---|
| `mcp-editor-shared.js` → `App.studio.mcpEditor.shared` | `MASKED_SENTINEL` (:37), `OAUTH_MANAGED_SECRET_KEYS` (:44-51), `formatTimeAgo` (:58-68), `hasOAuthState` (:83-96), `SPEC_CAPABILITY_KEYS` (:103), `STDIO_RUNTIME_OPTIONS` (:124-162), `findStdioRuntimeOption`, `deriveStdioRuntimeSelection`, `lookupStdioRuntimeHint` (:167-228) |
| `mcp-server-info.js` → `.serverInfo` | `renderToolsListHtml` (:234-286), `renderCapabilityFlags` (:288-304), `renderServerInfoSection` (:315-430), `cacheHasServerInfo` (:434-437), `syncServerInfoSection` (:448-470) |
| `mcp-connection-fields.js` → `.connectionFields` | `renderConnectionFields` (:741-851), `mountChipListEditors` and `wireChipLists` (:957-991), `applyStdioRuntimeSelection` and `applyTransportVisibility` (:1549-1575) |
| `mcp-sandbox-fields.js` → `.sandboxFields` | the Sandbox section's markup, extracted from `renderMcpSourceEditor` (:583-622) into a function that returns the same string |
| `mcp-env-headers.js` → `.envHeaders` | `collectExistingKvRows` (:853-881), `SENSITIVE_HINT` and `renderKvTable` (:886-920), `renderKvRow` (:922-953), `updateKvHeadVisibility` (:1495-1500), `handleSensitiveToggle` (:1504-1541), `partitionKvRows` (:1761-1785); the key/value event delegation from `wireEditorEvents` (the input, change and click handlers for the eye, remove and Add row), as one `wire(container, onChange)` |
| `mcp-connection-status.js` → `.connectionStatus` | the Refresh, Reset, LED and "Last updated" row markup from `renderMcpSourceEditor` (:546-576), `wireResetButton` (:1410-1446), `syncResetButtonVisibility` (:1453-1487), `handleTestConnection` (:1792-2150) apart from the consent part |
| `mcp-oauth-consent.js` → `.oauthConsent` | `launchConsentPopup` and what it owns (:1841-2023): the status sub-nodes, the `message` listener, the poll, `renderRetryUi`. Today these are closures inside `handleTestConnection`, so the leg passes their free variables in explicitly. The behaviour stays the same; the teardown is leg 03's |
| `mcp-server-editor.js` (kept, the controller) | `renderMcpSourceEditor` (the mount and composition), `getFormSnapshot`, the rest of `wireEditorEvents`, `revertEditorToSource`, `collectFormData`; keeps `App.studio.renderMcpSourceEditor` (:2152) |

- **Boundaries and names may move** if a function's closure makes the cut unnatural (Acceptable Variations), as long as each module stays at 800 lines or fewer and owns one surface. Record any change in the flight log.
- **Load order:** the new scripts go in `static/index.html` immediately before `mcp-server-editor.js` (`index.html:104`), in the table's order, and after `ui/consent-link.js`. The controller reads `App.studio.mcpEditor.*` at call time.
- **Pins and anchors that read MSE by path** (DD3; `git grep mcp-server-editor` on the branch):
  - **`tests/test_store_static.py`:**
    - `:260` `test_mcp_list_stale_callback_follows_the_non_save_invalidations` reads two files: the `onTestConnectSuccess` window from the controller (it stays in `wireEditorEvents`), and the Reset window (`'/connection', { method: 'DELETE' })` … `return fetch(`, inside `wireResetButton`) from `mcp-connection-status.js`;
    - `:281` the per-file `invalidate('agents')` minimum of 2 becomes two rows, `("areas/studio/mcp-server-editor.js", 1)` (Delete) and `("areas/studio/mcp-connection-status.js", 1)` (Reset);
    - `:316-334` the four `INVALIDATION_ROWS` for MCP (save, delete, Reset, test-connect). Each points at the file that now holds its anchor, with the anchor text unchanged.
  - **`tests/test_consent_link_static.py`:**
    - `:23` the load-order consumer list replaces `mcp-server-editor.js` with `areas/studio/mcp-oauth-consent.js`, since the controller no longer calls the consent link;
    - `:48` `isSafeUrl(consentUrl)` and the `launchConsentPopup` … `onOAuthMessage` window are read from the module that holds them.
  - **`tests/test_ui_guards.py`:** `HTML_SINK_ALLOWANCE` (`:134-137`) and the `DYNAMIC_SINK_BASELINE` snippets (`:105-123`), each moved per file through `MOVES`.
  - **`tests/_ui_ownership_allowance.py`:** MSE's 31 rows / 105 uses are split by file, each moved row with a `MOVES` entry whose `retire_by` is `M31 F5 L10` (or the surface leg that retires it, if earlier).
  - **`tests/test_area_module_size.py:26`:** if the controller is at 800 lines or fewer, the entry is removed. Otherwise it is lowered to the new count, and leg 10 removes it.
  - **`tests/_ui_guard_helpers.py:263`:** a comment naming MSE for `mf-args` and `mf-sandbox-writable-paths`. Name `mcp-connection-fields.js`, which holds `mountChipListEditors` for both (they move together in leg 06).
  - **Comment-only path mentions** in `css/components.css:1343`, `css/studio.css:140` and `js/areas/admin/tools-form-helpers.js:1`: update them to the module that now holds the code.
  - **Docs naming the file:** `the_one/agents.md` (the module map and the invalidation map's file paths) and `docs/ui-control-inventory.md` (hand-built notes). Update the paths only; the content changes in leg 12.
  - Browser test comments citing MSE line numbers (`test_flow_studio_mcp_editor.py:231, :1162`, `test_flow_studio_knowledge_inventory.py:228`, `test_flow_chiplist_label_resolver.py`) may stay or name the new file. They are comments, not pins.

## Inputs
- Leg 01 landed: the `MOVES` rule is in, and the before set is taken.

## Outputs
- The seven new modules and the reduced controller, each 800 lines or fewer, with an IIFE header comment that names what it holds and what it exposes.
- `static/index.html` with the new script tags.
- The pins and docs above retargeted; the `MOVES` entries recorded.
- The flight log entry, with the `git grep` hits for `mcp-server-editor` pasted (DD10) and the module line counts.

## Acceptance Criteria
- [ ] **Behaviour-free:** the MCP editor's browser tests pass with no test-body change apart from path pins and the listed anchors:
  - `test_flow_studio_mcp_editor.py`, `test_flow_studio_library_list.py` (lane `mcp`);
  - `test_mcp_test_connection_button.py`, `test_flow_studio_mcp_navigation.py`, `test_flow_studio_library_focus.py` (lane `library`);
  - `test_flow_chiplist_label_resolver.py`, `test_oauth_modal_flow.py` (in `shared`, run by file);
  - `test_studio_mcps_tab.py` (lane `agents`, run by file).
- [ ] **The captures match.** The leg 01 capture run of the MCP surfaces on this tree matches the before set pixel for pixel (`ImageChops` difference with no non-zero bounding box, masked text excepted). Any difference is a defect in the split.
- [ ] **Sizes:** every file under `js/areas/studio/` named `mcp-*.js` is 800 lines or fewer, and MSE's `ALLOWANCE` entry is removed.
  - The review estimated the controller at about 775-785 lines. If it comes out over 800, first move any further nearly self-contained piece that moves verbatim; only then lower the entry to the new count, with a flight-log note.
  - `tests/test_area_module_size.py` passes.
- [ ] **No new sink and no new use:** whole-app `HTML_SINK_ALLOWANCE` totals and per-key ownership totals are unchanged; every moved row has its `MOVES` entry, and leg 01's `MOVES` tests pass.
- [ ] **No sink text changed:** each `DYNAMIC_SINK_BASELINE` snippet appears under its new file key unchanged.
- [ ] **Store and consent pins:** `tests/test_store_static.py` and `tests/test_consent_link_static.py` pass, with each MCP anchor pointing at the module that holds it. The `invalidate('agents')` sum over the MCP files is still 2.
- [ ] **`App.studio.renderMcpSourceEditor`** is still the one entry point `mcp-glue.js` calls, with the same callbacks contract.
- [ ] **No module cycle:** `mcp-oauth-consent.js` never references `connectionStatus` (it re-runs through `rerun`). The only call back into the controller is `App.studio.renderMcpSourceEditor`, read at call time.
- [ ] **The split was measured, not predicted:** the ownership rows (for example `api:App.confirmDelete(` 1 + 1, `api:App.icon(` across files) and the sink counts come from the guards' own output after the move.
- [ ] **The unit tier passes:** `make test-unit`, the static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_ownership.py`, `tests/test_index_asset_cache_busting.py`), and `ruff`.

## Verification Steps
- `wc -l the_one/interfaces/web/static/js/areas/studio/mcp-*.js`.
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_area_module_size.py tests/test_store_static.py tests/test_consent_link_static.py tests/test_index_asset_cache_busting.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -q -x --timeout 120`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp -x`, then `--lane library -x`. Then by file with `-m browser`: `tests/browser/test_flow_chiplist_label_resolver.py`, `tests/browser/test_oauth_modal_flow.py` and `tests/browser/test_studio_mcps_tab.py`. Run at most 3 at a time, and not while the unit suite runs.
- The capture compare: re-run the leg 01 MCP surfaces into `$HOME/.cache/the-one-ui-capture/m31-f5-split`, then compare with the before set (a short PIL script in the FD's or your scratch space, never committed).
- `git grep -n "mcp-server-editor" tests/ scripts/ Makefile docs/ tests/behavior/ the_one/ CLAUDE.md`, with the hits pasted into the flight log. Every `the_one/agents.md` hit (8) and `docs/ui-control-inventory.md` hit (7) names the right module.

## Implementation Guidance
1. **Cut in dependency order:** shared, server info, sandbox, connection fields, env and headers, connection status, OAuth consent, then the controller. After each cut, run the MCP editor file (`test_flow_studio_mcp_editor.py -x`) so a break is found at the cut that made it.
2. **Move code verbatim.** Change only:
   - the references;
   - the explicit parameters a closure extraction needs.
   No renames, no reformatting beyond what the move needs, and no new behaviour (no `destroy`, no guards: those are leg 03's).
   - **Aliases are required** (design review M3). Every cross-module call is made through a local alias at the top of the IIFE with the **original identifier**, for example `var renderToolsListHtml = ...serverInfo.renderToolsListHtml;`, so every pinned anchor and every `DYNAMIC_SINK_BASELINE` snippet keeps its exact text (for example `listEl.innerHTML = renderToolsListHtml(data.tools);`).
   - **An alias reads its target lazily** (inside a function, or at call time) when that target loads later: the controller's `App.studio.renderMcpSourceEditor`, which `wireResetButton` calls after a Reset (:1431). Never cache an `undefined` at IIFE load time.
   - **Namespaces are plain objects.** Each file starts with `window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};`. These are stateless function namespaces, deliberately not `create(ctx)` modules.
   - **`hasOAuthState` lives in `shared`.** The connection-status markup, `syncResetButtonVisibility` and the controller alias it.
   - **Shared state:**
     - `nextRowIdx` moves into `envHeaders.wire`, initialised there from the row count as today. Cancel's row rebuild does not reset it today, and it still does not.
     - The Add-row listener stays a separate listener inside `wire`, outside the table guard, as today.
     - `snapshot`, `dirty` and `recaptureSnapshot` stay in the controller. `checkDirty` is the `onChange` passed to `envHeaders.wire` and `wireChipLists`.
   - **A string-equality check** (recommended): a one-off script in your scratch space, never committed, renders the editor's `html` for create, a stdio edit and an HTTP edit with OAuth state, before and after the split, and diffs them byte for byte. The pixel compare is the backstop.
3. **The OAuth extraction breaks a cycle** (design review H1).
   - **The cycle.** `handleTestConnection` calls `launchConsentPopup` (from the auto-popup branch and from the `noAutoPopup` consent button), and `launchConsentPopup` calls `handleTestConnection(sourceId, container, testBtn, formData, onSuccess, {noAutoPopup: true})` on a successful poll (about :2005).
   - **The fix.** `launchConsentPopup` takes one argument object `{consentUrl, statusEl, sourceId, settle, rerun}`. `rerun` is a closure that `handleTestConnection` builds over its own arguments (`container`, `formData`, `onSuccess`, `testBtn`), so the consent module never names the connection-status module.
   - **The retry button re-invokes `launchConsentPopup`** within its own module.
   - **The source name** is still read from `#mf-name`, as today.
   - **Check every free variable.** A missed one is a `ReferenceError` only on the sign-in path, which the stubbed tests in `test_flow_studio_mcp_editor.py` and `test_mcp_test_connection_button.py` exercise.
   - **Keep `function launchConsentPopup` before `function onOAuthMessage`** in the consent module, and keep the literal `isSafeUrl(consentUrl)`, because `test_consent_link_static.py:48` slices between them.
4. **Update the guards last**, from the measured counts: the per-file rows, their `MOVES` entries, the sink snippets under their new keys, and the line guard.
5. **Retarget the static pins and the doc paths**, run the capture compare, and write the flight log.

## Edge Cases
- **`this` and `arguments`:** none of the moved functions should depend on them. Check anyway when converting closures.
- **Shared mutable state between closures** (for example a variable that both `wireEditorEvents` and `handleTestConnection` write): keep it in the controller and pass an accessor. Never duplicate it into two modules.
- **`window.App.icon` and `App.escapeHtml` calls** move with their functions. They are allowance moves, not new uses.
- **A sink split across two files** (a string built in one module and inserted in another) counts in the file holding the assignment.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`, plus the new `mcp-editor-shared.js`, `mcp-server-info.js`, `mcp-connection-fields.js`, `mcp-sandbox-fields.js`, `mcp-env-headers.js`, `mcp-connection-status.js` and `mcp-oauth-consent.js`.
- `the_one/interfaces/web/static/index.html`.
- `tests/test_store_static.py`, `tests/test_consent_link_static.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`, `tests/test_area_module_size.py`, `tests/_ui_guard_helpers.py`.
- `the_one/agents.md` and `docs/ui-control-inventory.md` (paths only); the flight log.

## Citation Audit
- **MSE function ranges:** from the code survey §1a at `b1e47ae`. Leg 01 does not touch `the_one/`, so they hold at this leg's start.
- `index.html:104` (the MSE tag) and `:117` (`mcp-glue.js`). Verified by grep.
- `tests/test_store_static.py:260, :281, :316-334`; `tests/test_consent_link_static.py:23, :48`; `tests/_ui_guard_helpers.py:263`; `tests/test_area_module_size.py:26`. Verified by grep and read.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes.** Applied in place: the consent cycle broken with `rerun` (H1); the lazy read of `renderMcpSourceEditor` (H2); required aliases with the original identifiers (M3); the two-file store pin and the per-file `invalidate('agents')` rows (M4); the controller-size fallback order (M5); the shared-state notes for `nextRowIdx` and Add-row (M6); the comment-only paths and the widened grep (L); the consent pin's source order and consumer list (L); measuring the split rows (L). Suggestions taken: plain namespaces, `hasOAuthState` in `shared`, the string-equality check. Clarifications only, so there is no second cycle.
