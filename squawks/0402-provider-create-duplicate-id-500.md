# Squawk 0402: Creating a provider with a duplicate client-supplied id gives a 500

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-23

## Report

`POST /api/providers` accepts a client-supplied `id`. A body whose `id` already exists fails on
the insert's primary key and surfaces as a 500, not a clean 409 or 422. This is pre-existing. Leg
5a moved the code into `provider_service.create_provider` without changing it, and noted it as out
of scope (the provider survey, 2026-11-21). The editor never sends an id, so only API callers hit
it.

## Evidence
- `the_one/llm/provider_service.py` `create_provider`: `if "id" not in data: data["id"] =
  uuid.uuid4().hex[:12]`, with no existence check before `repo.create`.

## Corrective Action
`the_one/llm/provider_service.py::create_provider` records whether the body carried an `id`, and
catches `sqlite3.IntegrityError` from `repo.create`. When the id was client-supplied and
`repo.get(id)` finds a row, it raises `ProviderWriteError(409, "A model provider with id <id>
already exists.")`; otherwise it re-raises. The check follows the insert, so it is race-safe, and
the transaction has rolled back (an `on_commit` mark with it).

## Verification
`tests/test_provider_api.py::TestProviderAPI::test_create_with_a_duplicate_client_id_is_a_409`
(route), and in `tests/test_provider_service.py`
`test_create_with_an_existing_client_id_is_a_409_and_the_row_is_unchanged`,
`test_a_409_create_rolls_the_on_commit_mark_back`, `test_create_without_an_id_still_generates_one`.
The first three fail with the catch disabled (falsified). Original plan: a route test posts a provider whose `id` already exists. It gets a 409 with a plain detail, and
the stored row is unchanged.

## Sign-Off
- **Fixed in:** Mission 36 Flight 5, Leg 1b.
- **Reviewed:** by the Flight 5 Batch A Reviewer (Sonnet): `[HANDOFF:confirmed]`, 2026-11-23.
- **Committed:** in the Flight 5 Batch A checkpoint commit (its ref is in the flight log).
