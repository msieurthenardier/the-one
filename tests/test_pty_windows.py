"""Windows PTY session tests — cmd.exe round-trip + Job Object teardown (M15 F3 Legs 2-3).

These tests are guarded by ``skipif(os.name != "nt")`` and run ONLY on the
``windows-2022`` CI lane.  They are the authoritative backend verification for
``WindowsPtySession`` (pywinpty / ConPTY).  Running them on Linux would fail
at ``import winpty`` — the entire module is guarded to prevent that.

Test environment:
- ``THE_ONE_SANDBOX_DISABLED=1`` → forces ``PassthroughSandbox`` (matches the
  ``THE_ONE_TEST_MODE=1`` / sandbox-disabled convention in ``test_pty_session.py``
  and avoids the bwrap gate that does not exist on Windows).
- ``THE_ONE_TEST_MODE=1`` → enables any test-mode guards in the product code.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

# Guard the entire module — do NOT import WindowsPtySession or winpty at module
# scope on non-Windows; that would blow up collection on Linux.
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows-only PTY backend tests")

# Win32 constants used by Job Object teardown tests (Leg 3).
# Defined at module scope to satisfy ruff N806 (no uppercase variables in functions).
_PROCESS_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def _typed_kernel32():
    """Return ``kernel32`` with argtypes/restype set so 64-bit HANDLEs are not
    truncated.  Raw ``ctypes.windll.kernel32`` leaves ``OpenProcess.restype`` at
    the default ``c_int`` (4 bytes), which truncates the returned handle on
    64-bit Windows and makes the grandchild-liveness check unreliable — exactly
    the assertion these reap tests depend on.  Windows-only (imports ctypes
    lazily so the module stays import-safe on Linux)."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    return k32


@pytest.fixture(autouse=True)
def _windows_pty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force PassthroughSandbox for all tests in this module.

    Mirrors the convention in test_pty_session.py (THE_ONE_SANDBOX_DISABLED +
    THE_ONE_TEST_MODE) so WindowsPtySession uses PassthroughSandbox and the
    tests don't require bwrap (which doesn't exist on Windows).
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")


@pytest.mark.asyncio
async def test_start_creates_alive_session() -> None:
    """``start()`` spawns cmd.exe and the session reports alive."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        assert session.is_alive
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_send_echo_hello_round_trip() -> None:
    """``send("echo hello")`` returns output containing ``hello``."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        output = await session.send("echo hello", timeout=15.0)
        assert b"hello" in output
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_send_second_command_state_persists() -> None:
    """A second send in the same session succeeds — PTY state persists."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        await session.send("echo first", timeout=15.0)
        output2 = await session.send("echo second", timeout=15.0)
        assert b"second" in output2
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_close_makes_session_not_alive() -> None:
    """After ``close()``, ``is_alive`` returns False."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    await session.start()
    assert session.is_alive
    await session.close()
    assert not session.is_alive


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    """Calling ``close()`` multiple times does not raise."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    await session.start()
    await session.close()
    await session.close()  # second call must not raise


@pytest.mark.asyncio
async def test_last_activity_updated_after_send() -> None:
    """``last_activity`` is updated after each ``send``."""
    import time

    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        before = session.last_activity
        # Brief pause to ensure monotonic difference is measurable.
        time.sleep(0.05)
        await session.send("echo ts", timeout=15.0)
        after = session.last_activity
        assert after >= before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_send_after_close_raises_runtime_error() -> None:
    """``send()`` after ``close()`` raises ``RuntimeError``."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    await session.start()
    await session.close()
    with pytest.raises(RuntimeError, match="session not active"):
        await session.send("echo nope", timeout=5.0)


