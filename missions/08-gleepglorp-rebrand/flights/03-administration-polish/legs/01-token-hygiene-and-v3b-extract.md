# Leg: 01-token-hygiene-and-v3b-extract

**Status**: completed
**Flight**: [Administration Polish](../flight.md)

## Objective

Close four Flight 2 debrief debt items in a single autonomous pass: fix the gallery's silent radius-swatch bug, rip the dead `--panel-shadow-glow` token from all four reference sites, retune `--panel-radius-sm` from `6px` → `4px` for actual hierarchy with `--panel-radius`, and extract the V3b button gradient from 4-way duplication into a single `--btn-v3-gradient` token.

## Context

- **Flight 2 debrief carry-overs**: The four items are recommendations 3, 4, 4, and "refactor V3b gradient" from `flight-debrief.md`. Verified `confirmed-live` against current code during Phase 1b reconnaissance (see flight log).
- **Substrate is clean**: Flight 2 landed on main (commit `2f3b51c`) with the design language vocabulary committed. This leg operates on tokens-only and one JS line; no rendering logic touched.
- **Why first**: Subsequent polish legs (02-04) would otherwise have to navigate around the V3b duplication (4-way edit per retune) and the radius bug (gallery radius swatches render as 0-radius squares with blank hex labels). Doing this leg first means polish legs touch only their target surfaces.
- **Carry-over from prior debrief patterns**: Flight 2 Leg 06 documented an "opportunistic adjacent fix at design-review caught moments" pattern; this leg is the deliberate version — collecting four already-surfaced items into one mechanical pass.

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/css/tokens.css` — `--panel-shadow-glow` defined at `:135` (light) and `:271` (dark). **Active consumers (see api.py below) — NOT dead in CSS terms but no CSS-side consumers exist.** `--panel-radius-sm` defined at `:132` and `:268` as `6px`, identical to `--panel-radius`. Stale comment block at `:55-60` (inside the `--glass-bg` preceding comment) references the dead token.
- `the_one/interfaces/web/static/css/components.css` — V3b gradient duplicated literally at `:59` (`.app-picker-button`), `:387` (`.btn-outlined-primary`), `:426` (`.btn-filled-primary`), `:459` (`.btn-muted-destructive`). Comment at `:613` references the dead `--panel-shadow-glow` substitution rule.
- `the_one/interfaces/web/api.py:1535` — **LIVE consumer (5th site, missed by Flight 2 debrief because that recon scoped to `static/`)**: the OAuth callback page renders an inline `<style>` block where `.oauth-callback-card` uses `box-shadow: var(--panel-shadow), var(--panel-shadow-glow);`. Ripping `--panel-shadow-glow` without addressing this leaves a `var()` reference resolving to nothing — and since `box-shadow` is comma-separated, an invalid stop invalidates the WHOLE declaration. Browsers would drop both shadows. Must be edited as part of the rip.
- `the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js:30-32` — array `['--panel-radius-sm', '--panel-radius-md', '--panel-radius-lg']`; only the first is defined. The other two render as 0-radius swatches with blank hex labels.
- `the_one/agents.md` — three references to `--panel-shadow-glow`: `:602` (composition-rule narrative naming the dead token), `:682` and `:699` (Mission 08 F1 L2 historical narrative naming the dead token in a token-lockstep list).
- `tests/browser/design_tokens.py` — verified during flight design: does NOT currently track `--panel-radius-sm` or `--btn-v3-gradient`. No mirror updates needed in this leg.
- **`--panel-radius-sm` consumer enumeration** (verified during Leg 01 design review — full grep count: 16 CSS-rule consumers + 4 inline-style consumers in gallery section modules = 20 total token references, automatically tracked from the declaration retune): `admin.css` (4: `:31, :44, :262, :561`), `chat.css` (2: `:42, :118`), `components.css` (10), `tokens-section.js:30` (gallery surveys this token-name as a swatch), `surfaces-section.js:70` (inline-style consumer in topbar miniature), `status-section.js:84, :92` (inline-style consumers in empty-state/empty-canvas boxes). Per consumer review during Leg 01 design: none require radius equality with `--panel-radius`; all want "small radius" semantically. Retune 6→4px is safe.

## Outputs

What exists after this leg completes:

- `tokens.css` — `--panel-shadow-glow` declarations removed from both themes. `:55-60` comment block rewritten to describe the substitution rule without naming the removed token. `--panel-radius-sm` retuned to `4px` in both themes. New `--btn-v3-gradient` token defined at `:root` level (theme-independent — gradient stops use fixed rgba alphas).
- `components.css` — 4 V3b consumer sites use `background-image: var(--btn-v3-gradient);`. `:613` comment rewritten to past tense without naming the removed token.
- `api.py:1535` — `box-shadow` declaration in the OAuth callback card's inline style block reduced from `var(--panel-shadow), var(--panel-shadow-glow);` to `var(--panel-shadow);`. Accepts the visual loss of the accent halo on the callback card; aligns with the flight intent that "glass composition rule replaces the accent-glow treatment on chrome surfaces."
- `tokens-section.js` — gallery radius array contains only the defined tokens; radius swatches render correctly.
- `agents.md` — three `--panel-shadow-glow` references rewritten to describe the composition rule / historical narrative without naming the removed token.
- Branch `flight/03-administration-polish` carries the changes uncommitted; commit happens at flight close per the agentic-workflow's deferred-commit pattern.

## Acceptance Criteria

- [x] `grep -rn "panel-shadow-glow" the_one/` returns no matches (rip sentinel — CSS + JS + Python; **broadened from `static/` to whole package** to catch the api.py consumer)
- [x] `grep -n "panel-shadow-glow" the_one/agents.md` returns no matches (rip sentinel — docs)
- [x] `grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css` returns `0` (V3b extraction sentinel — currently returns `4`)
- [x] `grep -n "panel-radius-md\|panel-radius-lg" the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` returns no matches (gallery radius bug fixed)
- [x] `grep -n "btn-v3-gradient" the_one/interfaces/web/static/css/tokens.css` returns the new declaration (must be defined in both light + dark theme blocks — or in `:root` if theme-independent, since the gradient stops are all rgba and don't change between themes)
- [x] `grep -c "var(--btn-v3-gradient)" the_one/interfaces/web/static/css/components.css` returns `4` (consumed at all 4 V3b sites)
- [x] `grep -n "panel-radius-sm: 4px" the_one/interfaces/web/static/css/tokens.css` returns 2 matches (light + dark theme)
- [x] Narrow test gate passes: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10`
- [x] WCAG audit specifically passes: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` — all 45 parametrizations green (no contrast pair changes, but verify the audit hasn't regressed)
- [x] Visual scan of `#admin/design-language` in dev mode: tokens section's radius swatches now render with actual rounded corners + visible hex labels; button gallery V3b family appearance unchanged from pre-leg state (extract is purely refactor).
- [x] Flight log updated with leg progress + any deviations observed

