# Leg: live-region-and-labels

**Status**: completed
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
- [x] `aria-live="polite"` on the **status text span** (not the wrap div with the LED) — verified live (wrap has no aria-live)
- [x] The error wrap gets `role="alert"` so `last_error` + the portal link are announced on reveal — verified live
- [x] The live nodes are present from initial render and mutated in place (not restructured into a per-poll rebuild)
- [x] The presence-type `<select>` (`id="cf-discord-presence-type"`) and presence-name `<input>` (`id="cf-discord-presence-name"`) each have an associated `<label for>` with a real name; no id collision
- [x] (Opportunistic) the Validate/doctor-probe message row gets `aria-live="polite"`
- [x] Browser tests confirm the `aria-live`/`role` attributes and the presence-control accessible names — 12 browser tests pass

## Verification Steps
- Manual SR pass: trigger a connect→error transition and confirm the status text + error are announced (test in Firefox + NVDA — `role="alert"` first-reveal reliability)
- DOM check / browser test: the status text span carries `aria-live="polite"`; the error wrap carries `role="alert"`; the presence select + input have accessible names
- `pytest -m browser tests/browser/test_flow_studio_connector_discord_form.py -q` green (extend with label assertions)

## Implementation Guidance

1. **A1 — add live regions** (nodes already persist across polls — just add the attributes)
   - On `<span class="connector-live-status-text">` (~2064): add `aria-live="polite"`. Do NOT put it on the surrounding `connector-live-status-wrap` div (~2061) — that contains the LED (`_updateLed` rewrites its `aria-label` each poll, which would fire spurious announcements).
   - On `connector-live-status-error-wrap` (~2072): add `role="alert"` (more reliable than `aria-live="assertive"` for a hidden→revealed element). The portal link is inside the wrap, so it announces with the error.
   - The LED's `aria-label` change (~4491) is not announced (non-live element) — rely on the text region, as designed.

2. **A4 — label the presence controls**
   - `connector-form-discord.js`: the orphan `<label>Bot status</label>` (~183) wraps nothing. Give the presence-type `<select>` (~192) `id="cf-discord-presence-type"` and the presence-name `<input>` (~202) `id="cf-discord-presence-name"`, each with an associated `<label for>` (mirror the Bot Token field at ~289-300). The presence-name input needs a real name (e.g. label "Activity name" or `aria-label`), not just its placeholder. "Bot status" can remain as the group context.

3. **Tests** — extend `tests/browser/test_flow_studio_connector_discord_form.py` (exists) with accessible-name assertions (e.g. inside `test_presence_name_and_type_save`, ~183, which already navigates there). A live-region DOM assertion (`status span has aria-live="polite"`) can be added to the editor flow test (`test_flow_studio_connector_editor.py`).

## Edge Cases
- **Polite vs assertive** — status text is `polite` (don't interrupt); the error wrap is `role="alert"` (interrupts). Don't make the whole status region assertive or every 3s poll nags.
- **Region churn** — the live nodes must persist across polls (they do today); recreating them defeats announcement. Don't move them into a per-poll rebuild.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` - `aria-live` on status text span, `role="alert"` on error wrap, (opportunistic) probe row
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` - presence select/input ids + labels
- `tests/browser/test_flow_studio_connector_discord_form.py` (+ editor flow test) - assertions

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (not final)
- [x] Commit all changes together (code + artifacts)
