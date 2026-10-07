# Leg: chat-and-test-fixes

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

Close the two WebSocket edge cases (squawks 0119 and 0120, flight DD5), make the
Knowledge re-index test wait on a real signal (0115), and pin the deleted-agent heal of a
restored `#chats/~new/{agent}`, the Flight 4 action item.

## Context

- **Flight DD5** is the contract. Neither fix changes a message's shape.
- **Squawk 0119.** In `websocket_endpoint`'s `join` branch, the previous subscription is
  removed only when the requested id differs from the bound one. A degraded restore of the
  **same** id sets `session = None` but leaves the socket subscribed. Follow the
  `not_found` branch's pattern: when the socket is bound to that id, remove the
  subscriber in the degraded branch too.
- **Squawk 0120:**
  - **The fault.** A turn is spawned as a background task (`_spawn_web_message`, around
    `app.py:959`, tracked in `_session_inflight`). A `cancel` already queued on the socket
    can cancel the task before its first step. Then neither the coroutine's
    `async with session_locks[...]` nor `_process_and_broadcast`'s `except
    asyncio.CancelledError` (the only sender of `{"type": "cancelled"}`, around line 2298)
    ever runs, so the client stays busy.
  - **The same gap** applies to a task cancelled while it waits on the session lock
    inside `_spawn_message_processing` (around line 913), before
    `_process_and_broadcast`.
  - **The constraint:** **at most one `cancelled` per `cancel`**, even when one cancel
    hits a running task (which sends its own) and a never-started one.
- **Squawk 0115.** The test waits for `indexed: 3` after "Re-index all", but that text is
  already showing, so the search can run mid-reindex. The same file already uses the
  robust signal: `content_freshness` moves only when a file actually re-indexes (around
  line 1280, `body["content_freshness"] != initial_freshness`).
- **The Flight 4 action item.** `test_flow_chat_start_flow.py`'s
  `test_new_chat_route_hydrates_and_heals` heals an unknown, `default` and malformed
  agent, cold and warm, but not a **deleted** one (a pending chat whose agent was deleted
  afterwards). The heal path is `chat.js` `heal()`, around line 772, reached when
  `!agentListed(list, agent)`, around line 755.

## Inputs

Legs 1a and 1b's uncommitted work. This leg touches `app.py`'s WebSocket handler and two
browser test files only. Run it after 1b lands.

## Acceptance Criteria

- [ ] **0119.**
  - **The fix.** In the `join` branch's degraded path, `if session is not None:
    remove_subscriber(session.id, ws)` before `session = None` and the degraded
    `session_joined` frame. A join of a *different* id is unchanged. The client does not
    rely on later frames after a degraded join.
  - **Unit test.** Reuse the `TestExistingIdJoins` pattern (`_precreate`,
    `recorder.missing_agents`, `_probe`), with `{"action": "join", "session_id": sid}`:
    - bind the socket, make the agent missing, then re-join the same id;
    - assert the degraded frame arrived, `subscribers_for(sid)` excludes the socket, and a
      probe broadcast no longer reaches it.
- [ ] **0120.**
  - **The fix.** A `cancel` that cancels a task before it starts, or while it waits on the
    session lock, still sends **exactly one** `{"type": "cancelled"}` to the session. A
    cancel that hits a task already inside `_process_and_broadcast` still sends exactly
    one (its existing `except` block). Two tasks hit by one cancel never produce two
    `cancelled` frames.
  - **The mechanism** (from the design review; a `try`/`except` inside the coroutine alone
    **cannot** cover a task cancelled before its first step, because no body code runs):
    - **Two markers.** The spawned coroutine's **first statement** records the task as
      *started* (for example `_started_tasks.add(asyncio.current_task())`), and
      `_process_and_broadcast`'s entry records it as *running*. Both are discarded when
      the task finishes.
    - **A per-cancel token.** The `cancel` branch synchronously creates a fresh per-session
      token (`{"sent": False, "running": <any task in the batch is running>}`) **before**
      any `t.cancel()`. It is kept in a small module-level dict beside
      `_session_inflight`, dropped when `_session_inflight[sid]` empties, and reset in the
      harness's `_reset_state`. A lifespan-shutdown cancel with no token still sends.
    - **One sender helper.** `_notify_cancelled_once(session)` sends `{"type":
      "cancelled"}` only if the session's token is absent or unsent, and marks it sent.
    - **The started, running task is the sole sender whenever one exists** (the designer's
      decision). It sends from its existing `except`, **after** persisting partial text,
      through the helper.
    - **The lock-wait wrapper.** It wraps `async with session_locks[...]` and the call to
      `_process_and_broadcast` with `except CancelledError: if not token.running:
      notify_once; raise`. That covers case (b) and the window before
      `_process_and_broadcast`'s `try` (the Ollama preload, the user echo).
    - **The `cancel` branch** sends through the helper **only when no task in the batch
      was started**, which is case (a).
    - **Scope.** Only the WebSocket spawn path (the tasks registered in
      `_session_inflight`) changes. Other `_process_and_broadcast` callers are untouched.
  - **Partial-text persistence** for a started turn is unchanged.
  - **A harness change.** `FakeWebSocket.receive_text` yields (`await asyncio.sleep(0)`)
    before each frame, which makes case (a) unconstructible. Add a no-yield step type
    (for example `NoYield({...})`) that skips that sleep, and list it under Files
    Affected.
  - **Unit tests,** each asserting exactly one `cancelled` frame and a clean
    `_session_inflight` / `is_session_processing` end state:
    - **(a) a cancel before the spawned task starts:** send a message, then an immediate
      `NoYield` `cancel`;
    - **(b) a cancel while the task waits on the session lock:** a `Do` step holds
      `session_locks[sid]`; send a message and poll until the task exists and is blocked;
      send `cancel`; release the lock; assert `not session_locks[sid].locked()`;
    - **(c) a cancel of a running turn:** gate "slow" through `recorder.gates`, wait on
      `started("slow")`, then `cancel`;
    - **(d) one cancel over a running turn and an unstarted one:** a gated running turn,
      then a second message, then an immediate `NoYield` `cancel`. The single `cancelled`
      comes from the running task, after its partial save.

    Also run `tests/test_cancel.py` and the other cancel tests, since
    `_process_and_broadcast`'s `except` is rerouted through the helper.
  - **The squawk's browser check** ("Stop at once, then Send re-enables") is **dropped**.
    WebSocket frames cannot be ordered deterministically from Playwright, and the unit
    tests above pin the server behaviour the client reacts to. Record the reason in the
    squawk's Verification.
- [ ] **0115.** `test_detail_view_indexing_poll_reindex_and_search`:
  - **Before the click:** after the "changed" step's `indexed: 3` wait, and immediately
    before the "Re-index all files" click, record `content_freshness` from `GET
    /api/knowledge-bases/{kb_id}/status`.
  - **After the click:** wait until it has changed **and** no item is pending or indexing
    (`items.get("pending", 0) == 0 and items.get("indexing", 0) == 0`; `content_freshness`
    moves when the *first* file re-indexes). Then search.
  - **Two checks first:**
    - whether `indexed_at` has sub-second resolution, or a same-second finish could leave
      the value unchanged (if second-granular, also wait for a pending or indexing count
      above 0 or a changed per-item `indexed_at`);
    - that `scope=all` rewrites `indexed_at` for each file.
  - There is no fixed sleep, and the bounded wait fails loudly.
- [ ] **The deleted-agent heal.** A new test in `tests/browser/test_flow_chat_start_flow.py`
  (`chats` lane):
  - seed an agent and open `#chats/~new/{agent}` (pending);
  - delete the agent through the API;
  - **cold:** reload, and the route heals to `#chats`, idle (the welcome or empty state),
    with no session created;
  - **warm:** a history traversal back to the pending route heals the same way.
  - **The fix is expected, not conditional.** `chat.js`'s pending-route hydrate trusts
    `App.store.peek('agents')` when it is loaded. An API-side delete invalidates nothing,
    so a warm traversal keeps a pending chat for a deleted agent.
    - **The change:** keep the peek fast path, so the pending pane renders at once, then
      also run a background `App.store.get('agents', {force: true})` and re-run the
      pending validation. A missing agent heals to `#chats`.
    - **Request counts.** That is one extra `/api/agents` request per `~new` hydrate. Grep
      the browser tests for pinned request counts (`agents.md` "Client data store" lists
      some) and update them in place, saying so.
  - **The test** keeps the delete on the API path. Deleting through the UI would
    invalidate the store and hide the hazard. It mirrors the existing heal test:
    `_wait_state(page, "idle")`, `expect(_chats.welcome(page))`, `assert _sessions(base)
    == []`.
