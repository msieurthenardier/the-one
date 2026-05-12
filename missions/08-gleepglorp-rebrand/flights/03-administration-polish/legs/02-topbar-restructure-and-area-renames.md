# Leg: 02-topbar-restructure-and-area-renames

**Status**: landed
**Flight**: [Administration Polish](../flight.md)

## Objective

Replace the topbar's app-picker chevron menu with **three flat area buttons** (Chat / Agent Studio / System) and replace the wordmark + icon with the **brand banner image**. Rename area labels: chat `"Agent Chat"` → `"Chat"`; admin `"Settings"` → `"System"`. Operator-requested scope expansion surfaced at Leg 02 kickoff — replaces the originally-planned System page polish (which shifts to Leg 03).

## Context

- **Operator directive at Leg 02 kickoff**: "I want Agent Chat to be a first-class citizen." Initial direction was "pull Chat out as its own item, move Studio + Settings under a chevron menu." After implementing that v1, the operator pivoted: "lets get rid of the app picker altogether and just put three buttons. Also for the icon and app name on the left, replace that with the banner image in brand."
- **Final direction**: Three flat area buttons in the topbar actions area; chevron popover affordance entirely retired; banner image replaces the `<h1>` wordmark.
- **Rationale**: Chat is the highest-traffic surface; routing through a dropdown for ANY area is unnecessary friction now that there are only 3 areas total. The chevron popover added ~100 LOC of state machine (open/close/keyboard/click-outside) for a 3-item menu — a flat-button row is cleaner mechanically and visually.
- **Why insert ahead of System page polish**: Topbar is shared infrastructure consumed by every page; restructuring before page-by-page polish means the polish legs operate against the final topbar layout.
- **Studio label already correct**: `studio.js:3` was already `'Agent Studio'` from a prior flight. Only Chat + Admin labels needed updating.

## Inputs (pre-leg state)

- `static/js/app.js renderTopBar()` rendered an `<h1 class="app-topbar-title">` with the brand icon + `"GleepGlorp AI"` wordmark, followed by a single `.app-picker-button` showing the current area's icon + label + chevron. Clicking opened a `.app-picker-popover` `<nav>` containing one `.app-picker-option` per registered area.
- `static/js/areas/chat.js:3` `label: 'Agent Chat'`.
- `static/js/areas/admin.js:3, :6, :242` carried `'Settings'` / `'Settings categories'` / `'Settings sections'`.
- `static/css/components.css:23-152` defined `.app-topbar-title`, `.app-topbar-actions`, `.app-picker-button` (V3b family treatment + `[aria-expanded="true"]` open state + chevron-rotate animation + `:focus-visible` outline), `.app-picker-popover` (glass surface + bezel), and `.app-picker-option`/`.active`/`::before` (popover list item + active-rail indicator).
- `static/brand/gleepglorp_banner.png` — already present in working tree (untracked); operator's brand banner artwork.

## Outputs (post-leg state)

- `renderTopBar()` emits:
  - `<img src="/static/brand/gleepglorp_banner.png" alt="GleepGlorp AI" class="app-topbar-banner">` (replaces the `<h1>` wordmark + icon)
  - `<div class="app-topbar-actions">` containing **one flat `.app-picker-button` per registered area** (Chat / Agent Studio / System) built via a loop over `order[]`. Each button has `data-area="{id}"`, `aria-label="Go to {label}"`, an `.app-picker-button-icon` with the area's SVG icon, and an `.app-picker-button-label` with the area's label. No chevron child element. No popover element in the DOM.
  - Each button has a single `click` listener that navigates to `location.hash = areaId`.
