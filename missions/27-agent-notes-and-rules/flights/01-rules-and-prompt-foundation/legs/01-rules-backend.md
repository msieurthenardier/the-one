# Leg: rules-backend

**Status**: completed
**Flight**: [Rules and the Prompt Foundation](../flight.md)

## Objective

Store per-agent rules, compose every agent's system prompt from base, persona
and enabled rules through one shared path, serve rules over REST, and make
agent rename cascade through every agent-keyed table. That path also fixes the
two Known Issues the mission records.

## Context

- Flight design decisions **DD1** (composer), **DD2** (async loader, `next_turn`
  path, failure at settle), **DD3** (v42: `agent_rules` + the `agent_revisions`
  rebuild), **DD4** (limits), **DD5** (rules prompt text), **DD8** (REST) and
  **DD10** (test placement) govern this leg. Read them in
  [flight.md](../flight.md) first; this leg does not restate their rationale.
- Mission Known Issues 1 (rename fails with revision history) and 2 (a
  `next_turn` revision drops the base prompt) are closed by this leg.
- Leg 2 (`rules-ui`) builds the Studio tab and the drawer group on these
  routes. Keep the response shapes exactly as DD8 states.
- The prompt `notes` layer is a reserved, always-empty keyword in this flight.
  Flight 2 fills it.

## Inputs

- `main` at `77308c5` plus the planning commit `08db2cb`, on branch
  `flight/01-rules-and-prompt-foundation`.
- Schema at v41 (`the_one/db/schema.py::CURRENT_VERSION`).

## Outputs

- Migration v42 in `the_one/db/schema.py`, with `CURRENT_VERSION = 42`.
- A rules repository, beside `AgentRevisionRepository` in
  `the_one/db/repositories.py` (`AgentRuleRepository`), with the limit
  constants in one place.
- `the_one/agent/config.py::compose_system_prompt` extended, and
  `AgentConfig.get_system_prompt` removed.
- A new `the_one/agent/prompt_layers.py::build_system_prompt`.
- `AgentFactory.create` and `self_configuration/pending.py` wired through it,
  with the two `app.py` settle sites awaiting.
- REST routes in `the_one/interfaces/web/api.py`.
- Tests, plus `the_one/agents.md` updates.

## Acceptance Criteria

**Migration v42 (DD3)**
- [ ] AC1. A fresh database reaches v42 with an `agent_rules` table (columns,
      foreign key and index per DD3).
- [ ] AC2. A populated v41 database upgrades to v42 and keeps every
      `agent_revisions` row, including a `restored_from` chain, and the
      `idx_agent_revisions_agent_status` index. This is tested on two paths:
      - a fresh replay from v0 (v34 creates the table, v37 rebuilds it, v42
        rebuilds it again: the guard fires on every fresh install too);
      - a database stopped at v41 that already carries v37's
        `agent_revisions_new`-named self-reference.
- [ ] AC3. After v42, `PRAGMA foreign_key_list(agent_revisions)` shows:
      - the `agents` row with `on_update = CASCADE` and `on_delete = CASCADE`;
      - the `restored_from` row referencing table `agent_revisions` (not
        `agent_revisions_new`) with `on_delete = SET NULL`.
- [ ] AC4. Re-running `ensure_schema` on a v42 database changes nothing; the
      guard works.
- [ ] AC5. `SQLiteAgentStore.rename` succeeds for an agent that has both
      revision rows and rule rows, and both move to the new name. Before this
      leg, the same test fails with `FOREIGN KEY constraint failed` (Known
      Issue 1).
- [ ] AC6. `DELETE /api/agents/{name}` removes the agent's rules and revisions.
- [ ] AC7. `tests/test_schema_template.py`'s template-equals-fresh-replay
      check passes.

**Composition (DD1, DD2, DD5)**
- [ ] AC8. `compose_system_prompt(base, persona, *, rules=(), notes=())`
      returns the following, with no empty layer emitted, no stray separator,
      and output byte-identical to today's when `rules` and `notes` are empty:
      - `base`, then `---`, then the persona (when non-empty), then `---`, then
        the rules block (when `rules` is non-empty);
      - the rules block is the DD5 text plus the numbered rules (`1. …`).
- [ ] AC9. `build_system_prompt(agent_name, persona, *, conn=None)`:
      - loads only **enabled** rules, in `position` order;
      - uses `get_connection()` when `conn` is None;
      - returns base + persona (no rules) for an agent with no stored row.
- [ ] AC10. `AgentFactory.create` builds its prompt through
      `build_system_prompt`. A built agent's `messages[0]` holds the persona
      followed by its enabled rules in order, and no disabled rule's text.
- [ ] AC11. The chat-only degraded path keeps the rules: a degraded build's
      system content contains the rules block.
