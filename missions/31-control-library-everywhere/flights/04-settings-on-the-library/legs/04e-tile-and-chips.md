# Leg: tile-and-chips

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Add two pieces to the library:
- `App.ui.toolTile` and `toolTile.grid`, the Built-in tools tile;
- the `chipList` changes: the full value kept in `data-value`, `chipList.valuesOf(el)`, and a one-line middle ellipsis for long chips (B4).

Each is contract-tested in Chromium and WebKit with a catalogue row. **No consumer moves.**

Split from the list-controls leg (now 04d) at its design review (2026-10-23): the chip change ripples into the agent Tools tab and leg 05.

## Context
- **Flight decisions:** DD4, DD12 (`toolTile`'s marker classes are `ui-tool-tile` and `ui-tool-tile-grid`; the legacy `entity-tile*`, `tool-tile*`, `tile-title-row` and `entity-tile-grid` hand over in leg 06), DD11, DD7 (ledger rows 28 and 40).
- **The chip value contract changes.** Today `chip-list.js` reads a chip's value from `chip.textContent` minus the trailing "×" (`textOf`), for `values()`, `exists()` and the Backspace and click handlers. Truncating the visible text would corrupt all of these. So:
  - every chip stores its full value in `data-value`;
  - `textOf` reads `data-value`;
  - the visible text goes in a child `span.ui-chip-text`.

  The legacy string-built chips (`tools-form-helpers.js`'s `renderChipListEditor`, the MCP editor's) are untouched: Flight 5's.
- **The middle ellipsis: a JS character budget.** CSS cannot truncate in the middle, and measuring rendered width is not deterministic across engines and fonts.
  - A pure helper `App.ui.util.middleEllipsis(value, budget)` keeps the first about 60% and the last about 40% of the budget, joined by "…", and returns short values unchanged.
  - The chip uses a budget of **40** characters, a library constant recorded in the catalogue row.
  - A CSS backstop keeps any value on one line: `.ui-chip-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }` and `max-width: 100%` on the chip.
  - Locked chips are truncated the same way.
  - **Accessibility:**
    - the remove button keeps its name "Remove {full value}";
    - the chip sets `title` to the full value;
    - the truncated visible text is `aria-hidden`, with a `.visually-hidden` full-value twin, so a screen reader never reads "…".
  - **The ledger row (28)** applies to the agent Tools tab too. The MCP editor's string chips are Flight 5's.
- **`toolTile`:**
  - `App.ui.toolTile({key, name, href, selected, badge, description, toggle: {label, checked, disabled, onChange, testid, dataset}, testid, dataset})`, keyed by `key` (the tool name);
  - a card with the linked name (`aria-current="page"` when selected), an optional `App.ui.badge`, a description and an `App.ui.toggle`;
  - returns `{el, key, link, toggle, setSelected, setChecked, setDisabled, setDescription}`;
  - the toggle's accessible name comes from `toggle.label`, supplied by the caller (leg 06 decides the words, DD8-1). The testids (`tool-card`, `tool-toggle`) are caller-supplied too;
  - `toolTile.grid({label, testid})` returns `{el, sync(tiles)}`, a `role=list` container keyed by `tile.key`, using `App.ui.util.syncChildren`.
- **The frozen legacy look.** `tests/browser/_legacy_tool_css.py` freezes only the agent-tab Tools rules today. Add a new constant, `LEGACY_ADMIN_TILE_CSS`, with today's admin tile rules: from `admin.css`, `.area-admin .tool-tile`, `.tile-title-row`, `.tool-tile-link`, `.admin-tool-badge*` and the corner switch; from `components.css`, the shared `.entity-tile*`. Copy them as they are at this leg's start.

## Inputs
- Legs 03b (`syncChildren`), 04c (the emitted-class guard) and 04d landed.
- `js/ui/tile.js`, `js/ui/chip-list.js`, the toggle factory, `tests/browser/_legacy_tool_css.py`, `tests/browser/test_ui_tile_contract.py`, `tests/browser/test_ui_chip_list_contract.py`.

## Outputs
- `js/ui/tile.js`: `toolTile` and `toolTile.grid`.
- `js/ui/chip-list.js`: `data-value`, `span.ui-chip-text`, the ellipsis, `chipList.valuesOf`.
- `js/ui/core.js`: `App.ui.util.middleEllipsis`, with the util key pin in `test_ui_library_contract.py:70` updated in sorted order.
- The library CSS sections; `LEGACY_ADMIN_TILE_CSS`.
- Catalogue rows (`toolTile`, the `chipList` options, the budget constant, the `middleEllipsis` helper note) and contract tests in both engines.

## Acceptance Criteria
1. **`middleEllipsis`** returns exact strings for short, exactly-budget and over-budget values. The 97-character path gives an exact expected string, asserted.
2. **`chipList`** (contract, both engines):
   - `values()` and `valuesOf(el)` return the full values, locked chips included, even when chips are truncated;
   - duplicates are detected on full values;
   - Backspace and click-to-reposition work on truncated chips;
   - a 97-character chip renders on one line within the list's width, with the exact truncated text visible, `title` the full value, the remove button named with the full value, and the accessible text the full value with no "…".

   Existing `chipList` contract assertions on `textContent` are retargeted to `data-value` or the visible span, never relaxed.
3. **The agent Tools tab still works:** the `agent-tabs` lane passes. Its chip assertions are retargeted only where they read `textContent`.
4. **`toolTile`** (contract, both engines): the link name and `href`; `aria-current` when selected; the toggle's `role=switch` and caller name; the setters; the testids and dataset.
5. **The tile's look matches the frozen legacy tile.** Compare a `toolTile` under `.area-admin` with a legacy-markup tile rendered with `LEGACY_ADMIN_TILE_CSS`, on these named computed properties:
   - the title row's `display` and `gap`, and the link's flex, overflow and ellipsis;
   - padding top, left and right;
   - border and radius;
   - the badge's font, size and position in the title row;
   - the description's font and line clamp.

   **Bottom padding and height are excluded** (the in-flow library toggle replaces the absolutely positioned corner switch, ledger row 40). Instead, assert the toggle sits inside the tile and overlaps neither the badge nor the description.
6. **`grid.sync`** reconciles by key, and keeps a focused tile's toggle focused across a re-sort in both engines. If an engine blurs on move, the grid refocuses that toggle after `sync`; record which engines need this.
7. No allowance row is added and no consumer file changes. The emitted-class guard names `ui-tool-tile`, `ui-tool-tile-grid` and `ui-chip-text` as owned by their rows.
8. The unit tier, the static guards, both contracts lanes, and the `agent-tabs` and `agents` lanes pass.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py -q -x --timeout 120`.
- Lanes `contracts` (alias), `agent-tabs` and `agents` with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- `make test-unit` once.

## Implementation Guidance
1. `chipList` first: `data-value` and `textOf`, with every existing contract test passing, then the ellipsis, then `valuesOf`.
2. Freeze `LEGACY_ADMIN_TILE_CSS`, then build `toolTile` and its grid test-first against it.
3. Write the catalogue rows and update the util key pin.

## Edge Cases
- **A value that is a single long token** (a 97-character host with no separators): the character budget still applies.
- **Pasting several values:** each chip gets its own `data-value`.
- **`grid.sync` with a removed tile that had focus:** no special focus handling here; leg 06 decides.

## Files Affected
- `static/js/ui/tile.js`, `chip-list.js`, `core.js`; `static/css/components.css` (the library sections).
- `tests/browser/_legacy_tool_css.py`, `test_ui_tile_contract.py`, `test_ui_chip_list_contract.py`, `test_ui_library_contract.py`, and the `agent-tabs` tests (only retargeted chip reads).
- `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- `chip-list.js:34` `chipList`; `textOf` reading `textContent`: from the list-controls design review (Sonnet, 2026-10-23), not re-read by the FD.
- `tile.js` `groupTile` `:33`, `toolRow` `:216`: verified (FD grep).
- `_legacy_tool_css.py` holds only the agent-tab rules: from the list-controls design review.
- `components.css:2201` `.chip-list-editor .chip` has no `max-width`: from the list-controls design review.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
