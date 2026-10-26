# Installing GleepGlorp AI on macOS

This guide walks you through downloading and installing GleepGlorp AI on a Mac, getting past
Gatekeeper's first-launch warning, opening the app, and upgrading or removing it later.

**Supported:** Apple Silicon Macs (M1 and later) on **macOS 14 (Sonoma) or later**. Intel Macs
and earlier macOS versions are not supported. The app is **not notarized** (it has no Apple
Developer ID), so macOS asks you to approve it once (section 3).

**What has been checked.** The build, the bundle, the install-by-copy, close-to-Dock, reopen,
quit, upgrade and remove steps were exercised by script on a hosted macOS 15.7 (Apple Silicon)
machine. The Gatekeeper approval screens and real clicks on the Dock icon can only be seen by a
person at a real Mac; those parts of this guide describe macOS 15 as observed on the first
refused launch plus Apple's documented path, and have not yet been walked through end to end on
a personal Mac. If your screens differ, the contributor check
([macos-contributor-check.md](macos-contributor-check.md)) is how to report it.

---

## 1. Which download?

On the project's releases page, download **`GleepGlorp_AI-<version>-arm64.dmg`**. There is one
file; you do not need anything else. No Python and no Terminal are needed to use the app.

---

## 2. Install

1. Open the downloaded `.dmg` (double-click it). A window opens showing **GleepGlorp AI** and an
   **Applications** shortcut.
2. Drag **GleepGlorp AI** onto **Applications**.
3. Eject the disk image (the eject button next to it in the Finder sidebar) and delete the `.dmg`
   if you like.

Do not run the app from inside the disk image or from your Downloads folder; copy it to
Applications first. (macOS runs a freshly downloaded app from a temporary, read-only copy until
it is moved, which causes odd behaviour.)

---

## 3. Get past Gatekeeper (first launch only)

The first time you open the app from Applications, macOS refuses it:

> **"GleepGlorp AI" Not Opened**
> Apple could not verify "GleepGlorp AI" is free of malware that may harm your Mac or
> compromise your privacy.

On macOS 15 the dialog has only **Done** and **Move to Trash**; there is no Open button. Click
**Done** (not Move to Trash), then:

1. Open **System Settings** › **Privacy & Security**.
2. Scroll down to the **Security** section. A line says that "GleepGlorp AI" was blocked to
   protect your Mac. Click **Open Anyway**.
3. Enter your password or use Touch ID when asked.
4. In the dialog that follows, click **Open** (or **Open Anyway**).

