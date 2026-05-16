# Leg: 02-form-errors-tokens-and-sweep

**Status**: ready
**Flight**: [Accessibility Carry-forward](../flight.md)

## Objective

Resolve the remaining Action Required a11y findings — form-field error programmatic association (A.2 in this report; A.6 in the prior; second pass running) and light-theme `--fg-muted`/`--fg-faint` contrast on `--shell-chrome-bg` (F3.5 carry-forward) — and opportunistically sweep the medium/low-severity a11y items from the maintenance report.

## Context

A.2 (form-field error association) is the strongest indicator of accumulating a11y debt: the prior maintenance report (2026-05-04 §A.6) flagged it Advisory; M08 didn't address it; the 2026-05-15 report re-flagged with elevated severity. The Architect's framing: "second pass running on the same a11y finding indicates the carry-forward mechanism isn't enforcing." Close it this pass.

A.3 (light-theme contrast) is F3.5's deferred item. The token `--fg-muted: #64748b` against `--shell-chrome-bg: #d4d8df` produces ≈3.3:1 (text AA fail, UI-3:1 pass). `--fg-faint: #94a3b8` against the same is ≈1.85:1 (fail both). Token comment at `tokens.css:242-243` acknowledges faint is "AA-borderline." Two fix-shapes: (a) darken `--fg-muted` on light theme globally (could cascade through unrelated surfaces); (b) scope its usage so muted-text on chrome surfaces explicitly uses `--fg-tertiary` (#475569, AA-passing). The flight's adaptation criteria say roll back to (b) if (a) cascades; this leg starts with (a) — it's the cleaner conceptual fix — and pivots if needed.

The sweep items are mostly one-liner each. They cluster in this leg because (i) they share the same touch surface as A.2/A.3, (ii) atomic sub-commits keep them revertible, (iii) bundling avoids the alternative of either a third flight or letting them rot to a future maintenance pass.

## Inputs

- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js:517-521` — `renderFieldErrors` site appending `<span class="field-error">`
- `the_one/interfaces/web/static/css/areas/admin.css:362-368` — per-row red error styling
- `the_one/interfaces/web/static/css/tokens.css:242-243` — `--fg-muted` / `--fg-faint` light-theme variants
- `the_one/interfaces/web/static/css/tokens.css:404-413` — existing `prefers-reduced-motion` token zeroing
- `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js:18-21` — JS-driven Braille spinner setInterval
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js:20-21, 44-47` — overlay markup with `role="status"` + shorthand labels
- `the_one/interfaces/web/static/css/areas/chat.css:67, 75` — telemetry visual style
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:338-339` — `alt={MIME}` on icon
- `the_one/interfaces/web/static/js/app.js:241-244` — toast auto-dismiss timing
- `the_one/interfaces/web/static/js/areas/admin/provider-models.js:347, 376` — `indicator-led` instances without aria-label
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:486-489` — `indicator-led` instances WITH aria-label
- `the_one/interfaces/web/static/css/components.css:861` — `indicator-led` primitive
- `the_one/interfaces/web/static/js/layout/section-nav.js:34-92` — `role="group"` site
- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js:33-35` — `aria-hidden` count
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js:67-70` — tool toggle with `title=` only
- `README.md` — top-level project README
- `tests/test_design_tokens_a11y.py:187-191` — existing contrast test
- Existing or new browser tests that exercise form errors

## Outputs

- A.2: form-field errors carry `aria-invalid="true"` + `aria-describedby` to a generated id; `role="alert"` on first error per save cycle
- A.3: light-theme `--fg-muted` darkened (or `--fg-tertiary` substituted at chrome-text sites); contrast test green at AA
- A.5: toast extended to ≥5s OR pause-on-hover/focus + close button
- A.6: MCP server icon `alt=""` when decorative (title text alongside)
- A.7: thinking-indicator setInterval gated on `prefers-reduced-motion`
- A.8: telemetry overlay row-level `aria-label` (or container-only label + child `aria-hidden`); opacity bumped
- A.9: `indicator-led` primitive contract documented in `components.css`; call sites swept to match
- A.10: `section-nav.js` `role="group"` dropped or upgraded to `role="tablist"`
- A.11: trace-shell summary includes count in `aria-label`
- A.12: tool toggle visible (or visually-hidden) state label
- A.13: README "Accessibility" section added

## Acceptance Criteria

