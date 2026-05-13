# Leg: 01-prep-and-debrief-debt-close

**Status**: completed
**Flight**: [Studio Polish](../flight.md)

## Objective

Autonomous prep leg. Close 7 mechanical Flight 3.5 debrief items in a single pass so the polish legs (02-03) operate on a clean substrate + the reduced-transparency posture is coherent before Studio composes on top. All items are mechanical, low-risk, and interlock (token rename ripples into one CSS rule; reduced-transparency block extends existing pattern; agents.md updates are pure text edits).

## Context

- Flight 3.5 debrief recommended 7 items as forward-looking work for Flight 4. Operator directive: "roll in all of those recommendations." All confirmed-live during flight-design recon.
- Substrate: Flight 3.5 landed `--shell-chamfer` / `--shell-frame-fill` / `--shell-content-fill` / `--shell-frame-glow` / `--shell-chrome-bg` tokens + the alien-dashboard L-bracket on `#main-content` + unified metallic chrome on topbar + sidebar. This leg closes the documentation + reduced-transparency + WCAG-audit follow-ups.
- Pattern continuity: same shape as Flight 3 Leg 01 (token-hygiene + V3b extraction) — autonomous, mechanical, interlocked items closing debrief debt before the flight's main polish work begins.

## Inputs

What exists before this leg runs:

