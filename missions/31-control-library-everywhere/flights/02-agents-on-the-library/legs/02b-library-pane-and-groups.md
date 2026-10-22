# Leg: library-pane-and-groups

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
A behaviour-free restructure, continuing from leg 02a. Move the Library list and the knowledge, MCP and connector section glue out of `studio.js`:
- `js/areas/studio/library-pane.js`;
- `js/areas/studio/knowledge-glue.js`;
- `js/areas/studio/mcp-glue.js`;
- `js/areas/studio/connector-glue.js`.

Each is an `App.studio.<name>.create(ctx)` module on the `state` object leg 02a introduced. The DOM, behaviour and every test outcome stay identical.

## Context
- **Leg 02a** introduced `state` and moved `studio-route` and `agent-data`. Read 02a's artifact (binding addenda: `state` membership, generation tokens, pins) and its flight-log entry.
- **Lines in `studio.js` before 02a** (re-locate by symbol):

  | Lines | Section |
  |---|---|
  | 534-1040 | the Library list |
  | 1052-1354 | knowledge glue |
  | 1356-1547 | MCP glue |
  | 1549-1684 | connector glue |
  | 1686-1764 | the pending-item rule (`PENDING_KINDS`) |

- **The coupling between the pane and the groups** (review):
  - `PENDING_KINDS` calls `tryConsumePendingMcpSource`/`tryConsumePendingConnector`, the providers handle and `setActiveSection`;
  - the pane's `librarySelection`/`renderLibraryEmpty` read group state and call `goLibraryCreate`;
  - the groups call `reloadLibrary`, `syncLibrarySelection`, `focusLibrary*`, `libraryRowIndex`, `renderLibraryEmpty` and `discardOpen_`.

## Acceptance Criteria
- [ ] **Creation order.** `library-pane.js` is created first. Its handle exposes `syncCache`, `reload` (today's `reloadLibrary`), `render`, `sync` (`syncLibrarySelection`), `rowIndex`, `focusNear`, `focusGroupStart`, `renderEmpty`, `load` (`loadLibrary`), `create`/`destroy` (the list pane's lifetime), `reset()` and `isOpen()`.
- [ ] **The glue modules** are created next, with the pane handle in their ctx. They take the providers handle, `state`, `self`, `setActiveSection`, `discardOpen_`, `writeUrl_`, `sectionContent()` (a function), `fetchAgents`, `buildRootHeading`, and the `agent-data` handle. There are no lazy back-references.
- [ ] **`resolvePendingLibraryItem`/`PENDING_KINDS` live in the groups layer** (in `mcp-glue.js`, or a small `pending-items` section of the connector or MCP glue). Each glue module exposes `tryConsumePending…`, `reset()` and `isOpen()`. The shell's `closeOpenItem`/`discardOpen_` call `reset()` instead of poking module internals.
- [ ] **`buildRootHeading`** (shared with the Agents root, `studio.js` about `:1965`) stays in the shell and is passed by ctx.
- [ ] **The store subscriptions** for the Library collections stay in the shell and call the module handles.
- [ ] **Sizes.** Every new module is ≤ 800 lines. `studio.js` shrinks to roughly the editor-plus-shell remainder (about 1500-1700 lines; leg 03 brings it to ≤ 800).
- [ ] **No behaviour change**, same rule as 02a: no test edits except pins and allowances; `git diff` limited to `studio.js`, the new modules, `index.html` and the pins.
- [ ] **Pins:**
  - `onListStale: function () { reloadLibrary('mcp-sources'); }` (`tests/test_store_static.py` about `:232`) stays literal: the MCP glue keeps a local `var reloadLibrary = ctx.pane.reload;` alias.
  - The `_window` reads of `loadLibrary`, `reloadLibrary`, `createLibraryList`, `resolvePendingLibraryItem` and `fetchKnowledgeBases` use `_studio_src()` (from 02a), or point at the module that holds the text, without weakening.
  - The script count rises by 4, with a dated comment.
  - Sink and ownership rows move with the same sums, stated per key in the flight log. About 5 `studio.js` sinks move (at about `:1091, 1208, 1282, 1363, 1554`), plus `ui-list-pane-row`, `badge` and the `editor-title` comment row.
- [ ] **Docs:** CLAUDE.md lines naming `studio.js::knowledgeItemsSignature` (about `:90`) and `reloadLibrary` (about `:257`) name the new modules. `the_one/agents.md` mentions of moved functions are updated, and the "Studio area modules" note (02a) is extended.
- [ ] **Gates:** `make test-unit`; the `library`, `mcp`, `agents`, `routing` and `shared` lanes under netns; then the full `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`. ruff clean.

## Verification Steps
- `wc -l` on `studio.js` and the four new modules.
- `git diff --stat` since the leg-02a tree, limited to the files above.
- `grep -c` of each moved function name in `studio.js` is 0 except delegating calls.
- The lanes, then the full gate (background, explicit timeout).

## Implementation Guidance
1. Move the pane first, and run the `library` lane.
2. Move the knowledge glue, and run the `library` lane (knowledge inventory).
3. Move the MCP glue with the pending rule, and run the `mcp` and `library` lanes.
4. Move the connector glue, and run the `library` lane.
5. Pins, docs, then the full gate.

## Edge Cases
- **The knowledge 5 s poll timer** stays on `self._knowledgePollTimer`, because `deactivate` reads it.
- **`kbFocusFolderFor` and `knowledgeDetailHandle` are in `state`.** The shell's `closeOpenItem`/`setActiveSection` write them.
- **The providersSection ctx** (created at about `:614-627`) is created before the glue modules and passed to them.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio.js`, new `js/areas/studio/{library-pane,knowledge-glue,mcp-glue,connector-glue}.js`, `index.html`.
- `tests/test_store_static.py`, `tests/test_index_asset_cache_busting.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`.
- `CLAUDE.md`, `the_one/agents.md`.

## Citation Audit
Carried from the leg 02a design review (2026-10-21, at `9369fcc`): the coupling list, `onListStale` at `test_store_static.py:232`, the sink lines, `buildRootHeading` at `:1965`, and CLAUDE.md `:90`/`:257`. Re-locate by symbol after 02a.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
