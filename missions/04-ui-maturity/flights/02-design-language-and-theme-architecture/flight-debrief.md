# Flight Debrief: Design Language & Theme Architecture

**Date**: 2026-04-26
**Flight**: [Design Language & Theme Architecture](flight.md)
**Status**: landed
**Duration**: 2026-04-25 → 2026-04-26 (~1.5 days, single agentic-workflow session including HAT)
**Legs Completed**: 9 of 9 (all landed and committed in single bundled commit `bb43674`, mission-tracker check-off `d2a40f8`)

## Outcome Assessment

### Objectives Achieved

The flight delivered against all stated objectives:

- **Coherent visual identity established** — NEXUS-style cyan-glow design language with section-marker (`// PREFIX`) typographic convention applied across Chat / Studio / Admin. ✓
- **WCAG AA on text and interactive elements (both themes)** — 40-pair parametrized contrast test (`tests/test_design_tokens_a11y.py`); 4 token retunes during leg 07 to clear strict body AA; 2 documented `--fg-faint` deliberate exceptions pinned with band assertions. ✓
- **Theme architecture, swappable without code changes** — token-based design system (`tokens.css`, ~50 tokens × 2 themes); user-facing toggle added at HAT (Admin → System → Appearance) wired to existing `App.theme.{get, resolved, set}` API. ✓
- **Tri-state Light/Dark/Auto switching** — `prefers-color-scheme` matchMedia subscription + localStorage persistence (`theme-preference`) + canonical-default-to-dark when no OS preference; theme switches without reload. ✓
- **Geist Sans + Geist Mono self-hosted** — pinned to `vercel/geist-font@1.8.0`, ~141KB total, `font-display: swap`, no FOUC after script reorder. ✓
- **Lucide SVG icon system** — 20 icons bundled inline as a single JS module (`icons.js`), pinned to `lucide-icons/lucide@v0.265.0`, ~7KB. All decorative; `aria-hidden="true" focusable="false"` baked in (post-review). ✓
- **Visual snapshot regression net** — 12 baselines (3 areas × 2 states × 2 themes) via custom PIL+pixelmatch helper because Python Playwright lacks `to_have_screenshot`. Stable across 3+ runs. ✓
- **Design system documentation** — `agents.md` "Design system" section: token reference, contrast pair tables for both themes, typography scale, icon catalog, theme switching contract; CLAUDE.md updated with Geist + theme switcher pointer. ✓
- **Interactive HAT** — Flight Director walked the user through 25 verification steps; 6+ inline retunes applied; explicit user approval to close. ✓

### Mission Criteria Advanced

This flight contributes to four of the nine M04 success criteria:

- ✓ **"The interface presents a coherent visual identity"** — typography, spacing, color, and interaction patterns consistent across all areas.
- ✓ **"The color system meets accessibility contrast standards (WCAG AA)"** — 40-pair test suite passing; both themes compliant.
- ✓ **"Visual themes are swappable without code changes"** — token retune is the canonical change vehicle; HAT validated this 6 times.
- ✓ **"Each functional area reflects the established design language..."** — F2 establishes the language; F4-F6 polish per-area UX.

## What Went Well

### CSS @layer cascade architecture eliminated specificity wars
Zero "fight the cascade" rework across 9 legs. `index.html:7` declares `@layer tokens, base, components, areas, utilities;` once; all 7 component files self-tag their layer. Leg 01's round-1 review caught the subtle precedence trap (tokens.css inactive until styles.css's unlayered `:root` is wrapped) — the kind of layer-ordering bug that would have cost a day at implementation time without design review. Architecture also held when HAT introduced 7 new tokens and a brand-new component (theme toggle) with no layer adjustments needed.

### Light theme as designed coherent variant — strongest validation of the token architecture
Leg 06 produced a Linear/Stripe-light quality variant with **zero component-CSS overrides**. The same `var(--panel-shadow-glow)` resolves to cyan glow in dark and to composite cyan-tinted drop-shadow in light at `tokens.css:81` and `:169` — same affordance vocabulary, different visual register. Validates the up-front decision (made per user request) to design the light theme as its own leg, not a flip.

