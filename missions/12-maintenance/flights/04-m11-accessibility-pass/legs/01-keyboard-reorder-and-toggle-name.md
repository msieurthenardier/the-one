# Leg: keyboard-reorder-and-toggle-name

**Status**: ready
**Flight**: [Mission-11 UI Accessibility Pass](../flight.md)

## Objective
Make routing-rule reorder operable by keyboard (A2) and give the connector attach/enable toggle an accessible name (A3) — the two WCAG Level-A operability blockers in the connector-editor UI.

## Context
- Maintenance report 2026-06-04, findings **A2** (WCAG 2.1.1, top a11y priority) and **A3** (WCAG 4.1.2).
- **A2**: the drag handle is `<span role="button" draggable="true">` with no `tabindex` and only drag handlers, no keydown (`connector-editor.js:2511-2516`, wiring at `2854-2902`). The chevron move-buttons were removed in M11 in favor of HTML5 drag (comment at `:2850-2851`), leaving no keyboard path. A keyboard/AT/switch-access operator cannot reorder rules at all.
- **A3**: the attach checkbox is in an empty `<label class="mcp-source-tile-toggle">` + a decorative switch span; the connector name is an unassociated sibling (`connectors-tab.js:415-429`). SR announces an unnamed checkbox. The nearby per-agent "Always listen" toggle (`:815-848`) is correctly labeled — use it as the template.

## Inputs
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (routing-rule render + drag wiring).
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:415-429` (attach toggle) and `:815-848` (correct template).

## Outputs
- Keyboard-operable routing-rule reorder.
- Accessible name on the attach toggle.

## Acceptance Criteria
- [ ] Routing rules can be reordered using only the keyboard (move-up/down buttons, or a focusable handle with arrow-key reordering — per the flight's confirmed mechanism)
- [ ] The reorder controls are in the tab order and have correct names/roles (no `role="button"` without keyboard operability)
- [ ] Reorder changes are announced or visibly reflected for AT users (e.g. live-region feedback if using the arrow-key approach)
- [ ] The connector attach/enable toggle has a non-empty accessible name (e.g. `aria-label="Attach {account.name}"` or label-association to the name span)
- [ ] A browser test covers keyboard reorder; an assertion confirms the toggle's accessible name

## Verification Steps
- Manual: Tab to the routing-rule reorder control, reorder with keyboard only, confirm order changes
- Manual/automated: SR (or accessible-name computation) reports the toggle's name
- `pytest -m browser tests/browser/` (the connector-editor flow tests) green; add/extend a test asserting keyboard reorder and the toggle name

## Implementation Guidance

1. **A2 — restore a keyboard path** (mechanism per flight decision)
   - *Move-buttons approach*: re-add up/down `<button>`s (with `aria-label`s like "Move rule up") next to each routing rule, wired to the same reorder logic the drag drop calls. Keep the drag handle for mouse users.
   - *Focusable-handle approach*: give the handle `tabindex="0"`, add a `keydown` handler (ArrowUp/ArrowDown to move, with `preventDefault`), and announce the new position via a visually-hidden live region.
   - Either way: the `role="button"` must now be truly operable, or switch the handle to a real `<button>`.

2. **A3 — name the toggle**
   - Mirror the `:815-848` "Always listen" pattern: add `aria-label` to the checkbox (e.g. `'Attach ' + account.name`) or wrap/associate the name span via the label.

3. **Tests** — extend the existing connector-editor browser flow (`tests/browser/test_flow_studio_connector_account_editor.py`) to assert keyboard reorder and the toggle's accessible name.

## Edge Cases
- **Reorder at list boundaries** — first rule can't move up, last can't move down; disable or no-op the control and reflect that state to AT.
- **Drag and keyboard must not desync** — both paths call the same underlying reorder so state stays consistent.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` - keyboard reorder
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` - toggle accessible name
- `the_one/interfaces/web/static/css/studio.css` - any focus styling for new buttons/handle
- `tests/browser/test_flow_studio_connector_account_editor.py` - keyboard + name assertions

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
