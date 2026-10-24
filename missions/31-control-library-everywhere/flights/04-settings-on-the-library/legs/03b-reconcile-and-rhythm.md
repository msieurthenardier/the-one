# Leg: reconcile-and-rhythm

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Add two pieces to the library:
- `App.ui.util.syncChildren(parent, nodes, {after})`, which reconciles keyed children and never re-inserts a node that is already in place;
- an opt-in stack layout for `App.ui.section`.

Then move their first consumers onto them:
- `knowledge-folders.js` and `knowledge-rows.js` (from `knowledge-shared.js`), and `provider-models.js:placeNodes` (fixing its blur hazard);
- the connector doctor and pairing sections, and the knowledge folders section, retiring their area spacing rules.

Also fix two library a11y squawks: 0237 (a confirm lapse announced for a detached node) and 0238 (`keyValueTable` errors not announced).

## Context
- **Flight decisions:** DD3 (the reconcile and rhythm bullets, as corrected at Architect cycles 1 and 2), DD11.
- **`syncChildren`.** Leg 02b moved it from `knowledge-folders.js:101` to `knowledge-shared.js` (signature `syncChildren(parent, nodes, offset)`). Promote it to `js/ui/core.js` as `App.ui.util.syncChildren(parent, nodes, opts)`:
  - `opts.after` is an anchor node, and the managed run starts right after it;
  - without an anchor, the run starts at the first child;
  - a node that is already in its place is never moved;
  - nodes not in `nodes` are removed from the managed run only;
  - siblings before the anchor are untouched.

  `knowledge-shared.js` then delegates to it, or its callers switch to it; no copy remains.
- **The `placeNodes` hazard** (`provider-models.js:126-138`). When a desired node is not at `ref`, it calls `insertBefore`. So when an EARLIER row is removed, every LATER row is moved, which blurs a focused later row. The Ollama variant re-focuses through `focusedRow`/`restoreFocus` (about `:833`, `:960`), so the hazard is masked there. **Write a test that fails on today's code:** remove an earlier row while a later row's control has focus, and assert focus did not move and no `blur` fired. Then switch `placeNodes` to `syncChildren`. Keep or drop the re-focus workaround, but say which in the flight log.
- **The section stack** (opt-in, `App.ui.section({layout: 'stack'})`):
  - the body is a flex column with a token gap (`--space-3`);
  - children's own vertical margins are neutralised inside the stack (`.field-group`, `.section-title`, `.section-description`), because flex margins do not collapse;
  - `[hidden]` children take no space (the global `[hidden]` reset already does this).

  **The default layout does not change.** It has 26 `App.ui.section` calls in 14 files, plus `dangerZone`'s side-by-side buttons and the MCP editor's hand-built `.editor-section` blocks, and none of them may move.
- **The opt-ins and the rules they retire:**
  - the connector **doctor** section: retires `.area-studio .doctor-btn + :not([hidden]) { margin-top }` (`studio.css:784`);
  - the connector **pairing** section: `.area-studio .connector-pairing-result:has(> :not([hidden])) { margin-top }` (`:774`) exists because the result wrapper is visible while all its children are hidden. The editor hides the wrapper itself while it is empty (`hidden` on `connector-pairing-result`), and the stack gap does the rest. The rule then retires;
  - the knowledge **folders** section: retires `.kb-folders-list { margin-top }` (`:846`, re-locate it).
  - `studio.css` `.kb-item-row { padding: 6px 0 }` is row padding, not section rhythm. **It stays.**
- **Squawk 0237:** `ui/confirm.js:154-159` `lapse()` announces even when `itemEl` is no longer connected. Fix: skip the announcement (and the cue) when `!itemEl.isConnected`. The revert still runs, harmlessly. Add a contract test.
- **Squawk 0238:** `ui/key-value-table.js` `setError` (about `:260`) shows `div.ui-kv-error` with no role. Give it `role="alert"` (or focus the invalid cell; choose and say which). Add a contract test that it is announced (the role is present) and still linked through `aria-describedby`. No consumer calls `setError` today.
- **Visible change control:** capture `connector-edit` and the `kb-*` surfaces after the change, and compare them with leg 01's before set. Expected: no difference, or a few pixels' shift. Any difference is a ledger row with the measured px.

## Inputs
- Legs 02b and 03a landed.
- Leg 01's before set at `$HOME/.cache/the-one-ui-capture/m31-f4-before/`.

## Outputs
- `js/ui/core.js`: `App.ui.util.syncChildren`.
- `js/ui/editor.js` and the section's CSS (`components.css`, the library's own section): the stack layout.
- `knowledge-shared.js`, `knowledge-folders.js`, `knowledge-rows.js`, `provider-models.js`, `connector-editor.js` on the new pieces.
- `studio.css`: the three area rules removed.
- `ui/confirm.js` (0237), `ui/key-value-table.js` (0238); squawks 0237 and 0238 completed.
- Catalogue:
  - the `section` row gains `layout: 'stack'`;
  - the helpers list gains `syncChildren`;
  - the `confirm` and `keyValueTable` rows note the fixes.