## Verification Steps

How to confirm each criterion is met:

1. **Rip sentinels** (3 greps):
   ```
   grep -rn "panel-shadow-glow" the_one/
   grep -n "panel-shadow-glow" the_one/agents.md
   grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css
   ```
   First two return nothing; third returns `0`. **Note**: the first grep is broadened from `static/` to whole `the_one/` package — recon for this leg surfaced an active consumer at `api.py:1535` that the narrower `static/`-scoped grep would have missed.

2. **Token-section radius bug** (1 grep):
   ```
   grep -n "panel-radius-md\|panel-radius-lg" the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js
   ```
   Returns nothing.

3. **V3b extraction sentinels** (2 greps):
   ```
   grep -n "btn-v3-gradient" the_one/interfaces/web/static/css/tokens.css
   grep -c "var(--btn-v3-gradient)" the_one/interfaces/web/static/css/components.css
   ```
   First returns the new declaration line(s); second returns `4`.

4. **Radius retune sentinel**:
   ```
   grep -n "panel-radius-sm: 4px" the_one/interfaces/web/static/css/tokens.css
   ```
   Returns 2 lines (one per theme).

5. **Narrow test gate** (in container):
   ```
   docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10
   ```
   Expected: 56/56 pass (matches Flight 1 + Flight 2 baseline).

