# Leg: chat-row-status

**Status**: planned
**Flight**: [Chats, and closing every count to zero](../flight.md)
**Origin**: HAT step 3 (operator, 2026-10-28): "we also need a thinking indicator on the chat row item in the list to indicate thinking/done". Operator choice: build it in this flight. New behaviour, so it goes through the fix-vs-feature gate.

## Objective
Each Chats-list row shows a quiet "working" indicator while its session has a turn running. This applies to web and connector turns, and to chats the operator is not looking at. When a turn ends in a chat that is not open, the row shows a "new reply" marker until the operator opens it.

## Context
- **Server busy truth.** Web and connector turns both run inside `async with session_locks[id]`: `app.py` ~1104 for web, `connectors/inbound.py` ~477 for connectors. `is_session_processing(id)` (`the_one/sessions/_locks.py`) reads that lock. A web turn spawned but not yet holding the lock is in `_session_inflight[id]` (`app.py` ~832, and ~1636-1639 already combines both checks).
- **Chats list data.**
  - `_session_to_list_payload` (`app.py` ~1830) feeds the WebSocket `session_list` and the coalesced `sessions_changed` push (`_SessionsPushListener`, `app.py` ~125-180, 250 ms window).
  - `_session_summary` (`api.py` ~5247) is the REST `GET /api/chat/sessions` row that `App.store` `sessions` primes from.
  - The client maps both shapes into the store (CLAUDE.md "Client data store").
- **The list.** `areas/chat/chats-list.js` builds an `App.ui.listPane` (`rowStyle: 'chats'`, `js/ui/list-pane.js`). Rows carry title, time, agent and badges. There is no per-row status slot yet. Adding one means a library option, a catalogue row update and engine-parametrized contract tests (CLAUDE.md "Control library").

