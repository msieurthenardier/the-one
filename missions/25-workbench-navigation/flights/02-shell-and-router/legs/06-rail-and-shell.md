# Leg: rail-and-shell

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Replace the interim top bar with the workbench rail, delivered as a library factory
(`App.ui.rail`), and finish the shell:
- the rail + aside + main grid layout, and its widths;
- the destination icons;
- landmarks, the skip link and keyboard behaviour;
- the global `.visually-hidden` utility;
- copy that still names the old areas;
- the inventory and demo;
- `_nav`'s rail flip.

## Context

- **Flight decision:** DD7 is this leg's spec (rail API, geometry from reference spec §2,
  roving single tab stop, test ids, icons, shell grid, aside collapse and labels,
  widths, the `.visually-hidden` lift, copy updates). DD4 sets the rail's href rules:
  the current destination's link points to its root, the others to their last route.
  DD12 sets placement. Read them, plus reference spec §1–§2 and B3's rail markup.
- **Router commit hook** (design review). Today the router has **no** subscription or
  event API; `applyShell()` updates the top bar directly by looping over
  `#app-topbar [data-destination]` (router.js ~L339). This leg adds
  `App.router.onCommit(fn) → unsubscribe`, called from `applyShell` (commit step 5) with
  the destination id. The top-bar loop is deleted. Hrefs refresh **on every commit**;
  `sync()` only moves the current destination's `lastRoute`, and the current
  destination's rail href is its root anyway. `lastRoute(dest)` falls back to the
  destination root, so first-boot hrefs need no special case.
- **Dependency on leg 5.** The rail is plain `<a href>` links with **no click handler**.
  Guarded navigation, middle-click passthrough and restore all depend on leg 5's
  `nav.js` link interceptor. Leg 5 runs first.
- **Layout: a flex row, not a grid.** In a CSS grid, a `hidden` aside would make
  `<main>` auto-place into the aside's track. Keep `.app-shell-row` as a flex row and
  put the rail first inside it. `index.html` gets a mount point, `<div id="app-rail"></div>`
  (replacing `<header id="app-topbar">`). `app.js` mounts `App.ui.rail(...).el` there. The
  existing `min-width:0` chain is kept.
- **State after legs 3–5:**
  - the interim 4-button top bar (`#app-topbar [data-destination]`), whose clicks call
    `go(dest === current ? root : lastRoute(dest))`;
  - the aside already collapsed on Agents, with labels and `data-destination` set on
    the active panel;
  - `App.nav`'s link interceptor in place.

  The rail is plain `<a href>` links handled by that interceptor; it has **no click
  handler**. It keeps hrefs current through `App.router` updates. Confirm the
  subscription or event API name against the `router-core` flight-log entry.
- **Icons** (corrected at design review). `icons.js` already has `chat`, `studio` (the
  board's bot glyph) and `admin` (the board's cog). Their paths match the B3 rail SVGs.
  - **Only `database` is missing.** Copy it from B3's Library SVG, and add
    `focusable="false"` to match the existing attribute set.
  - Change the router destination table's Library `iconKey` from `studio` to
    `database` (router.js ~L57-60).
  - Do **not** rename `studio`, `admin` or `chat`: the area descriptors use them.
  - Size icons inside `.ui-rail-item` to 18px with CSS; the SVGs carry 24×24
    attributes.
- **Tests.** `_nav.destination_locator` and `open_destination` carry a
  `LEG-5`-marked branch from leg 1 (written before the split renumbered the legs). It
  flips here to the rail: `[data-testid=rail-<id>]`. `test_flow_picker.py`'s three
  permanently skipped dead tests retire with the top bar.

## Inputs

- `static/js/app.js` (interim top bar), `router.js`, `nav.js`, `ui/core.js`,
  `icons.js`.
- `static/index.html` (`#app-topbar`, `.app-shell-row`, `#app-sidebar`,
  `#main-content`, skip link), `css/base.css` (topbar, sidebar and shell rules),
  `css/components.css` (topbar and brand rules, `.visually-hidden` users),
  `css/admin.css`/`chat.css` (`.visually-hidden` definitions).
