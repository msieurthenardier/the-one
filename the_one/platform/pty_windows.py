"""Windows PTY session implementation — Windows-only backend (M15 F3 Leg 2).

This module is the concrete Windows backend for the platform-neutral
``PtySession`` ABC defined in ``the_one.platform.pty``.  It is imported
ONLY on Windows (``os.name == "nt"``); ``the_one.platform.pty`` guards the
import behind the ``nt`` branch of ``create_pty_session()``.  Linux never
imports this module, so the top-level ``import winpty`` (pywinpty) is safe.

The ``WindowsPtySession`` implementation uses pywinpty's ``PtyProcess``
(ConPTY-backed, Windows 10 1809+ / Server 2019+) to spawn cmd.exe in a
pseudo-terminal. The readiness contract mirrors ``UnixPtySession`` exactly:
``start()`` blocks until the socket goes idle for ~100 ms OR a hard 2-second
cap; ``send()`` reads until idle OR the per-call timeout.

**Idle-read mechanism (ConPTY-specific — the obvious approach is wrong).**
``PtyProcess.read()`` does a blocking ``fileobj.recv()`` fed by an internal
daemon thread. The ``read_blocking``/``PYWINPTY_BLOCK`` flag is captured into
that thread's closure at construction — setting it after spawn is a no-op.
The correct idle-detection is therefore: ``proc.fileobj.settimeout(idle_window)``
then ``proc.fileobj.recv(_READ_CHUNK)`` directly (giving raw bytes — not the
str that ``read()`` would return). Catch ``socket.timeout`` as the
"no data this window" signal; catch empty recv or ``EOFError`` as EOF.
Accumulate raw bytes throughout.

**Close (ConPTY-specific).** ``proc.close(force=True)`` terminates AND closes
``fileobj``/``_server`` atomically — this also unblocks any pending ``recv``
in the executor thread. ``terminate(force=True)`` alone returns a bool and
does NOT guarantee child death (no SIGKILL equivalent); ``close()`` is the
correct primitive here.

**No fork-safety constraint.** ``PtyProcess.spawn`` is a ``CreateProcess``
call — there is no ``fork()`` and no post-fork child branch. The SpawnSpec
is still computed via the sandbox seam (mirrors Unix; ensures
``warn_if_isolation_unenforced`` fires correctly and keeps the session-tool
layer decoupled from backend specifics). ``self._wrapped`` is structurally
``False`` — Windows always uses the Passthrough backend (no bwrap on Windows).

**Job Object teardown (M15 F3 Leg 3).** ``start()`` creates a Win32 Job
Object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and assigns the spawned
process to it immediately after spawn.  When ``close()`` calls
``CloseHandle`` on the job, the OS fires the kill on every surviving tree
member (including backgrounded grandchildren).  If the Python process dies
without calling ``close()``, the OS automatically closes the job handle and
the same reap fires — this is the lifecycle guarantee for parent-crash
scenarios (analogous to bwrap's ``--die-with-parent`` on Unix).  The Job
Object provides teardown, NOT containment: Windows remains unsandboxed
(DD9; SECURITY-MODEL.md).
"""

from __future__ import annotations

import asyncio
import ctypes
import shutil
import socket
import time
from ctypes import wintypes
from pathlib import Path
from typing import TYPE_CHECKING

import winpty  # noqa: F821  # pywinpty — Windows-only; imported only on nt via the dispatcher

from the_one.platform.env import _build_subprocess_env
from the_one.platform.pty import (
    _DEFAULT_IDLE_WINDOW,
    _DEFAULT_START_TIMEOUT,
    _READ_CHUNK,
    PtySession,
)
from the_one.platform.shell import select_shell

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import SandboxProfile

