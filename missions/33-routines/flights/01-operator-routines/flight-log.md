# Flight Log: Operator Routines, End to End

**Flight**: [Operator Routines, End to End](flight.md)

## Summary

In flight on `flight/01-operator-routines`. Batch mode: Batch A (legs 1-4, backend), Batch B (legs 5-7, UI), then leg 8 (behavior test).

---

## Leg Progress

### Leg 1: routines-store-and-schedule

**Status**: landed (not committed).

**Built**
- Schema v45 (`agent_routines`, `agent_routine_runs`, both indexes); `CURRENT_VERSION = 45`.
- `the_one/routines/`: `limits.py`, `schedule.py` (pure calculator with the DD3 gap/fold rules, `grace`, `occurrences_between`), `models.py`, `repository.py` (`AgentRoutineRepository`, `RoutineRunRepository`, `_now_iso()`).
- REST under `/api/agents/{name}/routines` (list, create, get, put, delete, runs) in `api.py`; the `default` agent refusal; Purge now and the purge sweep (and its test seam) return `runs_deleted`.
- `the_one/agents.md` "Routines (M33)" section.

**Tests**
- New: `tests/test_routines_schedule.py` (57), `tests/test_routines_repository.py` (13), `tests/test_routines_api.py` (all pass), `TestSchemaV45` (6) in `tests/test_db_migration.py`, `TestRoutineNames` in `tests/test_api_name_rule.py`, a run-retention test in `tests/test_retention.py`.
- Updated pins: the `== 44` version pins, `tests/test_db_api.py` (two purge dicts), `tests/test_retention.py` (sweep dict), `tests/test_name_repair.py` (`agent_routines` in the follow-the-rename loop).
- Unit gate (`THE_ONE_TEST_NETNS=1 make test-unit`): 7975 passed, 15 skipped (the expected netns count), 3652 deselected. `ruff check` and `ruff format --check` clean on the_one/ tests/ scripts/ evals/.

**Deviations**
- Field-level 422s on the routine routes are list-shaped on `loc [field]` (not plain strings) so the editor can map them; the `default`-agent refusal is a plain string.
- A re-enabled one-off whose time has passed gets no next run and is marked Done (`finished_at` = now), rather than staying armed with a null next run.

**Anomalies**: none.

### Leg 2: connector-delivery-split

**Status**: landed (not committed).

**AC1 counts** (`test_connectors_inbound.py` + `test_inbound_session_updated.py` + `test_connector_send_tool.py`): 93 passed before, 93 passed after; `git diff --stat` on the three files is empty. Characterization cases (a)-(e) plus step-limit written first and passed against the old code.

**Built**: `the_one/connectors/delivery.py` (`DeliveryResult`, `deliver_final_reply`, `send_step_limit_line`, `authorized_agent_for`, `STEP_LIMIT_LINE`); `inbound.py` wrappers delegate (re-exports `STEP_LIMIT_LINE`, keeps the two tool literals); `connector_send.py` uses `authorized_agent_for`; `tests/test_connector_delivery.py` (13 tests); notes in `connectors/README.md` and `agents.md`.

**Unit gate** (`THE_ONE_TEST_NETNS=1 make test-unit`): 7988 passed, 15 skipped (expected netns count). ruff check and format clean.

**Deviations**: the non-str-content characterization case was dropped (an ASSISTANT `Message` cannot hold list content; the model asserts). The delivery log lines now come from the `the_one.connectors.delivery` logger (wording unchanged).

**Anomalies**: none.

### Leg 3: routine-turn-path

**Status**: landed (not committed).

**Built** (`the_one/interfaces/web/app.py`, `llm/base.py`, `db/codec.py`): `Message.routine_id`/`routine_name` (USER-only, codec writes when set, UI events spread them, no provider reads them); `turn_info` threaded through `_spawn_message_processing` -> `_locked_message_processing` -> `_process_and_broadcast` (passed on only when not `None`, because existing tests stub `_process_and_broadcast` with the old signature); `_silent_cancel` + `_mark_silent_and_cancel(task)`; `_register_turn_task`, `_spawn_routine_turn(session, prompt, turn_info)`; `_create_session(..., title=None)`; `_bind_turn_user_marks(session, pre_step_len, routine)`; routine live-event keys, `step_clean`, cancel-safe delivery, shared inner `_save_and_notify_cancel()`, step-limit line after delivery.

