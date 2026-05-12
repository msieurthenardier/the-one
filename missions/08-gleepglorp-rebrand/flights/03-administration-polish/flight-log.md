# Flight Log: Administration Polish

**Flight**: [Administration Polish](flight.md)

## Summary

Flight log for Flight 3 of Mission 08 (GleepGlorp Rebrand). Flight design completed on 2026-05-11; awaiting kickoff via `/agentic-workflow flight 03 for the-one mission 08`.

---

## Reconnaissance Report

Source artifact: Flight 2 debrief (`missions/08-gleepglorp-rebrand/flights/02-design-language/flight-debrief.md`). Four code-cited items carried forward into Flight 3 scope; verified mechanically against current code (commit `2f3b51c` on main) during flight design.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `tokens-section.js:29-33` undefined `--panel-radius-md` / `-lg` references | confirmed-live | `tokens-section.js:30-32` references `--panel-radius-sm` / `-md` / `-lg`; only `-sm` is defined in `tokens.css:132, :268`. Line drift: actual location is `:30-32`, not `:29-33`. Citation repaired in flight artifact. | Fix in Leg 01. |
| `--panel-radius-sm` equals `--panel-radius` (both 6px) | confirmed-live | `tokens.css:131-132` (light) and `:267-268` (dark) define both as `6px`. | Retune `--panel-radius-sm` to `4px` in Leg 01 for actual hierarchy. |
| `--panel-shadow-glow` is dead token | **misclassified — actually live** | Defined at `tokens.css:135, :271`. Comment-references at `components.css:613` and the **stale mention inside the `--glass-bg` comment block at `tokens.css:60`** (Architect surfaced). **AND a live consumer at `api.py:1535`** (Leg 01 design-review Developer surfaced — Flight 2 debrief recon scoped to `static/` and missed this). The Flight 2 debrief misclassified the token as dead based on a too-narrow grep. | Rip 5 sites in Leg 01 (2 declarations + 2 comment references + 1 api.py box-shadow edit). |
| V3b button gradient duplicated at 4 selectors | confirmed-live | `components.css:59` (`.app-picker-button`), `:387` (`.btn-outlined-primary`), `:426` (`.btn-filled-primary`), `:459` (`.btn-muted-destructive`). | Extract to `--btn-v3-gradient` token in Leg 01. |

All four items remain in Flight 3 scope. No items retired.

---

## Leg Progress

### 01-token-hygiene-and-v3b-extract

**Status**: landed (2026-05-11)

