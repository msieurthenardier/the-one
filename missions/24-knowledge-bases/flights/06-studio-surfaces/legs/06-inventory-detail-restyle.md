# Leg: inventory-detail-restyle

**Status**: landed
**Flight**: [Studio Surfaces](../flight.md)

## Objective

Restructure the knowledge-base detail view to the MCP server editor's shape: an
always-editable header, a disabled-until-dirty Save/Cancel pair, folders as
expandable panels containing their own files, and the shared Danger Zone.

## Context

Second round of HAT findings, 2026-09-19, raised with reference screenshots of
`mcp-server-editor.js`'s rendered output. The operator's brief, verbatim in
substance: title and description at top, **no edit button** — Save enables on
change with a Cancel beside it; then Status; then a folders section using **"Add
folder"** rather than "Register folder"; each folder on **one line with a delete
icon**, and **correctly sized as an expandable panel with the files inside**;
Danger Zone styled the same.

**Classified as a FEATURE** — it restructures the page's information
architecture and its save model, not its appearance. But the risk is much lower
than a typical feature, because **every pattern already exists and is named**:

| Need | Existing pattern to reuse |
|---|---|
| Title + subtitle header | `editor-title` / `editor-subtitle` |
| Back / Cancel / Save trio | `btn-outlined-primary back-btn`, `cancel-btn` (disabled until dirty) |
| Expandable panel | **native `<details>` / `<summary>`** with a chevron — `mcp-tool-item` / `mcp-tool-summary` |
| Danger Zone | `editor-section danger-zone` + `section-title danger-zone-title` + `btn-muted-destructive` |

**Nothing new is invented.** Where the MCP editor already solves a problem, copy
it rather than parallel-inventing.

## Leg Design Decisions

**L6-D1 — Fields are always live; Save and Cancel are disabled until dirty.**
The edit-button-then-form model added in Leg 5 is removed. Name and Description
render as ordinary fields in the header region, editable immediately. **Save**
and **Cancel** sit beside **Back** in the header, both `disabled` until the form
is dirty, exactly as `mcp-server-editor.js` does. Cancel reverts to the loaded
values and clears dirty.

