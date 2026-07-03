# Flight: Design Language v3 — Tokens and Type

**Status**: ready
**Mission**: [UI Redesign — Clean, Professional, Consistent](../../mission.md)

## Contributing to Criteria

- [ ] SC1 — Complete visual-language replacement (token layer: glows/glass/bezels/chamfer/chrome retired here)
- [ ] SC2 — Both themes individually designed and accessible (new palette + full-palette AA audit land here)
- [ ] SC9 — Documentation reflects the new language (design-system reference + apparatus doctrine start here)

---

## Pre-Flight

### Objective

Replace the alien-console token system with the quiet-instrument-panel token system at the CSS layer: new neutral/accent/status palettes for both themes (each designed per-surface), a spacing/radius/shadow system, retirement of the glow/glass/bezel/chamfer/shell-chrome/btn-v3-gradient categories and their ~130 consumer declarations, the `// PREFIX` section-marker treatment quieted, and the a11y test machinery expanded to cover the full palette with an enforced CSS↔mirror lockstep. After this flight the app already *reads* quiet in both themes; Flight 3 rebuilds component structure on top.

### Open Questions

- [x] Keep violet or move to blue accent? → Design Decisions (violet retained per mission brand-continuity constraint)
- [x] How do retired tokens leave without breaking `test_token_definitions.py`? → Design Decisions (retire-with-consumers, single flight)
- [x] Does the type scale change? → Design Decisions (Geist + current size tokens retained; usage discipline changes)

### Design Decisions

**Palette v3 — violet accent on neutral ladders, both themes designed separately** (per mission constraint + design-research brief):
- **Dark**: lifted charcoal ladder replacing near-black — `--bg #101114`, `--bg-subtle/--surface #17181c`, `--surface-elevated #1c1d22`; borders `#26272c`/`#33343b` hairlines; text ladder `#ededf0`/`#a1a3ad`/`#7d7f89` family; accent stays violet-400 `#a78bfa` (already correct for dark), `--accent-subtle` washes replace glows.
- **Light**: white/near-white ladder — `--bg #ffffff`, `--bg-subtle #fafafa`; borders `#e4e4e7`/`#d4d4d8`; text `#18181b`/`#52525b`/`#71717a`; accent violet-700 `#6d28d9` (current value, retained).
- Status colors retuned to AA-passing values per the research brief (success `#15803d` light — current value retained; warning/danger checked per theme); status *glows* retired, `-bg-soft`/-border` soft fills kept.
- Provider/tool badge tokens kept as-is (brand-stable). `--accent-api` kept but demoted to badge-tier semantics (not an interactive accent).
- Final hex values are leg-level decisions validated by the contrast suite — the flight pins the *structure* (ladder roles, AA gates), not every hex.
- Rationale: violet preserves brand continuity (mission constraint); the neutral ladders and hairline discipline deliver the "quiet" read.
- Trade-off: two accents' worth of visual identity (violet + badge colors) demands restraint rules — accent appears only on interactive/selected states (documented in agents.md).

**Retire-with-consumers, one flight, staged**: `test_token_definitions.py` fails if a consumer references a deleted token (its `var()` regex captures the primary token even in fallback form), so retirement is sequenced inside the flight: Leg 1 lands the v3 token tables while keeping retired-category names defined as **neutralized values** (glows→`transparent`, glass-blur→`0`/solid, bezel shadows→`none`, chrome→solid colors, btn-v3-gradient→`none`) — the app visually quiets immediately and nothing breaks. Consumer removal is then split by nature of the work (architect review, 2026-07-03): **Leg 2a** does the mechanical sweep — ~130 token-reference removals across `components.css`/`chat.css`/`studio.css`/`admin.css` (blast radius verified: glass 45 + backdrop-filter 14, glow 50, bezel 26, btn-v3-gradient 6, panel-shadow 1), section-title quieting, then deletes the neutralized aliases + the now-dead `prefers-reduced-transparency` block (`prefers-reduced-motion` stays). **Leg 2b** dismantles the base.css shell *structure* — the `#main-content` chamfered L-bracket `clip-path` + frame fill, `::before` inner-glow layer, `.content-panel` mask-image, topbar sheen, brushed sidebar chrome — down to a plain quiet shell (bg + hairline borders). This structural work is qualitatively different from the sweep and carries its own divert checkpoint.
- **F2/F3 shell boundary (decided)**: F2 strips the shell to a plain quiet shell (a neutralized-token chamfer frame would read broken-quiet, not designed-quiet — the old decorative geometry is physically removed here); F3 owns the *rebuilt* shell structure and semantics (wordmark, nav restyle, topbar/sidebar layout, component vocabulary).
- **Chamfer containment corrected**: the shell chamfer lives in base.css, but a SECOND chamfer exists — the selected-tab L-bracket `clip-path` at `components.css:819` (hardcoded 5px, references `var(--accent)`, invisible to token sweeps and chamfer greps). It is a shared-component treatment: recorded as an **explicit Flight 3 handoff** (tabs rebuild). SC1's "no chamfered panels" is therefore NOT proven by grep-zero at F2 close — F2's completion evidence notes the tab L-bracket as the known, consciously-deferred remnant.

