# Leg: cascade-delete-and-orphan-purge

**Status**: completed
**Flight**: [Deleting an agent deletes its chats](../flight.md)

## Objective
`DELETE /api/agents/{name}` removes the agent, all its chats and everything keyed to them in one transaction. It stops, tells and evicts any open session, and scrubs the deleted content from the database files. Schema v57 purges chats already orphaned by earlier deletions.

## Context
- Read the flight's DD1, DD2, DD3, DD4, DD7 (its last bullet only) and DD9 first. They are the design; this leg implements them. Its two Architect review cycles are in the flight log.
- This reverses schema v5's decision that chats survive agent deletion (`the_one/db/schema.py`, the `if version < 5` comment). Tests that pin "chats survive" are **rewritten in place to pin the new behaviour** (rename the test where its name states the old behaviour; do not delete and re-add).
- Leg 2 (the dialog) depends on this leg's response field `chats_deleted`.
- The working tree is the worktree `/home/cprch/projects/the-one-sortie-20` with its own `.venv`. Never touch `/home/cprch/projects/the-one`.

## Inputs
- `main` at `c3df3d73` plus the design commit `8decdebf`. Nothing uncommitted except the Flight Director's artifact edits under `sorties/20-*`.
- The key files: `the_one/db/repositories.py` (`SQLiteAgentStore.delete`, `.rename`, `ChatSessionRepository.delete_all_for_agent`); `the_one/agent/store.py` (`AgentConfigStore`); `the_one/interfaces/web/api.py` (`delete_agent`); `the_one/interfaces/web/app.py` (`_run_purge_sweep_and_evict`, the socket `cancel` action, `_notify_cancelled_once`, `_cancel_tokens`, `_session_inflight`, `_sessions`, `_sessions_lock`, `session_locks`); `the_one/sessions/_broadcast.py`; `the_one/tools/_session_registry.py` (`list_for_agent`, `close`); `the_one/db/schema.py`; `the_one/db/connection.py`; `tests/_schema_template.py`.

## Outputs
- The cascade, the route, the shared eviction helper, connector clearing, v57, `secure_delete` and the checkpoints, as listed in the Acceptance Criteria.
- Unit tests; the lane `chats` browser tests moved off agent deletion; `the_one/agents.md` and `SECURITY-MODEL.md` updated.
- No change under `the_one/interfaces/web/static/`.

## Acceptance Criteria

**Store (DD1, DD3)**
- [ ] **AC1.** `SQLiteAgentStore.delete(name)` runs one `write_transaction` that:
  - raises `KeyError` for a missing agent, before any write;
  - deletes the `gleepglorp_proposals` and `gleepglorp_fills` of the agent's chats, then the agent's `chat_sessions` rows (interactive and connector-keyed);
  - removes the `connectors.config.default_agent` key where it equals the name, and drops `channel_map` entries whose value is the name, leaving other connectors and other entries byte-identical;
  - deletes the `agents` row.

  It returns the deleted chat ids (`list[str]`). `AgentConfigStore.delete` and `tests/test_factory.py:47`'s fake declare the same return type. `FilesystemConfigStore` is unchanged.
- [ ] **AC2 (cascade).** After deleting an agent that had two chats (one with a GleepGlorp proposal and a fill), a rule, a note, a routine with a finished run, a routine proposal and a connector binding: none of those rows remain. Another agent's chats, rules, routine and connector binding, and GleepGlorp's own chats, are untouched.
- [ ] **AC3 (atomicity).** If any statement inside the transaction fails (simulate it by making the connector update raise; it is the last statement before the `agents` delete), the agent row, its chats and the connector config are all unchanged afterwards, and the error propagates.
- [ ] **AC4 (rename unchanged).** The existing rename tests pass unchanged: rename still carries chats.

