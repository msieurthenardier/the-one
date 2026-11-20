# Leg: agent-and-rule-services

**Status**: completed
**Flight**: [Proposals and approval](../flight.md)

## Objective
Move the agent and rule write validation out of the route handlers into
services that check and save under the write lock. Add a field-level agent
change with a stale check and an in-transaction mark. Save, create, update and
the rule routes must behave exactly as before.

## Context
- Flight DD3 (as amended by both Architect cycles), DD4 (the status
  transitions that `on_commit` will carry in Leg 4), DD12 (where the code
  lives).
- This leg adds no proposal and no user-visible change.
  - It builds the write path that Leg 4's `apply_proposal` calls.
  - It makes Save and Approve run the same code.
- The existing tests are the guard: every agent, rule and routine test passes
  unchanged. A test that imports a moved private name from `api.py` keeps
  working through the thin wrapper there (AC2), with no edit.
- `api.py` is 7,537 lines. Moving the helpers shrinks it, and nothing new may
  land there except the thin route bodies.

## Inputs
- `the_one/interfaces/web/api.py`:
  - `create_agent` (~L1477) and `update_agent` (~L1536) validate inline;
  - `update_agent_mcp_credentials` (~L1642) and `rename_agent` (~L1721) share
    some helpers;
  - the rule routes run ~L2097-2150.
- The helpers, all in `api.py`, raise `HTTPException` or return detail lists:
  `_checked_agent_name`, `_normalize_surface_fields`,
  `_validate_mcp_override_credentials`, `_merge_preserved_mcp_credentials`,
  `_drop_surface_override`, `_validate_tool_overrides`,
  `_validate_secret_grants`, `_check_agent_provider`, `_tool_config_rows`,
  `_evict_changed_mcp_credentials` and `_validation_detail`.
- `the_one/db/repositories.py`:
  - `AgentStore.save` (~L270) is a full upsert in its own
    `write_transaction`;
  - `AgentRuleRepository` (~L1737) has `create`, `update`, `delete`,
    `reorder` and `_redensify`, each in its own transaction.
- `the_one/routines/repository.py`: `AgentRoutineRepository.create`,
  `update` and `delete` take `proposal: ProposalOp | None` and call
  `proposal.run(self.conn, routine_id)` inside their transaction (L241, L285).
- `the_one/db/_write_lock.py::write_transaction` raises `RuntimeError` when its
  own task re-enters it.

## Outputs
- **New `the_one/agent/service.py`:**
  - `AgentWriteError(status, detail)`;
  - `AgentStaleError(fields)`;
  - `create_agent`, `replace_agent` and `change_agent`;
  - the validation helpers it needs, moved here or into a sibling module
    `the_one/agent/write_checks.py` (Developer's call; neither imports
    `the_one.interfaces`).
- **New `the_one/agent/rules_service.py`:** `create_rule` and `change_rule`.
- **`AgentStore.save(config, *, precheck=None, on_commit=None)`**
  (repositories.py).
- **`AgentRuleRepository.create(..., position=None, precheck=None,
  on_commit=None)` and `update(..., precheck=None, on_commit=None)`.**
- **Routines' `proposal` parameter type** is widened to a small Protocol, with
  no behaviour change.
- **`api.py`:**
  - the agent and rule routes call the services and map errors through one
    helper;
  - the moved helper names stay in `api.py` as thin wrappers that turn
    `AgentWriteError` into `HTTPException` (AC2), for
    existing importers.
- **New unit tests** (see Acceptance Criteria), plus a module-map entry in
  `the_one/agents.md`.

## Acceptance Criteria
1. **The error type.** `the_one/agent/service.py` defines
   `AgentWriteError(status: int, detail: Any)`.
   - Every validation refusal on the agent create, update and change paths
     raises it, carrying exactly the `detail` payload the route returns today:
     each 422 `loc` list, the 409 name-conflict body and the provider 422.
   - The agent routes turn it into `HTTPException(status_code=e.status,
     detail=e.detail)` in one place, a helper or context manager in `api.py`.
   - Responses are byte-identical to today for every existing test.
