# lib.ps1 - shared helpers for the Windows lifecycle driver (Mission 32 Flight 4, leg 3b).
#
# Dot-sourced by packaging/windows/lifecycle.ps1; never run on its own except for its self test:
#   pwsh -NoProfile -File lib.ps1 -SelfTest
# These helpers were copied from packaging/windows/probe/probe.ps1 (frozen: the probe keeps its own
# copy) and extended for the lifecycle rows. Build-time tooling, never imported by the_one/.
#
# Rules this file keeps (leg 1's lessons: two hosted runs were lost to script defects):
#   * rows are seeded "FAIL <id> not-run" and replaced only by the code path that did the check
#     (Set-Row throws on an unknown id); the done line is written only on the normal path;
#   * window truth is NATIVE (EnumWindows + IsWindowVisible), the state route is a second witness;
#   * log reads take only the bytes added after a recorded offset (FileShare.ReadWrite);
#   * every wait is bounded and logs its own timeout; the whole run has a global bound;
#   * only pids this script recorded are ever killed;
#   * the file is ASCII (Windows PowerShell 5.1 reads a BOM-less file as ANSI);
#   * script-scope names are case-insensitive: a top-level `$rows` in a caller IS `$script:Rows`.
#     Callers use the `m` prefix for main-section variables; Test-ScriptScopeCollisions checks it.
#
# State lives in $script: variables set by Initialize-Lib. Because the caller dot-sources this
# file, "script" here is the caller's script scope.

# The Inno uninstall key. The shipped AppId line is `AppId={{CAEEFB46-...}}`; Inno treats the first
# `{{` as an escaped brace, so the effective AppId is `{CAEEFB46-...}}` (TWO closing braces) and the
# key is `{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}_is1`. Leg 1 measured this on the runner; the
# probe's single-brace read was a harness defect.
$script:UninstallKeyPath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}_is1'

# The job's cap is 80 minutes (4800 s). The run must end its own work, summary and upload step
# included, with at least 11 minutes to spare (the probe left 15 of 60): 4800 - 12 * 60 = 4080 s
# from M32_T0 (epoch seconds, set by the workflow's Paths step).
$script:JobBoundSeconds = 4080

function Get-EffectiveGlobalSeconds([int]$Requested, [string]$T0, [long]$NowEpoch) {
    if ($T0 -match '^\d+$') {
        $left = [int]([long]$T0 + $script:JobBoundSeconds - $NowEpoch)
        if ($left -lt $Requested) { return [Math]::Max($left, 0) }
    }
    return $Requested
}

# ---------------------------------------------------------------------------------------------
# State, log, summary, rows
# ---------------------------------------------------------------------------------------------
function Initialize-Lib([string]$Logs, [string]$Title, [string[]]$RowOrder, [int]$GlobalSeconds, [int]$Port = 8484) {
    $script:Out = Join-Path $Logs $Title
    New-Item -ItemType Directory -Force -Path $script:Out | Out-Null
    $script:Title = $Title
    $script:SummaryPath = Join-Path $script:Out 'SUMMARY.txt'
    $script:LogPath = Join-Path $script:Out "$Title.log"
    $script:Deadline = (Get-Date).AddSeconds($GlobalSeconds)
    $script:Completed = $false
    $script:Done = $false
    $script:AbortReason = ''
    $script:Clock = [System.Diagnostics.Stopwatch]::StartNew()
    $script:Port = $Port
    $script:Header = New-Object System.Collections.Generic.List[string]
    $script:Infos = New-Object System.Collections.Generic.List[string]
    $script:RowOrder = $RowOrder
    $script:Rows = [ordered]@{}
    foreach ($id in $script:RowOrder) { $script:Rows[$id] = "FAIL $id not-run" }
    $script:Pids = New-Object System.Collections.Generic.HashSet[int]
    $script:LogOffset = [long]0
    $script:OnWindows = ($PSVersionTable.PSVersion.Major -lt 6) -or $IsWindows
    # the fake directories exist only so a self test can load on Linux; on Windows a missing
    # variable is a hard error
    $pf = $env:ProgramFiles
    $la = $env:LOCALAPPDATA
    if ($script:OnWindows -and -not ($pf -and $la)) { throw 'ProgramFiles or LOCALAPPDATA is not set' }
    if (-not $pf) { $pf = Join-Path $script:Out 'fake-programfiles' }
    if (-not $la) { $la = Join-Path $script:Out 'fake-localappdata' }
    $script:InstallDir = Join-Path $pf 'GleepGlorp AI'
    $script:DataDir = Join-Path $la 'the-one'
    $script:AppLog = Join-Path $script:DataDir 'logs\the-one-app.log'
    $script:CredPath = Join-Path $script:DataDir 'api-credential'
    $script:UninstallKey = $script:UninstallKeyPath
}

