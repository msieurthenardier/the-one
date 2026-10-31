# Squawk 0195: a fresh `make up` data dir has no `api-credential`, contrary to CLAUDE.md

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —
**Related**: 0278: the same gap logged twice (`serve` never creates the credential file, CLAUDE.md says it does); complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
CLAUDE.md's "Behavior-test credential convention" says a fresh instance "creates the file on first launch". A host-native `make up` on a scratch data dir does not: `get_credential()` is create-on-first-use and the server never calls it at startup, so `make up`'s `verify-serving` stops with "no local API credential found" and a behavior-test Executor has no credential to read. Sortie 03 leg 2 had to run `rotate-api-credential` and restart. Fix one or the other: the doc, or create the credential at server startup. Read the code first to see which is intended.

## Evidence
- `the_one/api_credential.py::get_credential` — "Return the current credential, creating it on first use."
- CLAUDE.md, "Behavior-test credential convention" §1 ("start the instance first (it creates the file on first launch)").
- Sortie 03 flight log, `live-verification` (2026-10-12); debrief Recommendation 1.

## Deferral
Deferred at the sortie 03 debrief. Revisit trigger: the next squawk batch (with 0193, 0194), or before the next live behavior test on a scratch data dir.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
