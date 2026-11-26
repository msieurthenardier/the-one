# Squawk 0424: Browser tests that click a rail link right after `page.goto` race the router boot when the bwrap probe is slow

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: 2026-11-25

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
`tests/browser/_nav.py::open_destination` now calls `wait_router_started(page)` before clicking the rail link (the existing squawk 0409 helper; `wait_for_function` returns at once when the router is already up, so no cost on a warm page). Every caller benefits; no product change.

Reproduction (host load about 2, so the probe is fast and the natural race does not occur): a throwaway test in `tests/browser/` (deleted afterwards) routed `**/api/config` through `route.fetch()` plus a 3 s `page.wait_for_timeout`, then did `page.goto`, `open_destination(settings)` and expected `.page-title` = "Appearance". Without the fix it failed (page stayed on Chats, no title); with the fix it passed.

Suggested direction, from the diagnosis: on the test side, add a boot-ready wait to `tests/browser/_nav.py` before `open_destination`. For example, wait for the router to be current, or for `location.hash` to be non-empty after `page.goto`. The probe cost is environmental. A product-side deadline on `/api/config` would also work, but it changes runtime behaviour, which is beyond a squawk.

Second instance of the same class, found at the turnaround gate (load about 12): `test_flow_chat_drawer.py::test_deleted_and_unknown_agents_show_no_settings_link` failed 3 of 3 with `a._sessionState is not a function`. The chat area's `init()` (which assigns `_sessionState`) runs only after the router starts, i.e. after `/api/config` resolves, and `_nav.goto` does not pass through `open_destination`. An exception in a `wait_for_function` predicate fails the wait without retry. Pre-existing, not caused by the `open_destination` change. Fix: the predicate now tolerates the not-yet-assigned seam (`a && a._sessionState && ...`, falsy until ready); the same unguarded wait predicates were hardened in `test_flow_gleepglorp_drawer_chat.py`, `test_flow_chat_start_flow.py`, `test_flow_chat_pane.py`, `test_flow_chat_composer.py` and `test_flow_chat_start_reconnect.py`.

## Verification
Run at load about 2 (not the loaded host the criterion below names): `test_flow_hash_routing.py` passed 3 of 3 (6 passed each, via `run-tests.sh` with `THE_ONE_TEST_NETNS=1`); `--lane shared -x` 365 passed in 787 s; `tests/test_nav_helper.py` 83 passed. The slow-config repro above failed before and passed after.

Original criterion: on a loaded host (load above 10), the `test_flow_hash_routing.py` file passes three times in a row in isolation, and `tests/test_nav_helper.py` passes.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review plus a re-review of the predicate guards
**Verdict**: confirmed. The guards keep each wait's final state, and none is always true.
- **Lanes at load 6-28:** `gleepglorp-chat` 84 passed; `chats` 177 passed, with 1 failure from the same boot class via `_nav.goto`, logged as squawk 0428; the five further `open_destination` files 147 passed; the drawer file 35 passed.
- **The original hash-routing file:** 6 passed, 3 runs.
**Commit**: `squawk: turnaround 2026-11-25-2` on squawk/turnaround-2026-11-25-2
