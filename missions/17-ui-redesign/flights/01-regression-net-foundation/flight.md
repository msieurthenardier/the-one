# Flight: Regression-Net Foundation

**Status**: completed
**Mission**: [UI Redesign — Clean, Professional, Consistent](../../mission.md)

## Contributing to Criteria

- [ ] SC6 — Regression net intact and healthier than before (module-skip removal starts here)
- [ ] SC7 — Behavior-verified core flows (apparatus proven before redesign begins)
- [ ] SC8 — No performance regression (fresh baseline captured here)

---

## Pre-Flight

### Objective

Before any markup or visual change lands, make the regression net trustworthy: establish the stable-testid contract with automated guards, re-enable (or explicitly disposition) the five module-skipped browser test modules, capture a fresh performance baseline as SC8's comparison anchor, and prove the behavior-test apparatus (goldfinch MCP browser driving) against the running pre-redesign app. This flight makes every later flight's "did I break something?" question answerable.

### Open Questions

- [x] Are guards implemented as CI plumbing or pytest? → Design Decisions (pytest)
- [x] Where does the perf baseline live? → Design Decisions (committed mission artifact)
- [x] What happens if the two hang modules resist root-causing? → Design Decisions (timebox + defer)

### Design Decisions

**Guards ship as pytest tests, not CI plumbing**: A new `tests/test_ui_guards.py` (unit-tier, runs in default `make test-unit` and existing Concourse lint/test lanes) enforces: (1) testid registry ↔ source sync (see registry decision); (2) an **innerHTML baseline-freeze** — the current dynamic `innerHTML`/`insertAdjacentHTML` sites (~90 across ~20 files under `the_one/interfaces/web/static/js/`) are captured as a per-file allowlist with counts, and the guard fails on any NEW dynamic sink site beyond the baseline. Static-string assignments (including `= ''` clears) are exempt.
- Rationale: the project already runs pytest everywhere; zero new CI surface; guards are greppable Python. Single-sanctioned-sink enforcement is NOT implementable today — `markdown.js` builds DOM via `createElement` (it is not an innerHTML sink), and ~90 dynamic sites exist across the feature codebase. The freeze stops growth now; Flight 4's vendored sanitizer becomes the sanctioned chokepoint, after which the allowlist ratchets DOWN (per-area re-skin flights shrink their files' counts; Flight 7 verifies the ratchet).
- Trade-off: guards run at test time, not commit time — acceptable, CI runs on every push.

**Testid registry lives at `docs/ui-testid-registry.md`**: models **two id classes** — literal ids (166 today) and parametric ids registered by static prefix pattern, e.g. `connector-row-{id}` (~35 today, built via concatenation). The sync test matches literals exactly and parametric families by prefix; on mismatch it fails loudly emitting the exact add/remove diff. Convention `{area}-{element}` for new ids; existing ids are grandfathered as-is (renaming load-bearing ids now would churn the very tests this flight stabilizes).

**Hang modules: timebox, then defer with teeth**: `test_flow_agent_crud.py` and `test_flow_provider_setup.py` were skipped as "hangs, root cause unidentified" under post-M08-Leg-02 markup. **Resolved by Leg 02 (2026-07-03)** — the earlier "hover-reveal opacity" suspect (`components.css:660-699`) was wrong: Playwright treats `opacity: 0` as visible, so that treatment never broke the tests. The actual mechanism is `components.css:719` — `.page-header:has(+ .entity-tile-grid > .empty-canvas) .new-entity-btn:not(.is-expanded) { display: none; }` — which hides the header create CTA whenever the entity grid is empty; both tests start empty and clicked the header testid, so Playwright retried a `display: none` element until timeout. (The hang itself had already been fixed by the F5 L01 SQLite-isolation fix; only the visibility failure remained.) The fix was a test-side locator swap to the in-canvas `-empty` CTA variant at empty-state points; both modules are re-enabled and passing — no deferral needed. The underlying state-split CTA UX is logged as a mission Known Issue assigned to Flight 3. SC6 remains the mission-end gate.

**Perf baseline is a committed artifact**: `missions/17-ui-redesign/perf-baseline.md` — heap retention under the M08 F7 realistic-load procedure (`App.perf` via `?perf=1`, Chromium), plus coarse first-paint and interaction timings for the three areas. Captured on the pre-redesign branch point so every later flight compares against the same anchor.