- [ ] **Squawks 0115, 0119 and 0120** get their Corrective Action and Verification written
  and are marked `completed` (commit reference "pending the Flight 6 legs 1–3 commit").
- [ ] **Docs.** `the_one/agents.md`'s WebSocket protocol notes mention the
  `cancelled`-for-unstarted rule and the degraded same-id unsubscribe, in one or two lines
  each.
- [ ] **Gates.**
  - `ruff` passes; `TEST_TIMEOUT=3000 make test-unit` passes.
  - The `chats` and `library` lanes pass (`THE_ONE_TEST_NETNS=1`).
  - The `shared` lane passes (`TEST_TIMEOUT=3600`): the WebSocket changes reach every
    chat surface.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ws_start_session.py -x
  --timeout 60`, plus the other WebSocket test files.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser
  tests/browser/test_flow_chat_start_flow.py -x`, then the lanes in the background.

## Implementation Guidance

1. **Read** `websocket_endpoint`'s `join`, `cancel` and `start_session` branches,
   `_spawn_web_message`, `_spawn_message_processing` and `_process_and_broadcast`'s
   cancellation block. The squawks' Report sections carry the reproductions.
2. **0119:** the fix and its test.
3. **0120:** the dedupe design, then the fix and its four tests.
4. **0115:** the test fix.
5. **The heal test.**
6. **Squawks, docs and gates;** then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **A cancel with nothing in flight:** no `cancelled` is sent. That is today's
  behaviour; keep it.
