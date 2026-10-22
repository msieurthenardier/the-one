# Leg: tab-and-tile-controls

**Status**: landed
**Flight**: [Agents on the library](../flight.md)

## Objective
Add the library controls the agent tabs need, each in its canonical form (flight DD3/DD4, the operator's canvas of 2026-10-16), with a catalogue row, owned classes, and contract tests in Chromium and WebKit, including the size and role-structure assertions from DD11:
- `App.ui.tabs`;
- `App.ui.groupTile`;
- `App.ui.toolRow`;
- `App.ui.chipList`;
- the `tristate` option on `App.ui.toggle`;
- `actions` on `App.ui.dangerZone`.

No surface is migrated in this leg.

## Context
- **Flight decisions:** DD3 (the controls and their APIs), DD4 (the approved visible changes), DD11 (size and role-structure assertions).
- **Approved canvas:** https://claude.ai/artifact/Pzn35KdwV9gsTrnCPRCcqo, with "Tools tab: today" and "Tools tab: canonical" boards. The canonical board is the target for `groupTile`, `toolRow`, `chipList` and the tristate switch. MCP's Refresh moves to the library's small button: 24px, 10px text, 14px icon.
- **What to reproduce exactly** (the planning extraction, at `dbcd458`):
  - **Tabs:** `components.css:1229-1266` (`.tablist`, `.tab`, `:hover`, `:focus-visible`, `[aria-selected="true"]`, `.tabpanel`), and `js/tabs.js` behaviour:
    - arrows move focus only, Home and End are supported, Enter/Space/click selects;
    - `aria-selected` and roving `tabindex`;
    - inactive panels are `hidden`;
    - `onBeforeChange` can veto a change.
  - **Tiles:** `studio.css:410-604`. The `.mcp-source-tile*` and `.tools-category-tile*` declarations are identical: the list gap is 12px; the tile is `12px 14px`, `--surface`, `1px --border`, `--radius-sm`; the name is `--font-size-body-lg` bold; the count chip and protocol chip are mono, tiny, semibold, uppercase, `--surface-elevated` and `4px` radius; the expand button reads "**N** tools ▸" with a chevron that rotates 90° when expanded; the body has `padding-top:4px`, a 6px gap. The MCP subtitle (`admin.css:617-632`) is caption size, `--fg-secondary`, `padding-left:44px`.
  - **Tool rows:** `studio.css:611-714`.
    - The built-in row is `details.tool-tile`: `8px 12px`, a 6px radius (`--radius-sm` is 6px, so no visual change), hover border `--accent` plus an `--surface-elevated` wash, an "Overrides ▸" affordance, and a dashed top border on the body.
    - The MCP row is a label row with the same look.
    - Shared parts: the mono semibold name, " — " plus the description in caption `--fg-secondary`, truncated to 100 characters plus "…"; a `tool-row-disabled` opacity of .5; and `tool-name-strike`.
  - **Chip list:** `admin.css:391-448` (the `.area-admin`/`.area-studio` copies): `.chip-list-editor` (wrap, 4px gap, 6px padding, border, 4px radius, min-height 40px, `--surface`, accent border on `:focus-within`), the chip (`2px 8px`, `--accent-translucent`, body-sm), `.chip-list-input` (flex:1, min-width 100px, transparent). There are two variants: the admin `.tools-editor-field .chip-list-editor` (width:100%; max-width:320px) at `:345`, and `.field-error-highlight` at `:369`. Locked chips (`[data-locked]`) render on `--surface-elevated` at opacity .7 with no remove button.
  - **The remove "×" changes** (canvas, approved): from `--accent` to `--fg-secondary`, turning `--status-danger` on hover and focus-visible.
  - **The toggle:** today's `App.ui.toggle` is `js/ui/choice.js:87-…`, and its CSS is `components.css` (`.ui-toggle-*`). Tristate's look follows the canvas: the accent-translucent track with an accent thumb at translateX(8px).
  - **The danger zone:** `js/ui/editor.js:212-260`, with `opts.action` single (and `beforeArm`).
- **Leg 03 has landed** (the `studio.js` split): read the flight log. This leg touches only `js/ui/*`, `components.css`, the catalogue, contract tests and `index.html` for new library scripts.

## Inputs
- Legs 01-03 landed.

## Outputs
- **New library files:** `js/ui/tabs.js` (`App.ui.tabs`), `js/ui/tile.js` (`groupTile`, `toolRow`), `js/ui/chip-list.js` (`chipList`). Each gets an `index.html` tag among the other `js/ui/*.js`, and the script-count pin is bumped by 3 with a dated line.
- **Changed:** `js/ui/choice.js` (toggle `tristate`), `js/ui/editor.js` (dangerZone `actions`).
- **`css/components.css`:** banners `App.ui.tabs`, `App.ui.groupTile`, `App.ui.toolRow`, `App.ui.chipList`, plus the tristate rules in the toggle banner.
  - Tabs: the existing `.tablist`/`.tab`/`.tabpanel` rules move under the tabs banner, unchanged.
  - The tile and row rules are copied from `studio.css` into owned `ui-group-tile*` and `ui-tool-row*` classes. The old `studio.css` rules stay until legs 07-08 migrate their consumers, then are deleted there.
  - The chip-list rules are copied into the banner as the owned `chip-list-editor`, `chip-list-input`, `ui-chip-remove` and so on. The `admin.css` copies stay until Flight 3, as recorded debt.
- **Catalogue:** rows for `tabs`, `groupTile`, `toolRow` and `chipList`. The toggle and dangerZone rows are updated, and `tabs` gets a retired-API row for `App.tabs`.
- **Contract tests:** `tests/browser/test_ui_tabs_contract.py`, `test_ui_tile_contract.py`, `test_ui_chip_list_contract.py`; extended `test_ui_choice_contract.py` (tristate) and `test_ui_editor_contract.py` (actions).
- **Allowance:** `tests/_ui_ownership_allowance.py` regenerated. Rows rise where newly owned classes (`chip-list-editor`, `chip-list-input`, `tablist`/`tab`/`tabpanel`, `chip`) count existing hand-built uses in `tools-form-helpers.js`, `tools-editor.js`, `mcp-server-editor.js`, `agent-editor.js`, `tools-grid.js`, `admin.css` and `studio.css`. **Each rise is listed with its reason in the flight log**: an expected bump, Flight 1 leg 05 precedent.

## Acceptance Criteria
- [ ] **`App.ui.tabs(opts)`**
  - Options: `{label, items:[{id, label, testid}], initial, onBeforeChange(id), onChange(id), idPrefix, panelClass}`.
  - Renders `div[role=tablist].tablist[aria-label]` with one `button[role=tab].tab` per item (id, `aria-controls`, `aria-selected`, roving `tabindex`, `data-tab-id`, optional testid), and a sibling `div.tabpanels` holding one `div[role=tabpanel].tabpanel` per item (`aria-labelledby`, `hidden` when inactive, `data-tab-id`).
  - Returns `{el, tablist, panels, select(id), selected(), panel(id), destroy()}`. `el` wraps both parts, unless `opts.split` asks for the tablist and panels separately.
  - Keyboard matches `js/tabs.js` exactly: arrows move focus, Home/End, Enter/Space/click select, and an `onBeforeChange` veto keeps the current tab.
  - The DOM, classes and computed styles equal today's agent-editor tablist. A contract case compares computed `padding`, `font-size`, `border-bottom` and colours against the legacy markup in the harness.
  - Role structure: tablist > tab elements, each tab `aria-controls` a panel that is `aria-labelledby` it.
- [ ] **`App.ui.groupTile(opts)`**
  - Options: `{name, count (text, e.g. "3 / 4 enabled"), chips:[text], actions:[node], subtitle, master:{label (aria-label), state:'on'|'off'|'mixed', onChange(nextChecked), disabled, testid}, toolCount (number shown in the expand button; or `toolLabel` text when unknown, e.g. "Tools"), expanded, onExpand(expanded), onFirstExpand(body), testid, dataset}`.
  - Renders `div.ui-group-tile`:
    - row 1: the master `App.ui.toggle({tristate:true})`, `span.ui-group-tile-name`, the count chip and extra chips (`span.ui-group-tile-chip`), then the actions;
    - optional `div.ui-group-tile-subtitle`;
    - `button.ui-group-tile-expand[aria-expanded]` with "<strong>N</strong> tools" (or "1 tool", or `toolLabel`) and the chevron;
    - `div.ui-group-tile-body[hidden]`.
  - `onFirstExpand(body)` fires once, on the first expand.
  - Returns `{el, body, setCount(text), setMaster(state), setToolCount(n|label), setExpanded(bool), isExpanded(), setSubtitle(text|node|null), destroy}`.
  - The look equals the canonical canvas board: the tile, name, chip and expand button computed styles equal the legacy `.tools-category-tile` markup in the harness (a contract case). The switch is the library switch (36×20).
- [ ] **`App.ui.toolRow(opts)`**
  - Options: `{name, description, checked, disabled, strike, onChange(checked), title, testid, dataset, disclosure:{label:'Overrides', onFirstOpen(body), open}}`.
  - Without `disclosure`: `label.ui-tool-row` holding `App.ui.checkbox`-equivalent markup (the `checkbox-primary` input), the mono name and " — " plus the description (truncated to 100 characters plus "…", full text in `title`).
  - With `disclosure`: `details.ui-tool-row` with `summary` containing the label face and `span.ui-tool-row-affordance` ("Overrides ▸"). `onFirstOpen(body)` fires once. A click on the checkbox toggles it without toggling the details (today's behaviour; check `tools-tab.js` for how it stops propagation).
  - Returns `{el, input, body (disclosure only), setChecked, setDisabled, setOpen, destroy}`.
  - The summary has a visible `:focus-visible` ring (Flight 1 DD8: disclosures).
  - Computed styles equal the legacy `.tool-tile` and `.mcp-tool-toggle-label` markup (a contract case for each). Role structure: no interactive element nested inside another interactive element except the native `summary` > `label` > `input` pattern that exists today. Flag it in the flight log if Playwright's accessibility snapshot shows a problem.
- [ ] **`App.ui.chipList(opts)`**
  - Options: `{label, values:[string], locked:[string], placeholder ('Add entry…'), onChange(values), testid, inputId, dataset, className}`.
  - Renders `div.chip-list-editor` with locked chips (`span.chip[data-locked]`, `aria-label "<v> (locked by operator)"`, no remove), editable chips (`span.chip` plus `button.ui-chip-remove[aria-label "Remove <v>"]` "×"), and `input.chip-list-input` (`aria-label "Add entry"`). Enter or comma adds a value; Backspace on an empty input removes the last editable chip (copy today's `tools-form-helpers.js` behaviour exactly).
  - Returns `{el, input, values(), setValues(values, locked), setError(bool), destroy}`.
  - The remove "×" is `--fg-secondary`, turning `--status-danger` on `:hover` and `:focus-visible` (canvas, approved). The other computed styles equal the legacy studio chip-list markup.
  - It is owned, so the `.chip-list-editor` rules land in its banner. The admin and studio copies stay as recorded debt until their consumers migrate.
- [ ] **`App.ui.toggle` gains `tristate: true`:**
  - `role=switch` is not set, so the control keeps native checkbox semantics in every state;
  - `setIndeterminate(bool)` is added, and `setChecked` clears the indeterminate state;
  - `:indeterminate + .ui-toggle-track` renders the accent-translucent track with the accent thumb at `translateX(8px)`;
  - there is a forced-colors rule;
  - the contract test checks `getByRole('checkbox')`, and the mixed state appears as `aria-checked="mixed"` in Chromium's accessibility tree (or `indeterminate === true`).

  Non-tristate toggles are unchanged.
- [ ] **`App.ui.dangerZone` gains `actions: [{label, testid, confirmLabel, beforeArm, onConfirm, icon}]`.** It renders one delete-style button per action, in order. `action` (singular) is the one-item form and stays. Returns `{el, buttons:[…], button (the first), setNotice, setDisabled(bool, index?)}`.
- [ ] **DD11 size assertions** in the contract tests:
  - all tabs are equal height;
  - the group tile's header actions (a small Refresh button) are 24px tall;
  - a chip in the chip list is 2px 8px with a body-sm font;
  - the tool-row summary has the legacy height;
  - the danger-zone buttons have equal height.
- [ ] **Catalogue rows** with owned classes, including a retired-API row for `App.tabs`: `api:App.tabs(` is added to the reuse check's retired-API list and counted. The ownership and sink checks pass with the regenerated allowance. Rises are listed in the flight log with reasons.
- [ ] **Gates:**
  - `make test-unit`;
  - the static guards (`test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`), ownership and inventory checks;
  - the contracts lane with `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1`;
  - the `agents` and `settings` lanes under netns, to show the existing tabs and tools grid are unchanged.
- [ ] **Docs:** `the_one/agents.md` "Control library" describes the six controls.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_index_asset_cache_busting.py -x -q`; `make test-unit`.
- `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts -x --timeout 90` (background, explicit timeout), then `--lane agents` and `--lane settings` under netns.

## Implementation Guidance
1. Read `js/tabs.js`, `tools-tab.js:95-320`, `mcps-tab.js:113-310,506-558`, `tools-form-helpers.js` (the chip-list builders about `:313-447`) and the CSS citations above. Reproduce, don't redesign.
2. Build `tabs` first (it replaces a whole module's behaviour), then `toggle` tristate, `groupTile`, `toolRow`, `chipList`, and dangerZone `actions`.
3. For each control, write the legacy-markup comparison contract case first: mount today's markup and the factory's output side by side in the harness with the studio CSS loaded, and compare computed styles.
4. Catalogue, allowance regeneration (the reasons in the log), docs.

## Edge Cases
- **The harness loads `studio.css`**, so legacy comparisons see the `.area-studio`-scoped rules only if the harness root has `class="area-studio"`. Mount the comparisons inside such a wrapper.
- **`App.tabs` callers** (`agent-editor.js`, `tools-grid.js`, `studio.js`) are not changed in this leg.
- **The tristate master and the `onChange` cycle:** clicking a mixed master turns everything on (today's behaviour: check `tools-tab.js:159-165`).
- **A long tool name or description** in a row ellipsises; it does not wrap.

## Files Affected
- `the_one/interfaces/web/static/js/ui/{tabs,tile,chip-list}.js` (new), `js/ui/choice.js`, `js/ui/editor.js`, `css/components.css`, `index.html`.
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md` (only for new testids).
- `tests/browser/test_ui_{tabs,tile,chip_list}_contract.py` (new), `test_ui_choice_contract.py`, `test_ui_editor_contract.py`.
- `tests/test_index_asset_cache_busting.py`, `tests/_ui_ownership_allowance.py`, `tests/test_ui_ownership.py` (the retired-API list).
- `the_one/agents.md`.

## Citation Audit
- Checked at `9369fcc`: `js/tabs.js:1-90` (the API and behaviour), `js/ui/editor.js:212-260` (single `action`).
- The CSS line ranges come from the planning extraction (`dbcd458`, files unchanged since). Re-locate by selector after leg 03.

## Design Review Addenda (2026-10-21)
These are binding and take precedence over the criteria above where they differ.

**The legacy comparison recipe:**
- `load_harness` loads every CSS file, but `#harness-root` carries no area class. Each comparison test hand-writes today's legacy markup; the area renderers are not loadable in the harness.
- Base rules are compared in the neutral root. Area-scoped rules are compared inside one explicit wrapper per test: `<div class="area-studio">` for tiles, rows and the agent tablist, and `<div class="area-admin"><div class="settings-list">` for the admin tablist. The test names the wrapper it uses.
- The comparison covers a fixed property list, not every computed style: padding, margin, font-size, font-weight, font-family, line-height, border (width, style, colour), border-radius, background-color, color, height, gap and display.

**Tabs:**
- Keep manual activation: arrows move focus only, and `tabindex` is unchanged until the user commits.
- Keep `data-tab-id` on both the tab and its panel.
- The `.tablist`, `.tab` and `.tabpanel` rules move into the tabs banner in the **same `@layer components`**, with unchanged declarations.
- The wrapper `el` gets the class `ui-tabs` with `display:flex; flex-direction:column; flex:1; min-height:0`, so it reproduces today's flex column. `opts.split` returns `{tablist, panels}` unwrapped, for hosts that place them separately.
- `panelClass` adds an extra class to each panel. `div.tabpanels` carries no padding.
- A keyboard-parity contract test drives the legacy `App.tabs` and `App.ui.tabs` with the same key sequence and compares the results: arrows, wrap-around, Home/End, Enter/Space/click, and an `onBeforeChange` veto.

**Chip list: copy today's behaviour exactly.** "Codify, not redesign": `tools-form-helpers.js` is the spec.
- Enter, comma and Tab on a non-empty input commit; Tab on an empty input moves focus on.
- A paste containing a comma splits and adds.
- Duplicates are ignored.
- Backspace on an empty input removes the nearest editable chip before the input's DOM position.
- Clicking a chip body moves the input before that chip.
- An empty commit clears the input without `onChange`.
- A `validate(value) → true | false | string` option mirrors today's `onChipAttempt` accept/reject hook.
- `onChange(values)` passes the values array; consumers may ignore it.

Markup and styling:
- The remove button is `button.ui-chip-remove` with the text "×", inside the chip as today, so a chip's `textContent` shape is unchanged for unmigrated readers (`readChipListValue` strips the trailing "×").
- The legacy `.chip-remove` rule (`components.css:544-553`) is untouched.
- `.chip-list-editor .chip` reproduces the admin/studio override (`2px 8px`, body-sm, gap 4px, radius `--space-1`), so the DD11 assertion compares against that, not the base `.chip`.
- `dataset` carries `data-field`, `data-field-type="array"`, `data-marker` and `data-tool-override-*`.

**`chip` is already owned** (the catalogue `chip` row). The newly owned classes are `chip-list-editor`, `chip-list-input`, `ui-chip-remove`, `tablist`, `tab`, `tabpanel`, `tabpanels` and the `ui-*` families.
- Because `tab`, `tablist` and `tabpanel` are common tokens, the regenerated allowance may count them in several files.
- Do not predict the numbers. The flight log lists each file/key delta with its reason, and a tokenizer false positive is a bug to fix, not allowance.

**Tristate toggle:**
- Assert `.indeterminate === true` in both engines, and the accessibility snapshot (`checkbox [checked=mixed]`) in Chromium only.
- A user click on a mixed master gives `checked=true` (native behaviour) and calls `master.onChange(true)`.
- `setMaster`/`setChecked`/`setIndeterminate` are silent: they fire no `onChange`.
- `groupTile` never changes its children itself; the consumer does.
- Before relying on it, confirm by grep that no test or consumer finds the master by `input[role=switch]`.

**Tool row:**
- The `<summary><label><input>` nesting relies on the HTML rule that activating an interactive descendant of `summary` does not toggle the `<details>`. No `stopPropagation` is needed; that is today's mechanism. `onFirstOpen` uses the `toggle` event.
- A contract test, in **both engines**, checks four interactions:
  - Space on the focused checkbox toggles only the checkbox;
  - Enter on the summary toggles only the details;
  - a click on the label text toggles only the checkbox;
  - a click on the affordance toggles only the details.

  Record any WebKit difference in the flight log; it is the main engine risk.
- `disabled` omits the disclosure and affordance, adds `title` ("Disabled by operator") and the strike-through, as today.
- A `note` option adds the extra description span used by `current_time` (`data-testid="time-tool-note"`).

**Danger zone `actions`:**
- Each action has its own `beforeArm`. `icon` defaults to `trash`.
- The notice sits after the last button.
- `setDisabled(bool, index?)` applies to all buttons, or to the one at `index`.

**Other requirements:**
- **The `App.tabs` retired-API row** needs a regex entry in `tests/test_ui_ownership.py` (beside the others, with the same `(?<![\w$.])` lookbehind), plus fixture counts in `test_retired_api_calls_count_in_code_only`.
- **Script order:** `tabs.js`, `tile.js` and `chip-list.js` go after `core.js`, `button.js` and `choice.js` in `index.html`, and the pin rises by 3.
- **Group tile tests** cover "1 tool" and the `toolLabel` (unknown count) case.
- **The Refresh size:** verify that `App.ui.button({size:'sm'})` is 24px tall with 10px text and a 14px icon (`components.css` `.btn-sm`: `height:24px; padding:0 8px; font-size:tiny`). If the icon is not 14px in an `sm` text button, fix it in `button.js`/CSS in this leg and add it to Files Affected.
- **Docs** note the intentional duplicates (the `admin.css`/`studio.css` chip-list and tile copies) that Flights 3-4 remove.
- **Leg size:** kept as one leg (the reviewer rated the split low-priority). The guidance order (tabs, tristate, dangerZone; then groupTile, toolRow, chipList) lets the Developer regenerate the allowance in two explained steps.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