### Apply-tokens-before-visual-change separation paid off
Leg 02 had zero visual delta but surfaced 4 design-review catalog mismaps (`#fff` mistakenly mapped to `--fg-on-danger` when it was actually toggle-thumb-on-accent; `#333` missed entirely; line 354 wrongly catalogued; lines 261/300/347 missing). The refactor-before-redesign separation made these failures cheap and isolated. Verifies the F2 design principle: "set up tokens" → "use tokens" → "change visuals."

### Mock-provider-as-production-code (F1) carried the snapshot suite without modification
F1's `app_with_provider` / `app_with_agent` fixtures powered the 12 visual snapshot tests with zero F2-side fixture changes. Confirms the F1 architectural call (mock provider as production code, dev-mode-gated) was right-sized for cross-flight reuse.

### Bundled-commit-at-flight-end held cleanly across nine legs
50 files, +6326/-400 LOC committed atomically. Reviewer (Haiku) + Accessibility Reviewer (Sonnet) ran in parallel at flight-level review — A11y Reviewer correctly identified 3 BLOCKING WCAG 2.1.1 keyboard items as pre-existing structural debt, escalated to Flight Director judgment for scoping. No per-leg commit churn.

### HAT as conversational pacing produced changes no autonomous run could
The 6 HAT retunes (banner restyle, `--fg-muted` dark from `#555` to `#a8a8a8`, `--status-danger-muted` invented, theme toggle UI, nav-rail layering, bolder section headers) happened token-by-token with the user steering ("little more" → bumped further). An autonomous Developer agent would have shipped one of these and stopped; the conversational form let all six land in one session. Validates HAT as a non-substitutable execution mode.

### Design-review process continued to catch real issues before implementation
The 9-leg review pattern surfaced specific high-severity gaps before any code was written: leg 01's 3 highs (`Object.assign` clobbering, Playwright `color_scheme="light"` default, inactive-tokens.css cascade), leg 02's 4 catalog mismaps across 2 rounds, leg 04's Geist-URL discovery procedure, leg 05's stale Lucide release tag. The investment in design-review-heavy methodology continued to pay off.

## What Could Be Improved

### Process

- **Convergence work over-budgeted in spec, under-budgeted in HAT.** The flight spec called for "small set of visual experiments to converge on a design direction" but the user converged in conversation pre-flight with 3 reference screenshots — leg 03 produced shippable visuals on first pass. Conversely, the HAT introduced 6+ retunes and a brand-new theme toggle UI not in any leg spec. The implicit assumption "post-HAT changes will be small" was off by ~6×. Worth recognizing as a flight-design pattern: when reference convergence happens pre-flight, expect HAT to absorb the iteration the experiments leg would have done.

- **Refactor legs that touch every CSS file warrant 2 review rounds even when "mechanical."** Leg 02 (`apply-tokens`) carried disproportionate review weight (2 design-review rounds, 4 high-severity catalog mismaps surfaced) because it was the largest mechanical translation. The implementer's grep gate was effectively the third reviewer. Update flight-design heuristic: any leg touching N≥6 files with mechanical-translation work gets 2 review rounds budgeted, not 1.

- **A11y mandate scoping needs explicit tiers.** F2's leg 07 was scoped to contrast / ARIA / focus on already-focusable elements (~1 leg of work). The flight-level a11y reviewer correctly surfaced 3 BLOCKING WCAG 2.1.1 keyboard-operability failures (nav rail / list items / inline deletes as `<div>`/`<span>` with click-only handlers) — but those are flight-sized rebuilds, not leg-sized fixes. The flight design template should require the planner to pick a tier: **scoped a11y** (contrast / ARIA / focus on focusable elements — leg-sized) vs **structural a11y** (keyboard operability rebuild, semantic landmarks, skip-links — flight-sized) — and call it out so a11y reviewers can scope findings the same way.

- **Post-review fixes pattern worked here but should ideally happen earlier in flights with more visual rework.** F2's review-then-fix cycle was small enough to bundle (4 a11y improvements + 1 token retune). For larger flights with more visible review-fix iteration, snapshot regen churn could compound. Consider an intermediate review checkpoint after the design-language-establishing leg (analog of F2's leg 03) — that leg is most likely to need rework, and reviewing earlier saves mid-flight retunes.

