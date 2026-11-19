# Leg: proposal-store-and-tool

**Status**: completed
**Flight**: [Proposals and approval](../flight.md)

## Objective
Give GleepGlorp a `propose_change` tool that records a proposal and changes
nothing else.
- Proposals cover creating or changing an agent, one of its rules, or one of
  its routines.
- They are stored in a new `gleepglorp_proposals` table (schema v54).
- They are checked against one declared change shape, which also serves a new
  `fields` kind of `read_app_config`.

## Context
- **Flight design:**
  - DD1 (the change shape);
  - DD2 (what can be proposed, names to ids);
  - DD4 (the store, status transitions, deleting);
  - DD5 (the tool, one open proposal per chat);
  - DD12 (where code lives).
- **Out of scope here:**
  - **Leg 3** adds the secret guard and the finer `read_app_config` taint. In
    this leg the tool computes taint with today's `compute_taint`, which is
    fail-closed: after any `read_app_config` call a proposal is flagged.
    Nothing reaches the operator before Leg 3 lands; it is the same batch.
  - **Leg 4** applies proposals.
  - **Leg 6** draws the card.
- **The frame.** This leg writes the row and returns the model text. The
  `proposal_changed` frame is pushed from one helper, `proposals/events.py::
  push_proposal_changed(session_id, row)`, written here and called on create.
  - Leg 4 reuses it for status changes.
  - Leg 6's client handles it. Until then an unknown frame type is ignored by
    the client (`socket.js` routes unknown types to `turn-frames.js`, which
    drops what it does not know). Check this: see Edge Cases.
- **The base snapshot.** Leg 1's `change_agent(…, base=…)` and
  `change_rule(…, base=…)` take the `base` this leg records. The base values
  must use the same normalisation Leg 1's precheck compares:
  - `mcp_source_ids` without the surface id;
  - `mcp_overrides` is never in a proposal.

## Inputs
- **Schema:** `the_one/db/schema.py` is at `CURRENT_VERSION = 53`. The v53 step
  (~L3334) is the newest and the pattern to follow.
- **Tool registration:** `the_one/agent/factory.py` ~L567-576 registers
  GleepGlorp's `ReadAppConfigTool` and `GetAppGuideTool` under `if gleepglorp:`.
  `bind_agent` is called for the notes and routine tools at ~L806-809.
- **The taint pattern:** `the_one/routines/tools.py::_RoutineToolBase`
  (`bind_agent`, `_session_id(turn)`, `compute_taint(self._agent,
  current_tool_call_id.get(), turn)`).
- **Context:** `the_one/agent/_context.py::TurnContext.session_id`,
  `current_turn`, `current_tool_call_id`, `current_chat_session_id`.
- **Routine schedules:** `the_one/routines/service.py` provides
  `validate_schedule`, `_require_future`, `_min_ahead(False)` (operator caps,
  DD2), `values_schedule_text`, and `create_routine(…, schedule_pair=…)`, which
  stores an already-normalised pair verbatim.
- **Views:** `the_one/gleepglorp/view_core.py::KINDS` (L23), `views.read`
  (L85), `views.py` (the public entry, re-exports), and `read_tool.py`
  (`kind` enum from `views.KINDS`).
- **Chat deletes:** `the_one/db/repositories.py` `ChatSessionRepository`
  `delete`, `delete_all_for_agent`, `delete_older_than` and `purge_messages`
  (~L3211-3290). `retention.py` purges GleepGlorp chats through
  `delete_older_than`.
- **Rename:** `the_one/db/repositories.py::AgentStore.rename` (~L436) cascades
  references in one transaction.
- **Leg 1's outputs** (landing in parallel): `the_one/agent/service.py` and
  `rules_service.py`. This leg only reads stored values for `base`; it does not
  call them.

## Outputs
- `the_one/gleepglorp/proposals/` (new package):
  - `shape.py`: the change shape, its validation and the field definitions;
  - `store.py`: `GleepGlorpProposalRepository`;
  - `tool.py`: `ProposeChangeTool`;
  - `events.py`: `push_proposal_changed`.
