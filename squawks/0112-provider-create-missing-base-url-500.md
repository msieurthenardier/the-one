# Squawk 0112: Creating a provider without `base_url` returns a 500 with a raw ValidationError

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: 2026-10-06

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

`create_provider` (`the_one/interfaces/web/api.py`) now catches `ValidationError` around `LLMProviderConfig.model_validate` and raises `HTTPException(422, detail=e.errors(include_context=False, include_input=False))`, the sibling routes' pattern; `include_input=False` keeps a submitted `api_key` out of the response. The provider form's `performSave` now sends through `App.api.fetchJson`, so a 422 detail list reads "field: message" in `.editor-error`. Widened with squawk 0081 (same defect on `create_chat_session`).

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

Unit tests in `tests/test_provider_api.py::TestCreateProviderValidation` (missing `base_url` is 422; an `api_key` is not echoed in the 422 body). Browser: `tests/browser/test_flow_settings_visible_fixes.py::test_provider_create_422_is_flattened_in_the_error_area` (settings lane).

## Sign-Off

**Reviewer**: pending the Flight 6 leg review
