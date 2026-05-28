# Leg: acl-dm-admission-substrate

**Status**: completed
**Flight**: [ACL DM-admission + channels-axis UI split](../flight.md)

## Objective

Land the substrate for the DM-admission axis split: extend two strict Pydantic validators (account-scope allowlist + per-agent ACL) to accept the new `dm_admission` Literal-string and `admit_dms` bool fields; add migration v22 that walks existing rows; re-order `_acl.py:admits_inbound` so DMs skip channels/guilds/roles axes and consult the new `dm_admission` + existing peers axes. All in one leg because the field additions, validator extensions, dispatcher consultation, and tests are tightly coupled — partial landings would leave the system in an inconsistent state.

## Context

**Why one leg.** Splitting this would mean either (a) landing field schema without dispatcher consultation (substrate-without-effect — tests would fail because the new field is set but the dispatcher doesn't read it) or (b) landing dispatcher consultation without field validation (dispatcher reads a field that the Pydantic models reject — also fails). The atomic-leg-pattern convention applies cleanly.

**Cycle-1 + cycle-2 Architect findings** drive the shape (per F10 flight artifact):
- §1 + §3: Pydantic validators at `db/models.py:305-341` and `agent/config.py:230,262-322` are STRICT — they enforce both an exact-keys set AND a uniform value-type (list[str]). The new keys violate both invariants and need explicit validator extension with branch-by-key value-type validation.
- §2: Re-ordering `admits_inbound` changes how DMs interact with channels/guilds/roles axes — the new logic skips these axes for DMs and consults `dm_admission` instead.
- §4: Migration v22 mirrors the v7 row-rewrite precedent at `schema.py:286-303` (NOT the ALTER-ADD-COLUMN v17/v18/v20/v21 — those are wrong-shape precedents).

**Per L1 cycle-1 leg review (correction to F10 flight cycle-1 claim)**: the F10 flight artifact's claim that "3 existing tests at `tests/test_connectors_acl.py:486, 592, 605` MUST be inverted" rests on a flawed premise. Verified by reading the test bodies: ALL THREE of those tests call `admits_inbound(...)` WITHOUT passing `is_dm=True` (it defaults to `False`). Under the re-ordered dispatcher (§2), `is_dm=False` keeps the channels/guilds/roles axes in play (in the `else` branch) — so those tests pass UNCHANGED under L1's code. No inversion needed.

What L1 ACTUALLY needs in tests: add 3 NEW `is_dm=True` analogues to the existing 3 deny-when-restricted tests, pinning the new orthogonal-DM-admission semantic explicitly. The existing 3 tests stay untouched (they correctly pin `is_dm=False` behavior, which is unchanged).

**Cycle-1 dispatcher consult-site insertion ordering**. The current `admits_inbound` body (`_acl.py:311-349`) checks axes in this order: peers (account) → channels (account) → guilds (account) → roles (account) → peers (per-agent) → channels (per-agent) → guilds (per-agent) → roles (per-agent). L1 re-orders to:

For account-scope (lines 311-349):
1. peers (always consulted — both DMs and guild messages need allowlist membership when peers is non-empty)
2. **NEW** dm_admission gate (consulted only when `is_dm=True`):
   - `"none"` → deny
   - `"allowlisted-peers-only"` → admit IFF peer_id was admitted by step 1 (the peers check above), else deny
   - `"all"` → admit
3. channels (consulted only when `is_dm=False`)
4. guilds (consulted only when `is_dm=False`)
5. roles (consulted only when `is_dm=False`)

For per-agent (lines 350+):
6. peers (always consulted, unchanged)
7. **NEW** admit_dms gate (consulted only when `is_dm=True`):
   - `False` → deny
   - `True` or `None` → continue
8. channels (consulted only when `is_dm=False`, unchanged)
9. guilds (consulted only when `is_dm=False`, unchanged)
10. roles (consulted only when `is_dm=False`, unchanged)

The pattern: peer-axis is the universal gate; everything else is DM-vs-guild-context dependent.

**Migration v22 row-rewrite shape** (mirrors `schema.py:286-303` v7):
```python
if version < 22:
    async with conn.execute("SELECT id, config FROM connector_accounts") as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        account_id = row[0]
        config_json = row[1] or "{}"
        config = json.loads(config_json)
        allowlist = config.get("allowlist")
        if allowlist is not None and "dm_admission" not in allowlist:
            channels = allowlist.get("channels") or []
            allowlist["dm_admission"] = "all" if not channels else "none"
            config["allowlist"] = allowlist
            await conn.execute(
                "UPDATE connector_accounts SET config = ? WHERE id = ?",
                (json.dumps(config), account_id),
            )
    await conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (22,)
    )
    await conn.commit()
    version = 22
```

Note: rows without an `allowlist` key at all are LEFT UNCHANGED — the Pydantic validator's default behavior covers them at read time. Rows with `allowlist` already containing `dm_admission` (defensive — shouldn't happen pre-v22 but the `if "dm_admission" not in allowlist` guard makes the migration idempotent).

