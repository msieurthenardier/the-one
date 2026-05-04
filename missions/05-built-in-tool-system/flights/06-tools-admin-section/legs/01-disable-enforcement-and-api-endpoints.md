# Leg: 01-disable-enforcement-and-api-endpoints

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Wire L0's `tool_configs.enabled` storage layer into runtime enforcement and expose the four operator-facing admin endpoints (list, get-with-schema, upsert, test). `AgentFactory.create()` builds a `disabled_names: set[str]` from full `ToolConfig` rows and filters disabled tools out of the registry build, in addition to the existing per-agent `is_tool_enabled` check. `GET /api/tools/configs/{name}` returns the tool's `Config.model_json_schema()` enriched with `x_marker` per field (Decision 3 — Pydantic v2 strips the marker classes from the JSON Schema output, so a server-side helper walks `model_fields[field_name].metadata` to inject them). `POST /api/tools/configs/{name}/test` runs `web_search` or `fetch_url` against fixture inputs through the same `BuiltinToolProvider.get_tools` mechanics the agent uses, against the operator's currently-saved Config (Decision 5 — failed test = config-validity diagnostic). All four endpoints + the enforcement filter are unit-tested. No UI work in this leg (L2/L3/L4/L5 own that).

## Context

- **F6 mission goal — operator kill switch**: an operator-facing per-tool disable that sits independently from the agent-facing `enabled_tools` / `disabled_tools` whitelist. L0 landed the storage; L1 makes it bite at runtime AND surfaces the read/write/test API the L2-L4 UI consumes.
- **L0's `list_all()` shape preserved**: per the L0 design review, the resolver-facing `ToolConfigRepository.list_all()` API stays `{name: config_dict}` with `enabled` deliberately omitted. L1 introduces enforcement at the **factory** by switching `factory.py:109` to call `repo.list()` (full models), then projecting two derived structures — `tool_configs_by_name: dict[str, dict]` for the resolver (unchanged shape, fed to `provider.get_tools(...)`) AND `disabled_names: set[str]` for the registry filter. This keeps the resolver's shape pure and pushes the projection up to the factory boundary, where the second filter at `factory.py:120` already lives. Single DB hit, single source of truth.
- **F6 Decision 2** (enforcement): "BuiltinToolProvider.get_tools consults the enabled field via the resolver — disabled tools are filtered out of the returned list." L1 delivers this by intercepting at the factory, NOT inside `get_tools` itself — the provider's introspection path (called by `GET /api/tools` for the tool catalog) intentionally returns ALL tools regardless of operator disable state, so admin-facing surfaces (the L2 grid, this leg's `GET /api/tools/configs`) can render disabled tools as such. Enforcement at the factory makes the filter agent-facing only. This is the cleanest interpretation of Decision 2.
- **F6 Decision 3** (server-side marker enrichment): Pydantic v2's `Model.model_json_schema()` does NOT surface `field_info.metadata` markers (`Narrow`/`NarrowPrefix`/`NarrowSuperset`/`Substitute`) — the schema only carries `default`, `description`, `maximum`/`minimum`, `title`, `type`, plus the `ui_hint`/`ui_choices` extras already wired by F4/F5. L1 ships the `_enrich_schema_with_markers(schema, config_class)` helper to inject `x_marker: str | None` per top-level property by walking `config_class.model_fields[name].metadata` and matching marker class identity (`m is Narrow`, etc., the same pattern the resolver uses internally at `the_one/tools/resolver.py:233-236`).
- **F6 Decision 5** (test endpoint semantics): the test endpoint runs the tool with the **named tool's** currently-saved Config — NOT a synthetic minimal one, NOT a sibling tool's Config. **Cross-config shadowing pitfall**: `BuiltinToolProvider.get_tools` builds `cross_configs` (at `the_one/tools/builtins.py:120-127`) by walking `_TOOL_CLASSES` in declared order and resolving each Config from the FIRST tool name carrying that Config. For `WebConfig`, the first tool is `http_request` — so a naive `tool_configs_by_name = {c.name: c.config for c in repo.list()}` would mean testing `web_search` actually runs through `http_request`'s saved config (because `cross_configs[WebConfig]` is built from `http_request`'s row, and `web_search.execute` reads its config from `cross_configs[WebConfig]` via the F4 cross-Config dispatch). L1 fixes this by **re-keying** the test endpoint's `tool_configs_by_name` so every tool sharing the named tool's Config class is given the named tool's saved row: `{tname: tested_config for tname, tcls in _TOOL_CLASSES.items() if tcls.Config is named.Config}`. This makes `cross_configs[WebConfig]` carry the tested tool's saved config regardless of declaration order. Sibling tools that don't share a Config class get their own saved rows (irrelevant for the test path but cheap to include). Mirrors Decision 5's "operator's currently-saved Config" — singular, scoped to the named tool — strictly. **Note**: this differs from the agent runtime, where the FIRST-declared-tool semantics intentionally apply (operator policy is unified across same-Config tools at agent-create time). The test endpoint is the only place the named-tool isolation matters.
- **F6 Decision 11** (endpoint shape): four routes under `/api/tools/configs/*`. The plural `/configs` distinguishes from the existing `/api/tools` (tool catalog at `the_one/interfaces/web/api.py:79-84`). `POST /test` is its own endpoint (NOT a query param on PUT) so it has its own permission shape if F7+ adds RBAC.
- **F6 Decision 12** (two-Reviewer-pass batching): L1 commits no docs. CLAUDE.md "Tool Authorship Contract" admin-endpoint addendum is L9.
- **L0's runtime decision** (TestSchemaV8 stale assertions): noted only as background — L1 does not re-touch `tests/test_db_migration.py`.

