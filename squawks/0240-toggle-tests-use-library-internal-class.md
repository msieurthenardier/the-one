# Squawk 0240: Browser tests click switches through a library-internal class

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
Since Mission 31 Flight 3 leg 07a, several browser tests toggle `App.ui.toggle` switches by clicking `label.ui-toggle-label:has(...)`, a class internal to the library. That couples them to the factory's markup. The tests should use role locators instead: for example, `get_by_role('switch', name='Enabled')` with `.set_checked()` or `.check()`, because the native input is visually hidden. Found in the Mission 31 Flight 3 flight review. Pick it up with Flight 4 or 5, which touch the same tests.

## Evidence
- `label.ui-toggle-label:has([data-field="enabled"])`:
  - `tests/browser/test_store_library.py:431`
  - `tests/browser/test_flow_studio_library_list.py:571` and `:1390`
  - `tests/browser/test_router_guard.py:446`
  - `tests/browser/test_studio_connector_editor.py:193` and `:401`
- Tool tile toggles through `.ui-group-tile … .ui-toggle-label`:
  - `tests/browser/test_flow_studio_time_tool.py:122`
  - `tests/browser/test_flow_studio_tools_tab_patch.py:96`
- `tests/browser/test_deep_violet_computed_styles.py:53-54` builds the markup as a style fixture. That use is legitimate, and it stays.

## Corrective Action

## Verification

## Sign-Off
