# Leg: agent-config-connector-acls-and-v18

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

> **Post-redesign note (M10 F6 L7 HAT, 2026-05-19)**: the per-agent
> `connector_acls` field type was widened from
> `dict[str, dict[str, list[str]]] | None` to
> `dict[str, dict[str, list[str] | None]] | None` so each axis is
> tri-state (`None` = inherit, `[]` = explicit empty / "DMs only" for
> channels, `[items]` = subset). The v18 migration itself (column +
> JSON encoding) is unchanged. See the **Deviations** entry in
> `../flight-log.md` for the full new model, surface impact, and
> rationale. The body of this artifact reflects the pre-redesign
> two-state contract for archaeology.

## Objective

Atomically land the per-agent ACL persistence surface: add `AgentConfig.connector_acls: dict[str, dict[str, list[str]]] | None = None` (account_id-keyed; inner shape `{"peers": list[str], "channels": list[str]}`); add the v18 migration that adds `agents.connector_acls TEXT` (nullable, JSON-encoded list at the value layer); round-trip through `SQLiteAgentStore.save` / `_row_to_config`; ripple the v18 renumber across all docstrings, schema comments, agents.md checklist, and migration tests that currently predict v18 = F8's CHECK constraint. Pydantic field validator enforces the nested shape (mirrors leg-1b's `_validate_config_reserved_keys` discipline). Per the flight's F4-L5-style commitment, the field + migration + repository round-trip ship in ONE leg — F4 debrief recommendation #1 ("a Pydantic field intended to persist ships its migration in the SAME leg") is the methodology trap closure.

## Context