- **Hover-revealed delete buttons became MORE prominent at HAT, making the keyboard-can't-reach-them gap MORE glaring.** The muted-red default is a perceived-consistency regression: we made the affordance language louder while leaving the structural keyboard gap intact. Captured in the keyboard-operability known issue, but the flight log should note that visual-prominence changes can amplify pre-existing a11y debt.

### Technical

- **`--fg-muted` (dark) is missing from the a11y test parametrize set.** Original value `#555` was below WCAG AA but went uncaught because `--fg-muted` was used in non-body contexts at the time of leg 07's audit. HAT exposed the gap when studio editor subtext read as too dark. The retune to `#a8a8a8` was a pure aesthetic fix; the test set still doesn't pin dark `fg_muted` against `bg`/`surface` at body-AA. **A future retune that breaks it will not fail loudly.** Add `("dark", "fg_muted", "bg")` and `("dark", "fg_muted", "surface")` to `test_design_tokens_a11y.py:79-97` parametrize at the body 4.5:1 threshold.

- **`--sidebar-bg: transparent` (dark) is brittle as a value semantically.** It encodes "show body gradient through" as the implementation but not as the intent. If a future flight adds backdrop-blur or compositing under `#app-sidebar`, transparent will silently produce different visual results. Replace with declarative (`var(--bg)` if "match body" is the intent) or explicit (`background: none; backdrop-filter: none;` to make absence intentional and future-proof).

- **`admin.js` is 1248 LOC and growing.** Theme toggle (~70 LOC) was added at HAT into a single file already owning provider CRUD, encryption rotation, and pull/test flows. Splitting into `js/components/theme-toggle.js` (or moving to `theme.js` as `App.theme.renderToggle(container)`) would let any area mount the control — needed for F3's potential top-bar quick-toggle.

- **`// SECTION` `::before` pattern is duplicated 5× across studio/admin** (`studio.css:31`, `admin.css:24, 121, 133`) with slightly different opacity/weight (HAT bumped some away from 0.6; others retain it). Lift to a shared utility class `.section-marker` in `components.css` or expose the prefix as a CSS custom-property. Pick one idiom for the literal `// SETUP` string in `chat.css:48` vs the `::before` mechanism — currently competing.

- **Two competing idioms for the "// PREFIX" text marker** — `chat.css:48` uses literal `"// SETUP"` text in the `::before`; section headings use `"//"` followed by a separate text node. Consolidate.

- **Visual snapshot baselines are 572KB now; F4-F6 will compound.** Each new state × 2 themes ≈ 80-100KB. F3 might add ~3 states (top-bar variants, command palette, drawer-open) → ~600KB more; F4-F6 might add ~10 states → ~1.5-2MB total. At ~2MB consider Git LFS. Mitigation: viewport is fixed at 1280×800; future leg-level snapshots could capture sub-regions instead of full viewport.

- **Visual snapshots regenerate on token retunes by design.** A future flight that retunes a single token (e.g., the theme generator) invalidates all 12 baselines. Worth exploring a layout-not-color separation where snapshots capture DOM structure / computed dimensions / font metrics without color, so color regression is covered by the contrast test suite alone.

- **Lucide `gh api .../releases/latest` returns the stale pre-rename `1.x` tag.** Implementer caught this empirically in leg 05 and pinned `v0.265.0`. Class of "external repo quirk" worth recording in `agents.md` so future legs adding icons don't re-discover it.

- **Playwright `color_scheme="no-preference"` reports `lightMedia.matches=true` in this Chromium build** (Chromium 132 / Playwright 1.58). Leg 02 flight-log entry documents this. Worth recording as a Playwright-Python-specific gotcha in `agents.md` browser-testing section so future tests asserting on theme-resolution behavior aren't surprised.

### Documentation

- **No "how do I add a new token" guide.** `agents.md` design-system section reads as a reference catalog (token tables, contrast pairs) but doesn't tell a future-leg implementer the canonical workflow: define in `tokens.css` (dark + light) → add to `tests/browser/design_tokens.py` if test-relevant → add contrast tests if interactive/text → run grep gate → update `agents.md` table. Add a "Token lifecycle" subsection.

