# Flight: Cross-Platform Foundations & Policy Resolver

**Status**: ready
**Mission**: [Built-In Tool System](../../mission.md)

## Contributing to Criteria

- [ ] Each tool category enforces tool-level constraints — path scope, read-size caps, output caps, timeout caps, URL/host scope — that apply to all agents by default, and per-agent overrides can only narrow those constraint values, never widen them, with the narrowing invariant enforced at a single named resolution layer rather than ad-hoc in each tool *(F2 builds the resolution layer; F3-F5 introduce real constraint values)*
- [ ] The configuration model supports two override semantics at the agent level — narrowing (for constraint values) and substitution (for identity / shared-credential / KV values) — even though M05's built-in tools only exercise the narrowing path; the storage shape and resolver are designed to absorb the substitution case without restructuring when MCP integration arrives *(F2 implements both paths and unit-tests substitution via fixture)*
- [ ] Filesystem and execution tooling are architected for cross-platform support: platform-specific concerns (path semantics, shell selection, interpreter resolution, pty handling) are isolated behind a clear abstraction layer, and the implementation runs cleanly under the current Linux/WSL target without Linux-only assumptions in tool code *(F2 builds the platform layer)*
- [ ] Existing agent configurations referencing removed tools load cleanly and continue functioning — stale tool names in `enabled_tools`/`disabled_tools` are silently stripped via schema migration with no operator-visible breakage *(F1 handled the strip; F2's v8 migration adds `tool_overrides` and `tool_configs` without disturbing existing rows)*

---

## Pre-Flight

### Objective

Build the architectural seam every kept tool will go through for the rest of the mission. Two coupled deliverables: (a) `the_one/platform/` package abstracting platform-divergent concerns (paths, shell selection, Python interpreter resolution, temp-dir/user-dir helpers), and (b) `ToolPolicyResolver` — a pure function `resolve(schema, tool_config, agent_override) -> Config` that composes tool-level config (new `tool_configs` SQLite table) with agent-level overrides (new `tool_overrides` field on `AgentConfig`) and enforces narrow-or-substitute semantics per key. Per-key dispatch is declared on each tool's Pydantic config schema via `Annotated[type, Narrow]` / `Annotated[type, Substitute]` field metadata. The resolver is invoked once at `AgentFactory.create()` time; resolved configs flow into per-agent tool instances via `__init__(config)`. The seven existing tools (`shell`, `read_file`, `write_file`, `list_dir`, `python_exec`, `http_request`, `web_search`) are migrated through the platform layer + resolver but their *defaults match today's behavior* — F2 is a pure scaffolding refactor with regression-only tests; F3-F5 introduce real constraint values on top of this seam.

### Open Questions

- [x] **Agent-level override shape** — flat `tool_overrides: dict[str, dict] | None = None` field on `AgentConfig` (mirrors `enabled_tools`/`disabled_tools` shape) (resolved: see Decision 1)
- [x] **Resolver per-key semantic dispatch** — Pydantic schema on each tool with `Annotated[type, Narrow]` / `Annotated[type, Substitute]` field metadata (resolved: see Decision 2)
- [x] **Resolution-layer placement** — single resolver invoked at `AgentFactory.create()` time, resolved config passed into per-agent tool instances via `__init__(config)` (resolved: see Decision 3)
- [x] **Platform abstraction layout** — `the_one/platform/` package with submodules `paths.py`, `shell.py`, `interpreter.py`, `tempdirs.py` (resolved: see Decision 4)
- [x] **Per-tool vs shared `Config` Pydantic models** — F2 uses the empty default (`Tool.Config = BaseModel`); F3-F5 introduce per-tool or per-category Configs as they add constraint fields (resolved: see Decision 5)
- [x] **HAT leg** — Skipped for F2 (pure scaffolding refactor, no user-facing behavior change) (resolved: see Decision 6)
- [x] **Validation approach** — Regression-only: every pre-F2 test passes unchanged; new tests cover resolver (narrow + substitute fixture) and platform helpers (resolved: see Decision 7)
- [x] **Tool-config freshness contract** — Session-bound: resolved at `AgentFactory.create()`; mid-session operator updates apply at next agent build (resolved: see Decision 8)
- [x] **`BuiltinToolProvider.get_tools()` second caller** — `the_one/interfaces/web/api.py:80-83` (`/api/tools` introspection endpoint) plus 2 `get_tools()` call sites in `tests/test_builtins.py` use the zero-arg form. New signature accepts `tool_configs: dict[str, dict] | None = None` and `agent_overrides: dict[str, dict] | None = None`; introspection callers pass nothing (both default `None`) and receive tools instantiated with default empty Configs (resolved: see Decision 9)
- [x] **`tool_classes()` protocol method** — NOT added. `BuiltinToolProvider.get_tools(configs)` does internal name→Config-class lookup itself; protocol stays single-method, preserving MCP alignment (resolved: see Decision 10)

### Design Decisions

**Decision 1 — Agent-level override shape: `tool_overrides: dict[str, dict] | None = None` on `AgentConfig`**: A flat dict keyed by tool name, each value a JSON delta blob mirroring the matching `tool_configs.config` shape. Default is `None` (no agent-level overrides — locked-down NULL semantic, mirrors v7's `enabled_tools=NULL` preservation). The field lives on `AgentConfig` (not a sibling table) because it's a per-agent property, persisted as a single JSON column on the `agents` table, and the existing `enabled_tools`/`disabled_tools` fields already establish that pattern.
- Rationale: locality, consistency with existing AgentConfig fields, and the simplest possible MCP-readiness shape (when MCP overrides arrive, the same field hosts them).
- Trade-off: any per-agent override has to live in this single field; a future need for per-(agent, tool) audit timestamps would force a sibling table later. Acceptable — F2 doesn't have that need.

**Decision 2 — Per-key dispatch: Pydantic schema on each tool with `Annotated[type, Narrow]` / `Annotated[type, Substitute]` field metadata**: Each tool declares a `Config: type[BaseModel]` class attribute. Constraint fields are annotated `Annotated[<type>, Narrow]`; identity / shared-credential / KV fields are annotated `Annotated[<type>, Substitute]`. The resolver introspects `Config.model_fields` and dispatches per key.
- Rationale (architect's verdict, summarized):
  - Locality matches the codebase's existing pattern (`LLMProviderConfig`, `MCPSource` already follow "model lives next to consumer").
  - MCP alignment: the resolver's contract becomes "schema with annotated semantics" — works identically for built-in tools (compile-time schemas) and MCP servers (runtime-loaded schemas from server manifests). No registry to mutate at MCP install time.
  - Type-safe validation for free; auditability via `grep` is at least as good as a central registry.
  - Sets up F6's admin form generator (the admin UI can read `Tool.Config` schema to render editor controls).
- Trade-off: every tool gains a `Config` class. F2 keeps this lightweight by using the empty default (`Config = BaseModel`); F3-F5 will populate per-tool Configs as they introduce real constraint fields.

**Decision 3 — Resolver placement: single resolver at agent build, resolved policy passed into per-agent tool instances**: At `AgentFactory.create()` time, the resolver computes the resolved `Config` for each tool the agent has access to and hands it to the tool's `__init__(config)`. Tools store config as instance state and read it normally during `execute()`. **`BuiltinToolProvider.get_tools()` shifts from returning shared singletons to per-agent instantiation.**
- Rationale (architect's verdict):
  - Today's `BuiltinToolProvider.get_tools()` returns shared singleton tool instances registered into a per-agent registry (`factory.py:101-106`). That's a latent bug as soon as tools carry per-agent state. Shifting to per-agent instantiation fixes the latent bug *and* enables the resolver pattern.
  - Single resolution site (the factory) extends F1's "single read site, no escape hatch" pattern from prompt composition to tool config.
  - Substitution-path-via-fixture unit test becomes trivial: pure function, no agent, no registry, no factory needed.
  - Speculative "runtime context injection" benefit of two-phase placement isn't justified by any current mission criterion. Session-scoped overrides (if F4 or later need them) fit naturally as a session-construction parameter, not as a runtime resolver hook.
- Trade-off: `BuiltinToolProvider.get_tools()` and `AgentFactory.create()` change shape. Contained refactor; tests assert per-agent registry isolation.

**Decision 4 — Platform abstraction: `the_one/platform/` package with submodules**: New top-level package `the_one/platform/` containing:
- `paths.py` — path canonicalization, expanduser, resolve, symlink-safe-resolve helpers (Windows backslash normalization, case sensitivity, symlink resolution semantics)
- `shell.py` — shell selection (`/bin/sh` Unix vs `cmd.exe` Windows; `SHELL` env var preference); subprocess invocation helpers
- `interpreter.py` — Python interpreter resolution (`python3` Unix vs `python` / `py` Windows)
- `tempdirs.py` — temp-dir + user-dir helpers (`tempfile.gettempdir()`, `Path.home()` with cross-platform user-config-dir resolution)
- `__init__.py` — public API surface; documents the package's contract
- Rationale: F4 introduces pty handling (separate module); F3 will likely add more path-policy helpers (allowlist resolution, symlink-escape detection); F5 may add web-related platform concerns. Single-module would crowd. Inlined-into-tools loses centralized testability. Package gives growth room without restructuring.
- Trade-off: more files for F2 to author. Worth it for F3-F5 extensibility.

**Decision 5 — Per-tool vs shared Configs**: F2 uses `Tool.Config = BaseModel` default for all 7 tools (no fields). F3-F5 will introduce per-tool or per-category Config classes (e.g., `FilesystemConfig` shared across `ReadFileTool`/`WriteFileTool`/`ListDirTool` for path-scope; `ExecutionConfig` shared across `ShellTool`/`PythonExecTool` for output-cap and timeout). This decision is deferred — F2's job is to establish the contract, not to populate it.
- Rationale: Tool ABC change (Decision 3) requires *some* default. Empty `BaseModel` is the no-op default. F2 doesn't introduce constraint fields, so populating Configs would be premature.
- Trade-off: F3 design must decide per-tool vs per-category Configs explicitly. Documented as a forward-reference.

**Decision 6 — HAT leg: skipped for F2**: F2 is a pure scaffolding refactor. No new user-facing surfaces, no new agent behaviors, no admin UI changes. The `/api/agents` payload gains a `tool_overrides` field (always `null` until F3-F5 / F6 populate it). The deploy pipeline's `/api/selftest` continues to exercise one tool path against a real LLM; that's sufficient live coverage.
- Rationale: HAT's value is voice/feel/ergonomics validation against a real LLM. F2 has no voice or ergonomics surface to validate.
- Trade-off: any latent regression in tool execution (read_file path, shell output, etc.) gets caught only by AIAT live tests. F2 verification leg (L7) runs the AIAT smoke explicitly to mitigate this.

**Decision 7 — Validation approach: regression-only**: Every pre-F2 default unit test passes unchanged. Browser suite passes unchanged (modulo gitignored visual snapshots). AIAT live smoke passes unchanged. New tests cover (a) the resolver — narrowing path, substitution path via fixture, locked-down NULL semantics; (b) platform-layer helpers — path canonicalization, shell selection, interpreter resolution; (c) schema v8 migration — `tool_configs` table created, `agents.tool_overrides` column added, existing rows preserved; (d) `ToolConfigRepository` CRUD; (e) tool ABC contract — `Config` class attr, `__init__(config)` instantiation, `BuiltinToolProvider.get_tools()` per-agent isolation invariant.
- Rationale: F2's behavior IS its non-behavior — the seven tools should behave identically before and after. Tests beyond regression don't have meaningful targets until F3-F5 add constraint values.
- Trade-off: low ceiling for catching subtle regressions in tool execution. Mitigated by AIAT smoke + browser suite.
- **Note on F1 HAT-as-design-completion-gate principle**: F1's debrief promoted HAT to "design-completion gate" status because L7 surfaced a substantive design refinement (BASE_PROMPT minimization). The principle is preserved here: HAT triggers when there's a user-facing surface with voice/feel/ergonomics validation needs. F2 has no such surface — the resolver is invisible to operators until F6 exposes a Tools admin section. Decision 6's HAT-skip is consistent with the principle, not in conflict with it.

**Decision 8 — Tool-config freshness contract: session-bound**: Resolved tool configs are computed at `AgentFactory.create()` time and held as instance state on each tool. Mid-session operator updates to `tool_configs` rows or `AgentConfig.tool_overrides` apply at the next `AgentFactory.create()` invocation, NOT to in-flight agents. This mirrors the existing `AgentConfig` freshness contract (already session-bound — `AgentFactory.create()` reloads on every call but mid-session agents hold their resolved config). F6's admin UI must reflect this: a "Save" action on a tool's config updates the SQLite row but the running agent inherits the new value only on next session start.
- Rationale: matches the existing factory pattern (no surprise behavior change). Avoids per-call resolver invocation overhead. Per-session bound is the right granularity for constraint values that operators tweak rarely.
- Trade-off: F6's UX must communicate "applies to next session" clearly. A "live config" UX would require runtime resolver hooks (Decision 3 option (a)) — explicitly rejected.

**Decision 9 — `BuiltinToolProvider.get_tools(tool_configs, agent_overrides)` signature with default-None**: The zero-arg call form survives for introspection callers. New signature: `get_tools(tool_configs: dict[str, dict] | None = None, agent_overrides: dict[str, dict] | None = None) -> list[Tool]`. When both are `None`, each tool is instantiated with `Tool.Config()` (empty Pydantic model — introspection path; no resolver invocation). When at least one is supplied (factory path), the provider resolves each tool's Config internally via `resolve(cls.Config, tool_configs.get(name), agent_overrides.get(name))`. Verified callers besides `AgentFactory.create()` (factory.py:104):
- `the_one/interfaces/web/api.py:80-83` — `/api/tools` endpoint, returns `[{name, description}]`. Doesn't need configs. Calls `get_tools()` (zero-arg form). Continues to work via the both-None defaults.
- `tests/test_builtins.py` — 2 `get_tools()` call sites (plus 2 bare `BuiltinToolProvider()` instantiations that don't call `get_tools()` and are unaffected). Continue to work via the both-None defaults.
- Rationale: preserves the introspection callers without adding a separate method. Single-method protocol preserved (Decision 10 below).
- Trade-off: a tool that requires a non-empty Config to instantiate would break the zero-arg path. F2 keeps all `Config = BaseModel` (empty), so this isn't an issue today; F3-F5 must keep their Configs default-instantiable (Pydantic field defaults) to preserve the introspection-call contract. Worth flagging as a forward constraint.

**Decision 10 — Single-method `ToolProvider` protocol; `tool_classes()` NOT added**: The factory does NOT call a hypothetical `provider.tool_classes()` to enumerate tool classes for resolver invocation. Instead, the factory passes resolved configs to `provider.get_tools(configs)`, and the provider does its own internal name→Config-class mapping when instantiating tools. The `ToolProvider` Protocol (`the_one/tools/provider.py`) stays at two members: `name` property + `get_tools()` method.
- Rationale: protocol stability for MCP alignment. MCP servers will implement `get_tools(configs)` the same way; their internal "name → schema" mapping comes from server manifests, not Python class hierarchy. A `tool_classes() -> list[type[Tool]]` method wouldn't extend cleanly to MCP (no Python-level types) and would break the alignment claim Decision 2 was built on.
- Trade-off: factory loses direct access to `tool_class.Config`; resolver invocation must happen *inside* `BuiltinToolProvider.get_tools(configs)` rather than upstream of it. New flow: `AgentFactory.create()` reads `tool_configs` table + `AgentConfig.tool_overrides`, passes both to `BuiltinToolProvider.get_tools(...)`, and the provider does the per-tool resolver call internally. (Or — alternative — the resolver is invoked at the provider level by introspecting its own tool classes, with the factory passing only `tool_configs` + `agent_overrides` data.)
- Implementation note: L3 design picks one of these two factor-of-the-factor structurings; both honor Decision 10. The simpler one wins.

### Prerequisites

- [x] M05 Flight 1 landed and merged to `main` (commit `cd4d73d`)
- [x] Schema is at v7 (verified: `the_one/db/schema.py:7 CURRENT_VERSION = 7`)
- [x] Tool count: 7 (`shell`, `read_file`, `write_file`, `list_dir`, `python_exec`, `http_request`, `web_search`) — verified by `BuiltinToolProvider().get_tools()`
- [x] `AgentConfig` post-F1 fields: `name`, `description`, `provider_config_id`, `llm_model`, `system_prompt`, `enabled_tools`, `disabled_tools`, `kb_ids`, `mcp_source_ids`, `max_iterations` (4 model_fields verified for `Settings`; AgentConfig is the agent-side model — verify by inspection during L2)
- [x] `BuiltinToolProvider.get_tools()` returns shared singletons today (`factory.py:101-106`) — confirmed; L3 changes this
- [x] `MCPSourceRepository` exists in `the_one/db/repositories.py` and serves as the closest template for `ToolConfigRepository`
- [x] All four mission Open Questions assigned to F2 design are resolved (architect-advised at flight-design time)
- [ ] No port/network conflicts to verify — F2 doesn't introduce any new services, ports, or env vars
- [ ] User approves leg breakdown (Phase 4 sign-off)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined → see Legs section below

---

## In-Flight

### Technical Approach

**Order rationale (7 legs, executed in dependency order):**

1. **Platform package first** — establishes the seam every tool migration uses. No tool changes yet; just new helpers + tests.
2. **Schema v8 + AgentConfig.tool_overrides + ToolConfigRepository second** — adds the persistence surface. Independent of tools; pure DB work.
3. **Resolver + Tool ABC + factory wiring third** — implements the contract. Defines `Narrow` / `Substitute` markers. Migrates `BuiltinToolProvider.get_tools()` from singleton to per-agent. Tools still don't use the platform layer; they just get a (default empty) config injected. Resolver tests use a fixture Pydantic Config with both Narrow and Substitute fields.
4-6. **Migrate tools by category** — filesystem, then execution, then web. Each leg routes its tools through `the_one/platform/` and through the resolver. No new constraint values. Regression tests prove behavior unchanged.
7. **Integration verification** — full default unit + browser + AIAT smoke. Comprehensive regression sweep. `/api/agents` shape audit. Documentation updates.

**Key architectural shapes (locked at flight-design time):**

```python
# the_one/agent/resolver.py — pure function, single read site
from typing import Annotated, get_args, get_origin
from pydantic import BaseModel

class Narrow: pass        # sentinel marker
class Substitute: pass    # sentinel marker

def resolve(
    schema: type[BaseModel],
    tool_config: dict | None,
    agent_override: dict | None,
) -> BaseModel:
    """Compose tool-level config + agent-level override per the per-key
    semantic declared on the schema. Returns a validated Config instance."""
    # 1. Start from tool_config (operator-set tool-level defaults)
    # 2. For each field in schema.model_fields:
    #    - If Annotated marker is Narrow: agent_override[key] must be <= tool_config[key]
    #      (per-type narrowing semantics — list intersection, numeric min, etc.)
    #    - If Annotated marker is Substitute: agent_override[key] replaces tool_config[key]
    #    - If no override for this key: use tool_config[key] (or schema default)
    # 3. Validate the merged dict against schema; return instance
```

```python
# the_one/tools/base.py — Tool ABC change
from pydantic import BaseModel

class Tool:
    name: str
    description: str
    parameters: dict
    Config: type[BaseModel] = BaseModel  # default empty; override per tool

    def __init__(self, config: BaseModel | None = None) -> None:
        self._config = config or self.Config()

    async def execute(self, **kwargs) -> str: ...
```

**Default factoring: provider-drives-resolution** — the resolver invocation lives *inside* `BuiltinToolProvider.get_tools(...)`, not upstream in the factory. The factory passes raw `tool_configs_by_name` and `agent_overrides` to the provider; the provider does its own internal name→class lookup and resolver call. This keeps the `ToolProvider` Protocol single-method (`get_tools(...)`) and prevents the factory from reaching into `_TOOL_CLASSES`. MCP providers later implement the same shape with manifest-derived schemas.

```python
# the_one/tools/builtins.py — per-agent instantiation; provider owns resolution
from the_one.tools.resolver import resolve

class BuiltinToolProvider:
    # Internal mapping — implementation detail, not on the Protocol
    _TOOL_CLASSES = {
        "shell": ShellTool,
        "read_file": ReadFileTool,
        "write_file": WriteFileTool,
        "list_dir": ListDirTool,
        "python_exec": PythonExecTool,
        "http_request": HttpRequestTool,
        "web_search": WebSearchTool,
    }

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
    ) -> list[Tool]:
        """tool_configs: name → tool-level config dict (from tool_configs table).
        agent_overrides: name → agent-level override dict (from AgentConfig.tool_overrides).
        Both default to None for introspection callers (e.g., /api/tools), in which
        case each tool is instantiated with its default empty Config()."""
        tool_configs = tool_configs or {}
        agent_overrides = agent_overrides or {}
        result = []
        for name, cls in self._TOOL_CLASSES.items():
            if tool_configs or agent_overrides:
                cfg = resolve(cls.Config, tool_configs.get(name), agent_overrides.get(name))
            else:
                cfg = cls.Config()  # introspection path: empty default
            result.append(cls(cfg))
        return result
```

```python
# the_one/agent/factory.py — resolver invocation site
from the_one.db.repositories import ToolConfigRepository

async def create(self, name: str = "default") -> Agent:
    config = await self._load_config(name)
    # ... existing provider resolution ...

    # NEW: load tool_configs table + agent overrides, hand both to the provider.
    # Provider internally resolves each tool's Config and instantiates per-agent.
    conn = await get_connection()
    tool_configs_repo = ToolConfigRepository(conn)
    tool_configs_by_name = await tool_configs_repo.list_all()  # {name: dict}
    agent_overrides = config.tool_overrides or {}

    # Build per-agent tool registry (resolver runs inside provider.get_tools).
    registry = ToolRegistry()
    for provider in self.tool_providers:
        for tool in provider.get_tools(tool_configs_by_name, agent_overrides):
            if config.is_tool_enabled(tool.name):
                registry.register(tool)
    # ...
```

The `ToolProvider` Protocol gains a third method shape (`get_tools(tool_configs, agent_overrides)`) but stays single-method. Future MCP providers implement `get_tools(tool_configs, agent_overrides)` and source their schemas from manifests internally — same contract.

**Alternative factoring (factory-drives-resolution)** — kept as a footnote for L3 if provider-drives complexity surfaces: factory enumerates `provider._TOOL_CLASSES.items()`, calls `resolve(...)` per tool, passes resolved configs to `provider.get_tools(configs)`. Keeps `get_tools()` simple but leaks `_TOOL_CLASSES` to the factory. Use only if option (b) hits an unexpected wall during L3 implementation.

**Schema v8 migration shape:**

**Atomicity note** — Python's stdlib `sqlite3` (which `aiosqlite` wraps), in its default `isolation_level=""` mode (the project's current setup at `the_one/db/connection.py`), issues an implicit COMMIT before any non-DML statement (CREATE/ALTER/DROP). This applies equally to `executescript()` (which COMMITs first then runs) and to a `BEGIN`-then-DDL sequence (the `BEGIN` is silently committed before the DDL runs). **A true multi-DDL transaction would require switching the connection to `isolation_level=None` (autocommit mode where the application manages BEGIN/COMMIT explicitly)** — that's a connection-setup change beyond F2's scope. F2 follows the same pattern v3/v5/v6 use: each DDL effectively runs in its own auto-commit, idempotency comes from `IF NOT EXISTS` + `PRAGMA table_info` guards + `INSERT INTO schema_version` LAST so a partial-apply leaves the version at v7 and the next ensure_schema retries safely.

The F1 debrief's "wrap in explicit transaction for atomicity" recommendation is ACCEPTED but DEFERRED — it requires the connection-setup change, which is a separate maintenance task. Documented in the flight log as a forward-reference.

```python
if version < 8:
    # Add tool_configs table (mirrors mcp_sources shape)
    # Add agents.tool_overrides TEXT column (nullable, default NULL)
    # Each DDL runs in its own auto-commit (sqlite3 default isolation_level
    # behavior). Idempotency:
    #   - CREATE TABLE IF NOT EXISTS — re-run safe
    #   - ALTER TABLE guarded by PRAGMA table_info — re-run safe
    #   - INSERT INTO schema_version LAST — partial apply leaves version=7,
    #     next ensure_schema retries cleanly.

    await conn.execute("""\
CREATE TABLE IF NOT EXISTS tool_configs (
    name TEXT PRIMARY KEY,
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")

    # Idempotent ADD COLUMN: skip if column already exists.
    async with conn.execute("PRAGMA table_info(agents)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "tool_overrides" not in cols:
        await conn.execute(
            "ALTER TABLE agents ADD COLUMN tool_overrides TEXT DEFAULT NULL"
        )

    # Schema_version INSERT goes LAST so a partial apply leaves version at 7.
    await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (8,))
    await conn.commit()
    version = 8
```

Existing rows in `agents` get `tool_overrides=NULL` automatically (locked-down NULL preserved — agent has no per-tool overrides, uses tool-level defaults).

### Checkpoints

- [ ] **Platform package landed** — `the_one/platform/` package exists with four submodules; helpers replace direct platform-coupled calls in the seven existing tools (will land in L4-L6); platform-layer tests cover Linux/WSL behavior without Linux-only assumptions in the helpers themselves
- [ ] **Schema v8 applied** — `CURRENT_VERSION = 8`, `tool_configs` table created, `agents.tool_overrides` column added, migration wrapped in explicit transaction, both fresh and v7-fixture migration tests green
- [ ] **Resolver landed** — `resolve(schema, tool_config, agent_override) -> Config` is pure-function, narrowing + substitution paths both unit-tested via fixture Pydantic Config, locked-down NULL semantic documented and tested, Tool ABC updated, `BuiltinToolProvider.get_tools()` shifted to per-agent instantiation, `AgentFactory.create()` invokes the resolver
- [ ] **Filesystem tools migrated** — `ReadFileTool`, `WriteFileTool`, `ListDirTool` route through `the_one/platform/paths.py`; behavior unchanged; regression tests green
- [ ] **Execution tools migrated** — `ShellTool` routes through `the_one/platform/shell.py`; `PythonExecTool` routes through `the_one/platform/interpreter.py`; behavior unchanged; regression tests green
- [ ] **Web tools migrated** — `HttpRequestTool`, `WebSearchTool` route through Tool ABC `__init__(config)` contract; no platform-layer routing needed (httpx is already cross-platform); regression tests green
- [ ] **Integration verified** — full default unit suite green (modulo pre-existing CSS-token red); browser suite green; AIAT smoke green; `/api/agents` payload includes `tool_overrides` (default `null`) without breaking JS consumers; comprehensive regression sweep returns no unexpected matches

### Adaptation Criteria

**Divert if**:
- The Tool ABC change (Decision 3, L3) breaks more than two browser tests in unexpected ways. Browser tests rely on tool registry shape via `/api/agents` payloads; the per-agent instantiation shift may surface issues invisible to unit tests. Investigate before continuing.
- The resolver's substitution-path fixture test surfaces a design ambiguity — e.g., what happens when `Substitute` is declared on a non-string field, or when an `Annotated` marker is missing. Stop, refine the design (likely a default-to-Narrow rule), re-test.
- Schema v8 migration fails on a real DB fixture in a way that suggests `ALTER TABLE ADD COLUMN` doesn't behave as expected on existing v7 DBs. Fall back to the v3-pattern table-rebuild if needed.
- A platform-layer helper introduces a Linux-only assumption that would break Windows/macOS later. The mission constraint is "Linux-verified for now, but no Linux-only assumptions in tool code"; the *platform layer itself* may have OS-specific code paths but each helper must have a documented cross-platform contract.
- L3 surfaces that `BuiltinToolProvider.get_tools()` is called from sites other than `AgentFactory.create()` (callers we haven't audited). The shift from singleton to per-agent will break those callers. Audit before L3 implementation.

**Acceptable variations**:
- Whether `Narrow` and `Substitute` are sentinel classes (`class Narrow: pass`) or instances of a marker enum (`class FieldSemantic(Enum): NARROW = "narrow"; SUBSTITUTE = "substitute"`) — pick the simpler one in L3 design.
- Whether the resolver lives at `the_one/agent/resolver.py` or `the_one/tools/resolver.py` — pick wherever has cleaner imports in L3.
- Whether per-tool Configs introduced in F2 are empty `BaseModel` defaults, or `pass` subclasses (`class ShellConfig(BaseModel): pass`). Default to the former (no per-tool subclasses) unless a test or migration forces otherwise.
- Whether `AgentConfig.tool_overrides` field defaults to `None` or `{}` — Decision 1 specifies `None` (locked-down NULL); confirm in L2 implementation but reject `{}` as a default since it would conflate "no overrides set" with "explicit empty overrides".
- Whether the schema v8 migration uses `ALTER TABLE ADD COLUMN` (simple) or the v3-pattern table-rebuild. SQLite supports `ADD COLUMN` directly; the rebuild pattern is overkill for adding a single nullable column. Default to `ADD COLUMN` unless an existing FK constraint forces a rebuild.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `01-platform-package-scaffolding` — Create `the_one/platform/` package with `paths.py`, `shell.py`, `interpreter.py`, `tempdirs.py`, `__init__.py`. Each helper has a documented cross-platform contract; F2 verifies Linux/WSL behavior. **Extraction pattern: copy-don't-cut** — helpers are written *alongside* the existing platform-coupled code in `the_one/tools/{filesystem,shell,python_exec}.py` (no tool changes in L1; tools migrate to call the new helpers in L4-L6). This keeps L1 a pure additive change, simplifies L1's regression assertion ("tests are unchanged because tools are unchanged"), and lets L4-L6 land tool-by-tool with minimal blast radius. Tests under `tests/test_platform_*.py` exercise each helper directly (path canonicalization, shell selection, interpreter resolution).

- [ ] `02-schema-v8-tool-configs-and-overrides` — Bump `CURRENT_VERSION` 7 → 8. Add `tool_configs` table (mirrors `mcp_sources` shape; PK `name`, `config TEXT DEFAULT '{}'`, `created_at`, `updated_at`). Add `agents.tool_overrides TEXT DEFAULT NULL` column via `ALTER TABLE` guarded by `PRAGMA table_info(agents)` for idempotency. Use individual `await conn.execute()` calls (NOT `executescript()` — its implicit COMMIT breaks atomicity) inside an explicit transaction (BEGIN/COMMIT) per F1 debrief recommendation. Add `ToolConfigRepository` to `the_one/db/repositories.py` (mirrors `MCPSourceRepository`). Update `AgentConfig` Pydantic model with `tool_overrides: dict[str, dict] | None = None` field. **`SQLiteAgentStore` SQL audit (explicit list — must update every site):**
  - `the_one/db/repositories.py:47-83` — `SQLiteAgentStore.save()` has a hard-coded INSERT/UPDATE column list (currently 12 columns); extend to 13 to include `tool_overrides`. Update `ON CONFLICT DO UPDATE SET` clause too. (Line numbers per HEAD at flight-design time; re-grep at L2 leg-design per F1's "line-citations decay" lesson.)
  - `the_one/db/repositories.py:95-109` — `SQLiteAgentStore._row_to_config()` row reader; add JSON deserialize for the new column.
  - `the_one/agent/store.py::FilesystemConfigStore` — uses `model_dump()` round-trip; picks up the new field automatically. Verify with a roundtrip test, no SQL edit needed.
  - `the_one/interfaces/web/api.py` — `/api/agents` GET/POST/PUT handlers invoke `AgentConfig.model_dump()`. Field will appear as `"tool_overrides": null` in payloads. **Consumer audit**: grep `tests/browser/` for any assertion on `/api/agents` response shape — confirm none break. F1 added `direct_actions` removal which already cleared this surface; F2 adds back a single nullable field. Inbound JSON missing the field is silently allowed via `model_config = {"extra": "ignore"}`. Inbound JSON with malformed `tool_overrides` (e.g., not a dict) raises Pydantic validation error — verified L2 test asserts this.
  - **Tests**: `tests/test_db_migration.py::TestSchemaV8` — (i) fresh DB migrates straight to v8; (ii) v7 fixture DB with non-null `enabled_tools` row → v8 preserves the row, adds `tool_overrides=NULL`; (iii) idempotent re-run (rewind schema_version, re-migrate). `tests/test_db_repositories.py` (or wherever `MCPSourceRepository` is tested) — `ToolConfigRepository` CRUD. `tests/test_config.py` — `AgentConfig.tool_overrides` defaults to `None`; explicit `{"shell": {"output_cap": 1000}}` roundtrips through `model_dump` → `model_validate` cleanly; `extra: "ignore"` survives a stale `direct_actions: true` payload. `tests/test_db_api.py` — `/api/agents` GET returns `"tool_overrides": null` for the default agent; POST accepting an explicit `tool_overrides` dict roundtrips correctly.

- [ ] `03-tool-policy-resolver-and-tool-abc` — Implement `ToolPolicyResolver` as a pure function in `the_one/tools/resolver.py` (chosen at flight-design time — resolver is a property of the tool config system; F3-F5's Configs live next door in `the_one/tools/`). Define `Narrow` / `Substitute` as **sentinel marker classes** (never instantiated). Resolver lookup pattern: `Narrow in field.metadata` (class-identity check). Verified working against Pydantic v2 `Annotated[type, Marker]` field metadata. Update `Tool` ABC: add `Config: type[BaseModel] = BaseModel` class attribute and `__init__(config: BaseModel | None = None)` defaulting to `Config()` when omitted. Defensive: if `tool.Config.model_fields == {}`, the resolver short-circuits and returns `Config()` immediately (no Annotated dispatch). Update `BuiltinToolProvider.get_tools(configs=None)` from singleton-return to per-agent instantiation; default-None path calls `cls.Config()` for introspection callers (`/api/tools` endpoint, test_builtins.py). Update `AgentFactory.create()` to invoke the resolver with each tool's `Config` schema, the tool-level config from `tool_configs.list_all()`, and the agent-level override from `AgentConfig.tool_overrides`. Pick L3 implementation factoring per the Technical Approach note: factory-drives-resolution OR provider-drives-resolution — default to provider-drives unless complexity surfaces. Tests: resolver narrowing path (override <= tool config OK; override > tool config raises ValueError), substitution path via fixture (per-key semantic dispatch verification — MCP-readiness), locked-down NULL semantic (override `None` preserves tool config), empty-Config short-circuit, Tool ABC instantiation (with Config / without Config / with mismatched-type raises Pydantic error), `BuiltinToolProvider.get_tools()` per-agent registry isolation invariant (call twice, distinct instances), `BuiltinToolProvider.get_tools(None)` introspection path returns 7 tools with default empty Configs. **All 7 existing tools' tests must still pass** — they receive empty Configs, behave identically.

- [ ] `04-migrate-filesystem-tools` — Migrate `ReadFileTool`, `WriteFileTool`, `ListDirTool` (`the_one/tools/filesystem.py`) to use `the_one/platform/paths.py` helpers in place of direct `Path(path).expanduser().resolve()` calls. No new Config fields — `Tool.Config = BaseModel` default applies (F3 will introduce path scope). Regression tests prove pre-F2 behavior preserved. Update tests as needed.

- [ ] `05-migrate-execution-tools` — Migrate `ShellTool` (`the_one/tools/shell.py`) to use `the_one/platform/shell.py` for shell selection. Migrate `PythonExecTool` (`the_one/tools/python_exec.py`) to use `the_one/platform/interpreter.py` for Python interpreter resolution (replaces hardcoded `"python3"` with `interpreter.resolve_python()`). Regression tests prove behavior unchanged. F4 will harden these tools with caps and denylists.

- [ ] `06-migrate-web-tools` — `HttpRequestTool` and `WebSearchTool` (`the_one/tools/web.py`) don't need platform-layer routing (httpx is already cross-platform; their HTML parsing is platform-independent). This leg is small: confirm the Tool ABC contract migration (`Config = BaseModel`, `__init__(config)`) doesn't regress them; update any minor wiring (e.g., User-Agent string) if F2 design surfaces a need. Regression tests.

- [ ] `07-integration-verification` — Full default unit suite + browser suite + AIAT smoke. F2-specific regression sweep (different from F1 L6's shape — F2 sweep targets new patterns: any direct `Path(path).expanduser().resolve()` calls remaining in `the_one/tools/` outside the platform layer; any zero-arg `BuiltinToolProvider().get_tools()` callers that now need `None` explicitly; any tool that doesn't subclass `Tool.Config = BaseModel`). `/api/agents` payload audit: `tool_overrides` field present, defaults to `null`, serializes/deserializes through `extra: "ignore"` AgentConfig roundtrip without surprise. Documentation updates (`agents.md` and `CLAUDE.md`): document the platform package's cross-platform contract; document the resolver's narrow/substitute semantics; document the session-bound tool-config freshness contract (Decision 8). **F1 layered-prompt-model documentation carryover** (F1 debrief recommendation): NOT in F2 scope — defer to F6 (the Tools admin section flight) which has natural docs touchpoints, or to a dedicated maintenance task. Document the deferral explicitly in the flight log.

---

## Post-Flight

### Completion Checklist

- [ ] All legs landed (L1-L7, none optional)
- [ ] `the_one/platform/` package exists with `paths.py`, `shell.py`, `interpreter.py`, `tempdirs.py` populated with helpers extracted from the seven existing tools
- [ ] Schema is v8; `tool_configs` table exists; `agents.tool_overrides` column exists; migration tested on fresh and v7-fixture DBs
- [ ] `ToolConfigRepository` mirrors `MCPSourceRepository` shape; CRUD tested
- [ ] `AgentConfig.tool_overrides` field exists, defaults to `None`, roundtrips through `model_dump` / Pydantic
- [ ] `Tool` ABC has `Config: type[BaseModel] = BaseModel` class attribute and `__init__(config)`; `BuiltinToolProvider.get_tools()` instantiates per-agent
- [ ] `ToolPolicyResolver` (`resolve(schema, tool_config, agent_override) -> BaseModel`) implemented; narrowing + substitution paths unit-tested via fixture Pydantic Config; locked-down NULL semantic documented inline
- [ ] All 7 existing tools migrated through Tool ABC contract; filesystem + execution tools route through platform layer; web tools confirmed unchanged
- [ ] Default unit test suite green (modulo pre-existing CSS-token red, predates F1)
- [ ] Browser test suite green (M04 baseline preserved; visual snapshots gitignored per user-global instruction)
- [ ] AIAT smoke green (`pytest -m live tests/test_aiat.py`)
- [ ] No regressions in any L1-L6 surface (no stale removed-tool refs, no `/workspace`, no `behaviors.py`, no `DEFAULT_SYSTEM_PROMPT`)
- [ ] Code committed; flight log updated; flight status set to `landed`

### Verification

**Static (grep / read):**

```bash
# Platform package exists
ls the_one/platform/
# Expected: __init__.py paths.py shell.py interpreter.py tempdirs.py

# Tool ABC has Config + __init__(config)
rg -n "Config: type\[BaseModel\]" the_one/tools/base.py
rg -n "def __init__\(self, config" the_one/tools/base.py

# BuiltinToolProvider.get_tools accepts a dict
rg -n "def get_tools\(self" the_one/tools/builtins.py
# Expected: signature includes configs: dict[str, BaseModel] (or equivalent)

# AgentConfig has tool_overrides
rg -n "tool_overrides" the_one/agent/config.py
# Expected: field declaration + default None

# Schema v8
rg -n "^CURRENT_VERSION = " the_one/db/schema.py
rg -n "if version < 8:" the_one/db/schema.py

# Resolver exists
rg -n "def resolve\(" the_one/agent/resolver.py the_one/tools/resolver.py 2>/dev/null

# Tools no longer carry hardcoded platform-coupled calls
rg -n "asyncio.create_subprocess_shell|\"python3\"" the_one/tools/
# Expected: no matches in shell.py, python_exec.py (extracted into platform layer)

# No L1-L6 regressions
rg -n "self_deploy|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool|behaviors\.py|DIRECT_ACTIONS|match_direct_action|direct_actions|workspace_dir|/workspace|concourse_target|concourse_pipeline|14 built-in tools|currently v3|## Self-Deployment|self-modifying" the_one/ tests/ ci/ scripts/ docker-compose.yml CLAUDE.md
# Expected: matches confined to the_one/db/schema.py REMOVED set + tests/test_db_migration.py fixtures (per F1 baseline)
```

**Dynamic (test suite):**

```bash
make rebuild               # full rebuild against new code
make test-unit             # default unit suite must pass (modulo pre-existing CSS red)
make test-browser          # browser suite must pass
pytest -m live tests/test_aiat.py  # AIAT smoke must pass

# Resolver smoke
python -c "
from pydantic import BaseModel
from typing import Annotated
from the_one.agent.resolver import resolve, Narrow, Substitute

class FakeConfig(BaseModel):
    cap: Annotated[int, Narrow] = 100
    token: Annotated[str, Substitute] = ''

# Narrow: agent override <= tool config OK
r = resolve(FakeConfig, {'cap': 50, 'token': 'tool-tok'}, {'cap': 30, 'token': 'agent-tok'})
assert r.cap == 30 and r.token == 'agent-tok', r
# Locked-down NULL: agent override None preserves tool config
r = resolve(FakeConfig, {'cap': 50, 'token': 'tool-tok'}, None)
assert r.cap == 50 and r.token == 'tool-tok', r
print('OK')
"

# Per-agent registry isolation smoke (use public ToolRegistry.get(name), not private _tools)
python -c "
import asyncio
from the_one.agent.factory import AgentFactory
async def main():
    f = AgentFactory()
    a1 = await f.create()
    a2 = await f.create()
    assert a1.tools is not a2.tools, 'registry shared between agents'
    # Each named tool should be a distinct instance per agent (Decision 3).
    for name in ['shell', 'read_file', 'write_file', 'list_dir', 'python_exec', 'http_request', 'web_search']:
        t1 = a1.tools.get(name)
        t2 = a2.tools.get(name)
        assert t1 is not t2, f'tool singleton leaked for {name}'
    print('OK')
asyncio.run(main())
"
```

**Manual (none required for F2):** F2 has no HAT leg. The deploy pipeline's `/api/selftest` exercises one tool path live; that's sufficient operator-side verification.

---

## Architect Q&A — design refinements captured

The flight-design Architect surfaced six clarifying questions during the design review. Resolutions:

1. **`BuiltinToolProvider.get_tools()` zero-arg form for `/api/tools` introspection** → Decision 9. Default `configs=None` produces tools with empty Configs. No separate `describe_tools()` method.

2. **Tool-config freshness contract for mid-session operator updates** → Decision 8. Session-bound; mutations apply at next `AgentFactory.create()`. F6's admin UI must communicate "applies to next session" clearly.

3. **MCP alignment of `tool_classes() -> list[type[Tool]]`** → Decision 10. The hypothetical `tool_classes()` Protocol method is NOT added. `BuiltinToolProvider.get_tools(configs)` does its own internal name→class lookup; MCP servers will do their own internal manifest→schema lookup. Protocol stays at `name` + `get_tools()`.

4. **Schema v8 `ALTER TABLE ADD COLUMN` vs v3-rebuild pattern** → ADD COLUMN with `PRAGMA table_info` idempotency guard, inside an explicit transaction (no `executescript` — its implicit COMMIT defeats atomicity). The full table rebuild is overkill for a single nullable column; the idempotency guard handles partial-apply state cleanly.

5. **F1's missed integration test (`AgentFactory.create()` with non-empty `system_prompt` asserting layered composition flows through to `Message.system(...)`)** → NOT in F2 scope. F2's focus is the resolver scaffold, not adding F1 coverage. The L7 AIAT smoke exercises a real agent with a real system prompt; that's incidental coverage. **Defer the explicit unit/integration test to a maintenance leg** so it lands as standalone work, not buried inside F2.

6. **`AgentConfig.tool_overrides: dict[str, dict] | None` inner-dict type ambiguity** → The resolver's contract is:
   - **Unknown tool name in overrides** (no matching `_TOOL_CLASSES` entry): silently ignored. Mirrors `enabled_tools`/`disabled_tools` strip behavior from v7. Agent loads cleanly even if overrides reference a removed tool.
   - **Unknown key inside a tool's overrides** (key not in `tool.Config.model_fields`): Pydantic default `extra="ignore"` silently drops it. Document in resolver docstring; add a unit test asserting drop-on-unknown-key.
   - **Type mismatch** (override value's type incompatible with `Config` field): Pydantic raises `ValidationError`. Tests assert this raises and the error message is operator-readable.
   - **Narrow violation** (override value is wider than tool config): resolver raises `ValueError("agent override widens %s.%s; only narrowing allowed")`. Tests assert this raises with a clear message.

These six clarifications are lockable contracts for L3 implementation; deviations should generate flight-log Deviation entries.
