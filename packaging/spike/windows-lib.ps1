# Shared helpers for the Mission 32 Flight 1 Windows probe (spike tooling, not product).
# Dot-sourced by packaging/briefcase/build-windows.ps1 and packaging/spike/windows-checks.ps1.
# Written for PowerShell 7 (the workflow uses `shell: pwsh`); every external call is time-limited.

function ConvertTo-QuotedArg {
    # Windows command-line quoting for one argument (Start-Process joins an array with spaces
    # and no quoting of its own).
    param([AllowEmptyString()][string]$Arg)
    if ($Arg -eq '') { return '""' }
    if ($Arg -notmatch '[\s"]') { return $Arg }
    $inner = $Arg -replace '(\\*)"', '$1$1\"'
    $inner = $inner -replace '(\\+)$', '$1$1'
    return '"' + $inner + '"'
}

function Read-SharedText {
    # Read a file another process may still hold open (a grandchild that inherited the handle).
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        try {
            $sr = New-Object System.IO.StreamReader($fs, (New-Object System.Text.UTF8Encoding($false)), $true)
            return $sr.ReadToEnd()
        } finally { $fs.Dispose() }
    } catch { return "(unreadable: $_)" }
}

function Write-Utf8 {
    # UTF-8 without a BOM, LF line endings left as given.
    param([string]$Path, [string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Stop-Tree {
    # Kill one recorded PID and its children. Never by name or pattern (squawk 0160).
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return }
    & taskkill.exe /PID $ProcessId /T /F *> $null
}

function Invoke-Capped {
    # Run one program with stdout and stderr redirected to files and a time limit. The combined
    # text (stdout, then stderr) is written to OutFile with a final "rc=N" line (124 on a
    # timeout, -1 if it would not start), which is what score.py's score_doctor reads.
    # Returns @{Rc; TimedOut; Seconds; Started}.
    param(
        [Parameter(Mandatory)][string]$Exe,
        [string[]]$ArgList = @(),
        [Parameter(Mandatory)][string]$OutFile,
        [int]$TimeoutSec = 300,
        [string]$WorkDir = (Get-Location).Path
    )
    $o = "$OutFile.out"
    $e = "$OutFile.err"
    $outDir = Split-Path -Parent $OutFile
    if ($outDir -and -not (Test-Path -LiteralPath $outDir -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    }
    Remove-Item -LiteralPath $o, $e -Force -ErrorAction SilentlyContinue
    $argLine = ($ArgList | ForEach-Object { ConvertTo-QuotedArg $_ }) -join ' '
    $sp = @{
        FilePath = $Exe; WorkingDirectory = $WorkDir
        RedirectStandardOutput = $o; RedirectStandardError = $e
        PassThru = $true; NoNewWindow = $true
    }
    if ($argLine) { $sp.ArgumentList = $argLine }
    $t0 = Get-Date
    try {
        $p = Start-Process @sp
    } catch {
        Write-Utf8 $OutFile "start failed: $_`nrc=-1`n"
        return [pscustomobject]@{ Rc = -1; TimedOut = $false; Seconds = 0; Started = $false }
    }
    $null = $p.Handle   # keep the handle so ExitCode is readable after the process ends
    $done = $p.WaitForExit($TimeoutSec * 1000)
    $timedOut = -not $done
    if ($timedOut) {
        Stop-Tree $p.Id
        $null = $p.WaitForExit(15000)
    } else {
        $p.WaitForExit()
    }
    $rc = if ($timedOut) { 124 } else { $p.ExitCode }
    $text = (Read-SharedText $o)
    $err = (Read-SharedText $e)
    if ($err) { $text += "`n-- stderr --`n" + $err }
    Write-Utf8 $OutFile ($text.TrimEnd() + "`nrc=$rc`n")
    return [pscustomobject]@{
        Rc = $rc; TimedOut = $timedOut; Started = $true
        Seconds = [int]((Get-Date) - $t0).TotalSeconds
    }
}

function Start-Background {
    # Start a long-running program (serve) with output redirected; returns the Process object
    # (the caller stops it by PID with Stop-Tree).
    param(
        [Parameter(Mandatory)][string]$Exe,
        [string[]]$ArgList = @(),
        [Parameter(Mandatory)][string]$OutFile,
        [string]$WorkDir = (Get-Location).Path
    )
    $argLine = ($ArgList | ForEach-Object { ConvertTo-QuotedArg $_ }) -join ' '
    $sp = @{
        FilePath = $Exe; WorkingDirectory = $WorkDir
        RedirectStandardOutput = "$OutFile.out"; RedirectStandardError = "$OutFile.err"
        PassThru = $true; NoNewWindow = $true
    }
    if ($argLine) { $sp.ArgumentList = $argLine }
    return (Start-Process @sp)
}

function Use-EnvVars {
    # Run a script block with process environment variables set (and some cleared), then restore.
    param([hashtable]$Set = @{}, [string[]]$Clear = @(), [Parameter(Mandatory)][scriptblock]$Body)
    $saved = @{}
    foreach ($k in (@($Set.Keys) + $Clear)) { $saved[$k] = [Environment]::GetEnvironmentVariable($k) }
    try {
        foreach ($k in $Set.Keys) { [Environment]::SetEnvironmentVariable($k, [string]$Set[$k]) }
        foreach ($k in $Clear) { [Environment]::SetEnvironmentVariable($k, $null) }
        & $Body
    } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
    }
}
