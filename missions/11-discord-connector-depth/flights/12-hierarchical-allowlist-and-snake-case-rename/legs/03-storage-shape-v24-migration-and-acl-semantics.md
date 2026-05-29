# Leg: storage-shape-v24-migration-and-acl-semantics

**Status**: completed
**Flight**: [Hierarchical Allowlist Axes + Snake_Case Identifier Rename](../flight.md)

## Objective

Land the F12 substrate change as one atomic leg: Pydantic shape change + schema migration v24 (row-rewrite 3 axes of `connectors.config.allowlist` + parallel `agents.connector_acls` + rename `idx_pending_approvals_account_peer_status` index + rename `dm_admission` Literal value `"allowlisted-peers-only"` → `"admin-approved"`) + ACL helper updates (`_admits_inbound_dm` / `_admits_inbound_guild` / `admits_outbound` / `admits_dm_peer` updated for structured-tuple lookups + new DM composition chain per the operator-confirmed Truth Table) + 7 peer-list consumer site updates (`_inbound.py`, `interfaces/web/api.py`, `_discord.py`) + `TestSchemaV24` (5+ tests) + 12-cell DM composition cross-product matrix. Operator-merged L3+L5 to avoid transient ACL-vs-storage-shape state per architect cycle-1.

## Context

This is the third (and largest) of four legs in F12. L1 (snake_case rename) and L2 (`_acl.py` extraction + agents.md convention) both landed cleanly with backend baseline preserved at 2749 passed / 0 errors / ~242-262s wall.

**Per the flight spec's L3 design decisions** (architect cycle-1 + cycle-2 verified, operator-confirmed):

1. **Storage shape**: structured tuples for channels + roles; per-peer `dm_allowed` bool added to peer entries; `dm_admission` Literal value rename `"allowlisted-peers-only"` → `"admin-approved"`.

2. **DM Composition Truth Table** — operator chose option (b) "preserve current semantics":
```
admit_dm = (admit_dms is not False)
       AND (peer in allowlist)
       AND (
         dm_admission == "all" OR
         (dm_admission == "admin-approved" AND peer.dm_allowed == true)
       )
```
- Under `dm_admission="all"`: per-peer `dm_allowed` ignored
- Under `dm_admission="none"`: deny regardless of per-peer toggle
- Under `dm_admission="admin-approved"`: per-peer `dm_allowed` is the discriminator

3. **Backfill strategy**: legacy channel/role entries (post-v24 with null guild_id) admit regardless of envelope guild_id — legacy-permissive backward-compat.

4. **L3+L5 merge rationale**: adding the per-peer `dm_allowed` field to storage requires the ACL helpers to consume it in lockstep — splitting into separate storage + semantics legs would leave tests against the new shape without the ACL semantic that respects it. One atomic leg.

5. **Cross-product matrix**: 12 cells covering `admit_dms × dm_admission × dm_allowed × in_allowlist`. Per F11 debrief recommendation on codifying cross-axis HAT-discovered bugs as substrate-test-matrix-by-default.

## Inputs

- F12 L1 + L2 landed (status: landed, uncommitted on branch `flight/12-hierarchical-allowlist-and-snake-case-rename`)
- Backend baseline (post-L2): 2749 passed / 4 skipped / 0 errors / ~242s wall
- `_acl.py` post-L2: 575 LOC, 7 functions (added `_admits_inbound_dm` + `_admits_inbound_guild`)
- `the_one/db/schema.py` v23 block at lines 950-1155 (post-F11); v24 inserts AFTER v23
- `the_one/db/models.py` allowlist validator at lines 308+ (currently 5-axis: peers/channels/guilds/roles/dm_admission)
- `the_one/agent/config.py` connector_acls validator at lines 262+ (currently 5-axis: peers/channels/guilds/roles/admit_dms)
- 7 production peer-list consumer sites verified at L3 design time:
  - `the_one/connectors/_inbound.py:467-476` — "add peer to allowlist on first contact" path (pairing approve)
  - `the_one/interfaces/web/api.py:2727-2740` — peer-approval mutation in approve_peer_approval handler
  - `the_one/connectors/_discord.py:1651` — peer enumeration in pairing-resolver hook (`is_dm` admission gate)
  - Plus all reads/writes inside `_acl.py` helpers (covered by L2 extraction + L3 helper updates)
- Operator local-state callout (unchanged): `docker-compose.yml` stays unstaged

## Outputs

- Pydantic validators in `the_one/db/models.py` + `the_one/agent/config.py` accept the new structured shape for peers/channels/roles (and reject the old flat shape post-v24)
- Schema migration v24 added to `the_one/db/schema.py` (after v23) — row-rewrite + index rename + Literal-value rename
- ACL helpers updated to consume structured tuples + new DM composition chain
- 7 peer-list consumer sites updated to construct + consume `{id, dm_allowed}` dicts (and parallel updates for channels/roles)
- `TestSchemaV24` class added to `tests/test_db_migration.py` with 5+ tests
- 12-cell DM composition cross-product matrix added to `tests/test_connectors_acl.py`
- Existing ACL + db_repositories + db_api + connectors test fixtures updated to new shape OR reclassified as Category A (pre-v24 historical pinning)
- Flight log L3 progress entry appended
- Leg status `landed` (NOT committed — Phase 2d batches commits)

