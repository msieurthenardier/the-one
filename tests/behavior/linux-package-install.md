# Behavior Test: Linux packages install and behave like an app on fresh desktops

**Slug**: `linux-package-install`
**Status**: active
**Created**: 2026-10-24
**Last Run**: 2026-10-24-20-34-28 (44/44 PASS — see `runs/2026-10-24-20-34-28.md`)

## Intent
Verifies Mission 32's Linux criteria on real, fresh GNOME desktops: install without a terminal, a menu entry with the brand icon, a window, tray or no-tray close behaviour, relaunch, quit, an N to N+1 upgrade that keeps the user's data (taken over from a still-running N), and an uninstall that leaves the data. Each step runs for both packages (the `.deb` and the AppImage) on both distros (Ubuntu 26.04 and Debian 13).

This needs a real desktop session: a tray host (or its absence), a notification service, the file manager and package installer, and the compositor's window handling. Unit tests and Flight 1's containers cannot provide those. That is why this is a Witnessed behavior test.

## Preconditions
- **The fresh-VM apparatus (Mission 32 Flight 2, DD9):**
  - a QEMU/KVM guest inside a Docker container named `m32-vm-<distro>`;
  - booted from a fresh overlay of the provisioned snapshot (stock GNOME desktop, autologin as the test user, sshd);
  - SSH and QMP sockets reachable from the host;
  - nothing the packages need pre-installed;
  - the test user has passwordless `sudo` in the guest (used only for apparatus commands; the install steps still type the polkit password through QMP where a user would);
  - GDM autologin applies only at boot: after a logout the guest shows the login screen, so step 11 logs back in by typing the test user's password through QMP.
- **Packages:** the two package files for version N, and the same two for version N+1, built by the flight's pinned container or the hosted run. They are copied into the guest's `~/Downloads`, and their sha256 is recorded.
- **Safety:** the app runs only inside the guest, on the guest's default port and data dir. Nothing runs on the host's 8484 or 8485, and the host data dir is never touched.
- **Credential:** read from the guest's `~/.local/share/the-one/api-credential` over SSH (CLAUDE.md "Behavior-test credential convention", shell-only shape). Only the `loc_<id>` prefix is ever printed.

## Observables Required
- **screen:** QMP `screendump` PNGs of the guest display (what a user sees). Where a step names a timed capture, take screendumps at the stated offsets from the triggering action (a notification banner expires within seconds, so a single capture after a fixed wait can miss it).
- **window geometry:** the remembered window size, read as the window's outer size from the compositor (`xdotool`/`gdbus` or the `window-state.json` in the data dir) before closing and after relaunching. Position is X11-only (DD7) and is not asserted.
- **shell:** guest commands over SSH (stdout, exit codes, file listings).
- **http:** the app's API inside the guest, through SSH:
  - `GET /api/live`;
  - `GET /api/window/state` (`desktop`, `visible`, `tray`);
  - `GET /api/agents`.
- **input:** QMP keyboard and mouse events (`usb-tablet` absolute pointer): file-manager double-clicks, installer buttons, the polkit password, the title-bar close button, and the app-grid right-click "Quit GleepGlorp AI".

## Steps

