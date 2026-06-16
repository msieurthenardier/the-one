# Flight Debrief: Windows Native App Hardening — Desktop Presence & Lifecycle

**Date**: 2026-06-15
**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](flight.md)
**Status**: landed
**Duration**: 2026-06-15 (plan + 5 autonomous legs + operator HAT over 4 Concourse rebuild cycles, single day)
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

The flight delivered a **single composable desktop-shell module**
(`the_one/interfaces/desktop/`: `shell.py`, `tray.py`, `notice.py`, `window_state.py`)
on top of F4's native window, giving the installed Windows app real always-on desktop
behavior — **system-tray + background-run** (close-to-tray, first-run notice,
Quit-from-tray as the real exit), **single-instance focus** (a second launch raises the
running window via a header-less loopback `POST /api/window/focus`), and **window-state
persistence** (geometry captured on close, restored, visible-bounds clamped). `app.py`
was reduced to a 14-line back-compat shim. The freeze recipe collects the desktop
package + pystray (`on_error="warn"`) + Pillow, with a frozen `the-one doctor`
desktop-shell gate. **Leg 6's operator HAT passed all 10 checkpoints + the
over-the-top-upgrade variant** on the real frozen Windows binary, after surfacing and
fixing five defects no CI could see. PR #115 is ready for review.

### Mission Criteria Advanced

- **(Re-scope addition) "The installed Windows app behaves like a polished, always-on
  desktop app — tray presence with background-run, persisted window state, single-instance
  focus."** — **delivered and HAT-backed** (run log
  `tests/behavior/windows-desktop-presence/runs/2026-06-15-18-00-00.md`). Splash + chrome
  remain F7.
- **"Launching the installed app opens the agent UI in a native window"** — extended: a
  second launch now focuses the running window instead of opening a duplicate (closes
  F4's gap).
- **"Preserves user state across restarts"** — extended to window geometry; re-confirmed
  the F4/F5 theme/web-storage persistence on a frozen, reinstalled binary (HAT step 9).

### Checkpoints

All flight checkpoints met. The packaged-smoke checkpoint was satisfied **better than
specified** — the frozen `the-one doctor` desktop-shell gate ran green on Concourse
builds #13–#16 (the desktop check is a hard gate when frozen, so `RESULT: PASS` proves
the lazily-imported `tray`/`notice`/`window_state` are actually bundled). The
rendered-window/tray/installer behavior — which has no CI apparatus (DD6) — was the
operator HAT, which passed.

## What Went Well

