# Flight Log: Operator Routines, End to End

**Flight**: [Operator Routines, End to End](flight.md)

## Summary

Landed on `flight/01-operator-routines`. Batch mode:
- Batch A (legs 1-5, backend) was committed as `e8341d88`.
- Batch B (legs 6-9, UI) was committed as `de27abc4`.
- Leg 10's behavior test `routine-connector-delivery` passed 8 of 8 checkpoints (`tests/behavior/routine-connector-delivery/runs/2026-10-29-03-31-37.md`).
- Squawk 0283 was logged and deferred: an out-of-scope agent-create 500 found during the run.

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
- **Leg 10 `routine-connector-delivery-behavior-test`: low risk.** It only finalizes and runs an existing spec, and the Flight Director runs it through `/mission-control:behavior-test` after Batch B. No design review; `ready`.

### Leg 6: tools-tab-merge

Status: landed (not committed).

Built: the MCPs tab folded into Tools. `agent-editor.js` has five tabs; `buildPanel('tools')` builds two `App.ui.section`s ("Built-in tools", then "MCP servers", testids `agent-tools-builtin-section` / `agent-tools-mcp-section`), each with its own host div (`…-host`) because both child modules wipe their node; composite handle `{builtin, mcps, setAgent, destroy}`, `h.tools`/`h.mcps` are its children, and `h.destroy` now destroys it. `studio-route.js` splits `tools/{id}`, `agent-editor-controller.js` clears the selection when `tab !== 'tools'`, `router.js` `agents` branch aliases `agents/{name}/mcps[/{id}]` to `tools` (redirected, same pass as the legacy table, so one replaceState). `mcps-tab.js` `focusSource` scrolls the tile into view. "MCPs tab" copy and comments swept (library intro, MCP error copy, self-config status, behavior specs, HAT.md, comments). `scripts/ui_capture.py` surfaces keep their names, routes now `…/tools`. Registry, inventory, agents.md and CLAUDE.md updated.

Tests: re-pointed `test_studio_mcps_tab.py`, self-configuration tab, router items/core, frame, tabs, rules, scale, static contracts (5 tabs), nav helper; `RETIRED_SELECTORS` gains `tab-mcps` and `agent-tab-mcps`. New tests (in `test_studio_mcps_tab.py`): section order, one save across both sections (AC3), rebuild isolation (AC2a), legacy redirects (AC4).

Results (THE_ONE_TEST_NETNS=1, THE_ONE_REQUIRE_WEBKIT=1): agents green 416s; library 311s; mcp-connection 245s; shared 297s; contracts-controls 348s; agent-tabs 126 passed 251s (after fixing `test_flow_agent_rules` tab count 6 to 5); routing 186 passed 478s (after fixing a `test_router_core` parity corpus that pulled the new mcps alias through `_nav`). `make test-unit`: 8076 passed, 15 skipped, 2 failed (raw `location.hash` literals in my new test, and `tab-mcps` in the registry Retired table colliding with the live `tab-` prefix row), both fixed and re-run green (nav helper, ui_guards, token and a11y tests 445 passed). ruff check and format clean.

Measured tablist right edge at 1024px, five tabs: Chromium 893px, WebKit 883px (scroll/client 652/652), recorded in agents.md.

Grep for `mcps`, `tab-mcps`, `MCPs tab` in tests, scripts, docs, behavior: remaining hits are intentional (the retired-selector fence, router redirect rows and their tests, `mcps-tab.js` file name, the registry Retired row, historical release notes).

Deviations: (1) the `tab-mcps` row is not in the registry Retired table (the live `tab-` prefix row collides with the retired-id test); fenced in `RETIRED_SELECTORS` and noted on the `agent-tab-mcps` row. (2) `_nav.py` unchanged as specified, so the router-only mcps alias rows are excluded from `PARITY_CORPUS`. (3) The Tools-tab editor test for the CLAUDE.md "sixth" wording now says fifth; leg 8 raises it to six.

