# Squawk 0019: Reconcile WARNING doesn't name the CLI-window loss; "undecidable → promote" invariant uncommented

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: —

## Report

`resolve_pending_key` already WARNs when sampled ciphertext decrypts only under the canonical
key while a pending key is promoted — which is exactly the documented "CLI process wrote rows
under the old key during a crashed rotation" loss — but the message doesn't say so, so an
operator can't connect the log line to the `agents.md` trade-off note. Separately, the
"nothing decidable → promote" branch is correct only because the sidecar is written before the
DB commit (a `.next` with no decidable rows means nothing was re-encrypted that matters); that
invariant is not named at the branch. Rename the warning text to mention the CLI window and add
the invariant comment (and, if cheap, a test named for the failure mode the branch is not
vulnerable to).

## Evidence

- `the_one/encryption.py:resolve_pending_key` — `logger.warning(...)` at ~`:262` with `under_canonical_only`
- `the_one/agents.md` "Encryption-rotation invariant (seven corpora)" — CLI-window trade-off paragraph
- Debrief 2026-08-28, "What Could Be Improved → Technical"

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
