# Flight: Per-agent MCP attach + tool-routing in agent loop

**Status**: landed
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] An agent can be configured to attach to any number of registered MCP sources through the Studio agent editor's MCPs tab; the attached MCP servers' tools become callable by the agent during a session alongside the built-in tools *(F6 lands the runtime; the Studio attach UI is F8)*
- [ ] Per-agent override of MCP source configuration is supported through the same resolver pattern the built-in tools already use, so an operator can have one MCP source globally defined and multiple agents each with their own substituted credential without duplicating the source definition
- [ ] When two attached MCP servers expose tools with the same short name, both remain individually addressable from the agent's tool registry under stable name-spacing rules that prevent collisions and remain readable to the LLM
- [ ] Agent configurations referencing an MCP source that no longer exists, or attached to a server that fails to start, fail gracefully — the agent runtime continues to serve the remaining tools and surfaces the failure to the operator without taking the chat session down
- [ ] Each layer of the integration has automated coverage proving its contract — **the resolver's substitution behavior on MCP-shaped overrides** *(F6 contributes alongside F2's lock-in fixture)*; **the tool-name-spacing logic** *(F6 contributes)*; **OAuth flow** *(F5 contributes; F6 verifies the end-to-end retirement of the F2-known-issue via L5 HAT caplog assertion)*

---

## Pre-Flight

### Objective

Wire `AgentConfig.mcp_source_ids` (persisted since F1, ignored by the runtime today) into the agent's tool registry. Each attached MCP source contributes its tools to the agent under a stable `mcp__{source-name}__{tool-name}` namespace so two attached servers with overlapping short names remain individually addressable. Per-agent credential substitution composes through the same Narrow/Substitute resolver M05 F2 landed — but extended to a parallel `AgentConfig.mcp_overrides` dict (keyed by source name) rather than overloading `tool_overrides` (which keys by tool name and would collide ambiguously when an operator names a source `shell`). Tool-call dispatch routes through F4's pool: `MCPClientTool.execute(**args)` calls `pool.acquire(agent_name, source_id) → MCPClient.call_tool(...)`; `MCPAuthRequired` propagates into `Agent._execute_tool` exactly as F5 designed; the F4 pool's per-`(agent, source)` keying produces distinct bwrap subprocesses for distinct credential overrides for free. The agent loop is unchanged — F6 is a wiring + naming flight, not a loop-semantic change.

The flight also lands three F5-debrief carry-forwards that block clean F6 work: (a) structural break of the `mcp.oauth.__init__ → storage → db.repositories → agent.config → agent` circular import chain so the lazy-import workaround at `agent/core.py:251` and `mcp/client.py:436` retires; (b) replacement of F5's `current_chat_session_id` ContextVar `_pool_default` sentinel with per-tool-dispatch binding inside `Agent._execute_tool` so MCP OAuth `auth_required` broadcasts route to the correct chat session with the actual `tool_call_id` populated; (c) Tier-1 HAT caplog verification of F5 L1's F2-known-issue retirement claim. The third item is the **binary go/no-go** — pass retires the F2-known-issue from the mission; fail files a follow-up flight that reverts F5 L1's dispatcher rewrite.

F6 does NOT touch the Studio MCPs tab UI — the stub at `static/js/areas/studio/mcps-tab.js:7-22` survives this flight and is replaced by F8. F6 produces a backend data model (`AgentConfig.mcp_overrides`) that F8's UI will render. Power-user operators can JSON-edit attach + overrides today through `PUT /api/agents/{name}` once F6 lands; F8 wires the chips and form fields.

### Open Questions

All resolved at flight design (Phase 3 user input + this document). Each carries the mission-level Open-Question reference for traceability.

- [x] **Override surface shape** (mission Open Q L88) → **parallel `mcp_overrides: dict[str, dict[str, Any]] | None` field on `AgentConfig`, keyed by source name**. NOT a `tool_overrides` extension. Rationale: built-in tools key by tool name (`shell`, `read_file`); MCP sources key by source identity. Single dict creates a real collision class — operator names a source `shell` (legal in F1 today, no constraint forbids it) and the resolver cannot disambiguate which surface to dispatch on. Parallel field also makes the MCP override path testable in isolation and keeps `tool_overrides`'s built-in-only contract clear. See §1.

- [x] **Tool-name namespacing** (mission Open Q L89) → **`mcp__{source-name}__{tool-name}` prefix with double-underscore separator**. Stable across server-side tool-list changes (the prefix doesn't depend on the server's internal naming); readable to small LLMs (matches the Anthropic-internal MCP tool naming convention 7B-class models have been exposed to via Claude Code distillation traces); zero collision risk with built-in tools (no built-in carries `mcp__`). Source names are normalized to `[a-zA-Z0-9_]+` at attach time; F1's source-name validator already restricts to a near-identical safe set so this is a documentation note, not a new restriction. Two attached sources whose normalized names would collide raise `MCPRegistrationError` at agent build. Per-agent rename surface (the open question's third option) is NOT shipped — defer if demand surfaces. See §2.

- [x] **MCP source identity for the resolver** (mission Open Q L90) → **by source NAME at compose-time; ids stay on the wire**. `mcp_overrides` is keyed by source name; the factory resolves name → id when calling `pool.acquire`. Operator-facing JSON is human-readable (`{"github": {"github_token": "..."}}`); rename of an attached source orphans its override entry but F1's name-uniqueness guarantee plus the `mcp_source_ids` (id-keyed) reference makes orphans detectable at factory time. See §1, §3.

- [x] **Connection lifecycle binding** (mission Open Q L92) → **lazy on first registry build**. F4's pool already does lazy spawn on `acquire`. F6's `MCPToolProvider.get_tools_for_agent(config)` calls `acquire + list_tools` per-attached-source at `AgentFactory.create()` time so the registry can advertise tool schemas to the LLM (eager AT REGISTRY BUILD, not eager at agent-class construction). First chat turn pays N × (acquire + list_tools) latency where N = # of attached sources; subsequent agent builds within idle TTL hit the warm cache. Acceptable vs LLM call cost (~1-30s typical). NOT eager-at-process-startup. See §4.

- [x] **Per-tool enable/disable within an attached server** (mission Open Q L98) → **NOT in F6 scope**. The existing `AgentConfig.disabled_tools: list[str]` shape works for prefixed names — `disabled_tools: ["mcp__github__delete_repo"]` flows through the existing factory filter at `factory.py:130` unchanged. F8 wires the toggling UI. Power-user JSON-edit path works today through F6. See §2 trade-off.

- [x] **Override schema shape (per-transport)** (mission Open Q L97 — agent-mode override UI) → **`MCPSourceOverride` Pydantic schema in `the_one/mcp/_overrides.py` with all-`Substitute` markers for credential fields**. Two transport-specific variants (stdio: env-var dict; streamable-http: header dict + `bearer_token`). All overridable fields use `Substitute` (no narrowing semantic for credentials — operator either replaces or doesn't). Field-level validation (e.g. env-var key character class) lives on the schema. F8 will render this schema to a form; F6 lands the schema and the resolver wiring. See §1.

- [x] **F5 ContextVar carry-forward** (F5 debrief R4) → **bind `(chat_session_id, tool_call_id)` per-tool-dispatch inside `Agent._execute_tool`; eliminate the `_pool_default` sentinel**. Move the ContextVar from `the_one/interfaces/web/app.py:209-211` to `the_one/agent/_context.py` (canonical home, no `interfaces` dependency from the agent layer). Add `current_tool_call_id` companion. The F5 set-sites at `app.py:236, 853` retain their session-level binding for back-compat; the new per-tool binding nests inside. The pool's `_entry_worker` reads BOTH ContextVars when constructing the OAuth provider. When unset (introspection / pre-warm path), `build_oauth_provider_for_source` returns None — the lazy 401 path still surfaces, but the broadcast no-ops cleanly because there's no chat session to route to. See §5.

- [x] **F6-first-leg structural import break** (F5 debrief R2 + R5 R5_2) → **move `MCPAuthRequired` from `the_one/mcp/oauth/errors.py` to `the_one/mcp/errors.py`** (the canonical MCP errors module). `the_one/mcp/oauth/errors.py` keeps the symbol as a back-compat re-export per the canonical-import + convenience-re-export convention. `agent/core.py:251` and `mcp/client.py:436` lazy imports retire and become module-top imports. The `mcp.oauth.__init__ → storage → db.repositories → agent.config` chain still exists for callers who explicitly import oauth surfaces, but `MCPAuthRequired` no longer drags it in for every consumer of MCP-level signals. See §6.

- [x] **F2-known-issue HAT verification** (F5 debrief R3 + Action Item) → **L5 HAT runs `caplog` assertion: NO `MCPClient transport close failed` WARNING during the full multi-step Tier-1 HAT sequence**. Pass = retire the F2-known-issue entry from `mission.md`. Fail = file follow-up flight to revert F5 L1's `_open_*_transport_stack` helpers + dispatcher rewrite + README §3 scoping update; F2-known-issue stays open with a real diagnosis plan. F6 itself does NOT depend on the retirement — F6's runtime is functional regardless of whether L1's mechanism eliminates the warning under F4-pool routing or not. See §7.

- [x] **HAT inclusion** → **Tier-1 HAT required, blocking** (5-step verification end-to-end against the in-repo OAuth fixture from F5 plus a real local stdio MCP from F4 HAT — `mcp-server-fetch`). Tier-2 alignment-style optional, NOT in this flight (mission Flight 9 covers vibe-coding alignment). HAT step 5 restructured per Architect cycle-1 M5 to test the registry-rebuild-on-create semantic (delete source → rebuild agent → tools absent), NOT in-flight-session eviction (which would require wiring `_evict_all_for_source` into `delete_mcp_source` — out of F6 scope). See §7. CI environment is Linux (matches F4 HAT precedent at `mcr.microsoft.com/playwright/python:v1.58.0-jammy`); `pgrep -f` is reliable in that environment.

- [x] **Final UAT/alignment leg** → **NO**. F6 is backend-only; no UI-touching surface. Mission's optional `uat-and-alignment` template is for UI flights (F8's domain). Skipping keeps F6 atomic. See §Legs.

