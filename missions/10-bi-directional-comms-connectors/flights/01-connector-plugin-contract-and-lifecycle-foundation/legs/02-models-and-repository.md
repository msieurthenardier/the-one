# Leg: models-and-repository

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Land the `ConnectorAccount` Pydantic model (mirroring `MCPSource`), the `ConnectorAccountRepository` with encrypted-secrets CRUD (mirroring `MCPSourceRepository`), and a v14 schema migration that adds the missing `name TEXT NOT NULL DEFAULT ''` column to `connector_accounts` so the model can truly mirror MCPSource.

## Context

This is leg 2 of Flight 1 of Mission 10 (bi-directional communication connectors). Leg 1 landed the v13 migration that created `connector_accounts (id, type, config, secrets, created_at, updated_at)`, `the_one/db/_connector_types.py` with the empty `CONNECTOR_TYPES: tuple[str, ...] = ()` tuple, and the rotation-transaction extension covering connector secrets atomically.

### Design adjustment caught during leg 2 planning: add `name` column via v14 migration

The flight spec says "**`the_one/db/models.py`** — `ConnectorAccount` Pydantic model (mirrors `MCPSource` shape; …)". `MCPSource` at `db/models.py:MCPSource` has six fields: `id`, **`name`**, `type`, `config`, `secrets`, `created_at`, `updated_at`. The v13 schema enumerated columns omitted `name`. To truly mirror MCPSource (a stated flight design decision) and to give Flight 2's admin UI a first-class display field for distinguishing accounts (e.g. two Discord bots), this leg adds:

