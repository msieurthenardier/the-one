# Behavior Test: the macOS app installs and behaves like a Mac app on a real Mac

**Slug**: `macos-app-install`
**Status**: draft
**Created**: 2026-10-24
**Last Run**: never

## Intent
Verifies Mission 32's macOS criteria on a real Apple Silicon Mac, which the operator does not have:
- the downloaded, ad-hoc signed `.dmg` is approved once through Gatekeeper and installed by dragging;
- the app opens in its own window with the brand icon in the Dock;
- closing keeps it in the Dock, the Dock brings it back, and Cmd-Q quits;
- size and position are remembered;
- replacing N with N+1 keeps the user's data;
- moving the app to the Trash leaves the data;
- `doctor` passes from Terminal.

The hosted runner (Mission 32 Flight 3, DD9) proves what it can reach without a person. This test covers what only a real user session shows: Gatekeeper's approval flow, Finder, the Dock, and a real display.

## Preconditions
- **Apparatus:** a contributor's Apple Silicon Mac on a recent macOS. Record `sw_vers` and the chip. A human Executor performs each action, following `docs/macos-contributor-check.md`, and returns screenshots and command output. The Flight Director and a Validator judge from that evidence.
- **Packages:** the `.dmg` for versions N, N+1 and N+2 (macOS 14 or later, Apple Silicon), from a dispatched `macos-packages.yml` run (its `macos-dmg` artifact; Flight 4 provides fresh builds), with sha256 recorded. They are downloaded through a browser, so they carry the quarantine attribute a real download has.
- **Safety:** use a macOS user account the contributor is willing to give GleepGlorp AI data to. Never share the credential secret, only the `loc_<id>` prefix. Remove nothing outside `/Applications/GleepGlorp AI.app` and, at the very end and only if the contributor agrees, `~/Library/Application Support/the-one/`.
- **Credential:** read from `~/Library/Application Support/the-one/api-credential` (CLAUDE.md "Behavior-test credential convention", shell-only shape) for the `curl` reads.

## Observables Required
- **log:** the tail of `~/Library/Logs/GleepGlorp AI/app.log` when a step fails (the log shows `dock: window hidden on close`, `reopen: decision=show`, the quit drain lines).
- **screen:** the contributor's screenshots (Cmd-Shift-4): the Gatekeeper dialogs, the `.dmg` window, the app window, the Dock.
- **shell:** Terminal output of the listed commands.
- **http:** `curl` with the bearer credential against `127.0.0.1:8484`:
  - `GET /api/live`;
  - `GET /api/window/state` (`visible`, `tray: "dock"`, `pid`, `version`);
  - `GET /api/agents`.

## Steps
*(Draft. Wording finalized from the hosted run `40213503970` and the probe runs (Flight 3, leg `macos-hosted-checks`); it has never been run on a real Mac. The contributor's written form is `docs/macos-contributor-check.md`, numbered the same.)*

| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | Download the N `.dmg` in Safari and double-click it. | The disk image opens a Finder window showing "GleepGlorp AI" and an "Applications" shortcut. |
| 2 | Drag GleepGlorp AI onto Applications, then open it from Applications. | macOS refuses the first open with a dialog "GleepGlorp AI" Not Opened ("Apple could not verify ... is free of malware"; on macOS 15 only Done and Move to Trash, no Open button; older-style wording on other versions). No app window appears. Record the version and the exact wording. |
| 3 | Click Done, then follow the guide's approval steps (System Settings › Privacy & Security › Security › Open Anyway, authenticate, confirm Open). Record whether Open Anyway appeared and the screens shown. | Within 30 s a GleepGlorp AI window shows the Chats start page ("Hello."). The Dock shows the brand icon. No second Gatekeeper prompt appears later. |
| 4 | Close the window with the red button. Wait 5 s. Run the state `curl`. | The window is gone, the Dock icon stays with its running dot, and the state reads `visible: false` and `tray: "dock"`. No notification appears. |
| 5 | Click the Dock icon. Run the state `curl`. | The same window comes back in front with `visible: true`, and the `pid` is unchanged. |
| 6 | Resize the window and move it to a new spot. Press Cmd-Q. | The app quits within 10 s. The Dock's running dot is gone, and `curl /api/live` is refused. No "quit unexpectedly" dialog appears. |
| 7 | Open the app from Applications again. | It opens at the size and position from step 6, with no Gatekeeper prompt. |
| 7a | Right-click the Dock icon and choose Quit. | The app quits within 10 s, as in step 6, with no "quit unexpectedly" dialog. |
| 8 | Create an agent through the app (or `POST /api/agents`). Quit with Cmd-Q. Install N+1 the same way (steps 1-3), replacing the app in Applications. | Finder asks to replace it. After the replace and the approval, the window opens, the version from `/api/window/state` is N+1, and the agent from this step is listed. |
| 9 | With N+1 running, install N+2 the same way *without quitting first*, then open it from Applications. | Observation step, not a pass/fail on the replace itself. Hosted probe P5 (macOS 15.7) saw the old copy crash with a missing-resource exception once its bundle was swapped (an earlier run saw it keep running), so either outcome is acceptable: record whether Finder refused or replaced, whether a crash dialog appeared, and which version and pid answer `/api/window/state`. The data (the step 8 agent) must be intact either way, and after a Cmd-Q and a fresh open, N+2 answers. The guide says to quit first. |
| 10 | In Terminal (the guide's section 8), run `"/Applications/GleepGlorp AI.app/Contents/MacOS/the-one" doctor`. | It ends `RESULT: PASS`, or it fails only the python interpreter gate with the guide's "install Python 3" message on a Mac with no Python. The output includes `tray: dock` and a `path:` line (`login shell` expected). |
| 11 | Quit, then move GleepGlorp AI from Applications to the Trash. List `~/Library/Application Support/the-one/`. | The app is gone, and the data directory still holds its database and the `api-credential` file. |

## Out of Scope
- Intel Macs (mission scope).
- Notarized or Developer ID signed builds (no Apple account).
- Menu-bar icons (operator: Dock only).
- Multi-display geometry beyond one move on the main display.
- Release publishing (Flight 4).

## Variants
| variant | macOS |
|---|---|
| contributor-1 | whatever the first contributor runs; record `sw_vers` |
