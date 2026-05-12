# Flight Log: Shell Chrome Polish

**Flight**: [Shell Chrome Polish](flight.md)

## Summary

Flight log for Flight 3.5 of Mission 08 (GleepGlorp Rebrand). Flight design completed on 2026-05-12; awaiting kickoff via `/agentic-workflow flight 3.5 for the-one mission 08`.

---

## Reconnaissance Report

Source artifact: Flight 3 debrief (`missions/08-gleepglorp-rebrand/flights/03-administration-polish/flight-debrief.md`). The "Forward-Looking — Mission 08 Shell Chrome Polish (Flight 3.5)" section + Action Items #4 + #5 cite the shell surfaces and codification items.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `#app-topbar` strip background is flat `var(--nav-bg)` + 1px border | confirmed-live | `base.css:13-15` sets `background: var(--nav-bg)`. `tokens.css:164` dark theme `--nav-bg: var(--bg)` (uniform black); `tokens.css:309` light theme `--nav-bg: #0f172a` (dark navy chrome). No glass / bezel / gradient overlay. | Retreat in Leg 01 vibe — apply gradient + gleam + bezel-mini bottom edge. |
| `#app-sidebar` rail background is flat `var(--sidebar-bg)` + 1px border | confirmed-live | `base.css:34-36` sets `background: var(--sidebar-bg)`. `tokens.css:174` dark `--sidebar-bg: var(--bg)` (uniform black); `tokens.css:319` light `--sidebar-bg: #cbd5e1` (slate-300). No glass / bezel / gradient overlay. | Retreat in Leg 01 vibe — apply gradient + gleam + bezel-mini right edge. |
| `#main-content` frame surface inherits body bg-gradient | confirmed-live | `base.css:51` `#main-content { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }` — no background of its own; the bg-gradient on `body` reads through. | Retreat in Leg 01 vibe — add `box-shadow: var(--bezel-shadow-inset)` (or variant) so the content area reads as "inside" the housing. |
| `body` `bg-gradient` is a 2-stop linear vertical fade | confirmed-live | `tokens.css:155` dark `--bg-gradient: linear-gradient(180deg, #0e1428 0%, #050505 70%)` (navy-to-black); `tokens.css:297` light `--bg-gradient: linear-gradient(180deg, #fafbfc 0%, #f1f5f9 100%)` (pale slate fade). Both functional but minimally thematic. | Retreat in Leg 01 vibe — candidate for retune (radial accent glow, third stop, or other direction). Operator drives. |
| Codify topbar `<img>` CLS contract in agents.md (Flight 3 debrief Action Item #4) | confirmed-live | `agents.md` F3 subsection (lines ~621-) covers shared primitives + hooks but does NOT include the "topbar banner image requires explicit height + `flex-shrink: 0` for no first-paint CLS" rule. | Fold into Leg 02 step 7 (agents.md F3.5 subsection adds this as one bullet to existing F3 affordance vocabulary). |
| Codify legacy-class-as-JS-handle pattern in agents.md (Flight 3 debrief Action Item #5) | confirmed-live | Pattern exists at `components.css:964-967` (the `.action-blocked-message` comment documenting the decision) but no canonical guidance in agents.md. | Fold into Leg 02 step 7 (agents.md F3.5 subsection adds this as a short composition rule). |
| Playwright regression test for B2 cross-area dirty-gate (Flight 3 debrief Action Item #1) | **deferred to Flight 4** | Flight 3 fix is in place at `app.js switchTo()` (cross-area branch via `confirmLeave` hook) + `admin.js _confirmLeaveImpl`. Test would cover admin only. | Defer per Design Decisions — Flight 4 (Studio Polish) will implement `confirmLeave` on the studio area descriptor for parity; the test can be added once for both areas in one pass. Tracked in Flight 4. |

All non-deferred items remain in Flight 3.5 scope. No items retired silently.

---

## Leg Progress

### 01-shell-chrome-vibe

**Status**: landed (2026-05-12) — operator visual-confirmed across an extended iteration

**Aesthetic direction landed**: alien-dashboard / Galaxy-from-GleepGlorp. Solid black main panel with a chamfered violet L-bracket border (top + left only), unified metallic-chrome housing (topbar + sidebar) with brushed horizontal grain + top-edge sheen, content fades to invisible at the top edge via mask-image.

**New tokens** (theme-aware, in `tokens.css`):

| Token | Dark | Light |
|---|---|---|
| `--shell-chamfer` | 14px | 14px |
| `--shell-frame-fill` | `var(--accent)` (violet-400) | `var(--accent)` (violet-700) |
| `--shell-content-fill` | `#000` | `#fff` |
| `--shell-frame-glow` | `var(--accent-glow)` | `var(--accent-glow)` |
| `--shell-chrome-bg` | gunmetal `#20202a` + white grain stripes | silver `#d4d8df` + black grain stripes |
| `--bg-gradient` | `var(--shell-chrome-bg)` | `var(--shell-chrome-bg)` |

`color-scheme: dark/light` set per theme block so browser UA chrome (scrollbars, native form widgets) follows the active theme rather than OS default.

**Treatments applied**:

- **Body**: bg-gradient retuned from a pale/dark fade to `var(--shell-chrome-bg)`. Body is only visible through main-content's chamfer cut; making it the chrome bg lets the corner read as the housing continuing through the panel cut.
- **`#main-content`**: V1b technique — outer accent-filled element + inner pseudo-element (z-index: -1) inset 1px on top + left only, both clipped to a top-left-chamfer pentagon. Result: L-bracket accent border on top + left + chamfered diagonal corner. Inner pseudo also paints a directional inner glow (accent-glow fading 20px from top + left edges) layered over the solid content-fill. Margin removed so the frame sits flush against the chrome.
- **Top-edge fade mask**: `mask-image: linear-gradient(180deg, transparent 0px, black 8px)` on `.content-panel` (both themes) so scrolled content fades to invisible at the top — appears to tuck UNDER the L-bracket border. Required `mask-image` (not a black overlay) because the panel bg is the same color as the content bg in both themes; an overlay-based fade is invisible against itself.
- **`#app-topbar`**: shared `--shell-chrome-bg` + `linear-gradient(180deg, rgba(255,255,255,0.06), transparent 6px)` top-edge sheen ("lit from above"). The sheen is stacked separately (NOT in the token) so the sidebar doesn't also paint a sheen at its top — that would create a visible seam at the topbar/sidebar interface. Removed `border-bottom: 1px solid var(--nav-border)`.
- **`#app-sidebar`**: shared `--shell-chrome-bg` (no sheen). Removed `border-right: 1px solid var(--border)`. Added `padding-top: 10px` so the section-nav menu aligns properly with the new chrome treatment.
- **`.section-nav`**: removed `border-bottom: 1px solid var(--border)` — paints a visible line on the unified chrome bg.
- **Incidental**: removed dead `position: relative; /* for absolute popover positioning */` from `#app-topbar` (popover affordance retired in Flight 3 Leg 02).

**Operator-driven aesthetic decisions** (iteration trail):

1. Body bg: tried 4-option menu (linear, radial-accent-glow, three-stop, noise) → operator chose solid black instead, citing "phone screen with subtle reflections" / "alien dashboard of Galaxy" reference.
2. Main panel: tried 5 panel-frame variants in the design-language gallery (V1 octagonal, V2 diagonal cut, V3 bracket corners, V4 notched midpoints, V5 accent-glow top). Operator picked V1 + asked for proper border on all chamfered edges → built V1b (nested-clip technique). Also asked to drop glow option, switch background to solid black on gallery + body.
3. Refined V1b: 1.5px border → 1px border; body fill grey → `#000`; chamfer 8px → 14px (operator's "increase a little bit").
4. L-bracket pivot: dropped right + bottom borders → top + left only (asymmetric L-bracket). Chamfer only at top-left corner.
5. Margin: added 3px around main-content for inset (operator request "needs a margin on all sides"), then removed entirely (operator: "we had added some padding around the border, which now just leaves a gap, lets close that up") once the metallic chrome surrounded it.
6. Inner glow: added directional accent-glow gradient (32px fade), reduced to 20px (operator: "reduce the inner glow a bit").
7. Top-edge content fade: first tried `::after` black-overlay (didn't work — black on black is invisible) → switched to `mask-image` on `.content-panel` (operator-confirmed).
8. Chrome metallic: started flat gunmetal + sheen, added brushed grain (tried 45° diagonal, then 90° = vertical stripes, then 180° = horizontal stripes which was the operator's "horizontal" pick).
9. Seam removal: removed border-bottom on topbar + border-right on sidebar so the unified L reads as one component. Then fixed the line at the topbar/sidebar interface caused by the sheen layer painting on sidebar's top edge → split the sheen out of the shared `--shell-chrome-bg` token so only topbar adds it.
10. Chamfer corner: was showing black through main-content's chamfer cut → switched body bg to chrome so the corner reveals the metallic housing continuing.
11. Section-nav border: removed (it painted a visible line on the unified chrome).
12. Light-theme port: white main panel + silver chrome (operator: "nearly identical for light mode except that the main panel is white instead of black"). Generalized the dark-theme-only selectors to apply per theme via tokens.
13. Scrollbars: were inheriting OS theme regardless of app theme → set `color-scheme: dark/light` per theme block.
14. Sidebar top alignment: added 10px padding-top to align section-nav with the new chrome treatment.

**Cleanups at leg close**:

- All `.iter-panel-frame-*` gallery scaffolding ripped from `surfaces-section.js` + `admin.css` (V1, V1b, V3, V3b — were temporary iteration variants).
- `#app-topbar` dead `position: relative; /* for absolute popover positioning */` removed.

**Verification**:

- Narrow test gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30` → **56/56 in 0.82s**.
- `make rebuild` → all assets served correctly.
- Operator visual confirmation across ~30 iterations covering both themes.

**Anomalies**: None.

**Deviations from leg artifact**:

- Original leg artifact suggested iteration order: body → topbar → sidebar → main-content → cross-axis. Actual order was driven by operator's "stay focused on the main panel right now" early redirect, so main-content was iterated FIRST (most of the leg) before moving to topbar/sidebar treatments. Topbar + sidebar received unified treatment via the same `--shell-chrome-bg` token — closer to "single chrome surface" than the leg artifact's per-surface assumption.
- Light-theme port happened at leg close (operator requested) rather than being parallel work — the dark theme matured fully first, then a one-shot port to light with appropriate value swaps.
- Body bg-gradient retune wasn't just stylistic — it became load-bearing for the chamfer corner aesthetic (chamfer cut on main-content reveals body bg; body needs to read as chrome-continuation, not black hole).

**Methodology lessons**:

- **The "design-language gallery as iteration substrate" pattern from Flight 2 / Flight 3 works for shell treatments too.** Built 5 variants in the gallery (V1-V5), operator picked + hybridized (V1b), then graduated to actual application on `#main-content`. Gallery scaffolding lived alongside the gallery for the rest of the leg as reference, then ripped at close. Cleaner than direct-iteration on production surfaces.
- **`mask-image` is the correct technique for "tucking content under a border" on same-color content + bg.** A black overlay fades invisibly when both sides are black. mask-image affects element pixel visibility itself.
- **Token-driven theme aesthetics + theme-aware selectors generalize cleanly.** The dark-only selectors converted to all-themes by parameterizing through tokens — the rules' structure didn't need to change; only the token values differed per theme.

---

## Decisions

### Reconnaissance carry-forward classification

**Context**: Flight 3 debrief surfaced 4 shell-surface gaps + 2 docs codification items + 1 Playwright regression test as forward-looking work for Flight 3.5.
**Decision**:
- 4 shell-surface gaps + 2 docs items → in scope for this flight (Leg 01 vibe + Leg 02 step 7 respectively).
- Playwright B2 regression test → deferred to Flight 4 (Studio Polish will gain `confirmLeave` parity; test can be added once for both areas).
**Impact**: Flight 3.5 stays small (2 legs); Flight 4 absorbs the cross-area test work alongside its own Studio dirty-gate implementation.

### Design-review (Architect) feedback incorporated

**Context**: Phase 5b Architect review returned `approve with changes` with 2 medium + 2 low issues + 3 suggestions + 3 questions.
**Decision**: All 4 issues (medium + low) addressed in the flight artifact before Phase 6 closure. Specifically:
- **WCAG audit gap on `--nav-bg`/`--sidebar-bg`** (medium): Leg 02 step 2 now requires 6 new parametrizations regardless of vibe outcome — the existing `--sidebar-bg: #cbd5e1` × `--fg-muted` light-theme pair is currently unparametrized but in production. Audit must add this row at minimum.
- **Body gradient mid-point contrast** (medium): Design Decisions gates the gradient retune — if the lightest stop differs >5% lightness from `--bg`, extract a `--bg-gradient-peak` token and add a WCAG parametrization.
- **Topbar `position: relative` is dead** (low): incidental cleanup added to Leg 01 implementation guidance.
- **Defer-to-Flight-4 guard** (low): Design Decisions augmented with a Flight-4-entry-condition note so the Playwright test doesn't slip a second time.

3 suggestions applied:
- "Rule of two" token-extraction threshold codified in Leg 01 guidance.
- `#main-content` `overflow: hidden` interaction with `bezel-shadow-inset` flagged as an implementation caveat — recommended pseudo-element approach.
- Reduced-transparency dark-theme tier-collapse check added to Leg 01 (verify the tier reads under reduced-transparency emulation; if gleam is sole differentiator, retune tonal step instead).

3 questions resolved:
- `agents.md` F3.5 step (Leg 02 #7) now explicitly documents the "no `backdrop-filter` on viewport-edge chrome" decision rationale.
- Design Decisions augmented with body-gradient accent-binding caveat: prefer accent-independent retune; explicit log entry if operator chooses accent-bound direction.
- Leg 01 in-leg escape-hatch checkpoint added after surface 2 (operator may split into Leg 01b if vibe iterations exceed bandwidth).

Also captured a pre-Leg-01 sentinel from the Architect's grep verification: `grep -n "var(--nav-bg)\|var(--sidebar-bg)"` outside base.css returns zero hits — shell-tier retunes have no surprise consumers.

**Impact**: Flight 3.5 enters Phase 6 (Iterate) with a codebase-validated spec + concrete WCAG parametrization requirements. No re-review cycle needed — fixes were targeted enough that another Architect pass would be redundant.

---

## Deviations

*Populated during execution.*

---

## Anomalies

*Populated during execution.*

---

## Session Notes

*Populated during execution.*

---

## Flight Director Notes

### Flight design (2026-05-12)

- Loaded flight-design phase file from `/home/cprch/projects/the-one/.flightops/agent-crews/flight-design.md` (project file present).
- Reconnaissance verified 4 cited shell surfaces + 2 docs items; all `confirmed-live` and citations clean. Playwright test classified as `deferred to Flight 4` (not silently dropped — recorded as a Design Decision with rationale).
- Flight scoped as 2 legs (operator hinted size: 2-3): 1 interactive vibe leg covering all 4 surfaces + body retune + dark-theme tier-hierarchy establishment, 1 closing alignment leg with 10-step ordered close + agents.md F3.5 subsection codifying any new shell-treatment patterns + the 2 carry-forward Flight 3 debrief docs items.
- All Open Questions resolved with working assumptions documented inline; concrete shell-treatment values deferred to in-leg vibe resolution per the established operator-pattern.
- Two design choices worth noting: (a) topbar + sidebar do NOT use `backdrop-filter` (nothing scrolls behind viewport-edge chrome to refract — the housing aesthetic doesn't need transparency, it needs texture); (b) light theme retunes texture ON TOP of existing tonal hierarchy (`#0f172a` rail / `#cbd5e1` sidebar / pale body) rather than re-tiering the colors (Flight 1 palette decisions preserved).