- A **v14 migration** that does `ALTER TABLE connector_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''`. Uses the v11-style nullable-ALTER-ADD-COLUMN pattern — but with `NOT NULL DEFAULT ''` so existing rows (zero in practice — the table is new and empty in leg 1) get populated with empty string and new INSERTs must provide name. Bumps `CURRENT_VERSION` from 13 to 14.
- **Pydantic `ConnectorAccount.name: str`** (no default — required at create/update time, matching `MCPSource.name`'s shape).

**Downstream impact**: the flight spec mentions "v14 in Flight 8 adds CHECK via table-rename." That CHECK migration now becomes **v15** in Flight 8. This leg updates the flight spec text to reflect the renumbering and captures the rationale in the flight log under a new "Design Adjustments" section.

### Other design constraints from the flight that bind this leg

- **No `merged_config()` helper** on `ConnectorAccount`. Per flight Design Decisions: deferred to Flight 6 when per-agent override composition is wired. Connectors will have nested config; a flat top-level merge (the MCP shape) would reproduce M07 F1's K3 nested-merge bug.
- **No Literal narrowing on `type` yet.** `CONNECTOR_TYPES` is empty `()`; Python's `Literal[]` is invalid syntax with zero args. Use `type: str` for now. When Flight 8 (Discord) adds `'discord'` to `CONNECTOR_TYPES`, that flight's models leg narrows `type` to `Literal["discord"]` and adds the canonical `assert set(get_args(...)) == set(CONNECTOR_TYPES)` pin alongside `LLMProviderConfig`'s assert at `db/models.py:59-61`.
- **No `__MASKED__` sentinel handling in the repository.** Per `LLMProviderConfig._normalize_api_key` docstring at `db/models.py:43-48`, the `__MASKED__` sentinel path runs at the API edge (`interfaces/web/api.py::update_provider`), NOT in the repository. Mirror this: the repository in this leg stores whatever it's given; Flight 2's admin REST endpoints will handle `__MASKED__`.
- **No `find_by_runtime_package` analog.** That method on `MCPSourceRepository` (lines 378-414) refcounts lazy-install cache cleanup at MCP-source delete time. Connectors have no parallel cache-cleanup concern. Skip.
- **No `AgentConfig.connector_account_ids` field.** Per flight Design Decisions: deferred to Flight 4 when the platform-send tool needs to read it.

## Inputs

What exists before this leg runs:

- Leg 1 landed (uncommitted on `flight/01-connector-plugin-contract-and-lifecycle-foundation` branch)
- `the_one/db/schema.py:CURRENT_VERSION = 13`
- `connector_accounts` table exists with columns: `id`, `type`, `config`, `secrets`, `created_at`, `updated_at` (NO `name`, NO CHECK on type)
- `the_one/db/_connector_types.py` exists with `CONNECTOR_TYPES: tuple[str, ...] = ()`
- Rotation transaction at `interfaces/web/api.py:rotate_encryption_key` covers connector secrets atomically with LLM + MCP corpora
- Patterns this leg mirrors:
  - `MCPSource` model at `the_one/db/models.py:MCPSource` (lines 86-107) — six fields, `merged_config()` helper, no Literal pinning assert (that's `LLMProviderConfig`'s at lines 59-61, the canonical example)
  - `MCPSourceRepository` at `the_one/db/repositories.py:MCPSourceRepository` (lines 291-425) — `__init__(conn, encryptor)` with encryptor-as-reference, `_secrets_to_ciphertext`/`_ciphertext_to_secrets` encryption envelope, list/get/create/update/delete CRUD methods, `_row_to_model` deserializer
  - `MCPSourceRepository` test fixture pattern at `tests/test_db_repositories.py:51-65` — function-scoped `mcp_repo_encryptor` fixture (DO NOT widen to module/session scope per the in-file comment), `mcp_repo` fixture composing conn + encryptor
  - `TestMCPSourceRepository` test class at `tests/test_db_repositories.py:260` — 9 tests covering create_and_get, list, update, delete, secrets_round_trip, secrets_encrypted_at_rest, empty_secrets_default, install_key_post_create_decrypts_via_same_instance, plus merged_config tests
  - Migration patterns: v11 ALTER ADD COLUMN at `db/schema.py:412-430` is the structural template (PRAGMA check + ALTER with no DEFAULT). v14 here uses `NOT NULL DEFAULT ''` because we DO want a column-level default to satisfy NOT NULL for any rows that might exist.

## Outputs

- New `ConnectorAccount` Pydantic model in `the_one/db/models.py` — sibling to `MCPSource`. Six fields (`id`, `name`, `type`, `config`, `secrets`, `created_at`, `updated_at`). No `merged_config()`. `type: str` (unconstrained until Flight 8 adds Literal narrowing + pinning assert).
- New `ConnectorAccountRepository` in `the_one/db/repositories.py` — sibling to `MCPSourceRepository`. Same encryption envelope, same CRUD shape, same encryptor-reference invariant. No `find_by_runtime_package` analog.
- v14 migration in `the_one/db/schema.py:ensure_schema` — `ALTER TABLE connector_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''`. `CURRENT_VERSION` bump 13→14. Idempotency follows the v11 ALTER pattern + `INSERT OR IGNORE INTO schema_version` LAST.
- Flight spec text updated: any reference to "v14 in Flight 8 adds CHECK" becomes "v15 in Flight 8 adds CHECK"; the leg log captures the renumbering rationale.
- New `TestSchemaV14` class in `tests/test_db_migration.py` covering: fresh DB has the column; idempotent rerun.
- New `connector_repo_encryptor` and `connector_repo` fixtures in `tests/test_db_repositories.py` mirroring the MCP fixtures.
- New `TestConnectorAccountRepository` test class — 8 parallel tests (skipping the merged_config tests since we don't ship that helper).
- All tests pass; `make test`, `make lint` clean.
- Leg status `landed`.
- Flight log: `### Leg 02: models-and-repository` entry + `## Design Adjustments` section capturing the v14-name-column + v15-renumber decision.

## Acceptance Criteria

- [ ] `ConnectorAccount` Pydantic model exists in `the_one/db/models.py` with fields: `id: str`, `name: str`, `type: str`, `config: dict[str, Any]` (Field default_factory=dict), `secrets: dict[str, Any]` (Field default_factory=dict), `created_at: str` (Field default_factory=_now_iso), `updated_at: str` (Field default_factory=_now_iso)
- [ ] `ConnectorAccount` has NO `merged_config()` helper
- [ ] `ConnectorAccount` has NO `_normalize_*` validator (no `__MASKED__` handling at this layer)
- [ ] A comment near `ConnectorAccount` notes: "`type` is `str` until Flight 8 narrows it to `Literal[...]` once `CONNECTOR_TYPES` is non-empty; the pinning assert lands then."
- [ ] No drift assert is added against `CONNECTOR_TYPES` in this leg (the tuple is empty; a no-op assert is misleading). A short comment near `_connector_types.py` import in `models.py` flags the deferral.
- [ ] `ConnectorAccountRepository` exists in `the_one/db/repositories.py` with: `__init__(conn: aiosqlite.Connection, encryptor: Encryptor)` (encryptor stored as reference, not copy), `_secrets_to_ciphertext`, `_ciphertext_to_secrets` (tolerant of `InvalidToken` → `{}`; JSONDecodeError NOT swallowed), `list()`, `get(account_id)`, `create(account)`, `update(account)`, `delete(account_id)`, `_row_to_model(row)`. Methods raise `KeyError(f"Connector account not found: {account_id}")` when the row is missing on get/update/delete.
- [ ] `ConnectorAccountRepository` has NO `find_by_runtime_package` analog and NO other MCP-specific helpers
- [ ] v14 migration block in `the_one/db/schema.py:ensure_schema`: `if version < 14:` guard; uses individual `await conn.execute(...)` calls (no `executescript`); the `ALTER TABLE connector_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''` is idempotent (PRAGMA table_info guard, mirroring v11's `if "mcp_overrides" not in existing_cols:` pattern at `db/schema.py:423-426`); `INSERT OR IGNORE INTO schema_version (version) VALUES (?)` with `(14,)` is LAST before `await conn.commit()` and `version = 14`
- [ ] `the_one/db/schema.py:CURRENT_VERSION` is `14`
- [ ] `TestSchemaV8` hardcoded `CURRENT_VERSION` assertion at `tests/test_db_migration.py:227` is updated to `14` and the f-string message references v14 = name column on connector_accounts
- [ ] A fresh DB run of `ensure_schema` lands at v14 with `name TEXT NOT NULL DEFAULT ''` on `connector_accounts`
- [ ] A re-run of `ensure_schema` against a DB already at v14 is a no-op (PRAGMA check skips the ALTER; `INSERT OR IGNORE` swallows the duplicate)
- [ ] A v13 → v14 step on a fixture DB seeded with one connector_accounts row (via direct SQL, since v13 had no name column) preserves the row and populates the new `name` column with empty string
- [ ] New `TestSchemaV14` class in `tests/test_db_migration.py` covers: fresh-DB shape (column exists with correct PRAGMA `notnull=1` and `dflt_value="''"`); idempotent rerun; v13→v14 step on a v13-seeded row
- [ ] New `connector_repo_encryptor` and `connector_repo` fixtures in `tests/test_db_repositories.py` (function-scoped, mirroring `mcp_repo_encryptor` at line 51 and `mcp_repo` at line 63)
- [ ] New `TestConnectorAccountRepository` class in `tests/test_db_repositories.py` covers (parallel to `TestMCPSourceRepository`):
    - `test_create_and_get`
    - `test_list` (alphabetical by name)
    - `test_update`
    - `test_delete`
    - `test_secrets_round_trip`
    - `test_secrets_encrypted_at_rest`
    - `test_empty_secrets_default`
    - `test_install_key_post_create_decrypts_via_same_instance`
- [ ] `test_rotate_connector_account_secrets` and `test_rotate_preserves_connector_secrets_on_db_failure` (added in leg 1) STILL PASS after the v14 migration lands — they seed via raw SQL with `(id, type, config, secrets)`, which after v14 requires the `name` column to fall through to its `DEFAULT ''`. Verify they pass; if they don't, update them to explicitly pass `name=''` or similar canonical name in the seed.
- [ ] All existing tests still pass (no regression on LLM-provider or MCP-source paths)
- [ ] `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py tests/test_db_repositories.py tests/test_provider_api.py tests/test_encryption.py tests/test_schema.py` is clean
- [ ] `make test` and `make lint` are clean for the whole suite
- [ ] Flight spec text updated: every reference to "v14 in Flight 8" → "v15 in Flight 8" (Flight 8 description in the Legs section; Design Decisions block on schema versioning; anywhere else that mentions the renumbering)
- [ ] Flight log has a `## Design Adjustments` section (new section, not in the existing template) capturing: (a) why v14 = name column landed in leg 2 instead of leg 1; (b) Flight 8's CHECK migration renumbers to v15; (c) any other small adjustments
- [ ] Flight log has a `### Leg 02: models-and-repository` entry
- [ ] Leg status is `landed` (NOT `completed`)
- [ ] `schema-and-migration` and `models-and-repository` checkboxes ticked in the flight artifact's Legs section

## Verification Steps

1. **Pydantic model shape**:
   - `docker exec the-one python -c "from the_one.db.models import ConnectorAccount; ca = ConnectorAccount(id='a', name='b', type='stub'); assert ca.name == 'b' and ca.config == {} and ca.secrets == {}; print('ok')"`
   - `docker exec the-one python -c "from the_one.db.models import ConnectorAccount; assert not hasattr(ConnectorAccount, 'merged_config'); print('ok')"`

2. **Repository shape**:
   - `docker exec the-one python -c "from the_one.db.repositories import ConnectorAccountRepository; print(ConnectorAccountRepository.__init__.__doc__ or 'ok')"`
   - `docker exec the-one python -c "from the_one.db.repositories import ConnectorAccountRepository; assert not hasattr(ConnectorAccountRepository, 'find_by_runtime_package'); print('ok')"`

3. **Schema head pointer is 14**:
   - `docker exec the-one python -c "from the_one.db.schema import CURRENT_VERSION; assert CURRENT_VERSION == 14; print('ok')"`

4. **v14 migration is idempotent + adds the column**:
   - `TestSchemaV14.test_v14_fresh_db_includes_name_column` is the canonical verifier
   - `TestSchemaV14.test_v14_migration_idempotent_on_rerun` covers the rerun case
   - `TestSchemaV14.test_v14_preserves_v13_seeded_row_with_empty_name` covers the migration step on a pre-existing row

5. **Repository contract**:
   - All 8 tests in `TestConnectorAccountRepository` pass
   - Raw DB read of `secrets` column does NOT contain plaintext value (the encrypted-at-rest test)

6. **Rotation tests from leg 1 still pass**:
   - `docker exec the-one pytest -x --timeout 30 tests/test_provider_api.py -k "connector"` returns 2 passed

7. **No regression**:
   - `docker exec the-one pytest -x --timeout 30` full suite is green
   - `make lint` clean

## Implementation Guidance

Execute in this order:

### Step 1: Add v14 migration in `the_one/db/schema.py`

Bump `CURRENT_VERSION` 13 → 14 at line 11.

Add the new migration block as the last block in `ensure_schema` (after the v13 block from leg 1):

```python
    if version < 14:
        # Add `name` column to connector_accounts. Caught during leg 02 of
        # mission 10 flight 01: the flight spec said "mirror MCPSource shape"
        # but the v13 migration omitted the column. MCPSource has `name: str`
        # as a first-class column for operator-visible identification
        # (Studio agent editor + MCP admin surface both render `name`).
        # Connector accounts inherit the same display surface in flight 2.
        #
        # NOT NULL DEFAULT '' lets the ALTER succeed against any v13-seeded
        # row (in practice zero — the table was empty at v13). New rows
        # created through ConnectorAccountRepository will always carry a real
        # `name` because the Pydantic model requires it (no default).
        #
        # Idempotency follows the v11 ALTER ADD COLUMN pattern (PRAGMA guard
        # + INSERT OR IGNORE on schema_version LAST).
        async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "name" not in existing_cols:
            await conn.execute(
                "ALTER TABLE connector_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''"
            )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (14,))
        await conn.commit()
        version = 14
```

### Step 1b: Update the brittle hardcoded `CURRENT_VERSION` assertion in `TestSchemaV8`

`tests/test_db_migration.py:227` has the same regression-loud-fail guard leg 1 had to bump. It currently reads (post-leg-1):

```python
assert CURRENT_VERSION == 13, (
    f"CURRENT_VERSION must be 13 after connector_accounts v13 migration (got {CURRENT_VERSION})"
)
```

(Or close to that — read the file to get the exact wording.) Update the constant `13 → 14` and the message to mention v14 = `name` column on `connector_accounts`. This is part of the `CURRENT_VERSION` bump, NOT a separately-discovered brittle test — track it as expected in this leg's flight-log entry, not as "pre-existing test brittleness surfaced."

### Step 2: Add `ConnectorAccount` Pydantic model in `the_one/db/models.py`

Add immediately after the existing `MCPSource` class (which ends at `db/models.py:107`). Import `CONNECTOR_TYPES` is NOT needed yet — leave the import-free state for now and document the deferral.

```python
class ConnectorAccount(BaseModel):
    """A connector account — operator-registered third-party-platform identity.

    Mirrors :class:`MCPSource` shape. Stored in ``connector_accounts``
    (v13 table; v14 added the ``name`` column to match MCPSource).

    ``type`` is currently :class:`str` (unconstrained). When the first real
    connector type lands in flight 8, the spec is to narrow this to
    ``Literal[...]`` and add a ``get_args``-based pinning assert against
    ``CONNECTOR_TYPES`` from ``the_one.db._connector_types``, paralleling
    :class:`LLMProviderConfig`'s assert at the top of this module.
    """

    id: str
    name: str
    type: str  # narrows to Literal in flight 8 when CONNECTOR_TYPES is non-empty
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
```

Do NOT add a `merged_config()` method. Do NOT add a `_normalize_*` validator. Do NOT add a pinning assert (the tuple is empty).

### Step 3: Add `ConnectorAccountRepository` in `the_one/db/repositories.py`

Locate the file's end of MCP-source content (after `MCPSourceRepository._row_to_model` at line 425). Add `ConnectorAccountRepository` as a sibling class. Mirror `MCPSourceRepository` exactly:

```python
class ConnectorAccountRepository:
    """Async CRUD for connector accounts."""

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
        self.conn = conn
        self.encryptor = encryptor  # Reference, NOT copy. install_key() post-rotation
        # must propagate to live repository instances.
        # Mirrors MCPSourceRepository at the top of this file.

    def _secrets_to_ciphertext(self, secrets: dict[str, Any]) -> str:
        return self.encryptor.encrypt(json.dumps(secrets))

    def _ciphertext_to_secrets(self, ciphertext: str | None) -> dict[str, Any]:
        """Decrypt the secrets column. Mirrors MCPSourceRepository's path.

        Empty/None ciphertext returns ``{}``. ``InvalidToken`` is the
        migration-residue path (v13 column default ``'{}'`` is plaintext,
        not ciphertext); silently fall back to ``{}`` and let the next
        ``update()`` rewrite with proper ciphertext.

        ``JSONDecodeError`` propagates — that indicates real corruption,
        not migration residue.
        """
        if not ciphertext:
            return {}
        try:
            plaintext = self.encryptor.decrypt(ciphertext)
        except InvalidToken:
            return {}
        return json.loads(plaintext)

    async def list(self) -> list[ConnectorAccount]:
        async with self.conn.execute(
            "SELECT * FROM connector_accounts ORDER BY name"
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, account_id: str) -> ConnectorAccount:
        async with self.conn.execute(
            "SELECT * FROM connector_accounts WHERE id = ?", (account_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Connector account not found: {account_id}")
        return self._row_to_model(row)

    async def create(self, account: ConnectorAccount) -> None:
        await self.conn.execute(
            "INSERT INTO connector_accounts"
            " (id, name, type, config, secrets, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                account.id,
                account.name,
                account.type,
                json.dumps(account.config),
                self._secrets_to_ciphertext(account.secrets),
                account.created_at,
                account.updated_at,
            ),
        )
        await self.conn.commit()

    async def update(self, account: ConnectorAccount) -> None:
        async with self.conn.execute(
            "SELECT 1 FROM connector_accounts WHERE id = ?", (account.id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account.id}")
        await self.conn.execute(
            "UPDATE connector_accounts"
            " SET name=?, type=?, config=?, secrets=?, updated_at=? WHERE id=?",
            (
                account.name,
                account.type,
                json.dumps(account.config),
                self._secrets_to_ciphertext(account.secrets),
                _now_iso(),
                account.id,
            ),
        )
        await self.conn.commit()

    async def delete(self, account_id: str) -> None:
        async with self.conn.execute(
            "SELECT 1 FROM connector_accounts WHERE id = ?", (account_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account_id}")
        await self.conn.execute(
            "DELETE FROM connector_accounts WHERE id = ?", (account_id,)
        )
        await self.conn.commit()

    def _row_to_model(self, row: aiosqlite.Row) -> ConnectorAccount:
        return ConnectorAccount(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            config=json.loads(row["config"] or "{}"),
            secrets=self._ciphertext_to_secrets(row["secrets"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
```

Imports needed at the top of `repositories.py`:
- Add `ConnectorAccount` to the existing `from the_one.db.models import ...` line. (`Encryptor`, `InvalidToken`, `_now_iso`, `aiosqlite`, `json` are already imported for MCP — verify by reading the import block.)

### Step 4: Migration tests in `tests/test_db_migration.py`

Add `TestSchemaV14` class at the end of the file, after `TestMigrationV12` (which `TestSchemaV13` should now precede — confirm class ordering before adding):

```python
class TestSchemaV14:
    """Tests for the v14 migration that adds connector_accounts.name."""

    async def test_v14_fresh_db_includes_name_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v14 surfaces exist."""
        import aiosqlite
        db_path = tmp_path / "v14-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 14, CURRENT_VERSION

        async with conn.execute("PRAGMA table_info(connector_accounts)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert "name" in cols, "v14 migration missing: connector_accounts.name not created"
        name_col = cols["name"]
        assert name_col["type"] == "TEXT", name_col["type"]
        assert name_col["notnull"] == 1, name_col["notnull"]
        assert name_col["dflt_value"] == "''", name_col["dflt_value"]

        async with conn.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ) as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 14 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v14_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Re-running ensure_schema against a v14 DB is a no-op."""
        import aiosqlite
        db_path = tmp_path / "v14-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second run is the test

        async with conn.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ) as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(14) == 1, f"v14 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v14_preserves_v13_seeded_row_with_empty_name(self, tmp_path) -> None:
        """A row seeded against a hand-built v13 schema (no `name` column)
        survives the v14 ALTER with name=''.

        Bootstraps a real v13-shape `connector_accounts` table (NO `name`
        column) so the v14 ALTER actually runs against a row that pre-exists
        without the column. Modeled on TestMigrationV12.test_v12_real_v11_to_v12_upgrade
        at tests/test_db_migration.py around line 923 (read that test for
        the bootstrap pattern: hand-build the pre-migration schema, INSERT
        rows, set schema_version, then call ensure_schema).
        """
        import aiosqlite
        db_path = tmp_path / "v14-from-real-v13.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build the v13 schema for `connector_accounts` (no `name`
        # column). Also build the `schema_version` table — ensure_schema's
        # v1 block creates it, but we want full control over the starting
        # state.
        await conn.execute("""
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")
        # Seed schema_version with versions 1..13 so the migration loop
        # MAX() head pointer is 13 and the v14 block enters cleanly.
        # Use a tuple expansion to keep the test readable.
        for v in range(1, 14):
            await conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (v,)
            )
        # Build the v13-shape connector_accounts (no `name` column).
        await conn.execute("""
CREATE TABLE connector_accounts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    config TEXT DEFAULT '{}',
    secrets TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")
        # Seed a row against the v13 shape (no name).
        await conn.execute(
            "INSERT INTO connector_accounts (id, type, config, secrets)"
            " VALUES (?, ?, ?, ?)",
            ("seeded", "stub", "{}", "{}"),
        )
        await conn.commit()

        # Now run ensure_schema — this should hit the v14 block, run the
        # ALTER (the PRAGMA check sees no `name` column), populate the
        # seeded row's `name` with the DEFAULT '', and bump schema_version
        # to 14.
        await ensure_schema(conn)

        # Verify the row survived with empty name.
        async with conn.execute(
            "SELECT id, name, type FROM connector_accounts WHERE id = 'seeded'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["name"] == "", f"expected empty name from DEFAULT '', got {row['name']!r}"
        assert row["type"] == "stub"

        # Verify head pointer landed at 14.
        async with conn.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ) as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 14 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()
```

**Note**: this test bootstraps a hand-built v13 schema rather than relying on `ensure_schema` to walk through versions. Before implementing, read `TestMigrationV12.test_v12_real_v11_to_v12_upgrade` (search for `def test_v12_real_v11_to_v12_upgrade` in `tests/test_db_migration.py`) for the canonical pattern. The other v13 schema tables (LLM providers, agents, MCP sources, etc.) are NOT bootstrapped here — they're not exercised by the v14 ALTER, which only touches `connector_accounts`. If the v14 migration has any cross-table dependencies (it doesn't, but verify), the bootstrap may need to be widened.

### Step 5: Repository fixtures + tests in `tests/test_db_repositories.py`

**Imports** — add `ConnectorAccount` and `ConnectorAccountRepository` to the existing imports at the top of the file.

**Fixtures** — add directly after the `mcp_repo` fixture at line 65:

```python
@pytest.fixture
def connector_repo_encryptor(tmp_path):
    # Function-scoped (default). Do NOT promote to module/session scope —
    # would outlive the per-test `conn` fixture and create cross-test
    # state leakage on the encryptor's in-memory key.
    from cryptography.fernet import Fernet

    from the_one.encryption import Encryptor

    key = Fernet.generate_key()
    return Encryptor(key, key_path=tmp_path / "connector.key")


@pytest.fixture
def connector_repo(conn, connector_repo_encryptor):
    return ConnectorAccountRepository(conn, connector_repo_encryptor)
```

**Test class** — add after `TestMCPSourceRepository` at line 260. Mirror the 8 tests (skipping merged_config):

```python
class TestConnectorAccountRepository:
    async def test_create_and_get(self, connector_repo) -> None:
        account = ConnectorAccount(
            id="a1", name="Test Bot", type="stub", config={"intent": "guild_messages"}
        )
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.name == "Test Bot"
        assert loaded.config == {"intent": "guild_messages"}

    async def test_list(self, connector_repo) -> None:
        await connector_repo.create(
            ConnectorAccount(id="b", name="Bravo Bot", type="stub")
        )
        await connector_repo.create(
            ConnectorAccount(id="a", name="Alpha Bot", type="stub")
        )
        accounts = await connector_repo.list()
        assert [a.name for a in accounts] == ["Alpha Bot", "Bravo Bot"]

    async def test_update(self, connector_repo) -> None:
        await connector_repo.create(
            ConnectorAccount(id="a1", name="Old Name", type="stub")
        )
        account = await connector_repo.get("a1")
        account.name = "New Name"
        await connector_repo.update(account)
        loaded = await connector_repo.get("a1")
        assert loaded.name == "New Name"

    async def test_delete(self, connector_repo) -> None:
        await connector_repo.create(
            ConnectorAccount(id="a1", name="Doomed", type="stub")
        )
        await connector_repo.delete("a1")
        with pytest.raises(KeyError):
            await connector_repo.get("a1")

    async def test_secrets_round_trip(self, connector_repo) -> None:
        account = ConnectorAccount(
            id="a1",
            name="Discord Bot",
            type="stub",
            config={"intent": "guild_messages"},
            secrets={"BOT_TOKEN": "discord_secret_value_xyz"},
        )
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.config == {"intent": "guild_messages"}
        assert fetched.secrets == {"BOT_TOKEN": "discord_secret_value_xyz"}

    async def test_secrets_encrypted_at_rest(self, connector_repo) -> None:
        import json

        account = ConnectorAccount(
            id="a1",
            name="Test",
            type="stub",
            secrets={"TOKEN": "super-secret-value"},
        )
        await connector_repo.create(account)
        async with connector_repo.conn.execute(
            "SELECT secrets FROM connector_accounts WHERE id = ?", ("a1",)
        ) as cur:
            row = await cur.fetchone()
        raw = row["secrets"]
        assert raw is not None
        assert "super-secret-value" not in raw
        assert "TOKEN" not in raw
        decrypted = connector_repo.encryptor.decrypt(raw)
        assert json.loads(decrypted) == {"TOKEN": "super-secret-value"}

    async def test_empty_secrets_default(self, connector_repo) -> None:
        account = ConnectorAccount(id="a1", name="Test", type="stub", config={"x": 1})
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.secrets == {}

    async def test_install_key_post_create_decrypts_via_same_instance(
        self, connector_repo
    ) -> None:
        from cryptography.fernet import Fernet

        new_key = Fernet.generate_key()
        connector_repo.encryptor.install_key(new_key)

        account = ConnectorAccount(
            id="a1",
            name="PostKey",
            type="stub",
            secrets={"K": "value-after-rotation"},
        )
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.secrets == {"K": "value-after-rotation"}
```

### Step 6: Verify leg 1's rotation tests still pass

The leg 1 rotation tests at `tests/test_provider_api.py:TestEncryptionRotation::test_rotate_connector_account_secrets` and `test_rotate_preserves_connector_secrets_on_db_failure` seed connector_accounts directly via SQL with `(id, type, config, secrets)`. After v14, this INSERT will succeed because `name` has `DEFAULT ''`. **Run the tests to confirm**:

```
docker exec the-one pytest -x --timeout 30 tests/test_provider_api.py::TestEncryptionRotation -k connector
```

If they fail (e.g. because SQLite raises on the missing-NOT-NULL-without-DEFAULT path), update the INSERT to explicitly include `name`. The implementing agent should not pre-emptively change the leg 1 tests — only if the v14 migration's `DEFAULT ''` doesn't make them work.

### Step 7: Update flight spec — renumber Flight 8's CHECK migration v14 → v15

In `the_one/missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md`, find every reference to "v14 in Flight 8" or similar and update to "v15 in Flight 8". Specifically the Design Decisions block titled "Schema version increments from 12 to 13; no CHECK constraint on `type` in v13" — its sentence "The first real connector (Flight 8 — Discord) adds `'discord'` to the tuple AND lands a v14 migration that introduces the CHECK constraint via table-rename ceremony when there's an actual type to constrain." becomes "…lands a v15 migration that introduces the CHECK constraint…" (v14 is now claimed by leg 2's name-column migration).

Also check Flight 8's Legs entry in the flight artifact — if it mentions a specific version, update.

### Step 8: Update flight log

Add a new section `## Design Adjustments` to the flight log (after the existing `## Reconnaissance Report` and before `## Leg Progress`). Capture:

```markdown
## Design Adjustments

Adjustments to the flight spec discovered during leg planning/execution. Each
entry names the leg that surfaced the adjustment, what changed, and why.

### Leg 02 — `name` column on `connector_accounts` (v14 migration; Flight 8's CHECK migration renumbers to v15)

The flight spec calls for `ConnectorAccount` to "mirror MCPSource shape" but
the v13 schema (leg 1) omitted the `name` column that MCPSource has as a
first-class operator-visible identifier. Leg 2 added v14: `ALTER TABLE
connector_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''`.

Downstream impact: Flight 8 (Discord) was planned to land v14 (CHECK
constraint via table-rename). That migration now becomes v15. Flight spec
text updated accordingly.

Rationale: MCPSource has `name`; Flight 2's admin UI needs to identify
multiple Discord bots / Slack accounts visually; storing display name in
`config.name` (the alternative) would diverge from the MCP pattern this
flight intentionally mirrors.
```

Add the `### Leg 02: models-and-repository` entry under `## Leg Progress` with the standard shape.

### Step 9: Run targeted tests + full suite + lint

```bash
docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py::TestSchemaV14 tests/test_db_repositories.py::TestConnectorAccountRepository tests/test_provider_api.py::TestEncryptionRotation -k connector
docker exec the-one pytest -x --timeout 30
docker exec the-one bash -c "cd /workspace && make lint"
```

### Step 10: Update leg status + flight checkboxes

- Set this leg's status frontmatter to `landed`
- Check off `models-and-repository` in `flight.md`'s Legs section
- Signal `[HANDOFF:review-needed]`; do NOT commit

## Edge Cases

- **v13-seeded rows with no name column.** In practice zero rows (table was empty at v13). The ALTER's `DEFAULT ''` handles any edge case. Verified by `test_v14_preserves_v13_seeded_row_with_empty_name`.
- **Pydantic ConnectorAccount with empty string name.** Empty string is a valid `str`. Pydantic accepts. Display-layer logic in Flight 2 may want to fall back to `id` when `name == ""`, but that's Flight 2's concern.
- **Test ordering — `TestSchemaV12` after `TestSchemaV13`.** The existing file has `TestSchemaV11` followed by other classes; leg 1's `TestSchemaV13` was added at the bottom. The implementing agent should add `TestSchemaV14` at the end (after `TestSchemaV13`) so order matches schema version. Cosmetic but consistent.
- **Encryption envelope on `update()`.** Repository's `update()` always re-encrypts the secrets dict — even if the values are unchanged. This is correct (Fernet ciphertext is non-deterministic; each encryption produces a different ciphertext). No optimization needed.
- **`JSONDecodeError` in `_ciphertext_to_secrets`.** Propagates per the MCP pattern. Real corruption surfaces as a 500; not silently masked.
- **`merged_config()` callers.** No code in the codebase calls `MCPSource.merged_config()` for connector accounts (there is no such code yet). Skipping the helper has zero impact in this leg.
- **`AgentConfig.connector_account_ids` field.** Not added in this leg. Flight 4 adds it when the platform-send tool needs to read attached accounts.

## Files Affected

- `the_one/db/schema.py` — `CURRENT_VERSION` 13→14; new `if version < 14:` block
- `the_one/db/models.py` — new `ConnectorAccount` Pydantic model after `MCPSource`
- `the_one/db/repositories.py` — new `ConnectorAccountRepository` after `MCPSourceRepository`; import `ConnectorAccount`
- `tests/test_db_migration.py` — new `TestSchemaV14` class
- `tests/test_db_repositories.py` — imports updated; `connector_repo_encryptor` + `connector_repo` fixtures; new `TestConnectorAccountRepository` class
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — Design Decisions block renumber v14→v15 for Flight 8 CHECK
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — new `## Design Adjustments` section; `### Leg 02` entry under `## Leg Progress`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/02-models-and-repository.md` (this file) — status to `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All listed tests passing (`docker exec the-one pytest -x --timeout 30`)
- [ ] `make lint` clean
- [ ] Flight spec updated for v14→v15 renumbering of Flight 8's CHECK migration
- [ ] Flight log updated with `## Design Adjustments` section + `### Leg 02` entry
- [ ] Leg status set to `landed` (NOT `completed`)
- [ ] `models-and-repository` checkbox checked in flight.md
- [ ] Signal `[HANDOFF:review-needed]`
- [ ] Do NOT commit — defer to flight-end

---

## Citation Audit

7 citations verified against current code at leg design time:

| Citation | Verification |
|---|---|
| `the_one/db/models.py:MCPSource` (lines 86-107) | OK — verified |
| `the_one/db/models.py:LLMProviderConfig._normalize_api_key` (lines 32-53) | OK — `__MASKED__` is an API-layer concern, confirmed |
| `the_one/db/models.py:59-61` literal-pinning assert | OK — pattern to mirror in Flight 8, not this leg |
| `the_one/db/repositories.py:MCPSourceRepository` (lines 291-425) | OK — read in full |
| `the_one/db/schema.py:11 CURRENT_VERSION = 13` (post-leg-1) | OK — verified |
| `the_one/db/schema.py:412-430` v11 ALTER pattern | OK — structural template |
| `tests/test_db_repositories.py:51-65` MCP fixtures | OK — verified |
| `tests/test_db_repositories.py:260 TestMCPSourceRepository` | OK — 9 tests, will mirror 8 (skipping merged_config) |
