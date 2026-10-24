# Build GleepGlorp AI for Windows with Briefcase and package an .msi.
# Spike prototype (Mission 32 Flight 1, leg windows-cost, candidate B). Meant for the hosted
# windows-2022 runner (packaging-probe-windows.yml); the Linux twin is build.sh, the macOS twin
# build-macos.sh.
#
#   packaging/briefcase/build-windows.ps1 -Version 0.11.9.dev1
#
# Environment:
#   M32_BUILD         build root (default C:\m32: short, against MAX_PATH)
#   M32_LOGS          evidence/log directory (default $M32_BUILD\logs)
#   M32_REQUIREMENTS  the hash-pinned `uv export` closure (REQUIRED; the workflow writes it)
# Needs on PATH: python (3.11, setup-python) and git (Briefcase clones its template).
# Briefcase is pinned to 0.4.6 and installed into its own venv, never the repo's.
# Briefcase downloads WiX, rcedit, the stub and the embeddable Python itself; each phase is timed.
param(
    [Parameter(Mandatory)][string]$Version
)
$ErrorActionPreference = 'Continue'
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO = (Resolve-Path (Join-Path $HERE '..\..')).Path
. (Join-Path $REPO 'packaging\spike\windows-lib.ps1')

$M32_BUILD = if ($env:M32_BUILD) { $env:M32_BUILD } else { 'C:\m32' }
$M32_LOGS = if ($env:M32_LOGS) { $env:M32_LOGS } else { Join-Path $M32_BUILD 'logs' }
$REQS = $env:M32_REQUIREMENTS
if (-not $REQS) { throw 'set M32_REQUIREMENTS to the uv export closure file' }
$STAGE = Join-Path $M32_BUILD "stage-briefcase-$Version"
$VENV = Join-Path $M32_BUILD 'venv-briefcase'
$OUT = Join-Path $M32_BUILD 'out'
$LOG = Join-Path $M32_LOGS 'B'
New-Item -ItemType Directory -Force -Path $M32_BUILD, $M32_LOGS, $LOG, $OUT | Out-Null
$SUMMARY = Join-Path $LOG 'BUILD-SUMMARY.txt'
Set-Content -Path $SUMMARY -Value '' -Encoding utf8
function Note([string]$m) { Write-Host $m; Add-Content -Path $SUMMARY -Value $m -Encoding utf8 }
function Die([string]$m) { Note "FAIL build-windows: $m"; exit 1 }

$env:PYTHONUTF8 = '1'   # Briefcase prints non-ASCII; a redirected console is not UTF-8 by default
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
Note "== B: tool venv ($(python --version 2>&1))"
$t0 = Get-Date
if (Test-Path $VENV) { Remove-Item -Recurse -Force $VENV }
python -m venv $VENV
if ($LASTEXITCODE -ne 0) { Die 'venv failed' }
$VPY = Join-Path $VENV 'Scripts\python.exe'
$BC = Join-Path $VENV 'Scripts\briefcase.exe'
$r = Invoke-Capped -Exe $VPY -ArgList @('-m', 'pip', 'install', 'briefcase==0.4.6', 'pillow') `
    -OutFile (Join-Path $LOG 'pip-tools.log') -TimeoutSec 600
if ($r.Rc -ne 0) { Get-Content (Join-Path $LOG 'pip-tools.log') -Tail 20; Die 'briefcase install failed' }
$null = Invoke-Capped -Exe $VPY -ArgList @('-m', 'pip', 'freeze') -OutFile (Join-Path $LOG 'pip-freeze.txt') -TimeoutSec 60
Note "tool venv: $([int]((Get-Date) - $t0).TotalSeconds) s"
$null = Invoke-Capped -Exe $BC -ArgList @('--version') -OutFile (Join-Path $LOG 'briefcase-version.txt') -TimeoutSec 60
Note ("briefcase " + ((Get-Content (Join-Path $LOG 'briefcase-version.txt') | Select-Object -First 1)))

Note "== B: stage $Version (patches 01 and 02, staging copy only)"
$r = Invoke-Capped -Exe 'python' -ArgList @(
    (Join-Path $REPO 'packaging\spike\stage.py'), '--version', $Version, '--candidate', 'briefcase', '--out', $M32_BUILD
) -OutFile (Join-Path $LOG 'stage.log') -TimeoutSec 300
Get-Content (Join-Path $LOG 'stage.log')
if ($r.Rc -ne 0) { Die 'stage failed (a patch did not apply?)' }

# Inputs Briefcase insists on that the app tree does not have (same placeholders as build.sh).
Write-Utf8 (Join-Path $STAGE 'LICENSE.txt') "Placeholder license text for the Mission 32 packaging spike. Briefcase refuses to package without one.`n"
Write-Utf8 (Join-Path $STAGE 'CHANGELOG.md') "# Changelog`n`n## $Version`n`nSpike build (Mission 32 Flight 1).`n"
# The Windows icon: candidate A's committed .ico (Briefcase's `icon = "icon"` resolves to icon.ico).
Copy-Item (Join-Path $REPO 'packaging\windows\installer-assets\the-one.ico') (Join-Path $STAGE 'icon.ico')

