# Leg: ui-discoverable-dropdown-and-per-peer-dm-toggle

**Status**: completed
**Flight**: [Hierarchical Allowlist Axes + Snake_Case Identifier Rename](../flight.md)

## Objective

Land the F12 UI changes atomic to L3's storage substrate: update `connector-editor.js`'s allowlist editor + `agent-editor.js`'s per-agent overlay to render the structured-tuple shape (peers as `{id, dm_allowed}` dicts; channels as `{guild_id, channel_id}` tuples; roles as `{guild_id, role_id}` tuples); update `discoverable-dropdown.js` to emit structured tuples on selection; render the per-peer DM toggle CONDITIONALLY on account-scope `dm_admission` mode (visible under `admin-approved`, hidden/disabled under `all` / `none`); render the legacy-entry indicator for null-guild_id channel/role entries; update the dm_admission select options for the renamed Literal value `admin-approved` with revised label; sweep ~10 browser tests' fixtures + add 4-8 new browser tests covering conditional render + legacy indicator. Final leg of F12 before Phase 2d batches commits across L1-L4.

## Context

This is the fourth and final leg in F12. L1 (snake_case rename), L2 (`_acl.py` extraction + agents.md convention), and L3 (storage shape + v24 migration + ACL semantics) all landed cleanly with backend at **2767 passed / 0 errors / 248s wall** (post-L3 baseline; +18 vs L1's 2749 from new TestSchemaV24 + cross-product matrix + SQLite round-trip test).

**Per the flight spec's L4 design decision (UI — discoverable-dropdown grouping + per-peer DM toggle + allowlist editor refresh):**
- `dm_admission` row STAYS in the editor with revised label and updated Literal value (`"admin-approved"`).
- Per-peer DM toggle rendered conditionally — visible only when `dm_admission="admin-approved"`; hidden under `"all"` (everyone admitted) and `"none"` (nobody admitted) so operators don't see irrelevant controls.
- Channels + roles dropdowns emit structured `{guild_id, channel_id}` / `{guild_id, role_id}` tuples on selection.
- Legacy entries (post-v24 with null guild_id) render a "legacy entry" indicator + a "Re-scope to current guild" affordance.
- Per-agent overlay in `agent-editor.js` Connectors tab follows the same UI patterns with per-axis-tri-state-override semantics preserved.
- ~10-15 browser test fixture updates + 4-8 new browser tests; Phase 5c architect cycle enumerates exact test surface pre-implementation.

**L3 deviations to be aware of**: L3's implementing developer flipped the `dm_admission` Literal value in the storage layer to `"admin-approved"` and updated all Pydantic validators + ACL helpers. The UI is currently sending the old value `"allowlisted-peers-only"` on save — L3's tests pass because the JS-side request format is just a string the validator accepts post-rewrite. L4 closes this gap by updating the UI to send the new Literal value.

## Inputs

- F12 L1 + L2 + L3 landed (status: completed, uncommitted on branch `flight/12-hierarchical-allowlist-and-snake-case-rename`)
- Backend baseline (post-L3): 2767 passed / 4 skipped / 0 errors / ~248s wall
- Browser baseline (post-L3 — cycle-1 verified): browser tests are DEGRADED post-L3 because UI fixtures POST the old `"allowlisted-peers-only"` Literal value, which L3's Pydantic validator now REJECTS with 422. Specifically: 2 of 3 tests in `test_flow_studio_connector_dm_admission_row.py` fail; potentially additional failures across the 10 allowlist-touching browser tests. L4 explicitly UNBLOCKS these failures by updating fixtures + UI; L4 acceptance is "back to 431+ + 4-8 new tests passing", NOT "preserved at 431 since the start".
- `connector-editor.js` post-F11 rename (~3590 LOC) — allowlist editor at lines 1599-2095+ with dm_admission select at lines 2055-2095
- `discoverable-dropdown.js` — currently emits chips with `data-id` attribute (flat IDs); needs structured-tuple emit
- `agent-editor.js` — Connectors tab panel ID `agent-tab-panel-connectors` (line 49); per-agent `connector_acls` overlay rendering
- 10 browser tests touching allowlist or dm_admission: `test_flow_studio_connector_dm_admission_row.py`, `test_flow_chat_pending_approval.py`, `test_flow_studio_connector_routing_dropdown.py`, `test_flow_studio_connector_discord_vocabulary.py`, `test_flow_admin_tools_editor.py`, `test_flow_studio_per_agent_admit_dms.py`, `test_flow_studio_connector_allowlist_dropdown.py`, `test_flow_studio_per_agent_overlay_dropdown.py`, `test_flow_studio_connector_discoverable_dropdown.py`, `test_flow_studio_per_agent_overlay_label_resolver.py`
- Phase 5c architect cycle (mandated by F12 spec for L4) re-runs the browser-test grep pre-implementation to confirm + enumerate exact per-file diff scope
- Uncommitted operator dev state: `docker-compose.yml` (unchanged from L1-L3; stays unstaged)

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — allowlist editor renders structured-tuple peers/channels/roles; per-peer DM toggle conditional on `dm_admission`; legacy-entry indicator for null-guild_id; dm_admission select uses new `"admin-approved"` value with revised label
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — emits structured tuples on selection (for channels + roles); peers emit `{id, dm_allowed=false}` on first selection
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — per-agent overlay in Connectors tab mirrors structured-tuple rendering
- `the_one/interfaces/web/static/css/studio.css` (if needed) — styles for per-peer DM toggle + legacy-entry indicator
- 10+ browser tests updated for new shape; 4-8 new browser tests added covering conditional render + legacy indicator
- Flight log L4 progress entry appended
- Leg status `landed` (NOT committed — Phase 2d batches commits)

## Acceptance Criteria

- [x] **dm_admission select updated** in `connector-editor.js`:
  - Literal value `"allowlisted-peers-only"` → `"admin-approved"` in the `<option>` value attribute
  - Label revised: `"Admit DMs from approved peers"` → `"Admin-approved (per-peer)"` (operator-vocabulary alignment per F12 design)
  - Default fallback (in lines like `... || 'allowlisted-peers-only'`) updated to `'admin-approved'`
- [x] **Per-peer DM toggle rendered** in peers section of allowlist editor:
  - For each peer entry `{id, dm_allowed}`, render an additional control (slider/toggle/checkbox) for `dm_allowed`
  - CONDITIONAL rendering: visible + interactive ONLY when account-scope `dm_admission === "admin-approved"`. Under `"all"` and `"none"`, the toggle is HIDDEN (display: none) OR shown disabled with explanatory tooltip — implementer's call on hidden-vs-disabled; recommend hidden for cleanest UX
  - Toggle state mutates `allowlistState.peers[i].dm_allowed` on click; persists with the rest of the allowlist on save
  - DOM has `data-testid="connector-allowlist-peer-dm-toggle-{peer_id}"` for browser tests
- [x] **Structured-tuple peer/channel/role rendering**:
  - Peer chips read `peer["id"]` instead of `peer` (peer is now a dict, not a string)
  - Channel chips read `channel["channel_id"]` and `channel["guild_id"]` (display label includes guild context when non-null)
  - Role chips read `role["role_id"]` and `role["guild_id"]` similarly
  - All chip-removal logic finds entries by `id` field instead of by string equality
- [x] **Legacy-entry indicator** for null-guild_id channels + roles:
  - DOM: a visual indicator (icon + tooltip) on each chip with `guild_id === null` reading something like "Legacy entry — applies to any server"
  - DOM has `data-testid="connector-allowlist-channel-legacy-indicator-{channel_id}"` (or similar pattern for roles) for browser tests
  - Tooltip text references the migration (e.g. "Pre-v24 entry — guild context not stored")
  - Optional "Re-scope to current guild" affordance (a button on the chip OR a contextual action) — implementer's call; defer if scope-creepy
- [x] **`discoverable-dropdown.js` emits structured tuples**:
  - On channel selection: emits `{guild_id: <selected-guild>, channel_id: <selected-channel-id>}` to the allowlist state (instead of bare `channel_id` string)
  - On role selection: emits `{guild_id: <selected-guild>, role_id: <selected-role-id>}` similarly
  - On peer selection (if peers use the discoverable dropdown — verify at implementation): emits `{id: <peer_id>, dm_allowed: false}` (safe default)
  - Existing chip-render code in `discoverable-dropdown.js` reads structured shape on render
- [x] **`agent-editor.js` per-agent overlay** in Connectors tab mirrors the structured-tuple rendering:
  - Per-agent `peers` overlay shows the same peer structured-tuple shape
  - Per-agent `channels` + `roles` overlays show the same structured-tuple shape
  - Per-axis-tri-state-override semantics preserved (inherit / explicit-list / empty)
  - Per-agent peer DM toggle is NOT consulted by ACL (per L3 spec) — UI may show it grayed-out OR omit it entirely. Recommend OMIT for per-agent overlay (the field exists in storage for structural-uniformity but has no semantic) — render a note like "DM admission is account-scope only"
  - Per-agent `admit_dms` tri-state STAYS as-is (no L4 changes to this control)
- [x] **CSS (if needed)** in `studio.css`: add styles for `.connector-allowlist-peer-dm-toggle` (or similar class for the per-peer toggle) + `.connector-allowlist-legacy-indicator`. Match existing connector-editor styling patterns.
- [x] **10+ existing browser tests updated** for new shape: fixture data + assertion strings reflect structured-tuple shape. Tests pinning the OLD `"allowlisted-peers-only"` Literal value updated to `"admin-approved"`.
- [x] **`tests/browser/test_flow_studio_connector_dm_admission_row.py` updated** (per F12 spec edge case): the test currently exercises 3 mode-buttons; revise to assert the renamed Literal value `"admin-approved"` AND extend to verify per-peer DM toggle conditional rendering (visible under `admin-approved`, hidden under `all`/`none`).
- [x] **4-8 new browser tests added**:
  - `test_per_peer_dm_toggle_visible_only_under_admin_approved` — switching dm_admission to/from `admin-approved` shows/hides the per-peer toggle
  - `test_per_peer_dm_toggle_persists_on_save` — toggling + save round-trips the boolean
  - `test_channel_legacy_indicator_renders_for_null_guild_id` — a connector with a legacy channel entry shows the indicator
  - `test_role_legacy_indicator_renders_for_null_guild_id` — same for roles
  - Plus 1-4 more covering edge cases discovered during implementation
- [x] **Phase 5c architect cycle for L4** (pre-implementation): an architect agent re-runs the browser-test grep against the live codebase post-L3 and enumerates the exact per-file diff scope. If new browser tests need to be added beyond the 4-8 sketched above, fold into L4 scope.
- [x] **Browser test suite green** (unblocks the post-L3 degradation per cycle-1 finding): `docker exec the-one pytest tests/browser/ -m browser -x --timeout 120` shows all renamed/new tests pass; the 2 pre-existing-main failures persist (not F12-caused). Total browser pass count: ~435-445 (431 baseline + 4-8 new tests + 0 net from updates). **Post-L3 the dm_admission_row test fails 2-of-3 cases AND any other test POSTing the old Literal value also fails — L4 unblocks all of these by fixing fixtures + UI atomically.**
- [x] **POST-fixture audit across all 10 allowlist-touching browser tests** (cycle-1 finding): every test file in the Step 5 list is audited for fixtures that POST the OLD shape (`"allowlisted-peers-only"` Literal OR flat-string peers/channels/roles). Audit checklist:
  - `grep -rnE '"allowlisted-peers-only"' tests/browser/` returns 0 hits post-L4
  - `grep -rn 'connector.*config.*allowlist.*peers.*\["' tests/browser/` (flat-shape peers POST) returns 0 hits
  - The 5 known hits at pre-L4 grep time (4 in dm_admission_row.py + 1 docstring in per_agent_admit_dms.py) all updated to `"admin-approved"`
- [x] **Broad backend regression**: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` is green at 2767+ passing (no backend changes in L4; same baseline as L3).
- [x] Flight log `Leg Progress` section has an L4 entry summarizing UI changes + browser test updates + test results.
- [x] Leg status updated to `landed` in this file's header. **DO NOT commit** — Phase 2d batches commits.

## Verification Steps

1. **Backend regression** (no L4 backend changes; baseline preserved):
   - `docker exec the-one pytest --ignore=tests/browser -x --timeout 60`
   - Expect: 2767+ passing / 4 skipped / 0 errors / 0 failures.

2. **Browser test suite** (the critical regression net for L4):
   - `docker exec the-one pytest tests/browser/ -m browser -x --timeout 120`
   - Expect: 435-445 passing / 35 skipped / 14 deselected / 2 pre-existing-main failures persist.
   - All updated tests + new tests pass.

3. **Manual smoke test** (optional but operator-confirming):
   - Open running app at http://localhost:8484/studio
   - Open a Discord connector's editor
   - Verify dm_admission select shows "Admin-approved (per-peer)" option (not "Admit DMs from approved peers")
   - Set to "Admin-approved (per-peer)" → per-peer DM toggle appears on each peer chip
   - Set to "Admit all DMs" → per-peer toggle hides
   - Set to "Deny all DMs" → per-peer toggle hides
   - For a connector with legacy channel entries (post-v24 with null guild_id), legacy indicator appears on those chips

4. **DOM verification** (browser test assertion sanity):
   - Inspect peer chip: `data-testid="connector-allowlist-peer-dm-toggle-{peer_id}"` exists when dm_admission=admin-approved
   - Inspect legacy channel chip: `data-testid="connector-allowlist-channel-legacy-indicator-{channel_id}"` exists

## Implementation Guidance

**Order matters.** Update the JS rendering FIRST (so the editor handles the structured shape post-L3 storage), then update browser test fixtures + add new tests, then run tests. Order keeps the editor functional throughout.

### Step 1 — `connector-editor.js` updates

**Step 1a — dm_admission select Literal-value update**: locate the dm_admission select at lines 2055-2090. Update:
- `account.config.allowlist.dm_admission) || 'allowlisted-peers-only'` (line 2055) → `... || 'admin-approved'`
- `<option value="allowlisted-peers-only"` (line 2071) → `<option value="admin-approved"`
- Visible label `Admit DMs from approved peers` → `Admin-approved (per-peer)`
- `currentDmAdmission === 'allowlisted-peers-only'` (line 2072) → `currentDmAdmission === 'admin-approved'`
- Verify ALL occurrences of `'allowlisted-peers-only'` in the file are updated (grep `grep -n "allowlisted-peers-only" connector-editor.js` should return 0 post-step).

**Step 1b — Peer chip rendering** for structured `{id, dm_allowed}` shape:
- Locate the chip-rendering logic for peers (likely in a shared `renderChipList()` or similar function). Currently chips have `data-id={peer_id}` (line ~160 of discoverable-dropdown.js as reference); peer entries in `allowlistState.peers` are now dicts, not strings.
- Update chip render: read `peer["id"]` for the chip's `data-id` and visible label; the chip-removal logic finds entries by matching `entry["id"] === removedId` instead of `entry === removedId`.

**Step 1c — Per-peer DM toggle rendering** (CONDITIONAL):
- After rendering each peer chip, render the DM toggle if `currentDmAdmission === 'admin-approved'`.
- Render shape: a small checkbox (`<input type="checkbox">`) positioned within or adjacent to the chip. **CSS precedent (cycle-1 corrected)**: studio.css:1089 comment notes `.connector-allowlist-switch` was deleted as orphaned; use `.tool-enable-switch` inline default OR style new `.connector-allowlist-peer-dm-toggle` class. The `.connector-allowlist-chiplist` / `.connector-allowlist-row` families (studio.css:1162-1300) are the right styling neighborhood for layout.
- DOM: `<input type="checkbox" data-testid="connector-allowlist-peer-dm-toggle-{peer_id}" ...>` (or appropriate element per UX choice)
- Wire change handler: `allowlistState.peers[i].dm_allowed = newValue` then trigger save-or-debounced-save per the existing pattern (same as the chip-remove handler's save pattern).
- **Visibility toggle wiring (cycle-1 explicit guidance)**: there is NO existing studio-event-bus event for dm_admission changes. The dm_admission `<select>` at lines 2066-2076 has no current change handler. The implementer MUST add a new `change` event listener on `#connector-allowlist-dm-admission-select` that either: (a) calls the existing peers-section re-render function, OR (b) toggles a parent class on the peers section (e.g. `peersSection.classList.toggle('dm-admission-admin-approved', currentDmAdmission === 'admin-approved')`) and CSS controls visibility via that class. **Recommend (b)** — CSS-toggle path preserves checkbox state across the toggle (operator flips dm_admission back to admin-approved without losing their per-peer toggles' values).

