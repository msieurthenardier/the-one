# Squawk 0088: nothing pins the invariant the folder-delete confirm depends on

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: 2026-09-19

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

Added `test_armed_folder_confirm_survives_items_signature_tick` to
`tests/browser/test_flow_studio_knowledge_inventory.py`: arms the folder-delete
confirm, drives an **items** refresh (not merely a status tick) via a real
content-only edit + a direct `POST .../reindex?scope=changed`, and asserts the
`<summary>` is the same DOM node (a stamped `data-lapse-invariant-probe`
attribute) and still carries `.confirm-delete` afterward — the same
node-identity technique `test_folder_panel_open_state_survives_poll_ticks`
already uses for the first two invariants.

Mission 24 Flight 7 confirm-lapse leg's AC-10a raised a real timing hazard the
original Corrective Action sketch did not account for: arming and then simply
waiting on the real walk → hash → chunk → embed → 5-second-poll pipeline would
let the confirm's own 3-second `revertMs` fire BEFORE a naturally-timed tick
ever arrived, failing (or passing) for reasons unrelated to the invariant. The
landed test avoids the race two ways: (1) the signature-changing edit is
driven and CONFIRMED directly (`httpx` against the reindex endpoint, then a
tight polling loop against `GET .../status` for `content_freshness` to move)
rather than by sleeping on the pipeline's own latency, so the change is
already in the database before anything is armed; (2) the arm click is
phase-locked to the app's own 5-second status poll (observed live via
`page.expect_response`), so the very next natural tick lands well inside the
3-second window instead of racing an arbitrary point in the cycle.

## Verification

Observed the falsification directly, per the leg's AC-10: temporarily changed
`renderAllItems` (`knowledge-section.js`) to replace each folder's
`<summary>` element with a freshly-built one on every call (simulating a
future refactor that reintroduces the regression), ran the new test alone,
and confirmed it failed. The actual failure was sharper than "the class
didn't survive": the delete button's click handler closes over the
ORIGINAL `summary` variable from `buildFolderPanel`'s scope, so once
`renderAllItems` swaps in a new `<summary>` node, clicking the (now
re-parented-looking but still-live) trash button armed the stale, detached
node while the visibly-displayed summary showed no feedback at all — a
concrete instance of exactly the failure mode squawk 0088 describes ("a
tick that did would either destroy the armed node..."). Reverted the
temporary change and re-ran the test to confirm it passes against the real
implementation. See the flight log
(`missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`) for
the recorded before/after output.

The test pins the *invariant* (the summary node's identity and armed state
survive an items-signature tick), not today's call graph — a future refactor
that keeps summaries intact through a different code path still passes.

## Sign-Off

**Reviewer**: flight-end Reviewer, Mission 24 Flight 7 (Sonnet tier)
**Verdict**: confirmed — "the invariant is pinned by a test that drives a real
items-signature tick against an armed folder confirm and asserts the summary
node survives; the test was falsified before being trusted."
**Commit**: e7fea7e (`flight/07-mission-close`, Leg 03 `confirm-lapse`)

**Note**: the falsification found the failure mode is **worse than this squawk
described**. This report predicted a confirm that "intermittently fails to
arm". In fact the delete button's click handler closes over the stale,
now-detached `summary` from `buildFolderPanel`'s closure — so a rebuild arms an
**invisible** node while the displayed summary shows nothing. A silent phantom
arm, not a failure to arm.
