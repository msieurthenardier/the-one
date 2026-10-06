# Leg: windows-apparatus-input

**Status**: completed
**Flight**: [Window Chrome](../flight.md)

## Objective

Add the input and capture half of `scripts/windows_test_copy.py`:
- a helper-owned window;
- bringing the test copy to the front;
- screen captures and pixel samples;
- real keyboard and mouse input.

Each command carries the input-safety checks of the flight's DD10. The leg also answers
spike premises 1, 2, 3, 4, 7, 9, 11 and 13, so legs 2 and 3 can be designed on observed
facts.

## Context

- **Leg 1a landed**, and this leg extends its helper. Read 1a's flight-log entry and the
  "Windows test copy (M25 F5 L1a)" block in `the_one/agents.md` first.
  - **The helper's shape.** A WSL CLI validates arguments. It runs a Windows half: the
    same file piped to `C:\Python311\python.exe -` (stdlib only), with JSON in and out,
    dispatched through `_OPS`. The Windows half has `proc_table`, `_top_windows` (which
    already returns DWM `frame_bounds`), `op_rect`, `op_hands_off` and the guarded
    writes `g_write` and `g_read`.
  - **Launching and stopping.** `launch` (including `--script` for spikes) records an
    identity-checked tree under `R\pids\`. `stop` kills with one handle per process and
    logs to `audit.log`.
  - **Tree selection.** `_selected_trees(root, None)` returns every recorded tree.
  - **The hands-off rule.** `operator_input_recent` reads `R\last-injection`, which
    nothing writes yet. This leg writes it.
- **1a's findings that this leg relies on:**
  - `chrome.webview` exists at document start, and `pywebviewready` fires about 20ms
    after `load`.
  - The client rect equals `innerWidth`×`innerHeight`. The caption is 31px; the
    invisible frame is 8px at the sides and bottom (96 DPI).
  - The HWND is stable across hidden and shown.
  - CDP works on 9390 and up.
  - The frozen build exists.
  - The host: OS app and system themes Light, `ColorPrevalence` 0, transparency on.
- **Flight DD10, "Input safety on a live desktop"**, is the contract. Read it in full.
  This leg makes it concrete, and **applies the hands-off rule to every focus change as
  well as to input**, because a focus change while the operator types sends their keys
  to the wrong window.
- **The operator consented** (2026-10-06). Their installed `the-one-app.exe` runs on
  **port 8484 in session 1**, with the same window title as the test copy. The Flight
  Director tells them in chat when this leg's Windows work starts and ends. **The cursor
  and the foreground belong to the operator:**
  - the helper puts the cursor back unless the operator moved it;
  - it hands the foreground back only when doing so cannot take it from something the
    operator chose.
- **No product code changes.** Spike prototypes (DWM colour calls, hidden then show)
  are throwaway scripts in the Flight Director's scratchpad, started only through
  `launch --script`.
- **Scope decisions** (from this leg's design review):
  - **The own window is not a tree.** It is a separate record that no tree gate, `tree`
    listing or `launch` live-tree check ever matches.
  - **Drags may not end over an operator window.** Snap-to-edge checks stay with the
    operator at Flight 6.
  - **`launch` may gain an opt-in `--via-own` mode** if premise 13 shows that launch-time
    visibility needs it. Its default behaviour is unchanged.

## Inputs

- Leg 1a's uncommitted work: `scripts/windows_test_copy.py`,
  `tests/test_windows_test_copy.py`, the `agents.md` block, the `CLAUDE.md` sentence and
  the flight-log entry.
- The scratch root `C:\Users\cprch\AppData\Local\Temp\the-one-f5\` (`src\`, `venv\`,
  `src\dist\`). Re-run `setup` first; it copies only changed files.
- 1a's spike scripts in
  `/tmp/claude-1000/-home-cprch-projects-the-one/0eb14466-3200-4ca3-9529-5ff071966eae/scratchpad/f5-spike/`.

## Outputs

- **`scripts/windows_test_copy.py`:** the commands below, plus their pure helpers.
- **`tests/test_windows_test_copy.py`:** the new pure-function tests.
- **`the_one/agents.md`:** the "Windows test copy" block extended (1b). It covers the
  commands, the checks, the decided techniques, the capture rules, the restore rules and
  the known limits.
- **The flight log:** a "Leg 1b: windows-apparatus-input" entry. It has the premise
  table, the premise-13 trial matrix, each session's snapshot result and an
  `input.log` summary.

## Gate rules

**The gate target.** One target tree, resolved by a pure `select_gate_pids(trees,
target_id)`: the tree named by `--tree-id`, else the single recorded tree (refused if
there are several).
- The own windows' records (`R\own.json`, and `R\own-b.json` for window B) are never
  trees. The gates allow an own window only as a click target, never as a drag end, and
  only after an identity check: the HWND's owner PID and that process's creation time
  must match the record.
- Its PID is never in the gate PID set, so a key gate never accepts it.

**Hands-off.** It runs before every gesture and every focus change:
- `keys`, `click`, `drag`;
- `front`, `own-window show` (and `own-window do`, re-checked inside the own window's
  process), `show-window`, `focus-restore`;
- `launch` and `launch --via-own` (which keep 1a's call);
- `own-window close` and `stop` when the window they close is in front.

**Check order.** Immediately before each `SendInput`, and in this order: the hands-off
check, then the foreground or pointer gate, then the send. Hands-off can wait several
seconds, which would make an earlier gate result stale.

**A refinement of DD10.** DD10 says "check once before a compound gesture, never between
its events". The leg is stricter on purpose: it also aborts mid-gesture on operator
interference (below).

**The `last-injection` model.**
- A pure, injectable `record_injection(send, read_tick, write)` sends one batch, then
  reads `GetTickCount()`, then writes `R\last-injection`, so the helper's own input never
  counts as the operator's.
- A multi-batch gesture updates it after each batch. It aborts, with everything
  released, if `GetLastInputInfo` advances past the helper's own last tick by more than
  one timer tick (16ms; `GetLastInputInfo` is quantised to about 15ms). That counts as
  operator interference. The comparison uses `tick_age`, so it is safe across a wrap.
- `SetCursorPos` alone (the cursor restore) must not register as operator input. This is
  checked on the host.

**Keys.**
- **The foreground gate.** Before each key-down, `GetForegroundWindow()` (resolved with
  `GetAncestor(GA_ROOT)`) must be in the gate set. Otherwise the gesture aborts.
- **Release.** Every pressed key is released in a `finally`, and `release-all` releases
  every modifier and mouse button on demand.
- **Key codes.** Keys are sent as virtual keys from `VkKeyScanW` on the current layout,
  or as scan codes.
- **The grammar** is a small explicit one: `^` Ctrl, `+` Shift, `%` Alt, `{NAME}` named
  keys, plain text, and `{^}`, `{+}` and `{%}` for those characters typed literally. It
  is parsed by a pure function, which **refuses**:
  - any Win-key token;
  - Alt+Tab, Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc;
  - Alt+F4 (close the test copy with its × or `stop` instead);
  - Ctrl+Alt+anything;
  - PrintScreen;
  - media, volume, browser and launch keys;
  - any F-key with Alt or Win.

**Pointer input.**
- **Positioning.**
  1. Before any cursor movement, `WindowFromPoint(target)` plus `GA_ROOT` must be in the
     gate set or be the identity-checked own window. So a refused click never moves the
     cursor.
  2. Then `SetCursorPos(target)`.
  3. Then re-check: `GetCursorPos` must equal the target, and the same `WindowFromPoint`
     check must pass again.
  4. Only then does a coordinate-less button event go out. No `MOUSEEVENTF_ABSOLUTE`.
- **Release.** The button is released in a `finally`.
- **The cursor restore** puts the cursor back to its saved position only if it is still
  where the helper left it. If the operator moved it, the helper leaves it alone. A pure
  `cursor_restore_decision(saved, left_at, now_at)` holds the decision.
- **`drag` modes:**
  - **`--caption`:** the start must be on the gate tree's main window caption (inside its
    frame bounds, within 31px of the top, left of the caption buttons). The window's
    post-move frame bounds (its current bounds plus the delta) must lie inside the work
    area of the monitor that contains it. The end point lies inside those post-move
    bounds.
  - **Caption mode, after the move:** the helper re-checks that the window is where
    planned (within 4px). Otherwise it reports `moved-unexpectedly`.
  - **The default (content or resize):** the start must be in the gate tree's window.
    The end must lie inside that window's **current** frame bounds, **and**
    `WindowFromPoint(end)` (`GA_ROOT`) must be in the gate set itself (an own window does
    not count for a drag end), checked before starting, so a covered end point is
    refused. That covers spec step 8's inward
    corner drag.
  - **Both:** every step re-checks `GetCursorPos` against the planned point, and (in
    default mode) `WindowFromPoint` at that point. It aborts, with the button released,
    if either check fails.

**Captures.**
- **The containment area** is the gate tree's main window's DWM extended frame bounds
  (`frame_bounds`, attribute 9), never `GetWindowRect`, whose invisible 8px margins show
  the operator's content. The own window's frame bounds also count. `--rect` must lie
  inside one of them.
- **The occlusion test** is an exact Z-order check.
  - **Above** means earlier in `EnumWindows` order than the target.
  - **Skipped as occluders:** windows that are not visible, are cloaked
    (`DWMWA_CLOAKED`), are zero-size, have `WS_EX_TRANSPARENT`, or are layered with zero
    alpha.
  - **What happens.** Any other window above the target that intersects the capture rect
    fails the test:
  - for a single capture, the capture is refused;
  - for a series, the frame is tainted and its pixels discarded;
  - an intersecting own window is reported as `covered_by_own`, never attributed to the
    test copy;
  - an intersecting window of the test copy's own tree (the splash, a dialog) is
    reported as `covered_by_tree`.
  - **The diagnostic flag `--allow-own-cover`** (premise 11 only) takes the capture
    anyway when every intersecting window is the identity-checked own window, so the
    covered pixels are the helper's own content. The output says so.

  It runs before and after each grab.
- **`--print-window` frames** (`PrintWindow` with `PW_RENDERFULLCONTENT` on the main
  window) are exempt from the occlusion test, and say so.
- **Visibility and containment per frame.** Each frame re-resolves the main window's
  frame bounds:
  - With `--window`, a frame taken while no visible main window exists records only its
    timestamp and `no-window`, with no pixels.
  - With a fixed `--rect`, a frame where the rect is not inside the current bounds
    records `no-window` or `outside`, with no pixels.

  That is how premise 4's series starts before `show()`. It uses a `--rect` over the
  caption strip, because the 256 MB cap allows only about 60 frames of a full
  1280×800 window.
- **How:** stdlib only. `ctypes` GDI `BitBlt` into memory, a stdlib PNG writer (`zlib`),
  and pure-Python patch statistics.
- **Series:**
  - at most 200 frames, with intervals of at least 16ms;
  - total raw bytes at most 256 MB;
  - frames held raw in memory and encoded after the series ends;
  - timestamps from `QueryPerformanceCounter` (`time.perf_counter`), which is system-wide.
- **Files** go under `R\evidence\`.

**The own window.**
- **What it is:** a small stdlib window (200×100, titled `the-one-f5 helper`) run as a
  detached process and recorded in `R\own.json` (PID, creation time, path, HWND).
- **Placement:** by default the bottom-left of the primary work area, or `--at x,y`. It
  must not overlap the gate tree's main window when that matters (premises 1, 2 and 7).
- **Showing:** `SW_SHOWNOACTIVATE` with `WS_EX_NOACTIVATE`, so showing it never takes
  the foreground. Activation happens only through a gated, hands-off-checked click.
  - A second `own-window show` while a live record exists is refused.
  - `show` returns only after the own process has written its HWND to `own.json`.
- **Topmost:** not by default. `--topmost` is only for `front` attempts, at most 60s at a
  time.
- **A second window, B.** `own-window show --id b` makes a second helper-owned window
  (`R\own-b.json`, same rules). It stands in for "some other foreground" in premise
  13's trials, so the operator's real foreground is rarely displaced.
- **Lifetime:** it closes itself after `--seconds` (60 by default, at most 600).
- **`own-window close`** verifies the HWND's owner PID and creation time before posting
  `WM_CLOSE`, then falls back to the identity-checked kill. `stop` with no tree id also
  closes it.
- **The command channel.** It polls a guarded command file `R\own\cmd.json`, so actions
  that must be made by the foreground process (premise 13) run inside it.
  - **An allowlist:** `front-tree` and `restore-focus` only.
  - **Each command** carries a nonce and an expiry of 5s, and is deleted after use. An
    expired or repeated nonce is ignored and logged.
  - **The own process re-checks** before acting: hands-off, the gate-set identity check,
    and for `restore-focus` the focus decision table.

**Focus save and restore.**
- **`focus-save`** writes `R\focus.json`: the foreground HWND, its owner PID and that
  process's creation time. The first save of a session wins:
  - a save is refused while a fresh saved record exists, and when the current foreground
    is the gate tree or an own window;
  - a stale record (its identity no longer matches, or it is older than 2 hours) is
    replaced;
  - `focus-save --discard` deletes a record explicitly.
- **`focus-restore`** acts only when the current foreground is in the gate tree, is the
  own window, or is nothing. If the operator has moved to another window, it leaves it
  there. It checks the saved identity, uses the decided technique from premise 13 (from
  the own window's process when that is the technique), and verifies the result with
  `GetForegroundWindow()` about 300ms later.
- **Outcomes:** `restored`, `already-foreground` (no action), `failed`, `gone` (the
  identity no longer matches) or `operator-moved-on`. It then deletes `R\focus.json`.
- **Session order:** `focus-restore` runs after `stop` (closing the tree may itself move
  the foreground) and before `own-window close`, because the decided technique may run
  from the own window's process.

**Logging.** Every gesture appends a row to `R\input.log`, tagged with a per-session run
id:
- the time and the gesture;
- the target HWND, its owner PID, and whether that is the gate tree or the own window;
- the outcome: `sent`, `aborted` with a reason, or `refused` with the rule.

## The commands (this leg)

| Command | Behaviour |
|---|---|
| `own-window show [--id a\|b] [--at x,y] [--topmost] [--seconds N]` / `own-window close [--id …]` / `own-window do ACTION` | The own window or windows (see Gate rules). `do` writes an allowlisted command (`front-tree` or `restore-focus`) for window A to run. |
| `front [--tree-id T]` | Brings the gate tree's main window to the front with premise 13's decided technique. If the window is minimised, it uses `SW_RESTORE` first. It reports `in_front` only if `GetForegroundWindow()` is still that window about 300ms later. |
| `capture --out F (--window \| --own \| --rect x,y,w,h) [--series N --interval-ms M] [--print-window] [--allow-own-cover]` | See Gate rules. |
| `pixel --x X --y Y [--size 9]` | The patch's mean RGB, plus its darkest and lightest pixels (by luminance), inside the containment area and under the occlusion test. |
| `keys SPEC` | See Gate rules. |
| `release-all` | Releases every modifier and mouse button. It is safe at any time, and is meant for a blocked or aborted path. |
| `click X Y [--double]` | See Gate rules. The output carries exact `before`, `target` and `after` cursor positions. |
| `drag X1 Y1 X2 Y2 [--caption] [--steps N]` | See Gate rules. The output reports the same cursor positions. |
| `show-window --restore\|--minimize\|--maximize` | `ShowWindow` on the gate tree's main window, after the identity and hands-off checks. |
| `focus-save [--discard]` / `focus-restore` | See Gate rules. |

## Acceptance Criteria

- [ ] **Unit tests.** `tests/test_windows_test_copy.py` adds pure tests for:
  - `select_gate_pids`: one tree, several trees with and without `--tree-id`, and the own
    record never included;
  - the key grammar: valid specs, every refused combination above, malformed specs;
  - drag planning: caption start detection, post-move bounds in the work area, the
    default mode's end inside the current bounds, refusals;
  - capture containment against frame bounds, and the Z-order intersection logic, from a
    fixture window list (including `covered_by_own`);
  - the series limits (frames, interval, bytes);
  - patch statistics, the darkest and lightest pixels, and WCAG contrast;
  - the own window's timeout and placement clamps;
  - `record_injection` ordering (send, then read, then write), and the interference
    check on both sides of the one-tick tolerance and across a wrap;
  - `cursor_restore_decision`;
  - the `focus-restore` decision table (restored, already-foreground, failed, gone,
    operator-moved-on, and no action when the operator moved on);
  - `focus-save`'s first-save-wins rule, the staleness replacement and `--discard`;
  - the occlusion fixtures: a cloaked window, a transparent overlay, a tool window, an
    own window (`covered_by_own`) and a tree window (`covered_by_tree`);
  - a default-mode drag whose end point is covered by a foreign window (refused);
  - the `own-window do` allowlist, nonce and expiry;
  - the `{^}`, `{+}` and `{%}` literals.

  All 1a tests still pass.
- [ ] **On this host, bracketed by `snapshot --out` / `snapshot --compare` and
  `focus-save` / `focus-restore`:**
  - `own-window`, `front`, `capture` (single, series and `--print-window`), `pixel`,
    `keys`, `click`, `drag` (both modes), `show-window` and `release-all` each work on
    the from-source copy, on 8490 or higher with a fresh `R\data-l1b-*`;
  - each pointer command's output shows the cursor restored to its exact `before`
    position, or left alone because it moved;
  - `hands-off` called immediately after an injection, and after a `SetCursorPos`-only
    cursor restore, returns clear without waiting;
  - `focus-restore`'s outcome is recorded.
- [ ] **Negative checks shown working,** with nothing sent, each logged as `refused` in
  `input.log`:
  - `keys ^k` while the own window is in front;
  - `keys` with a Win-key token, and with `%{TAB}`;
  - a `click` at a point over the taskbar;
  - a `capture --rect` outside the frame bounds;
  - a default-mode `drag` whose end is outside the tree window;
  - a default-mode `drag` whose end is inside the tree's bounds but covered by own
    window B (refused, because B is not the drag's target window).
- [ ] **Premises answered** in the flight log. Each row gives the method, the observed
  values, a verdict and the consequence for legs 2–3:
  - **1.** On a spike pywebview window (active), with the colours applied on the UI
    thread through `window.native.Invoke`: the caption's empty middle (right of the title
    text, left of the buttons) samples within ±3 per channel of the target, in both
    themes, with the HRESULTs recorded. The splash's border is applied in `before_show`
    and sampled on its edge.
  - **2.** Under the OS Light theme (the only one testable without changing the
    operator's OS): the WCAG contrast between the minimize glyph's extreme pixel (the
    darkest on a light caption, the lightest on a dark one) and the caption sample. Four
    cases: light caption with attribute 20 off and on, dark caption with it off and on.
    The matched case reaches 3:1 or better, and the mismatched case's result is
    recorded.
  - **3.** On a shown window, with both sides timing on `QueryPerformanceCounter`: the
    time from the script's apply call to the first frame sampling the new caption. If
    none appears within 1s, add a frame redraw (`SetWindowPos` with `SWP_FRAMECHANGED`,
    or `RedrawWindow` with `RDW_FRAME`) and re-measure.
  - **4.** `hidden=True`, then tint, then `show()`, with a 16–50ms series started before
    `show()`, over the caption strip (`--rect`). Recorded as "no default-caption frame in N visible frames at M ms", or the
    frames that showed one. Also: whether `events.shown` fired, and whether the window
    was in front about 300ms after `show()`.
  - **7.** With a custom text colour and no activation tracking: the title text's
    darkest or lightest pixel, active and then inactive (the own window in front,
    placed so it does not overlap). This is information only; DD5 is committed to
    tracking.
  - **9.** A real Ctrl+K into the from-source copy (product code unchanged since `main`):
    - `front`, then a `click` at a page-body point derived from CDP (an empty area's
      rect plus the window's client origin);
    - `keys ^k` opens `[data-testid="jump-to"]` with focus in `jump-to-input`, read over
      CDP;
    - `keys {ESC}` closes it;
    - otherwise the failure is recorded.
  - **11.** What `CopyFromScreen` needs.
    - With the own window covering part of the test copy, a normal capture is refused
      and reported `covered_by_own`; that refusal is the passing outcome.
    - The same capture with `--allow-own-cover` produces the comparison pixels, showing
      what a naive capture would have attributed to the test copy. Whether `PrintWindow` renders the DWM-tinted caption, compared
    with a `CopyFromScreen` capture of the same window. A locked session may be recorded
    as "not observed".
  - **13.** The trial matrix, recorded in the flight log:
    - **Production candidates.** Every one is reachable from the helper's own processes
      (the helper, own window A, or `launch --via-own`) and touches only the tree's own
      window or the own windows:
      1. `SetForegroundWindow` from own window A's process, after a click on it;
      2. `SwitchToThisWindow`;
      3. `SetWindowPos` topmost, then not topmost, with the not-topmost step always run in
         a `finally`;
      4. minimise, then restore, on the tree window.
    - **Informational only, through a `launch --script` spike:**
      `AllowSetForegroundWindow(tree pid)` from own window A, then `SetForegroundWindow`
      from inside the tree. Product code is unchanged, so this cannot be a production
      technique.
    - **Never:**
      - `AttachThreadInput` with a foreign thread;
      - `AllowSetForegroundWindow(ASFW_ANY)`;
      - `SPI_SETFOREGROUNDLOCKTIMEOUT`, `LockSetForegroundWindow` or any other change to
        system state.
    - **Before the matrix,** `focus-save` is taken, and every trial runs hands-off first.
    - **Trials:** candidates are tried in the order listed, stopping at the first that
      reaches "decided". Each gets five trials starting from own window B in front (a
      stand-in for "some other app in front") and five starting from own window A in
      front.
    - **"Decided"** means five out of five from both starts.
    - **Real-foreground trials.** Then the decided candidate gets exactly **2 trials**
      starting from the operator's real foreground, each restored afterwards with
      `focus-restore`. A trial that fails to restore is logged and reported in the
      Developer's final message, so the Flight Director can tell the operator.
    - **Also covered:**
      - launch-time visibility: does a plain `launch` open in front, behind or depending
        on the foreground at launch? If needed, `launch --via-own` (the own window's
        process starts the tree) is added as an opt-in and tested in five out of five
        trials;
      - which technique `focus-restore` uses;
      - whether "foreground is nothing" is reachable on this host (for example right
        after `stop`).
    - **If nothing reaches five out of five,** the best result is recorded and the
      flight's Divert criterion is raised (`[BLOCKED:no-foreground-technique]`).
- [ ] **The operator's installation is untouched.**
  - Every session's snapshot comparison is clean, or one of the allowed changes,
    recorded in the flight log.
  - `audit.log` lists every kill.
  - `input.log` shows every `sent` gesture targeted the gate tree or the own window. The
    flight log summarises the counts of `sent`, `aborted` and `refused`.
  - No system setting was changed.
- [ ] **Docs.** The `agents.md` block is extended (see Outputs).
- [ ] **Gates.**
  - `ruff check` and `ruff format --check` pass on `scripts/` and `tests/`.
  - `TEST_TIMEOUT=3000 make test-unit` passes.
  - Apart from the flight artifacts the Flight Director owns, `git status` shows changes
    only in `scripts/windows_test_copy.py`, `tests/test_windows_test_copy.py`,
    `the_one/agents.md` and `CLAUDE.md`.

## Verification Steps

- **Unit tests:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_windows_test_copy.py -x --timeout 30`, then `TEST_TIMEOUT=3000 make
  test-unit`.
