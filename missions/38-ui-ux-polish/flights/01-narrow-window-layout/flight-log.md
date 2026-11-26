# Flight Log: Narrow-window layout

**Flight**: [Narrow-window layout](flight.md)

## Summary

Implemented Flight 1 on branch `flight/01-narrow-window-layout` (branched from `origin/main` at `7518aefa`). Below `900px`, `#app-sidebar` closes by default and opens as a left overlay (`App.narrowShell`) mutually exclusive with `#chat-drawer` and `#gleepglorp-drawer`, with focus transfer into opened overlays and focus return on dismiss; short-height (`max-height: 440px`) and sub-520px rail rules keep `624×321` usable across all destinations, and bottom scroll clearance keeps the last control clear of `#gleepglorp-corner-button`.

---

## Leg Progress

- [x] **Branch & docs setup**: Created `flight/01-narrow-window-layout`, set Mission 38 status to `active`, resolved Flight 1 open questions, marked Flight 1 checked in `mission.md`.
- [x] **JS shell & overlay coordination**: Added `narrow-shell.js`, `'panel-left'` in `icons.js`, `rail-sidebar-toggle` in `app.js`, overlay coordination in `agent-drawer.js` and `gleepglorp-drawer/shell.js`, plus testids in `docs/ui-testid-registry.md`.
- [x] **Responsive CSS & bottom clearance**: Updated `base.css`, `components.css`, `chat.css`, `studio.css`, `admin.css`, and `gleepglorp-drawer.css`.
- [x] **Capture, docs, and tests**: Added `640` and `624` sizes in `scripts/ui_capture.py`, updated `test_ui_capture_safety.py`, `overview.md`, `the_one/agents.md`, and added `tests/browser/test_flow_narrow_layout.py`.

## Decisions

- Chose left overlay sidebar below `900px` (`(max-width: 899px)`) with a rail toggle button (`rail-sidebar-toggle`, hidden at `900px+`) so `#main-content` stays mounted and dirty-state leave guards work unchanged.
- Mapped `App.narrowShell` destination labels to router destination ids (`chats`, `agents`, `library`, `settings`) and checked `!e.defaultPrevented` on sidebar `Escape` so inner menus/dialogs consume `Escape` first.
- Kept `.studio-editor` in `gleepglorp-drawer.css` (without `:not(:has([role="tablist"]))`) because tabbed Agent editor panels use `.tabpanel.ui-tabs--flush` (`overflow: visible`), so `.studio-editor` is their flex scroll container and needs the `88px` bottom spacer (`::after` + `scroll-padding-bottom`).
- Kept `studio.css` narrow media rules unlayered at the bottom of the file so they cleanly beat existing unlayered rules (lines 976–1314) without disturbing desktop specificity.

## Deviations

- Browser and parallel unit checks were executed via `.venv/bin/python -m pytest` (with explicit `start_new_session=True` + `os.killpg` process-group teardown for browser suites) rather than `scripts/run-tests.sh` because macOS ships Bash 3.2 (`declare -A` fails on line 67) and omits `setsid`. No changes were made to `scripts/run-tests.sh` or `Makefile`.

## Anomalies

- Pre-existing macOS host-only failures observed outside Flight 1 changes: `test_run_tests_lanes.py` (Bash 3.2 `run-tests.sh`), 3 unit items (`test_db_api.py::test_get_item` `/private/tmp`, `test_desktop_shell.py::test_run_calls_create_window_start_and_graceful_shutdown` fake `webview` vs `macos_dock.py`, `test_boot_policy.py::test_close_to_tray_marks_hidden_then_every_show_path_marks_visible`), 8 WebKit Tab-focus contract items (`webkit 27.2` on macOS skips buttons/links on plain `Tab`), and 22 `test_flow_jump_to.py` items expecting Linux `Control+K` / `"Jump to (Ctrl K)"` on macOS (`Meta+K` / `"Jump to (⌘ K)"`).

## Session Notes

### Flight Director Notes

- Post-verification checks (`make lint && make format-check`, targeted UI/guard suite, `test_flow_narrow_layout.py` Chromium+WebKit 8/8, Chromium shell/drawer/area suites, and `ui_capture.py --widths 624,640` 36/36) all passed cleanly.
- Local `agent-browser` interactive visual walkthrough (11 captures at `624×321`, `480×321`, and `1280×800`, dark + light) caught short-height clipping inside `#gleepglorp-drawer` when the unconfigured `Choose a model` setup block coexisted with `.gg-drawer-slot` at `321px` height. Fixed under `@media (max-height: 440px)` in `the_one/interfaces/web/static/css/gleepglorp-drawer.css`, then re-verified with `make lint && make format-check`, 248 UI/guard/guide/nav/capture tests, `THE_ONE_REQUIRE_WEBKIT=1` `test_flow_narrow_layout.py` + `test_flow_gleepglorp_drawer_shell.py` (33 passed), and re-inspection of the updated `agent-browser` screenshots (`0` errors).
