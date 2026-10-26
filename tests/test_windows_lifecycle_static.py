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
    assert "ewNoWait" in setup
    uninstall = _proc("QuitThenKillUninstall")
    # ExecAsOriginalUser is a setup-only function: it must never appear in uninstall-time code
    assert "ExecAsOriginalUser" not in uninstall
    assert "Exec(Exe, 'quit --wait'" in uninstall
    assert "ewNoWait" in uninstall
    for shared in ("PollThenKill", "AppsRunning", "ImageRunning", "KillRunning"):
        assert "ExecAsOriginalUser" not in _proc(shared)


def test_kill_running_is_always_reached_and_the_poll_is_bounded():
    for name in ("QuitThenKillSetup", "QuitThenKillUninstall"):
        assert "PollThenKill(" in _proc(name), f"{name} must end in the shared poll-then-kill"
    poll = _proc("PollThenKill")
    # no early exit between the poll and the force path
    assert "Exit;" not in poll and "Exit(" not in poll
    assert "Limit := 90000" in poll and "Elapsed < Limit" in poll
    assert poll.rstrip().endswith("end;")
    assert poll.index("KillRunning;") > poll.index("while Present")
    assert "M32Tick" in poll and "M32Sleep(1000)" in poll
    assert re.search(
        r"function M32Tick: Cardinal;\s*external 'GetTickCount@kernel32.dll stdcall';", _code()
    )
    assert re.search(
        r"procedure M32Sleep\(Ms: Cardinal\);\s*external 'Sleep@kernel32.dll stdcall';", _code()
    )


def test_log_lines_the_lifecycle_rows_read_are_emitted():
    # the format is '<tag> quit-poll: ...' with tag 'setup' or 'uninstall' (Log(Tag + ' quit-...'))
    poll = _proc("PollThenKill")
    for frag in (
        "' quit-poll: present (iteration 0)'",
        "' quit-poll: gone (iteration '",
        "' quit-poll: nothing left before KillRunning'",
        "' quit-killrunning: calling KillRunning'",
    ):
        assert f"Log(Tag + {frag}" in poll, frag
    assert "Log('setup quit-call: ExecAsOriginalUser '" in _proc("QuitThenKillSetup")
    assert "Log('uninstall quit-call: Exec '" in _proc("QuitThenKillUninstall")
    # and the lifecycle driver searches for exactly those strings
    for rx in (
        "setup quit-call: ExecAsOriginalUser",
        "setup quit-poll: present",
        "setup quit-poll: gone",
        "setup quit-poll: nothing left",
        "setup quit-killrunning: calling",
        "uninstall quit-call: Exec ",
        "uninstall quit-poll: present",
        "uninstall quit-poll: gone",
        "uninstall quit-poll: nothing left",
        "uninstall quit-killrunning: calling",
    ):
        assert rx in LIFECYCLE, rx


def test_uninstall_hook_runs_before_files_are_removed():
    # usUninstall is the first step of the removal; usPostUninstall would be too late
    assert "usPostUninstall" not in _code()
    assert "usUninstall" in _proc("CurUninstallStepChanged")


def test_lifecycle_rows_and_done_marker():
    for rid in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"):
        assert f"function Test-Row{rid}" in LIFECYCLE
        assert f"Id = '{rid}'" in LIFECYCLE
    row_ids = "$script:RowIds = @('L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L10', 'L9')"
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
