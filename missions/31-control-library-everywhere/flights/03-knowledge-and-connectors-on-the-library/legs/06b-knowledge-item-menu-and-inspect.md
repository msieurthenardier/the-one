# Leg: knowledge-item-menu-and-inspect

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Move the knowledge-base file row's item menu onto `App.ui.menu`. This retires the hand-built `buildItemMenu` and its capture-phase document listeners, and reproduces DD8-7 first. Then move the chunks and source panels onto library controls, with generation guards and focus on the opened panel (DD8-5's panel half).

When this leg lands, every knowledge module is at zero ownership-allowance rows, and the catalogue's "KB item menu: not yet defined" row is retired.

## Context
- **Flight DD4** (`App.ui.menu`; the `more` icon from leg 03b; no permanent document listeners), **DD8-5**, **DD8-7**, **DD10**, **DD11.** Leg 03b recorded the menu differences in the flight log; read them:
  - it closes on `pointerdown`;
  - `onSelect` runs after focus has returned to the trigger;
  - there is no portal and no flipping, so a popup inside the "Other items" panel may clip.
- **Leg 06a** keyed the rows and stopped closing menus on refresh. A row's menu closes when the row is removed, through whatever close hook 06a gave it. This leg moves that hook to `menu.close()` and `menu.destroy()`.
- **Today's menu** (`buildItemMenu`, in `knowledge-folders.js` after leg 02; formerly `knowledge-section.js:663-762`):
  - `div.kb-item-menu-wrap` holds the trigger `button.kb-item-menu-trigger` "⋯" (testid `kb-item-menu-btn`, `aria-haspopup=menu`, `aria-expanded`, aria-label "Item actions") and the popup `div.kb-item-menu[role=menu]` (testid `kb-item-menu`, hidden);
  - the items are `button.kb-item-menu-item[role=menuitem]`: `kb-item-chunks-btn` "View chunks" and `kb-item-source-btn` "View source";
  - while open, capture-phase `document` `click`/`keydown` listeners handle outside close, Escape and arrows;
  - one menu is open at a time (`openItemMenu`/`closeAnyOpenItemMenu`);
  - an item click closes with `returnFocus: false` and opens the panel.
- **Today's panels** (`knowledge-inspect.js` after leg 02; formerly `:768-853`):
  - `openChunksPanel(item)` and `openSourcePanel(item)` fetch `/items/{id}/chunks` and `/items/{id}/source` into fixed panels appended to `foldersSection` after `foldersListEl`;
  - `_panelTitle(item)` names the file;
  - chunk rows carry `.kb-chunk-seq`;
  - the source shows a freshness flag;
  - read the module for the exact testids (`kb-chunks-panel`, `kb-source-panel`, close buttons, …);
  - there is no generation guard, so a late response can paint the wrong item;
  - focus is left on a hidden menu item.
- **Tests:**
  - `test_flow_studio_knowledge_inventory.py`: the menu keyboard test (about `:1109-1139`: ArrowDown opens, Esc returns focus, outside click closes, item testids); chunk and source tests (about `:551`, `.kb-chunk-seq`); the panel-title and fixed-position notes (the "kb-studio-round-trip remediation FIX 4" comments);
  - `tests/behavior/kb-studio-round-trip.md` steps 5-6 (chunks and source).

## Inputs
- Legs 02, 03b (the `more` icon; menu differences recorded) and 06a landed.

## Outputs
- **The item menu:** `App.ui.menu({trigger: {iconOnly: true, icon: 'more', ariaLabel: 'Item actions', variant: 'ghost', size: 'sm', testid: 'kb-item-menu-btn'}, items: [{label: 'View chunks', testid: 'kb-item-chunks-btn', onSelect: …}, {label: 'View source', testid: 'kb-item-source-btn', onSelect: …}], align: 'end', testid: 'kb-item-menu'})` per row.
  - **Size:** match today's trigger size. If the library small ghost icon button differs computed-wise, add a ledger row, and change no library option in this leg; a needed option re-tiers the leg (DD11).
  - The trigger's "⋯" text becomes the `more` icon.
  - `buildItemMenu`, `openItemMenu`/`closeAnyOpenItemMenu` and the capture listeners go. One-open-at-a-time is the library's own (it keeps one open menu).
  - 06a's row removal calls `menu.destroy()`.
  - The disclosure's collapse closes a menu inside it (today's `toggle` handler), through `menu.close(false)` on the menus in that panel.