- **Flight Design Decision — "AgentConfig column for per-agent ACL"** (flight.md): `AgentConfig.connector_acls: dict[str, dict[str, list[str]]] | None`. Account_id-keyed; absent key = "inherit account-scope (no agent-level restriction)"; present-but-empty `{"peers": [], "channels": []}` = "agent narrows to empty (no peer / no channel)". v18 schema migration; mirrors `connector_account_ids` F4 L5 path exactly.
- **Cycle-2 architect finding #2 (flight log)**: "Leg 1c's 'mirrors F4 L5 exactly' needs the v18 ripple-site enumeration. F4 L5 sub-leg A touched 6+ ancillary sites: `_connector_types.py` v17 docstrings, `schema.py` inline comments referencing future flight, `agents.md` connector-type checklist, `test_db_migration.py` `CURRENT_VERSION` assertion + `TestSchemaV18` class + downstream-renumber docstrings. Leg 1c design must run `grep -n 'v18\|v17' the_one/ tests/` and enumerate ripple sites." Done at design time — full enumeration in **Ripple Sites** below.
- **F1-era predictive docstrings to renumber**: every site that currently says "v18 = Flight 8's CHECK migration" or "F8 CHECK constraint renumbers to v18" must shift to "v18 = F6 L1c's `agents.connector_acls`; v19 = Flight 8's CHECK." This is the F1 prediction-meets-reality moment.
- **Pydantic shape decision**: stick with the nested-dict annotation `dict[str, dict[str, list[str]]] | None` (mirrors `mcp_overrides` at `agent/config.py:153` shape — heavier than `connector_account_ids: list[str]` but matches an existing precedent in the SAME file). A `PerAgentACL(BaseModel)` submodel was considered (cycle-2 finding #5) and rejected: introducing a new Pydantic type forces legs 2/3/5 to import it; the leg's validator pattern (a `@field_validator("connector_acls", mode="after")` enforcing nested shape) provides equivalent invariants without the type-system widening. Documented in the validator docstring.
- **Empty-ACL inheritance semantics** (flight Design Decision): `connector_acls is None` (default for pre-v18 rows and for un-set agents) → agent inherits account-scope verbatim, no restriction. `connector_acls = {}` → empty dict, but a per-account_id entry being ABSENT also means "inherit account-scope" — so `{}` is semantically identical to `None`. A per-account entry with `{"peers": [], "channels": []}` → empty-list lockdown (agent narrows to nothing). A per-account entry with `{"peers": ["u1"], "channels": []}` → agent reaches peer u1 only (channels are unrestricted because the empty list at this slot means "no narrowing IN ADDITION to account-scope" per the leg-3 outbound resolver's intersection semantics — leg 3 documents the read-side rules). Leg 1c ships the PERSISTENCE; leg-3 ships the read-side semantics. The validator-side rule: when an account_id key IS present, both inner keys (`"peers"` and `"channels"`) MUST be present (no partial inner shape).
- **Why account_id-keyed at the outer level**: matches `mcp_overrides` (source name-keyed) and `tool_overrides` (tool name-keyed) — the precedent for "per-external-resource override on `AgentConfig`." Reverse lookup ("which agents have ACLs for account X?") becomes a SQL query rather than a JSON scan in every account row (per the flight Design Decision rationale).
- **F4 L5 pattern as the canonical atomic-leg shape** (NOT "fix for an earlier gap"): cycle-2 finding #4 corrected the framing — F4 L5 was the FIX for a leg-1 gap, NOT the canonical pattern. The CORRECT framing is "Adopts the F4 L5 sub-leg A pattern atomically — Pydantic field + ALTER TABLE + repository round-trip ship in one leg, as F4 debrief rec #1 prescribes." The leg ships the field, the migration, the repository serializer, the repository deserializer, the migration tests, the round-trip tests, the v18 ripple-site updates, AND the F8 v19-renumber updates — all atomically.
- **Backward-compatibility surface**: pre-v18 agent rows have NULL `connector_acls`. `_row_to_config` decodes NULL → `None` (NOT `{}`). The validator allows `None` (the default). Legs 2 and 3 read `config.connector_acls` and treat both `None` and `{}` as "no per-agent narrowing"; a present account_id entry triggers intersection logic.
- **Pydantic v2 validator runs on direct construction** (verified by leg 1b's `test_validator_fires_on_repo_read_path`): the field validator on `connector_acls` fires on `_row_to_config`'s `AgentConfig(**kwargs)` construction the same way leg-1b's `_validate_config_reserved_keys` fires on `_row_to_model`'s direct construction. No need to switch `_row_to_config` to `model_validate`.

## Ripple Sites (v18 = F6 L1c; F8 CHECK now lands at v19)

Design-time grep `grep -n "v1[3-9]\|flight 8\|Flight 8"` against current code produced the canonical enumeration below. Every F8-CHECK-prediction site (including stale ones predating this leg) is updated to v19 atomically — the leg principle is "after this leg, every site that names F8 CHECK says v19; no site says v18 = F8 CHECK." Stale-pre-leg sites (e.g. `schema.py:488` still saying "v14") were already wrong; the leg fixes them as part of the same surface so the codebase is internally consistent on F8 CHECK = v19.

Code:
- `the_one/db/_connector_types.py:7-18` — module docstring lists v14–v17 then says "v18 is Flight 8's CHECK". Rewrite to: v14 → F1 L2 name; v15 → F2 L2 idle_timeout_seconds; v16 → F3 L1 chat_sessions external-key + session_continuation_seconds; v17 → F4 L5 agents.connector_account_ids; **v18 → F6 L1c agents.connector_acls**; v19 → Flight 8 CHECK table-rename.
- `the_one/db/schema.py:11` — `CURRENT_VERSION = 17` → `CURRENT_VERSION = 18`
- `the_one/db/schema.py:485-491` — currently says "flight 8 (Discord) will land **v14** with the table-rename ceremony" — stale-pre-leg prediction that never tracked the renumbers. Update to "flight 8 (Discord) will land **v19** with the table-rename ceremony" (v14 was claimed by F1 L2, v15 by F2 L2, v16 by F3 L1, v17 by F4 L5, v18 by F6 L1c).
- `the_one/db/schema.py:546-548` — v15 block downstream comment "flight 08 (Discord) previously planned a v15 CHECK migration; that renumbers to v18" → "renumbers to v19 (v18 is claimed by F6 L1c — `agents.connector_acls`)"
- `the_one/db/schema.py:586-588` — v16 block: "flight 08 (Discord) previously planned a v16 CHECK migration; that renumbers to v18" → same renumber to v19 + v18 = F6 L1c
- `the_one/db/schema.py:636-640` — v17 block: "flight 08 (Discord) previously planned a v17 CHECK migration; that renumbers to **v18**" → "renumbers to **v19** (v18 is claimed by F6 L1c — `agents.connector_acls`)". Preserve the `**v19**` markdown emphasis (mirror the existing `**v18**` style).
- `the_one/db/schema.py` — add the v18 migration block immediately after the v17 block (after line ~655). The block:
  ```python
  if version < 18:
      # Mission 10 Flight 6 Leg 1c: AgentConfig.connector_acls persistence.
      # F6 L1c lands the per-agent ACL atomically — Pydantic field +
      # ALTER TABLE + repository round-trip in one leg, per F4 debrief
      # rec #1 ("a Pydantic field intended to persist ships its migration
      # in the SAME leg"). Adds a nullable TEXT column storing the JSON-
      # encoded outer dict {account_id: {"peers": [...], "channels": [...]}}
      # or NULL when no per-agent narrowing exists (back-compat for pre-v18
      # rows; matches connector_account_ids pre-v17 default decode).
      #
      # Downstream: flight 08 (Discord) previously planned v18 for its
      # CHECK constraint; that renumbers to v19. See _connector_types.py
      # docstring + tests/test_db_migration.py TestSchemaV{14,15,16,17}
      # downstream-renumber docstrings + agents.md connector-type
      # checklist item 4.
      #
      # Idempotency follows the v8/v9/v10/v11/v14/v15/v17 ALTER ADD COLUMN
      # pattern (PRAGMA guard + INSERT OR IGNORE on schema_version LAST).
      async with conn.execute("PRAGMA table_info(agents)") as cursor:
          existing_cols = {row[1] for row in await cursor.fetchall()}
      if "connector_acls" not in existing_cols:
          await conn.execute(
              "ALTER TABLE agents ADD COLUMN connector_acls TEXT"
          )

      await conn.execute(
          "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (18,)
      )
      await conn.commit()
      version = 18
  ```
- `the_one/agent/config.py:135` — add `connector_acls: dict[str, dict[str, list[str]]] | None = None` field with full docstring (after `connector_account_ids` line 135, placed alongside the `mcp_overrides` precedent at line 153 — i.e. with the other override dicts). Add a `@field_validator("connector_acls", mode="after")` classmethod `_validate_connector_acls` enforcing the nested shape.
- `the_one/db/repositories.py:96-136` — `SQLiteAgentStore.save` INSERT statement: add `connector_acls` column to the column list (between `connector_account_ids` and `created_at`); add the placeholder in VALUES; add to the ON CONFLICT update clause; pass `json.dumps(config.connector_acls) if config.connector_acls is not None else None` in the parameter tuple
- `the_one/db/repositories.py:190-216` — `_row_to_config`: add `connector_acls=(json.loads(row["connector_acls"]) if row["connector_acls"] else None)` to the kwargs dict
- `the_one/agents.md:302` — Connector type extension checklist item 4: extend the v-renumber list. "v17 by leg 05 of Flight 4 — `agents.connector_account_ids` persistence" → "v17 by leg 05 of Flight 4 — `agents.connector_account_ids` persistence; **v18 by leg 1c of Flight 6 — `agents.connector_acls` persistence**". "Flight 8's **v18** migration adds the CHECK" → "Flight 8's **v19** migration adds the CHECK"
- `the_one/connectors/README.md:297` — currently "The v13/v14 schema has no CHECK constraint". Reframe: "The v13–v18 schema has no CHECK constraint on `connector_accounts.type`" (or rewrite as time-independent: "Schema versions before v19 have no CHECK constraint").
- `the_one/connectors/README.md:303` — currently "Flight 8's **v15** migration adds the CHECK constraint" — stale-pre-leg prediction (was wrong before this leg too). Update to "Flight 8's **v19** migration adds the CHECK constraint". Preserve markdown emphasis.

Tests:
- `tests/test_db_migration.py:234-238` — `CURRENT_VERSION == 17` assertion: update integer to `18` and update the assertion message to name the F6 L1c migration. The surrounding comment block (L223-233) gets a new line `v18 added agents.connector_acls (M10 F06 L1c — per-agent ACL persistence; F4 debrief rec #1 atomic shape)`.
- `tests/test_db_migration.py:1171,1179` — "v18 in flight 8" / "deferred to v18 (flight 08)" — renumber to v19.
- `tests/test_db_migration.py:1262` — TestSchemaV14 docstring `that renumbers to v18` → `that renumbers to v19 (v18 is claimed by F6 L1c's agents.connector_acls)`. The "v15 is claimed by flight 02..., v16 is claimed by flight 03..., v17 is claimed by flight 04..." enumeration extends with `, v18 is claimed by flight 06 leg 1c`.
- `tests/test_db_migration.py:1448-1449` — TestSchemaV15 docstring: F8 CHECK "renumbered to v18" → "renumbered to v19"; same `v18 = F6 L1c` extension.
- `tests/test_db_migration.py:1638-1639` — TestSchemaV16 docstring: same pattern.
- `tests/test_db_migration.py:1867-1879` — TestSchemaV17 docstring: same pattern.
- `tests/test_db_migration.py` after `TestSchemaV17` (after L2026) — add a new `TestSchemaV18` class mirroring `TestSchemaV17`'s structure:
  - `test_v18_fresh_db_includes_agents_connector_acls_column` — fresh DB, ensure_schema, verify `agents.connector_acls` exists, TEXT, nullable, no DEFAULT; schema_version contains 18 and max==CURRENT_VERSION
  - `test_v18_migration_idempotent_on_rerun` — ensure_schema twice → no duplicate schema_version row for 18; column still present
  - `test_v18_legacy_v17_row_decodes_with_none_connector_acls` — hand-build a v17-shape agents table (with `connector_account_ids` but no `connector_acls`); INSERT a row; ensure_schema; column added as NULL; pre-existing row's `connector_acls` is NULL; `_row_to_config` decodes NULL → `None`
- `tests/test_db_repositories.py` — extend the existing `TestSQLiteAgentStore` class (around L207 "test_save_round_trips_connector_account_ids") with:
  - `test_save_round_trips_connector_acls` — save an agent with `connector_acls={"acct-a": {"peers": ["u1"], "channels": []}}`; reload; verify round-trip
  - `test_save_round_trips_connector_acls_none` — save with `connector_acls=None`; reload; verify None preserved
  - `test_save_round_trips_empty_outer_dict_connector_acls` — save with `connector_acls={}`; reload; verify `{}` (NOT collapsed to `None`). Distinguishes the JSON-literal `"{}"` truthy-string path from the SQL-NULL falsy path in `_row_to_config`'s `if row["X"] else None` decode.
  - `test_load_pre_v18_agent_has_none_connector_acls` — hand-write a row with `connector_acls = NULL`; load; verify `None`
  - `test_empty_per_account_acl_is_preserved_verbatim` — save with `connector_acls={"acct-a": {"peers": [], "channels": []}}`; reload; verify the empty-lists lockdown survives
  - `test_validator_fires_on_repo_read_path_connector_acls` — H2-closure analog to leg 1b's equivalent test. Create a valid row via the repo, then UPDATE the `connector_acls` column with malformed JSON via raw SQL (`{"acct-a": {"peers": ["u1"]}}` — missing channels); call `load()`; expect `ValidationError`. Confirms Pydantic v2 fires the validator on `_row_to_config`'s direct-kwargs construction.
- `tests/test_agent_config.py` (or wherever AgentConfig model tests live — verify existence; if absent, append to `tests/test_db_repositories.py::TestSQLiteAgentStore` near the existing connector_account_ids tests) — direct construction tests for the new validator:
  - `connector_acls = None` (default) accepted
  - `connector_acls = {}` accepted
  - `connector_acls = {"acct-a": {"peers": [], "channels": []}}` accepted
  - `connector_acls = {"acct-a": {"peers": ["u1", "u2"], "channels": ["c1"]}}` accepted
  - `connector_acls = {"acct-a": {"peers": ["u1"]}}` raises ValidationError (missing `channels`)
  - `connector_acls = {"acct-a": {"channels": []}}` raises (missing `peers`)
  - `connector_acls = {"acct-a": {"peers": [], "channels": [], "extra": []}}` raises (extra key)
  - `connector_acls = {"acct-a": {"peers": "not-a-list", "channels": []}}` raises
  - `connector_acls = {"acct-a": {"peers": [123], "channels": []}}` raises (non-string entry)
  - `connector_acls = {"acct-a": "not-a-dict"}` raises (per-account value not a dict — `dict_type` error from Pydantic's annotation)
  - `connector_acls = {1: {"peers": [], "channels": []}}` raises (non-string outer key — `string_type` error from Pydantic's annotation; empirically verified at design time, NO coercion in Pydantic v2)

## Inputs

- `the_one/agent/config.py:111-156` — `AgentConfig` model with `connector_account_ids`, `tool_overrides`, `mcp_overrides` shape
- `the_one/db/schema.py:11,628-655` — `CURRENT_VERSION = 17` + v17 migration block (F4 L5 precedent; leg 1c mirrors this shape for v18)
- `the_one/db/schema.py:490,547,587,637` — v18 prediction sites (currently pointing to F8 CHECK)
- `the_one/db/_connector_types.py:7-18` — F8 CHECK prediction docstring; receives v19-renumber update
- `the_one/db/repositories.py:69-216` — `SQLiteAgentStore` (`save`, `_row_to_config`) — modified for the new column round-trip
- `tests/test_db_migration.py:234-238` — CURRENT_VERSION assertion + surrounding migration history comments
- `tests/test_db_migration.py:1867-2026` — `TestSchemaV17` class (template for the new `TestSchemaV18`)
- `tests/test_db_repositories.py:207+` — `TestSQLiteAgentStore` connector_account_ids round-trip tests (template for the new `connector_acls` round-trip tests)
- Leg 1b (status: `landed`) — the `ConnectorAccount.config["pairing"]` + `config["allowlist"]` persistence on the ACCOUNT side; leg 1c is the AGENT side. The two are orthogonal at the persistence layer; legs 2 and 3 join them.
- Leg 1a (status: `landed`) — the resolver outcome ADT; not directly consumed by leg 1c (legs 2 and 3 are the join points).
- F4 L5 precedent: the existing v17 migration block, the `SQLiteAgentStore.save` shape, `_row_to_config` shape, and `TestSchemaV17` class. Leg 1c is structurally a clone of all four, adapted for `connector_acls` instead of `connector_account_ids`.

## Outputs

- `the_one/agent/config.py` — `AgentConfig` gains `connector_acls: dict[str, dict[str, list[str]]] | None = None` field with comprehensive docstring + `@field_validator("connector_acls", mode="after")` classmethod `_validate_connector_acls` enforcing the nested shape
- `the_one/db/schema.py` — `CURRENT_VERSION = 18`; new v18 migration block added after the v17 block; 4 existing docstring comments updated (L490, L547, L587, L637) to renumber F8 CHECK to v19 and name v18 as F6 L1c
- `the_one/db/_connector_types.py` — module docstring updated to reflect v18 = F6 L1c; v19 = F8 CHECK
- `the_one/db/repositories.py` — `SQLiteAgentStore.save` INSERT extended with the new column; `_row_to_config` extended with the new kwarg
- `the_one/agents.md:302` — connector-type extension checklist item 4 updated (v18 = F6 L1c; v19 = F8 CHECK)
- `tests/test_db_migration.py` — `CURRENT_VERSION` assertion bumped to 18; 4 downstream-renumber docstring blocks updated (TestSchemaV14/V15/V16/V17 + L1171,L1179); new `TestSchemaV18` class appended after `TestSchemaV17`
- `tests/test_db_repositories.py` — 4 new test methods on `TestSQLiteAgentStore`: round-trip with ACL set; round-trip with `None`; pre-v18 NULL → `None` decode; empty-per-account-ACL preservation
- `tests/test_agent_config.py` (NEW or append to `test_db_repositories.py::TestSQLiteAgentStore`) — 10+ direct-construction validator tests (per the Ripple Sites list above)
- The flight log gains a leg-1c entry under "## Leg Progress"

## Acceptance Criteria

- [ ] `AgentConfig.connector_acls: dict[str, dict[str, list[str]]] | None = None` field exists in `the_one/agent/config.py`, placed alongside `mcp_overrides` (around line 153) so the override dicts cluster together
- [ ] `_validate_connector_acls` validator enforces:
  - `None` is valid (default; no per-agent narrowing)
  - `{}` is valid (empty outer dict; semantically same as `None` per the leg-3 read rule)
  - Each outer key is a string (Pydantic's `dict[str, ...]` enforces this)
  - Each outer value must be a dict with EXACTLY keys `{"peers", "channels"}`
  - Each inner value must be a list of strings (no non-string entries)
  - Empty inner lists are PERMITTED and PRESERVED VERBATIM
  - All violations raise `ValueError` with operator-facing messages
- [ ] `the_one/db/schema.py` `CURRENT_VERSION = 18`; v18 migration block follows the v17 ALTER ADD COLUMN idempotency shape
- [ ] `the_one/db/_connector_types.py` docstring lists v18 = F6 L1c; v19 = F8 CHECK
- [ ] All four `the_one/db/schema.py` v18 prediction sites (L490, L547, L587, L637 — design-time citations; verify post-edit lines) reflect the new framing
- [ ] `SQLiteAgentStore.save` INSERT + ON CONFLICT clauses include `connector_acls`; parameter tuple passes `json.dumps(config.connector_acls) if config.connector_acls is not None else None`
- [ ] `_row_to_config` deserializes the column: `connector_acls=(json.loads(row["connector_acls"]) if row["connector_acls"] else None)` — `or` truthiness mirrors `tool_overrides` / `mcp_overrides` precedent at L207-208
- [ ] `tests/test_db_migration.py` `CURRENT_VERSION` assertion bumped to 18; the surrounding migration-history comment includes a line for v18 = F6 L1c
- [ ] `TestSchemaV18` class added with 3 tests: fresh-DB column presence; idempotent rerun; legacy-v17-row NULL → `None` decode
- [ ] 4 downstream-renumber sites in `test_db_migration.py` (TestSchemaV{14,15,16,17} docstrings + L1171,L1179) updated to renumber F8 CHECK to v19
- [ ] `field_validator` import added to `the_one/agent/config.py` (currently only `BaseModel, Field` are imported from pydantic; verified at design time)
- [ ] `tests/test_db_repositories.py::TestSQLiteAgentStore` gains 6 round-trip tests for `connector_acls` (ACL set; None preserved; empty outer dict preserved; pre-v18 NULL → None; empty per-account ACL preserved; H2-closure read-path validator fires); existing `connector_account_ids` tests pass byte-identically
- [ ] 10+ direct-construction validator tests in `tests/test_agent_config.py` (or appended to `TestSQLiteAgentStore`)
- [ ] `agents.md:302` Connector type extension checklist updated
- [ ] F1/F2/F3/F4/F5 + leg-1a + leg-1b regression suites pass byte-identically (no consumer touches `connector_acls` yet)
- [ ] `ruff check` clean on modified files; full test suite `docker exec the-one pytest -x --timeout 30` passes

## Verification Steps

- `python -c "from the_one.db.schema import CURRENT_VERSION; assert CURRENT_VERSION == 18; print('ok')"` (inside the container)
- `python -c "from the_one.agent.config import AgentConfig; a = AgentConfig(name='n'); assert a.connector_acls is None; print(a.connector_acls)"`
- `python -c "from the_one.agent.config import AgentConfig; a = AgentConfig(name='n', connector_acls={'acct-a': {'peers': ['u1'], 'channels': []}}); print(a.connector_acls)"`
- `python -c "from the_one.agent.config import AgentConfig; AgentConfig(name='n', connector_acls={'acct-a': {'peers': ['u1']}})"` — should raise (missing channels)
- `python -c "from the_one.agent.config import AgentConfig; AgentConfig(name='n', connector_acls={'acct-a': {'peers': [], 'channels': [], 'extra': []}})"` — should raise (extra key)
- `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py::TestSchemaV18`
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestSQLiteAgentStore`
- `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py` — all migration tests pass including the updated CURRENT_VERSION assertion and the renumbered downstream docstrings
- `docker exec the-one pytest -x --timeout 30` — full suite passes
- `grep -rn "v1[3-9]\|flight 8\|Flight 8" the_one/db/_connector_types.py the_one/db/schema.py the_one/agents.md the_one/connectors/README.md tests/test_db_migration.py` — every site that names v18 means F6 L1c `agents.connector_acls`; every site that names v19 means F8 CHECK; NO site says "v18 = F8 CHECK" or names an earlier obsolete F8 CHECK version (v14, v15, v16, v17, v18 — all stale-pre-leg predictions now canonically v19). Broader range than `v1[5-9]` so a stale v13/v14 prediction at `test_db_migration.py:1131` would surface.

## Implementation Guidance

1. **Add the Pydantic field + validator to `the_one/agent/config.py`**. REQUIRED IMPORT EDIT: the top of `the_one/agent/config.py` currently imports only `BaseModel, Field` from pydantic (verified at design time — no validators exist in the file). Add `field_validator` to the import: `from pydantic import BaseModel, Field, field_validator`. Then add the field + validator (placement: alongside `mcp_overrides` at line 153 — the override dicts cluster). Use this shape:

   ```python
   # M10 F6 L1c: per-agent ACL overrides keyed by account_id.
   # Shape: {account_id: {"peers": list[str], "channels": list[str]}}.
   # ``None`` (the default) means "no per-agent narrowing — inherit
   # account-scope verbatim." ``{}`` (empty outer dict) is semantically
   # identical to ``None`` (no per-account entries means no narrowing).
   # A per-account entry being ABSENT from a non-empty outer dict ALSO
   # means "inherit account-scope" for that specific account — legs 2/3
   # apply intersection semantics only when an entry IS present. Empty
   # inner lists (``{"peers": [], "channels": []}``) are valid and mean
   # "agent narrows to no peer / no channel for THIS account."
   #
   # Inner type ``dict[str, list[str]]`` (NOT bare ``dict``) so Pydantic
   # v2 actually validates each inner value — mirrors the same rationale
   # as ``tool_overrides`` and ``mcp_overrides`` above. The validator
   # below enforces the inner shape further (exact keys, list-of-string
   # entries).
   connector_acls: dict[str, dict[str, list[str]]] | None = None

   @field_validator("connector_acls", mode="after")
   @classmethod
   def _validate_connector_acls(
       cls, value: dict[str, dict[str, list[str]]] | None
   ) -> dict[str, dict[str, list[str]]] | None:
       """Enforce exact-keys shape on per-account ACL inner dicts.

       Pydantic v2's ``dict[str, dict[str, list[str]]]`` annotation
       already enforces:
         - non-string outer keys → rejected (``string_type`` error)
         - non-dict outer values → rejected (``dict_type`` error)
         - inner values that aren't lists of strings → rejected
       This validator's job is the ONE invariant Pydantic cannot express
       from the annotation alone: each inner dict MUST have EXACTLY the
       keys ``{"peers", "channels"}`` — no extra keys, no missing keys.
       Empty inner lists are PERMITTED and PRESERVED VERBATIM (agent
       narrows to no peer / no channel for this account).

       ``None`` and ``{}`` are both valid (semantically: no per-agent
       narrowing).

       Mirrors leg-1b's ``_validate_config_reserved_keys`` pattern at
       ``the_one/db/models.py:ConnectorAccount`` — Pydantic v2
       ``@field_validator(mode="after")`` runs on both
       ``model_validate`` and direct ``BaseModel(**kwargs)`` so the
       repository read path at ``_row_to_config`` is validated without
       a separate ``model_validate`` wrapper.
       """
       if value is None:
           return value
       for account_id, acl in value.items():
           # Pydantic already enforced ``acl`` is a dict with str keys.
           # The only invariant left is the exact-keys check.
           keys = set(acl.keys())
           extra = keys - {"peers", "channels"}
           if extra:
               raise ValueError(
                   f"connector_acls[{account_id!r}] has unexpected keys: "
                   f"{sorted(extra)}"
               )
           missing = {"peers", "channels"} - keys
           if missing:
               raise ValueError(
                   f"connector_acls[{account_id!r}] is missing required "
                   f"keys: {sorted(missing)}"
               )
       return value
   ```

   Rationale for the trimmed validator: empirical verification (Python + Pydantic v2) showed that `dict[str, dict[str, list[str]]] | None` rejects non-string outer keys (`string_type` error), non-dict outer values (`dict_type` error), non-list inner values (`list_type` error), and non-string inner entries (`string_type` error) ALL via Pydantic's native type system before the validator runs. The earlier defense-in-depth shape (with `isinstance` checks for each layer) was dead code. The trimmed validator handles only the one invariant the annotation cannot express: exact-keys `{"peers", "channels"}`.

2. **Bump `CURRENT_VERSION` and add the v18 migration block in `the_one/db/schema.py`**. The block goes immediately after the v17 block (after line ~655). Use the template in Ripple Sites above.

3. **Update the 4 prediction-comment sites in `the_one/db/schema.py`** at the locations enumerated in Ripple Sites: L485-491 (stale-pre-leg "flight 8 will land v14" → v19), L546-548, L586-588, L636-640. The text needs surgical edits — DO NOT rewrite the surrounding migration logic.

4. **Update `the_one/db/_connector_types.py` module docstring**. Lines 7-18. Use the shape:

   ```python
   - The SQLite CHECK constraint string baked into the ``connector_accounts``
     table (runtime DB-level rejection of bogus rows) — **deferred to flight 8**
     which adds the CHECK via a v19 table-rename ceremony when there is a real
     type to constrain (v14 → ``name`` column on ``connector_accounts`` (F1 L2);
     v15 → ``idle_timeout_seconds`` (F2 L2); v16 → chat_sessions external-key
     columns + ``session_continuation_seconds`` on ``connector_accounts`` (F3 L1);
     v17 → ``agents.connector_account_ids`` persistence (F4 L5);
     v18 → ``agents.connector_acls`` persistence (F6 L1c);
     v19 is Flight 8's CHECK constraint via the table-rename ceremony established
     by v6/v12).
     Until then ``connector_accounts.type`` is unconstrained at the DB level;
     the Pydantic ``Literal`` is the sole guard at the API edge.
   ```

5. **Update `the_one/db/repositories.py:SQLiteAgentStore`**. Three sites:
   - INSERT column list (around L98-103): add `connector_acls` between `connector_account_ids` and `created_at`
   - VALUES placeholders (L103): add one `?`
   - ON CONFLICT clause (around L116): add `connector_acls=excluded.connector_acls,`
   - Parameter tuple (around L132): add `json.dumps(config.connector_acls) if config.connector_acls is not None else None,` between the connector_account_ids JSON dump and `now`
   - `_row_to_config` (around L214): add `connector_acls=(json.loads(row["connector_acls"]) if row["connector_acls"] else None),` after the `connector_account_ids` line

6. **Update `the_one/agents.md:302`** (Connector type extension checklist item 4) — the v-version enumeration:
   - Add: "; v18 by leg 1c of Flight 6 — `agents.connector_acls` persistence (closes the F6 per-agent ACL substrate atomically per F4 debrief rec #1)"
   - Change: "Flight 8's **v18** migration adds the CHECK" → "Flight 8's **v19** migration adds the CHECK"

7. **Update `tests/test_db_migration.py`** — line numbers are approximate (±3); use grep to locate each site:
   - L234-238: bump assertion to `CURRENT_VERSION == 18`; update message to name F6 L1c
   - L223-233 (surrounding migration-history comment): append `; v18 added agents.connector_acls (M10 F06 L1c — per-agent ACL persistence; F4 debrief rec #1 atomic shape).`
   - L1131 (TestSchemaV13 docstring): "deferred to v14 in flight 8" — stale-pre-leg prediction; rewrite to "deferred to v19 in flight 8"
   - L1171, L1179: renumber "v18 in flight 8" → "v19 in flight 8"; "deferred to v18 (flight 08)" → "deferred to v19 (flight 08)"
   - L1261-1267 (TestSchemaV14 docstring): the 4-line renumber chain. Rather than surgical edit the multi-rebase chain, REWRITE to one current statement: "Downstream: flight 08 (Discord)'s CHECK constraint now lands at v19 (v14 claimed by this F1 L2 leg — `name` column; v15 by F2 L2 — `idle_timeout_seconds`; v16 by F3 L1 — chat_sessions external-key + `session_continuation_seconds`; v17 by F4 L5 — `agents.connector_account_ids`; v18 by F6 L1c — `agents.connector_acls`)."
   - L1445-1449 (TestSchemaV15 docstring): the same 4-line renumber chain. Same single-current-statement rewrite shape, adapted to identify v15 as F2 L2's claim: "Downstream: flight 08 (Discord)'s CHECK constraint now lands at v19 (v15 claimed by this F2 L2 leg — `idle_timeout_seconds`; v16 by F3 L1; v17 by F4 L5; v18 by F6 L1c — `agents.connector_acls`)."
   - L1638-1639 (TestSchemaV16 docstring): "renumbers to v18 (v17 is claimed by F4 L5)" → "renumbers to v19 (v17 is claimed by F4 L5; v18 by F6 L1c — `agents.connector_acls`)"
   - L1877 (TestSchemaV17 docstring): "Downstream: flight 08 (Discord) previously planned a v17 CHECK migration; that renumbers to v18." → "renumbers to v19 (v18 is claimed by F6 L1c — `agents.connector_acls`)."
   - Append `TestSchemaV18` class after `TestSchemaV17` (after L2026) — mirror `TestSchemaV17` shape with the three required tests (see Ripple Sites for the test list)

8. **Update `tests/test_db_repositories.py::TestSQLiteAgentStore`** — append 4 round-trip tests after the existing `test_load_pre_v17_agent_has_empty_connector_account_ids` test (around L238+). Use the shape:

   ```python
   async def test_save_round_trips_connector_acls(
       self, agent_store: SQLiteAgentStore
   ) -> None:
       """Saving an agent with ``connector_acls`` set roundtrips through
       ``save`` and ``load``. Mirror of
       ``test_save_round_trips_connector_account_ids`` at L207+ for the
       F6 L1c per-agent ACL field.
       """
       config = AgentConfig(
           name="agent",
           connector_acls={
               "acct-a": {"peers": ["u1", "u2"], "channels": ["c1"]},
               "acct-b": {"peers": [], "channels": []},
           },
       )
       await agent_store.save(config)
       loaded = await agent_store.load("agent")
       assert loaded.connector_acls == {
           "acct-a": {"peers": ["u1", "u2"], "channels": ["c1"]},
           "acct-b": {"peers": [], "channels": []},
       }

   async def test_save_round_trips_connector_acls_none(
       self, agent_store: SQLiteAgentStore
   ) -> None:
       config = AgentConfig(name="agent", connector_acls=None)
       await agent_store.save(config)
       loaded = await agent_store.load("agent")
       assert loaded.connector_acls is None

   async def test_load_pre_v18_agent_has_none_connector_acls(
       self, agent_store: SQLiteAgentStore
   ) -> None:
       """Hand-write an agent row with ``connector_acls = NULL`` —
       ``_row_to_config`` MUST decode NULL → ``None``. Mirror of
       ``test_load_pre_v17_agent_has_empty_connector_account_ids``.
       """
       # Use the agent_store's connection. SQL columns must mirror the
       # v18-shape (with connector_acls present, NULL on this row).
       # Recipe: INSERT with connector_acls explicitly NULL.
       # (See the existing v17 test for the column-list pattern.)
       # ... full implementation: INSERT row with connector_acls=NULL
       # ...                       SELECT to confirm NULL
       # ...                       load → assert connector_acls is None

   async def test_empty_per_account_acl_round_trips_through_save_load(
       self, agent_store: SQLiteAgentStore
   ) -> None:
       """Empty per-account ACL ``{"peers": [], "channels": []}`` survives
       the DB round-trip verbatim (does NOT collapse to an absent entry).
       Mirror of leg-1b's ``test_empty_allowlist_round_trips_through_repo``.
       """
       config = AgentConfig(
           name="agent",
           connector_acls={"acct-a": {"peers": [], "channels": []}},
       )
       await agent_store.save(config)
       loaded = await agent_store.load("agent")
       assert loaded.connector_acls == {"acct-a": {"peers": [], "channels": []}}
       # Confirm the per-account entry survives (not just the outer dict).
       assert "acct-a" in loaded.connector_acls
   ```

   The `agent_store` fixture is already present in `tests/test_db_repositories.py` — verify the existing tests use it (yes — `test_save_round_trips_connector_account_ids` does).

9. **Write the validator-only direct-construction tests**. Append a `TestAgentConfigConnectorAclsValidator` class to `tests/test_db_repositories.py` (sibling to `TestSQLiteAgentStore`) OR create a new `tests/test_agent_config.py` file (verify absence — if absent, choose the new-file path for clearer organization). Recommended: append to existing file to match leg-1b's pattern.

10. **Run the full verification budget** in this order:
    1. `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py::TestSchemaV18` — new tests pass
    2. `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py` — all migration tests pass (including the updated CURRENT_VERSION assertion + renumbered downstream docstrings)
    3. `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestSQLiteAgentStore` — new and existing tests pass
    4. `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py` — full file
    5. `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_pool.py tests/test_connectors_session.py tests/test_connectors_resolver.py` — F1/F3/F4/F5 + leg 1a regression
    6. `docker exec the-one pytest -x --timeout 30` — full suite passes
    7. `docker exec the-one ruff check the_one/agent/config.py the_one/db/schema.py the_one/db/repositories.py the_one/db/_connector_types.py tests/test_db_migration.py tests/test_db_repositories.py` — clean

11. **Update the flight log** with the leg-1c entry capturing: field shape, v18 migration shape, validator behavior, ripple-site enumeration (4 schema.py sites + 1 _connector_types.py site + 1 agents.md site + 5 test_db_migration.py docstring sites + new TestSchemaV18 class + new TestSQLiteAgentStore tests), F4 L5 atomic-leg pattern adoption (NOT "fix"), the cycle-2 finding-#5 PerAgentACL submodel rejection (rationale: validator pattern suffices; leg-2/leg-3 don't need a new import).

12. **Set leg status to `landed`**. Do NOT commit.

## Edge Cases

- **`connector_acls = {}` vs `None`**: semantically identical (no narrowing); both pass the validator. The JSON serialization differs: `{}` round-trips as the literal string `"{}"`; `None` round-trips as SQL NULL. The `_row_to_config` decode `(json.loads(row["X"]) if row["X"] else None)` correctly distinguishes them: the literal string `"{}"` is truthy in Python, so `json.loads` runs and returns `{}`; SQL NULL deserializes as `None` per `aiosqlite`'s row-mapping, which is falsy and triggers the `else None` branch. Verified at design time. The round-trip `{}` → `{}` invariant has an explicit test (`test_save_round_trips_empty_outer_dict_connector_acls`).
- **Non-string outer key**: empirically verified — Pydantic v2 REJECTS integer outer keys with `string_type` error. NO coercion. The validator does not need to enforce this; the test asserts the rejection deterministically.
- **`tool_overrides` / `mcp_overrides` precedent for the OR-truthiness deserialize**: `_row_to_config` uses `(json.loads(row["X"]) if row["X"] else None)` — same shape applies to `connector_acls`. NULL and the empty-string edge case both deserialize to `None`. The leg's framing matches this.
- **`mode="after"` runs on `model_dump | data | model_validate` path**: the API edge currently doesn't update `AgentConfig` through a round-trip PUT (no operator-facing endpoint widens this surface in legs 1c — leg 5's Studio Agent Editor Connectors tab does). The validator suffices for leg 1c's scope. Leg 5 will exercise the API path; the validator will fire there too.
- **Concurrent edits**: same shape as `connector_account_ids` — last-writer-wins on the entire `agents` row. Not changed by leg 1c.
- **F8 v19 renumber awareness for future readers**: every docstring touched by this leg explicitly names "F6 L1c claims v18; F8 CHECK renumbers to v19." A future reader who searches "v18 = Flight 8 CHECK" will hit the OLD prediction and follow the corrected docstrings to the current state. The renumber footprint is captured in the leg log so a debrief reviewer can audit it.
- **Pre-v18 agent rows in dev/test DBs**: existing operator dev DBs have agent rows with no `connector_acls` column. The v18 ALTER adds it as NULL; the next save through `SQLiteAgentStore.save` populates it (with `None`-serialized-to-NULL by default). No data loss; no surprise behavior change.
- **Multiple `connector_acls` for the same account_id key** (e.g. via JSON-merge attack): JSON doesn't allow duplicate keys (the last value wins on parse); Pydantic doesn't see the duplicate. Not a concern.
- **Leg 1c does NOT integrate with leg 1a's outcome ADT**: confirmed orthogonal at this layer. Legs 2 (inbound) and 3 (outbound) read `config.connector_acls` and `account.config["allowlist"]`, intersect them, and apply the resolver outcomes from leg 1a. The leg 1c artifact does NOT import from `connectors/base.py`.
- **`agents.md` connector-type checklist (item 4) edit is structural prose, not test contract**: the wording matters for future operators / debrief reviewers, not for test pass/fail. A leg-1c-time edit covers it.

## Files Affected

- `the_one/agent/config.py` — REQUIRED IMPORT EDIT: add `field_validator` to the pydantic import; add 1 Pydantic field + 1 field_validator classmethod (~35 lines after the dead-code trim)
- `the_one/db/schema.py` — bump CURRENT_VERSION 17 → 18; add v18 migration block (~25 lines); update 4 prediction-comment sites (L485-491 stale-pre-leg v14 → v19; L546-548 renumber-to-v18 → v19; L586-588 renumber-to-v18 → v19; L636-640 renumber-to-v18 → v19)
- `the_one/db/_connector_types.py` — update module docstring (~7 lines)
- `the_one/db/repositories.py` — extend SQLiteAgentStore.save INSERT + ON CONFLICT (~3 lines) + parameter tuple (~1 line) + _row_to_config kwargs (~1 line)
- `the_one/agents.md` — update connector-type extension checklist item 4 (~2 surgical edits on L302)
- `the_one/connectors/README.md` — update §6 "stub type reserved" section: L297 schema-range update + L303 F8 CHECK v15 → v19 (stale-pre-leg fix)
- `tests/test_db_migration.py` — bump CURRENT_VERSION assertion (1 line) + comment block extension (1 line) + L1131 stale-pre-leg "v14 in flight 8" → "v19" + L1171,L1179 prose comments (2 lines) + 4 downstream-renumber docstring blocks (TestSchemaV{14,15,16,17}, rewriting the L1261/L1445 multi-line renumber chains as single-current-statement) + new TestSchemaV18 class (~100 lines)
- `tests/test_db_repositories.py` — 6 new test methods on TestSQLiteAgentStore (~150 lines) + new TestAgentConfigConnectorAclsValidator class (~120 lines, 10+ validator tests) appended to the same file (lighter than a new module; matches leg-1b's organization)
- `the_one/connectors/base.py` — UNCHANGED (leg 1a's surface is already adequate; legs 2/3 join)
- `the_one/db/models.py` — UNCHANGED (leg 1b touches ConnectorAccount, not AgentConfig)
- `the_one/interfaces/web/api.py` — UNCHANGED (leg 5's Studio Agent Editor Connectors tab is the operator-facing surface; leg 1c is persistence-only)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry (including ripple-site enumeration: 4 schema.py prediction-comment sites updated, 1 _connector_types.py docstring updated, 1 agents.md checklist site updated, 5 test_db_migration.py docstring sites updated, 1 new TestSchemaV18 class added, 4+ TestSQLiteAgentStore round-trip tests added, 10+ validator tests added)
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed`
- [ ] Do NOT modify flight.md
- [ ] Do NOT commit (deferred-batched workflow)

## Citation Audit

Citations verified against current code at leg design time:
- `the_one/agent/config.py:111-156` — confirmed (AgentConfig with connector_account_ids, mcp_overrides shape)
- `the_one/agent/config.py:135` — confirmed (`connector_account_ids: list[str] = Field(default_factory=list)`)
- `the_one/agent/config.py:153` — confirmed (`mcp_overrides: dict[str, dict[str, Any]] | None = None` precedent)
- `the_one/db/schema.py:11` — confirmed (`CURRENT_VERSION = 17`)
- `the_one/db/schema.py:485-491` — confirmed (stale-pre-leg "flight 8 will land v14" prediction; design-time grep located this)
- `the_one/db/schema.py:546-548,586-588,636-640` — confirmed (3 active v18-renumber prediction blocks)
- `the_one/connectors/README.md:297,303` — confirmed (2 stale-pre-leg F8 CHECK prediction sites; design-time grep located these)
- `tests/test_db_migration.py:1131` — confirmed (stale-pre-leg "v14 in flight 8" TestSchemaV13 docstring)
- `tests/test_db_migration.py:1261-1267,1445-1449` — confirmed (4-line renumber chains in TestSchemaV14 and TestSchemaV15 docstrings)
- `the_one/db/schema.py:628-655` — confirmed (v17 migration block; template for v18)
- `the_one/db/_connector_types.py:7-18` — confirmed (F8 CHECK prediction docstring)
- `the_one/db/repositories.py:94-137` — confirmed (`SQLiteAgentStore.save` shape)
- `the_one/db/repositories.py:190-216` — confirmed (`_row_to_config` shape)
- `tests/test_db_migration.py:234-238` — confirmed (CURRENT_VERSION assertion at v17)
- `tests/test_db_migration.py:1171,1179,1262,1448-1449,1638-1639,1867-1879` — confirmed (5 downstream-renumber sites)
- `tests/test_db_migration.py:1867-2026` — confirmed (TestSchemaV17 class; template for TestSchemaV18)
- `tests/test_db_repositories.py:207+` — confirmed (TestSQLiteAgentStore connector_account_ids round-trip)
- `the_one/agents.md:302` — confirmed (connector-type checklist item 4)

All citations verified at design time + cycle-1 review.

## Cycle-1 design review closure

Cycle-1 Developer-agent review returned "needs rework" (5 high, 3 medium, 2 low). All findings addressed in this revision:

- [high] `field_validator` import claim corrected to REQUIRED edit (Implementation Guidance §1; Acceptance Criteria).
- [high] `schema.py:490` citation corrected: actual content is stale-pre-leg "flight 8 will land v14" prediction (NOT v18). Ripple Sites updated to L485-491 with v14 → v19 framing.
- [high] Missed ripple sites added: `connectors/README.md:297,303` (2 sites); `tests/test_db_migration.py:1131` + L1261-1267 + L1445-1449 (3 docstring sites — the latter two now rewritten as single-current-statements rather than surgical edits to the multi-rebase chain).
- [medium] Validator dead code removed: trimmed to the ONE invariant Pydantic's annotation cannot express (exact-keys `{"peers", "channels"}`). Empirical verification of Pydantic v2 native rejection (non-string outer key, non-dict outer value, non-list inner value, non-string inner entry) documented inline.
- [medium] Non-string outer key edge case corrected: empirically verified Pydantic v2 REJECTS (no coercion); test asserts deterministically.
- [medium] H2-closure test added: `test_validator_fires_on_repo_read_path_connector_acls` mirrors leg-1b's equivalent.
- [medium] Empty-outer-dict round-trip test added: `test_save_round_trips_empty_outer_dict_connector_acls` distinguishes JSON-literal `"{}"` truthy-string from SQL NULL falsy.
- [low] Test line citations marked as approximate (±3) — implementing agent uses grep to locate; absolute line numbers in this artifact may drift between design and implementation.
- [low] `**v19**` markdown emphasis preserved in the v17-block-renumber template.
