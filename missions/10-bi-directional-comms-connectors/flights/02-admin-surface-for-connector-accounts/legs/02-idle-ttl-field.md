# Leg: idle-ttl-field

**Status**: completed
**Flight**: [Admin Surface for Connector Accounts](../flight.md)

## Objective

Add the per-account `idle_timeout_seconds` field to the connector-account persistence layer (v15 schema migration + Pydantic model + repository round-trip) and thread the per-account override through the pool's TTL resolver, so the operator-visible field surfaced by leg 3 (REST CRUD) and leg 6 (UI) is semantically meaningful rather than vestigial.

## Context

### Why this leg

Per the flight's Design Decision "Idle-TTL: persist + wire through the pool, not persist-only; pool resolver takes an `int | None` override, NOT the whole account":

- Mission criterion: "Each connector-attached session has a defined lifecycle ... surfaces from the connector account's Admin detail page as a configurable parameter."
- Flight 2's reading of that criterion (per the "Session-lifecycle parameter (idle-timeout) mission-text disambiguation" Design Decision): the **connector-pool idle-TTL** is the parameter Flight 2 surfaces (the chat-session lifecycle is Flight 3 territory and needs Flight 3's schema migration to land).
- For the parameter to be semantically operator-visible from the Admin detail page, it must (a) persist on the `ConnectorAccount` row and (b) flow into pool behaviour. Persist-only would leave operators editing a vestigial field.

The architect-refined resolver shape is `_resolve_ttl_seconds(override: int | None = None) -> int` — the pool stays ignorant of which model field drives the override; the model owns the field name; the resolver owns the precedence. This preserves the `live-read-across-lazy-resolver-boundary` invariant (env var is read at call time, not at module import).

### Relevant design decisions

