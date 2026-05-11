# Leg: 04-chrome-bezels

**Status**: landed
**Flight**: [Design Language — Glass + Control Panel](../flight.md)

## Objective

Establish the **bezel / chrome** axis of the GleepGlorp AI design language — raised-edge treatment that makes glass surfaces feel like physical control-panel chrome rather than flat translucent layers. Builds directly on top of the Leg 03 glass substrate. Iteration is operator-driven in the live gallery; this artifact records the final state.

## Type

**Interactive vibe leg.** Flight Director presents 2-4 concrete CSS variants per micro-iteration; operator picks or steers. No autonomous Developer-agent implementation.

## Context

- Leg 4 of 6. Glass substrate from Leg 03 is in place (6 `--glass-*` tokens across both themes, applied to entity-tile + popover + modal + small pills).
- Flight Design Decision: glass surfaces use `--glass-highlight + --bezel-shadow` as elevation cue (replacing the dropped `--panel-shadow-glow`). Leg 03 added the highlight slot; Leg 04 fills the bezel-shadow slot.
- Bezel composition: replaces the current `box-shadow: inset 0 1px 0 var(--glass-highlight)` with a multi-stop inset shadow that expresses BOTH a lit top edge AND a darker bottom edge, plus optional inner soft glows for a "machined" feel.
- Directional light convention: pick one (top-only vs top-left vs ambient) and apply consistently across all glass chrome.
- Corner machining: optional retune of `--panel-radius` (currently 10px) if a different roundness reads as more "control-panel."

## Tokens to Land

- `--bezel-highlight` — sharp top-edge lit line (1-2px)
- `--bezel-highlight-soft` — softer inner glow that radiates from the top edge (4-6px, lower alpha)
- `--bezel-shadow` — sharp bottom-edge dark line (1-2px)
- `--bezel-shadow-soft` — softer inner shadow from the bottom edge
- (Possibly) `--bezel-corner-highlight` / `--bezel-corner-shadow` — directional corner accents if top-left convention is chosen
- (Possibly retuned) `--panel-radius` if corner machining iteration calls for it

## Surfaces in Scope (Leg 04)

Touched in this leg (anywhere Leg 03 landed glass):
- `.entity-tile` + active state (canonical starting surface)
- `.app-picker-popover` (full glass — gets full bezel)
- `.modal-dialog` (full glass — gets full bezel)
- `.list-item.active` (mini-glass — gets simplified bezel)
- `.section-nav-item[aria-current="page"]` (mini-glass — gets simplified bezel)
- `.chat-welcome-item:hover` (mini-glass — gets simplified bezel)

Composition rule:
- Full-glass surfaces: full bezel (top highlight + bottom shadow + optional soft glows)
- Mini-glass surfaces: simplified bezel (top highlight + bottom shadow, no soft glows — perf, small surface)

## Acceptance Criteria

This leg is operator-driven; acceptance is by **operator confirmation**:

- [x] Bezel tokens land in `tokens.css` for both themes: `--bezel-shadow` (full, 6-layer stacked-depth) and `--bezel-shadow-mini` (simplified, 2-layer edge-only for small pills)
- [x] In-scope chrome surfaces compose the bezel tokens — `.entity-tile`, `.app-picker-popover`, `.modal-dialog` use `var(--bezel-shadow)`; `.list-item.active`, `.section-nav-item[aria-current="page"]`, `.chat-welcome-item:hover` use `var(--bezel-shadow-mini)`
- [x] Directional light convention (top-left) applied consistently across all surfaces — same 6 box-shadow layers everywhere with `1px/1px` offsets
- [x] `--panel-radius` retuned from 10px → 6px (R2 corner machining); collapses with `--panel-radius-sm` which was already 6px (`-sm` slot kept as separate token in case operator wants to retune it lower later)
- [x] Operator confirmed aesthetic in both themes
- [x] WCAG audit still green
- [x] Narrow test gate still green: 56 passed in 0.89s
- [x] `prefers-reduced-transparency` fallback extended to cover both bezel tokens (degrade to 1px directional edge only — preserves elevation cue without layered glows)
- [x] Flight log updated with iteration trail and final token values
- [x] All temporary variant scaffolding REMOVED — `grep -rn 'bezel-variant\|design-language-bezel-variants\|corner-variant\|design-language-corner-variants\|ITERATION '` returns zero hits

## Iteration Strategy

**Starting surface: entity tiles** (carries over from Leg 03 — most-reused chrome, most-visible change).

Tentative iteration sequence:
1. Entity-tile bezel style — pick from 4-way comparison strip (thin / layered / directional / heavy)
2. Optional directional-light dial (if not settled in step 1)
3. Optional corner machining — try a few `--panel-radius` values if current 10px feels wrong with the bezel
4. Propagate to other glass surfaces
5. Re-verify reduced-transparency fallback + WCAG + narrow gate

