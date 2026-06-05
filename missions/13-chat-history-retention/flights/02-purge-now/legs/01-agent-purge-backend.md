# Leg: agent-purge-backend

**Status**: completed
**Flight**: [Purge Now](../flight.md)

## Objective

Add an agent-wide chat-history purge primitive — `ChatSessionRepository.delete_all_for_agent(agent_name) -> int` — and expose it as `DELETE /api/agents/{name}/chat/sessions` returning `{"status": "ok", "deleted": N}`, with unit tests pinning the connector sweep, cross-agent isolation, count, empty no-op, and rename-then-purge composition.

## Context

- **Flight DD1** — endpoint keyed by **agent name** (no agent id exists; `agents.name` is the PK at `db/schema.py:47`, and every agent route is `/agents/{name}`). The delete runs `DELETE FROM chat_sessions WHERE agent_name = ?` and returns a count. **No existence-404** — the operation is idempotent and also clears sessions orphaned by a prior agent deletion.
- **Flight DD2** — no schema change, no migration. Pure row deletion. The FK on `chat_sessions.agent_name` was dropped at schema v5, so on any running DB (version ≥ 5) the delete neither cascades nor is blocked.
- **Rename safety** — `SQLiteAgentStore.rename()` re-points `chat_sessions.agent_name` in the same transaction (`db/repositories.py:217-225` — the `UPDATE chat_sessions SET agent_name = ? WHERE agent_name = ?`). A name-keyed purge therefore always targets the renamed agent's sessions. Pinned by the rename-then-purge composition test below.
- **Connector sweep** — connector-originated conversations are `chat_sessions` rows with `agent_name` set (`connectors/_session.py:181-195`), so the single `WHERE agent_name = ?` delete removes them too (mission criterion 5).
- This is Leg 1 of 2. Leg 2 (`purge-now-button`) wires the frontend to this endpoint; it depends on this endpoint's path and response shape (`{"status": "ok", "deleted": N}`).

## Inputs

What exists before this leg runs:
- `ChatSessionRepository` at `the_one/db/repositories.py:909` with `list`, `get`, `create`, `update`, `delete(session_id)` (`:1030`), `purge_messages`, etc. No agent-wide delete primitive.
- The chat-session API routes at `the_one/interfaces/web/api.py:3597-3667` (`router = APIRouter(prefix="/api")` at `:49`); the per-session `DELETE /chat/sessions/{session_id}` is at `:3649`. Agent routes are at `:387-578` (`DELETE /agents/{name}` at `:509`).
- The `_chat_repo()` helper (used by every chat-session route, e.g. `:3599`).
- Existing tests: `tests/test_db_repositories.py::TestChatSessionRepository` (`:2388`) and `tests/test_db_api.py::TestChatSessionAPI` (`:2746`).

## Outputs

What exists after this leg completes:
- `ChatSessionRepository.delete_all_for_agent(agent_name: str) -> int` in `the_one/db/repositories.py` (placed adjacent to `delete(session_id)` at `:1030`).
- `DELETE /agents/{name}/chat/sessions` route in `the_one/interfaces/web/api.py` returning `{"status": "ok", "deleted": N}`.
- New repo tests in `tests/test_db_repositories.py::TestChatSessionRepository`: connector-keyed sweep, cross-agent isolation, count, empty no-op, rename-then-purge composition.
- New API test in `tests/test_db_api.py::TestChatSessionAPI`: endpoint returns `{status, deleted:N}` with the correct count.

## Acceptance Criteria
- [x] `ChatSessionRepository.delete_all_for_agent(agent_name)` exists, deletes every `chat_sessions` row with that `agent_name` (interactive **and** connector-keyed), and returns the number of rows deleted (`cur.rowcount`).
- [x] The method leaves another agent's sessions completely untouched (cross-agent isolation).
- [x] The method returns `0` (no error) when the agent has no sessions.
- [x] `DELETE /api/agents/{name}/chat/sessions` returns HTTP 200 with body `{"status": "ok", "deleted": N}` where `N` matches the number of rows removed; it does **not** 404 for an agent with no sessions.
- [x] A rename-then-purge composition test passes: an agent with both an interactive and a connector-keyed session is renamed, then purged **by the new name**, leaving zero sessions for the new name and a second agent's session intact.
- [x] All new and existing tests in `tests/test_db_repositories.py` and `tests/test_db_api.py` pass; `ruff check` + `ruff format --check` clean on touched files.

