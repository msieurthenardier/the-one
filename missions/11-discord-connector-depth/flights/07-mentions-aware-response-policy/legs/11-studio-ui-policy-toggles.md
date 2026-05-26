# Leg: studio-ui-policy-toggles

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Ship the Studio UI for L5's `account.config["always_listen"]` and L6's `agent_config.connector_always_listen[account_id]` storage fields: an "Always Listen" toggle in the connector-account editor's Session section (account-level capability switch) + a per-account "Always Listen on this connector account" toggle inside each agent-Connectors-tab tile, with disabled-state composition when the account toggle is OFF. A new CustomEvent (`connector-account-always-listen-changed`) syncs the two surfaces; the n=3 trigger for the studio-event-bus lift is documented inline with a TODO citing F4 R13 (lift deferred to routine-maintenance).

## Context

- **Flight DD §3 + L5/L6** — the toggles control the inference path's account-level + per-agent capability switches per the policy gate (L8). After L11, the operator has checkbox UI for both layers; before L11 they could only hand-edit raw JSON.
- **Field-row-3-column pattern (n=2 → n=3)** — Session section's existing rows (Chat-session window, Idle timeout) use the `field-row admin-pf-row` 3-column structure with `<label> | <button class="field-info-icon"> | <content>`. The account "Always Listen" toggle adds a third site at n=3. The primitive-lift is deferred to the future UX maturity mission per F5 R12.
- **CustomEvent n=3 trigger** — Studio currently dispatches two CustomEvents (`connector-account-pool-warmed` at F4, `connector-account-discoverable-refresh-requested` at F5). L11 adds the third (`connector-account-always-listen-changed`); this trips the studio-event-bus lift threshold per F4 R13. **Defer the bus lift to routine-maintenance** (per F7 recon and F4-debrief discipline); L11 ships the third inline string with an explicit TODO comment naming the lift candidate.
- **Disabled-state composition** — when `account.config["always_listen"]` is False, every per-agent toggle in agent-Connectors tiles attached to that account is greyed-out (`disabled` HTML attribute) + visually muted (CSS `:disabled` rule). When the operator toggles the account-level switch in the editor, the CustomEvent fires; the agent's open Connectors tab listens and updates the disabled state without page reload. If the agent editor is NOT open at the time, the next time the operator opens it the per-agent toggles reflect the current account state.
- **Backend storage already exists** — L5 ships the validator + DB write; L6 ships the agent-side field. L11 only adds the UI binding (`data-field="always_listen"` on the account toggle; per-account-keyed `data-field="connector_always_listen[<account_id>]"` or similar on the per-agent toggles). The save path serializes through existing form-collection code.
- **L11 form-collection update** — L5 removed the four JS sites that wrote `auto_relay_platform_replies`; L11 adds new code paths to write `always_listen` from the account toggle, and `connector_always_listen` (per-account) from the agent's toggle. The data-field attribute scheme mirrors how `connector_acls` is collected today.
- **Pre-L10/L11 hand-edit path** — operators could hand-edit `always_listen` via the existing raw-JSON connector-account editor surface (kv-config). After L11, the proper checkbox UI is the path of least friction; the raw-JSON path remains a fallback.

## Inputs

