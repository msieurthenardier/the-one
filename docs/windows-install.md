# Installing GleepGlorp AI on Windows

This guide walks you through downloading and installing GleepGlorp AI on Windows,
getting past the unsigned-app warning, and using the app for the first time.

---

## 1. Download the installer

Download the latest `the-one-setup-<version>.exe` installer from the project's
releases page (or the link you were given). Save it anywhere — your Downloads folder
is fine.

---

## 2. Get past the SmartScreen warning

Because the installer is **not yet code-signed**, Windows Defender SmartScreen will
show a blue dialog the first time you double-click it:

> **"Windows protected your PC"**

This is expected — it is not a malware detection, just Windows flagging an app from
an unknown publisher. To proceed:

1. Click **More info** (the link near the bottom of the dialog).
2. Click **Run anyway**.

---

## 3. Install the app

The installer will launch the setup wizard.

- **UAC prompt**: because the app installs into `Program Files`, Windows will ask for
  administrator permission. Click **Yes** to allow it.
- **Install location**: the app installs to `C:\Program Files\GleepGlorp AI\`.
- **Desktop shortcut** (optional): the wizard offers a "Create a Desktop shortcut"
  checkbox. Tick it if you want a shortcut on your desktop in addition to the
  Start-menu entry.
- Click through the wizard and then **Finish**. You can optionally tick "Launch
  GleepGlorp AI" on the final screen to open the app immediately.

---

## 4. Launch the app

Open GleepGlorp AI from the **Start menu** (search for "GleepGlorp AI") or from the
desktop shortcut if you created one. This runs the windowed launcher
(`the-one-app.exe`) — it opens a native desktop window backed by Edge WebView2, which
ships with Windows 10 and later. No extra browser or download is needed.

A small **splash screen** appears while the app starts up. It disappears
automatically once the main window has loaded.

---

## 5. Close-to-tray behaviour

GleepGlorp AI is designed to run in the background. When you click the **X** button
to close the window:

- The window hides — the app **keeps running** in the system tray.
- The first time this happens you will see a notification:

  > **"GleepGlorp AI is still running in the system tray — Quit from the tray menu to exit"**

- To bring the window back, click the GleepGlorp AI icon in the system tray and
  choose **Show**.
- To fully exit the app, click the tray icon and choose **Quit**.

> **Tip:** If the notification does not appear (for example, Focus Assist or
> Windows notification settings are blocking it), the app is still running — look
> for the GleepGlorp AI icon in the system tray near the clock.

---

## Using the command-line interface (CLI)

The installer also ships a CLI tool: **`the-one.exe`** in
`C:\Program Files\GleepGlorp AI\`. There is no Start-menu shortcut for it — to use
it, open a Command Prompt or PowerShell, change to the install directory, and run it
from there (or add the directory to your `PATH`).

```powershell
cd "C:\Program Files\GleepGlorp AI"

.\the-one.exe chat       # interactive AI chat in the terminal
.\the-one.exe serve      # start the web UI at http://localhost:8484
.\the-one.exe version    # show the installed version
.\the-one.exe doctor     # run a self-diagnostic (see Troubleshooting below)
```

> **Note:** The Start-menu shortcut runs `the-one-app.exe` directly — that is the
> normal way to open the desktop window. `the-one.exe app` also opens the window but
> shows a console window alongside it; use the shortcut instead for everyday use.

---

## Troubleshooting / advanced

### Where is my data stored?

GleepGlorp AI stores its database, agent configuration, and settings in:

```
%LOCALAPPDATA%\the-one
```

On a default Windows installation that resolves to something like
`C:\Users\YourName\AppData\Local\the-one`.

**Migrating from an older install**: if you previously used a version that stored data
in `~\.the-one` (i.e. `%USERPROFILE%\.the-one`), the app will automatically migrate
that folder to the new location the first time it starts. Nothing is lost.

### Running the self-diagnostic

If something is not working — especially if AI tools that need external runtimes are
failing — run:

```powershell
cd "C:\Program Files\GleepGlorp AI"
.\the-one.exe doctor
```

`doctor` checks that the app can spawn child processes correctly, resolve a Python
interpreter, load the desktop shell, import every LLM provider, resolve the bundled
model catalog, load both bundled vector stores, confirm FTS5 support, load the
bundled embedding model (offline, from inside the installed app — it never
downloads), and find any external runtimes on your `PATH`. It prints `PASS` or
`FAIL` for each check and exits non-zero if anything is wrong.

### MCP tools needing `node` or `uv`

`node` (Node.js) and `uv` (Python package manager) are **not bundled** with the
installer — they are external runtimes that some MCP tool servers require. If an MCP
tool server fails to start, install the runtime it needs and then run
`the-one.exe doctor` to confirm the app can find it.

### Uninstalling

Go to **Settings → Apps** (or **Control Panel → Programs → Programs and Features**),
find **GleepGlorp AI** in the list, and click **Uninstall**. The uninstaller removes
the application files and shortcuts. Your data in `%LOCALAPPDATA%\the-one` is not
removed automatically — delete that folder manually if you want a clean slate.
