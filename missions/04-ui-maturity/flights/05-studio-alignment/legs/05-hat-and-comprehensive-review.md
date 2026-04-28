# Leg: 05-hat-and-comprehensive-review

**Status**: completed
**Flight**: [Studio Alignment](../flight.md)

## Objective

Required final HAT pass. Walk the full restructured Studio surface in both themes with the user, verifying the four shipped legs (sidebar restructure, tile grid + confirmDelete, tabbed editor + Test button, dirty-state + confirmDialog modal) work as designed and meet the F4 design-language quality bar. Apply F3 lessons-learned scope guardrails (when "while we're here..." additions surface, weigh divert-to-future-flight explicitly) and F4 lessons-learned (HAT inline fixes that introduce new algorithms or cross-cutting state get a one-shot Developer review before commit; HAT inline fixes track LOC delta against leg-end budgets). Regenerate local visual snapshots if drifted (gitignored per user policy).

This leg is **interactive** — the Flight Director guides the user through verification steps one at a time. Failures dispatch inline fixes (Developer agent if code changes needed); success advances to the next step.

## Context

- Legs 01-04 committed in bundle `3025b65` on branch `flight/05-studio-alignment`. Draft PR #17 open.
- Tests: 407 unit + 176 browser passing. Single `App.router.replaceSub` call site preserved. `window.confirm` removed from studio.js. Both Reviewer and Accessibility Reviewer confirmed at flight-end review (one BLOCKING WCAG 1.3.1 fix applied + one high-value non-blocking listbox/option pair).
- Deferred a11y items from the flight-end review (heading hierarchy: editor title `<h2>` instead of `<h1>`; `.section-title` as `<h3>`; `.section-nav-header` as `<h2>`) — the HAT may surface them visually; user decides whether to fold into this leg or punt to debrief.
- Two known design-system smells captured for future flights: editor's "Delete Agent" button keeps capital-D inline flow (vs lowercase-d via `App.confirmDelete` for tile/chat); migration to canonical helper deferred. `studio.css` 70 LOC vs ≤60 LOC target — flight-log entry rationalizes the area-specific layout overage; F6 or routine-maintenance can consolidate via a canonical `.icon-btn` primitive.

## Verification Plan (interactive)

The Flight Director presents one step at a time. The user performs the step in their browser (and screen reader where noted) and reports the outcome. The Flight Director either advances or dispatches an inline fix.