- [ ] AC12. `apply_pending_revision` is `async`. Applying a pending
      `system_prompt` yields a prompt that starts with `BASE_PROMPT` and
      contains the new persona and the agent's enabled rules (Known Issue 2).
      Both settle sites in `app.py` `await` it, keeping
      `session.agent_name or "default"`.
- [ ] AC13. If loading the rules raises inside `apply_pending_revision`:
      - it logs a warning, applies base + persona with no rules, and consumes
        the entry;
      - the calling turn still sends `done`.

      A test that forces the rules read to fail pins this.
- [ ] AC14. `AgentConfig.get_system_prompt` no longer exists. Its tests
      (`tests/test_config.py:229-243`, including the block's header comment and
      docstring, and `tests/test_factory.py:184`) are rewritten against
      `compose_system_prompt` or the built agent. The byte-identical tests at
      `test_config.py:280-290` keep covering AC8's "identical when empty".

**REST (DD4, DD8)**
- [ ] AC15. Every route in DD8 exists with the stated request and response
      shapes and status codes:
      - `GET` returns `{rules, limits: {rule_chars: 500, total_chars: 4000}}`;
      - `POST` returns 201;
      - `PUT /rules/order` takes an exact permutation, else 422;
      - a rule of another agent, or an unknown rule, is 404;
      - an unknown agent is 404.
- [ ] AC16. Limits are enforced:
      - a rule that is empty after trimming, or longer than 500 characters, is
        422;
      - a create or edit that would push the total of all the agent's rules
        (enabled or not) past 4,000 characters is 422;
      - each 422 carries a plain-language `detail` stating the limit and the
        attempted size;
      - toggling `enabled` never fails on a limit.
- [ ] AC17. `PUT /api/agents/{name}` (the General form) leaves rules untouched,
      and so does `POST /api/agents/{name}/rename`, apart from carrying them
      over.
- [ ] AC18. No agent-reachable tool or MCP source exposes a rules write.
      - A test asserts that a built agent's `registry.tool_names` contain no
        name with "rule" in it.
      - The self-configuration write tools are still exactly
        `update_my_description` and `update_my_system_prompt`.
      - `get_my_configuration` still returns the raw stored persona, not the
        composed prompt.

**Tests and gates**
- [ ] AC19. The tests that pinned Known Issue 2's raw-persona behaviour now
      expect the composed prompt, as an intended contract change, and await
      the async call:
      - `tests/test_self_configuration_write.py:235, 267, 292, 426-433`, and
        the paused test's call at `:528`;
      - `TestAC4HookRunsAtNonPausedSettleOnly` (`:502-560`).

      **Database handle in these tests (decided):** every test that reaches
      the recompose path uses the `isolated_db` fixture (`tests/conftest.py`,
      about `:306`: it points `settings.data_dir` at `tmp_path` and resets the
      `the_one.db.connection` singleton). Alternatively, monkeypatch
      `the_one.db.connection.get_connection`, the lazily imported target, never
      `surface.get_connection`, to return a template connection
      (`tests/_schema_template.py`).

      Seed rules where the test asserts the full composition, so it expects
      `BASE_PROMPT`, then the persona, then the rules block. The fallback path
      is pinned separately by AC13's dedicated test, with the rules read
      forced to fail. The pytest run already isolates `THE_ONE_DATA_DIR` to a
      temp dir (`tests/conftest.py:36`), so the operator's data is never
      touched either way.
- [ ] AC20. The rules reach the persisted session on both paths:
      - **Connector:** extend `tests/test_connectors_inbound.py`'s real-factory
        test (`:523-555`, a real `AgentFactory(store=agent_store)`, a patched
        `get_provider` and a real `chat_repo`). Seed rules on the agent, run
        `dispatch_inbound`, then decode `chat_repo.get(...).messages` and
        assert that element 0 carries the rules block in order, with no
        disabled rule.
      - **Web:** do not build a new `_process_and_broadcast` harness; the
        existing ones mock `_save_session_to_db`. Instead:
        1. build the agent through a real `AgentFactory.create` on a template
           database with rules seeded, and assert that `agent.messages[0]`
           carries them;
        2. assert that `encode_messages` and `decode_messages` round-trip that
           system message unchanged, since `_save_session_to_db` persists
           `encode_messages(agent.messages)` (`app.py:1621-1640`).

        The end-to-end web persistence is observed by the behavior test
        (`agent-rules-round-trip` step 3).
- [ ] AC21. `make test-unit` passes (expected skip count 10, or 12 under the
      known timing conditions; see CLAUDE.md). `ruff check` and
      `ruff format --check` are clean.