- `areas/chat/welcome.js` (:9, :32-42), `areas/chat.js` (:1034),
  `areas/studio/mcps-tab.js` (:76).
- `tests/browser/_nav.py`, `test_flow_picker.py`, the reference-page and inventory
  guards, `docs/ui-testid-registry.md`.

## Outputs

- **`ui/rail.js`**: `App.ui.rail({items, currentId, brand})` → `{el, setCurrent(id),
  setHref(id, href)}`.
  - It renders `<nav class="ui-rail" aria-label="Main">`: a brand mark (the 24px asset,
    with an accessible name, at 24px) and four `<a>` items.
  - Each item carries an icon (`util.icon`), a label, `aria-current="page"` when
    current, and `testid` (`rail-chats|agents|library|settings`).
  - Keyboard: roving focus with a single tab stop, ArrowUp/Down, clamped.
  - It follows the full factory checklist: script tag and count, CSS in
    `components.css`, contract tests in both engines, a `data-ui-demo="rail"` demo, an
    inventory row, and registry rows.
- **`icons.js`:** a `database` icon (Lucide v0.265.0, the B3 Library glyph with
  `focusable="false"`). The router's Library `iconKey` becomes `database`.
- **`router.js`:** `App.router.onCommit(fn) → unsubscribe`; the `#app-topbar` loop is
  removed from `applyShell`.
