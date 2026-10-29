# Leg: agent-routine-store

**Status**: completed
**Flight**: [Agents Schedule Their Own Routines](../flight.md)

## Objective

Give the backend everything an agent's routine change needs, short of the
tools themselves (leg 3):
- the v46 schema;
- the operator's Routines switches;
- the flag on routines;
- the proposals record;
- the caps;
- one service entry point for an agent change, which is applied or held as
  pending, and approve and dismiss;
- the REST routes the Routines item will use.

The leg also completes squawk 0277, limited to the provider.

## Context

- **Flight DDs:** DD4 (schema and composition), DD5 (switches, routes,
  call-time check), DD6 (proposals, approve, dismiss, drift), DD7 (where the
  flag lives and how it clears), DD8 (the count and frequency caps), DD10
  (retention) and DD14 (squawk 0277).
- **Leg 1** moved the routine write rules into `the_one/routines/service.py`,
  which takes `conn` from its caller (read the leg 1 entry in the flight log
  for the landed function names). This leg extends the service. It never
  forks it.
- **Leg 3** will call `agent_change(...)` from the tools. Leg 3 supplies the
  taint, the session id and the per-turn counter. This leg does everything
  else, so leg 3 stays thin.

## Inputs

- Leg 1 landed (`routines/service.py`).
- Schema at v45 (`the_one/db/schema.py`, `CURRENT_VERSION = 45`; the v45
  migration creates `agent_routines` with
  `UNIQUE (agent_name, name COLLATE NOCASE)` and `created_by`).
- **`SQLiteAgentStore.save`** (`the_one/db/repositories.py:251-299`) lists
  every flag column in its INSERT and its `ON CONFLICT DO UPDATE`. The
  targeted setters `set_self_revision_requires_approval` (`:301`) and
  `set_notes_enabled` (`:318`) are the pattern.
- **`update_agent`** (`api.py:1065`) preserves operator-owned flags when the
  PUT omits them (`:1099-1110`). **`create_agent`** (`api.py:1014`)
  validates `AgentConfig` and never checks the provider exists (squawk 0277).
- **`AgentRoutineRepository`** (`the_one/routines/repository.py`): `create`
  (`:131`) enforces `ROUTINES_PER_AGENT_MAX` in its transaction; `update`
  (`:193`) is restricted to `_UPDATABLE` (`:45`); `delete` (`:216`). Each
  opens its own `write_transaction`, which refuses to nest
  (`the_one/db/_write_lock.py:63`).
- **The revisions approve route** (`api.py:2150-2212`) is the shape to
  mirror: 404 for a cross-agent id, an idempotent applied, a 409 for
  dismissed or superseded, and a stale 409 `{"error":"stale","current_value",
  "proposed_value","base_value"}`.
- **Pins:**
  - `tests/test_routines_api.py:86` pins the routine view's exact key set;
  - `tests/test_db_migration.py`, `tests/test_schema.py`,
    `tests/test_schema_template.py` and `tests/test_db_connection.py` carry
    version pins;
  - `tests/test_api_name_rule.py` classifies every POST/PUT route.

## Outputs

### Schema v46 (`the_one/db/schema.py`)

`CURRENT_VERSION = 46`. The migration makes three changes.

**1. `agents`** gains:
- `routines_self_config_enabled INTEGER NOT NULL DEFAULT 0`;
- `routines_require_approval INTEGER NOT NULL DEFAULT 1`.

**2. `agent_routines`** gains:
- `untrusted INTEGER NOT NULL DEFAULT 0`;
- `untrusted_sources TEXT` (a JSON list, or NULL).

**3. A new table, `agent_routine_proposals`**, exactly as flight DD4 lists
it:
- `id`;
- `agent_name`, a foreign key with `ON DELETE CASCADE ON UPDATE CASCADE`;
- `routine_id`, `REFERENCES agent_routines(id) ON DELETE SET NULL`;
- `routine_name`;
- `action`, CHECK create/update/delete;
- `payload` (`NOT NULL`) and `base`;
- `status`, CHECK applied/pending/dismissed/superseded;
- `untrusted` and `untrusted_sources`;
- `session_id` (no foreign key);
- `created_at` and `resolved_at`.

