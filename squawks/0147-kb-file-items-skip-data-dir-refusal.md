# Squawk 0147: Knowledge-base file items skip the data-directory refusal

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
Registering a `folder` item canonicalizes the path and refuses one that equals, contains or lies inside the application data directory (M24 F4, DD-6). A `file` item gets neither check: any `path_or_url` is stored, and `GET .../items/{id}/source` reads it back through the extractor. Only the credential-holding operator can do this, but it makes DD-6 a folder-only rule in practice. Found by routine maintenance 2026-10-08 (finding #22).

## Evidence
- `the_one/interfaces/web/api.py` item create (~1668-1707): the data-dir check runs only when `item.type == "folder"`
- Source read-back ~1978-2030

## Corrective Action
*(written at completion)* Expected: apply the same canonicalization and data-dir containment refusal (422) to `file` items, reusing the folder check's helper rather than copying it.

## Verification
A unit test: a `file` item inside the data dir → 422; one outside → 201.

## Sign-Off
*(written at completion)*