### Step 1 — Baseline boot
Open the app at `http://localhost:8000/` (or the user's local URL). Confirm the topbar app picker, Chat / Studio / Administration switcher, and theme toggle all render. Switch to Studio. **Pass criterion**: page loads without console errors; URL becomes `#studio` then upgrades to `#studio/agents`.

### Step 2 — Section nav (Agents / Knowledge / Tools)
With Studio open, click each of the three section-nav buttons. **Pass criteria**:
- URL updates: `#studio/agents`, `#studio/knowledge`, `#studio/tools`.
- Active section button shows visual emphasis (`aria-current="page"`).
- Knowledge / Tools render the centered empty-state one-liners exactly as specified.
- Refresh on each URL returns to the same view.

### Step 3 — Section nav keyboard
Tab into the section nav, then use Up/Down arrow keys + Home/End + Enter/Space. **Pass criteria**:
- Up/Down moves focus + highlight only (no URL change until Enter).
- Home jumps to first; End jumps to last.
- Enter or Space activates the focused section (URL updates, active-state moves).
- Roving `tabindex`: only the active section button is in the natural Tab order.

### Step 4 — Tile grid in the Agents section (REVISED — leg 05 layout refinement)
With the Agents section active, observe the agent tile grid in the **main panel** (not the sidebar — see leg 05 inline fix below). **Pass criteria**:
- Sidebar shows ONLY the section-nav (Agents / Knowledge / Tools).
- Main panel shows: page-title `<h1>Agents</h1>` left, "New Agent" button (square-pen icon, mirrors chat's "New Chat" button) right.
- Tiles render in a CSS grid that wraps responsively.
- Each tile shows agent name (large, bold), description (2-line clamp + ellipsis), provider · model footer (monospace).
- Knowledge / Tools sections similarly carry an `<h1>` title in the main panel.

### Step 5 — Tile click → editor (REVISED — tile X removed in leg 05)
Click an existing agent tile. **Pass criteria**:
- Editor opens with the agent's data; URL becomes `#studio/agents/{name}/general` (or whatever tab was last active).
- `aria-selected="true"` on the clicked tile (briefly — tile grid is then hidden as editor takes over the main panel).
- The tile grid is hidden; the editor fills the main panel.

(Leg 05 deliberately removed the per-tile X-button — agent deletion lives in the General tab's Danger Zone instead.)

### Step 6 — OBSOLETE (leg 05 removed the tile X-button)
Skipped — keyboard X-button bubble fix no longer applies.

### Step 7 — Editor structure (REVISED — leg 05 action-cluster refinement)
With an agent selected, observe the editor. **Pass criteria**:
- Top row: agent name + description on the left; `[← Back]  [Cancel]  [Save]` cluster on the right.
- Below: tablist with three tabs (General / Knowledge / Tools).
- Save AND Cancel both initially `disabled` (clean state). Editing any field flips both to enabled; Cancel reverts the form to the saved snapshot.
- Back uses arrow-left icon.
- The Delete button moved into the General tab's Danger Zone (existing agents only). It keeps the capital-D two-step inline flow.

### Step 8 — Tab manual activation (keyboard)
Tab into the tablist. Use Arrow Left / Arrow Right / Home / End. **Pass criteria**:
- Arrows move focus + highlight only — URL stays the same; panel content does NOT swap.
- Home jumps to first tab; End jumps to last.
- Active tab still has `tabindex="0"` even though focused tab differs (browsers honor `.focus()` on `tabindex="-1"`).

Then press Enter or Space. **Pass criteria**:
- Tab commits: URL updates with the new tab segment, panel visibility swaps, `aria-selected` and roving `tabindex` move.

### Step 9 — Tab click + URL refresh
Click each tab (mouse). Refresh the page on each tab URL. **Pass criteria**:
- Click commits the same way Enter does.
- Refresh on `#studio/agents/{name}/general` (or `/knowledge`, `/tools`) returns to that exact tab.

### Step 10 — General tab content
With General tab active, observe the form fields. **Pass criteria**:
- Identity fields: Name (read-only after creation), Description.
- LLM config: provider select + model select; Ollama VRAM warning surfaces when selecting an Ollama model with insufficient VRAM (manual check by selecting an oversize model).
- System prompt textarea.
- Behavior: `max_iterations` numeric input.
- Advanced disclosure (`<details>`/`<summary>`) with disabled Temperature / Top P / Max tokens + "Coming soon" caption.
- Test button: enabled when provider is selected; renders ✓ or ✗ result with `.test-result-ok` / `.test-result-fail` classes (NOT color alone — checkmark/cross icons accompany).

### Step 11 — Test button behavior
With a configured provider selected, click Test. **Pass criteria**:
- POST to `/api/providers/{id}/test` fires; result renders in `aria-live="polite"` span.
- Success: ✓ + detail text + flash success.
- Failure (e.g., unset endpoint): ✗ + detail text + flash error.
- Disabled state: clear the provider select; Test button becomes `disabled` (recomputed on `change`).

### Step 12 — Knowledge & Tools tabs
Switch to Knowledge tab. **Pass criterion**: centered empty-state with the exact two-sentence text about future-flight attachment.

Switch to Tools tab. **Pass criteria**:
- Two `.section-title` headers: "MCP tools" (one-liner stub) and "Built-in tools" (existing 4-category checkbox UI carries forward).
- Built-in tool checkboxes are interactive; toggling a checkbox marks the form dirty.

### Step 13 — Dirty-state Save toggle
Type into any field on any tab. **Pass criteria**:
- Save button becomes enabled.
- Visual emphasis (opacity 1 vs 0.4 disabled).
Click Save. **Pass criteria**:
- Agent saves successfully; flash message confirms.
- Save button returns to disabled (dirty cleared).

### Step 14 — Back-when-dirty modal
Type into a field (don't save). Click Back. **Pass criteria**:
- `App.confirmDialog` modal appears: "Unsaved changes" / "You have unsaved changes. Continue without saving?" / `[Stay] [Continue]` cluster.
- Modal carries `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `aria-describedby`.
- Cancel returns the user to the editor with form state intact, focus restored to Back button.
- Click Back + Continue: navigates to `#studio/agents`; editor unmounts.

### Step 15 — Section-nav-when-dirty modal
With agent selected and dirty, click a section button (Knowledge or Tools). **Pass criterion**: same modal opens. Cancel keeps the user on the editor; Continue switches section.

### Step 16 — Hash-route navigation when dirty (REVISED — leg 05 layout)
With an agent selected and dirty, the tile grid is hidden — there is no UI path to "click another tile". The equivalent dirty-gate path is hash-route navigation to a different agent (e.g. via browser history or a typed URL change), which routes through `selectAgent` via `tryConsumePendingSelect`. **Pass criterion**: same modal opens. Cancel stays put; Continue selects the new agent.

### Step 17 — Tab-when-dirty (REVISED — INVERTED in leg 05)
With agent selected and dirty, click another tab in the editor. **Pass criterion**: tab switches IMMEDIATELY — no modal. Tabs share the form's dirty state, so switching does not lose data. Save remains enabled across the switch.

### Step 18 — Modal focus-trap
With the modal open, press Tab repeatedly. **Pass criteria**:
- Focus cycles: Cancel → Continue → Cancel → ... (and reverse with Shift+Tab).
- Focus does NOT leave the dialog.

### Step 19 — Modal Escape + restore-focus
With the modal open, press Escape. **Pass criteria**:
- Modal closes (calls `onCancel`).
- Focus restores to the trigger element (e.g., the Back button that opened it).

### Step 20 — Beforeunload guard
With agent selected and dirty, attempt to close the tab (or hit refresh). **Pass criteria**:
- Browser shows native "Leave site?" dialog.
- Save the agent first; retry tab close — no dialog (clean state).

### Step 21 — Theme switching
Toggle between the two themes (light/dark or whichever F2 shipped). Walk the full surface again briefly. **Pass criteria**:
- All new primitives respect both themes.
- Modal overlay backdrop, dialog background, tile borders, tab active-state, Test result spans all have adequate contrast in both themes (WCAG AA).

### Step 22 — Accessibility spot-check (optional, if user has SR available)
With NVDA / VoiceOver / Orca running, navigate through:
- Section nav: announced as group with Studio sections; active section announced as current.
- Tile: announced as option with selected state.
- Tab: announced as tab with selected state, points to panel.
- Modal: announced as dialog with title + message; focus moves into dialog on open.
- Test result: announced via `aria-live="polite"`.

### Step 23 — Visual snapshots
If the user runs visual snapshot tests locally, regenerate baselines (gitignored per user-global policy). **Pass criterion**: any drift is visually inspected and accepted by the user.

### Step 24 — User explicit sign-off
After all steps pass: user explicitly confirms the flight is ready to land.

## Acceptance Criteria

- [ ] All 24 verification steps above pass (or fail-and-fix-and-re-verify).
- [ ] Any inline fixes have been applied via Developer agent (with one-shot Developer review per F4 lessons-learned for new algorithms / cross-cutting state).
- [ ] LOC budgets honored: `studio.js` ≤ 1000 + HAT delta; `chat.js` ≤ 605 (no expected change).
- [ ] If new patterns emerged during HAT, `agents.md` is updated.
- [ ] If new mission-level Known Issues surfaced, the mission's Known Issues section is updated.
- [ ] All four committed legs (01-04) checked off in `flight.md`; this leg (05) checked off after HAT signs off.
- [ ] Flight status `in-flight` → `landed`.
- [ ] User explicitly approves before flight closes.

## Verification Steps

- The 24 interactive steps above ARE the verification.
- After all steps pass, run baseline tests once more to confirm no regression: `pytest --timeout=60 tests/` (407) and `pytest --timeout=120 -m browser tests/browser/` (176 + any new tests added inline during HAT).

## Implementation Guidance

- **NOT autonomous**. The Flight Director guides; the human performs.
- One step at a time. Wait for the user to report results before advancing.
- On failure: diagnose, dispatch Developer agent if code changes are needed, re-verify that step, then proceed.
- F3 lessons-learned: when the user surfaces "while we're here..." additions, ASK explicitly: "Add to this leg, or divert to a future flight?" Default: divert.
- F4 lessons-learned: HAT inline fixes that grow studio.js or chat.js track LOC delta against leg-end budgets; new algorithms or cross-cutting state changes get a one-shot Developer review before commit.
- After all steps pass: spawn a Developer to commit the HAT changes (if any) + flight.md update + this leg's status `ready` → `completed` + flight status `in-flight` → `landed`. Use the bundled-flight commit pattern.

## Files Affected

- `missions/04-ui-maturity/flights/05-studio-alignment/legs/05-hat-and-comprehensive-review.md` — this file (status updates).
- `missions/04-ui-maturity/flights/05-studio-alignment/flight.md` — leg 05 checkbox + flight status.
- `missions/04-ui-maturity/flights/05-studio-alignment/flight-log.md` — HAT progress entry; any deviations or fixes applied inline.
- Possibly: `the_one/agents.md`, the F5 source files (if HAT surfaces fixes), `mission.md` (if a new mission-level Known Issue emerges).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:flight]`:**

- [ ] All 24 verification steps passed (or failed-and-fixed-and-re-verified)
- [ ] Inline fixes (if any) reviewed and committed
- [ ] User explicitly approved
- [ ] `agents.md` / `mission.md` updated if applicable
- [ ] Flight log HAT entry populated with: steps walked, deviations, anomalies, user feedback
- [ ] This leg's status set to `completed`
- [ ] All five legs checked off in `flight.md`
- [ ] Flight status set to `landed`
- [ ] Final HAT-bundle commit pushed to `origin/flight/05-studio-alignment`
- [ ] Draft PR #17 marked ready for review
- [ ] Signal `[COMPLETE:flight]`
