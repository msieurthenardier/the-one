# Flight: Narrow-window layout

**Status**: landed
**Mission**: [UI/UX Polish](../../mission.md)
**Branch**: `flight/01-narrow-window-layout`

## Contributing to Criteria

- Make the minimum desktop window client area (`624×321`, from `640×360` outer) usable across all four destinations without clipping, overlap, or horizontal page scroll, while preserving wide desktop (`1280×800`, `1024×768`) behaviour.
- Coordinate `#app-sidebar`, `#chat-drawer`, and `#gleepglorp-drawer` so at most one overlay is open at a time below its overlay breakpoint, moving focus into opened overlays and returning focus on close.
- Add `640` (`640×360`) and `624` (`624×321`) capture sizes to `scripts/ui_capture.py` (keeping `--widths` default `1280,1024`).
- Cover `(624, 321)` and `(1280, 800)` + `<624px` overflow safety in browser tests (Chromium + WebKit).

## Pre-Flight

### Objective

Turn every destination (Chats, Agents, Library, Settings) and every overlay (`#app-sidebar`, `#chat-drawer`, `#gleepglorp-drawer`) into a working narrow-window layout down to `624×321` (and horizontal-scroll-free below `624px` in a normal browser) with zero regressions at `900px+` and `1280px+`.

### Design Decisions

**Left overlay sidebar below `900px` (`(max-width: 899px)`).** `#app-sidebar` closes by default below `900px` and opens as a left overlay next to `#app-rail` via a rail footer toggle (`rail-sidebar-toggle`, hidden at `900px+`), leaving `552px` (`624 - 72`) for `#main-content`. Keeping `#main-content` mounted keeps dirty-state leave guards and router transitions unchanged.

**Single-overlay coordinator (`App.narrowShell`).** `#app-sidebar` (`< 900px`), `#chat-drawer` (`< 1280px`), and `#gleepglorp-drawer` (`< 1280px`) register with `App.narrowShell`. Opening one overlay closes any other active overlay before opening, moves focus into the newly opened overlay, and returns focus to the trigger control when dismissed via `Escape`, Close, or toggle.

**Compact short-height rules (`(max-height: 440px)`).** Tightens `.ui-rail`, `.page-header`, `.editor-header`, `.ui-tabs`, `.chat-header`, `.ui-message`, and `.ui-composer` so at `624×321` at least three lines of transcript remain visible above the composer.

**Bottom clearance for `#gleepglorp-corner-button`.** Extends scroll bottom clearance across `.studio-editor`, `.studio-section-content`, and `.admin-content` (`88px` flex `::after` spacer + `scroll-padding-bottom`), plus `padding-bottom: 88px` on non-flush `.tabpanel`, so the last interactive control in any scroll container never rests under the corner button.

### Prerequisites

- [x] Mission 38 activated on branch `flight/01-narrow-window-layout`.
- [x] Existing guard tests (`test_ui_guards.py`, `test_ui_ownership.py`, `test_ui_control_inventory.py`, `test_css_layers.py`) audited.

## In-Flight

### Technical Approach

1. Add `panel-left` icon in `icons.js`, `narrow-shell.js` overlay coordinator (`App.narrowShell`), rail toggle button in `app.js`, and overlay coordination hooks in `agent-drawer.js` and `gleepglorp-drawer/shell.js`.
2. Add responsive rules for `(max-width: 899px)`, `(max-width: 520px)`, and `(max-height: 440px)` across `base.css`, `components.css`, `chat.css`, `studio.css`, `admin.css`, and `gleepglorp-drawer.css`.
3. Add `640` and `624` sizes in `scripts/ui_capture.py` + unit tests in `tests/test_ui_capture_safety.py`; update `the_one/gleepglorp/guide/overview.md`, `docs/ui-testid-registry.md`, and `the_one/agents.md`.
4. Add `tests/browser/test_flow_narrow_layout.py` verifying layout bounds, 3+ chat lines at `624×321`, `elementFromPoint` on scrolled last controls, single-overlay exclusivity, focus movement/return, modals, `<624px` safety, and WebKit coverage.

### Checkpoints

- [x] Static UI guard, guide, capture-safety, and nav-helper unit tests pass.
- [x] Narrow-layout browser suite (`test_flow_narrow_layout.py`) passes across Chromium and WebKit, and affected area/drawer Chromium flow suites pass.
- [x] `ui_capture.py --widths 624,640` completes with zero failures across representative surfaces in all 4 destinations.

## Post-Flight

### Completion Checklist

- [x] Code implemented and linted (`make lint && make format-check`).
- [x] Unit and browser verification green (within documented macOS host caveats below) after final JS/CSS/test edits.
- [x] Mission, Flight, Flight Log, Guide, Testid Registry, and `the_one/agents.md` updated.

### Verification

- `make lint && make format-check` — passed (1067 files formatted).
- Targeted unit/guard tests (`.venv/bin/python -m pytest -x --timeout=60 tests/test_nav_helper.py tests/test_nav_guard_static.py tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_library_source.py tests/test_ui_mechanism_testids.py tests/test_css_layers.py tests/test_gleepglorp_guide.py tests/test_ui_capture_safety.py tests/test_shell_write_hook.py`): **501 passed**.
- Parallel unit run (excluding `test_run_tests_lanes`, `-n 4`): **1544 passed** before stopping on 3 pre-existing macOS host issues (`test_db_api.py::test_get_item`, `test_desktop_shell.py::test_run_calls_create_window_start_and_graceful_shutdown`, `test_boot_policy.py::test_close_to_tray_marks_hidden_then_every_show_path_marks_visible`). (`scripts/run-tests.sh` and `tests/test_run_tests_lanes.py` require Bash 4+ `declare -A` and `setsid`, absent on macOS Bash 3.2.)
- `THE_ONE_REQUIRE_WEBKIT=1` `tests/browser/test_flow_narrow_layout.py`: **8 passed** (Chromium + WebKit).
- `THE_ONE_REQUIRE_WEBKIT=1` 7 UI control contract suites (342 items across `drawer`, `rail`, `tabs`, `modal`, `corner_button`, `composer`, `message`): **334 passed**, with 8 pre-existing macOS WebKit `Tab`-focus failures (`webkit 27.2` skips buttons/links on plain `Tab` by macOS default; Chromium passed 100%, WebKit `drawer`/`tabs`/`message` passed 100%).
- Chromium regression suites:
  - `tests/browser/test_shell_rail.py`: **18 passed**.
  - `tests/browser/test_flow_chat_drawer.py` + `tests/browser/test_flow_gleepglorp_drawer_shell.py`: **60 passed**.
  - `tests/browser/test_flow_chat.py`, `test_flow_chat_pane.py`, `test_flow_agent_tabs.py`, `test_flow_studio_navigation.py`, `test_flow_studio_library_list.py`, `test_flow_admin_settings_nav.py`, `test_flow_admin_tools_grid.py`, `test_flow_admin_tools_editor.py`: **152 passed**.
  - `tests/browser/test_flow_jump_to.py`: **4 passed, 22 failed** on pre-existing hardcoded `Control+K` / `"Jump to (Ctrl K)"` Linux assertions running on macOS (`Meta+K` / `"Jump to (⌘ K)"`).
- `scripts/ui_capture.py --widths 624,640` across 9 representative surfaces (4 destinations, dark + light): **36 PNGs, 0 failed, 0 skipped**.
