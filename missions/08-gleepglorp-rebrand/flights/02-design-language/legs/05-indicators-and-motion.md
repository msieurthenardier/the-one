# Leg: 05-indicators-and-motion

**Status**: landed
**Flight**: [Design Language — Glass + Control Panel](../flight.md)

## Objective

Land the **indicator + motion** axes of the GleepGlorp AI design language — LED-style status dots, telemetry-strip eyebrows (status readout primitive), and motion tokens (easing curves + durations). Together with Leg 03's glass and Leg 04's bezels, these complete the "control panel" aesthetic vocabulary: glass chassis + bevel chrome + lit LEDs + tactile motion.

## Type

**Interactive vibe leg.** Flight Director presents 2-4 concrete variants per micro-iteration; operator picks or steers. No autonomous Developer-agent implementation.

## Context

- Leg 5 of 6 — the last vibe leg. Glass (L3) and bezels (L4) substrate is locked at P2 pullback values.
- Flight Design Decision: net-new primitives only land if there's an actual consumer. Speculative additions stay as gallery samples without graduating to `components.css`. So:
  - **LED indicator** — likely graduates: existing `.test-result-*` family + OAuth status + MCP source connection state all want a lit-status affordance
  - **Telemetry strip** — gallery sample only unless a polish flight (3/4/6) actually consumes it. The flight Design Decisions resolved that this is a **sibling primitive to `.section-title`**, not a variant of it (Leg 02 resolution).
- Flight Design Decision: `prefers-reduced-motion: reduce` reset for ANY motion that animates layout/scale/translate. Easing curves and color transitions are exempt (no vestibular risk).
- Same vibe cadence as Legs 03/04: 2-4 options per iteration.

## Surfaces in Scope

LED indicators applied to:
- `.test-result-{ok,fail,warning,pending}` — provider/tool/MCP connection-test results
- OAuth status (Studio MCP editor, OAuth pause/replay flow)
- MCP source connection state (Studio MCP grid)
- (Possibly) agent "active" indicator if natural

Telemetry strip — proves itself in the gallery; promotes to `components.css` only if a polish flight finds it useful.

Motion tokens applied to:
- Existing transition rules across the app (currently inline `transition: ... 0.15s ease`). Retune to use `var(--motion-fast) var(--ease-tactile)` etc. so the motion language is consistent and tunable.

## Tokens to Land

Indicator primitives:
- `.indicator-led` base class (8px dot, by default) — graduates to `components.css` if consumed
- `.indicator-led--{success,warning,danger,idle}` status modifiers
- `--indicator-led-glow-{success,warning,danger}` if glow intensity needs theming (TBD)

Telemetry strip primitive:
- `.telemetry-strip` — gallery-only by default; promotes if used elsewhere
- `.telemetry-strip-value` for the right-side status readout
- May reuse `.section-title` typography

Motion primitives:
- `--ease-tactile` — primary easing curve
- `--ease-overshoot` — optional secondary for delight moments (TBD if needed)
- `--motion-fast` — 100-150ms (hover, focus, small state changes)
- `--motion-base` — 200-300ms (panel transitions, tab switches)
- (Possibly) `--motion-slow` for area-switch transitions if observed need

Reduced-motion fallback:
- `@media (prefers-reduced-motion: reduce)` block overriding `--motion-*` to `0ms` (or near-zero) at the token level

## Acceptance Criteria

Operator-driven; acceptance is by operator confirmation:

