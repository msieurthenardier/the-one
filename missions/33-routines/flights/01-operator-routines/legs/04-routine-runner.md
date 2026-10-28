# Leg: routine-runner

**Status**: completed
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Run one routine unattended on demand (Run now), through leg 3's routine turn
path. The runner:
- pre-checks connector targets;
- resolves the target chat, including the channel's current chat;
- respects a chat paused for sign-in;
- bounds the run with a time limit;
- classifies every ending into a run outcome with a plain reason;
- after the lock is released, updates channel activity, the chat's routine
  metadata and any open tab.

Nothing schedules a routine yet. That is leg 5.

## Context

- Flight DD6 steps 1-5, 7 and 9-10, DD8 (targets), DD9 (`…/run`), DD11. This
  is part 3b of the original run-path leg, split at design review.
- **From leg 1:** `the_one/routines/` with `AgentRoutineRepository`,
  `RoutineRunRepository` (`insert`, `finish`, and a `finish` on a missing row
  that is a no-op), `_now_iso()`, and the REST row with `running: false`.
- **From leg 2:** `deliver_final_reply`, `send_step_limit_line` and
  `authorized_agent_for(connector, *, channel_id)`.
- **From leg 3:** `turn_info` keys (`started`, `error`, `paused`, `cancelled`,
  `step_limit`, `delivery`), `_spawn_routine_turn`,
  `_mark_silent_and_cancel`, `_create_session(title=)`, and
  `_process_and_broadcast`'s routine handling, which expects
  `turn_info["routine"] = {id, name, target, connector_id}`.
- Re-read the flight log entries for legs 1-3 for the actual names before
  starting.
- Leg 5 (the scheduler) spawns into this leg's `RunRegistry` with trigger
  `schedule` or `catch_up`, and calls `run_routine`.

## Inputs

**`the_one/connectors/inbound.py`:**
- `resolve_session` (`:153-213`) has the continuation rule: reuse when
  `session_metadata` has no `ended_at`, `last_inbound_at` parses, and
  `now - last_inbound_at < continuation`.
- `_resolve_continuation_seconds(override)` (`:73`).

**`the_one/db/repositories.py`:**
- `ChatSessionRepository.find_most_recent_by_external_key` (`:2591`);
- `update_last_inbound` (`:2772`);
- `set_session_metadata_key` (`:2848`);
- `create`, `get`;
- `ConnectorRepository.get` (and `Connector.name`).

**Elsewhere:**
- `the_one/connectors/base.py` `keying_to_target(session_row)` (`:70`).
- `the_one/connectors/manager.py` `get_manager()`, `client_for` (`:97`).
- `the_one/sessions/_broadcast.py` `broadcast_to_session` (`:71`). The client
  re-joins on `session_updated` for whichever chat it has open, web or
  connector (`static/js/areas/chat/socket.js:117-129`, `requestRefresh`).

**`the_one/interfaces/web/app.py`:**
- `_get_or_restore_session` (`:1764`), which replaces a non-busy cached agent;
- `_sessions`;
- the lifespan in-flight cancel (`:499-503`).

## Outputs

**`the_one/routines/runner.py`** (new):
- the `TurnHost` Protocol and `set_turn_host(host)`;
- `RunRegistry` and a module-level `registry`;
- `run_routine(routine_id, trigger_kind, due_at=None)`;
- `classify(...)`, a pure function;
- `routine_run_timeout_seconds()`, plus the test-override attribute
  `_TIMEOUT_FLOOR_SECONDS`.

**`the_one/connectors/inbound.py`:** `is_continuable(row, continuation_seconds, now)`
is extracted from `resolve_session`. `resolve_session` uses it, its behaviour
is unchanged, and the inbound tests stay unedited.

**`the_one/routines/repository.py`:**
`AgentRoutineRepository.set_target_session(routine_id, session_id)` is narrow.
It is a no-op on a missing row and does not touch `updated_at`.

**`the_one/interfaces/web/app.py`:**
- `_RoutineTurnHost`, registered in the lifespan after the factory and
  connector startup;
- the lifespan drains `registry` with a 5-second bound **before** the
  `_inflight_tasks` cancel.

**`the_one/interfaces/web/api.py`:**
- `POST /api/agents/{name}/routines/{id}/run`;
- `running` is live.

**Tests:**
- `tests/test_routines_runner.py`, `tests/test_routines_classify.py` (new);
- `tests/test_routines_api.py`;
- `tests/test_api_name_rule.py` (`…/run` EXEMPT).

