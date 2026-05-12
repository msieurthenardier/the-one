# Flight Debrief: Shell Chrome Polish

**Date**: 2026-05-12
**Flight**: [Shell Chrome Polish](flight.md)
**Status**: landed
**Duration**: 2026-05-12 (single-day flight; ~30 vibe iterations in Leg 01 + autonomous close in Leg 02)
**Legs Completed**: 2 of 2

## Outcome Assessment

### Objectives Achieved

The flight delivered exactly its scope: the outer app-shell surfaces (body bg / `#app-topbar` / `#app-sidebar` / `#main-content`) now carry the design-language vocabulary that Flight 2's component-focused work and Flight 3's per-page focus both missed. Aesthetic landed: **alien-dashboard / Galaxy-from-GleepGlorp** — solid black main panel (white in light theme) with a chamfered violet L-bracket border, unified metallic-chrome housing on topbar + sidebar reading as one continuous L-shaped component, content fades to invisible at the top edge via `mask-image`. Two legs landed:

- **Leg 01 — Shell Chrome Vibe** (interactive, ~30 operator iterations). Built 5 panel-frame variants in the design-language gallery as iteration substrate (V1-V5), operator hybridized to V1b (nested-clip chamfered-with-accent-border technique), then graduated to actual application on `#main-content`. Body bg retuned to `var(--shell-chrome-bg)` so the chamfer corner reveals the housing continuing through. Unified metallic chrome with horizontal brushed grain + top-edge sheen on topbar (only). Top-edge content fade via `mask-image` (not overlay — the panel + content backgrounds are the same color in both themes, making any overlay-based fade invisible against itself). Light-theme port at leg close as a value-swap exercise. 6 new shell tokens defined; `color-scheme: dark/light` per theme block for UA chrome parity.
- **Leg 02 — Alignment + Snapshot Regen** (10-step ordered close — same template from Flight 2 Leg 06 + Flight 3 Leg 07). Pre-close grep clean; WCAG 45/45; rebuild + playwright + snapshot regen 10/12 (2 carried-forward Flight 1 Known Issue); HAT operator-confirmed both themes × 8 pages; agents.md Mission 08 F3.5 subsection added (~75 lines) including both Flight 3 carry-forward docs items.

### Mission Criteria Advanced

| Criterion | Status | Notes |
|---|---|---|
| Coherent visual identity across all areas, both themes | Met | Shell vocabulary closes Flight 2's underscoping; aesthetic now reads end-to-end |
| Visual identity has deliberate aesthetic direction documented in design-language gallery | Met | Alien-dashboard housing now part of the canonical vocabulary; agents.md F3.5 codifies the patterns |
| Color contrast meets WCAG AA | Met (with bounded gap) | Existing 45/45 audit passes; new `--shell-chrome-bg` base colors aren't parametrized — bounded latent risk (no text on chrome bg today; flagged for follow-up) |
| All M01-M07 capabilities continue working | Met | Narrow gate 56/56 stable across both legs |
| Visual-snapshot baselines regenerate cleanly | Mostly met | 10/12 baselines regenerated and stable on rerun; 2 carried-forward Flight 1 Known Issue (`chat_with_messages` × dark + light, deferred to Flight 5) |

## What Went Well

