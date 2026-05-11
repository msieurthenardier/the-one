# Leg: 03-cyan-class-rename

**Status**: completed
**Flight**: [Brand Foundation](../flight.md)

## Objective

Rename the misnamed `.btn-filled-cyan` and `.btn-outlined-cyan` CSS class names to color-agnostic semantic equivalents (`.btn-filled-primary` / `.btn-outlined-primary`) across every consumer, and sweep stale "cyan" / "NEXUS" framing out of design-system documentation and CSS in-file comments so future readers aren't confused by a vocabulary that no longer matches the rendered UI.

## Context

- Leg 3 of 5 in Flight 1 (Brand Foundation). Legs 01 and 02 landed (uncommitted on `flight/01-brand-foundation` branch): the mascot favicon + topbar icon ship; the `--accent` token retuned from cyan to violet/purple in both themes. The running app already renders purple — but every primary button still has class names like `btn-filled-cyan`, which is now a lie.
- The CSS rule definitions for both classes already route through `var(--accent)` (see `the_one/interfaces/web/static/css/components.css:273-302`); only the *names* lie. Internal-CSS uses `var(--accent)` so the rename is purely a `class="..."` attribute / selector rewrite.
- Class-rename strategy from the flight spec: hard cutover, no temporary `.btn-filled-cyan` CSS alias. All consumers are in-repo; aliases would let future code grep "btn-filled-cyan" and find stale references indefinitely.
- Verification gate from the flight spec: `grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/` must return zero hits.
- Documentation sweep: in addition to class names, this leg cleans stale "NEXUS-style cyan" / "cool-tinted off-white, coordinates with cyan accent" / "cyan-700" / "Outlined-cyan" / "Filled-cyan CTA" prose in `tokens.css`, `components.css`, `agents.md`. The leg-02 review flagged `agents.md` design-system prose at lines ~637 and ~684-685 specifically (audit-retune narrative pinning old hex values, focus-ring section saying "cyan glow") that need updating; this leg owns that work.
- Tests do NOT pin the cyan class names (verified at leg design time: `grep -rn "btn-filled\|btn-outlined" tests/` returns zero hits). Browser tests address buttons by `data-testid` attributes. So the rename has no test consumer to update — it's purely a source-code sweep.
- Current grep totals at design time: 62 cyan-class references across 14 files. The leg's verification step re-runs the grep at implementation time so the count is up-to-date when the rename starts.

## Inputs

Files that must exist (verified at design time via `grep -rln`):
- **CSS** (4 files):
  - `the_one/interfaces/web/static/css/components.css` — canonical rule definitions for `.btn-filled-cyan` (line 289) and `.btn-outlined-cyan` (line 273), plus intra-file comment references at lines 322-323, 326-327, 714, 728
  - `the_one/interfaces/web/static/css/admin.css` — comment references at lines 59, 71, 96, 459, 463
  - `the_one/interfaces/web/static/css/studio.css:38-40 — ".area-studio .tool-actions .btn-outlined-cyan { ... }"` — per-area size override rule
  - `the_one/interfaces/web/static/css/tokens.css` — stale in-file comments at lines 3, 68, 115, 138, 140, 183 referencing "NEXUS-style cyan", "--accent moves to cyan", "coordinates with cyan accent", "cyan-700", "cyan tint"; NOTE: line 80 `--badge-filesystem: #008b8b; /* dark cyan */` is a literal color description for a non-brand token (filesystem badge color is genuinely a dark cyan hex) — LEAVE AS-IS
- **JS** (10 files, ~35 class-name occurrences total at design time):
  - `the_one/interfaces/web/static/js/dialog.js`
  - `the_one/interfaces/web/static/js/areas/chat.js`
  - `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`
  - `the_one/interfaces/web/static/js/areas/admin/provider-models.js`
  - `the_one/interfaces/web/static/js/areas/admin/tools-editor.js`
  - `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`
  - `the_one/interfaces/web/static/js/areas/studio/general-tab.js`
  - `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`
  - `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`
  - `the_one/interfaces/web/static/js/areas/studio/tools-tab.js`
