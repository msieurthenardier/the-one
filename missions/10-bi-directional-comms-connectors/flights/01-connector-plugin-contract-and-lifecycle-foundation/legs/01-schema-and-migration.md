# Leg: schema-and-migration

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Land the v13 schema migration that creates the `connector_accounts` table, the canonical `_connector_types.py` literal-source-of-truth module, and the extension to the encryption-rotation transaction so `connector_accounts.secrets` is re-encrypted atomically with LLM-provider `api_key` and MCP-source `secrets` in a single commit.

## Context

This is the foundation leg of Flight 1 of Mission 10 (bi-directional communication connectors). The flight ships the connectors SDK; this leg is the persistence-layer floor every subsequent leg of the flight (and every subsequent flight of the mission) stands on.

**Key design decisions from the flight that bind this leg**:

- **No CHECK constraint on `connector_accounts.type` in v13.** Mirrors the `_provider_types.py` pattern: the single source of truth is the `CONNECTOR_TYPES` tuple (empty in this leg) pinned to the (future, in `models-and-repository` leg) Pydantic `Literal[...]` on `ConnectorAccount.type` via an `assert set(get_args(...)) == set(CONNECTOR_TYPES)` invariant. Flight 8 (Discord) lands the v14 table-rename ceremony that adds CHECK when there is a real type to constrain.
- **Migration uses individual `await conn.execute(...)` calls, NOT `executescript`.** The v8/v9/v10/v11 idempotency contract: `INSERT OR IGNORE INTO schema_version` LAST so a partial-apply leaves `version=12` and the next call retries cleanly. v12's `executescript` is the exception (required to keep `PRAGMA foreign_keys=OFF` in scope across DROP/RENAME); v13 has no FK concerns and follows the v10/v11 idiom.
- **Rotation transaction stays single-commit.** A failure in any UPDATE loop rolls back all three corpora (LLM api_key, MCP secrets, connector secrets) atomically. Mirrors `rotate_encryption_key` at `interfaces/web/api.py:rotate_encryption_key` — extend, don't fork.
- **Tolerant decrypt mirrors the MCP path.** `InvalidToken` → empty `{}` dict (handles plaintext `'{}'` column defaults that may exist if a future migration adds the column to pre-existing rows; not strictly needed for v13 since the table is brand new, but mirroring keeps the rotation transaction symmetric and resilient to future column-default migration patterns). JSON decode errors are NOT swallowed — they indicate real corruption.

## Inputs

What exists before this leg runs:

- `main` branch is at `cf17f40` (Flight 1 spec landed)
- Feature branch is `flight/01-connector-plugin-contract-and-lifecycle-foundation` (Flight Director created it; this leg works on it)
- Schema head pointer is `CURRENT_VERSION = 12` at `the_one/db/schema.py:11`
- `_provider_types.py` exists at `the_one/db/_provider_types.py` with the canonical pattern this leg mirrors: docstring explaining three-layer agreement, `PROVIDER_TYPES: tuple[str, ...]` constant, `from __future__ import annotations`
- v10 migration block at `the_one/db/schema.py:363-410` is the structural template for table-creation legs (individual `await conn.execute(...)` calls; `INSERT OR IGNORE INTO schema_version` LAST; defensive `DROP TABLE IF EXISTS ..._new` if a rename ceremony is needed — but v13 creates a fresh table, no rename needed)
- v11 migration block at `the_one/db/schema.py:412-430` is the structural template for the `INSERT OR IGNORE` idempotency tail
- Rotation transaction at `the_one/interfaces/web/api.py:rotate_encryption_key` (lines 2744-2853) is the extension target — read it in full before modifying
- Test patterns:
  - Migration tests in `tests/test_db_migration.py` (class `TestV11Migration` at `tests/test_db_migration.py:757` is the structural template — fresh-DB-fresh-migrations test + rewind-and-rerun test)
  - Rotation tests in `tests/test_provider_api.py` (`test_rotate_mcp_source_secrets` at `tests/test_provider_api.py:612`, `test_rotate_preserves_mcp_secrets_on_db_failure` at `tests/test_provider_api.py:669`, `test_rotate_preserves_key_on_db_failure` at `tests/test_provider_api.py:548` are the structural templates)

## Outputs

What exists after this leg completes:

- New file `the_one/db/_connector_types.py` with empty `CONNECTOR_TYPES: tuple[str, ...] = ()` and a docstring explaining the three-layer-agreement role (Pydantic `Literal`, future SQLite CHECK in v14, future registry dispatch in flight 1 leg 4)
- `the_one/db/schema.py:CURRENT_VERSION` increments to 13
- New `if version < 13:` migration block in `ensure_schema` creating the `connector_accounts` table — id TEXT PK, type TEXT NOT NULL (NO CHECK), config TEXT DEFAULT `'{}'`, secrets TEXT DEFAULT `'{}'`, created_at TEXT NOT NULL DEFAULT `(datetime('now'))`, updated_at TEXT NOT NULL DEFAULT `(datetime('now'))`. Follows v10/v11 idempotency contract (individual `await conn.execute(...)`; `INSERT OR IGNORE INTO schema_version` LAST).
- `the_one/interfaces/web/api.py:rotate_encryption_key` extended to (a) SELECT existing connector secrets after the MCP SELECT, (b) tolerantly decrypt mirroring the MCP path, (c) re-encrypt with the new in-memory encryptor, (d) UPDATE `connector_accounts SET secrets = ?` inside the existing try/commit/except/rollback block so all three corpora commit atomically
- Docstring at `rotate_encryption_key` updated to mention three corpora (LLM api_key + MCP secrets + connector_accounts secrets) rather than two
- New test class `TestV13Migration` in `tests/test_db_migration.py` covering: (a) fresh DB + ensure_schema → v13 surfaces exist; (b) v12 → v13 idempotent rerun; (c) connector_accounts table has expected columns and NO CHECK constraint on `type`
- New tests in `tests/test_provider_api.py` (or a new `tests/test_connector_api.py` if the reviewer prefers separation — see Edge Cases): `test_rotate_connector_account_secrets` (positive path), `test_rotate_preserves_connector_secrets_on_db_failure` (rollback verification across all three corpora)
- All tests pass; `make test` and `make lint` clean
- Leg status `landed` (NOT `completed` — the agentic-workflow batch reviewer at flight end transitions to `completed`)
- Flight log updated with leg-progress entry

## Acceptance Criteria

- [ ] `the_one/db/_connector_types.py` exists, exports `CONNECTOR_TYPES: tuple[str, ...] = ()`, uses `from __future__ import annotations`, has a docstring explaining the three-layer agreement role
- [ ] `the_one/db/schema.py:CURRENT_VERSION` is `13`
- [ ] A new `if version < 13:` migration block exists in `ensure_schema` between the existing v12 block and the function return; it uses individual `await conn.execute(...)` calls (no `executescript`); `INSERT OR IGNORE INTO schema_version (version) VALUES (?)` with `(13,)` is the LAST statement before `await conn.commit()` and the `version = 13` reassignment
- [ ] The v13 migration creates `connector_accounts` with columns: `id TEXT PRIMARY KEY`, `type TEXT NOT NULL` (NO CHECK constraint), `config TEXT DEFAULT '{}'`, `secrets TEXT DEFAULT '{}'`, `created_at TEXT NOT NULL DEFAULT (datetime('now'))`, `updated_at TEXT NOT NULL DEFAULT (datetime('now'))`
- [ ] A fresh DB run of `ensure_schema` lands at `schema_version` head = 13 and includes a `connector_accounts` row in `sqlite_master` with the expected column shape
- [ ] A re-run of `ensure_schema` against a DB already at v13 is a no-op (idempotent — `INSERT OR IGNORE` swallows the duplicate-PK on `schema_version`, and the `CREATE TABLE IF NOT EXISTS` clause swallows the duplicate table)
- [ ] `rotate_encryption_key` at `the_one/interfaces/web/api.py` now decrypts existing connector secrets after the MCP SELECT, re-encrypts them with the new in-memory encryptor, and UPDATEs `connector_accounts SET secrets = ?` inside the same try/commit/except/rollback block; tolerant-decrypt of `InvalidToken` → `{}` mirrors the MCP path; JSON decode errors are NOT swallowed
- [ ] The single `await conn.commit()` covers all three UPDATE loops; a deliberate failure in any of the three rolls back the other two
- [ ] `rotate_encryption_key`'s docstring is updated to mention three corpora (was two)
- [ ] New tests in `tests/test_db_migration.py` (in a new class `TestSchemaV13` modeled on `TestSchemaV11`): `test_v13_fresh_db_includes_connector_accounts_table`, `test_v13_migration_idempotent_on_rerun`, `test_v13_connector_accounts_has_expected_columns_and_no_check_constraint`
- [ ] New tests in `tests/test_provider_api.py` (preferred — same module as MCP rotation tests for symmetry): `test_rotate_connector_account_secrets`, `test_rotate_preserves_connector_secrets_on_db_failure`
- [ ] All existing tests still pass (no regression on LLM-provider or MCP-source rotation paths)
- [ ] `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py tests/test_provider_api.py tests/test_encryption.py tests/test_schema.py` is clean
- [ ] `make test` and `make lint` are clean for the whole suite
- [ ] Leg status is `landed`
- [ ] Flight log has a `### Leg 01: schema-and-migration` entry with status, changes, and notes

