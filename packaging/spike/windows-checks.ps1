# Windows checks for candidate B's MSI (Mission 32 Flight 1 spike, leg windows-cost, DD7).
# Run on the hosted windows-2022 runner by packaging-probe-windows.yml, one phase per step.
# Every step is logged to its own file and none aborts the later ones; a failed hard check
# adds a FAIL line to SUMMARY.txt (the workflow's last step reads it). Disposable runner only.
#
#   windows-checks.ps1 -Phase fresh   -Msi <path> [-LogDir <dir>]
#   windows-checks.ps1 -Phase upgrade -Msi <path> [-LogDir <dir>]
#
#   fresh   : install the MSI per-user, record where it lands, run doctor / gate 2 / serve /
#             gate 4 / a probe on a copy / a bare launch, then uninstall it.
#   upgrade : delete the data dir, install the RELEASED Inno installer (latest v* release),
#             run it and seed an agent, stop it, install the MSI over it, record what changed
#             and whether the seeded agent reads back, then uninstall the MSI and record what
#             remains.
# Files land in <LogDir>\B\<phase>\. Needs on PATH: python (setup-python), gh (upgrade only,
# with GH_TOKEN set).
param(
    [Parameter(Mandatory)][ValidateSet('fresh', 'upgrade')][string]$Phase,
    [Parameter(Mandatory)][string]$Msi,
    [string]$LogDir = $(if ($env:M32_LOGS) { $env:M32_LOGS } else { 'C:\m32\logs' })
)
# This script deletes %LOCALAPPDATA%\the-one and installs and removes programs: a disposable hosted
# runner only, never a person's PC (the operator's real-machine try is a separate, manual guide).
if ($env:GITHUB_ACTIONS -ne 'true') { Write-Error 'refusing to run outside GitHub Actions'; exit 2 }
$ErrorActionPreference = 'Continue'
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $HERE 'windows-lib.ps1')

$OUT = Join-Path $LogDir "B\$Phase"
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
$SUMMARY = Join-Path $OUT 'SUMMARY.txt'
Set-Content -Path $SUMMARY -Value '' -Encoding utf8
$SCRATCH = Join-Path $(if ($env:M32_BUILD) { $env:M32_BUILD } else { 'C:\m32' }) "checks-$Phase"
Remove-Item -Recurse -Force $SCRATCH -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$SCRATCH\data", "$SCRATCH\cwd" | Out-Null
$script:Fails = 0
$PORT = 8490
$GH_REPO = if ($env:GITHUB_REPOSITORY) { @('-R', $env:GITHUB_REPOSITORY) } else { @() }
$DEFAULT_DATA = Join-Path $env:LOCALAPPDATA 'the-one'
$env:PYTHONUTF8 = '1'

function Note([string]$m) { Write-Host $m; Add-Content -Path $SUMMARY -Value $m -Encoding utf8 }
function Hard([string]$name, [bool]$ok) {
    if ($ok) { Note "PASS $name" } else { Note "FAIL $name"; $script:Fails++ }
}
function Tail([string]$path, [int]$n = 200) {
    if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Tail $n } else { "(missing: $path)" }
}
function Save([string]$name, $content) {
    $content | Out-String -Width 220 | Set-Content -Path (Join-Path $OUT $name) -Encoding utf8
}

# --- msiexec: per-user on every call (finding 2) ----------------------------------------------
$MSI_FLAGS = @('/qn', '/norestart', 'MSIINSTALLPERUSER=1', 'ALLUSERS=2')
function Install-Msi([string]$tag) {
    $log = Join-Path $OUT "msi-install-$tag.log"
    $r = Invoke-Capped -Exe 'msiexec.exe' -TimeoutSec 600 -OutFile (Join-Path $OUT "msiexec-install-$tag.txt") `
        -ArgList (@('/i', $Msi) + $MSI_FLAGS + @('/l*v', $log))
    Note "msiexec /i ($tag) rc=$($r.Rc) in $($r.Seconds) s"
    if ($r.Rc -ne 0 -and $r.Rc -ne 3010) {
        Tail $log 200 | Set-Content -Path (Join-Path $OUT "msi-install-$tag-tail200.txt") -Encoding utf8
        Note "  msi install log tail saved (msi-install-$tag-tail200.txt)"
    }
    return $r
}
function Uninstall-Msi([string]$tag) {
    $log = Join-Path $OUT "msi-uninstall-$tag.log"
    $r = Invoke-Capped -Exe 'msiexec.exe' -TimeoutSec 600 -OutFile (Join-Path $OUT "msiexec-uninstall-$tag.txt") `
        -ArgList (@('/x', $Msi) + $MSI_FLAGS + @('/l*v', $log))
    Note "msiexec /x ($tag) rc=$($r.Rc) in $($r.Seconds) s"
    if ($r.Rc -ne 0 -and $r.Rc -ne 3010) {
        Tail $log 200 | Set-Content -Path (Join-Path $OUT "msi-uninstall-$tag-tail200.txt") -Encoding utf8
    }
    return $r
}

