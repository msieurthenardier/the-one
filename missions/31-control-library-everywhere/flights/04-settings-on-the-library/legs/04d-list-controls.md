# Leg: list-controls

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Build the list and tile controls and options the Built-in tools and Date and time pages need, in the library only, each contract-tested in Chromium and WebKit with a catalogue row:
- the `searchList` inline variant;
- `toolTile` and its grid;
- `tabs` `panelPadding`;
- the `radioGroup` slot option;
- `chipList.valuesOf` and its one-line middle ellipsis.

**No consumer moves.**

## Context
- **Flight decisions:** DD4, DD12 (marker classes; the `toolTile` handover in leg 06, the inline CSS's recorded duplication until leg 09), DD11, DD7 (ledger rows 28 and 32).
- **The `searchList` inline variant.** Date and time hand-rolls these around today's `App.ui.searchList` (`date-time-page.js` about `:371-381`, `:117-120`, `:258-272`, `admin.css` about `:650-681`):
  - it keeps `scrollTop` across `refresh()` (which resets it, `search-list.js` about `:220`) by reaching into `.ui-search-list-listbox`;
  - it sets `aria-describedby` on the input by hand;
  - it draws the chosen check icon as a caller `lead`, aria-hidden, so assistive technology only gets it through the describedby line;
  - its CSS caps the listbox height, suppresses the active-row paint while the list is unfocused (with a forced-colours twin), sizes the lead and sets a mono description.

  The variant (`inline: true`) owns all of that:
  - `keepScroll` behaviour: when the active id survives a `refresh()`, the scroll position is kept;
  - `describedBy` (an id or a node);
  - an item `selected: true` flag drawn as the check lead, with a fixed-width spacer on the other rows and visually hidden "(selected)" text in the option's name;
  - **B8 (ledger row 32):** a `scrollActive: 'center'` option centres the active row in the listbox instead of `nearest`.

  The modal defaults (agent picker, Jump to) **must not change**: their contract lanes stay green with no test edits.
- **`toolTile`** (Architect: `groupTile` and `toolRow` do not fit). It is a card with:
  - a linked name (`href`, `aria-current="page"` when selected);
  - an optional `App.ui.badge`;
  - a description (B1: the per-tool summary, set by the caller);
  - an `App.ui.toggle` with its own label, `checked`, `disabled`, `onChange`, testid and dataset;
  - a selected state.

  It returns `{el, link, toggle, setSelected, setChecked, setDisabled, setDescription}`. **`toolTile.grid({label, testid})`** returns the `role=list` grid container (`entity-tile-grid`) with `{el, sync(tiles)}` (keyed through `App.ui.util.syncChildren`).
  - Marker classes: `ui-tool-tile`, `ui-tool-tile-grid`.
  - Legacy classes: `entity-tile*`, `tool-tile*`, `tile-title-row`, `entity-tile-grid` (handover leg 06).
  - Freeze today's tile and switch CSS as a test fixture (`tests/browser/_legacy_tool_css.py`, the Flight 2 precedent) so the contract can assert that the new tile, under `area-admin`, matches today's geometry, apart from the switch's planned change to the library toggle (ledger row 40).
- **`tabs` `panelPadding: 'none'`** replaces `.settings-list .tablist`/`.tabpanel` (`admin.css` about `:136-137`). `App.ui.tabs` (`js/ui/tabs.js:24`) is the library tabs; the legacy `App.tabs` retires in leg 06.
- **The `radioGroup` slot option.** `optionEl(value)` returns `div.ui-radio-slot`, and `admin.css` about `:643` indents it for Date and time. Add `slotIndent: 'none'|'label'` (or the name the Developer finds clearer), so the page stops restyling `ui-radio-slot`.
- **`chipList`:**
  - **`App.ui.chipList.valuesOf(el)`** (static) reads a mounted chip list's values from its root element, so area code (`agent-form-data.js` after leg 05) never names `chip-list-editor` or another owned class.
  - **B4 (ledger row 28, operator):** a long chip shows on one line with a **middle ellipsis** (keep the start and the end, for example `/home/…/deep/folder`). Its full value is in `title` and in the remove button's accessible name, which already names the value; check this. Measure with the chip's real width, or use a CSS-plus-character-budget approach. Pick one that is deterministic in both engines. The agent Tools tab gets it too. The MCP editor's string-built chips are Flight 5's and are untouched.

## Inputs
- Legs 04a-04c landed (`facts`, `banner`, the emitted-class guard from 04c).
- `js/ui/search-list.js`, `choice.js` (`radioGroup` `:163`, slot `:214`, `optionEl` `:286`), `tabs.js`, `tile.js` (`groupTile` `:33`, `toolRow` `:216`), `chip-list.js` (`:34`), `toggle` (find its file).

## Outputs
- The options and factories above, each with a catalogue row (options, states, owned classes, handover leg) and contract tests in both engines.
- `tests/browser/_legacy_tool_css.py` extended or created with the frozen tile and switch CSS.
- The emitted-class guard's exempt list updated only for new dynamic names, with reasons.

## Acceptance Criteria
1. **The inline `searchList`** (contract, both engines):
   - `refresh()` keeps the scroll position when the active id survives;
   - `describedBy` sets `aria-describedby`;
   - a `selected` item shows the check lead and has "(selected)" in its accessible name, while other rows have the spacer;
   - `scrollActive: 'center'` centres the active row (bounding-box assertion);
   - unfocused, no active-row paint; focused, the paint; the forced-colours twin is checked where the harness supports it;
   - the capped listbox height.
2. **The modal searchList is unchanged.** The agent picker and Jump to tests (the `chats`, `shared` and `contracts-overlay` lanes) pass with no edits, and the variant's CSS applies only under its own class.
3. **`toolTile` and `toolTile.grid`** (contract, both engines):
   - the link name and `href`, and `aria-current` when selected;
   - the toggle's `role=switch` and name;
   - `setChecked`/`setDisabled`/`setSelected`/`setDescription`;
   - `grid.sync` keeps a focused tile's toggle focused across a re-sort;
   - geometry under `area-admin` matches the frozen legacy fixture (title row, badge, description clamp, card padding), apart from the switch.
4. **`tabs` `panelPadding: 'none'`** and **`radioGroup` `slotIndent`**: computed-style checks under `area-admin`.
5. **`chipList.valuesOf`** returns exactly what the list holds, including locked chips. Contract-tested.
6. **The middle ellipsis** (contract, both engines):
   - a 97-character value renders on one line inside the list's width;
   - the visible text keeps its first and last segments;
   - `title` and the remove button's name carry the full value;
   - a short value is unchanged.
7. **No allowance row is added; no consumer file changes** (`git diff --stat` touches `js/ui/`, the library CSS sections, tests and docs only).
8. The unit tier, the static guards, the emitted-class guard, and both contracts lanes pass. So do `chats`, `shared` (picker and palette), `agent-tabs` (the chip list on the Tools tab) and `agents`.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py -q -x --timeout 120`.
- Lanes `contracts` (alias), `chats`, `shared`, `agent-tabs` and `agents` with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, at most 3 at once.
- `make test-unit` once.

## Implementation Guidance
1. Read `search-list.js` end to end and `date-time-page.js`'s use of it. Add the variant test-first. Put its CSS in the library's `searchList` section under the variant class. The `admin.css` overrides stay until leg 09 (a DD11 exception, recorded).
2. `toolTile`: freeze the legacy CSS fixture first, then build the tile to match it.
3. `tabs`, `radioGroup` and `chipList` options.
4. The catalogue rows, then the guard runs.

## Edge Cases
- **The middle ellipsis and RTL or very long single segments** (a 97-character host with no separators): ellipsis in the middle by characters is acceptable.
- **A selected item that is filtered out** by the query: no check is shown, and the describedby line still names the chosen zone (Date and time's existing rule).
- **`grid.sync` with a tile removed while its toggle has focus:** focus goes nowhere special here. Leg 06 decides where it goes.

## Files Affected
- `static/js/ui/search-list.js`, `tile.js`, `tabs.js`, `choice.js`, `chip-list.js`; `static/css/components.css` (the library sections).
- `tests/browser/test_ui_search_list*_contract.py`, `test_ui_tile_contract.py`, `test_ui_tabs_contract.py`, `test_ui_choice*`/radio contract, `test_ui_chip_list_contract.py`, `tests/browser/_legacy_tool_css.py`.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
Checked at `512616b`:
- `search-list.js:6-50` (options and ARIA; `scrollIntoView` `'nearest'`): verified (FD read).
- `choice.js:163` `radioGroup`, `:214` slot, `:286` `optionEl`: verified (FD grep).
- `tile.js:33` `groupTile`, `:216` `toolRow`; `tabs.js:24`; `chip-list.js:34`: verified (FD grep).
- `date-time-page.js` and `admin.css` lines: from the survey. Leg 01's dead-CSS deletion may shift `admin.css` lines.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.

**Split at planning.** This leg keeps the `searchList` inline variant, `tabs` `panelPadding` and the `radioGroup` slot option. **`toolTile`, `toolTile.grid`, `chipList.valuesOf` and the chip middle ellipsis move to the new leg 04e** (`tile-and-chips`). Body AC3, AC5 and AC6, and their guidance, belong to 04e.

- **`keepScroll`, defined.** The inline variant remembers the query and the active option id.
  - A `refresh()` with an unchanged query restores `scrollTop` and re-activates the previous active id if it still exists, without scrolling it.
  - A changed query resets the scroll to the top, and activates the first option.
  - AC1 tests both.
- **`scrollActive: 'center'`** applies only to programmatic activation (the initial render, `refresh()`, `setActive(id)`). Arrow keys keep `nearest`, so the list never jumps on a keypress.
- **The `selected` mark** is built inside the variant, without using the caller's `lead` option:
  - a check icon, or a fixed-width spacer on the other rows, in the aria-hidden lead wrapper;
  - plus a `.visually-hidden` " (selected)" span inside the element that names the option.

  The contract test reads the option's accessible name (`get_by_role('option', name=…)`) and proves it includes "(selected)".
- **`tabs` `panelPadding: 'none'`** adds a marker class (`ui-tabs--flush`) on the panels, not a second `panelClass` path. The test checks the computed padding is 0 under `.area-admin`.
- **`radioGroup` `slotIndent: 'label'`** aligns the slot's left edge with `.ui-radio-text` (bounding-box comparison), not a pixel number.
- **Forced colours:** the inline variant's forced-colours rule is checked by a CSS-text assertion, because the harness cannot emulate it.
- **Emitted-class guard:** spell out the new names (`ui-search-list--inline`, `ui-tabs--flush`). They are owned by their factory's row, not exempt.
- **Lanes:** add `settings`. Date and time still runs its hand-rolled list until leg 09, and must stay green.

Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
