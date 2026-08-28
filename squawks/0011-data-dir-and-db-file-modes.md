# Squawk 0011: SQLite database and data directory are created world-readable; `encryption.key` has a write-then-chmod window

**Status**: open
**Type**: defect
**Severity**: grounding
**Reported**: 2026-08-27
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion — a test opening a fresh data dir and asserting directory
`0700`, DB + WAL/SHM `0600`, and key file `0600` with no intermediate mode; skip the
mode assertions on Windows)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