**Snapshot strategy for the redesign window**: pixel baselines (local-only, gitignored, per operator's global rule) are expected to invalidate wholesale at Flights 2–3; developers regenerate at each flight boundary (`pytest -m pixel --snapshot-update`) and treat pixel diffs as advisory during the redesign window. DOM-shape assertions and the contrast/token suites are the binding regression net. No committed baselines, ever.

**Behavior-test apparatus is goldfinch MCP (operator-mandated, mission-canonical)**: the operator's brief names goldfinch as the browser apparatus for this mission's behavior tests. Existing specs (authored in the chrome-devtools era) name chrome-devtools in their Preconditions/Observables; `studio-smoke.md` gets an in-scope test-infra edit updating its apparatus lines to goldfinch before the proof run. Specs authored during this mission declare goldfinch from the start. Both the act path (openTab/navigate/click/typeText/evaluate) and the observe path (readDom/evaluate/captureScreenshot) were premise-audited live against `http://127.0.0.1:8484` during mission planning. Scope note: goldfinch cannot take CDP heap snapshots; the Flight-1 perf baseline uses coarse `App.perf`/`performance.memory` numbers via goldfinch `evaluate`, and deep heap-retention analysis (if Flight 7 suspects a regression) may use chrome-devtools MCP as the specialized instrument.

**studio-smoke data precondition**: the spec asserts seeded state (e.g. the "Discord Constellation" connector tile). The proof leg verifies the instance's data satisfies the spec's Preconditions before spawning the crew; if the live DB lacks the expected fixtures, the leg either seeds them or substitutes another existing spec whose preconditions the instance satisfies — the deliverable is a passing goldfinch-apparatus run, not that specific spec.

### Prerequisites

- [ ] `make up` server running on 8484 (verified: responds 200)
- [ ] goldfinch MCP live and able to drive the app (verified during mission planning: openTab/evaluate/screenshot all exercised)
- [ ] Working tree clean on `mission/17-ui-redesign`
- [ ] `THE_ONE_DEV_MODE=true` available for mock-provider flows where needed

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Work is test-infrastructure only — no visual or product-code changes except where a real defect blocks a re-enabled test. Order matters: guards first (they protect everything after), then the skipped-module work (biggest unknown, timeboxed), then baseline capture and apparatus proof (fast, mechanical). The three "pre-rebrand assertions" modules (`test_flow_studio_tools_overrides.py`, `test_studio_mcps_tab.py`, `test_flow_provider_grid.py`) are rewritten against current markup using current `data-testid`s; the two hang modules get the timeboxed root-cause treatment per the design decision.

### Checkpoints

- [x] Guards test file green in default suite
- [x] Three rewrite modules re-enabled and passing via `make test-browser`
- [x] Hang modules root-caused OR dispositioned with Flight-3-linked skip reasons (root-caused AND re-enabled — no deferral needed)
- [x] `perf-baseline.md` committed with real numbers (created by Leg 03; commit lands at flight close per single-commit protocol)
- [x] Behavior test run log shows pass with goldfinch apparatus (spec substitution per flight-log decision: `shell-navigation-smoke` authored + run live — 6/6 pass, `tests/behavior/shell-navigation-smoke/runs/2026-07-03-16-26-39.md`)

### Adaptation Criteria

**Divert if**:
- Re-enabling tests uncovers a product defect larger than a leg (log it, take it to the mission's Known Issues, decide there)
- The browser suite itself is systemically broken (>3 unrelated failures pre-existing on main)

**Acceptable variations**:
- Hang modules deferred per design decision
- Guard test implementation details (exact regexes, file organization)

### Legs

> **Note:** Tentative; created one at a time as the flight progresses.

- [x] `testid-registry-and-guards` - Registry doc + `tests/test_ui_guards.py` (testid sync + innerHTML-sink guard)
- [x] `reenable-skipped-browser-modules` - Rewrite 3 stale modules; timeboxed root-cause on 2 hang modules
- [x] `perf-baseline-and-apparatus-proof` - Capture perf baseline artifact; run `studio-smoke` behavior test via goldfinch (Flight Director runs the behavior test directly — see Leg 03's precondition-readiness note in the flight log before the run)
- [x] `unit-tier-stabilization` - *(added mid-flight, FD decision after Leg 01 findings)* Fix the pre-existing `test_lifespan` ordering flake + clear pre-existing ruff-format drift in six files

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [x] Tests passing (`make test-unit` + `make test-browser`)
- [x] Flight log updated
- [x] Documentation updated (CLAUDE.md testing section if guard commands change developer workflow)

### Verification

`make test-unit` green including `test_ui_guards.py`; `make test-browser` green with ≤2 module skips remaining (only the dispositioned hang modules, if deferred); `missions/17-ui-redesign/perf-baseline.md` exists with numbers; `tests/behavior/shell-navigation-smoke/runs/` contains a passing run log dated this flight (spec substitution per flight-log decision).
