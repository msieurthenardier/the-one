# Flight: Accessibility Carry-forward

**Status**: ready
**Mission**: [Maintenance (Post-M08)](../../mission.md)

## Contributing to Criteria

- [ ] Chat welcome agent picker has roving-tabindex + ArrowUp/ArrowDown/Home/End working with `aria-selected` toggling; pattern lifted from `areas/layout/section-nav.js:71-91`
- [ ] Session-list restructured: `role="listbox"`/`role="option"` removed; replaced with `<nav>` + `<ul>` of `<button>`; affected browser test assertions in `tests/browser/test_flow_keyboard.py` updated to match
- [ ] Admin tools-grid verified keyboard-accessible (already a button-grid post-M08 F5, NOT a listbox — no role change)
- [ ] Form-field errors carry `aria-invalid="true"` + `aria-describedby` to a generated id; `role="alert"` on first error per save cycle
- [ ] Light-theme `--fg-muted` (and `--fg-faint` where used on shell chrome) meet WCAG AA contrast against `--shell-chrome-bg` via scope-the-usage approach (use `--fg-tertiary` at chrome-text consumer sites rather than darkening `--fg-muted` globally)

---

## Pre-Flight

### Objective

Resolve the three Action Required accessibility findings from the 2026-05-15 maintenance report — two of which (A.2 form-field errors, A.3 light-theme contrast) are second-pass-running carry-forwards — and opportunistically sweep the medium/low-severity a11y items in the same touch surface.

### Open Questions

- [x] Bundle the medium/low a11y items inline with the Action Required ones, or scope them out? → see Design Decisions
- [x] Should the listbox structural fix (session-list `role="option"` contains `<button>`) preserve the listbox semantic or fall back to nav+links? → see Design Decisions

### Design Decisions

**Tools-grid is NOT a listbox** (Architect spot-check during Phase 4b mission validation): the maintenance report's A.1 routing claimed tools-grid was a `role="listbox"` site needing roving-tabindex treatment. Inspection of `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` showed it's actually `role="list"` + `role="listitem"` — already migrated to a button-grid in M08 F5 leg 02 (tab stops via the inner `<button>` affordance, as documented in `tests/browser/test_flow_keyboard.py:107-110`). The roving-tabindex + ArrowKey + `aria-selected` treatment from `section-nav.js` is semantically inappropriate for a `list`/`listitem` structure. **Decision**: leg 01 verifies tools-grid is keyboard-accessible as-is and skips any role-changing edit. Net result: only ONE site (welcome agent picker) actually needs the roving-tabindex treatment.
- Rationale: don't add `role="listbox"` to a structure already-migrated to button-grid. Don't lift a pattern across a semantic boundary.
- Trade-off: the original "shared helper at ≥2 consumers" decision becomes moot with one consumer. Leg 01 copies the pattern into welcome.js with attribution, no helper extraction.

**Session-list structural fix: fall back to `<nav>` + `<ul>` of `<button>` links**: the listbox semantic was being mis-applied (interactive descendants are not allowed under `role="option"`), and chat history is conceptually a navigation list more than a single-select. Dropping `role="listbox"` resolves the structural violation cleanly. The per-item delete button stays as a sibling element, not a child of the listed item.
- Rationale: the WCAG / ARIA semantic that matches "click a session to load it; click a sibling button to delete it" is `<nav>` + `<ul>` of `<button>` (or `<a>` if hash-routed); this matches the surrounding shell-navigation pattern.
- Trade-off: loses the listbox arrow-key behavior; gained by the `<nav>` getting `Tab`/`Shift+Tab` for free, which is the more idiomatic chat-history navigation.
- **Affected tests**: `tests/browser/test_flow_keyboard.py:50, 63` asserts `session_list.role == "listbox"`. The leg's Files Affected list and acceptance criteria account for updating this. Re-read the file end-to-end before edit — there may be related assertions in the same file.

**Bundle the medium/low a11y items, but reserve the bottom of the list for slip**: A.5 (toast 2s), A.6 (MCP icon MIME-as-alt), A.7 (thinking-indicator reduced-motion), A.8 (telemetry overlay), A.11 (trace-shell count), A.12 (tool toggle title=) touch surfaces leg 02 touches; bundle them in. **A.9** (`indicator-led` labeling discipline), **A.10** (`section-nav` `role="group"` disposition), and **A.13** (README accessibility section) are budgeted as **opportunistic — drop at first sign of leg slippage**. Each one can surface a deeper design question (LED primitive contract; tablist semantics; README voice) that pulls the leg beyond budget; per Architect sizing assessment, leg 02 already bundles ~8 firm sub-fixes plus the token-cascade risk, and 11+ sub-fixes is over-budget.
- Rationale: per M08 mission-debrief lesson — carry-forward stack decay happens when bottom-of-stack items never land. Better to land 8 reliably than scope-cram 11 and slip the leg.
- Trade-off: A.9/A.10/A.13 may rot to the next maintenance pass; that's the accepted cost of mission-sized scope discipline.

