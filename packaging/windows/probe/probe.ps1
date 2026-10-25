# probe.ps1 - the Windows premise probe (Mission 32 Flight 4, leg 1).
#
# Build-time tooling, run only by .github/workflows/windows-packages.yml (mode=probe) on an
# ephemeral hosted windows-2022 runner. Never imported by the_one/. Answers premises W1-W6 and
# writes <Logs>\probe\SUMMARY.txt. See packaging/windows/probe/README.md for what each row means.
#
# Rules this script keeps:
#   * every W row is seeded "FAIL <id> not-run" and is replaced only by the code path that did its
#     check (Set-Row throws on an unknown id);
#   * window truth is NATIVE (EnumWindows + IsWindowVisible), never the state route's `visible`;
#   * log reads take only the bytes added after a recorded offset (FileShare.ReadWrite);
#   * every wait is bounded and logs its own timeout; the whole probe has a global bound;
#   * only pids this script recorded are ever killed (the runner is ephemeral, but the rule holds).
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Logs,
    [Parameter(Mandatory = $true)][string]$VersionN,
    [Parameter(Mandatory = $true)][string]$VersionQ,
    [Parameter(Mandatory = $true)][string]$VersionR,
    [Parameter(Mandatory = $true)][string]$InstallerN,
    [Parameter(Mandatory = $true)][string]$InstallerQ,
    [Parameter(Mandatory = $true)][string]$InstallerR,
    [string]$IsccPath = '',
    [string]$PythonVersion = '',
    [string]$PyInstallerVersion = '',
    [int]$GlobalSeconds = 2100
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------------------------
$script:Out = Join-Path $Logs 'probe'
New-Item -ItemType Directory -Force -Path $script:Out | Out-Null
$script:SummaryPath = Join-Path $script:Out 'SUMMARY.txt'
$script:LogPath = Join-Path $script:Out 'probe.log'
# The global bound is also relative to the job start: M32_T0 (epoch seconds, set by the workflow's
# Paths step) + 45 minutes, so the probe always ends well before the 60-minute job cap and the
# summary, the log upload and the fail step still run. effective = min(GlobalSeconds, remaining).
$script:JobBoundSeconds = 2700
if ($env:M32_T0 -match '^\d+$') {
    $nowEpoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $remaining = [int]([long]$env:M32_T0 + $script:JobBoundSeconds - $nowEpoch)
    if ($remaining -lt $GlobalSeconds) { $GlobalSeconds = [Math]::Max($remaining, 0) }
}
$script:Deadline = (Get-Date).AddSeconds($GlobalSeconds)
$script:Completed = $false
$script:AbortReason = ''
$script:Clock = [System.Diagnostics.Stopwatch]::StartNew()
$script:Port = 8484
$script:Header = New-Object System.Collections.Generic.List[string]
$script:Infos = New-Object System.Collections.Generic.List[string]
$script:RowOrder = @('W6', 'W1', 'W2', 'W5', 'W4', 'W3')
$script:Rows = [ordered]@{}
foreach ($id in $script:RowOrder) { $script:Rows[$id] = "FAIL $id not-run" }
$script:Pids = New-Object System.Collections.Generic.HashSet[int]
$script:InstallDir = Join-Path $env:ProgramFiles 'GleepGlorp AI'
$script:DataDir = Join-Path $env:LOCALAPPDATA 'the-one'
$script:AppLog = Join-Path $script:DataDir 'logs\the-one-app.log'
$script:CredPath = Join-Path $script:DataDir 'api-credential'
$script:UninstallKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{CAEEFB46-2698-4048-AD9F-0120D0B7174A}_is1'
$script:Done = $false

function Write-Log([string]$Msg) {
    $line = '{0:0000.0}s {1}' -f ($script:Clock.ElapsedMilliseconds / 1000.0), $Msg
    Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Write-Summary {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($h in $script:Header) { $lines.Add($h) }
    $lines.Add('')
    foreach ($id in $script:RowOrder) { $lines.Add([string]$script:Rows[$id]) }
    foreach ($i in $script:Infos) { $lines.Add($i) }
    if ($script:Completed) { $lines.Add('== probe done') }
    elseif ($script:Done) { $lines.Add("== probe aborted: $($script:AbortReason)") }
    Set-Content -LiteralPath $script:SummaryPath -Value $lines -Encoding UTF8
}

function Set-Row([string]$Id, [string]$Status, [string]$Text) {
    if (-not $script:Rows.Contains($Id)) { throw "Set-Row: unknown row id '$Id'" }
    if (@('PASS', 'FAIL', 'INFO') -notcontains $Status) { throw "Set-Row: bad status '$Status'" }
    $script:Rows[$Id] = "$Status $Id $Text"
    Write-Log "ROW $Status $Id $Text"
    Write-Summary
}

function Add-Info([string]$Id, [string]$Text) {
    if (-not $script:Rows.Contains($Id)) { throw "Add-Info: unknown row id '$Id'" }
    $script:Infos.Add("INFO $Id $Text")
    Write-Log "INFO $Id $Text"
    Write-Summary
}

function Test-PastDeadline { return ((Get-Date) -gt $script:Deadline) }

# Bounded poll. Returns $true when the condition held, $false on timeout or the global bound.
function Wait-Until([scriptblock]$Cond, [int]$TimeoutSec, [int]$IntervalMs = 500, [string]$What = '') {
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ($true) {
        $ok = $false
        try { $ok = [bool](& $Cond) } catch { $ok = $false }
        if ($ok) { return $true }
        if ((Get-Date) -gt $end) { Write-Log "wait timed out after ${TimeoutSec}s: $What"; return $false }
        if (Test-PastDeadline) { Write-Log "global bound reached while waiting: $What"; return $false }
        Start-Sleep -Milliseconds $IntervalMs
    }
}

function Save-Text([string]$Name, [string]$Text) {
    Set-Content -LiteralPath (Join-Path $script:Out $Name) -Value $Text -Encoding UTF8
}

function Save-Evidence([string]$Tag) {
    try { (& tasklist /V 2>&1 | Out-String) | Set-Content -LiteralPath (Join-Path $script:Out "tasklist-$Tag.txt") -Encoding UTF8 } catch { }
    try {
        $reg = Join-Path $script:Out "uninstall-$Tag.txt"
        $roots = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')
        $acc = New-Object System.Collections.Generic.List[string]
        foreach ($r in $roots) {
            if (Test-Path $r) {
                foreach ($k in Get-ChildItem $r -ErrorAction SilentlyContinue) {
                    $p = Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue
                    if ($p -and ($p.DisplayName -like '*GleepGlorp*')) {
                        $acc.Add("$($k.Name) :: DisplayName=$($p.DisplayName) DisplayVersion=$($p.DisplayVersion) InstallLocation=$($p.InstallLocation)")
                    }
                }
            }
        }
        Set-Content -LiteralPath $reg -Value $acc -Encoding UTF8
    } catch { }
}

# ---------------------------------------------------------------------------------------------
# Native helpers: windows, screenshots
# ---------------------------------------------------------------------------------------------
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class M32Win {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string c, string t);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    public static string[] Windows() {
        List<string> acc = new List<string>();
        EnumProc cb = delegate (IntPtr h, IntPtr l) {
            uint pid; GetWindowThreadProcessId(h, out pid);
            StringBuilder t = new StringBuilder(512); GetWindowText(h, t, 512);
            StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256);
            acc.Add(h.ToInt64() + "|" + pid + "|" + (IsWindowVisible(h) ? 1 : 0) + "|" + c + "|" + t);
            return true;
        };
        EnumWindows(cb, IntPtr.Zero);
        return acc.ToArray();
    }
}
'@
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

