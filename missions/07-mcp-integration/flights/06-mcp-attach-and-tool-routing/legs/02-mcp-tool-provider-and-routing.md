# Leg: 02-mcp-tool-provider-and-routing

**Status**: completed
**Flight**: [Per-agent MCP attach + tool-routing in agent loop](../flight.md)

## Objective

Land the runtime that turns `AgentConfig.mcp_source_ids` (persisted since F1, ignored at runtime) into agent-callable tools: `MCPClientTool(Tool)` wrapper that dispatches via the F4 pool; `MCPToolProvider` (sibling to `BuiltinToolProvider`, async) that builds the per-agent MCP tool list with prefixed names + override resolution + all 5 failure classes from flight §8; `AgentFactory.create()` integration that registers the MCP tools through the existing tool-name filter.

## Context

**Why this leg, what's locked**: F6 §3 commits `MCPToolProvider` as a sibling class — NOT a `ToolProvider` Protocol implementer — because the Protocol's `get_tools` is sync and per-tool-name keyed; MCP work is async and per-source keyed. F6 §2 commits the prefix scheme `mcp__{normalize(source.name)}__{tool.name}` with a 64-char ceiling. F6 §1 commits source-name keying for `mcp_overrides` (resolver dispatch by name; ids on the wire). F6 §4 commits eager-at-AgentFactory.create — pay N × (acquire + list_tools) at build, accept ~200-600ms upfront. F6 §8 commits 4 failure classes + 1 sub-case (64-char ceiling); class #5 (OAuth-at-build) collapsed into class #2 per cycle-2 H1 because `MCPClient.list_tools` translates 401s to `MCPConnectionError`, NOT `MCPAuthRequired`.

**Override application — overlay-merge for stdio env, replace for streamable-http (deliberate semantic split)**: per flight §1, "operator-set env vars not overridden by the agent pass through unchanged" — so `effective_env = {**source.secrets.get("env", {}), **(resolved.env or {})}`. For streamable-http: `headers` replaces wholesale (the user's override IS the credential set; agent's substituted credential is the FULL credential identity, not a partial overlay); `bearer_token` replaces wholesale (it's a single value, not a dict). **Cycle-1 medium #3 disposition**: F6 §1's "operator-set env vars not overridden... pass through" text is scoped to stdio env semantics; the streamable-http REPLACE-headers semantic is a deliberate departure from that principle, justified by the credential-identity argument (an agent's `mcp_overrides.{source}.headers` represents a FULL header set under the agent's identity; merging operator headers like `X-Tenant-ID: acme` could leak operator-side context that the agent override is meant to fully replace). If F7 surfaces operator pain (e.g. "I want my X-Tenant-ID to flow through"), revisit in a follow-up flight. Documented as carry-forward design choice in the F6 debrief. The resolver's `Substitute` marker dispatches at FIELD level (replace the `env` field's value); the application logic dispatches at DICT-KEY level for stdio env (merge the dict) — two separate operations, both correct.

**`acquire` signature widening**: F4's `acquire(agent_name, source_id) -> MCPClient` calls `_load_source(source_id)` internally. To support per-agent override application, L2 widens to `acquire(agent_name, source_id, *, source_override: MCPSource | None = None)`. When `source_override` is provided, `acquire` uses it INSTEAD of calling `_load_source`. Existing callers (`_evict_all_for_source`-driven re-acquires after OAuth flow) pass nothing → behavior unchanged.

**Cache freshness contract — pool entry pins override at first acquire**: per flight §4-trade-off-detail, F4's pool worker is task-pinned at first acquire. F6's override is ALSO pinned at first acquire of `(agent_name, source_id)`. If the operator edits `mcp_overrides[source.name]` between two `AgentFactory.create()` calls, the FIRST build's override is what the warm pool entry serves until idle reap (300s default). Acceptable for v1 — mid-session override edits don't take effect until next reap or restart. Documented as carry-forward debt in the F6 debrief.

**Prior leg outcomes** (flight log):
- L0 landed: `MCPAuthRequired` canonical at `the_one/mcp/errors.py`; `MCPRegistrationError` defined; lazy imports retired.
- L1 landed: `_overrides.py` with `StdioMCPOverride` + `StreamableHttpMCPOverride` schemas (inverted-`Annotated` placement); `AgentConfig.mcp_overrides` field; v11 ALTER migration.
- L1 anomaly A2: implementer Developer hung 40 min on full-suite pytest. Process learning: subsequent legs run targeted tests only outside docker; full-suite gate deferred to flight-end inside container.

**Stake**: largest leg in the flight. Production ~+450 LOC across 4 files; tests ~+340 LOC (1 new file). Per F5 debrief Process #1, cycle-1 design review is mandatory at this scope.

## Inputs

What exists before this leg runs:

