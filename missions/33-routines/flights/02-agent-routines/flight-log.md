# Flight Log: Agents Schedule Their Own Routines

**Flight**: [Agents Schedule Their Own Routines](flight.md)

## Summary

*(Written at landing.)*

---

## Leg Progress

### Leg 1: routine-write-service

- **Built**: `the_one/routines/service.py` (validators, create/update/delete, `routine_view`, `limits_view`, `poke_scheduler`); `RoutineFieldError` in `limits.py`; `api.py` write routes now thin adapters (`_routine_schedule`/`_routine_target`/`_routine_prompt` removed, `_poke_scheduler` kept as a delegate); `tests/test_routines_service.py` (19 tests); `agents.md` paragraph.
- **Tests**: AC1 `tests/test_routines_api.py` 63 passed before, 63 after, `git diff --stat main` empty. Scheduler, runner, name-rule, repository files pass unedited (159 together).
- **Gate results**: `THE_ONE_TEST_NETNS=1 make test-unit`: 8111 passed, 15 skipped. ruff check and format --check clean.
- **Deviations**: none.
- **Anomalies**: none.

### Leg 2: agent-routine-store

- **Built**:
  - Schema v46 (`schema.py`, guarded ALTERs): the two operator-owned switches on `agents`, `untrusted`/`untrusted_sources` on `agent_routines`, and `agent_routine_proposals` with its index.
  - `AgentConfig` switches, `_row_to_config`, `SQLiteAgentStore.set_routines_self_config`. `save` writes neither switch. `create_agent` pops them and `update_agent` forces the stored values.
  - `Routine` flag fields. `AgentRoutineRepository.create/update/delete` take `precheck`, `agent_caps`, `flag` and `proposal` in the fixed in-transaction order, and `get_by_name` was added. Delete supersedes the routine's other pending proposals.
  - New `routines/proposals.py`: `RoutineProposal`, `RoutineProposalRepository`, `ProposalOp`, `ProposalStateError`/`ProposalStaleError`/`ProposalGoneError`.
  - `limits.py`: the DD8 constants, `runs_per_day`, raise-only `check_agent_caps`.
  - `service.py`: pass-throughs on create/update/delete, `agent_change`, `approve_proposal`, `dismiss_proposal`, the one-off minimum for agent writes, `untrusted` fields in `routine_view`.
  - REST: the Routines item GET/PUT, proposals list, pending-count, approve, dismiss. Operator `PUT` with `prompt` passes `flag="clear"`.
  - Squawk 0277: `_check_agent_provider` on create and (changed id only) update. The squawk has its Corrective Action and Verification and status `in-progress`.
  - Docs: `agents.md` "Routines (M33)" and the CLAUDE.md Routines paragraph.
- **Tests**:
  - New files: `test_routines_proposals.py` (14), `test_routines_self_config_api.py` (17), `test_api_agent_provider_check.py` (5).
  - Extended: `test_routines_service.py` (agent change, approve, dismiss), `test_retention.py` (proposals survive the sweep), `TestSchemaV46` in `test_db_migration.py`.
  - Edited pins: the `== 45` version pins (7 lines) and `_ROUTINE_COLS` in `test_db_migration.py`; the v44 re-migration test drops `agent_routine_proposals` first; `test_routines_api.py:86` key set plus `untrusted`, `untrusted_sources` (the `:546` pin is the runs shape and did not change); three new routes classified in `test_api_name_rule.py`. `test_self_configuration_api.py` unedited and passing.
- **Gate results**:
  - `THE_ONE_TEST_NETNS=1 make test-unit`: 8173 passed, 15 skipped (376 s).
  - `ruff check` and `ruff format --check` clean.
  - Lane `agent-tabs`: 161 passed (351 s). Lane `agents`: 170 passed (415 s). They ran one after the other, with nothing else running.