- L1-L10 landed uncommitted.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:398-455` — Session section with the two existing field-row-3-column rows (Chat-session window, Idle timeout). New row inserts before the closing `</div>` at ~line 455.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:1656-1658, 3181-3185` — two existing CustomEvent dispatches (F4 + F5 precedent shape).
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:196-299` — agent-editor Connectors tab's per-account tile structure. New per-account toggle inserts inside `detailsBody` (around line 254+) BEFORE the first axis row.
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js:594-599` — disabled-state composition precedent (HTML `disabled` attribute + CSS `:disabled` rule).
- L5 storage layer: `account.config["always_listen"]: bool` (default False). Backend validator at `the_one/db/models.py` accepts True/False.
- L6 storage layer: `agent_config.connector_always_listen: dict[str, bool] | None` (default None). API + repository round-trip already shipped.
- `tests/browser/test_flow_studio_connector_account_navigation.py:1-142` — Playwright browser-test precedent.
- F4 R13 — studio-event-bus lift candidate (deferred to routine-maintenance).
- F5 R12 — field-row-3-column primitive codification (deferred to future UX maturity mission).

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`:
  - **ADD** the account-level "Always Listen" toggle row in the Session section before the closing `</div>` at ~line 455. Use the field-row-3-column pattern:
    ```javascript
    // M11 F7 L11: Always Listen toggle (account-level capability switch).
    // When ON, the F7 policy gate runs inference on non-mentioned channel
    // messages and may engage the bot. When OFF, only mentions / DMs /
    // /talk_to overrides engage. Per-agent toggles in the agent's
    // Connectors tab gate which attached agents participate when this
    // master is ON (greyed-out when this is OFF).
    var alwaysListenConfigValue = (!isCreate && account.config && Object.prototype.hasOwnProperty.call(account.config, 'always_listen'))
        ? !!account.config.always_listen
        : false;
    var alwaysListenTipText = "When on, the bot listens to all channel messages on " +
            "this account and uses a lightweight inference call to decide whether " +
            "to respond. Per-attached-agent toggles control which agents participate. " +
            "When off, only @mentions, DMs, and /talk_to overrides engage the bot.";
    lifecycleHtml += '<div class="field-row admin-pf-row cf-always-listen-row">';
    lifecycleHtml += '<label for="cf-always-listen">Always Listen</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(alwaysListenTipText) + '" ' +
            'aria-describedby="connector-account-always-listen-help-text" ' +
            'data-testid="connector-account-always-listen-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-account-always-listen-help-text" class="visually-hidden">' +
            escHtml(alwaysListenTipText) + '</span>';
    lifecycleHtml += '<label class="tool-enable-switch">';
    lifecycleHtml += '<input type="checkbox" class="field-input" id="cf-always-listen" ' +
            'data-field="always_listen" ' +
            'data-testid="connector-account-always-listen-toggle"' +
            ' aria-label="Always Listen"' +
            (alwaysListenConfigValue ? ' checked' : '') + ' />';
    lifecycleHtml += '<span class="tool-enable-switch-slider"></span>';
    lifecycleHtml += '</label>';
    lifecycleHtml += '</div>';
    ```
  - **ADD** an event listener registration on the toggle (after the form is rendered + bound). When the toggle's `change` event fires, dispatch the `connector-account-always-listen-changed` CustomEvent:
    ```javascript
    // M11 F7 L11: dispatch always-listen changes for the agent's Connectors
    // tab to grey-out per-agent toggles. Third inline-CustomEvent string in
    // Studio (n=3 — see TODO below citing F4 R13 lift candidate).
    //
    // TODO(routine-maintenance): with n=3 reached
    // (connector-account-pool-warmed + connector-account-discoverable-
    // refresh-requested + this one), F4 R13 calls for lifting the inline
    // CustomEvent strings into a shared studio-event-bus module. Defer
    // per F7 recon discipline (the bus lift expands the leg surface
    // beyond the policy-gate scope).
    var alwaysListenEl = container.querySelector('[data-field="always_listen"]');
    if (alwaysListenEl) {
        alwaysListenEl.addEventListener('change', function () {
            document.dispatchEvent(new CustomEvent('connector-account-always-listen-changed', {
                detail: { accountId: account.id, enabled: !!alwaysListenEl.checked },
            }));
        });
    }
    ```
  - **ADD** form-collection writes for `always_listen` at TWO specific sites (cycle-1 review verified — L5 left no remaining sites; these are the actual locations):
    1. **`collectFormData` (~line 1556, immediately before `return { name, type, config, secrets, ... }`)**: explicitly write `config.always_listen = !!container.querySelector('[data-field="always_listen"]').checked;`. The function builds `config` via the per-type registry's `collect` hook OR the kv-table fallback; neither scans the new toggle by `data-field`, so the substrate must write it directly.
    2. **`getFormSnapshot` (line 881)**: add `'always_listen'` handling to the dirty-tracker snapshot. The current `staticFields` loop at line 884 reads `.value` (which is `"on"` for checkboxes regardless of state), so the new field MUST be captured as a separate top-level key on `snapshotObj`. Example:
       ```javascript
       var alwaysListenEl = container.querySelector('[data-field="always_listen"]');
       snapshotObj.always_listen = alwaysListenEl ? !!alwaysListenEl.checked : false;
       ```
       The merge happens at the substrate level (alongside `static`, `config`, `secrets`) — `always_listen` is a substrate-level field, NOT a registry-entry field. Do NOT route through the per-type registry's `snapshot()` hook (registry entries own only type-specific inputs).
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js`:
  - **ADD** a per-account "Always Listen on this connector account" toggle inside each tile's `detailsBody`, before the first axis row (~line 254+):
    ```javascript
    // M11 F7 L11: per-account "Always Listen" toggle.
    // Greyed-out when account.config.always_listen is False (no semantic
    // effect anyway since the master is OFF; UI mirrors the data layer's
    // structural inertness).
    var alwaysListenForAccount = (agent.connector_always_listen && agent.connector_always_listen[account.id]) || false;
    var accountAlwaysListenMaster = !!(account.config && account.config.always_listen);
    var alwaysListenRow = document.createElement('div');
    alwaysListenRow.className = 'field-row admin-pf-row connector-account-always-listen-row';
    var alwaysListenLabel = document.createElement('label');
    alwaysListenLabel.htmlFor = 'agent-always-listen-' + account.id;
    alwaysListenLabel.textContent = 'Always Listen on this connector account';
    alwaysListenRow.appendChild(alwaysListenLabel);
    var alwaysListenInput = document.createElement('input');
    alwaysListenInput.type = 'checkbox';
    alwaysListenInput.id = 'agent-always-listen-' + account.id;
    alwaysListenInput.className = 'field-input agent-connector-always-listen-toggle';
    alwaysListenInput.setAttribute('data-field', 'connector_always_listen');
    alwaysListenInput.setAttribute('data-account-id', account.id);
    alwaysListenInput.setAttribute('data-testid', 'agent-connector-always-listen-' + account.id);
    alwaysListenInput.checked = alwaysListenForAccount;
    alwaysListenInput.disabled = !accountAlwaysListenMaster;
    // M11 F7 L11 (cycle-1 review): wire onChange() for dirty-tracking.
    // Mirrors the attach-toggle wiring at connectors-tab.js:452 — without
    // this, toggling the per-agent switch leaves the Save button disabled.
    alwaysListenInput.addEventListener('change', function () { onChange(); });
    alwaysListenRow.appendChild(alwaysListenInput);
    detailsBody.appendChild(alwaysListenRow);
    ```
  - **ADD** a listener for the `connector-account-always-listen-changed` CustomEvent that updates the matching per-agent toggle's `disabled` state in real time:
    ```javascript
    // M11 F7 L11: listen for account-level master changes to grey-out
    // per-account toggles. Mirrors F4 / F5 listener pattern.
    document.addEventListener('connector-account-always-listen-changed', function (event) {
        var accountId = event.detail && event.detail.accountId;
        var enabled = !!(event.detail && event.detail.enabled);
        if (!accountId) return;
        var toggle = document.querySelector(
            '[data-field="connector_always_listen"][data-account-id="' + CSS.escape(accountId) + '"]'
        );
        if (toggle) {
            toggle.disabled = !enabled;
            if (!enabled) toggle.checked = false;  // master OFF → force per-agent off
        }
    });
    ```
  - **ADD** form-collection write for the per-agent toggles in **`the_one/interfaces/web/static/js/areas/studio.js::collectFormData` (~lines 2030-2150)** — NOT in `connectors-tab.js` (cycle-1 review correction). Mirror the `connector_acls` collection precedent at the same file (lines 1862-2152). The new code shape:
    ```javascript
    // M11 F7 L11: collect per-account always_listen toggles into a dict.
    // Mirrors the connector_acls collection pattern in this same file.
    var alwaysListenToggles = editorEl.querySelectorAll(
        '[data-field="connector_always_listen"][data-account-id]'
    );
    var alwaysListenDict = {};
    alwaysListenToggles.forEach(function (input) {
        var aid = input.getAttribute('data-account-id');
        if (aid) alwaysListenDict[aid] = !!input.checked;
    });
    data.connector_always_listen = Object.keys(alwaysListenDict).length > 0
        ? alwaysListenDict
        : null;
    ```
