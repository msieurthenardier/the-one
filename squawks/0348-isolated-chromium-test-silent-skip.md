# Squawk 0348: the isolated-Chromium widget test can skip silently

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-11
**Completed**: 2026-11-13

## Report
`tests/browser/test_flow_chat_widgets_isolated.py` is the only guard for the Mission 35 Flight 2 HAT defect where a sandboxed widget frame has 0 width at script start under Chromium site isolation (DD2 amendment). It skips when an isolating Chromium cannot launch or when its probe does not show the early 0 width, so on a host or CI image without that Chromium it becomes a silent no-op and the regression net disappears unnoticed.

## Evidence
- `tests/browser/test_flow_chat_widgets_isolated.py:56` `pytest.skip(f"cannot launch an isolating Chromium: {exc}")`, `:65` `pytest.skip(f"this Chromium does not isolate sandboxed frames (early width {early})")`.
- Precedent: `THE_ONE_REQUIRE_WEBKIT=1` turns a WebKit launch failure into a failure (`tests/browser/_ui_engines.py`).

## Corrective Action
Added `THE_ONE_REQUIRE_ISOLATED_CHROMIUM=1`, mirroring `THE_ONE_REQUIRE_WEBKIT`: a pure `isolated_chromium_policy(env, problem)` in `tests/browser/_ui_engines.py` (plus a test-only seam `THE_ONE_ISOLATED_CHROMIUM_FORCE_UNAVAILABLE=1`) decides skip vs fail; `tests/browser/test_flow_chat_widgets_isolated.py` routes both former `pytest.skip` sites (launch failure, non-isolating probe) through it. Unit test `test_isolated_chromium_policy` in `tests/test_ui_engines_policy.py`. CLAUDE.md names the flag beside `THE_ONE_REQUIRE_WEBKIT` (UI test apparatus) and in the `chats-widgets` lane line.

Note: the flag is NOT set in CI (`ci/tasks/browser.yml`, `.github/workflows/test.yml`); I could not verify that those images launch the isolating Chromium and show the early 0 width, so setting it could break CI. Set it there once verified.

## Verification
Unit: `tests/test_ui_engines_policy.py` 5 passed. Lane file (`THE_ONE_TEST_NETNS=1`, this host): normal run passed; with `THE_ONE_REQUIRE_ISOLATED_CHROMIUM=1` passed (isolation works here); with the force seam set, no require flag: skipped; force seam plus require flag: failed with "isolating Chromium required (THE_ONE_REQUIRE_ISOLATED_CHROMIUM=1) but: forced unavailable ...". Original criterion:
With the require flag set (the existing `THE_ONE_REQUIRE_WEBKIT=1` or a new `THE_ONE_REQUIRE_ISOLATED_CHROMIUM=1`), a launch failure or a non-isolating probe fails the test; without it the test still skips. CLAUDE.md's `chats-widgets` lane note names the flag.

## Sign-Off
**Reviewer**: batch Reviewer (Haiku), independent of the implementers.
- The policy is pure, and the fixture sends both former skip sites through it.
- The fail path raises before `yield`.
- The test-only force seam is named as test-only.
- Not setting the flag in CI is disclosed in the squawk.

The touched browser files passed 28 of 28 (WebKit required, netns).
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13`