- **No "how do I add a new icon" guide.** `agents.md` has the icon catalog but doesn't tell future legs the procedure for adding to `icons.js` (fetch from Lucide at pinned tag, inline as one-liner with `aria-hidden="true" focusable="false"`, document in catalog). Mechanical but currently tribal knowledge from leg 05.

- **Snapshot regeneration procedure documented but the workflow ("which scenarios force regeneration vs which are likely actual regressions") is not.** Worth a note: pure-CSS retunes → expect regen; `data-testid` removal → never regen.

- **Design-language affordance vocabulary is implicit, not codified.** F2 established 5 distinct color/treatment patterns: *outlined-cyan affordance* (create/edit), *filled-cyan + glow CTA* (primary actions), *muted-default + glow-on-hover destructive* (delete), *neutral utility button* (read/refresh/cancel), and the *cyan-vs-neutral-vs-red color disambiguation rule* itself. Plus the *info banner* pattern (cyan left-border + horizontal accent-translucent gradient + inset cyan glow + `// PREFIX` mono eyebrow). These are load-bearing design rules that F4-F6 must follow; today they live in scattered CSS, not in `agents.md`.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Schema migration v6 missed in initial leg 02 audit (CHECK constraint) | State-Machine Reachability Audit listed 5 layers but missed SQLite CHECK at `db/schema.py:18,129`; first test run failed `IntegrityError: CHECK constraint failed` | No (the migration follows v3/v5 pattern) — but YES the audit checklist must include DB-layer CHECK constraints (already flagged in F1 debrief) |
| Light theme as designed coherent variant (leg 06 added) | User explicit pre-flight commitment to dark + light from start; leg added to flight design before kickoff | Yes — when both themes are in scope from start, design each as a separate leg, not one as a flip of the other |
| HAT introduced 6+ token retunes + new theme toggle UI not in any leg spec | Pre-flight reference convergence reduced experiments-leg work; iteration moved to HAT | Yes — when convergence happens pre-flight, expect HAT to absorb the iteration; budget HAT for "real changes," not just verification |
| `--fg-muted` (dark) retuned `#555` → `#a8a8a8` outside of leg 07 | Token used in non-body contexts at leg 07 audit time; HAT exposed body-text use of it | Methodology improvement: parametrize a11y tests against ALL palette tokens at applicable threshold, not just observed-load-bearing pairs |
| `--status-danger-muted` invented during HAT (not in any leg spec) | User wanted "muted-default + glow-on-hover" affordance; required new token to express the idle state | Yes — the muted-default-then-glow pattern is reusable; canonize as a destructive-affordance template |
| 6 nav-rail palette tokens introduced at HAT | Light-mode body `--accent` (cyan-700) under-reads on dark navy nav rail; needed cyan-400 internal | Yes — "palette island" pattern (component carries its own theme-internal palette when chrome surface diverges from body) is legitimate; canonize with explicit boundaries (chrome only, not body content) |
| `--sidebar-bg: transparent` (dark) | "Show body gradient through" implementation choice | Replace with declarative value (`var(--bg)` or explicit `background: none`) — current value is brittle |
| Geist URL paths required discovery-first procedure (leg 04) | Upstream repo paths uncertain across releases; LICENSE filename varies | Yes — for any external-asset leg, mandate discovery-first via `gh api` before pinning download URLs |
| Lucide `releases/latest` returned stale `1.x` tag (leg 05) | Pre-rename versioning artifact in upstream repo | Document as known quirk; for any external-icon-library leg, use `gh api repos/.../tags` not `releases/latest` |
| Visual snapshot helper hand-rolled with PIL + pixelmatch (leg 08) | Python Playwright doesn't expose `to_have_screenshot()` (JS-only API in current playwright-python) | Yes — pattern reusable for any future visual-regression test; document the migration path for when Python Playwright eventually exposes the API |
| Theme-toggle added at HAT into `admin.js` | Implementation expedient; user requested in-app toggle; admin.js was the obvious mount point | No — should be moved to a reusable component (`App.theme.renderToggle(container)`) before F3 may want a top-bar quick-toggle |