- [x] LED indicator primitive `.indicator-led` committed to `components.css` (real primitive — graduated because it has real consumers via the `.test-result-*` retrofit)
- [x] LED status modifiers `.indicator-led--{success,warning,danger,idle}` defined
- [x] LED applied to ALL `.test-result-*` consumers via `::before` pseudo-element retrofit — picks up provider editor, agent editor, tool editor connection-test results automatically with zero JS changes
- [~] LED applied to OAuth status surfaces — DEFERRED to Leg 06 HAT decision. OAuth has a dedicated `.area-chat .oauth-required-notice` and other surfaces; not a `.test-result-*` consumer, so they don't auto-retrofit. Leg 06 surveys at HAT time.
- [~] LED applied to MCP source connection state — DEFERRED similarly. Studio MCP grid surfaces connection state via a different markup path; doesn't auto-retrofit. Leg 06 HAT decision.
- [x] Telemetry-strip sample in gallery (`.telemetry-strip` + `.telemetry-value`); gallery-only by default per flight design — rules scoped to `.area-admin` until a downstream polish flight finds a consumer and promotes them out of admin.css scope
- [x] Motion tokens (`--ease-tactile`, `--motion-fast`, `--motion-base`) defined in `tokens.css` for both themes
- [x] `.entity-tile` transition retuned to use motion tokens — also implements asymmetric in/out timing (fast-in on `:hover`, slow-out on base rule)
- [x] `prefers-reduced-motion: reduce` fallback lands at the token layer — durations collapse to 0ms
- [x] Operator confirmed aesthetic on both axes
- [x] WCAG audit still green
- [x] Narrow test gate still green: 56 passed
- [x] Flight log updated with iteration trail and final token values
- [x] All temporary variant scaffolding REMOVED — `grep -rn 'indicator-led-variant\|telemetry-strip-t1\|telemetry-strip-t2\|telemetry-strip-t3\|ITERATION \|TELEMETRY STRIP'` returns 0 hits

## Iteration Strategy

Tentative sequence (subject to operator redirection):
1. LED indicator visual style — 4-way comparison (flat / subtle glow / strong glow / chrome lit) on `.test-result` surface in the gallery STATUS section
2. LED size + status colors — confirm 8px default and per-status fills
3. Telemetry strip — 2-3 layout variants in gallery (status-on-right pill / value-after-eyebrow / split-with-divider)
4. Motion easing + durations — pick `--ease-tactile` curve + duration scale
5. Wire LEDs to test-result + OAuth + MCP consumers
6. Re-run reduced-motion + WCAG + narrow gate

## Files Affected (during the leg)

- `the_one/interfaces/web/static/css/tokens.css` — motion tokens + reduced-motion fallback
- `the_one/interfaces/web/static/css/components.css` — `.indicator-led` primitive if graduated; `.test-result-*` retunes to compose LED; transition retunes
- `the_one/interfaces/web/static/js/areas/admin/design-language/status-section.js` — telemetry strip sample
- (Variable) JS files emitting test-result spans — may need to add `.indicator-led .indicator-led--{status}` markup if LEDs are added as separate elements
- `the_one/interfaces/web/static/js/areas/admin/design-language/surfaces-section.js` — temporary LED variant scaffolding; removed at close
- `the_one/interfaces/web/static/css/admin.css` — temporary gallery-scoped variant rules; removed at close
- `missions/08-gleepglorp-rebrand/flights/02-design-language/flight-log.md` — iteration trail

---

## Iteration Trail

Vibe loop, operator-driven. 3 distinct iterations + a one-tweak refinement at the close:

1. **LED iteration 1 — 4 visual styles (A=Flat, B=Subtle glow, C=Strong glow, D=Chrome lit)**. Operator observed "I can hardly tell the difference between A, B, and C" at the 8px dot size — the box-shadow glows weren't pulling visual weight relative to the dot. Picked **D direction** ("OK, but can look rounder with a bright reflective crescent").
2. **LED iteration 2 — reflective-crescent D variants (D1=Subtle, D2=Bright, D3=Top-dome, D4=Pronounced)** — 10px dots with radial-gradient highlights at different positions and intensities. Operator picked **D2** but requested adding a darker crescent on the opposite side. Committed D2 + bottom-right shadow as the canonical `.indicator-led` primitive in `components.css`, plus a `::before` retrofit on `.test-result-*` so existing connection-test consumers pick up the LED automatically.
3. **Telemetry-strip iteration — 3 layouts (T1=Justified, T2=Inline, T3=Table)** — operator picked **T1** (eyebrow left, status right, divider line between rows). Committed as the gallery sample `.telemetry-strip`, gallery-only per flight design.
4. **Motion tokens** — committed Material "standard" easing (`cubic-bezier(0.4, 0, 0.2, 1)`) + 150ms/250ms durations as starter. Operator hover-tested and asked "on mouse out it should fade a little slower." Implemented asymmetric in/out: fast (`--motion-fast = 150ms`) on `:hover`, slow (`--motion-base = 250ms`) on base rule. Operator confirmed.
5. **Interactive primitives pass** (operator: "what about the buttons, checkboxes, fields, selectors, etc?"). Surfaced a real gap — flight design called for buttons/fields/checkboxes to carry the aesthetic but vibe iterations had focused on chrome. Iterations:
   - **Buttons**: cycled through B1-B4 (LED-style radials), V1-V4 (Apple/Mac linear bands), V3 dimming variants → V3b locked. Operator then asked about reproducing original Aqua look; researched canonical CSS-Aqua (girliemac/btxx), iterated through pill-vs-rect, fade, bottom-bounce, body-darkening — but operator pulled back: "ive gone down the rabbit hole of trying to reproduce this button rather than doing whats right for the UI." Reverted to V3b as canonical button-family treatment: `.btn-outlined-primary`, `.btn-filled-primary`, `.btn-muted-destructive`, AND `.app-picker-button` all use the V3 white→fade→dark gradient + `--glass-border` + `--bezel-shadow-mini` + asymmetric in/out motion. Filled-primary keeps solid-accent fill + accent-glow halo; muted-destructive uses destructive bg-soft + danger border. Added `--bezel-shadow-inset` token for the recessed feel on form inputs (also in reduced-transparency fallback).
   - **Fields**: `.field-input/textarea/select` get `--bezel-shadow-inset` (recessed, opposite of raised bezel). Focus state stacks the inset with accent-glow.
   - **Native `<select>` options**: surface-elevated bg, padding, hover, checked states styled within native-CSS limits. Custom dropdown component deferred to a future polish flight as mission Known Issue (rounded-corner popup chrome unstylable in pure CSS).
   - **Checkbox primitive**: 14px → 16px, kept 1.5px border, dropped `border-radius`, dropped inset-highlight on checked, `vertical-align: middle`, checkmark repositioned `top: 0` for proper centering.
   - **Chips**: accent-translucent base + `--glass-border` (colored but flat — no gradient, no shadow).
6. **Bug surfaced during cumulative review**: nested scrollbars on `#admin/design-language` page. `.admin-content` had `overflow-y: auto` AND `.design-language-sections` redundantly added it. Removed the inner overflow rule.

## Final Token Values

**LED primitive** (`components.css`, canonical):
- `.indicator-led` — 10px round dot, inline-block; two stacked `radial-gradient` `background-image` layers (white top-left crescent + black bottom-right shadow)
- `.indicator-led--success/warning/danger/idle` — fill from `--status-*` tokens; outer glow from matching `--status-*-glow` tokens (idle has no glow)
- `.test-result-{ok,fail,warning,pending}::before` — same visual, applied to existing `.test-result` consumers

**Telemetry strip** (`admin.css`, gallery-scoped):
- `.telemetry-strip` — `display: flex; justify-content: space-between` row with bottom-border
- `.telemetry-value` — inline-flex mono-uppercase status readout
- Reuses canonical `.section-title` for the left eyebrow + `.indicator-led` for status dots

**Motion tokens** (`tokens.css`, both themes — values identical, theme-agnostic):
- `--ease-tactile`: `cubic-bezier(0.4, 0, 0.2, 1)`
- `--motion-fast`: `150ms`
- `--motion-base`: `250ms`

**Asymmetric transition on `.entity-tile`**:
- Base rule: `transition: ... var(--motion-base) var(--ease-tactile)` (slow on mouse-out)
- `:hover` rule: same transition but with `var(--motion-fast)` (fast on mouse-in)

**Reduced-motion fallback** (`@media (prefers-reduced-motion: reduce)`):
- `--motion-fast` → `0ms`, `--motion-base` → `0ms` (instant state changes; easing curves are exempt)

## Post-Completion Checklist

- [ ] Operator confirms aesthetic on both axes (indicators + motion)
- [ ] LED indicator primitive committed if it has a real consumer; otherwise stays in gallery
- [ ] Motion tokens committed; at least one transition retuned to use them
- [ ] `prefers-reduced-motion` fallback verified
- [ ] WCAG audit green
- [ ] Narrow gate green
- [ ] Temp scaffolding removed
- [ ] Flight log updated
- [ ] Leg status `landed`