2. **Service location.**
   - **No interface imports.** None of `the_one/agent/service.py`,
     `write_checks.py` or `rules_service.py` imports `the_one.interfaces`. A
     unit test asserts this over their top-level and function-level import
     nodes. The lazy `interfaces` imports inside `self_configuration.manage`
     are accepted.
   - **Moved, not duplicated.** The helpers the service needs are moved:
     - `_validation_detail` (one definition in `write_checks.py`, which
       `api.py` imports under the same name for its 19 other call sites);
     - `_name_conflict_detail` and `NAME_CONFLICT_AGENT`;
     - `_credential_view`.

     `_checked_name` (non-agent), `_load_agent_or_404`, `_agent_rules_repo`
     and the `_TARGETED_*` constants stay in `api.py`.
   - **Old names in `api.py` stay as thin wrappers.** They call the moved
     helper and turn `AgentWriteError` into the same `HTTPException`, so any
     caller still in `api.py` behaves exactly as today. This covers
     `update_agent_mcp_credentials`, `rename_agent`,
     `tests/test_self_configuration_agent_writes.py:233` and
     `interfaces/web/mcp_agent_test.py:120`.
   - **No leak.** No route that calls a moved helper lets `AgentWriteError`
     escape.
   - **Dependencies are passed in.** The services take their repositories as
     an argument, for example an `AgentWriteDeps(store, mcp_repo,
     provider_repo, secret_repo, tool_config_repo)` that `api.py` builds from
     its own getters (`_agent_store()`, `_mcp_repo()`, …). The services never
     open a connection or read `get_encryptor()` themselves, so the tests that
     patch `the_one.interfaces.web.api.get_connection`, `.get_encryptor` or
     `._agent_store` (about 10 files, for example
     `test_agent_tool_overrides_round_trip.py`, `test_db_api.py:892`) keep
     working unchanged.
3. **`create_agent(deps, data: dict) -> (AgentConfig, rows)`** returns the
   tool-config rows it computed, so the route builds `_full_agent_response(cfg,
   rows)` with no second `ToolConfigRepository.list()`. It runs today's create
   checks in today's order, and then one change:
   1. reserved and naming check;
   2. strip the routines switches;
   3. surface normalization;
   4. MCP override credential validation;
   5. credential merge against `None`;
   6. `AgentConfig.model_validate`;
   7. foreign-surface guard;
   8. tool-override validation;
   9. secret grants;
   10. provider check;
   11. 409 if the name exists;
   12. save;
   13. evict changed MCP credentials.

   - The one change: the 409 for an existing name is also enforced under the
     lock, by a create precheck that raises it when `current is not None`.
     That closes today's check-then-upsert race. It is identical for any
     caller that is not racing.
   - `POST /api/agents` calls it, then builds the response as before.
4. **`replace_agent(deps, name: str, data: dict) -> (AgentConfig, rows)`**
   holds the PUT's whole-body rules, unchanged:
   - Omitted description, prompt, model and tools reset to the
     `AgentConfig` defaults.
   - The surface row is carried in `mcp_source_ids`.
   - These are kept when omitted: `self_revision_requires_approval`,
     `notes_enabled`, `rich_visuals`, `kb_ids`, `secret_ids` and
     `tool_overrides`.
   - The routines switches always keep their stored value.
   - Stored `mcp_overrides` credentials are merged in.
   - A provider is checked only when it changed.
   - It evicts changed MCP credentials after the commit.
   - `PUT /api/agents/{name}` calls it. An unknown agent is still a 404 with
     the same text.
5. **`change_agent(deps, name, changes: dict, *, base: dict | None = None,
   override: bool = False, on_commit=None) -> AgentConfig`** changes only the
   named fields:
   - It loads the stored row and builds the body from it plus `changes`. Every
     field not in `changes` keeps its stored value, the reset-on-omit fields
     included.
   - It never puts `mcp_overrides` in the body, so stored credentials are kept
     as stored and are not re-validated as incoming.
   - It runs the same checks `replace_agent` runs and saves through
     `AgentStore.save(cfg, precheck=…, on_commit=on_commit)`.
   - **Refused keys.** `changes` may not hold `name`, `mcp_overrides`,
     `routines_self_config_enabled` or `routines_require_approval`. Any of
     them is an `AgentWriteError(422, ...)` on its `loc`.