- Schema v54: the `gleepglorp_proposals` table.
- `factory.py`: GleepGlorp registers and binds `propose_change`.
- `read_app_config` gains `kind="fields"`.
- Chat deletes, the purge and agent rename handle proposals.
- Tests (below) and docs.

## Acceptance Criteria
1. **Schema v54** adds `gleepglorp_proposals`, with no foreign keys:
   - `id INTEGER PRIMARY KEY AUTOINCREMENT` (the "Proposal 12" number);
   - `session_id TEXT NOT NULL`, `tool_call_id TEXT`;
   - `kind TEXT CHECK IN ('agent','rule','routine')`;
   - `action TEXT CHECK IN ('create','change')`;
   - `agent_name TEXT` (the target agent; for an agent create, the proposed
     name);
   - `target_id TEXT` (a rule or routine id; null otherwise);
   - `target_key TEXT NOT NULL` (see AC6);
   - `changes TEXT NOT NULL` (JSON), `base TEXT` (JSON or null);
   - `status TEXT CHECK IN ('pending','applied','dismissed','withdrawn','failed')
     DEFAULT 'pending'`;
   - `result TEXT` (JSON or null);
   - `untrusted INTEGER NOT NULL DEFAULT 0`, `untrusted_sources TEXT` (JSON
     list);
   - `created_at TEXT NOT NULL`, `resolved_at TEXT`.

   Indexes: `(session_id, status)` and `(agent_name)`. The step is idempotent
   (`CREATE … IF NOT EXISTS`), `CURRENT_VERSION = 54`, and
   `tests/test_db_migration.py` gains a v54 class (fresh database; replay with
   the `schema_version` row rewound, as squawk 0388 fixed for v53). The session
   template picks it up with no change (its equivalence guard passes).
