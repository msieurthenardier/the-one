# Leg: ws-start-protocol

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Add the server side of "create the session on the first send" (DD1). That means:
- a non-persisting `leave` WebSocket action;
- an atomic, idempotent `start_session` action that validates first, joins an existing id,
  reserves the id, creates strictly, swaps the subscription, sends `session_joined` with
  `is_processing: true`, spawns the message task, and sends a typed `start_failed` on
  every non-success exit;
- a payload validator shared with the normal message path, and the broadened
  auto-create catch.

All of it gets unit tests that drive the real WebSocket endpoint. `new_session` stays
until leg 3.

## Context

- **Flight DD1** is the authoritative design. Read the "Server order" and the
  "Reconnect" bullets in full.
- **Why a separate leg.** Flight review cycle 2 split the start-flow core at the
  backend/client seam. The client (leg 3) builds on a protocol that is already proven by
  unit tests.
- **No client change in this leg.** `chat.js` keeps sending `new_session`. The browser
  suites therefore stay green unchanged.
- **The WebSocket loop is sequential per socket.** The cross-socket reconnect race (an old
  handler still inside a slow `factory.create` when a new socket re-sends the same id) is
  what the id reservation closes.
- **Today's ids** are `uuid.uuid4().hex[:12]` (`app.py` `_create_session`). Client ids are
  32 lowercase hex characters; both are valid, and nothing parses the length. The
  `mcp/oauth/handlers.py:27-40` docstring says "12-char", and its wording is updated (its
  charset argument still holds).
- **`join` of an unknown id** fell through to **auto-create a default-agent session**
  (`app.py` `join` branch). This leg changes that to a `join_failed` frame (AC8a), so the
  client can never be handed a session it did not ask for.

## Inputs

- `the_one/interfaces/web/app.py`:
  - `websocket_endpoint` (around 2469) and its `join`, `list_sessions`, `new_session`,
    `delete_session` and `cancel` branches;
  - the message path: validation (around 2621–2687), the bare auto-create (around
    2688–2700), `/reset`, `_build_user_content`, `_spawn_message_processing` and the
    `_session_inflight` bookkeeping (around 2701–2760);
  - `_create_session` (around 1115–1155), which swallows the DB insert failure;
  - `_get_or_restore_session`;
  - `_build_session_joined_ok` (around 1382–1412), with `is_processing` from the lock;
  - `_send_pause_snapshot_if_needed`;
  - `add_subscriber`, `remove_subscriber` and `subscribers_for`.
- `tests/test_ws_message_branch_crash_guard.py`: the harness that drives the real
  `websocket_endpoint` with a monkeypatched `_create_session`.

## Outputs

- `app.py`:
  - `_validate_message_payload(payload) -> ValidatedPayload`, a `NamedTuple` of
    `(user_input, images, content, error, empty)`, used by the message path and by
    `start_session`;
  - a module constant `_START_RESERVATION_WAIT_S = 30`;
  - `_restore_session`'s skip-rebuild guard (around 1241) extended with
    `or bool(_session_inflight.get(session_id))`;
  - a `leave` branch;
  - a `start_session` branch;
  - `_create_session(..., strict=False)` gains `strict`;
  - a module-level `_start_reservations: dict[str, asyncio.Future]`;
  - the bare auto-create catch broadened to `except Exception` with logging;
  - a shared `_spawn_web_message(session, content, ws)` helper used by both paths, so the
    `_session_inflight` bookkeeping is not duplicated.
- Tests: a new `tests/test_ws_start_session.py` in the crash-guard harness style, plus any
  adjustment to existing WebSocket tests.
- Docs: `the_one/agents.md`, a "Chat WebSocket protocol" note listing `leave`,
  `start_session`, `start_failed` and the idempotency rule. `CLAUDE.md` gets one line, if
  it documents WebSocket actions.

## Acceptance Criteria