6. **The precheck.** Validation is async (some of it runs in `to_thread`), so
   it runs outside the lock against a snapshot `S` of the stored row.
   `change_agent` then saves with a sync precheck closure that captures `S`,
   `changes` and `base`. The closure runs under the write lock against the row
   re-read inside the transaction:
   - **Touched fields.** When `base` is given, each field in `changes` whose
     stored value differs from `base[field]` is collected. When any differ and
     `override` is false, it raises `AgentStaleError(fields=[{"field", "current",
     "proposed"}])` and nothing is written.
   - **Lists.** `mcp_source_ids` is compared without the agent's own
     self-configuration surface id, and in order. Other lists are compared as
     stored.
   - **Untouched fields.** If a field not in `changes` differs from `S`,
     another write landed between the load and the save, and the closure
     raises a private `_Retry`. `change_agent` catches it, then re-loads,
     re-merges, re-validates and saves again.
     - At most 2 retries. It never raises stale for an untouched field, and
       never writes over the newer value.
     - After the second retry it raises `AgentWriteError(409, [{"loc": [],
       "msg": "This agent changed while the change was being applied. Try
       again."}])`, the list shape that the other 409 bodies use.
   - **What the untouched compare covers.** It compares every persisted
     column that `save` writes, read from `model_dump()`:
     - `description`, `provider_config_id`, `llm_model`, `system_prompt`;
     - `enabled_tools`, `disabled_tools`, `max_iterations`;
     - `kb_ids`, `mcp_source_ids`, `tool_overrides`, `mcp_overrides`;
     - `chat_history_retention_days`, `secret_ids`, `rich_visuals`,
       `self_revision_requires_approval`, `notes_enabled`.

     It leaves out `created_at`, `updated_at`, `routines_self_config_enabled`
     and `routines_require_approval`. `save` never writes the first routines
     switch, and the second is insert-only, so comparing them would cause
     false retries. `mcp_overrides` is compared decrypted, as `load` returns
     it.
   - **The retry loop** is load → merge → validate (all of it async) →
     `save(precheck)`, at most 3 attempts in total.
   - **The targeted writers.** The compare covers the switches that have their
     own writers: `set_self_revision_requires_approval` (repositories.py:330)
     and `set_notes_enabled` (repositories.py:349). A change racing one of
     them keeps the switch.
   - **`replace_agent`** has no precheck. Its documented last-write-wins
     behaviour is unchanged.
   - **The stale payload.** `AgentStaleError` carries `current` and `proposed`
     after normalisation, with the surface id stripped from `mcp_source_ids`.
   - **`base=None`** means there is no touched-field compare.
   - **Override** bypasses only the touched-field comparison.
7. **The save hooks.** `AgentStore.save(config, *, precheck=None,
   on_commit=None)`:
   - re-reads the row inside its `write_transaction` and calls the sync
     `precheck(current: AgentConfig | None)` before the upsert;
   - awaits `on_commit(conn)` after the upsert, inside the same transaction;
   - rolls back the agent write when either raises.

   Called with neither hook, it behaves exactly as today.
   - **A missing row:** the re-read catches `load`'s `KeyError` and passes
     `None`.
   - **Hook defaults:** every other `save` caller passes no hooks and is left
     as it is:
     - `api.py` credentials route (~L1700), self-configuration approve and
       restore (~L2390, ~L2453);
     - `self_configuration/manage.py` (L212, L253, L380);
     - `mcp/rename_references.py`, `knowledge/kb_rename.py`,
       `db/override_cleanup.py` and `db/migration.py`.
   - **Known race kept:** the credentials route keeps its documented narrow
     race.
   - **The Protocol is unchanged.** The `AgentConfigStore` Protocol
     (`the_one/agent/store.py:13`) keeps `save(config)`. Only the concrete
     `AgentStore` (repositories.py) gains the keyword hooks, and the services
     call them on `deps.store`, which is always the concrete class. So the four
     test fakes that implement `save(self, config)` (`tests/test_factory.py:44`,
     `tests/test_tool_exposure.py:189`,
     `tests/test_factory_disable_enforcement.py:46`,
     `tests/test_mcp_tool_provider.py:1252`) are not touched.
8. **Rules.** `the_one/agent/rules_service.py`:
   - `create_rule(agent, text, enabled=True, position=None, on_commit=None)`
     and `change_rule(agent, rule_id, changes, *, base=None, override=False,
     on_commit=None)` apply the rule routes' checks (body model, limits as
     `RuleLimitError`, 404 for a missing rule).
   - **The services take validated primitives.** The request body models
     (`_rules_body`, `_RuleCreateBody`, `_RuleUpdateBody`) stay in `api.py`.
   - **`AgentRuleRepository.create(name, text, enabled, *, position=None,
     precheck=None, on_commit=None)`** runs in one transaction:
     1. the total-chars limit check, as today;
     2. `precheck(None)`;
     3. if `position` is `None`, append at `MAX(position)+1`; otherwise clamp
        it to `[0, n]` (a negative value becomes 0), run `UPDATE ... SET
        position = position + 1 WHERE agent_name = ? AND position >= ?`, and
        insert at it;
     4. `on_commit`.
   - **`update(..., precheck=None, on_commit=None)`** runs in this order: get,
     `precheck(current_rule)`, the limit check, the UPDATE, `on_commit`.
   - **Out of scope:** `change_rule` does not move a rule. Reorder stays on its
     own route.
   - **The rule routes** call the service, and their responses are unchanged.
