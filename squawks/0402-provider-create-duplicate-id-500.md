# Squawk 0402: Creating a provider with a duplicate client-supplied id gives a 500

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

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
*(written at completion)*

## Verification
A route test posts a provider whose `id` already exists. It gets a 409 with a plain detail, and
the stored row is unchanged.