- **Docs**:
  - `the_one/agents.md` — design-system surface with at least 8 distinct "cyan" hits (per design-review grep): "Affordance Patterns" section (lines ~541-565) names patterns "Outlined-cyan" and "Filled-cyan CTA"; "Color contrast" audit-retune narrative (lines ~633-645) pins old hex values; focus-ring section (lines ~680-692) describes "`#22d3ee` outline + cyan glow"; plus uncited hits at lines ~521 ("cyan-accented gradient" in `.chat-no-providers` description), ~529 ("outlined-cyan" lowercase prose), ~622 (WCAG contrast table: "PASS (retuned cyan-600 → cyan-700)"), ~852 ("Active area accent: ... → cyan `::before` left-border stripe"), ~1015 ("Two variants, both using `var(--accent)` (cyan)")
  - `CLAUDE.md` (repo root) — line ~89 says "NEXUS-style cyan accent" framing the design system; same stale lie as the others, in scope for this leg
  - **Out of scope here, deferred to Leg 04**: `the_one/interfaces/web/api.py:1478` docstring ("the rest of the-one — dark-mode cyan-accent palette, Geist /") contains both a brand-text reference ("the rest of the-one") AND a cyan-palette reference ("dark-mode cyan-accent palette"). Leg 04 (brand-text sweep) rewrites the whole comment in one edit — handling it here would create a re-edit collision. Verification grep in this leg excludes `api.py:1478`.

State that must be true:
- Legs 01 and 02 landed (uncommitted on `flight/01-brand-foundation`)
- Container is running (`make up` if not)
- `grep -rn "btn-filled\|btn-outlined" tests/` returns zero hits (verified at design time)

## Outputs

Files modified:
- **CSS** (4 files): all `.btn-filled-cyan` → `.btn-filled-primary` and `.btn-outlined-cyan` → `.btn-outlined-primary` selector and comment occurrences renamed; stale cyan / NEXUS comments in `tokens.css` and `components.css` updated to the new color family or annotated as historical
- **JS** (10 files): all `class="... btn-filled-cyan ..."` and `class="... btn-outlined-cyan ..."` string occurrences renamed
- **Docs** (`the_one/agents.md`): affordance-pattern names "Outlined-cyan" / "Filled-cyan CTA" renamed to "Outlined primary" / "Filled primary CTA"; "Color contrast" audit-retune narrative refreshed to reflect the violet retune (or annotated as historical); focus-ring section refreshed to describe the new `--accent` hex values

Files NOT modified:
- `tests/` — no test pins these class names; verified
- `tokens.css:80` `--badge-filesystem: #008b8b; /* dark cyan */` — literal non-brand color description, leave alone

State changes:
- The codebase's CSS class vocabulary becomes color-agnostic: future palette changes are token-only edits, no JS HTML-string rewrites required
- Design-system documentation accurately reflects the running UI (purple primary, not "NEXUS cyan")

## Acceptance Criteria

