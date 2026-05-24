# Leg: discoverable-dropdown-component

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Ship the shared frontend dropdown component (`App.studio.discoverableDropdown(opts) → DOMElement`) that L6a/L6b will substitute into the allowlist + routing-rules editors. The component is a combobox: typeahead `<input>` + virtualized results panel + grouped sections + chip-list selected-values strip + Refresh button + stale-entry rendering. Extend the connector-form-registry's `optionalFns` array to n=5 by adding `renderDiscoverableDropdown` (flat-array shape preserved per F2 debrief operator decision). Add browser tests pinning the component contract.

## Context

- L4 landed: `GET /api/connector-accounts/{id}/discoverable-entities` and `POST .../refresh` endpoints, response shape `{entities: {peers, channels, groups, roles}, fetched_at, stale_seconds}` with each entity carrying `{id, label, group, metadata, stale}`. L5 consumes this API.
- **Design Decision — dropdown UI shape** (flight.md): combobox with grouped sections + typeahead + virtualization >100 + paged fetch >1000.
- **Design Decision — flat optionalFns** (flight.md): F2 debrief flagged n=5 as the evaluation point for restructuring `optionalFns` to an object map. Operator opted to keep the flat array — the 5th hook has the same function-if-present signature as the existing four.
- **Design Decision — opts shape** (flight.md): `{axis, accountId, currentValues, onChange, vocab}`. The component is axis-aware (which axis it filters for: `'peers'` / `'channels'` / `'groups'` / `'roles'`), account-scoped, and pre-populated with currently-selected values rendered as chips below the input.
- **Design Decision — registry-entry optional hook signature widens to 5 params** (this leg's resolution to cycle-1 self-contradiction): per-type entries opt in by exposing `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange) → HTMLElement | null`. The 5th param `onChange: function(newValues: string[]) → void` carries the change-event callback that L6 wires to the editor's collect-state machinery. Discord's entry implements it (delegates to the shared component via the explicit bridge code shown in Outputs below). Stub doesn't. L6's consumer surface consults the registry-entry hook; if null OR if no entry has the hook, falls back to the existing chip-list editor. The flight.md Design Decision §7 originally said 4 params — this leg widens it; note in flight-log under Decisions / drift.
- **Codebase recon (verified at design review)**:
  - `connector-form-registry.js:98` declares `var optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection'];` — the 4-item flat array.
  - `connector-form-registry.js:50-108` `_validateEntry` validates: required fns present + callable; reservedConfigKeys is array; **each name in `optionalFns` MUST be a function IF present** (lines 99-107).
  - `connector-form-registry.js:128-131` exposes `window.App.studio.connectorFormRegistry = {register, get}`.
  - `connector-form-discord.js:27+` is the IIFE template for the Discord per-type entry; line ~690 the `window.App.studio.connectorFormDiscord` namespace exposure.
  - `index.html:46-61` script loading order: `connector-form-registry.js` (L57) → `connector-form-discord.js` (L58) → `connector-vocabulary.js` (L59) → `connector-account-editor.js` (L60) → `studio.js` (L61). The new `discoverable-dropdown.js` slots between `connector-vocabulary.js` and `connector-account-editor.js` (so the editor can reference it; the dropdown can read vocab).
  - All studio JS uses ES5 IIFE pattern: `(function() { 'use strict'; ... })()`.
  - Studio CSS lives at `static/css/studio.css`. Hand-rolled class naming; no per-component files. The `.field-select` / `.chip-list-editor` / `.chip` precedents (e.g. studio.css ~L45-68 for select; chip-list classes elsewhere) provide the visual posture; the new dropdown classes inherit color tokens via CSS variables (`--accent`, `--surface`, `--border`).
  - Browser test pattern: `tests/browser/test_connector_form_registry.py` uses `page.evaluate()` for JS-contract probes. `tests/browser/test_connector_test_connection_button.py` is the example for `data-testid` + Playwright `expect` real-form tests.

## Inputs

- L4 has landed: `_get_account_cache_snapshot` + the two API endpoints are callable.
- `connector-form-registry.js` exists with 4-element `optionalFns`.
- `connector-form-discord.js` exists with the Discord per-type entry.
- `connector-account-editor.js` exists with `renderAllowlistSection` (L1774) + `renderRoutingRulesSection` (L2041) — UNTOUCHED by this leg (L6 owns the consumer integration).
- `index.html` loads scripts sequentially in the listed order.
- `studio.css` exists with form/select/chip-list precedent classes.

## Outputs

- **NEW file** `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` (~400-700 LOC; pause + extract virtualization helper if >700 per the flight Adaptation Criteria):
  - IIFE wrapper per project convention.
  - Public API: `App.studio.discoverableDropdown(opts) → HTMLElement` where `opts = {axis: 'peers'|'channels'|'groups'|'roles', accountId: string, currentValues: string[], onChange: function(newValues: string[]) → void, vocab: object}`.
  - Component DOM structure:
    ```
    <div class="discoverable-dropdown" data-axis="{axis}" data-account-id="{accountId}">
      <div class="discoverable-dropdown-input-row">
        <input type="text" class="discoverable-dropdown-input"
               role="combobox" aria-autocomplete="list" aria-expanded="false"
               aria-haspopup="listbox" aria-controls="dd-menu-{axis}-{accountId}"
               aria-activedescendant=""
               id="dd-input-{axis}-{accountId}"
               data-testid="discoverable-dropdown-input-{axis}"
               placeholder="{derived from vocab — see Behavior below}">
        <button type="button" class="discoverable-dropdown-refresh"
                data-testid="discoverable-dropdown-refresh-{axis}"
                aria-label="Refresh">↻</button>
      </div>
      <div class="discoverable-dropdown-menu" role="listbox"
           id="dd-menu-{axis}-{accountId}"
           data-testid="discoverable-dropdown-menu-{axis}" hidden>
        <!-- Grouped <div class="discoverable-dropdown-group"> sections with
             <div class="discoverable-dropdown-item" role="option"
                  id="dd-item-{axis}-{itemId}"
                  aria-selected="{true if id in currentValues, else false}" ...>
             entries. ArrowDown/Up updates the input's aria-activedescendant
             to the focused item's id. -->
      </div>
      <div class="chip-list-editor discoverable-dropdown-chips"
           role="group" aria-label="Selected entries"
           data-testid="discoverable-dropdown-chips-{axis}">
        <!-- Per-currentValue: <span class="chip" data-id="..."> {label} <button .chip-remove>×</button> </span>.
             Reuses the existing `.chip-list-editor` precedent (admin.css:388-433);
             chip + chip-remove styling inherits automatically. NO text input
             child (the chips strip is read-only here; the dropdown's <input>
             is the data-entry surface). -->
      </div>
      <div class="discoverable-dropdown-status" data-testid="discoverable-dropdown-status-{axis}" aria-live="polite">
        <!-- Status messages: "Loading…", "No matches", "Bot can no longer see this entity", error messages -->
      </div>
    </div>
    ```
  - **Placeholder derivation from vocab**: vocab carries singular axis names (`vocab.peer`, `vocab.channel`, `vocab.group`, `vocab.role`) — verified at `connector-vocabulary.js:46-62`. There is NO `vocab.placeholder` field. The component derives the placeholder internally: `"Add " + vocab[axisSingular] + "…"` where `axisSingular` maps `peers → peer`, `channels → channel`, `groups → group`, `roles → role`. F1 L6 vocabulary discipline preserved (the substrate vocab tokens carry the platform-specific labels; the component renders them).
  - Behavior:
    - **On mount**: triggers a GET `/api/connector-accounts/{accountId}/discoverable-entities`. While loading, the status line shows "Loading…" and the input is disabled. On success, populates the menu data from the response's selected axis. On 404 with the cold-pre-probe-hint, the status line shows the hint string AND the menu is hidden (operator must run Test Connection); on 503, shows "This connector type does not expose discoverable entities" (this is the fallback failure; in normal L6 flow, the registry-entry-hook fallback to chip-list prevents this branch from reaching the operator).
    - **Typeahead filter**: input keyup → filter the menu items by case-insensitive substring on `label`. Hidden items get `hidden` attribute toggled; group sections with no visible items are also hidden.
    - **Naive render — no scroll-based virtualization** (this leg's resolution to a cycle-1 LOC-budget catch): for axes with ≤ 1000 entries, ALL items render as DOM nodes with `hidden`-attribute toggling for the typeahead filter. Browser DOM handles 1000 nodes with `hidden` cheaply. **NO scrollTop-based windowed render in L5** — eliminates ~200 LOC of virtualization code and the fixed-item-height assumption, brings L5 firmly under the 700-LOC ceiling. The >1000-entries hint (next bullet) gates the upper bound. The flight Adaptation Criteria's "virtualization >100" language is satisfied by the >1000-entry type-to-filter gate; if F8 HAT surfaces UX friction on 200-500-entry guilds, a scroll-virt helper is added in a followup leg.
    - **>1000 entries hint**: when the axis has > 1000 entries, show "Filter to narrow results" hint until the operator types ≥ 2 chars in the input. The menu is hidden in this initial state to avoid rendering 1000+ DOM nodes. Once ≥ 2 chars typed, render the matching-filter subset (subset is < 1000 by construction in practice — Discord guilds with > 1000 members have rare typeahead matches that exceed 1000).
    - **Grouped sections**: items with the same `entity.group` value cluster under a `<div class="discoverable-dropdown-group" data-group-key="{group}">` with a group header `<div class="discoverable-dropdown-group-header">{group-label}</div>`. The group-label is computed from the entity's group field (e.g., `guild:123` → look up the matching group entity from another axis; the component receives the full DiscoverableEntities response from the API and uses the cross-axis lookup).
    - **Chip-list selected values**: currentValues renders as chips below the input. Each chip has an × button that removes the value and fires `onChange(newValues)`. Selecting a menu item adds its id to currentValues; clicking the same item again is a no-op (already in chips).
    - **Stale-entry rendering**: entities with `entity.stale === true` get `data-stale="true"` on their list item AND on any matching chip. CSS applies strikethrough + tooltip "Bot can no longer see this entity."
    - **Refresh button**: POSTs `/api/connector-accounts/{accountId}/discoverable-entities/refresh`, repopulates the menu data, fires no `onChange` (selected values are unchanged). Shows "Refreshing…" in the status line. **Race protection via AbortController**: the component maintains a single `AbortController` per in-flight fetch; if Refresh is clicked while a GET is in flight, the in-flight fetch is aborted before the POST fires. Last-response wins is enforced by sequence ordering. Eliminates the brief "fresh → stale" flicker possibility from cycle-1.
    - **Unknown-id chip fallback**: if `currentValues` contains an id that does NOT appear in `state.entities` for the axis (e.g., operator pasted an id from an external source, or the platform deleted the entity before the bot last saw it), the chip renders with the bare id as its label AND a tooltip "label unknown — try Refresh." NOT a regression vs M10's free-form chip-list — the operator's data is preserved; the only UX change is the label fallback. F8 HAT may surface this as a follow-up; for L5 it's the accepted shape.
    - **Keyboard navigation** (WCAG combobox APG):
      - ArrowDown/ArrowUp: navigate items in the menu; updates the input's `aria-activedescendant` attribute to the focused item's `id` so screen readers announce navigation.
      - Enter: select the focused item (adds to chips); fires `onChange(newValues)`.
      - Escape: close the menu (sets `aria-expanded="false"` on input; hides the menu element).
      - Tab: commit focus exit (the menu hides if it was open).
      - Focus on input: opens the menu (if not in >1000-entries-hint state).
    - **Error handling**: GET / POST failures (network error, 5xx) → status line "Couldn't load entities; try Refresh." Refresh button remains active. Console logs the error per the project's existing logging posture.
  - The component caches the per-axis API response within the component instance — the GET is fired once on mount and on Refresh button click; typeahead filtering operates on the cached data, NOT a re-fetch.
- **Modified file** `connector-form-registry.js`:
  - `optionalFns` extended to 5 elements: `['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']`. The flat-array shape is preserved per F2 debrief operator decision (no object-map restructure at n=5).
  - The top-comment block (around L1-40) is extended with a one-paragraph note that `renderDiscoverableDropdown(account, axis, currentValues, vocab) → HTMLElement | null` is the n=5 optional hook for live-data dropdowns shipped by F3. Format matches the existing optional-hook documentation paragraphs.
  - **No other changes** to the registry. The validator's "must be a function IF present" check (lines 99-107) naturally accepts the new entry.
- **Modified file** `connector-form-discord.js`:
  - Add a `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange) → HTMLElement` method to the Discord per-type entry's registered object. The method is a direct bridge to the shared component — exact body:
    ```javascript
    renderDiscoverableDropdown: function(account, axis, currentValues, vocab, onChange) {
      return App.studio.discoverableDropdown({
        axis: axis,
        accountId: account.id,
        currentValues: currentValues,
        onChange: onChange,
        vocab: vocab,
      });
    },
    ```
  - The bridge handles the positional-to-opts translation explicitly. No internal logic; reusable shape for future per-type entries (Slack/Matrix when they add the hook).
  - **No tests** in this leg for `connector-form-discord.js`'s new method; L6's consumer-integration tests + the new browser tests for the component cover the path. (A small "Discord entry exposes the method" regression check is added — see Tests below.)
- **Modified file** `the_one/agents.md` (small update to keep codification current at n=5):
  - The `optional-registry-entry-hook` convention's citation block (around L180-185) currently cites n=3 from M11 F1 with three named hooks; F2 L4 added a 4th (`renderDirectiveSection`) without updating the citation. L5 adds the 5th. Update the citation to read: "Citations (n=5 from M11 F1+F2+F3): `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js:_validateEntry` — the `optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']` array; each name is an optional entry-shape hook. The per-name validation is "must be a function IF present" — absent without error." Keep the existing per-hook-source bullets intact; add a sibling bullet for the new hook citing F3 L5. This keeps the codification current per `flight-spec-dom-order-audit` (L1-codified) — the convention's exemplar should match the actual code.
- **NEW file** `tests/browser/test_flow_studio_connector_discoverable_dropdown.py`:
  - Mount the component in isolation via `page.evaluate()` injecting a small test harness DOM + calling `App.studio.discoverableDropdown({axis:'channels', accountId:'fake-id', currentValues:[], onChange: function(v){ window._lastOnChange = v; }, vocab: {placeholder: 'Add channel…'}})`.
  - Use `page.route()` to fulfill the GET endpoint with a stubbed `_DiscoverableEntitiesResponse`-shaped payload (3 channels: `#general` fresh, `#random` fresh, `#deprecated` stale).
  - Tests:
    - `test_dropdown_populates_from_api_response` — mount; assert the menu items match the stubbed payload (3 items rendered, group sections present).
    - `test_dropdown_typeahead_filters_by_label_substring` — mount; type "gen" into input; assert only `#general` is visible (other items hidden).
    - `test_dropdown_select_item_fires_onChange_with_new_value` — mount; click `#general` item; assert `window._lastOnChange === ['<general-id>']`.
    - `test_dropdown_chip_remove_fires_onChange_with_value_dropped` — mount with `currentValues: ['<general-id>']`; click the chip's × button; assert `window._lastOnChange === []`.
    - `test_dropdown_stale_entry_renders_with_data_stale_attribute` — mount; assert `#deprecated`'s DOM has `data-stale="true"`.
    - `test_dropdown_refresh_button_posts_refresh_endpoint` — mount; click Refresh; assert the POST hit the right URL.
    - `test_dropdown_renders_pre_probe_hint_when_api_404` — mount with a route that fulfills 404 + pre-probe hint detail; assert the status line shows the hint and the menu is hidden.
- **NEW file** `tests/browser/test_connector_form_registry_optionalfns_n5.py` (or extension of existing `tests/browser/test_connector_form_registry.py`):
  - Single test: `test_registry_optionalFns_includes_renderDiscoverableDropdown` — `page.evaluate('App.studio.connectorFormRegistry')` returns an object whose internal optionalFns list (probed via `_validateEntry` behavior or a direct accessor) includes the new name. Test approach: register a stub entry with `renderDiscoverableDropdown: function(){}` — registration succeeds. Register a stub entry with `renderDiscoverableDropdown: "not-a-function"` — registration fails with a meaningful error. (The validator's "must be a function IF present" check is the regression contract.)
- **Modified file** `static/css/studio.css`: add new combobox classes per the DOM structure above. Classes use existing color tokens (`--accent`, `--surface`, `--border`, `--fg`, `--fg-secondary`, `--fg-muted` (verified against `tokens.css:53-69` — there is no `--text-primary`/`--text-secondary`; the project's typography tokens are `--fg`-prefixed). Also reuse `--glass-border`, `--bezel-shadow-inset`, `--panel-radius-sm`, `--accent-translucent`, `--accent-glow` from the `.chip-list-editor` precedent in `admin.css:388-433`). Stale-entry styling: `[data-stale="true"] { text-decoration: line-through; opacity: 0.6; }`. Estimate: ~80-150 LOC of CSS.
- **Modified file** `the_one/interfaces/web/static/index.html` (or wherever the Studio area template lives — see codebase recon): add `<script src="/static/js/areas/studio/discoverable-dropdown.js"></script>` between the `connector-vocabulary.js` and `connector-account-editor.js` script tags.

## Acceptance Criteria

### Component file

- [x] New file `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` exists with the IIFE wrapper convention.
- [x] The file exposes `window.App.studio.discoverableDropdown` as a function accepting `opts = {axis, accountId, currentValues, onChange, vocab}` and returning an `HTMLElement`.
- [x] The returned element has the DOM structure documented in Outputs above (input, menu, chips, status, refresh button) with `data-testid` attributes for browser testing.
- [x] On mount, the component fires `GET /api/connector-accounts/{accountId}/discoverable-entities`; status line shows "Loading…" until the response arrives.
- [x] On 200, the menu populates from the response's selected axis; entries with the same `group` cluster under a group header.
- [x] On 404 with the pre-probe hint detail, the status line shows the hint string and the menu stays hidden.
- [x] On 503, the status line shows "This connector type does not expose discoverable entities."
- [x] Typeahead filter: typing in the input filters menu items by case-insensitive substring on `label`; empty groups hide; group-headers with no visible items hide.
- [x] **No scroll-based virtualization in L5** — naive render of all axis entries up to 1000 (using `hidden` attribute for typeahead filter); >1000 triggers the type-to-filter gate.
- [x] >1000-entries hint: when the axis has > 1000 entries, the menu stays hidden until the operator types ≥ 2 chars; the status line shows "Filter to narrow results." Once ≥ 2 chars typed, render the matching-filter subset.
- [x] Selecting an item adds its id to the internal currentValues + renders a new chip + fires `onChange(newValues)`. Selecting the same item again is a no-op.
- [x] Removing a chip via its × button removes the id from currentValues + fires `onChange(newValues)`.
- [x] Stale entries (those with `entity.stale === true` from the API response) render with `data-stale="true"` attribute on the item AND on any matching chip; CSS applies strikethrough + tooltip.
- [x] Refresh button POSTs `/api/connector-accounts/{accountId}/discoverable-entities/refresh`, repopulates the menu data, leaves currentValues + chips intact; status line shows "Refreshing…" during the call.
- [x] Keyboard navigation per WCAG combobox APG: ArrowDown/Up navigates AND updates the input's `aria-activedescendant` attribute to the focused item's `id`; Enter selects; Escape closes (sets `aria-expanded="false"`); Tab commits exit.
- [x] ARIA compliance: input has `role="combobox"`, `aria-autocomplete="list"`, `aria-expanded` (reflects menu visibility), `aria-haspopup="listbox"`, `aria-controls="dd-menu-{axis}-{accountId}"`, `aria-activedescendant` (updated on ArrowUp/Down). Menu has `role="listbox"` with matching `id`. Each item has `role="option"`, `id="dd-item-{axis}-{itemId}"`, `aria-selected` (true if id in currentValues). Chips wrapper has `role="group"` with `aria-label="Selected entries"`.
- [x] AbortController-based race protection: Refresh-while-loading aborts the in-flight GET before the POST fires; eliminates the brief "fresh → stale" flicker.
- [x] Unknown-id chip fallback: chips for ids not in `state.entities` render with the bare id as label + a "label unknown — try Refresh" tooltip.
- [x] GET / POST network errors → status line "Couldn't load entities; try Refresh"; Refresh button remains active; error logged to console.

### Registry extension

- [x] `connector-form-registry.js:optionalFns` extended to `['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']` — n=5; flat-array shape preserved.
- [x] The top-comment block documents `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange) → HTMLElement | null` as the n=5 optional hook for live-data dropdowns. **Signature has 5 params** (resolved at design — see Context: the L4 callback plumbing requires `onChange` to flow into the component).
- [x] No other changes to `connector-form-registry.js` (validator code path unchanged; `_validateEntry`'s "must be a function IF present" check accepts the new entry by name).

### Discord per-type entry

- [x] `connector-form-discord.js` exposes a new method `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange) → HTMLElement` on its registered entry. The method delegates to `App.studio.discoverableDropdown({axis, accountId: account.id, currentValues, onChange, vocab})` and returns the resulting element. Body is a direct positional-to-opts bridge (no internal logic).
- [x] After L5 lands, `App.studio.connectorFormRegistry.get('discord').renderDiscoverableDropdown` is a function (probed via `page.evaluate()` in the regression test).

### agents.md codification

- [x] `the_one/agents.md`'s `optional-registry-entry-hook` convention's Citation block updates to n=5: array literal `['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']` (matches the post-leg registry state); per-hook bullets include the new entry citing F3 L5.

### CSS

- [x] `static/css/studio.css` grows new classes covering the dropdown DOM structure. Classes use the existing token suite: `--accent`, `--surface`, `--border`, `--fg`, `--fg-secondary`, `--fg-muted` (verified against `tokens.css:53-69`); reuse `--glass-border`, `--bezel-shadow-inset`, `--panel-radius-sm`, `--accent-translucent`, `--accent-glow` from the `.chip-list-editor` precedent in `admin.css:388-433`. The chips wrapper inherits the existing `.chip-list-editor` styling (the leg adds the dropdown's wrapper as `class="chip-list-editor discoverable-dropdown-chips"` — both classes apply).
- [x] Stale-entry styling is scoped: `.discoverable-dropdown-item[data-stale="true"], .discoverable-dropdown .chip[data-stale="true"] { text-decoration: line-through; opacity: 0.6; }`. NOT the broad `[data-stale="true"]` selector.

### HTML / Script loading

- [x] `the_one/interfaces/web/static/index.html` (or the relevant Studio template) inserts `<script src="/static/js/areas/studio/discoverable-dropdown.js"></script>` between the `connector-vocabulary.js` and `connector-account-editor.js` script tags so the dropdown is available when the editor mounts.

### Tests

- [x] New file `tests/browser/test_flow_studio_connector_discoverable_dropdown.py` with the 7 tests enumerated in Outputs.
- [x] New test (file or extension) `test_registry_optionalFns_includes_renderDiscoverableDropdown` pinning the n=5 contract.
- [x] Existing tests pass byte-identically: `docker exec the-one pytest tests/browser/test_connector_form_registry.py tests/browser/test_flow_studio_connector_account_editor.py -x --timeout 60 -q -m browser` reports 0 failures.

### Cross-cutting

- [x] L6's allowlist + routing surfaces are NOT modified in this leg (L6a/L6b own those refactors).
- [x] `connector-account-editor.js` is NOT modified in this leg (other than possibly registering the dropdown component if L5 wants a smoke-load — defer to L6 if not needed).
- [x] Python API endpoints from L4 are NOT modified.
- [x] `git diff --stat` shows changes only in: the new component JS file, `connector-form-registry.js`, `connector-form-discord.js`, `static/css/studio.css`, `the_one/interfaces/web/static/index.html` (or equivalent), the two new test files, plus F3 sibling artifacts.

## Verification Steps

- `ls the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — file exists.
- `grep -n "App.studio.discoverableDropdown" the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — exports the function.
- `grep -n "renderDiscoverableDropdown" the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — appears in optionalFns array AND in the top-comment block.
- `grep -n "renderDiscoverableDropdown" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — appears in the Discord entry's method.
- `grep -n "discoverable-dropdown.js" the_one/interfaces/web/static/index.html` (or relevant template) — script tag present.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py -x --timeout 60 -q -m browser` — 7 tests pass.
- `docker exec the-one pytest tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser` — existing tests + the new optionalFns-n=5 test pass.
- Full studio browser suite: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_form_registry.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_discoverable_dropdown.py -x --timeout 60 -q -m browser` — 0 failures.
- LOC check: `wc -l the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — confirm ≤ 700 (flight.md ceiling). If > 700, PAUSE per flight Adaptation Criteria and tighten the implementation or extract a helper module.

## Implementation Guidance

1. **Read the current state** of `connector-form-registry.js` (full file ~135 LOC), `connector-form-discord.js` (full file ~700 LOC, focus on the entry registration and existing optional-hook implementations like `renderInviteSection` / `renderDirectiveSection`), `connector-vocabulary.js`, `studio.css` (the form/select/chip-list CSS regions), and `the_one/interfaces/web/static/index.html` (the Studio script loading block at L46-61).

2. **Create `discoverable-dropdown.js`** with the IIFE wrapper. Internal structure:
   - Private helpers: `_buildDOM(opts)` builds the static structure; `_fetchEntities(accountId)` does the GET; `_renderMenu(state)` re-renders the menu from state; `_renderChips(state)` re-renders the chips; `_applyTypeaheadFilter(input, state)` filters; `_handleKeyboard(event, state)` handles keyboard nav; `_handleRefresh(state)` POSTs.
   - State per instance: `{axis, accountId, currentValues, vocab, onChange, entities, fetched_at, stale_seconds, loading, error, filter, focusedItemIndex, menuOpen}`.
   - Mount: build DOM → return element → asynchronously fire fetch → on success, replace state.entities + re-render menu.

3. **Decide on the virtualization implementation** before writing. Two viable shapes:
   - **(a) Naive**: render ALL items as DOM nodes when entity count ≤ 1000. Use `hidden` attribute toggling for typeahead filtering. Simple; ~150 LOC; fine for the gleepglorp test guild.
   - **(b) Windowed**: compute visible index range from scrollTop; render only ≤ 50 items at a time. More complex; ~250 LOC. Required for axes with > 100 entries.
   - **Pick (a) for entities ≤ 100; (b) for entities > 100; >1000 entries trigger the "type to filter" hint, never render the menu items eagerly.** This is the size-based dispatch.

4. **Stale-entry rendering**: apply `setAttribute('data-stale', 'true')` on both the menu item AND any matching chip whose id is in `state.entities` axis with `stale: true`. CSS does the visual.

5. **CSS additions to `studio.css`**: Add a `/* Discoverable Dropdown (M11 F3 L5) */` section. Mirror the existing form-select + chip-list visual posture. Key classes per the DOM structure. Stale styling: `.discoverable-dropdown-item[data-stale="true"], .discoverable-dropdown .chip[data-stale="true"] { text-decoration: line-through; opacity: 0.6; }`.

6. **Update `connector-form-registry.js:98`** — extend `optionalFns` array to 5 elements. Update the top-comment to document the new hook (one new paragraph).

7. **Update `connector-form-discord.js`** — add `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange)` to the Discord entry's returned object. Body delegates to `App.studio.discoverableDropdown({axis, accountId: account.id, currentValues, onChange, vocab})` and returns the result.

8. **Update `the_one/interfaces/web/static/index.html`** (or wherever the Studio JS scripts are listed) — insert `<script src="/static/js/areas/studio/discoverable-dropdown.js"></script>` between the `connector-vocabulary.js` and `connector-account-editor.js` script tags.

9. **Write the browser tests** in `tests/browser/test_flow_studio_connector_discoverable_dropdown.py`. Use the `app_clean` fixture + `page.route()` to fulfill the API endpoints with stubbed payloads. Use `page.evaluate()` to mount the component in isolation (no need for the full editor context).

   **Test sequence** (critical — Playwright route registration must happen BEFORE page navigation): for each test:
   1. `page.route("**/api/connector-accounts/*/discoverable-entities", handle_get)` — register BEFORE the goto so the initial app load doesn't trigger a real backend call.
   2. `page.goto(app_clean)` and `page.wait_for_load_state("domcontentloaded")` — page loads; `App.studio.discoverableDropdown` is registered.
   3. `page.evaluate("""...mount component into a test harness div..."""))` — mounts the component; `_fetchEntities()` fires the GET which hits the pre-registered route.
   4. Assert DOM via Playwright `expect(page.locator("[data-testid='...']")).to_*(...)`.

   For each test, verify the relevant DOM/behavior via Playwright `expect(...)` locators with `data-testid`.

10. **Write the registry test** pinning n=5. Either extend `tests/browser/test_connector_form_registry.py` (single new test function) or create a new file. Test: register a stub entry with `renderDiscoverableDropdown: function() { return null; }` — registration succeeds; verify via `connectorFormRegistry.get(stub-type).renderDiscoverableDropdown !== undefined`. Register with `renderDiscoverableDropdown: "not-a-function"` — registration fails (validator rejects).

11. **Run tests**:
    - Component tests: `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py -x --timeout 60 -q -m browser`.
    - Registry test: `docker exec the-one pytest tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser`.
    - Sibling regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py -x --timeout 60 -q -m browser`.
    - Note: the leg-execution.md crew prompt's `-m browser` was discovered in L2; the project's pytest config defaults to deselecting browser tests.

12. **LOC check after writing**: `wc -l the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js`. Confirm ≤ 700 LOC (flight.md ceiling). If > 700, PAUSE per flight Adaptation Criteria — tighten the implementation OR extract a helper module (e.g., `discoverable-dropdown-filter.js` for typeahead) into a sibling module, and re-test.

13. **Sibling artifact bookkeeping**: check off L5 in `flight.md` (Checkpoints + Legs sections); append L5 entry to `flight-log.md` under `## Leg Progress`.

14. **Update leg status header** `ready → in-flight → landed`. Do NOT commit; do NOT signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`onChange` is the only mutation channel**: the component does NOT mutate `opts.currentValues` directly. It maintains an internal `state.currentValues` initialized from `opts.currentValues` and fires `onChange(newValues)` on every change. Callers (L6's editor) maintain their own state and re-render the component when needed (or pass an `onChange` that updates the editor's state without re-rendering the dropdown).
- **Multiple instances on the same page**: L6 will mount one dropdown per axis (4 dropdowns for the allowlist; more for routing-rules). Each instance is independent — the API GET is fired per-instance. If this becomes a perf concern, L6 can add a shared cache at the consumer layer; L5 does NOT introduce shared state.
- **Vocab object shape**: the `vocab` opts field carries platform-substituted labels (e.g., `vocab.placeholder = "Add user…"` for Discord peers, `"Add peer…"` for the generic substrate). The component reads vocab only for display strings, never for behavior decisions. F1 L6 vocabulary discipline.
- **Refresh button race**: AbortController-based protection (see Behavior bullet). The in-flight fetch is aborted before the POST refresh fires; eliminates the brief "fresh → stale" UI flicker possibility.
- **WCAG combobox role compliance**: see https://www.w3.org/WAI/ARIA/apg/patterns/combobox/. The component sets `role="combobox"` on the input, `aria-autocomplete="list"`, `aria-expanded` (true/false reflecting menu visibility), `aria-controls` pointing to the menu's id. The menu itself is `role="listbox"`; each item is `role="option"`. Keyboard nav follows the WCAG pattern.
- **Loading-state UX**: the input is disabled for the entire load window (no 100ms threshold — keeps implementation simple; perceived flicker on fast loads is acceptable UX). After load, the input is re-enabled and the menu opens on focus.
- **Empty axis from API**: if the API returns 200 with an empty axis (e.g., `peers: []`), the menu shows "No entries available." in the status line. Operator can still see chips from `currentValues`; chips whose id is not in the entities list render with bare-id labels per the unknown-id fallback (see Behavior).
- **L6 interaction order**: this leg ships the component; L6a wires it into the allowlist editor; L6b wires it into the routing-rules and per-agent overlay. L5 does NOT wire any consumer; the editor's chip-list code paths remain intact until L6 lands.
- **`atomic-leg-pattern` non-applicability**: L5 touches 7 files (1 new JS + 4 modified JS/CSS/HTML + 2 new tests). This is NOT the atomic-leg-pattern shape (no Pydantic/DB/codec/consumer crossing); it's "coherent surface" — the new component + registry hook + Discord entry method + script-tag wiring + CSS must all land together to avoid an intermediate state where the component is callable but not loadable.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — NEW; ~400-700 LOC.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — `optionalFns` extended; top-comment extended.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — `renderDiscoverableDropdown` method added to Discord entry.
- `the_one/interfaces/web/static/css/studio.css` — new combobox CSS classes; ~80-150 LOC.
- `the_one/interfaces/web/the_one/interfaces/web/static/index.html` (or relevant template — verify exact path) — script tag insertion.
- `tests/browser/test_flow_studio_connector_discoverable_dropdown.py` — NEW; 7 tests.
- `tests/browser/test_connector_form_registry.py` — 1 new test for n=5 contract (or new file).
- `missions/.../flight.md` — L5 checkpoint + leg checklist checked off.
- `missions/.../flight-log.md` — L5 leg-progress entry.
- `missions/.../legs/05-discoverable-dropdown-component.md` — this artifact's status header progresses.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Browser tests pass: `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser`
- [x] Sibling browser tests pass byte-identically: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py -x --timeout 60 -q -m browser`
- [x] LOC check on `discoverable-dropdown.js` — confirm ≤ 700 LOC OR document the deviation in flight-log per Adaptation Criteria
- [x] Update `flight-log.md` with L5 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L5 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F3 batches review + commit at flight end)
