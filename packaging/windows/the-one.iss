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
; Build (Windows-only -- iscc is the Inno compiler; it cannot run on Linux/WSL2). Use the recipe,
; packaging\windows\build.ps1: it stages the source, renders product.iss (below), freezes, and runs
;   iscc /DDistDir=<dist-dir> /O<output-dir> packaging\windows\the-one.iss
; Output: <output-dir>\the-one-setup-<version>.exe  (the stem comes from product.toml).
;
; Mission 32 Flight 4: the names, the version and the exe names are NOT written here any more.
; product.iss is rendered from packaging/product.toml by packaging/render.py (template
; product.iss.in) and is the only version source: no command-line version define, no fallback, so a
; missing product.iss is an ISCC error, not a silent 0.2.0. ISPP looks for the include in this
; file's own directory first, which is where build.ps1 writes it.

#include "product.iss"

; The frozen one-dir to package (build.ps1 passes /DDistDir=<Out>\dist-<version>).
#ifndef DistDir
  #error DistDir is not defined: pass /DDistDir=<the PyInstaller distpath> (build.ps1 does)
#endif

[Setup]
; Stable AppId GUID — frozen, NEVER regenerate. This is the upgrade/uninstall
; identity Windows tracks across versions; changing it would orphan prior installs.
AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={autopf}\{#AppDirName}
DefaultGroupName={#AppDirName}
; Branded Add/Remove-Programs entry. The windowed exe (the-one-app.exe) now embeds
; the brand icon via EXE(icon=) in the .spec (DD5 / Leg 5). UninstallDisplayIcon
; still uses the separately-installed {app}\the-one.ico for Add/Remove-Programs
; registration, which is correct — that entry points at the install-dir copy.
UninstallDisplayIcon={app}\the-one.ico
OutputBaseFilename={#SetupStem}-{#AppVersion}
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
; F6 HAT fix: close-to-tray means WM_CLOSE only hides the running app, so the
; installer's normal graceful-close step leaves the process alive and files locked.
; CloseApplications=force tells the Restart Manager to gracefully close then forcibly
; terminate any process locking install-dir files. RestartApplications=no prevents
; the Restart Manager from relaunching the old binary after the upgrade completes
; (the post-install [Run] entry handles optional user-initiated launch instead).
CloseApplications=force
RestartApplications=no

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
; The entire one-dir (the-one.exe + _internal/ payload) from the PyInstaller distpath that
; build.ps1 passes as /DDistDir (outside the repo; there is no repo-root dist/ any more).
Source: "{#DistDir}\{#DistName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Install the branded .ico into {app} so the shortcut has a durable icon target
; (copied from the_one/interfaces/web/static/brand/favicon.ico — the installer does
; not reach into the app's live static tree).
Source: "installer-assets\the-one.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start-menu shortcut -> the WINDOWED launcher the-one-app.exe (console=False, no
; stray console window — operator-HAT fix). It always runs the `app` path, so no
; Parameters needed. The console the-one.exe remains the CLI:
;   the-one.exe chat | serve | doctor | version   (run from {app}; no extra shortcut)
Name: "{group}\{#AppName}"; Filename: "{app}\{#GuiExe}"; IconFilename: "{app}\the-one.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Desktop shortcut gated behind the desktopicon [Tasks] checkbox.
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#GuiExe}"; IconFilename: "{app}\the-one.ico"; Tasks: desktopicon

[Run]
; Optional post-install launch checkbox (skipped on silent installs).
Filename: "{app}\{#GuiExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

; Uninstall: the Inno default removes the install tree ({app}) and both shortcuts.
; No custom [UninstallDelete] needed — everything lives under {app}.

[Code]
// F6 HAT fix: close-to-tray makes WM_CLOSE hide rather than quit the running app,
// so the Restart Manager may not flag the background process as a locker. This
// backstop force-terminates both the windowed launcher (the-one-app.exe) and the
// CLI entry-point (the-one.exe) before files are copied. taskkill /F is best-effort
// — RC is ignored so a "process not found" (exit 128) does not abort the install.
// The installer image is the-one-setup-<ver>.exe, so neither target matches it.
procedure KillRunning;
var
  RC: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM the-one-app.exe', '',
       SW_HIDE, ewWaitUntilTerminated, RC);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM the-one.exe', '',
       SW_HIDE, ewWaitUntilTerminated, RC);
end;

// --- Mission 32 Flight 4 (DD2): quit the running app gracefully, then force ---------------------
// KillRunning above is the force path and stays the last step of both sequences. Before it, the
// installer (and the uninstaller) asks the running app to quit through its own CLI
// (`the-one.exe quit --wait`, which makes the server drain: sessions closed, MCP children
// stopped), polls until the processes are gone (bounded at 90 s), and only then force-kills what
// is left. CloseApplications=force / RestartApplications=no above remain as the backstop: the
// Restart Manager alone cannot close a tray app (probe W3, run 40246340174: installer exit 5).
// Every stage logs a line, so /LOG shows the order (the lifecycle rows L7 and L9 read it).
// Order evidence (leg 1, probe run 40246340174): in W3's /LOG, PrepareToInstall ran (line 14,
// "rm-variant: PrepareToInstall ran") BEFORE "Shutting down applications using our files"
// (line 21), so the quit and the poll in PrepareToInstall finish before Restart Manager starts;
// W4's quit call drained the app before Restart Manager ran.
// The quit call is made only when {app}\the-one.exe exists; the poll and KillRunning run
// either way (harmless when nothing is running).
//
// tasklist through cmd + find: find exits 0 when the image name is in the list.
function ImageRunning(const Image: String): Boolean;
var
  RC: Integer;
begin
  Result := False;
  if Exec(ExpandConstant('{sys}\cmd.exe'),
          '/C tasklist /FI "IMAGENAME eq ' + Image + '" /NH | find /I "' + Image + '"',
          '', SW_HIDE, ewWaitUntilTerminated, RC) then
    Result := (RC = 0);
end;

// the-one.exe is watched as well as the-one-app.exe: the quit CLI IS a the-one.exe in {app}, and
// it holds a file open until it has seen the app go (its own bound is 5 s plus 75 s, below 90 s).
function AppsRunning: Boolean;
begin
  Result := ImageRunning('the-one-app.exe') or ImageRunning('the-one.exe');
end;

// Declared here under unique names so this compiles whether or not Inno provides them as built-ins.
// They are plain kernel32 imports, which work in the installer and in the uninstaller.
function M32Tick: Cardinal;
external 'GetTickCount@kernel32.dll stdcall';

procedure M32Sleep(Ms: Cardinal);
external 'Sleep@kernel32.dll stdcall';

// The shared half: poll (bounded), log what is left, then KillRunning, always. Callable from
// setup and from uninstall code (Exec, Log, FileExists and ExpandConstant are available in both).
procedure PollThenKill(const Tag: String);
var
  I: Integer;
  Started, Elapsed, Limit: Cardinal;
  Present: Boolean;
begin
  Started := M32Tick;
  Limit := 90000;
  Elapsed := 0;
  I := 0;
  Present := AppsRunning;
  if Present then
    Log(Tag + ' quit-poll: present (iteration 0)')
  else
    Log(Tag + ' quit-poll: absent at iteration 0 (nothing was running)');
  while Present and (Elapsed < Limit) do
  begin
    M32Sleep(1000);
    I := I + 1;
    Elapsed := M32Tick - Started;
    Present := AppsRunning;
  end;
  if Present then
    Log(Tag + ' quit-poll: timeout after 90 s, processes still present')
  else
    Log(Tag + ' quit-poll: gone (iteration ' + IntToStr(I) + ')');
  if AppsRunning then
    Log(Tag + ' quit-poll: something left before KillRunning')
  else
    Log(Tag + ' quit-poll: nothing left before KillRunning');
  Log(Tag + ' quit-killrunning: calling KillRunning');
  KillRunning;
  Log(Tag + ' quit-killrunning: done');
end;

// Install: ExecAsOriginalUser runs the quit CLI as the user who started setup (not the elevated
// admin token), so `quit` resolves THAT user's data directory and credential. It needs Inno
// Setup 6.1 or newer (build.ps1 refuses an older parsed ISCC version). It is a setup-only
// function, so it lives only here and never in the uninstall path.
procedure QuitThenKillSetup;
var
  RC: Integer;
  Exe: String;
begin
  Exe := ExpandConstant('{app}\the-one.exe');
  if FileExists(Exe) then
  begin
    Log('setup quit-call: ExecAsOriginalUser ' + Exe + ' quit --wait');
    if not ExecAsOriginalUser(Exe, 'quit --wait', '', SW_HIDE, ewNoWait, RC) then
      Log('setup quit-call: ExecAsOriginalUser returned False, RC=' + IntToStr(RC))
    else
      Log('setup quit-call: started');
  end
  else
    Log('setup quit-call: ' + Exe + ' does not exist, nothing to ask (an install without the quit command)');
  PollThenKill('setup');
end;

// Uninstall: ExecAsOriginalUser is not available to uninstall-time [Code] (it is a setup-only
// function in Inno Setup 6), so the uninstaller uses Exec, which runs the quit CLI with the
// uninstaller's own token: the user who ran the uninstall, elevated (PrivilegesRequired=admin).
// In the silent-elevation case (an administrator accepting or auto-approving the prompt) that is
// the same user who installed, so `quit` resolves the same data directory and credential. When
// the elevating account is a different one from the user running the app, the quit call cannot
// reach the app: the poll then times out or sees it still running and KillRunning ends it. That
// case is a field check, not something the hosted runner proves.
procedure QuitThenKillUninstall;
var
  RC: Integer;
  Exe: String;
begin
  Exe := ExpandConstant('{app}\the-one.exe');
  if FileExists(Exe) then
  begin
    Log('uninstall quit-call: Exec ' + Exe + ' quit --wait');
    if not Exec(Exe, 'quit --wait', '', SW_HIDE, ewNoWait, RC) then
      Log('uninstall quit-call: Exec returned False, RC=' + IntToStr(RC))
    else
      Log('uninstall quit-call: started');
  end
  else
    Log('uninstall quit-call: ' + Exe + ' does not exist, nothing to ask');
  PollThenKill('uninstall');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  QuitThenKillSetup;
  Result := '';
end;

// Before the uninstaller removes any file ({app} still holds the exes here).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    QuitThenKillUninstall;
end;
