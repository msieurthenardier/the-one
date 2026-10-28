# Leg: tools-tab-merge

**Status**: ready
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Fold the agent editor's MCPs tab into the Tools tab as a second section. The
editor drops to five tabs: General, Rules and notes, Knowledge, Tools,
Self-configuration. Leg 8 adds Routines before Self-configuration, which
makes six. MCP deep links move to `#agents/{name}/tools/{sourceId}`, and old
`…/mcps…` hashes redirect. Saving, attaching, and per-tool choices behave
exactly as before.

## Context

- Flight DD12, first half (operator decision: "combine mcps and built-in
  tools to a single tab... Tools, with 2 different sections").
- This is the first leg of Batch B, the UI legs. It runs after Batch A's
  checkpoint commit.
- Leg 8 (`routines-tab`) adds the Routines tab and re-pins the counts from
  five to six. This leg pins five.
- **Section order** *(autonomous judgement call, reviewed at the mission
  HAT)*: "Built-in tools" first, "MCP servers" second.

## Inputs

All paths are under `the_one/interfaces/web/static/js/`.

`areas/studio/agent-editor.js`:
- `TAB_ITEMS` (`:42-51`);
- `buildPanel` (`:60-130`), with its `case 'mcps'` and `case 'tools'`;
- `rebuildPanels`, which assigns `h.mcps` and `h.tools` (`~:240-248`);
- `h.patch`, which calls `h.mcps.setSources`/`setAgent` and
  `h.tools.setAgent` (`~:265-284`).

`areas/studio/mcps-tab.js` (`App.studio.renderMcpsTab`):
- returns `{setAgent, setSources, destroy}`;
- its callback `onSelectedSourceChange` and option `pendingSourceId` drive
  the per-source deep link.

`areas/studio/tools-tab.js` (`App.studio.renderToolsTab`) returns
`{setAgent, destroy}`.

`areas/studio/studio-route.js`:
- the `mcps/` deep-link split and the tab whitelist (`:267-279`);
- URL building with `_activeTab === 'mcps'` (`:99-112`).

`areas/studio/agent-editor-controller.js`:
- `setActiveTab`, which clears the MCP selection when `tab !== 'mcps'`
  (`:380`).

`router.js`:
- `resolve()` and its legacy table (`:266-320`);
- the `settings/general` alias rewrite (`:341`), which is the pattern for a
  route-level alias.

`agent-form-data.js`: its save-flow selectors query the editor container,
not a specific panel. Verify this.

Copy that says "MCPs tab":
- `areas/studio/self-config-status.js:39`;
- `areas/studio/library-pane.js:105`, `:422`.

## Outputs

- **`agent-editor.js`:**
  - `TAB_ITEMS` without `mcps`, and the Tools label becomes "Tools".
  - `buildPanel('tools')` builds two `App.ui.section`s inside the panel:
    - "Built-in tools" (testid `agent-tools-builtin-section`) holds
      `renderToolsTab`;
    - "MCP servers" (testid `agent-tools-mcp-section`) holds
      `renderMcpsTab`.
  - It returns a composite handle, `{builtin, mcps, setAgent, destroy}`,
    and `h.tools` and `h.mcps` are assigned from it.
  - `h.patch` keeps calling `h.mcps.setSources`/`setAgent` and
    `h.tools.setAgent`, through the composite's children.
- **`studio-route.js` and `agent-editor-controller.js`:**
  - The deep link is `tools/{sourceId}`.
  - The selection is cleared when `tab !== 'tools'`.
  - The URL is built from `_activeTab === 'tools'` plus the selected source.
- **`router.js`:** a route-level alias. `agents/{name}/mcps` becomes
  `agents/{name}/tools`, and `agents/{name}/mcps/{id}` becomes
  `agents/{name}/tools/{id}`, with `redirected: true`. It is resolved in the
  same `resolve()` pass as the legacy area table, so
  `#studio/agents/x/mcps/s1` reaches `#agents/x/tools/s1` in one
  `replaceState`.
- **Copy:** "MCPs tab" becomes "Tools tab" in `self-config-status.js` and
  `library-pane.js` (both sites).
- **Docs:**
  - `docs/ui-testid-registry.md`: `tab-mcps` and `agent-tab-mcps` move to
    the Retired table, and the two section testids are added.
  - `docs/ui-control-inventory.md` rows that mention the MCPs tab.
  - `the_one/agents.md` (tab list, "expects 6 tabs") and CLAUDE.md (the tab
    mentions).
  - `scripts/ui_capture.py` surfaces `agent-mcps` and `agent-mcps-full`
    retarget the Tools tab's MCP section.
- **Tests.** Every pin of the MCPs tab is re-pointed:
  - `tests/test_nav_helper.py`: `RETIRED_SELECTORS` gains `tab-mcps` and
    `agent-tab-mcps`.
  - Other `tests/` files:
    - `tests/browser/test_studio_mcps_tab.py`, the bulk: navigation goes to
      Tools and the MCP section;
    - `test_studio_self_configuration_tab.py` (`:77`, `:104`);
    - `test_router_items.py` (`:751-780`, which also reads `mcps-tab.js`
      source);
    - `test_router_core.py` (`:92`, `:241`);
    - `tests/test_nav_helper.py` (`:33`);
    - `test_studio_editor_contracts_static.py` (the count and the
      `{id}-tab.js` map);
    - `test_flow_agent_editor_frame.py`;
    - `test_flow_agent_tabs.py`;
    - `test_flow_agents_scale.py` (five tabs, no overflow at 1024px).
  - The `_nav.py` helpers, if any, name the mcps route.

## Acceptance Criteria

- [ ] AC1. **Five tabs.** The editor shows exactly General, Rules and notes,
      Knowledge, Tools, Self-configuration, in that order. `tab-tools` is
      labelled "Tools", and `tab-mcps` and `agent-tab-mcps` no longer exist.
- [ ] AC2a. **Rebuild isolation.** Changing the operator-disabled tool set
      (`disabledTools`, which makes `tools-tab.js` rebuild) leaves the MCP
      section, its expanded tiles and both section headings intact. A browser
      test covers this.
- [ ] AC2. **Two sections.** The Tools panel holds two `App.ui.section`s in
      order:
      - "Built-in tools", with every category tile, master, row and
        override disclosure as before;
      - "MCP servers", with every source tile, attach switch, lazily loaded
        tool rows and the locked self-configuration row as before.

      The empty states for no sources and no tools are unchanged inside
      their section.
- [ ] AC3. **Save is unchanged.** On one agent, from the Tools tab:
      - toggle a built-in tool;
      - toggle an MCP source's attach switch;
      - toggle one MCP tool;
      - save.

      The stored `enabled_tools`/`disabled_tools`, `mcp_source_ids` and
      `mcp_overrides` equal what the two old tabs produced for the same
      actions. Dirty tracking, Cancel (revert) and the leave guard behave as
      before.
- [ ] AC4. **Deep links.** The tile is also scrolled into view, because the
      MCP section now sits below the built-in categories.
      - `#agents/{name}/tools/{sourceId}` opens the Tools tab with that
        source's tile expanded and scrolled into view, as the MCPs deep link
        did.
      - Selecting a source writes that URL.
      - Switching to another tab clears it.
      - `#agents/{name}/mcps` and `#agents/{name}/mcps/{id}` redirect with
        `replaceState` to the Tools forms. `#studio/agents/{name}/mcps/{id}`
        reaches the Tools form in one history entry.
- [ ] AC5a. **Every pinned string and surface the design review found is
      updated.**
      - **Library intro** (`library-pane.js:422`): the copy becomes "Attach
        them from an agent's Knowledge and Tools tabs." Update
        `tests/browser/test_flow_studio_navigation.py:71` and
        `test_flow_studio_library_list.py:166`.
      - **MCP error copy:** "agent's MCPs tab" becomes "agent's Tools tab" in
        `the_one/mcp/errors.py:69` and in
        `tests/browser/test_flow_studio_mcp_editor_signin_lifecycle.py:206`
        (`mcp-connection` lane).
      - **Behavior specs:** `tests/behavior/agent-self-revision-propagation.md:83`
        becomes "Tools tab". Review `tests/behavior/list-and-detail.md:108`
        and update it if it names the tab.
      - **Comments mentioning the MCPs tab** (sweep):
        - `the_one/self_configuration/manage.py:304`;
        - `the_one/mcp/client.py:257`, `:750`;
        - `the_one/mcp/_overrides.py:102`;
        - `the_one/interfaces/web/api.py:3377`, `:3874`;
        - `static/js/areas/studio.js:42`, `:71`;
        - `agent-editor-controller.js:276`, `:318`, `:378`;
        - `agent-editor.js:24`;
        - `agent-data.js:46`;
        - `agents-list.js:333`, `:438`;
        - `self-configuration-tab.js:9-10`;
        - `agent-form-data.js:170`, `:180`;
        - `mcp-error.js:2`;
        - `studio.css:187-188`;
        - `tests/browser/test_ui_tile_contract.py:8`.
      - **`the_one/agents.md`:** the "MCPs tab (M31 F2 L07b)" block, the tab
        whitelist and route scheme (`~:2551`), the routing note (`~:2591`)
        and `:2329`.
      - **`docs/ui-control-inventory.md`** rows `:62`, `:71`, `:72`, `:100`,
        `:101`.
      - **`CLAUDE.md`:** `:87` (the tab count wording) and any lane text.
      - **`scripts/ui_capture.py`:** `agent-mcps` (`:873`) and
        `agent-mcps-full` (`:1445`) keep their surface names, because
        `tests/test_ui_capture_safety.py:215` filters on them. Their routes
        and ready selectors move to `…/tools` and the MCP section.
      - **Router tests:**
        - `tests/browser/test_router_core.py:241`: the expected value is now
          `agents/foo/tools/src1`, redirected.
        - `:92` (an `href` builder case) is re-pointed to `tools`.
        - `tests/test_nav_helper.py:33` is re-pointed for hygiene. `_nav.py`
          itself needs no change.
      - **Panel ids:** `PANEL_IDS` loses `agent-tab-panel-mcps`. Grep for
        `AGENT_PANEL_IDS` consumers (`test_flow_agent_editor_frame.py:65-68`).
- [ ] AC5. **Copy and docs.**
      - No UI string says "MCPs tab".
      - The testid registry, the control inventory, `agents.md`, CLAUDE.md
        and `scripts/ui_capture.py` are updated.
      - `tests/test_ui_guards.py`'s registry diff passes.
- [ ] AC6. **No overflow.** `test_flow_agents_scale.py` asserts five tabs and
      no tablist overflow at 1024px. Record the measured last-tab right edge
      in `agents.md`, replacing the old 1005/994px note.
- [ ] AC7. **Gates.** These lanes are green with `THE_ONE_TEST_NETNS=1` and
      `THE_ONE_REQUIRE_WEBKIT=1` where a contracts lane is run:
      - `agents`;
      - `agent-tabs`;
      - `routing`;
      - `library`;
      - `mcp-connection`;
      - `shared`;
      - `contracts-controls`, because of the comment-only touch.

      Also green:
      - `make test-unit`;
      - the static guards (`tests/test_ui_guards.py`,
        `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`);
      - `make lint`.

      Before signalling, grep `tests/`, `scripts/`, `docs/` and
      `tests/behavior/` for `mcps`, `tab-mcps` and `MCPs tab`, and resolve
      every hit or record why it stays (for example, the router's own legacy
      contract test).

## Verification Steps

- AC1, AC2, AC6: `tests/browser/test_flow_agent_tabs.py`,
  `test_flow_agent_editor_frame.py` and `test_flow_agents_scale.py`.
- AC3: `tests/browser/test_studio_mcps_tab.py` (re-pointed) plus one new save
  round trip covering both sections in `test_flow_agent_tabs.py`, or in the
  MCP tab test.
- AC4: the router tests (`test_router_items.py`, `test_router_core.py`) and
  `tests/test_nav_helper.py`.
- AC5: the grep and `tests/test_ui_guards.py`.
- AC7: lane commands:

  ```bash
  THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>
  ```

## Implementation Guidance

1. **Both modules wipe their host** (design review), so neither can be given
   the tabpanel or `section.body`:
   - `tools-tab.js` `build()` calls `clearNode(panel)` (`:251`), and
     `setAgent` re-runs `build()` when `disabledTools` changes;
   - `mcps-tab.js` clears `panel` at `:57` and in `destroy`, and `reconcile`
     appends straight to it.

   `App.ui.section().body` is the section root, which includes its title.
   So in `buildPanel('tools')`:
   - create each section with `App.ui.section({title, titleTag: 'h2', testid})`;
   - append a plain host `div` to each section (`agent-tools-builtin-host`,
     `agent-tools-mcp-host`);
   - pass each tab its own host.

   Neither module needs to change for this.
2. Build the composite in `buildPanel('tools')`. Pass every callback the
   two old cases received, merged into one bag. Patch order is unchanged:
   `mcps.setSources`, then `mcps.setAgent`, then `tools.setAgent`. The
   composite's `destroy` destroys both children, and is called on editor
   teardown.
3. Update the route split, the URL builder and `setActiveTab`.
4. Add the router alias in `resolve()`'s **`agents` branch**, before
   `route = segs.join('/')`. When `segs[1] !== '~new'` and
   `segs[2] === 'mcps'`, set `segs[2] = 'tools'` and `redirected = true`.
   - A legacy `#studio/agents/x/mcps/s1` becomes `agents/x/mcps/s1` through
     `areaSubToRoute` and then passes through this branch, so the result is
     one `replaceState`.
   - Update the `router.js:155` comment.
   - In `studio-route.js`, replace the `mcps/` split with a `tools/` split
     (`tab.indexOf('tools/') === 0` gives the source id and tab `tools`)
     before the whitelist. Otherwise the whitelist falls back to `general`,
     the F8 L3 Patch A trap.
5. Re-point the tests, then the docs, registry, inventory and capture
   script.
6. Run the lanes and the grep.

## Edge Cases

- **A new (`~new`) agent.** The Tools panel renders both sections, and the
  MCP section shows its create-mode empty state. There is no `tools/{id}`
  deep link for `~new`.
- **The self-configuration surface row:** it stays locked and checked in the
  MCP section, and its explanatory copy now names the Tools tab.
- **A bookmarked `#agents/x/mcps` with a dirty editor open on another
  agent:** the redirect happens before the guard, as other aliases do.

## Files Affected

All `static/js` paths are under `the_one/interfaces/web/static/js/`.

- `static/js/areas/studio/agent-editor.js`, `studio-route.js`,
  `agent-editor-controller.js`, `self-config-status.js`, `library-pane.js`
- `static/js/router.js`
- `tests/browser/test_studio_mcps_tab.py`,
  `test_studio_self_configuration_tab.py`, `test_router_items.py`,
  `test_router_core.py`, `test_flow_agent_editor_frame.py`,
  `test_flow_agent_tabs.py`, `test_flow_agents_scale.py`
- `tests/test_nav_helper.py`, `tests/test_studio_editor_contracts_static.py`
- `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`,
  `scripts/ui_capture.py`, `the_one/agents.md`, `CLAUDE.md`

## Citation Audit

Checked on the working tree:
- `agent-editor.js:42-51` `TAB_ITEMS`, `buildPanel` cases, `rebuildPanels`
  assignments and `h.patch`;
- `studio-route.js:99-112`, `:267-279`;
- `agent-editor-controller.js:380`;
- `router.js:266-320`, `:341`;
- copy sites at `self-config-status.js:39` and `library-pane.js:105`, `:422`.

The test pin lines come from the flight design review (cycle 1); re-grep at
the start.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off the
leg in the parent flight, and the commit) are Flight Control protocol, driven
by the execution workflow, and are not repeated here.