## Key Learnings

### Technical

1. **CSS @layer cascade architecture is the right default for token-driven design systems.** Specificity wars eliminated; layer ordering declared once in HTML, respected by every component file. Component-level rules can be high-specificity without fighting low-specificity tokens. Cost: one sentence in HTML head, one `@layer` wrapper per CSS file. Worth canonizing as the default pattern for any new CSS module in the project.

2. **Designed light theme (per surface) beats flipped light theme.** F2's leg 06 produced a coherent light variant with zero component overrides — possible only because the dark realization (leg 03) and the light realization (leg 06) were separate design passes through the same token vocabulary, not a single pass with conditional values.

3. **Single source-of-truth for token values across CSS and Python tests is a small DRY win that pays off immediately.** `tests/browser/design_tokens.py` mirrors `tokens.css`. Leg 08's a11y test refactor was a one-line import change. The brittleness ("update both files in lockstep") is intentional and shouted by the test that pins the contract.

4. **Hand-rolled `_assert_screenshot` is a viable workaround for the Python Playwright API gap.** ~80 LOC, single PIL+pixelmatch dependency, env-var bridge for `--snapshot-update`, writes diff PNGs on failure. Migration plan: when Python Playwright exposes the API, swap internals — single-file refactor.

5. **Palette islands are a legitimate escape hatch.** When a chrome surface (nav rail, top bar, modal scrim) needs internal contrast diverging from body, give it its own palette tokens. Discourage the pattern for body content (sidebars, main panels) — anywhere a user reads prose, follow the body palette.

6. **Cycling through HAT retunes one token at a time is the right pacing.** "Bump a value, rebuild, look, judge, retune" is faster and produces better results than "speculate at a value, ship, run snapshots, revise." Validates HAT as a non-substitutable mode.

### Process

1. **A11y mandates need tiered scoping.** Distinguish *scoped a11y* (contrast / ARIA / focus on focusable elements — leg-sized) from *structural a11y* (keyboard operability rebuild, semantic landmarks, skip-links — flight-sized). Force the planner to pick a tier so reviewers can scope findings the same way. Without this, the mandate-vs-findings mismatch produces correctly-flagged-but-out-of-scope issues that have to be deferred or absorbed mid-flight.

2. **Refactor legs touching N≥6 files warrant 2 review rounds.** Leg 02 (`apply-tokens`) needed both rounds to surface all 4 catalog mismaps. The "mechanical" framing under-estimates the per-line vigilance required.

3. **Pre-flight reference convergence shifts iteration to HAT.** When users converge on direction in conversation (rather than via in-code experiments), the experiments leg becomes a no-op and HAT absorbs the iteration. Budget HAT accordingly: not "verify everything works" but "make all the small calls that didn't get made earlier."

4. **Bundled-commit-at-flight-end remains the right default** at this scale (50 files, 9 legs). The flight log + per-leg artifacts capture per-leg detail; the single commit gives reviewers one coherent change set. No per-leg commit churn.

5. **Post-review-fix-then-commit shape worked here** but should ideally happen earlier for flights with more visual rework. Consider intermediate review after the design-language-establishing leg (analog of F2 leg 03) so the highest-risk leg gets feedback before later legs build on it.

### Domain

1. **The mock provider remains load-bearing across flights.** F1 introduced it as test infrastructure dual-purposed for offline dev; F2's 12 visual snapshot tests rely on it without modification. Validates the F1 design call to make it production code, not a test stub. Future flights touching providers must preserve mock-provider compatibility.

2. **Theme-internal palette islands are an architectural seam, not pure debt.** The nav rail's light-mode internal cyan-400 (vs body cyan-700) deviates from "one accent, one palette" but does so for a sound reason (cyan-700 under-reads on dark navy). The pattern needs explicit boundaries to prevent fragmentation: chrome only (rails, top-bars, modal scrims), not body content; documented in tokens.css with a "why" comment; never spreads beyond a single named component family.

3. **Visual-prominence changes can amplify pre-existing a11y debt.** Making the muted-red delete buttons louder while leaving the structural keyboard-operability gap intact is a perceived regression the user wouldn't have noticed without seeing the new aesthetic. Future visual-changes should explicitly check: does this make any pre-existing a11y issue more or less severe?

