# Leg: 03-visual-realization

**Status**: completed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Apply the NEXUS-style "clean tron" design language to the dark theme. This leg makes the visible aesthetic transformation: cyan accent, glowing panel borders, translucent surfaces, larger border radii, outlined-cyan buttons with hover-fill, `// SECTION` cyberpunk-style headers, status dots with subtle glow, and a deep gradient body backdrop. Light theme stays in placeholder state — leg 06 designs it properly. F1 browser tests must continue to pass (testids stable, DOM unchanged).

## Context

- This is THE leg where the UI visibly transforms. After this leg, the app should look distinctly tron/NEXUS-influenced in dark mode.
- **Leg 02 outcome**: tokens.css is now the active theme source; styles.css split into 5 component files under `css/`; `--accent: #4a9eff` (regular blue), all surfaces/borders/text driven by tokens.
- **Reference aesthetic**: clean tron at refined density (NEXUS dashboard images shared during planning) — NOT the dense Wikipedia-tool density. Cyan accents, glowing borders, translucent panels, geometric.
- **What changes**: token values (especially `--accent`), CSS rules across all component files, new design-language tokens (`--accent-glow`, `--accent-translucent`, `--panel-shadow-glow`, etc.), section-header `::before` pseudo-element for `//` prefix, body gradient backdrop.
- **What does NOT change**: DOM structure, class names, `data-testid` attributes, JS behavior, layout grids. F1's 14 testids remain on the same elements; no new IDs introduced.
- **Light theme**: stays placeholder. Leg 03 only ships designed dark; leg 06 ships designed light.
- **Design judgment is the leg's product**: acceptance criteria can describe the *moves* (cyan glow on borders, etc.) but the QUALITY is the implementer's craft. The HAT leg (09) is where the user gives final aesthetic feedback.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, legs 01-02 landed (uncommitted)
- `the_one/interfaces/web/static/css/tokens.css` — ~30 tokens × 2 themes (from leg 02)
- `the_one/interfaces/web/static/css/{base,components,chat,studio,admin}.css` — 5 component files (from leg 02)
- `the_one/interfaces/web/static/index.html` — wired for tokens, theme.js, layered cascade
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing
- Reference screenshots (from F2 mission planning): NEXUS dashboard chat-mode + dashboard-mode (the clean-tron exemplars)

## Outputs

**`tokens.css` updated**:
- `--accent` value changes from `#4a9eff` → `#22d3ee` (Tailwind cyan-400, dark theme)
- New design-language tokens added in dark block:
  - `--accent-glow: rgba(34, 211, 238, 0.25)` — for box-shadow glows
  - `--accent-glow-strong: rgba(34, 211, 238, 0.4)` — for active/focus glows
  - `--accent-translucent: rgba(34, 211, 238, 0.08)` — for translucent fills (active states)
  - `--accent-translucent-hover: rgba(34, 211, 238, 0.12)` — for hover fills on outlined buttons
  - `--surface-translucent: rgba(255, 255, 255, 0.02)` — subtle panel translucency over gradient bg
  - `--panel-radius: 10px` — design-language border-radius
  - `--panel-radius-sm: 6px` — smaller variant for chips/badges/inputs (kept smaller for density)
  - `--panel-shadow: 0 1px 0 rgba(255, 255, 255, 0.03), inset 0 1px 0 rgba(255, 255, 255, 0.02)` — subtle elevation
  - `--panel-shadow-glow: 0 0 12px var(--accent-glow)` — glow for active/hovered panels
  - `--bg-gradient: linear-gradient(180deg, #0e1428 0%, #050505 70%)` — body backdrop
  - (NO new `--accent-fg` token — the existing `--fg-on-accent: #000` (dark) / `#fff` (light) already serves text-on-accent. Keep using `--fg-on-accent` for ALL text-on-accent contexts including primary cyan accent, per-type badges, etc. Single semantic token, no migration ambiguity.)