# ---------------------------------------------------------------------------
# Win32 Job Object — ctypes plumbing (M15 F3 Leg 3)
#
# All types follow the exact Win32 ABI (x86-64):
#   DWORD          → wintypes.DWORD      (4 bytes; NOT c_ulong which is 8 on Linux)
#   LARGE_INTEGER  → ctypes.c_int64      (8 bytes)
#   SIZE_T/ULONG_PTR → ctypes.c_size_t  (pointer-width; 8 bytes on x64)
#   HANDLE/BOOL    → wintypes.HANDLE / wintypes.BOOL
#
# ctypes inserts the correct x64 padding automatically — e.g. the DWORD
# LimitFlags field before the first SIZE_T field gets 4 bytes of implicit
# padding, matching the Windows SDK layout.
# ---------------------------------------------------------------------------

_ULONG_PTR = ctypes.c_size_t

# JobObjectExtendedLimitInformation class id (winnt.h)
_JobObjectExtendedLimitInformation = 9

# LimitFlags value: kill every process in the job when the last job handle closes
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

# OpenProcess access rights needed for AssignProcessToJobObject
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _IO_COUNTERS(ctypes.Structure):  # noqa: N801  # Win32 naming convention
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),  # LARGE_INTEGER
        ("PerJobUserTimeLimit", ctypes.c_int64),  # LARGE_INTEGER
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),  # SIZE_T
        ("MaximumWorkingSetSize", ctypes.c_size_t),  # SIZE_T
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", _ULONG_PTR),  # ULONG_PTR, NOT DWORD
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _setup_kernel32() -> ctypes.WinDLL:  # type: ignore[name-defined]  # WinDLL exists on Windows
    """Return kernel32 with argtypes/restype set for every call we use.

    HANDLE must be wintypes.HANDLE (== c_void_p, pointer-width) — using
    c_int would silently truncate 64-bit handles → ERROR_INVALID_HANDLE.
    """
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]  # ctypes.windll only on Windows; module is nt-gated

    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]

    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]

    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    k32.CloseHandle.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    k32.GetLastError.restype = wintypes.DWORD
    k32.GetLastError.argtypes = []

    return k32


