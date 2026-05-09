# Flight: Studio MCPs tab + inspector polish

**Status**: in-flight
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] **#7** — agent attaches MCP sources; tools become callable. F6 wired the runtime; F8 lands the operator UI for selecting which sources to attach AND which tools within each source the agent should see.
- [ ] **#8** — stable namespacing for collisions. F6's `mcp__{source}__{tool}` prefix scheme + 64-char ceiling already in production; F8's per-tool toggle UI exposes the namespaced names to operators.
- [ ] **#10** — graceful failure isolation. F8 surfaces the auth-required redirect-to-source-edit affordance when an attached source's tokens have expired (no auto-popup from the agent-editor).
- [ ] **#11** — automated coverage. Browser tests for attach/detach/per-tool/credential-override-with-`__MASKED__`-round-trip; unit tests for the override-schema reserved-key validation; binding Tier-2 HAT against live Cloudflare API MCP.
- [ ] **#12** — Settings, Studio MCPs tab, and source-edit Tools polish meet the M04/M06 design-language quality bar.

---

## Pre-Flight

### Objective

Three coordinated deliverables under one flight: (a) replace `mcps-tab.js`'s 22-line stub with the real per-agent attach + override + per-tool-toggle UI; (b) polish the existing source-edit Tools section with capability flags and collapsible input-schema views (the useful F7 leftovers absorbed per mission amendment); (c) bundle six small carry-forward maintenance items from the F6.5 + F6.6 debriefs that pair naturally with this UI work.

### Open Questions