**turn_info keys for leg 4.** In: `routine = {id, name, target, connector_id}` (`target` a `SendTarget` or `None`). Out: `started`, `error` (str, <= 200 chars), `paused` (MCP `source_name`, else `source_id`, else "an MCP server"), `cancelled`, `step_limit`, `delivery` (`DeliveryResult`; absent unless delivery ran). Helpers: `_spawn_routine_turn`, `_mark_silent_and_cancel`, `_silent_cancel`, `_create_session(title=)`. `_locked_message_processing`'s generic exception sets `error` to "An error occurred while processing your message."

**Tests**: `test_routine_message_marker.py` 9, `test_routine_turn_path.py` 16, one appended in `test_cancel.py` (the connector cancel-tagging regression). `test_cancel.py`, `test_track_turn.py`, `test_process_and_broadcast_*` otherwise unedited and green.

**Gate**: `THE_ONE_TEST_NETNS=1 make test-unit` 8014 passed, 15 skipped (expected netns count). ruff check and format clean. Lanes: `chats` 166 passed (311 s), `chats-transcript` 89 passed (214 s).

**Deviations / anomalies**: the leg text says a cancel during `_ensure_ollama_model_loaded` or the `user` broadcast reaches the cancel path; in the code the `try` begins after `pre_step_len`, so those cancels were never saved (unchanged; `_bind_turn_user_marks` is still bounds-safe). Behaviour change outside routines: the cancel path now tags connector-chat messages operator-only.

### Leg 4: routine-runner

**Status**: landed (not committed).

**Built**
- `the_one/routines/runner.py`: `TurnHost` Protocol + `set_turn_host`, `RunRegistry` (module `registry`: `try_spawn(id, factory)`, `is_running`, `remember_pause`/`own_pause`/`clear_pause`, `drain(timeout=5.0)`, `reset_for_test()`), pure `classify(state, turn_info, *, timed_out, timeout_seconds, connector_name=None)`, `routine_run_timeout_seconds()` with `_TIMEOUT_FLOOR_SECONDS`, `run_routine(routine_id, trigger_kind, due_at=None)`.
- `inbound.is_continuable(row, seconds, now)` extracted; `resolve_session` uses it (`test_connectors_inbound.py` unedited). `AgentRoutineRepository.set_target_session`.
- `app.py`: `_RoutineTurnHost` registered in the lifespan after the connector manager; the lifespan drains `registry` (5 s) before the `_inflight_tasks` cancel and clears the host.
- `api.py`: `POST /api/agents/{name}/routines/{id}/run` (202 / 404 / 409), `running` live, list `limits.run_timeout_seconds`. EXEMPT row added in `test_api_name_rule.py`; leg 1's exact `limits` dict updated.
- Docs: `agents.md` Routines section (runner order, targets, outcomes, registry), `connectors/README.md` (`is_continuable`).

**For leg 5.** `from the_one.routines.runner import registry, run_routine`; spawn `registry.try_spawn(id, lambda: run_routine(id, "schedule"|"catch_up", due_at))`. Test fixture `routine_app` (in `tests/test_routines_runner.py`) yields a `Harness` (`dm`, `routine`, `run_now`, `runs`, `last_run`, `llm` = `ScriptLLM` with `.script` / `.delay`); it runs the real lifespan inside a dedicated task (anyio scopes) with the stub connector, a mock provider, agent `bot`, and resets `_write_lock`, session locks and `appmod._sessions`.

**Gate**: `THE_ONE_TEST_NETNS=1 make test-unit` 8053 passed, 15 skipped (expected netns count); ruff check and format clean; `chats` lane 166 passed (310 s).