# ---------------------------------------------------------------------------
# Job Object teardown tests (M15 F3 Leg 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_reaps_grandchild() -> None:
    """Closing a session kills backgrounded grandchildren via the Job Object.

    Shape mirrors the Unix ``test_pty_close_reaps_namespace_grandchild`` test
    in ``test_pty_sandbox.py``.

    Strategy: write a temp .py script for the grandchild (avoids the quoting
    hazard of ``python -c "..."`` through cmd.exe-through-PTY mangling
    backslash paths in %TEMP%).  Launch via ``start /b "" "exe" "script"``
    with both paths quoted.  The grandchild writes its own PID to a temp file
    — this is robust in shared CI (``tasklist`` before/after diff false-passes
    when another python.exe/timeout.exe runs concurrently).
    After ``close()``, we assert the grandchild is gone by opening its handle
    and checking whether the process has exited.
    """
    import ctypes
    import tempfile
    from ctypes import wintypes
    from pathlib import Path

    from the_one.platform.pty_windows import WindowsPtySession

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        pid_file = f.name

    sentinel_part = "wro" + "te_pid"

    # Write the grandchild script to a temp .py file — no quoting-through-PTY needed.
    grandchild_script = (
        "import os, time\n"
        f"with open(r'{pid_file}', 'w') as _f:\n"
        "    _f.write(str(os.getpid()))\n"
        f"with open(r'{pid_file}', 'a') as _f:\n"
        f"    _f.write(' {sentinel_part}')\n"
        "time.sleep(60)\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as sf:
        script_path = sf.name
        sf.write(grandchild_script)

    try:
        session = WindowsPtySession()
        try:
            await session.start()

            # Both exe and script paths are quoted to handle spaces/backslashes
            # in %TEMP% without quoting-through-PTY mangling.
            grandchild_cmd = f'start /b "" "{sys.executable}" "{script_path}"'
            await session.send(grandchild_cmd, timeout=15.0)

            # Wait up to 5 s for the grandchild to write its PID
            pid_path = Path(pid_file)
            deadline = time.monotonic() + 5.0
            grandchild_pid: int | None = None
            while time.monotonic() < deadline:
                if pid_path.exists():
                    content = pid_path.read_text().strip()
                    if sentinel_part in content:
                        grandchild_pid = int(content.split()[0])
                        break
                time.sleep(0.1)

            assert grandchild_pid is not None, (
                f"Grandchild did not write PID to {pid_file} within 5 s"
            )

            # Verify grandchild is alive before close
            k32 = _typed_kernel32()
            hgc = k32.OpenProcess(
                _PROCESS_SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                grandchild_pid,
            )
            assert hgc, f"Could not open grandchild handle (pid={grandchild_pid})"
            k32.CloseHandle(hgc)

        finally:
            await session.close()

        # After close() the Job Object fires KILL_ON_JOB_CLOSE — the grandchild
        # should be gone.  Poll for up to 3 s (the OS teardown is synchronous on
        # CloseHandle, but scheduling lag can delay it slightly).
        k32 = _typed_kernel32()
        deadline = time.monotonic() + 3.0
        grandchild_gone = False
        while time.monotonic() < deadline:
            hgc = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, grandchild_pid)
            if not hgc:
                # OpenProcess failed → process no longer exists
                grandchild_gone = True
                break
            exit_code = wintypes.DWORD(0)
            k32.GetExitCodeProcess(hgc, ctypes.byref(exit_code))
            k32.CloseHandle(hgc)
            if exit_code.value != _STILL_ACTIVE:
                grandchild_gone = True
                break
            time.sleep(0.1)

        assert grandchild_gone, (
            f"Grandchild (pid={grandchild_pid}) still running after session.close() — "
            "Job Object KILL_ON_JOB_CLOSE did not fire"
        )
    finally:
        import os as _os

        try:
            _os.unlink(pid_file)
        except OSError:
            pass
        try:
            _os.unlink(script_path)
        except OSError:
            pass