- `the_one/mcp/types.py::MCPTool` — frozen dataclass with `name, description, input_schema, output_schema, annotations`. Constructed by `MCPClient.list_tools`.
- `the_one/mcp/types.py::MCPToolResult` — frozen dataclass with `text, raw, structured, is_error`. Returned by `MCPClient.call_tool`.
- `the_one/mcp/client.py::MCPClient.list_tools` — async; returns `list[MCPTool]`; populates `_tools_cache`. Translates `httpx.HTTPError` and `McpError` to `MCPConnectionError` (per cycle-2 H1 — does NOT raise `MCPAuthRequired` even on 401).
- `the_one/mcp/client.py::MCPClient.call_tool` — async; takes `name: str, arguments: dict[str, Any]`; returns `MCPToolResult`. Has F5 OAuth `except*` translation for 401 → `MCPAuthRequired`.
- `the_one/mcp/_pool.py::acquire(agent_name: str, source_id: str) -> MCPClient` — at line 401. Pre-loads source OUTSIDE the lock at line 427 via `_load_source(source_id)`.
- `the_one/mcp/_pool.py::_entry_worker` lines 148-212 — takes `source: MCPSource, entry: _RegistryEntry`; constructs `MCPClient(source, auth_provider=...)`. Source is currently always the DB-loaded model.
- `the_one/mcp/errors.py::MCPRegistrationError` (added L0) — for prefix collisions and 64-char ceiling.
- `the_one/mcp/errors.py::MCPSandboxError`, `MCPConnectionError`, `MCPVersionMismatch` — failure-class #2 catch types.
- `the_one/mcp/_overrides.py::StdioMCPOverride, StreamableHttpMCPOverride` (added L1) — Pydantic models with `Substitute` markers.
- `the_one/agent/config.py::AgentConfig` — has `mcp_source_ids: list[str]` and `mcp_overrides: dict[str, dict[str, Any]] | None` (added L1).
- `the_one/agent/factory.py::AgentFactory` — `__init__` lines 51-57 (accepts `tool_providers: list[ToolProvider] | None`, defaults to `[BuiltinToolProvider()]`); `create()` lines 59-142 with the registry-build loop at lines 127-131.
- `the_one/tools/base.py::Tool` — base class with `name, description, parameters` attributes; `__init__(config, cross_configs, agent_name)`; abstract `execute(**kwargs) -> str`.
- `the_one/tools/base.py::ToolRegistry::register, get` — registers by name; raises on get-of-unknown-name.
- `the_one/tools/resolver.py::resolve(schema, tool_config, agent_override) -> BaseModel` — Substitute path tested in L1.
- `the_one/db/repositories.py::MCPSourceRepository` — `get(source_id) -> MCPSource` (raises KeyError on miss); `list() -> list[MCPSource]`.
- L0+L1 work uncommitted: 14 modified files + 3 new (per `git status` at L2 design time). L2 lands on top of this.

## Outputs

- `the_one/mcp/_tool.py` (NEW) — `MCPClientTool(Tool)` wrapping an `MCPTool`. Constructor `(mcp_tool, source_id, source_name, agent_name)`. Sets `name = f"mcp__{normalize(source_name)}__{mcp_tool.name}"`, `description`, `parameters`. `execute(**kwargs)` calls `acquire(agent_name, source_id)` then `client.call_tool(...)`, returns `result.text`. Raises `MCPRegistrationError` from `__init__` if the prefixed name exceeds 64 chars. ~120 LOC.
- `the_one/mcp/_tool_provider.py` (NEW) — `MCPToolProvider` class with `async def get_tools_for_agent(self, config: AgentConfig, *, agent_name: str) -> list[Tool]`. Implements all logic per Implementation Guidance steps 3-7. ~280 LOC.
- `the_one/mcp/_pool.py::acquire` — widened with `*, source_override: MCPSource | None = None` kwarg. ~6 LOC delta.
- `the_one/agent/factory.py::AgentFactory.__init__` — accepts `mcp_provider: MCPToolProvider | None = None` arg, defaults to fresh instance. `create()` extends after the existing tool-loop with an MCP registration block. ~30 LOC delta.
- `the_one/mcp/__init__.py` — re-exports `MCPToolProvider` and `MCPClientTool` (canonical-import + convenience-re-export convention). ~4 LOC delta.
- `tests/test_mcp_tool_provider.py` (NEW) — covers all paths. ~340 LOC.
- `tests/test_mcp_pool.py` — adds `test_acquire_with_source_override` to lock the new kwarg behavior. ~30 LOC delta.

## Acceptance Criteria

- [ ] `the_one/mcp/_tool.py::MCPClientTool` exists, subclasses `Tool`, has the `name = f"mcp__{normalize(source_name)}__{mcp_tool.name}"` formula, raises `MCPRegistrationError` from `__init__` if `len(name) > 64`.
- [ ] `MCPClientTool.execute(**kwargs)` calls `acquire(self._agent_name, self._source_id)`, then `client.call_tool(self._original_tool_name, kwargs)`, returns `result.text`.
- [ ] `the_one/mcp/_tool_provider.py::MCPToolProvider.get_tools_for_agent(config, *, agent_name)` exists; takes `AgentConfig`; returns `list[Tool]`.
- [ ] Empty `mcp_source_ids` returns `[]` immediately (no DB calls, no acquires).
- [ ] Each source: load via `MCPSourceRepository.get(source_id)`; on `KeyError` → log `WARNING: agent {agent_name} references deleted MCP source {source_id}; skipping` and continue with next source. Failure class #1.
- [ ] Override resolution: per-source, look up `(config.mcp_overrides or {}).get(source.name)`; pass to `resolve(StdioMCPOverride or StreamableHttpMCPOverride, None, payload)`; raise informatively on schema mismatch (e.g. operator put `bearer_token` under a stdio source — Pydantic `ValidationError` propagates with source name in the error msg).
- [ ] Override application: stdio overlays `resolved.env` onto `source.secrets["env"]` (operator env preserves on collision-absent keys; agent wins on collisions); streamable-http replaces `secrets["headers"]` and `secrets["bearer_token"]` wholesale when set.
- [ ] `acquire(agent_name, source_id, source_override=effective_source)` is called; on `MCPSandboxError | MCPConnectionError | MCPVersionMismatch` → log `WARNING: MCP source {source.name} failed to connect: {exc}; skipping` and continue with next source. Failure class #2 (covers OAuth-at-build per cycle-2 H1).
- [ ] `client.list_tools()` is called; on the same exception classes as #2 → log + skip. Failure class #2 also covers list_tools failures.
- [ ] Each `MCPTool` is wrapped in `MCPClientTool`. If `MCPClientTool.__init__` raises `MCPRegistrationError` (64-char ceiling) — log `WARNING: MCP tool {prefixed_name} exceeds 64-char limit; dropping` AND continue with the source's NEXT tool (NOT next source — inner-loop catch per cycle-1 M2). Failure class #1 sub-case.
- [ ] Prefix-collision: when wrapping a new tool would produce a prefixed name already in the result list → raise `MCPRegistrationError("source-name collision: '{normalized}' produced by sources {a.id} and {b.id}")` AT THE COLLISION SITE. The provider catches at the per-source loop level: log `WARNING: source-name collision '{normalized}' between {a.id} and {b.id}; first source wins, dropping {b.id}` and discard ALL of source B's tools (NOT continue inner-loop — collision is per-source, not per-tool). Failure class #4.
- [ ] Orphan-override warn: at start of `get_tools_for_agent`, if any key in `config.mcp_overrides` does NOT match the `name` of any source resolved from `mcp_source_ids` → log `WARNING: agent {agent_name}'s mcp_overrides references unknown source name '{key}'; ignoring`. (Logs once per unknown key, then proceeds; non-fatal.)
- [ ] `acquire` widened: `the_one/mcp/_pool.py::acquire` accepts `*, source_override: MCPSource | None = None`. When provided, the worker uses the override INSTEAD of `_load_source(source_id)`. When None, behavior unchanged.
- [ ] `AgentFactory.__init__` accepts `mcp_provider: MCPToolProvider | None = None`; defaults to `MCPToolProvider()` when None. Tests can pass `None` explicitly to disable.
- [ ] `AgentFactory.create()` calls `await self.mcp_provider.get_tools_for_agent(config, agent_name=name)` AFTER the built-in tool registration loop; registers each returned tool through the existing `if tool.name not in disabled_names and config.is_tool_enabled(tool.name): registry.register(tool)` filter.
- [ ] Top-level re-exports: `from the_one.mcp import MCPToolProvider, MCPClientTool` succeeds.
- [ ] All ~25 unit tests in `tests/test_mcp_tool_provider.py` pass with `--timeout=15`.
- [ ] `tests/test_mcp_pool.py::test_acquire_with_source_override` passes — the new kwarg path is locked.
- [ ] Existing `tests/test_mcp_pool.py` tests pass UNMODIFIED (the kwarg widening is non-breaking).
- [ ] Existing `tests/test_agent.py` and `tests/test_mcp_client.py` regression tests pass (L0+L1 baseline).
- [ ] `ruff check the_one/ tests/` is clean.