- New browser tests in `tests/browser/test_flow_studio_always_listen_toggles.py` (NEW file):
  - `test_account_editor_always_listen_toggle_renders` — visit `#studio/connectors/<id>`; verify `[data-testid="connector-account-always-listen-toggle"]` is visible.
  - `test_account_editor_always_listen_toggle_persists_true` — toggle ON, save, navigate away + back; verify the toggle is checked.
  - `test_account_editor_always_listen_toggle_persists_false` — toggle OFF (or leave default), save, verify state.
  - `test_account_editor_always_listen_info_icon_tooltip_present` — verify `[data-testid="connector-account-always-listen-hint"]` is present with the help text.
  - `test_agent_connectors_tab_per_account_toggle_renders` — open an agent editor on the Connectors tab with at least one attached account; verify `[data-testid="agent-connector-always-listen-<account-id>"]` is visible.
  - `test_agent_connectors_tab_per_account_toggle_disabled_when_master_off` — account toggle OFF in account editor; navigate to agent editor; per-agent toggle is `disabled`.
  - `test_agent_connectors_tab_per_account_toggle_enabled_when_master_on` — account toggle ON; per-agent toggle is interactive.
  - `test_cross_component_event_disables_per_agent_toggle` — open agent editor (with master ON); toggle account-level OFF in another tab/window via direct DOM; verify the per-agent toggle becomes disabled WITHOUT page reload. (May require simulating the CustomEvent dispatch directly via `page.evaluate`.)
