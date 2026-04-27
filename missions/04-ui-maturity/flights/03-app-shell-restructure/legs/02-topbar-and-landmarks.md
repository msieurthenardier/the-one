# Leg: 02-topbar-and-landmarks

**Status**: completed
**Flight**: [App Shell Restructure](../flight.md)

## Objective

Replace the vertical `#app-nav` rail with a horizontal `#app-topbar` containing the app name on the left and a hamburger app picker on the right. Add semantic landmarks (`<header>` / `<nav>` / `<main>` / `<aside>` / `<h1>`) and a focus-revealed skip-link as the first focusable element. Reflow body layout from horizontal flex (rail | sidebar | content) to outer flex-column (topbar above) + inner flex-row (sidebar | content). Reuse the existing `--nav-*` palette island for chrome continuity; rename `--nav-w` (width) to `--topbar-h` (height).

## Context

This leg is the structural pivot of F3: every later leg builds on the new layout (leg 03 keyboard rebuild touches the picker dropdown; leg 04 hash routing dispatches into the new picker; leg 05 new-chat restructure inherits the new sidebar layout; leg 06 regenerates snapshots after the layout has settled).

Key carry-forward decisions from the flight spec and design-review rounds:

- **Top-bar replaces nav rail entirely**: `#app-nav` is removed; `#app-topbar` takes its place. App name (`<h1>` "the-one") on the left, hamburger app-picker `<button>` on the right.
- **App picker = popover/dropdown** with three keyboard-accessible buttons (Chat / Studio / Admin). Active option uses `--nav-fg-active` cyan and the `::before` left-border accent treatment ported from `.nav-item.active::before` (`base.css:38-47`).
- **Hamburger icon** = Lucide `menu` (3-line stack), pinned to `lucide-icons/lucide@v0.265.0`. Add as a one-line entry to `App.icons.menu` in `icons.js`.
- **Token migration**: `--nav-w: 48px` (rail width) → `--topbar-h: 48px` (top-bar height). Rename in BOTH `[data-theme="dark"]` and `[data-theme="light"]` blocks (`tokens.css:88`, `:176`). Keep the `--nav-bg` / `--nav-fg` / `--nav-border` / `--nav-fg-active` palette family — chrome continuity is intentional.
- **Layout reflow**: `body { display: flex; }` (current row) → `body { display: flex; flex-direction: column; }` with the topbar as the first child and an inner `<div class="app-shell-row">` (or `<main>` + `<aside>` wrapped — see semantic-landmark choice below) holding the sidebar+content row.
- **Semantic landmarks**: `<header>` wraps the topbar; `<nav aria-label="App areas">` wraps the picker (NOT the topbar — the topbar contains both the heading and the nav, and the heading is not navigation); `<aside aria-label="…">` wraps the sidebar (per-area label set by area code via `aside.setAttribute('aria-label', ...)` in `init`); `<main id="main-content">` wraps the content. The picker's `<nav>` element lives INSIDE the dropdown overlay (not on the picker button itself) so the implicit landmark only shows when the picker is open.
- **Skip-link** = `<a class="skip-link" href="#main-content">Skip to main content</a>` as the FIRST element after `<body>`, before the topbar. Style in `components.css` under `@layer components`: `position: absolute; top: -40px; left: 0;` then `:focus { top: 0; }`. Background `var(--accent)`, text `var(--fg-on-accent)`, padding to match topbar height.
  - **Hash-collision fix required**: `<a href="#main-content">` triggers `location.hash = '#main-content'`, which fires the `hashchange` listener in `app.js:82-84`. Currently that listener calls `switchTo(getHashArea())`, and `getHashArea()` returns `'chat'` for any unknown hash — so a skip-link click would force-reset the active area to chat. **Fix**: guard the `hashchange` listener to bail when the hash is not a registered area:
    ```javascript
    window.addEventListener('hashchange', function () {
      var hash = location.hash.replace('#', '');
      if (!areas[hash]) return;  // skip-link / non-area hashes — ignore
      switchTo(hash);
    });
    ```
    `getHashArea()` keeps its `|| 'chat'` fallback for the **initial** load only (DOMContentLoaded path). This also future-proofs leg 04 hash routing where `#chat/sessions/<id>` will need similar bail-or-parse logic in the listener.
- **App.theme.renderToggle compact mount**: leg 02 mounts a `'compact'` theme toggle in the topbar (right side, before the hamburger). This is the FIRST consumer of the compact variant landed in leg 01.
- **Visual snapshots WILL DRIFT** after this leg — the layout change is structural. Per flight spec, **DO NOT regenerate snapshot baselines in leg 02**; leg 06 handles all snapshot regeneration in one consolidated pass after legs 03-05 land. The leg 02 verification deselects `test_visual_snapshots.py` from the browser-test run; flow tests + smoke + new picker-keyboard tests must pass.

