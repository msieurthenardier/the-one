# Leg: new-chat-every-run-backend

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Remove the routine **target** from the backend. Every routine run, operator or
agent made, starts a new web chat owned by the routine's agent and titled with
the routine's name. Routines no longer deliver to connectors: posting to a
platform is the agent's existing `send_to_platform_channel` tool, used only
when the prompt asks for it. The data model, migration, service, runner, turn
path, REST API, agent tools (and their text, with an eval run), unit tests and
backend docs change together, and every piece of code, test, comment and doc
that only served targets or routine connector delivery is deleted, not left
dormant (operator: "be sure the code and tests get cleaned up, dont want stale
code/comments laying around").

## Context

- **Operator decision at the HAT (flight log, "Operator decision: every run
  starts a new chat")**: the target choice was hard to understand; "always do
  new chat no matter what. It's limiting, but intuitive." No routine
  connector delivery ("the prompt can simply say 'post to discord'... we
  don't need a special mechanism"). Agent follow-ups start a new chat too.
- **Leg 03** (`new-chat-every-run-ui`) removes the form's target group, the
  chat chooser and the other client pieces, and adds the run-history chat
  link. This leg ships the backend contract leg 03 builds on, including the
  run history's chat-existence flag (AC6). The UI is broken between the legs
  only in ways leg 03 removes (the form still sends `target`; see DD3); both
  legs land and are reviewed together before the walk resumes.
- **The consumer inventory** (an Explore pass at `7dd144d5` plus the HAT
  fixes) is summarized under Files Affected; every item there is in scope.
- **Platform tools premise (verified):** `send_to_platform_channel`
  (`the_one/tools/connector_send.py::SendToPlatformChannelTool.execute`) DMs
  an allowlisted peer from a web chat with an explicit
  `{connector_id, peer_id}` target when the agent is the connector's
  `default_agent`; `find_platform_destination`
  (`tools/connector_lookup.py`) finds those ids from observed peers. Both
  are on by default for every agent (`tools/builtins.py::_TOOL_CLASSES`),
  seeded on the first turn for an agent named in a connector binding
  (`agent/factory.py` ~:551-581).

### Design decisions (leg-level)

**L2-DD1. Schema v49, a frozen migration.**
- `agent_routines` loses `target_kind` (with its inline CHECK) and
  `target_session_id`, `target_platform`, `target_connector_id`,
  `target_channel_id`, `target_thread_id`, `target_peer_id`, by **seven
  guarded `ALTER TABLE ... DROP COLUMN`s** (the v38 idiom: each checked
  against `PRAGMA table_info` first). The design review verified on this
  venv's SQLite (3.45.1) that DROP COLUMN works on a column with its own
  inline CHECK, beside a UNIQUE on other columns, with child FKs intact;
  none of the seven is indexed, in a UNIQUE or referenced by an FK. The
  migration is a no-op on a database where `agent_routines` /
  `agent_routine_runs` are absent (hand-built fixtures), as v48 is.
- `agent_routine_runs.new_chat` is dropped the same way (every run is now a
  new chat, so it carries nothing); `session_id` stays (the run's chat;
  leg 03 links to it). `RoutineRun.new_chat` and the `new_chat` parameter
  of `AgentRoutineRepository.finish(...)` go with it.
- The references into `agent_routines(id)` from `agent_routine_runs`
  (`ON DELETE CASCADE`) and `agent_routine_proposals` (`ON DELETE SET NULL`)
  still hold: `TestSchemaV49` asserts `PRAGMA foreign_key_check` is clean,
  deletes a routine and sees both behaviours, and asserts each table's
  `table_info` column names equal the expected list exactly.
- **Proposals:** v49 carries its own frozen helpers (`_v49_*`, copied from
  the v48 pattern such as `_v48_loads`; never the live service; the
  `frozen-migration-converter-with-guarded-failure-row` convention). It
  removes `payload["target"]` and `base["target_kind"]` /
  `base["target_session_id"]` from every proposal. A pending `delete` has no
  target and is untouched. A **pending** `update` whose payload is empty
  afterwards is set to `superseded` (valid in the v46 status CHECK: applied,
  pending, dismissed, superseded) with `resolved_at` set, as
  `supersede_pending` does. A row whose JSON cannot be read is left
  untouched and logged, never failing startup. v49 never touches
  `agent_routine_proposals.session_id` (the chat the proposal came from,
  not a target).
- `CURRENT_VERSION` 49; the 11 version pins in `tests/test_db_migration.py`
  move; a `TestSchemaV49` class covers: columns gone, data kept (every other
  column of every routine and run), indexes, FK behaviour, the proposal
  rewrite (pending create, pending target-only update superseded, applied
  history stripped, unreadable JSON untouched), idempotence (running the
  guard twice), and an upgrade from a v48 database built by the real chain.

**L2-DD2. The run path.**
- `runner.py`: target resolution becomes `host.create_web_session(
  routine.agent_name, routine.name)` for every run. Deleted: the connector
  pre-check ("isn't connected", "is now answered by"), `_resolve_target`,
  `NEW_CHAT_GONE` and its reason append, `set_target_session`, the
  `RunRegistry` pause memory (`_pauses`, `remember_pause`, `own_pause`,
  `clear_pause`) and the paused peek with `REASON_WAITING_SIGN_IN`, the
  `connector_name` parameter and delivery branches of `classify`, the
  `last_inbound_at` post-step, and every import only those used.
- The "chat stayed busy" wait: confirmed unreachable at design review (a
  fresh session has no lock contention; `turn_info["started"]` is set once
  `track_turn` takes the lock). Delete `REASON_CHAT_BUSY`
  (`repository.py` ~:34) and its test pin (`test_routines_runner.py`
  ~:295). `classify`'s remaining `timed_out and not started` branch returns
  the existing "took longer than N minutes" failure (FD call: no new
  wording). Keep `mark_silent_and_cancel` / `discard_silent` (the
  unstarted-timeout and interrupt paths need them). Delete
  `TurnHost.peek_session`, its `app.py` implementation and the test fakes'
  copies once the paused peek is gone.
- A run that needs a sign-in still fails with the existing "Needs a
  sign-in…" sentence; the next run starts a fresh chat.
- `app.py`: the routine delivery block in `_process_and_broadcast`, the
  routine step-limit platform line, the `routine` dict's `target` and
  `connector_id` keys, the `delivery` out-key and its docstring/comment
  lines; the `delivery.py` imports that only those used.
- `connectors/delivery.py` keeps `deliver_final_reply`,
  `send_step_limit_line` and `authorized_agent_for` (inbound and
  `connector_send` use them). **Remove `DeliveryResult` and
  `deliver_final_reply`'s return value**: the design review found no
  non-routine reader (`inbound.py` ~:313 discards it). Update
  `tests/test_connector_delivery.py` (`test_deliver_statuses`); the inbound
  pipeline's behaviour must not change (its characterization tests pass
  unedited except that pin). Drop the module docstring's routine-runner
  mention, and update `the_one/connectors/README.md` (~:146-157), which
  names the delivery primitives.
- Dead imports after the cut, to remove: in `runner.py`
  `ConnectorRepository`, `get_manager`, `authorized_agent_for`,
  `keying_to_target`, `is_continuable`, `_resolve_continuation_seconds`,
  `ChatSession`, `get_encryptor`, `settings`, `uuid`, `now_iso` (each only if
  unused); in `app.py` check `step_clean` and `_connector_manager` for
  leftovers.

**L2-DD3. The REST API and service.**
- `service.py`: delete `resolve_target`, `_target_body`, the `target`
  handling in `create_routine` / `update_routine` / `agent_change` /
  `approve_proposal` / `_hypothetical`, the target entries in `_BASE_KEYS`
  and `_PAYLOAD_TO_BASE`, the view's `target` object, and the `chat_repo`
  parameters that only served targets (and their plumbing in
  `routines_api.py`).
- A request body that still carries `target` is ignored like any other
  unknown key (verified at design review: `_routine_body` returns a bare
  dict and the service reads only named keys). A PUT whose only key is
  `target` is therefore an empty update: pin its response (whatever the
  update path does today with an empty diff: a 200 with no write, or a
  422) in a test, and record it in the flight log.
- `GET .../routines/{id}/runs` (`routines_api.py::list_agent_routine_runs`)
  gains, per run, `chat_exists: bool`, from one batched lookup: a new
  `ChatSessionRepository.existing_ids(ids) -> set[str]` (one
  `WHERE id IN (...)` query), unit-tested. `new_chat` leaves the run view.
  `routine_view` and `list_agent_routines` lose `chat_repo`.

**L2-DD4. The agent tools, their text, and evals.**
- `tools.py`: delete `target` from `schedule_routine` and `change_routine`
  (schemas, arguments, `coerce_target`, `_resolve_target`, `_TARGET_*`,
  `NO_CHAT_REFUSAL`, `TARGET_REFUSAL`), the "Runs in" line of
  `list_my_routines`, and the "in {target}" words in results and proposal
  descriptions. `describe.py::describe_target` goes.
- The tool text says, briefly: each run starts a new chat with only the
  routine's prompt, so write the prompt so it stands alone (what to check
  and what to do with the result, including any message to a platform).
  Keep the change minimal; it is platform prompt text (CLAUDE.md "Prompt
  evals"). The proposal's `session_id` (the chat it came from) and the
  taint snapshot stay.
- **Evals:** `evals/checks.py` loses the target param, `_TARGETS`,
  `_target_ok`, `RoutineView` target fields and `RunTrace.session_ids` if
  nothing else reads it; `evals/harness.py` loses the `this_chat` chat-row
  setup and the target copies; `routines-follow-up.toml` loses
  `target = "this_chat"`; `evals/README.md` updated;
  `tests/test_evals_routines.py` updated. The eval **runs** need the plan
  token and burn quota, so the Flight Director runs them after the review:
  1. a git worktree at the pre-leg commit (the old prompt) with the leg's
     new `evals/` files copied in (checks and harness without target, the
     scenario without `target = "this_chat"`); `baseline` there rewrites
     `evals/baselines/m33-routines.json` (CLAUDE.md: a changed scenario set
     needs a same-prompt re-baseline). The old code defaults an omitted
     target to `this_chat`, which differs from the new behaviour; the FD
     records that as a known confound of the baseline cell;
  2. `compare` on the leg-02 tree against the new `m33-routines` baseline;
  3. `measure-prompt`, then `compare --baseline evals/baselines/m30-platform.json`.
  The Developer leaves the tree ready for these and runs `make test-unit`
  (which covers the offline eval tests).
- **Size:** the `m30-platform` size target is ratio 1.0 (no larger than the
  baseline). Deleting the target schema and text must outweigh the added
  "each run is a new chat; write a prompt that stands alone" sentence. The
  Developer measures it before landing (`make eval ARGS="measure-prompt"`
  needs the `[evals]` extra and no model calls) and reports the
  routine-tools token count against Flight 3's 945.

**L2-DD5. Docs.** CLAUDE.md's Routines paragraph (the target sentence and
"for a connector chat, posts only the reply"); `the_one/agents.md` "Routines
(M33)" (every target and delivery bullet listed under Files Affected) and its
"Delivery primitives" line (~:1010); `SECURITY-MODEL.md` "Routines": the
connector-routine and authorized-agent paragraphs (~:606-607) become one
statement that a routine posts to a platform only through
`send_to_platform_channel`, authorized at call time by the binding and
allowlist rule, with no human present.

## Acceptance Criteria

- [ ] AC1. Schema v49 drops the seven target columns and `new_chat`, keeps
      every other column and row, keeps both FK behaviours into
      `agent_routines`, and rewrites proposals per L2-DD1; `TestSchemaV49`
      covers every L2-DD1 bullet; the version pins are 49.
- [ ] AC2. Every routine run creates a new web chat titled with the
      routine's name; a unit test runs one routine through each trigger
      (scheduled, Run now, catch-up) and sees three distinct chats.
- [ ] AC3. No routine code path delivers to a connector, pre-checks a
      connector, reuses a chat, or keeps pause memory; the inbound pipeline's
      tests pass with at most the `DeliveryResult` pin changed.
- [ ] AC4. The routine REST routes neither accept nor return a target; the
      behaviour for a stray `target` key is the routes' existing unknown-key
      behaviour, recorded in the flight log.
- [ ] AC5. `schedule_routine` and `change_routine` take no target; tool
      results and `list_my_routines` say nothing about where a routine runs;
      the tool text tells the agent each run is a new chat with only the
      prompt.
- [ ] AC6. The runs route reports `chat_exists` per run, from one batched
      lookup.
- [ ] AC7. **Clean-up grep** (run and quote in the flight log):
      `grep -rnE "target_kind|target_session_id|target_platform|target_connector_id|target_channel_id|target_thread_id|target_peer_id|resolve_target|_target_body|describe_target|coerce_target|this_chat|own_chat|NEW_CHAT_GONE|set_target_session|own_pause|remember_pause|clear_pause|REASON_WAITING_SIGN_IN|REASON_CHAT_BUSY|TARGET_REFUSAL|NO_CHAT_REFUSAL|DeliveryResult|peek_session" the_one/ tests/ evals/ CLAUDE.md SECURITY-MODEL.md --exclude-dir=browser`
      has hits only in `the_one/db/schema.py`'s frozen migrations (v45,
      v46, v48, v49) and `tests/test_db_migration.py`'s tests of them; and
      `grep -rnwE "new_chat" the_one/routines the_one/db/schema.py the_one/interfaces/web/routines_api.py the_one/interfaces/web/app.py tests/test_routine* evals/`
      has hits only in the frozen migrations. `tests/browser/` and
      `scripts/ui_capture.py` are leg 03's.
