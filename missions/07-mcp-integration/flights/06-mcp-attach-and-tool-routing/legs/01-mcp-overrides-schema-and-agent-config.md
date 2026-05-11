# Leg: 01-mcp-overrides-schema-and-agent-config

**Status**: completed
**Flight**: [Per-agent MCP attach + tool-routing in agent loop](../flight.md)

## Objective

Land the per-agent MCP credential override surface end-to-end: `MCPSourceOverride` Pydantic schemas with all-`Substitute` markers in `the_one/mcp/_overrides.py`, the `mcp_overrides: dict[str, dict[str, Any]] | None = None` field on `AgentConfig`, and the v11 SQLite migration that adds the `mcp_overrides TEXT` column to the `agents` table — including SQLiteAgentStore round-trip and the cycle-1 H1 introspection regression test that locks the `Annotated[T | None, Substitute] = None` placement.

## Context

**Why this leg**: F6's per-agent override path needs a parallel `mcp_overrides` field on `AgentConfig`, NOT an extension of the existing `tool_overrides` (mission-level decision §1 — built-in tools key by tool name, MCP sources key by source identity, single dict creates a real collision class when an operator names a source `shell`). L1 is the smallest standalone unit that lands the data shape so L2 can read it during `MCPToolProvider.get_tools_for_agent`.

**Why all-`Substitute`**: credentials don't have a narrowing semantic — an operator-set bearer token is REPLACED by the agent's bearer token, not narrowed to a substring. Future fields with narrowing semantic (e.g. a per-source `read_only` boolean) can use `Narrow` without changing the schema shape.

**Why the inverted-`Annotated` placement**: per Architect cycle-1 H1 — `Annotated[T, Substitute] | None = None` (the broken form) places metadata INSIDE the Union, which Pydantic v2 hoists during model construction such that `model_fields[name].metadata == []` and `the_one.tools.resolver.resolve` raises `ValueError: ... no Narrow/Substitute marker`. The correct form is `Annotated[T | None, Substitute] = None`. Verified empirically by the Architect — no existing tools use the broken placement; the Substitute marker dispatches correctly under the inverted form. **L1 ships an introspection regression test** that reads `field_info.metadata` directly so a future schema addition cannot silently regress.