## Verification Steps

```bash
# Module surface
./.venv/bin/python -c "from the_one.mcp import MCPToolProvider, MCPClientTool; print('OK')"

# 64-char ceiling
./.venv/bin/python -c "
from the_one.mcp._tool import MCPClientTool, _normalize_source_name
from the_one.mcp.types import MCPTool
from the_one.mcp.errors import MCPRegistrationError
mt = MCPTool(name='create_or_update_repository_settings', description='', input_schema={}, output_schema=None, annotations=None)
try:
    MCPClientTool(mt, source_id='x', source_name='github_enterprise_internal', agent_name='a')
    print('FAIL — should have raised')
except MCPRegistrationError as e:
    assert 'exceeds 64-character limit' in str(e), e
    print('OK')
"

# Targeted leg gate (under 30s; per L1 anomaly A2 process learning, do NOT run full suite outside docker)
./.venv/bin/python -m pytest tests/test_mcp_tool_provider.py tests/test_mcp_pool.py tests/test_mcp_overrides.py -v --timeout=15

# Regression gate (L0 + L1 baseline)
./.venv/bin/python -m pytest tests/test_imports.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_client.py tests/test_db_repositories.py tests/test_db_migration.py -q --timeout=15

# Lint
./.venv/bin/ruff check the_one/ tests/

# Manual smoke (post-test): construct AgentFactory in a REPL, assert MCP attach surface compiles end-to-end
./.venv/bin/python -c "
from the_one.agent.factory import AgentFactory
from the_one.mcp._tool_provider import MCPToolProvider
fac = AgentFactory(mcp_provider=MCPToolProvider())
print('mcp_provider:', fac.mcp_provider)
print('OK')
"
```

## Implementation Guidance

The order minimizes failed-test feedback loops: data-flow primitives first, then composition, then factory wiring. Each step has self-contained tests.

1. **Widen `the_one/mcp/_pool.py::acquire` with `source_override`.**
   - At line 401 (`async def acquire(agent_name: str, source_id: str) -> MCPClient:`), add the keyword-only argument:
     ```python
     async def acquire(
         agent_name: str,
         source_id: str,
         *,
         source_override: MCPSource | None = None,
     ) -> MCPClient:
     ```
   - At line 427 (`source = await _load_source(source_id)`), branch:
     ```python
     # Pre-load OUTSIDE the lock (cycle-2 medium #2). Different-key
     # acquires must not serialize on the F1 DB read. F6 L2: when
     # ``source_override`` is provided, use it instead of the DB read
     # — MCPToolProvider applies per-agent overrides before calling
     # acquire, and the override-applied source is the one the pool
     # caches for this (agent, source) entry's lifetime.
     source = source_override if source_override is not None else await _load_source(source_id)
     ```
   - Update the docstring at lines 402-419 to mention the new kwarg in 1-2 sentences.
   - **Critical**: the `(agent_name, source_id)` cache key is unchanged. The override is pinned to the FIRST acquire of the key for the entry's lifetime. Document this as a carry-forward of F4's task-pinning trade-off.