- [ ] **AC1. Shared validation.** `_validate_message_payload(payload)` returns a small
  result `(user_input, images, content, error, empty)`:
  - **`empty=True`** when there is neither text nor images. The message path keeps
    today's **silent** `continue`, and `start_session` sends `start_failed` with
    `"Message is empty."`.
  - **`error`** carries exactly today's texts:
    - a malformed images payload;
    - too many images;
    - an oversized image;
    - a content-build failure (`"Cannot process message: {exc}"`).
  - **Type checks.**
    - `message: None` is treated as `""`, so `message: null` stays empty and silent as
      today.
    - Any other non-`str` returns the error `"Message must be text."`. Both paths send it:
      the message path as a `system` frame, and `start_session` as `start_failed`.
  - A `/reset` with a malformed image now errors instead of clearing. That is benign and
    is recorded with the order change.
  - **The order change.** The content build (`_build_user_content`) now runs in the
    validator, **before** the auto-create, so a build failure no longer creates a session.
    That is intended and benign; record it in the flight log.
    `test_ws_message_branch_crash_guard.py`'s `create_calls` assertions still hold.

  The normal message path uses the validator. Apart from the order change, its behaviour
  is unchanged, and the existing WebSocket tests stay green.
- [ ] **AC2. `leave`.** `{action:"leave"}` with a bound session:
  - calls `remove_subscriber(session.id, ws)`;
  - touches `session.last_activity`;
  - sets the loop's `session = None`.

  It does **not** cancel in-flight tasks, writes nothing to the DB and sends **no** frame.
  Without a bound session it is a no-op. A test asserts that, after `leave`, a frame
  broadcast to the old session (through `_send_to_session`) does not reach this socket,
  and that a running turn still completes.
- [ ] **AC3. `start_session` validation.** The payload is
  `{action:"start_session", session_id, agent_name, message, images}`, with the same
  message keys as a normal message.
  - Each of these sends exactly one `{type:"start_failed", session_id, error}` and
    creates nothing (no `_sessions` entry, no DB row):
    - a `session_id` that is not a `str` or not `^[0-9a-f]{32}$`. Check the type first:
      `re.fullmatch` on a non-string raises;
    - an `agent_name` that is not a non-empty `str`, or is `"default"`;
    - an empty message with no images;
    - **a `/reset` first message** (`"A new chat cannot start with /reset."`). With no
      task spawned, the forced `is_processing: true` would leave the client stuck busy;
    - each image-validation failure;
    - a content-build failure.
  - It then `continue`s, and never falls into the message path.
  - The socket's previously bound session stays bound, because nothing was swapped.
- [ ] **AC4. An existing id joins.**
  - **A lookup failure is caught.** The `await _get_or_restore_session(sid)` call alone
    sits in a narrow `try/except Exception` (logged). On failure it sends `start_failed`
    and `continue`s; `_restore_session` maps only a few error types, and a DB error or an
    `ImportError` must not kill the socket. A test injects a lookup failure.
  - If the lookup is not `not_found`, `start_session` behaves exactly like `join`:
  - **OK:**
    - it leaves any previously bound session that is a different session;
    - it subscribes;
    - it sends `_build_session_joined_ok`;
    - it sends the pause snapshot;
    - it does **not** process the message again, **unless** the session's history is
      empty and no task is in flight for it (`not _session_inflight.get(sid)`). Then the
      first message was never delivered (a disconnect between the create and the spawn),
      so it **is** processed now. This refines DD1's "not processed again" to "processed
      exactly once", and the flight log records it. A test covers both branches.
  - **Degraded:** it calls `remove_subscriber` for **whatever was bound**, then sets
    `session = None` and sends the degraded joined frame. Do not copy the `join` branch's
    latent behaviour, which only removes a subscription when the id differs.
  - This holds even when the existing session belongs to another agent.
  - A test re-sends the same `start_session` twice on one socket, and once again on a
    second socket. It asserts:
    - one `_sessions` entry;
    - one DB row;
    - one message processed;
    - each socket receives `session_joined` for the same id.