- **Deviations**:
  - A duplicate pending create is refused with `RoutineLimitError` (a 422), as the leg gave only the message.
  - `ProposalOp.run` takes the routine id from the mutator (new id, updated id, `None` after a delete) and ignores any id in the row. A delete's applied row would otherwise break the foreign key.
  - Stale compare for a delete covers every base key except `finished_at`.
- **Anomalies**: none.

### Leg 3: agent-routine-tools

- **Built**:
  - New leaf modules `the_one/agent/tool_names.py` and `the_one/agent/taint.py` (`compute_taint`, `_add_source`, `UNKNOWN_*`, `TRUSTED_TOOL_NAMES`, `FLAGGED_CONTENT_MARK`, `LISTED_SOURCE`). `notes/tools.py` re-exports every name it used to define. `TRUSTED_TOOL_NAMES` gained the four routine tools and `current_time`. The `list_my_routines` sentinel, the history snapshot rule and the current-run rule are in `compute_taint`, which stays pure.
  - `TurnContext` fields `routine_id`, `routine_name`, `routine_sources`, `routine_writes`. `Message.routine_untrusted_sources` (USER-only; codec writes it whenever not `None`, reads it back, does not spread it into UI events). `runner.run_routine` adds `untrusted_sources` to `turn_info["routine"]`; `app.py` builds the `TurnContext` from it and `_bind_turn_user_marks` binds the snapshot (`_routine_turn_sources` helper). `_resume_paused_session` is untouched.
  - `routines/describe.py`, `routines/tools.py` (four tools), `routines/tool_provider.py`, and the `AgentFactory` hook (`routines_provider`, register, seed, `bind_agent`).
  - `evals/checks.py` imports `TRUSTED_TOOL_NAMES` from `the_one.agent.taint` (the only change there).
  - Docs: `SECURITY-MODEL.md` "Agent self-scheduling (Flight 2)", `agents.md` "Routines (M33)" (and the notes taint pointer), CLAUDE.md Routines paragraph.
