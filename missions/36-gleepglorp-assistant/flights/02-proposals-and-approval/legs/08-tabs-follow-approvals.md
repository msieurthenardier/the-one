# Leg: tabs-follow-approvals

**Status**: completed
**Flight**: [Proposals and approval](../flight.md)

## Objective
Extend Leg 7's follow-through to the agent editor's other tabs: Tools, MCP
servers, Knowledge, Rules and Routines.

When an approved proposal changes these:
- clean tiles take the new values;
- dirty ones keep the operator's choice;
- changed tiles show option A's note;
- the Rules and Routines lists reload without losing an open form's text.

## Context
- Flight DD10. Split from Leg 7 at its design review (the flight's acceptable
  variation).
- It uses Leg 7's mechanism unchanged:
  - `App.approvals` (the record, de-duplication and the `CONFIG_CHANGED`
    bus event);
  - the follow module's central clean or dirty decision over
    `JSON.parse(getFormSnapshot())` against `JSON.parse(state.snapshot)`;
  - rebasing from the DOM;
  - the dirty trick (write, read into base, restore);
  - notes drawn from the record at every mount.
- **Tab facts** (design survey):
  - **Tools** (`tools-tab.js`): rows with `setChecked`; `setAgent` 480-507;
    `enabledSetFor` 117-131. All on means `enabled_tools: null`.
    `disabled_tools` carries the ungated-prefix and exempt-off union, so a
    rebase reads from the DOM.
  - **MCP** (`mcps-tab.js`): master toggles `[data-mcp-source-toggle]`,
    `patchEntry` 279-290, and `setAgent` 604-628, which leaves
    credential-dirty tiles alone.
  - **Knowledge** (`knowledge-tab.js`): `patchRows` 68-77, gated on
    `data-kb-list-loaded`.
  - **Rules** (`rules-notes-tab.js`): rules `load` 290-300 is private;
    `renderList` clears `listWrap` and rebuilds, seeding the inline editor
    from `rule.text` (~174-176); `editingId` is cleared only when the rule
    vanished.
  - **Routines** (`routines-tab.js`): the handle has `setAgent`, `activate`,
    `deactivate` and `destroy`; `load` 447-462; `apply` reconciles by id and
    keeps an open form.

## Inputs
- Leg 7's `approvals.js` and `agent-editor-follow.js`, with its flight-log
  entry for the actual names.
- `static/js/areas/studio/tools-tab.js`, `mcps-tab.js`, `knowledge-tab.js`,
  `rules-notes-tab.js` (and its shared module), and `routines-tab.js`.

## Outputs
- Plain setters on the Tools, MCP and Knowledge handles, where missing.
- The follow module's central apply extended to the groups `tools`
  (`enabled_tools` and `disabled_tools` together), `mcp_source_ids` and
  `kb_ids`.
- A Rules `reload()` that keeps an open inline edit's typed text and shows a
  row-local note.
- A Routines `reload()`.
- Notes on tiles and tab lists. Tests, docs.

## Acceptance Criteria
1. **Groups.** The central apply (Leg 7 AC4) gains three groups:
   - `tools` (`enabled_tools` and `disabled_tools` as one);
   - `mcp_source_ids`;
   - `kb_ids`.

   They use the same clean or dirty rule, the DOM rebase and the dirty trick.
   - **Tools:** each row's checked state follows `enabledSetFor(updated)`
     through `setChecked`, with no change event.
   - **MCP:** master toggles follow `updated.mcp_source_ids`. A tile with
     dirty credentials is left untouched, as `setAgent` does; its master is
     still set, and the tile shows the note.
   - **Knowledge:** toggles follow `updated.kb_ids`. When the list has not
     loaded (`data-kb-list-loaded` false), nothing is set, and the next load
     takes the stored value.
2. **Notes on tiles.** A tile whose state took an approved value shows the
   option A note inside the tile, under its header row. Testid
   `agent-approved-change-note`, with `data-field` set to the group and
   `data-item` set to the tool name, MCP source id or KB id. They are drawn
   at every mount from the record, so a tab rebuild keeps them.
3. **Rules** (`kind: rule`).
   - The Rules section gains a public `reload()`, exposed through the panel's
     handle (today `buildPanel` returns none; add one).
   - Before `renderList`, it captures the open inline editor's input value
     (`rules-row-edit-input`). After the rebuild, if that value differs from
     the rule's text before the reload, it sets the new editor's input to the
     captured value and shows a row-local caption: "This rule changed. Save
     will replace it with your text." The General tab's panel note is not
     used here.
   - The Add textarea is untouched.
   - The list's top shows the option A note for the change.
4. **Routines** (`kind: routine`). The tab gains `reload()`. It calls `load()`
   when the tab is active, or marks it stale for the next `activate`. An open
   New or Edit form is kept by `apply()`. The list's top shows the option A
   note.
5. **Tests:** extend `tests/browser/test_flow_agent_editor_follows_approval.py`,
   or add a second file in the same lane list, with these cases:
   - clean tool, MCP and KB toggles follow, with notes;
   - a dirty tool row is kept;
   - an MCP tile with dirty credentials is kept;
   - the KB list has not loaded yet, and its first load shows the stored
     value;
   - a rule approval with an open inline edit keeps the typed text and shows
     the row caption, while a clean rule list just updates;
   - a routine approval reloads with an open form kept;
   - the notes survive a tab switch.

   **Falsify:** drop the inline-edit capture (the text is lost).

   **Also run:** the static guards; lanes `agents`, `agent-tabs` and
   `agent-routines`, one at a time.
6. **Docs:** extend Leg 7's `the_one/agents.md` section and register any new
   testids.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_area_module_size.py -x --timeout 60`
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents`,
  then `--lane agent-tabs` and `--lane agent-routines`, one at a time.

## Implementation Guidance
1. Read Leg 7's flight-log entry and the follow module.
2. Add the setters, and the three groups to the central apply.
3. Draw the tile notes at mount.
4. Add the Rules `reload()` with the inline-edit capture, and its handle.
5. Add the Routines `reload()`.
6. Write the tests and run the lanes. Then write the docs.

## Edge Cases
- **An MCP server attached by the proposal that is not in the cached sources
  list** (created in another window): `setSources` reconciles first. A
  refresh of the MCP sources cache is part of the fetch step.
- **A tool removed from the registry** since the proposal: its row is absent,
  so nothing is set.
- **A rule deleted by the operator while the approval of a change to it
  lands:** the proposal is `gone` (Leg 4), so no event fires.

## Files Affected
- `static/js/areas/studio/tools-tab.js`, `mcps-tab.js`, `knowledge-tab.js`,
  `rules-notes-tab.js` (and its shared module), `routines-tab.js`,
  `agent-editor.js` (handles), `agent-editor-follow.js`.
- `css/studio.css`, `docs/ui-testid-registry.md`.
- The test file(s).
- `the_one/agents.md`.

## Citation Audit
From Leg 7's design survey and review:
- `tools-tab.js` `setAgent` 480-507, `enabledSetFor` 117-131;
- `mcps-tab.js` `patchEntry` 279-290, `setAgent` 604-628;
- `knowledge-tab.js` `patchRows` 68-77;
- `rules-notes-tab.js` `load` 290-300, the inline editor seeded from
  `rule.text` ~174-176, `buildPanel` with no handle (`agent-editor.js:70-83`);
- `routines-tab.js` handle 503-530, `load` 447-462, `apply` 390-433.

Verified at survey. Re-check after Leg 7 lands.