function Write-Log([string]$Msg) {
    $line = '{0:0000.0}s {1}' -f ($script:Clock.ElapsedMilliseconds / 1000.0), $Msg
    Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Write-Summary {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($h in $script:Header) { $lines.Add($h) }
    $lines.Add('')
    foreach ($rid in $script:RowOrder) {
        $rv = ''
        if ($script:Rows -is [System.Collections.IDictionary] -and $script:Rows.Contains($rid)) { $rv = [string]$script:Rows[$rid] }
        if (-not $rv) { $rv = "FAIL $rid not-run (the row table lost this row)" }
        $lines.Add($rv)
    }
    foreach ($i in $script:Infos) { $lines.Add($i) }
    if ($script:Completed) { $lines.Add("== $($script:Title) done") }
    elseif ($script:Done) { $lines.Add("== $($script:Title) aborted: $($script:AbortReason)") }
    # LF endings, no BOM: the workflow verdict greps this file with bash anchors
    [IO.File]::WriteAllText($script:SummaryPath, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
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

# one-line abort text: message, then the function/line from PositionMessage, newlines folded
function Get-AbortText($ErrRec) {
    $pos = ''
    try { $pos = [string]$ErrRec.InvocationInfo.PositionMessage } catch { }
    $t = "$($ErrRec.Exception.Message) | $pos"
    return (($t -replace '\s*[\r\n]+\s*', ' | ').Trim())
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

# ---------------------------------------------------------------------------------------------
# Pure helpers (self-tested on Linux)
# ---------------------------------------------------------------------------------------------
# Every regex must match, and the FIRST match of each must come after the first match of the one
# before it. Returns Ok plus the reason (the names of what is missing or out of order).
function Test-LogOrder([string]$Text, [string[]]$Regexes) {
    $idx = @()
    $missing = New-Object System.Collections.Generic.List[string]
    $bad = New-Object System.Collections.Generic.List[string]
    $prev = -1
    foreach ($re in $Regexes) {
        $m = [regex]::Match($Text, $re)
        if (-not $m.Success) { $missing.Add($re); $idx += -1; continue }
        $idx += $m.Index
        if ($m.Index -le $prev) { $bad.Add($re) }
        $prev = $m.Index
    }
    $why = ''
    if ($missing.Count -gt 0) { $why += "missing: $($missing -join ' | ')" }
    if ($bad.Count -gt 0) { $why += " out of order: $($bad -join ' | ')" }
    return [pscustomobject]@{ Ok = ($missing.Count -eq 0 -and $bad.Count -eq 0); Why = $why.Trim(); Indexes = $idx }
}

# Geometry hashtables: X, Y, W, H. True when every value differs by at most $Tol pixels.
function Test-GeometryClose($Expected, $Actual, [int]$Tol) {
    if ($null -eq $Expected -or $null -eq $Actual) { return $false }
    foreach ($k in @('X', 'Y', 'W', 'H')) {
        if ($null -eq $Expected[$k] -or $null -eq $Actual[$k]) { return $false }
        if ([Math]::Abs([int]$Expected[$k] - [int]$Actual[$k]) -gt $Tol) { return $false }
    }
    return $true
}

function Format-Geometry($G) {
    if ($null -eq $G) { return 'none' }
    return ('{0}x{1}@{2},{3}' -f $G['W'], $G['H'], $G['X'], $G['Y'])
}

# What the app restores from a saved window-state.json (the_one/interfaces/desktop/window_state.py):
# apply_floor (width >= 640, height >= 360), then clamp_to_bounds to the union of the screens:
# width/height first, then the top-left into [min, max - size]. $Saved has width/height and
# optionally x/y (a parsed JSON object); $Union is @{X;Y;W;H}. Returns X/Y/W/H (X/Y $null when the
# state had no position).
function Get-ExpectedGeometry($Saved, $Union) {
    $w = [int]$Saved.width
    $h = [int]$Saved.height
    if ($w -lt 640) { $w = 640 }
    if ($h -lt 360) { $h = 360 }
    $w = [Math]::Min($w, [int]$Union.W)
    $h = [Math]::Min($h, [int]$Union.H)
    $x = $null
    $y = $null
    if ($null -ne $Saved.x) { $x = [Math]::Max([int]$Union.X, [Math]::Min([int]$Saved.x, [int]$Union.X + [int]$Union.W - $w)) }
    if ($null -ne $Saved.y) { $y = [Math]::Max([int]$Union.Y, [Math]::Min([int]$Saved.y, [int]$Union.Y + [int]$Union.H - $h)) }
    return @{ X = $x; Y = $y; W = $w; H = $h }
}

# A target rectangle inside a work area (@{X;Y;W;H}): 1000x700 shrunk to leave an 80 px margin,
# never below the window's 640x360 floor, offset 40/30 from the top-left.
function Get-GeometryTarget($Area) {
    $w = [Math]::Max(640, [Math]::Min(1000, [int]$Area.W - 80))
    $h = [Math]::Max(360, [Math]::Min(700, [int]$Area.H - 80))
    return @{ X = [int]$Area.X + 40; Y = [int]$Area.Y + 30; W = $w; H = $h }
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

function Get-FileLen([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return [long]0 }
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        try { return [long]$fs.Length } finally { $fs.Dispose() }
    } catch { return [long]0 }
}

# The bytes added after $Offset only (a log the app holds open for writing).
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

# True when no top-level variable of any of the given files shares a (case-insensitive) name with
# a `$script:` variable of any of them. Returns the list of collisions (empty when clean).
function Test-ScriptScopeCollisions([string[]]$Paths) {
    $scoped = @{}
    $asts = @()
    foreach ($p in $Paths) {
        $tokens = $null; $errs = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$tokens, [ref]$errs)
        if ($errs -and $errs.Count -gt 0) { throw "$p does not parse: $($errs[0].Message)" }
        $asts += , @{ Path = $p; Ast = $ast }
        foreach ($v in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] }, $true)) {
            if ($v.VariablePath.IsScript) { $scoped[($v.VariablePath.UserPath -replace '^(?i)script:', '').ToLowerInvariant()] = $true }
        }
    }
    $collide = New-Object System.Collections.Generic.List[string]
    foreach ($entry in $asts) {
        foreach ($v in $entry.Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] }, $true)) {
            $inFn = $false
            for ($a = $v.Parent; $null -ne $a; $a = $a.Parent) { if ($a -is [System.Management.Automation.Language.FunctionDefinitionAst]) { $inFn = $true; break } }
            if ($inFn) { continue }
            if ($v.VariablePath.IsScript -or $v.VariablePath.IsGlobal -or $v.VariablePath.UserPath.Contains(':')) { continue }
            if ($scoped.ContainsKey($v.VariablePath.UserPath.ToLowerInvariant())) { $collide.Add("`$$($v.VariablePath.UserPath) at $(Split-Path -Leaf $entry.Path):$($v.Extent.StartLineNumber)") }
        }
    }
    return $collide
}

