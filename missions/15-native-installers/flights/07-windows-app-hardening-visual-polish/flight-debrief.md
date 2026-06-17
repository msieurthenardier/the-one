# Flight Debrief: Windows Native App Hardening — Visual Polish

**Date**: 2026-06-17
**Flight**: [Windows Native App Hardening — Visual Polish](flight.md)
**Status**: landed
**Duration**: 2026-06-15 (planning) → 2026-06-17 (landed); execution 2026-06-15 → 06-17
**Legs Completed**: 7 of 8 (Leg 3 `window-resize` mooted by the DD3 divert — native frame resizes)

## Outcome Assessment

### Objectives Achieved
The installed Windows app now *looks* finished: a launch **splash** (README brand logo via a
frozen-safe base64 data URI, dismissed when the UI loads), a crisp **brand icon** (256/128/64
`.ico`) on the window/taskbar/Alt-Tab, and a **branded native desktop window**. All shipped
behind a `DesktopSession` lifecycle refactor of the F6 desktop shell.

The flight's *original* objective — a **frameless custom-chrome** window — was **not** achieved
and was deliberately abandoned mid-flight (DD3 divert → DD2-alt). It proved infeasible on Windows
WebView2. The *re-scoped* objective ("the installed Windows app behaves like a polished desktop
app — visual half") was achieved via the native frame, which delivers drag/min/max/close/resize
natively and is a strictly more robust result than the planned custom chrome would have been.

### Mission Criteria Advanced
Advanced the M15 re-scope criterion *"the installed Windows app behaves like a polished, always-on
desktop app"* — F7 delivered the **visual** half (splash, native window, icon); F6 delivered the
presence/lifecycle half. HAT-verified on the real install (`/behavior-test
windows-native-frame-splash`, 10/10, build #22).

### Checkpoints
The flight's in-flight checkpoints were written for the frameless plan; the splash/icon/HAT
checkpoints met, the frameless-chrome/resize checkpoints superseded by the divert (annotated in
flight.md; the live record is the flight-log PIVOT entry).

## What Went Well

- **DD6 (HAT-before-merge) was vindicated.** The operator HAT caught **three** real defects across
  five builds (#18–#22) that no host-native unit test could (pywebview is mocked on Linux): the
  `_boot` no-arg crash (hung splash), the `pywebviewready` bridge race (controls not rendering),
  and — decisively — the frameless/WebView2 incompatibility that forced the pivot. The "visual
  polish is even more HAT-dependent" calculus was exactly right.
- **DD1 (DesktopSession refactor) landed cleanly** with zero F6 test adaptations — the design
  review's catch of the dual `_really_quit` reach points + the `focus_window` module-global
  contract, *before* implementation, made the module-global bridge work first try.
- **The splash spike de-risked the architecture before coding** — confirmed two pywebview windows
  coexist + surfaced the writable-`storage_path` footgun (the `C:\Python311` red herring).
- **The DD3 divert was executed cleanly** — Leg 8 removed all frameless plumbing with a
  dead-reference grep gate; the merged branch carries no dead code (verified).
- **The behavior-test-as-acceptance pattern worked** — the `windows-native-frame-splash` spec was
  the only apparatus that could verify native window behavior, and the run log captures the full
  story.

## What Could Be Improved

### Process
- **The chrome spike tested the wrong thing.** DD7 ("verify every pywebview API against a real
  install before locking") was the right principle, but the spike that ran (`spike_splash.py`)
  exercised only *multi-window coexistence* — a structural cousin of the chrome question. It never
  injected a `js_api`, clicked a wired button, tested a drag region, or checked frameless resize.
  A complete chrome-interaction spike would have surfaced — in minutes — that js_api/drag/resize
  are inert on WebView2, forcing the native-frame decision **before** a full leg (Leg 2:
  `_WindowApi`, `_watchBridge`, win-controls injection, CSS, 16 unit/Playwright tests) was built
  and then discarded. **Lesson: a real-install spike must exercise the exact interaction surface
  the design depends on, not a runtime cousin — and it must run before the leg, not at the HAT.**
- **"Likely inoperative" from a source read should gate, not defer.** Leg 2's spec correctly
  flagged `easy_drag` as "likely inoperative on Windows edgechromium" (pywebview's source guards
  it on `platform=='chromium'`) but framed it as a deferred "HAT observation" rather than a
  blocking go/no-go spike. When a dependency's source shows a platform-conditional branch that
  excludes the target runtime, that is a spike pre-condition.

### Technical
- **Test metrics (this run):** full suite **3178 passed / 10 skipped / 589 deselected / 0 failures
  / 0 flakes** in **312.55 s** (`pytest --durations=20 -q --timeout=60`). **vs F6** (3173 passed /
  ~326 s): **+5 tests** (net of the Leg-4 splash tests added and the Leg-2 chrome tests added then
  deleted in Leg 8), wall-clock −14 s (within noise; the same pool/PTY/execution suites dominate,
  unchanged by F7). No new slow outliers, skips, or deselections. Pre-existing warnings persist
  (aiosqlite loop-closed teardown race on `test_db_migration.py::TestSchemaV17`; discord `audioop`
  / starlette / websockets deprecations) — none introduced by F7.
- **Test-helper triplication is now debt.** `_EventCapture` and `_make_splash_mock()` are each
  copied across `test_desktop_shell.py`, `test_desktop_tray.py`, `test_window_state.py`, and the
  `_EventCapture` copies have **diverged** (different `is_set` defaults). The F6 debrief
  recommended extracting `tests/desktop_helpers.py`; F7 added a third copy instead. The mac/Linux
  port will add a fourth — extract now.
- **Stale comments after the pivot:** `shell.py:30` still says `# HAT-deferred (Leg 7)…` (the HAT
  passed); `_close_to_tray()`'s docstring still names `_WindowApi.close()` as a caller (removed in
  Leg 8); `_SPLASH_TEXT_ONLY` carries `-webkit-app-region: drag` CSS (Electron-only; inert on
  WebView2 — harmless but inconsistent with the Leg-8 cleanup).
- **A silent pywebview contract:** `webview.start(func)` calls `func()` with **no arguments**;
  defining `_boot(splash_win)` crashed the boot thread and passed CI (tests called
  `_boot(mock_splash)`, matching the bug). The post-fix tests call `_boot()` with no args, enforcing
  the contract — but there's no static guard against re-introducing a defaulted parameter.

### Documentation
- The pywebview/WebView2 **frameless footgun is now documented in `agents.md`** (Leg 6) — good.
  The `_boot` no-arg call convention should be added there too (it caused a full HAT cycle).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Frameless custom chrome → native OS frame (DD3 divert → DD2-alt) | js_api/drag/resize all inert on Windows WebView2; pywebview frameless targets CEF/GTK/Qt | **Yes** — native-frame-first is the standard for this app's desktop window on all platforms (operator decision 2026-06-17) |
| `_wait_until_serving` + main-window create moved into `webview.start(func=_boot)` | A splash can only be visible during the boot wait if the wait runs inside the GUI loop | Yes — this is the permanent launch architecture; preserve the `_boot()` no-arg convention |
| Leg 3 (`window-resize`) never executed | Native frame provides edge-resize; conditional leg mooted by the divert | N/A — correct conditional-leg behavior |
| Splash logo embedded as a runtime base64 data URI (not a bundled file path) | Freeze-safe; the server isn't serving when the splash shows | Yes — the pattern for any pre-server desktop asset |

## Key Learnings

1. **Real-install spikes must exercise the exact interaction surface.** The single most expensive
   miss this flight (builds #18–#20 of speculative chrome work) traces to a spike that tested
   coexistence instead of chrome interaction. This is a generalizable methodology gap, not a
   one-off.
2. **Mocked-dependency unit tests give false confidence for runtime-form bugs.** The `_boot`
   signature bug and the `pywebviewready` race both passed CI green and failed the real install.
   Host-native pytest validates *logic*; only the HAT validates *pywebview/WebView2 runtime form*
   (DD7's intent). Keep the HAT gate; don't trust green CI as readiness for native behavior.
3. **Native-frame-first is the right default.** F4/F6 shipped `frameless=False` and HAT-passed;
   the frameless switch was the sole source of all the jank. The conservative default for a
   platform-shell flight is the OS-native frame, with custom chrome only as a spike-gated bonus.
4. **The DesktopSession refactor's "strictly minimal class" rule paid off** — no scaffolding to
   undo when the splash and the divert both reshaped the launch path.

## Recommendations

1. **Codify a "platform-verification spike" as a first-class, pre-implementation gate** (mission-
   control methodology improvement): for any leg depending on a dependency API whose behavior on
   the target platform is unverified, a throwaway script exercising *that exact API surface* runs
   on the target platform and its go/no-go result is recorded in the flight log **before** the leg
   is implemented. Distinct from a feasibility spike (pre-flight) and a HAT (post-implementation).
2. **Extract `tests/desktop_helpers.py`** (`_EventCapture` parametrized on its `is_set` default +
   `_make_splash_mock()`) before the mac/Linux port adds a fourth copy. *(Carries forward the F6
   debrief's deferred recommendation — now higher priority.)*
3. **Add the `_boot()` no-arg pywebview contract to `agents.md`** next to the frameless footgun;
   it caused a full HAT cycle and is a silent crash-on-real-install class of bug.
4. **Housekeeping pass** on the post-pivot stale artifacts: remove the `shell.py:30` HAT-deferred
   comment, scrub the `_close_to_tray` docstring's `_WindowApi` reference, and decide intentionally
   on the `_SPLASH_TEXT_ONLY` `-webkit-app-region` CSS (drop it, or comment why it's kept for a
   future WKWebView splash).
5. **For the follow-up macOS/Linux desktop mission:** native-frame-first on all platforms (operator
   decision); reuse the `DesktopSession` + `_boot` architecture; budget a `pystray`-on-macOS
   review (different backend/threading); each platform needs its own HAT — do not assume the
   WebView2 experience transfers.

## Action Items
- [ ] Extract `tests/desktop_helpers.py` (dedupe `_EventCapture` + `_make_splash_mock`) — fold into
      the next desktop-touching flight or the mac/Linux port's first leg
- [ ] Housekeeping: remove stale `shell.py:30` comment; scrub `_close_to_tray` docstring; resolve
      `_SPLASH_TEXT_ONLY` app-region CSS
- [ ] Add the `_boot()` no-arg pywebview contract note to `agents.md`
- [ ] *(Methodology — mission-control)* Propose the "platform-verification spike" leg type to the
      `/leg` / `/flight` skills so DD7-style "verify the runtime before locking" is gated at the
      leg, not deferred to the HAT