- Contract tests in both engines.
- The after captures for the opted-in surfaces, compared in the flight log.

## Acceptance Criteria
1. `App.ui.util.syncChildren` is contract-tested in both engines:
   - order is reconciled;
   - leftovers are removed;
   - siblings before the anchor are untouched;
   - a node already in place is never re-inserted (a `MutationObserver` records no move for it);
   - a focused later node keeps focus when an earlier node is removed.
2. **`placeNodes` is gone.** The new focus test fails on today's code (record this) and passes now. The `providers` lane passes.
3. **One `syncChildren`.** `git grep -n "function syncChildren" the_one/` shows only `js/ui/core.js`. The `knowledge` lane passes, including the Flight 3 no-re-append tests.
4. **The section stack** is contract-tested in both engines under an `area-studio` ancestor and an `area-admin` ancestor:
   - the gap between two children equals the token;
   - a `.field-group` child adds no extra margin;
   - a hidden child takes no space;
   - the default layout (no option) has the same computed child spacing as before, checked on a fixture with a field group, a status line and a button.
5. **The three area rules are removed.** The connector doctor and pairing results and the knowledge folders list keep their gap: a computed-style or bounding-box assertion in their own tests checks the gap between the button and the shown result. The `library` and `knowledge` lanes pass.
6. **Captures:** the after captures of `connector-edit` and the `kb-*` surfaces match the before set, or each difference is a ledger row.
7. **Squawk 0237:** a lapse on a detached element announces nothing. Contract test; squawk completed.
8. **Squawk 0238:** the `keyValueTable` error is announced and linked. Contract test; squawk completed.
9. The unit tier, the static guards, both contracts lanes, and the `providers`, `library` and `knowledge` lanes pass. Every lane with a `dangerZone` host (`agents`, `mcp`) passes too, because `confirm.js` changed.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py -q -x --timeout 120`.
- Lanes, at most 3 at a time, each with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`: `contracts-controls`, `contracts-overlay`, `providers`, `library`, `knowledge`, `agents`, `mcp`.
- The capture compare (`scripts/ui_capture.py` with the surfaces named, then a PIL diff against the before set).
- `make test-unit` once.

## Implementation Guidance
1. Write the failing `placeNodes` focus test first.
2. Add `syncChildren` to `core.js` with its contract tests. Switch `knowledge-shared.js`, then `provider-models.js`.
3. Add the stack layout and its contract tests, with the default-layout regression fixture.
4. Opt in the connector doctor and pairing sections and the knowledge folders section. Hide the empty pairing wrapper. Delete the three rules.
5. Do 0237 and 0238.
6. Take the captures and compare them; update the catalogue, `agents.md` and the flight log.

## Edge Cases
- **A node in `nodes` that currently lives in another parent** is moved into the run (an expected insertion).
- **An `after` anchor not in `parent`:** throw. That is a caller bug.
- **Duplicate nodes in `nodes`:** throw. That is a caller bug.
- **The stack on a section with a title:** the title stays first, and the gap applies between it and the first child too. Check that this matches today's title-to-content spacing within a pixel or two, or neutralise the title's own margin to keep the same visual distance. Record the choice.

