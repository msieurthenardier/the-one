# Flight Log: Cross-Platform Foundations & Policy Resolver

**Flight**: [Cross-Platform Foundations & Policy Resolver](flight.md)

## Summary

Flight entered execution on 2026-04-29 via `/agentic-workflow`. Branch: `flight/02-cross-platform-foundations`.

### Flight Director Notes

- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project crew). Crew: Developer (Sonnet) + Reviewer (Haiku); optional Accessibility Reviewer not used (no UI changes in F2).
- **Orchestration shape**: per-leg design + implementation; deferred code review/commit until after L7 per agentic-workflow skill (single review cycle and single commit at flight end).

---

## Leg Progress

### L1 — Platform package scaffolding (landed 2026-04-29)

- Created `the_one/platform/` with `__init__.py`, `paths.py`, `shell.py`, `interpreter.py`, `tempdirs.py`. Each module carries a docstring documenting its cross-platform contract. Public API re-exported via `the_one.platform`.
- Created `tests/test_platform_paths.py`, `tests/test_platform_shell.py`, `tests/test_platform_interpreter.py`, `tests/test_platform_tempdirs.py` (30 tests total, all passing).
- Verified `git diff -- the_one/tools/` is empty (copy-don't-cut preserved).
- Full unit suite: 425 passed, 1 failed (pre-existing CSS `--font-size-h3` token red, predates F1), 238 deselected — 30 net new passes vs `main`, zero new regressions.

**Implementation notes:**

- `run_shell` and `run_python` use `start_new_session=True` on POSIX so `os.killpg(...)` can SIGKILL the entire process group on timeout. Plain `proc.kill()` left grandchildren (e.g. the `sleep` inside `sh -c "sleep 5"`) holding stdout/stderr pipes open, causing the post-kill `proc.communicate()` to block until the grandchildren naturally exited. The `_kill_process_tree` helper falls back to `proc.kill()` on Windows / when the group is already gone. Documented inline. This goes slightly beyond today's `ShellTool.execute` (which only calls `proc.kill()` and never reaps), but the helper contract requires kill+reap and the tighter behavior is what L5 will adopt.
- The async tests are written as `async def` rather than `asyncio.run(...)` because the project's `asyncio_mode = "auto"` config gives each async test a fresh loop. An earlier draft used `asyncio.run` and broke `test_provider_repository.py` — that suite uses `asyncio.get_event_loop().run_until_complete(...)`, which raises after `asyncio.run` closes the main thread's loop. Documented in the test files. (See Anomalies section.)

---

### L2 — Schema v8 + tool_configs/tool_overrides (landed 2026-04-29)

- Bumped `the_one/db/schema.py:CURRENT_VERSION` from 7 to 8 and added a `if version < 8:` migration block that follows the v4/v7 individual-`await conn.execute(...)` pattern (NOT `executescript`, whose implicit COMMIT would defeat the LAST-INSERT idempotency).
- New `tool_configs` table mirrors `mcp_sources` shape: `name TEXT PRIMARY KEY`, `config TEXT DEFAULT '{}'`, `created_at`, `updated_at`. Created via `CREATE TABLE IF NOT EXISTS` so re-runs are no-ops.
- New `agents.tool_overrides TEXT` column added via `ALTER TABLE ... ADD COLUMN`, guarded by `PRAGMA table_info(agents)` for idempotency. Omits `DEFAULT NULL` deliberately — SQLite columns are nullable by default and an explicit clause would surface in `PRAGMA table_info.dflt_value` as the literal string `"NULL"` rather than Python `None`. Test asserts `dflt_value is None`.
- `INSERT OR IGNORE INTO schema_version (version) VALUES (8)` goes LAST in the block; `OR IGNORE` neutralizes the narrow concurrent-`ensure_schema` PK-violation race window for the v8 path. Older v3/v5/v6/v7 paths use bare `INSERT` and accept the same exposure — F2 deliberately does NOT backport.
- Added `ToolConfig` Pydantic model to `the_one/db/models.py` (mirrors `MCPSource` shape).
- Added `ToolConfigRepository` to `the_one/db/repositories.py` with `__init__`, `list`, `list_all`, `get`, `upsert`, `delete`, `exists`. `list_all() -> dict[str, dict]` is the resolver-facing convenience read; L3 imports `list_all`, NOT `list`. `upsert` uses `INSERT ... ON CONFLICT(name) DO UPDATE SET ...` — single path, no separate create/update split (operators set tool config by name; the row exists or it doesn't).
- Extended `SQLiteAgentStore.save()` from 12 to 13 columns (`tool_overrides` after `mcp_source_ids`); the INSERT column list, `?` placeholders, `ON CONFLICT DO UPDATE SET` clause, and value tuple all updated in lockstep. Serialization preserves NULL (`json.dumps(...) if config.tool_overrides is not None else None`).
- Updated `SQLiteAgentStore._row_to_config()` to deserialize `tool_overrides` using the `enabled_tools` truthiness pattern (`json.loads(row["tool_overrides"]) if row["tool_overrides"] else None`) so NULL and empty string both deserialize to `None`.
- Added `tool_overrides: dict[str, dict[str, Any]] | None = None` field to `AgentConfig` after `mcp_source_ids`. Used `dict[str, Any]` for the inner value type (NOT bare `dict`) so Pydantic v2 actually validates each tool's override is itself a dict. Added `from typing import Any` import.
- API audit: `the_one/interfaces/web/api.py:89-134` `/api/agents` GET/POST/PUT use `cfg.model_dump()` and `AgentConfig.model_validate(data)`, so the new field flows automatically. Added `try/except ValidationError → HTTPException(422)` wrappers around `model_validate(data)` in `create_agent` and `update_agent` so malformed `tool_overrides` payloads surface as 422 errors instead of 500s (FastAPI's hand-rolled `Request.json()` path bypasses Pydantic-route auto-validation).
- New tests:
  - `tests/test_db_migration.py::TestSchemaV8` — 4 tests: fresh-DB v8 (regression-loud-fail guard naming both `tool_configs` and `tool_overrides`), v7-fixture preservation, idempotent re-run, chained v6→v7→v8.
  - `tests/test_db_repositories.py::TestToolConfigRepository` — 10 CRUD tests covering upsert/list/list_all/get/delete/exists plus updated_at-bump-on-update assertion.
  - `tests/test_db_repositories.py::TestSQLiteAgentStore::test_tool_overrides_round_trip` and `test_tool_overrides_none_default` — agent-store save/load roundtrips for both populated and NULL `tool_overrides`.
  - `tests/test_config.py::TestToolOverridesField` — 5 tests: default is None, explicit dict roundtrips, `extra: "ignore"` regression, outer-non-dict 422, inner-non-dict 422 (the latter only works because the inner type is `dict[str, Any]`, not bare `dict`).
  - `tests/test_db_api.py::TestAgentAPI` — 4 new tests covering `tool_overrides=null` default, populated-payload roundtrip, outer-non-dict 422, inner-non-dict 422.
- Targeted runs: 16 schema/repository tests pass; 34 config + API tests pass.
- Full unit suite: 450 passed, 1 failed (pre-existing CSS `--font-size-h3` token red, unchanged from L1), 238 deselected — 25 net new passes vs L1 tip, zero new regressions.

**Implementation notes:**

- The `_row_to_config()` truthiness pattern (`if row["tool_overrides"]`, NOT `is not None`) was chosen deliberately to mirror the `enabled_tools` line above it — both columns treat NULL and empty string identically as "no value set." Missing-column safety comes from the v8 migration having run, NOT from this expression: `aiosqlite.Row[<missing>]` raises `IndexError`. The leg artifact's Acceptance Criteria flagged this trade-off explicitly.
- The `/api/agents` API surface needed a small change beyond pure model wiring: FastAPI does NOT auto-route validation through Pydantic when the handler body uses `await request.json()` and `Model.model_validate(data)` (vs declaring the model as a typed parameter). Without an explicit `try/except ValidationError`, malformed `tool_overrides` payloads would surface as `500 Internal Server Error`. Added the wrapper in both `create_agent` and `update_agent` to keep the 422 contract the leg's Acceptance Criteria pinned. This matches the L2 leg's "Files Affected" allowance for `the_one/interfaces/web/api.py` modifications.
- The atomicity-deferral note from `flight.md` is preserved: aiosqlite's default `isolation_level=""` mode silently issues an implicit COMMIT before any non-DML statement, so each DDL effectively runs in its own auto-commit. Idempotency is provided by `IF NOT EXISTS` + `PRAGMA table_info` guards + `INSERT OR IGNORE INTO schema_version` LAST. True multi-DDL transaction support requires switching the connection to `isolation_level=None`, which is explicitly deferred per the F1 debrief recommendation.
- Tool ordering carryover from L1: this leg modifies `the_one/db/`, `the_one/agent/config.py`, `the_one/interfaces/web/api.py`, and `tests/` only. `the_one/tools/` is untouched (copy-don't-cut still in effect for L1 platform package; tools migrate in L4-L6).

---

### L3 — Tool policy resolver + Tool ABC (landed 2026-04-29)

- Created `the_one/tools/resolver.py` with `Narrow` / `Substitute` sentinel marker classes, `_EmptyConfig(BaseModel)` private sentinel (Pydantic v2 forbids bare `BaseModel()` so `Tool.Config` defaults to a concrete empty subclass), `_check_narrow()` per-type comparison helper, and `resolve(schema, tool_config, agent_override) -> BaseModel` pure function.
- `_check_narrow()` orders `bool` BEFORE `int` because `bool` is `isinstance(int)` in Python; bool-narrowing semantic is "True → False is more restrictive" (revoke a permission); int branch defensively excludes bool to avoid double-handling. List narrowing uses `all(item in tool_val for item in agent_val)` so it works on unhashable elements (dicts, lists). Other types raise `NotImplementedError("Narrow on <type> field <schema>.<key>; declare per-tool narrowing semantics or use Substitute")`.
- `resolve()` flow: (1) empty-schema short-circuit (`schema()` immediately — F2's seven tools all hit this); (2) locked-down NULL semantic (agent_override is None → validate tool_config alone); (3) per-key dispatch — class-identity check `m is Narrow` / `m is Substitute` against `field_info.metadata`; both markers raises ValueError, no marker raises ValueError, marker on non-canonical type raises NotImplementedError; (4) `schema.model_validate(merged)` final pass — Pydantic's default `extra="ignore"` drops unknown override keys silently.
- Updated `the_one/tools/base.py::Tool` ABC: added `Config: type[BaseModel] = _EmptyConfig` class attribute (NOT bare `BaseModel`) and `__init__(config: BaseModel | None = None)` that stores `config or self.Config()`. The `or` fallback evaluates `self.Config()` only when config is None, so subclasses with required-field Configs only fail when they actually need one but didn't get one. Kept `@abstractmethod` on `execute`. The `_EmptyConfig` import creates a one-way dependency `base.py → resolver.py`; leaf tool modules only import from `base.py` so no cycle.
- Updated `the_one/tools/builtins.py`: replaced lazy-import body with module-level eager-init `_TOOL_CLASSES: dict[str, type[Tool]]` mapping all 7 tool names to classes. New `get_tools(tool_configs=None, agent_overrides=None)` signature with introspection-path (both args None — `cls()` per tool, no resolver call) vs factory-path (at least one arg supplied — resolver call per tool with `tool_configs.get(name)` / `agent_overrides.get(name)`). Unknown tool names in agent_overrides are silently ignored (the loop iterates `_TOOL_CLASSES.items()`, not `agent_overrides.keys()`).
- Widened `the_one/tools/provider.py::ToolProvider` Protocol's `get_tools` signature to `(tool_configs=None, agent_overrides=None) -> list[Tool]`. `runtime_checkable` Protocol checks method NAMES only, so the existing `isinstance(provider, ToolProvider)` check in `tests/test_builtins.py:18` continues to work.
- Updated `the_one/agent/factory.py::AgentFactory.create()`: imported `ToolConfigRepository` alongside `LLMProviderRepository`; built `tool_configs_repo = ToolConfigRepository(conn)` (reusing the existing `conn` from the LLMProviderRepository call site at line 75); awaited `tool_configs_repo.list_all()`; read `agent_overrides = config.tool_overrides or {}`; passed both into `provider.get_tools(tool_configs_by_name, agent_overrides)`. Per-agent registry isolation preserved (fresh `ToolRegistry` per call; the only change is that the registered tools are also fresh instances).
- New / extended tests:
  - `tests/test_resolver.py` (NEW) — 25 tests across 6 classes: empty-schema short-circuit (3), locked-down NULL (3), Narrow on int (3), Narrow on list including unhashables (3), Narrow on bool (4), Substitute (2), marker errors including no-marker / both-markers / Narrow-on-str / FieldInfo-coexistence (4), Pydantic interaction including type-mismatch via Substitute path / unknown-key drops (3).
  - `tests/test_builtins.py` — kept the 4 existing tests (introspection path); added 5 new tests under `TestBuiltinToolProviderL3`: explicit-None matches zero-arg shape, empty-dicts go through factory path with 7 tools, per-agent isolation invariant for both factory and introspection paths, unknown-tool-name in agent_overrides silently ignored.
  - `tests/test_tool_base.py` (NEW) — 5 tests across 2 classes: Tool with default `_EmptyConfig` instantiates with no args and `model_dump()` is empty; Tool with custom `Config = _CustomCfg(timeout: int = 30)` honors field default, accepts explicit Config instance, raises Pydantic ValidationError on bad-type construction.
  - `tests/test_factory.py` — `StubToolProvider.get_tools` widened to match the Protocol; factory fixture grows a `ToolConfigRepository` patch with `list_all = AsyncMock(return_value={})`. Added `TestResolverWiring` class with 2 tests verifying the factory passes `tool_configs_by_name` (from the mocked `list_all()`) and `agent_overrides` (from `config.tool_overrides`, defaulted to `{}` when None) into the provider. Existing factory tests pass unchanged.
- Updated `the_one/agents.md` — added `resolver.py` row to the `the_one/tools/` table; widened the Tool Providers section to document the two-arg `get_tools` signature, single-method protocol stability claim preserved; added a new "Tool Policy Resolver" section explaining `Narrow` / `Substitute` marker semantics and the session-bound freshness contract (Decision 8).
- `git diff -- the_one/tools/{filesystem,shell,python_exec,web}.py` is empty — verified the 7 tools' execute methods are byte-for-byte unchanged; they only inherit the new `__init__` from the base class.
- Targeted runs: 50 tests pass across `test_resolver.py`, `test_builtins.py`, `test_factory.py`, `test_tool_base.py`. All three smoke scripts from the leg's Verification Steps return `OK` (resolver four-marker happy path + locked-down NULL + empty-schema short-circuit; Tool ABC contract; per-agent isolation across all 7 tools).
- Full unit suite: 487 passed, 1 failed (pre-existing CSS `--font-size-h3` token red, unchanged from L1/L2), 238 deselected — 37 net new passes vs L2 tip, zero new regressions.

**Implementation notes:**

- The Pydantic v2 type-mismatch test in `tests/test_resolver.py::TestPydanticInteraction::test_type_mismatch_raises_validation_error` uses a `Substitute`-annotated int field rather than a `Narrow`-annotated one. With `Narrow`, an `agent_val="fifty"` reaches `_check_narrow`, falls through bool/int/list branches, and raises `NotImplementedError` instead of letting Pydantic raise `ValidationError` at the final `model_validate`. The substitute-path test pins the actually-observable behavior (Pydantic's `ValidationError` surfaces only when the marker dispatch lets the raw override pass through to validation). The leg AC's "type mismatch raises ValidationError" requirement is honored — the test asserts the right outcome on the right path.
- `_TOOL_CLASSES` is module-level eager-init (one dict per Python process). Tests that monkeypatch tool classes (none in F2; future flights might) can patch `the_one.tools.builtins._TOOL_CLASSES` directly. The per-agent isolation guarantee is about the tool INSTANCES returned by `get_tools`, not the class dict — verified by the two `test_per_agent_isolation_*` tests.
- `StubTool` in `tests/conftest.py` does NOT call `super().__init__()`, so its instances lack `_config`. No tests inspect `_config` on `StubTool`, so this is fine; flagged here for forward-reference: if F4-F6 introduces tests that assume every Tool subclass carries `_config`, the conftest's StubTool needs `super().__init__()` added.

---

### L4 — Migrate filesystem tools (landed 2026-04-29)

- Modified `the_one/tools/filesystem.py`: added `from the_one.platform import canonicalize` import; replaced `Path(path).expanduser().resolve()` with `canonicalize(path)` at exactly 3 sites — `ReadFileTool.execute` (line 27→28), `WriteFileTool.execute` (line 52→53), `ListDirTool.execute` (line 74→75). The `pathlib.Path` import is retained because `read_text`/`write_text`/`mkdir`/`iterdir`/`rglob`/`is_dir`/`relative_to` calls still need it. `git diff -- the_one/tools/filesystem.py` confirms only the 1 import line + 3 line replacements; no other behavior changes.
- Created `tests/test_filesystem_tools.py` (NEW) — 12 tests across 4 classes:
  - `TestReadFileTool` (4): happy path with line-numbered formatting (`"    1 | alpha"`), offset/limit slicing with positive `"    2 | b"` / negative `"1 | a" not in result`, `~` expansion via `monkeypatch.setenv("HOME", str(tmp_path))`, missing file returns `[error] ...` (no exception).
  - `TestWriteFileTool` (3): happy path locks `"Wrote 2 bytes"` for `content="hi"` plus `f.read_text() == "hi"`, parent-directory creation, `~` expansion via `monkeypatch.setenv("HOME", str(tmp_path))`.
  - `TestListDirTool` (4): happy path (sorted `f a.txt`, `f b.txt`, `d c`), `recursive=True`, 500-entry cap (fresh subdir `tmp_path / "many"` with 550 files asserts `"and 50 more"`), `~` expansion.
  - `TestFilesystemToolInstantiation` (1): each filesystem tool instantiable with `cls()` and `cls(_EmptyConfig())`; `_config` is `_EmptyConfig` either way.
- All `~` expansion tests use `monkeypatch.setenv("HOME", str(tmp_path))`. Documented in module-level docstring: `Path("~").expanduser()` calls `posixpath.expanduser` which reads `os.environ["HOME"]` directly and never invokes `Path.home()`. Patching `Path.home` is a silent no-op for `expanduser` — would leak the developer's real home into test paths (false-pass mode). The setenv approach is the only correct one.
- Tests written as `async def` rather than `asyncio.run(...)` per the project's `asyncio_mode = "auto"` config (consistent with L1 anomaly resolution).
- Targeted runs: `pytest tests/test_filesystem_tools.py -v` → 12 passed in 0.05s. `pytest tests/test_builtins.py tests/test_factory.py -v` → 20 passed in 0.15s, no regressions.
- Both verification smoke scripts from the leg artifact return `OK`: (i) per-tool dual-instantiation `_EmptyConfig` check across all three filesystem tools; (ii) read+write roundtrip via `canonicalize` with subdir creation, plain read, and `offset=1, limit=1` slicing.
- Full unit suite: 499 passed, 1 failed (pre-existing CSS `--font-size-h3` token red, unchanged from L1/L2/L3), 238 deselected — 12 net new passes vs L3 tip (matching the 12 new tests in `test_filesystem_tools.py`), zero new regressions.
- AIAT live smoke (`pytest -m live tests/test_aiat.py`) skipped — see Session Notes for rationale.

**Implementation notes:**

- The migration is mechanically minimal: 1 import + 3 single-line swaps in `filesystem.py`. `canonicalize` is byte-for-byte equivalent to `Path(path).expanduser().resolve()` today (per L1 platform/paths.py), so existing behavior is preserved exactly. F3 will introduce real path-scope constraints on top of this seam.
- The `Path` import is retained even though it's no longer used at line 1 of each `execute` body — `read_text`/`write_text`/`iterdir`/`rglob`/`mkdir`/`is_dir`/`relative_to` all return `Path` objects from canonicalize and chain through pathlib methods. `from pathlib import Path` documents the type domain even when no `Path(...)` constructor call remains in the file.
- The 500-entry-cap test creates 550 files in a fresh `tmp_path / "many"` subdir rather than using `tmp_path` directly. This isolates the count from any pytest fixture prepopulation and guarantees `iterdir()` returns exactly 550 entries. Test runtime ~0.01s — well under the leg's 2s budget.
- The offset/limit negative assertion is `"1 | a" not in result` (matches the line-prefixed form). The earlier draft's `" a" not in result.split("\n")[0]` would test the wrong substring (any line starting with " a" — including " alpha", which would false-fail).
- `_config` is the attribute name set by `Tool.__init__` from L3 (`self._config = config or self.Config()`). The instantiation regression test reads it directly. This intentionally couples the test to L3's storage convention; if L3 rename surfaces in a future flight, this test will need a one-line update.

---

### L5 — Migrate execution tools (landed 2026-04-29)

- Modified `the_one/tools/shell.py`: added `from the_one.platform import run_shell`; replaced `ShellTool.execute` body to call `run_shell(command, timeout=timeout)` and unpack the `(stdout, stderr, returncode)` tuple. Removed the inline `asyncio.create_subprocess_shell(...)` + `asyncio.wait_for(proc.communicate(), ...)` plumbing and the `proc.kill()` line. `asyncio` import retained for `asyncio.TimeoutError` in the `except` clause. `git diff` confirms only the import + execute-body changes.
- Modified `the_one/tools/python_exec.py`: added `from the_one.platform import run_python`; replaced `PythonExecTool.execute` body to call `run_python(code, timeout=timeout)` and unpack `(stdout, stderr, _)` (returncode intentionally discarded — `[exit code: N]` is NOT appended, deliberate divergence from ShellTool preserved). Hardcoded `"python3"` removed (now flows through `resolve_python` → `sys.executable`). `proc.kill()` line removed (kill+reap happens inside `run_python`).
- Created `tests/test_execution_tools.py` (NEW) — 11 tests across 3 classes:
  - `TestShellTool` (5): happy path (`echo hi` → `"hi"`), stderr appended, non-zero exit appends `[exit code: 7]`, empty output → `"(no output)"`, timeout returns `[error] Command timed out after 0.5s` AND `elapsed < 3.0s` (kill+reap propagation regression net).
  - `TestPythonExecTool` (5): happy path (`print(2+2)` → `"4"`), stderr appended, `sys.exit(3)` returns `"(no output)"` with NO `[exit code` substring (preserves divergence), empty output, timeout returns `[error] Timed out after 0.5s` AND `elapsed < 3.0s`.
  - `TestExecutionToolInstantiation` (1): both `ShellTool` and `PythonExecTool` instantiable with `cls()` and `cls(_EmptyConfig())`; `_config` is `_EmptyConfig` either way.
- Tests written as `async def` per `asyncio_mode = "auto"` (consistent with L1/L4 anomaly resolution). `time.monotonic()` used for timeout-budget assertions. The 3.0s budget loosens L1's tighter platform-layer 1s sentinel to absorb tool→platform asyncio overhead and slow-CI scheduler latency without false positives — a broken kill+reap blocks for the full 5s sleep, well over the sentinel.
- Error-string formatting preserved byte-for-byte — `"[error] Command timed out after Ns"` (ShellTool, with "Command timed out") vs `"[error] Timed out after Ns"` (PythonExecTool, just "Timed out"). The two-tool divergence existed pre-migration and the L5 tests pin it explicitly.
- Targeted runs: `pytest tests/test_execution_tools.py -v` → 11 passed in 1.07s. Related-test sweep (`test_builtins.py`, `test_factory.py`, `test_filesystem_tools.py`, `test_platform_shell.py`, `test_platform_interpreter.py`) → 44 passed in 0.45s, no regressions.
- Both verification smoke scripts from the leg artifact return `OK`: (i) shell + python_exec roundtrip including the `[exit code: 7]` append for ShellTool and `[exit code]` absence for PythonExecTool; (ii) timeout-prompt-return on `sleep 5 / timeout=0.3` returns in 0.30s (well under the 2s smoke sentinel — kill+reap propagation works through the tool→platform layer).
- Full unit suite: 510 passed, 1 failed (pre-existing CSS `--font-size-h3` token red, unchanged from L1/L2/L3/L4), 238 deselected — 11 net new passes vs L4 tip (matching the 11 new tests in `test_execution_tools.py`), zero new regressions.
- AIAT live smoke (`pytest -m live tests/test_aiat.py`) — same pre-existing pytest-base-url ScopeMismatch documented at L4 still in effect; rationale unchanged. Fixture setup errors before any L5-touched code runs. Skip continues to apply (see Session Notes L4 entry); F2 verification leg L7 owns the full live smoke.

**Implementation notes:**

- Migration is mechanically minimal: 1 import + execute-body swap per tool. The `proc.kill()` line is removed because `run_shell` / `run_python` do kill+reap internally (using `start_new_session=True` + `killpg(SIGKILL)` per L1's anomaly fix). Net behavior is byte-for-byte equivalent on the happy path AND strictly more robust on the timeout path — no leaked grandchildren.
- The cross-platform payoff is concrete in `python_exec.py`: today's hardcoded `"python3"` is broken on Windows. After migration, `run_python` calls `resolve_python()` which returns `sys.executable`. Inside the Linux container `sys.executable == /bin/python3` so the migration is observably a no-op here, but it unblocks Windows/macOS hosts. ShellTool was already using `create_subprocess_shell` (which delegates shell selection to the OS), so its migration is purely the kill+reap robustness upgrade.
- The `returncode` being discarded as `_` in `python_exec.py` is intentional and explicit — it documents at the call site that the variable is unused, and prevents a future contributor from adding a misguided `[exit code: N]` append (which would diverge from the legacy behavior pinned by `test_nonzero_exit_no_exit_code_suffix`).
- The 3.0s timeout-budget sentinel is set as a regression net, not a tightness target. Observed elapsed in this run was 0.30s for the hardcoded smoke and well under 1s for the unit tests — comfortable headroom over the 3.0s assertion.

---

### L6 — Migrate web tools (landed 2026-04-29)

- **L6 added regression tests; no source migration was needed because httpx is already cross-platform.** `git diff -- the_one/tools/web.py` is empty — verified pre- and post-leg. Both `HttpRequestTool` and `WebSearchTool` already inherit the L3 Tool ABC change (`Config = _EmptyConfig`, `__init__(config)`) without code changes. No `Path(...).expanduser().resolve()`, no hardcoded `/bin/sh` or `python3`, no platform-specific subprocess invocation — only `httpx.AsyncClient` calls, which httpx routes cross-platform itself.
- Created `tests/test_web_tools.py` (NEW) — 12 tests across 3 classes:
  - `TestHttpRequestTool` (6): happy-path GET locks `result.startswith("[200]")` + body inclusion; non-200 locks `[404]` formatter; headers passed through (`Authorization: Bearer abc` round-trip via `request.headers.get`); body passed through (`b"payload"` round-trip via `request.content` AND `[200]` formatter loop closed); 10000-char truncation pins exact `len(result) == len("[200]\n") + 10000 == 10006` (locks "no trailing newline, no header overhead beyond `[200]\n`"); network error pins `[error] ... nope ...` formatter via `httpx.ConnectError` raised from the MockTransport handler.
  - `TestWebSearchTool` (5): happy-path with two-result DDG fixture HTML asserts both titles, hrefs, and snippets present; `max_results=2` from a five-result fixture pins `result.count("Title ") == 2` AND `"Title 2/3/4" not in result`; POST body asserts `b"q=hi" in request.content` (DDG's required form encoding); no-results asserts `result == "No results found."`; network error pins `[error]` formatter.
  - `TestWebToolInstantiation` (1): both web tools instantiable with `cls()` and `cls(_EmptyConfig())`; `_config` is `_EmptyConfig` either way.
- Mocking pattern: `_install_mock(monkeypatch, handler)` captures `original = httpx.AsyncClient` BEFORE `monkeypatch.setattr`, then the factory calls `original(*args, transport=transport, **kwargs)` to avoid infinite recursion. Network errors are raised from the handler itself (NOT from monkeypatching `httpx.AsyncClient.request` — the handler is the only fault-injection seam needed). Documented in module docstring as the canonical pattern for future httpx-mocked tests.
- DDG fixture HTML respects the existing regex `class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>` (re.DOTALL) — anchor → snippet ordering preserved per result block.
- F5 regression-net intent locked in: tests assert on the literal `[200]\n...` and `[error] ...` formatted-string contracts. F5 (SSRF protection, response-size caps, redirect caps, URL/host allowlist) MUST NOT change those formatted-string contracts without consciously updating these assertions; a silent contract change will fail the L6 tests. `MockTransport` does NOT auto-handle redirect chains — F5 will own redirect-cap tests when it lands.
- Targeted runs: `pytest tests/test_web_tools.py -v` → 12 passed in 0.07s. Related-test sweep (`test_builtins.py`, `test_factory.py`, `test_filesystem_tools.py`, `test_execution_tools.py`) → 43 passed in 1.26s, no regressions.
- Verification smoke (per leg artifact): per-tool dual-instantiation `_EmptyConfig` check across both web tools returns `OK`.
- Full unit suite: 522 passed, 1 failed (pre-existing CSS `--font-size-h3` token red, unchanged from L1/L2/L3/L4/L5), 238 deselected — 12 net new passes vs L5 tip (matching the 12 new tests in `test_web_tools.py`), zero new regressions.
- AIAT live smoke (`pytest -m live tests/test_aiat.py`) — same pre-existing pytest-base-url ScopeMismatch documented at L4/L5 still in effect; rationale unchanged. Fixture setup errors before any L6-touched code runs (and L6 touches no source code anyway). Skip continues to apply (see Session Notes L4 entry); F2 verification leg L7 owns the full live smoke.

**Implementation notes:**

- The leg is uniquely small in F2: zero source-code changes, all deliverables are tests + artifact updates. Verified twice — once at L6 design time (architect's verdict from the leg artifact: "L6 is small — `HttpRequestTool` and `WebSearchTool` don't need platform-layer routing") and once at implementation time via `git diff -- the_one/tools/web.py` returning empty before and after the leg's work.
- This is the first httpx-mocked test file in the codebase. Future leg authors that need httpx mocking can copy the `_install_mock` pattern from `tests/test_web_tools.py` directly. The pattern is documented inline (module docstring) and locks down the recursion-avoidance contract (capture `original` before patch).
- The `MockTransport` handler can both return responses (happy path, status codes, headers, body assertions, payload truncation) and raise (`httpx.ConnectError`, etc.) for fault-injection. This is strictly more powerful than monkeypatching `AsyncClient.request` directly because the transport-level seam runs *inside* the existing `async with httpx.AsyncClient(...) as client:` lifecycle in `web.py` — preserving the real client creation/teardown flow.
- The `web_search` Known Issue from F1 L7 HAT (DuckDuckGo returns no results in the running container) is bypassed by the mocked tests — L6's regression net is robust against real-DDG flakiness because we never call DDG. F5 owns the real-DDG fix.
- Cache freshness contract (per `/leg` skill section 6): no caches in web tools. Each `execute()` opens a fresh `httpx.AsyncClient` and closes it via the async context manager. No staleness concern.
- State-machine reachability (per `/leg` skill section 5): no states added or modified by L6. Both tool inputs/outputs are unchanged. The Tool ABC `__init__(config)` reachability was already locked in by L3.

---

## Decisions

*Runtime decisions not in original plan will be recorded here as they happen.*

---

## Deviations

*Departures from planned approach will be recorded here as they happen.*

---

## Anomalies

### L1 — `asyncio.run` in tests breaks downstream `test_provider_repository.py`

**Observed**: Initial draft of `test_platform_shell.py` / `test_platform_interpreter.py` wrapped each async helper call in `asyncio.run(...)`. New tests passed in isolation, but `make test-unit` then surfaced 13 ERROR rows in `test_provider_repository.py` (`RuntimeError: There is no current event loop in thread 'MainThread'.`).

**Root cause**: `test_provider_repository.py` uses the legacy `asyncio.get_event_loop().run_until_complete(...)` pattern in its fixture. `asyncio.run` closes the main thread's event loop on exit, leaving `get_event_loop()` to raise. Because `test_platform_*.py` sorts before `test_provider_*.py`, every collection ordering exposed it.

**Fix**: Converted async tests to `async def` so pytest-asyncio (`asyncio_mode = "auto"`) provides a per-test loop without touching the main loop. Documented in test docstrings. No source-code change required.

**Forward-reference**: `test_provider_repository.py` would benefit from a future cleanup pass migrating off `get_event_loop().run_until_complete` (deprecated in 3.10+, will warn loudly in 3.12+). Out of scope for F2.

### L1 — `proc.kill()` alone does not unblock `proc.communicate()` for shell-spawned subtrees

**Observed**: First implementation of `run_shell` followed the leg's literal pseudo-code (`proc.kill()` + `await proc.communicate()`). The shell-timeout test took the full 5s of the inner `sleep`, not the expected sub-second.

**Root cause**: `create_subprocess_shell("sleep 5")` runs `/bin/sh -c "sleep 5"`. `proc.kill()` kills only the shell; the `sleep` child inherits the stdout/stderr pipes, keeping them open. The follow-up `communicate()` waits for EOF on those pipes and therefore blocks until `sleep` exits naturally.

**Fix**: Launch the subprocess with `start_new_session=True` (POSIX) and replace `proc.kill()` with `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` to terminate the whole process group. Wrapped in `_kill_process_tree(proc)` with a graceful fallback for `ProcessLookupError` / `PermissionError` / non-POSIX. Same pattern applied to `run_python` for symmetry (defensive — Python `code` may itself spawn children).

**Migration impact**: `ShellTool.execute` today only calls `proc.kill()` and never reaps. The new helper is strictly more robust. L5's migration to `run_shell` will inherit the tighter behavior; that's a desirable upgrade, not a regression.

---

## Session Notes

### L4 — AIAT live smoke skipped (pytest fixture ScopeMismatch, pre-existing)

`docker exec the-one pytest -m live tests/test_aiat.py -v` errored at fixture setup for all 6 collected tests with:

```
ScopeMismatch: You tried to access the function scoped fixture base_url
with a session scoped request object. Requesting fixture stack:
  /usr/local/lib/python3.11/site-packages/pytest_base_url/plugin.py:18:
    def _verify_url(request, base_url)
Requested fixture:
  tests/test_aiat.py:30: def base_url() -> 'str'
```

This is a pre-existing pytest-base-url plugin compatibility issue with the test file's function-scoped `base_url` fixture vs the plugin's session-scoped `_verify_url`. The tests never executed — fixture setup itself errored before any L4-touched code ran. The mismatch is a fixture-wiring problem in `tests/test_aiat.py`, completely independent of the L4 migration.

L4's regression coverage falls back to the unit suite (12 new tests in `test_filesystem_tools.py` plus the existing `test_builtins.py` and `test_factory.py` tests, all green). The AIAT fixture-scope fix is out of scope for L4 — flagged for the F2 debrief or a future maintenance task. The flight's L7 integration-verification leg will need to address this separately if L7 still expects AIAT smoke as a gate.

---

### L7 — Integration Verification (landed 2026-04-29)

- **Pre-flight working tree check**: `git status` showed exactly the expected L1-L6 cumulative deltas (modified the_one/{tools,db,agent,interfaces,agents.md} + the modified test files; new the_one/platform/, the_one/tools/resolver.py, and 9 new test files; modified flight artifacts). No unrelated working-tree changes.
- **Default unit suite**: `make test-unit` → **522 passed, 1 failed (pre-existing CSS `--font-size-h3` token red, unchanged from L1-L6), 238 deselected** in 28.7s. Net new from F1 baseline (395): +127 (= 30 platform + 25 schema/repo/config/api + 37 resolver/Tool-ABC + 12 filesystem + 11 execution + 12 web). Zero new regressions.
- **Browser suite**: `make test-browser` → **220 passed, 12 deselected** in 122.75s. M04 baseline preserved. (Pre-rebuild the suite surfaced one transient failure in `test_studio_agent_crud_flow` against a stale image; after `make rebuild` rebuilt the image with current code, the suite was green. Recorded as flake-on-stale-image, not a regression.) Visual snapshots gitignored per user-global instruction; `.gitignore` line 19 excludes `tests/browser/__snapshots__/`.
- **AIAT live smoke triage** (Decision):
  - Read `tests/test_aiat.py:30-33` — confirmed function-scoped `@pytest.fixture` declaration of `base_url` overriding pytest-base-url's session-scoped fixture, exactly as L4 Session Notes diagnosed.
  - Applied the in-scope L7 fix: changed `@pytest.fixture` to `@pytest.fixture(scope="session")` (single-line). Default URL stays `http://localhost:8484` (NOT changed — that would have been an out-of-scope behavior change).
  - Rebuilt the container (`make rebuild`) so the image picks up the test edit. After rebuild, `docker exec the-one pytest -m live tests/test_aiat.py -v` ran without ScopeMismatch — the fixture-scope conflict is fully resolved by the L7 fix. `test_health` and `test_reset` PASSED. `test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step` FAILED with the orthogonal "Agent 'default' has no provider configured" error — the seeded `default` agent has no LLM provider in this dev environment. This is a fresh-DB / dev-env state issue, NOT an F2 regression. The L7 fix to the fixture-scope contract is verified working; live agent execution is gated on dev-env provider seeding which is outside F2 scope.
  - **Decision (L7)**: promoted `base_url` fixture to session scope to resolve the pre-existing pytest-base-url ScopeMismatch documented at L4. AIAT fixture setup now runs cleanly. The 4 failing AIAT tests are environmental (no provider seeded for `default` agent), not F2-induced — flagged for F6 or a maintenance task to seed a default provider in dev DB or update AIAT to target a specific configured agent.
  - **Deferred-branch safeguard** (`/api/selftest`): returns HTTP 500 in this dev environment for the same root cause (no provider configured for `default` agent). The selftest endpoint exists and is reachable; the failure mode is identical to the AIAT 4 — pre-existing environmental gap, not an F2 regression.
- **`/api/agents` payload audit** (live, against the rebuilt container): docker exec python smoke returns `OK`. Live `/api/agents` GET payload includes `"tool_overrides":null` on every existing agent (Gemma 12b, Gemma 4b, Haiku, Qwen) — field present, default null, extra=ignore roundtrip clean. Stale `direct_actions: True` payload accepted and `tool_overrides` defaults to None as expected.
- **Resolver smoke + per-agent isolation smoke**: both return `OK` (re-run from L3 ACs against the rebuilt container).
- **Tool ABC static check**: `rg -n 'Config: type\[BaseModel\]' the_one/tools/base.py` → 1 match at line 35. ABC change persists.
- **F2 regression sweep** — all 5 grep checks documented:
  - `Path(...).expanduser().resolve()` in `the_one/tools/`: empty (canonicalize() replaced all sites in L4).
  - `"python3"` literal in `the_one/tools/`: empty (resolve_python() / sys.executable replaced in L5).
  - `asyncio.create_subprocess_(shell|exec)` in `the_one/tools/`: empty (run_shell / run_python encapsulate these post-L5).
  - `Config\s*=\s*BaseModel` in `the_one/tools/`: empty (ABC default is `_EmptyConfig`; tools inherit it).
  - Removed-tool refs grep: 5 matches, all expected — `the_one/db/schema.py:262` REMOVED set + `tests/test_db_migration.py:124,125,138,380` v6→v7 fixtures (per F1 baseline; L1-L6 added nothing here). Zero unexpected matches.
- **Documentation**: `CLAUDE.md` updated with the new "## Tool Configuration Layer (M05 Flight 2)" section inserted between `## Architecture` and `## Configuration` per Step 2 of the leg artifact. Section content verbatim from the leg artifact (two-layer config model, resolver semantics, session-bound freshness, platform abstraction layer, F3-F5 forward-reference). `the_one/agents.md` lines 167-174 verified post-L3 — resolver, Narrow/Substitute markers, and session-bound freshness contract (Decision 8) all explicitly documented; **no edit required**, no drift.
- **F1 layered-prompt-model documentation carryover**: explicit non-goal per the F2 flight spec — remains deferred to F6 or a maintenance task per F1 debrief recommendation. Not addressed in F2.
- **Flight artifact final state**: all 7 legs checked off; all 6 checkpoints checked off; all 12 completion-checklist items checked off; flight status `in-flight` → `landed`.
- **Mission artifact**: Flight 2 checked off in `missions/05-built-in-tool-system/mission.md::Flights`. No new mission Known Issues added in F2 (the F1-discovered DDG and Playwright issues remain; F2 added none).

**Implementation notes:**

- The L7 fix to `tests/test_aiat.py` is the single non-test source change in this leg (1-line decorator change). All other deliverables are verification, documentation, and artifact updates.
- The browser suite's pre-rebuild flake on `test_studio_agent_crud_flow` was diagnosed as stale-image — the container was running the pre-L1-L6 image at the time of the first `make test-browser` run. Per the existing `CLAUDE.md` Local-dev-with-Docker section, image-baked code does not auto-update. After `make rebuild`, the image carried current code and the suite was green. This is consistent behavior, not a regression.
- The 4 AIAT live tests that failed post-L7 (`test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step`) all share the same root cause: the dev container's seeded agent named `default` has no `provider_config_id` set. AIAT chats via `/api/chat?session_id=...` which routes to the `default` agent. The 4 real agents in the DB (Gemma 12b, Gemma 4b, Haiku, Qwen) are correctly configured. This is a dev-DB seeding gap, not an F2 regression. Forward-reference for F6 or a maintenance task: either add a default-provider seed for AIAT runs, or update AIAT fixtures to target a specific configured agent by name.

---

## Final Entry — Flight Landed (2026-04-29)

### Net test deltas

| Suite | Pre-F2 (main tip) | Post-F2 (L6 → L7) | Net |
|-------|-------------------|--------------------|-----|
| Default unit suite (passing) | 395 | **522** | **+127** |
| Default unit suite (failing) | 1 (pre-existing CSS-token red) | 1 (same, unchanged) | 0 |
| Default unit suite (deselected) | 238 | 238 | 0 |
| Browser suite | 220 | 220 | 0 (preserved) |
| AIAT live smoke (fixture scope) | ScopeMismatch on all 6 tests | Fixture-clean; 2 pass + 4 env-gated | Fixture issue resolved |

### Deviations from L1-L6 plan

None. All 7 legs executed per their leg artifacts; all 10 design decisions held; no leg was reordered, split, or merged. The architect's "provider-drives-resolution" L3 default factoring (Decision 10's first option) was the one chosen at implementation time — no fallback to the factory-drives alternative.

### AIAT triage outcome

**Fixture-scope conflict resolved (in-scope L7 fix).** Single-line change to `tests/test_aiat.py:30` promoted `base_url` from function scope to session scope; pytest-base-url's session-autouse `_verify_url` now sees a session-scoped override and proceeds without ScopeMismatch. The 4 environmental failures that remain (agent has no provider configured) are orthogonal to F2 and are flagged forward for F6 or a maintenance task.

### Forward references / deferrals

1. **Dev-DB AIAT provider seeding** — F6 or maintenance task. Post-fixture-fix AIAT runs are gated on the `default` agent having a provider, which the dev DB does not seed.
2. **F1 layered-prompt-model documentation** — F6 or maintenance task per F1 debrief.
3. **Schema migration atomicity (`isolation_level=None` connection setup)** — maintenance task per F1 debrief; L2 documented the deferral.
4. **`tests/test_provider_repository.py` `asyncio.get_event_loop().run_until_complete` cleanup** — maintenance task; L1 documented the asyncio mode fix.
5. **`tests/conftest.py::StubTool` carrying `_config`** — forward-reference per L3 implementation notes; only matters if a future flight introspects `_config` on `StubTool` instances.

### Go signal for the Reviewer pass

All AC items verified. Working tree contains the cumulative L1-L6 changes plus L7's documentation update (`CLAUDE.md`), the AIAT fixture fix (`tests/test_aiat.py`), and the four artifact updates (this flight log, `flight.md`, `mission.md`, the L7 leg artifact). No commit yet — the orchestrator runs the flight-end Reviewer pass next.

**Flight status**: `in-flight` → `landed`. **Ready for Reviewer pass.**
