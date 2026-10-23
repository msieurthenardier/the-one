# Leg: library-pane-and-labels

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Close out the Library glue and pane:
- the `mcp-glue.js` host clear becomes `replaceChildren()` (sink 1 → 0);
- squawk 0191: `isLibrarySection` and `studio-route.js`'s Library section list derive from one `LIBRARY_GROUPS` table;
- squawk 0192: the router announces "Knowledge bases" for the knowledge group (operator, 2026-10-22).

## Context
- **Flight DD9** (0191: hoist and expose `LIBRARY_GROUPS`, read lazily; 0192's scope is the Library knowledge group, not the agent editor's Knowledge tab), **DD10** (the `routing` and `mcp` lanes hold the pins), **DD11**.
- **Code at `332496d`:**
  - `js/areas/studio/library-pane.js`:
    - `LIBRARY_GROUPS` (about `:60`) is declared inside `libraryPane`'s `create(ctx)` closure (about `:38`). Each group has `{id, section, route, collection, label, emptyText, failText, icon, testid, prefix}`. The sections are `providers`, `knowledge`, `mcp-sources` and `connectors`.
    - `isLibrarySection(section)` (about `:114-117`) hand-lists `library` plus the four sections.
  - `js/areas/studio/studio-route.js` about `:186`: `hydrateState`'s root list `sub === 'library' || … 'providers' || 'knowledge' || 'connectors' || 'mcp-sources'`. This is the drifted site squawk 0191 names (it was `studio.js` about `:187`).
  - `studio-route.js` loads before `library-pane.js` (`index.html` about `:104` against `:106`), so `studio-route.js` must read the table at call time.
  - `js/router.js` about `:440`: `LIBRARY_LABELS = {providers: 'Model providers', knowledge: 'Knowledge', mcp: 'MCP servers', connectors: 'Connectors'}`, the spoken labels.
  - `js/areas/studio/mcp-glue.js` about `:45`: `sectionContentEl.innerHTML = ''` (the sink). It is the MCP editor's glue, but the mount path is unchanged here; only the clear changes.
- **Pins for 0192:**
  - `tests/browser/test_router_announce.py:201` (`"Library — Knowledge"`) — `routing` lane;
  - `tests/browser/test_flow_studio_library_list.py:507` and `:1276` (`"Library — Knowledge — {name}"`) — `mcp` lane.

  Grep for any other "Library — Knowledge" or `'Knowledge'` label pin, and any `tests/behavior/*.md` step that reads the announcer.
- **The Library list group heading** is already "Knowledge bases" (`LIBRARY_GROUPS`' label). Check the Add menu item, the start-page card and the jump-to palette's "where" text and note them in the flight log; change nothing that already says "Knowledge bases".

## Inputs
- Legs 01 (lanes), 05a/05b (`knowledge-glue.js`) and 07a/07b (`connector-glue.js`) landed. This leg touches neither glue file except as named.

## Outputs
- **The table:** `LIBRARY_GROUPS` is hoisted to `library-pane.js`'s IIFE scope and exposed as `App.studio.libraryGroups` (frozen or copied on read, so no caller mutates it). `libraryPane.create` uses it unchanged.
- **The derived sections:**
  - `isLibrarySection(section)` returns `section === 'library'` or any group's `section`;
  - `studio-route.js`'s list is `sub === 'library'` or any group's `section`, read from `App.studio.libraryGroups` at call time;
  - a fallback, if the table is missing at call time, throws a clear error (it never runs before `library-pane.js` loads).
- **A unit-tier static check** (`tests/test_library_groups_static.py`, or an existing studio static file) fails if `isLibrarySection` or `studio-route.js` hand-lists a Library section literal, or if a `LIBRARY_GROUPS` entry lacks a `section`. It reads the source; it is not a browser test.
- **0192:** `router.js` `LIBRARY_LABELS.knowledge` becomes `'Knowledge bases'`. The three pins and any others found change to "Library — Knowledge bases…", together with any behavior-spec step.
- **The `mcp-glue.js` clear** becomes `replaceChildren()`. Its `HTML_SINK_ALLOWANCE` row is removed.
- **Squawks 0191 and 0192:** their Corrective Action and Verification are written, and the status set to `in-progress` (the Flight Director completes them at the flight commit).

## Acceptance Criteria
- [ ] `App.studio.libraryGroups` exists. `isLibrarySection` and `studio-route.js` derive from it, and `git grep -n "'mcp-sources'" -- the_one/interfaces/web/static/js/areas/studio/studio-route.js the_one/interfaces/web/static/js/areas/studio/library-pane.js` shows no hand-listed section comparison outside the table.
- [ ] The static check passes, and fails when a literal section list is re-added: try once and revert.
- [ ] The router announces "Library — Knowledge bases" (and "— {name}" for an item). The updated pins pass in `routing` and `mcp`.
- [ ] `HTML_SINK_ALLOWANCE` has no `mcp-glue.js` row.
- [ ] The `library`, `mcp`, `routing` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1`, plus `make test-unit` and the static guards.
- [ ] Ledger row: "router announcement | 'Knowledge' → 'Knowledge bases' | DD7-3, 0192". The agent editor's Knowledge tab is recorded as a HAT question.

## Verification Steps
- The listed lanes; `make test-unit`; the grep; the static check's falsification.

## Implementation Guidance
1. Log a start line. Hoist and expose the table, then switch `isLibrarySection`, then `studio-route.js`.
2. Write the static check.
3. Make the 0192 label change and update the pins.
4. The `mcp-glue.js` clear.
5. Squawk artifacts, the ledger, the flight log.

## Edge Cases
- **A route `sub` like `library/knowledge/…`** is matched by other branches; only the bare root list is derived here. Keep the order of the `if` branches.
- **`section` against `route`:** the table's `section` for MCP is `mcp-sources` and its route is `mcp`. Derive from `section`, which is what both sites compare today.

## Files Affected
- `js/areas/studio/library-pane.js`, `js/areas/studio/studio-route.js`, `js/areas/studio/mcp-glue.js`, `js/router.js`
- `tests/browser/test_router_announce.py`, `tests/browser/test_flow_studio_library_list.py` (and any other pin found)
- A new or extended unit-tier static test; `tests/test_ui_guards.py` (the sink allowance)
- `squawks/0191-…md`, `squawks/0192-…md`; `tests/behavior/*.md` if a step reads the announcer
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD read and grep):
- `library-pane.js:38,60,114-117`;
- `studio-route.js:186`;
- `router.js:440`;
- `mcp-glue.js:45`;
- `test_router_announce.py:201`;
- `test_flow_studio_library_list.py:507,1276`;
- `agent-editor.js:43` (the tab label, unchanged).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
