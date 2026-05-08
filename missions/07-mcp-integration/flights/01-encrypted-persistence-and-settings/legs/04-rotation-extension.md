# Leg: 04-rotation-extension

**Status**: completed
**Flight**: [Encrypted MCP Source Persistence + Settings Page](../flight.md)

## Objective

Extend `/api/encryption/rotate` to re-encrypt every MCP source's `secrets` column in the same crash-safe transaction that already re-encrypts every `llm_providers.api_key`. After rotation, both surfaces must decrypt cleanly under the new key; if the DB commit fails, neither surface's on-disk ciphertext changes and the on-disk key file is byte-identical to its pre-rotation contents.

## Context

L1/L2/L3 landed the schema, repository, and HTTP surface for encrypted MCP source secrets. The rotation endpoint at `the_one/interfaces/web/api.py:1292-1356` currently handles only `llm_providers.api_key`. The flight's design decision (`flight.md:51-53`) requires extending that endpoint in one pass to cover MCP secrets — a partial rotation that handles only one surface would leave the other surface encrypted with a key that no longer exists on disk (silent corruption).

Critical invariants (per flight spec line 128 + the v8 schema docstring):

- **All-in-memory before any UPDATE**: SELECT all LLM provider rows → SELECT all MCP source rows → decrypt + re-encrypt all in memory → ONE UPDATE loop covering both tables → ONE `commit()` → file replace. The existing endpoint already follows this shape for one table; L4 extends to two.
- **No non-DML statements between the two table SELECTs and the two UPDATE loops**: aiosqlite's default mode silently COMMITs before any non-DML statement (PRAGMA, DDL, BEGIN). A `PRAGMA foreign_keys=...` or `CREATE TEMP TABLE` mid-rotation would split the rotation into two separately-committed transactions and break the atomicity contract. The endpoint stays pure-DML between SELECT and commit.
- **Migration-residue tolerance**: post-v10 MCP rows that have NEVER been written by the L2 repository carry `secrets='{}'` (plaintext default from the column DEFAULT clause). `Fernet.decrypt('{}')` raises `InvalidToken`. The repository's `_ciphertext_to_secrets` helper at `repositories.py:258-280` swallows `InvalidToken` and returns `{}`. Rotation must use the SAME tolerant-decode semantic so it doesn't crash on these rows; treat them as empty secrets and re-encrypt as `Fernet.encrypt(b'{}')` with the new key. Side-effect: rotation incidentally normalizes migration-residue rows to proper ciphertext — desirable.
- **Cached encryptor swap order**: `encryptor.install_key(new_key)` happens AFTER `os.replace`. Any in-flight repository instance holding `self.encryptor = encryptor` (via L2's reference-not-copy contract at `repositories.py:251-253` for `MCPSourceRepository` and `repositories.py:530` for `LLMProviderRepository`) sees the new key on the next decrypt — no stale-key reads. If the `install_key` call were placed before `os.replace` and the file rename failed, the cached encryptor would have a key that's not on disk; recovery would require reading the on-disk file's bytes back into the cache.

L4 does NOT touch the L1 schema, the L2 repository class, the L3 endpoints, or any UI. Pure rotation-endpoint surgery.

## Inputs

- L1 + L2 + L3 have landed
- `the_one/interfaces/web/api.py` — `rotate_encryption_key` endpoint at lines 1292–1356 (anchor: `@router.post("/encryption/rotate")` decorator and the function name). Implementer: regrep before edits because L3 already shifted lines downstream of the MCP block.
- `the_one/db/repositories.py::MCPSourceRepository._ciphertext_to_secrets` (`repositories.py:258-280`) — the tolerant-decode pattern that rotation must mirror.
- `the_one/db/repositories.py::MCPSourceRepository._secrets_to_ciphertext` (`repositories.py:255-256`) — the encrypt-side reference: `encryptor.encrypt(json.dumps(secrets))`.
- `the_one/db/repositories.py::MCPSourceRepository.__init__` (`repositories.py:249-253`) — the reference-not-copy invariant for the cached `self.encryptor`. Mirror citation: `LLMProviderRepository.__init__` at `repositories.py:525-530` (the `self.encryptor = encryptor` line is at 530).
- `tests/test_provider_api.py::TestEncryptionRotation` (lines 495–611):
  - `test_rotate_key` (line 496) — basic round-trip with one provider
  - `test_rotate_empty_table` (line 519) — no providers, no-op
  - `test_rotate_multiple_providers` (line 525) — three providers
  - `test_rotate_preserves_key_on_db_failure` (line 548) — commit-failure invariants (key file untouched, cached encryptor unchanged, on-disk ciphertext untouched, direct decrypt with old key still works)
- `tests/test_provider_api.py:55-81` — `client` fixture that creates an isolated DB + test encryptor and patches `get_connection` and `get_encryptor` (already extended in L2 — confirms the test rig supports MCP rotation).
- `the_one/db/models.py::MCPSource` — model shape (post-L2): `type: Literal["stdio", "streamable-http"]`, `secrets: dict[str, Any]`.
- `the_one/encryption.py::Encryptor` — `encrypt(plaintext: str) -> str`, `decrypt(ciphertext: str) -> str`, `install_key(new_key: bytes) -> None`. Anchor by symbol.
- `the_one/db/schema.py` v8 docstring — the canonical statement of the "no non-DML inside auto-begin transaction" rule that drives the no-PRAGMA-mid-rotation invariant.

## Outputs

- `the_one/interfaces/web/api.py::rotate_encryption_key` extended:
  - Adds a parallel SELECT of `mcp_sources.id, secrets`
  - Adds a tolerant decrypt loop (mirroring `_ciphertext_to_secrets` semantic — swallow `InvalidToken`, treat as `{}`)
  - Adds a re-encrypt loop using `new_encryptor.encrypt(json.dumps(secrets_dict))`
  - Adds a parallel UPDATE loop on `mcp_sources` inside the same `try:` / single-`commit()` block
  - All other lines (key generation, file replace, `install_key`, status return) unchanged
- `tests/test_provider_api.py::TestEncryptionRotation` extended with five new tests:
  - `test_rotate_mcp_source_secrets` — single MCP source with non-empty secrets, rotate, decrypt-with-new-key proves round-trip
  - `test_rotate_mixed_providers_and_mcps` — both surfaces populated, single rotation re-encrypts both
  - `test_rotate_preserves_mcp_secrets_on_db_failure` — commit-failure invariant for the MCP surface, mirroring the existing provider failure-path test
  - `test_rotate_with_migration_residue_mcp_row` — a row with plaintext `secrets='{}'` (simulating a v10-migrated row that's never been written by the L2 repo) rotates without crashing and ends up with proper new-key ciphertext
  - `test_rotate_dual_surface_atomicity_on_db_failure` — both surfaces populated, simulated commit failure rolls back BOTH UPDATE loops; on-disk ciphertext byte-identical to pre-rotation on BOTH tables (proves the single-`commit()` covers both)

## Acceptance Criteria

- [ ] `POST /api/encryption/rotate` re-encrypts both `llm_providers.api_key` AND `mcp_sources.secrets` in a single transaction
- [ ] After rotation, every MCP source's `secrets` decrypts cleanly under the new key — verified by GET-after-rotate: the masked-tail values shown in `/api/mcp-sources/{id}` are unchanged
- [ ] After rotation, every LLM provider's `api_key` still decrypts (existing `test_rotate_key` and `test_rotate_multiple_providers` continue to pass)
- [ ] The rotation endpoint contains NO non-DML statements (no `PRAGMA`, no `CREATE TEMP TABLE`, no DDL) between the first SELECT and the final `commit()`
- [ ] Migration-residue MCP rows (plaintext `secrets='{}'` from v10's column default that have never been written by the L2 repo) do NOT crash rotation; they are normalized to proper new-key ciphertext for `{}` (treated as empty secrets, mirroring `_ciphertext_to_secrets`'s `InvalidToken`-swallow semantic)
- [ ] `test_rotate_preserves_key_on_db_failure` continues to pass without modification (the LLM provider failure-path invariants are unchanged)
- [ ] New `test_rotate_mcp_source_secrets` passes — single MCP source with `secrets={"GITHUB_TOKEN": "ghp_realsecretvalue"}` rotates; post-rotation a direct `Fernet(new_key).decrypt(...)` of the on-disk ciphertext yields the original plaintext JSON
- [ ] New `test_rotate_mixed_providers_and_mcps` passes — both an LLM provider and an MCP source populated; single rotation re-encrypts both; both decrypt under the new key (verified via masked-tail GET equality, mirroring `test_rotate_key`'s pattern). The negative invariant ("neither decrypts under the old key") is implicit in "key file replaced + new ciphertext written"; we do not assert it explicitly because the existing `test_rotate_key` doesn't either, and round-trip GET equality is the established proof shape.
- [ ] New `test_rotate_preserves_mcp_secrets_on_db_failure` passes — under simulated `aiosqlite.Connection.commit` failure: the on-disk key file is byte-identical to its pre-rotation contents; the on-disk MCP `secrets` ciphertext is byte-identical to its pre-rotation contents; the cached encryptor still decrypts the pre-rotation ciphertext (proves `install_key` was NOT called); a fresh `Fernet(key_before).decrypt(...)` of the row's `secrets` column still yields the original plaintext JSON
- [ ] New `test_rotate_with_migration_residue_mcp_row` passes — row with `secrets='{}'` (plaintext) pre-rotation; post-rotation the row's `secrets` column is non-`'{}'` (it's now proper ciphertext for `'{}'`) and decrypts under the new key to `{}`
- [ ] New `test_rotate_dual_surface_atomicity_on_db_failure` passes — both an LLM provider AND an MCP source populated, simulated `aiosqlite.Connection.commit` failure; on-disk ciphertext on BOTH surfaces is byte-identical to its pre-rotation contents (proves the single `try:` / single `commit()` / single `rollback` rolls back BOTH tables atomically)
- [ ] Full unit suite passes: `pytest tests/ --tb=short -q --timeout=60` — 0 failures (count climbs by 5 from L3's 1094)

## Verification Steps

- `pytest tests/test_provider_api.py::TestEncryptionRotation -v --timeout=60` — 4 existing + 5 new tests green
- `pytest tests/ --tb=short -q --timeout=60` — full suite green (~1099 tests)
- Code-review verification: visually inspect the rotation function — confirm the structure is `SELECT-providers → SELECT-mcps → generate key → re-encrypt providers → re-encrypt mcps → try{ UPDATE-providers → UPDATE-mcps → commit } → file replace → install_key`. No `PRAGMA`, no `CREATE TEMP TABLE`, no DDL anywhere in the function body.
- Manual: with a `'streamable-http'` MCP source containing encrypted `client_secret` and a `'stdio'` source containing encrypted `env`, plus an LLM provider, trigger `POST /api/encryption/rotate`; all three sources still decrypt correctly afterward (verified via GET masked-tail equality).

## Implementation Guidance

1. **Re-locate the rotation endpoint**. Run `grep -n "@router.post(\"/encryption/rotate\")\|async def rotate_encryption_key" the_one/interfaces/web/api.py`. The L3 landing shifted line numbers; cited line range 1292–1356 is approximate. Anchor by the symbol `rotate_encryption_key`.

2. **Read the current implementation in full** before editing. The existing structure has 7 numbered steps in inline comments — the L4 edits insert MCP-parallel code AT specific points, NOT a wholesale rewrite. Critical: the existing comment numbering (1-7) is the canonical structure documenting the crash-safety contract; preserve it and extend.

3. **Add the json+InvalidToken imports if not present**. `json` is already imported at the top of the file. `InvalidToken` is NOT — add `from cryptography.fernet import Fernet, InvalidToken` (already imports `Fernet`; extend the existing line).

4. **Add MCP source SELECT after the LLM provider SELECT** (current Step 1 of the function — "Decrypt existing rows with the current encryptor"). The new SELECT goes immediately after the existing `decrypted = [...]` line, BEFORE Step 2 (key generation). New code:

   ```python
   async with conn.execute("SELECT id, secrets FROM mcp_sources") as cur:
       mcp_rows = await cur.fetchall()

   # Tolerant decrypt mirrors MCPSourceRepository._ciphertext_to_secrets at
   # repositories.py:258-280 — pre-L2-write rows or v10-migration-residue
   # rows carry the column default '{}' (plaintext) which Fernet rejects
   # with InvalidToken. Treat those as empty secrets and let rotation
   # incidentally normalize them to proper ciphertext for {}. JSON decode
   # errors are NOT swallowed — they indicate real corruption.
   decrypted_mcps: list[tuple[str, dict]] = []
   for row in mcp_rows:
       ciphertext = row["secrets"]
       if not ciphertext:
           secrets_dict: dict = {}
       else:
           try:
               plaintext = encryptor.decrypt(ciphertext)
               secrets_dict = json.loads(plaintext)
           except InvalidToken:
               secrets_dict = {}
       decrypted_mcps.append((row["id"], secrets_dict))
   ```

   **Do NOT** issue any `PRAGMA`, `CREATE`, `BEGIN`, or other non-DML statement here — the cursor for the LLM SELECT and this MCP SELECT are both inside the implicit transaction; aiosqlite's silent-COMMIT-before-non-DML rule (per schema.py v8 docstring) would split rotation into two separately-committed transactions otherwise.

5. **Re-encrypt the MCP rows in memory** after the LLM `reencrypted = [...]` line, BEFORE the existing `try:` block (current Step 4). The encrypt mirrors `MCPSourceRepository._secrets_to_ciphertext`:

   ```python
   reencrypted_mcps = [
       (sid, new_encryptor.encrypt(json.dumps(secrets_dict)))
       for sid, secrets_dict in decrypted_mcps
   ]
   ```

6. **Extend the UPDATE loop inside the existing `try:` block** (current Step 4) to cover both tables. The combined block becomes:

   ```python
   try:
       for pid, ct in reencrypted:
           await conn.execute(
               "UPDATE llm_providers SET api_key = ? WHERE id = ?",
               (ct, pid),
           )
       for sid, ct in reencrypted_mcps:
           await conn.execute(
               "UPDATE mcp_sources SET secrets = ? WHERE id = ?",
               (ct, sid),
           )
       await conn.commit()
   except Exception:
       await conn.rollback()
       raise
   ```

   **Single `commit()` covers both tables.** A failure in the MCP UPDATE loop rolls back BOTH tables atomically — same crash-safety guarantee as before, extended.

7. **Do NOT change Steps 5–7** (key file write, atomic rename, `install_key`). Those run only after the combined commit succeeds. The `install_key` call propagates to BOTH `LLMProviderRepository` (which holds `self.encryptor` per `repositories.py:489`) AND `MCPSourceRepository` (which holds `self.encryptor` per `repositories.py:251-253`) — both are reference-not-copy, both pick up the new key automatically.

8. **Update the function docstring** to reflect the dual-surface scope:

   ```python
   """Rotate the encryption key with crash-safe ordering.

   Re-encrypts every LLM provider row's ``api_key`` AND every MCP source
   row's ``secrets`` blob using a freshly generated key in memory and
   commits the DB transaction *before* the new key file replaces the old
   one via temp-file + ``os.replace``. Both surfaces commit atomically —
   a partial rotation that handled only one would leave the other
   encrypted under a key that no longer exists on disk. If the DB commit
   fails, the on-disk key file is left byte-identical to its pre-rotation
   contents so existing ciphertext on both surfaces remains decryptable.

   Migration-residue MCP rows (plaintext ``'{}'`` carried over from the
   v10 column default) are tolerated via InvalidToken-swallowing decrypt;
   they are normalized to proper ciphertext for ``{}`` as a side-effect.
   """
   ```

9. **Extend `tests/test_provider_api.py::TestEncryptionRotation`** with the five new tests. Place them AFTER `test_rotate_preserves_key_on_db_failure` (current line ~611) and BEFORE the next class/section (`# ── Provider helper ──...` at ~613). The new tests POST through the `/api/mcp-sources` endpoint (not direct repository writes), mirroring how the existing tests POST through `/api/providers`. `aiosqlite` is already imported at the top of the file; no new imports needed beyond `Fernet`/`Encryptor` (already present).

   ```python
   async def test_rotate_mcp_source_secrets(self, client: AsyncClient) -> None:
       """After rotation, MCP source secrets still decrypt under the new key."""
       create_resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "GH",
               "type": "stdio",
               "config": {"command": "github-mcp"},
               "secrets": {"GITHUB_TOKEN": "ghp_rotationtest5678"},
           },
       )
       assert create_resp.status_code in (200, 201)
       sid = create_resp.json()["id"]

       resp = await client.post("/api/encryption/rotate")
       assert resp.status_code == 200
       assert resp.json() == {"status": "ok"}

       # GET-after-rotate proves the cached encryptor decrypts under the new key
       get_resp = await client.get(f"/api/mcp-sources/{sid}")
       assert get_resp.status_code == 200
       assert get_resp.json()["secrets"]["GITHUB_TOKEN"] == "***...5678"

   async def test_rotate_mixed_providers_and_mcps(
       self, client: AsyncClient
   ) -> None:
       """One rotation re-encrypts both surfaces atomically."""
       prov_resp = await client.post(
           "/api/providers",
           json={
               "name": "MixedProv",
               "type": "openai",
               "base_url": "https://api.openai.com/v1",
               "api_key": "sk-mixedrotateprovider",
           },
       )
       pid = prov_resp.json()["id"]

       mcp_resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "MixedMCP",
               "type": "streamable-http",
               "config": {"url": "https://mcp.example.com"},
               "secrets": {"AUTH": "bearer-mixedrotatemcptoken"},
           },
       )
       sid = mcp_resp.json()["id"]

       rot_resp = await client.post("/api/encryption/rotate")
       assert rot_resp.status_code == 200
       assert rot_resp.json() == {"status": "ok"}

       # Both surfaces still decrypt under the new key
       prov_get = await client.get(f"/api/providers/{pid}")
       assert prov_get.json()["api_key"] == "***...ider"
       mcp_get = await client.get(f"/api/mcp-sources/{sid}")
       assert mcp_get.json()["secrets"]["AUTH"] == "***...oken"

   async def test_rotate_preserves_mcp_secrets_on_db_failure(
       self, client: AsyncClient, tmp_path: Path
   ) -> None:
       """A DB commit failure during rotation leaves MCP ciphertext intact.

       Mirrors test_rotate_preserves_key_on_db_failure for the MCP surface:
       on-disk key file unchanged, cached encryptor unchanged, on-disk
       ciphertext unchanged, direct decrypt with the pre-rotation key
       still yields the original plaintext.
       """
       create_resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "FailMCP",
               "type": "stdio",
               "config": {"command": "x"},
               "secrets": {"K": "preservedmcpsecretvalue"},
           },
       )
       sid = create_resp.json()["id"]

       key_path = tmp_path / "test.key"
       key_before = key_path.read_bytes()

       # Capture pre-rotation ciphertext directly from the DB so we can
       # assert it's byte-identical post-failure.
       direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
       direct_conn.row_factory = aiosqlite.Row
       try:
           async with direct_conn.execute(
               "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
           ) as cur:
               row = await cur.fetchone()
           ct_before = row["secrets"]
       finally:
           await direct_conn.close()

       with (
           patch(
               "aiosqlite.Connection.commit",
               side_effect=RuntimeError("simulated DB failure"),
           ),
           pytest.raises(RuntimeError, match="simulated DB failure"),
       ):
           await client.post("/api/encryption/rotate")

       # (i) Key file byte-identical to its pre-rotation contents
       assert key_path.read_bytes() == key_before

       # (ii) Cached encryptor still decrypts (proves install_key NOT called)
       get_resp = await client.get(f"/api/mcp-sources/{sid}")
       assert get_resp.status_code == 200
       assert get_resp.json()["secrets"]["K"] == "***...alue"

       # (iii) On-disk ciphertext byte-identical (catches a regression where
       # the UPDATE loop wrote new ciphertext before the commit failed)
       direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
       direct_conn.row_factory = aiosqlite.Row
       try:
           async with direct_conn.execute(
               "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
           ) as cur:
               row = await cur.fetchone()
       finally:
           await direct_conn.close()
       assert row is not None
       assert row["secrets"] == ct_before
       # Direct decrypt with the pre-rotation key still works on disk ciphertext
       decrypted = Fernet(key_before).decrypt(row["secrets"].encode()).decode()
       assert json.loads(decrypted) == {"K": "preservedmcpsecretvalue"}

   async def test_rotate_with_migration_residue_mcp_row(
       self, client: AsyncClient, tmp_path: Path
   ) -> None:
       """A v10-migrated row with plaintext '{}' rotates without crashing.

       Pre-L2 rows + v10-migration-residue rows have secrets='{}' (the
       column default — plaintext, not ciphertext). Rotation must tolerate
       these via the same InvalidToken-swallow semantic as
       MCPSourceRepository._ciphertext_to_secrets, and normalize them to
       proper ciphertext as a side-effect.

       Pattern: create the row through the API (so it's established via the
       fixture's cached connection — guaranteed visible to subsequent API
       reads), then reach in via a fresh aiosqlite connection to OVERWRITE
       the secrets column with literal '{}' (simulating migration-residue).
       This is the inverse of the existing failure-path test's pattern
       (write via API conn, read via fresh conn) — same proven cross-
       connection commit-visibility ordering.
       """
       # Step 1: create the row through the API. This goes through the L2
       # repository's encrypted-write path and the row is established via
       # the fixture's cached connection.
       create_resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "Residue",
               "type": "stdio",
               "config": {"command": "x"},
               "secrets": {},  # The L2 repo encrypts '{}' as proper ciphertext
           },
       )
       assert create_resp.status_code in (200, 201)
       sid = create_resp.json()["id"]

       # Step 2: open a fresh aiosqlite connection and overwrite the secrets
       # column with literal '{}', simulating a migration-residue row that
       # has never been written by the L2 repo. The fresh connection's
       # commit is visible to the API's cached connection on its next
       # SELECT (standard SQLite cross-connection visibility — proven by
       # the existing test_rotate_preserves_key_on_db_failure pattern).
       direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
       direct_conn.row_factory = aiosqlite.Row
       try:
           await direct_conn.execute(
               "UPDATE mcp_sources SET secrets = '{}' WHERE id = ?",
               (sid,),
           )
           await direct_conn.commit()
       finally:
           await direct_conn.close()

       # Pre-rotation: residue row reads as empty secrets (tolerant decode)
       pre_get = await client.get(f"/api/mcp-sources/{sid}")
       assert pre_get.status_code == 200
       assert pre_get.json()["secrets"] == {}

       # Rotate — must NOT crash on the residue row
       rot_resp = await client.post("/api/encryption/rotate")
       assert rot_resp.status_code == 200
       assert rot_resp.json() == {"status": "ok"}

       # Post-rotation: residue row reads as empty secrets, AND the on-disk
       # column is no longer the literal '{}' — it's proper Fernet
       # ciphertext for the JSON string '{}'
       post_get = await client.get(f"/api/mcp-sources/{sid}")
       assert post_get.status_code == 200
       assert post_get.json()["secrets"] == {}

       direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
       direct_conn.row_factory = aiosqlite.Row
       try:
           async with direct_conn.execute(
               "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
           ) as cur:
               row = await cur.fetchone()
       finally:
           await direct_conn.close()
       assert row is not None
       assert row["secrets"] != "{}"  # Normalized to ciphertext
       # New key on disk decrypts the normalized ciphertext to '{}'
       new_key = (tmp_path / "test.key").read_bytes()
       assert Fernet(new_key).decrypt(row["secrets"].encode()) == b"{}"

   async def test_rotate_dual_surface_atomicity_on_db_failure(
       self, client: AsyncClient, tmp_path: Path
   ) -> None:
       """A commit failure rolls back BOTH surfaces atomically.

       Populates both an LLM provider AND an MCP source, simulates
       aiosqlite.Connection.commit failure, and asserts that the on-disk
       ciphertext on BOTH surfaces is byte-identical to its pre-rotation
       contents. This is the dual-surface counterpart of the existing
       test_rotate_preserves_key_on_db_failure (LLM-only) and the new
       test_rotate_preserves_mcp_secrets_on_db_failure (MCP-only) —
       proves the single-try / single-commit / single-rollback structure
       rolls back BOTH UPDATE loops together.
       """
       prov_resp = await client.post(
           "/api/providers",
           json={
               "name": "DualFailProv",
               "type": "openai",
               "base_url": "https://api.openai.com/v1",
               "api_key": "sk-dualfailureprovider",
           },
       )
       pid = prov_resp.json()["id"]

       mcp_resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "DualFailMCP",
               "type": "stdio",
               "config": {"command": "x"},
               "secrets": {"K": "dualfailuremcpsecret"},
           },
       )
       sid = mcp_resp.json()["id"]

       # Capture pre-rotation ciphertext for both surfaces
       direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
       direct_conn.row_factory = aiosqlite.Row
       try:
           async with direct_conn.execute(
               "SELECT api_key FROM llm_providers WHERE id = ?", (pid,)
           ) as cur:
               prov_ct_before = (await cur.fetchone())["api_key"]
           async with direct_conn.execute(
               "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
           ) as cur:
               mcp_ct_before = (await cur.fetchone())["secrets"]
       finally:
           await direct_conn.close()

       key_path = tmp_path / "test.key"
       key_before = key_path.read_bytes()

       with (
           patch(
               "aiosqlite.Connection.commit",
               side_effect=RuntimeError("simulated DB failure"),
           ),
           pytest.raises(RuntimeError, match="simulated DB failure"),
       ):
           await client.post("/api/encryption/rotate")

       # (i) Key file untouched
       assert key_path.read_bytes() == key_before

       # (ii) BOTH on-disk ciphertexts byte-identical to pre-rotation
       direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
       direct_conn.row_factory = aiosqlite.Row
       try:
           async with direct_conn.execute(
               "SELECT api_key FROM llm_providers WHERE id = ?", (pid,)
           ) as cur:
               assert (await cur.fetchone())["api_key"] == prov_ct_before
           async with direct_conn.execute(
               "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
           ) as cur:
               assert (await cur.fetchone())["secrets"] == mcp_ct_before
       finally:
           await direct_conn.close()

       # (iii) Cached encryptor still decrypts both surfaces (proves
       # install_key was NOT called — masked tail equality round-trips
       # through the cached encryptor)
       prov_get = await client.get(f"/api/providers/{pid}")
       assert prov_get.json()["api_key"] == "***...ider"
       mcp_get = await client.get(f"/api/mcp-sources/{sid}")
       assert mcp_get.json()["secrets"]["K"] == "***...cret"
   ```

10. **Run the test suite**:

    ```
    pytest tests/test_provider_api.py::TestEncryptionRotation -v --timeout=60
    pytest tests/ --tb=short -q --timeout=60
    ```

    Expected: 4 existing + 5 new rotation tests green; full suite green (~1099 tests).

11. **Update the flight log** at `flight-log.md` with `### 04-rotation-extension` entry: status `landed`, started/completed timestamps, "Changes Made" listing the api.py + test_provider_api.py edits, "Notes" entry confirming the all-in-memory invariant and the migration-residue normalization side-effect.

12. **Set leg status to `landed`** in this leg's frontmatter.

13. **Do NOT commit**. Per agentic-workflow protocol commit happens at flight end.

14. **Signal `[HANDOFF:review-needed]`** when complete.

## Edge Cases

- **Empty MCP table**: `SELECT id, secrets FROM mcp_sources` returns zero rows; `decrypted_mcps` is empty; `reencrypted_mcps` is empty; the UPDATE loop iterates zero times. No special handling needed. (Counterpart of the existing `test_rotate_empty_table` for the LLM surface.)
- **MCP rows with `secrets=NULL`** (theoretically possible if a future migration loosens the NOT-NULL/default contract): the `if not ciphertext` guard at decrypt time treats NULL as empty `{}`. Re-encryption then writes proper ciphertext for `'{}'` to the row — same normalization as the migration-residue case.
- **MCP rows with proper ciphertext for empty `{}`**: `Fernet.decrypt` succeeds, `json.loads` yields `{}`, re-encrypt writes new ciphertext for `'{}'`. Idempotent — round-trip behavior unchanged.
- **MCP rows with proper ciphertext for non-empty secrets**: `Fernet.decrypt` succeeds, `json.loads` yields the dict, re-encrypt writes new ciphertext for the same dict. Round-trip preserves the dict identity.
- **Real corruption (proper ciphertext but invalid JSON)**: `Fernet.decrypt` succeeds, `json.loads` raises `JSONDecodeError`. We do NOT swallow this — it propagates out of the rotation endpoint and the `try:` block's `except Exception: rollback` catches it, rolls back the partial UPDATE work, and re-raises. The on-disk key file is untouched (we haven't reached Step 5 yet). On-disk ciphertext is unchanged (rolled back). Operator sees a 500 with the JSON error. This is correct: real corruption should NOT be silently masked by a rotation pass.
- **Concurrent writes during rotation**: aiosqlite serializes operations on a single connection, and `get_connection` returns a process-wide cached connection. A concurrent `POST /api/mcp-sources` writing during rotation would interleave UPDATEs against the same connection — the awaitable scheduling means the rotation's `commit()` either includes the concurrent write (re-encrypted under the new key, which is correct because the concurrent write used the cached encryptor which still has the OLD key — *wait, that's wrong*: the concurrent write encrypts with the OLD encryptor (cached) but rotation will re-encrypt-with-new-key in its UPDATE loop only if the row was in `decrypted_mcps` at SELECT time). A row created AFTER the SELECT but BEFORE the commit would be OLD-key-encrypted but the new key would be on disk post-`os.replace`. Mitigation: for L4, document this as a known race-condition out of scope (operators should not write during rotation; the API offers no rotation lock); F5/F6 may add a mutex if HAT surfaces issues. **Severity assessment**: low — rotation is operator-triggered, manual, infrequent; concurrent writes during rotation are not a realistic operator workflow.
- **Encryptor without `key_path`** (in-memory encryptor — non-file-backed test fixtures): the existing `if encryptor.key_path is None: raise HTTPException(500, ...)` early-returns before any DB read. Unchanged.

## Files Affected

- `the_one/interfaces/web/api.py` — extended `rotate_encryption_key` (added MCP SELECT, decrypt, re-encrypt, UPDATE within the same single-commit transaction; updated docstring; added `InvalidToken` import)
- `tests/test_provider_api.py` — added 5 tests in `TestEncryptionRotation`: `test_rotate_mcp_source_secrets`, `test_rotate_mixed_providers_and_mcps`, `test_rotate_preserves_mcp_secrets_on_db_failure`, `test_rotate_with_migration_residue_mcp_row`, `test_rotate_dual_surface_atomicity_on_db_failure`
- `missions/07-mcp-integration/flights/01-encrypted-persistence-and-settings/flight-log.md` — `### 04-rotation-extension` entry appended

## State-Machine Reachability Audit

States introduced or affected:
- **Rotation transaction scope** expands from one table (`llm_providers`) to two (`llm_providers` + `mcp_sources`). The transaction-atomicity contract is unchanged in shape; only the row count covered by the single `commit()` grows. Failure path: `except Exception: rollback` rolls back BOTH tables atomically — no partial-rotation state where one surface is on the new key and the other is on the old key.
- **MCP `secrets` column ciphertext** has three possible pre-rotation states post-L2: (a) proper Fernet ciphertext for non-empty secrets, (b) proper Fernet ciphertext for empty `{}`, (c) plaintext `'{}'` (migration-residue). All three transition post-rotation to "proper Fernet ciphertext under the new key". State (c) is the migration-residue normalization side-effect — desirable.
- **Encryptor cache state**: `encryptor.install_key(new_key)` happens AFTER `os.replace`. The reference-not-copy invariant on both `LLMProviderRepository.encryptor` (`repositories.py:489`) and `MCPSourceRepository.encryptor` (`repositories.py:251-253`) means subsequent reads on either surface see the new key automatically. No L4 code change to either repository.

Tests that pin pre-L4 state and would contradict L4:
- `test_rotate_key`, `test_rotate_empty_table`, `test_rotate_multiple_providers`, `test_rotate_preserves_key_on_db_failure` — all four LLM-only rotation tests. L4 must not break any of them. The MCP additions are STRICTLY ADDITIVE in the rotation function: a SELECT that's a no-op on empty MCP tables, an UPDATE loop that's a no-op on empty `decrypted_mcps`. The four existing tests run with `mcp_sources` empty (the test fixture's DB is fresh per-test) — they continue to pass.

L3 introduced the `secrets={}` baseline assertion in `test_crud` (`tests/test_db_api.py`) — L4 doesn't touch that path. The three new MCP-touching tests in `TestEncryptionRotation` POST through `/api/mcp-sources`, which exercises the L3 endpoint surface as a transitive dependency. If L3 regressed (e.g., POST validation rejected `config={"command": "x"}`), these new tests would fail before reaching the rotation. Acceptable — the L3 surface is locked by L3's own tests.

No FK behaviors to audit (rotation is intra-table). No application caches in L4 (the rotation function reads fresh from the DB each call; the encryptor cache is the only state and its install-after-commit ordering is unchanged).

## Cache Freshness Contract

- L4 introduces no new caches. The single existing cache is `_encryptor` in `the_one.encryption` (process-global, file-backed). Its post-rotation freshness contract is unchanged: `install_key(new_key)` mutates the cached `_fernet` in place AFTER the new key bytes are on disk. Live repository instances (which hold the encryptor by reference) see the new key on the next decrypt call.

## Citation Audit

Citations re-verified against current code at design time. Implementer should re-grep before edits because rotation lives downstream of the L3 MCP block and L3's helper-and-endpoint additions may have shifted lines further than expected.

- `the_one/interfaces/web/api.py::rotate_encryption_key` — anchor by symbol; current location ~lines 1292–1356 (pre-L3) — re-verify by grep at edit time.
- `the_one/db/repositories.py::MCPSourceRepository._ciphertext_to_secrets` (lines 258–280) — tolerant-decode pattern reference; OK.
- `the_one/db/repositories.py::MCPSourceRepository._secrets_to_ciphertext` (lines 255–256) — encrypt-side reference; OK.
- `the_one/db/repositories.py::MCPSourceRepository.__init__` (lines 249–253) — reference-not-copy invariant; OK.
- `the_one/db/repositories.py::LLMProviderRepository.__init__` (lines 525–530; the `self.encryptor = encryptor` line is at 530) — reference-not-copy mirror citation. **Correction**: an earlier draft cited `repositories.py:489`, which was stale; verified post-design-review against the current file via `grep -n "self.encryptor = encryptor" the_one/db/repositories.py` (matches at lines 251 and 530).
- `tests/test_provider_api.py::TestEncryptionRotation` (lines 495–611) — class header at 495; tests at 496/519/525/548; OK.
- `tests/test_provider_api.py` `client` fixture at lines 55–81 (extended in L2 to patch `get_encryptor`) — OK.
- `the_one/db/schema.py` v8 docstring — canonical source of "no non-DML mid-transaction" rule; OK.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] `pytest tests/test_provider_api.py::TestEncryptionRotation -v --timeout=60` green (4 existing + 5 new = 9 tests)
- [x] `pytest tests/ --tb=short -q --timeout=60` green
- [x] Code-review: rotation function contains zero `PRAGMA`, `CREATE`, `BEGIN`, or DDL statements between first SELECT and `commit()`
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed` (frontmatter line 3)
- [ ] Do NOT check off this leg in flight.md (commit at flight end)
- [ ] Do NOT commit