- **The "design-language gallery as iteration substrate" pattern continues to deliver.** Built 5 panel-frame variants (V1 octagonal, V2 diagonal cut, V3 bracket corners, V4 notched midpoints, V5 accent-glow top) as `.iter-panel-frame-*` gallery samples; operator picked V1 + asked for proper border on chamfered edges → built V1b (nested-clip technique) → graduated to `#main-content`. Scaffolding lived alongside the gallery for the rest of the leg as reference, ripped at close. Cleaner than direct-iteration on production surfaces.
- **`mask-image` for "content tucks under chrome"** is the correct technique on same-color content + bg. Operator hit this in iteration 7 when a `::after` black-overlay was invisible against the black panel bg. `mask-image` operates on the element's own pixels (removing them at the fade region) regardless of underlying paint — exactly the semantic needed. Reusable pattern, codified in agents.md F3.5 composition rule #3.
- **The V1b nested-clip technique for bordered chamfered shapes** — outer element accent-filled + clipped to pentagon, inner pseudo (z-index: -1) inset 1px on the L-bracket-bearing edges with matching clip, accent shows in the 1px gap — gives a true accent border on a clip-pathed shape without SVG or stacked gradients. Reusable; codified.
- **Theme generalization via token parameterization** continues to compound. Flight 3 established the pattern (theme-aware `--code-block-bg`/`-fg`); Flight 3.5 confirms it. Convention now: when a treatment differs only by value across themes, parametrize through tokens and drop the `[data-theme="..."]` selector prefix; selectors stay theme-agnostic. **Lift this to F2's design-language foundation subsection** so it's discoverable as a cross-flight convention.
- **"Land dark, port light" vibe cadence.** Dark theme matured fully first (the aesthetic anchor); light followed at leg close as a value-swap exercise (white panel + silver chrome + black grain). Parallel iteration would have added 2× decisions per micro-iteration during the operator-bandwidth-bottleneck phase. **Promote to flight-design template guidance** for vibe legs where the aesthetic translates symmetrically across themes.
- **10-step ordered close template** held up cleanly for the third time (Flight 2 Leg 06 → Flight 3 Leg 07 → Flight 3.5 Leg 02). Reusable asset; pattern is canonical.
- **Operator HAT caught `color-scheme` parity issue.** The light-theme scrollbar appearing dark on dark OS (and vice versa) was NOT anticipatable pre-flight — no flight-design phase would have surfaced UA chrome inheritance behavior. Only visible when operator actually inspected the rendered scrollbar. Clean argument for operator HAT in vibe legs; right loop caught it.
- **6 new shell tokens at clean granularity.** `--shell-chamfer` (geometry), `--shell-frame-fill` / `--shell-content-fill` / `--shell-frame-glow` (L-bracket triad), `--shell-chrome-bg` (housing surface), plus `--bg-gradient` rebinding. Naming parallels the F2 `--glass-*` / `--bezel-*` families. "Rule of two" honored (sheen overlay stayed as one-site literal, not extracted prematurely).
- **Closes both Flight 3 carry-forward docs items.** Topbar `<img>` CLS contract + legacy class-as-JS-handle pattern both codified in agents.md F3.5 affordance vocabulary.

## What Could Be Improved

### Process

- **Vibe-leg iteration order in flight design** should be framed as "axes to cover," not "sequence to execute." Two consecutive vibe legs (Flight 3 Leg 02, Flight 3.5 Leg 01) had their flight-design-stated iteration order superseded by operator priorities — body→topbar→sidebar→main-content was the spec; main-content FIRST was the actual. Both productive deviations; framing the order as suggested-not-prescribed would set the right expectation.

### Technical (in priority order)

- **(Important) Reduced-transparency posture is broken for the new shell tokens.** Flight 2's `@media (prefers-reduced-transparency: reduce)` block in `tokens.css` was designed for `--glass-*` tokens; it has no awareness of `--shell-chrome-bg` (rgba grain stripes), the topbar sheen (rgba), or the inner glow (rgba accent fade). A reduced-transparency user on the new shell gets grain + sheen + glow still rendering (browser preserves whatever opacity it deems "reduced"). **Action**: extend the F2 reduced-transparency block to also (a) override `--shell-chrome-bg` to its solid base color (no grain layer), (b) suppress the topbar sheen (likely via a `--shell-sheen` token = transparent under reduced-transparency, currently the gradient is inlined at the rule), (c) suppress the inner glow (likely via `--shell-frame-glow: transparent` under reduced-transparency). **Should land before Flight 4** — Studio Polish will compose on top of this aesthetic and the reduced-transparency posture should be coherent across the shell + chrome.

- **(Important) WCAG audit gap on `--shell-chrome-bg`.** The 6 new shell tokens introduced base colors (`#20202a` dark gunmetal / `#d4d8df` light silver) that aren't parametrized in `tests/test_design_tokens_a11y.py`. No text currently sits directly on these surfaces (topbar/sidebar host buttons + nav items with their own bg), so it's a **latent** risk, not live. But Flight 4 (Studio Polish) is plausibly the first place text-on-chrome could land (toolbars, breadcrumbs, etc.) and forgetting the audit at that point is a pixel-test-only catch. **Action**: 5-minute follow-up — add `(dark, fg, shell_chrome_bg, 4.5)` + `(light, fg, shell_chrome_bg, 4.5)` parametrizations now to close the gap before Flight 4 risks introducing the dependency.

- **(Minor) `--bg-gradient` token is now misnamed.** Repurposed from a vertical-fade gradient to a chrome-bg binding (so the chamfer cut reveals housing continuation). The name implies a gradient; the value is now a flat-color-or-layered binding. A future agent retuning "the body gradient" without context could break the housing illusion. **Action**: rename to `--shell-bg` or add a one-line alias / comment at the definition site documenting the semantic shift. Maintenance pass.

