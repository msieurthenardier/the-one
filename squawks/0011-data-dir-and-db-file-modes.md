# Squawk 0011: SQLite database and data directory are created world-readable; `encryption.key` has a write-then-chmod window

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

The operator credential (`api-credential`) and the Fernet key (`encryption.key`) are
`0600`, but the SQLite database — which holds chat history, agent system prompts,
revision logs and every Fernet ciphertext — is created with the process umask
(`0644` observed), its `-wal`/`-shm` siblings likewise, and the data directory is
`0755`. Any other local OS account can read the database directly off disk, bypassing
the entire Mission 20 HTTP/WS credential gate. This is GitHub issue #169 (open since
2026-08-08), re-confirmed by the 2026-08-27 maintenance inspection (S2). The same
inspection re-confirmed the Mission 20 debrief's note that `encryption.py` writes the
key with `write_bytes()` *then* `chmod(0o600)` — a brief world-readable window that
`api_credential.py` deliberately avoids with an `O_CREAT|O_EXCL, 0o600` open (S3).

Fix, one at-rest-permissions pass: create the data directory `0700` and the database
file `0600` before first write (mirror `api_credential`'s no-window pattern), reconcile
`-wal`/`-shm` after `PRAGMA journal_mode=WAL` activates, and port the atomic
`O_CREAT|O_EXCL` write into `encryption.py` for both first-key and rotation. On Windows
`os.chmod` is a no-op against ACLs; protection there comes from `%LOCALAPPDATA%`
user-profile ACL inheritance, exactly as the two existing `0600` secrets already rely
on — add one line to `SECURITY-MODEL.md` recording that, and close #169.

## Evidence

- `the_one/db/connection.py:16-17` — `settings.ensure_dirs()` then
  `_connection = await aiosqlite.connect(str(settings.db_path))` — no mode handling
  anywhere in `the_one/db/` (`grep -rn chmod the_one/db/` is empty).
- `the_one/config.py:108` `Settings.ensure_dirs` — bare `mkdir`, no `mode=`.
- `the_one/encryption.py:77-78` (rotate) and `:103-104` (first key) —
  `write_bytes(...)` followed by `os.chmod(..., 0o600)`.
- `the_one/api_credential.py:159` `_write_new_credential_atomic` — the `O_EXCL`
  + `0o600` pattern to port; its docstring (`:17`) names the write-then-chmod pattern
  as the anti-pattern it avoids.
- Live data dir (2026-08-27): `the-one.db` / `-wal` / `-shm` `0644`, directory `0755`,
  `api-credential` and `encryption.key` `0600`.

## Corrective Action

- `the_one/config.py:Settings.ensure_dirs` — `data_dir.mkdir(...)` now passes
  `mode=0o700`, and an unconditional `os.chmod(self.data_dir, 0o700)` follows
  it (only the data dir itself, never its parents), because `mkdir`'s `mode`
  argument is only honored on creation (and is still subject to umask) — the
  `chmod` is what tightens a pre-fix install's existing `0o755` dir on the
  next startup.
- `the_one/db/connection.py:get_connection` — new `_create_or_tighten_db_file`
  helper opens the DB path with `os.open(path, O_CREAT | O_RDWR, 0o600)` (no
  `O_EXCL`, since a pre-existing DB must be reused, not replaced) before
  `aiosqlite.connect`, then explicitly `os.chmod`s it to `0o600` — closing
  both the umask window for a fresh DB and tightening an existing `0o644`
  one. A new `_tighten_wal_shm_modes` helper runs after
  `PRAGMA journal_mode=WAL` and chmods `-wal`/`-shm` to `0o600` if present.
  In practice SQLite copies the main DB file's mode bits onto `-wal`/`-shm`
  it creates during a later write (verified empirically — spawned sidecars
  came out `0o600` once the main file was `0o600`, independent of the
  process umask), so the explicit reconcile call mainly matters for
  leftover `0o644` sidecars from a pre-fix install.
- `the_one/encryption.py` — added `_write_key_atomic(path, key)`, mirroring
  `the_one/api_credential.py:_write_new_credential_atomic`: a uniquely-named
  sibling temp file opened with `O_CREAT | O_EXCL, 0o600`, written, fsynced,
  closed, then `os.replace`d onto the canonical path. Both `get_encryptor`'s
  first-key branch and `Encryptor.rotate_key` now call this instead of
  `write_bytes()` + `os.chmod()`. Rotation's ordering relative to the DB
  commit (re-encrypt callback succeeds, *then* persist) is unchanged — only
  the on-disk write mechanism changed.
- `SECURITY-MODEL.md` "Secrets" — added a bullet recording the data dir
  (`0o700`) and DB/`-wal`/`-shm` (`0o600`) modes, GH #169, and the Windows
  `os.chmod`-is-a-no-op / `%LOCALAPPDATA%` ACL-inheritance posture, matching
  the existing `api-credential` and `encryption.key` bullets.
- Updated `tests/test_api_credential.py::test_creation_uses_o_excl_and_never_chmods`:
  it monkeypatches the shared `os` module (not a namespaced import), so it
  was observing every `os.chmod` call process-wide, not just calls against
  the credential path. `get_credential()` calls `settings.ensure_dirs()`,
  which now legitimately chmods the data directory — updated the assertion
  from "chmod is never called" to "chmod is never called on the credential
  path, and the data-dir chmod is the only other call", rather than loosening
  the original intent (no world-readable window on the credential file).

## Verification

Added tests (all skip mode assertions on `os.name == "nt"` via
`pytest.mark.skipif`):
- `tests/test_config_data_dir.py`: `test_ensure_dirs_creates_data_dir_0700`,
  `test_ensure_dirs_tightens_existing_0755_data_dir`.
- `tests/test_db_connection.py`: `test_db_file_permissions`,
  `test_new_wal_shm_sidecars_inherit_0600` (write-triggered sidecar
  creation, confirming the mode-inheritance behavior above),
  `test_tightens_existing_0644_wal_shm_sidecars`,
  `test_tightens_existing_0644_db_file`.
- `tests/test_encryption.py`: `test_write_key_atomic_no_temp_file_left_behind`
  (asserts the canonical file lands at `0o600` and no `.tmp.*` sibling
  survives), `test_rotated_key_file_permissions`. The pre-existing
  `test_key_file_permissions` continues to cover first-key creation and
  needed no change.

Ran (all pass):
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_config.py
  tests/test_db_migration.py tests/test_db_repositories.py
  tests/test_api_credential.py tests/test_plan_credentials.py
  tests/test_api_secret_mask_roundtrip.py tests/test_lifespan.py
  tests/test_config_data_dir.py tests/test_db_connection.py
  tests/test_encryption.py tests/test_db_api.py --timeout 90` — 663 passed.
- `make lint` — all checks passed.
- `make format-check` — 441 files already formatted (no changes needed).

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `squawk/turnaround-2026-08-27` — PR pending (sha recorded on close)
