# Leg: routine-turn-path

**Status**: completed
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Teach the web turn path to carry a routine turn, without a runner yet. This
leg adds:
- the routine marker on `Message` (stored, shown in UI events, never sent to
  a provider);
- an outcome channel (`turn_info`) through the turn wrappers;
- a silent cancel for a turn still waiting on the lock;
- a spawn helper for routine turns;
- titled session creation;
- routine handling inside `_process_and_broadcast`: the live event, marker
  binding at both save sites, and cancel-safe delivery after a clean step;
- connector visibility tagging on the cancel path for every turn.

## Context

- Flight DD6 steps 6-8, DD7 (server side). Design review of the original leg 3
  split it: this is part 3a, and `routine-runner` (leg 4) is 3b. The split is
  a divert boundary. After this leg, `turn_info["routine"]` is understood but
  nothing sets it.
- From leg 2: `the_one/connectors/delivery.py` `deliver_final_reply`,
  `DeliveryResult` and `send_step_limit_line`. Re-read the leg 2 flight-log
  entry for the actual names.
- The frozen loop (`the_one/agent/core.py`) is not touched. If it seems to be
  needed, stop with `[BLOCKED:frozen-loop]`.
- **Behaviour change outside routines** (recorded in the flight log): the
  cancel path now tags connector-chat messages operator-only before saving.
  Today a cancelled web turn in a connector chat stores untagged messages, so
  they look peer-visible after reload.

## Inputs

In `the_one/interfaces/web/app.py`, verified at `c2366221`:
- `_spawn_message_processing` (`:1068`), `_locked_message_processing`
  (`:1101`) and `_spawn_web_message` (`:1146`);
- `_started_tasks`, `_running_tasks` and `_cancel_tokens` (`:847-849`), and
  `_notify_cancelled_once` (`:851`);
- `_process_and_broadcast` (`:2184`):
  - `user_event` (`:2209-2235`);
  - the pause `break` (`:2458-2472`);
  - `except CancelledError` (`:2512-2539`);
  - `except Exception` (`:2540-2549`);
  - tagging (`:2553-2564`);
  - save, `done` and `turn_info` (`:2566-2612`);
- `_create_session` (`:1527`); `Session.add_event` retitles "New chat"
  (`:783-787`).

Elsewhere:
- `the_one/llm/base.py` `Message` (`:150`), `Message.user` (`:274`);
- `the_one/db/codec.py` `message_to_dict` (`:143`), `message_from_dict`
  (`:198`), `messages_to_ui_events` (`:280`);
- test patterns:
  - `tests/test_cancel.py` and `tests/test_process_and_broadcast_live_read.py`
    build a `Session` with a stub agent and monkeypatch `_send_to_session` to
    capture frames;
  - `tests/test_track_turn.py`.

## Outputs

- `the_one/llm/base.py`, `the_one/db/codec.py`: the marker fields.
- `the_one/interfaces/web/app.py`:
  - `turn_info` threading, `_silent_cancel`, `_register_turn_task`,
    `_spawn_routine_turn`, `_create_session(..., title=None)`,
    `_bind_turn_user_marks`;
  - in `_process_and_broadcast`: routine handling, cancel-safe delivery, and
    cancel-path tagging.
- Tests:
  - `tests/test_routine_message_marker.py`, `tests/test_routine_turn_path.py`:
    new;
  - `tests/test_cancel.py`: the new connector cancel-tagging regression test,
    with existing tests unedited.
- `the_one/agents.md`: a "Routines (M33)" subsection on the turn path.

## Acceptance Criteria

- [ ] AC1. **Marker fields.** `Message` gains `routine_id: str | None = None`
      and `routine_name: str | None = None`, documented as USER-only.
      - `Message.user(...)` accepts both as keywords.
      - `message_to_dict` writes each only when set, and `message_from_dict`
        reads them, so a legacy dict decodes to `None`.
      - `messages_to_ui_events` adds them to USER events only when set.
- [ ] AC2. **No leak to providers.** For every provider converter, a USER
      message with both fields set produces a payload equal to one without
      them:
      - Anthropic `_to_api_message`, with the plan subclass inheriting it;
      - OpenAI `_to_api_message`, with OpenRouter;
      - Ollama `_to_api_message` and `_to_native_message`.

      `build_user_message_content` is unchanged.
