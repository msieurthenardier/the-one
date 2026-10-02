# Leg: library-editors (4b)

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Finish Library's detail chrome (DD2, DD8). For the knowledge-base, MCP and connector
editors this leg:

- adds the **"Library / {Group}" breadcrumb** to each editor's own header;
- **retires their Back controls** (the interim Back from leg 4a);
- adds the **unsaved indicator**;
- adds the **create-opens-item and state-preservation checks** for all three types;
- completes the library-lane migration.

## Context

- **Flight decisions:**
  - DD2: the breadcrumb insertion rules by build style. Cycle 2 issue 5 adds these:
    - string-built editors insert the breadcrumb after `innerHTML`;
    - DOM-built editors insert it during construction;
    - the knowledge-base detail re-adds it on its re-mount;
    - the knowledge-base `~new` form already has its own header from leg 4a.
  - DD8: the per-type acceptance list (opens, preserved, URL, announced) and the focus
    rule.
- **Leg 4a** hosted all three editors beside the list, with interim Back controls routed
  to the section root:
  - `back-knowledge-btn` (`knowledge-section.js:~464`, DOM-built header around
    `:457-458`);
  - `back-mcp-source-btn` (`mcp-server-editor.js:~492`, string-built header around
    `:475-476`);
  - `back-connector-btn` (`connector-editor.js:~317`, DOM-built header around
    `:287-288`).
  
  Read the leg 4a entry in the flight log for the final structure.
- **Leg 3 patterns:** the breadcrumb element (`.editor-breadcrumb`), and the stable
  `editor-unsaved` status span toggled by the dirty callback.
- **Leg 4a ground truth** (landed; read its flight-log entry):
  - **The knowledge-base `~new` form** (`App.studio.renderKnowledgeCreate`, DOM-built)
    already has the breadcrumb "Library / Knowledge bases" as plain text. This leg turns
    its group segment into a link like the others, and adds the unsaved indicator.
  - **Interim Back** on all three editors is a `go()` to the section root. The
    connector's inline `confirmLeave` gate is already gone.
  - **Tests written onto the interim Back in 4a, to move to the breadcrumb link here:**
    - `test_router_guard.py`: the four "current section closes the editor" tests;
    - `test_router_items.py`: `test_connector_editor_closed_by_back_to_the_section_root`
      (rename it again, to say breadcrumb) and `test_kb_back_clean_closes_detail` (the
      AC3 interim Back);
    - `test_nav_guard.py`: the connector Back that asks through the router guard.
  - **The allow-list holds 20 files.** Its remaining Library hits are interim Back only:
    - `test_flow_studio_knowledge_attach`
    - `test_flow_studio_knowledge_inventory`
    - `test_flow_studio_mcp_editor`
    - `test_studio_connector_editor`
    - `test_nav_guard`
    - `test_router_guard`
    - `test_router_items`

    Files whose only remaining hits are these Back usages leave the allow-list in this
    leg; files with Settings hits stay.
  - **`App.usage` row meta and the pending-item rule** are not this leg's concern. Don't
    change them.

## Outputs

**1. Breadcrumbs.**
- The breadcrumb text per editor:
  - knowledge-base detail: "Library / Knowledge bases";
  - MCP editor (edit and `~new`): "Library / MCP servers";
  - connector editor (edit and `~new`): "Library / Connectors".
- It goes in each editor's existing `.editor-header-text`, as the first child, following
  the DD2 insertion rule for that editor's build style.
- **The group segment is a link to its section root** (a DD2 refinement made at the leg
  4a design review; see the flight log).
  - For example "Library / <a href="#library/mcp">MCP servers</a>". "Library" stays plain
    text.
  - The `href` is built with `App.router.href`, and the link uses DOM APIs only.
  - With Back gone, this is how a user closes an item back to its section's empty state.
    The router guard covers a dirty editor.
  - Focus after the close follows DD8: the item's own row.
- **Agents, for uniformity.** Leg 3's "Agents" crumb (`agent-editor.js`) becomes a link
  to `#agents` in this leg. Leg 5b does the same for "Settings / Providers" and
  "Settings / Built-in tools".
- **The knowledge-base `~new` form's** "Knowledge bases" segment becomes a link too, to
  `#library/knowledge`. With a dirty form the router guard asks once.
- **Styling.** The link inherits the breadcrumb's 11px `--fg-muted`, with an underline on
  hover and a visible `:focus-visible` ring. Add it to `test_design_tokens_a11y.py` if
  that test pins the breadcrumb pair.
- **Accessibility.** Keep the breadcrumb a `div`, not a `nav` landmark: one link does not
  warrant a landmark. The link's text is the group name, so its accessible name is the
  destination.
- **Testid** `editor-breadcrumb-link`, registered.
- The knowledge-base detail re-adds it on every re-mount, for example after Save
  (`knowledge-section.js:452-456`).

**2. Back retired.**
- Delete `back-knowledge-btn`, `back-mcp-source-btn` and `back-connector-btn`, together
  with their `onBack` wiring in `studio.js`.
- The list replaces Back: clicking another row, or the section's empty state, closes the
  item.

**3. Unsaved indicator.**
- Each editor gets a stable `<span class="editor-unsaved" role="status"
  data-testid="editor-unsaved">` at the start of its `.form-actions`. It is toggled by
  that editor's dirty callback, the same callback that feeds studio's `dirty` and
  `onDirtyChange`.