- **Lint:** `.venv/bin/ruff check scripts/ tests/` and `.venv/bin/ruff format --check
  scripts/ tests/`.
- **A session:**
  1. `snapshot --out`, `focus-save`;
  2. `setup`;
  3. `launch`;
  4. `own-window show` (A, and B for the trials), then the premise-13 trials, then
     `front`;
  5. `rect`, `capture` (single, series, print-window), `pixel`;
  6. the negative checks;
  7. `click`, `keys`, `drag` (both modes), `show-window`, `release-all`;
  8. `stop`;
  9. `focus-restore`, then `own-window close` (A and B), then `snapshot --compare`;
  10. read `input.log` and `audit.log`.
- **Premises:** each row names its spike script (in the scratchpad's `f5-spike/`) or its
  commands, and the observed values.

## Implementation Guidance

1. **Read 1a's code, its flight-log entry and the `agents.md` block.** Keep 1a's default
   behaviour unchanged. Add new ops to `_OPS`, and reuse `op_rect`, `proc_table`,
   `_top_windows` (with its `frame_bounds`), the guarded writes and `op_hands_off`.
2. **The pure parts and their tests first:**
   - `select_gate_pids`;
   - the key grammar and its refusals;
   - drag planning;
   - containment and the Z-order intersection;
   - the series limits;
   - patch statistics and contrast;
   - the own window's clamps;
   - `record_injection`;
   - the focus decision table.
3. **The Windows layer** (stdlib only):
   - DPI awareness: `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` first.
   - Input: `SendInput` with `INPUT` structs (`# noqa: N815` for Win32 field names),
     `SetCursorPos` and `GetCursorPos`, and `WindowFromPoint` with `GetAncestor`.
   - Captures: GDI `BitBlt` and `PrintWindow` into a DIB section, and a stdlib PNG
     writer.
   - Logs: `input.log` rows.
4. **The own windows** (`ctypes` `CreateWindowExW` with `WS_EX_NOACTIVATE`, a
   command-file poll, run detached by the venv's `pythonw.exe`). Then the premise-13
   trials (B and A starts, then 2 real-foreground trials). Then `front`, `focus-save` and
   `focus-restore` on the decided technique.
5. **Captures and pixels,** then the input commands, then the negative checks.
6. **The spike for premises 1, 2, 3, 4, 7 and 11,** as `launch --script` scripts:
   - The scripts call `DwmSetWindowAttribute` (attributes 20, 34, 35 and 36) on the UI
     thread through `window.native.Invoke`. They set `storage_path` under their scratch
     data dir, and record HRESULTs and `perf_counter` timestamps (apply, showing) to a
     JSON file there.
   - Premise 2's glyph patch is centred on the minimize button: its centre lies 46px ×
     2.5 left of the caption's right frame edge at 96 DPI, at the caption's vertical
     centre. Confirm it on a capture before measuring.
7. **Premise 9** on the from-source copy, reading over CDP from WSL with the repo
   `.venv`'s Playwright. The click point comes from CDP.
8. **Record:** the flight-log entry (premise table, trial matrix, sessions, `input.log`
   summary) and the `agents.md` block.
9. **Finish:** run the gates, mark the leg `landed`, and signal `[LAND:leg]`.

## Edge Cases

- **The operator is active.** The hands-off rule waits, then exits 3. Report it, without
  retrying in a loop. If it happens repeatedly, stop with `[BLOCKED:operator-active]`
  after `release-all`.
- **A locked session.** Captures come back black. Run `release-all` and report
  `[BLOCKED:session-locked]`. Never lock or unlock the session.
- **The foreground changes mid-gesture,** or the cursor moves. The gesture aborts with
  everything released, and the abort is logged.
- **A toast or other topmost window covers the capture.** The occlusion test refuses or
  taints the frame; wait and retry once, or move the sample within the caption.
- **A second monitor** appears. Coordinates are screen pixels, and work-area checks use
  the monitor that contains the window.
- **The helper is killed mid-gesture.** A key may stay pressed. The next helper call
  runs `release-all` first whenever `input.log` ends with a gesture that has no outcome
  row.
- **The own window outlives a crashed session.** Its timeout closes it, and `stop`
  closes it after the identity check.

## Files Affected

- `scripts/windows_test_copy.py`: the input and capture commands, and any opt-in
  `launch --via-own`.
- `tests/test_windows_test_copy.py`: the new pure tests.
- `the_one/agents.md`: the "Windows test copy" block extended for 1b.
- `missions/25-workbench-navigation/flights/05-window-chrome/flight-log.md`: the Leg 1b
  entry.
- This leg file: status transitions.

## Citation Audit

Checked on 2026-10-06 against the working tree after leg 1a, and re-checked by the
design review:
- **`scripts/windows_test_copy.py`:**
  - `_OPS` (line 1689);
  - `op_hands_off` (line 1139);
  - `operator_input_recent` (line 450) and `parse_last_injection` (line 468);
  - `op_launch` (line 1200; its live-tree check is at lines 1209–1214);
  - `_selected_trees` (line 1337), `_top_windows` (line 1372; returns `frame_bounds`),
    `op_windows` (line 1414), `op_rect` (line 1420) and `op_stop` (line 1436).
- **`the_one/agents.md`:** "Windows test copy (M25 F5 L1a)" (line 1832).
- **The flight log:** "Leg 1a: windows-apparatus-core", with its premise table and the
  host record.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