## Recommendations

1. **Add `--fg-muted` (dark) to the WCAG body-AA test parametrize set BEFORE F3 starts touching tokens.** The retune to `#a8a8a8` happened at HAT but the test contract still doesn't pin it. A future flight retuning this token will not fail loudly. Concretely: add `("dark", "fg_muted", "bg")` and `("dark", "fg_muted", "surface")` to `test_design_tokens_a11y.py:79-97` parametrize at the 4.5:1 threshold. This closes the exact gap that produced the HAT retune.

2. **Document the design-language affordance vocabulary in `agents.md`** as an explicit "Affordance patterns" subsection. Six patterns to canonize (with file:line references in the existing CSS): *info banner* (cyan left-border + accent-translucent gradient + inset glow + `// PREFIX` eyebrow), *outlined-cyan affordance* (create/edit), *filled-cyan + glow CTA* (primary), *muted-default + glow-on-hover destructive* (delete), *neutral utility button* (read/refresh), and the *cyan-vs-neutral-vs-red disambiguation rule*. Plus add the **palette island** rule (when a component may carry its own theme-internal palette) with explicit boundaries (chrome only, not body content). Without this, F4-F6 will re-derive these inconsistently.

3. **Open a dedicated Keyboard Operability flight** (estimated 1 flight) addressing the 3 BLOCKING WCAG 2.1.1 patterns flagged at F2 review: convert nav-rail items / list items / inline deletes from `<div>`/`<span>` with click-only handlers to `<button>`; add `:focus-within` reveal for hover-only delete affordances; add roving-tabindex/listbox semantics where appropriate; consider semantic landmarks (`<nav>`, `<main>`, `<aside>`, `<h1>`, skip-link) at the same time. Reserve test slot for ~6 new visual snapshot baselines (focused-revealed states for the inline deletes). Anchor TODOs as marker comments at affected sites now (cheap; lets the future flight grep for the work).

4. **Move the theme toggle from `admin.js` to a reusable component** before F3. Either `App.theme.renderToggle(container)` (extending `theme.js`) or a new `js/components/theme-toggle.js`. Currently `admin.js` is the only mount point; F3's potential top-bar quick-toggle would re-implement the same widget if not extracted now.

5. **Add a `Token lifecycle` and `Icon lifecycle` subsection to `agents.md` "Design system."** Document the canonical workflow for a future leg adding a new token (define in tokens.css both themes → mirror in design_tokens.py if test-relevant → add contrast tests at applicable threshold → run grep gate → update agents.md table) and a new icon (fetch from Lucide at pinned tag → inline as one-liner with `aria-hidden="true" focusable="false"` → document in catalog). Today this is tribal knowledge from leg 02 / leg 05.

6. **Replace `--sidebar-bg: transparent` (dark)** with a declarative value (`var(--bg)` if "match body" is the intent) or explicit `background: none; backdrop-filter: none;` if absence is genuinely the intent. Current value will silently fail under future compositing changes.

7. **Update mission-control's `/leg` skill** to require an explicit a11y tier declaration on any leg that introduces interactive UI elements: *scoped* (contrast / ARIA / focus on already-focusable elements) or *structural* (keyboard operability, semantic landmarks). This prevents the F2-style mandate-vs-findings mismatch where review correctly flags out-of-scope issues.

## Action Items

### Immediate (next 1-3 sessions)

- [ ] **Add `--fg-muted` (dark) to a11y body-AA parametrize set** — `tests/test_design_tokens_a11y.py:79-97` adds `("dark", "fg_muted", "bg")` and `("dark", "fg_muted", "surface")` at 4.5:1 threshold. Closes the exact gap that produced the HAT retune.
- [ ] **Document affordance pattern vocabulary in `agents.md`** — six patterns + palette-island rule, with file:line references into the existing CSS. Required before F4-F6 starts.
- [ ] **Replace `--sidebar-bg: transparent` (dark)** with `var(--bg)` or explicit `background: none`. ~5-min fix.
- [ ] **Move theme toggle from `admin.js` to reusable form** — extend `theme.js` with `App.theme.renderToggle(container)` or extract to `js/components/theme-toggle.js`. ~30-min refactor.
- [ ] **Add marker comments** at the keyboard-operability debt sites (`app.js:18`, `chat.js` session-item creation, `studio.js` agent-item creation, etc.): `// TODO(a11y-keyboard): convert to <button>`. Lets the future flight grep.

