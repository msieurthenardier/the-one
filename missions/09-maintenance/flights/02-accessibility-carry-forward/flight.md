# Flight: Accessibility Carry-forward + F1 Tech-Debt Cleanup

**Status**: completed
**Mission**: [Maintenance (Post-M08)](../../mission.md)

## Contributing to Criteria

**Accessibility (existing scope)**:
- [x] Chat welcome agent picker has roving-tabindex + ArrowUp/ArrowDown/Home/End working with `aria-selected` toggling; pattern lifted from `areas/layout/section-nav.js:71-91`
- [x] Session-list restructured: `role="listbox"`/`role="option"` removed; replaced with `<nav>` + `<ul>` of `<button>`; affected browser test assertions in `tests/browser/test_flow_keyboard.py` updated to match
- [x] Admin tools-grid verified keyboard-accessible (already a button-grid post-M08 F5, NOT a listbox — no role change)
- [x] Form-field errors carry `aria-invalid="true"` + `aria-describedby` to a generated id; `role="alert"` on first error per save cycle
- [x] Light-theme `--fg-muted` (and `--fg-faint` where used on shell chrome) meet WCAG AA contrast against `--shell-chrome-bg` via scope-the-usage approach (use `--fg-tertiary` at chrome-text consumer sites rather than darkening `--fg-muted` globally)

**F1 tech-debt carry-forward (added 2026-05-16 from F1 debrief — non-methodology recommendations)**:
- [x] `Makefile` gains `rebuild-browsers` target combining `make rebuild` + `docker exec the-one playwright install chromium` (breaks the recurring "rebuild wipes Chromium" foot-gun flagged in F5/F6/F6.5/F7/F1 debriefs)
- [x] `agents.md` `### live-read-across-lazy-resolver-boundary` entry's test citation fixed (cites `test_max_context_tokens_live_read_across_resolver` in `tests/test_agent_core.py` — neither exists; actual test is `test_usage_event_reflects_live_max_context_tokens_at_emission` in `tests/test_process_and_broadcast_live_read.py`)
- [x] `agents.md ## Project Conventions` gains a new `### host-side-bench-drift-detection` entry codifying the host-side `make doctor` / `make audit` convention (asymmetry from container-first `make lint`/`make format`)
- [x] `make doctor` target shifts from bare `python -c ...` to `.venv/bin/python -c ...` to match `make audit`'s shape (fixes sub-shell `python`-not-on-PATH foot-gun surfaced in F1 Leg 3)
- [x] `Makefile` gains `audit-bytes` target: `git grep -lP "[\x{2028}\x{2029}]"` against the_one/ and tests/ returns empty (catches raw U+2028/U+2029 LSEP/PSEP characters in source — the class of bug F1 Leg 3 implementation almost shipped)
- [x] `agents.md` (or `SECURITY-MODEL.md`) documents the npm-spec regex pattern (`^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$`) as a reusable security primitive for "operator-supplied identifiers that flow into filesystem paths or subprocess argv must be validated against a spec-grounded allowlist, NOT a permissive character class" — references `_VALID_NPX_PKG_RE` as the exemplar

---

## Pre-Flight

### Objective

Resolve the three Action Required accessibility findings from the 2026-05-15 maintenance report — two of which (A.2 form-field errors, A.3 light-theme contrast) are second-pass-running carry-forwards — opportunistically sweep the medium/low-severity a11y items in the same touch surface, **and bundle in the F1 debrief's non-methodology carry-forward recommendations** (Makefile/docs/tooling cleanup) since they're small, atomic, and avoid letting tech-debt rot to a future maintenance pass.

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

