# Leg: keyboard-reorder-and-toggle-name

**Status**: completed
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
- [x] The drag handle has `tabindex="0"` and a `keydown` handler: ArrowUp/ArrowDown move the row in DOM order (with `preventDefault`); the handle is in the tab order
- [x] **Focus is retained** on the moved handle after a reorder (`handle.focus()` after the swap) — verified live in the behavior test
- [x] The handle no longer carries a bare `role="button"`; the `aria-label` ("Reorder rule — use Arrow keys to move") describes the arrow-key operation
- [x] A persistent visually-hidden `aria-live="polite"` region announces the new position ("Rule moved to position N of M") and boundary ("Rule is already first/last") — verified live
- [x] Keyboard and drag reorder stay consistent — both mutate the DOM order `collectRoutingFromContainer` reads (no separate model)
- [x] The connector attach/enable toggle has a non-empty accessible name (`aria-label="Attach " + account.name`)
- [x] Browser test covers keyboard reorder (order changed + focus retained) and the toggle accessible name — 22 browser tests pass

## Verification Steps
- Manual: Tab to a routing-rule handle, ArrowDown/Up to reorder with keyboard only, confirm order changes AND focus stays on the handle
- Manual/automated: SR (or accessible-name computation) reports the toggle's name and the position announcement
- `pytest -m browser tests/browser/test_flow_studio_connector_editor.py` green; extend it (model on `test_routing_rules_drag_reorder`, ~line 527) with a keyboard-reorder test and the toggle-name assertion

## Implementation Guidance

1. **A2 — focusable handle + arrow keys** (confirmed mechanism)
   - **There is NO shared reorder function.** The drag path (`_wireRoutingDropTarget`, ~2873-2902) mutates the DOM directly via `parent.insertBefore(...)` then calls `checkDirty()`; `collectRoutingFromContainer` (~3012) reads rule order straight from `section.querySelectorAll('tr.connector-routing-row')`. So the keydown handler must **replicate that pattern inline**: get the live rows array via `querySelectorAll('tr.connector-routing-row')`, find the current index with `Array.prototype.indexOf(rowEl)` (NOT the `data-row` attr, which is presentation-only/stale per the comment at ~2789-2791), `insertBefore` to swap with the neighbor, then `checkDirty()`.
   - Give the handle `tabindex="0"`; add the `keydown` handler in `wireRoutingRulesEvents` (`checkDirty` is in closure scope there, passed as a param ~2782). ArrowUp/ArrowDown with `preventDefault`.
   - **After the swap, call `handle.focus()`** (the `e.currentTarget` handle) — `insertBefore` drops focus otherwise.
   - **Live region:** inject one persistent node into `renderRoutingRulesSection` (~2552): `<span class="visually-hidden" aria-live="polite" data-routing-live-region></span>` (the `.visually-hidden` class is defined in `admin.css:505`). The handler writes the new-position text to it (query it by `[data-routing-live-region]`).
   - **Drop the `role="button"`** on the handle (it implies Enter/Space activation the handle doesn't support); keep an `aria-label` like `"Reorder rule — use Arrow keys to move"`. Keep `draggable="true"` on the `<span>` for mouse users (do NOT switch to a `<button>` — `draggable` on `<button>` is unreliable in Firefox).

2. **A3 — name the toggle**
   - Mirror the `connectors-tab.js:815-848` "Always listen" pattern: add `aria-label = 'Attach ' + account.name` to the checkbox (confirm `account.name` is in scope at ~415-429) or associate the name span via the label.

3. **Tests** — the file is `tests/browser/test_flow_studio_connector_editor.py` (NOT `_account_editor`). Model the keyboard test on `test_routing_rules_drag_reorder` (~527): same seed/tab-activation/save-assert flow, but locate `[data-routing-drag-handle]` in the target row, `.focus()` it, `page.keyboard.press('ArrowDown')`, assert the order changed and the handle still has focus.

## Edge Cases
- **Reorder at list boundaries** — first rule can't move up, last can't move down; **no-op + announce "already first/last" via the live region** (do NOT use `disabled`, which removes focusability from the handle).
- **Drag and keyboard must not desync** — both mutate DOM order directly (the single source `collectRoutingFromContainer` reads), so they stay consistent by construction.
- **Focus loss** — the single most common bug in this pattern; the explicit `handle.focus()` after `insertBefore` is mandatory (see AC).

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` - focusable handle, keydown reorder, persistent live region
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` - toggle accessible name
- `the_one/interfaces/web/static/css/studio.css` - focus styling for the handle (visible focus ring)
- `tests/browser/test_flow_studio_connector_editor.py` - keyboard-reorder + toggle-name assertions

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