**Tests**: `test_routines_classify.py` 17, `test_routines_runner.py` 14 (end to end), `test_is_continuable.py` 5, 3 appended to `test_routines_api.py`.

**Deviations / notes**
- `run_routine` inserts the `running` row with `session_id`/`new_chat` already set (so a live row shows its chat); `finish` re-writes them.
- A reused connector row must also belong to the routine's agent, else a new row is created.
- Post-steps run only when the turn `started` (a skipped-before-start run sends no `session_updated` and writes no metadata).
- The stub DM has `channel_id=""`, which `send_to_platform_channel`'s default target rejects ("exactly one of channel_id or peer_id"); the `already_sent` test DMs with a non-empty channel. Delivery itself works with `""`.
- Test base URL uses port 8499 (the unit suite refuses 8484 requests).
### Leg 5: routine-scheduler

**Status**: landed (not committed).

**Built**
- `the_one/routines/scheduler.py`: `RoutineScheduler(clock, spawn, conn_factory, sleep)` (`start`, `stop`, `poke`, `run_pass`, `startup`), pure `next_sleep`, `get_scheduler`/`set_scheduler`, `ZONE_KEY = "routines_zone"`.
- `repository.py`: `advance_if_due`, `earliest_next_run`, `list_active_wall_clock`, `recompute_next_run` (the two writes are compare-and-sets).
- `runner.py`: `RunRegistry.drain` now sets a closed flag so `try_spawn` refuses; `reopen()` (called by the lifespan at startup) and `reset_for_test()` clear it.
- `app.py`: scheduler started last (after `_sessions_push`), stopped first in shutdown (above "stop pushing"), replacing leg 4's direct `registry.drain()`; each step in `try/except`. `api.py`: `_poke_scheduler()` called by routine create/update/delete and `PUT /time-settings`.
- `tests/_routine_app.py` (new): leg 4's `routine_app` fixture and helpers moved out of `test_routines_runner.py` (which imports them; 14 tests still pass).
- Docs: `agents.md` (scheduler, startup order, CAS, sleep floor, stop order, `routines_zone`, accepted loss, timestamps), CLAUDE.md "Routines (M33 F1)", `SECURITY-MODEL.md` "Routines (Mission 33)".

**Tests**: `tests/test_routines_scheduler.py` 25 (AC1-AC8: trigger kinds, catch-up, miss counts incl. more-than-1000, one-off miss and finish-before-spawn, overlap, not-picked, CAS and deletion races, startup order and LA-to-London recompute, first boot, sweep, no-hot-loop across 5 iterations, poke, real-lifespan once-routine within 10 s, Run-now independence, stop under 8 s with `interrupted`, `_poke_scheduler` with no scheduler).

**Gate**: `THE_ONE_TEST_NETNS=1 make test-unit` 8078 passed, 15 skipped (expected netns count); `shared` browser lane 333 passed (294 s); ruff check and format clean.

**Deviations / notes**
- The due pass in `startup` uses the currently effective zone for `next_run`/grace (stored `next_run_at` values are used as-is); the zone recompute follows it.
- A name-only or prompt-only edit during a pass does not change `next_run_at`, so the compare-and-set still succeeds (only schedule/enable/finish edits are "edits that win").


---

## Decisions

### Tools absorbs MCPs (planning, operator)
**Context**: A seventh agent-editor tab would overflow the tab row at the
1024px minimum width (six tabs end about 20px from the edge).
**Decision**: The operator chose to merge the MCPs and Built-in tools tabs
into one Tools tab with two sections, so Routines takes the freed slot.
**Impact**: The `tools-tab-merge` leg; the `#agents/{name}/mcps` routes redirect.

