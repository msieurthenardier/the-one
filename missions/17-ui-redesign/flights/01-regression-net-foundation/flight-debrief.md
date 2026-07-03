# Flight Debrief: Regression-Net Foundation

**Date**: 2026-07-03
**Flight**: [Regression-Net Foundation](flight.md)
**Status**: completed
**Duration**: 2026-07-03 09:40 – 13:05 CDT (single day)
**Legs Completed**: 4 of 4 (3 planned + 1 added mid-flight)

## Outcome Assessment

### Objectives Achieved

The regression net is measurably healthier than at flight start: testid registry (185 literals / 46 parametric prefixes / 4 manual exceptions) with probe-verified sync guards; innerHTML dynamic-sink baseline frozen (95 sites / 30 files, snippet-multiset ratchet); all five module-skipped browser modules re-enabled and passing (zero module skips remain — SC6's clause satisfied at Flight 1); the two "unidentified hang" modules root-caused (`components.css:719` empty-state `display:none` on the header CTA — the prior hover-opacity theory disproven); pre-redesign perf baseline committed (+6.55% heap over the pinned M08 150-transition procedure, byte-precise, well under ≤20% budget); goldfinch behavior-test apparatus proven end-to-end with a new re-runnable read-only spec (`shell-navigation-smoke`, 6/6 pass, live two-agent Witnessed run); the default unit tier flake-free for the first time since the M16 F9 escalation (3× consecutive 3681/0 runs — the `_shutting_down` latch root-caused to `TestClient(app)` lifespans, not aiosqlite); ruff format/check clean tree-wide.

### Mission Criteria Advanced

- **SC6** — effectively satisfied already (mission-end gate remains); browser suite 478→532 passed, module skips 5→0, per-test skips 35→6.
- **SC7** — apparatus proven; standing navigation gate authored; run doctrine established.
- **SC8** — baseline anchored with a pinned, re-runnable procedure.

## What Went Well

- **Design-review layers earned their keep twice**: the flight-level architect review reformulated an unimplementable guard premise (single-sanctioned-sink → baseline-freeze) before legs were cut, and Leg 02's design review corrected the flight's root-cause hypothesis *before implementation* (Playwright treats `opacity:0` as visible; the real mechanism was `:719`). Implementation then reproduced the recorded failure before fixing — root cause confirmed, not assumed.
- **"Indicative vs authoritative" calibration hedge**: Leg 01 ranked its citation-audit numbers as indicative and the extractor bootstrap as authority; when ground truth moved (166→185 literals, 103→95 sinks), nothing broke.
- **Constrain-the-deliverable DD writing**: "the deliverable is a passing goldfinch-apparatus run, not that specific spec" let the FD turn a broken precondition (studio-smoke's vanished fixture) into a durable improvement (data-independent `shell-navigation-smoke`).
- **Witnessed pattern under apparatus degradation**: goldfinch `captureScreenshot` wedged all session (compositor throttling); the crew maintained rendered-state evidence discipline anyway — a11y rendered/notRendered discrimination, provenance-verified window-surface captures, and `printToPDF` as the provenance-certain pixel fallback. One frame that failed provenance verification was honestly discarded.
- **Mutation-verified guards**: both failure modes probe-tested (planted testid, planted sink) — guards proven to fail loudly, not assumed.
- **Mid-flight leg addition** absorbed newly-surfaced net-health work (flake + format drift) without ceremony.

## What Could Be Improved

### Process

- **Verify fixture-dependent behavior-spec preconditions at flight design time**, not leg execution — a two-minute read-only check would have made the substitute spec a planned deliverable.
- **Label flight-level defect hypotheses as suspects until live-verified** — the stale "hover-reveal opacity" claim survived into a design decision before Leg 02's review killed it.
- **"Is the default tier green and stable?" is a cheap pre-flight check** a regression-net flight should spec up front (Leg 04 existed only because Leg 01 tripped over the flake).
- Sub-agent developers twice parked on background test monitors instead of finishing synchronously — cost several orchestration nudges. Per-spawn instruction "check runs synchronously; never end your turn waiting on a monitor" should be standard.

### Technical

- **The sink baseline is the flight's most consequential maintenance surface**: any edit to an existing sink's first 80 chars reads as a NEW sink. That's the ratchet working, but Flights 2–6 will trip it constantly (see Recommendations 1–2).
- **Testid extractor blind spot**: a testid introduced inside a backtick template literal would be invisible and silently unregistered (the codebase currently has none — convention-dependent safety). Cheap tripwire closes it (Recommendation 3).
- **Opt-in lifespan fixture is a trap for future test authors**: any new module driving the real lifespan re-creates the `_shutting_down` poison unless it opts in to `reset_lifespan_singletons`.
- Residual low-volume aiosqlite loop-closed warning (single location, `test_db_migration.py::TestSchemaV17`, down from 18–19 occurrences in M16) needs a fix-or-accept disposition rather than silent carry-forward.

### Documentation

- Goldfinch apparatus doctrine (printToPDF fallback + provenance discipline + a11y-tree discrimination) lives only in a behavior-test run log; every M17 flight needs it (Recommendation 7).
- Reusable test idioms (`expect_response` around destructive clicks; disabled-save synchronization; empty↔populated CTA variant boundary) live only in test docstrings.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Spec substitution: `shell-navigation-smoke` authored + run instead of seeded `studio-smoke` | Live fixture vanished; read-only > mutating operator data | Yes — data-independent smoke specs as standing flight gates |
| Leg 04 added mid-flight | Leg 01 surfaced flake + format drift poisoning later gates | Yes — flights own newly-surfaced work that threatens their objective |
| Root-cause DD rewritten in place (`:679` → `:719`) | Design review disproved the recorded hypothesis | Yes — corrections at design review are the system working |
| No draft PR opened | Operator directive: long-running mission branch, no merge to main | Mission-scoped only |
| Flight review batched once across 4 legs (agentic-workflow protocol) | Batching eliminated per-leg review overhead; review found zero issues | Keep for infra flights; revisit for large product-code flights |

## Key Learnings

1. Playwright visibility semantics: `opacity:0` is visible; `display:none` is not — test-breakage triage should start from the engine's definition, not visual intuition.
2. Process-global singletons + real-lifespan tests = ordering poison; reset seams (`_clear_for_test`) + a reusable fixture fix the class, not the instance.
3. AST-equality is the right standard of proof for "format-only" claims on product code.
4. A behavior-test crew can maintain rendered-state evidence discipline through a degraded apparatus if the protocol (evidence-for-pass, provenance, a11y-precedence) is explicit at spawn time.
5. A 7-step Witnessed run ≈ 48 minutes with two live agents — Flight 7's 3 flows × 2 themes needs multi-hour budgeting.

## Recommendations

1. **(Flights 2–6, per-leg)** Budget guard churn explicitly: leg specs name "update registry rows / prune sink-baseline entries" as a step; guard failures are bookkeeping with an exact-diff worklist, not blockers. Expected baseline direction is **shrinkage**; growth or same-size re-wording needs reviewer justification. Record per-file before/after sink counts in flight logs; Flight 7 asserts total < 95.
2. **(Flight 2, urgent)** Add a mirror↔CSS **value-sync guard** (same genre as the Flight-1 guards) landing in the same leg as the new tokens.css — nothing currently enforces the `design_tokens.py` lockstep, and the mirror is already stale on two values (`--fg-faint`, `--fg-tertiary` dark). Expand contrast parametrization to ALL palette tokens per SC2. Fix + regression-test the theme-unset cross-tab sync bug (`storage` handler must handle `newValue === null`).
3. **(Flight 2, cheap)** Backtick tripwire in `test_ui_guards.py`: fail on template literals containing `data-testid` or backtick innerHTML RHS (~5 lines).
4. **(Flight 3, one linked leg)** State-split CTA product fix + dead `connector-test-status` query removal + `KNOWN_DEAD_SELECTORS` entry removal + re-simplify the state-explicit grid tests (they pin the *flawed current* behavior deliberately — spec that so the redesign doesn't imitate it) + retire `-empty` registry rows if the affordance unifies.
5. **(Flight 5)** Fix the studio save→delete race (stale `loadAll()` continuation) during the studio rebuild — the test-side sync idiom currently masks a real product race.
6. **(All flights)** Run `shell-navigation-smoke` at every flight close as the standing navigation gate; apply the Validator's spec-quality fixes (restore-step value re-citing; Auto/unset branch clarification; "existing data acceptable" phrasing). Seeded-empty variant is a Flight 7 candidate.
7. **(Immediate, docs)** Promote goldfinch apparatus doctrine into `the_one/agents.md` (or a testing doc): printToPDF as provenance-certain pixel fallback (print CSS mutes fills — judge active states via a11y checked-state), multi-tab provenance discipline (unattributed frames are non-evidence), a11y rendered/notRendered as the hidden-DOM discriminator, run-tab-unoccluded as an environment precondition. Ride Flight 2's docs leg.
8. **(Watch)** Browser suite 12.5 min and growing (532 tests; wrapper default 1200s already exceeded — CLAUDE.md notes 3600). Record wall-clock per debrief; consider per-area lanes before Flight 4.

## Action Items

- [ ] Flight 2 spec incorporates: mirror-sync guard, full-palette contrast parametrization, theme-unset fix + test, backtick tripwire, apparatus-doctrine docs (owner: Flight 2 design)
- [ ] Flight 3 spec bundles the four linked CTA/dead-selector/test-simplification items (owner: Flight 3 design)
- [ ] Flight 5 spec includes the save→delete race fix (owner: Flight 5 design)
- [ ] aiosqlite `TestSchemaV17` warning: fix-or-accept disposition (owner: Flight 7 or mission debrief)
- [ ] Mission debrief notes M16's undebriefed status and that its F9 "fix at mission-debrief" directive was absorbed here

## Test Metrics (record for future comparison)

- **Unit tier**: 3681 passed / 10 skipped / 0 failed, 333.8s pytest (5:33) — inside the M16 band (296–346s) despite +189 tests since M16 F7; three consecutive flake-free runs (first since M16 F9 escalation). Warnings: aiosqlite loop-closed down to 1 location (was 18–19).
- **Browser tier**: 532 passed / 0 failed / 6 per-test skips, ~12.5 min (~750s), `TEST_TIMEOUT=3600` required. Priors: 478 passed / 35 skips / 563s (M13 F3).
- **Perf**: heap +6.55% (budget ≤20%), switch latency p50 0.10ms / budget 50ms — heap growth is the metric that matters going forward.
