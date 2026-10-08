# Squawk 0143: Validation 422s echo the request input, including submitted secrets

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
Most `ValidationError` → 422 handlers in `api.py` return `e.errors(include_context=False)`, which still carries pydantic's `input`. A create request missing a required field (e.g. a connector with no `name`) gets its whole body echoed back, including `secrets.bot_token`. Three handlers use bare `e.errors()`, which can also 500 when a validator puts a raw exception in `ctx` (the failure documented in the comment at `api.py:577`). The M25 F6 L1a convention (`include_input=False`) is applied at only two sites. Found by routine maintenance 2026-10-08 (finding #19). Update routes were checked and do not echo stored secrets (all validators are field-level), so this is hardening, not an active leak.

## Evidence
- `the_one/interfaces/web/api.py` — `include_input=False` only at the provider-create (~4324) and chat-session-create (~4663) handlers
- `include_context=False` without `include_input=False` at ~1494, 1526, 1667, 2165, 2573, 2700, 3534 (`create_connector`), 3588, 4351, 4724; bare `e.errors()` at ~830, 904, 978
- In-process repro: `Connector.model_validate` on a create body with `secrets.bot_token` and no `name` → `loc ["name"]`, `input` = full payload

## Corrective Action
Added module-level `_validation_detail(e)` in `api.py` (`e.errors(include_context=False, include_input=False)`) and routed all 17 `ValidationError` -> 422 handlers through it (including the 3 bare `e.errors()` sites, which could 500 on a non-serializable `ctx`, and the 2 prior `include_input=False` sites). Response shape unchanged apart from the dropped `input`/`ctx` keys.

## Verification
New tests: `tests/test_connector_routes.py::test_create_422_does_not_echo_submitted_secret` and `tests/test_db_api.py::TestMCPSourceAPI::test_create_422_does_not_echo_submitted_secret` (sentinel secret + missing `name` -> 422, sentinel absent). Falsified: with the helper reverted to `include_context=False` only, both fail; restored. Both files pass (219 passed); ruff check/format clean. No test asserted on a 422 `input` key. A bare-`e.errors()` 500 regression test was skipped (needs a model-validator raising a raw exception; not cheap to construct).

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
