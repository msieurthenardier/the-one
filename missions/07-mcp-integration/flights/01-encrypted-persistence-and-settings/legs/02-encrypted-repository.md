# Leg: 02-encrypted-repository

**Status**: completed
**Flight**: [Encrypted MCP Source Persistence + Settings Page](../flight.md)

## Objective

Wire field-segregated encryption through `MCPSource` (Pydantic model) and `MCPSourceRepository` (storage layer) using the existing `Encryptor` infrastructure. Update the type literal away from the deprecated `'sse'`. Cascade the constructor signature change and `'sse'` literal removal through every call site.

## Context

L1 reshaped the `mcp_sources` table at the SQL layer. L2 lifts that shape into the Python data layer:
- The `MCPSource.type` literal becomes `Literal["stdio", "streamable-http"]` to match L1's CHECK constraint.
- A new `secrets: dict[str, Any]` field on the model carries operator-marked sensitive values, separately from the existing plaintext `config` dict.
- `MCPSourceRepository` gains an `Encryptor` dependency (mirrors `LLMProviderRepository(conn, encryptor)` at `repositories.py:486-489`) and JSON-encrypts the `secrets` blob as a single ciphertext on write, decrypts on read.

The key design choice locked at flight design: encrypt the entire `secrets` JSON blob as one ciphertext (one `Fernet.encrypt(json.dumps(secrets).encode())` call per row), NOT per-field encryption inside the JSON. This mirrors the LLM-provider precedent at the structural level (one Fernet call per row), and keeps the storage split auditable by column name.

The `merged_config()` helper is a one-time convenience for F2's bearer-token-from-config / env-var resolution path at MCP-process spawn time. F4's resolver path will NOT use it — F4 keeps the split visible because per-key Substitute/Narrow markers may need to know whether a field is sensitive.

The `Encryptor` is stored as a reference (not a copy) on the repository instance — `Encryptor.install_key()` post-rotation must propagate to live repository instances. This is a behavior pinned by `LLMProviderRepository` at `repositories.py:489` and is the contract L4 (encryption rotation) will rely on.