2. **The change shape** (`proposals/shape.py`) declares, per kind, a
   `FieldSpec` for each field: `name`, type, `label` (card text), bounds or
   choices, `create_required`, `create_only`, and `ref` (`provider` / `mcp` /
   `kb` / `None`, for name-to-id resolution).
   - **agent:**
     - `name` (create only, required on create);
     - `description`, `system_prompt`;
     - `provider` and `model` (a pair: both or neither; `provider` is a name,
       stored as `provider_config_id`; `model` is stored as `llm_model`);
     - `enabled_tools` and `disabled_tools` (lists of built-in tool names,
       checked against the registry's built-in names);
     - `mcp_servers` (names, stored as `mcp_source_ids`);
     - `knowledge_bases` (names, stored as `kb_ids`);
     - `rich_visuals`, `notes_enabled` (booleans);
     - `max_iterations` (an integer, 1-200);
     - `chat_history_retention_days` (an integer, 1-365).
   - **rule:** `text` (required on create), `enabled`, `position` (create
     only, 1-based, default last).
   - **routine:** `name` (required on create), `prompt` (required on create),
     `schedule` (required on create; the canonical `{start, repeat, ends}`),
     `enabled`.
   - **Nothing else is accepted.** Any other key is refused with a sentence
     naming the allowed fields, and in particular `secret_ids`,
     `tool_overrides`, `mcp_overrides`, `self_revision_requires_approval`,
     `routines_self_config_enabled` and `routines_require_approval`. A test
     asserts these six never appear in any spec.
   - **A pin test** maps every agent `FieldSpec` to its `AgentConfig` field
     (`name`, `description`, `provider_config_id`, `llm_model`,
     `system_prompt`, `enabled_tools`, `disabled_tools`, `mcp_source_ids`,
     `kb_ids`, `rich_visuals`, `notes_enabled`, `max_iterations`,
     `chat_history_retention_days`) with a compatible type. The shape may be
     stricter, never looser.
3. **Validation and resolution** (`shape.normalize(kind, action, target,
   changes, *, conn, now, zone) -> Normalized`) refuses with a plain sentence
   (a `ShapeError` that the tool returns as text):
   - an unknown kind, action or field;
   - a missing required field on create;
   - a `create_only` field on change;
   - an empty change;
   - a wrong type or an out-of-range value;
   - provider and model pairing:
     - on a create, both or neither;
     - on a change, `model` alone keeps the agent's current provider (only
       `llm_model` is touched), and `provider` alone is refused ("Give the
       model too.");
   - an unknown built-in tool name. The names come from one shared helper,
     `builtin_tool_names()`, over `BuiltinToolProvider().get_tools()` (the
     source `GET /api/tools`, `api.py` ~L838, uses). Leg 1's agent service
     uses the same helper if it validates tool names. Every built-in name,
     including the whitelist-exempt `current_time`, is valid in
     `enabled_tools` and in `disabled_tools`.

   Name resolution, against the live tables:
   - The provider, MCP server and knowledge-base repositories have only
     `list()` and `get(id)`. Resolution is `list()` plus a filter in `shape.py`,
     and that filter also gives the ambiguity check.
   - A `provider`, an MCP server or a knowledge base name that matches no
     item, or more than one (names are unique only for agents and secrets),
     gets the sentence "No model provider named X." or "More than one MCP
     server is named X; rename one first.".
   - The self-configuration surface row is never resolvable as an MCP server.
     It is excluded by its name, `SURFACE_ROW_NAME` (`the_one/self_configuration/
     constants.py` L108), with the same filter `gleepglorp/view_mcp.py` uses.
   - A rule position resolves by indexing `AgentRuleRepository.list_for_agent`.
     A routine name resolves through `RoutineRepository.get_by_name`
     (`routines/repository.py` L137).
   - The stored `changes` hold ids, in the model's own field names.

   Targets:
   - An agent change needs an existing agent `agent`.
   - An agent create needs `name` free and accepted by `check_agent_name`.
   - A rule change needs `agent` plus `rule` (1-based position), resolved to
     the rule's id.
   - A routine change needs `agent` plus `routine` (name), resolved to its id.
   - The target must exist when the proposal is made (DD2).
   - `GleepGlorp` and `default` are never valid targets (reserved).

   Routine schedules:
   - The schedule is normalised once, at proposal time, with the operator's
     caps (`validate_schedule(raw, now, tz, min_ahead=_min_ahead(False))`,
     then `_require_future`).
   - The now-start shape is refused (`normalize` refuses it when
     `resolve_now_start` is not called; a test pins this).
   - The stored change holds `schedule` and `anchor_at`, the pair
     `create_routine(schedule_pair=…)` takes.
4. **`base`** holds, for a change, the stored value of each touched field read
   at proposal time, in stored form (ids; `mcp_source_ids` without the surface
   id). A create has `base` null.
   - **One normaliser.** The "without the surface id" form comes from one public
     function in Leg 1's `the_one/agent/service.py`, which Leg 1's precheck uses
     too, so the two cannot drift.
   - **If Leg 1 did not export it, this leg adds** `comparable_value(field,
     value, surface_id)` there, with Leg 1's precheck switched to it, and
     records that in the flight log.
   - **The surface row's id** for an agent is the id of the MCP source named
     `SURFACE_ROW_NAME` in that agent's `mcp_source_ids`.
5. **`propose_change`** (`proposals/tool.py::ProposeChangeTool`):
   - **Parameters:**
     - `kind` (enum), `action` (enum);
     - `agent` (string), `rule` (integer, optional), `routine` (string,
       optional);
     - `changes` (object).
   - **The schema stays thin.** The description names the fields per kind in
     one short line each. A unit test always asserts it is at most 520
     characters. The same test also asserts at most 120 `o200k_base` tokens
     when `tiktoken` is importable (`pytest.importorskip` branch; it is in the
     repo `.venv` but not in CI).
   - **On a call it:**
     1. reads the chat id (`TurnContext.session_id`, else
        `current_chat_session_id`; with neither, it refuses: "Proposals need a
        chat.");
     2. normalises (AC3) and reads `base` (AC4);
     3. computes the taint with `compute_taint(self._agent,
        current_tool_call_id.get(), turn)` (unbound means flagged as "unknown
        position");
     4. inserts through the repository (AC6), which applies the
        one-open-per-chat rule;
     5. pushes `proposal_changed`.
   - **It returns** "Proposal {id} is waiting for the operator. Nothing has
     changed yet." or the refusal sentence. It never raises into the loop.
   - **Registration:** GleepGlorp registers and binds it whenever GleepGlorp is
     built (enabled and ready), outside every operator filter, alongside
     `read_app_config`. It is in GleepGlorp's starting set, since the factory
     seeds every GleepGlorp tool (~L753). Build tests that assert
     `agent._loaded_schemas` are updated.
   - **Trusted in the taint rule.** `propose_change` is added to
     `TRUSTED_TOOL_NAMES` (`the_one/agent/taint.py` L36). Its result is
     shipped text ("Proposal N is waiting…"), like `get_app_guide`, so one
     proposal never flags the next. A test checks that a second proposal after
     a first, with no untrusted read between them, is not flagged. Falsify it
     by removing the name.
   - **No other agent gets it.** A test builds an ordinary agent with every
     tool on and asserts `propose_change` is absent.
6. **The repository** (`proposals/store.py::GleepGlorpProposalRepository`):
   - **`target_key`:**
     - `agent:{name}` for an agent create or change;
     - `rule:{agent}:{rule_id}` for a rule change, `rule:{agent}:new` for a
       rule create;
     - `routine:{agent}:{routine_id}` for a routine change,
       `routine:{agent}:new:{name}` for a routine create.
   - **`insert(row)`** runs one `write_transaction`. It reads the chat's open
     proposal (status `pending` or `failed`; at most one exists):
     - if the open one is `failed`, or has the same `target_key`, it is marked
       `withdrawn` (`resolved_at` set, `result = {"reason": "replaced",
       "by": new_id}`), then the new row is inserted;
     - otherwise the insert is refused with `ProposalOpen(open_id)`, and the
       tool returns "Proposal {open_id} is still waiting for the operator.
       Wait for their answer before the next step.";
     - with no open proposal, the new row is inserted.
   - **Reads:** `get(id)`, `list_for_session(session_id)` (by id) and
     `open_for_session(session_id)`.
   - **`mark(id, status, *, result=None, from_statuses)`** writes only
     `WHERE id = ? AND status IN (from_statuses)` and returns whether a row
     changed. An `op(conn, id)` form is usable inside another repository's
     transaction (Leg 4's `on_commit`, the routines `proposal.run` Protocol).
     Leg 4 uses `mark`; this leg tests it.
7. **Deleting and renaming:**
   - `ChatSessionRepository.delete`, `delete_all_for_agent` and
     `delete_older_than` delete the proposals of every chat they delete, in
     the same transaction.
   - `purge_messages` deletes the purged chat's proposals.
   - `AgentStore.rename` rewrites `agent_name` and the `agent:` / `rule:` /
     `routine:` prefix of `target_key` for the renamed agent, in its
     transaction.
   - A test covers each of these, the GleepGlorp retention purge included.
8. **`read_app_config(kind="fields", name=?)`:**
   - With no `name`, it lists the three proposable kinds with their field
     names and labels.
   - With `name` (`agent`, `rule` or `routine`), it gives each field's type,
     bounds or choices, whether it is required on create, create only, and how
     to name a reference ("a model provider's name").
   - It is generated from the shape, never hand-written.
   - **It is a list kind** (`LIST_KINDS`). Its list entries are `{name,
     summary}`, and its detail is `{name, fields: [{name, label, type, ...}]}`.
     Every key is declared, with `fields` as `nested`, so the structural key
     guard (`UndeclaredKeyError`) passes. An unknown name (`does-not-exist`,
     `x*500`) answers through the unknown-name `PlainMessage` path, never a
     raise.
   - **The deliberate test edits** in `tests/test_gleepglorp_views.py`:
     - `test_every_kind_is_classified` goes from `len(KINDS) == 10` to 11;
     - `KINDS`, `VIEWS`, `ALLOWED` (exactly `{list, detail, nested}` for
       `fields`), `PARITY_DRIVER` and the tool's enum gain the kind;
     - `test_unknown_name_lists_only_that_kinds_valid_names`,
       `test_reads_change_nothing` and secret parity now cover it.
   - It emits no stored value.
9. **The allowlist:** `tests/test_gleepglorp_build.py` gains `propose_change`
   wherever it enumerates the tool set, updated on purpose:
   - the sets at ~L94-133;
   - `_BASE` (~L192);
   - the parametrized matrix (~L199-220);
   - `test_the_allowlist_holds_with_current_time_off_app_wide` (~L121). A new test
   runs a `propose_change` call (a create and a change, each kind) against a
   seeded database and asserts that every table except `gleepglorp_proposals`
   is byte-identical before and after (a dump of every table).
10. **Tests**, falsified where marked: `tests/test_gleepglorp_proposals_store.py`,
    `tests/test_gleepglorp_proposals_shape.py`,
    `tests/test_gleepglorp_proposals_tool.py`, plus the edits named in AC1, 8
    and 9. They cover:
    - each refusal sentence in AC3;
    - name resolution (unknown, ambiguous, surface row);
    - one open per chat (refused, replace-failed, replace-same-target), each
      falsified;
    - `mark` transitions (no write from a disallowed status), falsified;
    - a routine schedule normalised with operator caps, with the now-start
      refused;
    - the delete, purge and rename cascades, falsified for one delete site;
    - the no-write test, falsified by making the tool also save an agent;
    - the six forbidden keys.
11. **Docs:**
    - `the_one/agents.md` gains a "GleepGlorp proposals (M36 F2)" section
      covering the shape, the table, the tool and the one-open rule.
    - `CLAUDE.md` gains one short paragraph.
    - The paragraph says the prompt does not yet mention proposals (Leg 9).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_proposals_*.py tests/test_gleepglorp_build.py tests/test_gleepglorp_views.py tests/test_db_migration.py tests/test_schema_template.py -x --timeout 60`
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `ruff check` and `ruff format --check` on the touched files.
- No browser lane is needed: no static file changes. If one does change,
  run its lane and the static guards.

## Implementation Guidance
1. **Schema first:** write the v54 step and the migration tests.
2. **The shape:** write `shape.py`, with `FieldSpec`, the three kind specs,
   `normalize` and `describe`. Resolve references through the existing
   repositories:
   - provider: `LLMProviderRepository`;
   - MCP: `MCPSourceRepository`, excluding the surface row;
   - knowledge bases: their repository;
   - rules: `AgentRuleRepository.list_for_agent`;
   - routines: the routine repository's lookup by name.

   Use the connection the tool gets from `get_connection()`, as the routine
   tools do.
3. **The repository and events:** write `store.py` and `events.py`.
   `push_proposal_changed` uses `sessions/_broadcast.py::broadcast_to_session`
   with `{"type": "proposal_changed", "proposal": view}`.
   - The `view` serialiser lives in `store.py` and is reused by Leg 4 and Leg
     6. Its docstring states the payload shape, as Leg 6's contract.
   - Display names are resolved when the view is read. A reference that no
     longer exists shows as "(removed)". It carries:
   - `id`, `kind`, `action`, `agent_name`, `target_id`;
   - `changes` and `base` with display names resolved at read time;
   - `labels` from the shape;
   - `status`, `result`, `untrusted`, `untrusted_sources`, `created_at`,
     `tool_call_id`.
4. **The tool:** write it, register it in the factory's `if gleepglorp:`
   block, and add it to the `bind_agent` loop.
5. **Cascades:** add the chat delete, purge and rename handling.
6. **The fields kind:** add `fields` to the views and `read_app_config`.
7. **Tests:** write them and falsify the ones marked. Run the unit tier.
8. **Docs.**

## Edge Cases
- **An unknown `proposal_changed` frame before Leg 6** is ignored silently, as
  checked at design review. `turn-frames.js::handle` is an if/else-if chain
  with no fallback, and the frame gate drops it while not joined. No static
  change is made in this leg.
- **The v53 step's own chat deletes** (`schema.py` ~L3385) predate proposals,
  so no cascade is needed there.
- **A routine's `schedule` given as a sentence or other non-object** is
  refused by the shape, "schedule must be an object like {start, repeat,
  ends}". The routines error sentences pass through for a bad object.
- **`provider` alone, or `model` alone, on a change** is refused (AC3). On a
  create, both may be omitted; the agent then has no model, which the forms
  allow.
- **`enabled_tools: null` in the model means "all"**, and a proposal cannot
  express null. Lists only; an empty list is "none". Say so in the field
  definition.
- **A rule position beyond the last** is clamped to "last" (Leg 1's
  repository clamps too).
- **Two tool calls in one turn** both go through `insert`. The second one
  either replaces the first (same target) or is refused, so a chat never has
  two open.
- **The tool runs while GleepGlorp's settings change mid-turn.** It does not
  re-check `enabled`. A proposal from a turn that started while enabled is
  recorded, and Leg 4 decides what Approve does.

## Files Affected
- `the_one/gleepglorp/proposals/__init__.py`, `shape.py`, `store.py`,
  `tool.py` and `events.py` (new).
- `the_one/db/schema.py` (v54).
- `the_one/db/repositories.py` (the chat delete, purge and rename cascades).
- `the_one/agent/factory.py` (registration and bind).
- `the_one/agent/taint.py` (`propose_change` added to `TRUSTED_TOOL_NAMES`).
- `the_one/agent/service.py` (only if Leg 1 did not export the shared
  normaliser; AC4).
- `the_one/gleepglorp/view_core.py`, `views.py` and `read_tool.py` (the
  `fields` kind; a new `view_fields.py` if `view_core.py` would pass about 400
  lines).
- Tests: the three new files, plus `test_gleepglorp_build.py`,
  `test_gleepglorp_views.py` and `test_db_migration.py`.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Checked against the working tree at `6f073dd4`. Leg 1 is landing in parallel;
re-check `repositories.py` line numbers after it lands.
- `schema.py` `CURRENT_VERSION = 53` L18; the v53 step at L3334, which creates
  `gleepglorp_notes` at ~L3393 — verified.
- `factory.py` L567-576: `if gleepglorp:` registers `ReadAppConfigTool` and
  `GetAppGuideTool`. `bind_agent` loop at L806-809 — verified.
- `routines/tools.py::_RoutineToolBase` L113-180: `bind_agent`, `_session_id`
  (`turn.session_id or current_chat_session_id.get()`), `compute_taint(self._agent,
  current_tool_call_id.get(), turn)` — verified.
- `agent/_context.py` `TurnContext.session_id` L98, `current_turn` L108 —
  verified.
- `routines/service.py`: `validate_schedule` L112 (wraps
  `recurrence.normalize`), `resolve_now_start` L143 (operator only),
  `_require_future` L169, `_min_ahead` L216, `create_routine(…,
  schedule_pair=…)` L222-240, `_agent_schedule` L494 (the agent variant this
  leg does not use) — verified.
- `gleepglorp/read_tool.py`: `kind` enum from `views.KINDS`; a failure returns
  "Could not read {kind} right now." — verified. `view_core.py::KINDS` L23 —
  verified.
- `repositories.py` `ChatSessionRepository`: `delete`, `delete_all_for_agent`,
  `delete_older_than` and `purge_messages` (~L3211-3285) — verified.
  `retention.py` L77 and L88 purge through `delete_older_than`, GleepGlorp
  included — verified.
- `repositories.py::AgentStore.rename` ~L436: one transaction with manual
  cascades — verified.
- Design review (Developer, Sonnet), approve with changes:
  - `TRUSTED_TOOL_NAMES` L36 lacked the new tool (high).
  - The provider, MCP and KB repositories have no get-by-name.
    `RoutineRepository.get_by_name` is at L137. `SURFACE_ROW_NAME` is at
    `self_configuration/constants.py` L108.
  - `GET /api/tools` builds from `BuiltinToolProvider().get_tools()` (L838).
  - The views tests pin `len(KINDS) == 10`. The build tests enumerate the set
    at L94-133, L192 and L199-220.
  - The client ignores unknown frames silently. The schema template needs
    nothing beyond the version bump.

  All folded in above.
