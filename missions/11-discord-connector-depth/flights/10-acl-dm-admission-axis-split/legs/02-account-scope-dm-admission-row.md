# Leg: account-scope-dm-admission-row

**Status**: completed
**Flight**: [ACL DM-admission + channels-axis UI split](../flight.md)

## Objective

Add a "DM admission" row to the Studio connector account allowlist editor — a 3-value selector (`none` / `allowlisted-peers-only` / `all`) that persists to `account.config.allowlist.dm_admission`. Wire it into the dirty-tracker snapshot and the save flow so it round-trips without other allowlist axes regressing.

## Context

**Why this leg.** L1 landed the substrate (validator + dispatcher) — the field exists in storage and the dispatcher consults it, but the operator can only set it via direct DB edits today. L2 ships the UI affordance so the operator can pick "deny all DMs / approved peers only / all DMs" from the connector account detail page.

**Placement** (per F10 §5): row inserted between the **peers** axis (`renderAllowlistSection` at line 2031-2043) and the **channels** axis (line 2045-2057). Semantic ordering: peers defines WHO can DM; dm_admission defines WHETHER DMs are admitted at all; channels (interpreted post-L1 as guild-channel restriction) follows.

**Render shape**: HTML `<select>` element with three `<option>` entries. The semantic distinction matters more than radio-vs-select; `<select>` keeps the form vertically compact (the editor already has 4+ axis rows below). Option values match the Pydantic Literal exactly:
- `<option value="none">Deny all DMs</option>`
- `<option value="allowlisted-peers-only">Admit DMs from approved peers</option>` (default `selected` when account has this value)
- `<option value="all">Admit all DMs</option>`

**Dirty-tracker integration**: `collectAllowlistFromContainer` (line 3383-3437) returns a dict with `peers/channels/guilds/roles`. L2 extends the dict shape to include `dm_admission`. Because `getFormSnapshot` (line 920+) calls `collectAllowlistFromContainer` and stores the result as `snapshotObj.allowlist`, the new field rides into the snapshot for free. The dirty-tracker re-snapshots after every input change and compares JSON-stringified snapshots — a single new key in the dict gets diffed automatically.

**Save flow integration**: `collectFormData` (line 1484+) at lines 1604-1614 calls `collectAllowlistFromContainer` then explicitly enumerates the 4 known keys (`peers`, `channels`, `guilds`, `roles`) when building `config.allowlist`. **The merge is NOT a spread** — L2 MUST add `dm_admission: allowlistState.dm_admission` to that explicit list, or the new field will be silently dropped from the save payload. Sub-step C adds this; the leg-design-cycle-1 reviewer caught this gap.

**Backwards compatibility**: when the editor renders an account whose `allowlist.dm_admission` is absent (i.e. a fresh model_validate just inserted the default `"allowlisted-peers-only"` per L1), the selector defaults to `"allowlisted-peers-only"`. The L1 migration walks legacy v21 rows and pre-populates the field, so production accounts arriving at the editor will already carry an explicit value.