**What was implemented** (18 mechanical edits per the leg's edit accounting):

- `the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` — `RADIUS_TOKENS` array collapsed from `['--panel-radius-sm', '--panel-radius-md', '--panel-radius-lg']` to `['--panel-radius', '--panel-radius-sm']`. (The pre-edit array did NOT include `--panel-radius` — the leg description's "replace `['--panel-radius', '--panel-radius-sm', '--panel-radius-md', '--panel-radius-lg']` with `['--panel-radius', '--panel-radius-sm']`" misstated the starting array; the actual starting array was 3 entries. Net result matches the intent: gallery now surveys only defined tokens, and the larger `--panel-radius` is exposed as a swatch — a small bonus over the leg's literal "keep only `-sm`" reading.)
- `tokens.css` light + dark theme: `--panel-radius-sm: 6px;` → `--panel-radius-sm: 4px;` in both blocks.
- `tokens.css` `:root` block: new `--btn-v3-gradient` token declared with the canonical 4-stop white→fade→dark gradient. Verified all 4 V3b consumer sites carried IDENTICAL gradient stops pre-edit; no drift detected; substitution is a pure refactor.
- `components.css` 4 V3b sites (`.app-picker-button`, `.btn-outlined-primary`, `.btn-filled-primary`, `.btn-muted-destructive`): each multi-line `background-image: linear-gradient(...)` block replaced with single-line `background-image: var(--btn-v3-gradient);`.
- `api.py:1535`: `box-shadow: var(--panel-shadow), var(--panel-shadow-glow);` → `box-shadow: var(--panel-shadow);` (the load-bearing pre-step before ripping the token declaration so the OAuth callback page never renders with an invalid var() reference).
- `tokens.css`: `--panel-shadow-glow` declarations deleted from BOTH theme blocks. `:55-60` `--glass-bg` preamble comment rewritten: `"Glass surfaces REPLACE --panel-shadow-glow per the flight's composition rule."` → `"Glass surfaces replace the prior accent-tinted shadow treatment on chrome per the flight's composition rule."`. Dark-theme panel-tokens comment (originally `:264-266`) trimmed to a single sentence (`"panel design tokens — drop-shadow style replaces dark's glow shadows."`) removing the two sentences that named the dead token.
- `components.css:593` (formerly `:613` before the 4×5-line gradient blocks were removed): comment rewritten from `"/* --panel-shadow-glow intentionally dropped — glass surfaces use the …"` to `"/* Prior accent-glow shadow intentionally dropped — glass surfaces use the …"`.
- `agents.md:602`: composition-rule sentence rewritten to drop the dead-token mention.
- `agents.md:682` (blockquote list): `"accent-glow / accent-translucent / panel-shadow-glow rgba tokens in"` → `"accent-glow / accent-translucent rgba tokens in"`.
- `agents.md:699`: trailing bullet `` "`--panel-shadow-glow` cyan tint also updated." `` deleted; surrounding paragraph still grammatical.

**Verification**:

- All 7 grep sentinels green:
  - `grep -rn "panel-shadow-glow" the_one/` → no matches
  - `grep -n "panel-shadow-glow" the_one/agents.md` → no matches
  - `grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css` → `0`
  - `grep -n "panel-radius-md\|panel-radius-lg" the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` → no matches
  - `grep -n "btn-v3-gradient" the_one/interfaces/web/static/css/tokens.css` → declaration at `:26`
  - `grep -c "var(--btn-v3-gradient)" the_one/interfaces/web/static/css/components.css` → `4`
  - `grep -n "panel-radius-sm: 4px" the_one/interfaces/web/static/css/tokens.css` → 2 matches (`:143`, `:276`)
- Narrow test gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x --timeout 30 -q` → **56 passed in 0.92s** (matches Flight 1 + Flight 2 baseline).
- WCAG audit standalone: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 30` → **45 passed in 0.05s** (no regression).
- Visual scan deferred to the human operator (Developer agent runs non-interactively); the leg's visual verification step (`make rebuild` + `#admin/design-language` walkthrough) is a Flight Director / human checkpoint.

**Deviations**:

- The leg description for step 1 said to replace the 4-entry array `['--panel-radius', '--panel-radius-sm', '--panel-radius-md', '--panel-radius-lg']` with `['--panel-radius', '--panel-radius-sm']`. The actual pre-edit array had only 3 entries (`'--panel-radius-sm', '--panel-radius-md', '--panel-radius-lg'` — no `--panel-radius`). I produced the leg's target array `['--panel-radius', '--panel-radius-sm']` regardless, which adds `--panel-radius` to the gallery survey. This is consistent with the leg's intent ("contain only the defined tokens"); `--panel-radius` is defined in `tokens.css` (both themes). If the Flight Director wants the gallery to expose ONLY `--panel-radius-sm`, drop the first entry in a follow-up edit — trivial.

**Anomalies**: None. No V3b gradient drift detected at any of the 4 consumer sites; all stops byte-identical. No other live consumer of `--panel-shadow-glow` discovered beyond the recon's enumeration (the recon's broadened-to-`the_one/` grep was correct).

---

## Decisions

### Reconnaissance citation drift on `tokens-section.js`

**Context**: Flight 2 debrief cited `tokens-section.js:29-33` for the radius-references bug.
**Decision**: Updated the cite to the actual current location `:30-32` in the flight artifact's Prerequisites and Leg 01 description.
**Impact**: None substantive — Leg 01's implementing agent operates on the corrected cite.

### Leg 01 design-review (Developer) surfaced recon blind spot

