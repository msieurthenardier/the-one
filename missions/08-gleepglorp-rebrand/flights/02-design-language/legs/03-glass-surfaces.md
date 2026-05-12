# Leg: 03-glass-surfaces

**Status**: landed
**Flight**: [Design Language — Glass + Control Panel](../flight.md)

## Objective

Establish the **glass surface treatment** axis of the GleepGlorp AI design language — reflective glass that reads as "futuristic cartoon, but crisp" — and apply it across the in-scope chrome surfaces (entity tiles, section-nav, sidebar, app-picker popover, modal dialog, topbar) plus the supporting compositions in both light and dark themes. Iteration is operator-driven, executed in the live gallery at `#admin/design-language`; this artifact records the final state, not the iteration path (which lives in the flight log).

## Type

**Interactive vibe leg.** Flight Director presents 2-4 concrete CSS variants per micro-iteration; operator picks or steers; final token values commit at leg close. No autonomous Developer-agent implementation.

## Context

- Leg 3 of 6. Legs 01-02 are landed (uncommitted on branch); the gallery at `#admin/design-language` shows every in-scope primitive as a live sample.
- Flight Design Decision: chrome + interactive primitives are in scope. Glass tokens land in `tokens.css` for both themes; chrome surfaces compose them.
- Flight Design Decision: **glass + existing `--panel-shadow-glow` composition rule** — glass surfaces REPLACE `--panel-shadow-glow` with `--glass-edge-highlight + --bezel-shadow` (the bezel side lands in Leg 04). For Leg 03's scope, glass surfaces drop `--panel-shadow-glow` and replace with the glass highlight; the bezel-shadow slot remains a placeholder until Leg 04 fills it. The 4 `--panel-shadow-glow` consumers identified at flight design (`components.css:144, :421, :607` + `chat.css:155`) get the substitution.
- Flight Design Decision: light theme uses **frosted-white glass** — low-alpha white surface + backdrop-saturate + top-edge highlight. Same token names as dark, theme-tuned values.
- Flight Design Decision: **`prefers-reduced-transparency` fallback** — when the user agent suppresses transparency, glass surfaces degrade to solid-tinted surfaces (use the same `--surface` / `--surface-elevated` token as the underlay, without backdrop-filter). The CSS for this lives in `tokens.css` (token-level @media query swap) OR `components.css` (per-rule @media query). Resolved at implementation time.
- WCAG concern: glass tints shift effective text-on-surface contrast. Re-run `pytest tests/test_design_tokens_a11y.py` at leg close; if any text-on-glass slot fails AA, retune the glass-bg alpha.

## Surfaces in Scope (Leg 03 — glass treatment)

Touched in this leg:
- `.entity-tile` + `.entity-tile.active` / `[aria-selected="true"]` (the primary starting surface)
- `.section-nav-item[aria-current="page"]` (sidebar section nav active state)
- `.app-picker-popover` (dropdown popover from topbar)
- `.modal-dialog` (used by `App.confirmDialog`)
- `.list-item.active` (chat session active state, also lifted as a list primitive)
- `.app-topbar-title` background + topbar chrome strip
- `.app-picker-button[aria-expanded="true"]` (open-state pill)

Out of scope this leg (covered in Leg 04 — chrome / bezels):
- Raised-edge / bezel treatment
- Corner machining
- Directional light convention