## Inputs

- `the_one/db/repositories.py:308-388` — `ToolConfigRepository` (now with `list()` returning `list[ToolConfig]` carrying the new `enabled: bool` field via L0).
- `the_one/db/models.py:61-85` — `ToolConfig` (now widened with `enabled: bool = True` via L0).
- `the_one/agent/factory.py:104-121` — current factory wiring; line 109 calls `list_all()`; lines 116-121 build the registry with the per-agent `is_tool_enabled` check.
- `the_one/tools/builtins.py` — `_TOOL_CLASSES: dict[str, type[Tool]]` (19 tools); `BuiltinToolProvider.get_tools(tool_configs, agent_overrides, agent_name=None)` (introspection path returns all tools when both args are None).
- `the_one/tools/base.py:19-104` — `Tool` base class; `Tool.Config` defaults to `_EmptyConfig`; `execute(**kwargs) -> str` returns the agent-visible string with `[error] [constraint] ...` formatting baked in.
- `the_one/tools/resolver.py:31-93` — `Narrow`, `NarrowPrefix`, `NarrowSuperset`, `Substitute` sentinel marker classes. The resolver uses `m is Narrow` / `m is Substitute` identity checks at `resolver.py:233-236`.
- `the_one/tools/_web_config.py` — `WebConfig` (carries the markers we need to round-trip in the schema).
- `the_one/tools/filesystem.py` — `FilesystemConfig`.
- `the_one/tools/execution.py` — `ExecutionConfig`.
- `the_one/tools/python_exec.py` — `PythonExecConfig`.
- `the_one/tools/web.py:340-389` — `WebSearchTool.execute(query, max_results=5)`.
- `the_one/tools/web.py:144-...` — `FetchUrlTool.execute(url)`.
- `the_one/interfaces/web/api.py:1-90` — router setup; existing `GET /api/tools` (introspection at line 80) and `_provider_repo()` helper pattern at line 377.
- `the_one/interfaces/web/api.py:39-61` — repo helper pattern (`_agent_store`, `_kb_repo`, etc.) — the new `_tool_config_repo()` helper follows the same shape.

## Outputs

- `the_one/agent/factory.py` (lines 104-121):
  - Replace `tool_configs_by_name = await tool_configs_repo.list_all()` with a single `configs = await tool_configs_repo.list()` call.
  - Build the resolver-facing dict: `tool_configs_by_name = {c.name: c.config for c in configs}`.
  - Build the disabled set: `disabled_names = {c.name for c in configs if not c.enabled}`.
  - Add `disabled_names` to the registry-build filter at line 120: `if config.is_tool_enabled(tool.name) and tool.name not in disabled_names`.
  - Comment block updated to reflect the two-derived-structures projection.
