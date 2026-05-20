# Leg: studio-connectors-attach-tab

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

## Objective

Add a new "Connectors" tab to the Studio Agent Editor that mirrors the existing MCPs tab pattern: attach/detach toggles for each connector account (writing `AgentConfig.connector_account_ids`) plus a per-attached-account ACL editor for `connector_acls` (peers + channels lists with add/remove). Empty per-account ACL labeled inline as "no restrictions — inherits account-scope." Tab id `'connectors'` is added to the four-tab whitelist at `studio.js:161` (extending to five tabs) and to `PANEL_IDS` in `agent-editor.js:45-50`. New module `studio/connectors-tab.js` mirrors `mcps-tab.js` shape. The `collectFormData` walk in `studio.js` is extended with `connector_account_ids` (from toggle selectors) + `connector_acls` (from per-attached-account peer/channel list editors). The deep-link `#studio/agents/{name}/connectors` lands at this tab.

## Context

- **Flight Design Decision — "Intra-Studio edit-surface split"**: account-scope on Connectors detail page (leg 4); per-agent ACL on Agent Editor Connectors tab (this leg). The two together render the full picture for a multi-agent account.
- **Empty-ACL labeling** (flight Design Decision): "no restrictions — inherits account-scope" when a per-account ACL is absent OR has empty `{peers: [], channels: []}` inner. The UI must visually distinguish "no entry for this account" (inherit) from "entry with empty lists" (also inherit per leg-1c) from "entry with non-empty lists" (narrowing). Per leg-1c, both empty and absent mean the same semantic; the UI should treat them identically.
- **MCPs tab as the canonical UI precedent**: `mcps-tab.js:34 renderMcpsTab(panel, agent, allSources, callbacks)` is the structural mirror. Each connector account renders as a row with an attach toggle on the summary line + a collapsible details panel containing the per-account ACL editor (when attached).
- **Tab routing**: `studio.js:161` `if (tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'tools')` is the four-tab whitelist. Leg 5 extends it to include `'connectors'`. Hash route `#studio/agents/{name}/connectors` is the deep-link target leg 4 already emits.
- **`agent-editor.js:45-50` `PANEL_IDS`**: add `connectors: 'agent-tab-panel-connectors'`. The tablist HTML at L91-107 adds a Connectors button; the tabpanels at L111-119 add the matching panel div; the mount loop at L140-167 fetches the panel and calls `renderConnectorsTab`.
- **`collectFormData` extension** at `studio.js:1801+`: walk new selectors `[data-connector-account-toggle][data-connector-account-id]:checked` → `connector_account_ids`; `[data-connector-acl-peer][data-connector-acl-account]` + `[data-connector-acl-channel][data-connector-acl-account]` → `connector_acls`. Mirror the leg-1b/1c empty-preservation invariant on the API edge: omit `connector_acls[account_id]` when both inner lists are empty AND the operator's intent is "inherit" (don't pin a useless entry); ONLY include `connector_acls[account_id]` when the operator added at least one peer or channel. The leg-1c validator accepts both shapes; this choice keeps the serialized state tidy.
- **AgentConfig payload shape from `/api/agents/{name}`**: the existing GET endpoint already returns `connector_account_ids` (since F4 L5) and `connector_acls` (since leg 1c — same trip through `model_dump` adds it automatically). No new endpoint needed; verify the existing GET round-trips both fields.
- **PUT round-trip for `connector_acls`**: existing PUT handler at `api.py:537` does `cfg = AgentConfig.model_validate(data)` which fires leg-1c's validator. Round-trip works automatically. The save flow at `studio.js:1781` `data = collectFormData()` packages the fields; the PUT call follows.
- **All connector accounts** are fetched once on editor mount (mirror of `callbacks.allMcpSources` pattern). The fetch is from `GET /api/connector-accounts` — already exists from F2.
- **No new endpoint or backend changes**: leg 5 is JS-only on the agent-side. The backend round-trip path is already complete via leg 1c.
- **Pre-existing `connector_account_ids` UI** (F4 L5 may have shipped one): verify with `grep -rn "connector_account_ids\|connector-account-toggle" the_one/interfaces/web/static/js/`. If F4 shipped a chip-area or similar on the General tab, leg 5 MIGRATES that surface into the new Connectors tab (preserving the data field; just moving the UI). Otherwise leg 5 introduces the surface fresh.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js:45-182` — `PANEL_IDS` + tablist HTML + mount loop
- `the_one/interfaces/web/static/js/areas/studio.js:161,1801-1969` — tab whitelist + collectFormData
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` — the canonical sibling tab pattern
- `the_one/interfaces/web/api.py:537` — PUT handler model_validate site
- `the_one/agent/config.py:connector_account_ids,connector_acls` — leg-1c data fields
- Leg-4's GET `/api/connector-accounts` — existing endpoint for the all-accounts fetch

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — NEW module `App.studio.renderConnectorsTab(panel, agent, allConnectorAccounts, callbacks)` mirroring `renderMcpsTab` shape: attach toggle per account + per-attached-account ACL editor (peers + channels lists with add/remove)
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — extend `PANEL_IDS` with `connectors`; add the Connectors tab button to the tablist HTML; add the matching panel div; add a fetch + mount call for `renderConnectorsTab` in the mount loop
- `the_one/interfaces/web/static/js/areas/studio.js` — extend the four-tab whitelist at L161 to include `'connectors'`; extend `collectFormData` at L1801+ with `connector_account_ids` + `connector_acls` walks; ensure `allConnectorAccounts` is fetched once and passed through `callbacks` to the editor
- The flight log gains a leg-5 entry

