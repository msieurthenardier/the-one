# Leg: 01-shell-chrome-vibe

**Status**: landed
**Flight**: [Shell Chrome Polish](../flight.md)

## Objective

Apply the Flight 2 design-language vocabulary (glass + bezel + gradient) to the four outer app-shell surfaces — body bg-gradient, topbar housing rail, sidebar housing rail, `#main-content` recessed-interior — so the shell reads as a "control-panel housing" framing the polished interiors. **Interactive vibe leg** — operator drives aesthetic decisions; Flight Director presents micro-iterations (2-4 concrete options per axis).

## Context

- Flight 3.5 = the smallest flight in Mission 08 (~2 legs). Most of the design-language vocabulary is already in `tokens.css` + `components.css`; this leg composes it onto new surfaces.
- Operator flagged at kickoff: "I probably want to make some more substantive visual changes but we can work through them (the 3 main parts stay the same, its really just styling)" — the 3 layout surfaces (topbar / sidebar / main-content) stay structurally as-is; visual treatments iterate substantively. Body bg-gradient retune is in scope.
- **Pre-Leg-01 sentinel verified** at flight-design time (per Architect review): `grep -n "var(--nav-bg)\|var(--sidebar-bg)"` outside `base.css` returns ZERO hits. Shell-tier retunes have no surprise consumers.
- **Dark theme**: currently uniform `#0a0a0a` across body / nav-bg / sidebar-bg — no tier hierarchy. This leg establishes one.
- **Light theme**: existing `rail (#0f172a) > sidebar (#cbd5e1) > content (pale)` tonal hierarchy is intentional (per `tokens.css:316-319` comment). Layer texture on top; don't re-tier.

## Inputs (pre-leg state)

- `base.css:10` — `body { background: var(--bg-gradient); ... overflow: hidden; height: 100vh; }`
- `base.css:13-22` — `#app-topbar { height: var(--topbar-h); background: var(--nav-bg); border-bottom: 1px solid var(--nav-border); ... position: relative; /* for absolute popover positioning */ }` — the `position: relative` + comment are DEAD (popover retired in Flight 3 Leg 02); incidental cleanup in this leg.
- `base.css:34-36` — `#app-sidebar { width: var(--sidebar-w); background: var(--sidebar-bg); border-right: 1px solid var(--border); ... }`
- `base.css:51` — `#main-content { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }` — no background of its own; the `overflow: hidden` will clip child-painted shadows, so inset treatment likely needs pseudo-element technique.
- `tokens.css:155, :297` — `--bg-gradient` per theme (dark: navy fade `#0e1428 → #050505 70%`; light: pale slate fade `#fafbfc → #f1f5f9`).
- `tokens.css:164, :309` — `--nav-bg` per theme (dark: `var(--bg)`; light: `#0f172a` slate-900).
- `tokens.css:174, :319` — `--sidebar-bg` per theme (dark: `var(--bg)`; light: `#cbd5e1` slate-300).
- `--glass-*` + `--bezel-*` + `--motion-*` tokens defined per theme (Flight 2); reduced-preference fallbacks at the token layer.

## Outputs (post-leg state)

Operator-driven; specifics emerge during the vibe iteration. Expected shape:

- **Body `--bg-gradient`** retuned (or kept) to a chosen direction. If retuned with a peak luminance materially different from `--bg`, a `--bg-gradient-peak` token is extracted for WCAG parametrization in Leg 02.
- **Topbar (`#app-topbar`)** carries gradient overlay + `var(--glass-gleam)` + `var(--bezel-shadow-mini)` bottom edge (or equivalent housing-rail treatment).
- **Sidebar (`#app-sidebar`)** carries the mirror treatment (right-edge bezel).
- **`#main-content`** carries a recessed-interior visual (pseudo-element or non-shadow technique to survive `overflow: hidden` clipping).
- **Dark theme** tier hierarchy established (rail / sidebar / content visually differentiated).
- **`#app-topbar` `position: relative` + dead comment** removed (incidental cleanup).
- Possibly new tokens (`--shell-gleam` if the overlay literal hits the "rule of two" threshold; `--bg-gradient-peak` if the gradient retune justifies it).
- All compositions remain reduced-preference-fallback-safe (token-layer fallbacks from Flight 2 carry forward); dark-theme tier hierarchy survives the gleam-stripped reduced-transparency fallback (verified mid-leg via DevTools emulation).