## Verification Steps

For each criterion, here is the command or check that confirms it:

1. **`_connector_types.py` exists and has the expected shape**:
   - `docker exec the-one cat the_one/db/_connector_types.py` (or read locally) — verify the docstring, the `from __future__ import annotations`, and `CONNECTOR_TYPES: tuple[str, ...] = ()`
   - `docker exec the-one python -c "from the_one.db._connector_types import CONNECTOR_TYPES; assert CONNECTOR_TYPES == (); print('ok')"`

2. **Schema head pointer is 13**:
   - `docker exec the-one python -c "from the_one.db.schema import CURRENT_VERSION; assert CURRENT_VERSION == 13; print('ok')"`

3. **v13 migration block exists with correct shape**:
   - `grep -n "if version < 13:" the_one/db/schema.py` — must return one match
   - `grep -n "INSERT OR IGNORE INTO schema_version (version) VALUES (?), (13," the_one/db/schema.py` — verify the LAST-statement pattern (the actual grep is on the literal substring; adjust for the exact whitespace formatting in the file)
   - `grep -c "await conn.executescript" the_one/db/schema.py` — must not have increased since v12 (i.e., v13 does NOT introduce a new `executescript`)

4. **Fresh DB lands at v13 with `connector_accounts` table**:
   - The new migration test `test_v13_fresh_db_includes_connector_accounts_table` is the canonical verifier

5. **Rotation transaction extension**:
   - Reading `rotate_encryption_key` shows: SELECT loop for `connector_accounts` after the MCP SELECT; tolerant-decrypt pattern duplicating the MCP path; UPDATE loop for `connector_accounts` inside the same try block; single `await conn.commit()` covering all three
   - The new test `test_rotate_connector_account_secrets` is the positive-path verifier
   - The new test `test_rotate_preserves_connector_secrets_on_db_failure` is the rollback-atomicity verifier

6. **No regression**:
   - `docker exec the-one pytest -x --timeout 30` on the full suite is green

## Implementation Guidance

Execute in this order. Each step is independently verifiable; do not advance to the next until the previous compiles and passes its smoke check.

### Step 1: Create `the_one/db/_connector_types.py`

Mirror `the_one/db/_provider_types.py` byte-for-byte in structure (just different content). The docstring should explain:

- Single source of truth for the connector type enum
- Three layers must agree on the valid values:
  - The Pydantic `Literal` annotation on `ConnectorAccount.type` (compile-time type checking, JSON-schema generation, request validation at the API edge) — landed in the `models-and-repository` leg of this flight
  - The SQLite CHECK constraint string baked into the `connector_accounts` table — **deferred to Flight 8 (Discord)** which adds the CHECK via a v14 table-rename ceremony when there is a real type to constrain. Until then, `connector_accounts.type` is unconstrained at the DB level; the Pydantic `Literal` is the only guard at the API edge
  - The connector-type → registry-class map in `the_one/connectors/registry.py` (runtime dispatch from a stored account config to a `ConnectorPlugin`) — landed in the `registry` leg of this flight

The body is a single `CONNECTOR_TYPES: tuple[str, ...] = ()` — empty in Flight 1, grown as real connectors land.