**Context**: The Phase 2a Developer agent review of Leg 01 surfaced a live consumer of `--panel-shadow-glow` at `api.py:1535` (OAuth callback card's inline `<style>` block).
**Decision**:
- Updated Leg 01 to add a 5th rip site at `api.py:1535`; broadened the rip sentinel grep from `static/` to whole `the_one/` package.
- Decided to drop the second box-shadow stop entirely (substitute `box-shadow: var(--panel-shadow), var(--panel-shadow-glow);` → `box-shadow: var(--panel-shadow);`) rather than inline the resolved value. Rationale: aligns with the flight intent that "glass composition rule replaces the accent-glow treatment on chrome surfaces"; the OAuth callback card is a chrome surface; loses the accent halo but gains intent coherence.
- Updated recon report classification of `--panel-shadow-glow` from `confirmed-live` (as a "dead token") to `misclassified — actually live`. The Flight 2 debrief's classification was based on a `static/`-scoped grep that didn't see the api.py consumer.
- Also incorporated 4 other Developer-surfaced refinements: V3b extraction safety note for `tokens.css:66, :208` glass-gleam gradients (NOT V3b candidates); full enumeration of 14 `--panel-radius-sm` consumers; tightening of `tokens.css:60` cite to the `:55-60` comment-block range.

**Impact**: Leg 01 implementation is 17 mechanical edits, not the 13 originally estimated. The leg also captures a methodology lesson: when ripping CSS tokens, grep the WHOLE package (not just `static/`) — Python files with inline CSS templates are consumers too.

### Design-review (Architect) feedback incorporated

**Context**: Phase 5b Architect review returned `approve with changes` with 3 medium-severity issues + 1 low + 5 suggestions.
**Decision**: All 3 medium + 1 low fixes applied to the flight artifact before Phase 6 closure. Specifically:
- Added the missed `tokens.css:60` site to the Leg 01 rip checklist (Architect-surfaced — Flight 2 debrief missed it).
- Corrected "8px square" → "8px round dot" in Open Question 6 + added size delta vs `.indicator-led`.
- Made the LED wire-up (path b — JS markup edit) the working assumption rather than implementation-time choice; inventoried BOTH `provider-models.js:346` (loaded list) AND `:375` (unloaded list) emission sites; chained the dead-selector cleanup of `.admin-pf-model-dot{,.loaded}` in `admin.css:90-91`.
- Added the warning-callout WCAG-regression guard to Leg 02 (re-run a11y audit mid-leg if surface changes) + working assumption to keep `--status-warning-bg-soft-2` background and only add `--bezel-shadow-inset`.

5 suggestions also applied:
- V3b extraction grep sentinel mirrored from Verification into Leg 06 step 1.
- `tools-form-helpers.js`-already-canonical pre-flight expectation added to Leg 04 ("lightest of the three polish legs").
- Gallery swatch-grids out-of-scope note added to Leg 05 cosmetic pass.
- Routing-catalog two-pass cadence (catalog first, fix second) made explicit in Leg 05.
- Beforeunload checklist promoted from Open Question to an explicit Leg 05 sub-step with 4 named scenarios.
- Theme-toggle Design Decision augmented with implementation note: rip the existing `box-shadow: 0 0 8px var(--accent-glow)` on `admin.css:47` when adding accent-translucent to avoid muddy double-glow.

**Impact**: Flight 3 enters Phase 6 (Iterate) with a codebase-validated spec. No re-review cycle needed — fixes were targeted enough that another Architect pass would be redundant.

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

### Flight design (2026-05-11)

- Loaded flight-design phase file from `/home/cprch/projects/the-one/.flightops/agent-crews/flight-design.md` (project file present).
- Reconnaissance verified four Flight 2 debrief items; all four confirmed-live; one citation drift repaired (`:29-33` → `:30-32`).
- Flight scoped as 6 legs: 1 autonomous prep (token hygiene + V3b extraction), 3 interactive page-polish vibe legs, 1 mixed routing-sweep leg, 1 closing alignment leg.
- Mission Known Issue (custom dropdown for native `<select>`) explicitly deferred to Flight 4 (Studio Polish) per the design decision in the flight artifact — Studio has materially more dropdown consumers and amortizes the build cost.
- LED wire-up scope narrowed to the Ollama lifecycle panel's `.admin-pf-model-dot.loaded` — the natural in-Admin status surface. Provider editor's Test-connection already auto-retrofits from Flight 2's `.test-result-*::before` rule (no new work). No OAuth in Admin (OAuth is MCP-only, lives in Studio + Chat).
- Snapshot regen + HAT folded into Leg 06 alignment (mirrors Flight 2 pattern); per-leg HAT explicitly rejected to avoid HAT fatigue.
- User invoked `/flight` with the "work without stopping for clarifying questions" directive; all open-questions resolved with working assumptions documented inline rather than blocking pre-flight on operator input.
