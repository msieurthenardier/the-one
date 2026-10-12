# Squawk 0188: anthropic-plan re-auth message still sends users to "Administration"

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

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
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
