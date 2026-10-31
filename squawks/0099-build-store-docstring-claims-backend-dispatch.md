# Squawk 0099: `_build_store`'s docstring claims it constructs the backend named by settings; it hardcodes `UsearchStore`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: —
**Related**: 0096, 0098: docstring and doc claims that overstate the knowledge/vector code; complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report

`_build_store`'s docstring says it constructs "the backend named by
`vector_store_settings`". It reads `dtype` and `dim` from those settings but
ignores `.backend` entirely and always returns `UsearchStore`.

Harmless today — `VectorStoreSettings.backend` is `Literal["usearch"]`, so there
is nothing else to name. It matters because this is the seam a second backend
would arrive through, and the docstring describes dispatch that does not exist,
which is how the next reader mis-plans that work. Same family as squawks 0096
and 0098: documentation asserting behaviour the code does not implement.

## Evidence

- `the_one/vectors/__init__.py:70` — "Construct (but do not open) the backend
  named by ``vector_store_settings``."
- `the_one/vectors/__init__.py:76-78` — `from the_one.vectors.usearch_store import UsearchStore` / `return UsearchStore(conn, dtype=..., dim=...)`; `.backend` is never read.

## Corrective Action

*(written at completion)*

Say what it does: constructs the one production backend, with `dtype`/`dim` from
settings, and note that `.backend` is not yet a dispatch key.

## Verification

Read-back: the docstring matches the body.

## Sign-Off

*(written at completion)*
