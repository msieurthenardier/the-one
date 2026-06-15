; the-one.iss — Inno Setup script for the GleepGlorp AI Windows installer (DD6).
;
; Wraps the Leg-2 PyInstaller one-dir (dist/the-one/) in a double-click installer:
;   * installs the whole one-dir under Program Files\GleepGlorp AI\
;   * Start-menu + (optional) Desktop shortcut launching the windowed app
;     (the-one.exe app — DD3) with the branded icon
;   * a clean Inno default uninstaller
;
; Display-name / slug split (deliberate, NOT a mismatch):
;   * Display name           = "GleepGlorp AI"  (AppName, install dir, shortcut;
;                               matches `the-one.exe version` -> "GleepGlorp AI v0.2.0")
;   * Internal slug / exe     = "the-one"        (the-one.exe, the-one-setup-*.exe)
; So the installer lands the-one.exe under Program Files\GleepGlorp AI\ with a
; "GleepGlorp AI" shortcut — intentional.
;
; Build (Windows-only — iscc is the Inno compiler; it cannot run on Linux/WSL2):
;   iscc packaging\windows\the-one.iss
;   iscc /DAppVersion=1.2.3 packaging\windows\the-one.iss   ; CI injects the_one.__version__
; Output: packaging\windows\Output\the-one-setup-<version>.exe
;
; This .iss is authored + statically reviewed on the Linux dev host. The actual
; `iscc` build of the .exe runs in Leg 4's CI on windows-2022 (Inno Setup >=6.3
; pinned), after the Leg-2 one-dir is built. See the flight log Decisions entry.

; --- Version define (CI-injectable) ---------------------------------------
; The #ifndef guard lets `iscc /DAppVersion=x.y.z` win: a /D define is set before
; the script is parsed, so this #define is skipped when /D supplied it.
#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
; Stable AppId GUID — frozen, NEVER regenerate. This is the upgrade/uninstall
; identity Windows tracks across versions; changing it would orphan prior installs.
AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}
AppName=GleepGlorp AI
AppVersion={#AppVersion}
AppVerName=GleepGlorp AI {#AppVersion}
DefaultDirName={autopf}\GleepGlorp AI
DefaultGroupName=GleepGlorp AI
; Branded Add/Remove-Programs entry. The exe carries no embedded icon resource
; (the Leg-2 .spec omits EXE(icon=)), so point at the installed .ico.
UninstallDisplayIcon={app}\the-one.ico
OutputBaseFilename=the-one-setup-{#AppVersion}
; Resolves to packaging\windows\Output\ (relative to this .iss). Leg 4's CI globs
; this for the uploaded artifact.
OutputDir=Output
SetupIconFile=installer-assets\the-one.ico
Compression=lzma2
SolidCompression=yes
; x64compatible requires Inno Setup 6.3+ (pinned by Leg 4's CI). If a future runner
; can't guarantee 6.3+, the universal fallback is `x64` — but do NOT leave both
; tokens live; swap, don't duplicate.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Program Files is machine-wide, so elevation is required. Per-user alternative:
; PrivilegesRequired=lowest (then {autopf} resolves to the per-user app dir). We
; pick admin deliberately for a Program Files install; per-user is out of scope now.
PrivilegesRequired=admin
WizardStyle=modern

; --- Signing hook (inert — unsigned this round) ---------------------------
; The mission imposes no code-signing this round, so the build is unsigned and
; triggers SmartScreen (see README "Unsigned installer — first run"). To sign later
; WITHOUT reworking this .iss, register a sign tool with iscc and uncomment:
;   SignTool=mysigntool
;   SignedUninstaller=yes
; (Define the tool via `iscc /Smysigntool="signtool ... $f"` or the IDE settings.)
; Left commented so the current unsigned build is unaffected.

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; The entire Leg-2 one-dir (the-one.exe + _internal/ payload). This .iss lives in
; packaging\windows\, so ..\..\dist\the-one\ reaches the repo-root dist/. dist/
; exists only after the Leg-2 .spec runs (Leg 4 CI builds it before iscc).
Source: "..\..\dist\the-one\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Install the branded .ico into {app} so the shortcut has a durable icon target
; (copied from the_one/interfaces/web/static/brand/favicon.ico — the installer does
; not reach into the app's live static tree).
Source: "installer-assets\the-one.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start-menu shortcut -> the WINDOWED launcher the-one-app.exe (console=False, no
; stray console window — operator-HAT fix). It always runs the `app` path, so no
; Parameters needed. The console the-one.exe remains the CLI:
;   the-one.exe chat | serve | doctor | version   (run from {app}; no extra shortcut)
Name: "{group}\GleepGlorp AI"; Filename: "{app}\the-one-app.exe"; IconFilename: "{app}\the-one.ico"
Name: "{group}\Uninstall GleepGlorp AI"; Filename: "{uninstallexe}"
; Desktop shortcut gated behind the desktopicon [Tasks] checkbox.
Name: "{autodesktop}\GleepGlorp AI"; Filename: "{app}\the-one-app.exe"; IconFilename: "{app}\the-one.ico"; Tasks: desktopicon

[Run]
; Optional post-install launch checkbox (skipped on silent installs).
Filename: "{app}\the-one-app.exe"; Description: "Launch GleepGlorp AI"; Flags: nowait postinstall skipifsilent

; Uninstall: the Inno default removes the install tree ({app}) and both shortcuts.
; No custom [UninstallDelete] needed — everything lives under {app}.
