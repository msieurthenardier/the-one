# Leg: window-size-and-doctor

**Status**: completed
**Flight**: [Window Chrome](../flight.md)

## Objective

The desktop window opens at about the board's size, fitted to the screen, and can be
made as small as Windows' snap layouts need but no smaller than a sanity floor (flight
DD6). The-one doctor gains a tenth gate, `window chrome`, which proves the DWM path
loads in the packaged build (flight DD8). CI's needles check for it.

## Context

- **Flight DD6** (sizes and units) and **flight DD8** (the doctor gate) are the
  contract.
  - **DD6 has one change from its first draft:** the floor is a sanity minimum of
    640×360 (outer), not the 1024 supported minimum, so snap thirds and halves keep
    working (SC9). Whether to enforce 1024 is a DD12 preview question for the operator.
- **Leg 1a premise 6:** at 96 DPI the client rect is the outer rect minus 16px wide and
  39px high (a 31px caption and 8px frames). So 1440×900 outer gives a 1424×861
  viewport, which is at least 1280, so the agent drawer pushes.
- **pywebview 5.4** (`winforms.py`, lines 170–198):
  - width, height and `min_size` go to a form with `AutoScaleMode.Dpi`;
  - explicit `x`/`y` are multiplied by the scale factor, otherwise `CenterScreen`;
  - `get_screens()` (line 940) returns `Screen(x, y, width, height, frame=WorkingArea)`.

  So on first launch, pass width and height only. On WinForms, `screens[0].frame` is a
  .NET `Rectangle` (`.X`, `.Y`, `.Width`, `.Height`); on GTK, `frame` is the monitor
  geometry, not a work area.
- **Leg 2** changed `_create_kwargs` (it added `background_color` and `hidden=True`).
  This leg adds the size keys to the same dict without disturbing them.
- **The existing test** `tests/test_window_state.py::test_run_desktop_no_state_uses_defaults`
  (line 432) pins "no width or height when state is absent". This leg renames and
  inverts it (rename, not delete and re-add).
- **The doctor:**
  - `run_doctor` and its `gates` list are in `the_one/diagnostics.py` (lines 848–939).
    The probe contract (`report-what-you-got`, never raise) is in `the_one/agents.md`'s
    doctor section (lines 1564–1580).
  - `tests/test_doctor.py::test_gates_list_has_nine_names_ending_with_file_watcher` (line
    867) pins the line-up.
  - CI's needles: `ci/tasks/windows-installer-build.yml` (line 113, the `foreach`) and
    `.github/workflows/windows-installer.yml` (lines 96–111, `grep -q`). The GitHub
    runner is `windows-2022` (build 20348), so it takes the dark-mode-only branch.
  - `the_one/interfaces/desktop/chrome.py` already has `windows_build()` (line 82),
    reading `sys.getwindowsversion().platform_version[2]`.
- **Verification** uses the Windows test copy, as in leg 2, under the rules in
  `the_one/agents.md` "Windows test copy". The Flight Director notifies the operator
  before the session.

## Inputs

- Legs 1a, 1b and 2's uncommitted work.
- `the_one/interfaces/desktop/window_state.py` (`load_state`, `save_state`,
  `clamp_to_bounds`).
- `the_one/interfaces/desktop/shell.py`: `_create_kwargs` (line 634) and the saved-state
  restore block (lines 621–660).
- `the_one/diagnostics.py`, `tests/test_doctor.py`, `tests/test_window_state.py`.

## Outputs

- **`the_one/interfaces/desktop/window_state.py`**, pure and unit-tested:
  - `DEFAULT_SIZE = (1440, 900)`, `MIN_SIZE = (640, 360)`, `SCREEN_MARGIN = 64`;
  - `work_area(screens, platform) -> tuple[int, int, int, int] | None`:
    - on `win32`, the first screen's `frame` (`.X`, `.Y`, `.Width`, `.Height`), used only
      when all four are real numbers (`MagicMock`s create `.frame` on access);
    - elsewhere, the first screen's bounds, each side reduced by `SCREEN_MARGIN`;
    - None with no screens;
  - `first_launch_size(screens, platform) -> tuple[int, int]`: `DEFAULT_SIZE` fitted
    into the work area, never below `MIN_SIZE` unless the work area itself is smaller,
    in which case the work area wins; `DEFAULT_SIZE` when there is no work area;
  - `apply_floor(state) -> state`: lifts a saved width or height below `MIN_SIZE`, and
    leaves everything else unchanged.
- **`the_one/interfaces/desktop/shell.py`:**
  - `_create_kwargs` always gains `min_size=MIN_SIZE`.
  - **With no saved state:** `width` and `height` from `first_launch_size(screens,
    sys.platform)`, with **no `x` or `y`**. This uses the same robust `webview.screens`
    resolution the restore path already does; factor it into one helper.
  - **With saved state:** `apply_floor`, then `clamp_to_bounds` as today.