It has the index `idx_agent_routine_proposals_agent_status (agent_name,
status)`.

`ALTER TABLE ... ADD COLUMN` is enough for 1 and 2: there are no CHECK
changes on existing columns.

**Guard every `ALTER`** with a column-exists check against `PRAGMA
table_info`, and create the table and index with `IF NOT EXISTS`. That is the
established pattern: `schema.py:2100-2103` (`self_revision_requires_approval`)
and `:2707-2709` (`notes_enabled`). It matters because
`test_v44_database_migrates` re-runs migrations over a database that
already has the columns.

**The version and table pins.** Grep, rather than trusting a list:
- grep `CURRENT_VERSION`, `schema_version` and `\b45\b` across
  `tests/test_db_migration.py`, `tests/test_schema.py`,
  `tests/test_schema_template.py` and `tests/test_db_connection.py`;
- known at design: `test_db_migration.py:5019, 5375, 5521, 5662, 5785, 5799`
  (`== 45`, including the `== 45 == CURRENT_VERSION` forms in older classes)
  and `:5807/:5813/:5823` (`schema_version >= 45` / `= 45`).

**What else in `TestSchemaV45` changes:**
- Its `_ROUTINE_COLS` comparisons (`:5742/:5791/:5812`) compare
  `PRAGMA table_info(agent_routines)` exactly. Extend the list with the two
  new columns, or split a v46 list.
- `test_v44_database_migrates` (`:5802-5823`) drops `agent_routine_runs` and
  then `agent_routines`. It must drop `agent_routine_proposals` first (the
  foreign key), and delete `schema_version >= 45` rows so v45 and v46 both
  re-run.

### Agent switches

**`AgentConfig`** (`the_one/agent/config.py`) gains:
- `routines_self_config_enabled: bool = False`;
- `routines_require_approval: bool = True`.

Both carry a comment like the existing operator-owned ones.

**`_row_to_config`** reads both columns.

**`save` writes neither.** They are out of both its INSERT column list and
its `ON CONFLICT` set, so a new row gets the literal defaults.

**`create_agent` and `update_agent`:**
- They ignore any incoming value. `create_agent` pops both keys from `data`
  before `AgentConfig.model_validate`, so the defaults apply. `update_agent`
  sets them to the existing values before validation, beside the
  `notes_enabled` preserve (`api.py:1108-1109`).
- So the response echoes the stored truth, and a PUT can never change them.
- An exported-then-imported agent, if any such path exists (grep for
  `model_dump()` → `save`), gets the defaults. That is the safe direction, so
  it needs no change; note it if found.

**The targeted setter.** `SQLiteAgentStore.set_routines_self_config(name,
*, enabled: bool | None = None, requires_approval: bool | None = None)`:
- It is a targeted UPDATE of the given fields only, in the pattern of
  `set_notes_enabled`.
- It raises `KeyError` for an unknown agent.

### Routine model and repository

**`Routine`** gains `untrusted: bool = False` and
`untrusted_sources: list[str] = []`. They are read from the new columns, with
the JSON decoded.

**`AgentRoutineRepository.create`, `update` and `delete`** gain keyword-only
arguments, all applied inside the mutator's one `write_transaction`. Leg 1's
service functions take no transaction of their own (by design), so **every
check that must not race lives in the repository**, in this order inside the
transaction:

1. **Re-read.** `update` and `delete` re-SELECT the routine row inside the
   transaction (the repo already does this for `update`). A missing row is a
   `KeyError`, as today.
2. **`precheck: Callable[[Routine | None], None] | None = None`**: a sync
   callable run on the row just read, inside the transaction. The service
   uses it for approval's stale and gone checks (`ProposalStaleError`,
   `ProposalGoneError`). For `create` it receives `None`. That is the only way
   a base-versus-current compare is atomic with the write. Never compare in
   the service before calling the repo.
3. **`agent_caps: bool = False`**: SELECT the agent's routines inside the
   transaction, build the "after" list (the before list with this change
   applied: the new row, the updated fields, or the row removed) and run the
   DD8 raise-only check (below).