- **Leg 6 landed (FD read of the `[LAND:leg]` report).** The editor now has five tabs, with MCP servers as the second section of Tools. Six lanes and the static guards are green.
  - **Unit suite:** run before the last two fixes (8076 passed, 2 failed). After the fixes only the six affected unit files were re-run (445 passed), so the leg 7 Developer is told to run the full unit suite and to own any failure in leg 6's files.
  - **Accepted deviation:** `tab-mcps` is fenced in `RETIRED_SELECTORS` and not in the registry's Retired table, because the live `tab-` prefix row collides with it.
  - **Tablist width:** the right edge is 893px at 1024px in Chromium, so leg 8's sixth tab has room.
  - **Spawned:** a leg 7 Developer (Sonnet), standard implement prompt plus the batch overrides.

### Leg 7: message-marker-and-panel

Status: landed (not committed).

Built:
- **`App.ui.message` `marker: {label}`.** It renders an `App.ui.chip` (sm) in `span.ui-message-marker-chip`, on any role, after the operator chip and before the peer label and body. null and undefined are no-ops, and an empty or non-string label throws. CSS is in `components.css`, and the inventory row is updated.
- **Transcript.** `transcript.addUserEvent(ev, {ts, history})` is the one place a user event becomes a bubble, for live frames and replay. A routine event gets the routine name as attribution (side `you`), the "Routine" marker and `data-routine-id` (set in `addMsg`), with no prefix. Other sources keep theirs.
- **In-flight.** `turn-frames.js`: a `user` frame with `source === 'routine'` and `session_id === chatState.boundId()` sets `inFlightSessions[sid]` (never `ownTurn`), then calls `updateStopControl`, `applyComposerState` and `showThinking`, after the bubble.
- **Drawer.**
  - `setSessionMetadata(sid, meta)` and `refreshRoutines()` are called from `session_joined` in `socket.js`.
  - The metadata is kept per session id and dropped when the view's session differs.
  - A `chat-drawer-routine` fact shows when `session_metadata.routine` is set.
  - A read-only Routines group follows Notes: A-Z, meta Done over Off over "Next {day} {time}", refreshed without flicker with token, gen and agent guards. The default and deleted agents omit the group.
- **Seeder and lane.** `seeders.seed_session(..., session_metadata=)`; the new test file is in `chats_transcript_pat`.
- **Docs.** `docs/ui-testid-registry.md` has three new rows, and `agents.md` and CLAUDE.md are updated.

Tests: new `test_flow_chat_routine_marker.py` (7: replay, live gate and in-flight and hold and done, Stop cancel, `done` idle, api prefix kept, drawer fact and group, no-metadata, no leak to another chat), plus a marker contract case in `test_ui_message_contract.py` (both engines). The drawer label-order assertion in `test_flow_chat_drawer.py` gains "Routines".

Results (THE_ONE_TEST_NETNS=1):
- `chats-transcript`: 97 passed, 230 s.
- `chats`: 166 passed, 311 s (after updating the group-order assertion).
- `contracts-chat` with `THE_ONE_REQUIRE_WEBKIT=1`: 148 passed, 50 s.
- Static guards (`ui_guards`, `token_definitions`, `design_tokens_a11y`, plus inventory, emitted classes, ownership, nav helper, lanes, `store_static`, `tool_categories`, area size): 493 passed.
- `make test-unit`: 8078 passed, 15 skipped.
- ruff check and format: clean.

Deviations:
1. The 800-line area-module rule failed, because `agent-drawer.js` reached 869 lines. The Routines helpers and the Notes item builders moved to a new `areas/chat/agent-drawer-parts.js` (`App.chat.drawerParts`, with a script tag in `index.html`), and `agent-drawer.js` is now 780.
2. The fourth facts-pair element was dropped. The testid guard needs a literal `setAttribute('data-testid', ...)`, so the last `dd` is tagged at the call site instead.
3. The Done and Off meta wording is as specified. The day label is Today, a weekday within 6 days, or `Mon D`.
4. Leg 6's two unit failures were already fixed before this leg, and the full suite is green.