**Step 1d — Channel + role chip rendering** for structured tuples:
- Channels: read `channel["channel_id"]` for data-id + visible label. Include `channel["guild_id"]` in the label when non-null (e.g., display "#general (Guild ABC)").
- Roles: read `role["role_id"]` similarly.
- Removal logic: match by `entry["channel_id"]` / `entry["role_id"]` (not by string equality).

**Step 1e — Legacy-entry indicator** for null-guild_id channels/roles:
- For each channel/role chip where `entry["guild_id"] === null`, render a visual indicator (e.g. a small icon prepended or appended to the chip label) with `data-testid="connector-allowlist-channel-legacy-indicator-{channel_id}"` (or `role-`).
- Tooltip text: "Pre-v24 entry — guild context not stored. Re-scope by removing + re-adding via the dropdown."
- Optional "Re-scope to current guild" affordance: defer if scope-creepy; if implemented, render as a small inline button that triggers a re-scope dialog.

**Step 1f — Save shape update**: locate the save-handler (lines 1599-1612 reference per L4 design recon). Verify the saved shape matches L3's Pydantic validator expectations (cycle-1 added `guilds`):
```js
{
  peers: allowlistState.peers,         // already in {id, dm_allowed} shape after L1c
  channels: allowlistState.channels,   // already in {guild_id, channel_id} shape after L1d
  guilds: allowlistState.guilds,        // unchanged shape (list[str] — guilds is flat at substrate)
  roles: allowlistState.roles,         // already in {guild_id, role_id} shape after L1d
  dm_admission: allowlistState.dm_admission  // post-1a now sends 'admin-approved'
}
```

