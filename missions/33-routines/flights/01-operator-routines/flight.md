# Flight: Operator Routines, End to End

**Status**: completed
**Mission**: [Routines](../../mission.md)

## Contributing to Criteria

- [x] **The operator manages an agent's routines** (whole criterion)
- [x] **Routines run on time, unattended** (whole criterion)
- [x] **The reply lands in the target** (whole criterion; behavior-test-backed,
      `routine-connector-delivery`)
- [x] **A routine's message says it came from the routine** (whole criterion)
- [x] **Unattended runs are honest** (whole criterion)
- [x] **Routines follow their agent** (whole criterion for operator routines;
      Flight 2 adds its proposals record to the same cascade)

Flight 2 owns the Self-configuration split, the agent's routine tools,
approval, flagging and caps. Flight 3 is the mission's one HAT. This flight has
no HAT leg (operator decision); it lands on automated gates and the behavior
test.

---

## Pre-Flight

### Objective

Give the operator named, per-agent routines that run on their own.
- **Setting one up.** On the agent editor's new Routines tab the operator
  creates a routine with:
  - a prompt;
  - a schedule: once (at a time or after a delay), daily, weekdays, weekly on
    chosen days, or every N hours;
  - a target: one of the agent's chats (web or connector), a new chat every
    run, or the routine's own chat.
- **Running.** A scheduler in the web app runs each routine when it is due, in
  the operator's time zone, with nobody watching. The run takes the chat's turn
  lock like any other turn and streams to anyone who has the chat open. In a
  connector chat it sends the agent's reply to the channel, and only the reply.
- **Being honest about it.**
  - The run's message is marked as the routine's, by name.
  - Every run, skip, miss and failure is in the routine's run history, with a
    reason.
  - The chat agent panel shows a chat's routine and lists the agent's
    routines.
- **Making room.** The editor's MCPs and Built-in tools tabs merge into one
  **Tools** tab with two sections, so the editor stays at six tabs.

### Open Questions