- `switchTo()` updates `aria-current="page"` on the active-area button (removed from the others) — simpler than the prior popover-option highlight logic.
- `chat.js:3` `label: 'Chat'`.
- `admin.js:3, :6, :242` `label: 'System'` / `sidebarLabel: 'System categories'` / `ariaLabel: 'System sections'`.
- Studio + Admin sidebar-omission comments updated to reflect the new topbar semantic ("the topbar's area buttons already name the active area").
- `components.css`:
  - `.app-topbar-title`/`.app-topbar-title img` rules replaced with `.app-topbar-banner` (`height: 32px; width: auto`).
  - `.app-picker-button` rule retained + simplified: padding tightened from `0 10px 0 8px` (asymmetric for chevron) to `0 12px` (symmetric); transition properties unchanged. Removed `[aria-expanded="true"]` rule + chevron-rotate rule + chevron descendant selector.
  - `.app-picker-button[aria-current="page"]` rule added: accent-translucent + accent border (no outer glow halo — that's reserved for `:focus-visible`).
  - `.app-picker-popover` + all `.app-picker-option*` rules removed (popover affordance fully retired).
  - `.app-picker-button-chevron` rules removed.
- `design-language/surfaces-section.js` app-picker miniature updated: "closed / open" pair (which referenced the retired chevron + popover) replaced with "rest / active" pair using `aria-current="page"` to show the active state. Labels relabeled to `"System"` (post-rename).
- `static/brand/gleepglorp_banner.png` added to git tracking (was untracked).

## Acceptance Criteria

- [x] `chat.js:3` reads `label: 'Chat'`
- [x] `admin.js:3` reads `label: 'System'`; `:6` reads `sidebarLabel: 'System categories'`; `:242` reads `ariaLabel: 'System sections'`
- [x] `studio.js:3` reads `label: 'Agent Studio'` (no change required — already correct)
- [x] `renderTopBar()` emits `<img class="app-topbar-banner">` + `<div class="app-topbar-actions">` containing one flat `.app-picker-button` per registered area; no `.app-picker-popover` element
- [x] All popover machinery removed from `app.js` (no `openPicker`/`closePicker` functions; no click-outside listener; no popover keyboard handler)
- [x] CSS rule `.app-picker-button[aria-current="page"]` defined in `components.css` (active-area state)
- [x] CSS rules `.app-picker-popover`, `.app-picker-option`/`-option:hover`/`-option:focus`/`-option:focus-visible`/`-option.active`/`-option.active::before`, `.app-picker-button-chevron`, `.app-picker-button[aria-expanded="true"]` all removed
- [x] `.app-topbar-title`/`.app-topbar-title img` rules replaced with `.app-topbar-banner` rule
- [x] Design-language gallery's app-picker miniature relabeled to `"System"` + restructured to "rest / active" pair
- [x] `gleepglorp_banner.png` tracked in git
- [x] Narrow test gate green: 56/56 (no behavioral regressions)
- [x] WCAG audit green: 45/45 (no contrast pair changes — `aria-current` state uses already-audited accent-translucent on body bg)
- [x] Operator visual verification confirmed ("looks good")

## Files Modified

- `the_one/interfaces/web/static/js/app.js` — `renderTopBar()` completely restructured (banner image + button loop); `switchTo()` button-active-state simplified to `aria-current` toggle; ~100 LOC of popover machinery removed
- `the_one/interfaces/web/static/js/areas/chat.js:3` — label rename
- `the_one/interfaces/web/static/js/areas/admin.js:3, :6, :242` — label + sidebarLabel + ariaLabel rename; sidebar-omission comment updated
- `the_one/interfaces/web/static/js/areas/studio.js:310-312` — sidebar-omission comment updated
- `the_one/interfaces/web/static/css/components.css` — `.app-topbar-title` → `.app-topbar-banner`; popover rules removed; `[aria-current="page"]` rule added
- `the_one/interfaces/web/static/js/areas/admin/design-language/surfaces-section.js` — gallery miniature restructured ("rest / active" pair) + relabeled
- `the_one/interfaces/web/static/brand/gleepglorp_banner.png` — added to git (was untracked)
- `missions/08-gleepglorp-rebrand/flights/03-administration-polish/legs/03-system-page-polish.md` — renumbered from `02-` to `03-` to make room for this leg
- `missions/08-gleepglorp-rebrand/flights/03-administration-polish/flight.md` — leg list reordered and renumbered

## Citation Audit

10 citations verified against current code (commit `75864da` on `flight/03-administration-polish`):
- `app.js:14-126` `renderTopBar()` body — verified pre-restructure (rendered `<h1>` + single picker button + popover); restructure applied.
- `app.js:182-202` `switchTo` picker-button refresh block — verified; simplified to `aria-current` toggle loop.
- `chat.js:3` — verified pre-edit `'Agent Chat'`; post-edit `'Chat'`.
- `admin.js:3, :6, :242` — verified pre-edit `'Settings'` / `'Settings categories'` / `'Settings sections'`; all renamed.
- `studio.js:3` — verified `'Agent Studio'` (no change).
- `components.css:23-152` `.app-topbar-title` / `.app-picker-button` family / popover rules — verified pre-restructure; rules retired + simplified per Outputs section.
- `surfaces-section.js:78-101` — verified pre-edit "closed / open" pair with chevron; restructured to "rest / active".
- `static/brand/gleepglorp_banner.png` — verified file exists in working tree (445KB).

All citations clean.