The app now opens, and macOS remembers your decision for that copy; later launches should not ask
again (Apple's documented behaviour, not yet confirmed on a real Mac). A newly downloaded version
is a new download to macOS and may ask once more. (Apple says the **Open Anyway** button stays
available for about an hour after the refused launch. If it is missing, open the app once more
from Applications, click **Done**, and look again.)

**macOS versions.** The steps above are for macOS 15 (Sequoia), where the dialog was observed on
15.7. macOS 14 (Sonoma) offers the same Privacy & Security route; it may also show an **Open**
button in the first dialog, or let you Control-click the app and choose **Open**. The macOS 14
screens have not been checked.

**Advanced fallback (Terminal).** **Open Anyway** is the preferred route. If it does not work,
`xattr -dr com.apple.quarantine "/Applications/GleepGlorp AI.app"` removes the download mark and
skips Gatekeeper's check entirely, so macOS no longer vets the app at all. Use it only on a
`.dmg` you downloaded from the project's official releases page.

---

## 4. First launch

Open **GleepGlorp AI** from Applications (or Launchpad, or Spotlight). A small splash appears,
then the app window within a few seconds, showing the Chats start page. If you have not used it
before, the app walks you through adding a model provider. The window is the system's own web
view (WebKit); no extra browser is involved.

### What closing the window does

GleepGlorp AI keeps running in the Dock when you close its window, so your agents and connectors
stay available. There is no menu-bar icon.

- **Close** (the red button, or **Cmd-W**) hides the window. The Dock icon stays, with its
  running dot. (The hosted macOS runner observed both the close button and Cmd-W hiding the
  window.)
- **Click the Dock icon** to bring the window back. (Opening the app from Applications or
  Spotlight again does the same; no second copy starts.)
- **Quit** to really exit: **Cmd-Q**, **GleepGlorp AI › Quit** in the menu bar, or right-click
  the Dock icon and choose **Quit**. Quitting waits a moment while the app shuts its server down
  cleanly, then exits. (The runner drove Cmd-Q, the menu and the quit request; Dock **Quit**
  sends the same request but has not yet been confirmed on a real Mac, which the contributor check
  does.)
- Logging out or restarting the Mac also quits it; the app is built to shut down cleanly then,
  but that path has not been exercised on a real Mac yet.

The window's size and position are remembered between launches.

---

## 5. Upgrade

**Quit GleepGlorp AI first** (Cmd-Q), then drag the new version onto Applications and choose
**Replace** when Finder asks. Your chats, agents and settings carry over.

Do not replace the app while it is running. The running copy reads parts of itself from the
bundle as it goes, and when the bundle is swapped underneath it, it can crash. The data is not
touched, but the new version does not take effect until you quit and start it again. If this
happens, quit (or force quit) and open the app again.

---

## 6. Remove

Quit the app, then drag **GleepGlorp AI** from Applications to the Trash.

Removing the app never removes your data (next section).

---

## 7. Where your data and logs live

GleepGlorp AI stores its database, agent configuration, settings, credentials and
knowledge-base indexes in:

```
~/Library/Application Support/the-one/
```

(In Finder: **Go › Go to Folder…**, paste the path.) An uninstall never touches it, and an
upgrade keeps using it. To start completely fresh, quit the app and move that folder to the
Trash. That removes your chats, agents, provider settings and stored keys for good, so copy it
somewhere first if you might want them back.

The app's log is:

```
~/Library/Logs/GleepGlorp AI/app.log
```

Open it with the **Console** app (File › Open) or in Terminal with
`tail -n 50 ~/Library/Logs/GleepGlorp\ AI/app.log`. It is trimmed at launch once it passes 10 MB.
When you report a problem, attach the end of this file.

---

## 8. The command line, and checking that it works

The Terminal command is inside the app, so type its full path (quote it, because of the space):

```bash
"/Applications/GleepGlorp AI.app/Contents/MacOS/the-one" doctor
```

To type less, add an alias to your shell profile:
`alias the-one='"/Applications/GleepGlorp AI.app/Contents/MacOS/the-one"'`.

`doctor` runs a self-diagnostic and prints `OK` or `FAIL` for each check, ending with
`RESULT: PASS` or `RESULT: FAIL`. It exits non-zero if anything is wrong. It ends with
informational lines that never fail the run:

- **`sandbox:`** says shell and Python tool calls run without isolation on macOS
  (`passthrough`).
- **`tray: dock`** says the app lives in the Dock, as in section 4.
- **`path:`** says where the app got its program search path for tools it starts.
  `login shell` is the normal answer: the app asked your login shell for its `PATH` once at
  start, so tools such as `node`, `npx`, `uv` or Homebrew programs are found as in Terminal.
  `static fallback` means that lookup failed or timed out and the app used a built-in list of
  common locations instead; the line gives the reason.

Other useful commands, with the same prefix: `the-one version`, and `the-one quit --wait` (asks
the running app to quit and waits until it has).

### Do I need Python?

Not to use the app. A few features run Python on your behalf (Python tools, and some MCP tool
servers), and those need a Python 3 installed on the Mac. The `doctor` line `python interpreter:`
says which one the app found. macOS's own `/usr/bin/python3` is only a stub that asks to install
the Command Line Tools, so the app does not use it. If `doctor` reports `FAIL` on the Python
interpreter, install Python 3 from [python.org](https://www.python.org/downloads/macos/) or with
Homebrew (`brew install python`), then run `doctor` again. You can also point the app at a
specific interpreter with the `THE_ONE_PYTHON` environment variable.

---

## 9. Troubleshooting

- **"Not Opened" and no Open button.** That is the first-launch warning; follow section 3.
- **I closed the window and it is gone.** The app is still running in the Dock. Click the Dock
  icon.
- **The app crashed or "quit unexpectedly" after I replaced it.** You replaced it while it ran
  (section 5). Open it again; your data is intact.
- **The window is blank for a moment.** A launch takes a few seconds; the splash and then the
  app appear. If it stays blank for more than about ten seconds, check the log (section 7).
- **MCP tools needing `node` or `uv`.** These are not bundled; install the runtime a tool server
  needs, then run `doctor` to confirm the app can find it (the `runtimes` lines).
- **Something else is wrong.** Run `doctor` (section 8) and read the `FAIL` lines, and look at
  the log.

---

See also the [Linux guide](linux-install.md), the [Windows guide](windows-install.md), the
[contributor check](macos-contributor-check.md) and the [README](../README.md).