**Tooltip / help text** (operator-facing semantic): "DMs (direct messages to the bot) are admitted independently of channel restrictions. Approved peers are those on the Peers allowlist above." Inline via the existing `field-info-icon` pattern at line 2036-2041.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:2031-2043` — peers axis row (precedent for row markup pattern).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:2045-2057` — channels axis row (precedent + insertion point — L2's row goes BEFORE this).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:3383-3437` — `collectAllowlistFromContainer`. Extend.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:920+` — `getFormSnapshot`. No direct change (rides on collectAllowlistFromContainer).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:1605` — `collectFormData` allowlist merge site. No direct change (also rides on collectAllowlistFromContainer).
- `the_one/db/models.py` (post-L1) — Pydantic validator enforces `dm_admission` Literal values and inserts default. L2's UI value must match these exactly.
- `tests/browser/test_flow_studio_connector_*.py` — browser test patterns.

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `renderAllowlistSection` extended with the DM admission row; `collectAllowlistFromContainer` extended to read the selector and emit `dm_admission` in the returned dict.
- `tests/browser/test_flow_studio_connector_dm_admission_row.py` — NEW browser test file covering: row renders with current account value preselected; save/load round-trip persists the chosen value; dirty-tracker fires when the value changes.
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — append L2 progress entry.

L2 does NOT touch: the per-agent ACL overlay (L3 owns that), the substrate (L1 landed), any backend tests beyond the browser fixture (the API round-trip is covered by L1's repository + API tests).

## Acceptance Criteria

- [ ] `renderAllowlistSection` emits a new row with `data-testid="connector-allowlist-dm-admission-row"` between the peers row and the channels row.
- [ ] The row contains a `<select data-testid="connector-allowlist-dm-admission-select">` with exactly three options (`none`, `allowlisted-peers-only`, `all`) and a `<label>` reading "DM admission" — literal (no vocabulary substitution; DM is universal across connector types).
- [ ] On render, the selector's selected value matches `account.config.allowlist.dm_admission`. For accounts with absent `dm_admission` (shouldn't happen post-L1 but defensively), the selector defaults to `allowlisted-peers-only`.
- [ ] `collectAllowlistFromContainer` returns a dict that now includes a `dm_admission` key (string value, one of the 3 Literal values).
- [ ] Dirty-tracker fires when the operator changes the selector value (verified by the existing `_pollDirty` mechanism — no new wiring needed).
- [ ] Save flow persists the chosen value to `account.config.allowlist.dm_admission` via the existing `PUT /api/connector-accounts/{id}` path.
- [ ] Round-trip: GET the account → renders with the new value preselected.
- [ ] Tooltip via `field-info-icon` is wired with `aria-describedby` + a `visually-hidden` help-text span (mirroring the existing peers/channels rows).
- [ ] Browser tests pass:
  - `test_dm_admission_row_renders_with_account_value_preselected` — seed account with `dm_admission="all"`; navigate to editor; expect the selector's selected option to be `"all"`.
  - `test_dm_admission_change_marks_form_dirty` — change selector; expect Save button to enable (the existing dirty-tracker indicator).
  - `test_dm_admission_save_persists_value` — change selector, click Save; expect a subsequent GET to show the new value.
- [ ] Existing browser tests pass unchanged (vocab + allowlist-dropdown + connector-form tests).

## Verification Steps

```bash
# New browser test
docker exec the-one pytest tests/browser/test_flow_studio_connector_dm_admission_row.py -x --timeout 120 -v

# Existing connector-account-editor browser tests (regression net)
docker exec the-one pytest tests/browser -k "connector" -x --timeout 120 -v

# Full backend suite (post-L1 baseline: 2733)
docker exec the-one pytest --timeout 60 -q
```

Expected: green; backend suite unchanged (L2 is UI-only); 3 new browser tests pass.

## Implementation Guidance

### Sub-step A — Render the row

Edit `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`. Insert this block between line 2043 (end of peers row) and line 2045 (start of channels row):

```javascript
// M11 F10 L2: DM admission axis (3-value selector). Semantic
// placement: peers defines WHO can DM; dm_admission gates WHETHER
// DMs are admitted; channels (post-L1: guild-channel restriction)
// follows. Storage at account.config.allowlist.dm_admission;
// dispatcher consult at _acl.py:admits_inbound (L1).
var dmAdmissionTipText = 'DMs (direct messages to the bot) are ' +
    'admitted independently of channel restrictions. Approved ' +
    'peers are those on the Peers allowlist above.';
var currentDmAdmission = (account && account.config && account.config.allowlist &&
    account.config.allowlist.dm_admission) || 'allowlisted-peers-only';
html += '<div class="field-row admin-pf-row connector-account-acl-fieldrow" ' +
        'data-testid="connector-allowlist-dm-admission-row">';
html += '<label class="connector-account-acl-fieldlabel" ' +
        'for="connector-allowlist-dm-admission-select">DM admission</label>';
html += '<button type="button" class="field-info-icon" ' +
        'title="' + escapeAttr(dmAdmissionTipText) + '" ' +
        'aria-describedby="connector-allowlist-dm-admission-help-text" ' +
        'data-testid="connector-allowlist-dm-admission-hint">' + infoIcon + '</button>';
html += '<span id="connector-allowlist-dm-admission-help-text" class="visually-hidden">' +
        escapeHtml(dmAdmissionTipText) + '</span>';
html += '<select id="connector-allowlist-dm-admission-select" ' +
        'class="field-input admin-pf-input" ' +
        'data-testid="connector-allowlist-dm-admission-select">';
html += '<option value="none"' +
        (currentDmAdmission === 'none' ? ' selected' : '') + '>Deny all DMs</option>';
html += '<option value="allowlisted-peers-only"' +
        (currentDmAdmission === 'allowlisted-peers-only' ? ' selected' : '') +
        '>Admit DMs from approved peers</option>';
html += '<option value="all"' +
        (currentDmAdmission === 'all' ? ' selected' : '') + '>Admit all DMs</option>';
html += '</select>';
html += '</div>';
```

The `currentDmAdmission` defensive default `|| 'allowlisted-peers-only'` covers the unlikely case where the account arrives at the editor without the field set. L1's validator should always populate it via the in-place default insertion, but the JS defensive default matches.

### Sub-step B — Extend `collectAllowlistFromContainer`

Edit the function at line 3383-3437. **Note the early-return guard at line 3404** (`if (!peersSlot && !channelsSlot && !guildsSlot && !rolesSlot) return null;`). The DM admission selector lives in the same allowlist section as the chiplist slots, so if all chiplist slots are absent, the dm_admission selector is also absent — the early `return null` correctly short-circuits the whole allowlist read. NO change to the guard; the new field rides inside the existing dict-return path.

After the chiplist reads, extend the return block:

```javascript
function collectAllowlistFromContainer(container) {
    // ... existing peers/channels/guilds/roles slot queries unchanged ...
    if (!peersSlot && !channelsSlot && !guildsSlot && !rolesSlot) return null;
    // ... existing _readChiplist helper unchanged ...

    // M11 F10 L2: dm_admission axis (3-value selector). Reads the
    // selector value; defaults to 'allowlisted-peers-only' when the
    // selector is absent (defensive — shouldn't reach this code path
    // because the early-return above already guards on chiplist
    // absence, and dm_admission renders in the same section).
    var dmAdmissionSelect = container.querySelector(
        '[data-testid="connector-allowlist-dm-admission-select"]');
    var dmAdmission = dmAdmissionSelect ? dmAdmissionSelect.value : 'allowlisted-peers-only';

    return {
        peers: _readChiplist(peersSlot),
        channels: _readChiplist(channelsSlot),
        guilds: _readChiplist(guildsSlot),
        roles: _readChiplist(rolesSlot),
        dm_admission: dmAdmission,
    };
}
```

### Sub-step C — Extend `collectFormData`'s allowlist key list

**REQUIRED change** — the merge at lines 1604-1614 is explicit-key enumeration, NOT a spread. Add the new field to the explicit list:

```javascript
if (isEdit) {
  var allowlistState = collectAllowlistFromContainer(container);
  if (allowlistState) {
    config.allowlist = {
      peers: allowlistState.peers,
      channels: allowlistState.channels,
      guilds: allowlistState.guilds,
      roles: allowlistState.roles,
      dm_admission: allowlistState.dm_admission,  // M11 F10 L2
    };
  }
}
```

Without this line, `collectAllowlistFromContainer` reads the selector but `collectFormData` drops the value on the floor — save silently regresses. The cycle-1 reviewer flagged this; do NOT skip.

### Sub-step D — Browser tests

Create `tests/browser/test_flow_studio_connector_dm_admission_row.py`. Mirror the fixture shape from `tests/browser/test_flow_studio_connector_discord_vocabulary.py` (sibling test in the same area). Seed accounts via the existing `seed_connector_account(app_clean, type="stub", config={"allowlist": {...}})` helper at `tests/browser/seeders.py:86` (the established pattern — uses the API which exercises L1's validator). Navigate the Playwright page to the connector account detail view; assert via `data-testid` selectors.

Test cases:

1. `test_dm_admission_row_renders_with_account_value_preselected`:
   - Seed: account with `config.allowlist.dm_admission = "all"`.
   - Navigate to editor.
   - Assert: `connector-allowlist-dm-admission-select` exists; selected option value is `"all"`.

2. `test_dm_admission_change_marks_form_dirty`:
   - Seed: account with `dm_admission = "allowlisted-peers-only"`.
   - Navigate to editor.
   - Change select to `"none"`.
   - Assert: `save_btn = page.locator('[data-testid="save-connector-account-btn"]'); expect(save_btn).not_to_be_disabled()` (concrete pattern per `tests/browser/test_flow_studio_connector_account_editor.py:217-218`).

3. `test_dm_admission_save_persists_value`:
   - Seed: account with `dm_admission = "allowlisted-peers-only"`.
   - Navigate to editor, change select to `"all"`, click Save.
   - Wait for save to complete.
   - Issue a follow-up GET (via httpx or via the page's network — match existing test pattern).
   - Assert: response's `config.allowlist.dm_admission == "all"`.

### Sub-step E — Flight log

Append to `flight-log.md` under "Leg Progress":

```
### {date} — L2 account-scope-dm-admission-row (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `connector-account-editor.js` — DM admission row inserted between peers and channels in `renderAllowlistSection`; `collectAllowlistFromContainer` extended to read the selector value.
- `tests/browser/test_flow_studio_connector_dm_admission_row.py` — NEW (3 tests).

**Test outcomes**: 3 new browser tests pass; existing connector-area browser tests pass unchanged; backend suite unchanged (2733).

**Anomalies**: {document any}
```

## Edge Cases

- **Account renders in create-mode (no allowlist yet)**: `account.config.allowlist` may be `null` or `undefined`. The `currentDmAdmission` defensive default covers this. Create-mode flow doesn't render the allowlist section at all (line 531 `var allowlistHtml = isCreate ? '' : renderAllowlistSection(account);`) — so the row only appears in edit mode, by inheritance.
- **`dm_admission` field is malformed at the API**: rejected by L1's validator with HTTP 422 (covered by L1's API tests). L2's UI never produces malformed values because the selector is constrained to 3 fixed options.
- **Operator opens the editor on a connector account THAT IS NOT Discord** (e.g. a stub account from tests): the row still renders because the allowlist editor is connector-agnostic. The dispatcher only consults `dm_admission` when `is_dm=True`, which is determined by the plugin's `is_dm` hook — stub plugins don't return True, so the field has no runtime effect on non-Discord accounts. Acceptable; the UI surface is the same shape across connector types.
- **Reset / discard changes**: the existing reset flow re-renders the form with the original account; the selector re-selects per `account.config.allowlist.dm_admission` (the captured original) via the standard render path. No special handling needed.
- **Discoverable-dropdown path doesn't apply**: dm_admission is not an entity-based axis (no users/channels/roles to enumerate); the row uses a plain `<select>` not a dropdown component.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — +~30 LOC (row markup) + ~5 LOC (collect function extension).
- `tests/browser/test_flow_studio_connector_dm_admission_row.py` — NEW, ~150-200 LOC.
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — L2 entry.

Estimated total: ~200 LOC of net change.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new browser tests pass; existing browser tests pass unchanged
- [ ] Backend suite unchanged (L2 is UI-only)
- [ ] Update flight-log.md with L2 progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

5 citations verified against current code at leg design time (post-L1):
- `connector-account-editor.js:2031-2043` (peers axis row) — OK
- `connector-account-editor.js:2045-2057` (channels axis row; insertion point) — OK
- `connector-account-editor.js:3383-3437` (collectAllowlistFromContainer) — OK
- `connector-account-editor.js:920+` (getFormSnapshot) — OK
- `connector-account-editor.js:1604-1614` (collectFormData allowlist merge — explicit-key copy, NOT spread; L2 must extend the explicit key list per Sub-step C) — verified.