- `tokens.css:394-419` — `@media (prefers-reduced-transparency: reduce)` block. Currently covers glass + bezel tokens. Does NOT cover the new shell tokens (`--shell-chrome-bg`, `--shell-frame-glow`, the topbar sheen inlined at `#app-topbar`).
- `tokens.css` dark theme block (~lines 36-150) + light theme block (~lines 210-345) — both define the shell tokens.
- **`--bg-gradient` consumers** (corrected per design-review — original recon was static-tree-scoped; actual count is THREE consumers + two definitions):
  - `base.css:10` body bg
  - `api.py:1519` OAuth callback inline CSS (silent break risk if missed — `api.py` Python-embedded CSS is invisible to `test_token_definitions.py`'s `.css`-only scan)
  - `agents.md:682` token-table row
  - `agents.md:698` F3.5 composition rule #6 prose (cites the old name)
  - Plus the two definitions at `tokens.css:166` (dark) and `tokens.css:349` (light)
- `base.css` topbar rule (the `#app-topbar` background includes an inlined sheen gradient: `linear-gradient(180deg, rgba(255, 255, 255, 0.06) 0%, transparent 6px)` stacked over `var(--shell-chrome-bg)`).
- `tests/test_design_tokens_a11y.py:152-185` — `test_text_on_color` parametrize block. Currently includes `fg / fg_secondary / fg_muted` on `bg / surface` pairs across both themes. Missing shell-chrome-bg pairs.
- `tests/browser/design_tokens.py` — Python mirror of `tokens.css` token values. Has `DARK` + `LIGHT` dicts but no `shell_chrome_bg` key.
- `agents.md:577-619` — Mission 08 F2 Design Language Layer subsection. Does NOT have an explicit "theme generalization via tokenization" composition rule (the convention is implicit in F3 + F3.5 prose).
- `agents.md` Design system section (`## Design system` at ~line 508) — no "Vibe-leg conventions" subsection exists.
- `agents.md:621` — F3 affordance vocabulary subsection. Does NOT cross-reference the F3.5 placement of topbar `<img>` CLS contract + legacy class-as-JS-handle pattern.
- `tokens.css` `--shell-chrome-bg` definitions (~lines 154-165 dark; ~330-340 light) — no cascade-override caveat comment.

## Outputs

What exists after this leg completes:

- **Reduced-transparency block extended** in `tokens.css:394-419`:
  - New `--shell-topbar-sheen` token (extracted from the inlined gradient in base.css `#app-topbar` rule): rgba sheen gradient at rest, transparent under reduced-transparency.
  - Under `@media (prefers-reduced-transparency: reduce)`: dark + light theme blocks gain overrides for `--shell-chrome-bg` (to its solid base color, no grain layer), `--shell-frame-glow` (to transparent), `--shell-topbar-sheen` (to transparent).
  - `base.css` `#app-topbar` rule consumes `var(--shell-topbar-sheen)` instead of the inlined literal.

- **WCAG audit gap closed**:
  - 4 new parametrizations in `tests/test_design_tokens_a11y.py:152-185` `test_text_on_color`: `(dark, fg, shell_chrome_bg, 4.5)` + `(light, fg, shell_chrome_bg, 4.5)` + `(dark, fg_muted, shell_chrome_bg, 4.5)` + `(light, fg_muted, shell_chrome_bg, 4.5)`.
  - New `shell_chrome_bg` key in `tests/browser/design_tokens.py` `DARK` + `LIGHT` dicts with the base color value (`#20202a` dark, `#d4d8df` light).
  - WCAG audit must pass with all new parametrizations (45 + 4 = 49 total).

- **`--bg-gradient` → `--shell-bg` hard rename**:
  - `tokens.css`: rename `--bg-gradient` to `--shell-bg` in both theme blocks. Delete the old name (no alias).
  - `base.css:10`: update the single consumer to `var(--shell-bg)`.
  - Grep sentinel verifies no stale references.

- **`--shell-chrome-bg` cascade-override comment**:
  - One-line comment at the token's definition site in both themes noting "to strip grain, edit token definition, not via cascade override."

- **agents.md**:
  - F2 subsection (Mission 08 Flight 02 Design Language Layer) gains a new composition rule (likely rule #5 or appended): "Theme generalization via tokenization — when a treatment differs only by value across themes, parametrize through tokens and drop `[data-theme="..."]` selector prefix; selectors stay theme-agnostic." With a short rationale + example reference.
  - New "Vibe-leg conventions" subsection added at the top of the Design system section (between `### Affordance patterns` and `### Mission 08 Flight 02 ...`). Documents two conventions: (a) "Land dark, port light" cadence; (b) "Gallery-as-iteration-substrate" pattern.
  - F3 affordance vocabulary section gains a one-line cross-reference: "Topbar `<img>` CLS contract + legacy class-as-JS-handle pattern documented under F3.5 — see `### Mission 08 Flight 3.5 — Shell Chrome Polish Layer` below."

## Acceptance Criteria

- [ ] `grep -rn "var(--bg-gradient)\|--bg-gradient" the_one/` returns no matches (rename sentinel — **broadened from static-only to whole package** per design-review, catches api.py + agents.md consumers)
- [ ] `grep -n "var(--shell-bg)" the_one/interfaces/web/static/css/base.css` returns 1 match (the body bg consumer)
- [ ] `grep -n "var(--shell-bg)" the_one/interfaces/web/api.py` returns 1 match (the OAuth callback consumer)
- [ ] `grep -nE "^\\s*--bg-gradient" the_one/interfaces/web/static/css/tokens.css` returns no matches (token deleted from both themes; anchor uses `\s*` for indent-resilience)
- [ ] `grep -nE "^\\s*--shell-bg" the_one/interfaces/web/static/css/tokens.css` returns 2 matches (light + dark)
- [ ] `grep -n "shell-bg\|--shell-bg" the_one/agents.md` returns ≥2 matches (token table row + F3.5 rule #6 prose updated)
- [ ] `grep -n "shell-topbar-sheen" the_one/interfaces/web/static/css/tokens.css` returns ≥4 matches (defined in dark + light + suppressed in reduced-transparency dark + light)
- [ ] `grep -n "var(--shell-topbar-sheen)" the_one/interfaces/web/static/css/base.css` returns 1 match (topbar bg consumer)
- [ ] `grep -n "--shell-chrome-bg" the_one/interfaces/web/static/css/tokens.css` shows the cascade-override comment present at definitions (both themes)
- [ ] `grep -E "shell_chrome_bg" tests/test_design_tokens_a11y.py` returns 2 matches (2 parametrizations: dark + light fg-on-chrome-bg; fg_muted variants DROPPED per design-review — light fg_muted = `#64748b` on `#d4d8df` = 3.33:1, FAILS body AA; documented as Known Issue)
- [ ] `grep -n "shell_chrome_bg" tests/browser/design_tokens.py` returns 2 matches (DARK + LIGHT entries)
- [ ] `grep -n "Theme generalization via tokenization\|Vibe-leg conventions\|see F3.5\|see.*F3.5" the_one/agents.md` returns ≥3 matches (all 3 agents.md additions present)
- [ ] WCAG audit passes with 47/47: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 30` shows 47 passed (45 prior + 2 new dark/light fg-on-shell_chrome_bg; muted variants dropped per design-review)
- [ ] Narrow test gate passes: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30` returns 56/56 (or 60/60 if test_token_definitions has new token counts — verify)
- [ ] `make rebuild` clean
- [ ] Visual smoke check (Flight Director runs `make rebuild` + page-loads the app in dark and light to verify nothing visually regressed)

## Verification Steps

1. **Rename sentinels** (3 greps):
   ```
   grep -rn "var(--bg-gradient)" the_one/interfaces/web/static/
   grep -n "^    --bg-gradient" the_one/interfaces/web/static/css/tokens.css
   grep -c "var(--shell-bg)" the_one/interfaces/web/static/css/base.css
   ```
   First two return no matches; third returns 1.

2. **Topbar sheen extraction sentinels** (2 greps):
   ```
   grep -c "shell-topbar-sheen" the_one/interfaces/web/static/css/tokens.css
   grep -c "var(--shell-topbar-sheen)" the_one/interfaces/web/static/css/base.css
   ```
   First returns ≥4; second returns 1.

3. **WCAG audit** (in container):
   ```
   docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 30 | tail -3
   ```
   Expected: 49/49 (existing 45 + 4 new shell_chrome_bg).

4. **Narrow gate** (in container):
   ```
   docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30
   ```
   Expected: 56-60 passed (test_token_definitions count may change if it counts token names; verify against last run baseline).

5. **agents.md grep sentinels**:
   ```
   grep -n "Theme generalization via tokenization" the_one/agents.md
   grep -n "Vibe-leg conventions" the_one/agents.md
   grep -nE "see.{0,20}F3\\.5|see Mission 08 Flight 3\\.5" the_one/agents.md
   ```
   First 2 return ≥1; third returns ≥1 (cross-reference).

6. **Visual smoke** (Flight Director runs post-implementation):
   ```
   make rebuild
   ```
   Then load app in browser — dark theme renders identically (body bg = chrome bg via renamed token; topbar sheen via renamed token); light theme same. No regression.

## Implementation Guidance

**Order matters** — token rename FIRST (so subsequent edits in tokens.css use the new name; otherwise we'd add `--bg-gradient` overrides to the reduced-transparency block, then have to rename them).

1. **Audit current state** (sentinel sweep before any edits):
   ```
   grep -rn "var(--bg-gradient)" the_one/interfaces/web/static/
   grep -n "^    --bg-gradient\|^    --shell-chrome-bg\|^    --shell-frame-glow" the_one/interfaces/web/static/css/tokens.css
   ```
   Confirm `--bg-gradient` has exactly 1 consumer (`base.css:10`). Confirm shell tokens defined in both themes.

2. **Rename `--bg-gradient` → `--shell-bg`** — 5 sites (corrected per design-review):
   - `tokens.css:166` dark theme + `:349` light theme definitions: rename. Token VALUE unchanged (still `var(--shell-chrome-bg)`). Delete old name; no alias.
   - `base.css:10` body bg consumer: `var(--bg-gradient)` → `var(--shell-bg)`.
   - `api.py:1519` OAuth callback inline CSS: `var(--bg-gradient)` → `var(--shell-bg)`. **Important** — `test_token_definitions.py` scans only `.css` files; Python-embedded CSS is invisible to it. Easy to miss without the broadened grep.
   - `agents.md:682` token-table row: rename the token name.
   - `agents.md:698` F3.5 composition rule #6 prose: update the inline `--bg-gradient` reference to `--shell-bg`.

3. **Extract topbar sheen into a token**:
   - In `tokens.css` dark theme block, add: `--shell-topbar-sheen: linear-gradient(180deg, rgba(255, 255, 255, 0.06) 0%, transparent 6px);` (the same value currently inlined in base.css `#app-topbar` rule).
   - In `tokens.css` light theme block, add: same value (the white sheen works on both gunmetal and silver chrome per the Flight 3.5 implementation note).
   - In `base.css`, update `#app-topbar` rule to consume `var(--shell-topbar-sheen)` instead of the inlined gradient. The topbar `background` becomes a stack: `var(--shell-topbar-sheen), var(--shell-chrome-bg)`.

4. **Add cascade-override comment to `--shell-chrome-bg`** definitions in both themes (place above the token line):
   ```
   /* To strip the grain layer (e.g., under reduced-transparency), edit
      this token definition or use the @media block below — do NOT try to
      override via cascade, as the value is a layered background and the
      `repeating-linear-gradient(...)` cannot be selectively suppressed. */
   ```

5. **Extend reduced-transparency block** (`tokens.css:394-419`):
   - In the dark theme override block, add:
     ```
     --shell-chrome-bg: #20202a;  /* Strip grain; keep solid base. */
     --shell-frame-glow: transparent;
     --shell-topbar-sheen: none;
     ```
   - In the light theme override block, add:
     ```
     --shell-chrome-bg: #d4d8df;  /* Strip grain; keep solid base. */
     --shell-frame-glow: transparent;
     --shell-topbar-sheen: none;
     ```

6. **Update `tests/browser/design_tokens.py`** — add `shell_chrome_bg` key to both `DARK` and `LIGHT` dicts:
   ```python
   DARK: dict[str, str] = {
       ...existing...
       "shell_chrome_bg": "#20202a",
   }
   LIGHT: dict[str, str] = {
       ...existing...
       "shell_chrome_bg": "#d4d8df",
   }
   ```

7. **Add WCAG parametrizations** in `tests/test_design_tokens_a11y.py:152-185` `test_text_on_color`:
   - Add 2 rows to the parametrize block (fg_muted variants DROPPED per design-review computation — see Edge Cases):
     ```python
     ("dark",  "fg", "shell_chrome_bg", 4.5),
     ("light", "fg", "shell_chrome_bg", 4.5),
     ```
   - Computed contrasts (design-review-verified):
     - Dark: `#e0e0e0` on `#20202a` = **12.22:1** ✓ passes 4.5
     - Light: `#0f172a` on `#d4d8df` = **12.49:1** ✓ passes 4.5
     - Dark fg_muted: `#a8a8a8` on `#20202a` = 6.79:1 — passes but **deferred** (latent risk only; muted-text-on-chrome not currently in production)
     - Light fg_muted: `#64748b` (slate-500, NOT `#94a3b8`) on `#d4d8df` = **3.33:1** — **FAILS body AA 4.5**, passes large/UI 3.0. Document as Known Issue (light theme has no muted-text-on-chrome consumer today; if Studio's polish work introduces one, audit must be revisited).
   - Add a comment near the new parametrizations referencing the deferred muted variants + reason.

8. **agents.md updates** (in this order — the F2 lift adds a rule, the vibe-leg conventions adds a subsection, the F3 cross-ref is a 1-line touch):
   - F2 lift: in `agents.md` Mission 08 F2 Design Language Layer subsection, find the composition rules numbered list (rules 1-4 per design-review verification — F3.5 has its OWN composition rules 1-6 at line 686, separately). Append as rule #5: `**Theme generalization via tokenization.** When a chrome/component treatment differs only by value across themes, parametrize through tokens and drop the \`[data-theme="..."]\` selector prefix. Selectors stay theme-agnostic; tokens carry theme. Example: F3.5's shell rules (\`#main-content\`, \`#app-topbar\`, \`#app-sidebar\`) apply in both themes with values driven entirely by per-theme tokens.`
   - Vibe-leg conventions: insert a new `### Vibe-leg conventions` subsection right after `### Affordance patterns` (before `### Mission 08 Flight 02 ...`). Content:
     ```
     ### Vibe-leg conventions

     Patterns for running interactive vibe legs efficiently:

     - **"Land dark, port light."** For vibe legs translating symmetrically across themes, iterate to operator-confirmed dark theme first (the aesthetic anchor); port to light at leg close as a value-swap exercise. Avoids 2× decision load during operator-bandwidth bottleneck. Established in Flight 3.5 (shell chrome). Use when the aesthetic translates symmetrically — if light requires structurally different decisions (not just value swaps), parallel iteration is necessary.

     - **Gallery-as-iteration-substrate.** Build vibe variants as `.iter-*`-prefixed gallery samples in the design-language gallery (`#admin/design-language`). Operator picks + hybridizes from side-by-side comparison. Variant code stays in the gallery as reference for the rest of the vibe leg, then ripped at flight-close via the iteration-cleanup grep. Cleaner than direct-iterating on production surfaces. Established in Flights 2 + 3 + 3.5.
     ```
   - F3 cross-reference: in `agents.md` Mission 08 F3 Administration Polish Layer subsection, find the "New affordance vocabulary entries" list or affordance-vocabulary block. Append one bullet: `**Topbar \`<img>\` CLS contract + legacy class-as-JS-handle pattern**: documented under F3.5 — see \`### Mission 08 Flight 3.5 — Shell Chrome Polish Layer\` below.`

9. **Run verification gates** (in container):
   - WCAG audit: expect 49/49 (45 prior + 4 new).
   - Narrow gate: expect 56/56 (no behavioral change).
   - `make rebuild` clean.
   - Flight Director visually verifies app in both themes (dark + light) after rebuild — body bg renders as chrome; topbar sheen visible at top.

10. **Update flight log** with leg progress + verification results.

## Edge Cases

- **`fg_muted` light theme contrast on shell_chrome_bg** (corrected per design-review): light `--fg-muted` is `#64748b` (slate-500, NOT `#94a3b8` as originally cited). On `#d4d8df` it computes to **3.33:1** — FAILS body AA 4.5, passes large/UI 3.0. Decision: **drop both fg_muted variants** (dark fg_muted passes but is speculative coverage; light fails). Add a one-line comment in `test_design_tokens_a11y.py` near the new parametrizations: "muted-text-on-chrome variants deferred — no production consumer today; light pair would fail (3.33:1)." If Studio's polish work introduces muted-on-chrome text, the audit must be revisited.
- **Reduced-transparency literals must stay in sync** with `--shell-chrome-bg` base color: the suppression block re-encodes `#20202a` (dark) / `#d4d8df` (light) as solid-color overrides. If the base color of `--shell-chrome-bg` ever retunes (e.g., future palette swap), these literals MUST update in lockstep. Add a comment at each override site noting "keep in sync with --shell-chrome-bg base color (see token definition above)."
- **Token rename: check serving model** — `make rebuild` should re-serve `tokens.css` + `base.css`. Verify no stale cached version on disk in a container layer.
- **Topbar sheen value preservation**: extract the EXACT value from the current `base.css` topbar rule. Don't introduce a subtle value drift during extraction.
- **agents.md F2 rule insertion**: the F2 subsection's composition rules are numbered (1-6 from Flight 2 Leg 06 + Flight 3.5 added more). Append as the next number; don't disrupt prior numbering.
- **Visual smoke after token rename**: body bg = `var(--shell-bg)` = `var(--shell-chrome-bg)` = chrome surface. Should look IDENTICAL pre/post rename. If it doesn't, something else broke.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — `--bg-gradient` rename to `--shell-bg` (both themes); new `--shell-topbar-sheen` token (both themes); `--shell-chrome-bg` cascade-override comment (both themes); reduced-transparency block extended with 3 shell-token overrides per theme
- `the_one/interfaces/web/static/css/base.css:10` — body bg consumer renamed
- `the_one/interfaces/web/static/css/base.css` `#app-topbar` rule — sheen extracted to token reference
- `tests/browser/design_tokens.py` — `shell_chrome_bg` key in DARK + LIGHT dicts
- `tests/test_design_tokens_a11y.py:152-185` — 1-4 new parametrizations on shell_chrome_bg
- `the_one/agents.md` — 3 documentation edits (F2 lift; new vibe-leg-conventions subsection; F3 cross-reference)
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-log.md` — append leg progress entry
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/legs/01-prep-and-debrief-debt-close.md` — status `planning` → `in-flight` → `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All 10 acceptance criteria verified
- [ ] WCAG audit passes 49/49 (or 47/47 if fg_muted variants deferred per edge case)
- [ ] Narrow gate passes
- [ ] Update flight log with leg progress
- [ ] Set this leg's status to `landed` (NOT `completed`; commit step at flight close sets `completed`)
- [ ] Do NOT check off this leg in flight.md (deferred to commit step)
- [ ] Do NOT commit (deferred per agentic-workflow's standard pattern — operator commits per-leg per Flight 3+ cadence; Flight Director handles)
- [ ] Signal `[HANDOFF:review-needed]`

## Citation Audit

7 citations verified against current code at leg design time (commit `c0a716c` on `flight/04-studio-polish` branched from main):

- `tokens.css:394-419` — `@media (prefers-reduced-transparency: reduce)` block. Verified; covers glass + bezel; does NOT cover shell tokens.
- `tokens.css` dark theme `--bg-gradient: var(--shell-chrome-bg);` + light theme same — verified (Flight 3.5 set this).
- `base.css:10` — `body { ... background: var(--bg-gradient); ... }` — verified single consumer (no other consumers in `the_one/interfaces/web/static/`).
- `tests/test_design_tokens_a11y.py:152-185` — `test_text_on_color` parametrize block — verified; existing parametrizations don't include shell_chrome_bg.
- `tests/browser/design_tokens.py` — DARK + LIGHT dicts — verified; no shell_chrome_bg key today.
- `agents.md:577-619` F2 subsection — verified; no explicit "theme generalization via tokenization" rule (convention implicit).
- `agents.md:621` F3 subsection — verified; no F3.5 cross-reference.

All citations clean; no drift since flight-design recon (yesterday). The leg is ready to implement.