- Light-theme block gets placeholder values for these new tokens (deeper cyan equivalents — refined in leg 06)

**`base.css` updated**:
- `body` background changes to `var(--bg-gradient)` (was solid `var(--bg)`)
- `body` font kept as monospace fallback (Geist comes in leg 04)

**`chat.css` / `studio.css` / `admin.css` updated** with the design language:
- Panels (cards, sidebar items, message bubbles, form rows): use `var(--panel-radius)`, subtle translucent overlay or `var(--surface)`, thin border with optional outer glow on hover/active
- Active sidebar items: translucent cyan fill (`var(--accent-translucent)`) + cyan border + soft glow
- Section headers (`.section-title`, `.admin-section-title`, similar): `::before` pseudo-element adds `// ` prefix in cyan
- Outlined buttons (transparent + cyan border + cyan text): hover fills with `var(--accent-translucent-hover)`. Specifically: `.new-chat`, `.new-agent-btn`, `.admin-provider-add-btn`, `.admin-provider-edit-btn`, `.admin-system-btn`, `.tool-actions button`, `.chip-add`, `.admin-pf-cancel`, `.admin-pf-models-refresh`. Existing primary CTAs (Save, Create, Send) keep filled-cyan style but may shift to use the new accent value.
- Status dots / model-loaded indicators: small circles get `box-shadow: 0 0 6px {color-glow}` for subtle glow
- Form inputs: focus state uses `outline: 1px solid var(--accent); box-shadow: 0 0 0 3px var(--accent-glow)` for visible cyan focus ring (improves a11y too)
- Chat user message bubble: uses `var(--accent)` background as before; text uses `var(--fg-on-accent)` (the new dark-on-cyan value); slight glow on the bubble (`box-shadow: 0 0 8px var(--accent-glow)`)
- Chat assistant message bubble: `var(--surface-translucent)` background + thin border + `var(--panel-radius)` border-radius
- Context bar (telemetry): the filled portion gets a subtle glow

**`components.css` updated**:
- `.app-flash` — keep accent fill, add subtle glow

## Acceptance Criteria

