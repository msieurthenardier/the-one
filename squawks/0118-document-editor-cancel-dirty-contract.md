# Squawk 0118: Document the editor Cancel and dirty contract (create mode versus edit mode)

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: 2026-10-05 (M25 Flight 4 leg 6, `agent-drawer-and-chat-action`)

## Report

Every item editor (agent, provider, MCP server, connector, and the knowledge-base `~new`
form) shares an unwritten contract for its Save and Cancel controls:
- **Create mode** (`~new`). Cancel is **always enabled**, even on a pristine form, because
  Cancel abandons the create (flight DD8). Save or Create is enabled once the required
  fields are valid.
- **Edit mode.** Save and Cancel are enabled only while the editor is dirty. The
  `editor-unsaved` caption shows exactly while it is dirty.
- **After Cancel, close or delete**, focus follows DD8's single rule: the item's own row,
  else the nearest surviving row, else the primary action.

M25 Flight 3 shipped all four editors gating Cancel on `dirty` in create mode, which
disabled Cancel on a pristine create form. Only the `list-and-detail` behavior run caught
it, and it was fixed in `56f7d75`. Nothing in `the_one/agents.md` or `CLAUDE.md` states the
contract, so the next create flow (M25 Flight 4 adds the New chat agent picker and drawer)
has nothing to follow.

What needs doing: add a short "Editor Save/Cancel contract" block to `the_one/agents.md`, in
or beside "Agents list and detail" / "Settings item pages". It should give:
- the two-mode rule above;
- the DD8 focus rule;
- the staleness guard for save-create (`stillOnCreate()` / `createGen`): a create whose
  POST resolves after the user navigated away must not open the new item.

It should cite the four editors' `checkDirty` sites. This is documentation only, with no
code change.

## Evidence

- The fix and its tests: `56f7d75`, and the "Behavior-gate fix: create-form Cancel" entry
  in `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`.
- The save-create staleness guard was added in the flight-end review fixes (`studio.js`
  agent create, after the knowledge-base path's `stillOnCreate()`).
- `grep -n -i cancel the_one/agents.md` finds no editor contract.
- M25 F3 debrief, "Documentation" and recommendation 4.

## Corrective Action

Documented in M25 Flight 4 leg 6 (`agent-drawer-and-chat-action`, flight DD8), beside the
agent editor's new Chat header action, which extends the same header chrome. Documentation
only: no editor's behaviour changed.

- **`the_one/agents.md` gains "Editor Save/Cancel contract (squawk 0118)"**, directly after
  "Agents list and detail" and before "Library list and detail". It gives:
  - **create mode:** Cancel always enabled, from first render (it abandons the create,
    Flight 3 DD8); Save ("Create") waits for a change (the agent, provider and MCP server
    forms on the first edit, the connector form on the first field change; the
    knowledge-base `~new` form's Create is enabled from first render), and required
    fields are checked on click ("Name is required.", no request), not by keeping it
    disabled;
  - **edit mode:** Save and Cancel enabled only while dirty; the `editor-unsaved` caption
    shows exactly while dirty; the agent editor's extra squawk 0090 Save block;
  - **focus:** DD8's one rule (the item's row, else the neighbouring row, else the list's
    primary action; a create form's own fallback);
  - **the save-create staleness guard:** the knowledge-base form's `stillOnCreate()` and
    the agent create's `createGen` / `onThisForm()`, both in `areas/studio.js`;
  - **the single studio `dirty` flag** (Flight 4 DD8: it stays one flag; Chat, the drawer
    link and the palette leave through `go()`);
  - **the grep-derived sites:** `checkDirty` in `areas/studio.js`, `areas/studio/
    mcp-server-editor.js`, `areas/admin/provider-editor.js`, `areas/admin/tools-editor.js`
    and `areas/studio/knowledge-section.js`, with `areas/studio/agent-editor.js` holding the
    agent header markup the studio `checkDirty` drives; the connector editor's equivalent is
    `markDirty` / `reportDirty` in `areas/studio/connector-editor.js`.
- **One correction to the report's wording.** The report says Save or Create "is enabled once
  the required fields are valid". No editor does that: Save enables on the first change and
  the required-field check runs on click. The block states what the code does.
- The "Agent drawer" section in `agents.md` (the agent editor's Chat) and `CLAUDE.md`'s
  Chats paragraph point at the same contract.

## Verification

- `grep -n "### Editor Save/Cancel contract" the_one/agents.md` finds the block, between
  "Agents list and detail" and "Library list and detail".
- **The citations resolve** (re-grepped at completion):
  `grep -rn "function checkDirty" the_one/interfaces/web/static/js` lists `areas/studio.js`,
  `areas/studio/mcp-server-editor.js`, `areas/admin/provider-editor.js`,
  `areas/admin/tools-editor.js` and `areas/studio/knowledge-section.js`;
  `grep -n "stillOnCreate\|createGen" the_one/interfaces/web/static/js/areas/studio.js`
  finds both guards; `grep -n "function markDirty\|function reportDirty"
  the_one/interfaces/web/static/js/areas/studio/connector-editor.js` finds the connector's.
- **The rules match the code:** create-mode Cancel is enabled from first render in the agent
  (`agent-editor.js` header markup), provider (`isEdit && !dirty`), MCP server
  (`isEdit && !dirty`), connector (`cancelBtn.disabled = !isCreate`) and knowledge-base
  `~new` forms; edit-mode Save and Cancel follow `!dirty` in every editor.
- The existing tests of the contract stay green: the agents, library and settings browser
  lanes (numbers in the flight log's leg 6 entry), including the create-form Cancel tests
  that came with `56f7d75`.
- **Leg 8 re-check** (the flight's closing gates): the greps above re-run and resolve (the
  block is at `the_one/agents.md` "Editor Save/Cancel contract (squawk 0118)", between
  "Agents list and detail" and "Library list and detail"); `agents` 134 passed and 2
  skipped, `library` 145 passed and 1 skipped, `settings` 178 passed.

## Sign-Off

*(pending: the M25 Flight 4 flight-end review signs it off)*