- [ ] `grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/` returns **zero hits** (the canonical completeness check)
- [ ] `grep -rn "btn-filled-primary\|btn-outlined-primary" the_one/` returns at least 60 hits (corresponding to the renames)
- [ ] `the_one/interfaces/web/static/css/components.css` has `.btn-filled-primary` and `.btn-outlined-primary` rule definitions where `.btn-filled-cyan` and `.btn-outlined-cyan` used to live; rule bodies are unchanged (still reference `var(--accent)`)
- [ ] `the_one/interfaces/web/static/css/studio.css` `.area-studio .tool-actions .btn-outlined-cyan` selector becomes `.area-studio .tool-actions .btn-outlined-primary`
- [ ] All 10 JS files have their `class="... btn-{filled,outlined}-cyan ..."` strings rewritten to the `-primary` form
- [ ] `the_one/agents.md` "Affordance Patterns" section: pattern names "Outlined-cyan" / "Filled-cyan CTA" renamed to "Outlined primary" / "Filled primary CTA"; surrounding prose references updated
- [ ] `the_one/agents.md` "Color contrast (WCAG AA)" section: audit-retune narrative no longer pins old cyan hex values as the current state — either rewritten to describe the violet retune, or annotated as "[historical: pre-Mission-08]"
- [ ] `the_one/agents.md` focus-ring section ("In dark this resolves to a `#22d3ee` outline + cyan glow ..."): updated to describe the new `--accent` hex resolution (`#a78bfa` outline in dark, `#6d28d9` in light) and drop "cyan" terminology
- [ ] `the_one/agents.md` additional uncited "cyan" hits at lines ~521, ~529, ~622, ~852, ~1015 all swept (refreshed to violet OR annotated as historical, per implementer judgment per line)
- [ ] `CLAUDE.md` line ~89 ("NEXUS-style cyan accent" description) refreshed to drop the cyan/NEXUS framing or annotate as historical Mission-08 context
- [ ] `the_one/interfaces/web/static/css/tokens.css` stale "NEXUS-style cyan", "--accent moves to cyan", "coordinates with cyan accent", "cyan-700", "cyan tint" comments at lines 3, 68, 115, 138, 140, 183 are updated to the new color family OR explicitly annotated as historical context
- [ ] `grep -rin "nexus" the_one/ CLAUDE.md` returns zero hits (or only intentional historical-context annotations)
- [ ] `grep -rin "cyan" the_one/ CLAUDE.md` returns only: the deliberate `/* dark cyan */` literal description at `tokens.css:80` for `--badge-filesystem`, the deferred `api.py:1478` line (handled by Leg 04), any deliberate historical-context annotations the implementer chose to retain, and no living references to the app's primary accent as "cyan"
- [ ] `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -x -q --timeout 10` exits 0 (no regression — the rename is name-only, no token values or contrast pairs changed)
- [ ] `make verify-serving` exits 0 (admin sub-modules still return 200; rebranded buttons render correctly)
- [ ] Visual sanity (after `make rebuild`, optional but recommended): primary buttons in Admin (Save provider, Refresh, Pull Model), Studio (Save agent, Back), Chat (Login required), and dialog modals all render as purple — confirming the new class names properly inherit the CSS rules

## Verification Steps

- **Completeness greps** (run after the rename is applied):
  ```
  grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/
  # Expect: no output, exit 1 (grep returns 1 when nothing matches)
  grep -rn "btn-filled-primary\|btn-outlined-primary" the_one/ | wc -l
  # Expect: 60+ matches (the renamed call sites)
  ```
- **CSS rule definitions intact**:
  ```
  grep -A3 "^\s*\.btn-filled-primary\s*{" the_one/interfaces/web/static/css/components.css
  grep -A3 "^\s*\.btn-outlined-primary\s*{" the_one/interfaces/web/static/css/components.css
  # Expect: rules exist; body still uses var(--accent)
  ```
- **Stale-cyan-vocabulary check**:
  ```
  grep -in "cyan" the_one/interfaces/web/static/css/ the_one/agents.md | grep -v "badge-filesystem.*dark cyan" | grep -v "historical"
  # Expect: empty (or only intentional historical comments the implementer documents)
  grep -in "nexus" the_one/interfaces/web/static/css/ the_one/agents.md
  # Expect: empty
  ```
- **Test gate**:
  ```
  docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -x -q --timeout 10
  # Expect: exit 0
  ```
- **Serving check**: `make verify-serving` → exit 0
- **Visual spot-check (after `make rebuild`)**: load `http://localhost:8484/`, navigate to any page with a Save/Cancel/Back button cluster (Admin → LLM Providers → edit any provider, or Studio → Agents → edit any agent); buttons should render in the new purple-accent style — confirming the renamed classes inherit the violet `--accent` token

## Implementation Guidance