The "draft survives `session_updated`" case is covered by the existing per-chat draft behaviour. This leg adds no explicit test for it, and the mid-run re-join order is covered by the existing `is_processing` path.
- **Leg 7 landed (FD read of the `[LAND:leg]` report).** It covers `App.ui.message` `marker`, `transcript.addUserEvent`, the routine in-flight state in `turn-frames.js`, the drawer's routine fact and the Routines group.
  - **Gates:** `chats-transcript` 97, `chats` 166, `contracts-chat` 148; unit tests 8078 passed, 15 skipped. The full unit run is green, which closes leg 6's open unit re-run.
  - **Deviations accepted:**
    - `agent-drawer-parts.js` was split out to stay under the 800-line rule. It adds a script tag to `index.html`, so a running dev instance needs a restart to pick it up.
    - The optional fourth `facts` pair element was dropped in favour of a call-site testid.
    - Two re-join edge cases rely on existing per-chat behaviour, with no new test. The Batch B Reviewer should look at them.
  - **Spawned:** a leg 8 Developer (Sonnet). It was told about the tab-count pins and the 1024px tablist width check.

### Leg 8: routines-tab-list

Status: landed (not committed).

Built:
- **Routines tab** between Tools and Self-configuration (six tabs). `routines-tab.js` returns `{setAgent, activate, deactivate, destroy}`; `routines-describe.js` is the pure helper set leg 9 reuses.
- **Rows** are built once per routine and patched in place, so the 3 s poll keeps an open History, an armed Delete and focus. Row controls are the switch, Run now (409 shown inline), armed Delete and a History disclosure that pages with `before`.
- **Activation.** It is activated at the end of the editor mount when the tab is selected, and from `setActiveTab`. Studio `deactivate` stops the poll and Studio `activate` resumes it.
- **Form hooks.** New routine and Edit are hidden until `App.studio.routinesForm` exists.
- Route whitelist, callbacks in `agent-data.js` and the controller, script tags, CSS, 24 registry rows, `agents.md` section, CLAUDE.md "sixth".
- Pins moved from 5 to 6 in rules, tabs, frame, scale and the static contracts test.
- Lane: the new `test_flow_agent_routines.py` (17 tests) is in `agent-tabs` via `agent_tabs_pat`.

Tablist right edge at 1024px with six tabs: 979px Chromium, 967.5px WebKit (scroll/client 652/652).

Results (THE_ONE_TEST_NETNS=1, THE_ONE_REQUIRE_WEBKIT=1):
- `agent-tabs`: 143 passed, 310 s.
- `agents`: 170 passed, 414 s.
- `routing`: 186 passed, 478 s.
- Static guards (ui_guards, token_definitions, design_tokens_a11y, editor contracts, ownership, lanes, area size, nav helper, time getters, emitted classes, inventory): 471 passed.
- `make test-unit`: 8078 passed, 15 skipped.
- ruff check and format: clean.

Deviations:
1. Delete's aria-label is updated by name change (not by the `confirm-delete` class, which the ownership guard forbids).
2. No browser test for the Done row UI or for paging past 20 runs; Done precedence is covered through the describe helpers.
3. A poll test leaves to Settings, not Chats, because Chats auto-joins the run's new chat and its drawer fetches `/routines` itself.
- **Leg 8 landed (FD read of the `[LAND:leg]` report).** The editor now has six tabs, with Routines between Tools and Self-configuration.
  - **Tablist width:** the right edge at 1024px is 979px in Chromium and 967.5px in WebKit, with no overflow.
  - **Gates:**
    - lanes: `agent-tabs` 143 passed, `agents` 170 passed, `routing` 186 passed;
    - unit tests: 8078 passed, 15 skipped;
    - the static guards and ruff are clean.
  - **Deviations accepted:**
    - Delete's `aria-label` is patched without a class check, because of the ownership guard.
    - The Done row and paging past 20 runs are covered by the describe helpers only. The Batch B Reviewer should look at this.
    - The poll-stop test leaves to Settings instead of Chats.
  - **Spawned:** a leg 9 Developer (Sonnet), the last autonomous leg of Batch B.