- [ ] Flight 1 (Code Hygiene + Concourse Removal) completed (status `completed`) — F1 dependencies: ruff 0/0 baseline; `make doctor` + `make audit` exist; `_safe_script_json` / `_clean_npx` / `_can_unshare_user_namespace` helpers in place
- [ ] **Chromium restoration** (per F1 debrief): `make _ensure-playwright` invoked once at flight start. The existing `_ensure-playwright` target at `Makefile:39-46` conditionally installs Chromium when absent — it's already wired into `make test-browser` and `make test-pixel`, so the F1 debrief's "312 ERRORS at setup" came from bypassing `make` and calling raw `docker exec the-one pytest` (Architect spot-check during F2 design review confirmed). Leg 3 sub-fix (a) adds `rebuild-browsers` as a convenience target that chains `rebuild + _ensure-playwright`. **Net change to F2 verification**: switch any raw `docker exec the-one pytest -m browser` calls to `make test-browser`, which auto-restores via the existing machinery.
- [ ] No outstanding browser-test failures from Flight 1's commits (broad pytest exits 0 — confirmed at F1 close at 1700 passed host + container)
- [ ] Local Playwright can run pixel tests via `make test-pixel` (also chains `_ensure-playwright` automatically)
- [ ] **Branch strategy**: F2 work happens on a new branch `flight/02-accessibility-and-cleanup` branched off `flight/01-integrity-gate-restoration` (NOT off `main` — F1's commits aren't on `main` yet; F2's legs reference F1 commits as preconditions). Rebase F2 onto `main` after PR #56 merges. Set via `git checkout flight/01-integrity-gate-restoration && git checkout -b flight/02-accessibility-and-cleanup`.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites identified
- [x] Validation approach defined (each WCAG criterion verified per leg; pixel baselines regenerated locally after token changes per project convention — baselines are gitignored)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Three legs.

**Leg 1 (Welcome picker keyboard + session-list restructure + tools-grid verify)**: copy the roving-tabindex pattern from `areas/layout/section-nav.js:71-91` into the chat welcome agent picker (`areas/chat/welcome.js`). This is the one site that needs the treatment; helper extraction is moot with one consumer. For the session-list, replace `role="listbox"` / `role="option"` with `<nav>` + `<ul>` of `<button>` items; the per-item delete button becomes a sibling rather than a child; update `tests/browser/test_flow_keyboard.py` assertions accordingly. For tools-grid, verify keyboard accessibility of the existing button-grid (no role change — already migrated in M08 F5 leg 02). Verify with manual keyboard testing (Tab, Shift+Tab, Arrow keys, Enter, Escape).

**Leg 2 (Form errors + tokens + sweep)**: A.2 form-field error wiring (`aria-invalid` + `aria-describedby` + `role="alert"`) — locate `renderFieldErrors` site and wire up the association. A.3 light-theme contrast — lead with scope-the-usage: enumerate chrome-text consumer sites (topbar, sidebar) and switch them from `var(--fg-muted)` to `var(--fg-tertiary)`; verify with `tests/test_design_tokens_a11y.py`. A.5 toast extend to 5s. A.6 MCP icon `alt=""` when decorative. A.7 thinking-indicator `prefers-reduced-motion` gate. A.8 telemetry overlay labeling + opacity. A.11 trace-shell count include in `aria-label`. A.12 tool toggle visible state label.

**Opportunistic in Leg 2 (drop at first sign of leg slippage)**: A.9 `indicator-led` labeling discipline (contract docs + call-site sweep); A.10 `section-nav` `role="group"` → drop or `role="tablist"`; A.13 README accessibility section.

**Leg 3 (F1 tech-debt + tooling cleanup — NEW per F1 debrief recommendations)**: 6 atomic small fixes bundled because they share the same touch surface (Makefile + agents.md):
- (a) `Makefile`: new `rebuild-browsers` target chaining `make rebuild` + `docker exec the-one playwright install chromium` so the recurring "rebuild wipes Chromium" foot-gun stops recurring.
- (b) `Makefile`: shift `doctor` target's `python -c ...` to `.venv/bin/python -c ...` (matches `audit` target's shape; fixes sub-shell `python`-not-on-PATH foot-gun surfaced in F1 Leg 3).
- (c) `Makefile`: new `audit-bytes` target: `git grep -lP "[\x{2028}\x{2029}]" -- 'the_one/*.py' 'tests/*.py'` returns empty; non-zero exit if raw LSEP/PSEP found.
- (d) `agents.md` `### live-read-across-lazy-resolver-boundary` (line ~233): fix the test citation (currently `test_max_context_tokens_live_read_across_resolver` in `tests/test_agent_core.py` — neither exists; replace with `test_usage_event_reflects_live_max_context_tokens_at_emission` in `tests/test_process_and_broadcast_live_read.py:98`).
- (e) `agents.md ## Project Conventions`: new `### host-side-bench-drift-detection` entry codifying the host-side `make doctor` / `make audit` convention as peer to `### gated-debug-instrumentation`.
- (f) `agents.md` (or `SECURITY-MODEL.md`): new entry documenting npm-spec regex as a reusable security primitive. Reference `_VALID_NPX_PKG_RE` at `mcp/cache_cleanup.py:71-83` as the exemplar.

