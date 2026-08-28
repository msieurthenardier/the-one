# Squawk 0020: No single test asserts every `/_test/*` route 403s without dev mode

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: —

## Report

Four dev-mode test seams are always registered on the router and gated only inside each
handler by `settings.dev_mode`. Each has its own 403 test, but nothing asserts the set — a
fifth seam added by copy-paste without the gate would not be caught. Add one parametrized
test that walks `app.routes` for paths under `/_test/` and asserts each returns 403 with
`dev_mode=False`.

## Evidence

- `the_one/interfaces/web/api.py:4603` `/_test/chat/sessions/{session_id}/routing-audit`, `:4642` `/_test/chat/sessions/lookup`, `:4682` `/_test/purge-sweep`, `:4711` `/_test/oauth/pending`
- Gate detail string `"test-seam endpoint requires THE_ONE_DEV_MODE=true"` at `api.py:4625, :4670, …`
- `the_one/interfaces/web/app.py` — no conditional mounting by `dev_mode`

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
