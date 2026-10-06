# Squawk 0118: Document the editor Cancel and dirty contract (create mode versus edit mode)

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: —

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

*(written at completion)*

## Verification

The `agents.md` block exists and names the two-mode rule, the DD8 focus rule and the
staleness guard, citing the current `checkDirty` sites. A reviewer confirms the citations
resolve.

## Sign-Off

*(written at completion)*
