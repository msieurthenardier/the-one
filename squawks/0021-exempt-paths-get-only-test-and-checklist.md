# Squawk 0021: Pin `EXEMPT_PATHS` members to GET-only routes; record the exemption checklist

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: —

## Report

`EXEMPT_PATHS` is path-only (no method check); its safety argument relies on each exempt
route being registered GET-only so other methods 405 at routing. With a second member the
set is now a hand-maintained enumeration. Add a test that, for every member of
`EXEMPT_PATHS`, asserts the app route at that path allows only `GET`/`HEAD`. Also lift the
four-part inertness checklist used for the OAuth callback (no DB read/write; mints no
credential; sets no cookie; single-use token consumed on first use) into
`SECURITY-MODEL.md` as the named bar for any future exemption.

## Evidence

- `the_one/interfaces/web/middleware.py:203-204` — `OAUTH_CALLBACK_PATH`, `EXEMPT_PATHS = frozenset({LIVENESS_PATH, OAUTH_CALLBACK_PATH})`
- `middleware.py:_handle_http` — `if path in EXEMPT_PATHS:` before any credential resolution
- `SECURITY-MODEL.md:57` "Exactly two exemptions"
- Flight log Leg 3 entry, "AC7 — inertness re-confirmation"

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
