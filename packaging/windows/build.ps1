# build.ps1 - the one Windows recipe (Mission 32 Flight 4, leg 3).
#
# Stages the source at a chosen version, renders packaging/product.toml into the installer's
# product.iss, freezes from the staged copy, runs strict `doctor` on the frozen exe and builds
# the Inno Setup installer. Called by the Concourse task (ci/tasks/windows-installer-build.yml)
# and by .github/workflows/windows-packages.yml, so both build the same way.
#
#   build.ps1 [-Version X] -Out DIR [-Python PYTHON] [-ReuseVenv]
#   build.ps1 -SelfTest
#
#   -Version   the version to build (e.g. 0.11.9.dev1). Empty: __version__ in the_one/__init__.py.
#   -Out       the parent of the stage, venv, work, dist and installer directories. It must be
#              OUTSIDE the repo: nothing the build makes lands in the repo except the rendered
#              packaging\windows\product.iss (gitignored; ISPP #includes it from the .iss's own
#              directory), which is deleted and re-rendered on every build.
#   -Python    a Python 3.12 interpreter (empty: `python` on PATH).
#   -ReuseVenv keep an existing build venv under -Out (the N+1 build); otherwise it is rebuilt.
#
# Output (all under -Out):  stage-windows-<V>\  work-<V>\  dist-<V>\  installer-<V>\
#   installer-<V>\<setup_file_stem>-<V>.exe   and   build-<V>.env (VERSION, SETUP_EXE, DIST).
# The project is NEVER installed (no editable install): the freeze sees only the staged copy,
# through M32_STAGE (see the-one.spec), like the macOS recipe.
#
# Rules this script keeps: $LASTEXITCODE is checked after every native call; any failure throws;
# the file is ASCII (Windows PowerShell 5.1 reads a BOM-less file as ANSI); script-scope names are
# case-insensitive, so no top-level variable shares a name with a $script: variable (the
# -SelfTest AST check enforces it). It runs on Windows PowerShell 5.1 and PowerShell 7.
[CmdletBinding()]
param(
    [string]$Version = '',
    [string]$Out = '',
    [string]$Python = '',
    [switch]$ReuseVenv,
    # -SelfTest exercises the argument handling, the path validation, the version resolution and
    # the doctor needle list with no Windows API (it runs on Linux pwsh in a container).
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$script:PyInstallerVersion = '6.22.3'
$script:MinInnoMajor = 6
$script:MinInnoMinor = 1

# What strict `doctor` must print, by name: the exit code alone cannot see a probe silently
# dropped from run_doctor's gate list. (the retired windows-installer.yml's list, plus the desktop shell and
# the child-spawn seam.)
function Get-DoctorNeedles {
    return @(
        'usearch: OK', 'fts5: OK', 'embedding model: OK', 'file watcher: OK', 'window chrome: OK',
        'time zones: OK', 'mcp sdk: OK', 'chart images: OK', 'desktop shell: OK', 'child spawn: OK'
    )
}

function Assert-DoctorOutput([string]$Text) {
    foreach ($needle in (Get-DoctorNeedles)) {
        if (-not $Text.Contains($needle)) { throw "frozen doctor output missing '$needle'" }
    }
}

function Test-VersionString([string]$Value) {
    return [bool]($Value -match '^\d+\.\d+\.\d+(\.dev\d+)?$')
}

function Get-RepoRoot {
    # this script lives in <repo>\packaging\windows
    return (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function Read-RepoVersion([string]$Repo) {
    $init = Join-Path $Repo 'the_one/__init__.py'
    $text = [System.IO.File]::ReadAllText($init)
    $hits = [regex]::Matches($text, '(?m)^__version__\s*=\s*"([^"]*)"\s*$')
    if ($hits.Count -ne 1) { throw "expected exactly one __version__ line in $init, found $($hits.Count)" }
    return $hits[0].Groups[1].Value
}

function Resolve-BuildVersion([string]$Requested, [string]$Repo) {
    $v = $Requested
    if (-not $v) { $v = Read-RepoVersion $Repo }
    if (-not (Test-VersionString $v)) { throw "unsupported version form '$v' (X.Y.Z or X.Y.Z.devN)" }
    return $v
}

function Get-FullPathNoFs([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path)
}

# $true when $Path is the repo or lies inside it (case-insensitive, separator-agnostic).
function Test-InsideRepo([string]$Path, [string]$Repo) {
    $p = (Get-FullPathNoFs $Path).TrimEnd('\', '/').Replace('\', '/').ToLowerInvariant()
    $r = (Get-FullPathNoFs $Repo).TrimEnd('\', '/').Replace('\', '/').ToLowerInvariant()
    return ($p -eq $r) -or $p.StartsWith($r + '/')
}

function Assert-OutDir([string]$OutDir, [string]$Repo) {
    if (-not $OutDir) { throw 'build.ps1: -Out is required' }
    if (Test-InsideRepo $OutDir $Repo) { throw "build.ps1: -Out $OutDir is inside the repo $Repo" }
}

function Get-InstallerName([string]$Stem, [string]$Ver) { return "$Stem-$Ver.exe" }

function Assert-Native([string]$Label) {
    if ($LASTEXITCODE -ne 0) { throw "$Label failed (exit $LASTEXITCODE)" }
}

# A version counts only if it parses and is not all zeros (the image's ISCC.exe can report
# FileVersion 0.0.0.0). Returns the matched string or $null; callers use the return value.
function Test-IsccVersion([string]$Raw) {
    if ($Raw -and ($Raw -match '\d+\.\d+(\.\d+)*')) {
        $m = $Matches[0]
        if ($m -notmatch '^0(\.0)*$') { return $m }
    }
    return $null
}

function Test-InnoTooOld([string]$Found) {
    if (-not $Found) { return $false }
    $parts = $Found -split '\.'
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -lt $script:MinInnoMajor) -or ($major -eq $script:MinInnoMajor -and $minor -lt $script:MinInnoMinor)
}

function Find-Iscc {
    $pf86 = ${env:ProgramFiles(x86)}
    $cands = @()
    if ($pf86) { $cands += (Join-Path $pf86 'Inno Setup 6\ISCC.exe') }
    if ($env:ProgramFiles) { $cands += (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe') }
    $hit = $cands | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $hit) {
        $cmd = Get-Command iscc -ErrorAction SilentlyContinue
        if ($cmd) { $hit = $cmd.Source }
    }
    if (-not $hit) { throw 'ISCC.exe not found (install Inno Setup 6.1 or newer)' }
    return $hit
}

# Best-effort ISCC version from several sources, each logged raw. Never throws: an unreadable
# version is 'unknown' (the compile of the .iss is the loud check). Fails only a PARSED version
# below 6.1 (the quit hook's ExecAsOriginalUser needs it).
function Get-IsccVersion([string]$Iscc) {
    $found = $null
    $tried = New-Object System.Collections.Generic.List[string]
    $vi = (Get-Item -LiteralPath $Iscc).VersionInfo
    $sources = @(
        @{ Label = 'ISCC.exe ProductVersion'; Value = $vi.ProductVersion },
        @{ Label = 'ISCC.exe FileVersion'; Value = $vi.FileVersion }
    )
    $dll = Join-Path (Split-Path -Parent $Iscc) 'ISCmplr.dll'
    if (Test-Path -LiteralPath $dll) {
        $dvi = (Get-Item -LiteralPath $dll).VersionInfo
        $sources += @{ Label = 'ISCmplr.dll FileVersion'; Value = $dvi.FileVersion }
        $sources += @{ Label = 'ISCmplr.dll ProductVersion'; Value = $dvi.ProductVersion }
    }
    foreach ($rk in @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1', 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1')) {
        $dv = ''
        try { $dv = [string](Get-ItemProperty -LiteralPath $rk -ErrorAction Stop).DisplayVersion } catch { $dv = '' }
        $sources += @{ Label = "registry $rk DisplayVersion"; Value = $dv }
    }
    foreach ($s in $sources) {
        $raw = (([string]$s.Value) -replace '\s+', ' ').Trim()
        $tried.Add("$($s.Label)=[$raw]")
        if (-not $found) { $found = Test-IsccVersion $raw }
    }
    if ($found) {
        Write-Host "ISCC version: $found ($($tried -join '; '))"
        if (Test-InnoTooOld $found) { throw "Inno Setup $found is older than 6.1: ExecAsOriginalUser (the quit hook) is unavailable" }
        return $found
    }
    Write-Host "ISCC version: unknown ($($tried -join '; '))"
    return 'unknown'
}

function Invoke-Build {
    $repo = Get-RepoRoot
    Assert-OutDir $Out $repo
    $outDir = Get-FullPathNoFs $Out
    $ver = Resolve-BuildVersion $Version $repo
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    Write-Host "=== build.ps1: version $ver, out $outDir, repo $repo"

    $base = $Python
    if (-not $base) { $base = 'python' }
    $baseVersion = (& $base --version) | Out-String
    Assert-Native 'python --version'
    Write-Host "python: $($baseVersion.Trim())"
    if ($baseVersion -notmatch 'Python 3\.12\.') { throw "Python 3.12 is required, got: $($baseVersion.Trim())" }

    # [1] the build venv: fresh unless -ReuseVenv, so a persistent worker's site-packages cannot
    # ride along into the freeze (Concourse build 606657's stale hf_xet).
    Write-Host '=== [1/8] build venv'
    $venv = Join-Path $outDir 'venv'
    $py = Join-Path $venv 'Scripts\python.exe'
    if ($ReuseVenv -and (Test-Path -LiteralPath $py)) {
        Write-Host 'build venv reused (-ReuseVenv)'
    }
    else {
        if (Test-Path -LiteralPath $venv) { Remove-Item -Recurse -Force -LiteralPath $venv }
        & $base -m venv $venv
        Assert-Native 'python -m venv'
        & $py -m pip install --upgrade pip --quiet
        Assert-Native 'pip install --upgrade pip'
        & $py -m pip install uv --quiet
        Assert-Native 'pip install uv'
        # [2] the LOCKED closure (uv.lock), hash-pinned, installed without resolving: a fresh
        # resolve could bundle an untested SDK, and without --no-deps pip walks each wheel's own
        # declared requirements (huggingface-hub still declares the excluded hf-xet) and aborts
        # require-hashes mode. uv export runs from the repo root (it reads pyproject.toml and uv.lock).
        Write-Host '=== [2/8] locked closure'
        $reqs = Join-Path $outDir 'release-requirements.txt'
        Push-Location $repo
        try {
            & $py -m uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt --output-file $reqs
            Assert-Native 'uv export'
        }
        finally { Pop-Location }
        if (-not (Test-Path -LiteralPath $reqs) -or ((Get-Item -LiteralPath $reqs).Length -eq 0)) { throw 'release-requirements.txt missing or empty after uv export' }
        & $py -m pip install --require-hashes --no-deps --quiet -r $reqs
        Assert-Native 'pip install of the locked closure'
    }

    # [3] the build tool, pinned like the macOS build; the hooks-contrib version it pulls is recorded.
    Write-Host '=== [3/8] PyInstaller'
    & $py -m pip install --quiet "pyinstaller==$($script:PyInstallerVersion)"
    Assert-Native 'pip install pyinstaller'
    $contrib = (& $py -m pip show pyinstaller-hooks-contrib) | Out-String
    Assert-Native 'pip show pyinstaller-hooks-contrib'
    $contribVer = 'unknown'
    if ($contrib -match '(?m)^Version:\s*(\S+)') { $contribVer = $Matches[1] }
    Write-Host "pyinstaller $($script:PyInstallerVersion), pyinstaller-hooks-contrib $contribVer"
    # the project must NOT be importable from the venv: the freeze reads the staged copy only
    Push-Location $outDir
    try {
        & $py -c "import importlib.util, sys; sys.exit(1 if importlib.util.find_spec('the_one') else 0)"
        Assert-Native 'the build venv must not hold the_one'
    }
    finally { Pop-Location }

    # [4] stage
    Write-Host '=== [4/8] stage'
    & $py (Join-Path $repo 'packaging/stage.py') --version $ver --target windows --out $outDir
    Assert-Native 'stage.py'
    $stage = Join-Path $outDir "stage-windows-$ver"
    if (-not (Test-Path -LiteralPath (Join-Path $stage 'the_one'))) { throw "stage produced no the_one/ at $stage" }

    # [5] product.iss: deleted, then rendered at THIS version (without --set, render.py reads the
    # repo's __version__, which is wrong for an N+1 build).
    Write-Host '=== [5/8] render product.iss'
    $winDir = Join-Path $repo 'packaging/windows'
    $iss = Join-Path $winDir 'the-one.iss'
    $inc = Join-Path $winDir 'product.iss'
    if (Test-Path -LiteralPath $inc) { Remove-Item -Force -LiteralPath $inc }
    & $py (Join-Path $repo 'packaging/render.py') --repo $repo --template (Join-Path $winDir 'product.iss.in') --set "version=$ver" --out $inc
    Assert-Native 'render.py product.iss'
    if (-not (Select-String -LiteralPath $inc -SimpleMatch -Pattern "#define AppVersion `"$ver`"" -Quiet)) { throw "product.iss does not define AppVersion $ver" }
    $product = ((& $py (Join-Path $repo 'packaging/render.py') --repo $repo --json --set "version=$ver") | Out-String) | ConvertFrom-Json
    Assert-Native 'render.py --json'
    $setupName = Get-InstallerName $product.setup_file_stem $ver

    # [6] freeze, per version, so an N+1 build never clobbers N
    Write-Host '=== [6/8] freeze'
    $work = Join-Path $outDir "work-$ver"
    $dist = Join-Path $outDir "dist-$ver"
    if (Test-Path -LiteralPath $dist) { Remove-Item -Recurse -Force -LiteralPath $dist }
    $env:M32_STAGE = $stage
    Push-Location $outDir
    try {
        & $py -m PyInstaller --noconfirm --clean --workpath $work --distpath $dist (Join-Path $winDir 'the-one.spec')
        Assert-Native 'PyInstaller freeze'
    }
    finally { Pop-Location }
    $cli = Join-Path $dist ($product.cli_executable + '/' + $product.cli_executable + '.exe')
    $gui = Join-Path $dist ($product.cli_executable + '/' + $product.gui_executable + '.exe')
    if (-not (Test-Path -LiteralPath $cli)) { throw "freeze produced no $cli" }
    if (-not (Test-Path -LiteralPath $gui)) { throw "freeze produced no $gui" }

    # [7] strict doctor on the frozen exe
    Write-Host '=== [7/8] frozen doctor (build gate)'
    $doctorLines = & $cli doctor
    $doctorCode = $LASTEXITCODE
    $doctorText = [string]($doctorLines | Out-String)
    Write-Host $doctorText
    Set-Content -LiteralPath (Join-Path $outDir "doctor-$ver.txt") -Value $doctorText -Encoding ASCII
    if ($doctorCode -ne 0) { throw "frozen doctor failed ($doctorCode)" }
    Assert-DoctorOutput $doctorText

    # [8] the installer
    Write-Host '=== [8/8] Inno installer'
    $iscc = Find-Iscc
    $isccVer = Get-IsccVersion $iscc
    Write-Host "ISCC: $iscc ($isccVer)"
    $instDir = Join-Path $outDir "installer-$ver"
    New-Item -ItemType Directory -Force -Path $instDir | Out-Null
    & $iscc "/DDistDir=$dist" "/O$instDir" $iss
    Assert-Native 'ISCC'
    $setupExe = Join-Path $instDir $setupName
    if (-not (Test-Path -LiteralPath $setupExe)) { throw "installer not produced: $setupExe" }
    $size = (Get-Item -LiteralPath $setupExe).Length
    Write-Host "installer: $setupExe ($size bytes)"
    $envLines = @("VERSION=$ver", "SETUP_EXE=$setupExe", "DIST=$dist")
    Set-Content -LiteralPath (Join-Path $outDir "build-$ver.env") -Value $envLines -Encoding ASCII
    Write-Host "BUILD OK: $setupName"
}

# ---------------------------------------------------------------------------------------------
# Self test: no Windows-only API. Runs in a Linux pwsh container before any build minute.
# ---------------------------------------------------------------------------------------------
function Invoke-SelfTest {
    $script:SelfFails = New-Object System.Collections.Generic.List[string]
    function Assert-That([bool]$Cond, [string]$What) {
        if ($Cond) { Write-Host "ok   $What" } else { Write-Host "FAIL $What"; $script:SelfFails.Add($What) }
    }
    function Assert-Throws([scriptblock]$Fn, [string]$Pattern, [string]$What) {
        $msg = $null
        try { & $Fn } catch { $msg = $_.Exception.Message }
        Assert-That ($null -ne $msg -and $msg -match $Pattern) "$What (threw: $msg)"
    }

    # 1. the file parses, is ASCII, and no top-level variable shares a name with a $script: one
    $tokens = $null; $errs = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$errs)
    Assert-That (-not ($errs -and $errs.Count -gt 0)) 'build.ps1 parses clean'
    $bytes = [System.IO.File]::ReadAllBytes($PSCommandPath)
    Assert-That (@($bytes | Where-Object { $_ -gt 127 }).Count -eq 0) 'build.ps1 is ASCII'
    $scoped = @{}
    foreach ($v in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] }, $true)) {
        if ($v.VariablePath.IsScript) { $scoped[($v.VariablePath.UserPath -replace '^(?i)script:', '').ToLowerInvariant()] = $true }
    }
    $collide = New-Object System.Collections.Generic.List[string]
    foreach ($v in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] }, $true)) {
        $inFn = $false
        for ($a = $v.Parent; $null -ne $a; $a = $a.Parent) { if ($a -is [System.Management.Automation.Language.FunctionDefinitionAst]) { $inFn = $true; break } }
        if ($inFn) { continue }
        if ($v.VariablePath.IsScript -or $v.VariablePath.IsGlobal -or $v.VariablePath.UserPath.Contains(':')) { continue }
        if ($scoped.ContainsKey($v.VariablePath.UserPath.ToLowerInvariant())) { $collide.Add("`$$($v.VariablePath.UserPath) at line $($v.Extent.StartLineNumber)") }
    }
    Assert-That ($collide.Count -eq 0) "no top-level variable shares a name with a `$script: variable ($($collide -join ', '))"

    # 2. version strings and resolution
    foreach ($good in @('0.11.8', '0.11.9.dev1', '10.0.0')) { Assert-That (Test-VersionString $good) "version '$good' accepted" }
    foreach ($bad in @('', '0.11', 'v0.11.8', '0.11.8-rc1', '0.11.8.dev', '0.11.8 ', '0.11.8a1')) { Assert-That (-not (Test-VersionString $bad)) "version '$bad' refused" }
    $repoRoot = Get-RepoRoot
    Assert-That (Test-Path -LiteralPath (Join-Path $repoRoot 'the_one/__init__.py')) 'Get-RepoRoot finds the repo'
    $repoVer = Read-RepoVersion $repoRoot
    Assert-That (Test-VersionString $repoVer) "the repo version '$repoVer' parses"
    Assert-That ((Resolve-BuildVersion '' $repoRoot) -eq $repoVer) 'an empty -Version resolves to __version__'
    Assert-That ((Resolve-BuildVersion '0.11.9.dev1' $repoRoot) -eq '0.11.9.dev1') 'an explicit -Version wins'
    Assert-Throws { Resolve-BuildVersion 'nope' $repoRoot } 'unsupported version' 'a bad -Version throws'

    # 3. -Out validation
    Assert-Throws { Assert-OutDir '' $repoRoot } '-Out is required' 'an empty -Out throws'
    Assert-Throws { Assert-OutDir $repoRoot $repoRoot } 'inside the repo' '-Out equal to the repo throws'
    Assert-Throws { Assert-OutDir (Join-Path $repoRoot 'build') $repoRoot } 'inside the repo' '-Out under the repo throws'
    Assert-Throws { Assert-OutDir (Join-Path $repoRoot 'a/../build') $repoRoot } 'inside the repo' '-Out reaching the repo through .. throws'
    $sibling = $repoRoot.TrimEnd('\', '/') + '-build'
    Assert-That (-not (Test-InsideRepo $sibling $repoRoot)) 'a sibling directory sharing the repo name prefix is outside'
    Assert-That (-not (Test-InsideRepo (Join-Path ([System.IO.Path]::GetTempPath()) 'm32-out') $repoRoot)) 'a temp directory is outside'
    Assert-That (Test-InsideRepo ($repoRoot.ToUpperInvariant() + '/x') $repoRoot) 'the repo check ignores case'

    # 4. the doctor needle list
    $needles = Get-DoctorNeedles
    Assert-That ($needles.Count -eq 10) 'ten doctor needles'
    foreach ($n in @('usearch: OK', 'fts5: OK', 'embedding model: OK', 'file watcher: OK', 'window chrome: OK', 'time zones: OK', 'mcp sdk: OK', 'chart images: OK', 'desktop shell: OK', 'child spawn: OK')) {
        Assert-That ($needles -contains $n) "needle '$n' present"
    }
    $allOk = ($needles -join "`n")
    Assert-That ($null -eq (Assert-DoctorOutput $allOk)) 'a doctor output holding every needle passes'
    Assert-Throws { Assert-DoctorOutput ($allOk -replace 'time zones: OK', 'time zones: FAIL') } "missing 'time zones: OK'" 'a missing needle throws, named'
    Assert-Throws { Assert-DoctorOutput '' } 'missing' 'an empty doctor output throws'

    # 5. ISCC version parsing
    Assert-That ((Test-IsccVersion '6.7.1.0') -eq '6.7.1.0') 'a parsed ISCC version is returned'
    Assert-That ($null -eq (Test-IsccVersion '0.0.0.0')) '0.0.0.0 is treated as unknown'
    Assert-That ($null -eq (Test-IsccVersion '')) 'an empty ISCC version is unknown'
    Assert-That (Test-InnoTooOld '6.0.5') '6.0.5 is too old'
    Assert-That (Test-InnoTooOld '5.6.1') '5.6.1 is too old'
    Assert-That (-not (Test-InnoTooOld '6.1.0')) '6.1.0 is new enough'
    Assert-That (-not (Test-InnoTooOld '6.7.1')) '6.7.1 is new enough'
    Assert-That (-not (Test-InnoTooOld $null)) 'an unknown version is never too old'

    # 6. the installer name
    Assert-That ((Get-InstallerName 'the-one-setup' '0.11.8') -eq 'the-one-setup-0.11.8.exe') 'installer name from the stem and version'

    # 7. Assert-Native
    $global:LASTEXITCODE = 0
    Assert-That ($null -eq (Assert-Native 'ok')) 'Assert-Native passes on exit 0'
    $global:LASTEXITCODE = 3
    Assert-Throws { Assert-Native 'demo' } 'demo failed \(exit 3\)' 'Assert-Native throws on a non-zero exit'
    $global:LASTEXITCODE = 0

    if ($script:SelfFails.Count -gt 0) {
        Write-Host "build.ps1 -SelfTest: $($script:SelfFails.Count) failure(s)"
        exit 1
    }
    Write-Host 'build.ps1 -SelfTest: all ok'
}

if ($SelfTest) { Invoke-SelfTest; exit 0 }
Invoke-Build
