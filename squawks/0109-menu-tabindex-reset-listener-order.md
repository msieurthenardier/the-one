# Squawk 0109: `App.ui.menu` tabindex reset depends on keydown listener order

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: —

## Report

`App.ui.util.rovingFocus` sets `tabindex="0"` on the item it focuses. Menu items must
stay `tabindex="-1"` (APG menu; Flight 1 leg `menu-control` AC4). `ui/menu.js` handles
this with a second `keydown` listener that resets every item to `-1` after
`rovingFocus` runs. That correctness depends on listener registration order. If a later
change reorders the listeners or makes the reset run first, menu items become tab stops
without any test noticing. Found by the Mission 25 Flight 1 debrief (Architect).

## Evidence

- `the_one/interfaces/web/static/js/ui/menu.js:150` resets each item to `-1` in a
  second handler.
- `the_one/interfaces/web/static/js/ui/core.js` `rovingFocus` has no option to leave
  `tabindex` untouched.

## Corrective Action

*(written at completion)*

Add a `rovingFocus` option, for example `{manageTabindex: false}`, that moves focus
without writing `tabindex`. Use it from the menu, and delete the second listener.

## Verification

*(written at completion)*

Run `tests/browser/test_ui_menu_contract.py`, including the items-stay-`-1` assertion,
in both engines.

## Sign-Off

*(written at completion)*