- **DD8-7, test-first:** with a row's menu open, pressing Ctrl K (Meta K on macOS) opens Jump to, and arrows and Escape in the palette act on the palette (or record that the old menu did not hijack them, if the reproduction shows no defect, and keep the test as a regression pin).
- **The panels:**
  - `openChunks(item)` and `openSource(item)` each take a token from a per-panel `mountSlot` (or generation counter). A response for an older token, or after `destroy`, is dropped;
  - the panels are built from `section`/`status`/`emptyState`/`button` where they hold controls (the close button, loading, error, empty), keeping their testids and text;
  - the chunk and source content nodes (`.kb-chunk-seq` and so on) are area layout and stay;
  - **focus:** after a menu `onSelect` opens a panel (focus has returned to the trigger first), focus moves to the opened panel's heading (`tabindex=-1`), so it is never left on a hidden menu item.
- **Clipping:** check a menu opened on a row in the "Other items" panel near its bottom. If the popup clips, record it in the ledger and the flight log as a HAT item; do not add flipping to the library here.
- **CSS:** the `.kb-item-menu*` rules (`studio.css` about `:1001-1047`) are removed after grep.
- **Allowances:** `knowledge-*.js` have zero `OWNERSHIP_ALLOWANCE` rows. If any remain from other legs' leftovers, finish them here; if a row needs a library option, stop and re-tier.
- **Catalogue:** the "KB item menu" row (about `:118`) is retired (status: library `App.ui.menu`), and the `menu` row lists the knowledge consumer.
- **Tests:**
  - the menu keyboard test passes, with locators moved to roles where they used old classes;
  - **new:**
    - (a) DD8-7 (above);
    - (b) **DD8-5, test-first:** open chunks for item A and, while its response is held (`page.route`), open chunks for item B; release A, and the panel shows B;
    - (c) focus after "View chunks" is on the chunks panel's heading;
    - (d) no `document`/`window` listener remains after a menu closes (the listener-cleanup approach, or an instrumented count).

## Design review amendments (binding; they supersede earlier text where they differ)
Design review cycle 1 (Sonnet Developer): approve with changes. **The citations after the split:**
- `buildItemMenu` at `knowledge-folders.js:144-227` (its tracker `:121-135`, the capture listeners `:197-198`), which leg 06a reduces to `{el, close}` per row;
- the panels in `knowledge-inspect.js`: `_panelTitle` `:26-30`, `openChunksPanel` `:41-79`, `openSourcePanel` `:81-111`, placed by `knowledge-detail.js:224-225`;
- `studio.css` `.kb-item-menu*` at `:1001-1045`;
- the catalogue rows at `:117-118`;
- the registry rows at `:175-176` and `:427-428`.

1. **One stable heading per panel (a high finding).** Today every state does `panel.textContent = ''` and rebuilds the title (`knowledge-inspect.js:44-108`), so focus on the heading is lost when the response lands.
   - Each panel is an `App.ui.section({titleTag: 'h3'})` whose heading (`tabindex=-1`, with the title testid kept) is built once.
   - Each state replaces only a content region beneath it.
   - The heading changes from `div.section-title--plain` to `h3`: a ledger row.
   - Test (c) asserts focus on the heading **after** the response arrives.