### Design review cycle 1 (planning)
**Context**: The Architect approved with changes: three high issues, eight
medium and ten low.
**Decision**: All were applied.
- **DD6, the run path, was rewritten:**
  - `turn_info` is threaded through the web turn path as the outcome channel.
  - A silent cancel for a lock-wait timeout, so no false `cancelled` reaches
    an open chat.
  - Delivery only after a clean step.
  - The marker is bound at both save sites, and the cancel path's connector
    visibility gap is fixed.
  - `session_updated` after a routine run.
  - Pre-checks run before any chat is created.
  - A paused chat skips the run.
  - The paused reason no longer promises a resume.
- **DD5, shutdown and startup:**
  - bounded cancel on stop, with the runner recording `interrupted`;
  - the scheduler starts after the sessions push listener;
  - `routines_zone` persisted so a zone change while the app was closed is
    caught.
- **DD7:** a routine-source frame puts the open chat in flight.
- **DD12:**
  - the Routines tab polls while a row is running instead of relying on
    `sessions_changed`;
  - the full MCPs pin list;
  - the deep link is `tools/{id}`;
  - a router-level `mcps` alias.
- **DD8:**
  - the shared `authorized_agent_for`;
  - the DM approximation recorded;
  - `last_inbound_at` set on connector chat creation;
  - titles set at creation.
- **DD3:** the zoneinfo 3:30 gap trap is named.
- **DD4:** one-off states get a `finished_at` column for Done.
- **DD1:** the run column is `trigger_kind`.
- **DD9:**
  - the `default` agent is refused;
  - the target view carries `session_id`.
- **DD15:** a security-model section.
- **Legs:** the plan went from five legs to eight, in strict order. The
  connector delivery split is now its own leg, which is the divert boundary.
- **Behavior test:** "same channel" is judged from the stub outbound targets,
  and the zone is read before judging 9:00 AM.

**Impact**: The second design review checks the rewrite.

### Design review cycle 2 (planning)
**Context**: Approve with changes: one high issue, three medium and three
low.
**Decision**: All were applied.
- **DD6 step 5:** the paused check peeks the cache before any restore, since a
  restore would wipe the pause. A pause from the routine's own earlier run
  does not block it.
- **`session_updated`:** moved out of `_process_and_broadcast` to the runner,
  after the lock is released and the metadata is written (the inbound rule).
- **DD8:** the stub DM target corrected to `ChannelTarget("")`, with no
  normalization.
- **One `RunRegistry`** owns scheduled and Run-now runner tasks. The runner's
  cancel handler cancels the turn task explicitly and records `interrupted`.
- **Marker binding** is a bounds- and role-checked helper before each save
  site, with a cancel-during-first-call test.
- **DD4's one-off finishing** matches advance-before-run.
- **The paused reason** no longer points at the chat unless the leg confirms a
  replayed Sign in.

**Impact**: The maximum two review cycles are done. The remaining suggestions
are carried as leg guidance:
- a possible early split of the cancel-path visibility fix and codec marker
  out of `routine-run-path`;
- a single-`replaceState` legacy `#studio…/mcps` alias chain pinned in the
  router tests.

### Run history follows the agent's retention policy (planning, operator)
**Context**: The draft kept the newest 50 runs per routine.
**Decision**: The operator directed that run history be subject to the agent's
retention policy instead.
- The daily purge sweep deletes finished runs older than the agent's
  `chat_history_retention_days`. There is no count cap.
- Purge now clears run history along with the chats.
- The runs route pages with `limit` and `before`.

**Impact**: DD1, DD9, and the `routines-store-and-schedule` leg.

---

## Deviations

---

## Anomalies

---

## Session Notes

### Flight Director Notes

- **2026-10-28, start.**
  - Loaded `leg-execution.md`.
  - The flight was `ready` and is now `in-flight`; branch
    `flight/01-operator-routines` is cut from `main` at `c2366221`.
  - **Batch mode**, the operator's standing preference for multi-leg UI
    flights:
    - Batch A is legs 1-4 (backend). A checkpoint review and commit follow,
      with a Sonnet Reviewer, because the diff touches turn
      cancellation/lock paths and connector posting.
    - Batch B is legs 5-7 (UI). A review plus an Accessibility Reviewer and a
      commit follow.
    - Leg 8 runs the behavior test.