### Near-term (small follow-up legs or bundled in maintenance)

- [ ] **Open Keyboard Operability flight** (M04 follow-up) to address the 3 BLOCKING WCAG 2.1.1 patterns. Mission known issue captures scope.
- [ ] **Lift `// SECTION` `::before` to a shared utility class** (`.section-marker` in `components.css`) and pick one idiom for the literal "// PREFIX" string variant (`chat.css:48`).
- [ ] **Add `Token lifecycle` and `Icon lifecycle` subsections to `agents.md`** — canonical workflows, with concrete file paths.
- [ ] **Document the Lucide release-tag quirk** (`releases/latest` returns stale `1.x`; use `tags` endpoint) in `agents.md` browser-testing or design-system section.
- [ ] **Document the Playwright `color_scheme="no-preference"` Chromium-version-specific behavior** in `agents.md` browser-testing section.
- [ ] **Document the visual-snapshot regeneration heuristic** ("which scenarios force regen vs which are likely real regressions") in `agents.md`.
- [ ] **Document the migration plan for `_assert_screenshot`** in `tests/browser/test_visual_snapshots.py` docstring: "delete this helper when playwright-python issue exposes `to_have_screenshot()`."
- [ ] **Add a defensive test** for `App.theme.set('invalid')` — currently asserts throw at `theme.js:77-79` but no test exercises it.
- [ ] **Add a `localStorage`-throwing test** — try/catch wrappers exist but are untested.
- [ ] **Consider Git LFS threshold** for visual snapshots as F4-F6 expands the surface (currently 572KB; will likely exceed 2MB by F6).

### Mission-Control methodology

- [ ] **Update `/flight` design template** to require explicit a11y tier declaration (scoped vs structural) so reviewers can scope findings consistently.
- [ ] **Update `/leg` heuristic**: any leg touching N≥6 files with mechanical-translation work gets 2 design-review rounds budgeted, not 1.
- [ ] **Add to `/flight` flight-design pattern guide**: when reference convergence happens pre-flight, expect HAT to absorb the iteration the experiments leg would have done — budget HAT for real changes, not just verification.
- [ ] **Add to `/flight` post-flight rules**: visual-prominence changes must explicitly check whether they amplify pre-existing a11y debt.
- [ ] **Update `/leg` State-Machine Reachability Audit** to include DB-layer CHECK constraints alongside FK behaviors (carrying forward from F1 debrief; F2 leg 02 hit this same gap).

### Mission-Level Known Issues at Close

These cross flight boundaries; future flights touching these areas must coordinate. Already captured in `mission.md:70-71`:

- **Pre-existing keyboard-operability debt** — nav rail items, list items (sessions/agents/admin-categories), inline delete affordances rendered as `<div>`/`<span>` with click-only handlers (WCAG 2.1.1 fail). Pre-existing from F1 and earlier; needs dedicated future flight.
- **Theme generator under Settings** — user-suggested future feature: Settings UI exposing load-bearing tokens per theme with live preview. Punted from F2; small flight or later mission.

Newly identified for the mission:

- **`--fg-muted` (dark) a11y test gap** — token retuned at HAT but not yet pinned by parametrized contrast tests; future retune may regress silently (action item #1 above closes this).
- **`admin.js` is 1248 LOC and growing** — already flagged in F1 debrief; F2 added ~70 LOC for theme toggle. F3 form-primitive extraction must absorb this too.
- **Visual-snapshot regen on every token retune** — by design, but compounds as F4-F6 add states. Worth exploring layout-not-color split.
- **`KNOWN_BADGE_TYPES` allow-list + `--type` BEM modifier pattern** — F2 introduces this as the "class-name enumeration over JS color maps" pattern. Worth canonizing in `agents.md` for any future "branded enumeration" (status types, role types).