## Acceptance Criteria

- [ ] New tab "Connectors" rendered in the Agent Editor between MCPs and Built-in Tools (or wherever the existing MCPs-tab adjacency makes most sense)
- [ ] Tab id `'connectors'` whitelisted at `studio.js:161`; the deep-link `#studio/agents/{name}/connectors` activates this tab
- [ ] `PANEL_IDS.connectors = 'agent-tab-panel-connectors'` exists
- [ ] `renderConnectorsTab(panel, agent, allConnectorAccounts, callbacks)` exists at `App.studio` and is called from `agent-editor.js`'s mount loop
- [ ] Each connector account renders as a row with: name + type label, attach toggle (`[data-connector-account-toggle][data-connector-account-id]`), collapsible details
- [ ] When attached, the details panel shows per-account ACL editor: peers list + channels list, each with add/remove buttons; existing entries from `agent.connector_acls[account_id]` are pre-populated
- [ ] When attached with empty ACL OR no ACL entry, the details panel shows an inline label "no restrictions — inherits account-scope" alongside the (currently empty) list editors. Adding an entry converts to narrowing.
- [ ] `collectFormData` walks the new selectors:
  - `connector_account_ids` from `[data-connector-account-toggle]:checked` → `data.connector_account_ids = [...]`
  - `connector_acls` from per-account peer/channel inputs → `data.connector_acls = {account_id: {peers, channels}, ...}` — OMIT an account_id entry if both lists are empty (the inherit semantic; leg-1c accepts absent = empty = same)
- [ ] PUT round-trip works end-to-end: save → GET reload reflects the saved `connector_account_ids` + `connector_acls`
- [ ] F1-F5 + leg-1a/1b/1c/2/3/4 regression byte-identical (no behavioral changes outside the new tab)
- [ ] Existing F4 chip-area UI for `connector_account_ids` (if it exists on the General tab) is migrated or removed — leg 5 owns the surface for connector attachment. The data field round-trip is preserved.
- [ ] `ruff check` clean on the api.py (no changes expected); JS additions follow `mcps-tab.js` style

## Verification Steps

- `grep -n "data-connector-account-toggle\|connectors-tab" the_one/interfaces/web/static/js/areas/studio/ -r` — confirm the new module and selectors exist
- `docker exec the-one pytest -x --timeout 30` — full suite passes (leg 5 changes are JS-only; backend tests are regression)
- Manual smoke (HAT): operator attaches a connector account to an agent, edits the ACL, saves, reloads, verifies state survives