This leg also fixes the two test cases L1 left intentionally broken (`test_db_repositories.py:230,244` constructed `MCPSource(type='sse')` — those literals get rewritten as part of L2's "Update sites" cascade).

## Inputs

- L1 has landed: `mcp_sources` table is at v10 shape with `secrets TEXT DEFAULT '{}'` column, CHECK accepts only `('stdio', 'streamable-http')`. CURRENT_VERSION = 10.
- `the_one/db/models.py:50-58` — current `MCPSource` model (id, name, type, config, created_at, updated_at; type is `Literal["stdio", "sse"]`)
- `the_one/db/repositories.py:245-303` — current `MCPSourceRepository` (plain CRUD, no Encryptor)
- `the_one/db/repositories.py:486-566` — `LLMProviderRepository` as the encryption-pattern precedent (stored Encryptor reference, `_to_row`, `_row_to_model` with `encrypt_optional`/`decrypt_optional`)
- `the_one/encryption.py` — `Encryptor` class with `encrypt`/`decrypt`/`encrypt_optional`/`decrypt_optional`/`install_key` methods
- `the_one/interfaces/web/api.py:56-58` — current `_mcp_repo()` factory (no Encryptor)
- `the_one/interfaces/web/api.py:617-620` — `_provider_repo()` factory as the construction precedent (`get_encryptor(settings.data_dir)`)
- `tests/test_provider_repository.py` — reference for repository-with-encryptor test patterns (encryptor fixture at lines 17-21, encrypted-at-rest assertion pattern at lines 83-90)
- `tests/test_db_repositories.py:51-52` — current MCP fixture (no Encryptor)
- `tests/test_db_repositories.py:221-250` — current `TestMCPSourceRepository` (4 methods, two of which (`test_list`, `test_delete`) construct `MCPSource(type='sse')` and currently fail post-L1)
- `tests/test_db_api.py:188-209` — `TestMCPSourceAPI::test_crud` (uses `type='stdio'`, currently passing post-L1; L2 will leave it intact but augment with shape changes if API layer needs it — but L2 doesn't change the API layer; that's L3)

## Outputs

- `the_one/db/models.py` — `MCPSource` updated: type literal, new `secrets` field with `default_factory=dict`, new `merged_config()` method
- `the_one/db/repositories.py` — `MCPSourceRepository` updated: `__init__` takes `encryptor` (stored as reference), `create`/`update` write `secrets` column, `_row_to_model` decrypts, helpers added if needed
- `the_one/interfaces/web/api.py` — `_mcp_repo()` factory passes `get_encryptor(settings.data_dir)`
- `tests/test_db_repositories.py` — `mcp_repo` fixture wires Encryptor; existing `test_list`/`test_delete` literals updated; new tests for encryption round-trip, empty-secrets default, post-install_key decryption, encrypted-at-rest invariant
- `tests/test_db_api.py` — leave existing test as-is unless the construction signature change breaks it (it shouldn't — it only goes through the API endpoint which L2 doesn't change)

## Acceptance Criteria

- [ ] `MCPSource.type` is `Literal["stdio", "streamable-http"]` (drops `'sse'`)
- [ ] `MCPSource.secrets: dict[str, Any] = Field(default_factory=dict)` field exists separately from `config`
- [ ] `MCPSource.merged_config()` returns `{**self.config, **self.secrets}` (secrets win on key collision — operator-marked sensitive fields override plaintext defaults)
- [ ] `MCPSourceRepository.__init__(self, conn, encryptor)` accepts and stores the encryptor as a reference (`self.encryptor = encryptor`); the stored reference is the same object identity as the constructor argument
- [ ] `MCPSourceRepository.create()` and `update()` write the `secrets` column with `Fernet.encrypt(json.dumps(secrets).encode())` ciphertext; an empty `secrets={}` round-trips as `Fernet.encrypt(b"{}")` (NOT a plaintext `'{}'` storage shape — empty dict still encrypts)
- [ ] `MCPSourceRepository.get()` and `list()` decrypt the `secrets` column back to a dict via `json.loads(self.encryptor.decrypt(row["secrets"]))`
- [ ] Reading the raw `secrets` column from the DB (bypassing the repository) yields a Fernet-ciphertext string, NOT plaintext JSON
- [ ] After `encryptor.install_key(new_key)`, the SAME repository instance can decrypt newly-written rows with the new key (confirms the reference-not-copy invariant)
- [ ] `the_one/interfaces/web/api.py:_mcp_repo()` constructs `MCPSourceRepository(conn, get_encryptor(settings.data_dir))` mirroring `_provider_repo()` at `api.py:617-620`
- [ ] `tests/test_db_repositories.py` `mcp_repo` fixture passes an `Encryptor` to the repository constructor
- [ ] `tests/test_db_repositories.py:230` and `:244` are updated: `type="sse"` literals replaced with `type="streamable-http"` (the two tests that L1 left intentionally broken)
- [ ] All four existing `TestMCPSourceRepository` tests (`test_create_and_get`, `test_list`, `test_update`, `test_delete`) pass post-L2
- [ ] New `TestMCPSourceRepository` tests added: encryption round-trip (mixed plaintext + secrets), empty-secrets default round-trip, encrypted-at-rest invariant (raw DB read), post-`install_key` decryption preserves on the same instance
- [ ] `tests/test_db_api.py::TestMCPSourceAPI::test_crud` passes after the `client` fixture is updated to also patch `get_encryptor` (the `_mcp_repo()` factory change adds a `get_encryptor(settings.data_dir)` call which would otherwise touch `~/.the-one/encryption.key` in tests, silently coupling test isolation to the developer's actual data directory). Mirror the `test_provider_api.py:72` pattern: add `patch("the_one.interfaces.web.api.get_encryptor", return_value=<test-encryptor>)` to the `with patch(...)` block alongside the existing `get_connection` patch
- [ ] The full unit suite passes: `pytest tests/ --tb=short -q --timeout=60` — no failing tests, including the two `'sse'` tests L1 left broken
- [ ] No `'sse'` string literal remains in any of: `the_one/db/models.py`, `the_one/db/repositories.py`, `tests/test_db_repositories.py`, `tests/test_db_api.py` (verified by grep)

## Verification Steps

- `pytest tests/test_db_repositories.py::TestMCPSourceRepository -v` — all original tests + new tests green
- `pytest tests/ --tb=short -q --timeout=60` — full suite green (1077+ passed, 0 failures)
- `grep -rn "type=.sse.\|type=\"sse\"\|'sse'" the_one/ tests/ --include='*.py'` — no hits in the L2-affected files (allowance: `tests/test_schema.py:55` `_LEGACY_SCHEMA_V1` constant retains the legacy `'sse'` per L1's contract; that hit is expected and frozen)
- Manual: `await repo.get(id)` after `await repo.create(MCPSource(secrets={"GITHUB_TOKEN": "secret123"}))` returns the decrypted secrets verbatim
- Manual: raw `SELECT secrets FROM mcp_sources WHERE id = ?` returns a Fernet ciphertext string (starts with `gAAAAA`-ish base64), NOT `{"GITHUB_TOKEN":"secret123"}`

## Implementation Guidance

1. **Update `the_one/db/models.py`** (`MCPSource` class at lines 50-58). **First**: change the import at line 6 from `from typing import Literal` to `from typing import Any, Literal` — the L2-introduced `dict[str, Any]` annotations require this. Then update the model:
   ```python
   class MCPSource(BaseModel):
       """An MCP source definition — operator-registered server entry."""

       id: str
       name: str
       type: Literal["stdio", "streamable-http"]
       config: dict[str, Any] = Field(default_factory=dict)
       secrets: dict[str, Any] = Field(default_factory=dict)
       created_at: str = Field(default_factory=_now_iso)
       updated_at: str = Field(default_factory=_now_iso)

       def merged_config(self) -> dict[str, Any]:
           """Return a flat dict combining `config` and `secrets`.

           Used by F2's bearer-token-from-config / env-var resolution path at
           MCP-process spawn time. F4's resolver path keeps the split — do not
           call this method from the resolver.

           Secrets win on key collision so an operator-marked-sensitive field
           overrides any plaintext default of the same name.
           """
           return {**self.config, **self.secrets}
   ```
   - Update the `Any` import: `from typing import Any, Literal` (likely already imported; confirm during implementation)
   - The docstring "stub for future protocol connection" at the current line 51 is now stale; update to "operator-registered server entry."

2. **Update `the_one/db/repositories.py::MCPSourceRepository`** (lines 245-303):
   - Add `Encryptor` to the import block (already imported at line 19; no change there).
   - `__init__`:
     ```python
     def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
         self.conn = conn
         self.encryptor = encryptor  # Reference, NOT copy. install_key() post-rotation
                                       # must propagate to live repository instances.
                                       # Mirrors LLMProviderRepository:489.
     ```
   - Add a `_secrets_to_ciphertext` helper and a `_ciphertext_to_secrets` helper inline, OR inline the calls in `create`/`update`/`_row_to_model`. The two-line helpers are cleaner; suggest:
     ```python
     def _secrets_to_ciphertext(self, secrets: dict[str, Any]) -> str:
         return self.encryptor.encrypt(json.dumps(secrets))

     def _ciphertext_to_secrets(self, ciphertext: str | None) -> dict:
         """Decrypt the secrets column. Empty/None ciphertext returns empty dict."""
         if not ciphertext:
             return {}
         return json.loads(self.encryptor.decrypt(ciphertext))
     ```
     The empty-ciphertext branch handles the v10-migrated row case where `secrets` is the column-default `'{}'` string (NOT a Fernet ciphertext). After v10, every `INSERT` from `MCPSourceRepository.create` writes a real ciphertext, so this branch only fires for migration-residue rows. **Important**: the column default `'{}'` is a plaintext-shaped value; the `_ciphertext_to_secrets` helper must handle it. **Use a try/except**:
     ```python
     def _ciphertext_to_secrets(self, ciphertext: str | None) -> dict[str, Any]:
         """Decrypt the secrets column. Empty/None ciphertext returns empty dict.

         InvalidToken is the migration-residue path — pre-L2 rows or rows
         migrated by v10 carry the column default '{}' (plaintext) which
         Fernet.decrypt rejects. Silently fall back to {} for that case;
         the next update() rewrites the column with proper ciphertext.

         JSONDecodeError is NOT swallowed — it means decrypt() succeeded
         but the cleartext bytes were not valid JSON. That indicates real
         data corruption (e.g., manual DB tampering, key reuse mishap)
         and must surface, not be silently masked.
         """
         if not ciphertext:
             return {}
         try:
             plaintext = self.encryptor.decrypt(ciphertext)
         except InvalidToken:
             # Migration-residue: column default '{}' is plaintext, not
             # ciphertext. Treat as empty secrets. Will be rewritten with
             # real ciphertext on the next update().
             return {}
         return json.loads(plaintext)  # JSONDecodeError propagates
     ```
     Add `from cryptography.fernet import InvalidToken` at the top of the file.
   - `create()`:
     ```python
     async def create(self, source: MCPSource) -> None:
         await self.conn.execute(
             "INSERT INTO mcp_sources (id, name, type, config, secrets, created_at, updated_at)"
             " VALUES (?, ?, ?, ?, ?, ?, ?)",
             (
                 source.id,
                 source.name,
                 source.type,
                 json.dumps(source.config),
                 self._secrets_to_ciphertext(source.secrets),
                 source.created_at,
                 source.updated_at,
             ),
         )
         await self.conn.commit()
     ```
   - `update()`:
     ```python
     async def update(self, source: MCPSource) -> None:
         async with self.conn.execute("SELECT 1 FROM mcp_sources WHERE id = ?", (source.id,)) as cur:
             if await cur.fetchone() is None:
                 raise KeyError(f"MCP source not found: {source.id}")
         await self.conn.execute(
             "UPDATE mcp_sources SET name=?, type=?, config=?, secrets=?, updated_at=? WHERE id=?",
             (
                 source.name,
                 source.type,
                 json.dumps(source.config),
                 self._secrets_to_ciphertext(source.secrets),
                 _now_iso(),
                 source.id,
             ),
         )
         await self.conn.commit()
     ```
   - `_row_to_model()`:
     ```python
     def _row_to_model(self, row: aiosqlite.Row) -> MCPSource:
         return MCPSource(
             id=row["id"],
             name=row["name"],
             type=row["type"],
             config=json.loads(row["config"] or "{}"),
             secrets=self._ciphertext_to_secrets(row["secrets"]),
             created_at=row["created_at"],
             updated_at=row["updated_at"],
         )
     ```
     Note: this method MUST become an instance method (not `@staticmethod`) because it now calls `self._ciphertext_to_secrets`. Remove the `@staticmethod` decorator at line 294.

3. **Update `the_one/interfaces/web/api.py:_mcp_repo()`** at lines 56-58:
   ```python
   async def _mcp_repo() -> MCPSourceRepository:
       conn = await get_connection()
       encryptor = get_encryptor(settings.data_dir)
       return MCPSourceRepository(conn, encryptor)
   ```
   Mirrors `_provider_repo()` at lines 617-620 exactly.

4. **Update `tests/test_db_repositories.py`**:

   (a) `mcp_repo` fixture at lines 50-52 (must remain function-scoped — broader scope would outlive the per-test conn fixture):
   ```python
   @pytest.fixture
   def mcp_repo_encryptor(tmp_path):
       # Function-scoped (default). Do NOT promote to module/session scope —
       # would outlive the per-test `conn` fixture and create cross-test
       # state leakage on the encryptor's in-memory key.
       from cryptography.fernet import Fernet

       from the_one.encryption import Encryptor
       key = Fernet.generate_key()
       return Encryptor(key, key_path=tmp_path / "mcp.key")


   @pytest.fixture
   def mcp_repo(conn, mcp_repo_encryptor):
       return MCPSourceRepository(conn, mcp_repo_encryptor)
   ```

   (b) Existing `test_list` at line 230 — change `type="sse"` to `type="streamable-http"`.

   (c) Existing `test_delete` at line 244 — same fix.

   (d) Add new tests inside `TestMCPSourceRepository`:
   ```python
   async def test_secrets_round_trip(self, mcp_repo: MCPSourceRepository) -> None:
       """secrets dict round-trips through the encryption envelope."""
       source = MCPSource(
           id="s1",
           name="GitHub MCP",
           type="stdio",
           config={"command": "github-mcp"},
           secrets={"GITHUB_TOKEN": "ghp_secret_value_123"},
       )
       await mcp_repo.create(source)
       fetched = await mcp_repo.get("s1")
       assert fetched.config == {"command": "github-mcp"}
       assert fetched.secrets == {"GITHUB_TOKEN": "ghp_secret_value_123"}

   async def test_secrets_encrypted_at_rest(self, mcp_repo: MCPSourceRepository) -> None:
       """Raw DB read of the secrets column yields a ciphertext, NOT plaintext JSON."""
       source = MCPSource(
           id="s1", name="Test", type="stdio",
           secrets={"TOKEN": "super-secret-value"},
       )
       await mcp_repo.create(source)
       async with mcp_repo.conn.execute(
           "SELECT secrets FROM mcp_sources WHERE id = ?", ("s1",)
       ) as cur:
           row = await cur.fetchone()
       raw = row["secrets"]
       assert raw is not None
       assert "super-secret-value" not in raw
       assert "TOKEN" not in raw
       # Fernet ciphertext is base64; sanity-check it decrypts back via the
       # repo's encryptor.
       decrypted = mcp_repo.encryptor.decrypt(raw)
       assert decrypted == '{"TOKEN": "super-secret-value"}'

   async def test_empty_secrets_default(self, mcp_repo: MCPSourceRepository) -> None:
       """A source created without secrets= round-trips with secrets={}."""
       source = MCPSource(id="s1", name="Test", type="stdio", config={"x": 1})
       await mcp_repo.create(source)
       fetched = await mcp_repo.get("s1")
       assert fetched.secrets == {}

   async def test_install_key_post_create_decrypts_via_same_instance(
       self, mcp_repo: MCPSourceRepository
   ) -> None:
       """Post install_key, the same repo instance decrypts new writes.

       Locks the reference-not-copy invariant: install_key() mutates the
       Encryptor in place; the repository's stored reference sees the
       mutation. Re-creates a row after the key swap and round-trips.
       """
       from cryptography.fernet import Fernet
       new_key = Fernet.generate_key()
       mcp_repo.encryptor.install_key(new_key)

       source = MCPSource(
           id="s1", name="PostKey", type="stdio",
           secrets={"K": "value-after-rotation"},
       )
       await mcp_repo.create(source)
       fetched = await mcp_repo.get("s1")
       assert fetched.secrets == {"K": "value-after-rotation"}
   ```
   `merged_config` is a model method, not a repository concern — but worth a model-level test:
   ```python
   def test_merged_config_overlays_secrets_on_config() -> None:
       """secrets win on key collision; non-overlapping keys merge."""
       source = MCPSource(
           id="s1", name="T", type="stdio",
           config={"command": "x", "TOKEN": "plaintext-default"},
           secrets={"TOKEN": "encrypted-real"},
       )
       merged = source.merged_config()
       assert merged == {"command": "x", "TOKEN": "encrypted-real"}
   ```
   Add this test to `tests/test_db_repositories.py` at the end of `TestMCPSourceRepository` OR in a new `TestMCPSourceModel` class — designer's choice. The implementer should make a judgment call based on test class organization conventions.

5. **Update `tests/test_db_api.py:16-37` `client` fixture** to also patch `get_encryptor`. The current fixture patches only `get_connection` (line 27). After L2, `_mcp_repo()` calls `get_encryptor(settings.data_dir)` which would otherwise touch `~/.the-one/encryption.key` in tests, silently coupling test isolation to the developer's actual home directory. Mirror the `tests/test_provider_api.py:56-72` pattern:
   ```python
   from cryptography.fernet import Fernet
   from the_one.encryption import Encryptor

   @pytest.fixture
   async def client(tmp_path):
       """Create a test client with an isolated DB and test encryptor."""
       db_path = tmp_path / "test.db"

       conn = await aiosqlite.connect(str(db_path))
       conn.row_factory = aiosqlite.Row
       await conn.execute("PRAGMA foreign_keys=ON")
       await ensure_schema(conn)

       # Test encryptor — function-scoped (mirrors test_provider_api.py).
       test_key = Fernet.generate_key()
       key_path = tmp_path / "test.key"
       test_encryptor = Encryptor(test_key, key_path=key_path)

       with (
           patch("the_one.interfaces.web.api.get_connection", return_value=conn),
           patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
       ):
           test_app = FastAPI()
           test_app.include_router(router)
           transport = ASGITransport(app=test_app)
           async with AsyncClient(transport=transport, base_url="http://test") as c:
               yield c

       await conn.close()
   ```
   This is shared infrastructure used by every test in `test_db_api.py` (TestAgentAPI, TestKBAPI, TestMCPSourceAPI, TestChatSessionAPI). All of them get the patched encryptor; none currently exercise it but L2's `_mcp_repo()` change makes it required.

6. **Verify no `'sse'` literals remain**: run `grep -rn "type=.sse.\|'sse'" the_one/ tests/ --include='*.py'` — expected hits limited to `tests/test_schema.py:55` (frozen `_LEGACY_SCHEMA_V1`) and any incidental string occurrences in comments. No `MCPSource(type='sse')` calls should remain.

7. **Run the test suite**:
   ```
   pytest tests/test_db_repositories.py::TestMCPSourceRepository -v
   pytest tests/test_db_api.py -v
   pytest tests/ --tb=short -q --timeout=60
   ```
   Expected: full green, 1077+ passed (the 2 failing tests from L1 are now fixed by L2's `'sse'` literal updates AND by the new encryption envelope; new tests are additive). `test_db_api.py` must be all green — the `client` fixture's new `get_encryptor` patch keeps the test environment isolated from the host's `~/.the-one/`.

8. **Update flight log** at `missions/07-mcp-integration/flights/01-encrypted-persistence-and-settings/flight-log.md`:
   - Append `### 02-encrypted-repository` entry under `## Leg Progress`
   - Status `landed`, started/completed timestamps, "Changes Made" listing the model + repository + api factory + tests edits, "Notes" entry confirming the L1 anomaly is now resolved (the two `'sse'` tests pass).
   - Under `## Decisions` if any deviation from the leg spec was made (e.g., where `merged_config` test was placed); under `## Anomalies` only if something unexpected surfaced.

9. **Set leg status to `landed`** in this leg's frontmatter (line 3).

10. **Do NOT commit** — flight-end commit per agentic-workflow protocol.

11. **Signal `[HANDOFF:review-needed]`** when implementation is complete.

## Edge Cases

- **Migration-residue row with plaintext `'{}'` in the secrets column**: the v10 migration writes the column-default `'{}'` (plain SQL string, NOT a Fernet ciphertext) for any existing rows at the time of migration. The `_ciphertext_to_secrets` helper handles this via try/except on `InvalidToken`, returning an empty dict. The next `update()` rewrites the column with proper ciphertext. Documented inline in the helper.
- **Fernet decryption failure mid-flight**: if the encryption key on disk is rotated externally without going through `/api/encryption/rotate` (e.g., operator manually replaces `encryption.key`), all existing ciphertexts become un-decryptable. This is the same behavior as `LLMProviderRepository` (verified at `repositories.py:562` — `decrypt_optional` raises). L2 inherits this behavior; L4's rotation endpoint is the supported rotation path.
- **`secrets` field mutation post-load**: since `secrets` is a `dict[str, Any]`, mutations to the returned dict do NOT propagate to the DB unless `update()` is called. Pydantic's default behavior. Documented as part of the model contract (no special handling needed in L2; surfaces in L3 as the API endpoint contract).
- **Pydantic model-method tests**: `merged_config()` is a pure function with no DB. The test should be sync (`def`, not `async def`) and avoid the `mcp_repo` fixture.

## Files Affected

- `the_one/db/models.py` — `MCPSource` model: type literal, secrets field, merged_config method, docstring update
- `the_one/db/repositories.py` — `MCPSourceRepository`: __init__ takes encryptor, _secrets_to_ciphertext + _ciphertext_to_secrets helpers, create/update/_row_to_model updates; `_row_to_model` becomes instance method
- `the_one/interfaces/web/api.py` — `_mcp_repo()` factory passes encryptor
- `tests/test_db_repositories.py` — `mcp_repo_encryptor` fixture (new), `mcp_repo` fixture (signature change), `test_list`/`test_delete` literal fixes, new tests for encryption round-trip, encrypted-at-rest, empty-secrets default, install_key invariant, merged_config method

## State-Machine Reachability Audit

States introduced or affected:
- `MCPSource.type` value space (Pydantic level): `{"stdio", "sse"}` → `{"stdio", "streamable-http"}`. The `'sse'` value is removed; any external caller hardcoding it gets a Pydantic ValidationError. Only known external caller from grep: the two test cases at `tests/test_db_repositories.py:230,244` (already enumerated as L2 update sites).
- `MCPSource.secrets` value space: introduced as a free-form `dict[str, Any]` with `default_factory=dict`. Any value is valid; the only constraint is JSON-serializability (enforced at write time by `json.dumps`).
- `MCPSourceRepository` instance state gains `self.encryptor`. Construction is now strictly `(conn, encryptor)` — no zero-arg fallback. Verified no other call site of `MCPSourceRepository(conn)` exists (grep `MCPSourceRepository(`).

Tests that pin pre-L2 state and would contradict L2:
- `tests/test_db_repositories.py:230` — `MCPSource(type="sse")` — gets rewritten to `type="streamable-http"`.
- `tests/test_db_repositories.py:244` — same.
- `tests/test_db_repositories.py:51-52` — `MCPSourceRepository(conn)` zero-encryptor construction — gets rewritten to take an encryptor.
- `tests/test_db_api.py:188-209` — `TestMCPSourceAPI::test_crud` already uses `type="stdio"`; the API endpoint factory change is internal so the test continues to pass without modification (the `_mcp_repo()` change is transparent to the test client).

No FK behaviors to audit (no FK references to/from `mcp_sources`). No application caches in L2. No fallback handlers silently masking the `'sse'` value.

## Cache Freshness Contract

- The `MCPSourceRepository` instance holds a reference to the `Encryptor`. The Encryptor's Fernet key is mutated in place by `install_key()`. **Source of truth**: the on-disk `encryption.key` file; **rebuild trigger**: explicit `install_key()` call (currently only `/api/encryption/rotate` calls it); **maximum staleness acceptable**: zero — once rotation happens, all subsequent reads/writes MUST use the new key. The shared-reference design ensures this. Tested by `test_install_key_post_create_decrypts_via_same_instance`.
- No other caches in this leg.

## Citation Audit

19 citations verified against current code at leg design time:
- `the_one/db/models.py:50-58` `MCPSource` — OK (type Literal, no secrets field today, no merged_config)
- `the_one/db/repositories.py:245-303` `MCPSourceRepository` — OK (no Encryptor, plain CRUD)
- `the_one/db/repositories.py:486-489` `LLMProviderRepository.__init__` precedent — OK
- `the_one/db/repositories.py:562` `decrypt_optional` raise behavior — OK
- `the_one/db/repositories.py:294` `@staticmethod` on `_row_to_model` (to be removed) — OK
- `the_one/encryption.py` Encryptor class shape — OK (encrypt/decrypt/encrypt_optional/decrypt_optional/install_key all present)
- `the_one/interfaces/web/api.py:56-58` `_mcp_repo()` factory (no Encryptor) — OK
- `the_one/interfaces/web/api.py:617-620` `_provider_repo()` factory (Encryptor passed) — OK
- `tests/test_db_repositories.py:50-52` `mcp_repo` fixture (no Encryptor) — OK
- `tests/test_db_repositories.py:221-250` `TestMCPSourceRepository` — OK (4 methods present)
- `tests/test_db_repositories.py:230,244` `type="sse"` literals — OK (verified pre-L2 state, will be the L2 fix targets)
- `tests/test_db_api.py:188-209` `TestMCPSourceAPI::test_crud` (uses `type="stdio"`) — OK
- `tests/test_provider_repository.py:17-21` encryptor fixture pattern — OK
- `tests/test_provider_repository.py:34` `LLMProviderRepository(conn, encryptor)` construction precedent — OK
- `tests/test_provider_repository.py:83-90` encrypted-at-rest test pattern — OK

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `pytest tests/test_db_repositories.py::TestMCPSourceRepository -v` green (existing 4 + new 4-5 tests)
- [ ] `pytest tests/ --tb=short -q --timeout=60` green (no failures)
- [ ] `grep -rn "MCPSource(type=.sse.\|'sse'" the_one/ tests/ --include='*.py'` confirms no MCPSource(type='sse') literals remain (test_schema.py legacy DDL hit is allowed)
- [ ] Update flight-log.md with leg progress entry (status `landed`, note that L1's anomaly is resolved)
- [ ] Set this leg's status to `landed` (in this file's frontmatter, line 3)
- [ ] Do NOT check off this leg in flight.md yet — that happens at flight commit
- [ ] Do NOT commit — per agentic-workflow protocol, commit happens once at flight end