- [x] Per-tool enable/disable storage shape? → **Extend `AgentConfig.mcp_overrides[source_name]` with reserved sub-keys `enabled_tools` and `disabled_tools`** alongside credential overrides. One field, one resolver call site. Reservation-validation in `_overrides.py` rejects operator field names that collide with the reserved keys (so operators can't accidentally claim `enabled_tools` as a credential field name). See Design Decision §1.
- [x] Tool catalogue discovery for the attach UI? → **Reuse `/api/mcp-sources/{id}/test/connect` wrapped in a closure-promise cache** in `studio.js`, mirroring the existing `fetchToolSchema` pattern at `studio.js:595-609`. No schema migration; no new endpoint; no new freshness contract. The Phase A fast path runs in 0.5–2s with cached tokens; closure cache makes tab re-opens instant. Auth-required surfaces as an inline notice with a redirect to the source-edit page — never an auto-popup from the agent-editor. See Design Decision §2.
- [x] Tier-2 HAT? → **Required, binding**. Per F6.5/F6.6 empirical pattern (4+ invisible-to-unit-tests bugs caught by HAT in F6.5 alone), OAuth-touching flights bind a HAT. F8 adds credential override surface + per-tool toggling — material new operator-facing surface. See Design Decision §6.
- [x] Scope shape? → **Bundle**: tab + polish + maintenance items in one flight. Maintenance bundle scoped to ~6 items at ≤30 LOC each; bundling reduces orchestration cost without coupling. See Design Decision §7.
- [x] Hash routing for per-source attach editor? → **`#studio/agents/{name}/mcps/{source-id}`** per mission spec. Source-id (not source-name) is stable across renames; the URL survives operator-side source renaming. See Design Decision §3.
- [x] App.areas array-shape contract from F6.6? → **Lock with a registration test** (don't refactor). F8 registers no new areas, but the F6.6 deviation (`areas: order` instead of `areas: areas`) made `App.areas` a public surface with `Array.prototype.find` semantics. A test that asserts the array shape prevents future regressions to dict-shape. See Design Decision §4.

### Design Decisions

**§1. Per-tool storage: reserved sub-keys in `mcp_overrides[source_name]` — un-prefixed tool names** — extend the existing dict shape with two optional fields (`enabled_tools` and `disabled_tools`) alongside credential overrides:

```python
mcp_overrides = {
  "github_mcp": {
    "bearer_token": "ghp_...",          # existing credential override
    "enabled_tools": ["create_issue"],  # NEW field — un-prefixed server-side names
    "disabled_tools": [],               # NEW field — un-prefixed server-side names
  }
}
```

`StdioMCPOverride` and `StreamableHttpMCPOverride` in `the_one/mcp/_overrides.py` extend with two optional fields: `enabled_tools: list[str] | None = None` and `disabled_tools: list[str] | None = None`. Pydantic v2 with the project's `extra="ignore"` default (per `_tool_provider.py:104`) accepts these alongside credential keys without collision; **NO operator-side reservation-validation is needed** — `mcp_overrides` is agent-side authored (via the F8 UI), and `MCPSource.secrets` (operator-side) is a structurally separate dict that doesn't collide with these reserved field names.

`MCPToolProvider.get_tools_for_agent` integrates the filter at the splice point between `list_tools()` returning un-prefixed `MCPTool` objects (line 229) and the wrap loop that builds prefixed `MCPClientTool` instances (around line 256). Filter on `mt.name` (un-prefixed); the per-tool 64-char ceiling check at line 257 runs only for tools that pass the filter (a disabled tool that would have failed the 64-char check is skipped silently, no spurious warning). **Storage convention: un-prefixed server-side tool names** in both `enabled_tools` and `disabled_tools` (matches `mt.name` at the filter site, survives source rename, no double-bookkeeping). The UI shows the prefixed display name (`mcp__src__foo`) for operator clarity, but stores the un-prefixed value (`foo`) in the override.

- Rationale: one field, one resolver call site; un-prefixed storage matches the server's canonical name and simplifies the filter logic; no parallel field; `mcp_overrides`'s purpose ("per-source overrides keyed by source name") generalizes naturally from credentials to per-tool toggles.
- Trade-off: a future MCP server with a credential field literally named `enabled_tools` or `disabled_tools` would force a refactor — but no current MCP servers in scope (GitHub, Cloudflare API, filesystem, fetch) use those names. Acceptable.

**§2. Tool discovery: reuse `/test/connect` + closure-promise cache** — `studio.js` adds a `fetchMcpSourceTools(sourceId)` factory next to `fetchToolSchema` (same promise-cache shape, keyed by `sourceId`, lifetime = agent-editor-session). POSTs `/api/mcp-sources/{id}/test/connect`; `{status: "ok"}` resolves with `tools[]`; `{status: "auth_required"}` rejects with a typed error the UI renders as an inline notice "This source needs Test/auth on the source-edit page first" with a link to the source-edit page; `{status: "error"}` rejects and the UI renders "Could not list tools — Refresh" (and the cache entry drops so retry works). The agent-editor MUST NOT auto-trigger the OAuth popup — that's the source-edit page's affordance.

- Rationale: zero schema change; reuses tested code path; live-fresh tools (no staleness contract). The Phase A fast path is bounded (cached-token connect ~0.5-2s); closure cache makes re-opens instant. No pool churn — `/test/connect` builds a transient `MCPClient` (`api.py:874`), bypassing the F4 pool entirely.
- Trade-off: opening agent-editor tab repeatedly across sessions costs one `/test/connect` per source per session. Acceptable; pattern matches `fetchToolSchema`'s existing per-session caching at `studio.js:595-609`. The factory accepts a `forceRefresh: boolean` flag (extending the closure-cache pattern) so a "Refresh tools" button can bypass cache by call rather than by side-effecting the cache from outside.
- Inherited risks (architect consult): Phase B leakage on silent token expiry and parallel `_evict_all_for_source` thrashing chat warm-pool entries are inherited from `/test/connect`'s F6.5 design; F8 doesn't introduce them but does multiply opportunities to trigger them by adding tab-open as a new caller. If thrashing surfaces in HAT, lift the cache key to include a token-version so retries don't trigger pool evictions (covered in Adaptation Criteria's second "Divert if"). If a future flight bolts on a cached `/api/mcp-sources/{id}/tools` endpoint, mission #7 picks up a staleness-vs-mission-criterion contract that doesn't exist today — document and defer at that point.

**§3. Hash routing: `#studio/agents/{name}/mcps/{source-id}`** — source-id is stable across renames; the URL survives operator-side source renaming where source-name does not. Agent-name (already in URL) is also stable until rename, but agent rename invalidates URLs project-wide already (existing pattern). Detail panel renders the per-attachment editor for that source; absent fragment renders the multi-attach chip-list.

- Rationale: source-id is the canonical key in `AgentConfig.mcp_source_ids` and `MCPSourceRepository.get(id)`; stable URLs reduce broken-link surprises.
- Trade-off: source-id is uuid4-hex (less readable than name). Operators rarely type-share these URLs; the deep-link is for in-session navigation, not human-shared. Acceptable.

**§4. `App.areas` array-shape contract test** — F6.6 L0 deviation (`areas: order` vs `areas: areas`) made `App.areas` a public surface with `Array.prototype.find` semantics. F8 registers no new areas but inherits this contract. Add a browser test that asserts: (a) `Array.isArray(window.App.areas)`, (b) `window.App.areas.length > 0` (catch the trivially-passing-empty-array case), (c) every entry has `id`, `label`, and `order` keys, (d) `window.App.areas.find(a => a.id === 'studio')` returns the studio area descriptor. The test prevents a future "tidy-up" refactor from re-introducing the dict shape and re-breaking the 4 `test_oauth_modal_flow.py` tests F6.6 fixed.

- Rationale: surgical fix — one test locks the contract documented in F6.6's flight log.
- Trade-off: minor — adds a test that documents an invariant rather than verifies behavior. Justified because the invariant has already been broken once and was costly to debug.

**§5. Capability flags + input-schema polish** — the `/test/connect` response gains a `capabilities` field sourced from `MCPClient.server_capabilities` — **already a public property** at `client.py:189-194` (set during connect at line 397 from `result.capabilities`). No `MCPClient` changes; just `api.py::test_mcp_connection` reads `client.server_capabilities` after `list_tools()` and includes it in the response. `mcp-server-editor.js:130-138`'s Tools section gets two enhancements: (a) a one-line status `Server supports: tools, resources, prompts` (or whatever subset the server announced) above the tools list; (b) each tool's `<details>` panel gains a nested `<details>Input schema</details>` with the raw JSON pretty-printed inside a `<pre>` block. No form-builder; no separate inspector page.

- Rationale: tiny scope; reuses the existing public capabilities property; absorbs the useful parts of former F7 without re-introducing the developer-tool surface F7 was reframed away for being.
- Trade-off: the `capabilities` field on the `/test/connect` response is a public API addition; future spec revisions adding capability flags will surface them automatically (no client-side allowlist).

**§6. Binding Tier-2 HAT against live Cloudflare API MCP** — Per F6.5/F6.6 precedent. F8's HAT verifies: register source → click Test → consent flow → click Test again → tools render with capability flags + collapsible schema → open agent editor → MCPs tab → select source → tool list renders with checkbox group → toggle two tools off → save → build agent → verify agent's tool registry contains exactly the enabled tools (and NOT the disabled ones) → run a chat tool call against an enabled tool → verify result. Cycle credential override (e.g. set a per-agent `bearer_token` substitution) with `__MASKED__` round-trip in the save → reload → re-edit cycle.

- Rationale: F8 introduces material operator-facing surfaces (attach UI, per-tool toggles, credential override save flow). Without HAT, "agent registry contains exactly the enabled tools" has no live verification; the F6.5 lesson (4 bugs invisible to unit tests) applies.
- Trade-off: ~1 hour of operator time. Justified per empirical pattern.

**§7. Maintenance bundle in L0** — six small carry-forward items from F6.5/F6.6 debriefs that pair naturally with F8's MCP-area work. Ordered docs-first / code-second for review-surface clarity:

1. **F6.6 #A4** — Add `Raises:` block to `MCPClient.connect()` docstring (~6 lines, docs only).
2. **F6.6 #A5** — Codify connect() exception translation contract in `mission.md` (~5-7 lines, docs only).
3. **F6.6 #A7** — Document `tests/test_mcp_pool.py` exclusion rationale in CLAUDE.md testing section (~4 lines, docs only).
4. **F6.6 #A6** — Investigate + document the 306-deselected pytest count. The likely source is `pyproject.toml::addopts = "-m 'not live and not browser and not pixel'"`. Verify by running `pytest --collect-only -q -m "live or browser or pixel"` to see the breakdown per marker, then add a comment in `pyproject.toml::addopts` showing the per-marker count math (e.g., `# 306 deselected: live=N, browser=M, pixel=K`) so future contributors see the breakdown without re-deriving (config + docs).
5. **F6.5 #7** — Add a fixture-based cross-check test that fails when `MCPSourceTokenStorage.set_tokens` writes a `secrets` key not present in `OAUTH_MANAGED_SECRET_KEYS`. Construct an `OAuthToken` with every optional field populated; call `set_tokens` against a recording stub; assert `set(secrets.keys()) - existing_secrets <= OAUTH_MANAGED_SECRET_KEYS`. Cheap, no production code change, fails loud when a future PR adds a key write without updating the frozenset (test only).
6. **F6.6 #A2** — Migrate `tests/test_mcp_pool.py:36-39`'s `requires_bwrap = pytest.mark.skipif(...)` to a true pytest marker `pytest.mark.requires_bwrap`, register it in `pyproject.toml::[tool.pytest.ini_options]::markers`, extend `addopts` from `-m 'not live and not browser and not pixel'` to `-m 'not live and not browser and not pixel and not requires_bwrap'`, and update the `--ignore=tests/test_mcp_pool.py` documented runbook pattern in any current-state docs that reference it (the directive lives only in F6.5/F6.6 flight artifacts; no `pyproject.toml`/`Makefile`/CI config carries it — verified at design time). Result: `tests/test_mcp_pool.py`'s 10 pure-unit tests run by default; the 2 bwrap-dependent tests at lines 322 and 354 skip cleanly via the marker (config + tests).

- Rationale: each item is independent and ≤30 LOC; bundling avoids the orchestration cost of a separate maintenance flight; pairing with F8's MCP-area work means the bundle's reviewer has the same context window as the F8 reviewer.
- Trade-off: a partial-completion of L0 lands as one mixed-state leg rather than 6 cleanly-separable legs. Acceptable per F6.6 precedent.

### Prerequisites

- [x] F6.6 landed and merged to main (commit `a375f33`).
- [x] F6 runtime in production: `MCPToolProvider.get_tools_for_agent` already filters per-source via `mcp_overrides`; F8 extends the filter logic but builds on the existing dispatch.
- [x] F6.5 Test connection endpoint at `/api/mcp-sources/{id}/test/connect` in production; F8 extends its response shape with `capabilities`.
- [x] Override schemas at `the_one/mcp/_overrides.py` with `StdioMCPOverride` + `StreamableHttpMCPOverride`; F8 extends both with reserved keys.
- [x] `mcp-server-editor.js` Tools section scaffold from F6.5 L4 (lines 125-138); F8 polishes it.
- [x] `studio.js`'s `fetchToolSchema` closure-promise cache pattern (lines 595-609) — F8's `fetchMcpSourceTools` mirrors this shape.
- [ ] Live Cloudflare API MCP source registered in dev environment (for L4 HAT) — operator's existing `cloudflare_api` source from F6.5 HAT should still work.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (one operator-side check at HAT time)
- [x] Validation approach defined (unit + browser + binding HAT)
- [x] Legs defined

---

## In-Flight

### Technical Approach

**L0 (maintenance bundle)**: six independent edits in one leg. Each item has its own AC; bundle reduces orchestration cost. ~150-200 LOC across ~8-10 files.

**L1 (backend extensions)**: three coordinated changes:
- `the_one/mcp/_overrides.py` — extend `StdioMCPOverride` + `StreamableHttpMCPOverride` with `enabled_tools: list[str] | None = None` and `disabled_tools: list[str] | None = None` fields. No reservation-validation needed (per Design Decision §1: `mcp_overrides` is agent-side, no collision surface against operator-authored `MCPSource.secrets`).
- `the_one/mcp/_tool_provider.py::MCPToolProvider.get_tools_for_agent` — splice in the per-source filter **between line 229 (`mcp_tools = await client.list_tools()`) and line 256 (the wrap loop that builds prefixed `MCPClientTool` instances)**. Filter on un-prefixed `mt.name`. Semantics mirror `AgentConfig.is_tool_enabled`: if `enabled_tools` is non-None, only those tools pass; `disabled_tools` is always subtracted. The 64-char ceiling check at line 257 runs only for tools that pass the filter — a disabled tool that would have failed the ceiling is skipped silently with no spurious warning.
- `the_one/interfaces/web/api.py::test_mcp_connection` — extend the `{status: "ok", tools: [...]}` response with a `capabilities` field sourced from `client.server_capabilities` (already a public property at `client.py:189-194`, populated during connect at line 397). Single-line addition to the response dict at `api.py:876-886`.

L1 unit tests:
- Override-schema acceptance test: `StreamableHttpMCPOverride(enabled_tools=["a","b"], disabled_tools=["c"], bearer_token="t")` validates cleanly with all four fields.
- Provider filter — `enabled_tools` allowlist: source with tools `["read", "write", "delete"]` and `mcp_overrides={"src": {"enabled_tools": ["read"]}}` produces an agent registry containing only `mcp__src__read`.
- Provider filter — `disabled_tools` denylist: same source with `{"disabled_tools": ["delete"]}` produces a registry containing `mcp__src__read` + `mcp__src__write`.
- Provider filter — both set (intersection): `{"enabled_tools": ["read", "write"], "disabled_tools": ["write"]}` produces only `mcp__src__read`.
- Provider filter edge cases: empty `enabled_tools` list (zero tools registered), `disabled_tools` naming a tool not present (no-op).
- `/test/connect` capabilities test: response contains `capabilities` field matching `MCPClient.server_capabilities`'s shape (e.g. `{"tools": {}, "resources": None, ...}`).
- `/test/connect` capabilities edge case: server announcing `{tools: {}, resources: None}` produces `capabilities.resources is None` in the response (no key invention; preserve `model_dump`'s shape).

**L2 (source-edit Tools section polish)**: UI-only on top of L1's capabilities API extension.
- `mcp-server-editor.js::handleTestConnection` reads the `capabilities` from the response and renders a one-line status `Server supports: tools, resources, prompts` (filtering to capabilities the spec actually defines; ignore unknown keys).
- Each tool's `<details>` panel gains a nested `<details>Input schema</details>` element with `<pre>` containing `JSON.stringify(tool.input_schema, null, 2)`.
- CSS: re-use `var(--font-family-mono, monospace)` for the schema view; respect `--surface-2` background.

L2 browser tests: capability flags render correctly for a server with `{tools: true, resources: true}`; collapsible schema view opens/closes; schema content is the exact JSON the API returned.

**L3 (agent-editor MCPs tab — the bulk)**:
- `studio.js` adds `fetchMcpSourceTools(sourceId, {forceRefresh: false})` factory mirroring `fetchToolSchema`. Closure-cached promises; cache is per-editor-session (cleared on agent-editor close/reopen). `forceRefresh: true` deletes the cache entry before invoking the fetch so retries land on a fresh promise.
- `mcps-tab.js` rewrite:
  - Multi-attach chip-list: rendered from `/api/mcp-sources` (a separate fetch from L0 sources). Each chip shows the source name + transport-type badge; click toggles attach state.
  - Empty-state: when no MCP sources are registered, show a call-to-action linking to `#studio/mcp-sources` with text "No MCP sources registered yet. Add one in MCP Sources."
  - Per-attachment editor: rendered when the user clicks a chip OR navigates to `#studio/agents/{name}/mcps/{source-id}`. **URL-to-key translation**: the URL carries `source-id` (uuid, stable across renames); the editor resolves source-id → `MCPSource` via the chip-list's already-fetched source list, then uses `source.name` as the key for `mcp_overrides[source_name]` reads/writes. The lookup happens at editor-mount time, not on every save. Two sub-sections:
    - **Tools** — checkbox group rendered from `fetchMcpSourceTools(sourceId)`. Each checkbox writes to `mcp_overrides[source_name].{enabled_tools,disabled_tools}` via `collectFormData`. "Refresh tools" button calls `fetchMcpSourceTools(sourceId, {forceRefresh: true})`.
    - **Override credentials** — renders fields per `StdioMCPOverride`/`StreamableHttpMCPOverride` schema (using F6 L5 form helpers `App.adminFormHelpers`). `__MASKED__` sentinel preserves existing values on save.
- Auth-required handling: `fetchMcpSourceTools` rejection with `auth_required` renders an inline notice "This source needs Test/auth on the source-edit page first" with a link to `#studio/mcp-sources/{source-id}`.
- Hash routing: hook into the existing `App.router` (`app.js:284-290`) for `#studio/agents/{name}/mcps/{source-id}` deep links.
- Save flow: `studio.js::collectFormData` extends to walk the new `[data-mcp-override-source][data-mcp-override-field]` selectors into `mcp_overrides` (mirrors the existing tool-override walking pattern from F6 L5).

L3 includes its browser tests (folded in per F6 L4 precedent — UI flight where browser tests are the natural home for the leg's verification surface):
- attach a source → save → reload → still attached
- detach → save → reload → no longer attached
- toggle two tools off → save → reload → toggles preserved
- credential override save with `__MASKED__` round-trip — operator types `bearer_token=t1`, saves, reopens (sees `__MASKED__`), saves again without retyping, value preserved
- empty-state when no MCP sources are registered
- hash routing: visit `#studio/agents/X/mcps/Y` directly → editor renders for source Y
- auth-required notice: a source with no tokens triggers the inline redirect-to-source-edit notice (NO popup auto-opens)
- App.areas array-shape lock: `Array.isArray(window.App.areas)` and `window.App.areas.find(a => a.id === 'studio')` returns the studio descriptor

**L4 (Tier-2 HAT)** — interactive verification against live Cloudflare API MCP:
1. Operator registers/uses an existing Cloudflare API MCP source (`https://mcp.cloudflare.com/mcp`).
2. Click Test on the source-edit page → consent flow if needed → tools list renders WITH capability flags one-liner above + collapsible input schemas under each tool description.
3. Open agent editor for an existing test agent → MCPs tab.
4. Verify empty-state of the tab if the agent has no `mcp_source_ids`.
5. Select the Cloudflare source via chip click → editor renders → tool checkbox group populates.
6. Toggle off 2-3 tools (uncheck their boxes) → Save.
7. Reload the agent editor → verify the same toggles are preserved.
8. Cycle credential override: set a per-agent `bearer_token` (or stdio env-var override for a different source if more practical) → Save → reload → field shows `__MASKED__` → Save again without retyping → reload → value still preserved.
9. Trigger an agent build (start a chat session) → verify agent's tool registry contains exactly the enabled tools (NOT the disabled ones). **Verification path**: the chat UI's WebSocket `tool_call` event payload carries `available_tools` (per F6.5 inspector groundwork). Open the browser devtools' WebSocket inspector during the first agent message; the `available_tools` list MUST contain only the enabled tools' prefixed names. Disabled tools' prefixed names MUST be absent. (If the WebSocket inspection is awkward, inline a 5-LOC debug endpoint `GET /api/agents/{name}/tools` in L1 that returns the registered tool list — implementer's discretion at L1 design.)
10. Run one chat tool call against an enabled tool → verify success.
11. Verify the disabled tool's absence from the LLM's tool list by inspecting the same `available_tools` payload from step 9 (no separate chat call needed).

Caplog gate: 0 occurrences of `MCPClient.disconnect` warnings across the HAT (matches F6.6 baseline).

### Checkpoints

- [ ] **L0 landing**: 6 maintenance items shipped; full unit suite green; pytest deselect count documented; `test_mcp_pool.py` re-included in default run (modulo legitimately-skipped bwrap tests).
- [ ] **L1 landing**: override-schema validates reserved-key collisions; provider-filter respects `enabled_tools`/`disabled_tools`; `/test/connect` returns `capabilities`; ≥5 new unit tests, all passing.
- [ ] **L2 landing**: source-edit Tools section renders capability flags + collapsible schemas; ≥2 new browser tests, all passing.
- [ ] **L3 landing**: agent-editor MCPs tab is no longer a stub; attach/detach/per-tool/override save flows pass ≥7 browser tests; App.areas array-shape lock-test passes; hash routing works for direct deep links.
- [ ] **L4 landing**: HAT all 11 steps pass; caplog gate clean; any inline fixes captured in flight log.

### Adaptation Criteria

**Divert if**:
- HAT (L4) reveals a regression in F6's tool-routing dispatch when the new `enabled_tools`/`disabled_tools` filter applies. Bug-fix inline; do not ship F8 with regressions to F6 paths.
- HAT reveals parallel `_evict_all_for_source` thrashing chat warm-pool entries (architect-flagged risk #2 from the tool-discovery consult). If thrashing surfaces, lift the closure cache key to include a token-version so retries don't trigger pool evictions.
- L3 implementation trends past 1000 LOC (excluding folded browser tests). Branch out a new leg L3b for the per-attachment editor surface; keep L3 as multi-attach chip-list + hash routing only.

**Acceptable variations**:
- L0 maintenance items 5 (`OAUTH_MANAGED_SECRET_KEYS` cross-check test) implementation shape — fixture-recording stub vs `MagicMock(set_tokens)`; either is acceptable so long as the test fails when `set_tokens` writes a key absent from the frozenset.
- L2 capability-flag rendering format — "Server supports: tools, resources" vs a row of pill-shaped chips vs a tooltip; implementer's discretion within the design-language constraints.
- L3 chip-list visual treatment — chip-list, table, or vertical list; pick what matches existing Studio patterns for similar multi-select.


### Legs

> **Note:** Tentative. Lock per-leg as designed.

- [x] `00-maintenance-bundle` — 6 carry-forward items from F6.5 + F6.6 debriefs; ~150-200 LOC, parallel-safe with L1+.
- [x] `01-overrides-and-capabilities` — Schema extension for reserved keys + provider filter integration + `/test/connect` capabilities; ~250-350 LOC, ≥5 new unit tests.
- [x] `02-source-edit-tools-polish` — UI on top of L1: capability flags one-liner + collapsible input-schema; ~200-300 LOC, ≥2 new browser tests.
- [x] `03-agent-editor-mcps-tab` — Replace stub with attach + override + per-tool toggle UI + hash routing + App.areas lock-test + browser tests folded in; ~700-900 LOC.
- [ ] `04-hat-cloudflare-attach-and-toggle` — Tier-2 HAT against live Cloudflare API MCP; 11-step procedure; binding per Design Decision §6.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing inside `docker compose exec the-one pytest -q --timeout 120` (full suite — pre-existing bwrap failures noted, no new ones)
- [ ] Browser tests passing inside `docker compose exec the-one pytest tests/browser/ -q --timeout 120 -m browser`
- [ ] HAT (L4) signed off
- [ ] No new mission known-issues introduced
- [ ] F6.5 + F6.6 debrief action items 1, 4, 6, 7 closed (the 6 bundled items)
- [ ] CLAUDE.md updates for new conventions (per-tool toggle storage shape, capability-flag surface)

### Verification

- **Maintenance**: each L0 item verified by its own AC (Raises docstring present; mission.md F-contract entry present; pytest-deselect-count documented; etc.).
- **Backend**: override schema validators raise on reserved-key collision; provider filter produces an agent registry containing exactly the operator-enabled tools per attached source; `/test/connect` returns `capabilities` for streamable-http sources.
- **UI polish**: source-edit page Tools section renders capability flags + collapsible input schemas after a successful Test connection.
- **Attach UI**: agent-editor MCPs tab is functional end-to-end — attach, detach, per-tool toggle, credential override with `__MASKED__` round-trip, empty-state, hash routing, auth-required redirect.
- **HAT**: all 11 steps pass against live Cloudflare API MCP with caplog gate clean.