**Route and eviction (DD2)**
- [ ] **AC5.** `DELETE /api/agents/{name}` returns `{"status": "ok", "chats_deleted": N}` and keeps 404 for a missing agent. The existing `cascade_delete` and `_evict_agent_connections` calls stay.
- [ ] **AC6.** A shared helper in `app.py` (name at the Developer's discretion) takes chat ids. For each id, in this order:
  1. it cancels in-flight tasks through a shared cancel function, which the socket's `cancel` action is refactored to call.
     - Signature: `(session_id, session | None)`. It uses only module globals (`_session_inflight`, `_cancel_tokens`, `_running_tasks`, `_started_tasks`) and returns the cancelled batch.
     - Steps: set the cancel token first, call `t.cancel()` on not-done tasks, then call `_notify_cancelled_once(session)` when nothing had started. That notify is skipped when `session` is `None`.
     - The socket passes its bound `session`. The eviction helper reads `_sessions.get(sid)` before any pop and passes that.
     - **Only the eviction helper** then awaits a bounded `asyncio.wait(batch, timeout=…)`. The socket path does not wait, so its timing is unchanged.
     - The task's done callback (`app.py` around `:1519-1520`) still clears the token.
  2. it broadcasts `{"type": "session_deleted", "session_id": sid}` with `broadcast_to_session`;
  3. it evicts (pops `_sessions` under `_sessions_lock`, then `session_locks.pop` and `agent.aclose()` outside it).

  `_run_purge_sweep_and_evict` calls the same helper; its log line and return value are unchanged. The socket's `cancel` behaviour is unchanged (its existing tests pass).
- [ ] **AC7.** The route calls the helper with the returned ids and calls `notify_sessions_changed()` once if any chat was deleted (not once per chat; the store must not notify inside the transaction). It closes every PTY session from `_session_registry.list_for_agent(name)`.
- [ ] **AC8 (live chat).** A test with a cached session for the agent and an in-flight task registered for it shows, after the delete:
  - the task was cancelled;
  - a subscriber received `session_deleted`;
  - the id is no longer in `_sessions` or `session_locks`;
  - `aclose` was awaited.

  A test with no cached session and no tasks shows the helper is a no-op that does not raise.

**Migration (DD4)**
- [ ] **AC9.** `CURRENT_VERSION` is 57. The `if version < 57:` block:
  - deletes orphan chats (the flight's exact `NOT EXISTS` predicate, excluding `'GleepGlorp'`, including `agent_name IS NULL`) and their GleepGlorp proposals and fills first;
  - is table-guarded as DD4 states;
  - stamps 57 and commits;
  - then runs `PRAGMA wal_checkpoint(TRUNCATE)`, tolerating busy or errors with a log line;
  - imports nothing live.
- [ ] **AC10.** A migration test seeds a v56 database with:
  - an orphan chat with a proposal and a fill;
  - a chat with `agent_name` NULL;
  - a live agent's chat;
  - a GleepGlorp chat;
  - an `agents` row whose name is NULL.

  After `ensure_schema`, only the orphan and NULL chats and their proposal and fill are gone. A database with no `gleepglorp_*` tables migrates without error.
- [ ] **AC11.** Every exact pin that equals `CURRENT_VERSION` (56) moves to 57.
  - `tests/test_gleepglorp_fill_store.py:58`.
  - In `tests/test_db_migration.py`: `:5035`, `:5391`, `:5537`, `:5678`, `:5684`, `:5817`, `:5969`, `:6016`, `:6375`, `:6388`, `:6580`, `:6875`, `:7083`, `:7133`, `:7155`, `:7165`, `:7283`, `:7373`.
  - **Not** `:7419` (`COUNT(*) … WHERE version = 56 == 1`): v56 still exists. Check it, but do not edit it blindly.
  - The `TestSchemaV56` rewind (around `:7269`, `DELETE … WHERE version >= 56`) and its comments saying "the template is v56" are reworded to fit.
  - Before editing, grep `tests/` for other `== 56` and `CURRENT_VERSION`-derived values.

  Full-replay tests that seed chats for agents with no `agents` row will see v57 purge them. Each one either seeds the agent row (when its subject is something else) or asserts the purge (when its subject is the chat). Record which, per test, in the flight log:
  - `tests/test_db_migration.py` around `:1959-1985` (`seeded-session` for `test-agent`).
  - The v53 `_seed` (around `:7015-7023`, which seeds `s-null`, `s-default`, `s-Default`, `s-research`, `s-gleep`) feeds `test_v52_database_loses_the_default_agent_and_its_data` (asserts `["s-Default","s-research"]`, `:7058`) and `test_a_live_gleepglorp_agents_chats_survive` (`:7093`). `s-Default` is the subject v53 keeps, so seeding a `Default` agents row is the expected fix.
  - Check `:2973` (`agent-1`, probably seeded) and `tests/test_name_repair.py:228` (a `Default` chat).

  `tests/test_schema_template.py` passes.

**Scrub (DD9)**
- [ ] **AC12.** `the_one/db/connection.py` sets `PRAGMA secure_delete=ON` beside its existing pragmas, and `tests/_schema_template.py` sets it on all three connection builders. Tests read `PRAGMA secure_delete` as 1:
  - on `get_connection()`;
  - on a template connection, asserted in `tests/test_schema_template.py` beside its existing `PRAGMA foreign_keys` assertion (around `:82`).

  Ad hoc `aiosqlite.connect(` in individual test files (migration replays, `fresh_db` and the like) are exempt: they never run the app's delete paths.
- [ ] **AC13.** After the store transaction commits, the route runs `PRAGMA wal_checkpoint(TRUNCATE)` through a checkpoint helper.
  - The helper runs it in its own, sequential `write_transaction` block, and consumes the cursor: `async with conn.execute(...) as cur: row = await cur.fetchone()`. An unfinalized statement can pin the snapshot and cause a busy result.
  - It returns `row[0]` (busy).
  - A busy result or an exception is logged and never fails the delete.
  - A 404 delete (missing agent) does not run the checkpoint.
- [ ] **AC14 (raw bytes).** The flight's checkpoint test runs the store delete plus the same checkpoint helper the route uses (the preferred apparatus; it needs no app lifespan). It uses the `isolated_db` fixture (`tests/conftest.py`, around `:358`): it points `settings.data_dir` at `tmp_path`, copies the template and resets the connection singleton, so `get_connection()` opens a fresh WAL connection on a private file. Do not use the process-wide default data directory: this worktree's unit tier has no per-worker directories. Steps:
  1. A unique **ASCII** marker (JSON may escape non-ASCII) is in a **non-first** message's text, with an explicit chat title, so it cannot also land in an auto-generated title.
  2. the marker is present in the `.db` or `-wal` bytes before the delete;
  3. the agent is deleted through the route (or the store plus the same checkpoint helper the route uses);
  4. the checkpoint reported `busy == 0`;
  5. the marker is absent from both files.

  Read the bytes with plain `open()` while the connection is still open. `close_connection()` checkpoints and removes the `-wal`. The `-shm` holds no page data and is not scanned. It must be deterministic. If it proves flaky, say so; do not loosen it into vacuity.

**Tests and documents**
- [ ] **AC15.** Tests that pinned "chats survive agent deletion" are rewritten in place to pin the cascade: `tests/test_db_repositories.py` around `:2086-2105`, `tests/test_schema.py` around `:360-409` (if it is a v5 migration test, leave the v5 assertion and confirm only that v57 is what removes orphans later). Re-check, and update only where they break: `tests/test_session_lifecycle.py`, `tests/test_session_joined_payload.py`, `tests/test_ws_start_session.py`, `tests/test_last_usage_round_trip.py`, `tests/test_routines_runner.py`, `tests/test_retention.py`, `tests/test_db_api.py`, `tests/test_self_configuration_external.py`, `tests/test_mcp_pool_resolve.py`. Tests that reach the `agent_deleted` state by deleting an agent now reach it by creating a chat for a never-existing agent name (DD7).
- [ ] **AC16.** Lane `chats` browser tests that deleted an agent over HTTP to reach the deleted-agent state (`test_flow_chat_composer_library.py`, `test_flow_chat_drawer.py`, `test_flow_chat_pane.py`, `test_flow_chat_session_state.py`, `test_flow_chat_list.py`, `test_flow_chat_proposals.py`, `test_flow_chat_start_flow.py`, `test_flow_chat_picker.py`. Some may delete through a helper, so grep every lane for others that send `DELETE` to `/api/agents/` in any spelling. Run the owning lane of each file touched; `--list` shows which lane owns it) instead create a chat for a name that never existed (`POST /api/chat/sessions`). Each test still asserts what it asserted before. Tests that delete an agent through the UI (lanes `agents` and `routing`) are leg 2's and are not touched here.
- [ ] **AC17 (documents).**
  - `the_one/agents.md`:
    - the text saying agent delete leaves sessions in place (around `:2811`, `:2829-2833`) states the cascade, the eviction order, `chats_deleted`, connector clearing, v57 and DD9;
    - the deleted-agent states (around `:1843`, `:1892`) say they are now reached only by the two races in DD7;
    - DD2's accepted connector-turn gap is stated.
  - `SECURITY-MODEL.md`, beside the agent-delete cascade text (around `:439`, `:460`): the three statements of the flight's DD8, including the out-of-scope remnants.
- [ ] **AC18 (gates).** Green:
  - `THE_ONE_TEST_NETNS=1 make test-unit` with the expected skip count (15 under the namespace);
  - the lane `chats` and the owning lane of every other browser file touched (`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>`), one at a time, alone on the host. In this worktree `make test-unit` runs serially (the xdist change is on Mission 37's unmerged branch), so allow about 300 s or more.
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`.

## Verification Steps
- AC1 to AC4, AC9 to AC14: new or rewritten unit tests. Build databases through `tests/_schema_template.py` (never `ensure_schema(` or `init_db(` directly outside the allowlisted migration-replay files); use `tests/_api_app.py::shared_app()` for route tests; use `FakeLLM` and `StubTool`, with no mock libraries beyond `monkeypatch`.
- AC5 to AC8: route tests through the shared app. For AC8, seed `_sessions` and `_session_inflight` directly (follow the existing purge-eviction tests for the pattern, grep `_run_purge_sweep_and_evict` in `tests/`), and subscribe a fake socket through `the_one/sessions/_broadcast.py`'s subscribe API.
- **Falsification** (report yes or no for each). Edit the mechanism out, see the named test fail, edit it back:
  1. drop the `chat_sessions` delete from the store method → AC2 fails;
  2. move the connector update outside the transaction → AC3 fails;
  3. replace `NOT EXISTS` with `NOT IN (SELECT name FROM agents)` → AC10 fails (because of the NULL-named agent row);
  4. remove the `'GleepGlorp'` exclusion → AC10 fails;
  5. remove the `secure_delete` pragma from `connection.py` → AC14 fails at step 5 (if WAL alone happens to scrub the marker, say so and show which step catches it instead);
  6. skip the broadcast in the helper → AC8 fails.
- AC16: the lane `chats`, alone on the host.
- AC18: the unit tier, then the lane, then the lint pair, never concurrently.

## Implementation Guidance
1. **Store**: the new statements go into `SQLiteAgentStore.delete` inside its existing `write_transaction`. Reuse the SQL of `delete_all_for_agent` and the connector loop of `rename` (`repositories.py:532-553`), with "remove the key" in place of "set to new name". `delete_all_for_agent` itself cannot be called inside (the lock is not re-entrant), and it stays for the Purge route.
2. **Helper**: factor the socket's cancel body (`app.py` around `:4066-4079`) into a module-level `async` function taking a session id; the socket calls it with its bound session's id. Then write the eviction helper around it and the existing eviction half of `_run_purge_sweep_and_evict`. The route imports it lazily, as `api.py` already does for `app._sessions` (grep `from the_one.interfaces.web.app import` in `api.py`).
3. **Checkpoint helper**: one small `async` function (in `the_one/db/connection.py` or a sibling, at the Developer's choice). It runs the pragma inside its own `write_transaction`, consumes the cursor, returns the `busy` value, and logs and swallows errors. `write_transaction` issues no `BEGIN`, and Python 3.12's legacy isolation opens a transaction only before DML, so after the delete block's commit no transaction is open. The route uses the helper; AC14 asserts its result. The v57 block runs the pragma directly after its commit: `init_db()` runs it at startup before any task, and on `:memory:` or DELETE-mode connections it is a no-op returning `(0, -1, -1)`.
4. **v57**: add it after the v56 block in the same style as v53. Bump `CURRENT_VERSION`.
5. **PRAGMA placement**: `connection.py` sets `secure_delete` next to `foreign_keys`; the template's three builders likewise.
6. **Out of scope**: the Purge route `DELETE /agents/{name}/chat/sessions` does not get the eviction helper (it is not this sortie's charter). If its lack of eviction looks like a defect, note it in the flight log for a squawk; do not fix it here.
7. Then tests (Verification), the lane `chats` moves, the documents, the gates.

## Citation Audit
Checked against the worktree at `8decdebf`:
- `api.py::delete_agent` (`:1253-1266`), `repositories.py::SQLiteAgentStore.delete` (`:447-451`), `rename`'s connector loop (`:532-553`), `delete_all_for_agent` (`:3510-3539`);
- `app.py`: `_cancel_tokens` (`:1006`), `_notify_cancelled_once` (`:1021`), `_register_turn_task` (`:1502`), `_run_purge_sweep_and_evict` (`:1727-1760`), the socket cancel (`:4066-4079`);
- `_session_registry.py`: `close` (`:125`), `list_for_agent` (`:155`);
- `schema.py`: the v56 block ending `version = 56` (`:3612-3627`).

All are present as cited. The `test_db_migration.py` line numbers come from the Architect and are re-located by the Developer.
