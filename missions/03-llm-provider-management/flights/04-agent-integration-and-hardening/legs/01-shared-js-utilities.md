# Leg: shared-js-utilities

**Status**: completed
**Flight**: [Agent Integration & Hardening](../flight.md)

## Objective

Extract duplicated JavaScript utility functions into the shared `App` namespace in `app.js`, replacing all inline copies in `admin.js` and `studio.js`.

## Context

- Flight 02 and 03 debriefs identified duplicated JS utilities across area files
- `escapeHtml` is already centralized in `App` namespace; `escapeAttr`, `formatBytes`, and flash message functions are duplicated
- `formatBytes` has divergent algorithms between admin.js (iterative) and studio.js (logarithmic) — must pick one canonical version
- The `showFlash` / `showAdminFlash` functions differ in CSS class names and the admin version has accessibility attributes
- Confirm timer patterns are NOT extracted — they vary too much across call sites (different CSS classes, timeouts, async pre-checks, aria attributes) and the abstraction payoff is too low

## Inputs

- `the_one/interfaces/web/static/js/app.js` — App namespace with `escapeHtml` already exported
- `the_one/interfaces/web/static/js/areas/admin.js` — inline `escapeAttr` (line 1165), `formatBytes` (line 719), `showAdminFlash` (line 1143)
- `the_one/interfaces/web/static/js/areas/studio.js` — inline `escapeAttr` (line 806), `formatBytes` (line 694), `showFlash` (line 680)

## Outputs

- `app.js` exports `escapeAttr`, `formatBytes`, `showFlash` alongside `escapeHtml`
- `admin.js` and `studio.js` use `App.*` versions, inline copies removed

## Acceptance Criteria

- [ ] `App.escapeAttr(s)` defined in app.js and used in admin.js and studio.js (inline definitions removed)
- [ ] `App.formatBytes(bytes)` defined in app.js with a single canonical algorithm (admin.js iterative version); inline definitions removed from both files
- [ ] `App.showFlash(container, msg, isError)` defined in app.js; replaces `showAdminFlash` in admin.js and `showFlash` in studio.js. Uses a shared CSS class (`app-flash`) plus optional `error` modifier. Includes accessibility attributes (role="alert" for errors, role="status" for success).
- [ ] CSS updated: `.app-flash` and `.app-flash.error` rules created in `styles.css`. Existing `.admin-flash` and `.studio-flash` rules removed or aliased.
- [ ] No JS console errors when navigating all three areas (Chat, Admin, Studio)
- [ ] Existing functionality preserved — flash messages appear correctly, byte formatting consistent

## Verification Steps

- Search admin.js and studio.js for any remaining inline definitions of `escapeAttr`, `formatBytes`, `showFlash`, or `showAdminFlash` — should find none (function definitions only; usage via App.* is fine)
- Check that `App` return object in app.js includes all four utilities (escapeHtml, escapeAttr, formatBytes, showFlash)
- Manually test: save an agent in Studio (flash message), view model sizes in Admin (formatBytes)

## Implementation Guidance

1. **Add utilities to `app.js`** after `escapeHtml`:
   - `escapeAttr(s)` — same implementation as current (they're identical in both files)
   - `formatBytes(bytes)` — use the admin.js iterative version (more readable, handles edge cases better with the `i >= 2` rounding logic). Preserves behavior for `null`, `undefined`, and `0` inputs (all return `'0 B'`).
   - `showFlash(container, msg, isError)` — generalized version that:
     - Creates a div with class `app-flash` (plus `error` if isError)
     - Sets `role="alert"` for errors, `role="status" aria-live="polite"` for success
     - Appends to `container` element
     - Fades in after 10ms, removes after 2000ms with 300ms fade-out

2. **Update the `App` return object** to export all four utilities

3. **Update `admin.js`**:
   - `escapeAttr`: change to `var escapeAttr = App.escapeAttr;` and remove the function definition (lines 1165-1168)
   - `formatBytes`: remove the function definition (lines 719-726), add `var formatBytes = App.formatBytes;` near the existing `var escapeHtml = App.escapeHtml;` line
   - `showAdminFlash`: replace all calls with `App.showFlash(contentEl, msg, isError)`, remove the function definition (lines 1143-1159)

4. **Update `studio.js`**:
   - `escapeAttr`: change to `var escapeAttr = App.escapeAttr;` and remove the function definition (lines 806-809)
   - `formatBytes`: remove the function definition (lines 694-701), add `var formatBytes = App.formatBytes;` near the existing `var escapeHtml = App.escapeHtml;` line
   - `showFlash`: replace the function definition (lines 680-690) with a thin wrapper: `var showFlash = function(msg) { App.showFlash(editorEl, msg); };` — preserves existing call sites that only pass `msg`

5. **Update CSS** in `the_one/interfaces/web/static/styles.css`:
   - Add `.app-flash` base rule (copy from existing `.admin-flash`)
   - Add `.app-flash.error` rule (copy from `.admin-flash.error`)
   - Remove or alias `.admin-flash` and `.studio-flash` selectors

## Edge Cases

- **Container element must exist**: `showFlash` receives the container element directly, so callers must ensure it exists
- **formatBytes(0)**, `formatBytes(null)`, `formatBytes(undefined)`: Must all return "0 B"

## Files Affected

- `the_one/interfaces/web/static/js/app.js` — Add utility functions and exports
- `the_one/interfaces/web/static/js/areas/admin.js` — Remove inline utilities, use App.*
- `the_one/interfaces/web/static/js/areas/studio.js` — Remove inline utilities, use App.*
- `the_one/interfaces/web/static/styles.css` — Add `.app-flash` styles, clean up old selectors