## Design (to confirm at design review)
- **Server: a `busy` flag.**
  - Add `busy: bool` to `_session_to_list_payload`, and to `_session_summary` if needed for store parity. It is computed at projection time from `is_session_processing(id) or bool(_session_inflight.get(id))`.
  - Turn start and turn end each call the sessions push listener's `notify()`, after acquiring and after releasing the lock, in both the web and the connector paths. The coalesced `sessions_changed` then carries the new state to every socket.
  - The design review checks two things. First, how `notify` is reached from `inbound.py` without an import cycle (the db-layer listener hook may already fire on the turn's writes). Second, that a turn's end is not pushed before its final write.
- **Client: working.** A row whose session is `busy` shows a small animated indicator in a new `App.ui.listPane` row slot, for example a `status` field. It has a visually hidden "Working" in the row's name and no layout shift. It must honour `prefers-reduced-motion`, so a static dot replaces the animation.
- **Client: new reply.**
  - When a session goes from `busy` to not busy while it is not the open chat, the row shows a "new reply" dot, with a visually hidden "New reply" in its name.
  - Opening that chat clears the dot.
  - The state is client-side and per window. It does not survive a reload, which is acceptable for a first cut; confirm at review.
  - The open chat itself shows no dot, since its transcript already shows the turn.
- **Pending row.** The pending "New chat" row has no session and no status.
- **Contrast.** The indicator and dot use existing tokens and meet 3:1 as UI components in both themes, on both resting and selected rows.

## Acceptance Criteria
- [ ] A web turn in chat A: A's row shows "working" while the turn runs, including from another chat or another tab, and it clears at `done`. The same holds for a stub-connector turn.
- [ ] A turn that finishes while A is not open leaves a "new reply" dot on A. Opening A clears it. The open chat never shows the dot.
- [ ] Accessibility: the status is in the row's accessible name; no layout shift; reduced motion is honoured; contrast passes, with the `test_design_tokens_a11y.py` rows added.
- [ ] Server tests: the `busy` field in both projections, and a push at turn start and end (web and connector). Library contract tests for the new listPane option run in both engines, with a catalogue row update. Browser tests cover working, done and new reply, including a connector turn through the stub seam.
- [ ] The chats, contracts and routing lanes pass, with the unit tier. CLAUDE.md "Chats list and agent picker" and the store notes, plus `the_one/agents.md`, are updated. Add ledger row 49.

## Verification
- Unit: the projection and push tests.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts -x`, plus `--lane chats -x`.
- The HAT re-walks step 3 and step 5 (the connector update while another chat is open).

## Design Review Amendments (cycle 1, Developer/Sonnet, 2026-10-28: needs rework; this section replaces the Design above where they differ)
- **"New reply" comes from a server sequence, not from watching `busy`.** The 250 ms coalescing reads state at push time, so a short turn's busy edge is never seen.
  - The server keeps a process-local `turn_seq[sid]`, bumped when a turn ends (done, cancel or error).
  - The client keeps `seen[sid]`. A row shows the dot when `turn_seq > seen` and it is not the open chat.
  - The open chat sets `seen = turn_seq` on a successful join (not on click) and on its own `done`.
  - The first prime after a page load sets every baseline silently. A socket reconnect does NOT re-baseline: a reply that landed during the gap is a real new reply.
  - It is not persisted, and a server restart resets the counters; both are acceptable for a first cut.
  - A Stop or an error in a chat that is not open also lights the dot.
- **One turn seam: a `track_turn(sid)` async context manager in `the_one/sessions/_locks.py`.**
  - It wraps the lock in both `app.py` ~1104 and `connectors/inbound.py` ~477.
  - On enter (lock acquired) it calls `the_one.db._session_changes.notify_sessions_changed()`.
  - On exit, AFTER the lock is released, it bumps `turn_seq[sid]` and notifies again. This guarantees the end push never carries `busy: true`.
  - `notify_sessions_changed` is a stdlib-only leaf that `_sessions_push.notify` already listens on (app.py ~472), so there is no import cycle and connectors are covered.
- **`busy` is answered by the sessions module.**
  - Add `is_session_busy(sid)` (lock held OR registered in-flight) in `the_one/sessions/`.
  - Move the in-flight registry's read side (or a mirror `register`/`clear`) out of `app.py`, so `api.py` can answer it without a cycle.
  - A turn paused for MCP sign-in releases the lock, so the row reads idle. This is stated, not a defect.
- **Both projections carry `busy` and `turn_seq`:** `_session_to_list_payload` (app.py) and `_session_summary` (api.py). Extend the `tests/test_db_api.py` key pin. Update `toSessionSummary` (`areas/chat.js` ~323) to copy both fields, otherwise every WebSocket prime drops them.
- **The library option.**
  - Name it `activity` and its class `ui-list-pane-activity`. `ui-list-pane-status` already exists, for the pane's own live node (list-pane.js ~238).
  - Values: `'working'`, `'new'`, or none. "Working" is an animated ring; "New reply" is a filled accent dot. They differ in shape, not only colour.
  - Under `prefers-reduced-motion`, the ring is static, which still differs from the filled dot.
  - Each value adds a separate visually hidden text run to the row's link name: "…, Working" or "…, New reply".
  - Add the class to both catalogue rows (`docs/ui-control-inventory.md` ~87 and ~89) and to any ownership or emitted-class expectations. Add a `tests/browser/test_ui_list_pane*.py` contract in both engines that calls the option.
  - Name the tokens up front. Add the contrast pairs (resting and selected-row wash, light and dark, 3:1 as a UI component) to `tests/test_design_tokens_a11y.py`.
- **Which rows show it.**
  - The open chat shows "working" too: it is cheap and consistent.
  - The pending row shows nothing, and a test says so.
  - An armed delete survives a `busy` flip through `setItems`; add a test.
- **Tests.**
  - Unit: the projections; the `track_turn` order (at the end signal, `is_session_processing` is already false inside a fake listener registered through `add_listener`); web and connector paths. Assert on the listener, never by sleeping for the coalescing window.
  - Browser: use the mock's `delay_ms`, or the stub seam, so "working" is observable. Cover a connector turn while another chat is open, then the new-reply dot, then its clearing on join.
- **Implementation order:**
  1. the server seam and the projections;
  2. `toSessionSummary` and the store;
  3. the listPane option, with the catalogue and contracts;
  4. the Chats list wiring;
  5. the tests and docs.
- **Sequencing.** 10b runs after 10a. The uncommitted HAT platform-badge fix in `chats-list.js` is committed first.
- **Status:** a second review cycle runs on this amended design before implementation.