## Inputs

State that must exist before this leg runs:

- Branch `flight/03-app-shell-restructure` checked out; leg 01 landed (uncommitted per F3 batching).
- Working tree state: leg 01's modifications (8 markers, theme.js renderToggle, admin.js refactor, tokens.css sidebar swap, agents.md affordance vocabulary, 6 dark snapshots regenerated) are present uncommitted alongside the F3 flight artifacts.
- `App.theme.renderToggle(container, options)` available in `theme.js` with `'full'` and `'compact'` variants (landed in leg 01).
- `App.icons` loaded from `icons.js` (no `menu` icon yet — leg 02 adds it).
- Current `index.html` structure: `<div id="app-nav">` + `<div id="app-sidebar">` + `<div id="app-content">` as siblings under `<body>`, with `body { display: flex; }`.
- Current `app.js` `renderNav()` at lines 13-28 (renders `.nav-item` divs into `#app-nav`); `switchTo` at lines 30-75 (which uses `document.getElementById('app-nav')` indirectly via `.nav-item` querySelector at line 66).
- Current `base.css` `#app-nav` rules at lines 6-17, `.nav-item` rules at lines 18-47.
- Current `tokens.css`: `--nav-w: 48px` at line 88 (dark) and line 176 (light). All other `--nav-*` tokens defined in both blocks.

## Outputs

State that must exist after this leg completes:

### `index.html`
- `<a class="skip-link" href="#main-content">Skip to main content</a>` as the first body element (line ~18).
- `<header id="app-topbar"></header>` replacing the previous `<div id="app-nav"></div>`.
- An inner row container — either a wrapping `<div class="app-shell-row">` containing `<aside id="app-sidebar">` and `<main id="main-content">`, OR `<aside>` + `<main>` as direct flex-row siblings within an inner wrapper. Either is acceptable; the leg implementation chooses ONE and documents it in code comments.
- `id="app-sidebar"` on the `<aside>`, `id="app-content"` removed (replaced by `id="main-content"` on the `<main>` for skip-link target). Existing CSS rules using `#app-content` updated to `#main-content`.

### `tokens.css`
- `--nav-w: 48px;` removed from BOTH dark (line 88) and light (line 176) blocks.
- `--topbar-h: 48px;` added to BOTH blocks (same location — the "density-and-geometry" group).
- The `/* density-and-geometry */` group comment unchanged; the comment immediately above the new token reads: `/* topbar height — chrome strip across the top of the shell */`.
- All other `--nav-*` tokens (`--nav-bg`, `--nav-bg-active`, `--nav-border`, `--nav-fg`, `--nav-fg-hover`, `--nav-fg-active`) remain unchanged in both blocks. The chrome palette is reused by the topbar.

### `base.css`
- `#app-nav` selector + `.nav-item*` selectors fully removed (lines 6-47).
- `body { display: flex; }` (line 4) changed to `body { display: flex; flex-direction: column; }`.
- New `#app-topbar` rules: `height: var(--topbar-h); display: flex; align-items: center; justify-content: space-between; padding: 0 16px; background: var(--nav-bg); border-bottom: 1px solid var(--nav-border); flex-shrink: 0;`.
- New `.app-shell-row` (or equivalent wrapper) rule: `display: flex; flex: 1; min-height: 0; overflow: hidden;`.
- Existing `#app-sidebar` rules (lines 49-58) preserved EXCEPT: `flex-shrink: 0` already set, no change needed; `border-right: 1px solid var(--border)` preserved.
- Existing `#app-content` rules (line 63) renamed to `#main-content` selectors, identical CSS.
- `.stub-content`, `.stub-sidebar` unchanged.

### `components.css`
- New `.skip-link` rule under `@layer components`:
  ```css
  .skip-link {
    position: absolute;
    top: -40px;
    left: 0;
    z-index: 1000;
    background: var(--accent);
    color: var(--fg-on-accent);
    padding: 8px 16px;
    text-decoration: none;
    font-weight: var(--font-weight-bold);
    border-bottom-right-radius: var(--panel-radius-sm);
  }
  .skip-link:focus { top: 0; outline: 2px solid var(--fg); outline-offset: 2px; }
  ```
  (The `:focus` outline uses `--fg` for visible focus on top of the accent background.)