The dirty bridge added in Leg 5 (`onDirtyChange` → Studio's `inEditor`) stays and
now covers a form that is *always* live rather than one behind a button — which
makes it more load-bearing, not less.

**L6-D2 — Folders become native `<details>` panels containing their own files.**
Each registered folder is one summary line carrying its path, walk status, watch
state and a **delete icon**; expanding it reveals the files indexed *from that
folder*. Use native `<details>`/`<summary>`, as the MCP tools list does — it is
keyboard- and screen-reader-accessible for free, and the alternative is
re-implementing disclosure by hand.

**The open question this raises, which must be answered before implementation:
where do items with `parent_id = null` go?** DD-9's "standalone" badge exists
precisely because an item can sit inside a folder's path without being its child.
Three options, and the leg picks one rather than leaving it to the implementer:

- **(a)** Group by `parent_id`; render any parentless items in a trailing
  "Other items" panel. ✅ **Chosen** — it is truthful (it does not pretend a
  standalone item was discovered by the folder), it keeps DD-9's distinction
  visible, and it degrades to nothing when the list is empty.
- (b) Nest parentless items under the folder whose path contains them. Rejected:
  it would render a *false* parentage, which is exactly what DD-9's badge exists
  to prevent.
- (c) Keep a flat list beside the folders. Rejected: it defeats the operator's
  stated point, which is that files belong inside their folder.

**L6-D3 — "Add folder", and the delete icon replaces the row's remove button.**
The section is titled **Folders**; its control reads **Add folder**. Leg 5's
labelled remove button on the folder row becomes a **trash icon** in the summary
line, taking its *visual* form from the Custom Headers row in the MCP editor.

**Amended after implementation (Flight Director).** The first draft of this
decision said the row "matches the Custom Headers row pattern" without
qualification, and the implementing Developer correctly read that as licence to
drop the confirm step — that row's remove is a bare immediate click. The
analogy does not carry that far, and the Developer flagged it rather than
shipping it silently. **A Custom Headers row is a client-side form row**: it is
added and removed purely in the DOM by `kv-add-row-btn` / `kv-remove-row-btn`
and nothing is persisted until the operator presses Save, so its bare click
costs nothing and is trivially undone by not saving. **Removing a registered
folder is an immediate, irreversible, server-side cascading DELETE** — the
folder, its file items, and their chunks. Borrowing the icon is right; borrowing
the absence of a confirm is not. The two-step confirm from L5-D1 therefore
**survives** this restyle, rendered on the icon via the canonical
`App.confirmDelete` helper (`static/js/confirm.js`) with the folder-path span as
the `[data-confirm-title]` target — the same helper and the same shape as this
page's own Danger Zone delete, and as `chat.js`'s session delete.

This is only safe because of the keyed reconciliation in `renderFolders`:
`appendChild` **moves** an already-attached `<details>` rather than re-creating
it, so an armed confirm is not destroyed by the 5-second poll tick landing
inside the helper's 3-second revert window. `updateFolderMeta` must therefore
keep its hands off the path span — it may rewrite the status and watch chips
only. The two behaviours are coupled; neither is optional.

**A third invariant, named after the implementing Developer flagged it.** The
two above are not sufficient on their own: the *items* refresh path must also
leave the summary alone. It does — `renderAllItems` reaches a panel only through
`renderFolderFiles(panel, …)`, which writes `panel.filesEl` (the panel body) —
but nothing stated that as a constraint, so a future change that re-rendered
summaries on an items-signature tick would break the armed confirm with both
invariants above still satisfied. Stated here so the guarantee rests on three
named behaviours rather than two named ones and one accident. The mechanical
guard that would pin it is not in this leg; it is raised separately.

**The consequence caption from L5-D1 does not disappear with the button.** An
icon carries less meaning than a labelled button, not more, so the cascade
warning must survive the restyle — as section-level helper text under **Folders**,
stating that removing a folder also removes every file indexed from it and their
chunks. Losing that sentence in a visual tidy-up would quietly undo the reason it
was written.

**L6-D4 — The per-row overflow menu stays, and moves inside the folder panel.**
Leg 5's menu for "View chunks"/"View source" now lives on the file rows *within*
each expanded folder. It must still close on list rebuild (Leg 5's single-open
tracker) — and a `<details>` panel collapsing while its menu is open is a **new**
instance of that same leak, so the tracker must cover it.

## Acceptance Criteria

- [x] AC-1 — The detail view renders `editor-title` + `editor-subtitle`, with
      **Back, Cancel and Save** in the header. No edit button exists.
- [x] AC-2 — Name and Description are editable on arrival, with no intermediate
      click.
- [x] AC-3 — Save and Cancel are **disabled until the form is dirty**, and both
      re-disable after a successful save or a cancel.
- [x] AC-4 — Cancel reverts both fields to their loaded values and clears dirty.
- [x] AC-5 — Navigating away dirty still raises the confirm dialog (Leg 5's
      bridge, now over an always-live form).
- [x] AC-6 — Section order is: header/fields → **Status** → **Folders** →
      Search → **Danger Zone**. **AMENDED by the HAT polish pass
      (2026-09-19): Folders now precedes Status** — see the second
      Implementation Notes block. The operator asked for the re-index pair
      to move into Status and for Status to sit below Folders; the shipped
      order is header/fields → **Folders** → **Status** (re-index inside
      it) → Search → **Danger Zone**.
- [x] AC-7 — The folders control reads **Add folder**.
- [x] AC-8 — Each folder is one summary line carrying path, walk status, watch
      state and a **delete (trash) icon**, and expands to reveal the files
      indexed from it.
- [x] AC-9 — Items with `parent_id = null` render in a separate trailing panel,
      **not** nested under a folder whose path happens to contain them. DD-9's
      standalone badge still renders.
- [x] AC-10 — The cascade warning survives as section-level helper text under
      Folders — removing a folder removes its files and their chunks.
- [x] AC-11 — Deleting via the trash icon still removes the folder and its
      items, and the view refreshes immediately (not on the poll).
- [x] AC-12 — Danger Zone uses `editor-section danger-zone` +
      `section-title danger-zone-title` + `btn-muted-destructive`, matching the
      MCP editor.
- [x] AC-13 — "View chunks"/"View source" still work from file rows inside an
      expanded folder, still fetch **only on activation** (DD-8), and an open
      menu does not leak when its `<details>` collapses or the list rebuilds.
- [x] AC-14 — `tests/test_ui_guards.py` passes with **no new dynamic-sink
      entries**; registry matches both ways.
- [x] AC-15 — `make lint` clean, `make test-unit` green, `--lane studio` green.

## Verification Steps

- AC-1 to AC-13: extend `tests/browser/test_flow_studio_knowledge_inventory.py`.
  **Existing tests in that file and in `test_flow_studio_knowledge_attach.py` key
  on testids this leg moves** — re-point them, and check each for a *content*
  assertion rather than assuming a selector swap suffices. Leg 1 and Leg 5 both
  hit that trap.
- AC-9 needs a fixture with a standalone item — create one directly via
  `POST /items` with `type: "file"` and no `parent_id`.
- AC-15: `make lint`; `make test-unit` verbatim, alone, foreground; then the lane.

## Edge Cases

- **A knowledge base with no folders** — the Folders section renders its empty
  state and the Add control, not a bare heading.
- **A folder with zero indexed files** (all filtered by the walk) — the panel
  expands to an empty state, not a broken list.
- **Dirty fields + a poll tick** — the 5-second status poll must not clobber
  what the operator is typing. The poll updates status and, on a signature
  change, the items list; **it must never re-render the name/description
  inputs.** This is the one genuine hazard the restyle introduces, because the
  fields are now always live rather than mounted behind a button.
- **Save with an unchanged name** — L2-D9's early returns still gate the
  cross-entity rewrite; unchanged from Leg 5 and already covered by tests.

## Files Affected

- `static/js/areas/studio/knowledge-section.js` — the restructure
- `static/js/areas/studio.js` — callbacks if the signature changes
- `static/css/studio.css` — reuse MCP classes; add only what is genuinely new
- `docs/ui-testid-registry.md`
- `tests/browser/test_flow_studio_knowledge_inventory.py`,
  `tests/browser/test_flow_studio_knowledge_attach.py`

## Implementation Notes

**Follow-up pass (post-amendment of L6-D3, 2026-09-19).** The first
implementation of this leg shipped the folder delete as a bare single click
and flagged it. The Flight Director amended L6-D3 above; this pass
implements that amendment. What changed, all of it localized as the flagging
Developer predicted:

- `knowledge-section.js` — `buildFolderPanel`'s trash-button handler now
  routes through `window.App.confirmDelete(summary, …)`; the `<summary>` is
  the state element and the folder-path span carries `[data-confirm-title]`.
  `deleteFolder` gained a third parameter, `revertFn`, called on the
  transport-failure path beside the existing re-enable + flash, so a failed
  DELETE rolls the armed row back instead of stranding it reading "Confirm
  delete?" over a folder that still exists. This mirrors the same file's
  Danger Zone `delete-knowledge-base-btn` handler exactly.
- The file's header L6-D3 block and the per-button comment both asserted the
  single-click choice; both are rewritten to state the amended reasoning
  (the Custom Headers row supplies the icon's visual form, not its bare
  click, because that row persists nothing until Save whereas this one is an
  irreversible server-side cascading DELETE).
- `updateFolderMeta` was already innocent — it writes only the two chips and
  the meta body, never the path span. It now carries a comment saying it
  must stay that way, and why: while armed, the path span holds
  `App.confirmDelete`'s placeholder and the helper reverts from a value
  captured at arm time, so a tick that rewrote the span would either wipe
  the armed signal or get its own text captured as the "original". This is
  the second half of the coupling; `renderFolders`' move-don't-recreate
  reconciliation is the first.
- `studio.css` — the canonical `.list-item.confirm-delete` rules are scoped
  to `.list-item` / `.delete-btn` and match no `<summary>`, so without a
  rule the armed row would have swapped its text with **no danger
  affordance at all**. Three rules added, scoped to a new
  `kb-folder-summary` class (same local-override precedent as
  `kb-folder-delete-btn` beside `kv-remove-row-btn`): the danger colour on
  the `<details>`'s **existing** border (recoloured, not added — an added
  1px border would jump the row under the operator's cursor between the two
  clicks), on the swapped-in title, and on the trash glyph. Existing tokens
  only (`var(--status-danger)`); no new tokens, no colour literals. The
  `:has()` selector's (0,4,0) specificity beats the (0,3,0)
  `.mcp-tool-item:hover` accent-border rule above it; `:has()` was already
  in use in `components.css`, so it is not a new technique here.