9. **Routines.** The `proposal` parameter of `AgentRoutineRepository.create`,
   `update` and `delete` is typed as a Protocol with one method, `async def
   run(conn, routine_id) -> None`. `ProposalOp` still satisfies it. Nothing
   else changes.
10. **New unit tests** (`tests/test_agent_service.py`,
    `tests/test_rules_service.py`), each falsified where noted:
    - `change_agent` writes only the named fields. A seeded agent with every
      field set keeps all the others, including `mcp_overrides` credentials,
      the switches, `kb_ids` and `secret_ids`. Falsify by building the body
      the PUT way.
    - Stale: a touched field changed since `base` raises `AgentStaleError`
      naming it, and nothing is written. Override applies. Falsify by
      skipping the compare.
    - Concurrent untouched write: a different field saved between load and
      save is kept. Simulate it through a seam, such as a patched `load` that
      saves before returning on the first attempt only, so the retry
      converges. Falsify by removing the retry.
    - A raise from `on_commit` rolls back the agent write. Falsify by moving
      `on_commit` after the transaction.
    - Each refused key gives its 422 `loc`.
    - The self-configuration surface id is carried, and is ignored in the
      `mcp_source_ids` comparison.
    - `create_rule` with `position=0` inserts first, with dense positions
      afterwards. The rule `precheck` and `on_commit` roll back on a raise.
    - The import-boundary test from criterion 2.
    - A concurrent `set_self_revision_requires_approval` or `set_notes_enabled`
      write between load and save is kept by `change_agent`.
    - A route still returns the identical 422 JSON for a pydantic failure with
      no `input` echo (`include_input=False` survives the move).
    - A create racing an existing name gets the 409 under the lock.
11. **The guard.** These are green with no change to an assertion:
    - the existing agent, rule and routine unit tests, and every test file
      that calls `/api/agents` (about 36 files);
    - `THE_ONE_TEST_NETNS=1 make test-unit`;
    - the browser lanes `agents`, `agent-tabs` and `agent-routines`.
