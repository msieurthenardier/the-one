# Leg: studio-state-route-data

**Status**: landed
**Flight**: [Agents on the library](../flight.md)

## Objective
A behaviour-free restructure, done in two steps.
1. Inside `studio.js`, replace the cross-section closure variables with one shared `state` object owned by the shell.
2. Move four sections out of `studio.js` into their own modules, `studio-route`, `agent-data`, `library-pane` and `library-groups`. Each follows the `providers-section.js` ctx precedent.

The DOM, behaviour and every test outcome stay identical.

## Context
- **Flight DD1.** Legs 02-03 are a pure restructure: any visible or test-behaviour change is a defect. Static pins that read `studio.js` text are retargeted to the new modules deliberately, never relaxed. Leg 03 moves the editor modules afterwards, onto the same `state` object.
- **The precedent:** `js/areas/studio/providers-section.js:1-30`. `App.studio.providersSection.create(ctx)` returns a handle, the module reaches studio only through `ctx`, and studio creates it at about `studio.js:614-627`.
- **`studio.js` map** (planning survey, at `dbcd458`, unchanged at `9369fcc`):

| Lines | Section |
|---|---|
| 18-117 | `serializeState` |
| 157-355 | `hydrateState`, which calls about 13 `this._*` hooks |
| 357-419 | init state on `self.*`, plus the closure variables `dirty`, `snapshot`, `tabHandle`, `selectSeq`, `editorGen` (`:377-381`) |
| 421-501 | the MCP, connector and KB-create closure variables, exposed through `Object.defineProperty` getters on `self` |
| 508-532 | layout hosts (`agentsListHost`, `libraryListHost`, `sectionContentEl`, `editorEl`) |
| 534-1040 | the Library list (`providersCache`, the pane state, the providersSection ctx, `loadLibrary`, `reloadLibrary`, `createLibraryList`, `renderLibraryEmpty`) |
| 1052-1354 | knowledge glue (create view, detail, the 5 s poll) |
| 1356-1547 | MCP-section glue |
| 1549-1684 | connector glue |
| 1686-1764 | the pending-item rule (`PENDING_KINDS`) |
| 1979-2226 | API wrappers (agents, tools, mcp, rules, notes, self-config, credentials, KB, providers) |
| 2228-2366 | caches (`_schemaPromiseCache`, `_mcpSourceToolsCache`), `fetchMcpSourceTools`, `fetchToolSchema` |
| 2368-2476 | `loadAll`, 7 store subscriptions, `showLoadAllError` |

  The rest (the Agents list, selection, the editor controller, form data, the model picker, pending-agent, boot) stays in `studio.js` for leg 03.
- **The riskiest coupling** (design review):
  - `serializeState`, the `defineProperty` getters, `checkDirty` and `collectFormData` read the closure variables by name;
  - `doSelect` and `loadAll` depend on call-time ordering with `selectSeq` and `editorGen`;
  - `dirty` has about 32 assignment sites.

  A module must read and write `state.x` at use time and **never cache it in a local variable**. One missed rename fails silently, which is why step 1 runs the full gate before anything moves.

## Inputs
- Leg 01 landed (`scripts/ui_capture.py` only). `studio.js` is unchanged since `dbcd458`.

## Outputs
- **`studio.js`**: a shell with the `state` object and the remaining sections, roughly 2400 lines after this leg (≤ 800 after leg 03).
- **New modules:** `js/areas/studio/studio-route.js`, `agent-data.js`, `library-pane.js`, `library-groups.js`. `library-groups` may instead be three files (`knowledge-glue.js`, `mcp-glue.js`, `connector-glue.js`) if one file would exceed 800 lines.
- **`index.html`**: the script tags, in dependency order, before `areas/studio.js`.
- **Retargeted pins:** the script-count pin, `test_store_static.py`, `test_tool_categories.py` (only if `App.toolCategories.byCategory` moves; it is used by the editor, so it probably stays), `test_ui_guards.py` sink rows (moved, not added), `tests/_ui_ownership_allowance.py` rows (moved).