- **(Minor) `--shell-chrome-bg` is layered.** Future agents stripping the grain via cascade override would not realize the grain lives inside the token definition (not via a separate `--shell-grain` token). One-line comment at the token's definition site noting "to strip grain, edit token definition, not via cascade" prevents the search miss.

### Documentation

- **(Minor) Flight 3 carry-forward docs items live in F3.5 subsection, but semantically belong under F3.** The topbar `<img>` CLS contract describes the topbar shipped in Flight 3 Leg 02; the legacy-class-as-JS-handle pattern describes `.action-blocked-message` retained as a JS handle in Flight 3 Leg 03. Both are CORRECTLY labeled as carry-forwards in F3.5 but a future reader searching F3 won't find them. **Action**: add a one-line cross-reference under F3's affordance vocabulary pointing to F3.5 for these two contracts.

- **(Minor) "Body-bg = chrome-bg semantic continuation" rule** is in the flight log but not explicitly documented as a composition rule in agents.md F3.5. A future agent retuning body bg without grokking the chamfer reveal could break the housing illusion. The agents.md F3.5 composition rule #6 covers it but could be more pointed about the "do not retune `--bg-gradient` to a different color/gradient without confirming the chamfer-corner read is preserved" constraint.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Iteration order: spec body→topbar→sidebar→main-content; actual main-content FIRST (and dominant) | Operator "stay focused on the main panel right now" redirect at iteration 2 | Yes — frame vibe-leg ordering as "axes to cover" not "sequence to execute" |
| Topbar + sidebar received UNIFIED treatment (shared chrome bg) vs spec's per-surface assumption | Operator's "unified component" framing crystallized into shared token | Yes — when chrome surfaces share a visual treatment, prefer shared-token + per-element override for differences (sheen on topbar only) over per-element compositions |
| Light theme ported at leg close vs parallel iteration | Operator's "land dark, port light" cadence | Yes — promote as flight-design template guidance for vibe legs translating symmetrically across themes |
| Body bg-gradient repurposed from vertical fade to chrome bg | Chamfer corner reveal needed the chrome continuation | Per-flight judgment; document the semantic shift via token rename in a future maintenance pass |
| `mask-image` on `.content-panel` (not a `::after` black overlay) | Black overlay invisible against black panel bg | Yes — codified in F3.5 composition rule #3 |
| Sheen on topbar only (stacked outside the shared chrome token) | Avoids seam line at topbar/sidebar interface | Yes — codified in F3.5 composition rule #5 |
| `color-scheme: dark/light` per theme block | Operator HAT caught light scrollbar inheriting dark from OS | Yes — promote to F2 design-language-foundation as a "theme primitive" |
| 5 panel-frame variants built as gallery scaffolding then ripped | Gallery-as-iteration-substrate pattern from Flights 2 + 3 | Yes — promote pattern to flight-design template as "build vibe variants as `.iter-*` gallery samples; rip at close" |

## Key Learnings

- **Vibe-leg iteration order should be flexible, not prescribed.** Two consecutive vibe legs had operator-driven reordering. Future flight designs should mark vibe-leg orderings as suggested-not-prescribed.
- **"Land dark, port light" is the right vibe cadence** when the aesthetic translates symmetrically across themes. Avoids the 2× decision load during operator-bandwidth bottleneck.
- **Theme generalization via tokenization is now a flight convention.** When a treatment differs only by value across themes, parametrize through tokens and drop `[data-theme="..."]` selector prefix.
- **`mask-image` is the correct technique for "content tucks under chrome" on same-color panels.** Overlay-based fades are invisible against themselves; mask-image operates on the element's pixels directly.
- **Nested-clip is the correct technique for bordered chamfered shapes** when SVG or stacked gradients would be overkill. Outer accent + inner inset pseudo with matching clip-path = true accent border on a clip-pathed shape.
- **Body-bg = chrome-bg semantic coupling** is a load-bearing aesthetic choice (chamfer reveal). Document the coupling explicitly; future retunes of either should check the corner read.
- **HAT-discovery items (like `color-scheme`)** continue to surface things flight design can't anticipate. Operator HAT in vibe legs is irreplaceable for UA-chrome / native-widget-level issues.

## Test Metrics Capture

