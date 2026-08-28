# Squawk 0022: Admin System page shows the success flash for a `key_file: "staged"` rotation

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: 2026-08-28

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

`wireEncryptionRotate`'s success handler in
`the_one/interfaces/web/static/js/areas/admin/system-page.js` now reads the
rotate response body and branches on `key_file`:

- `"staged"` — a distinct warning flash: "Encryption key rotated, but the
  key file could not be updated on disk — the new key is staged and will be
  applied at next start. Check the server log." Uses a new
  `.admin-system-flash.warning` CSS modifier (`the_one/interfaces/web/static/css/admin.css`,
  reusing the existing `--status-warning` token already used elsewhere for
  attention-required states, e.g. `.banner-warning` on this same page) and is
  **not** auto-dismissed (the existing `success`/`error` paths clear after
  3s/4s via `setTimeout`; the staged warning has no such timer, so it stays
  until the operator's next rotate attempt or page navigation).
- `"promoted"`, any other value, or a missing field — unchanged existing
  success flash ("Encryption key rotated successfully.", auto-dismissed
  after 3s), preserving backward compatibility with older server responses.

No backend changes; `the_one/interfaces/web/api.py` was not touched.

## Verification

Added `tests/browser/test_flow_admin_rotate_flash.py` (no prior browser test
covered the System page rotate button — confirmed via
`grep -rln rotate-key-btn tests/browser/`). Two cases, both driving the
button through the real `App.confirmDelete` two-click arm/commit flow and
mocking `POST /api/encryption/rotate` via `page.route`:

- `test_rotate_staged_shows_warning_flash` — `key_file: "staged"` →
  `.admin-system-flash` gets the `warning` class, text contains the staged
  message + "Check the server log", and — after waiting past the 3s success
  auto-dismiss window — the flash is still showing (proves non-dismissal).
- `test_rotate_promoted_shows_success_flash` — `key_file: "promoted"` →
  unchanged `success` class + "Encryption key rotated successfully." text.

Ran the browser lane restricted to this file:

```
THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh \
  -m browser tests/browser/test_flow_admin_rotate_flash.py -v --tb=short
```

Result: `2 passed, 1 warning in 7.29s` (the one warning is an unrelated
pre-existing `discord.player` `audioop` deprecation notice).

`.venv/bin/ruff check tests/browser/test_flow_admin_rotate_flash.py` and
`.venv/bin/ruff format --check tests/browser/test_flow_admin_rotate_flash.py`
both pass (only Python file added by this squawk).

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-28; Sonnet — batch touches the credential gate and key-material code)
**Verdict**: confirmed
**Commit**: `{sha}` on `squawk/turnaround-2026-08-28` — PR #{pr}

Full unit suite at close-out: 4580 passed / 10 skipped / 0 failed (513s); browser lane for 0022: 2 passed.
