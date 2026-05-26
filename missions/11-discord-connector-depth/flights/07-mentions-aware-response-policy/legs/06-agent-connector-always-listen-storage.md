# Leg: agent-connector-always-listen-storage

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Add a new `connector_always_listen: dict[str, bool] | None` field to `AgentConfig` (per-account toggle keyed by account_id, default None = "all-False semantic"); ship the DB migration (new `connector_always_listen TEXT` column on the `agents` table) + repository codec + Pydantic validator + API surface acceptance + tests, all atomic in one leg. Mirrors the M10 F6 L1c `connector_acls` precedent across all five surfaces.

## Context

- **Flight DD §8 (Architect-finalized)** — `connector_always_listen` is a named field (not a generic policy bucket). Mirrors the `connector_acls` precedent at `agent/config.py:246` (per-account dict keyed by `account_id`, distinct from list-shaped ACL data). Validator follows the `connector_acls` validator template at `agent/config.py:251-311`. YAGNI bias from `agents.md` rules out the speculative generic-bucket option until a second per-account policy field surfaces.
- **Atomic-leg-pattern (per agents.md)** — Pydantic field + DB migration + repository codec + `AgentFactory` consumer (NONE in L6 — the AgentFactory consumer reads come in L8 the policy gate / L11 the UI) + tests all land here. L6 ships the storage surface only; L8 reads at the gate; L11 reads at the UI.
- **Validator discipline (DD §8)** — validator enforces only the shape: outer keys are `account_id` strings, inner values are bools. Composition with `account.always_listen` (the account-level master switch from L5) is at runtime, not at validate time. Per the DD: "the dispatcher's gate composition already handles the False+True case correctly by checking account first; accept-and-document is the lighter discipline." A `True` per-agent toggle with `False` account-level toggle is structurally inert (the account check short-circuits), so the validator accepts the inconsistency rather than rejecting it.
- **None vs `{}` distinction** — `None` decodes from NULL DB rows (pre-v20 agents AND new agents with no per-agent override). `{}` decodes from `"{}"` JSON (an agent that was edited then had all toggles removed). Both have the same runtime semantic ("no per-account override present"); the distinction is preserved by the codec for round-trip fidelity (mirrors the `connector_acls` None vs `{}` distinction).
- **DB migration version** — v18 is `connector_acls` (M10 F6 L1c). v19 is F8 L2's CHECK constraint on `connector_accounts`. L6 ships **v20** with the same idempotent ALTER ADD COLUMN pattern.
- **L6 / L11 boundary** — L6 ships storage + API + validator. L11 ships the UI (the per-agent toggle in the agent's Connectors tab). After L6 lands, the operator can hand-edit the agent JSON via the existing agent-editor JSON path (or POST to the API directly) to set `connector_always_listen`. Until L11 ships the toggle UI, the operator has the data path but no checkbox.

## Inputs

- L1–L5 landed uncommitted. `ConnectorAccount.config["always_listen"]` exists (L5); `connector_acls` field on `AgentConfig` exists (M10 F6 L1c) with v18 migration in place; `_validate_connector_acls` validator template exists at `agent/config.py:251-311`.
- `the_one/agent/config.py:173-246` — `AgentConfig` class declaration with the `connector_acls` field at the end (~line 246). New field appends after `connector_acls`.
- `the_one/agent/config.py:251-311` — `_validate_connector_acls` validator template. L6 mirrors the shape (`@field_validator(..., mode="after")`).
- `the_one/db/schema.py:677-706` — v18 migration block (the `connector_acls` ALTER ADD COLUMN precedent). L6 adds a v20 block in the same shape.
- `the_one/db/repositories.py:158-159` — encode path: `json.dumps(config.connector_acls) if ... is not None else None`.
- `the_one/db/repositories.py:241-247` — decode path: `connector_acls=(json.loads(row["connector_acls"]) if row["connector_acls"] else None)`. L6 mirrors with the new column.
- `the_one/interfaces/web/api.py:457-487` — POST/PUT endpoints validate via `AgentConfig.model_validate(data)`; new field flows automatically via Pydantic; no api.py change required for happy path.
- `tests/test_db_repositories.py:278-312, 407-447` — round-trip + validator-on-read tests for `connector_acls`. L6 mirrors with the new field.

## Outputs

- `the_one/agent/config.py`:
  - **ADD** new field `connector_always_listen: dict[str, bool] | None = None` immediately after `connector_acls` at the end of `AgentConfig`. Docstring above the field cites M11 F7 L6, names the L5 account-level capability switch as the precondition (per-agent True is structurally inert when account.always_listen is False), notes the absent-account_id → False default at the policy-gate consult site (L8).
  - **ADD** field validator `_validate_connector_always_listen` immediately after `_validate_connector_acls`. Mirrors the `connector_acls` precedent's approach of relying on the type annotation for outer-key shape (Pydantic v2 handles `dict[str, bool]`'s string-key coercion/rejection at annotation level) and using the validator body only for inner-value invariants the annotation can't express:
    ```python
    @field_validator("connector_always_listen", mode="after")
    @classmethod
    def _validate_connector_always_listen(
        cls, value: dict[str, bool] | None
    ) -> dict[str, bool] | None:
        """Enforce inner-value bool invariants on the per-agent toggle dict.

        Shape contract: outer keys are account_id strings (enforced by the
        ``dict[str, bool]`` annotation; Pydantic v2 coerces or rejects
        non-str keys before the validator runs). Inner values must be bools
        — defensively enforced here against truthy-but-non-bool smuggling
        through the kv-table or raw-JSON edit paths.

        Runtime semantic (NOT validator-enforced — composition happens at
        the L8 policy-gate consult site):
        - The account-level ``always_listen`` switch (L5) is the master
          gate; per-agent True is structurally inert when account-level
          is False (the account check short-circuits).
        - Absent account_id in the dict → False (the per-agent default).
        - Explicit False is equivalent to absent and round-trips as-is so
          the codec preserves the operator's intent.

        Per Flight DD §8: "accept-and-document is the lighter discipline"
        — the validator does NOT reject inconsistent (per-agent True +
        account-level False) configurations; the dispatcher's gate
        composition handles them correctly at runtime.
        """
        if value is None:
            return value
        for account_id, toggle in value.items():
            if not isinstance(toggle, bool):
                raise ValueError(
                    f"connector_always_listen[{account_id!r}] must be a bool "
                    f"(True or False); got {type(toggle).__name__}: {toggle!r}"
                )
        return value
    ```
