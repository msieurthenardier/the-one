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
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import time
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
        """Write ``input`` (newline-appended if not already terminated)
        to cmd.exe; read response until idle or timeout.

        Returns raw bytes. Raises ``asyncio.TimeoutError`` on no-output
        windows. Raises ``RuntimeError`` if the session is closed or
        the subprocess has exited.
        """
        if self._closed or not self.is_alive:
            raise RuntimeError("session not active")
        if not input.endswith("\n"):
            input = input + "\n"
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            self._send_blocking,
            input,
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

        # Remove session scratch directory after the process is confirmed
        # gone and the PTY socket is closed.
        if self._cleanup_dir is not None:
            shutil.rmtree(self._cleanup_dir, ignore_errors=True)
