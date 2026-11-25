# Squawk 0406: The drawer test helper's `boot()` returns before the router has started

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-11-23
**Completed**: 2026-11-23

## Report

`tests/browser/_drawer.py::boot()` waits only for `App.gleepglorpDrawer.state() !== null` and an
open drawer socket. Neither depends on the router: `static/js/app.js` mounts the drawer and its
chat on `DOMContentLoaded` (about line 195-203), but calls `App.router.start` only after
`/api/config` and `/api/time-settings` resolve (about line 239). Under host load a test acts in
that window: `App.router.current()` is null, no area is mounted, the page context is null.

Symptoms seen in the `gleepglorp-chat` lane (all in `test_flow_gleepglorp_drawer_chat.py`, which
boots through `_drawer.boot`): no `page` key on `start_session` (`KeyError: 'page'`), no
`message-context` chip, a rail click into Settings or Chats ignored (hash unchanged for 8 s),
`a._sessionState is not a function`. Batch C of M36 Flight 5 failed the lane in 7 of 9 runs at load
4-6.5; HEAD `fbf11634` failed 1 of 4 (`test_deleting_the_conversation_from_chats_resets_the_drawer`).
Grounding because the lane is a gate of the flight in flight.

## Evidence
- `tests/browser/_drawer.py::boot` — "wait for the drawer's socket to open"; no router wait.
- `the_one/interfaces/web/static/js/app.js` — drawer mounts at `DOMContentLoaded`; `App.router.start`
  inside the config/time-settings `Promise.all`.
- A Playwright probe at HEAD with a 300 ms delay on `/api/config` passed both `boot()` waits with
  `App.router.current() === null` (M36 F5 Batch C investigation, session scratchpad `probe.py`).

## Corrective Action
`tests/browser/_drawer.py`: `boot()` now ends with `wait_router(page, route)`, which waits for
`App.router.current()` to be non-null (the router has committed a route) and then reuses
`_nav.expect_route` for the canonical compare against the requested route. `wait_socket()` itself
also waits for the router to have committed (`wait_router_started`), so every other helper that
loads or reloads a page and drives the drawer at once (the `page.reload()` then `wait_socket`
sequences in `test_flow_gleepglorp_drawer_chat.py` and `test_flow_gleepglorp_fill.py`, and the
second-window `new_page` + `_nav.goto` + `wait_socket` cases) gets the same wait without a per-site
edit. `test_flow_gleepglorp_drawer_shell.py::_open` already waits for the destination panel (which
mounts after the router), so it is unchanged. No product code changed: the app's start order
(drawer at `DOMContentLoaded`, router after the config fetches) is deliberate.

## Verification
`boot()` also waits until the router has committed the requested route (canonical compare, as
`_nav.expect_route` does). The `gleepglorp-chat` lane then passed three runs in a row alone on the
Batch C tree (82 passed each, about 210 s; load average at the starts 1.43, 3.55, 2.93) and once
inside the full `--parallel 3` browser run (82 passed, load 2.79 at its start). Before the fix the
lane failed 7 of 9 runs at load 4 to 6.5. Found and fixed within M36 Flight 5's Batch C fix pass.

## Sign-Off
- **Fixed in:** Mission 36 Flight 5, the Batch C fix pass (Developer).
- **Reviewed:** by the Flight Director, who read the `_drawer.py` diff and accepted it,
  2026-11-23. It is a test-harness wait with no product change, and the root cause was found by
  a separate investigator who did not write the fix. The squawk was not put through a separate
  Reviewer spawn; the FD's reading stands as the sign-off.
- **Committed:** in the Flight 5 Batch C checkpoint commit (its ref is in the flight log).
