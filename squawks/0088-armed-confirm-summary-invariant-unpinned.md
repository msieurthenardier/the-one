# Squawk 0088: nothing pins the invariant the folder-delete confirm depends on

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: —

## Report

The per-folder delete in Studio's knowledge-base detail view uses the canonical
two-step `App.confirmDelete`, armed on the folder's `<summary>` with the
folder-path span as the `[data-confirm-title]` target. The helper arms for 3
seconds; the page polls every 5. So the confirm is only reliable because **no
render path may rebuild or rewrite a folder's `<summary>` while it is armed** — a
tick that did would either destroy the armed node or capture the placeholder text
("Confirm delete?") as the "original" and write it back on revert.

M24 F06 L06's L6-D3 names three behaviours this rests on:

1. `renderFolders` reconciles by folder id and `appendChild`-moves existing nodes
   rather than recreating them.
2. `updateFolderMeta` writes only the status and watch chips, never the path span.
3. `renderAllItems` must not rebuild the summary either — it reaches a panel only
   through `renderFolderFiles`, which writes `panel.filesEl` (the panel *body*).

**All three hold today. Only the first two have any test behind them.** The third
was found by the implementing Developer during review and written into the leg
artifact, but nothing mechanically enforces it: a future change that re-rendered
folder summaries on an items-signature tick would break the armed confirm with
both of the other invariants still satisfied, and every existing test would still
pass.

The failure mode is quiet and unpleasant — a confirm that intermittently fails to
arm on an irreversible, server-side cascading delete (the folder, its file items,
and their chunks).

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js:1111`
  — `renderFolderFiles(panel, fileItemsForFolder, folder)` writes `panel.filesEl` only
- `:1128` / `:1153` — `renderAllItems` reaches panels solely via `renderFolderFiles`
- `the_one/interfaces/web/static/js/confirm.js` — the 3-second `revertMs` and the
  arm-time title capture the invariant protects
- `missions/24-knowledge-bases/flights/06-studio-surfaces/legs/06-inventory-detail-restyle.md`
  — L6-D3, which names the third invariant and states plainly that the guard is
  raised separately rather than carried by that leg

## Corrective Action

*(pending)* Add one browser assertion: arm the confirm on a folder panel, drive an
**items** refresh (not merely a status tick), and assert the summary is the same
DOM node and still carries the armed state — the same node-identity technique the
existing open-state-across-poll test already uses.

## Verification

*(pending)* The new assertion fails if `renderAllItems` is changed to rebuild
summaries, and passes against current `main`.

## Sign-Off

*(pending)*
