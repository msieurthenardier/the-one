# Flight Log: App Shell Restructure

**Flight**: [App Shell Restructure](flight.md)

## Summary

Flight in planning. Designed 2026-04-26, immediately following the F2 debrief. Scope absorbs the F2 debrief's immediate-action items (leg 01) AND the structural keyboard-operability rebuild (leg 03) flagged as a BLOCKING WCAG 2.1.1 issue at F2 flight-level review — both per F2 debrief recommendation. Form-primitive extraction (the F1-debrief-flagged `admin.js` / `studio.js` divergence) is explicitly OUT OF SCOPE; deferred to a follow-up F3.5.

---

## Leg Progress

_(Populated during execution)_

---

## Decisions

_(Runtime decisions not in original plan — populated during execution)_

---

## Deviations

_(Departures from planned approach — populated during execution)_

---

## Anomalies

_(Unexpected issues encountered — populated during execution)_

---

## Session Notes

### 2026-04-26 — Flight design

- F3 designed with the Option B scoping the user picked at flight-debrief close: keyboard-operability rebuild absorbed into F3 (since F3 restructures the shell anyway), F2 cleanup as leg 01.
- Flight branch will be created from F2's merge commit when F2 PR #14 lands on `main`.
- Mission directory is on `main` (committed during F1); this F3 directory is currently untracked and will land with the first leg.

### Flight Director Notes

**Phase file loaded**: Project-side `the-one/.flightops/agent-crews/flight-design.md` (same as F1/F2).

**Auto-mode flight-design**: Per user instruction, the `/flight` skill ran in auto mode (no Phase 3/4 user interview). Open questions were resolved at design time using the F2 debrief as the substantive input — every design decision below is traceable to either the original mission spec, the F2 debrief, or a code-level constraint surfaced at code interrogation.

**Scope decision rationale**:
- The user asked at flight-debrief close to "design the next leg incorporating that feedback" and explicitly chose Option B from the three proposed options.
- Option B was: absorb keyboard rebuild + F2 cleanup items into F3 (vs Option A separate Keyboard Operability flight, vs Option C tight cleanup leg only).
- Form-primitive extraction is the riskiest piece per mission notes ("May split during flight design — the form primitive extraction is the riskiest piece and may benefit from isolation in a separate flight"). Splitting it preserves F3's ability to land in 2-3 days.

**Form-primitive split is explicit**: The mission roadmap intent for F3 included form primitives. F3's scope expansion (top bar + keyboard rebuild + F2 cleanup) means the form work split is necessary, not opportunistic. F3.5 will be its own flight, bridge between F3 and F4 (Chat Alignment).

**HAT included as final optional leg**: F2's HAT-as-conversational-pacing produced 6+ inline retunes that no autonomous run would have caught. F3 includes structural changes (layout reflow, focus order, hash-routing edge cases) that benefit from real-time iteration with the user.

**Visual snapshot strategy**: F2's 12 baselines will be invalidated by the top-bar restructure (leg 02). DO NOT regenerate after each leg — wait until leg 06 to regen all at once after the layout has settled. This avoids baseline thrashing as keyboard rebuilds (leg 03) and hash-routing (leg 04) land. Leg 06 is the snapshot-and-test consolidation.

**Browser-test additions planned**:
- Hash-routing persistence per area (~3-4 tests)
- Keyboard-state captures (~6 new visual baselines for focused list items + revealed deletes)
- Skip-link reachability (~1 test asserting first Tab from page load lands skip-link)
- App-picker keyboard interaction (~1-2 tests asserting open/close + arrow nav + Escape)

Total browser test count post-F3: ~30-32 (was 20 pre-F3; +10-12 across F3).

**Pre-flight snapshot of mission criteria contribution**: F3 advances 4 of M04's 9 success criteria (sub-page persistence + keyboard operability + shared primitives partial + design-language preservation). The remaining 5 are F4-F6 territory (per-area alignment) + F7 (resilience) + the alignment / debrief flights.

### 2026-04-26 — Architect design review (round 1)

Spawned an Architect (Sonnet) for codebase-validated design review per the `/flight` skill's Phase 5b. Result: **approve with changes** — 3 HIGH issues, 4 MEDIUM, 5 LOW, plus several non-blocking suggestions. All issues incorporated below.