- [ ] **AC5. Reservation, taken first.** After validation, the reservation is a
  **synchronous check-and-set** with no await between the check and the insert. On the
  single event loop that is atomic, so the dict needs no lock.
  - **If the id is already reserved**, the handler awaits
    `asyncio.wait_for(asyncio.shield(fut), _START_RESERVATION_WAIT_S)`.
    - **The shield is required.** Without it, a waiter's timeout, or its own handler's
      cancellation, would cancel the **shared** future for every other waiter.
    - On `asyncio.TimeoutError` it sends `start_failed`.
    - Then it runs the `_get_or_restore_session` lookup:
    - if the session now exists, it **joins** (AC4) without processing again;
    - if the creator **failed** (`not_found`), this waiter **becomes the creator** and
      processes its own message, re-entering the reservation step.
  - **If not reserved**, it inserts a new future, then runs the lookup **inside** the
    reservation, then joins (AC4) or creates (AC6–AC7).
  - **This loops until a lookup or create decision is reached.** With several waiters, a
    failed creator wakes them together: one re-reserves, and the others see the new
    reservation and wait again. The bound applies per wait.
  - The `finally` does `if not fut.done(): fut.set_result(None)` and then pops the id.
  - **The test.** Drive two sockets with `asyncio.gather(websocket_endpoint(a),
    websocket_endpoint(b))`, using a `_create_session` stub that parks on an
    `asyncio.Event`. A gate releases socket B's `start_session` only once A is inside the
    create; then A's event is released. Assert one create, one processed message and both
    sockets joined.
  - **A second test:** A's create fails, and B then creates and processes its own
    message.
  - **A third test** (with the constant patched small): a waiter times out and gets
    `start_failed`, and the creator and a second waiter still complete normally.
- [ ] **AC6. Strict create.**
  - `_create_session(agent_name, session_id=sid, strict=True)` pops `_sessions[sid]`
    under `_sessions_lock` and re-raises, on a DB persist failure **or a cancellation**.
    The strict branch catches `BaseException`, so a disconnect cancelling the task during
    `repo.create` cannot leave an in-memory session with no row.
  - With `strict=False`, today's behaviour is unchanged (`except Exception`, swallowed);
    a test pins that the failure is still swallowed.
  - The `try/except Exception` wraps **only the strict create**. It logs, sends
    `start_failed` with the error text, and leaves the previous binding intact.
  - **The swap, the joined frame, the snapshot and the spawn sit after the try.** A
    failure there (for example `WebSocketDisconnect` from `send_json`) must not send
    `start_failed` for a session that was created and bound.
  - A test injects a `factory.create` failure and a persist failure. In both cases there
    is no `_sessions` entry and no DB row, and `start_failed` is sent.
- [ ] **AC7. Swap, joined, spawn.** Only after a successful create:
  - remove the subscription to the previous session, if any;
  - **bind and subscribe the new one before the first `send_json`.** Assign the loop's
    `session = new_session` and call `add_subscriber`. Then the outer
    `except WebSocketDisconnect` cleans up correctly if a send fails;
  - send `_build_session_joined_ok(session, is_processing=True)`, through a new optional
    parameter `is_processing: bool | None = None` (`None` means derive from the lock, as
    today). Do not mutate the returned dict;
  - send the pause snapshot;
  - spawn the message through `_spawn_web_message`, the same helper as the normal path,
    with the `_inflight_tasks` and `_session_inflight` bookkeeping.
  - **The existing-id join (AC4)** sets `is_processing` from
    `bool(_session_inflight.get(sid)) or is_session_processing(sid)`. That covers a first
    turn spawned but not yet holding its lock.
  - A test asserts the frame order, `session_joined` (`is_processing: true`) before any
    `assistant*`/`done` frame, and that the reply is persisted under the new id with the
    agent name.
- [ ] **AC8. The broadened auto-create catch.** The bare-message auto-create catches
  `except Exception` (logged), not only `(ValueError, KeyError)`, matching `join` and
  `new_session`. A test injects an `ImportError` from `_create_session` and asserts a
  `system` frame and a live socket.
- [ ] **AC8a. `join` of an unknown id fails instead of auto-creating.** A `join` with a
  non-empty `session_id` whose lookup is `not_found`:
  - removes the subscription to any previously bound session;
  - sets `session = None`;
  - sends `{type: "join_failed", session_id, error: "not_found"}`;
  - **creates nothing**.

  Today it falls through to auto-create a default-agent session, which orphans sessions
  and forced the client to guess. Leg 3b's design review asked for this (question 2).
  - A `join` **without** a `session_id` keeps today's behaviour: an idempotent re-bind, or
    the auto-create when nothing is bound. No client path uses it.
  - A test asserts the `join_failed` frame, that no session or row was created, and the
    unbinding.
  - `the_one/agents.md`'s protocol note lists `join_failed`.
- [ ] **AC8b. The restore guard.** `_restore_session`'s skip-rebuild guard (around 1241)
  becomes `is_session_processing(session_id) or bool(_session_inflight.get(session_id))`.
  A first turn that was spawned but does not yet hold its lock is then never rebuilt from
  the empty DB snapshot. A test pins this.