**Docs:**
- `the_one/agents.md`: runner and outcome table;
- `the_one/connectors/README.md`: the `last_inbound_at` rule.

## Acceptance Criteria

**The run registry**

- [ ] AC1. **`RunRegistry`.**
      - `try_spawn(routine_id, factory: Callable[[], Coroutine]) -> Task | None`
        checks and adds **synchronously**. It returns `None`, without
        creating any coroutine, when that id is already running.
      - `is_running(id)`.
      - `remember_pause(routine_id, sid)`, `own_pause(routine_id) -> sid | None`
        and `clear_pause(routine_id)`. A run that starts clears its own entry.
      - `drain(timeout=5.0)` cancels every runner task and awaits them, up to
        the bound.

      The web lifespan calls `registry.drain()` before the `_inflight_tasks`
      cancel.

**Order of a run (DD6)**

- [ ] AC2. `run_routine` loads the routine fresh by id; it is this run's
      snapshot. It then proceeds in this order:
      1. pre-checks (AC3);
      2. target resolution (AC4);
      3. insert the `running` row;
      4. the paused peek (AC5);
      5. restore (AC6);
      6. build `turn_info["routine"]`;
      7. spawn;
      8. wait and classify (AC7, AC8);
      9. post-steps (AC9).

      A pre-check failure inserts and finishes a row in one step, with
      `session_id` null. A routine gone at load time returns quietly.

**Pre-checks and targets**

- [ ] AC3. **Pre-checks**, for a connector target (`target_connector_id` set).
      They run before any chat is created:
      - The connector row is missing, or `get_manager().client_for(id)` is
        `None`: `failed`, "{connector name or id} isn't connected." The name
        is read through `ConnectorRepository`.
      - `authorized_agent_for(connector, channel_id=target_channel_id)` is not
        the routine's agent: `failed`, "{channel_id or 'This channel'} is now
        answered by {agent or 'no agent'}."

      No model call happens and no chat row is created.
- [ ] AC4. **Target resolution (DD8).**
      - **chat, web.** If `target_session_id`'s row exists and its
        `agent_name` is the routine's, use it. Otherwise create a web chat
        through the host (`title` = routine name), and set `new_chat` with the
        reason "The chosen chat was gone, so this run started a new chat."
      - **chat, connector.**
        1. Call `find_most_recent_by_external_key(platform, connector_id,
           channel_id, thread_id)`.
        2. Reuse that row if `is_continuable(row,
           _resolve_continuation_seconds(connector.session_continuation_seconds-equivalent override), now)`,
           using the same override source inbound uses.
        3. Otherwise create a `ChatSession` with: a new id, the routine's
           agent, the snapshot identity (`peer_id` too), the previous row's
           title or the channel id, and `last_inbound_at = now`.

        `new_chat` is set only when a row was created.
      - **new.** Create a web chat titled with the routine name on every run.
        `new_chat` is true.
      - **own.** Use `target_session_id` if it exists. Otherwise create a web
        chat titled with the routine name, with `new_chat` true.
      - **Retarget.** Every chosen or created chat is written back with
        `set_target_session` (a no-op if the routine is gone).
      - **Delivery target.** `turn_info["routine"]["target"]` =
        `keying_to_target(row)` from the resolved stored row. It is `None` for
        a web chat, and "carries a target" means not `None`.
        `turn_info["routine"]["connector_id"]` = `row.connector_id`.
- [ ] AC5. **The paused peek.** This runs before any restore.
      - If the host's cached session for the chosen chat has an agent with
        `_deferred_tool_calls`, and `registry.own_pause(routine_id)` is not
        that chat, the run is `skipped` with "The chat is waiting for a
        sign-in." No restore happens.
      - A test asserts the cached agent's `_deferred_tool_calls` is unchanged
        afterwards.
      - When the pause belongs to this routine, the run proceeds and clears
        the memory.
- [ ] AC6. **Degraded sessions.** A `provider_missing` restore is `failed`
      with "The agent's model provider is missing." An `agent_deleted` restore
      is `failed` with "The agent no longer exists."

**Waiting and classifying**

- [ ] AC7. **The time limit.** `routine_run_timeout_seconds()` reads
      `THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS` at call time (default 900),
      clamped to at least `_TIMEOUT_FLOOR_SECONDS` (60).
      - **Waiting.** The runner waits with `asyncio.wait({task}, timeout=…)`,
        never `wait_for`.
      - **Timeout before `turn_info["started"]`.** It calls
        `_mark_silent_and_cancel(task)`.
      - **Timeout after `started`.** It calls `task.cancel()`.
      - **After either cancel,** it awaits the task again with a bound of 5
        seconds, so the cancel path's save completes before the post-steps.
      - **When the runner itself is cancelled** (drain or shutdown):
        - If the turn task is not done, it cancels it: silently if not
          `started`, normally otherwise.
        - It awaits the task, bounded so `drain(5s)` holds.
        - It finishes the run row as `interrupted`, and re-raises.
      - **The runner's `finally`** discards the task from `_silent_cancel`
        through the host.
      - **The reason text** writes minutes as `max(1, round(seconds / 60))`.
