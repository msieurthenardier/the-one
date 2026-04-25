# Leg: key-rotation-atomicity

**Status**: completed
**Flight**: [Resilience & Verification](../flight.md)

## Objective

Make encryption-key rotation crash-safe by re-encrypting and committing DB rows *before* persisting the new key file, and by writing the new key via a temp-file + `os.replace` atomic rename — so no failure mode leaves DB ciphertext readable only with a key that is no longer on disk.

## Context

Flight 05 design decision **"Key rotation: temp-file + atomic rename"** specifies this approach. The current API handler at `the_one/interfaces/web/api.py:701-729` has a data-loss window:

1. It calls `Encryptor.rotate_key(callback)` (line 720), which **writes the new key file** as soon as the callback returns successfully.
2. *Then* it executes `UPDATE llm_providers SET api_key = ?` and `conn.commit()` (lines 723-728).

If the UPDATE/commit fails after step 1, the DB still contains ciphertext encrypted with the **old** key, but the key file already holds the **new** key — data loss.

The fix: the API handler bypasses `Encryptor.rotate_key()` entirely and manages the rotation sequence itself, so the key file is the *last* thing to change.

The existing `Encryptor.rotate_key()` method and its sync tests in `tests/test_encryption.py` (`TestKeyRotation`, 6 tests, plus `test_rotation_propagates_through_cache`) remain unchanged — they cover non-API callers.

## Inputs

What exists before this leg:

- `the_one/encryption.py` — `Encryptor` class with `_fernet`, `_key`, `_key_path` attributes; existing `rotate_key()` callback-based method
- `the_one/interfaces/web/api.py:701-729` — `rotate_encryption_key()` handler using the unsafe ordering described above
- `tests/test_encryption.py` — 11 tests, all passing on `main` at `0005128`
- `tests/test_provider_api.py:249-300` — 3 rotation tests (`test_rotate_key`, `test_rotate_empty_table`, `test_rotate_multiple_providers`) using a test fixture that builds an `Encryptor` with its own `key_path`

## Outputs

What exists after this leg completes:

- `the_one/interfaces/web/api.py` — `rotate_encryption_key()` rewritten to follow the crash-safe order: generate new key in memory → re-encrypt all rows → DB commit → temp-file write → `os.replace` → mutate cached `Encryptor`
- `the_one/encryption.py` — small additive helper `Encryptor.install_key(new_key)` that updates `_fernet` and `_key` in place (so the cached encryptor reflects the new key after the API handler's atomic rename succeeds), plus a public read-only `key_path` property. Existing `rotate_key()` continues to work unchanged but becomes effectively dead code on the production path (only exercised by `tests/test_encryption.py`); deliberately not deprecated to keep this leg's diff small.
- `tests/test_provider_api.py` — new test that simulates DB-commit failure mid-rotation and asserts the key file, cached encryptor state, and on-disk ciphertext are all unchanged
- `the_one/agents.md` — one-line update to reflect that the API rotation path no longer flows through `Encryptor.rotate_key`
- All tests previously passing on `main` (the 317 collected tests, excluding the 2 known pre-existing collection errors) still pass

## Acceptance Criteria

- [x] `Encryptor.install_key(new_key: bytes)` exists, updates `_fernet` and `_key` in place, and is documented with a one-line docstring
- [x] `Encryptor.key_path` property exists (public, read-only, returns `Path | None`) so the API handler does not access `_key_path` directly
- [x] `rotate_encryption_key()` no longer calls `Encryptor.rotate_key`; instead it (a) decrypts existing rows with the current encryptor, (b) constructs a new `Fernet` key + new `Encryptor` in memory, (c) re-encrypts all rows, (d) `await conn.commit()`, (e) writes the new key to a temp file in the same directory as `key_path`, (f) calls `os.replace(tmp, key_path)`, (g) calls `cached_encryptor.install_key(new_key)`
- [x] `the_one/interfaces/web/api.py` has top-level imports for `os`, `secrets`, and `from cryptography.fernet import Fernet` (none of these exist on `main` at `0005128` — the implementer must add all three)
- [x] The temp file is created with mode `0o600` from creation via `os.open(path, O_WRONLY | O_CREAT | O_EXCL, 0o600)` (do NOT use `Path.write_bytes` then `chmod` — there is a brief window where the file is world-readable)
- [x] The temp filename is in the same directory as `key_path` (so `os.replace` is atomic on a single filesystem) and uses the production key filename as a prefix, e.g. `f"{key_path.name}.tmp.{secrets.token_hex(4)}"`
- [x] `os.fsync(fd)` is called on the temp file before the `finally`/close, so the new key bytes hit disk before the rename
- [x] If the DB `commit()` raises, the on-disk key file is **byte-for-byte identical** to its pre-rotation contents, the cached `Encryptor` still decrypts pre-rotation ciphertext, and the on-disk ciphertext for an existing provider row is decryptable with the *pre-rotation* key bytes (verified by a test that snapshots the key file before rotation and re-decrypts using `Fernet(key_before)`)
- [x] All previously-passing tests (the 317 currently collected, excluding the 2 known pre-existing collection errors in `tests/test_tool_registry.py` and `workspace/test_agent.py`) still pass
- [x] A new test in `tests/test_provider_api.py` (`TestEncryptionRotation.test_rotate_preserves_key_on_db_failure` or similar) injects a failure during DB commit by patching `aiosqlite.Connection.commit` (NOT `aiosqlite.core.Connection.commit` — the former is a re-export of the same class object, and `aiosqlite.Connection` is the canonical name) and asserts: (i) endpoint returns 5xx, (ii) the key file on disk equals `key_before`, (iii) `Fernet(key_before).decrypt(...)` on the row's ciphertext returns the original plaintext, (iv) a subsequent GET still returns the correct masked api_key suffix — note (i) deviation: the fixture's ASGITransport uses `raise_app_exceptions=True`, so the simulated `RuntimeError` propagates out of `client.post` rather than surfacing as a 500 response; the test asserts the propagation via `pytest.raises(RuntimeError)`. The underlying invariant (failure is surfaced and rotation is half-undone safely) is unchanged.
- [x] Orphaned temp files from a *write* failure (e.g. fsync error after `os.open` succeeded) are an explicitly accepted edge case — no cleanup code required, but the choice is recorded in the flight log so a future operator knows what stale `*.key.tmp.*` files mean
- [x] (Successful rotations leave no temp files — guaranteed by `os.replace` semantics; no extra test assertion needed)
- [x] `ruff check` and `ruff format --check` are clean for `the_one/encryption.py`, `the_one/interfaces/web/api.py`, and `tests/test_provider_api.py`

## Verification Steps

- `pytest tests/test_encryption.py -v` — all 11 tests pass (unchanged behavior for `rotate_key`)
- `pytest tests/test_provider_api.py::TestEncryptionRotation -v` — all rotation tests pass, including the new failure-injection test
- `pytest -q` — full suite passes (modulo the 2 known pre-existing collection errors in `tests/test_tool_registry.py` and `workspace/test_agent.py`, which Leg 04 will fix)
- `ruff check the_one/encryption.py the_one/interfaces/web/api.py tests/test_provider_api.py`
- Manual smoke (optional): start the app, create one provider with an API key, hit `POST /api/encryption/rotate`, verify the key still works via `GET /api/providers/{id}` (masked tail visible)

## Implementation Guidance

1. **Add `Encryptor.install_key` and `Encryptor.key_path`** in `the_one/encryption.py`
   - `install_key`:
     - Signature: `def install_key(self, new_key: bytes) -> None:`
     - Body: `self._fernet = Fernet(new_key); self._key = new_key`
     - Docstring: one line — "Replace the in-memory Fernet key without touching disk. Caller is responsible for ensuring the key file already reflects this key."
     - Do NOT touch `_key_path` — the file location does not change.
   - `key_path`:
     - `@property` returning `Path | None`, body `return self._key_path`
     - Docstring: one line — "Return the on-disk key file path, or None if this Encryptor is not file-backed."
   - Both go on the `Encryptor` class, near the existing `rotate_key` method. Do not modify `rotate_key` itself.

2. **Rewrite `rotate_encryption_key()`** in `the_one/interfaces/web/api.py`
   - Strategy below. Keep the docstring style and import patterns consistent with the rest of the file.
   - Order of operations (this is load-bearing — do not reorder):
     ```python
     encryptor = get_encryptor(settings.data_dir)
     conn = await get_connection()

     # 1. Decrypt existing rows with the current encryptor
     async with conn.execute(
         "SELECT id, api_key FROM llm_providers WHERE api_key IS NOT NULL AND api_key != ''"
     ) as cur:
         rows = await cur.fetchall()
     decrypted = [(row["id"], encryptor.decrypt(row["api_key"])) for row in rows]

     # 2. Generate a new key + Encryptor in memory only
     new_key = Fernet.generate_key()
     new_encryptor = Encryptor(new_key)

     # 3. Re-encrypt every row using the new encryptor
     reencrypted = [(pid, new_encryptor.encrypt(pt)) for pid, pt in decrypted]

     # 4. Write all rows in a single transaction and commit
     for pid, ct in reencrypted:
         await conn.execute(
             "UPDATE llm_providers SET api_key = ? WHERE id = ?",
             (ct, pid),
         )
     await conn.commit()

     # 5. Persist the new key to a temp file in the same directory
     key_path = encryptor.key_path
     if key_path is None:
         raise HTTPException(status_code=500, detail="encryptor not file-backed")
     tmp_path = key_path.with_name(f"{key_path.name}.tmp.{secrets.token_hex(4)}")
     # 0o600 from creation — Path.write_bytes + chmod has a world-readable window
     fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
     try:
         os.write(fd, new_key)
         os.fsync(fd)
     finally:
         os.close(fd)

     # 6. Atomic rename — after this point, the new key is canonical
     os.replace(str(tmp_path), str(key_path))

     # 7. Update the cached encryptor so subsequent requests use the new key
     encryptor.install_key(new_key)

     return {"status": "ok"}
     ```
   - **Required new top-level imports** in `api.py` (none of these are present on `main` — verified): `import os`, `import secrets`, `from cryptography.fernet import Fernet`. `HTTPException` is already imported on line 12 — no new fastapi import needed.
   - Use the new `encryptor.key_path` property (added in step 1) — do not access `_key_path` directly.

3. **Add the failure-injection test** in `tests/test_provider_api.py::TestEncryptionRotation`
   - **Fixture facts** (verified in design review — do not re-derive):
     - The `client` fixture (`tests/test_provider_api.py:36-63`) creates `key_path = tmp_path / "test.key"`, writes a fresh `Fernet.generate_key()` to it, and constructs `test_encryptor = Encryptor(test_key, key_path=key_path)`.
     - It then patches both `the_one.interfaces.web.api.get_connection` and `the_one.interfaces.web.api.get_encryptor` to return that `test_encryptor`/test connection for the lifetime of the test.
     - Because `get_encryptor` is patched to return the *same instance* for every call, `encryptor.install_key(new_key)` mutates the object subsequent requests will see — the new failure test does NOT need to worry about cache plumbing.
   - **Patch target**: use `aiosqlite.Connection.commit`. `aiosqlite.Connection` is the same class object as `aiosqlite.core.Connection` (re-export); both work.
   - Test outline:
     ```python
     async def test_rotate_preserves_key_on_db_failure(
         self, client: AsyncClient, tmp_path: Path
     ) -> None:
         """If DB commit fails mid-rotation, the key file, cached encryptor, and on-disk ciphertext must all be unchanged."""
         create_resp = await client.post(
             "/api/providers",
             json={
                 "name": "FailureTest",
                 "type": "openai",
                 "base_url": "https://api.openai.com/v1",
                 "api_key": "sk-failuretest9999",
             },
         )
         assert create_resp.status_code == 200
         provider_id = create_resp.json()["id"]

         key_path = tmp_path / "test.key"
         key_before = key_path.read_bytes()

         with patch("aiosqlite.Connection.commit", side_effect=RuntimeError("simulated DB failure")):
             resp = await client.post("/api/encryption/rotate")
         assert resp.status_code >= 500

         # (i) Key file byte-identical
         assert key_path.read_bytes() == key_before

         # (ii) Masked tail still works (exercises the cached encryptor's decrypt path)
         get_resp = await client.get(f"/api/providers/{provider_id}")
         assert get_resp.status_code == 200
         assert get_resp.json()["api_key"] == "***...9999"

         # (iii) Direct decrypt with the pre-rotation key bytes succeeds — this catches
         #      a regression where the cached _fernet was mutated before commit failed.
         #      Open a fresh connection to the test DB; Fernet is already imported at module top.
         direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
         direct_conn.row_factory = aiosqlite.Row
         try:
             async with direct_conn.execute(
                 "SELECT api_key FROM llm_providers WHERE id = ?", (provider_id,)
             ) as cur:
                 row = await cur.fetchone()
         finally:
             await direct_conn.close()
         assert Fernet(key_before).decrypt(row["api_key"].encode()).decode() == "sk-failuretest9999"
     ```
   - The fixture (lines 36-63) closes its `conn` after `yield`, so the test cannot reuse the fixture's connection. Opening a fresh `aiosqlite.connect(str(tmp_path / "test.db"))` is the cleanest path — the test DB file persists for the duration of `tmp_path`. `aiosqlite` and `Fernet` are already imported at the top of the test file (lines 9 and 11) — no new imports needed for this test.

4. **Run the suite** — `pytest tests/test_encryption.py tests/test_provider_api.py -v` first (fast feedback), then full `pytest -q`.

5. **Update flight log** — add a Leg Progress entry for `key-rotation-atomicity` with status `landed` and a summary. Two Decisions to record explicitly under the `## Decisions` section so future audits can find them in one place:
   - **Orphan policy on write failure**: temp files left by a write failure (post-`os.open`, pre-`os.replace`) are not cleaned up. Future operators may safely delete `*.key.tmp.*` siblings of `encryption.key`.
   - **API path no longer flows through `Encryptor.rotate_key`**: the public `rotate_key` method remains in place (still tested by `test_encryption.py`) but is no longer called by production code; if a future flight wants to remove it, that's the entry point.
   Do NOT commit.

## Edge Cases

- **No rows to rotate (empty `llm_providers`)**: `decrypted` is `[]`, `reencrypted` is `[]`, the UPDATE loop is a no-op, `commit()` still runs (committing nothing), and the key file is still rotated. The existing `test_rotate_empty_table` covers this — make sure it still passes.
- **Rows with `api_key = NULL` or `''`**: already filtered by the `WHERE` clause. No special handling.
- **Concurrent rotation request**: not addressed by this leg — out of scope. Add a note to the flight log if you want to flag it for a future leg, but don't add a lock.
- **Filesystem out of space mid-temp-write**: `os.write` raises, the `finally` closes the fd, the temp file is left behind on disk (orphaned). Acceptable — operator can clean up. Optionally add a `try/except` around steps 5-6 that unlinks the temp file on failure; if you do, document the choice in the flight log.
- **`os.replace` failure after DB commit succeeded**: documented in the flight design decision as an accepted edge case — manual recovery via locating the temp file and renaming it. Do not add code for this.
- **Cached encryptor not updated**: if step 7 is skipped, subsequent requests will fail to decrypt because the cached `Encryptor` still holds the old key but the file holds the new key. Step 7 is mandatory. The `test_rotation_propagates_through_cache` test in `test_encryption.py` covers the existing `rotate_key` path; the new API path needs equivalent coverage — the `test_rotate_key` integration test already verifies post-rotation reads work, so this is implicitly covered.

## Files Affected

- `the_one/encryption.py` — add `install_key` method and `key_path` property
- `the_one/interfaces/web/api.py` — add three top-level imports (`os`, `secrets`, `Fernet`); rewrite `rotate_encryption_key()` (lines 701-729)
- `tests/test_provider_api.py` — add failure-injection test in `TestEncryptionRotation`
- `the_one/agents.md` — update the one line that describes `Encryptor.rotate_key` as "re-encrypts all provider credentials in a single transaction"; the API path no longer flows through `rotate_key`. One-line edit only — do not restructure the doc.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`pytest tests/test_encryption.py tests/test_provider_api.py -v` green)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off the leg in flight.md yet — that happens at flight commit
- [x] Do NOT commit — Mission Control batches review and commit at end of flight