## Acceptance Criteria

- [x] **Schema migration v24 added** to `the_one/db/schema.py` after the v23 block (which ends at line 1155 with `version = 23`). v24 must:
  - Row-rewrite `connectors.config.allowlist` JSON for every row: `peers: list[str]` → `peers: list[{"id": str, "dm_allowed": bool}]`; `channels: list[str]` → `channels: list[{"guild_id": null, "channel_id": str}]`; `roles: list[str]` → `roles: list[{"guild_id": null, "role_id": str}]`; `dm_admission` Literal-value rename `"allowlisted-peers-only"` → `"admin-approved"` (preserving `"none"` and `"all"` unchanged).
  - Row-rewrite `agents.connector_acls` JSON for every row: same transformations applied to each `connector_acls[account_id]` payload (per-agent shape mirrors account-scope; `admit_dms` stays as-is per per-agent overlay design decision).
  - DROP + CREATE the index: `DROP INDEX IF EXISTS idx_pending_approvals_account_peer_status`; `CREATE INDEX idx_pending_approvals_connector_peer_status ON pending_approvals (connector_id, peer_id, status)`.
  - Idempotent on re-run (`if version < 24:` guard); transactional via `executescript`; `INSERT OR IGNORE INTO schema_version` LAST.
  - Use the F11 v23 segment-level re-entry guards pattern for the v7-strip-test scenario (skip transformation if source column already in target shape).
- [x] **DM Admission collapse rule** preserves F10 semantics exactly per the migration body:
  - `dm_admission == "all"` → all existing peers get `dm_allowed=true`
  - `dm_admission == "none"` → all existing peers get `dm_allowed=false`
  - `dm_admission` set to `"allowlisted-peers-only"` OR absent-but-allowlist-present → all existing peers get `dm_allowed=true` AND `dm_admission` value rewritten to `"admin-approved"`
  - `allowlist` absent entirely → no peers to migrate
- [x] **Pydantic validators updated** in lockstep:
  - `the_one/db/models.py` `_validate_config_v17_extras` (or wherever the allowlist validator lives at line 308+) accepts the new structured shape; rejects flat strings; accepts `dm_admission: Literal["none", "admin-approved", "all"]` (the new value `"admin-approved"`; `"allowlisted-peers-only"` rejected — migration handles rewrite).
  - `the_one/agent/config.py:262+` `_validate_connector_acls` extended to accept structured peers/channels/roles dicts (current shape is `list[str] | bool | None`; new shape adds the dict form).
- [x] **ACL helpers updated** in `the_one/connectors/_acl.py`:
  - `_admits_inbound_dm`: implements the DM Composition Truth Table verbatim — `admit_dm = (admit_dms is not False) AND (peer in allowlist) AND (dm_admission == "all" OR (dm_admission == "admin-approved" AND peer.dm_allowed == true))`. The `peer in allowlist` check uses the structured-dict form (`any(p["id"] == peer_id for p in peers)`).
  - `_admits_inbound_guild`: structured-tuple channel + role lookups. Channel admission: `any(c["channel_id"] == channel_id AND (c["guild_id"] is None OR c["guild_id"] == guild_id) for c in channels)`. Roles overlap: a peer's `member_roles` overlaps with any `r` where `r["role_id"] in member_roles AND (r["guild_id"] is None OR r["guild_id"] == guild_id)`.
  - `admits_outbound`: mirror update per `two-symmetric-paths-in-acl` convention — same channel-tuple lookup (null guild_id permissive); outbound has no envelope guild_id context so the guild_id check is effectively "match-OR-null". No DM composition at outbound (no envelope context per F10 design).
  - `admits_dm_peer`: updated for the structured-dict peer lookup + per-peer `dm_allowed` consumption.
- [x] **Peer-list consumer sites updated** (7 production sites + tests):
  - `the_one/connectors/_inbound.py:467-476` — peer-add path constructs `{"id": envelope.peer_id, "dm_allowed": false}` (safe default; operator can flip via UI later). The default `dm_allowed=false` matches the new-peer convention.
  - `the_one/interfaces/web/api.py:2727-2740` — `approve_peer_approval` handler constructs `{"id": approval.peer_id, "dm_allowed": false}` when adding the approved peer to the allowlist (matching the pairing-approve path).
  - `the_one/connectors/_discord.py:1651` — peer enumeration in pairing-resolver hook reads `peer["id"] for peer in allowlist["peers"]` instead of `peer in allowlist["peers"]`.
- [x] **`TestSchemaV24` class added** to `tests/test_db_migration.py` (after the existing TestSchemaV23 class at lines ~2992-3390 per F11 L1 record) with at minimum 5 tests:
  - `test_v24_fresh_db_shape` — fresh DB schema applied through v24 produces the expected post-v24 shape (Pydantic validator accepts; flat shape rejected).
  - `test_v24_idempotent_on_rerun` — running `ensure_schema` against an already-v24 DB is a no-op.
  - `test_v24_legacy_v23_row_migration_preserves_data` — a v23-seeded DB with `connectors` rows containing the 5-axis flat allowlist migrates to v24 with all data preserved per the collapse rules (3 sub-cases covering `dm_admission` ∈ {"all", "none", "allowlisted-peers-only", absent}).
  - `test_v24_agents_connector_acls_rewrite` — `agents.connector_acls` JSON column row-rewrite works in lockstep (parallel structured shape).
  - `test_v24_index_rename` — `idx_pending_approvals_account_peer_status` no longer exists; `idx_pending_approvals_connector_peer_status` exists with the correct column expression.