- [ ] AC8. **`classify(state, turn_info, *, timed_out, timeout_seconds) -> (outcome, reason)`**
      is a pure function, unit-tested row by row:

      | Situation | Outcome | Reason |
      |---|---|---|
      | Done, no `error`/`paused`/`cancelled`; delivery `delivered`, `already_sent` or none | `ok` | none, or "Stopped at the step limit." |
      | Delivery `no_text` | `ok` | "The agent gave no reply to send." |
      | Delivery `send_failed` / `no_client` | `failed` | "Couldn't send to {connector}: {error or 'not connected'}." |
      | `paused` | `failed` | "Needs a sign-in to {server}. Sign in on its page in Library, then run it again." |
      | `error` | `failed` | the error line |
      | Timed out, not `started` | `skipped` | "The chat stayed busy for {N} minutes." |
      | Timed out, `started` | `failed` | "The run took longer than {N} minutes." |
      | Cancelled with no timeout (the chat's Stop) | `stopped` | "Stopped from the chat." |
      | Runner cancelled | `interrupted` | "The app stopped during this run." |

      A `paused` outcome also calls `registry.remember_pause(routine_id, sid)`.

**After the run**

- [ ] AC9. **Post-steps,** for every outcome that ran a turn, once the turn
      task is done (lock released), in order:
      1. On `delivered`/`already_sent`, `update_last_inbound(sid, now)`.
      2. `set_session_metadata_key(sid, "routine", {id, name, last_run_at})`,
         mirrored into the host's cached `session.session_metadata`.
      3. `broadcast_to_session(sid, {"type": "session_updated", "session_id": sid})`.
      4. `finish` the run row (`outcome`, `reason`, `session_id`, `new_chat`).

      Every step is idempotent and tolerates a deleted chat (`KeyError` is
      logged and skipped). On `interrupted`, the steps are best-effort inside
      the bounded window; the startup sweep (leg 5) is the backstop.

**End to end and REST**

- [ ] AC10. **End to end through the app lifespan.** A fixture,
      `routine_app` in `tests/test_routines_runner.py` or a conftest helper,
      builds:
      - the web app with its lifespan (`TestClient`), on a schema-template
        data dir with `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`
        (the stub plugin registers);
      - a mock provider and agent;
      - a stub connector (`default_agent` = that agent);
      - a DM opened through `POST /api/_test/stub/inbound`.

      Over it, the tests prove:
      - **Run now in the connector DM:**
        - the stub outbound log holds exactly the final reply, to the row's
          `keying_to_target` target;
        - no outbound record contains the prompt;
        - the stored USER message has `routine_name` and
          `visibility: operator`;
        - the stored reply has no `visibility`;
        - `session_metadata.routine` is set;
        - the run row is `ok`;
        - a WS subscriber on that chat receives `session_updated` after
          `done`.
      - **`already_sent`:** the agent calls `send_to_platform_channel` (the
        mock `tool_calls`). There is no second send, the run is `ok`, and
        `last_inbound_at` has moved.
      - **`/new`, then Run now:** a new chat row with the same identity
        columns, `new_chat` true, and the routine retargeted.
      - **A web-chat target that was deleted:** a new web chat titled with
        the routine name, `new_chat` true.
      - **Pre-check failures:** connector disabled, and a wrong agent. Each
        is `failed`, and no chat is created.
      - **The paused peek** (a cached session with `_deferred_tool_calls` set
        by the test): `skipped`, and the pause survives.
      - **Timeouts** (`_TIMEOUT_FLOOR_SECONDS` and the env var patched to
        sub-second values, mock `delay_ms`):
        - busy (a web turn holds the lock): `skipped`, and the web turn's
          subscriber gets no `cancelled`;
        - long run: `failed`, with partial text saved.
      - **Drain during a run:** `interrupted`.
- [ ] AC11. **`POST /api/agents/{name}/routines/{id}/run`.**
      - 202 `{"status": "started"}`.
      - 404 for an unknown agent or routine.
      - 409 "This routine is already running." when `try_spawn` refuses.
      - Trigger `manual`, `due_at` null.
      - It never changes `next_run_at` or `finished_at` (asserted).
      - EXEMPT in `tests/test_api_name_rule.py` ("acts on the routine in the
        path and never sets a name").

      Every row's `running` is `registry.is_running(id)`. The list
      response's `limits` gains `run_timeout_seconds` (the value of
      `routine_run_timeout_seconds()`, for leg 8's poll cap). Update leg 1's
      exact-dict `limits` assertion.
- [ ] AC12. **`is_continuable`** is extracted from `resolve_session` into
      `inbound.py` and used by it. `tests/test_connectors_inbound.py` passes
      unedited, and direct unit tests cover the ended, stale, missing,
      unparsable and naive-timezone cases.
- [ ] AC13. **Gate.**
      - `THE_ONE_TEST_NETNS=1 make test-unit` green with the expected skip
        count;
      - `make lint` and `ruff format --check` clean;
      - the `chats` lane is green.

## Verification Steps

- AC1, AC8: unit tests of `RunRegistry` and `classify` (no app).
- AC2-AC7, AC9-AC10: `tests/test_routines_runner.py` over the `routine_app`
  fixture. Read `tests/browser/conftest.py`'s seeding and
  `tests/test_connector_stub_registration_hook.py` for how the stub registers
  under the lifespan, and reuse `auth_headers()`.
- AC11: `tests/test_routines_api.py` and `tests/test_api_name_rule.py`.
- AC12: `tests/test_connectors_inbound.py` unedited (`git diff --stat`), plus
  the new unit tests.
- AC13: the commands.

## Implementation Guidance

1. `is_continuable` extraction (AC12), then `set_target_session`.
2. `RunRegistry` and `classify`, pure and unit-tested first (AC1, AC8).
3. **`TurnHost` Protocol**, implemented in `app.py` by `_RoutineTurnHost`.
   Methods:
   - `peek_session(sid)`;
   - `get_or_restore(sid) -> (session | None, status)`;
   - `create_web_session(agent_name, title) -> sid`;
   - `spawn_turn(session, prompt, turn_info) -> Task`;
   - `mark_silent_and_cancel(task)`;
   - `discard_silent(task)`;
   - `mirror_metadata(sid, key, value)`;
   - `broadcast(sid, payload)`.

   Register it in the lifespan; `routines/runner.py` imports nothing from
   `interfaces/`.
4. `run_routine` in AC2 order, with the AC7 wait logic and the AC9
   post-steps.
5. The REST route and the `running` field.
6. The `routine_app` fixture and end-to-end tests.
7. Docs:
   - `agents.md`: the runner order, the registry, the outcome table, and the
     `last_inbound_at` rule;
   - `connectors/README.md`: one paragraph on `last_inbound_at`.

## Edge Cases

- **A routine deleted mid-run:** `finish` and `set_target_session` are
  no-ops.
- **Agent renamed mid-run:** re-read `agent_name` from the row loaded at the
  start; FK cascade keeps the id.
- **Two routines on one chat:** they serialize on the lock.
- **The stub DM row** has `channel_id=""`, which gives
  `ChannelTarget(channel_id="")`. `authorized_agent_for(channel_id="")`
  returns `default_agent` (DD8, leg 2).
- **Delivery inside the time limit:** a stalled platform send counts against
  the routine's limit. That is acceptable, and recorded in `agents.md`.

## Files Affected

- `the_one/routines/runner.py` (new); `the_one/routines/repository.py`
  (`set_target_session`)
- `the_one/connectors/inbound.py` (`is_continuable`)
- `the_one/interfaces/web/app.py` (host and lifespan), `the_one/interfaces/web/api.py`
- `tests/test_routines_runner.py`, `tests/test_routines_classify.py` (new);
  `tests/test_routines_api.py`, `tests/test_api_name_rule.py`
- `the_one/agents.md`, `the_one/connectors/README.md`

## Citation Audit

Checked at `c2366221` during design and by the leg-3 design reviewer:
- `inbound.py:73`, `:153-213`;
- `repositories.py:2591`, `:2772`, `:2848`;
- `base.py:70`;
- `manager.py:97`;
- `_broadcast.py:71`;
- `socket.js:117-129` (`session_updated` re-join for any open chat);
- `app.py:1764`, `:499-503`.

Leg 1-3 names come from their plans; re-read the flight log before starting.

---

## Post-Completion
Completion steps (status transitions, flight-log update, checking off in the
parent flight, and the commit) are Flight Control protocol, driven by the
execution workflow, and are not repeated here.
