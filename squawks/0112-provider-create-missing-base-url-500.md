# Squawk 0112: Creating a provider without `base_url` returns a 500 with a raw ValidationError

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: —

## Report

`POST /api/providers` with a body that leaves out `base_url` returns HTTP **500**, and
the body is a raw Pydantic `ValidationError`. It should return HTTP **422**, a validation
error in the API's usual shape. The docstring of the browser test seeder claims a 422.

Mission 25 Flight 3 leg 2 found this while seeding a dev instance by hand. The UI always
sends `base_url`, so operators are not affected. API clients and test seeders that leave
it out get an unhandled server error instead of a clear validation message.

## Evidence

- Repro: `curl -X POST /api/providers -H 'Authorization: Bearer …' -d '{"name":"x","type":"mock","config":{}}'`
  returns 500.
- Recorded in the leg 2 entry of
  `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`.
- `tests/browser/seeders.py` (its docstring for the provider seeder).

## Corrective Action

*(written at completion)*

## Verification

## Sign-Off

*(written at completion)*
