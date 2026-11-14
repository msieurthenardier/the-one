# lifecycle.ps1 - the Windows installer lifecycle driver (Mission 32 Flight 4, leg 3b).
#
# Build-time tooling, run only by .github/workflows/windows-packages.yml (mode=lifecycle) on an
# ephemeral hosted windows-2022 runner, after build.ps1 has built version N and N+1. Never
# imported by the_one/. Writes <Logs>\lifecycle\SUMMARY.txt with rows L1-L11:
#
#   L1 old-to-new        v0.11.8 release installer, then N over it (one entry, same {app}, data kept)
#   L2 install & launch  shortcut, doctor from {app}, window natively visible
#   L3 title bar         GET /api/window/chrome answers (DWM results are INFO)
#   L4 close to tray     WM_CLOSE hides the window, the process lives
#   L5 second launch     one app process remains, the window is shown again
#   L6 geometry          move/resize, quit, relaunch, compare with window-state.json
#   L7 graceful upgrade  N+1 over a running N: quit, poll, KillRunning, then the first copy
#   L8 quit              `the-one.exe quit --wait`
#   L9 uninstall running uninstall while the app runs: the same quit sequence, data kept
#   L10 quit during boot `quit --wait` as soon as /api/live answers: must still drain and exit
#                        (run before L9, which removes the install; see Get-RowPlan)
#   L11 interactive upgrade  N+1 over a running app with the wizard SHOWN, driven by BM_CLICK on
#                        Next/Install/Finish; every pass probes the wizard with WM_NULL (5 s), the
#                        wizard must close within 30 s of Finish, and the %TEMP% Setup log must exist
#                        (v0.12.1: the v0.12.0 wizard froze in the field, all other rows are silent)
#
# Shared helpers (rows, summary, bounded waits, native windows, installers) are in lib.ps1, copied
# from the frozen probe. Every row is seeded "FAIL <id> not-run" and replaced only by the code that
# did its check. "== lifecycle done" is written only on the normal completion path.
#
# Local self test (no Windows API), in a throwaway container:
#   docker run --rm --name m32-pwsh-lifecycle -v "$PWD:/repo:ro" mcr.microsoft.com/powershell:latest \
#     pwsh -NoProfile -File /repo/packaging/windows/lifecycle.ps1 -SelfTest
[CmdletBinding()]
param(
    [string]$Logs = '',
    [string]$VersionN = '',
    [string]$VersionNext = '',
    [string]$InstallerN = '',
    [string]$InstallerNext = '',
    [string]$PythonVersion = '',
    [string]$PyInstallerVersion = '',
    [int]$GlobalSeconds = 3900,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

. (Join-Path $PSScriptRoot 'lib.ps1')

# Script-scope names are case-insensitive: a top-level `$rows` IS `$script:Rows`. Main-section
# variables in this file use the `m` prefix; Test-ScriptScopeCollisions (run by -SelfTest) checks it.
$script:OldVersion = '0.11.8'
$script:MarkerAgent = 'lifecycle-marker'
$script:MarkerFileName = 'lifecycle-marker.txt'
$script:RowIds = @('L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L10', 'L11', 'L9')
$script:Tolerance = 16

# ---------------------------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------------------------
function Write-Header {
    $h = $script:Header
    $h.Add('== windows installer lifecycle (Mission 32 Flight 4, leg 3b)')
    $h.Add("== image: ImageOS=$($env:ImageOS) ImageVersion=$($env:ImageVersion)")
    $ubr = ''
    try { $ubr = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop).UBR } catch { }
    $h.Add("== windows: $([Environment]::OSVersion.VersionString) UBR=$ubr")
    $iscc = 'not found'
    if ($env:M32_ISCC_VERSION) { $iscc = $env:M32_ISCC_VERSION }
    $h.Add("== iscc: $iscc")
    $lua = ''; $consent = ''
    try {
        $pol = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -ErrorAction Stop
        $lua = $pol.EnableLUA; $consent = $pol.ConsentPromptBehaviorAdmin
    } catch { }
    $h.Add("== uac: EnableLUA=$lua ConsentPromptBehaviorAdmin=$consent")
    $elevated = $false
    try { $elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) } catch { }
    $h.Add("== elevated: $elevated")
    $who = ''
    try { $who = (& whoami 2>&1 | Out-String).Trim() } catch { }
    $h.Add("== whoami: $who")
    $h.Add("== python: $PythonVersion   pyinstaller: $PyInstallerVersion")
    $h.Add("== versions: N=$VersionN  N+1=$VersionNext  old release=$($script:OldVersion)")
    if ($script:OnWindows -and -not $SelfTest) {
        try {
            $sc = Get-ScreenAreas
            $h.Add("== screen: union $(Format-Geometry $sc.Union) work area $(Format-Geometry $sc.Work) system DPI $($sc.Dpi)")
        } catch { $h.Add("== screen: unreadable ($($_.Exception.Message))") }
    }
    $h.Add("== drain evidence: uvicorn 'Finished server process [<pid>]' in new bytes of the-one-app.log; watcher resolution 250 ms; global bound ${GlobalSeconds}s; geometry tolerance +-$($script:Tolerance) px")
    Write-Summary
}