- [ ] AC22. `the_one/agents.md` gains a "Rules and prompt composition (M27 F1)"
      section covering:
      - the layer order and the rules text;
      - `build_system_prompt` and its failure fallback;
      - the v42 foreign-key cascade, and that new agent-keyed tables must use
        `ON UPDATE CASCADE`;
      - the REST routes and limits;
      - the known limitations from DD2:
        - an open conversation can pick up rules at a self-revision settle;
        - a rename during an open web conversation drops rules until rejoin;
        - a pending `next_turn` entry keyed under the old name goes stale
          across a rename.

## Verification Steps

- AC1-AC5, AC7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_migration.py tests/test_schema_template.py tests/test_repositories*.py -x --timeout 60`
  (adjust to wherever the store tests live).
- AC5: confirm the new rename test fails on `main`'s schema logic, by
  temporarily skipping the v42 rebuild in a scratch copy or by reasoning from
  the reproduced failure. Record the result in the flight log.
- AC8-AC14: `tests/test_config.py`, `tests/test_factory.py`, and a new
  `tests/test_prompt_layers.py`.
- AC12, AC13, AC19: `tests/test_self_configuration_write.py` (under
  `isolated_db`, or with `the_one.db.connection.get_connection` patched).
- AC15-AC18: a new `tests/test_agent_rules_api.py` using the existing
  authenticated test-client fixtures (`tests/_credential_helpers.py`).
- AC20: `tests/test_connectors_inbound.py` (connector), and
  `tests/test_prompt_layers.py` or `tests/test_factory.py` (web build plus
  codec round trip).
- AC21: `make test-unit`; `ruff check the_one/ tests/ scripts/`;
  `ruff format --check the_one/ tests/ scripts/`.

## Implementation Guidance

1. **Migration v42** (`the_one/db/schema.py`).
   - Append a `if version < 42:` block after v41 and set `CURRENT_VERSION = 42`.
   - `CREATE TABLE IF NOT EXISTS agent_rules (...)` per DD3, plus
     `CREATE INDEX IF NOT EXISTS idx_agent_rules_agent_position ON agent_rules (agent_name, position)`.
   - The `agent_revisions` rebuild:
     - Guard first on the table existing (`sqlite_master`), as v37 does at
       `schema.py:2172-2175`.
     - Then read `PRAGMA foreign_key_list(agent_revisions)` and rebuild only
       when the row whose `table` is `agents` has `on_update != 'CASCADE'`.
     - Copy the v37 `executescript` ceremony (`schema.py:2190-2220`). Add
       `ON UPDATE CASCADE` to `agent_name`, and declare `restored_from TEXT
       REFERENCES agent_revisions(id) ON DELETE SET NULL` (the **final** table
       name).
     - List all 11 columns explicitly in `INSERT ... SELECT`, including
       `source_principal`.
     - Recreate `idx_agent_revisions_agent_status`.
     - Run `PRAGMA foreign_keys=ON` after the script.
   - `INSERT OR IGNORE INTO schema_version` last, then commit.
   - There is **no separate fresh-install DDL**: `ensure_schema` runs
     `SCHEMA_V1`, then every `version < N` block, so the chain is the only
     path. v34 `agent_revisions` lives only in the chain
     (`schema.py:2041-2079`).

2. **Repository.** `AgentRuleRepository(conn)` in
   `the_one/db/repositories.py` provides:
   - `list_for_agent(name)`, ordered by `position`;
   - `get(name, rule_id)`;
   - `create(name, text, enabled)`, which appends at `MAX(position)+1`;
   - `update(name, rule_id, *, text=None, enabled=None)`;
   - `delete(name, rule_id)`, which re-densifies positions;
   - `reorder(name, ids)`, which rewrites positions densely in one
     `write_transaction`;
   - `total_chars(name)`.

   Ids are `uuid4().hex`, and timestamps use the repository's existing
   `now_iso()`. Enforce the limits in one helper the API calls, with constants
   `RULE_MAX_CHARS = 500` and `RULES_TOTAL_MAX_CHARS = 4000` in one module
   (e.g. `the_one/agent/rules.py`, which may also hold the DD5 heading text).

   **Transaction shape (decided).** `write_transaction` is not re-entrant: it
   raises on re-entry within a task (`the_one/db/_write_lock.py:65`). So:
   - Each mutating repository method (`create`, `update`, `delete`,
     `reorder`) opens **one** `write_transaction` itself. Inside it, the
     method reads (`total_chars`, the current ids), validates, and writes.
   - A limit violation raises a typed `RuleLimitError(detail)`. An invalid
     reorder raises `RuleOrderError(detail)`. A missing or foreign rule raises
     `KeyError`.
   - The route maps these to 422, 422 and 404.
   - A pure validation helper (text length after trimming) may run before the
     call. Nothing that opens a transaction may be called from inside one.

   **Positions are 0-based and dense:** after any delete or reorder they are
   `0..n-1`. A create on an empty list gets 0. A repository test pins
   this.

3. **Composer.** Extend `compose_system_prompt` per DD1 and DD5, render the
   numbered list, then delete `AgentConfig.get_system_prompt` and move its
   tests (AC14).

4. **Loader.** Write `the_one/agent/prompt_layers.py::build_system_prompt`
   (AC9). Import `get_connection` lazily inside the function, as
   `factory.create` does (`factory.py:313`), to avoid import cycles.

5. **Factory.** At step 3 (`factory.py:515`), replace the direct
   `compose_system_prompt` call with
   `await build_system_prompt(config.name, config.system_prompt, conn=conn)`.
   Check that `config.name` is the stored name (for the synthesized default it
   is `"default"` and has no rules, which is fine).

6. **Pending path.** Make `apply_pending_revision` `async`.
   - When the entry has `system_prompt`, compute
     `await build_system_prompt(agent_name, entry_prompt)` inside
     `try/except Exception`. On failure, log a warning and fall back to
     `compose_system_prompt(BASE_PROMPT, entry_prompt)`.
   - Assign `agent.system_prompt` and `messages[0]`.
   - Update both `app.py` call sites to `await`.
   - Update the module docstring.

7. **REST routes** in `api.py`, beside the self-configuration routes, under
   `# ── Rules (M27 F1) ──`.
   - Follow `_agent_revisions_repo()`'s accessor pattern.
   - 404 for an unknown agent through `store.load`.
   - Use pydantic request models, or explicit parsing with
     `_validation_detail` for 422s, matching nearby routes.
   - Never echo request bodies in errors beyond the sizes.

