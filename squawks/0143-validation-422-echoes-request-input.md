# Squawk 0143: Validation 422s echo the request input, including submitted secrets

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
Most `ValidationError` → 422 handlers in `api.py` return `e.errors(include_context=False)`, which still carries pydantic's `input`. A create request missing a required field (e.g. a connector with no `name`) gets its whole body echoed back, including `secrets.bot_token`. Three handlers use bare `e.errors()`, which can also 500 when a validator puts a raw exception in `ctx` (the failure documented in the comment at `api.py:577`). The M25 F6 L1a convention (`include_input=False`) is applied at only two sites. Found by routine maintenance 2026-10-08 (finding #19). Update routes were checked and do not echo stored secrets (all validators are field-level), so this is hardening, not an active leak.

## Evidence
- `the_one/interfaces/web/api.py` — `include_input=False` only at the provider-create (~4324) and chat-session-create (~4663) handlers
- `include_context=False` without `include_input=False` at ~1494, 1526, 1667, 2165, 2573, 2700, 3534 (`create_connector`), 3588, 4351, 4724; bare `e.errors()` at ~830, 904, 978
- In-process repro: `Connector.model_validate` on a create body with `secrets.bot_token` and no `name` → `loc ["name"]`, `input` = full payload

## Corrective Action
*(written at completion)* Expected: one module-level helper (e.g. `_validation_422(e)`) returning `e.errors(include_context=False, include_input=False)`, used by every handler. The response shape is unchanged apart from the dropped `input`/`ctx` keys.

## Verification
New tests: POST `/api/connectors` with `secrets.bot_token` and no `name` → 422 whose body does not contain the token; the same for the MCP-source create route. Optional guard: a connector-update 422 does not contain the stored token.

## Sign-Off
*(written at completion)*
