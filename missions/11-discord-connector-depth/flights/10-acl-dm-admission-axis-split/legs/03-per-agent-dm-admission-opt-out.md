# Leg: per-agent-dm-admission-opt-out

**Status**: completed
**Flight**: [ACL DM-admission + channels-axis UI split](../flight.md)

## Objective

Add a per-agent "Admit DMs from this account" checkbox to the agent editor's Connectors tab so the operator can opt an agent OUT of DM admission even when the account-scope `dm_admission` permits. Wire it into the `connector_acls` collection in `studio.js` so the value persists to `agent.connector_acls[account_id].admit_dms`.

## Context

**Why this leg.** L1 landed the per-agent substrate (`admit_dms: bool | None` in `connector_acls` inner dict). L3 ships the UI affordance: a single checkbox per attached account inside the per-account ACL section of the agent editor's Connectors tab. Operator-confirmed semantic: checked = inherit account-scope (`admit_dms` absent from the per-account ACL); unchecked = explicit opt-out (`admit_dms: false`).

**Why a sibling helper, NOT `_buildAxisRow`.** `_buildAxisRow` (in `connectors-tab.js:293`) is axis-shaped: takes a `scopeList` array + per-agent value list and renders either a checkbox-list (when account-scope has chips) or a chip-list editor. `admit_dms` is a single boolean — no list semantics, no checkbox-mode/chip-mode duality. Per F10 §6 (cycle-1 Architect): use a NEW sibling helper (call it `_buildAdmitDmsRow`) modeled on the existing always-listen row at `connectors-tab.js:497-520`, NOT a parameter-extension of `_buildAxisRow`.

**Placement.** Inside `_populateAclEditor`'s `section` (line 285+), AFTER the always-listen row (~line 520) but BEFORE the peers/channels axis rows (lines 522-523). The operator's mental ordering: connector-attachment toggle (outer) → master capability toggles (always-listen, admit-dms) → per-axis ACL editors. The admit-dms row sits with always-listen because both are per-agent boolean overrides keyed by account_id.

**Render shape.** Mirror the always-listen row's `tool-enable-switch` toggle structure (`connectors-tab.js:484-520`). A `<label class="field-row connector-account-admit-dms-row">` containing a descriptive label + a `tool-enable-switch` element. Switch checked = inherit (default); unchecked = opt-out.

