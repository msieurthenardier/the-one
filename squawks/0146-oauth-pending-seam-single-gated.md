# Squawk 0146: The OAuth pending-flow test seam is gated by dev mode alone

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
`POST /api/_test/oauth/pending` registers a pending OAuth flow for a chosen `source_id` and chat session, which helps forge a callback. It is gated only by `THE_ONE_DEV_MODE`, unlike every sibling seam (stub, Discord sever, purge sweep), which each also need their own env flag (the `risk-tiered-test-seam-gating` convention). Its docstring says its gating "mirrors the sibling seams", which is no longer true. The seam env flags are also not listed together anywhere (purge-sweep's flag appears only once, in agents.md). Found by routine maintenance 2026-10-08 (finding #21).

## Evidence
- `the_one/interfaces/web/api.py::seed_pending_oauth_flow` — `if not settings.dev_mode:` is the only gate
- Only user: `tests/browser/test_flow_oauth_callback_cross_site.py`

## Corrective Action
*(written at completion)* Expected: add a dedicated env flag (e.g. `THE_ONE_OAUTH_TEST_ENDPOINT=1`) checked at request time (403 otherwise), set it in the one browser test's spawn env, and add a short table of all `/_test/*` seams and their flags to CLAUDE.md's dev-mode section.

## Verification
A unit test asserting 403 with dev mode on but the flag unset, and 200 with both set; the cross-site browser test still passes.

## Sign-Off
*(written at completion)*
