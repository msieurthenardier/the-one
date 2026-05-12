# Flight Log: Studio Polish

**Flight**: [Studio Polish](flight.md)

## Summary

Flight log for Flight 4 of Mission 08 (GleepGlorp Rebrand). Flight design completed on 2026-05-12; awaiting kickoff via `/agentic-workflow flight 04 for the-one mission 08`.

---

## Reconnaissance Report

Source artifacts: Flight 3 debrief (`missions/.../03-administration-polish/flight-debrief.md`) and Flight 3.5 debrief (`missions/.../03.5-shell-chrome-polish/flight-debrief.md`). All cited items + carry-forwards verified mechanically.

| Item | Source | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| Extend reduced-transparency `@media` block for shell tokens | F3.5 debrief rec #1 | `confirmed-live` | `tokens.css:394` has the existing block; no override for `--shell-chrome-bg` / shell sheen / `--shell-frame-glow` present | Leg 01 prep |
| WCAG audit gap on `--shell-chrome-bg` base colors | F3.5 debrief rec #2 | `confirmed-live` | `tests/test_design_tokens_a11y.py:152-185` test_text_on_color has parametrize block; no `shell_chrome_bg` rows | Leg 01 prep |
| Lift theme-generalization-via-tokenization convention to F2 | F3.5 debrief rec #3 | `confirmed-live` | `agents.md:577-619` F2 subsection lacks the convention as a canonical rule (rule is in prose, scattered across flights) | Leg 01 prep |
| Lift "land dark, port light" cadence | F3.5 debrief rec #4 | `confirmed-live` | No flight-design-conventions section exists in agents.md; cadence documented only in F3.5 debrief narrative | Leg 01 prep |
| Cross-reference F3 carry-forward docs items | F3.5 debrief rec #5 | `confirmed-live` | F3 affordance vocabulary doesn't pointer to F3.5 placement of topbar `<img>` CLS + legacy-class-as-JS-handle | Leg 01 prep |
| Rename `--bg-gradient` → `--shell-bg` | F3.5 debrief rec #6 | `confirmed-live` | `tokens.css` has `--bg-gradient: var(--shell-chrome-bg)` in both themes; rename will improve semantic clarity | Leg 01 prep |
| `--shell-chrome-bg` cascade-override comment | F3.5 debrief rec #7 | `confirmed-live` | Token definition in `tokens.css` lacks the cascade-caveat comment | Leg 01 prep |
| Shell-inheritance shaves Flight 4 vibe scope | F3.5 debrief rec #8 | `confirmed-live` | Per-page polish operates on `.content-panel` interior only; baked into Flight 4 scope above | Recorded in Design Decisions |
| Playwright B2 regression test (carry-forward from F3) | F3 debrief Action Item #1 | `confirmed-live` | Flight 3's `confirmLeave` hook + stale-then guard in admin.js ship in production; no Playwright test covers the cross-area path | Leg 05 |
| Carry chip-list UX + LED wire-up + confirmLeave + stale-then guard to Studio | F3 debrief Action Item #11 | `confirmed-live` | Studio area at `static/js/areas/studio.js` + sub-modules; chip-list ships via shared `wireChipListEditor` automatically (no work needed); LED wire-up + confirmLeave + stale-then-guard are real Studio work | Legs 03 (LED) + 05 (confirmLeave + stale-then + Playwright test) |
| Native `<select>` custom dropdown component | Mission Known Issue | `confirmed-live` | 4 Studio sites (`general-tab.js:52, :77`; `mcp-server-editor.js:506, :533`) + 2-3 Admin sites; no `App.dropdown` helper exists | Leg 04 |

All items remain in Flight 4 scope. No retirements.

---

## Leg Progress

### Leg 01 — Prep + Debrief Debt Close (landed 2026-05-12)

**Status**: landed. All 7 Flight 3.5 debrief items closed in a single autonomous pass per the leg's "Order matters" guidance (token rename FIRST, then sheen extraction + reduced-transparency block, so the block writes against the new token names).

**Implemented**:

- **`--bg-gradient` → `--shell-bg` hard rename** (5 sites — confirmed per design-review's correction from "1 site" to "5 sites"):
  - `tokens.css:166` (dark theme definition) + `tokens.css` light theme definition (now `:365` after token additions): renamed; value unchanged (`var(--shell-chrome-bg)`); no alias retained.
  - `base.css:10` body bg consumer: `var(--bg-gradient)` → `var(--shell-bg)`.
  - `api.py:1519` OAuth callback inline CSS: `var(--bg-gradient)` → `var(--shell-bg)`. Caught by the broadened `grep -rn ... the_one/` sentinel (would have been invisible to `test_token_definitions.py`'s `.css`-only scan).
  - `agents.md:682` token-table row: renamed.
  - `agents.md:698` F3.5 composition rule #6 prose: renamed inline reference.

- **`--shell-topbar-sheen` token extracted** (dark + light both define identical value: `linear-gradient(180deg, rgba(255, 255, 255, 0.06) 0%, transparent 6px)` — same white sheen reads on gunmetal + silver chrome). `base.css` `#app-topbar` rule consumes `var(--shell-topbar-sheen)` instead of the inlined gradient. Preserved the sheen-first / chrome-bg-second order in the topbar background stack per design-review note.

- **`--shell-chrome-bg` cascade-override caveat comment** added immediately above each token definition (dark + light); placed adjacent to the existing comment block without disrupting the grain-alternates list.

- **Reduced-transparency `@media` block extended** for both themes. Each theme gains 3 overrides: `--shell-chrome-bg` collapses to its solid base color (`#20202a` dark, `#d4d8df` light), `--shell-frame-glow: transparent`, `--shell-topbar-sheen: none`. Sync-with-base-color comment added per Edge Cases.

- **WCAG audit gap closed (partially — fg_muted variants DROPPED per design review)**:
  - 2 new parametrizations in `tests/test_design_tokens_a11y.py`: `("dark", "fg", "shell_chrome_bg", 4.5)` (12.22:1 measured) + `("light", "fg", "shell_chrome_bg", 4.5)` (12.49:1 measured).
  - `fg_muted` variants intentionally deferred: light `--fg-muted` is `#64748b` (slate-500, NOT `#94a3b8` as originally cited) → 3.33:1 on `#d4d8df` → FAILS body AA. No production muted-text-on-chrome consumer today; documented as Known Issue inline near the new parametrizations.
  - `shell_chrome_bg` key added to both `DARK` and `LIGHT` dicts in `tests/browser/design_tokens.py`.

- **agents.md documentation lift** (3 edits):
  - F2 Design Language Layer subsection — appended new composition rule #5: "Theme generalization via tokenization."
  - New `### Vibe-leg conventions` subsection inserted between `### Affordance patterns` and `### Mission 08 Flight 02`. Documents (a) "Land dark, port light" cadence; (b) "Gallery-as-iteration-substrate" pattern.
  - F3 affordance vocabulary section — appended one bullet cross-referencing F3.5's topbar-`<img>` CLS contract + legacy-class-as-JS-handle pattern.

**Verification (sentinel sweep)**:

| Sentinel | Expected | Actual |
|---|---|---|
| `grep -rn "var(--bg-gradient)\|--bg-gradient" the_one/` | 0 matches | 0 matches |
| `grep -n "var(--shell-bg)" the_one/interfaces/web/static/css/base.css` | 1 | 1 (line 10) |
| `grep -n "var(--shell-bg)" the_one/interfaces/web/api.py` | 1 | 1 (line 1519) |
| `grep -nE "^\s*--shell-bg" the_one/interfaces/web/static/css/tokens.css` | 2 | 2 (lines 166, 365) |
| `grep -n "shell-bg\|--shell-bg" the_one/agents.md` | ≥2 | 2 |
| `grep -c "shell-topbar-sheen" the_one/interfaces/web/static/css/tokens.css` | ≥4 | 4 |
| `grep -c "var(--shell-topbar-sheen)" the_one/interfaces/web/static/css/base.css` | 1 | 1 |
| `grep -E "shell_chrome_bg" tests/test_design_tokens_a11y.py` | 2 | 2 |
| `grep -n "shell_chrome_bg" tests/browser/design_tokens.py` | 2 | 2 (lines 57, 90) |
| `grep -nE "Theme generalization\|Vibe-leg conventions\|see F3\.5\|see.*F3\.5" the_one/agents.md` | ≥3 | 3 |

**Test gates** (in container, narrow scope per leg spec):

- WCAG audit: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 30` → **47 passed** (45 prior + 2 new fg-on-shell_chrome_bg). Matches edge-case-adjusted expectation.
- Narrow 4-module gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30` → **58 passed** (within the 56-60 expected range).

**Deviations**: None of substance. Two minor adjustments worth noting:

- The F3 cross-reference bullet was authored as `documented under F3.5 — see F3.5's section \`### Mission 08 Flight 3.5 — ...\`` (rather than `documented under F3.5 — see \`### Mission 08 Flight 3.5...\``). The original phrasing satisfied the intent but missed the leg's literal `see F3.5` / `see.*F3.5` regex sentinel because the regex expects the `F3.5` token to appear after `see` within the line. Adjusted the phrasing to include `see F3.5` literally without altering the reference's meaning.
- Light theme `--shell-bg` definition now lives at line 365 of tokens.css (was 349 before this leg) because the new `--shell-topbar-sheen` token + cascade-override comment lines pushed it down ~16 lines.

**Anomalies**: None. No additional `--bg-gradient` consumers discovered beyond the 5 sites the design review identified.

**Flight Director follow-up**: visual smoke check (`make rebuild` + dark/light page-load) deferred to Flight Director per leg spec.

---

## Decisions

### Reconnaissance carry-forward classification

**Context**: Flight 3 + Flight 3.5 debriefs surfaced 11 cumulative action items + the mission's native-`<select>` Known Issue. All items in scope for Flight 4 per operator directive ("roll in all of those recommendations").
**Decision**: 7 Flight 3.5 debrief items consolidate into Leg 01 prep (autonomous, mechanical). 4 items split across Legs 03 / 04 / 05. Knowledge-tab polish deferred (stub).
**Impact**: Leg 01 absorbs the technical-debt close so polish legs (02, 03) operate on a clean substrate. Leg 04 (custom dropdown) + Leg 05 (Studio dirty-gate parity + B2 regression test) handle infrastructure work. Legs 06 (routing sweep) + 07 (alignment close) follow the established Flight 3 template.

### Design-review (Architect) feedback incorporated

**Context**: Phase 5b Architect review returned `approve with changes` with 2 high + 3 medium + 1 low severity issues + 3 suggestions + 3 questions.
**Decision**: All 6 issues addressed in the flight artifact before Phase 6 closure. Specifically:

- **(high) Stale-then guard scope misframed**: original Leg 05 scope listed `fetchAgent` per-agent detail as needing a guard; this function doesn't exist (agents load only via `loadAll()` at init, already guarded). Studio also already guards `fetchMcpSources_()` (lines 470/475/484) + `fetchMcpSourceTypes()` (line 355). Reframed Leg 05 as "verify + gap-fill," not infrastructure-from-scratch.

- **(high) Chat `#chat-agent-select` (chat.js:55) omitted from dropdown migration**: high-traffic on-shell native select. Leaving it native creates a visible inconsistency post-Flight-4 that Flight 6 would have to revisit. Added to Leg 04 migration scope (opportunistically; not gating Flight 6).

- **(medium) Studio confirmLeave is smaller than initial framing**: Studio already has inline `dirty + inEditor` gate at studio.js:301-303 in sidebar setActiveSection. Leg 05's work is EXTRACTION + EXPOSURE (closure + descriptor method), not from-scratch implementation. Updated Design Decisions to reflect ~20 LOC instead of ~30+.

- **(medium) Leg 04 conflates 3 work shapes** (helper-build / popover-vibe / migration): added explicit migration checkpoint before vibe-close. Acceptance criterion: grep verifies all 7-8 migration sites swapped before vibe-close.

- **(medium) Leg 03 MCP Server editor (1654 LOC) + LED wire-up is heaviest leg**: added pre-leg LED-site audit so the wire-up sub-task has a known-finite consumer-site list pinned in the leg artifact before vibe kickoff. Isolates LED from the open-ended polish vibe.

- **(low) `--bg-gradient` alias is over-engineered**: only 1 internal consumer. Hard rename, no alias. Updated Design Decisions.

3 suggestions applied:
- agents.md F4 subsection will be lean (only `App.dropdown` is an F4-original pattern).
- "Vibe-leg conventions" subsection name (vs. "flight-design conventions") — narrower and more accurate.
- Playwright B2 test: keep parametrized one-file approach.

3 questions resolved with explicit decisions:
- `#chat-agent-select` → included in Leg 04 migration (not deferred).
- Routing sweep covers all Studio sub-routes including Knowledge stubs (routing correctness is structural, not cosmetic).
- Studio `inEditor` predicate covers BOTH editor mount contexts: `(activeSection === 'agents' && _selectedAgent)` AND `(activeSection === 'mcp-sources' && mcpSourceFormMode)`.

**Impact**: Flight 4 enters Phase 6 with a codebase-validated spec. Leg 05 scope correctly framed. Migration scope corrected to 8 sites (including Chat agent-select). No re-review needed.

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
- Reconnaissance verified 11 carry-forward items (8 from Flight 3.5 debrief + 3 from Flight 3 debrief + 1 mission Known Issue). All `confirmed-live`. No retirements.
- Flight scoped as 7 legs: 1 autonomous prep (7-item debt close from Flight 3.5 debrief), 2 vibe page-polish (Agents + MCP Sources), 1 mixed leg for custom dropdown (autonomous helper + vibe popover treatment), 1 autonomous infrastructure (Studio confirmLeave + stale-then + B2 Playwright test), 1 mixed routing-sweep, 1 closing alignment.
- Scope shaving applied per Flight 3.5 debrief recommendation #8: shell housing inherited from F3.5 → per-page polish operates on `.content-panel` interior only. Saved ~1 vibe leg vs. originally-planned size. Knowledge tab polish-deferred (21-line stub).
- Custom dropdown component (mission Known Issue → F3 deferred → F4) gets its own leg with autonomous helper-building + vibe popover treatment. Migrates 4 Studio sites + 2-3 Admin sites.
- Studio cross-area dirty-gate parity + B2 regression test consolidated into one leg — implementing both atomically because the test verifies the hook (no point shipping the hook without the test that locks it in).
- "Land dark, port light" cadence applies to vibe legs 02 + 03 per Flight 3.5 debrief recommendation #4.
- All open questions resolved with working assumptions documented inline.
