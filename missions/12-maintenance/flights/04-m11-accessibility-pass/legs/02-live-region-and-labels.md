# Leg: live-region-and-labels

**Status**: ready
**Flight**: [Mission-11 UI Accessibility Pass](../flight.md)

## Objective
Announce connector live-status changes to screen readers (A1) and label the Discord "Bot status" presence controls (A4).

## Context
- Maintenance report 2026-06-04, findings **A1** (WCAG 4.1.3, AA — downgraded to Advisory but fixed in this pass) and **A4** (WCAG 1.3.1 / 4.1.2, A).
- **A1**: the live-status text span (`connector-live-status-text`) and error wrap (`connector-live-status-error-wrap`/`-error`) are updated by a 3s poll (`_applyStatus` at `connector-editor.js:2057-2077` render, `4508-4526` apply) but have no `aria-live`. Connected→error transitions, the `last_error` message, and the "Fix in Developer Portal" link are silent for SR users. The Validate/doctor-probe row (`:2094`) has the same gap (user-triggered, lower priority).
- **A4**: `<label>Bot status</label>` (`connector-form-discord.js:183`) has no `for` and wraps nothing; the presence-type `<select>` (`:192`) and presence-name `<input>` (`:202`, placeholder-only) are unlabeled. The Bot Token field (`:289-300`, `for="cf-discord-bot-token"`) is the correct template.

## Inputs
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (live-status render/apply).
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:183-202` (presence controls) and `:289-300` (template).

## Outputs
- Live-status region announces changes; presence controls are labeled.

## Acceptance Criteria
- [ ] The live-status text region has `aria-live="polite"` (or `role="status"`) so state changes are announced
- [ ] The error wrap has `aria-live="assertive"` (or `role="alert"`) so `last_error` + the portal link are announced when they appear
- [ ] The presence-type `<select>` and presence-name `<input>` each have an associated label (`<label for>` + `id`, or `aria-label`); the input has a real name beyond its placeholder
- [ ] (Opportunistic) the Validate/doctor-probe message row gets the same live-region treatment
- [ ] An assertion (browser test or DOM-shape check) confirms the `aria-live`/label presence

## Verification Steps
- Manual SR pass: trigger a connect→error transition and confirm the status + error are announced
- DOM check / browser test: the status region carries `aria-live`; the presence select + input have accessible names
- `pytest -m browser tests/browser/test_flow_studio_connector_discord_form.py -q` green (extend with label assertions)

## Implementation Guidance

1. **A1 — add live regions**
   - On the status text span: `aria-live="polite"` (or render it inside a `role="status"` container). On the error wrap: `aria-live="assertive"` or `role="alert"`. Since `_applyStatus` toggles `hidden` and rewrites `textContent`, the live region must be present in the DOM before the update (don't create it on each poll) so the change is detected.
   - Note: an `aria-label` change on a non-live element (the LED, `:4491`) is not announced — rely on the text region, not the LED label.

2. **A4 — label the presence controls**
   - Give the `<select>` and `<input>` `id`s and point `<label for>` at them (mirror the Bot Token field). The presence-name input needs its own visible or `aria-label` name beyond the placeholder.

3. **Tests** — extend the Discord-form browser test with accessible-name assertions; if a live-region assertion fits the harness, add it to the editor flow test.

## Edge Cases
- **Polite vs assertive** — status text is `polite` (don't interrupt); errors are `assertive`/`alert` (interrupt). Don't make the whole region assertive or every 3s poll nags.
- **Region churn** — ensure the live node persists across polls; recreating it defeats announcement.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` - live regions on status + error (+ probe row)
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` - presence control labels
- `tests/browser/test_flow_studio_connector_discord_form.py` (+ editor flow test) - assertions

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: (not final)
- [ ] Commit all changes together (code + artifacts)