## Acceptance Criteria

Vibe leg — operator-confirmed rather than mechanically verified:

- [ ] **Body bg-gradient** — operator confirms the chosen direction reads on-brand in both themes
- [ ] **Topbar** — operator confirms the housing-rail treatment reads in both themes; tier differentiates from body in dark
- [ ] **Sidebar** — operator confirms the housing-rail treatment reads in both themes; tier differentiates from body in dark + from rail in both themes
- [ ] **`#main-content`** — operator confirms the recessed-interior feel reads (without being painted-over by content)
- [ ] **Cross-axis consistency check** — operator confirms the assembled shell reads as a coherent "control-panel housing" framing the polished interiors
- [ ] **Reduced-transparency dark-theme tier-collapse check** — with `prefers-reduced-transparency: reduce` emulated, the dark-theme rail/sidebar/content tier hierarchy is still readable (tonal step, not gleam-only)
- [ ] **`#app-topbar position: relative` cleanup** — base.css:22 dead-comment-and-rule removed
- [ ] All iteration scaffolding removed (no `--temp-iter-*`, `.iter-*`, `-v{N}` leftover classes/tokens)
- [ ] WCAG audit green at leg close if any new text-on-shell parametrization needed (per Leg 02 step 2 enumeration); otherwise audit unchanged from flight start
- [ ] Narrow gate green at leg close
- [ ] Flight log updated with iteration trail

## Verification Steps

1. **Load each of the 8 pages × 2 themes**, walk through, confirm operator's on-brand assessment for the assembled shell.
2. **Reduced-transparency emulation** (DevTools → Rendering panel → Emulate CSS media → `prefers-reduced-transparency: reduce`) — verify dark-theme tier hierarchy survives.
3. **Iteration-cleanup grep**: `grep -rEn '(--temp-iter|\.iter-|--shell-iter|-v[0-9]+ )' the_one/interfaces/web/static/css/` returns nothing.
4. **Sentinel re-run** if `--nav-bg`/`--sidebar-bg` got dark-theme retunes: `grep -n "var(--nav-bg)\|var(--sidebar-bg)" the_one/interfaces/web/static/css/components.css the_one/interfaces/web/static/css/admin.css the_one/interfaces/web/static/css/studio.css the_one/interfaces/web/static/css/chat.css` still returns zero hits.
5. **Narrow gate** at leg close.

## Implementation Guidance

**Iteration order** (operator may reorder or skip):

1. **Body bg-gradient** — sets the mood for everything else. Present 2-4 options. Common directions:
   - Keep current linear fade
   - Add a third stop for horizontal tint
   - Switch to radial gradient (accent glow center; subtle dark vignette)
   - Add a subtle pattern (noise, dot, or grid overlay via SVG / radial-gradient layers)
   - Use `var(--accent-glow)` as a radial center (note: accent-binds the body backdrop)

2. **Topbar housing rail** — apply on top of `--nav-bg`. Composition options:
   - `linear-gradient(180deg, var(--nav-bg), darker)` overlay
   - `var(--glass-gleam)` reflective overlay
   - `var(--bezel-shadow-mini)` bottom edge
   - Dark theme: retune `--nav-bg` to a slight tonal step from body (`#0e0e10` / `#15151a` / similar — operator picks)

3. **Sidebar housing rail** — mirror topbar but right-edge bezel instead of bottom. Compose existing tokens where possible.

4. **`#main-content` recessed-interior feel** — `overflow: hidden` clips child shadows, so:
   - Pseudo-element technique: `#main-content::before { content: ''; position: absolute; inset: 0; box-shadow: inset 0 N px M px rgba(...); pointer-events: none; }` (requires `#main-content { position: relative }`)
   - Or 1px inner borders at the topbar-bottom + sidebar-right edges
   - Or apply the inset shadow to a wrapper around `.content-panel` rather than to `#main-content` itself

5. **Cross-axis consistency** — operator surveys all 4 surfaces in both themes; iterate if any feels off.