- [ ] **AC9. `new_session` untouched.** Its behaviour and its callers (`chat.js`, browser
  tests) are unchanged in this leg; leg 3 removes it.
- [ ] **AC10. Gates.** `make lint`, `ruff format --check`, `make test-unit`, and the chats
  lane (`THE_ONE_TEST_NETNS=1`, through `scripts/run-tests.sh`) as a no-regression check.
  The numbers go in the flight log.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ws_start_session.py
  tests/test_ws_message_branch_crash_guard.py -x --timeout 60`.
- `make test-unit`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=1200 bash
  scripts/run-tests.sh --lane chats -x`.
- **Falsify AC4 and AC5** once each, and record the result in the flight log:
  - remove the existing-id check, and the double-send test must fail;
  - remove the reservation, and the concurrent test must fail.

  Restore each afterwards.

## Test Harness

Prescribed by the design review:
- **Copy, don't reuse.** Copy `FakeWebSocket` from
  `tests/test_ws_message_branch_crash_guard.py` into the new file. That file's autouse
  `_stub_session_and_spawn` fixture (lines 115–121) patches `_create_session` and
  `_spawn_message_processing` to no-ops with no DB, so it is **not** reused for the
  persistence tests.
- **A real DB.** The `isolated_db` fixture (`tests/conftest.py` around 306); count rows
  with `ChatSessionRepository.list()` and read one with `ChatSessionRepository.get(sid)`.
  `chat_sessions.agent_name` has no FK (it was dropped around `schema.py:201`), so **no
  agent row is seeded**. `_ensure_ollama_model_loaded` returns early for an agent with no
  DB record.
- **A fake factory.** Monkeypatch `app_module._get_factory` to return a factory whose
  `create()` returns a fake agent modelled on **`tests/test_cancel.py` around 40–110**
  (`_LLMShim`, `_QuickAgent`). It has `messages`, `llm` and `_deferred_tool_calls`, and an
  async-generator `step`.
  - For AC7's persistence assertion, the fake `step` must `self.messages.append(...)` and
    `yield Message(role=Role.ASSISTANT, content=...)`. `_save_session_to_db` encodes
    `session.agent.messages`.
  - Do **not** patch `_send_to_session` or `_save_session_to_db`.
- **`FakeWebSocket` scripts** gain awaitable steps (an `asyncio.Event` gate) for AC5.
  `receive_text` already yields with `asyncio.sleep(0)`.
- **Assert** on `ws.sent` frames and on `_sessions`, not on subscriber state after the
  script ends. The disconnect handler removes subscribers.
- **An async autouse cleanup fixture** (`asyncio_mode = "auto"`), mirroring
  `tests/test_cancel.py` around 127–135:
  - cancel and gather `_inflight_tasks`;
  - clear `_session_inflight`, `_start_reservations` and **`app_module._sessions`**
    (`the_one.sessions.clear_for_test` clears only the lock and subscriber registries);
  - call `clear_for_test` and `clear_locks_for_test`.

  Tests **await the spawned task** (from `_inflight_tasks`) before asserting persistence.
  `FakeWebSocket` raises `WebSocketDisconnect` when its script runs out, and the task
  outlives `websocket_endpoint`.

## Implementation Guidance

1. **Extract `_validate_message_payload`** from the message path (the `message` type,
   then shape, count and size, then the content build). It returns a `ValidatedPayload`
   NamedTuple:
   - `message: None` becomes `""`;
   - any other non-`str` gives the error `"Message must be text."`;
   - `empty` is True when there is no text and no images.

   The message path sends `system` frames with the same text, keeping the silent empty
   `continue`.
2. **Extract `_spawn_web_message(session, content, ws)`** from the tail of the message
   path, covering the task and both inflight bookkeeping sets.
   - `/reset` stays in the message path only.
   - `start_session` rejects `message == "/reset"` exactly. The message path compares
     with `==`, unstripped.