# ---------------------------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------------------------
function Get-AppPidByName {
    $p = @(Get-Process -Name 'the-one-app' -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    if ($p.Count -eq 0) { return $null }
    return $p[0]
}

function Wait-MainWindowVisible([int]$TimeoutSec, [string]$What) {
    $script:LastWin = $null
    $script:LastGeo = $null
    $ok = Wait-Until { $w = Get-MainWindow; if ($w -and $w.Visible) { $script:LastWin = $w; return $true } else { return $false } } $TimeoutSec 500 $What
    return $(if ($ok) { $script:LastWin } else { $null })
}

# The normal-case precondition for a quit: the main window natively visible, the route reporting
# visible:true, then a short settle so the page has loaded (a quit during boot is row L10's job).
# Returns the window, or $null (logged) when it never got there.
function Wait-AppReady([int]$TimeoutSec, [string]$What) {
    $w = Wait-MainWindowVisible $TimeoutSec $What
    if (-not $w) { return $null }
    $null = Wait-Until { (Get-RouteVisible).Visible -eq $true } 30 500 "$What route visible:true"
    Start-Sleep -Seconds 6
    return $w
}

function Test-MarkerAgent {
    return ((Invoke-Api GET "/api/agents/$($script:MarkerAgent)").Status -eq 200)
}

function Invoke-ProcessBounded([string]$File, [string[]]$ArgList, [string]$OutName, [int]$TimeoutSec) {
    $o = Join-Path $script:Out $OutName
    $p = Start-Process -FilePath $File -ArgumentList $ArgList -PassThru -NoNewWindow -RedirectStandardOutput $o -RedirectStandardError "$o.err"
    $null = $p.Handle
    $null = $script:Pids.Add($p.Id)
    $done = $p.WaitForExit($TimeoutSec * 1000)
    if (-not $done) {
        Write-Log "$OutName did not finish in ${TimeoutSec}s; killing recorded pid $($p.Id)"
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    $code = $null
    if ($done) { try { $code = $p.ExitCode } catch { $code = $null } }
    return [pscustomobject]@{ Finished = $done; ExitCode = $code; Output = $o }
}

# ---------------------------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------------------------
function Test-RowL1 {
    Write-Log "=== L1: v$($script:OldVersion) -> N, old to new"
    $fails = New-Object System.Collections.Generic.List[string]
    $dl = Join-Path $Logs 'v0118-download'
    New-Item -ItemType Directory -Force -Path $dl | Out-Null
    $repo = if ($env:GITHUB_REPOSITORY) { @('-R', $env:GITHUB_REPOSITORY) } else { @() }
    $dlTxt = Join-Path $dl 'gh-download-output.txt'
    $oldName = "the-one-setup-$($script:OldVersion).exe"
    $ghArgs = @('release', 'download', "v$($script:OldVersion)", '-p', $oldName, '-D', $dl, '--clobber') + $repo
    $dlp = Start-Process -FilePath 'gh' -ArgumentList $ghArgs -PassThru -NoNewWindow -RedirectStandardOutput $dlTxt -RedirectStandardError "$dlTxt.err"
    $null = $dlp.Handle
    $dlPid = $dlp.Id
    $dlDone = $dlp.WaitForExit(120000)
    if (-not $dlDone) {
        Write-Log "gh release download did not finish in 120 s; killing recorded pid $dlPid"
        Stop-Process -Id $dlPid -Force -ErrorAction SilentlyContinue
    }
    Save-Text 'L1-download.txt' ("finished=$dlDone pid=$dlPid`n" + ((Get-Content -LiteralPath $dlTxt, "$dlTxt.err" -ErrorAction SilentlyContinue) -join "`n"))
    $old = Join-Path $dl $oldName
    if (-not ((Test-Path -LiteralPath $old) -and ((Get-Item -LiteralPath $old).Length -gt 1000000))) {
        Set-Row 'L1' 'FAIL' "the v$($script:OldVersion) release download failed"
        return
    }
    Add-Info 'L1' "pre-state: install dir exists=$(Test-Path -LiteralPath $script:InstallDir) data dir exists=$(Test-Path -LiteralPath $script:DataDir) running=$(@(Get-AppPids).Count)"

    $r0 = Invoke-Installer $old 'v0118' 300
    Save-Evidence 'after-v0118'
    if ($r0.ExitCode -ne 0) { $fails.Add("the v$($script:OldVersion) install exit code was $($r0.ExitCode) (timedOut=$($r0.TimedOut))") }
    $locBefore = Get-InstalledLocation
    Add-Info 'L1' "after the old install: DisplayVersion=$(Get-InstalledVersion) InstallLocation=$locBefore"

    $pid0 = Start-App 'v0118'
    $oldVer = Get-ApiVersion
    if ($oldVer -ne $script:OldVersion) { $fails.Add("the old app reported version '$oldVer', not $($script:OldVersion)") }
    $post = Invoke-Api POST '/api/agents' @{ name = $script:MarkerAgent }
    $markerBefore = Test-MarkerAgent
    Set-Content -LiteralPath (Join-Path $script:DataDir $script:MarkerFileName) -Value 'lifecycle marker' -Encoding ASCII
    Add-Info 'L1' "old app: pid=$pid0 version=$oldVer; marker agent POST -> $($post.Status), readable=$markerBefore"
    if (-not $markerBefore) { $fails.Add("the marker agent could not be created or read back (POST $($post.Status)): $($post.Content)") }

    $rN = Invoke-Installer $InstallerN 'N' 300 @{} $pid0
    Save-Evidence 'after-N'
    $alive = [bool](Get-Process -Id $pid0 -ErrorAction SilentlyContinue)
    Add-Info 'L1' "N install over the running old app: exit code $($rN.ExitCode) timedOut=$($rN.TimedOut); old pid $pid0 alive=$alive (the old build has no quit command: the force path is expected)"
    if ($rN.ExitCode -ne 0 -or $rN.TimedOut) { $fails.Add("the N install exit code was $($rN.ExitCode) (timedOut=$($rN.TimedOut))") }
    if ($alive) { $fails.Add("the old pid $pid0 is still alive") }
    $locAfter = Get-InstalledLocation
    $want = $script:InstallDir.TrimEnd('\')
    if (-not $locBefore -or -not $locAfter -or ($locBefore -ne $locAfter) -or ($locAfter -ne $want)) { $fails.Add("InstallLocation changed or is not $want (before '$locBefore', after '$locAfter')") }
    $dv = Get-InstalledVersion
    if ($dv -ne $VersionN) { $fails.Add("DisplayVersion in the }}_is1 key is '$dv', not $VersionN") }
    $entries = Get-UninstallEntryCount
    if ($entries -ne 1) { $fails.Add("$entries uninstall entries match 'GleepGlorp AI', not exactly one") }
    $lnk = @(Get-ProductShortcuts)
    $names = @($lnk | ForEach-Object { Split-Path -Leaf $_ })
    $dups = @($names | Group-Object | Where-Object { $_.Count -gt 1 })
    $mainCount = @($names | Where-Object { $_ -eq 'GleepGlorp AI.lnk' }).Count
    Add-Info 'L1' "uninstall entries=$entries; Start-menu .lnk files: $($lnk -join ', ')"
    if ($dups.Count -gt 0 -or $mainCount -ne 1) { $fails.Add("shortcut check: 'GleepGlorp AI.lnk' count $mainCount, duplicate names $($dups.Count)") }

    Stop-App 'L1-pre-N-launch'
    $pidN = Start-App 'N'
    $verN = Get-ApiVersion
    $markerAfter = Test-MarkerAgent
    $markerFile = Test-Path -LiteralPath (Join-Path $script:DataDir $script:MarkerFileName)
    Add-Info 'L1' "N app: pid=$pidN version=$verN; marker agent present=$markerAfter, marker file present=$markerFile"
    if ($verN -ne $VersionN) { $fails.Add("N's /api/info version is '$verN', not $VersionN") }
    if (-not $markerAfter) { $fails.Add('the marker agent did not survive the upgrade') }
    if (-not $markerFile) { $fails.Add('the marker file did not survive the upgrade') }

    if ($fails.Count -eq 0) { Set-Row 'L1' 'PASS' "v$($script:OldVersion) -> N=${VersionN}: exit 0, old pid $pid0 gone, same {app} $want, one uninstall entry (DisplayVersion $dv), one shortcut set, marker kept, N answers $verN" }
    else { Set-Row 'L1' 'FAIL' ($fails -join '; ') }
}

function Test-RowL2 {
    Write-Log '=== L2: install and launch'
    $fails = New-Object System.Collections.Generic.List[string]
    $lnkPath = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\GleepGlorp AI\GleepGlorp AI.lnk'
    if (-not (Test-Path -LiteralPath $lnkPath)) { $fails.Add("the Start-menu shortcut $lnkPath does not exist") }
    if ((Get-InstalledVersion) -ne $VersionN) { $fails.Add("precondition: the installed version is '$(Get-InstalledVersion)', not $VersionN") }
    Stop-App 'L2-pre'
    $exe = Join-Path $script:InstallDir 'the-one.exe'
    $d = Invoke-ProcessBounded $exe @('doctor') 'doctor.txt' 180
    $dtxt = (Get-Content -LiteralPath $d.Output -ErrorAction SilentlyContinue) -join "`n"
    Add-Info 'L2' "doctor from {app}: finished=$($d.Finished) exit=$($d.ExitCode) RESULT: PASS present=$($dtxt -match 'RESULT: PASS')"
    if (-not $d.Finished -or $d.ExitCode -ne 0 -or $dtxt -notmatch 'RESULT: PASS') { $fails.Add("doctor from {app} did not pass (finished=$($d.Finished), exit=$($d.ExitCode))") }
    $appPid = Start-App 'L2'
    if (-not $appPid) { $fails.Add('the app did not start'); Set-Row 'L2' 'FAIL' ($fails -join '; '); return }
    $w = Wait-MainWindowVisible 60 'L2 visible main window'
    $routeOk = Wait-Until { (Get-RouteVisible).Visible -eq $true } 30 500 'L2 route visible:true'
    $route = Get-RouteVisible
    Save-Text 'windows-L2.txt' ((Get-AllWindows | ForEach-Object { "{0}|pid={1}|visible={2}|{3}|{4}" -f $_.Hwnd, $_.ProcId, $_.Visible, $_.Class, $_.Title }) -join "`r`n")
    Add-Info 'L2' "route /api/window/state -> $($route.Status) $($route.Content)"
    if (-not $w) { $fails.Add('no natively visible main window (owned by an app pid, titled GleepGlorp AI) within 60 s') }
    if (-not $routeOk) { $fails.Add("the route did not report visible:true (status $($route.Status), visible $($route.Visible))") }
    if ($fails.Count -eq 0) { Set-Row 'L2' 'PASS' "Start-menu shortcut present, doctor passed, native window visible (hwnd $($w.Hwnd), pid $($w.ProcId)), route visible:true" }
    else { Set-Row 'L2' 'FAIL' ($fails -join '; ') }
}

function Test-RowL3 {
    Write-Log '=== L3: title bar route'
    $r = Invoke-Api GET '/api/window/chrome'
    $parsed = $null
    try { $parsed = ConvertFrom-Json $r.Content } catch { $parsed = $null }
    Add-Info 'L3' "GET /api/window/chrome -> $($r.Status) $($r.Content) (the DWM results are INFO: Server 2022 reports dark mode only)"
    if ($r.Status -eq 200 -and $null -ne $parsed) { Set-Row 'L3' 'PASS' "GET /api/window/chrome answered 200 with a parseable body ($($r.Content.Length) chars)" }
    else { Set-Row 'L3' 'FAIL' "GET /api/window/chrome returned $($r.Status), parseable=$($null -ne $parsed)" }
}

function Test-RowL4 {
    Write-Log '=== L4: close to tray'
    $fails = New-Object System.Collections.Generic.List[string]
    $w = Get-MainWindow
    if (-not $w -or -not $w.Visible) { Set-Row 'L4' 'FAIL' 'positive control failed: no visible main window to close'; return }
    $appPid = $w.ProcId
    $posted = [M32Win]::PostMessage([IntPtr]$w.Hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)   # WM_CLOSE
    Write-Log "L4: WM_CLOSE posted to hwnd $($w.Hwnd) (pid $appPid) -> $posted"
    $hidden = Wait-Until { $x = @(Get-AllWindows | Where-Object { $_.Hwnd -eq $w.Hwnd }); ($x.Count -eq 0) -or (-not $x[0].Visible) } 10 250 'L4 window hidden'
    $routeHidden = Wait-Until { (Get-RouteVisible).Visible -eq $false } 10 250 'L4 route visible:false'
    $aliveP = [bool](Get-Process -Id $appPid -ErrorAction SilentlyContinue)
    $route = Get-RouteVisible
    Add-Info 'L4' "route after close: $($route.Status) $($route.Content)"
    if (-not $posted) { $fails.Add('PostMessage returned false (positive control)') }
    if (-not $hidden) { $fails.Add('IsWindowVisible stayed true for 10 s after WM_CLOSE') }
    if (-not $routeHidden) { $fails.Add("the route did not report visible:false (status $($route.Status), visible $($route.Visible))") }
    if (-not $aliveP) { $fails.Add("pid $appPid is gone: the app exited instead of closing to the tray") }
    if ($fails.Count -eq 0) { Set-Row 'L4' 'PASS' "WM_CLOSE to hwnd $($w.Hwnd): natively hidden, route visible:false, pid $appPid alive" }
    else { Set-Row 'L4' 'FAIL' ($fails -join '; ') }
}

function Test-RowL5 {
    Write-Log '=== L5: second launch'
    $fails = New-Object System.Collections.Generic.List[string]
    $first = Get-AppPidByName
    if (-not $first) { Set-Row 'L5' 'FAIL' 'precondition: no running app'; return }
    $exe = Join-Path $script:InstallDir 'the-one-app.exe'
    $p2 = Start-Process -FilePath $exe -WorkingDirectory $script:InstallDir -PassThru
    $null = $p2.Handle
    $null = $script:Pids.Add($p2.Id)
    $exited = $p2.WaitForExit(20000)
    $code2 = $null
    if ($exited) { try { $code2 = $p2.ExitCode } catch { $code2 = $null } }
    Add-Info 'L5' "second launch: pid $($p2.Id) exited within 20 s=$exited exit code=$code2 (INFO only)"
    if (-not $exited) {
        Write-Log "L5: the second launch is still running after 20 s; killing recorded pid $($p2.Id)"
        Stop-Process -Id $p2.Id -Force -ErrorAction SilentlyContinue
    }
    $after = @(Get-Process -Name 'the-one-app' -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    if ($after.Count -ne 1 -or $after[0] -ne $first) { $fails.Add("app pids after the second launch: [$($after -join ',')], wanted exactly [$first]") }
    $w = Wait-MainWindowVisible 20 'L5 window visible again'
    $routeOk = Wait-Until { (Get-RouteVisible).Visible -eq $true } 20 500 'L5 route visible:true'
    if (-not $w) { $fails.Add('the main window was not natively visible again within 20 s') }
    if (-not $routeOk) { $fails.Add('the route did not report visible:true again') }
    if ($fails.Count -eq 0) { Set-Row 'L5' 'PASS' "one app pid remains ($first); window natively visible again, route visible:true" }
    else { Set-Row 'L5' 'FAIL' ($fails -join '; ') }
}

function Test-RowL6 {
    Write-Log '=== L6: geometry'
    $fails = New-Object System.Collections.Generic.List[string]
    $w = Wait-MainWindowVisible 20 'L6 visible main window'
    if (-not $w) { Set-Row 'L6' 'FAIL' 'precondition: no visible main window'; return }
    $appPid = $w.ProcId
    $areas = Get-ScreenAreas
    $target = Get-GeometryTarget $areas.Work
    Add-Info 'L6' "screen union $(Format-Geometry $areas.Union), work area $(Format-Geometry $areas.Work), DPI $($areas.Dpi); target $(Format-Geometry $target)"
    $moved = [M32Win]::Move([IntPtr]$w.Hwnd, $target.X, $target.Y, $target.W, $target.H)
    Start-Sleep -Milliseconds 1500
    $beforeQuit = Get-WindowGeometry $w.Hwnd
    Add-Info 'L6' "SetWindowPos -> $moved; rect before the quit $(Format-Geometry $beforeQuit)"
    if (-not $moved) { $fails.Add('SetWindowPos returned false') }

    $off = Get-FileLen $script:AppLog
    $q = Invoke-QuitCli 'L6'
    $gone = Wait-Until { @(Get-AppPids).Count -eq 0 } 20 250 'L6 processes gone after quit'
    $drained = Wait-Until { (Read-NewBytes $script:AppLog $off).Text -match "Finished server process \[$appPid\]" } 10 250 'L6 drain line'
    if (-not $q.Finished -or $q.ExitCode -ne 0) { $fails.Add("quit --wait did not exit 0 (finished=$($q.Finished), exit=$($q.ExitCode))") }
    if (-not $gone) { $fails.Add('processes remained after quit --wait') }
    if (-not $drained) { $fails.Add("no 'Finished server process [$appPid]' line after the quit") }

    $statePath = Join-Path $script:DataDir 'window-state.json'
    $saved = $null
    try { $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } catch { $saved = $null }
    if ($null -eq $saved) { $fails.Add("$statePath is missing or unparseable after the quit"); Set-Row 'L6' 'FAIL' ($fails -join '; '); return }
    Add-Info 'L6' "window-state.json after the quit: $(Get-Content -LiteralPath $statePath -Raw)"
    $savedGeo = @{ X = $saved.x; Y = $saved.y; W = $saved.width; H = $saved.height }
    Add-Info 'L6' "saved $(Format-Geometry $savedGeo) against the target $(Format-Geometry $target) (INFO; the pass test is the relaunch)"

    $pid2 = Start-App 'L6-relaunch'
    if (-not $pid2) { $fails.Add('the relaunch did not start'); Set-Row 'L6' 'FAIL' ($fails -join '; '); return }
    $w2 = Wait-MainWindowVisible 60 'L6 relaunch visible main window'
    if (-not $w2) { $fails.Add('no visible main window after the relaunch'); Set-Row 'L6' 'FAIL' ($fails -join '; '); return }
    Start-Sleep -Milliseconds 2000
    $actual = $null
    $null = Wait-Until { $mw = Get-MainWindow; if ($mw -and $mw.Visible) { $script:LastGeo = Get-WindowGeometry $mw.Hwnd; return ($null -ne $script:LastGeo) } else { return $false } } 30 500 'L6 relaunch native rect'
    $actual = $script:LastGeo
    if ($null -eq $actual) { $fails.Add('the relaunched main window has no native rectangle after 30 s'); Set-Row 'L6' 'FAIL' ($fails -join '; '); return }
    $expected = Get-ExpectedGeometry $saved $areas.Union
    Add-Info 'L6' "relaunch: native rect $(Format-Geometry $actual); expected after the app's clamps (window_state.py: floor 640x360, clamp to the screen union) $(Format-Geometry $expected); tolerance +-$($script:Tolerance)"
    if (-not (Test-GeometryClose $expected $actual $script:Tolerance)) { $fails.Add("the relaunched rect $(Format-Geometry $actual) is not within $($script:Tolerance) px of $(Format-Geometry $expected)") }
    if ($fails.Count -eq 0) { Set-Row 'L6' 'PASS' "saved $(Format-Geometry $savedGeo), relaunched at $(Format-Geometry $actual) (expected $(Format-Geometry $expected), +-$($script:Tolerance)); quit drained pid $appPid" }
    else { Set-Row 'L6' 'FAIL' ($fails -join '; ') }
}

function Test-RowL7 {
    Write-Log '=== L7: graceful upgrade (N+1 over a running N)'
    $fails = New-Object System.Collections.Generic.List[string]
    $pidN = Get-AppPidByName
    if (-not $pidN) { Set-Row 'L7' 'FAIL' 'precondition: N is not running'; return }
    $pat = @{
        'quit-call'    = @{ Src = 'inno'; Re = 'setup quit-call: ExecAsOriginalUser' }
        'check-present' = @{ Src = 'inno'; Re = 'setup quit-check: present' }
        'check-gone'    = @{ Src = 'inno'; Re = 'setup quit-check: gone' }
        'nothing-left'  = @{ Src = 'inno'; Re = 'setup quit-check: nothing left' }
        'killrunning'  = @{ Src = 'inno'; Re = 'setup quit-killrunning: calling' }
        'first-copy'   = @{ Src = 'inno'; Re = 'Dest filename:' }
        'drain'        = @{ Src = 'app'; Re = "Finished server process \[$pidN\]" }
    }
    $r = Invoke-Installer $InstallerNext 'Next' 300 $pat $pidN
    Save-Evidence 'after-Next'
    $ev = $r.Events
    $order = ($ev.GetEnumerator() | Sort-Object Value | ForEach-Object { "$($_.Name)@$($_.Value)ms" }) -join ' < '
    Add-Info 'L7' "N+1=$VersionNext exit code $($r.ExitCode) timedOut=$($r.TimedOut); observed order (+-250 ms): $order"
    $lines = Get-KeyLines $r.InnoText 'quit-call|quit-check|quit-killrunning|Dest filename:|taskkill'
    Save-Text 'L7-inno-key-lines.txt' ($lines -join "`r`n")
    Save-Text 'L7-app-log-new-bytes.txt' $r.AppText
    $seq = @('setup quit-call: ExecAsOriginalUser', 'setup quit-check: present', 'setup quit-check: gone', 'setup quit-check: nothing left','setup quit-killrunning: calling', 'Dest filename:')
    $ord = Test-LogOrder $r.InnoText $seq
    if (-not $ord.Ok) { $fails.Add("the /LOG sequence quit, present, gone, nothing left, KillRunning, first copy failed: $($ord.Why)") }
    if (-not $ev.ContainsKey('drain')) { $fails.Add("no 'Finished server process [$pidN]' line in the new app-log bytes: N was not drained") }
    elseif ($ev.ContainsKey('first-copy') -and $ev['drain'] -gt $ev['first-copy']) { $fails.Add('the drain line was first seen after the first file copy') }
    if ($r.TimedOut -or $r.ExitCode -ne 0) { $fails.Add("the installer did not finish cleanly (exit $($r.ExitCode), timedOut=$($r.TimedOut))") }
    $dv = Get-InstalledVersion
    if ($dv -ne $VersionNext) { $fails.Add("DisplayVersion is '$dv', not $VersionNext") }
    Stop-App 'L7-pre-launch'
    $pidX = Start-App 'Next'
    $verX = Get-ApiVersion
    $marker = Test-MarkerAgent
    Add-Info 'L7' "N+1 app: pid=$pidX version=$verX; marker agent present=$marker; DisplayVersion=$dv"
    if ($verX -ne $VersionNext) { $fails.Add("N+1's /api/info version is '$verX', not $VersionNext") }
    if (-not $marker) { $fails.Add('the marker agent is gone after the upgrade') }
    if ($fails.Count -eq 0) { Set-Row 'L7' 'PASS' "quit, present, gone, nothing left, KillRunning, first copy in order; N pid $pidN drained before the first copy; N+1 answers $verX; DisplayVersion $dv; marker kept" }
    else { Set-Row 'L7' 'FAIL' ($fails -join '; ') }
}

function Test-RowL8 {
    Write-Log '=== L8: quit'
    $fails = New-Object System.Collections.Generic.List[string]
    $appPid = Get-AppPidByName
    if (-not $appPid) { Set-Row 'L8' 'FAIL' 'precondition: the app is not running'; return }
    $ready = Wait-AppReady 60 'L8 ready'
    if (-not $ready) { Set-Row 'L8' 'FAIL' 'precondition: the main window is not natively visible'; return }
    $off = Get-FileLen $script:AppLog
    $q = Invoke-QuitCli 'L8'
    $gone = Wait-Until { @(Get-AppPids).Count -eq 0 } 20 250 'L8 processes gone'
    $drained = Wait-Until { (Read-NewBytes $script:AppLog $off).Text -match "Finished server process \[$appPid\]" } 10 250 'L8 drain line'
    if (-not $q.Finished -or $q.ExitCode -ne 0) { $fails.Add("quit --wait did not exit 0 (finished=$($q.Finished), exit=$($q.ExitCode))") }
    if (-not $drained) { $fails.Add("no 'Finished server process [$appPid]' line after the quit") }
    if (-not $gone) { $fails.Add("processes left: $((@(Get-AppPids)) -join ',')") }
    if ($fails.Count -eq 0) { Set-Row 'L8' 'PASS' "quit --wait exit 0, drain line for pid $appPid, no process left" }
    else { Set-Row 'L8' 'FAIL' ($fails -join '; ') }
}

function Test-RowL10 {
    Write-Log '=== L10: quit during boot'
    $fails = New-Object System.Collections.Generic.List[string]
    Stop-App 'L10-pre'
    $appPid = Start-App 'L10'
    if (-not $appPid) { Set-Row 'L10' 'FAIL' 'precondition: the app did not start'; return }
    # no ready wait: the quit goes in as soon as /api/live answers, while the window is still booting
    $off = $script:LogOffset
    $q = Invoke-QuitCli 'L10'
    $gone = Wait-Until { @(Get-AppPids).Count -eq 0 } 20 250 'L10 processes gone'
    $drained = Wait-Until { (Read-NewBytes $script:AppLog $off).Text -match "Finished server process \[$appPid\]" } 10 250 'L10 drain line'
    if (-not $q.Finished -or $q.ExitCode -ne 0) { $fails.Add("quit --wait during boot did not exit 0 within the bound (finished=$($q.Finished), exit=$($q.ExitCode))") }
    if (-not $drained) { $fails.Add("no 'Finished server process [$appPid]' line after the quit during boot") }
    if (-not $gone) { $fails.Add("processes left: $((@(Get-AppPids)) -join ',')") }
    if ($fails.Count -eq 0) { Set-Row 'L10' 'PASS' "quit --wait during boot exit 0, drain line for pid $appPid, no process left" }
    else { Set-Row 'L10' 'FAIL' ($fails -join '; ') }
}

function Test-RowL11 {
    Write-Log '=== L11: interactive upgrade (the wizard driven by clicks)'
    # The v0.12.0 field defect: the wizard froze while the quit step ran and the Finish page took
    # no input. Every other row installs silently, so none of them saw it. This row runs N+1 over
    # the running app WITHOUT /VERYSILENT and /LOG (so SetupLogging writes the %TEMP% log) and
    # presses Next / Install / Finish with BM_CLICK, probing the wizard window with WM_NULL
    # (SMTO_ABORTIFHUNG, 5 s) on every pass: a wizard that is not pumping messages fails the row.
    # The post-install "Launch" box is left ticked, so the app is started the way a user gets it.
    $fails = New-Object System.Collections.Generic.List[string]
    Stop-App 'L11-pre'
    $appPid = Start-App 'L11'
    if (-not $appPid) { Set-Row 'L11' 'FAIL' 'precondition: the app did not start'; return }
    if (-not (Wait-AppReady 60 'L11 ready')) { Set-Row 'L11' 'FAIL' 'precondition: the main window is not natively visible'; return }
    $off = Get-FileLen $script:AppLog
    $t0 = Get-Date
    $p = Start-Process -FilePath $InstallerNext -ArgumentList @('/NORESTART') -PassThru
    $null = $p.Handle
    $null = $script:Pids.Add($p.Id)
    Write-Log "L11: started the interactive installer, recorded pid $($p.Id)"
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    $deadline = (Get-Date).AddSeconds(360)
    $clicks = New-Object System.Collections.Generic.List[string]
    $lastClickSig = $null
    $lastClickAt = $null
    $slowest = 0
    $finishAt = $null
    $seenWizard = $false
    while ((Get-Date) -lt $deadline -and -not (Test-PastDeadline)) {
        $w = Get-WizardWindow
        if (-not $w) {
            if ($p.HasExited -and $seenWizard) { break }
            if ($p.HasExited -and $clock.Elapsed.TotalSeconds -gt 20) { break }
            Start-Sleep -Milliseconds 500
            continue
        }
        $seenWizard = $true
        $probe = [System.Diagnostics.Stopwatch]::StartNew()
        $answered = [M32Win]::Responsive([IntPtr]$w.Hwnd, 5000)
        if ($probe.ElapsedMilliseconds -gt $slowest) { $slowest = $probe.ElapsedMilliseconds }
        if (-not $answered) {
            $fails.Add("the wizard did not answer WM_NULL within 5 s at $([int]$clock.Elapsed.TotalSeconds) s (not pumping messages: a frozen wizard)")
            break
        }
        $ctl = @(Get-ChildControls $w.Hwnd)
        $btn = @(Get-WizardButtons $ctl)
        $sig = (($ctl | Where-Object { $_.Visible } | ForEach-Object { "$($_.Class):$($_.Text):$([int]$_.Enabled)" }) -join ';')
        if ($btn.Count -gt 0 -and $sig -ne $lastClickSig) {
            $pick = $btn[0]
            foreach ($mWant in @('Finish', 'Install', 'Next')) {
                $hit = @($btn | Where-Object { (($_.Text -replace '[&<>\s]', '')) -eq $mWant })
                if ($hit.Count -gt 0) { $pick = $hit[0]; break }
            }
            $word = ($pick.Text -replace '[&<>\s]', '')
            $clicks.Add("$word@$([int]$clock.Elapsed.TotalSeconds)s")
            Write-Log "L11: clicking '$($pick.Text)' (hwnd $($pick.Hwnd)); controls: $sig"
            $null = [M32Win]::PostMessage([IntPtr]$pick.Hwnd, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero)   # BM_CLICK
            $lastClickSig = $sig
            $lastClickAt = Get-Date
            if ($word -eq 'Finish') { $finishAt = Get-Date; break }
        }
        elseif ($btn.Count -gt 0 -and $sig -eq $lastClickSig -and ((Get-Date) - $lastClickAt).TotalSeconds -gt 15) {
            $fails.Add("the click at $($clicks[$clicks.Count - 1]) was not acted on within 15 s (the page and its buttons are unchanged)")
            break
        }
        Start-Sleep -Milliseconds 500
    }
    Add-Info 'L11' "clicks: $($clicks -join ', '); slowest WM_NULL answer ${slowest} ms; wizard seen=$seenWizard"
    Save-Evidence 'L11-after-wizard'
    if (-not $finishAt -and $fails.Count -eq 0) { $fails.Add("the wizard never reached a pressable Finish within 360 s (clicks: $($clicks -join ', '))") }
    if ($finishAt) {
        $closed = Wait-Until { (-not (Get-WizardWindow)) -and $p.HasExited } 30 250 'L11 wizard exit after Finish'
        $afterMs = [int](((Get-Date) - $finishAt).TotalMilliseconds)
        Add-Info 'L11' "wizard gone and installer exited $afterMs ms after the Finish click (bound 30000); closed=$closed"
        if (-not $closed) { $fails.Add('the wizard did not close within 30 s of the Finish click') }
    }
    if (-not $p.HasExited) {
        Write-Log "L11: installer did not exit; killing recorded pid $($p.Id)"
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    else {
        $code = $null
        try { $code = $p.ExitCode } catch { $code = $null }
        Add-Info 'L11' "installer exit code $code"
        if ($finishAt -and $code -ne 0) { $fails.Add("the installer exit code is $code, not 0") }
    }

    # the quit evidence: the app drained, and the Setup log (SetupLogging) shows the sequence
    $drained = Wait-Until { (Read-NewBytes $script:AppLog $off).Text -match "Finished server process \[$appPid\]" } 10 250 'L11 drain line'
    if (-not $drained) { $fails.Add("no 'Finished server process [$appPid]' line: the running app was not drained") }
    $logs = @(Get-ChildItem -LiteralPath $env:TEMP -Filter 'Setup Log *.txt' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $t0.AddSeconds(-5) } | Sort-Object LastWriteTime)
    if ($logs.Count -eq 0) { $fails.Add("no 'Setup Log *.txt' newer than the start in $($env:TEMP) (SetupLogging=yes)") }
    else {
        $setupLog = $logs[$logs.Count - 1]
        $text = Get-Content -LiteralPath $setupLog.FullName -Raw -ErrorAction SilentlyContinue
        if ($null -eq $text) { $text = '' }
        Add-Info 'L11' "setup log $($setupLog.Name) ($($setupLog.Length) bytes)"
        Save-Text 'L11-setup-log-key-lines.txt' ((Get-KeyLines $text 'quit-call|quit-check|quit-killrunning|Dest filename:|taskkill') -join "`r`n")
        $ord = Test-LogOrder $text @('setup quit-call:', 'setup quit-check: nothing left','setup quit-killrunning: calling', 'Dest filename:')
        if (-not $ord.Ok) { $fails.Add("the Setup log sequence quit, nothing left, KillRunning, first copy failed: $($ord.Why)") }
    }

    # the new app: the "Launch" box was left ticked, so it should be up; start it if not (INFO)
    $live = Wait-Until { (Invoke-Api GET '/api/live' -NoAuth -TimeoutSec 3).Status -eq 200 } 60 1000 'L11 launched by Finish'
    if (-not $live) {
        Add-Info 'L11' 'the app was not started by the Finish page within 60 s; starting it'
        $null = Start-App 'L11-after'
    }
    foreach ($i in (Get-AppPids)) { $null = $script:Pids.Add($i) }
    $ver = Get-ApiVersion
    $marker = Test-MarkerAgent
    $dv = Get-InstalledVersion
    Add-Info 'L11' "after: launched by Finish=$live; /api/info version=$ver; DisplayVersion=$dv; marker present=$marker"
    if ($ver -ne $VersionNext) { $fails.Add("/api/info version is '$ver', not $VersionNext") }
    if ($dv -ne $VersionNext) { $fails.Add("DisplayVersion is '$dv', not $VersionNext") }
    if (-not $marker) { $fails.Add('the marker agent is gone after the interactive upgrade') }
    if ($fails.Count -eq 0) { Set-Row 'L11' 'PASS' "clicks $($clicks -join ', '), every probe answered (slowest $slowest ms), wizard closed after Finish, pid $appPid drained, Setup log in TEMP, $ver answers, marker kept" }
    else { Set-Row 'L11' 'FAIL' ($fails -join '; ') }
}

function Test-RowL9 {
    Write-Log '=== L9: uninstall while running'
    $fails = New-Object System.Collections.Generic.List[string]
    Stop-App 'L9-pre'
    $appPid = Start-App 'L9'
    if (-not $appPid) { Set-Row 'L9' 'FAIL' 'precondition: the app did not start'; return }
    if (-not (Wait-AppReady 60 'L9 ready')) { Set-Row 'L9' 'FAIL' 'precondition: the main window is not natively visible'; return }
    $appOff = $script:LogOffset
    $unins = Join-Path $script:InstallDir 'unins000.exe'
    if (-not (Test-Path -LiteralPath $unins)) { Set-Row 'L9' 'FAIL' "$unins does not exist"; return }
    $logPath = Join-Path $script:Out 'inno-uninstall.log'
    Remove-Item -LiteralPath $logPath -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $unins -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', "/LOG=$logPath") -PassThru
    $null = $p.Handle
    $null = $script:Pids.Add($p.Id)
    # the uninstaller re-spawns a temp copy and exits at once: do not wait on its pid
    $dirGone = Wait-Until { -not (Test-Path -LiteralPath $script:InstallDir) } 240 1000 'L9 {app} gone'
    $keyGone = Wait-Until { -not (Test-Path -LiteralPath $script:UninstallKey) } 60 1000 'L9 uninstall key gone'
    $logClosed = Wait-Until { (Get-Content -LiteralPath $logPath -Raw -ErrorAction SilentlyContinue) -match '(?i)log closed' } 30 1000 'L9 /LOG final line'
    Save-Evidence 'after-uninstall'
    $innoText = ''
    try { $innoText = [string](Get-Content -LiteralPath $logPath -Raw -ErrorAction Stop) } catch { $innoText = '' }
    $lines = Get-KeyLines $innoText 'quit-call|quit-check|quit-killrunning|taskkill|Log closed'
    Save-Text 'L9-inno-key-lines.txt' ($lines -join "`r`n")
    $appText = (Read-NewBytes $script:AppLog $appOff).Text
    Save-Text 'L9-app-log-new-bytes.txt' $appText
    Add-Info 'L9' "uninstaller pid $($p.Id) has exited=$($p.HasExited); /LOG final line seen=$logClosed; key lines (first 14 of $($lines.Count)): $(($lines | Select-Object -First 14) -join ' || ')"
    $seq = @('uninstall quit-call: Exec ', 'uninstall quit-check: present', 'uninstall quit-check: gone', 'uninstall quit-check: nothing left', 'uninstall quit-killrunning: calling')
    $ord = Test-LogOrder $innoText $seq
    if (-not $ord.Ok) { $fails.Add("the uninstall /LOG quit sequence failed: $($ord.Why)") }
    if ($appText -notmatch "Finished server process \[$appPid\]") { $fails.Add("no 'Finished server process [$appPid]' line in the new app-log bytes: the app was not drained") }
    if (-not $dirGone) { $fails.Add('{app} still exists') }
    if (-not $keyGone) { $fails.Add('the }}_is1 uninstall key still exists') }
    $left = @(Get-AppPids)
    if ($left.Count -gt 0) { $fails.Add("processes left: $($left -join ',')") }
    $dataKept = Test-Path -LiteralPath $script:DataDir
    $markerKept = Test-Path -LiteralPath (Join-Path $script:DataDir $script:MarkerFileName)
    $dbs = @(Get-ChildItem -LiteralPath $script:DataDir -Filter '*.db' -ErrorAction SilentlyContinue)
    Add-Info 'L9' "data dir kept=$dataKept marker file kept=$markerKept databases=$(($dbs | ForEach-Object { $_.Name }) -join ',')"
    if (-not $dataKept -or -not $markerKept -or $dbs.Count -eq 0) { $fails.Add("the data dir or its marker was not kept (dir=$dataKept, marker=$markerKept, dbs=$($dbs.Count))") }
    if ($fails.Count -eq 0) { Set-Row 'L9' 'PASS' "uninstall quit sequence logged in order, pid $appPid drained, {app} gone, key gone, no process left, data dir and marker kept" }
    else { Set-Row 'L9' 'FAIL' ($fails -join '; ') }
}

# ---------------------------------------------------------------------------------------------
# The row plan and the runner
# ---------------------------------------------------------------------------------------------
function Get-RowPlan {
    return @(
        @{ Id = 'L1'; Fn = { Test-RowL1 } },
        @{ Id = 'L2'; Fn = { Test-RowL2 } },
        @{ Id = 'L3'; Fn = { Test-RowL3 } },
        @{ Id = 'L4'; Fn = { Test-RowL4 } },
        @{ Id = 'L5'; Fn = { Test-RowL5 } },
        @{ Id = 'L6'; Fn = { Test-RowL6 } },
        @{ Id = 'L7'; Fn = { Test-RowL7 } },
        @{ Id = 'L8'; Fn = { Test-RowL8 } },
        # L10 runs before L9: the uninstall removes the install every other row needs
        @{ Id = 'L10'; Fn = { Test-RowL10 } },
        # L11 also needs the install: it runs the wizard over it, after L10 and before L9
        @{ Id = 'L11'; Fn = { Test-RowL11 } },
        @{ Id = 'L9'; Fn = { Test-RowL9 } }
    )
}

# Runs each row; a row that throws keeps a FAIL with the reason. Sets Completed only when the
# loop ends normally (a throw outside a row propagates to the caller, which writes the aborted line).
function Invoke-RowPlan($Plan) {
    foreach ($mRow in $Plan) {
        if (Test-PastDeadline) { Write-Log "global bound reached; $($mRow.Id) stays not-run"; continue }
        try { & $mRow.Fn }
        catch {
            $why = Get-AbortText $_
            Write-Log "row $($mRow.Id) threw: $why"
            # the bookkeeping below must never take the whole run down
            try { Add-Info $mRow.Id "harness exception: $why" } catch { Write-Log "Add-Info failed: $($_.Exception.Message)" }
            try {
                if ($script:Rows[$mRow.Id] -like '* not-run') { Set-Row $mRow.Id 'FAIL' "not-run (the row threw: $($_.Exception.Message))" }
            } catch { Write-Log "Set-Row failed: $($_.Exception.Message)" }
        }
    }
    $script:Completed = $true
}

# ---------------------------------------------------------------------------------------------
# Self test (Linux pwsh, no Windows-only API)
# ---------------------------------------------------------------------------------------------
function Invoke-SelfTest {
    $fails = New-Object System.Collections.Generic.List[string]
    $check = {
        param([bool]$Cond, [string]$What)
        if ($Cond) { Write-Host "ok   $What" } else { Write-Host "FAIL $What"; $fails.Add($What) }
    }
    $scratch = Join-Path ([System.IO.Path]::GetTempPath()) ('m32-lifecycle-selftest-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $scratch | Out-Null

    # the shared helpers: hygiene, collisions, rows, bounds, readers, geometry (lib.ps1)
    $libFails = Invoke-LibSelfTest $scratch @((Join-Path $PSScriptRoot 'lib.ps1'), $PSCommandPath)
    foreach ($f in $libFails) { $fails.Add("lib: $f") }

    # this file's own contract
    Initialize-Lib $scratch 'lifecycle' $script:RowIds 600
    & $check (($script:RowIds -join ',') -eq 'L1,L2,L3,L4,L5,L6,L7,L8,L10,L11,L9') 'the rows are L1 to L8, L10, L11, L9 in run order'
    & $check (((Get-RowPlan | ForEach-Object { $_.Id }) -join ',') -eq ($script:RowIds -join ',')) 'the plan runs every row once, in order'
    foreach ($e in (Get-RowPlan)) {
        & $check ($null -ne (Get-Command "Test-Row$($e.Id)" -ErrorAction SilentlyContinue)) "a function Test-Row$($e.Id) exists"
    }
    & $check ($script:UninstallKey.EndsWith('}}_is1')) 'the lifecycle reads the }}_is1 key'
    & $check ($script:Tolerance -eq 16) 'the geometry tolerance is 16 px'
    $script:Header = New-Object System.Collections.Generic.List[string]
    Write-Header
    $s = @(Get-Content -LiteralPath $script:SummaryPath)
    & $check (@($s | Where-Object { $_ -like 'FAIL L* not-run' }).Count -eq 11) 'the header write leaves eleven rows FAIL not-run'
    & $check ($s[0] -like '== windows installer lifecycle*') 'header first line'
    & $check (($s -join "`n") -notmatch 'lifecycle done|lifecycle aborted') 'a running summary has neither done nor aborted'

    # the runner: a row that throws keeps a FAIL with its reason, the others run, the end is "done"
    $fake = @(
        @{ Id = 'L1'; Fn = { Set-Row 'L1' 'PASS' 'fine' } },
        @{ Id = 'L2'; Fn = { throw 'boom in L2' } },
        @{ Id = 'L3'; Fn = { Set-Row 'L3' 'FAIL' 'a real failure' } }
    )
    Invoke-RowPlan $fake
    $script:Done = $true
    Write-Summary
    $s = @(Get-Content -LiteralPath $script:SummaryPath)
    & $check ($s -contains 'PASS L1 fine') 'the runner: a passing row lands'
    & $check (@($s -match '^FAIL L2 not-run \(the row threw: boom in L2\)').Count -eq 1) 'the runner: a throwing row keeps a FAIL with its reason'
    & $check (@($s | Where-Object { $_ -like 'INFO L2 harness exception:*' }).Count -eq 1) 'the runner: the exception is recorded as INFO'
    & $check ($s -contains 'FAIL L3 a real failure') 'the runner: a failing row stays FAIL'
    & $check (@($s | Where-Object { $_ -like 'FAIL L4 not-run' }).Count -eq 1) 'the runner: rows outside the plan stay not-run'
    & $check ($s[-1] -eq '== lifecycle done') 'the runner: the normal path ends with the done marker'

    # past the global bound: rows stay not-run, the loop still completes
    Initialize-Lib $scratch 'lifecycle' $script:RowIds 600
    $script:Deadline = (Get-Date).AddSeconds(-1)
    Invoke-RowPlan @(@{ Id = 'L1'; Fn = { Set-Row 'L1' 'PASS' 'should not run' } })
    & $check ($script:Rows['L1'] -eq 'FAIL L1 not-run') 'the bound: a row past the deadline is not run'

    # the abort path: no done line, every row still shows, the reason names the failure
    Initialize-Lib $scratch 'lifecycle' $script:RowIds 600
    $script:Header = New-Object System.Collections.Generic.List[string]
    Write-Header
    try { Set-Row 'L99' 'PASS' 'x' } catch { $script:AbortReason = Get-AbortText $_ }
    $script:Done = $true
    Write-Summary
    $s = @(Get-Content -LiteralPath $script:SummaryPath)
    $ab = @($s | Where-Object { $_ -like '== lifecycle aborted:*' })
    & $check ($ab.Count -eq 1 -and $ab[0] -match "unknown row id 'L99'") 'abort path: one aborted line naming the failure'
    & $check (@($s | Where-Object { $_ -like 'FAIL L* not-run' }).Count -eq 11) 'abort path: all eleven rows still show FAIL not-run'
    & $check (($s -join "`n") -notmatch 'lifecycle done') 'abort path: no done line'

    Remove-Item -Recurse -Force -LiteralPath $scratch -ErrorAction SilentlyContinue
    Write-Host ''
    if ($fails.Count -gt 0) {
        Write-Host "SELFTEST FAILED ($($fails.Count)):"
        $fails | ForEach-Object { Write-Host "  $_" }
        return $false
    }
    Write-Host 'SELFTEST PASSED'
    return $true
}

# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------
if ($SelfTest) {
    $mSelfOk = $false
    try { $mSelfOk = Invoke-SelfTest } catch { Write-Host "SELFTEST CRASHED: $($_.Exception.Message) $($_.InvocationInfo.PositionMessage)" }
    if ($mSelfOk) { exit 0 } else { exit 1 }
}

foreach ($mReq in @('Logs', 'VersionN', 'VersionNext', 'InstallerN', 'InstallerNext')) {
    if (-not (Get-Variable -Name $mReq -ValueOnly)) { throw "lifecycle.ps1: -$mReq is required (or pass -SelfTest)" }
}
# the global bound is relative to the job start (M32_T0): see lib.ps1 for the arithmetic
$GlobalSeconds = Get-EffectiveGlobalSeconds $GlobalSeconds $env:M32_T0 ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
Initialize-Lib $Logs 'lifecycle' $script:RowIds $GlobalSeconds
Initialize-Win32
try {
    Write-Header
    Invoke-RowPlan (Get-RowPlan)
}
catch {
    $script:AbortReason = Get-AbortText $_
    Write-Log "lifecycle aborted: $($script:AbortReason)"
    throw
}
finally {
    try { Stop-App 'finally' } catch { }
    try { Save-Evidence 'end' } catch { }
    try { if (Test-Path -LiteralPath $script:AppLog) { Copy-Item -LiteralPath $script:AppLog -Destination (Join-Path $script:Out 'the-one-app.log') -Force } } catch { }
    $script:Done = $true
    if (-not $script:Completed -and -not $script:AbortReason) { $script:AbortReason = 'ended before the normal completion path' }
    try { Write-Summary } catch { Write-Log "final Write-Summary failed: $(Get-AbortText $_)" }
}
