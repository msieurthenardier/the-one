# Leg: per-agent-tool-list

**Status**: completed
**Flight**: [Per-agent MCP credentials](../flight.md)

## Objective
Give an agent that uses its own credentials on a source a tool list made with those credentials: a per-agent tool cache (schema v50, DD5) read by the three build-time readers (DD4), filled by a cold build and by a new per-agent connection test route `POST /api/mcp-sources/{source_id}/test/agent` (DD6, with the Phase A extraction), invalidated at the DD7 hooks, and exposed to Studio as `mcp_tool_cache` on the single-agent routes, with tests and docs.

## Context
- The flight's DD4, DD5, DD6 and DD7 (cache-row deletes) are the design. Read `../flight.md` first; this leg does not restate the rationale.
- Charter criterion this leg delivers on the server: 3 (each agent's tools come from a listing with its own credentials; a key-less Library server still lists tools for an agent with a key; the switch-on test the UI calls in leg 3). It also keeps the constraint "an agent with no overrides behaves exactly as today".
- **Leg 1 landed** (commit `4b274ae4`): `the_one/mcp/_overrides.py` now has `has_oauth_state`, `configured_names`, `missing_values`; `_apply_override` overlays case-insensitively and skips OAuth Authorization; `_build_and_test_no_auth_mcp` and `_build_and_test_stdio_mcp` have `cache_write` (`"none" | "shared" | "shared_no_posture"`, default `"shared"`) and the no-auth helper has `classify`; `acquire(resolve_source=...)` and `_evict_all_for_agent` exist; eviction hooks are in `create_agent`, `update_agent`, `rename_agent`, `delete_agent` and `update_mcp_source`. Re-read those sites; line numbers below were taken after leg 1.
- **Schema change:** v50 migration created and executed in this leg (schema pins and the session template).
- **Security-sensitive:** the route connects with an agent's credentials. No value in any response, error or log line.
- **Layering deviation from DD6's suggested path:** the helpers the route reuses live in `the_one/interfaces/web/api.py`, so the route's logic goes in a new **interfaces-layer** module, `the_one/interfaces/web/mcp_agent_test.py`, not `the_one/mcp/agent_test.py` (an `mcp/` module must not import from `interfaces/`). The route in `api.py` stays thin; avoid an import cycle with a function-local import of the `api.py` helpers, or by moving the extracted Phase A helper into the new module and importing it from `api.py`.

## Inputs
- Branch `sortie/09-per-agent-mcp-credentials` at `4b274ae4`.
- Leg 1's helpers and hooks (above).

## Outputs
- Schema: `the_one/db/schema.py` (v50), `tests/test_schema.py` pins, the session template.
- Server: `the_one/db/repositories.py` (`AgentMcpToolCacheRepository`), `the_one/mcp/_overrides.py` (`has_credential_override`), `the_one/mcp/_tool_provider.py`, `the_one/agent/factory.py`, `the_one/self_configuration/projection.py`, new `the_one/interfaces/web/mcp_agent_test.py`, `the_one/interfaces/web/api.py`.
- Tests: new unit test files (suggested `tests/test_agent_mcp_tool_cache.py`, `tests/test_mcp_agent_test_route.py`).
- Docs: `the_one/agents.md`, `CLAUDE.md`, `SECURITY-MODEL.md`.

## Acceptance Criteria

**Which agents (DD4)**
- [ ] AC1. `has_credential_override(entry, source) -> bool` in `mcp/_overrides.py` is true exactly when `entry` (already read through `override_for`, so the self-configuration row never counts) has a non-empty `headers`, `env` or `bearer_token` that `_apply_override` would send: a per-agent `Authorization` (any case) or `bearer_token` on a source with OAuth state does not count, and an entry with only tool filters does not count. Unit tests cover each case.

**Cache table (DD5)**
- [ ] AC2. Schema v50 creates `agent_mcp_tool_cache` (`agent_name TEXT NOT NULL REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE`, `source_id TEXT NOT NULL REFERENCES mcp_sources(id) ON DELETE CASCADE`, `tools TEXT NOT NULL`, `fetched_at TEXT NOT NULL`, primary key `(agent_name, source_id)`), following the v43 `agent_notes` migration shape; `CURRENT_VERSION = 50`. The existing version pins are symbolic (they compare against `CURRENT_VERSION`) and the template is built from `ensure_schema`, so nothing there needs editing; add a v50 migration test in `tests/test_db_migration.py` (the table exists; re-running after `DELETE FROM schema_version WHERE version >= 50` is idempotent, like the v43 tests ~5571). Tests: an agent rename moves its rows, an agent delete and a source delete remove them.
- [ ] AC3. `AgentMcpToolCacheRepository` in `db/repositories.py`: `get(agent, source_id) -> {tools, fetched_at} | None`, `get_for_agent(agent) -> {source_id: {...}}`, `put_if_unchanged(agent, source_id, tools, expected_updated_at) -> bool` (one statement: `INSERT OR REPLACE INTO agent_mcp_tool_cache (...) SELECT ... WHERE (SELECT updated_at FROM agents WHERE name = ?) = ?`; returns whether a row was written), `delete(agent, source_id)`, `delete_for_source(source_id)`, and `agent_updated_at(name) -> str | None` (`AgentConfig` and `SQLiteAgentStore.load()` don't expose it; `None` means the agent is not in the store). Not encrypted. A unit test interleaves an agent `save()` between reading `updated_at` and `put_if_unchanged` and checks that no row is written; a renamed or deleted agent writes nothing. A code comment notes that other `agents.updated_at` writers (the notes and routines flags, field setters) also cancel an in-flight write, which is safe.
- [ ] AC4. Cache-row deletes at leg 1's hooks: `update_agent` deletes `(name, source_id)` for each source whose credential view changed (the same diff that drives eviction); `update_mcp_source` calls `delete_for_source` when it evicts (type, config minus `_cache`, or secrets changed); `reset_mcp_connection` calls `delete_for_source`. A no-op save deletes nothing (test).

**Readers (DD4)**
- [ ] AC5. The three build-time readers use the per-agent cache when `has_credential_override(override_for(config.mcp_overrides, source), source)` holds, and never the shared `_cache` for such a source: `_tool_provider.py` Path B (`get_tools_for_agent`, ~378), `factory._build_source_index` (~145, the `search_tools` index) and `self_configuration/projection.py` (~139, `describe_my_capabilities`). Every other agent reads the shared `_cache` exactly as today, and **an agent not in the store** (`agent_updated_at` is `None`: an injected test config) also reads the shared `_cache` as today, so existing tests that inject a credentialed config with a shared cache (for example `tests/test_self_configuration_projection.py:~253`) keep their behaviour.
  - Tests: an agent with no override still uses the shared cache and does **not** call `acquire`; a credentialed stored agent with a per-agent row uses it and does not acquire; a credentialed stored agent whose shared cache is full but whose per-agent row is empty does not use the shared list; an injected (not stored) credentialed config uses the shared cache.
  - Only Path B/A lists live. With a cold per-agent row, the projection reports `tools: []`, `tools_known: False` and never connects (it stays read-only), and `_build_source_index` skips the source with its existing "no cached tools" WARNING.
  - In `AgentFactory.create`, `mcp_provider.get_tools_for_agent` (factory.py ~491) runs before the index build, so a Path A write is visible to the index in the same build (test).
  - Reader context: all three are async. `get_tools_for_agent` has `conn` and the agent name; `_build_source_index` calls `get_connection()` (factory.py ~127); `build_describe_my_capabilities` reaches the table the same way, through `get_connection()`, and gets no new parameter.
- [ ] AC6. A credentialed stored agent with a cold per-agent cache lists live at build (Path A, which already uses its effective source). On success it converts the `MCPTool` objects to `{name, description, input_schema}` and writes its per-agent row through `put_if_unchanged`, with the agent's `updated_at` read before the listing (test). A failed listing writes nothing, and the source is skipped with the existing WARNING, as today.

**The route (DD6)**
- [ ] AC7. `POST /api/mcp-sources/{source_id}/test/agent`, body `{"agent": <name> | null, "overrides": <one mcp_overrides entry in the DD1 write shape> | null}`, behind the credential gate like every route: unknown `source_id` 404; unknown named agent 404; a self-configuration row (`is_surface_row`) 422; a malformed body 422. The logic is in `the_one/interfaces/web/mcp_agent_test.py`; the route in `api.py` is thin.
- [ ] AC8. Resolution: the stored source; the stored agent's entry through `override_for` (if `agent` is set); merged with `overrides` by `_merge_preserved_mcp_credentials` (the `{source.name: overrides}` shape, against the stored `{source.name: entry}`); leg 1's `validate_mcp_overrides` on the incoming entry (a refusal is a 422 in its shape); `_apply_override`. Then, if `missing_values(source, effective)` is non-empty: `{"status": "needs_values", "missing": [...]}` with no connection (test: the key server sees no request).
- [ ] AC9. Phase A is extracted from `_test_mcp_connection_inner` (~4359-4470) into one helper that both routes call (suggested `_connect_with_tokens(source, repo, *, record_era, cache_write)`). The helper takes `cache_write` and does its own write: `"shared"` and `"shared_no_posture"` both write today's Phase A fields (that block writes no posture), and `"none"` writes nothing. It keeps the same **function-local** imports (`MCPClient`, `build_oauth_provider_for_source`, the error classes), because tests patch `the_one.mcp.client.MCPClient` and a module-top import would defeat that. It re-raises `MCPAuthRequired`, `MCPConnectionError` (untouched, so the caller's `TOKEN_FAILURE_MARKERS` check still works) and `MCPVersionMismatch`, and `recordable` stays in the caller. The extraction keeps the Library Test's behaviour exactly (token clearing, `_evict_all_for_source`, fall-through to Phase B stay in the Library caller; every existing Library Test test passes untouched). The per-agent route uses it for a source with live sign-in tokens and never clears tokens, never evicts, never falls through: `MCPAuthRequired` -> `{"status": "auth_required"}` with no `consent_url`; `MCPConnectionError` / `MCPVersionMismatch` -> `{"status": "error", "error": "<Class>: <msg>"}`.
- [ ] AC10. Without live tokens: stdio -> `_build_and_test_stdio_mcp(..., cache_write="none", record_era=False)`; streamable-http -> `_build_and_test_no_auth_mcp(..., cache_write="none", record_era=False, classify=True)` with `MCPAuthRequired` -> `auth_required` (no `consent_url`) and `MCPCredentialsRejected` -> `error`. The route never runs the Phase 0 probe or Phase B and never writes `auth_posture`, `last_check` or the era record (tests read `_cache` before and after).
- [ ] AC11. Persistence. The mode is decided **before** connecting, because whether the tested credentials are the stored ones is known up front: the merged `headers`/`env`/`bearer_token` equal the stored agent's, or, with `agent: null`, the body carries no credential key.
  - The agent exists and `has_credential_override` holds for its stored entry: the helpers get `cache_write="none"`, and on `ok` the route writes the returned `tools` to the per-agent row via `put_if_unchanged`, with the agent's `updated_at` read at the start.
  - No override, or `agent: null`: the helpers get `cache_write="shared_no_posture"`, so the shared `_cache` fields (`tools`, `capabilities`, `server_info`, `instructions`, `meta`, `protocol_version`, `last_updated`) are written by the helper itself, never `auth_posture` or `last_check`.
  - Anything else (an unsaved value, an unsaved removal): `cache_write="none"`, and nothing is written.
  - With live tokens, Phase A runs against the **effective** source. `_apply_override` keeps `secrets` (`dcr_credentials`, `access_token`), and live tokens are detected on the effective source. Test: an OAuth source plus a per-agent non-Authorization header.
  Tests: one per branch, including an unsaved removal (masks only, one name left out) writing nothing.
- [ ] AC12. Responses keep the Library Test's shapes (`ok` with `tools` and `capabilities`; `auth_required`; `error`) plus `needs_values`; a test with a distinctive value asserts it appears in no response and no captured log record, on success, rejection and refusal.

**Studio exposure**
- [ ] AC13. `GET /api/agents/{name}`, and the create, update and rename responses, carry an additive `mcp_tool_cache: {<source_id>: {"tools": [...], "fetched_at": ...}}` for the attached sources where `has_credential_override` holds and a row exists (an empty object otherwise); `list_agents` does not (no extra read per page). `update_agent` and `create_agent` ignore `mcp_tool_cache`, `notices` and `kb_tool_names` in a request body (a GET body sent back saves with 200, test).

**End to end, docs, gate**
- [ ] AC14. With `key_server.py` in-process (the harness from leg 1's end-to-end test), two agents on one source with keys that allow different tools: each agent's route call returns its own tools; after a save of each, a build of each registers only its own tools (Path B from the per-agent row, no acquire); an agent with no override and a key-less Library source gets `needs_values`. Falsified: with the DD4 switch removed from Path B, the credentialed agent gets the shared list.
- [ ] AC15. `the_one/agents.md`'s "Per-agent MCP credentials (sortie 09)" block gains the cache table, the readers, the route (its steps, responses and persistence rules) and the Phase A extraction; `CLAUDE.md`'s `mcp_overrides` watch-out gains one sentence on per-agent credentials (validated on save, effective at the next connection, a per-agent tool list, `POST /api/mcp-sources/{id}/test/agent`); `SECURITY-MODEL.md`'s paragraph gains the tool-list note (an agent's tool list now depends on its own credentials; the cache holds tool metadata only). The flight log has the leg's entry.
- [ ] AC16. The full `THE_ONE_TEST_NETNS=1 make test-unit` passes (expected skip count), and the `mcp`, `mcp-connection` and `agents` browser lanes pass through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`, one at a time (or one failure that passes isolated and is logged). `ruff check` and `ruff format --check` clean.

## Verification Steps
- AC1-AC6: the new unit tests; `tests/test_mcp_tool_provider.py`, `tests/test_factory.py`, `tests/test_self_configuration_projection.py`, `tests/test_schema.py`, `tests/test_schema_template.py`, `tests/test_db_migration.py` green.
- AC7-AC12: the route tests; `tests/test_oauth_test_connection_endpoint.py`, `tests/test_mcp_library_test_missing_values.py`, `tests/test_mcp_test_connection_negotiation.py`, `tests/test_mcp_stdio_test_connect.py` green untouched.
- AC13: API tests on the response field and the GET-body round trip.
- AC14: the end-to-end test and its falsification.
- AC15: read the docs diff.
- AC16: `THE_ONE_TEST_NETNS=1 make test-unit`; `--lane mcp`, `--lane mcp-connection`, `--lane agents`; ruff.

## Implementation Guidance

1. **Schema and repository** (AC2-AC3). Add `if version < 50:` after the v49 block (`db/schema.py:~3255`), modelled on v43 `agent_notes`. Update `CURRENT_VERSION`, the pins and the template (see CLAUDE.md "Test databases come from a template"). Repository beside `AgentNoteRepository` (`repositories.py:~1871`), same connection pattern; `put_if_unchanged` is one statement, `fetched_at` an ISO timestamp.
2. **`has_credential_override`** (AC1) next to `missing_values` in `mcp/_overrides.py`, reusing `has_oauth_state`.
3. **Readers** (AC5-AC6). In each reader, compute the entry through `override_for`, branch on `has_credential_override`, and read the per-agent row (one `get_for_agent` per build where several sources are read). Path A: read the agent's `updated_at` from the store before listing; write with `put_if_unchanged`. Agents not in the store (CLI, injected configs) use the shared cache as today.
4. **Hooks** (AC4): extend leg 1's eviction sites; reuse their diff.
5. **Phase A extraction** (AC9). Move the `if source.secrets.get("dcr_credentials") and source.secrets.get("access_token"):` body (~4364-4470) into a helper that performs connect + list + the cache write per `cache_write` and **raises** `MCPAuthRequired` / `MCPConnectionError` / `MCPVersionMismatch` to its caller; keep the token clearing, eviction and fall-through decisions in `_test_mcp_connection_inner`. Run every Library Test test before going further.
6. **Route** (AC7-AC12) in `interfaces/web/mcp_agent_test.py`; register `POST /mcp-sources/{source_id}/test/agent` in `api.py` next to `test_mcp_connection` (~4110), reading the body with the existing `_read_json` pattern. Layering precedent: `routines_api.py` is a sibling module that reaches `api.py` through a call-time `_ApiModule` proxy (`routines_api.py:40-50`, attached at the end of `api.py` ~7025-7029). Mirror that, or import the new module function-locally from the route. The new module must not import `api` at module top.
7. **Response field** (AC13): `AgentConfig.model_config = {"extra": "ignore"}` (`agent/config.py:92`), so a GET-body round trip already works and needs only a test; check that leg 1's raw-body validation and the masking loop also ignore the extra key. Add an async resolver and a `mcp_tool_cache` parameter to `_agent_response`, used from `_full_agent_response` (api.py ~305-310, the single-agent routes GET ~1204, create ~1355, update ~1449, rename ~1520) like `kb_tool_names`; `list_agents` (~1194) passes none.
   Compute the set of changed sources once in `update_agent` (a small helper shared by leg 1's eviction and AC4's deletes).
8. **End to end** (AC14), docs (AC15), gate (AC16). Long runs in the background; wait for their notifications.

## Edge Cases
- **An agent attached to a source with a credential override for a source it no longer attaches**: the readers only read attached sources; an orphan row is harmless (it is deleted by cascade or overwritten).
- **A credentialed agent whose server is unreachable and cache cold**: the build waits for the connect timeout (known effect, DD4); the source is skipped.
- **The route in create mode with overrides**: nothing persisted (no agent).
- **A source renamed in the Library**: the cache is keyed by source id, so rows survive; `carry_mcp_rename` moves the override key, so `has_credential_override` still holds.
- **A credentialed agent on an OAuth source with only a per-agent Authorization**: not credentialed (AC1); it uses the shared list, which is correct since the Authorization is skipped.
- **`fetched_at` and time zones**: store UTC ISO; Studio does not format it in this leg.
- **Upgrade effect**: every existing agent with a credential override starts with a cold per-agent cache, so its first build lists live on each such source (and waits for the connect timeout if the server is down). Record this in the docs' known effects and the release-notes note.

## Files Affected
- `the_one/db/schema.py`, `tests/test_schema.py`, `tests/_schema_template.py` (if it pins the version) - v50
- `the_one/db/repositories.py` - `AgentMcpToolCacheRepository`
- `the_one/mcp/_overrides.py` - `has_credential_override`
- `the_one/mcp/_tool_provider.py`, `the_one/agent/factory.py`, `the_one/self_configuration/projection.py` - readers, Path A write
- `the_one/interfaces/web/mcp_agent_test.py` - new: the route logic
- `the_one/interfaces/web/api.py` - Phase A extraction, the route, the response field, the hook deletes
- `tests/test_*.py` - new and updated tests
- `the_one/agents.md`, `CLAUDE.md`, `SECURITY-MODEL.md` - docs

## Citation Audit
Checked against the working tree at `4b274ae4` (after leg 1):
- `the_one/mcp/_tool_provider.py` Path B reads `source.config.get("_cache", {}).get("tools")` at ~378 - verified
- `the_one/agent/factory.py::_build_source_index` reads `_cache.tools` at ~145 - verified
- `the_one/self_configuration/projection.py` reads `_cache.tools` at ~139 - verified
- `the_one/interfaces/web/api.py`: `_build_and_test_no_auth_mcp` 3842, `_build_and_test_stdio_mcp` 3964, `_test_mcp_connection_inner` 4133, `has_live_tokens` ~4280, the missing-values branch ~4291, Phase A block ~4359-4470 (provider built with `f"test:{source_id}"`, `MCPClient(..., fresh_negotiation=True, record_era=...)`, `repo.merge_cache` of tools/capabilities/server_info/instructions/meta/protocol_version/last_updated, `MCPAuthRequired` -> clear + evict + fall through, `MCPConnectionError` with `TOKEN_FAILURE_MARKERS` -> clear + evict + fall through else error, `MCPVersionMismatch` -> error) - verified
- `the_one/db/schema.py`: `CURRENT_VERSION = 49` (18), last block `if version < 49:` (3255) - verified
- `the_one/db/repositories.py::AgentNoteRepository` (1871) - verified
- leg 1's `has_oauth_state`, `configured_names`, `missing_values` in `the_one/mcp/_overrides.py`; `cache_write`/`classify` on the two helpers - verified by leg 1's landing report and commit `4b274ae4`; re-check signatures at implementation
