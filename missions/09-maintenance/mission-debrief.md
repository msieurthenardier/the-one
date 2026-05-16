# Mission Debrief: Maintenance (Post-M08)

**Date**: 2026-05-16
**Mission**: [Maintenance (Post-M08)](mission.md)
**Status**: completed
**Duration**: 2026-05-15 → 2026-05-16 (2 calendar days)
**Flights Completed**: 2 of 2 (both `completed`)

## Outcome Assessment

### Success Criteria Results

19 of 19 contributing criteria checked off (with 3 explicitly DROPPED per the mid-mission Concourse-removal pivot, marked as such). All listed below with commit references where applicable.

| Criterion | Status | Notes |
|---|---|---|
| `ruff check the_one/ tests/` returns 0 errors on main | Met | F1 Leg 1, commit `7cb3f99` (restored from 69) |
| `ruff format --check the_one/ tests/` returns "all files already formatted" | Met | F1 Leg 1 (restored from 81 would-reformat) |
| ~~CI lint+format gate proven via deliberate-violation experiment~~ | DROPPED | Concourse removed in F1 Leg 4 (operator pivot 2026-05-15) |
| `asgi-lifespan` installed in dev venv AND `make doctor` drift-detection target added | Met | F1 Leg 2, commit `6f2e1f1` |
| `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` skip predicate tightened | Met | F1 Leg 2 — Case B SKIPPED on WSL2 host |
| OAuth callback `postMessage` JSON escaped against `</script>` injection (all 3 flow sites) | Met | F1 Leg 3 commit A, `e092eb9` |
| `_clean_npx` package-name validated against npm-spec allowlist | Met | F1 Leg 3 commit A — rejects `../etc/passwd` (the CRITICAL design-review save) |
| `pip-audit` added to dev extras + `make audit` local target | Met | F1 Leg 3 commit A |
| `agents.md ## Provider type extension checklist` includes `_init_provider_state` | Met | F1 Leg 3 commit B, `daf24e2` |
| `agents.md ## Project Conventions` codifies "live-read across lazy-resolver boundary" | Met | F1 Leg 3 commit B |
| `.env.example` documents `THE_ONE_DEV_MODE` | Met | F1 Leg 3 commit B (variable survived Leg 4 cleanup) |
| `SECURITY-MODEL.md` Future Work names MCP `streamable-http` URL gating asymmetry | Met | F1 Leg 3 commit B |
| ~~`SECURITY-MODEL.md` documents Concourse team-password rotation cadence~~ | DROPPED | Concourse removed in F1 Leg 4 |
| OpenRouter `_APP_URL` / `_APP_NAME` updated to GleepGlorp AI identity | Met | F1 Leg 3 commit B |
| Concourse infrastructure removed | Met | F1 Leg 4, commit `56bfc71` (`ci/` deleted; `THE_ONE_CONCOURSE_PASS` removed) |
| Self-modification framing removed from live narrative | Met | F1 Leg 4 (CLAUDE.md L56; SECURITY-MODEL.md 3 sites; mission-control `projects.md` rewritten locally — gitignored) |
| Chat welcome agent picker roving-tabindex + arrow keys + `aria-selected` toggling | Met | F2 Leg 1 (augmented existing handler at `chat.js:184-198`) |
| Session-list restructured to `<nav>` + `<ul>` of `<button>` items; `aria-current="page"` toggle | Met | F2 Leg 1 (3 browser test files updated to match) |
| Admin tools-grid verified keyboard-accessible (no role change) | Met | F2 Leg 1 (button-grid post-M08 F5 confirmed) |
| Form-field errors carry `aria-invalid` + additive `aria-describedby` + `role="alert"` | Met | F2 Leg 2 (`clearFieldErrorA11y` helper for clear cycle) |
| Light-theme `--fg-muted`/`--fg-faint` chrome contrast resolved | Met | F2 Leg 2 (scope-the-usage at 3 sites: `base.css:144`, `chat.css:15`, `chat.css:35` — 3rd site caught by post-edit grep-enforce, not pre-enumeration) |

### Overall Outcome

