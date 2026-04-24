# Leg: encryption-module

**Status**: completed
**Flight**: [Provider Data Model & Persistence](../flight.md)

## Objective

Create `the_one/encryption.py` with Fernet-based encryption for storing API credentials at rest. The module auto-generates a key file on first use, provides encrypt/decrypt helpers, and supports key rotation with re-encryption of existing secrets.

## Context

- Flight design decision: encryption uses Fernet from the `cryptography` package, key stored at `{data_dir}/encryption.key` (file mode 0600), auto-generated on first access
- This is the first leg — no prior legs or flight log entries
- The `cryptography` package is not yet in `pyproject.toml` — this leg adds it
- The module lives at `the_one/encryption.py` (top-level, not under `db/`) per architect review
- Empty/None API keys should not be encrypted — pass through as-is

## Inputs

What exists before this leg runs:
- `the_one/config.py` with `settings.data_dir` (Path to `~/.the-one`)
- `pyproject.toml` with current dependencies (no `cryptography`)
- Existing test infrastructure in `tests/` with pytest-asyncio

## Outputs

What exists after this leg completes:
- `the_one/encryption.py` — encryption module with key management and encrypt/decrypt functions
- `cryptography>=43.0` added to `pyproject.toml` core dependencies
- `tests/test_encryption.py` — unit tests for the module
- Package installed with new dependency (`pip install -e ".[all-llms,dev]"`)

## Acceptance Criteria

- [x] `the_one/encryption.py` exists with the following public API:
  - `get_encryptor(data_dir: Path) -> Encryptor` — returns an Encryptor instance, auto-generating the key file if it doesn't exist
  - `Encryptor.encrypt(plaintext: str) -> str` — returns a Fernet-encrypted, base64-encoded string
  - `Encryptor.decrypt(ciphertext: str) -> str` — returns the original plaintext
  - `Encryptor.encrypt_optional(value: str | None) -> str | None` — pass-through for None/empty, encrypt otherwise
  - `Encryptor.decrypt_optional(value: str | None) -> str | None` — pass-through for None/empty, decrypt otherwise
  - `Encryptor.rotate_key(reencrypt: callable) -> None` — generates a new key, calls the provided callback to re-encrypt secrets, replaces the key file
- [x] Key file is created at `{data_dir}/encryption.key` with file permissions 0600
- [x] Key file is not recreated if it already exists
- [x] Encrypt/decrypt round-trips produce the original value
- [x] `encrypt_optional(None)` returns `None`; `encrypt_optional("")` returns `""`
- [x] Key rotation generates a new key that differs from the old key
- [x] Key rotation calls the reencrypt callback with both old and new Encryptor instances
- [x] `cryptography>=43.0` is listed in `pyproject.toml` core dependencies
- [x] `ruff check the_one/encryption.py tests/test_encryption.py` passes
- [x] `pytest tests/test_encryption.py` passes

## Verification Steps

- `python -c "from the_one.encryption import get_encryptor; print('import ok')"` — no import error
- `ruff check the_one/encryption.py tests/test_encryption.py` — no lint errors
- `pytest tests/test_encryption.py -v` — all tests pass
- Inspect `the_one/encryption.py` — confirm public API matches acceptance criteria

## Implementation Guidance

1. **Add `cryptography` to `pyproject.toml`**
   - Add `"cryptography>=43.0"` to the `dependencies` list in `[project]`
   - Run `pip install -e ".[all-llms,dev]"` to install

2. **Create `the_one/encryption.py`**
   - Import `Fernet` from `cryptography.fernet`
   - Import `Path` and `os` for file operations

3. **Implement the `Encryptor` class**
   ```python
   class Encryptor:
       def __init__(self, key: bytes, key_path: Path | None = None):
           self._fernet = Fernet(key)
           self._key_path = key_path

       def encrypt(self, plaintext: str) -> str:
           return self._fernet.encrypt(plaintext.encode()).decode()

       def decrypt(self, ciphertext: str) -> str:
           return self._fernet.decrypt(ciphertext.encode()).decode()

       def encrypt_optional(self, value: str | None) -> str | None:
           if not value:
               return value
           return self.encrypt(value)

       def decrypt_optional(self, value: str | None) -> str | None:
           if not value:
               return value
           return self.decrypt(value)
   ```

4. **Implement `get_encryptor(data_dir: Path) -> Encryptor`**
   - Key file path: `data_dir / "encryption.key"`
   - If key file exists: read and use it
   - If not: generate with `Fernet.generate_key()`, write to file, set `os.chmod(path, 0o600)`
   - Return `Encryptor(key, key_path=key_file_path)`

5. **Implement `rotate_key` on Encryptor**
   - The `rotate_key` method accepts a callback `reencrypt: Callable[[Encryptor, Encryptor], None]` where the callback receives `(old_encryptor, new_encryptor)`
   - Generate new key with `Fernet.generate_key()`
   - Create new Encryptor with the new key
   - Call `reencrypt(self, new_encryptor)` — the caller is responsible for re-encrypting all stored secrets
   - After callback succeeds, overwrite the key file with the new key
   - Update `self._fernet` to use the new key
   - The key file path is needed — store it on the Encryptor instance or pass `data_dir` to `rotate_key`

   Design note: `_key_path` is set at construction time by `get_encryptor`. If `_key_path` is None (e.g., test-only Encryptor), `rotate_key` should raise an error.

   **Atomicity note for downstream legs**: If the reencrypt callback partially completes (e.g., re-encrypts 3 of 5 rows then fails), the old key is preserved but the DB may have a mix of old-key and new-key encrypted values. The caller (repository layer in leg 03/04) is responsible for wrapping re-encryption in a DB transaction so partial failures roll back.

6. **Create `tests/test_encryption.py`**
   - Use `tmp_path` fixture for isolated key file testing
   - Test: `get_encryptor` creates key file with correct permissions
   - Test: `get_encryptor` reuses existing key file
   - Test: encrypt/decrypt round-trip
   - Test: `encrypt_optional(None)` returns `None`
   - Test: `encrypt_optional("")` returns `""`
   - Test: key rotation generates different key
   - Test: key rotation calls reencrypt callback with old and new encryptors
   - Test: after rotation, new encryptor can decrypt values encrypted with new key
   - Test: after rotation, old encrypted values cannot be decrypted with new key (verifying rotation actually changed the key)

## Edge Cases

- **Permission errors on key file creation**: Let the OS error propagate — `data_dir` should already be writable (ensured by `settings.ensure_dirs()`)
- **Corrupt key file**: Fernet raises `ValueError` on invalid key — let it propagate with a clear error
- **Concurrent access**: Single-user system, no locking needed
- **Windows compatibility**: `os.chmod` with 0o600 is a no-op on Windows but doesn't error. Acceptable since the primary target is Linux/Docker.

## Files Affected

- `pyproject.toml` — add `cryptography>=43.0` to dependencies
- `the_one/encryption.py` — new file (encryption module)
- `tests/test_encryption.py` — new file (unit tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