# Every command a file calls by a literal name must be a function defined in one of the files, a
# cmdlet this host knows, or one of the native programs the scripts run on Windows. Catches a
# misspelt helper name, which only a hosted run would otherwise find.
function Test-UndefinedCommands([string[]]$Paths) {
    $native = @('tasklist', 'whoami', 'gh', 'ConvertTo-Json', 'ConvertFrom-Json')
    $defined = @{}
    $asts = @()
    foreach ($p in $Paths) {
        $tokens = $null; $errs = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$tokens, [ref]$errs)
        $asts += , @{ Path = $p; Ast = $ast }
        foreach ($f in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) { $defined[$f.Name.ToLowerInvariant()] = $true }
    }
    $bad = New-Object System.Collections.Generic.List[string]
    foreach ($entry in $asts) {
        foreach ($c in $entry.Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
            $name = $c.GetCommandName()
            if (-not $name) { continue }
            if ($defined.ContainsKey($name.ToLowerInvariant()) -or ($native -contains $name)) { continue }
            if (Get-Command $name -ErrorAction SilentlyContinue) { continue }
            $bad.Add("$name at $(Split-Path -Leaf $entry.Path):$($c.Extent.StartLineNumber)")
        }
    }
    return $bad
}

# ---------------------------------------------------------------------------------------------
# Native helpers (Windows only; Initialize-Win32 is never called by a self test)
# ---------------------------------------------------------------------------------------------
function Initialize-Win32 {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class M32Win {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string c, string t);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern uint GetDpiForSystem();
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
    [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr SendMessageTimeout(IntPtr h, uint msg, IntPtr w, IntPtr l, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll", EntryPoint = "SendMessageTimeoutW", CharSet = CharSet.Unicode, SetLastError = true)] public static extern IntPtr SendMessageTimeoutText(IntPtr h, uint msg, IntPtr w, StringBuilder l, uint flags, uint timeout, out IntPtr result);
    // WM_NULL with SMTO_ABORTIFHUNG: true when the window's thread answers inside the bound. A
    // thread blocked in Sleep or a long call (not pumping messages) times out; that is the test.
    public static bool Responsive(IntPtr h, uint ms) {
        IntPtr r;
        return SendMessageTimeout(h, 0, IntPtr.Zero, IntPtr.Zero, 0x0002, ms, out r) != IntPtr.Zero;
    }
    // WM_GETTEXT through SendMessageTimeout (GetWindowText cannot be trusted across processes)
    static string TextOf(IntPtr h) {
        StringBuilder t = new StringBuilder(256);
        IntPtr r;
        if (SendMessageTimeoutText(h, 0x000D, (IntPtr)256, t, 0x0002, 2000, out r) == IntPtr.Zero) { return ""; }
        return t.ToString();
    }
    // child windows as "hwnd|visible|enabled|class|text"
    public static string[] Children(IntPtr parent) {
        List<string> acc = new List<string>();
        EnumProc cb = delegate (IntPtr h, IntPtr l) {
            StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256);
            acc.Add(h.ToInt64() + "|" + (IsWindowVisible(h) ? 1 : 0) + "|" + (IsWindowEnabled(h) ? 1 : 0) + "|" + c + "|" + TextOf(h));
            return true;
        };
        EnumChildWindows(parent, cb, IntPtr.Zero);
        return acc.ToArray();
    }
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
    public static int[] Rect(IntPtr h) {
        RECT r;
        if (!GetWindowRect(h, out r)) { return null; }
        return new int[] { r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top };
    }
    public static bool Move(IntPtr h, int x, int y, int w, int hh) {
        // SWP_NOZORDER (0x4) | SWP_NOACTIVATE (0x10)
        return SetWindowPos(h, IntPtr.Zero, x, y, w, hh, 0x0014);
    }
}
'@
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Windows.Forms
}

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