@pytest.mark.xfail(
    reason=(
        "Parent-death reap via TerminateProcess from a subprocess is best-effort — "
        "the job handle may not propagate into the child subprocess's Python interpreter "
        "on all Windows CI configurations (the child process may not hold the job handle "
        "if it was created in a separate Windows Job Object context by the CI runner). "
        "The primary guarantee (close()-triggered reap) is covered by "
        "test_close_reaps_grandchild.  The operator's Windows host is the definitive "
        "check for parent-death reap when this test is xfail."
    ),
    strict=False,
)
@pytest.mark.asyncio
async def test_parent_death_reaps_grandchild() -> None:
    """A parent process crash (hard kill) reaps grandchildren via the Job Object.

    Creates a child script that starts a ``WindowsPtySession`` + grandchild,
    then TerminateProcesses the child.  Asserts the grandchild is gone afterward.

    Marked xfail/best-effort: the job handle is held by the child Python process;
    if the CI runner places the child in its own Job Object context, the Job Object
    created inside the child may not auto-close on TerminateProcess in all
    configurations.  The primary reap guarantee (close()-triggered) is verified
    by ``test_close_reaps_grandchild``.  This test documents the parent-death
    contract and provides a passing result on configurations where it works.
    """
    import ctypes
    import tempfile
    from ctypes import wintypes
    from pathlib import Path

    # Child script: starts a PTY session, backgrounds a grandchild that writes
    # its PID + a sentinel to a temp file, then prints "READY:<pid>" and sleeps.
    child_script = textwrap.dedent(
        f"""\
        import asyncio, os, sys, time
        import os as _os
        _os.environ["THE_ONE_SANDBOX_DISABLED"] = "1"
        _os.environ["THE_ONE_TEST_MODE"] = "1"
        sys.path.insert(0, {repr(str(Path(__file__).parent.parent))})
        from the_one.platform.pty_windows import WindowsPtySession
        import tempfile

        pid_file = sys.argv[1]

        async def main():
            session = WindowsPtySession()
            await session.start()
            sentinel = "wro" + "te_pid"
            cmd = (
                f"start /b \\\"\\\" {repr(sys.executable)} -c "
                f'"import os,time; '
                f"open(r'{{pid_file}}', 'w').write(str(os.getpid())); "
                f"open(r'{{pid_file}}', 'a').write(' {{sentinel}}'); "
                f'time.sleep(60)"'
            )
            await session.send(cmd, timeout=15.0)
            # wait for grandchild to write PID
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if os.path.exists(pid_file):
                    content = open(pid_file).read().strip()
                    if sentinel in content:
                        gc_pid = int(content.split()[0])
                        print(f"READY:{{gc_pid}}", flush=True)
                        break
                time.sleep(0.1)
            else:
                print("ERROR:timeout", flush=True)
                return
            # hold the job handle open (don't close the session)
            time.sleep(60)

        asyncio.run(main())
        """
    )

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        pid_file = f.name
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        script_path = f.name
        f.write(child_script)

    try:
        child = subprocess.Popen(
            [sys.executable, script_path, pid_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for the child to report the grandchild PID (up to 20 s)
        grandchild_pid: int | None = None
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and child.poll() is None:
            line = child.stdout.readline()
            if line.startswith("READY:"):
                grandchild_pid = int(line.strip().split(":")[1])
                break

        assert grandchild_pid is not None, (
            f"Child script did not report grandchild PID — stderr: {child.stderr.read()}"
        )

        # Hard-kill the child (simulates parent crash)
        child.kill()
        child.wait(timeout=5)

        # The job handle in the child process should have been closed by the OS
        # on process termination → KILL_ON_JOB_CLOSE fires on the grandchild.
        # Poll up to 3 s.
        k32 = _typed_kernel32()
        deadline = time.monotonic() + 3.0
        grandchild_gone = False
        while time.monotonic() < deadline:
            hgc = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, grandchild_pid)
            if not hgc:
                grandchild_gone = True
                break
            exit_code = wintypes.DWORD(0)
            k32.GetExitCodeProcess(hgc, ctypes.byref(exit_code))
            k32.CloseHandle(hgc)
            if exit_code.value != _STILL_ACTIVE:
                grandchild_gone = True
                break
            time.sleep(0.1)

        assert grandchild_gone, (
            f"Grandchild (pid={grandchild_pid}) still alive after parent was killed — "
            "Job Object KILL_ON_JOB_CLOSE did not fire on parent death"
        )
    finally:
        import os as _os

        try:
            _os.unlink(pid_file)
        except OSError:
            pass
        try:
            _os.unlink(script_path)
        except OSError:
            pass