## Implementation Guidance

1. **Verify existing `connector_account_ids` UI on the General tab**: `grep -rn "connector_account_ids\|connector-account-toggle\|connectorAccountId" the_one/interfaces/web/static/js/areas/studio/`. If F4 L5 shipped a chip-area or similar on the General tab, MIGRATE it into the new Connectors tab. If F4 L5 only persisted the field without UI, introduce the UI fresh.

2. **Create `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js`** — mirror `mcps-tab.js` structure. Skeleton:

   ```js
   // App.studio.renderConnectorsTab — agent-editor Connectors tab (M10 F6 L5).
   //
   // Mirrors mcps-tab.js: attach toggle per account + collapsible details
   // panel with the per-account ACL editor (peers + channels lists). Empty
   // ACL labeled "no restrictions — inherits account-scope".
   //
   // Save-flow selectors (collected by studio.js::collectFormData):
   //   [data-connector-account-toggle][data-connector-account-id]:checked
   //     → connector_account_ids
   //   [data-connector-acl-peer][data-connector-acl-account]
   //     → connector_acls[id].peers
   //   [data-connector-acl-channel][data-connector-acl-account]
   //     → connector_acls[id].channels
   (function () {
     'use strict';
     window.App = window.App || {};
     window.App.studio = window.App.studio || {};

     function renderConnectorsTab(panel, agent, allAccounts, callbacks) {
       // ... empty state + per-account row rendering + ACL editor wiring ...
     }

     window.App.studio.renderConnectorsTab = renderConnectorsTab;
   })();
   ```

   Refer to `mcps-tab.js` for: the chip-list-editor wrapper pattern, attach-toggle handling, collapsible-details summary line, change-event propagation via `callbacks.onChange`.

3. **Modify `agent-editor.js`**:
   - L45-50 `PANEL_IDS`: add `connectors: 'agent-tab-panel-connectors'`
   - L91-107 tablist HTML: insert a Connectors button between MCPs and Built-in Tools (or wherever the placement is most logical given tab order):
     ```html
     <button type="button" role="tab" class="tab" id="agent-tab-connectors"
       aria-controls="' + PANEL_IDS.connectors + '" data-tab-id="connectors"
       data-testid="tab-connectors" aria-selected="false" tabindex="-1">Connectors</button>
     ```
   - L111-119 tabpanels: add `<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.connectors + '" data-tab-id="connectors" aria-labelledby="agent-tab-connectors" hidden></div>`
   - L140-167 mount loop: fetch the panel + call `renderConnectorsTab(connectorsPanel, agent, callbacks.allConnectorAccounts, { onChange: callbacks.onChange })`

4. **Modify `studio.js`**:
   - L161: extend the whitelist `if (tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'connectors' || tab === 'tools')`
   - Ensure `allConnectorAccounts` is fetched once when the editor mounts (mirror of `allMcpSources`) and passed through `callbacks` to `renderAgentEditor`. The existing fetch pattern for `allMcpSources` is the precedent — grep for it and replicate.
   - L1801+ `collectFormData`: append after the MCPs walk:
     ```js
     // F6 L5: connector_account_ids from toggle selector.
     var connectorToggles = editorEl.querySelectorAll('[data-connector-account-toggle][data-connector-account-id]');
     data.connector_account_ids = [];
     for (var ci = 0; ci < connectorToggles.length; ci++) {
       if (connectorToggles[ci].checked) {
         data.connector_account_ids.push(connectorToggles[ci].dataset.connectorAccountId);
       }
     }
     // F6 L5: connector_acls from per-account peer/channel inputs.
     var aclAccounts = {};
     var peerInputs = editorEl.querySelectorAll('[data-connector-acl-peer][data-connector-acl-account]');
     for (var pi = 0; pi < peerInputs.length; pi++) {
       var pe = peerInputs[pi];
       var aid = pe.dataset.connectorAclAccount;
       var val = (pe.value || '').trim();
       if (!val) continue;
       if (!aclAccounts[aid]) aclAccounts[aid] = { peers: [], channels: [] };
       aclAccounts[aid].peers.push(val);
     }
     var channelInputs = editorEl.querySelectorAll('[data-connector-acl-channel][data-connector-acl-account]');
     for (var chi = 0; chi < channelInputs.length; chi++) {
       var ce = channelInputs[chi];
       var aidc = ce.dataset.connectorAclAccount;
       var valc = (ce.value || '').trim();
       if (!valc) continue;
       if (!aclAccounts[aidc]) aclAccounts[aidc] = { peers: [], channels: [] };
       aclAccounts[aidc].channels.push(valc);
     }
     // Omit accounts with both lists empty (inherit semantic; leg 1c accepts
     // absent = empty as identical).
     var finalAcls = {};
     for (var aid2 in aclAccounts) {
       var entry = aclAccounts[aid2];
       if (entry.peers.length > 0 || entry.channels.length > 0) {
         finalAcls[aid2] = entry;
       }
     }
     data.connector_acls = Object.keys(finalAcls).length > 0 ? finalAcls : null;
     ```
   - Migrate or remove the F4 chip-area code for `connector_account_ids` on the General tab (if it exists). The field is now collected via the Connectors tab toggles.