- **`aria-label` judgement.** The armed state's visible signal is the path
  span's text swap — a different element from the button, and not part of
  the button's accessible name, so a screen-reader user would otherwise get
  no announcement of the state change. Rejected: mutating the label on arm
  (the helper's internal 3-second auto-revert offers no hook to undo it, so
  the label would go stale and actively lie) and an `aria-live` region on
  the path span (a live region on a node the poll is adjacent to, for one
  transient string, is more machinery than the problem). Chosen: state the
  two-step **once, statically**, in the name announced on focus —
  `"Delete folder {path} (press twice to confirm)"`. It cannot go stale, it
  sets the expectation before the first press, and it adds no new mechanism.
  Residual, and NOT introduced here: a screen-reader user who takes longer
  than 3 seconds between presses silently re-arms rather than committing.
  That is inherent to `App.confirmDelete` and equally true of this page's
  Danger Zone button and chat's session delete — a helper-wide question, not
  this leg's to answer.
- **Tests** — `tests/browser/test_flow_studio_knowledge_inventory.py`:
  `test_folder_remove_single_click_…` is rewritten as
  `test_folder_remove_two_step_confirm_cascade_hint_and_immediate_refresh`
  (first click arms and issues **no DELETE**, proven by a
  `page.on("request")` counter rather than a DOM-stability sleep; second
  click commits, wrapped in `expect_response` so a revert-window expiry
  under load fails as a missing-DELETE timeout rather than a confusing
  downstream failure — the `test_flow_agent_crud.py` idiom). New
  `test_folder_panel_open_state_survives_poll_ticks` proves the
  reconciliation half of the coupling: expand a panel, await two real
  `/status` **responses** (not a wall-clock sleep — `renderFolders` runs in
  the response handler, so the second response's arrival proves the first
  tick rendered), then assert the panel is still `open` **and** still the
  same DOM node, via a probe attribute stamped on it before the ticks. The
  ~10s this costs is well inside this file's existing budget (it already
  waits 30s for a real indexing pass and sleeps 6s elsewhere), so no
  alternative was needed.
