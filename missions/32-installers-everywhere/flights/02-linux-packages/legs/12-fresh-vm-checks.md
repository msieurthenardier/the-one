# Leg: fresh-vm-checks

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Close the flight's verification and documentation:
- the `linux-package-install` behavior test passes on all four variants (Ubuntu and Debian × `.deb` and AppImage) in fresh VMs, with its run log committed;
- the Linux install guide and the packaging documentation reflect what the VMs showed.

## Context
- **Flight DDs:** DD4, DD5, DD7, DD9, DD11, DD13, DD14.
- **The operator's decisions of 2026-10-24:**
  - Ubuntu `.deb` upgrade and removal are documented with `apt`, and the AppImage is recommended first to Ubuntu users who want no terminal;
  - the cosmetic polish is in leg 11.
- **What the earlier legs established:**
  - **Leg 6:** every lifecycle row passed on real GNOME. Ubuntu's App Center can't upgrade or remove a local `.deb`. GNOME Software can do both on Debian, but doesn't list the package.
  - **Leg 4:** install facts. FUSE works with `fusermount3`, and no `libfuse2` is needed.
  - **Leg 7:** the AppImage's menu-entry files.
  - **Leg 5:** `the-one quit [--wait]`, and the takeover.
  - **Leg 2:** the `doctor` `sandbox:`/`tray:` lines.
- **The behavior test is updated to the decisions** (`tests/behavior/linux-package-install.md`, status `active`): step 9 upgrades `ubuntu-deb` through the guide's `apt` command, and step 11 removes it the same way. The notice wording follows leg 11.

## Two parts, done in this order

### Part A — documentation (a Developer spawn; can run beside leg 11, disjoint files)
- **`docs/linux-install.md`** (new), modelled on `docs/windows-install.md`'s structure and tone:
  - **Which download:** the AppImage (works anywhere; no terminal for anything; recommended on Ubuntu) or the `.deb` (system package; Debian's Software app installs, upgrades and removes it; on Ubuntu, App Center installs it but cannot upgrade or remove it).
  - **Install:**
    - `.deb`: double-click, then Install, then the password;
    - AppImage: Files → Properties → "Executable as Program", then double-click; on first launch it adds "GleepGlorp AI (AppImage)" to the menu.
  - **First launch:** the window. With a tray (Ubuntu), closing goes to the tray. With no tray (stock Debian GNOME), closing hides the window, a one-time notice explains, and launching again brings it back. Quit with right-click → "Quit GleepGlorp AI", or `the-one quit`.
  - **WebKitGTK missing** (rare on a desktop): the app opens in the browser and a notice says what to install.
  - **Upgrade:**
    - AppImage: download the new file and launch it; the old file can be deleted.
    - `.deb` on Debian: double-click the new file, then Install.
    - `.deb` on Ubuntu: `sudo apt install ./gleepglorp-ai_<version>_amd64.deb`.
    - A running older version is replaced automatically when the new one launches. One exception: an instance older than this release is brought to the front instead, and a restart finishes the upgrade.
  - **Remove:**
    - AppImage: delete the file, plus `~/.local/share/applications/gleepglorp-ai-appimage.desktop` and `~/.local/share/icons/hicolor/512x512/apps/gleepglorp-ai-appimage.png` for an immediate clean-up (otherwise the menu entry disappears at the next login).
    - `.deb` on Debian: Software, then the package's page, then Uninstall.
    - `.deb` on Ubuntu: `sudo apt remove gleepglorp-ai`.
  - **Where your data lives:** `~/.local/share/the-one` (with `$XDG_DATA_HOME`). Never removed by an uninstall. How to remove it, and what is in it.
  - **Both installed:** they share the data, the port and the credential, so they are one app.
  - **Window size and position:** size is remembered. Position is remembered on X11 only, since Wayland gives apps no position (DD7).
  - **Checking it works:** `the-one doctor` (`.deb`) or `./GleepGlorp_AI-<v>-x86_64.AppImage doctor`, with what the `sandbox:` and `tray:` lines mean (bubblewrap, or the passthrough reason; indicator or none).
  - **Supported:** Ubuntu 26.04 LTS and Debian 13, x86-64, GNOME. Others may work; untested.
  - **Troubleshooting:**
    - the AppImage needs `fusermount3` (present on both); otherwise run it with `--appimage-extract-and-run`;
    - a hidden window: launch it again.
  - Then cross-links: `docs/windows-install.md` and README.
- **README "Install":** a Linux subsection pointing at `docs/linux-install.md`, beside the Windows one. The source-install instructions, including the `gir1.2-webkit2-4.1` `apt` step, stay as they are, for source installs only.
- **`CLAUDE.md`:** a short additive "Linux packaging (M32 F2)" paragraph next to "Windows packaging (M15 F5)". It covers:
  - `packaging/linux/` (`build.sh`, the pinned container, `product.toml` + `render.py`);
  - the AppImage fallback;
  - the audit;
  - `packaging/linux/checks/` (`gates.sh`, `gtk-smoke.sh`);
  - `packaging/linux/vm/` (the fresh-VM apparatus, and its safety rules);
  - `.github/workflows/linux-packages.yml` (dispatch-only);
  - pointers to `docs/linux-install.md` and `the_one/agents.md`.

  The file is shared with Mission 31, so this edit is additive and in its own paragraph. Also add the new routes and command (`GET /api/window/state`, `POST /api/window/quit`, `the-one quit`) to the Desktop launcher paragraph in one sentence, if leg 5 did not already.
- **`the_one/agents.md`:** an additive "Linux packaging" section, the deep reference:
  - the build flow;
  - the runtime hook and the fallback (host-first soname preload; never `LD_LIBRARY_PATH`; the dropped stock hooks);
  - the tray decision and the three close states;
  - the GTK traps (DD12) and their fixes;
  - the window routes and `the-one quit`;
  - the takeover (`_pid_alive`; never `os.kill` on Windows);
  - AppRun self-integration and its escaping;
  - the checks, the audit, the VM apparatus;
  - the hosted workflow.

  Also extend the Desktop launcher section only where it now differs.
- **Checks:** `make test-unit` (12 skips); `ruff`; any doc tests (for example `tests/test_*claude*`/`test_*agents_md*`, if present: grep first). Only docs change.

### Part B — the behavior test (the Flight Director runs `/mission-control:behavior-test linux-package-install` after leg 11 lands)
- **Packages:** a fresh N/N+1 pair built from the committed tree after leg 11 (`0.11.9.dev20`/`0.11.9.dev21`), with their sha256s recorded.
- **All four variants**, one guest at a time, fresh overlays. The run log lands at `tests/behavior/linux-package-install/runs/<timestamp>.md` and is committed. Evidence stays outside the repo.
- **Leg 11's AC4 is recorded here:** whether App Center shows the brand icon and a publisher.
- **A failing step** is an unmet criterion: the leg does not land while it fails, unless the operator accepts it as a known issue, with that disposition recorded.

## Acceptance Criteria
- [x] **AC1** — Part A's documents exist as specified; the Linux guide covers every bullet. `make test-unit` passes and `ruff` is clean.
- [x] **AC2** — `/mission-control:behavior-test linux-package-install` passes on all four variants, or each failure has an operator disposition. The run log is committed.
- [x] **AC3** — leg 11's App Center icon and publisher outcome is recorded.
- [x] **AC4** — the guide's commands and paths are the ones the behavior test exercised (the `apt` lines, the AppImage clean-up paths, `the-one quit`). A cross-check of the run log against the guide is noted in the flight log.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
