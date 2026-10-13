# Squawk 0198: `make verify-serving` checks a moved file and always fails

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
`make up` (and `make verify-serving`) fails against a healthy instance:
`✗ admin/providers-list.js returned 404 — not serving`. Sortie 2 (Model providers in Library) moved the provider list out of `static/js/areas/admin/`, but the Makefile's asset list still names `admin/providers-list.js`, so the check cannot pass. Found during Mission 29 Flight 1's HAT, on a dev instance on port 8492.

## Evidence
- `Makefile` `verify-serving` asset loop (~154): `for f in admin.js admin/system-page.js admin/providers-list.js admin/provider-editor.js admin/provider-models.js …`
- `ls the_one/interfaces/web/static/js/areas/admin/` has no `providers-list.js`, `provider-editor.js` or `provider-models.js` (moved by `f88b5a0`, "sortie/2: model providers move to Library").
- Every other listed asset returned 200 on the same instance.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

## Disposition
**Deferred**: out of scope for Mission 29 Flight 1 (MCP SDK port), logged mid-flight per the agentic workflow. Revisit at the next squawk turnaround, or the next time the Makefile is touched.