## Verification Steps
- `docker exec the-one pytest tests/test_db_repositories.py -x --timeout 30 -q` — repo tests pass (including connector sweep, isolation, count, empty no-op, rename-then-purge). *(Direct `docker exec the-one pytest` per the crew Implement prompt; the `make test-unit` / `scripts/run-tests.sh` wrapper exists to process-group-reap browser subtrees, which these pure DB/API suites never spawn, so direct pytest is equivalent here. Run the broader suite once at leg-end.)*
- `docker exec the-one pytest tests/test_db_api.py -x --timeout 30 -q -k ChatSessionAPI` — endpoint test passes.
- `docker exec the-one ruff check the_one/db/repositories.py the_one/interfaces/web/api.py tests/test_db_repositories.py tests/test_db_api.py` — clean.
- `docker exec the-one ruff format --check the_one/db/repositories.py the_one/interfaces/web/api.py tests/test_db_repositories.py tests/test_db_api.py` — clean.

## Implementation Guidance

1. **Add the repository method** in `the_one/db/repositories.py`, immediately after `delete(session_id)` (`:1030-1037`):
   ```python
   async def delete_all_for_agent(self, agent_name: str) -> int:
       """Delete every chat session for an agent (interactive AND
       connector-keyed) and return the number of rows removed.

       Name-keyed (agents have no id column; agents.name is the PK).
       Idempotent: returns 0 for an agent with no sessions and never
       raises for a missing agent — the FK was dropped at schema v5,
       so this neither cascades nor is blocked. Rename-safe because
       rename() re-points chat_sessions.agent_name in one transaction.
       """
       async with self.conn.execute(
           "DELETE FROM chat_sessions WHERE agent_name = ?", (agent_name,)
       ) as cur:
           count = cur.rowcount
       await self.conn.commit()
       return count
   ```
   - **Why capture the cursor**: the sibling `delete()` at `:1030` does not capture the cursor because it needs no count. Here we read `cur.rowcount` (populated by aiosqlite/sqlite3 for a DELETE) for the returned count — a small, deliberate extension of the house `async with self.conn.execute(...) as cur:` idiom already used by `list`/`get`/`update`.
   - Do **not** add a pre-flight existence SELECT — DD1 specifies no existence check (idempotent, also clears orphaned sessions).

2. **Add the API route** in `the_one/interfaces/web/api.py`, near the chat-session routes (after the per-session delete at `:3649-3657`):
   ```python
   @router.delete("/agents/{name}/chat/sessions")
   async def delete_agent_chat_sessions(name: str) -> dict[str, Any]:
       repo = await _chat_repo()
       deleted = await repo.delete_all_for_agent(name)
       return {"status": "ok", "deleted": deleted}
   ```
   - Mirror the existing route style (`_chat_repo()` access, plain dict return). Return type is `dict[str, Any]` because the body mixes `str` and `int` (the per-session delete returns `dict[str, str]`; this one cannot).
   - No `try/except KeyError` / 404 — the method never raises for a missing agent (DD1).
   - **Route placement / no conflict**: `/agents/{name}/chat/sessions` does not collide with `DELETE /agents/{name}` (`:509`) — distinct path suffix. Placing it with the chat-session routes keeps purge logic together; placing it with the agent routes is an acceptable variation.

3. **Add repo tests** to `tests/test_db_repositories.py::TestChatSessionRepository` (`:2388`), following the existing fixtures (`agent_store`, `chat_repo`) and the connector-keyed construction pattern at `test_create_and_get_with_connector_identity` (`:2472`):
   - `test_delete_all_for_agent_sweeps_interactive_and_connector` — save agent `a1`; create one plain `ChatSession` and one with `platform="discord", connector_id="acc-1", channel_id="ch-1"`; assert `delete_all_for_agent("a1")` returns `2` and `list(agent_name="a1")` is empty.
   - `test_delete_all_for_agent_leaves_other_agents` — sessions for `a1` and `a2`; purge `a1`; assert `a2`'s session survives.
   - `test_delete_all_for_agent_empty_is_noop` — save agent with no sessions; assert returns `0`, no error.
   - `test_rename_then_purge_composition` — save `a1`; create interactive + connector-keyed sessions for `a1`; save bystander `a2` with one session; `await agent_store.rename("a1", "a1-renamed")`; assert `delete_all_for_agent("a1-renamed")` returns `2`; assert **both** `list(agent_name="a1-renamed")` **and** `list(agent_name="a1")` are empty (locks the re-point direction — the old name resolves to zero sessions because the cascade moved them, not because they were deleted under the old name); assert `a2`'s session intact. (Uses `SQLiteAgentStore.rename`, whose cascade is at `repositories.py:217-225`.)

