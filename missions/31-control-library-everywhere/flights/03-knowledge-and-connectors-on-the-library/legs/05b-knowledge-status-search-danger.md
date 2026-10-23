# Leg: knowledge-status-search-danger

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Move the knowledge-base detail's Status, Search and Danger zone sections onto the library:
- Status: counts as `chip`s with a dataset, chunks and indexer lines patched only on change, re-index buttons;
- Search: `clearableInput` (squawk 0100), library buttons, a generation guard (DD8-5's search half), results and the degraded line;
- Danger zone: `dangerZone` with a header error on failure.

## Context
- **Flight DD4** (`chip` `dataset`, `clearableInput`; leg 03b), **DD5**, **DD6** (Status lines on `status` with `live:'off'` and `led:false`, set only on change; Search with `clearableInput`, where clearing also clears the results and the degraded line; the danger zone and the header error), **DD7** item 2 (the × clear) and item 5 (the danger-zone trash icon and armed style), **DD8-5**, **DD9** (closes 0100), **DD10**, **DD11.**
- **Leg 02** put these sections in `knowledge-status.js` (`{update}`), `knowledge-search.js`, and the danger zone in `knowledge-detail.js`. **Leg 05a** put the frame on `editorShell` and added `destroy` stubs. Read both flight-log entries first.
- **Today's code** (from `knowledge-section.js:1290-1480` at `332496d`):
  - **Status:**
    - `kb-status-summary` is rebuilt on every `update` (`textContent = ''`);
    - "Loading status…" uses `div.admin-loading`;
    - the counts row has a `span.chip.kb-status-chip` per label (testid `kb-status-count`, `data-status`), text "{label}: {n}";
    - `kb-chunk-count` "Chunks: N";
    - `kb-indexer-state` "Indexer: X";
    - the re-index hint `kb-reindex-scope-hint` (`field-hint`);
    - the `kb-reindex-row` buttons `kb-reindex-changed-btn` "Re-index changed files" and `kb-reindex-all-btn` "Re-index all files" (outlined, disabled during the request, then `refreshStatusNow()`).
  - **Search:**
    - `kb-search-input` (`data-field=q`, label "Search", placeholder "Search this knowledge base");
    - `kb-search-btn` "Search", with Enter running the search;
    - `kb-search-degraded` (`field-error kb-search-degraded`, hidden), text "Degraded: {d} (indexer: {i})";
    - `kb-search-results`: "Searching…" (`admin-loading`), then the hits `kb-search-hit` (`.kb-search-hit-path`, `.kb-search-hit-score` "score: 0.123", `.kb-search-hit-text`), "No results." (`empty-state`), or a `field-error` on failure;
    - an empty query clears the results and returns;
    - there is no generation guard.
  - **Danger zone:**
    - a hand-built `editor-section danger-zone`, "Danger Zone";
    - `btn-muted-destructive delete-btn` `delete-knowledge-base-btn`, with the trash icon (`_appendIcon`) and "Delete Knowledge Base" (`data-confirm-title`);
    - `App.confirmDelete(deleteBtn, (el, revertFn) => DELETE …)`, then `invalidate('knowledge-bases')` and `invalidate('agents')`, then `onDeleteSuccess`;
    - on failure only `revertFn()`, silent (DD6 changes this).
- **Tests:**
  - `test_flow_studio_knowledge_inventory.py`: `.kb-search-hit-score` (about `:655`), the danger zone's icon and text (`:219-228`), `kb-status-count[data-status]`, the section-title order list (`:572-584`), the delete flow;
  - `test_agents_library_isolation.py`;
  - `tests/behavior/kb-studio-round-trip.md` steps 6-8 (search with its score) and 14-18 (delete).
- **The `test_store_static.py` delete row** (in `knowledge-detail.js` after leg 02): keep the order DELETE → `invalidate('knowledge-bases')`/`invalidate('agents')` → `onDeleteSuccess`, or retarget it.

## Inputs
- Legs 02, 03b and 05a landed.

## Outputs
- **Status** (`knowledge-status.js`):
  - **built once:** the counts row as one `App.ui.chip({label, dataset: {status}, testid: 'kb-status-count'})` per label (keep the `kb-status-chip` look: if the plain library chip differs computed-wise, add a ledger row); the chunks line and the indexer line as `App.ui.status({led: false, live: 'off', testid: …})` or plain text nodes with area layout classes, kept as testids `kb-chunk-count`/`kb-indexer-state`, whichever matches today's look exactly (pick and record it);
  - `update(status)` **patches only what changed:** each chip's text and the two lines are set only when their text differs. A test pins that an unchanged tick rewrites nothing (a MutationObserver over `kb-status-summary` records no mutations);
  - loading is a `status` pending line ("Loading status…"), replacing `admin-loading`;
  - the hint is a library field hint or `section` description (the text unchanged);
  - the re-index buttons are `App.ui.button` (outlined, testids kept), disabled during the request.
- **Search** (`knowledge-search.js`):
  - **the input:** `App.ui.clearableInput({testid: 'kb-search-input', dataset: {field: 'q'}, placeholder: 'Search this knowledge base', clearTestid: 'kb-search-clear-btn', onClear})` inside `field({label: 'Search'})`;
  - **clearing:** the × or Escape-with-text empties the query, clears the results and hides the degraded line, the same as today's empty query;
  - `kb-search-btn` is `App.ui.button`, and Enter runs the search as today;
  - **a generation guard:** each `runSearch` takes a token. A response for an older token, or after `destroy`, is dropped (DD8-5);
  - "Searching…" is a `status` pending line;
  - **the degraded line** is a `status` line (`led: false`, the state that matches today's `field-error` colour; a ledger row if the computed colour differs), testid `kb-search-degraded`, the text unchanged;
  - **hits:** keep their DOM (`kb-search-hit` and its child classes; they are area layout, not library controls), testids and text, including the score format;
  - "No results." is `App.ui.emptyState`, and a failure is a `status` danger line.
- **The danger zone** (`knowledge-detail.js`): `App.ui.dangerZone({actions: [{label: 'Delete Knowledge Base', testid: 'delete-knowledge-base-btn', icon: 'trash', onConfirm: function (revert) {…}}]})`.
  - It sends one DELETE: a `deleting` flag until the request settles.
  - On failure: `revert()` plus `shell.setError('Delete failed')` (DD6: no longer silent; a ledger row).
  - On success: the invalidations and `onDeleteSuccess`.
  - Writes after `destroy` are gated.
- **Aliases:** the `App.confirmDelete` call here goes (one of the knowledge modules' two; the other is the folder delete, 06a). `_appendIcon`'s `App.icon(` stays only if the folders module still uses it (06a removes it).
- **Squawk 0100:** its Corrective Action and Verification are written, with status `in-progress`.
- **New tests:**
  - (a) type a query, search, press ×: the query, results and degraded line are cleared, and focus is in the input;
  - (b) Escape with text does the same;
  - (c) two searches, where the first response is delayed (`page.route` holds it) and arrives after the second: the second's results stay;
  - (d) a failed DELETE (route-stubbed 500) shows the header error and the button reverts;
  - (e) a double confirm sends one DELETE;
  - (f) an unchanged poll tick records no DOM mutation in the status summary.

## Design review amendments (binding; they supersede earlier text where they differ)
Design review cycle 1 (Sonnet Developer): approve with changes. **The citations after the split:**
- Status: `knowledge-status.js:39-66` (`renderStatusSummary`), the hint `:77-86`, the buttons `:87-94`, `triggerReindex` `:95-116`;
- Search: `knowledge-search.js:19-88` (`runSearch` `:39-77`);
- Danger: `knowledge-detail.js:262-299` (`confirmDelete` `:287`).

1. **Coloured status text.** A `status` line with `led:false` has no state colour today. Leg 03b is amended to add `textTone: true`: for `danger` and `warning`, the text takes `--status-danger`/`--status-warning`, with contrast-gated pairs. The degraded line uses `status({state: 'danger', led: false, live: 'off', textTone: true, testid: 'kb-search-degraded'})`, matching today's `field-error` red, and so does the search failure line. Each is checked computed-wise, and a ledger row is added if it differs.
2. **The search guard:**
   - `runSearch` bumps the token **before** the empty-query early return;
   - clearing and `destroy` bump it too;
   - a late `.then` **and** `.catch` are both dropped;
   - "Searching…" is replaced only by the current token's result;
   - test (c) also asserts that "Searching…" is gone after the second search resolves.

   Nothing on the `input` path triggers a search. Enter runs it on `c.input`, and the Search button stays on its own row below the field, as today, outside the clearable wrapper.
3. **Delete failure goes to the danger zone's own notice,** not the header: `dangerZone`'s `notice` (`role=alert`, next to the button, testid `kb-delete-error`, `setNotice(text)`) with `fetchJson`'s error text.
   - This amends flight DD6 (recorded in flight.md): an error far from a bottom-of-page button would be invisible.
   - Leg 07b's connector danger zone and leg 06a's folder delete use the same rule for their own failures: 07b the notice, 06a the header, because the folder delete sits at the top of the page.
4. **One DELETE:**
   - a `deleting` flag in the `onConfirm` closure short-circuits every later `onConfirm`;
   - `danger.setDisabled(true)` while deleting;
   - on failure: `revert()`, `setDisabled(false)`, `deleting = false`, and the notice.

   Test (e) covers a second and a third click. The `api:App.confirmDelete(` allowance row for `knowledge-detail.js` goes.
5. **The "Loading status…" state is dead code:** the glue mounts only after `/status` resolves, and `update` never receives null. Delete it; no ledger row.
6. **`.kb-status-chip` has no CSS:** the chips are plain `App.ui.chip`, so there is no visible change. The chunks and indexer lines are `status({led: false, live: 'off', testid})`, which computes like today's `.kb-chunk-count`/`.kb-indexer-state` (`body-sm`, `--fg-secondary`). `.kb-status-counts` stays as area layout.
7. **Patching on change is the caller's job.** The chips are built once in `STATUS_LABELS` order, and `update` caches the last strings and writes only changed text. Test (f) observes `kb-status-summary` (the container) across two real poll ticks (about 11 s) with a stubbed, unchanging `/status`.
8. **Re-index:** the requests are gated by `isCurrent`, and a failure stays silent, as today (no behaviour change). The hint is `section`'s description with testid `kb-reindex-scope-hint` (`p.section-description`); the `.kb-reindex-hint` margin is lost, so add a ledger row for the computed difference.
9. **"No results."** is `App.ui.emptyState`, with a ledger row if it differs computed-wise. A null score throwing into `.catch` is pre-existing and stays.
10. **Registry:** `kb-search-clear-btn` and `kb-delete-error` rows. Confirm that the registry scanner sees testids passed as `testid: '…'` options (it matches the `[a-z]+Testid`/`testid:` patterns, per the leg 07b review).
11. **Behavior spec steps:** delete is steps 17-18 (not 14-18); step 14 is the rename (05a); search is step 7.

## Acceptance Criteria
- [ ] Status, Search and the Danger zone are built from library controls, with no hand-built danger-zone, button or loading markup left in these modules.
- [ ] Tests (a)-(f) pass. (c), (d) and (e) are recorded as failing before the fix. The existing knowledge tests and `kb-studio-round-trip.md`'s steps still describe the UI (amend any step that names a changed class or text).
- [ ] `App.confirmDelete` has no call in `knowledge-detail.js`, and the ownership rows for the classes these sections stop emitting are removed.
- [ ] The `library`, `mcp`, `routing` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1`, and so do `make test-unit` and the static guards.
- [ ] **Ledger rows:**
  - the search × (DD7-2);
  - the danger zone (DD7-5);
  - the delete-failure message (DD6);
  - the warning chip, if the standalone badge moved here (it is 06a's);
  - any computed difference in the status chips or lines, or the degraded line.
- [ ] The `library` lane's time is reported against its budget.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_studio_knowledge_inventory.py -x --timeout 60`; the four lanes; `make test-unit`.

## Implementation Guidance
1. **Log a start line.** Write tests (c), (d) and (e), and see them fail.
2. **Status,** then Search, then the Danger zone, running the knowledge inventory file after each.
3. **Pins, allowances, the squawk, the ledger, the flight log.**

## Edge Cases
- **The score format** (`hit.score.toFixed(3)`) and the "score:" prefix are pinned by the behavior spec. Keep them.
- **Clearing during an in-flight search:** the clear bumps the generation, so the late response is dropped.
- **Enter on the clearable input** still runs the search, and Escape is handled by the control.

## Files Affected
- `js/areas/studio/knowledge-status.js`, `knowledge-search.js`, `knowledge-detail.js`
- `css/studio.css`: dead status, search or danger rules, after grep
- `tests/browser/test_flow_studio_knowledge_inventory.py`, `tests/test_store_static.py`, `tests/_ui_ownership_allowance.py`, `docs/ui-testid-registry.md` (the new `kb-search-clear-btn`; move the manual-exception rows for `kb-reindex-*`/`kb-search-btn` to the literal table)
- `tests/behavior/kb-studio-round-trip.md` (if a step changes)
- `squawks/0100-kb-search-has-no-clear-button.md`
- The flight log

## Citation Audit
Drafted at `332496d` from `knowledge-section.js:1290-1480` (FD read). **Re-cited by module and function after leg 02 lands,** before this leg goes `ready`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