2. **Create `the_one/mcp/_tool.py::MCPClientTool`.**
   - Module docstring: explain the wrapping pattern; cite F6 §2 for the prefix; cite the 64-char ceiling.
   - Constants: `_TOOL_NAME_MAX_LEN = 64`. Derived: `_PREFIX_OVERHEAD = len("mcp____")` (7 chars).
   - Helper function `_normalize_source_name(name: str) -> str`:
     ```python
     def _normalize_source_name(name: str) -> str:
         """Return a source name normalized for use in tool-name prefixes.

         F1 source-name validation does not exist today; L2 normalizes
         defensively. Replace any character outside [a-zA-Z0-9_-] with
         underscore. Idempotent on already-normalized names.
         """
         return re.sub(r"[^a-zA-Z0-9_-]", "_", name)
     ```
   - Define `MCPClientTool(Tool)`:
     ```python
     class MCPClientTool(Tool):
         """Tool wrapper that dispatches a server-supplied MCPTool through
         the F4 pool to the appropriate MCPClient.

         Constructed by MCPToolProvider per attached source. The constructor
         enforces the 64-character LLM tool-name ceiling and raises
         MCPRegistrationError if the prefixed name would exceed it; the
         provider catches per-tool and drops the offending tool with a
         WARNING (NOT the entire source's tools).

         Pattern note (cycle-1 medium #2): MCPClientTool is the FIRST
         Tool subclass with dynamic per-instance names. All other
         Tool subclasses (shell, filesystem, sessions, etc.) declare
         `name = "..."` at class level. The base class's `__init__`
         (the_one/tools/base.py:61-99) does NOT touch
         `self.name` / `self.description` / `self.parameters` — it only
         writes `self._config`, `self._cross_configs`, `self._agent_name`.
         So setting instance attrs BEFORE `super().__init__` is safe;
         the base won't clobber them.

         Cache-key trade-off (cycle-1 low #5 fix): the constructor
         takes `effective_source` — the override-applied MCPSource that
         MCPToolProvider built at agent-build time. `execute` passes
         this to `acquire(...)` as `source_override`, so a post-OAuth
         re-acquire (after `_evict_all_for_source`) re-applies the
         agent's override on the next pool spawn. Without this, the
         operator-side DB read inside `_load_source` would silently
         drop the agent's `mcp_overrides`-derived credentials.
         """

         def __init__(
             self,
             mcp_tool: MCPTool,
             source_id: str,
             source_name: str,
             agent_name: str,
             effective_source: MCPSource,
         ) -> None:
             prefixed_name = f"mcp__{_normalize_source_name(source_name)}__{mcp_tool.name}"
             if len(prefixed_name) > _TOOL_NAME_MAX_LEN:
                 raise MCPRegistrationError(
                     f"MCP tool name {prefixed_name!r} exceeds "
                     f"{_TOOL_NAME_MAX_LEN}-character limit; rename the source "
                     "or contact the server author about the tool name"
                 )
             # Set instance-level dynamic attrs BEFORE super().__init__.
             # Safe per the pattern note above — base.__init__ does NOT
             # touch these names.
             self.name = prefixed_name
             self.description = mcp_tool.description or ""
             self.parameters = mcp_tool.input_schema or {"type": "object", "properties": {}}
             self._mcp_tool = mcp_tool
             self._source_id = source_id
             self._source_name = source_name
             self._agent_name = agent_name
             self._original_tool_name = mcp_tool.name
             # Cache the override-applied source so `execute` can pass it
             # as `source_override` to `acquire` — survives post-OAuth
             # `_evict_all_for_source` re-acquires (cycle-1 low #5).
             self._effective_source = effective_source
             # Tool's standard __init__ takes (config, cross_configs, agent_name)
             # — call it with empty defaults; MCPClientTool doesn't participate
             # in the resolver dispatch (tool_overrides keys are built-in tools
             # only; mcp_overrides is its own surface).
             super().__init__(config=None, cross_configs={}, agent_name=agent_name)

         async def execute(self, **kwargs: Any) -> str:
             """Dispatch the tool call through the F4 pool to the MCP server.

             Returns the `[error]` string envelope on failure — matches
             builtin tools' ENVIRONMENTAL-failure pattern (NOT constraint;
             see the_one/tools/base.py:11-16 for Flight 3 Decision 1.5
             — ConstraintError uses `[error] [constraint]`, env failures
             use bare `[error]`). The agent loop's `_execute_tool`
             (the_one/agent/core.py::Agent._execute_tool) wraps the str
             return in `ToolResult(is_error=False)`; the `[error]` prefix
             is the LLM's signal that the result represents a failure
             (per mission constraint #75 small-model-friendly invariant).

             Per F6 §8 failure class #3: source-fails-mid-session — if
             acquire raises MCPSandboxError / MCPConnectionError /
             MCPVersionMismatch during a session (e.g., the warm pool
             entry was reaped and respawn fails), return the env-failure
             envelope. The LLM sees the error and either retries or
             moves on.

             Passes `source_override=self._effective_source` to acquire
             so post-OAuth re-acquires preserve the agent's override
             (cycle-1 low #5 fix).
             """
             try:
                 client = await acquire(
                     self._agent_name,
                     self._source_id,
                     source_override=self._effective_source,
                 )
             except (MCPSandboxError, MCPConnectionError, MCPVersionMismatch) as e:
                 return (
                     f"[error] MCP source {self._source_name!r} unavailable: "
                     f"{type(e).__name__}: {e}"
                 )
             # call_tool propagates MCPAuthRequired (F5) — the agent loop's
             # _execute_tool catches that and translates to metadata. We
             # do NOT catch MCPAuthRequired here; let it propagate.
             result = await client.call_tool(self._original_tool_name, kwargs)
             return result.text
     ```
   - Tests in `tests/test_mcp_tool_provider.py::TestMCPClientTool`:
     - `test_prefixed_name_format` — assert exact name shape for a clean source name.
     - `test_normalize_replaces_invalid_chars` — `"My Source/v2"` → `"My_Source_v2"`; assert prefixed name uses normalized form.
     - `test_64_char_ceiling_raises` — long source/tool name combo raises `MCPRegistrationError`.
     - `test_64_char_ceiling_at_limit_passes` — exactly 64 chars passes.
     - `test_description_falls_back_to_empty` — `mcp_tool.description=None` → empty string.
     - `test_parameters_falls_back_to_empty_schema` — `input_schema=None` or `{}` → `{"type": "object", "properties": {}}`.
     - `test_execute_acquires_and_calls` — mock `acquire` to return a stub MCPClient; assert `call_tool` invoked with `(original_tool_name, kwargs)`; assert return is `result.text`.
     - `test_execute_handles_acquire_failure` — mock `acquire` to raise `MCPSandboxError`; assert returned string starts with `[error]` and includes the source name.

