# Squawk 0311: `promote_pending_key`'s key-path guard is tested only with an explicit key

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
Mission 34 Flight 3 added `tests/test_encryption.py::test_promote_without_key_path_raises`, which calls `promote_pending_key(Fernet.generate_key())` on an `Encryptor` with no `key_path`. The no-argument path (promote the staged pending key) is not asserted against the guard. Add a case that stages a key on an instance without a `key_path` (or sets one up so the pending key exists) and calls `promote_pending_key()` with no argument, expecting the "no key_path set" `RuntimeError`, or record why that path cannot be reached (the staging guard may fire first, in which case the existing stage test covers it and the squawk closes with that note).

## Evidence
- `the_one/encryption.py::Encryptor.promote_pending_key(self, key: bytes | None = None)` — "key: The key to promote. Defaults to the currently pending key."
- `tests/test_encryption.py:180` — `enc.promote_pending_key(Fernet.generate_key())` only.
- Mission 34 Flight 3 debrief (Developer interview), Action Items.

## Corrective Action
The no-argument path can reach the guard: `Encryptor.__init__` accepts `pending_key` without a `key_path`, so `promote_pending_key()` passes the "no pending key" check and then hits the "no key_path set" guard (the staging guard is not involved). Added `tests/test_encryption.py::TestPendingKey::test_promote_no_argument_without_key_path_raises`, which builds `Encryptor(key, pending_key=...)` and expects the RuntimeError. Test-only; `the_one/encryption.py` unchanged.

## Verification
- Falsified by editing: with the guard condition replaced by `if False:`, the new test failed (AttributeError in `next_key_path`); restored by editing, `git diff -- the_one/encryption.py` empty. `tests/test_encryption.py` 33 passed; ruff check and format clean; `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped.
- Original criterion: Either a new test fails when the guard is removed for the no-argument path (falsified by editing, restored by editing), or the squawk records that the no-argument path cannot reach the guard on a key-path-less instance and which test covers it. `make test-unit` passes.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.