- **`the_one/diagnostics.py`:**
  - `_probe_window_chrome()`. It never raises (a broad `except` reports `ok=False`), and
    always reports a concrete value. It is unconditional, so it is not frozen-only:
    - **Off Windows:** `ProbeResult("window chrome", True, "skipped (not Windows)")`.
    - **On Windows:** load `ctypes.windll.dwmapi`, and call `DwmSetWindowAttribute(NULL,
      35, &value, 4)`, which is expected to return an error HRESULT for the null handle.
      Then:
      - build 22000 or later gives `ok=True` with `"caption colours supported (build N,
        probe 0x%08X)"`;
      - an older build gives `ok=True` with `"dark mode only (build N, probe 0x%08X)"`;
      - a failure to load dwmapi or find the function gives `ok=False`, naming the
        error.
    - The detail is ASCII only (cp1252 CI pipes).
  - It is appended **last** to `gates`.
  - `run_doctor`'s docstring is updated to ten gates.
- **CI needles:**
  - `"window chrome: OK"` is added to the `foreach` list in
    `ci/tasks/windows-installer-build.yml` and to its comment;
  - a `grep -q "window chrome: OK" doctor.out` line is added to
    `.github/workflows/windows-installer.yml`, beside the others.
- **Tests:**
  - **`tests/test_window_state.py`:**
    - `test_run_desktop_no_state_uses_defaults` is renamed to
      `test_run_desktop_no_state_uses_first_launch_size` and inverted. Its main-window
      `create_window` kwargs now carry `width`, `height` and `min_size`, with no `x` or
      `y`. The size is fitted to the mocked 1920×1080 screen, so 1440×900;
    - new pure tests for `work_area`, `first_launch_size` and `apply_floor`, plus a
      restore test showing a saved 400×250 lifted to 640×360 and a saved 1294×1399 kept,
      apart from clamping;
    - any other existing test that pins `_create_kwargs` exactly gains `min_size`, in
      place.
  - **`tests/test_doctor.py`:**
    - `test_gates_list_has_nine_names_ending_with_file_watcher` is renamed to
      `test_gates_list_has_ten_names_ending_with_window_chrome`, with `"window chrome"`
      appended;
    - new tests for `_probe_window_chrome` off Windows, and on a faked Windows with a
      fake `windll` (22000 or later, below 22000, and dwmapi missing);
    - a test that the detail is ASCII.
- **Docs:**
  - **`the_one/agents.md`:**
    - the doctor section: "The nine gates" becomes ten, with a row for `window chrome`,
      and the probe-contract counts change from "Seven of the nine" to the new numbers;
    - the "Desktop launcher" block: the first-launch size, the floor, the unit
      convention, and that `CenterScreen` centres on the screen under the mouse when
      there are several monitors (noted for Flight 6).
  - **`CLAUDE.md`:** the "ninth gate" sentence gains a mention of the tenth,
    `window chrome`, and the desktop launcher paragraph mentions the first-launch size and
    floor in one clause.
- **The flight log:** a "Leg 3: window-size-and-doctor" entry with the test-copy values.

## Acceptance Criteria

- [ ] **`window_state.py` unit tests:**
  - `work_area` on win32 with a numeric `frame`; on win32 with a `MagicMock` `frame`
    (falls back to bounds less the margin); on Linux; with no screens.
  - `first_launch_size`:
    - a 2560×1392 work area gives 1440×900;
    - 1366×728 gives 1366×728;
    - 600×400 gives 600×400 (the work area wins below the floor);
    - no screens gives 1440×900.
  - `apply_floor`: 400×250 gives 640×360; 1294×1399 is unchanged; a missing width or
    height is left as it is.
- [ ] **The renamed and inverted first-launch test** passes. Every other window-state,
  shell, tray and focus test passes, with any exact-kwargs pin updated in place for
  `min_size`.
- [ ] **The doctor:**
  - `_probe_window_chrome` tests pass;
  - `test_gates_list_has_ten_names_ending_with_window_chrome` passes;
  - on Linux, `the-one doctor` prints `window chrome: OK — skipped (not Windows)` and
    `RESULT: PASS`.
- [ ] **CI:** both needle lists include `window chrome: OK`. The Concourse file is still
  valid YAML, and the GitHub workflow still parses (`python -c "import yaml;
  yaml.safe_load(open(...))"`).