**Why v11, ALTER TABLE pattern (NOT table rebuild)**: the `agents` table has NO CHECK constraints needing rebuild (`provider_config_id` is `REFERENCES llm_providers(id) ON DELETE SET NULL`, but that's a foreign-key action, not a CHECK). Per Architect cycle-1 L3, the right precedent is the v8 migration at `the_one/db/schema.py::ensure_schema` lines 292-332 (`tool_overrides` column add) — individual `await conn.execute(...)` calls (NOT `executescript`), idempotent `PRAGMA table_info` guard, `INSERT OR IGNORE INTO schema_version (version) VALUES (?)` LAST. Add `mcp_overrides TEXT` (NO `DEFAULT NULL` — per the v8 comment block at lines 320-324, an explicit `DEFAULT NULL` surfaces in PRAGMA as the literal string "NULL" rather than Python None).

**Why this leg, not L2**: separating the data-shape surface from the consumer-wiring surface keeps L2 pure-runtime-wiring. L1 is verifiable in isolation via 12-14 round-trip tests; L2 reads `config.mcp_overrides` and never has to think about the storage layer.

**Prior leg outcomes (flight log)**:
- L0 landed (move `MCPAuthRequired` to canonical `the_one/mcp/errors.py`; add `MCPRegistrationError`; retire F5 lazy imports). Status `landed`. **Not committed yet** — flight-end commit per agentic-workflow protocol.
- L0 deviation D1: docstring line wrap for ruff 100-char compliance.
- L0 anomaly A1: 18 failures + 7 errors in full-suite outside `docker compose` — all infra-driven (no docker daemon for aiosqlite worker thread, ASGI fixture, bwrap-privilege paths). Inside-container baseline expected at 1280 → 1282 with the new `tests/test_imports.py` tests.
- L0 added `MCPAuthRequired` and `MCPRegistrationError` re-exports to `the_one/mcp/__init__.py`. **L1 does NOT need to import either.** Available if needed.

**Stake**: schemas + field + migration + round-trip = ~110 LOC production + ~190 LOC tests. Verifiable in isolation; gates are mechanical (PRAGMA assertions, marker-introspection assertion, resolver dispatch assertion).

## Inputs

What exists before this leg runs:

- `the_one/agent/config.py::AgentConfig` — Pydantic model with `tool_overrides: dict[str, dict[str, Any]] | None = None` at line 65. **No `mcp_overrides` field yet.** Model validator: `model_config = {"extra": "ignore"}` at line 38.
- `the_one/db/schema.py:9` — `CURRENT_VERSION = 10`.
- `the_one/db/schema.py::ensure_schema` lines 292-332 — v8 ALTER TABLE pattern for `tool_overrides`. Verified: individual `await conn.execute(...)` calls; PRAGMA-check idempotency guard at lines 325-327; `INSERT OR IGNORE` at line 330 LAST; comment block at lines 320-324 warns "omit `DEFAULT NULL` — SQLite columns are nullable by default; an explicit `DEFAULT NULL` clause would surface in PRAGMA table_info as the literal string `NULL` rather than Python None."
- `the_one/db/repositories.py::SQLiteAgentStore.save` lines 56-94 — UPSERT statement explicitly lists 13 columns including `tool_overrides` at line 63 + line 75. Bind tuple at lines 78-91.
- `the_one/db/repositories.py::SQLiteAgentStore._row_to_config` lines 106-125 — parses `tool_overrides` at line 124: `tool_overrides=(json.loads(row["tool_overrides"]) if row["tool_overrides"] else None)`. Comment block at lines 120-123 explains the truthiness pattern + the v8 migration dependency.
- `the_one/tools/resolver.py::resolve` lines 195-260 — Narrow/Substitute dispatch. Substitute path at line 256 (`# Substitute path: no check; merge below performs replacement.`) + line 257 (`merged[key] = agent_override[key]`). For `tool_config=None`, the locked-down NULL semantic at lines 224-226 returns `schema.model_validate(merged)` where `merged = {}`.
- `the_one/tools/resolver.py::Substitute` lines 53-60 — sentinel marker class (never instantiated; identity dispatch via `m is Substitute` at line 236).
- `tests/test_db_repositories.py::TestSQLiteAgentStore` lines 81-160 — round-trip precedent. Specifically `test_tool_overrides_round_trip` (lines 140-152) and `test_tool_overrides_none_default` (lines 154-160) ARE the L1 mirror pattern.
- `tests/test_db_migration.py::TestSchemaV8` lines 203-onwards — v8 migration test precedent. Specifically `test_v8_fresh_db_includes_tool_configs_and_tool_overrides` (lines 206-269), `test_v8_migration_on_v7_fixture_db_preserves_existing_rows` (lines 271-328), `test_v8_migration_is_idempotent` (lines 330-onwards). v11 mirrors all three.
- `the_one/mcp/_overrides.py` — does NOT exist (verified at design time).
- `the_one/agents.md` "Module Map" + "Project Conventions" sections — convention documentation lives here; L6 docs-sweep covers `agents.md` updates (NOT L1).

## Outputs

What exists after this leg completes:

- `the_one/mcp/_overrides.py` (NEW) — defines `StdioMCPOverride` and `StreamableHttpMCPOverride` Pydantic models with all-`Substitute` markers using the inverted-`Annotated` pattern. ~90 LOC.
- `the_one/agent/config.py::AgentConfig` — gains `mcp_overrides: dict[str, dict[str, Any]] | None = None` field, sibling to `tool_overrides`. The field's docstring/comment block mirrors `tool_overrides`'s comment at lines 59-64 (locked-down NULL; outer-key contract; inner `dict[str, Any]` not bare `dict`). ~12 LOC.
- `the_one/db/schema.py` — `CURRENT_VERSION` bumped from `10` to `11`; new `if version < 11:` block AFTER the v10 block (lines 355-402). v11 follows the v8 ALTER pattern verbatim — individual `await conn.execute(...)`, PRAGMA-check idempotency, `INSERT OR IGNORE` LAST, no `DEFAULT NULL`. ~22 LOC.
- `the_one/db/repositories.py::SQLiteAgentStore.save` — UPSERT extends column list with `mcp_overrides` (alphabetical position is by-design irrelevant; insert in the same group as `tool_overrides` for diff readability — between `tool_overrides` and `created_at`). Bind tuple extends with `json.dumps(config.mcp_overrides) if config.mcp_overrides is not None else None`. ~6 LOC.
- `the_one/db/repositories.py::SQLiteAgentStore._row_to_config` — parses `mcp_overrides=(json.loads(row["mcp_overrides"]) if row["mcp_overrides"] else None)`, mirroring the `tool_overrides` parse at line 124. ~3 LOC.
- `tests/test_mcp_overrides.py` (NEW) — schema introspection regression test (locks `Annotated[T | None, Substitute] = None` placement); resolver dispatch tests for both schema variants; locked-down NULL semantic test. ~110 LOC, ~10 tests.
- `tests/test_db_repositories.py::TestSQLiteAgentStore` — adds `test_mcp_overrides_round_trip` and `test_mcp_overrides_none_default`, mirroring lines 140-160. ~25 LOC, 2 tests.
- `tests/test_db_migration.py` — adds `class TestSchemaV11` mirroring `TestSchemaV8` (lines 203-onwards). 3 tests: fresh-DB shape, v10→v11 preserves existing rows, idempotent re-run. ~115 LOC, 3 tests.
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry appended.

## Acceptance Criteria

- [ ] `the_one/mcp/_overrides.py` exists and defines `StdioMCPOverride` (with `env: Annotated[dict[str, str] | None, Substitute] = None`) and `StreamableHttpMCPOverride` (with `headers: Annotated[dict[str, str] | None, Substitute] = None` AND `bearer_token: Annotated[str | None, Substitute] = None`). Both `frozen=True` via `model_config = ConfigDict(frozen=True)`.
- [ ] Inverted-`Annotated` placement is correct: `python -c "from the_one.mcp._overrides import StdioMCPOverride; from the_one.tools.resolver import Substitute; m = StdioMCPOverride.model_fields['env'].metadata; assert any(x is Substitute for x in m), m"` exits 0. Same check for `headers`, `bearer_token`.
- [ ] `AgentConfig.mcp_overrides: dict[str, dict[str, Any]] | None = None` field exists at `the_one/agent/config.py`.
- [ ] `the_one/db/schema.py::CURRENT_VERSION == 11`.
- [ ] v11 migration block exists at `the_one/db/schema.py::ensure_schema` AFTER the v10 block. Pattern matches v8: individual `await conn.execute(...)` calls (NOT `executescript`); `PRAGMA table_info(agents)` idempotency guard; `INSERT OR IGNORE INTO schema_version (version) VALUES (11)` LAST.
- [ ] `agents.mcp_overrides` column has type `TEXT`, is nullable (notnull=0), and has NO default value (`dflt_value is None`, NOT the literal string "NULL").
- [ ] `SQLiteAgentStore.save` UPSERT round-trips `config.mcp_overrides` correctly: dict-shaped value persists as JSON; `None` persists as SQL `NULL`.
- [ ] `SQLiteAgentStore._row_to_config` parses `mcp_overrides`: `None` and empty string both deserialize to Python `None`; non-empty JSON deserializes to `dict[str, dict[str, Any]]`.
- [ ] `resolve(StdioMCPOverride, None, {"env": {"FOO": "bar"}})` returns a `StdioMCPOverride` instance with `env == {"FOO": "bar"}` (Substitute path: tool-level None replaced by agent value).
- [ ] `resolve(StdioMCPOverride, None, None)` returns a `StdioMCPOverride` instance with `env is None` (locked-down NULL semantic, resolver lines 224-226).
- [ ] `resolve(StreamableHttpMCPOverride, None, {"headers": {"X-Foo": "y"}, "bearer_token": "tok"})` returns a model with `headers == {"X-Foo": "y"}` AND `bearer_token == "tok"`.
- [ ] `resolve(StreamableHttpMCPOverride, None, {"headers": {"X-Foo": "y"}})` partial override returns model with `headers` set, `bearer_token is None`.
- [ ] `pytest tests/test_mcp_overrides.py -v` is green (~10 tests).
- [ ] `pytest tests/test_db_repositories.py::TestSQLiteAgentStore -v` is green (12 existing tests + 2 new = 14).
- [ ] `pytest tests/test_db_migration.py::TestSchemaV11 -v` is green (3 new tests).
- [ ] `pytest tests/test_db_migration.py::TestSchemaV8 tests/test_db_migration.py::TestSchemaV9 tests/test_db_migration.py::TestSchemaV10 -v` is green (regression — `CURRENT_VERSION` bumps at lines 226, 430, 558 plus literal-10 max-version assertions at lines 458, 494, 589 rewritten to `CURRENT_VERSION` indirection ensure these tests still pass against `CURRENT_VERSION = 11`).
- [ ] `ruff check the_one/ tests/` is clean.
- [ ] Full suite `pytest --tb=no -q --timeout=300` is green inside `docker compose exec the-one` (note: outside-container suite has env-driven failures per L0 anomaly A1; flight-end review re-runs the canonical gate).

## Verification Steps

How to confirm each criterion is met:

```bash
# Schema module surface
python -c "from the_one.mcp._overrides import StdioMCPOverride, StreamableHttpMCPOverride; print(StdioMCPOverride.model_fields.keys(), StreamableHttpMCPOverride.model_fields.keys())"

# Marker introspection (the L1 H1 regression lock)
python -c "
from the_one.mcp._overrides import StdioMCPOverride, StreamableHttpMCPOverride
from the_one.tools.resolver import Substitute
for cls in (StdioMCPOverride, StreamableHttpMCPOverride):
    for name, field in cls.model_fields.items():
        markers = [m for m in field.metadata if m is Substitute]
        assert len(markers) == 1, f'{cls.__name__}.{name} marker count: {len(markers)} (expected 1)'
print('OK')
"

# AgentConfig field
python -c "from the_one.agent.config import AgentConfig; assert 'mcp_overrides' in AgentConfig.model_fields; print('OK')"

# CURRENT_VERSION + v11 surface (single Python invocation; uses pytest's tmp_path-equivalent)
python -c "
import asyncio, tempfile, os
import aiosqlite
from the_one.db.schema import CURRENT_VERSION, ensure_schema
assert CURRENT_VERSION == 11, CURRENT_VERSION

async def check():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, 'v11.db')
        conn = await aiosqlite.connect(db)
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys=ON')
        await ensure_schema(conn)
        async with conn.execute('PRAGMA table_info(agents)') as cur:
            cols = {r['name']: r for r in await cur.fetchall()}
        col = cols['mcp_overrides']
        assert col['type'] == 'TEXT', col['type']
        assert col['notnull'] == 0, col['notnull']
        assert col['dflt_value'] is None, col['dflt_value']
        async with conn.execute('SELECT version FROM schema_version ORDER BY version') as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert max(versions) == 11, versions
        await conn.close()
asyncio.run(check())
print('OK')
"

# Round-trip resolver tests
pytest tests/test_mcp_overrides.py -v

# SQLiteAgentStore round-trip tests (existing + new)
pytest tests/test_db_repositories.py::TestSQLiteAgentStore -v

# Migration tests (existing + new)
pytest tests/test_db_migration.py::TestSchemaV8 tests/test_db_migration.py::TestSchemaV11 -v

# Full suite + lint (run inside docker compose for canonical baseline)
docker compose exec the-one pytest --tb=no -q --timeout=300
ruff check the_one/ tests/
```

## Implementation Guidance

The order matters — schema module first (no DB dependency), then field, then migration, then repository wiring, then tests. Each step is independently verifiable.

1. **Create `the_one/mcp/_overrides.py` with both Pydantic schemas.**
   - File header (module docstring): explain the all-`Substitute` semantic; explain the inverted-`Annotated[T | None, Substitute] = None` placement and why (per Architect cycle-1 H1 — Pydantic v2 hoists metadata inside Union types).
   - Imports: `from typing import Annotated`; `from pydantic import BaseModel, ConfigDict`; `from the_one.tools.resolver import Substitute`.
   - Define `StdioMCPOverride(BaseModel)`:
     - `model_config = ConfigDict(frozen=True)`
     - `env: Annotated[dict[str, str] | None, Substitute] = None`
     - Class docstring explains: substitution-only overlay; spawn-time env-var overlay onto the source's `secrets["env"]`; references the `Annotated[T | None, Substitute] = None` placement convention with a 1-paragraph rationale.
   - Define `StreamableHttpMCPOverride(BaseModel)`:
     - `model_config = ConfigDict(frozen=True)`
     - `headers: Annotated[dict[str, str] | None, Substitute] = None`
     - `bearer_token: Annotated[str | None, Substitute] = None`
     - Class docstring: same `Annotated` placement note + the per-field rationale (header dict overlay; bearer-token replaces source-stored token at `auth=...` injection time).
   - Total: ~90 LOC including docstrings.

2. **Add `mcp_overrides` field to `AgentConfig` at `the_one/agent/config.py`.**
   - Locate the `tool_overrides` field declaration at lines 59-65 (current shape: `tool_overrides: dict[str, dict[str, Any]] | None = None` with a 5-line comment).
   - Insert `mcp_overrides` immediately AFTER `tool_overrides` so the two override surfaces sit together. Comment block:
     ```python
     # Per-agent MCP source override dict — shape parallels `tool_overrides`
     # but keys by source NAME (NOT tool name). The outer dict's key is the
     # MCPSource.name; the inner dict's keys are validated against the
     # transport-specific schema in `the_one/mcp/_overrides.py`
     # (StdioMCPOverride or StreamableHttpMCPOverride). None = no overrides
     # set (locked-down NULL semantic, mirrors `tool_overrides` and
     # `enabled_tools`). Inner type is `dict[str, Any]` (NOT bare `dict`)
     # for the same Pydantic v2 inner-validation reason as `tool_overrides`.
     mcp_overrides: dict[str, dict[str, Any]] | None = None
     ```
   - Total: ~12 LOC including comment.

3. **Bump `CURRENT_VERSION` to 11 in `the_one/db/schema.py:9`.**
   - Single-character change: `CURRENT_VERSION = 10` → `CURRENT_VERSION = 11`.

4. **Add v11 migration block to `the_one/db/schema.py::ensure_schema` AFTER the v10 block.**
   - The v10 block ends at line 402 (`version = 10`). v11 starts immediately after.
   - Pattern verbatim from v8 (lines 292-332):
     ```python
     if version < 11:
         # Add `mcp_overrides` JSON column to `agents` for per-agent MCP
         # source override dispatch (mission 07 flight 06 leg 01 design).
         # Mirrors the v8 ALTER pattern for `tool_overrides` — TEXT column,
         # nullable, NO `DEFAULT NULL` clause (the explicit clause would
         # surface in PRAGMA table_info as the literal string "NULL"
         # rather than Python None — see v8 comment block).
         #
         # Idempotency: PRAGMA-check the column presence so a re-run after
         # partial-apply is a no-op. `INSERT OR IGNORE` on schema_version
         # LAST, mirroring the v8/v9/v10 pattern.
         async with conn.execute("PRAGMA table_info(agents)") as cursor:
             existing_cols = {row[1] for row in await cursor.fetchall()}
         if "mcp_overrides" not in existing_cols:
             await conn.execute("ALTER TABLE agents ADD COLUMN mcp_overrides TEXT")

         await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (11,))
         await conn.commit()
         version = 11
     ```
   - Total: ~22 LOC.

5. **Update `SQLiteAgentStore.save` UPSERT in `the_one/db/repositories.py`.**
   - Find the INSERT column list at lines 60-63 and the bind-tuple at lines 78-91.
   - Add `mcp_overrides` to the column list AFTER `tool_overrides` (so the column ordering reads `... tool_overrides, mcp_overrides, created_at, updated_at`).
   - Increase the `VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)` count from 13 to 14.
   - Add `mcp_overrides=excluded.mcp_overrides,` to the `ON CONFLICT(name) DO UPDATE SET` clause (line 75 area).
   - Add the bind: `json.dumps(config.mcp_overrides) if config.mcp_overrides is not None else None,` immediately AFTER the existing `tool_overrides` bind (line 89-area).
   - Total: ~6 LOC delta.

6. **Update `SQLiteAgentStore._row_to_config` in `the_one/db/repositories.py:106-125`.**
   - Add to the `AgentConfig(...)` constructor call (immediately after the `tool_overrides=` line at 124):
     ```python
     mcp_overrides=(json.loads(row["mcp_overrides"]) if row["mcp_overrides"] else None),
     ```
   - The truthiness pattern at line 124's existing comment (lines 120-123) covers the new field too — no new comment needed.
   - Total: ~3 LOC delta.

7. **Create `tests/test_mcp_overrides.py` with the marker-introspection regression test + resolver dispatch tests.**
   - File scope: schemas + resolver dispatch only. The repository round-trip tests live in `tests/test_db_repositories.py` (step 8); the migration tests live in `tests/test_db_migration.py` (step 9).
   - **Ordering note** (per Architect cycle-1 medium #1): step 7 is independent of step 4 — these tests touch Pydantic + the resolver only, NOT the DB. Step 7 can run BEFORE the migration is applied. (Step 8's tests require the migration; the existing `agent_store` fixture at `tests/test_db_repositories.py:36-37` calls `ensure_schema` via the `conn` fixture at lines 19-32, which auto-applies v11 once `CURRENT_VERSION` is bumped.)
   - Tests to include (~10 total):
     - `test_stdio_override_env_marker_is_substitute` — `field_info.metadata` check for `env`. Locks the H1 placement.
     - `test_streamable_http_override_headers_marker_is_substitute` — same for `headers`.
     - `test_streamable_http_override_bearer_token_marker_is_substitute` — same for `bearer_token`.
     - `test_resolve_stdio_substitute_replaces_env` — `resolve(StdioMCPOverride, None, {"env": {"FOO": "bar"}}).env == {"FOO": "bar"}`.
     - `test_resolve_stdio_locked_down_null_returns_none_env` — `resolve(StdioMCPOverride, None, None).env is None`.
     - `test_resolve_streamable_http_full_override` — both headers + bearer_token set.
     - `test_resolve_streamable_http_partial_override` — only headers set, bearer_token stays None.
     - `test_resolve_streamable_http_locked_down_null` — `agent_override=None` returns model with both fields None.
     - `test_resolve_unknown_key_dropped_silently` — Pydantic's default `extra="ignore"` (resolver line 260) drops unknown keys; assert behavior at the resolver boundary.
     - `test_models_are_frozen` — attempt to mutate after construction raises `pydantic.ValidationError` or `dataclasses.FrozenInstanceError`-equivalent (Pydantic uses `ValidationError`).
   - Sample skeleton:
     ```python
     """L1 — MCP source override schema + resolver dispatch tests.

     Locks the inverted-Annotated[T | None, Substitute] = None placement
     per Architect cycle-1 H1 — Pydantic v2 hoists metadata inside Union
     types, so the broken form Annotated[T, Substitute] | None yields
     model_fields[name].metadata == [] and the resolver fails to dispatch.
     """
     from typing import get_type_hints

     import pytest
     from pydantic import ValidationError

     from the_one.mcp._overrides import StdioMCPOverride, StreamableHttpMCPOverride
     from the_one.tools.resolver import Substitute, resolve


     class TestMarkerPlacementRegression:
         """Lock Annotated[T | None, Substitute] = None placement (cycle-1 H1).

         A future schema addition that uses the broken Annotated[T, Substitute] | None
         placement would silently regress to marker_count==0 and break the resolver.
         These tests pin the working form.
         """

         def test_stdio_override_env_marker_is_substitute(self) -> None:
             markers = StdioMCPOverride.model_fields["env"].metadata
             assert any(m is Substitute for m in markers), markers

         def test_streamable_http_override_headers_marker_is_substitute(self) -> None:
             markers = StreamableHttpMCPOverride.model_fields["headers"].metadata
             assert any(m is Substitute for m in markers), markers

         def test_streamable_http_override_bearer_token_marker_is_substitute(self) -> None:
             markers = StreamableHttpMCPOverride.model_fields["bearer_token"].metadata
             assert any(m is Substitute for m in markers), markers


     class TestResolverDispatch:
         def test_resolve_stdio_substitute_replaces_env(self) -> None:
             merged = resolve(StdioMCPOverride, None, {"env": {"FOO": "bar"}})
             assert isinstance(merged, StdioMCPOverride)
             assert merged.env == {"FOO": "bar"}

         def test_resolve_stdio_locked_down_null_returns_none_env(self) -> None:
             merged = resolve(StdioMCPOverride, None, None)
             assert merged.env is None

         # ... continue with the other 7 tests
     ```
   - Total: ~110 LOC including docstrings.

8. **Add `mcp_overrides` round-trip tests to `tests/test_db_repositories.py::TestSQLiteAgentStore`.**
   - **Ordering note** (per Architect cycle-1 medium #1): step 8 REQUIRES step 4 (the v11 migration). The existing `agent_store` fixture at `tests/test_db_repositories.py:36-37` chains through the `conn` fixture at lines 19-32, which calls `await ensure_schema(connection)` at line 30 — so once `CURRENT_VERSION` is bumped (step 3) AND the v11 block is added (step 4), the round-trip tests pick up the new column automatically.
   - Insert AFTER `test_tool_overrides_none_default` at line 160. The tests mirror the precedent verbatim — only the field name changes:
     ```python
     async def test_mcp_overrides_round_trip(self, agent_store: SQLiteAgentStore) -> None:
         """Saving an agent with `mcp_overrides` set roundtrips through
         the SQLite store cleanly (F6 §1: dict[str, dict[str, Any]] keyed
         by source name)."""
         cfg = AgentConfig(
             name="mcp-override-test",
             mcp_overrides={
                 "github": {"bearer_token": "tok-a"},
                 "filesystem": {"env": {"ROOT": "/srv"}},
             },
         )
         await agent_store.save(cfg)
         loaded = await agent_store.load("mcp-override-test")
         assert loaded.mcp_overrides == {
             "github": {"bearer_token": "tok-a"},
             "filesystem": {"env": {"ROOT": "/srv"}},
         }

     async def test_mcp_overrides_none_default(self, agent_store: SQLiteAgentStore) -> None:
         """An agent without `mcp_overrides` set roundtrips as None
         (locked-down NULL semantic, mirrors tool_overrides)."""
         cfg = AgentConfig(name="no-mcp-overrides")
         await agent_store.save(cfg)
         loaded = await agent_store.load("no-mcp-overrides")
         assert loaded.mcp_overrides is None
     ```
   - Total: ~25 LOC.

9. **Add v11 migration tests to `tests/test_db_migration.py` and bump pre-existing `CURRENT_VERSION` / max-version assertions.**
   - Add `class TestSchemaV11` AFTER the existing `TestSchemaV10` class. (`TestSchemaV9` and `TestSchemaV10` classes already exist per Architect cycle-1 verification.)
   - The tests mirror `TestSchemaV8` lines 203-onwards verbatim — only the column name and version number change.
   - Three tests:
     - `test_v11_fresh_db_includes_mcp_overrides_column` — fresh `ensure_schema`; assert `agents.mcp_overrides` column exists, type=TEXT, notnull=0, dflt_value is None; assert max(versions) == CURRENT_VERSION; assert `CURRENT_VERSION == 11`.
     - `test_v11_migration_on_v10_fixture_db_preserves_existing_rows` — mirror `TestSchemaV8::test_v8_migration_on_v7_fixture_db_preserves_existing_rows` at line 271 verbatim — fresh `ensure_schema` to current shape (this is what the v8 precedent does too — the "v10 fixture" really means "current shape with rewound version pointer"), seed an agent with `tool_overrides` set, rewind via `DELETE FROM schema_version WHERE version >= 11`, re-run `ensure_schema`, assert the seed agent survives with `mcp_overrides=NULL`, assert `tool_overrides` column from v8 still present + populated. Do NOT attempt to programmatically invert the v10 `mcp_sources` rebuild ceremony — that's not what the v8 precedent does.
     - `test_v11_migration_is_idempotent` — call `ensure_schema` twice; assert no duplicate v11 schema_version rows; assert no errors.
   - **CURRENT_VERSION bump — three sites** (per Architect cycle-1 medium #2): `tests/test_db_migration.py` has THREE `assert CURRENT_VERSION == 10` sites that must bump to `== 11`:
     - `:226` — in `TestSchemaV8::test_v8_fresh_db_includes_tool_configs_and_tool_overrides`
     - `:430` — in `TestSchemaV9::test_v9_fresh_db_has_enabled_column_with_default_1`
     - `:558` — in `TestSchemaV10::test_v10_fresh_db_has_secrets_column_and_streamable_http_check`
     All three are mechanical string-equality bumps from `10` to `11`.
   - **Literal-10 max-version assertions — rewrite to `CURRENT_VERSION` indirection** (per Architect cycle-1 low #3): `tests/test_db_migration.py` has THREE `assert row[0] == 10` (or equivalent) sites — these are max-version-pointer assertions that ALSO break after the v11 bump:
     - `:458` — bump to `assert row[0] == CURRENT_VERSION` (or rewrite to follow the v8 file's existing precedent at line 267, 326, 413 which uses `max(versions) == CURRENT_VERSION`)
     - `:494` — same treatment
     - `:589` — same treatment
     Pick the indirection (`CURRENT_VERSION`) so future v12 doesn't repeat this chore. Add `from the_one.db.schema import CURRENT_VERSION` to the file's imports if not already present.
   - Total: ~115 LOC for the new class; ~6 LOC delta to existing `TestSchemaV8/V9/V10` classes (3 mechanical CURRENT_VERSION bumps + 3 indirection rewrites).

10. **Update flight log.**
    - Append a Leg Progress entry to `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` per the ARTIFACTS.md template (Started/Completed timestamps, Changes Made, Notes).
    - Document any deviations or anomalies in the appropriate flight-log sections.

11. **Run lint + targeted test gate before signaling handoff.**
    - `ruff check the_one/ tests/`
    - `pytest tests/test_mcp_overrides.py tests/test_db_repositories.py::TestSQLiteAgentStore tests/test_db_migration.py -v`
    - Then full suite inside docker: `docker compose exec the-one pytest --tb=no -q --timeout=300` (canonical baseline; outside-container runs hit L0 anomaly A1's env-driven failures).

## Edge Cases

- **`Annotated[T, Substitute] | None = None` placement (the broken form)**: a future schema addition that copies the wrong placement would silently regress — `field_info.metadata == []` and the resolver raises `ValueError: ... no Narrow/Substitute marker`. The L1 introspection tests at step 7 lock the placement so this regression fails LOUD at test time, not silently at agent-build time. NEVER use the broken form.
- **`json.dumps(config.mcp_overrides)` when value is `{}` (empty dict)**: empty dict serializes to `"{}"` — truthy-as-string, NOT NULL. This roundtrips cleanly because `_row_to_config` parses `"{}"` → `{}` (a real empty dict, NOT `None`). The locked-down NULL semantic only applies when `config.mcp_overrides is None`, NOT when it's `{}`. Operators who want "no overrides" set `None`; operators who want "empty overrides dict" set `{}`. This is the same semantic as `tool_overrides` (see lines 120-124's existing comment).
- **Pydantic v2 `extra="ignore"` (resolver line 260)**: unknown keys in the agent override silently drop. An operator who types `mcp_overrides={"github": {"bear_token": "..."}}` (typo: `bear_token` instead of `bearer_token`) gets a `bearer_token=None` model — NO error. Test `test_resolve_unknown_key_dropped_silently` locks this behavior; documents the silent-drop as expected. Strictness can be added later via `model_config = ConfigDict(extra="forbid")` per-schema if F8 UI demands it.
- **v11 migration on a freshly-created v8/v9/v10 DB**: the `if version < 11:` block runs ONLY when version is currently 10 or lower. Once version is 11, the block is skipped. Idempotent re-runs (calling `ensure_schema` twice) hit the PRAGMA-check `if "mcp_overrides" not in existing_cols:` guard and SKIP the ALTER, then the `INSERT OR IGNORE` no-ops the schema_version row.
- **Migration ordering during stacked PR review**: F6's PR (#TBD) targets the F5 branch, which targets the F4 branch, which targets `main`. `main` is at v10 today (verified via `the_one/db/schema.py:9` HEAD). F4 + F5 do NOT modify `CURRENT_VERSION`. F6 L1 is the FIRST migration in this stack — there's no "v11 collision risk" with another flight.
- **Ruff 100-char line limit (D1 from L0)**: docstrings and comment blocks in `the_one/mcp/_overrides.py` MUST stay under 100 chars per line. L0's deviation D1 wrapped a 102-char line; apply the same defensive 96-char practical-cap to L1's docstrings to leave breathing room for inline edits.
- **`AgentConfig.model_config = {"extra": "ignore"}` (line 38)**: the existing config already drops unknown fields. Adding `mcp_overrides` doesn't change this — agents serialized PRE-L1 don't have the field, agents deserialized POST-L1 just get the default `None`. No migration needed for in-memory `AgentConfig` instances.
- **Aiosqlite `Row[<missing>]` raises `IndexError`**: if v11 migration hasn't run for some reason and `_row_to_config` reads `row["mcp_overrides"]`, it raises `IndexError`. This is the existing safety contract per the comment at lines 120-123. No new defensive logic — the v11 migration is the gate, not the parse code.

## Files Affected

- `the_one/mcp/_overrides.py` (NEW) — ~90 LOC; two Pydantic schemas with `Substitute` markers.
- `the_one/agent/config.py` — `mcp_overrides` field added (~12 LOC including comment).
- `the_one/db/schema.py` — `CURRENT_VERSION` bumped 10→11 (1 LOC); v11 migration block added (~22 LOC).
- `the_one/db/repositories.py` — `SQLiteAgentStore.save` UPSERT extended (~6 LOC); `_row_to_config` parse extended (~3 LOC).
- `tests/test_mcp_overrides.py` (NEW) — ~110 LOC; ~10 tests covering schema introspection + resolver dispatch.
- `tests/test_db_repositories.py` — 2 new tests in `TestSQLiteAgentStore` (~25 LOC).
- `tests/test_db_migration.py` — `TestSchemaV11` class with 3 new tests (~115 LOC); 3 LOC `CURRENT_VERSION == 10 → == 11` mechanical bumps at `:226, :430, :558`; 3 LOC literal-10 max-version assertions rewritten to `CURRENT_VERSION` indirection at `:458, :494, :589` (per Architect cycle-1 low #3); add `from the_one.db.schema import CURRENT_VERSION` to imports if missing.
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry appended (~15 LOC).

Net delta: ~+135 LOC production + ~+250 LOC tests ≈ **~+385 LOC total**, slightly above the flight artifact's L1 estimate of "~110 LOC production + ~180 LOC tests" because the tests write (a) the v11 migration suite (~115 LOC) and (b) marker-introspection regression tests beyond the original spec. The ~290 LOC test estimate from the flight artifact accounts only for the resolver dispatch + one round-trip pair; the migration suite is additional.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (each grep / pytest / ruff command produces the expected result)
- [ ] Tests passing (`pytest --tb=no -q --timeout=300` green inside `docker compose`; targeted suite per Verification Steps green)
- [ ] Lint clean (`ruff check the_one/ tests/`)
- [ ] Update `flight-log.md` with leg progress entry (Started/Completed timestamps, Changes Made, Notes)
- [ ] Set this leg's status to `landed` (in this file's header) — Flight Director (NOT the implementer) will flip to `completed` at flight commit time per the agentic-workflow protocol
- [ ] Do NOT check off this leg in flight.md yet — that happens at flight commit
- [ ] Do NOT commit — defer to flight-end commit per agentic-workflow protocol
- [ ] Signal `[HANDOFF:review-needed]` once all checklist items above are done

---

## Citation Audit

15 citations verified against current code at leg design time. Two `drifted` repaired inline; rest `OK`:

| Citation | Classification | Evidence |
|----------|----------------|----------|
| `the_one/agent/config.py:65` — `tool_overrides: dict[str, dict[str, Any]] \| None = None` | OK | Read directly; matches |
| `the_one/agent/config.py:38` — `model_config = {"extra": "ignore"}` | OK | Read directly; matches |
| `the_one/db/schema.py:9` — `CURRENT_VERSION = 10` | OK | Read directly; matches |
| `the_one/db/schema.py:292-332` — v8 ALTER pattern (tool_overrides) | OK | Read directly; matches; `INSERT OR IGNORE` at 330; PRAGMA check at 325-327; comment block 320-324 explicit about omitting `DEFAULT NULL` |
| `the_one/db/schema.py:355-402` — v10 block (mcp_sources rebuild) | OK | Read directly; v10 ends at 402; v11 inserts immediately after |
| `the_one/db/repositories.py::SQLiteAgentStore.save` lines 56-94 | OK | Read directly; UPSERT at 60-77; bind tuple at 78-91 |
| `the_one/db/repositories.py::SQLiteAgentStore._row_to_config` lines 106-125 | OK | Read directly; tool_overrides parse at line 124 with comment 120-123 |
| `the_one/tools/resolver.py:195-260` — `resolve` body | OK | Read directly; locked-down NULL at 224-226; Substitute path at 256-257; final validate at 260 |
| `the_one/tools/resolver.py:53-60` — `Substitute` sentinel class | OK | Read directly; matches |
| `the_one/tools/resolver.py:236` — `m is Substitute` identity check | OK | Read directly; line 236 is `has_substitute = any(m is Substitute for m in markers)` |
| `tests/test_db_repositories.py::TestSQLiteAgentStore` lines 81-160 | OK | Read directly; class spans 81-160; `test_tool_overrides_round_trip` at 140-152; `test_tool_overrides_none_default` at 154-160 |
| `tests/test_db_migration.py::TestSchemaV8` lines 203-onwards | OK | Read directly; class begins at 203; `test_v8_fresh_db_includes_tool_configs_and_tool_overrides` at 206-269; `test_v8_migration_on_v7_fixture_db_preserves_existing_rows` at 271-328; `test_v8_migration_is_idempotent` at 330+ |
| ~~`tests/test_schema.py` (flight-artifact L1 reference)~~ | **drifted** | `tests/test_schema.py:1` docstring says "Tests for schema migrations (v1 -> v2 -> v3 -> v4 -> v5)"; v8+ tests live in `tests/test_db_migration.py` instead. **Repaired**: L1 implementation guidance points to `tests/test_db_migration.py`, NOT `tests/test_schema.py`. |
| ~~`tests/test_store.py` (flight-artifact L1 reference)~~ | **drifted** | `tests/test_store.py:1` docstring says "Tests for FilesystemConfigStore"; SQLiteAgentStore tests live in `tests/test_db_repositories.py::TestSQLiteAgentStore` instead. **Repaired**: L1 implementation guidance points to `tests/test_db_repositories.py`, NOT `tests/test_store.py`. |
| `tests/test_db_migration.py::TestSchemaV8::test_v8_fresh_db_includes_tool_configs_and_tool_overrides` line 226 — `assert CURRENT_VERSION == 10` | OK | Read directly; matches; L1 step 9 updates this to `== 11` (mechanical shift). |