6. **WCAG audit alone** (in container):
   ```
   docker exec the-one pytest tests/test_design_tokens_a11y.py -v
   ```
   Expected: 45/45 pass.

7. **Visual scan**: Load app in dev mode, navigate to `#admin/design-language`, confirm:
   - Tokens section's radius swatches render with visible rounded corners (previously rendered as 0-radius squares with blank labels for `-md` / `-lg`)
   - Buttons section's V3b family (outlined / filled / muted-destructive / app-picker buttons) appears unchanged from pre-leg state
   - Visual sweep across the gallery for any unexpected radius shifts on small-radius primitives (notable consumers: app-flash, code-block bottom corner, app-picker, theme toggle container, token swatches, V3b buttons, btn-lg)

## Implementation Guidance

**Order matters** — execute in this sequence so verification sentinels can be run incrementally:

1. **Fix `tokens-section.js:30-32` first** (no dependencies, simplest)
   - Replace the array `['--panel-radius', '--panel-radius-sm', '--panel-radius-md', '--panel-radius-lg']` with `['--panel-radius', '--panel-radius-sm']`.
   - Verify sentinel: `grep -n "panel-radius-md\|panel-radius-lg" the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` returns nothing.

2. **Retune `--panel-radius-sm`** in `tokens.css`
   - Line `:132` (light theme): `--panel-radius-sm: 6px;` → `--panel-radius-sm: 4px;`
   - Line `:268` (dark theme): same change.
   - Verify sentinel: `grep -n "panel-radius-sm: 4px" the_one/interfaces/web/static/css/tokens.css` returns 2 lines.

