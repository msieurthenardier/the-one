# Squawk 0004: Factor the surface-row marker check into `constants.py` to remove import-order duplication

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-25
**Completed**: —

## Report

The `the_one/self_configuration/` package routes around a circular import by
duplicating the surface-row ownership-marker check. `credentials.py:load_from_rows`
re-implements the same marker predicate that `manage.is_surface_row` already
provides, inline, rather than calling it — because `manage` imports `surface` and
`surface` imports `manage` (function-local imports break the cycle at runtime). The
duplicated marker logic is exactly the "duplicate shape for import-order reasons"
pattern the Mission 20 debrief flagged as a recurring maintenance smell (its three
near-identical `auth_headers` implementations).

Servicing action: move the marker constant + the `is_surface_row`-style predicate
into the leaf `constants.py` module (which already holds `MOUNT_PATH` /
`CONFINED_SOURCE_PATHS` and imports nothing heavy), then have both `manage.py` and
`credentials.py` import it from there — removing the duplication and, ideally, the
function-local import dance.

Non-urgent watch-item raised by the Mission 21 Flight 1 debrief; do it if/when the
self-configuration package grows further.

## Evidence

- `the_one/self_configuration/credentials.py:load_from_rows` — inline marker check.
- `the_one/self_configuration/manage.py:is_surface_row` — the canonical predicate.
- `the_one/self_configuration/manage.py:enable` / `surface.py:_calling_agent` —
  function-local imports of each other to break the cycle.
- Precedent: Mission 20 debrief, "three near-identical `auth_headers`" finding
  (see squawk 0001).

## Corrective Action

*(written at completion)*

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
