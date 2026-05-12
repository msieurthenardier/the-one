# Flight: Shell Chrome Polish

**Status**: in-flight
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] A coherent visual identity anchored to the new logo and a purple-led palette is present and consistent across all three areas, in both light and dark themes *(this flight closes the outer-shell gap so the design language reads end-to-end, not just inside each area's polished surfaces)*
- [ ] The visual identity has a deliberate aesthetic direction (robot / control-panel) documented in a live design-language gallery page *(shell housing reinforces the "control-panel" framing — the polished interiors live inside a frame that also reads as part of the housing)*
- [ ] Color contrast meets WCAG AA across the rebranded palette *(re-verify after any token retunes touch text-on-shell-chrome pairs)*
- [ ] All existing functionality (M01–M07 capabilities) continues working *(no behavioral change in this flight; aesthetic only)*
- [ ] Automated browser tests pass after the rebrand and polish work; local visual-snapshot baselines regenerate cleanly *(closing leg regenerates baselines for the post-polish state)*

---

## Pre-Flight

### Objective

Apply the Flight 2 design-language vocabulary (glass + bezel + gradient) to the **outer app-shell surfaces** that Flight 2's component-focused work and Flight 3's per-page focus both missed: `#app-topbar` strip, `#app-sidebar` rail, `#main-content` frame, `body` `bg-gradient`. Surfaced as a Flight 2 underscoping at Flight 3 close (the debrief's flight-design-accuracy finding). Aesthetic target: a **control-panel housing** that frames the polished interior — the shell reads as part of the same "control-panel" metaphor the components live inside, not as a flat backdrop to them. Sequenced BEFORE Flight 4 (Studio Polish) so Studio + Chat polish flights inherit a polished shell rather than re-discover the gap.

### Open Questions

- [x] **Where does the bulk of the visual differentiation come from in dark theme?** Currently `--nav-bg` = `--sidebar-bg` = `var(--bg)` = `#0a0a0a` — uniform black. The shell needs some elevation hierarchy. Working assumption: introduce a small `--shell-elevation-1`/`--shell-elevation-2` tonal step (e.g., topbar 1-2% lighter than body, sidebar 0.5-1% lighter, or composing glass-tinted overlays on top of body bg) so the rail/sidebar/content tiers read visually. Operator-resolved in Leg 01 vibe.
- [x] **Light theme already has a tiered shell** (rail = slate-900, sidebar = slate-300, content = pale). Working assumption: apply glass/bezel texture ON TOP of the existing tonal hierarchy rather than retuning the colors. Operator-resolved in Leg 01 vibe.
- [x] **Glass on the topbar — backdrop-filter or static layered surface?** Topbar sits at the top of the viewport; nothing is "behind" it to refract. Working assumption: `backdrop-filter` is not the right tool for the topbar specifically. Use a `linear-gradient` + `--glass-gleam` overlay + `--bezel-shadow-mini` bottom edge for the "housing rail" look. Same for sidebar (nothing scrolls behind it). Operator-resolved in Leg 01.
- [x] **`body { background: var(--bg-gradient) }` — retune the gradient or keep it?** Current dark gradient is `linear-gradient(180deg, #0e1428 0%, #050505 70%)` — a navy-to-black vertical fade. Working assumption: retune to better evoke the "control-panel housing depth" aesthetic. Options on the table: keep linear; switch to radial (accent glow from center); add a third stop for subtle horizontal tint. Operator picks in Leg 01.
- [x] **`#main-content` frame treatment** — should it have its own background or stay transparent (inheriting body)? Working assumption: keep transparent so the body-gradient reads through; add a subtle inset shadow at the chrome-borders so the content "sits inside" the housing. Operator-resolved in Leg 01.
- [x] **Sub-leg structure**: 2 legs (vibe + close) per operator hint. Recorded in Design Decisions.
- [x] **Carry-forward Flight 3 debrief items** — Action Items #4 (codify topbar `<img>` CLS contract in agents.md) + #5 (codify legacy-class-as-JS-handle pattern in agents.md): fold into Leg 02's close-step #7 (agents.md F3.5 subsection). Action Item #1 (Playwright B2 regression test): defer to Flight 4 (Studio Polish will implement `confirmLeave` for parity and can add the test for both areas in one pass). Recorded in Design Decisions.
- [ ] **New tokens vs compose existing** — specific value-naming decisions. Working assumption: introduce minimal new tokens (`--shell-bg-rail`, `--shell-bg-content`?) only if compositions of existing `--glass-*` + `--bezel-*` + theme bg tokens prove insufficient. Resolved in Leg 01 vibe.
- [ ] **Reduced-transparency / reduced-motion posture** — same token-layer fallback pattern as Flight 2 (the `@media (prefers-reduced-*)` blocks at the end of `@layer tokens`). Verify in Leg 02 alignment HAT.

### Design Decisions

**Two-leg flight structure: vibe + close**: Leg 01 is an interactive vibe leg (operator drives shell-treatment aesthetic decisions for topbar / sidebar / body / main-content). Leg 02 is the closing alignment leg (10-step ordered close template from Flight 2 Leg 06 / Flight 3 Leg 07).
- Rationale: Mirrors the operator-validated cadence from Flight 2 (3 vibe legs + 1 close) and Flight 3 (mixed legs + 1 close). Smaller flight → fewer vibe legs needed; the shell is a single coherent unit of work rather than 3 distinct surface-treatment axes.
- Trade-off: All 4 surfaces (topbar / sidebar / body / main-content) iterate within one vibe leg rather than separating by axis. Acceptable — they're tightly coupled (the housing concept demands consistency across surfaces).

**Topbar + sidebar use static layered surfaces (no `backdrop-filter`)**: Both surfaces sit at viewport edges; nothing scrolls behind them to refract. Use `linear-gradient` overlay + `--glass-gleam` + `--bezel-shadow-mini` bottom/right edge.
- Rationale: `backdrop-filter` has nothing useful to do when the underlying content is `body` (which has its own bg-gradient). Compositing the gleam + bezel onto the existing `--nav-bg`/`--sidebar-bg` is the right move.
- Trade-off: Doesn't compose the `--glass-*` blur tokens. Acceptable — the "housing rail" aesthetic doesn't need transparency; it needs texture.

**Light theme retunes texture ON TOP of existing tonal hierarchy**: Light theme already has `--nav-bg: #0f172a` (slate-900) > `--sidebar-bg: #cbd5e1` (slate-300) > body pale gradient. The "rail < sidebar < content" elevation chain exists; this flight adds glass/bezel texture to that chain rather than re-tier the colors.
- Rationale: The existing tonal hierarchy is intentional (per the `--sidebar-bg` comment in `tokens.css`). Disrupting it would re-litigate Flight 1 palette decisions.
- Trade-off: Less aesthetic flexibility in light theme than in dark (where the shell is currently uniformly black). Acceptable — light theme already has a good substrate.

**Dark theme establishes tier hierarchy via tonal steps + glass overlay**: Dark currently has `--nav-bg` = `--sidebar-bg` = `--bg` = `#0a0a0a`. Need to introduce ~1-2% lightness step for rail and sidebar (or a glass overlay that does it visually).
- Rationale: Without some tier hierarchy, the topbar and sidebar read as part of body — no "housing" feel possible. The values are operator-driven in Leg 01.
- Trade-off: Possible WCAG re-audit if `--fg` text appears on the new rail/sidebar tones. Verify in Leg 02 step 2.

**`body { background: var(--bg-gradient) }` retune in scope**: The `--bg-gradient` token itself is candidate-for-retune in Leg 01 (operator drives). Likely directions: keep current linear; switch to radial (accent glow); add a subtle pattern.
- Rationale: The body gradient is the largest aesthetic surface in the app; it's the canvas the housing sits on. Worth a deliberate vibe pass.
- **WCAG audit gap (per design-review Architect)**: the audit captures `--fg` on `--bg` (gradient's bottom anchor) but NOT arbitrary gradient mid-points. If the retune introduces a radial accent glow or a third stop with materially different luminance from `--bg`, text-on-gradient-midpoint could silently fail while the audit stays green. **Required**: if Leg 01 lands a gradient whose lightest stop differs >5% lightness from `--bg`, extract the lightest stop as a named token (e.g., `--bg-gradient-peak`) and add a `(theme, fg, bg_gradient_peak, 4.5)` parametrization in Leg 02 step 2.
- **Accent-binding caveat**: if the operator picks a `var(--accent-glow)` radial direction in Leg 01, the body backdrop becomes accent-palette-bound. Working assumption: prefer accent-independent retunes (so a future mission palette swap doesn't drag the shell with it) — but if the operator's chosen direction REQUIRES accent-binding, document it explicitly in the flight log as a deliberate constraint.

**`#main-content` stays transparent + composes `--bezel-shadow-inset` for "recessed interior" feel**: No background of its own; inherits body bg-gradient. Add an inset shadow at the topbar-bottom + sidebar-right edges so the content area reads as "sitting inside" the housing.
- Rationale: Reinforces the housing-around-interior metaphor without adding a new fill color.
- Trade-off: Inset shadows are subtle in many displays; operator confirms in Leg 01 vibe.

**`backdrop-filter` performance posture**: Even though topbar/sidebar don't use `backdrop-filter`, the chrome already on top (`.app-picker-popover`, `.modal-dialog`, glass `.entity-tile`s) does. No change here. Reduced-transparency fallbacks from Flight 2 carry forward unchanged.

**No new flight-design template patterns required**: The 10-step ordered close template (Flight 2 Leg 06 / Flight 3 Leg 07) applies as-is. No new closing-leg step needed for this flight's scope.

**Defer Playwright B2 regression test to Flight 4**: Flight 3 debrief Action Item #1 (Playwright test for cross-area dirty-gate path). Defer to Flight 4 because Studio Polish will implement `confirmLeave` on its area descriptor for parity; the test can be added once for both areas in one pass.
- Rationale: Premature test now would only cover admin; Flight 4 enables the comprehensive add.
- Trade-off: B2 regression stays HAT-verified-only for one more flight.
- **Guard against slip** (per Architect): when Flight 4 is designed, add an explicit entry-condition row in the Flight 4 mission-criteria/spec asserting that Studio `confirmLeave` + cross-area regression test ship together. If Flight 4 doesn't land it, it slips to Flight 7 (UI Performance Audit catch-all).

**Carry-forward agents.md docs items folded into Leg 02 close**: Flight 3 debrief Action Items #4 + #5 (topbar `<img>` CLS contract + legacy-class-as-JS-handle pattern). Both are small additions; piggyback the F3.5 agents.md subsection added at Leg 02 step 7.

### Prerequisites

- [x] Mission 08 active; Flights 1 + 2 + 3 completed and merged to main (latest: `1ee6893`)
- [x] Flight 2 design-language vocabulary committed and consumed across `tokens.css` + `components.css`
- [x] `--glass-*` + `--bezel-*` + `--motion-*` tokens defined per theme and reduced-preference-fallback-protected
- [x] `--bg-gradient`, `--nav-bg`, `--sidebar-bg` tokens defined per theme (light: tiered hierarchy; dark: currently uniform black)
- [x] `body { overflow: hidden }` + flex-column `min-height: 0` chain established (Flight 3 Leg 03) so any inner-content shifts from shell treatments don't propagate document-level scroll
- [x] `tests/test_design_tokens_a11y.py` WCAG audit + Python mirror in place
- [x] Snapshot baselines from Flight 3 Leg 07 captured (10/12 pass; 2 known-issue carry-forward)
- [ ] Narrow-test-gate fallback documented for legs 01 + 02 (broad pytest hangs on SQLite WAL anomaly per Flights 1/2/3 debriefs; same narrow gate works)
- [ ] Operator available for Leg 01 vibe + Leg 02 HAT — no batchable surrogate

### Pre-Flight Checklist

- [x] All open questions for pre-flight scope resolved (concrete shell-treatment values deferred to in-leg resolution and NOT pre-flight blockers)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [ ] Legs defined (two legs, see below)

---

## In-Flight

### Technical Approach

**Two-leg flight: vibe + close.** Leg 01 is fully interactive — operator drives aesthetic decisions for shell-treatment values across all 4 surfaces. Leg 02 is the 10-step ordered close template (per Flight 2 Leg 06 + Flight 3 Leg 07).

**Leg 01 — Shell-chrome vibe** (interactive, vibe-driven):

Flight Director presents 2-4 concrete options per micro-iteration for each surface; operator picks; values commit to `tokens.css` / `base.css` / `components.css`; reload, iterate. Order:

1. **Body bg-gradient** (largest canvas — sets the mood). Operator picks: keep current linear, switch to radial-accent-glow, add a horizontal third stop, or some other direction.
2. **Topbar housing rail** — gradient overlay + gleam + bezel-mini bottom edge. Treatment composes `linear-gradient` (new topbar-specific) + `var(--glass-gleam)` + `var(--bezel-shadow-mini)` (bottom-edge variant). Dark theme: introduce tonal step from body (e.g., `--nav-bg` retune to `#15151a` or similar — operator chooses). Light theme: layer texture on top of existing `#0f172a` (no color retune).
3. **Sidebar housing rail** — mirror the topbar treatment for the sidebar (right-edge bezel instead of bottom). Compose existing tokens.
4. **`#main-content` recessed-interior feel** — add `box-shadow: var(--bezel-shadow-inset)` (or a variant) so the content area reads as "inside" the housing. **Implementation caveat**: `#main-content` is `overflow: hidden` AND its `.content-panel` flex-children paint full-bleed, which can clip the inset shadow. Likely needs the inset applied via a pseudo-element on `#main-content` OR via a non-shadow technique (e.g., 1px top + left inner borders) to avoid being painted over.

5. **Cross-axis consistency check** — operator surveys the assembled shell across all 4 surfaces, both themes, and confirms the housing-around-interior metaphor reads correctly. Iterate if any surface feels off.

**In-leg checkpoint after surface 2** (escape hatch per design-review Architect — 4 surfaces × 3-8 iterations each = potentially 12-32 iterations in one leg, plausibly oversized): after the topbar lands (surface 2), operator may optionally call to land Leg 01 partial and split remaining surfaces (sidebar / main-content / cross-axis) into a new Leg 01b. Default: continue through all 4 surfaces in one leg unless operator surfaces fatigue.

Mid-leg WCAG re-run if any surface change touches a text-on-shell pair (e.g., a `--fg-muted` text on the new sidebar bg). Per Flight 2 + Flight 3 pattern: audit before continuing if the surface composition crosses an audited pair.

**"Rule of two" for token extraction**: if the vibe iteration ends with two or more sites consuming the same `linear-gradient(...)` overlay literal, extract a `--shell-gleam` (or similar) token. Codifies the project's implicit DRY threshold.

**Pre-Leg-01 sentinel** (verified at flight-design time, per Architect review): `grep -n "var(--nav-bg)\|var(--sidebar-bg)" the_one/interfaces/web/static/css/components.css the_one/interfaces/web/static/css/admin.css the_one/interfaces/web/static/css/studio.css the_one/interfaces/web/static/css/chat.css` returns ZERO hits — shell-tier retunes have no surprise consumers outside base.css. Re-run this sentinel during Leg 01 if the operator picks dark-theme `--nav-bg`/`--sidebar-bg` retunes to confirm no drift.

**Reduced-transparency dark-theme tier-collapse check** (per Architect): the Flight 2 reduced-transparency fallback blanks `--glass-gleam` and reduces `--bezel-shadow*` to static insets. If the dark-theme tier hierarchy depends primarily on the gleam overlay for visual differentiation, reduced-transparency dark collapses back to uniform black. **Required**: verify in Leg 01 that the dark-theme rail/sidebar tier reads correctly under reduced-transparency (use DevTools emulation). If the gleam is the sole differentiator, retune dark `--nav-bg`/`--sidebar-bg` so tonal steps survive the gleam-stripped fallback.

**Incidental cleanup in Leg 01** (per Architect): `base.css:22` `position: relative; /* for absolute popover positioning */` on `#app-topbar` is dead — the app-picker popover was retired in Flight 3 Leg 02; the comment and rule are no longer load-bearing. Delete both as a 1-line tidy that fits the housing-polish theme.

**Leg 02 — Alignment + snapshot regen + agents.md F3.5** (10-step ordered close):

Each step's output is the next step's input — strict ordering:

1. **Pre-close grep sweep** — `grep -E '#[0-9a-f]{3,6}' the_one/interfaces/web/static/css/*.css | grep -v tokens.css` (no hex literals leaked outside tokens), plus any shell-specific sentinels.
2. **Run WCAG audit** — `docker exec the-one pytest tests/test_design_tokens_a11y.py -v`. Audit must be green BEFORE snapshot regen. **Required new parametrizations regardless of vibe-leg outcome** (per design-review Architect finding — current audit covers `--fg`/`--fg-secondary`/`--fg-muted` only on `--bg`/`--surface`, not on `--nav-bg` or `--sidebar-bg` — and `--sidebar-bg: #cbd5e1` × `--fg-muted: #475569` is a live production pair that's currently unparametrized):
   - `(dark, fg, nav_bg, 4.5)` + `(light, fg, nav_bg, 4.5)`
   - `(dark, fg_muted, nav_bg, 4.5)` + `(light, fg_muted, nav_bg, 4.5)` *(if text-on-nav exists; verify in Leg 01)*
   - `(dark, fg, sidebar_bg, 4.5)` + `(light, fg, sidebar_bg, 4.5)`
   - `(dark, fg_muted, sidebar_bg, 4.5)` + `(light, fg_muted, sidebar_bg, 4.5)` — **especially the light pair which is in production today and unparametrized**
   - If Leg 01 introduces a `--bg-gradient-peak` (or equivalent) lightest-stop token: `(dark, fg, bg_gradient_peak, 4.5)` + `(light, fg, bg_gradient_peak, 4.5)`
3. **`make rebuild`** — bake final state into running container.
4. **`make _ensure-playwright`** — re-install playwright deps (cache wiped by rebuild per Flights 1/2/3 pattern).
5. **`UPDATE_SNAPSHOTS=1 pytest -m pixel tests/browser/test_visual_snapshots.py`** — regenerate baselines (expected: 10/12; 2 carried-forward Flight 1 Known Issue).
6. **HAT walkthrough** — operator confirms shell reads correctly in light + dark themes across all 8 pages (Chat / Studio / Admin × 4 sub-routes / Design Language). Tactical fixes inline; structural issues logged.
7. **Codify in `agents.md`** — append Mission 08 Flight 3.5 Shell Chrome Polish subsection (after the Flight 3 F3 subsection, before `### Color contrast (WCAG AA)`). Document:
   - Any new shell-specific tokens introduced (e.g., `--shell-gleam` if extracted; `--bg-gradient-peak` if added for WCAG parametrization).
   - The shell-treatment composition rule (gradient + gleam + bezel-mini-edge for topbar/sidebar; `--bezel-shadow-inset` or pseudo-element technique for `#main-content`).
   - The dark-theme tier-hierarchy decision (if `--nav-bg`/`--sidebar-bg` got retuned).
   - **The "no `backdrop-filter` on viewport-edge chrome" decision** (per Architect — non-obvious choice future agents may second-guess): topbar + sidebar use static layered surfaces because nothing scrolls behind them to refract; the housing aesthetic needs texture, not transparency. Document as a composition rule.
   - **If body gradient ended up accent-bound** (operator chose `var(--accent-glow)` radial direction): document explicitly so future palette-swap missions know the body backdrop will drift with the accent.

   ALSO fold in the two carry-forward Flight 3 debrief Action Items #4 + #5: **topbar `<img>` CLS contract** (`flex-shrink: 0` + explicit dimensions for no first-paint CLS) → append as one bullet to the existing F3 affordance vocabulary; **legacy-class-as-JS-handle pattern** (the `.action-blocked-message` shape at `components.css:964-967`) → append as a short composition rule explaining when to retain a bespoke class as a JS-query handle vs delete it.
8. **Snapshot stability re-run** without `UPDATE_SNAPSHOTS=1` — confirm new baselines stable on re-run.
9. **Final narrow gate** — `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10`. Expected: 56/56.
10. **Status updates + commit** — Leg 02 → `completed`; Flight 3.5 → `landed`; Flight 3.5 checkbox ticked in `mission.md`.

**Narrow-test-gate fallback** (carried from prior flights): autonomous portions of both legs use the 4-module narrow gate. Broad pytest hangs on SQLite WAL anomaly; not attempted.

### Checkpoints

- [ ] **Leg 1 done**: All 4 shell surfaces (topbar / sidebar / body / main-content) carry the chosen design-language vocabulary in both themes; dark-theme tier hierarchy established; operator confirms the housing-around-interior metaphor reads.
- [ ] **Leg 2 done**: 10-step ordered close complete — WCAG green, snapshot baselines regenerated, operator HAT confirmed both themes × 8 pages, agents.md F3.5 subsection added including Flight 3 carry-forward docs items, narrow gate stable.

### Adaptation Criteria

**Divert if**:
- Dark-theme tier hierarchy cannot be established within 3 vibe iterations without WCAG regression — escalate; may require redesigning `--fg-muted` or other text-on-shell tokens.
- Light-theme shell treatments fight the existing `rail < sidebar < content` tonal hierarchy (e.g., glass overlay washes out the deliberate slate-900 navy rail) — escalate; either retune the texture or back off the layer.
- Body bg-gradient retune surfaces a downstream regression on any glass-consuming surface (e.g., `.entity-tile` glass reads wrong against the new gradient) — pause, decide whether to revert the gradient or retune the glass-tint.

**Acceptable variations**:
- Per-surface ordering within Leg 01 — body / topbar / sidebar / main-content can iterate in any order.
- Number of operator iterations per surface — vibe legs from prior flights ran 3-8 iterations per axis; this flight will be similar.
- Whether new tokens are introduced or existing tokens composed — operator/Developer call at Leg 01 implementation time.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `01-shell-chrome-vibe` *(vibe)* — Interactive. Apply design-language vocabulary to topbar / sidebar / body / main-content. Body bg-gradient retune in scope. Dark-theme tier hierarchy established. Operator drives aesthetic; Flight Director presents micro-iterations.
- [ ] `02-alignment-and-snapshot-regen` — 10-step ordered close: pre-close grep, WCAG audit, rebuild, playwright, snapshot regen, HAT × 2 themes × 8 pages, agents.md F3.5 subsection + Flight 3 carry-forward docs, stability rerun, final narrow gate, status update + commit.

---

## Post-Flight

### Completion Checklist

- [ ] All 2 legs completed
- [ ] All 4 shell surfaces (topbar / sidebar / body / main-content) carry on-brand treatments in both themes
- [ ] Dark-theme tier hierarchy established (rail / sidebar / content tonally differentiated)
- [ ] WCAG audit green (any new text-on-shell parametrizations added if shell retunes crossed audited pairs)
- [ ] Visual-snapshot baselines regenerated locally; 10/12 pass on rerun (modulo carried-forward Flight 1 Known Issue)
- [ ] `prefers-reduced-motion` and `prefers-reduced-transparency` posture verified — degrades to static / solid fallbacks
- [ ] `agents.md` Mission 08 Flight 3.5 Shell Chrome Polish subsection added; Flight 3 carry-forward items folded in
- [ ] HAT walkthrough complete in both themes × all 8 pages (Chat / Studio / Admin × 4 / Design Language)
- [ ] Code merged; flight status updated to `landed`
- [ ] Flight 3.5 checkbox ticked in `mission.md`

### Verification

- **Shell aesthetic check**: Load each of the 8 pages × 2 themes; the topbar, sidebar, and body bg read as a coherent "housing" framing the polished interiors. No surface feels like a flat backdrop.
- **WCAG check**: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` — all parametrizations pass; any new parametrizations added if shell retunes crossed audited pairs.
- **Snapshot stability check**: After regen in Leg 02, re-run `pytest -m pixel tests/browser/test_visual_snapshots.py` without `UPDATE_SNAPSHOTS=1`; passes cleanly (modulo 2 Flight 1 Known Issue blockers).
- **Reduced-preference check**: With `prefers-reduced-motion: reduce` and `prefers-reduced-transparency: reduce` simulated in DevTools (or via OS toggle), the shell degrades to solid / static fallbacks without losing structural visibility.
- **`agents.md` check**: Mission 08 Flight 3.5 Shell Chrome Polish subsection exists; topbar `<img>` CLS contract is documented (one bullet under affordance vocabulary); legacy-class-as-JS-handle pattern is documented (short composition rule).
- **No-regression check**: Narrow gate stable at 56/56; all M01-M07 capabilities continue working.