**In-leg checkpoint after surface 2** (per design-review): operator may optionally call to land Leg 01 partial and split into Leg 01b for remaining surfaces. Default: continue through all 4.

**"Rule of two"**: if two or more sites consume the same `linear-gradient(...)` overlay literal, extract a `--shell-gleam` (or similar) token.

**WCAG re-run mid-leg** if a surface change introduces text on a new shell-tier surface (e.g., a `--fg-muted` text node ending up on the new sidebar bg). Per Flight 2 + Flight 3 pattern: audit before continuing if the surface composition crosses an audited pair.

**Reduced-transparency dark-theme tier-collapse check** (per Architect): the Flight 2 reduced-transparency fallback blanks `--glass-gleam` and reduces `--bezel-shadow*` to static insets. Verify dark-theme rail/sidebar tier survives this fallback. If gleam is sole differentiator, retune tonal step instead.

**Incidental cleanup**: delete `base.css:22` `position: relative; /* for absolute popover positioning */` on `#app-topbar` — popover retired in Flight 3 Leg 02; no longer load-bearing.

## Edge Cases

- **`#main-content overflow: hidden`** clips inset shadows applied directly to it. Use pseudo-element or alternative technique.
- **Light theme tonal hierarchy is intentional** — don't re-tier `--nav-bg` / `--sidebar-bg` in light theme; layer texture on top.
- **Body bg-gradient retune** with a >5% lightness change at the lightest stop → extract `--bg-gradient-peak` token + add WCAG parametrization in Leg 02.
- **Accent-glow body gradient** — if operator picks a `var(--accent-glow)` direction, the body backdrop becomes accent-palette-bound. Document explicitly in the flight log as a deliberate constraint.
- **Reduced-transparency dark theme** — gleam-only tier differentiation collapses to uniform black. Tonal step IS needed in dark theme.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — possibly: `--bg-gradient` retune both themes; new `--shell-gleam` / `--bg-gradient-peak` tokens; dark-theme `--nav-bg`/`--sidebar-bg` tonal retune
- `the_one/interfaces/web/static/css/base.css` — `#app-topbar`, `#app-sidebar`, `#main-content` shell-treatment rules; `position: relative` cleanup at `:22`
- Possibly `the_one/interfaces/web/static/css/components.css` — if reduced-preference fallback blocks need new entries for new tokens
- `missions/08-gleepglorp-rebrand/flights/03.5-shell-chrome-polish/flight-log.md` — iteration trail entry
- `missions/08-gleepglorp-rebrand/flights/03.5-shell-chrome-polish/legs/01-shell-chrome-vibe.md` — status `in-flight` → `landed`

---

## Post-Completion Checklist

- [ ] All vibe acceptance criteria operator-confirmed
- [ ] WCAG audit green (with new parametrizations if needed)
- [ ] Narrow gate green
- [ ] No iteration leftovers (grep clean)
- [ ] `position: relative` dead-rule cleanup applied
- [ ] Reduced-transparency dark-theme tier survives
- [ ] Flight log updated with iteration trail
- [ ] Leg status `in-flight` → `landed` (NOT `completed`; commit step at flight close sets `completed`)
- [ ] Signal `[HANDOFF:review-needed]`

## Citation Audit

All 8 citations verified against current code at leg design time (commit `1ee6893` on `flight/03.5-shell-chrome-polish`):
- `base.css:10` — verified body bg-gradient + overflow:hidden + 100vh.
- `base.css:13-22` — verified `#app-topbar` rules including dead `position: relative` + comment.
- `base.css:34-36` — verified `#app-sidebar` rules.
- `base.css:51` — verified `#main-content` rules including `overflow: hidden` + `min-height: 0`.
- `tokens.css:155, :297` — verified `--bg-gradient` per-theme definitions.
- `tokens.css:164, :309` — verified `--nav-bg` per-theme definitions.
- `tokens.css:174, :319` — verified `--sidebar-bg` per-theme definitions.
- Pre-Leg-01 sentinel — `grep -n "var(--nav-bg)\|var(--sidebar-bg)" ... ` outside base.css returns 0 (verified at flight-design time per Architect review).

All citations clean.
