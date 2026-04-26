# Flight: Design Language & Theme Architecture

**Status**: completed
**Mission**: [UI Maturity](../../mission.md)

## Contributing to Criteria

- [x] The interface presents a coherent visual identity — typography, spacing, color, and interaction patterns are consistent across all areas
- [x] The color system meets accessibility contrast standards (WCAG AA) for text, interactive elements, and focus indicators
- [x] Visual themes are swappable without code changes, allowing palette and density adjustments through configuration
- [x] Each functional area (Chat, Studio, Administration) reflects the established design language and meets a quality bar suitable for showing to external developers without apology *(this flight establishes the design language; per-area polish lands in F4-F6)*

---

## Pre-Flight

### Objective

Stand up the theme architecture (CSS custom properties for palette / typography / spacing / motion / density), implement Geist Sans + Geist Mono typography, replace emoji icons (`💬`/`🤖`/`⚙️`) with a coherent SVG icon set, and apply a "clean tron / NEXUS-style" visual language as the dark default theme. Light theme ships as a pragmatic accessibility flip (same accent palette, inverted surfaces). All existing F1 browser tests continue to pass; visual snapshot baselines establish the regression net for F3-F6.

### Open Questions

_(all resolved during planning — see Design Decisions)_

### Design Decisions

**Design language anchor — clean tron / NEXUS-style at refined density**: The user committed to the visual direction during planning, with three reference screenshots: the "NEXUS AI Operating System" dashboard (chat + dashboard variants) and a Wikipedia visualization tool. NEXUS density is the target; the Wikipedia tool is too dense for a chat-first app.
- Rationale: Reference convergence happened in conversation rather than in a coding leg, saving F2's leg 1 from a multi-direction experiment phase. The direction is locked.
- Trade-off: We commit before any code exists. If the realization in leg 3 reveals the language doesn't fit the-one's UX, divert per Adaptation Criteria below.

**Token system — CSS custom properties, CSS cascade layers, no preprocessor, no framework**: Theme tokens live as `[data-theme="dark"]` and `[data-theme="light"]` declarations in `tokens.css`. Component CSS references tokens; no hardcoded colors anywhere outside the token blocks. **Cascade ordering pinned via `@layer`**: `<style>@layer tokens, base, components, areas, utilities;</style>` declared in `index.html` head before any `<link>`. Each component file opens with `@layer components { ... }` (or appropriate layer).

Layer order rationale (rules later in the cascade win):
- `tokens` — variable definitions only; never wins on cascade
- `base` — reset, body, typography baselines
- `components` — buttons, inputs, panels, gauges, sidebars, area-shell components
- `areas` — `.area-{id}` scoped overrides; ranks above `components` so `.area-admin .admin-provider-badge` wins over a default `.admin-provider-badge` rule
- `utilities` — utility classes win over both, conventional