### Step 2 — `discoverable-dropdown.js` emit-shape update

- On channel selection in the dropdown: emit `{guild_id: <selected-guild-id>, channel_id: <selected-channel-id>}`. Determine `selected-guild-id` from the dropdown's context (it already groups by server per F11 — the guild_id is available at the option-selection moment).
- On role selection: emit `{guild_id: <selected-guild-id>, role_id: <selected-role-id>}` similarly.
- On peer selection: emit `{id: <peer-id>, dm_allowed: false}` (safe default; operator flips via the per-peer toggle in Step 1c).
- Chip render logic inside `discoverable-dropdown.js` itself: reads structured shape if it's also responsible for displaying selected chips (verify at implementation — may delegate to the parent editor).

### Step 3 — `agent-editor.js` per-agent overlay updates

Per-agent overlay in Connectors tab mirrors the L3 storage shape:
- Peers overlay reads `{id, dm_allowed}` shape — but per-agent `dm_allowed` is NOT consulted by ACL (per L3 spec). Recommend: per-agent peer overlay omits the DM toggle entirely; render a one-line note "DM admission is account-scope only" near the peers section header.
- Channels overlay: same structured-tuple shape as account-scope; legacy indicator applies.
- Roles overlay: same.
- Per-axis-tri-state-override semantics preserved: per-agent `peers: None | [] | [items]` → inherit / explicit-empty / narrow. The UI already handles the tri-state for the flat shape; structured shape is just an entry-format change.
- `admit_dms` per-agent tri-state UI control STAYS unchanged.