5. **Run verification budget**:
   1. `pytest tests/test_db_api.py` — agent API tests pass (existing PUT round-trip with `connector_acls` should already work post-leg-1c; confirm)
   2. `pytest tests/test_db_repositories.py tests/test_db_migration.py` — leg 1c regression
   3. `pytest tests/test_connector_send_tool.py tests/test_connectors_inbound.py tests/test_connectors_resolver.py` — leg 1a/2/3 regression
   4. `pytest tests/test_connectors.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — F1/F3/F4/F5
   5. `pytest` — full suite
   6. `node --check` on new + modified JS files; `ruff check the_one/interfaces/web/api.py` (no changes expected)

6. **Update flight log** with leg-5 entry: new tab id, new module, collectFormData extension, F4-General-tab-chip-area migration outcome (if any), test counts.

7. **Set leg status `landed`**. Do NOT modify flight.md. Do NOT commit.

## Edge Cases

- **Attach toggle while ACL is populated**: detaching an account does NOT clear its ACL entry (the data persists; if re-attached, the prior ACL re-applies). UX nuance: the operator may want a "clear ACL on detach" affordance — out of scope for leg 5; mention in flight log as F10 polish.
- **An account in `connector_account_ids` that no longer exists in `allConnectorAccounts`** (operator deleted the account): defensive — render a row with a "(missing — account deleted)" badge. The save flow leaves the stale id in the list unless the operator explicitly unchecks; or the save flow can prune. **Decision**: leave the stale id; operator must explicitly unchecked. Mirrors the existing MCP-source-deletion behavior.
- **Empty peers AND empty channels on save**: omitted from the serialized payload (inherit semantic). Leg-1c validator accepts both absent and empty-lists; this choice favors tidier persisted state.
- **Whitespace-only peer/channel entries**: trimmed; empty after trim means dropped. Documented.
- **Per-account ACL with whitespace inside an entry**: persisted verbatim (the platform IDs in Discord/Slack can have specific formats; leg 5 does NOT validate — the leg-1c validator accepts any non-empty string).
- **Tab routing back from leg-4's deep-link**: the leg-4 deep-link `#studio/agents/{name}` doesn't include `/connectors`; the URL was reserved for leg-5's tab routing. After leg 5, the link target should activate the Connectors tab.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — NEW (~250 lines mirroring `mcps-tab.js`)
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — extend PANEL_IDS, tablist, tabpanels, mount loop (~15 lines)
- `the_one/interfaces/web/static/js/areas/studio.js` — extend tab whitelist (1 line), collectFormData (~40 lines), allConnectorAccounts fetch (~10 lines if not already present)
- `the_one/interfaces/web/api.py` — UNCHANGED
- `tests/*` — UNCHANGED (no JS unit tests; HAT validates)
- The flight log gains a leg-5 entry

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (regression net byte-identical)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT modify flight.md
- [ ] Do NOT commit (deferred-batched workflow)