- **Leg 1 `routines-store-and-schedule`: high risk** (schema v45, a new
  agent-keyed cascade, and changes to the retention sweep and the Purge now
  response). A Developer design review comes before implementation.
- **Leg 2 `connector-delivery-split`: low risk, no design review.**
  - Every existing signature is kept, and the change is pure extraction.
  - It is mechanically guarded: AC2 requires the three existing test files to
    pass unedited, otherwise `[BLOCKED:delivery-split-not-contained]` and a
    divert.
  - The flight-end Reviewer covers it.
- **Leg 1 design review** (Developer, Sonnet): approve with changes. All
  applied:
  - the exact whole-minute DST gap algorithm, with the Lord Howe case;
  - three exact-dict response pins named (`test_db_api.py:3719/3730`,
    `test_retention.py:182`) and the hand-built purge-sweep seam response;
  - the `default` literal check before the 404 load;
  - PUT precedence rules;
  - Purge now excludes running runs, and `finish` on a missing row is a
    no-op;
  - all routine and run timestamps go through `time_zones.utcnow()`;
  - the `limits` keys are specified.

  The changes were precise, so there is no second cycle. Legs 1 and 2 are
  `ready`.
- **Leg 3 `routine-run-path`: high risk** (turn cancellation and lock
  bookkeeping, a shared web-turn interface with existing consumers, connector
  posting). Its design review runs in parallel with the leg 1 implementation;
  the reviewer does not run the unit suite.
- **Leg 3 design review** (Developer, Sonnet): approve with changes, and
  split. Two high issues:
  - a cancel during delivery would skip the save and the `cancelled` frame;
    delivery is now cancel-safe and exception-safe;
  - the timeout and shutdown paths must await the cancelled turn, with a
    bound, before the post-steps.

  Mediums applied:
  - a narrow `set_target_session`;
  - `try_spawn` with a coroutine factory, so a refusal leaks nothing;
  - `_silent_cancel` discarded by the caller too, and shutdown cancels
    silently before `started`;
  - the delivery target is computed from the stored row;
  - an app-lifespan `routine_app` test fixture;
  - `session_updated` confirmed to re-join web chats too (`socket.js:117`).

  Lows applied: the `{N} minutes` rounding, the `paused` server name, a named
  `is_continuable`, connector names from the repo, and a pure `classify`.

  **The leg is split** into 3a `routine-turn-path` (`legs/03`) and 3b
  `routine-runner` (`legs/04`). The scheduler is leg 5, the Tools merge leg 6,
  the marker and panel leg 7, the Routines tab leg 8, and the behavior test
  leg 9. The cancel-path tagging change for every turn is recorded as a
  deliberate behaviour change outside routines. Both new legs are `ready`;
  the fixes were precise, so there is no second review cycle.