**Section markers quieted at the CSS layer**: `.section-title` (components.css:332-352) drops the `::before { content: "//" }` pseudo-element and the mono-uppercase-letterspaced treatment in favor of a quiet label style (sans, `--font-size-body-sm`, medium weight, `--fg-secondary`). All 52 JS usage sites inherit the change without JS edits. (Renaming the class/semantics is Flight 3 component-vocabulary work.)

**Spacing/radius/shadow system introduced, migrated incrementally**: new tokens `--space-1..-8` (4/8/12/16/24/32/48/64), `--radius-sm 6 / --radius-md 8 / --radius-lg 12`, and exactly two shadows (`--shadow-popover`, `--shadow-modal`). Old `--panel-radius*` names stay defined (aliased to the new scale) until Flight 3 migrates component CSS. Declarations Flight 2 rewrites anyway adopt the new tokens; wholesale migration of untouched declarations is NOT this flight's scope.

**Type: Geist retained, scale retained, discipline changed**: fonts.css `@font-face` and size tokens are already right for the target aesthetic (13px UI chrome / 14-15px content, per research brief). No new fonts vendored. Weight discipline (400 body / 500-600 emphasis, no 700 in chrome) and tabular-numerals-for-tables are documented as conventions and applied where Leg 2 touches declarations.