# the main window: owned by an app pid, titled GleepGlorp AI (visible or not); a visible one wins
function Get-MainWindow {
    # not the launch splash ("GleepGlorp AI - starting"): it is visible first and goes away
    $w = @(Get-AppWindows | Where-Object { $_.Title -like 'GleepGlorp AI*' -and $_.Title -notlike '*starting*' })
    if ($w.Count -eq 0) { return $null }
    $vis = @($w | Where-Object { $_.Visible })
    if ($vis.Count -gt 0) { return $vis[0] }
    return $w[0]
}

# Inno's wizard form: class TWizardForm, any process (the elevated setup .tmp owns it), visible.
# Returns the window object or $null.
function Get-WizardWindow {
    $w = @(Get-AllWindows | Where-Object { $_.Class -eq 'TWizardForm' -and $_.Visible })
    if ($w.Count -eq 0) { return $null }
    return $w[0]
}

# The controls of a window: objects with Hwnd, Visible, Enabled, Class, Text.
function Get-ChildControls([int64]$Hwnd) {
    $res = @()
    foreach ($l in [M32Win]::Children([IntPtr]$Hwnd)) {
        $p = $l.Split('|', 5)
        if ($p.Count -ge 5) {
            $res += [pscustomobject]@{ Hwnd = [int64]$p[0]; Visible = ($p[1] -eq '1'); Enabled = ($p[2] -eq '1'); Class = $p[3]; Text = $p[4] }
        }
    }
    return $res
}

# The wizard's buttons that could be pressed now: visible, enabled TNewButton (or a plain BUTTON)
# whose caption is Next, Install or Finish (ampersands and arrows ignored).
function Get-WizardButtons($Controls) {
    return @($Controls | Where-Object {
        $_.Visible -and $_.Enabled -and ($_.Class -eq 'TNewButton' -or $_.Class -eq 'Button') -and
        (($_.Text -replace '[&<>\s]', '') -match '^(Next|Install|Finish)$')
    })
}

# the native rectangle as @{X;Y;W;H}, or $null
function Get-WindowGeometry([int64]$Hwnd) {
    $r = [M32Win]::Rect([IntPtr]$Hwnd)
    if ($null -eq $r) { return $null }
    return @{ X = $r[0]; Y = $r[1]; W = $r[2]; H = $r[3] }
}