1. **Re-grep current state** (line numbers may have drifted since leg design — design review found components.css selector lines shifted ~+8 from cited values):
   ```
   grep -rln "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/
   grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/ | wc -l
   grep -rin "cyan\|nexus" the_one/ CLAUDE.md | grep -v "badge-filesystem.*dark cyan"
   ```
   Record the count in the flight log so completeness can be verified by deltas. The cited line numbers in this leg's Inputs section are anchors from design time; treat them as approximate and trust the grep.

2. **CSS rename** (4 files):
   - `the_one/interfaces/web/static/css/components.css` — rename selector definitions at lines 273 (`.btn-outlined-cyan {`) and 289 (`.btn-filled-cyan {`); update all in-file `:hover` / `:focus-visible` / `:disabled` modifier rules to match; update comment references at lines 322-327, 714, 728
   - `the_one/interfaces/web/static/css/admin.css` — update comment references at lines 59, 71, 96, 459, 463
   - `the_one/interfaces/web/static/css/studio.css` — rename selector at line 40 (`.area-studio .tool-actions .btn-outlined-cyan`) and update the descriptive comment at line 38
   - `the_one/interfaces/web/static/css/tokens.css` — clean up stale-cyan in-file comments:
     - Line 3: `Dark-theme values realized in leg 03 (NEXUS-style cyan + glow).` → update to historical framing (e.g., `... (originally NEXUS-style cyan; retuned to GleepGlorp violet in Mission 08).`) OR drop the cyan/NEXUS framing entirely
     - Line 68: `NOTE: --badge-openai stays at #4a9eff even though --accent moves to cyan.` → factually wrong post-leg-02; rewrite to e.g. `NOTE: --badge-openai stays at #4a9eff regardless of --accent palette; provider badges are theme- and accent-stable.`
     - Line 115: `/* surfaces — cool-tinted off-white, coordinates with cyan accent */` → e.g. `/* surfaces — cool-tinted off-white; coordinates with the primary accent */`
     - Lines 138, 140: `cyan-700` / `cyan-600` framing in the `--accent` comment block — rewrite to reflect violet-700 OR annotate as historical
     - Line 183: `composites cyan tint + dark elevation` → `composites accent tint + dark elevation`

3. **JS rename** (10 files): in each, replace `btn-filled-cyan` → `btn-filled-primary` and `btn-outlined-cyan` → `btn-outlined-primary`. Use replace-all per file (the strings only ever appear inside `class="..."` HTML-string concatenations — no risk of false-positive matches).
   - The simplest invocation is `sed -i 's/btn-filled-cyan/btn-filled-primary/g; s/btn-outlined-cyan/btn-outlined-primary/g'` per file, OR per-file Edit tool calls with `replace_all: true`