- `docs/ui-testid-registry.md` line 88's `kb-folder-delete-btn` entry
  rewritten to match. No new testids were introduced — the two new selectors
  are CSS classes (`kb-folder-summary`, and the existing `kb-folder-path`),
  which is why `tests/test_ui_guards.py` needed no registry additions.

**Deliberately unchanged**: `kb-folders-cascade-hint` — it is additional to
the confirm, not a substitute for it, and its text and testid are untouched.

**HAT polish pass (2026-09-19, third visit to this leg).** Five
look-and-feel findings from the operator's live HAT walk, all on this one
surface. No behaviour changed: same routes, same `scope=changed|all`
values, same two-step confirm on folder delete, same cascade hint.

1. **Re-index moved into Status; Status moved below Folders.** Both
   buttons POST `/api/knowledge-bases/{kb_id}/reindex`, which is
   whole-knowledge-base by construction (`requeue_for_reindex` is one
   `UPDATE … WHERE kb_id = ?`); there is no per-folder re-index at all.
   Sitting among the per-folder `<details>` panels they read as
   folder-scoped — the operator asked outright whether they were, which
   is the defect. `_section` appends in call order, so the fix is
   ordering: `_section(root, 'Folders')` now runs first and the whole
   Status block (section, `summaryEl`, `renderStatusSummary`, its initial
   call) moved *verbatim* to just after the Folders section's last append,
   taking `reindexRow` with it. Nothing else moved — `renderStatusSummary`
   is a hoisted function declaration and `summaryEl` a hoisted `var`, and
   the earlier `refreshStatusNow` / returned `updateStatus` call sites
   only ever run from an event handler or a promise, long after the
   assignment. Shipped order: header/fields → Folders → Status (re-index)
   → Search → Danger Zone, which **amends AC-6** (annotated above).
   Scope made legible three ways, all in existing vocabulary: labels
   "Re-index changed files" / "Re-index all files" (the old "Re-index all"
   answered "all *what*?" with nothing), a `.field-hint`
   (`kb-reindex-scope-hint`) stating that re-indexing always covers every
   registered folder and there is no per-folder re-index, and the move
   itself putting them beside the whole-knowledge-base counts.

