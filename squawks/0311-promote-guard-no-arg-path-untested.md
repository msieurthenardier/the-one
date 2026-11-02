# Squawk 0311: `promote_pending_key`'s key-path guard is tested only with an explicit key

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
Mission 34 Flight 3 added `tests/test_encryption.py::test_promote_without_key_path_raises`, which calls `promote_pending_key(Fernet.generate_key())` on an `Encryptor` with no `key_path`. The no-argument path (promote the staged pending key) is not asserted against the guard. Add a case that stages a key on an instance without a `key_path` (or sets one up so the pending key exists) and calls `promote_pending_key()` with no argument, expecting the "no key_path set" `RuntimeError`, or record why that path cannot be reached (the staging guard may fire first, in which case the existing stage test covers it and the squawk closes with that note).

## Evidence
- `the_one/encryption.py::Encryptor.promote_pending_key(self, key: bytes | None = None)` — "key: The key to promote. Defaults to the currently pending key."
- `tests/test_encryption.py:180` — `enc.promote_pending_key(Fernet.generate_key())` only.
- Mission 34 Flight 3 debrief (Developer interview), Action Items.

## Corrective Action
*(written at completion)*

## Verification
- Either a new test fails when the guard is removed for the no-argument path (falsified by editing, restored by editing), or the squawk records that the no-argument path cannot reach the guard on a key-path-less instance and which test covers it. `make test-unit` passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