## Files Affected
- `static/js/ui/core.js`, `static/js/ui/editor.js`, `static/js/ui/confirm.js`, `static/js/ui/key-value-table.js`, `static/css/components.css` (the section's own rules).
- `static/js/areas/studio/knowledge-shared.js`, `knowledge-folders.js`, `knowledge-rows.js`, `provider-models.js`, `connector-editor.js`.
- `static/css/studio.css` (three rules removed).
- `tests/browser/test_ui_library_contract.py`, the `section`, `confirm` and `keyValueTable` contract test files, and the provider-models, connector and knowledge browser tests.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, `squawks/0237-*`, `squawks/0238-*`, the flight log.

## Citation Audit
Checked at `512616b`:
- `editor.js:188-218` `App.ui.section` (no layout option; children appended to `root`): verified (FD read).
- `components.css:1496-1502` (`.editor-section { padding: 12px 0 }` and the divider rules): verified (FD read).
- `studio.css:774` (`connector-pairing-result:has`), `:784` (`.doctor-btn + :not([hidden])`): verified (FD read).
- `studio.css:845` `.kb-item-row { padding: 6px 0 }`: verified. The `.kb-folders-list` margin rule is from the recon; re-locate it.
- `provider-models.js:126-138` `placeNodes`: verified (FD read).
- `confirm.js:154-159` `lapse()`: verified (FD read).
- `key-value-table.js:163`, `:260`: from the recon.

## Design Review Amendments (cycle 1, 2026-10-23)
These override anything above they contradict.
- **`tests/browser/test_ui_library_contract.py:70`** pins `Object.keys(App.ui.util).sort()`. Add `syncChildren` (after 03a's `latest`). The contract homes:
  - `syncChildren`: `test_ui_library_contract.py`;
  - the stack: `test_ui_editor_contract.py` (`contracts-controls`);
  - 0237: `test_ui_confirm_contract.py` (`contracts-overlay`, beside `test_lapse_is_visually_distinct…` at about `:114`);
  - 0238: `test_ui_key_value_table_contract.py`.
- **`syncChildren` semantics, stated exactly:**
  - element-only (it walks element children, as today's `parent.children` indexing does);
  - the managed run is everything after the anchor to the end of `parent`;
  - a node of `nodes` that sits before the anchor, a duplicate, a non-node, or an anchor outside `parent` all throw;
  - callers keep their own `.filter(Boolean)`.

  Today's algorithm (remove leftovers first, then a positional insert) already meets the guarantee. AC1's wording: "a node whose position is unchanged relative to the desired list after removals is never moved". The tests: `[A,B,C]` → `[A,C]` with C focused (C is not moved); `[A,C]` → `[A,X,C]` (only X is inserted); a swap moves exactly one node. Confirm that the `provider-models` regions hold only elements, or that a text node there is harmless.
- **The `placeNodes` focus test** lives in a `providers` browser test that drives the Ollama models panel (or `renderProviderModels` directly). Record it red on `placeNodes` before the switch.
- **Stack spacing decision.** Today a `.section-title` has margin `22px 0 10px` (title to content 10px), `.section-description` has `margin-top: -4px; margin-bottom: 12px` (title to description about 6px), and a `.field-group` has `margin-bottom: 12px`. Inside a stack (`row-gap: var(--space-3)`, 12px):
  - the title keeps today's distances: `margin-bottom: -2px` (10px to content) and the description `margin-top: -6px` (about 6px from the title);
  - the field group's `margin-bottom` is zeroed.

  Net: no visible change, measured by bounding boxes in the stack contract test. Any residual of 1px or more is a ledger row.
- **The stack class** (for example `editor-section--stack`) is owned by `section`. Add it to that catalogue row's owned list (`docs/ui-control-inventory.md` about `:120`). Consumers pass `layout: 'stack'` and never name the class. Its selectors must at least match the specificity of the area `.field-group` overrides (`studio.css` about `:813`, `:1003`); check them under `area-studio` and `area-admin`.
- **The default-layout fixture** compares computed margins and bounding-box offsets against numbers recorded on today's code (pasted into the flight log), not "same as before".
- **Pairing wrapper visibility:** one `syncPairingVisibility()` sets `resultEl.hidden = every child hidden`. It is called at:
  - the initial state;
  - the reset (about `:435`, `replaceChildren(pairingStatus.el)`);
  - "Generating…";
  - success;
  - error.

  The existing `>= 8` gap assertion (`test_studio_connector_editor.py:228-231`) and the doctor `>= 12` assertion (about `:116`) stay as the regressions for the retired rules.
- **The knowledge folders section:** the `.kb-folders-list` margin rule is at `studio.css` about `:1014`. The section's children are `[folderField, addFolderBtn, foldersListEl]`. Add a bounding-box assertion for button-to-list in `test_flow_studio_knowledge_inventory.py`.
- **Squawk 0238:** set `role="alert"` when the error shows and remove it when it clears (a pre-existing hidden alert is unreliable). The test asserts the role is present when shown, absent or hidden when cleared, and that `aria-describedby` equals the error id.
- **Squawk 0237:** the `isConnected` check goes first in `lapse()`. A detached element only reverts: no class, no announcement.
- **AC9 lanes** (confirm and section are shared): `contracts-controls`, `contracts-overlay`, `providers`, `library`, `knowledge`, `agents`, `agent-tabs`, `mcp`, `settings`, `chats` (the chat-row-delete lapse) and `routing`. Run them in batches of at most 3.
- **A flex column blockifies inline children.** Only opt-in sections use the stack, and the three opt-ins are checked by their captures. Record that no opted-in section relies on inline flow.

## Design Review Amendments (cycle 2, 2026-10-23)
These override cycle 1's spacing numbers.
- **The spacing inside a stack** (`row-gap: 12px`; flex margins don't collapse):
  - `.section-title { margin-bottom: -2px }`: 10px from title to a field, as today;
  - `.section-description { margin-top: -4px; margin-bottom: 0 }`: 6px from the title (12 - 2 - 4) and 12px to the first child, as today;
  - `.field-group { margin-bottom: 0 }`, except the **last** child keeps its own margin, so the section's trailing space is unchanged.

  The stack contract test pins: title to description 6px, title to field 10px, description to first child 12px, field to field 12px, and the trailing space equal to today's.
- **`test_ui_library_contract.py:70`** after 03a and 03b reads, sorted: `["applyDataset","el","icon","latest","mountSlot","rovingFocus","syncChildren","uid"]`.
- **Superseded body text:**
  - 0238 is `role="alert"`, set on show and removed on clear (there is no "focus the cell" choice);
  - the Verification lane list is AC9's 11 lanes;
  - the "stack on a titled section" edge case is settled by the spacing above.
- **The `.kb-folders-list` opt-in** goes where that section is built (`knowledge-folders.js` about `:171`; re-locate it after 02b). The `syncChildren` tests include the swap case. If `provider-models` passes an `after` anchor, it is an element.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