**A11y machinery: full-palette parametrization + enforced lockstep** (debrief mandate): `tests/browser/design_tokens.py` mirror rewritten for v3 (fixing the two known drifts: `--fg-faint`, `--fg-tertiary` dark); `tests/test_design_tokens_a11y.py` parametrization expanded to cover ALL fg×bg palette pairs used by the system in BOTH themes (documented deliberate exceptions annotated, e.g. `--fg-faint`); a new **mirror↔CSS value-sync guard** (same lint-by-pytest genre as Flight 1's guards) parses `tokens.css` and asserts the mirror's values match — the lockstep is enforced, not aspirational, and lands in the SAME leg as the new tokens.css.

**Cross-tab theme sync ADDED (not amended)** (mission Known Issue, corrected by architect review): grep-verified, NO `storage` event listener exists anywhere in `static/js` — cross-tab sync is entirely absent (neither set nor unset propagates; `App.theme.set` dispatches only a same-document CustomEvent). The run log's "set propagated live" observation is contradicted by the Validator's own note and by the code. The leg first re-verifies actual current cross-tab behavior, then **adds** a `window.addEventListener('storage', …)` in theme.js that reapplies the theme on both value change AND `newValue === null` (unset → revert to auto). Regression test covers BOTH directions (set propagates; unset propagates).

**Guards, all mutation-probe-tested** (Flight-1 "proven to fail loudly" discipline). The **mirror↔CSS value-sync guard lands in Leg 1** with the new tokens.css and rewritten mirror (the lockstep must be enforced from the moment the mirror is rewritten, not left unguarded through the churn legs): it parses tokens.css's two theme blocks and asserts `design_tokens.py` values match, scoped to literal-hex tokens with per-token extraction rules — the mirror is deliberately not a verbatim copy (layered values mirror a base color; `var()`-indirection entries and omissions exist), so a naive whole-file compare would false-positive; v3 dropping shell-chrome/glow simplifies the surface. **Two further guards land together in Leg 3**:
1. **Banned-token guard** (mission DD, promised "after Flight 2", NOT yet shipped — architect confirmed absent): fails on any reintroduction of retired-category tokens/effects in `static/css` (glow/glass/bezel/chamfer/shell-chrome/btn-v3-gradient names, `backdrop-filter`). This is the enforcement behind SC1's retirement — without it Flights 3–6 could silently reintroduce effects. (Lands in Leg 3 because it can only go green after Legs 2a/2b remove the last references.)
2. **Backtick tripwire** (debrief rec 3): fails on template literals containing `data-testid` or backtick innerHTML RHS.

**Focus system pinned** (mission scope, was implicit): `:focus-visible` = `outline: 2px solid var(--accent); outline-offset: 2px` — **no halo/glow**. Neutralizing `--accent-glow` leaves existing rules with a visible ring (verified: every focus-visible rule pairs glow with a 2px accent outline), and the sweep legs normalize to the pinned form where touched. `:focus-within` container treatments (e.g. `admin.css:405`) degrade from halo to border-color change — **accepted as intentional**. Focus-visible acceptance criteria ride Legs 2a/2b.

**fg-faint exception re-evaluated, not ported**: the "deliberate sub-AA exception" is false in production (dark `--fg-faint` is `#808080` ≈ 5:1 — passes AA; the exception test audits a phantom `#444444`). The v3 palette decides fresh whether a sub-AA faint tier exists at all; if none does, the exception tests are deleted rather than re-pointed.

**Docs land in-flight** (SC9 start + debrief rec 7): `the_one/agents.md` design-system section rewritten for v3 (token roles, accent restraint rule, weight discipline, both-themes-designed contract, AA audit contract); goldfinch apparatus doctrine (printToPDF provenance fallback, multi-tab provenance discipline, a11y rendered/notRendered discrimination, run-tab-unoccluded precondition) promoted from the Flight-1 run log into the testing docs.

**Design gallery updated minimally**: `tokens-section.js`'s hand-maintained token list updated for v3 (drop glow/glass entries, add spacing/radius/shadow swatches). Full gallery-section redesign is Flight 3 (it showcases component variants that F3 rebuilds). This resolves the mission Open Question "gallery redesigned in place or rebuilt" as: **updated in place at F2 (tokens), rebuilt per-section at F3 (components)**.

**Guard churn is bookkeeping** (debrief rec 1): every leg that touches CSS/JS expects testid-registry or sink-baseline guard diffs; specs treat the exact-diff failure output as the update worklist. Expected sink-baseline direction: unchanged (this flight rewrites CSS, not JS sinks; `tokens-section.js` may shift entries — justify any diff in the flight log).

### Prerequisites

- [x] Flight 1 landed: guards active, browser suite green (532/0), perf baseline anchored, apparatus proven
- [x] `make up` server on 8484 for visual verification via goldfinch; `make restart` picks up CSS edits
- [x] Token-architecture map verified (81 tokens, consumer blast radii, lockstep contract — mission-planning exploration, 2026-07-03)
- [x] Pixel-snapshot invalidation accepted (advisory during redesign window per Flight 1 DD; regenerate locally at flight close)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Leg 1 is the palette flight-deck: new tokens.css (both theme blocks rewritten, retired categories neutralized in place), mirror rewrite + full parametrization in the same change, validated by the contrast suite before anything else moves. Leg 2a is the mechanical consumer sweep (components → chat → studio → admin), section-title quieting, alias + reduced-transparency deletion — after 2a, retired-category references in those four files are zero. Leg 2b dismantles the base.css shell structure with its own divert checkpoint. Leg 3 is JS-side + guards + docs: cross-tab theme listener + both-direction test, the three guards (banned-token / mirror-sync / backtick, probe-tested), tokens-section.js gallery update, agents.md v3 rewrite + apparatus doctrine. Leg 4 verifies: full suites, both-themes visual pass via goldfinch (three areas + tabs + focus states, printToPDF fallback per doctrine), shell-navigation-smoke re-run, flight log records per-file sink counts (expect unchanged ±justified — this flight rewrites CSS, not JS sinks).

Dual-theme discipline: Leg 1 designs BOTH theme blocks (land-dark-port-light cadence permitted inside the leg, but the leg doesn't land with one theme unfinished).

### Checkpoints

- [ ] Leg 1: contrast suite green with full-palette parametrization; mirror-sync guard landed and green; app renders quiet in both themes (neutralized effects)
- [ ] Leg 2a: zero retired-category references in components/chat/studio/admin CSS; token-definition test green; both themes visually coherent
- [ ] Leg 2b (divert gate): base.css shell reads plain-quiet in both themes; shell-navigation-smoke still green; no structural coupling surprises beyond leg scope
- [ ] Leg 3: cross-tab theme sync works both directions (regression test green); banned-token guard + tripwire active and probe-tested; agents.md reflects v3
- [ ] Leg 4: `make test-unit` + `make test-browser` green; shell-navigation-smoke passes; both-themes evidence captured incl. tabs + focus states

### Adaptation Criteria

**Divert if**:
- The full-palette AA audit forces palette restructuring beyond hex retunes (e.g., a whole ladder role can't clear AA on its surfaces)
- Consumer removal reveals load-bearing layout coupling to retired tokens (e.g., chamfer geometry structurally required by the shell) bigger than a leg can absorb — that's Flight 3 shell work pulled forward; stop and re-scope

**Acceptable variations**:
- Exact hex values within the pinned ladder roles
- Leg 2 file-sweep order
- Where the apparatus doctrine lands (agents.md vs a testing doc), as long as it's discoverable

### Legs

> **Note:** Tentative; created one at a time as the flight progresses.

- [ ] `tokens-v3-both-themes` - New token tables + neutralized retirements + mirror rewrite + full-palette parametrization (fg-faint exception re-derived) + mirror-sync guard (probe-tested)
- [ ] `consumer-sweep` - (2a) ~130 mechanical token-reference removals in components/chat/studio/admin CSS; `.section-title` quieting (incl. hardcoded ALL-CAPS text in `status-section.js` and stale `//` comments); alias + reduced-transparency deletion; focus-visible normalization where touched
- [ ] `shell-structure-dismantle` - (2b) base.css: de-chamfer `#main-content`, remove frame/glow/mask/sheen/chrome structure → plain quiet shell; own divert checkpoint
- [ ] `theme-sync-guards-docs` - ADD cross-tab storage listener + both-direction regression test; banned-token guard + mirror-sync guard + backtick tripwire (all probe-tested); gallery token list; agents.md v3 + apparatus doctrine
- [ ] `dual-theme-verification` - Full suites + goldfinch visual pass both themes (explicitly capturing tabs and :focus-visible states, so the deferred tab L-bracket and outline-only focus are seen and consciously accepted) + shell-navigation-smoke re-run

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Tests passing (`make test-unit` + `make test-browser`)
- [ ] Flight log updated
- [ ] Documentation updated (agents.md design section, CLAUDE.md if commands changed)

### Verification

Contrast suite green over the full v3 palette (both themes); `test_token_definitions.py` green with zero retired-category tokens or references remaining; mirror-sync guard green; browser suite green; `tests/behavior/shell-navigation-smoke/runs/` contains a passing run dated this flight; goldfinch-captured evidence of all three areas in both themes shows the quiet language (no glows/glass/bezels/chamfer/`//` markers).