- The knowledge-base detail's dirty source is its rename form.
- **The knowledge-base `~new` create form** (built in leg 4a) gets the indicator too, so
  four forms carry it.

**4. Create-opens-item and preservation checks** (DD8). Test each type end to end:

| Type | Route on save-create | What must hold |
|---|---|---|
| Knowledge base | `go` replace from `~new` (leg 4a) | The new detail view mounts, its row is selected, the name is announced, and `history.length` is unchanged. |
| MCP server | `sync` to the id | The editor is **not torn down**: the active tab and the Test result survive. The URL is `/{id}`, the name is announced, and the row appears. |
| Connector | `sync` to the id | The editor is **not torn down**: its fields stay populated. The URL is `/{id}`, the name is announced, and the row appears. |

For each type, also check that `dirty` is clear after save, so the leave guard does not
prompt when the user then clicks another row.

**5. Tests.**
- Finish the library-lane migration.
- Remove every `back-*` usage for these three editors from the tests.
- Prune the allow-list. Files leave it only when fully clean, which includes no
  Settings usages, since leg 5 owns those.

**6. Docs.** `agents.md` covers the Library editor chrome. `docs/ui-testid-registry.md`
records the three Back testids as retired, and adds `editor-unsaved` usage.

## Acceptance Criteria

- [ ] **AC1 — Breadcrumbs.**
  - Each editor shows its breadcrumb in edit and create modes, as the first child of
    `.editor-header-text`, with exactly one `h1` in the pane.
  - The knowledge-base breadcrumb survives a Save re-mount.
- [ ] **AC2 — No Back.**
  - The three Back testids exist in neither the DOM nor the code
    (`grep -r "back-knowledge-btn\|back-mcp-source-btn\|back-connector-btn" the_one/ tests/`
    is empty).
  - **Closing.** The breadcrumb's group link closes an open item to its section root's
    empty state. With a dirty editor it asks once. Focus goes to the item's row.
  - The leg 4a tests that closed items with the interim Back are moved to the breadcrumb
    link:
    - `test_router_guard.py` ×4;
    - `test_router_items.py::test_connector_editor_closed_by_library_connectors_section`;
    - the AC3 interim-Back assertions in `test_router_items.py`.
  - The Agents crumb links to `#agents`.
- [ ] **AC3 — Unsaved indicator.** For each of the three editors and the knowledge-base
  create form, it shows on an edit and clears on Save, Cancel or Continue. It is a stable
  node.
- [ ] **AC4 — Create-opens-item.** All three rows of the Outputs §4 table pass, including
  the preservation checks and the no-prompt-after-save check.
- [ ] **AC5 — Tests and guard.**
  - The library lane is green with the migration complete.
  - The allow-list is pruned.
  - The guard is green.
- [ ] **AC5b — Breadcrumb links.**
  - Every Agents and Library item header (including the knowledge-base `~new` form)
    shows its last segment as a link (`editor-breadcrumb-link`) to its root.
  - Activating the link closes the item to the root's empty state, and focus goes to the
    item's row (DD8).
  - With a dirty editor, it asks once.
  - Pinned for one item type per destination, and for the knowledge-base `~new` form.
- [ ] **AC6 — Gates.**
  - `make lint` and `make test-unit`;
  - all five lanes, one at a time, with `THE_ONE_TEST_NETNS=1`;
  - the `test_ui_*` contracts in both engines;
  - the WebKitGTK probe at an open MCP server (`--root-selector '#main-content'`).

## Implementation Guidance

1. **Breadcrumbs**, per editor and per build style.
2. **Back removal**, with the `studio.js` wiring.
3. **The indicator** in each editor.
4. **The create-opens-item and preservation tests.**
5. **Migration and allow-list.**
6. **Docs, then the gates.**

## Edge Cases

- **MCP OAuth state.** The MCP editor may hold an OAuth connect state during
  save-create. `sync` does not re-render it, so verify the connect flow survives.
- **Connector pairing-code state** after save-create. Same as above.
- **The knowledge-base detail poll.** It must keep running after the breadcrumb change.
  Keep any re-mount path unchanged apart from the breadcrumb.

## Files Affected

- `areas/studio.js`
- `areas/studio/knowledge-section.js` (detail and the `~new` form),
  `areas/studio/mcp-server-editor.js`, `areas/studio/connector-editor.js`,
  `areas/studio/agent-editor.js` (the "Agents" crumb link)
- `css/studio.css` (only if needed)
- library-lane tests; shared files (their Library parts);
  `test_flow_studio_library_list.py` (extended); `test_flow_agents_list.py` (the Agents
  crumb link); `tests/test_nav_helper.py` (the allow-list)
- `docs/ui-testid-registry.md`, `the_one/agents.md`
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## Citation Audit

Cited from the cycle-2 Architect review and the Flight 3 research, against `4828d53`. Legs
3 and 4a moved these, and they are uncommitted in the working tree. Re-grep at leg start.
The Flight Director refreshed Context from leg 4a's flight-log entry. Risk tier: **low**,
with no per-leg design review (see the flight log).

---

## Post-Completion

Status transitions, the flight-log update, checking off in the parent flight, and the
commit are Flight Control protocol, driven by the execution workflow. They are not
repeated here.
