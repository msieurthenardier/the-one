# Flight Log: Per-agent MCP attach + tool-routing in agent loop

**Flight**: [Per-agent MCP attach + tool-routing in agent loop](flight.md)

## Summary

**Status**: landed (2026-05-08).

Orchestration started 2026-05-08 via `/agentic-workflow`. Branch `flight/06-mcp-attach-and-tool-routing` created from F5 branch tip (F4 + F5 stacked, both unmerged at PRs #31 + #32).

5 of 5 required legs landed (L0+L1+L2+L3+L5; L4 folded into L2; L6 out of scope per L5's disposition). Reviewer confirmed `[HANDOFF:confirmed]` over the full L0-L5 delta with no blocking or non-blocking issues. Targeted leg gates green throughout (~219 tests at L3 close + 7 HAT tests collected/skipped on host at L5).

**Net delta**: 17 modified files + 5 new files (~+648 / -144 LOC).

**Deferred to docker run at flight-end (NOT in this commit)**:
1. **Tier-1 HAT execution** — `tests/test_mcp_attach_hat.py` 7 tests skip outside docker via module-level `pytestmark.skipif`; the binary PASS gate runs as `docker compose exec the-one pytest tests/test_mcp_attach_hat.py -v`.
2. **F2-known-issue retirement** — `mission.md:104` line edit gated on Tier-1 HAT caplog assertion PASS (`assert not any("MCPClient transport close failed" in r.message ...)`). On PASS: edit mission.md line 104, mark F2-known-issue retired. On FAIL: file follow-up flight per `tests/HAT.md` "On FAIL" section (revert F5 L1's `_open_*_transport_stack` helpers + dispatcher rewrite + README §3 scoping update).
3. **`tests/test_mcp_pool.py::test_acquire_with_source_override`** — env-dependent (per A1/A2/A3); verifies via the same docker run.

**Carry-forward debts retired in this flight**:
1. ✓ Circular import chain `mcp.oauth.__init__ → storage → db.repositories → agent` broken (L0 — `MCPAuthRequired` canonical at `mcp/errors.py`).
2. ✓ `_pool_default` ContextVar fallback retired; multi-tab cross-routing bug fixed (L3 — `current_chat_session_id` canonical at `agent/_context.py` + per-tool-dispatch `current_tool_call_id`).
3. ✓ F2-known-issue HAT scaffold landed (L5 — file authoring; binary PASS gate deferred to docker).
4. ✓ `_drive_flow` httpx-error broadcast — already-satisfied per F6 Phase 1b reconnaissance (`api.py:1106-1121` already catches & broadcasts `auth_failed`).

**Carry-forward debts inherited (NOT fixed in F6)**:
- F4 task-pinning trade-off: pool entry's OAuth provider + override material pinned to FIRST acquire's csid+tcid+source_override for the entry's lifetime. Mid-session edits don't take effect until idle reap. Documented in F6 §4-trade-off-detail and L3 leg artifact; out of F6 scope.
- L6 docs sweep: 5th `same-task-anyio-cm-ownership` convention in agents.md, README "F5 Lazy-path Two-Event UX" section + F5→F6 carry-forwards table, `provider_factory.py` flowchart docstring — deferred to routine maintenance.

**Mission criteria advanced** (F6's contribution; full assessment at debrief):
- ✓ #7 (agent attaches MCP sources; tools become callable)
- ✓ #8 (tool-name collision under stable namespacing)
- ✓ #10 (graceful failure isolation per source)
- ✓ #11 partial (resolver substitution + tool-namespacing automated coverage; OAuth flow + idle-TTL + sandbox already covered by F2-F5)

---

## Leg Progress

(append per leg as legs complete)

### Leg 00: break-circular-imports — landed 2026-05-08

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Started**: 2026-05-08T07:00:00Z (approx)
- **Completed**: 2026-05-08T12:28:35Z
- **Pre-edit SHA**: `46c7a85` (F6 design commit; same baseline as flight start)
- **Changes Made**:
  - `the_one/mcp/errors.py` — added canonical `MCPAuthRequired` class (verbatim move from `oauth/errors.py`); added new `MCPRegistrationError` class (~+50 LOC).
  - `the_one/mcp/oauth/errors.py` — removed `MCPAuthRequired` definition; added re-export `from the_one.mcp.errors import MCPAuthRequired, MCPClientError  # noqa: F401`; added `__all__` block; added docstring sentence about canonical-home relocation (~-30 LOC class def, +9 LOC).
  - `the_one/agent/core.py` — dropped F5 lazy-import comment block (lines 8-13); added module-top `from the_one.mcp.errors import MCPAuthRequired`; dropped lazy-import statement and its preceding comment inside `_execute_tool` (~-9 LOC, +1 LOC).
  - `the_one/mcp/client.py` — dropped F5 lazy-import comment block (lines 41-45); inserted `MCPAuthRequired` into the existing `from the_one.mcp.errors import (...)` tuple (alphabetical position: between `MCPArgumentError` and `MCPCallError`); dropped lazy-import statement and its preceding comment inside `call_tool` (~-7 LOC, +1 LOC).
  - `the_one/mcp/__init__.py` — extended the `from the_one.mcp.errors import (...)` tuple with `MCPAuthRequired` and `MCPRegistrationError`; extended `__all__` with the same names (placed near positional siblings per the leg's grouping note).
  - `tests/test_agent.py` — added module-top `from the_one.mcp.errors import MCPAuthRequired`; removed lazy import inside `test_execute_tool_translates_mcp_auth_required_to_metadata`.
  - `tests/test_imports.py` (NEW) — 2 subprocess-isolated tests (~50 LOC): positive case locks the chain break (importing `the_one.agent.core` does NOT pull in `the_one.mcp.oauth.*`); negative case locks that explicit `import the_one.mcp.oauth` still loads the storage chain.
- **Verification gates**:
  - `grep -n "^class MCPAuthRequired" the_one/mcp/errors.py` → 1 hit; same grep on `the_one/mcp/oauth/errors.py` → 0 hits.
  - `grep -n "^class MCPRegistrationError" the_one/mcp/errors.py` → 1 hit.
  - `python -c "from the_one.mcp.errors import MCPAuthRequired, MCPRegistrationError, MCPClientError; assert issubclass(MCPAuthRequired, MCPClientError); assert issubclass(MCPRegistrationError, MCPClientError)"` → exit 0.
  - `python -c "from the_one.mcp.oauth.errors import MCPAuthRequired as A; from the_one.mcp.errors import MCPAuthRequired as B; assert A is B"` → exit 0 (re-export identity preserved).
  - `python -c "from the_one.mcp import MCPAuthRequired, MCPRegistrationError"` → exit 0 (top-level re-export works).
  - `grep "from the_one.mcp.oauth.errors import MCPAuthRequired" the_one/agent/core.py the_one/mcp/client.py tests/test_agent.py` → 0 hits across all three files.
  - `grep "imported lazily" the_one/agent/core.py the_one/mcp/client.py` → 0 hits (comment blocks dropped).
  - `pytest tests/test_imports.py -v` → 2 passed.
  - `pytest tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_oauth_provider_factory.py tests/test_imports.py -v` → 17 passed.
  - `pytest tests/test_agent.py tests/test_mcp_client.py -v` → 75 passed.
  - `ruff check the_one/ tests/` → All checks passed.
  - Combined leg-targeted suite (6 files: imports + oauth errors + oauth integration + oauth provider factory + agent + mcp_client) → 92 passed in 1.87s.
- **Test count delta**: full project suite +2 tests (the new `tests/test_imports.py` file), expected 1280 → 1282 inside the dev container.
- **Deviations from leg artifact**:
  - **D1 — `MCPRegistrationError` docstring line wrap**: leg artifact's IG step 2 specified the docstring text including the line `- Tool-name length exceeds the LLM provider tool-name ceiling (64 chars per OpenAI/Anthropic spec)`. That line is 102 chars, exceeding the project's `ruff` 100-char limit. Wrapped to two lines (`- Tool-name length exceeds the LLM provider tool-name ceiling (64 chars per` / `        OpenAI/Anthropic spec)`). Pure formatting change; no semantic shift. Ruff clean post-fix.
  - **D2 — `__all__` ordering in `the_one/mcp/__init__.py`**: leg artifact's IG step 6 specified positional grouping (i.e., `MCPAuthRequired` near `MCPArgumentError`/`MCPCallError`; `MCPRegistrationError` near `MCPConnectionError`/`MCPToolNotFoundError`). The pre-existing `__all__` block already deviates from strict alphabetical order — it lists `MCPClientError, MCPVersionMismatch, MCPCapabilityMissing, MCPConnectionError, MCPToolNotFoundError, MCPArgumentError, MCPCallError`. New entries inserted to match the leg's positional intent: `MCPRegistrationError` between `MCPConnectionError` and `MCPToolNotFoundError`; `MCPAuthRequired` between `MCPArgumentError` and `MCPCallError`. Implementation matches the leg's intent.
- **Anomalies**:
  - **A1 — Outside-container test environment delta**: full project suite (`pytest --tb=no -q --timeout=30` against the local `.venv` outside `docker compose`) shows 18 failures + 7 errors NOT seen in the F5 dev-container baseline. Inspection: all failures are infrastructure-driven (no docker daemon running locally; aiosqlite worker thread + ASGI fixtures + bwrap-privilege tests all hit env limits). None of the failing tests reference `MCPAuthRequired` or any L0-touched symbol; targeted leg test gates (`tests/test_imports.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_oauth_provider_factory.py tests/test_agent.py tests/test_mcp_client.py` — 92 tests) all green. Per F5 flight-log convention, full-suite gate should be re-run inside `docker compose exec the-one pytest -q --timeout=30` at flight-end review for the canonical 1282-pass count.
- **Files changed (7)**:
  - `the_one/mcp/errors.py`
  - `the_one/mcp/oauth/errors.py`
  - `the_one/mcp/__init__.py`
  - `the_one/mcp/client.py`
  - `the_one/agent/core.py`
  - `tests/test_agent.py`
  - `tests/test_imports.py` (NEW)
- **Notes**: Net delta ~+85 LOC production+tests, ~-15 LOC retirement, ≈ +70 LOC total — matches the leg artifact's stake estimate. The chain-break invariant (`the_one.agent.core` import does NOT load `the_one.mcp.oauth.*`) is locked by `test_import_agent_core_does_not_load_mcp_oauth` running in subprocess isolation.

### Leg 01: mcp-overrides-schema-and-agent-config — landed 2026-05-08

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Started**: 2026-05-08 (immediately after L0)
- **Completed**: 2026-05-08 (FD finished verification gates after recovering from a hung implementer-Developer run — see Anomaly A2 below)
- **Implementation**: First Developer agent wrote all production + test code but hung running the broader pytest suite outside the docker container (40 minutes elapsed before user-killed). Recovery: Flight Director ran the leg's targeted gates directly; all gates pass, code is sound, hang root cause is the same env-driven `aiosqlite._connection_worker_thread` issue documented in L0 anomaly A1.
- **Changes Made**:
  - `the_one/mcp/_overrides.py` (NEW) — `StdioMCPOverride` + `StreamableHttpMCPOverride` Pydantic schemas with `Annotated[T | None, Substitute] = None` placement (cycle-1 H1 inverted form). Both `frozen=True`.
  - `the_one/agent/config.py` — `mcp_overrides: dict[str, dict[str, Any]] | None = None` field added (~+10 LOC).
  - `the_one/db/schema.py` — `CURRENT_VERSION` bumped 10 → 11; v11 ALTER block added (~+22 LOC) following the v8 precedent verbatim.
  - `the_one/db/repositories.py` — `SQLiteAgentStore.save` UPSERT extended; `_row_to_config` parse extended (~+8 LOC).
  - `tests/test_mcp_overrides.py` (NEW) — 11 tests covering marker placement, resolver dispatch, frozen-model semantics. All pass in 0.03s.
  - `tests/test_db_repositories.py::TestSQLiteAgentStore` — `test_mcp_overrides_round_trip` + `test_mcp_overrides_none_default` added.
  - `tests/test_db_migration.py` — `TestSchemaV11` class (3 tests: fresh-DB shape, v10→v11 preserves rows, idempotent); 3 mechanical `CURRENT_VERSION == 10 → == 11` bumps (V8/V9/V10 fresh-DB tests); 3 literal-10 max-version assertions rewritten to `CURRENT_VERSION` indirection per cycle-1 low #3 (~+163 LOC).
- **Verification gates** (all run with `--timeout=15` per-test cap):
  - `pytest tests/test_mcp_overrides.py -v` → 11 passed in 0.03s.
  - `pytest tests/test_db_migration.py::TestSchemaV11 tests/test_db_repositories.py::TestSQLiteAgentStore tests/test_db_migration.py::TestSchemaV8 tests/test_db_migration.py::TestSchemaV9 tests/test_db_migration.py::TestSchemaV10 -v` → 28 passed in 3.64s.
  - L0 regression gate (88 tests across `test_imports`, `test_mcp_oauth_errors`, `test_mcp_oauth_integration`, `test_agent`, `test_mcp_client`) → 88 passed in 1.36s.
  - `ruff check the_one/ tests/` → All checks passed.
  - **Total verified**: 127 targeted tests pass; net L1 delta confirmed via `git diff --stat`.
- **Test count delta**: +14 new tests (11 in `test_mcp_overrides.py` + 2 in `test_db_repositories.py` + 3 in `test_db_migration.py::TestSchemaV11`). Expected post-L0+L1 count inside container: 1296.
- **Deviations**: none (cycle-1 fixes applied at design time; implementer followed the spec verbatim).
- **Files changed (4 modified + 1 new since L0)**:
  - `the_one/mcp/_overrides.py` (NEW)
  - `the_one/agent/config.py`
  - `the_one/db/schema.py`
  - `the_one/db/repositories.py`
  - `tests/test_mcp_overrides.py` (NEW)
  - `tests/test_db_repositories.py`
  - `tests/test_db_migration.py`
- **Notes**: The cycle-1 H1 inverted-`Annotated` placement is the load-bearing detail. Subsequent legs adding override schemas MUST use `Annotated[T | None, Substitute] = None`, NEVER `Annotated[T, Substitute] | None = None`. The 3 marker-introspection regression tests in `tests/test_mcp_overrides.py::TestMarkerPlacementRegression` lock this for future schema additions.

### Leg 02: mcp-tool-provider-and-routing — landed 2026-05-08

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Started**: 2026-05-08 (immediately after L1)
- **Completed**: 2026-05-08 (FD finished verification + lint repairs after recovering from a hung implementer-Developer test gate run — see Anomaly A3 below)
- **Implementation**: Largest leg of F6 (~820 LOC). 2-cycle Architect design review applied 3 mediums + 1 low (constructor signature change) + 3 test gaps + 1 mild defect inline before implementation. Implementer-Developer wrote all production + test code correctly, then hung on the test gate when `tests/test_mcp_pool.py` was run outside docker — same root cause as L0 anomaly A1 / L1 anomaly A2. Recovery: Flight Director ran targeted L2 + regression gates directly excluding `test_mcp_pool.py`; all 202 targeted tests pass; ruff clean post-7-error repair (4 autofixed, 3 manual: 1 F821 via TYPE_CHECKING, 2 E501 line-wraps).
- **Changes Made**:
  - `the_one/mcp/_tool.py` (NEW) — `MCPClientTool(Tool)` wrapper; constructor takes `(mcp_tool, source_id, source_name, agent_name, effective_source)`; `name = f"mcp__{normalize}__{tool}"`; raises `MCPRegistrationError` at 64-char ceiling; `execute(**kwargs)` calls `acquire(source_override=self._effective_source)` then `client.call_tool`. Cycle-1 low #5 fix threaded through.
  - `the_one/mcp/_tool_provider.py` (NEW) — `MCPToolProvider.get_tools_for_agent(config, *, agent_name)`; loads sources from F1 repo; resolves overrides via `_apply_override` helper (stdio env merge / streamable-http replace); calls `acquire` with `source_override=effective_source`; wraps `MCPTool`s in `MCPClientTool`s; handles all 5 failure classes from §8 + 64-char ceiling; orphan-warn fires even on empty `mcp_source_ids` (cycle-1 medium #4 fix).
  - `the_one/mcp/_pool.py` — `acquire` widened with `*, source_override: MCPSource | None = None` kwarg (~+6 LOC). Existing callers unchanged.
  - `the_one/mcp/__init__.py` — re-exports `MCPClientTool` and `MCPToolProvider` (~+4 LOC).
  - `the_one/agent/factory.py` — `__init__` accepts `mcp_provider: MCPToolProvider | None`; `create()` registers MCP tools after the built-in loop through the same `disabled_names + is_tool_enabled` filter (~+25 LOC). Added `from typing import TYPE_CHECKING` block at module top to satisfy ruff F821 on the lazy-imported `MCPToolProvider` annotation.
  - `tests/test_mcp_tool_provider.py` (NEW) — 31 tests across 4 classes per the cycle-1-expanded inventory: `TestMCPClientTool` (9), `TestApplyOverride` (6), `TestMCPToolProvider` (12), `TestAgentFactoryMCPIntegration` (3). Includes the 3 cycle-1 test-gap additions (`test_execute_propagates_mcp_auth_required`, `test_orphan_override_logs_warning_for_each_unknown_key`, `test_duplicate_source_id_registers_once`) plus `test_failure_class_4_collision_drops_partial_first_source_tools` and `test_apply_override_schema_mismatch_propagates`.
  - `tests/test_mcp_pool.py` — `test_acquire_with_source_override` added (~+30 LOC) to lock the new kwarg behavior. **Note**: this test cannot execute outside docker due to `_entry_worker`'s `get_connection()` for OAuth provider construction — same env-dependence as the rest of `test_mcp_pool.py`. Verification deferred to flight-end inside docker; the test follows the existing `monkeypatch.setattr(pool_mod, "MCPClient" / "_load_source", ...)` pattern verbatim and is structurally identical to the existing 22 pool tests that pass inside docker.
- **Verification gates** (all run with `--timeout=10` per-test cap):
  - `pytest tests/test_mcp_tool_provider.py tests/test_mcp_overrides.py -v` → 42 passed in 0.11s.
  - L0+L1 regression (`test_imports`, `test_mcp_oauth_errors`, `test_mcp_oauth_integration`, `test_agent`, `test_mcp_client`, `test_db_repositories`, `test_db_migration`) → 160 passed in 10.34s.
  - `ruff check the_one/ tests/` → All checks passed (after fixing 7 errors: 4 autofixed import-sort/F401-unused; 3 manual: F821 via `TYPE_CHECKING` block + 2 E501 line-wraps + 1 E402 noqa-coverage repair).
  - **Total verified**: 202 targeted tests pass.
  - **Deferred to flight-end inside docker**: `tests/test_mcp_pool.py` (22 existing + 1 new acquire-widening test) — env-dependent per L0 A1 / L1 A2 / L2 A3.
- **Test count delta**: +32 new tests (31 in `test_mcp_tool_provider.py` + 1 in `test_mcp_pool.py`). Expected post-L0+L1+L2 count inside container: 1328.
- **Deviations from leg artifact**:
  - **D2 — `TYPE_CHECKING` block for ruff F821 compliance**: leg artifact's IG step 4 specified the lazy-import-inside-`__init__` pattern with a string-quoted `"MCPToolProvider | None"` annotation. With `from __future__ import annotations` already in effect, Python's runtime accepts this — but ruff F821 flags it as undefined name. Added `if TYPE_CHECKING: from the_one.mcp._tool_provider import MCPToolProvider` block at module top (5 LOC); annotation becomes `MCPToolProvider | None` (no quotes needed). Zero runtime cost (TYPE_CHECKING is False at runtime), satisfies ruff. Pure tooling-compliance change.
- **Anomalies**:
  - **A3 — L2 implementer Developer hung on `test_mcp_pool.py` in targeted gate**: the L2 leg artifact's IG step 9 included `tests/test_mcp_pool.py` in the targeted gate command. This was the Flight Director's mistake — L0 anomaly A1 already documented `test_mcp_pool.py` as env-dependent (its `_entry_worker` calls `get_connection()` to construct the OAuth provider, which hangs on aiosqlite worker-thread setup outside docker). The hang reproduces on EVERY pool test, not just the new `test_acquire_with_source_override`. The leg's targeted-gate was over-broad. Recovery: re-ran without `test_mcp_pool.py`; all 202 tests pass. Process correction: future leg artifacts referencing pool tests in their targeted gate must explicitly note the env-dependence and exclude.
- **Files changed (5 modified + 3 new since L1)**:
  - `the_one/mcp/_tool.py` (NEW)
  - `the_one/mcp/_tool_provider.py` (NEW)
  - `the_one/mcp/_pool.py`
  - `the_one/mcp/__init__.py`
  - `the_one/agent/factory.py`
  - `tests/test_mcp_tool_provider.py` (NEW)
  - `tests/test_mcp_pool.py`
- **Notes**: The override-application semantic split (stdio env MERGE vs streamable-http headers/bearer_token REPLACE) is the load-bearing design choice. Operator-set stdio env vars not overridden by the agent pass through unchanged (per F6 §1); operator-set streamable-http headers DO NOT pass through (deliberate departure from F6 §1, justified by credential-identity argument — agent's headers represent a FULL credential identity, NOT a partial overlay). If F7 surfaces operator pain, revisit. Documented in F6 debrief as carry-forward design choice.

### Leg 03: context-relocation-and-per-tool-binding — landed 2026-05-08

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Started**: 2026-05-08 (immediately after L2)
- **Completed**: 2026-05-08 (single-pass implementation; targeted gate green; lint clean post-1-fix-pass)
- **Implementation**: Mid-size leg (~150 LOC total: ~30 LOC net production + ~120 LOC tests). Followed the 8-step Implementation Guidance verbatim. The data-flow primitive (new `the_one/agent/_context.py` module) was created first; consumers (`app.py` re-export, `_pool.py::_entry_worker`, `provider_factory.py`, `agent/core.py::_execute_tool`) were updated in dependency order; tests authored last. No design deviations; no anomalies.
- **Changes Made**:
  - `the_one/agent/_context.py` (NEW, ~70 LOC) — canonical home for `current_chat_session_id` and `current_tool_call_id` ContextVars. Module docstring documents the canonical-import + convenience-re-export convention, the cross-task `asyncio.create_task` snapshot semantics, and the F4 task-pinning trade-off carried through F6.
  - `the_one/interfaces/web/app.py` — F5's module-level `current_chat_session_id` definition replaced with a re-export `from the_one.agent._context import current_chat_session_id, current_tool_call_id`. F5's set-sites at `:218, :238, :835, :857` (post-relocation line numbers) continue to work unchanged via the re-exported name. Dropped the now-stale `from contextvars import ContextVar` import + the F5 docstring block (lines 188-211 of pre-L3 app.py); canonical home's docstring is more authoritative.
  - `the_one/mcp/_pool.py::_entry_worker` — replaced the lazy `from the_one.interfaces.web.app import current_chat_session_id` with `from the_one.agent._context import current_chat_session_id, current_tool_call_id`. Dropped the `or "_pool_default"` sentinel. Now reads `current_tool_call_id.get(None)` and passes both csid + tcid to `build_oauth_provider_for_source(source, repo, csid, source_id=source.id, tool_call_id=tcid)`. Updated the leading comment block to describe the new None-passes-through behavior.
  - `the_one/mcp/oauth/provider_factory.py::build_oauth_provider_for_source` — type signature widened: `chat_session_id: str` → `chat_session_id: str | None`. Added a `chat_session_id is None` early-return BEFORE the `dcr_credentials` check (so a chat-session-less spawn skips the entire `make_oauth_handlers` + `MCPSourceTokenStorage` path). Module-top docstring lines 34-38 retired the "Architectural debt (carried to F6)" note; replaced with "F6 L3 retirement (2026-05-08): ..." paragraph documenting the canonical-ContextVar reads in `_entry_worker` + the multi-tab cross-routing-bug fix.
  - `the_one/agent/core.py::Agent._execute_tool` — wrapped existing function body in a `try/finally` that binds `current_tool_call_id.set(tool_call.id)` at function entry and resets via `current_tool_call_id.reset(token)` in finally. Both inner exception paths (`MCPAuthRequired` translation + generic `Exception` fallthrough) traverse the outer finally correctly (verified via test). Added module-top import `from the_one.agent._context import current_tool_call_id`.
  - `tests/test_agent_context.py` (NEW, 13 tests across 4 classes) — `TestContextVarsCanonicalHome` (3): canonical definitions + re-export identity for both csid and tcid. `TestPerToolDispatchBinding` (5): unset by default; observable from inside `tool.execute()`; reset to None after normal return; reset after `MCPAuthRequired` path; reset after generic Exception path. `TestPoolDefaultSentinelRetired` (2): grep `_pool_default` returns 0 hits in production; `_pool.py` uses canonical import + does not lazy-import from `app.py`. `TestProviderFactoryNoneCsidShortCircuit` (3): `chat_session_id=None` returns None; short-circuit runs BEFORE `source.secrets.get` (verified via mock that errors on access); real csid still hits the dcr branch.
- **Verification gates**:
  - Targeted L3 gate per leg artifact IG step 8 (excludes `tests/test_mcp_pool.py` per A1/A2/A3): `pytest tests/test_agent_context.py tests/test_oauth_provider_factory.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_overrides.py tests/test_mcp_tool_provider.py tests/test_db_migration.py tests/test_db_repositories.py tests/test_imports.py tests/test_mcp_client.py -v --timeout=15` → **219 passed in 10.48s** (13 new L3 + 206 L0+L1+L2+F5 OAuth regression).
  - `ruff check the_one/ tests/` → **All checks passed** (after 1 autofix pass: I001 import-block sort + F401 unused `pytest` removal in the new test file; no manual fixes needed).
  - Acceptance-criteria spot-checks all green:
    - `python -c "from the_one.agent._context import current_chat_session_id, current_tool_call_id; print('OK')"` → OK.
    - `python -c "from the_one.interfaces.web.app import current_chat_session_id as A; from the_one.agent._context import current_chat_session_id as B; assert A is B"` → exit 0.
    - `grep -rn "_pool_default" the_one/` → 0 hits (exit 1).
    - `grep -n 'current_chat_session_id: ContextVar' the_one/interfaces/web/app.py` → 0 hits (exit 1).
    - `grep -n 'from the_one.agent._context import' the_one/interfaces/web/app.py the_one/mcp/_pool.py the_one/agent/core.py` → 3 hits (re-export + 2 import sites).
- **Test count delta**: +13 new tests in `tests/test_agent_context.py`. Expected post-L0+L1+L2+L3 count inside container: 1341.
- **Deviations from leg artifact**: None. The leg artifact specified ~12 tests; the implementation has 13 (the `TestPerToolDispatchBinding` class added a 5th test — `test_unset_at_function_entry_by_default` — to lock the default-None invariant explicitly. Pure additive test coverage, not a design change).
- **Anomalies**: None. The L0/L1/L2 environment trap (full-suite pytest hangs on `tests/test_mcp_pool.py` outside docker) was honored; the targeted gate excluded `test_mcp_pool.py` per the leg artifact's explicit instruction. No env-driven hangs encountered.
- **Files changed (4 modified + 2 new since L2)**:
  - `the_one/agent/_context.py` (NEW)
  - `the_one/interfaces/web/app.py`
  - `the_one/mcp/_pool.py`
  - `the_one/mcp/oauth/provider_factory.py`
  - `the_one/agent/core.py`
  - `tests/test_agent_context.py` (NEW)
- **Notes**: The cycle-2-inherited warm-pool task-pinning trade-off remains (the OAuth provider built at FIRST acquire pins csid+tcid for the entry's lifetime; subsequent acquires within idle TTL reuse the cached client). F6 doesn't fix this; documented in `_context.py`'s module docstring + the F5 OAuth-handlers' `_sessions` "most-recently-active fallback" still covers the warm-pool cross-session case for now. The cold-spawn multi-tab cross-routing bug from F5 IS fixed — the `_pool_default` sentinel is fully retired and `chat_session_id=None` short-circuits to no-provider rather than constructing a handler that would broadcast to nowhere.

### Leg 05: hat-tier-1-with-caplog-retirement — landed 2026-05-08

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5; F2-known-issue retirement DEFERRED to flight-end docker run; mission.md:104 NOT yet edited)
- **Started**: 2026-05-08 (immediately after L3)
- **Completed**: 2026-05-08 (single-pass implementation; collection-only verification gate per L0/L1/L2/L3 inheritance)
- **Implementation**: File-authoring-only leg (no production code change). Wrote `tests/test_mcp_attach_hat.py` (~410 LOC; ~7 tests covering the 5-step Tier-1 sequence + caplog gate + bonus per-(agent, source) keying test) + `tests/HAT.md` (~100 LOC documenting Tier-1 docker run + Tier-2 GitHub MCP manual procedure + F2-known-issue retirement gate + on-FAIL follow-up flight scope). The HAT test file uses module-level `pytestmark = pytest.mark.skipif(not _HAT_AVAILABLE, ...)` to inherit skip behavior across all 7 tests; outside docker (no `bwrap`, no `mcp-server-fetch`), the tests SKIP cleanly rather than hang. The skipif probe for `mcp-server-fetch` uses `subprocess.run(... timeout=5)` to defend against the import itself hanging.
- **Changes Made**:
  - `tests/test_mcp_attach_hat.py` (NEW) — Tier-1 HAT scaffold. Module-level `pytestmark` skipif on bwrap + mcp-server-fetch availability. Tests: (1) `test_step_1_pre_state_register_sources_and_configure_agents` — locks DB-state precondition; (2) `test_step_2_tool_list_visibility_under_agent_build` — asserts prefixed tool names, no collision; (3) `test_step_3_tool_call_dispatch_via_pool_to_real_subprocess` — real bwrap subprocess + 1-PID pgrep; (4) `test_step_4_per_agent_isolation_distinct_subprocesses` — 2 distinct PIDs across agents A/B; (5) `test_step_5_graceful_degrade_delete_source_then_rebuild_drops_tools` (cycle-1 M5 restructure) — F6 §8 failure class #1 lock; (6) `test_caplog_no_transport_close_failed_warnings` — binary F2-known-issue retirement gate, replays steps 3+4+5 inside a single `caplog.at_level(WARNING, logger="the_one.mcp.client")` block, asserts `not any("MCPClient transport close failed" in r.message for r in caplog.records)` per the project's `verbatim-message-equality` convention; (7) `test_bonus_per_agent_source_keying_no_override` — F4 HAT precedent's per-(agent, source) keying invariant with NO override.
  - `tests/HAT.md` (NEW) — Tier-1 docker run command, Tier-2 GitHub MCP manual procedure (operator setup at github.com/settings/developers + manual-entry path through chat UI), F2-known-issue retirement gate with explicit assertion form + retirement-on-PASS protocol, "On FAIL" pre-written follow-up flight scope (revert F5 L1 helpers + dispatcher + README §3 scoping update; F2-known-issue stays open with diagnosis plan).
- **Verification gates**:
  - `pytest --collect-only tests/test_mcp_attach_hat.py -q` → 7 tests collected in 0.21s.
  - `pytest tests/test_mcp_attach_hat.py -v --timeout=10` → 7 SKIPPED (host has no bwrap + mcp-server-fetch). All skips, no failures, no hangs.
  - `ruff check the_one/ tests/` → All checks passed.
  - L0-L3 regression: `pytest tests/test_imports.py tests/test_mcp_overrides.py tests/test_mcp_tool_provider.py tests/test_agent_context.py tests/test_oauth_provider_factory.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_client.py tests/test_db_repositories.py tests/test_db_migration.py -q --timeout=15` → 219 passed in 10.63s.
- **Test count delta**: +7 new HAT tests in `tests/test_mcp_attach_hat.py` (all skipped on host; expected to PASS inside docker). Expected post-L0+L1+L2+L3+L5 count inside container: 1348 (1341 + 7).
- **Deviations from leg artifact**: None. Implementation followed the 7 numbered Implementation Guidance steps verbatim. Step 6 in the leg artifact (caplog gate) is implemented as a single test that replays steps 3-5 (the steps that actually spawn subprocesses) inside one `caplog.at_level` block, per the leg artifact's Edge Case "Caplog assertion across 5 steps" guidance.
- **Anomalies**: None. The L0/L1/L2/L3 environment trap (full-suite pytest hangs outside docker on `tests/test_mcp_pool.py` and any test that constructs a real `_entry_worker`) is honored: HAT test file's skipif inherits the same constraint via module-level `pytestmark`. Targeted L5 gate uses `pytest --collect-only` + `--timeout=10` SKIP-verification — no execution of the HAT tests outside docker.
- **F2-known-issue retirement status**: **DEFERRED to flight-end docker run**. The HAT test caplog assertion is the binary go/no-go gate; PASS retires the F2-known-issue from `missions/07-mcp-integration/mission.md:104`, FAIL files a follow-up flight per `tests/HAT.md`'s "On FAIL" section. **`mission.md:104` NOT edited in this leg.** The retirement edit happens AFTER the docker run actually PASSES — out of L5 scope per the leg artifact's "DO NOT" gate.
- **Files changed (2 new since L3)**:
  - `tests/test_mcp_attach_hat.py` (NEW)
  - `tests/HAT.md` (NEW)
- **Notes**: Net delta ~+510 LOC across 2 files; zero production code change. The `pytestmark = pytest.mark.skipif(...)` module-level pattern is the load-bearing protection against outside-docker hangs — every test in the file inherits the skip without per-test annotation. The `subprocess.run(... timeout=5)` defensive probe on `mcp-server-fetch` import is the second load-bearing detail: without it, an import hang in the parent process would propagate up into pytest collection. Both protections were verified by the host-side `pytest tests/test_mcp_attach_hat.py -v --timeout=10` showing 7 SKIPPED in 0.18s — fast, clean, no hangs.

---

## Decisions

(append as runtime decisions surface)

---

## Deviations

(append as planned-vs-actual gaps surface)

### 2026-05-08 — L0 docstring line wrap for ruff compliance

Leg L0 IG step 2 specified the `MCPRegistrationError` docstring text including the line `- Tool-name length exceeds the LLM provider tool-name ceiling (64 chars per OpenAI/Anthropic spec)` (102 chars). Project's `ruff` 100-char limit rejected this; wrapped to two lines (`(64 chars per` newline `OpenAI/Anthropic spec)` with continuation indent). Pure formatting; no semantic shift. Ruff clean post-fix.

---

## Anomalies

(append as unexpected issues surface)

### 2026-05-08 — A5 — OAuth-protected source without credentials crashes agent build (found + fixed during Tier-2 HAT)

User opted to do Tier-2 HAT (live GitHub MCP via streamable-http). Registered `https://api.githubcopilot.com/mcp/` as a streamable-http source with no auth credentials, attached to a fresh `hat_github` agent (no `mcp_overrides`, GitHub MCP requires OAuth/PAT and we passed neither). Per cycle-2 H1 disposition, the registry-build path was supposed to graceful-degrade-skip via failure class #2 with "MCPConnectionError: failed to connect" diagnostic. **It crashed instead.**

**Root cause cascade**:
1. `MCPClient.connect()` (`the_one/mcp/client.py`) calls `session.initialize()` — the SDK's first JSON-RPC call to the server.
2. GitHub returns 401. SDK's `streamable_http_client` async-context-manager's anyio task group hits `httpx.HTTPStatusError`.
3. The task group's `__aexit__` runs cleanup on a different task than the one that opened it → `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in` (the F2-class cross-task-cancel-scope guard).
4. The cancel-scope chain converts the error into `asyncio.CancelledError` by the time it reaches `MCPClient.connect()`'s exception handlers.
5. **Cycle-2 H1's pre-existing claim** ("`list_tools` translates 401 to `MCPConnectionError`") was correct as far as it went — but `connect()` calls `initialize()` BEFORE `list_tools` ever runs, and `connect()`'s pre-A5 `except Exception as e: raise MCPConnectionError(...) from e` did NOT catch `asyncio.CancelledError` (which extends `BaseException` only, per Python 3.8+ PEP 656).
6. CancelledError propagated up: `_entry_worker` → `acquire` → `MCPToolProvider.get_tools_for_agent`, whose class #2 handler `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch)` also missed it. Agent build crashed.

**Production impact**: operator registers a streamable-http MCP source without credentials → first chat message after attaching it → entire agent build crashes, chat dies. NOT graceful-degrade as F6 §8 + cycle-2 H1 documented.

**Inherited from F5, amplified by F6**: F5's lazy-401 design assumed the 401 surfaces from `call_tool`, not from build-time `connect()` → `initialize()`. F6 §4's eager-at-AgentFactory.create choice (calling `acquire` + `list_tools` at build) put the 401 ahead of the user's first tool call. F2/F4/F5 didn't exercise OAuth-protected streamable-http sources at agent-BUILD time because nothing called `acquire` at build pre-F6.

**Fix** (inline during HAT, post-A4-fix-tested-clean):

`the_one/mcp/client.py::MCPClient.connect` exception handlers extended:

1. **NEW first handler `except asyncio.CancelledError`** — translates the cross-task cancel-scope cancellation to `MCPConnectionError`; **abandons** the transport stack reference (sets `self._transport_stack = None` and `self._session = None`) **without** calling `_cleanup_after_failed_connect`. Calling cleanup would re-trigger the SDK's wedged task group and either hang or re-cancel; we accept the partial-connection leak (GC + process shutdown reaps) in exchange for not deadlocking the agent build.
2. **NEW second handler `except (Exception, BaseExceptionGroup)`** — extends the catch list with `BaseExceptionGroup` so any non-cancelled SDK task-group exception groups also collapse to `MCPConnectionError` (with optional 401 walk → `MCPAuthRequired` if the SDK ever surfaces a clean-grouped HTTPStatusError).
3. **`_safe_cleanup` helper** — wraps `_cleanup_after_failed_connect` in `asyncio.wait_for(timeout=3.0)` for the non-cancelled path, narrows catch to `(asyncio.TimeoutError, Exception, BaseExceptionGroup)` (does NOT catch CancelledError so caller cancellations propagate cleanly), abandons stack on cleanup failure.

**Tests**: 1 new regression test `test_connect_cancelled_error_translates_to_connection_error` in `tests/test_mcp_client.py::TestConnectDisconnectLifecycle`. Mocks `session.initialize` to raise `asyncio.CancelledError` directly (avoids needing a real anyio task group + cross-task setup); asserts `MCPConnectionError` raised, `is_alive=False`, abandon-cleanup invariant (`_transport_stack is None`, `_session is None`). 121 → 122 targeted regression tests pass.

**HAT continuation**: post-A5-fix, `factory.create('hat_github')` succeeds in 0.3s with 16 builtins + 0 MCP tools. The expected WARNING fires: `MCP source 'GitHub' failed to connect: MCPConnectionError: MCP connect failed: cancelled during initialize (cross-task cleanup deadlock; original cause likely 401 Unauthorized or transport error): Cancelled via cancel scope ...; skipping`. Operator UX: chat works for `hat_github`, GitHub tools simply absent.

**Carry-forward to F7**: the diagnostic message "cancelled during initialize" is lossy — the actual cause is a 401 but the cross-task cancel-scope cleanup chain loses the `httpx.HTTPStatusError` context by the time we catch. F7 (inspector) was already getting cycle-2 H1's "extend list_tools/connect with except* OAuth translation" carry-forward; A5's cleaner-diagnostic improvement folds in. The current message is acceptable for v1 because the pattern "create source without credentials → see WARNING in logs / no MCP tools in agent registry → realize you need OAuth or PAT" is operator-discoverable.

### 2026-05-08 — A4 — `_apply_override` nesting bug found + fixed during HAT step 3

The L2 leg's `_apply_override` was nesting the agent's overlay under `secrets["env"]` (stdio) / `secrets["headers"]` + `secrets["bearer_token"]` (streamable-http) — but the F2 transport contract treats `source.secrets` as a **flat kv table at top level** (`transports/stdio.py:224-225`: `{**allowlist_env, **config_env, **source.secrets}`; `transports/streamable_http.py:68-69`: `{**config_headers, **source.secrets}`). The nesting caused `StdioServerParameters` to receive `env={"env": {"HAT_AGENT": "A"}}` — the SDK rejected with `string_type` validation error because the env-var VALUE was a dict, not a string.

The bug surfaced as a `MCPConnectionError: ValidationError: 2 validation errors for StdioServerParameters` at HAT step 3 (agent build → list_tools → bwrap spawn). HAT's failure-class #2 graceful-degrade caught it (agent built with 0 MCP tools + a WARNING log), so F6's runtime contract held — but the override path was non-functional.

**Root cause**: cycle-1 medium #3's "REPLACE for streamable-http headers" disposition was structurally unsafe against the F2 contract — would nuke every operator header (including OAuth-managed keys living in `source.secrets`). The "OVERLAY for stdio env via `secrets['env']`" framing was likewise wrong against the same flat-secrets contract.

**Fix** (inline during HAT, before re-running step 3):
- `the_one/mcp/_tool_provider.py::_apply_override` — both branches now flat-merge into `source.secrets` directly:
  - stdio: `{**source.secrets, **resolved.env}` (overlay; agent wins on collision)
  - streamable-http: overlay `headers` flat; `bearer_token` translates to `secrets["Authorization"] = f"Bearer {bearer_value}"`
- 4 affected tests in `tests/test_mcp_tool_provider.py::TestApplyOverride` updated to assert flat-merge + the new `Authorization` translation; renamed `test_apply_override_streamable_http_replaces_*` → `test_apply_override_streamable_http_overlays_*` / `test_apply_override_streamable_http_bearer_token_becomes_authorization`.
- `test_override_applies_correctly` in `TestMCPToolProvider` updated for flat-secrets shape.
- 31 tests still pass (post-fix): `pytest tests/test_mcp_tool_provider.py -v --timeout=10` → 31 passed in 0.09s.

**Documentation**: the `_apply_override` docstring is rewritten to cite the F2 contract and the cycle-1 M3 disposition correction. Future schema additions to `StdioMCPOverride` / `StreamableHttpMCPOverride` MUST flat-merge into `source.secrets` to match the transport contract.

**HAT continuation**: post-fix, HAT step 3 PASSED (1 MCP tool registered with `--setenv HAT_AGENT A` in the bwrap argv, proving end-to-end override application). HAT steps 4a, 4b, 5, and the caplog gate all PASSED — F2-known-issue retired.

### 2026-05-08 — Tier-1 HAT PASS (full sequence; F2-known-issue retired)

5-step verification + caplog gate executed end-to-end against the dev container's bwrap-spawned `mcp-server-fetch`:

- **Step 1**: source registered via Studio UI — `fetch_local` (stdio, network_allowed=true).
- **Step 2**: `hat_agent_a` + `hat_agent_b` PUT via API with `mcp_source_ids=[<id>]` and distinct `mcp_overrides[fetch_local].env.HAT_AGENT` values (A vs B). Builtin web tools (`fetch_url`, `download_file`, `http_request`) disabled on both agents to force the MCP path during step 4 chat dispatch (qwen2.5:7b's tool-pick heuristic favored the simpler-named `fetch_url` builtin in the first 4a attempt; disabling forced the MCP route).
- **Step 3**: agent A registry inspection (REPL) — 16 builtins + 1 MCP tool (`mcp__fetch_local__fetch`).
- **Step 4a**: chat dispatch via `hat_agent_a` UI — agent invoked `mcp__fetch_local__fetch(url="https://example.com/")`; one bwrap subprocess tree alive with `--setenv HAT_AGENT A`.
- **Step 4b**: chat dispatch via `hat_agent_b` UI — second bwrap subprocess tree spawned with `--setenv HAT_AGENT B`. F4's per-`(agent, source)` keying with distinct env overrides spawned distinct subprocesses end-to-end.
- **Step 5**: source deleted via Studio UI; agent A rebuilt in REPL — 16 tools, 0 MCP tools. Two WARNINGs fired: failure class #1 (`agent 'hat_agent_a' references deleted MCP source ...; skipping`) + cycle-1 M4 orphan-warn (`mcp_overrides references unknown source name 'fetch_local'`).
- **Caplog gate**: `docker compose logs --since="$HAT_START" the-one | grep "MCPClient transport close failed" | wc -l` → **0**. Includes a uvicorn WatchFiles reload (triggered by editing `_tool_provider.py` for the A4 fix mid-HAT) which exercised the full lifespan shutdown_drain path → per-entry `_evict` → worker `finally:` → `disconnect()` for every warm pool entry. **F2-known-issue retirement: PASS.**

`mission.md::Known Issues` line 104 updated: F2-known-issue checkbox flipped to `[x]` with a one-line retirement note citing 2026-05-08 HAT.

### 2026-05-08 — A3 — L2 leg-artifact targeted gate over-broad; pool tests hang outside docker

L2's leg artifact IG step 9 included `tests/test_mcp_pool.py` in the targeted-gate command. The implementer-Developer ran this gate and hung — same root cause as A1/A2: `_entry_worker` calls `get_connection()` for OAuth provider construction (`_pool.py:184`), which blocks on aiosqlite worker-thread setup outside docker. The hang affects EVERY test in `test_mcp_pool.py` (all 23 tests + the new `test_acquire_with_source_override`), not just the new test.

Recovery (this session): Flight Director recognized the same A1 pattern, re-ran the targeted gate excluding `test_mcp_pool.py`. All 42 L2 unit tests + 11 L1 schema tests + 160 L0+L1 regression tests pass. New `test_acquire_with_source_override` is structurally identical to the existing 22 `test_mcp_pool.py` tests (same `monkeypatch.setattr(pool_mod, "MCPClient" / "_load_source", ...)` pattern); verification deferred to flight-end inside `docker compose exec the-one pytest`.

Process correction: future leg artifacts referencing pool tests in their targeted gate MUST explicitly note env-dependence and exclude. The L0 anomaly A1 listed `test_mcp_pool.py` as env-dependent; L2 leg-design Phase 3b should have caught this in citation audit but did not. Adding to F6 debrief recommendations: leg-design-time citation-audit must verify "tests this leg references run cleanly in the gate environment we're using" — not just "files exist."

### 2026-05-08 — A2 — L1 implementer Developer hung 40 minutes on full-suite pytest

L1's first Developer-agent implementation run wrote all production + test code correctly, then hung 40 minutes on the full-suite pytest gate before user-killed. Root cause: same env-driven `aiosqlite._connection_worker_thread` block documented in L0's A1 below — running the unfiltered `pytest --tb=no -q` outside `docker compose` reaches `tests/test_mcp_pool.py` and other infra-dependent tests that hang waiting for resources that don't exist on the host.

Recovery (this session, post-kill): Flight Director ran the leg's targeted gates directly with `--timeout=15` per-test caps. All 127 targeted tests passed (11 + 28 L1-scoped + 88 L0-regression). Lint clean. Production code matches the leg spec verbatim; no implementation deviation.

Process learning carried to future legs: the leg-execution prompt's "Run tests with a timeout flag appropriate to this project's test runner" instruction is necessary but insufficient — the per-test timeout (`--timeout=N`) catches a single hanging test but does NOT bound the full-suite walltime when 30+ tests independently hit the 30s ceiling. Either (a) the implementer should NEVER run the full unfiltered suite outside docker (use targeted runs only, with full-suite gating deferred to flight-end inside the container), OR (b) the prompt should specify an outer `timeout 600 pytest ...` shell-level cap. F6 L2+ implementer prompts will adopt option (a) — targeted runs only; flight-end review handles the canonical full-suite gate inside the container.

### 2026-05-08 — L0 outside-container full-suite environment delta

Full project suite run outside `docker compose` (against local `.venv` only) showed 18 failures + 7 errors clustered in `tests/test_mcp_pool.py`, `tests/test_mcp_integration.py`, and `tests/test_mcp_sandbox_integration.py::test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3`. Stack traces show:

- Pool tests timeout in `aiosqlite._connection_worker_thread`-bound waits (DB worker thread hangs without docker daemon).
- Integration tests error in setup (ASGI fixture cannot bind without proper container networking).
- The bwrap test depends on the privilege-stripped env that the dev container intentionally provides.

None of the failing tests reference `MCPAuthRequired` / `MCPRegistrationError` / any L0-touched symbol. The leg's targeted test gates (`tests/test_imports.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_oauth_provider_factory.py tests/test_agent.py tests/test_mcp_client.py` — 92 tests) all green. F5 baseline documents these tests as passing inside `docker compose exec the-one pytest`; this is purely a host-vs-container env delta. Flagged for the flight-end review to confirm the canonical 1282-pass count inside the container before commit.

---

## Session Notes

### 2026-05-08 — Flight start

Branch created. Flight artifact transitioned `ready` → `in-flight`. F5 + F4 stacked beneath; F6 PR will target F5 branch and rebase onto main once F4/F5 merge.

---

## Flight Director Notes

Transparency log for orchestration decisions. Per `agentic-workflow/SKILL.md` — "anyone reviewing the flight log can understand not just what the crew did, but why the Flight Director made the orchestration choices it did."

### 2026-05-08 — Phase 1: context loading + branch setup

- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project-side, NOT default fallback). Validated structure: `## Crew`, `## Interaction Protocol`, `## Prompts` all present; all prompt subsections have fenced code blocks.
- **Crew extracted**: Developer (Sonnet) for design-review + implement + fix + commit; Reviewer (Haiku) for code review; Accessibility Reviewer (Sonnet, optional) for UI legs only — F6 has zero UI surface, so the A11y Reviewer will NOT be spawned in this flight.
- **Branch strategy**: stacked. F4 PR #31 and F5 PR #32 are both open and unmerged; F6 builds on top of F5 (which builds on F4). Branch `flight/06-mcp-attach-and-tool-routing` created from current HEAD (F5 branch tip). PR will target the F5 branch initially; rebase to main once F4 + F5 land.
- **Total legs**: 5 required (L0, L1, L2, L3, L5) + 2 optional (L4 default-fold-into-L2, L6 default-fold-into-L5). HAT precedent says L5 is interactive — does NOT use autonomous Developer agent; the Flight Director guides the human through it step-by-step.

### Orchestration cadence reminder

Per F5 debrief recommendation #4 (Process #4 — context-budget pressure): after every 2 legs OR every ~3 hours of active orchestration, the Flight Director MUST checkpoint to the user. F6 has 5 implementation legs; expected checkpoint after L1 (post-2-legs) and after L3 (post-2-more-legs). L5 is human-interactive and naturally interrupts.

