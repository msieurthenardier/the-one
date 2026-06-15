# Leg: inno-windows-installer

**Status**: completed
**Flight**: [Packaging & Installer — Windows](../flight.md)

## Objective

Author the checked-in **Inno Setup `.iss`** (DD6) that takes the Leg-2 PyInstaller
one-dir (`dist/the-one/`), installs it under Program Files, creates a Start-menu and
Desktop shortcut launching the **windowed** entry (`the-one.exe app`), ships the CLI
in the same bundle, provides a clean uninstaller, and documents the unsigned-app
Windows SmartScreen click-through — so `iscc the-one.iss` produces a double-click
`.exe` installer on `windows-2022`.

## Context

Leg 3 wraps Leg 2's frozen one-dir in a user-facing installer. Per DD6, Inno Setup is
chosen over NSIS/WiX (simplest scriptable path for "take the one-dir → Program Files →
shortcuts → uninstaller", no MSI/Group-Policy, no signing this round). The shortcut
invokes `the-one.exe app` (the Flight-4 windowed entry, DD3) — **not** bare `the-one`
(which drops to `chat`). The frozen bundle ships the CLI alongside via the **single
multi-call exe** pinned in Leg 2 (DD6): the same `the-one.exe` dispatches `app`, `chat`,
`serve`, `doctor`, `version` on argv.

**Build-host reality (same as Leg 2).** Inno Setup's `iscc` compiler is Windows-only;
this host is Linux/WSL2. The `.iss` is authored and **statically reviewed** here; the
**`iscc` build of the actual `.exe` installer is performed in CI on `windows-2022`**,
consolidated into Leg 4's packaged-smoke job (which already builds the one-dir the
installer consumes). Leg 3's local acceptance criteria are the reviewable ones (the
`.iss` is well-formed, references the right one-dir source + entry + icon, the
SmartScreen docs exist); the `iscc`-produces-`.exe` milestone is a **forward
dependency on Leg 4**, recorded explicitly (mirroring Leg 2's deferral).

## Inputs

What exists before this leg runs (post-Leg-2):

- `packaging/windows/the-one.spec` — emits a **one-dir** bundle at `dist/the-one/`
  with `the-one.exe` (single multi-call exe, `console=True`) + `_internal/` payload.
- `packaging/windows/frozen_entry.py`, `packaging/windows/README.md` — Leg 2 build
  recipe; the README documents `dist/the-one/the-one.exe` as the build output.
- `the_one/__init__.py:3` — `__version__ = "0.2.0"` (the version the installer names
  itself with; pyproject's `0.1.0` is stale and not used).
- `the_one/interfaces/web/static/brand/favicon.ico` — a real multi-size `.ico`
  (6977 bytes; 16/32/48). The only `.ico` in the repo — used for `SetupIconFile` and
  the shortcut icon.
- `the_one/main.py:cli_entry` — `app` branch launches the windowed entry; the
  shortcut passes `app` as the argument.
- No `packaging/windows/*.iss`, no `installer/` dir yet.

## Outputs

- `packaging/windows/the-one.iss` *(new)* — the Inno Setup script.
- `packaging/windows/installer-assets/the-one.ico` *(new, copied from the brand
  favicon.ico)* **or** an `.iss` reference straight to the brand `favicon.ico` — pick
  one stable source path (see guidance); the installer also installs the icon into
  `{app}` so the shortcut has a durable icon target.
- `packaging/windows/README.md` — extended with the installer build command
  (`iscc packaging/windows/the-one.iss`), the version-define override, and the
  **SmartScreen unsigned-app click-through** ("Windows protected your PC → More info →
  Run anyway").
- CLAUDE.md/README — one-line pointer already exists from Leg 2; extend only if needed.

## Acceptance Criteria

- [ ] `packaging/windows/the-one.iss` exists and is a well-formed Inno Setup script
      with `[Setup]`, `[Files]`, `[Icons]` sections (and `[Run]`/`[Tasks]` as needed).
- [ ] **Display-name / slug split (deliberate, call it out):** the product display
      name is **"GleepGlorp AI"** (matches `the-one.exe version` → `GleepGlorp AI
      v0.2.0`), used for `AppName`, the install dir, and the shortcut; the internal
      slug / exe name is **"the-one"** (`the-one.exe`, `the-one-setup-*.exe`). So the
      installer lands `the-one.exe` under `Program Files\GleepGlorp AI\` with a
      "GleepGlorp AI" shortcut — intentional, not a mismatch.
- [ ] `[Setup]` defines: a **stable `AppId` GUID** (so upgrades/uninstall track
      correctly across versions — hardcode one GUID, never regenerate it);
      `AppName`/`AppVerName` for "GleepGlorp AI"; `AppVersion` from a
      `#define AppVersion "0.2.0"` that is **overridable via `iscc
      /DAppVersion=x.y.z`** (so CI can inject `the_one.__version__`);
      `DefaultDirName={autopf}\GleepGlorp AI` (Program Files);
      `ArchitecturesAllowed=x64compatible` /
      `ArchitecturesInstallIn64BitMode=x64compatible` (the current Inno tokens,
      requiring Inno Setup **6.3+** — Leg 4's CI pins an Inno ≥6.3 so this is tested,
      not assumed; see the Leg-4 forward dependency);
      `OutputBaseFilename` including the version (e.g. `the-one-setup-{#AppVersion}`);
      `OutputDir=Output` (resolves to `packaging/windows/Output/` — relative to the
      `.iss`); `SetupIconFile` → the `.ico`; `UninstallDisplayIcon={app}\the-one.ico`
      (branded Add/Remove-Programs entry — the exe has no embedded icon resource since
      the Leg-2 `.spec` omits `EXE(icon=)`); `Compression=lzma2`/`SolidCompression=yes`.
      No signing directives (unsigned this round; a `SignTool` hook may be noted as a
      future conditional but must be inert).
- [ ] `[Files]` recursively sources the **entire Leg-2 one-dir** —
      `Source: "..\..\dist\the-one\*"; DestDir: "{app}"; Flags: recursesubdirs
      createallsubdirs` (path relative to the `.iss`) — so `the-one.exe` + `_internal/`
      land under `{app}`. The brand `.ico` is also installed into `{app}` for a durable
      shortcut icon.
- [ ] `[Icons]` creates a **Start-menu** shortcut and a **Desktop** shortcut (the
      Desktop one gated behind a standard `[Tasks]` `desktopicon` checkbox), both
      pointing at `{app}\the-one.exe` with `Parameters: "app"` and an `IconFilename`
      → the installed `.ico`. The shortcut name is "GleepGlorp AI".
- [ ] The CLI is reachable from the install (same `the-one.exe`); the `.iss` documents
      that `the-one.exe chat|serve|doctor` work from the install dir (no separate CLI
      shortcut required, but the exe is on disk under `{app}`).
- [ ] The uninstaller is the Inno default (no custom `[UninstallDelete]` needed beyond
      the install tree); a clean uninstall removes `{app}` and both shortcuts.
- [ ] `packaging/windows/README.md` documents the installer build
      (`iscc packaging/windows/the-one.iss`, optional `/DAppVersion=`), the
      `Output\the-one-setup-*.exe` artifact location, and the **SmartScreen
      unsigned-app workaround** verbatim enough for the F9 per-OS docs to inherit.
- [ ] `PrivilegesRequired` is set deliberately: default to `admin` (Program Files
      install) **or** `lowest` + `{autopf}` resolving to per-user — pick one and state
      the rationale (recommend `admin`/`PrivilegesRequired=admin` for a Program Files
      install; note the per-user alternative). Document the choice.
- [ ] **Forward dependency recorded (not a gate this leg):** the `iscc` build of the
      `.exe` installer runs in **Leg 4's CI** on `windows-2022` (after the one-dir is
      built), uploading the installer as an artifact. Leg 4's CI **installs Inno Setup
      ≥6.3 pinned** (e.g. `choco install innosetup --version=…`) so the
      `x64compatible` token compiles, and runs `iscc /DAppVersion=<the_one.__version__>
      packaging\windows\the-one.iss`, then uploads `packaging/windows/Output/
      the-one-setup-*.exe`. **Decision (Flight Director):** the flight.md Verification
      line parenthetically referenced "(Leg 5)" for the iscc build; this is consolidated
      into **Leg 4** (the CI leg already provisions `windows-2022` + builds the one-dir),
      recorded in the flight-log Decisions — flight.md body left as its planning
      snapshot, log is ground truth. Stated in the leg + flight log.

## Verification Steps

- Read `the-one.iss` and confirm each `[Setup]` directive above is present and
  correctly spelled; confirm the `[Files]` `Source` path resolves from the `.iss`
  location to `dist/the-one/` (`..\..\dist\the-one\*`).
- Confirm the `AppId` is a single hardcoded GUID and there is exactly one (grep).
- Confirm `[Icons]` entries pass `Parameters: "app"` (not bare).
- Confirm `#define AppVersion` has a default and is referenced as `{#AppVersion}`
  in `AppVersion`/`OutputBaseFilename`, and that `iscc /DAppVersion=` would override
  it (Inno semantics: `/D` overrides a later `#define`, so guard with
  `#ifndef AppVersion`).
- `iscc` is not available on this Linux host — **do not attempt to compile**; the
  build is Leg 4 CI. Note this in the run.
- Host-native unit suite remains green (this leg adds no Python runtime code; confirm
  no accidental edits to `the_one/`).

## Implementation Guidance

1. **Layout.** `packaging/windows/the-one.iss`. If copying the icon to a stable
   installer-asset path, use `packaging/windows/installer-assets/the-one.ico` (copy of
   `the_one/interfaces/web/static/brand/favicon.ico`); alternatively reference the
   brand `favicon.ico` directly via a relative path from the `.iss`. Prefer the
   **copied installer-asset** so the installer doesn't reach into the app's static
   tree and so a future icon swap is localized. Document whichever you choose.

2. **Version define (CI-injectable).**
   ```
   #ifndef AppVersion
     #define AppVersion "0.2.0"
   #endif
   ```
   CI runs `iscc /DAppVersion=$(python -c "import the_one; print(the_one.__version__)")
   packaging\windows\the-one.iss`. The `#ifndef` guard lets `/D` win.

3. **`[Setup]` essentials.**
   ```
   [Setup]
   AppId={{<STABLE-GUID>}}
   AppName=GleepGlorp AI
   AppVersion={#AppVersion}
   AppVerName=GleepGlorp AI {#AppVersion}
   DefaultDirName={autopf}\GleepGlorp AI
   DefaultGroupName=GleepGlorp AI
   UninstallDisplayIcon={app}\the-one.ico
   OutputBaseFilename=the-one-setup-{#AppVersion}
   OutputDir=Output
   SetupIconFile=installer-assets\the-one.ico
   Compression=lzma2
   SolidCompression=yes
   ArchitecturesAllowed=x64compatible
   ArchitecturesInstallIn64BitMode=x64compatible
   PrivilegesRequired=admin
   WizardStyle=modern
   ```
   Generate the GUID once (any UUID) and **freeze it** — it's the upgrade/uninstall
   identity. `x64compatible` requires Inno **6.3+**; Leg 4's CI pins an Inno ≥6.3 so
   this compiles (leave a one-line comment recording the version floor — if a future
   runner can't guarantee 6.3+, the universal fallback is `x64`, but do not leave both
   tokens live).

4. **`[Files]`.**
   ```
   [Files]
   Source: "..\..\dist\the-one\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
   Source: "installer-assets\the-one.ico"; DestDir: "{app}"; Flags: ignoreversion
   ```
   The first line pulls the whole one-dir (exe + `_internal/`). The `.iss` lives in
   `packaging/windows/`, so `..\..\dist\the-one\` reaches the repo-root `dist/`.

5. **`[Tasks]` + `[Icons]`.**
   ```
   [Tasks]
   Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"

   [Icons]
   Name: "{group}\GleepGlorp AI"; Filename: "{app}\the-one.exe"; Parameters: "app"; IconFilename: "{app}\the-one.ico"
   Name: "{group}\Uninstall GleepGlorp AI"; Filename: "{uninstallexe}"
   Name: "{autodesktop}\GleepGlorp AI"; Filename: "{app}\the-one.exe"; Parameters: "app"; IconFilename: "{app}\the-one.ico"; Tasks: desktopicon
   ```

6. **`[Run]` (optional).** A post-install "Launch GleepGlorp AI" checkbox:
   ```
   [Run]
   Filename: "{app}\the-one.exe"; Parameters: "app"; Description: "Launch GleepGlorp AI"; Flags: nowait postinstall skipifsilent
   ```

7. **SmartScreen docs.** In `packaging/windows/README.md` add an "Unsigned installer —
   first run" section: double-clicking the unsigned `.exe` triggers "Windows protected
   your PC" (SmartScreen, unknown publisher); the click-through is **More info → Run
   anyway**. Note this is expected per the mission no-signing constraint and that a
   signing step can be added later (conditional on a cert secret) without reworking the
   `.iss`. F9 inherits this text for the consolidated per-OS docs.

8. **Signing hook (inert).** Optionally add a commented `[Setup] SignTool=` /
   `SignedUninstaller` note showing where signing slots in later — must be commented
   out / no-op so the unsigned build is unaffected.

## Edge Cases

- **Inno arch token version skew** — `x64compatible` requires Inno 6.3+. Resolved by
  pinning Inno ≥6.3 in Leg 4's CI; the `.iss` uses `x64compatible` only (the `x64`
  fallback is documented in a comment but not left live alongside it).
- **`/DAppVersion` override** — without the `#ifndef` guard, a `#define` later in the
  file would shadow the CLI `/D`. Guard it.
- **One-dir not built yet** — the `[Files]` `Source` points at `dist/the-one/` which
  only exists after the Leg-2 `.spec` runs (Leg 4 CI builds it before `iscc`). On this
  host `dist/` is absent; that's expected (no local compile).
- **Per-user vs admin install** — `PrivilegesRequired=admin` + `{autopf}` → Program
  Files (machine-wide). If a per-user no-elevation install is later wanted, switch to
  `PrivilegesRequired=lowest` and `{autopf}` resolves to the per-user app dir; out of
  scope to support both now — pick admin, document the alternative.
- **Shortcut launches `app` but no webview backend** — handled upstream: Flight 4's
  `interfaces/app.py:run` falls back to the system browser; not an installer concern.

## Files Affected

- `packaging/windows/the-one.iss` *(new)*
- `packaging/windows/installer-assets/the-one.ico` *(new — copy of brand favicon.ico)*
- `packaging/windows/README.md` — installer build + SmartScreen section.
- `CLAUDE.md`/`README.md` — extend the packaging pointer only if warranted.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All locally-verifiable acceptance criteria met; Leg-4 `iscc`-build forward
      dependency recorded
- [ ] Host-native unit suite green (no `the_one/` runtime changes)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (Flight 5 batches review + commit after Leg 4;
      do NOT commit, do NOT touch flight.md status)

## Citation Audit

All citations verified against current code at leg design time (2026-06-14) over the
post-Leg-2 tree: `packaging/windows/the-one.spec` (one-dir `dist/the-one/` output),
`the_one/__init__.py:3` (`__version__ = "0.2.0"`),
`the_one/interfaces/web/static/brand/favicon.ico` (6977-byte `.ico`, the only one in
the repo), `the_one/main.py:cli_entry` (`app` branch). No drift; all `OK`.