- [ ] AC3. **`turn_info` threading.** `turn_info` is threaded through
      `_spawn_message_processing(session, user_input, source, exclude_user_echo, turn_info=None)`,
      then `_locked_message_processing`, then `_process_and_broadcast`. Keys:

      | Key | Value |
      |---|---|
      | `started` | `True`, set immediately after `turn.ran = True` |
      | `error` | a one-line message (`str(exc)` truncated to 200 characters in `_process_and_broadcast`'s `except Exception`; the generic text in `_locked_message_processing`'s) |
      | `paused` | the MCP server name taken from the pause metadata (`_auth_required_event_from_metadata`'s server or source name), or `"an MCP server"` |
      | `cancelled` | `True`, set in the cancel path before the re-raise |
      | `step_limit` | as today |
      | `delivery` | AC7 |

      Every existing caller passes nothing and behaves as before:
      `tests/test_cancel.py`, `tests/test_track_turn.py` and every
      `tests/test_process_and_broadcast_*` pass **unedited**.
- [ ] AC4. **Silent cancel.** A module-level `_silent_cancel: set[asyncio.Task]`.
      - `_spawn_message_processing`'s `CancelledError` branch skips
        `_notify_cancelled_once` when `me in _silent_cancel`, and its
        `finally` discards `me`.
      - A public helper `_mark_silent_and_cancel(task)` adds the task to the
        set, then cancels it.
      - Callers also `discard` in their own `finally`, because a task
        cancelled before its coroutine starts never runs the wrapper's
        `finally`.

      Tests:
      - A web turn holds the lock (stub agent blocked on an event). A routine
        task waits behind it and is silent-cancelled. The subscriber gets no
        `cancelled`, and the web turn still finishes with `done`.
      - The same cancel unmarked sends exactly one `cancelled`, as today.
      - A WS-style cancel (token created, `t.cancel()`) of a queued routine
        task that is also silent-marked sends at most one `cancelled`.
- [ ] AC5. **Shared registration.** `_register_turn_task(session, task)` holds
      `_spawn_web_message`'s registration (`_inflight_tasks`,
      `_session_inflight`, and both done-callbacks), and `_spawn_web_message`
      uses it. `_spawn_routine_turn(session, prompt, turn_info)` creates
      `_spawn_message_processing(session, prompt, "routine", None, turn_info)`
      and registers it the same way. A test asserts that `is_session_busy`
      is true while it runs.
- [ ] AC6. **Titled sessions.** `_create_session(agent_name, source="web",
      session_id=None, strict=False, title=None)`. A given title is set on the
      `Session` before the DB row is written, so the row and memory agree and
      `add_event` keeps it. One accepted quirk: a title that is literally "New
      chat" is still retitled.
- [ ] AC7. **Routine handling in `_process_and_broadcast`.** It applies when
      `routine = (turn_info or {}).get("routine")` is a dict
      `{id, name, target, connector_id}`. `target` is a `SendTarget` or
      `None`, and is computed by the caller from the stored row (leg 4).
      - **Live event.** The live `user` event carries `source: "routine"`,
        `routine_id`, `routine_name` and `session_id` (so the client can gate
        it to the bound chat, leg 7), plus `visibility: operator` on a
        connector chat as today.
      - **`_bind_turn_user_marks(session, pre_step_len, routine)`** runs
        immediately before **both** save sites:
        - It checks bounds and role: it acts only if
          `len(messages) > pre_step_len` and that message is USER. It never
          asserts.
        - It sets `routine_id`/`routine_name` on routine turns, and on a
          connector chat `visibility = OPERATOR_VISIBILITY`.
        - The existing USER operator-mark code (`:2559-2564`) is replaced by
          this helper, so there is no duplication.
      - **Cancel-path tagging, every turn.** Before its save, the cancel path
        runs `tag_post_step_visibility` and the helper for a connector chat.
        Regression test: cancel a web turn in a connector chat, and every
        stored message from `pre_step_len` on is operator-only.
      - **Delivery** happens only when all of the following hold:
        - the step loop completed with no exception, no pause and no cancel
          (a local `step_clean` that the `except Exception` and pause paths
          clear);
        - `session.platform is not None`;
        - `routine["target"] is not None`.

        It runs after the existing tagging and before the save, through
        `deliver_final_reply(...)`, and the result goes into
        `turn_info["delivery"]`.
        - **Exceptions.** Delivery is wrapped in `try/except Exception`. A
          raised error becomes `DeliveryResult("send_failed", error=…)`, never
          an escape.
        - **Cancel during delivery.** A `CancelledError` during delivery runs
          the same save and `_notify_cancelled_once` as the step-loop cancel
          path, sets `turn_info["cancelled"]`, and re-raises.

        Test: cancel while the fake client's `send` is blocked. The USER and
        assistant messages are saved with their marks, and exactly one
        `cancelled` is sent.
      - **Step limit.** After the save, if `hit_step_limit` and the delivery
        status is `delivered` or `already_sent`, call
        `send_step_limit_line(target, connector_id, manager)`.
      - **No `session_updated`** is sent from `_process_and_broadcast`.
      - **Tests** drive error, pause and cancel each, and assert that no send
        happens. A clean step with a fake client sends exactly the final
        text, and the stored reply's `visibility` is cleared.