## Files Affected (during the leg)

- `the_one/interfaces/web/static/css/tokens.css` — add bezel tokens to both themes + reduced-transparency override block
- `the_one/interfaces/web/static/css/components.css` — update `box-shadow` on glass surfaces to compose the new bezel tokens
- `the_one/interfaces/web/static/css/chat.css` — same, for `.chat-welcome-item:hover`
- `the_one/interfaces/web/static/js/areas/admin/design-language/surfaces-section.js` — temporary variant scaffolding during iteration; removed at close
- `the_one/interfaces/web/static/css/admin.css` — temporary gallery-scoped variant rules; removed at close
- `missions/08-gleepglorp-rebrand/flights/02-design-language/flight-log.md` — iteration trail

---

## Iteration Trail

Vibe loop, operator-driven. 3 iterations on bezel + 1 on corner machining + 1 pullback after operator viewed everything together:

1. **Iteration 1 — 4 bezel styles (A=Thin, B=Layered, C=Directional, D=Heavy chrome)**. Operator observed "A and B are almost identical" (the layered soft glows weren't pulling weight at those alphas), "D sort of has bezel effect but not really" (spread without edge definition), and chose the **directional top-left light convention from C** as the right direction.
2. **Iteration 2 — 4 top-left directional intensities (C1=Subtle, C2=Standard, C3=Strong, C4=Heavy w/depth)**. Operator picked C4's structure (stacked 4px + 10px glows for concave-interior depth) but flagged contrast as too high.
3. **Iteration 3 — C4 structure with C1/C2-level alphas (S1=Soft, S2=Mid, S3=Standard)**. Operator initially picked S3 — C4's stacked depth at C2 alphas. Committed as `--bezel-shadow` token.
4. **Corner machining — 4 panel-radius values (R1=2px, R2=6px, R3=10px current, R4=14px)**. Operator picked **R2** (6px) — collapses with existing `--panel-radius-sm`; cascades app-wide.
5. **Pullback iteration (post-Leg-04-close back-track)** — operator surveyed the cumulative result and observed "we went a little hard on the bevel, the background color is overly frosted." Staged 3 simultaneous-axis pullback variants (P1=~20% lighter, P2=~40%, P3=~60%) dialing back BOTH glass (blur, saturate, gleam alphas, bg-tint alpha) and bezel (drop the 10px outer glow, lower edge/glow alphas). Operator picked **P2**. Committed as the retuned `--glass-*` AND `--bezel-shadow` tokens.

## Final Token Values

**Glass (both themes — P2 pullback)**:
- Dark: `--glass-bg: rgba(167,139,250,0.04)` / `--glass-blur: 12px` / `--glass-saturate: 130%` / `--glass-gleam: linear-gradient(to bottom, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.01) 30%, transparent 55%)`
- Light: `--glass-bg: rgba(100,116,139,0.15)` / `--glass-blur: 12px` / `--glass-saturate: 130%` / `--glass-gleam` two stacked: bottom-light-shimmer + top-violet-glow at lower alphas
- Border + highlight tokens unchanged from Leg 03

**Bezel (both themes — P2 pullback — same alphas across themes)**:
- `--bezel-shadow`: `inset 1px 1px 0 rgba(255,255,255,0.22), inset -1px -1px 0 rgba(0,0,0,0.18), inset 2px 2px 4px rgba(255,255,255,0.07), inset -2px -2px 4px rgba(0,0,0,0.09)` (4-layer, dropped the 10px outer glow)
- `--bezel-shadow-mini`: `inset 1px 1px 0 rgba(255,255,255,0.22), inset -1px -1px 0 rgba(0,0,0,0.18)` (2-layer edge only)

**Corner machining**:
- `--panel-radius`: `6px` (retuned from 10px)
- `--panel-radius-sm`: unchanged at 6px (now equal to `--panel-radius`)

**Reduced-transparency fallback** (`@media (prefers-reduced-transparency: reduce)`):
- `--bezel-shadow`, `--bezel-shadow-mini` → single-layer 1px directional edge (theme-tuned alphas)
- All other glass tokens degrade to opaque non-blurring values per Leg 03 fallback

## Post-Completion Checklist

- [ ] Operator confirms aesthetic
- [ ] Bezel tokens committed to `tokens.css`
- [ ] All in-scope glass surfaces compose bezel tokens
- [ ] `prefers-reduced-transparency` fallback verified
- [ ] WCAG audit green
- [ ] Narrow gate green
- [ ] Temp scaffolding removed
- [ ] Flight log updated
- [ ] Leg status `landed`