## Acceptance Criteria
- [ ] **Step 1, the `state` object.** `studio.js` declares one `var state = { dirty, snapshot, tabHandle, selectSeq, editorGen, … }` in `init`, holding:
  - every closure variable that more than one section reads or writes;
  - the MCP, connector and KB-create variables that today sit behind the `defineProperty` getters, which now delegate to `state`.

  Every reference becomes `state.x`. No module or function caches `state.x` in a local variable across an async boundary.
- [ ] **Step 1 gate, before any file moves:** `make test-unit` and the `agents`, `library`, `mcp`, `routing` and `shared` browser lanes run under netns and pass. The flight log records the results as the step-1 checkpoint.
- [ ] **Step 2, the moves.** These sections move out, behaviour-free:
  - `serializeState`/`hydrateState` bodies → `studio-route.js`. The area methods become one-line delegations.
  - API wrappers, caches and `loadAll` → `agent-data.js`. The store subscriptions stay with their owners, or move only if every callback they call is reachable through ctx.
  - The Library list plus the pending-item rule → `library-pane.js`.
  - The knowledge, MCP and connector glue → `library-groups.js`, or three files.

  Each module is `App.studio.<name>.create(ctx)`, returns a handle, and reaches studio only through `ctx` (`state`, `self`, the layout hosts and the functions it calls). The module header documents its ctx, as `providers-section.js` does.
- [ ] **Self-config refresh.** `_refreshAgentAfterSelfConfigurationChange`, the API layer's call into `doSelect`, goes through a ctx hook, `onSelfConfigChanged(updated)`, so `agent-data` does not reach the controller directly. Its behaviour is unchanged in this leg; leg 10 changes it (DD9-3).
- [ ] **Sizes.** Every new module is ≤ 800 lines, and `studio.js` shrinks by the moved sections.
- [ ] **No behaviour change.** No browser or unit test is edited other than the static pins and allowances below, and no testid, class or DOM shape changes.
  - `git diff 9369fcc -- the_one/interfaces/web/static/css/` is empty.
  - `git diff 9369fcc -- the_one/` touches only `studio.js`, the new modules and `index.html`.
- [ ] **Pins retargeted deliberately:**
  - `tests/test_index_asset_cache_busting.py`: the count rises by the number of new scripts, with a dated comment.
  - `tests/test_store_static.py`: every pin that reads `studio.js` text (`_window` reads of `fetchKnowledgeBases`, `loadLibrary`, `reloadLibrary`, `createLibraryList`, `self._refresh`, `resolvePendingLibraryItem`, `onListStale` at about `:192-219,:232`; the `invalidate('agents')` count of ≥ 5 at about `:245`; `INVALIDATION_ROWS` at about `:297,:321,:327`; the `router.sync` text at about `:350`) now reads the module that holds the text. A count spread across files sums those files. The assertion's strength is unchanged.
  - `tests/test_ui_guards.py`: `HTML_SINK_ALLOWANCE` rows and `DYNAMIC_SINK_BASELINE` snippets move to the new files, with the same totals.
  - `tests/_ui_ownership_allowance.py`: rows move, with the same totals.
  - The `index.html` order is checked by any existing order test (grep `tests/` for `areas/studio.js`).
