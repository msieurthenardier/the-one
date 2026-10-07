# Squawk 0109: `App.ui.menu` tabindex reset depends on keydown listener order

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: 2026-10-07

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

Fixed menu-locally; `rovingFocus` is untouched (no option needed). `rovingFocus` writes
`tabindex="0"` on the target item strictly BEFORE calling `.focus()`, so the focus move
fires `focusin` on the popup after the write. `ui/menu.js` now resets every menuitem to
`-1` from a `focusin` listener on the popup instead of a second `keydown` listener. That
holds regardless of listener registration order, and also covers any other path that
focuses an item (Home/End, arrows, `open('first'|'last')`). The `rovingFocus` option the
report suggested was rejected as unnecessary.

## Verification

- `tests/browser/test_ui_menu_contract.py::test_arrow_wrap_home_end_skip_disabled_and_keep_tabindex`
  already asserted tabindex at the end of the walk (so the report's "without any test
  noticing" was overstated); it now asserts all items are `-1` after open and after every
  key press (arrows, Home, End).
- Falsified: removing the reset listener fails that test (chromium, line 217); restored.
- Menu contract file, Chromium + WebKit (`THE_ONE_REQUIRE_WEBKIT=1`): 66 passed.
- `test_flow_studio_library_list.py` (production menu): 50 passed. Static guards: 261
  passed. `make test-unit`: 5458 passed, 10 skipped. ruff check and format clean.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
