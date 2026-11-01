# Leg: agent-routine-tools

**Status**: completed
**Flight**: [Agents Schedule Their Own Routines](../flight.md)

## Objective

Give an agent four native routine tools, seeded only while its Routines item
is on. Every write goes through leg 2's `agent_change` and carries an
untrusted-content flag. The flag is computed from the conversation the model
has seen, including routine runs, and that judgement lasts for the life of
the chat. The leg ends with a scripted proof at the unit tier and the
security-model section.

## Context

- **Flight DDs:** DD1 (native tools, factory hook, seeded), DD2 (the tools'
  shapes and results), DD7 (taint), DD8 (the per-turn counter only; the other
  caps are leg 2's), DD9 (races).
- **Leg 2 built the write path.** It provides
  `service.agent_change(conn, agent_name, action, data, *, now, zone, taint, session_id)`
  and `AgentChangeResult(pending, replaced, routine, proposal_id,
  routine_id)`. It also does the call-time switch check, the validation, the
  caps, the proposals, the flag merge and the scheduler poke. Read the leg 2
  entry in the flight log for the landed names, and use them.
- **This leg adds only:**
  - the turn context;
  - the taint computation;
  - the per-turn counter;
  - argument coercion;
  - the result and refusal wording;
  - the factory wiring;
  - the run-path snapshot.
- **Leg 2 must land first.** `AgentConfig.routines_self_config_enabled`,
  `agent_change` and the errors come from it. The provider reads
  `config.routines_self_config_enabled` directly, not through `getattr`.
- **A deliberate deviation from flight DD1:** `RoutineToolProvider` lives in
  `routines/tool_provider.py`, mirroring `notes/tool_provider.py`, not in
  `routines/tools.py`.
- **The tests' pattern** is `tests/test_notes_tools.py:109`: a real
  `Agent(llm=FakeLLM(...), tools=reg, system_prompt=...)`, the scripted
  `_call`/`_asst`/`_done` helpers and the template-database `conn` fixture.
  `:123` shows how a test sets `current_turn`.
- **The frozen loop `the_one/agent/core.py` is not touched.** If anything
  appears to need it, stop and signal `[BLOCKED:frozen-loop]`.

## Inputs

**The notes tools are the pattern.**
- `the_one/notes/tools.py`:
  - `compute_taint` (`:60`) and `TRUSTED_TOOL_NAMES` (`:46`);
  - `_WriteCounter` (`:115`) and `_NotesToolBase` (`:123`), with
    `bind_agent`, `_writes`/`_check_budget`/`_count_write` and the lazy
    `_repo()` through `get_connection()`;
  - `_origin` (`:184`);
  - `SaveNoteTool` (`:217`).
- `SOURCES_CAP` and `NOTE_WRITES_PER_TURN` are in `the_one/db/_notes.py`.
- Refusals raise `ValueError`, and the loop turns that into an error result.

**`the_one/notes/tool_provider.py::NotesToolProvider`** returns `[]` when
`not config.notes_enabled`.

**`the_one/agent/factory.py`:**
- `__init__` takes `notes_provider` (`:286`, default `:311`);
- `create` registers notes tools (`:516-517`);
- the notes seed loop (`:560-563`), `capabilities_from_registry(...)`
  (`:567`), and `bind_agent` after `Agent(...)` (`:597-598`).

**`the_one/agent/_context.py::TurnContext`** (`:83-99`) has the fields
`peer`, `session_id` and `writes`. `current_turn`, `current_tool_call_id` and
`current_chat_session_id` are there too.

**`the_one/interfaces/web/app.py`:**
- `_bind_turn_user_marks(session, pre_step_len, routine)` binds
  `routine_id`/`routine_name` onto the turn's USER message at each save site;
- `_process_and_broadcast` sets
  `current_turn.set(TurnContext(peer=None, session_id=session.id))` (`:2480`
  at planning; re-locate it), with `turn_info` in scope.

**`the_one/routines/runner.py`** builds `turn_info["routine"]` (around
`:408`).

**`the_one/llm/base.py::Message`** has `routine_id`/`routine_name` (USER-only).
`the_one/db/codec.py` writes them when set (`:191-194`), reads them (`:252`),
and spreads them into UI events (`:379-382`).

**The pin.** `tests/test_notes_tools.py:169`
(`test_trusted_set_is_exactly_the_documented_names`) pins the exact set.

**The eval mirror.** `evals/checks.py:275` re-implements `compute_taint`.

## Outputs

### Leaf names and the taint module

**`the_one/agent/tool_names.py`** (new; it imports only from
`the_one.time_zones`, and `the_one/agent/__init__.py` must stay light; check
it does not eagerly import the factory) holds:
- the notes tool names, moved here and re-exported from `notes/tools.py`;
- `ROUTINE_TOOL_NAMES = ("list_my_routines", "schedule_routine",
  "change_routine", "cancel_routine")`;
- `CURRENT_TIME_TOOL_NAME`, re-exported from `the_one/time_zones.py:40`,
  where it is defined. There is one definition, and it is not moved.

**`the_one/agent/taint.py`** (new) receives `compute_taint`, `_add_source`,
`UNKNOWN_*` and `TRUSTED_TOOL_NAMES`, moved from `notes/tools.py`.
`notes/tools.py` re-exports every name it used to define (the
`canonical-import + convenience-re-export` convention).
- **`TRUSTED_TOOL_NAMES`** becomes `{*NOTES_TOOL_NAMES, *ROUTINE_TOOL_NAMES,
  "current_time", "search_tools", "continue"}`. The existing pin is updated
  by exactly those five names.
- **The `list_my_routines` sentinel.** A `list_my_routines` result whose text
  contains `FLAGGED_CONTENT_MARK` is untrusted, with source
  `routine:listed`. The constant is in `taint.py`.
- **History snapshots.** A USER message whose
  `routine_untrusted_sources` is a non-empty list adds
  `routine:{routine_name or "unnamed"}` plus those sources. An empty list or
  `None` adds nothing.
- **The current run.** `turn.routine_sources`, when non-empty, adds
  `routine:{turn.routine_name}` plus those sources.
- The scan stays pure: no I/O.

### Turn context and the run path

**`TurnContext`** gains:
- `routine_id: str | None = None`;
- `routine_name: str | None = None`;
- `routine_sources: list[str] = field(default_factory=list)`;
- `routine_writes: int = 0`.

**`Message`** gains `routine_untrusted_sources: list[str] | None = None`:
- USER-only, read by no provider;
- `codec.py` writes it whenever it is not `None` (an empty list included) and
  reads it back;
- it is **not** spread into UI events. The client does not need it, and leg
  5 shows the flag from the routine row.

**`runner.run_routine`** puts `"untrusted_sources": routine.untrusted_sources
if routine.untrusted else []` into `turn_info["routine"]`.

**`_process_and_broadcast`** builds its `TurnContext` with `routine_id`,
`routine_name` and `routine_sources` from `turn_info["routine"]` when present.

**`_bind_turn_user_marks`** also sets `msg.routine_untrusted_sources` from
`routine.get("untrusted_sources", [])`.

**Provider serializers.** No existing test pins `routine_id` against
providers. **Add one** to `tests/test_llm_provider_cross_provider_history.py`:
serialize a USER message carrying `routine_id`, `routine_name` and
`routine_untrusted_sources` (holding the `FLAGGED_CONTENT_MARK` text as a
source) through each of the Anthropic, OpenAI, Ollama and OpenRouter
converters, and assert that none of those values appears in the payload.

**`None` versus a list.** `routine_untrusted_sources` is `None` on every
non-routine message. `_bind_turn_user_marks` sets a list (`[]` when
unflagged) only for a routine turn. Binding is by attribute assignment, the
current `_bind_turn_user_marks` pattern, and `Message.user(...)` gains no
argument. Flight 1's marker tests (`tests/test_routine_turn_path.py`) stay
green.

**Pause and resume.**
- A routine run that pauses for an MCP sign-in breaks out of the event loop.
  `_bind_turn_user_marks` still runs at the post-step site before the save
  (verified at leg design), so the snapshot is saved before any resume.
- `_resume_paused_session`'s `TurnContext` deliberately carries **no**
  routine fields. The resume is operator-driven, and the history snapshot
  covers it.
- Its `routine_writes` budget is fresh, like notes' `writes` there.
- A test pins it: a flagged routine's run that pauses, then resumes, then
  writes a note, gives a flagged note.

**A cancel during the run (DD9).** This leg owns it, in
`the_one/routines/runner.py`. Every read or write of the routine row after
the turn (the post-steps, `finish`, any re-load for delivery or metadata)
tolerates a missing row: no exception and no error-level log. `finish`
on a missing row is already a no-op (`repository.py:360`), so audit the
rest.

### The tools (`the_one/routines/tools.py`)

**`_RoutineToolBase(Tool)`** is built in the pattern of `_NotesToolBase`:
- `bind_agent`;
- the lazy `_conn()` through `get_connection()`;
- a counter. The counter reads and increments `turn.routine_writes`. With no
  `TurnContext` it **refuses**: "Routine changes need a chat turn." Unlike
  notes, there is no fallback counter.

**A write:**
1. checks the budget (`AGENT_ROUTINE_WRITES_PER_TURN`; refusal "Routine
   change limit for this turn reached (5 changes).");
2. computes `compute_taint(self._agent, current_tool_call_id.get(), turn)`;
3. resolves `session_id = turn.session_id or current_chat_session_id.get()`;
4. maps `"this_chat"`/`"new_chat"`/`"own_chat"`/`{"chat_id": ...}` onto the
   REST target body. `"this_chat"` with no session refuses: "There's no chat
   to target here; use new_chat or own_chat.";
5. builds `now = time_zones.utcnow()` and a `ZoneLoader`
   (`async def zone(): return (await time_zones.load_effective_zone(conn)).tzinfo`,
   the same shape `api.py` passes). `agent_change` takes the loader. The
   `describe_*` helpers take the resolved `tzinfo`;
6. calls `agent_change`;
7. maps `RoutineFieldError` (`.message`), `RoutineScheduleError`,
   `RoutineLimitError` and `RoutineNameTaken` (`.detail`), and
   `NameRuleError` (`.message`) to `ValueError(sentence)`, raised `from None`,
   with leg 2's sentences unchanged (`routines/limits.py:22-52`);
8. counts the write on success, whether applied or pending.

**`list_my_routines()`**, read-only (it counts nothing). It returns one
block per routine:
- name and id, origin, on/off/Done;
- the schedule in words, from `routines/describe.py`;
- the next run in the operator zone, and the target in words;
- `flagged` with its sources;
- the prompt.

Then one block per pending proposal: the action, the routine name from its
payload, and a short "what would change". The first line is
`FLAGGED_CONTENT_MARK` when any listed routine or proposal is flagged. When
there is nothing to list: "You have no routines."
- `truncation_direction = "head"` explicitly, so result governance never cuts
  the first line.

**`schedule_routine(name, prompt, schedule, target="this_chat", enabled=true)`**
- Applied: "Scheduled '{name as passed}' (id {id}) for {next run in words}
  {target in words}." plus " It was flagged for your operator to check."
  when flagged.
- Pending: "Asked your operator to approve '{name as passed}'. It won't run
  until they do."

**`change_routine(routine, name?, prompt?, schedule?, target?, enabled?)`**
- At least one field is required ("Say what to change.").
- Results: "Changed routine {id}." and the pending equivalent. Add
  " This replaces your earlier pending change to that routine." when
  `replaced`.

**`cancel_routine(routine)`**: "Cancelled routine {id}." or the pending
equivalent.

**The text rule (DD7): the write tools echo only the id and the text the
agent passed, never a stored name or prompt.** `describe.py` never emits a
chat title or channel name. A chat target reads "this chat" (when it is the
current session), "chat {id}", "a new chat each run" or "its own chat".

**The tool descriptions** are platform prompt text (DD12), so keep them
short and honest. Each says:
- when to use the tool (a follow-up the person asked for, or one the agent
  needs, such as checking back on something);
- that times are wall-clock in the operator's time zone;
- the shapes;
- the limits (10 active, 48 runs a day, 5 changes a turn);
- that the operator may need to approve.

**`the_one/routines/describe.py`** (new) provides
`describe_schedule(schedule, zone)`, `describe_next(next_run_at, zone)` and
`describe_target(routine_or_payload, current_session_id)`. They use
`App.time`-equivalent server formatting: `the_one.time_zones` formatters and
12-hour clock times.

**`RoutineToolProvider.get_tools_for_agent(config, *, agent_name)`**, in
`the_one/routines/tool_provider.py`:
- it returns `[]` for the `default` agent, and when
  `not config.routines_self_config_enabled`;
- otherwise it returns the four tools, sharing nothing mutable.

### Factory (`the_one/agent/factory.py`)

**`__init__`** takes `routines_provider: RoutineToolProvider | None = None`,
with the default built like `notes_provider`'s.

**`create`:**
- registers the routine tools beside the notes tools, outside the
  `disabled_names` filter;
- seeds them into `loaded_schemas`/`loaded_tool_names` right after the
  notes seed loop;
- binds them with `bind_agent(agent)` after `Agent(...)`.

**Not changed:** `capabilities_from_registry` and the prompt layers.
`tests/test_self_configuration_write.py:117` (four surface tools) and
`tests/test_prompt_layers.py:277` stay green unedited.

### The eval mirror (`evals/checks.py`)

**Keep `_taint_expected`** (`evals/checks.py:274-289`). It takes
`(messages, upto)` and cannot be swapped for `compute_taint`, which needs an
agent, a tool-call id and a turn. Change only its import of
`TRUSTED_TOOL_NAMES`, to `the_one.agent.taint`.
- It gains the five trusted names automatically.
- That changes the expected taint for any scenario that calls `current_time`
  before a save. That is DD7's recorded behaviour change. Leg 4 (evals)
  re-measures and compares it against `m30-platform`; this leg only notes it.
- `tests/test_evals_*` stay green.

### Security model and docs

**`SECURITY-MODEL.md` "Routines (Mission 33)"** gains an "Agent
self-scheduling (Flight 2)" subsection covering:
- the threat: persistence of injected instructions;
- the switch and its call-time check;
- approval, which defaults on;
- the proposals record, never purged;
- the flag: what counts as untrusted, the snapshot, the sentinel, and the
  connector-peer rule including the operator's own DM;
- the caps;
- the residual risks:
  - an approved-but-planted routine runs with full tool access;
  - a flagged routine's run is only flagged, never blocked;
  - turning the item on reaches an open web chat only after a rebuild.

**`the_one/agents.md` "Routines (M33)"** gains:
- the tools;
- the provider hook;
- the taint module and its rules;
- `TurnContext` and `Message` fields;
- the describer.

**CLAUDE.md**'s Routines paragraph gains one sentence on the agent tools and
the "Check this" flag.

## Acceptance Criteria

- [ ] **AC1. Gating.** With `routines_self_config_enabled` false, or for the
      `default` agent, `AgentFactory.create` registers and seeds no routine
      tool. With it true, the four are registered and present in the first
      turn's visible schemas. Test at the unit tier with the factory and a
      template database.
- [ ] **AC2. The switch at call time.** A tool built while Routines was on
      refuses every write after the switch is turned off, with leg 2's
      sentence, and writes nothing. That is a cached `Agent`, the same object,
      tested.
- [ ] **AC3. Tools end to end** (`tests/test_routine_tools.py`, the real
      `Agent` and `FakeLLM` scripted calls, a template database), with
      approval off:
  - schedule with `in` and `this_chat` gives a routine targeting the turn's
    session, `created_by` `agent`;
  - `new_chat` and `own_chat`;
  - `chat_id` of another agent's chat is refused;
  - change by a name in a different case;
  - cancel;
  - list shows all of it, and a pending proposal;
  - the per-turn limit refuses the sixth write;
  - with no `TurnContext`, a write refuses;
  - every refusal is a tool error with one sentence.
- [ ] **AC4. Approval through the tools.** With approval on, schedule gives
      the pending sentence and no routine. A second change to the same
      routine gives the "replaces" sentence.
- [ ] **AC5. The taint proof** (`tests/test_routine_tools_taint.py`): every
      case in flight DD7's "deterministic proof" list passes, including the
      next-turn and after-clear and after-delete snapshot cases, the
      unflagged-routine and legacy-marker cases, and the sentinel across a
      later turn.
- [ ] **AC6. The sentinel holds up.**
  - A 60-item listing (50 routines and 10 pending) whose last item is
    flagged keeps `FLAGGED_CONTENT_MARK` as its first line after result
    governance.
  - The test sets a small `max_context_tokens` on the `FakeLLM` (or the
    governor override), so the listing really is truncated, and asserts that
    it was. `Tool.truncation_direction` already defaults to `"head"`
    (`tools/base.py:57`); the explicit setting documents it.
  - `change_routine` and `cancel_routine` results contain no stored name or
    prompt text: test with a planted name.
- [ ] **AC7. The run path.**
  - A flagged routine's run binds `routine_untrusted_sources` onto its USER
    message, and an unflagged one binds `[]`.
  - The field round-trips through the codec, is absent from UI events, and
    no provider serializer sends it.
  - A routine run's `TurnContext` carries the routine fields.
  - Cancelling the routine that is running it ends the run with no error
    log and no exception (DD9; the runner audit above).
  - A flagged routine's run that pauses, resumes and then writes a note gives
    a flagged note.
- [ ] **AC8. Notes unchanged.** Every `tests/test_notes_*` file passes,
      edited only at `test_notes_tools.py`'s trusted-set pin, which gains
      exactly five names. `tests/test_self_configuration_write.py` and
      `tests/test_prompt_layers.py` pass unedited.
- [ ] **AC9. Evals offline.** `tests/test_evals_*` pass. `_taint_expected`
      keeps its shape and imports the trusted set from `the_one.agent.taint`.
- [ ] **AC10. Gates.** `THE_ONE_TEST_NETNS=1 make test-unit` is green (15
      skipped). `ruff` is clean. The `chats` and `chats-transcript` lanes
      pass, because the run path and codec changed.
- [ ] **AC11. Docs.** `SECURITY-MODEL.md`, `agents.md` and CLAUDE.md are
      updated as stated.

## Verification Steps

- The unit files named in the criteria, plus `tests/test_notes_*`,
  `tests/test_evals_*`, `tests/test_routines_runner.py`,
  `tests/test_routine_turn_path.py` and `tests/test_routine_message_marker.py`.
- The lanes, through `scripts/run-tests.sh --lane chats` and
  `--lane chats-transcript`, with `THE_ONE_TEST_NETNS=1`.

## Implementation Guidance

1. Move the names and the taint code first, with the re-exports. Run every
   notes test; only the trusted-set pin may change.
2. Add the `TurnContext` and `Message` fields, the codec, the runner and the
   `app.py` binding, with the AC7 tests.
3. Add `describe.py`, then the tools and the provider, with the AC3, AC4 and
   AC6 tests.
4. Wire the factory, with the AC1 and AC2 tests.
5. Write the taint proof (AC5), then the eval mirror (AC9).
6. Run the gates, then write the docs and the flight log.

## Edge Cases

- **A routine run's own `schedule_routine` call.** A routine whose run
  schedules another routine is capped by leg 2's active and per-day caps and
  this leg's per-turn counter. Flagged runs flag the child.
- **`"this_chat"` from inside a routine run** targets the run's chat (the
  run's `session_id`).
- **`list_my_routines` with a stored prompt containing the sentinel text.**
  It flags, which is correct: fail closed.
- **Schedules given as JSON strings by weak models.** Accept a string that
  parses as a JSON object, for `schedule` and `target` only. Otherwise refuse
  with the shape sentence.
  A string over 2000 characters is refused before it is parsed.
- **The echoed name** is the post-trim string the agent passed, cut to 64
  characters with an ellipsis. `"routine {id}"` in a change or cancel result
  is the resolved `AgentChangeResult.routine_id`. A pending create has none,
  so its sentence uses only the passed name.
- **`list_my_routines`'s description says** that listing a flagged routine
  marks what follows as needing the operator's check, so the model is not
  surprised.

## Files Affected

- `the_one/agent/tool_names.py` (new) and `the_one/agent/taint.py` (new)
- `the_one/notes/tools.py`
- `the_one/agent/_context.py`
- `the_one/llm/base.py` and `the_one/db/codec.py`
- `the_one/routines/runner.py` and `the_one/interfaces/web/app.py`
  (`_bind_turn_user_marks`, the `TurnContext` construction)
- `the_one/routines/tools.py`, `tool_provider.py` and `describe.py` (all new)
- `the_one/agent/factory.py`
- `evals/checks.py`
- `SECURITY-MODEL.md`, `the_one/agents.md` and `CLAUDE.md`
- **Tests:**
  - `tests/test_routine_tools.py` (new)
  - `tests/test_routine_tools_taint.py` (new)
  - `tests/test_notes_tools.py` (the pin only)
  - the codec and turn-path tests extended

## Citation Audit

Checked at leg design against the tree at `5b607af3`, plus leg 1:
- `notes/tools.py:46/60/115/123/184/217`;
- `factory.py:286/311/516-517/560-567/597-598`;
- `_context.py:83-99`;
- `codec.py:191-194/252/379-382`;
- `runner.py` `turn_info["routine"]` (around `:408`);
- `app.py` `_bind_turn_user_marks` and `_process_and_broadcast`'s
  `current_turn.set`.

`app.py` line numbers move with leg 2's edits, so locate them by symbol.