3. **Create `the_one/mcp/_tool_provider.py::MCPToolProvider`.** Single class, single async method `get_tools_for_agent`. Helper functions for override application + orphan-override warn.
   - Module structure:
     ```python
     """Per-agent MCP tool provider.

     Reads AgentConfig.mcp_source_ids + mcp_overrides at agent build
     time; produces the list of MCPClientTool instances the agent's
     ToolRegistry consumes. Sibling to BuiltinToolProvider — NOT a
     ToolProvider Protocol implementer (Protocol is sync; MCP is async;
     keying differs — F6 §3).
     """

     from __future__ import annotations
     import logging
     from typing import Any

     from the_one.agent.config import AgentConfig
     from the_one.config import settings
     from the_one.db.connection import get_connection
     from the_one.db.models import MCPSource
     from the_one.db.repositories import MCPSourceRepository
     from the_one.encryption import get_encryptor
     from the_one.mcp._overrides import StdioMCPOverride, StreamableHttpMCPOverride
     from the_one.mcp._pool import acquire
     from the_one.mcp._tool import MCPClientTool
     from the_one.mcp.errors import (
         MCPConnectionError,
         MCPRegistrationError,
         MCPSandboxError,
         MCPVersionMismatch,
     )
     from the_one.tools.base import Tool
     from the_one.tools.resolver import resolve

     logger = logging.getLogger(__name__)
     ```
   - **Override-application helper** (overlay-merge for stdio env, replace for streamable-http):
     ```python
     def _apply_override(source: MCPSource, override_payload: dict | None) -> MCPSource:
         """Apply a per-agent override to a source.

         Returns a NEW MCPSource with config/secrets updated — does NOT
         mutate the input. The shape depends on transport:

         - stdio: agent's `env` overlays operator's `secrets["env"]`
           dict (agent wins on key collision; operator-only keys
           preserve). Per F6 §1: "operator-set env vars not overridden
           by the agent pass through unchanged."
         - streamable-http: agent's `headers` REPLACES `secrets["headers"]`
           wholesale; agent's `bearer_token` REPLACES `secrets["bearer_token"]`.
           No merge — the override IS the credential set.

         When override_payload is None or empty, returns the source
         unchanged (cheap fast-path).
         """
         if not override_payload:
             return source
         if source.type == "stdio":
             resolved = resolve(StdioMCPOverride, None, override_payload)
             if resolved.env is None:
                 return source
             new_env = {**(source.secrets.get("env") or {}), **resolved.env}
             new_secrets = {**source.secrets, "env": new_env}
             return source.model_copy(update={"secrets": new_secrets})
         elif source.type == "streamable-http":
             resolved = resolve(StreamableHttpMCPOverride, None, override_payload)
             updates: dict[str, Any] = dict(source.secrets)
             if resolved.headers is not None:
                 updates["headers"] = resolved.headers
             if resolved.bearer_token is not None:
                 updates["bearer_token"] = resolved.bearer_token
             return source.model_copy(update={"secrets": updates})
         else:
             # Unknown type — preserve source unchanged. The pool will
             # error on connect; that's the right surface for an
             # unsupported transport.
             return source
     ```
   - **Orphan-override warn helper**:
     ```python
     def _warn_orphan_overrides(
         agent_name: str,
         mcp_overrides: dict[str, dict[str, Any]] | None,
         resolved_source_names: set[str],
     ) -> None:
         """Log a WARNING for each mcp_overrides key that doesn't match
         any resolved source name. Non-fatal — orphans are dropped
         silently downstream."""
         if not mcp_overrides:
             return
         for key in mcp_overrides:
             if key not in resolved_source_names:
                 logger.warning(
                     "agent %r's mcp_overrides references unknown source name %r; ignoring",
                     agent_name,
                     key,
                 )
     ```
   - **Main provider class**:
     ```python
     class MCPToolProvider:
         """Per-agent MCP tool builder. NOT a ToolProvider Protocol
         implementer — see F6 §3 for the sibling-class rationale."""

         async def get_tools_for_agent(
             self,
             config: AgentConfig,
             *,
             agent_name: str,
         ) -> list[Tool]:
             """Return the list of MCPClientTool instances to register
             into agent_name's ToolRegistry.

             Per F6 §8, five failure classes degrade gracefully:
             #1: source deleted (KeyError from repo.get) → log + skip
             #2: source fails to start (acquire/list_tools raises
                 MCPSandboxError/MCPConnectionError/MCPVersionMismatch)
                 → log + skip; covers OAuth-at-build per cycle-2 H1
                 (list_tools translates 401 to MCPConnectionError).
             #3: source fails mid-session (handled in MCPClientTool.execute)
             #4: prefix collision (two source names normalize to same prefix)
                 → log + drop second source's tools.
             #1 sub-case: tool-name length over 64 chars → log + drop tool.

             Empty mcp_source_ids → return [] without DB calls.
             """
             # Cycle-1 medium #4 fix: orphan-warn fires even when
             # mcp_source_ids is empty (otherwise an operator with
             # all-stale config-references would silently miss the
             # diagnostic).
             if not config.mcp_source_ids:
                 _warn_orphan_overrides(agent_name, config.mcp_overrides, set())
                 return []
             conn = await get_connection()
             encryptor = get_encryptor(settings.data_dir)
             repo = MCPSourceRepository(conn, encryptor)

             # Phase A: load all sources; collect names for orphan-warn.
             # Failure class #1 (deleted source) handled here.
             sources: list[MCPSource] = []
             for source_id in config.mcp_source_ids:
                 try:
                     sources.append(await repo.get(source_id))
                 except KeyError:
                     logger.warning(
                         "agent %r references deleted MCP source %r; skipping",
                         agent_name,
                         source_id,
                     )
             resolved_names = {s.name for s in sources}
             _warn_orphan_overrides(agent_name, config.mcp_overrides, resolved_names)

             # Phase B: per source, apply override + acquire + list_tools + wrap.
             # Failure classes #2 and #4 + #1 sub-case handled here.
             tools: list[Tool] = []
             produced_names: dict[str, str] = {}  # prefixed_name → source_id
             for source in sources:
                 # Override application (failure: Pydantic ValidationError;
                 # we do NOT catch — operator schema mismatch is loud, not
                 # graceful-degrade).
                 override_payload = (config.mcp_overrides or {}).get(source.name)
                 effective_source = _apply_override(source, override_payload)

                 # Acquire (failure class #2 — covers connect AND list_tools).
                 try:
                     client = await acquire(
                         agent_name,
                         source.id,
                         source_override=effective_source,
                     )
                     mcp_tools = await client.list_tools()
                 except (MCPSandboxError, MCPConnectionError, MCPVersionMismatch) as e:
                     logger.warning(
                         "MCP source %r failed to connect: %s: %s; skipping",
                         source.name,
                         type(e).__name__,
                         e,
                     )
                     continue

                 # Wrap each MCPTool. 64-char ceiling caught per-tool
                 # (cycle-1 M2 — OTHER tools from the same source survive).
                 # Prefix collision detected here; collision drops ALL
                 # of THIS source's tools (failure class #4).
                 source_tools: list[Tool] = []
                 for mt in mcp_tools:
                     try:
                         tool = MCPClientTool(
                             mt,
                             source_id=source.id,
                             source_name=source.name,
                             agent_name=agent_name,
                             effective_source=effective_source,
                         )
                     except MCPRegistrationError as e:
                         logger.warning(
                             "MCP tool %s exceeds 64-char limit; dropping (operator: rename source or contact server author)",
                             e,
                         )
                         continue
                     # Prefix collision check. If a prior source already
                     # registered this prefixed name, drop ALL of THIS
                     # source's tools (per §8 #4 — first source wins).
                     if tool.name in produced_names:
                         existing_source_id = produced_names[tool.name]
                         logger.warning(
                             "source-name collision %r between %r and %r; first source wins, dropping %r",
                             tool.name,
                             existing_source_id,
                             source.id,
                             source.id,
                         )
                         source_tools.clear()  # discard accumulated tools from THIS source
                         break  # exit inner loop; don't process more of THIS source's tools
                     source_tools.append(tool)

                 # Commit this source's tools to the result. produced_names
                 # populates AFTER the loop (so a same-source same-name
                 # collision — the server returning duplicate tool names —
                 # would be detected as a prefix collision against itself
                 # at the second occurrence; same handling).
                 for tool in source_tools:
                     produced_names[tool.name] = source.id
                     tools.append(tool)

             return tools
     ```

