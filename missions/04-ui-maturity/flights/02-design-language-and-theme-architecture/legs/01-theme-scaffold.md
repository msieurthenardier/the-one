# Leg: 01-theme-scaffold

**Status**: landed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Stand up the theme architecture scaffold: create `css/tokens.css` with `[data-theme="dark"]` and `[data-theme="light"]` blocks, create `js/theme.js` implementing the tri-state toggle (Light/Dark/Auto) with localStorage persistence and live OS-preference response, declare CSS cascade layers in `index.html`, and wire everything up so the app loads with `data-theme` set on `<html>` before any rendering. **No visual change** — dark theme tokens exactly match current `:root` values.

## Context

- This is the foundation leg of Flight 02. Subsequent legs (02-09) build on this scaffold.
- Per the flight design: `[data-theme="dark"]` / `[data-theme="light"]` blocks (no `:root` shortcut), CSS cascade layers `@layer tokens, base, components, areas, utilities`, tri-state toggle stored in single localStorage key `theme-preference`.
- **CRITICAL — tokens.css is INACTIVE in leg 01**: the existing `:root` block in `styles.css:2-11` is unlayered, which means it lives in CSS's "implicit final layer" — outranking ALL named layers regardless of selector specificity. So `tokens.css`'s `@layer tokens { [data-theme="dark"] { ... } }` block is effectively dead until leg 02 wraps styles.css in named layers and removes the unlayered `:root` block. **This is intentional**: leg 01 is the scaffold (file structure + theme.js wiring + HTML hookup), leg 02 activates it.
- **Practical consequence for verification**: toggling `App.theme.set('light')` in leg 01 produces **NO visible change** (tokens.css's light-theme values are overridden by styles.css's unlayered `:root`). This is correct behavior for leg 01 — verification confirms `data-theme` attribute changes on `<html>`, NOT visual change. Leg 02 brings the tokens to life.
- Token group structure: `palette`, `typography`, `space`, `motion`, `density-and-geometry`. Leg 01 establishes the structure with minimal token coverage — just enough to mirror what's currently in `:root`. Leg 02 (apply-tokens) expands coverage by introducing tokens for every hardcoded value found during the refactor.
- Theme.js must run BEFORE rendering to avoid FOUC (flash of unthemed content). Placed in `<head>` before any stylesheet link.
- **`window.App` namespace mutation pattern**: `app.js:1` currently uses `var App = (function() {...})()` which CLOBBERS any existing `window.App` when it runs (after theme.js). To preserve `App.theme`, this leg modifies `app.js` to mutate `window.App` in place rather than reassigning. This makes the App namespace explicitly extensible — F2's later legs (and beyond) will add more sub-namespaces (e.g., `App.icons`, `App.snapshots`) under the same pattern.
- **Test environment color_scheme**: Playwright's `browser.new_context()` default is `color_scheme="light"`, not `"no-preference"`. The leg explicitly sets `color_scheme="no-preference"` in `tests/browser/conftest.py` so the test environment matches the canonical "no preference → default to dark" behavior.
- No prior leg outcomes (this is the first leg of the flight).
- F1 outcomes still apply: 14 data-testids on existing elements, 350+8 tests pass, mock provider type, etc.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture` checked out, status `in-flight`
- Existing files in their pre-leg state:
  - `the_one/interfaces/web/static/index.html` — 20 lines, simple shell with `<link rel="stylesheet" href="/static/styles.css">` and 4 script tags
  - `the_one/interfaces/web/static/styles.css:1-11` — current `:root` block with 8 custom properties
  - `the_one/interfaces/web/static/js/app.js` — exposes `App` namespace globally (`App.registerArea`, `App.escapeHtml`, etc.)
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing

## Outputs

- `the_one/interfaces/web/static/css/tokens.css` (new) — token definitions wrapped in `@layer tokens { ... }`, two theme blocks, plus `color-scheme: dark light` for native UI element theming
- `the_one/interfaces/web/static/js/theme.js` (new) — synchronous theme initialization + tri-state toggle API exposed under `App.theme`; localStorage access wrapped in try/catch
- `the_one/interfaces/web/static/index.html` modified:
  - `<head>` gets `<style>@layer tokens, base, components, areas, utilities;</style>` declaration (FIRST in head after meta tags)
  - `<head>` gets `<script src="/static/js/theme.js"></script>` (BEFORE the stylesheet link — must run before render)
  - `<head>` gets `<link rel="stylesheet" href="/static/css/tokens.css">` (BEFORE the existing styles.css link)
- `the_one/interfaces/web/static/js/app.js` modified — IIFE rewritten to mutate `window.App` in place (preserves `App.theme` registered by theme.js)
- `tests/browser/conftest.py` modified — `browser.new_context()` call gets `color_scheme="no-preference"` so test env matches canonical default
- The existing `:root` block in styles.css is **untouched** in this leg. Leg 02 will remove it as part of the apply-tokens refactor (and is what activates the token blocks).

## Acceptance Criteria

### Token file
- [ ] `the_one/interfaces/web/static/css/tokens.css` exists
- [ ] File opens with `@layer tokens { ... }` wrapping both theme blocks
- [ ] `[data-theme="dark"]` block contains the current 8 tokens with EXACT values from styles.css `:root`:
  - `--bg: #0a0a0a`
  - `--fg: #e0e0e0`
  - `--accent: #4a9eff`
  - `--surface: #1a1a1a`
  - `--border: #2a2a2a`
  - `--tool: #2d2d2d`
  - `--sidebar-w: 240px`
  - `--nav-w: 48px`