- [x] Making room for the tab → DD12 (operator: merge MCPs into Tools)
- [x] Schedule representation and DST → DD2, DD3
- [x] Grace window → DD4 (operator: scaled to the schedule)
- [x] Run message shape and what the model sees → DD7
- [x] How the panel knows a chat was activated by a routine → DD10
- [x] Keeping a connector target alive; `/new` and the continuation window → DD8
      (operator: the channel's current chat)
- [x] How a test makes a routine due → DD11 (operator: a Run now button; no
      test seam)
- [x] Whether connector delivery extraction trips the mission's split point →
      DD6 (no, but it is its own leg, so it is a clean divert boundary)
- [x] Edit races for operator-only routines → DD5
- [x] How the run learns its outcome from the shared web turn path → DD6
- [x] A routine due on a chat that is paused for a sign-in → DD6 (skipped)
- [x] Routines on the `default` agent → DD9 (refused)
- Deferred to Flight 2 (unchanged from the mission): the Self-configuration
  split, the agent tools, approval, flagging, caps, and whether the model is
  told a turn is a routine run.

### Design Decisions

Decisions marked *(autonomous judgement call)* were made by the Flight Director
without an operator answer. Each is reviewed at the mission HAT (Flight 3).
Revised after design review cycle 1; the changes are listed in the flight log.

**DD1 — The store: migration v45, two tables.** *(columns are an autonomous
judgement call)*

`agent_routines`:

| Column | Definition |
|---|---|
| `id` | `TEXT PRIMARY KEY` (`uuid4().hex`) |
| `agent_name` | `TEXT NOT NULL REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE` |
| `name` | `TEXT NOT NULL` |
| `prompt` | `TEXT NOT NULL` |
| `schedule` | `TEXT NOT NULL` (JSON, DD2) |
| `enabled` | `INTEGER NOT NULL DEFAULT 1` (the operator's switch) |
| `finished_at` | `TEXT` (a one-off that has had its one scheduled chance, DD4; "Done") |
| `target_kind` | `TEXT NOT NULL CHECK (target_kind IN ('chat', 'new', 'own'))` |
| `target_session_id` | `TEXT` (no FK: a gone chat is handled at run time, DD8) |
| `target_platform`, `target_connector_id`, `target_channel_id`, `target_thread_id`, `target_peer_id` | `TEXT` (connector identity snapshot, DD8; null for a web chat) |
| `next_run_at` | `TEXT` (UTC ISO; null when off or Done) |
| `anchor_at` | `TEXT` (UTC ISO; the `interval` anchor, DD2) |
| `created_by` | `TEXT NOT NULL DEFAULT 'operator' CHECK (created_by IN ('operator', 'agent'))` (Flight 2 writes `agent`) |
| `created_at`, `updated_at` | `TEXT NOT NULL` |

- Table constraint `UNIQUE (agent_name, name COLLATE NOCASE)` (works on the
  shipped SQLite 3.45).
- Index on `(enabled, next_run_at)` for the due query.

`agent_routine_runs`:

| Column | Definition |
|---|---|
| `id` | `TEXT PRIMARY KEY` |
| `routine_id` | `TEXT NOT NULL REFERENCES agent_routines(id) ON DELETE CASCADE` |
| `trigger_kind` | `TEXT NOT NULL CHECK (trigger_kind IN ('schedule', 'catch_up', 'manual'))` |
| `outcome` | `TEXT NOT NULL CHECK (outcome IN ('running', 'ok', 'failed', 'skipped', 'missed', 'interrupted', 'stopped'))` |
| `reason` | `TEXT` (one plain sentence, shown to the operator) |
| `due_at` | `TEXT` (the scheduled instant; null for manual) |
| `started_at`, `finished_at` | `TEXT` |
| `session_id` | `TEXT` (the chat the run used; no FK) |
| `new_chat` | `INTEGER NOT NULL DEFAULT 0` (the run started a chat, DD8) |

- Index `(routine_id, started_at DESC)`.
- **Run history follows the agent's retention policy** (operator decision).
  - **There is no count cap.** The daily purge sweep (`retention.py`
    `run_purge_sweep`) also deletes each agent's finished run rows older than
    that agent's `chat_history_retention_days`, judged on `finished_at`.
    `running` rows are never purged.
  - **It runs in the same pass,** with the same per-agent cutoff, and reuses
    `list_retention_windows`. The sweep result gains `runs_deleted`.
  - **Purge now.** The agent editor's "Purge now"
    (`DELETE /api/agents/{name}/chat/sessions`) clears the agent's run
    history along with its chats. The routines themselves stay. *(autonomous
    judgement call: run history refers to chats that Purge now deletes)*
  - **A routine's own target chat** is not exempt from retention. A routine
    that runs at least once per retention window keeps its chat fresh by
    updating it.
- **Cascades.** Runs cascade with their routine and so with the agent. A rename
  (`UPDATE agents SET name`) follows through `ON UPDATE CASCADE`.
  `chat_sessions` has no FK to agents (dropped in v5), so nothing new is
  needed there.
- **`app_metadata` key `routines_zone`** holds the zone key that the stored
  `next_run_at` values were computed in (DD5).
- **Migration style** follows v42/v43: `CREATE TABLE IF NOT EXISTS`,
  idempotent, `schema_version` row 45. The tests are a `TestSchemaV45` class in
  `tests/test_db_migration.py`: fresh replay columns and FKs, rewind
  idempotency, rename and delete cascade. Every `== 44` version pin moves to
  45.

**DD2 — Five schedule kinds as structured JSON, one pure calculator.**

```
{"kind": "once",     "at": "<UTC ISO>"}
{"kind": "daily",    "time": "HH:MM"}
{"kind": "weekdays", "time": "HH:MM"}                  # Monday to Friday
{"kind": "weekly",   "days": [0..6], "time": "HH:MM"}  # 0 = Monday, non-empty
{"kind": "interval", "hours": N}                       # 1 <= N <= 168
```

- **"Once, after a delay"** is a form convenience. The server stores the
  absolute `at`, computed on save from minutes, hours or days.
- **`the_one/routines/schedule.py`** holds pure functions with no I/O:
  - `validate(schedule) -> Schedule` raises a `ValueError` subclass carrying
    `.detail` (the `db/_rules.py` pattern).
  - `next_run(schedule, *, after: datetime, zone: tzinfo, anchor: datetime | None) -> datetime | None`
    returns the first occurrence strictly after `after`, in UTC. Callers pass
    `load_effective_zone().tzinfo`, and the zone *key* is used only for change
    detection (DD5).
  - The helpers `occurrences_between` (bounded) and `grace` serve DD4.
- **Wall-clock kinds** (daily, weekdays, weekly) are evaluated in the operator's
  effective zone.
- **`interval`** is absolute elapsed time from `anchor_at`, so DST and zone
  changes do not affect it. `anchor_at` is set on create, re-enable, and
  schedule change.
- **A past `once`.** A `once` whose `at` has passed is refused on create or
  edit with a 422: "That time has already passed."
- **The clock** is `time_zones.utcnow()`. The calculator and scheduler never
  call `datetime.now`. Tests use `frozen_clock`.

**DD3 — Daylight saving.**
- **Spring-forward gap.** A wall time that does not exist (2:30 AM in
  America/Los_Angeles on the change day) runs once, at the end of the gap
  (3:00 AM).
  - **Trap:** Python's `zoneinfo` resolves a nonexistent `02:30` to `03:30`
    PDT, by applying the pre-gap offset. The calculator must detect the gap
    explicitly: a round-trip through UTC changes the wall time. It then uses
    the gap's end.
- **Fall-back repeat.** A wall time that occurs twice (1:30 AM) runs once, on
  its first occurrence (`fold=0`), never twice.
- **Tests.** Unit tests pin both cases in America/Los_Angeles and
  Europe/London, plus Asia/Kolkata (an offset that is not a whole hour, and no
  DST).

**DD4 — Missed runs, the grace window, and one-offs** (operator: scaled to the
schedule).

A due routine is late by `now - next_run_at` when the scheduler looks at it.

- **Grace, repeating kinds:** min(half the gap between the missed occurrence
  and the one after it, 2 hours). A daily 9 AM routine still runs at 10:59. An
  every-2-hours routine gets 1 hour.
- **Grace, one-off:** 24 hours.
- **Within grace,** the routine runs once, with trigger `catch_up`. It is
  `schedule` instead when it is late by less than one tick, 60 seconds.
- **Beyond grace,** one `missed` row is recorded. Its reason counts the skipped
  occurrences ("Missed 3 runs while the app was closed."), with the count
  capped at 1000 ("more than 1000"). None of the missed occurrences runs.
- **Either way,** `next_run_at` moves to the first occurrence strictly after
  `now`. A backlog never runs.
- **One-offs.** A one-off gets one scheduled chance. When the scheduler takes
  that chance, whether it runs it (`schedule` or `catch_up`) or records it
  `missed`, it sets `finished_at` and nulls `next_run_at` **before** the run
  starts. This is DD5's advance-before-run rule. So the one-off is Done
  whatever the run's outcome, and the tab shows it as "Done".
  - Run now on a one-off, whether pending or Done, does not finish it and does
    not move its time.
  - Editing a Done one-off's time to a future instant clears `finished_at`
    and re-arms it.
  - The enable switch on a Done row is disabled, with the hint "Set a new
    time to run it again."

**DD5 — The scheduler loop.** `the_one/routines/scheduler.py`, class
`RoutineScheduler`, one per process, started in the web app lifespan.

- **Placement in the lifespan.**
  - **Start** comes after connector startup, because delivery needs the
    manager. It also comes after the `_sessions_push` listener is registered,
    so chat writes in the startup catch-up pass push `sessions_changed`.
  - **Stop** comes first in shutdown, before the in-flight turn cancel.
- **Stopping.**
  - Stop cancels the loop and every runner task it spawned, then awaits them
    with a short bound of 5 seconds. It never waits for a run to finish
    naturally, so a 15-minute run cannot hold shutdown, and the desktop
    `_graceful_shutdown` join gives up at 60 seconds.
  - A runner cancelled by shutdown records its run `interrupted` ("The app
    stopped during this run.") while the database is still open.
- **Startup.**
  - A sweep marks any `running` row `interrupted`. This is the backstop for a
    crash.
  - If the effective zone key differs from `routines_zone`, `next_run_at` is
    recomputed from now for every enabled, unfinished wall-clock routine, and
    the key is stored.
  - Then one due pass runs (DD4 catch-up).
- **Loop.** The scheduler sleeps until the earliest `next_run_at`, or 60
  seconds, whichever is sooner. It wakes early on an `asyncio.Event` that
  every routine write and every `PUT /api/time-settings` set through
  `scheduler.poke()`.
- **Each pass:**
  - It selects enabled, unfinished routines with `next_run_at <= now`.
  - It applies DD4 and writes the new `next_run_at` (and `finished_at` for a
    one-off) **before** it starts the run, so a crash cannot double-run.
  - It spawns the run as a tracked task.
  - A pass whose effective zone key differs from the stored one recomputes as
    at startup. This is how "system" mode follows a host zone change within a
    minute.
- **Run now** is separate from the pass. It never touches `next_run_at` or
  `finished_at`, and the advance-before-run rule does not block it. Its runner
  task goes into the same `RunRegistry` (DD6 step 7).
- **The scheduler spawns into the `RunRegistry`.** Stop cancels the loop and
  then drains the registry with the 5-second bound. Before this leg lands, the
  lifespan drains the registry itself.
- **Edit races (operator only).**
  - A run uses a snapshot of the routine taken at its start, so an edit during
    a run applies from the next run.
  - A schedule edit recomputes `next_run_at` from now.
  - Disabling stops future runs. It does not cancel a run that is already
    going; the chat's Stop does that.
  - Deleting a routine lets its running run finish. The history row goes with
    the routine, and the runner tolerates its row being gone.
- **Testability.** The scheduler takes its clock (`time_zones.utcnow`) and its
  runner as constructor arguments. Unit tests drive passes directly with a fake
  runner, with no sleeping.

**DD6 — The run path: reuse the web turn, thread an outcome out, deliver only
on success.**

`the_one/routines/runner.py` `run_routine(routine, trigger_kind)` is reached
from `app.py` through a registered hook (the `_set_module_factory` pattern),
so `routines/` never imports `app.py`. The order matters:

1. **Overlap.** If this routine already has a run in flight (an in-memory set),
   it records `skipped` ("The previous run was still going.") and stops.
2. **Pre-checks before anything is created.**
   - For a connector target, the connector must be available: the row exists,
     and `client_for` is not `None`.
   - The routine's agent must be the channel's authorized agent, through the
     shared `authorized_agent_for` (DD8).
   - A failure is `failed` with its reason. No chat row is created and no model
     call is made.
3. **Resolve the target chat** (DD8), creating one if needed, with its title
   set at creation (below).
4. **Insert a `running` row.**
5. **Check for a paused chat, then get the session.**
   - **Peek first.** Before any restore, the runner peeks the cache
     (`_sessions.get(sid)`). If that session's agent is paused for a sign-in
     (`_deferred_tool_calls` set) by another turn, the run is `skipped`
     ("The chat is waiting for a sign-in.").
     - The peek must come first: `_restore_session` replaces a non-busy
       session's agent and would wipe the pause.
     - A pause left by **this routine's own** earlier run does not block it.
       The runner remembers `{routine_id: session_id}` for its own paused
       runs, and that run's `failed` row already told the operator. The new
       run proceeds and replaces the stale pause. *(autonomous judgement
       call)*
     - A test pins this: a cached paused session, a due routine, a skipped
       run, and the pause survives.
   - **Then restore.** `_get_or_restore_session(sid)` returns the session. A
     degraded result (`provider_missing`, `agent_deleted`) is `failed` with a
     plain reason.
6. **Spawn the turn** through a routine variant of `_spawn_web_message`. It
   registers in `_inflight_tasks` and `_session_inflight[sid]`, so the chat
   shows busy, the open chat's Stop cancels it, and shutdown drains it. The
   task runs `_spawn_message_processing(session, prompt, "routine", None,
   turn_info)`.
   - **`turn_info` is threaded** through `_spawn_message_processing` and
     `_locked_message_processing` into `_process_and_broadcast`. It extends the
     existing out-parameter (M31 F6 leg 06, `app.py:2189`).
     - **In:** `routine` (`{id, name}`).
     - **Out:**
       - `started`: the lock was acquired;
       - `paused`;
       - `error`: a one-line message, set where `_process_and_broadcast` and
         `_locked_message_processing` turn an exception into a `system`
         frame;
       - `step_limit`;
       - `delivery`: the `DeliveryResult`.
7. **The time limit.** `THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS` (default 900,
   floor 60, read at call time) bounds the whole run, lock wait included. The
   runner waits with `asyncio.wait({task}, timeout=…)`, never `wait_for`, and
   classifies the end:
   - **The task finished:** read `turn_info`.
   - **The timeout fired before `started`:** the task is cancelled
     **silently**. A per-task marker (a `_silent_cancel` set beside
     `_started_tasks`) makes `_spawn_message_processing`'s `CancelledError`
     branch skip `_notify_cancelled_once`. The turn running ahead of it, often
     the operator's, gets no false `cancelled` and keeps its busy state and
     hold queue. Outcome `skipped` ("The chat stayed busy for 15 minutes.").
   - **The timeout fired after `started`:** the task is cancelled normally,
     the existing cancel path saves the partial reply and sends `cancelled`.
     Outcome `failed` ("The run took longer than 15 minutes.").
   - **The task was cancelled by someone else:** `task.cancelled()` with no
     timeout, or the chat's Stop, gives `stopped`. A Stop on the operator's own
     turn also cancels a routine run queued behind it ("Stop stops everything
     in the chat").
   - **The runner itself was cancelled** (shutdown): `asyncio.wait` does not
     cancel the tasks it waits on. So the runner's own `CancelledError`
     handler cancels the turn task explicitly, records `interrupted`, and
     re-raises, all within the 5-second stop bound.
   - **The silent cancel.** The marker is added to `_silent_cancel` before
     `task.cancel()`. The `CancelledError` branch of
     `_spawn_message_processing` gains `and me not in _silent_cancel`, and
     discards it in its `finally`. `turn_info["started"]` is set where
     `turn.ran = True` is set, right after `track_turn` is entered. A task
     granted the lock but cancelled before it resumes leaves `started` false,
     and `skipped` is correct for it: `asyncio.Lock` hands the lock on to the
     next waiter.
   - **One registry owns every runner task.** `routines/runner.py` keeps a
     module-level `RunRegistry` holding every runner task: scheduled,
     catch-up and Run now. The lifespan drains it with the bounded cancel.
     `routine-run-path` adds the registry and its drain; `routine-scheduler`
     spawns into the same registry. So a Run now during shutdown records
     `interrupted`, not `stopped`.
   - **Tests** pin each branch. One of them is: a routine waits behind a
     running web turn, times out, and no `cancelled` frame reaches the
     subscriber.
8. **Inside `_process_and_broadcast`,** for a routine run:
   - **The live event.** The live `user` event carries `source: "routine"` and
     `routine_name`.
   - **The marker** (`routine_id`/`routine_name`, DD7) is bound onto
     `messages[pre_step_len]`. In a connector chat the operator-only mark on
     that USER message is bound at the same moment.
     - **Where it is bound.** One helper binds both, and it runs immediately
       before **each** save site: the normal save and the cancel path's save
       (`app.py:2505-2524`).
     - **How it checks.** The helper checks bounds and role: it binds only if
       `len(messages) > pre_step_len` and that message is USER. It does not
       assert, unlike `_bind_peer_name`. A cancel during
       `_ensure_ollama_model_loaded` or the `user` broadcast reaches the
       cancel path before `agent.step` has appended anything.
     - **Why not earlier.** Binding on the first item from `agent.step` would
       be too late on its own. The first item arrives only after the first
       model call, which is when most cancels happen.
     - **Test.** One test cancels during the first model call (mock
       `delay_ms`) and asserts the stored marker.
     - **The cancel path's visibility gap.** That path never tagged connector
       visibility, which already affects web turns in connector chats. It is
       fixed for every turn in the same change.
   - **Delivery** happens only when the step completed normally. It is skipped
     when the step raised, paused or was cancelled, because the inbound path
     delivers only after a clean step loop. After the existing
     `tag_post_step_visibility`, it calls `deliver_final_reply` (below) and
     records the result in `turn_info["delivery"]`.
     - A turn whose agent already sent through `send_to_platform_channel` is
       delivered by that send.
     - A turn with no final text sends nothing; the outcome is `ok`, with the
       reason "The agent gave no reply to send."
     - A step-limited connector run sends `STEP_LIMIT_LINE`, as inbound does.
   - **No `session_updated` here.** `_process_and_broadcast` sends no
     `session_updated`. The runner sends it in step 10, after the lock is
     released.
9. **Outcome mapping.**

   | End of the run | Outcome | Reason |
   |---|---|---|
   | Normal end | `ok` | none |
   | Hit the step limit | `ok` | "Stopped at the step limit." |
   | Paused for a sign-in | `failed` | "Needs a sign-in to {server}. Sign in on its page in Library, then run it again." (the leg confirms whether a replayed transcript offers Sign in for a stored `auth_required` result; only if it does may the reason point at the chat) |
   | Error | `failed` | the one-line error |
   | Delivery failed | `failed` | "Couldn't send to {connector}: {reason}."; the reply stays in the chat, operator-only |

   The paused reason deliberately does not promise to resume the run. A later
   join rebuilds the agent (`_restore_session`), and the reaper can evict the
   pause.
10. **After the turn task completes** (lock released, session saved), the
    runner does three things, in order:
    1. It writes `session_metadata["routine"]` = `{id, name, last_run_at}`
       with `set_session_metadata_key`.
    2. It mirrors that into the in-memory `session.session_metadata`.
    3. It sends `session_updated` to the chat's subscribers. An open tab then
       re-joins, after `done`, and gets the saved history (the delivered
       reply's cleared operator-only mark) and the routine metadata.

    This is the inbound path's rule (`inbound.py:528-537`): a re-join made
    while the lock is held gets the cached, stale session. The runner sends
    `session_updated` for a routine run on any chat, web or connector, and
    for every outcome that ran a turn.

**Delivery extraction (its own leg, `connector-delivery-split`).**
- **The split.** `_auto_deliver_reply`'s body uses the envelope only to pick
  the target. It becomes
  `deliver_final_reply(messages, pre_step_len, target, connector_id, manager) -> DeliveryResult`,
  which:
  - skips after a successful `send_to_platform_channel`;
  - takes the final assistant text;
  - calls `client.send`;
  - flips `visibility` to `None` only on success.

  `_auto_deliver_reply` keeps its signature and calls it with
  `_reply_target(envelope, ...)`.
- **The shared agent rule.** `authorized_agent_for(connector, channel_id)` is
  extracted from `SendToPlatformChannelTool.execute`
  (`channel_map.get(channel_id) or default_agent`, with `default_agent` alone
  for a peer target). Both `execute` and the runner call it.
- **Characterization tests land first** and must pass unchanged after the
  split:
  - inbound delivery: the skip rule, the success flip, client missing, send
    error, a DM (its target asserted), and no final text;
  - the tool's agent rule.

**What the routine path does not reuse:** `/api/chat`, which takes no lock.

**DD7 — The run's message.**
- **What the model sees.** The run's message is a USER message whose text is
  the routine's prompt, verbatim, and the model sees exactly that. No platform
  prompt text changes, so no eval run is due. Flight 2 decides whether
  agent-authored runs are framed for the model, and runs the eval if they are.
- **The new fields.** `Message` (`llm/base.py`) gains two optional USER-only
  fields, `routine_id` and `routine_name`.
  - `message_to_dict`/`message_from_dict` handle them, written only when set.
  - `messages_to_ui_events` spreads them onto USER events.
  - No provider serializer reads them, since each builds its payload from a
    whitelist. A unit test asserts that each provider converter's payload for
    a marked message equals an unmarked one's.
- **Visibility.** In a connector chat the routine's message is operator-only,
  as an operator's typed message is today, so the prompt is never posted. Only
  a delivered reply becomes peer-visible.
- **In the transcript** *(autonomous judgement call)*:
  - It is a user-side bubble. Its attribution name is the routine's name, with
    a "Routine" chip, and never "You".
  - `App.ui.message` gains a `marker` option (a label chip on any role); its
    inventory row and contract test grow with it.
  - `transcript.js` and `turn-frames.js` stop prefixing `"[routine] "` for
    the new source.
- **In-flight state in the client.** A live `user` frame with
  `source === 'routine'` puts the open chat into the in-flight state:
  - Stop is enabled and cancels the run.
  - Sends are held in the hold queue.
  - The run's `done` ends the state, as for the tab's own send.

**DD8 — Targets** (operator: a connector target is the channel's current
chat).

- **Existing chat, web.** The routine stores `target_session_id`. If the chat
  no longer exists (deleted, or purged by retention):
  - the run starts a new web chat with the agent;
  - the routine is retargeted to it;
  - the run row gets `new_chat` = 1 and the reason "The chosen chat was gone,
    so this run started a new chat."
- **Existing chat, connector.** The routine stores the picked row's connector
  identity (platform, connector, channel, thread, peer) and its session id.
  - **At run time** it resolves the channel's **current** chat the way an
    incoming message would: `find_most_recent_by_external_key`, continuing it
    when it is not ended and its `last_inbound_at` is within the connector's
    continuation window.
  - **Otherwise** it starts a new chat for that channel:
    - the same identity columns;
    - the previous row's title, or the channel id;
    - `last_inbound_at` set to now at creation, as `resolve_session` does, so
      a peer reply after a failed delivery still continues it.
  - **The routine is retargeted** to the chat the run used.
  - **After a successful delivery,** including the agent's own
    `send_to_platform_channel`, the run sets the chat's `last_inbound_at` to
    now (`update_last_inbound`). The delivered message counts as channel
    activity, so the peer's reply on Discord continues the routine's chat.
    This is the one non-inbound write that moves `last_inbound_at`, and it is
    documented in `the_one/connectors/README.md`.
- **The DM approximation.** A stored row does not record whether it is a DM.
  - **Delivery.** `keying_to_target(row)` gives a `ChannelTarget` for any row
    whose `channel_id` is not `None`. A Discord DM stores its DM channel id,
    and a Telegram DM stores its chat id, so a `ChannelTarget` reaches both.
  - **Stub DMs.** The stub seam defaults `channel_id` to `""`, so a stub DM row
    gives `ChannelTarget(channel_id="")`. Inbound replies to the same DM use a
    `PeerTarget`. The routine path keeps this as it is: `keying_to_target` is
    not normalized, because that would change `send_to_platform_channel`'s
    default target. The characterization tests assert the actual shapes.
  - **Authorization.** `authorized_agent_for` treats a DM's channel id like any
    channel. A DM channel id is never in `channel_map`, so it resolves to
    `default_agent`, which is the inbound DM rule.
  - **Tests.** The characterization tests assert both shapes.
- **Who answers the channel.** The pre-check (DD6 step 2) fails the run with
  "{channel} is now answered by {agent}." when the routine's agent is not the
  authorized one. So no routine can post as an agent the operator moved off
  that channel. *(autonomous judgement call)*
- **New chat every run.** Each run creates a web chat owned by the agent.
- **Its own chat.** Created on the first run as a web chat, stored in
  `target_session_id`. A gone own chat is recreated.
- **Titles.** Every chat a routine creates is titled with the routine's name
  at creation, before the first `user` event, because `Session.add_event`
  retitles a "New chat" from the prompt.
- **Purge.** A target deleted by the purge sweep is simply gone at the next
  run. It needs no cleanup hook, since there is no FK.

**DD9 — REST surface.** All routes are under `/api/agents/{name}/routines`.
An unknown agent is a 404. Bodies are parsed by hand, as the rules routes do,
so input is never echoed.

| Route | Purpose |
|---|---|
| `GET …/routines` | `{routines: [...], limits}`; each row has `next_run_at`, `finished_at`, `last_run` (outcome, reason, finished_at), `running`, and `target` (kind, `session_id`, chat title, platform, `missing`) |
| `POST …/routines` | 201; create |
| `GET …/routines/{id}` | one routine (same row shape) |
| `PUT …/routines/{id}` | partial update: `name`, `prompt`, `schedule`, `target`, `enabled` |
| `DELETE …/routines/{id}` | `{"status": "ok"}` |
| `POST …/routines/{id}/run` | 202; Run now (trigger `manual`); 409 while that routine is running |
| `GET …/routines/{id}/runs` | newest first; `limit` (default 50, at most 200) and `before` (a `started_at` cursor) page through everything retention has kept |

- **Names** go through `check_name` (`_checked_name`, `loc ["name"]`). A
  duplicate within the agent is a 409.
  - The POST and PUT routes join `CHECKED` in `tests/test_api_name_rule.py`.
  - `…/run` joins `EXEMPT` ("acts on the routine in the path and never sets a
    name").
- **A target chat** must belong to the agent (`agent_name`), else a 422 ("That
  chat belongs to another agent.").
- **The `default` agent** cannot have routines (422, "Routines need a named
  agent."). Its chats store `agent_name` as null, so it cannot own a target.
  *(autonomous judgement call)*
- **Limits** *(autonomous judgement call; Flight 2 adds agent caps)*:
  - prompt 1–4000 characters;
  - 50 routines per agent;
  - `interval` hours 1–168;
  - a `once` at most a year ahead.
- **Writes** call `scheduler.poke()`. `PUT /api/time-settings` pokes too.
- **The client** reads the effective zone from `GET /api/time-settings`
  through `App.time`, to show next-run times.

**DD10 — The chat agent panel.**
- **Activated by a routine.** When the open chat's
  `session_metadata.routine` is set (DD6 step 10), the panel's facts gain a
  "Routine" row: "{name} · last ran {time}" (`chat-drawer-routine`).
  - The value comes from `session_joined`'s `session_metadata`, and the
    panel's view gains `sessionMetadata`.
  - It is fresh after every routine run, because the run ends with
    `session_updated` and the tab re-joins (DD6 step 8).
- **Routines group.** A "Routines" group after Notes (`data-group="routines"`)
  lists the agent's routines by name, A-Z. Each row's meta is "Next {day}
  {time}", "Off" or "Done".
  - It is fetched per open, like Rules (404 means none), and refetched on each
    `session_joined`.
  - It is read-only. Open agent settings reaches the tab.

**DD11 — Making a routine due in tests: Run now plus a short one-off; no test
seam** (operator: Run now).
- **Run now** is a product feature (DD9). It drives the run path and delivery
  on demand.
- **The scheduled path** is proven live by a one-off due 1 minute out. The
  poked scheduler wakes for it.
- **Catch-up, missed, DST and zone changes** are proven at the unit tier with
  `frozen_clock` and the scheduler's injected clock and runner.
- **No `/api/_test/*` route** is added, so
  `tests/test_seam_routes_403_sweep.py` is unchanged.

**DD12 — Tools absorbs MCPs; the Routines tab** (operator: merge MCPs and
Built-in tools into one Tools tab with two sections).

*Tools merge (leg `tools-tab-merge`, before the Routines tab):*
- **Tab order** becomes General, Rules and notes, Knowledge, Tools,
  Self-configuration: five tabs after this leg, and six once `routines-tab`
  inserts Routines before Self-configuration.
- **The Tools tab** (`data-tab-id="tools"`, testid `tab-tools`) holds two
  `App.ui.section`s:
  - "Built-in tools" holds today's `renderToolsTab` content;
  - "MCP servers" holds today's `renderMcpsTab` content.

  Built-in tools comes first *(autonomous judgement call)*. Both modules keep
  their handles, and the tab composes `setAgent`, `setSources` and `destroy`.
  The save-flow selectors in `agent-form-data.js` are unchanged (they query
  the editor, not a panel), and a test proves a save from each section.
- **Routes.** The MCP deep link becomes `#agents/{name}/tools/{sourceId}` (one
  sub segment, so `App.router.href` stays usable with no `%2F`).
  - The old `#agents/{name}/mcps` and `…/mcps/{sourceId}` hashes are a
    router-level alias, like `settings/general`. They redirect with
    `replaceState` to `…/tools` and `…/tools/{sourceId}`.
  - `studio-route.js`'s `mcps/` split becomes a `tools/{id}` split.
  - The controller's tab-specific branches (`agent-editor-controller.js:380`,
    `studio-route.js` `_pendingMcpAgentSourceId`) key off `tools`.
- **Retired and copy.**
  - `tab-mcps` and `agent-tab-mcps` move to the registry's Retired table, and
    `RETIRED_SELECTORS`.
  - Copy that says "the MCPs tab" says "the Tools tab", in:
    - `self-config-status.js`;
    - `library-pane.js`;
    - the Self-configuration tab's locked-row text;
    - `docs/ui-control-inventory.md`;
    - the `router.js` comments.
- **Every pin moves in this leg:**
  - `tests/browser/test_studio_mcps_tab.py`, the bulk of the work;
  - `test_studio_self_configuration_tab.py`;
  - `test_router_items.py`, which also reads `mcps-tab.js` source;
  - `test_router_core.py`;
  - `tests/test_nav_helper.py` (a legacy `#studio/…/mcps/…` now redirects
    twice);
  - `test_studio_editor_contracts_static.py` (count and the `{id}-tab.js`
    map);
  - `test_flow_agent_editor_frame.py`;
  - `test_flow_agent_tabs.py`;
  - `test_flow_agents_scale.py` (tab count, no overflow at 1024px,
    re-measured);
  - `scripts/ui_capture.py` (`agent-mcps`, `agent-mcps-full`);
  - `the_one/agents.md`;
  - CLAUDE.md.

*Routines tab (leg `routines-tab`)* is `data-tab-id="routines"`, in
`areas/studio/routines-tab.js`. `App.studio.renderRoutinesTab` returns
`{setAgent, destroy}`, and the tab is inserted before Self-configuration.
- **Saving.** It saves immediately, like Rules: each action is an API call then
  a refetch, outside dirty tracking and `App.nav`. The edit form's unsaved
  draft is held locally and discarded on Cancel or on leaving the tab
  *(autonomous judgement call: matches Rules' unguarded add and edit text)*.
- **A `~new` agent** shows the "save first" empty state. The `default` agent
  shows "Routines need a named agent."
- **List.** One row per routine shows:
  - the name;
  - a schedule sentence ("Weekdays at 9:00 AM");
  - the target ("DM: alice · Discord", "New chat each run", "Its own chat";
    a gone chat reads "Chat gone, a new one starts on the next run");
  - the next run, or "Done";
  - the last outcome as `App.ui.status`.

  Its controls are:
  - the enable `App.ui.toggle`, disabled on Done with its hint;
  - Run now;
  - Edit;
  - an armed delete (`App.ui.confirm`);
  - a run-history `App.ui.disclosure` listing outcome, time and reason.

  With no routines, the tab shows `App.ui.emptyState` and "New routine".
- **Form** (create and edit, inline under the list's header):
  - Name (`textInput`) and Prompt (`textarea`).
  - Schedule is an `App.ui.radioGroup` of the five kinds, each revealing its
    fields:
    - time of day: hour, minute and AM/PM `App.ui.select`s (12-hour, per M25
      DD14);
    - weekly days: seven `App.ui.checkbox`es in a fieldset with legend "Days";
    - once: "In" (a number plus minutes, hours or days) or "At" (a day
      `select` of the next 60 days: "Today", "Tomorrow", "Fri, Oct 30", plus
      the time selects);
    - interval: a number of hours.

    *(Autonomous judgement call: the library has no date or time control,
    and native `type=time/date` varies across WebKitGTK and WebView2.)* If the
    day checkboxes need a grouping factory, `App.ui.checkboxGroup` is added
    with its inventory row and contract test.
  - Target is a `radioGroup`: "A chat", "A new chat each run" or "Its own
    chat". "A chat" opens a chooser (`App.ui.searchList` in an `App.ui.modal`,
    the agent-picker pattern) over the agent's chats from `App.store`
    `sessions`, newest first, with platform badges.
  - A 422 maps to fields through `App.api.fieldErrors`.
- **Times** go through `App.time`.
- **Live refresh.** It does not depend on the chat WebSocket: a cold load of
  `#agents/x/routines` has no socket, and a run that fails before its turn
  writes no chat.
  - The tab refetches after its own actions.
  - It polls `GET …/routines` every 3 seconds while any row shows `running`
    or a Run now is pending, for up to the run time limit.
  - It also refetches when it becomes visible again.
  - A generation guard drops stale responses.
- **Testids** use the `routines-*` and `routine-*` families, registered:
  `routines-new-btn`, `routine-row` with `data-routine-id`, `routine-toggle`,
  `routine-run-now`, `routine-edit`, `routine-delete`, `routine-history`,
  `routine-form`, `routine-target-picker`, `routines-save-first`.

**DD13 — Verification apparatus.**
- **Unit tier:**
  - the calculator (DD2-DD4) with `frozen_clock`;
  - scheduler passes with a fake runner and injected clock, including stop
    and interrupted;
  - the runner through the real app path with the mock provider, with the stub
    connector plugin registered in-process for delivery, covering every DD6
    outcome branch including the silent-cancel test;
  - delivery and agent-rule characterization tests;
  - codec and provider no-leak tests;
  - REST, migration v45 and the name-rule classification.
- **Browser tier:**
  - the Tools merge, in the files that own the tabs;
  - `tests/browser/test_flow_agent_routines*.py`, in `agent_tabs_pat`;
  - the transcript marker and routine in-flight state, in `chats-transcript`;
  - the panel, in the chats lane's drawer tests;
  - the `App.ui.message` `marker` contract, in `contracts-chat`.
- **Behavior test `routine-connector-delivery`** (shell-only Executor, draft at
  `tests/behavior/routine-connector-delivery.md`) runs on a dedicated dev
  instance: port 8490 or higher, a scratch data dir under `$HOME`, a scratch
  cwd, `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`.
  - **Act:** REST seeds the provider, agent and stub connector;
    `POST /api/_test/stub/inbound` opens the DM and sends `/new`;
    `POST …/routines`, `…/run`, and a 1-minute one-off.
  - **Observe:**
    - `GET /api/_test/stub/outbound` gives each send's text and target
      (connector, channel, peer). Comparing targets is how "same channel" is
      judged, since the session routes return only `platform`.
    - `GET …/routines/{id}/runs` gives the outcome, `new_chat` and
      `session_id`.
    - `GET …/routines/{id}` gives `target.session_id`, `next_run_at` and
      `finished_at`.
    - `GET /api/chat/sessions/{id}` gives the stored messages and
      `session_metadata`.
    - `GET /api/time-settings` gives the effective zone, for judging "next
      9:00 AM".

  Both premises hold: every act path is an existing route or one this flight
  adds, and every observable is read through one too.

**DD14 — Test placement and lanes.**
- **Unit:**
  - `tests/test_routines_schedule.py`;
  - `test_routines_scheduler.py`;
  - `test_routines_runner.py`;
  - `test_routines_api.py`;
  - `test_connector_delivery_characterization.py`.
- **Browser:** `test_flow_agent_routines*` joins `agent_tabs_pat` in
  `scripts/run-tests.sh`. The router tests carry the `mcps` → `tools` alias.
- **Lane budgets.** The `agent-tabs` lane absorbs the routines tests and the
  merge churn. Its budget is re-measured under the quiet-host rule in the last
  UI leg, and re-budgeted if it moves more than 15%.

**DD15 — Security model.** `SECURITY-MODEL.md` gains a "Routines" section:
- routines are unattended turns with the agent's full tool access;
- a connector routine posts to a channel with no human present;
- only the reply is posted, never the prompt;
- the authorized-agent rule;
- every run's outcome is recorded.

Flight 2 extends the section with agent-authored routines, approval and
flagging.

### Citation Audit

Verified against the working tree at `c2366221` (cycle 1's corrections
applied):

| Citation | Status |
|---|---|
| `the_one/agent/core.py:247` — `Agent.step` appends `Message.user(user_input)` itself; no marker can be passed in (DD7 bind) | verified |
| `the_one/connectors/inbound.py:216` `_bind_peer_name` — post-step bind onto `messages[pre_step_len]`, asserts USER (DD6, DD7 pattern) | verified |
| `the_one/connectors/inbound.py:285` `_auto_deliver_reply(messages, pre_step_len, envelope, connector_id, manager)` — envelope used only via `_reply_target` (`:250`); called only after a clean step loop (`:504-512`) (DD6) | verified |
| `the_one/connectors/base.py:70` `keying_to_target(session)` — `ChannelTarget` when `channel_id is not None` (so `""` too), else `PeerTarget`; the stub seam defaults `channel_id` to `""` (`api.py:4518`) (DD8 DM approximation) | verified (cycle 2) |
| `the_one/interfaces/web/api.py:4546-4552` `GET /_test/stub/outbound` — each record carries `connector_id`, `channel_id`, `peer_id` (DD13 step 4/7 comparison) | verified (cycle 2) |
| `the_one/interfaces/web/app.py` `_restore_session` — replaces a non-busy cached session's agent, which drops `_deferred_tool_calls` (DD6 step 5 peek-first) | verified (cycle 2) |
| `the_one/connectors/manager.py:97` `client_for` — `None` when not running or not connected (DD6 pre-check) | verified |
| `the_one/connectors/inbound.py:153` `resolve_session` — continuation by `ended_at` and the `last_inbound_at` window; sets `last_inbound_at` on create (DD8) | verified |
| `the_one/db/repositories.py:2591` `find_most_recent_by_external_key` (by `updated_at DESC`), `:2772` `update_last_inbound`, `:2848` `set_session_metadata_key` (DD8, DD6 step 10) | verified |
| `the_one/tools/connector_send.py` `SendToPlatformChannelTool.execute` — the agent rule `channel_map.get(channel_id) or default_agent` (`:171-172`); `_resolve_default_target` (`:95`) only builds the target (DD6 `authorized_agent_for`) | verified |
| `the_one/interfaces/web/app.py:1068` `_spawn_message_processing` — the `CancelledError` branch calls `_notify_cancelled_once` when the task is not running and has no token (`:1088-1095`) (DD6.7 silent cancel) | verified |
| `the_one/interfaces/web/app.py:1101` `_locked_message_processing` — `track_turn`, resync, `current_chat_session_id`, then `_process_and_broadcast`; swallows exceptions into a `system` frame (DD6 `turn_info`) | verified |
| `the_one/interfaces/web/app.py:1146` `_spawn_web_message` — registers `_inflight_tasks` and `_session_inflight` (DD6 routine variant) | verified |
| `the_one/interfaces/web/app.py:2184` `_process_and_broadcast(..., turn_info=None)` — `turn_info` out-parameter at `:2189`; visibility tagging at `:2558` runs on success and error; the cancel path saves and re-raises (DD6.8) | verified |
| `the_one/interfaces/web/app.py:1764` `_get_or_restore_session` — degraded statuses; a non-busy restore replaces `existing.agent` (DD6.5, DD6.9 paused reason) | verified |
| `the_one/interfaces/web/app.py:1416` `_chat_history_purge_loop` — due-loop and lifespan start/drain pattern (DD5) | verified |
| `the_one/sessions/_locks.py:76` `track_turn` — FIFO `asyncio.Lock`; a second turn waits (DD6 "chat busy waits") | verified |
| `the_one/time_zones.py:135` `utcnow` (test seam); `load_effective_zone` returns `EffectiveZone(key, tzinfo)` (DD2, DD5) | verified |
| `tests/conftest.py:470` `frozen_clock` — patches `time_zones.utcnow` and `detect_system_zone` only (DD2) | verified |
| `the_one/db/codec.py:143` / `:198` / `:280` — whitelist encode/decode and UI-event spread (DD7) | verified |
| `the_one/llm/base.py:409` `build_user_message_content` — the only place USER metadata reaches the model; unchanged (DD7) | verified |
| `the_one/db/schema.py:14` `CURRENT_VERSION = 44` — v45 next (DD1) | verified |
| `the_one/interfaces/web/static/js/areas/studio/agent-editor.js:42` `TAB_ITEMS`; `studio-route.js:269-279` the `mcps/` split and tab whitelist; `router.js` `settings/general` alias pattern (DD12) | verified |
| `the_one/interfaces/web/api.py:5095` `GET /chat/sessions/{id}` — returns stored `messages` and `session_metadata`; `_session_summary` has `platform` but no connector or channel ids (DD13) | verified |

### Prerequisites

- [x] Mission 33 active; Flight 1 is its first flight.
- [x] Mock provider scripts replies; the stub connector seam exists
      (`/api/_test/stub/inbound`, `/outbound`), and inbound dispatch is awaited
      synchronously, so seeding is deterministic.
- [x] No new external services or ports. The behavior test uses a dev
      instance at 8490 or higher, never 8484 (the operator's app) or 8485 (the
      Flight Director's preview).
- [x] Branch `flight/01-operator-routines` cut from `main` at execution start.
- [x] Each leg re-verifies the cited line numbers at its start (the Citation
      Audit is at `c2366221`).
- [x] The behavior-test leg re-checks that the dev port is free and runs
      `the-one rotate-api-credential` against the scratch data dir before the
      first request (squawk 0278).

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

- **New package `the_one/routines/`:**
  - `schedule.py`, the pure calculator;
  - `repository.py`, with `AgentRoutineRepository` and
    `RoutineRunRepository` in the `db/` repository style: async aiosqlite,
    one `write_transaction` per mutator, and `KeyError` for a missing or
    other-agent row;
  - `scheduler.py`;
  - `runner.py`.
- **The web layer:**
  - registers the runner hook;
  - threads `turn_info` and the silent-cancel marker through the web turn
    path;
  - starts and stops the scheduler in the lifespan;
  - serves the REST routes in `api.py`.
- **Connector delivery** is split into `deliver_final_reply` and
  `authorized_agent_for`, behind characterization tests.
- **The client:**
  - merges MCPs into Tools;
  - adds the `marker` option to `App.ui.message`;
  - adds the routine in-flight state to the chat;
  - extends the agent panel;
  - adds the Routines tab.

### Checkpoints

- [x] v45 migrates fresh and existing databases; rename and delete cascade.
- [x] Calculator and grace rules pass their frozen-clock tests, DST included.
- [x] Delivery characterization tests green before and after the split.
- [x] A routine runs headless in a web chat and in a stub connector chat; the
      reply is delivered and the prompt is not; every outcome branch is pinned.
- [x] The scheduler fires a due routine, catches up once, records missed,
      survives restart, and stops promptly.
- [x] The editor shows Tools with both sections; no overflow at 1024px.
- [x] The transcript marks routine messages; an open chat shows a routine run
      as in flight; the panel shows the Routine row and group.
- [x] Routines tab creates, edits, toggles, runs now, deletes, shows history.
- [x] Behavior test `routine-connector-delivery` passes on a dev instance.

### Adaptation Criteria

**Divert if:**
- `connector-delivery-split`'s characterization tests cannot stay unchanged
  across the split. That is the mission's pre-declared split point: stop after
  that leg and re-plan the connector half as its own flight. The web-chat run
  path, scheduler and UI continue without connector targets.
- The routine run path needs a change to `agent/core.py` (the frozen loop).
- The Tools merge breaks the MCP editor or save flow beyond test re-pointing:
  pause and ask the operator.

**Acceptable variations:**
- Column names, testid names, limits and reason wording.
- Moving the routine hook between `app.py` and `routines/runner.py`.
- Adding `App.ui.checkboxGroup` or not.

### Legs

> **Note:** Tentative. Legs are designed one at a time and run in this strict
> order (cycle 1: the UI legs share the tab registry, pins and docs, so
> nothing runs in parallel).

- [x] `routines-store-and-schedule`: v45 and its migration tests, the
      repositories, the schedule calculator (DD2-DD4), and the REST surface
      without Run now (DD9). Also name-rule classification, limits, and the
      `default` refusal. Run-history retention joins the purge sweep and
      Purge now (DD1), with tests through the existing
      `/api/_test/purge-sweep` seam path. No runs yet.
- [x] `connector-delivery-split`: characterization tests first, then
      `deliver_final_reply` and `authorized_agent_for` (DD6 extraction, DD8
      DM approximation). This is the mission's split point, and so the divert
      boundary.
- [x] `routine-turn-path` *(3a, split at leg design review)*: the marker in
      `Message`, codec and UI events; `turn_info` threading; the silent cancel;
      `_spawn_routine_turn`; titled sessions; routine handling in
      `_process_and_broadcast` (marker at both save sites, cancel-safe delivery
      after a clean step); the cancel path's connector tagging for every turn
      (DD6 steps 6-8, DD7 server).
- [x] `routine-runner` *(3b)*: `RunRegistry`; pre-checks; target resolution
      and channel continuation (`is_continuable`); the paused peek; the time
      limit and the pure `classify`; post-steps (`last_inbound_at`, routine
      metadata, `session_updated`); Run now and the live `running` field;
      end-to-end tests over the app lifespan with the stub connector (DD6, DD8,
      DD11). Docs: `agents.md` and `connectors/README.md`.
- [x] `routine-scheduler`: the loop, lifespan start and stop, the poke, DD4
      catch-up, missed and one-off finishing, the interrupted sweep, and the
      zone-change recompute with `routines_zone` (DD5). Docs: `agents.md`,
      CLAUDE.md, and `SECURITY-MODEL.md` (DD15).
- [x] `tools-tab-merge`: MCPs folded into Tools as a section; the `tools/{id}`
      deep link and the router-level `mcps` alias; retired testids; every pin
      re-pointed; copy updated (DD12 first half).
- [x] `message-marker-and-panel`: `App.ui.message` `marker`, the transcript
      bubble, the routine in-flight client state (DD7 client), the panel's
      Routine row and Routines group (DD10), registry, browser tests and
      inventory row.
- [x] `routines-tab-list` *(8a, split at leg design review)*: the Routines
      tab (the sixth tab) with lazy activation, the list, row controls (toggle,
      Run now, delete, history with paging), polling while it is running, and
      the form hooks; `routines-describe.js`.
- [x] `routines-tab-form` *(8b)*: `App.ui.checkboxGroup`; the server
      accepts `once` as `{on: {date, time}}` in the operator zone; the pure
      form model; the inline form for five schedule kinds and three targets;
      the chat chooser; capture surfaces; the agent-tabs lane re-measured.
- [x] `routine-connector-delivery-behavior-test`: finalize and run
      `tests/behavior/routine-connector-delivery.md` on a dedicated dev
      instance (DD13). Fix what it finds through the fix-vs-feature gate.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged
- [x] `make test-unit` green; `make test-browser` green (`THE_ONE_TEST_NETNS=1`)
- [x] Behavior test `routine-connector-delivery` passed and its run log
      committed
- [x] Documentation updated: CLAUDE.md, `the_one/agents.md`,
      `the_one/connectors/README.md`, `SECURITY-MODEL.md`,
      `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`

### Verification

- **Unit tier:** the calculator, scheduler, runner (every outcome branch),
  delivery characterization, REST and migration tests.
- **Browser tier:** the Tools merge, the Routines tab, the transcript marker
  and in-flight state, and the panel.
- **Real environment:** `routine-connector-delivery` proves that:
  - a routine run replies through a connector with the prompt withheld;
  - a scheduled one-off fires on its own;
  - a run after `/new` lands in the channel's new chat;
  - the peer's reply continues that chat.
