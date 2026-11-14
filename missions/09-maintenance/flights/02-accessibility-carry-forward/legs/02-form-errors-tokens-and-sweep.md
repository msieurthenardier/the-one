# Leg: 02-form-errors-tokens-and-sweep

**Status**: completed
**Flight**: [Accessibility Carry-forward + F1 Tech-Debt Cleanup](../flight.md)

## Objective

Resolve the remaining Action Required a11y findings — form-field error programmatic association (A.2 in this report; A.6 in the prior; second pass running) and light-theme `--fg-muted`/`--fg-faint` contrast on `--shell-chrome-bg` (F3.5 carry-forward) — and opportunistically sweep the medium/low-severity a11y items from the maintenance report.

## Context

A.2 (form-field error association) is the strongest indicator of accumulating a11y debt: the prior maintenance report (2026-05-04 §A.6) flagged it Advisory; M08 didn't address it; the 2026-05-15 report re-flagged with elevated severity. The Architect's framing: "second pass running on the same a11y finding indicates the carry-forward mechanism isn't enforcing." Close it this pass.

A.3 (light-theme contrast) is F3.5's deferred item. The token `--fg-muted: #64748b` against `--shell-chrome-bg: #d4d8df` produces ≈3.3:1 (text AA fail, UI-3:1 pass). `--fg-faint: #94a3b8` against the same is ≈1.85:1 (fail both). Token comment at `tokens.css:242-243` acknowledges faint is "AA-borderline." Two fix-shapes: (a) darken `--fg-muted` on light theme globally (could cascade through unrelated surfaces); (b) scope its usage so muted-text on chrome surfaces explicitly uses `--fg-tertiary` (#475569, AA-passing). The flight's adaptation criteria say roll back to (b) if (a) cascades; this leg starts with (a) — it's the cleaner conceptual fix — and pivots if needed.

The sweep items are mostly one-liner each. They cluster in this leg because (i) they share the same touch surface as A.2/A.3, (ii) atomic sub-commits keep them revertible, (iii) bundling avoids the alternative of either a third flight or letting them rot to a future maintenance pass.

## Inputs

(Line refs verified during cycle-1 design review on 2026-05-16; locate by symbol where line numbers may drift.)

- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` — `renderFieldErrors` function spans **L493-536**; per-row mutation site (where `row.classList.add('field-error-highlight')` + span append happens) at **L513-521**. The function also needs to QUERY the input inside the row (`row.querySelector('input, select, .chip-list-editor')` — see Step 2 for the additivity sequence). Existing `aria-describedby` pattern from info-icon at L106-119 + L130-134; `dataAttrs += ' aria-describedby="' + descId + '"'` lands on the wrapping div for chip-list-editor (not on the inner chip input).
- `the_one/interfaces/web/static/css/areas/admin.css:362-368` — per-row red error styling
- `the_one/interfaces/web/static/css/tokens.css` — `--fg-muted` at **L247** (`#64748b` light); `--fg-faint` at **L248** (`#94a3b8` light); `--fg-tertiary` at **L246** (`#475569`, AA-passing chrome-text target); `--shell-chrome-bg` at **L447** (`#d4d8df` light). Locate by token name, not line number. The "AA-borderline" comment is at L242-243 (above the definitions).
- `the_one/interfaces/web/static/css/tokens.css:404-413` — existing `prefers-reduced-motion` token zeroing
- `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js:18-21` — JS-driven Braille spinner setInterval
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js:20-21, 44-47` — overlay markup with `role="status"` + shorthand labels
- `the_one/interfaces/web/static/css/areas/chat.css` — telemetry overlay visuals at **L80** (`.telemetry-overlay { opacity: 0.4; color: var(--fg-muted); }`) + **L88** (`.telemetry .label { color: var(--fg-faint); }`). Earlier line refs in this leg (`:67, 75`) were WRONG — those were `new-chat-header` rules.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:337-340` — `<img>` tag with a ternary `icons[0].mimeType ? alt=icons[0].mimeType : alt=""` (drop the ternary, always emit `alt=""` — see Step 3)
- `the_one/interfaces/web/static/js/app.js:233, 235, 244` — toast role wiring (`role="alert"` on error at L233; `role="status"` on success at L235) is already correct; the dismiss timeout literal `2000` is at L244. WCAG 2.2.1 concern is partially mitigated by the `role` semantics; the duration bump is for visual-reading dwell time.
- `the_one/interfaces/web/static/js/areas/admin/provider-models.js:347, 376` — `indicator-led` instances without aria-label (visible-text label adjacent → `aria-hidden="true"` per A.9 contract)
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:486-489` — `indicator-led` instances WITH aria-label (sibling visible text exists; see A.9 design question — leave OR drop the redundant aria-label)
- `the_one/interfaces/web/static/css/components.css:864-877` — `indicator-led` primitive definition (where the new contract comment lands)
- `the_one/interfaces/web/static/js/areas/layout/section-nav.js:32-92` — `role="group"` site (path is `areas/layout/`, not `layout/` — original Inputs entry was wrong); container is a `<div role="group">`, NOT under a `<nav>` landmark. See A.10 design decision in Step 8.
- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js:32-35` — count CREATE site (initial `aria-label`); `:55-58` — count UPDATE site inside `appendToTrace` (where `count.textContent = String(...)` runs and `aria-label` needs the matching refresh).
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js:67-72` — tool toggle (`title=` at L67; input + visually-hidden track at L68-71)
- `README.md` — top-level project README
- `tests/test_design_tokens_a11y.py:183-192` — existing contrast test. Lines 187-190 are a COMMENT BLOCK deferring `--fg-muted`-on-chrome ("Muted-text-on-chrome variants deferred — no production consumer today"); L191-192 parametrize entries are `("dark", "fg", "shell_chrome_bg", 4.5)` and `("light", "fg", "shell_chrome_bg", 4.5)` — these test PRIMARY `--fg`, NOT `--fg-muted`. Under scope-the-usage, NO new test parametrization becomes green; the deferral STAYS valid (no production consumer of `--fg-muted` on chrome). The AC #2 needs to reflect this reality — see AC.
- Pre-enumerated chrome-text consumer sites (where to apply scope-the-usage A.3 fix):
  - `the_one/interfaces/web/static/css/base.css:144` — `.stub-sidebar .subtitle { color: var(--fg-muted); }` paints on `#app-sidebar` (chrome) — **must scope to `var(--fg-tertiary)`**
  - `the_one/interfaces/web/static/css/areas/chat.css:15` — `.area-chat .session-group-label { color: var(--fg-faint); }` paints on `#app-sidebar` (chrome, post-Leg-1 restructure) — **decide per A.3 scope: also switch to `var(--fg-tertiary)` OR document as accepted "borderline" case per the existing test's deferral stance**
  - Other `var(--fg-muted)` consumers (~25 sites across `base.css`, `chat.css`, `admin.css`, `studio.css`, `components.css`) paint inside `.area-*` content panels (NOT chrome) and are out of scope for A.3
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
- [ ] A.3 verification: under scope-the-usage, the EXISTING deferral comment at `tests/test_design_tokens_a11y.py:187-190` is updated to reference the scope-the-usage decision and confirm "no production consumer" by enumerating which sites were rescoped (Pre-enumerated chrome-text consumer sites above) — OR a new grep-based test asserts that no `var(--fg-muted)` consumer paints on `--shell-chrome-bg` (chrome). Pick one — recommended: the deferral-comment update + a `grep -rn 'var(--fg-muted)' the_one/interfaces/web/static/css/` shows no chrome-text result (sidebar/topbar selectors don't match `--fg-muted`).
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
- `cd ~/projects/the-one && pytest tests/test_design_tokens_a11y.py -v` → relevant tests PASS
- Manual A.5: trigger a toast (e.g., agent save success); verify it persists ≥5s OR has pause-on-hover + close button
- Inspect DOM for MCP server tile: `alt=""` when icon present; `alt={meaningful}` only if non-decorative
- Manual A.7: set OS `prefers-reduced-motion: reduce` → trigger thinking-indicator → confirm no animation update OR very slow update
- Manual A.8: inspect telemetry overlay DOM; verify row-level labels; verify visual opacity ≥0.7
- `cd ~/projects/the-one && grep -A5 "indicator-led" the_one/interfaces/web/static/css/components.css` — contract comment present
- `cd ~/projects/the-one && grep "role=\"group\"\|role=\"tablist\"" the_one/interfaces/web/static/js/layout/section-nav.js` — appropriate role
- Manual A.11: inspect trace-shell DOM; `summary aria-label` includes count
- Manual A.12: inspect tools-grid; toggle has visible state context
- `cd ~/projects/the-one && grep -i "accessibility\|wcag" README.md` — section present
- `cd ~/projects/the-one && pytest --tb=no -q` → exit 0
- `cd ~/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` → both exit 0

## Implementation Guidance

This leg has 8 firm sub-tasks + 3 opportunistic ones (A.9, A.10, A.13). Sequence by risk: contrast fix first (smallest blast-radius approach), form-field error wiring next (highest a11y significance — second pass running), then mechanical sweep, then opportunistic items if time permits.

1. **A.3 light-theme contrast — scope-the-usage at PRE-ENUMERATED sites**
   - **Pre-enumerated chrome-text consumer sites (from Inputs)**:
     - **`base.css:144`** — `.stub-sidebar .subtitle { color: var(--fg-muted); }` paints on `#app-sidebar` (chrome). **Switch to `var(--fg-tertiary)`.**
     - **`chat.css:15`** — `.area-chat .session-group-label { color: var(--fg-faint); }` paints on `#app-sidebar` (chrome, post-Leg-1 restructure). **Decision**: switch to `var(--fg-tertiary)` too, OR document as accepted "borderline" per existing `test_design_tokens_a11y.py:187-190` deferral. **Recommended**: switch to `var(--fg-tertiary)` — consistency with `base.css:144` fix; `--fg-faint`-on-chrome was the F3.5-debrief original concern.
     - **NO OTHER sites** — re-verify via `grep -rn 'var(--fg-muted)\|var(--fg-faint)' the_one/interfaces/web/static/css/` and check each result is INSIDE a `.area-*` content panel (not chrome). If a new chrome-text consumer surfaces, add to this enumeration before editing.
   - Make the two CSS edits.
   - **Test parametrization update**: `tests/test_design_tokens_a11y.py:187-190` deferral comment currently reads "Muted-text-on-chrome variants deferred — no production consumer today." Update to: "Muted-text-on-chrome variants deferred under scope-the-usage rule (F2 Leg 2, 2026-05-16): chrome surfaces use `--fg-tertiary` directly (verified at `base.css:144`, `chat.css:15`). Re-introducing a chrome-text consumer of `--fg-muted` or `--fg-faint` requires updating BOTH this comment AND the consumer site."
   - **Grep-enforce post-edit**: `grep -rn 'var(--fg-muted)\|var(--fg-faint)' the_one/interfaces/web/static/css/ | grep -E 'topbar|sidebar|chrome'` should return empty (or only `tokens.css` definitional lines).
   - Re-run `pytest tests/test_design_tokens_a11y.py -v` — verify the existing parametrized tests still PASS (no regression on `--fg`-on-chrome).
   - Visually inspect the app (light theme) — sidebar text should now read clearly.
   - **Fallback to Attempt A** (global token darkening) only if the enumeration was incomplete (e.g., a hidden consumer site discovered post-edit). Pivot rule: if 3+ unanticipated chrome-text consumers surface, switch to Attempt A and document the cascade.
   - Regenerate local pixel baselines (gitignored per project convention; verified `tests/browser/__snapshots__/` covered by `.gitignore:17-19`)
   - Sub-commit: `a11y(tokens): scope --fg-tertiary at chrome-text sites for light-theme AA`

2. **A.2 form-field error wiring (HIGH significance — second pass running)**
   - Locate `renderFieldErrors` function in `admin/tools-form-helpers.js` (function spans L493-536; per-row mutation site at L513-521 where `row.classList.add('field-error-highlight')` + span append happens).
   - **Query the input inside each error row**: `row.querySelector('input, select, .chip-list-editor')`. Note: chip-list-editor is a `<div>` (not a native input); the `aria-describedby` target for it is the wrapping div (matches the existing info-icon pattern at L130-134 which sets `dataAttrs += ' aria-describedby="' + descId + '"'` on the wrapping div). For native `<input>`/`<select>`, the target is the element itself.
   - Generate an id per error span: `errorId = '<field-key>-error-<row-id>'` or similar; ensure unique-per-row.
   - Set `aria-invalid="true"` on the queried input/select/chip-list-editor target.
   - Set `aria-describedby={existingValue + " " + errorId}` (ADDITIVE — preserve the existing info-icon `aria-describedby="<field-key>-desc"`). Concrete sequence:
     ```js
     const existing = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
     existing.push(errorId);
     input.setAttribute('aria-describedby', Array.from(new Set(existing)).join(' '));
     ```
   - Set `role="alert"` on the FIRST error span per save cycle. Implementation: pass an `isFirst` flag or check `container.querySelectorAll('.field-error[role="alert"]').length === 0` before adding the attribute. If save-side errors group into a banner (`.editor-error`), prefer `role="alert"` on the banner — single alert per save instead of per-row.
   - Verify the existing `.field-error` CSS still renders correctly; adjust if id-based selector is needed.
   - **Clear logic**: when the field is fixed (input becomes valid mid-edit), `renderFieldErrors` should ALSO remove `aria-invalid` and de-additively remove the error id from `aria-describedby` (reverse the additive sequence). Check existing field-clear behavior at the function's clear paths.
   - Sub-commit: `a11y(forms): aria-invalid + aria-describedby + role=alert on field errors`

3. **A.6 MCP icon alt-text (LOW risk, mechanical)**
   - Edit `studio/mcp-server-editor.js:337-340` — the `<img>` tag has a ternary `icons[0].mimeType ? alt=icons[0].mimeType : alt=""`. **Drop the ternary; always emit `alt=""`** (icon is purely decorative; title text is rendered alongside at L343-344).
   - Sub-commit: `a11y(mcp): drop MIME alt-text on decorative icons`

4. **A.7 thinking-indicator reduced-motion gate**
   - Edit `chat/thinking-indicator.js:18-21`
   - Wrap the `setInterval` call in a `window.matchMedia('(prefers-reduced-motion: reduce)').matches` check
   - If reduced motion: render a single static "thinking…" string and skip the interval
   - Sub-commit: `a11y(chat): thinking-indicator honors prefers-reduced-motion`

5. **A.5 toast duration**
   - The toast already carries `role="alert"` (error path at L233) or `role="status"` (success path at L235), so the WCAG concern is partially mitigated for screen-reader users (alert is announced immediately regardless of duration). The duration bump is primarily for visual-reading dwell time.
   - Edit `app.js:244` — change the setTimeout literal `2000` → `5000` (extend dismiss to 5s; covers WCAG 2.2.1 minimum).
   - Optional improvement (out of leg scope unless time permits): add a close-button affordance + pause-on-hover/focus. Bracket the leg's success on the simple duration bump.
   - Sub-commit: `a11y(toast): extend auto-dismiss to 5s (WCAG 2.2.1/2.2.3)`

6. **A.8 telemetry overlay labeling + opacity**
   - Edit `chat/telemetry-overlay.js:20-21, 44-47` (markup) AND `chat.css:80, 88` (visual — corrected from prior leg's :67, 75 which were wrong).
   - Pick ONE approach: (a) add `aria-label` to each row (e.g., `"Input tokens"`) and keep `role="status"` → polite-live will re-announce per-row; OR (b) mark each row's inner spans `aria-hidden="true"` and rely on the container `aria-label` ("Token usage") — terser, less churn. **Recommended**: (b), to avoid per-token live-region churn.
   - Bump default visual opacity at `chat.css:80` from `0.4` → `0.7` (or switch the color from `var(--fg-muted)` to `var(--fg-tertiary)` directly).
   - Sub-commit: `a11y(telemetry): row labels + opacity bump`

7. **A.9 `indicator-led` labeling discipline** — OPPORTUNISTIC (drop at first sign of leg slippage)
   - Add a comment block at the `indicator-led` primitive definition in `components.css` (around L864-877, locate by class name) describing the contract:
     ```
     /* indicator-led contract:
      *   - When adjacent visible text fully conveys state → LED is decorative; carry aria-hidden="true"
      *   - When the LED carries state distinct from adjacent text (e.g., color encodes severity not in label) → carry aria-label describing the state
      *   - In ambiguous cases (label partial but contextual), prefer aria-label for explicitness
      */
     ```
   - Sweep call sites:
     - `provider-models.js:347, 376` — LEDs adjacent to `.admin-pf-model-name` visible text → **add `aria-hidden="true"`**
     - `mcp-server-editor.js:486-489` — LED with `aria-label="Connected"/"Not connected"` adjacent to "Reset connection" button. The visible button text is NOT the LED state; the LED encodes connection status (distinct from action). **Leave `aria-label` in place** per contract rule 2 ("LED carries state distinct from adjacent text"). Document this decision in the contract comment as an exemplar.
   - Sub-commit: `a11y(led): document contract + sweep call sites`
   - **Slip rule**: if the LED-contract conversation surfaces design ambiguity beyond the two contract rules above (e.g., LEDs in tooltips without adjacent text — none exist today, but future case), drop this item and route to next maintenance pass.

8. **A.10 `section-nav.js` role** — OPPORTUNISTIC (drop at first sign of leg slippage)
   - Edit `the_one/interfaces/web/static/js/areas/layout/section-nav.js:32-92` (container at L32 currently builds a `<div role="group">`; the buttons L34-92 form the group items).
   - **Important**: Cycle-1 design-review caught this — the original spec said "drop `role="group"`; rely on `<nav>` landmark" BUT the container is a `<div>`, NOT under a `<nav>`. Dropping the role with no replacement removes all semantic grouping.
   - Three viable options:
     - (i) Drop `role="group"` AND change `<div>` → `<nav>` (matches the chat session-list pattern Leg 1 introduced). Strongest grouping + landmark.
     - (ii) Drop `role="group"` and keep `<div>` (no landmark; lightest touch, but loses grouping)
     - (iii) Upgrade to `role="tablist"` + `role="tab"` per button + `aria-controls` per tab (most semantically accurate if the sections truly behave as tabs)
   - **Recommended**: (i) — change `<div>` to `<nav>`, drop `role="group"`. Matches the F2-Leg-1 `<nav class="session-list">` precedent. The current `aria-current="page"` semantic is already correct for nav role.
   - Sub-commit: `a11y(section-nav): <div role=group> → <nav>; rely on nav landmark`
   - **Slip rule**: if the `<div>`→`<nav>` change ripples through CSS selectors (`.section-nav div` etc.) in unexpected ways, fall back to option (ii) or skip entirely; route to next maintenance pass.

9. **A.11 trace-shell count in aria-label** — edit TWO sites
   - **Create site** (`trace-shell.js:32-35`): when the trace shell is created and the count span is built, set the summary's INITIAL `aria-label` to `"Tool activity, 0 items"` (or `"Tool activity"` if count is 0; pick the convention).
   - **Update site** (`trace-shell.js:55-58`, inside `appendToTrace`): where `count.textContent = String(body.children.length)` runs, ALSO update the summary's `aria-label`. The summary element is accessible via `traceEl.querySelector('summary')`. Pattern:
     ```js
     const count = body.children.length;
     summary.setAttribute('aria-label', `Tool activity, ${count} ${count === 1 ? 'item' : 'items'}`);
     ```
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
    - `cd ~/projects/the-one && pytest --tb=no -q` — exit 0
    - `cd ~/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both exit 0
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
- `the_one/interfaces/web/static/js/areas/layout/section-nav.js` — A.10 (role + `<div>`→`<nav>`; path corrected from prior leg's `js/layout/`)
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