- **DD6 (no CI apparatus → operator HAT as a pre-merge gate) was the decisive call of
  the flight, and it was vindicated.** It caught **five** real defects mocked-GUI unit
  tests could not: the frozen `sys.stdout=None` crash, the `webview.screens` proxy-list
  crash, the on-show resize, the installer-over-the-top failure, and (operator-side) the
  stale container. Trusting the green mocked suite for acceptance would have shipped four
  code defects. The HAT was planned as a flight-level gate, ran on the branch before
  merge (builds #13–#16 off `flight/06`), and is exactly the right posture for frozen GUI
  work.
- **DD1 (single composable module, not a per-OS backend split) held cleanly.** Every one
  of the five fixes touched the composable shell directly; no OS branching was needed.
  The module is genuinely cross-platform-clean (the "abstract now" payoff): `window_state`
  is pure Python, `notice` is `Path`-only, `tray` uses pystray's cross-platform surface,
  and `shell` has a single pre-existing OS branch (`_webview_available`). The mac/Linux
  port is a localized change, not a rewrite.
- **Spike-driven Leg 2 surfaced subtle library constraints from source the team can't run
  locally.** `run_detached()` spawns a *non-daemon* thread → `icon.stop()` is mandatory
  (a skipped stop hangs the drain). The `shown.is_set()` pre-check on geometry capture
  avoided a 15-second GUI-thread freeze (reading `window.x` before shown blocks on
  `shown.wait(15)`). Both came from reading pystray/pywebview source at design time.
- **The crash-log-to-`data_dir` fix turned blind debugging into one-look diagnosis.** The
  `ensure_stdio_streams()` fix (#2) added a `data_dir/logs/the-one-app.log`; the very next
  bug (#3, the screens crash) was diagnosed instantly because the operator pasted the
  logged traceback instead of us guessing.
- **The scaffold-first sequencing delivered.** Leg 1 de-risked the refactor (consumer
  audit found exactly 3 importers; the back-compat shim covered all 3) before features
  piled on. No leg had to undo a prior leg's design.
- **The Origin-allowlist pre-analysis (DD4) was accurate** — a header-less loopback POST
  clears the middleware with no exemption; verified in the FD review and by test.

## What Could Be Improved

### Process

- **The `webview.screens` bug was predictable and the design-review process missed it.**
  Leg 4's review read pywebview's source and concluded `screens` is a *callable* needing
  parens. The installed library exposes it as a `proxy_tools` lazy property that *is* the
  list. Reading the attribute *definition* is not the same as knowing its *runtime form* —
  `proxy_tools`/descriptors/`cached_property` make attributes behave differently than
  import-inspection suggests. **Lesson: for library attributes that may be lazy-wrapped,
  verify the runtime form against a real install (`python -c "print(type(webview.screens))"`),
  not just the source.**
- **The mock reinforced the wrong API model and hid the bug until the HAT.** The test used
  `webview_mock.screens.return_value = [screen]` — "screens is a callable returning a
  list" — which is *not* what the real library does. Had the mock been
  `webview_mock.screens = [screen]` (an attribute holding a list), the code's `screens()`
  call would have raised `TypeError` in CI. **Standing lesson: mock the real runtime
  behavior/type, not the assumed API signature.** This belongs as an explicit cross-check
  in every GUI leg's design review.
- **Installer interaction with close-to-tray should have been in scope at flight design,
  not discovered at the HAT.** "X = hide, not quit" predictably defeats an installer's
  graceful-close on over-the-top upgrade. Any flight that changes close/hide semantics on
  a platform with an active installer should carry an "upgrade-over-running-instance"
  pre-flight checkpoint.
- **The frozen `console=False` stdio gap was a *named* F5 risk that became an F6 HAT
  discovery.** F5's debrief flagged the stdio/`console=False` gap; it could have been an
  explicit Leg-5/6 acceptance criterion rather than a launch-blocking surprise.

### Technical

- **`run_desktop()` is a ~180-line function with four nested lifecycle closures**
  (`_save_current_geometry`/`_on_closing`/`_on_show`/`_on_quit`). Correct-by-construction
  for a single-window app (the closures share `_desktop_window`/`_icon` state), but it
  makes the callbacks hard to unit-test directly and platform-divergence hard to inject.
  **Refactor to a `DesktopSession` class before the mac/Linux port** — that's the natural
  point where callbacks need platform-conditional paths (macOS `NSStatusItem` must run on
  the main thread; Windows tray runs detached).
- **The lazy-imports-for-testability pattern is in direct tension with PyInstaller static
  analysis.** `tray`/`notice`/`window_state` are imported inside function bodies →
  invisible to the freezer → would silently `ImportError` in the bundle. The end-of-flight
  review caught it (`collect_submodules("the_one.interfaces.desktop")`). This reconciliation
  must be explicit in every freeze recipe that bundles a lazily-imported package.
- **`_EventCapture` test helper is duplicated** across `test_desktop_tray.py` and
  `test_window_state.py` (slightly divergent). Extract a shared `tests/desktop_helpers.py`
  before the port adds more desktop test files.
- **Deferred known issue — single-instance vs a no-window `serve`.** `_select_port`'s
  `is_ours=True` (same version, port answers `/api/info`) can't tell a desktop instance
  from a headless `serve`; the focus POST returns `{"focused": false}` and the launcher
  silently exits. Recommended fix: a `has_window` discriminator (in `/api/info` or the
  focus response) so the second launch can choose a visible behavior (raise / notify /
  open browser) rather than vanish. (Operator chose to land F6 and defer this.)

### Documentation

- Docs (`agents.md`/`README.md`/`CLAUDE.md`) were updated for the tray/Quit/focus/window-state
  behavior. **Gaps to add**: (a) the canonical `webview.screens` resolution + the
  "clamp dimensions before origin, union-not-first-screen" geometry rule; (b) why the
  `.spec` needs `collect_submodules("the_one.interfaces.desktop")` + `on_error="warn"`
  (comments in the spec); (c) the `sys.modules`-injection + `_EventCapture` test pattern
  for future desktop test authors.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `webview.screens()` (callable) → robust list/callable resolution | Installed pywebview exposes `screens` as a `proxy_tools` list, not a function | **Yes** — verify dynamically-wrapped attrs against a real install; mock the real type, not `.return_value` |
| Windowed entry redirects `None` stdio to a `data_dir` logfile | Frozen `console=False` → `sys.stdout=None` → uvicorn `isatty()` crash | **Yes** — crash-log-to-`data_dir` in every `console=False` freeze recipe |
| Installer `CloseApplications=force` + `PrepareToInstall` taskkill | Close-to-tray turns the installer's WM_CLOSE into hide; over-the-top upgrade couldn't close the app | **Yes** — audit installer close behavior whenever close/hide semantics change |
| `_on_show` drops `restore()` | `restore()` resized a merely-hidden (not minimized) window | Lesson — `hide()`≠`minimize()`; `show()` un-hides, `restore()` un-minimizes |
| Docs folded into Leg 5 (freeze) | Convenience | Lesson — name a docs scope or a separate leg; folding obscures the freeze leg's diff |
| Single-instance vs no-window-`serve` deferred | Needs a coexistence design decision; edge case | Operator-accepted known issue → follow-up flight |

## Key Learnings

- **Test-metric snapshot** (host-native): **3173 passed / 10 skipped / 589 deselected /
  ~326 s**, 0 failures, no flakes across two runs. vs F5 (3115/10/589/~419 s): **+58
  tests** (the six new desktop suites: tray 17, window-state 22, focus 8, frozen-stdio 7,
  doctor-probe 5, net shell ~0). Wall-clock dropped back to ~F4 territory (326 s) — F5's
  419 s was its subprocess-heavy freeze-seam tests; F6's new tests are all fast mock-GUI
  unit tests. Headless-Linux caveat: pywebview/pystray aren't installed here ([gui] needs
  GTK headers), so every desktop suite runs against `sys.modules`-injected mocks — which
  is precisely why the HAT was load-bearing.
- **Reading a dependency's source is necessary but not sufficient for proxied/lazy
  attributes.** The single highest-value lesson: verify runtime *form* (`type(...)`)
  against a real install, and make mocks match that form.
- **A frozen GUI app needs a crash log on day one.** `console=False` swallows every
  traceback; `ensure_stdio_streams()` → `data_dir/logs` converts silent death into a
  pasteable error. This should be standard freeze hygiene, not a HAT discovery.
- **The operator HAT is the only apparatus that can act-and-observe the native surface.**
  DD6 named this; the flight proved it. For frozen GUI features, HAT-before-merge is a
  gate, not an afterthought.
- **Operator product signal worth carrying forward**: the unauthenticated localhost API
  is a real concern — confirmed as the explicitly-planned *next* mission ("secure the
  API"); F6 didn't change that surface. Port 8484 validated as an appropriate
  registered/user port.

## Recommendations

1. **Codify "verify runtime form, mock the real type" for GUI dependency APIs.** Add to
   the leg-design-review step: for any library attribute a leg reads, confirm its runtime
   type against a real install and make the test mock match that type (`module.x = value`,
   not `module.x.return_value = value`). This one rule would have caught the flight's worst
   bug at design time.
2. **Standardize the frozen-GUI hygiene pair: crash-log-to-`data_dir` + HAT-before-merge.**
   Put both in the packaging/flight checklist for any `console=False` freeze or
   close/hide-semantics change — plus an "over-the-top upgrade with the app in the tray"
   installer test.
3. **Refactor `run_desktop()` → a `DesktopSession` class and extract
   `tests/desktop_helpers.py` BEFORE the mac/Linux port.** Both are cheap now and pay off
   exactly when the port adds platform-conditional callbacks and a third/fourth desktop
   test file.
4. **Resolve the single-instance-vs-`serve` gap in a follow-up** with a `has_window`
   discriminator so a second launch never silently vanishes (raise / notify / open
   browser). Tracked in mission Known Issues.
5. **Update the stale `leg-execution.md` crew prompt** (still says `docker exec the-one
   pytest …`; M15 retired Docker) to the host-native `python -m pytest` command — flagged
   at this flight's kickoff and overridden per-spawn, but it should be fixed at the source
   before F7/the follow-up mission.

## Action Items

- [ ] Follow-up flight: fix single-instance-vs-no-window-`serve` (add `has_window`
      discriminator; the launcher chooses a visible behavior). (Mission Known Issues.)
- [ ] Before the mac/Linux desktop-shell port: refactor `run_desktop()` → `DesktopSession`
      class; extract `tests/desktop_helpers.py` (shared `_EventCapture`/mock-window).
- [ ] Update `.flightops/agent-crews/leg-execution.md` to drop the `docker exec` test
      command (host-native `python -m pytest`).
- [ ] Docs: add to `agents.md` the `webview.screens` resolution + the clamp algorithm +
      the `sys.modules`-injection test pattern; comment the `.spec`'s
      `collect_submodules(...)` + `on_error="warn"`.
- [ ] Methodology: codify the two standing lessons — "verify runtime form / mock the real
      type for proxied GUI attrs" and "crash-log-to-data_dir + HAT-before-merge for frozen
      GUI" — and add the "upgrade-over-running-instance" installer checkpoint.
- [ ] Strengthen `test_both_close_paths_write_geometry` and add an `_on_quit`-fires
      geometry-capture test (currently tests the guard inline, not the wired closure).
- [ ] At release: bump version (F6 is a feature add; HAT builds were `0.2.1` → `0.3.0`).

## Skill Effectiveness

- **The Mission/Flight/Leg hierarchy held up well.** The 6-leg breakdown was correctly
  sized and sequenced (scaffold → features → freeze → HAT); per-leg design reviews were
  again the dominant pre-HAT quality driver.
- **The `flight` skill's design-review step under-specified runtime-form verification for
  wrapped attributes.** It correctly pushed "read the dependency source," but the
  `webview.screens` miss shows the prompt should explicitly ask: "for any library attribute
  this leg reads, what is its runtime *type*, verified against a real install, and does the
  mock match it?"
- **`/agentic-workflow`'s interactive-HAT path worked as designed** — the FD guided the
  operator step-by-step, fixed inline (spawning Developers), and rebuilt via Concourse
  between fixes. The four fix→rebuild→reinstall→re-verify cycles are the expected shape of
  frozen-GUI HAT debugging; the skill handled the long interactive leg cleanly.
- **The behavior-test methodology adapted correctly to an un-automatable surface.** The
  `windows-desktop-presence` spec ran operator-driven (no automated Executor/Validator can
  reach a native Windows GUI — DD6); the run log honestly records the apparatus. This is
  the right degenerate case of the Witnessed pattern: human Executor, FD Validator.
- **Skill-boundary discipline held**: the FD overrode the stale crew `docker exec` test
  command per-spawn (per the boundary rule) rather than coupling to it — flagged for a
  source fix.