4. **Docs sweep** (`the_one/agents.md` + `CLAUDE.md`):
   - "Affordance Patterns" section (`agents.md` ~541-565): rename "Outlined-cyan" → "Outlined primary" and "Filled-cyan CTA" → "Filled primary CTA"; update surrounding prose so the pattern descriptions reference `--accent` semantically rather than by hue
   - "Color contrast (WCAG AA)" section (`agents.md` ~633-645): the audit-retune narrative pins old cyan hex values (`#0891b2`, `#0e7490`, "cyan-600", "cyan-700") as the current state. Either rewrite to reflect the violet retune (`#6d28d9` light, `#a78bfa` dark per Leg 02) OR add a leading note like `[Mission 08 update: palette retuned from cyan to violet. The hex values below are historical; see Leg 02 of Flight 01 of Mission 08 for current values.]`. The latter is lower-risk because the surrounding prose was originally written about the cyan-tuning iteration and would need substantial rewriting to map onto the violet retune.
   - Focus-ring section (`agents.md` ~680-692): `"In dark this resolves to a \`#22d3ee\` outline + cyan glow; in light it resolves to a \`#0e7490\` outline + cyan glow."` → `"In dark this resolves to a \`#a78bfa\` outline + violet glow; in light it resolves to a \`#6d28d9\` outline + violet glow."` (or whatever the post-Leg-02 final values are). Both meet 3:1 against adjacent surfaces (computed at leg 02 design time).
   - **Additional uncited hits in `agents.md`** flagged at design review — sweep these too:
     - Line ~521: "cyan-accented gradient" describing `.chat-no-providers` — refresh to "primary-accented gradient" or "violet-accented gradient"
     - Line ~529: lowercase "outlined-cyan" prose — refresh to "outlined-primary"
     - Line ~622: WCAG contrast table cell "PASS (retuned cyan-600 → cyan-700)" — annotate as historical or rewrite to reflect violet retune
     - Line ~852: "Active area accent: ... → cyan `::before` left-border stripe" — refresh to "violet" / "primary accent"
     - Line ~1015: "Two variants, both using `var(--accent)` (cyan)" — drop the "(cyan)" parenthetical or rewrite to "(primary accent)"
   - `CLAUDE.md` line ~89: "NEXUS-style cyan accent" framing — refresh to "GleepGlorp violet accent" or drop the "NEXUS-style" reference; this is project-level documentation that should match the rendered UI
   - General sweep: `grep -rin "cyan\|nexus" the_one/ CLAUDE.md` — for any remaining hits beyond the enumeration above, decide per-line: (a) refresh to violet, (b) annotate as historical, or (c) leave if it's a non-brand reference (e.g., `--badge-filesystem` literal "dark cyan" hex description at `tokens.css:80`, or the deferred `api.py:1478` handled by Leg 04). Record the policy decision in the flight log so reviewers can audit.

5. **Run the audit and serving check**:
   ```
   docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -x -q --timeout 10
   make verify-serving
   ```

6. **Re-grep for completeness**:
   ```
   grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/    # must be empty
   grep -rn "btn-filled-primary\|btn-outlined-primary" the_one/ | wc -l    # ≥60
   grep -rin "cyan" the_one/ CLAUDE.md | grep -v "badge-filesystem\|historical\|Mission 08 update\|api.py:1478"    # only deliberate retentions; api.py:1478 deferred to Leg 04
   grep -rin "nexus" the_one/ CLAUDE.md    # must be empty (or only deliberate historical annotations)
   ```

7. **Visual rebuild + spot-check (optional)**: `make rebuild`; load the running app; verify a Save/Cancel button cluster on any editor page renders purple correctly.

## Edge Cases

- **Mixed-content CSS class strings**: JS strings like `class="btn-filled-cyan refresh-btn admin-pf-pull-go"` are multi-class; the rename touches ONLY the cyan token, leaving sibling classes intact. Per-file `replace_all` is safe because the cyan token only ever appears inside such class strings (no false-positive substring matches — verified by the design-time grep listing every occurrence in HTML-string concat contexts).
- **Comment-only file changes**: tokens.css and admin.css have several lines where the rename is to *comments*, not selectors. Comments don't affect runtime — but stale comments are debt. The leg includes them in scope so the codebase reads consistently. Optional: implementer may skip the most narrative comments in admin.css (lines 59, 71, 96 are explanatory comments about the canonical button cluster pattern; refreshing them is hygiene, not correctness).
- **agents.md narrative rewrite risk**: the audit-retune narrative was originally about the cyan tuning iteration. A wholesale rewrite to violet creates content gaps (no equivalent iteration story for violet, since Leg 02's starter palette passed audit on first run). The "annotate as historical" path (option b in implementation guidance step 4) is the conservative choice — keep the original narrative as a story of how the cyan iteration went, add a leading note pointing at Mission 08 for current values. Capture the choice in the flight log.
- **`tokens.css:80` `--badge-filesystem: #008b8b; /* dark cyan */`**: do NOT rename. The comment is a literal hex-color description for a tool-category badge that is intentionally a dark cyan hex value; it's not framing the primary accent as cyan. Leave the comment in place; verification grep filters this match out.
- **Test gate cannot regress on rename**: the WCAG audit and token-definitions tests reference token NAMES (which are unchanged) and hex VALUES (set in Leg 02, also unchanged). The rename of CSS class names does not exercise any test parametrization. Confidence: high that the test gate stays green.

## Files Affected

- `the_one/interfaces/web/static/css/components.css` — rule rename + comment refresh
- `the_one/interfaces/web/static/css/admin.css` — comment refresh
- `the_one/interfaces/web/static/css/studio.css` — selector rename + comment refresh
- `the_one/interfaces/web/static/css/tokens.css` — stale in-file comment cleanup (lines ~3, 68, 115, 138, 140, 183)
- 10 JS files (listed in Inputs) — `class="..."` string updates
- `the_one/agents.md` — affordance-pattern names, audit-retune narrative annotation, focus-ring section, and the 5 additional uncited hits at lines ~521, ~529, ~622, ~852, ~1015
- `CLAUDE.md` (repo root) — line ~89 "NEXUS-style cyan accent" framing

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] WCAG audit + token-definitions green; `make verify-serving` exit 0
- [ ] Flight log entry under `## Leg Progress` records: pre-rename grep count, post-rename grep count (must be 0 for old names, ≥60 for new names), which agents.md narrative-cleanup option was chosen (rewrite vs annotate-as-historical), any deliberate cyan-comment retentions and why
- [ ] Set leg status to `landed` in this file's header
- [ ] Signal `[HANDOFF:review-needed]` — orchestrator commits at flight-end; do NOT commit or signal `[COMPLETE:leg]`