**Disabled state.** When account-scope `dm_admission === "none"`, the per-agent override is structurally inert (no DMs reach the dispatcher for the account anyway). Render the switch disabled + visually-checked (operator can see the field exists but can't toggle it). Hint text adjusts: "Account denies all DMs; per-agent override does not apply."

When account-scope is `"all"` or `"allowlisted-peers-only"`, the switch is interactive.

**Collection in `studio.js`.** The per-agent ACL is collected at `studio.js:2104-2181`. Currently:
1. Walk `[data-connector-acl-account][data-connector-acl-list][data-connector-acl-mode]` elements (peers/channels axes).
2. Build `aclAccounts[aid] = { peers, channels }`.
3. Omit accounts where BOTH axes are null (inherit-both) at line 2178.
4. Emit `data.connector_acls`.

L3 extends this with a SEPARATE walk (mirroring the `connector_always_listen` walk at lines 2193-2204) for `[data-field="admit_dms"][data-account-id]`. The result merges into the same `aclAccounts` dict — but ONLY when the operator OPTS OUT (checkbox unchecked → `admit_dms: false`). When checked = inherit, do NOT emit the key (matches the existing "absent = inherit" convention for peers/channels).

**Omit-when-empty adjustment.** Line 2178's omit-when-inherit-both check needs to also consider `admit_dms`. After L3:
```
if (entry.peers === null && entry.channels === null && !("admit_dms" in entry)) continue;
```
Equivalently: only emit the account entry if any of the three axes has an explicit narrowing.

**Cycle-1 reviewer note for L2** found `collectFormData`'s allowlist merge enumerated keys explicitly. L3's collection is shape-symmetric (writes into an existing dict-of-dict structure with explicit per-key behaviour at the omit check) — no equivalent shape hazard, but the omit-check needs the explicit `admit_dms` addition.

**Backwards compatibility.** Pre-L3 agents have `connector_acls[acct]` entries that lack `admit_dms`. L1's validator accepts the absent-key case (validator only enforces the value-type WHEN the key is present per Sub-step C). The UI renders pre-L3 entries as checked-by-default (inherit).

**Critical: `accountAcl` normalization at `connectors-tab.js:155-164` strips `admit_dms`** — the existing normalization rebuilds `accountAcl` as `{peers, channels}` ONLY, dropping any other keys. Without fixing this, the helper's `accountAcl.admit_dms` is ALWAYS `undefined` regardless of what's in storage, so a previously-saved `admit_dms: false` would render as CHECKED (inherit), losing the operator's opt-out on every page reload. L3 MUST extend the normalization to preserve `admit_dms`. See Sub-step A2 below.

**Disabled-state collect posture (cycle-1 reviewer call)**: when account-scope `dm_admission === "none"`, the per-agent toggle is disabled. The collect logic skips disabled inputs (`if (adInput.disabled) continue;`), so a previously-persisted `admit_dms: false` will be silently dropped on the next agent save. **This is intentional cleanup**: when the account denies all DMs, the per-agent opt-out is redundant and removing it keeps the persisted shape clean. Operator-observable: flipping account-scope to "none" and saving the agent removes the per-agent opt-out from storage; subsequent flip back to "all" re-renders the switch as default-checked (inherit). Documented in Edge Cases.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:285-526` — `_populateAclEditor`. L3's row insertion happens here.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:484-520` — existing always-listen row (precedent shape).
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:522-523` — peers + channels axis rows (insertion point — L3's row goes BETWEEN always-listen and these).
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:155-170` — `accountAcl` / `scopePeers` / `scopeChannels` resolution. L3 needs to also resolve `accountScope.dm_admission` for the disabled-state logic.
- `the_one/interfaces/web/static/js/areas/studio.js:2104-2181` — `connector_acls` collection. Extend omit check at line 2178.
- `the_one/interfaces/web/static/js/areas/studio.js:2193-2204` — `connector_always_listen` collection (precedent for the new `admit_dms` walk).
- `the_one/db/models.py` / `the_one/agent/config.py` (post-L1) — validator accepts `admit_dms: bool | None` per-account.
- `tests/browser/test_flow_studio_always_listen_toggles.py` — sibling browser test (closest analogue).
- `tests/browser/seeders.py:86` — `seed_connector_account` helper.

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — new `_buildAdmitDmsRow(account, accountScopeDmAdmission, accountAcl, onChange)` sibling helper; called from `_populateAclEditor` between always-listen and peers/channels. Existing axes unchanged.
- `the_one/interfaces/web/static/js/areas/studio.js` — `collectFormData` extended with an `admit_dms` walk paralleling `connector_always_listen`; merges into `aclAccounts`; omit-check at line 2178 extended.
- `tests/browser/test_flow_studio_per_agent_admit_dms.py` — NEW browser test file (3 tests).
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — append L3 progress entry.

L3 does NOT touch: backend (L1 landed), account-scope UI (L2 landed), or the existing peers/channels axis rendering.

## Acceptance Criteria

- [ ] `connectors-tab.js` exports a new `_buildAdmitDmsRow` helper that builds a `tool-enable-switch`-shaped row with `data-testid="agent-connector-admit-dms-row-{account.id}"`.
- [ ] The switch input has `data-field="admit_dms"`, `data-account-id="{account.id}"`, `data-testid="agent-connector-admit-dms-{account.id}"`.
- [ ] Initial state: `checked` IFF the agent's `connector_acls[account.id].admit_dms` is NOT explicitly `false`. (i.e. absent / `null` / `true` → checked; only `false` → unchecked.)
- [ ] When account-scope `dm_admission === "none"`, the switch is DISABLED + visually-checked, hint text reads "Account denies all DMs; per-agent override does not apply."
- [ ] When account-scope is `"all"` or `"allowlisted-peers-only"`, the switch is interactive; default-state is checked (inherit) when no explicit `admit_dms` exists.
- [ ] Change event wires into the existing `onChange()` dirty-tracker callback (same pattern as always-listen at line 513).
- [ ] `studio.js:collectFormData` extended:
  - Walks `[data-field="admit_dms"][data-account-id]` and emits `admit_dms: false` into `aclAccounts[aid]` ONLY when the checkbox is unchecked.
  - Checked or disabled-and-checked → DO NOT emit the key (inherit; absent from per-account ACL).
- [ ] Omit-check at studio.js line 2178 extended: account entry is emitted into `finalAcls` if ANY of `peers/channels/admit_dms` is explicitly narrowing.
- [ ] Round-trip: unchecking the switch and saving persists `connector_acls[account.id].admit_dms = false`; re-rendering shows the switch unchecked.
- [ ] Round-trip: re-checking the switch and saving REMOVES the `admit_dms` key from the per-account ACL (does NOT persist `admit_dms: true` — true is structurally equivalent to inherit and would just clutter the persisted shape).
- [ ] New browser tests:
  - `test_admit_dms_renders_checked_by_default` — agent attached to account with `dm_admission="all"`; no per-agent override; switch is checked + interactive.
  - `test_admit_dms_unchecks_and_persists` — uncheck the switch, save; verify GET returns `connector_acls[acct].admit_dms == false`.
  - `test_admit_dms_disabled_when_account_dm_admission_none` — account `dm_admission="none"`; switch is disabled + visually checked; hint text matches the disabled-state literal.
- [ ] Existing browser tests pass unchanged.
- [ ] Backend suite unchanged (L3 is UI-only).

## Verification Steps

```bash
# New browser tests
docker exec the-one pytest tests/browser/test_flow_studio_per_agent_admit_dms.py -x --timeout 120 -v

# Existing studio + connector browser tests (regression net — especially always-listen)
docker exec the-one pytest tests/browser -k "studio or connector or always_listen" -x --timeout 120 -v

# Full backend suite (post-L2 baseline: 2733)
docker exec the-one pytest --timeout 60 -q
```

Expected: green; backend unchanged.

## Implementation Guidance

### Sub-step A1 — Extend `accountAcl` normalization to preserve `admit_dms`

**REQUIRED** (cycle-1 review HIGH). Edit `connectors-tab.js:155-164`. The existing normalization rebuilds `accountAcl` as `{peers, channels}` ONLY. Extend to preserve `admit_dms`:

```javascript
var rawAcl = aclsMap[account.id];
var accountAcl;
if (rawAcl == null) {
    accountAcl = { peers: null, channels: null, admit_dms: undefined };
} else {
    accountAcl = {
        peers: (rawAcl.peers === undefined) ? null : rawAcl.peers,
        channels: (rawAcl.channels === undefined) ? null : rawAcl.channels,
        admit_dms: rawAcl.admit_dms,  // M11 F10 L3: preserve through normalization
    };
}
```

Without this, the helper's `accountAcl.admit_dms` is always `undefined` and a previously-saved opt-out renders as CHECKED. Verification: load-render round-trip test (see Sub-step E test #4).

### Sub-step A2 — Resolve account-scope dm_admission for the disabled check

Edit `connectors-tab.js` around line 167 (where `accountScope`/`scopePeers` / `scopeChannels` are resolved). Add a resolution for the account-scope DM-admission value, which the new row needs to drive its disabled state:

```javascript
var accountScope = (account && account.config && account.config.allowlist) || null;
var scopePeers = (accountScope && Array.isArray(accountScope.peers)) ? accountScope.peers : [];
var scopeChannels = (accountScope && Array.isArray(accountScope.channels)) ? accountScope.channels : [];
// M11 F10 L3: account-scope dm_admission gates whether the per-agent
// admit_dms toggle is interactive. "none" disables the toggle
// (structurally inert); "allowlisted-peers-only" / "all" leave it
// interactive. Defensive default mirrors L1's validator behavior.
var scopeDmAdmission = (accountScope && accountScope.dm_admission) || 'allowlisted-peers-only';
```

### Sub-step B — New `_buildAdmitDmsRow` sibling helper

Add to `connectors-tab.js` adjacent to `_buildAxisRow` (just before it, around line 290). Modeled on the always-listen row pattern at lines 484-520:

```javascript
function _buildAdmitDmsRow(scopeDmAdmission, accountAcl, onChange) {
    // M11 F10 L3: per-agent opt-out for DM admission. Boolean field;
    // tri-state inheritance:
    //   - admit_dms absent / null → inherit account-scope (checked)
    //   - admit_dms === false → explicit opt-out (unchecked)
    //   - admit_dms === true → equivalent to inherit (still checked)
    var row = document.createElement('div');
    row.className = 'field-row admin-pf-row connector-account-admit-dms-row';  // L3: mirror always-listen row classes for visual parity
    row.setAttribute('data-testid',
        'agent-connector-admit-dms-row-' + account.id);

    var label = document.createElement('label');
    label.className = 'connector-account-admit-dms-label';
    label.textContent = 'Admit DMs from this account';
    row.appendChild(label);

    var hint = document.createElement('span');
    hint.className = 'form-hint connector-account-admit-dms-hint';

    var disabled = (scopeDmAdmission === 'none');
    if (disabled) {
        hint.textContent = 'Account denies all DMs; per-agent override does not apply.';
    } else {
        hint.textContent = 'Uncheck to deny DMs to this agent (account permits otherwise).';
    }
    row.appendChild(hint);

    // Tri-state initial: absent / null / true → checked; false → unchecked.
    var currentAdmitDms = accountAcl ? accountAcl.admit_dms : undefined;
    var initiallyChecked = (currentAdmitDms !== false);  // strict false check

    var sw = document.createElement('label');
    sw.className = 'tool-enable-switch';
    var input = document.createElement('input');
    input.type = 'checkbox';
    input.setAttribute('data-field', 'admit_dms');
    input.setAttribute('data-account-id', account.id);
    input.setAttribute('data-testid', 'agent-connector-admit-dms-' + account.id);
    input.checked = disabled ? true : initiallyChecked;
    input.disabled = disabled;
    input.addEventListener('change', function () { onChange(); });
    sw.appendChild(input);
    var track = document.createElement('span');
    track.className = 'tool-enable-switch-track';
    track.setAttribute('aria-hidden', 'true');
    sw.appendChild(track);
    row.appendChild(sw);

    return row;
}
```

Note: `account` is in closure from the enclosing `_populateAclEditor` / outer function — same scope structure as `_buildAxisRow` (which references `account.id` directly). Verify scope before final placement; if scope is unclear, pass `account` as a parameter to `_buildAdmitDmsRow`.

### Sub-step C — Wire into `_populateAclEditor`

Edit `connectors-tab.js:520-523`. Insert the new row between always-listen and peers/channels:

```javascript
// ... existing always-listen row construction ...
section.appendChild(alwaysListenRow);

// M11 F10 L3: per-agent admit_dms opt-out row (between always-listen
// and the peers/channels axis rows — both are per-agent boolean
// overrides keyed by account_id).
section.appendChild(_buildAdmitDmsRow(scopeDmAdmission, accountAcl, onChange));

section.appendChild(_buildAxisRow('peers', scopePeers, accountAcl.peers));
section.appendChild(_buildAxisRow('channels', scopeChannels, accountAcl.channels));
```

### Sub-step D — Extend `studio.js:collectFormData`

Edit `studio.js`. After the existing `connector_acls` collection block (lines 2104-2181), add a walk for `admit_dms`:

```javascript
// M11 F10 L3: collect per-agent admit_dms opt-out toggles. Walks
// every input with data-field="admit_dms"; emits admit_dms: false
// into aclAccounts[aid] ONLY when unchecked. Checked → inherit
// (key absent). Disabled-and-checked → inherit. Merges into the
// existing aclAccounts dict; the omit-check below is widened to
// consider admit_dms in addition to peers/channels.
var admitDmsToggles = editorEl.querySelectorAll(
    '[data-field="admit_dms"][data-account-id]'
);
for (var adi = 0; adi < admitDmsToggles.length; adi++) {
    var adInput = admitDmsToggles[adi];
    var adAid = adInput.getAttribute('data-account-id');
    if (!adAid) continue;
    if (adInput.checked) continue;  // checked = inherit (no key emitted)
    if (adInput.disabled) continue;  // disabled = structurally inert
    if (!aclAccounts[adAid]) {
        aclAccounts[adAid] = { peers: null, channels: null };
    }
    aclAccounts[adAid].admit_dms = false;
}
```

Place this block AFTER the existing peers/channels collection loop (~line 2173) and BEFORE the `finalAcls` construction (line 2174).

Update the omit-check at line 2178:

```javascript
var finalAcls = {};
for (var aid2 in aclAccounts) {
    var entry = aclAccounts[aid2];
    // Omit accounts where ALL axes are inherit-state.
    if (entry.peers === null
        && entry.channels === null
        && !("admit_dms" in entry)) continue;
    finalAcls[aid2] = entry;
}
data.connector_acls = Object.keys(finalAcls).length > 0 ? finalAcls : null;
```

### Sub-step E — Browser tests

Create `tests/browser/test_flow_studio_per_agent_admit_dms.py`. Mirror the fixture shape from `tests/browser/test_flow_studio_always_listen_toggles.py` (closest sibling).

Seed via `seed_connector_account(app_clean, type="stub", config={"allowlist": {"peers": [], "channels": [], "dm_admission": "all"}})` + create an agent attached to the account. The dm_admission value drives the disabled-state test.

Tests:

1. `test_admit_dms_renders_checked_by_default`:
   - Seed: account with `dm_admission="all"` + an agent attached, no per-agent override.
   - Navigate to agent editor → Connectors tab.
   - Assert: `expect(page.locator(f'[data-testid="agent-connector-admit-dms-{acct_id}"]')).to_be_checked()`.
   - Assert: NOT disabled.

2. `test_admit_dms_unchecks_and_persists`:
   - Seed: same as #1.
   - Uncheck the switch, click agent Save.
   - Issue GET on `/api/agents/{name}` (via httpx in the test, following sibling pattern).
   - Assert: response's `connector_acls[acct_id].admit_dms == false`.

3. `test_admit_dms_disabled_when_account_dm_admission_none`:
   - Seed: account with `dm_admission="none"`.
   - Navigate to agent editor → Connectors tab.
   - Assert: switch is `disabled`; visually checked; hint text contains "Account denies all DMs".

4. `test_admit_dms_reload_shows_unchecked_when_persisted_false` (REQUIRED — pins the cycle-1 normalization fix):
   - Seed: agent with `connector_acls = {acct_id: {peers: None, channels: None, admit_dms: False}}` attached to an account with `dm_admission="all"`.
   - Navigate to agent editor → Connectors tab.
   - Assert: switch renders UNCHECKED. (Without Sub-step A1's normalization fix, this would render CHECKED — the test catches the regression.)

### Sub-step F — Flight log

```
### {date} — L3 per-agent-dm-admission-opt-out (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `connectors-tab.js` — new `_buildAdmitDmsRow` sibling helper inserted between always-listen and peers/channels in `_populateAclEditor`; `scopeDmAdmission` resolution added near `scopePeers`/`scopeChannels`.
- `studio.js` — collectFormData extended with `admit_dms` walk + omit-check widened.
- `tests/browser/test_flow_studio_per_agent_admit_dms.py` — NEW (3 tests).

**Test outcomes**: 3 new browser tests pass; existing studio/connector browser tests pass unchanged; backend suite unchanged.

**Anomalies**: {document any}
```

## Edge Cases

- **Agent has connector_acls = null** (no per-account overrides). The `accountAcl` resolution at lines 158-167 yields `{ peers: null, channels: null }`; the helper checks `accountAcl.admit_dms` which is `undefined` → defaults to `initiallyChecked = true`. Correct (checked = inherit).
- **Agent has connector_acls[acct] but no admit_dms key** (pre-L3 data). Same disposition — `accountAcl.admit_dms === undefined`, checkbox checked, no opt-out.
- **Operator unchecks then re-checks** the switch within the same session, without saving in between. The dirty-tracker sees the snapshot diff and back, ending at the original state → Save button correctly disables again. Standard `getFormSnapshot` / `_pollDirty` behavior; no special handling.
- **Operator changes account-scope `dm_admission` from "all" to "none" while a per-agent unchecked override exists**. The collect path skips disabled inputs (per Sub-step D). On the NEXT save of this agent, the per-agent `admit_dms: false` is dropped from storage (intentional cleanup — see Context paragraph above). If the operator does NOT save before flipping the account-scope back to "all", the persisted `admit_dms: false` survives and the switch re-renders unchecked. This is the cleanest stable shape: stored opt-outs only exist when the account-scope makes them meaningful.
- **Multiple browser windows on the same agent**: both windows write `admit_dms`; last-writer-wins. Standard single-user-local-tool race posture.
- **Form load order: `account` object hasn't loaded when `_populateAclEditor` runs**: the existing code already handles the `accountScope = null` case (line 158). New code adds defensive default `|| 'allowlisted-peers-only'`.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — +~50 LOC (helper + insertion + scope resolution).
- `the_one/interfaces/web/static/js/areas/studio.js` — +~15 LOC (collection walk + omit-check extension).
- `tests/browser/test_flow_studio_per_agent_admit_dms.py` — NEW, ~150-200 LOC.
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — L3 entry.

Estimated total: ~225 LOC of net change.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new browser tests pass; existing browser tests pass unchanged
- [ ] Backend suite unchanged (L3 is UI-only)
- [ ] Update flight-log.md with L3 progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

7 citations verified against current code at leg design time:
- `connectors-tab.js:285-526` (_populateAclEditor) — OK
- `connectors-tab.js:484-520` (always-listen row precedent) — OK
- `connectors-tab.js:522-523` (peers + channels axis rows; insertion point) — OK
- `connectors-tab.js:155-170` (accountScope/scopePeers/scopeChannels resolution) — OK
- `studio.js:2104-2181` (connector_acls collection) — OK
- `studio.js:2178` (omit-when-inherit-both check) — OK
- `studio.js:2193-2204` (connector_always_listen walk precedent) — OK