**Validator-default coupling**: when a row WITHOUT `dm_admission` (e.g. fresh `ConnectorAccount(...)` constructor call from a test that doesn't set the field) flows through `model_validate`, the validator inserts `dm_admission = "allowlisted-peers-only"` (fresh-account default). The MIGRATION-INSERTED value for legacy rows (`"all"` or `"none"`) overrides this because it's already in the JSON. Two different defaults serving two different code paths.

## Inputs

- `the_one/db/models.py:305-341` — `ConnectorAccount.config` `@field_validator` (allowlist key/value validator). Extend.
- `the_one/agent/config.py:230` — `AgentConfig.connector_acls` outer type annotation. Widen.
- `the_one/agent/config.py:262-322` — `AgentConfig.connector_acls` `@field_validator`. Extend.
- `the_one/db/schema.py:12` — `CURRENT_VERSION = 21`. Bump to 22.
- `the_one/db/schema.py:286-303` — v7 row-rewrite precedent. Mirror.
- `the_one/connectors/_acl.py:251-431` — `admits_inbound` function (full span). Re-order axis checks. Account-scope block at 311-349; per-agent block at 350-431 (~80 LOC across 4 axes, each with tri-state empty-list sentinel).
- `the_one/connectors/_acl.py:296-302` — F8 L8 "DMs out-of-scope under guild restriction" posture docstring. Update to reflect inversion.
- `tests/test_connectors_acl.py` (730 LOC, 58 tests) — extend with 9 new + 3 inverted tests.
- `tests/test_connectors_acl.py:486` — `test_account_guilds_restrictive_denies_dm_envelope` (despite the name, DOES NOT pass `is_dm=True`; defaults to False). Stays untouched; L1 adds an `is_dm=True` analogue.
- `tests/test_connectors_acl.py:592` — `test_account_roles_empty_member_roles_denies_when_restricted` (same: no `is_dm=True`). Stays untouched.
- `tests/test_connectors_acl.py:605` — `test_account_roles_member_roles_none_denies_when_restricted` (same). Stays untouched.
- `tests/test_db_migration.py:243` — `assert CURRENT_VERSION == 21` literal inside multi-line assert (lines 243-246 include the error message). L1 bumps to 22.
- `tests/test_db_migration.py:2453+` — `TestSchemaV21` class (last migration test class; F9 L2 added). L1 adds `TestSchemaV22` after it.
- `tests/test_db_repositories.py` — repository round-trip tests for the new fields.
- `tests/test_api_connector_account_config_validation.py` — likely needs additions for the new validator branch (per-key value-type validation of `dm_admission`).

## Outputs

- `the_one/db/models.py` — validator extended: `"dm_admission"` added to allowed keys; per-key branch validates `dm_admission` as `Literal["none", "allowlisted-peers-only", "all"]`; absent-key default `"allowlisted-peers-only"` set during validation.
- `the_one/agent/config.py` — outer annotation widened to `dict[str, dict[str, list[str] | bool | None]] | None`; validator extended: `"admit_dms"` added to allowed inner-keys; per-key branch validates `admit_dms` as `bool | None` (`None` and absent both meaning inherit).
- `the_one/db/schema.py` — `CURRENT_VERSION = 22`; new `if version < 22:` block walking `connector_accounts` rows per the legacy-preservation rule.
- `the_one/connectors/_acl.py` — `admits_inbound` re-ordered per §1-§2; docstring updated documenting the new "DMs orthogonal to guild restriction" posture (replacing F8 L8's "out-of-scope" framing).
- `tests/test_connectors_acl.py` — +9 new tests covering account-scope dm_admission × peer-allowlist combinations (all with `is_dm=True`) + 3 per-agent admit_dms tests + 3 new `is_dm=True` analogues to the existing deny-when-restricted tests (pin the new orthogonal-DM semantic on guilds/roles axes). Existing 3 tests at `:486, 592, 605` stay untouched.
- `tests/test_db_migration.py` — new `TestSchemaV22` class with fresh-DB / idempotent / 3 legacy-preservation tests.
- `tests/test_db_repositories.py` — round-trip tests for new `dm_admission` + `admit_dms` fields.
- `tests/test_api_connector_account_config_validation.py` — new branches covering `dm_admission` validator (accepts valid Literals; rejects invalid strings; rejects non-strings).
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — append L1 progress entry.

L1 does NOT touch: any UI files (L2 + L3 own those), dispatcher entry-point (`_inbound.py` only calls `admits_inbound`; the call site is unchanged), repository CRUD (the existing CRUD round-trips JSON columns; no schema change to row shape beyond the new key inside the JSON).

## Acceptance Criteria

- [ ] `the_one/db/schema.py:CURRENT_VERSION == 22`.
- [ ] `ensure_schema` v22 block walks `connector_accounts` rows:
  - Rows with `allowlist.channels` empty/absent get `allowlist.dm_admission = "all"`.
  - Rows with `allowlist.channels` non-empty get `allowlist.dm_admission = "none"`.
  - Rows without `allowlist` are untouched.
  - Idempotent: re-run produces no further mutation; schema_version row v22 appears exactly once.
- [ ] `ConnectorAccount.config` validator at `db/models.py:305-341`:
  - Accepts `dm_admission` as an allowed key in `allowlist`.
  - Rejects `dm_admission` values not in `{"none", "allowlisted-peers-only", "all"}` with a clear error message.
  - Sets `dm_admission = "allowlisted-peers-only"` when `allowlist` is present but `dm_admission` is absent (fresh-account default).
  - Existing `peers`, `channels`, `guilds`, `roles` validation unchanged.
- [ ] `AgentConfig.connector_acls` validator at `agent/config.py:262-322`:
  - Outer type annotation widened to permit `bool | None` value types (in addition to existing `list[str] | None`).
  - Accepts `admit_dms` as an allowed inner key.
  - Validates `admit_dms` as `bool | None`; rejects non-bool non-None values with a clear error.
  - Existing axes (`peers`, `channels`, `guilds`, `roles`) keep their `list[str] | None` validation.
- [ ] `the_one/connectors/_acl.py:admits_inbound` consults the new fields per the re-ordered axis logic:
  - When `is_dm=True`: peers axis enforced, then `dm_admission` gate; channels/guilds/roles axes SKIPPED at both account-scope and per-agent scope.
  - When `is_dm=False`: peers axis enforced, then channels/guilds/roles enforced; `dm_admission` SKIPPED.
  - Per-agent `admit_dms=False` denies DMs even when account-scope `dm_admission` permits.
- [ ] Docstring at `_acl.py:296-302` updated to document the new "DMs orthogonal to guild restriction" posture, replacing F8 L8's "out-of-scope" framing.
- [ ] 9 new tests in `tests/test_connectors_acl.py` covering the 3×3 matrix of account-scope `dm_admission` ∈ {`none`, `allowlisted-peers-only`, `all`} × peer-allowlist state ∈ {peer-on-allowlist, peer-not-on-allowlist, peers-list-empty}, all with `is_dm=True`.
- [ ] 3 per-agent `admit_dms` tests: `admit_dms=False` overrides account-scope `dm_admission="all"`; `admit_dms=False` is irrelevant when `is_dm=False` (guild messages unaffected); `admit_dms=None` inherits account-scope.
- [ ] 3 new `is_dm=True` analogues added (DO NOT rename or modify the existing 3 tests at `:486, 592, 605` — they pin `is_dm=False` behavior which is unchanged under L1):
  - `test_account_guilds_restrictive_admits_dm_envelope_when_dm_admission_permits` — same setup as `:486` but `is_dm=True` + `allowlist.dm_admission="all"` + `allowlist.peers=["P1"]`; assert admit.
  - `test_account_roles_empty_member_roles_admits_dm_regardless_of_role_restriction` — same setup as `:592` but `is_dm=True` + `dm_admission="all"` + peer allowlisted; assert admit.
  - `test_account_roles_member_roles_none_admits_dm_regardless_of_role_restriction` — same setup as `:605` but `is_dm=True` + similar dm_admission setup; assert admit.
- [ ] Existing 3 tests at `:486, 592, 605` PASS UNCHANGED (no rename, no body changes; the new dispatcher still produces the same deny outcome when `is_dm=False`).
- [ ] New `TestSchemaV22` class in `tests/test_db_migration.py`:
  - `test_v22_fresh_db_has_no_legacy_rewrite` (fresh DB has no rows; migration is a no-op writing only the schema_version row).
  - `test_v22_migration_idempotent_on_rerun` (running ensure_schema twice produces one v22 entry; existing rows preserve their post-first-run state).
  - `test_v22_legacy_row_with_empty_channels_gets_dm_admission_all`.
  - `test_v22_legacy_row_with_non_empty_channels_gets_dm_admission_none`.
  - `test_v22_legacy_row_without_allowlist_untouched`.
- [ ] Repository round-trip tests in `tests/test_db_repositories.py`:
  - `ConnectorAccount` with `allowlist.dm_admission` set survives create → list → get → update → get.
  - `AgentConfig` with `connector_acls[acct].admit_dms = False` survives save → load round-trip.
- [ ] API validation tests in `tests/test_api_connector_account_config_validation.py`:
  - Valid `dm_admission` values accepted via POST/PUT.
  - Invalid string rejected with HTTP 422.
- [ ] Existing tests pass unchanged. The 3 tests at `:486, 592, 605` produce the same deny outcomes under L1 because they default to `is_dm=False`.
- [ ] Full suite passes; suite count rises by ~24-25 tests (9 dm_admission matrix + 3 per-agent admit_dms + 3 new is_dm=True analogues + 5 migration + 2 repo + 2-3 API).

## Verification Steps

```bash
# Migration tests
docker exec the-one pytest tests/test_db_migration.py::TestSchemaV22 -x --timeout 30 -v

# ACL tests (all — existing tests including :486, :592, :605 still pass unchanged; new tests pass)
docker exec the-one pytest tests/test_connectors_acl.py -x --timeout 30 -v

# Repository tests
docker exec the-one pytest tests/test_db_repositories.py -k "dm_admission or admit_dms" -x --timeout 30 -v

# API validation
docker exec the-one pytest tests/test_api_connector_account_config_validation.py -x --timeout 30 -v

# Full suite (post-F9 baseline: 2721)
docker exec the-one pytest --timeout 60 -q

# Quick grep — confirm validator extension landed
grep -n "dm_admission" the_one/db/models.py
grep -n "admit_dms" the_one/agent/config.py

# Confirm no stray CURRENT_VERSION literal lingers at the wrong value
grep -rn "CURRENT_VERSION == 21" tests/ the_one/
# Expected: zero matches (only the bumped == 22 should appear).
```

Expected: green; suite count rises ~17-20.

## Implementation Guidance

### Sub-step A — Schema migration v22

1. Edit `the_one/db/schema.py:12` — bump `CURRENT_VERSION = 21` → `CURRENT_VERSION = 22`.
2. Append a new migration block at the tail of `ensure_schema` (after the v21 block ~line 822). Mirror the v7 row-rewrite shape from `schema.py:286-303`:

```python
    if version < 22:
        # Mission 11 Flight 10 Leg 1: dm_admission axis on
        # connector_accounts.config.allowlist. Row-rewrite migration
        # (NOT ALTER ADD COLUMN — the column is JSON-encoded TEXT, so
        # the schema change is shape-only and lives inside the JSON).
        # Legacy-preservation rule:
        #   - allowlist.channels empty/absent → dm_admission="all"
        #     (existing behavior admitted all DMs)
        #   - allowlist.channels non-empty → dm_admission="none"
        #     (existing behavior denied all DMs against channels mismatch)
        # Rows without an allowlist key are untouched; the Pydantic
        # validator default handles them at read time.
        # Mirrors the v7 row-rewrite precedent at schema.py:286-303.
        async with conn.execute(
            "SELECT id, config FROM connector_accounts"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            account_id = row[0]
            config_json = row[1] or "{}"
            config = json.loads(config_json)
            allowlist = config.get("allowlist")
            if allowlist is None or "dm_admission" in allowlist:
                continue  # skip rows without allowlist or already migrated
            channels = allowlist.get("channels") or []
            allowlist["dm_admission"] = "all" if not channels else "none"
            config["allowlist"] = allowlist
            await conn.execute(
                "UPDATE connector_accounts SET config = ? WHERE id = ?",
                (json.dumps(config), account_id),
            )
        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (22,)
        )
        await conn.commit()
        version = 22
```

3. Bump the literal at `tests/test_db_migration.py:243` (the `assert CURRENT_VERSION == 21` lives inside a multi-line `assert (...)` at lines 243-246): change `== 21` → `== 22` AND update the error-message string at lines 244-246 to reference v22. Append a v22 entry to the preceding migration-history comment block (`v22 added dm_admission to connector_accounts.config.allowlist via row-rewrite (M11 F10 L01 — DM admission axis split)`).

### Sub-step B — Pydantic validator extension (account-scope)

Edit `the_one/db/models.py:305-341` — extend the existing `allowlist` validator. Two changes:

1. **Allowed-keys set** at line 318 — add `"dm_admission"`:
```python
extra = set(allowlist.keys()) - {"peers", "channels", "guilds", "roles", "dm_admission"}
```

2. **Per-key value validation loop** at lines 328-341 — branch by key:
```python
for key in ("peers", "channels", "guilds", "roles"):
    if key not in allowlist:
        continue
    entries = allowlist[key]
    if not isinstance(entries, list):
        raise ValueError(
            f"config['allowlist'][{key!r}] must be a list of strings"
        )
    for i, item in enumerate(entries):
        if not isinstance(item, str):
            raise ValueError(
                f"config['allowlist'][{key!r}][{i}] must be a string"
            )

# M11 F10 L1: dm_admission axis validation + default insertion.
# Literal["none", "allowlisted-peers-only", "all"]. Default for
# absent-key on a present allowlist: "allowlisted-peers-only" (fresh-
# account default — F9 flow's intended state). The v22 migration
# walks legacy rows and inserts "all" or "none" per the legacy-
# preservation rule, so legacy rows reaching this validator after
# migration ALREADY carry dm_admission and skip the default.
dm_admission = allowlist.get("dm_admission")
if dm_admission is None:
    allowlist["dm_admission"] = "allowlisted-peers-only"
elif dm_admission not in ("none", "allowlisted-peers-only", "all"):
    raise ValueError(
        f"config['allowlist']['dm_admission'] must be one of "
        f"{{'none', 'allowlisted-peers-only', 'all'}}; got {dm_admission!r}"
    )
```

The `allowlist["dm_admission"] = ...` mutation is in-place on the dict the validator is processing — this is the standard pattern for default-insertion in Pydantic v2 `@field_validator(mode="after")`. The validator returns `value` (the outer config dict) at the end of the existing function; the inner allowlist dict mutation propagates.

### Sub-step C — Pydantic validator extension (per-agent)

Edit `the_one/agent/config.py:230` — widen the outer type annotation:
```python
connector_acls: dict[str, dict[str, list[str] | bool | None]] | None = None
```

Edit `the_one/agent/config.py:262-322` — extend the validator. The change is at line 310 (allowed-keys set):
```python
extra = keys - {"peers", "channels", "guilds", "roles", "admit_dms"}
```

Plus add a branch-by-key value-type check (the outer annotation enforces `list[str] | bool | None` uniformly, but we want stricter per-key: `peers`/`channels`/`guilds`/`roles` are list[str] | None; `admit_dms` is bool | None). Add after the `extra` / `missing` checks at line 322:

```python
# M11 F10 L1: per-key value-type validation.
# The widened annotation `dict[str, list[str] | bool | None]` accepts
# either type for any key; this branch enforces the intended type per
# key.
for key, value_at_key in acl.items():
    if key == "admit_dms":
        if value_at_key is not None and not isinstance(value_at_key, bool):
            raise ValueError(
                f"connector_acls[{account_id!r}]['admit_dms'] must be "
                f"bool or None; got {type(value_at_key).__name__}"
            )
    else:
        # peers, channels, guilds, roles — list[str] | None
        if value_at_key is not None and not isinstance(value_at_key, list):
            raise ValueError(
                f"connector_acls[{account_id!r}][{key!r}] must be "
                f"list[str] or None; got {type(value_at_key).__name__}"
            )
        if isinstance(value_at_key, list):
            for i, item in enumerate(value_at_key):
                if not isinstance(item, str):
                    raise ValueError(
                        f"connector_acls[{account_id!r}][{key!r}][{i}] "
                        f"must be a string"
                    )
```

Note: do NOT add `admit_dms` to the `missing` required-keys check (line 316) — it's optional like `guilds` and `roles`.

### Sub-step D — Dispatcher re-order in `_acl.py:admits_inbound`

Edit `the_one/connectors/_acl.py:251-431` (full function span; account-scope at 311-349; per-agent at 350-431). The function currently checks axes in this order: peers → channels → guilds → roles (account-scope), then same order per-agent. L1 re-orders to put DM-vs-guild branching ahead of the channels/guilds/roles checks.

Re-shape the account-scope block (lines 311-349):

```python
account_id = account.id
member_roles_set = set(member_roles or [])
allowlist = account.config.get("allowlist")
if allowlist is not None:
    # 1. peers (always consulted — DMs and guild messages both need
    #    allowlist membership when peers is non-empty)
    allowed_peers = allowlist.get("peers", [])
    if allowed_peers and peer_id not in allowed_peers:
        return (
            False,
            f"peer_id {peer_id!r} is not admitted on account "
            f"{account_id!r}",
        )

    # M11 F10 L1: DM-context branch.
    # When is_dm=True, channels/guilds/roles axes are skipped (they
    # restrict guild-context messages, not DMs). dm_admission gates
    # DM admission orthogonally.
    if is_dm:
        dm_admission = allowlist.get("dm_admission", "allowlisted-peers-only")
        if dm_admission == "none":
            return (
                False,
                f"DM denied: account {account_id!r} dm_admission is 'none'",
            )
        if dm_admission == "allowlisted-peers-only":
            # peers axis above already enforced this when allowed_peers
            # was non-empty. If allowed_peers is empty AND dm_admission
            # is allowlisted-peers-only, no peer has been approved yet:
            # deny.
            if not allowed_peers:
                return (
                    False,
                    f"DM denied: account {account_id!r} dm_admission is "
                    f"'allowlisted-peers-only' and no peers are on the "
                    f"allowlist",
                )
        # dm_admission == "all" or "allowlisted-peers-only" with the
        # peer on allowlist: fall through to per-agent check.
    else:
        # 2. channels / guilds / roles (consulted only when NOT a DM)
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and channel_id not in allowed_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not admitted on account "
                f"{account_id!r}",
            )
        allowed_guilds = allowlist.get("guilds", [])
        if allowed_guilds and guild_id not in allowed_guilds:
            return (
                False,
                f"guild_id {guild_id!r} is not admitted on account "
                f"{account_id!r}",
            )
        allowed_roles = allowlist.get("roles", [])
        if allowed_roles and not (member_roles_set & set(allowed_roles)):
            return (
                False,
                f"peer roles do not overlap with admitted roles on account "
                f"{account_id!r}",
            )
```

Per-agent block (lines 350-431) — concrete reshape. Existing peers check unchanged; insert `admit_dms` gate after it (consulted only on DMs); existing channels/guilds/roles checks (each with their tri-state empty-list sentinel logic) gated on `not is_dm`:

```python
if agent_acl is not None:
    # Peers axis (always consulted — tri-state semantic preserved).
    agent_peers = agent_acl.get("peers")
    if agent_peers is None:
        pass  # inherit account-scope
    elif agent_peers == []:
        return (
            False,
            f"peer_id {peer_id!r} is not admitted for this agent on "
            f"account {account_id!r} (per-agent peers axis is "
            f"explicitly empty)",
        )
    elif peer_id not in agent_peers:
        return (
            False,
            f"peer_id {peer_id!r} is not admitted for this agent on "
            f"account {account_id!r}",
        )

    # M11 F10 L1: DM-context branch (per-agent).
    if is_dm:
        admit_dms = agent_acl.get("admit_dms")
        if admit_dms is False:
            return (
                False,
                f"DM denied: agent admit_dms is False on account "
                f"{account_id!r}",
            )
        # admit_dms is None (inherit) or True (explicit-affirm; same
        # effect as inherit when account-scope permits): fall through.
        # Account-scope dm_admission gate above already validated DM
        # admissibility; per-agent override has consumed its turn.
    else:
        # Guild-context branch: channels/guilds/roles axes consulted
        # exactly as pre-L1. Each axis retains its tri-state shape.

        # Channels axis (per-agent).
        agent_channels = agent_acl.get("channels")
        if agent_channels is None:
            pass  # inherit account-scope
        elif agent_channels == []:
            # NOTE: pre-L1, this sentinel admitted DMs unconditionally
            # ("DMs-only override"). Under L1, DMs take the if-is_dm
            # branch above, so this branch is unreachable for DMs.
            # The empty-list sentinel's effective semantic for the
            # not-is_dm branch is "deny all guild channels for this
            # agent on this account." Documented in the docstring
            # update (see below).
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this "
                f"agent on account {account_id!r} (per-agent channels "
                f"axis is explicitly empty; guild-context)",
            )
        elif channel_id not in agent_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this "
                f"agent on account {account_id!r}",
            )

        # Guilds axis (per-agent) — unchanged from pre-L1.
        agent_guilds = agent_acl.get("guilds")
        if agent_guilds is None:
            pass
        elif agent_guilds == []:
            return (
                False,
                f"guild_id {guild_id!r} is not admitted for this agent "
                f"on account {account_id!r} (per-agent guilds axis is "
                f"explicitly empty)",
            )
        elif guild_id not in agent_guilds:
            return (
                False,
                f"guild_id {guild_id!r} is not admitted for this agent "
                f"on account {account_id!r}",
            )

        # Roles axis (per-agent) — unchanged from pre-L1.
        agent_roles = agent_acl.get("roles")
        if agent_roles is None:
            pass
        elif agent_roles == []:
            return (
                False,
                f"peer roles do not overlap with admitted roles for "
                f"this agent on account {account_id!r} (per-agent "
                f"roles axis is explicitly empty)",
            )
        elif not (member_roles_set & set(agent_roles)):
            return (
                False,
                f"peer roles do not overlap with admitted roles for "
                f"this agent on account {account_id!r}",
            )

return True, ""
```

**Critical semantic shift on the `agent_channels == []` sentinel**: pre-L1, the sentinel at lines 372-378 was "DMs-only override" — when `agent_channels=[]` AND `is_dm=True`, admit unconditionally. Under L1, the entire `agent_channels` axis lives inside `if not is_dm:` — so `agent_channels=[]` only fires for guild-context messages, where it denies (no guild channels admitted for this agent). The "DMs-only" semantic that the empty-list sentinel encoded is now expressed via the orthogonal account-scope `dm_admission` + per-agent `admit_dms` mechanism — operators wanting DMs-only set `dm_admission="all"` (or `"allowlisted-peers-only"`) on the account and let `admit_dms` inherit.

**Docstring update at `_acl.py:296-302`** — replace the existing F8 L8 paragraph with:

```
**DM-with-guild-restriction posture (M11 F10 L1)** — DMs are
orthogonal to guild-context restrictions. The ``is_dm`` parameter
gates which axes get consulted: ``is_dm=True`` consults only
the peers axis + the new account-scope ``dm_admission`` axis
(Literal[``"none"``, ``"allowlisted-peers-only"``, ``"all"``]) +
the per-agent ``admit_dms`` axis (``bool | None``, opt-out
sentinel). ``is_dm=False`` consults the peers/channels/guilds/
roles axes per the established 4-axis ACL semantics. This
inverts the F8 L8 documented "DMs out-of-scope under guild
restriction" posture (which conflated guild-channel restriction
with DM-admission scope); F10 L1 splits them per the F9 L8 HAT
findings.
```

Also sweep `_acl.py:284-289, 304-309, 330-332` for related F8 L8 comment headers and update text references to reflect the new posture.

### Sub-step E — Tests

**5.1 New ACL tests** (in `tests/test_connectors_acl.py`):

9 tests covering the 3×3 matrix. **Each cell specifies EXACT `allowed_peers` list state to disambiguate**:

| dm_admission | allowed_peers state | inbound peer_id | Expected |
|--------------|---------------------|-----------------|----------|
| `"none"` | `["P1"]` | `"P1"` | deny (dm_admission gate fires after peers passes) |
| `"none"` | `["P1"]` | `"P2"` | deny (peers axis fires first; either path denies) |
| `"none"` | `[]` | `"P1"` | deny (dm_admission gate fires; peers empty doesn't restrict) |
| `"allowlisted-peers-only"` | `["P1"]` | `"P1"` | admit (peers passes; dm_admission permits this case) |
| `"allowlisted-peers-only"` | `["P1"]` | `"P2"` | deny (peers axis denies first) |
| `"allowlisted-peers-only"` | `[]` | `"P1"` | deny (dm_admission rule: no one approved yet) |
| `"all"` | `["P1"]` | `"P1"` | admit |
| `"all"` | `["P1"]` | `"P2"` | deny (peers axis still denies — non-empty peers restricts even when dm_admission is `"all"`) |
| `"all"` | `[]` | `"P1"` | admit (peers empty doesn't restrict; dm_admission permits) |

Each test calls `admits_inbound(account, agent_acl=None, peer_id=..., channel_id="dm-channel", is_dm=True, guild_id=None, member_roles=None)`.

Plus 3 per-agent admit_dms tests:
- `test_per_agent_admit_dms_false_overrides_account_admit` — account `dm_admission=all`, agent `admit_dms=False`, `is_dm=True` → deny.
- `test_per_agent_admit_dms_false_irrelevant_for_guild_messages` — account `dm_admission=none`, agent `admit_dms=False`, `is_dm=False` → admit (the per-agent admit_dms is DM-only).
- `test_per_agent_admit_dms_none_inherits_account` — account `dm_admission=all`, agent `admit_dms=None`, `is_dm=True` → admit.

**Important test fixture note**: when constructing `agent_acl` dicts that pass through Pydantic validation (e.g. via `AgentConfig(...)`), the validator REQUIRES `peers` AND `channels` keys (per existing line 316 invariant). Test inputs must include them — e.g. `{"peers": None, "channels": None, "admit_dms": False}`. When passing `agent_acl` directly to `admits_inbound` (bypassing Pydantic), the dispatcher doesn't enforce required-keys — but matching the validator's shape keeps the tests faithful to production paths.

**5.2 Add 3 new `is_dm=True` analogues** in `tests/test_connectors_acl.py`:

**DO NOT rename or modify** the existing tests at `:486, 592, 605`. They pin `is_dm=False` behavior (axis defaults), which is unchanged under L1. Their deny outcomes still hold.

Add 3 NEW tests adjacent to each existing test (so the pair sits together) that flip `is_dm` to True and add appropriate `dm_admission` + `peers` setup:

- `test_account_guilds_restrictive_admits_dm_when_dm_admission_permits` (near `:486`): same setup but `is_dm=True`, `allowlist.dm_admission="all"`, `allowlist.peers=["P1"]`; assert admit. Pins: guilds-axis restriction is irrelevant for DMs under the new posture.
- `test_account_roles_empty_member_roles_admits_dm_when_dm_admission_permits` (near `:592`): same setup but `is_dm=True`, `dm_admission="all"`, peers allowlisted; assert admit. Pins: roles-axis restriction is irrelevant for DMs.
- `test_account_roles_member_roles_none_admits_dm_when_dm_admission_permits` (near `:605`): same setup but `is_dm=True`, `dm_admission="all"`, peers allowlisted; assert admit. Pins: missing member_roles + restrictive roles axis irrelevant for DMs.

The pair-of-tests pattern explicitly documents the orthogonality: `is_dm=False` keeps guild-context restriction; `is_dm=True` consults dm_admission instead.

**5.3 Migration tests** (`tests/test_db_migration.py` — new `TestSchemaV22` class):

5 tests per the Acceptance Criteria list. Mirror the `TestSchemaV21` pattern from F9 L2 for fresh-DB + idempotent tests; add row-rewrite tests using the connector_accounts table.

**5.4 Repository tests** (`tests/test_db_repositories.py`):

2 round-trip tests for the new fields (one for ConnectorAccount, one for AgentConfig).

**5.5 API validation tests** (`tests/test_api_connector_account_config_validation.py`):

2-3 tests: valid values, invalid string, missing-from-validator-default behavior.

### Sub-step F — Flight log

Append L1 entry to `flight-log.md`:

```
### {date} — L1 acl-dm-admission-substrate (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `the_one/db/schema.py` — CURRENT_VERSION 21 → 22; v22 row-rewrite block walking connector_accounts per legacy-preservation rule.
- `the_one/db/models.py` — ConnectorAccount.config validator: dm_admission added to allowed keys; Literal-string value validated; absent-key default "allowlisted-peers-only" inserted in-place.
- `the_one/agent/config.py` — connector_acls outer annotation widened to permit bool; admit_dms added to allowed inner keys; per-key value-type branch validation.
- `the_one/connectors/_acl.py` — admits_inbound re-ordered: DMs skip channels/guilds/roles, consult dm_admission + peers; per-agent admit_dms gates DM admission. F8 L8 posture docstring updated.
- `tests/test_connectors_acl.py` — +9 dm_admission matrix tests, +3 per-agent admit_dms tests, +3 new is_dm=True analogues adjacent to the existing `:486, 592, 605` deny tests. Existing 3 tests untouched.
- `tests/test_db_migration.py` — TestSchemaV22 class + literal bump at `:243`.
- `tests/test_db_repositories.py` — +2 round-trip tests.
- `tests/test_api_connector_account_config_validation.py` — +N tests for dm_admission validator branch.

**Test outcomes**: full suite 2721 → ~2745 (+~24). All existing tests unchanged.

**Anomalies**: {document any}
```

## Edge Cases

- **`allowlist` is present but `dm_admission` is missing AND `model_validate` runs before migration**: validator inserts the fresh default `"allowlisted-peers-only"`. This is the production-realistic path for any code that constructs a `ConnectorAccount` in memory without going through the DB.
- **`allowlist` is None / absent on the account**: existing behavior preserved — no restriction. The whole `if allowlist is not None:` block is skipped. dm_admission has no effect. (Unusual configuration; the API enforces allowlist presence at create time.)
- **Migration runs on a row whose JSON has `allowlist=None`**: skip — the `if allowlist is None or "dm_admission" in allowlist: continue` guard handles this.
- **Migration runs twice on the same DB (idempotency)**: the second pass's `if "dm_admission" in allowlist: continue` short-circuits; no double-rewrites.
- **Test row constructed via `ConnectorAccount(config={"allowlist": {"peers": [], "channels": []}})` without dm_admission**: validator inserts default `"allowlisted-peers-only"`. Tests that depend on the dispatcher's behavior should pass `dm_admission="all"` explicitly if they want the legacy "admit DMs" semantic, OR set up `peers=[allowed_peer]` to satisfy `allowlisted-peers-only`.
- **Pre-existing dispatcher tests that don't pass `is_dm`**: `admits_inbound`'s `is_dm` parameter defaults to `False` (line 257). Pre-existing tests calling without it implicitly route to the `if not is_dm:` branch (channels/guilds/roles still consulted) — preserving their behavior. Only tests EXPLICITLY passing `is_dm=True` interact with the new dm_admission gate.
- **The 3 existing tests at `:486, 592, 605` do NOT pass `is_dm=True`** (verified by cycle-1 reviewer). They default to `is_dm=False` and produce deny outcomes via the channels/guilds/roles axes — which is unchanged behavior under L1's `if not is_dm:` branch. They pass unchanged. The 3 NEW `is_dm=True` analogues per Sub-step E.2 pin the new orthogonal-DM-admission semantic explicitly.
- **`agent_acl["admit_dms"]` is set but the account has no per-agent ACL entry at all**: standard `agent_acl is None` short-circuit; the new logic only fires inside `if agent_acl is not None:`.
- **Concurrent migration on first ensure_schema after upgrade**: aiosqlite's serialized connection prevents concurrent migrations within a single process; cross-process is single-user-local-tool out-of-scope.
- **Pre-migration validator-default behavior**: if a code path reads a v21 row through `model_validate` BEFORE the v22 migration completes (e.g. test fixtures, a hand-crafted JSON dict), the validator inserts the FRESH default `"allowlisted-peers-only"`. The MIGRATION-default for legacy data is different (`"all"` for empty-channels rows; `"none"` for non-empty-channels rows). For single-process aiosqlite, the migration runs to completion before the connection is usable, so this divergence isn't reachable in production. For tests and any future multi-connection refactor, the divergence is documented and the test author is responsible for setting `dm_admission` explicitly when constructing in-memory `ConnectorAccount` instances that need legacy-equivalent semantics.

## Files Affected

- `the_one/db/schema.py` — +~25 LOC migration block.
- `the_one/db/models.py` — +~15 LOC validator extension (allowed-keys + dm_admission branch).
- `the_one/agent/config.py` — +~25 LOC validator extension (allowed-keys + admit_dms branch + outer annotation widening).
- `the_one/connectors/_acl.py` — re-ordered admits_inbound function (~40 LOC delta net); docstring update.
- `tests/test_connectors_acl.py` — +~280 LOC new tests (9 dm_admission matrix + 3 per-agent admit_dms + 3 is_dm=True analogues to the existing tests at `:486, 592, 605`). NO existing tests modified.
- `tests/test_db_migration.py` — +~150 LOC TestSchemaV22 class + literal bump at `:243` (inside multi-line assert).
- `tests/test_db_repositories.py` — +~50 LOC.
- `tests/test_api_connector_account_config_validation.py` — +~30 LOC.
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — L1 entry.

Estimated total: ~600 LOC of meaningful change.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new tests pass; pre-existing tests (including `:486, 592, 605`) pass unchanged
- [ ] Full suite green (post-L1 expected: 2745±)
- [ ] Update flight-log.md with L1 progress entry (template above)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

8 citations verified against current code at leg design time:
- `the_one/db/models.py:305-341` (allowlist validator) — OK
- `the_one/agent/config.py:230` (outer annotation) — OK
- `the_one/agent/config.py:262-322` (validator) — OK
- `the_one/db/schema.py:12` (CURRENT_VERSION) — OK (=21)
- `the_one/db/schema.py:286-303` (v7 row-rewrite precedent) — OK
- `the_one/connectors/_acl.py:251-431` (admits_inbound; full function span) — OK
- `tests/test_connectors_acl.py:486, 592, 605` (3 existing deny tests; L1 leaves them UNTOUCHED and adds 3 new is_dm=True analogues adjacent) — verified by cycle-1 reviewer.
- `tests/test_db_migration.py:243` (`assert CURRENT_VERSION == 21` literal inside multi-line assert at lines 243-246; L1 bumps to 22 and updates the error-message string) — OK
