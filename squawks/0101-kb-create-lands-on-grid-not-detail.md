# Squawk 0101: Creating a knowledge base returns to the grid instead of opening the new knowledge base

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: —

## Report

After creating a knowledge base in Studio → Knowledge, the operator lands back on
the summary tile grid, not the new knowledge base's detail page. A new knowledge
base is empty, and its next step is always registering a folder, which only the
detail page offers. So every create costs an extra click to find and open the tile
that was just made.

Repro: Studio → Knowledge → create a knowledge base with a name → submit. The grid
refreshes with the new tile. Expected: the new knowledge base's detail view opens.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js` — the create
  handler calls `onCreateSuccess(kb)` with the created row, which carries `kb.id`.
- `the_one/interfaces/web/static/js/areas/studio.js` — the `onCreateSuccess` passed to
  `renderKnowledgeGrid` ignores that argument and only calls `fetchKnowledgeBases_()`
  ("AC-2: appears in the list without a page reload").
- Same file, `selectKnowledgeBase(id)` — the grid's existing tile-click path
  (`_selectedKbId` + `App.router.replaceSub` + re-render) is the navigation that is
  wanted here.

## Corrective Action

*(written at completion)*

## Verification

## Sign-Off

*(written at completion)*