**Mission outcome substantively achieved, with significant architectural improvement beyond the original maintenance scope.** The pre-pivot framing was "restore the integrity gate posture M06 codified that M07/M08 silently eroded." The post-pivot framing absorbed an additional outcome: **remove Concourse + self-improvement framing from the project entirely.** Both outcomes landed cleanly in M09's two flights:

- **F1 (Code Hygiene + Concourse Removal)** restored the lint+format zero-baseline (the original gate-restoration goal) AND removed the Concourse infrastructure (the pivot goal) in 4 legs. The deliberate-violation experiment that was the original Leg 1 centerpiece was dropped (no pipeline to test); the cleanup work survived as standalone code hygiene; the removal added Leg 4 absorbing the new scope.
- **F2 (Accessibility Carry-forward + F1 Tech-Debt Cleanup)** resolved all three Action Required accessibility findings (A.1-A.3) plus the listbox structural fix, swept all 11 medium/low a11y items (firm + opportunistic; zero slippage), AND bundled in the 6 F1-debrief non-methodology recommendations as a new Leg 3. The flight grew from 2 legs to 3 mid-design; landed in one calendar day.

**Net architectural ledger across M09**:
- **Retired**: Concourse infrastructure (-160 lines, -8 cognitive-overhead categories); self-modification narrative across 4 files; M06 F1 lint baseline regression (0/0 restored); `asgi-lifespan` host install drift; sandbox skip-predicate over-narrow case; OAuth callback XSS injection path; `_clean_npx` path-traversal vector (CRITICAL save); 6 F1 debrief non-methodology recommendations; all 8 a11y items from the 2026-05-15 report (firm + opportunistic); 3 M08 mission-debrief carry-forward items closed.
- **Added**: form-error a11y wiring helper (`tools-form-helpers.js`); LED contract docblock (`components.css:855-881`); `<div>`→`<nav>` semantic upgrade at 2 sites; `aria-current="page"` propagation; npm-spec allowlist regex documented as security primitive; `host-side-bench-drift-detection` convention codified; `make rebuild-browsers`/`make audit`/`make audit-bytes` host-side targets.
- **Introduced debt** (small, schedulable in M10's first opportunistic leg, ~45 min total): welcome handler still in `chat.js` not `welcome.js`; `:(glob)` pathspec gotcha not codified as convention; pre-existing `mcp.client.auth.exceptions` host-pytest import failure (NOT caused by M09; invocation-path-sensitive; container is authoritative).

**Value delivered to stakeholders**:
- **Primary operator/user**: a cleaner codebase with less cognitive overhead (one fewer trust boundary, one fewer secret rotation surface, one fewer "maybe-CI-someday" narrative thread), an a11y posture that meets WCAG 2.1 AA across the Chat / Studio / Admin surfaces (modulo the M10-routed items), and a recurring foot-gun ("rebuild wipes Chromium") finally broken via `make test-browser` chaining the existing `_ensure-playwright` machinery.
- **Future maintainers** (including the agent itself self-editing): the methodology has accumulated a substantial pre-implementation issue-catch dataset (1 critical + ~22 high + ~32 medium + ~20 low across F1+F2) that argues for locking per-leg design review as non-skippable. The conventions codified (`host-side-bench-drift-detection`, npm-spec regex security primitive, LED 3-rule contract, `<div>`→`<nav>` semantic preference) reduce surface for future drift.

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| F1: Code Hygiene + Concourse Removal | completed | Lint+format 0/0 restored (`7cb3f99`); asgi-lifespan + `make doctor` host-side + sandbox skip-predicate tightened (`6f2e1f1`); OAuth XSS escape + `_clean_npx` allowlist (CRITICAL save) + `pip-audit` (`e092eb9`); 5 docs carry-forwards (`daf24e2`); Concourse + self-modification framing removed (`56bfc71`). Mid-flight pivot absorbed cleanly. 7 commits + flight-close, PR #56. |
| F2: Accessibility Carry-forward + F1 Tech-Debt Cleanup | completed | Welcome picker `aria-selected` augment; session-list restructure to `<nav>` (`9011576`); 12 atomic a11y sub-commits (firm + opportunistic; zero slippage; `983369b`→`626735d`); 6 F1 carry-forward sub-commits (`beb60c8`→`15233c8`). Mid-design scope expansion (2 legs → 3) absorbed. 25 commits + flight-close, PR #57. |

## What Went Well

**Per-leg design-review discipline produced the methodology's strongest dataset to date.** Cumulative across F1+F2: 1 critical + ~22 high + ~32 medium + ~20 low caught BEFORE implementation across 8 design-review passes (one of which was cycle-2). The Leg 3 (`_clean_npx`) CRITICAL save — the original `[A-Za-z0-9._@/-]` allowlist permitted `../etc/passwd` — is the strongest single data point yet for non-skippable per-leg design review. F2's 4 design-review passes (Leg 1 needed cycle-2) reinforce the same lesson at a different surface (DOM restructure + ARIA semantics). **Second consecutive flight validating per-leg design review as the methodology's load-bearing control.**

**Mid-mission scope absorption worked cleanly — twice.** F1 absorbed the Concourse-removal pivot mid-flight (originally 3 legs → 4 legs); F2 absorbed the F1 carry-forward bundle mid-design (originally 2 legs → 3 legs). Both used the same annotation pattern: preserve original framing as commentary, treat new framing as live spec, durable record in flight log Flight Director Notes Track, source-artifact header annotation rather than body rewrite. **The pivot-annotation pattern is now battle-tested across two distinct scope-change shapes (pivot vs expansion).**

**Cross-mission carry-forward closure was clean.** Eight M08-debrief items absorbed in F1 and F2; six F1-debrief non-methodology recommendations absorbed in F2 Leg 3. Zero decay. The "bundle small tech-debt items into a touching-same-surface leg" pattern (F2 Leg 3) is now validated as a methodology pattern with concrete preconditions: shared entry surface, ≤6 items, ≤2 hours, atomic items.

**Architectural simplification dominated.** The Concourse removal in F1 Leg 4 retired 8 distinct cognitive-overhead categories (upgrade cadence, password rotation, auto-rollback selftest, CI build waste, git-revision binding, AIAT gating, pip-audit-in-CI, gate-evasion) and 3 stale `SECURITY-MODEL.md` anchors. The maintenance report's Cat-8 findings + Finding 1.4 dissolved entirely with the substrate. **Maintenance can produce more value by removing the inspected surface than by fixing what was found on it** — a deep lesson worth carrying to future maintenance missions.

**Cross-leg coherence enforced via grep-and-probe, not upfront enumeration.** F2 Leg 2's A.3 chrome-text consumer enumeration pre-listed 2 sites (`base.css:144`, `chat.css:15`); post-Leg-1 restructure caused `chat.css:35 .session-item-agent` to become a 3rd consumer. Post-edit grep-enforce caught it and absorbed the additional rescope in the same A.3 sub-commit. **Pattern: when Leg N+1 measures over Leg N's restructured surface, re-run enumeration at implementation start.**

**`_ensure-playwright` reframe at F2 design time was the highest-ROI single architectural call of the mission.** The F1 debrief's "add `make rebuild-browsers`" recommendation was reframed to "chain the existing `_ensure-playwright` machinery at `Makefile:39-46`" — a 4-line target rather than a re-implementation. The recurring F5/F6/F6.5/F7/F1 "Chromium wipe" foot-gun was finally broken — not by adding new mitigation, but because the F2-design Architect spot-check caught that the existing machinery already mitigated and the F1-debrief "312 ERRORS at setup" came from BYPASSING `make`. **Lesson: before adding mitigation, audit whether existing machinery already mitigates and the bug is in invocation form, not infrastructure form.**

**Test baseline preserved across all surfaces.** Container broad pytest 1700 passed (F1 close → F2 close, unchanged); host pytest 1700 (when import-failure didn't fire); `make test-browser` 316/35 (restored from BLOCKED at F1 debrief time); ruff 0/0 throughout. Zero new flakes; zero newly-skipped tests. The previously-broken browser test invocation path is now reliable.

**Maintenance posture HELD across both flights.** All M06 F1 security controls (Origin allowlist, https-refusal, encrypted credentials, `.dockerignore`, image pinning) intact at F1 close and confirmed at F2 close.

## What Could Be Improved

### Process

- **Mission-scaffold-time leg specs degrade in accuracy over the flight's lifetime.** F2 Leg 1 + Leg 2 were written during M09 mission scaffolding (2026-05-15); by 2026-05-16 when reviewed per-leg, Leg 1 had 7 high-severity issues and Leg 2 had 2 high + 4 medium + 5 low. **Recommendation**: treat mission-scaffold-time leg specs as DRAFTS — assume per-leg design review will substantively rewrite them. Don't skip cycle-1 even when the spec looks reasonable. (Locked-in as a finding for skill-level codification.)

- **Heavy cycle-1 issue counts on legs touching security-sensitive or structurally-invasive surfaces.** F2 Leg 1's 7 cycle-1 high issues plus F1 Leg 3's CRITICAL save both involved surfaces (DOM restructure + ARIA semantics; security one-liners with regex allowlists) where Architect attention pays off. **Recommendation**: add a `depth-review-required` label to leg specs at flight-design time for legs touching security or structural surfaces; flight Architect adds two design-review cycles by default for labeled legs. Architect mission-debrief proposed three tiers; refined to binary (labeled vs default) for methodology simplicity at current size.

- **Browser-test shape assumptions need disambiguation in leg specs.** F2 Leg 1 marked `test_flow_new_chat.py:196-201` as "SURVIVES — class names preserved." Class names WERE preserved, but the descendant `.session-item .delete` selector broke under the sibling-button shape. **Recommendation**: leg-spec template gets a "Selector continuity ledger" sub-section for legs touching DOM restructure — distinguish class-name preservation (lexical) from selector-continuity preservation (structural), per test file × selector form.

- **Opportunistic-bracket calibration on F2 Leg 2.** "Drop A.9/A.10/A.13 at first sign of slip" was never triggered; all three landed firm. Either the bracket was too conservative or the leg sizing was generous. **Recommendation**: future opportunistic-bracket decisions should distinguish "this could surface a deeper question that pulls the leg over-budget" from "this is small and bundle-able."

### Technical

- **Welcome handler still in `chat.js:184-198`, not `welcome.js`.** F2 Leg 1 cycle-2 design review pre-decided to defer; M10 cohesion-improvement candidate (~30 min).

- **`:(glob)` pathspec gotcha not codified.** F2 Leg 3 caught it at implementation time via negative-case probe (raw `the_one/**/*.py` was silently false-clean under git's default fnmatch). Not yet documented as a project convention. **M10 quick win**: one-line Makefile comment OR addition to `agents.md ### host-side-bench-drift-detection`.

- **Pre-existing `mcp.client.auth.exceptions` host-pytest import failure surfaced during F2 Leg 1; did NOT recur in Leg 3 or close.** Invocation-path-sensitive (likely stale `__pycache__` or shim difference). Container is authoritative. **M10 host-venv refresh candidate**.

- **Browser-test coverage gaps**: A.2 additive `aria-describedby` end-to-end (~30 min); A.7 reduced-motion gate via Playwright emulation (~20 min); LED contract static-check pytest assertion (~15 min); form-error clear-cycle path (low priority). M10 candidates.

- **No automated replacement for the Concourse lint+format gate.** With Concourse removed, the M06 lint+format zero-baseline restoration in F1 Leg 1 has no automated enforcement substrate. Operator-discipline alone is the same mechanism that failed across M07/M08 (and caused M09's whole gate-restoration centerpiece). **M10 must make a call here**: pre-commit hooks, minimal GitHub Actions workflow running `make lint format test`, or accept operator-discipline-only with explicit documentation. Architect mission-debrief leans toward a minimal GHA workflow — small enough not to re-introduce Concourse-class overhead, automated enough to catch the drift class.

### Documentation

- **`landmark-elements-over-aria-roles` convention** at n=2 today (chat session-list + section-nav). Worth codifying in `agents.md ## Project Conventions` as a peer of `host-side-bench-drift-detection`. M10 quick win.
- **"Container test entry-points reach via `make` not raw `docker exec`"** convention not codified despite being empirically established. M10 quick win (~10 min).
- **`mcp.client.auth.exceptions` invocation-path-sensitive failure** not yet routed to M10 known-issues. Worth carrying forward as "investigate during M10 host-venv refresh."
- **The maintenance report's "Post-Report Pivot" annotation** is correct architecturally but adds a cognitive hop for future readers. Optional one-line cross-link from each superseded finding's row pointing at the pivot section. Low-priority.

## Lessons Learned

### Technical

1. **`[A-Za-z0-9._@/-]` is NOT an allowlist for paths** — every character is permitted individually, so `../etc/passwd` passes. Use spec-grounded allowlists (npm package-name spec, RFC-grounded URL schemes, etc.). The F1 Leg 3 CRITICAL save established this concretely.
2. **Source files must NOT carry raw U+2028/U+2029 characters** — both terminate JavaScript statements when literal in source. Use Python escape sequences. The F2 Leg 3 implementation anomaly + `make audit-bytes` regression-net established this.
3. **`aria-current="page"` is the canonical "active item in nav list" semantic** — both `section-nav.js` and `chat.js` session-list use it. `aria-selected` is listbox-only.
4. **Native landmark elements (`<nav>`, `<main>`, etc.) over `<div role="...">` for shell-level navigation surfaces.** Native semantics survive ARIA spec churn. Applied at 2 sites; codify at n=2.
5. **Git's default pathspec mode treats `**` literally** — drift-detection targets need `:(glob)` prefix for recursive glob. Only execution surfaces this; spec-time review cannot.
6. **Form-error `aria-describedby` additivity** must preserve existing wiring via split-on-whitespace + push + dedupe-via-Set + join. Clear-cycle must prune both explicit ids AND orphan prefixed ids defensively.
7. **Maintenance can produce more value by REMOVING the inspected surface than by FIXING what was found on it.** Five maintenance-report Action Required findings dissolved entirely when Concourse was removed (1.4, 4.1, 4.2, 8.1, all of Cat-8 advisories).
8. **Code hygiene is independent of CI substrate.** Removing Concourse didn't invalidate F1 Leg 1's lint+format zero-baseline restoration — it just removed automated enforcement. The cleanup work survived as standalone code hygiene. Don't bundle "run tests" with "enforce tests via pipeline X."

### Process

1. **Per-leg design review is the methodology's load-bearing control.** F1+F2 caught 1 critical + ~22 high + ~32 medium + ~20 low pre-implementation issues across 8 design-review passes. Lock as non-skippable in `/agentic-workflow`, even for "trivial" legs.
2. **Cycle-2 escape hatch is the design value, not its routine use.** Most legs settle in 1 cycle; the option to do focused cycle-2 when cycle-1 produces substantive rewrites is what keeps a broken brief from reaching the implementer.
3. **Mission-scaffold-time leg specs are DRAFTS.** Treat as such; per-leg design review will substantively rewrite them, especially for legs scaffolded days before flight execution.
4. **Mid-mission pivots are NORMAL for maintenance missions**, not exceptional. The act of inspecting scope creates conditions for scope-questioning. The pivot-annotation pattern (preserve original as commentary, new as live spec, FD Notes track + header annotation) is battle-tested at n=2.
5. **The bundle-on-touching-surface pattern absorbs scope expansion at design time, not implementation time.** F2 Leg 3's 6-item / 6-sub-commit / ~2-hour bundle is the canonical example.
6. **Cross-leg coherence enforced by grep-and-probe at implementation start, not upfront enumeration.** When Leg N+1 measures over Leg N's restructured surface, re-run enumeration; don't rely on design-time list.
7. **Before adding mitigation, audit existing machinery.** The `_ensure-playwright` reframe saved ~30 min by recognizing the F1 debrief's "rebuild wipes Chromium" foot-gun was an invocation-form bug, not an infrastructure-form bug.

### Domain

1. **Concourse drifted from "tool the agent uses" to "maybe-CI-someday infrastructure"** that nobody invoked. The drift was diagnostic evidence (password-server mismatch in `.env`); the architectural question ("is this serving its purpose?") was the right one to ask, even though it surfaced mid-flight rather than at maintenance-report write time. **Future maintenance reports should explicitly ask "is each piece of infrastructure named in this report still serving its original purpose?"** Architect-level question at inspection time.

2. **The maintenance-mission shape is working as designed.** Two data points (M06 post-M05; M09 post-M08) — M09 absorbed a pivot + a scope expansion cleanly. Maintenance missions SHOULD be expected to evolve mid-flight because inspection-creates-scope-questioning. Continue the post-major-mission trigger pattern; re-evaluate cadence at M12 or after the next maintenance mission.

## Methodology Feedback

### What worked

- **Per-leg cycle-1 design review** as default. Sustainable across F1 + F2 (8 passes total). Continue.
- **Cycle-2 escape hatch** when cycle-1 produces substantive rewrites. Used at F1 Leg 3 + F2 Leg 1. Continue.
- **Reconnaissance Report at top of flight log** + post-edit grep-enforce. Continue.
- **Mid-mission pivot pattern** (original framing as commentary, new as live spec, FD Notes track + source-artifact header annotation). Codify.
- **Bundle-on-touching-surface for small tech-debt.** Codify with preconditions.
- **The `_ensure-playwright`-style reframe heuristic** (audit existing machinery before adding mitigation). Codify.

### What didn't work

- **Leg specs scaffolded at mission-design time were factually incomplete for legs touching structurally-invasive surfaces.** F2 Leg 1's 7 cycle-1 high issues. Not a methodology failure per se — per-leg design review caught them — but a signal that **mission-design Architect should label structurally-invasive legs as `depth-review-required`** so flight-design assigns cycle-2 by default rather than reactively.

- **Browser-test impact enumeration relied on "class names preserved" framing** that didn't distinguish lexical vs structural preservation. The `test_flow_new_chat.py:196-201` beyond-spec edit was the miss class. Worth a leg-spec template addition (selector-continuity ledger).

- **`mission-control/projects.md` description re-write was a local-only edit** because the file is gitignored. Discovered at implementation time. **Acceptable** — the gitignore is intentional — but the leg spec should have flagged it. Future cross-repo legs should re-verify gitignore status during recon.

### What's worth promoting to skill updates

Lifted from F1+F2 debriefs for mission-debrief consumption (the methodology improvements that should land BEFORE M10 starts):

1. **`/agentic-workflow` skill**: lock per-leg cycle-1 design review as non-skippable. Cycle-2 escape hatch documented. The 1 critical + ~22 high pre-implementation catch rate across F1+F2 is unambiguous.

2. **`/agentic-workflow` skill (or `/flight`)**: codify the mid-mission/mid-flight pivot pattern. When scope changes during execution, preserve original framing as commentary, treat new framing as live spec, durable record in flight log Flight Director Notes Track, source-artifact header annotation rather than body rewrite.

3. **`/flight` skill**: add `depth-review-required` label for legs touching security-sensitive or structurally-invasive surfaces at mission-design time. Flight Architect adds cycle-2 by default for labeled legs. Binary label (not three-tier) for methodology simplicity.

4. **`/flight` skill**: leg-spec template gains a "Selector continuity ledger" sub-section for legs touching DOM restructure. Distinguish class-name preservation (lexical) from selector-continuity (structural).

5. **`/flight-debrief` and `/flight` skill prompts**: codify "container test entry-points reach via `make`, not raw `docker exec`" as a project convention (not just a one-flight observation).

6. **`/flight-debrief` and `/flight` skill prompts**: codify the bundle-on-touching-surface pattern for small tech-debt. Preconditions: shared entry surface, ≤6 items, ≤2 hours, atomic items.

7. **`/flight` skill**: codify drift-detection probe-with-negative-case as a Verification contract sub-bullet. Drift-detection target specs must include positive+negative probe in the AC, not just clean-tree exit-0.

8. **`/routine-maintenance` skill**: Inspector framing should include the "is this infrastructure still serving its original purpose?" question at inspection time. M09's pivot signal (Concourse password drift) was visible in the maintenance report's findings but not surfaced as an architectural question until mid-flight.

9. **`agents.md` codification** (within `the-one` project):
   - `### landmark-elements-over-aria-roles` convention at n=2 (chat session-list + section-nav).
   - "Container test entry-points reach via `make`" convention.
   - `:(glob)` pathspec gotcha note under `### host-side-bench-drift-detection`'s contract.
   - LED 3-rule contract docblock pattern — DON'T codify at n=1; wait for n=2.

## Action Items

### M10-blocking (must be decided early in M10 mission design)

- [ ] **Decide gate-replacement substrate**: pre-commit hooks, minimal GitHub Actions workflow running `make lint format test`, OR accept operator-discipline-only with explicit `agents.md` documentation. M09 retired the Concourse gate; M10 must make this call early — operator-discipline alone is the same mechanism that failed across M07/M08.

### High priority (M10 priority #1/#2, operator-flagged)

- [ ] **M10 priority #1**: Build mid-turn stop/cancel button + investigate agent-loop reliability on local models (M08 KI #6/#7). Operator-confirmed top priority at M08 debrief.
- [ ] **M10 priority #2**: Resolve the 5 module-skipped browser test files + paired `.new-entity-btn` DOM-visibility defect (M08 KI #3). User-facing defect, not just CI inconvenience.

### Medium priority (M10 candidates, schedulable)

- [ ] Welcome-handler re-home from `chat.js:184-198` to `welcome.js` (~30 min cohesion refactor)
- [ ] `:(glob)` pathspec gotcha codified as Makefile comment or `agents.md` entry
- [ ] "Container test entry-points reach via `make`" convention added to `agents.md`
- [ ] `landmark-elements-over-aria-roles` convention added to `agents.md ## Project Conventions`
- [ ] A.2 additive `aria-describedby` end-to-end browser test (~30 min)
- [ ] A.7 reduced-motion gate browser test via Playwright emulation (~20 min)
- [ ] LED contract static-check pytest assertion (~15 min)
- [ ] Form-error clear-cycle path test (low-frequency regression risk)
- [ ] Investigate `mcp.client.auth.exceptions` host-pytest invocation-path-sensitive failure (M10 host-venv refresh)
- [ ] Routine-maintenance "maybe-someday infrastructure" audit (`concourse-local` stranded repo; `THE_ONE_DEV_MODE`; Playwright browser-test infrastructure; encrypted-credentials rotation story)

### Routed to M11 (separate mission — architectural cluster)

- [ ] Singleton aiosqlite production lifecycle
- [ ] Per-call `httpx.AsyncClient` pooling (11 sites)
- [ ] `_sessions` eviction
- [ ] Per-provider streaming-parser dedup
- [ ] MCP SSRF symmetry with LLM provider path
- [ ] Schema migration v7-v9 atomicity

These are mission-sized and should NOT bundle with M10's reliability + gate-replacement scope. Recommend M11 = "architectural cluster" as a separate mission.

### Methodology improvements (mission-control skill updates BEFORE M10 starts)

- [ ] Update `/agentic-workflow` skill: lock per-leg cycle-1 design review as non-skippable
- [ ] Update `/agentic-workflow` or `/flight` skill: codify mid-mission/mid-flight pivot pattern
- [ ] Update `/flight` skill: `depth-review-required` label for security-sensitive or structurally-invasive legs
- [ ] Update `/flight` skill: leg-spec template "Selector continuity ledger" sub-section
- [ ] Update `/flight-debrief` and `/flight` skill prompts: bundle-on-touching-surface pattern + drift-detection probe-with-negative-case + container-test-entry-points-via-make
- [ ] Update `/routine-maintenance` skill: Inspector "is this infrastructure still serving its original purpose?" question

### Low priority / informational

- [ ] Maintenance-report cross-link from each superseded finding row to the "Post-Report Pivot" header section (optional)
- [ ] LED contract docblock pattern codification — DEFER until n=2 (a second similar primitive surfaces)
- [ ] Carry-forward stack artifact (`carry-forward-stack.md`) — DEFER; current bundle-on-touching-surface absorbs the mass. Re-evaluate at M10 scaffold if ≥10 M09 carry-forwards route to M10 opportunistic legs.
- [ ] Flight-log split into `flight-log.md` + `design-reviews.md` — DEFER; F2 is at the upper edge but not over (~334 lines). Re-evaluate at next flight if design-review track exceeds 4 cycles.
