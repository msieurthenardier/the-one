# Flight: Mission-11 UI Accessibility Pass

**Status**: ready
**Mission**: [Maintenance (Post-M11)](../../mission.md)

## Contributing to Criteria
- [ ] Routing-rule reorder is operable by keyboard (A2)
- [ ] The connector attach/enable toggle has an accessible name (A3)
- [ ] The connector live-status region announces state changes to screen readers (A1)
- [ ] Discord "Bot status" presence select + name input are labeled; editor section titles are programmatic headings (A4, A5)
- [ ] Custom-dropdown focus indicator meets 3:1; `studio.css` transitions respect `prefers-reduced-motion` (A6, A7)

---

## Pre-Flight

### Objective
Bring the new Mission-11 connector-editor UI up to WCAG 2.1 Level-A operability and clean up the AA/AAA gaps, in one cohesive pass over `connector-editor.js`, `connectors-tab.js`, and `connector-form-discord.js` (and `studio.css`).

### Open Questions
- [ ] A2 mechanism — restore chevron move-up/down buttons, or make the drag handle focusable with arrow-key reordering? See Design Decisions; confirm at flight start.

### Design Decisions

**Severity framing (from roundtable)**: These are Action-Required operability fixes, not security-parity blockers. A2 is the top priority — keyboard inaccessibility is a *loss of capability*, and the single-user posture removes the safety net rather than lowering it. A1 was downgraded to Advisory (the status info is visible to a sighted operator) but is fixed in the same pass.

**A2 — restore an explicit keyboard path**: The chevron move-buttons were removed in M11 in favor of HTML5 drag. Recommended: restore move-up/down buttons (simplest, discoverable) — the drag handle can stay for mouse users. Alternative: make the handle `tabindex="0"` with arrow-key reordering and live-region feedback. The `role="button"` currently promises keyboard operability it doesn't deliver, so whichever path is chosen must make the promise true.

**A1 — `role="status"` on the polled region**: Add `aria-live="polite"` / `role="status"` to the live-status text span and `aria-live="assertive"` (or `role="alert"`) to the error wrap, so the 3s-poll state changes and the "Fix in Developer Portal" link are announced.

**Bundle the smaller items**: A4 (presence controls), A5 (section titles → `<h2>`), A6 (dropdown focus contrast), A7 (reduced-motion tokens) ride along in the same pass since they touch the same files.

### Prerequisites
- [ ] A2 mechanism confirmed.
- [ ] `THE_ONE_DEV_MODE=true` for browser-test verification.

### Pre-Flight Checklist
- [ ] All open questions resolved (A2 mechanism)
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined (browser tests + manual keyboard/SR pass)
- [ ] Legs defined

---

## In-Flight

### Technical Approach
Three legs grouped by file-cohesion and severity: Leg 1 the two Level-A operability blockers (A2 keyboard reorder, A3 toggle name); Leg 2 the announcement + labeling Level-A/AA items (A1 live region, A4 presence labels); Leg 3 the structural + visual polish (A5 headings, A6 focus contrast, A7 reduced-motion). Each leg adds or extends a browser test where one fits.

### Checkpoints
- [ ] Routing rules reorderable by keyboard; toggle named (Leg 1)
- [ ] Live-status announced; presence controls labeled (Leg 2)
- [ ] Section titles are headings; dropdown focus visible at 3:1; transitions honor reduced-motion (Leg 3)

### Adaptation Criteria

**Divert if**:
- Restoring move-buttons conflicts with the routing-rule data model in a way that needs design work — fall back to the focusable-handle + arrow-key approach.

**Acceptable variations**:
- Exact ARIA mechanism (`role="status"` vs `aria-live`), heading level styling.

### Legs
- [ ] `01-keyboard-reorder-and-toggle-name` - A2 (keyboard routing-rule reorder) + A3 (named attach toggle)
- [ ] `02-live-region-and-labels` - A1 (live-status announcements) + A4 (presence control labels)
- [ ] `03-headings-contrast-motion` - A5 (section headings) + A6 (dropdown focus contrast) + A7 (reduced-motion tokens)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (incl. browser tests for the keyboard path)
- [ ] Documentation updated (agents.md a11y notes if a convention changes)

### Verification
Manual keyboard-only pass: routing rules reorderable, all controls reachable and named. Screen-reader pass (or `aria-*` assertions in a browser test): status changes announced, toggle/presence controls named, section titles navigable as headings. `pytest -m browser tests/browser/` green. `pytest tests/test_design_tokens_a11y.py` still green.

### Regression-gate note
The 2026-06-04 maintenance report recommends authoring a **behavior test** for the connector-editor keyboard + screen-reader flow (keyboard-only routing-rule reorder; status-change announcement) — these regress silently and don't fit a unit test. Author the spec inline during this flight's planning per `.claude/skills/behavior-test/AUTHORING.md`, and run it via `/behavior-test` after the legs land.