4. **The write**: the INSERT, UPDATE or DELETE, with `flag` applied to the
   row.
5. **`proposal`**: run after the write, so a create's `resolve` and
   `insert_applied` know the new `routine_id`.

The arguments, in detail:
- **`flag: tuple[Literal["merge"], list[str]] | Literal["clear"] | None = None`**:
  - `merge` ORs `untrusted` in and merges the sources, de-duplicated, in
    order, capped at `SOURCES_CAP` (10, imported from `the_one.db._notes`,
    a leaf module with no cycle);
  - `clear` sets `0` and `NULL`;
  - `None` leaves the flag alone.
- **`proposal: ProposalOp | None = None`**: one of `insert_applied(row)` or
  `resolve(proposal_id)`, executed on the same connection inside the
  transaction. `resolve` sets the pending row to `applied`, sets
  `resolved_at` and, for a create, `routine_id`.
- **`delete`** also supersedes that routine's pending proposals in the same
  transaction. That is DD4's rule for an operator delete, and it is harmless
  for an agent delete.
- **`created_by`.** `create` accepts it from the caller ("agent" for agent
  writes), as today. `_UPDATABLE` gains `untrusted` and `untrusted_sources`
  only through the `flag` argument, not as free fields.

### Proposals (`the_one/routines/proposals.py`)

**`RoutineProposal`**, a pydantic model mirroring the table. It holds
`payload` and `base` as dicts and `untrusted_sources` as a list.

**`RoutineProposalRepository(conn)`** has these methods:
- `list(agent_name, *, status=None, limit=50, before=None)`: newest first,
  paged by `created_at`, then `id`;
- `pending_count(agent_name)`;
- `get(proposal_id)`;
- `insert_pending(row, *, caps_check)`. In **one** transaction, so two
  concurrent agent calls cannot both pass a limit, it:
  - for a create, refuses when a pending create with the same name exists:
    `json_extract(payload,'$.name') = ? COLLATE NOCASE`, the message "A
    routine with that name is already waiting for approval." It also refuses
    when an existing routine has that name (`RoutineNameTaken`);
  - supersedes an older pending row with the same `routine_id`, for an
    update or delete;
  - refuses past `AGENT_PENDING_PROPOSALS_MAX = 20` with
    `RoutineLimitError("You have 20 changes waiting for approval.")`;
  - runs the caps check (a create or update that would raise a capped
    measure over its cap is refused at proposal time, DD6);
  - inserts the row;
  - prunes the agent's resolved rows beyond the newest
    `AGENT_PROPOSALS_KEPT = 500`.

  It returns `(row, replaced: bool)`.
- `insert_applied(conn_in_txn, row)`: used inside a routine mutator's
  transaction; it also prunes;
- `resolve(conn_in_txn, proposal_id, routine_id)`;
- `mark_dismissed(proposal_id)`: idempotent on an already-dismissed row, and
  `ValueError` on applied or superseded;
- `supersede_pending(agent_name)`: returns the count.

`ProposalOp` is a small dataclass naming which operation to run and with
what.

### Caps (`the_one/routines/limits.py`)

**New constants:**
- `AGENT_ACTIVE_ROUTINES_MAX = 10`;
- `AGENT_RUNS_PER_DAY_MAX = 48`;
- `AGENT_ONCE_MIN_AHEAD_MINUTES = 1`;
- `AGENT_PENDING_PROPOSALS_MAX = 20`;
- `AGENT_PROPOSALS_KEPT = 500`;
- `AGENT_ROUTINE_WRITES_PER_TURN = 5`. Leg 3 uses it; it is defined here.

**`runs_per_day(schedule: dict, *, now, next_run_at) -> int`** returns the
conservative maximum for one routine:
- daily, weekdays, and weekly with any day are each 1;
- interval is `ceil(24 / hours)` (the interval kind is in whole hours, with
  `INTERVAL_HOURS_MIN = 1`; confirm this against `schedule.validate`);
- a once due within 24 hours of `now` is 1, and later is 0.

