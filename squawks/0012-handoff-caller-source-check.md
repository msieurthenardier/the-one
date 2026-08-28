# Squawk 0012: `_require_long_lived_caller` has no explicit `caller.source == "file"` check and a stale docstring

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

`/api/session/handoff` mints an unscoped operator browser session. Its dependency
`_require_long_lived_caller` resolves the bearer via `resolve_caller()` and its
docstring says that function "only walks long-lived-credential sources" — true when
written (Mission 20), stale since Mission 21 added the `agt_`/`ext_` credential
sources, which `resolve_caller` now walks too. The only thing preventing an `agt_` or
`ext_` holder from reaching the handoff route is `CredentialGateMiddleware`'s
`CONFINED_SOURCE_PATHS` check at the ASGI layer. The 2026-08-27 Security Reviewer
verified that control holds (no bypass via path normalisation, redirect, or the WS
branch) — so this is not a live escalation, but the route's safety rests on a single
external control the code's own comments don't acknowledge, and the docstring will
mislead the next person to touch it. Finding S4.

Fix: in `_require_long_lived_caller`, `if caller.source != "file": raise
HTTPException(status_code=401, ...)` so the property holds by construction; refresh
the docstring to say the confinement middleware is the first line and this is the
second; one test asserting an `ext_` bearer gets 401 from the dependency directly.

## Evidence

- `the_one/interfaces/web/app.py:2140-2163` — `_require_long_lived_caller`; docstring
  at `:2146-2150` ("Resolves through `resolve_caller`, the same single entry point the
  gate middleware uses …") with no `source` check on the returned caller.
- `the_one/interfaces/web/middleware.py:377-382` — the confinement check (HTTP) and
  `:420-422` (WS closes 1008) that currently carry the whole guarantee.

## Corrective Action

`the_one/interfaces/web/app.py:_require_long_lived_caller` now checks the
resolved caller's source explicitly: after `resolve_caller` returns a
non-`None` `IdentifiedCaller`, `if caller.source != "file": raise
HTTPException(status_code=401, detail="Local API credential missing or
invalid")` — the same 401 body the function already raises for a missing
header or an unresolved token, so a caller can't distinguish "no credential
resolved" from "resolved, but not the long-lived one."

Refreshed the function's docstring: removed the outdated "`resolve_caller`
only walks long-lived-credential sources" claim (superseded by Mission 21's
`agt_`/`ext_` self-configuration sources) and added a paragraph naming the
confinement middleware (`CredentialGateMiddleware`'s `CONFINED_SOURCE_PATHS`
check, `middleware.py:377-382`) as the first line of defense and this
explicit check as the second, so the property holds by construction.

Added half a sentence to `SECURITY-MODEL.md`'s Authentication section,
where it describes `POST /api/session/handoff`, noting the route's
dependency checks the resolved caller's source is explicitly `file`.

No change to `middleware.py`, `api_credential.py`, or any credential
source — this is a single additive check at the route dependency, matching
the squawk's proposed fix exactly.

## Verification

Added `TestMintEndpointOnRealApp.test_mint_endpoint_refuses_a_resolved_caller_whose_source_is_not_file`
in `tests/test_credential_gate.py`: registers a fake, *unconfined*
`CredentialSource` (`_InMemorySource`, already used elsewhere in this file
by `TestSeam`) so the request reaches the route dependency rather than
being stopped by the confinement middleware first, then asserts
`POST /api/session/handoff` with that source's bearer token gets 401, and
that the ordinary `file` bearer still gets 200 in the same test.

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_credential_gate.py -x --timeout 60`
  — 82 passed (81 pre-existing + 1 new), 0 failed.
- `make lint` — all checks passed, no findings in the touched files.
- `make format-check` — 441 files already formatted, no diff.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `5cf3cac` on `squawk/turnaround-2026-08-27` — PR #178
