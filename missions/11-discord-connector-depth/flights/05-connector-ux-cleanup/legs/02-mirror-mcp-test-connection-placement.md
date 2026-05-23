# Leg: mirror-mcp-test-connection-placement

**Status**: completed
**Flight**: [Connector UX Cleanup](../flight.md)

## Objective

Fold the connector editor's `// TEST CONNECTION` and `// INVITE` standalone sections INSIDE the `// CONNECTION` section as a footer-row, mirroring the MCP editor's Refresh-connection placement (`mcp-server-editor.js:441-502`). Drop the standalone `<div class="editor-section connector-test-section">` and the `<section class="editor-section connector-invite-section">` wrappers; their content moves into the Connection section as a `<div class="field-row admin-pf-row connector-test-row">` (Test Connection actions row, mirroring MCP's `mcp-test-row`) + the Invite URL block as a sibling. Remove the standalone `// TEST CONNECTION` and `// INVITE` section titles — the parent Connection section owns the section identity. Preserve all data-testids, all click-handler wiring, and the registry-mediated `renderInviteSection` hook semantics. Chrome MCP visual verification confirms the placement matches MCP editor's footer-row shape.

## Context

- F5 L2 is the second leg per the flight's primitives-first then section-shape sequencing. L1 just landed the canonical primitives across `connector-form-discord.js` + `connector-account-editor.js` (Auto-relay → `tool-enable-switch`, Intent inputs → `.checkbox-primary`, etc.). L2 reshapes the Connection section to absorb Test Connection + Invite.
- F5 flight Design Decision "MCP-mirror placement of Test Connection + Invite — fold into Connection section as footer-row" pins the move. The MCP editor's `<div class="field-row admin-pf-row mcp-test-row">` at lines 472-501 is the working reference; the connector editor's new shape mirrors it byte-shape.
- The Discord `renderInviteSection` hook in `connector-form-discord.js:385-411` returns a `<section class="editor-section connector-invite-section">` today. L2 changes the hook to return a wrapper-less row-shape so the Connection-section caller can embed it without a redundant `editor-section` nesting. The registry contract (`inviteEntry.renderInviteSection(account)` returns HTML) is preserved; only the returned HTML shape changes.
- F4 L4 fold-in (`connector-account-pool-warmed` event listener in `discoverable-dropdown.js`) is unaffected — it listens on `document`, not on any test-connection DOM ancestor.
- Touched-surface UX-debt folding (F4 L1 convention): the F4 debrief listed no outstanding UX-debt against `connector-account-editor.js`'s Test Connection section or `connector-form-discord.js`'s Invite section beyond items already in F5 scope. Nothing to fold beyond the leg's own scope.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` exists with:
  - **Connection section** at lines 316-321:
    ```javascript
    var connectionHtml = '';
    connectionHtml += '<div class="editor-section">';
    connectionHtml += '<div class="section-title">Connection</div>';
    connectionHtml += renderConnectionFields(account, types, isCreate);
    connectionHtml += '</div>';
    ```
  - **Test Connection section** at lines 421-437 (edit-mode-only): wraps button + LED + status + details-wrap in `<div class="editor-section connector-test-section">` with its own `<div class="section-title">Test Connection</div>`.
  - **Invite section** at lines 439-452 (edit-mode-only): registry-mediated; calls `inviteEntry.renderInviteSection(account)` which today returns a full `<section class="editor-section">`.
  - **General-tab mount sequence** at lines 518-525: emits `connectionHtml + credentialsHtml + pairingHtml + directiveHtml + attachedAgentsHtml + testConnectionHtml + inviteHtml + dangerZoneHtml`. L2 removes `testConnectionHtml` and `inviteHtml` from this sequence; their content moves inside `connectionHtml`.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:renderInviteSection` (lines 385-411) returns `<section class="editor-section connector-invite-section"><div class="section-title">Invite</div>...</section>`. L2 changes the return to a wrapper-shape `<div class="connector-invite-block" data-testid="connector-invite-section">...</div>` (no section-title; no `editor-section` class).
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:441-502` is the working reference. The structure inside MCP's Connection section after `renderConnectionFields`:
  ```
  <div class="field-row admin-pf-row mcp-test-row">
    <label></label>
    <div class="mcp-connection-actions">
      <button class="btn-outlined-primary mcp-refresh-connection-btn">Refresh connection</button>
      [Reset connection button — OAuth-state-dependent]
      <span class="indicator-led indicator-led--{state} mcp-connection-led"></span>
      <div class="mcp-tools-last-updated">Last updated: ...</div>
    </div>
  </div>
  ```
- The connector editor uses `connector-test-led`, `connector-test-message`, `connector-test-status`, `connector-test-details-wrap`, `connector-test-details` data-testids. All preserved.
- The Discord renderInviteSection uses `connector-invite-section`, `connector-invite-hint`, `connector-invite-url-wrap`, `connector-invite-url`, `connector-invite-copy-btn`, `connector-invite-recompute-btn` data-testids. All preserved.
- The Test Connection click-handler wiring at `connector-account-editor.js:1177-1182` looks up `[data-testid="connector-test-connection-btn"]`. Preserved.
- The Invite event-wiring at `connector-form-discord.js:wireInviteEvents` (find it via grep) looks up the invite-related testids. Preserved.
- Chrome MCP available; `the-one` container at `http://localhost:8484/`.

## Outputs

- `connector-account-editor.js`:
  - **Connection section block** at lines 316-321 expands to host the Test Connection footer-row + Invite block (edit-mode-only):
    ```javascript
    var connectionHtml = '';
    connectionHtml += '<div class="editor-section">';
    connectionHtml += '<div class="section-title">Connection</div>';
    connectionHtml += renderConnectionFields(account, types, isCreate);
    if (!isCreate) {
      connectionHtml += renderTestConnectionRow();  // Test Connection footer-row
      connectionHtml += inviteContent;              // type-registry-mediated invite block
    }
    connectionHtml += '</div>';
    ```
  - **`testConnectionHtml` variable + standalone section block** at lines 421-437 REPLACED with a helper `renderTestConnectionRow()` that returns the row + status + details-wrap as inner content (no outer `editor-section` wrapper, no section-title).
  - **`inviteHtml` variable** at lines 445-452 RENAMED to `inviteContent` and the registry-call result is used directly (the call to `inviteEntry.renderInviteSection(account)` returns wrapper-less content per the L2 change to `connector-form-discord.js:renderInviteSection`).
  - **General-tab mount sequence** at lines 518-525 drops `testConnectionHtml + inviteHtml` from the section emission list. New sequence: `connectionHtml + credentialsHtml + pairingHtml + directiveHtml + attachedAgentsHtml + dangerZoneHtml`. (Test Connection + Invite are now inside connectionHtml.)
  - **Test Connection footer-row markup** mirrors MCP's `mcp-test-row` shape:
    ```html
    <div class="field-row admin-pf-row connector-test-row">
      <label></label>
      <div class="connector-test-actions">
        <button class="btn-outlined-primary connector-test-connection-btn" data-testid="connector-test-connection-btn">
          {refresh-cw icon} Test connection
        </button>
        <span class="indicator-led indicator-led--idle connector-test-led" data-testid="connector-test-led" data-state="idle" aria-label="Not tested"></span>
        <span class="connector-test-message" data-testid="connector-test-message">Not tested</span>
      </div>
    </div>
    <div class="connector-test-status" data-testid="connector-test-status" hidden></div>
    <div class="connector-test-details-wrap" data-testid="connector-test-details-wrap" hidden>
      <div data-testid="connector-test-details"></div>
    </div>
    ```
    Note: the status + details-wrap live OUTSIDE the field-row (siblings to it), matching the existing structure — they're conditionally-shown panels that don't fit in a 2-column field-row.
  - **MCP-parity comment** added near the new `renderTestConnectionRow` helper citing `mcp-server-editor.js:472-501` as the precedent.
- `connector-form-discord.js`:
  - **`renderInviteSection(account)`** at lines 385-411 returns wrapper-less content:
    ```html
    <div class="connector-invite-block" data-testid="connector-invite-section">
      <p class="connector-invite-hint" ...>Run Test Connection first to fetch your application ID.</p>
      <div class="connector-invite-url-wrap" ...>
        <code class="connector-invite-url">...</code>
        <button class="btn-outlined-primary connector-invite-copy-btn">Copy</button>
        <button class="btn-outlined-primary connector-invite-recompute-btn">Recompute</button>
      </div>
    </div>
    ```
    Removed: `<section class="editor-section connector-invite-section">` outer wrapper, `<div class="section-title">Invite</div>` (the parent Connection section now owns the section identity).
    Preserved: `data-testid="connector-invite-section"` moves from `<section>` to `<div class="connector-invite-block">`. All inner data-testids unchanged.
- **CSS**: small addition to `studio.css` for `.connector-test-row`. Cycle-1 review confirmed `.mcp-test-row` is at `studio.css:126` under the `.area-studio` namespace, a single-rule `margin-top: 8px;`. Add `.connector-test-row` to the same selector list: `.area-studio .mcp-test-row, .area-studio .connector-test-row { margin-top: 8px; }`. The related `.connector-test-actions` / `.connector-test-led` / `.connector-test-message` rules already exist at `studio.css:1183-1194` (no change needed).
- No changes to data-testids beyond the documented move of `connector-invite-section` from `<section>` to `<div>`. Optional: ADD `data-testid="connector-connection-section"` to the wrapping `<div class="editor-section">` so future tests can assert "Test Connection lives inside Connection" by DOM ancestry. Cycle-1 reviewer suggestion; small future-proofing win.
- No changes to JS event-wiring (click handlers find buttons by data-testid, which are preserved). The Invite Copy/Recompute wiring lives inside `wireEvents` at `connector-form-discord.js:629-649` (verified by cycle-1 reviewer; not `wireInviteEvents`).
- **Doc-comment updates** (sibling-files in L2 scope):
  - `connector-account-editor.js:5-11` file-header comment lists section layout including `<div class="editor-section">Test Connection</div>` as standalone — UPDATE to reflect Test Connection + Invite folded inside Connection section.
  - `connector-form-registry.js:53-54` and `:108-112` document `renderInviteSection` contract as "section mounted between Test Connection and Danger Zone" — UPDATE to "wrapper-less content embedded inside the Connection section" (or similar).
  - `the_one/agents.md:181-183` (Connector subsystem doc) mentions the Invite section's contract — UPDATE for the wrapper-less embed semantics.
- Sibling artifact bookkeeping: F5 `flight.md`'s L2 Checkpoints + L2 Legs item checked off; F5 `flight-log.md`'s Leg Progress section grows an L2 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `connector-account-editor.js` Connection section at lines 316-321 expands to include Test Connection footer-row + Invite block (edit-mode-only) inside the same `<div class="editor-section">`.
- [x] `connector-account-editor.js` defines a new helper `renderTestConnectionRow()` (or inline-emits the same content) that returns the field-row + status + details-wrap markup without an outer `editor-section` wrapper and without a section-title.
- [x] `connector-account-editor.js` Test Connection footer-row uses class `field-row admin-pf-row connector-test-row` on the wrapping `<div>`, mirroring MCP's `mcp-server-editor.js:473` `field-row admin-pf-row mcp-test-row` pattern.
- [x] `connector-account-editor.js` Test Connection actions-wrap uses class `connector-test-actions` (unchanged from current).
- [x] `connector-account-editor.js` Test Connection button, LED, message, status-wrap, details-wrap, details elements ALL preserve their existing data-testids: `connector-test-connection-btn`, `connector-test-led`, `connector-test-message`, `connector-test-status`, `connector-test-details-wrap`, `connector-test-details`.
- [x] `connector-account-editor.js` General-tab mount sequence at lines 518-525 emits: `connectionHtml + credentialsHtml + pairingHtml + directiveHtml + attachedAgentsHtml + dangerZoneHtml`. The `testConnectionHtml` and `inviteHtml` variables are REMOVED from the sequence (their content is inside connectionHtml).
- [x] `connector-account-editor.js` standalone `var testConnectionHtml = '';` block at lines 422-437 is DELETED (replaced by the `renderTestConnectionRow()` call inside connectionHtml).
- [x] `connector-account-editor.js` standalone `var inviteHtml = '';` block at lines 445-452 is REMOVED; the registry-mediated Invite content is called from inside the connectionHtml block.
- [x] `connector-form-discord.js:renderInviteSection(account)` at lines 385-411 returns wrapper-less content: `<div class="connector-invite-block" data-testid="connector-invite-section">...</div>`. The `<section class="editor-section connector-invite-section">` outer wrapper is removed; the `<div class="section-title">Invite</div>` is removed.
- [x] `connector-form-discord.js:renderInviteSection(account)` preserves ALL inner data-testids: `connector-invite-section` (moves from `<section>` to `<div>`), `connector-invite-hint`, `connector-invite-url-wrap`, `connector-invite-url`, `connector-invite-copy-btn`, `connector-invite-recompute-btn`.
- [x] `connector-form-discord.js:renderInviteSection(account)` preserves the Discord-specific hint text + URL computation + Copy/Recompute button wiring contracts.
- [x] Visual containment: in Chrome MCP, the Connection section reads as a single bordered block containing Name + Type + Bot Token + Test Connection row + Invite URL block (when edit-mode). The Credentials section below is visually distinct (separate `editor-section` border).
- [x] Test Connection click still wires correctly — clicking the Test Connection button triggers the POST to `/api/connector-accounts/{id}/test/connect` and renders the result in the banner/details panels (verify via Chrome MCP click + network panel + visual change in LED/status).
- [x] Invite URL still resolves correctly — after a successful Test Connection, the Invite URL appears in the `connector-invite-url` element (verify via Chrome MCP).
- [x] L4 fold-in `connector-account-pool-warmed` event from F4 still fires after the new layout — Test Connection success still nudges the dropdowns on Access-and-Routing tab (no regression).
- [x] CSS: `.connector-test-row` added to `studio.css:126`'s `.area-studio .mcp-test-row` selector list (resulting rule: `.area-studio .mcp-test-row, .area-studio .connector-test-row { margin-top: 8px; }`). No other CSS changes; no additions to `admin.css` or `components.css`.
- [x] **Doc-comment updates**: `connector-account-editor.js:5-11` file-header reflects the new structure (Test Connection + Invite inside Connection section). `connector-form-registry.js` docstrings (lines ~53-54 and ~108-112) updated to reflect `renderInviteSection` now returns wrapper-less content embedded inside Connection. `the_one/agents.md` Connector subsystem section (~181-183) updated to match.
- [x] No changes to other sections (Credentials, Lifecycle, Pairing, Directive, AttachedAgents, DangerZone) — they remain standalone `editor-section` blocks.
- [x] Browser test suite: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_account_create_and_test.py -m browser -x --timeout 60 -v` passes — no regressions on the editor + test-connection + invite-section flows.
- [x] Source files modified: `connector-account-editor.js`, `connector-form-discord.js`, `studio.css`, `connector-form-registry.js` (docstrings only), `the_one/agents.md` (Connector subsystem section only). No other source files touched.

## Verification Steps

- `grep -n "field-row admin-pf-row connector-test-row" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns exactly 1 hit (the new footer-row wrapper).
- `grep -n "editor-section connector-test-section" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns 0 hits (the standalone Test Connection section wrapper is removed).
- `grep -n "editor-section connector-invite-section" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns 0 hits (the standalone Invite section wrapper is removed).
- `grep -n "connector-invite-block" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns 1 hit (the new wrapper-less div class).
- `grep -n "section-title.*Test Connection\|section-title.*Invite" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns 0 hits (both standalone section-titles removed).
- `grep -n "data-testid=\"connector-test-connection-btn\"\|data-testid=\"connector-invite-section\"" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns at least 2 hits (test-id preserved on both elements, just relocated).
- `grep -n "\.connector-test-row\b\|\.mcp-test-row\b" the_one/interfaces/web/static/css/*.css` returns at least 2 hits across the CSS files — the `.connector-test-row` rule must be present and either share the body of `.mcp-test-row` or be in the same selector list.
- Visual (Chrome MCP):
  - Navigate to `http://localhost:8484/#studio/connectors/{discord-account-id}` General tab; take screenshot; visually confirm Test Connection button + LED + Invite URL all live INSIDE the Connection section (between Connection's fields and the Credentials section boundary).
  - Click Test Connection button; observe LED transitions to `testing` then `ok`/`failed`; status message updates; details panel (if non-ok) expands.
  - Verify Invite URL renders inside the Connection section after a successful Test Connection (not in a separate section block below).
- Browser test suite: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_account_create_and_test.py -m browser -x --timeout 60 -v` shows 100% pass.
- `git diff --stat` shows changes in: `connector-account-editor.js`, `connector-form-discord.js`, `studio.css`, `connector-form-registry.js` (docstrings), `the_one/agents.md` (Connector subsystem doc), + F5 sibling artifacts (`flight.md`, `flight-log.md`, this leg). No other files.

## Implementation Guidance

1. **Read the three target file sections** before editing:
   - `connector-account-editor.js:316-321` — Connection section block.
   - `connector-account-editor.js:421-437` — current Test Connection section.
   - `connector-account-editor.js:439-452` — current Invite section block.
   - `connector-account-editor.js:518-525` — General-tab mount sequence.
   - `connector-form-discord.js:385-411` — current Discord `renderInviteSection`.
   - `mcp-server-editor.js:472-501` — MCP `mcp-test-row` reference.

2. **GREP for `.mcp-test-row` in CSS** to find the existing rule body:
   - `grep -n "\.mcp-test-row\b" the_one/interfaces/web/static/css/*.css`
   - Note the file and line range.

3. **Define the `renderTestConnectionRow()` helper** in `connector-account-editor.js`. Place at FILE-SCOPE inside the IIFE, alongside the existing section-renderer helpers `renderPairingSection` (line 1732), `renderAllowlistSection` (1788), `renderRoutingRulesSection` (2055), `renderAttachedAgentsSection` (2562). Do NOT nest inside `renderConnectorAccountEditor` (would break the established pattern). Return value:
   ```javascript
   function renderTestConnectionRow() {
     var html = '';
     html += '<div class="field-row admin-pf-row connector-test-row">';
     html += '<label></label>';
     html += '<div class="connector-test-actions">';
     html += '<button type="button" class="btn-outlined-primary connector-test-connection-btn" data-testid="connector-test-connection-btn">' +
             window.App.icon('refresh-cw') + ' Test connection</button>';
     html += '<span class="indicator-led indicator-led--idle connector-test-led" data-testid="connector-test-led" data-state="idle" aria-label="Not tested"></span>';
     html += '<span class="connector-test-message" data-testid="connector-test-message">Not tested</span>';
     html += '</div>';
     html += '</div>';
     html += '<div class="connector-test-status" data-testid="connector-test-status" hidden></div>';
     html += '<div class="connector-test-details-wrap" data-testid="connector-test-details-wrap" hidden>' +
             '<div data-testid="connector-test-details"></div>' +
             '</div>';
     return html;
   }
   ```
   Add a comment block citing `mcp-server-editor.js:472-501` as the MCP-parity precedent.

4. **Modify the Connection section block** at `connector-account-editor.js:316-321`:
   ```javascript
   var connectionHtml = '';
   connectionHtml += '<div class="editor-section">';
   connectionHtml += '<div class="section-title">Connection</div>';
   connectionHtml += renderConnectionFields(account, types, isCreate);
   if (!isCreate) {
     connectionHtml += renderTestConnectionRow();
     // Invite block — registry-mediated (Discord today). Returns
     // wrapper-less content per L2's renderInviteSection contract change.
     var inviteRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
     var inviteEntry = (inviteRegistry && account && account.type) ? inviteRegistry.get(account.type) : undefined;
     if (inviteEntry && typeof inviteEntry.renderInviteSection === 'function') {
       connectionHtml += inviteEntry.renderInviteSection(account);
     }
   }
   connectionHtml += '</div>';
   ```

5. **DELETE the standalone Test Connection block** at `connector-account-editor.js:421-437`:
   - Remove the entire `// Test Connection section (edit mode only).` comment and the `var testConnectionHtml = '';` + the conditional emission.
   - Replace with a one-line comment: `// Test Connection content lives INSIDE the Connection section above (L2 MCP-parity refactor).`

6. **DELETE the standalone Invite block** at `connector-account-editor.js:439-452`:
   - Remove the entire `// Invite section (edit mode only) — M11 F1 L5.` comment and the `var inviteHtml = '';` + the registry-mediated emission.
   - Replace with a one-line comment: `// Invite content lives INSIDE the Connection section above (L2 MCP-parity refactor); the registry hook is called from there.`

7. **Update the General-tab mount sequence** at `connector-account-editor.js:518-525`:
   - Current: `html += connectionHtml; html += credentialsHtml; ...; html += testConnectionHtml; html += inviteHtml; html += dangerZoneHtml;`
   - New: `html += connectionHtml; html += credentialsHtml; ...; html += dangerZoneHtml;` (drop the testConnectionHtml + inviteHtml lines).
   - Add a comment near the dropped lines: `// L2: testConnectionHtml + inviteHtml folded into connectionHtml above to mirror MCP editor's mcp-test-row placement.`

8. **Modify `connector-form-discord.js:renderInviteSection`** at lines 385-411 to return wrapper-less content:
   ```javascript
   function renderInviteSection(account) {
     var accountId = (account && account.id) || '';
     var appId = _lastApplicationIdByAccount[accountId];
     var hintHidden = appId ? ' hidden' : '';
     var urlHidden = appId ? '' : ' hidden';
     var url = appId ? _computeInviteUrl(appId) : '';

     var html = '';
     // L2: returns wrapper-less content; the caller (connector-account-editor.js)
     // embeds this inside the Connection section per MCP-parity placement.
     html += '<div class="connector-invite-block" data-testid="connector-invite-section">';
     html += '<p class="connector-invite-hint" ' +
             'data-testid="connector-invite-hint"' + hintHidden + '>' +
             'Run Test Connection first to fetch your application ID.' +
             '</p>';
     html += '<div class="connector-invite-url-wrap" ' +
             'data-testid="connector-invite-url-wrap"' + urlHidden + '>';
     html += '<code class="connector-invite-url" ' +
             'data-testid="connector-invite-url">' + _escapeHtml(url) + '</code>';
     html += '<button type="button" class="btn-outlined-primary connector-invite-copy-btn" ' +
             'data-testid="connector-invite-copy-btn">Copy</button>';
     html += '<button type="button" class="btn-outlined-primary connector-invite-recompute-btn" ' +
             'data-testid="connector-invite-recompute-btn">Recompute</button>';
     html += '</div>';
     html += '</div>';
     return html;
   }
   ```
   - The Discord-specific function name `renderInviteSection` stays (registry contract).
   - The `<section class="editor-section connector-invite-section">` outer wrapper becomes `<div class="connector-invite-block" data-testid="connector-invite-section">`.
   - The `<div class="section-title">Invite</div>` is REMOVED.
   - `data-testid="connector-invite-section"` moves from the `<section>` to the `<div>`.

9. **Add the `.connector-test-row` CSS rule** at `studio.css:126`:
   - Current rule (verified cycle-1): `.area-studio .mcp-test-row { margin-top: 8px; }`.
   - Change to: `.area-studio .mcp-test-row, .area-studio .connector-test-row { margin-top: 8px; }`.
   - Optionally add a one-line comment on the rule: `/* L2 MCP-parity: connector editor's Test Connection footer-row shares MCP's mcp-test-row margin. */`.

9a. **Update `connector-account-editor.js:5-11` file-header doc-comment**:
   - The existing comment lists `<div class="editor-section">Test Connection</div> (edit-mode only — probe + banner)` as a standalone section. UPDATE to reflect: Test Connection content (button + LED + message + status + details-wrap) lives INSIDE the Connection section as a footer-row (per L2 MCP-parity refactor); the Invite block (Discord today, registry-mediated) is mounted in the same section.

9b. **Update `connector-form-registry.js` docstrings** at approximately lines 53-54 and 108-112 (verify with grep `grep -n "renderInviteSection\|Invite section" the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js`):
   - The docstrings currently describe `renderInviteSection` as "section mounted between Test Connection and Danger Zone" or similar. UPDATE to: "returns wrapper-less HTML content embedded inside the Connection section (post-L2 MCP-parity refactor); the registry contract is unchanged — the hook still returns an HTML string."

9c. **Update `the_one/agents.md` Connector subsystem doc** at approximately lines 181-183 (verify with grep `grep -n "renderInviteSection\|Invite section" the_one/agents.md`):
   - If the doc mentions the Invite section's contract or placement, UPDATE to reflect the new wrapper-less embed semantics. Keep the substance of the contract description; just update the wrapper-shape language.

10. **Run Chrome MCP verification**:
    - Navigate to `http://localhost:8484/#studio/connectors/{discord-account-id}` (Discord Constellation at `58f1fe5a833f`).
    - Take screenshot; visually confirm the Connection section now contains Test Connection + Invite as nested content.
    - Click Test Connection button; verify the click handler still fires (LED transitions, status message updates, network panel shows the POST).
    - Verify Invite URL renders inside the Connection section after a successful test.

11. **Run targeted browser tests**:
    - `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_account_create_and_test.py -m browser -x --timeout 60 -v`

12. **Update F5 `flight.md`** — check off L2 in Checkpoints + Legs sections.

13. **Append L2 leg-progress entry** to F5 `flight-log.md`.

14. **Update this leg artifact's Status header** progressively: `planning` → `ready` → `in-flight` → `landed`.

## Edge Cases

- **Tests asserting `<section class="editor-section connector-invite-section">` or `<div class="editor-section connector-test-section">`**: grep `grep -rn "connector-invite-section\|connector-test-section" tests/browser/` before editing. Tests using `data-testid="connector-invite-section"` are immune (the testid moves to the `<div>`). Tests asserting the surrounding `editor-section` class would need updating — that's expected and part of this leg's scope.
- **The Invite section's `<p class="connector-invite-hint">` text "Run Test Connection first to fetch your application ID."**: unchanged in L2. L3 may revise the copy for human-friendliness; L2 preserves the existing text byte-identical.
- **Test Connection click handler wiring**: at `connector-account-editor.js:1177-1182` the handler does `container.querySelector('[data-testid="connector-test-connection-btn"]')`. Since the testid is preserved, the handler resolves the button regardless of its DOM position. No JS wiring change needed.
- **Invite Copy/Recompute click wiring**: at `connector-form-discord.js:wireInviteEvents` (or similar — grep for `wireInviteEvents` or `connector-invite-copy-btn` event registration) uses data-testid lookups. Preserved.
- **Application-ID cache contract**: `renderTestConnectionBanner` at `connector-account-editor.js:1598-1602` pushes the application_id into Discord's `setApplicationId` cache. The cache push runs from a different code path (Test Connection's POST response callback), not from the renderInviteSection. So the Invite section's dependence on `_lastApplicationIdByAccount` is unaffected by L2.
- **`renderInviteSection` registry contract**: today only Discord implements the hook. The contract change ("returns wrapper-less content") affects future connector types. Document the new contract in the L5 sweep coverage report so future plugin authors know the shape.
- **`.connector-test-row` CSS rule placement**: if `.mcp-test-row` is in `studio.css`, add `.connector-test-row` there. If it's in `admin.css`, add it there. Single source of truth for the rule body.
- **Visual rhythm after the fold**: the Connection section grows in height (now contains Test Connection row + Invite block). If this looks too dense, L5 sweep may surface a recommendation for spacing — but L2 doesn't preempt; it just moves the content.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — Connection section expanded to host Test Connection row + Invite block (edit-mode-only); new `renderTestConnectionRow()` helper at file-scope inside IIFE; standalone Test Connection + Invite section blocks deleted; General-tab mount sequence drops `testConnectionHtml + inviteHtml`; file-header doc-comment at lines 5-11 updated.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — `renderInviteSection` rewritten to return wrapper-less content (`<div class="connector-invite-block">` + `data-testid="connector-invite-section"`); section-title removed; inner content preserved byte-identical.
- `the_one/interfaces/web/static/css/studio.css` — `.connector-test-row` added to existing `.area-studio .mcp-test-row` selector list at line 126; ~1 LOC change.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — docstring updates only (~2 sites; ~5-10 LOC of comments); registry contract code unchanged.
- `the_one/agents.md` — Connector subsystem doc updates only (~3 LOC of prose) reflecting the new `renderInviteSection` wrapper-less semantics.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight.md` — L2 checkpoint + L2 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight-log.md` — L2 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/legs/02-mirror-mcp-test-connection-placement.md` — this artifact's status header updated through the lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; Chrome MCP visual verification confirms placement matches MCP editor; click + invite-URL flows still work; browser tests pass)
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_account_create_and_test.py -m browser -x --timeout 60` passes
- [x] Update `flight-log.md` with L2 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L2 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F5 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23, post-L1):

