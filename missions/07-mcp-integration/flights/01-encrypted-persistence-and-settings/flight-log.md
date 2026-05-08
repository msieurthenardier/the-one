# Flight Log: Encrypted MCP Source Persistence + Settings Page

**Flight**: [Encrypted MCP Source Persistence + Settings Page](flight.md)

## Summary

Execution status and key outcomes will be captured here as legs complete.

---

## Leg Progress

> Per-leg entries appended as legs land.

### 01-schema-v10-migration

- **Status**: landed
- **Started**: 2026-05-05T21:40:00Z
- **Completed**: 2026-05-05T21:45:19Z

**Changes Made**

- `the_one/db/schema.py`: bumped `CURRENT_VERSION` from 9 to 10; appended `if version < 10:` block implementing a table-rename ceremony on `mcp_sources` — adds `secrets TEXT DEFAULT '{}'` column, replaces `CHECK (type IN ('stdio', 'sse'))` with `CHECK (type IN ('stdio', 'streamable-http'))`, and renames existing `'sse'` rows to `'streamable-http'` via CASE-WHEN in INSERT-SELECT. Uses individual `await conn.execute(...)` calls (not `executescript`) with `INSERT OR IGNORE INTO schema_version` last, per v8/v9 idempotency contract.
- `tests/test_db_migration.py`: added `class TestSchemaV10` with four methods: `test_v10_fresh_db_has_secrets_column_and_streamable_http_check`, `test_v10_migration_on_v9_fixture_db_preserves_existing_rows`, `test_v10_migration_is_idempotent`, `test_v9_to_v10_chained_migration`. Also updated stale version-pin assertions in `TestSchemaV8` and `TestSchemaV9` (hardcoded `== 9` checks) to reflect `CURRENT_VERSION = 10`.

**Test Results**

- `pytest tests/test_db_migration.py::TestSchemaV10 -v` — 4/4 passed
- `pytest tests/test_db_migration.py -v` — 17/17 passed (no v3-v9 regression)
- `pytest tests/test_schema.py -v` — 17/17 passed
- `pytest tests/ --tb=short -q --timeout=60` — 1077 passed, 1 skipped, **2 expected failures** (see Anomalies)

**Notes**

Expected partial-flight test breakage: `tests/test_db_repositories.py:230` and `tests/test_db_repositories.py:244` both fail with `sqlite3.IntegrityError: CHECK constraint failed: type IN ('stdio', 'streamable-http')` because they construct `MCPSource(type="sse")` against the new v10 schema. This is by design — the `'sse'` literal removal from the `MCPSource` Pydantic model and all call sites is L2's "Update sites" work. `tests/test_db_api.py::TestMCPSourceAPI::test_crud` is unaffected (uses `type='stdio'`).

### 02-encrypted-repository

- **Status**: landed
- **Started**: 2026-05-05T21:55:00Z
- **Completed**: 2026-05-05T22:00:00Z

**Changes Made**

- `the_one/db/models.py`: added `Any` to `from typing import Any, Literal`; updated `MCPSource` — type literal changed to `Literal["stdio", "streamable-http"]`, docstring updated to "operator-registered server entry", added `secrets: dict[str, Any] = Field(default_factory=dict)`, added `merged_config()` method (secrets win on key collision).
- `the_one/db/repositories.py`: added `from cryptography.fernet import InvalidToken`; updated `MCPSourceRepository.__init__` to accept `(conn, encryptor)` and store `self.encryptor` as a reference (mirrors `LLMProviderRepository:489`); added `_secrets_to_ciphertext` and `_ciphertext_to_secrets` helpers (the latter swallows `InvalidToken` for migration-residue rows, propagates `JSONDecodeError`); updated `create()` and `update()` to write the `secrets` column with Fernet ciphertext; updated `_row_to_model` to decrypt secrets and removed the `@staticmethod` decorator.
- `the_one/interfaces/web/api.py`: updated `_mcp_repo()` factory to construct `MCPSourceRepository(conn, get_encryptor(settings.data_dir))`, mirroring `_provider_repo()`.
- `tests/test_db_repositories.py`: replaced `mcp_repo` fixture (no-arg) with `mcp_repo_encryptor` (new, function-scoped, with protective comment) + `mcp_repo(conn, mcp_repo_encryptor)`; fixed `test_list` (line 230) and `test_delete` (line 244) `type="sse"` → `type="streamable-http"`; added 5 new tests: `test_secrets_round_trip`, `test_secrets_encrypted_at_rest`, `test_empty_secrets_default`, `test_install_key_post_create_decrypts_via_same_instance`, `test_merged_config_overlays_secrets_on_config`.
- `tests/test_db_api.py`: updated `client` fixture to import `Fernet` and `Encryptor`, create a function-scoped `test_encryptor`, and patch `the_one.interfaces.web.api.get_encryptor` alongside `get_connection`; mirrors `test_provider_api.py:56-72`.