| Suite | Flight 1 | Flight 2 | Flight 3 | Flight 3.5 | Delta vs F3 |
|---|---|---|---|---|---|
| Narrow gate (4 modules) | 56 in 0.95s | 56 in 0.90s | 56 in 0.82s | 56 in 0.88s | +0.06s (within noise) |
| WCAG audit | 45 in 0.06s | 45 in 0.06s | 45 in 0.05s | 45 in 0.05s | Unchanged |
| Pixel suite | 10p/2f in 25.06s | 10p/2f in 25.36s | 10p/2f in 25.67s | 10p/2f in 24.42s | Stable; same 2 Flight 1 Known Issue failures |
| New flakes | — | — | None | None | — |
| Broad pytest | Hung (SQLite WAL) | Not attempted | Not attempted | Not attempted | Anomaly unchanged |

- **No new audit parametrizations added** in this flight (correctly — none of the existing audited pairs changed). The 2 candidate parametrizations (`fg` on `--shell-chrome-bg` per theme) are deferred as the recommended 5-minute follow-up.
- **Pixel suite timing slightly faster** (25.67s → 24.42s) — likely cache warmth; no signal.

## Recommendations (top 5)

1. **(Important) Extend reduced-transparency `@media` block** in `tokens.css` to cover the new shell tokens — override `--shell-chrome-bg` to solid base, suppress topbar sheen, suppress inner glow. **Should land before Flight 4** so Studio Polish composes on a coherent reduced-transparency posture.

2. **(Important) Close WCAG audit gap on `--shell-chrome-bg`** — 5-minute follow-up to add `(dark/light, fg, shell_chrome_bg, 4.5)` parametrizations now, before Flight 4 risks introducing text-on-chrome dependency.

3. **(Methodology) Promote two patterns** to flight-design template / agents.md cross-flight guidance:
   - **"Land dark, port light"** vibe cadence for symmetric aesthetic translation
   - **Theme generalization via tokenization** (drop `[data-theme="..."]` prefix once values parametrize through tokens)

4. **(Methodology) Flight 4 (Studio Polish) scope review at design time** — shell housing inherited from F3.5 means per-page polish operates on `.content-panel` interior only. Likely shaves 1 leg off Flight 4's vibe scope. Studio's `confirmLeave` parity work (carrying Flight 3 Action Item #1 forward) should remain its own leg.

5. **(Minor) Documentation polish**: cross-reference Flight 3 carry-forward docs items from F3 → F3.5 (so F3 searchers find them); rename or comment `--bg-gradient` to reflect its semantic shift to chrome binding.

## Action Items

- [ ] **Extend reduced-transparency `@media` block** in `tokens.css` to override `--shell-chrome-bg`, sheen, and inner-glow for prefers-reduced-transparency users. **Before Flight 4 design.**
- [ ] **Close WCAG audit gap** — add `(dark, fg, shell_chrome_bg, 4.5)` + `(light, fg, shell_chrome_bg, 4.5)` parametrizations in `tests/test_design_tokens_a11y.py` + Python mirror. **5-minute follow-up; do before merging Flight 3.5 if quick, else maintenance pass.**
- [ ] **Lift "theme generalization via tokenization" convention** from F3.5 prose to F2 design-language-foundation subsection in agents.md as a canonical composition rule.
- [ ] **Lift "land dark, port light" cadence** to flight-design template guidance for vibe legs translating symmetrically across themes.
- [ ] **Cross-reference Flight 3 carry-forward docs items** under F3 affordance vocabulary section pointing to F3.5 placement (so F3-searchers find them).
- [ ] **Rename or alias `--bg-gradient`** to reflect chrome-bg binding semantic (e.g., `--shell-bg` with `--bg-gradient` as deprecated alias). Maintenance pass.
- [ ] **Comment on `--shell-chrome-bg` token definition** noting "to strip grain, edit token definition, not via cascade" so future agents don't search-miss.
- [ ] **Flight 4 design phase**: explicitly note "shell housing inherited from F3.5; per-page polish operates on `.content-panel` interior only" in mission/flight criteria.
- [ ] **Carried forward from Flight 3 Action Item #1**: Playwright B2 regression test → Flight 4 (Studio Polish will gain `confirmLeave` parity; test added once for both areas).
- [ ] **Carried forward from Flight 1 + Flight 2**: `app_with_agent` fixture `.session-agent-badge` race blocking 2/12 pixel snapshots — Flight 5 (Chat Response Trace) territory.
- [ ] **Carried forward from Flight 2**: native `<select>` popup chrome design-language gap — custom dropdown component for Flight 4 (Studio Polish has more dropdown consumers).
