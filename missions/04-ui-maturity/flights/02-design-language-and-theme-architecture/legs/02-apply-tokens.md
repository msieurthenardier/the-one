# Leg: 02-apply-tokens

**Status**: landed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Activate the theme architecture by (1) expanding `tokens.css` to cover every hardcoded color and density value found in `styles.css`, (2) splitting `styles.css` into multiple files under `css/` with proper `@layer` directives (which causes the unlayered `:root` to no longer win cascade), (3) replacing every hex literal and rgba value in CSS with token references, (4) converting `admin.js`'s `TYPE_BADGE_COLORS` JS dictionary to a class-name pattern with per-type CSS rules backed by tokens. **Pure refactor — no visual change.** F1 browser tests must pass identically.

## Context

- This is the leg where tokens.css "comes alive" — leg 01 was the scaffold, leg 02 activates it.
- Per the flight design and the Round 2 review of the flight: cascade layers `tokens, base, components, areas, utilities`. Each component file opens with the appropriate `@layer NAME { ... }` directive.
- **The "no visual change" guarantee** depends on: every hex/rgba literal in `styles.css` having a corresponding token in tokens.css with EXACT matching dark-theme value. Light-theme values are placeholder-quality (redesigned in leg 06).
- After this leg, `tokens.css`'s `[data-theme="dark"]` block actually drives rendering — toggling `App.theme.set('light')` will produce a VISIBLE change for the first time. (Light theme will look ugly because values are placeholder; that's expected.)
- **Leg 01 outcome**: tokens.css exists with 8 tokens; theme.js + tri-state toggle wired; `@layer tokens, base, components, areas, utilities;` declared in HTML head; app.js refactored to mutate `window.App`. Test baseline: 350 passed, 16 deselected; 8 browser tests passing.
- **TYPE_BADGE_COLORS removal**: `admin.js:47-53` currently maps provider types to hex literals; the inline `style="background: " + badgeColor` injection at `admin.js:339` is a JS-side color literal that bypasses tokens. The leg converts this to per-type CSS classes (`admin-provider-badge--ollama` etc.) backed by tokens. The `'#888'` fallback at line 336 becomes `'unknown'` class with its own token-backed style.
- **SVG arrow exception**: `styles.css:154` has a `data:image/svg+xml,...%23888...` URL with `#888` encoded as `%23888`. CSS variables can't be used inside data URLs. Two options: (a) keep as exception with grep allowlist, (b) replace with `currentColor` referenced via SVG `<use>`. Going with (a) — minimal scope; option (b) belongs in F3 form-primitive extraction.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, leg 01 landed (uncommitted)
- `the_one/interfaces/web/static/styles.css` — 363 lines, ~50+ hex literals, 3 rgba values, 1 SVG arrow exception
- `the_one/interfaces/web/static/css/tokens.css` (from leg 01) — 8 tokens × 2 themes
- `the_one/interfaces/web/static/index.html` (from leg 01) — has `@layer` declaration + theme.js + tokens.css link
- `the_one/interfaces/web/static/js/areas/admin.js` — TYPE_BADGE_COLORS at lines 47-53, badge render at line 339
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing

## Outputs

**CSS file split** (under `the_one/interfaces/web/static/css/`):
- `tokens.css` (extended) — expanded with ~30+ new tokens covering all hex/rgba values
- `base.css` (new) — reset (`* {}`, `html`/`body`), shell layout (`#app-nav`, `#app-sidebar`, `#app-content`), nav-item, sidebar-panel, content-panel, stub-*. Wraps in `@layer base { ... }`
- `components.css` (new) — truly shared components: `.app-flash` (the only one currently). Wraps in `@layer components { ... }`. Will grow significantly in F3.
- `chat.css` (new) — `.area-chat .*` rules (lines 69-121 of styles.css). Wraps in `@layer areas { ... }`
- `studio.css` (new) — `.area-studio .*` rules (lines 123-203 of styles.css). Wraps in `@layer areas { ... }`
- `admin.css` (new) — `.area-admin .*` rules (lines 210-357 of styles.css), PLUS new `.admin-provider-badge--{type}` rules for the badge color migration. Wraps in `@layer areas { ... }`