- `the_one/db/schema.py`:
  - **ADD** a v20 migration block immediately after the v19 block, mirroring the v18 `connector_acls` shape:
    ```python
    if version < 20:
        # M11 F7 L6: AgentConfig.connector_always_listen persistence.
        # Per-agent toggle keyed by account_id (dict[str, bool] | None);
        # NULL pre-L6 rows AND new agents without per-agent overrides
        # decode to None. Idempotent ALTER ADD COLUMN pattern mirrors
        # v18's connector_acls migration.
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "connector_always_listen" not in existing_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN connector_always_listen TEXT"
            )
        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (20,),
        )
    ```
- `the_one/db/repositories.py`:
  - **THREE update sites in `SQLiteAgentStore.save()`** (lines 119-164 per cycle-1 review — the SQL has an upsert pattern with ON CONFLICT, so column references appear in three places):
    - **(a)** `INSERT INTO agents (...)` column list (~line 123-128): append `connector_always_listen` to the column list.
    - **(b)** `VALUES (?, ?, ...)` placeholder count (~line 128) AND the corresponding tuple/parameter list passed to `execute()`: add a `?` placeholder AND the `json.dumps(config.connector_always_listen) if config.connector_always_listen is not None else None` value in the tuple at the matching position.
    - **(c)** `ON CONFLICT(name) DO UPDATE SET ...` clause (~line 129-143): append `connector_always_listen=excluded.connector_always_listen`. **WITHOUT THIS the upsert path silently retains the original value on update** — this is the specific bug shape `tests/test_db_repositories.py:300-312` (the connector_acls test) was added to catch.
  - **ADD** to `SQLiteAgentStore._row_to_config()` (around line 217-248 — after the connector_acls decode):
    ```python
    # M11 F7 L6: per-agent always_listen toggle. NULL (pre-v20 rows
    # AND default for agents without per-agent overrides) decodes
    # to None, distinguishing it from `{}` (an agent that was edited
    # then had all toggles removed).
    connector_always_listen=(
        json.loads(row["connector_always_listen"])
        if row["connector_always_listen"]
        else None
    ),
    ```