```python
"""Single source of truth for the connector type enum.

Mirrors the_one/db/_provider_types.py exactly in role: three layers must
agree on the valid values, and the tuple below is the canonical list each
re-derives its representation from.

- The Pydantic ``Literal`` annotation on ``ConnectorAccount.type`` (compile-time
  type checking, JSON-schema generation, request validation at the API edge)
  — landed in the models-and-repository leg of flight 1.
- The SQLite CHECK constraint string baked into the ``connector_accounts``
  table (runtime DB-level rejection of bogus rows) — **deferred to flight 8**
  which adds the CHECK via a v14 table-rename ceremony when there is a real
  type to constrain. Until then ``connector_accounts.type`` is unconstrained
  at the DB level; the Pydantic ``Literal`` is the sole guard at the API edge.
- The connector-type → registry-class map in ``the_one/connectors/registry.py``
  (runtime dispatch from a stored account config to a ConnectorPlugin) —
  landed in the registry leg of flight 1.

The consistency tests pin the three layers to this tuple — currently a no-op
because the tuple is empty.
"""

from __future__ import annotations

CONNECTOR_TYPES: tuple[str, ...] = ()
```

### Step 2: Bump `CURRENT_VERSION` and add the v13 migration block to `the_one/db/schema.py`

Increment the `CURRENT_VERSION` constant at the top of `schema.py:11` from 12 to 13.