def _create_job_and_assign(pid: int) -> wintypes.HANDLE:  # type: ignore[name-defined]
    """Create a Win32 Job Object with KILL_ON_JOB_CLOSE and assign *pid*.

    Returns the job handle (caller owns it; call CloseHandle when done).

    Raises RuntimeError on any failure — a ConPTY-works-but-job-fails
    environment should fail loudly rather than silently leak process trees.
    """
    k32 = _setup_kernel32()

    # Create the job object (unnamed — no sharing needed)
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise RuntimeError(f"CreateJobObjectW failed (GetLastError={k32.GetLastError()})")

    # Configure KILL_ON_JOB_CLOSE via the extended limit information struct
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = k32.SetInformationJobObject(
        job,
        _JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        k32.CloseHandle(job)
        raise RuntimeError(f"SetInformationJobObject failed (GetLastError={k32.GetLastError()})")

    # Open the target process with the rights needed for assignment
    hproc = k32.OpenProcess(
        _PROCESS_SET_QUOTA | _PROCESS_TERMINATE,
        False,
        pid,
    )
    if not hproc:
        k32.CloseHandle(job)
        raise RuntimeError(f"OpenProcess(pid={pid}) failed (GetLastError={k32.GetLastError()})")

    # Assign the process to the job.  On Win8+/windows-2022 this succeeds
    # even if the process is already in a job (nested jobs are supported).
    # ERROR_ACCESS_DENIED here is a genuine permissions failure — raise, do
    # NOT silently degrade (the "already-in-a-job" nested-job path does NOT
    # produce ACCESS_DENIED on the target CI platform).
    ok = k32.AssignProcessToJobObject(job, hproc)
    last_error = k32.GetLastError()
    k32.CloseHandle(hproc)  # we only need the job handle going forward
    if not ok:
        k32.CloseHandle(job)
        raise RuntimeError(f"AssignProcessToJobObject failed (GetLastError={last_error})")

    return job


def _normalize_submit(text: str) -> str:
    """Turn every line ending (``\\r\\n``, ``\\n``, ``\\r``) into the ConPTY
    submit sequence ``\\r\\n`` and end the input with exactly one.

    ConPTY submits a line only on ``\\r`` (squawk 0164); pywinpty's own tests
    use ``\\r\\n``. Trailing line endings collapse into one submit, so a
    terminated and an unterminated input behave alike.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n").split("\n")
    return "\r\n".join(lines) + "\r\n"


class WindowsPtySession(PtySession):
    """Windows concrete ``PtySession`` using pywinpty ``PtyProcess`` (ConPTY).

    Spawns cmd.exe (or a configured shell override) via
    ``winpty.PtyProcess.spawn``, routed through the sandbox seam.  The
    sandbox always resolves to ``PassthroughSandbox`` on Windows (no bwrap
    available); ``warn_if_isolation_unenforced`` still fires for boxed
    profiles, preserving the seam contract.

    Construction is cheap; the subprocess is spawned by ``start()``.
    Tests should always wrap ``await s.close()`` in a ``try/finally`` to
    avoid leaking child processes between tests.

    Args:
        cwd: Optional working directory for the spawned shell.
        shell: Optional explicit shell path.  Defaults to ``select_shell()[0]``
            (= ``cmd.exe`` on Windows).
        profile: Optional ``SandboxProfile`` controlling sandbox policy.
            Unit tests pin to passthrough via ``THE_ONE_SANDBOX_DISABLED=1``.
        cleanup_dir: Optional directory to remove (via ``shutil.rmtree``)
            when the session closes.  ``None`` for host sessions (no cleanup).
    """

    def __init__(
        self,
        cwd: Path | None = None,
        shell: str | None = None,
        profile: SandboxProfile | None = None,
        cleanup_dir: Path | None = None,
    ) -> None:
        self._cwd = cwd
        self._shell_override = shell
        self._profile = profile
        self._cleanup_dir = cleanup_dir
        self._proc: winpty.PtyProcess | None = None
        self._closed = False
        # Win32 Job Object handle — set by start(), closed in close().
        # None before start() or after close().
        self._job: wintypes.HANDLE | None = None  # type: ignore[name-defined]
        # Initialize to construction time so the idle reaper has a sensible
        # value even before start() completes.
        self._last_activity = time.monotonic()

    # ------------------------------------------------------------------
    # PtySession protocol implementation
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn cmd.exe via PtyProcess and block until idle-mark or 2s cap.

        The SpawnSpec is computed via the sandbox seam before the spawn call
        (mirrors the UnixPtySession convention even though there is no fork).
        """
        if self._proc is not None:
            raise RuntimeError("session already started")

        # cmd.exe as an interactive PTY session — use the executable alone
        # (NOT the /c args from select_shell() — /c is for one-shot commands,
        # not persistent interactive sessions, just like Unix uses the shell
        # without -c for PTY sessions).
        shell = self._shell_override or select_shell()[0]
        cwd = self._cwd

        # Function-level imports to avoid platform↔sandbox import cycles
        # (mirrors pty_unix.py convention).
        from the_one.platform.sandbox import get_sandbox_backend
        from the_one.platform.sandbox._seam import warn_if_isolation_unenforced
        from the_one.platform.sandbox.base import SandboxProfile

        prof = self._profile if self._profile is not None else SandboxProfile()
        backend = get_sandbox_backend()
        warn_if_isolation_unenforced(prof, backend)
        spec = backend.prepare_spawn(
            prof,
            shell,
            [],  # no args — interactive PTY session, not a one-shot /c call
            _build_subprocess_env(),
            str(cwd) if cwd is not None else None,
        )

        # Spawn the ConPTY process. dimensions=(50, 220) reduces line-wrap
        # surprises in the idle-detection loop (cmd.exe banner can be wide).
        self._proc = winpty.PtyProcess.spawn(
            [spec.command, *spec.args],
            cwd=spec.cwd,
            env=spec.env,
            dimensions=(50, 220),
        )

        # Create a Win32 Job Object with KILL_ON_JOB_CLOSE and assign the
        # spawned process to it BEFORE the banner drain — so any sub-processes
        # cmd.exe forks during startup are already in the job.  If this fails,
        # raise immediately: a session without job-object teardown silently leaks
        # process trees, which is worse than a start() failure.
        self._job = _create_job_and_assign(self._proc.pid)

        # Drain the cmd.exe startup banner to idle.  cmd.exe is more verbose
        # than Unix shells — it emits multiple banner lines before settling.
        # Swallow TimeoutError if the drain exhausts the cap with no bytes
        # (some configurations don't emit a banner in time — session still
        # usable), exactly as UnixPtySession.start() does.
        try:
            await self._read_until_idle(
                timeout=_DEFAULT_START_TIMEOUT,
                idle_window=_DEFAULT_IDLE_WINDOW,
            )
        except asyncio.TimeoutError:
            pass

        self._last_activity = time.monotonic()

    async def send(self, input: str, timeout: float = 30.0) -> bytes:
        """Write ``input`` to cmd.exe as submitted lines; read response
        until idle or timeout.

        Line endings are normalized by ``_normalize_submit`` so every line
        (and the end of the input) is pressed as Enter, which ConPTY only
        recognizes as ``\\r``; a bare ``\\n`` just types at the prompt.

        Returns raw bytes. Raises ``asyncio.TimeoutError`` on no-output
        windows. Raises ``RuntimeError`` if the session is closed or
        the subprocess has exited.
        """
        if self._closed or not self.is_alive:
            raise RuntimeError("session not active")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            self._send_blocking,
            _normalize_submit(input),
            timeout,
        )
        self._last_activity = time.monotonic()
        return result

    async def close(self) -> None:
        """Idempotent teardown. Uses proc.close(force=True) for atomic
        terminate + socket teardown (unblocks any pending recv in the
        executor).
        """
        if self._closed:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._close_blocking)

    @property
    def is_alive(self) -> bool:
        """True if the subprocess is still running.

        Returns False immediately after ``close()`` or if ``start()``
        was never called. Uses ``proc.isalive()`` which is a non-blocking
        check via the pywinpty handle.
        """
        if self._closed or self._proc is None:
            return False
        return self._proc.isalive()

    @property
    def last_activity(self) -> float:
        """Monotonic timestamp of the most recent ``send`` return (or
        ``start()`` completion if no ``send`` has happened yet)."""
        return self._last_activity

    # ------------------------------------------------------------------
    # Blocking helpers (run via ``loop.run_in_executor``)
    # ------------------------------------------------------------------

    def _send_blocking(self, input: str, timeout: float) -> bytes:
        """Synchronous write-then-read. Caller wraps in run_in_executor."""
        assert self._proc is not None  # set by start()
        try:
            self._proc.write(input)
        except EOFError as exc:
            raise RuntimeError("PTY closed during write") from exc
        return self._read_until_idle_blocking(
            timeout=timeout,
            idle_window=_DEFAULT_IDLE_WINDOW,
        )

    async def _read_until_idle(
        self,
        timeout: float,
        idle_window: float,
    ) -> bytes:
        """Async wrapper around ``_read_until_idle_blocking``."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._read_until_idle_blocking,
            timeout,
            idle_window,
        )

    def _read_until_idle_blocking(
        self,
        timeout: float,
        idle_window: float,
    ) -> bytes:
        """Read from the pywinpty socket until idle for ``idle_window``
        seconds (buffer non-empty) OR the ``timeout`` budget is exhausted.

        Uses the socket-timeout mechanism: set a per-recv timeout on the
        underlying socket (``proc.fileobj``), then call ``recv`` directly
        for raw bytes (bypassing ``proc.read()`` which returns str and blocks
        unconditionally).  Catch ``socket.timeout`` as the idle-window signal.

        Returns the accumulated bytes. Raises ``asyncio.TimeoutError`` if the
        timeout elapses with no bytes received.

        Edge cases:
        * On empty recv or ``EOFError`` (child exited / PTY closed): returns
          the buffer accumulated so far (mirrors Unix's OSError(EIO) branch).
        * ``socket.timeout`` with buffered data + idle window elapsed: return.
        """
        assert self._proc is not None  # set by start()
        proc = self._proc
        buffer = bytearray()
        start_time = time.monotonic()
        last_byte_time = start_time

        while True:
            now = time.monotonic()
            elapsed = now - start_time
            remaining = timeout - elapsed
            # Clamp non-negative — negative timeouts are semantically
            # "exhausted"; we'll detect that after the recv attempt.
            recv_timeout = max(0.001, min(idle_window, remaining))

            try:
                proc.fileobj.settimeout(recv_timeout)
                chunk = proc.fileobj.recv(_READ_CHUNK)
            except socket.timeout:
                # No data this window.  If buffer is non-empty AND the
                # last-byte time is at least idle_window ago, we're
                # idle-stable: return.
                if buffer and (time.monotonic() - last_byte_time) >= idle_window:
                    return bytes(buffer)
                # Timeout budget check — exhausted with nothing?
                if time.monotonic() - start_time >= timeout:
                    if buffer:
                        return bytes(buffer)
                    raise asyncio.TimeoutError(
                        f"PTY read timed out after {timeout}s with no output"
                    )
                # Not yet idle-stable and budget remains — keep polling.
                continue
            except EOFError:
                # Child exited — PTY closed.
                return bytes(buffer)
            except OSError:
                # Socket closed (e.g. close() called concurrently).
                return bytes(buffer)

            if chunk:
                buffer.extend(chunk)
                last_byte_time = time.monotonic()
            else:
                # Zero-byte recv (genuine EOF from a non-timed-out path).
                return bytes(buffer)

            # Timeout budget check (after each data iteration so a single
            # idle-window doesn't busy-loop past the cap).
            if time.monotonic() - start_time >= timeout:
                if buffer:
                    return bytes(buffer)
                raise asyncio.TimeoutError(f"PTY read timed out after {timeout}s with no output")

    def _close_blocking(self) -> None:
        """Synchronous teardown. Caller wraps in run_in_executor.

        Uses ``proc.close(force=True)`` which terminates the process AND
        closes ``fileobj``/``_server`` atomically — this unblocks any
        pending ``recv`` in the executor thread, preventing it from
        outliving the event loop.  Catches ``IOError`` which ``proc.close()``
        may raise if terminate fails.

        After closing the ConPTY process, ``CloseHandle(self._job)`` fires
        ``KILL_ON_JOB_CLOSE`` on any surviving tree members (backgrounded
        grandchildren, detached sub-processes).  The job handle is closed in
        its own ``try/finally`` so a non-``IOError`` from ``proc.close`` can
        never skip it (idempotent-teardown contract).

        Removes ``cleanup_dir`` AFTER the process is gone and the socket
        is closed (mirrors UnixPtySession order).
        """
        if self._closed:
            return
        self._closed = True

        proc = self._proc
        if proc is not None:
            try:
                proc.close(force=True)
            except IOError:
                # terminate() inside close() failed — process may already
                # be gone. Not fatal; best-effort.
                pass

        # Close the Job Object handle — this fires KILL_ON_JOB_CLOSE on any
        # survivors regardless of whether proc.close() raised.  The finally
        # block nulls _job unconditionally so double-close is safe.
        job = self._job
        if job is not None:
            try:
                _setup_kernel32().CloseHandle(job)
            finally:
                self._job = None

        # Remove session scratch directory after the process is confirmed
        # gone and the PTY socket is closed.
        if self._cleanup_dir is not None:
            shutil.rmtree(self._cleanup_dir, ignore_errors=True)