4. **Add API test** to `tests/test_db_api.py::TestChatSessionAPI` (`:2746`), following the `client`-fixture style of `test_crud` (`:2747`):
   - `test_delete_agent_chat_sessions_returns_count` — POST agent `a1`; POST two sessions for `a1`; `DELETE /api/agents/a1/chat/sessions`; assert 200 and body `{"status": "ok", "deleted": 2}`; then `GET /api/chat/sessions?agent_name=a1` returns `[]`. **Required**: also assert the no-session case — `DELETE /api/agents/<agent-with-no-sessions>/chat/sessions` returns 200 with `{"deleted": 0}` and does **not** 404 (pins DD1 idempotency at the HTTP layer, not just the repo layer).

5. **Run** `make rebuild` if needed so the container reflects the source edits, then the touched unit suites (Verification Steps). Run `ruff check` + `ruff format --check` on all touched files (M12 CI gate).

## Edge Cases
- **Agent with no sessions** → `delete_all_for_agent` returns `0`; endpoint returns `{"deleted": 0}`, **not** 404 (DD1 idempotency).
- **Orphaned sessions** (agent already deleted, sessions survive per v5) → still purgeable by name; this is intended (DD1).
- **`rowcount` semantics** → for a DELETE, aiosqlite/sqlite3 populates `cur.rowcount` with the affected row count; it is read **before** `commit()` while the cursor is open. (New to this repo but valid.)
- **In-memory `_sessions` not evicted** (DD2a) — this leg is DB-only by design; live-session eviction is explicitly out of F2 scope. Not a code concern for this leg, noted so a reviewer doesn't flag it as a gap.

## Files Affected
- `the_one/db/repositories.py` — add `delete_all_for_agent` after `:1030`.
- `the_one/interfaces/web/api.py` — add `DELETE /agents/{name}/chat/sessions` route near `:3649`.
- `tests/test_db_repositories.py` — add 4 tests to `TestChatSessionRepository`.
- `tests/test_db_api.py` — add 1 test to `TestChatSessionAPI`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** *(Note: under `/agentic-workflow`, commit is deferred to flight review — do NOT commit at leg end. Mark the leg `landed`, update the flight log, and hand off.)*

- [x] All acceptance criteria verified
- [x] Tests passing (`test_db_repositories.py`, `test_db_api.py`); `ruff` clean
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT commit (flight-level review + commit happens after the last autonomous leg)
- [x] Signal `[HANDOFF:review-needed]`

## Citation Audit

7 citations verified against current code at leg design time:
- `db/repositories.py:909` (`class ChatSessionRepository`) — OK.
- `db/repositories.py:1030` (`async def delete(self, session_id)`) — OK.
- `db/repositories.py:217-225` (rename cascade `UPDATE chat_sessions SET agent_name = ?`) — OK (the UPDATE statement is at `:223`, inside the single-transaction `rename()` at `:209-226`).
- `interfaces/web/api.py:49` (`router = APIRouter(prefix="/api")`) — OK.
- `interfaces/web/api.py:3597-3667` (chat-session routes; per-session DELETE at `:3649`) — OK.
- `interfaces/web/api.py:509` (`DELETE /agents/{name}`) — OK.
- `tests/test_db_repositories.py:2388` (`TestChatSessionRepository`), `:2471` (connector-keyed construction `test_create_and_get_with_connector_identity`); `tests/test_db_api.py:2746` (`TestChatSessionAPI`), `:2747` (`test_crud`) — OK.

Note: the flight spec cites `api.py:3649` and `repositories.py:1030` against the file root; the project layout places these at `the_one/interfaces/web/api.py` and `the_one/db/repositories.py` respectively — line numbers confirmed against those files.