- **Idle-TTL persist + wire through the pool** — drives the four edit surfaces in this leg: schema migration, model field + validator, repository round-trip, resolver signature change + acquire wiring.
- **Schema version v15 for `idle_timeout_seconds`; Flight 8's CHECK migration renumbers from v15 to v16** — codifies the schema-version sequencing this leg inherits (leg 1 already patched `agents.md` checklist item 4 and corrected the Flight-1 leg-2 carry-forward language).
- **`idle_timeout_seconds` validation bounds (1 ≤ value ≤ 604800 = 7 days)** — drives the Pydantic validator; rejects the milliseconds-vs-seconds typo (`idle_timeout_seconds: 31_536_000_000` is suspiciously high).
- **`"Session-lifecycle parameter (idle-timeout)" mission-text disambiguation`** — names this field as the **connector-pool** TTL, NOT the chat-session lifecycle. The repository column ships in v15; the Pydantic field name (`idle_timeout_seconds`) reflects this; the chat-session lifecycle column lands in Flight 3 alongside (likely named differently, e.g. `session_continuation_window_seconds`, so the UI in Flight 3 + this leg's UI in leg 6 can render two distinct labels next to each other).

### Key learnings from prior flights

- **F1 leg-2 schema-version renumber precedent** — when F1 leg 2 took v14 for the `name` column, it bumped `CURRENT_VERSION`, updated every `tests/test_db_migration.py` site that hardcoded the head version (including the `assert CURRENT_VERSION == 14` message), updated `_connector_types.py`'s docstring referencing the next-version claim, and added Design Adjustments note in the flight log. This leg replicates that mechanical pattern for the v14 → v15 renumber.
- **`live-read-across-lazy-resolver-boundary` is named precedent** — environment-driven resolvers MUST read the env var at call time (`os.environ.get(...)` inside the function body), NOT capture it at module import or function-entry. The existing `_resolve_ttl_seconds` already does this; this leg's signature change extends the same shape with a new positional argument.
- **F1 leg-6 docstring shape** — `_resolve_ttl_seconds` at `connectors/_pool.py:122-143` is the canonical precedent for documenting an env-var-driven resolver: docstring names the env var, the default, and the "fail open" stance on bad input. This leg's update preserves that shape and inserts the override semantics.

## Inputs

What exists before this leg runs:

- `the_one/db/schema.py:CURRENT_VERSION = 14` (top of file); the v14 ALTER block at L512-536 is the most recent migration. v15 has no block.
- `the_one/db/_connector_types.py:11-15` — module docstring currently claims v15 (CHECK constraint, Flight 8) and notes v14 is claimed by the `name` ALTER. Needs to renumber: v15 is now claimed by THIS leg's `idle_timeout_seconds` ALTER; the CHECK migration becomes v16.
- `the_one/db/models.py:118-137` — `ConnectorAccount` Pydantic model with `id, name, type, config, secrets, created_at, updated_at`. No `idle_timeout_seconds` field.
- `the_one/db/repositories.py:502-559` — `ConnectorAccountRepository.create` / `update` / `_row_to_model` round-trip the 7 existing fields.
- `the_one/connectors/_pool.py:122-143` — `_resolve_ttl_seconds() -> int` (no arg); reads env var at call time; default 1800; logs warning + falls back on non-int.
- `the_one/connectors/_pool.py:396-451` — `acquire()` constructs `_RegistryEntry` at L437-441 with `ttl_seconds=_resolve_ttl_seconds()` (no override).
- `tests/test_db_migration.py:228-230` — `assert CURRENT_VERSION == 14, ("CURRENT_VERSION must be 14 after the connector_accounts.name v14 migration (got {CURRENT_VERSION})")` — the assertion value AND the error message both reference v14 + the F1 L2 migration explicitly.
- `tests/test_db_migration.py:1230-1243` — `TestSchemaV14` class docstring includes "flight 08 (Discord) previously planned a v14 CHECK migration; that renumbers to v15" — needs to renumber to v16.
- `tests/test_connectors_pool.py:346-382` — four tests pin the existing `_resolve_ttl_seconds()` (no-arg) shape: default, env override, non-int fallback, read-at-call-time.
- `tests/test_db_repositories.py:392-559` — `TestConnectorAccountRepository` covers the existing create/list/update/delete round-trip plus encrypted-secrets cases.

## Outputs

What exists after this leg completes:

- `the_one/db/schema.py:CURRENT_VERSION = 15`; a new v15 block applies `ALTER TABLE connector_accounts ADD COLUMN idle_timeout_seconds INTEGER NULL` with PRAGMA-guarded idempotency, ending with `INSERT OR IGNORE INTO schema_version (version) VALUES (?)" (15)` LAST before `commit`.
- `the_one/db/_connector_types.py` docstring (around L11-15) — renumbered to reference v15 (this leg) and v16 (Flight 8 CHECK migration).
- `the_one/db/models.py:ConnectorAccount` — adds `idle_timeout_seconds: int | None = None` with a Pydantic `@field_validator` that enforces `value is None or (1 <= value <= 604800)` and raises `ValueError("idle_timeout_seconds must be between 1 and 604800 seconds (7 days)")` on violation.
- `the_one/db/repositories.py:ConnectorAccountRepository.create` / `update` / `_row_to_model` — round-trip the new column. `create` INSERT extends the column list and the `VALUES` tuple. `update` UPDATE extends the SET clause. `_row_to_model` reads `row["idle_timeout_seconds"]` (sqlite3 returns `None` for NULL, the Pydantic default handles unknown legacy rows transparently).
- `the_one/connectors/_pool.py:_resolve_ttl_seconds(override: int | None = None) -> int` — signature change. Resolution order: explicit override (if not None) → env var (if set + parseable) → default 1800. Docstring updated to document the new override parameter and the resolution-order contract. The existing live-read semantics are preserved (env var still read at call time).
- `the_one/connectors/_pool.py:acquire()` — the `_RegistryEntry(ttl_seconds=_resolve_ttl_seconds(), ...)` call at L438 becomes `_resolve_ttl_seconds(override=account.idle_timeout_seconds)`.
- `tests/test_db_migration.py:228-230` — `assert CURRENT_VERSION == 15` with message rewritten to reference the F2-L2 migration (so the assertion's failure message stays accurate post-bump).
- `tests/test_db_migration.py:1230-1243` — `TestSchemaV14` class docstring — "renumbers to v15" becomes "renumbers to v16."
- `tests/test_db_migration.py` — new `TestSchemaV15` class with three tests: (a) v15 migration applies cleanly to a v14 database (idempotency), (b) `connector_accounts.idle_timeout_seconds` column exists and is `INTEGER` nullable, (c) `idle_timeout_seconds` defaults to NULL for pre-existing v14 rows.
- `tests/test_connectors_pool.py` — four existing `_resolve_ttl_seconds` tests stay green (no-arg calls now resolve as `_resolve_ttl_seconds(override=None)`, which falls through to env-var / default — byte-identical behaviour). Three NEW tests pin the override branch: (a) explicit override beats env var, (b) explicit override beats default, (c) `override=None` is treated identically to no-arg.
- `tests/test_db_repositories.py:TestConnectorAccountRepository` — TWO new tests: (a) `idle_timeout_seconds` round-trips through create + get when set to a real value (e.g. 600), (b) `idle_timeout_seconds` round-trips as `None` when not set (and survives a no-op update). Existing tests stay green (the default-None field doesn't change any existing fixture's payload).
- `tests/test_db_repositories.py` or wherever Pydantic model unit tests live — at least one new test asserting the validator rejects bounds violations (`idle_timeout_seconds=0` → `ValueError`; `idle_timeout_seconds=604801` → `ValueError`; `idle_timeout_seconds=None` → OK; `idle_timeout_seconds=1` → OK; `idle_timeout_seconds=604800` → OK). If a dedicated model-test file exists, use it; otherwise embed the validator tests alongside the repository round-trip tests.
- Flight log "Leg Progress" entry appended.
- Flight artifact's leg-2 checkbox ticked.

## Acceptance Criteria

- [ ] `CURRENT_VERSION == 15` in `the_one/db/schema.py`.
- [ ] Applying `ensure_schema` against a v14 database is idempotent and crash-safe; running it twice in a row leaves `MAX(schema_version) == 15` with no error.
- [ ] `connector_accounts.idle_timeout_seconds` exists in the schema as `INTEGER` NULL; pre-existing v14 rows decode to `idle_timeout_seconds=None`.
- [ ] `ConnectorAccount.idle_timeout_seconds: int | None = None` with the `1 ≤ value ≤ 604800` validator; `None` is the default + accepted; `0` and `604801` are rejected with the canonical `ValueError` message.
- [ ] `ConnectorAccountRepository.create` / `update` / `_row_to_model` round-trip `idle_timeout_seconds` (both `None` and a real value).
- [ ] `_resolve_ttl_seconds(override: int | None = None) -> int` honours the resolution order: explicit override → env var → default. Live-read invariant preserved (env var read at call time).
- [ ] `acquire()` passes `override=account.idle_timeout_seconds` into `_resolve_ttl_seconds` so the warm entry's `ttl_seconds` reflects the per-account configured value.
- [ ] All four existing `_resolve_ttl_seconds` tests remain green (no-arg call resolves identically).
- [ ] Three NEW resolver tests pin the override branch + the precedence ordering.
- [ ] Two NEW repository tests pin the `idle_timeout_seconds` round-trip.
- [ ] At least three NEW validator tests pin the bounds + the None-accepts-default.
- [ ] One NEW `TestSchemaV15` test class with at least 3 tests (migration idempotency + column shape + None-default).
- [ ] `_connector_types.py` docstring reflects v15 (this leg) and v16 (Flight 8 CHECK).
- [ ] `tests/test_db_migration.py:228-230` assertion value AND message reflect v15 + the F2-L2 migration.
- [ ] `tests/test_db_migration.py:1230-1243` `TestSchemaV14` docstring says "renumbers to v16" (not v15).
- [ ] `make test` clean; `make lint` clean. Pass count delta: +at least 8 tests, no regressions.

## Verification Steps

How to confirm each criterion:

- `grep -n "^CURRENT_VERSION" the_one/db/schema.py` — shows `CURRENT_VERSION = 15`.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py::TestSchemaV15 tests/test_db_migration.py::TestSchemaV14 tests/test_db_migration.py::TestSchemaV8` — all green.
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py::test_resolve_ttl_seconds_default_is_1800 tests/test_connectors_pool.py::test_resolve_ttl_seconds_reads_env_override tests/test_connectors_pool.py::test_resolve_ttl_seconds_non_int_falls_back tests/test_connectors_pool.py::test_resolve_ttl_seconds_read_at_call_time` — all green (existing four).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py -k "resolve_ttl"` — all 7 tests green (existing 4 + new 3).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestConnectorAccountRepository` — green; new round-trip and validator tests present and passing.
- `grep -n "idle_timeout_seconds" the_one/db/schema.py the_one/db/models.py the_one/db/repositories.py the_one/connectors/_pool.py` — every expected site lights up.
- `grep -n "v16\|renumbers to v16" the_one/db/_connector_types.py tests/test_db_migration.py the_one/agents.md` — leg 1's agents.md item-4 update reflects v16; `_connector_types.py` docstring reflects v16; `TestSchemaV14` docstring reflects v16.
- `make test` — full suite clean.
- `make lint` — clean.

## Implementation Guidance

1. **Add the v15 schema migration** (`the_one/db/schema.py`)
   - Bump `CURRENT_VERSION` from 14 to 15 at L11.
   - Append a `if version < 15:` block AFTER the v14 block (L512-536) and BEFORE the function's terminating `return`. Use the v11 / v14 ALTER pattern as the template — PRAGMA-guarded idempotency:
     ```python
     if version < 15:
         # Add `idle_timeout_seconds` column to connector_accounts. Mission 10
         # flight 02 leg 02: operator-configurable per-account pool idle TTL.
         # Nullable INTEGER — NULL means "use _resolve_ttl_seconds default /
         # env-var override" (the existing pre-flight-02 behaviour). Bounded
         # at the Pydantic layer (1 ≤ value ≤ 604800) to catch the
         # milliseconds-vs-seconds typo.
         #
         # Downstream: flight 08 (Discord) previously planned a v15 CHECK
         # migration; that renumbers to v16. See _connector_types.py
         # docstring + tests/test_db_migration.py TestSchemaV14 docstring.
         #
         # Idempotency follows the v11/v14 ALTER ADD COLUMN pattern (PRAGMA
         # guard + INSERT OR IGNORE on schema_version LAST).
         async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
             existing_cols = {row[1] for row in await cursor.fetchall()}
         if "idle_timeout_seconds" not in existing_cols:
             await conn.execute(
                 "ALTER TABLE connector_accounts ADD COLUMN idle_timeout_seconds INTEGER NULL"
             )

         await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (15,))
         await conn.commit()
         version = 15
     ```

2. **Update `_connector_types.py` docstring** (`the_one/db/_connector_types.py:11-15`)
   - Current text references "v15 table-rename ceremony when there is a real type to constrain (v14 is claimed by leg 2's `name` column ALTER)."
   - Updated text: "v16 table-rename ceremony when there is a real type to constrain (v14 → `name` column on `connector_accounts` (F1 L2); v15 → `idle_timeout_seconds` (F2 L2); v16 is Flight 8's CHECK constraint via the table-rename ceremony established by v6/v12)."

3. **Add the `idle_timeout_seconds` field to `ConnectorAccount`** (`the_one/db/models.py:118-137`)
   - Add `idle_timeout_seconds: int | None = None` AFTER `secrets: dict[str, Any] = Field(default_factory=dict)` and BEFORE `created_at: str = Field(default_factory=_now_iso)` — placement that mirrors a fresh new field, not interleaved with timestamps.
   - Add the field validator under the same class (use Pydantic v2 `@field_validator` syntax — confirm against other `db/models.py` validators):
     ```python
     @field_validator("idle_timeout_seconds")
     @classmethod
     def _validate_idle_timeout_seconds(cls, value: int | None) -> int | None:
         if value is None:
             return value
         if not (1 <= value <= 604800):
             raise ValueError(
                 "idle_timeout_seconds must be between 1 and 604800 seconds (7 days)"
             )
         return value
     ```
   - **Verify import**: if `field_validator` is not already imported at the top of `models.py`, add `from pydantic import field_validator` (likely needed alongside an existing `from pydantic import ...`). Reuse existing imports if present.

4. **Round-trip the new column in `ConnectorAccountRepository`** (`the_one/db/repositories.py:502-559`)
   - `create` — extend the INSERT column list to include `idle_timeout_seconds`; add a `?` to the VALUES tuple; add `account.idle_timeout_seconds` to the tuple in the same position. **Column ordering in the INSERT statement is arbitrary** as long as the values tuple matches — the ALTER appends `idle_timeout_seconds` at the END of the physical schema (so `PRAGMA table_info` will list it last). `_row_to_model` uses keyed access, so physical column order doesn't matter for reads.
   - `update` — extend the UPDATE SET clause to include `idle_timeout_seconds=?`. The current SET clause is `name=?, type=?, config=?, secrets=?, updated_at=?`. Insert `idle_timeout_seconds=?` BEFORE `updated_at=?` to keep the tuple ordering visually consistent with `create` (no functional requirement, just readability). Add `account.idle_timeout_seconds` at the matching position in the tuple.
   - `_row_to_model` — add `idle_timeout_seconds=row["idle_timeout_seconds"]`. SQLite returns Python `None` for NULL cells, which matches the Pydantic default for unknown legacy rows.

5. **Change `_resolve_ttl_seconds` signature** (`the_one/connectors/_pool.py:122-143`)
   - New signature: `def _resolve_ttl_seconds(override: int | None = None) -> int:`
   - Updated docstring:
     ```
     Resolution order: explicit ``override`` (if not None) → env var
     ``THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`` (if set + parseable) →
     ``_DEFAULT_TTL_SECONDS`` (1800). Env var is read at call time so test
     monkeypatching works; mirrors :func:`the_one.mcp._pool._resolve_ttl_seconds`.

     The override is the per-account ``ConnectorAccount.idle_timeout_seconds``
     value, passed through by :func:`acquire`. The pool stays ignorant of
     which model field drives the override; the model owns the field name,
     the resolver owns the precedence.

     Non-int env-var values fall back to the default with a warning — matches
     the MCP pool's "fail open, don't crash startup" stance.
     ```
   - Body:
     ```python
     if override is not None:
         return override
     raw = os.environ.get("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS")
     if raw is None:
         return _DEFAULT_TTL_SECONDS
     try:
         return int(raw)
     except ValueError:
         logger.warning(
             "THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS=%r is not an int; falling back to %d",
             raw,
             _DEFAULT_TTL_SECONDS,
         )
         return _DEFAULT_TTL_SECONDS
     ```
   - Note: the `override is not None` guard short-circuits BEFORE the env-var read by design — the operator's explicit per-account choice always wins, regardless of what the env var says.

6. **Thread the override through `acquire`** (`the_one/connectors/_pool.py:438`)
   - Change `ttl_seconds=_resolve_ttl_seconds(),` to `ttl_seconds=_resolve_ttl_seconds(override=account.idle_timeout_seconds),`.
   - `account` is already loaded one line above (`account = await _load_account(account_id, encryptor)` at L428).

7. **Bump and patch `tests/test_db_migration.py`**
   - L228-230 — change `assert CURRENT_VERSION == 14` to `assert CURRENT_VERSION == 15`; rewrite the failure message to reference v15 + the F2-L2 migration: `"CURRENT_VERSION must be 15 after the connector_accounts.idle_timeout_seconds v15 migration (got {CURRENT_VERSION})"`.
   - L1240-1243 — `TestSchemaV14` docstring: change "flight 08 (Discord) previously planned a v14 CHECK migration; that renumbers to v15" → "flight 08 (Discord) previously planned a v14 CHECK migration; that renumbers to v16 (v15 is claimed by flight 02 leg 02's `idle_timeout_seconds` ALTER)."
   - Add a new `TestSchemaV15` class AFTER `TestSchemaV14`, mirroring `TestSchemaV14`'s structure. At minimum three tests:
     - `test_v15_fresh_db_includes_idle_timeout_seconds_column` — fresh `ensure_schema`, assert `CURRENT_VERSION >= 15`, assert the column exists and is INTEGER nullable.
     - `test_v15_legacy_v14_row_decodes_with_none_idle_timeout` — seed a row at v14 (via a manual INSERT into a v14-fresh DB), run ensure_schema to v15, assert the row decodes with `idle_timeout_seconds=None`.
     - `test_v15_migration_is_idempotent` — run `ensure_schema` twice; assert no error and the final schema_version is 15.

8. **Add new resolver tests** (`tests/test_connectors_pool.py`, alongside the existing 4 tests at L346-382)
   - `test_resolve_ttl_seconds_override_beats_env(monkeypatch)` — set `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS=60`; assert `_resolve_ttl_seconds(override=300) == 300`.
   - `test_resolve_ttl_seconds_override_beats_default(monkeypatch)` — ensure env unset; assert `_resolve_ttl_seconds(override=300) == 300`.
   - `test_resolve_ttl_seconds_none_override_falls_through(monkeypatch)` — set env=60; assert `_resolve_ttl_seconds(override=None) == 60` (proves `override=None` is treated identically to the no-arg call).
   - Optional 4th: `test_resolve_ttl_seconds_override_is_returned_directly` — assert `_resolve_ttl_seconds(override=1)` returns 1 (no Pydantic-style bound check at the pool layer — the Pydantic validator at the model edge is the gate; pool trusts pre-validated input).

9. **Add new repository tests** (`tests/test_db_repositories.py`, within `TestConnectorAccountRepository`)
   - `test_idle_timeout_seconds_round_trips_real_value` — create with `idle_timeout_seconds=600`; get; assert value preserved through `update` + re-get.
   - `test_idle_timeout_seconds_round_trips_none` — create with default (None); get; assert `None`; update; assert still `None`.
   - Validator tests (one of):
     - Inside the same `TestConnectorAccountRepository` class (more practical — co-located with the field):
       - `test_idle_timeout_seconds_validator_rejects_zero` — `ConnectorAccount(..., idle_timeout_seconds=0)` raises `ValueError` with "between 1 and 604800" in `str(exc)`.
       - `test_idle_timeout_seconds_validator_rejects_one_week_plus_one` — same shape with `604801`.
       - `test_idle_timeout_seconds_validator_accepts_bounds` — `1` and `604800` both succeed; `None` succeeds.

10. **Run scoped tests then full suite**
    - `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py tests/test_connectors_pool.py tests/test_db_repositories.py` — green.
    - `make test` — full suite green. Expected delta: +8-12 tests on the 1774 baseline.
    - `make lint` — clean.

11. **Update artifacts and the flight log**
    - Set this leg's status to `landed` after acceptance criteria pass.
    - Append a "Leg Progress" entry to the flight log under `## Leg Progress` summarizing: schema v15 migration, model field + validator, repository round-trip, resolver signature change + acquire wiring, schema-version renumber sites updated, test deltas.
    - Check off this leg in `flight.md` Legs list.
    - Do NOT commit — review and commit happen once at the end of the flight per `/agentic-workflow`.

## Edge Cases

- **`field_validator` import shape** — Pydantic v2 syntax. Confirm with `grep -n "field_validator\|from pydantic" the_one/db/models.py`. If only `validator` is imported (Pydantic v1 style), add the v2 import — but the project is already on Pydantic v2 (per `LLMProviderConfig`'s validators); the v2 import almost certainly already exists.
- **`acquire()` test breakage** — the change at L438 passes `account.idle_timeout_seconds` (which is None for any account that doesn't set it; the resolver falls through to env/default). The behaviour for existing tests using accounts without `idle_timeout_seconds` is byte-identical. If a test fixture seeds an account dict via `model_validate` and DOESN'T include the new field, Pydantic uses the default `None`. No test changes required for this branch.
- **SQLite NULL vs Python None in `_row_to_model`** — `aiosqlite.Row` returns Python `None` for NULL cells. Pydantic accepts `None` for `int | None`. No conversion needed.
- **`mcp/_pool.py` parallel resolver** — `the_one.mcp._pool._resolve_ttl_seconds` does NOT take an override (MCP doesn't have a per-source TTL field today). DO NOT touch the MCP resolver in this leg — it is a separate subsystem with its own design constraints and changing its signature would be scope creep.
- **Connector pool test fixtures that mock `_resolve_ttl_seconds`** — if any test monkey-patches `_resolve_ttl_seconds` directly (rather than env-var-driving it), the patched callable's signature must accept the new `override` kwarg. Audit with `grep -rn "monkeypatch.*_resolve_ttl_seconds\|setattr.*_resolve_ttl_seconds" tests/` before implementing; update any mocks to accept the new signature.
- **`__init__` ordering with `idle_timeout_seconds` between `secrets` and `created_at`** — Pydantic doesn't care about field ordering for default behaviour, but JSON-schema-emitted property order may change. If any test does an exact JSON-schema string-equality check on `ConnectorAccount.model_json_schema()`, update it. Likely none — but grep for `model_json_schema` to confirm.
- **Connector account fixture factories** — if `tests/test_db_repositories.py` or `tests/test_connectors_pool.py` use a helper like `_make_account(...)` that constructs `ConnectorAccount` instances, the helper doesn't need updating (the new field has a default). New tests can pass `idle_timeout_seconds=...` as a kwarg without changing the helper. **Specifically verified**: `tests/test_connectors_pool.py::_make_stub_account` (around L70-81) does NOT set `idle_timeout_seconds`, so `test_entry_ttl_seconds_is_resolved_at_acquire_time` (around L317-329) continues to pass after the `acquire()` change at step 6 — the stub account returns `idle_timeout_seconds=None` and the resolver falls through to the env/default chain (byte-identical behaviour for that test).
- **Legacy v14 row test precedent** — `tests/test_db_migration.py::TestSchemaV14::test_v14_legacy_row_*` (around L1305-1345) is the existing template for "seed a row at v(N-1), run migration, assert the new column decodes with NULL." Step 7's new `test_v15_legacy_v14_row_decodes_with_none_idle_timeout` should copy that pattern.
- **Legacy v14 rows without the column** — once v15 migration runs, the ALTER adds the column with default NULL. Pre-existing rows decode as `idle_timeout_seconds=None`. Test `test_v15_legacy_v14_row_decodes_with_none_idle_timeout` pins this. If the operator chose to leave Flight 1's stub rows in a test DB and re-runs migrations, they'll keep working untouched.

## Files Affected

- `the_one/db/schema.py` — bump `CURRENT_VERSION` to 15; add the v15 ALTER block (~20 LoC).
- `the_one/db/_connector_types.py` — 1-line docstring update reflecting v15/v16 sequencing.
- `the_one/db/models.py` — add `idle_timeout_seconds: int | None = None` + the validator (~12 LoC).
- `the_one/db/repositories.py` — extend `ConnectorAccountRepository.create` / `update` / `_row_to_model` (~5 LoC net change across three methods).
- `the_one/connectors/_pool.py` — `_resolve_ttl_seconds` signature change + docstring (~10 LoC); `acquire()` one-line change at L438.
- `tests/test_db_migration.py` — assertion + message rewrite at L228-230 (~2 LoC); `TestSchemaV14` docstring patch (~1 LoC); new `TestSchemaV15` class with at least 3 tests (~80 LoC).
- `tests/test_connectors_pool.py` — three new resolver-override tests (~30 LoC).
- `tests/test_db_repositories.py` — two new round-trip tests + three new validator tests (~50 LoC).
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight-log.md` — Leg Progress entry.
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight.md` — leg-2 checkbox.

## State-Machine Reachability Audit

This leg introduces a new lifecycle value (`idle_timeout_seconds`) but no new state machine. The value is operator-set, range-validated at the Pydantic edge, persisted as INTEGER NULL, and consumed by `_resolve_ttl_seconds` with the documented precedence. No FK, CHECK, or trigger touches the new column.

- **DB-level reachability**: the column is NULLABLE INTEGER with no DEFAULT. Existing v14 rows have implicit DEFAULT NULL via the ALTER. New rows can store any 32-bit-int value the application provides; the Pydantic validator gates the upper end at 604800, but the DB has NO upper bound — a hand-crafted INSERT bypassing Pydantic could set a higher value, and the next `acquire` would honor it. Acceptable: the Pydantic layer is the operator-facing gate; bypassing it requires direct DB access (which means the operator is debugging, not configuring).
- **Cache invalidation**: warm pool entries cache `ttl_seconds` at acquire-time. An operator update of `idle_timeout_seconds` after a warm entry exists does NOT update the warm entry's `ttl_seconds` — the new value applies on the NEXT `acquire` after the entry is evicted. This is consistent with how the PUT branch in leg 3 will handle credential changes (evict-on-actual-change). Per-account TTL is fundamentally similar: a credential change MUST evict (credentials are auth-bearing); a TTL change SHOULD evict but the operational impact of waiting until next eviction is bounded by the OLD TTL (worst case ~30 min on the default). Leg 3 will document whether the PUT branch evicts on TTL change as well as on credential change. THIS LEG ships the persistence + the resolver; the eviction-on-TTL-change behaviour is a leg-3 acceptance criterion, not a leg-2 one. Add a hint in the flight log "Decisions" section noting this gets resolved at leg 3 design time.

## Cache Freshness Contract

For the `_pool` registry entries' `ttl_seconds` cache:

- **Source of truth**: `connector_accounts.idle_timeout_seconds` per row; or env var; or default.
- **Rebuild trigger**: per-entry, at `acquire` time. The cached value lives for the lifetime of the warm entry (until eviction).
- **Maximum staleness**: until next eviction. With the default 30-min TTL, an operator changing `idle_timeout_seconds` on a warm account sees the change applied on the next `acquire` after the eviction (worst case 30 min for an idle account; immediate for an active conversation that re-acquires).
- **User-action invalidation map**: PUT on the connector account (leg 3) MUST consider whether to evict on TTL change. Until leg 3 ships the eviction-on-PUT logic, the staleness window is "until the warm entry naturally evicts." Leg 3's acceptance criteria pin this.

## Files Affected (re-stated)

See the explicit list above.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test` passing (pass-count delta: +8 to +12 expected; report actual)
- [ ] `make lint` clean
- [ ] Flight log updated with a "Leg Progress" entry summarizing the v15 migration + model + repository round-trip + resolver signature change + renumber bookkeeping + test deltas
- [ ] This leg's status updated to `landed` (in this file's header)
- [ ] This leg checked off in `flight.md` Legs list
- [ ] Do NOT commit — review and commit happen once at the end of the flight per `/agentic-workflow`

---

## Citation Audit

11 code-location citations verified against current code at leg design time:

- `the_one/db/schema.py: CURRENT_VERSION = 14` (L11) — **OK** (verified live).
- `the_one/db/schema.py: v14 ALTER block` (L512-536, beginning `if version < 14:`) — **OK** (verified; the v15 block in step 1 appends after this block).
- `the_one/db/_connector_types.py: docstring referencing v15 + v14` (L11-15) — **OK** (verified — exact phrase "v15 table-rename ceremony" and "v14 is claimed by leg 2's `name` column ALTER" present).
- `the_one/db/models.py: ConnectorAccount` (L118-137) — **OK** (verified; 7-field model, no `idle_timeout_seconds`).
- `the_one/db/repositories.py: ConnectorAccountRepository.create / update / _row_to_model` (L502-559) — **OK** (verified; current INSERT/UPDATE/decode shape exact match).
- `the_one/connectors/_pool.py: _resolve_ttl_seconds` (L122-143) — **OK** (verified; no-arg signature, env-var-at-call-time, default 1800).
- `the_one/connectors/_pool.py: acquire ttl_seconds=_resolve_ttl_seconds()` (L438) — **OK** (verified; the call site referenced in step 6).
- `the_one/connectors/_pool.py: account = await _load_account(account_id, encryptor)` (L428) — **OK** (verified; account is in scope at L438).
- `tests/test_db_migration.py: TestSchemaV8 assert CURRENT_VERSION == 14` (L228-230) — **OK** (verified; assertion value 14 + error message reference v14 + connector_accounts.name v14 migration).
- `tests/test_db_migration.py: TestSchemaV14 docstring "renumbers to v15"` (L1230-1243) — **OK** (verified).
- `tests/test_connectors_pool.py: 4 existing _resolve_ttl_seconds tests` (L346-382) — **OK** (verified; test names match exactly).

0 citations drifted, 0 unverifiable.