---

## Citation Audit

11 citations verified against current code at leg design time:

| Citation | Verified |
|---|---|
| `components.css:273 — ".btn-outlined-cyan {"` | OK (rule definition at line 273) |
| `components.css:289 — ".btn-filled-cyan {"` | OK (rule definition at line 289) |
| `components.css:322-327, 714, 728 — cyan-class comment references` | OK |
| `admin.css:59, 71, 96, 459, 463 — cyan-class comment references` | OK |
| `studio.css:38-40 — ".area-studio .tool-actions .btn-outlined-cyan { ... }"` | OK |
| `tokens.css:3 — "Dark-theme values realized in leg 03 (NEXUS-style cyan + glow)"` | OK |
| `tokens.css:68 — "NOTE: --badge-openai stays ... even though --accent moves to cyan"` | OK |
| `tokens.css:115, 138, 140, 183 — stale cyan/cyan-700 framing` | OK |
| `tokens.css:80 — "--badge-filesystem: #008b8b; /* dark cyan */"` (deliberate non-brand reference; leave) | OK |
| `agents.md:633-645 — Color contrast audit-retune narrative pinning old hex` | OK |
| `agents.md:680-692 — focus-ring section "#22d3ee outline + cyan glow"` | OK |
| `tests/ — no cyan-class pins (verified zero hits)` | OK |
| `agents.md ~521, ~529, ~622, ~852, ~1015 — additional uncited "cyan" hits` | OK (Developer found at design review round 1) |
| `CLAUDE.md ~89 — "NEXUS-style cyan accent"` | OK (Developer found at design review round 1; added to scope) |
| `api.py:1478 — "dark-mode cyan-accent palette"` | OK (deferred to Leg 04 brand-text sweep, where the same comment also gets "the rest of the-one" rebranded) |

Design-review revisions applied (Developer review, round 1):
- Medium: components.css selector line numbers drifted +8 since flight design; step-1 re-grep covers this, note added.
- Medium: enumerated 5 additional `agents.md` "cyan" hits the leg under-counted (lines 521, 529, 622, 852, 1015).
- Medium: added `CLAUDE.md:89` to docs sweep scope (same "NEXUS-style cyan accent" lie).
- Medium: explicitly deferred `api.py:1478` to Leg 04 (avoids re-edit collision; Leg 04 rewrites the same comment for brand-text).
- Low: verification grep scope broadened from `static/css/ agents.md` to `the_one/ CLAUDE.md` to catch the wider docs surface.