- `the_one/interfaces/web/api.py` — NO CODE CHANGE. The POST/PUT endpoints at lines 457-487 flow through `AgentConfig.model_validate(data)`; the new field is picked up by Pydantic automatically. Response includes the field via `cfg.model_dump()`. Verified by the round-trip test.
- New tests in `tests/test_db_repositories.py` — mirror the full `connector_acls` precedent at lines 278-755. Add them inside (or alongside) a new `TestAgentConfigConnectorAlwaysListenValidator` class for the validator tests and the existing repository test class for the round-trip tests:
  - `test_save_round_trips_connector_always_listen` — `connector_always_listen={"acct-a": True, "acct-b": False}`, save → load → assert equality. **MUST include an upsert-overwrite assertion**: save once, then save again with a different `connector_always_listen` value, then load and assert the SECOND value persists (catches the ON CONFLICT SET clause bug per cycle-1 review).
  - `test_save_round_trips_connector_always_listen_none` — save with field `None`, load → assert None preserved.
  - `test_save_round_trips_empty_outer_dict_connector_always_listen` — save with `{}`, load → assert `{}` preserved (distinct from None).
  - `test_load_pre_v20_agent_has_none_connector_always_listen` — write a row directly via raw SQL with `connector_always_listen` column NULL, load through the repo, assert `loaded.connector_always_listen is None`. Mirrors the connector_acls pre-v18 back-compat test at `test_db_repositories.py:347-384` per cycle-1 review.
  - `test_validator_rejects_non_bool_inner_value` — `connector_always_listen={"acct-a": "yes"}` → ValidationError.
  - `test_validator_accepts_true_per_agent_toggle_without_cross_check_against_account` — `connector_always_listen={"acct-a": True}` validates cleanly with no account-level cross-check (locks the DD §8 accept-and-document discipline).
  - `test_orphan_account_id_toggle_validates_cleanly` — `connector_always_listen={"acct-not-attached": True}` with `connector_account_ids=[]` validates fine (mirrors the `connector_acls` precedent: validator does NOT cross-check against `connector_account_ids`; dead-data is allowed).
  - `test_validator_fires_on_repo_read_path_connector_always_listen` — write valid row → UPDATE the row's `connector_always_listen` column with malformed JSON → load raises ValidationError. Mirrors `test_validator_fires_on_repo_read_path_connector_acls` at line 407.
- New tests in `tests/test_db_migration.py` (verified file path — singular, not `test_db_migrations.py`). Mirror the full v18 `TestSchemaV18` class at lines 2075-2254 — THREE tests:
  - `test_v20_fresh_db_includes_agents_connector_always_listen_column` — fresh DB, run migrate, `connector_always_listen` column exists on `agents` table.
  - `test_v20_migration_idempotent_on_rerun` — run migrate twice, no error on second run; schema_version row 20 persists.
  - `test_v20_legacy_v19_row_decodes_with_none_connector_always_listen` — pre-v20 row hand-inserted, run migrate, load through repo, `connector_always_listen` is None.
- New tests in `tests/test_db_api.py` (verified file path — NOT `test_api_agents.py`):
  - `test_create_agent_persists_connector_always_listen` — POST `/agents` with `connector_always_listen` in the payload; verify GET returns it; verify DB row has the column populated. Extend or mirror the existing `test_create_agent` family at lines 51, 75.
  - `test_update_agent_clears_connector_always_listen` — POST then PUT with `connector_always_listen=None` (or missing); verify the field clears.

## Acceptance Criteria

