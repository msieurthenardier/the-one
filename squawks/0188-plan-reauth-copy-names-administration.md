# Squawk 0188: anthropic-plan re-auth message still sends users to "Administration"

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-13

## Report
When an `anthropic-plan` provider needs re-authentication, the error tells the user to
"Open the provider in Administration and sign in again." There has been no
"Administration" destination since Mission 25 (it is Settings), and since sortie 02 providers
live in Library ("Model providers"). The copy should point at Library.

## Evidence
- `the_one/llm/plan_credentials.py:81` — `"Open the provider in Administration and sign in again."` (the default message of the re-auth error).
- `tests/browser/test_flow_provider_plan_signin.py:369` — `reauth_detail = "Re-authentication required: sign in to Anthropic again from Administration."` (a second copy of the wording, asserted by the test; trace its source when fixing).
- Found by the sortie 02 leg 2 Developer; out of that sortie's charter (no backend change).

## Corrective Action
Replaced every provider-pointing "Administration" string with "Library › Model providers" in `the_one/llm/plan_credentials.py` (default re-auth message, no-stored-credentials message, refresh-rejected message, `ReauthRequiredError` docstring) and `the_one/llm/anthropic_plan_provider.py` (unsaved-provider message). The `anthropic-plan-token` type has no separate string. The browser test's `reauth_detail` is a Playwright route stub (not server-sourced); updated to the new wording. Tests asserting `"Administration"` in `test_plan_credentials.py`, `test_anthropic_provider.py`, `test_provider_api.py` now assert `"Library › Model providers"`.

Non-provider "Administration" leftovers, unchanged: `the_one/interfaces/web/static/js/areas/admin/knowledge-settings-page.js:6` (comment), `tests/browser/test_flow_admin_knowledge_settings.py:1` (docstring), `the_one/agents.md:1231` (Admin config UI web_search history note).

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_plan_credentials.py tests/test_anthropic_provider.py tests/test_provider_api.py -x --timeout 30`: 341 passed
- `ruff check` / `ruff format --check` on changed files: clean
- Browser stub test not run (string-only change in a route stub).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.