- [ ] **Test-copy verification on Windows**, bracketed by `snapshot` and focus, with the
  values recorded in the flight log:
  1. **From source, a fresh data dir:**
     - the main window's outer rect is 1440×900 (±2), centred in the work area: about
       (560, 246) on a 2560×1392 work area, ±2;
     - `innerWidth` is at least 1280 over CDP;
     - with a chat open, the drawer is in push mode (`#chat-drawer` visible beside
       `<main>`) if a chat can be opened. Otherwise the record says so.
  2. **A saved 400×250** gives a 640×360 (±2) outer rect at launch. A default-mode
     `drag` of the bottom-right corner inward by 300, 200 leaves it at 640×360 (±2).
  3. **A saved 1294×1399 at (1273, 0)**, the operator's own geometry shape, is restored
     at that size and position, clamped by `clamp_to_bounds`, not shrunk or centred.
  4. **Frozen:**
     - `freeze` (on the re-synced tree) builds;
     - `doctor --frozen` exits 0 with `RESULT: PASS` and **ten** gates, and its output
       contains `window chrome: OK — caption colours supported (build 26100, probe
       0x…)`;
     - CI's `foreach` check, run verbatim with the new needle list, passes.
- [ ] **Gates:**
  - `ruff check` and `ruff format --check` pass;
  - `TEST_TIMEOUT=3000 make test-unit` passes;
  - every Windows session's snapshot comparison is clean, or shows only an allowed
    change.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_window_state.py
  tests/test_desktop_shell.py tests/test_doctor.py tests/test_window_chrome.py
  tests/test_desktop_tray.py tests/test_window_focus.py -x --timeout 60`.
- `.venv/bin/the-one doctor` on Linux (it must print `window chrome: OK` and
  `RESULT: PASS`).
- `TEST_TIMEOUT=3000 make test-unit`, in the background.
- **The test copy:**
  1. `snapshot --out`, `focus-save`;
  2. `setup`;
  3. `launch` with a fresh dir, then `rect` and CDP `innerWidth`;
  4. `stop`;
  5. write the 400×250 state, `launch`, `rect`, `drag`, `rect`, `stop`;
  6. write the 1294×1399 state, `launch`, `rect`, `stop`;
  7. `freeze`, `doctor --frozen`;
  8. `focus-restore`, `snapshot --compare`.

## Implementation Guidance

1. **The pure functions and their tests** in `window_state.py` first.
2. **`shell.py`:**
   - factor the `webview.screens` resolution (list, iterable or callable) into one
     helper used by both paths;
   - add `min_size` and the first-launch size, plus `apply_floor` on the restore path;
   - keep leg 2's `background_color` and `hidden` keys.
3. **Rename and invert the first-launch test,** then update any exact-kwargs pins.
4. **The doctor probe,** its tests and the gate-list rename. Run `the-one doctor`
   locally.
5. **The CI needles** in both files.
6. **Docs.**
7. **The test-copy checks,** then the gates. Mark the leg `landed` and signal
   `[LAND:leg]`.

## Edge Cases

- **Several monitors.** The first launch uses `screens[0]`'s work area for sizing, and
  `CenterScreen` places the window. If the mouse is on another monitor, the window may
  centre there. This is acceptable, and noted for Flight 6.
- **A work area smaller than the floor** (a tiny or rotated screen). The size fits the
  work area, and WinForms' `MinimumSize` may still enforce 640×360, which is
  acceptable.
- **A corrupt `window-state.json`** loads as None, which takes the first-launch path, as
  today.
- **Scaling above 100%.** Untested (DD6). The unit convention is logical pixels, and the
  record says so.
- **A missing `dwmapi`** on a stripped Windows image gives `window chrome: FAIL`. That is
  intended: it is a packaging or OS defect.

## Files Affected

- `the_one/interfaces/desktop/window_state.py`, `the_one/interfaces/desktop/shell.py`
- `the_one/diagnostics.py`
- `ci/tasks/windows-installer-build.yml`, `.github/workflows/windows-installer.yml`
- `tests/test_window_state.py`, `tests/test_doctor.py`, and any shell or tray test with
  exact kwargs
- `the_one/agents.md`, `CLAUDE.md`
- The flight log: the Leg 3 entry. This leg file: status.

## Citation Audit

Checked on 2026-10-06 against the working tree after leg 2:
- **`shell.py`:** `clamp_to_bounds` import (line 621), `_create_kwargs` (line 634),
  `webview.screens` (line 648), main `create_window` (line 758).
- **`window_state.py`:** `clamp_to_bounds` (line 81).
- **`diagnostics.py`:** `_probe_desktop_shell` (line 128), `run_doctor` (line 848), the
  `gates` list.
- **`tests/test_doctor.py`:** the gate line-up test (line 867).
- **`tests/test_window_state.py`:** `test_run_desktop_no_state_uses_defaults` (line 432).
- **`ci/tasks/windows-installer-build.yml`:** line 113.
- **`.github/workflows/windows-installer.yml`:** lines 96–111.
- **`the_one/agents.md`:** the doctor gates (line 1564) and the probe contract (line
  1580).
- **`chrome.py`:** `windows_build` (line 82).
- **pywebview 5.4 `winforms.py`:** lines 170–198 and 940.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