12. **Docs.** `the_one/agents.md` names the two services, the save hooks and
    the error type in its module map and in the agent-write section. CLAUDE.md
    is unchanged, since nothing is operator-visible.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_agent_service.py tests/test_rules_service.py -x --timeout 30`
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh $(grep -rl '/api/agents' tests/*.py) -x --timeout 60`
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh $(grep -rlE 'interfaces\.web\.api\.|import api as|api\._' tests/*.py) -x --timeout 60`
  (the files that patch or import `api` internals)
- `THE_ONE_TEST_NETNS=1 make test-unit` (15 skipped expected under netns).
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents`,
  then `--lane agent-tabs` and `--lane agent-routines`, one at a time.
- `git diff --stat main -- tests/` shows only the two new test files. No
  existing test file changes.
- `ruff check` and `ruff format --check` on the touched files.

## Implementation Guidance
1. **Read first.** Read `create_agent`, `update_agent`,
   `update_agent_mcp_credentials` and `rename_agent` in `api.py`, and each
   helper they call. List which of them use api-module state (`_agent_store()`,
   `_mcp_repo()`, `_tool_config_rows`). Pass them into the services as an
   `AgentWriteDeps` that `api.py` builds from its own getters. The services
   never open a connection, never call `get_encryptor()`, and never reach
   back into `api.py`.
2. **Errors.**
   - Convert each moved helper's `raise HTTPException(status_code=S,
     detail=D)` to `raise AgentWriteError(S, D)`.
   - `reject_foreign_surface_attachments` returns a detail: raise it as a 422.
   - `_validation_detail` has one definition in `write_checks.py`, and `api.py`
     imports it under the same name for its other call sites.
   - Keep the exact detail objects.
3. **The route mapping.**
   - Add an `@contextmanager` in `api.py`, for example `_agent_write_errors()`,
     that turns `AgentWriteError` into `HTTPException`. Wrap the agent create
     and update routes and the rule routes with it.
   - For every moved helper name that other code in `api.py` still calls (the
     credentials route, rename), and for the two outside importers, keep a
     thin wrapper of the same name in `api.py` that calls the moved helper and
     maps the error.
4. **Services.** Build `create_agent` and `replace_agent` by moving the route
   bodies. Build `change_agent` on the same check sequence, starting from the
   stored row.
5. **Hooks.** Add the `AgentStore.save` hooks, then the rule repository's
   `position`, `precheck` and `on_commit`. For `position`, shift the
   positions of rules at or after it, then `_redensify` in the same
   transaction.
6. **Rules.** Write the rule service and point the rule routes at it.
7. **Routines.** Widen the routines `proposal` type.
8. **Tests.** Write the new tests and falsify each one marked above. Run the
   guard set, the unit tier and the three lanes.
9. **Docs.** Update `the_one/agents.md`.

## Edge Cases
- **A PUT body with `mcp_overrides` as a list** (not a dict) still reaches
  `AgentConfig` validation and gets today's 422.
- **`change_agent` on a missing agent** raises a 404-equivalent
  (`AgentWriteError(404, f"Agent not found: {name}")`, today's text).
- **A provider changed to one that does not exist** is the provider 422. A
  provider deleted earlier and left unchanged is not checked (squawk 0277
  behaviour).
- **Tool overrides:** `changes` cannot carry `tool_overrides` in Flight 2
  (DD2), but `change_agent` itself should still validate them the PUT way if
  passed, since it is a generic service. Only the four keys in criterion 5
  are refused.
- **`max_iterations` and other unbounded fields** keep the model's own rules.
  The stricter bounds of the change shape belong to Leg 2.
- **The precheck runs synchronously inside the transaction.** Load the
  comparison values before calling it, as the routines repository does with
  `cur_row`.
- **Rename** (`rename_agent`) keeps its current behaviour. It only switches to
  the moved `_checked_agent_name`.

## Files Affected
- `the_one/agent/service.py` (new), optionally `the_one/agent/write_checks.py`
  (new).
- `the_one/agent/rules_service.py` (new).
- `the_one/interfaces/web/api.py`: route bodies thinned, thin wrappers kept
  under the moved helper names, the error mapping added.
- `the_one/db/repositories.py`: `AgentStore.save` hooks; `AgentRuleRepository`
  `create`/`update` hooks and `position`.
- `the_one/routines/repository.py`: the `proposal` type Protocol.
- `tests/test_agent_service.py` and `tests/test_rules_service.py` (new).
- `the_one/agents.md`.

## Citation Audit
Checked against the working tree at `6f073dd4` (branch
`flight/02-proposals-and-approval`):
- `api.py::create_agent` L1477-1533: the order listed in AC3 matches the code
  line by line; save L1530; evict L1532 — verified.
- `api.py::update_agent` L1536-1635: the preserve list (`self_revision_requires_approval`,
  `notes_enabled`, `rich_visuals`, routines switches forced, `kb_ids`,
  `secret_ids`, `tool_overrides`); provider checked only when changed L1628;
  `_drop_surface_override(_merge_preserved_mcp_credentials(...))` L1574 — verified.
- Helper caller counts: `_validate_mcp_override_credentials` 3,
  `_merge_preserved_mcp_credentials` 4 (including `mcp_agent_test.py:120`),
  `_evict_changed_mcp_credentials` 3, `_checked_agent_name` 2 (create,
  rename) — verified with grep.
- `tests/test_self_configuration_agent_writes.py:233` imports
  `_normalize_surface_fields` from `api.py` — verified.
- `api.py` rule routes L2097-2150: `_rules_body`, `_load_agent_or_404`,
  `RuleLimitError` → 422 `e.detail`, `KeyError` → 404 "Rule not found" —
  verified.
- `repositories.py::AgentStore.save` L270: its own `write_transaction`, a full
  upsert — verified.
- `repositories.py::AgentRuleRepository` L1737: `create(name, text, enabled)`
  computes `MAX(position)+1` in its transaction; `update`, `reorder` and
  `_redensify` exist — verified.
- `routines/repository.py` L177, L259 and L301: `proposal: ProposalOp | None`;
  `update` re-reads `cur_row` and calls a sync `precheck(cur_row)` inside
  `write_transaction` (L265-269) — verified.
- `_write_lock.py` re-entry `RuntimeError` — verified.
- Design review (Developer, Sonnet), approve with changes:
  - The api getters (`get_connection` and `get_encryptor`, imported into
    `api`) are patched by about 10 test files, so the services take their
    dependencies as an argument.
  - `_validation_detail` has 19 call sites.
  - `AgentStore.save` does not write `routines_self_config_enabled`, and
    `routines_require_approval` is insert-only (it is not in the `ON CONFLICT
    DO UPDATE`).
  - `AgentStore` is a Protocol, implemented by `SQLiteAgentStore`.
  - The other `save` callers are listed in AC7.

  All folded in above.

---

## Post-Completion
Completion steps (status transitions, flight-log update, checking off in the
parent flight, and commit) are Flight Control protocol, driven by the execution
workflow. They are not repeated here.
