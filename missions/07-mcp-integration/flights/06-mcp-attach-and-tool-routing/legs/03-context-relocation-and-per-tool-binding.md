# Leg: 03-context-relocation-and-per-tool-binding

**Status**: completed
**Flight**: [Per-agent MCP attach + tool-routing in agent loop](../flight.md)

## Objective

Move F5's `current_chat_session_id` ContextVar from `the_one/interfaces/web/app.py` to its canonical home at `the_one/agent/_context.py`, add `current_tool_call_id` companion, bind it per-tool-dispatch inside `Agent._execute_tool`, drop the `_pool_default` sentinel from `_entry_worker`, and widen `build_oauth_provider_for_source` to accept `chat_session_id: str | None` (returning None when unset rather than constructing a provider that broadcasts to nowhere).

## Context

**Why this leg**: F5 placed `current_chat_session_id` in the web-interface layer with a `_pool_default` sentinel as a silent-drop fallback for pool spawns outside a chat-driven context. F5 debrief R4 flagged this as carry-forward debt — the sentinel produces INCORRECT routing in multi-tab scenarios (broadcast goes to "most-recently-active session" via the OAuth handlers' lazy `_sessions` lookup, NOT the originating session). The F5 `provider_factory.py` module-top docstring at lines 34-38 explicitly names this as "Architectural debt (carried to F6)." L3 retires the debt.

**Why ContextVar in `the_one/agent/_context.py` is the right home**: per the project's `canonical-import + convenience-re-export` convention (`agents.md::Project Conventions`), a symbol's canonical home matches its primary semantics. `current_chat_session_id` is read by the MCP pool to route `auth_required` broadcasts to a chat session — but it's set by the agent dispatch boundary. The agent layer is the symbol's owner; the web interface is the convenience-re-export consumer. Moving it also lets the new `current_tool_call_id` live alongside it without dragging the agent layer through a `the_one/interfaces/web/app` import.

**Why per-tool-dispatch binding for `current_tool_call_id`**: the F5 OAuth handler's `auth_required` broadcast payload includes `tool_call_id` so the chat UI can correlate the Login-required button to the specific tool call. F5 L4 plumbed this through `MCPClient.call_tool`'s 401 catch and `_execute_tool`'s translation — but at pool-spawn time (before any tool call), `tool_call_id` is None. F6 L3's per-tool-dispatch binding fills this gap when the pool worker spawns DURING a tool dispatch (i.e., the cold-spawn path on first `acquire` from `MCPClientTool.execute`).

**Why drop `_pool_default` sentinel and pass `None` directly**: F5's "fallback to most-recently-active session" routes the broadcast to a session that may not be the operator's current tab. Worse: in a multi-tab scenario where tab A's chat triggered the spawn and tab B is most recently active, tab B receives an OAuth prompt for an action it didn't initiate. Replacing the sentinel with None means: when no chat session is bound to the current task, NO provider is constructed (the lazy 401 path takes over at next `call_tool`, which DOES have per-tool-dispatch context bound). This is strictly more correct.

**Why widen `build_oauth_provider_for_source` to `chat_session_id: str | None`**: an OAuth provider whose `redirect_handler` has no chat-session target would block forever waiting for a callback that can't be triggered. If the csid is None at provider construction time, we return None (no provider). The MCPClient connects without auth; lazy 401 surfaces at next `call_tool`; that path DOES have csid bound (via the agent dispatch boundary) and routes correctly. **Trade-off** (cycle-2 inherited): this fixes the COLD-SPAWN path. The WARM-pool task-pinning trade-off — where the OAuth provider built at first-acquire is permanently bound to that csid for the entry's lifetime — is unchanged. F6 inherits and documents it; doesn't fix.

**Cache freshness contract**: `current_chat_session_id` and `current_tool_call_id` are NOT caches — they're per-task contextual state that resets at each task boundary. ContextVars carry through `asyncio.create_task` snapshots (verified at L2 cycle-2). Source of truth: the WebSocket session handler sets `current_chat_session_id` at message-processing entry; `_execute_tool` sets `current_tool_call_id` at tool-dispatch entry. Both reset on exit via `try/finally`. Maximum staleness: zero — values are set and read in the same task scope.

**Prior leg outcomes** (flight log):
- L0 landed: `MCPAuthRequired` canonical at `the_one/mcp/errors.py`; lazy imports retired.
- L1 landed: `_overrides.py` schemas + `AgentConfig.mcp_overrides` field + v11 ALTER migration.
- L2 landed: `MCPClientTool` + `MCPToolProvider` + `acquire` widening + factory integration. 31 new unit tests + 1 pool widening test (deferred to docker per A3).
- L0 anomaly A1 / L1 anomaly A2 / L2 anomaly A3: `tests/test_mcp_pool.py` is env-dependent — `_entry_worker` calls `get_connection()` for OAuth provider construction. L3 modifies `_entry_worker`; the new tests for ContextVar binding MUST avoid the same env trap by either mocking `get_connection` + `build_oauth_provider_for_source` OR testing the agent-layer bind without invoking the pool worker.

**Stake**: ~75 LOC production delta + ~120 LOC tests. Smaller than L2; cycle-1 design review is recommended but not strictly mandatory per F5 debrief Process #1 thresholds (no new public API endpoint, no new module-level concurrency primitive, leg LOC well under 800).

## Inputs

What exists before this leg runs (post-L2):

- `the_one/interfaces/web/app.py:209-211` — `current_chat_session_id: ContextVar[str | None] = ContextVar("current_chat_session_id", default=None)`.
- `the_one/interfaces/web/app.py:236, :256` — set/reset in `_spawn_message_processing` (the WebSocket message handler) using token-pattern.
- `the_one/interfaces/web/app.py:853, :875` — set/reset in `_resume_paused_session` (the OAuth resume handler) using token-pattern.
- `the_one/mcp/_pool.py:181-189 (in _entry_worker)` — lazy imports `current_chat_session_id` from `the_one.interfaces.web.app`; reads via `current_chat_session_id.get(None) or "_pool_default"`; passes to `build_oauth_provider_for_source(source, repo, csid, source_id=source.id)`.
- `the_one/mcp/oauth/provider_factory.py::build_oauth_provider_for_source` — accepts `chat_session_id: str` (line 58, NOT yet `str | None`); also accepts `tool_call_id: str | None = None` (line 60, F5-plumbed but not yet read from ContextVar at call sites). Module-top docstring at lines 34-38 names the F6 plumbing as "Architectural debt (carried to F6)."
- `the_one/mcp/oauth/provider_factory.py:80-82` — `if not dcr or not dcr.get("client_id"): return None` — current early-return path. L3 widens to also return None when `chat_session_id is None`.
- `the_one/agent/core.py::Agent._execute_tool` lines 249-279 — current implementation. F5 L4 lazy import of `MCPAuthRequired` was retired in F6 L0 (now module-top). L3 wraps the function body in a `try/finally` for `current_tool_call_id` bind.
- `the_one/agent/_context.py` — does NOT exist (verified by Phase 1 grep — no `the_one/agent/_context*` files in the tree).
- F5 OAuth tests: `tests/test_oauth_*.py` (pre-existing) and `tests/test_mcp_oauth_integration.py` (pre-existing) — must continue passing post-L3 via the back-compat re-export at `the_one/interfaces/web/app.py`.
- L0+L1+L2 working tree changes uncommitted: 16 modified + 5 new files.

## Outputs

- `the_one/agent/_context.py` (NEW) — module-level definitions of `current_chat_session_id: ContextVar[str | None]` AND `current_tool_call_id: ContextVar[str | None]` plus a module docstring explaining the canonical-home rationale and the cross-task ContextVar inheritance via `asyncio.create_task` snapshot semantics. ~35 LOC.
- `the_one/interfaces/web/app.py` — `current_chat_session_id` module-level definition REPLACED with re-export `from the_one.agent._context import current_chat_session_id`. Existing set-sites at `:236, :256, :853, :875` are UNCHANGED (the re-exported name resolves to the canonical class object). Add re-export of `current_tool_call_id` for any future consumer in the web layer. ~+3 LOC / ~-4 LOC delta.
- `the_one/mcp/_pool.py::_entry_worker` — replace lazy `from the_one.interfaces.web.app import current_chat_session_id` with `from the_one.agent._context import current_chat_session_id, current_tool_call_id`. Drop the `or "_pool_default"` sentinel. Read `current_tool_call_id.get(None)`. Pass both to `build_oauth_provider_for_source`. ~+5 LOC / ~-3 LOC delta.
- `the_one/mcp/oauth/provider_factory.py::build_oauth_provider_for_source` — type signature: `chat_session_id: str` → `chat_session_id: str | None`. Add early-return: when `chat_session_id is None`, return None (no provider construction). Update module-top docstring to retire the "Architectural debt (carried to F6)" note. ~+8 LOC delta.
- `the_one/agent/core.py::Agent._execute_tool` — wrap function body in `try/finally` that sets `current_tool_call_id` at entry and resets at exit. Module-top import added: `from the_one.agent._context import current_tool_call_id`. ~+8 LOC delta.
- `tests/test_agent_context.py` (NEW) — covers ContextVar visibility from inside `_execute_tool`, reset on exception path, `_pool_default` sentinel grep returning zero hits, the `chat_session_id is None` short-circuit in `build_oauth_provider_for_source`. ~120 LOC, ~12 tests.
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry.

## Acceptance Criteria

- [ ] `the_one/agent/_context.py` exists with both `current_chat_session_id: ContextVar[str | None]` and `current_tool_call_id: ContextVar[str | None]` definitions; both have `default=None`.
- [ ] `the_one/interfaces/web/app.py` no longer DEFINES `current_chat_session_id` (verified by `grep -n "current_chat_session_id: ContextVar" the_one/interfaces/web/app.py` returning 0 hits) but DOES re-export it (verified by `grep -n "from the_one.agent._context import current_chat_session_id" the_one/interfaces/web/app.py` returning 1 hit).
- [ ] F5 set-sites at `:236, :256, :853, :875` of `app.py` continue to work UNCHANGED — they import the re-exported name; the re-export resolves to the canonical class object.
- [ ] `python -c "from the_one.interfaces.web.app import current_chat_session_id as A; from the_one.agent._context import current_chat_session_id as B; assert A is B"` exits 0 (re-export identity preserved).
- [ ] `the_one/mcp/_pool.py::_entry_worker` no longer references `_pool_default`. Verified by `grep -n "_pool_default" the_one/` returning 0 hits in production code.
- [ ] `_entry_worker` reads `current_chat_session_id.get(None)` AND `current_tool_call_id.get(None)`; passes both to `build_oauth_provider_for_source(source, repo, csid, source_id=source.id, tool_call_id=tcid)`.
- [ ] `build_oauth_provider_for_source` type signature: `chat_session_id: str | None`. When `chat_session_id is None`, returns None BEFORE the dcr check (no handler construction; no provider).
- [ ] `Agent._execute_tool` binds `current_tool_call_id.set(tool_call.id)` at function entry; resets via token-pattern in `finally`. The bind is INSIDE the function body, NOT at module scope.
- [ ] ContextVar reset on exception: when `MCPAuthRequired` is caught (lines 257-273 of current core.py) AND when generic `Exception` is caught (lines 274-279), the `current_tool_call_id` token is properly reset before the function returns.
- [ ] `tests/test_agent_context.py` exists with ~12 tests covering all paths.
- [ ] All F5 OAuth tests pass UNMODIFIED (`tests/test_oauth_*.py`, `tests/test_mcp_oauth_integration.py`, `tests/test_mcp_oauth_errors.py`, `tests/test_oauth_provider_factory.py`).
- [ ] L0+L1+L2 regression unaffected (`tests/test_imports.py`, `tests/test_mcp_overrides.py`, `tests/test_mcp_tool_provider.py`, `tests/test_db_migration.py`, `tests/test_db_repositories.py`, `tests/test_agent.py`).
- [ ] `provider_factory.py` module-top docstring lines 34-38 — "Architectural debt (carried to F6)" note retired (replaced with "Resolved at F6 L3" or similar).
- [ ] `ruff check the_one/ tests/` is clean.

## Verification Steps

```bash
# Module surface
./.venv/bin/python -c "from the_one.agent._context import current_chat_session_id, current_tool_call_id; print('OK')"

# Re-export identity preservation
./.venv/bin/python -c "from the_one.interfaces.web.app import current_chat_session_id as A; from the_one.agent._context import current_chat_session_id as B; assert A is B; print('OK')"

# Sentinel retirement
grep -n "_pool_default" the_one/   # → 0 hits
grep -n 'current_chat_session_id: ContextVar' the_one/interfaces/web/app.py  # → 0 hits (definition gone)
grep -n 'from the_one.agent._context import' the_one/interfaces/web/app.py the_one/mcp/_pool.py the_one/agent/core.py  # → 3 hits (re-export + 2 import sites)

# Targeted leg gate (L3 + F5 OAuth regression + L0+L1+L2 regression)
./.venv/bin/python -m pytest tests/test_agent_context.py tests/test_oauth_provider_factory.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_overrides.py tests/test_mcp_tool_provider.py tests/test_db_migration.py tests/test_db_repositories.py tests/test_imports.py tests/test_mcp_client.py -v --timeout=15

# Lint
./.venv/bin/ruff check the_one/ tests/

# DO NOT include tests/test_mcp_pool.py in the targeted gate (env-dependent per A1/A2/A3).
# DO NOT run full unfiltered pytest outside docker.
```

## Implementation Guidance

The order minimizes test-feedback loops: data-flow primitives (the new module + re-export) first, then the consumers, then `_execute_tool`'s wrapping, then tests. Each step has localized verification.

1. **Create `the_one/agent/_context.py` with both ContextVar definitions.**
   - Module-level scaffold:
     ```python
     """Per-task context for agent dispatch.

     Owns the canonical definitions of:

     - ``current_chat_session_id``: identifier for the chat session whose
       agent is currently dispatching. Set by the WebSocket message handler
       in ``the_one.interfaces.web.app`` (``_spawn_message_processing`` and
       ``_resume_paused_session``) at message-processing entry; reset on
       exit via the token pattern.
     - ``current_tool_call_id``: identifier for the specific tool call
       currently being dispatched. Set by ``Agent._execute_tool`` at
       function entry; reset in ``finally``.

     Both ContextVars are read by ``the_one.mcp._pool._entry_worker`` at
     pool-spawn time to route OAuth ``auth_required`` broadcasts to the
     correct chat session and to attach the originating tool_call_id to
     the broadcast payload (so the chat UI can correlate the
     Login-required button to the specific tool call).

     Cross-task inheritance: ``asyncio.create_task`` snapshots the parent
     task's context at creation time. The pool worker task spawned via
     ``asyncio.create_task`` inside ``acquire`` inherits the
     ``current_chat_session_id`` and ``current_tool_call_id`` from the
     calling tool dispatch. This is the F4 task-pinning trade-off:
     the FIRST acquire of an ``(agent_name, source_id)`` key pins the
     ContextVar values for the entry's lifetime; subsequent acquires
     within idle TTL reuse the cached client whose OAuth provider was
     built with the FIRST acquire's csid+tcid. F6 inherits this; cross-
     session routing of the broadcast still depends on F5's "most-
     recently-active session fallback" in OAuth handlers for the
     warm-pool case.

     Canonical home (this module) per the
     ``canonical-import + convenience-re-export`` convention
     (``the_one/agents.md::Project Conventions``):
     ``the_one.interfaces.web.app`` re-exports ``current_chat_session_id``
     for back-compat with F5's set-sites; future consumers in any layer
     should import from here.
     """

     from __future__ import annotations

     from contextvars import ContextVar

     current_chat_session_id: ContextVar[str | None] = ContextVar(
         "current_chat_session_id", default=None
     )
     """The chat session id whose agent is currently dispatching.

     None when no chat session is active in the current task scope (e.g.
     agent build invoked from CLI / REST / tests). Pool's
     ``_entry_worker`` reads this; when None, ``build_oauth_provider_for_source``
     returns None (no provider — lazy 401 path surfaces at next
     ``call_tool`` which DOES have per-tool-dispatch context bound).
     """

     current_tool_call_id: ContextVar[str | None] = ContextVar(
         "current_tool_call_id", default=None
     )
     """The tool_call_id of the specific tool call currently being dispatched.

     Set by ``Agent._execute_tool`` at function entry. Read by the OAuth
     handlers' ``redirect_handler`` so the ``auth_required`` broadcast
     payload carries the originating tool_call_id (for chat-UI
     correlation of the Login-required button).

     None when no tool call is currently dispatching (e.g. pool spawn
     during agent build's ``MCPToolProvider.get_tools_for_agent`` call —
     before any tool call has fired).
     """
     ```
   - Total: ~35 LOC including the comprehensive docstrings.

2. **Migrate `the_one/interfaces/web/app.py`'s definition to a re-export.**
   - Find the existing block at lines 209-211:
     ```python
     current_chat_session_id: ContextVar[str | None] = ContextVar(
         "current_chat_session_id", default=None
     )
     ```
   - REPLACE with a re-export at the imports area (top of file, alongside other module imports):
     ```python
     # F6 L3: ContextVar definition moved to the_one/agent/_context.py
     # (canonical home). Re-exported here for back-compat with F5's
     # existing set-sites at _spawn_message_processing (line ~236) and
     # _resume_paused_session (line ~853). New consumers should import
     # from the_one.agent._context directly.
     from the_one.agent._context import (
         current_chat_session_id,  # noqa: F401  back-compat re-export
         current_tool_call_id,  # noqa: F401  re-export for future consumers
     )
     ```
   - The 4 set-site usages at `:236, :256, :853, :875` continue to work UNCHANGED — Python's name resolution finds the re-exported `current_chat_session_id` via the module-top import.
   - Drop the now-unused `from contextvars import ContextVar` import IF no other contextvars are defined in the file (verify: `grep -n 'from contextvars\|ContextVar(' the_one/interfaces/web/app.py`). If contextvars is still imported elsewhere, leave it.
   - Drop the comprehensive docstring block at lines ~196-211 of `app.py` (the F5 explanation of "Best-effort fallback... ContextVar"). The canonical home's docstring is more authoritative; the back-compat re-export gets a 4-line comment above it referencing the canonical home.

3. **Update `the_one/mcp/_pool.py::_entry_worker` to drop `_pool_default` sentinel and add tool_call_id read.**
   - Find the block at lines ~181-189 (in `_entry_worker`):
     ```python
     from the_one.interfaces.web.app import current_chat_session_id
     from the_one.mcp.oauth import build_oauth_provider_for_source
     csid = current_chat_session_id.get(None) or "_pool_default"
     conn = await get_connection()
     encryptor = get_encryptor(settings.data_dir)
     repo = MCPSourceRepository(conn, encryptor)
     auth_provider = build_oauth_provider_for_source(
         source, repo, csid, source_id=source.id
     )
     ```
   - REPLACE with:
     ```python
     # F6 L3: read csid + tcid from the canonical agent-layer ContextVars.
     # When csid is None (no chat session in the current task scope —
     # e.g. agent build via CLI / REST / tests), pass None to the
     # factory; the factory returns None and the MCPClient connects
     # without auth. The lazy 401 path surfaces MCPAuthRequired at next
     # call_tool, which DOES have per-tool-dispatch context bound via
     # Agent._execute_tool's wrapper. The F5 _pool_default sentinel
     # (which silently routed broadcasts to the most-recently-active
     # session in multi-tab scenarios) is retired in this leg.
     from the_one.agent._context import current_chat_session_id, current_tool_call_id
     from the_one.mcp.oauth import build_oauth_provider_for_source
     csid = current_chat_session_id.get(None)
     tcid = current_tool_call_id.get(None)
     conn = await get_connection()
     encryptor = get_encryptor(settings.data_dir)
     repo = MCPSourceRepository(conn, encryptor)
     auth_provider = build_oauth_provider_for_source(
         source, repo, csid, source_id=source.id, tool_call_id=tcid,
     )
     ```
   - Update the existing comment block at lines ~171-180 to reflect L3's policy (drop the sentinel-fallback explanation; reference the new None-passes-through behavior).

4. **Widen `build_oauth_provider_for_source` to accept `chat_session_id: str | None`.**
   - Find the signature at line 55-62 of `provider_factory.py`:
     ```python
     def build_oauth_provider_for_source(
         source: MCPSource,
         repo: MCPSourceRepository,
         chat_session_id: str,  # ← change to: str | None
         source_id: str | None = None,
         tool_call_id: str | None = None,
         resource_metadata_url: str | None = None,
     ) -> httpx.Auth | None:
     ```
   - Update to `chat_session_id: str | None`.
   - Find the early-return at lines 80-82:
     ```python
     dcr = source.secrets.get("dcr_credentials")
     if not dcr or not dcr.get("client_id"):
         return None
     ```
   - Add a sibling early-return BEFORE the dcr check (so a chat-session-less spawn skips the entire DB-touching path of `make_oauth_handlers` + `MCPSourceTokenStorage` construction):
     ```python
     # F6 L3: when no chat session is bound to the current task, no
     # provider can be constructed — the redirect_handler would have
     # nowhere to broadcast auth_required. Return None; the MCPClient
     # connects without auth and the lazy 401 path surfaces
     # MCPAuthRequired at next call_tool. That dispatch DOES have a
     # csid bound (via the agent layer's _execute_tool wrapper) and
     # routes correctly.
     if chat_session_id is None:
         return None
     dcr = source.secrets.get("dcr_credentials")
     if not dcr or not dcr.get("client_id"):
         return None
     ```
   - Update the module-top docstring at lines 34-38 — retire the "Architectural debt (carried to F6)" sentence:
     ```python
     # OLD:
     # Architectural debt (carried to F6): the factory takes ``chat_session_id`` as
     # a positional parameter because L5 has no agent-layer plumbing for per-tool-
     # dispatch session routing. F6 will replace this with a ContextVar set inside
     # ``Agent._execute_tool`` so the factory can read it without parameter
     # threading. See L5 flight log A17 notes.

     # NEW:
     # F6 L3 retirement (2026-05-08): chat_session_id remains a positional
     # parameter, but the_one/mcp/_pool::_entry_worker now reads it from the
     # canonical the_one.agent._context ContextVar (set by Agent._execute_tool
     # at per-tool-dispatch entry). When the ContextVar is unset (e.g. pool
     # spawn outside a tool dispatch), this factory returns None — no provider
     # construction — and the lazy 401 path surfaces at the next call_tool
     # boundary, where csid IS bound. The F5 _pool_default sentinel is
     # retired; multi-tab cross-routing bug is fixed.
     ```

5. **Wrap `Agent._execute_tool` body in a `try/finally` for `current_tool_call_id` bind.**
   - Find `_execute_tool` in `the_one/agent/core.py` (currently lines 249-279 per L0 retirement).
   - Add module-top import: `from the_one.agent._context import current_tool_call_id` (placed alongside the other agent-layer imports).
   - Wrap the existing body:
     ```python
     async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
         # F6 L3: bind tool_call_id into the per-task ContextVar so the
         # MCP pool's _entry_worker (and the OAuth handlers it wires)
         # can attach the originating tool_call_id to any auth_required
         # broadcast. Reset in finally — the inner try/except blocks
         # handle MCPAuthRequired translation (F5 L4) and generic
         # exception fall-through, both of which return through the
         # outer finally.
         token = current_tool_call_id.set(tool_call.id)
         try:
             try:
                 tool = self.tools.get(tool_call.name)
                 output = await tool.execute(**tool_call.arguments)
                 return ToolResult(tool_call_id=tool_call.id, content=output)
             except MCPAuthRequired as e:
                 # F5 L4 (A10): MCP tool requires user re-authentication.
                 return ToolResult(
                     tool_call_id=tool_call.id,
                     content="<auth required>",
                     metadata={
                         "is_auth_required": True,
                         "source_id": e.source_id,
                         "resource_metadata_url": e.resource_metadata_url,
                         "tool_call_id": tool_call.id,
                         "consent_url": e.consent_url,
                     },
                 )
             except Exception as e:
                 return ToolResult(
                     tool_call_id=tool_call.id,
                     content=f"[error] Tool execution failed: {e}",
                     is_error=True,
                 )
         finally:
             current_tool_call_id.reset(token)
     ```
   - Note: the L0-landed module-top `from the_one.mcp.errors import MCPAuthRequired` import remains; this leg adds a sibling import for `current_tool_call_id`.

6. **Create `tests/test_agent_context.py` with 12 tests.**
   - Test classes:
     - `TestContextVarsCanonicalHome` (3 tests): exists at `the_one/agent/_context.py`; both ContextVars defined; back-compat re-export from `the_one/interfaces/web/app.py` resolves to the same class object.
     - `TestPerToolDispatchBinding` (4 tests): `current_tool_call_id` is None at function-entry-by-default; after `_execute_tool` runs, the value is observable from inside `tool.execute()` via a stub Tool that captures `current_tool_call_id.get(None)`; reset to None after `_execute_tool` returns; reset to None after `_execute_tool` raises (test the `MCPAuthRequired` and generic Exception paths).
     - `TestPoolDefaultSentinelRetired` (2 tests): grep `_pool_default` returns 0 hits in production code; `_entry_worker` no longer references the sentinel.
     - `TestProviderFactoryNoneCsidShortCircuit` (3 tests): `build_oauth_provider_for_source(..., chat_session_id=None)` returns None; the early-return runs BEFORE the `dcr_credentials` check (verified via mock that asserts `source.secrets.get` is NOT called); when `chat_session_id` is a real string, the existing dcr-based dispatch fires unchanged.
   - Sample skeleton:
     ```python
     """L3 — ContextVar canonical-home + per-tool-dispatch binding tests.

     Locks:
       - ContextVar definition lives at the_one.agent._context (canonical home).
       - the_one.interfaces.web.app re-exports for F5 set-site back-compat.
       - Agent._execute_tool binds current_tool_call_id per-dispatch.
       - _pool_default sentinel grep returns zero hits.
       - build_oauth_provider_for_source short-circuits on chat_session_id=None.
     """
     from __future__ import annotations
     import subprocess
     from typing import Any

     import pytest
     from unittest.mock import MagicMock

     from the_one.agent._context import current_chat_session_id, current_tool_call_id


     class TestContextVarsCanonicalHome:
         def test_canonical_definitions_exist(self) -> None:
             from the_one.agent._context import current_chat_session_id, current_tool_call_id
             assert current_chat_session_id.name == "current_chat_session_id"
             assert current_tool_call_id.name == "current_tool_call_id"
             assert current_chat_session_id.get(None) is None
             assert current_tool_call_id.get(None) is None

         def test_app_reexport_resolves_to_same_object(self) -> None:
             from the_one.agent._context import current_chat_session_id as A
             from the_one.interfaces.web.app import current_chat_session_id as B
             assert A is B  # re-export identity preserved

         # ... continue with the other tests
     ```

7. **Update flight log + leg artifact status.**
   - Append L3 Leg Progress entry to `flight-log.md` per the L0/L1/L2 precedent.
   - Set this leg's status to `landed`.

8. **Test gate (per A1/A2/A3 process learning).**
   - `./.venv/bin/python -m pytest tests/test_agent_context.py tests/test_oauth_provider_factory.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_overrides.py tests/test_mcp_tool_provider.py tests/test_db_migration.py tests/test_db_repositories.py tests/test_imports.py tests/test_mcp_client.py -v --timeout=15`
   - `./.venv/bin/ruff check the_one/ tests/`
   - **DO NOT include `tests/test_mcp_pool.py`** in the targeted gate (env-dependent per A1/A2/A3).
   - **DO NOT run the full unfiltered `pytest` suite outside docker.**

## Edge Cases

- **F5 set-site at `app.py:853` reads via the re-export**: the line `csid_token = current_chat_session_id.set(session.id)` continues to work after the move because Python's `from the_one.agent._context import current_chat_session_id` makes the canonical class object accessible at the top-level `current_chat_session_id` name in the `app.py` module. No code change needed at the set-sites.
- **`asyncio.create_task` snapshot semantics**: `_entry_worker` is spawned via `asyncio.create_task` inside `acquire`. The worker inherits the parent task's ContextVar values AT TASK-CREATION TIME. If `Agent._execute_tool` is on the call stack when `acquire` is reached, both `current_chat_session_id` and `current_tool_call_id` are bound — the worker sees the bound values. If agent build (`MCPToolProvider.get_tools_for_agent`) is on the call stack instead, `current_tool_call_id` is None and the worker sees None for tcid. Documented; verified behavior via test.
- **`provider_factory` early-return ordering**: the new `chat_session_id is None` check goes BEFORE the dcr check. Why? `make_oauth_handlers` (called inside the provider construction path) calls `asyncio.get_running_loop().create_future()` — it MUST be inside an async context, and it constructs handlers parameterized on csid. If we let csid=None reach this code path, the handlers would be constructed with a None csid that the broadcast can't route. Better to short-circuit BEFORE constructing anything.
- **Existing F5 OAuth tests that pass `chat_session_id="some_real_id"`**: continue to pass unchanged. The new None-check fires on `chat_session_id is None`; tests passing real strings hit the original early-return logic.
- **F5 OAuth tests that pass `chat_session_id="_pool_default"` literal**: search for `"_pool_default"` in tests. If any test exercises the sentinel literal directly (vs via `current_chat_session_id.get(None) or "_pool_default"`), update or remove. The grep should reveal these.
- **`Agent._execute_tool`'s nested try/except + outer try/finally**: the outer finally runs the ContextVar reset; the inner exception handlers catch and translate. Both `MCPAuthRequired` and generic `Exception` paths return a `ToolResult` value (NOT re-raise), so the function exits via return — finally fires correctly. Test: stub a Tool that raises `MCPAuthRequired` from inside `tool.execute`; assert `current_tool_call_id` is None after the function returns.
- **Pool worker task-pinning trade-off (cycle-2 inherited)**: the OAuth provider built at first acquire is permanently bound to the FIRST acquire's csid+tcid for the entry's lifetime. F6 inherits and documents this; doesn't fix. Cross-session warm-pool routing still depends on F5's "most-recently-active session fallback" in the OAuth handlers — that fallback isn't being removed in L3, just the SENTINEL is. The fallback path retains correctness for the warm-pool case where csid is None at second acquire.
- **`current_tool_call_id` bind during `continue` virtual signal**: per L0 + F5, the `continue` virtual signal in `_dispatch_tool_calls` is handled inline (lines 182-197 of core.py), NOT via `_execute_tool`. So `current_tool_call_id` is NOT set for the continue signal. Acceptable — the continue signal doesn't trigger MCP tool calls.
- **`AgentFactory.create()` lifecycle and ContextVar inheritance**: the factory is invoked from various paths. In the WebSocket path, `_spawn_message_processing` sets csid BEFORE creating an agent; the build's `acquire` calls inherit csid. In REST/CLI paths, csid is None; the build skips OAuth providers per the `chat_session_id is None` short-circuit. Documented; verified behavior.

## Files Affected

- `the_one/agent/_context.py` (NEW) — ~35 LOC.
- `the_one/interfaces/web/app.py` — `current_chat_session_id` definition replaced with re-export (~+3 LOC / ~-12 LOC delta — drop the old definition + docstring block).
- `the_one/mcp/_pool.py` — `_entry_worker` updated (~+5 LOC / ~-3 LOC).
- `the_one/mcp/oauth/provider_factory.py` — type signature widened, early-return added, docstring updated (~+12 LOC / ~-5 LOC).
- `the_one/agent/core.py` — `_execute_tool` wrapped in try/finally; module-top import added (~+10 LOC).
- `tests/test_agent_context.py` (NEW) — ~120 LOC, 12 tests.
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry (~+25 LOC).

Net delta: ~+50 LOC production / ~-20 LOC retirement = ~+30 LOC net production + ~+120 LOC tests ≈ **~+150 LOC total**, slightly under the flight artifact's L3 estimate of ~+195 LOC because the `app.py` docstring deletion is larger than originally scoped.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (each grep / pytest / ruff command produces the expected result)
- [ ] Targeted leg test gate green (per Verification Steps section)
- [ ] Lint clean (`ruff check the_one/ tests/`)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md, do NOT update mission.md, do NOT commit
- [ ] **DO NOT include `tests/test_mcp_pool.py` in the targeted gate** — env-dependent per A1/A2/A3
- [ ] **DO NOT run the full unfiltered `pytest` suite outside docker**
- [ ] Signal `[HANDOFF:review-needed]` once all checklist items above are done

---

## Citation Audit

10 citations verified against current code at leg design time. All `OK`:

| Citation | Classification | Evidence |
|----------|----------------|----------|
| `the_one/interfaces/web/app.py:209-211` — `current_chat_session_id: ContextVar[str \| None] = ContextVar(...)` | OK | grep confirmed at line 209-210 |
| `the_one/interfaces/web/app.py:236, :256` — set/reset in `_spawn_message_processing` | OK | grep confirmed; `:236` set, `:256` reset |
| `the_one/interfaces/web/app.py:853, :875` — set/reset in `_resume_paused_session` | OK | Read directly; `:853` set, `:875` reset |
| `the_one/mcp/_pool.py:181-183` — lazy import + `_pool_default` sentinel | OK | Read directly; matches |
| `the_one/mcp/oauth/provider_factory.py:55-62` — `build_oauth_provider_for_source` signature | OK | Read directly; `chat_session_id: str` at line 58, `tool_call_id: str \| None = None` at line 60 |
| `the_one/mcp/oauth/provider_factory.py:80-82` — early-return on absent dcr | OK | Read directly; matches |
| `the_one/mcp/oauth/provider_factory.py:34-38` — "Architectural debt (carried to F6)" docstring note | OK | Read directly; lines 34-38 contain the verbatim text |
| `the_one/agent/core.py::Agent._execute_tool` lines 249-279 — current implementation | OK | Read directly at L0/L1 design time; F6 L0 module-top `MCPAuthRequired` import already in place |
| `the_one/agent/_context.py` — does NOT exist | OK | Phase 1 grep confirms no `agent/_context*` files |
| `tests/test_agent_context.py` — does NOT exist | OK | grep confirms no such file |