- New non-browser tests in `tests/test_studio_always_listen_form_collection.py` (OPTIONAL — Developer judges whether the browser tests cover this surface adequately; if the form-collection logic is non-trivial, a focused unit-test on the JS via `pytest-playwright`'s in-browser JS exec may be worth it):
  - One test asserting the save payload includes `always_listen: true/false` when the account toggle is set.
  - One test asserting the agent save payload includes `connector_always_listen: {account_id: bool}`.

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` has the new "Always Listen" toggle row in the Session section, with `data-field="always_listen"` and `data-testid="connector-account-always-listen-toggle"`.
- [ ] The account-editor toggle dispatches `connector-account-always-listen-changed` on change.
- [ ] An explicit `TODO(routine-maintenance):` comment cites F4 R13 (studio-event-bus lift) above the dispatch.
- [ ] Form save serializes `always_listen` to `account.config["always_listen"]` (bool).
- [ ] `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` has a per-account "Always Listen on this connector account" toggle inside each tile's `detailsBody`, with `data-field="connector_always_listen"` and `data-account-id="<account_id>"` and `data-testid="agent-connector-always-listen-<account-id>"`.
- [ ] Per-account toggle's `disabled` attribute reflects the account's master toggle state at render time.
- [ ] Per-account toggle's `disabled` attribute updates in real-time when the `connector-account-always-listen-changed` CustomEvent fires.
- [ ] Toggling either switch (account-level OR per-agent) enables the editor's Save button (verifies dirty-tracker integration).
- [ ] When the master toggle turns OFF, per-agent toggles for that account are forced to `checked = false` (cycle-safe defensive UI).
- [ ] Agent save serializes the per-account toggles into `agent.connector_always_listen: {account_id: bool, ...}`.
- [ ] All ~8 new browser tests in `tests/browser/test_flow_studio_always_listen_toggles.py` pass.
- [ ] `docker exec the-one pytest tests/browser/test_flow_studio_always_listen_toggles.py -x --timeout 60` passes (browser tests run slower; allow higher timeout).
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L11-introduced regressions in the non-browser path; browser-test gate run separately.
- [ ] Flight log L11 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md`; status set to `landed`.

## Verification Steps

- `grep -n "always_listen" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns the toggle + form-collection sites.
- `grep -n "connector_always_listen" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` returns the per-account toggle + form-collection sites.
- `grep -n "connector-account-always-listen-changed" the_one/interfaces/web/static/js/` returns one dispatch (account-editor) + one listener (connectors-tab).
- `grep -n "TODO(routine-maintenance)" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns the F4-R13 lift-candidate citation.
- Browser tests: `docker exec the-one pytest tests/browser/test_flow_studio_always_listen_toggles.py -x --timeout 60` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green (browser tests deselected by default per pyproject; run them explicitly).

## Implementation Guidance

1. **Add the account-level toggle** in `connector-account-editor.js` Session section per the Outputs code sketch. Insert before the closing `</div>` at line ~455. Use the existing field-row-3-column pattern (Chat-session window / Idle timeout are precedents).

2. **Add the CustomEvent dispatch** on the account toggle's change. Place the listener-registration code in the same form-init function that wires the other event listeners (the Developer agent finds the standard location for these registrations in the file).

3. **Add the per-account toggle in `connectors-tab.js`** per the Outputs code sketch. Insert inside `_populateAclEditor` or wherever `detailsBody` is populated, BEFORE the first axis row.

4. **Add the listener** in `connectors-tab.js` for `connector-account-always-listen-changed`. Place at module init (one-time registration) or inside the per-tile setup (re-registered each tile — safe but redundant). The Developer agent picks the cleaner placement.

5. **Add form-collection writes**:
   - In `connector-account-editor.js`: write `always_listen` to the saved config dict (find the form-collection sites — same locations as the old L5-removed `auto_relay_platform_replies` writes).
   - In `connectors-tab.js`: gather per-account toggle states into a `{account_id: bool}` dict and write to the agent's `connector_always_listen` field at save time. Mirror the `connector_acls` collection precedent.

6. **Add the TODO comment** citing F4 R13 above the CustomEvent dispatch in `connector-account-editor.js`.

7. **Write browser tests** per Outputs. Use the Playwright pattern from `test_flow_studio_connector_account_navigation.py`. The browser-test fixture provides `page`, `app_clean`, and the connector account setup.

8. **Run targeted browser tests, then full suite**. Update flight log under `## Leg Progress` with `### L11 — studio-ui-policy-toggles`. Check off in flight.md. Set L11 status to `landed`. Do NOT commit.

## Edge Cases

- **Account.config["always_listen"] absent on existing rows** — read defaults to `false` via the leg's `Object.prototype.hasOwnProperty` check; the toggle renders unchecked. Matches the storage default.
- **Agent.connector_always_listen is None** — the per-account toggle reads `(agent.connector_always_listen && agent.connector_always_listen[account.id]) || false`. The `&&` short-circuits on None.
- **Operator un-checks the master toggle while an agent's Connectors tab is open in another browser tab** — the CustomEvent dispatches in the source tab only; the other tab doesn't see it. Acceptable — the operator's next save would persist the new state, and the other tab's stale UI corrects on next render. Tests cover the same-tab path.
- **Cross-account interaction** — if an agent is attached to multiple accounts with different master toggles, each per-account row reflects its own master state. The CustomEvent's `accountId` ensures only the matching row updates.
- **Form-collection ordering** — when both the agent toggle AND the account toggle are saved (e.g., operator edits an agent, then immediately edits the connector account), they're independent saves. No cross-coordination needed.
- **Validator rejection on save** — backend validator (L5) rejects non-bool values for `always_listen`. The frontend coerces to bool via `!!`, so the validator should never reject. Defensive in case a future field-input shape sends something else.
- **Per-agent toggles for non-attached accounts** — if `agent.connector_account_ids = ["acct-a"]` but `agent.connector_always_listen = {"acct-a": True, "acct-b": True}`, the orphan "acct-b" entry doesn't render any UI (no tile for unattached accounts). On save, the form collects only currently-rendered toggles; orphan entries get pruned. (L6's validator accepts orphan entries; L11 doesn't preserve them — matches the connector_acls behavior.)
- **Disabled toggle interaction** — a disabled checkbox can't be clicked by the operator. JS code that programmatically clicks it via `.click()` would still fire (browser-test edge case to avoid).
- **F5 R12 codification deferral** — the field-row-3-column pattern continues at n=3 (account toggle), then n=4-5 (per-agent toggle + agent's existing axes). The primitive lift is deferred to the future UX maturity mission. Honor the pattern in L11; do not introduce a new primitive component.
- **F4 R13 codification deferral** — the studio-event-bus lift candidate is at n=3 after L11. The TODO comment in `connector-account-editor.js` documents the candidate; routine-maintenance picks it up.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — ADD account-level toggle + CustomEvent dispatch + TODO comment + form-collection writes.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — ADD per-account toggle + CustomEvent listener + `onChange()` wiring.
- `the_one/interfaces/web/static/js/areas/studio.js` — ADD per-account `connector_always_listen` dict collection in `collectFormData` (mirror the `connector_acls` collection precedent at lines 1862-2152).
- `tests/browser/test_flow_studio_always_listen_toggles.py` — NEW file with ~8 browser tests.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND L11 entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (browser targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Commit all changes — DEFERRED per F7 flight-level commit ordering.

## Citation Audit

Citations verified against current code at design time via the F7 L11 reconnaissance pass:

- `connector-account-editor.js:398-455` — Session section with two existing field-row-3-column rows (verified).
- `connector-account-editor.js:1656-1658` — `connector-account-pool-warmed` CustomEvent dispatch (verified, F4 precedent).
- `connector-account-editor.js:3181-3185` — `connector-account-discoverable-refresh-requested` dispatch (verified, F5 precedent).
- `connectors-tab.js:196-299` — per-account tile structure (verified).
- `discoverable-dropdown.js:594-599` — disabled-state composition (verified).
- `tests/browser/test_flow_studio_connector_account_navigation.py:1-142` — Playwright precedent (verified).
- F4 R13 + F5 R12 deferred-lift candidates (verified via flight debriefs).
- L5 storage layer + L6 storage layer in place (verified via task list).
- L9 deleted `tests/browser/test_flow_studio_connector_directive_section.py` (verified — file gone).
