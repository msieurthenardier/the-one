"""Static pins for the Windows installer's quit hooks and the lifecycle driver (M32 F4 leg 3b).

Inno Setup and Windows PowerShell cannot run here, so these read the text: the product ``.iss``
``[Code]`` must quit the app and reach ``KillRunning`` on install and on uninstall, and
``lifecycle.ps1`` must keep its row ids, its done marker and its PASS rules. The behaviour itself is
proven by the hosted ``lifecycle`` run (rows L7 and L9 read the ``/LOG`` these lines produce).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = ROOT / "packaging" / "windows"
ISS = (WIN / "the-one.iss").read_text(encoding="utf-8")
LIFECYCLE = (WIN / "lifecycle.ps1").read_text(encoding="utf-8")
LIB = (WIN / "lib.ps1").read_text(encoding="utf-8")


def _code() -> str:
    return ISS[ISS.index("\n[Code]") :]


def _proc(name: str) -> str:
    """The body of a Pascal procedure/function, from its header to the next top-level one."""
    code = _code()
    m = re.search(
        rf"^(?:procedure|function) {name}\b.*?(?=^(?:procedure|function) |\Z)", code, re.M | re.S
    )
    assert m, f"{name} is not defined in [Code]"
    # code only: a `//` comment (which may name ExecAsOriginalUser) belongs to the next routine
    return "\n".join(ln for ln in m.group(0).splitlines() if not ln.lstrip().startswith("//"))


def test_backstop_directives_stay():
    assert "CloseApplications=force" in ISS
    assert "RestartApplications=no" in ISS


def test_both_hooks_are_present_and_call_the_quit_sequence():
    assert "QuitThenKillSetup;" in _proc("PrepareToInstall")
    hook = _proc("CurUninstallStepChanged")
    assert "CurUninstallStep = usUninstall" in hook
    assert "QuitThenKillUninstall;" in hook
    assert re.search(
        r"procedure CurUninstallStepChanged\(CurUninstallStep: TUninstallStep\);", _code()
    )
    assert re.search(r"function PrepareToInstall\(var NeedsRestart: Boolean\): String;", _code())


def test_setup_uses_execasoriginaluser_and_uninstall_uses_exec():
    setup = _proc("QuitThenKillSetup")
    assert "ExecAsOriginalUser(Exe, 'quit --wait'" in setup
    assert "ewWaitUntilTerminated" in setup and "ewNoWait" not in setup
    uninstall = _proc("QuitThenKillUninstall")
    # ExecAsOriginalUser is a setup-only function: it must never appear in uninstall-time code
    assert "ExecAsOriginalUser" not in uninstall
    assert "Exec(Exe, 'quit --wait'" in uninstall
    assert "ewWaitUntilTerminated" in uninstall and "ewNoWait" not in uninstall
    for shared in ("CheckThenKill", "AppsRunning", "ImageRunning", "KillRunning"):
        assert "ExecAsOriginalUser" not in _proc(shared)


def test_kill_running_is_always_reached_and_the_ui_thread_is_never_blocked():
    for name in ("QuitThenKillSetup", "QuitThenKillUninstall"):
        assert "CheckThenKill(" in _proc(name), f"{name} must end in the shared check-then-kill"
    check = _proc("CheckThenKill")
    # no early exit between the check and the force path
    assert "Exit;" not in check and "Exit(" not in check
    assert check.rstrip().endswith("end;")
    assert "KillRunning;" in check
    # v0.12.1: the v0.12.0 wizard froze because the UI thread slept and polled for up to 90 s.
    # Nothing in [Code] may sleep, loop on a clock or import them again.
    code = "\n".join(ln for ln in _code().splitlines() if not ln.lstrip().startswith("//"))
    for banned in ("Sleep", "GetTickCount", "M32Sleep", "M32Tick", "while ", "Limit :="):
        assert banned not in code, banned
    assert "external '" not in code
    # the quit call is the one wait, so Inno keeps pumping messages (the wizard stays responsive)
    assert _proc("QuitThenKillSetup").count("ewWaitUntilTerminated") == 1


def test_setup_logging_is_on():
    setup = ISS[: ISS.index("\n[Code]")]
    assert re.search(r"^SetupLogging=yes$", setup, re.M)


def test_lifecycle_has_the_interactive_wizard_row():
    assert "function Test-RowL11" in LIFECYCLE
    body = LIFECYCLE[LIFECYCLE.index("function Test-RowL11") :]
    body = body[: body.index("function Test-RowL9")]
    body = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))
    assert (
        "/VERYSILENT" not in body and "/LOG" not in body
    )  # the wizard is shown; the TEMP log is the proof
    for needle in ("TWizardForm", "Responsive(", "0x00F5", "Setup Log *.txt", "Get-WizardWindow"):
        assert needle in body or needle in LIB, needle
    assert "SMTO" in LIB or "0x0002" in LIB
    ids = re.search(r"\$script:RowIds = @\(([^)]*)\)", LIFECYCLE).group(1)
    assert ids.replace("'", "").replace(" ", "") == "L1,L2,L3,L4,L5,L6,L7,L8,L10,L11,L9"


def test_log_lines_the_lifecycle_rows_read_are_emitted():
    # the format is '<tag> quit-check: ...' with tag 'setup' or 'uninstall' (Log(Tag + ' quit-...'))
    poll = _proc("CheckThenKill")
    for frag in (
        "' quit-check: present'",
        "' quit-check: gone'",
        "' quit-check: nothing left before KillRunning'",
        "' quit-killrunning: calling KillRunning'",
    ):
        assert f"Log(Tag + {frag}" in poll, frag
    assert "Log('setup quit-call: ExecAsOriginalUser '" in _proc("QuitThenKillSetup")
    assert "Log('uninstall quit-call: Exec '" in _proc("QuitThenKillUninstall")
    # and the lifecycle driver searches for exactly those strings
    for rx in (
        "setup quit-call: ExecAsOriginalUser",
        "setup quit-check: present",
        "setup quit-check: gone",
        "setup quit-check: nothing left",
        "setup quit-killrunning: calling",
        "uninstall quit-call: Exec ",
        "uninstall quit-check: present",
        "uninstall quit-check: gone",
        "uninstall quit-check: nothing left",
        "uninstall quit-killrunning: calling",
    ):
        assert rx in LIFECYCLE, rx


def test_uninstall_hook_runs_before_files_are_removed():
    # usUninstall is the first step of the removal; usPostUninstall would be too late
    assert "usPostUninstall" not in _code()
    assert "usUninstall" in _proc("CurUninstallStepChanged")


def test_lifecycle_rows_and_done_marker():
    for rid in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10", "L11"):
        assert f"function Test-Row{rid}" in LIFECYCLE
        assert f"Id = '{rid}'" in LIFECYCLE
    row_ids = (
        "$script:RowIds = @('L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L10', 'L11', 'L9')"
    )
    assert row_ids in LIFECYCLE
    # seeded not-run and the done marker only on the normal path
    assert '"FAIL $id not-run"' in LIB
    assert '"== $($script:Title) done"' in LIB
    assert LIB.count("== $($script:Title) done") == 1
    runner = LIFECYCLE[LIFECYCLE.index("function Invoke-RowPlan") :]
    assert "$script:Completed = $true" in runner
    assert LIFECYCLE.count("$script:Completed = $true") == 1
    assert "$script:Completed = $true" not in LIB.split("function Invoke-LibSelfTest")[0]
    assert "dot-source" not in LIFECYCLE or ". (Join-Path $PSScriptRoot 'lib.ps1')" in LIFECYCLE
    assert ". (Join-Path $PSScriptRoot 'lib.ps1')" in LIFECYCLE


def test_lifecycle_pass_rules_hold_their_key_checks():
    assert "}}_is1" in LIB
    assert "$script:Tolerance = 16" in LIFECYCLE
    assert "Get-UninstallEntryCount" in LIFECYCLE and "-ne 1" in LIFECYCLE  # exactly one entry
    assert "Get-RouteVisible" in LIFECYCLE
    assert "[M32Win]::PostMessage" in LIFECYCLE  # WM_CLOSE for L4
    assert "0x0010" in LIFECYCLE
    assert "[M32Win]::Move" in LIFECYCLE  # SetWindowPos for L6
    assert "Finished server process" in LIFECYCLE  # the drain line (L6, L7, L8, L9)
    assert "'/VERYSILENT', '/SUPPRESSMSGBOXES', \"/LOG=$logPath\"" in LIFECYCLE
    assert "unins000.exe" in LIFECYCLE
    assert "gh" in LIFECYCLE and "release" in LIFECYCLE and "download" in LIFECYCLE
    assert "window-state.json" in LIFECYCLE
    # recorded pids only
    for text in (LIFECYCLE, LIB):
        assert not re.search(r"(&|Start-Process\s+(-FilePath\s+)?)['\"]?taskkill", text, re.I)
        assert not re.search(r"Stop-Process\s+-Name", text)
        assert not re.search(r"Get-Process[^\n]*\|\s*Stop-Process", text)


def test_ps1_files_are_ascii_and_self_testable():
    for path in (WIN / "lib.ps1", WIN / "lifecycle.ps1", WIN / "smoke.py"):
        assert path.read_bytes().isascii(), f"{path.name} must stay ASCII"
    assert "-SelfTest" in (WIN / "lifecycle.ps1").read_text(encoding="utf-8")
    assert "$args -contains '-SelfTest'" in LIB


def test_probe_is_untouched_by_the_shared_library():
    probe = (WIN / "probe" / "probe.ps1").read_text(encoding="utf-8")
    assert "lib.ps1" not in probe
    assert "}}_is1" not in probe, (
        "the frozen probe keeps its single-brace key (the recorded defect)"
    )
