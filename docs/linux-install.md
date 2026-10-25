# Installing GleepGlorp AI on Linux

This guide walks you through downloading and installing GleepGlorp AI on Linux, opening
it for the first time, and upgrading or removing it later.

**Supported:** Ubuntu 26.04 LTS and Debian 13, 64-bit Intel/AMD (x86-64), with the GNOME
desktop. Other distributions and desktops may work; they are untested.

---

## 1. Which download?

There are two files on the project's releases page. Pick one; you do not need both.

- **`GleepGlorp_AI-<version>-x86_64.AppImage`** works on any supported desktop, needs no
  terminal for anything, and leaves your system packages alone. **If you are on Ubuntu and
  want to avoid the terminal, choose this one.**
- **`gleepglorp-ai_<version>_amd64.deb`** is a normal system package. On Debian, the
  Software app installs, upgrades and removes it. On Ubuntu, App Center installs it, but
  cannot upgrade or remove it; those two steps use a one-line terminal command (see
  sections 5 and 6).

---

## 2. Install

### The `.deb`

1. Double-click the downloaded `.deb` file. Your software app opens.
2. Click **Install** and enter your password when asked.

The app appears in your application menu as **GleepGlorp AI**.

### The AppImage

1. Open **Files**, right-click the downloaded `.AppImage` file and choose **Properties**.
2. Tick **Executable as Program** (the wording varies slightly between versions), then close
   the dialog.
3. Double-click the file.

The first time it runs, it adds **GleepGlorp AI (AppImage)** to your application menu, so you
can start it from there afterwards. The file can stay wherever you saved it; if you move it,
launch it once from its new place and the menu entry follows.

---

## 3. First launch

Open **GleepGlorp AI** from the application menu. A native window opens on the desktop's own
web engine (WebKitGTK); no extra browser is involved. If you have not used it before, the app
walks you through adding a model provider.

### What closing the window does

GleepGlorp AI keeps running in the background when you close its window, so your agents and
connectors stay available. What you see depends on whether your desktop has a system tray:

- **With a tray (Ubuntu's default desktop):** closing hides the window to the tray. Click the
  tray icon and choose **Show** to bring it back.
- **Without a tray (stock Debian GNOME):** closing hides the window, and a one-time
  notification explains that the app is still running. Launch GleepGlorp AI from the menu again
  and the hidden window comes back to the front; no second copy starts.

### Quitting

To really exit, use any of these:

- right-click the app's icon in the dock or the application menu and choose
  **Quit GleepGlorp AI**;
- choose **Quit** from the tray menu, if you have a tray;
- run `the-one quit` in a terminal (`.deb`), or
  `./GleepGlorp_AI-<version>-x86_64.AppImage quit` (AppImage). Add `--wait` to have the command
  wait until the app has exited.
  `quit` reaches the app on its configured port (8484 unless you changed it); an instance that
  had to start on another port because that one was taken cannot be quit this way, so use the
  dock or tray instead.

### If WebKitGTK is missing

This is rare on a desktop. If the web engine is not installed, the app opens in your regular
browser instead and shows a notice naming the package to install for its own window. The
`.deb` pulls in what it needs; the AppImage uses the desktop's own copy.

---

## 4. Window size and position

The window's size is remembered between launches. Its position is remembered only on X11
sessions: on Wayland, which is the default on both supported systems, desktop apps are not
allowed to place themselves, so the desktop chooses where the window opens.

---

## 5. Upgrade

A running older version is replaced automatically: when you launch the new version, it asks
the old one to quit and takes over. Your chats, agents and settings carry over.

One exception: if the running instance is older than the first Linux release, the new launch
brings that window to the front instead, and the upgrade finishes the next time you restart the
app.

- **AppImage:** download the new file and launch it. You can delete the old file afterwards.
- **`.deb` on Debian:** double-click the new `.deb` file and click **Install**.
- **`.deb` on Ubuntu:** in a terminal, from the folder holding the new file:

  ```bash
  sudo apt install ./gleepglorp-ai_<version>_amd64.deb
  ```

---

## 6. Remove

- **AppImage:** delete the `.AppImage` file. The menu entry disappears at your next login. To
  clean up at once, also delete these two files:

  ```
  ~/.local/share/applications/gleepglorp-ai-appimage.desktop
  ~/.local/share/icons/hicolor/512x512/apps/gleepglorp-ai-appimage.png
  ```

  (If you set `$XDG_DATA_HOME`, they are under that directory instead of `~/.local/share`.)
- **`.deb` on Debian:** open **Software**, go to the package's page and click **Uninstall**.
  (Software does not list the package under Installed or in search; open the package from the
  `.deb` file again, and its page offers the uninstall.)
- **`.deb` on Ubuntu:** in a terminal:

  ```bash
  sudo apt remove gleepglorp-ai
  ```

Removing the app never removes your data (next section).

---

## 7. Where your data lives

GleepGlorp AI stores its database, agent configuration, settings, credentials and knowledge-base
indexes in:

```
~/.local/share/the-one
```

or under `$XDG_DATA_HOME/the-one` if you have set that variable. An uninstall never touches it,
and an upgrade keeps using it. To start completely fresh, quit the app and delete that folder.
Deleting it removes your chats, agents, provider settings and stored keys for good, so copy it
somewhere first if you might want them back.

### Both installed

If you have both the `.deb` and an AppImage, they share the same data, the same port and the
same sign-in credential, so they behave as one app: launching either brings up the one running
copy, and the newer version replaces the older.

---

## 8. Checking that it works

`doctor` runs a self-diagnostic and prints `PASS` or `FAIL` for each check. It exits non-zero if
anything is wrong.

```bash
the-one doctor                                       # .deb
./GleepGlorp_AI-<version>-x86_64.AppImage doctor     # AppImage
```

It ends with two informational lines that never fail the run:

- **`sandbox:`** names the isolation used for shell and Python tool calls. `bubblewrap` is the
  normal answer; otherwise the line says why the app is running without it.
- **`tray:`** says how closing the window behaves. `indicator` (or `xembed`) means a tray icon
  is available. `none` means your desktop has no tray, and the line gives the reason; closing
  hides the window as described in section 3.

---

## 9. Troubleshooting

- **The AppImage does not start.** AppImages need `fusermount3`, which is present on Ubuntu 26.04
  and Debian 13. If your system lacks it, run the file with extraction instead of FUSE:

  ```bash
  ./GleepGlorp_AI-<version>-x86_64.AppImage --appimage-extract-and-run
  ```

- **I closed the window and it is gone.** The app is still running. Launch it again from the
  menu and the window returns.
- **Something else is wrong.** Run `doctor` (section 8) and read the `FAIL` lines.
- **MCP tools needing `node` or `uv`.** These are not bundled; install the runtime a tool server
  needs, then run `doctor` to confirm the app can find it.

---

See also the [Windows guide](windows-install.md) and the [README](../README.md).