2. **There are no close buttons and no freshness flag in the panels.** Drop both mentions. Add nothing: no behaviour addition.
3. **Menu placement:** each row wraps the menu in an area-owned `span.kb-item-menu-slot { margin-left: auto }` (replacing `.kb-item-menu-wrap`'s rule). No area rule names a library class.
4. **Panel collapse:** leg 06a's per-panel row map holds each row's menu. The disclosure's `onToggle(false)` calls `menu.close(false)` on that panel's menus. Row removal calls `menu.destroy()`.
5. **The final sweep:** grep `tests/_ui_ownership_allowance.py` and `tests/test_ui_guards.py` for `knowledge-`. Delete the dead helpers from `knowledge-shared.js` (`_input`, `_fieldGroup`, `_section`, `_btn`, `_appendIcon`, `_textarea`, and any other with no caller left). The leg fails loudly, as a report to the Flight Director, if any row remains that the earlier legs should have removed.
6. **DD8-7 (test (a)) is expected to reproduce.** The old capture `keydown` takes ArrowDown and Escape while the palette is open. The test opens a menu, presses Control+K, then ArrowDown and Escape, and asserts on the palette. It lives in `test_flow_studio_knowledge_inventory.py` (the `library` lane).
7. **Test (d):** open a menu, remove its row through an items refresh, then assert no leaked `pointerdown` listener and no open menu.
8. **One `mountSlot` for both panels.** A later "View chunks" makes a pending source response a no-op.
9. **The loading and error lines:**
   - `admin-loading` becomes `status` pending (`live: 'off'`, `led: false`);
   - errors become `status` danger (`role: 'alert'`, `led: false`, `textTone: true`);
   - "No chunks yet." stays `div.empty-state` through `App.ui.emptyState` (the test about `:435` reads that class).
10. **Ledger:**
    - the trigger changes from a bordered "⋯" text button to a ghost `more` icon button (height, border);
    - the panel `h3` heading.

    Tests use `expect(...).to_be_focused()`, because focus moves twice: to the trigger, then to the heading.

## Acceptance Criteria
- [ ] Every Output is in place. No hand-built menu, popup or capture listener remains in the knowledge modules.
- [ ] Tests (a)-(d) pass. (b) (and (a), if it reproduces) are recorded as failing before the fix. The existing menu and panel tests pass, with any change a locator move listed in the flight log.
- [ ] `OWNERSHIP_ALLOWANCE` and `HTML_SINK_ALLOWANCE` have no rows for any `knowledge-*.js` file.
- [ ] The catalogue's "KB item menu" row is retired, and `tests/test_ui_control_inventory.py` passes.
- [ ] The `library`, `mcp`, `routing` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1`, and so do `make test-unit` and the static guards.
- [ ] **Ledger rows:** the `more` icon trigger; any trigger-size difference; the menu closing on pointer-down; the focus move to the panel heading (a behaviour change, DD8-5); a clipping note if found.
- [ ] The `library` lane's time is reported against its budget.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_studio_knowledge_inventory.py tests/browser/test_flow_jump_to.py -x --timeout 90`; the four lanes; `make test-unit`.

## Implementation Guidance
1. **Log a start line.** Write tests (a) and (b) against the current code; record the results.
2. **The menu onto `App.ui.menu`;** remove the old machinery.
3. **Panel generation guards and focus.**
4. **CSS removal, the catalogue, allowances, ledger, flight log.**

## Edge Cases
- **A menu open while its row's panel collapses:** the menu closes without returning focus to a now-hidden trigger. Focus goes to the summary.
- **The same item opened twice:** the panel re-fetches. The older token is dropped, and the panel shows the latest.
- **A panel open while its item is removed by a poll:** the panel stays, showing its last content, as today. Record any change.

## Files Affected
- `js/areas/studio/knowledge-folders.js`, `knowledge-inspect.js`
- `css/studio.css`
- `tests/browser/test_flow_studio_knowledge_inventory.py` (and a jump-to interaction test, in that file or `test_flow_jump_to.py`)
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `tests/_ui_ownership_allowance.py`
- `tests/behavior/kb-studio-round-trip.md` (if needed)
- The flight log

## Citation Audit
Drafted at `332496d` from `knowledge-section.js:663-853` and `menu.js` (FD read). **Re-cited by module and function after leg 02 lands,** before this leg goes `ready`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
