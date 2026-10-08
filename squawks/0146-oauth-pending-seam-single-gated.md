# Squawk 0146: The OAuth pending-flow test seam is gated by dev mode alone

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
`POST /api/_test/oauth/pending` registers a pending OAuth flow for a chosen `source_id` and chat session, which helps forge a callback. It is gated only by `THE_ONE_DEV_MODE`, unlike every sibling seam (stub, Discord sever, purge sweep), which each also need their own env flag (the `risk-tiered-test-seam-gating` convention). Its docstring says its gating "mirrors the sibling seams", which is no longer true. The seam env flags are also not listed together anywhere (purge-sweep's flag appears only once, in agents.md). Found by routine maintenance 2026-10-08 (finding #21).

## Evidence
- `the_one/interfaces/web/api.py::seed_pending_oauth_flow` — `if not settings.dev_mode:` is the only gate
- Only user: `tests/browser/test_flow_oauth_callback_cross_site.py`

## Corrective Action
`seed_pending_oauth_flow` now requires dev mode AND `THE_ONE_OAUTH_TEST_ENDPOINT=1`, read from the environment at request time (403 otherwise), exactly like the sibling seams; docstring corrected. The cross-site browser test overrides `app_clean` locally to spawn with the flag. Added a "Test seams at a glance" table to CLAUDE.md; updated the `risk-tiered-test-seam-gating` precedent in `the_one/agents.md` and the dual-gated-seams paragraph in SECURITY-MODEL.md.

## Verification
Added `TestSeam::test_seam_403s_without_flag` (dev mode on, flag unset: 403); the existing dev-mode-off test now sets the flag; the 200/409 tests set both. Falsified: reverting the flag check failed the new test, then restored. `test_oauth_callback_gate.py` + `test_seam_routes_403_sweep.py`: 17 passed. Browser `test_flow_oauth_callback_cross_site.py`: 1 passed. ruff check and format clean.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
