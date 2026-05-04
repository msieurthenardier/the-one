# Flight: Tools Admin Section

**Status**: landed
**Mission**: [Built-In Tool System](../../mission.md)

## Contributing to Criteria

- [ ] The administration interface exposes a tool-management surface where each built-in tool can be enabled, disabled, and configured at the tool level, with verification controls (test buttons) for connection-style operations *(F6 ships the full admin surface)*
- [ ] The studio agent editor reflects the tool-level state — tool-level-disabled tools are unavailable to all agents and visibly inaccessible in the per-agent toggle UI — and exposes the agent-level override surface for per-tool constraint narrowing *(F6 wires the Studio Tools tab to the new admin state)*
- [ ] The new Tools admin section reflects the established design language and meets the M04 quality bar without alignment-flight rework *(F6 reuses the F4 admin section-nav + entity-tile + editor-section canon)*

---

## Pre-Flight

### Objective

Land the operator-facing tool-management surface that makes the F2-F5 tool-level config knobs editable from the UI. Adds a peer "Tools" section to the admin area (alongside System and LLM Providers), wires per-tool enable/disable + per-tool constraint editing + connection-test buttons for `web_search` and `fetch_url`, and updates the Studio Tools tab so tool-level-disabled tools are visibly unavailable in the per-agent picker AND so agents can narrow constraint values via the existing `AgentConfig.tool_overrides` shape.

The leg breakdown applies the F5 debrief's three methodology recommendations: (a) HAT rubric is operator-flow-explicit (one scenario per UX path: enable/disable, narrow a constraint, run a test button, agent override visible); (b) doc-refresh leg runs AFTER the Reviewer pass (was: before); (c) library-API drift checklist is in scope but limited (F6 is mostly vanilla JS + FastAPI — no new third-party deps).

### Open Questions