# The pinned closure, by absolute path: Briefcase hands `requires` straight to pip on Windows.
Copy-Item $REQS (Join-Path $STAGE 'closure.txt')
$fill = @'
import json
import sys

src, dst, version, closure = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
text = text.replace("@VERSION@", version).replace("@REQUIRES@", json.dumps(["-r", closure]))
with open(dst, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
'@
Write-Utf8 (Join-Path $M32_BUILD 'fill-pyproject.py') $fill
python (Join-Path $M32_BUILD 'fill-pyproject.py') (Join-Path $HERE 'pyproject.toml.in') `
    (Join-Path $STAGE 'pyproject.toml') $Version (Join-Path $STAGE 'closure.txt')
if ($LASTEXITCODE -ne 0) { Die 'pyproject fill failed' }

Set-Location $STAGE
Note '== B: briefcase create / build / package (msi)'
$t0 = Get-Date
foreach ($step in @('create', 'build', 'package')) {
    $a = @($step, 'windows', 'app', '--no-input', '-v')
    # no signing identity on the runner: --adhoc-sign is Briefcase's explicit "do not sign"
    if ($step -eq 'package') { $a += '--adhoc-sign' }
    $log = Join-Path $LOG "briefcase-$step.log"
    $s0 = Get-Date
    $r = Invoke-Capped -Exe $BC -ArgList $a -OutFile $log -TimeoutSec 900 -WorkDir $STAGE
    Note ("briefcase $step rc=$($r.Rc) in $($r.Seconds) s ($([int]((Get-Date) - $t0).TotalSeconds) s so far)")
    if ($r.Rc -ne 0) { Get-Content $log -Tail 60; Die "briefcase $step failed" }
}

# Timing of the downloads Briefcase makes (WiX, rcedit, stub, embeddable Python, template).
Select-String -Path (Join-Path $LOG 'briefcase-*.log') -Pattern 'Downloading|Downloaded|Unpacking|Installing WiX|Installing RCEdit|Cloning|template' -ErrorAction SilentlyContinue |
    Select-Object -First 60 | ForEach-Object { $_.Line } |
    Set-Content -Path (Join-Path $LOG 'downloads.txt') -Encoding utf8

$msi = Get-ChildItem -Path (Join-Path $STAGE 'dist') -Filter *.msi -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $msi) { Die 'no .msi under dist' }
Copy-Item $msi.FullName (Join-Path $OUT $msi.Name)
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $msi.FullName).Hash.ToLower()
Write-Utf8 (Join-Path $OUT "$($msi.Name).sha256") "$hash *$($msi.Name)`n"
Note "msi: $($msi.Name) $($msi.Length) bytes sha256=$hash"

# What Briefcase generated: the .wxs (scope, upgrade code, shortcuts), the app layout, the stub kind.
$wxs = Get-ChildItem -Path (Join-Path $STAGE 'build') -Filter *.wxs -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($wxs) { Copy-Item $wxs.FullName (Join-Path $LOG 'the-one.wxs'); Note "wxs: $($wxs.FullName)" }
$src = Get-ChildItem -Path (Join-Path $STAGE 'build') -Directory -Recurse -Depth 4 -Filter src -ErrorAction SilentlyContinue | Select-Object -First 1
if ($src) {
    Get-ChildItem $src.FullName | Select-Object Mode, Length, Name | Format-Table -AutoSize | Out-String -Width 200 |
        Set-Content -Path (Join-Path $LOG 'bundle-src-top.txt') -Encoding utf8
    Get-ChildItem -Path $src.FullName -Filter *._pth -ErrorAction SilentlyContinue | ForEach-Object {
        "-- $($_.Name)"; Get-Content $_.FullName
    } | Set-Content -Path (Join-Path $LOG 'bundle-pth.txt') -Encoding utf8
    $bytes = (Get-ChildItem -Path $src.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    Note ("bundle src: {0:N0} bytes" -f $bytes)
}
Get-Content (Join-Path $STAGE 'pyproject.toml') | Set-Content -Path (Join-Path $LOG 'pyproject.generated.toml') -Encoding utf8
Note "== B: build done ($Version)"
exit 0
