# Leg: windows-install-guide

**Status**: completed
**Flight**: [Windows install docs & mission closeout](../flight.md)

## Objective

Author `docs/windows-install.md` — an end-user guide that walks a non-technical Windows user from
downloading the installer through a running app, including the unsigned-app SmartScreen
click-through — and link it from the README so it's discoverable.

## Context

- **Mission criterion** (primary): "Installation and first-run steps — including how to get past
  unsigned-app OS warnings — are documented." Windows-only (DD4).
- **DD3**: this is a NEW end-user doc at `docs/windows-install.md`, distinct from the developer
  build-contract `packaging/windows/README.md`. `docs/` already exists and the README links into it.
- **Shipped reality this guide must describe accurately (verified at planning):**
  - **Installer**: Inno Setup `.exe` (`the-one-setup-<ver>.exe`), unsigned → Windows **SmartScreen**
    "Windows protected your PC / unknown publisher" on first run; passthrough is **More info → Run
    anyway**. App name **GleepGlorp AI**; installs to `C:\Program Files\GleepGlorp AI\`
    (`{autopf}\GleepGlorp AI`); stable AppId → upgrades in place, uninstall via Add/Remove Programs.
  - **Two executables** (`packaging/windows/the-one.iss`): the **Start-menu shortcut → `the-one-app.exe`**
    (windowed, no console — it hard-forces the `app` command, `frozen_entry_gui.py:31`). The **CLI is
    the separate `the-one.exe`** in the install dir, with **no shortcut** — run from
    `C:\Program Files\GleepGlorp AI\` for `the-one.exe chat | serve | version | doctor` (surface from
    `the_one/main.py`). `the-one.exe app` *exists* but opens a console window — the **shortcut**, not
    the CLI, is the normal way to launch the window; describe `app` as secondary in the CLI section.
  - **Install needs elevation**: `.iss` sets `PrivilegesRequired=admin` + `{autopf}` → a **UAC prompt**
    appears during install (machine-wide Program Files). An optional "create a desktop shortcut"
    checkbox is offered (`[Tasks] desktopicon`).
  - **First launch**: opens the native window (Edge WebView2); the app runs **close-to-tray** — the
    window X hides to the system tray (a one-time first-run notice explains it), Quit is from the
    tray menu (`the_one/interfaces/desktop/`).
  - **Data location**: `%LOCALAPPDATA%\the-one` (`platformdirs.user_data_dir("the-one",
    appauthor=False)`, roaming=False — NOT `%APPDATA%`). An existing `~/.the-one` (`%USERPROFILE%\.the-one`)
    is **migrated**, not orphaned (`config.py::_maybe_migrate_legacy`).
  - **MCP runtimes**: `node`/`uv` are not bundled; if missing, the app gives non-Docker guidance.
    The user self-check is **`the-one.exe doctor`** (diagnoses the spawn seam + runtime presence).
- **No code changes in this leg** — pure doc authoring. (Any code-message inaccuracies discovered,
  e.g. the `config.py` `%APPDATA%` docstring, are fixed in Leg 2, not here.)

## Inputs

- A working, operator-validated Windows installer (F8 MinIO artifact).
- `packaging/windows/the-one.iss`, `the_one/main.py`, `the_one/config.py`,
  `the_one/interfaces/desktop/` — sources of ground truth for the guide's claims.

## Outputs

- `docs/windows-install.md` — the end-user guide.
- `README.md` — a link to the guide from the Quickstart (the deeper README/Docker pass is Leg 2/DD5).

## Acceptance Criteria

- [x] `docs/windows-install.md` exists and walks the user through, in order: **download** the
      installer → **SmartScreen** passthrough (More info → Run anyway, with a one-line "why: the app
      is unsigned this release") → install (a **UAC admin prompt** appears — click Yes; installs to
      Program Files\GleepGlorp AI, Start-menu entry, optional desktop-shortcut checkbox) →
      **first launch** of the windowed app → the **close-to-tray / background-run** behavior (the
      window's X hides to the system tray; the tray menu's **Show** restores the window, **Quit**
      exits; a one-time tray notice explains it — quote the shipped text from `shell.py`).
- [x] The guide documents the **CLI** correctly: it is `the-one.exe` in
      `C:\Program Files\GleepGlorp AI\` (no Start-menu shortcut), commands
      `chat | serve | version | doctor` (with `app` mentioned as secondary — the shortcut is the
      normal window launch), with an example invocation.
- [x] The guide states the **data location** as `%LOCALAPPDATA%\the-one` and notes an existing
      `~/.the-one` / `%USERPROFILE%\.the-one` is migrated automatically.
- [x] The guide points users at **`the-one.exe doctor`** as the self-diagnostic when MCP tools that
      need `node`/`uv` don't work, and notes those runtimes aren't bundled.
- [x] The guide covers **uninstall** (Add/Remove Programs → "GleepGlorp AI").
- [x] `README.md` links to `docs/windows-install.md` from the Quickstart (or an Install section).
- [x] Every factual claim matches the real `.iss` / `main.py` / `config.py` / desktop code — no
      invented paths, command names, or behaviors.

## Verification Steps

- Render-read `docs/windows-install.md`: the steps are correct and in a sensible order; the SmartScreen
  click-through is explicit; the CLI path + commands match `main.py`'s usage string; the data path is
  `%LOCALAPPDATA%\the-one`.
- `grep` the README for the new link; confirm it resolves to `docs/windows-install.md`.
- Cross-check each claim against its source file (cite them in the leg progress entry).

## Implementation Guidance

1. Read the ground-truth sources before writing: `packaging/windows/the-one.iss` (shortcut, exes,
   install dir, AppName, uninstall, `[Tasks] desktopicon`, `PrivilegesRequired=admin`),
   `the_one/main.py` (CLI command surface + usage text), `the_one/config.py` (data dir +
   `_maybe_migrate_legacy`), `the_one/interfaces/desktop/shell.py` (the `_close_to_tray` first-run
   notice — quote its exact string) + `desktop/tray.py` (the **Show** + **Quit** menu items), and
   `packaging/windows/README.md` for SmartScreen phrasing. **WARNING:** that README's "Output"
   section + its "shortcut invokes `the-one.exe app`" note are **stale (pre-F5 single-exe model)** —
   the authoritative exe/shortcut model is the `.iss` `[Icons]` block + `the-one.spec` (two exes:
   `the-one-app.exe` shortcut, `the-one.exe` CLI). Do not copy the stale prose. *(Leg 2 fixes that
   stale dev README — see the flight log.)*
2. Write `docs/windows-install.md` for a non-technical reader: short numbered steps, the SmartScreen
   screenshot-free but precise ("click **More info**, then **Run anyway**"), a clear separation
   between the **windowed app** (Start-menu) and the **CLI** (`the-one.exe` in the install dir).
3. Add a "Troubleshooting / advanced" tail: data location + migration, `the-one.exe doctor`,
   MCP-runtime (`node`/`uv`) note, uninstall, and a one-liner that if the close-to-tray notification
   doesn't appear (Focus Assist / notifications off), the app is still running — look for the
   GleepGlorp AI icon in the system tray.
4. Link it from the README Quickstart with a one-liner ("**Install on Windows:** see
   [docs/windows-install.md](docs/windows-install.md)"). Keep the broader README restructure (DD5
   Docker-path demotion) for Leg 2.

## Edge Cases

- **Don't document the `~/.docker` path or any Docker step** — there is no Docker in the Windows
  install path.
- **Don't claim signing/notarization** — the installer is unsigned this mission (SmartScreen is
  expected, by design).
- **`the-one app` vs the shortcut** — the Start-menu shortcut runs `the-one-app.exe` directly; `the-one.exe app`
  is the CLI-invoked equivalent. Describe the shortcut as the normal path; mention `the-one.exe app`
  only in the CLI section.
- **Data path nuance** — say `%LOCALAPPDATA%\the-one`; do NOT copy the (wrong) `%APPDATA%` from the
  `config.py` docstring (that bug is fixed in Leg 2).

## Files Affected

- `docs/windows-install.md` — new.
- `README.md` — add the install-guide link.
- `missions/.../flight-log.md` — leg progress entry.

---

## Post-Completion Checklist

- [x] `docs/windows-install.md` authored, accurate against the real installer/code, linked from README
- [x] Flight log updated with the leg progress entry (cite source files for the key claims)
- [x] Set this leg's status to `landed` (commit deferred to end-of-flight batch)