# every top-level window: objects with Hwnd, ProcId, Visible, Class, Title
function Get-AllWindows {
    $res = @()
    foreach ($l in [M32Win]::Windows()) {
        $p = $l.Split('|', 5)
        if ($p.Count -ge 5) {
            $res += [pscustomobject]@{ Hwnd = [int64]$p[0]; ProcId = [int]$p[1]; Visible = ($p[2] -eq '1'); Class = $p[3]; Title = $p[4] }
        }
    }
    return $res
}

function Get-AppWindows {
    $ids = @(Get-AppPids)
    return @(Get-AllWindows | Where-Object { $ids -contains $_.ProcId })
}

# the main window: owned by an app pid, titled GleepGlorp AI (visible or not)
function Get-MainWindow {
    $w = @(Get-AppWindows | Where-Object { $_.Title -like 'GleepGlorp AI*' })
    if ($w.Count -eq 0) { return $null }
    $vis = @($w | Where-Object { $_.Visible })   # prefer a visible one when several match
    if ($vis.Count -gt 0) { return $vis[0] }
    return $w[0]
}

function Save-Screenshot([string]$Name) {
    # returns @{ Ok; Stddev; Path; Error }
    $path = Join-Path $script:Out $Name
    try {
        $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
        if ($b.Width -le 0 -or $b.Height -le 0) { return [pscustomobject]@{ Ok = $false; Stddev = 0.0; Path = $path; Error = "empty virtual screen ($($b.Width)x$($b.Height))" } }
        $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
        $g.Dispose()
        $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        # pixel variance on a coarse grid (luminance); a flat or all-black screen is ~0
        $n = 0; $sum = 0.0; $sum2 = 0.0
        $stepX = [Math]::Max(1, [int]($bmp.Width / 64)); $stepY = [Math]::Max(1, [int]($bmp.Height / 48))
        for ($y = 0; $y -lt $bmp.Height; $y += $stepY) {
            for ($x = 0; $x -lt $bmp.Width; $x += $stepX) {
                $c = $bmp.GetPixel($x, $y)
                $lum = 0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B
                $n++; $sum += $lum; $sum2 += $lum * $lum
            }
        }
        $bmp.Dispose()
        $mean = $sum / [Math]::Max(1, $n)
        $sd = [Math]::Sqrt([Math]::Max(0.0, $sum2 / [Math]::Max(1, $n) - $mean * $mean))
        return [pscustomobject]@{ Ok = $true; Stddev = [Math]::Round($sd, 2); Path = $path; Error = '' }
    } catch {
        return [pscustomobject]@{ Ok = $false; Stddev = 0.0; Path = $path; Error = "$($_.Exception.Message)" }
    }
}

# ---------------------------------------------------------------------------------------------
# Files: new bytes only
# ---------------------------------------------------------------------------------------------
function Get-FileLen([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return [long]0 }
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        try { return [long]$fs.Length } finally { $fs.Dispose() }
    } catch { return [long]0 }
}

function Read-NewBytes([string]$Path, [long]$Offset) {
    $res = [pscustomobject]@{ Text = ''; Offset = $Offset }
    if (-not (Test-Path -LiteralPath $Path)) { return $res }
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        try {
            $len = $fs.Length
            if ($len -lt $Offset) { $Offset = 0 }
            $null = $fs.Seek($Offset, 'Begin')
            $n = [int]($len - $Offset)
            $buf = New-Object byte[] $n
            $read = 0
            while ($read -lt $n) {
                $k = $fs.Read($buf, $read, $n - $read)
                if ($k -le 0) { break }
                $read += $k
            }
            $res.Text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $read)
            $res.Offset = $Offset + $read
        } finally { $fs.Dispose() }
    } catch { Write-Log "Read-NewBytes failed for ${Path}: $($_.Exception.Message)" }
    return $res
}

function Get-KeyLines([string]$Text, [string]$Regex) {
    $out = New-Object System.Collections.Generic.List[string]
    $i = 0
    foreach ($l in ($Text -split "`r?`n")) {
        $i++
        if ($l -match $Regex) { $out.Add(("{0}: {1}" -f $i, $l.Trim())) }
    }
    return $out
}