Each finding in Leg 3 gets a separate sub-commit, like Leg 2's atomic-sub-commit pattern. Most are 1-5 line edits. Estimated leg size: ~1-2 hours.

Each finding gets a separate sub-commit inside its leg so reverting any one item is clean. If a sub-fix surfaces a deeper issue, document it in the flight log Anomalies section and decide whether to scope it out.

### Checkpoints

- [ ] Leg 1: three listbox sites have correct keyboard semantics; session-list structural fix landed; manual keyboard test passed across all three; `tests/browser/test_flow_keyboard.py` assertions updated
- [ ] Leg 2: form-field error wiring landed; light-theme contrast test green; all firm sweep items landed with sub-commits; opportunistic items either landed or explicitly skipped with reason
- [ ] Leg 3: 6 sub-fixes landed; `make doctor`/`make audit`/`make audit-bytes`/`make rebuild-browsers` all functional; `agents.md` citation fix + new conventions land cleanly
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

- [x] `01-listbox-keyboard-and-structure` — Welcome agent picker: roving-tabindex + arrow keys. Session-list: drop listbox semantic, restructure to nav+buttons, update affected browser test assertions. Tools-grid: verify keyboard accessibility (no role change).
- [x] `02-form-errors-tokens-and-sweep` — Form-field error wiring; light-theme chrome-text contrast via scope-the-usage; firm sweep (A.5/A.6/A.7/A.8/A.11/A.12). Opportunistic (drop if leg slips): A.9, A.10, A.13.
- [x] `03-f1-techdebt-and-tooling-cleanup` — Bundle of 6 F1-debrief carry-forward fixes (non-methodology): `make rebuild-browsers`; `make doctor` venv-python fix; `make audit-bytes`; agents.md live-read citation fix; agents.md `### host-side-bench-drift-detection` convention; npm-spec regex documented as security primitive.

---

## Post-Flight

### Completion Checklist

- [ ] All THREE legs completed
- [ ] All success criteria contributing to this flight checked off (accessibility + F1 tech-debt bundle)
- [ ] Manual keyboard navigation works correctly in welcome picker + session list + tools-grid
- [ ] Form-field error announcements work (verify with VoiceOver / NVDA / Orca screen-reader test if available; otherwise inspect DOM)
- [ ] Light-theme contrast test passes (the existing test in `test_design_tokens_a11y.py` or equivalent)
- [ ] Local pixel baselines regenerated (gitignored, local-only)
- [ ] Broad pytest exits 0
- [ ] Browser pytest passes (`make test-browser` — auto-restores Chromium via existing `_ensure-playwright`)
- [ ] Ruff baseline preserved (0/0 from F1)
- [ ] `make doctor` / `make audit` / `make audit-bytes` / `make rebuild-browsers` all functional
- [ ] Flight debrief run (per M08 lesson)
- [ ] Mission flight checkbox checked

### Verification

- `cd /home/cprch/projects/the-one && pytest --tb=no -q` → exit 0
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` → both exit 0
- `cd /home/cprch/projects/the-one && make test-browser` → exit 0 (auto-restores Chromium via existing `_ensure-playwright` if absent; preferred over raw `docker exec` to leverage existing machinery)
- `cd /home/cprch/projects/the-one && make doctor` (HOST) → exit 0 `doctor: ok`
- `cd /home/cprch/projects/the-one && make audit` (HOST) → runs, prints any findings, exits 0 (non-blocking)
- `cd /home/cprch/projects/the-one && make audit-bytes` → exit 0 (no raw LSEP/PSEP)
- `cd /home/cprch/projects/the-one && grep "test_usage_event_reflects_live_max_context_tokens_at_emission" the_one/agents.md` → match (citation fix landed)
- `cd /home/cprch/projects/the-one && grep "^### host-side-bench-drift-detection" the_one/agents.md` → match (new convention landed)
- Manual: open chat → click in welcome agent picker → press ArrowDown → focus moves to next agent → press Enter → agent selected
- Manual: open chat → focus session list → press Tab through items → each item focusable; delete button per-item also focusable via Tab
- Manual: open admin tools-grid → focus first tile → press ArrowRight/ArrowDown → focus moves; press Enter → tile activates
- Manual: trigger a form-error save (e.g., invalid agent name) → screen-reader announces the error
- Visual: in light theme, the muted-text labels in topbar/sidebar are clearly readable against the chrome background (subjective check + contrast test confirms ≥4.5:1)