### Step 4 — CSS updates (if needed)

Add styles for new elements if the existing connector-editor styling doesn't cover them. Likely additions:
- `.connector-allowlist-peer-dm-toggle` — small inline toggle/checkbox, positioned near peer chip
- `.connector-allowlist-legacy-indicator` — small icon with hover tooltip, distinct visual treatment (e.g. dashed border on chip, info-icon color)
- Update existing classes if needed for the per-peer-toggle's conditional visibility

### Step 5 — Browser test fixture updates

Pre-implementation Phase 5c grep:
```bash
grep -rln "allowlist\|dm_admission\|admit_dms\|dm_allowed" tests/browser/ --include='*.py'
```
Expected: 10 files identified at L4 design time. Verify hit count + per-file diff scope before implementation.

For each test file, update:
- Test fixtures that POST connector config with old shape — update to structured shape
- Test assertions that read DOM with old testids — update to new testids
- Tests that pin the old Literal value `"allowlisted-peers-only"` — update to `"admin-approved"`

The 10 files (per L4 design recon):
- `test_flow_studio_connector_dm_admission_row.py` — extend per AC for per-peer toggle conditional render
- `test_flow_studio_connector_allowlist_dropdown.py` — chip/dropdown shape updates
- `test_flow_studio_connector_discoverable_dropdown.py` — emit-shape verification
- `test_flow_studio_per_agent_admit_dms.py` — preserve per-agent admit_dms semantics; verify no per-agent dm_allowed UI
- `test_flow_studio_per_agent_overlay_dropdown.py` — per-agent overlay structured shape
- `test_flow_studio_per_agent_overlay_label_resolver.py` — structured-shape label resolution
- `test_flow_studio_connector_routing_dropdown.py` — verify no regression
- `test_flow_studio_connector_discord_vocabulary.py` — verify dm_admission label revision picks up vocabulary
- `test_flow_chat_pending_approval.py` — verify approve flow constructs new peer shape
- `test_flow_admin_tools_editor.py` — verify no regression