# ---------------------------------------------------------------------------------------------
# The app and the API
# ---------------------------------------------------------------------------------------------
function Get-AppPids {
    return @(Get-Process -Name 'the-one-app', 'the-one' -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

function Get-Cred {
    if (-not (Test-Path -LiteralPath $script:CredPath)) { return $null }
    try { return (Get-Content -LiteralPath $script:CredPath -Raw).Trim() } catch { return $null }
}

function Invoke-Api([string]$Method, [string]$Path, $Body = $null, [switch]$NoAuth, [int]$TimeoutSec = 10) {
    # Invoke-WebRequest, not Invoke-RestMethod: the status code is the evidence (404 vs 200)
    $uri = "http://127.0.0.1:$($script:Port)$Path"
    $h = @{}
    if (-not $NoAuth) {
        $c = Get-Cred
        if ($c) { $h['Authorization'] = "Bearer $c" }
    }
    try {
        $p = @{ Uri = $uri; Method = $Method; Headers = $h; TimeoutSec = $TimeoutSec; UseBasicParsing = $true; SkipHttpErrorCheck = $true }
        if ($null -ne $Body) { $p['Body'] = ($Body | ConvertTo-Json -Compress); $p['ContentType'] = 'application/json' }
        $r = Invoke-WebRequest @p
        return [pscustomobject]@{ Status = [int]$r.StatusCode; Content = [string]$r.Content }
    } catch {
        return [pscustomobject]@{ Status = 0; Content = "$($_.Exception.Message)" }
    }
}

function Get-ApiVersion {
    $r = Invoke-Api GET '/api/info'
    if ($r.Status -ne 200) { return "http-$($r.Status)" }
    try { return [string]((ConvertFrom-Json $r.Content).version) } catch { return 'unparseable' }
}

# Launch the installed windowed app; returns the pid of the primary the-one-app process, or $null.
function Start-App([string]$Tag) {
    $exe = Join-Path $script:InstallDir 'the-one-app.exe'
    if (-not (Test-Path -LiteralPath $exe)) { Write-Log "Start-App($Tag): $exe does not exist"; return $null }
    $script:LogOffset = Get-FileLen $script:AppLog
    $p = Start-Process -FilePath $exe -WorkingDirectory $script:InstallDir -PassThru
    $null = $script:Pids.Add($p.Id)
    $null = Wait-Until { @(Get-AppPids).Count -gt 0 } 15 500 "Start-App($Tag) process visible"
    foreach ($i in (Get-AppPids)) { $null = $script:Pids.Add($i) }
    $live = Wait-Until { (Invoke-Api GET '/api/live' -NoAuth -TimeoutSec 3).Status -eq 200 } 90 1000 "Start-App($Tag) /api/live"
    $cred = Wait-Until { Test-Path -LiteralPath $script:CredPath } 60 500 "Start-App($Tag) credential file"
    if (-not $cred) {
        # evidence for a wrong data-dir guess
        $found = @(Get-ChildItem -Path $env:LOCALAPPDATA -Recurse -Depth 3 -Filter 'api-credential' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
        Write-Log "credential file not at $($script:CredPath); found: $($found -join ', ')"
    }
    $app = @(Get-Process -Name 'the-one-app' -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    Write-Log "Start-App($Tag): pid(s) $($app -join ',') live=$live credential=$cred"
    if ($app.Count -eq 0) { return $null }
    return $app[0]
}

# Kill only the pids this script recorded (and only while they are still a the-one process).
function Stop-App([string]$Tag) {
    foreach ($id in @($script:Pids)) {
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($p -and ($p.ProcessName -like 'the-one*')) {
            Write-Log "Stop-App($Tag): killing recorded pid $id ($($p.ProcessName))"
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        }
    }
    $null = Wait-Until { @(Get-AppPids).Count -eq 0 } 15 500 "Stop-App($Tag) processes gone"
}

# ---------------------------------------------------------------------------------------------
# Installers
# ---------------------------------------------------------------------------------------------
function Get-InstalledVersion {
    if (-not (Test-Path $script:UninstallKey)) { return $null }
    try { return [string](Get-ItemProperty $script:UninstallKey).DisplayVersion } catch { return $null }
}

# Run an installer silently, bounded. Returns @{ ExitCode; TimedOut; Pid; Log; Events; InnoText; AppText }
# Events maps a name to the first-seen time (ms on the probe clock, +-250 ms) of a pattern in the
# Inno /LOG ('inno') or the NEW bytes of the app log ('app'). 'proc-exit' is the watched pid's exit.
function Invoke-Installer([string]$Installer, [string]$Name, [int]$TimeoutSec, [hashtable]$Patterns = @{}, [int]$WatchPid = 0) {
    $logPath = Join-Path $script:Out "inno-$Name.log"
    Remove-Item -LiteralPath $logPath -ErrorAction SilentlyContinue
    $appOff = Get-FileLen $script:AppLog
    $events = @{}
    $innoText = ''
    $appText = ''
    Write-Log "installer($Name): starting $Installer (bound ${TimeoutSec}s)"
    $p = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$logPath") -PassThru
    $null = $p.Handle   # cache the handle so ExitCode is readable after exit
    $null = $script:Pids.Add($p.Id)
    $startMs = $script:Clock.ElapsedMilliseconds
    $timedOut = $false
    $final = $false
    while ($true) {
        $ms = $script:Clock.ElapsedMilliseconds
        $inno = Read-NewBytes $logPath 0
        $innoText = $inno.Text
        $app = Read-NewBytes $script:AppLog $appOff
        $appOff = $app.Offset
        $appText += $app.Text
        foreach ($k in $Patterns.Keys) {
            if (-not $events.ContainsKey($k)) {
                $src = if ($Patterns[$k].Src -eq 'inno') { $innoText } else { $appText }
                if ($src -match $Patterns[$k].Re) { $events[$k] = $ms; Write-Log "event($Name): $k at ${ms}ms" }
            }
        }
        if ($WatchPid -gt 0 -and -not $events.ContainsKey('proc-exit')) {
            if (-not (Get-Process -Id $WatchPid -ErrorAction SilentlyContinue)) { $events['proc-exit'] = $ms; Write-Log "event($Name): proc-exit at ${ms}ms" }
        }
        if ($final) { break }
        if ($p.HasExited) { $final = $true; continue }   # one more pass over the logs
        if ((($ms - $startMs) / 1000.0) -gt $TimeoutSec -or (Test-PastDeadline)) {
            $timedOut = $true
            Write-Log "installer($Name): did not finish in ${TimeoutSec}s; killing recorded pid $($p.Id)"
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            $final = $true
            continue
        }
        Start-Sleep -Milliseconds 250
    }
    $code = $null
    try { $code = $p.ExitCode } catch { $code = $null }
    Write-Log "installer($Name): exit code $code timedOut=$timedOut"
    Save-Text "events-$Name.txt" (($events.GetEnumerator() | Sort-Object Value | ForEach-Object { "{0,8} ms  {1}" -f $_.Value, $_.Name }) -join "`r`n")
    return [pscustomobject]@{ ExitCode = $code; TimedOut = $timedOut; Pid = $p.Id; Log = $logPath; Events = $events; InnoText = $innoText; AppText = $appText }
}

# ---------------------------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------------------------
function Write-Header {
    $h = $script:Header
    $h.Add('== windows premise probe (Mission 32 Flight 4, leg 1)')
    $h.Add("== image: ImageOS=$($env:ImageOS) ImageVersion=$($env:ImageVersion)")
    $ubr = ''
    try { $ubr = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').UBR } catch { }
    $h.Add("== windows: $([Environment]::OSVersion.VersionString) UBR=$ubr")
    $iscc = 'not found'
    if ($IsccPath -and (Test-Path -LiteralPath $IsccPath)) {
        # The workflow resolves the version best-effort (FileVersion can read 0.0.0.0) and exports it.
        if ($env:M32_ISCC_VERSION) { $iscc = $env:M32_ISCC_VERSION } else { $iscc = 'unknown (M32_ISCC_VERSION not set)' }
    }
    $h.Add("== iscc: $iscc")
    $lua = ''; $consent = ''
    try {
        $pol = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
        $lua = $pol.EnableLUA; $consent = $pol.ConsentPromptBehaviorAdmin
    } catch { }
    $h.Add("== uac: EnableLUA=$lua ConsentPromptBehaviorAdmin=$consent")
    $elevated = $false
    try { $elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) } catch { }
    $h.Add("== elevated: $elevated")
    $h.Add("== whoami: $((& whoami 2>&1 | Out-String).Trim())")
    $h.Add("== python: $PythonVersion   pyinstaller: $PyInstallerVersion")
    $h.Add("== versions: N=$VersionN  N+1 (quit variant)=$VersionQ  N+2 (RM variant)=$VersionR")
    $h.Add("== drain evidence: uvicorn 'Finished server process [<pid>]' in new bytes of the-one-app.log; watcher resolution 250 ms; global bound ${GlobalSeconds}s")
    Write-Summary
}

# ---------------------------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------------------------
function Test-RowW6 {
    Write-Log '=== W6: v0.11.8 -> N, old to new'
    $fails = New-Object System.Collections.Generic.List[string]
    $dl = Join-Path $Logs 'v0118-download'
    New-Item -ItemType Directory -Force -Path $dl | Out-Null
    $repo = if ($env:GITHUB_REPOSITORY) { @('-R', $env:GITHUB_REPOSITORY) } else { @() }
    $dlTxt = Join-Path $dl 'gh-download-output.txt'
    $ghArgs = @('release', 'download', 'v0.11.8', '-p', 'the-one-setup-0.11.8.exe', '-D', $dl, '--clobber') + $repo
    $dlp = Start-Process -FilePath 'gh' -ArgumentList $ghArgs -PassThru -NoNewWindow -RedirectStandardOutput $dlTxt -RedirectStandardError "$dlTxt.err"
    $null = $dlp.Handle
    $dlPid = $dlp.Id
    $dlDone = $dlp.WaitForExit(120000)
    if (-not $dlDone) {
        Write-Log "gh release download did not finish in 120 s; killing recorded pid $dlPid"
        Stop-Process -Id $dlPid -Force -ErrorAction SilentlyContinue
    }
    $dlOut = "finished=$dlDone pid=$dlPid`n" + ((Get-Content -LiteralPath $dlTxt, "$dlTxt.err" -ErrorAction SilentlyContinue) -join "`n")
    $old = Join-Path $dl 'the-one-setup-0.11.8.exe'
    $dlOk = (Test-Path -LiteralPath $old) -and ((Get-Item -LiteralPath $old).Length -gt 1000000)
    Save-Text 'W6-download.txt' $dlOut
    if (-not $dlOk) { $fails.Add('the v0.11.8 download failed'); Set-Row 'W6' 'FAIL' ($fails -join '; '); return }

    Add-Info 'W6' "pre-state: install dir exists=$(Test-Path $script:InstallDir) data dir exists=$(Test-Path $script:DataDir) running=$(@(Get-AppPids).Count)"
    $r0 = Invoke-Installer $old 'v0118' 300
    Save-Evidence 'after-v0118'
    if ($r0.ExitCode -ne 0) { $fails.Add("the v0.11.8 install exit code was $($r0.ExitCode) (timedOut=$($r0.TimedOut))") }
    $dirBefore = if (Test-Path $script:InstallDir) { @(Get-ChildItem $script:InstallDir -Recurse -File -ErrorAction SilentlyContinue).Count } else { 0 }
    Add-Info 'W6' "install dir before the upgrade: $($script:InstallDir), $dirBefore files, DisplayVersion=$(Get-InstalledVersion)"

    # the old app: launched by the probe (silent mode skips the post-install launch)
    $pid0 = Start-App 'v0118'
    $oldVer = Get-ApiVersion
    $st = Invoke-Api GET '/api/window/state'
    Add-Info 'W6' "old app: pid=$pid0 /api/info version=$oldVer /api/window/state status=$($st.Status)"
    if ($oldVer -ne '0.11.8') { $fails.Add("the old app reported version '$oldVer', not 0.11.8") }
    if ($st.Status -ne 404) { $fails.Add("/api/window/state returned $($st.Status), not 404 (the positive control that this is the old app)") }

    # the data marker
    $post = Invoke-Api POST '/api/agents' @{ name = 'probe-marker' }
    $get = Invoke-Api GET '/api/agents/probe-marker'
    Add-Info 'W6' "data marker before the upgrade: POST /api/agents -> $($post.Status) $($post.Content.Substring(0, [Math]::Min(200, $post.Content.Length))); GET -> $($get.Status)"
    $markerBefore = ($get.Status -eq 200)
    if (-not $markerBefore) { $fails.Add("the data marker could not be created or read back (POST $($post.Status), GET $($get.Status)): $($post.Content)") }

    # N over the running v0.11.8 (today's KillRunning is the expected force path: recorded, not failed)
    $rN = Invoke-Installer $InstallerN 'N' 300 @{} $pid0
    Save-Evidence 'after-N'
    $alive = [bool](Get-Process -Id $pid0 -ErrorAction SilentlyContinue)
    Add-Info 'W6' "N install over the running v0.11.8: exit code $($rN.ExitCode) timedOut=$($rN.TimedOut); old pid $pid0 still alive=$alive"
    $force = Get-KeyLines $rN.InnoText '(?i)taskkill|the-one-app|restart manager|closing|applications'
    Add-Info 'W6' "force-path evidence in the /LOG ($($force.Count) lines, see inno-N.log): $(($force | Select-Object -First 8) -join ' || ')"
    if ($rN.ExitCode -ne 0) { $fails.Add("the N install exit code was $($rN.ExitCode) (timedOut=$($rN.TimedOut))") }
    $dv = Get-InstalledVersion
    Add-Info 'W6' "after the upgrade: DisplayVersion=$dv (want $VersionN)"
    if ($dv -ne $VersionN) { $fails.Add("DisplayVersion is '$dv', not $VersionN") }
    $dirAfter = if (Test-Path $script:InstallDir) { @(Get-ChildItem $script:InstallDir -Recurse -File -ErrorAction SilentlyContinue).Count } else { 0 }
    $entries = 0
    foreach ($root in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
        if (Test-Path $root) {
            foreach ($k in Get-ChildItem $root -ErrorAction SilentlyContinue) {
                $pp = Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue
                if ($pp -and $pp.DisplayName -like '*GleepGlorp AI*') { $entries++ }
            }
        }
    }
    $lnk = @(Get-ChildItem -Path "$env:ProgramData\Microsoft\Windows\Start Menu\Programs", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like '*GleepGlorp*' } | ForEach-Object { $_.FullName })
    Add-Info 'W6' "install dir after: $($script:InstallDir), $dirAfter files; uninstall entries matching 'GleepGlorp AI': $entries; Start-menu .lnk files: $($lnk -join ', ')"

    # N launched: /api/window/state must answer 200, and the marker must have survived
    Stop-App 'W6-pre-N-launch'
    $pidN = Start-App 'N'
    $st2 = Invoke-Api GET '/api/window/state'
    $verN = Get-ApiVersion
    Add-Info 'W6' "N app: pid=$pidN /api/info version=$verN (an unstaged build reports __version__, not N) /api/window/state status=$($st2.Status)"
    if ($st2.Status -ne 200) { $fails.Add("/api/window/state returned $($st2.Status), not 200, on the N app") }
    $get2 = Invoke-Api GET '/api/agents/probe-marker'
    Add-Info 'W6' "data marker after the upgrade survives=$($get2.Status -eq 200) (GET -> $($get2.Status))"

    if ($fails.Count -eq 0) { Set-Row 'W6' 'PASS' "v0.11.8 installed (rc 0), answered as the old app (version 0.11.8, window/state 404), N=$VersionN installed over it (rc 0), DisplayVersion=$dv, window/state 200 on N" }
    else { Set-Row 'W6' 'FAIL' ($fails -join '; ') }
}

function Test-RowW1 {
    Write-Log '=== W1: window'
    Stop-App 'W1-start'
    Save-Evidence 'W1-before'
    $offset = Get-FileLen $script:AppLog
    $script:W1Offset = $offset
    $appPid = Start-App 'W1'
    $fails = New-Object System.Collections.Generic.List[string]
    if (-not $appPid) { Set-Row 'W1' 'FAIL' 'the app did not start'; return }
    $found = $null
    $null = Wait-Until { $w = Get-MainWindow; if ($w -and $w.Visible) { $script:W1Win = $w; return $true } else { return $false } } 60 1000 'W1 visible main window'
    $found = $script:W1Win
    $all = Get-AllWindows
    Save-Text 'windows-W1.txt' (($all | ForEach-Object { "{0}|pid={1}|visible={2}|{3}|{4}" -f $_.Hwnd, $_.ProcId, $_.Visible, $_.Class, $_.Title }) -join "`r`n")
    $tray = [M32Win]::FindWindow('Shell_TrayWnd', $null)
    Add-Info 'W1' "window enumeration saved (windows-W1.txt, $($all.Count) top-level windows); Shell_TrayWnd=$($tray -ne [IntPtr]::Zero)"
    $route = Invoke-Api GET '/api/window/state'
    Add-Info 'W1' "route /api/window/state -> $($route.Status) $($route.Content) (INFO only: the route's visible is tracked_visible, not native truth)"
    $shot = Save-Screenshot 'W1-screen.png'
    Add-Info 'W1' "screenshot ok=$($shot.Ok) pixel stddev=$($shot.Stddev) $($shot.Error) -> W1-screen.png"
    $titled = @($all | Where-Object { $_.Title -like 'GleepGlorp AI*' -and (@(Get-AppPids) -contains $_.ProcId) })
    if (-not $found) { $fails.Add('no visible main window (EnumWindows, owned by an app pid, titled GleepGlorp AI) within 60 s') }
    if ($titled.Count -eq 0) { $fails.Add('no window titled GleepGlorp AI exists') }
    if (-not $shot.Ok) { $fails.Add("screenshot failed: $($shot.Error)") }
    elseif ($shot.Stddev -le 3.0) { $fails.Add("screenshot is flat (pixel stddev $($shot.Stddev) <= 3.0): no painted desktop") }
    if ($fails.Count -eq 0) { Set-Row 'W1' 'PASS' "native IsWindowVisible true for hwnd $($found.Hwnd) ('$($found.Title)', pid $($found.ProcId)); screenshot pixel stddev $($shot.Stddev)" }
    else { Set-Row 'W1' 'FAIL' ($fails -join '; ') }
}

function Test-RowW2 {
    Write-Log '=== W2: tray'
    $exe = Join-Path $script:InstallDir 'the-one.exe'
    $doctorOut = Join-Path $script:Out 'doctor.txt'
    $doctorErr = Join-Path $script:Out 'doctor-err.txt'
    $dp = Start-Process -FilePath $exe -ArgumentList 'doctor' -PassThru -NoNewWindow -RedirectStandardOutput $doctorOut -RedirectStandardError $doctorErr
    $null = $dp.Handle
    if (-not $dp.WaitForExit(180000)) { Write-Log 'doctor did not finish in 180 s; killing recorded pid'; Stop-Process -Id $dp.Id -Force -ErrorAction SilentlyContinue }
    $trayLine = @(Get-Content -LiteralPath $doctorOut -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*tray:' })
    Add-Info 'W2' "doctor tray: line (static text on Windows, INFO only): $($trayLine -join ' / ') (doctor exit $($dp.ExitCode))"
    $tray = [M32Win]::FindWindow('Shell_TrayWnd', $null)
    $trayPresent = ($tray -ne [IntPtr]::Zero)
    $new = Read-NewBytes $script:AppLog $script:W1Offset
    $unavail = ($new.Text -match 'System tray unavailable')
    Save-Text 'W2-app-log-new-bytes.txt' $new.Text
    if ($trayPresent -and -not $unavail) { Set-Row 'W2' 'PASS' "Shell_TrayWnd present and no 'System tray unavailable' line in the new app-log bytes since launch" }
    else { Set-Row 'W2' 'FAIL' "Shell_TrayWnd present=$trayPresent; 'System tray unavailable' in new app-log bytes=$unavail" }
}

function Test-RowW5 {
    Write-Log '=== W5: close to tray'
    $fails = New-Object System.Collections.Generic.List[string]
    $w = Get-MainWindow
    if (-not $w -or -not $w.Visible) {
        Add-Info 'W5' 'precondition: no visible main window; relaunching'
        Stop-App 'W5-pre'
        $null = Start-App 'W5'
        $null = Wait-Until { $x = Get-MainWindow; if ($x -and $x.Visible) { $script:W5Win = $x; return $true } else { return $false } } 60 1000 'W5 visible main window'
        $w = $script:W5Win
    }
    if (-not $w) { Set-Row 'W5' 'FAIL' 'positive control failed: no visible main window to close'; return }
    $appPid = $w.ProcId
    $posted = [M32Win]::PostMessage([IntPtr]$w.Hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)   # WM_CLOSE
    Write-Log "W5: WM_CLOSE posted to hwnd $($w.Hwnd) (pid $appPid) -> $posted"
    $hidden = Wait-Until { $x = @(Get-AllWindows | Where-Object { $_.Hwnd -eq $w.Hwnd }); ($x.Count -eq 0) -or (-not $x[0].Visible) } 10 250 'W5 window hidden'
    $aliveP = [bool](Get-Process -Id $appPid -ErrorAction SilentlyContinue)
    $route = Invoke-Api GET '/api/window/state'
    Add-Info 'W5' "route after close: $($route.Status) $($route.Content) (INFO only: tracked_visible never clears on Windows, fixed in leg 2)"
    $shot = Save-Screenshot 'W5-after-close.png'
    Add-Info 'W5' "screenshot after close: ok=$($shot.Ok) stddev=$($shot.Stddev)"
    if (-not $posted) { $fails.Add('PostMessage returned false (positive control)') }
    if (-not $hidden) { $fails.Add('IsWindowVisible stayed true for 10 s after WM_CLOSE') }
    if (-not $aliveP) { $fails.Add("pid $appPid is gone: the app exited instead of closing to the tray") }
    if ($fails.Count -eq 0) { Set-Row 'W5' 'PASS' "WM_CLOSE to hwnd $($w.Hwnd) (visible before, post ok): window hidden within 10 s, pid $appPid alive" }
    else { Set-Row 'W5' 'FAIL' ($fails -join '; ') }
}

function Test-RowW4 {
    Write-Log '=== W4: graceful quit'
    $fails = New-Object System.Collections.Generic.List[string]
    # --- positive control: the quit CLI alone
    Stop-App 'W4-pre'
    $pidA = Start-App 'W4-control'
    $exe = Join-Path $script:InstallDir 'the-one.exe'
    $off = Get-FileLen $script:AppLog
    if (-not $pidA) { $fails.Add('positive control: the app did not start') }
    else {
        $qOut = Join-Path $script:Out 'W4-quit-cli.txt'
        $qp = Start-Process -FilePath $exe -ArgumentList @('quit', '--wait') -PassThru -NoNewWindow -RedirectStandardOutput $qOut
        $null = $qp.Handle
        $qdone = $qp.WaitForExit(100000)
        if (-not $qdone) { Stop-Process -Id $qp.Id -Force -ErrorAction SilentlyContinue }
        $gone = Wait-Until { -not (Get-Process -Id $pidA -ErrorAction SilentlyContinue) } 10 250 'W4 control pid gone'
        $drained = Wait-Until { (Read-NewBytes $script:AppLog $off).Text -match "Finished server process \[$pidA\]" } 10 250 'W4 control drain line'
        $newTxt = (Read-NewBytes $script:AppLog $off).Text
        Save-Text 'W4-control-app-log-new-bytes.txt' $newTxt
        Add-Info 'W4' "control: quit --wait finished=$qdone output='$((Get-Content -LiteralPath $qOut -ErrorAction SilentlyContinue) -join ' / ')'; pid $pidA gone=$gone; drain line 'Finished server process [$pidA]'=$drained"
        if (-not $qdone -or -not $gone) { $fails.Add("control: the pid did not exit through quit --wait (finished=$qdone gone=$gone)") }
        if (-not $drained) { $fails.Add("control: no 'Finished server process [$pidA]' line in the new app-log bytes (the drain evidence is not observable)") }
    }
    Stop-App 'W4-control-end'

    # --- the quit variant's N+1 installer over a running app
    $pidB = Start-App 'W4-installer'
    if (-not $pidB) { $fails.Add('installer run: the app did not start'); Set-Row 'W4' 'FAIL' ($fails -join '; '); return }
    $pat = @{
        'quit-call'    = @{ Src = 'inno'; Re = 'quit-call: ExecAsOriginalUser' }
        'poll-present' = @{ Src = 'inno'; Re = 'quit-poll: present' }
        'poll-gone'    = @{ Src = 'inno'; Re = 'quit-poll: gone' }
        'nothing-left' = @{ Src = 'inno'; Re = 'quit-poll: nothing left' }
        'killrunning'  = @{ Src = 'inno'; Re = 'quit-killrunning: calling' }
        'first-copy'   = @{ Src = 'inno'; Re = 'Dest filename:' }
        'drain'        = @{ Src = 'app'; Re = "Finished server process \[$pidB\]" }
        'shutdown'     = @{ Src = 'app'; Re = 'Application shutdown complete\.' }
    }
    $r = Invoke-Installer $InstallerQ 'Q' 240 $pat $pidB
    Save-Evidence 'after-Q'
    $ev = $r.Events
    $order = ($ev.GetEnumerator() | Sort-Object Value | ForEach-Object { "$($_.Name)@$($_.Value)ms" }) -join ' < '
    Add-Info 'W4' "installer N+1=$VersionQ exit code $($r.ExitCode) timedOut=$($r.TimedOut); observed order (+-250 ms): $order"
    $lines = Get-KeyLines $r.InnoText 'quit-call|quit-poll|quit-killrunning|Dest filename:|taskkill'
    Save-Text 'W4-inno-key-lines.txt' ($lines -join "`r`n")
    Add-Info 'W4' "the /LOG's key lines (first 14 of $($lines.Count)): $(($lines | Select-Object -First 14) -join ' || ')"
    Save-Text 'W4-app-log-new-bytes.txt' $r.AppText
    function Get-Idx([string]$Re) { $m = [regex]::Match($r.InnoText, $Re); if ($m.Success) { return $m.Index } else { return -1 } }
    $iPresent = Get-Idx 'quit-poll: present'; $iGone = Get-Idx 'quit-poll: gone'; $iNone = Get-Idx 'quit-poll: nothing left'
    $iKill = Get-Idx 'quit-killrunning: calling'; $iCopy = Get-Idx 'Dest filename:'
    if ($iPresent -lt 0) { $fails.Add("the /LOG has no 'quit-poll: present': the poll would have passed vacuously") }
    if ($iGone -lt 0) { $fails.Add("the /LOG has no 'quit-poll: gone'") }
    if ($iPresent -ge 0 -and $iGone -ge 0 -and $iPresent -gt $iGone) { $fails.Add("'gone' was logged before 'present'") }
    if ($iNone -lt 0) { $fails.Add("the /LOG has no 'quit-poll: nothing left before KillRunning' (something was left, or the poll did not complete)") }
    if ($iNone -ge 0 -and $iKill -ge 0 -and $iNone -gt $iKill) { $fails.Add("'nothing left' was logged after KillRunning") }
    if ($iKill -lt 0) { $fails.Add('KillRunning was not logged') }
    if ($iCopy -lt 0) { $fails.Add('no file copy in the /LOG') }
    elseif ($iKill -ge 0 -and $iKill -gt $iCopy) { $fails.Add('the first file copy came before KillRunning') }
    if (-not $ev.ContainsKey('drain')) { $fails.Add("no 'Finished server process [$pidB]' line in the new app-log bytes: the app was not drained") }
    elseif ($ev.ContainsKey('first-copy') -and $ev['drain'] -gt $ev['first-copy']) { $fails.Add('the drain line was first seen after the first file copy') }
    if ($r.TimedOut -or $r.ExitCode -ne 0) { $fails.Add("the installer did not finish cleanly (exit $($r.ExitCode), timedOut=$($r.TimedOut))") }
    Add-Info 'W4' "elevation: runneradmin with UAC off (field-only, DD2); DisplayVersion after=$(Get-InstalledVersion) (want $VersionQ)"
    if ($fails.Count -eq 0) { Set-Row 'W4' 'PASS' "quit call, poll present then gone, nothing left, then KillRunning, then the first copy; drain line for pid $pidB seen before the first copy; control quit --wait drained too" }
    else { Set-Row 'W4' 'FAIL' ($fails -join '; ') }
}

function Test-RowW3 {
    Write-Log '=== W3: the Restart Manager alone'
    Stop-App 'W3-pre'
    $pidC = Start-App 'W3'
    if (-not $pidC) { Add-Info 'W3' 'precondition: the app did not start; the RM variant ran against no running app'; }
    $exePath = Join-Path $script:InstallDir 'the-one.exe'
    $before = if (Test-Path $exePath) { (Get-Item $exePath).LastWriteTimeUtc.ToString('o') } else { 'missing' }
    $pat = @{
        'rm-variant'  = @{ Src = 'inno'; Re = 'rm-variant: PrepareToInstall ran' }
        'first-copy'  = @{ Src = 'inno'; Re = 'Dest filename:' }
        'drain'       = @{ Src = 'app'; Re = "Finished server process \[$pidC\]" }
    }
    $r = Invoke-Installer $InstallerR 'R' 180 $pat ([int]$pidC)
    Save-Evidence 'after-R'
    $after = if (Test-Path $exePath) { (Get-Item $exePath).LastWriteTimeUtc.ToString('o') } else { 'missing' }
    $lines = Get-KeyLines $r.InnoText '(?i)restart manager|closing|applications|rm-variant|taskkill|Starting the installation|Dest filename:|CloseApplications|using one or more files'
    Save-Text 'W3-inno-key-lines.txt' ($lines -join "`r`n")
    Save-Text 'W3-app-log-new-bytes.txt' $r.AppText
    $closed = $r.Events.ContainsKey('proc-exit') -or ($pidC -and -not (Get-Process -Id ([int]$pidC) -ErrorAction SilentlyContinue))
    $graceful = $r.Events.ContainsKey('drain')
    $order = ($r.Events.GetEnumerator() | Sort-Object Value | ForEach-Object { "$($_.Name)@$($_.Value)ms" }) -join ' < '
    Add-Info 'W3' "RM/closing lines in the /LOG (first 14 of $($lines.Count)): $(($lines | Select-Object -First 14) -join ' || ')"
    Add-Info 'W3' "order of PrepareToInstall (rm-variant line) against the first copy and the app's events (+-250 ms): $order"
    Add-Info 'W3' "app closed=$closed gracefully (drain line for pid $pidC)=$graceful; the-one.exe LastWriteTimeUtc before=$before after=$after replaced=$($before -ne $after); DisplayVersion=$(Get-InstalledVersion) (want $VersionR)"
    if ($r.TimedOut) { Add-Info 'W3' 'installer did not finish' }
    Set-Row 'W3' 'INFO' "RM variant N+2=$VersionR installer exit code $($r.ExitCode) timedOut=$($r.TimedOut); app closed=$closed gracefully=$graceful files replaced=$($before -ne $after)"
}

function Test-FinalUninstall {
    Write-Log '=== final: silent uninstall'
    Stop-App 'final'
    $unins = Join-Path $script:InstallDir 'unins000.exe'
    if (-not (Test-Path -LiteralPath $unins)) { Add-Info 'W6' "final uninstall: $unins does not exist"; return }
    $logPath = Join-Path $script:Out 'inno-uninstall.log'
    $p = Start-Process -FilePath $unins -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', "/LOG=$logPath") -PassThru
    $null = $p.Handle
    $null = $script:Pids.Add($p.Id)
    $done = $p.WaitForExit(180000)
    if (-not $done) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    $null = Wait-Until { -not (Test-Path -LiteralPath $script:InstallDir) } 20 500 'final install dir gone'
    Save-Evidence 'after-uninstall'
    Add-Info 'W6' "final uninstall: exit $($p.ExitCode) finished=$done; {app} gone=$(-not (Test-Path $script:InstallDir)); leftover the-one processes=$(@(Get-AppPids).Count); data dir remains=$(Test-Path $script:DataDir); registry key remains=$(Test-Path $script:UninstallKey)"
}

# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------
try {
    Write-Header
    $rows = @(
        @{ Id = 'W6'; Fn = { Test-RowW6 } },
        @{ Id = 'W1'; Fn = { Test-RowW1 } },
        @{ Id = 'W2'; Fn = { Test-RowW2 } },
        @{ Id = 'W5'; Fn = { Test-RowW5 } },
        @{ Id = 'W4'; Fn = { Test-RowW4 } },
        @{ Id = 'W3'; Fn = { Test-RowW3 } }
    )
    foreach ($row in $rows) {
        if (Test-PastDeadline) { Write-Log "global bound reached; $($row.Id) stays not-run"; continue }
        try { & $row.Fn }
        catch {
            Write-Log "row $($row.Id) threw: $($_.Exception.Message)"
            Add-Info $row.Id "harness exception: $($_.Exception.Message) at $($_.InvocationInfo.PositionMessage)"
            # a row that threw before it recorded a result keeps its not-run FAIL; say why
            if ($script:Rows[$row.Id] -like '* not-run') { Set-Row $row.Id 'FAIL' "not-run (the row threw: $($_.Exception.Message))" }
        }
    }
    if (-not (Test-PastDeadline)) { try { Test-FinalUninstall } catch { Write-Log "final uninstall threw: $($_.Exception.Message)" } }
    else { Write-Log 'global bound reached; the final uninstall was skipped' }
    $script:Completed = $true
}
catch {
    $script:AbortReason = "$($_.Exception.Message)"
    Write-Log "probe aborted: $($script:AbortReason)"
    throw
}
finally {
    try { Stop-App 'finally' } catch { }
    try { Save-Evidence 'end' } catch { }
    try { if (Test-Path $script:AppLog) { Copy-Item -LiteralPath $script:AppLog -Destination (Join-Path $script:Out 'the-one-app.log') -Force } } catch { }
    $script:Done = $true
    if (-not $script:Completed -and -not $script:AbortReason) { $script:AbortReason = 'ended before the normal completion path' }
    Write-Summary
}