- [ ] AC7b. The routine-tools prompt cost is measured
      (`measure-prompt`) and reported against Flight 3's 945 tokens; it is
      not larger (the `m30-platform` ratio-1.0 size target).
- [ ] AC8. No comment or docstring in a touched file still describes
      targets, delivery for routines, pause reuse or own chats.
- [ ] AC9. `THE_ONE_TEST_NETNS=1 make test-unit` passes (15 skipped);
      `ruff check` and `ruff format --check` clean.

## Verification Steps

- AC1-AC6: the named unit tests; `TestSchemaV49`.
- AC7-AC8: the grep, quoted; a read of each touched file's docstrings.
- AC9: the commands.

## Edge Cases

- A pending agent **create** that carried a target: after v49 its payload
  has no target and it can still be approved.
- A routine whose old target was a connector chat stops posting there after
  the upgrade. That is the decided behaviour; record it in the flight log
  for the mission debrief and any release note. No prompt is rewritten.
- `taint`: a run's `routine_untrusted_sources` snapshot is unaffected; a
  write from a connector chat is still flagged through `compute_taint`.
- The `default` agent still cannot own routines.
- **Between legs 02 and 03 the browser lanes are red** (the seeders' raw
  INSERTs name `target_kind`; the tab's tests expect targets). Legs 02 and
  03 are one batch: browser lanes are not a gate for leg 02, only for 03.
  The tab does not throw meanwhile (`describeTarget(undefined)` returns '').
- **Chats volume** (record for the debrief): a frequent routine now creates
  a chat per run (every 10 minutes is 144 a day); retention is the only
  bound. Operator's decision.
- Purge now and the retention sweep still work (no target column in their
  SQL; `tests/test_retention.py` fixtures drop `target_kind`).

## Files Affected

Shared with leg 03: `the_one/agents.md` (leg 02 edits the backend bullets,
leg 03 the form/tab bullets), the flight log.

- **Schema:** `the_one/db/schema.py` (v49), `tests/test_db_migration.py`.
- **Routines:** `the_one/routines/models.py` (`TargetKind`, target fields,
  `RoutineRun.new_chat`), `repository.py` (`_COLS`, `_INSERT_COLS`,
  `_UPDATABLE`, `_routine()` indices, `create()`, `set_target_session`, run
  rows), `proposals.py` (docstring), `service.py`, `runner.py`, `tools.py`,
  `describe.py`.
- **Web:** `the_one/interfaces/web/app.py` (routine delivery, step-limit
  line, `routine` dict keys, imports), `routines_api.py` (`chat_repo`
  plumbing, runs `chat_exists`).
- **Connectors:** `the_one/connectors/delivery.py` (docstring; possibly
  `DeliveryResult`), `tests/test_connector_delivery.py` (only if so).
- **Unit tests:** `tests/test_routines_service.py`, `test_routines_api.py`,
  `test_routines_runner.py`, `_routine_app.py` (`Harness.routine`, `dm()`),
  `test_routine_turn_path.py`, `test_routines_classify.py`,
  `test_routine_tools.py`, `test_routine_tools_taint.py`,
  `test_routines_proposals.py`, `test_routines_repository.py`,
  `test_routines_scheduler.py`, `test_routines_self_config_api.py`,
  `test_retention.py`, `test_name_repair.py`, `test_api_name_rule.py`,
  `test_evals_routines.py`, `test_connector_delivery.py`. Target-only tests are deleted; tests that used a
  target incidentally lose it; tests of reuse/pause/delivery are deleted
  with their code.
- **Evals:** `evals/checks.py`, `evals/harness.py`,
  `evals/routines/scenarios/routines-follow-up.toml`, `evals/README.md`.
- **Docs:** CLAUDE.md, `the_one/agents.md` (incl. ~:1010 and ~:2842),
  SECURITY-MODEL.md, `the_one/connectors/README.md` (~:146-157).
- **Behavior specs (FD, artifact work after the batch review):**
  `tests/behavior/routine-connector-delivery.md` and its `runs/` are
  deleted (the spec exists only for target delivery; git history keeps
  them); `tests/behavior/agent-schedules-follow-up.md` is re-authored
  (header ~:18-19 and step 3 ~:104 assert `target.kind` /
  `target.session_id`; step 4's outbound record no longer comes from the
  run) and re-run.
- **Browser seeders** used by unit-tier code: `tests/browser/seeders.py`
  (`seed_agent_routine` raw INSERT) is leg 03's, but if a unit test imports
  it, fix it here.

## Citation Audit

From the consumer inventory at `7dd144d5` (Explore pass, file:line cited
there): schema v45 target columns (:3053-3059), v46 proposals (:3097-3147),
v37 rebuild precedent (:2404-2475), v38 DROP COLUMN precedent
(:2477-2530); `service.resolve_target` (:129-164), `_BASE_KEYS`
(:376-385); `runner._resolve_target` (:239-309), pre-check (:326-353),
pause memory (:102, :129-148, :386-395); `app.py` routine delivery
(:2756-2784) and step-limit line (:2828-2837); `tools.py` target pieces
(:55-189, :268, :293-312, :335-412); `connector_send.py::execute`
(:136-208). The Developer re-reads each before editing (line numbers drift
with the HAT fixes).