Add the v13 migration block immediately after the v12 block (which ends at `the_one/db/schema.py:477` — the current last line of `ensure_schema`). Place it as the last block in `ensure_schema` (the function has no explicit `return` — the v12 block's `version = 12` is currently the final statement). The block follows the v10/v11 pattern of individual `await conn.execute(...)` calls with the `INSERT OR IGNORE INTO schema_version` LAST.

```python
    if version < 13:
        # Add connector_accounts table (mission 10 flight 01) for
        # bi-directional communication connector identities (Discord bot,
        # Slack workspace app, etc.). Sibling to mcp_sources at the
        # persistence-layer level.
        #
        # No CHECK constraint on `type` in v13 (in contrast to mcp_sources
        # which had `CHECK (type IN ('stdio', 'streamable-http'))` from v3).
        # The Pydantic Literal on ConnectorAccount.type is the sole guard
        # at the API edge; flight 8 (Discord) will land v14 with the
        # table-rename ceremony to add the CHECK once 'discord' is a real
        # type to constrain. The _connector_types.py tuple is the canonical
        # source of truth — empty in v13, grown by future flights.
        #
        # Idempotency follows the v10/v11 contract: individual
        # `await conn.execute(...)` calls (NOT executescript), CREATE TABLE
        # IF NOT EXISTS makes the table creation a no-op on rerun, and the
        # `INSERT OR IGNORE INTO schema_version` is LAST so a partial-apply
        # leaves version=12 and the next call retries cleanly.
        await conn.execute("""\
CREATE TABLE IF NOT EXISTS connector_accounts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    config TEXT DEFAULT '{}',
    secrets TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (13,))
        await conn.commit()
        version = 13
```

Smoke check after this step: `docker exec the-one python -c "from the_one.db.schema import CURRENT_VERSION; print(CURRENT_VERSION)"` returns `13`.

### Step 3: Extend the rotation transaction at `the_one/interfaces/web/api.py:rotate_encryption_key`

Read the existing rotation function in full (lines 2744-2853) before modifying. The structure is: SELECT decrypted rows → generate new encryptor in memory → re-encrypt → single try/commit/except/rollback block with all UPDATE loops → key-file persistence dance.

Modify three places:

**(a) Docstring (lines 2745-2760).** Update the summary line and the body to mention three corpora instead of two. Example:

```python
    """Rotate the encryption key with crash-safe ordering.

    Re-encrypts every LLM provider row's ``api_key``, every MCP source row's
    ``secrets`` blob, AND every connector account row's ``secrets`` blob using
    a freshly generated key in memory and commits the DB transaction *before*
    the new key file replaces the old one via temp-file + ``os.replace``. All
    three surfaces commit atomically — a partial rotation that handled only
    a subset would leave the others encrypted under a key that no longer
    exists on disk. If the DB commit fails, the on-disk key file is left
    byte-identical to its pre-rotation contents so existing ciphertext on
    all three surfaces remains decryptable.

    Migration-residue MCP and connector rows (plaintext ``'{}'`` carried over
    from the column default) are tolerated via InvalidToken-swallowing decrypt;
    they are normalized to proper ciphertext for ``{}`` as a side-effect.
    """
```

**(b) Add the connector SELECT + tolerant decrypt loop** after the MCP block at line 2799 and before the `# 2. Generate a new key` comment at line 2801:

```python
    async with conn.execute("SELECT id, secrets FROM connector_accounts") as cur:
        connector_rows = await cur.fetchall()

    # Tolerant decrypt mirrors the MCP path above. Pre-rotation connector
    # rows created through ConnectorAccountRepository will already be
    # encrypted; tolerant decrypt only matters if a future migration adds
    # the column to pre-existing rows with the plaintext '{}' default.
    decrypted_connectors: list[tuple[str, dict[str, Any]]] = []
    for row in connector_rows:
        ciphertext = row["secrets"]
        if not ciphertext:
            secrets_dict: dict[str, Any] = {}
        else:
            try:
                plaintext = encryptor.decrypt(ciphertext)
                secrets_dict = json.loads(plaintext)
            except InvalidToken:
                secrets_dict = {}
        decrypted_connectors.append((row["id"], secrets_dict))
```

**(c) Add the connector re-encrypt + UPDATE loop**, mirroring the MCP path:

Re-encrypt (after line 2810, alongside `reencrypted_mcps`):

```python
    reencrypted_connectors = [
        (aid, new_encryptor.encrypt(json.dumps(secrets_dict)))
        for aid, secrets_dict in decrypted_connectors
    ]
```

UPDATE loop (inside the existing `try:` block, after the `for sid, ct in reencrypted_mcps:` loop at line 2825-2829):

```python
        for aid, ct in reencrypted_connectors:
            await conn.execute(
                "UPDATE connector_accounts SET secrets = ? WHERE id = ?",
                (ct, aid),
            )
```

The single `await conn.commit()` already in the function covers all three; the `except: await conn.rollback(); raise` already rolls back atomically across all UPDATE loops. No structural change to the try/except/rollback block — only added a third UPDATE loop inside it.

### Step 4: Migration tests in `tests/test_db_migration.py`

Add a new test class `TestSchemaV13` modeled on `TestSchemaV11` at `tests/test_db_migration.py:756` (note the actual existing class names are `TestSchemaV7`, `TestSchemaV8`, ..., `TestSchemaV11` — the previous review caught that this leg incorrectly referred to them as `TestVxxMigration`). Three tests minimum:

```python
class TestSchemaV13:
    """Tests for the v13 migration that adds the connector_accounts table."""

    async def test_v13_fresh_db_includes_connector_accounts_table(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v13 surfaces exist."""
        db_path = tmp_path / "v13-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 13, CURRENT_VERSION

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connector_accounts'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, "v13 migration missing: connector_accounts table not created"

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 13 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v13_connector_accounts_has_expected_columns_and_no_check_constraint(
        self, tmp_path
    ) -> None:
        """connector_accounts has the expected columns; type column is NOT NULL but unconstrained."""
        db_path = tmp_path / "v13-cols.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(connector_accounts)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert set(cols) == {"id", "type", "config", "secrets", "created_at", "updated_at"}, cols

        assert cols["id"]["type"] == "TEXT" and cols["id"]["pk"] == 1
        assert cols["type"]["type"] == "TEXT" and cols["type"]["notnull"] == 1
        assert cols["config"]["type"] == "TEXT" and cols["config"]["dflt_value"] == "'{}'"
        assert cols["secrets"]["type"] == "TEXT" and cols["secrets"]["dflt_value"] == "'{}'"

        # No CHECK constraint on type — verify by inserting a bogus type and
        # asserting it does NOT raise (would raise IntegrityError if there
        # were a CHECK).
        await conn.execute(
            "INSERT INTO connector_accounts (id, type) VALUES (?, ?)",
            ("test-id", "bogus-type-that-flight-8-will-constrain"),
        )
        await conn.commit()

        async with conn.execute(
            "SELECT type FROM connector_accounts WHERE id = 'test-id'"
        ) as cur:
            row = await cur.fetchone()
        assert row["type"] == "bogus-type-that-flight-8-will-constrain"

        await conn.close()

    async def test_v13_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Re-running ensure_schema against a v13 DB is a no-op."""
        db_path = tmp_path / "v13-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second run is the test

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(13) == 1, f"v13 row should appear exactly once: {versions}"

        await conn.close()
```

Imports needed at the top of `test_db_migration.py` if missing: confirm `CURRENT_VERSION`, `ensure_schema`, `aiosqlite` are already imported (they are — see existing test classes).

### Step 5: Rotation tests in `tests/test_provider_api.py`

The existing rotation tests use `unittest.mock.patch("aiosqlite.Connection.commit", side_effect=RuntimeError(...))` to inject the failure at the commit boundary — that is the canonical pattern this leg's tests MUST mirror. The previous review caught a draft of this leg using `monkeypatch.setattr(conn, "execute", ...)` which would not have exercised the rollback path because the rotation handler gets its own connection via `get_connection()` and the test-scope `conn` is not the same object.

Read `tests/test_provider_api.py:test_rotate_preserves_mcp_secrets_on_db_failure` at line 669 and `tests/test_provider_api.py:test_rotate_preserves_key_on_db_failure` at line 548 in full first. Mirror their structure exactly — same imports (`from unittest.mock import patch` if not already imported), same seeding pattern (raw SQL via `aiosqlite.connect(str(tmp_path / "test.db"))`, since Flight 1 ships no REST routes for connector_accounts and the existing MCP tests at lines 600/697/727 already use this idiom), same assertion pattern (open a fresh connection post-failure, read each corpus's ciphertext, assert byte-identical to pre-rotation).

```python
async def test_rotate_connector_account_secrets(self, client: AsyncClient) -> None:
    """Rotation re-encrypts connector_accounts.secrets atomically with
    llm_providers.api_key and mcp_sources.secrets in the same single commit.

    Mirrors test_rotate_mcp_source_secrets at line 612. Seeds via raw SQL
    because Flight 1 ships no REST routes for connector_accounts — those
    land in Flight 2.
    """
    # Seed a connector account directly via SQL. Use the same seeding
    # pattern as test_rotate_mcp_source_secrets — open a fresh connection,
    # encrypt secrets in-process, INSERT, close. The required imports
    # (get_connection, get_encryptor, settings, json) must be present
    # in the file; if any is missing, add it alongside the existing imports.
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    secrets_plain = {"BOT_TOKEN": "test-token-12345"}
    ciphertext = encryptor.encrypt(json.dumps(secrets_plain))
    await conn.execute(
        "INSERT INTO connector_accounts (id, type, config, secrets) VALUES (?, ?, ?, ?)",
        ("test-account", "stub", "{}", ciphertext),
    )
    await conn.commit()

    response = await client.post("/api/encryption/rotate")
    assert response.status_code == 200

    # Verify secrets decrypt correctly with the rotated encryptor.
    rotated_encryptor = get_encryptor(settings.data_dir)
    async with conn.execute(
        "SELECT secrets FROM connector_accounts WHERE id = 'test-account'"
    ) as cur:
        row = await cur.fetchone()
    decrypted = json.loads(rotated_encryptor.decrypt(row["secrets"]))
    assert decrypted == secrets_plain


async def test_rotate_preserves_connector_secrets_on_db_failure(
    self, client: AsyncClient
) -> None:
    """A failure at the commit boundary rolls back all three corpora —
    llm_providers, mcp_sources, and connector_accounts — together.

    Mirrors test_rotate_preserves_mcp_secrets_on_db_failure at line 669
    exactly — `unittest.mock.patch("aiosqlite.Connection.commit",
    side_effect=RuntimeError(...))` is the canonical pattern. Patching at
    the commit boundary (not earlier UPDATE statements) is what exercises
    the full try/UPDATE-loops/commit/except/rollback contract — the
    monkeypatch-on-`conn.execute` approach explored in the leg-design
    review would not fire because the rotation handler gets its own
    connection via get_connection().
    """
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)

    # Seed one row in each of the three encrypted corpora.
    llm_ct_before = encryptor.encrypt("llm-secret-xyz")
    await conn.execute(
        "INSERT INTO llm_providers (id, name, type, base_url, api_key) VALUES (?, ?, ?, ?, ?)",
        ("llm-1", "test", "mock", "http://localhost", llm_ct_before),
    )
    mcp_ct_before = encryptor.encrypt(json.dumps({"AUTH": "mcp-secret"}))
    await conn.execute(
        "INSERT INTO mcp_sources (id, name, type, secrets) VALUES (?, ?, ?, ?)",
        ("mcp-1", "test-mcp", "stdio", mcp_ct_before),
    )
    conn_ct_before = encryptor.encrypt(json.dumps({"BOT_TOKEN": "connector-secret"}))
    await conn.execute(
        "INSERT INTO connector_accounts (id, type, config, secrets) VALUES (?, ?, ?, ?)",
        ("conn-1", "stub", "{}", conn_ct_before),
    )
    await conn.commit()

    # Inject failure at the commit boundary. This exercises the full
    # try/UPDATE-loops/commit/except/rollback contract — all three UPDATE
    # loops run, then commit raises, then the rollback in the except path
    # restores all three corpora atomically.
    with patch(
        "aiosqlite.Connection.commit",
        side_effect=RuntimeError("simulated commit failure"),
    ):
        response = await client.post("/api/encryption/rotate")
    # 500 propagates from the re-raise in the except path.
    assert response.status_code == 500

    # Re-open the DB connection to verify the rolled-back state. The
    # connection cache from get_connection() may still surface stale state
    # if reused (mirrors the comment at api.py:2814 about "uncommitted
    # ciphertext encrypted with the new (not-yet-on-disk) key"). Use a
    # fresh connection on the same DB to assert post-rollback state.
    async with conn.execute(
        "SELECT api_key FROM llm_providers WHERE id = 'llm-1'"
    ) as cur:
        assert (await cur.fetchone())["api_key"] == llm_ct_before
    async with conn.execute("SELECT secrets FROM mcp_sources WHERE id = 'mcp-1'") as cur:
        assert (await cur.fetchone())["secrets"] == mcp_ct_before
    async with conn.execute(
        "SELECT secrets FROM connector_accounts WHERE id = 'conn-1'"
    ) as cur:
        assert (await cur.fetchone())["secrets"] == conn_ct_before
```

**Critical**: do not skip reading `test_rotate_preserves_mcp_secrets_on_db_failure` in full before writing this — its exact import set, fixture signatures, and assertion sequencing are the contract this test must match. Diverging from the established pattern even in small ways (different assertion order, different fixture name, different way to open the verification connection) introduces drift and makes the test harder to maintain.

**Imports** that may be missing in `tests/test_provider_api.py` and need to be added if so:
- `from unittest.mock import patch`
- `import json`
- `from the_one.config import settings` (or however `settings.data_dir` is resolved by the existing rotation tests)
- `from the_one.db.connection import get_connection`
- `from the_one.encryption import get_encryptor`

Inspect the existing rotation tests at lines 612, 669, 548 to see which imports are already present; only add missing ones, do not duplicate.

### Step 6: Run the targeted tests, then the full suite

```bash
docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py::TestV13Migration tests/test_provider_api.py -k "rotate"
docker exec the-one pytest -x --timeout 30
docker exec the-one bash -c "cd /workspace && make lint"
```

If any test fails, isolate it; do not advance to the next step until each gate is clean.

### Step 7: Update the flight log and leg status

Append a new `### Leg 01: schema-and-migration` section to `flight-log.md` under `## Leg Progress` with the standard shape (Status, Started, Completed, Changes Made, Notes). Set leg status in this artifact's frontmatter from `planning` → `landed` (NOT `completed` — the flight-end batch reviewer transitions to `completed`).

Signal `[HANDOFF:review-needed]` when this leg is complete. Do NOT commit (the agentic-workflow defers commits to flight-end).

## Edge Cases

- **Existing developers running mid-flight against a partial-applied DB**. The `INSERT OR IGNORE INTO schema_version` tail makes the migration safe to re-run from any intermediate state. If a developer's local DB landed at v13 but the test runner uses a fresh tmp_path DB, both paths converge on the same final state.
- **A pre-existing `connector_accounts` table (impossible in practice)**. The `CREATE TABLE IF NOT EXISTS` clause makes this a no-op. If a developer somehow created the table by hand before this leg ran, the migration accepts the existing table; column drift would be surfaced by `test_v13_connector_accounts_has_expected_columns_and_no_check_constraint`.
- **An empty `connector_accounts` table during rotation**. The SELECT loop returns zero rows, `decrypted_connectors` is empty, `reencrypted_connectors` is empty, the UPDATE loop iterates zero times. Rotation completes successfully. Add a test case in `test_rotate_empty_table` (existing test at `tests/test_provider_api.py:519`) confirming connector_accounts is included in the no-rows path if that test asserts on table coverage; otherwise the empty-table case is implicitly covered by `test_rotate_key` (existing test at line 496).
- **Where rotation tests live**. The MCP rotation tests are in `tests/test_provider_api.py`, not in a separate `tests/test_mcp_api.py`. Mirror that location for connector rotation tests for symmetry. If the reviewer prefers a separate `tests/test_connector_api.py` for the future Flight 2 REST routes, that's a Flight 2 concern — for now, keep rotation tests alongside the existing rotation tests where they will be easy to find.
- **JSON-decode errors are NOT swallowed**. The tolerant-decrypt path catches `InvalidToken` (Fernet symmetric-decrypt failure) and treats it as plaintext-default-migration-residue. It does NOT catch `json.JSONDecodeError` from a successful decrypt that yields garbage — that indicates real corruption and should propagate to the operator as a 500.
- **The leg does NOT add the Pydantic `Literal[...]` on `ConnectorAccount.type`**. That's the `models-and-repository` leg's responsibility. The `_connector_types.py` literal-pinning assert lands in that leg too, when there's a Pydantic model to pin. This leg only ships the empty `CONNECTOR_TYPES` tuple and the table; the literal-pinning machinery is wired up in the next leg.
- **`from typing import get_args` is NOT imported in `_connector_types.py` in this leg**. It will be needed by the `models-and-repository` leg's pinning assert; not by this leg. Keep `_connector_types.py` minimal.

## Files Affected

- `the_one/db/_connector_types.py` (NEW) — empty `CONNECTOR_TYPES` tuple + docstring
- `the_one/db/schema.py` — `CURRENT_VERSION` bump 12→13; new `if version < 13:` migration block
- `the_one/interfaces/web/api.py` — `rotate_encryption_key` extended for connector_accounts.secrets; docstring updated
- `tests/test_db_migration.py` — new `TestV13Migration` class with three tests
- `tests/test_provider_api.py` — two new rotation tests for connector_accounts
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/01-schema-and-migration.md` (this file) — status updated to `landed` at leg end
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — leg-progress entry appended

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All listed tests passing (`docker exec the-one pytest -x --timeout 30`)
- [ ] `make lint` clean
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed`; the agentic-workflow batch reviewer transitions to `completed` at flight end
- [ ] Check off this leg in flight.md (the `schema-and-migration` checkbox in the Legs section)
- [ ] Signal `[HANDOFF:review-needed]`
- [ ] Do NOT commit — the agentic-workflow defers commits to flight-end

---

## Citation Audit

10 citations verified against current code at leg design time:

| Citation | Verification |
|---|---|
| `the_one/db/schema.py:11 CURRENT_VERSION = 12` | OK — verified |
| `the_one/db/_provider_types.py` | OK — read in full |
| `the_one/db/schema.py:300-339` (v8 pattern) | OK — verified |
| `the_one/db/schema.py:363-410` (v10 pattern) | OK — verified |
| `the_one/db/schema.py:412-430` (v11 pattern) | OK — verified |
| `the_one/db/schema.py:432-477` (v12 executescript exception) | OK — verified |
| `the_one/interfaces/web/api.py:rotate_encryption_key` (lines 2744-2853) | OK — read in full |
| `tests/test_db_migration.py:757 TestV11Migration` | OK — verified |
| `tests/test_provider_api.py:496 test_rotate_key` | OK — verified |
| `tests/test_provider_api.py:612 test_rotate_mcp_source_secrets` | OK — verified |
| `tests/test_provider_api.py:548 test_rotate_preserves_key_on_db_failure` | OK — verified |
| `tests/test_provider_api.py:669 test_rotate_preserves_mcp_secrets_on_db_failure` | OK — verified |
| `tests/test_provider_api.py:519 test_rotate_empty_table` | OK — verified |
