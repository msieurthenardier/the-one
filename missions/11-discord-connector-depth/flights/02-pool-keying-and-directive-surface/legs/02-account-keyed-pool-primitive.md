# Leg: account-keyed-pool-primitive

**Status**: landed
**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](../flight.md)

## Objective

Clean-break refactor of `the_one/connectors/_pool.py`: rename `acquire` → `agent_acquire` (MCP-style per-agent keying); rename `connector_acquire` → `account_acquire` (gateway-protocol account-keyed); DELETE `_CONNECTOR_POOL_AGENT_SENTINEL` from the module namespace (keep `"__connector__"` as an internal-only literal at a new private constant `_ACCOUNT_POOL_AGENT_SLOT` so the composite-key shape persists warm entries across deployment); add `_keys_for_test()` HAT inspection seam; update all 5 production call sites + 6 test files + docstring sweep + agents.md exemplar citation lockstep per `atomic-leg-pattern` (codified F1 L1).

## Context

- **Why now**: M10 F8 debrief critical action item #1 ("F1 pool keying needs proper refactor — Fix #6's sentinel-wrapper works but leaves the bare `pool_acquire(agent_name, account_id)` API as a footgun"). F1 debrief forward-looking §1 names this as F2 core work. F1 L1's `atomic-leg-pattern` is the contract for this refactor: every consumer site updates in one leg.
- **Why clean-break (not deprecation)**: Operator decision at F2 Phase 4 crew interview (recorded in `flight.md` Design Decisions §1). Single-user local tool; no external consumers; deprecation path preserves the footgun the M10 F8 debrief asked to remove.
- **`cross-subsystem-pattern-premise-revalidation` walk** (L1-codified F1, applied per F1 debrief Architect-checklist methodology): MCP's per-agent keying serves the F6 resolver pattern that legitimately produces different credentials per agent. Gateway connectors (Discord Gateway, Slack Socket Mode, ...) are one-IDENTIFY-per-token by physical necessity — per-agent keying would multiplex N agents onto N gateway WebSockets carrying the same token; Discord rejects the second IDENTIFY. F8 L11 Fix #6's sentinel-wrapper retrofitted account-keying onto a per-agent-keyed API; L2 fixes the structural mismatch by splitting the API surface into the two semantic primitives. MCP keeps `agent_acquire` (renamed from `acquire`); connectors get `account_acquire` (renamed from `connector_acquire`). Both primitives use ONE internal composite-key dict; the slot semantics are encoded in the call site, not the dict shape.
- **Why preserve `"__connector__"` as the slot literal**: deployments with warm pool entries in-memory at swap time would lose them if the literal changed (the composite-key tuple wouldn't match). Keeping the literal at the new private constant `_ACCOUNT_POOL_AGENT_SLOT` is a zero-disruption migration — the key shape is byte-identical to today's `(_CONNECTOR_POOL_AGENT_SENTINEL, account_id)` tuples. The PUBLIC API removes the sentinel; the INTERNAL slot literal stays.
- **No behavior change**: eviction, the reaper loop, the encryption-rotation invariant, and the cycle-2 race-fix invariant ALL walk the single composite-key dict uniformly. The two new primitives are call-site renames; the underlying storage and lifecycle machinery is unchanged.

## Inputs

Files that must exist (verified by exhaustive `grep -rn "connector_acquire\|_CONNECTOR_POOL_AGENT_SENTINEL" tests/ the_one/` at cycle-1 review):

**Production source (5 call sites + multiple imports)**:
- `the_one/connectors/_pool.py` (primary target — symbols at `:acquire`, `:connector_acquire`, `:_CONNECTOR_POOL_AGENT_SENTINEL`; storage at `:_pool`, `:_lock`, `:_shutting_down`)
- `the_one/connectors/_inbound.py` (3 call sites in `dispatch_inbound` body + 2 imports at top + 2 docstring references at lines 86, 121)
- `the_one/tools/connector_send.py` (1 call site at `:SendToPlatformChannelTool.execute` + 2 imports)
- `the_one/interfaces/web/app.py` (1 call site at `:lifespan` warm-up + function-local import)

**Tests with FUNCTIONAL code references (NOT docstring sweep — these touch runtime symbols and break at import/monkeypatch sites)**:
- `tests/test_connectors_pool.py` — multi-line import group at top of file
- `tests/test_connectors_e2e.py` — two import groups near top
- `tests/test_db_api.py` — 7 import sites + their call sites (count drifts; grep at impl time)
- `tests/test_connectors_inbound.py` — REAL CODE references: `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` at lines 351, 1411, 2601, 2682, 2688 (assertion-side); `monkeypatch.setattr(inbound_mod_local, "connector_acquire", ...)` at lines 2257-2267 (functional monkeypatch); plus docstring references at lines 1337, 2239, 2248, 2549-2550, 2666. Lines 2682-2688 also iterate pool keys filtering `if k[0] != pool_mod._CONNECTOR_POOL_AGENT_SENTINEL`.
- `tests/test_lifespan.py` — REAL CODE: `pool_mod.connector_acquire` getattr/setattr at lines 232, 238, 299, 303, 305; `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` assertion at line 253; docstring references at lines 154, 161, 164, 227-228.
- `tests/test_connectors_e2e_platform_send.py` — REAL CODE: `tool_mod.connector_acquire` getattr/setattr at lines 384, 390 (monkeypatch); `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` assertion at line 469; docstring references at lines 374, 377, 380, 396.

**Docstring sweep only (no runtime references)**:
- `tests/test_connector_send_tool.py` — confirmed at cycle-1 review: any references are doc-comment only
- `the_one/connectors/README.md`, `the_one/connectors/base.py`, `the_one/connectors/_session.py`, `the_one/agent/_context.py` — cross-reference docstring sweep

**`agents.md` citation update**:
- `the_one/agents.md:### \`cross-subsystem-pattern-premise-revalidation\`` — exemplar citation references `_pool.py:148 _CONNECTOR_POOL_AGENT_SENTINEL` AND `_pool.py:512-530 connector_acquire`. Updated by L2 to symbolic anchors reflecting post-refactor state: cite `the_one/connectors/_pool.py:agent_acquire` and `:account_acquire`. The F8 L11 historical framing stays; the symbol citations refresh.

State that must be true:
- L1 is `landed` (`optional-registry-entry-hook` + `registry-dispatch-create-mode-AC` codified — L2 doesn't reference them by name, but L4 will, so L1 must land first per dependency ordering)
- F2 branch `flight/02-pool-keying-and-directive-surface` checked out
- All F1 baseline tests pass at 2804

## Outputs

State changes after this leg:
- `the_one/connectors/_pool.py`:
  - `async def acquire(agent_name, account_id) -> ConnectorClient` renamed to `async def agent_acquire(agent_name, account_id) -> ConnectorClient`. Body unchanged (still uses the composite-key dict).
  - `async def connector_acquire(account_id) -> ConnectorClient` renamed to `async def account_acquire(account_id) -> ConnectorClient`. Body updated to use the new private slot constant: `return await agent_acquire(_ACCOUNT_POOL_AGENT_SLOT, account_id)`.
  - `_CONNECTOR_POOL_AGENT_SENTINEL = "__connector__"` REMOVED from the module namespace. Replaced with `_ACCOUNT_POOL_AGENT_SLOT = "__connector__"` (same literal value; new private name; not exported via `__all__` if any). The accompanying docstring/comment block is rewritten to reflect the post-refactor state — describes the slot semantics, explains why the literal value is preserved (warm-entry continuity), removes the "Fix #6 retrofit" framing.
  - NEW: `def _keys_for_test() -> list[tuple[str, str]]:` — returns `list(self._pool.keys())` (or `list(_pool.keys())` at module scope). Pure read; no lock acquisition needed for the snapshot semantics tests need. Test seam for L6 HAT verification step 8.
- `the_one/connectors/_inbound.py`:
  - Top-of-file imports: `from the_one.connectors._pool import acquire as pool_acquire` → `from the_one.connectors._pool import agent_acquire as pool_acquire` (alias preserved internally for minimal call-site churn IF the alias is currently used at any other call sites; otherwise just rename in place). `from the_one.connectors._pool import connector_acquire` → `from the_one.connectors._pool import account_acquire`.
  - 3 call sites: `connector_acquire(account_id)` → `account_acquire(account_id)`.
  - Module docstring (lines ~10-30) that names the pool API: scrub references to `connector_acquire` → `account_acquire`.
- `the_one/tools/connector_send.py`:
  - Imports: `from the_one.connectors._pool import acquire as pool_acquire` → `agent_acquire as pool_acquire` (or drop if unused); `from the_one.connectors._pool import connector_acquire` → `account_acquire`.
  - 1 call site at `SendToPlatformChannelTool.execute`: `connector_acquire(account_id)` → `account_acquire(account_id)`.
- `the_one/interfaces/web/app.py`:
  - Imports (function-local inside `lifespan`): `from the_one.connectors._pool import connector_acquire` → `account_acquire`.
  - 1 call site: `await connector_acquire(account.id)` → `await account_acquire(account.id)`.
- Tests:
  - `tests/test_connectors_pool.py` import group: `acquire, ...` → `agent_acquire, ...`. Pool-test scenarios that exercise `acquire` semantics retain their semantics — only the symbol name changes. Add new test cases: `test_account_acquire_routes_to_account_keyed_slot` (verifies `account_acquire(account_id)` produces a pool entry at `(_ACCOUNT_POOL_AGENT_SLOT, account_id)`), `test_keys_for_test_returns_current_keys` (verifies the new seam).
  - `tests/test_connectors_e2e.py` two import groups: rename.
  - `tests/test_db_api.py` 7 sites: rename `from the_one.connectors._pool import acquire` → `from the_one.connectors._pool import agent_acquire`, then update each call site.
  - `tests/test_connectors_inbound.py`, `tests/test_connector_send_tool.py`, `tests/test_lifespan.py`: docstring/comment sweep — scrub `acquire`/`connector_acquire` mentions to `agent_acquire`/`account_acquire`.
- Doc-comment cross-references in `the_one/connectors/README.md`, `the_one/connectors/base.py`, `the_one/connectors/_session.py`, `the_one/agent/_context.py`: scrub references to the old names.
- `the_one/agents.md` `### \`cross-subsystem-pattern-premise-revalidation\`` exemplar citation: update the cited symbol from `_pool.py:_CONNECTOR_POOL_AGENT_SENTINEL` to the historical framing (the sentinel was the F8 L11 retrofit; L2 of F2 split into two primitives), so future readers grep-find the convention's exemplar in the current code shape. Keep the F8 L11 + F2 L2 chronology visible.
- Anyone importing `acquire`, `connector_acquire`, OR `_CONNECTOR_POOL_AGENT_SENTINEL` from `the_one.connectors._pool` gets `ImportError`. Clean break per operator decision.

## Acceptance Criteria

- [ ] `the_one/connectors/_pool.py` exports `agent_acquire` and `account_acquire` (verified by `grep -n "^async def agent_acquire\|^async def account_acquire" the_one/connectors/_pool.py` returning exactly 2 hits).
- [ ] `_CONNECTOR_POOL_AGENT_SENTINEL` is NOT in `the_one/connectors/_pool.py` (verified by `grep -n "_CONNECTOR_POOL_AGENT_SENTINEL" the_one/connectors/_pool.py` returning zero hits).
- [ ] `_ACCOUNT_POOL_AGENT_SLOT = "__connector__"` is in `the_one/connectors/_pool.py` (verified by `grep -n "_ACCOUNT_POOL_AGENT_SLOT" the_one/connectors/_pool.py` returning at least 2 hits — the definition and the use inside `account_acquire`).
- [ ] `account_acquire(account_id)` produces an entry at `(_ACCOUNT_POOL_AGENT_SLOT, account_id)` — pinned by a new test `test_account_acquire_routes_to_account_keyed_slot` in `tests/test_connectors_pool.py`.
- [ ] `_keys_for_test()` exists and returns the current `list[tuple[str, str]]` of pool keys — pinned by a new test `test_keys_for_test_returns_current_keys`.
- [ ] Bare `acquire` and `connector_acquire` are NO LONGER exported — `python -c "from the_one.connectors._pool import acquire"` AND `python -c "from the_one.connectors._pool import connector_acquire"` BOTH raise `ImportError`. (Mechanical verification: `grep "from the_one.connectors._pool import \(acquire\|connector_acquire\)" -r the_one/ tests/` returns zero hits.)
- [ ] All 5 production call sites + imports updated lockstep:
  - `the_one/connectors/_inbound.py:dispatch_inbound` — 3 call sites + 2 imports + module docstring references at lines 86, 121.
  - `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute` — 1 call site + 2 imports.
  - `the_one/interfaces/web/app.py:lifespan` — 1 call site + function-local import.
- [ ] All test files with FUNCTIONAL code references updated lockstep (renames + monkeypatch updates, not just docstring):
  - `tests/test_connectors_pool.py` — import group renamed; new tests added for `account_acquire` + `_keys_for_test`.
  - `tests/test_connectors_e2e.py` — two import groups renamed.
  - `tests/test_db_api.py` — 7 import sites + their call sites renamed.
  - `tests/test_connectors_inbound.py` — code references at lines 351, 1411, 2257-2267 (monkeypatch), 2601, 2682, 2688 updated: `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` → `pool_mod._ACCOUNT_POOL_AGENT_SLOT`; `monkeypatch.setattr(inbound_mod_local, "connector_acquire", ...)` → `monkeypatch.setattr(inbound_mod_local, "account_acquire", ...)`; the local helper `_raising_connector_acquire` renamed for clarity (`_raising_account_acquire`); docstring references swept (lines 1337, 2239, 2248, 2549-2550, 2666).
  - `tests/test_lifespan.py` — code references at lines 232, 238, 253, 299, 303, 305 updated: `pool_mod.connector_acquire` → `pool_mod.account_acquire`; `original_connector_acquire` local rename → `original_account_acquire`; `monkeypatch.setattr(pool_mod, "connector_acquire", ...)` → `monkeypatch.setattr(pool_mod, "account_acquire", ...)`; `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` assertion → `pool_mod._ACCOUNT_POOL_AGENT_SLOT`; docstring references swept (lines 154, 161, 164, 227-228).
  - `tests/test_connectors_e2e_platform_send.py` — code references at lines 384, 390, 469 updated: `tool_mod.connector_acquire` getattr/setattr → `tool_mod.account_acquire`; `monkeypatch.setattr(tool_mod, "connector_acquire", _counting_acquire)` → `monkeypatch.setattr(tool_mod, "account_acquire", _counting_acquire)`; the `original_acquire = tool_mod.connector_acquire` local stays as `original_acquire` (variable name describes the cached reference, not the resolved symbol); `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` assertion → `pool_mod._ACCOUNT_POOL_AGENT_SLOT`; docstring references swept (lines 374, 377, 380, 396).
- [ ] Docstring sweep across `tests/test_connector_send_tool.py`, `the_one/connectors/README.md`, `the_one/connectors/base.py`, `the_one/connectors/_session.py`, `the_one/agent/_context.py` — no stale references remain (grep returns zero hits across these surfaces).
- [ ] `the_one/agents.md` `cross-subsystem-pattern-premise-revalidation` exemplar citation updated to reflect post-L2 state (the F8 L11 sentinel-wrapper is now historical; F2 L2 split into the two-primitive API). The convention's structural lesson stays; the citation chronology updates.
- [ ] Eviction, reaper, and encryption-rotation invariants unchanged — confirmed by full pool-test suite passing at or above F1's count (no regressions).
- [ ] Full suite `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` stays at or above F1's 2804-passed baseline (plus 2 new pool tests). Pre-existing R9 failures may persist; no new failures introduced by L2.

## Verification Steps

- `grep -rn "from the_one.connectors._pool import" the_one/ tests/` — every hit imports `agent_acquire`, `account_acquire`, or internal symbols (`_DEFAULT_TTL_SECONDS`, `_resolve_ttl_seconds`, `_reap_once`, `_RegistryEntry`, `shutdown_drain`, `_clear_for_test`). NO hits for `acquire`, `connector_acquire`, or `_CONNECTOR_POOL_AGENT_SENTINEL`.
- `grep -rn "connector_acquire\|_CONNECTOR_POOL_AGENT_SENTINEL" the_one/ tests/` (excluding the L2 leg artifact + flight-log) — zero hits.
- `grep -rn "pool_acquire" the_one/ tests/` — ZERO hits (the F8-era `acquire as pool_acquire` alias is dropped in L2 per cycle-1 reviewer suggestion + clean-break ethos).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py` — full pool-test suite passes; 2 new tests pinned (`test_account_acquire_routes_to_account_keyed_slot`, `test_keys_for_test_returns_current_keys`).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_e2e.py` — passes.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py` — passes (the 7 renamed import sites still resolve).
- `docker exec the-one pytest -x --timeout 30 tests/test_lifespan.py` — passes (lifespan warm-up uses `account_acquire`).
- `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite at or above 2804 + 2 new tests; zero new regressions.

## Implementation Guidance

1. **Read `the_one/connectors/_pool.py` end-to-end** (current ~570 LOC). The two functions to rename are at module-level; their bodies are unchanged. The sentinel comment block (currently lines ~122-148) is replaced wholesale with a shorter post-refactor docstring on `_ACCOUNT_POOL_AGENT_SLOT`.

2. **Enumerate all current `acquire` / `connector_acquire` consumers via grep BEFORE editing**:
   ```bash
   grep -rn "from the_one.connectors._pool import" the_one/ tests/
   grep -rn "connector_acquire\b" the_one/ tests/
   grep -rn "_CONNECTOR_POOL_AGENT_SENTINEL\b" the_one/ tests/
   ```
   Compare against the spec's expected sites. If any unexpected consumer surfaces, pause and re-scope.

3. **Refactor `_pool.py` in order**:
   - Replace the sentinel constant + its comment block (lines ~122-148) with `_ACCOUNT_POOL_AGENT_SLOT = "__connector__"` + a short docstring covering: (a) slot semantics (`"__connector__"` is a sentinel string occupying the per-agent slot when an entry is account-shared, not per-agent); (b) why the literal value is preserved (warm-entry continuity across deployment); (c) cite F2 L2 + F8 L11 chronologically.
   - Rename `acquire` → `agent_acquire` (function body unchanged).
   - Rename `connector_acquire` → `account_acquire` (function body: `return await agent_acquire(_ACCOUNT_POOL_AGENT_SLOT, account_id)`).
   - Add `def _keys_for_test() -> list[tuple[str, str]]: return list(_pool.keys())` after `_clear_for_test`.
   - Update the module-level docstring (top of file ~lines 1-50) to scrub references to the old names. Replace `:func:\`acquire\`` → `:func:\`agent_acquire\``; `:func:\`connector_acquire\`` → `:func:\`account_acquire\``.

4. **Update consumers in dependency order** (callers of the pool module first, then their tests):
   - **`the_one/connectors/_inbound.py`** — fix the two imports + 3 call sites. The `pool_acquire` alias on line 139 (currently `from the_one.connectors._pool import acquire as pool_acquire`) can stay as an alias against `agent_acquire` (`from the_one.connectors._pool import agent_acquire as pool_acquire`) IF the `pool_acquire` name is referenced elsewhere in the file — otherwise drop the alias and just rename.
   - **`the_one/tools/connector_send.py`** — same shape; 1 call site + imports.
   - **`the_one/interfaces/web/app.py:lifespan`** — function-local import + 1 call site.
   - **`tests/test_connectors_pool.py`** — multi-line import group at top; rename `acquire` → `agent_acquire`. Add 2 new tests at end of file:
     ```python
     async def test_account_acquire_routes_to_account_keyed_slot(...):
         """account_acquire produces a pool entry at (_ACCOUNT_POOL_AGENT_SLOT, account_id)."""
         # setup as the existing acquire tests do
         await account_acquire(account_id)
         keys = _keys_for_test()
         assert (_ACCOUNT_POOL_AGENT_SLOT, account_id) in keys

     async def test_keys_for_test_returns_current_keys(...):
         """_keys_for_test reflects the live pool state."""
         assert _keys_for_test() == []
         await agent_acquire("alice", account_id)
         await account_acquire(account_id)
         keys = set(_keys_for_test())
         assert ("alice", account_id) in keys
         assert (_ACCOUNT_POOL_AGENT_SLOT, account_id) in keys
     ```
   - **`tests/test_connectors_e2e.py`** — two import groups; rename.
   - **`tests/test_db_api.py`** — 7 import sites + their call sites; rename in lockstep.

5. **Functional code updates in test files** (NOT docstring sweep — these touch runtime symbols):
   - **`tests/test_connectors_inbound.py`** — five `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` references at lines 351, 1411, 2601, 2682, 2688 → `pool_mod._ACCOUNT_POOL_AGENT_SLOT`. One `monkeypatch.setattr(inbound_mod_local, "connector_acquire", _raising_connector_acquire)` at line 2267 → `monkeypatch.setattr(inbound_mod_local, "account_acquire", _raising_account_acquire)` (rename the local helper too). The key-iteration filter at lines 2682-2688 (`if k[0] != pool_mod._CONNECTOR_POOL_AGENT_SENTINEL`) becomes `if k[0] != pool_mod._ACCOUNT_POOL_AGENT_SLOT`. Docstring references at lines 1337, 2239, 2248, 2549-2550, 2666 swept to the new symbol names.
   - **`tests/test_lifespan.py`** — `pool_mod.connector_acquire` getattr at lines 232, 299 → `pool_mod.account_acquire`. `monkeypatch.setattr(pool_mod, "connector_acquire", _spying_acquire)` at lines 238, 305 → `monkeypatch.setattr(pool_mod, "account_acquire", _spying_acquire)`. Local `original_connector_acquire = pool_mod.connector_acquire` at lines 232, 299 — rename local to `original_account_acquire` for clarity (mirrors helper-naming convention in the same file). `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` assertion at line 253 → `pool_mod._ACCOUNT_POOL_AGENT_SLOT`. Docstring references at lines 154, 161, 164, 227-228 swept.
   - **`tests/test_connectors_e2e_platform_send.py`** — `tool_mod.connector_acquire` getattr at line 384 → `tool_mod.account_acquire`. `monkeypatch.setattr(tool_mod, "connector_acquire", _counting_acquire)` at line 390 → `monkeypatch.setattr(tool_mod, "account_acquire", _counting_acquire)`. `original_acquire = tool_mod.connector_acquire` local variable STAYS as `original_acquire` (the name describes the cached reference, not the resolved symbol — preserved for minimal diff). `pool_mod._CONNECTOR_POOL_AGENT_SENTINEL` assertion at line 469 → `pool_mod._ACCOUNT_POOL_AGENT_SLOT`. Docstring references at lines 374, 377, 380, 396 swept.

6. **Docstring sweep** (no runtime references): grep `the_one/connectors/README.md the_one/connectors/base.py the_one/connectors/_session.py the_one/agent/_context.py tests/test_connector_send_tool.py` for `acquire(agent_name`, `connector_acquire`, `_CONNECTOR_POOL_AGENT_SENTINEL`, `pool_acquire`. Update each occurrence to use the new symbol names. Preserve historical-context framing where applicable (e.g., `_session.py` may reference how the pool was extended in F8 L11 — that history is fine, but the symbol names should be current).

7. **Update `the_one/agents.md` `### \`cross-subsystem-pattern-premise-revalidation\``** exemplar citation. Current shape: `Citation: \`the_one/connectors/_pool.py\` — F1 mirrored \`mcp/_pool.py\`'s per-agent pool keying... Fix #6 shipped the sentinel-wrapper \`_CONNECTOR_POOL_AGENT_SENTINEL = "__connector__"\` at \`the_one/connectors/_pool.py:148\` and the convenience \`connector_acquire(account_id)\` at \`the_one/connectors/_pool.py:512-530\` as a tactical patch (call sites: \`the_one/tools/connector_send.py:194\`, \`the_one/connectors/_inbound.py:140\`). M11 F2 owns the proper refactor to an account-keyed primitive.` Replace with a post-L2 framing that (a) drops the line numbers per F1 debrief Recommendation §3 symbolic-anchor methodology; (b) preserves the F8 L11 historical lesson; (c) cites the post-refactor symbols. Suggested rewrite: `Citation: \`the_one/connectors/_pool.py\` — F1 mirrored \`mcp/_pool.py\`'s per-agent pool keying without re-validating the gateway-protocol-vs-MCP premise mismatch (gateway protocols are one-IDENTIFY-per-token; per-agent keying is incompatible). The mismatch surfaced at F8 L11 HAT seven flights after the original commit; Fix #6 shipped a sentinel-wrapper as a tactical patch. F2 L2 closed the convention's loop by splitting the public API into two semantic primitives: \`the_one/connectors/_pool.py:agent_acquire\` (MCP-style per-agent keying for the F6 resolver pattern) and \`the_one/connectors/_pool.py:account_acquire\` (gateway-protocol account-keyed, one entry per account). The proper refactor invoked this convention by name; the citation here documents both the original violation and the eventual resolution.`

8. **Remove the dead `pool_acquire` alias import in `_inbound.py` and `connector_send.py`** (per cycle-1 reviewer suggestion, operator agreement implied by clean-break ethos). Current: `from the_one.connectors._pool import acquire as pool_acquire` — the alias is imported but never called (the call sites use `connector_acquire` directly). The alias is dead code; clean break removes it. Drop the import line; the symbol is unused. Grep `pool_acquire` after the refactor — should return zero hits across `the_one/` and `tests/`.

9. **Run tests in order**:
   - `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py` — pool tests first (most direct).
   - `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py tests/test_connectors_e2e.py tests/test_connectors_e2e_platform_send.py tests/test_db_api.py tests/test_lifespan.py` — direct consumers (the three with functional code references run together to catch any rename misses early).
   - `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite final check.
   - If any test fails: diagnose. The clean-break shape means any failure is either (a) a missed call site (grep again), (b) a test that depends on the old symbol name (rename), or (c) a real behavior delta (would indicate the refactor changed pool semantics — should not happen since the body is byte-identical).

## Edge Cases

- **Aliased imports (`as pool_acquire`)**: existing `_inbound.py` and `connector_send.py` use `from ... import acquire as pool_acquire`. The alias can stay (`from ... import agent_acquire as pool_acquire`) for minimal call-site churn, OR be dropped to use `agent_acquire` directly. Reviewer's call at impl time; both shapes are correct.
- **Warm-entry continuity across deployment**: the literal `"__connector__"` is preserved at `_ACCOUNT_POOL_AGENT_SLOT`, so the composite-key tuples in any pre-deploy warm pool match the post-deploy key shape. No eviction churn at deployment. (In practice, deployments restart the process — the in-memory pool is empty at start. But the contract is documented for future zero-restart deploys.)
- **`connector_acquire` in flight-log entries from F1**: leg artifacts and flight-log entries from prior flights reference `connector_acquire`. These are historical records — DO NOT edit them. The grep verification step excludes the M11 mission folder explicitly.
- **Out-of-tree consumers**: operator confirmed clean break is acceptable; no external code imports these symbols. If any in-tree consumer was missed in the spec, grep will surface it at impl time — pause and re-scope.

## Files Affected

**Production source**:
- `the_one/connectors/_pool.py` — function renames (`acquire`→`agent_acquire`, `connector_acquire`→`account_acquire`) + sentinel→slot constant (`_CONNECTOR_POOL_AGENT_SENTINEL`→`_ACCOUNT_POOL_AGENT_SLOT`, literal value preserved) + new `_keys_for_test()` + docstring refresh
- `the_one/connectors/_inbound.py` — 2 imports + 3 call sites + module docstring at lines 86, 121
- `the_one/tools/connector_send.py` — 2 imports + 1 call site
- `the_one/interfaces/web/app.py` — function-local import + 1 call site at `:lifespan`

**Tests — functional code updates**:
- `tests/test_connectors_pool.py` — imports + 2 new tests (`test_account_acquire_routes_to_account_keyed_slot`, `test_keys_for_test_returns_current_keys`)
- `tests/test_connectors_e2e.py` — two import groups
- `tests/test_db_api.py` — 7 import sites + their call sites
- `tests/test_connectors_inbound.py` — code references at lines 351, 1411, 2257-2267 (monkeypatch), 2601, 2682, 2688 + docstring references at 1337, 2239, 2248, 2549-2550, 2666
- `tests/test_lifespan.py` — code references at lines 232, 238, 253, 299, 303, 305 + docstring references at 154, 161, 164, 227-228
- `tests/test_connectors_e2e_platform_send.py` — code references at lines 384, 390, 469 + docstring references at 374, 377, 380, 396

**Docstring sweep (no runtime references)**:
- `tests/test_connector_send_tool.py`, `the_one/connectors/README.md`, `the_one/connectors/base.py`, `the_one/connectors/_session.py`, `the_one/agent/_context.py`

**Doc citation update**:
- `the_one/agents.md` — `cross-subsystem-pattern-premise-revalidation` exemplar citation updated to symbolic anchors (`the_one/connectors/_pool.py:agent_acquire` + `:account_acquire`); F8 L11 historical framing stays

**Flight artifacts**:
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/02-account-keyed-pool-primitive.md` — status transitions

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All 5 production call sites + 6 test files (3 functional + 3 with code references) + all docstring sweep targets touched lockstep per `atomic-leg-pattern`
- [ ] `grep -rn "connector_acquire\|_CONNECTOR_POOL_AGENT_SENTINEL\b" the_one/ tests/` returns zero hits (excluding M11 mission folder)
- [ ] `python -c "from the_one.connectors._pool import acquire"` raises `ImportError`
- [ ] Full suite at or above F1 baseline (2804 + 2 new tests)
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off the leg in flight.md
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L1) — INCLUDES cycle-1 review's three additional file discoveries:

**Production source**:
- `the_one/connectors/_pool.py:acquire` (~lines 436-509) — verified function present; signature `(agent_name, account_id)`; body uses `_pool` composite-key dict.
- `the_one/connectors/_pool.py:connector_acquire` (~lines 512-530) — verified function present; body wraps `acquire(_CONNECTOR_POOL_AGENT_SENTINEL, account_id)`.
- `the_one/connectors/_pool.py:_CONNECTOR_POOL_AGENT_SENTINEL` (~line 148) — verified constant present with value `"__connector__"`.
- `the_one/connectors/_inbound.py` — verified 5 references total: 2 imports at top (lines 139-140, `acquire as pool_acquire` + `connector_acquire`), 3 call sites in `dispatch_inbound` body (lines 396, 433, 750), plus 2 module-docstring references at lines 86, 121.
- `the_one/tools/connector_send.py` — verified 2 imports (lines 37-38) + 1 `connector_acquire` call site at line 194 (`SendToPlatformChannelTool.execute`).
- `the_one/interfaces/web/app.py:lifespan` — verified function-local `from the_one.connectors._pool import connector_acquire` at line 136 + 1 call site at line 151 (`await connector_acquire(account.id)`).

**Tests — functional code references** (cycle-1 review found three files mis-characterized as docstring sweep):
- `tests/test_connectors_pool.py` — verified multi-line import group at top; existing tests exercise `acquire` semantics.
- `tests/test_connectors_e2e.py` — verified two `from the_one.connectors._pool import (...)` groups near top.
- `tests/test_db_api.py` — verified 7 `from the_one.connectors._pool import acquire` sites + 8 call sites (call-site count slightly exceeds import count because one import precedes 2 calls).
- `tests/test_connectors_inbound.py` — verified at cycle-1: code references at lines 351, 1411, 2257-2267 (monkeypatch + local `_raising_connector_acquire`), 2601, 2682, 2688 + docstring references at 1337, 2239, 2248, 2549-2550, 2666. **FUNCTIONAL code, not docstring-only** — fix at L2.
- `tests/test_lifespan.py` — verified at cycle-1: code references at lines 232, 238, 253, 299, 303, 305 (getattr/setattr + assertion) + docstring references at 154, 161, 164, 227-228. **FUNCTIONAL code** — fix at L2.
- `tests/test_connectors_e2e_platform_send.py` — **discovered at cycle-1** (missing from cycle-0 spec): code references at lines 384, 390, 469 (monkeypatch + assertion) + docstring references at 374, 377, 380, 396. **FUNCTIONAL code** — fix at L2.

**Docstring sweep only**:
- `tests/test_connector_send_tool.py`, `the_one/connectors/README.md`, `the_one/connectors/base.py`, `the_one/connectors/_session.py`, `the_one/agent/_context.py` — references are doc-comment only; no runtime symbols touched.

**Doc citation update**:
- `the_one/agents.md:### cross-subsystem-pattern-premise-revalidation` — verified exemplar citation references `_pool.py:_CONNECTOR_POOL_AGENT_SENTINEL` (with line numbers `:148` and `:512-530`). L2 updates this to use post-refactor symbolic anchors per F1 debrief Recommendation §3.

Thirteen citation clusters verified live against the post-F1 / pre-L2 tree, including the three test-file discoveries from cycle-1 review. No further drift.
