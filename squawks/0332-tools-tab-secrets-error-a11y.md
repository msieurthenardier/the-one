# Squawk 0332: Tools-tab Secrets section error is unreliable for assistive tech and goes stale

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: —

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
*(written at completion)* Planned:
- keep the status element in the DOM as a permanent live region, and only change its text;
- wrap the rows in a group labelled by the section heading;
- add the error's id to each switch's `aria-describedby` while it shows;
- clear the error on any toggle.

## Verification
A browser test in `tests/browser/test_flow_agent_secrets.py` (lane `agent-tabs`): a forced 422 shows the error in a live region present before the save; the switches reference it; the next toggle clears it.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