- Rationale: Matches mission constraint (no CSS framework), composes with existing `.area-{id}` scoping, zero build-step. Cascade layers prevent specificity surprises if `<link>` order shifts during refactor — and survive a future "concatenate at startup" optimization unchanged.
- Trade-off: No design-time validation that all tokens exist (a hardcoded color slipping into a component file won't break compile). Mitigated by a CI grep check (every `var(--x)` referenced in `static/css/**/*.css` must be defined in `tokens.css`) and visual snapshot regression. The grep check expands to `static/**/*.{css,js,html}` to catch JS-side color literal leaks (see Edge Cases for the `TYPE_BADGE_COLORS` case).

**Theme switching mechanism — tri-state toggle (Light / Dark / Auto)**: Theme is applied via `data-theme` attribute on `<html>` (always one of `"dark"` | `"light"`). One localStorage key: `theme-preference` = `"dark"` | `"light"` | `"auto"` (or absent, treated as `"auto"`).

Behavior:
- **`theme-preference === "auto"` (or absent)**: apply `prefers-color-scheme` (or `dark` if unset/no-preference). `matchMedia('(prefers-color-scheme: dark)').addEventListener('change', ...)` flips the UI live if the user changes OS preference.
- **`theme-preference === "dark"` or `"light"`**: apply that value; ignore OS preference.
- **Tri-state toggle UI**: a single control (segmented/cycle button) with three options — Light, Dark, Auto. Choosing Auto deletes or sets `theme-preference = "auto"` and re-enters system-tracking mode. Choosing Light or Dark writes that value.
- **CSS structure**: only `[data-theme="dark"]` and `[data-theme="light"]` blocks define tokens — no `:root` shortcut, to avoid cascade ambiguity when the attribute flips live.

- Rationale: Tri-state is the established modern pattern (GitHub, Discord, macOS app prefs panes). Single control, clear semantics, no permanent opt-out from OS preference. Matches user expectation that "I want to follow system" is reachable from the same control as "I want to override."
- Trade-off: Three states is slightly more UI than a binary toggle. Acceptable — the cycle/segmented pattern fits in the same footprint.

**Light theme is a designed coherent variant**: Same cyan accent palette (slightly desaturated/deepened for contrast on light surfaces), same typography, same geometric language, same icon system. Surfaces use off-white / light gray (NOT pure white — too harsh); text in deep navy/near-black; borders darker and more visible than the dark-theme variants; cyan-glow effects replaced by subtle shadows or thin borders (glow doesn't read on light backgrounds). Section headers, status dots, and structural details stay.
- Rationale: A pragmatic flip produces a noticeably lower-quality variant. Per user request, light gets its own designed pass — light backgrounds with dark border/font variants — closer to Linear/Stripe light-mode quality. Both themes are first-class.
- Trade-off: ~1 additional leg of work (leg 07 added for light realization). The cyan-glow → shadow translation requires intentional design judgment per surface, not a token swap.

**Typography — Geist Sans + Geist Mono, self-hosted**: Geist Sans for UI (display, headlines, body); Geist Mono for code, IDs, timestamps, and `// SECTION_NAME` cyberpunk-style headers. Self-host the WOFF2 files (small payload, no external CDN dependency).
- Rationale: Geist's slightly-technical geometric character matches the design direction. Self-hosting avoids a cross-origin font load on the critical path.
- Trade-off: ~80-150KB of WOFF2 bundled into static. Acceptable for a dev tool; the-one isn't bandwidth-constrained.

**Icon system — Lucide, inline SVG, curated subset**: Replace emoji area icons with Lucide icons (open source, MIT, ~1500 icons, geometric line style, designed by Vercel/community). Inline SVG (not icon font) for color theming via `currentColor`. Curate a subset of ~20-30 icons committed to repo as individual SVG files.
- Rationale: Lucide pairs aesthetically with Geist (both Vercel ecosystem, both geometric). Inline SVG inherits text color via `currentColor`, matching token-based theming. No icon library dependency at runtime.
- Trade-off: Manual curation when adding new icons. Acceptable for the project's icon volume.

**Token boundary — theme vs layout via the responsive-breakpoint test**: A token is a **theme token** if its value can change without restructuring the DOM or breaking responsive breakpoints. A token is a **layout token** if changing it would require updating media queries or grid templates.

Under this rule:
- `--sidebar-w` (240px), `--nav-w` (48px): **theme tokens** (a "compact" density theme could shrink them; no media query depends on the exact value)
- A future `--breakpoint-md`: layout token
- A future `--grid-template-areas`: layout token
- Border radii, padding, typography scale, motion durations, color palette: theme tokens

Token groups in `tokens.css`: `palette`, `typography`, `space`, `motion`, `density-and-geometry` (last group includes widths/heights/radii — anything that's a length-with-no-breakpoint-dependency).

- Rationale: A "compact" density variant should be allowed to shrink the sidebar from 240px to 200px — that's the point of density. The earlier "width is layout, padding is theme" heuristic produced the wrong answer for `--sidebar-w`.
- Trade-off: Per-area sidebar width overrides (e.g., a wider sidebar in Studio only) scope under `.area-{id}` — `--sidebar-w` becomes the default, areas can override locally.

**Test strategy — flow tests must continue passing; visual snapshots establish baseline at flight close**: Existing F1 browser tests use `data-testid` selectors that survive CSS rewrites. Visual snapshots are added in the final leg, AFTER the design language is committed (no thrashing baselines).
- Rationale: F1 deferred snapshots specifically to avoid baselining the pre-redesign UI. F2 lands the redesign, then baselines.
- Trade-off: There's a window between F2 leg 1 and F2 final leg where visual regression is uncovered. Acceptable — flow tests cover functional regression, and the window is one flight.

**Snapshot strategy — per-area-per-state, not per-flow**: Snapshots capture the rendered UI state of each area in each significant state (empty, with-data, with-error, with-active-selection). Flow tests cover behavior; snapshots cover visual.
- Rationale: Per-flow snapshots create one-baseline-per-flow which is brittle to test ordering. Per-state snapshots are stable and naturally extensible to new states.
- Trade-off: Some duplication between flow and snapshot tests' setup. Mitigated by reusing the layered fixture stack from F1.

### Prerequisites

- [ ] F1 (Browser Test Foundation) committed and merged to `main` — verified, commit `9c11af7` on main as of 2026-04-26
- [x] All 8 F1 browser tests passing on `main` — verify with `pytest -m browser tests/browser/ -v --timeout=60` (expect 8 passed)
- [x] Default `pytest tests/` baseline: 350 passed, 16 deselected
- [x] Geist Sans + Geist Mono Variable Fonts (WOFF2) obtainable from `vercel/geist-font` repo (SIL Open Font License 1.1; ~70-80KB per VF, ~150KB total)
- [x] Lucide icon SVGs obtainable (`lucide.dev` direct download; we use raw SVGs, NOT the JS runtime)
- [x] `THE_ONE_DEV_MODE=true` continues to work for any tests that need mock providers (no F2 changes to the dev-mode flag)
- [ ] Constraints carried forward (must be respected through F2):
  - Existing `.area-{id}` CSS scoping convention from M02 (`styles.css:62-70`, `app.js:48,52`) is load-bearing — component files preserve this prefix
  - `role="alert"` / `role="status"` / `aria-live="polite"` attributes on `.app-flash` and similar surfaces (`app.js:113-117`) must survive any flash-styling rework
  - F1's 14 `data-testid` attributes must remain on the same elements (CSS class rewrites OK; attribute removal is not OK)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified *(re-run `pytest -m browser tests/browser/ -v --timeout=60` at flight start; expect 8 passed)*
- [x] Validation approach defined
- [x] Legs defined (tentative; planned one-at-a-time during execution)

---

## In-Flight

### Technical Approach

The flight introduces theme architecture and applies the visual language in a sequence designed to keep the regression net intact at every leg-end. Key principle: **separate "set up tokens" from "use tokens" from "change visuals"** so each leg has a clean, verifiable boundary.

Leg dependency graph:

```
01 theme-scaffold ──► 02 apply-tokens ──► 03 visual-realization ──► 06 light-realization ──► 07 a11y-audit
                            │                       │                                              │
                            ▼                       ▼                                              ▼
                  04 typography ──► 05 icon-system ───────────────────────────► 08 snapshots + docs ─► 09 HAT (optional)
```

File layout introduced in this flight:

```
the_one/interfaces/web/static/
├── css/
│   ├── tokens.css          # [data-theme="dark"] / [data-theme="light"] custom properties
│   ├── base.css            # Reset, typography baselines, body
│   └── components/
│       ├── primitives.css  # Buttons, inputs, panels, gauges (shared across areas)
│       ├── nav.css         # App nav rail
│       ├── sidebar.css     # Per-area sidebars
│       ├── chat.css        # Chat area scoped (.area-chat — opens with @layer areas)
│       ├── studio.css      # Studio area scoped (@layer areas)
│       └── admin.css       # Admin area scoped (@layer areas)
├── fonts/
│   ├── GeistVF.woff2
│   └── GeistMonoVF.woff2
├── icons/
│   ├── chat.svg
│   ├── studio.svg
│   ├── admin.svg
│   └── ... (~20 curated)
├── js/
│   ├── theme.js            # NEW: theme switcher + localStorage persistence
│   └── ... (existing area files)
├── index.html              # Updated to load tokens, fonts, theme.js
└── styles.css              # SHRINKS dramatically — most content moves to css/components/
```

`styles.css` becomes a thin import-style file (CSS doesn't natively import; we either inline `<link>` tags in HTML or concatenate at build time). Going with multiple `<link>` tags in `index.html` — no build step, vanilla-friendly.

### Checkpoints

- [x] Theme tokens scaffold defined and dark theme covers every existing color used in styles.css (no missing tokens)
- [x] `apply-tokens` leg results in zero hardcoded colors anywhere outside `tokens.css` — including JS files (`TYPE_BADGE_COLORS` in `admin.js:47-53` becomes `TYPE_BADGE_CLASSES` returning class-name suffixes; per-type badges styled in CSS via tokens). Grep check covers `static/**/*.{css,js,html}` for hex / rgba literals
- [x] **F1 browser tests pass at every leg-end** (per-leg checkpoint, not flight-end-only — explicit gate per F1 debrief recommendation)
- [x] Geist Sans + Geist Mono load without FOUC (font-display: swap; SIL OFL preserved with `static/fonts/LICENSE.txt`)
- [x] Icons render in both themes via `currentColor`
- [x] Light theme passes WCAG AA on text + interactive elements (manual contrast check + automated tool if available)
- [x] Visual snapshots committed for dark + light variants of three areas × primary states (target ~12 baselines: chat-empty, chat-with-messages, studio-empty, studio-with-agent, admin-empty, admin-with-provider — each in dark + light)
- [x] Theme toggle works: switching theme updates the UI without reload; preference persists across reloads; OS-preference change flips the UI live until user explicitly toggles
- [x] CI grep check enforces "every `var(--x)` referenced in `static/css/**/*.css` is defined in `tokens.css`"

### Adaptation Criteria

**Divert if**:
- Geist licensing changes between flight start and font integration (currently OFL/SIL — verified)
- Lucide icon coverage proves insufficient for a critical UI affordance — fall back to hand-drawing the missing icons in the same geometric line style
- Visual realization in leg 3 produces a UI where the user cannot navigate to a specific common task (start a chat, configure a provider, create an agent) within ~5 seconds without scanning every element — re-converge with the user before continuing. (Concrete user-facing test, not aesthetic judgment.)
- Light theme cannot pass WCAG AA without diverging significantly from the cyan accent — ship dark-only as v1, defer light to a follow-up flight

**Acceptable variations**:
- Specific token names (`--color-accent-primary` vs `--accent-primary`)
- Number of font weights loaded (start with Regular + Medium + Bold; add others if needed)
- Icon library substitute (Heroicons or Feather are acceptable replacements if Lucide proves insufficient)
- Snapshot tolerance settings (Playwright supports per-pixel and percentage-based diffs)

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-theme-scaffold` — Set up `css/tokens.css` with palette, typography, spacing, motion, density tokens for both dark and light themes. Add `js/theme.js` for localStorage + `prefers-color-scheme` initialization and `[data-theme]` attribute toggle. Update `index.html` to load tokens.css and theme.js. NO visual change yet — existing styles.css still drives rendering.
- [x] `02-apply-tokens` — Replace every hardcoded color/typography value in styles.css AND in JS files with token references. Specifically: `admin.js:47-53` `TYPE_BADGE_COLORS` (hex literals) becomes `TYPE_BADGE_CLASSES` returning per-type CSS class-name suffixes (`'ollama'`, `'openai'`, etc.); the inline `style="background:..."` injection at `admin.js:339` is removed; per-type badge styling moves into `css/components/admin.css` backed by tokens (`.admin-provider-badge--ollama { background: var(--badge-ollama); }` etc.). The `'#888'` fallback at `admin.js:336` becomes a `.admin-provider-badge--unknown` class with a token-backed background. Split styles.css into `css/components/*.css` files preserving `.area-{id}` scoping. NO visual change — pure refactor. F1 browser tests must pass identically. Grep check confirms zero hex/rgba literals outside `tokens.css`.
- [x] `03-visual-realization` — Apply the NEXUS-style design language: cyan-glow borders, translucent panels, ringed gauges where appropriate, `// SECTION_NAME` headers, outlined cyan buttons with hover-fill, status dots with glow, dark gradient background. This is where the UI VISIBLY changes. Browser tests must pass (testids stable); visual snapshots TBD until leg 7. Optional: save a small set of `before-design.png` screenshots to the flight directory (not Playwright snapshots — just inline reference for the debrief comparison).
- [x] `04-typography` — Self-host Geist Sans + Geist Mono WOFF2 files. Define typography scale tokens (display, headline-1/2/3, body-large/regular/small, caption, mono). Apply across components. Verify font-display: swap behavior, no FOUC.
- [x] `05-icon-system` — Replace 3 emoji area icons with Lucide SVG icons (`message-circle` for Chat, `bot` or `sparkles` for Studio, `settings` for Admin). Curate ~20 additional icons for likely future use (close, edit, delete, plus, check, alert, info, etc.) and bundle as a single JS module `static/js/icons.js` exporting `{ chat: '<svg>...</svg>', studio: '<svg>...</svg>', ... }` (one HTTP request, fast parse). Add `App.icon('name')` helper. Icons inherit color via `currentColor`. Avoid per-icon `fetch('/static/icons/X.svg')` — that's 20 RTTs at startup.
- [x] `06-light-realization` — Bring light theme to design parity with dark. Token deltas: surfaces shift to off-white / light gray (NOT pure white — too harsh), text to deep navy / near-black, cyan accent slightly desaturated/deepened for contrast on light surfaces, borders darker and more visible than the dark-theme variants, cyan-glow effects replaced with subtle shadows or thin borders (glow doesn't read on light bg), section-header `// SECTION_NAME` styling adapted, status dots stay vibrant, gauges and ringed indicators retain their geometric language. Reference points: Linear light, Stripe docs light. The leg is per-surface design judgment, not a token-flip — each component reviewed in light context and adjusted.
- [x] `07-a11y-audit` — Audit BOTH themes against WCAG AA: 4.5:1 contrast for body text, 3:1 for large text and interactive elements, visible focus indicators, sufficient touch/click targets. Verify `role="alert"`/`role="status"`/`aria-live` survive any flash-styling rework. Adjust tokens where needed; both themes must pass. Document a11y compliance in design system docs. **`a11ymcp` MCP server is OUT OF SCOPE for this leg** — manual audit only; the MCP install would be a Claude Code config change, deferred to a separate setup task if desired post-flight.
- [x] `08-snapshots-and-docs` — Add Playwright `expect(page).to_have_screenshot()` baselines for dark and light variants of each area in their primary states (target ~12 baselines: chat-empty, chat-with-messages, studio-empty, studio-with-agent, admin-empty, admin-with-provider — each in dark + light). Generate `tests/browser/design_tokens.py` exporting token names as constants for future test imports. Add CI grep check: every `var(--x)` in CSS files must be defined in `tokens.css`. Document the design system in `the_one/agents.md`: token reference, typography scale, icon list, theme switching contract. Update CLAUDE.md with Geist + theme switcher mention.
- [x] `09-hat-and-alignment` *(opted in at flight kickoff; landed)* — Guided HAT session with the user: walk through dark and light themes in all three areas, verify the design lands as intended, fix anything that feels off (color tweaks, spacing adjustments, icon substitutions). User explicitly approves before flight closes.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged *(post-commit)*
- [x] All existing tests still passing (`pytest tests/` → 387 passed)
- [x] All F1 browser tests still passing (`pytest -m browser tests/browser/` → 20 passed, includes the 12 new visual-snapshot tests)
- [x] Visual snapshot tests added and passing (`pytest -m browser` includes new snapshot tests)
- [x] Documentation updated:
  - [x] `CLAUDE.md` — Geist typography mention, theme switcher contract, design system pointer
  - [x] `the_one/agents.md` — Design system section: token reference, typography scale, icon list, theme switching
  - [x] HAT follow-ups captured: theme-generator-under-Settings (punted to a future flight); structural keyboard-operability debt (pre-existing nav-rail/list-item/inline-delete patterns) documented as a known issue to address in a dedicated future flight

### Verification

- Run `pytest tests/` — passes with no new failures (browser tests excluded by default marker filter)
- Run `pytest -m browser tests/browser/` — all flow tests pass + new snapshot tests pass
- Open the app in a browser — dark theme renders by default, light theme accessible via toggle, switching themes is instantaneous (no reload), preference persists across reloads
- Manual contrast spot-check on body text and interactive elements in both themes
- Verify no FOUC on font load (network throttle to slow 3G in DevTools and reload)
- Confirm Lucide icons render correctly in both themes via `currentColor`