- **The socket disconnects between the cancel and the send:** the send fails quietly, as
  other sends do.
- **A connector-driven turn on the same session** (no WebSocket client): `cancelled` goes
  to the session's subscribers. That is unchanged.
- **The session lock released while a waiting task is cancelled:** the lock's context
  manager is never entered, so there is nothing to release. Verify no lock is left held.

## Files Affected

- `the_one/interfaces/web/app.py`: the WebSocket branches and the spawn helpers.
- `tests/test_ws_start_session.py` (the `NoYield` harness step and the new tests), or a
  sibling WebSocket test file.
- `the_one/interfaces/web/static/js/areas/chat.js`: the pending-route background forced
  `agents` read.
- `tests/browser/test_flow_studio_knowledge_inventory.py`,
  `tests/browser/test_flow_chat_start_flow.py`.
- Squawks 0115, 0119, 0120; `the_one/agents.md`; the flight log.

## Citation Audit

Checked on 2026-10-06 in the working tree:
- **`app.py`:** `_session_inflight` (line 711), `_spawn_message_processing` (line 913),
  `_spawn_web_message` (line 959), `_process_and_broadcast` (line 1963), the `cancelled`
  send (line 2298), the `cancel` loop (line 3039).
- **`test_flow_studio_knowledge_inventory.py`:** the `content_freshness` precedent
  (around line 1280).
- **`test_flow_chat_start_flow.py`:** `test_new_chat_route_hydrates_and_heals` (around
  line 417).
- **`chat.js`:** `heal` (around line 772).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