3. **The `leave` branch**, near `join`.
4. **The `start_session` branch.** Order:
   1. **Validate**, each failure sending `start_failed`: the type and format of `sid`,
      then the agent, then the payload (empty, `/reset`, images, content).
   2. **Reserve** synchronously. If the id is already reserved, `await
      asyncio.wait_for(asyncio.shield(fut), _START_RESERVATION_WAIT_S)` (timeout →
      `start_failed`), then go to step 3. Loop until a lookup or create decision is
      reached; the bound applies per wait.
   3. **Look up** `_get_or_restore_session(sid)` inside the reservation, in its own
      narrow `try/except Exception` (`start_failed` on error):
      - **OK:** leave the previous session, bind and subscribe, send joined
        (`is_processing` from the inflight set), send the snapshot. If the history is
        empty and nothing is in flight, spawn the message (AC4). Then `continue`;
      - **degraded:** `remove_subscriber` for whatever was bound, set `session = None`,
        send the degraded frame, `continue`.
   4. **Strict create** inside `try/except Exception`, the only thing the try wraps; on
      exception send `start_failed` and `continue`.
   5. **After the try:** swap (**bind and subscribe before the first send**), then joined
      (`is_processing=True`), then the snapshot, then `_spawn_web_message`.
   6. **`finally`:** resolve the future if not done, and pop it.
5. **`_create_session(strict=...)`**: in the persist `except`, if `strict`, pop
   `_sessions[sid]` under `_sessions_lock` and re-raise.
6. **Broaden** the bare auto-create catch.
7. **Tests**, per the Test Harness section:
   - drive `websocket_endpoint` directly with a copied `FakeWebSocket`;
   - use `isolated_db`;
   - patch `_get_factory`, and patch `_create_session` only where a test needs to park or
     fail it.
8. **Docs:** the `agents.md` protocol note, and the `mcp/oauth/handlers.py` docstring
   wording.

## Edge Cases

- **`start_session` while a turn is running on the bound session:** the swap leaves the
  old session. Its turn completes and persists, as with `join`. Its later frames do not
  reach this socket.
- **The same socket re-sends `start_session` after it is already bound to that id:** the
  existing-id path re-binds idempotently. Do not double-subscribe; check
  `subscribers_for`.
- **The client id collides with an existing session of another agent** (a vanishingly
  unlikely random collision): AC4 joins it. That is accepted per DD1, question 2.
- **The degraded path on an existing id** (a deleted agent): `session = None`, and the
  degraded frame is sent with no processing.
- **The reservation future must always be resolved.** Resolve it with a result in
  `finally`, or waiters hang. Waiters re-run the existing-id lookup.
- **A constraint for leg 3.** A plain `join(sid)` landing between `_create_session`'s
  `_sessions[sid] = session` and its DB insert pops the in-memory entry. The reservation
  does not cover `join`, so **leg 3 must re-send `start_session` while starting, never
  `join`**. Record this in the flight log for leg 3.
- **A disconnect between the create and the spawn.** The session persists empty. Leg 3's
  re-send of `start_session` takes the existing-id path, which **delivers** the message
  because the history is empty and nothing is in flight (AC4). The first message is
  therefore never lost.
- **`start_failed` echoes `session_id`** when it was a `str`, and `null` otherwise.
- **`leave` after the bound session was deleted** is a no-op beyond setting
  `session = None`; covered by a test.
- **A disconnect after `leave`**: the disconnect handler sees `session = None` and does
  nothing; covered by a test.

## Files Affected

- `the_one/interfaces/web/app.py` — the validator, the helpers, the `leave` and
  `start_session` branches, `join`'s `join_failed` for an unknown id, `_create_session(strict)`, the reservations dict with
  `_START_RESERVATION_WAIT_S`, the broadened catch, the `_build_session_joined_ok`
  parameter and the `_restore_session` guard.
- `tests/test_ws_start_session.py` — new.
- `tests/test_ws_message_branch_crash_guard.py` — only if the extraction moves a
  monkeypatch target.
- `the_one/agents.md` — the protocol note.
- `the_one/mcp/oauth/handlers.py` — the docstring wording.

## Citation Audit

Checked by the Flight Director against `af86324`:
- `app.py` `_create_session`: lines 1115–1155, with `sid = session_id or
  uuid.uuid4().hex[:12]` and the persist failure swallowed by
  `except Exception: logger.warning(...)`.
- `websocket_endpoint`: line 2469. `join`: lines 2480–2541, with the `not_found`
  fall-through to auto-create. `new_session`: lines 2559–2580.
- The message validation: lines 2621–2687. The bare auto-create catch:
  `except (ValueError, KeyError)` at line 2693.
- The content build and spawn: lines 2715–2760.