- [x] **Cross-product matrix added** to `tests/test_connectors_acl.py` — a `TestDmAdmissionCompositionMatrix` class with 12 tests (or parametrized into one method with 12 cases) covering the `admit_dms × dm_admission × dm_allowed × in_allowlist` product. Each cell asserts the expected admit/deny per the DM Composition Truth Table.
- [x] **Existing ACL + db tests updated**: fixture data updated to new shape across `tests/test_connectors_acl.py`, `tests/test_connectors_routing.py`, `tests/test_connectors_inbound.py`, `tests/test_db_repositories.py`, `tests/test_db_api.py`, `tests/test_app_pending_approval_merge.py`, `tests/_connector_dispatch_helpers.py`. Tests pinning pre-v24 historical shape (rare — Category A) are renamed to `TestPreV24*` or similar.
- [x] **Migration test suite green**: `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30` — pre-v23 TestSchemaVN classes pass unchanged (Category A); TestSchemaV24 added; total test count grows by ~5.
- [x] **Broader backend suite green**: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` at **2766+ passing** (L1 baseline 2749 + 5 new TestSchemaV24 + 12 new cross-product matrix tests + 0 net for existing fixture-updated tests = 2766; "+" allows for any additional round-trip / property-shape tests added per AC). Wall-clock within 10% of L2 baseline (242s).
- [x] **SQLite round-trip test added** (cycle-1 finding #4): a new test (in `tests/test_db_repositories.py` or `tests/test_db_api.py`) that constructs a Connector with structured-shape allowlist, persists via `ConnectorRepository.create()`, retrieves via `.get()`, and asserts the retrieved Pydantic instance matches the original (no shape mutation through SQLite JSON serialization). Pydantic catches shape at boundaries; SQLite stores arbitrary JSON. The round-trip test catches accidental shape mutations in repository code.
- [x] **`_acl.py` docstring/comment sweep** (cycle-1 finding #7): all references to `"allowlisted-peers-only"` Literal value in `_acl.py` docstrings + comments + module docstring updated to `"admin-approved"`. Pre-implementation grep: `grep -nE '"allowlisted-peers-only"' the_one/connectors/_acl.py`. Expected: ~8 hits at module-doc + helper docstrings + comments (cycle-1 enumerated lines 24, 203, 269, 374, 382, 385, 391, 394).
- [x] **No new errors**: 0 errors / 0 failures. The 2 pre-existing aiosqlite teardown warnings persist (not L3-caused).
- [x] Browser baseline preserved (no L3 changes to UI — `tests/browser/` untouched).
- [x] Flight log `Leg Progress` section has an L3 entry summarizing the substrate change + ACL semantics + migration + cross-product matrix + test results.
- [x] Leg status updated to `landed` in this file's header. **DO NOT commit** — Phase 2d batches commits.

## Verification Steps

1. **Migration test suite** (the regression net for v24):
   - `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30`
   - Expect: all pre-v24 TestSchemaVN classes pass (Category A — historical shape pinned) + TestSchemaV24 passes (5+ tests). Total file count grows by ~5.

2. **ACL test suite** (the regression net for the helper + composition changes):
   - `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30`
   - Expect: existing 169 passing (L2 baseline) + 12 new matrix cells + ~5 fixture-update changes = 181+ passing.

3. **Full backend suite**:
   - `docker exec the-one pytest --ignore=tests/browser -x --timeout 60`
   - Expect: 2766+ passing / 4 skipped / 0 errors / 0 failures.

4. **Pydantic validator manual check**:
   - In a Python REPL: `from the_one.db.models import Connector; Connector.model_validate({"id": "x", "type": "stub", "config": {"allowlist": {"peers": ["U1"], "channels": []}}})` should raise (flat strings no longer accepted post-v24).
   - `Connector.model_validate({"id": "x", "type": "stub", "config": {"allowlist": {"peers": [{"id": "U1", "dm_allowed": true}], "channels": []}}})` should succeed.

5. **Schema introspection** (after migration test runs against a fresh DB):
   - `sqlite3 <test.db> '.schema pending_approvals'` shows the index named `idx_pending_approvals_connector_peer_status` (not the old name).

## Implementation Guidance

**Order matters.** This is a large leg; ordering minimizes the time tests are broken:
1. Step 1: Schema migration v24 — add the block to schema.py FIRST (no Pydantic changes yet; existing tests still work against pre-v24 rows but new tests using `ensure_schema` will start seeing v24 shape).
2. Step 2: Pydantic validators updated to accept BOTH shapes temporarily (transitional dual-shape) — see Edge Cases below for the recommendation.
3. Step 3: ACL helpers updated.
4. Step 4: Peer-consumer site updates.
5. Step 5: Pydantic validators tightened to ONLY accept new shape (drop flat-shape acceptance from Step 2).
6. Step 6: TestSchemaV24 + cross-product matrix tests added.
7. Step 7: Existing test fixtures updated.
8. Step 8: Final test runs + grep verification + flight log + leg status.

**Alternative single-step path**: implementer may opt to land Steps 2 + 5 as one (Pydantic accepts only new shape from the start; existing tests fail immediately and are updated in lockstep in Step 7). Either path works; the dual-shape transitional path is gentler on the iteration loop.

### Step 1 — Schema migration v24

Locate the end of the v23 block at `the_one/db/schema.py:1155` (where `version = 23` is set). Add a new `if version < 24:` block following the v23 row-rewrite pattern. v24 body:

```python
if version < 24:
    # Mission 11 Flight 12 Leg 3: structured-tuple storage for
    # channels + roles, per-peer dm_allowed for DM admission gating
    # under the admin-approved policy mode, and the dm_admission
    # Literal-value rename "allowlisted-peers-only" → "admin-approved"
    # (operator-vocabulary alignment).
    #
    # Row-rewrites BOTH connectors.config.allowlist AND
    # agents.connector_acls JSON column contents in a single transaction.
    # The transformation is offline-safe (no network); guild_id is
    # backfilled to null for legacy channel/role entries (ACL treats
    # null as "any guild" = legacy-permissive backward-compat).
    #
    # Also renames idx_pending_approvals_account_peer_status →
    # idx_pending_approvals_connector_peer_status (bundled per F12
    # operator decision; L1 explicitly deferred the index rename to
    # here).
    #
    # Idempotency: `if version < 24:` short-circuit + segment-level
    # re-entry guards (skip transformation if already in target shape).
    # The v7-strip-test scenario (test re-runs ensure_schema after
    # rewinding schema_version) is handled by the segment guards.
    
    import json as _json
    
    # ---- Transform connectors.config.allowlist ----
    async with conn.execute("SELECT id, config FROM connectors") as cursor:
        connector_rows = await cursor.fetchall()
    for row in connector_rows:
        config_str = row["config"] or "{}"
        config = _json.loads(config_str)
        allowlist = config.get("allowlist")
        if allowlist is None:
            continue
        # Segment guard: skip if already in v24 shape
        peers = allowlist.get("peers", [])
        if peers and isinstance(peers[0], dict):
            continue  # already migrated
        # Determine dm_allowed default from old dm_admission value.
        # Note: bare `.get("dm_admission")` without default — we need to
        # distinguish ABSENT (treat as F10 default "allowlisted-peers-only")
        # from explicit "admin-approved" (pre-existing migrated value or
        # manual operator edit; cycle-1 callout #3 — defensive net).
        dm_admission_raw = allowlist.get("dm_admission")
        dm_admission_old = dm_admission_raw if dm_admission_raw is not None else "allowlisted-peers-only"
        if dm_admission_old == "none":
            dm_allowed_default = False
        else:  # "all", "allowlisted-peers-only", "admin-approved", or absent (→ defaulted to allowlisted-peers-only above)
            dm_allowed_default = True
        # Rewrite peers
        allowlist["peers"] = [
            {"id": peer_id, "dm_allowed": dm_allowed_default}
            for peer_id in peers
        ]
        # Rewrite channels (null guild_id backfill)
        allowlist["channels"] = [
            {"guild_id": None, "channel_id": ch_id}
            for ch_id in allowlist.get("channels", [])
        ]
        # Rewrite roles (null guild_id backfill)
        if "roles" in allowlist:
            allowlist["roles"] = [
                {"guild_id": None, "role_id": role_id}
                for role_id in allowlist["roles"]
            ]
        # Rename / normalize dm_admission Literal value.
        # Three cases handled by ONE branch because dm_admission_old already
        # collapsed "absent" → "allowlisted-peers-only" at line 190 default:
        # (a) was "allowlisted-peers-only" (explicit or absent-defaulted) → rewrite to "admin-approved"
        # (b) was "all" / "none" / pre-existing "admin-approved" → unchanged
        if dm_admission_old == "allowlisted-peers-only":
            allowlist["dm_admission"] = "admin-approved"
        config["allowlist"] = allowlist
        await conn.execute(
            "UPDATE connectors SET config = ? WHERE id = ?",
            (_json.dumps(config), row["id"]),
        )
    
    # ---- Transform agents.connector_acls ----
    async with conn.execute("SELECT name, connector_acls FROM agents") as cursor:
        agent_rows = await cursor.fetchall()
    for row in agent_rows:
        acls_str = row["connector_acls"]
        if not acls_str:
            continue
        acls = _json.loads(acls_str)
        # Segment guard: skip the ENTIRE row only if ALL accounts already in
        # v24 shape (any-account-already-migrated → row was migrated; partial
        # would indicate corruption). Detection: check first non-empty peers
        # list across all accounts; if any is structured-dict shape, treat
        # the whole row as already-migrated.
        any_v24_shape = any(
            payload.get("peers") and isinstance(payload["peers"][0], dict)
            for payload in acls.values()
        )
        if any_v24_shape:
            continue
        for acct_id, payload in acls.items():
            # Transform peers (per-agent dm_allowed defaults true; per-agent
            # is a narrowing overlay and inherits account-scope's default)
            if isinstance(payload.get("peers"), list):
                payload["peers"] = [
                    {"id": peer_id, "dm_allowed": True}
                    for peer_id in payload["peers"]
                ]
            # Transform channels (null guild_id backfill)
            if isinstance(payload.get("channels"), list):
                payload["channels"] = [
                    {"guild_id": None, "channel_id": ch_id}
                    for ch_id in payload["channels"]
                ]
            # Transform roles (null guild_id backfill; if present)
            if isinstance(payload.get("roles"), list):
                payload["roles"] = [
                    {"guild_id": None, "role_id": role_id}
                    for role_id in payload["roles"]
                ]
            # admit_dms stays as-is per per-agent overlay design
        await conn.execute(
            "UPDATE agents SET connector_acls = ? WHERE name = ?",
            (_json.dumps(acls), row["name"]),
        )
    
    # ---- Rename index ----
    await conn.execute("DROP INDEX IF EXISTS idx_pending_approvals_account_peer_status")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pending_approvals_connector_peer_status "
        "ON pending_approvals (connector_id, peer_id, status)"
    )
    
    await conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (24,)
    )
    await conn.commit()
    version = 24