- [ ] `the_one/agent/config.py:AgentConfig` has the new `connector_always_listen: dict[str, bool] | None = None` field appended after `connector_acls`, with M11 F7 L6 docstring naming the L5 precondition and the L8 consumer.
- [ ] `the_one/agent/config.py` has `_validate_connector_always_listen` field validator mirroring `_validate_connector_acls`'s template shape; enforces outer-key-str + inner-value-bool; accepts None.
- [ ] `the_one/db/schema.py` has a v20 migration block adding `connector_always_listen TEXT` to the `agents` table; idempotent ALTER ADD COLUMN; schema_version row 20 inserted.
- [ ] `the_one/db/repositories.py:SQLiteAgentStore.save()` writes `json.dumps(config.connector_always_listen) if not None else None` at the new column position; `_row_to_config()` decodes the column with the None-on-NULL semantic. The SQL column list / placeholder count in `save()` is updated.
- [ ] `the_one/interfaces/web/api.py` is unchanged (Pydantic flow-through verified by the round-trip test).
- [ ] `tests/test_db_repositories.py` has the eight new tests listed in Outputs (round-trip × 3 + back-compat × 1 + validator × 4).
- [ ] `tests/test_db_migration.py` (singular) has the THREE new v20 migration tests mirroring `TestSchemaV18`.
- [ ] `tests/test_db_api.py` has the two new API round-trip tests.
- [ ] `docker exec the-one pytest tests/test_db_repositories.py tests/test_db_migration.py tests/test_db_api.py tests/test_agent_config.py -x --timeout 30` passes.
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L6-introduced regressions.
- [ ] Flight log L6 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md`. Leg artifact status set to `landed`.

## Verification Steps

- `python -c "from the_one.agent.config import AgentConfig; print(AgentConfig.model_fields['connector_always_listen'])"` prints field metadata (not None — confirms the field is registered on the model).
- `python -c "from the_one.agent.config import AgentConfig; AgentConfig(name='x', connector_always_listen={'a': True, 'b': False})"` does NOT raise.
- `python -c "from the_one.agent.config import AgentConfig; AgentConfig(name='x', connector_always_listen={'a': 'yes'})"` raises `ValidationError` mentioning `connector_always_listen` and `bool`.
- `python -c "from the_one.agent.config import AgentConfig; AgentConfig(name='x', connector_always_listen=None)"` does NOT raise.
- DB migration test: run targeted test for v20.
- Round-trip test: save/load with each of None, `{}`, `{"a": True}`, `{"a": True, "b": False}` and assert equality.
- API round-trip: POST then GET the agent, verify `connector_always_listen` survives.
- Targeted: `docker exec the-one pytest tests/test_db_repositories.py tests/test_db_migrations.py tests/test_api_agents.py tests/test_agent_config.py -x --timeout 30` — all green (file paths verified at impl time).
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Add the AgentConfig field + validator** per Outputs. Append both blocks at the end of the existing definitions to keep diff scope tight. Mirror the `connector_acls` docstring shape so a reader knows where to look for the parallel template.

2. **Add the v20 migration** at the end of the existing if-version-N chain in `the_one/db/schema.py`. Verify the version-number sequence by reading the highest pre-L6 version (v19 per recon); use v20.

3. **Update the repository codec** per Outputs:
   - `save()` encode site: add the `json.dumps(...)` line for the new column. Verify the column-list SQL + placeholder count; an off-by-one here is the most common bug shape for this pattern.
   - `_row_to_config()` decode site: add the JSON-decode-or-None line for the new column.
   - **Important**: the column-position ordering in `save()` MUST match the order of `?` placeholders in the SQL INSERT statement AND the order of column reads in `_row_to_config()`. Triple-check by reading the v18 precedent.

4. **Confirm api.py is unaffected** — read the endpoints at lines 457-487, verify the `AgentConfig.model_validate(data)` flow picks up the new field automatically (it does for all `BaseModel` fields). The new field appears in `cfg.model_dump()` responses without code change.

5. **Add tests** per Outputs (cycle-1 review verified file paths):
   - **Eight in `tests/test_db_repositories.py`** mirroring `connector_acls` tests at lines 278-755 (round-trip × 3 with upsert-overwrite assertion in the first one, back-compat × 1, validator × 4). Place validator tests inside a new `TestAgentConfigConnectorAlwaysListenValidator` class to mirror `TestAgentConfigConnectorAclsValidator` at line 598.
   - **Three in `tests/test_db_migration.py`** (singular path, verified) mirroring `TestSchemaV18` at lines 2075-2254: fresh-DB, idempotent-rerun, legacy-pre-v19-row decodes.
   - **Two in `tests/test_db_api.py`** (verified path; NOT `test_api_agents.py`): extend or mirror the existing `test_create_agent` family at lines 51, 75.

6. **Run tests** per Verification Steps. Update flight log under `## Leg Progress` with `### L6 — agent-connector-always-listen-storage`. Check off in flight.md. Set L6 status to `landed`. Do NOT commit.