### Leg 9: routines-tab-form

Status: landed (not committed).

Built:
- **`App.ui.checkboxGroup`** (`ui/choice.js`): fieldset, legend and one `App.ui.checkbox` per option; `value()` in option order, silent `setValue`/`setDisabled`, `focus`, `destroy`; missing legend or options throws. Inventory row, CSS, and `test_ui_checkbox_group_contract.py` (both engines, `contracts-controls`).
- **Nested radio fix (AC2b).** The checked-card rule (and its forced-colors twin) is now `.ui-radio-option:has(> .ui-radio-label > .ui-radio-input:checked)`. A nested-group case is in `test_ui_radio_group_contract.py` (outer card styled checked only for its own radio; nested radios and an inner select never fire the outer `onChange`).
- **Server `on` input.** `_routine_schedule(raw, now, zone)` accepts `{kind: "once", on: {date, time}}` (exact keys, strict date regex, `_parse_hhmm`, `resolve_wall_time` in the effective zone, then the existing past and one-year checks). POST and PUT load the zone first. Tests in `tests/test_routines_api.py`: zone conversion (LA and Kolkata), gap end (2027-03-14 02:30 -> 10:00Z), repeated hour (first occurrence), past, too far, ten malformed shapes (list 422 on `loc ["schedule"]`), and a PUT with `on` on a Done one-off clearing `finished_at`. The resolver's own DST tests already live in `test_routines_schedule.py` (leg 1), so none were added there.
- **`routines-form-model.js`** (pure: `defaultState`, `scheduleBody`, `targetBody`, `formToBody`, `bodyToFormState`, `dayOptions`, `hourMinuteOptions`, `precheck`) and **`routines-form.js`** (the inline form, the nested "When" group, one shared time row moved into the selected kind's slot, the chat chooser). `routines-tab.js` hosts it in `.routines-form-host` above the list and discards it on `deactivate`/`destroy`; leg 8's hide-until-form checks are gone (and their test now asserts the buttons show).
- **Plumbing.** `createRoutine` in `agent-data.js`, the controller bag and `agent-editor.js`' routines callbacks; script tags; `studio.css` form styles.
- **Docs/tooling.** Registry rows (plus the `routine-form-day-` prefix family), `the_one/agents.md` "Routine form (M33 F1 L9)" and the Form hooks bullet, CLAUDE.md Routines paragraph, `scripts/ui_capture.py` surfaces `agent-routines` and `agent-routines-form` (three seeded routines through REST; the next-run weekday and time are masked) captured to a scratch directory in both themes and widths: 8 PNGs, 0 failed.
- **Tests.** `tests/browser/test_flow_agent_routines_form.py` (18 tests, `agent-tabs` lane via the `test_flow_agent_routines*` glob, no `run-tests.sh` edit needed): each schedule kind, each target kind, the chooser (filter, platform search, Enter, Escape, focus return, empty and failed-load lines), edit omissions (name-only PUT, reverted field, kind and target change), 409 on Name, field errors, schedule and target group errors, discard on tab leave, and the pure model through `page.evaluate`.

Results (THE_ONE_TEST_NETNS=1, THE_ONE_REQUIRE_WEBKIT=1; one lane at a time, solo):
- `agent-tabs`: 161 passed, 518 s (up from 143 and 310 s at leg 8 on a different host load).
- `agents`: 170 passed, 414 s.
- `contracts-controls`: 1062 passed, 4 skipped, 350 s.
- Static guards (ui_guards, token_definitions, design_tokens_a11y, control_inventory, ownership, emitted_classes, area_module_size, nav_helper, time_getters, studio_editor_contracts, ui_capture_safety, run_tests_lanes): all passed.
- `make test-unit`: 8092 passed, 15 skipped, 415 s.
- ruff check and format: clean.

Deviations:
1. **Platform badge.** `App.ui.searchList` has no badge slot, so a connector chat's platform name shows on the row's description line (and the day as the meta) instead of a neutral badge.
2. **Lane re-measure (AC8).** Not done on a quiet-host `--parallel 3` run (the quiet-host rule forbids re-budgeting from a solo run). The solo 518 s is not comparable to the 294 s parallel reading; the 18 new tests are about 42 s solo. The Flight Director should re-measure `agent-tabs` in the next full parallel run and re-budget (360 s now) if it moved more than 15%.
3. **Form state variable** is `fs` in `routines-form.js`, because `test_studio_editor_contracts_static.py` scans every studio module for `state.x =` writes against the shell's declared keys. Testids on the form's selects are stamped with literal `setAttribute` calls because the registry guard rejects variable testid values.
4. **The `{kind: "once", on}` precheck for "At" in the past** compares operator-zone wall time as strings (a DST edge is left to the server, which stays the authority).
- **Leg 9 landed (FD read of the `[LAND:leg]` report).** Batch B's autonomous legs are complete.
  - **Gates:**
    - lanes: `agent-tabs` 161 passed, `agents` 170 passed, `contracts-controls` 1062 passed / 4 skipped;
    - unit tests: 8092 passed, 15 skipped;
    - the static guards and ruff are clean.
  - **Deviations accepted:**
    - A chat's platform shows on the chooser's description line, because `searchList` has no badge slot.
    - The past-"At" pre-check is wall-clock only; the server decides DST edges.
    - The literal testids and the `fs` variable name were chosen to fit the guards.
  - **Re-budget open:** the AC8 lane re-measure is deferred. `agent-tabs` grew by 18 tests and ran 518 s solo, against a 360 s budget. Under the quiet-host rule only a `--parallel 3` reading can re-budget it, so the FD will measure `agent-tabs` in the next quiet `--parallel 3` run and re-budget if it moved more than 15%.
- **Batch B review.** The Reviewer runs on Sonnet: the diff touches the self-configuration and MCP copy (`the_one/mcp/*`, the self-configuration tab) and an API write boundary (the schedule `on` parsing). The Accessibility Reviewer (Sonnet, required for UI flights) runs in parallel. Each is told to run at most one browser run at a time.
- **Batch B review results.**
  - **Code review:** the Reviewer signalled `[HANDOFF:confirmed]` with no blocking issues, and listed stale "MCPs tab" prose in `agents.md` and the control inventory.
  - **Accessibility review:** no blocking issues, and five non-blocking findings.
  - **FD call:**
    - Fix accessibility findings 1-4: focus after Run now, spoken Run now start and finish, the chosen chat announced, and the Days focus on a weekly save with no days.
    - Fix the stale prose.
    - Accept finding 5 (h2 versus h3 across tabs): it is a pre-existing pattern and valid either way.
    - Run-history paging past 20 is already API-tested (`test_routines_api.py`, `limit`/`before`), so no browser test is added for it.
  - **Spawned:** a fix Developer (Sonnet). These fixes are cosmetic and accessibility work, so there is no re-review; the fix gates (unit tests, `agent-tabs`, the static guards) are the check.

### Batch B review fixes
- Run now keeps focus in the row (paint moves focus to the row toggle when it disables a focused Run now); a polite `routines-live` line announces "Started {name}" once and "{name}: {outcome}" once when that run settles (polls stay silent).
- The routine form's Choose chat button name carries the choice ("Choose chat, current: X"); a weekly save with no day focuses the first day checkbox (the `checkboxGroup` handle already had `focus()`).
- Stale "MCPs tab" prose fixed in `the_one/agents.md` (795, 829, 1184) and `docs/ui-control-inventory.md` (groupTile row). Heading levels across tabs accepted as-is. Tests added in `test_flow_agent_routines.py` and `test_flow_agent_routines_form.py`.
- **Batch B fixes accepted.** Accessibility findings 1-4 and the stale prose are fixed, with new assertions in the two routines browser files. `agent-tabs` passed 161.
  - **Unit suite:** it failed 1 (the unregistered `routines-live` testid), which was then registered. The FD runs the batch gate before committing, so the unit suite is re-run there.
  - **Batch-end gate:** the unit suite, then `--parallel 3` across every lane, on a quiet host (load 0.79 at start). This also gives the quiet-host reading for the `agent-tabs` re-budget that leg 9 AC8 deferred.

- **Batch B gate and checkpoint.** Unit tests: 8092 passed, 15 skipped. `--parallel 3` across all 16 lanes was green (`rc=0 total=1724s`). `agent-tabs` was re-budgeted from 360 to 540 s (it measured 410 s). Legs 6-9 are `completed` and committed as the Batch B checkpoint.

### Leg 10: routine-connector-delivery-behavior-test

- **Spec finalized (AC1).** The FD re-read every step against `_routine_view`, `RoutineRun.model_dump()` and the `/_test/stub/*` seams, then corrected these names:
  - `trigger_kind`, the target body `{kind, session_id}`, `once` as `{kind, at}`;
  - the outbound record's `content`, and the inbound body's `connector_id`/`peer_id`/`text`/`is_dm`;
  - `config.default_agent`.

  It also added a step-1 Expected Result. The spec's status is `active`.
- **Run (AC2).** `/mission-control:behavior-test routine-connector-delivery` passed 8 of 8 checkpoints, in live mode with Sonnet as Executor and Validator. The run was against port 8490, a scratch data dir under `$HOME` and a scratch cwd, with the credential rotated first.
  - **Checkpoints:**
    - The reply reached the connector, and the prompt never did.
    - The run is stored as the routine's (`routine_name`, `visibility` `operator`, `session_metadata.routine`).
    - A one-off fired from the scheduler on its own, 0.8 s after its due time, and ended Done.
    - After `/new`, a run landed in a new chat and the routine re-pointed to it.
    - The peer's next DM continued that chat.
  - **Run log:** `tests/behavior/routine-connector-delivery/runs/2026-10-29-03-31-37.md`.
- **Teardown (AC3).** The instance was stopped by its recorded PID, the scratch dir was removed, and the default data dir's mtimes were identical before and after. Nothing touched 8484 or 8485.
- **Finding, by design.** A routine delivers through `keying_to_target(row)`, which gives a `ChannelTarget`, while an inbound DM reply uses `PeerTarget`. Real DM rows carry the platform's DM channel id. Only the stub seam leaves it `""`. No product change was needed.
- **Spec re-authored after the run** from the Validator's feedback. No step's intent changed:
  - step 1 names `config.default_agent` and the mock provider's `base_url`;
  - step 7 compares against step 4's routine record and explains the two target shapes;
  - a Preconditions bullet requires a before-count of outbound before every triggering action.
- **Squawk 0283 (defect, routine, deferred).** `POST /api/agents` with an empty `provider_config_id` returns 500 (a foreign-key `IntegrityError`) instead of 422. The Executor's unintended step-1 request hit it. It is pre-existing and unrelated to routines.

### Flight landing (FD)

- **All legs `completed`** (1-10), with flight-log entries for every leg.
- **Docs verified.** CLAUDE.md's "Routines (M33 F1)" paragraph covers the REST routes, the scheduler, the Routines tab and form, the `on` input and `THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS`. These also cover the flight:
  - `the_one/agents.md` (44 routine references, including "Routines (M33)", "Routines tab", "Routine form");
  - `SECURITY-MODEL.md` "Routines (Mission 33)";
  - `the_one/connectors/README.md`;
  - the testid registry and the control inventory (`App.ui.checkboxGroup`).
- **Status:** the flight is `landed`, Flight 1 is checked off in `mission.md`, and a draft PR is opened. A flight debrief (`/mission-control:flight-debrief`) is recommended next, on this branch.