2 & 3. **Both trash affordances became real SVG icons — the guard
   judgement.** `window.App.icon()` returns an SVG *string*, so it
   normally needs an `innerHTML` sink, and `tests/test_ui_guards.py`'s
   `DYNAMIC_SINK_BASELINE` has **no entry for `knowledge-section.js`** —
   any concatenated sink here fails the freeze. `mcp-server-editor.js`'s
   `window.App.icon('trash') + …` is a grandfathered baseline entry, not a
   licence. But the freeze bans *HTML-string sinks*, not icons: reading
   the guard rather than assuming it, `tests/_ui_guard_helpers.py`'s own
   allowance note names `new DOMParser().parseFromString(svg,
   'image/svg+xml')` **the sanctioned no-inner-HTML path** for exactly
   this case, and `markdown.js::injectIcon` already ships it. So a local
   `_appendIcon(parent, name)` was added on that precedent — it parses
   only trusted `icons.js` literals, never untrusted data, and touches no
   scanned sink. `test_ui_guards.py` passes with **no baseline additions**.
   Both items are therefore implemented in full; no compliant-alternative
   substitution was needed.
   - **Item 2 (folder trash too small):** the glyph rendered at the
     summary line's `--font-size-body-sm` (12px). The SVG picks up
     `.kv-remove-row-btn svg { width: 16px; height: 16px }` — the rule the
     borrowed Custom Headers class already carries — so the sizing fix
     cost *no new CSS*, and the local `line-height: 1` override was
     **deleted**: it existed only because the button held a text glyph,
     and the base class's `line-height: 0` is now correct again. One rule
     *was* required, and it is load-bearing rather than cosmetic:
     `.kb-folder-delete-btn svg { pointer-events: none }`. What keeps this
     button from toggling its `<details>` is the summary's default handler
     skipping clicks on a form control — and Blink tests the click's
     **target node itself**, not its ancestors
     (`HTMLSummaryElement::DefaultEventHandler` → `IsClickableControl`).
     With a text glyph the target was the `<button>`; an `<svg>` child is
     its own hit-test target and is not a form control, so every delete
     press would also have expanded/collapsed the panel. Found in review of
     this pass's own diff, before the lane run — and now pinned by an
     assertion (the panel is `open === false` both before the arming click
     and after it) in
     `test_folder_remove_two_step_confirm_…`, since the invariant only
     became breakable with the icon.
   - **Item 3 (red trash on Delete Knowledge Base, with the words):** the
     icon is appended *before* the `[data-confirm-title]` span, so
     `App.confirmDelete` still swaps only the label and the glyph persists
     through the confirm flow — the exact shape `mcp-server-editor.js`'s
     own Danger Zone delete has. Red and layout need no new CSS either:
     `.btn-muted-destructive` is already `inline-flex` with a 6px gap and
     `color: var(--status-danger)`, which the icon's
     `stroke="currentColor"` inherits, and `components.css` already sizes
     `.btn-muted-destructive svg` at 16px.

4. **File rows now read as sub-items of their folder.** `.kb-folder-path`,
   `.kb-item-path` and `.kb-search-hit-path` shared one `font-weight: 500`
   rule, so a file inside a panel rendered at the section's 13px body size
   at weight 500 while its *parent* folder's summary line sat at 12px
   (`.mcp-tool-summary`'s `--font-size-body-sm`) — the child was literally
   bigger than the parent. `.kb-item-path` is split out to
   `--font-size-body-sm` + `--font-weight-regular`, putting it a clear
   notch below the folder. Both consumers of that class are file rows (a
   folder panel's body and the trailing "Other items" panel), so no
   scoping split was needed; `.kb-folder-path` / `.kb-search-hit-path`
   keep medium weight, neither being a sub-item of anything, and the
   literal `500` became `var(--font-weight-medium)` on the way past.

5. **Space under "Add folder".** `.kb-folders-list` gained
   `margin-top: var(--space-3)` — the same `--space-*` vocabulary
   `.connector-enabled-row` already uses in this file. (`base.css` zeroes
   every margin with a `*` reset, so vertical rhythm here is always
   explicit; the same one-line rule, as `.kb-reindex-hint`, keeps item 1's
   new scope hint off the indexer-state line above it.) Existing tokens
   only throughout this pass: no new tokens, no colour literals, no size
   literals (the two 16px icon sizes are inherited from rules that already
   existed).

- **Tests** — assertions added to
  `tests/browser/test_flow_studio_knowledge_inventory.py`, each folded
  into the existing test that already builds the fixture it needs rather
  than paying for extra browser spawns. In
  `test_detail_view_indexing_poll_reindex_and_search`: the
  `.editor-section .section-title` sequence inside the inventory root is
  asserted as exactly `["Folders", "Status", "Search", "Danger Zone"]`
  (deliberately order-encoding — this is the amended AC-6, and the point
  of the change), both re-index buttons are asserted to live *inside* the
  Status section with their new labels, and the scope hint's two
  load-bearing phrases are asserted. In
  `test_delete_knowledge_base_via_confirm_affordance`: the Danger Zone
  button has exactly one `svg` **and** still reads "Delete Knowledge
  Base", pinning "alongside, not instead of". In
  `test_folder_remove_two_step_confirm_…`: the summary trash is an `svg`,
  and the panel is `open === false` both before the arming click and after
  it (the `pointer-events` invariant above). No existing assertion was
  weakened or removed; the only pre-existing
  assertions that touched this surface keyed on testids, none of which
  changed.
- `docs/ui-testid-registry.md` — one new literal testid
  (`kb-reindex-scope-hint`); the two `kb-reindex-*-btn` manual-exception
  rows re-described with their new labels and their new home in Status.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`; `--lane studio`)
- [x] Update flight-log.md
- [x] Set status to `landed`
- [x] Do NOT commit — the Flight Director commits
