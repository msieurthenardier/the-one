# Flight Debrief: Accessibility Carry-forward + F1 Tech-Debt Cleanup

**Date**: 2026-05-16
**Flight**: [Accessibility Carry-forward + F1 Tech-Debt Cleanup](flight.md)
**Status**: landed
**Duration**: 2026-05-16 (single calendar day; F2 design + 4 design-review passes + 3 implementations + flight review + flight-close commit, all same day)
**Legs Completed**: 3 of 3 (Leg 3 added mid-design per operator direction to absorb the F1 debrief's 6 non-methodology recommendations)

## Outcome Assessment

### Objectives Achieved

Every Action Required accessibility finding from the 2026-05-15 maintenance report is closed, every opportunistic medium/low sweep item landed (zero slippage), and all six F1-debrief non-methodology recommendations shipped as a bundled atomic-sub-commits leg. Concretely:

- **A.1 + listbox keyboard semantics + structural fix**: chat welcome agent picker's existing keydown handler at `chat.js:184-198` augmented to toggle `aria-selected` in lockstep with `tabindex` (attribution comment naming `section-nav.js:71-91`). Session-list restructured: `chat.js:60` container `<div class="session-list" role="listbox">` → `<nav class="session-list" aria-label="Chat sessions">`; per-bucket `<ul>` wrappers with `aria-labelledby` from `history-buckets.js`; each item now `<li class="list-item"><button class="session-item" data-id="..." [aria-current="page"]>title</button><button class="delete list-item-delete">×</button></li>` — `data-id` attribute preserved (NOT renamed); `.list-item` class preserved for the CSS `:focus-within` reveal at `components.css:123-124`. `highlightActiveSession` at `chat.js:131-138` uses `setAttribute('aria-current', 'page')` on the active item + `removeAttribute('aria-current')` on inactive (NOT `'false'` — semantic correctness verified during design review). Admin tools-grid verified keyboard-accessible as-is (button-grid post-M08 F5, NOT a listbox).
- **A.2 form-field error wiring**: `tools-form-helpers.js:557-633` renders error spans with generated ids and adds `aria-invalid="true"` + additive `aria-describedby` (split-on-whitespace → push → dedupe-via-Set → join — preserves the existing info-icon `<field>-desc` wiring). `role="alert"` lands on the FIRST error span per save cycle via `firstAlertWired` flag. New `clearFieldErrorA11y(row)` companion strips both per-error ids it tracked AND any orphan `field-error-*` prefixed id (defensive against prior-render leakage).
- **A.3 light-theme contrast**: scope-the-usage approach rescoped 3 chrome-text consumer sites from `var(--fg-muted)` / `var(--fg-faint)` to `var(--fg-tertiary)` (`#475569`, AA-passing on `--shell-chrome-bg`): `base.css:144 .stub-sidebar .subtitle`, `chat.css:15 .session-group-label`, `chat.css:35 .session-item-agent`. The third site (`chat.css:35`) was a post-Leg-1 chrome-text consumer that the pre-enumeration missed; caught by the post-edit grep-enforce mechanism and absorbed into the same A.3 sub-commit. `tests/test_design_tokens_a11y.py:187-196` deferral comment updated to enumerate the rescoped sites + require dual update on future chrome-text re-introduction.
- **A.5 toast duration**: `app.js:244` literal `2000` → `5000` (5s minimum per WCAG 2.2.1).
- **A.6 MCP icon alt-text**: `mcp-server-editor.js:337-340` ternary dropped; always emits `alt=""` (decorative icon; title text rendered alongside).
- **A.7 thinking-indicator reduced-motion gate**: `chat/thinking-indicator.js:24-31` wraps `setInterval` in `window.matchMedia('(prefers-reduced-motion: reduce)').matches` check; reduced-motion path renders static `' …'` and skips the interval.
- **A.8 telemetry overlay**: per-row `aria-hidden="true"` (rely on container `aria-label="Token usage"`); `chat.css:80` opacity bumped `0.4` → `0.7`.
- **A.9 indicator-led contract**: docblock at `components.css:855-881` codifies the 3-rule taxonomy (decorative → `aria-hidden="true"`; state-distinct from adjacent text → `aria-label`; ambiguous → prefer `aria-label`). 6 sweep sites updated (2 in `provider-models.js`, 4 in design-language gallery); `mcp-server-editor.js:486-489` left as-is per the contract's "state-distinct" rule.
- **A.10 section-nav role**: `<div role="group">` → `<nav>` (matches the chat session-list pattern from Leg 1; native landmark replaces the ARIA role). `test_flow_keyboard.py:163-164` assertion updated to tagName check in the same sub-commit.
- **A.11 trace-shell count in aria-label**: BOTH create site (`trace-shell.js:32-35`) and update site (`:55-58` inside `appendToTrace`) refresh the summary's `aria-label` to include the count with singular/plural agreement.
- **A.12 tool toggle visible state label**: `tools-grid.js:76` adds visually-hidden `<span>` inside the `<label>` carrying state text.
- **A.13 README accessibility section**: brief section landed describing WCAG 2.1 AA target + `prefers-reduced-motion` support + report-issue pointer.
- **F1 carry-forward Leg 3** (NEW): `make rebuild-browsers` chains existing `_ensure-playwright` (no duplication); `make doctor` uses `.venv/bin/python3 -c` (closes sub-shell PATH foot-gun); `make audit-bytes` PCRE git-grep for raw U+2028/U+2029 with `:(glob)` pathspec (inline fix during impl — git's default fnmatch treats `**` literally); `agents.md:243` citation corrected (`test_max_context_tokens_live_read_across_resolver` → `test_usage_event_reflects_live_max_context_tokens_at_emission`); new `` ### `host-side-bench-drift-detection` `` convention entry between `gated-debug-instrumentation` and `live-read-across-lazy-resolver-boundary` (chronologically correct + backtick-wrapped per section convention); new `Operator-supplied identifier allowlists` peer bullet in `SECURITY-MODEL.md ## Tool Execution Boundary` (flat-bullet-list voice; NOT a nested H3).

### Mission Criteria Advanced

All 5 F2-contributing mission criteria checked off (welcome picker, session-list, tools-grid verify, form-field errors, light-theme contrast). The 6 F1 tech-debt items are tracked via F2 Leg 3 sub-commits rather than mission-level criteria (they originated post-mission-design). Net: Mission 09 has now satisfied 19 of 19 contributing criteria across F1 + F2.

## What Went Well

**Per-leg design-review discipline produced the methodology's strongest dataset to date.** Across 4 design-review passes (Leg 1 needed 2 cycles per the skill's escape hatch; Leg 2 + Leg 3 one each), the cumulative pre-implementation issue count was **11 high + ~16 medium + ~10 low**. Combined with F1's 1 critical + the same-class catches, M09 has accumulated 1 critical + ~22 high + ~32 medium + ~20 low caught BEFORE implementation. The Leg 1 cycle-1 review alone caught 7 high-severity issues that would have silently broken consumers (`data-id` rename), shipped invalid ARIA (`aria-selected` on `<button>`), missed tests (3rd listbox-role assertion at `test_flow_keyboard.py:67`), or stalled implementation (welcome handler "missing" when it actually existed). The cycle-2 escape hatch caught a path typo (`areas/chat/chat.js` vs `areas/chat.js`) that would have produced an implementation-time stall. **Second consecutive flight validating that per-leg design review is the methodology's load-bearing control — lock as non-skippable, even for "trivial" legs.**

**Mid-flight scope expansion absorbed cleanly.** F2 was originally 2 legs (a11y carry-forward) at mission scaffolding. Operator direction post-F1-debrief was to bundle in the 6 non-methodology recommendations. The flight grew to 3 legs, ~1.5–2 days estimate → ~2.5–4 days, executed in one calendar day. The methodology absorbed the expansion at the design phase rather than the implementation phase. Leg 3 was structurally orthogonal (Makefile + agents.md + SECURITY-MODEL.md — none of Leg 1/2 touched these files), so cross-leg conflict risk was zero.

**Architect's `_ensure-playwright` reframe at F2 design time was the highest-ROI single architectural call of the flight.** F1 debrief recommended "add `make rebuild-browsers` to break the Chromium foot-gun." F2 design review caught that the existing `_ensure-playwright` machinery at `Makefile:39-46` already mitigated the foot-gun for canonical entry points; the F1 debrief's "312 ERRORS at setup" came from BYPASSING `make` and calling raw `docker exec the-one pytest -m browser`. Leg 3 sub-fix (a) shifted from "implement rebuild-browsers" to "chain rebuild + _ensure-playwright using existing machinery" — a 4-line target rather than a re-implementation. Saved ~30 minutes of duplicated install-call surface. **Lesson: before adding a new mitigation, audit whether the existing machinery already mitigates and the bug is in invocation form, not infrastructure form.**

**Cross-leg coherence handled via grep-enforce + post-edit verification, not upfront-only enumeration.** A.3 chrome-text consumer enumeration in Leg 2 pre-listed 2 sites (`base.css:144`, `chat.css:15`). The post-Leg-1 session-list restructure caused `chat.css:35 .session-item-agent` to become a 3rd chrome-text consumer that the pre-enumeration missed. The post-edit grep-enforce (`grep -rn 'var(--fg-muted)' the_one/interfaces/web/static/css/` filtered to chrome consumers) caught it and Leg 2's A.3 sub-commit absorbed the additional rescope. **Pattern validated: when a later leg measures over a surface an earlier leg restructured, post-edit grep-enforce catches what upfront enumeration cannot.**

**LED contract docblock pattern is reusable.** The 3-rule taxonomy at `components.css:855-881` (decorative / state-distinct / ambiguous) compressed a sprawling sweep-question into discrete dispositions. Six call sites swept in a single sub-commit (`c0ecda0`). The docblock-above-primitive-with-canonical-exemplars-cited-inline pattern works; codify at n=2 when a second similar primitive arises.

**`<div>` → `<nav>` semantic upgrade applied at 2 sites (session-list Leg 1 + section-nav Leg 2 A.10) produced cross-surface coherence.** Two shell-navigation surfaces now share one canonical pattern: `<nav aria-label>` + `<ul>` of `<button>` with `aria-current="page"` on the active item. The dev-mode `console.warn` on non-`<nav>` containers in the section-nav helper is the load-bearing regression guard. **Net architectural simplification, not accidental coupling.**

**Test metrics held perfectly across all surfaces.** Container broad pytest 1700 passed (unchanged from F1 close); host pytest 1700 passed; `make test-browser` 316/35; ruff 0/0; `make doctor`/`audit`/`audit-bytes`/`rebuild-browsers --dry-run` all exit 0. Zero new flakes. Zero newly-skipped tests. The F1-flagged `mcp.client.auth.exceptions` host import failure DID NOT recur in this debrief's run — confirms Leg 3's hypothesis that it's invocation-path-sensitive, not a tree-level defect.

**F1 carry-forward closure was clean.** All 6 non-methodology recommendations from the F1 debrief landed as 6 atomic sub-commits in Leg 3, no decay to a future maintenance pass. The "bundle small tech-debt items into a touching-same-surface leg" pattern is validated.

## What Could Be Improved

### Process

- **Mission-scaffold-time leg specs degrade in accuracy over the flight's lifetime.** Leg 1 + Leg 2 were written 2026-05-15 during M09 mission scaffolding; by 2026-05-16 when they were reviewed per-leg, line refs had drifted and Leg 1's recon was demonstrably incomplete (7 high-severity issues at cycle-1). Future flights should treat mission-scaffold-time leg specs as DRAFTS — assume per-leg design review will substantively rewrite them. Don't skip cycle-1 even when the spec "looks fine."
- **Browser-test shape assumptions need disambiguation in leg specs.** Leg 1 marked `test_flow_new_chat.py:196-201` as "SURVIVES — class names preserved." Class names WERE preserved, but the descendant `.session-item .delete` selector and the `.confirm-delete`-on-`.session-item` assertion broke under the sibling-button shape (`.confirm-delete` now lands on `<li>`). Future leg specs touching DOM restructure should enumerate ALL selectors that touch the restructured surface (descendant, child, sibling, attribute-equals) and call SURVIVES/UPDATES per row, not just "class names preserved."
- **Heavy cycle-1 issue counts on legs scaffolded at mission-design time.** Leg 1 had 7 high cycle-1; Leg 2 had 2 high + 4 medium + 5 low; total ~17 issues caught per design-review pass across F2. This is significantly more than F1's per-leg reviews caught. The cumulative cost is real (4 design-review passes ~ 60-120 minutes total). Worth considering at the methodology level: **flag legs that touch security-sensitive or structurally-invasive surfaces at mission-design time** ("depth-review-required at flight-design time" label rather than a re-design). Concentrates Architect attention where most needed without committing to upfront depth-design.
- **Opportunistic-bracket calibration**: Leg 2's "drop A.9/A.10/A.13 at first sign of slip" was never triggered. All three landed firm. Either the bracket was too conservative or the leg sizing was generous. Future opportunistic-bracket decisions should distinguish "this could surface a deeper question that pulls the leg over-budget" from "this is small and bundle-able." A.9 (LED contract) had real design surface; A.10 + A.13 were mechanical.

### Technical

- **`make audit-bytes` pathspec spec-vs-actual drift**: leg spec carried `'the_one/**/*.py' 'tests/**/*.py'` raw-glob form forward. Negative-case probe at implementation time revealed git's default fnmatch treats `**` literally → silently false-clean. Inline fix to `:(glob)the_one/**/*.py` `:(glob)tests/**/*.py`. **This is the class of bug only execution surfaces.** Future drift-detection target specs should mandate a positive+negative probe in the AC, not just a "runs clean on a clean tree" check. Worth codifying under `host-side-bench-drift-detection`'s contract.
- **No browser-test exercises the A.2 additive `aria-describedby` end-to-end** with both info-icon id and error id co-present. The 14 existing `test_flow_admin_tools_editor.py` tests cover field-error rendering but don't assert the additivity sequence specifically. M10 candidate: ~30-minute focused test covering the full info-icon + error-id co-presence and clear-cycle pruning.
- **No browser-test for A.7 reduced-motion gate** (would require Playwright `emulate({ reducedMotion: 'reduce' })`). M10 candidate.
- **LED contract violations not bound to a static check.** The 3-rule taxonomy is documentation. Future LEDs could violate silently. M10 candidate: a `pytest` test that greps every `indicator-led` occurrence and asserts either `aria-hidden="true"` or `aria-label=` is present.
- **Clear-cycle for form errors covered by implementation inspection only.** A regression where a new "fix" path doesn't fire the change handler would silently leave stale `aria-invalid="true"` on a valid input. M10 candidate: focused test.
- **Welcome handler still in `chat.js`, not `chat/welcome.js`.** Cycle-2 design review pre-decided to defer; M10 cohesion-improvement candidate.
- **Pre-existing `mcp.client.auth.exceptions` host-pytest import failure**: Leg 1 reproduced it; Leg 3 + this debrief did NOT reproduce. Invocation-path-sensitive (likely stale `__pycache__` in a specific dir, or `python -m pytest` vs `pytest` shim difference). Container is authoritative. M10 host-venv refresh candidate.

### Documentation

- **`:(glob)` pathspec gotcha not codified as a project convention.** One-line Makefile comment near the `audit-bytes` pathspec OR an `agents.md` entry under `host-side-bench-drift-detection`'s contract would prevent regression. Low-priority.
- **"Container test entry points reach via `make`, not raw `docker exec`" convention not codified.** Empirically established (F1 debrief #5 + F2 Leg 3 reinforces); not in `agents.md`. ~10-minute addition.
- **Browser-test selector continuity ledger** not part of the leg-spec template. Worth a sub-section template addition.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 3 added mid-design (2 legs → 3 legs) | F1 debrief surfaced 6 non-methodology recommendations; operator direction to bundle into F2 rather than M10. Touching-same-surface (Makefile + agents.md + SECURITY-MODEL.md) made the bundle clean. | Yes — codify "bundle small tech-debt items (≤6 items / ≤2 hours / shared entry surface) into a touching-same-surface leg" as a methodology pattern; preconditions: (a) shared entry surfaces; (b) ≤6 items; (c) ≤2 hours estimate. |
| Leg 1 needed TWO design-review cycles | Cycle-1 produced substantive rewrites (7 high-severity issues); cycle-2 caught a path-typo HIGH that would have stalled implementation. Per-skill rule allows cycle-2 when substantive changes are applied. | Yes — keep the cycle-2 escape hatch documented; its existence is the design value (most legs settle in 1 cycle). |
| Pre-flight Chromium prereq downgraded BEFORE F2 kickoff | F2 design-review Architect spot-check found `_ensure-playwright` machinery at `Makefile:39-46` already mitigated for canonical entry points; F1 debrief's "312 ERRORS at setup" came from bypassing `make`. Reframed prereq from "operator must run `playwright install`" to "run `make _ensure-playwright` once at flight start" with all verification commands switched to `make test-browser`. | Yes — codify "before adding a new mitigation, audit whether existing machinery already mitigates and the bug is in invocation form, not infrastructure form" as a recommendation for future flight design. |
| A.3 chrome-text 3rd consumer (`chat.css:35`) caught at implementation time | Pre-enumeration listed `base.css:144` + `chat.css:15`; post-Leg-1 restructure caused `.session-item-agent` to paint on chrome. Grep-enforce mechanism caught it post-edit. | Yes — codify "when Leg N+1 enumerates over a surface Leg N restructures, the enumeration must be re-run at Leg-N+1 implementation start, not relied upon from design." Grep-enforce as the post-edit verification mechanism. |
| `make audit-bytes` `:(glob)` pathspec inline fix | Leg spec used raw `the_one/**/*.py` (looked plausible at design); negative-case probe at implementation time revealed git default fnmatch treats `**` literally. Fixed inline. | Yes — codify "drift-detection target specs must include positive+negative probe in the AC, not just clean-tree exit-0." |
| `test_flow_new_chat.py:196-201` beyond-spec edit | Leg 1 spec marked test as "SURVIVES — class names preserved." Implementation found descendant `.session-item .delete` selector broke under sibling-button shape (`.confirm-delete` moved from `.session-item` to `<li>`). | Yes — codify "browser-test impact enumeration must distinguish class-name preservation from selector-continuity preservation." Per-leg template gets a "Selector continuity ledger" sub-section. |

## Key Learnings

### Technical

1. **`aria-current="page"` is the project's canonical "active item in nav list" semantic** — both `section-nav.js` and now `chat.js` session-list use it. `aria-selected` is listbox-only; don't reach for it on nav surfaces.
2. **`<div role="group">` and `<div role="listbox">` should be `<nav>` for shell-navigation surfaces.** Native landmark elements survive ARIA spec churn and tooling improvements; F2 standardized this at 2 sites.
3. **Git's default pathspec mode treats `**` literally** — drift-detection targets need `:(glob)` prefix for recursive glob. The negative-case probe is the only reliable catch mechanism; spec-time review cannot detect this.
4. **Form-error `aria-describedby` additivity sequence** (split-on-whitespace → push → dedupe-via-Set → join) preserves info-icon wiring while adding error-id; the clear-cycle inverse must prune both explicit ids AND orphan prefixed ids defensively.
5. **LED 3-rule contract** (decorative → `aria-hidden`; state-distinct → `aria-label`; ambiguous → prefer `aria-label`) compresses sprawling per-site decisions into discrete dispositions. The docblock-above-primitive pattern is reusable for future primitives with semantic contracts.

### Process

1. **Per-leg design review is the methodology's load-bearing control** — F2's 11 high + ~16 medium + ~10 low caught pre-implementation issues (plus F1's 1 critical) make this an unambiguous lock-in. Non-skippable even for "trivial" legs.
2. **Cycle-2 escape hatch is the design value, not its routine use.** Most legs settle in 1 cycle; the option to do a focused cycle-2 when cycle-1 produces substantive rewrites is what kept Leg 1 from shipping a path-typo'd brief.
3. **Mission-scaffold-time leg specs are DRAFTS, not finals.** Treat as such; don't skip per-leg design review even when the spec looks reasonable.
4. **The "bundle small tech-debt into a touching-same-surface leg" pattern absorbs scope expansion at design time, not implementation time.** F2 Leg 3 validates: 6 items, 6 atomic sub-commits, zero decay.
5. **Cross-leg coherence is enforced by grep-and-probe at implementation start, not upfront enumeration.** When Leg N+1 measures over Leg N's restructured surface, re-run enumeration at Leg-N+1 implementation, not rely on design-time list.

### Domain

1. **The `_ensure-playwright` reframe pattern**: before adding a new mitigation, audit whether existing machinery already mitigates and the bug is in invocation form, not infrastructure form. F2 saved ~30 minutes via this audit.
2. **The maintenance-mission shape is working as designed** — per-leg design review concentrated correction at the cheapest phase; mid-flight scope expansion absorbed without scope explosion; cross-leg coherence enforced by grep-and-probe; existing-machinery reframe avoided duplication. Flight grew 50% in leg-count and ~67% in estimate; landed in one calendar day.

## Test Metrics

Captured this debrief, 2026-05-16, post-flight-close commit `005a087`:

| Suite | Pass | Fail | Skip | Deselect | Wall-clock | Notes |
|---|---|---|---|---|---|---|
| Container broad pytest (`docker exec the-one pytest --tb=no -q --ignore=tests/browser`) | **1700** | 0 | 4 | 12 | **103.26s** | 2 pre-existing warnings (`test_ollama_models` AsyncMock + cache-write perms) |
| Host broad pytest (`.venv/bin/python3 -m pytest --tb=no -q`) | **1700** | 0 | 4 | 375 | **104.25s** | 17 pre-existing warnings. **`mcp.client.auth.exceptions` import failure did NOT recur** — confirms Leg 3's invocation-path-sensitive hypothesis |
| `make test-browser` (`docker exec the-one pytest -m browser ...`) | **316** | 0 | 35 | 12 | **266.88s** | Chromium auto-restored via `_ensure-playwright`; exit 0 |
| `make doctor` | — | — | — | — | <1s | exit 0 |
| `make audit` | — | — | — | — | ~6s | 6 advisories (4 pip 24.0; 2 urllib3 2.6.3); non-blocking exit 0 |
| `make audit-bytes` | — | — | — | — | <1s | exit 0 (clean) |
| `make -n rebuild-browsers` | — | — | — | — | <1s | dry-run resolves chain; exit 0 |
| `ruff check the_one/ tests/` | — | — | — | — | <1s | All checks passed |
| `ruff format --check the_one/ tests/` | — | — | — | — | <1s | 220 files already formatted |

**Comparison vs prior baselines**:

| Suite | F7 close | F1 close (M09) | **M09 F2 close** | Delta F1 → F2 |
|---|---|---|---|---|
| Container broad pytest | 1679p/4s 97.28s | 1700p/4s 95.12s | **1700p/4s 103.26s** | +0 tests; wall-clock +8.14s (within noise) |
| Host broad pytest | — | 1700p/4s 102.68s | **1700p/4s 104.25s** | +0 tests; wall-clock +1.57s |
| Browser (`make test-browser`) | 316p/35s 265.02s | BLOCKED (Chromium missing) | **316p/35s 266.88s** | unchanged baseline; **F1 debrief recommendation #5 RESOLVED via F2 Leg 3 (a) chaining `_ensure-playwright`** |

**Notes**:
- F2 broad-pytest baseline (1700) is identical to F1 close — F2 work was assertion-edits to existing tests, not net-new test files, so test count unchanged.
- Browser baseline restored from BLOCKED at F1 debrief time to 316/35 — recurring F5/F6/F6.5/F7/F1 foot-gun finally broken via the existing `_ensure-playwright` machinery (`make test-browser` chains it correctly).
- Zero flakes across all three suites (sequential reruns identical).

## Recommendations

1. **Lock per-leg design review as non-skippable** in the `/agentic-workflow` skill, even for "trivial" or "mechanical" legs. F1 + F2 produce the strongest data point yet (1 critical + ~22 high + ~32 medium pre-implementation across two flights). The cycle-2 escape hatch stays documented; cycle-1 is mandatory.

2. **Codify "container test entry-points reach via `make`, not raw `docker exec`"** as a project convention in `agents.md`. The `_ensure-playwright` machinery only fires when the canonical wrappers are used. This is empirically established but not codified. ~10 minutes; M10 candidate.

3. **Codify the bundle-on-touching-surface pattern** for small tech-debt items in the `/flight-debrief` and `/flight` skill prompts: "When debrief items share entry surface and total ≤6 items / ≤2 hours, bundle into a touching-same-surface leg rather than scheduling a separate flight." Validates by F2 Leg 3.

4. **Codify drift-detection probe-with-negative-case** as a Verification contract sub-bullet under `host-side-bench-drift-detection` in `agents.md`. Drift-detection target specs must include positive+negative probe in the AC, not just "clean-tree exit-0." Prevents recurrence of the `make audit-bytes` `**` pathspec false-clean trap.

5. **Add browser-test coverage gaps as M10 candidates**: A.2 additive `aria-describedby` end-to-end (~30 min); A.7 reduced-motion gate via Playwright emulation (~20 min); LED contract static-check pytest grep assertion (~15 min); form-error clear-cycle path (low priority).

6. **Investigate the `mcp.client.auth.exceptions` host-pytest import failure during M10 host-venv refresh.** Invocation-path-sensitive; container is authoritative. Likely stale `__pycache__` or shim difference. Reproducible from Leg 1's specific invocation but not from broader runs.

7. **Codify "browser-test selector-continuity ledger"** as a leg-spec template sub-section for legs touching DOM restructure. Distinguish class-name preservation (lexical) from selector-continuity (structural). Prevents the `test_flow_new_chat.py` "SURVIVES" miss class of error.

8. **Re-home welcome-picker keydown handler from `chat.js:184-198` into `welcome.js`** as a cohesion improvement. M10 candidate; ~30-minute refactor. Cycle-2 design review pre-decided to defer.

## Action Items

### High priority (M10-blocking or methodology)

- [ ] Lock per-leg design review as non-skippable in `/agentic-workflow` skill (methodology update)
- [ ] Codify drift-detection probe-with-negative-case under `host-side-bench-drift-detection` convention (1-line addition to `agents.md`)
- [ ] Add "container test entry-points reach via `make`" convention to `agents.md` (M10 candidate; ~10 min)

### Medium priority (M10 candidates, schedulable)

- [ ] A.2 additive `aria-describedby` end-to-end browser test (~30 min)
- [ ] A.7 reduced-motion gate browser test via Playwright emulation (~20 min)
- [ ] LED contract static-check pytest assertion (~15 min)
- [ ] Welcome-handler re-home from `chat.js` to `welcome.js` (~30 min cohesion refactor)
- [ ] `:(glob)` pathspec gotcha codified as Makefile comment or `agents.md` entry
- [ ] Form-error clear-cycle path test (low-frequency regression risk)

### Low priority (informational / quick wins)

- [ ] Investigate `mcp.client.auth.exceptions` host-pytest invocation-path-sensitive import failure (M10 host-venv refresh)
- [ ] Browser-test selector-continuity ledger template addition to leg-spec template (methodology)
- [ ] LED contract docblock pattern formalized as `agents.md` convention when a 2nd similar primitive arises (n=1 today; don't formalize yet)
- [ ] `<div>` → `<nav>` semantic upgrade codified as `agents.md` convention (`landmark-elements-over-aria-roles`) — 2 sites applied is n=2 bar (M10 candidate)

### Methodology improvements (for mission-debrief consumption)

- [ ] Consider `depth-review-required` label for legs touching security-sensitive or structurally-invasive surfaces at mission-design time (concentrates Architect attention without committing to upfront depth-design)
- [ ] Carry-forward stack artifact (`carry-forward-stack.md` at mission level) IF M09 mission-debrief surfaces ≥3 recommendations that don't immediately schedule in M10 — not yet needed; flag for mission-debrief
- [ ] Flight-log Flight Director Notes track split into `flight-log.md` (FD Notes + Decisions + Deviations) + `design-reviews.md` (per-leg cycle tracks) IF F3 in any project approaches 4+ design-review passes (F2 is at the upper edge today)