- `connector-account-editor.js:316-321` — Connection section block confirmed.
- `connector-account-editor.js:421-437` — Test Connection standalone section confirmed.
- `connector-account-editor.js:439-452` — Invite registry-mediated block confirmed.
- `connector-account-editor.js:518-525` — General-tab mount sequence confirmed (line range repaired from initial 512-522 at cycle-1).
- `connector-account-editor.js:1177-1182` — Test Connection click handler wiring confirmed (line range repaired from initial 1179-1184 at cycle-1).
- `connector-account-editor.js:1598-1602` — application_id cache push confirmed (line range repaired from initial 1602-1604 at cycle-1).
- `connector-account-editor.js:5-11` — file-header doc-comment confirmed (lists Test Connection as standalone section; L2 updates).
- `connector-form-discord.js:385-411` — `renderInviteSection` body confirmed (`<section class="editor-section connector-invite-section">` wrapper at line 393, `<div class="section-title">Invite</div>` at line 395).
- `connector-form-discord.js:629-649` — `wireEvents` Invite Copy/Recompute wiring confirmed (cycle-1 reviewer surfaced; the wiring function is `wireEvents`, not `wireInviteEvents`).
- `connector-form-registry.js:53-54, 108-112` — `renderInviteSection` contract docstrings confirmed; L2 updates wrapper-shape language.
- `the_one/agents.md:181-183` — Connector subsystem section confirmed mentioning the Invite section's contract; L2 updates wrapper-shape language.
- `mcp-server-editor.js:472-501` — `mcp-test-row` reference confirmed (the canonical MCP-parity precedent).
- `studio.css:126` — `.area-studio .mcp-test-row { margin-top: 8px; }` rule confirmed (single-rule, simple add `.connector-test-row` to selector list).
- `studio.css:1183-1194` — `.connector-test-actions` / `.connector-test-led` / `.connector-test-message` rules confirmed (no change needed).

13 citation sites verified clean. 3 line-drift repairs applied at cycle-1 (mount sequence; click handler; cache push). 4 new sites added at cycle-1 (file-header; wireEvents; registry docstrings; agents.md doc; studio.css mcp-test-row anchor).