- [ ] `[data-theme="light"]` block contains placeholder light-theme values (educated guesses; will be redesigned in leg 06):
  - `--bg: #fafafa` (off-white)
  - `--fg: #1a1a1a` (deep gray text)
  - `--accent: #2563eb` (blue, slightly darker than dark theme's for contrast)
  - `--surface: #ffffff`
  - `--border: #e5e7eb`
  - `--tool: #f3f4f6`
  - `--sidebar-w: 240px` (same as dark)
  - `--nav-w: 48px` (same as dark)

### Theme switcher script
- [ ] `the_one/interfaces/web/static/js/theme.js` exists
- [ ] Script reads `localStorage.getItem('theme-preference')` wrapped in try/catch (values: `'dark'` | `'light'` | `'auto'` | `null` — treat `null` and any read failure as `'auto'`)
- [ ] Script uses TWO matchMedia queries: `'(prefers-color-scheme: dark)'` AND `'(prefers-color-scheme: light)'`. Resolution: `'auto'` + dark match → `'dark'`; `'auto'` + light match → `'light'`; `'auto'` + neither match → `'dark'` (canonical default for "no OS preference")
- [ ] Script synchronously sets `document.documentElement.setAttribute('data-theme', resolved)` on initial run (before render)
- [ ] Script installs change listeners on BOTH media queries (so live OS preference response works for both light→dark and dark→light transitions while in auto mode)
- [ ] Script exposes `App.theme.set(preference)` (writes localStorage and re-resolves; `'auto'` removes the localStorage key)
- [ ] Script exposes `App.theme.get()` (returns the stored preference: `'dark'` | `'light'` | `'auto'`)
- [ ] Script exposes `App.theme.resolved()` (returns the currently-applied theme: `'dark'` | `'light'`)
- [ ] All localStorage access (`getItem`, `setItem`, `removeItem`) wrapped in try/catch — degrades gracefully in private browsing / Storage-disabled environments to in-memory non-persistent behavior
- [ ] Script attaches `App.theme` via `window.App = window.App || {}; window.App.theme = {...}` BEFORE app.js loads — and persists across app.js execution (verified by acceptance criterion below on app.js mutation pattern)
- [ ] Script does NOT add any UI — toggle UI lands in a later leg (sensible spot is leg 03 visual realization, or admin settings panel)

### HTML wiring
- [ ] `index.html` `<head>` contains `<style>@layer tokens, base, components, areas, utilities;</style>` declaration immediately after `<meta>` tags, BEFORE any other stylesheets or scripts
- [ ] `<head>` contains `<script src="/static/js/theme.js"></script>` BEFORE any `<link rel="stylesheet">` tags
- [ ] `<head>` contains `<link rel="stylesheet" href="/static/css/tokens.css">` BEFORE the existing `<link rel="stylesheet" href="/static/styles.css">`
- [ ] No other changes to index.html (existing div mountpoints, area script tags untouched)

### Behavioral
- [ ] On first load with no localStorage `theme-preference` AND test env `color_scheme="no-preference"`: `<html data-theme="dark">` (canonical default); page renders identically to pre-leg state
- [ ] If user toggles their OS to `prefers-color-scheme: light` while the app is open AND no preference is set: `data-theme` flips to `light` live without reload
- [ ] If `localStorage['theme-preference'] = 'light'` and reload: `<html data-theme="light">` (attribute changes; **no visible change** in leg 01 because tokens.css is inactive — see Context note. Will become visible in leg 02 once styles.css is wrapped in `@layer`)
- [ ] `App.theme.set('dark')` then reload: persists, `<html data-theme="dark">`
- [ ] `App.theme.set('auto')` then reload: removes localStorage key, follows OS preference

### App namespace mutation (app.js)
- [ ] `app.js` IIFE rewritten so `window.App` is mutated in place (not reassigned). After full page load (DOMContentLoaded), BOTH `window.App.theme.get()` returns a valid preference AND `window.App.registerArea` exists (and other existing exports: `escapeHtml`, `escapeAttr`, `formatBytes`, `showFlash`)
- [ ] All existing callers of `App.registerArea`, `App.escapeHtml`, etc. continue to work (verified via F1 browser tests passing)

### Test environment
- [ ] `tests/browser/conftest.py` `browser.new_context()` call passes `color_scheme="no-preference"`
- [ ] All F1 browser tests still pass with this change (no test relied on light-mode default)

### Suite-level
- [ ] All F1 browser tests still pass (`pytest -m browser tests/browser/` shows 8 passed)
- [ ] Default test suite passes (`pytest tests/` shows 350 passed, 16 deselected)
- [ ] No FOUC on page load (theme is applied before first paint — verify by reload with cache disabled)
- [ ] `ruff check` clean for any Python files touched (none expected — this is a pure frontend leg)

## Verification Steps

1. **Files exist**: `ls the_one/interfaces/web/static/css/tokens.css the_one/interfaces/web/static/js/theme.js`
2. **Token coverage**: `grep -c "^  --" the_one/interfaces/web/static/css/tokens.css` returns at least 16 (8 tokens × 2 themes)
3. **HTML wiring**: `grep -n "tokens\|theme.js\|@layer" the_one/interfaces/web/static/index.html` shows the three additions in correct order
4. **Tests**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=60
   ```
5. **Manual visual check**:
   ```bash
   docker compose up -d --build
   # Open http://localhost:8484 in browser; should look identical to pre-leg state
   # In DevTools console: App.theme.get()  → 'auto' (or whatever was set)
   # In DevTools console: App.theme.resolved() → 'dark'
   # In DevTools console: App.theme.set('light') → page should re-render with placeholder light theme
   # In DevTools console: App.theme.set('auto') → returns to OS preference
   ```
6. **FOUC check**: in DevTools, throttle network to "Slow 3G" and reload. Page should NOT flash white-then-dark; theme should apply with first paint.

## Implementation Guidance

### 1. Create `the_one/interfaces/web/static/css/tokens.css`

```css
/* Theme tokens — F2 scaffold leg.
 *
 * Dark-theme values match the pre-F2 :root block in styles.css exactly,
 * ensuring no visual change at this leg. Subsequent legs:
 *   - Leg 02 (apply-tokens) expands token coverage during refactor
 *   - Leg 03 (visual-realization) refines dark-theme values (NEXUS aesthetic)
 *   - Leg 06 (light-realization) designs the light theme properly
 *
 * Token groups: palette, typography, space, motion, density-and-geometry.
 * This leg only populates a minimal set; legs 02-06 expand coverage.
 */

@layer tokens {
  /* Native UI element theming (scrollbars, form controls, default selection). */
  :root {
    color-scheme: dark light;
  }

  [data-theme="dark"] {
    /* palette */
    --bg: #0a0a0a;
    --fg: #e0e0e0;
    --accent: #4a9eff;
    --surface: #1a1a1a;
    --border: #2a2a2a;
    --tool: #2d2d2d;

    /* density-and-geometry */
    --sidebar-w: 240px;
    --nav-w: 48px;
  }

  [data-theme="light"] {
    /* palette — placeholder values; redesigned in leg 06 */
    --bg: #fafafa;
    --fg: #1a1a1a;
    --accent: #2563eb;
    --surface: #ffffff;
    --border: #e5e7eb;
    --tool: #f3f4f6;

    /* density-and-geometry — same as dark */
    --sidebar-w: 240px;
    --nav-w: 48px;
  }
}
```

### 2. Create `the_one/interfaces/web/static/js/theme.js`

```javascript
/* Theme switcher — F2 scaffold leg.
 *
 * Tri-state preference (Light / Dark / Auto) persisted in localStorage under
 * "theme-preference". When "auto" or unset, follows prefers-color-scheme live.
 *
 * Runs in <head> BEFORE any stylesheet load to avoid FOUC. Exposes API on
 * App.theme; creates window.App if it doesn't yet exist (theme.js loads
 * before app.js, and app.js mutates window.App in place to preserve this).
 */

(function () {
  'use strict';

  var STORAGE_KEY = 'theme-preference';
  var darkMedia = window.matchMedia('(prefers-color-scheme: dark)');
  var lightMedia = window.matchMedia('(prefers-color-scheme: light)');

  // localStorage may throw in private-browsing / Storage-disabled contexts.
  function safeGet() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }
  function safeSet(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch (e) { /* no-op — degrade to non-persistent */ }
  }
  function safeRemove() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) { /* no-op */ }
  }

  function getPreference() {
    var pref = safeGet();
    if (pref === 'dark' || pref === 'light' || pref === 'auto') return pref;
    return 'auto';
  }

  function resolve(pref) {
    if (pref === 'dark' || pref === 'light') return pref;
    // 'auto': follow OS if it has a preference; else default to dark.
    if (darkMedia.matches) return 'dark';
    if (lightMedia.matches) return 'light';
    return 'dark'; // no OS preference — our canonical default
  }

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  function reapply() {
    apply(resolve(getPreference()));
  }

  // Synchronous initial application — runs before render.
  apply(resolve(getPreference()));

  // Live OS-preference response when in auto mode (listen on BOTH queries).
  function onMediaChange() {
    if (getPreference() === 'auto') reapply();
  }
  darkMedia.addEventListener('change', onMediaChange);
  lightMedia.addEventListener('change', onMediaChange);

  // Public API (App.theme).
  window.App = window.App || {};
  window.App.theme = {
    get: function () { return getPreference(); },
    resolved: function () {
      return document.documentElement.getAttribute('data-theme');
    },
    set: function (pref) {
      if (pref !== 'dark' && pref !== 'light' && pref !== 'auto') {
        throw new Error('Invalid theme preference: ' + pref);
      }
      if (pref === 'auto') {
        safeRemove();
      } else {
        safeSet(pref);
      }
      reapply();
    }
  };
})();
```

### 3. Update `the_one/interfaces/web/static/js/app.js` (App namespace mutation)

The current `app.js:1` opens with `var App = (function() { ... })()` which CLOBBERS any existing `window.App` (including `App.theme` registered by theme.js). Fix: rewrite the IIFE to mutate `window.App` in place.

Read the file first to see the current shape, then transform it from:

```javascript
var App = (function () {
  // ... internal state ...
  return {
    registerArea: ...,
    escapeHtml: ...,
    escapeAttr: ...,
    formatBytes: ...,
    showFlash: ...,
  };
})();
```

to:

```javascript
(function () {
  // ... internal state ...
  window.App = window.App || {};
  window.App.registerArea = ...;
  window.App.escapeHtml = ...;
  window.App.escapeAttr = ...;
  window.App.formatBytes = ...;
  window.App.showFlash = ...;
})();
```

OR (cleaner, single assignment):

```javascript
(function () {
  // ... internal state ...
  window.App = window.App || {};
  Object.assign(window.App, {
    registerArea: ...,
    escapeHtml: ...,
    escapeAttr: ...,
    formatBytes: ...,
    showFlash: ...,
  });
})();
```

The `Object.assign` form preserves existing properties (e.g., `App.theme` from theme.js) while adding the IIFE's exports. Either form is acceptable; `Object.assign` is preferred for clarity.

After this change, F1's existing usage (`App.registerArea({...})` etc.) is unaffected — same property names, same behavior, just attached to the global rather than reassigning it.

### 4. Update `tests/browser/conftest.py` (Playwright color_scheme)

In the `page` fixture (around line 174), `browser.new_context()` is called with no color_scheme argument — defaulting to Playwright's `"light"`. Add `color_scheme="no-preference"` so the test environment matches the canonical "no OS preference → default to dark" behavior the app relies on:

```python
context = browser.new_context(color_scheme="no-preference")
```

This is a one-keyword-argument addition. F1's existing 8 browser tests don't make CSS-value assertions, so they continue passing.

### 5. Update `the_one/interfaces/web/static/index.html`

Replace the `<head>` block from:

```html
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>the-one</title>
<link rel="stylesheet" href="/static/styles.css">
</head>
```

to:

```html
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>the-one</title>
<style>@layer tokens, base, components, areas, utilities;</style>
<script src="/static/js/theme.js"></script>
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/styles.css">
</head>
```

> **Why the `<style>@layer ...;</style>` declaration is FIRST**: cascade layer order is established by the FIRST appearance of `@layer NAME`. Declaring all layer names up front (before any layer is populated by linked stylesheets) pins the order regardless of `<link>` order in the rest of the head or any future additions.

> **Why theme.js is BEFORE the stylesheet links**: synchronous JavaScript in `<head>` blocks rendering. The script sets `data-theme` on `<html>` before the browser parses any stylesheets, so when the styles cascade resolves on first paint, the `[data-theme="dark"]` (or `light`) selector is already matching. No flash.

> **Why tokens.css before styles.css**: tokens.css is wrapped in `@layer tokens` (lowest in the cascade); styles.css is currently unlayered, which means it lives in an "implicit final layer" that wins over named layers. So link order doesn't actually matter for cascade — but ordering tokens first is conventional and helps human readers. Leg 02 wraps styles.css's contents in appropriate `@layer` directives, at which point cascade order DOES depend on layer names.

### 6. Run verification

```bash
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
```

Expect: 350 passed / 16 deselected; 8 browser tests passed.

Then manual visual check:

```bash
docker compose up -d --build
```

Open http://localhost:8484 — should look identical to pre-leg. In DevTools console:

```javascript
App.theme.get()        // 'auto' (or 'dark' if set previously)
App.theme.resolved()   // 'dark'
App.theme.set('light') // page re-renders with placeholder light theme
App.theme.set('auto')  // returns to OS preference (likely dark)
```

## Edge Cases

- **`localStorage` unavailable** (private browsing, browser denies): `localStorage.getItem` throws. Wrap reads/writes in try/catch and fall back to `'auto'` for reads, no-op for writes. Acceptable degradation: theme just won't persist.

- **`matchMedia` unavailable** (very old browsers): `window.matchMedia('(prefers-color-scheme: dark)')` could return undefined/null. Wrap the queries; if undefined, treat as no-preference (default to dark).

- **`App` global already exists when theme.js runs**: `window.App = window.App || {}` is idempotent — assigning to it is safe regardless. The order is theme.js BEFORE app.js, so on a clean load `App` won't exist yet, but the safe init handles both orders.

- **Test environment**: pytest browser tests use a Chromium instance launched with `headless=True` (no OS preference). On first load, `darkMedia.matches` is false and `lightMedia.matches` may be false (Chromium default is no-preference in headless). Our default-to-dark behavior means tests see `data-theme="dark"`, matching the F1 test assumptions.

- **`data-theme` set before `<body>` renders**: Setting attribute on `<html>` from `<head>` script is the standard pattern. Verified safe: at the time theme.js runs, `document.documentElement` is the `<html>` element (already exists in the DOM tree before `<body>`).

- **CSS `@layer` browser support**: Supported in all browsers Playwright runs (Chrome 99+, Firefox 97+, Safari 15.4+ — all 2022). Not an issue.

- **Caching**: The `<link>` and `<script>` URLs are static paths — FastAPI's StaticFiles serves them with default cache headers. If a user has the old styles.css cached and the new tokens.css is fresh, the cascade should still work (browsers parse both in any order). No special cache-busting needed for this leg.

- **Browser tests asserting on visible CSS**: F1's flow tests don't make pixel-perfect visual assertions — they assert on text content and element presence. So even if the placeholder light theme is ugly, tests pass as long as elements render and text content is correct. Confirmed via review.

## State-Machine Reachability Audit

**State introduced**: `data-theme` attribute on `<html>` (values: `'dark'` | `'light'`); `theme-preference` localStorage key (values: `'dark'` | `'light'` | `'auto'` | absent).

Lower layers verified:
- No DB schema changes
- No FK/CHECK constraints relevant
- No application caches affected (theme.js maintains its own state in localStorage)
- No existing tests pin behavior this leg breaks: F1 tests rely on functional behavior (DOM elements present, text content correct), not on specific CSS values

✓ Pass.

## Cache Freshness Contract

**Cache 1 — `data-theme` attribute on `<html>`**:
- Source of truth: localStorage `theme-preference` + `prefers-color-scheme` media query (when preference is auto/unset)
- Rebuild trigger: page load (synchronous on first paint), `App.theme.set()`, `matchMedia` change event (when in auto mode)
- Maximum staleness acceptable: instantaneous (theme changes apply immediately, no reload required)
- User-action invalidation map:
  - User toggles via `App.theme.set(...)` → re-resolves and re-applies immediately
  - User changes OS preference while app open and in auto mode → matchMedia event fires → re-resolves and re-applies
  - User opens a new tab (cross-tab) → re-reads localStorage on load (storage event listener could be added but not required for this leg)

**Cache 2 — `localStorage['theme-preference']`**:
- Source of truth: user toggle action
- Rebuild trigger: explicit set via `App.theme.set()`
- Maximum staleness acceptable: until user re-toggles
- User-action invalidation map: only `App.theme.set()` writes; reads happen on every page load

✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — new file (~35 lines)
- `the_one/interfaces/web/static/js/theme.js` — new file (~80 lines)
- `the_one/interfaces/web/static/index.html` — modified (add `<style>@layer ...;</style>`, `<script src="theme.js">`, `<link rel="stylesheet" href="tokens.css">`; ~3 lines added in `<head>`)
- `the_one/interfaces/web/static/js/app.js` — modified (IIFE rewritten to mutate `window.App` in place via `Object.assign`; ~5 lines changed near top of file)
- `tests/browser/conftest.py` — modified (add `color_scheme="no-preference"` to `browser.new_context()` call; 1 line)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 350 passed, 16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [ ] Manual visual check: app looks identical to pre-leg state in default mode; toggle to light shows placeholder light theme (visibly different); toggle to auto follows OS preference; toggle to dark restores
- [ ] No FOUC observed on reload
- [ ] Update flight-log.md with leg progress entry (status, what was done, any anomalies)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (happens at flight-level commit time per agentic-workflow protocol)
- [ ] Do NOT commit (flight-level review and commit happen after the last autonomous leg)
- [ ] Signal `[HANDOFF:review-needed]`