## Edge Cases

- **Pre-v20 agents loaded after L6 lands** — `connector_always_listen` column is NULL → decodes to None → policy gate at L8 sees the absent-account semantic → all per-agent toggles effectively False → bot stays mentioned-only for all accounts (the F7 default). No surprise behavior.
- **`connector_always_listen={"acct-x": True}` with `acct-x` not in `connector_account_ids`** — the agent has a toggle for an account it isn't attached to. Validator does NOT cross-check (mirroring `connector_acls`'s precedent: it doesn't cross-check either). Runtime consumer (L8 gate) only consults the toggle when actually routing for that account; orphan entries are inert. Tests don't need to pin this — it's a "dead data" condition similar to ACL entries for non-attached accounts.
- **`connector_always_listen={}` (empty dict)** — encodes to JSON `"{}"`; decodes back to `{}`. Distinct from None at the codec layer (preserves operator's "I edited then cleared" intent). At the policy-gate runtime, both have the same semantic (no per-account toggle present → all-False default).
- **Pydantic outer-key coercion** — the test `test_validator_rejects_non_str_outer_key` pins whichever behavior Pydantic exhibits. If Pydantic v2 coerces non-str keys to str, the validator's `if not isinstance(account_id, str)` check fires before the coercion can take effect (the validator runs in `mode="after"` so it sees the post-coercion shape — confirm at impl time by inspecting whether the validator sees coerced or pre-coerced keys).
- **A POST that omits `connector_always_listen` entirely** — Pydantic uses the default `None`; the field appears in `cfg.model_dump()` as None; DB write stores NULL; subsequent GET returns None. Symmetric with `connector_acls`.
- **JSON-coding of the dict** — Python dict with string keys + bool values serializes to JSON as `{"a": true, "b": false}` (lowercase booleans). Round-trip is byte-identical at the JSON layer.
- **Migration idempotency under repeated runs** — the PRAGMA-guard on the ALTER ADD COLUMN is the existing convention (v18 uses it). Re-running the migration is safe.
- **L8 runtime read pattern** — when L8's policy gate consults `config.connector_always_listen`, the read pattern mirrors L5's account-level read: `config.connector_always_listen.get(account_id, False) if config.connector_always_listen else False`. L8 picks this up in its own leg artifact.

## Files Affected

- `the_one/agent/config.py` — ADD field + validator.
- `the_one/db/schema.py` — ADD v20 migration block.
- `the_one/db/repositories.py` — UPDATE `save()` + `_row_to_config()` encode/decode paths + SQL column list.
- `the_one/interfaces/web/api.py` — NO CHANGE (Pydantic flow-through).
- `tests/test_db_repositories.py` — ADD 8 new tests mirroring the `connector_acls` precedent (round-trip × 3 incl. upsert-overwrite + back-compat × 1 + validator × 4 in a new `TestAgentConfigConnectorAlwaysListenValidator` class).
- `tests/test_db_migration.py` — ADD 3 new v20 migration tests mirroring `TestSchemaV18`.
- `tests/test_db_api.py` — ADD 2 API round-trip tests.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND `## Leg Progress` entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Commit all changes — DEFERRED per F7 flight-level commit ordering.

## Citation Audit

Citations verified against current code at design time via the F7 L6 reconnaissance pass:

- `the_one/agent/config.py:173-246` — AgentConfig class declaration + connector_acls field (verified).
- `the_one/agent/config.py:251-311` — `_validate_connector_acls` validator template (verified).
- `the_one/db/schema.py:677-706` — v18 connector_acls migration precedent (verified).
- `the_one/db/repositories.py:158-159, 241-247` — encode + decode paths for connector_acls (verified).
- `the_one/interfaces/web/api.py:457-487` — POST/PUT endpoints with AgentConfig.model_validate flow (verified).
- `tests/test_db_repositories.py:278-312, 407-447` — round-trip + validator-on-read tests for connector_acls (verified).
- Latest schema version pre-L6: v19 (F8 L2's connector_accounts CHECK constraint); L6 uses v20.

Test file paths for the migration test and the API test are flagged for verification at implementation time — the Developer agent locates the exact test files for v18 migration and `connector_acls` API tests and mirrors them.