- [ ] Triggering a save with invalid form data: the input has `aria-invalid="true"`; the error span has a generated id; the input's `aria-describedby` includes that id; screen reader announces the error (manual verification with VoiceOver/NVDA/Orca, OR DOM inspection confirming the wiring)
- [ ] `pytest tests/test_design_tokens_a11y.py -v` reports the light-theme `--fg-muted` vs `--shell-chrome-bg` test as PASS at WCAG AA 4.5:1 (or the test is parametrized cleanly to capture only the surfaces where muted-on-chrome is acceptable)
- [ ] Toast dismiss timing ≥5s OR pause-on-hover behavior verified
- [ ] MCP server icon does NOT emit `alt="image/png"` (decorative path emits `alt=""`)
- [ ] Thinking-indicator JS spinner does NOT update content when `prefers-reduced-motion: reduce` is active (verify by setting OS preference or `document.documentElement.style.setProperty('--reduce-motion', '1')`-equivalent + JS check)
- [ ] Telemetry overlay row-level labeling is appropriate; opacity is ≥0.7 by default
- [ ] `indicator-led` primitive has a contract documented in `components.css` (a comment block describing labeling expectations); call sites are consistent
- [ ] `section-nav.js` `role="group"` is replaced with appropriate semantic
- [ ] Trace-shell summary's accessible name includes the count
- [ ] Tool toggle has a visible (or visually-hidden) state label
- [ ] README has an "Accessibility" section
- [ ] Broad pytest exits 0
- [ ] Ruff baseline preserved (0/0)
- [ ] Local pixel baselines regenerated after token change (gitignored)

## Verification Steps