- [x] **Section placement** — peer to `system` and `providers` in the admin section nav (NOT nested under System). Mirrors LLM Providers' rationale: a distinct entity model with its own CRUD surface deserves its own section. *(see Decision 1)*
- [x] **Tool-level disable storage** — new `enabled INTEGER NOT NULL DEFAULT 1` column on `tool_configs` (schema v9). Cleaner than mixing admin metadata into the JSON `config` blob. Resolver / `BuiltinToolProvider.get_tools` filters disabled tools out before instantiation. *(see Decision 2)*
- [x] **Per-tool config form generation** — drive form rendering from `Config.model_json_schema()` (Pydantic v2 produces a JSON Schema with the `ui_hint`/`ui_choices` extras already wired in F4 + F5). One renderer handles all four Config classes (FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig). *(see Decision 3)*
- [x] **Agent-level override UI shape** — typed widget per field (dropdowns from `ui_choices`, number inputs with `ge`/`le` bounds, chip-list editor for list fields). Free-form JSON editor as a fallback when the operator wants to override a `Substitute`-marked field with arbitrary content. *(see Decision 4)*
- [x] **Connection-test buttons** — `web_search` (fixed query: `"the one cli agent"`) and `fetch_url` (fixture URL: `https://example.com/`). NOT `http_request` (operator-trusted; arbitrary methods can't be sensibly tested). NOT `download_file` (creates files; test would leak artifacts). *(see Decision 5)*
- [x] **Test button result surface** — inline panel below the button showing the tool's raw output (truncated to ~2KB if long). Same `[error] [constraint] ...` / `[200]\n...` format the agent sees, so operators reading the test output learn the agent's UX. *(see Decision 6)*
- [x] **Hash routing** — `#admin/tools` for the grid; `#admin/tools/{tool_name}` for the per-tool editor. Mirrors `#admin/providers/{id}` semantic. *(see Decision 7)*
- [x] **Studio Tools tab — disabled-tool surfacing** — disabled tools show in the per-agent grid with a `disabled` HTML attribute, a "Disabled by operator" tooltip, and a strikethrough on the name. Click is no-op. Agent's existing `enabled_tools`/`disabled_tools` data is preserved (no auto-stripping). *(see Decision 8)*
- [x] **Substitute-vs-Narrow agent UI distinction** — `Narrow`/`NarrowPrefix`/`NarrowSuperset` markers render as constrained widgets (the value MUST be within operator's bounds). `Substitute` markers render as free-form input (any value replaces operator's). Marker is read from the JSON Schema's `metadata` array. *(see Decision 9)*
- [x] **`ToolConfig` model widening** — add `enabled: bool = True` to the Pydantic model alongside the new SQLite column. Backward-compat: existing rows decode `enabled=True` (migration default). *(see Decision 10)*
- [x] **API endpoints** — `GET /api/tools/configs` (list all), `GET /api/tools/configs/{name}` (one), `PUT /api/tools/configs/{name}` (upsert), `POST /api/tools/configs/{name}/test` (run a connection test). The plural `/configs` distinguishes from the existing `/api/tools` (which lists tool names + descriptions). *(see Decision 11)*
- [x] **Doc-refresh ordering** — applies F5 debrief recommendation: doc-refresh leg runs AFTER the Reviewer pass, not before. Verifies the as-built code is the source of truth for the doc claims. *(see Decision 12)*
- [x] **Browser test scope** — **full coverage**. L7 ships Playwright tests for grid + editor save flow + test button + Studio disabled-tool visual + Studio agent override UI + deep-link routing. ~8-12 tests; matches the F4/F5 admin-area browser-test density.
- [ ] **Schema migration test pattern** — fresh `TestV9Migration` class vs reuse existing pattern. Resolved at L0 leg-design time by the architect.

### Design Decisions

**Decision 1 — Tools section is a peer of System and LLM Providers**:

```javascript
// admin.js
var categories = [
  { id: 'system', label: 'System' },
  { id: 'providers', label: 'LLM Providers' },
  { id: 'tools', label: 'Tools' }, // F6
];
```

- Rationale: Tools is a distinct entity model (19 builtin tools, each with its own Config schema, kill switch, and test surface). Nesting under System would conflate two different concerns (System = process-level admin; Tools = per-entity CRUD).
- Trade-off: adds a third top-level admin section; operator's mental model grows by one. Acceptable — the Tools surface is too large to inline into System.

**Decision 2 — `enabled` column on `tool_configs` (schema v9)**:

```sql
ALTER TABLE tool_configs ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
```

- Migration is idempotent (PRAGMA-check for the column before ALTER, mirroring F2's pattern at `the_one/db/schema.py:325-330`).
- Pydantic `ToolConfig` model gains `enabled: bool = True` (default keeps existing rows enabled post-migration).
- `BuiltinToolProvider.get_tools` consults the `enabled` field via the resolver — disabled tools are filtered out of the returned list. The `AgentFactory` then sees a smaller toolset; the agent's `is_tool_enabled` check becomes a second-pass filter (per-agent disable on top of operator disable).
- Rationale for separate column (not a JSON key in `config`): admin metadata (kill switch) is operationally distinct from constraint config (size caps, etc.). A separate column makes the `enabled=true/false` query trivial without JSON unpacking.
- Trade-off: schema migration touches the existing table; bumps version to v9. Reversible: `ALTER TABLE tool_configs DROP COLUMN enabled` (SQLite 3.35+).

**Decision 3 — JSON-Schema-driven form generation with server-side marker enrichment**:

**Architect-verified gap**: Pydantic v2's `Model.model_json_schema()` strips the resolver marker classes (`Narrow`/`NarrowPrefix`/`NarrowSuperset`/`Substitute`) from the output. The schema dump only surfaces `default`, `description`, `maximum`, `minimum`, `title`, `type`, `ui_choices`, `ui_hint` — `host_allowlist` (Narrow list) and `host_denylist` (NarrowSuperset list) are indistinguishable in the raw schema.

**Resolution**: server-side enrichment in `GET /api/tools/configs/{name}`. The endpoint walks `Config.model_fields[field_name].metadata` (Pydantic v2 surfaces marker instances here, even though they don't make it to JSON Schema), identifies the marker class, and injects an `x_marker: "Narrow"|"NarrowPrefix"|"NarrowSuperset"|"Substitute"|null` extra into each property. The JS form renderer reads `x_marker` to pick the constrained-vs-free-form widget shape.

Implementation site: `the_one/interfaces/web/api.py::get_tool_config` (new endpoint). Helper:
```python
def _enrich_schema_with_markers(schema: dict, config_class: type[BaseModel]) -> dict:
    from the_one.tools.resolver import Narrow, NarrowPrefix, NarrowSuperset, Substitute
    marker_map = {Narrow: "Narrow", NarrowPrefix: "NarrowPrefix",
                  NarrowSuperset: "NarrowSuperset", Substitute: "Substitute"}
    properties = schema.get("properties", {})
    for field_name, field_info in config_class.model_fields.items():
        if field_name not in properties:
            continue
        for marker in marker_map:
            if any(m is marker for m in field_info.metadata):
                properties[field_name]["x_marker"] = marker_map[marker]
                break
    return schema
```

The renderer then dispatches:
- `x_marker = "Narrow"` (int) → `<input type=number max={operator_value}>`
- `x_marker = "Narrow"` (list) → chip-list constrained to subset of operator's
- `x_marker = "NarrowPrefix"` (list) → path-prefix-checked chip list
- `x_marker = "NarrowSuperset"` (list) → chip-list that must contain operator's items
- `x_marker = "Substitute"` (any) → free-form input, no comparison
- `x_marker = null` (no marker, e.g., `redirect_cap`) → admin form: regular widget; agent form: hide the field entirely (operator-only field)

Single renderer handles all four Configs (FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig). New tools added in future flights get UI-for-free as long as their Config carries the marker metadata.

**Decision 4 — Typed widget per field for agent-level overrides**:

The Studio Tools tab gains a per-tool "narrow" panel that surfaces the same widget renderer as the admin Tools editor. The widget enforces `Narrow`-marked fields by:
- Reading the operator's resolved value (from `tool_configs.config`).
- Constraining the agent's input to be `<=` (for ints), subset (for `Narrow` lists), or superset (for `NarrowSuperset` lists).
- For `Substitute` markers: free-form input, no comparison.

Validation happens client-side (immediate feedback) AND server-side (resolver re-validates at `AgentFactory.create()` time — the existing F2 contract). The server-side check is the security boundary; client-side is UX.

**Decision 5 — Connection-test buttons (web_search + fetch_url; uses operator's resolved Config)**:

The test endpoint runs the tool with the **operator's currently-saved Config**, NOT a synthetic minimal one. If the operator has narrowed `web_search`'s `extra_allowed_hosts=[]` and DDG happens to require it, the test fails — and that's the intended UX: a failed test surfaces a misconfigured constraint, which is exactly what the operator needs to know. The test panel becomes a config-validity diagnostic, not just a smoke check.

Test inputs (fixture):
- `web_search` → `query="the one cli agent"`, `max_results=5`.
- `fetch_url` → `url="https://example.com/"`.



- `web_search`: button runs a fixed query (`"the one cli agent"`); displays the parsed `SearchResult` list (or "No results found." / `[error] ...`).
- `fetch_url`: button fetches `https://example.com/`; displays the readability+markdownify output.
- NOT `http_request`: operator-trusted; the request shape (method, body, headers) is too varied to test with a single button.
- NOT `download_file`: writes a file; test would leak artifacts; UX-questionable.
- NOT `shell` / `python_exec` / pty session tools: arbitrary code execution; test buttons would create operational risk.
- NOT filesystem tools: no externally-facing connection.
- F6's two test buttons cover the two F5 connection-style operations — meets the mission constraint without expanding scope.

**Decision 6 — Test result inline panel**:

Below each test button, an inline `<pre>` panel shows the tool's raw output (truncated to ~2KB if longer). Format matches what the agent sees — `[200]\n<body>`, `[error] [constraint] ...`, etc. This makes operators learn the agent's view directly, and surfaces real config issues (e.g., `extra_allowed_hosts` not yet set when testing against `localhost:8484`).

Two-phase UI: button click → spinner → result panel. Disable the button while the test is in flight (per-test idempotency, no double-fire).

**Decision 7 — Hash routing — `#admin/tools` and `#admin/tools/{name}`**:

```
#admin                  → admin section (default: system)
#admin/tools            → Tools grid
#admin/tools/web_search → Tools editor for web_search
```

Mirrors the existing `#admin/providers/{id}` pattern. The router's `replaceSub` call honors deep links — refreshing the page on `#admin/tools/web_search` lands the user back on the same editor.

**Decision 8 — Studio Tools tab — disabled-tool surfacing**:

In `the_one/interfaces/web/static/js/areas/studio/tools-tab.js`, the per-tool checkbox row gets two new visual states based on the tool's tool-level `enabled` value:

```html
<label class="tool-row tool-row-disabled" title="Disabled by operator">
  <input type="checkbox" class="tool-toggle" data-tool="..." disabled />
  <span class="tool-switch tool-switch-disabled"></span>
  <span class="tool-name tool-name-strike">tool_name</span>
  <span class="tool-desc">...</span>
</label>
```

CSS adds strikethrough on the name, dims the row, and makes the checkbox visually unclickable. The `disabled` HTML attribute is the source of truth (browsers respect it for click + keyboard).

Agent's existing `enabled_tools`/`disabled_tools` data is preserved (NOT auto-stripped). When the operator re-enables a tool, the agent's per-agent toggle state survives.

**Decision 9 — Substitute-vs-Narrow agent UI**:

The form renderer reads the field's marker from `model_json_schema()['$defs'][...].properties[field].metadata` (Pydantic v2 surface). Mapping:

| Marker | Widget shape | Validation |
|---|---|---|
| `Narrow` (int) | `<input type=number max={operator_value}>` | client + server |
| `Narrow` (list) | chip-list constrained to subset of operator's | client + server |
| `NarrowPrefix` (list of paths) | path-prefix-checked chip list | client + server |
| `NarrowSuperset` (list) | chip-list that must contain operator's items | client + server |
| `Substitute` (any) | free-form input typed to field's base type | server-only |

Server-side validation is the F2 resolver's existing `_check_narrow*` chain — already tested.

**Decision 10 — `ToolConfig.enabled: bool = True`**:

```python
class ToolConfig(BaseModel):
    name: str
    enabled: bool = True  # F6 — operator-level kill switch
    config: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
```

Default `True` means existing rows + post-migration rows are enabled-by-default. Operators must explicitly disable. The repository's `_row_to_model` decoder maps the `enabled` SQLite INTEGER column to the bool field.

**Decision 11 — API endpoint shapes**:

```
GET    /api/tools/configs              → [{name, enabled, config, ...}, ...]
GET    /api/tools/configs/{name}       → {name, enabled, config, schema, ...}  -- schema = Config.model_json_schema() for client-side form generation
PUT    /api/tools/configs/{name}       → {name, enabled, config, ...}  -- upserts
POST   /api/tools/configs/{name}/test  → {output, error, elapsed_ms}  -- runs a connection test (web_search OR fetch_url only)
```

The `GET /one` returning a `schema` field is the renderer's data source. Avoids embedding 19 schemas in the initial page bundle.

`POST /test` is a separate endpoint (NOT a query param on PUT) so it has its own permission shape if F7+ adds RBAC.

**Decision 12 — Doc refresh as separate L9 leg AFTER Reviewer pass** (F5 debrief recommendation):

Per F5 debrief recommendation 2, doc refresh moves to a **separate L9 leg that runs AFTER the Reviewer's batch sign-off**, not in L8 alongside verification. This removes the "doc author works from spec, not as-built" drift class that affected F4 and F5 L8 doc refreshes (4 stale claims in F5 alone).

**Concrete orchestration sequence** (Flight Director coordinates):
1. Implement L0-L7 autonomously (no commits).
2. L8 = integration verification + regression sweeps + browser tests (NO docs).
3. Spawn Reviewer over the L0-L8 batch.
4. If Reviewer passes: spawn Doc Author for L9 (docs-only — touches `agents.md`, `CLAUDE.md`, mission Open Questions).
5. Spawn second Reviewer over the L9 docs commit.
6. Single squashed commit covering L0-L9 + draft PR.

The two Reviewer passes reflect the two distinct concerns: code correctness (pass 1) and documentation accuracy against as-built code (pass 2). L9 cannot reference anything that doesn't exist post-pass-1.

### Prerequisites

- [x] M05 Flight 5 landed and merged to `main` (commit `e65077e`).
- [x] Schema is at v8 (verified `the_one/db/schema.py:9 CURRENT_VERSION = 8`); F6 introduces v9 via `enabled` column ALTER.
- [x] `the_one/tools/builtins.py::_TOOL_CLASSES` has 19 entries (post-F5).
- [x] `tool_configs` SQLite table exists (F2 L2); `ToolConfigRepository` ships `list/get/upsert/delete/exists` (F2 L2).
- [x] `AgentConfig.tool_overrides` field exists (F2 L1b).
- [x] All 4 tool Configs (`FilesystemConfig`, `ExecutionConfig`, `PythonExecConfig`, `WebConfig`) carry `ui_hint`/`ui_choices` metadata for dropdown fields (F4 + F5).
- [x] `_DEFAULT_USER_AGENT` and `default_user_agent: Substitute` field on `WebConfig` (post-F5 debrief).
- [x] Existing admin section's section-nav + entity-tile + editor-section primitives (F4 M04 design language) are stable.
- [x] uvicorn `--reload` wired in `docker-compose.yml` (F4 follow-up `a41789a`).
- [ ] No port/network conflicts — F6 introduces no new services.
- [ ] User approves leg breakdown (Phase 4 sign-off).

### Pre-Flight Checklist
- [x] All open questions resolved (13/14; 1 leg-design-time at L0 — schema migration test pattern)
- [x] Design decisions documented (12)
- [x] Prerequisites verified (8 of 9; 1 trivial)
- [x] Validation approach defined → see Verification section
- [x] Legs defined → see Legs section below

---

## In-Flight

### Technical Approach

**Order rationale (10 legs after pre-flight, executed in dependency order)**:

1. **L0 — Schema v9 migration + `ToolConfig.enabled` field.** Idempotent ALTER COLUMN; bump `CURRENT_VERSION` to 9; widen Pydantic model; update repo encode/decode. Existing F2-F5 tests pass unchanged. ~80 LoC + tests.
2. **L1 — Tool-level disable enforcement + `/api/tools/configs/*` endpoints + connection-test endpoint.** `BuiltinToolProvider.get_tools` filters disabled tools. New FastAPI routes for list/get/upsert/test. The `GET /one` returns the Config's `model_json_schema()` for client-side form rendering. Connection test runs `web_search` or `fetch_url` against fixture inputs. ~200 LoC + tests.
3. **L2 — Tools admin grid.** New section in `admin.js` (peer to system/providers); new `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` sub-module rendering all 19 tools as a tile/list with on/off toggles. Click navigates to per-tool editor. ~150 LoC + browser tests in L8.
4. **L3 — Per-tool config editor.** New `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` sub-module. JSON-Schema-driven form generation (one renderer for all 4 Configs). Save via `PUT /api/tools/configs/{name}`. Dirty-flag + beforeunload guards mirror F4 admin patterns. ~300 LoC + browser tests in L8.
5. **L4 — Connection-test buttons.** Inline button + result panel for `web_search` and `fetch_url` editor pages. Spinner + per-test disable. ~80 LoC.
6. **L5 — Studio Tools tab updates.** Disabled-tool visual states (`tool-row-disabled`, strikethrough, tooltip). Agent-level override UI surface — typed widget per Narrow/Substitute field, surfaced inline below each enabled tool's checkbox row. ~250 LoC + browser tests in L8.
7. **L6 — HAT (interactive; non-autonomous).** Operator drives the agent through 8 scenarios per Decision 5 / Studio surface. Inline fixes via spawned Developer if any UX gaps surface.
8. **L7 — Browser tests.** Playwright tests for: tools grid renders, tool toggle persists, per-tool editor save flow, connection-test button, agent narrowed override visible in Studio Tools tab, disabled tool unclickable in Studio. ~6-10 tests.
9. **L8 — Integration verification** (NO docs). Full unit + browser + AIAT smoke; F6 regression sweeps. Mission Open Questions closed.
10. **L9 — Docs refresh** (post-Reviewer; per F5 debrief recommendation 2). Doc-only commit updating `agents.md` + `CLAUDE.md` + mission Known Issues. Spawned AFTER the L0-L8 batch Reviewer signs off so docs reference as-built code. Second Reviewer pass over the docs commit before the F6 PR opens.

### Checkpoints

- [ ] **L0 schema migration landed** — v8 → v9; `enabled` column on `tool_configs`; `ToolConfig.enabled` Pydantic field; F2-F5 test suites pass unchanged.
- [ ] **L1 endpoints + filter shipped** — disabled tools excluded from `BuiltinToolProvider.get_tools`; 4 new routes; connection-test runs against fixture inputs.
- [ ] **L2 admin Tools grid landed** — section nav now has 3 entries; grid renders 19 tool tiles with toggles.
- [ ] **L3 per-tool editor shipped** — JSON-Schema-driven form for all 4 Configs; save via PUT.
- [ ] **L4 connection-test buttons** — `web_search` returns parsed `SearchResult` list; `fetch_url` returns markdown; result panel renders inline.
- [ ] **L5 Studio Tools tab updates** — disabled tools show strikethrough + tooltip; per-tool agent override UI surfaces typed widgets.
- [ ] **L6 HAT pass complete** — 8 operator scenarios validated; any UX issues fixed inline.
- [ ] **L7 browser tests** — Playwright suite green (modulo pre-existing env gap).
- [ ] **L8 integration verified** — full unit suite green (modulo pre-existing CSS-token red); F6 regression sweeps return zero unexpected matches.
- [ ] **L9 docs refreshed (post-Reviewer)** — `agents.md` + `CLAUDE.md` updated to match as-built; second Reviewer pass over docs commit signed off.

### Adaptation Criteria

**Divert if**:
- JSON-Schema-driven form generation hits a Pydantic v2 marker-extraction edge case (e.g., `metadata` key not surfaced in `model_json_schema()` output for some marker types). Fall back to a hand-written form per Config (4 forms total). Document as Decision-revision; L3 leg-design picks the alternative.
- Schema migration fails on existing dev databases that have leftover `tool_configs` rows from F5 HAT. Add a one-line cleanup script + revert path; document.
- Browser test environment (Playwright Chromium) remains unavailable. L7 falls back to manual operator verification per scenario; document.

**Acceptable variations**:
- Whether the "Tools" section label is `Tools` or `Tool Library` or `Tool Settings` — operator preference; default `Tools`.
- Whether the test result panel uses `<pre>` or a richer pretty-printed component — UX call at L4.
- Whether the agent override UI is inline below each tool row OR in a separate sub-tab — UX call at L5.

### Legs

> **Note:** These are tentative suggestions, not commitments.

- [ ] `00-schema-v9-tool-config-enabled` — Schema migration v8→v9: idempotent `ALTER TABLE tool_configs ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1`. Bump `CURRENT_VERSION` to 9. Widen `ToolConfig` Pydantic model with `enabled: bool = True`. Update `ToolConfigRepository.list/get/_row_to_model/upsert` to encode/decode the new field. **Update the existing `tests/test_db_migration.py` pin at line ~233** (`assert CURRENT_VERSION == 8` → `== 9`) AND add a new `TestV9Migration` class with parallel structure: fresh-v9 + v8→v9-with-rows. F2-F5 test suites pass otherwise unchanged (existing rows decode `enabled=True` via the column default). **Bonus folded in (per F5 debrief / mission Known Issue F1-2)**: drop `_ensure-playwright` from `up`/`rebuild` Makefile targets; keep only in `test-browser`/`hat`. ~5 lines; clears the L7 Playwright env gap before L7 runs. ~120 LoC + tests.

- [ ] `01-disable-enforcement-and-api-endpoints` — `BuiltinToolProvider.get_tools` consults the tool's `enabled` flag (via `tool_configs_by_name[name].get('enabled', True)` in `AgentFactory.create()`'s flow); disabled tools are filtered out before construction. **Update `ToolConfigRepository.list_all` to include `enabled`** in the returned per-name dicts (currently returns just `config`). New FastAPI routes in `the_one/interfaces/web/api.py`: `GET /api/tools/configs`, `GET /api/tools/configs/{name}` (returns enriched `schema` per Decision 3 — calls `_enrich_schema_with_markers(Config.model_json_schema(), Config)` to inject `x_marker` per field), `PUT /api/tools/configs/{name}`, `POST /api/tools/configs/{name}/test` (only accepts `web_search` or `fetch_url`; rejects others with 400; runs against operator's resolved Config per Decision 5). Tests cover: disabled tool not in returned tools list; agent's `is_tool_enabled` independent from operator's disable; PUT validates against the Config schema (Pydantic ValidationError → 400); test-endpoint runs through the actual tool with a fixture input; `_enrich_schema_with_markers` correctly identifies all 4 marker classes. ~250 LoC + tests.

- [ ] `02-tools-admin-grid` — Add `tools` to `admin.js`'s `categories` array. New `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` sub-module exposing `App.admin.renderToolsGrid(content, tools, callbacks)`. Renders all 19 tools as `.entity-tile` elements (mirrors `providers-grid.js`); each tile shows tool name, description, category badge, enabled-state toggle. Click navigates to `#admin/tools/{name}`. Toggle calls `PUT /api/tools/configs/{name}` with the existing config + flipped `enabled`. Hash routing: `#admin/tools` → grid; `#admin/tools/{name}` → editor. ~150 LoC.

- [ ] `03-per-tool-config-editor` — New `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` sub-module. Fetches `GET /api/tools/configs/{name}`, parses the returned JSON Schema, renders per-field widgets:
  - `int` + `ui_hint=dropdown` → `<select>` from `ui_choices`
  - `int` + `ge`/`le` → `<input type=number>`
  - `bool` → `<input type=checkbox>`
  - `list[str]` → chip-list editor (existing pattern from F5 `extra_allowed_hosts`)
  - `str` → `<input type=text>`
  
  Save via `PUT /api/tools/configs/{name}`. Dirty-flag + beforeunload guards mirror F4 admin (`provider-editor.js:127-149` reference). Back button navigates to `#admin/tools`. Section-nav clicks gated by dirty (existing `App.confirmDialog` pattern). ~300 LoC.

- [ ] `04-connection-test-buttons` — Inline test button + result panel on the per-tool editor for `web_search` and `fetch_url` ONLY. Other tools show no test button (per Decision 5). Click → `POST /api/tools/configs/{name}/test` with `{}` body (no params; backend uses fixture inputs); spinner during request; result rendered into `<pre>` below the button (truncated to 2KB if longer). Disable button while in flight; re-enable on response. Error path: any non-200 from test endpoint renders into the same panel. ~80 LoC.

- [ ] `05-studio-tools-tab-updates` — Edit `the_one/interfaces/web/static/js/areas/studio/tools-tab.js`. Two changes:
  1. **Disabled-tool surfacing** — for each tool row, fetch the tool's `enabled` state (callback param `disabledTools: Set<string>`); apply `tool-row-disabled` class + strikethrough + `disabled` attr + `Disabled by operator` tooltip when disabled.
  2. **Agent-level override UI** — for each enabled tool with a non-empty Config (i.e., NOT `_EmptyConfig`), render a collapsible "Narrow constraints" panel below the checkbox row. Inside the panel, render typed widgets (same renderer as L3) for each field, but with the marker dispatch (Narrow → constrained widget; Substitute → free-form). Initial values: agent's existing `tool_overrides[name]` if set; otherwise empty (no override). Save via the existing agent save flow — `tool_overrides` is already a field on AgentConfig; the editor's `collectFormData` reads it from a new `data-tool-override` attribute pattern.
  
  CSS additions for `tool-row-disabled` + collapsible-panel style. ~250 LoC.

- [ ] `hat-tools-admin-walkthrough` *(interactive; non-autonomous)* — Operator-driven HAT through 8 scenarios applying F5 debrief HAT-rubric (per-flow scenarios, not per-bug):
  1. Navigate to `#admin/tools` — grid renders all 19 tools with current enabled state.
  2. Toggle `web_search` from enabled → disabled via the grid; reload page; state persists.
  3. Open `#admin/tools/web_search` editor; narrow `timeout_seconds_max` from default to 10; save; refresh; values persist.
  4. Click test button on `web_search` editor → result panel shows `SearchResult` list (or `No results found.` if DDG rate-limits).
  5. Click test button on `fetch_url` editor → result panel shows markdown of `https://example.com/`.
  6. Open Studio → Haiku45 → Tools tab. Confirm `web_search` (still disabled from step 2) shows strikethrough + tooltip + un-clickable checkbox.
  7. Re-enable `web_search` via admin; refresh Studio Tools tab; row is interactive again. Agent's prior on/off state preserved.
  8. In Studio Tools tab, expand `http_request`'s "Narrow constraints" panel; narrow `extra_allowed_hosts` to `["localhost"]`; save agent; verify via `POST /api/agents/Haiku45` that `tool_overrides.http_request.extra_allowed_hosts == ["localhost"]`.
  9. In Studio Tools tab, expand `shell`'s "Narrow constraints" panel; ADD an entry to `command_denylist` (`NarrowSuperset` semantic — agent must contain operator's items + can add more). Verify the chip-list editor surfaces operator's existing entries as locked (un-removable) and only allows additions. Save agent; verify the saved override contains operator's items + new agent additions.

  Flight Director walks operator through each step. Inline fixes for any UX gaps spawned via Developer agent.

- [ ] `07-browser-tests` — **Full Playwright coverage** (operator's resolution). Tests in `tests/browser/test_flow_admin_tools.py` and `tests/browser/test_flow_studio_tools_overrides.py`:
  - **Admin Tools grid**: renders 19 tiles with current enabled state; toggle flips state via PUT; state persists across reload.
  - **Per-tool editor (admin)**: deep-link `#admin/tools/{name}` opens the editor; JSON-Schema-driven form renders typed widgets per `x_marker`; save triggers PUT and returns to grid; dirty-flag prevents accidental nav-away (mirrors F4 admin pattern).
  - **Connection-test buttons**: `web_search` test button populates result panel with `SearchResult` list; `fetch_url` test button populates with markdown of `https://example.com/`; non-test tools have no button.
  - **Studio disabled-tool visual**: when an admin disables `web_search`, the Studio Tools tab renders the row with strikethrough + tooltip + un-clickable checkbox; re-enabling restores interactivity.
  - **Studio agent override UI**: per-tool "Narrow constraints" panel collapsible; typed widgets render correctly per `x_marker`; save persists to `tool_overrides` (verified via API readback).
  - **NarrowSuperset semantic in UI**: operator-set entries on `command_denylist` show as locked chips in the agent-side editor; agent additions are removable.
  
  Playwright Chromium env gap pre-cleared by L0's Makefile fix (F1-2 resolution folded in). ~8-12 tests.

- [ ] `08-integration-verification` — **NO docs in this leg** (per Decision 12). Full unit suite green (modulo CSS-token red); F6 regression sweeps:
  ```bash
  rg -n 'enabled INTEGER NOT NULL DEFAULT 1' the_one/db/schema.py  # 1 (the migration line)
  rg -n 'GET /api/tools/configs\|PUT /api/tools/configs\|POST.*tools/configs.*test' the_one/interfaces/web/api.py  # 4 routes
  rg -n 'renderToolsGrid\|renderToolsEditor' the_one/interfaces/web/static/js/areas/admin/  # 2+
  rg -n 'tool-row-disabled\|tool-name-strike' the_one/interfaces/web/static/  # 2+ (CSS + JS)
  rg -n '_enrich_schema_with_markers' the_one/interfaces/web/api.py  # 1+ (enrichment helper)
  ```
  Mission Open Question for F6 (section placement) marked resolved. Append L8 entry to flight log. **Reviewer pass over L0-L8 batch happens AFTER L8 lands.**

- [ ] `09-docs-refresh` *(post-Reviewer)* — Runs AFTER the Reviewer signs off on the L0-L8 batch. Doc-only commit. Updates: `the_one/agents.md` (new Tools admin section description; F6 entries in the constraint-surface table; Studio Tools tab override-UI documentation; updated tool count if any new tools — none in F6); `CLAUDE.md` (admin section reference; Tool Authorship Contract section gets a "tool-level kill switch" addendum). Mission Known Issues update if HAT surfaced any small-model artifacts. **Second Reviewer pass over the docs commit** before the F6 PR opens. Two-Reviewer-pass protocol verifies docs match the as-built code from pass 1.

---

## Post-Flight

### Completion Checklist

- [ ] All legs landed (L0-L9; L6 is HAT, L9 is post-Reviewer docs)
- [ ] Schema v9 migration clean; F2-F5 tests unchanged
- [ ] `ToolConfig.enabled` end-to-end — admin disables, agent loses access
- [ ] 4 new API endpoints shipped + tested
- [ ] Tools admin section visible + functional
- [ ] Per-tool config editor renders all 4 Configs (FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig) without manual per-tool form code
- [ ] Connection-test buttons work for `web_search` + `fetch_url`
- [ ] Studio Tools tab marks disabled tools + surfaces agent override UI
- [ ] HAT pass complete; UX gaps fixed inline
- [ ] Browser tests green (or env gap documented)
- [ ] Default unit suite green (modulo CSS-token red)
- [ ] No regressions in F1-F5 surfaces
- [ ] `CLAUDE.md` and `agents.md` refreshed (POST-Reviewer ordering)
- [ ] Code committed; flight log updated; flight status set to `landed`

### Verification

**Static (grep / read):**

```bash
# Schema migration
docker exec the-one rg -n "ADD COLUMN enabled" the_one/db/schema.py  # 1
docker exec the-one rg -n "CURRENT_VERSION = 9" the_one/db/schema.py  # 1

# API endpoints
docker exec the-one rg -n "/api/tools/configs" the_one/interfaces/web/api.py  # 4 routes

# Admin sub-modules
docker exec the-one rg -n "renderToolsGrid\|renderToolsEditor" the_one/interfaces/web/static/js/  # 2+

# Studio updates
docker exec the-one rg -n "tool-row-disabled\|disabled-by-operator" the_one/interfaces/web/static/  # 2+ (CSS + JS)
```

**Dynamic (test suite):**

```bash
make test-unit
make test-browser
docker exec the-one pytest -m live tests/test_aiat.py

# Smoke: disable a tool, verify it doesn't appear in agent's toolset
docker exec the-one python -c "
import asyncio
from the_one.db.connection import get_connection
from the_one.db.repositories import ToolConfigRepository
from the_one.tools.builtins import BuiltinToolProvider

async def main():
    conn = await get_connection()
    repo = ToolConfigRepository(conn)
    await repo.upsert('web_search', config={'extra_allowed_hosts': []}, enabled=False)
    tool_configs = await repo.list_all()
    tools = BuiltinToolProvider().get_tools(tool_configs, {})
    names = [t.name for t in tools]
    assert 'web_search' not in names, names
    await repo.upsert('web_search', config={'extra_allowed_hosts': []}, enabled=True)
    print('OK disable enforcement')

asyncio.run(main())
"
```

**Manual (HAT):** L6 walkthrough — operator drives the agent through 8 admin/Studio scenarios.
