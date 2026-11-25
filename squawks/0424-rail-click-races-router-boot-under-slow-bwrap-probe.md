# Squawk 0424: Browser tests that click a rail link right after `page.goto` race the router boot when the bwrap probe is slow

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

On a loaded host, two `app_clean` tests fail every time, including in isolation:
- `tests/browser/test_flow_hash_routing.py::test_hash_routing_admin_subpage_persists_on_refresh` (line 38);
- `test_hash_routing_settings_nav_pushes_history` (line 202).

This is the cause:
1. The first `GET /api/config` waits on the sandbox posture. The bwrap probe (`bwrap --unshare-user --ro-bind / / /usr/bin/true`, `timeout=5`) needs more than 5 s of CPU at load around 20, so it times out. The lifespan warm-up is fire-and-forget, so the first request pays for the probe.
2. The app starts its router only after the config fetch returns, about 5-6 s after `page.goto`.
3. The test clicks the Settings rail link before that, the router's start overrides the click, and the page stays on Chats. There is no `.page-title`.

It is not caused by Mission 37: it fails the same way with `-p no:xdist`, and the flight changed nothing under `the_one/` apart from `agents.md`. It probably predates Mission 37: the probe code dates from Mission 32 (`e21d2195`), and the router gate predates the M36 F5 gate, which passed on a quieter host. Neither has been checked on an older commit. Found by the Mission 37 Flight 1 closing-gate sample (Developer diagnosis).

## Evidence
- A debug run: `/api/config` was requested at 0.95 s and answered at 5.96 s. `/api/providers` and `/api/agents` were requested at 5.99 s.
- `time bwrap --unshare-user --ro-bind / / /usr/bin/true`: 5.65 s real, 5.7 s user, at load about 20. `describe_selection()` returned `('passthrough', 'user namespace probe failed')` after 5.01 s.
- `the_one/platform/sandbox/factory.py`: the probe, with `timeout=5`.

## Corrective Action
*(written at completion)*

Suggested direction, from the diagnosis: on the test side, add a boot-ready wait to `tests/browser/_nav.py` before `open_destination`. For example, wait for the router to be current, or for `location.hash` to be non-empty after `page.goto`. The probe cost is environmental. A product-side deadline on `/api/config` would also work, but it changes runtime behaviour, which is beyond a squawk.

## Verification
On a loaded host (load above 10), the `test_flow_hash_routing.py` file passes three times in a row in isolation, and `tests/test_nav_helper.py` passes.

## Sign-Off
*(written at completion)*