- [ ] **Full gate:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` passes. ruff is clean.
- [ ] **Docs:** `the_one/agents.md` gains a short "Studio area modules" note (the module list, the ctx contract, the `state` rule). CLAUDE.md is untouched unless a line names a moved function.

## Verification Steps
- `wc -l the_one/interfaces/web/static/js/areas/studio.js the_one/interfaces/web/static/js/areas/studio/{studio-route,agent-data,library-pane,library-groups}*.js`
- `git diff --stat 9369fcc -- the_one/`
- `grep -nE "\bdirty\s*=|\bsnapshot\s*=|\beditorGen\b|\bselectSeq\b" the_one/interfaces/web/static/js/areas/studio.js the_one/interfaces/web/static/js/areas/studio/*.js`: every hit is a `state.` access.
- The step-1 lanes, then the full gate (background, explicit timeout).

## Implementation Guidance
1. **Step 1 is mechanical.** Rename each shared closure variable to `state.x` everywhere in `studio.js` (a careful search, with each hit read). Rewrite the `defineProperty` getters to read and write `state`. Run the step-1 gate.
2. **Move one module at a time:** route first (smallest coupling), then `agent-data`, then `library-pane`, then `library-groups`. After each move, run the unit tier and the most relevant lane (`routing` for route, `agents` for data, `library` for the pane and groups) before the next.
3. **Keep function names** inside modules as they are, so stack traces and greps still match.
4. **Grep** for every moved function name across `tests/`, `scripts/`, `Makefile` and `docs/` before the gate, and paste the hits into the flight log (the Flight 1 debrief rule).

## Edge Cases
- **Getters defined on `self`** must still exist on the area object after the move. `serializeState` reads them.
- **`escapeHtml`/`escapeAttr` are hoisted `var`s defined after their uses** (about `:4006-4007`). If a moved module uses them, it must get them from ctx or `App` (`App.escapeHtml` exists), not rely on hoisting.
- **Store subscriptions call `renderAgentList`**, which moves in leg 03. Keep that subscription in `studio.js` for now.
- **The `_dirty` test seam** (about `:4105`) reads `dirty`. It must read `state.dirty`.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio.js`;
- new `the_one/interfaces/web/static/js/areas/studio/{studio-route,agent-data,library-pane,library-groups}.js` (or the three glue files);
- `the_one/interfaces/web/static/index.html`;
- `tests/test_index_asset_cache_busting.py`, `tests/test_store_static.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`; possibly `tests/test_tool_categories.py`;
- `the_one/agents.md`.

## Citation Audit
- Checked at `9369fcc`: `studio.js:357-501` (the `init` state, the closure variables at `:377-381`, the getters); `index.html:75-90` (studio script order, `areas/studio.js` last).
- Carried from the planning survey (`dbcd458`, the file is unchanged since): the section ranges and the `test_store_static.py` pin lines.

## Design Review Addenda (2026-10-21)
**This leg is split** (review recommendation). Leg **02a** (this file) covers the `state` object (step 1, with its gate), `studio-route` and `agent-data`. Leg **02b** (`02b-library-pane-and-groups.md`) moves `library-pane` and the three glue files. Leg 03 then moves the editor modules. Everything below about `library-pane` and `library-groups` moves to 02b. These addenda take precedence over the text above.

**`studio-route` is stateless.** `App.studio.route.serialize(area)` and `App.studio.route.hydrate(area, sub, opts)`:
- the area methods become `return App.studio.route.serialize(this)` and the matching hydrate call;
- it is not a `create(ctx)` module, because the router may call it before `init`, and `hydrateState` guards `this._closeOpenItem || function(){}`, which must survive.

**`state` membership (binding).** Moves into `var state = {…}` in `init`:
- controller state: `dirty`, `snapshot`, `tabHandle`, `selectSeq`, `editorGen`. All five move now, so leg 03 only relocates functions.
- form state: `mcpSourceFormMode`, `editingMcpSource`, `pendingMcpSourceId`, `pendingMcpSourceFormMode`, `connectorFormMode`, `editingConnector`, `pendingConnectorId`, `pendingConnectorFormMode`, `kbCreateMode`;
- knowledge: `kbFocusFolderFor`, `knowledgeDetailHandle`;
- section caches: `knowledgeBases`, `mcpSources`, `connectors`, `providersCache`.

Stay private to their eventual module, **not** in `state`:
- `lastKnownItemsSignature`, `MCP_TYPES`, `mcpTypesReady`, `CONNECTOR_TYPES` and `connectorTypesReady` (the groups);
- `libraryList`, `libraryAddMenu`, `libraryRendered`, `libraryPaneGen` and the `…Settled`/`…Failed` flags (the pane);
- `loadAllDepth` and the schema and tools caches (`agent-data`);
- `bootLoad` (the shell).

Stay on `self`, unchanged, because browser tests and `deactivate` read them: `_activeSection`, `_selectedKbId`, `_kbFresh`, `_knowledgePollTimer`, `_pendingSelectName`, `_agents`, `_createMode`, `_dirty` (the test seam reads `state.dirty`), `_pendingMcpSourceId`, `_pendingMcpSourceFormMode` and every other `self._*` field.

The `defineProperty` getters remain, read and write `state`, and keep their init seeds: `pendingMcp… = self._pendingMcp… || null`, `kbCreateMode = !!self._kbCreateMode`, and the `_kbCreateMode` setter's `!!` coercion.

**Generation tokens: replaces the "never cache" criterion.** Never cache a *mutable flag or object* (`state.dirty`, caches, form modes) across an async boundary. Generation tokens are captured *by value on purpose* (`var mySelect = ++state.selectSeq`, `kbGen = state.editorGen`, `mcpGen`, `connGen`, `createGen`) and compared against the live `state.selectSeq`/`state.editorGen` when they resolve. That pattern stays.
- The providersSection ctx (`:614-618`) is rewritten to `editorGen: function () { return state.editorGen; }` and `setDirty` → `state.dirty`.
- The verification grep must ignore comments and object keys named `editorGen:`.

**`agent-data`:**
- `App.studio.agentData.create(ctx)`'s handle exposes **every** wrapper under its existing name. About 30 of them are passed by reference into `renderAgentEditor` (`:2924-2971`), and `doSelect` calls the four `refresh*Cache` functions.
- `loadAll` takes `ctx.renderAgentList`; `showLoadAllError` takes the content and section hosts; `_refreshAgentAfterSelfConfigurationChange` goes through `ctx.onSelfConfigChanged(updated)`. The connectors path uses `fetchAgents(true)`, which the handle exposes.
- The **five Library `App.store.subscribe` calls and the agent subscriptions stay in the shell** (`studio.js`), the coordinator. They call module handles.

**Pins (binding):**
- Add a `_studio_src()` helper in `tests/test_store_static.py` that concatenates `studio.js` and every studio module. Use it for text-presence pins that may span files.
- The `invalidate('agents')` pin becomes per-file, so a lost site is still caught: `agent-data.js` has 1 (`:2043`'s site) and `studio.js` 4. Leg 03 will move those 4 and update the per-file numbers.
- `App.router.sync('studio', self.serializeState(), { name: updated.name })` keeps its text: the module that holds it names its area reference `self`.
- The `gone not in src` / `include_agent_surfaces` pins cover the moved files.
- `onListStale: function () { reloadLibrary('mcp-sources'); }` is 02b's concern.

**Allowance:**
- The sinks that move with `agent-data` and the route (if any) keep the same sum.
- Compute the rows from the printed corrected dicts, and state in the flight log, per key, "same sum, moved from `studio.js` to X".
- The ownership rows move likewise.

**Docs:**
- CLAUDE.md names `studio.js::knowledgeItemsSignature` (`:90`) and `reloadLibrary` (`:257`). Update those lines to the new module names in the leg that moves them (02b).
- `the_one/agents.md` (23 `studio.js` mentions) is updated where a moved function is named.

**Moot:** the escape helpers are not used in the moved ranges.

**Checks:** after each move, `grep -c` of each moved function name in `studio.js` is 0, apart from the delegating call sites. The script-count pin rises by the number of new files (2 in this leg).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