- Manual A.2: open Studio → edit an agent → save with empty name → inspect DOM via DevTools: confirm `aria-invalid="true"` on input, `aria-describedby` references the error span id, error span has `role="alert"` or is announced
- `cd /home/cprch/projects/the-one && pytest tests/test_design_tokens_a11y.py -v` → relevant tests PASS
- Manual A.5: trigger a toast (e.g., agent save success); verify it persists ≥5s OR has pause-on-hover + close button
- Inspect DOM for MCP server tile: `alt=""` when icon present; `alt={meaningful}` only if non-decorative
- Manual A.7: set OS `prefers-reduced-motion: reduce` → trigger thinking-indicator → confirm no animation update OR very slow update
- Manual A.8: inspect telemetry overlay DOM; verify row-level labels; verify visual opacity ≥0.7
- `cd /home/cprch/projects/the-one && grep -A5 "indicator-led" the_one/interfaces/web/static/css/components.css` — contract comment present
- `cd /home/cprch/projects/the-one && grep "role=\"group\"\|role=\"tablist\"" the_one/interfaces/web/static/js/layout/section-nav.js` — appropriate role
- Manual A.11: inspect trace-shell DOM; `summary aria-label` includes count
- Manual A.12: inspect tools-grid; toggle has visible state context
- `cd /home/cprch/projects/the-one && grep -i "accessibility\|wcag" README.md` — section present
- `cd /home/cprch/projects/the-one && pytest --tb=no -q` → exit 0
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` → both exit 0

## Implementation Guidance

This leg has 8 firm sub-tasks + 3 opportunistic ones (A.9, A.10, A.13). Sequence by risk: contrast fix first (smallest blast-radius approach), form-field error wiring next (highest a11y significance — second pass running), then mechanical sweep, then opportunistic items if time permits.

1. **A.3 light-theme contrast — lead with scope-the-usage, NOT global token change**
   - Architect spot-check (Phase 4b mission validation) found that the prior leg flow's "Attempt A" (darken `--fg-muted` globally) would cascade through `.oauth-callback-detail`, telemetry overlay, session-item-agent, and likely many pixel-snapshot baselines. Plan the leg with the scope-the-usage approach as the PRIMARY path.
   - Read `the_one/interfaces/web/static/css/tokens.css` around the light-theme `--fg-muted` definition (current value `#64748b`, around line 247 — locate by token name, not line number)
   - Enumerate the chrome-text consumer sites by `grep -rn 'var(--fg-muted)' the_one/interfaces/web/static/css/` and filter to those used on `--shell-chrome-bg` surfaces (topbar, sidebar). Likely candidates: topbar CSS, sidebar CSS, possibly `areas/layout/section-nav.css`.
   - At each chrome-text site, replace `var(--fg-muted)` with `var(--fg-tertiary)` (already `#475569`, AA-passing on `--shell-chrome-bg`)
   - Re-run `pytest tests/test_design_tokens_a11y.py -v` — verify the relevant test(s) now PASS. If the test is parametrized in a way that conflicts with scope-the-usage (e.g., it tests `--fg-muted` directly against `--shell-chrome-bg`), update the test parametrization to reflect the new intent ("muted-text on chrome surfaces uses `--fg-tertiary`")
   - Visually inspect the app (light theme) to confirm the chrome text is now readable and no unwanted surfaces darkened
   - **Fallback to Attempt A only if scope-the-usage proves intractable** (e.g., the consumer sites all use a shared partial that can't be scoped without restructuring). If A is needed, document the cascading sites and budget time for pixel-baseline regen.
   - Regenerate local pixel baselines (gitignored per project convention)
   - Sub-commit: `a11y(tokens): scope --fg-tertiary at chrome-text sites for light-theme AA`

2. **A.2 form-field error wiring (HIGH significance — second pass running)**
   - Locate `renderFieldErrors` in `admin/tools-form-helpers.js:517-521`
   - Generate an id per error span: `errorId = field.id + '-error'` (or use a uuid if no field.id)
   - Add `aria-invalid="true"` to the matching input
   - Add `aria-describedby={errorId}` to the input (additively if already set from info-icon pattern: split existing value on space, dedup, rejoin)
   - Add `role="alert"` to the first error span per save cycle (or to a banner element if save-side errors group)
   - Verify the existing `.field-error` CSS still renders correctly; adjust if id-based selector is needed
   - Sub-commit: `a11y(forms): aria-invalid + aria-describedby + role=alert on field errors`

3. **A.6 MCP icon alt-text (LOW risk, mechanical)**
   - Edit `studio/mcp-server-editor.js:338-339`
   - Change `alt={icon_mime}` to `alt=""` (decorative path); the title text is rendered alongside at line 343
   - Sub-commit: `a11y(mcp): drop MIME alt-text on decorative icons`

4. **A.7 thinking-indicator reduced-motion gate**
   - Edit `chat/thinking-indicator.js:18-21`
   - Wrap the `setInterval` call in a `window.matchMedia('(prefers-reduced-motion: reduce)').matches` check
   - If reduced motion: render a single static "thinking…" string and skip the interval
   - Sub-commit: `a11y(chat): thinking-indicator honors prefers-reduced-motion`

5. **A.5 toast duration**
   - Edit `app.js:241-244` — extend the dismiss timeout to 5000ms (or 5500ms)
   - Optional improvement: add a close-button affordance to the toast; pause auto-dismiss on hover/focus. Bracket the leg's success on the simple duration bump; the close-button is opportunistic.
   - Sub-commit: `a11y(toast): extend auto-dismiss to 5s (WCAG 2.2.1/2.2.3)`

6. **A.8 telemetry overlay labeling + opacity**
   - Edit `chat/telemetry-overlay.js:20-21, 44-47`
   - Pick ONE approach: (a) add `aria-label` to each row (e.g., `"Input tokens"`) and keep `role="status"` → polite-live will re-announce per-row; OR (b) mark each row's inner spans `aria-hidden="true"` and rely on the container `aria-label` ("Token usage") — terser, less churn
   - Bump default visual opacity from 0.4 → 0.7 (or use `var(--fg-tertiary)` directly)
   - Sub-commit: `a11y(telemetry): row labels + opacity bump`

7. **A.9 `indicator-led` labeling discipline** — OPPORTUNISTIC (drop at first sign of leg slippage)
   - Add a comment block at the `indicator-led` primitive definition in `components.css` (locate by class name) describing the contract: "When the LED's state is fully conveyed by adjacent visible text, the LED MUST carry `aria-hidden=\"true\"`. Otherwise, the LED MUST carry an `aria-label` describing its state."
   - Sweep call sites: `provider-models.js` LED instances → add `aria-hidden="true"` (text label is adjacent); `mcp-server-editor.js` already has `aria-label`, leave it
   - Sub-commit: `a11y(led): document contract + sweep call sites`
   - **Slip rule**: if the LED-contract conversation surfaces design ambiguity (e.g., what about LEDs in tooltips without adjacent text?), drop this item and route to next maintenance pass

8. **A.10 `section-nav.js` role** — OPPORTUNISTIC (drop at first sign of leg slippage)
   - Edit `the_one/interfaces/web/static/js/areas/layout/section-nav.js` (NOTE: path is `areas/layout/`, not `layout/` — Architect spot-check fix)
   - Choose between dropping `role="group"` entirely (let surrounding `<nav>` provide semantic) OR upgrading to `role="tablist"` + `role="tab"` + `aria-controls` per tab
   - Recommend dropping `role="group"`; the `<nav>` wrapper provides the right semantic + the current `aria-current="page"` is already correct for the navigation role
   - Sub-commit: `a11y(section-nav): drop role=group; rely on nav landmark`
   - **Slip rule**: if the role-drop affects an existing screen-reader behavior the operator relies on, pivot to `role="tablist"` or skip entirely; route to next maintenance pass

9. **A.11 trace-shell count in aria-label**
   - Edit `chat/trace-shell.js:33-35`
   - When the count text updates, ALSO update the summary's `aria-label` to include the count: `summary.setAttribute('aria-label', \`Tool activity, ${count} ${count === 1 ? 'item' : 'items'}\`)`
   - Sub-commit: `a11y(trace): include count in summary accessible name`

10. **A.12 tool toggle visible state label**
    - Edit `admin/tools-grid.js:67-70`
    - Add a `<span class="visually-hidden">` (utility already exists) with the state text: "Enabled for all agents" / "Disabled for all agents"
    - Drop reliance on `title=` (or keep it for sighted-mouse users; add the visually-hidden span as the screen-reader path)
    - Sub-commit: `a11y(tools): visually-hidden state label on tool toggle`

11. **A.13 README accessibility section** — OPPORTUNISTIC (drop at first sign of leg slippage)
    - Edit `README.md`
    - Add a brief section, e.g.:
      ```markdown
      ## Accessibility

      GleepGlorp AI targets WCAG 2.1 AA. The UI is keyboard-operable end-to-end, honors `prefers-reduced-motion` (animations collapse to instant), and meets minimum contrast on both light and dark themes. The design language gallery (Admin → Design Language, dev-mode) is the canonical reference for tokens, components, and indicator vocabulary.

      Known gaps and ongoing accessibility work are tracked in `maintenance/` reports. To report an accessibility issue, [open a GitHub issue](https://github.com/msieurthenardier/the-one/issues) with the `accessibility` label.
      ```
    - Sub-commit: `docs(readme): accessibility section`
    - **Slip rule**: if README section placement requires reading the file end-to-end + voice-matching takes more than 15 minutes, route to next maintenance pass; this is the lowest-impact item in the bundle

12. **Verify all sub-fixes**
    - `cd /home/cprch/projects/the-one && pytest --tb=no -q` — exit 0
    - `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both exit 0
    - Run manual a11y checks per the verification steps

13. **Regenerate local pixel baselines** if the A.3 token change affected pixel-snapshot test surfaces (likely it did)
    - `make snapshot-update` or equivalent
    - Note: baselines are gitignored; this is local-only

## Edge Cases

- **A.2 wiring conflicts with existing info-icon `aria-describedby`**: if the input already has `aria-describedby="<field-id>-desc"` from the info-icon pattern, append the error id additively. Split the value on whitespace, dedupe, rejoin.
- **A.3 token cascade unacceptable**: pivot to Attempt B (scope `--fg-tertiary` at chrome-text sites). Document the decision in flight log.
- **A.5 close-button addition** breaks an existing toast test that asserts content shape: scope the close-button improvement out and accept the simple duration bump.
- **A.7 reduced-motion gate makes thinking-indicator look broken** to QA: the WCAG 2.3.3 guideline is AAA so this is judgment-call territory. If "broken" perception outweighs the a11y benefit, leave the spinner running and document A.7 as accepted-trade-off in flight log + maintenance report.
- **A.10 `role="group"` removal breaks a screen-reader navigation expectation**: revert and use `role="tablist"` route instead. The functional `aria-current="page"` semantic is the load-bearing part.
- **A.13 README accessibility section conflicts with existing structure**: place it after the "Architecture" section or before "Mission Control" pointer; match the file's existing voice.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — A.3 (light-theme `--fg-muted` token)
- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` — A.2 (form-field error wiring)
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — A.6 (MCP icon alt)
- `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js` — A.7 (reduced-motion gate)
- `the_one/interfaces/web/static/js/app.js` — A.5 (toast duration)
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` + `static/css/areas/chat.css` — A.8 (telemetry labels + opacity)
- `the_one/interfaces/web/static/css/components.css` — A.9 (LED contract comment)
- `the_one/interfaces/web/static/js/areas/admin/provider-models.js` — A.9 (sweep)
- `the_one/interfaces/web/static/js/layout/section-nav.js` — A.10 (role)
- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` — A.11 (count in label)
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` — A.12 (state label)
- `README.md` — A.13 (accessibility section)
- Possibly `tests/test_design_tokens_a11y.py` (parametrization adjustment if Attempt B)
- `flight-log.md` — Leg Progress with sub-commit list + manual test outcomes

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Manual a11y checks documented in flight log
- [ ] Light-theme contrast test PASS
- [ ] Broad pytest exits 0
- [ ] Ruff baseline preserved
- [ ] Local pixel baselines regenerated (if A.3 caused drift)
- [ ] Update `flight-log.md` with leg progress entry (one sub-section per sub-fix is helpful for review)
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in `flight.md`
- [ ] If final leg of the flight:
  - [ ] Update `flight.md` status to `landed`
  - [ ] Check off this flight in `mission.md`
- [ ] Commit all changes (per-sub-fix commits already landed; ensure flight artifacts are also committed)