**HIGH issues fixed in spec**:
1. Lifecycle ordering for `init`/`activate`/`hydrateState` was under-specified — added explicit "init → activate → hydrateState on cold entry; hydrateState only on same-area sub-change" decision (Open Question #2 + Design Decision rewrite). Also documents the `switchTo` early-return modification needed at `app.js:32`.
2. `replaceState` vs `pushState` semantics for sub-state was implicit — added explicit decision: sub-state uses `replaceState` (no back-button between sub-pages); cross-area uses `location.hash =` assignment which pushes history. Documented as a separate design decision with rationale.
3. `.skip-link` placement and the unused `utilities` CSS layer were ambiguous — resolved: `.skip-link` lives in `components.css` under `@layer components`; `utilities` layer remains a future placeholder (no leg removes it; no leg uses it in F3). Added to Open Questions.

**MEDIUM issues fixed in spec**:
4. Leg 02 → 03 ordering rationale clarified: legs are independent (no shared files); ordering chosen for narrative coherence (visible structure first, then internal a11y). Documented in leg 03 description.
5. `--nav-w` token disposition: repurposed as `--topbar-h: 48px` in both themes; the `.nav-item.active::before` accent treatment ports to the picker dropdown's active option. Documented in Open Questions + leg 02 description.
6. Theme toggle multi-mount sync: `App.theme.set()` dispatches `CustomEvent('theme-preference-changed')`; each `renderToggle` instance subscribes for state sync. Specified `options.variant: 'full' | 'compact'`. Added to Open Questions + Design Decision rewrite.
7. Leg 05 (`new-chat-restructure`) reframed as a **discovery-via-HAT leg** (Flight Director runs interactively, captures requirements mid-flight, then implements). Intentionally autonomous-Developer-unfriendly — same pattern as F2's leg 09.

**LOW issues fixed in spec**:
8. HAT (leg 07) marked **required**, not optional — F3 is structural; HAT is load-bearing.
9. Leg 06 test count refined: 4 new snapshot scenarios × 2 themes = 8 new baselines (not 6 as originally estimated). Total post-leg: 20 baselines. Browser test count target: ~33-35 post-F3.
10. Leg 01 affordance vocabulary lands as a NEW `### Affordance patterns` subsection in `agents.md` "Design system" section (parallel to existing subsections), not buried inside an existing one.
11. F2 PR #14 still draft prerequisite explicitly stated: F3 cannot enter `in-flight` until PR #14 merges; alternative branching strategy noted.
12. `// PREFIX` consolidation + `.section-marker` lift (F2 debrief recommendations) explicitly deferred to F3.5 form-primitive flight (touches the same files); documented in form-primitive-extraction Open Question.
13. Hamburger app-picker icon: pinned to Lucide `menu`; will be added as a one-line entry to `icons.js` in leg 02.

**Suggestions absorbed**:
- `serializeState`/`hydrateState` are properties on the area descriptor passed to `App.registerArea`, NOT on a separate `App.areas[id]` registry — co-locates with existing `init`/`activate`/`deactivate` lifecycle. Documented in Design Decision rewrite.
- Skip-link styling pattern documented (absolute, top -40px → 0 on focus, accent background).

**Suggestions deferred (non-blocking)**:
- `App.router` namespace split for hash dispatch (vs growing `app.js`): noted but not yet committed; reassess after leg 04 implementation if `app.js` LOC concerns surface.
- The discrepancy between "14 F1 testids" claim and current 13-in-source / 24-in-tests count: minor reconciliation; not blocking. Worth confirming during leg 06.

**Skipped second review**: changes are clarifications and explicit-decision additions, not new technical approach. Per agentic-workflow protocol "skip second review when only clarifications applied." Proceeding with codebase-validated spec.

### 2026-04-26 — Flight design complete

F3 spec is ready. All HIGH and MEDIUM issues from architect review are addressed in-spec. The flight is ready to enter `ready` status once F2 PR #14 merges to `main` (or earlier with the explicit branch-from-F2-HEAD rebase plan).

### 2026-04-26 — Flight ready

F2 PR #14 merged to `main` (merge commit `730b4f3`). F3 prerequisites satisfied (F2 tokens / theme switcher / design-system docs on baseline). Status flipped `planning` → `ready`. Awaiting `/agentic-workflow` kickoff to enter `in-flight`.