8. **Tests** per the Verification Steps. Build databases from the schema
   template (`tests/_schema_template.py`). Only the migration test calls
   `ensure_schema` directly, and it lives in `tests/test_db_migration.py`, which
   is already allowed.

9. **Docs** (AC22). Also tick nothing in the mission. The Flight Director
   updates the mission's Known Issues at flight landing.

## Edge Cases

- **Persona empty, rules present:** base, `---`, rules block.
- **All rules disabled:** no rules layer, and output identical to having no
  rules.
- **A rule containing a newline:** allowed, rendered as-is after its number. Do
  not renumber or wrap lines.
- **Reorder with duplicate, missing or foreign ids:** 422, and no write.
- **Deleting the last rule:** the list is empty, and the next create gets
  position 0 (0-based, dense).
- **Concurrent creates near the cap:** the cap check and insert share one
  transaction.
- **Agent renamed while a pending `next_turn` entry exists:** keyed by the old
  name. Accepted (DD2, documented).
- **The degraded path** relies on `system_prompt.startswith(BASE_PROMPT)`
  (`core.py:459`). Never put anything before the base.

## Files Affected

- `the_one/db/schema.py`: v42, `CURRENT_VERSION`.
- `the_one/db/repositories.py`: `AgentRuleRepository`.
- `the_one/agent/rules.py` (new): limits and rules heading text.
- `the_one/agent/config.py`: `compose_system_prompt`; remove
  `get_system_prompt`.
- `the_one/agent/prompt_layers.py` (new): `build_system_prompt`.
- `the_one/agent/factory.py`: step 3.
- `the_one/self_configuration/pending.py`: async plus recompose.
- `the_one/interfaces/web/app.py`: two `await`s.
- `the_one/interfaces/web/api.py`: rules routes.
- `tests/test_db_migration.py`, `tests/test_config.py`, `tests/test_factory.py`,
  `tests/test_self_configuration_write.py`, `tests/test_prompt_layers.py`
  (new), `tests/test_agent_rules_api.py` (new), plus the web-turn and connector
  test files extended for AC20.
- `the_one/agents.md`.

## Citation Audit

Checked against the working tree at `08db2cb`:
- `compose_system_prompt` is at `config.py:82`, and `get_system_prompt` at
  `config.py:193`.
- Factory step 3 is at `factory.py:515`.
- `apply_pending_revision` is at `pending.py:75`. Its callers are
  `app.py:2422` and `:2496`, plus tests at `test_self_configuration_write.py`
  235, 267, 292, 426 and 528.
- `get_system_prompt` is called in tests at `test_config.py:238` and `:242`,
  and `test_factory.py:184`.
- The v37 ceremony is at `schema.py:2170-2220`.
- `AgentRevisionRepository` is at `repositories.py:1517`, and
  `_agent_revisions_repo` at `api.py:374`.
- `delete_agent` is at `api.py:933`, and `rename_agent` at `api.py:948`.

All were verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
