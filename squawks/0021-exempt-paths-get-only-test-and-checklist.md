# Squawk 0021: Pin `EXEMPT_PATHS` members to GET-only routes; record the exemption checklist

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: 2026-08-28

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

1. **Test** — added `TestExemption.test_exempt_paths_are_get_only_on_the_real_app`
   in `tests/test_credential_gate.py`, next to the existing
   `test_exempt_set_is_liveness_and_oauth_callback`. It imports the real
   `the_one.interfaces.web.app.app`, and for every member of `EXEMPT_PATHS`:
   asserts at least one route is registered at that path (an exempt path
   with no route is a typo waiting to become a hole), then asserts each
   matching route's declared `methods` is a subset of `{"GET", "HEAD"}`.
   The failure message names the offending path, the full declared method
   set, and the specific non-GET/HEAD method(s), and explains that the
   gate is path-only so the safety argument depends on GET-only
   registration at the routing layer.
2. **Doc** — added a "Bar for any future exemption" paragraph in
   `SECURITY-MODEL.md` immediately after the "Exactly two exemptions"
   bullet (now lines 89-96), stating the four-part inertness checklist
   (no DB read/write; mints no credential/sets no cookie; single-use
   token consumed on first use; route registered GET-only) and requiring
   a proposed exemption to document all four in the `EXEMPT_PATHS`
   comment block and be pinned by the test from item 1.
3. Added a pointer comment directly above `EXEMPT_PATHS` in
   `the_one/interfaces/web/middleware.py` cross-referencing the
   SECURITY-MODEL.md section and the new test by name.

No gate behavior changed — both existing exempt routes (`/api/live`,
`/api/oauth/callback`) were confirmed already GET-only before and after
this change; the new test only pins that fact going forward.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_credential_gate.py -x --timeout 60`
  → 83 passed (82 pre-existing + 1 new), 0 failed.
- Confirmed against the real app object directly (`app.routes`) that
  `/api/live` and `/api/oauth/callback` each resolve to exactly one route
  with `methods == {"GET"}` (no HEAD/other methods declared; HEAD/POST
  return 405 at routing, not 401 from the gate) — matches what the new
  test asserts.
- `.venv/bin/ruff check .` → All checks passed.
- `.venv/bin/ruff format --check .` → 454 files already formatted.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-28; Sonnet — batch touches the credential gate and key-material code)
**Verdict**: confirmed
**Commit**: `{sha}` on `squawk/turnaround-2026-08-28` — PR #{pr}

Full unit suite at close-out: 4580 passed / 10 skipped / 0 failed (513s); browser lane for 0022: 2 passed.
