# Flight Log: Knowledge and connectors on the library

**Flight**: [Knowledge and connectors on the library](flight.md)

## Summary
Planned 2026-10-22 from `main` at `08562ec`. The branch is `flight/03-knowledge-and-connectors-on-the-library`.

---

## Planning Notes

- **The split.** The mission's Flight 3 ("Library and Settings on the library") was two independent clusters of decisions, about 20 legs. On 2026-10-22 the operator chose to split it:
  - this flight is the Library half (knowledge bases and connectors);
  - Settings is Flight 4;
  - the MCP server editor moves to 5, Chats and the close to zero to 6, and Alignment to 7.
- **Operator decisions, 2026-10-22:**
  - the library switch replaces the legacy iOS switch (here, the connector's Enabled row; in Flight 4, the Settings uses);
  - squawk 0100 gets an explicit × clear button;
  - squawk 0192's label is "Knowledge bases" everywhere;
  - a HAT closes the flight (standing choice: a HAT per flight).
- **Planning surveys at `08562ec`** (three read-only surveyors):
  - Settings (carried to Flight 4);
  - Library;
  - cross-cutting: the catalogue, alias counts, the contracts lane, the capture tool, squawks, behavior specs, the testid registry.
- **Flight Director calls, made out loud** (each follows an earlier decision or keeps today's look):
  - patch in place on Save (Flight 2 DD6);
  - a value-model dirty state (Flight 2 debrief recommendation 3, applied to these editors only);
  - the key-value table's core built here, with the masked column in Flight 5;
  - the admission lists and the channel map's agent column keep their inputs;
  - knowledge-base Create stays enabled before typing (`enabledWhenClean`);
  - one header error surface per editor;
  - the danger-zone, status-line and sentence-case canonical forms from Flight 1 DD8.

### Debt at the start (`08562ec`)

| File | Reuse rows / uses | Sinks |
|---|---|---|
| `knowledge-section.js` | 27 / 62 | 0 |
| `connector-editor.js` | 26 / 40 | 3 |
| `knowledge-glue.js` | 0 / 0 | 3 |
| `connector-glue.js` | 0 / 0 | 1 |
| `mcp-glue.js` | 0 / 0 | 1 |
| `css/studio.css` (knowledge, connector, confirm-on-summary rows) | part of 7 / 12 | n/a |
| **Whole app** | 187 / 409 | 46 |

## Reconnaissance Report

Squawks and debrief items sourced into this flight, checked against `08562ec`:

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| 0100 KB search has no clear button | confirmed-live | `knowledge-section.js` about `:1378-1382`: only an input and a button | Fold in (DD4, leg 05) |
| 0191 duplicate Library group lists | partially-satisfied / drifted | `hydrateState`'s copy is gone; `library-pane.js:114-117` `isLibrarySection` and `studio-route.js` about `:186` still hand-list beside `LIBRARY_GROUPS:60` | Fold in at the drifted sites (leg 08) |
| 0192 "Knowledge" vs "Knowledge bases" | confirmed-live | `router.js:440` | Fold in, operator label "Knowledge bases" (leg 08) |
| 0093 same-named KBs indistinguishable | confirmed-live | Rows show name plus agent count (`library-pane.js` about `:206-244`); the list API has no folder path | Keep open: needs an API change (DD9) |
| 0233 exact script-count pin | confirmed-live | `test_index_asset_cache_busting.py:99` `== 93` | Fold in, first (leg 01) |
| 0235 editor contracts undocumented | confirmed-live | No tab-handle, `mountSlot` or `state` section in `agents.md` | Fold in, first (leg 01) |
| Flight 2 debrief: `App.ui.disclosure` | confirmed-live | Native `<details>` built in `knowledge-section.js` (folder panels, Other items), `self-config-history.js:80`, `tile.js` toolRow, `mcp-error.js`, `trace-shell.js`, `mcp-server-editor.js` | Build in leg 03 |
| Flight 2 debrief: split `contracts` | confirmed-live | 1010 tests in 27 files | Leg 01 |
| Flight 2 debrief: snapshot model | confirmed-live | Connector sticky `markDirty` (`connector-editor.js:591`); KB JSON-from-DOM snapshot | DD5 for these editors |
| 0222 / 0234 profile the unit tier | duplicates | Both ask for a `--durations` profile | Not in this flight; merge when one is done |
| 0228, 0229, 0230, 0232 | confirmed-live | Agent editor and tests | Not in this flight's path |

## Visible-differences ledger

Every leg appends one row for each visible difference it causes (DD7, DD11). The HAT reads this ledger.

| Leg | Surface | Difference | Allowed by | Notes |
|---|---|---|---|---|
| 01 | none | no visible change | DD2 | Groundwork only: lane split, script-count pin, editor-contract docs and tests, report script, capture surfaces. `git diff --stat -- the_one/interfaces/web/static` is empty. |
| 02 | none | no visible change | DD3 | Pure restructure: `knowledge-section.js` split into 7 modules; 7 before/after DOM dumps byte-identical. |
| 03a | none | no visible change | DD4 | Self-configuration history moved onto `App.ui.disclosure` (plain); computed-style parity against a frozen copy of the old `.advanced-collapsible` rules holds in both themes and both engines (everything but `margin-top`, which the area rule keeps at 12px). |
| 03b | none | no visible change | DD4 | Library options only (chip `dataset`/`warning`, `status` `ledTestid`/`textTone`, `editorShell` `save.enabledWhenClean`/`errorRole`, `copyField` `buttonLabel`, `field` `errorTestid`, `section` `descriptionTestid`, `more` icon, `clearableInput`); no consumer changed. The warning chip's small visible change (soft fill and border, gated pair) lands with its consumer leg (05b or 06a), which must add a ledger row. |
| 03c | agent Tools tab | locked chips get the library fill back (`--surface-elevated`, opacity 0.7); an invalid chip list shows its red border | DD7 item 9, DD8-6 | Marker classes `ui-chip-list`/`ui-chip-list-input`; `admin.css` area chip rules narrowed with `:not()`. String-built lists (Settings tools editor, MCP editor) unchanged. |
| 04 | none | no visible change | DD4 | `App.ui.keyValueTable` built in the harness with no consumer yet; the connector channel map migrates in leg 07b (DD7 item 8). |

---
| 05a | KB create form and detail header | Header built by `editorShell`: Cancel and Save/Create are library buttons (`secondary`/`primary`) in place of `btn-outlined-primary`/`btn-filled-primary`; the empty `p.editor-subtitle` is no longer rendered when the description is empty (removed, not hidden); `editor-error` span gains `role=alert` | DD6, DD4 | Computed differences, if any, are the library button's and the shell's own look; same layout and testids. |
| 05a | KB name/description fields | Built by `App.ui.field` + `textInput`/`textarea`: the name hint element exists only while the name is over 43 code points (was a hidden element); the description control gains `field-input` beside `field-textarea` | DD6 | Hint text and testids unchanged; hidden state tests still pass (an absent element is hidden). |
| 05a | KB create form error | `kb-create-error` is an `App.ui.status` line (danger text tone, no LED, role=alert) instead of a `field-error` div; empty until an error | DD6 | Text colour from the status token (`--status-danger` text), same position. |
| 05a | KB loading and failure lines | "Loading knowledge base…" and "Failed to load knowledge base." are `App.ui.status` lines (pending, no LED, `live: off`; danger, role=alert) instead of `.admin-loading` blocks | DD6 | Loses the old `.admin-loading` 20px vertical padding and body-size text (status line is body-sm, margin 0). |
| 05a | KB Save | Save patches the frame in place: no remount, so the breadcrumb, expanded folder panels, open chunks/source panels, search query and results and scroll survive; the inputs are disabled while Save is in flight and the saved (trimmed) name is written back | DD5 | Save no longer re-fetches `/status` and `/items`. Behaviour difference, intended. |
| 05a | KB create, Cancel while in flight | Cancel is disabled while Create is in flight (`setBusy`) | DD5 | New; a double Create was already prevented. |
| 05a | KB non-JSON errors | A non-JSON error body reads "Server error N …" (`App.api.fetchJson`) instead of "Create failed"/"Save failed" | DD6 | JSON `detail` errors unchanged. |
| 05b | KB Status section | Chips are plain `App.ui.chip` (no `kb-status-chip` CSS existed, so no visible change); the chunks and indexer lines are `App.ui.status` (`led: false`, `live: off`), computing like the old `.kb-chunk-count`/`.kb-indexer-state` (body-sm, `--fg-secondary`); the DOM is patched only when text changes, so an unchanged poll tick writes nothing. The scope hint is the section's description, so it now sits directly under the "Status" title, ABOVE the counts (was between the counts and the buttons), and loses the `.kb-reindex-hint` top margin | DD6 | Re-index buttons are `App.ui.button` secondary. The "Loading status..." state was dead code and is gone. |
| 05b | KB Search | The query field is `App.ui.clearableInput` with an in-field x button (squawk 0100): x or Escape-with-text clears the query, results and degraded line; the Search button is a library button on its own row; "Searching..." and a failure are `status` lines (failure: danger text tone, role=alert); "No results." is `App.ui.emptyState` (a `p` title in `.empty-state`); the degraded line is a danger-tone `status` line (red text, no LED, was a `field-error` div) | DD6, DD7 item 2 | A late response from an older search, or after leaving, is dropped (generation token). Hits keep their DOM, text and score format. |
| 05b | KB Danger zone | `App.ui.dangerZone` (same markup and look: trash icon, "Delete Knowledge Base"); a failed DELETE now shows the server's reason in the zone's own notice (`kb-delete-error`, role=alert) and reverts the button (was silent); a second click while the DELETE is in flight sends nothing and the button is disabled | DD6 (amended: notice, not header), DD7 item 5 | A fetchJson failure with no JSON detail reads "Server error N ...". |
| 06a | KB folder panels | Panels are `App.ui.disclosure` (bordered), chips `status:`/`watch:` as `meta`, the delete is a library ghost icon button in `actions`. Parity expected; the summary's accessible name is now the path plus the two chips (the delete keeps its own name). Path text: the disclosure text has no medium weight (`.kb-folder-path` had `font-weight: medium` and `word-break: break-all`) and ellipsises a long path instead of breaking it; the summary gains the library's `:focus-visible` ring. No consumer CSS on library internals, so HAT should check long paths in both themes | DD4, DD6 | Recorded for the HAT per amendment 5. |
| 06a | KB standalone badge | The "standalone (in ...)" badge is the library warning chip (soft fill and border) instead of a plain chip with warning-coloured text | DD4, 03b | The small visible change 03b reserved for its consumer. |
| 06a | KB folder-delete failure | A failed folder DELETE shows "Couldn’t remove the folder: {reason}" in the editor header (role=alert), cleared when the next Add folder or folder delete starts; the summary reverts and the button is re-enabled (was a flash toast "Error: ...") | DD6 | The server's `detail` is shown when the body has one. |
| 06a | KB folder-delete success | Focus moves to the Add-folder input after a successful folder delete (was lost with the removed button) | DD8 | New. |
| 06a | KB folder rows | A poll refresh no longer closes an open item menu or steals focus from a row control (DD8-4); a poll tick no longer blurs a focused folder summary or delete button (panels are no longer re-appended every tick) | DD8-4 | Behaviour fix, intended. |
| 06a | KB folder meta lines | The folder's walk error, watch error and a failed item's error are danger-tone `App.ui.status` lines (red text, no LED) instead of `field-error` divs | DD6 | Same position and text. |
| 06a | KB folders empty states and Add folder | "No folders registered." and "No files indexed from this folder yet." are `App.ui.emptyState` (a `p` title in `.empty-state`); Add folder is a library field with a secondary library button; its error is the field's error (`aria-invalid`, `aria-describedby`) | DD6 | The cascade sentence is the section description, now directly under the "Folders" title. |
| 06b | KB item menu trigger | The trigger is a library ghost small `more` icon button (was a bordered "⋯" text button: height and border differ); the popup is the library menu | DD4, 03b | HAT should compare the row height and the trigger in both themes. |
| 06b | KB item menu behaviour | The menu closes on pointer-down outside (was a capture click); a pick runs after focus returned to the trigger; one menu open at a time is the library's | DD4, 03b | Intended. |
| 06b | KB inspect panels heading | Each panel has one stable `h3` heading (`kb-panel-title`, `tabindex=-1`) instead of a `div.section-title--plain` rebuilt on every state | DD8-5 | Ledger per amendment 10. |
| 06b | KB inspect panels focus | Opening chunks or source moves focus to the panel heading (was left on a hidden menu item); a late response for an older item or the other panel is dropped | DD8-5 | Behaviour fix, intended. |
| 06b | KB inspect loading/error | Loading is a pending `status` line, an error a danger `status` line (role=alert); "No chunks yet." is `emptyState` | DD6 | Same text. |
| 06b | KB item menu clipping | No clipping rule found in code (the disclosure body has no overflow clip; the popup is absolutely positioned, no flip), so a menu on the last row near the pane's bottom may extend the scroll area | DD4 | HAT item: open a menu on the last "Other items" row. |
| 07a | Connector Enabled switch | `App.ui.toggle` (label beside it) replaces the legacy `.tool-enable-switch` row; the native input is clipped, so tests click `label.ui-toggle-label` | DD7-1 | Same behaviour and `data-field="enabled"`. |
| 07a | Connector token | `App.ui.secretInput` with a reveal eye (was a bare password input); after Save and Cancel the field shows the server's MASK with the reveal off | DD7-4 | Security-tested: no plaintext in any attribute, value or text after Save, Cancel or type-then-revert. |
| 07a | Connector doctor result | `App.ui.status` line (LED + words), hidden until a run; a non-OK response shows the error text in danger (was "undefined: undefined") | DD7-6, DD8-3 | Same testid. |
| 07a | Connector header status | `App.ui.status` line (same text and states); its LED is decorative (aria-hidden), the words and `data-state` carry the outcome; a non-OK automatic probe reads "Connection check failed" (was stuck at "Checking connection…") | DD7-10, DD8-3 | A network failure still leaves "Checking…". |
| 07a | Connector dirty | Revert-to-clean is clean: typing a change and reverting it clears the caption and disables Save (was sticky) | DD5 | Behaviour change, intended. |
| 07a | Connector Save/Cancel | Edit Save and Cancel patch in place (no remount, header node survives); Save and Cancel are disabled while a request is in flight; a create stays busy until the remount | DD5, DD8-2 | Fixes the double-create. |
| 07a | Connector errors | A non-JSON error body reads "Server error N ..." (`fetchJson`) instead of "Create failed"/"Save failed"; the header error slot is role=alert | DD6 | JSON `detail` unchanged. |
| 07a | Connector pairing copy flash | `App.ui.flash` replaces `App.showFlash` for "Copied!"/"Copy failed" | DD6 | Cosmetic only. |
| 07b | Connector pairing code | A read-only input (`copyField`) named "Pairing code" with a "Copy pairing code" button that shows "Copied" (was a `<code>` plus a bare Copy button); the status line holds "Generating…" and failure text | DD7-7 | Same testids; `connector-pairing-code` is now an input (`input_value`). |
| 07b | Connector channel map | `keyValueTable`: header row, trash-icon remove per row (hover red), named inputs ("Channel id, row n"); typed values survive Add and Remove, and a second Save stores the edited value | DD7-8, DD8-1, DD8-8 | Behaviour fix (data loss). Inputs moved from `.channel-map-*` classes to `connector-channel-map-channel`/`-agent`. |
| 07b | Connector danger zone | `dangerZone` trash icon and armed style; one DELETE per commit; a failed DELETE shows `fetchJson`'s text in the zone's own alert (`connector-delete-error`) | DD7-5, DD6 | Was a header error. |
| 08 | Router announcement | "Knowledge" -> "Knowledge bases" (`Library — Knowledge bases[ — {name}]`) | DD7-3, 0192 | Library knowledge group only. The agent editor's Knowledge tab label (`agent-editor.js:43`) is unchanged: a HAT question. |

## Leg Progress

### Leg 01: groundwork-and-before-set (landed, awaiting review)

- **Lane split.** `scripts/run-tests.sh` now has 11 canonical lanes: `contracts-overlay` (explicit list of 11 globs, 12 files) and `contracts-controls` (`test_ui_*` minus overlay, 15 files). `contracts` is an alias (in `resolve_lane`, not `CANON_LANES`). `--help`, the unknown-lane message, header comments, `ci/tasks/browser.yml`, `agents.md` and CLAUDE.md follow. `tests/test_run_tests_lanes.py` pins disjointness, union, budget rows, the alias union and that `test_ui_listener_cleanup.py` stays in controls.
- **Budgets** from a full `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 --parallel 3` run (`PARALLEL_RESULT rc=0 total=1261s lanes=11 failed=-`): `contracts-controls` 199 s, budget 270; `contracts-overlay` 178 s, budget 240 (balance 1.12x, no file moves). No lane over budget (routing 532/600, agents 446/540, chats 352/450, mcp 371/450, providers 339/420, agent-tabs 264/300, library 257/300, settings 258/300, shared 281/300).
- **Squawk 0233** (`in-progress`, Corrective Action and Verification written): `check_static_refs(body)` asserts existence on disk, a single `?v=`, no duplicates and the relative `.js` load order; three negative tests (missing script, area script above `ui/core.js`, duplicate ref) prove it fails. No `len(refs) ==`. The history comment is gone.
- **Squawk 0235** (`in-progress`, written): `agents.md` "Editor contracts (M31 F3 L01)" covers the tab-handle contract (General and Rules and notes are the exemptions; `h.destroy` in `agent-editor.js` calls only `selfConfig.destroy()` and `tabs.destroy()`, recorded as found), the real `mountSlot` API, the 21 `state` fields with owners (`saveInFlight` is not one: it is controller-local) and the hidden-editor patch. `tests/test_studio_editor_contracts_static.py` (3 tests): the `state` key-set pin by brace-balanced parse, the written-key grep and the tab `destroy` check. Tried once and reverted: adding a `state` key and deleting the knowledge tab's `destroy` each fail the right test.
- **`scripts/unused_selectors.py`** plus `tests/test_unused_selectors_script.py` (fixture: used, unused, dynamic-prefixed). Run on `studio.css`: 0 unused. On `admin.css` it reports 12 (for example `.admin-note`, `.admin-placeholder*`), on `components.css` 6 plus dynamic ones, a list for later legs.
- **Capture surfaces** (11, both themes): `library-start`, `kb-new`, `kb-detail`, `kb-item-menu`, `kb-chunks`, `kb-source`, `kb-search`, `kb-status`, `kb-danger-armed`, `connector-new`, `connector-edit`. Seeder `seed_library()`: scratch folder beside the data dir, 4 files, polled to indexed, stub connector with a 2-row channel map; `THE_ONE_STUB_TEST_ENDPOINT=1` on the capture instance only. Masking by MutationObserver (indexed-at, run-id path, scores, watch, pairing code and expiry). Known residue: search hits tied on score may reorder between runs.
- **Before set**: `$HOME/.cache/the-one-ui-capture/m31-f3-before/`, 33 surfaces x 2 themes = 66 PNGs, 0 failed, 4 pre-existing skips, taken at `332496d` (tree dirty only in `missions/` and this leg's files; `static/` untouched).
- **Verification**: `make test-unit` (netns): 6725 passed, 14 skipped (the netns count). ruff check and format clean. `git diff --stat -- the_one/interfaces/web/static` empty. Full `--parallel 3` run rc=0.


### Leg 02: knowledge-split (landed, awaiting review)

- `knowledge-section.js` (1493 lines) deleted; seven ES5 modules replace it: shared 210, create 147, inspect 122, status 124, search 89, folders 634, detail 312 lines (all under 800). `index.html` loads them shared, create, inspect, status, search, folders, detail, before the glue. Exports `App.studio.renderKnowledgeCreate`/`renderKnowledgeDetail` keep their names and signatures. Per-mount state lives in each `create(ctx)` closure; cross-module calls are lazy ctx wrappers; composition order reproduces today's DOM order.
- **DOM check:** seven dumps (create, detail with folder and Other items expanded, after `updateStatus`+`updateItems`, chunks open, source open, dirty, cancelled), taken from a pre-edit HEAD worktree and from the new tree through a Playwright-driven scratch instance with fixed data: `diff -r` empty. The worktree is removed.
- **Pins retargeted:** `test_store_static.py` (create row to `knowledge-create.js`, rename/delete and the count of 2 to `knowledge-detail.js`); ownership allowance rows moved with their call sites (62 rows before and after, per-key totals equal); `docs/ui-control-inventory.md`, `agents.md` (references plus a new "Knowledge modules (M31 F3 L02)" paragraph), `studio.css` comments, and the one docstring in `test_flow_studio_knowledge_inventory.py` (the only browser-test diff). Remaining `knowledge-section` mentions are historical squawks and behavior run logs, left as records.
- **Verification:** static guards (store, ownership, ui_guards, inventory, tokens, a11y, cache-busting) 351 passed; ruff check and format clean; `make gate` (netns, WebKit required): unit 6725 passed, 14 skipped; browser parallel run rc=1 with only `test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url` failing in `shared`; the whole file passes in isolation (18 passed), so it is recorded as a flake, not a regression. library, mcp, routing lanes passed. Lanes `library` (301/300 s), `settings` (404/300), `shared` (474/300), `contracts-controls` (330/270) ran over budget this run, which looks like host load rather than the split (`settings` and `shared` have no knowledge files); worth a re-measure.


### Flight Director Notes
- 2026-10-22: the flight was planned. The Architect review follows.
- 2026-10-22: Architect review, cycle 1: **approve with changes**. All of it was incorporated:
  - **High findings:**
    - `save.enabledWhenClean` is a new `editorShell` option, added to DD4 and leg 03b;
    - DD8-6's mechanism is `@layer areas` outranking `@layer components`, not a specificity tie, so the fix narrows the area rules with a `chipList` marker class (DD4 gains the layer rule, and so does DD11).
  - **Medium findings:**
    - the glue mount paths move to legs 05a and 07a;
    - legs 03, 05 and 06 are split into a and b;
    - the merge variations are dropped;
    - the testid shapes for the LED and the pairing code are decided (DD6);
    - the connector token's masked round-trip is pinned in 07a, tiered high;
    - DD3's pins include `test_store_static.py`;
    - `clearable`'s return shape is specified;
    - budgets are measured in a full `--parallel 3` netns and WebKit run, and each leg lists the lanes it runs.
  - **Low findings:** `.admin-loading` dropped from DD10; the `LIBRARY_GROUPS` hoist; the DD8-1 and DD8-4 sequences restated; the hoisting-trap note corrected; the prerequisite branch unchecked; the mission's Flight 1 key-value text corrected; disclosure variants; 0088 on summaries; dynamic class prefixes in the selector report; frozen capture text; a `destroy` frame check.
  - **Flight Director answers to the Architect's questions:**
    - 0192 does not rename the agent editor's Knowledge tab; that becomes a HAT question;
    - the × clear also clears the results;
    - actions stay inside `<summary>`, as an accepted pattern;
    - the LED keeps its testid on a status LED-only variant;
    - the danger-zone labels keep their title case, matching the other editors.
- 2026-10-22: Architect review, cycle 2 (the last allowed): **approve with changes**, no high findings. It confirmed every cycle-1 resolution against the code, and every change was incorporated with no third cycle:
  - **the connector header** keeps its visible status text, as a `status` line with `ledTestid`, so both testids stay and there is no visible change. This is the Flight Director's call, keeping today's look; the cycle-1 "LED-only" text was stale and is gone;
  - **lanes:** `routing` and `shared` are added to legs 05a, 05b, 06a, 07a and 07b, and `agent-tabs`, `settings` and `mcp` to the chip fix;
  - **computed-style checks** run under an area ancestor, so they can fail first;
  - **the poll-driven status lines** take `live:'off'`, `led:false` where there is none today, and are set only on a change;
  - **the host clears** become `replaceChildren()` on an identity change, after `destroy`;
  - **the pairing code:** `copyField` `buttonLabel`, and both test changes named;
  - **the create form** keeps `kb-create-error` as its one error surface;
  - **`clearable` became its own factory,** `App.ui.clearableInput` with `{el, input, clear, setValue, destroy}`, so `textInput`'s return type never depends on an option;
  - **pin retargets** are per leg;
  - **the disclosure** owns `ui-disclosure-*` and never reuses `mcp-tool-*`, and the DD10 `.kv-remove-row-btn` note is corrected;
  - **the automatic doctor probe** handles a non-OK response;
  - **the channel map's dirty state** compares raw rows;
  - **leg 03c** (the chip cascade) is split from 03b;
  - **`library` lane headroom** is reported at each surface leg;
  - **the capture folder** sits beside the data directory, and the CI comment is updated.
- Planning complete. The flight is `ready` for execution. The operator asked to plan and implement through to the HAT, so execution starts with `/mission-control:agentic-workflow`.
- 2026-10-22: **Execution started.**
  - Branch `flight/03-knowledge-and-connectors-on-the-library` was created from `main` at `08562ec`, and the flight set to `in-flight`.
  - The crew file `leg-execution.md` is loaded: Developer Sonnet; Reviewer Sonnet for security-sensitive diffs, otherwise Haiku. This flight's Reviewer is **Sonnet**, because leg 07a carries the connector token's masked round-trip. An Accessibility Reviewer (Sonnet) runs at the flight review, since the flight changes user-facing UI.
- **Leg 01 tiered high.** The lane split changes a shared interface with existing consumers: CI's `--parallel 1` over the canonical lanes, `tests/test_run_tests_lanes.py`, CLAUDE.md, and the `THE_ONE_REQUIRE_WEBKIT=1` convention. Design review: one Sonnet Developer.
- **Leg 01, design review cycle 1** (Sonnet): approve with changes. Its three high findings were all false premises in the leg:
  - not every tab has `destroy`: General and Rules and notes do not, so they become an explicit allow-list;
  - the shells `studio.js`/`chat.js` load after their modules, so the order pin is relative, `.js` only, with no adjacency;
  - the real `mountSlot` API is `mount(destroyFn, data)`, a token, `isCurrent`/`release`/`current`/`destroy`.

  The medium findings were also applied: the static `state` parse with its 21 keys and a written-key grep; the hard-coded spots in the lane test, CLAUDE.md and CI; the capture instance env for the stub endpoint. The corrections were factual, with no design change, so there was no second cycle. Leg 01 is `ready`.
- [L01 checkpoint] lane split done (run-tests.sh, test_run_tests_lanes.py, browser.yml, agents.md); CLAUDE.md + budgets pending the parallel run.
- [L01 checkpoint] squawk 0233 test rewritten and passing (3 negative tests); squawk docs pending.
- **Leg 02 tiered high** (a restructure; the flight's divert criterion is that it must stay behaviour-free).
  - **Design review cycle 1** (Sonnet): approve with changes. It added the dependency on leg 01 (0233), the composition order with lazy ctx wrappers, a deterministic DOM dump from a pre-edit worktree (four states, including after a poll update and with the panels open), and the exact pin and `agents.md` targets.
  - The changes refine the method without changing the design, so there was no second cycle. Leg 02 is `ready` and waits for leg 01 to land.
- **Leg 03a tiered high** (a new shared factory, plus a consumer on the agent-tabs surface). Its design review is running.
- [L01 checkpoint] squawk 0235 done (agents.md subsection + tests/test_studio_editor_contracts_static.py, negative trials failed as intended and reverted); 0233 corrective written.
- [L01 checkpoint] scripts/unused_selectors.py + smoke test done.
- **Leg 03a, design review cycle 1** (Sonnet): approve with changes, with two high findings: the summary's accessible name, and the confirm title. **Flight Director calls:**
  - **the summary is named through `aria-labelledby`** (the text plus a new `meta` option for chips), so action buttons keep their own names. This is a small option addition, the cleanest reading of DD4's "actions inside summary";
  - **`summaryText` always carries `data-confirm-title`,** and `setSummary` is a no-op while armed;
  - **the plain variant** refuses `meta`, `actions` and the chevron, and carries no margin.

  The rest is method detail. There was no second cycle, and leg 03a is `ready`.
- **Leg 03b tiered high** (several shared factories: `editorShell`, `status`, `chip`, `copyField`, plus a new factory). Its design review is next.
- [L01 checkpoint] capture surfaces written (11 new); trial run next.
- **Leg 03b, design review cycle 1** (Sonnet): approve with changes. Two high findings: the copy feedback always reads "Copied", and the warning chip pair was unaudited. **Flight Director calls:**
  - **`chip--warning` mirrors `chip--danger`:** the gated soft fill, border and text. A small visible change on the standalone badge when it migrates, so a ledger row for the HAT;
  - `ledTestid` is ignored when `led:false`;
  - `errorRole` is top-level and `'alert'` only;
  - Escape clears with `preventDefault`;
  - the menu needs no change, and its differences are listed for 06b.

  Leg 03b is `ready`, with no second cycle.
- **Leg 03c tiered low:** an additive marker class plus narrowed area selectors, test-first with a falsified reproduction. The flight review covers it. No design review.
- **Leg 04 tiered high** (a new shared factory that Flight 5 extends). Its design review is running.
- **Leg 04, design review cycle 1** (Sonnet): approve with changes. **Flight Director calls:**
  - **the connector tests' `.channel-map-*` class selectors move to new input testids in 07b.** There is no `inputClass` option: library controls are styled and selected by owned classes and testids only;
  - **the Flight 5 extension is reserved, not built:** a column `type` that is text-only for now through one internal cell builder, Node labels, preserved non-column row keys, and `rowDataset`;
  - **the remove button** is a ghost icon button whose `btn-icon` size is overridden, with the size pinned.

  Leg 04 is `ready`.
- [L01 checkpoint] before set taken: $HOME/.cache/the-one-ui-capture/m31-f3-before/ , 33 surfaces x 2 themes = 66 PNGs (11 new Library surfaces), 4 pre-existing skips, 0 failed, sha 332496d (tree dirty only in missions/ artifacts and this leg's files; static/ untouched).
- **Leg 07a tiered high** (security: the connector token's masked round-trip; glue lifecycle). Its design review is running.
- **Leg 07b tiered high** (the first consumer of a new shared factory, plus DD8-1 data loss). It is reviewed after 07a's review, so its design builds on 07a's corrections.
- **Leg 08 tiered low** (single-surface, an established pattern, three small items with static or announcer pins). No design review; it is `ready`.
- **Legs 05a, 05b, 06a and 06b are designed after leg 02 lands,** so their citations match the split knowledge modules rather than the 1493-line file.
- **Leg 07a, design review cycle 1** (Sonnet): approve with changes, with three high findings, all applied as binding amendments in the leg:
  - the post-Save ordering: re-mask, then snapshot from the controls, so no plaintext is held;
  - on create success the shell stays busy until the remount, and the glue's catch un-busies it;
  - Cancel restores from the last saved record, including the old channel-map DOM.

  The medium findings were applied too: dirty wiring through control callbacks; synchronous focus on Cancel; `isCurrent` gates on every late write; a glue identity key compared inside the `then`; the Diagnostics ownership in 07a; the `test_store_static` ordering; stronger token-leak tests with a 12-character token and attribute scans. **Flight Director calls:** a same-key re-render keeps the editor and does not refresh its dropdown lists (documented); Diagnostics is 07a's. There was no second cycle, because the design is unchanged and the amendments are precise. Leg 07a is `ready`.
- **Leg 07b, design review cycle 1** (Sonnet): approve with changes, with three high findings, all applied as binding amendments:
  - the pairing result becomes a plain container holding a status line and the `copyField` (no `copyField` inside a `<p>` live region);
  - the copy button's aria-label assertion changes;
  - the `test_store_static` delete pin is handled.

  The medium findings were applied too: the kv `onChange` and Save/Cancel ordering; DD8-1 failures taken against the post-07a tip with an exact sequence and a Cancel test; the single-DELETE guard on the danger zone; the behavior-spec amendment made mandatory. **Flight Director calls:** `.connector-pairing-expiry` stays as area layout; empty and duplicate channel rows keep today's behaviour (no `setError`). Leg 07b is `ready`.
- [L02 checkpoint] leg 02 started: before DOM dumps from a HEAD worktree next, then the split.
- [L02 checkpoint] before DOM dumps taken from a HEAD worktree (7 dumps: create, detail, updated, chunks, source, dirty, cancel), deterministic across two runs; split next.
- [L02 checkpoint] 7 knowledge modules extracted (shared 226, create 147, inspect 122, status 124, search 89, folders 634, detail 312 lines); knowledge-section.js deleted; index.html updated; DOM compare next.
- [L02 checkpoint] DOM-dump comparison: all 7 dumps (create, detail, updated, chunks, source, dirty, cancel) byte-identical before vs after. Pin retargets next.
- [L02 checkpoint] pins retargeted (store_static, ownership allowance 62=62 rows by key, inventory docs, agents.md incl. new Knowledge modules paragraph, studio.css comments, test docstring); static unit guards pass (351). Full gate started.
- **Legs 05a and 05b, design review cycle 1** (Sonnet): both approve with changes, applied as binding amendments with the citations re-targeted to the split modules. Leg 05a was tiered high (mount, state and glue lifecycle); 05b high (a shared-factory consumer and DD8-5).
  - **High findings:**
    - mount-once would leave the poll dead after a cross-area return, so `deactivate` now calls `knowledgeGlue.reset()`;
    - the glue key lifecycle is now fully specified, with one slot in the glue;
    - a test that pins the Save remount is inverted, and listed as a semantic change;
    - a `status` line has no state colour, so **leg 03b gains `textTone`** (amended before 03b runs);
    - the search guard's edge details are specified;
    - the delete failure needed an error the user can see.
  - **Flight Director calls:**
    - **flight DD6 is amended:** a Delete failure goes to the danger zone's own alert notice, in the knowledge-base editor and in the connector (07b updated); the folder delete keeps the header error;
    - the inputs are disabled while a Save is busy;
    - the dead "Loading status…" state is removed;
    - re-index failures stay silent (no behaviour change);
    - the Search button keeps its own row.

  Legs 05a and 05b are `ready`.
- **Legs 06a and 06b, design review cycle 1** (Sonnet): both approve with changes, applied as binding amendments with citations re-targeted. Both legs were tiered high (the poll and focus invariants; the 0088 invariant; a shared-factory consumer).
  - **High findings:**
    - `appendChild` of an attached node blurs focus, so today's `renderFolders` steals focus on **every** status tick. A reference-based reconcile is now required, with tests (a1)-(a3);
    - `kb-folder-add-error` needs a field error testid, so **03b gains `field.errorTestid` and `section.descriptionTestid`**;
    - the inspect panels rebuild their heading on every state, so they now keep one stable `h3` heading.
  - **Flight Director calls:**
    - the folder-path weight and ellipsis, and the summary focus ring, become ledger rows rather than consumer CSS on library internals;
    - the menu sits in an area-owned slot span;
    - poll tests use `page.clock`, to protect the `library` lane;
    - focus goes to the Add-folder input after a folder delete.

  Legs 06a and 06b are `ready`. **Every autonomous leg is now designed, reviewed and `ready`** (09 needs no review: it is tiered low and adds no library change, with a re-tier trigger).

- **Leg 09 landed (FD acceptance, 2026-10-23).** Full `make gate` (netns and WebKit) exited 0: unit 6736 passed, 14 skipped; browser `rc=0`, 1235 s.
  - `library` read 1.32x its budget, so a `knowledge` lane was split out. The FD accepts the narrower `knowledge_pat` (the inventory file only): the glob would also have taken `test_flow_studio_knowledge_attach` out of `agents`.
  - The 12-lane re-run gave `rc=0`, 1250 s. It was re-budgeted per the rule.
  - The after captures map wholly to ledger rows. The 05a header button inset becomes a HAT item.
  - `scripts/ui_capture.py` stepping outside the leg's diff scope (a stale `.kb-folder-path` selector) is accepted as a tool fix.
  - The Developer's mistaken `git stash`/pop was checked by the FD: the stash list is empty and the tree is intact (92 entries).
- **Flight review (Phase 2d, cycle 1).** Two reviewers run in parallel over every uncommitted change relative to `08562ec`:
  - a **Reviewer** on **Sonnet**, because the diff touches a security-sensitive surface (the connector token's masked round-trip and `secretInput` re-mask, DD5);
  - an **Accessibility Reviewer** on **Sonnet**, because the flight is UI-heavy.
  
  The FD asked the Reviewer to assess three items:
  - 07b's hand-copied muted rule on `.connector-setup-steps-doc-ref`;
  - 03c's ownership-allowance bump of +12 (accepted at the time);
  - the toggle tests' `label.ui-toggle-label:has(...)` locators.

- **Flight review cycle 1 results.** Both reviewers signalled `[HANDOFF:confirmed]`, with no blocking issues. The Reviewer's guard tests passed (356).
  - **The Reviewer's verdicts:**
    - (a) The 07b muted rule is fine: it is built from tokens, not a copied library class. Its comment is stale.
    - (b) The 03c +12 bump is fine but is not repaid inside this flight. The repayment is deferred to Flights 4 and 5, which retire the string-built chip lists; the FD accepted that earlier.
    - (c) The toggle locators should change eventually. This is squawk **0240**.
  - **The FD's call:** fix the straightforward non-blocking items in one fix pass, followed by a scoped re-review:
    - the stale `studio.css` comment;
    - the Run doctor race, with no sequence token and no busy state;
    - the `onSaveSuccess` ordering ahead of the token re-mask (DD5 hardening);
    - the a11y finding on silent search results (SC 4.1.3).
  - **Deferred as squawks:** **0238** (the key-value table's error is not announced; no consumer calls `setError` yet) and **0239** (inspect-panel content arrival is not announced; focus is already on the heading).
  - **Accepted as is:** the inspect-panel errors carry both `live: polite` and `role: alert` (redundant but harmless). The armed disclosure summary is not colour-only, because its text swaps.

- **Flight review cycle 2** (Sonnet, a scoped re-review of the fix pass): `[HANDOFF:confirmed]`, with no issues. Guards: 329 passed. The review loop closes after two cycles. At the commit, the FD:
  - moves legs 01-09 to `completed`;
  - ticks the flight's leg list and checkpoints, apart from the HAT;
  - signs off squawks 0100, 0191, 0192, 0233 and 0235;
  - writes `legs/10-flight-hat.md` (`ready`) from the completed ledger, DD7 and DD8. Step 10 now includes the doctor button's busy state from the fix pass.

- **Committed and the HAT opened (2026-10-23).**
  - The flight commit is `330f406`, pushed, with draft PR #303.
  - The HAT dev instance:
    - port 8496, PID 2604830;
    - scratch data dir `~/the-one-m31f3-hat/data`, credential minted with `rotate-api-credential`;
    - started from the scratch cwd;
    - `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`.
  - Seeded with:
    - the Mock provider;
    - Agent A, attached;
    - "HAT notes": the folders `files/notes` (3 files) and a long nested runbooks path (10 files), plus a standalone `loose-note.txt`. 14 items indexed, indexer idle;
    - "HAT stub connector", disabled, default agent Agent A, channel map general and support.
  - Leg 10 is `in-flight`.

### Leg 03a: disclosure (in progress -> landed, awaiting review)

- `App.ui.disclosure` in `js/ui/disclosure.js` (loaded after `button.js`); CSS section `.ui-disclosure*` in `components.css`; catalogue row; `.advanced-collapsible` and `.advanced-caption` deleted; stale references updated (self-configuration tab comment, `studio.css` comment, testid registry, `agents.md`, and the dead "Advanced collapsible" line in the `test_flow_agent_tabs.py` docstring). `git grep -E 'advanced-(collapsible|caption)' -- ':!missions'` is empty.
- `self-config-history.js` builds its log through the plain disclosure (testids kept; "History (N)" via `setSummary`).
- `tests/browser/test_ui_disclosure_contract.py`: 26 tests (Chromium + WebKit, no fixed sleeps on assertions that expect events). Covers required variant, toggles by click/Enter/Space, `onFirstOpen` once, initial open, action button and real-pointer svg click not toggling, accessible names, confirm on the summary and `setSummary` while armed, body rebuild, destroy, bordered and plain parity in both themes, armed danger colours in both themes.
- Falsified once: removing `.ui-disclosure-actions svg { pointer-events: none }` fails the svg test in both engines; restored.

### Leg 03b: control options (in progress -> landed, awaiting review)

- Started. Options added to `feedback.js` (chip `dataset`/`warning`; status `ledTestid`/`textTone`), `editor.js` (`save.enabledWhenClean`, `errorRole`, `section.descriptionTestid`), `copy.js` (`buttonLabel`), `field.js` (`errorTestid`, new `App.ui.clearableInput`), `icons.js` (`more`, 3-circle lucide ellipsis), CSS in `components.css` (`.chip--warning`, `.ui-status--tone`, `.ui-clearable*`). No `index.html` change (the factory lives in `field.js`).
- Contract tests added to the existing feedback, editor, copy, icon and secret-input (field) files, plus new `test_ui_clearable_input_contract.py` (contracts-controls). Contrast guards added to `test_design_tokens_a11y.py` (`.chip--warning` pair; `.ui-status--tone` uses the gated status text tokens, gated on bg and surface by `test_status_text_passes_body_aa`).
- Edge cases covered: `setBusy(true)`, `setDirty(false)`, `setBusy(false)` ends with Save enabled; Escape during composition does not clear. Modal Escape order (clearable input inside a modal) was not exercised here: the factory calls `stopPropagation` on the input's own keydown, so a bubble-phase or capture-on-dialog handler ordering is for the consumer leg (06b/07) to confirm.
- **Menu gap list for leg 06b** (no `menu.js` change made): `App.ui.menu` closes on `pointerdown`, not a capture `click`; the `kb-item-menu*` classes and their `studio.css` rules go; `onSelect` runs after focus has returned to the trigger, so the consumer moves focus to the opened panel itself; no portal and no edge flipping, so a popup inside the scrolling "Other items" panel may clip (06b checks); the catalogue row "KB item menu" flips in 06b. The trigger glyph gap is closed by the new `more` icon.
- Verification (all with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, run after the last code change): `contracts-controls` 578 passed, 4 skipped, 222s; `contracts-overlay` 483 passed, 1 skipped, 180s; `providers` 129 passed, 313s; `agent-tabs` 115 passed, 348s; `make test-unit` 6732 passed, 12 skipped, 340s. Static guards (`test_ui_guards`, `test_ui_ownership`, `test_ui_control_inventory`, `test_token_definitions`, `test_design_tokens_a11y`, `test_run_tests_lanes`) pass; ruff check and format clean. Sink and ownership allowances did not grow.
- Leg 03b landed, awaiting review.

### Leg 03c: chip cascade (in progress -> landed, awaiting review)

- Started. Test-first: `test_ui_chip_list_contract.py` gains `test_library_chip_list_keeps_its_own_look_under_an_area` (`area-studio`/`area-admin` x light/dark x both engines) and `test_string_built_chip_list_keeps_the_area_look`.
- **Failing before the fix** (8 failed, 8 passed: every library case failed, every legacy case passed), for example light theme: `assert 'rgba(109, 40, 217, 0.08)' == 'rgb(244, 244, 245)'` (locked chip fill is the area's accent-translucent, not `--surface-elevated`); dark: `'rgba(167, 139, 250, 0.1)' == 'rgb(28, 29, 34)'`.
- Fix: `chip-list.js` adds `ui-chip-list` on the root and `ui-chip-list-input` on the input (the old classes stay: tests and the shared helpers read them); `admin.css` area chip rules (root, `:focus-within`, `.chip`, `.chip-remove`, `:hover`, input) narrowed with `:not(.ui-chip-list)` / `:not(.ui-chip-list-input)`, no declaration changes. After: 44/44 in the chip-list contract file. Note the library remove button is `.ui-chip-remove`, so the area `.chip-remove` rule never matched it; the remove assertion passed before and after.
- `.tools-editor-field .chip-list-editor` (max-width) and `.field-error-highlight .chip-list-editor` rules left alone: a library chip list is only mounted by the agent tool-override panel (`.tool-row-overrides`), never inside `.tools-editor-field`.
- **Allowance raised, with reason:** `css/admin.css` `ui-chip-list` 0 -> 10 and `ui-chip-list-input` 0 -> 2. The narrowing necessarily names the new owned class in `admin.css` (the leg expected no change; the two new rows are inherent to the `:not()` approach). The existing `chip-list-editor: 12`, `chip-list-input: 2`, `chip: 2` rows did not change.
- Real-surface assertions added to existing tests: agent Tools tab locked chips (`test_flow_studio_tools_overrides.py`: fill == `--surface-elevated`, opacity 0.7), MCP editor chip (`test_flow_studio_mcp_editor.py`: accent-translucent fill, accent remove), Settings tools editor list (`test_flow_chiplist_label_resolver.py`, shared lane: no marker, min-height 40px, max-width 320px, padding 6px). Existing DOM-shape assertions in the contract file updated for the new classes. Catalogue row updated.
- `make test-unit`: 6732 passed, 12 skipped, 383s. Static guards, ruff check and format clean.

- Lanes (all `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, after the last code change): `contracts-controls` 594 passed, 4 skipped, 203s; `contracts-overlay` 483 passed, 1 skipped, 171s; `agent-tabs` 115 passed, 270s; `settings` 107 passed, 281s; `mcp` 110 passed, 379s. The edited shared-lane label-resolver file was run alone (2 passed).
- Leg 03c landed, awaiting review.
- **Leg 03c, a Flight Director call on the allowance bump.**
  - The bump: `css/admin.css` `ui-chip-list` +10 and `ui-chip-list-input` +2 (the `:not()` narrowing must name the library marker). It is accepted as an expected, reasoned bump, the precedent being Flight 2 DD3's chipList bump.
  - The rows disappear when Flights 4 (Settings tools editor) and 5 (MCP editor) migrate the string-built chip lists and delete those `admin.css` rules.
  - The alternative, moving the area rules into `@layer components`, would make the cascade depend on source order: more fragile, and a larger change.
  - The flight review sees this note.
- **The `agent-tabs` lane** ran 348 s (03b) and 270 s (03c) against a 300 s budget, depending on host load. It is re-measured in leg 09's full gate.

### Leg 04: key-value table (in progress -> landed, awaiting review)

- Started. `App.ui.keyValueTable` in `js/ui/key-value-table.js` (after `chip-list.js` in `index.html`), CSS `.ui-kv*` in `components.css`, catalogue row, `tests/browser/test_ui_key_value_table_contract.py` (contracts-controls, 30 tests across both engines).
- Design notes: delegated `input`/`click` listeners on the wrapper (one pair, removed by `destroy`); keyed rows with internal ids, remove splices by key and re-numbers `data-row-idx`, input names and remove names in place (surviving `<tr>` nodes kept, pinned by a node-identity test); one internal `buildCell` switch for Flight 5's `sensitive` type; remove button is the library ghost icon-only button with `.ui-kv .ui-kv-remove` overriding `btn-icon` (about 24px, transparent, 16px svg; size, padding and rest/hover colours pinned against a legacy `mcp-kv-table` fixture in both themes). The hover-colour parity test disables transitions on both buttons (the colour animates, so an unsettled sample differed).
- Contract tests: 30 across both engines (validation, extra keys, Node label, names and roles, custom `removeLabel`/`rowDataset`, empty head, keyed survive-add-remove, onChange types, focus rules, svg click, setValues focus, setError following the row, destroy, look and size parity, hover).
- Verification (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, after the last code change; the two lanes ran concurrently with `make test-unit`, so their wall times are inflated): `contracts-controls` 624 passed, 4 skipped, 331s (budget 270); `contracts-overlay` 483 passed, 1 skipped, 303s; `make test-unit` 6735 passed, 12 skipped, 467s. Static guards (`test_ui_guards`, `test_ui_ownership`, `test_ui_control_inventory`, `test_token_definitions`, `test_design_tokens_a11y`, `test_run_tests_lanes`, `test_index_asset_cache_busting`) pass; ruff check and format clean. No allowance changed. The `contracts-controls` budget needs a re-measure on a quiet host (leg 09).
- Leg 04 landed, awaiting review.

### Leg 05a: knowledge-frame (landed, awaiting review)

- Started. Create form and detail frame rebuilt on `editorShell`/`field`/`section`/`status`; glue moved to one `mountSlot` keyed `create`/`kb:{id}`/null; Save patches in place.
- **Files.** `knowledge-create.js` (editorShell + fields + `kb-create-error` status, `fetchJson`, busy/`alive`, `destroy`), `knowledge-detail.js` (editorShell, fields in a title-less `section`, value model `readValues`/`snapshot`/`stored`, in-place Save and Cancel, inputs disabled while busy, handle `{updateStatus, updateItems, destroy}`, `alive` gates on refreshes/delete), `knowledge-glue.js` (one `mountSlot`, `handleKey`, `teardown()`, same-key render is a no-op beyond `syncLibrarySelection`, `isCurrent(token)` replaces `kbGen` and the `_activeSection/_selectedKbId` stale-then checks, loading and failure `status` lines via `replaceChildren()`, `App.focusAfter.flush()` removed, `onSaveSuccess` only reloads the list), `studio.js` (`deactivate` calls `knowledgeGlue.reset()` through `self._resetKnowledge`), `-status`/`-search`/`-inspect`/`-folders` return objects with `destroy` (no-ops) and `status`/`search` gate late writes on `ctx.isLive()`. `knowledge-shared.js` dead helpers `breadcrumb`, `unsaved`, `showUnsaved` deleted (`input`/`textarea`/`fieldGroup` stay: folders and search use them).
- **Semantic test changes (listed as such).** `test_flow_studio_library_list.py::test_kb_breadcrumb_survives_a_save_remount_and_the_poll_keeps_running` INVERTED and renamed `..._survives_a_save_in_place_and_the_poll_keeps_running` (the breadcrumb mark now survives a Save; the poll check stays). Stale comments updated there ("Save re-mounts") and in `test_router_items.py` ("placeholder" -> "status line"). `test_store_static.py`: the create anchor retargeted to `App.api.fetchJson('/api/knowledge-bases', {` (order unchanged: request, invalidate, callback). No other existing test changed.
- **New tests** (`test_flow_studio_knowledge_inventory.py`, library lane): (a)+(b) Save patches in place (header node marker, folder panel node marker and open state, search query and results, zero `/items` requests, title, subtitle and Library row follow); (c)+(d) type-and-revert is clean, Cancel restores the last SAVED record (also the trimmed name written back); (e) Create AND Cancel disabled while the POST is held, one POST, one knowledge base; (f) leaving for the Library root while the PUT is held: no editor, route stays at the root, nothing written after the PUT lands; (g) inputs disabled while Save is in flight, focus on the title after Save, header error and focus on Save after a failed Save; amendment 1: Library -> Chats -> Library is a fresh mount and `/status` requests resume (and keep running). **Falsified once** (then restored): remounting after Save fails (a); dropping `setBusy` from Create fails (e) (`Locator expected to be disabled`).
- **Pins.** `HTML_SINK_ALLOWANCE` `knowledge-glue.js` row removed (3 -> 0); `git grep innerHTML -- knowledge-*.js` empty. Ownership allowance only shrank: 22 rows touched (create and detail frame classes to 0, `editor-section` 2 -> 1 in detail, three `editor-breadcrumb*`/`editor-unsaved` rows in shared removed); nothing added. Registry: `cancel-knowledge-btn`, `save-knowledge-btn`, `kb-create-cancel-btn`, `kb-create-submit-btn` moved from the manual-exception table to the literal table. `agents.md` gained "Knowledge frame on the library (M31 F3 L05a)".
- **Recorded edges.** (12) If `open()` bails after a successful Create (the user moved, or a guard is deciding) the form stays busy, as before. A Save whose mount was destroyed mid-flight still invalidates `knowledge-bases` and `agents` but does not call `reloadLibrary` (the same gate as before 05a), so the Library row can show the old name until the next list load; recorded, not changed.
- **Verification** (all `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, after the last code change; the first three lanes ran concurrently): `library` 56 passed, 284 s (budget 300); `mcp` 110 passed, 351 s (budget 450); `routing` 184 passed, 508 s (budget 600); `shared` 257 passed, 306 s alone (budget 300); `make test-unit` 6733 passed, 14 skipped, 298 s. Static guards (ui_guards, ui_ownership, store_static, token definitions, a11y, inventory, cache busting) pass; ruff check and format clean.
- Leg 05a landed, awaiting review.
- **Leg 05a, a Flight Director note.** The Developer wrote the new tests after the implementation, not before, but falsified two of them (a remount after Save fails (a); dropping `setBusy` fails (e)). That is accepted as equivalent evidence for this leg, whose tests pin new behaviour rather than an old defect.
  - Later prompts insist on failing-first for defect tests.
  - The `shared` lane ran 306 s against 300; it is re-measured in leg 09.

### Leg 05b: knowledge-status-search-danger (landed, awaiting review)

- Started. Status, Search and the Danger zone rebuilt on `chip`/`status`/`button`/`section`/`clearableInput`/`field`/`emptyState`/`dangerZone` per the binding amendments.
- **Failing-first (recorded before the fix).** The new tests were written and run against the 05a code: (c) `test_a_late_older_search_response_is_dropped` FAILED (the held first response overwrote the second: results read `/x/first.txt ... FIRST` instead of `SECOND`); (d) `test_a_failed_delete_shows_the_danger_zone_notice_and_reverts` FAILED (`kb-delete-error` not found; the failure was silent); (e) `test_a_double_confirm_sends_one_delete` FAILED (4 DELETE requests for one confirm plus three further clicks). (a)/(b) (no clear control), the in-flight-clear test and (f) (the summary was rebuilt each tick) failed too. After the fix all pass.
- **Files.** `knowledge-status.js` (chips and two status lines built once, `update` patches changed text only, section description is the scope hint, library buttons, `isLive`-gated re-index, failures silent), `knowledge-search.js` (`clearableInput`+`field`, generation token bumped in `runSearch` before the empty return, on clear and in `destroy`; `.then` and `.catch` both gated), `knowledge-detail.js` (`dangerZone` with notice `kb-delete-error`, `deleting` flag + `setDisabled`, `App.api.fetchJson`, writes gated by `alive`; `App.confirmDelete` call gone), `studio.css` (dead `.kb-chunk-count`/`.kb-indexer-state`/`.kb-reindex-hint` rules removed).
- **Pins.** Ownership allowance only shrank (all rows for `knowledge-detail.js`, `knowledge-search.js`, `knowledge-status.js` removed, including `api:App.confirmDelete(`); `test_store_static` delete row unchanged and green (DELETE -> invalidations -> `onDeleteSuccess`). Registry: new `kb-search-clear-btn`, `kb-delete-error`; `kb-reindex-*` and `kb-search-btn` moved from the manual table to the literal table. `tests/behavior/kb-studio-round-trip.md` steps 7 and 17-18 still describe the UI; unchanged.
- **New tests** (`test_flow_studio_knowledge_inventory.py`): (a)/(b) clear by x and by Escape, (c) late older search dropped, clear during an in-flight search dropped, (d) failed DELETE notice and revert, (e) one DELETE, (f) no mutation across two real poll ticks.
- **Verification** (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, after the last code change; library, mcp and routing ran concurrently): `library` 63 passed, 298 s (budget 300); `mcp` 110 passed, 325 s (450); `routing` 184 passed, 477 s (600); `shared` 257 passed, 253 s alone (300); `make test-unit` 6735 passed, 12 skipped, 305 s. Static guards green. Squawk 0100 is `in-progress` with Corrective Action and Verification written.
- Leg 05b landed, awaiting review.


### Leg 06a: knowledge-folder-panels (landed, awaiting review)

- Started. Tests written first, run against the 05b code, then the fix.
- **Failing first (recorded before the fix, 7 of 7 new tests red).** (a1) `test_an_items_refresh_keeps_a_focused_menu_trigger` FAILED (`Locator expected to be focused ... inactive`: the refresh rebuilt the row). (a3) `test_a_status_tick_keeps_focus_on_a_folder_summary_and_delete_button` FAILED the same way, on the folder `<summary>` (checked with the old `.kb-folder-watch` class locator so the failure was about focus, not the new testid): `renderFolders` re-appended every panel on every tick. (b) `test_a_row_node_survives_a_poll_refresh_that_only_changes_its_status` FAILED (`None == 'same-node'`: the row node was replaced). (a2) shared a test with (a1) before the split, so it was not reached; after the fix it was split into its own test and **falsified** by reinstating `closeAnyOpenItemMenu()` at the top of `renderAllItems` (it FAILED: the menu was `hidden`), then reverted. (c) `test_a_removed_item_row_disappears_and_its_open_menu_is_released` passed on the old code (the old code removed every row and closed the menu on refresh); it is a regression guard for the keyed rebuild (it counts document `click`/`keydown` listeners through an init-script wrapper: the count returns to the baseline after the removal). (d), (e) and the focus-after-delete test failed on the missing testids/behaviour.
- **Files.** `knowledge-folders.js` rewritten onto the library (Add folder `field`+`textInput`+`button`, the Folders `section` with `descriptionTestid`, bordered `disclosure` panels with `chip` meta and a ghost icon `button` action, `status` danger lines, `emptyState`, the warning `chip`); `syncChildren(parent, nodes, offset)` is the one reconcile (reference-based: remove unwanted children first, insert only where a node is not already in place, never re-append an attached node); file rows keyed by item id per group and patched in place; the L6-D3 header comment rewritten ("never recreate" for 0088, "moving blurs focus" as the second hazard); `buildItemMenu(getItem)` returns `{el, close}`; `destroy()` releases panel controls and row menus. `knowledge-detail.js`: the folders ctx gains `isCurrent` and `setError(text)` (writes the header through `shell.setError`, gated by `alive`). `knowledge-shared.js`: `appendIcon`, `input`, `textarea`, `fieldGroup` and `section` had no user left and are deleted. `studio.css`: `.kb-folder-delete-btn svg`, the three armed rules, `.kb-item-standalone-badge`, the `.kb-folder-error`/`.kb-folder-watch-error`/`.kb-item-error` margin group and the `.kb-folder-path` selector are gone (`unused_selectors.py studio.css`: 0 unused).
- **Pins.** Ownership allowance only shrank: every `knowledge-folders.js` and `knowledge-shared.js` row removed (16 rows) and `css/studio.css` `confirm-delete` 3 -> removed; nothing added. **Residual:** `knowledge-folders.js` has no ownership-allowance row; the old item menu's `kb-item-menu*` classes are not library-owned, so 06b removes them with the menu. `git grep -E 'confirmDelete|showFlash|App.icon\(|innerHTML' knowledge-folders.js` is empty. The 0088 grep (`setSummary`/summary text writes in the folders module) shows only the Other-items `setSummary`. Registry: new `kb-folder-status`, `kb-folder-summary`, `kb-folder-watch` (literal table); `kb-folder-path`, `kb-folder-skip-counts`, `kb-folder-status-error`, `kb-folder-watch-error` moved to the manual-exceptions table (carried through `summaryTextTestid`/a helper argument, invisible to the extractor); `kb-folder-delete-btn` text updated.
- **Library gaps found, recorded.** (1) The registry extractor matches `[a-z]+Testid` only, so `summaryTextTestid` values need a manual-exception row. (2) The `no variable testid` guard forbids passing a testid through a helper argument, so the two danger lines are built at their call sites. (3) `App.ui.confirm`'s lapse timer still fires once on a detached summary (it reverts the node and announces "not confirmed"); harmless, not changed (not this leg's file). (4) Folder-path styling: see the ledger row.
- **Existing tests changed (locator moves only).** `.kb-folder-summary`, `.kb-folder-path`, `.kb-folder-watch` -> the `kb-folder-summary`, `kb-folder-path`, `kb-folder-watch` testids (about 20 lines in `test_flow_studio_knowledge_inventory.py`); the armed-across-poll 0088 test (`test_armed_folder_confirm_survives_items_signature_tick`) passes with only that locator move. The behavior spec `tests/behavior/kb-studio-round-trip.md` names no `.kb-*` classes: no amendment needed.
- **Verification** (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, after the last code change; library, mcp and routing ran concurrently): `library` 71 passed, 323 s (budget 300, 1.3x limit 390: within); `mcp` 110 passed, 329 s (450); `routing` 184 passed, 481 s (600); `shared` 257 passed, 259 s alone (300); `make test-unit` (netns) 6733 passed, 14 skipped, 298 s. The knowledge inventory file alone: 40 passed. Static guards (ui_guards, ui_ownership, token definitions, a11y, store_static, inventory, cache busting, nav helper) 430 passed; ruff check and format clean.
- Leg 06a landed, awaiting review.
- **Leg 06a, a Flight Director note.** Its finding, that a confirm lapsing on a detached armed summary still announces "not confirmed", is logged as **squawk 0237** (routine, deferred: a library behaviour outside this flight's surfaces; fix on `main` or in a later flight).
  - The `library` lane ran 323 s against 300 (1.08×), so leg 09 re-budgets it.

### Leg 06b: knowledge-item-menu-and-inspect (landed, awaiting review)

- **Failing first (before the fix, run against the 06a code).** (a) DD8-7 `test_ctrl_k_with_an_item_menu_open_leaves_the_palette_its_keys` PASSED: it did NOT reproduce (the old capture keydown did not take the palette's ArrowDown or Escape in this setup); kept as a regression pin. (b) DD8-5 `test_a_late_chunks_response_never_paints_over_a_later_item` FAILED (panel title showed item A after B was opened and A released). (c) `test_view_chunks_and_source_leave_focus_on_the_panel_heading` FAILED (heading `inactive`). The existing 06a test `test_a_removed_item_row_disappears_and_its_open_menu_is_released` is the listener-cleanup test (d); it now also tracks `pointerdown` (the library menu's listener), and a duplicate test I wrote first was dropped.
- **Files.** `knowledge-folders.js`: `buildItemMenu`, `openItemMenu`/`closeAnyOpenItemMenu` and the capture listeners are gone; each row builds an `App.ui.menu` inside an area-owned `span.kb-item-menu-slot`; a row's removal calls `menu.destroy()`, a panel's `onToggle(false)` calls `menu.close(false)` on that panel's rows (`closeGroupMenus`). `knowledge-inspect.js`: both panels are `App.ui.section({titleTag: 'h3'})` with one stable heading built once, a content region replaced per state, one `mountSlot` for both panels, `status`/`emptyState` lines, focus to the heading on open. `knowledge-shared.js`: dead `btn` removed (the others were removed in 06a). `studio.css`: `.kb-item-menu*` rules replaced by `.kb-item-menu-slot { margin-left: auto }`. Test move: the section-order assertion excludes `.kb-inspect-panel` (the panels are now `.editor-section`s).
- **Pins.** `knowledge-inspect.js` ownership rows (3) removed; no `knowledge-*.js` row remains in either allowance (the `knowledge-settings-page.js` rows belong to the Settings page, a different flight). Catalogue "KB item menu" row retired, `menu` row lists the consumer; registry notes updated.
- **Results.** Unit: `make test-unit` 6735 passed, 12 skipped (305 s). Lanes under `THE_ONE_TEST_NETNS=1` (3 at once for the first three): library 74 passed 336 s (budget 300 s: 1.12x, under the 390 s report threshold), mcp 110 passed 332 s, routing 184 passed 486 s, shared 257 passed 257 s. Static guards (`test_ui_guards`, token, a11y, inventory, ownership, cache-busting, lanes) pass.


### Leg 07a: connector-frame (landed, awaiting review)

- Started. Failing-first tests (a)-(e) written and run against the 06b code.
- **Failing first (recorded before the fix).** (a) `test_a_double_click_on_create_makes_one_connector` FAILED (2 POSTs for two clicks: `['.../api/connectors', '.../api/connectors']`). (b) `test_b_a_failing_manual_doctor_shows_the_error_not_undefined` FAILED (result read `undefined: undefined`). (c) the probe test FAILED (stuck at "Checking connection…"). (e) `test_e_a_typed_token_replaces_it...` FAILED on the old code: **after an edit Save the typed plaintext stayed in the token field** (`input_value()` was `typed-token-PLAINTEXT-9999`, not the mask), an existing defect that the new Save fixes. (d) (untouched token survives an edit Save) PASSED before the change and pins the contract.
- **Files.** `connector-editor.js` rewritten (editorShell, section, field, textInput/select/textarea/secretInput/toggle, status, button; handle `{destroy, setBusy, setError}`; module `mountSlot`; `readValues`/`buildPayload`/`applyRecord`; Pairing, Channel map and Danger zone left as the old DOM), `connector-glue.js` (handle + `handleKey`, key compared inside the `then`, `epoch`, `.catch` un-busies, `reset`/`_closeConnectorForm` destroy), `studio.css` (`.connector-enabled-row`, `.connector-status-row/-label` removed), tests, `agents.md` ("Connector frame on the library"), registry.
- **Token paths (for audit).** Render: the stored mask (or '' on create) via `secretInput` `value` (a property, no attribute). Dirty: `JSON.stringify(readValues()) !== snapshot`, a transient string; the snapshot holds only the mask (or what was there at mount). Payload: built in the click handler from `readValues()`, serialised to `body`, the object nulled; the body string goes to `fetchJson`; nothing in the `.then` closures references it. After Save: `cfg=config=stored=updated` (masked response), `secret.setValue(mask)` (reveal off), snapshot read back from the controls. Cancel: `applyRecord(stored)` writes the stored mask, reveal off. Reveal: flips only `input.type`. Create: stays busy until the glue remounts from the masked response. Tests (d)/(e) scan every attribute, value and text node.
- **Semantic test changes.** The status-LED test now checks the line's text and `data-state` (LED aria-label gone); `.editor-title` is `h1.editor-title`; five tests that `.uncheck()`ed `[data-field="enabled"]` now click `label.ui-toggle-label:has(...)` (the input is clipped).
- **Known non-changes (amendment 10).** A masked-looking string typed on edit is "preserve"; a stale `default_agent` falls back to the first option. A same-key re-render keeps the editor and does not refresh the agents and types lists (accepted).
- **Pins.** `HTML_SINK_ALLOWANCE`: `connector-glue.js` row removed, `connector-editor.js` 3 -> 1 (the channel map's clear, leg 07b). Ownership allowance only shrank (connector-editor rows, `studio.css` `indicator-led` 2 -> 1). Registry: `cancel-connector-btn`, `connector-doctor-btn`, `save-connector-btn` moved to the literal table; status notes updated. `test_store_static` connector pins unchanged and green.
- **For leg 07b (remaining old DOM in `connector-editor.js`):** Pairing section (`_section`, `_btn`), Channel map (`rowsEl`, `renderRows`, `readChannelRows` is the adapter to replace, `innerHTML` clear), Danger zone (`App.confirmDelete`; its failure writes `shell.setError` as an interim).
- **Verification** (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`; library, mcp, routing ran concurrently): `library` 84 passed, 362 s (budget 300, 1.2x); `mcp` 110 passed, 329 s; `routing` 184 passed, 483 s; `shared` 257 passed, 257 s alone; `make test-unit` (netns) 6733 passed, 14 skipped, 296 s after the final allowance fix (one ownership row for `studio.css` was corrected after that run; the guard files then pass). Static guards, ruff check and format clean. `test_api_secret_mask_roundtrip` passes.
- Leg 07a landed, awaiting review.

### Leg 07b: connector-sections (landed, awaiting review)

- Started. DD8-1 tests written first and run against the post-07a code (`pytest -k "dd8 or delete"`).
- **Failing first (recorded before the fix).** DD8-1 (1) add-row keeps typed values: FAILED. (2) remove-row keeps typed values: FAILED. (3) second Save stores the edited channel (`chan-a2`) and not the stale `chan-a`: FAILED. (4) Cancel restores the rows: PASSED (kept as a pin). DD8-8 role names: FAILED (no accessible names). Double-confirm sends one DELETE: FAILED. Failed DELETE shows `connector-delete-error`: FAILED (testid did not exist). All pass after the fix.
- **Files.** `connector-editor.js` (Pairing, channel map, Danger zone on library controls; micro-helpers `_el`/`_btn`/`_section` deleted), `studio.css` (`.connector-pairing-code-row`/`-code` removed; `.connector-setup-steps-doc-ref` now carries its own muted rule instead of the owned `field-hint` class), tests (`test_studio_connector_editor.py` new DD8-1/DD8-8/delete tests and pairing changes, `test_flow_studio_library_list.py` selectors, `test_store_static.py` delete pin window), registry, catalogue, `agents.md`, `tests/behavior/stub-connector-round-trip.md` step 2 (the code is `connector-pairing-code`'s value; expiry in `connector-pairing-result`).
- **Allowances.** `connector-editor.js` has 0 `HTML_SINK_ALLOWANCE` and 0 `OWNERSHIP_ALLOWANCE` rows; the grep for `App.showFlash|App.confirmDelete|innerHTML` in `connector-*.js` is empty.

- **Verification** (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, after the last code change; library, mcp, routing concurrently): `library` 91 passed, 381 s (budget 300, 1.27x: under the 390 s limit); `mcp` 110 passed, 331 s; `routing` 184 passed, 486 s; `shared` 257 passed, 254 s alone; `make test-unit` (netns) 6733 passed, 14 skipped, 295 s (covers 07a's stale-row fix). Static guards 430 passed; ruff clean.
- Leg 07b landed, awaiting review.

### Leg 08: library-pane-and-labels (landed, awaiting review)

- Started. `LIBRARY_GROUPS` hoisted to `library-pane.js`'s IIFE scope and exposed as `App.studio.libraryGroups()` (a copy per call); `isLibrarySection` derives from `libraryGroupFor`; `studio-route.js`'s bare-section list reads the table at call time (`isLibraryRootSub`, throws if the table is missing). New `tests/test_library_groups_static.py` (3 tests); falsified once by re-adding `sub === 'connectors'` (fails), reverted.
- 0192: `router.js` `LIBRARY_LABELS.knowledge` is "Knowledge bases"; pins updated in `test_router_announce.py:201` and `test_flow_studio_library_list.py` (two). Other label sites checked: the Library list heading, Add menu, start-page card and the `list-and-detail.md` behaviour step already say "Knowledge bases"; the jump-to palette's "Library · Knowledge base" is the singular item kind and is left as is; no behaviour spec reads the announcer text.
- `mcp-glue.js` clear is `replaceChildren()`; its `HTML_SINK_ALLOWANCE` row removed.
- **Verification** (`THE_ONE_TEST_NETNS=1`; library, mcp, routing concurrently): `mcp` 110 passed, 329 s; `library` 91 passed, 380 s; `routing` 184 passed, 484 s; `shared` 257 passed, 257 s alone; `make test-unit` 6738 passed, 12 skipped, 307 s. Static guards (ui_guards, token_definitions, a11y, store_static, ownership, control_inventory) 349 passed.

### Leg 09: library-close (landed, awaiting review)

- **Counts (zero rows, zero sinks).** None of `knowledge-{shared,create,inspect,status,search,folders,detail}.js`, `knowledge-glue.js`, `connector-editor.js`, `connector-glue.js`, `mcp-glue.js` or `library-pane.js` has a row in `HTML_SINK_ALLOWANCE` or `OWNERSHIP_ALLOWANCE` (verified by loading both tables; the only knowledge row left is `areas/admin/knowledge-settings-page.js`, a Settings file for Flight 4).

| File | `HTML_SINK_ALLOWANCE` | `OWNERSHIP_ALLOWANCE` |
|---|---|---|
| `knowledge-*.js` (7 modules) | 0 | 0 |
| `knowledge-glue.js` | 0 | 0 |
| `connector-editor.js` | 0 | 0 |
| `connector-glue.js` | 0 | 0 |
| `mcp-glue.js` | 0 | 0 |
| `library-pane.js` | 0 | 0 |
| **Whole app, start of flight** | 46 sinks | 187 rows / 409 uses |
| **Whole app, now** | 37 sinks (7 files) | 135 rows / 315 uses |

- **Dead CSS** (`scripts/unused_selectors.py css/studio.css css/components.css`). Before (leg 01): `studio.css` 0, `components.css` 6 unused. Now: `studio.css` 0; `components.css` 7. The new one, `.section-title--plain`, lost its last user in leg 06b: its rules and the two comment mentions are deleted (agents.md and the catalogue follow). Of the remaining 6: `.entity-tile-meta`, `.refresh-btn`, `.test-result-warning`, `.u-block`, `.u-flex` are not knowledge, connector or disclosure related (kept, recorded). `.ui-disclosure--plain` is reported but used (the class is built as `'ui-disclosure--' + variant`). Fourteen "dynamic" prefixes (`.badge--*`, `.ui-list-pane-*`, `.ui-menu-align-start`, `.indicator-led--warning`) are runtime-built, kept. After the deletion: `components.css` 6 unused.
- **Single-consumer options (all kept, none removed).** Still one: `button.compactIcon` (MCP Refresh), `groupTile` `master.describedBy` and `master.tristate: false` (`mcps-tab.js`; Tools tab uses the default), `dangerZone.beforeArm` (provider editor), `status.ledTestid` and `copyField.buttonLabel` (connector editor), `disclosure.summaryTextTestid` (knowledge folders), `clearableInput` (knowledge search), `keyValueTable` (connector channel map; a second consumer in Flight 5). Now several: `chip` `warning`/`dataset`, `status.textTone` (8 uses), `editorShell` `save.enabledWhenClean` (5 files), `field.errorTestid`, `section.descriptionTestid` (2), `menu` (2), `disclosure` (3 files). `emptyState` `plain`/`flush`: no third variant, not merged.
- **After captures** (`$HOME/.cache/the-one-ui-capture/m31-f3-after/`, 33 surfaces x 2 themes = 66 PNGs). The first run had 8 failures: `scripts/ui_capture.py` still clicked `.kb-folder-path`, which the disclosure replaced (leg 06a); fixed in the tool (summary testid; mask selectors also match the new testids) and the four surfaces re-run with `--force`. Pixel-diffed against the before set, then viewed. Every difference maps to a ledger row: kb-new header (Cancel/Create sit about 8px in from the right edge: 05a); kb-detail, kb-status, kb-search, kb-danger-armed, kb-chunks, kb-source (taller by 18-45 px: 05b status hint above the counts and search button row, 06a folder description and gap, 06b ghost item menu and panel heading); connector-new and connector-edit (07a toggle beside its label, token eye, status LED lines; 07b pairing code input with Copy pairing code, channel map table with header and trash icons, danger-zone trash icon). Unmapped by ledger but not UI changes (capture residue): the agent Knowledge tab's tool name carries a per-run id (`kb__Capture_knowledge_<id>__search`); the connector pairing code is now an input, so the mask (which sets text) leaves its value showing (`3d86546e`); one-pixel and sub-threshold noise on provider and agent surfaces. library-start has no difference. No unmapped visible difference.
- **Gate.** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`: unit 6736 passed, 14 skipped; browser `PARALLEL_RESULT rc=0 total=1235s lanes=11`, no flake appeared. `library` read 397 s against 300 (1.32x, over the 1.3x rule), so `knowledge` was split out (`knowledge_pat` = `test_flow_studio_knowledge_inventory.py`, 233 s of the lane's 393; the leg's `test_flow_studio_knowledge_*` glob would also have moved `test_flow_studio_knowledge_attach` out of `agents`, so the single file is used). `scripts/run-tests.sh` (12 canonical lanes, budgets), `tests/test_run_tests_lanes.py`, `ci/tasks/browser.yml` comment, CLAUDE.md (table, lane list, alias) and agents.md follow. Re-measured `--parallel 3` (netns, WebKit): `PARALLEL_RESULT rc=0 total=1250s lanes=12`.

| Lane | Budget now | Measured | Old budget |
|---|---|---|---|
| routing | 600 | 526 | 600 |
| agents | 540 | 456 | 540 |
| chats | 450 | 362 | 450 |
| mcp | 450 | 335 | 450 |
| providers | 420 | 311 | 420 |
| shared | 420 | 319 | 300 |
| contracts-controls | 330 | 249 | 270 |
| agent-tabs | 360 | 273 | 300 |
| settings | 360 | 271 | 300 |
| contracts-overlay | 270 | 212 | 240 |
| knowledge | 300 | 229 | new |
| library | 210 | 164 | 300 |

  The only OVER BUDGET flag in the second run was `shared` (319 against the old 300, 1.06x); it was re-budgeted as above (lanes that moved more than 15% since the Flight 2 table). No lane is over 1.3x of its new budget.
- **Docs.** Catalogue: stale rows removed (compact row actions, pull button, pull-model control, studio pill toggle), `.tool-enable-switch` consumers corrected (connector out, MCP editor in), status, chip and clearable-input rows list the knowledge and connector consumers; "not yet defined" control rows: 9 (was 13). The registry needed nothing (no id retired this flight; `tests/test_ui_guards.py` passes). CLAUDE.md: Control library paragraph (Flight 3 controls and counts), Library list paragraph (patch in place), lane table. agents.md: library editor handles (destroy, identity keys), the control-library bullet, lane list. Mission Known Issues: `App.confirmDelete(` 4, `App.showFlash(` 11, `App.icon(` 17, `App.tabs` 2, `App.consentLink` 7 (call sites outside `js/ui/` and comments).
- **Behavior specs.** `stub-connector-round-trip.md` step 2 already amended by leg 07b (pairing code input). `kb-studio-round-trip.md` amended here: the closing breadcrumb link is "Library"; step 6 now names the item menu path (`kb-item-menu-btn`, `kb-item-chunks-btn`, `kb-item-source-btn`). `list-and-detail.md` (steps 10-17: "Knowledge bases" group, `Name is required.`, `lnd-conn` token masking) and `jump-to-palette.md` (step 5 "Library · Knowledge base", step 7 Settings page) read against the landed UI: no change needed.
- **Diff scope.** This leg changed only docs, tests (`test_run_tests_lanes.py`), `scripts/run-tests.sh`, `scripts/ui_capture.py` (capture selectors, a tool), `ci/tasks/browser.yml` (comment), one dead CSS block in `components.css`, the behavior specs and this log. No `js/ui/` file and no library option changed.
- **Verification.** `tests/test_ui_guards.py`, `test_ui_control_inventory.py`, `test_run_tests_lanes.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`, `test_ui_ownership.py`, `test_nav_helper.py` pass; ruff check and format clean.

## Flight review fixes (four non-blocking items)

1. **Stale CSS comment** (`studio.css`, `.connector-setup-steps-doc-ref`): reworded to say the rule carries `--font-size-caption` / `--fg-muted` itself. No test.
2. **Run doctor race** (`connector-editor.js`): `doctorSeq` guards the result line and re-enables the button; the button is disabled while a run is in flight; `headerSeq` is shared by the open-time probe and manual runs so the newest request wins the header line (the probe never writes the result line). Choice: a second manual click cannot fire (disabled), so the race test drives probe-held plus manual run: `test_a_late_auto_probe_cannot_overwrite_a_newer_manual_doctor_on_the_header` (also asserts disabled during the run, enabled after). Failing first: with the header guard removed it failed at the final `data-state` success assertion (the late probe turned the header danger); passes with the fix.
3. **Save-success callback throwing** (`connector-editor.js`): on an edit Save the record is applied and the token re-masked first, then `onSaveSuccess` runs inside try/catch (logged, not shown as a save failure); create still calls it first (it hands off to the remount). No test: by code reading, the callback now runs after `applyRecord`/`setBusy(false)`/`setDirty(false)`, and a throw cannot reach `.catch`'s `setError`. The DD5 masked round-trip tests pass.
4. **Silent search results** (`knowledge-search.js`): the degraded line is `live: 'polite'`; a visually hidden `App.ui.status` (`kb-search-announcer`, `.visually-hidden` added to its root, no library change) announces "N results" / "1 result" / "No results." only when a non-stale response is applied, and is emptied on a new search and on clear. Registry row added. Test: assertions added to `test_detail_view_indexing_poll_reindex_and_search`. Failing first: with the announcer calls removed it failed on the empty text; passes with the fix. No allowance row added.

Verification: guard/token/a11y/ownership/inventory tests 329 passed; ruff clean; `--lane library` 49 passed in 143 s; `--lane knowledge` 43 passed in 216 s. No ledger row (nothing visible changed).

## Completed visible-differences ledger (leg 09)

Each row above is marked: "HAT item" (the operator is asked to look) or "approved by DD" (the flight's design decision already allows it; the HAT sees it in the capture set only).

| Rows | Disposition |
|---|---|
| 01, 02, 03a, 03b, 04 (no visible change) | approved by DD2 / DD3 / DD4 |
| 03c locked chips and invalid chip border | approved by DD7 item 9, DD8-6 |
| 05a header buttons, fields, form error, in-place Save, Cancel while busy, non-JSON errors | approved by DD5, DD6; header button inset (about 8px) is a HAT item |
| 05a loading and failure lines (lost 20px padding) | HAT item |
| 05b Status section (hint above counts), Search (clear x, own-row button, status lines), Danger zone notice | approved by DD6, DD7 item 2, DD7 item 5; the moved scope hint is a HAT item |
| 06a folder panels (path ellipsis instead of break, focus ring, meta chips), standalone warning chip | HAT item (long paths in both themes), chip approved by DD4 |
| 06a folder-delete failure, focus after delete, poll no longer steals focus, meta status lines, empty states | approved by DD6, DD8, DD8-4 |
| 06b item menu trigger and menu behaviour | HAT item (row height, trigger) / approved by DD4 |
| 06b inspect panel heading and focus, loading and error lines | approved by DD8-5, DD6 |
| 06b item menu clipping on the last row | HAT item |
| 07a Enabled switch, token secret input, doctor result, header status, dirty revert, Save/Cancel in place, errors, copy flash | approved by DD7-1, DD7-4, DD7-6, DD7-10, DD5, DD8, DD6 |
| 07b pairing code input, channel map table, danger zone | approved by DD7-7, DD7-8, DD7-5 |
| 08 router announcement "Knowledge bases" | approved by DD7-3 (squawk 0192); the agent editor's Knowledge tab label is a HAT question |

## HAT (leg 10) results

Instance: port 8496, scratch data `~/the-one-m31f3-hat/data`, PID 2604830.

- **Step 1 [fresh]:** pass. The Library groups each show once, and the breadcrumb and title name "Knowledge bases".
- **HAT item 7:** the operator keeps "Knowledge" as the agent editor's tab label. No change.
- **Step 2 [kb-create]:** create passes; HAT item 1 (header inset) approved. Finding: "Name is required." shows on the form-level line under Description. This placement is unchanged from main; DD6 kept the one error line, and the step text wrongly promised a field error. The operator chose option A: the empty-name error moves to the Name field (`kb-create-name-error`, aria-invalid), and server errors stay on `kb-create-error`. This overrides DD6 for this form only.
- **Step 3 [kb-detail]:** HAT item 2 (loading line) accepted. Unsaved state, revert and Save in place pass. Finding: the expanded folder panel and the search results read as clunky:
  - raw ISO `Indexed:` timestamps, the `Indexed:` line larger than the file name, and `Skipped: 0 dirs, 0 entries` at body size;
  - search hits headed by the full absolute path, with a raw score and unclamped chunk text.
  These pre-date the flight. The FD classifies them as look-and-feel fixes on one surface (the knowledge editor), so they ride inline. A Developer was spawned with fixes A, B (folder panel) and C (search results). The fix revises the DD14 note "Knowledge `Indexed:` stays precise": the lines show date and time, with the precise value in a tooltip.
- **Step 4 [kb-status]:** pass. HAT item 3 (the scope hint above the counts) is approved. Re-index (changed) updates in place.
- **Order change:** steps 5-8 (folders, items, poll, search) wait for the fix pass. The walk continues with step 9, then 10-13.
- **Step 9 [kb-danger]:** pass. Arm, then commit; the row drops from the list.
- **Step 10 [connector]:** two findings.
  - (a) **Header status goes stale after Save.** This is a regression from DD5. Before Flight 3, an edit Save remounted the editor, which re-ran the one-shot auto-probe. With patch in place, the header keeps its pre-save verdict. Repro: enable and Save, the header still reads the old state; disable and Save, it still reads "Connected".
  - (b) **Pairing layout:** the "Generate pairing code" button and the code field touch.
  Both are fixes on one surface, the connector editor. A second Developer was spawned for them, scoped away from the knowledge files. Its fix: re-probe the header after an edit Save, clear the stale doctor line, and add a gap at the pairing result.
- **Step 10, remainder:** pass. The switch with Tab and Space, the token re-mask after Save, dirty revert, doctor disabled while running, and the pairing copy all work.
- **Step 13 [agent-tools]:** pass. The locked chips have the library fill. The invalid-chip border was not walked live; it is pinned by the 03c tests.
- **Step 10 fix landed (uncommitted):**
  - `connector-editor.js`: `runHeaderProbe` re-runs after an edit Save, and `resetDoctorResult` clears the doctor line and drops any run in flight.
  - `studio.css`: the pairing result gets a 12px gap above it and an 8px gap between its children.
  - Two new tests, plus a spacing assertion.
  - Library lane: 51 passed, 154 s.
  - Noted: Run doctor's result line has the same no-gap layout. It is left for the operator's call.
- **Step 11 [channel-map]:** pass (column labels, trash per row, typed values kept across add/remove, second Save stores newest, reload confirms).
- **Step 10 re-check:** pass. The header re-probes after each Save, and the pairing gap is in. The operator asked for the same gap under Run doctor's result line; the connector Developer was resumed for it.
- **Step 12 [connector-create]:** pass. A double-click on Create makes one connector, and its danger-zone delete removes it.
- **Main merge requested:** sortie 5 (#302, 11b61b4). It is deferred until the knowledge fix lands, because CLAUDE.md and `agents.md` overlap. Then: commit the HAT fixes, merge, and restart the HAT instance.
- **Knowledge fix landed (uncommitted):** fixes A, B and C.
  - **A:** `kb-create-name-error` on the Name field.
  - **B:** the "Last checked …" meta line; compact file rows reading "Indexed {date}, {time}", with the precise ISO in `title`/`data-indexed-at`; Skipped shown only when non-zero; an `App.time.onChange` repaint.
  - **C:** search hits as a list: basename title, path and score meta line, snippet clamped to 3 lines.
  - **Docs:** CLAUDE.md (the DD14 wording), `agents.md`, the registry, and two behavior specs amended.
  - **Tests:** guards 135 + 325 passed; knowledge lane 43 passed (217 s); mcp lane 110 passed (305 s); routing `-k knowledge` 18 passed.
  - The FD reviewed the scratch captures in `cap1/`: the layout is as specified.
- **Doctor gap landed (uncommitted):** `.doctor-btn + :not([hidden])` gets a 12px margin-top; spacing assertion added; library lane 51 passed (152 s).
- **Committed and merged:** HAT fixes 79457ac; merge of origin/main a1cbcd4 (no conflicts; unit 6773 passed / 14 skipped under netns); pushed. HAT instance restarted on 8496 with the same data and env, new PID 2679954.
- **State fix:** "HAT notes" was missing after the restart, and "HAT scratch" (created 12:07, at step 2) was still there. So step 9 had deleted "HAT notes", not the scratch KB; the delete itself behaved correctly. The FD re-seeded "HAT notes" (id ca81b23fed8c, same folders, 14 items indexed) and re-attached Agent A.
- **Step 2 re-check and step 5 [kb-folders]:** pass. The ellipsis, focus ring, chips, "Last checked" line, compact rows with hover, bad-path error, and the folder delete and its focus all work. The operator approved the new file-row and search formatting.
  - **Finding:** "Other items" showed no chip. The behaviour is correct: the DD-9 standalone chip shows only for an individually registered file that lies inside a registered folder, and the seed's `loose-note.txt` does not. The step text was wrong. The FD registered `runbook-01.md` individually to show the case.
  - **The operator found the "Other items" label unclear.** Context: the UI can only add folders, so this panel holds files registered on their own through the API.
- **Operator direction on "Other items".** FD fix-vs-feature calls:
  - (1) Rename to "Individual files", with a one-line description (an info line rather than a new info-button control, since the library has no popover): **fix**, inline.
  - (2) Self-explanatory chip text: **fix**.
  - (3) A way to remove an individual file (the API route exists; the UI has none): **feature**, so it gets a scoped design review first (a Plan agent was spawned).
  - (4) Status/watch on the panel: per-row status already shows. Folder-level watch likely does not apply to single files; the design review confirms.
  - (5) An "Add file" section in the UI: **feature**, larger. Recommended for deferral to a later flight or sortie; the operator decides.
- **Step 6 [kb-items], partial.** HAT item 5 is approved: the ⋯ trigger and row height. View chunks works. Findings, folded into the same design review:
  - (a) Rows say "indexed" twice: the status word and "Indexed {date}". **Fix.**
  - (b) Individual-file rows show the full absolute path at body size, and the DD-9 chip overflows on its own line. **Fix.**
  - (c) The source and chunks panel heading is the full absolute path at heading size. **Fix.**
  - (d) A header label and a **close** button for the chunks and source panels. **Feature**, small; it goes through the design review.
- **Step 6, remainder:** pass. HAT item 6 is approved: the last-row menu may extend the scroll area. The menu arrows and Escape, and Ctrl K with a menu open, work.
- **Step 7 [kb-poll]:** skipped at the operator's request. DD8-4 (the poll keeps focus and an open menu) stays covered by the knowledge-lane tests.
- **Design review result.** The Plan agent's design is accepted; it is held in the scratchpad as `hat-individual-files-design.md` and summarised here:
  - **Individual files:**
    - "Individual files ({n})", with a hint: "Added one at a time through the API. These files aren't watched for changes; use Re-index all files to pick up edits." The operator's "re-index" alone was wrong: `scope=changed` skips parentless files.
    - No summary chips: watch would always be off, and walk status does not apply.
    - Remove is a trash `App.ui.confirm` button armed on itself, on parentless rows only. Tombstones stop a stale poll from resurrecting a removed row. Focus goes to the next row, else the previous row, else Add-folder.
    - The orphan hold-out amends L6-D2.
  - **Rows:** the status word only when not indexed with a stamp; "Last indexed …" for pending and failed rows.
  - **Individual row:** the basename, plus an ellipsised full-path line. The chip reads "Also in folder {basename}".
  - **Inspect panels:** a static "Chunks"/"Source" h3, a name and path line, and a close (×) that returns focus to the opener. No Escape.
  - **Testids:** `kb-other-items-panel` is retired in favour of `kb-individual-files-panel`.
  - **Squawk candidates (backend, to log at close):**
    - the item DELETE of a walked file answers 200 and the next walk re-adds it (it should be 409);
    - a file-item POST does not call `request_index`.
  - An implementing Developer was spawned.
- **Step 8 [kb-search], partial.** "zzzz" returns low-score hits. This is retrieval behaviour: semantic search has no score floor, so "No results." appears only for an empty KB, and the RRF scores are not percentages. It is not a flight regression. Proposed follow-up (needs design, and evals since agents share it): a semantic-only score floor and/or a keyword-match marker. The operator was asked to check "No results." on the empty "HAT scratch".
- **Follow-ups (operator-confirmed):** an "Add file" UI for individual files (a new form with its own validation and errors). Carried to the flight debrief / mission Known Issues.
- **Step 8, remainder:** pass. The result layout, × (clears and keeps focus), Escape, and "No results." on the empty KB all work.
- **Step 15 [theme]:** pass. The operator checked dark and approved it; they are confident the pending Individual files and inspect changes inherit it (they use the same tokens).
- **Follow-up (operator-confirmed): knowledge search scoring.**
  - Semantic search has no score floor, so nonsense queries ("zzzz", "xyzxyz") return a full page of low-score hits, and "No results." appears only for an empty KB.
  - The fused RRF score (≈0.016) reads like a percentage but is not one.
  - This needs design (a floor for semantic-only hits and/or a keyword-match marker) plus an eval run, because agents use the same `retrieval.search`. It fails squawk criterion 2 (design decisions), so it goes to the mission Known Issues and the debrief, not a squawk.
- **Operator check: "all the chunks are the same."** Not a defect. The seed wrote each runbook as one paragraph repeated 4 times, and the 4 short paragraphs fit one chunk (`runbook-01.md` has one chunk, `seq` 0), so the panel shows the file's real text. Separately, `runbook-01.md` appears twice in search because it is registered twice (walked, and individually): the DD-9 case the chip warns about.
- **Step 16 [captures]:** waived by the operator ("not worried about the screenshot"). The after set from leg 09 stands, and the HAT fixes were checked live.
- **Individual files and inspect change landed (uncommitted):** the design as written, with two adaptations:
  - `renderFolders` re-runs `renderAllItems` when a folder panel is added or removed, so held-out orphans appear;
  - the opener-focus check also verifies `activeElement`, because Chromium reports rects for a trigger inside collapsed `<details>`. A new test caught this.
  - **Tests:** knowledge lane 59 passed (258 s), with 17 new tests; guards 125 passed. `kb-other-items-panel` is retired.
  - The FD eyeballed `cap2/`: rows, chip, trash and inspect head as designed.
  - Because this adds behaviour, a scoped Sonnet Reviewer was spawned before the commit. The operator re-checks live in parallel.
- **Review:** [HANDOFF:confirmed], no blocking issues; guards 117 passed. Four nits accepted as non-blocking: an indent at `knowledge-inspect.js:119`; `removeFile`'s catch also covers success-path throws; the in-flight test leans on the disabled button; the aria-label is set once (the path is immutable). Waiting on the operator's live re-check before commit.
- **Operator re-check of Individual files and inspect:** "looks really good". One ask: the chunks panel should match the source panel's isolated box. This is a look-and-feel fix on a single surface; the implementing Developer was resumed to wrap the chunk rows in a boxed `div.kb-chunk-list` that shares the `.kb-source-text` box.
- **Chunks box landed (uncommitted):** `div.kb-chunk-list` (testid `kb-chunk-list`) shares the `.kb-source-text` box rule; the `setLine` indent nit is fixed. Knowledge lane 59 passed (257 s); guards 125 passed.
- **HAT complete (2026-10-23).**
  - The operator re-checked the chunks box and said "call it done".
  - Steps 1-6 and 8-15 passed with fixes; step 7 was skipped (test-covered); step 16 was waived. HAT items 1-6 were approved; item 7 keeps "Knowledge".
  - Squawks 0243 (deleting a walked file is undone) and 0244 (a file POST does not start indexing) were logged.
  - Mission Known Issues gained the search score floor and "Add file".
  - Leg 10 is `completed`; the flight is `landed`.