**`check_agent_caps(before: list[Routine], after: list[Routine], now)`**
measures the active count (enabled and `finished_at` is None) and the
runs-per-day sum, before and after. For each measure it raises
`RoutineLimitError(sentence)` only if the measure **rose** and is now over
its cap. The sentences name the cap and the current value, for example:
- "You already have 10 active routines, the most allowed. Cancel or turn one
  off first."
- "That would make your routines run more than 48 times a day."

**The one-off minimum.** For agent writes, a `once` less than
`AGENT_ONCE_MIN_AHEAD_MINUTES` ahead is refused: "A one-time routine must be
at least a minute away." Operator writes keep Flight 1's rule.

### The agent change service (`the_one/routines/service.py`)

**`async agent_change(conn, agent_name, action, data, *, now, zone: ZoneLoader, taint, session_id) -> AgentChangeResult`**

(`zone` is leg 1's async `ZoneLoader`, not a `tzinfo`. The same applies to
`approve_proposal` below.)

- `action` is `"create" | "update" | "delete"`.
- For update and delete, `data` carries `routine` (an id, or a
  case-insensitive name).
- `taint` is `(untrusted: bool, sources: list[str])`.

In order, it:
1. **Re-reads the agent's two switches** from `agents`. When Routines is
   off, it raises `RoutineFieldError("routines", "Routine tools are turned
   off for this agent.")` (DD5, the call-time check). It refuses the
   `default` agent the same way: "Routines need a named agent."
