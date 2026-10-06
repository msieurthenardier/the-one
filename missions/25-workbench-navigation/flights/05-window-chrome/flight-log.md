# Flight Log: Window Chrome

**Flight**: [Window Chrome](flight.md)

## Summary

**Status**: ready (planned 2026-10-06, after two Architect review cycles).

---

## Reconnaissance Report

**Sources:**
- the Flight 5 research digest (read-only reconnaissance of `b044cab`, the pywebview 5.4
  and 6.2.1 wheels, Microsoft Learn and the WebView2 specs, and the Windows host; kept in
  the Flight Director's scratchpad);
- the Flight 4 debrief's Flight 5 action item;
- the mission's Known Issues and the open design question for Flight 5.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Mission open question: "Window chrome mechanism" (spike non-client regions) | confirmed-live; answered by research and operator decision | pywebview 5.4 SDK 1.0.2957.106 has `IsNonClientRegionSupportEnabled`, but snap layouts need the prerelease-only window-controls overlay, and a frameless form loses resize | DD1: tinted native bar (operator, 2026-10-06). Close the mission question at landing. |
| Known Issue: Ctrl K in WebView2 (Flight 4 DD9) | confirmed-live | No packaged-build observation exists | DD9: crew-verified with a real `SendInput` key in leg 1 and at the close gate. The operator confirms at Flight 6. |
| F4 debrief: route any desktop shortcut through `App.shortcuts` | already-satisfied for this flight | The flight adds no shortcut | Recorded in DD13. |
| F4 debrief: respect the static drawer slot and `--drawer-w` | already-satisfied by design | The native caption is outside the page | DD13. The first-launch size puts the drawer in push mode. |
| The `agents.md` footgun note is imprecise for pywebview 5.4 | confirmed-live | `the_one/agents.md` lines 66–74, against 5.4 `util.py` and `customize.js` | Corrected in leg 2 (DD13). |
| First launch opens at 800×600 | confirmed-live | `shell.py` passes no size without `window-state.json`; the 5.4 defaults | Leg 3 (DD6). |
| A white flash before a dark page paints | confirmed-live | 5.4 `background_color='#FFFFFF'` default | Leg 2 (DD4). |
| The splash's hard-coded `#0f1117` | confirmed-live | `shell.py` lines 51 and 143 | Leg 2 (DD4). |
| `windows-native-frame-splash` step 9 is stale under the credential gate | confirmed-live | The spec's own Preconditions "Known gap" | Leg 4. |
| Restore drift at more than 100% scaling (pywebview multiplies `x`/`y` by the scale factor) | needs-human-recheck | Inferred from 5.4 `winforms.py`; the operator's screen is 100% | Out of scope. Not observable on this host; noted for the Flight 6 operator walk. |

---

## Leg Progress

*(entries added as legs land)*

---

## Flight Director Notes

### Planning (2026-10-06)

- **The operator's answers.** "Tinted Windows bar (Recommended)" and "Test copy on my
  desktop (Recommended)".
- **Planning probes,** all read-only on the Windows side:
  - `powershell.exe` from WSL runs in session 1;
  - `C:\Python311` (3.11.9, pip, uv) and Git for Windows are present;
  - the installed `the-one-app.exe` is PID 208344 in session 1;
  - DPI is 96;
  - WSL networking is mirrored;
  - `%LOCALAPPDATA%\the-one` holds no `.env`, and its `window-state.json` is a right-half
    snap at 1294×1399.
- **Concourse** at `localhost:8080` timed out from `fly`, so the local freeze replaces
  `fly execute` (DD10).
- **Design review, cycle 1** (Architect, Opus): **approve with changes**. One high, nine
  medium and six low issues. All were incorporated:
  - **High: input safety on a live desktop** (DD10).
    - Windows are found by PID tree only.
    - A foreground check and a `WindowFromPoint` check run before every injection.
    - An occlusion check runs before sampling.
    - Bringing the window to the front is premise 13.
    - Injection is held off while the operator is typing (`GetLastInputInfo`).
    - The inactive state uses a window the helper owns.
  - **Medium:**
    - The first-post race (DD3): register before show, record a requested theme, mark a
      theme sent only on a 2xx, and serialise posts.
    - The DD3/DD7 contradiction: persistence is cross-platform, and only the tint is
      Windows-gated.
    - DPI units (DD6): no `x`/`y` on first launch, so pywebview uses `CenterScreen`; the
      work area is `screens[0].frame`.
    - The floor against snapping (DD6): a 640×360 floor instead of an enforced 1024, made
      a preview question.
    - Spec step 7's false failures: wait, then × to the tray, then kill.
    - The stale safety check: a snapshot of the operator's data dir replaces "file
      absent".
    - Per-session re-checks: the operator's `.env` and the host record.
    - The user-agent fallback replaced by `window.chrome.webview`.
    - The closure copied verbatim from CI.
  - **Low:**
    - The build from `platform_version`.
    - The doctor gate gets a concrete HRESULT and a CI needle.
    - The tests that will break are named.
    - "Outer" is stated.
    - Plain `def` routes.
    - The browser-test stub order.
  - **Suggestions taken:** the doctor gate moves to leg 3; the token pin covers `--bg`; the
    splash is themed in full; the HWND is checked with `IsWindow`; the `events.shown`
    premise; launch hygiene; the watchdog; `/api/info` in step 1; minimize in step 9.
  - **Structural changes,** so a second cycle follows: a new premise 13, a reshaped DD3
    and DD6, and a new leg 3 scope.
- **Design review, cycle 2** (Architect, Opus, the last allowed): **approve with
  changes**, nothing blocking. It confirmed every cycle-1 fix landed, and raised six
  mediums and fourteen lows on the revisions. All were applied:
  - **M1, a lock deadlock.** Every DWM apply now runs on the UI thread through `Invoke`.
    The lock guards state only and is never held across `show()` or `Invoke`.
  - **M2, inactive text.** Applies use the tracked activation state, with a unit test and
    a step-5 sub-step.
  - **M3, launch visibility.** Premise 13 now covers it, and steps 1 and 7 fall back to
    `PrintWindow`, else INCONCLUSIVE.
  - **M4, input rules.**
    - Pointer input is gated on `WindowFromPoint` only.
    - The hands-off check ignores the helper's own input and runs once per gesture.
    - No Alt-key trick.
    - Step 9 restores with `ShowWindow`.
  - **M5, stop.** `stop` waits for the whole tree and both ports. The process tree
    includes the venv launcher's child.
  - **M6, environment.** The session record gains the system theme, title-bar accent,
    transparency and any existing `WEBVIEW2_*` variables. **DD5 is committed to activation
    tracking**, the designer's answer to the review's question 2.
  - **Lows:**
    - the dedup rule;
    - `IsHandleCreated`;
    - the splash border in `before_show`;
    - the palette pin covers every hex;
    - the kernel32 build note;
    - Win32-gated work area;
    - `CenterScreen` with several monitors;
    - GTK's hidden no-op;
    - premise 10 answered from source;
    - the GitHub needle and the gate's position and line format;
    - two citation drifts;
    - the spec wording;
    - reset, the atomic write and handler exceptions;
    - the sibling-prefix test;
    - re-runnable `setup`.
  - **Answers to the review's questions:**
    1. The apply runs on the UI thread.
    2. DD5 is committed.
    3. Unoccluded launches that prove impossible make steps 1 and 7 INCONCLUSIVE and
       move them to Flight 6.
  - **Suggestion taken:** leg 1 lands its non-injecting parts first.
- **Status: ready.** The flight is planned after two review cycles.

---

## Decisions

*(runtime decisions not in the flight spec)*

---

## Deviations

---

## Anomalies

---

## Session Notes