```

Pattern matches the v17, v18, v20 ALTER ADD COLUMN + INSERT-LAST style for non-table-rename row-mutations. The v23 `executescript` pattern is not needed here since v24 doesn't change table structure (only column content + index name).

### Step 2 — Pydantic validators (transitional dual-shape, optional)

Recommendation: skip transitional dual-shape. Update validators to accept only new shape; existing tests will fail in Step 3-7 until their fixtures are updated. This is the cleaner path because the leg's atomicity demands the new shape.

**`the_one/db/models.py` allowlist validator (lines 308+)**:
- Update peers entry validation: must be `dict[str, Any]` with required keys `id: str`, `dm_allowed: bool`
- Update channels entry validation: must be `dict[str, Any]` with required keys `channel_id: str`, optional `guild_id: str | None`
- Update roles entry validation: must be `dict[str, Any]` with required keys `role_id: str`, optional `guild_id: str | None`
- `dm_admission` Literal updated: `Literal["none", "admin-approved", "all"]`. Reject `"allowlisted-peers-only"` (migration handles rewrite; post-v24 no row should have it).
- **Default for absent `dm_admission` key** (when allowlist present): insert `"admin-approved"` explicitly via in-place mutation (mirroring the F10 validator's pattern at the current `:362-364` site which inserted `"allowlisted-peers-only"` — replace that string with the new Literal value). This guards against any post-v24 code path that constructs an allowlist without an explicit `dm_admission` (e.g. operator hand-edits via test fixtures).

**`the_one/agent/config.py` connector_acls validator (lines 262+)**:
- Mirror the same shape changes for per-agent `peers`, `channels`, `roles` lists
- `admit_dms` stays as `bool | None`
- Note: per-agent `peers` may be `None` (inherit) or `[]` (explicit empty) — same tri-state semantic; only the per-entry shape changes

### Step 3 — ACL helper updates in `the_one/connectors/_acl.py`

**`_admits_inbound_dm`** — implement the Composition Truth Table:
```python
def _admits_inbound_dm(...) -> tuple[bool, str]:
    account_id = account.id
    allowlist = account.config.get("allowlist")
    if allowlist is None:
        return True, ""  # unrestricted
    
    # account-scope peers: structured dicts
    allowed_peers = allowlist.get("peers", [])
    peer_entry = next((p for p in allowed_peers if p["id"] == peer_id), None)
    
    # composition rule:
    # admit_dm = (admit_dms is not False)  -- per-agent
    #        AND (peer in allowlist)        -- per_entry is not None (if peers non-empty)
    #        AND (dm_admission == "all" OR
    #             (dm_admission == "admin-approved" AND peer.dm_allowed == true))
    
    # Per-agent admit_dms (deny short-circuit)
    if agent_acl is not None and agent_acl.get("admit_dms") is False:
        return False, f"DM denied: agent admit_dms is False on account {account_id!r}"
    
    # Peers axis check
    if allowed_peers and peer_entry is None:
        return False, f"peer_id {peer_id!r} is not admitted on account {account_id!r}"
    
    # dm_admission gate
    dm_admission = allowlist.get("dm_admission", "admin-approved")
    if dm_admission == "none":
        return False, f"DM denied: account {account_id!r} dm_admission is 'none'"
    if dm_admission == "admin-approved":
        if peer_entry is None:
            # admin-approved + no peers → deny (no one approved)
            return False, f"DM denied: account {account_id!r} dm_admission is 'admin-approved' and peer not in allowlist"
        if not peer_entry.get("dm_allowed", False):
            return False, f"DM denied: peer {peer_id!r} has dm_allowed=false under admin-approved policy"
    # dm_admission == "all" OR ("admin-approved" AND peer.dm_allowed == true): admit
    
    return True, ""