- **Shell:**
  - `#app-topbar` and its CSS are removed: the interim top bar code, `nav-chat-btn` and
    its registry row, `.app-brand*` (the "GleepGlorp AI" wordmark is **dropped**; only
    the rail's brand mark remains, with its accessible name), `--topbar-h` if nothing
    else uses it, and the design-language surfaces section's `app-picker-button`
    sample along with its CSS (`surfaces-section.js` ~:52-70, :133).
  - Also updated:
    - `_nav.py` (`TOPBAR_BUTTON_SELECTOR`, ~L394-400);
    - `docs/ui-control-inventory.md` ("App picker (top bar)" row);
    - `docs/ui-testid-registry.md` (~:170);
    - `agents.md` (~:1755);
    - the test_flow_hash_routing comment.

    `tests/test_nav_helper.py`'s `_TOPBAR_MARKERS` **stays**, as regression markers.
  - The `index.html` shell becomes a **flex row** (`.app-shell-row`): `#app-rail`, then
    `<aside id="app-sidebar">`, then `<main id="main-content" tabindex="-1">`.
  - The skip link stays first.
  - Widths follow DD7: `@media (max-width: 1279px)` makes the aside 200px, so exactly
    1280px is 240px; 1024px is the supported minimum; `body` keeps `overflow:hidden`.
  - `app.js` mounts the rail and keeps it in sync with the router (`setCurrent`, and
    `setHref` for each destination: the current one points to its root, the others to
    `lastRoute`).
- **CSS:** `.visually-hidden` is defined once in `components.css` and removed from
  `admin.css` and `chat.css`.
- **Copy** (exact strings; re-grep after leg 4 lands):
  - welcome.js ~L32/34/38/42: "LLM Settings" becomes "Settings", and "Agent Studio"
    becomes "Agents". L9's `href` is leg 4's link change, not copy.
  - chat.js ~L1034: "Configure a provider in Studio" becomes "Add a provider in
    Settings".
  - mcps-tab.js ~L76: "Add one in MCP Sources." becomes "Add one in the Library.". This
    is inside an existing inner-HTML assignment, so keep it a single statement and leave
    the sink baseline count unchanged.
  - Tests asserting the old copy are updated: `test_flow_provider_setup.py` (~:38, :80)
    and `test_studio_mcps_tab.py` (~:318).
- **Tests:**
  - `_nav` flips to the rail;
  - `test_flow_picker.py`'s dead skipped tests are removed, and the skip-link test is
    kept;
  - the top-bar assertions anywhere are migrated;
  - new rail and shell tests.
- **Docs:**
  - `agents.md`: the App-shell section is rewritten for the rail and grid, and the
    Control-library `rail` entry is added;
  - CLAUDE.md: a shell pointer;
  - `docs/ui-control-inventory.md`.

## Acceptance Criteria

- [x] **AC1 — Rail factory.** It takes `items` as data and does not access `App.router`.
  It initialises `tabindex` itself: the current item gets 0 and the others -1, reset in
  `setCurrent`, since `util.rovingFocus` only sets them on keydown. It reuses
  `rovingFocus` (clamped). It may render briefly with no `aria-current` before the first
  commit, and the contract tests must not assume otherwise.
  - The API and markup are as in Outputs. It is ES5, follows the export idiom, uses no
    app globals and contains no sink tokens.
  - Contract tests in **both engines** cover:
    - roving focus with one tab stop;
    - ArrowUp/Down, clamped;
    - `aria-current`;
    - `setCurrent` and `setHref`;
    - `assert_controls_labelled_and_described`;
    - a visible focus ring (`outline` or inset `box-shadow`) after a keyboard Tab, with
      a positive control.
- [x] **AC2 — Geometry and colour against reference spec §2** (variation: see flight log, recorded deviations), in both themes, measured
  as computed style in Chromium on the app: rail width 72px, item width 60px, icon
  18px, label `--font-size-tiny`.
  - The selected marker (wash plus inset ring) and the hover treatment follow DD14.
  - Any deviation from §2 is listed in the flight log as fixed or as a recorded
    deviation (SC8 evidence starts here).
  - Every new text-on-surface pair in the rail is gated in `test_design_tokens_a11y.py`:
    labels on `--surface`, and labels on the selected wash composited.
- [x] **AC3 — The shell.**
  - `#app-topbar` is gone (grep, and a DOM assertion). The layout is the flex row with
    `#app-rail`.
  - Landmarks are present: `nav[aria-label="Main"]`, the aside (when not hidden) and
    `main#main-content`.
  - The skip link is first in the tab order and focuses `#main-content`.
  - The aside is hidden on Agents.
  - At 1024×768 and 1440×900:
    - the rail's bounding box is x ∈ [0, 72] and fully inside the viewport;
    - `main.getBoundingClientRect().right <= innerWidth`;
    - the aside is 200px below 1280px and 240px at 1280px and above;
    - no direct child of the active panel extends past `main.right`;
    - at 1024, section-nav labels and chat session rows in the 200px aside ellipsize or
      wrap rather than clip.

    `overflow:hidden` hides clipping, so `scrollWidth` alone is not evidence.
- [x] **AC4 — Rail hrefs and restore.**
  - The current destination's rail link points to its root, and the others to their
    `lastRoute`. Hrefs are kept current on every router write.
  - Clicking the current destination goes to its root.
  - Clicking another destination restores its last item. Test it: open an agent → go to
    Settings → click Agents on the rail → the agent is restored.
  - A middle-click (modifier) is not intercepted. Assert the `href` value, without
    opening a tab.
- [x] **AC5 — Icons.**
  - `database` is added, from Lucide v0.265.0, with `aria-hidden`, `focusable="false"`
    and `stroke="currentColor"`.
  - A unit test asserts every destination's `iconKey` exists in `App.icons` and parses
    as SVG through `util.icon`.
  - Rail icons render at 18px.
- [x] **AC6 — `.visually-hidden`** is defined once in `components.css`. Grep shows it is
  defined nowhere else. The library `labelHidden` usages render hidden in the disk
  harness **without** `admin.css` or `chat.css` loaded: a contract-test assertion loads
  only `tokens.css` and `components.css`.
- [x] **AC7 — Copy.** The three copy sites are updated, and any test asserting the old
  copy is updated.
- [x] **AC8 — Tests and the inventory.**
  - `_nav`'s destination helpers use the rail.
  - Top-bar references are gone from the tests: the migration guard's top-bar selectors
    list is updated, and the guard passes.
  - `test_flow_picker.py`'s dead tests are removed.
  - Reference page: `[data-ui-demo="rail"]` in both theme panes, with a non-routing demo
    (hrefs set to `#main-content`, or `aria-current` shown statically).
  - Inventory and registry are updated; the guards pass.
- [x] **AC9 — Docs.**
  - `agents.md`: the App-shell section (rail, grid, widths, landmarks, skip link) and
    the Control-library `rail` entry.
  - CLAUDE.md: the shell pointer.
  - The `windows-native-frame-splash.md` spec mention is left for leg 8.
- [x] **AC10 — Gates pass.**
  - `make lint`;
  - `make test-unit`;
  - all five lanes, one at a time;
  - every `test_ui_*` in both engines.

  The WebKitGTK probe at `#agents` and `#settings/general` (`--root-selector body`)
  records results, including whether the rail resolves cleanly.

## Verification Steps

- AC1:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_rail_contract.py -x -rA`.
- AC2–AC4: new shell tests (`tests/browser/test_shell_rail.py`), plus the a11y suite.
- AC5–AC8: the unit tier and guards.
- AC9–AC10: a doc read and the gates.

## Implementation Guidance

1. **Icons**: copy the SVGs from B3's rail markup.
2. **`ui/rail.js`** plus its CSS and contract tests.
3. **The shell**: rewrite the `index.html` structure and `base.css` grid; mount the rail
   in `app.js`; remove the top bar and its CSS.
4. **`.visually-hidden` lift.**
5. **Copy.**
6. **`_nav` flip, test migration, dead-test removal.**
7. **Demo, inventory, registry, docs, gates, probe.**

## Recorded deviations from reference spec §2 (for the flight log; SC8)

- Destinations are `<a>`, per DD7, not `<button>`.
- The active marker is the DD14 wash plus inset ring, not
  `border-color: var(--accent)`.
- Hover uses `--surface-elevated`, per DD14; §2 defines no hover.
- The brand mark is 24px, not 28px.
- The jump-to control at the bottom of the rail (44px ghost button, Ctrl K) is **out of
  scope**: Flight 4.

## Edge Cases

- **Design-language route in non-dev mode**: Settings still works, and the rail is
  unaffected.
- **Brand mark asset**: use `static/brand/` (the 24px topbar icon). Never scale a
  pixel-art image to a non-integer factor.
- **Reduced motion**: the rail has no motion beyond the standard hover transitions on
  the motion tokens.
- **Theme switch**: rail colours come from tokens only. Check the selected wash in both
  themes.

## Files Affected

- `static/js/ui/rail.js` (new), `router.js` (`onCommit`, Library `iconKey`), `icons.js`,
  `app.js`, `index.html`, `css/base.css`,
  `css/components.css`, `css/admin.css`, `css/chat.css`
- `areas/chat/welcome.js`, `areas/chat.js`, `areas/studio/mcps-tab.js`
- `tests/browser/test_ui_rail_contract.py` (new), `tests/browser/test_shell_rail.py`
  (new), `tests/browser/_nav.py`, `test_flow_picker.py`, the guard, the a11y suite,
  `tests/test_index_asset_cache_busting.py`
- `design-language/ui-*-section.js` (rail demo), `design-language/surfaces-section.js`
  (`app-picker-button` sample retired), `Makefile` (`verify-serving` list),
  `docs/ui-control-inventory.md`,
  `docs/ui-testid-registry.md`
- `the_one/agents.md`, `CLAUDE.md`
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

To be re-verified at leg start against legs 3–5 outputs: the top-bar code, the router
update API, and `_nav`'s marked branch. The copy sites welcome.js:9/:32-42,
chat.js:1034 and mcps-tab.js:76 come from the flight review (Architect, `fe595cc`).

Design review (Developer, 2026-10-01) — "approve with changes". Applied:
- a router `onCommit` hook, added in this leg;
- the icon premise corrected (only `database`), with the Library `iconKey`;
- a flex row with an `#app-rail` mount point, not a grid;
- the `app-picker-button` sample and `.app-brand*` retired, and the wordmark dropped;
- precise width and overflow assertions with the `@media` breakpoint;
- the leg 5 dependency stated;
- exact copy strings, with their tests named;
- the `.visually-hidden` lift notes;
- the §2 deviations recorded;
- the roving-tabindex initialisation.

The cache-busting count is computed from the tree at implementation time.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
