# Squawk 0101: Creating a knowledge base returns to the grid instead of opening the new knowledge base

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: 2026-10-02

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

Fixed in Mission 25 Flight 3 leg 4a (`library-list`), as part of the Library list
rebuild (flight DD8), rather than by patching the grid it retires:

- The tile grid and its inline create form are gone. Creating a knowledge base is a
  route, `#library/knowledge/~new` (Library list -> Add -> "Knowledge base"), whose
  create form (`App.studio.renderKnowledgeCreate` in `knowledge-section.js`) sits in the
  detail pane beside the Library list.
- On a successful create (`studio.js` `renderKnowledgeCreateView`): the module
  invalidates `knowledge-bases`; studio clears the shared `dirty` flag only while still
  on the form; awaits the store reload (so the new row exists and the router can name
  the opaque-id item); re-checks that the user is still on the form with no decision
  pending; then `go(href(kb), {replace: true, bypassGuard: true})` opens the new
  knowledge base's detail view, replacing the `~new` entry. The route announcer speaks
  the knowledge base's name, its list row is selected, and focus moves to the
  folder-path field (registering a folder is always the next step).

Why this rather than the one-line `selectKnowledgeBase(kb.id)` the report suggested:
the grid is retired in the same leg, and DD8 makes every creatable type a `~new` route
whose save-create replaces the create entry, so Back never lands on a stale form.

## Verification

- `tests/browser/test_flow_studio_library_list.py::test_kb_create_form_opens_the_new_knowledge_base`
  -- the repro: Add -> "Knowledge base", name, Create opens `#library/knowledge/{id}`
  (`history.length` unchanged), exactly one POST (Create stays disabled while it is in
  flight), the new row selected, the announcer says "Library — Knowledge — {name}",
  focus in `kb-folder-path-input`.
- `tests/browser/test_flow_studio_knowledge_inventory.py` -- `_create_knowledge_base`
  now waits for the new knowledge base's detail view, and every create-based test
  continues from it.
- `tests/browser/test_flow_studio_library_list.py::test_kb_save_create_opens_the_item_and_a_row_click_does_not_prompt`
  (leg 4b) -- the opened item carries its breadcrumb, `dirty` is clear, and the next
  row click opens without a prompt.
- Flight 3's close gates (leg 6) ran the library lane, which holds all three, green.

## Sign-Off

Fixed by M25 F3 leg 4a (`library-list`): creating a knowledge base opens it; closed with the Flight 3 flight commit.
**Reviewer**: the Flight 3 flight-end Reviewer
**Verdict**: pending the flight-end review (the Flight Director records it at the flight commit)
**Commit**: the Flight 3 flight commit (`flight/3: …`)