```

**`_admits_inbound_guild`** — update channel + role checks for structured tuples:
```python
def _admits_inbound_guild(...) -> tuple[bool, str]:
    account_id = account.id
    member_roles_set = set(member_roles or [])
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        # Peers axis (structured dicts)
        allowed_peers = allowlist.get("peers", [])
        if allowed_peers and not any(p["id"] == peer_id for p in allowed_peers):
            return False, f"peer_id {peer_id!r} is not admitted on account {account_id!r}"
        # Channels axis (structured tuples; null guild_id permissive)
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and not any(
            c["channel_id"] == channel_id
            and (c["guild_id"] is None or c["guild_id"] == guild_id)
            for c in allowed_channels
        ):
            return False, f"channel_id {channel_id!r} is not admitted on account {account_id!r}"
        # Guilds axis (unchanged — already list[str])
        # Roles axis (structured tuples; null guild_id permissive)
        allowed_roles = allowlist.get("roles", [])
        if allowed_roles:
            admitted_role_ids = {
                r["role_id"] for r in allowed_roles
                if r["guild_id"] is None or r["guild_id"] == guild_id
            }
            if not (member_roles_set & admitted_role_ids):
                return False, f"peer roles do not overlap with admitted roles on account {account_id!r}"
    # ...same shape for per-agent block...
