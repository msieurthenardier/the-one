# Leg: inbound-dispatcher

**Status**: completed
**Flight**: [Session Model — Schema, Key Normalization, Visibility](../flight.md)

## Objective

Compose pool acquire + session resolver + per-session lock + `agent.step()` into a single end-to-end inbound dispatcher in a new `the_one/connectors/_inbound.py` module. The dispatcher is the contract F8 (Discord) will satisfy when it replaces the F1 stub-driven inbound with a real gateway-driven inbound. F3 L4 also ratifies the F1 `last_activity` carry-forward by acquiring-per-inbound from the connector pool — no `touch_activity` API; the existing `acquire()` already touches the field on every call.

## Context

- **Parent flight design decisions** (see `flight.md`):
  - Dispatcher signature: `dispatch_inbound(agent_name, account_id, envelope, *, factory)`. The `factory: AgentFactory` is injected by the call site, NOT pulled from a global — avoids circular-import to `interfaces/web/app.py`.
  - Pool acquire-per-inbound is the **`last_activity` ratification** (F1 carry-forward Known Issue at `the_one/agents.md`). The dispatcher does NOT cache the `ConnectorClient` reference outside the pool — every inbound goes through `acquire(agent_name, account_id)`.
  - **Per-session `asyncio.Lock`** in a module-level `defaultdict[str, asyncio.Lock]` serializes concurrent inbounds for the same `chat_sessions` row. F5 owns reconciliation with the WS handler's `Session.processing_lock` (documented in mission Known Issues).
  - Inbound message has `visibility=None` (peer-visible, default). Agent reply also `visibility=None` for F3 (platform-visible default; F4 will own operator-tagging on replies via the platform-send tool).
  - F3 dispatcher does NOT call any outbound mechanism. F4 (platform-send built-in tool) owns outbound. F3's job is: persist inbound, drive `agent.step`, persist agent reply — full stop.
  - `current_chat_session_id` ContextVar binding (`the_one/agent/_context.py:45`) mirrors the WS handler at `interfaces/web/app.py:257` so any pool-spawned MCP OAuth provider construction during `agent.step` routes `auth_required` broadcasts to the right session id.
- **`AgentFactory.create(name)` actual signature** (`the_one/agent/factory.py:181`): no `session_id` kwarg. Session-id propagation goes through `current_chat_session_id`. Confirmed.
- **`agent.step(user_input)` appends `Message.user(user_input)` internally** (`the_one/agent/core.py:138`). Do NOT pre-append the inbound message — that would duplicate. Agent.step also iterates and appends assistant + tool messages to `agent.messages`. After step completes, `agent.messages` holds the full updated history.
- **Persistence pattern**: mirror `_save_session_to_db` at `the_one/interfaces/web/app.py:469-487` — `encode_messages(agent.messages)`, then `repo.update(row.model_copy(update={"title": ..., "messages": encoded}))`. The leg-1 docstring contract on `ChatSessionRepository.update` guarantees connector identity columns (`platform`, `connector_account_id`, etc.) are preserved across the call.
- **Agent message-history wiring at session restoration** (`interfaces/web/app.py:426-434`): `decode_messages(db_session.messages)` → keep agent's freshly-built system message (`agent.messages[:1]`) + append non-system stored messages. Mirror this pattern in the dispatcher.
- **Pool `acquire` signature** (`the_one/connectors/_pool.py:407`): `async def acquire(agent_name: str, account_id: str) -> ConnectorClient`. Returns the client directly (NOT a context manager). The dispatcher uses the return for the side effect of touching `last_activity`; the client itself isn't consumed (F4 will use it for outbound).
- **REVISION from flight spec**: drop `ChatSessionRepository.append_messages` — the existing whole-history `repo.update` pattern is sufficient since `agent.step` already appends internally. The leg-3 architect review noted leg-1 update's docstring guarantees connector identity columns are preserved. Only `update_last_inbound` is added as a new narrow primitive.

## Inputs

State that must exist before this leg runs:

- Legs 1, 2, 3 of this flight are `landed` (1862 tests passing on `flight/03-session-model-key-and-visibility`; uncommitted per batched-review model).
- `the_one/connectors/_pool.py:407 — "async def acquire(agent_name: str, account_id: str) -> ConnectorClient:"` (returns client; touches `last_activity` at line 479).
- `the_one/connectors/_session.py:resolve_session` (leg 3 — `(envelope, account, repo, *, agent_name, plugin) -> ChatSession`).
- `the_one/connectors/registry.py` — `resolve(type) -> ConnectorPlugin` (the existing F1 registry).
- `the_one/agent/factory.py:181 — "async def create(self, name: str = \"default\") -> Agent:"` (the actual signature — no `session_id` kwarg).
- `the_one/agent/_context.py:45 — "current_chat_session_id: ContextVar[str | None] = ..."` (the ContextVar to bind for the agent turn).
- `the_one/agent/core.py:113 — "async def step(self, user_input: str, ...) -> AsyncIterator[Message]:"` (appends user message internally at line 138; yields each message).
- `the_one/db/codec.py:encode_messages` and `decode_messages` (codec round-trip; updated in leg 2 for visibility round-trip).
- `the_one/db/repositories.py:ChatSessionRepository.update` (leg 1 docstring contract: connector identity columns are NOT mutated).
- `the_one/db/repositories.py:ConnectorAccountRepository.get` (extant; reads + decrypts account).
- `the_one/db/repositories.py:ChatSessionRepository.find_most_recent_by_external_key` (leg 3).
- `the_one/connectors/_stub.py:StubPlugin` (leg 3 added `display_channel`).
- `the_one/agents.md:344 — Known Issues entry for `last_activity` ratification` (leg 4 updates to mark as ratified, citing this leg's `acquire` call as the contract anchor).

## Outputs

State that must exist after this leg completes:

- New module `the_one/connectors/_inbound.py` (private; underscore-prefixed) with:
  - `_session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)` module-level.
  - `async def dispatch_inbound(agent_name: str, account_id: str, envelope: InboundEnvelope, *, factory: AgentFactory) -> None` — the dispatcher.
  - `async def _clear_for_test() -> None` — resets `_session_locks` (mirror of `connectors/_pool.py:483 _clear_for_test`). Cheap test-isolation helper that prevents lock identity from leaking across `importlib.reload` or autouse-fixture-driven test resets.
- New method `ChatSessionRepository.update_last_inbound(session_id: str, when: str) -> None` in `the_one/db/repositories.py`. Single-column UPDATE on `last_inbound_at` + `updated_at` (touch both — the resolver consumes `updated_at` for "most recent" ordering; the dispatcher consumes `last_inbound_at` for window calculation).
- **Amend `ChatSessionRepository.update`'s docstring** in `the_one/db/repositories.py` (added by leg 1). The current docstring (per leg-1 implementation at lines ~758-759) enumerates `append_messages` AND `update_last_inbound` as the "narrow primitives" used by the dispatcher for connector-identity-preserving mutations. Leg 4 drops `append_messages` (the leg-design revision noted at top of this artifact); the docstring must be updated to reference ONLY `update_last_inbound`. This is in-scope cleanup — the leg-1 contract description must match what leg-4 actually ships.
- `the_one/agents.md` Known Issues entry for `last_activity` updated: change wording from "Flight 3 ratification needed" → "Flight 3 ratified (M10 F03 L04 — `dispatch_inbound` at `connectors/_inbound.py` calls `acquire(agent_name, account_id)` per inbound; the existing `_RegistryEntry.last_activity` touch at `_pool.py:479` is the contract anchor)." Keep the entry (don't delete) so future readers see the ratification trail.
- New test file `tests/test_connectors_inbound.py` covering:
  - Stub-driven inbound flows through the full dispatcher: pool acquire happens (assertable via `_pool._pool` membership check), session resolved (new on first contact, reused within window), agent.step driven, history persisted.
  - **Pool `last_activity` touch verification**: snapshot `entry.last_activity` before and after a dispatch; assert strictly increasing. (This is the contract anchor for the agents.md Known Issues update.)
  - **Per-session lock serializes concurrent same-session inbounds**: event-coordinated test — arrange the test agent's step to await a test-controlled `asyncio.Event` before completing. Spawn two `dispatch_inbound` calls for the same session; assert only one reaches the blocked state while the other waits on the lock. Release the event; assert the second proceeds.
  - **Per-session lock allows parallel different-session inbounds**: event-coordinated — both reach blocked state concurrently before either event is set.
  - **`current_chat_session_id` ContextVar is set during the turn and reset after**.
  - **Inbound message visibility=None** persisted (peer-visible default).
  - **Agent reply visibility=None** persisted (F3 — platform-visible default; F4 will own operator-tagging).
  - **Account-not-found path**: dispatcher logs a warning and returns gracefully (no crash).
  - **Unknown connector type path**: dispatcher logs an error and returns gracefully.
  - **session_continuation_seconds drives session reuse**: first inbound creates session; second inbound within window reuses; third inbound after window-mock creates new session.
- Flight log gains "Leg Progress: inbound-dispatcher" entry.
- Leg status flipped to `landed`. This leg ticked off in `flight.md` under `### Legs`.

## Acceptance Criteria

- [x] `the_one/connectors/_inbound.py` exists as a new module.
- [x] `_session_locks: defaultdict[str, asyncio.Lock]` declared module-level (use `defaultdict(asyncio.Lock)` — lazy lock creation per session_id).
- [x] `async def dispatch_inbound(agent_name, account_id, envelope, *, factory: AgentFactory) -> None` exists with that exact signature.
- [x] The dispatcher body executes (in order):
  1. **Pool acquire**: `await pool.acquire(agent_name, account_id)` — touches `last_activity`. The returned client is NOT consumed by F3 L4 (F4 owns outbound); the call is for the touch side effect AND to surface pool failures (account not found, plugin not registered, connect failed) BEFORE the dispatcher does any DB work.
  2. **Load account**: function-local import the repository per the load-cycle convention. `account = await _connector_repo().get(account_id)`. On `KeyError`, log warning and return (best-effort — account was deleted while inbound was in flight).
  3. **Resolve plugin**: `plugin = registry.resolve(account.type)`. On `ConnectorRegistrationError`, log error and return.
  4. **Resolve session** via leg 3: `chat_repo = await _chat_session_repo()`; `session_row = await resolve_session(envelope, account, chat_repo, agent_name=agent_name, plugin=plugin)`.
  5. **Acquire per-session lock**: `async with _session_locks[session_row.id]:` — serializes concurrent inbounds for the same chat_sessions row.
  6. **Update `last_inbound_at`**: `await chat_repo.update_last_inbound(session_row.id, _utc_now_iso())`.
  7. **Build the agent**: `agent = await factory.create(agent_name)`.
  8. **Load message history**: re-fetch the session row (history may have been mutated by a previously serialized inbound on this lock). `db_session = await chat_repo.get(session_row.id)`. Decode messages: `stored = decode_messages(db_session.messages)`. Set `agent.messages = agent.messages[:1] + [m for m in stored if m.role != Role.SYSTEM]` (mirror of `_restore_session:434`).
  9. **Bind ContextVar**: `token = current_chat_session_id.set(session_row.id)`. Wrap remaining steps in `try / finally` so the token is reset.
  10. **Drive `agent.step(envelope.text)`**: iterate without callbacks (`async for _ in agent.step(envelope.text): pass`). `agent.step` appends `Message.user(envelope.text)` to `agent.messages` internally; iterates LLM round-trips; appends assistant + tool messages. After completion, `agent.messages` holds the full updated history. NO `on_chunk` / `on_usage` callbacks (F3 has no UI subscribers — F5 owns broadcast).
  11. **Persist history**: `encoded = encode_messages(agent.messages)`; `updated = db_session.model_copy(update={"title": session_row.title, "messages": encoded})`; `await chat_repo.update(updated)`. The leg-1 docstring contract on `ChatSessionRepository.update` guarantees the connector identity columns are preserved (the SQL only writes `title`, `messages`, `updated_at`). This is the **`_save_session_to_db`-equivalent persist** for the connector-driven flow.
  12. **Reset ContextVar** in `finally`: `current_chat_session_id.reset(token)`.
- [x] No call to `record_outbound` or any stub-plugin outbound recorder — F3 L4 does NOT exercise outbound (F4 owns).
- [x] Function-local imports inside the dispatcher to break load cycles, per the `function-local-import-to-break-load-cycle` convention (`the_one/agents.md:86-94`). Concretely: `from the_one.db.connection import get_connection` and `from the_one.db.repositories import ChatSessionRepository, ConnectorAccountRepository` are imported function-locally (the leg-3 resolver already pays this cost via its `repositories` import being top-level — confirm leg-3's import strategy and mirror if possible, OR pay the function-local cost in the dispatcher). The leg author makes the call based on the leg-3 author's pattern.
- [x] `ChatSessionRepository.update_last_inbound(session_id: str, when: str) -> None` exists at `the_one/db/repositories.py`. SQL: `UPDATE chat_sessions SET last_inbound_at = ?, updated_at = ? WHERE id = ?` (touch both). Raises `KeyError` if the session doesn't exist (mirror of the existing `update` / `delete` / `purge_messages` not-found-guard pattern).
- [x] `the_one/agents.md` Known Issues entry at line ~344 updated from "ratification needed" → "ratified by M10 F03 L04 — `dispatch_inbound` at `connectors/_inbound.py` calls `acquire(agent_name, account_id)` per inbound." Keep the entry (don't delete) so the trail is visible.
- [x] New test file `tests/test_connectors_inbound.py` covers all the scenarios in Outputs. The mock LLM provider (extant at `the_one/llm/mock.py`) is the natural test-fixture LLM for the non-concurrency tests — produces predictable single-shot replies without network calls.
- [x] **For the event-coordinated concurrency tests specifically**: the extant `MockProvider` exposes only `delay_ms` (wall-clock) and `stream_chunks` — NO test-controllable async-event hook. Leg 4 introduces a test-local `BlockingProvider` (or equivalent) defined inside `tests/test_connectors_inbound.py` that takes an `asyncio.Event` at construction and awaits it inside its `complete()` / `stream()` before returning. Or equivalently, monkeypatch the `Agent.step` generator's first yield to await the event. Either pattern works; leg-4 author's call. The point: do NOT use `MockProvider.delay_ms` for the concurrency tests — wall-clock sleeps are flaky on CI.
- [x] **`tests/test_connectors_inbound.py` includes an explicit no-duplicate-user-message regression test** (`test_dispatch_inbound_persists_exactly_one_user_message_per_inbound`): after a single `dispatch_inbound` call, the persisted history has exactly one `Message.user` with `content == envelope.text`. This documents the architect-revised deviation (drop `append_messages`; let `agent.step` append internally) as a regression net.
- [x] `make test` clean (no regressions; new test count is added).
- [x] `make lint` clean (no new ruff findings).
- [x] Flight log updated with leg-completion entry citing test counts before/after, deviations encountered, any unforeseen findings.
- [x] Leg status flipped to `landed`.
- [x] This leg ticked off in `flight.md` under `### Legs`.

## Verification Steps

- **Module exists** — `ls the_one/connectors/_inbound.py`.
- **Dispatcher signature** — `grep -n "def dispatch_inbound" the_one/connectors/_inbound.py` shows the function with the exact signature.
- **Per-session lock primitive** — `grep -n "_session_locks" the_one/connectors/_inbound.py` shows the module-level defaultdict.
- **Pool acquire** — `grep -n "pool.acquire\|connectors._pool.acquire\|from the_one.connectors._pool import acquire" the_one/connectors/_inbound.py` confirms the per-inbound acquire.
- **ContextVar binding** — `grep -n "current_chat_session_id" the_one/connectors/_inbound.py` shows the set/reset pair inside `try/finally`.
- **No outbound calls** — `grep -n "record_outbound\|send" the_one/connectors/_inbound.py` returns no matches in production code (test file may grep-match for assertions).
- **`update_last_inbound` exists** — `grep -n "update_last_inbound" the_one/db/repositories.py` shows the new method.
- **agents.md updated** — `grep -n "ratified" the_one/agents.md` shows the new wording.
- **Scoped tests** — `docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30 -v` passes.
- **Full suite** — `docker exec the-one pytest -x --timeout 30` green.
- **Lint** — `docker exec the-one ruff check the_one/ tests/` clean.

## Implementation Guidance

1. **Create `the_one/connectors/_inbound.py`**:

   ```python
   """Inbound dispatcher — composes pool + session resolver + per-session lock
   + agent.step into the end-to-end ingestion path for a connector-driven
   message.

   M10 F03 L04. This is the contract F8 (Discord) and F9 (the second
   connector) will satisfy when they replace the F1-stub-driven inbound
   with a real gateway-driven inbound. F3's stub-based tests prove the
   contract holds against a synthetic envelope; F8 wires the real Discord
   gateway to call this same ``dispatch_inbound``.

   F4 (platform-send tool) owns outbound. This module is INBOUND ONLY.

   The per-(agent, account) pool's :func:`acquire` is called per inbound
   here — that is the **last_activity ratification** of the F1 Known
   Issue (see ``the_one/agents.md``'s Connector subsystem section). The
   dispatcher does NOT cache the :class:`ConnectorClient` reference
   outside the pool; every inbound goes through ``acquire``.

   Per-session serialization via :data:`_session_locks` ensures
   concurrent inbounds for the same ``chat_sessions`` row queue rather
   than race on ``agent.messages``. F5 will reconcile this lock with the
   WS handler's ``Session.processing_lock`` when operator-typed messages
   into connector-attached sessions land (see mission Known Issues).
   """

   from __future__ import annotations

   import asyncio
   import logging
   from collections import defaultdict
   from datetime import datetime, timezone

   from the_one.agent._context import current_chat_session_id
   from the_one.agent.factory import AgentFactory
   from the_one.connectors import registry
   from the_one.connectors._pool import acquire as pool_acquire
   from the_one.connectors._session import resolve_session
   from the_one.connectors.base import InboundEnvelope
   from the_one.connectors.errors import ConnectorRegistrationError
   from the_one.db.codec import decode_messages, encode_messages
   from the_one.llm.base import Role

   logger = logging.getLogger(__name__)

   # Per-(chat_sessions.id) lock. Module-level defaultdict — locks are
   # created lazily on first use. Memory growth flagged for F10 hardening:
   # locks accumulate monotonically with session count over process
   # lifetime. Mitigation options (WeakValueDictionary, TTL cleanup, LRU)
   # are deferred until growth matters.
   _session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


   def _utc_now_iso() -> str:
       return datetime.now(timezone.utc).isoformat()


   async def dispatch_inbound(
       agent_name: str,
       account_id: str,
       envelope: InboundEnvelope,
       *,
       factory: AgentFactory,
   ) -> None:
       """Dispatch a single inbound envelope through the full pipeline.

       Pool-acquires for the (agent, account) pair (touches
       ``last_activity``; this is the F1 ratification anchor). Loads the
       account, resolves the plugin, resolves the chat_sessions row via
       :func:`the_one.connectors._session.resolve_session`, acquires the
       per-session lock, updates ``last_inbound_at``, builds a fresh
       :class:`Agent` via the injected ``factory``, loads the session's
       message history into the agent, drives :meth:`Agent.step`, and
       persists the updated history back to the row.

       The agent loop is unchanged — this dispatcher drives ``agent.step``
       the same way the WS handler does, the only difference is the trigger
       source (an :class:`InboundEnvelope` vs. a WS message).

       Errors at any pipeline stage (account not found, plugin not
       registered, connect failed) are logged and the function returns —
       a connector-layer failure DOES NOT take the agent runtime down.
       """
       # 1. Pool acquire — touches last_activity (F1 ratification).
       try:
           await pool_acquire(agent_name, account_id)
       except (KeyError, ConnectorRegistrationError) as exc:
           logger.warning(
               "dispatch_inbound: pool acquire failed for (agent=%s, account=%s): %s",
               agent_name,
               account_id,
               exc,
           )
           return
       except Exception:
           # Any other pool failure (connect raise, plugin connect timeout, etc.)
           logger.exception(
               "dispatch_inbound: unexpected pool acquire failure for (agent=%s, account=%s)",
               agent_name,
               account_id,
           )
           return

       # 2. Load account (function-local imports per the load-cycle convention).
       from the_one.db.connection import get_connection
       from the_one.db.repositories import (
           ChatSessionRepository,
           ConnectorAccountRepository,
       )
       from the_one.encryption import get_encryptor
       from the_one.settings import settings

       conn = await get_connection()
       encryptor = get_encryptor(settings.data_dir)
       acc_repo = ConnectorAccountRepository(conn, encryptor)
       chat_repo = ChatSessionRepository(conn)

       try:
           account = await acc_repo.get(account_id)
       except KeyError:
           logger.warning(
               "dispatch_inbound: account %s not found (deleted mid-flight?)",
               account_id,
           )
           return

       # 3. Resolve plugin.
       try:
           plugin = registry.resolve(account.type)
       except ConnectorRegistrationError as exc:
           logger.error(
               "dispatch_inbound: unknown connector type %r for account %s: %s",
               account.type,
               account_id,
               exc,
           )
           return

       # 4. Resolve session.
       session_row = await resolve_session(
           envelope,
           account,
           chat_repo,
           agent_name=agent_name,
           plugin=plugin,
       )

       # 5-12. Per-session lock + persist + agent.step + persist.
       async with _session_locks[session_row.id]:
           # 6. Update last_inbound_at.
           await chat_repo.update_last_inbound(session_row.id, _utc_now_iso())

           # 7-8. Build agent + load history.
           agent = await factory.create(agent_name)
           db_session = await chat_repo.get(session_row.id)
           stored = decode_messages(db_session.messages)
           if stored:
               non_system = [m for m in stored if m.role != Role.SYSTEM]
               agent.messages = agent.messages[:1] + non_system

           # 9-12. Bind ContextVar, drive agent.step, persist history.
           token = current_chat_session_id.set(session_row.id)
           try:
               # 10. Agent.step appends Message.user(envelope.text) internally;
               # iterates LLM round-trips; appends assistant + tool messages.
               async for _ in agent.step(envelope.text):
                   pass

               # 11. Persist updated history (mirror _save_session_to_db pattern).
               encoded = encode_messages(agent.messages)
               updated = db_session.model_copy(
                   update={
                       "title": session_row.title,
                       "messages": encoded,
                   }
               )
               await chat_repo.update(updated)
           finally:
               # 12. Reset ContextVar.
               current_chat_session_id.reset(token)
   ```

   Notes on the imports:
   - `from the_one.connectors import registry` — but the registry resolution is via the module-level `registry.resolve(type)` function at `the_one/connectors/registry.py:99` (which dispatches to a singleton `_registry`). The alternative `from the_one.connectors.registry import resolve` works too; either is fine.
   - `from the_one.connectors._pool import acquire as pool_acquire` — aliased to avoid name collision with any function-local `acquire` that doesn't exist today but might be added.
   - **`from the_one.agent.factory import AgentFactory` at module top is SAFE** (design-review-verified): `the_one/agent/factory.py` does NOT transitively import from `the_one.connectors.*` (its top-level imports are `agent.config`, `agent.core`, `agent.store`, `config`, `db._provider_types`, `llm`, `tools.*`). No `TYPE_CHECKING` guard needed. Confirmed by the design-review pass at `the_one/agent/factory.py:161`.
   - Function-local imports for `db.connection`, `db.repositories`, `encryption`, `settings` — per the load-cycle convention. The dispatcher being at the connectors→db layer boundary triggers the same circular-import risk that `_pool.py` and `_session.py` already pay through function-local imports. Mirror the same pattern.
   - **`ConnectorRegistrationError` is caught twice** (once at step 1 via `pool.acquire` — `_pool._resolve_plugin` raises it at `_pool.py:440` — and once at step 3 explicitly). The second catch is dead in the happy path because pool acquire would have already raised. Acceptable defensive coding — note in a comment that the redundancy is deliberate so a future reader doesn't try to "simplify" by removing.

2a. **Add `_clear_for_test()`** helper at module-bottom of `the_one/connectors/_inbound.py`, mirroring `connectors/_pool.py:_clear_for_test`:

   ```python
   async def _clear_for_test() -> None:
       """Test seam: clear the per-session lock dict.

       Mirrors :func:`the_one.connectors._pool._clear_for_test`. Test
       fixtures that exercise the dispatcher should call this to ensure
       lock identity doesn't leak across tests (an `asyncio.Lock` built
       on a closed event loop will error on next `async with`).
       """
       _session_locks.clear()
   ```

2b. **Amend `ChatSessionRepository.update`'s docstring** at `the_one/db/repositories.py` (added by leg 1). Read the current docstring (likely at lines ~758-759 per the design-review's spot-check); it enumerates `append_messages` and `update_last_inbound` as the narrow primitives. Replace the `append_messages` reference with `update_last_inbound (M10 F03 L04)` and `... and through this method itself for whole-history mutations (e.g. _save_session_to_db at interfaces/web/app.py:469-487; the connector dispatcher at connectors/_inbound.py:dispatch_inbound)`. The point: the docstring's "narrow primitives" enumeration must match what's shipped — `append_messages` is intentionally not added in this leg.

2. **Add `ChatSessionRepository.update_last_inbound`** to `the_one/db/repositories.py`:

   ```python
   async def update_last_inbound(self, session_id: str, when: str) -> None:
       """Bump the connector-driven activity timestamps for a session.

       Touches both ``last_inbound_at`` (consumed by the resolver's
       continuation-window check at
       :func:`the_one.connectors._session.resolve_session`) and
       ``updated_at`` (the most-recent-by-updated_at ordering the resolver
       uses to pick the active row when multiple historical rows exist
       for the same external key).

       Raises ``KeyError`` if the session doesn't exist — mirrors
       :meth:`update` / :meth:`delete` / :meth:`purge_messages` not-found
       semantics.

       M10 F03 L04 — narrow primitive consumed by
       :func:`the_one.connectors._inbound.dispatch_inbound`. The seven
       connector-identity columns are intentionally not touched — see
       :meth:`update`'s docstring for the identity-columns contract.
       """
       async with self.conn.execute(
           "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
       ) as cur:
           if await cur.fetchone() is None:
               raise KeyError(f"Chat session not found: {session_id}")
       await self.conn.execute(
           "UPDATE chat_sessions SET last_inbound_at = ?, updated_at = ? WHERE id = ?",
           (when, when, session_id),
       )
       await self.conn.commit()
   ```

   Insert after `purge_messages` and BEFORE the new `find_most_recent_by_external_key` from leg 3 (or wherever fits the existing method ordering — leg author's call).

3. **Update `the_one/agents.md` Known Issues** for `last_activity` ratification. Find the bullet starting "Flight 3 ratification needed for `last_activity` tracking" (around line 344). Rewrite as:

   ```markdown
   - **Flight 3 ratified `last_activity` tracking via acquire-per-inbound** (M10 F03 L04). `connectors/_pool.py:_RegistryEntry.last_activity` is updated by `acquire()` on every call (warm and cold paths converge — see `_pool.py:479`). The reaper consumes this value to decide eviction. The dispatcher at `connectors/_inbound.py:dispatch_inbound` calls `acquire(agent_name, account_id)` per inbound envelope — `last_activity` is touched per inbound, NOT per session-key resolution or per agent.step iteration. This is the contract: any future code path that bypasses the pool (e.g. caches a `ConnectorClient` reference outside the pool) is responsible for re-touching `last_activity` itself OR for accepting that the reaper may evict actively-used connections.
   ```

   Keep the entry — don't delete. The retroactive note preserves the trail for future maintainers.

4. **Add tests** in a new file `tests/test_connectors_inbound.py`. Use the mock LLM provider (`the_one/llm/mock.py`) for predictable agent replies. Test fixture pattern: build an `AgentFactory` with a mock provider, seed a stub `ConnectorAccount` row, register the StubPlugin via `register_for_test`, push synthetic envelopes through `dispatch_inbound`.

   Tests (use `pytest.mark.asyncio` per the existing test discipline):

   **Test fixture for event-coordinated concurrency** — define inside `tests/test_connectors_inbound.py`:

   ```python
   class _BlockingProvider(LLMProvider):
       """Test-only LLM provider that awaits an asyncio.Event before
       producing its single assistant reply. Enables event-coordinated
       concurrency tests where wall-clock sleeps would be flaky.
       """
       def __init__(self, event: asyncio.Event, reply: str = "ok") -> None:
           self._event = event
           self._reply = reply

       async def complete(self, messages, tools=None, **kwargs) -> Message:
           await self._event.wait()
           return Message.assistant(self._reply)

       async def stream(self, messages, tools=None, **kwargs):
           await self._event.wait()
           yield StreamChunk(content=self._reply, is_final=True,
                             message=Message.assistant(self._reply))

       async def supports_tools(self) -> bool:
           return False  # avoid the tool-loop path; single-shot reply suffices.
   ```

   Inject via a factory built around this provider for the two concurrency tests. The mock-provider-based tests (`MockProvider` at `the_one/llm/mock.py`) cover the non-concurrency scenarios.

   - `test_dispatch_inbound_creates_session_on_first_contact` — assert session row created with all external-key columns + agent.messages persisted with the user + assistant turns.
   - `test_dispatch_inbound_persists_exactly_one_user_message_per_inbound` — regression net for the architect-revised "drop append_messages, let agent.step append internally" deviation. After one `dispatch_inbound`, the decoded persisted messages contain exactly one `Message.user` whose content matches `envelope.text`.
   - `test_dispatch_inbound_reuses_session_within_window` — two inbounds for same key → one session row; both turns in the persisted history.
   - `test_dispatch_inbound_creates_new_session_after_window` — monkeypatch `_DEFAULT_CONTINUATION_SECONDS` or set `THE_ONE_SESSION_CONTINUATION_SECONDS=1` env; two inbounds with sleep between → two rows.
   - `test_dispatch_inbound_touches_pool_last_activity` — snapshot `the_one.connectors._pool._pool[(agent, account)].last_activity` before/after; assert strict increase.
   - `test_dispatch_inbound_serializes_concurrent_same_session` — event-coordinated: arrange the mock LLM to await a `test_event` before completing; spawn two `asyncio.create_task(dispatch_inbound(...))` for the same envelope key; assert only one reaches the blocked state; release event; assert the second completes.
   - `test_dispatch_inbound_parallelizes_different_sessions` — event-coordinated: two dispatches for different external keys → both reach blocked state concurrently.
   - `test_dispatch_inbound_sets_and_resets_context_var` — assert `current_chat_session_id.get()` returns `None` outside the dispatch, and is set to the session_id during the agent.step call. Achievable by monkeypatching `agent.step` to capture the ContextVar value at entry.
   - `test_dispatch_inbound_account_not_found_returns_gracefully` — pass a non-existent account_id; assert no exception, no session created.
   - `test_dispatch_inbound_unknown_connector_type_returns_gracefully` — register an account with an unregistered type; assert no exception.
   - `test_dispatch_inbound_persists_inbound_with_visibility_none` — assert the persisted user message has `visibility=None` (i.e. the codec output dict has no `visibility` key).
   - `test_dispatch_inbound_persists_agent_reply_with_visibility_none` — same for the assistant reply.
   - `test_dispatch_inbound_does_not_call_record_outbound` — assert `StubPlugin.outbound_records` is empty after dispatch. F3 L4 owns NO outbound path.
   - `test_update_last_inbound_bumps_both_timestamps` — repository-level unit test: seed a session with old timestamps; call `update_last_inbound`; assert both `last_inbound_at` and `updated_at` updated to the new value.
   - `test_update_last_inbound_raises_keyerror_on_missing_session` — repository unit test.

5. **Run tests**:
   ```
   docker exec the-one pytest tests/test_connectors_inbound.py tests/test_db_repositories.py -x --timeout 30 -v
   ```
   Then full suite + lint.

6. **Update flight log** with "Leg Progress: inbound-dispatcher" entry. Capture timestamps + test-count delta from leg 3's 1862 + any deviations.

7. **Flip leg status to `landed`**. Tick leg 4 in `flight.md` under `### Legs`. Do NOT commit. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Pool acquire raises**: any exception from `pool.acquire` aborts the dispatch — the session is NOT created (resolver never runs), nothing is persisted. The dispatcher logs and returns gracefully. Acceptable: a connector with broken credentials simply doesn't process inbounds; the operator sees the connector's degraded state via the existing doctor probe (F2) and fixes credentials.

- **Concurrent first-contact race (revisited)**: leg 3 documented that two concurrent `resolve_session` calls for the same external key can both create rows. Leg 4's per-session lock fires AFTER `resolve_session` returns, so the lock-on-session-id can't serialize the resolver itself. **This is intentional and acceptable** — the orphan row simply becomes historical-not-active. The "active" session for the external key is whichever was most-recently `update_last_inbound`-ed. The next inbound's `find_most_recent_by_external_key` returns the most-recent-by-updated_at, picks up the surviving session, and continues from there.

- **Agent build fails during `factory.create`**: e.g. `ProviderNotConfiguredError` or `ProviderNotFoundError`. The dispatcher's `try / finally` does NOT catch these — they propagate up. F3 L4 lets them bubble; F8's gateway-listener should catch them with a try/except around the `dispatch_inbound` call and surface a degraded state. Document this in the dispatcher's docstring so F8's caller knows.

- **Agent.step raises mid-stream**: any LLM-side or tool-side exception propagates up through the `async for` and out of the dispatcher (after the ContextVar is reset by the `finally`). Same as agent build failures — F8's caller catches.

- **Session row mutated between `resolve_session` and `chat_repo.get(session_row.id)` inside the lock**: shouldn't happen in F3 (no other writer), but defensive: the dispatcher uses the freshly-fetched `db_session` for history decoding. The `session_row` from `resolve_session` is used for `id` and `title` only.

- **Memory growth of `_session_locks`**: documented in the module docstring. F10 hardening.

- **`THE_ONE_SESSION_CONTINUATION_SECONDS` env var**: read at call time by the resolver (leg 3); the dispatcher does NOT cache it. Test-time monkeypatching changes resolution without restart.

## Files Affected

- `the_one/connectors/_inbound.py` — new module (dispatcher + `_clear_for_test` helper)
- `the_one/db/repositories.py` — add `ChatSessionRepository.update_last_inbound` + amend `ChatSessionRepository.update`'s docstring to remove the `append_messages` reference (replace with `update_last_inbound` + the `repo.update` whole-history pattern citation)
- `the_one/agents.md` — update Known Issues entry for `last_activity` to mark ratified
- `tests/test_connectors_inbound.py` — new test file (~15 tests including the no-duplicate-user-message regression and the `_BlockingProvider` fixture for concurrency tests)
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight-log.md` — leg-completion entry
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight.md` — tick leg 4 under `### Legs`
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/legs/04-inbound-dispatcher.md` — this file's status → `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (scoped + full suite)
- [x] Lint clean
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md's Legs list
- [x] Do NOT commit — agentic-workflow batched-review defers commit to flight end
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

9 citations verified against current code at leg design time:

- `the_one/connectors/_pool.py:407` (`async def acquire`) — verified.
- `the_one/connectors/_pool.py:479` (`entry.last_activity = time.monotonic()`) — verified.
- `the_one/agent/factory.py:181` (`async def create(self, name: str = "default")`) — verified.
- `the_one/agent/_context.py:45` (`current_chat_session_id: ContextVar`) — verified.
- `the_one/agent/core.py:113` (`async def step(self, user_input, ...)`) — verified.
- `the_one/agent/core.py:138` (`self.messages.append(Message.user(user_input))`) — verified.
- `the_one/interfaces/web/app.py:469` (`async def _save_session_to_db`) — verified.
- `the_one/interfaces/web/app.py:426-434` (history-loading mirror pattern) — verified.
- `the_one/agents.md:344` (Known Issues `last_activity` entry) — verified (leg 1+2+3 may have shifted line numbers; the entry header text is the durable anchor: "Flight 3 ratification needed for `last_activity` tracking" — verify by grep on the phrase before editing).