4. **Modify `the_one/agent/factory.py::AgentFactory.__init__` and `create()`.**
   - In `__init__` lines 51-57, add the `mcp_provider` kwarg:
     ```python
     def __init__(
         self,
         store: AgentConfigStore | None = None,
         tool_providers: list[ToolProvider] | None = None,
         mcp_provider: "MCPToolProvider | None" = None,
     ) -> None:
         self.store = store
         self.tool_providers = tool_providers or [BuiltinToolProvider()]
         # F6 L2: MCPToolProvider injected for testability; default to
         # fresh instance. Tests pass None to disable MCP wiring.
         from the_one.mcp._tool_provider import MCPToolProvider as _MCPToolProvider
         self.mcp_provider = mcp_provider if mcp_provider is not None else _MCPToolProvider()
     ```
     The lazy import inside `__init__` is acceptable here (single import, not on a hot path). Module-top would create another circular-chain risk because `mcp._tool_provider` imports `agent.config` indirectly via the resolver.
   - In `create()` AFTER the existing built-in tool registration loop at lines 127-131, add:
     ```python
         # F6 L2: MCP attach. After the built-in tool loop registers
         # disabled-aware tools, the MCPToolProvider produces the
         # per-agent MCP tool list; the same enabled/disabled filter
         # applies (operators can disable an MCP tool by its prefixed
         # name — `disabled_tools=["mcp__github__delete_repo"]`).
         if self.mcp_provider is not None and config.mcp_source_ids:
             mcp_tools = await self.mcp_provider.get_tools_for_agent(
                 config, agent_name=name
             )
             for tool in mcp_tools:
                 if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
                     registry.register(tool)
     ```

5. **Re-export `MCPToolProvider` and `MCPClientTool` from `the_one/mcp/__init__.py`.**
   - Find the existing import block + `__all__`. Add:
     ```python
     from the_one.mcp._tool import MCPClientTool  # noqa: E402
     from the_one.mcp._tool_provider import MCPToolProvider  # noqa: E402
     ```
   - Append `"MCPClientTool"` and `"MCPToolProvider"` to `__all__`.

6. **Add `the_one/mcp/_pool.py::acquire` widening test in `tests/test_mcp_pool.py`.**
   - Add a test that calls `acquire(agent_name, source_id, source_override=fake_source)` and asserts the override was used INSTEAD of the DB load. Mock `_load_source` to assert it was NOT called when `source_override` is provided.