**Files modified**:
- `the_one/interfaces/web/static/styles.css` — DELETED (or shrunk to empty file with comment; either is fine)
- `the_one/interfaces/web/static/index.html` — `<link rel="stylesheet" href="/static/styles.css">` removed; replaced with 5 new links to `base.css`, `components.css`, `chat.css`, `studio.css`, `admin.css`
- `the_one/interfaces/web/static/js/areas/admin.js` — `TYPE_BADGE_COLORS` removed; per-type class logic replaces inline-style injection at line 339; `'#888'` fallback replaced with `'unknown'` class lookup

## Acceptance Criteria

### Token coverage
- [ ] `tokens.css` `[data-theme="dark"]` block contains tokens for EVERY hardcoded value found in styles.css. Specifically (each hex value must have at least one corresponding token):
  - **Surfaces**: `--bg` (#0a0a0a), `--surface` (#1a1a1a), `--surface-elevated` (#333 — used for tool-switch off bg), `--surface-tool` (#2d2d2d, was --tool)
  - **Borders**: `--border` (#2a2a2a), `--border-hover` (#444 — used by `:hover { border-color }` rules), `--border-strong` (#666 — used by `:hover { border-color: #666 }` rules)
  - **Text**: `--fg` (#e0e0e0), `--fg-secondary` (#888), `--fg-tertiary` (#666), `--fg-muted` (#555), `--fg-faint` (#444), `--fg-on-accent` (#000), `--fg-on-accent-muted` (#333 — used for muted text on accent-hover, e.g. line 349 suggestion-size hover), `--fg-on-danger` (#fff), `--fg-tool-msg` (#999)
  - **Accent**: `--accent` (#4a9eff), `--accent-api` (#7c4dff)
  - **Status**: `--status-success` (#2ecc71), `--status-warning` (#f5a623), `--status-warning-bg-soft` (rgba(245, 166, 35, 0.08)), `--status-warning-bg-soft-2` (rgba(245, 166, 35, 0.1)), `--status-warning-border` (rgba(245, 166, 35, 0.3)), `--status-danger` (#ff4a4a)
  - **Provider badges**: `--badge-ollama` (#2ecc71), `--badge-openai-compatible` (#d4a800), `--badge-openai` (#4a9eff), `--badge-anthropic` (#9b59b6), `--badge-mock` (#888), `--badge-unknown` (#888)
  - **Density-and-geometry**: `--sidebar-w` (240px), `--nav-w` (48px) — unchanged
- [ ] `tokens.css` `[data-theme="light"]` block contains corresponding light-theme values for ALL the same tokens (placeholder quality — redesigned in leg 06)

### File split with layers
- [ ] `the_one/interfaces/web/static/css/base.css` exists, opens with `@layer base { ... }`, contains: reset, `html`/`body`, `#app-nav`, `.nav-item`, `.nav-item.active`, `.nav-item.active::before`, `#app-sidebar`, `.sidebar-panel`, `.sidebar-panel.active`, `#app-content`, `.content-panel`, `.content-panel.active`, `.stub-content`, `.stub-sidebar`, `.stub-sidebar .title`, `.stub-sidebar .subtitle`
- [ ] `css/components.css` exists, opens with `@layer components { ... }`, contains: `.app-flash`, `.app-flash.visible`, `.app-flash.error`
- [ ] `css/chat.css` exists, opens with `@layer areas { ... }`, contains all `.area-chat .*` rules
- [ ] `css/studio.css` exists, opens with `@layer areas { ... }`, contains all `.area-studio .*` rules
- [ ] `css/admin.css` exists, opens with `@layer areas { ... }`, contains all `.area-admin .*` rules PLUS new `.admin-provider-badge--{type}` rules with token-backed `background-color`

### Hex literal elimination
- [ ] Grep check returns ZERO results: `grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css | grep -v tokens.css | grep -v "data:image/svg"` produces no matches
- [ ] Grep check on JS files returns ZERO results: `grep -rnE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/js/` produces no matches (the SVG arrow data URL exception is in CSS only — admin.js's removed `TYPE_BADGE_COLORS` is the only JS color leak, now eliminated). Use `grep -r` (POSIX, works in dash/sh), NOT bash globstar `**/*.js` which requires `shopt -s globstar`.

### admin.js refactor
- [ ] `TYPE_BADGE_COLORS` constant (admin.js:47-53) is REMOVED
- [ ] A new constant `TYPE_BADGE_CLASSES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock']` (or similar — the list of known type values) replaces it; or the logic uses an inline check
- [ ] The badge render at admin.js:339 uses `<span class="admin-provider-badge admin-provider-badge--{suffix}">` where `{suffix}` is `p.type` if known, `'unknown'` otherwise — NOT inline `style="background:..."`
- [ ] All 5 known provider types (`ollama`, `openai-compatible`, `openai`, `anthropic`, `mock`) have corresponding `.admin-provider-badge--{type}` rules in `admin.css` with `background-color: var(--badge-{type})`
- [ ] `.admin-provider-badge--unknown` rule exists with `background-color: var(--badge-unknown)`

### HTML wiring
- [ ] `index.html` `<head>` has the OLD `<link rel="stylesheet" href="/static/styles.css">` removed
- [ ] `<head>` has 5 new links (in this order, after tokens.css): `base.css`, `components.css`, `chat.css`, `studio.css`, `admin.css`
- [ ] Existing `<style>@layer ...;</style>` declaration, theme.js script, and tokens.css link remain unchanged

### styles.css cleanup
- [ ] `the_one/interfaces/web/static/styles.css` is either DELETED or REDUCED to a comment-only file (e.g., `/* See css/ subdirectory — split during F2 leg 02. */`)

### Tests
- [ ] All F1 browser tests still pass (`pytest -m browser tests/browser/` shows 8 passed)
- [ ] Default `pytest tests/` shows 350 passed, 16 deselected
- [ ] No visual regression: app looks identical to pre-leg state in default dark mode (verify manually OR via Playwright screenshot before/after)

### Cascade verification
- [ ] Manually toggle `App.theme.set('light')` in the running app. UI should now visibly change to placeholder light values (light backgrounds, dark text). This is the FIRST leg where toggling has visible effect — confirms tokens are wired and active.
- [ ] `App.theme.set('auto')` returns to dark (since `color_scheme="no-preference"` resolves to dark).

## Verification Steps

1. **Files exist with correct structure**: `ls the_one/interfaces/web/static/css/` shows: `tokens.css`, `base.css`, `components.css`, `chat.css`, `studio.css`, `admin.css`
2. **Layer wrapping**: `head -1 the_one/interfaces/web/static/css/{base,components,chat,studio,admin}.css` shows `@layer NAME {` for each
3. **No hex/rgba leaks**:
   ```bash
   grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
     | grep -v tokens.css | grep -v "data:image/svg"
   ```
   Expected: empty output (no matches)
4. **No JS color literals**:
   ```bash
   grep -rnE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/js/
   ```
   Expected: empty output
5. **Tests**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=60
   ```
   Expected: 350/16 deselected; 8 browser tests pass
6. **Manual visual verification**:
   ```bash
   docker compose up -d --build
   # Open http://localhost:8484 — should look identical to pre-leg
   # In DevTools: App.theme.set('light')
   # Page should now visibly switch to placeholder light theme (white-ish bg, dark text)
   # In DevTools: App.theme.set('auto')
   # Page returns to dark
   ```

## Implementation Guidance

### Strategy

This is a large mechanical refactor. Recommended order:

1. **Expand tokens.css FIRST** with all new tokens (both dark + light blocks). Don't change anything else yet — verify the file parses correctly.
2. **Catalog every hex/rgba in styles.css** by scanning the file. Map each to its token.
3. **Create the 5 new component CSS files** by copying sections from styles.css, wrapping in `@layer NAME { ... }`, and replacing hex/rgba with `var(--token)` references.
4. **Update admin.js** for the badge class refactor.
5. **Update index.html** to link the new files; remove the old link.
6. **Delete styles.css** (or empty it).
7. **Run grep checks + tests** to verify.

### 1. Expand `tokens.css`

Replace the existing `[data-theme="dark"]` and `[data-theme="light"]` blocks with the expanded versions covering all tokens. Keep the existing `:root { color-scheme: dark light; }` declaration. Token groups in comments help future readers.

```css
@layer tokens {
  :root {
    color-scheme: dark light;
  }

  [data-theme="dark"] {
    /* surfaces */
    --bg: #0a0a0a;
    --surface: #1a1a1a;
    --surface-elevated: #333333;
    --surface-tool: #2d2d2d;

    /* borders */
    --border: #2a2a2a;
    --border-hover: #444444;
    --border-strong: #666666;

    /* text */
    --fg: #e0e0e0;
    --fg-secondary: #888888;
    --fg-tertiary: #666666;
    --fg-muted: #555555;
    --fg-faint: #444444;
    --fg-on-accent: #000000;
    --fg-on-accent-muted: #333333;
    --fg-on-danger: #ffffff;
    --fg-tool-msg: #999999;

    /* accent */
    --accent: #4a9eff;
    --accent-api: #7c4dff;

    /* status */
    --status-success: #2ecc71;
    --status-warning: #f5a623;
    --status-warning-bg-soft: rgba(245, 166, 35, 0.08);
    --status-warning-bg-soft-2: rgba(245, 166, 35, 0.1);
    --status-warning-border: rgba(245, 166, 35, 0.3);
    --status-danger: #ff4a4a;

    /* provider badges */
    --badge-ollama: #2ecc71;
    --badge-openai-compatible: #d4a800;
    --badge-openai: #4a9eff;
    --badge-anthropic: #9b59b6;
    --badge-mock: #888888;
    --badge-unknown: #888888;

    /* density-and-geometry */
    --sidebar-w: 240px;
    --nav-w: 48px;
  }

  [data-theme="light"] {
    /* surfaces */
    --bg: #fafafa;
    --surface: #ffffff;
    --surface-elevated: #e5e7eb;
    --surface-tool: #f3f4f6;

    /* borders */
    --border: #e5e7eb;
    --border-hover: #d1d5db;
    --border-strong: #9ca3af;

    /* text */
    --fg: #1a1a1a;
    --fg-secondary: #4b5563;
    --fg-tertiary: #6b7280;
    --fg-muted: #9ca3af;
    --fg-faint: #d1d5db;
    --fg-on-accent: #ffffff;
    --fg-on-accent-muted: #d1d5db;
    --fg-on-danger: #ffffff;
    --fg-tool-msg: #6b7280;

    /* accent */
    --accent: #2563eb;
    --accent-api: #7c3aed;

    /* status */
    --status-success: #16a34a;
    --status-warning: #d97706;
    --status-warning-bg-soft: rgba(217, 119, 6, 0.08);
    --status-warning-bg-soft-2: rgba(217, 119, 6, 0.1);
    --status-warning-border: rgba(217, 119, 6, 0.3);
    --status-danger: #dc2626;

    /* provider badges — same brand colors in both themes (badges identify
       the provider, NOT the theme; brand stability over palette consistency) */
    --badge-ollama: #2ecc71;
    --badge-openai-compatible: #d4a800;
    --badge-openai: #4a9eff;
    --badge-anthropic: #9b59b6;
    --badge-mock: #888888;
    --badge-unknown: #888888;

    /* density-and-geometry */
    --sidebar-w: 240px;
    --nav-w: 48px;
  }
}
```

### 2. Catalog mapping (hex literal → token)

Quick reference for the substitution pass. Apply per-line as you split styles.css into the new files:

| Source hex | Token replacement | Used in |
|---|---|---|
| `#0a0a0a` | `var(--bg)` | (already a token) |
| `#1a1a1a` | `var(--surface)` | (already a token; one duplicate at line 94) |
| `#2a2a2a` | `var(--border)` | (already a token) |
| `#2d2d2d` | `var(--surface-tool)` | (was `var(--tool)` — rename references) |
| `#444` | `var(--border-hover)` (in border-color contexts) OR `var(--fg-faint)` (in color contexts) | lines 92, 234, 260 |
| `#555` | `var(--fg-muted)` | lines 83, 84, 86, 92, 99, 130 (etc.) |
| `#666` | `var(--fg-tertiary)` (in color) OR `var(--border-strong)` (in border-color) | lines 75, 89, 92, 127, 167, 186, etc. |
| `#888` | `var(--fg-secondary)` | many lines |
| `#999` | `var(--fg-tool-msg)` | line 113 |
| `#000` | `var(--fg-on-accent)` for lines 110, 120, 194, 206, 261, 298, 300, 347, 350 (text on accent or accent-hovered bg, plus line 261 provider-badge text). **Line 199 is a pre-existing inconsistency** (`color: #000` on `--status-danger` bg, while lines 208/248/268/335 use `#fff` on the same bg) — normalize line 199 to `var(--fg-on-danger)` for consistency with the other danger-confirm states. | (see note) |
| `#fff` | `var(--fg-on-accent)` for line 174 (toggle thumb on accent ON state). `var(--fg-on-danger)` for lines 208, 248, 268, 335 (text on danger bg). | (see note) |
| `#333` | `var(--surface-elevated)` for line 171 (tool-switch off bg). `var(--fg-on-accent-muted)` for line 349 (suggestion-size text on hovered accent bg). | line 171, line 349 |
| `#e0e0e0` | `var(--fg)` | (already a token) |
| `#4a9eff` | `var(--accent)` | (already a token) |
| `#7c4dff` | `var(--accent-api)` | line 111 |
| `#ff4a4a` | `var(--status-danger)` | many lines |
| `#f5a623` | `var(--status-warning)` | lines 96, 101, 105, 202, 244 |
| `#2ecc71` | `var(--status-success)` | lines 251, 306, 327 |
| `rgba(245, 166, 35, 0.08)` | `var(--status-warning-bg-soft)` | line 202 |
| `rgba(245, 166, 35, 0.1)` | `var(--status-warning-bg-soft-2)` | line 244 |
| `rgba(245, 166, 35, 0.3)` | `var(--status-warning-border)` | line 244 |
| `var(--tool)` | `var(--surface-tool)` | line 113 (existing token reference, renamed) |

> **Note on context-dependent substitution**: `#000` appears in different semantic contexts. When it's text-on-accent (e.g., `.area-chat .msg.user { color: #000 }` where bg is `var(--accent)`), use `var(--fg-on-accent)`. When it's something else (rare in this codebase), evaluate semantically. Same with `#fff`.

### 3. Create the 5 component CSS files

For each file, the structure is:

```css
@layer LAYER_NAME {
  /* === Section title === */
  .selector { property: var(--token); }
  ...
}
```

**`base.css`** — wraps lines 12-13 (reset + body), lines 15-50 (#app-nav and .nav-item), lines 52-67 (#app-sidebar/.sidebar-panel and #app-content/.content-panel), lines 359-363 (.stub-*) — all in `@layer base { ... }`.

**`components.css`** — wraps lines 205-208 (.app-flash) — in `@layer components { ... }`. Will grow when F3 extracts shared form/button primitives; for now it's small.

**`chat.css`** — wraps lines 69-121 — in `@layer areas { ... }`.

**`studio.css`** — wraps lines 123-203 — in `@layer areas { ... }`.

**`admin.css`** — wraps lines 210-357 — in `@layer areas { ... }`. ALSO add new badge class rules at the end:

```css
  /* Provider type badges (per-type background — replaces JS-side TYPE_BADGE_COLORS) */
  .area-admin .admin-provider-badge--ollama { background: var(--badge-ollama); }
  .area-admin .admin-provider-badge--openai-compatible { background: var(--badge-openai-compatible); }
  .area-admin .admin-provider-badge--openai { background: var(--badge-openai); }
  .area-admin .admin-provider-badge--anthropic { background: var(--badge-anthropic); }
  .area-admin .admin-provider-badge--mock { background: var(--badge-mock); }
  .area-admin .admin-provider-badge--unknown { background: var(--badge-unknown); }
```

### 4. Update `admin.js`

Find the `TYPE_BADGE_COLORS` constant (lines 47-53):

```javascript
var TYPE_BADGE_COLORS = {
  'ollama': '#2ecc71',
  'openai-compatible': '#d4a800',
  'openai': '#4a9eff',
  'anthropic': '#9b59b6',
  'mock': '#888'
};
```

Replace with:

```javascript
var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock'];
```

Find the badge rendering at line 336-339 (currently uses `TYPE_BADGE_COLORS[p.type] || '#888'` and inline `style="background:..."`). Replace with class-based:

```javascript
var typeSuffix = KNOWN_BADGE_TYPES.indexOf(p.type) >= 0 ? p.type : 'unknown';
html +=
  '<div class="admin-provider-card" role="listitem" data-testid="provider-card" data-id="' + escapeAttr(p.id) + '">' +
    '<span class="admin-provider-badge admin-provider-badge--' + escapeAttr(typeSuffix) + '">' + escapeHtml(p.type) + '</span>' +
    '<span class="admin-provider-name">' + escapeHtml(p.name) + '</span>' +
    ...
```

Note: `escapeAttr(typeSuffix)` is defensive (typeSuffix is from a controlled allow-list, but defensive escaping costs nothing).

### 5. Update `index.html`

Current `<head>` (post-leg-01):

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

Replace the LAST line (`<link ... styles.css>`) with five new links:

```html
<link rel="stylesheet" href="/static/css/base.css">
<link rel="stylesheet" href="/static/css/components.css">
<link rel="stylesheet" href="/static/css/chat.css">
<link rel="stylesheet" href="/static/css/studio.css">
<link rel="stylesheet" href="/static/css/admin.css">
```

### 6. Remove or empty `styles.css`

```bash
rm the_one/interfaces/web/static/styles.css
```

Or leave a comment-only file:

```css
/* Split into css/ subdirectory during F2 leg 02. See css/{base,components,chat,studio,admin}.css. */
```

### 7. Run verification

```bash
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
  | grep -v tokens.css | grep -v "data:image/svg"
grep -rnE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/js/
ruff check tests/
```

If grep returns ANY results from CSS (other than tokens.css / SVG arrow), or from JS, the refactor missed something. Fix and re-run.

## Edge Cases

- **The SVG arrow exception** at line 154 of styles.css (`background-image: url("data:image/svg+xml,...%23888...")`) is `studio.css`-bound after split. Leave the `%23888` (URL-encoded `#888`) inline; document with a CSS comment that this is an exception. The grep filter `grep -v "data:image/svg"` allowlists it.

- **Cascade ordering after split**: tokens.css is `@layer tokens` (lowest); base.css is `@layer base`; components.css is `@layer components`; chat/studio/admin.css are `@layer areas`. After this leg, when the user toggles to light theme, `[data-theme="light"]` block in tokens.css now wins because the unlayered `:root` from styles.css is gone. **This is the activation moment.**

- **`var(--tool)` references**: leg 01 kept `--tool: #2d2d2d`. Leg 02 renames to `--surface-tool`. Update all references (line 113 in chat: `.area-chat .msg.tool { background: var(--tool); }` becomes `var(--surface-tool)`). The token rename is a semantic improvement; the value is the same.

- **`#1a1a1a` hardcoded at line 94**: `.area-chat .context-bar-wrap` has `background: #1a1a1a` instead of `var(--surface)`. Same value, but using the token is cleaner. Replace.

- **#666 disambiguation**: Used in two contexts. As `color: #666` (text), use `var(--fg-tertiary)`. As `border-color: #666` (typically in `:hover` rules), use `var(--border-strong)`. Read each occurrence in context.

- **#444 disambiguation**: Same — `color: #444` → `var(--fg-faint)`, `border-color: #444` → `var(--border-hover)`.

- **`#000` and `#fff` semantic intent**: Always check the surrounding rule. `color: #000` after a rule that sets `background: var(--accent)` → `var(--fg-on-accent)`. `color: #fff` after `background: var(--status-danger)` → `var(--fg-on-danger)`. If neither — rare — use the most appropriate token.

- **Test environment**: F1 browser tests pass in dark theme (no preference resolved to dark). After this leg, if tokens are correctly wired, dark-theme rendering matches pre-leg pixel-for-pixel. Tests don't make pixel assertions; they assert on element presence and text — should pass identically.

- **Cache busting**: Browser may cache the old `/static/styles.css`. If a developer reloads and gets the old file (now 404 or empty), they'll see broken styles. `Cmd+Shift+R` (hard reload) clears. For end users on a deployed instance, the build/deploy pipeline rebuilds the image so cache is naturally busted.

- **Light-theme placeholder values intentionally fail WCAG AA in places**: `--fg-muted: #9ca3af` on `--bg: #fafafa` is ~2.9:1 (fails 4.5:1 body-text AA); `--fg-faint: #d1d5db` on same bg is ~1.6:1 (also fails). These are placeholder values for leg 02; leg 06 (light-realization) and leg 07 (a11y-audit) bring them up to WCAG AA. **When manually verifying this leg in light theme, expect some illegible muted text — this is expected, not a regression.**

- **`:root { color-scheme: dark light }` rule is preserved in tokens.css**: The flight design says "no `:root` shortcut" for theme tokens. This rule is NOT a theme token — `color-scheme` is a meta-property informing native browser widget rendering (scrollbars, form controls, default selection color). Keeping this in `:root` is consistent with the design intent (don't put theme tokens in `:root`, but non-token meta-properties are fine).

## State-Machine Reachability Audit

**State exercised**: `data-theme` attribute (existing); CSS layer cascade (newly relevant — leg 01 declared layers, leg 02 makes them load-bearing).

Lower layers verified:
- `@layer` browser support: all browsers Playwright runs (Chromium 99+, Firefox 97+, Safari 15.4+) — verified during F2 design review
- No DB schema changes
- No new JS state introduced (only TYPE_BADGE_COLORS removed)
- F1 browser test selectors (data-testid attributes) remain on the same elements — verified by reading admin.js: the rendering changes class lists but keeps `data-testid="provider-card"` on the parent `<div>`

✓ Pass.

## Cache Freshness Contract

This leg introduces no new caches. The existing `data-theme` attribute and localStorage preference (from leg 01) continue to work; this leg activates their effect by removing the unlayered cascade winner.

✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — extended with ~30 new tokens × 2 themes (~60 new lines)
- `the_one/interfaces/web/static/css/base.css` — new (~50 lines, `@layer base`)
- `the_one/interfaces/web/static/css/components.css` — new (~10 lines, `@layer components`)
- `the_one/interfaces/web/static/css/chat.css` — new (~60 lines, `@layer areas`)
- `the_one/interfaces/web/static/css/studio.css` — new (~85 lines, `@layer areas`)
- `the_one/interfaces/web/static/css/admin.css` — new (~160 lines, `@layer areas`, includes new badge class rules)
- `the_one/interfaces/web/static/styles.css` — DELETED (or empty stub)
- `the_one/interfaces/web/static/index.html` — 1 link removed, 5 links added
- `the_one/interfaces/web/static/js/areas/admin.js` — TYPE_BADGE_COLORS removed (7 lines), badge render refactored (~3 lines changed)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 350 passed, 16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [ ] Both grep checks return zero results (CSS hex/rgba outside tokens.css; JS hex/rgba)
- [ ] Manual visual check: dark theme renders identical to pre-leg; toggle to light produces VISIBLE change (placeholder light theme — ugly is fine)
- [ ] Update flight-log.md with leg progress entry (status, what was done, anomalies, observation about tokens being newly active)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (happens at flight-level commit time)
- [ ] Do NOT commit
- [ ] Signal `[HANDOFF:review-needed]`
