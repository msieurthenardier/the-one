"""Static pins for the Windows recipe (Mission 32 Flight 4, leg 3).

``packaging/windows/build.ps1`` is the one recipe Concourse and GitHub both call. None of this runs
Windows; it reads the files. The PowerShell side runs its own ``-SelfTest`` in a local pwsh
container (and, from leg 3b, on the runner before the build).
"""

from __future__ import annotations

import py_compile
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "packaging" / "windows" / "build.ps1"
SPEC = REPO / "packaging" / "windows" / "the-one.spec"
TASK = REPO / "ci" / "tasks" / "windows-installer-build.yml"
PIPELINE = REPO / "ci" / "windows-installer.pipeline.yml"


def _code(path: Path) -> str:
    """The file without whole-line comments (# or ;)."""
    return "\n".join(
        ln
        for ln in path.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith(("#", ";"))
    )


# ---- the spec ------------------------------------------------------------------------------


def test_spec_compiles(tmp_path):
    py_compile.compile(str(SPEC), cfile=str(tmp_path / "spec.pyc"), doraise=True)


def test_spec_requires_the_stage_and_never_inserts_the_repo_root():
    code = _code(SPEC)
    assert 'os.environ.get("M32_STAGE")' in code
    assert "raise SystemExit" in code and "M32_STAGE" in code
    assert "_REPO_ROOT" not in code
    inserts = re.findall(r"sys\.path\.insert\(0, ([^)]*)\)", code)
    assert sorted(inserts) == ["_PACKAGING", "_STAGE"], inserts
    assert "sys.path.append" not in code
    m = re.search(r"_analysis_kwargs = dict\(\s*pathex=\[([^\]]*)\]", code)
    assert m and m.group(1).strip() == "_STAGE"
    # _PACKAGING is packaging/ itself (render.py lives there), never the repo root above it
    assert re.search(r"_PACKAGING = .*SPECPATH, os\.pardir", code)


def test_spec_puts_the_stage_first_before_any_collect_call():
    code = _code(SPEC)
    stage_at = code.index("sys.path.insert(0, _STAGE)")
    first_call = min(m.start() for m in re.finditer(r"\bcollect_\w+\(", code))
    assert stage_at < first_call
    assert stage_at < code.index("from the_one import __version__")


def test_spec_reads_both_exe_names_from_render():
    code = _code(SPEC)
    assert "import render" in code and "render.load(" in code
    assert 'APP_NAME = PRODUCT["cli_executable"]' in code
    assert 'GUI_NAME = PRODUCT["gui_executable"]' in code
    assert "name=APP_NAME" in code and "name=GUI_NAME" in code
    for literal in ('"the-one"', '"the-one-app"', "'the-one'", "'the-one-app'"):
        assert literal not in code.replace("PRODUCT[", ""), literal
    # the version in names is the staged __version__
    assert 'render.load(_REPO, {"version": APP_VERSION})' in code


def test_spec_keeps_specpath_relative_entries():
    code = _code(SPEC)
    assert 'Analysis(["frozen_entry.py"]' in code
    assert 'Analysis(["frozen_entry_gui.py"]' in code
    assert "icon='installer-assets/the-one.ico'" in code


# ---- build.ps1 -------------------------------------------------------------------------------


def test_build_ps1_is_ascii_and_never_installs_the_project():
    text = BUILD.read_text(encoding="utf-8")
    assert text.isascii(), "build.ps1 must stay ASCII (Windows PowerShell 5 reads it as ANSI)"
    assert "pip install -e" not in text and "pip install -e ." not in text
    assert "/DAppVersion" not in text
    assert "[switch]$SelfTest" in text and "function Invoke-SelfTest" in text


def test_build_ps1_closure_and_pins():
    text = BUILD.read_text(encoding="utf-8")
    # one physical line each (the locked-closure test's regexes match single lines)
    assert re.search(
        r"^\s*& \$py -m uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms "
        r"--format requirements-txt --output-file \$reqs$",
        text,
        re.M,
    )
    assert re.search(
        r"^\s*& \$py -m pip install --require-hashes --no-deps --quiet -r \$reqs$", text, re.M
    )
    assert "pyinstaller==$($script:PyInstallerVersion)" in text
    assert "$script:PyInstallerVersion = '6.22.3'" in text
    assert "pyinstaller-hooks-contrib" in text
    assert "Push-Location $repo" in text, "uv export runs from the repo root"