3. **Define `--btn-v3-gradient` token** in `tokens.css`
   - The V3b gradient currently in components.css is theme-independent (uses rgba values that don't change between themes), so define ONCE in the `:root` selector at the top of `tokens.css` (or as a `@layer tokens` block-level declaration outside the per-theme blocks).
   - Token value:
     ```css
     --btn-v3-gradient: linear-gradient(to bottom,
       rgba(255, 255, 255, 0.30) 0%,
       rgba(255, 255, 255, 0.10) 35%,
       rgba(255, 255, 255, 0.0) 50%,
       rgba(0, 0, 0, 0.10) 100%
     );
     ```
   - Verify the existing gradient stops match this exactly at all 4 sites in components.css BEFORE substituting — if any site has drift (e.g., a different alpha value), pause and resolve.
   - Verify sentinel: `grep -n "btn-v3-gradient" the_one/interfaces/web/static/css/tokens.css` returns the declaration line.

4. **Substitute V3b gradient at 4 sites in `components.css`**
   - Line `:59` (`.app-picker-button`): replace the `background-image: linear-gradient(to bottom, …)` block with `background-image: var(--btn-v3-gradient);`
   - Line `:387` (`.btn-outlined-primary`): same.
   - Line `:426` (`.btn-filled-primary`): same.
   - Line `:459` (`.btn-muted-destructive`): same.
   - Note: each site spans multiple lines (the gradient is broken across lines). The replacement is a single-line `background-image: var(--btn-v3-gradient);`.
   - Verify sentinels:
     - `grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css` returns `0`
     - `grep -c "var(--btn-v3-gradient)" the_one/interfaces/web/static/css/components.css` returns `4`

5. **Substitute `api.py:1535` BEFORE ripping the token declaration** — the OAuth callback card's `box-shadow` rule consumes the token live. Change `box-shadow: var(--panel-shadow), var(--panel-shadow-glow);` to `box-shadow: var(--panel-shadow);` (drop the second stop). Decision rationale: the flight intent is "glass composition rule replaces the accent-glow treatment on chrome surfaces"; the OAuth callback card is a chrome surface and inherits the rip cleanly. Visual delta: loses the accent halo around the callback card (replaced by the plain panel shadow). If a future flight wants to restore an accent treatment on this card specifically, it can do so deliberately. Order is load-bearing — if you rip the token first and the api.py edit fails, the OAuth callback page renders with zero box-shadow (the comma-separated `box-shadow` rule becomes invalid in browsers when one of its `var()` references resolves to nothing).
   - Verify: `grep -n "panel-shadow-glow" the_one/interfaces/web/api.py` returns nothing.

6. **Rip `--panel-shadow-glow`** in `tokens.css` (4 sites)
   - Line `:135` (light theme `--panel-shadow-glow: 0 0 12px var(--accent-glow);`): delete the line.
   - Line `:271` (dark theme `--panel-shadow-glow: 0 4px 12px rgba(109, 40, 217, 0.18), 0 1px 3px rgba(15, 23, 42, 0.06);`): delete the line.
   - Line `:55-60` (stale comment block inside the `--glass-bg` preceding comment): rewrite to describe the substitution rule without naming the removed token. Current text at `:59-60`: `"Glass surfaces REPLACE / --panel-shadow-glow per the flight's composition rule."` New text suggestion: `"Glass surfaces replace the prior accent-tinted shadow treatment on chrome per the flight's composition rule."` — adjust verbiage if you find a tighter formulation.
   - Line `:264-266` (dark-theme block comment "panel design tokens — drop-shadow style replaces dark's glow shadows. / --panel-shadow-glow composites accent tint + dark elevation for the / 'designed affordance with subtle lift' feeling on white."): rewrite to describe the dark-theme `--panel-shadow` without naming `--panel-shadow-glow`. The first sentence is fine; remove the two sentences referencing the dead token. (This block contains a reference at `:265` per recon.)
   - Verify sentinel: `grep -rn "panel-shadow-glow" the_one/interfaces/web/static/` returns no matches.

7. **Rewrite components.css:613 comment**
   - Current text (inside an `@layer components` rule): `"/* --panel-shadow-glow intentionally dropped — glass surfaces use the / …"`. Rewrite to past tense without naming the removed token: `"/* Prior accent-glow shadow intentionally dropped — glass surfaces use the / …"` (or similar — preserve the rest of the multi-line comment).
   - Verify sentinel: `grep -c "panel-shadow-glow" the_one/interfaces/web/static/css/components.css` returns `0`.

8. **Rewrite agents.md references** (3 sites)
   - Line `:602` (composition rule narrative): currently reads `"Replaces \`--panel-shadow-glow\` on these surfaces (it would composite poorly with the bezel stack)."` Rewrite to `"Replaces the prior accent-tinted shadow treatment on these surfaces (it would composite poorly with the bezel stack)."`
   - Line `:682` (historical narrative, blockquote list): currently reads `"accent-glow / accent-translucent / panel-shadow-glow rgba tokens in"`. Rewrite to `"accent-glow / accent-translucent rgba tokens in"`. Adjust prose if the surrounding sentence becomes ungrammatical.
   - Line `:699` (historical narrative bullet): currently reads `"`--panel-shadow-glow` cyan tint also updated."`. Delete this entire bullet line — the historical narrative loses its tail clause but stays readable.
   - Verify sentinel: `grep -n "panel-shadow-glow" the_one/agents.md` returns no matches.

9. **Run verification gate**
   - In-container narrow gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10`. Expected: 56/56.
   - Visual verification of the gallery: run `make rebuild` (mounts the new CSS + JS into the container), load the app in dev mode, navigate to `#admin/design-language`, verify radius swatches now render correctly + V3b button family appearance unchanged.

10. **Update flight log + leg status**
   - Append a `### 01-token-hygiene-and-v3b-extract` entry to `flight-log.md` under `## Leg Progress`, capturing what was implemented and any deviations.
   - Update this leg's status from `planning` → `in-flight` (at start) → `landed` (at end).
   - Update Pre-Flight Checklist box `[ ] Legs defined` in `flight.md` to `[x]`.
   - Do NOT commit. Do NOT mark leg as `completed`. Do NOT check off the leg in flight.md (the commit happens at flight close per the agentic-workflow's deferred-commit pattern, and `completed` status is set by the commit step).
   - Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **V3b gradient drift at a consumer site**: If any of the 4 V3b sites has a gradient that doesn't EXACTLY match the canonical 4-stop value (e.g., a subtly different alpha), pause and flag in flight log — substituting with `--btn-v3-gradient` would visually shift that site. Two resolution paths: (a) the canonical value wins (substitute, accept the small visual shift, document); (b) leave the divergent site untouched and document why it diverges. Default: path (a) unless the diverging value reads as deliberate (Flight 2 explicitly locked V3b as the canonical button family treatment — divergences are likely scribal drift).
- **Other `linear-gradient(to bottom` matches in tokens.css are NOT V3b candidates**: `tokens.css:66` (`--glass-gleam` dark theme) and `:208` (`--glass-gleam` light theme) are glass-gleam reflection gradients (different stops, different role — they are theme-tuned tokens, not the V3b button gradient). Leave both untouched. The V3b extraction sentinel `grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css` is correctly scoped to `components.css` only and ignores these `tokens.css` matches.
- **`tokens.css:60` comment block context**: The comment block lives inside the `--glass-bg` token's preceding multi-line comment. Re-read lines 55-66 before editing to preserve the surrounding narrative.
- **`tokens.css:264-266` dark-theme comment block**: Similar — preserve surrounding narrative about `--panel-shadow` (still defined) while removing references to `--panel-shadow-glow`.
- **`agents.md:602` is inside the Mission 08 F2 Design Language Layer composition-rule subsection**: rewriting the line must keep the substitution-rule semantics intact (the rule is "glass replaces something on chrome surfaces" — the something just gets named generically now).
- **`agents.md` historical narrative (lines 678-700)**: This is a Mission 08 F1 L2 historical update block. The accent-color retune narrative is still valid; only the dead-token mention is being stripped. Keep the violet retune narrative intact.
- **Existing visual snapshot baselines**: Are gitignored per project convention. The 6→4px radius retune will shift small-radius primitives' rendering by 2px corner-radius, which is a visible delta. Visual snapshot regen is deferred to Leg 06 per the flight's flight-close pattern; this leg should NOT regenerate baselines mid-flight.
- **WCAG audit risk**: The audit reads CSS variables for contrast-pair parametrizations. None of the affected tokens (`--panel-shadow-glow`, `--panel-radius-sm`, `--btn-v3-gradient`) are color tokens, so audit pairs should be unaffected. If the audit fails unexpectedly, surface the failure — it indicates a mirror in `design_tokens.py` that has drifted.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — declaration/comment edits (2 panel-shadow-glow rips, 2 radius retunes, 2 comment rewrites at `:55-60` light-block and dark-block, 1 new `--btn-v3-gradient` declaration)
- `the_one/interfaces/web/static/css/components.css` — 4 V3b consumer-site substitutions + 1 comment rewrite at `:613`
- `the_one/interfaces/web/api.py` — line `:1535` box-shadow declaration reduced from 2 stops to 1 (drop the dead-token reference)
- `the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` — line `:30-32` array fix
- `the_one/agents.md` — 3 references rewritten (lines `:602`, `:682`, `:699`)
- `missions/08-gleepglorp-rebrand/flights/03-administration-polish/flight-log.md` — append leg-progress entry
- `missions/08-gleepglorp-rebrand/flights/03-administration-polish/legs/01-token-hygiene-and-v3b-extract.md` — leg status `planning` → `in-flight` → `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]` (Developer agent should signal `review-needed` per the agentic-workflow protocol — Flight Director will arrange commit + close at flight end, NOT after this leg):**

- [ ] All acceptance criteria verified (run all 4 grep sentinels + narrow gate)
- [ ] Narrow gate passes (`56/56`)
- [ ] WCAG audit passes (`45/45`)
- [ ] Visual scan of gallery confirms radius swatches render + V3b appearance unchanged
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header — NOT `completed`; `completed` is set by the eventual commit step at flight close)
- [ ] Do NOT check off this leg in flight.md (deferred to flight-close commit)
- [ ] Do NOT commit (deferred to flight-close commit per agentic-workflow standard pattern)
- [ ] Signal `[HANDOFF:review-needed]`

## Citation Audit

11 citations verified against current code at leg design time (commit `2f3b51c` on main + uncommitted Flight 3 artifact additions on branch `flight/03-administration-polish`):

- `tokens.css:55-60` — verified: 6-line comment block; `:60` reads `"--panel-shadow-glow per the flight's composition rule."` inside `--glass-bg` preceding comment block. (Cite tightened during Leg 01 design review from bare `:60` to the comment-block range.)
- `tokens.css:132` + `:268` — verified: both define `--panel-radius-sm: 6px;`.
- `tokens.css:135` + `:271` — verified: light defines `--panel-shadow-glow: 0 0 12px var(--accent-glow);`; dark defines layered shadow.
- `tokens.css:264-266` — verified: dark-theme comment block references the dead token at `:265` ("--panel-shadow-glow composites accent tint…").
- `components.css:59, :387, :426, :459` — verified: all 4 sites carry `background-image: linear-gradient(to bottom,` opening a multi-line gradient definition. The 4-stop canonical value was confirmed visually equivalent across sites at flight design.
- `components.css:613` — verified: comment reads `"--panel-shadow-glow intentionally dropped — glass surfaces use the …"`.
- **`api.py:1535`** — verified (surfaced during Leg 01 design review; missed by Flight 2 debrief recon which scoped to `static/`): `box-shadow: var(--panel-shadow), var(--panel-shadow-glow);` inside the OAuth callback card's inline `<style>` block. Live consumer; must be edited as part of the rip.
- `tokens-section.js:30-32` — verified: array entries `'--panel-radius-sm'`, `'--panel-radius-md'`, `'--panel-radius-lg'`.
- `agents.md:602` — verified: composition-rule sentence in the Mission 08 F2 Design Language Layer subsection.
- `agents.md:682` — verified: blockquote list reads `"accent-glow / accent-translucent / panel-shadow-glow rgba tokens in"`.
- `agents.md:699` — verified: bullet reads `"`--panel-shadow-glow` cyan tint also updated."`.
- **`tokens.css:66` + `:208`** — verified: these are `--glass-gleam` gradient definitions (NOT V3b candidates). Listed in Edge Cases to prevent over-eager edit passes.

All citations clean; no drift after Leg 01 design-review recon. `tests/browser/design_tokens.py` does NOT track `--panel-radius-sm` or `--btn-v3-gradient` (verified during flight-design Architect review) — no mirror updates needed.

**Leg 01 design-review recon finding**: The `--panel-shadow-glow` rip is a 6-site edit, not 4. Flight 2 debrief's "dead token" classification was based on a `static/`-scoped grep that missed `api.py:1535`. Edit accounting: 6 rip sites (2 tokens.css declarations + 2 tokens.css comment blocks at `:55-60` + `:264-266` + 1 components.css `:613` comment + 1 api.py `:1535` box-shadow edit) + 3 agents.md docs sites + 5 V3b consumer-site substitutions (1 token definition + 4 consumer replacements) + 1 radius bug fix + 2 radius retunes + 1 new `--btn-v3-gradient` token declaration = 18 mechanical edits.