```

**`admits_outbound`** — mirror the channel-tuple update per two-symmetric-paths-in-acl convention. **Locked decision (cycle-1 finding #5)**: outbound matches by `channel_id` alone, ignoring `guild_id`. Outbound writes are operator-initiated through the F4 platform-send tool; the target channel's guild is determined by the channel itself, not by the operator's intent. Matching by `channel_id` alone preserves legacy-permissive backward-compat (consistent with the null-guild_id-is-permissive rule for inbound legacy entries):
```python
# Outbound channel admission (no envelope guild_id context):
if allowed_channels and not any(
    c["channel_id"] == channel_id for c in allowed_channels
):
    return False, f"..."
```
Document the choice in `admits_outbound` docstring with a 2-line note: "Outbound matches by channel_id alone (ignoring guild_id) because the F4 platform-send tool has no envelope guild context. Symmetric to inbound's null-guild_id-permissive rule."

**`admits_dm_peer`** — update for structured-dict peer lookup + per-peer `dm_allowed` consumption per the Composition Truth Table.

### Step 4 — Peer-list consumer site updates

**`the_one/connectors/_inbound.py:467-476`** — pairing-approve path. Replace:
```python
peers = list(allowlist.get("peers", []))
if envelope.peer_id not in peers:
    peers.append(envelope.peer_id)
allowlist["peers"] = peers
```
with:
```python
peers = list(allowlist.get("peers", []))
if not any(p["id"] == envelope.peer_id for p in peers):
    peers.append({"id": envelope.peer_id, "dm_allowed": False})
