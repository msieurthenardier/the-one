# Squawk 0332: Tools-tab Secrets section error is unreliable for assistive tech and goes stale

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: 2026-11-05

## Report
In an agent's Tools tab, the Secrets section's save-error status has three problems, carried from the sortie 10 leg 3 part B reviews (non-blocking; not raised in the HAT):
- A 422 un-hides the status and fills it in the same step, so a screen reader may not announce it. Leg 3 part A fixed the same pattern in `App.ui.chipList` with a permanent live region.
- The error is not linked to the switches it concerns, and the switch list is not a labelled group.
- A stale section error survives a later toggle, and stays until the next save.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/secrets-section.js:82-84` — the status is created hidden (`errorEl.el.hidden = true`).
- `:155-157` — `errorEl.set('danger', text); errorEl.el.hidden = false;` runs in one step.
- `:125` — each switch's `aria-describedby` points only to its meta text.
- `sorties/10-secrets/flight-log.md` "Carried to the HAT (non-blocking polish)".

## Corrective Action
In `secrets-section.js` (no `js/ui/` change):
- the `App.ui.status` error node is never `hidden`; it is a permanent `role=status` live region and `showError` only changes its text;
- the switch list is `role="group"` labelled by the section's h2 (`agent-editor.js` gives the h2 an id and passes `headingId`; `aria-label="Secrets"` is the fallback);
- while the error shows, each switch's `aria-describedby` is `"{meta id} {error id}"`; it returns to the meta id alone when cleared;
- any toggle clears the error and the references (`clearError`).

## Verification
New test `test_section_error_is_a_permanent_live_region_linked_to_the_switches` in `tests/browser/test_flow_agent_secrets.py` (lane `agent-tabs`): live region present, not hidden and empty before the save; group labelled "Secrets"; a forced 422 fills the same node and both switches reference its id; the next toggle clears text and references. Falsified by removing `clearError()` from the toggle callback (test failed, restored). Results: file 7 passed; `--lane agent-tabs` 202 passed; `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_ownership`, `test_store_static` 381 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-11-05 squawk turnaround, scoped to the diff: `[HANDOFF:confirmed]`, no blocking issues, no `js/ui/` factory changed. Accessibility Reviewer (Sonnet): `[HANDOFF:confirmed]`. A polite `role=status` is right; the group label and the `aria-describedby` set and restore are correct. Its one low-severity note is outside this diff: a 422 that first switches to the Tools tab shows the region in the same frame as its text (a new squawk candidate). The Flight Director's `--lane agent-tabs` on the final tree: 202 passed, 390 s.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-05` commit on `squawk/turnaround-2026-11-05`.