Run once per variant (see Variants).

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Boot a fresh overlay. Wait for the GNOME session. Screendump. Over SSH, list `~/.local/share/the-one`, and run `command -v the-one`. | Desktop visible and logged in, with no first-run wizard. The data dir does not exist, and `the-one` is not installed. |
| 2 | Install package N the way a user would, by QMP keyboard and mouse only. `.deb`: double-click it in Files, which opens App Center (Ubuntu) or GNOME Software (Debian); choose Install; type the user's password into the polkit dialog. AppImage: in Files, Properties, allow executing as a program, then double-click it (the app process then runs under the AppImage runtime, `AppRun`/`mount` parent, not as a child of Files, so identify it by the AppImage path, never by Files as its parent). No terminal, `apt`, `dpkg` or `pkcon`. Screendump at each dialog. | The install completes with no error dialog, and no extra system-package step is asked for. `.deb`: `dpkg -s gleepglorp-ai` (read over SSH) reports installed, version N. AppImage: the app starts. |
| 3 | Open the Activities app grid and search "GleepGlorp". Screendump. | The entry "GleepGlorp AI" (`.deb`) or "GleepGlorp AI (AppImage)" is shown with the brand icon, not a generic one. |
| 4 | Launch the entry from the app grid (if it is not already running from step 2). Wait up to 30 s. Screendump. Read `GET /api/window/state`. | The app window is on screen with the Chats start page rendered (the welcome greeting "Hello." is visible), not blank. `/api/live` answers 200. The state reads `desktop: true, visible: true` (from GTK). `tray` is `indicator` on Ubuntu (stock AppIndicator extension) and `none` on Debian (no tray host). |
| 5 | Over SSH, with the session's environment (`XDG_RUNTIME_DIR=/run/user/<uid>`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus`), run `the-one doctor` (`.deb`) or `<AppImage> doctor`. | Exit 0. No gate detail contains `skipped`, except `window chrome: OK — skipped (not Windows)`. The `sandbox:` line names bubblewrap or a passthrough reason. The `tray:` line matches step 4. |
| 6 | Seed data through the API: a provider `m32-vm-provider` with a dummy API key, the agent `m32-vm-agent`, and a chat session for it (`POST /api/chat/sessions`, titled `m32-vm-chat`). Record the credential's `loc_<id>` prefix. | `GET /api/agents` lists `m32-vm-agent`. The provider is listed with a stored key (masked). `GET /api/chat/sessions` lists `m32-vm-chat`. |
| 7 | Close the window with its title-bar close button (QMP pointer). Before closing, record the window's outer size. Timed captures: screendump at about 0.5 s, 2 s and 5 s after the click, then once at 3 s of idle. Read the window state and `/api/live`. | The window is gone from the screen. The process is still running (`/api/live` 200), and the state reads `visible: false`. Debian (no tray): a desktop notification titled "GleepGlorp AI is still running" appears in one of the timed captures, says how to bring it back and how to quit, and is not cut off (judged on the capture where it is fully visible: the whole title and every line of the body are readable and none ends in an ellipsis or is clipped by the banner's edge; a truncated notice is a fail, as the HAT found). Ubuntu (tray): the tray icon is in the top bar. |
| 8 | Launch the entry from the app grid again. Wait 10 s. Screendump. Read the window state. | The same window is back and raised (not a "ready" notification), with `visible: true`. One process, one listener. The window's outer size equals the size recorded in step 7 (the size is remembered across the hide and relaunch). |
| 9 | Close the window again (hidden on Debian, in the tray on Ubuntu; still running). Install package N+1 the way the Linux guide says, without quitting N. **ubuntu-deb:** App Center cannot upgrade a local `.deb` (operator decision, 2026-10-24), so open a terminal (QMP: Super, type `terminal`, Enter) and run the guide's one-line upgrade, `sudo apt install ./Downloads/<N+1 .deb>`, typing the password. **debian-deb:** double-click the N+1 `.deb` in Files, then Install in GNOME Software, with the polkit password. **AppImage variants:** make the N+1 file executable and double-click it; that is itself the N+1 launch, and the menu entry points at N+1 after it. Then launch the N+1 entry from the app grid (`.deb` variants). Wait 30 s. Read the version and the seeded data. | The old instance has exited, and N+1 is running in its own window: the version reads N+1. `m32-vm-agent`, `m32-vm-chat` and `m32-vm-provider` (with its stored key) are still listed, and the credential prefix is unchanged. Closing and relaunching restores the window at the same size (record the outer size before closing and compare after relaunch). Exactly one app process and one listener (for an AppImage, the process runs under the AppImage runtime, so count the app by its AppImage path and treat the runtime parent as part of the same one process). The menu shows one entry per package. |
| 10 | Quit. Debian: right-click the app-grid icon and choose "Quit GleepGlorp AI". Ubuntu: the tray menu's Quit. Wait 10 s. | The window is gone, `/api/live` no longer answers, and no app process remains. |
| 11 | Uninstall the way the guide says. **ubuntu-deb:** in a terminal, `sudo apt remove gleepglorp-ai` (App Center cannot remove a local `.deb`). **debian-deb:** open the package's page in GNOME Software (from the installed `.deb`) and choose the trash/Uninstall button, with polkit. **AppImage variants:** delete both AppImage files in Files. Log out and back in (QMP). Search the app grid. List `~/.local/share/the-one`. | No GleepGlorp entry for the removed package is shown. For an AppImage, the `.desktop` entry may still be on disk after the file is deleted: it passes if it is hidden from the menu (the entry's `TryExec` points at the deleted file, so GNOME hides it), so judge what the app grid shows, not the file listing. The data dir is still present, with `api-credential` and `the-one.db`. |

## Out of Scope
- Upgrading or removing a local `.deb` through Ubuntu's App Center: it cannot, which is a known App Center limit (Flight 2 leg 6; the operator's decision on 2026-10-24 documents the `apt` commands instead).
- macOS and Windows (Flights 3 and 4).
- Release publishing (Flight 4).
- WebKit rendering fidelity beyond "the start page rendered".
- X11 sessions: both distros' defaults are Wayland. Window position memory is X11-only (flight DD7), so position is not asserted here.

## Variants
| variant | distro | package |
|---|---|---|
| ubuntu-deb | Ubuntu 26.04 | `.deb` |
| ubuntu-appimage | Ubuntu 26.04 | AppImage |
| debian-deb | Debian 13 | `.deb` |
| debian-appimage | Debian 13 | AppImage |