- **Leg 5 `routine-scheduler`: high risk** (a new background loop and changes to the lifespan's startup and shutdown order). Its design review runs during the leg 1 implementation.
- **Leg 5 design review** (Developer, Sonnet): approve with changes. All
  applied in a rewrite:
  - **Highs:**
    - AC1's contradictory first-boot text was fixed;
    - a 1-second sleep floor plus per-routine isolation, so there is no hot
      loop;
    - the advance became a compare-and-set (`advance_if_due`), so an operator
      edit during a pass wins.
  - **Mediums:**
    - deleted-routine handling during a pass;
    - the missing repository queries;
    - the due pass runs before the startup zone recompute, which skips
      already-due routines;
    - the missed count's epsilon and its minimum of 1, with one-off miss
      wording;
    - the advance-to-spawn loss documented as accepted;
    - testability through a `sleep` seam, a `lambda` clock and a real-time
      poke test;
    - startup work runs inside the loop task, and boot is isolated from
      scheduler failures.
  - **Lows:** a `_stopped` flag, and `drain` makes `try_spawn` refuse.

  The fixes were precise, so there is no second cycle. Leg 5 is `ready`.
- **Leg 6 design review** (Developer, Sonnet): approve with changes. All
  applied:
  - **High:** both tab modules clear their host, so each section gets its own
    host `div` (AC2a rebuild isolation).
  - **High:** a full sweep of pinned strings and surfaces:
    - Library intro → "Knowledge and Tools tabs";
    - `mcp/errors.py:69` and its test → "Tools tab";
    - behavior specs, `agents.md`, inventory and CLAUDE.md lines, comments,
      and the `ui_capture` surface names kept.
  - **Medium:** the router alias goes in `resolve()`'s `agents` branch, and
    `studio-route` gets a `tools/` split. Section titles are `h2`. The deep
    link scrolls the tile into view.
  - The `mcp-connection` lane is added to the gates. Leg 6 is `ready`.
- **Legs 7 `message-marker-and-panel` and 8 `routines-tab`: high risk.** Leg 7 changes the client chat state machine (the routine in-flight state); leg 8 is a large new surface. Both get one combined design review.
- **Legs 7 and 8 design review** (Developer, Sonnet).
  - **Leg 7: approve with changes.** All applied as amendments:
    - a fourth testid element on facts;
    - per-session routine metadata through `setSessionMetadata`;
    - `data-routine-id` set in `addMsg`, not a factory option;
    - marker placement and validation;
    - the routine frame is gated on `session_id`, which leg 3 now adds;
    - ordering, the re-join, held-message and drafts cases;
    - refresh without flicker;
    - a `session_metadata` seeder kwarg.

    Leg 7 is `ready`.
  - **Leg 8: needs rework, split.** The decisions:
    - one-off "At" is sent as a local `{on: {date, time}}` and converted by
      the server in the operator zone, since the client has no local-to-UTC
      helper;
    - the tab loads lazily, with an `activate`/`deactivate` handle driven by
      `setActiveTab`;
    - a new `App.ui.checkboxGroup` factory;
    - the chooser lists all of the agent's chats, from
      `App.store.get('sessions')` at open;
    - schedule and target errors show on group status lines;
    - edit-mode dirty checks compare against the serialized initial state.

    New legs: `08-routines-tab-list` (8a) and `09-routines-tab-form` (8b).
    The behavior test becomes leg 10. A second review cycle runs on 8a and
    8b.
- **Legs 8 and 9 design review, cycle 2** (Developer, Sonnet): both approve
  with changes. All applied:
  - **Leg 8:**
    - activation is driven from the editor mount when the initial tab is
      Routines, because `App.ui.tabs` fires `onChange(initial)` before the
      panels exist;
    - `activate` and `deactivate` are idempotent and null-safe;
    - polling also stops on Studio area deactivate;
    - a same-identity patch does not refetch;
    - the poll cap reads `limits.run_timeout_seconds`, which leg 4 adds.
  - **Leg 9:**
    - the exact `on` parsing: a zone parameter loaded before the call, a
      strict date regex and `_parse_hhmm`;
    - the nested radio card `:has()` descendant bug is fixed with a direct
      child selector and a contract test;
    - explicit `checkboxGroup` classes, since wildcards fail the inventory
      regex;
    - unique testids for the At time selects;
    - edit-mode omissions and the zone-built day list.

  The maximum of two cycles is reached. Legs 8 and 9 are `ready`, and all
  legs from 3 to 9 are `ready`.
- **Batch A checkpoint review:** Reviewer on Sonnet, since the diff touches turn cancellation and lock bookkeeping, connector posting, and a security-model section. It reviews legs 1-5 against `main`.
- **Batch A review: `[HANDOFF:confirmed]`**, with no blocking issues. The
  unit gate gave 8078 passed and 15 skipped, and ruff is clean. Three
  non-blocking nits are accepted as they are:
  - Run now during shutdown returns the 409 "already running";
  - a duplicated `nxt` expression in `scheduler._handle`;
  - a function-local import in `runner._resolve_target`.

  Legs 1-5 are `completed`, and the Batch A checkpoint is committed.
