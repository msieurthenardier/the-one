# Leg: macos-probe-rerun

**Status**: in-flight
**Flight**: [macOS app](../flight.md)

## Objective
Fix the probe so its delegate premises can actually be observed, re-run it on the hosted runner (dispatch 2 of 5), and settle the decisions leg 3 left unanswered: the delegate route and `NSTerminateLater`, the reopen handler, Cmd-W's behaviour, and whether the product app triggers a local-network prompt.

## Context
- **Leg 3's section in the flight log** is the ground truth. `delegate_probe.py` declared `applicationShouldTerminate:` as `objc.typedSelector(b"Q@:@")`, but the installed prototype is `I@:@`. Both the subclass and `classAddMethods` routes raised `BadPrototypeError`, every launch ran pywebview's stock delegate, and `--selftest` passed anyway.
- **The other unknowns:**
  - a "M32 Probe … local network" permission prompt stayed on screen after the first probe launch and overlays later screenshots;
  - Cmd-W did nothing to the probe window but ended the product (the product had no tray, so close exits; why the probe ignored it is unknown: focus?).
- **The operator raised the cap to 5 dispatches** (2026-10-25). This is dispatch 2. The outward steps (commit, push, dispatch) are covered by the operator's go for the probe.

## Outputs
- **`packaging/macos/probe/delegate_probe.py`:**
  - The overrides take their signatures from the runtime, never hard-coded:
    - **Subclass route:** define the methods with **no explicit signature**, so PyObjC uses the inherited/protocol prototype. After definition, log each method's `.signature` and the superclass method's `.signature` (`BrowserView.AppDelegate.applicationShouldTerminate_.signature`).
    - **`classAddMethods` route:** build `objc.selector(fn, selector=…, signature=<the superclass's or the protocol's signature>)`.
  - The return value is `AppKit.NSTerminateLater`, whatever integer type PyObjC expects.
  - **`--selftest` exits non-zero (3) when the route is `none`,** so the workflow's selftest step fails visibly. The workflow keeps running the premise probe after a failed selftest (the step stays `continue-on-error` or the probe step uses `if: always()`; choose and record which), so a route failure still yields P1/P4/P8 evidence.
  - It logs `NSApp.delegate().className()` after window creation (the route actually in effect).
- **`packaging/macos/probe/probe.sh`:**
  - After every probe launch, dismiss a local-network prompt if one is up (bounded System Events: click "Allow" or "Don't Allow" in a `UserNotificationCenter`/`SecurityAgent`-owned dialog; record which and whether it worked) before any screenshot.
  - **P3's Cmd-W:** click inside the probe window first (System Events `click at` the window's centre from its `position`/`size`, bounded), then send Cmd-W. Record frontmost and the window's visible state before and after.
  - **P1:** sample at +1, +2, +3, +5, +10 s (denser early marks).
  - **A new row `PLN`:** after the product's first launch, record whether a local-network prompt naming **GleepGlorp AI** appeared (screenshot, plus the dialog's owning process and text through System Events, bounded).
- **The workflow is unchanged** unless the selftest-failure handling needs a step tweak (record it).
- **Rehearsal:** re-run leg 2's three Linux scenarios with the shims, plus a fourth in which the fake selftest reports route `none` (the selftest step fails, the probe still runs, the upload still happens).

## Acceptance Criteria
- [ ] **AC1:** the probe changes as listed. `ruff`, `py_compile`, `shellcheck`, `bash -n` (bash 3.2 syntax) and `actionlint` (if the workflow changed) are clean. The four rehearsals pass and are recorded.
- [ ] **AC2:** the Flight Director commits the probe changes plus the artifacts, pushes, and dispatches `mode=probe` (run id recorded).
- [ ] **AC3:** the evidence is downloaded to `$HOME/the-one-m32-evidence/f3/leg3b/`, and a `### macos-probe-rerun` flight-log section answers:
  - the route that installed, with both signatures as logged;
  - whether `NSTerminateLater` plus the deferred reply terminated the probe (quit Apple event, and Cmd-Q keystroke);
  - whether `applicationShouldTerminate:` was logged for Cmd-Q (path T, observed directly);
  - whether the reopen handler fired on `open -a`;
  - Cmd-W's effect on a focused probe window;
  - `PLN`: whether the product triggers a local-network prompt;
  - any changed reading of leg 3's other premises.

  Every divert criterion is re-evaluated, and the hosted minutes are recorded.

## Implementation Guidance
- Two spawns:
  - a Developer for AC1 (probe code plus rehearsal; edits only `packaging/macos/probe/` and, if needed, `.github/workflows/macos-packages.yml`; the on: block must stay byte-identical to the stub);
  - after the Flight Director's dispatch, a Developer for AC3 (evidence reading; edits only the flight log section and this leg's status).
- Leg 5's Developer works concurrently in `the_one/platform/`, `the_one/diagnostics.py`, `the_one/main.py` and tests. The probe never touches those.

## Files Affected
- `packaging/macos/probe/{delegate_probe.py,probe.sh,README.md}`, possibly `.github/workflows/macos-packages.yml`
- the flight log (its own section), this leg file

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