7. **Create `tests/test_mcp_tool_provider.py` with comprehensive coverage.**

   ~28 tests across 4 classes (cycle-1 expanded by 3):

   **`TestMCPClientTool`** (~9 tests):
   - `test_prefixed_name_format` — exact `mcp__source__tool` shape.
   - `test_normalize_replaces_invalid_chars` — special chars become `_`.
   - `test_64_char_ceiling_raises` — at 65 chars raises `MCPRegistrationError`.
   - `test_64_char_ceiling_at_limit_passes` — at exactly 64 chars passes.
   - `test_description_falls_back_to_empty`.
   - `test_parameters_falls_back_to_empty_schema`.
   - `test_execute_acquires_and_calls` — mock `acquire` + stub MCPClient; assert `call_tool` invoked correctly; **assert `acquire` called with `source_override=effective_source` kwarg (cycle-1 low #5 lock-in)**; result returned.
   - `test_execute_handles_acquire_failure` — mock `acquire` to raise `MCPSandboxError`; assert `[error]` envelope; assert string includes source name.
   - `test_execute_propagates_mcp_auth_required` (cycle-1 test gap #1) — stub `acquire` returns a stub client whose `call_tool` raises `MCPAuthRequired`; assert it propagates from `MCPClientTool.execute` (NOT swallowed by the failure-class #3 catch — verify the catch list is exactly `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch)`).

   **`TestApplyOverride`** (~6 tests):
   - `test_apply_override_stdio_overlay_merge` — operator env `{A: 1, B: 2}` + agent env `{B: 3, C: 4}` → `{A: 1, B: 3, C: 4}`.
   - `test_apply_override_stdio_no_payload_returns_unchanged`.
   - `test_apply_override_streamable_http_replaces_headers`.
   - `test_apply_override_streamable_http_replaces_bearer_token`.
   - `test_apply_override_streamable_http_partial_keeps_other_secrets` — only headers set; `secrets["bearer_token"]` and any other key preserve.
   - `test_apply_override_schema_mismatch_propagates` — payload with `bearer_token` for stdio source; `resolve(StdioMCPOverride, ...)` raises `pydantic.ValidationError`; `_apply_override` does NOT catch (operator schema mismatch is loud, not graceful-degrade).

   **`TestMCPToolProvider`** (~12 tests, mock `acquire` and `MCPSourceRepository.get`):
   - `test_empty_source_ids_returns_empty_list_no_db_calls`.
   - `test_empty_source_ids_with_orphan_overrides_logs_warning` (cycle-1 medium #4 fix) — `mcp_source_ids=[]` AND `mcp_overrides={"foo": {...}}`; assert orphan-warn fires even on the early-return path.
   - `test_single_source_no_overrides_produces_prefixed_tools`.
   - `test_two_sources_no_collision_both_register`.
   - `test_failure_class_1_deleted_source_skipped` — repo.get raises KeyError; assert WARNING log + continue.
   - `test_failure_class_2_acquire_raises_skipped` — acquire raises `MCPSandboxError`; assert WARNING log + continue.
   - `test_failure_class_2_list_tools_raises_skipped` — list_tools raises `MCPConnectionError`; assert WARNING log + continue.
   - `test_failure_class_4_prefix_collision_first_wins` — two sources with `name="github"` and `name="GitHub"` both normalize to `github`; assert first source's tools register, second source's drop with WARNING.
   - `test_failure_class_4_collision_drops_partial_first_source_tools` — source B with `[tool_A, tool_B, tool_C]` where tool_B collides with source A's `mcp__github__tool_B`; assert source B's tool_A is dropped too (NOT just tool_B and after — entire source B's tools out).
   - `test_failure_class_1_sub_case_64_char_ceiling_drops_one_tool` — source with 2 tools, one over limit; assert non-violating tool registers, violating drops with WARNING.
   - `test_orphan_override_logs_warning_for_each_unknown_key` (cycle-1 test gap #2) — `mcp_overrides={"unknown1": {...}, "unknown2": {...}}` with no matching source; assert TWO warnings logged (one per key); locks per-key loop, NOT early-exit-on-first-orphan.
   - `test_duplicate_source_id_registers_once` (cycle-1 test gap #3) — `mcp_source_ids=["sid1", "sid1"]`; assert N tools registered, NOT 2N (the prefix-collision path's de-dup behavior).
   - `test_override_applies_correctly` — assert `acquire` was called with `source_override` whose secrets reflect the agent's override (env merged for stdio, headers replaced for streamable-http).

   **`TestAgentFactoryMCPIntegration`** (~3 tests):
   - `test_factory_with_mcp_provider_none_skips_mcp_wiring` — `mcp_provider=None`; agent build still works.
   - `test_factory_default_mcp_provider_constructs` — fresh `AgentFactory()` has a `MCPToolProvider` instance.
   - `test_factory_create_with_mcp_attached_registers_tools` — full path: `AgentConfig` with `mcp_source_ids=[real_id]`, mock `acquire`/`list_tools`; assert agent's registry contains the prefixed tool name; assert `disabled_tools=["mcp__source__bar"]` filter works.

8. **Update flight log.** Append a Leg Progress entry per the L0/L1 precedent. Note any deviations or anomalies.

9. **Test gate (per L1 anomaly A2 — targeted only, NEVER full suite outside docker).**
   - `./.venv/bin/python -m pytest tests/test_mcp_tool_provider.py tests/test_mcp_pool.py tests/test_mcp_overrides.py -v --timeout=15`
   - Regression: `./.venv/bin/python -m pytest tests/test_imports.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_client.py tests/test_db_repositories.py tests/test_db_migration.py -q --timeout=15`
   - `./.venv/bin/ruff check the_one/ tests/`
   - **DO NOT run the full unfiltered `pytest` suite outside docker** — hits the L0 anomaly A1 / L1 anomaly A2 hangs.

10. **Update leg status to `landed`** at the top of this file. Do NOT commit (per agentic-workflow protocol).

## Edge Cases

- **Source with no tools list** (`list_tools()` returns `[]`): the per-source loop runs zero inner iterations; the source contributes zero tools but is otherwise registered. Not an error.
- **Same source listed twice in `mcp_source_ids`**: `repo.get` succeeds twice (returns the same row both times); the inner loop runs twice; the second iteration hits the prefix-collision check (every prefixed name already in `produced_names`); per the design, this drops all of the second iteration's tools. End-state: the source's tools register exactly once. Acceptable behavior; not specifically tested but documented here.
- **Override payload with extra keys** (e.g. operator types `bear_token` instead of `bearer_token`): Pydantic `extra="ignore"` (the project default) silently drops unknown keys. The L1 introspection regression test pinned this; L2 inherits the behavior. Documented in the override-application code comment.
- **Override payload schema mismatch** (e.g. operator puts `{"env": {...}}` for a streamable-http source): `resolve(StreamableHttpMCPOverride, None, payload)` raises `pydantic.ValidationError`. We do NOT catch this in `_apply_override` — operator schema mismatch should surface loud at agent build time, NOT graceful-degrade. The factory's `create()` propagates the error to the caller (chat UI sees agent-build failure with a clear ValidationError message). Test: `test_apply_override_schema_mismatch_propagates`.
- **Source with empty name** (operator created via direct DB INSERT bypassing F1's name validator): `_normalize_source_name("")` returns `""`; prefixed name becomes `mcp____{tool_name}` (4 underscores). 64-char ceiling check still applies. Not a correctness issue, just operator-facing ugliness. Not tested.
- **Pool entry already warm at `get_tools_for_agent` time** (rare, only happens if same agent built twice): `acquire` returns the cached client; the override applied on first build STILL APPLIES (per F4 task-pinning). The second build's override is IGNORED until idle reap. Documented in flight §4-trade-off-detail. Not tested at L2 (would require lifecycle tests; covered better in L5 HAT).
- **`MCPClientTool.execute` and `MCPAuthRequired`**: F5 L4's translation — when `client.call_tool` raises `MCPAuthRequired`, it propagates out of `execute()` (we do NOT wrap it). The agent loop's `_execute_tool` catches it and translates to `ToolResult.metadata.is_auth_required=True`. F6 L2 inherits the F5 path unchanged. Test: stub `acquire` returning a stub client whose `call_tool` raises `MCPAuthRequired`; assert it propagates from `MCPClientTool.execute` (NOT swallowed).
- **Concurrent same-agent same-source acquires** (e.g. agent's tool loop running in parallel for multiple tool calls): the F4 pool's race-fix invariant covers this. L2 inherits.
- **`AgentFactory.create()` failure during MCP attach** (e.g. orphan `mcp_source_ids` references all deleted sources): `get_tools_for_agent` returns `[]` (silently — only warnings log); the agent builds with built-in tools only. NOT a build failure. Per F6 §8 graceful-degrade contract.

## Files Affected

- `the_one/mcp/_tool.py` (NEW) — ~120 LOC.
- `the_one/mcp/_tool_provider.py` (NEW) — ~280 LOC.
- `the_one/mcp/_pool.py` — `acquire` widened (~+6 LOC).
- `the_one/mcp/__init__.py` — re-exports (~+4 LOC).
- `the_one/agent/factory.py` — `__init__` extended; `create()` extended (~+25 LOC).
- `tests/test_mcp_tool_provider.py` (NEW) — ~340 LOC, ~25 tests.
- `tests/test_mcp_pool.py` — `test_acquire_with_source_override` added (~+30 LOC).
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry (~+25 LOC).

Net delta: ~+450 LOC production + ~+370 LOC tests ≈ **~+820 LOC total**, slightly above the flight artifact's L2 estimate (~+760) because the override-application helper + orphan-warn helper grew during design.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (each grep / pytest / ruff command produces the expected result)
- [ ] Targeted leg test gate green (`pytest tests/test_mcp_tool_provider.py tests/test_mcp_pool.py tests/test_mcp_overrides.py --timeout=15`)
- [ ] Regression test gate green (~88 tests across L0+L1 baseline files)
- [ ] Lint clean (`ruff check the_one/ tests/`)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md, do NOT update mission.md, do NOT commit
- [ ] **DO NOT run the full unfiltered `pytest` suite outside docker** — per L1 anomaly A2 process learning
- [ ] Signal `[HANDOFF:review-needed]` once all checklist items above are done

---

## Citation Audit

12 citations verified against current code at leg design time. All `OK`:

| Citation | Classification | Evidence |
|----------|----------------|----------|
| `the_one/mcp/types.py::MCPTool, MCPToolResult` — frozen dataclasses | OK | Read directly; matches |
| `the_one/mcp/client.py::MCPClient.list_tools` — translates 401s to MCPConnectionError | OK | Read directly at lines 352-407; no `MCPAuthRequired` raise path |
| `the_one/mcp/client.py::MCPClient.call_tool` — F5 OAuth except\* translation at lines 480-521 | OK | Read directly; raises `MCPAuthRequired` |
| `the_one/mcp/_pool.py::acquire` line 401 — `acquire(agent_name, source_id) -> MCPClient` | OK | grep confirmed line 401 |
| `the_one/mcp/_pool.py:427` — `source = await _load_source(source_id)` | OK | Read directly; pre-load OUTSIDE the lock per cycle-2 medium #2 |
| `the_one/mcp/_pool.py::_entry_worker` lines 148-212 — accepts `source: MCPSource` | OK | Read directly; matches |
| `the_one/mcp/errors.py::MCPRegistrationError` — added L0 | OK | grep confirmed |
| `the_one/mcp/_overrides.py::StdioMCPOverride, StreamableHttpMCPOverride` — added L1 | OK | git status confirms `the_one/mcp/_overrides.py` is untracked-new in the working tree |
| `the_one/agent/config.py::AgentConfig.mcp_source_ids, mcp_overrides` | OK | git status confirms config.py modified at L1 |
| `the_one/agent/factory.py::AgentFactory.__init__` lines 51-57; `create()` lines 59-142 with registry-build at 127-131 | OK | Read directly |
| `the_one/tools/base.py::Tool, ToolRegistry` | OK | Read directly at L0/L1 design time |
| `the_one/tools/resolver.py::resolve` — Substitute path | OK | Read directly at L1 design time |
