# Squawk 0258: Encryption page shows "0" stored items with an environment-supplied key

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: 2026-11-03

## Report
When the encryption key comes from the environment rather than the key file (`key_path` is `None`), `GET /api/encryption/status` reports `credential_count: 0` without reading the corpora. Settings › Encryption then shows "Items with stored secrets: 0" with no qualifier, which reads as a fact about the data rather than "not counted". Found in the Mission 31 Flight 4 debrief.

## Evidence
- `the_one/interfaces/web/api.py`, the `encryption_status` docstring (about `:6196`): "``credential_count`` is reported as 0, not as a real count."
- `the_one/interfaces/web/static/js/areas/admin/system-page.js:328`: `{ label: 'Items with stored secrets', value: String(data.credential_count) }`.

**Expected:** the page shows "Not counted (key from environment)", or the route returns `null` and the page says so. Add a test for the env-key case.

## Corrective Action
Root cause: `encryption_status` skipped `gather_corpora` whenever `encryptor.key_path` was `None`, though decryption only needs the in-memory key. Removed the guard in `the_one/interfaces/web/api.py`, so the count is real for any key source; updated the docstring. Key loading, rotation and the three-field response are untouched. The page wording is unchanged (it now shows a true number), so no browser pin changed. Added `test_an_environment_key_with_no_key_file_still_counts` in `tests/test_encryption_status.py` (an `Encryptor` with `key_path=None`, a stored provider key, expects count 1).

## Verification
`tests/test_encryption_status.py` 14 passed. Falsified: restoring the `key_path is not None` guard made the new test fail; fix put back. `ruff check` / `ruff format --check` clean. `THE_ONE_TEST_NETNS=1 make test-unit`: 8727 passed, 15 skipped. No static JS changed, so no browser lane was run.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