### Token updates
- [ ] `tokens.css` `[data-theme="dark"]` `--accent` value changed from `#4a9eff` to `#22d3ee`
- [ ] New tokens added to `[data-theme="dark"]`: `--accent-glow`, `--accent-glow-strong`, `--accent-translucent`, `--accent-translucent-hover`, `--surface-translucent`, `--panel-radius`, `--panel-radius-sm`, `--panel-shadow`, `--panel-shadow-glow`, `--bg-gradient`, `--accent-fg`
- [ ] Same tokens present in `[data-theme="light"]` with placeholder values (light-context cyan deeper, surface-translucent against light bg, etc.)
- [ ] `--fg-on-accent` is the single token for text on cyan-accent OR per-type badge backgrounds. Value stays `#000` in dark / `#fff` in light. No new accent-fg token introduced.
- [ ] `.msg.user.api` (purple `--accent-api` bg) explicitly verified readable: text uses `var(--fg-on-accent)` (#000 dark / #fff light); contrast against purple `#7c4dff` is ~6.4:1 dark / ~3.7:1 light (passes AA for body / large text respectively)
- [ ] Grep check still clean: no hex/rgba literals in component CSS files outside the SVG-arrow exception (note: rgba() values now appear in tokens.css for the glow tokens — that's expected and the grep filter `grep -v tokens.css` allows it)

### Body backdrop
- [ ] `base.css` `body` rule uses `background: var(--bg-gradient)` (or equivalent — gradient subtly visible from top to bottom)

### Section header `//` prefix
- [ ] Section header pseudo-element rule applied to ALL section-title classes:
  - `.area-studio .section-title::before { content: "// "; color: var(--accent); opacity: 0.6; }` (and equivalent for other selectors)
  - `.area-admin .admin-section-title::before` — same pattern
  - `.area-admin .admin-pf-models-title::before` — same pattern  
  - `.area-admin .admin-pf-section-label::before` — same pattern
  - `.area-studio .tool-group::before` — optionally apply (small-caps category headers); pick consistent style
- [ ] Prefix renders in cyan with reduced opacity, visually distinct from the title text

### Panels with cyan borders + glow
- [ ] `.area-admin .admin-provider-card` — has `border-radius: var(--panel-radius)`, `:hover` adds `border-color: var(--accent); box-shadow: var(--panel-shadow-glow)`
- [ ] `.area-chat .session-item.active` — uses `background: var(--accent-translucent); border: 1px solid var(--accent); box-shadow: var(--panel-shadow-glow)`
- [ ] `.area-studio .agent-item.active` — same active-state pattern
- [ ] `.area-admin .admin-category-item.active` — same active-state pattern
- [ ] Chat user message (`.area-chat .msg.user`) — keeps accent fill, adds glow: `box-shadow: 0 0 8px var(--accent-glow)`. Text color uses `var(--fg-on-accent)` (new dark-on-cyan value)
- [ ] Chat assistant message (`.area-chat .msg.assistant`) — `background: var(--surface-translucent); border: 1px solid var(--border); border-radius: var(--panel-radius)`

### Outlined-cyan buttons with hover-fill
- [ ] All "creation/affordance" buttons use the outlined-cyan pattern: `background: transparent; border: 1px solid var(--accent); color: var(--accent);` and on hover `background: var(--accent-translucent-hover)`. Specific selectors:
  - `.area-chat .new-chat`
  - `.area-studio .new-agent-btn`
  - `.area-admin .admin-provider-add-btn`
  - `.area-admin .admin-provider-edit-btn` (split from shared rule with delete-btn — see Implementation Guidance §11)
  - `.area-admin .admin-pf-cancel`
  - `.area-studio .chip-add`
  - `.area-studio .tool-actions button`
- [ ] **Delete buttons stay NEUTRAL** (color disambiguation: cyan = create/edit, neutral = read/secondary, red = destruction): `.admin-provider-delete-btn`, `.delete-btn`, `.agent-item-delete` retain `border: 1px solid var(--border)` + `color: var(--fg-secondary)` default and `:hover { color: var(--status-danger); border-color: var(--status-danger) }`
- [ ] **Utility buttons stay NEUTRAL**: `.admin-pf-models-refresh`, `.admin-pf-pull-cancel`, `.admin-pf-pull-btn`, `.admin-pf-eye` — utility actions, not affordances. Keep current neutral styling.
- [ ] **`.admin-pf-test` deliberate exception**: already outlined cyan in admin.css. KEEPS its existing `:hover { background: var(--accent); color: var(--fg-on-accent); }` solid-fill hover behavior as a deliberate confirmation-moment affordance (more aggressive than the other outlined-cyan buttons). Document as exception with a CSS comment.
- [ ] Primary CTAs keep filled-cyan: `.save-btn`, `.admin-pf-save`, `.admin-pf-pull-go`, `.area-chat .input-area button`. Use `--accent` bg + `var(--fg-on-accent)` text + `box-shadow: 0 0 8px var(--accent-glow)` glow.

### Status dots with glow
- [ ] `.area-admin .admin-pf-model-dot.loaded` — `box-shadow: 0 0 6px rgba(46, 204, 113, 0.6)` (success green glow). Use `--status-success-glow` token or rgba directly tied to `--status-success` value.
- [ ] Other status dots in the UI receive equivalent treatment (online/loaded/etc.)

### Focus rings
- [ ] All `:focus-visible` styles updated to use cyan focus ring: `outline: 1px solid var(--accent); box-shadow: 0 0 0 3px var(--accent-glow)` or equivalent. Specifically the existing focus-visible rules in `admin.css` (around line 270 of original styles.css).

### Border radius migration
- [ ] Major panels use `var(--panel-radius)` (10px). Specific updates:
  - `.admin-provider-card`, `.admin-pf-models-list`, message bubbles, sidebar `.session-item.active`, `.agent-item.active`, `.admin-category-item.active`
- [ ] Smaller elements (chips, badges, small inputs) keep `var(--panel-radius-sm)` (6px) — DO NOT bump these

### Behavioral
- [ ] All F1 browser tests still pass (testids stable, no DOM/JS changes)
- [ ] Default `pytest tests/` shows 350 passed, 16 deselected
- [ ] Hardcoded hex/rgba grep on CSS still clean (rgba in tokens.css is allowed; other files reference via `var(...)`)
- [ ] No `console.error` in browser DevTools when loading any area
- [ ] App functional: can navigate Chat / Studio / Admin, send a message (with mock provider), create an agent, configure a provider — same flows F1 tests cover, manually verified

### Visual judgment
- [ ] App in dark mode looks distinctly tron/NEXUS-influenced compared to pre-leg
- [ ] Cyan accent reads as "cyan", not "blue" (the `#22d3ee` value)
- [ ] Body has a subtle gradient (visible but not distracting)
- [ ] Active sidebar items "glow" softly cyan when selected
- [ ] Panel borders have a hint of cyan glow on hover for cards
- [ ] Section headers display `// ` prefix in cyan-with-reduced-opacity
- [ ] No element looks broken (e.g., unstyled text, missing background, overflow)

## Verification Steps

1. **All tests pass**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=60
   ```
   Expected: 350/16 deselected; 8 browser tests pass.

2. **Hex/rgba leak check** (rgba now allowed in tokens.css for glow tokens):
   ```bash
   grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
     | grep -v tokens.css | grep -v "data:image/svg"
   ```
   Expected: empty output.

3. **Manual visual check (CRITICAL for this leg)**:
   ```bash
   docker compose up -d --build
   ```
   Open http://localhost:8484 in a browser:
   - Body should have subtle gradient (top deep navy fading to near-black at bottom)
   - Sidebar nav rail (left) should look as before structurally; nav items should glow cyan on active state
   - Chat area: input text turns cyan on focus with glow ring; send button is solid cyan with glow; assistant messages are translucent panels with thin borders
   - Studio area: agent list items get cyan-glow active state; "+" button is outlined cyan that fills on hover; section headers show `//` prefix
   - Admin → LLM Providers: provider cards have rounded corners and slight glow on hover; "Add Provider" button is outlined cyan; provider type badges still show colored backgrounds (per-type)
   - Toggle to light mode (`App.theme.set('light')` in console): should still work but look ugly (placeholder); switch back (`App.theme.set('dark')`)

4. **Cross-area consistency check**: Open all three areas in sequence and confirm:
   - Section header `// ` prefix renders consistently
   - Active item highlights look the same in chat session list, studio agent list, and admin category list
   - Buttons follow the outlined/filled distinction consistently

## Implementation Guidance

### Strategy

This leg has a lot of CSS edits. Recommended order:

1. **First**, expand `tokens.css` with all new tokens. Run a quick visual to confirm nothing breaks.
2. **Second**, change `--accent` value in dark theme to `#22d3ee`. The whole UI now reads as cyan instead of blue. Visual check.
3. **Third**, update `body` background to `var(--bg-gradient)` in `base.css`. Visual check.
4. **Fourth**, work through each area file (chat.css, studio.css, admin.css) applying:
   - Panel radius and shadow patterns
   - Active state translucent + glow
   - Section header `::before` pseudo-element
   - Button outlined/filled distinction
   - Status dot glows
   - Focus ring updates
5. **Fifth**, run all tests and the manual visual check.

### 1. Token additions to `tokens.css`

Add these to the dark block (under appropriate semantic groups):

```css
[data-theme="dark"] {
  /* ... existing tokens ... */

  /* accent + glow */
  --accent: #22d3ee;             /* was #4a9eff */
  /* (--fg-on-accent stays #000 from leg 02 — single token for text-on-accent and text-on-badge) */
  --accent-glow: rgba(34, 211, 238, 0.25);
  --accent-glow-strong: rgba(34, 211, 238, 0.4);
  --accent-translucent: rgba(34, 211, 238, 0.08);
  --accent-translucent-hover: rgba(34, 211, 238, 0.12);

  /* panel design tokens */
  --panel-radius: 10px;
  --panel-radius-sm: 6px;
  --surface-translucent: rgba(255, 255, 255, 0.02);
  --panel-shadow: 0 1px 0 rgba(255, 255, 255, 0.03), inset 0 1px 0 rgba(255, 255, 255, 0.02);
  --panel-shadow-glow: 0 0 12px var(--accent-glow);

  /* body backdrop */
  --bg-gradient: linear-gradient(180deg, #0e1428 0%, #050505 70%);

  /* status glows */
  --status-success-glow: rgba(46, 204, 113, 0.6);
  --status-warning-glow: rgba(245, 166, 35, 0.5);
  --status-danger-glow: rgba(255, 74, 74, 0.5);
}
```

For light theme, add placeholder values (deeper cyan, light-bg gradient):

```css
[data-theme="light"] {
  /* ... existing tokens ... */

  --accent: #0891b2;             /* deeper cyan for light bg contrast */
  /* (--fg-on-accent stays #fff from leg 02) */
  --accent-glow: rgba(8, 145, 178, 0.25);
  --accent-glow-strong: rgba(8, 145, 178, 0.4);
  --accent-translucent: rgba(8, 145, 178, 0.08);
  --accent-translucent-hover: rgba(8, 145, 178, 0.12);

  --panel-radius: 10px;
  --panel-radius-sm: 6px;
  --surface-translucent: rgba(0, 0, 0, 0.02);
  --panel-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  --panel-shadow-glow: 0 0 8px var(--accent-glow);

  --bg-gradient: linear-gradient(180deg, #ffffff 0%, #f3f4f6 100%);

  --status-success-glow: rgba(22, 163, 74, 0.4);
  --status-warning-glow: rgba(217, 119, 6, 0.4);
  --status-danger-glow: rgba(220, 38, 38, 0.4);
}
```

Also: where the existing `--badge-openai` token in dark currently equals the OLD accent (`#4a9eff`), KEEP IT at `#4a9eff` (not change to the new `#22d3ee`). Brand colors are stable; we already discussed this in leg 02. Just ensure the badge value isn't accidentally modified.

### 2. Body gradient

In `base.css`, find the `body` rule and update:

```css
@layer base {
  body {
    /* ... existing properties ... */
    background: var(--bg-gradient);
    /* (was: background: var(--bg);) */
  }
}
```

### 3. Section header `// ` prefix

Section-title classes already exist with uppercase + letter-spacing. Add `::before` pseudo-element wherever applicable. Example for studio.css:

```css
@layer areas {
  .area-studio .section-title::before {
    content: "//";
    padding-right: 0.4em;
    color: var(--accent);
    opacity: 0.6;
    font-weight: 600;
  }
}
```

Apply analogous rules in `admin.css` for `.admin-section-title`, `.admin-pf-models-title`, `.admin-pf-section-label`. Optional for `.area-studio .tool-group` (small-caps category labels) — pick consistently and apply or skip.

### 4. Active sidebar items (cyan translucent + glow)

Update existing `.session-item.active`, `.agent-item.active`, `.admin-category-item.active`:

```css
.area-chat .session-item.active {
  background: var(--accent-translucent);
  color: var(--fg);
  border: 1px solid var(--accent);
  box-shadow: var(--panel-shadow-glow);
  /* (was: background: var(--surface); border: 1px solid var(--border)) */
}
```

Same pattern for the other two active states. Inactive states keep the subtle hover (`background: var(--surface)`).

### 5. Outlined-cyan buttons

Migrate "secondary" buttons from `border: 1px solid var(--border); color: var(--fg-secondary)` to outlined cyan:

```css
.area-chat .new-chat {
  background: transparent;
  border: 1px solid var(--accent);
  border-radius: var(--panel-radius-sm);
  padding: 4px 10px;
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.2s, color 0.2s;
}
.area-chat .new-chat:hover {
  background: var(--accent-translucent-hover);
}
```

Apply the same pattern to other outlined buttons (see acceptance criteria list). Primary CTAs (Save, Create, Send) keep filled style.

### 6. Filled-cyan primary buttons (with glow)

```css
.area-studio .save-btn {
  background: var(--accent);
  border: none;
  border-radius: var(--panel-radius-sm);
  padding: 8px 24px;
  color: var(--fg-on-accent);
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 0 8px var(--accent-glow);
  /* (existing other props kept) */
}
```

### 7. Status dot glows

```css
.area-admin .admin-pf-model-dot.loaded {
  background: var(--status-success);
  box-shadow: 0 0 6px var(--status-success-glow);
}
```

### 8. Focus ring

The current focus-visible rules are spread across multiple files. Grep `:focus-visible` across `the_one/interfaces/web/static/css/*.css` to find all existing rules; update each to the cyan-glow pattern below. Primary site is admin.css (lines ~63-73 of admin.css after split, was lines 270-281 of original styles.css).

Replace existing `:focus-visible` rules to use cyan ring:

```css
.area-admin .admin-pf-input:focus-visible,
.area-admin .admin-pf-select:focus-visible {
  border-color: var(--accent);
  outline: 1px solid var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.area-admin .admin-system-btn:focus-visible,
.area-admin .admin-provider-add-btn:focus-visible,
.area-admin .admin-provider-edit-btn:focus-visible,
.area-admin .admin-provider-delete-btn:focus-visible,
... etc {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px var(--accent-glow);
}
```

### 9. Chat message bubbles

Update `.area-chat .msg.user` and `.area-chat .msg.assistant`:

```css
.area-chat .msg.user {
  align-self: flex-end;
  background: var(--accent);
  color: var(--fg-on-accent);
  border-radius: var(--panel-radius);
  box-shadow: 0 0 8px var(--accent-glow);
}
.area-chat .msg.assistant {
  align-self: flex-start;
  background: var(--surface-translucent);
  border: 1px solid var(--border);
  border-radius: var(--panel-radius);
}
```

### 10. Provider cards

```css
.area-admin .admin-provider-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--surface-translucent);
  border: 1px solid var(--border);
  border-radius: var(--panel-radius);
  margin-bottom: 8px;
  box-shadow: var(--panel-shadow);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.area-admin .admin-provider-card:hover {
  border-color: var(--accent);
  box-shadow: var(--panel-shadow-glow);
}
```

### 11. Split `.admin-provider-edit-btn,.admin-provider-delete-btn` shared rule

`admin.css` (post-leg-02) has `.admin-provider-edit-btn, .admin-provider-delete-btn { ... }` as a shared rule (was line 264-265 of original styles.css). Split into TWO separate rules:

```css
@layer areas {
  /* Edit — outlined cyan, creation/affordance accent */
  .area-admin .admin-provider-edit-btn {
    background: transparent;
    border: 1px solid var(--accent);
    border-radius: var(--panel-radius-sm);
    padding: 3px 10px;
    color: var(--accent);
    font-size: 11px;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.2s;
  }
  .area-admin .admin-provider-edit-btn:hover {
    background: var(--accent-translucent-hover);
  }

  /* Delete — neutral default, danger hover (UNCHANGED behavior, just split rule) */
  .area-admin .admin-provider-delete-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: var(--panel-radius-sm);
    padding: 3px 10px;
    color: var(--fg-secondary);
    font-size: 11px;
    cursor: pointer;
    font-family: inherit;
  }
  .area-admin .admin-provider-delete-btn:hover {
    color: var(--status-danger);
    border-color: var(--status-danger);
  }
}
```

The existing `.admin-provider-delete-btn:hover` and `.admin-provider-delete-btn.admin-provider-delete-confirm` rules in admin.css continue to work unchanged.

### 12. Verification

```bash
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
  | grep -v tokens.css | grep -v "data:image/svg"
docker compose up -d --build
# Open http://localhost:8484 — manual visual check
```

## Edge Cases

- **rgba() now appears in tokens.css**: The glow tokens use rgba literals. This is allowed (the grep filter `grep -v tokens.css` permits it). Don't accidentally use rgba() outside tokens.css.

- **`--badge-openai` brand color stays `#4a9eff`** even though `--accent` changes. These are independent tokens; do not consolidate.

- **Light theme placeholder updates**: The new tokens (--accent-glow, --bg-gradient, etc.) need light variants. They'll be ugly until leg 06 redesigns. Acceptable.

- **`color-mix()` alternative**: Modern CSS can compute `color-mix(in srgb, var(--accent) 25%, transparent)` instead of hardcoding rgba. This is cleaner but more verbose at every use site. For F2, use the explicit rgba tokens; F3+ may revisit.

- **Visual regression in F1 browser tests**: F1 tests assert on text content and element presence, NOT pixel colors. They should pass regardless of visual changes. If a test fails, investigate immediately — it likely means a class or testid was accidentally removed.

- **Performance**: box-shadow with blur is GPU-accelerated; multiple panels with glow effects are fine. If you observe jank, remove the shadow on hover-only states first; full static glows are typically fine.

- **Accessibility**: focus-visible rings now use a 3px cyan glow + 1px solid border. This is more visible than the pre-leg `outline: 2px solid var(--accent); outline-offset: 2px;` pattern. WCAG 2.4.7 Focus Visible passes; WCAG 1.4.11 Non-text Contrast (3:1 against adjacent colors) passes for cyan-on-dark.

- **Color contrast**: dark `--accent: #22d3ee` on dark `--bg: #0a0a0a` is approximately 11.6:1 (passes WCAG AAA for any text size). Cyan-text-on-dark-surface is fine for buttons and links.

- **Subjective polish vs landing**: this leg lands the design language. The HAT leg (09) is where the user gives final feedback ("more glow", "less glow", "different cyan", "smaller radius", etc.). Don't over-iterate during leg 03 — get the moves in, ship to HAT.

- **DOM and behavior unchanged**: this is a pure CSS leg. No JS files modified. No HTML structural changes. Only CSS rule additions/edits. If you find yourself wanting to change DOM, scope-check.

## State-Machine Reachability Audit

This leg introduces no new states. CSS rule changes only. Tokens added are additive (no token removals). All existing CSS classes and DOM structure preserved.

✓ Pass.

## Cache Freshness Contract

No new caches. The existing browser CSS cache will hold the new files; users may need a hard reload to see changes after deploy. Mitigation: docker-compose rebuild bumps the image, hash-based invalidation handles it.

✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — extended with ~12 new tokens × 2 themes; `--accent` value changed
- `the_one/interfaces/web/static/css/base.css` — `body` background changed to gradient
- `the_one/interfaces/web/static/css/chat.css` — multiple rule updates (active states, message bubbles, buttons, focus)
- `the_one/interfaces/web/static/css/studio.css` — multiple rule updates (active states, buttons, section headers, focus)
- `the_one/interfaces/web/static/css/admin.css` — multiple rule updates (provider cards, buttons, section headers, focus, status dots)
- `the_one/interfaces/web/static/css/components.css` — `.app-flash` glow update

(No JS, HTML, or Python files touched.)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 350/16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [ ] Grep check (CSS hex/rgba excluding tokens.css and SVG) returns zero matches
- [ ] Manual visual check: dark mode looks distinctly tron/NEXUS-influenced; cyan reads as cyan; gradient visible; active states glow; section headers show `//` prefix
- [ ] Update flight-log.md with leg progress entry (status, what was done, anomalies, observation about visual transformation, any subjective notes for HAT leg)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (happens at flight-level commit time)
- [ ] Do NOT commit
- [ ] Signal `[HANDOFF:review-needed]`