- New `.app-topbar-title` rule for the `<h1>`: `font-size: var(--font-size-h1); font-weight: var(--font-weight-bold); color: var(--accent); margin: 0;`. (Margin reset because `<h1>` defaults to 0.67em margin which would push the topbar contents.)
- New `.app-topbar-actions` rule (right-side container holding the theme toggle + picker): `display: flex; align-items: center; gap: 8px;`.
- New `.app-picker-button` rule: matches the previous `.nav-item` size convention but oriented for the topbar — `width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 8px; background: transparent; border: none; cursor: pointer; color: var(--nav-fg);`. Hover/focus rules: `background: var(--nav-bg-active); color: var(--nav-fg-hover);`. Focus-visible: standard `outline: 2px solid var(--accent); outline-offset: 2px;`.
- New `.app-picker-popover` rule: `position: absolute; top: calc(var(--topbar-h) + 4px); right: 16px; min-width: 180px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--panel-radius); box-shadow: var(--panel-shadow); padding: 4px; display: none; z-index: 100;`. `.app-picker-popover[data-open="true"] { display: block; }`.
- New `.app-picker-option` rule: `display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 12px; background: transparent; border: none; color: var(--fg); cursor: pointer; border-radius: var(--panel-radius-sm); text-align: left; position: relative;`. Hover/focus: `background: var(--surface-elevated); color: var(--nav-fg-hover);`. Active: `color: var(--nav-fg-active);` plus the `::before` accent stripe ported from `.nav-item.active::before`.
- `.app-picker-option.active::before { content: ''; position: absolute; left: -2px; top: 8px; bottom: 8px; width: 3px; background: var(--nav-fg-active); border-radius: 2px; }`.
- New `.theme-toggle-compact` rule (mount placement only — internal styling already lives in `theme.js` MVP from leg 01): `width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 8px; background: transparent; color: var(--nav-fg); border: none; cursor: pointer; font-weight: var(--font-weight-bold);` plus standard hover + focus-visible per the picker button pattern. (Leg 01's `theme-toggle-compact` MVP renders text labels L/D/A; leg 02 styles the button container so it composes with the topbar palette; the letter rendering itself stays in `theme.js`.)

### `icons.js`
- New `menu` icon entry: `menu: '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>',` — placed in the "Chevrons" group or in a new "Picker" group with chevron-down. Verify the SVG matches Lucide v0.265.0's `menu` icon exactly (3 horizontal lines, viewBox 0 0 24 24, stroke-width 2).

### `app.js`
- `renderNav()` (line 13) renamed and rewritten as `renderTopBar()`. **`closePicker` is defined inside `renderTopBar` (NOT inside a separate `wirePicker` function)** so the option-click handlers built in the same scope can call it directly without closure-scoping bugs. The full picker wiring (open/close, click-outside, keyboard) lives inline in `renderTopBar`:
  ```javascript
  function renderTopBar() {
    var topbar = document.getElementById('app-topbar');
    topbar.innerHTML =
      '<h1 class="app-topbar-title">the-one</h1>' +
      '<div class="app-topbar-actions">' +
        '<div class="theme-toggle-compact-mount"></div>' +
        '<button class="app-picker-button" aria-label="Switch app" aria-haspopup="true" aria-expanded="false">' +
          App.icons.menu +
        '</button>' +
      '</div>' +
      '<nav class="app-picker-popover" aria-label="App areas" data-open="false"></nav>';

    // Mount compact theme toggle
    var themeMount = topbar.querySelector('.theme-toggle-compact-mount');
    if (window.App && window.App.theme && window.App.theme.renderToggle) {
      window.App.theme.renderToggle(themeMount, { variant: 'compact' });
    }

    var pickerBtn = topbar.querySelector('.app-picker-button');
    var popover = topbar.querySelector('.app-picker-popover');

    // Picker open/close — defined here so option-click handlers can call closePicker via closure.
    function openPicker() {
      popover.dataset.open = 'true';
      pickerBtn.setAttribute('aria-expanded', 'true');
      var firstOpt = popover.querySelector('.app-picker-option');
      // data-open switches CSS to display: block synchronously (attribute sets are
      // synchronous; the CSS rule applies to the next style recalc which happens
      // before focus() returns). Safe to focus immediately.
      if (firstOpt) firstOpt.focus();
    }
    function closePicker() {
      popover.dataset.open = 'false';
      pickerBtn.setAttribute('aria-expanded', 'false');
    }

    // Build picker options — closePicker is in scope here.
    for (var i = 0; i < order.length; i++) {
      var a = order[i];
      var opt = document.createElement('button');
      opt.className = 'app-picker-option';
      opt.dataset.area = a.id;
      opt.setAttribute('type', 'button');
      opt.innerHTML = a.icon + '<span>' + a.label + '</span>';
      opt.addEventListener('click', (function (id) {
        return function (e) {
          e.stopPropagation();
          location.hash = id;
          closePicker();
        };
      })(a.id));
      popover.appendChild(opt);
    }

    pickerBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (popover.dataset.open === 'true') closePicker();
      else openPicker();
    });

    // Click-outside closes
    document.addEventListener('click', function (e) {
      if (popover.dataset.open !== 'true') return;
      if (popover.contains(e.target) || pickerBtn.contains(e.target)) return;
      closePicker();
    });

    // Keyboard within popover (Escape, arrow-cycle)
    popover.addEventListener('keydown', function (e) {
      var opts = Array.prototype.slice.call(popover.querySelectorAll('.app-picker-option'));
      var idx = opts.indexOf(document.activeElement);
      if (e.key === 'Escape') {
        e.preventDefault();
        closePicker();
        pickerBtn.focus();
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        e.preventDefault();
        if (idx === -1) opts[0].focus();
        else opts[(idx + 1) % opts.length].focus();
        return;
      }
      if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault();
        if (idx === -1) opts[opts.length - 1].focus();
        else opts[(idx - 1 + opts.length) % opts.length].focus();
        return;
      }
    });
  }
  ```
- **No separate `wirePicker` function** — the previous design split it out, but that introduced a closure-scope hazard. Inlining keeps `closePicker` reachable from option-click handlers without exposing private internals on a function reference.
- `switchTo` (line 30) updated: the active-highlight section (lines 65-69) operates on `.app-picker-option` (not `.nav-item`). The data attribute is the same (`data-area`).
- `getElementById('app-content')` references throughout the codebase: rename to `getElementById('main-content')`. Search for: `app-content`. Sites likely include `switchTo` (line 41, 53) and possibly area-init code in chat.js / studio.js / admin.js.
- DOMContentLoaded listener (line 87): `renderNav()` → `renderTopBar()`.

### Aside (`<aside>`) `aria-label` setting in area code
- `chat.js`, `studio.js`, `admin.js`: in their `init(sidebar, content)` function (where `sidebar` is now the per-area sidebar panel inside `<aside id="app-sidebar">`), set the parent `<aside>`'s `aria-label` on first activation of each area. The cleanest hook is in `switchTo`: after `targetSidebar.classList.add('active')`, call `document.getElementById('app-sidebar').setAttribute('aria-label', areas[areaId].sidebarLabel || (areas[areaId].label + ' sidebar'))`. Add a `sidebarLabel` optional property to `App.registerArea`'s descriptor (e.g., chat → "Chat sessions"; studio → "Agent list"; admin → "Admin categories"). If `sidebarLabel` is omitted, fallback to `"<Label> sidebar"`.

### Tests
- New browser test `tests/browser/test_flow_picker.py`:
  - `test_picker_renders_closed`: load app, assert `.app-picker-popover[data-open="false"]` is in DOM, `.app-picker-button[aria-expanded="false"]` present, no `.app-picker-option` is visible (DOM check via `is_visible()`).
  - `test_picker_opens_on_click`: click `.app-picker-button`, assert `aria-expanded="true"` and `data-open="true"`, all three `.app-picker-option`s visible.
  - `test_picker_keyboard_open`: Tab to picker button (use `page.keyboard.press("Tab")` after focusing body), press Enter, assert popover opens, Tab cycles through three options, Escape closes and focus returns to picker button.
- Skip-link test `test_skip_link_first_tab`: load app, press Tab, assert active element is `.skip-link`, press Enter, assert URL hash becomes `#main-content` and the `<main>` is the focused/scrolled-to element.
- These FOUR tests (3 picker + 1 skip-link) bring the browser flow-test count from 6 to 10. (Existing flow tests verified by enumeration: `test_app_fixture.py` has 2, `test_smoke.py` has 1, `test_flow_chat.py` has 1, `test_flow_provider_setup.py` has 1, `test_flow_agent_crud.py` has 1 = 6 prior. Snapshot suite still has 12 tests; intentionally drifted.)

### Documentation
- `the_one/agents.md` — new subsection `### App shell` (or update existing `### App architecture` if present): documents the topbar + landmark structure, the picker contract (popover with `aria-haspopup`/`aria-expanded`, keyboard model: Enter/Space opens, arrow keys cycle, Escape closes), the skip-link convention, and the `--topbar-h` / `--nav-*` palette-island reuse rationale.
- `CLAUDE.md` (mission-control) — NO change; CLAUDE.md is methodology-level, not project-level.

## Acceptance Criteria

- [x] `index.html` has skip-link as first body element, `<header id="app-topbar">`, `<aside id="app-sidebar">`, `<main id="main-content">` with the inner row wrapper. No `<div id="app-nav">` remains.
- [x] `tokens.css` has `--topbar-h: 48px;` in BOTH dark and light blocks; `--nav-w` REMOVED from both blocks. All other `--nav-*` tokens unchanged.
- [x] `base.css` has the new `#app-topbar` rules and the body flex-column reflow; `#app-nav` and `.nav-item*` rules fully removed; `#app-content` selectors renamed to `#main-content`.
- [x] `components.css` has `.skip-link`, `.app-topbar-title`, `.app-topbar-actions`, `.app-picker-button`, `.app-picker-popover`, `.app-picker-option`, `.app-picker-option.active::before`, and `.theme-toggle-compact` rules. All under `@layer components`.
- [x] `icons.js` has the `menu` SVG matching Lucide v0.265.0 (verifiable by source).
- [x] `app.js` `renderTopBar()` replaces `renderNav()`. The function builds the topbar content, mounts the compact theme toggle, populates the picker popover, and wires open/close + keyboard interaction. `switchTo` updates `.app-picker-option` active highlighting (not `.nav-item`). All `'app-content'` getElementById/querySelector references renamed to `'main-content'`. DOMContentLoaded calls `renderTopBar()`.
- [x] App-picker popover opens on click (`aria-expanded="true"`, `data-open="true"`), closes on click-outside / Escape / option click. Three options visible when open: Chat / Studio / Admin in the same `order` order. The active area's option has the cyan `::before` accent stripe.
- [x] Skip-link is the first focusable element on page load: pressing Tab from a fresh page focuses it; pressing Enter scrolls to / focuses `<main id="main-content">`.
- [x] Compact theme toggle mounts in the topbar; clicking it cycles preference; the admin-page Settings full toggle stays in sync via the `theme-preference-changed` event from leg 01.
- [x] `<aside>` carries an area-appropriate `aria-label` after each `switchTo` (Chat → "Chat sessions" or fallback "Chat sidebar"; Studio → "Agent list"; Admin → "Admin categories").
- [x] `pytest tests/` reports 393 passing (no change from leg 01; this leg adds no Python unit tests).
- [x] `pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120` reports 10 flow tests passing: 6 prior (`test_app_fixture.py:test_app_clean_serves_index`, `test_app_fixture.py:test_app_clean_responds_to_api_info`, `test_smoke.py:test_playwright_loads_data_url`, `test_flow_chat.py`, `test_flow_provider_setup.py`, `test_flow_agent_crud.py`) + 4 new (`test_flow_picker.py:test_picker_renders_closed`, `test_picker_opens_on_click`, `test_picker_keyboard_open_close`, `test_skip_link_first_tab`). Actual count is 12 (includes 2 seeder tests also marked browser).
- [x] Visual snapshot tests (`pytest -m browser tests/browser/test_visual_snapshots.py`) FAIL on dark + light baselines — this is **expected and intentional**; leg 06 regenerates them. Document the failing baseline names in the flight log so leg 06 has the inventory.
- [x] `the_one/agents.md` has the App shell section (or App architecture section updated) describing the topbar + landmark + picker + skip-link contract.

## Verification Steps

- `grep -n "app-nav\|nav-item" the_one/interfaces/web/static/css/base.css` → returns ZERO hits.
- `grep -n "app-nav" the_one/interfaces/web/static/index.html` → returns ZERO hits.
- `grep -n "app-content" the_one/interfaces/web/static/js/` → returns ZERO hits (all renamed to `main-content`).
- `grep -n "app-content" the_one/interfaces/web/static/css/` → returns ZERO hits.
- `grep -n "renderNav\|renderTopBar" the_one/interfaces/web/static/js/app.js` → returns hits for `renderTopBar` only.
- `grep -n "menu:" the_one/interfaces/web/static/js/icons.js` → returns one hit (the new icon entry).
- `grep -n "skip-link" the_one/interfaces/web/static/` (recursive) → returns hits in `index.html` and `components.css`.
- `pytest tests/ --tb=short --timeout=60` → 393 passing.
- `pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120` → all flow tests passing.
- `pytest -m browser tests/browser/test_visual_snapshots.py --tb=short --timeout=120` → all 12 snapshot cases FAIL (assert this is the expected outcome — they will be regenerated in leg 06).
- Manual browser open: load app, verify topbar renders with "the-one" heading + theme toggle + hamburger; click hamburger → popover opens with three options; click an option → area switches and popover closes; press Escape with popover open → closes; Tab from address bar → first focus is skip-link.
- Lighthouse / axe quick check (informational, not blocking): the new landmarks should be detected as `<header>`, `<navigation>` (when popover open), `<main>`, `<aside>`. `<h1>` count = 1 (good — single page heading).

## Implementation Guidance

1. **Add the `menu` icon to `icons.js`** (do this first — `app.js` references `App.icons.menu`):

   In `the_one/interfaces/web/static/js/icons.js`, in the icons object literal (currently has `chat`, `studio`, `admin`, `plus`, `x`, `edit`, `trash`, `check`, `alert-triangle`, `alert-circle`, `info`, `eye`, `eye-off`, `refresh`, `send`, `download`, `chevron-down`, `chevron-right`, `zap`, `sparkles`), add a new "Picker" group with the `menu` entry. Suggested location: between `chevron-right` and `zap`. The exact SVG (verified against Lucide v0.265.0):
   ```javascript
   // Picker
   menu: '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>',
   ```

2. **Update `tokens.css` token migration**

   In `tokens.css`, in the `[data-theme="dark"]` block (around line 86-100, the "density-and-geometry" group):
   - DELETE `--nav-w: 48px;` (line 88).
   - ADD `--topbar-h: 48px;` immediately after the `--sidebar-w: 240px;` declaration. Comment above: `/* topbar height — chrome strip across the top of the shell */`.

   Repeat the same edits in the `[data-theme="light"]` block (around line 174-180).

   The `--nav-bg` / `--nav-fg` / etc. tokens stay untouched in both blocks — they're reused by the topbar and by the picker dropdown's active-option accent.

3. **Update `index.html`**

   Replace the body content section. Current:
   ```html
   <body>

   <div id="app-nav"></div>
   <div id="app-sidebar"></div>
   <div id="app-content"></div>

   <script src="/static/js/app.js"></script>
   ...
   ```

   New:
   ```html
   <body>
   <a class="skip-link" href="#main-content">Skip to main content</a>

   <header id="app-topbar"></header>
   <div class="app-shell-row">
     <aside id="app-sidebar"></aside>
     <main id="main-content"></main>
   </div>

   <script src="/static/js/app.js"></script>
   ...
   ```

   Script tag order unchanged.

4. **Update `base.css`**

   - At line 4, change `body { font-family: var(--font-family-sans); background: var(--bg-gradient); color: var(--fg); height: 100vh; display: flex; }` to add `flex-direction: column;` at the end of the property list.
   - DELETE all `#app-nav` and `.nav-item*` rules (lines 6-47 — the entire nav-rail section).
   - ADD new rules (place where the deleted nav-rail rules were, to preserve file structure):
     ```css
     /* === Top Bar === */
     #app-topbar {
       height: var(--topbar-h);
       background: var(--nav-bg);
       border-bottom: 1px solid var(--nav-border);
       display: flex;
       align-items: center;
       justify-content: space-between;
       padding: 0 16px;
       flex-shrink: 0;
       position: relative; /* for absolute popover positioning */
     }

     /* === App Shell Row (sidebar + content) === */
     .app-shell-row {
       display: flex;
       flex: 1;
       min-height: 0;
       overflow: hidden;
     }
     ```
   - At lines 49-58 (the existing `#app-sidebar` rules), no functional change is needed but the rule remains (it sits inside `.app-shell-row` now; flex behavior unchanged because the parent is a flex row).
   - At line 63, rename `#app-content` → `#main-content`. Same CSS body. Verify nothing else in `chat.css`, `studio.css`, `admin.css` references `#app-content` — if so, rename those too.

5. **Update `components.css`**

   In the `@layer components` block, add the new component rules listed under "Outputs > components.css" above. Place them after any existing component rules; group related ones (skip-link separately, all `.app-picker-*` together, theme-toggle-compact + topbar-title near each other).

6. **Update `app.js`** — the largest mechanical change

   - Rename `renderNav` → `renderTopBar`. Implement the full body inline (see "Outputs > app.js" code block above) — `closePicker`, `openPicker`, picker-button click handler, click-outside listener, and keyboard handler all live INSIDE `renderTopBar`'s function scope. No separate `wirePicker` function.

   - **Update the `hashchange` listener** at `app.js:82-84` to bail when the hash is not a registered area (skip-link compat + leg 04 readiness):
     ```javascript
     window.addEventListener('hashchange', function () {
       var hash = location.hash.replace('#', '');
       if (!areas[hash]) return;  // skip-link / non-area hashes — ignore
       switchTo(hash);
     });
     ```
     Keep `getHashArea()`'s `|| 'chat'` fallback for the **initial** DOMContentLoaded path (so a fresh visit to `/` lands on chat).

   - Update `switchTo` (lines 30-75) — the highlight section at lines 65-69. Replace:
     ```javascript
     var navItems = document.querySelectorAll('.nav-item');
     for (var i = 0; i < navItems.length; i++) {
       navItems[i].classList.toggle('active', navItems[i].dataset.area === areaId);
     }
     ```
     With:
     ```javascript
     var pickerOpts = document.querySelectorAll('.app-picker-option');
     for (var i = 0; i < pickerOpts.length; i++) {
       pickerOpts[i].classList.toggle('active', pickerOpts[i].dataset.area === areaId);
     }
     ```

   - Update `switchTo`'s `app-content` → `main-content` references (lines 41, 53):
     ```javascript
     var contentPanels = document.querySelectorAll('#main-content .content-panel');
     ...
     document.getElementById('main-content').appendChild(contentPanel);
     ```

   - Add the `<aside>` aria-label setting (after `targetSidebar.classList.add('active')` at line 62):
     ```javascript
     var asideEl = document.getElementById('app-sidebar');
     var areaLabel = areas[areaId].sidebarLabel || (areas[areaId].label + ' sidebar');
     asideEl.setAttribute('aria-label', areaLabel);
     ```

   - DOMContentLoaded handler (line 87): `renderNav()` → `renderTopBar()`.

7. **Update area registrations** (chat.js, studio.js, admin.js)

   Each area's `App.registerArea({...})` call gets an optional `sidebarLabel` field:
   - `chat.js`: `sidebarLabel: 'Chat sessions'`
   - `studio.js`: `sidebarLabel: 'Agent list'`
   - `admin.js`: `sidebarLabel: 'Admin categories'`

   Insertion point: in each registerArea descriptor object, add the new field next to `label`, `icon`, `order`. No other area-code changes needed; the rename of `app-content` → `main-content` lives in `app.js` only because area code references panels via `sidebar` / `content` parameters passed to `init`.

8. **Add picker + skip-link tests**

   Create `tests/browser/test_flow_picker.py`:
   ```python
   """Picker + skip-link browser tests (F3 leg 02)."""
   from __future__ import annotations
   import pytest
   from playwright.sync_api import Page, expect


   @pytest.mark.browser
   def test_picker_renders_closed(app_clean: str, page: Page) -> None:
       page.goto(app_clean)
       expect(page.locator(".app-picker-button")).to_have_attribute("aria-expanded", "false")
       expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "false")


   @pytest.mark.browser
   def test_picker_opens_on_click(app_clean: str, page: Page) -> None:
       page.goto(app_clean)
       page.click(".app-picker-button")
       expect(page.locator(".app-picker-button")).to_have_attribute("aria-expanded", "true")
       expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "true")
       options = page.locator(".app-picker-option")
       expect(options).to_have_count(3)


   @pytest.mark.browser
   def test_picker_keyboard_open_close(app_clean: str, page: Page) -> None:
       page.goto(app_clean)
       page.locator(".app-picker-button").focus()
       page.keyboard.press("Enter")
       expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "true")
       page.keyboard.press("Escape")
       expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "false")


   @pytest.mark.browser
   def test_skip_link_first_tab(app_clean: str, page: Page) -> None:
       page.goto(app_clean)
       page.keyboard.press("Tab")
       active = page.evaluate("document.activeElement.className")
       assert "skip-link" in active, f"First Tab should land skip-link; got: {active!r}"
   ```

9. **Update `the_one/agents.md`**

   Add an "App shell" subsection (or update an existing "App architecture" / "Frontend layout" section if present) describing:
   - The topbar + landmark structure (`<header>` + `<aside>` + `<main>` + `<a class="skip-link">`).
   - The picker contract: button with `aria-haspopup="true"` and `aria-expanded`; popover toggled via `data-open`; keyboard model: Enter/Space opens, ArrowUp/Down (or ArrowLeft/Right) cycles options, Escape closes and returns focus to button; click-outside closes.
   - The skip-link contract: first body child, `position: absolute; top: -40px;` until focused.
   - The `--topbar-h` / `--nav-*` palette-island reuse rationale (chrome continuity from rail to topbar).
   - The new `sidebarLabel` optional area-descriptor field and the fallback (`<Label> sidebar`).

10. **Run tests and verify**

    ```
    pytest tests/ --tb=short --timeout=60
    pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120
    pytest -m browser tests/browser/test_visual_snapshots.py --tb=short --timeout=120
    ```

    The first should pass at 393. The second should pass at 10 (6 prior flow tests + 4 new picker/skip-link tests; verify by enumeration). The third is **expected to fail** — record the failing baseline names in the flight log so leg 06 has the inventory.

    **TIMEOUT POLICY**: per leg-execution conventions, kill any pytest run that exceeds 5 minutes wall-clock and signal `[BLOCKED:test-hang]`.

## Edge Cases

- **Click-outside while picker option is being clicked**: the `document.addEventListener('click', ...)` for click-outside fires AFTER the option's click handler (event bubbling). The option handler calls `closePicker()` itself; the click-outside check then sees `data-open === 'false'` and bails. No race. But to guard against future race introductions, the option-click handlers should `e.stopPropagation()` to be defensive. Document this in a code comment.
- **Hamburger button + popover positioning on narrow viewports**: with `position: absolute; right: 16px` the popover can extend off-screen if the viewport is narrower than 200px. Acceptable for v1 (the app is desktop-first). Document as known limitation in agents.md if not already.
- **`<h1>` vs page title**: there's now exactly one `<h1>` per page (the topbar). Some areas may have had `<div class="title">` as a visual heading (e.g., `chat.js:20` uses `<span class="title">`). These are NOT promoted to `<h2>` in this leg — that's per-area alignment work in F4-F6. The current `<span class="title">` stays as visual chrome.
- **Skip-link target focus**: clicking the skip-link causes `location.hash = '#main-content'` which scrolls but does NOT necessarily move keyboard focus. To move focus, `<main id="main-content" tabindex="-1">` is the standard fix; add `tabindex="-1"` to the `<main>` element so it can receive programmatic focus. (Keep `tabindex="-1"` rather than `0` so it's not in the natural Tab order beyond the skip-link target.)
- **Mounting compact toggle BEFORE picker keyboard wiring**: order matters in `renderTopBar` because the picker's first focusable option must be reachable via the picker button's `aria-controls` semantics. The current implementation mounts toggle, then picker button, then popover. Tab order from address bar will be: skip-link → topbar-title (not focusable; an `<h1>` is not interactive) → theme toggle compact → picker button → (when picker opens) options. Verify with `test_skip_link_first_tab` and a manual Tab walkthrough.
- **`document.getElementById('main-content')`**: in step 6's switchTo update, ensure NO callsite still references `getElementById('app-content')`. A grep of all JS files is the safest check; do it before declaring complete.
- **The `<aside>` `aria-label` default fallback**: if an area registers without a `sidebarLabel` AND its `label` is e.g. "Admin", the fallback yields "Admin sidebar" — acceptable. If `label` is missing entirely (shouldn't happen given existing areas all declare `label`), the fallback would be "undefined sidebar" — the area-registration descriptor invariant prevents this, but document for clarity.

## Files Affected

- `the_one/interfaces/web/static/index.html` — Replace app-nav/app-sidebar/app-content divs with semantic landmarks + skip-link.
- `the_one/interfaces/web/static/css/tokens.css` — Rename `--nav-w` → `--topbar-h` in both theme blocks.
- `the_one/interfaces/web/static/css/base.css` — Remove nav-rail rules; add topbar + app-shell-row rules; rename `#app-content` → `#main-content`; add `flex-direction: column` to body.
- `the_one/interfaces/web/static/css/components.css` — Add `.skip-link`, `.app-topbar-*`, `.app-picker-*`, `.theme-toggle-compact` rules.
- `the_one/interfaces/web/static/js/icons.js` — Add `menu` icon.
- `the_one/interfaces/web/static/js/app.js` — Rename `renderNav` → `renderTopBar`; rewrite the function with inline picker wiring (open/close/keyboard/click-outside all inside `renderTopBar`'s scope, NO separate `wirePicker`); update the `hashchange` listener to bail on non-area hashes (skip-link compat); update switchTo highlighting + `app-content` → `main-content` references; update DOMContentLoaded handler; add aside aria-label setter.
- `the_one/interfaces/web/static/js/areas/chat.js` — Add `sidebarLabel: 'Chat sessions'` to registerArea descriptor.
- `the_one/interfaces/web/static/js/areas/studio.js` — Add `sidebarLabel: 'Agent list'` to registerArea descriptor.
- `the_one/interfaces/web/static/js/areas/admin.js` — Add `sidebarLabel: 'Admin categories'` to registerArea descriptor.
- `tests/browser/test_flow_picker.py` — NEW file: 4 tests covering picker + skip-link.
- `the_one/agents.md` — Add/update App shell subsection.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[LEG:02:landed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing per the verification plan (393 unit; 12 flow tests in browser including 4 new picker/skip-link; visual snapshots intentionally failing — record baseline names in the flight log)
- [x] Flight log updated with: list of failing visual snapshot baselines (for leg 06 inventory), any deviations, manual Tab-order verification result, picker keyboard test result
- [x] Leg status updated to `landed`
- [x] Per F3 batching: do NOT commit. Report `[LEG:02:landed]`.