Deferred to operator HAT in Leg 06 (not glassed in this leg):
- `#app-topbar` chrome strip — leg-time decision: topbar is the chrome boundary at the very top of the viewport; there is no content behind it for `backdrop-filter` to refract. Dark theme topbar matches body bg already; light theme is intentionally dark navy as control-panel chrome. If HAT surfaces a need, can apply gleam-only treatment without `backdrop-filter`.
- `.app-picker-button[aria-expanded="true"]` open-state pill — leg-time decision: open-state currently uses `--accent-translucent-hover` + `--accent-glow` shadow (NOT a `--panel-shadow-glow` consumer, so composition rule didn't trigger). Operator did not flag during glass propagation. Leave as-is; HAT will surface if it reads inconsistent with the new popover it opens.

## Tokens to Land

Final values picked during the vibe iteration; the **names** are committed by this leg:

- `--glass-bg` — translucent surface tint (theme-tuned)
- `--glass-blur` — backdrop-filter blur radius
- `--glass-saturate` — backdrop-filter saturate amount (the "punchy refraction" / cartoon dial)
- `--glass-highlight` — top-edge highlight color/intensity (composed via `box-shadow inset 0 1px 0 ...` or 1px linear-gradient overlay)
- `--glass-border` — 1px border tint
- `--glass-edge-highlight` — alias / composition slot for the inset highlight shadow (used by the glass+shadow composition rule)

Mirrored into `tests/browser/design_tokens.py` ONLY if any of them participate in a text-on-color contrast pair (most do not — glass is a chrome treatment, not a text-on-color slot).

## Acceptance Criteria

This leg is operator-driven; acceptance is by **operator confirmation**, not autonomous test:

- [x] Glass tokens (6: `--glass-bg/blur/saturate/border/highlight/gleam`) land in `tokens.css` for both `[data-theme="dark"]` and `[data-theme="light"]` blocks
- [x] In-scope chrome surfaces compose the glass tokens — entity-tile + popover + modal use FULL glass (incl. `backdrop-filter`); list-item-active + section-nav-active + chat-welcome-hover use MINI-glass (gleam image + accent-translucent base + inset top-edge highlight, no `backdrop-filter` — small pills don't benefit from blur)
- [x] Both themes carry the design language — dark = violet-accent glass with gleam reflection; light = silver-chrome with violet undertone (deviated from "frosted white" per operator direction — silver reads better in context)
- [x] Glass + existing shadow composition rule honored — `--panel-shadow-glow` is REPLACED on glass surfaces, not composited (4 consumers updated: entity-tile-active, section-nav-active, list-item-active, chat-welcome-hover)
- [x] `prefers-reduced-transparency: reduce` fallback lands at the token layer (per-theme `@media` override in `tokens.css`) — every glass consumer degrades to solid `--surface` / `--surface-elevated` without needing per-rule overrides
- [x] Gallery at `#admin/design-language` SURFACES section shows the final glass treatment via the canonical `.entity-tile` rule — passive consumption confirmed
- [x] Operator confirms aesthetic in both themes
- [x] WCAG audit re-runs green: `docker exec the-one pytest tests/test_design_tokens_a11y.py -x -q --timeout 10` — 33 passed
- [x] Narrow test gate still green: 56 passed in 0.88s (Flight 1 baseline preserved)
- [x] Flight log updated with iteration trail and final token values
- [x] All temporary variant-comparison scaffolding REMOVED — `grep -rn 'glass-variant\|design-language-glass-variants\|ITERATION ' the_one/interfaces/web/static/` returns zero hits

## Iteration Strategy

Per operator preference: **Flight Director proposes 2-4 concrete options per micro-iteration**; operator picks or steers. **Starting surface: entity tiles** (highest-reuse chrome across all three areas, most visible impact, informs the rest).

Iteration sequence (subject to operator redirection):
1. Entity-tile dark-theme glass — pick a variant from a 4-way comparison strip in the gallery
2. Entity-tile light-theme glass — frosted-white tuning to match the dark choice
3. Active-state composition — how does `.entity-tile.active` / `[aria-selected="true"]` differ from the rest state? (Replaces `--panel-shadow-glow`)
4. Propagate to other in-scope surfaces — section-nav, popover, modal, list-item, topbar — verify the treatment scales
5. `prefers-reduced-transparency` fallback path
6. WCAG audit + narrow gate

Steps may collapse, expand, or reorder based on what the iterations surface.

## Verification (at leg close)

- Operator HAT through `#admin/design-language` (surfaces section), Studio (Agents grid → MCP Sources grid), Admin (LLM Providers grid → Built-in Tools grid), Chat (session list active state) — in both themes
- WCAG audit green
- Narrow gate green
- `prefers-reduced-transparency: reduce` simulated in DevTools — glass surfaces show as solid

## Files Affected (during the leg)

- `the_one/interfaces/web/static/css/tokens.css` — add 6 new glass tokens to both `[data-theme="dark"]` and `[data-theme="light"]` blocks
- `the_one/interfaces/web/static/css/components.css` — compose glass tokens onto in-scope chrome rules; substitute `--panel-shadow-glow` per the composition rule
- `the_one/interfaces/web/static/js/areas/admin/design-language/surfaces-section.js` — temporary variant-comparison strips during iteration; removed at leg close
- `the_one/interfaces/web/static/css/admin.css` — temporary gallery-scoped variant rules during iteration; removed at leg close
- (Possibly) `the_one/interfaces/web/static/css/chat.css` — substitute `--panel-shadow-glow` consumer at line 155
- `missions/08-gleepglorp-rebrand/flights/02-design-language/flight-log.md` — iteration trail

---

## Post-Completion Checklist

- [ ] Operator confirms aesthetic
- [ ] All glass tokens committed to `tokens.css`
- [ ] All in-scope chrome surfaces compose glass tokens
- [ ] Reduced-transparency fallback verified
- [ ] WCAG audit green
- [ ] Narrow gate green
- [ ] Temporary iteration scaffolding removed
- [ ] Flight log records iteration trail + final token values
- [ ] Leg status `landed`

## Iteration Trail

Vibe loop, operator-driven. 4 iterations converged to final values:

1. **Iteration 1 — Dark-theme entity-tile, 4-way comparison (A/B/C/D)**. Operator picked C ("Punchy / accent-tinted") as base but flagged "missing the reflective layer."
2. **Iteration 2 — Reflective treatments on top of C (C1/C2/C3/C4)**. Operator picked C2 ("Gleam overlay" — linear-gradient sheen running top→middle, 12%→2%→transparent alphas). Committed as the dark-theme tokens.
3. **Iteration 3 — Light-theme silver variants (S1/S2/S3/S4)**. Operator selected S4 reflective base + S3 violet undertone as the target mix; iteration 4 staged.
4. **Iteration 4 — S4 chrome × S3 violet intensities (M1/M2/M3)**. Operator picked M2 (border violet at 40%, 10% violet bottom-fade). Committed as light-theme tokens.

Mid-leg adjustment after propagation: popover + modal first dialed-up by dropping the competing `var(--panel-shadow)`; modal-overlay opacity reduced from 50% to 30% so the modal's backdrop-filter refraction reads through. Small pills (list-item-active, section-nav-active, chat-welcome-hover) promoted from "inset highlight only" to mini-glass (gleam-image + accent-translucent base + inset highlight). All confirmed by operator after re-check.

## Final Token Values

**Dark theme** (`[data-theme="dark"]`):
- `--glass-bg`: `rgba(167, 139, 250, 0.06)` (accent-tinted)
- `--glass-blur`: `20px`
- `--glass-saturate`: `160%`
- `--glass-border`: `rgba(167, 139, 250, 0.18)`
- `--glass-highlight`: `rgba(255, 255, 255, 0.18)`
- `--glass-gleam`: `linear-gradient(to bottom, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.02) 35%, transparent 60%)`

**Light theme** (`[data-theme="light"]`):
- `--glass-bg`: `rgba(100, 116, 139, 0.25)` (slate-500)
- `--glass-blur`: `20px`
- `--glass-saturate`: `140%`
- `--glass-border`: `rgba(109, 40, 217, 0.40)` (violet-700)
- `--glass-highlight`: `rgba(255, 255, 255, 0.95)`
- `--glass-gleam`: two stacked — `linear-gradient(to bottom, rgba(255,255,255,0.70) 0%, rgba(148,163,184,0.25) 45%, rgba(71,85,105,0.10) 75%, transparent 95%), linear-gradient(to top, rgba(167,139,250,0.10) 0%, transparent 50%)`

**Reduced-transparency fallback** (`@media (prefers-reduced-transparency: reduce)`):
- `--glass-bg` → `var(--surface)` (dark) / `var(--surface-elevated)` (light)
- `--glass-blur` → `0px` (backdrop-filter is no-op)
- `--glass-saturate` → `100%`
- `--glass-border` → `var(--border)`
- `--glass-highlight` → `rgba(255,255,255,0.06)` (dark) / `rgba(15,23,42,0.04)` (light)
- `--glass-gleam` → `none`

## Citation Audit

5 citations verified at leg design time:
- `components.css:144 .list-item.active { box-shadow: var(--panel-shadow-glow); }` — confirmed (consumer of `--panel-shadow-glow`)
- `components.css:421 .entity-tile[aria-selected="true"], .entity-tile.active { box-shadow: var(--panel-shadow-glow); }` — confirmed (consumer)
- `components.css:607 .section-nav-item[aria-current="page"] { box-shadow: var(--panel-shadow-glow); }` — confirmed (consumer)
- `chat.css:155` — confirmed consumer (Flight Design Decision lists this as the 4th consumer)
- `tokens.css:90, :191` — `--panel-shadow-glow` declarations for dark and light themes confirmed