### Design Decisions

**§1. Override surface — parallel `mcp_overrides` field, source-name-keyed, transport-aware schema with Substitute markers**

`AgentConfig` gains:

```python
# the_one/agent/config.py — F6 L1
mcp_overrides: dict[str, dict[str, Any]] | None = None
```

Same shape as `tool_overrides` (outer key → inner dict), same `None` semantic (no overrides set; locked-down NULL — agent receives the source's defaults verbatim). Outer key is the **source name** (not id); inner dict is the override payload validated by the transport-specific schema.

`the_one/mcp/_overrides.py` (NEW) defines:

```python
from typing import Annotated
from pydantic import BaseModel, ConfigDict
from the_one.tools.resolver import Substitute


class StdioMCPOverride(BaseModel):
    """Per-agent override for a stdio MCP source.

    Substitution-only — credentials don't have a narrowing semantic. The
    `env` dict OVERLAYS the source's `secrets["env"]` at spawn time;
    operator-set env vars not overridden by the agent pass through
    unchanged.

    NOTE: marker placement is `Annotated[T | None, Substitute] = None`,
    NOT `Annotated[T, Substitute] | None = None`. The latter places the
    metadata INSIDE the Union, which Pydantic v2 hoists during model
    construction such that ``model_fields[name].metadata == []`` and the
    resolver's marker scan at ``resolver.py::resolve``'s per-key dispatch
    finds zero markers, raising ``ValueError: ... no Narrow/Substitute
    marker``. Inverting the union (T-pipe-None inside Annotated) keeps the
    marker visible. The L1 test file pins this with a regression
    introspection test that reads ``field_info.metadata`` directly so a
    future schema addition cannot silently regress (per Architect cycle-1
    H1 lock-in).
    """
    model_config = ConfigDict(frozen=True)
    env: Annotated[dict[str, str] | None, Substitute] = None


class StreamableHttpMCPOverride(BaseModel):
    """Per-agent override for a remote streamable-http MCP source.

    Same `Annotated[T | None, Substitute] = None` placement convention as
    StdioMCPOverride — see that docstring for the resolver-marker-visibility
    rationale.
    """
    model_config = ConfigDict(frozen=True)
    headers: Annotated[dict[str, str] | None, Substitute] = None
    bearer_token: Annotated[str | None, Substitute] = None
```

Resolver dispatch reuses `the_one.tools.resolver.resolve(...)` verbatim — no resolver change needed. The factory calls:

```python
override_schema = StdioMCPOverride if source.type == "stdio" else StreamableHttpMCPOverride
override_payload = (mcp_overrides or {}).get(source.name)
resolved_override = resolve(override_schema, None, override_payload)  # tool_config=None: source defaults are NOT shaped like tool_configs
```

The merged result feeds the spawn-time config: stdio overlays `env` onto the bwrap-spawn env after the 8-key allowlist (mission constraint L64); streamable-http injects `headers` + `Authorization: Bearer {bearer_token}` into the httpx client construction. The pool's per-`(agent, source)` keying means agent A's `env=tokenA` and agent B's `env=tokenB` produce distinct bwrap subprocesses — no shared-process credential leak.

- **Trade-off**: source rename orphans the override entry. Mitigation: factory-time orphan detection — if `mcp_overrides` has a key with no matching `source.name` in the registered sources, log a warning naming both. The orphan is silent at runtime (no override applies); the warning surfaces it on next agent build.
- **Why all-Substitute, not Narrow**: credentials don't have a narrowing semantic — an operator-set bearer-token is overridden by the agent's own bearer-token (Substitute), not narrowed to a substring. Future fields with narrowing semantic (e.g. a per-source `read_only` boolean) can use `Narrow` without schema-shape changes.
- **Sentinel pattern preservation**: `__MASKED__` (the F1 round-trip pattern for unchanged secrets) applies through the F8 UI layer when it arrives; F6's API surface for `mcp_overrides` stores values verbatim. F8 layer can normalize `__MASKED__` to "preserve existing" before the API write.

**§2. Tool naming — `mcp__{source-name}__{tool-name}` prefix**

`MCPClientTool` (the `Tool` subclass that wraps an `MCPTool`) constructs its `name` attribute as:

```python
self.name = f"mcp__{normalize(source.name)}__{mcp_tool.name}"
```

`normalize` is the identity transform for source names that match `[a-zA-Z0-9_-]+` (already enforced by F1's name validator); normalization is added defensively so a future relaxation of F1's name rules can't break F6's namespacing.

- **Why `mcp__` prefix, not `mcp:` or `mcp/`**: tool names are surfaced into JSON-Schema `name` fields in the LLM's tool-call protocol. JSON-Schema `name` allows letters, digits, underscores, hyphens; `:` and `/` are NOT universally accepted (some providers normalize them; some reject). Underscores are universal.
- **Why double underscore**: visual separation from the tool name. `mcp__github__list_repos` reads as three tokens at a glance; `mcp_github_list_repos` reads as one. The double-underscore convention also matches Anthropic-internal MCP naming distilled into 7B-class models (mission constraint L74's small-model-friendly invariant).
- **Built-in tool collision**: zero — no built-in tool name carries `mcp__`. `read_file`, `shell`, `web_search` are all bare names.
- **Prefix-collision detection**: when `MCPToolProvider.get_tools_for_agent` would register two tools with the same prefixed name (because two source names normalize to the same string), it raises `MCPRegistrationError("source-name collision: '{normalized}' produced by sources {a.id} and {b.id}")` BEFORE registering the first tool. The error is caught by the factory which logs and skips the second source's tools — first-source-wins, consistent with §4's graceful-degrade contract.
- **Tool-name length cap** (Architect cycle-1 M2): OpenAI's function-calling spec caps tool names at 64 chars; Anthropic's tool-use API has the same ceiling. `mcp__{source}__{tool}` adds 7 chars of prefix overhead. A real combination like source `github_enterprise_internal` (26) + tool `create_or_update_repository_settings` (37) = 70 chars — over the limit. `MCPClientTool.__init__` enforces the 64-char ceiling and raises `MCPRegistrationError("MCP tool name '{name}' exceeds 64-character limit; rename the source or contact the server author about the tool name")` at the wrap site. The error is caught by `MCPToolProvider.get_tools_for_agent` and surfaces as a per-tool skip (the OTHER tools from the same source still register; only the over-limit tool drops with WARNING).
- **No source-name validator at F1** (Architect cycle-1 M1): `MCPSource.name` accepts arbitrary strings today (`db/models.py::MCPSource` has no `Field(..., pattern=...)` constraint; `_validate_mcp_source_config` validates transport config but not name). L2 introduces `normalize()` defensively because no F1 validator exists. Adding a real character-class validator at the API layer is out of F6 scope — defer to routine maintenance. The defensive normalize is the F6 floor.
- **Per-tool disable**: `AgentConfig.disabled_tools: ["mcp__github__delete_repo"]` works through the existing `factory.py:130` filter unchanged. No new disable surface in F6.

**§3. `MCPToolProvider` shape — sibling provider, not Protocol-conforming**

`MCPToolProvider` is NOT registered in `AgentFactory.tool_providers: list[ToolProvider]` because:

1. `ToolProvider.get_tools` is sync; MCP work (acquire + list_tools) is async and fundamentally cannot run sync.
2. The Protocol's `tool_configs` + `agent_overrides` args are tool-name-keyed; MCP needs `mcp_source_ids` + `mcp_overrides` (source-name-keyed). Same shape, different identity → forcing into one signature creates a polymorphic mess.
3. Introspection callers (`/api/tools`) want built-in tool metadata only; calling MCPToolProvider sync would either return [] (silent gap) or block on async work (incorrect).

Instead, `AgentFactory` gains an `mcp_provider: MCPToolProvider | None` constructor arg defaulting to a fresh instance:

```python
class AgentFactory:
    def __init__(
        self,
        store: AgentConfigStore | None = None,
        tool_providers: list[ToolProvider] | None = None,
        mcp_provider: "MCPToolProvider | None" = None,  # F6
    ) -> None:
        self.store = store
        self.tool_providers = tool_providers or [BuiltinToolProvider()]
        # F6: MCPToolProvider injected for testability; default to fresh instance.
        # Tests pass None or a stub to disable MCP wiring.
        self.mcp_provider = mcp_provider if mcp_provider is not None else MCPToolProvider()
```

The factory's existing tool-loop registers built-ins; a new section after it registers MCP tools when applicable:

```python
# After the built-in tool loop in AgentFactory.create() (factory.py:127-131):
if self.mcp_provider is not None and config.mcp_source_ids:
    mcp_tools = await self.mcp_provider.get_tools_for_agent(
        config,
        agent_name=name,
    )
    for tool in mcp_tools:
        if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
            registry.register(tool)
```

`MCPToolProvider.get_tools_for_agent(config: AgentConfig, *, agent_name: str) -> list[Tool]` is async, reads `config.mcp_source_ids`, calls `acquire` per id, calls `list_tools` per client, wraps each `MCPTool` in `MCPClientTool`, applies the resolved `mcp_overrides` to the spawn-time config. Returns the flat list — the factory does the registration filter (consistent with the built-in path).

`agents.md` Tool-Providers section is updated to call out the sibling shape: built-ins behind the sync `ToolProvider` Protocol; MCP behind the async `MCPToolProvider` class. Both feed the same `ToolRegistry`.

**§4. Connection lifecycle — lazy spawn at first registry build, cache reuse within idle TTL**

`AgentFactory.create()` calls `acquire(agent_name, source_id)` per attached source. The pool either spawns the bwrap subprocess (cold path, ~50-200ms) or returns the warm `MCPClient` (warm path, ~µs). `client.list_tools()` runs against the active session — F2-cached on `MCPClient._tools_cache` so subsequent reads in the same agent build hit memory.

Per-(agent, source) keying in the F4 pool means agent A's first build pays cold spawn for source X; agent B's first build (different override → different subprocess) ALSO pays cold spawn — but each subsequent agent build for the same `(agent, source)` pair within idle TTL hits warm. This is the right semantic given mission constraint L65 ("Idle-TTL reaper pattern, not on-demand").

- **Trade-off**: an agent attached to N sources pays N × cold-spawn on first build. Mission constraint L65 accepts this cost. Bounded by N (typical: 1-3 attached MCPs per specialized agent); each spawn is ~50-200ms; total ~200-600ms upfront. Acceptable vs LLM call cost (~1-30s typical).
- **Failure during build**: any single source's `acquire` failure (sandbox refusal, MCPVersionMismatch, timeout) is caught + logged + skipped per §8 graceful-degrade. The agent build continues with the remaining sources. The agent loop runs without the failed source's tools.
- **Tool list freshness**: `MCPClient._tools_cache` is set inside `list_tools`; subsequent `call_tool` reads cache for unknown-tool detection. `list_tools` re-fetches on every call (no client-side cache invalidation). F6 builds the registry once at agent-create; tool list shape is frozen for the agent's lifetime — server-side tool changes don't surface until the next agent build.
- **OAuth-protected source at registry build — diagnostic-name caveat** (Architect cycle-1 M4 + cycle-2 H1): an OAuth-protected streamable-http source whose `dcr_credentials` are missing (or whose stored access_token is expired and refresh fails) DOES NOT surface as `MCPAuthRequired` at registry build. Verified empirically in cycle 2: `MCPClient.list_tools` (`client.py:352-385`) catches `McpError` and `httpx.HTTPError` and translates them to `MCPConnectionError` with no `except*` block for `OAuthFlowError` / `httpx.HTTPStatusError`-401 — only `MCPClient.call_tool` has the OAuth-aware translation. `MCPClient.connect` (`client.py:210-262`) likewise wraps every `Exception` from `initialize` into `MCPConnectionError`. So OAuth-401-at-build presents as a generic connection failure, NOT a typed auth-required signal. **Policy**: registry-build OAuth failures are handled by §8 failure class #2 (source-fails-to-start; `MCPConnectionError` catch). The diagnostic message is "MCP source X failed to connect: ..." rather than "requires authorization", which is acceptable degradation — the operator's resolution path is the same: complete the OAuth flow on a tool dispatch (which DOES use `call_tool`'s OAuth-aware path), then rebuild the agent. F6 does NOT extend `list_tools` / `connect` with parallel OAuth translation — that would be a F2/F4 client-surface change, out of F6 scope. If operator UX demand surfaces post-F6 for a typed "needs OAuth" diagnostic at build, file as a follow-up flight that adds the `except*` blocks to `list_tools` + `connect`. The trade-off (lossy diagnostic) is documented in the F6 debrief.

**§4-trade-off-detail. Pool worker is task-pinned at first acquire** (Architect cycle-1 M3): F4's `_entry_worker` is spawned via `asyncio.create_task` at first acquire of a `(agent, source)` key. Python's `asyncio.create_task` snapshots the parent task's context AT CREATION; subsequent ContextVar updates in the parent do not propagate. So the OAuth provider built inside `_entry_worker` is permanently bound to the FIRST acquire's `current_chat_session_id` value for the entry's lifetime (default 5 min idle TTL). A second tool call from a DIFFERENT chat session reuses the warm client — its OAuth provider, if it triggers an `auth_required` broadcast, routes to the FIRST session, NOT the current one. This is a **pre-existing F5 issue inherited by F6**, not introduced. F6's per-tool-dispatch ContextVar bind (§5) addresses the silent-drop fallback (`_pool_default` retirement) but does NOT fix cross-session routing — F5's "most-recently-active session fallback" in OAuth handlers still backstops cross-session cases. Re-keying the pool on `(agent, source, chat_session_id)` would resolve this but is a F4 contract change out of F6 scope. Documented as carry-forward debt in the F6 debrief.

**§5. ContextVar relocation + per-tool-dispatch binding**

Move `current_chat_session_id` from `the_one/interfaces/web/app.py:209-211` to `the_one/agent/_context.py` (NEW). Add `current_tool_call_id: ContextVar[str | None]`. The new module is the canonical home; `app.py` re-exports for back-compat with F5's set-sites.

```python
# the_one/agent/_context.py (NEW)
from contextvars import ContextVar

current_chat_session_id: ContextVar[str | None] = ContextVar(
    "current_chat_session_id", default=None
)

current_tool_call_id: ContextVar[str | None] = ContextVar(
    "current_tool_call_id", default=None
)
```

`Agent._execute_tool` binds BOTH ContextVars before `tool.execute(**kwargs)`:

```python
# the_one/agent/core.py::Agent._execute_tool — F6 L3 modifications
async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
    from the_one.mcp.errors import MCPAuthRequired  # F6 L0: was lazy, now module-top in this leg
    from the_one.agent._context import current_tool_call_id  # NEW

    tool_token = current_tool_call_id.set(tool_call.id)
    try:
        try:
            tool = self.tools.get(tool_call.name)
            output = await tool.execute(**tool_call.arguments)
            return ToolResult(tool_call_id=tool_call.id, content=output)
        except MCPAuthRequired as e:
            # ... existing F5 L4 metadata-shaped return ...
        except Exception as e:
            # ... existing F5 L4 error envelope ...
    finally:
        current_tool_call_id.reset(tool_token)
```

`current_chat_session_id` does NOT need a per-tool-dispatch bind because the session-level bind from `_spawn_message_processing` already covers the tool-dispatch nested scope (ContextVar lookup walks outward through the task's context).

`the_one/mcp/_pool.py::_entry_worker` (the OAuth provider construction site) drops the `_pool_default` sentinel:

```python
# Before (F5):
csid = current_chat_session_id.get(None) or "_pool_default"

# After (F6 L3):
csid = current_chat_session_id.get(None)
# csid is None or a real session id; build_oauth_provider_for_source already
# accepts None and returns None when unset (no provider → lazy 401 path
# surfaces; broadcast no-ops cleanly when no chat session)
```

`build_oauth_provider_for_source(..., chat_session_id: str | None, ...)` is updated to accept `None` and return `None` when `chat_session_id is None` (introspection / pre-warm path — no chat session to route to). The OAuth handlers' lazy `_sessions` lookup (F5) keeps the "most-recently-active session fallback" for back-compat with the existing F5 set-sites at `app.py:236, 853`.

- **Trade-off**: when an OAuth provider is constructed during agent-build (lazy spawn at registry build, §4) BEFORE any tool call, `current_tool_call_id` is None — so the broadcast (if it fires) carries `tool_call_id=None`. F6 accepts this: registry-build OAuth events are pre-tool-call by definition; the chat UI can render them as "agent-build OAuth" rather than "tool-call OAuth" if it cares to differentiate. F6 doesn't add new chat-UI surface for this distinction.
- **Backwards compat**: F5's set-sites at `app.py:236, 853` continue to bind `current_chat_session_id`. F6 adds nested binds inside `Agent._execute_tool`. Nesting is correct — ContextVar's outer scope is preserved by `set/reset` token semantics.

**§6. Circular-import structural break — move `MCPAuthRequired` to `the_one/mcp/errors.py`**

The chain F5 documented (`agent.core → mcp.oauth.errors → mcp.oauth.__init__ → mcp.oauth.storage → db.repositories → agent.config → agent`) exists because `mcp.oauth.__init__` eagerly imports `storage` (line 31) which imports `db.repositories` (transitively) which imports `agent.config` (line 12). Importing ANY symbol from `mcp.oauth.*` triggers this chain because Python loads the package's `__init__` before resolving submodules.

`MCPAuthRequired` is the symbol the agent layer needs to import — it's an MCP-level control-flow signal (the agent loop catches it to translate to `metadata.is_auth_required`), NOT an OAuth-internal type. Per the project's `canonical-import + convenience-re-export` convention (agents.md:185), it belongs in the canonical MCP errors module:

- Move definition: `the_one/mcp/oauth/errors.py::MCPAuthRequired` → `the_one/mcp/errors.py::MCPAuthRequired`
- `the_one/mcp/oauth/errors.py` re-exports for back-compat: `from the_one.mcp.errors import MCPAuthRequired`
- `the_one/mcp/oauth/__init__.py:27`: `from the_one.mcp.oauth.errors import MCPAuthRequired` continues to work via the re-export
- Replace lazy imports with module-top:
  - `the_one/agent/core.py:251` (in `_execute_tool`): module-top `from the_one.mcp.errors import MCPAuthRequired`
  - `the_one/mcp/client.py:436` (in `call_tool`): module-top `from the_one.mcp.errors import MCPAuthRequired`
- Drop the lazy-import comment blocks (lines 8-13 of `agent/core.py`; lines 41-45 of `mcp/client.py` — verify ranges at L0 implementation time).

**Verification**: import-time grep `python -c "import the_one.agent.core"` should NOT trigger `mcp.oauth.__init__` evaluation (verifiable by adding a `print` in `mcp/oauth/__init__.py` and running the import — or by `python -c "import sys; import the_one.agent.core; assert 'the_one.mcp.oauth' not in sys.modules"` as an automated test in `test_imports.py`). The `mcp.oauth.__init__ → storage → db.repositories → agent.config` chain still exists for explicit oauth-surface imports (it has to — `provider_factory` legitimately needs `MCPSourceRepository`); F6 just keeps `MCPAuthRequired` consumers off it.

- **Trade-off**: a future refactor that wants to split `MCPAuthRequired` further (e.g. distinct exception types per failure mode) needs to keep the `the_one/mcp/errors.py` canonical home. F6 documents the home in the docstring + `agents.md::Module Map` table.

**§7. HAT — Tier-1 required, blocking on caplog assertion**

Five-step verification, runs in CI under `make test`:

1. **Pre-state**: register an MCP source via the F1 admin path (`POST /api/mcp-sources`) — both a stdio source (the F4 HAT's `mcp-server-fetch`) and a streamable-http source (F5's in-repo OAuth fixture). Configure agent A with both attached (`mcp_source_ids=[stdio_id, http_id]`); configure agent B with the same stdio source attached but different `mcp_overrides[stdio.name].env` (different per-agent env-var override → different bwrap PIDs).
2. **Tool-list visibility**: `await AgentFactory.create("agent-a")`; assert `agent.tools.all_schemas()` contains `mcp__{stdio.name}__fetch` and at least one `mcp__{http.name}__*` entry; assert NO collision between `mcp__{stdio.name}__*` and `mcp__{http.name}__*` (different prefixes).
3. **Tool-call dispatch**: agent A makes a tool call to `mcp__{stdio.name}__fetch(url=...)`; assert the bwrap subprocess receives the call (verify via `pgrep -f mcp-server-fetch` shows ONE PID); assert the result text comes back through `MCPToolResult.text` → `Tool.execute` → `Agent._execute_tool`'s success path; assert `_deferred_tool_calls` stays None (no auth_required for stdio).
4. **Per-agent isolation**: agent B makes a tool call to the same stdio source; assert `pgrep -f mcp-server-fetch` shows TWO distinct PIDs (one per agent); assert agent B's bwrap env contains agent B's override, NOT agent A's.
5. **Graceful degrade — restructured per Architect cycle-1 M5**: delete the http source via `DELETE /api/mcp-sources/{id}`. (Note: F4 / F1's `delete_mcp_source` does NOT call `_evict_all_for_source` — `api.py::delete_mcp_source` removes the DB row only; warm pool entries continue serving until idle reap. This is documented behavior, NOT a bug.) Then **rebuild agent A** (`agent_A_v2 = await factory.create("agent-a")`); assert `agent_A_v2.tools.all_schemas()` no longer contains any `mcp__{http.name}__*` entries (the per-source `MCPSourceRepository.get` raised `KeyError` which `MCPToolProvider.get_tools_for_agent` caught + logged + skipped). `mcp__{stdio.name}__fetch` continues to be present. The original `agent_A` instance (the pre-deletion build) still has the http tools registered and pointed at a warm pool entry — its next `call_tool` would either succeed (warm cache) or fail at idle-reap-then-respawn (when respawn calls `_load_source` and gets KeyError); F6 does NOT add cross-instance eviction logic and accepts the documented behavior. The HAT step's invariant tests the registry-rebuild semantic, NOT the in-flight-session eviction semantic.

**Caplog gate (F5 debrief R3 + F6 acceptance criterion)**: throughout steps 1-5, capture `pytest caplog` records at `WARNING` level for `the_one.mcp.client`. Assert `assert not any("MCPClient transport close failed" in r.message for r in caplog.records)`. PASS = retire the F2-known-issue entry from `mission.md::Known Issues`. FAIL = file follow-up flight per §7-fail.

**§7-fail. If caplog assertion fails**

The follow-up flight (NOT planned in F6 itself; filed only on fail) reverts F5 L1's:
- `_open_streamable_http_transport_stack` helper at `streamable_http.py:171`
- `_open_stdio_transport_stack` helper at `stdio.py:368`
- `MCPClient._transport_connect` dispatcher consumption of the helpers
- `the_one/mcp/README.md §3` scoping update

The mission's F2-known-issue entry stays open with a real diagnosis plan. F6 itself is NOT blocked by an L1 revert — F6 lands the attach + tool-routing work; whether or not L1's mechanism eliminates the warning under F4-pool routing is independent.

**Tier-2 (manual / not required)**: live GitHub MCP via F5's manual-entry path with agent A attached; verify a real tool call succeeds end-to-end through F6's routing. Documented in `tests/HAT.md` per F5 precedent; not run in CI.

**§8. Graceful degrade — failure isolation per source**

Four failure classes (cycle-1 said five; cycle-2 collapsed #5 into #2 because `list_tools` translates 401s to `MCPConnectionError` rather than propagating `MCPAuthRequired`); each handled at a distinct site with a distinct surface:

1. **Source-deleted-after-attach** (`mcp_source_ids` references a `source_id` that no longer exists in the DB): `MCPToolProvider.get_tools_for_agent` catches `KeyError` from `MCPSourceRepository.get`. Logs `WARNING: agent {name} references deleted MCP source {source_id}; skipping`. Continues with remaining sources.
2. **Source-fails-to-start** (`acquire` or `list_tools` raises `MCPSandboxError` / `MCPConnectionError` / `MCPVersionMismatch`): `MCPToolProvider.get_tools_for_agent` catches the named exception classes, logs `WARNING: MCP source {source.name} failed to connect: {exc}; skipping`, continues. **Includes OAuth-protected sources whose tokens are missing/expired at build time** — `list_tools` translates the 401 to `MCPConnectionError` (not `MCPAuthRequired`), so the diagnostic name is "failed to connect" rather than "requires authorization" (per §4 OAuth-at-build caveat). The operator's resolution is the same: complete OAuth on a tool dispatch (which DOES use `call_tool`'s OAuth-aware path), then rebuild. The agent build succeeds with the remaining sources' tools.
3. **Source-fails-mid-session** (an attached source's `MCPClient` is evicted mid-session and the next `acquire` fails): `MCPClientTool.execute` catches the named exception class, returns `ToolResult(content=f"[error] MCP source {source.name} unavailable: {exc}", is_error=True)`. The agent loop continues. The LLM sees the error and either retries or moves on.
4. **Tool-name prefix collision** (two source names normalize to the same prefix): `MCPRegistrationError` raised at registry build by `MCPToolProvider.get_tools_for_agent`; provider catches, logs `WARNING: source-name collision '{normalized}' between {a.id} and {b.id}; first source wins, dropping {b.id}`. First source's tools register; second source's tools drop. Agent build continues.

Plus a sub-case of #1: **Tool-name length over 64-char limit** (the OpenAI/Anthropic ceiling): `MCPClientTool.__init__` raises `MCPRegistrationError`. **Catch site is the inner `for mcp_tool in tools` loop INSIDE `get_tools_for_agent`** (per Architect cycle-2 suggestion — must be inner-loop catch, not around `acquire + list_tools`, so OTHER tools from the same source still register). Logs `WARNING: MCP tool {prefixed_name} exceeds 64-char limit; dropping (operator: rename source or contact server author)`, drops the offending tool, continues with the rest of the source's tools.

The F4 pool's failure-mode handling (`entry.failure` propagation through `entry.client_ready`) carries failures from `_entry_worker` to the `acquire` caller as a re-raised exception. F6 doesn't change pool internals; it consumes the existing surface.

**§9. Module placement — slim wiring layer over F2-F5 primitives**

```
the_one/mcp/
├── _tool_provider.py    # NEW (F6 L2): MCPToolProvider class — per-agent tool-list builder
├── _tool.py             # NEW (F6 L2): MCPClientTool(Tool) — wraps MCPTool, dispatches via pool
├── _overrides.py        # NEW (F6 L1): StdioMCPOverride + StreamableHttpMCPOverride Pydantic schemas
├── errors.py            # MODIFIED (F6 L0): MCPAuthRequired moves here from oauth/errors.py;
│                        #   MCPRegistrationError NEW for §2 collision/§8 source-error surface
├── oauth/errors.py      # MODIFIED (F6 L0): re-exports MCPAuthRequired for back-compat
└── _pool.py             # MODIFIED (F6 L3): drops `_pool_default` sentinel; reads ContextVars from
                         #   the_one/agent/_context (was: from the_one.interfaces.web.app)

the_one/agent/
├── _context.py          # NEW (F6 L3): canonical home for current_chat_session_id +
│                        #   current_tool_call_id ContextVars
├── core.py              # MODIFIED (F6 L0 + L3): module-top MCPAuthRequired import; per-tool-
│                        #   dispatch ContextVar bind in _execute_tool
├── config.py            # MODIFIED (F6 L1): mcp_overrides field added
└── factory.py           # MODIFIED (F6 L2): mcp_provider injection + per-agent MCP tool wiring;
                         #   uses async path; orphan-override warn at compose time

the_one/db/
└── schema.py            # MODIFIED (F6 L1): v11 migration adds mcp_overrides column to agents
```

**Touchpoints OUTSIDE the new modules** (per F5 debrief R3 — full surface, not just new package):

- `the_one/db/repositories.py::SQLiteAgentStore.save/_row_to_config` — read/write `mcp_overrides` column (L1)
- `the_one/interfaces/web/app.py:209-211` — replace ContextVar definition with re-export from `the_one.agent._context`; existing set-sites at `:236, :853` keep working unchanged via the re-export (L3)
- `the_one/mcp/oauth/provider_factory.py::build_oauth_provider_for_source` — accept `chat_session_id: str | None`; return None when csid is None (L3)
- `the_one/mcp/_pool.py::_entry_worker` — drop `_pool_default` sentinel; read ContextVar from new home (L3)
- `the_one/mcp/__init__.py` — re-export `MCPAuthRequired`, `MCPRegistrationError` (L0); re-export `MCPToolProvider`, `MCPClientTool` (L2)
- `the_one/agents.md::Module Map` + `::Tool Providers` + `::Project Conventions` — document new modules; document the sibling-provider shape; (optional L6) add `same-task-anyio-cm-ownership` 5th convention

### §10. Per-file LOC budget (F5 debrief R3 — full-surface enumeration)

| File | New (LOC) | Modified (LOC) | Tests touched | Leg |
|------|-----------|----------------|----------------|-----|
| `the_one/mcp/errors.py` | +25 | — | 0 | L0 |
| `the_one/mcp/oauth/errors.py` | — | -8/+3 | 0 | L0 |
| `the_one/agent/core.py` | — | -10/+8 | `tests/test_agent.py` (light) | L0 |
| `the_one/mcp/client.py` | — | -8/+3 | `tests/test_mcp_client.py` (light) | L0 |
| `the_one/mcp/__init__.py` | — | +6 | — | L0+L2 |
| `tests/test_imports.py` (NEW) | +40 | — | new test file | L0 |
| `the_one/mcp/_overrides.py` | +90 | — | tested in L2 | L1 |
| `the_one/agent/config.py` | — | +12 | `tests/test_agent_config.py` if exists, else covered downstream | L1 |
| `the_one/db/schema.py` | — | +20 | `tests/test_db_schema.py` if exists | L1 |
| `the_one/db/repositories.py` | — | +12 | `tests/test_db_repositories.py` (or add) | L1 |
| `tests/test_mcp_overrides.py` (NEW) | +180 | — | new test file | L1 |
| `the_one/mcp/_tool.py` | +120 | — | covered downstream | L2 |
| `the_one/mcp/_tool_provider.py` | +260 | — | covered downstream | L2 |
| `the_one/agent/factory.py` | — | +30 | `tests/test_agent_factory.py` (or add) | L2 |
| `tests/test_mcp_tool_provider.py` (NEW) | +320 | — | new test file | L2 |
| `the_one/agent/_context.py` | +35 | — | covered downstream | L3 |
| `the_one/agent/core.py` | — | +18 (separate from L0 changes) | `tests/test_agent.py` (per-tool ctx tests) | L3 |
| `the_one/interfaces/web/app.py` | — | -12/+4 (remove inline def, add re-export) | `tests/test_app_websocket_*.py` regression | L3 |
| `the_one/mcp/_pool.py` | — | -6/+8 | `tests/test_mcp_pool.py` adjust | L3 |
| `the_one/mcp/oauth/provider_factory.py` | — | +10 | `tests/test_oauth_*.py` regression | L3 |
| `tests/test_agent_context.py` (NEW) | +120 | — | new test file | L3 |
| `tests/HAT.md` | — | +90 (new Tier-1 procedure) | — | L5 |
| `tests/test_mcp_attach_hat.py` (NEW, automated portion) | +250 | — | new test file | L5 |
| `the_one/agents.md` | — | +80 | — | L5 (or L6) |
| `the_one/mcp/README.md` | — | +60 (F6 wiring section) | — | L5 (or L6) |

**Production LOC**: new modules ~+530 (`errors.py +25` + `_overrides +90` + `_tool +120` + `_tool_provider +260` + `_context +35`); modified files net ~+90 → **~+620 net production** (revised post-Architect cycle-1 LOC spot-check; the original `+560/+600` undercounted `_tool_provider` by ~60 LOC because the §8 five failure classes each need try/except + log + skip plus orphan-warn plus prefix-collision plus 64-char ceiling plus the override resolver dispatch)
**Test LOC**: ~+910 new + adjustments to ~6 existing files
**Total flight LOC**: ~+1530-1730

### Prerequisites

- [x] F1, F2, F3, F4, F5 `completed`
- [x] `AgentConfig.mcp_source_ids` persisted (`agent/config.py:57`)
- [x] `AgentConfig.tool_overrides` shape locked (`agent/config.py:65`)
- [x] `pool.acquire(agent_name, source_id)` operational (`the_one/mcp/_pool.py`)
- [x] `MCPClient.list_tools` + `call_tool` operational (F2 + F5)
- [x] `MCPAuthRequired` propagation site in `Agent._execute_tool` (F5 L4)
- [x] `Agent.resume_after_auth` entry point (F5 L3)
- [x] `the_one.tools.resolver.resolve` Narrow/Substitute dispatch (M05 F2)
- [x] F1 source-name uniqueness validator
- [x] F4 pool's per-`(agent, source)` keying produces distinct subprocess for distinct overrides
- [x] F5 ContextVar `current_chat_session_id` in place at `app.py:209-211`
- [x] In-repo OAuth fixture from F5 L5 (for HAT step 1's streamable-http arm)
- [x] `mcp-server-fetch` installable in dev container (used by F4 HAT)
- [ ] Architect-approved at Phase 5b (this document, post-design-review)

### Pre-Flight Checklist

- [x] All open questions resolved (10 above)
- [x] Design decisions documented (§§1-10; §§1, §2, §4, §5, §7 step 5, §8 substantively revised post-cycle-1)
- [x] Prerequisites verified
- [x] Validation approach defined (test strategy in legs L0-L5)
- [x] Legs defined (see In-Flight § Legs)
- [x] Architect design review cycle 1 — needs rework. 1 high (`Annotated[X, Substitute] | None` strips marker — schema fix to `Annotated[X | None, Substitute] = None`) + 5 medium (no F1 source-name validator, 64-char tool-name ceiling, pool-worker task-pinning at first acquire, eager tool-list at agent BUILD with OAuth source policy, HAT step 5 ambiguity with `delete_mcp_source` not evicting warm entries) + 4 low. All resolved inline (§1 schema fix; §2 normalize-as-defense + 64-char ceiling + MCPRegistrationError per-tool drop; §4-trade-off-detail documents task-pinning as inherited F5 debt; §4 + §8 add OAuth-at-build policy with graceful-degrade-skip; §7 step 5 restructured to "delete + rebuild → tools absent"; §10 LOC table updated; L1 leg cites v8 ALTER pattern; test file references corrected to existing `test_schema.py` / `test_store.py`).
- [x] Architect design review cycle 2 — approve with changes. 1 NEW high (cycle-1 §4/§8-class-#5 premise wrong — `MCPClient.list_tools` does not propagate `MCPAuthRequired`; only `call_tool` has the OAuth-aware translation). Resolved inline by collapsing failure class #5 into class #2 — registry-build OAuth failures present as `MCPConnectionError` with diagnostic "failed to connect" rather than "requires authorization"; operator resolution path unchanged. §4 OAuth-at-build paragraph reframed to document the diagnostic-name caveat. Cycle-2 also confirmed the §1 schema fix is correct, the §2 inner-loop catch site is the right placement, the §4-trade-off-detail task-pinning analysis holds, the §7 step 5 restructure is coherent, and the §10 LOC table is defensible. No cycle-3 required — cycle-2 fix is a doc/wording change, not a structural redesign.
- [x] User approval (Phase 6) — granted 2026-05-08; flight transitioned `planning` → `ready`

---

## In-Flight

### Technical Approach

Six legs, all autonomous-implementation-friendly except L5 (HAT — interactive verification with caplog gate):

1. **L0 — break-circular-imports** (smallest leg). `MCPAuthRequired` moves from `mcp/oauth/errors.py` to `mcp/errors.py`. Lazy imports in `agent/core.py` and `mcp/client.py` retire to module-top. `MCPRegistrationError` introduced for §2/§8 surfaces (consumed by L2). New import-graph regression test (`tests/test_imports.py`) locks the chain break: `import the_one.agent.core` does NOT load `the_one.mcp.oauth`.
2. **L1 — override schema + AgentConfig field + DB migration**. `the_one/mcp/_overrides.py` lands `StdioMCPOverride` + `StreamableHttpMCPOverride` Pydantic schemas with all-`Substitute` markers. `AgentConfig.mcp_overrides: dict[str, dict[str, Any]] | None` field added. DB schema v11 migration adds `mcp_overrides` column to `agents` table; `SQLiteAgentStore.save/load` round-trip the new column. Resolver dispatch tests prove the schema composes through `the_one.tools.resolver.resolve` correctly under the `Substitute` marker (mission criterion: "resolver's substitution behavior on MCP-shaped overrides" automated coverage).
3. **L2 — `MCPToolProvider` + `MCPClientTool` + factory wiring**. `MCPClientTool(Tool)` wraps `MCPTool` instances with prefixed names (`mcp__{source}__{tool}`); `execute` dispatches through `pool.acquire → call_tool → MCPToolResult.text`. `MCPToolProvider.get_tools_for_agent(config, *, agent_name)` reads `mcp_source_ids`, acquires per-source clients, lists tools, applies override resolver, wraps in `MCPClientTool`, returns flat list. `AgentFactory.__init__` accepts `mcp_provider` injection; `create()` calls the provider after the built-in loop. Tests cover: attach without overrides, attach with overrides (the two-agents-two-credentials case from mission criterion), tool-name prefix construction, prefix-collision raises, source-deleted-mid-build skips, source-fails-to-start skips (graceful-degrade), the agent's tool registry exposes both prefixed names when two sources have overlapping short names.
4. **L3 — ContextVar relocation + per-tool-dispatch binding + `_pool_default` sentinel removal**. `the_one/agent/_context.py` introduced as canonical home; `interfaces/web/app.py` re-exports for back-compat with F5 set-sites. `Agent._execute_tool` binds `current_tool_call_id` per dispatch. Pool's `_entry_worker` drops the `_pool_default` sentinel; reads ContextVar from new home; passes `None` to `build_oauth_provider_for_source` when unset. `provider_factory.build_oauth_provider_for_source` accepts and handles `chat_session_id is None`. F5's WebSocket-driven `auth_required` broadcasts continue to route through the existing handler chain — F6 L3 only changes the SOURCE of the chat-session-id (per-task ContextVar) and adds the `tool_call_id` companion.
5. **L4 — graceful-degrade test fortification + tool-name prefix invariants**. (Largely a test-only leg; production code is mostly polish on L2's error paths.) Tests cover: source-deleted-mid-session error envelope; source-fails-mid-session through the `_evict + re-acquire` path; tool-name collision under hostile source names (an operator names two sources `Github` and `gitHub` — both normalize to `github`; first wins, second drops with WARNING); `disabled_tools: ["mcp__foo__bar"]` filters correctly through the existing factory filter. Fold this leg into L2 if scope is right-sized.
6. **L5 — Tier-1 HAT + F2-known-issue caplog retirement**. 5-step verification per §7. Bundles the speculative-mechanism (F5 L1) verification with the HAT step (per F5 debrief recommendation #2 — bundle speculative+verification into one indivisible leg). PASS retires F2-known-issue from mission.md; FAIL files follow-up flight per §7-fail.

Optional **L6 — routine-maintenance docs sweep**: lifts agents.md 5th convention `same-task-anyio-cm-ownership`; adds `the_one/mcp/README.md` "F5 Lazy-path Two-Event UX" section + F5→F6 carry-forwards table; extends `provider_factory.py` docstring with manual-vs-DCR flowchart. Pure docs leg; no tests beyond import smoke. Skip if scope is tight; default plan: include in L5's docs-pass alongside the HAT documentation.

### Checkpoints

- [ ] **C0** — `MCPAuthRequired` canonical at `the_one.mcp.errors`; lazy-import workaround retired in `agent/core.py` + `mcp/client.py`; import-graph test locks the chain break (L0)
- [ ] **C1** — `AgentConfig.mcp_overrides` field + DB schema v11 + override schema module + resolver dispatch round-trip tests green (L1)
- [ ] **C2** — `MCPToolProvider` + `MCPClientTool` + `AgentFactory` integration; attach/override/collision/graceful-degrade unit tests green; agent build for an agent with `mcp_source_ids=[X, Y]` exposes tools under `mcp__{X.name}__*` and `mcp__{Y.name}__*` (L2)
- [ ] **C3** — ContextVar relocation; `_pool_default` sentinel grep returns zero hits; per-tool-dispatch binding tests green; F5 OAuth round-trip regression unaffected (L3)
- [ ] **C4** — Graceful-degrade tests green for all four failure classes (§8) (L4 — or folded into L2)
- [ ] **C5** — Tier-1 HAT 5/5 PASS in CI; caplog assertion green; F2-known-issue retired from `mission.md::Known Issues` (L5)

### Adaptation Criteria

**Divert if**:

- Architect cycle-1 finds the override schema can't compose through `resolve(...)` cleanly (e.g., `dict[str, str]` Substitute fails the per-key dispatch because `dict` isn't a recognized field shape). Fall back to: drop the resolver path; `MCPToolProvider` does the merge inline (operator env + agent override → flat dict) without `resolve`. Lose the resolver-uniformity property; keep the override functionality. Document as a Known Issue.
- L2's tool-list latency at agent build (N × cold-spawn for N attached sources) exceeds ~2s in HAT — operators perceive agent-create as slow. Fall back to: lazy per-source tool-list at first call (the registry returns a placeholder schema; first tool call materializes via `acquire + list_tools`); accept first-call latency surprises. Documented as a Known Issue; F6 ships with the eager path.
- L3's ContextVar relocation breaks an F5 OAuth round-trip test in a way that's not fixable via the re-export pattern. Revert L3's relocation; keep `_pool_default` sentinel; document as residual debt; F6 still lands the per-tool-dispatch binding (just at the original `app.py` ContextVar).
- L5 caplog assertion fails. Per §7-fail: F6 lands; F2-known-issue stays open; follow-up flight reverts F5 L1's helpers. F6 is NOT blocked.
- Architect cycle-1 surfaces a 4th open-question category (e.g., the resolver source-identity question reveals a cycle with the storage layer that L1 can't paper over). Pull forward F1-design-revisit at flight design Phase 5b; do NOT proceed to L1 implementation until the storage shape is locked.

**Acceptable variations**:

- L4 folding into L2 if combined leg LOC stays under ~600 (L2's ~470 + L4's ~80 = ~550 — likely fine).
- L1 splitting into L1a (override schema only) + L1b (AgentConfig field + DB migration) if the schema design needs its own design pass. Default: single L1.
- L2 splitting into L2a (`MCPClientTool` + name prefix) + L2b (`MCPToolProvider` + factory wiring) if combined LOC exceeds ~800. Default: single L2.
- L5 deferring Tier-2 (manual GitHub) HAT to operator's local run — F6 ships with Tier-1 caplog gate as the binding requirement. F5 precedent (Tier-2 manual / Tier-1 CI).
- L6 (docs sweep) folding into L5's docs-pass. Default: fold.

### Legs

> **Note**: tentative suggestions, not commitments. Refined per leg as work progresses.
>
> **Conventions for all legs**: leg artifacts use anchor-by-symbol-name (NOT `file.py:LINE`) per F1 debrief recommendation; each leg's post-completion checklist includes `ruff check` clean before `[HANDOFF:review-needed]`; leg artifacts include "stake-test probe" scripts when integration tests stake on a specific OS/SDK pattern (per F2 debrief KL #1); test-count reconciliation across Objective / Outputs / Acceptance Criteria; **citation audit MUST include "find direct callers of any public symbol whose signature changes" via grep against test files** (per F4 debrief R2 — codified in `mission-control` PR #5). §11 "module placement" sections enumerate the FULL flight surface with per-file LOC estimates, summed (per F5 debrief R3 — done in §10 above).
>
> **Citation convention boundary** (F5 cycle-2 L6): the FLIGHT artifact (this document) uses `file.py:LINE` citations freely — read top-to-bottom. LEG artifacts use anchor-by-symbol-name to insulate against line-drift between leg-design and leg-execution.

- [x] `00-break-circular-imports` *(completed 2026-05-08)* — Move `MCPAuthRequired` from `the_one/mcp/oauth/errors.py` to `the_one/mcp/errors.py` (canonical home per `canonical-import + convenience-re-export` convention). Add `MCPRegistrationError` to `the_one/mcp/errors.py` (consumed by L2's prefix-collision + L8's source-error surface). `the_one/mcp/oauth/errors.py` re-exports `MCPAuthRequired` for back-compat. Replace lazy imports at `the_one/agent/core.py::_execute_tool` and `the_one/mcp/client.py::call_tool` with module-top imports. Drop the lazy-import comment blocks (lines 8-13 of `agent/core.py`; lines 41-45 of `mcp/client.py` — verify ranges at L0 implementation time). New `tests/test_imports.py` locks the chain break: `import the_one.agent.core` does NOT load `the_one.mcp.oauth` — assert via `sys.modules` snapshot diff. **Citation audit**: `grep -rn 'MCPAuthRequired' the_one/ tests/` BEFORE implementation; expect 8-15 hits (definition site + lazy import sites + tests + re-export sites). All must continue to import successfully post-move; tests verify. ~2-3 new tests; ~70 LOC delta. Smallest leg in the flight.

- [x] `01-mcp-overrides-schema-and-agent-config` *(completed 2026-05-08)* — Land `the_one/mcp/_overrides.py` defining `StdioMCPOverride` (with `env: Annotated[dict[str, str] | None, Substitute] = None`) and `StreamableHttpMCPOverride` (with `headers: Annotated[dict[str, str] | None, Substitute] = None` and `bearer_token: Annotated[str | None, Substitute] = None`). **Critical** (per Architect cycle-1 H1): use `Annotated[T | None, Substitute] = None` placement, NOT `Annotated[T, Substitute] | None = None`. Pydantic v2 hoists metadata inside Union types such that `model_fields[name].metadata == []` and the resolver's marker scan raises `ValueError: ... no Narrow/Substitute marker`. Verified empirically — no existing tools use the broken placement. The L1 test file MUST include a `field_info.metadata` introspection regression test that pins the working placement so future schema additions cannot silently regress. Both schemas `frozen=True` per the `cross_configs` shared-view convention. Add `mcp_overrides: dict[str, dict[str, Any]] | None = None` to `AgentConfig` at `the_one/agent/config.py`. **DB schema v11 migration via the v8 ALTER TABLE precedent** (Architect cycle-1 L3): cite `the_one/db/schema.py::_migrate_v7_to_v8` (lines ~312-332) as the exact pattern — individual `await conn.execute(...)` (NOT `executescript`), idempotent PRAGMA-check, `INSERT OR IGNORE` LAST. Add `mcp_overrides TEXT` column (no `DEFAULT NULL` per the v8 comment-block warning). Update `the_one/db/repositories.py::SQLiteAgentStore.save` UPSERT and `_row_to_config` parse to round-trip the new column. New `tests/test_mcp_overrides.py`: introspection regression test (locks `Annotated[T | None, Substitute] = None` placement); schema round-trip; `resolve(StdioMCPOverride, None, {"env": {"FOO": "bar"}})` returns merged model with `env={"FOO": "bar"}` (Substitute path); locked-down NULL `resolve(StdioMCPOverride, None, None).env is None`; AgentConfig round-trips through SQLite with mcp_overrides set + with mcp_overrides=None. Update existing `tests/test_schema.py` for schema migration v11 (replaces "tests/test_db_schema.py" which doesn't exist per Architect cycle-1 L7). Update existing `tests/test_store.py` for AgentConfig round-trip (replaces "tests/test_agent_config.py" which doesn't exist per Architect cycle-1 L7). **Citation audit**: `grep -rn 'tool_overrides\|mcp_overrides' the_one/ tests/` BEFORE implementation; ensure no existing tests assume mcp_overrides is the same field as tool_overrides. ~12-14 new tests; ~110 LOC production + migration; ~180 LOC tests.

- [x] `02-mcp-tool-provider-and-routing` *(completed 2026-05-08; absorbed L4 graceful-degrade tests via TestMCPToolProvider class)* — Land `the_one/mcp/_tool.py::MCPClientTool(Tool)` wrapping an `MCPTool` instance. Constructor takes `mcp_tool: MCPTool, source: MCPSource, agent_name: str`; sets `name = f"mcp__{normalize(source.name)}__{mcp_tool.name}"`, `description = mcp_tool.description`, `parameters = mcp_tool.input_schema or {"type": "object", "properties": {}}`. `execute(**kwargs)` calls `await acquire(self._agent_name, self._source.id)` then `client.call_tool(self._original_tool_name, kwargs)`; returns `result.text`. Land `the_one/mcp/_tool_provider.py::MCPToolProvider`: `async def get_tools_for_agent(self, config: AgentConfig, *, agent_name: str) -> list[Tool]`. Reads `config.mcp_source_ids`; for each id: load MCPSource (catch KeyError → log + skip per §8); resolve override via `resolve(override_schema, None, (config.mcp_overrides or {}).get(source.name))`; apply override to the source's spawn-time config (pre-acquire); call `acquire` (catch MCPSandboxError/MCPConnectionError/MCPVersionMismatch → log + skip); call `client.list_tools()`; wrap each MCPTool in MCPClientTool; collision-check the prefixed name against names already produced; raise/log per §2/§8. Modify `AgentFactory.__init__` to accept `mcp_provider: MCPToolProvider | None = None`, default to fresh instance; modify `create()` to call `self.mcp_provider.get_tools_for_agent(config, agent_name=name)` after the built-in loop and register the returned tools through the existing filter. **Critical**: orphan-override warn — at the start of `get_tools_for_agent`, if `mcp_overrides` has a key that doesn't match any source's `name` in the resolved sources, log a `WARNING: agent {name}'s mcp_overrides references unknown source name '{key}'`. **Citation audit**: `grep -rn 'AgentFactory\.\|tool_providers\|BuiltinToolProvider\|get_tools' tests/ the_one/` BEFORE implementation; verify factory-test fixtures don't break under the `mcp_provider` injection (default is fresh instance; tests pass `None` to disable). Tests: attach without overrides; attach with overrides (two-agents-two-credentials case — different bwrap PIDs verified via mock or `pool._pool` inspection); tool-name prefix construction (assert exact name shape); prefix collision raises; source-deleted-mid-build skips with WARNING; source-fails-to-start skips with WARNING; orphan-override WARNING; agent.tools.all_schemas() exposes both prefixed names when attached to two sources with overlapping short names; integration test against an in-repo MCP fixture verifies end-to-end registry build → tool-call dispatch. ~30+ tests across mock + integration; ~320 LOC production; ~320 LOC tests.

- [x] `03-context-relocation-and-per-tool-binding` *(completed 2026-05-08)* — Land `the_one/agent/_context.py` defining `current_chat_session_id: ContextVar[str | None]` (DEFINITION moves here from `the_one/interfaces/web/app.py:209-211`) plus NEW `current_tool_call_id: ContextVar[str | None]`. `the_one/interfaces/web/app.py` keeps a re-export of `current_chat_session_id` so F5's set-sites at `:236, :853` continue to work unchanged via the back-compat re-export. Modify `Agent._execute_tool` (`the_one/agent/core.py`): bind `current_tool_call_id.set(tool_call.id)` at function entry under `try/finally`; reset on exit. Modify `the_one/mcp/_pool.py::_entry_worker`: drop the `_pool_default` sentinel (lines `~181-183`); read `current_chat_session_id.get(None)` directly; pass through to `build_oauth_provider_for_source(source, repo, csid_or_none, source_id=source.id)`. Modify `the_one/mcp/oauth/provider_factory.py::build_oauth_provider_for_source` to accept `chat_session_id: str | None`; when None, return None (no provider construction; lazy 401 path surfaces; broadcast no-ops cleanly because no session). Re-export `current_tool_call_id` from `app.py` for any future consumer. **Citation audit**: `grep -rn 'current_chat_session_id\|_pool_default' the_one/ tests/` BEFORE implementation; expected hit list (verify exact count): `app.py:209-211 + 236 + 256 + 853 + 875` (5 sites in production), `_pool.py:181-183` (1 site), tests (~3 sites). All must continue to work post-move via the re-export. Tests in `tests/test_agent_context.py`: ContextVar visibility from inside `_execute_tool`; ContextVar reset on exception path (the existing `MCPAuthRequired` catch + the generic `Exception` catch); `_pool_default` sentinel grep returns zero hits in production code; F5 OAuth round-trip regression (run `tests/test_oauth_*.py` unmodified — must stay green). ~12-15 new tests; ~75 LOC production delta + ~120 LOC tests.

- [x] `04-graceful-degrade-fortification` *(folded into L2 per default disposition; tests live in tests/test_mcp_tool_provider.py::TestMCPToolProvider — failure_class_1/2/4 + 64-char-ceiling + collision-step-trace + duplicate-source-id all covered)* — Test-fortification leg. (Largely no production code beyond polish.) Tests cover: source-deleted-mid-session error envelope rendered through `MCPClientTool.execute`'s exception path (the warm pool entry continues serving until idle reap; documented behavior, not a bug — test asserts the LATER-build sees the deletion + skip). Source-fails-mid-session through `_evict + re-acquire`: simulate the source's `MCPClient` evicted mid-session; next `call_tool` re-acquires; if the spawn fails, the error envelope reaches `Agent._execute_tool`'s generic exception catch + returns is_error=True. Tool-name collision under hostile source names (operator names two sources `Github` and `gitHub` — both normalize to `github`; first wins, second drops with WARNING). `AgentConfig.disabled_tools = ["mcp__foo__bar"]` filters correctly through the existing factory filter. Tests for the `enabled_tools` whitelist with prefixed names (verify no prefix-aware special-casing in the existing filter at `factory.py:130` is needed). **Decision**: at leg-design time, evaluate whether L4 has enough independent surface to warrant a separate leg or if it folds into L2. Default: fold into L2 if L2's leg-design is under ~600 LOC; standalone if L2 is heavier. ~80 LOC if standalone (mostly tests).

- [x] `05-hat-tier-1-with-caplog-retirement` *(file authoring completed 2026-05-08; binary PASS gate + F2-known-issue retirement DEFERRED to flight-end docker run — see flight-log)* — Per §7. 5-step verification plus the F5 L1 caplog gate. Documented in `tests/HAT.md` as Tier-1 (CI-runnable). Automated portion in `tests/test_mcp_attach_hat.py`: spawn the in-repo OAuth fixture (F5 L5 reuse) AND `mcp-server-fetch` (F4 HAT reuse) as the two attached sources; configure agents A and B; run the 5 steps; assert each step's invariants; capture `caplog` records throughout; assert NO `MCPClient transport close failed` WARNING. PASS = update `mission.md::Known Issues` to remove the F2-known-issue entry (the leg artifact spells out the exact line removal); FAIL = file follow-up flight per §7-fail (the leg artifact pre-writes the follow-up flight title + scope; orchestrator escalates to user). Tier-2 (live GitHub MCP) documented in `tests/HAT.md` as a manual procedure — operator runs locally; not blocking. **Citation audit**: `grep -rn 'F2-known-issue\|MCPClient transport close failed\|MCPClient.disconnect' the_one/ tests/ missions/` BEFORE implementation; ensure the retirement update touches the right mission line (currently `missions/07-mcp-integration/mission.md:104`). ~15 HAT tests; ~250 LOC test code; mission.md edit. **F5 debrief recommendation #2 compliance**: this leg bundles the speculative-mechanism (F5 L1) verification with the HAT step — non-separable per the recommendation.

- [ ] `06-docs-sweep` *(NOT in F6 — deferred to routine maintenance per L5 leg artifact's "L6 fold" disposition; the 5th `same-task-anyio-cm-ownership` convention + README sections + provider_factory docstring flowchart are out of F6 scope)* — Lift `same-task-anyio-cm-ownership` 5th convention into `the_one/agents.md::Project Conventions` (covers F4's worker-task pattern + F5's verbatim subclass override + F6's per-tool-dispatch ContextVar bind, all variations on "same-task ownership of cancel-scope-rooted CMs"). Add `the_one/mcp/README.md` "F5 Lazy-path Two-Event UX" section (the consent_url=None first event → Connect button → /api/oauth/start → real consent_url second event). Add `the_one/mcp/README.md` "F5→F6 Carry-Forwards" enumeration table (links to the four named items from F5 debrief: circular import, ContextVar fallback, F2-known-issue HAT, _drive_flow error handling — note _drive_flow is **already-satisfied** per F6 Phase 1b reconnaissance; document the status). Extend `the_one/mcp/oauth/provider_factory.py` module docstring with manual-vs-DCR flow description. Pure docs leg. Default: fold this content into L5's docs-pass.

---

## Phase 1b Reconnaissance Report

Walked the F5 flight-debrief.md "Action Items" section and named "Architectural debt carried forward to F6" against current code. Each source item classified:

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| **F6 design phase: enumerate FULL flight surface in §11 (per-file LOC table)** | methodology — applies to this design | n/a | Done in §10 of this artifact. |
| **F6 first leg: structural break of `oauth.__init__ → storage → db.repositories → agent` circular chain** | confirmed-live | `the_one/db/repositories.py:12` imports `from the_one.agent.config import AgentConfig`; `the_one/mcp/oauth/__init__.py:26-31` eagerly imports `_state, errors, handlers, manual_metadata, provider_factory, storage`; lazy-import workaround at `the_one/agent/core.py:251` and `the_one/mcp/client.py:436` | Real work for F6 L0; structural fix is to move `MCPAuthRequired` to canonical `the_one/mcp/errors.py` per §6. |
| **F6 first HAT step: caplog assertion for L1's F2-known-issue retirement claim** | partially-satisfied (mechanism shipped at F5 L1, HAT verification pending) | `_open_streamable_http_transport_stack` exists at `the_one/mcp/transports/streamable_http.py:171`; `_open_stdio_transport_stack` exists at `the_one/mcp/transports/stdio.py:368`; `MCPClient.disconnect` at `the_one/mcp/client.py:333` still logs the warning by design as "cross-task safety net" | F6 L5 HAT runs the caplog assertion per §7. |
| **F6 design: per-tool-dispatch ContextVar binding inside `Agent._execute_tool`; eliminate `_pool_default` sentinel** | confirmed-live | `the_one/interfaces/web/app.py:209-211` defines ContextVar; `the_one/mcp/_pool.py:181-183` uses `_pool_default` sentinel | Real work for F6 L3 per §5. |
| **F6 / routine maintenance: error handling in `_drive_flow` (`api.py::oauth_start`); broadcast `auth_failed` on `httpx.ConnectError` / timeout** | **ALREADY-SATISFIED** | `the_one/interfaces/web/api.py:1106-1121`: `_drive_flow` actually catches `Exception` (broader than the F5 debrief's claim of "swallows silently") AND broadcasts `auth_failed` event with `description=str(exc)`. F5 debrief was empirically wrong about the no-error-handling claim. | Retire from F6 scope; no work needed. Mention in F6 L6 docs-sweep that the F5→F6 carry-forwards table notes this item as already-satisfied. |
| **F6 / routine maintenance: extend `the_one/mcp/README.md` with "F5 Lazy-path Two-Event UX" section + "F5→F6 carry-forwards" enumeration** | confirmed-live (doc gap) | README does not currently have these sections (verified by grep at recon time) | Defer to F6 L6 docs-sweep (or fold into L5 docs-pass). |
| **F6 / routine maintenance: extend `provider_factory.py` module docstring with manual-vs-DCR flow description** | confirmed-live (doc gap) | Module docstring exists but lacks the flow-chart-style description | Defer to F6 L6 docs-sweep. |
| **F6 / routine maintenance: simplify `stop_periodic_sweep` to direct `async def`** | confirmed-live | `the_one/mcp/oauth/_state.py:199-226` has the two-level indirection per F5 debrief | Defer to routine maintenance (NOT F6 — too tangential to F6's wiring scope). |
| **Routine maintenance: add `playwright install chromium` to Dockerfile** | infra (not F6 scope) | Pre-existing infra gap affecting all `tests/browser/*.py` | Routine maintenance. |
| **Routine maintenance (carried from F4 R5): add fifth named convention `same-task-anyio-cm-ownership` to `agents.md`** | confirmed-live (doc gap) | `the_one/agents.md::Project Conventions` lists 4 conventions (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`); 5th not present | Defer to F6 L6 docs-sweep — F6 itself is a strong example of the pattern (per-tool-dispatch ContextVar bind = same-task ownership of nested cancel-scope state) so the convention writes naturally. |
| **Routine maintenance: address 3 non-blocking accessibility findings** | infra (not F6 scope) | Pre-existing F5 L5 deferred items | Routine maintenance. |
| **mission-control PR (next): codify the 4 process recommendations** | done | Recent commits to `mission-control` repo (e.g. commit `65fad37 feat: add upstream reconnaissance + citation verification to skills`) addressed these | No further action. |
| **mission update: keep F2-known-issue entry OPEN in `mission.md` until F6 HAT runs the L1 caplog assertion** | procedural — still open | `missions/07-mcp-integration/mission.md:104` shows the F2-known-issue entry as `[ ] **MCPClient.disconnect teardown noise**` (open) | F6 L5 HAT caplog assertion gates retirement per §7. |

**Confirmed-live items rolled into F6**: 4 (circular-import break / L0; ContextVar binding / L3; F2-known-issue HAT / L5; convention + docs / L6).
**Already-satisfied items retired**: 1 (`_drive_flow` error handling — F5 debrief was empirically wrong; code already does this).
**Items deferred to routine maintenance**: 6 (Playwright install, accessibility findings, `stop_periodic_sweep` simplification, README sections [or L6], `provider_factory` docstring [or L6]).
**Items already done**: 1 (mission-control process recommendations PR).

User confirmation of these classifications was given inline at flight-design Phase 3 ("go").

---

## Post-Flight

### Completion Checklist

- [ ] All required legs (L0, L1, L2, L3, L5) completed; L4 folded into L2 OR shipped standalone; L6 docs-sweep folded into L5 OR shipped standalone
- [ ] All checkpoints (C0-C5) met
- [ ] `pytest --tb=no -q` green; new test count documented in flight-debrief; F1/F2/F3/F4/F5 regression unaffected
- [ ] `ruff check the_one/ tests/` clean (per-leg gate)
- [ ] F2-known-issue entry retired from `missions/07-mcp-integration/mission.md::Known Issues` (post-L5 caplog PASS)
- [ ] `_pool_default` sentinel grep returns ZERO hits in production code (post-L3)
- [ ] Lazy-import workaround comment blocks dropped from `agent/core.py` and `mcp/client.py` (post-L0)
- [ ] `the_one/agents.md::Module Map` updated for new modules (`_overrides`, `_tool`, `_tool_provider`, `_context`)
- [ ] `the_one/agents.md::Tool Providers` section documents the sibling `MCPToolProvider` shape
- [ ] (If L6 ships) `the_one/agents.md::Project Conventions` 5th convention `same-task-anyio-cm-ownership` lands
- [ ] (If L6 ships) `the_one/mcp/README.md` extends with F5 Lazy-path Two-Event UX + F5→F6 carry-forwards table
- [ ] F7 design has F6 prerequisites met
- [ ] F8 design has F6 prerequisites met (specifically: the `mcp_overrides` data shape for the Studio MCPs tab to render against)

### Verification

How to confirm the flight achieved its objective:

1. **Tool-list visibility**: from a Python REPL, `factory = AgentFactory(...); agent = await factory.create("agent-with-mcp-attached"); names = {t.name for t in agent.tools._tools.values()}; assert any(n.startswith("mcp__") for n in names)`.
2. **Per-agent isolation**: configure agent A and agent B with the same stdio source attached but different `mcp_overrides[source.name].env`; build both; trigger a tool call from each; verify `pgrep -f mcp-server-fetch` shows two distinct PIDs.
3. **Tool-name collision invariant**: configure two MCP sources with overlapping short tool names (e.g., both expose `read_file`); attach both to one agent; verify `agent.tools.get("mcp__source-a__read_file")` and `agent.tools.get("mcp__source-b__read_file")` BOTH succeed and dispatch to distinct sources.
4. **Graceful degrade**: delete an attached source via API; build the agent again; verify the build SUCCEEDS with a WARNING log; verify the agent's tool registry no longer carries the deleted source's tools but still carries the other sources' tools.
5. **Resolver substitution**: `pytest tests/test_mcp_overrides.py -v` — green; the resolver dispatch lock-in test (mission criterion #11 "resolver's substitution behavior on MCP-shaped overrides" automated coverage).
6. **Tool-name namespacing**: `pytest tests/test_mcp_tool_provider.py -v -k namespacing` — green.
7. **L5 Tier-1 HAT**: `pytest tests/test_mcp_attach_hat.py -v` — green; caplog assertion locks the F2-known-issue retirement.
8. **F5 OAuth round-trip regression**: `pytest tests/test_oauth_*.py tests/test_mcp_oauth_*.py -v` — green (no regression from L3's ContextVar relocation).
9. **Import-graph regression**: `pytest tests/test_imports.py -v` — green; `import the_one.agent.core` does NOT load `the_one.mcp.oauth`.
10. **Lint + existing-suite regression**: lint clean; F1/F2/F3/F4/F5 prior tests grow by F6's net new tests (estimated +75-95 across L0-L5), no regressions.

The flight delivers the agent-MCP wiring layer that closes mission criteria #7 ("agent attached to MCP sources contributes their tools"), #8 ("tool-name collision handled by stable namespacing"), and #10 ("graceful failure isolation"). It contributes to criterion #11 (per-layer automated coverage of resolver substitution + tool-name-spacing logic). F6 is the runtime; F7 (inspector) and F8 (Studio MCPs tab UI) consume the data shape F6 lands.