- [ ] AC8. **Gate.**
      - `THE_ONE_TEST_NETNS=1 make test-unit` is green with the expected skip
        count, and `make lint` and `ruff format --check` are clean.
      - The `chats` and `chats-transcript` browser lanes are green
        (`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats`,
        then `--lane chats-transcript`), because this leg changes the turn
        path.

## Verification Steps

- AC1-AC2: `tests/test_routine_message_marker.py`, covering codec round-trip
  and each provider converter.
- AC3-AC7:
  - `tests/test_routine_turn_path.py`, in the `tests/test_cancel.py` style: a
    stub agent, `_send_to_session` monkeypatched to capture frames, and a fake
    connector manager and client for delivery (see
    `tests/test_connectors_inbound.py` for the fake);
  - the existing `test_cancel.py`, `test_track_turn.py` and
    `test_process_and_broadcast_*` unedited
    (`git diff --stat` on them shows only the new appended test in
    `test_cancel.py`).
- AC8: the commands above.

## Implementation Guidance

1. **Marker fields and codec** (AC1-AC2).
2. **`turn_info` threading** (AC3). Run the existing turn tests after it.
3. **`_silent_cancel` and `_mark_silent_and_cancel`** (AC4).
4. **`_register_turn_task` and `_spawn_routine_turn`** (AC5), then
   `_create_session(title)` (AC6).
5. **`_process_and_broadcast` routine handling** (AC7):
   - Read `routine` once at the top.
   - Add the routine keys to `user_event`.
   - Factor `_bind_turn_user_marks`.
   - Add `step_clean`.
   - Restructure the post-loop so delivery and save sit in one block that
     handles `CancelledError` by saving, notifying and re-raising. A small
     inner async function, `_save_and_notify_cancel()`, can be shared by both
     cancel sites.
6. **Docs.** In `agents.md`, add the `turn_info` keys, the silent cancel, the
   delivery rule (clean step only, cancel-safe), and the cancel-path tagging
   change.

## Edge Cases

- **Image content.** `user_input` may be list content; routine prompts are
  always str. Keep the `content_to_text` projection.
- **A routine turn on a web chat** (`platform is None`): no delivery and no
  tagging, but the marker is still bound.
- **Paused turns**: the save happens, there is no delivery, and the marker is
  bound.
- **Pass-through.** `turn_info` may be `None`. Every write is guarded.

## Files Affected

- `the_one/llm/base.py`, `the_one/db/codec.py`
- `the_one/interfaces/web/app.py`
- `tests/test_routine_message_marker.py`, `tests/test_routine_turn_path.py`
  (new); `tests/test_cancel.py` (one new test appended)
- `the_one/agents.md`

## Citation Audit

The line references were spot-checked by the design reviewer at `c2366221`:
`app.py:847-851`, `:1068`, `:1101`, `:1146`, `:1529`, `:2184` and
`:2512-2564` are accurate. The leg 2 names come from its plan; re-read the leg
2 flight-log entry before starting.

---

## Post-Completion
Completion steps (status transitions, flight-log update, checking off in the
parent flight, and the commit) are Flight Control protocol, driven by the
execution workflow, and are not repeated here.