- **Tests**:
  - New: `tests/test_routine_tools.py` (18: AC1 gating through the real factory, AC2 switch at call time on the same agent, AC3, AC4, AC6), `tests/test_routine_tools_taint.py` (14: every DD7 deterministic-proof case, incl. next-turn, cleared and deleted routine, unflagged and legacy marker, sentinel across later turns, pause then resume then note, codec round trip), `tests/_routine_tools_env.py`.
  - Extended: `test_routine_turn_path.py` (+4: snapshot, `TurnContext` fields, `[]` for unflagged, codec round trip and no UI event key), `test_routines_runner.py` (+2: end-to-end snapshot of a flagged and an unflagged run; cancelling the running routine leaves no error log), `test_llm_provider_cross_provider_history.py` (+1: no provider serializer sends the marker or the snapshot).
  - Edited pins: `tests/test_notes_tools.py` trusted set (exactly the five names); `tests/test_evals_freeze.py` `checks.py` digest (the one import line changed; the leg directs the import edit and the test's own hint says to update the digest in the same commit).
  - `tests/test_self_configuration_write.py`, `tests/test_prompt_layers.py` and every other `tests/test_notes_*` file unedited and passing.
- **Gate results**:
  - `THE_ONE_TEST_NETNS=1 make test-unit`: 8212 passed, 15 skipped (374 s). `ruff check` and `ruff format --check` clean.
  - Lane `chats`: 166 passed (311 s). Lane `chats-transcript`: 97 passed (232 s). One after the other, nothing else running.
- **Deviations**:
  - `tests/test_evals_freeze.py`'s `checks.py` digest was updated (see above); the leg did not name it but it is the direct consequence of the leg's `evals/checks.py` import edit.
  - A refusal is not counted against the per-turn budget (only a success, applied or pending, counts), per the leg's step 8.
  - Applied `change_routine` results also carry the "flagged" sentence when flagged (the leg specified it only for `schedule_routine`).
- **Anomalies**:
  - A tool refusal reaches the model as `[error] Tool execution failed: {sentence}` (the loop's fixed prefix); tests assert the sentence after the prefix.
  - DD9 runner audit: no change needed. `_post_steps` and `_finish_row` re-read no routine row and tolerate a cascaded run; the new test pins no error-level log when the running routine is deleted.
  - Leg 4 note: `current_time` joining the trusted set changes the expected taint for any eval scenario that calls it before a save; re-measure against `m30-platform`.
- **Final tool descriptions (platform prompt text, DD12; for leg 4)**:
  - `list_my_routines`: List your routines (scheduled follow-ups) and any changes waiting for your operator's approval. Listing a flagged routine marks what follows as needing your operator's check.
  - `schedule_routine`: Schedule a prompt to run later, for a follow-up the person asked for or one you need (such as checking back on something). Times are wall-clock in the operator's time zone. Schedule: {"kind":"once","in":{"amount":N,"unit":"minutes|hours|days"}}, {"kind":"once","on":{"date":"YYYY-MM-DD","time":"HH:MM"}}, {"kind":"daily"|"weekdays","time":"HH:MM"}, {"kind":"weekly","days":[0-6, 0 is Monday],"time":"HH:MM"} or {"kind":"interval","hours":N}. At most 10 active routines, 48 runs a day and 5 changes a turn. Your operator may need to approve.
  - `change_routine`: Change one of your routines, by name or id. Pass only what changes. Times are wall-clock in the operator's time zone. Schedule: {"kind":"once","in":{"amount":N,"unit":"minutes|hours|days"}}, {"kind":"once","on":{"date":"YYYY-MM-DD","time":"HH:MM"}}, {"kind":"daily"|"weekdays","time":"HH:MM"}, {"kind":"weekly","days":[0-6, 0 is Monday],"time":"HH:MM"} or {"kind":"interval","hours":N}. At most 10 active routines, 48 runs a day and 5 changes a turn. Your operator may need to approve.
  - `cancel_routine`: Cancel (delete) one of your routines, by name or id. Your operator may need to approve.

---

## Decisions

### Planned without a planning conversation (operator)
**Context**: The operator asked for this flight to be planned and flown
directly after the Flight 1 debrief and merge (2026-10-29).
**Decision**: Every decision the mission left open is settled in the flight
spec as an *(autonomous judgement call)*, marked *(J)*. The mission's Flight 3
HAT reviews them with the operator.
**Impact**: DD1, DD2 and DD5-DD13 carry *(J)* marks.

### Design review cycle 1 (planning)
**Context**: The Architect (Opus) approved with changes: four high issues,
eight medium and six low, plus suggestions.
**Decision**: All were applied.

**High:**
- **DD3:** the service takes `conn` from its caller, because
  `test_routines_api.py` patches `api.get_connection`. Without this the
  "unedited" guard trips. `NameRuleError` and the scheduler poke move in too.
- **DD4:** `save` leaves the two switches out of its `ON CONFLICT` update, so
  a General Save cannot turn Routines off.
- **DD7:** routine taint now spans the whole conversation. A history scan of
  `routine_id`s, with flags looked up and `routine:unknown` for a gone
  routine, covers later turns and a resumed pause.
- **DD7:** the `list_my_routines` marker moved from a per-turn set to a fixed
  sentinel in the stored result.

**Medium:**
- a separate `routine_writes` counter;
- the proposal and caps writes composed inside the repository's one
  transaction;
- `payload` is the validated request with an absolute `at`, `base` is the raw
  fields, and approval runs the full service write;
- squawk 0277 is limited to the provider, because dangling `kb_ids` are
  designed (M24 DD-14);
- `this_chat` resolves `turn.session_id` first, and the eval harness creates
  a chat row;
- a Routines-on token measure;
- the pinned trusted-set test is an intended edit, with a leaf names module;
- leg 3 split into tools (3) and evals (4), with Ollama and the token
  re-checked at leg time.

**Low:**
- refuse only changes that raise a capped measure;
- DD9 re-pointed: a cancel cascades the run's history, and the drawer fact is
  pinned;
- `ValueError`, not `ToolError`;
- name matching is case-insensitive;
- the target adapter;
- no `routines=` capability flag;
- the approve and dismiss routes are classified.

**Suggestions taken:**
- the revisions route's stale keys, and an idempotent dismiss;
- the `name_repair` note;
- the newest 500 resolved proposals kept per agent;
- a pending create never reaches `list_due`;
- a Python describer.

**Not taken:** `describe_my_capabilities` mentioning the routine tools. The
seeded tool descriptions already tell the model.

**HAT notes recorded**: an agent write to an operator routine flags the whole
routine; an allowlisted-peer exemption to connector-chat flagging.

**Impact**: This was a substantive change, so a second review cycle runs.

### Design review cycle 2 (planning)
**Context**: The Architect (Opus) approved with changes: two new high issues,
five medium and six low, plus suggestions. All of its spot-checked citations
held.
**Decision**: All were applied.

**High:**
- **DD5:** every routine tool call re-reads the switch and the approval flag
  in its transaction and refuses when the item is off. A cached web `Agent`
  outlives a switch-off, which is the notes `NotesDisabledError` pattern.
  The HAT note: turning Routines on reaches an open web chat only after a
  rebuild.
- **DD7:** the history taint snapshots the flag on the USER message at bind
  time (`Message.routine_untrusted_sources`), instead of reading the
  routine's current flag. That closes the fail-open after an operator clear
  and the permanent `routine:unknown` noise after a delete. The scan is
  pure, with no DB access, so the notes tools need nothing new.

**Medium:**
- the stale 0277 checkpoint wording;
- a new `GET`/`PUT .../self-configuration/routines` pair, with the existing
  GET and POST byte-identical (a pinned shape);
- every count and frequency cap moved into leg 2;
- the proposal operations (`insert_applied`, `insert_pending`, `resolve`),
  the flag mode `merge`/`clear` and the stale check, all inside the mutator
  transaction;
- the eval `compute_taint` mirror named.

**Low:**
- the sentinel fires on any flagged routine or proposal, `head`
  truncation is pinned, and the write tools never echo stored text;
- the describer omits chat titles;
- the lane globs stay disjoint;
- the payload stores the adapted target;
- INSERT uses the literal defaults;
- a CLI write refuses;
- the doc ownership is assigned per leg.

**Suggestions taken:**
- conservative runs-per-day weights;
- the tool says when it replaced an earlier pending change;
- an operator delete supersedes that routine's pending proposals;
- refused calls are not recorded *(J)*.

**Impact**: The maximum two cycles are done. The fixes are precise, so there
is no third review. The flight is `ready`.

---

## Deviations

---

## Anomalies

---

## Session Notes

### Flight Director Notes

- **2026-10-29, start.**
  - Loaded `leg-execution.md`.
  - The flight was `ready` and is now `in-flight`, on branch
    `flight/02-agent-routines` (cut from `main` at `6ed89395`).
  - **Batch mode:**
    - Batch A is legs 1-3, at the unit tier: a Sonnet Reviewer (the diff
      touches taint, approval and a security-model section), then a
      checkpoint commit.
    - Leg 4, the evals, is its own checkpoint.
    - Batch B is leg 5, the UI: a Reviewer plus an Accessibility Reviewer,
      then a commit.
    - Leg 6 runs the behavior test.
  - **The Flight Director makes every commit itself, never a crew agent**
    (Flight 1 debrief: a delegated commit lost the session's attribution).
- **Leg 1 `routine-write-service`: low risk, no design review.** It is a pure
  extraction, mechanically guarded: `tests/test_routines_api.py` must pass
  unedited, otherwise `[BLOCKED:routine-service-not-contained]` and a divert.
  It is the Flight 1 leg 2 pattern, and the flight-end Reviewer covers it.
  `ready`.
- **Leg 1 landed (FD read of the `[LAND:leg]` report).**
  - `routines/service.py` is in place.
  - `tests/test_routines_api.py` passed 63 tests before and 63 after, with
    the file unedited.
  - Unit tests: 8111 passed, 15 skipped.
  - No deviations.
- **Leg 2 `agent-routine-store`: high risk** (schema v46, an approval path, a
  security surface, and an agent write-boundary change for squawk 0277).
- **Leg 2 design review** (Developer, Sonnet): approve with changes. All
  applied.
  - **High:**
    - every check that must not race lives in the repository mutator, in a
      fixed order inside its transaction: re-read, a `precheck` callable
      (the approval stale and gone checks), caps over the rows read in the
      transaction, the write, then the proposal operation;
    - approval validation is split: the zone and the target are resolved
      before the lock, and the name, caps and stale checks inside it, on a
      routine re-read at approval;
    - the migration pins go beyond `== 45`: `TestSchemaV45`'s
      `_ROUTINE_COLS`, and the v44 re-migration test's drop order. Every
      `ALTER` is guarded by a column-exists check (the established pattern).
  - **Medium:**
    - the provider check is conditional on update (only a changed id is
      checked, so an agent whose provider was deleted stays editable), with
      the `KeyError` lookup and the corrected `_provider_repo` citation;
    - `SOURCES_CAP` comes from `the_one.db._notes`;
    - pending-create name matching uses `json_extract ... COLLATE NOCASE`,
      and a duplicate pending create is refused;
    - create pops the switch keys.
  - **Low:**
    - the second key-set pin (`:546`);
    - the REST `PUT` is the only flag clear;
    - `zone` is a `ZoneLoader`;
    - failure injection through a failing proposal operation.

  The fixes were precise, so there is no second cycle. Leg 2 is `ready`.
- **Leg 3 `agent-routine-tools`: high risk** (shared taint, the run path and
  codec, the factory). Its design review runs in parallel with the leg 2
  implementation, against leg 2's artifact as the contract. The reviewer runs
  no suites.
- **Leg 3 design review** (Developer, Sonnet): approve with changes. All
  applied.
  - **High:**
    - **The pause and resume path.** The FD verified that a paused routine run
      still binds its USER marks at the post-step site before the save
      (`app.py`, the `break` then `_bind_turn_user_marks` then save). So the
      snapshot survives a resume. The resume `TurnContext` deliberately
      carries no routine fields, and a test pins it.
    - **The DD9 cancel mid-run** is owned by this leg, as a runner audit for a
      missing routine row.
  - **Medium:**
    - the `ZoneLoader` passed to `agent_change`;
    - the error attributes (`.detail`/`.message`);
    - the dependency on leg 2;
    - `tool_provider.py` as a deliberate deviation from DD1's file name;
    - the eval mirror keeps `_taint_expected` and changes only its import;
    - a new provider-serializer test, since none existed;
    - `None` versus `[]` for the snapshot.
  - **Low:**
    - `tool_names.py` re-exports `CURRENT_TIME_TOOL_NAME` from
      `time_zones`;
    - the governance test sets a small `max_context_tokens`;
    - the echoed name is capped;
    - a limit on JSON-string arguments;
    - `list_my_routines`'s description warns about the sentinel.

  The fixes were precise, so there is no second cycle. Leg 3 is `ready`, and
  it starts after leg 2 lands.
- **Leg 4 `routine-evals`: low risk, no design review.** It is additive eval
  tooling within the Mission 30 patterns. Every outcome that would need
  judgement (a hard failure, or a new safety cell failing on Haiku) is a
  `[BLOCKED:eval-regression]` stop, never a tweak. It is designed now and
  marked `ready` after leg 3 lands, because leg 3 edits `evals/checks.py`.
- **Leg 5 `self-config-routines-item`: high risk** (a large UI surface and
  the approval UI).
- **Leg 5 design review** (Developer, Sonnet): approve with changes. All
  applied in an authoritative amendments section.
  - **High:**
    - a new tab `activate` hook, wired from `setActiveTab`, which also closes
      the revisions queue's staleness gap;
    - the `cb.*` network callbacks through `agent-data.js`,
      `agent-editor.js` and the controller;
    - the full lane machinery, including the `agents_files()` subtraction.
  - **Medium:**
    - the drawer tests run in `chats` and the `noteFlag` contract in
      `contracts-controls`;
    - seeding by direct sqlite rows (the `seed_note` pattern), plus one
      end-to-end mock tool-call test, with no new seam;
    - the flag-aware form (`ctx.flagged`);
    - the `base` to view normalisation for the proposal display;
    - the relabel pins listed exactly;
    - the `noteFlag` inventory row and contract case.
  - **Low:** the module split decided up front, the capture surface, and the
    registry rows.

  The fixes were precise, so there is no second cycle. Leg 5 is `ready`.
- **Leg 2 landed (FD read of the `[LAND:leg]` report).**
  - It delivers v46, the switches, the proposals, the caps, the
    `agent_change`/approve/dismiss service, the REST routes and squawk 0277.
  - **Gates:** unit tests 8173 passed, 15 skipped; `agent-tabs` 161 passed
    and `agents` 170 passed, run one after the other.
  - **Deviations accepted:**
    - A duplicate pending create is a 422 (`RoutineLimitError`).
    - `ProposalOp` takes the routine id from the mutator, because an applied
      delete row pointing at the deleted routine broke the foreign key.
    - **Approving a delete runs a stale check** (every base key except
      `finished_at`). DD6 said a delete approve has no drift check.
      - Accepted *(J)*: it fails closed, `override=true` still applies, and
        the operator sees that the routine changed before removing it.
      - Leg 5's stale banner must therefore also handle a cancel proposal.
        The leg 5 Developer is told.
  - **Spawned:** a leg 3 Developer (Sonnet).
- **Leg 3 landed (FD read of the `[LAND:leg]` report).**
  - It delivers the four tools, the shared taint module, the snapshot and the
    factory hook. `core.py` is untouched.
  - **Gates:** unit tests 8212 passed, 15 skipped; `chats` 166 passed and
    `chats-transcript` 97 passed.
  - Batch A review fix: list_my_routines checks the switch at call time.
  - **Deviations accepted:**
    - the `test_evals_freeze.py` digest was updated for the `checks.py`
      import change;
    - only a successful write counts against the per-turn limit;
    - an applied `change_routine` result also says when the change was
      flagged.
  - The DD9 runner audit needed no code change.
- **Batch A review.** The Reviewer runs on Sonnet: the diff touches taint, the
  approval path, an agent write boundary and the security model. It reviews
  legs 1-3 against `5b607af3`.
- **Batch A review: `[HANDOFF:confirmed]`.** The Reviewer's own gate gave
  8212 passed and 15 skipped, ruff was clean, `core.py` is untouched, and
  `test_routines_api.py` carries only the key-set pin change. All the
  security checks passed.
  - **Non-blocking notes:**
    1. **`list_my_routines` did not check the switch at call time.** The FD
       makes this a fix, because of the mission criterion "With the item off,
       the agent has no routine tools". A fix Developer is spawned.
    2. **The switch-off race** can leave at most one stray pending proposal,
       which the operator can dismiss. Accepted.
    3. **An approval's untouched-key race** is the same shape as the
       operator PUT path. Accepted.
    4. **A near-term one-off pending too long cannot be approved.** It fails
       safe. Leg 5's copy notes it.
    5. **Saving clears the flag even with the prompt unchanged.** By design;
       leg 5 adds a form hint.
    6. **Refusals do not count toward the per-turn budget.** Bounded by the
       step limit. Accepted.
