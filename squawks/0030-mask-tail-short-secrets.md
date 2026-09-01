# Squawk 0030: Secret mask reveals last-4 plaintext — nearly the whole value for short secrets

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: —

## Report

The established `_emit_mask` convention (M11 F8 L3) renders masked secrets as `***...{tail4}` in API
responses. For a short secret this reconstructs nearly the whole value — the behavior-test's 5-char
token `dummy` masked to `***...ummy`, eliding only one character. Fix: show the tail only when the
secret length clears a threshold (e.g. ≥12 chars), else fully opaque (`***`). Strictly safer; the
tail's identification purpose only makes sense for long tokens anyway. Applies to the shared helpers
(`_mask_secrets`/`_emit_mask` in `api.py`), so MCP-source and connector responses both change —
update the existing mask-format regression test accordingly.

## Evidence

- `the_one/interfaces/web/api.py` `_emit_mask`/`_mask_secrets` (~`:1489-1609`)
- Behavior-test runs `2026-08-31-21-37-14` (checkpoint 1 validator notes) and `2026-08-31-22-43-08`
  (validator closing) — flagged non-blocking both runs
- Flight 2 flight-end review: convention pre-exists this flight (not a Flight 2 defect), but "weak masking"

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