2. **Resolves the routine** for an update or delete:
   - by id, else by name `COLLATE NOCASE`, within the agent;
   - an unknown routine gives "There's no routine called '{the name as
     passed}'.";
   - a routine whose create is still pending (the name matches a pending
     create proposal's payload, through the same `json_extract ... COLLATE
     NOCASE` query, never a fetch-and-loop) gives "That routine is still
     waiting for your operator's approval, so it can't be changed yet."
3. **Validates exactly as the operator path does,** through leg 1's
   validators, plus the one-off minimum. The validated request becomes the
   `payload`: a once's `in` is converted to an absolute `at`, and the target
   is the adapted REST body `{kind, session_id?}`.
4. **Takes a `base` snapshot** for an update or delete: the raw stored
   fields `name`, `prompt`, `schedule`, `enabled`, `finished_at`,
   `target_kind`, `target_session_id`.
5. **With approval on:** calls `RoutineProposalRepository.insert_pending`
   with the caps check, and returns `pending=True` plus `replaced`.
6. **With approval off:** applies through leg 1's `create_routine`,
   `update_routine` or `delete_routine`. These pass
   `created_by="agent"` (create only), `agent_caps=True`,
   `flag=("merge", sources)` when `untrusted` is true (else `None`), and
   `proposal=insert_applied(...)`. The result has `pending=False`.
7. **Pokes the scheduler** on an applied write.

`AgentChangeResult` carries `pending`, `replaced`, `routine` (when applied),
`proposal_id` and `routine_id`.

Leg 1's `create_routine` and `update_routine` grow the keyword pass-throughs
(`created_by`, `agent_caps`, `flag`, `proposal`). Their operator callers pass
none of them, so REST behaviour is unchanged, except for the flag clear
below.

**`async approve_proposal(conn, agent_name, proposal_id, *, override, now, zone) -> RoutineProposal`**
- **The checks:**
  - a cross-agent or unknown id raises `KeyError`, which becomes a 404;
  - an applied proposal is returned as is;
  - a dismissed or superseded one raises `ProposalStateError`, a 409.
- **Validation, split at the transaction boundary.**
  - **Before the transaction**, as leg 1 does: await the zone, re-validate
    the schedule (a past `at` refuses with the schedule sentence, a 422), and
    re-resolve the target through `resolve_target` (the chat still exists
    and is the agent's). Never `await` the zone or the chat repository while
    holding the write lock.
  - **Re-read the routine at approval time** for an update, then call
    `update_routine` with that fresh `current`. Its computed `anchor_at` and
    `next_run_at` then reflect now, not proposal time.
  - **Inside the mutator's transaction:** name uniqueness
    (`RoutineNameTaken`, a 409), the caps (`agent_caps=True`), and, for an
    update or delete, the stale and gone checks through `precheck`.
- **The stale check** compares `base` with the re-read row's raw fields over
  the keys the payload touches. On a difference without `override`, it
  raises `ProposalStaleError(current, proposed, base)`, a 409.
- **A gone routine:**
  - for an update, the proposal becomes `superseded` and the call raises
    `ProposalGoneError`, a 409 `{"error":"gone"}`;
  - for a delete, the proposal becomes `superseded` and is returned (a 200).
- **On success:**
  - it writes with `proposal=resolve(id)`, `created_by="agent"` for a
    create, and the proposal's flag `merge`d;
  - it pokes the scheduler.

**`async dismiss_proposal(conn, agent_name, proposal_id) -> RoutineProposal`**
uses `mark_dismissed`, with the same 404 and 409 mapping.

**The operator flag clear.** `update_routine` called from the REST route
with `prompt` present in the body passes `flag="clear"`. The REST `PUT` is
the **only** caller that ever passes `"clear"`. An agent-applied prompt
update merges, and AC9 pins that.

### REST (`the_one/interfaces/web/api.py`)

**`GET` and `PUT /api/agents/{name}/self-configuration/routines`**
- The body is `{enabled?: StrictBool, requires_approval?: StrictBool}`. The
  PUT needs at least one key, and an empty body is a 422.
- Both return `{enabled, requires_approval, pending_count}`.
- `default` gives a 422 "Routines need a named agent."; an unknown agent
  gives a 404.
- A PUT that turns `enabled` from on to off also calls
  `supersede_pending(name)`.
- The existing `GET` and `POST /api/agents/{name}/self-configuration` are
  byte-identical (pinned at `tests/test_self_configuration_api.py:90`).

**The proposals routes**, under
`/api/agents/{name}/self-configuration/routines/proposals`:
- `GET` with `status` (`pending|applied|dismissed|superseded`, optional),
  `limit` (1-200, default 50) and `before` → `{"proposals": [...]}`;
- `GET pending-count` → `{"count": n}`;
- `POST {id}/approve?override=false`;
- `POST {id}/dismiss`.

These map the service's errors as described above. A proposal is serialized
by `model_dump()`, with no extra fields.

**The routine view** (leg 1's `routine_view`) gains `untrusted` and
`untrusted_sources`.

**The name-rule classification.** `tests/test_api_name_rule.py` classifies
the new PUT and the two new POSTs. None of them sets a name: the approve
route's name comes from an already-validated proposal.

### Squawk 0277 (and 0283)

**The check.** `create_agent` and `update_agent` check the provider after
`AgentConfig` validation:
- `provider_config_id == ""`, or a non-null id with no provider row (through
  `_provider_repo()` at `api.py:5447`; `LLMProviderRepository.get` raises
  `KeyError` for a missing row (`repositories.py:2969-2976`), so catch
  that), gives a 422
  `[{"type":"value_error","loc":["provider_config_id"],"msg":"That model provider doesn't exist."}]`;
- an absent or `null` id stays legal;
- **On `update_agent`, check only when the incoming id differs from the
  stored one.** A Studio Save round-trips the stored id. An agent whose
  provider was deleted later must stay editable (and fixable: the operator
  picks a new provider, which is checked).
- Before landing, grep every `seeders.py` payload and every test that POSTs
  or PUTs `/api/agents` for a hard-coded or fake provider id that would now
  422, and fix the fixture rather than the check;
- `kb_ids` are not checked (flight DD14; M24 DD-14).

**The tests**, in `tests/test_api_agent_provider_check.py`:
- create with `""` gives a 422 and no row; create with an unknown id gives a
  422 and no row;
- update with an unknown id gives a 422 and the row unchanged;
- update round-tripping a stored id whose provider was deleted gives a 200;
- create with no provider gives a 201;
- create with a real provider gives a 201.

**The squawk artifacts:**
- `squawks/0277-...md`: Corrective Action and Verification are written;
  status stays `in-progress` until the FD commits. The FD sets `completed`,
  the commit, and the reviewer sign-off at the Batch A commit.
- 0283 is noted as closing with it.

### Retention

- `run_purge_sweep` and Purge now do not touch `agent_routine_proposals`.
  This is verified, and a test pins it: a sweep with an old proposal leaves
  it.

### Docs

- `the_one/agents.md` "Routines (M33)" gains:
  - the v46 columns;
  - the proposals table and its operations;
  - `agent_change`, approve and dismiss;
  - the caps and their raise-only rule;
  - the call-time switch check;
  - the operator flag clear;
  - the routes.
- CLAUDE.md's Routines paragraph gains one sentence on the Routines item
  routes and the proposals queue.

## Acceptance Criteria

- [ ] **AC1. Migration.** A fresh template database and an existing v45
      database both migrate to v46, and the new columns, table and index
      exist with the stated defaults and CHECKs. This is
      `TestSchemaV46` in `tests/test_db_migration.py`. Every `== 45` version
      pin moves to 46.
- [ ] **AC2. Switches.** Every agent row starts with Routines off and its
      approval on. `PUT /api/agents/{name}` with
      `routines_self_config_enabled: true` changes nothing, and the response
      shows the stored value. After the setter turns them on, a full
      `PUT /api/agents/{name}` with no routine keys leaves both unchanged.
      `POST /api/agents` with them set creates the agent with the defaults.
- [ ] **AC3. Routines item routes.** GET and PUT behave as stated: the
      `default` 422, the unknown-agent 404, the empty-body 422, a
      non-boolean 422, and an off-switch that supersedes pending proposals.
      `tests/test_self_configuration_api.py` passes unedited.
- [ ] **AC4. Agent change, applied.** With approval off, `agent_change`:
  - creates a routine with `created_by` `agent`, an `applied` proposal whose
    `routine_id` is set, and the payload's `at` absolute;
  - on update, writes the change, records an `applied` proposal with
    `base`, and ORs the flag in when `taint` is untrusted;
  - on delete, deletes the routine, and the proposal keeps `routine_name`
    with `routine_id` null.

  All three poke the scheduler. A failure inside the transaction leaves no
  partial row. Test it by injecting a failing `proposal` operation, which
  runs after the routine write: no routine row and no proposal row remain.
  An agent-applied update that includes `prompt` **merges** the flag and
  never clears it.
- [ ] **AC5. Agent change, pending.** With approval on, a create writes only
      a `pending` proposal (no routine; `list_due` sees nothing), and a
      second update to the same routine supersedes the first (`replaced`
      true). The 21st pending is refused with the stated sentence. Resolved
      rows beyond 500 are pruned and pending rows never are.
- [ ] **AC6. Call-time switch.** With Routines off, every action refuses with
      "Routine tools are turned off for this agent." and writes nothing. The
      `default` agent refuses the same way.
- [ ] **AC7. Caps.** The service tests cover:
  - the 11th active routine refused;
  - a create pushing runs per day over 48 refused;
  - a rename, a prompt edit and a frequency-lowering change accepted while
    operator routines already exceed both caps;
  - a once less than a minute ahead refused for the agent and accepted for
    the operator.

  `runs_per_day` is unit-tested per kind.
- [ ] **AC8. Approve and dismiss.** The REST and service tests cover:
  - the 404 for a cross-agent id;
  - an idempotent applied;
  - the 409 for dismissed or superseded;
  - a stale 409 with the three `*_value` keys, then `override=true`
    applying;
  - a gone update giving 409 `gone` and the proposal superseded;
  - a gone delete giving 200 and the proposal superseded;
  - a past `at` at approval giving a 422 with the proposal still pending;
  - a name taken since giving a 409;
  - caps re-checked at approval;
  - a dismiss idempotent on dismissed and a 409 on applied.
- [ ] **AC9. The flag.** An operator `PUT` with `prompt` clears the flag. A
      PUT without `prompt`, a toggle, Run now and approve do not. The
      routine view carries `untrusted` and `untrusted_sources`, and
      `tests/test_routines_api.py`'s key-set pins (`:86`, and the
      `set(out[0])` at `:546`) are updated by exactly those two keys.
- [ ] **AC10. Cascade.** Renaming an agent carries its proposals. Deleting it
      removes them. Deleting a routine supersedes its pending proposals and
      sets `routine_id` null on the others.
- [ ] **AC11. Retention.** The purge sweep and Purge now leave proposals in
      place.
- [ ] **AC12. Squawk 0277.** The five provider tests pass, and the 0277
      artifact has its Corrective Action and Verification.
- [ ] **AC13. Name rule.** `tests/test_api_name_rule.py` classifies the new
      routes and passes.
- [ ] **AC14. Gates.** `THE_ONE_TEST_NETNS=1 make test-unit` is green (15
      skipped). `ruff check` and `ruff format --check` are clean. The
      browser lanes `agent-tabs` and `agents` pass, because the agent PUT
      and the self-configuration GET are used there.
- [ ] **AC15. Docs.** `agents.md` and CLAUDE.md are updated as stated.

## Verification Steps

- **Unit files:**
  - `tests/test_db_migration.py::TestSchemaV46`;
  - `tests/test_routines_proposals.py` (new: repository and caps);
  - `tests/test_routines_service.py` (extended: `agent_change`, approve,
    dismiss);
  - `tests/test_routines_self_config_api.py` (new: the item and proposals
    REST);
  - `tests/test_api_agent_provider_check.py` (new);
  - `tests/test_routines_api.py`;
  - `tests/test_self_configuration_api.py` (unedited);
  - `tests/test_retention.py`;
  - `tests/test_api_name_rule.py`.
- **Lanes**, with `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agent-tabs`:
  `agent-tabs` and `agents`.

## Implementation Guidance

1. Write the schema and migration first, with `TestSchemaV46` and the
   version pins. The template database rebuilds itself from `ensure_schema`.
2. Then `AgentConfig`, `_row_to_config`, `save`'s exclusion, the setter, and
   the create and update forcing. Write the AC2 tests here.
3. Then the `Routine` fields, the repository keyword arguments, and
   `proposals.py`. Run the composition inside the existing `write_transaction`
   blocks; do not add a second transaction.
4. Then the caps, the service functions, the REST routes and squawk 0277.
5. Then docs and the flight log.

## Edge Cases

- **Name matching.** A name the agent passes that matches no routine but
  matches a *pending create* gives the pending sentence, not "no routine".
- **A pending update for a routine that the operator then deletes.**
  `delete` supersedes it, so approve never sees it as pending.
- **The `"{name}"` in refusal sentences** is the name *as the agent passed
  it*, never the stored name (DD7: trusted results never echo stored text).
- **The JSON in `untrusted_sources`**: NULL decodes to `[]`.
- **`resolve` on a create** must set `routine_id` to the newly created id,
  inside the same transaction.
- **The `pending_count` in the item GET** counts this agent only.

## Files Affected

- `the_one/db/schema.py`
- `the_one/agent/config.py`
- `the_one/db/repositories.py`
- `the_one/routines/models.py`
- `the_one/routines/repository.py`
- `the_one/routines/proposals.py` (new)
- `the_one/routines/limits.py`
- `the_one/routines/service.py`
- `the_one/interfaces/web/api.py`
- `the_one/agents.md`
- `CLAUDE.md`
- `squawks/0277-create-agent-unknown-provider-500.md`
- **Tests:**
  - `tests/test_db_migration.py`, plus the version-pin files;
  - `tests/test_routines_proposals.py` (new);
  - `tests/test_routines_service.py`;
  - `tests/test_routines_self_config_api.py` (new);
  - `tests/test_api_agent_provider_check.py` (new);
  - `tests/test_routines_api.py` (the key-set pin only);
  - `tests/test_retention.py`;
  - `tests/test_api_name_rule.py`.

## Citation Audit

Checked at leg design against the tree at `5b607af3`, with leg 1 in
progress:
- `repositories.py:251-299` `save`, `:301`/`:318` setters;
- `api.py:1014` `create_agent`, `:1065` `update_agent`, `:1099-1110`
  preserves, `:2150-2212` revisions approve (shifted by leg 1; re-locate it
  by symbol `approve_agent_revision`), `:5447` `_provider_repo` (corrected
  from `:5672` at design review);
- `routines/repository.py:45/131/193/216`;
- `db/_write_lock.py:63`;
- `tests/test_routines_api.py:86`.

Re-check the `api.py` lines after leg 1 lands, since leg 1 edits that file.