- `the_one/interfaces/web/api.py` — append a new `# ── Tool configs ──` section (after the existing `# ── Tools ──` introspection block at line 76, before the agents block at line 87). Contents:
  - `_tool_config_repo()` helper (mirrors `_agent_store`/`_provider_repo`).
  - `_TOOL_CLASS_FOR_NAME` accessor: `from the_one.tools.builtins import _TOOL_CLASSES` at function-local scope to avoid module-import cycles (api.py is imported early; builtins.py pulls in every tool module).
  - `_enrich_schema_with_markers(schema: dict, config_class: type[BaseModel]) -> dict` — module-level helper; safe to live next to the route definitions.
  - `_TESTABLE_TOOLS = {"web_search", "fetch_url"}` — module constant; the test endpoint rejects names not in this set with HTTP 400.
  - 4 route handlers (see Decision 11):
    - `GET /api/tools/configs` — returns `[{name, enabled, config}, ...]` for every tool in `_TOOL_CLASSES`. Tools without a saved row appear with `enabled=True` and `config={}` (the default state). Sorted by tool name. Includes the tool's `description` for grid rendering convenience.
    - `GET /api/tools/configs/{name}` — returns `{name, enabled, config, description, schema}` where `schema` is `_enrich_schema_with_markers(cls.Config.model_json_schema(), cls.Config)`. 404 if `name not in _TOOL_CLASSES`.
    - `PUT /api/tools/configs/{name}` — body `{enabled?: bool, config?: dict}`. **Replace-not-merge contract** for `config`: when `config` is present in the body, it REPLACES the saved config wholesale (REST PUT convention). When `config` is omitted, the existing saved config is preserved. Same convention for `enabled`: present → use it; omitted → preserve existing. Validates submitted `config` by constructing `cls.Config.model_validate(submitted_config)` (raises `ValidationError` → HTTP 422). Calls `repo.upsert(name, validated.model_dump(), enabled=enabled)`. Returns the post-write row shape (same as `GET /one` minus `schema`). Rationale: the L3 form always submits the full Config state (it builds the form from `Config.model_json_schema()` and reads every field on save), so REPLACE matches L3's actual behaviour and makes "remove a field" possible (PUT with `config={}` validates against the Config's defaults, wiping the saved overrides).
    - `POST /api/tools/configs/{name}/test` — body `{}` (no params accepted; backend uses fixture inputs). Returns `{output: str, elapsed_ms: int}`. Rejects names not in `_TESTABLE_TOOLS` with HTTP 400 `"Tool {name} does not support connection testing"`. Builds `tool_configs_by_name` from `repo.list()`, invokes `BuiltinToolProvider().get_tools(tool_configs_by_name, agent_overrides={})`, picks the named tool, and awaits its `execute(...)` with the fixture input. Wall-clock timing via `time.perf_counter()`. The output string already carries `[error] [constraint] ...` formatting if the tool refused — passed through verbatim. The endpoint never returns 5xx for tool-side failures (those are operator-meaningful diagnostics carried in the `output` field). It DOES return 5xx if the BuiltinToolProvider construction itself raises (e.g., a malformed saved Config — that's a bug, not a diagnostic).
- `tests/test_factory_disable_enforcement.py` (new file):
  - `test_disabled_tool_excluded_from_registry` — operator disables `web_search`, factory builds a registry, `web_search` not in registry.
  - `test_disabled_tool_independent_of_per_agent_whitelist` — agent's `enabled_tools` includes `web_search`, operator disables it, agent still doesn't get the tool.
  - `test_re_enabling_restores_tool_to_registry` — disable, re-enable, factory registry contains the tool again.
  - `test_per_agent_disable_independent_of_operator_disable` — operator-enabled, agent-disabled (via `disabled_tools=["web_search"]`); tool absent from registry. Mirror coverage to confirm the two filters are independent.
  - `test_factory_does_not_call_list_all` — replace the L0 `list_all` call with `list()`; assert at integration level that `list_all` is not exercised on the factory path (light regression net for the projection change).
- `tests/test_api_tool_configs.py` (new file):
  - `test_list_configs_returns_all_19_tools` — fresh DB, no rows; GET returns 19 entries each with `enabled=True`, `config={}`, and the tool's description.
  - `test_list_configs_reflects_saved_state` — upsert one row with `enabled=False`; GET shows that row's `enabled=False` and the others' `enabled=True`.
  - `test_get_one_returns_enriched_schema` — GET `/configs/web_search`; assert `schema["properties"]["host_allowlist"]["x_marker"] == "Narrow"`; assert `schema["properties"]["default_user_agent"]["x_marker"] == "Substitute"`. Confirms the helper covers all 4 marker types via WebConfig (which uses Narrow + NarrowSuperset + NarrowPrefix + Substitute).
  - `test_get_one_returns_404_for_unknown_tool` — GET `/configs/nonexistent` → 404.
  - `test_get_one_for_empty_config_tool` — GET `/configs/shell_session_close` (uses `_EmptyConfig`) → schema has empty `properties`; `x_marker` injection is a no-op.
  - `test_put_validates_config_against_schema` — PUT `/configs/web_search` with `{"config": {"timeout_seconds_max": -1}}` (negative bound on a `>= 0` field) → 422.
  - `test_put_persists_enabled_and_config` — PUT `{"enabled": false, "config": {"timeout_seconds_max": 10}}` → row stored; subsequent GET shows the values.
  - `test_put_replaces_config_wholesale` — codifies the REPLACE-not-merge contract: existing row `config={"timeout_seconds_max": 99, "host_allowlist": ["a.com"]}`; PUT `{"config": {"timeout_seconds_max": 10}}`; subsequent GET shows `config` validated against `WebConfig` defaults — `host_allowlist` is gone (replaced by Config's default), `timeout_seconds_max == 10`. NOT merged with the prior row.
  - `test_put_preserves_omitted_top_level_keys` — codifies the "omitted keys preserved" contract for the top-level body: existing row `enabled=False, config={"timeout_seconds_max": 10}`; PUT `{"enabled": true}` (no `config` key) → row becomes `enabled=True` AND `config={"timeout_seconds_max": 10}` (unchanged). Symmetric: PUT `{"config": {...}}` with no `enabled` preserves the saved `enabled` value.
  - `test_put_with_empty_config_wipes_to_defaults` — PUT `{"config": {}}` with an existing row carrying overrides → `model_validate({})` succeeds against the Config's defaults; saved `config` becomes the Config's default-dump (every field at its default value). Demonstrates that REPLACE makes "wipe to defaults" expressible.
  - `test_put_for_unknown_tool` — PUT `/configs/nonexistent` → 404.
  - `test_test_endpoint_runs_web_search_with_fixture_query` — POST `/configs/web_search/test`. Use a `monkeypatch` on `the_one.tools._search_backends.DDGSearchBackend.search` to return a fixed list of `SearchResult`. Assert `output` contains the fixture results; `elapsed_ms` is an int.
  - `test_test_endpoint_runs_fetch_url_with_fixture_url` — POST `/configs/fetch_url/test`. Use a `monkeypatch` on `FetchUrlTool._build_transport` to return an `httpx.MockTransport` returning fixture HTML. Assert `output` contains the readability-extracted markdown.
  - `test_test_endpoint_rejects_non_testable_tool` — POST `/configs/shell/test` → 400 with the exact message text.
  - `test_test_endpoint_rejects_unknown_tool` — POST `/configs/nonexistent/test` → 404 (404 must take precedence over 400).
  - `test_test_endpoint_uses_operator_resolved_config_for_fetch_url` — operator saves `fetch_url` with `host_denylist=["example.com"]` (NarrowSuperset adds to the operator default; `example.com` blocks the fixture URL). POST `/configs/fetch_url/test`. The endpoint MUST surface the constraint refusal as `[error] [constraint] host 'example.com' is in denylist` (or equivalent — exact wording from `_url_check`) in the `output` field; HTTP 200; the diagnostic IS the value. **Note**: the analogous test for `web_search` is intentionally omitted — `WebSearchTool` delegates to `DDGSearchBackend` which owns its own httpx client (no `SSRFGuardedTransport`), so operator-set `host_allowlist` / `host_denylist` on `WebConfig` does NOT bind the search backend's network calls. F6 ships this test for `fetch_url` only; documenting the gap here so a future flight that wires the backend through `SSRFGuardedTransport` can add the symmetric `web_search` test.
  - `test_test_endpoint_named_tool_isolation` — operator saves `web_search` with `host_denylist=["example.com"]` AND `http_request` (also WebConfig) with NO denylist additions. POST `/configs/fetch_url/test` (which uses WebConfig). The endpoint must use `fetch_url`'s saved row (empty in this case → defaults) — NOT `http_request`'s (also empty) and NOT `web_search`'s (with the denylist). Codifies the named-tool re-keying behaviour: the test endpoint resolves `cross_configs[WebConfig]` from the named tool's row, regardless of `_TOOL_CLASSES` declaration order. The cleanest assertion: monkeypatch `BuiltinToolProvider.get_tools` (or `_enrich_schema_with_markers`-style intercept) to capture the `tool_configs_by_name` dict it receives, then assert `dict["http_request"] == dict["fetch_url"] == dict["web_search"] == fetch_url_saved_config`. Alternative: assert behavioural — save a distinguishable host on `web_search` and a different one on `fetch_url`, then verify the test for `fetch_url` honours `fetch_url`'s.
- `tests/test_enrich_schema_with_markers.py` (new file):
  - `test_enriches_narrow` — `WebConfig.host_allowlist` → `x_marker == "Narrow"`.
  - `test_enriches_narrow_prefix` — pick a `NarrowPrefix`-marked field (verify which Config has one — `FilesystemConfig.path_allowlist` per F3).
  - `test_enriches_narrow_superset` — `WebConfig.host_denylist` → `x_marker == "NarrowSuperset"` (per F5 L1 design).
  - `test_enriches_substitute` — `WebConfig.default_user_agent` → `x_marker == "Substitute"`.
  - `test_omits_x_marker_for_unmarked_field` — pick an admin-only field (e.g., `WebConfig.redirect_cap` if unmarked, or any other unmarked one) → `x_marker` key absent OR `None` (assert chosen contract).
  - `test_empty_config_helper_no_op` — pass `_EmptyConfig` → returned schema unchanged.
  - `test_helper_does_not_mutate_input_schema` — pass a schema dict, capture a deep copy, call helper, assert deep copy still equals the post-call schema (or assert helper returns a new dict — pick one contract; recommendation: returns the same dict but mutates in-place is fine since the helper is internal and the call site immediately serializes).

## Acceptance Criteria

- [x] `the_one/agent/factory.py` projects `repo.list()` into `tool_configs_by_name: dict[str, dict]` AND `disabled_names: set[str]`. The registry-build filter at line 120 adds `and tool.name not in disabled_names`.
- [x] `the_one/tools/builtins.py::BuiltinToolProvider.get_tools` is **NOT modified** — the introspection path continues to return ALL tools. The disabled filter lives at the factory only. `GET /api/tools` (catalog) continues to list 19 tools regardless of disable state.
- [x] `_enrich_schema_with_markers(schema, config_class)` correctly identifies all 4 marker types (`Narrow`, `NarrowPrefix`, `NarrowSuperset`, `Substitute`) by walking `config_class.model_fields[name].metadata` with `m is MarkerClass` identity checks.
- [x] `GET /api/tools/configs` returns 19 entries (fresh DB) with `enabled=True`, `config={}`, plus the tool's `description`. Sorted by `name`.
- [x] `GET /api/tools/configs/{name}` returns `{name, enabled, config, description, schema}` with `schema["properties"][field]["x_marker"]` populated for marker-bearing fields.
- [x] `GET /api/tools/configs/{name}` for `name not in _TOOL_CLASSES` returns 404 (NOT 200 with empty schema).
- [x] `PUT /api/tools/configs/{name}` validates the `config` body against `cls.Config` and returns 422 on Pydantic ValidationError. Validates `name` is in `_TOOL_CLASSES` and returns 404 if not.
- [x] `PUT /api/tools/configs/{name}` with a partial body `{"config": {...}}` (no `enabled`) reads the existing row first and preserves the existing `enabled` value via the `upsert(..., enabled=existing_enabled)` call — codified by `test_put_preserves_omitted_top_level_keys` (renamed from spec's `test_put_partial_update_reads_then_writes` to consolidate symmetric behaviour into one test, see flight log L1 deviations).
- [x] `POST /api/tools/configs/{name}/test` accepts only `name in _TESTABLE_TOOLS = {"web_search", "fetch_url"}`; other names yield HTTP 400; unknown names yield HTTP 404 (404 takes precedence).
- [x] `POST /api/tools/configs/{name}/test` invokes `BuiltinToolProvider().get_tools(tool_configs_by_name, {})` — the same construction path the agent uses — with the operator's currently-saved Config (Decision 5).
- [x] `POST /api/tools/configs/{name}/test` returns `{output: str, elapsed_ms: int}` on tool-side success AND tool-side failure (constraint refusals carried as `[error] [constraint] ...` strings in `output`, NOT as HTTP 5xx). (Note: `elapsed_ms` is `float` rounded to 2 decimals per Implementation Guidance step 3.)
- [x] `tests/test_factory_disable_enforcement.py` ships with 5 tests; all pass.
- [x] `tests/test_api_tool_configs.py` ships with 17 tests (acceptance criterion said 14; outputs section enumerated 17 distinct tests — all enumerated tests are implemented; tally inconsistency in the spec, see flight log L1 deviations) covering the 4 endpoints + the REPLACE/preserve PUT contracts + the operator-resolved-config behaviour + named-tool isolation; all pass.
- [x] `tests/test_enrich_schema_with_markers.py` ships with 7 tests (one per marker, plus empty-Config no-op, plus mutate-vs-return contract); all pass.
- [x] **`tests/test_factory.py` updated to mock `list` instead of `list_all`** — three concrete fixtures (line ~110, line ~239, line ~305) currently mock `mock_tool_repo.list_all = AsyncMock(...)`. Each must change to `mock_tool_repo.list = AsyncMock(return_value=[ToolConfig(name=..., config=..., enabled=True), ...])`. The `tool_configs={"shell": {"output_cap": 1000}}` fixture at line 239 also flips to a `list[ToolConfig]` shape. Codified deliverable, not optional.
- [x] **F1-F5 unit tests otherwise pass unchanged.** L0 tests still pass — in particular `test_list_all_omits_enabled` (which asserts the resolver-facing API is untouched; `list_all()` itself is not modified by L1).
- [x] `make test-unit` is green (modulo the pre-existing `tests/test_token_definitions.py::test_every_var_reference_is_defined` red, deselected as in F5/L0).
- [x] `ruff check` clean on touched files.
- [x] No UI / Studio / admin sub-module file is touched. (L2/L3/L4/L5 own those.)

## Verification Steps

```bash
# 1. Helper isolation: enrichment correctly identifies all 4 markers via WebConfig
docker exec the-one python -c "
from the_one.tools._web_config import WebConfig
import sys, importlib
sys.path.insert(0, '/app')
from the_one.interfaces.web.api import _enrich_schema_with_markers
schema = WebConfig.model_json_schema()
out = _enrich_schema_with_markers(schema, WebConfig)
props = out['properties']
# host_allowlist is Narrow (per F5 L1 architect catch)
assert props['host_allowlist'].get('x_marker') == 'Narrow', props['host_allowlist']
# host_denylist is NarrowSuperset (extends operator's denylist)
assert props['host_denylist'].get('x_marker') == 'NarrowSuperset', props['host_denylist']
# default_user_agent is Substitute
assert props['default_user_agent'].get('x_marker') == 'Substitute', props['default_user_agent']
print('OK enrichment: Narrow / NarrowSuperset / Substitute')
"

# 2. Factory enforcement: disabled tool excluded
docker exec the-one python -c "
import asyncio
from the_one.db.connection import get_connection
from the_one.db.repositories import ToolConfigRepository
from the_one.agent.factory import AgentFactory
# Use a default agent fixture; assert post-disable registry omits web_search.
# Implementation detail moves to tests/test_factory_disable_enforcement.py.
print('OK factory enforcement smoke (full assertion in pytest)')
"

# 3. Endpoint surfaces — DEFER to pytest. The full TestClient/ASGI plumbing
#    requires the `client` fixture pattern from tests/test_db_api.py:16-35
#    (ASGITransport + AsyncClient + isolated DB + patched get_connection).
#    Running it inline is too noisy; rely on the targeted pytest run in step 4.

# 4. Targeted test runs
docker exec the-one pytest tests/test_factory_disable_enforcement.py -x -q
docker exec the-one pytest tests/test_api_tool_configs.py -x -q
docker exec the-one pytest tests/test_enrich_schema_with_markers.py -x -q

# 5. Regression — L0 + factory + agent tests untouched (modulo the codified
#    factory-mock update that L1 ships in tests/test_factory.py)
docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py tests/test_factory.py tests/test_db_api.py -x -q

# 6. Full unit suite
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 7. Lint
docker exec the-one ruff check the_one/agent/factory.py the_one/interfaces/web/api.py tests/test_factory_disable_enforcement.py tests/test_api_tool_configs.py tests/test_enrich_schema_with_markers.py
```

## Implementation Guidance

1. **Factory enforcement** — `the_one/agent/factory.py` lines 104-121:

   ```python
           # 2. Load tool-level configs and agent-level overrides for the
           # tool policy resolver. Resolved per-agent — Decision 8's
           # session-bound freshness contract: mid-session updates apply at
           # the next AgentFactory.create() call.
           #
           # F6 L1: project the full ToolConfig list into TWO derived
           # structures — the resolver-facing `{name: config_dict}` (which
           # `list_all()` would return identically) AND a `disabled_names`
           # set for the registry-build filter. We deliberately do NOT
           # widen `list_all()` to carry `enabled`; pushing the projection
           # to the factory keeps the resolver's API surface pure (see
           # L0's `test_list_all_omits_enabled`).
           tool_configs_repo = ToolConfigRepository(conn)
           configs = await tool_configs_repo.list()
           tool_configs_by_name = {c.name: c.config for c in configs}
           disabled_names = {c.name for c in configs if not c.enabled}
           agent_overrides = config.tool_overrides or {}

           # 3. Build filtered tool registry — fresh ToolRegistry per call,
           # populated with fresh per-agent tool instances (the provider
           # invokes the resolver internally per Decision 10). The filter
           # composes operator-disable (tool_configs.enabled) with per-agent
           # disable (config.is_tool_enabled) — both must pass.
           registry = ToolRegistry()
           for provider in self.tool_providers:
               for tool in provider.get_tools(
                   tool_configs_by_name, agent_overrides, agent_name=name
               ):
                   if (
                       tool.name not in disabled_names
                       and config.is_tool_enabled(tool.name)
                   ):
                       registry.register(tool)
   ```

2. **Helper section** — extend the existing repo-import block at api.py:22-29 to add `ToolConfigRepository`. Then append a helper block AFTER `_chat_repo` (line 61), BEFORE `# ── Settings ──`:

   ```python
   # ── Tool config helpers (F6 L1) ───────────────────────────────────────────

   _TESTABLE_TOOLS = frozenset({"web_search", "fetch_url"})


   async def _tool_config_repo() -> ToolConfigRepository:
       conn = await get_connection()
       return ToolConfigRepository(conn)


   def _enrich_schema_with_markers(
       schema: dict[str, Any], config_class: type
   ) -> dict[str, Any]:
       """Inject `x_marker` per top-level property by reading
       `config_class.model_fields[name].metadata`. Pydantic v2 does not
       surface marker classes in `model_json_schema()`; the resolver
       dispatches on `m is Narrow` / `m is Substitute` identity at
       `the_one/tools/resolver.py:233-236` — same pattern here.

       Mutates `schema` in place AND returns it (caller convenience —
       both forms work). Safe to call on `_EmptyConfig` (no-op since
       `model_fields` is empty).

       Assumes a flat schema (no nested BaseModel fields under `$defs`).
       All four F2-F5 Configs (FilesystemConfig, ExecutionConfig,
       PythonExecConfig, WebConfig) are flat. A future Config that
       nests another BaseModel will need a `$defs` walk added here."""
       from the_one.tools.resolver import (
           Narrow,
           NarrowPrefix,
           NarrowSuperset,
           Substitute,
       )
       marker_map = {
           Narrow: "Narrow",
           NarrowPrefix: "NarrowPrefix",
           NarrowSuperset: "NarrowSuperset",
           Substitute: "Substitute",
       }
       properties = schema.get("properties") or {}
       for field_name, field_info in config_class.model_fields.items():
           prop = properties.get(field_name)
           if prop is None:
               continue
           for marker_cls, marker_name in marker_map.items():
               if any(m is marker_cls for m in field_info.metadata):
                   prop["x_marker"] = marker_name
                   break
       return schema
   ```

   - `ValidationError`, `Request`, `HTTPException`, and `time` are already imported at api.py top (lines 8, 15, 17). Do NOT re-import.
   - The `from the_one.tools.builtins import _TOOL_CLASSES` import in each route handler is intentionally function-local (api.py is imported very early in app start; pulling the full builtin tool tree at module load time would slow it).

3. **Tools-config routes** — append a new `# ── Tool configs ──` section AFTER the `# ── Tools ──` introspection block at api.py line 76 (so `GET /api/tools` and `GET /api/tools/configs` are visually colocated). Local imports of `_TOOL_CLASSES` are deliberate — the api module is imported very early; pulling the full builtin tool tree at module level slows import without need:

   ```python
   # ── Tool configs ──────────────────────────────────────────────────────────


   @router.get("/tools/configs")
   async def list_tool_configs() -> list[dict[str, Any]]:
       """Operator-facing tool-config list. Tools without a saved row
       appear with `enabled=True` and `config={}` (the default state).
       Sorted by tool name. The L2 admin grid consumes this."""
       from the_one.tools.builtins import _TOOL_CLASSES

       repo = await _tool_config_repo()
       saved = {c.name: c for c in await repo.list()}
       result: list[dict[str, Any]] = []
       for name in sorted(_TOOL_CLASSES):
           cls = _TOOL_CLASSES[name]
           row = saved.get(name)
           result.append(
               {
                   "name": name,
                   "description": cls.description,
                   "enabled": row.enabled if row else True,
                   "config": row.config if row else {},
               }
           )
       return result


   @router.get("/tools/configs/{name}")
   async def get_tool_config(name: str) -> dict[str, Any]:
       """Per-tool detail with marker-enriched JSON Schema. The L3 editor
       drives form rendering from the returned `schema`."""
       from the_one.tools.builtins import _TOOL_CLASSES

       cls = _TOOL_CLASSES.get(name)
       if cls is None:
           raise HTTPException(status_code=404, detail=f"Unknown tool: {name}")
       repo = await _tool_config_repo()
       try:
           row = await repo.get(name)
           enabled = row.enabled
           config = row.config
       except KeyError:
           enabled = True
           config = {}
       schema = _enrich_schema_with_markers(cls.Config.model_json_schema(), cls.Config)
       return {
           "name": name,
           "description": cls.description,
           "enabled": enabled,
           "config": config,
           "schema": schema,
       }


   @router.put("/tools/configs/{name}")
   async def upsert_tool_config(name: str, request: Request) -> dict[str, Any]:
       """Upsert the operator-saved config + enabled state.

       Body shape: `{enabled?: bool, config?: dict}`.

       REPLACE-not-merge contract for `config`: when present in body,
       REPLACES the saved config wholesale (REST PUT convention). The
       L3 form always submits the full Config state, so REPLACE matches
       its actual behaviour. To wipe to defaults, send `{"config": {}}`.

       Top-level keys are preserved when omitted: PUT `{"enabled": true}`
       (no `config` key) updates only `enabled` and leaves `config`
       intact. Symmetric for `config`-only PUTs.

       Validates submitted `config` against `cls.Config` — Pydantic v2's
       default `extra="ignore"` (verified for all four F2-F5 Configs)
       silently drops unknown extras."""
       from the_one.tools.builtins import _TOOL_CLASSES

       cls = _TOOL_CLASSES.get(name)
       if cls is None:
           raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
       data = await request.json()
       repo = await _tool_config_repo()
       try:
           existing = await repo.get(name)
           current_enabled = existing.enabled
           current_config = existing.config
       except KeyError:
           current_enabled = True
           current_config = {}

       # `enabled` — preserve when omitted from body; coerce when present.
       new_enabled = bool(data["enabled"]) if "enabled" in data else current_enabled

       # `config` — REPLACE when present (validate body), preserve when omitted.
       if "config" in data:
           try:
               validated = cls.Config.model_validate(data["config"])
           except ValidationError as e:
               raise HTTPException(status_code=422, detail=e.errors())
           new_config = validated.model_dump()
       else:
           new_config = current_config

       await repo.upsert(name, new_config, enabled=new_enabled)
       return {
           "name": name,
           "description": cls.description,
           "enabled": new_enabled,
           "config": new_config,
       }


   @router.post("/tools/configs/{name}/test")
   async def test_tool_config(name: str, request: Request) -> dict[str, Any]:
       """Run a connection test against the named tool's currently-saved
       Config (Decision 5). Only `web_search` and `fetch_url` are
       testable. Tool-side failures (constraint refusals, network
       errors) come through as `[error] [constraint] ...` strings in
       `output` — not HTTP 5xx — so the operator sees the agent's view.

       Named-tool isolation: `BuiltinToolProvider.get_tools` builds
       `cross_configs[Config]` by walking `_TOOL_CLASSES` in declared
       order and resolving from the FIRST tool name carrying that
       Config. For WebConfig, that's `http_request`. To honour
       Decision 5's "named tool's saved Config" semantics in the test
       endpoint, we re-key the input dict so EVERY tool sharing the
       named tool's Config class is given the named tool's saved row.
       This makes `cross_configs[NamedConfig]` carry the tested tool's
       saved config regardless of declaration order. Sibling tools
       with different Config classes get their own saved rows."""
       from the_one.tools.builtins import _TOOL_CLASSES, BuiltinToolProvider

       # 404 takes precedence over 400 — unknown name is not "untestable",
       # it's "doesn't exist".
       if name not in _TOOL_CLASSES:
           raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
       if name not in _TESTABLE_TOOLS:
           raise HTTPException(
               status_code=400,
               detail=f"Tool {name} does not support connection testing",
           )

       repo = await _tool_config_repo()
       saved = {c.name: c.config for c in await repo.list()}
       named_config_class = _TOOL_CLASSES[name].Config
       named_config = saved.get(name, {})
       # Re-key sibling tools sharing the named tool's Config class to use
       # the named tool's saved row (Decision 5 named-tool isolation).
       # Other tools keep their own saved rows.
       tool_configs_by_name = dict(saved)
       for tname, tcls in _TOOL_CLASSES.items():
           if tcls.Config is named_config_class:
               tool_configs_by_name[tname] = named_config

       provider = BuiltinToolProvider()
       tools = provider.get_tools(tool_configs_by_name, {})
       tool = next(t for t in tools if t.name == name)

       fixture_kwargs = {
           "web_search": {"query": "the one cli agent", "max_results": 5},
           "fetch_url": {"url": "https://example.com/"},
       }[name]

       start = time.perf_counter()
       output = await tool.execute(**fixture_kwargs)
       elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
       return {"output": output, "elapsed_ms": elapsed_ms}
   ```

   - 404 `detail` wording uses `"Tool not found: {name}"` for consistency with `update_agent` at api.py:107 (`f"Agent not found: {name}"`) and `get_knowledge_base` at api.py:170.
   - `elapsed_ms` is `float` (rounded to 2 decimals) so monkeypatched in-test runs that complete in <1ms surface as e.g. `0.42` instead of `0`.

4. **Test files** — write them in this order to keep iteration tight:

   1. `tests/test_enrich_schema_with_markers.py` (helper-only; no DB, no app, no async — fastest to red→green).
   2. `tests/test_factory_disable_enforcement.py` (factory unit). Use `aiosqlite.connect(":memory:")` + `ensure_schema` + the existing `AgentFactory` constructor pattern. The factory takes `agent_store`, `provider_store`, `encryptor`, and `tool_providers` — supply minimal stand-ins. Survey `tests/test_factory.py` for the existing fixture pattern (it patches `get_connection` and uses an in-memory `AsyncMock` provider). The new file mirrors that pattern but exercises real `ToolConfigRepository.list()` rather than the mocked `list_all`.
   3. `tests/test_api_tool_configs.py` — **mirror the established API-test pattern at `tests/test_db_api.py:16-35` exactly**: ASGITransport + AsyncClient + isolated DB + `with patch("the_one.interfaces.web.api.get_connection", return_value=conn)` + `test_app = FastAPI()` + `test_app.include_router(router)`. Do NOT use `from fastapi.testclient import TestClient` — that path triggers the real app's `lifespan` and is not what existing API tests use. Recommended fixture name: `client` (matches existing convention).

5. **`tests/test_factory.py` mock update** — three mocks at lines ~110, ~239, ~305 currently look like:

   ```python
   mock_tool_repo.list_all = AsyncMock(return_value={"shell": {"output_cap": 1000}})
   ```

   Each becomes:

   ```python
   from the_one.db.models import ToolConfig
   mock_tool_repo.list = AsyncMock(return_value=[
       ToolConfig(name="shell", config={"output_cap": 1000}, enabled=True),
   ])
   ```

   The `ToolConfig` import already exists in `the_one.db.models`. Each fixture's `return_value` switches from `dict[str, dict]` to `list[ToolConfig]`. The `TestResolverWiring` class at line 207+ asserts `captured["tool_configs"] == {"shell": {"output_cap": 1000}}` — that assertion stays valid because the factory's projection produces an identically-shaped dict for the resolver path. No assertion changes needed beyond the mock's return value.

6. **Run the verification block** above; paste the relevant `pytest -q` summaries into the L1 flight-log entry.

## Edge Cases

- **`_EmptyConfig`-bearing tools** (e.g., `shell_session_close`): `model_json_schema()` returns `{"properties": {}, "type": "object", ...}`. The enrichment helper's loop over `model_fields.items()` is empty; it returns the schema unchanged. The endpoint surfaces it cleanly — the L3 form renderer handles "no fields" by rendering "No operator-configurable settings.".
- **PUT body without `name` field**: the endpoint takes `name` from the URL path; ignores any `name` in the body. (Mirrors how `update_agent` at api.py:135 forces `data["name"] = name`.)
- **PUT with `config={}`** (operator wants to wipe back to defaults): under the REPLACE contract this is unambiguously "wipe to defaults" — `cls.Config.model_validate({})` succeeds against the Config's defaults; the saved row's `config` becomes the Config's default-dump. Codified by `test_put_with_empty_config_wipes_to_defaults`. The PUT body distinguishes "config absent" (preserve saved) from "config present but empty" (wipe).
- **Test endpoint mid-call exception** (e.g., backend raises `RuntimeError` not handled by the tool's `[error]` formatter): bubble up as 500. The `output`/`elapsed_ms` envelope only fits formatted-string failures; a hard exception is a bug, not a diagnostic. The L4 UI panel renders 500s with the standard error path.
- **Operator-saved Config that no longer validates** (e.g., a field was removed in a code change but a stale row still has it in the JSON): Pydantic v2's `extra="ignore"` default silently drops the unknown key; the resolver receives a clean dict. If the Config sets `extra="forbid"`, the resolver raises — which surfaces as a 500 from the `BuiltinToolProvider.get_tools` call. Acceptable: this is the operator-meaningful "your saved config is stale, re-save it" signal.
- **`POST /test` with a body** (operator UI sends `{}` reliably, but a stray client might send fields): we don't read the body. FastAPI tolerates an empty/None body for POST without a Pydantic body model. If we need stricter enforcement later, add a `body: dict = Body(default_factory=dict)` and assert `body == {}`. **L1 doesn't.**
- **`_TESTABLE_TOOLS` membership update**: future flights that add another testable tool (e.g., a connection test for an MCP source) update this set in one place. The set lives in api.py — it's the API's contract, not the tool's.
- **Schema dict mutation**: `_enrich_schema_with_markers` mutates `schema["properties"][name]` in place. Pydantic v2's `Model.model_json_schema()` returns a fresh dict per call, so callers are not at risk of the mutation persisting across requests — but document the in-place behaviour in the helper's docstring so a future caller doesn't pass in a cached dict.
- **Marker map entries**: any future marker class added to `the_one/tools/resolver.py` MUST be added to `_enrich_schema_with_markers`'s `marker_map`. The L1 implementation deliberately enumerates all 4 explicitly — there's no introspection trick to keep them in sync. CLAUDE.md "Tool Authorship Contract" addendum (L9) records this as a maintenance contract.
- **`list_all` callers**: `the_one/agent/factory.py:109` is the only caller in `the_one/`. After L1's switch to `list()`, `list_all` survives only as the resolver-facing convenience for any future caller that wants the dict shape. L1 does not delete it; the L0 leg specifically tested it (`test_list_all_omits_enabled`) and the resolver-facing API contract is preserved.
- **404-vs-400 ordering on `/test`**: the implementation checks `_TOOL_CLASSES` membership before `_TESTABLE_TOOLS`. Codified by `test_test_endpoint_rejects_unknown_tool` — if reordered, that test fails.

## Files Affected

- `the_one/agent/factory.py` — replace `list_all()` projection with `list()` + two derived structures; widen the registry-build filter.
- `the_one/interfaces/web/api.py` — extend repo import block with `ToolConfigRepository`; append `_tool_config_repo`, `_TESTABLE_TOOLS`, `_enrich_schema_with_markers` helpers; append 4 new route handlers under a `# ── Tool configs ──` section.
- `tests/test_factory.py` — update 3 existing mocks at lines ~110, ~239, ~305 from `mock_tool_repo.list_all = AsyncMock(...)` to `mock_tool_repo.list = AsyncMock(return_value=[ToolConfig(...), ...])`. Add `from the_one.db.models import ToolConfig` to the imports.
- `tests/test_factory_disable_enforcement.py` — new (5 tests).
- `tests/test_api_tool_configs.py` — new (14 tests).
- `tests/test_enrich_schema_with_markers.py` — new (7 tests).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new test files passing
- [ ] `make test-unit` green (modulo CSS-token deselect)
- [ ] `tests/test_factory.py` (or its location) confirmed green after the `list_all` → `list` swap; if any test asserted `list_all` was called, update + note in flight log
- [ ] L0 tests confirmed unchanged green (especially `test_list_all_omits_enabled`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