# --- observation helpers -------------------------------------------------------------------------
function Get-UninstallEntries {
    $roots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        foreach ($k in (Get-ChildItem $root -ErrorAction SilentlyContinue)) {
            $p = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction SilentlyContinue
            if ($p.DisplayName -like 'GleepGlorp*') {
                [pscustomobject]@{
                    Hive = ($root -replace 'Microsoft\\Windows\\CurrentVersion\\Uninstall', '...\Uninstall')
                    Key = $k.PSChildName; DisplayName = $p.DisplayName; DisplayVersion = $p.DisplayVersion
                    Publisher = $p.Publisher; InstallLocation = $p.InstallLocation
                    UninstallString = $p.UninstallString
                }
            }
        }
    }
}
function Get-StartMenuEntries {
    $roots = @(
        (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
        (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs')
    )
    $sh = New-Object -ComObject WScript.Shell
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        Get-ChildItem -Path $root -Recurse -Filter *.lnk -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like '*GleepGlorp*' } | ForEach-Object {
                $lnk = $sh.CreateShortcut($_.FullName)
                [pscustomobject]@{ Scope = $(if ($root -like "$env:APPDATA*") { 'user' } else { 'all-users' })
                    Link = $_.FullName.Substring($root.Length); Target = $lnk.TargetPath; Args = $lnk.Arguments }
            }
    }
}
function Find-MsiExe {
    $roots = @((Join-Path $env:LOCALAPPDATA 'Programs'), $env:ProgramFiles, ${env:ProgramFiles(x86)}) |
        Where-Object { $_ -and (Test-Path $_) }
    Get-ChildItem -Path $roots -Recurse -Depth 4 -Filter 'GleepGlorp AI.exe' -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
}
function Wait-Live([int]$seconds, [System.Diagnostics.Process]$proc) {
    for ($i = 0; $i -lt $seconds; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "http://127.0.0.1:$PORT/api/live"
            if ($r.StatusCode -eq 200) { return $r.Content }
        } catch { }
        if ($proc -and $proc.HasExited) { return $null }
        Start-Sleep -Seconds 1
    }
    return $null
}
function Get-Credential-Text([string]$dataDir) {
    $f = Join-Path $dataDir 'api-credential'
    if (Test-Path $f) { return (Get-Content -Raw $f).Trim() }
    return ''
}
function Get-Agents([string]$cred) {
    try {
        $r = Invoke-RestMethod -TimeoutSec 20 -Headers @{ Authorization = "Bearer $cred" } -Uri "http://127.0.0.1:$PORT/api/agents"
        return ($r | ConvertTo-Json -Depth 6 -Compress)
    } catch { return "ERROR: $_" }
}
function Snapshot-State([string]$tag) {
    Save "state-$tag-uninstall-entries.txt" (Get-UninstallEntries | Format-List)
    Save "state-$tag-startmenu.txt" (Get-StartMenuEntries | Format-List)
    $dirs = @(
        (Join-Path $env:ProgramFiles 'GleepGlorp AI'),
        (Join-Path $env:LOCALAPPDATA 'Programs\GleepGlorp AI'),
        $DEFAULT_DATA
    )
    $dirs | ForEach-Object {
        "{0}: exists={1}" -f $_, (Test-Path $_)
        if (Test-Path $_) { Get-ChildItem $_ -Force | Select-Object Mode, Length, Name | Format-Table -AutoSize | Out-String -Width 200 }
    } | Set-Content -Path (Join-Path $OUT "state-$tag-dirs.txt") -Encoding utf8
    $ue = @(Get-UninstallEntries)
    $sm = @(Get-StartMenuEntries)
    Note ("[$tag] Add/Remove entries: {0}; Start-menu links: {1}" -f $ue.Count, $sm.Count)
    foreach ($u in $ue) { Note ("  ARP {0} | {1} {2} | {3} | loc={4}" -f $u.Hive, $u.DisplayName, $u.DisplayVersion, $u.Key, $u.InstallLocation) }
    foreach ($s in $sm) { Note ("  LNK [{0}] {1} -> {2} {3}" -f $s.Scope, $s.Link, $s.Target, $s.Args) }
}

