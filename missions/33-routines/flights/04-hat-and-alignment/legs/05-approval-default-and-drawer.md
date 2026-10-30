# Leg: approval-default-and-drawer

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Two small backend-and-client changes from the HAT, split out of the
Self-configuration rebuild at design review: (1) Routines approval defaults to
**off** for newly created agents, like Agent prompt (C8 reversed); (2) the
chat drawer's Routines group refreshes live when the agent changes a routine
(F-E2-1).

## Context

- **Operator decisions** (flight log, E1/E2): "we should switch the default
  to match the other setting"; the agent's new routine "didnt show up in the
  drawer until I refreshed".
- **Why the default needs an INSERT change (design review):**
  `SQLiteAgentStore.save`'s INSERT (`the_one/db/repositories.py` ~:256-300)
  writes neither `routines_self_config_enabled` nor
  `routines_require_approval`, so a new row takes the v46 DDL default
  (`DEFAULT 1`, `db/schema.py` ~:3191); `create_agent` pops the field
  (`interfaces/web/api.py` ~:1052) and `_row_to_config` reads the column back
  (~:519). Changing only `AgentConfig` would change nothing.
- Mission 33 is unreleased (`docs/releases/` ends at v0.12.3), so no shipped
  data depends on the old default.

### Design decisions

**L5-DD1. The default.**
- `AgentConfig.routines_require_approval` defaults to `False`
  (`agent/config.py` ~:156; reword the comment ~:152-155).
- The INSERT in `SQLiteAgentStore.save` gains `routines_require_approval`
  (`int(config.routines_require_approval)`), and it is **left out of `ON
  CONFLICT DO UPDATE`**, so a save still never changes an existing row's
  value (the doc comments become "never changes an existing row").
  `update_agent` keeps overwriting the field from the stored row (~:1140), so
  a PUT cannot change it.
- **No migration:** the DDL default stays `1` (a rebuild of `agents` is not
  worth it for a default the INSERT now overrides); existing rows keep their
  stored value (dev and HAT databases keep approval on, the safe side). No
  `CURRENT_VERSION` change.
- Docs: `the_one/agents.md` (Routines and Self-configuration), CLAUDE.md's
  Routines paragraph ("approval on by default" → off), `SECURITY-MODEL.md`
  "Routines" (the new default for newly created agents, existing rows keep
  their value, and the operator's reason: consistency with Agent prompt, the
  switch one click away). Check `evals/README.md` wording (the harness
  already forces approval off).

**L5-DD2. The drawer refresh.** In `static/js/areas/chat/turn-frames.js`,
beside `NOTE_TOOLS` (~:18), a `ROUTINE_TOOLS` map (`schedule_routine`,
`change_routine`, `cancel_routine`); on a live tool result for one of them
that is not an error (`is_error` false), call `agentDrawer.refreshRoutines()`
(already exported, `agent-drawer.js` ~:768), as note tools call
`refreshNotes()` (~:126). A held-for-approval result refreshes harmlessly. A
drawer refresh after an approval made in another tab or window is out of
scope (the drawer refreshes on `session_joined`).

## Acceptance Criteria

- [ ] AC1. A newly created agent reads Routines approval **off**, through the
      store and through `POST /api/agents` (unit tests); a save of an existing
      agent never changes its stored value (unit test).
- [ ] AC2. Tests that pinned the old default are updated, not deleted:
      `tests/test_routines_self_config_api.py` (~:85, :93, :110, :111) and
      `tests/browser/test_flow_agent_routines_self_config.py` (~:139); the v46
      migration test (`test_db_migration.py` ~:5902, DDL default "1") stays.
- [ ] AC3. A live routine tool write refreshes the drawer's Routines group
      with no reload; an error result does not refresh (browser test with a
      scripted mock tool call, approval off).
- [ ] AC4. Docs state the new default (L5-DD1).
- [ ] AC5. `THE_ONE_TEST_NETNS=1 make test-unit` (15 skipped); the static
      guards; the lanes owning the touched browser tests (`agent-routines`;
      the drawer test's lane, e.g. `chats`) pass.

## Out of the Developer's scope

`tests/behavior/agent-schedules-follow-up.md` step 1 (expects approval on for
a fresh agent): the Flight Director re-authors it with the other behavior
spec changes.

## Files Affected

`the_one/agent/config.py`, `the_one/db/repositories.py`;
`static/js/areas/chat/turn-frames.js`; `tests/test_routines_self_config_api.py`,
a repository/API unit test, `tests/browser/test_flow_agent_routines_self_config.py`,
a drawer browser test; `the_one/agents.md`, CLAUDE.md, SECURITY-MODEL.md,
possibly `evals/README.md`.

## Citation Audit

Design review at the working tree: `repositories.py` INSERT ~:256-300, setter
~:355, `_row_to_config` ~:519; `schema.py` ~:3191; `api.py` ~:1052, ~:1140;
`config.py` ~:152-156; `turn-frames.js` ~:18, ~:102, ~:126; `agent-drawer.js`
`refreshRoutines` export ~:768.
