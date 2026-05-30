# Leg: hierarchical-server-parent-ui

**Status**: completed
**Flight**: [Hierarchical Allowlist Axes + Snake_Case Identifier Rename](../flight.md)

## Objective

Restructure the connector allowlist editor so **Servers (guilds) become the parent organizer** with **channels + roles rendered as sub-controls (chicklets) under each server row** — replacing the L4 flat-three-sections layout (Servers / Channels / Roles separate). Substrate enforces server-first: schema migration v25 deletes orphaned null-guild_id channel/role entries (legacy from v24's nullable backfill); Pydantic validator post-v25 rejects null guild_id; new `"*"` sentinel value for `channel_id` / `role_id` means "all channels/roles of this guild" — added automatically when a server is allowlisted without explicit narrowing; ACL helpers updated for wildcard semantics + cross-product matrix extended. UI: connector-editor.js allowlist section + connectors-tab.js per-agent overlay both restructured to the hierarchical Server-parent layout. L4's legacy-entry indicator removed (no more legacy entries post-v25).

## Context

This is the fifth leg in F12, added as a post-land extension per operator decision (2026-05-30). L1-L4 committed as `eb7f04d` (50 files / 5707 ins / 522 del); F12 was status `landed` then flipped back to `in-flight` to accommodate L5 per the agentic-workflow mid-execution-pivot guidance.

**Operator decisions at L5 planning** (recorded in flight-log FD note):
- **Server-required-for-channel/role: ENFORCED**. The dropdown for channels + roles only appears within a server row context; no orphaned (server-less) channels or roles. UI does not offer the option.
- **Legacy entries (null guild_id from v24 migration): AUTO-DELETED in migration v25**. Operator framing: "app is not live, just enforce going forward." No data preservation needed.
- **Empty server row semantic**: server added to `guilds` list AND explicit `{guild_id, channel_id: "*"}` / `{guild_id, role_id: "*"}` sentinel markers in the structured-tuple lists. The `"*"` wildcard means "any channel of this guild" / "any role of this guild" — preserves the current per-axis-tri-state-override "absent axis = unrestricted" intent but at the per-guild scope instead of the global scope.
- **Flight scope: L5 on F12**. Cleaner than F13 since F12 isn't merged yet; the hierarchical-axes substrate (L3) ships WITH the hierarchical UI (L5) in a single flight + single PR.

**L4 baseline at L5 design time** (post-`eb7f04d`):
- Backend: 2767 passed / 4 skipped / 0 errors / ~248s wall
- Browser: 438 passed / 35 skipped / 2 pre-existing-main failures
- L4's UI shows 3 separate flat sections (Servers / Channels / Roles) with guild_id labels on channel/role chips and a legacy-entry indicator for null-guild_id chips
- L4 added `test_flow_studio_per_peer_dm_toggle.py` with 7 tests including 2 legacy-indicator tests — L5 will need to retire or rework those 2 tests since post-v25 there are no legacy entries to indicate

## Inputs

- F12 L1-L4 committed locally as `eb7f04d` on branch `flight/12-hierarchical-allowlist-and-snake-case-rename`. NOT pushed.
- Backend baseline post-L4: 2767 passed / 4 skipped / 0 errors / ~248s wall
- Browser baseline post-L4: 438 passed / 35 skipped / 2 pre-existing-main failures (carried since pre-F10)
- `_acl.py` post-L3 (575 LOC after L2 extraction + L3 helper updates) — 4 helpers consume the structured-tuple shape
- `the_one/db/schema.py` v24 block at lines 1158-1356 (post-L3); v25 inserts AFTER v24
- `the_one/db/models.py` allowlist validator (post-L3) — accepts `{guild_id: str | None, channel_id: str}` / `{guild_id: str | None, role_id: str}`; L5 tightens to reject null guild_id
- `the_one/agent/config.py` `_validate_connector_acls` (post-L3) — same structured-shape validator; mirrors account-scope tightening
- `connector-editor.js` post-L4 (~3590 LOC + L4 changes) — flat 3-section allowlist editor
- `discoverable-dropdown.js` post-L4 — emits structured tuples with valueShape opt-in
- `connectors-tab.js` post-L4 — per-agent overlay surface with structured-tuple shape
- `tests/browser/test_flow_studio_per_peer_dm_toggle.py` post-L4 — 7 tests including 2 legacy-indicator tests due for retirement
- Uncommitted operator dev state: `docker-compose.yml` (unchanged from L1-L4; stays unstaged)

## Outputs

- Schema migration v25 added to `the_one/db/schema.py` after v24 — deletes orphaned null-guild_id channel/role entries from `connectors.config.allowlist` AND `agents.connector_acls`; idempotent
- Pydantic validators in `models.py` + `agent/config.py` tightened: reject null guild_id for channels/roles; accept new wildcard `"*"` for channel_id/role_id
- ACL helpers in `_acl.py` updated for wildcard semantics: `channel_id === "*"` admits any channel matching guild_id; `role_id === "*"` admits any role matching guild_id (subject to `member_roles` overlap with non-wildcard entries in the same guild). Mirror update in `admits_outbound` per `two-symmetric-paths-in-acl` convention.
- Cross-product matrix in `test_connectors_acl.py` extended with wildcard cells
- `TestSchemaV25` class added to `test_db_migration.py` (3+ tests: orphan deletion + idempotency + post-v25 validator rejection)
- `connector-editor.js` allowlist section restructured: Servers section as parent organizer; nested Channels + Roles chiplists per server row; server-scoped channel/role dropdowns; "remove server" cascades; default `(all channels)` + `(all roles)` sentinel chips when server added empty
- `connectors-tab.js` per-agent overlay mirrors hierarchical layout
- L4's legacy-entry indicator code removed (no more legacy entries post-v25)
- `test_flow_studio_per_peer_dm_toggle.py` — 2 legacy-indicator tests retired or reworked
- New/updated browser tests for hierarchical layout: server row rendering + nested chiplists + server-scoped dropdowns + cascade-delete + sentinel rendering
- Flight log L5 progress entry appended
- Leg status `landed` (NOT committed in-leg — Phase 2d-redux commits)

## Acceptance Criteria

### Substrate (Schema v25 + Pydantic + ACL)

- [x] **Schema migration v25 added** to `the_one/db/schema.py` after the v24 block. v25 must:
  - Row-rewrite `connectors.config.allowlist`: delete entries from `channels` and `roles` lists where `guild_id is None` (orphans from v24 backfill). Preserve all other entries.
  - Row-rewrite `agents.connector_acls`: same deletion across each per-account payload.
  - Idempotent (`if version < 25:` guard; per-row UPDATE-only-when-changed gives natural no-op on re-run — no separate segment marker needed unlike v21's CREATE INDEX).
  - Transactional; `INSERT OR IGNORE INTO schema_version` LAST.
- [x] **`TestSchemaV25` class added** to `tests/test_db_migration.py` (after TestSchemaV24) with 3+ tests:
  - `test_v25_deletes_orphan_null_guild_id_channels_and_roles` — seed v24 row with mix of null-guild_id + structured entries; verify orphans deleted, structured preserved
  - `test_v25_idempotent_on_rerun` — already-v25 DB applies cleanly
  - `test_v25_agents_connector_acls_orphan_deletion` — same for the per-agent payload
- [x] **Pydantic validator tightened** in `the_one/db/models.py` and `the_one/agent/config.py`:
  - Channel/role entries must have non-null `guild_id: str` (was `str | None`)
  - Wildcard `channel_id == "*"` and `role_id == "*"` are accepted (sentinel for "all of this guild")
  - Test added in `test_db_repositories.py` (or `test_connectors_*`) confirming null-guild_id channel rejected with clear error message
- [x] **ACL helpers updated** in `the_one/connectors/_acl.py` for wildcard semantics:
  - `_admits_inbound_guild`: when iterating channels, if `c["channel_id"] === "*"`, admit any channel matching `c["guild_id"] === envelope_guild_id`. Same wildcard handling for roles: `r["role_id"] === "*"` admits regardless of `member_roles` membership (but still requires `r["guild_id"] === envelope_guild_id`).
  - `admits_outbound` mirror update per `two-symmetric-paths-in-acl` convention: same wildcard channel semantic (match channel_id alone per L3's outbound rule; wildcard `"*"` matches any channel_id of any guild — since outbound ignores guild_id, the wildcard simply admits unconditionally for channels in the list).
  - Helper docstrings updated to document the wildcard semantic.
- [x] **Cross-product matrix extended** in `test_connectors_acl.py` with 4+ wildcard cells covering:
  - `channel_id="*"` + matching `guild_id` + non-DM envelope → admit
  - `channel_id="*"` + non-matching `guild_id` + non-DM envelope → deny (still guild-scoped)
  - `role_id="*"` + matching `guild_id` + any `member_roles` → admit
  - Combination cells if useful

### UI (connector-editor.js + connectors-tab.js)

- [x] **Allowlist editor restructured** in `connector-editor.js`: Channels + Roles sections no longer appear as siblings of Servers. Instead, Servers section becomes the parent organizer:
  ```
  Servers section:
    [+ Add server] dropdown
    Server row: "Guild ABC" [remove]
      Channels (sub-chiplist): [chip] [chip] [+ add channel ▼]
      Roles (sub-chiplist):    [chip] [chip] [+ add role ▼]
    Server row: "Guild XYZ" [remove]
      Channels: ...
      Roles: ...
  ```
- [x] **Server-scoped dropdowns**: when the operator opens a channel or role dropdown inside a server row, the dropdown is filtered to show only entities from that server. Implementer wires the `guild_id` context to the discoverable-dropdown invocation.
- [x] **Default sentinel insertion** when a server is added without explicit channel/role narrowing: storage shape is `channels: [..., {guild_id: "guild-abc", channel_id: "*"}]` and `roles: [..., {guild_id: "guild-abc", role_id: "*"}]`. UI renders these as visually-distinct chips labeled "(all channels)" / "(all roles)" with a `data-testid="connector-allowlist-channels-wildcard-{guild_id}"` (or similar).
- [x] **Pre-L5 empty-server-row rendering rule** (locked per architect cycle-1 low-1): UI renders the sentinel chip for ANY server row whose channels list is empty for that guild_id, regardless of pre-/post-L5 origin. Operator sees a consistent UI state. v25 migration does NOT auto-insert sentinels for legacy rows (operator state preserved as storage-level "no narrowing"); the UI renders the wildcard on display. New server additions DO insert sentinels at storage-write time. Same rule applies for roles.
- [x] **Sentinel removal**: when the operator adds an explicit channel/role to a server's chiplist, the corresponding `"*"` sentinel is removed. When all explicit channels/roles are removed from a server's chiplist (so it would be empty), the sentinel is re-inserted (preserves "(all channels)" intent).
- [x] **Cascade-delete**: when a server row is removed, all channel + role entries with matching `guild_id` are deleted from the lists (including any `"*"` sentinels). Server-row "remove" affordance does this atomically.
- [x] **Legacy-entry indicator removed** from `connector-editor.js` and `connectors-tab.js` (no more null-guild_id entries post-v25). Code paths handling null-guild_id-display are deleted, not just commented out.
- [x] **Per-agent overlay in `connectors-tab.js` mirrors hierarchical layout**: same Server-as-parent structure for the per-agent overlay; preserve the per-axis-tri-state-override semantics (inherit / explicit-list / empty). Per-agent `peers[*].dm_allowed` still not consulted by ACL per L3 spec (carry-forward).
- [x] **CSS updates** in `studio.css` for nested chiplist layout — indentation of server rows' children, visual distinction between server row + sub-controls, sentinel-chip styling.
- [x] **Save shape verified**: post-L5 save sends structured tuples with non-null `guild_id` for all channel/role entries; the wildcard `"*"` is in `channel_id` / `role_id` not in `guild_id`. Server presence in `guilds` list is independent of channel/role presence.

### Tests (Browser + L4 retirement)

- [x] **2 L4 legacy-indicator tests retired or reworked**:
  - `test_channel_legacy_indicator_renders_for_null_guild_id` — DELETE (no more legacy entries post-v25)
  - `test_role_legacy_indicator_renders_for_null_guild_id` — DELETE
  - OR rework into: `test_pre_v25_legacy_entries_deleted_by_migration` (migration regression test in `test_db_migration.py`, NOT browser) — implementer's call; migration regression test is cheaper
- [x] **New browser tests** in a new `test_flow_studio_hierarchical_server_rows.py` (or extension of `test_flow_studio_connector_allowlist_dropdown.py`):
  - `test_server_row_renders_with_nested_channels_and_roles` — visual structure of a server row
  - `test_add_channel_via_server_row_dropdown` — server-scoped dropdown picks correct channel
  - `test_remove_server_cascades_channel_and_role_chips` — cascade-delete behavior
  - `test_server_added_without_explicit_children_shows_wildcard_sentinel_chips` — `(all channels)` / `(all roles)` rendering
  - `test_per_agent_overlay_uses_same_hierarchical_layout` — connectors-tab.js parity
  - Optional: 2-4 more covering wildcard chip removal, edge cases
- [x] **POST-fixture audit across all browser tests**:
  - `grep -rnE '"guild_id":\s*null' tests/browser/` returns 0 hits post-L5 (no more null-guild_id fixtures)
  - `grep -rnE 'channel_id":\s*"\*"' tests/browser/` returns at least 1 hit (new wildcard fixtures)
- [x] **Backend regression**: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` is green at 2770+ passing (L4 baseline 2767 + ~3 new TestSchemaV25 + cross-product matrix wildcard cells). Wall-clock within 10% of L4 baseline.
- [x] **Browser test suite green**: `docker exec the-one pytest tests/browser/ -m browser -x --timeout 120` at ~440-450 passing (438 baseline - 2 retired + 5-8 new = 441-444). 2 pre-existing-main failures persist.
- [x] Flight log `Leg Progress` section has an L5 entry summarizing v25 migration + UI restructure + test results.
- [x] Leg status updated to `landed` in this file's header. **DO NOT commit** — Phase 2d-redux batches commit onto F12 branch.

## Verification Steps

1. **Migration test suite**: `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30` — expect green; new TestSchemaV25 (3+ tests) passes.

2. **ACL test suite**: `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30` — expect green at L4 baseline + new wildcard matrix cells.

3. **Broad backend suite**: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` — expect 2770+ / 4 skipped / 0 errors.

4. **Browser suite**: `docker exec the-one pytest tests/browser/ -m browser -x --timeout 120` — expect 441-444 passing + 2 pre-existing-main failures.

5. **Grep verification gates**:
   - `grep -rnE '"guild_id":\s*null' tests/browser/` → 0 hits (no legacy fixtures)
   - `grep -rnE 'guild_id":\s*null' the_one/db/schema.py` → may have hits in v24 body (acceptable — that's the FROM side of v25's deletion); 0 hits in v25 body
   - `git grep -nE "connector-allowlist-channel-legacy-indicator\|connector-allowlist-role-legacy-indicator" the_one/ tests/` → 0 hits (L4 legacy indicator removed)

6. **Manual smoke test** (optional but operator-confirming):
   - Open connector editor at http://localhost:8484/studio
   - Add a server → server row renders with `(all channels)` + `(all roles)` sentinel chips
   - Add a specific channel from the server's dropdown → sentinel removed, explicit chip added
   - Remove the explicit channel → sentinel re-inserted (or chiplist becomes empty + sentinel; implementer choice — verify behavior matches AC)
   - Remove the server row → all channel + role chips with that guild_id deleted
   - Verify per-agent overlay in Agent editor → Connectors tab uses same hierarchical layout

## Implementation Guidance

**Order matters.** Substrate FIRST (migration + validator + ACL helpers + backend tests), THEN UI (connector-editor + connectors-tab + browser tests). This minimizes the time the editor renders against an unmigrated DB.

### Step 1 — Schema migration v25 + validator tightening

Add `if version < 25:` block to `the_one/db/schema.py` after the v24 block (which ends at line ~1356 with `version = 24`). Body shape (offline-safe, no network):

```python
if version < 25:
    # Mission 11 Flight 12 Leg 5: hierarchical server-parent UI alignment —
    # delete orphaned null-guild_id channel/role entries (legacy from v24's
    # permissive backfill). Operator framing at L5 planning: app is not
    # live, just enforce going forward; the discoverable-dropdown UI will
    # always emit guild_id-scoped tuples post-L5.
    import json as _json
    
    # ---- Delete orphan null-guild_id from connectors.config.allowlist ----
    async with conn.execute("SELECT id, config FROM connectors") as cursor:
        connector_rows = await cursor.fetchall()
    for row in connector_rows:
        config_str = row["config"] or "{}"
        config = _json.loads(config_str)
        allowlist = config.get("allowlist")
        if allowlist is None:
            continue
        changed = False
        if "channels" in allowlist:
            original = allowlist["channels"]
            filtered = [c for c in original if c.get("guild_id") is not None]
            if len(filtered) != len(original):
                allowlist["channels"] = filtered
                changed = True
        if "roles" in allowlist:
            original = allowlist["roles"]
            filtered = [r for r in original if r.get("guild_id") is not None]
            if len(filtered) != len(original):
                allowlist["roles"] = filtered
                changed = True
        if changed:
            config["allowlist"] = allowlist
            await conn.execute(
                "UPDATE connectors SET config = ? WHERE id = ?",
                (_json.dumps(config), row["id"]),
            )
    
    # ---- Same for agents.connector_acls ----
    async with conn.execute("SELECT name, connector_acls FROM agents") as cursor:
        agent_rows = await cursor.fetchall()
    for row in agent_rows:
        acls_str = row["connector_acls"]
        if not acls_str:
            continue
        acls = _json.loads(acls_str)
        changed = False
        for acct_id, payload in acls.items():
            if "channels" in payload and isinstance(payload["channels"], list):
                original = payload["channels"]
                filtered = [c for c in original if c.get("guild_id") is not None]
                if len(filtered) != len(original):
                    payload["channels"] = filtered
                    changed = True
            if "roles" in payload and isinstance(payload["roles"], list):
                original = payload["roles"]
                filtered = [r for r in original if r.get("guild_id") is not None]
                if len(filtered) != len(original):
                    payload["roles"] = filtered
                    changed = True
        if changed:
            await conn.execute(
                "UPDATE agents SET connector_acls = ? WHERE name = ?",
                (_json.dumps(acls), row["name"]),
            )
    
    await conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (25,)
    )
    await conn.commit()
    version = 25
```

Then tighten Pydantic validators:
- `the_one/db/models.py` allowlist validator: change channel entry's `guild_id` field annotation from `str | None` to `str` (required, non-null); same for role entry's `guild_id`. Accept `channel_id: str` (str includes the new `"*"` sentinel — no Literal needed, validator just accepts the string).
- `the_one/agent/config.py` `_validate_connector_acls`: same tightening for the per-agent overlay.

Bump `CURRENT_VERSION = 25` in `the_one/db/schema.py`.

### Step 2 — ACL helper wildcard handling

Update `_admits_inbound_guild` in `_acl.py` for the wildcard semantic:

```python
# Channels check (current L3 shape):
if allowed_channels:
    if not any(
        c["channel_id"] == channel_id and c["guild_id"] == guild_id
        for c in allowed_channels
    ):
        return False, "..."
```

Replace with wildcard-aware:

```python
if allowed_channels:
    if not any(
        c["guild_id"] == guild_id
        and (c["channel_id"] == "*" or c["channel_id"] == channel_id)
        for c in allowed_channels
    ):
        return False, "..."
```

Same wildcard treatment for roles overlap check:

```python
# Roles check — wildcard role_id="*" admits regardless of member_roles
# (for that specific guild_id):
allowed_role_ids_for_guild = {
    r["role_id"] for r in allowed_roles
    if r["guild_id"] == guild_id
}
if allowed_roles:
    if not allowed_role_ids_for_guild:
        # No role allowance for this guild → deny
        return False, "..."
    if "*" not in allowed_role_ids_for_guild and not (
        member_roles_set & allowed_role_ids_for_guild
    ):
        return False, "..."
```

`admits_outbound`: same wildcard pattern; outbound matches by channel_id alone (L3-locked semantic), so `"*"` admits unconditionally for any channel in the list.

Update helper docstrings to document the wildcard semantic.

### Step 3 — Cross-product matrix extension

Add 4-6 new cells to `TestDmAdmissionCompositionMatrix` (or to a new `TestHierarchicalAxisMatrix` class) in `test_connectors_acl.py` covering:

| # | scenario | expected |
|---|----------|----------|
| 1 | channels=[{guild_id="A", channel_id="*"}], envelope={guild_id="A", channel_id="X"} | admit |
| 2 | channels=[{guild_id="A", channel_id="*"}], envelope={guild_id="B", channel_id="X"} | deny |
| 3 | roles=[{guild_id="A", role_id="*"}], envelope.guild_id="A", member_roles=[] | admit |
| 4 | roles=[{guild_id="A", role_id="*"}], envelope.guild_id="B", member_roles=["R1"] | deny |
| 5 | channels=[{guild_id="A", channel_id="X"}, {guild_id="B", channel_id="*"}], envelope={guild_id="A", channel_id="Y"} | deny |
| 6 | (combo) channels wildcard + explicit role narrow | mixed expected |

### Step 4 — UI restructure in `connector-editor.js`

Major change to the allowlist editor's render function. Current shape (post-L4): 3 sibling sections (Servers / Channels / Roles), each rendered via the existing chiplist abstraction. Target shape: Servers section contains nested sub-chiplists.

Render shape pseudocode:
```js
function renderAllowlistEditor(state) {
  renderPeersSection(state);     // unchanged
  renderDmAdmissionRow(state);   // unchanged
  renderServersSection(state);   // RESTRUCTURED
  // (Channels + Roles sections — DELETED at the top level)
}

function renderServersSection(state) {
  // Server-search dropdown for adding new servers
  renderServerSearchDropdown();
  
  // Per-server row
  for (const guildId of state.allowlist.guilds || []) {
    const guildName = lookupGuildName(guildId);
    renderServerRow({
      guildId,
      guildName,
      channels: state.allowlist.channels.filter(c => c.guild_id === guildId),
      roles: state.allowlist.roles.filter(r => r.guild_id === guildId),
    });
  }
}

function renderServerRow({guildId, guildName, channels, roles}) {
  // Header: server name + remove button
  // Nested channels chiplist (with server-scoped dropdown)
  // Nested roles chiplist (with server-scoped dropdown)
  
  // Render each channel chip — if channel_id === "*", render as sentinel "(all channels)" chip
  // Same for roles
}
```

**Wiring sentinel-on-empty**: when adding a server, insert sentinel entries immediately:
```js
function addServer(guildId) {
  state.allowlist.guilds.push(guildId);
  state.allowlist.channels.push({guild_id: guildId, channel_id: "*"});
  state.allowlist.roles.push({guild_id: guildId, role_id: "*"});
  rerender();
}
```

**Wiring sentinel-replacement-on-explicit**: when adding the first explicit channel under a server, remove the `"*"` sentinel for that server:
```js
function addChannelToServer(guildId, channelId) {
  // Remove sentinel if present
  state.allowlist.channels = state.allowlist.channels.filter(
    c => !(c.guild_id === guildId && c.channel_id === "*")
  );
  state.allowlist.channels.push({guild_id: guildId, channel_id: channelId});
  rerender();
}
```

**Wiring sentinel-restoration-on-empty**: when removing the last explicit channel under a server, re-insert the sentinel:
```js
function removeChannelFromServer(guildId, channelId) {
  state.allowlist.channels = state.allowlist.channels.filter(
    c => !(c.guild_id === guildId && c.channel_id === channelId)
  );
  // If no remaining channels for this guild, re-insert sentinel
  const remaining = state.allowlist.channels.filter(c => c.guild_id === guildId);
  if (remaining.length === 0) {
    state.allowlist.channels.push({guild_id: guildId, channel_id: "*"});
  }
  rerender();
}
```

**Cascade-delete**: when removing a server row:
```js
function removeServer(guildId) {
  state.allowlist.guilds = state.allowlist.guilds.filter(g => g !== guildId);
  state.allowlist.channels = state.allowlist.channels.filter(c => c.guild_id !== guildId);
  state.allowlist.roles = state.allowlist.roles.filter(r => r.guild_id !== guildId);
  rerender();
}
```

**Server-scoped dropdown**: pass `guildId` context to the discoverable-dropdown invocation so it filters its data source to entities from that server only. The dropdown already groups by server (L4) — L5 just opt-into-filtering for the sub-chiplists.

**L4 legacy-indicator removal** (architect-corrected file targeting): the legacy-indicator code lives in `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js:258-285` — `_entryGuildId` check + `data-legacy` attribute + `connector-allowlist-legacy-indicator` span. Delete the `isLegacy` branch + the indicator-rendering block. NOT in `connector-editor.js`. Verification grep stays the same: `git grep -nE "connector-allowlist-channel-legacy-indicator|connector-allowlist-role-legacy-indicator" the_one/ tests/` should return 0 hits.

### Step 5 — `connectors-tab.js` per-agent overlay parallel restructure

The per-agent overlay surface (per L4 deviation discovery, this is in `connectors-tab.js`, not `agent-editor.js`) needs the same hierarchical layout. Per-axis-tri-state-override semantics preserved:
- Per-agent `peers: None` (inherit) | `[]` (explicit-empty) | `[entries]` (narrow) — same as L3
- Per-agent `channels` overlay: per-guild sub-chiplist mirrors account-scope structure; `None` = inherit account-scope's channels for that guild; `[]` = explicit-empty (no channels under this guild for this agent); `[entries]` (with wildcard or specific) = narrow
- Per-agent `roles` overlay: same shape as channels
- Per-agent `guilds` overlay: the server list at per-agent overlay narrows which servers the agent admits

### Step 6 — CSS updates

Add styles for hierarchical layout in `studio.css`:
- Nested server-row indentation (margin-left on sub-chiplists)
- Server-row header styling (distinct from regular chiplist row)
- Sentinel chip styling (visually distinct from explicit channel chips — e.g. dashed border + italic label)
- Per-agent overlay parity styles

### Step 7 — Browser test updates

**Retire L4's 2 legacy-indicator tests** in `test_flow_studio_per_peer_dm_toggle.py`:
- Delete `test_channel_legacy_indicator_renders_for_null_guild_id` and `test_role_legacy_indicator_renders_for_null_guild_id`
- OR rework into 1 migration regression test in `test_db_migration.py::TestSchemaV25`

**Add new browser tests** in a new `test_flow_studio_hierarchical_server_rows.py` covering AC list (5-8 tests).

**Update existing browser tests** with allowlist fixtures: any test posting flat-shape allowlist needs the structured-tuple shape including non-null guild_id (some may already be using L4's `_to_v24_shape()` helper — extend or add `_to_v25_shape()` if needed).

### Step 8 — Run tests + verify + update flight log

```bash
# Migration:
docker exec the-one pytest tests/test_db_migration.py -x --timeout 30

# ACL focused:
docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30

# Broad backend:
docker exec the-one pytest --ignore=tests/browser -x --timeout 60

# Browser:
docker exec the-one pytest tests/browser/ -m browser -x --timeout 120
```

Expected: backend 2770+ / 0 errors; browser 441-444 passing + 2 pre-existing failures.

Append L5 progress entry to flight-log. Update leg status `in-flight` → `landed`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Operator already had explicit channels/roles at L4 land time**: v25 migration leaves them alone (only deletes orphan null-guild_id entries). The UI restructures and renders them under their respective server rows correctly.
- **Operator has server in `guilds` list but NO channels/roles for that server (pre-L5 state)**: post-L5 UI renders the server row with the wildcard sentinel chips (which represent the existing "no narrowing = unrestricted" semantic explicitly). v25 migration does NOT auto-insert sentinels (legacy operator state is preserved as "no explicit narrowing"); the UI inserts sentinels on NEW server additions only. The ACL helper's handling: a server with NO channel entries means unrestricted-on-channels-axis (existing per-axis-tri-state-override semantic at the GLOBAL channels-axis level); a server WITH a `"*"` sentinel means explicit "(all channels)" at the per-guild scope. Subtle but correct: storage state preserved; UI shows the wildcard as the explicit form for NEW servers.

  Actually — operator should confirm: does the L5 UI render existing empty-channels server rows with the sentinel chip, or with nothing? Recommendation: render the sentinel chip even for pre-L5 empty-channels server rows (operator sees the same state regardless of pre-/post-L5 origin). This is a render-time UI choice, not a storage change.

- **Operator removes the last explicit channel AND removes the server in one undo-able action**: each remove is a separate state change; the implementer wires them independently. Removing the last explicit channel triggers sentinel re-insertion; subsequently removing the server cascades to delete all channel/role entries with that guild_id.

- **Wildcard `"*"` in per-agent overlay**: same semantic as account-scope; per-agent overlay can also have `{guild_id: "X", channel_id: "*"}` meaning "narrow to this guild but admit any channel of it for this agent." Implementer handles uniformly.

- **`docker-compose.yml` discipline (unchanged)**: continues; explicit `git add` only.

- **2 L4 legacy-indicator browser tests**: retire decision (delete vs rework) is implementer's call. Recommend delete + add migration regression test in TestSchemaV25 instead — the migration test is the right home for "v25 deletes orphans" assertion.

## Files Affected

**Substrate** (4 files — count corrected per architect):
- `the_one/db/schema.py` — v25 migration block; bump `CURRENT_VERSION = 25`
- `the_one/db/models.py` — Pydantic validator tightened (invert the `guild_id is not None` permissive check at `:420` to require non-null)
- `the_one/agent/config.py` — `_validate_connector_acls` tightened (parallel; `:442,484`)
- `the_one/connectors/_acl.py` — wildcard handling in `_admits_inbound_guild` + `admits_outbound`

**Frontend** (4 files — architect-corrected):
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — allowlist section restructure (substantial)
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — L4 legacy-entry indicator code at `:258-285` REMOVED
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — per-agent overlay parallel restructure
- `the_one/interfaces/web/static/css/studio.css` — nested layout styles + sentinel-chip styling

**Tests** (multiple files):
- `tests/test_db_migration.py` — new `TestSchemaV25` class (3+ tests)
- `tests/test_connectors_acl.py` — cross-product matrix extended with 4-6 wildcard cells
- `tests/test_db_repositories.py` OR `tests/test_connectors_*.py` — validator-rejection test for null guild_id
- `tests/browser/test_flow_studio_per_peer_dm_toggle.py` — 2 legacy-indicator tests retired
- New: `tests/browser/test_flow_studio_hierarchical_server_rows.py` (5-8 tests)
- Existing browser tests with fixtures — may need shape updates (use Phase 5c grep at implementation time to enumerate)

**Flight artifacts** (mandatory updates):
- `missions/11-discord-connector-depth/flights/12-hierarchical-allowlist-and-snake-case-rename/flight-log.md` — append L5 progress entry
- This file — status → `landed`

**Explicitly NOT affected in L5**:
- `tests/test_db_migration.py` pre-v25 TestSchemaVN classes (Category A — preserve historical shape)
- Backend test_provider_repository.py asyncio teardown warnings (deferred to routine-maintenance per F11 + F12 recon)
- `docker-compose.yml` (operator's local dev state)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (v25 migration, validator tightening, ACL wildcard, cross-product matrix, UI restructure, browser tests)
- [x] L5 atomicity boundary verified (no L1-L4-only files re-touched outside intended L5 scope)
- [x] Backend regression: 2770+ passing
- [x] Browser suite: 441-444 passing + 2 pre-existing failures
- [x] L4 legacy-indicator code DELETED (not just commented)
- [x] Flight-log L5 progress entry appended
- [x] This leg's status set to `landed`
- [x] Do NOT update flight-spec leg checkbox (Phase 2d-redux commit does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d-redux batches L5 commit on top of `eb7f04d`)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-30, post-L4 leg-design time):

| Citation | Classification | Resolution |
|----------|---------------|------------|
| `the_one/db/schema.py` v24 block ends at line ~1356 with `version = 24` | OK | Verified by grep at L3 land time; v25 inserts after this line |
| `the_one/connectors/_acl.py` post-L3 structured-tuple shape | OK | L3 implementer confirmed; wildcard `"*"` is a string extension of the existing channel_id/role_id field |
| `the_one/db/models.py` allowlist validator post-L3 | OK | L3 spec confirmed; tightening from `str | None` → `str` for guild_id is a 1-line change |
| `connector-editor.js` post-L4 (~3590+ LOC) flat 3-section allowlist | OK | L4 implementer confirmed; restructure into nested sub-chiplists is the L5 scope |
| `connectors-tab.js` post-L4 per-agent overlay surface | OK | L4 deviation note: per-agent surface lives here, not in agent-editor.js |
| L4's 2 legacy-indicator browser tests in `test_flow_studio_per_peer_dm_toggle.py` | OK | Verified by L4 implementer report |
| `tests/test_db_migration.py` TestSchemaV24 (post-L3) | OK | TestSchemaV25 inserts after this class |
| Cross-product matrix in `test_connectors_acl.py` post-L3 (12 cells) | OK | Extension with 4-6 wildcard cells is straightforward parametrize-extension |

8 citations verified clean against current code at leg design time. The Phase 5c architect cycle for L5 (mandated by F12 spec convention) will re-verify the browser-test surface for any drift between L4 land time and L5 implementation start.