# Run an app executable (the MSI's stub or Inno's the-one.exe) and keep its combined output.
function Invoke-App([string]$exe, [string[]]$appArgs, [string]$name, [int]$timeout, [hashtable]$envSet = @{}, [string[]]$envClear = @()) {
    $file = Join-Path $OUT $name
    $inv = {
        Invoke-Capped -Exe $exe -ArgList $appArgs -OutFile $file -TimeoutSec $timeout -WorkDir "$SCRATCH\cwd"
    }
    $res = Use-EnvVars -Set $envSet -Clear $envClear -Body $inv
    return $res
}

# A copy of the installed app with two extra modules (adding them to the install would alter the
# tree the uninstall check looks at): the stub probe and the redirect wrapper.
$script:CopyExe = $null
function Ensure-ProbeCopy([string]$appDir, [string]$exe) {
    if ($script:CopyExe) { return $script:CopyExe }
    $copy = Join-Path $SCRATCH 'probe-copy'
    Copy-Item -Recurse -Force $appDir $copy
    $appPkg = Join-Path $copy 'app'
    if (Test-Path $appPkg) {
        Copy-Item (Join-Path $HERE 'm32probe_win.py') $appPkg
        Copy-Item (Join-Path $HERE 'm32run.py') $appPkg
    }
    $script:CopyExe = Join-Path $copy (Split-Path -Leaf $exe)
    return $script:CopyExe
}
# Run a CLI command through the copy's redirect wrapper; the wrapper's file becomes $name.
function Invoke-Wrapped([string]$appDir, [string]$exe, [string]$cliArgs, [string]$name, [int]$timeout, [hashtable]$extraEnv = @{}) {
    $cexe = Ensure-ProbeCopy $appDir $exe
    $wrapped = Join-Path $OUT "$name.wrapped"
    Remove-Item -LiteralPath $wrapped -Force -ErrorAction SilentlyContinue
    $env2 = @{ BRIEFCASE_MAIN_MODULE = 'm32run'; M32_OUT = $wrapped; M32_ARGS = $cliArgs } + $extraEnv
    $r = Invoke-App $cexe @() "$name.stub" $timeout $env2
    if (Test-Path -LiteralPath $wrapped) {
        Copy-Item -LiteralPath $wrapped (Join-Path $OUT $name) -Force
    } else {
        Copy-Item -LiteralPath (Join-Path $OUT "$name.stub") (Join-Path $OUT $name) -Force
    }
    return $r
}

function Note-Header {
    Note "== B/$Phase windows checks: msi=$Msi"
    $info = @(
        '-- OS', ((Get-CimInstance Win32_OperatingSystem) | ForEach-Object { "$($_.Caption) $($_.Version) $($_.OSArchitecture)" }),
        '-- python on PATH', ((Get-Command python -ErrorAction SilentlyContinue).Source), (& python --version 2>&1),
        '-- pip', (& python -m pip --version 2>&1),
        '-- pwsh', $PSVersionTable.PSVersion.ToString(),
        '-- gh', ((Get-Command gh -ErrorAction SilentlyContinue).Source),
        '-- user / profile', "$env:USERNAME $env:USERPROFILE",
        '-- LOCALAPPDATA', $env:LOCALAPPDATA,
        '-- PATH', $env:PATH
    )
    $info | Set-Content -Path (Join-Path $OUT 'env.txt') -Encoding utf8
}