allowlist["peers"] = peers
```
Also update the fallback dict at `:467-470`: `"peers": []` initialization stays (empty list still valid).

**`the_one/interfaces/web/api.py:2727-2740`** — `approve_peer_approval` handler. Same transformation as `_inbound.py`. Replace the `peers.append(approval.peer_id)` with `peers.append({"id": approval.peer_id, "dm_allowed": False})`.

**`the_one/connectors/_discord.py:1651`** — pairing resolver hook. Replace `if envelope.peer_id in peers:` with `if any(p["id"] == envelope.peer_id for p in peers):`.

Search for any OTHER peer-list consumers via:
```bash
grep -rn "allowlist.*peers\|allowlist\['peers'\]\|allowlist\[\"peers\"\]" the_one/ --include='*.py'
```
Update each site for structured-dict consumption.

### Step 5 — Add `TestSchemaV24` to `tests/test_db_migration.py`

Follow the existing `TestSchemaVN` class pattern (see TestSchemaV23 in the same file post-F11). Add 5+ tests per AC. Mirror the v23 pattern of hand-building a v23-shape DB then running `ensure_schema` to v24 and asserting the post-migration shape.

### Step 6 — Add cross-product matrix to `tests/test_connectors_acl.py`

Add `TestDmAdmissionCompositionMatrix` class with exactly 12 tests (parametrized via `@pytest.mark.parametrize` recommended). The 12 cells (operator-spec-enumerated; cycle-1 suggestion #2 to enumerate explicitly):

| # | admit_dms | dm_admission | dm_allowed | in_allowlist | expected | rationale |
|---|-----------|--------------|------------|--------------|----------|-----------|
| 1 | None | "all" | true | true | admit | baseline: everyone DMs |
| 2 | None | "all" | false | true | admit | dm_admission=all ignores per-peer toggle |
| 3 | None | "all" | true | false | admit | "all" + not in allowlist → admit (no peers axis to fail) |
| 4 | None | "none" | true | true | deny | dm_admission=none always denies |
| 5 | None | "none" | false | true | deny | (same) |
| 6 | None | "admin-approved" | true | true | admit | the happy path: explicit approval |
| 7 | None | "admin-approved" | false | true | deny | per-peer toggle off → deny |
| 8 | None | "admin-approved" | true | false | deny | not in allowlist → deny under admin-approved |
| 9 | False | "all" | true | true | deny | admit_dms=False short-circuits |
| 10 | False | "admin-approved" | true | true | deny | (same — overrides admit) |
| 11 | True | "all" | true | true | admit | admit_dms=True behaves as None (no elevation) |
| 12 | True | "admin-approved" | false | true | deny | admit_dms=True does NOT override per-peer toggle |

Cell #3 deserves extra attention: the F11 + F12 design treats account-scope `peers` as `[]` (empty list) when no peer is allowlisted; `dm_admission="all"` with empty `peers` admits regardless. If `peers` has entries but the inbound peer is NOT among them, the peers-axis check denies (which is separate from the DM-composition decision). Cell #3's "in_allowlist=false" means the peer is NOT in a NON-EMPTY peers list; the test should set `peers = [{"id": "other-peer", "dm_allowed": true}]` and the inbound peer's ID is different. Under `dm_admission="all"` the peers-axis check applies first and denies — so cell #3's expected is actually DENY (the peers-axis check fails before the DM composition is consulted).

**Revised cell #3 expected**: **deny** (peers-axis check fails first). Implementer verifies this matches the actual rule precedence in `_admits_inbound_dm`. If precedence differs, update the cell or update the helper to match the intended semantic.

### Step 7 — Update existing test fixtures

Sweep these files for allowlist + connector_acls fixture data and update to new shape (cycle-1 found 16 non-browser test files touching the surface — full list below; previous 8 was incomplete):
- `tests/test_connectors_acl.py` (the existing 169 tests from L2 baseline)
- `tests/test_connectors_routing.py`
- `tests/test_connectors_inbound.py`
- `tests/test_db_repositories.py`
- `tests/test_db_api.py`
- `tests/test_app_pending_approval_merge.py`
- `tests/_connector_dispatch_helpers.py`
- `tests/test_lifespan.py`
- **`tests/test_connector_history_tools.py`** (cycle-1 added)
- **`tests/test_connector_send_tool.py`** (cycle-1 added)
- **`tests/test_connectors_discord.py`** (cycle-1 added)
- **`tests/test_connectors_commands.py`** (cycle-1 added)
- Any others surfaced by the pre-implementation grep below
- **Note**: 5 `tests/browser/*.py` files touch the surface too (cycle-1 enumerated) — these are L4 scope, NOT L3. Track for L4 traceability.

Also: `grep -rn "allowlisted-peers-only" tests/ --include='*.py'` returns ~26 hits at L3 design time — each needs updating to `"admin-approved"` (or removal if the test was specifically pinning the old Literal value as Category A historical).

Pre-implementation grep for the surface:
```bash
grep -rln 'allowlist.*peers\|allowlist.*channels\|allowlist.*roles\|allowlist.*dm_admission\|connector_acls' tests/ --include='*.py'
```

For each fixture: change `"peers": ["U1", "U2"]` → `"peers": [{"id": "U1", "dm_allowed": false}, {"id": "U2", "dm_allowed": false}]` (or `dm_allowed: true` if the test exercises DM admission). Same shape for `channels` (add `guild_id: null` for legacy) and `roles`.

Tests pinning the OLD shape's semantic (pre-v24 historical behavior) get renamed to `TestPreV24*` or similar; they should be RARE — most tests just construct test data, they don't pin shape behavior.

### Step 8 — Run tests + verify + update flight log

```bash
# Migration suite:
docker exec the-one pytest tests/test_db_migration.py -x --timeout 30

# ACL + connectors:
docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30

# Broad backend:
docker exec the-one pytest --ignore=tests/browser -x --timeout 60
```

Expected: 2766+ passing / 4 skipped / 0 errors / 0 failures.

Append L3 progress entry to flight log. Update leg status `in-flight` → `landed`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Migration test for the v7-strip scenario**: F11 v23 migration introduced segment-level re-entry guards for this. v24 follows the same pattern — segment guards check `if peers and isinstance(peers[0], dict)` BEFORE transforming. If a test rewinds schema_version and re-runs ensure_schema, the segment guard short-circuits the transformation.
- **Tests that pin `dm_admission="allowlisted-peers-only"` Literal value**: any test asserting this Literal value will need updating to `"admin-approved"`. Pre-implementation grep: `grep -rn "allowlisted-peers-only" tests/ --include='*.py'` to enumerate.
- **Empty allowlist edge case**: if `allowlist["peers"] = []` post-v24, the `peer_entry = next(...)` returns None. The composition rule handles this: with `dm_admission="admin-approved"` and no peers, all DMs are denied (no one approved). With `dm_admission="all"` and no peers, DMs are admitted (everyone allowed). Verify both cases in the matrix.
- **`admit_dms=True` does NOT elevate**: per the Truth Table option (b), True and None behave identically. Cross-product matrix must explicitly verify this (2 cells: `admit_dms=True` with various peer/dm states should match `admit_dms=None` behavior).
- **Outbound guild_id semantic**: outbound has no envelope guild_id. Implementer chooses (a) outbound matches channel_id alone (ignore guild_id constraint) OR (b) outbound only admits null-guild_id channels (strict). Recommend (a) for backward-compat with operator's existing outbound writes; document choice in helper docstring.
- **`tests/test_db_migration.py` TestSchemaV23 class stays untouched**: it pins pre-v24 schema state with `connector_account_id` and 5-axis flat allowlist. Per L1's Category A discipline, do not modify.
- **`docker-compose.yml` discipline**: continues — explicit `git add` of L3 files only; `docker-compose.yml` stays unstaged.

- **Per-agent `peers` entries' `dm_allowed` field — not consulted by Truth Table** (cycle-1 question #1): the migration sets per-agent `peers[*].dm_allowed = True` by default (line ~235 in migration body); ACCOUNT-SCOPE per-peer `dm_allowed` is what the Truth Table consults. Per-agent `peers` entries carry the field for structural-uniformity (same shape as account-scope) but the ACL helpers DO NOT consult per-agent `peers[*].dm_allowed` in F12. The per-agent overlay only narrows WHICH peers are admitted (peers-axis); DM admission is decided at account-scope. If a future flight wants per-agent DM granularity (e.g. "this peer can DM agent A but not agent B"), that would be a substrate change. Document this in `_admits_inbound_dm` helper docstring.

- **Defensive assertion at end of v24 migration**: after the `for row in connector_rows` loop, add a verification pass: `for row in connector_rows: assert "allowlisted-peers-only" not in (row['config'] or '')` to catch any row the rewrite logic missed. Optional safety net (cycle-1 suggestion).

- **`tests/test_lifespan.py` inclusion in sweep**: cycle-1 verified `test_lifespan.py` does NOT appear in the allowlist/connector_acls grep output. May be removable from Step 7's sweep list — implementer's call. Defaulting to include is safer (run the grep at implementation time; if no hits, no edits needed).

- **Index rename non-concern**: SQLite migrations run with a single connection; DROP + CREATE is atomic-from-the-app's-perspective (no concurrent reads during migration). Not a concern.

## Files Affected

**Production code** (5 files):
- `the_one/connectors/_acl.py` — 4 helpers updated (`_admits_inbound_dm`, `_admits_inbound_guild`, `admits_outbound`, `admits_dm_peer`)
- `the_one/db/models.py` — Pydantic allowlist validator updated for structured shape + new Literal value
- `the_one/agent/config.py` — Pydantic connector_acls validator updated for parallel structured shape
- `the_one/db/schema.py` — v24 migration block added (after v23 at `:1155`)
- `the_one/connectors/_inbound.py` — peer-add path uses structured-dict construction
- `the_one/connectors/_discord.py` — peer-enumeration consumer reads structured dicts
- `the_one/interfaces/web/api.py` — peer-approval handler uses structured-dict construction

**Test code** (8+ files):
- `tests/test_db_migration.py` — new `TestSchemaV24` class (5+ tests)
- `tests/test_connectors_acl.py` — new `TestDmAdmissionCompositionMatrix` (12 cells) + existing-fixture updates
- `tests/test_connectors_routing.py`, `tests/test_connectors_inbound.py` — fixture updates
- `tests/test_db_repositories.py`, `tests/test_db_api.py`, `tests/test_app_pending_approval_merge.py` — fixture updates
- `tests/_connector_dispatch_helpers.py`, `tests/test_lifespan.py` — fixture updates

**Flight artifacts** (mandatory updates):
- `missions/11-discord-connector-depth/flights/12-hierarchical-allowlist-and-snake-case-rename/flight-log.md` — append L3 progress entry
- This file (`legs/03-storage-shape-v24-migration-and-acl-semantics.md`) — status → `landed`

**Explicitly NOT affected in L3**:
- Any frontend file (L4 scope)
- `tests/browser/*.py` (L4 scope)
- `tests/test_db_migration.py` pre-v24 TestSchemaVN classes (Category A — preserve)
- `docker-compose.yml` (operator's local dev state)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (v24 migration, validators, ACL helpers, peer-consumer sites, TestSchemaV24, cross-product matrix, fixture updates, tests green)
- [x] L3 atomicity boundary verified (no frontend, no browser tests)
- [x] Migration test suite green
- [x] Focused ACL + connectors suites green
- [x] Broad backend suite green at 2766+ passing
- [x] Browser baseline preserved
- [x] Flight-log L3 progress entry appended
- [x] This leg's status set to `landed` (NOT `completed` — Phase 2d commits)
- [x] Do NOT update flight-spec leg checkbox (commit leg does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d batches all 4 legs into one review + one commit)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-29, leg-design time):

| Citation | Classification | Resolution |
|----------|---------------|------------|
| `the_one/db/schema.py:1155` — `version = 23` (end of v23 block) | OK | Verified by grep; v24 inserts after this line |
| `the_one/db/models.py:308+` — allowlist validator | OK | Verified by reading; current validator accepts 5-axis flat shape with `dm_admission` Literal at :354-356 |
| `the_one/agent/config.py:262+` — `_validate_connector_acls` | OK | Verified by grep; current validator accepts `list[str] \| bool \| None` per-axis shape with `admit_dms` at :313 |
| `the_one/connectors/_acl.py` post-L2 (575 LOC, 7 functions) | OK | Verified post-L2 land |
| `the_one/connectors/_inbound.py:467-476` — pairing-approve peer-add | OK | Verified by reading; structure matches spec |
| `the_one/interfaces/web/api.py:2727-2740` — `approve_peer_approval` mutation | OK | Verified by reading; peer-add at `:2731-2733`, allowlist write at `:2734` |
| `the_one/connectors/_discord.py:1651` — pairing-resolver peer enumeration | OK | Verified by reading; `if envelope.peer_id in peers:` at the cited line |
| `tests/test_db_migration.py` TestSchemaV23 at lines ~2992-3390 (per F11 L1 record) | OK | TestSchemaV24 to be inserted after this class |
| 12-cell cross-product matrix scope | OK (spec-derived) | `admit_dms × dm_admission × dm_allowed × in_allowlist` = 3×3×2×2 = 36 full Cartesian; 12 representative cells per architect-confirmed scope |

9 citations verified clean against current code at leg design time. All references match live post-L2 state.