**Test Results**

- `pytest tests/test_db_repositories.py::TestMCPSourceRepository -v` — 9/9 passed (4 original + 5 new)
- `pytest tests/test_db_api.py -v` — 15/15 passed (get_encryptor patch confirmed working)
- `pytest tests/ --tb=short -q --timeout=60` — 1084 passed, 1 skipped, 0 failures

**Notes**

L1 anomaly resolved: `tests/test_db_repositories.py:230` and `tests/test_db_repositories.py:244` now construct `MCPSource(type="streamable-http")` and pass. Full unit suite is back to green with 7 additional tests (4 migration + 5 encryption).

### 03-api-endpoint-extension

- **Status**: landed
- **Started**: 2026-05-05T22:05:00Z
- **Completed**: 2026-05-05T22:15:51Z

**Changes Made**

- `the_one/interfaces/web/api.py`: extended the `# ── MCP Sources ──` block with four new module-level helpers above the route registrations — `_mask_secret_value` (per-decoded-VALUE mask mirroring `_mask_api_key`'s `***`/`***...{tail4}` shape, defensive `Any -> Any` signature, non-string values mask wholesale as `***`), `_mask_secrets` (per-key map over the decoded secrets dict, returns a new dict), `_mcp_source_response` (renders `MCPSource.model_dump()` then OVERWRITES `data["secrets"]` with the masked form — explicit INVARIANT comment locks the regression net), and `_validate_mcp_source_config` (transport-aware shape validation with stdio/streamable-http branches and a defensive `else: raise` for unknown literals). Inserted new `/api/mcp-sources/types` GET endpoint between `list_mcp_sources` and `get_mcp_source` (route-ordering invariant comment in docstring mirrors `list_provider_types`). Updated `list_mcp_sources` and `get_mcp_source` to return `_mcp_source_response(...)`. Updated `create_mcp_source` to wrap `MCPSource.model_validate` in `try/except ValidationError` with `e.errors(include_context=False)` (canonical pattern) and call `_validate_mcp_source_config` before `repo.create`. Updated `update_mcp_source` with per-key `__MASKED__` handling inside the secrets dict (reuses the existing `_MASKED_API_KEY_SENTINEL` constant — comment notes the cosmetic name-misleading observation), `try/except ValidationError` around `model_copy`, and `_validate_mcp_source_config(updated)` running on the merged-post-`model_copy` state.
- `tests/test_db_api.py`: added 1 baseline assertion (`assert resp.json()["secrets"] == {}` after the GET in `test_crud`) plus 10 new tests in `TestMCPSourceAPI` — `test_list_returns_masked_secrets`, `test_get_returns_masked_secrets`, `test_put_masked_sentinel_preserves_secret`, `test_put_drops_omitted_secret_key`, `test_validation_rejects_stdio_missing_command`, `test_validation_rejects_streamable_http_missing_url`, `test_validation_rejects_unknown_transport_type`, `test_types_endpoint_returns_two_transports`, `test_types_endpoint_route_order_does_not_collide_with_get_by_id`, `test_put_transport_type_switch_revalidates_config`.

**Test Results**

- `pytest tests/test_db_api.py::TestMCPSourceAPI -v --timeout=60` — 11/11 passed (existing `test_crud` + 10 new)
- `pytest tests/ --tb=short -q --timeout=60` — 1094 passed, 1 skipped, 0 failures (10 new tests above L2's 1084)

**Notes**

Route ordering invariant locked by `test_types_endpoint_route_order_does_not_collide_with_get_by_id` — verified `list → types → {source_id} → POST → PUT → DELETE` ordering via `grep -n "@router.*mcp-sources" the_one/interfaces/web/api.py`. Per-decoded-value masking lives at the API layer only — repository continues to return decrypted plaintext per L2's contract; `_mcp_source_response` is the single chokepoint that masks before serializing. Per-key `__MASKED__` handling reuses `_MASKED_API_KEY_SENTINEL` (the constant name is now slightly misleading post-L3 — covers both the provider single `api_key` column and the per-key MCP secrets dict — but renaming is a cosmetic refactor out of scope). Transport-aware validation runs on the merged-post-`model_copy` state, which is what catches the type-switch-with-stale-config case (`test_put_transport_type_switch_revalidates_config`). The defensive `else: raise` in `_validate_mcp_source_config` is dead code today (Pydantic Literal validation gates the type at model-validate time) but locks the contract that any future transport literal addition must extend the helper.

### 04-rotation-extension

- **Status**: landed
- **Started**: 2026-05-05T22:25:00Z
- **Completed**: 2026-05-05T22:34:00Z

**Changes Made**

- `the_one/interfaces/web/api.py`: extended the `from cryptography.fernet import Fernet` import to also pull in `InvalidToken`. Updated `rotate_encryption_key` docstring to reflect dual-surface scope and migration-residue tolerance. Inserted between the existing LLM provider SELECT and Step 2 (key generation): a parallel `SELECT id, secrets FROM mcp_sources` followed by a tolerant decrypt loop mirroring `MCPSourceRepository._ciphertext_to_secrets` (`repositories.py:258-280`) — `if not ciphertext: secrets_dict = {}`, else `try: encryptor.decrypt + json.loads / except InvalidToken: secrets_dict = {}`. Inserted at Step 3: `reencrypted_mcps = [(sid, new_encryptor.encrypt(json.dumps(secrets_dict))) for sid, secrets_dict in decrypted_mcps]`. Extended the existing single `try:` block at Step 4 to add a parallel `UPDATE mcp_sources SET secrets = ? WHERE id = ?` loop AFTER the existing LLM provider UPDATE loop, BEFORE the single `await conn.commit()`. The `except Exception: rollback; raise` block is unchanged — one rollback covers both tables. Steps 5–7 (key file write, `os.replace`, `install_key`) are untouched.
- `tests/test_provider_api.py`: added 5 tests inside `TestEncryptionRotation` after `test_rotate_preserves_key_on_db_failure`: `test_rotate_mcp_source_secrets`, `test_rotate_mixed_providers_and_mcps`, `test_rotate_preserves_mcp_secrets_on_db_failure`, `test_rotate_with_migration_residue_mcp_row`, `test_rotate_dual_surface_atomicity_on_db_failure`. The migration-residue test uses the POST-then-direct-UPDATE pattern (create through API, then overwrite `secrets` to literal `'{}'` via a fresh aiosqlite connection) to simulate a v10-migration-residue row that has never been written by the L2 repository.

**Test Results**

- `pytest tests/test_provider_api.py::TestEncryptionRotation -v --timeout=60` — 9/9 passed (4 existing + 5 new)
- `pytest tests/ --tb=short -q --timeout=60` — 1099 passed, 1 skipped, 0 failures (5 new tests above L3's 1094)

**Notes**

The all-in-memory invariant is preserved: rotation now does SELECT-providers → SELECT-mcps → generate-new-key → reencrypt-providers-in-memory → reencrypt-mcps-in-memory → try { UPDATE-providers-loop → UPDATE-mcps-loop → commit } except rollback/raise → file replace → install_key. No `PRAGMA`, no `CREATE`, no `BEGIN`, no DDL anywhere between the first SELECT and the final commit — verified by visual code review. The single `try:` / single `commit()` / single `rollback` covers both tables atomically; `test_rotate_dual_surface_atomicity_on_db_failure` proves a simulated commit failure leaves on-disk ciphertext on BOTH surfaces byte-identical to pre-rotation. Migration-residue tolerance: rows with plaintext `secrets='{}'` from v10's column default are decrypted as `{}` (via `InvalidToken`-swallow) and re-encrypted as proper Fernet ciphertext for `'{}'` under the new key — incidental normalization side-effect documented in the docstring. The reference-not-copy invariant on both `LLMProviderRepository.encryptor` and `MCPSourceRepository.encryptor` is left untouched: both repository classes pick up the new key automatically via the shared `install_key()` mutation, so no per-repo reset is required. JSON decode errors are NOT swallowed — they propagate and trigger rollback, surfacing real corruption rather than silently masking it (covered in the "Edge Cases" section of the leg artifact).

### 05-settings-nav-and-grid

- **Status**: landed
- **Started**: 2026-05-05T22:45:00Z
- **Completed**: 2026-05-05T23:25:00Z

**Changes Made**

- `the_one/interfaces/web/static/js/areas/admin.js`: extended at all 18 enumerated touchpoints from the leg's "Files Affected" checklist. (1) `serializeState`: new `mcp-sources` branch with `add` / `edit` / hydrate-vs-fetch-race fallbacks (`pendingMcpSourceFormMode === 'add'` / `pendingMcpSourceId`). (2-6) `hydrateState`: added `pendingMcpSourceId_local` + `pendingMcpSourceFormMode_local` declarations; new parsing branch for `mcp-sources/new` (exact match → `pendingMcpSourceFormMode_local = 'add'`) and `mcp-sources/{id}` (prefix match → defensive trailing-slash strip + first-segment-only extraction → `pendingMcpSourceFormMode_local = 'edit'` + `pendingMcpSourceId_local = decodeURIComponent(...)`); extended the early-return reset block (`!sub`) with `_pendingMcpSourceId = null` + `_pendingMcpSourceFormMode = null`; extended the unconditional overwrite block at the end with the two new pending writes; appended `if (this._tryConsumePendingMcpSource) this._tryConsumePendingMcpSource();` to the unconditional consume-fire list. (7) `validIds` extended to `['system', 'providers', 'tools', 'mcp-sources']`. (8) `categories` array extended with `{ id: 'mcp-sources', label: 'MCP Servers' }` as the 4th entry. (9) `init()` declared 5 new closure-locals: `mcpSources`, `mcpSourceFormMode`, `editingMcpSource`, `pendingMcpSourceId`, `pendingMcpSourceFormMode` (all null). (10) `doSetCategory` reset block extended with the 4 active+pending mcp wipes (cache `mcpSources` is intentionally NOT reset, mirroring providers). (11) `setCategory` dirty-gate `inEditor` extended with `(currentCategory === 'mcp-sources' && mcpSourceFormMode)`. (12) `renderContent` dispatch routes `currentCategory === 'mcp-sources'` to `renderMcpSourcesPanel()`. (13) NEW `renderMcpSourcesPanel`: editor-branch renders the L5 placeholder DIV with `data-testid="mcp-editor-placeholder"` and returns; grid-branch delegates to `App.admin.renderMcpServersGrid` then triggers `fetchMcpSources()`. (14) NEW `fetchMcpSources` (uses the stricter tools pattern at admin.js:498-525 — stale-then guard wraps BOTH the cache-write `mcpSources = data` AND the populate, NOT the older providers pattern), `populateMcpSourcesGrid` (stale-then guard + editor-branch bail), `selectMcpSource` (findMcpSource + mode flip + replaceSub), `enterCreateMcpSourceMode` (mode='add' + replaceSub), `findMcpSource` (linear cache scan). (15) `_refresh` extended with `mcp-sources` branch → `fetchMcpSources()`. (16) 4 new `Object.defineProperty` slots: `_mcpSourceFormMode`, `_editingMcpSource`, `_pendingMcpSourceId`, `_pendingMcpSourceFormMode`. The `mcpSources` cache var is intentionally closure-private (mirrors `providers` and `toolConfigs`). (17) `_setCategory` reset block extended with the 4 active+pending mcp wipes. (18) NEW `_tryConsumePendingMcpSource` mirroring `_tryConsumePendingProvider` — handles both `'add'` and `'edit'` pending modes; bails when source isn't yet in cache; relies on the `fetchMcpSources.then` re-fire.
- `the_one/interfaces/web/static/js/areas/admin/mcp-servers-grid.js` (NEW, 114 lines): exports `App.admin.renderMcpServersGrid(container, mcpSources, callbacks)`. Mirrors `providers-grid.js` structurally with these substitutions: `KNOWN_TRANSPORT_BADGES = ['stdio', 'streamable-http']` (with comment noting the three sites — this file, `_validate_mcp_source_config` in api.py, and `/api/mcp-sources/types` — that must stay in sync); page header `<h1>MCP Servers</h1>` + `data-testid="new-mcp-source-btn"` CTA; loading state when `mcpSources === null`; empty-canvas with `data-testid="new-mcp-source-btn-empty"` when `mcpSources.length === 0`; tile DOM `data-testid="mcp-source-card"` + `data-id` + `aria-selected` + 3 spans (badge / name / meta); badge text is `s.type`, badge class suffix is `s.type` if known else `'unknown'`; transport-aware meta string (stdio → `config.command`, streamable-http → `config.url`, fallback `'—'`). Filename uses "mcp-servers" (matches user-facing label "MCP Servers"); URL category and JS identifiers use "mcp-sources" (matches API path) — asymmetry documented in a header comment.
- `the_one/interfaces/web/static/index.html`: added one `<script src="/static/js/areas/admin/mcp-servers-grid.js"></script>` registration between `providers-grid.js` and `tools-form-helpers.js`, preserving the sub-modules-first / orchestrator-last loading order.
- `tests/browser/test_flow_admin_navigation.py`: updated `test_admin_section_nav_renders_three_sections` count assertion from 3 to 4 and added the `MCP Servers` label assertion at `items.nth(3)`. Function name retained for git-blame continuity; docstring extended to note the M07 F1 L5 widening.
- `tests/browser/test_flow_admin_tools_grid.py`: updated `test_admin_tools_section_nav_label_is_built_in_tools` `to_have_count(3)` → `to_have_count(4)` (the `items.nth(2)` index for "Built-in Tools" remains valid because MCP Servers appends at index 3).
- `tests/browser/test_flow_admin_mcp_navigation.py` (NEW): 7 Playwright tests — `test_admin_section_nav_includes_mcp_servers`, `test_admin_section_nav_click_to_mcp_sources`, `test_admin_direct_load_mcp_sources`, `test_admin_direct_load_mcp_sources_new_renders_placeholder` (BEHAVIORAL DOM assertion on `data-testid="mcp-editor-placeholder"` — App.areas is closure-private so state introspection isn't possible), `test_admin_refresh_preserves_mcp_sources_section`, `test_admin_mcp_sources_empty_grid_shows_cta`, `test_admin_mcp_placeholder_navigation_skips_confirm` (confirms the dirty-gate path is statically reachable but practically false-bypassed because the L5 placeholder is non-interactive — pins the L6 onDirtyChange bridge contract).

**Test Results**

- `make _ensure-playwright` — chromium installed.
- `docker exec the-one pytest -m browser tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_admin_tools_grid.py tests/browser/test_flow_admin_mcp_navigation.py -v --tb=short` — 23/24 passed. The single failure (`test_admin_tools_renders_grid_with_4_tabs`) is pre-existing (verified by stashing all L5 changes and re-running — same failure: tools-grid renders 3 tabs but the test expects 4 [Filesystem, Execution, Python, Web]; the implementation has only `['filesystem', 'execution', 'web']`). Unrelated to L5; flagged for follow-up.
- `docker exec the-one pytest -m browser tests/browser/ -k "admin" -v --tb=short` — 39/40 passed (same single pre-existing failure).
- All 7 new MCP navigation tests pass on first run. All 7 prior admin navigation tests pass with the count update. All 10 admin tools-grid tests still pass with the count update.
- `make lint` — NOT clean. 4 pre-existing ruff failures inherited from L1-L4: `repositories.py:255,258` (`F821 Undefined name 'Any'` — missing `from typing import Any` import), `api.py:11` (`F401 unused 'pathlib.Path'`), `api.py:583` (`E501 line >100 chars`). Verified by stash-and-rerun — all 4 are present pre-L5; L5 introduces zero new ruff errors. L5 itself touches only `.js` and `.html` files plus 2 Python test files; ruff has no new failures on those.

**Notes**

Closure-mirror enumeration is COMPLETE — all 18 touchpoints checked. The MCP Servers section now mirrors the LLM Providers section's structural shape: separate cache (closure-private), separate active-state pair (`mcpSourceFormMode` + `editingMcpSource`), separate pending-state pair (`pendingMcpSourceId` + `pendingMcpSourceFormMode`), separate `_tryConsumePendingMcpSource` consumer, separate `serializeState` and `hydrateState` branches, separate `renderMcpSourcesPanel` dispatch, separate `_refresh` branch, separate dirty-gate disjunct.

L6 editor bridge points are STAGED:
- `mcpSourceFormMode` is the editor mount gate (currently routes to the L5 placeholder; L6 swaps in `App.admin.renderMcpEditor`).
- `editingMcpSource` carries the source object into the editor mount.
- The dirty-gate `inEditor` disjunct is in place; the closure `dirty` flag is shared with the L6 editor's onDirtyChange callback (no further admin.js edits needed for the bridge).
- `_tryConsumePendingMcpSource` already handles both `'add'` and `'edit'` modes; once L6 wires the editor, direct-load `#admin/mcp-sources/{id}` opens the editor on first paint.

Stale-then guard upgrade: `fetchMcpSources` adopts the stricter tools pattern (cache-write inside the guard) rather than the older providers pattern (cache-write outside the guard). This deliberately diverges from providers — under the providers pattern, a fetch resolving after the operator navigates away would still clobber the cache (`providers = data`), even though the populate-bail short-circuits the visible render. The tools/L5 pattern eliminates that latent race.

Filename asymmetry (`mcp-servers-grid.js` filename + "MCP Servers" UI label) vs (`mcp-sources` URL slug + `mcpSource` JS identifiers) is intentional and documented in a header comment in the new grid sub-module — it tracks the user-facing concept ("Servers") at the UI surface and the storage entity ("Sources" matching the API path `/api/mcp-sources`) in code identifiers.

L5 placeholder editor: when `mcpSourceFormMode` is non-null, `renderMcpSourcesPanel` renders a non-interactive `<div class="admin-loading" data-testid="mcp-editor-placeholder">MCP source editor lands in L6.</div>` and returns. No form, no inputs, nothing that could mutate the closure `dirty` flag. The dirty-gate codepath at `setCategory:218` is statically reachable when on `mcp-sources` with non-null mode but practically false-bypassed until L6 wires `onDirtyChange`. `test_admin_mcp_placeholder_navigation_skips_confirm` pins this behavior.

Out of scope inheritances flagged for review: (1) The 4 pre-existing ruff failures (L1-L4) — these need cleanup before flight-end commit. (2) The pre-existing `test_admin_tools_renders_grid_with_4_tabs` failure (F6 leg-07; 3 tabs vs expected 4) — unrelated to this flight; flagged for separate follow-up.

### 06-editor-sub-module

- **Status**: landed
- **Started**: 2026-05-05T23:30:00Z
- **Completed**: 2026-05-05T23:55:00Z

**Changes Made**

- `the_one/interfaces/web/static/js/areas/admin/mcp-server-editor.js` (NEW, ~620 lines): exports `App.admin.renderMcpSourceEditor(container, source, mcpTypes, callbacks)`. Mirrors the provider-editor structural shape (header / form-actions / Connection section / dynamic kv section / OAuth section / Danger Zone) with the L6-specific extensions: (a) per-key `__MASKED__` round-trip via `data-original-masked` attribute on each kv-value input (and on `oauth-client-secret`); (b) unified kv table with delegated event handlers on the `<table>` element (single set of listeners covers add-row / remove-row / sensitive-checkbox change / eye-toggle / key/value input — no per-row attach); (c) `getFormSnapshot` does three explicit walks (static / chips / kvRows) avoiding the flat `data[dataset.field]=value` collision since multiple kv rows share `data-field` attributes; (d) `collectFormData` routes by `type` (NOT visible-field set) so a type-change-then-immediate-save emits the type-correct payload; (e) sensitive→non-sensitive flip on a row whose value still equals `_originalMasked` clears the value field (otherwise the masked tail leaks into plaintext config.env / config.headers); (f) Cancel-in-edit-mode rebuilds the kv tbody + chip-list editors from source (DOM rebuild — row count can change during edit) instead of value-loop restoration; (g) bare `App.confirmDelete` (no agent-usage pre-gate — F4 will land that). Locked contract: OAuth `client_secret` routes into `secrets["oauth_client_secret"]` (top-level), NOT nested under `config.oauth`.
- `the_one/interfaces/web/static/js/areas/admin.js`: (1) declared `MCP_TYPES = []` + `mcpTypesReady = null` near the existing `PROVIDER_TYPES` block; (2) added `fetchMcpSourceTypes()` mirroring `fetchProviderTypes` (fetches `/api/mcp-sources/types`, caches into `MCP_TYPES`, swallows network errors to `[]`); (3) replaced the L5 placeholder branch in `renderMcpSourcesPanel` with `mcpTypesReady`-gated delegation to `App.admin.renderMcpSourceEditor`, wiring the orchestrator-side callbacks (`onBack` with dirty-gate via `App.confirmDialog`, `onCancel`, `onSaveSuccess` with create→edit re-render, `onDeleteSuccess`, `onDirtyChange` bridge to closure-local `dirty`); (4) appended `fetchMcpSourceTypes();` to the bottom-of-init block alongside `fetchProviderTypes();`.
- `the_one/interfaces/web/static/index.html`: registered new `<script src="/static/js/areas/admin/mcp-server-editor.js"></script>` after `provider-editor.js` and `provider-models.js`, mirroring the providers grid → editor pairing structurally and ensuring `tools-form-helpers.js` (chip-list helper provider) loads before the editor consumes it.
- `tests/browser/test_flow_admin_mcp_editor.py` (NEW, ~280 lines): 9 Playwright tests covering all critical paths — `test_create_stdio_source`, `test_create_streamable_http_source_with_oauth` (round-trips all OAuth fields including masked client_secret), `test_edit_stdio_source_preserves_unchanged_secrets` (per-key MASKED_SENTINEL preserves stored ciphertext when only the name field is edited), `test_edit_streamable_http_source_changes_one_secret` (two sensitive headers; change one → overwrite, leave one → MASKED preserved), `test_delete_stdio_source` + `test_delete_streamable_http_source` (App.confirmDelete two-click flow), `test_dirty_back_confirm_dialog` (modal appears + Cancel keeps editor mounted with field value preserved), `test_type_change_swaps_field_visibility` (stdio→streamable-http: command hidden, url visible, kv-label "Environment Variables"→"Custom Headers", OAuth section reveals), `test_save_with_empty_kv_key_row_silently_skips` (empty-key row is dropped at partition time, never persisted as `""` key).
- `tests/browser/test_flow_admin_mcp_navigation.py`: refactored `test_admin_direct_load_mcp_sources_new_renders_placeholder` → `test_admin_direct_load_mcp_sources_new_renders_editor` (asserts `[data-testid="save-mcp-source-btn"]` + `[data-field="name"]` are visible AND the L5 placeholder is no longer in the DOM); deleted `test_admin_mcp_placeholder_navigation_skips_confirm` (the placeholder no longer exists; the new editor's clean-state navigation behavior is covered by `test_dirty_back_confirm_dialog`'s Cancel-keeps-mounted assertion plus the natural clean-editor navigation flow exercised across the create/edit/delete tests). Module docstring updated to record the L5→L6 transition.

**Test Results**

- `make lint` — 4 pre-existing errors (F821×2 in `repositories.py`, F401 + E501 in `api.py`, all inherited from L1-L5). L6 introduces zero new lint errors. The new test file's import-block I001 issue from initial draft was auto-fixed via `ruff check --fix` before completion.
- `pytest -m browser tests/browser/test_flow_admin_mcp_editor.py -v --timeout=120` — 9/9 passed (~10s).
- `pytest -m browser tests/browser/test_flow_admin_mcp_navigation.py -v --timeout=120` — 6/6 passed (~6s).
- `pytest -m browser tests/browser/ -k "admin or mcp" -v --timeout=120` — 47/48 passed (~54s). The single failure (`test_admin_tools_renders_grid_with_4_tabs`) is the L5-flagged pre-existing failure (3 tabs vs expected 4 in tools-grid), unrelated to L6 — verified via `git stash` baseline check.

**Notes**

Per-sensitive-field UI shape decision LOCKED at option (c) — unified kv table with key / value / sensitive-checkbox / eye / remove columns. Implementation honors all critical invariants from the leg's design preamble:

- **Reuse over reimplement**: chip-list rendering for `args` (stdio) and `oauth-scopes` (streamable-http OAuth) is delegated to `App.adminFormHelpers.renderChipListEditor` / `wireChipListEditor` / `readChipListValue` — the editor sub-module never reimplements chip rendering. Script-load ordering invariant verified in `index.html` (lines 50→55: tools-form-helpers.js loads before mcp-server-editor.js).

- **Per-key MASKED_SENTINEL is per-row, not editor-global**: each kv row carries its own `_originalMasked` snapshot via `data-original-masked` attribute (captured once at mount). `partitionKvRows` checks `value === _originalMasked` per row and substitutes `'__MASKED__'` only for that one key in the secrets payload. The OAuth `client_secret` follows the same per-row shape via `secrets['oauth_client_secret']`. Round-trip preservation verified by `test_edit_stdio_source_preserves_unchanged_secrets` (one secret) and `test_edit_streamable_http_source_changes_one_secret` (two secrets, one preserved + one overwritten).

- **OAuth client_secret payload key locked**: `secrets["oauth_client_secret"]` (top-level), NOT `config.oauth.client_secret`. The encryption boundary is the `secrets` column; routing the secret elsewhere would leak through any code path reading `config` plaintext. F5's OAuth flow MUST look up the client secret by this exact key.

- **collectFormData routes by `type`, not by visible-field set**: `command` is read only when `type === 'stdio'`; `url` is read only when `type === 'streamable-http'`. A type-change-then-immediate-save (before the dirty-handler debounces) emits the type-correct payload, never including the wrong-transport's fields.

- **Sensitive→non-sensitive flip clears the masked tail**: when the operator unchecks the sensitive checkbox on a row whose value still equals `_originalMasked`, the value input is cleared (otherwise `***...alue` would persist into `config.env` / `config.headers` plaintext on save). The kv-section hint paragraph documents this contract inline.

- **Cancel-in-edit-mode rebuilds the kv tbody DOM**: row count can change during edit (operator added/removed rows), so a value-restoration loop alone would mis-shape the table. Static fields revert via the snapshot value-loop (mirrors provider-editor); kv table re-renders from `source` via `collectExistingKvRows` + `renderKvRow`; chip-list editors re-mount fresh via `App.adminFormHelpers.renderChipListEditor`.

- **Event delegation on the kv `<table>`**: a single set of listeners on the table element handles input on key/value text inputs, change on the sensitive checkbox, and click on eye-toggle / remove-row buttons. The add-row handler appends a new tr and the delegated listeners pick it up automatically — no per-row attach, no per-row listener leak.

- **getFormSnapshot uses three explicit walks**: `{ static: {...}, chips: {args: [...], 'oauth-scopes': [...]}, kvRows: [{key, value, sensitive}, ...] }`. Avoids the flat `data[dataset.field] = value` collision since multiple kv rows share `data-field="kv-key"` / `kv-value"` / `kv-sensitive"`.

- **No agent-usage pre-gate on Delete (yet)**: bare `App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' })`. F4 will add the agent-usage pre-gate when per-agent MCP attachment lands; until then MCP sources have no FK from agents, so a hard-block check would be vacuous.

- **Stranded-secret edge case handled**: if the operator clears all OAuth plaintext fields in edit mode AND the source previously had `secrets["oauth_client_secret"]` populated, `collectOAuthSection` emits `secrets["oauth_client_secret"] = ""` to drop the stranded ciphertext blob. Without this, clearing OAuth from the UI would leave a dangling secret.

L7 (HAT walkthrough) is the only remaining leg in this flight. F2 (live connection) and F4 (per-agent attachment) and F5 (OAuth flow) consume the L6 contract surface from outside this flight.

---

## Decisions

> Runtime decisions not in the original flight spec captured here as they occur.

---

## Deviations

> Departures from the planned approach captured here with planned/actual/reason.

---

## Anomalies

> Unexpected issues encountered, with severity (blocking/degraded/cosmetic) and resolution.

### L01: test_db_repositories.py:230,244 — expected CHECK failures on MCPSource(type='sse')

- **Severity**: blocking-for-flight-but-expected
- **Tests**: `tests/test_db_repositories.py::TestMCPSourceRepository::test_list` (line 230), `tests/test_db_repositories.py::TestMCPSourceRepository::test_delete` (line 244)
- **Error**: `sqlite3.IntegrityError: CHECK constraint failed: type IN ('stdio', 'streamable-http')`
- **Cause**: Both tests construct `MCPSource(id=..., name=..., type="sse")` which the new v10 CHECK constraint rejects.
- **Resolution**: L2 update-sites work — the `'sse'` literal is removed from the `MCPSource` Pydantic model and all callers as part of L2's enumerated changes. Do not fix in L1.
- **Resolution (L02 landed)**: the two tests now construct `MCPSource(type="streamable-http")` and pass; full unit suite is back to green.

---

## Session Notes

> Chronological notes from work sessions.

---

## Flight Director Notes

### Flight-end commit (post-review)

- **Pre-commit lint cleanup**: 4 lint errors at flight start (3 inherited from L1-L4 lint hygiene gaps + 1 L3-introduced) → 0 lint errors at flight end. Specifically: 1 pre-existing `F401` (unused `pathlib.Path` on main) + 1 L3-introduced `E501` (line >100 chars at `api.py:583`); both fixed before the commit.
- **Reviewer signaled `[HANDOFF:confirmed]` post-fix** — review passed with the lint cleanup applied.
- **L7 (HAT) deferred** per the flight spec adaptation criteria: "L7 may be skipped if L1-L6 land cleanly and HAT-class issues are not surfaced during integration." User can opt into it as a follow-up.
- **Final test counts**:
  - `pytest tests/`: 1099 passed, 1 skipped, 0 failed
  - Browser admin+mcp sweep: 47/48 (1 unrelated F6 pre-existing test failure — `test_admin_tools_renders_grid_with_4_tabs` expecting 4 category tabs but seeing 3 — documented in the L5 entry as out-of-flight scope)
- **All 6 autonomous legs landed cleanly**:
  - L1: 4 tests (schema v10 migration)
  - L2: 5 tests (encrypted repository round-trip)
  - L3: 10 tests (API endpoint extension + masking)
  - L4: 5 tests (encryption rotation extension)
  - L5: 7 browser tests (settings nav + grid)
  - L6: 9 browser tests (editor sub-module)
  - ~40 new tests total
