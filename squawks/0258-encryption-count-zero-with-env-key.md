# Squawk 0258: Encryption page shows "0" stored items with an environment-supplied key

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: —

## Report
When the encryption key comes from the environment rather than the key file (`key_path` is `None`), `GET /api/encryption/status` reports `credential_count: 0` without reading the corpora. Settings › Encryption then shows "Items with stored secrets: 0" with no qualifier, which reads as a fact about the data rather than "not counted". Found in the Mission 31 Flight 4 debrief.

## Evidence
- `the_one/interfaces/web/api.py`, the `encryption_status` docstring (about `:6196`): "``credential_count`` is reported as 0, not as a real count."
- `the_one/interfaces/web/static/js/areas/admin/system-page.js:328`: `{ label: 'Items with stored secrets', value: String(data.credential_count) }`.

**Expected:** the page shows "Not counted (key from environment)", or the route returns `null` and the page says so. Add a test for the env-key case.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