### Step 6 — Add 4-8 new browser tests

Author 4 mandatory + up to 4 discretionary tests covering:
1. `test_per_peer_dm_toggle_visible_only_under_admin_approved` — switching dm_admission select; assert toggle visibility
2. `test_per_peer_dm_toggle_persists_on_save` — toggle a peer's dm_allowed; save; reload; verify state
3. `test_channel_legacy_indicator_renders_for_null_guild_id` — seed a connector with structured channel entries (one with `guild_id: null`); verify indicator renders on that chip only
4. `test_role_legacy_indicator_renders_for_null_guild_id` — same for roles

Optional (4 more):
5. `test_per_peer_dm_toggle_hidden_under_all_mode` — explicit-hidden verification
6. `test_per_peer_dm_toggle_hidden_under_none_mode` — explicit-hidden verification
7. `test_legacy_indicator_tooltip_text` — hover/screen-reader text assertion
8. `test_per_agent_overlay_omits_dm_toggle` — per-agent overlay does NOT show per-peer DM toggle (it's account-scope only per L3 spec)

### Step 7 — Run tests

```bash
# Backend (must remain at L3 baseline; no L4 backend changes):
docker exec the-one pytest --ignore=tests/browser -x --timeout 60

# Browser (the critical L4 regression net):
docker exec the-one pytest tests/browser/ -m browser -x --timeout 120
```

Expected backend: 2767+ / 4 / 0 errors. Expected browser: 435-445 passing + 2 pre-existing-main failures.

### Step 8 — Update flight log and leg status

- Append entry to `../flight-log.md` under `## Leg Progress` summarizing: dm_admission Literal-value UI update, per-peer toggle conditional rendering, structured-tuple chip rendering, legacy indicator, discoverable-dropdown emit-shape update, per-agent overlay updates, ~10 browser test updates + 4-8 new tests, test results.
- Update this leg artifact's header `**Status**: in-flight` → `**Status**: landed`.
- Do NOT update the flight-spec leg checkbox (commit leg does that).
- Do NOT commit. Do NOT `git add`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Empty peers list under admin-approved mode**: per-peer toggle has nothing to render. UI shows just the empty peers chiplist + the dm_admission select; no toggles. Verify in `test_per_peer_dm_toggle_visible_only_under_admin_approved` that toggle DOM elements only exist when peers are present.
- **dm_admission switched mid-edit (before save)**: operator changes dm_admission from `admin-approved` to `none` without saving; per-peer toggles should hide live. Implementer must wire a re-render OR a CSS class toggle on dm_admission change. Browser test verifies.
- **Legacy entry "Re-scope to current guild" affordance**: **EXPLICITLY OUT OF L4 SCOPE** (cycle-1 suggestion to remove implementer-ambiguity). Operators can re-scope by removing the legacy chip and re-adding via the dropdown. If a future flight wants the affordance as a one-click action, file as known issue.
- **Per-agent overlay UX**: per L3 spec, per-agent `peers[*].dm_allowed` is NOT consulted by ACL. UI should NOT show per-peer DM toggles in the per-agent overlay. The note "DM admission is account-scope only" prevents operator confusion.
- **Browser test fixture shapes**: tests that POST connector config in old shape will now fail Pydantic validation post-L3. Update fixtures to structured shape OR use a fixture helper (similar to L3's `_to_v24_shape()` for backend tests).
- **`docker-compose.yml` discipline (unchanged)**: continues; explicit `git add` only.
- **JS file size**: `connector-editor.js` is currently 3590 LOC; L4 adds maybe 100-200 LOC. The agents.md convention `cross-flight-ux-debt-reconciliation` (line 315) flags JS file growth; if L4 pushes the file past some threshold the implementer judges as readability-impacting, defer the per-agent overlay UI changes to a follow-up (but that creates per-leg-debt — not preferred).

## Files Affected

**Frontend** (3-4 files):
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — main allowlist editor updates (~100-150 LOC change)
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — emit-shape updates (~30-50 LOC change)
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — per-agent overlay updates (~30-80 LOC change)
- `the_one/interfaces/web/static/css/studio.css` (if needed) — new styles for per-peer toggle + legacy indicator

**Browser tests** (10+ files):
- 10 existing files updated per Step 5 list
- 4-8 new tests added (likely as new test methods in existing files OR a new `test_flow_studio_per_peer_dm_toggle.py` file)

**Flight artifacts**:
- `missions/11-discord-connector-depth/flights/12-hierarchical-allowlist-and-snake-case-rename/flight-log.md` — append L4 progress entry
- This file (`legs/04-ui-discoverable-dropdown-and-per-peer-dm-toggle.md`) — status → `landed`

**Explicitly NOT affected in L4**:
- Any Python file (L3 owns the backend; L4 is frontend-only)
- `tests/test_*.py` non-browser tests (L3 updated all backend fixtures)
- `the_one/db/schema.py` (L3's v24 already landed)
- `docker-compose.yml` (operator's local dev state)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (UI updates, conditional rendering, legacy indicator, browser tests green)
- [x] L4 atomicity boundary verified (no backend / no non-browser tests touched)
- [x] Backend baseline preserved at 2767+ passing
- [x] Browser suite green at 435-445 passing
- [x] Flight-log L4 progress entry appended
- [x] This leg's status set to `landed` (NOT `completed` — Phase 2d commits)
- [x] Do NOT update flight-spec leg checkbox (commit leg does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d batches all 4 legs into one review + one commit)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-29, leg-design time, post-L3):

| Citation | Classification | Resolution |
|----------|---------------|------------|
| `connector-editor.js:2055-2090` — dm_admission select rendering | OK | Verified by reading; Literal value `'allowlisted-peers-only'` at :2055, :2071-2072; visible label `"Admit DMs from approved peers"` at :2072 |
| `connector-editor.js:1599-1612` — save shape | OK | Verified by reading; current save sends `dm_admission: allowlistState.dm_admission` (string passes-through) |
| `connector-editor.js` size 3590 LOC | OK | Verified via `wc -l` |
| `discoverable-dropdown.js` chip-render with `data-id` at lines ~160 | OK | Verified by reading; uses flat string IDs currently |
| `agent-editor.js` Connectors tab panel ID `agent-tab-panel-connectors` (line 49) | OK | Verified by reading PANEL_IDS |
| 10 browser tests touching allowlist + dm_admission + admit_dms + dm_allowed | OK | Verified by `grep -rln tests/browser/` returning exactly 10 files |
| `tests/browser/test_flow_studio_connector_dm_admission_row.py` existence | OK | File exists at expected path |
| L3 baseline 2767 passing / 0 errors | OK (from L3 implementer report) | Implementer report confirmed 2767 passed |
| Browser baseline 431 passed + 2 pre-existing failures | OK | Per F11 + L1 + L2 + L3 verification |
| CSS classes `.connector-allowlist-*` exist in studio.css | OK | Verified — multiple existing classes; styling pattern established |

10 citations verified clean against current code at leg design time. All references match live post-L3 state. The Phase 5c architect cycle pre-implementation will re-verify the browser-test surface for any drift.
