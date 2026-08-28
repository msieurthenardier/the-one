# Squawk 0012: `_require_long_lived_caller` has no explicit `caller.source == "file"` check and a stale docstring

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