# ============================================================================================
# Phase: fresh
# ============================================================================================
function Phase-Fresh {
    if (-not (Test-Path -LiteralPath $Msi)) { Hard 'msi present' $false; return }
    Note ("msi: {0} bytes sha256={1}" -f (Get-Item -LiteralPath $Msi).Length, (Get-FileHash -Algorithm SHA256 -LiteralPath $Msi).Hash.ToLower())
    Snapshot-State 'before'

    # ---- install --------------------------------------------------------------------------
    $r = Install-Msi 'fresh'
    Hard 'msi installs (rc 0 or 3010)' ($r.Rc -eq 0 -or $r.Rc -eq 3010)
    $exeItem = Find-MsiExe
    if (-not $exeItem) { Hard 'installed stub found' $false; Snapshot-State 'after-install'; return }
    $EXE = $exeItem.FullName
    $APPDIR = $exeItem.DirectoryName
    Note "install path: $APPDIR"
    Note "stub: $EXE"
    Snapshot-State 'after-install'
    Get-ChildItem $APPDIR -Force | Select-Object Mode, Length, Name | Format-Table -AutoSize | Out-String -Width 200 |
        Set-Content -Path (Join-Path $OUT 'layout-top.txt') -Encoding utf8
    Get-ChildItem $APPDIR -Filter *._pth -ErrorAction SilentlyContinue | ForEach-Object { "-- $($_.Name)"; Get-Content $_.FullName } |
        Set-Content -Path (Join-Path $OUT 'layout-pth.txt') -Encoding utf8
    $bytes = (Get-ChildItem $APPDIR -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    Note ("installed size: {0:N0} bytes; stub: {1}" -f $bytes, (& { (Get-Item $EXE).VersionInfo | ForEach-Object { "$($_.ProductName) $($_.FileVersion)" } }))
    # the GUI/console subsystem of the stub: PE header, Subsystem field (2 = GUI, 3 = console)
    try {
        $b = [System.IO.File]::ReadAllBytes($EXE)
        $pe = [BitConverter]::ToInt32($b, 0x3C)
        $sub = [BitConverter]::ToUInt16($b, $pe + 24 + 68)
        Note "stub PE subsystem: $sub (2 = GUI, 3 = console)"
    } catch { Note "stub PE subsystem: unreadable ($_)" }
    $pys = @(Get-ChildItem $APPDIR -Filter 'python*.exe' -ErrorAction SilentlyContinue)
    Note ("python*.exe in the install dir: {0}" -f $(if ($pys) { ($pys.Name -join ', ') } else { '(none)' }))

    # ---- version (can the GUI stub talk to a redirected stdout at all?) ----------------------------
    $dataEnv = @{ THE_ONE_DATA_DIR = "$SCRATCH\data" }
    $r = Invoke-App $EXE @('version') 'version.txt' 120 $dataEnv
    $v = (Get-Content (Join-Path $OUT 'version.txt') -Encoding utf8 | Select-Object -First 1)
    $sz = (Get-Item (Join-Path $OUT 'version.txt.out') -ErrorAction SilentlyContinue).Length
    Note "version: '$v' (rc=$($r.Rc), stdout file $sz bytes)"
    Hard 'version prints to a redirected stdout' ($r.Rc -eq 0 -and $sz -gt 0)
    $silent = (-not $sz)
    if ($silent) { Note '  CLI COST: the GUI-subsystem stub gave no stdout (B needs console_app or a second console app for its CLI)' }

    # ---- gate 1: doctor ------------------------------------------------------------------------
    if ($silent) {
        Note '  doctor through the redirect wrapper (m32run.py) on a copy, because the stub prints nothing'
        $r = Invoke-Wrapped $APPDIR $EXE 'doctor' 'doctor.txt' 300 $dataEnv
    } else {
        $r = Invoke-App $EXE @('doctor') 'doctor.txt' 300 $dataEnv
    }
    Note "doctor rc=$($r.Rc) in $($r.Seconds) s timedOut=$($r.TimedOut)"
    $score = (& python (Join-Path $HERE 'score_doctor_file.py') (Join-Path $OUT 'doctor.txt') 2>&1) -join ''
    $score | Set-Content -Path (Join-Path $OUT 'doctor-score.json') -Encoding utf8
    Note "doctor score: $score"
    Hard 'gate 1 doctor' ($score -match '"pass": true')
    Select-String -Path (Join-Path $OUT 'doctor.txt') -Pattern 'desktop shell|file watcher|window chrome|python interpreter|time zones|mcp sdk|usearch|embedding' -Encoding utf8 |
        ForEach-Object { Note ("  " + $_.Line.Trim()) }

    # ---- gate 2: the interpreter doctor resolved, run independently ------------------------------
    $pyp = ''
    $m = Select-String -Path (Join-Path $OUT 'doctor.txt') -Pattern 'python interpreter: OK.*resolved to (.+)$' -Encoding utf8 | Select-Object -First 1
    if ($m) { $pyp = $m.Matches[0].Groups[1].Value.Trim() }
    $g2 = Join-Path $OUT 'gate2.txt'
    $ran = $false
    if ($pyp -and (Test-Path -LiteralPath $pyp)) {
        $rr = Invoke-Capped -Exe $pyp -ArgList @('-c', 'import sys; print(sys.executable, sys.prefix)') -OutFile $g2 -TimeoutSec 60
        $ran = ($rr.Rc -eq 0)
    } else { "resolved: '$pyp' (missing)" | Set-Content $g2 -Encoding utf8 }
    Note ("gate 2: resolved='{0}' ran={1}" -f $pyp, $ran)
    $inside = $pyp -and ($pyp.ToLower().StartsWith($APPDIR.ToLower()))
    $setupPy = (Get-Command python -ErrorAction SilentlyContinue).Source
    Note ("  setup-python's python: $setupPy; resolved is inside the install dir: $inside")
    Hard 'gate 2 interpreter outside the install dir' ([bool]$pyp -and $ran -and -not $inside)

    # ---- serve on a scratch port: GET /api/live needs no credential --------------------------------
    $serveEnv = @{ THE_ONE_PORT = "$PORT"; THE_ONE_DATA_DIR = "$SCRATCH\data" }
    $proc = $null
    Use-EnvVars -Set $serveEnv -Body {
        $script:proc = Start-Background -Exe $EXE -ArgList @('serve') -OutFile (Join-Path $OUT 'serve.log') -WorkDir "$SCRATCH\cwd"
    }
    $proc = $script:proc
    $live = Wait-Live 90 $proc
    Note ("serve /api/live: {0}" -f $(if ($live) { $live } else { '(no answer)' }))
    if ($proc) { Stop-Tree $proc.Id; Start-Sleep -Seconds 2 }
    Save 'serve-log.txt' ((Read-SharedText (Join-Path $OUT 'serve.log.out')) + "`n-- stderr --`n" + (Read-SharedText (Join-Path $OUT 'serve.log.err')))
    if (-not $live) {
        Note ("  serve.log tail: " + ((Tail (Join-Path $OUT 'serve-log.txt') 8) -join ' | '))
        # a GUI stub with no stdout may crash uvicorn (isatty on None): retry through the wrapper
        Note '  CLI COST: serve did not come up directly under the stub; retrying through the redirect wrapper (m32run.py) on a copy'
        $cexe = Ensure-ProbeCopy $APPDIR $EXE
        $wrapped = Join-Path $OUT 'serve-wrapped.txt'
        $wenv = $serveEnv + @{ BRIEFCASE_MAIN_MODULE = 'm32run'; M32_OUT = $wrapped; M32_ARGS = 'serve' }
        Use-EnvVars -Set $wenv -Body {
            $script:proc = Start-Background -Exe $cexe -ArgList @() -OutFile (Join-Path $OUT 'serve-wrapped.log') -WorkDir "$SCRATCH\cwd"
        }
        $proc = $script:proc
        $live = Wait-Live 90 $proc
        Note ("serve through the wrapper /api/live: {0}" -f $(if ($live) { $live } else { '(no answer)' }))
        if ($proc) { Stop-Tree $proc.Id; Start-Sleep -Seconds 2 }
        Note ("  wrapped serve output tail: " + ((Tail $wrapped 8) -join ' | '))
    }
    Hard 'serve answers /api/live' ([bool]$live)

    # ---- gate 4: the default data dir (the runner is disposable; no override) ------------------------
    $r = Invoke-App $EXE @('rotate-api-credential') 'gate4-rotate.txt' 60 @{} @('THE_ONE_DATA_DIR')
    Get-ChildItem -Recurse -Force $DEFAULT_DATA -ErrorAction SilentlyContinue | Select-Object FullName, Length |
        Format-Table -AutoSize | Out-String -Width 220 | Set-Content -Path (Join-Path $OUT 'gate4-ls.txt') -Encoding utf8
    $g4 = Get-Content (Join-Path $OUT 'gate4-rotate.txt') -Encoding utf8 -Raw
    Note ("gate 4: " + (($g4 -split "`n" | Select-Object -First 2) -join ' | '))
    $want = (Join-Path $env:LOCALAPPDATA 'the-one') + '\'
    Hard 'gate 4 data dir under %LOCALAPPDATA%\the-one' ($g4.ToLower().Contains($want.ToLower()))

    # ---- probe, on a COPY of the install (adding a module would alter the installed tree) -----------
    $pexe = Ensure-ProbeCopy $APPDIR $EXE
    $r = Invoke-App $pexe @('a', 'b') 'stub-probe.txt' 120 @{ BRIEFCASE_MAIN_MODULE = 'm32probe_win'; THE_ONE_DATA_DIR = "$SCRATCH\data" }
    Note ("stub probe rc=$($r.Rc): " + @(Select-String -Path (Join-Path $OUT 'stub-probe.txt') -Pattern '^PROBE' -Encoding utf8).Count + ' PROBE lines (stub-probe.txt)')
    Select-String -Path (Join-Path $OUT 'stub-probe.txt') -Pattern '^PROBE (sys.executable|sys.frozen|is_frozen|stdout|import|pywinpty)' -Encoding utf8 |
        Select-Object -First 14 | ForEach-Object { Note ("  " + $_.Line) }

    # ---- best effort, unscored: a Finder-style bare launch (the Start-menu shortcut's path) --------------
    $dopen = "$SCRATCH\data-open"
    New-Item -ItemType Directory -Force -Path $dopen | Out-Null
    $oproc = $null
    Use-EnvVars -Set @{ THE_ONE_PORT = "$PORT"; THE_ONE_DATA_DIR = $dopen } -Body {
        $script:oproc = Start-Background -Exe $EXE -ArgList @() -OutFile (Join-Path $OUT 'bare-launch.log') -WorkDir "$SCRATCH\cwd"
    }
    $oproc = $script:oproc
    $olive = Wait-Live 90 $oproc
    Note ("bare launch (no arguments): live={0}" -f $(if ($olive) { $olive } else { '(no answer)' }))
    if ($olive) {
        $cred = Get-Credential-Text $dopen
        try {
            $f = Invoke-WebRequest -UseBasicParsing -TimeoutSec 8 -Method Post -Headers @{ Authorization = "Bearer $cred" } -Uri "http://127.0.0.1:$PORT/api/window/focus"
            Note "  window focus: $($f.StatusCode) $($f.Content)"
        } catch { Note "  window focus: $_" }
        try {
            Add-Type -AssemblyName System.Windows.Forms, System.Drawing
            $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
            $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
            $bmp.Save((Join-Path $OUT 'bare-launch-screen.png'))
            Note '  screenshot saved (bare-launch-screen.png)'
        } catch { Note "  screenshot failed: $_" }
        Get-Process -Id $oproc.Id -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, MainWindowTitle |
            Format-List | Out-String | Set-Content -Path (Join-Path $OUT 'bare-launch-process.txt') -Encoding utf8
    }
    if ($oproc) { Stop-Tree $oproc.Id; Start-Sleep -Seconds 2 }

    # ---- uninstall -------------------------------------------------------------------------------
    $r = Uninstall-Msi 'fresh'
    Hard 'msi uninstalls (rc 0 or 3010)' ($r.Rc -eq 0 -or $r.Rc -eq 3010)
    Snapshot-State 'after-uninstall'
    Note ("after uninstall: install dir exists={0}" -f (Test-Path $APPDIR))
}

# ============================================================================================
# Phase: upgrade (over the released Inno installer)
# ============================================================================================
function Phase-Upgrade {
    if (-not (Test-Path -LiteralPath $Msi)) { Hard 'msi present' $false; return }
    # finding 6: the fresh-install step's data dir must not leak into the "before" state
    Remove-Item -Recurse -Force $DEFAULT_DATA -ErrorAction SilentlyContinue
    Note "data dir cleared: $DEFAULT_DATA exists=$(Test-Path $DEFAULT_DATA)"
    Snapshot-State 'start'

    # ---- the released Inno installer ---------------------------------------------------------------
    $dl = Join-Path $SCRATCH 'inno'
    New-Item -ItemType Directory -Force -Path $dl | Out-Null
    $tagFile = Join-Path $OUT 'inno-release.txt'
    $r = Invoke-Capped -Exe 'gh' -TimeoutSec 60 -OutFile $tagFile `
        -ArgList (@('release', 'list') + $GH_REPO + @('--exclude-drafts', '--exclude-pre-releases', '--limit', '30', '--json', 'tagName,isLatest'))
    $tag = $null
    try {
        $rows = Get-Content "$tagFile.out" -Raw -Encoding utf8 | ConvertFrom-Json
        $latest = @($rows | Where-Object { $_.isLatest -and $_.tagName -like 'v*' })
        if (-not $latest) { $latest = @($rows | Where-Object { $_.tagName -like 'v*' }) }
        if ($latest) { $tag = $latest[0].tagName }
    } catch { Note "release list unreadable: $_" }
    if (-not $tag) { Note 'FAIL upgrade scenario: no v* release found (gh release list)'; $script:Fails++; return }
    $r = Invoke-Capped -Exe 'gh' -TimeoutSec 600 -OutFile (Join-Path $OUT 'inno-download.txt') `
        -ArgList (@('release', 'download', $tag) + $GH_REPO + @('--pattern', 'the-one-setup-*.exe', '--dir', $dl))
    $setup = Get-ChildItem $dl -Filter 'the-one-setup-*.exe' | Select-Object -First 1
    if (-not $setup) { Note "FAIL upgrade scenario: could not download the Inno installer from $tag (rc=$($r.Rc))"; $script:Fails++; return }
    Note ("Inno release: {0}, {1} ({2:N0} bytes)" -f $tag, $setup.Name, $setup.Length)

    $r = Invoke-Capped -Exe $setup.FullName -TimeoutSec 900 -OutFile (Join-Path $OUT 'inno-install.txt') `
        -ArgList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$OUT\inno-install.log")
    Note "inno install rc=$($r.Rc) in $($r.Seconds) s"
    Hard 'inno installs' ($r.Rc -eq 0)
    $INNO = Join-Path $env:ProgramFiles 'GleepGlorp AI'
    $innoCli = Join-Path $INNO 'the-one.exe'
    Hard 'inno install dir has the-one.exe' (Test-Path $innoCli)
    Snapshot-State 'inno-installed'

    $r = Invoke-App $innoCli @('version') 'inno-version.txt' 60 @{} @('THE_ONE_DATA_DIR')
    Note ("inno version: '{0}' rc={1}" -f (Get-Content (Join-Path $OUT 'inno-version.txt') -Encoding utf8 | Select-Object -First 1), $r.Rc)

    # ---- seed data through the Inno install's serve --------------------------------------------------------
    $proc = $null
    Use-EnvVars -Set @{ THE_ONE_PORT = "$PORT" } -Clear @('THE_ONE_DATA_DIR') -Body {
        $script:proc = Start-Background -Exe $innoCli -ArgList @('serve') -OutFile (Join-Path $OUT 'inno-serve.log') -WorkDir "$SCRATCH\cwd"
    }
    $proc = $script:proc
    $live = Wait-Live 120 $proc
    Hard 'inno serve answers /api/live' ([bool]$live)
    $cred = Get-Credential-Text $DEFAULT_DATA
    Note ("inno credential file present: {0} (prefix {1})" -f ([bool]$cred), $(if ($cred) { $cred.Split('.')[0] } else { '-' }))
    $seeded = $false
    if ($live -and $cred) {
        try {
            $body = '{"name":"m32-upgrade-agent","description":"seeded under the Inno install"}'
            $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 30 -Method Post -ContentType 'application/json' `
                -Headers @{ Authorization = "Bearer $cred" } -Uri "http://127.0.0.1:$PORT/api/agents" -Body $body
            Note "seed agent: HTTP $($resp.StatusCode)"
        } catch { Note "seed agent failed: $_" }
        $list = Get-Agents $cred
        $list | Set-Content -Path (Join-Path $OUT 'agents-inno.json') -Encoding utf8
        $seeded = $list -match 'm32-upgrade-agent'
    }
    Hard 'agent seeded under the Inno install' $seeded
    if ($proc) { Stop-Tree $proc.Id; Start-Sleep -Seconds 3 }
    Get-ChildItem -Recurse -Force $DEFAULT_DATA -ErrorAction SilentlyContinue | Select-Object FullName, Length |
        Format-Table -AutoSize | Out-String -Width 220 | Set-Content -Path (Join-Path $OUT 'data-after-inno.txt') -Encoding utf8
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($INNO) })
    Note ("processes still running from the Inno dir after stop: {0}" -f $running.Count)

    # ---- the MSI over it -----------------------------------------------------------------------------------------
    $r = Install-Msi 'over-inno'
    Hard 'msi installs over the Inno install (rc 0 or 3010)' ($r.Rc -eq 0 -or $r.Rc -eq 3010)
    Snapshot-State 'after-msi-over-inno'
    $exeItem = Find-MsiExe
    Note ("both installs present: inno={0} msi={1}" -f (Test-Path $innoCli), [bool]$exeItem)
    $arp = @(Get-UninstallEntries)
    Note ("Add/Remove entries named GleepGlorp*: {0} (two means side by side, one means replaced)" -f $arp.Count)
    $links = @(Get-StartMenuEntries)
    foreach ($l in $links) {
        Note ("  start-menu '{0}' [{1}] runs: {2}" -f $l.Link, $l.Scope, $l.Target)
    }
    if (-not $exeItem) { Hard 'msi stub found after the install' $false; return }
    $EXE = $exeItem.FullName
    Note "msi install path: $($exeItem.DirectoryName); inno install path: $INNO"

    # ---- does the seeded agent read back through the MSI install? ----------------------------------------------------
    $proc = $null
    Use-EnvVars -Set @{ THE_ONE_PORT = "$PORT" } -Clear @('THE_ONE_DATA_DIR') -Body {
        $script:proc = Start-Background -Exe $EXE -ArgList @('serve') -OutFile (Join-Path $OUT 'msi-serve.log') -WorkDir "$SCRATCH\cwd"
    }
    $proc = $script:proc
    $live = Wait-Live 120 $proc
    Hard 'msi serve (shared data dir) answers /api/live' ([bool]$live)
    $cred2 = Get-Credential-Text $DEFAULT_DATA
    Note ("credential unchanged across the upgrade: {0}" -f ($cred2 -eq $cred))
    $read = $false
    if ($live) {
        $list = Get-Agents $cred2
        $list | Set-Content -Path (Join-Path $OUT 'agents-msi.json') -Encoding utf8
        $read = $list -match 'm32-upgrade-agent'
    }
    Hard 'seeded agent reads back through the MSI install' $read
    if ($proc) { Stop-Tree $proc.Id; Start-Sleep -Seconds 3 }

    # ---- uninstall the MSI; what remains? ---------------------------------------------------------------------------------
    $r = Uninstall-Msi 'over-inno'
    Hard 'msi uninstalls (rc 0 or 3010)' ($r.Rc -eq 0 -or $r.Rc -eq 3010)
    Snapshot-State 'after-msi-uninstall'
    Note ("remaining after the MSI uninstall: inno install={0}, inno ARP entries={1}, msi dir={2}, data dir={3}" -f
        (Test-Path $innoCli), @(Get-UninstallEntries).Count, (Test-Path $EXE), (Test-Path $DEFAULT_DATA))
    $r = Invoke-App $innoCli @('version') 'inno-version-after.txt' 60 @{} @('THE_ONE_DATA_DIR')
    Note ("inno still runs after the MSI uninstall: rc={0}" -f $r.Rc)
}

# ============================================================================================
Note-Header
try {
    if ($Phase -eq 'fresh') { Phase-Fresh } else { Phase-Upgrade }
} catch {
    Note "FAIL unhandled error in phase ${Phase}: $_"
    $script:Fails++
}
Note "== B/$Phase done: $($script:Fails) hard check(s) failed"
if ($script:Fails -gt 0) { exit 1 }
exit 0
