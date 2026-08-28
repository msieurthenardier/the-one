# Squawk 0022: Admin System page shows the success flash for a `key_file: "staged"` rotation

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: —

## Report

`POST /api/encryption/rotate` now returns `{"status": "ok", "key_file": "promoted" | "staged"}`.
`"staged"` means the DB and in-memory key rotated but the on-disk key file could not be
promoted (the `.next` sidecar stays and the next start reconciles it). The System page
ignores the field and shows "Encryption key rotated successfully." for both. Reproduce: make
the promote `os.replace` fail (read-only data dir) and click Rotate. Expected: a warning
flash that names the staged state.

## Evidence

- `the_one/interfaces/web/static/js/areas/admin/system-page.js:85-96` — `fetch('/api/encryption/rotate')` → `.then(function () { … flashEl.textContent = 'Encryption key rotated successfully.'; … })`, response body unused
- `the_one/interfaces/web/api.py:rotate_encryption_key` — `key_file = "staged"` branch with `logger.exception`

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