# primary-screen working area and the virtual screen (the union), as @{X;Y;W;H}
function Get-ScreenAreas {
    $wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
    return [pscustomobject]@{
        Work  = @{ X = $wa.X; Y = $wa.Y; W = $wa.Width; H = $wa.Height }
        Union = @{ X = $vs.X; Y = $vs.Y; W = $vs.Width; H = $vs.Height }
        Dpi   = [M32Win]::GetDpiForSystem()
    }
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

# GET /api/window/state -> @{ Status; Visible ($true/$false/$null) }
function Get-RouteVisible {
    $r = Invoke-Api GET '/api/window/state'
    $v = $null
    if ($r.Status -eq 200) {
        try { $o = ConvertFrom-Json $r.Content; if ($null -ne $o.visible) { $v = [bool]$o.visible } } catch { $v = $null }
    }
    return [pscustomobject]@{ Status = $r.Status; Visible = $v; Content = $r.Content }
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

# `the-one.exe quit --wait`, bounded. Returns @{ ExitCode; Finished; Output }.
function Invoke-QuitCli([string]$Tag) {
    $exe = Join-Path $script:InstallDir 'the-one.exe'
    $qOut = Join-Path $script:Out "quit-$Tag.txt"
    $qp = Start-Process -FilePath $exe -ArgumentList @('quit', '--wait') -PassThru -NoNewWindow -RedirectStandardOutput $qOut
    $null = $qp.Handle
    $null = $script:Pids.Add($qp.Id)
    $done = $qp.WaitForExit(100000)
    if (-not $done) {
        Write-Log "quit($Tag) did not finish in 100 s; killing recorded pid $($qp.Id)"
        Stop-Process -Id $qp.Id -Force -ErrorAction SilentlyContinue
    }
    $code = $null
    if ($done) { try { $code = $qp.ExitCode } catch { $code = $null } }
    $txt = ((Get-Content -LiteralPath $qOut -ErrorAction SilentlyContinue) -join ' / ')
    Write-Log "quit($Tag): finished=$done exit=$code output='$txt'"
    return [pscustomobject]@{ ExitCode = $code; Finished = $done; Output = $txt }
}

# ---------------------------------------------------------------------------------------------
# Installer, registry, shortcuts, evidence
# ---------------------------------------------------------------------------------------------
function Get-InstalledVersion {
    if (-not (Test-Path -LiteralPath $script:UninstallKey)) { return $null }
    try { return [string](Get-ItemProperty -LiteralPath $script:UninstallKey).DisplayVersion } catch { return $null }
}

function Get-InstalledLocation {
    if (-not (Test-Path -LiteralPath $script:UninstallKey)) { return $null }
    try { return ([string](Get-ItemProperty -LiteralPath $script:UninstallKey).InstallLocation).TrimEnd('\') } catch { return $null }
}

# every Uninstall entry (both hives) whose DisplayName matches GleepGlorp AI: the duplicate check
function Get-UninstallEntryCount {
    $entries = 0
    foreach ($root in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
        if (Test-Path -LiteralPath $root) {
            foreach ($k in Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue) {
                $pp = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction SilentlyContinue
                if ($pp -and $pp.DisplayName -like '*GleepGlorp AI*') { $entries++ }
            }
        }
    }
    return $entries
}

# the Start-menu .lnk files of this product (all users and the current user)
function Get-ProductShortcuts {
    $roots = @("$env:ProgramData\Microsoft\Windows\Start Menu\Programs", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs")
    return @(Get-ChildItem -LiteralPath $roots -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like '*GleepGlorp*' } | ForEach-Object { $_.FullName })
}

function Save-Evidence([string]$Tag) {
    try { (& tasklist /V 2>&1 | Out-String) | Set-Content -LiteralPath (Join-Path $script:Out "tasklist-$Tag.txt") -Encoding UTF8 } catch { }
    try {
        $acc = New-Object System.Collections.Generic.List[string]
        foreach ($r in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
            if (Test-Path -LiteralPath $r) {
                foreach ($k in Get-ChildItem -LiteralPath $r -ErrorAction SilentlyContinue) {
                    $p = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction SilentlyContinue
                    if ($p -and ($p.DisplayName -like '*GleepGlorp*')) {
                        $acc.Add("$($k.Name) :: DisplayName=$($p.DisplayName) DisplayVersion=$($p.DisplayVersion) InstallLocation=$($p.InstallLocation)")
                    }
                }
            }
        }
        Set-Content -LiteralPath (Join-Path $script:Out "uninstall-$Tag.txt") -Value $acc -Encoding UTF8
    } catch { }
}

# Run an installer silently, bounded. Returns @{ ExitCode; TimedOut; Pid; Log; Events; InnoText; AppText }
# Events maps a name to the first-seen time (ms on the run clock, +-250 ms) of a pattern in the
# Inno /LOG (Src 'inno') or the NEW bytes of the app log (Src 'app'). 'proc-exit' is the watched
# pid's exit.
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
# Self test of the non-Windows helpers. Returns the list of failure messages (empty when clean).
# ---------------------------------------------------------------------------------------------
function Invoke-LibSelfTest([string]$Scratch, [string[]]$AstPaths) {
    $fails = New-Object System.Collections.Generic.List[string]
    $check = {
        param([bool]$Cond, [string]$What)
        if ($Cond) { Write-Host "ok   $What" } else { Write-Host "FAIL $What"; $fails.Add($What) }
    }
    $rowIds = @('A1', 'A2', 'A3')
    Initialize-Lib $Scratch 'libtest' $rowIds 600
    $sumLines = { @(Get-Content -LiteralPath $script:SummaryPath) }

    # the key constant: two closing braces (leg 1's finding)
    & $check ($script:UninstallKeyPath.EndsWith('}}_is1')) 'the uninstall key ends with }}_is1 (two closing braces)'
    & $check ($script:UninstallKeyPath -match '\{CAEEFB46-2698-4048-AD9F-0120D0B7174A\}\}_is1$') 'the uninstall key holds the pinned GUID'
    & $check ($script:UninstallKey -eq $script:UninstallKeyPath) 'Initialize-Lib exposes the key'

    # rows and summary
    $script:Header.Add('== header')
    Write-Summary
    $s = & $sumLines
    & $check (@($s | Where-Object { $_ -like 'FAIL * not-run' }).Count -eq 3) 'all three seeded rows show FAIL not-run'
    & $check ($s[0] -eq '== header') 'header first'
    & $check (-not ([IO.File]::ReadAllText($script:SummaryPath).Contains("`r"))) 'the written summary has no CR'
    & $check (($s -join "`n") -notmatch 'libtest done|libtest aborted') 'a running summary has neither done nor aborted'
    Set-Row 'A1' 'PASS' 'one'
    Set-Row 'A2' 'INFO' 'two'
    Add-Info 'A3' 'note'
    $s = & $sumLines
    & $check ($s -contains 'PASS A1 one' -and $s -contains 'INFO A2 two' -and $s -contains 'INFO A3 note') 'Set-Row and Add-Info land in the summary'
    & $check (@($s | Where-Object { $_ -like 'FAIL * not-run' }).Count -eq 1) 'one row still not-run'
    $threw = $null; try { Set-Row 'Z9' 'PASS' 'x' } catch { $threw = $_.Exception.Message }
    & $check ($threw -match "unknown row id 'Z9'") 'Set-Row rejects an unknown id'
    $threw = $null; try { Add-Info 'Z9' 'x' } catch { $threw = $_.Exception.Message }
    & $check ($threw -match "unknown row id 'Z9'") 'Add-Info rejects an unknown id'
    $threw = $null; try { Set-Row 'A1' 'MAYBE' 'x' } catch { $threw = $_.Exception.Message }
    & $check ($threw -match 'bad status') 'Set-Row rejects a bad status'

    # abort path: rows still show, aborted line names the failure, no done line
    Initialize-Lib $Scratch 'libtest' $rowIds 600
    try { Set-Row 'Z9' 'PASS' 'x' } catch { $script:AbortReason = Get-AbortText $_ }
    $script:Done = $true
    Write-Summary
    $s = & $sumLines
    & $check (@($s | Where-Object { $_ -like 'FAIL * not-run' }).Count -eq 3) 'abort path: every row still shows FAIL not-run'
    $ab = @($s | Where-Object { $_ -like '== libtest aborted:*' })
    & $check ($ab.Count -eq 1 -and $ab[0] -match "unknown row id 'Z9'") 'abort path: one aborted line naming the failure'
    & $check (($s -join "`n") -notmatch 'libtest done') 'abort path: no done line'

    # normal path: done is the last line, no FAIL
    Initialize-Lib $Scratch 'libtest' $rowIds 600
    foreach ($rid in $rowIds) { Set-Row $rid 'PASS' "ok $rid" }
    $script:Completed = $true; $script:Done = $true
    Write-Summary
    $s = & $sumLines
    & $check ($s[-1] -eq '== libtest done') 'normal path: the last line is the done marker'
    & $check (@($s | Where-Object { $_ -like 'FAIL*' }).Count -eq 0) 'normal path: no FAIL line'
    # a lost row table still writes every row
    Initialize-Lib $Scratch 'libtest' $rowIds 600
    $script:Rows = @(1, 2)
    Write-Summary
    & $check (@(& $sumLines | Where-Object { $_ -like 'FAIL * not-run*' }).Count -eq 3) 'a lost row table still writes three FAIL rows'
    Initialize-Lib $Scratch 'libtest' $rowIds 600

    # the global bound arithmetic against the 80-minute job cap
    $now = [long]2000000
    & $check ($script:JobBoundSeconds -eq 4080 -and (4800 - $script:JobBoundSeconds) -ge 11 * 60) 'the job bound leaves at least 11 minutes of an 80-minute job'
    & $check ((Get-EffectiveGlobalSeconds 3000 ([string]($now - 100)) $now) -eq 3000) 'bound: early keeps the request'
    & $check ((Get-EffectiveGlobalSeconds 3000 ([string]($now - 2000)) $now) -eq 2080) 'bound: 2000 s in leaves 2080'
    & $check ((Get-EffectiveGlobalSeconds 3000 ([string]($now - 4080)) $now) -eq 0) 'bound: at the bound leaves 0'
    & $check ((Get-EffectiveGlobalSeconds 3000 ([string]($now - 5000)) $now) -eq 0) 'bound: past the bound clamps to 0'
    & $check ((Get-EffectiveGlobalSeconds 3000 '' $now) -eq 3000) 'bound: no M32_T0 keeps the request'
    & $check ((Get-EffectiveGlobalSeconds 3000 'abc' $now) -eq 3000) 'bound: a non-numeric M32_T0 keeps the request'
    & $check ((Get-EffectiveGlobalSeconds 600 ([string]($now - 2000)) $now) -eq 600) 'bound: a smaller request wins'

    # the new-bytes log reader
    $tmp = Join-Path $Scratch 'selftest-app.log'
    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
    & $check ((Get-FileLen $tmp) -eq 0) 'Get-FileLen of a missing file is 0'
    & $check ((Read-NewBytes $tmp 0).Text -eq '') 'Read-NewBytes of a missing file is empty'
    [System.IO.File]::WriteAllText($tmp, "line one`nline two`n")
    $r1 = Read-NewBytes $tmp 0
    & $check ($r1.Text -eq "line one`nline two`n" -and $r1.Offset -eq 18) 'Read-NewBytes reads everything from offset 0'
    $writer = [System.IO.File]::Open($tmp, 'Append', 'Write', 'ReadWrite')   # held open, like the app's logger
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("Finished server process [4242]`n")
        $writer.Write($bytes, 0, $bytes.Length); $writer.Flush()
        $r2 = Read-NewBytes $tmp $r1.Offset
        & $check ($r2.Text -eq "Finished server process [4242]`n") 'Read-NewBytes returns only the bytes added after the offset (file held open)'
        & $check ($r2.Text -match 'Finished server process \[4242\]') 'the drain pattern matches the new bytes'
        $r3 = Read-NewBytes $tmp $r2.Offset
        & $check ($r3.Text -eq '' -and $r3.Offset -eq $r2.Offset) 'no new bytes reads empty and keeps the offset'
    } finally { $writer.Dispose() }
    [System.IO.File]::WriteAllText($tmp, "new`n")
    & $check ((Read-NewBytes $tmp 999).Text -eq "new`n") 'an offset past the end (rotation) restarts from 0'
    $kl = Get-KeyLines "a`r`nquit-check: present`r`nb`r`nquit-check: gone" 'quit-check'
    & $check ($kl.Count -eq 2 -and $kl[0] -eq '2: quit-check: present') 'Get-KeyLines numbers lines and handles CRLF'

    # Wait-Until
    & $check (Wait-Until { $true } 2 50 'always') 'Wait-Until returns true at once'
    $t0 = Get-Date
    & $check (-not (Wait-Until { $false } 1 100 'never')) 'Wait-Until returns false on timeout'
    & $check (((Get-Date) - $t0).TotalSeconds -lt 5) 'Wait-Until timeout is bounded'
    & $check (-not (Wait-Until { throw 'x' } 1 100 'throws')) 'Wait-Until treats a throwing condition as false'
    $script:Deadline = (Get-Date).AddSeconds(-1)
    & $check (-not (Wait-Until { $false } 30 100 'past the global bound')) 'Wait-Until stops at the global bound'
    $script:Deadline = (Get-Date).AddSeconds(60)

    # log order (the /LOG sequence of an upgrade)
    $good = "setup quit-call: ExecAsOriginalUser x`nsetup quit-check: present`nsetup quit-check: gone`nsetup quit-check: nothing left before KillRunning`nsetup quit-killrunning: calling KillRunning`nDest filename: C:\a"
    $seq = @('setup quit-call: ExecAsOriginalUser', 'quit-check: present', 'quit-check: gone', 'quit-check: nothing left', 'quit-killrunning: calling', 'Dest filename:')
    & $check ((Test-LogOrder $good $seq).Ok) 'Test-LogOrder accepts the right sequence'
    $swapped = $good -replace 'present', 'XX' -replace 'quit-check: gone', 'quit-check: present'
    & $check (-not (Test-LogOrder $swapped $seq).Ok) 'Test-LogOrder rejects a missing step'
    $late = "Dest filename: C:\a`n" + $good
    & $check (-not (Test-LogOrder $late $seq).Ok) 'Test-LogOrder rejects a first copy before the quit'
    & $check ((Test-LogOrder $late $seq).Why -match 'out of order') 'Test-LogOrder names what is out of order'
    & $check ((Test-LogOrder '' $seq).Why -match 'missing') 'Test-LogOrder names what is missing'

    # geometry
    $e = @{ X = 100; Y = 100; W = 1000; H = 700 }
    & $check (Test-GeometryClose $e @{ X = 116; Y = 84; W = 1016; H = 684 } 16) 'geometry: exactly 16 px off is within the tolerance'
    & $check (-not (Test-GeometryClose $e @{ X = 117; Y = 100; W = 1000; H = 700 } 16)) 'geometry: 17 px off is outside'
    & $check (-not (Test-GeometryClose $e @{ X = 100; Y = 100; W = 1000; H = 760 } 16)) 'geometry: a height 60 px off is outside'
    & $check (-not (Test-GeometryClose $e @{ X = $null; Y = 100; W = 1000; H = 700 } 16)) 'geometry: a missing value is not close'
    $union = @{ X = 0; Y = 0; W = 1280; H = 1024 }
    $g = Get-ExpectedGeometry ([pscustomobject]@{ width = 500; height = 300; x = 10; y = 20 }) $union
    & $check ($g.W -eq 640 -and $g.H -eq 360 -and $g.X -eq 10 -and $g.Y -eq 20) 'expected geometry: the 640x360 floor lifts a small window'
    $g = Get-ExpectedGeometry ([pscustomobject]@{ width = 2000; height = 1500; x = 50; y = 50 }) $union
    & $check ($g.W -eq 1280 -and $g.H -eq 1024 -and $g.X -eq 0 -and $g.Y -eq 0) 'expected geometry: clamped to the screen union, then the origin follows'
    $g = Get-ExpectedGeometry ([pscustomobject]@{ width = 800; height = 600; x = 1200; y = 900 }) $union
    & $check ($g.X -eq 480 -and $g.Y -eq 424) 'expected geometry: an origin past the edge is pulled back by the size'
    $g = Get-ExpectedGeometry ([pscustomobject]@{ width = 800; height = 600 }) $union
    & $check ($null -eq $g.X -and $null -eq $g.Y) 'expected geometry: no saved position stays unset'
    $g = Get-ExpectedGeometry ([pscustomobject]@{ width = 800; height = 600; x = -50; y = -10 }) @{ X = -1280; Y = 0; W = 2560; H = 1024 }
    & $check ($g.X -eq -50 -and $g.Y -eq 0) 'expected geometry: negative-origin union is honoured'
    $t = Get-GeometryTarget @{ X = 0; Y = 0; W = 1920; H = 1040 }
    & $check ($t.W -eq 1000 -and $t.H -eq 700 -and $t.X -eq 40 -and $t.Y -eq 30) 'target: 1000x700 inside a large work area'
    $t = Get-GeometryTarget @{ X = 0; Y = 0; W = 1024; H = 728 }
    & $check ($t.W -eq 944 -and $t.H -eq 648) 'target: shrunk to leave an 80 px margin in a small work area'
    $t = Get-GeometryTarget @{ X = 0; Y = 0; W = 700; H = 400 }
    & $check ($t.W -eq 640 -and $t.H -eq 360) 'target: never below the 640x360 floor'
    & $check ((Format-Geometry @{ X = 1; Y = 2; W = 3; H = 4 }) -eq '3x4@1,2') 'Format-Geometry'

    # file hygiene and the scope-collision check
    foreach ($p in $AstPaths) {
        $bytes = [System.IO.File]::ReadAllBytes($p)
        & $check (@($bytes | Where-Object { $_ -gt 127 }).Count -eq 0) "$(Split-Path -Leaf $p) is ASCII"
    }
    $collide = Test-ScriptScopeCollisions $AstPaths
    & $check ($collide.Count -eq 0) "no top-level variable shares a name with a `$script: variable ($($collide -join ', '))"
    $undef = Test-UndefinedCommands $AstPaths
    & $check ($undef.Count -eq 0) "every command called by name is defined or a known cmdlet ($($undef -join ', '))"
    # the check really detects a collision (a positive control)
    $probeFile = Join-Path $Scratch 'collide.ps1'
    Set-Content -LiteralPath $probeFile -Value '$script:Rows = 1; $rows = 2' -Encoding ASCII
    & $check ((Test-ScriptScopeCollisions @($probeFile)).Count -eq 1) 'the collision check flags $rows against $script:Rows'

    return $fails
}

# Direct run: `pwsh -File lib.ps1 -SelfTest`. A dot-source from lifecycle.ps1 passes no arguments.
if ($MyInvocation.InvocationName -ne '.' -and ($args -contains '-SelfTest')) {
    $mScratch = Join-Path ([System.IO.Path]::GetTempPath()) ('m32-lib-selftest-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $mScratch | Out-Null
    $mFails = Invoke-LibSelfTest $mScratch @($PSCommandPath)
    if (@($mFails).Count -gt 0) { Write-Host "lib.ps1 -SelfTest: $(@($mFails).Count) failure(s)"; exit 1 }
    Write-Host 'lib.ps1 -SelfTest: all ok'
    exit 0
}