**Light-theme contrast fix: lead with scope-the-usage (Attempt B), not global token change (Attempt A)**: Architect spot-check during Phase 4b found that darkening `--fg-muted` globally would cascade through `.oauth-callback-detail`, telemetry overlay, session-item-agent, and likely many pixel-snapshot baselines. Leading with the global change burns time on a rollback+retry that the leg flow originally documented as "highest-risk first." Better path: replace `var(--fg-muted)` with `var(--fg-tertiary)` (already #475569, AA-passing) at the specific chrome-text consumer sites (topbar, sidebar) directly.
- Rationale: smaller blast radius, faster verification, less pixel-baseline churn.
- Trade-off: requires enumerating the chrome-text consumer sites individually; the leg flow now leads with that enumeration step.

### Prerequisites

- [ ] Flight 1 (Integrity Gate Restoration) completed and merged — this flight depends on the ruff baseline being clean and `make doctor` being in place
- [ ] No outstanding browser-test failures from Flight 1's commits (broad pytest exits 0)
- [ ] Local Playwright can run pixel tests (for visual baseline regeneration after token changes)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites identified
- [x] Validation approach defined (each WCAG criterion verified per leg; pixel baselines regenerated locally after token changes per project convention — baselines are gitignored)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Two legs.

**Leg 1 (Welcome picker keyboard + session-list restructure + tools-grid verify)**: copy the roving-tabindex pattern from `areas/layout/section-nav.js:71-91` into the chat welcome agent picker (`areas/chat/welcome.js`). This is the one site that needs the treatment; helper extraction is moot with one consumer. For the session-list, replace `role="listbox"` / `role="option"` with `<nav>` + `<ul>` of `<button>` items; the per-item delete button becomes a sibling rather than a child; update `tests/browser/test_flow_keyboard.py` assertions accordingly. For tools-grid, verify keyboard accessibility of the existing button-grid (no role change — already migrated in M08 F5 leg 02). Verify with manual keyboard testing (Tab, Shift+Tab, Arrow keys, Enter, Escape).

**Leg 2 (Form errors + tokens + sweep)**: A.2 form-field error wiring (`aria-invalid` + `aria-describedby` + `role="alert"`) — locate `renderFieldErrors` site and wire up the association. A.3 light-theme contrast — lead with scope-the-usage: enumerate chrome-text consumer sites (topbar, sidebar) and switch them from `var(--fg-muted)` to `var(--fg-tertiary)`; verify with `tests/test_design_tokens_a11y.py`. A.5 toast extend to 5s. A.6 MCP icon `alt=""` when decorative. A.7 thinking-indicator `prefers-reduced-motion` gate. A.8 telemetry overlay labeling + opacity. A.11 trace-shell count include in `aria-label`. A.12 tool toggle visible state label.

**Opportunistic (drop at first sign of leg slippage)**: A.9 `indicator-led` labeling discipline (contract docs + call-site sweep); A.10 `section-nav` `role="group"` → drop or `role="tablist"`; A.13 README accessibility section.

Each finding gets a separate sub-commit inside the leg so reverting any one item is clean. If a sub-fix surfaces a deeper issue, document it in the flight log Anomalies section and decide whether to scope it out.

### Checkpoints

- [ ] Leg 1: three listbox sites have correct keyboard semantics; session-list structural fix landed; manual keyboard test passed across all three
- [ ] Leg 2: form-field error wiring landed; light-theme contrast test green; all sweep items landed with sub-commits
- [ ] Local pixel baselines regenerated after Leg 2's token change (baselines are gitignored — local artifact)

### Adaptation Criteria

**Divert if**:
- Light-theme contrast fix requires a token change that cascades through unrelated surfaces with regression. Roll back to a scope-the-usage approach (use `--fg-tertiary` at the chrome-text sites instead of darkening `--fg-muted` globally).
- Form-field error wiring breaks the existing per-row highlight CSS. Inspect the cascade and choose between fixing the CSS or restructuring the markup.
- The session-list structural fix breaks a hash-route deep-link to a specific session. Verify route handling before merging the fix.

**Acceptable variations**:
- Sweep items A.9-A.13 may be skipped individually if scope surfaces complexity not visible at scaffold time. Document each skip in the flight log with a reason.
- Pixel baseline regeneration may surface unrelated visual drift introduced by the token change — that's the regression-net working as intended; the change either is acceptable polish or is reverted.

### Legs

- [ ] `01-listbox-keyboard-and-structure` — Welcome agent picker: roving-tabindex + arrow keys. Session-list: drop listbox semantic, restructure to nav+buttons, update affected browser test assertions. Tools-grid: verify keyboard accessibility (no role change).
- [ ] `02-form-errors-tokens-and-sweep` — Form-field error wiring; light-theme chrome-text contrast via scope-the-usage; firm sweep (A.5/A.6/A.7/A.8/A.11/A.12). Opportunistic (drop if leg slips): A.9, A.10, A.13.

---

## Post-Flight

### Completion Checklist

- [ ] All two legs completed
- [ ] All success criteria contributing to this flight checked off
- [ ] Manual keyboard navigation works correctly in all three listbox sites
- [ ] Form-field error announcements work (verify with VoiceOver / NVDA / Orca screen-reader test if available; otherwise inspect DOM)
- [ ] Light-theme contrast test passes (the existing test in `test_design_tokens_a11y.py` or equivalent)
- [ ] Local pixel baselines regenerated (gitignored, local-only)
- [ ] Broad pytest exits 0
- [ ] Ruff baseline preserved (0/0)
- [ ] Flight debrief run (per M08 lesson)
- [ ] Mission flight checkbox checked

### Verification

- `cd /home/cprch/projects/the-one && pytest --tb=no -q` → exit 0
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` → both exit 0
- Manual: open chat → click in welcome agent picker → press ArrowDown → focus moves to next agent → press Enter → agent selected
- Manual: open chat → focus session list → press Tab through items → each item focusable; delete button per-item also focusable via Tab
- Manual: open admin tools-grid → focus first tile → press ArrowRight/ArrowDown → focus moves; press Enter → tile activates
- Manual: trigger a form-error save (e.g., invalid agent name) → screen-reader announces the error
- Visual: in light theme, the muted-text labels in topbar/sidebar are clearly readable against the chrome background (subjective check + contrast test confirms ≥4.5:1)