def test_build_ps1_steps_in_order():
    text = BUILD.read_text(encoding="utf-8")
    order = [
        "packaging/stage.py",
        "--target windows",
        "product.iss.in",
        '--set "version=$ver"',
        "$env:M32_STAGE = $stage",
        "-m PyInstaller --noconfirm --clean --workpath $work --distpath $dist",
        "Assert-DoctorOutput $doctorText",
        '"/DDistDir=$dist"',
        '"/O$instDir"',
        "build-$ver.env",
    ]
    last = -1
    for needle in order:
        at = text.find(needle, last + 1)
        assert at > last, f"{needle!r} missing or out of order"
        last = at
    assert "Remove-Item -Force -LiteralPath $inc" in text, (
        "product.iss is deleted before it is re-rendered"
    )
    assert "-ReuseVenv" in text
    assert "work-$ver" in text and "dist-$ver" in text and "installer-$ver" in text


def test_build_ps1_checks_the_exit_code_after_every_native_call():
    lines = BUILD.read_text(encoding="utf-8").splitlines()
    native = re.compile(r"^\s*(\$\w+ = )?\(?& \$(py|base|cli|iscc)\b|^\s*\$\w+ = \(& \$py")
    checked = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") or not native.search(line):
            continue
        window = "\n".join(lines[i + 1 : i + 4])
        assert "Assert-Native" in window or "$LASTEXITCODE" in window, (
            f"line {i + 1}: {line.strip()}"
        )
        checked += 1
    assert checked >= 14, checked
    assert "throw" in "\n".join(lines)


def test_build_ps1_doctor_needles_are_by_name():
    text = BUILD.read_text(encoding="utf-8")
    m = re.search(r"function Get-DoctorNeedles \{\s*return @\((.*?)\n\s*\)\s*\}", text, re.S)
    assert m
    needles = re.findall(r"'([^']+)'", m.group(1))
    assert needles == [
        "usearch: OK",
        "fts5: OK",
        "embedding model: OK",
        "file watcher: OK",
        "window chrome: OK",
        "time zones: OK",
        "mcp sdk: OK",
        "desktop shell: OK",
        "child spawn: OK",
    ]


# ---- the Concourse task ----------------------------------------------------------------------


def test_task_calls_the_recipe_with_an_out_beside_the_repo():
    text = TASK.read_text(encoding="utf-8")
    assert "repo\\packaging\\windows\\build.ps1" in text
    assert re.search(r"-Out \$buildDir", text)
    assert '$buildDir = Join-Path $taskDir "build"' in text
    assert "-Python $py" in text
    assert "pip install" not in _code(TASK) and "iscc" not in _code(TASK).lower().replace(
        "build.ps1", ""
    )
    assert "Get-Command git" in text, "the log records whether git is on PATH"
    assert "Copy-Item" in text and "$installerDir" in text
    assert "choco install innosetup" in text and "choco install python311" in text


def test_pipeline_minio_step_still_matches_the_installer_name():
    for path in (PIPELINE, REPO / "ci" / "the-one.pipeline.yml"):
        assert "installer/the-one-setup-*.exe" in path.read_text(encoding="utf-8")


# ---- the other consumers of the spec and the .iss (AC8b) -------------------------------------

EXEMPT = {
    REPO / ".github" / "workflows" / "windows-installer.yml",  # deleted in leg 4, broken by design
}
SUFFIXES = {".yml", ".yaml", ".sh", ".ps1", ".py", ".iss"}


def _consumers():
    for top in ("ci", ".github", "scripts", "packaging"):
        for path in (REPO / top).rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES or "__pycache__" in path.parts:
                continue
            if path in EXEMPT or (REPO / "packaging" / "windows" / "probe") in path.parents:
                continue
            yield path


def _runs_spec(text: str) -> bool:
    """A non-comment line that hands the-one.spec to PyInstaller."""
    for line in text.splitlines():
        if line.lstrip().startswith(("#", ";")):
            continue
        if "the-one.spec" in line and re.search(r"pyinstaller", line, re.I):
            return True
    return False


def test_nothing_passes_dappversion_or_freezes_the_spec_unstaged():
    bad = []
    for path in _consumers():
        text = path.read_text(encoding="utf-8")
        if re.search(r"/DAppVersion", text):
            bad.append(f"{path.relative_to(REPO)}: passes /DAppVersion")
        if _runs_spec(text) and "M32_STAGE" not in text:
            bad.append(f"{path.relative_to(REPO)}: runs the-one.spec without M32_STAGE")
    assert not bad, bad


def test_the_spec_guard_catches_an_unstaged_run():
    assert _runs_spec("& $py -m PyInstaller --noconfirm packaging/windows/the-one.spec")
    assert _runs_spec('["pyinstaller", "packaging/windows/the-one.spec"]')
    assert not _runs_spec("# pyinstaller packaging/windows/the-one.spec")
    assert not _runs_spec("see the-one.spec for the contract")


def test_the_guard_sees_the_known_consumers():
    seen = {p.relative_to(REPO).as_posix() for p in _consumers()}
    assert "packaging/windows/build.ps1" in seen
    assert "scripts/windows_test_copy.py" in seen
    assert ".github/workflows/windows-packages.yml" in seen
