"""PTY session helpers — cross-platform contract.

F4 ships Unix-only support; Windows ConPTY is deferred to a future mission.
The module raises ``NotImplementedError`` at IMPORT time on Windows
(``os.name == "nt"``) so consumers get a fast, deterministic failure rather
than a runtime surprise from a half-wired session.

Public surface:

    PtySession (ABC)        — async session contract: start / send / close /
                              is_alive / last_activity
    UnixPtySession          — concrete Unix implementation using
                              ``pty.fork()`` + child-side ``execvp`` to
                              route through the shared sandbox seam
                              (F14 M14 F2: SpawnSpec computed in parent,
                              child execs the spec — single-path through
                              the seam, passthrough reproduces today's
                              behavior byte-for-byte).
    create_pty_session(...) — platform-dispatching factory; on POSIX returns
                              ``UnixPtySession``; on other platforms is
                              unreachable thanks to the import-time guard.

L5a is the platform primitive — no registry, no reaper, no agent_name. The
session-tool layer (L5b registry + lifespan; L6 four ``shell_session_*``
tools) wires this primitive into the agent surface.

PTY readiness: ``start()`` blocks until the master_fd has been idle (no new
bytes for ~100ms) OR a hard 2-second cap, whichever comes first. This avoids
brittle prompt-regex matching (different shells / RC files produce different
prompts) while still giving the agent a clean post-``start()`` state for
its first ``send``.

Stdlib-only — no async-pty libraries — per the M01-M04 framework constraint.
``send`` is async; internally it uses ``loop.run_in_executor`` to wrap the
synchronous ``os.write`` + ``select.select`` + ``os.read`` loop.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import SandboxProfile

if os.name == "nt":
    raise NotImplementedError("Windows ConPTY support deferred to a future mission")

# Imports below this guard are POSIX-only — ``fcntl``, ``pty``, ``select``,
# and ``signal`` are all stdlib modules that exist only on Unix. Importing
# any of them on Windows would raise ``ModuleNotFoundError`` BEFORE the
# clean ``NotImplementedError`` above could fire. Keep them below the
# guard so Windows consumers see the guarded message instead.
import fcntl  # noqa: E402
import pty  # noqa: E402
import select  # noqa: E402
import signal  # noqa: E402

from the_one.platform.env import _build_subprocess_env  # noqa: E402
from the_one.platform.shell import select_shell  # noqa: E402

# Internal tuning constants. Idle window of 100ms is the recommended PTY
# readiness signal (Decision-resolution at L5a leg-design); 2s cap is the
# defense against shells that never go idle (e.g. RC file emits an infinite
# loop). 65536 is a comfortable single-read size — smaller than typical PTY
# kernel buffers, so a single ``os.read`` rarely truncates a logical chunk.
_DEFAULT_IDLE_WINDOW = 0.1
_DEFAULT_START_TIMEOUT = 2.0
_READ_CHUNK = 65536

# Shells that benefit from ``-i`` (interactive flag): ``bash`` and ``zsh``
# both source RC files and emit prompts more reliably with ``-i``. ``dash``
# (which is ``/bin/sh`` on Debian/Ubuntu) emits a "can't access tty" warning
# under some configurations when invoked with ``-i``; the F4 use case does
# not strictly need an interactive prompt — the idle-mark detects readiness
# regardless of whether a prompt was printed.
_INTERACTIVE_SHELL_BASENAMES: frozenset[str] = frozenset({"bash", "zsh"})


class PtySession(ABC):
    """Abstract async PTY session contract.

    L5a defines the protocol; L5a's ``UnixPtySession`` is the only concrete
    implementation in this flight. Consumers (L5b registry, L6 session
    tools) program against this ABC.
    """

    @abstractmethod
    async def start(self) -> None:
        """Spawn the shell subprocess and block until ready for input.

        Implementations must:

        * route through the sandbox seam (compute SpawnSpec in parent,
          exec through spec in child — DD1 fork-safety).
        * block until the shell signals readiness (idle-mark — no new bytes
          for ~100ms — OR a hard 2s cap, whichever comes first).
        """

    @abstractmethod
    async def send(self, input: str, timeout: float = 30.0) -> bytes:
        """Write ``input`` (newline-terminated if not already) to the
        shell; read response until idle (no new bytes for ~100ms) OR the
        ``timeout`` elapses. Returns raw bytes. Updates
        ``self.last_activity``.

        Raises ``asyncio.TimeoutError`` if the shell produces no output
        for the entire ``timeout`` window.
        """

    @abstractmethod
    async def close(self) -> None:
        """Teardown: SIGKILL-fast on bwrap-wrapped sessions (bwrap doesn't
        forward SIGTERM); SIGTERM→1s→SIGKILL on passthrough. Idempotent —
        safe to call multiple times."""

    @property
    @abstractmethod
    def is_alive(self) -> bool:
        """True if the subprocess is still running.

        Non-blocking ``os.waitpid(pid, os.WNOHANG)`` check; returns
        ``False`` once the child has exited (or after ``close()``).
        """

    @property
    @abstractmethod
    def last_activity(self) -> float:
        """``time.monotonic()`` timestamp of the most recent ``send``
        return. Used by the idle reaper (L5b) to decide when to call
        ``close()``."""


class UnixPtySession(PtySession):
    """Unix concrete ``PtySession`` using ``pty.fork()`` + child-side
    ``execvp`` routed through the sandbox seam (F14 M14 F2).

    The SpawnSpec is computed in the parent BEFORE ``pty.fork()`` (DD1
    fork-safety: the factory touches logging locks). The child execs through
    the spec — passthrough reproduces today's behavior byte-for-byte;
    bubblewrap wraps the shell in a PID namespace.

    Construction is cheap; the subprocess is spawned by ``start()``.
    Tests should always wrap ``await s.close()`` in a ``try/finally`` to
    avoid leaking child processes between tests.

    Args:
        cwd: Optional working directory for the spawned shell. Passed to
            ``spec.cwd`` (bubblewrap uses ``--chdir``; passthrough uses
            ``os.chdir`` in the child). chdir failure makes the child
            ``os._exit(127)`` (parent then sees the session as dead via
            ``is_alive``).
        shell: Optional explicit shell path. Used by tests for
            deterministic ``env`` output. Defaults to ``select_shell()[0]``
            (honors ``$SHELL`` on POSIX).
        profile: Optional ``SandboxProfile`` controlling sandbox policy
            (writable paths, network, PID namespace, etc.). When ``None``
            on a bubblewrap host a strict-floor profile is used (no
            writable paths). Callers that need a working session on Linux
            must pass a profile that includes the workspace in
            ``writable_paths``. The tool layer (Leg 2) always supplies
            a real profile; unit tests pin to passthrough via
            ``THE_ONE_SANDBOX_DISABLED=1``.
    """

    def __init__(
        self,
        cwd: Path | None = None,
        shell: str | None = None,
        profile: SandboxProfile | None = None,
    ) -> None:
        self._cwd = cwd
        self._shell_override = shell
        self._profile = profile
        self._pid: int | None = None
        self._master_fd: int | None = None
        self._closed = False
        self._wrapped: bool = False
        # ``_last_activity`` is set by ``start`` and ``send``. Initialize
        # to construction time so the reaper has a sensible value even if
        # ``start`` somehow doesn't run (shouldn't happen, but defensive).
        self._last_activity = time.monotonic()

    # ------------------------------------------------------------------
    # PtySession protocol implementation
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn the shell via ``pty.fork()`` and block until idle-mark
        or 2s cap, whichever comes first.

        The SpawnSpec is computed HERE (parent, before fork) for fork-safety:
        ``get_sandbox_backend()`` touches logging locks the child must not
        acquire (DD1). The child execvp's through the spec unchanged.
        """
        if os.name != "posix":
            # Belt-and-suspenders. Module-level guard already raised on
            # Windows; this also covers (hypothetical) future os.name
            # values that aren't "posix".
            raise NotImplementedError(
                f"UnixPtySession requires os.name == 'posix' (got {os.name!r})"
            )
        if self._pid is not None:
            raise RuntimeError("session already started")

        shell = self._shell_override or select_shell()[0]
        cwd = self._cwd

        # --- Compute SpawnSpec in the parent (before fork) — DD1 ---
        # Function-level import to avoid any platform↔platform.sandbox
        # import cycle — mirrors platform/shell.py:123.
        from the_one.platform.sandbox import get_sandbox_backend
        from the_one.platform.sandbox.base import SandboxProfile

        # Carry the existing interactive-shell logic into shell_args (it
        # must be resolved here so the child branch is fork-safe).
        if os.path.basename(shell) in _INTERACTIVE_SHELL_BASENAMES:
            shell_args = ["-i"]
        else:
            shell_args = []

        prof = self._profile if self._profile is not None else SandboxProfile()
        backend = get_sandbox_backend()
        spec = backend.prepare_spawn(
            prof,
            shell,
            shell_args,
            _build_subprocess_env(),
            str(cwd) if cwd is not None else None,
        )
        # Record whether this session is bwrap-wrapped for the teardown branch
        # (spec-level ground truth — a future backend variant can't drift this).
        self._wrapped = spec.command == "bwrap"

        # Fork-safety (DD1): load libc HERE, in the PARENT, before pty.fork().
        # Importing ctypes or calling CDLL inside the post-fork child is unsafe —
        # a new dlopen() can deadlock on a mutex inherited from a parent thread
        # mid-import. ctypes is already imported at module level; we just call
        # CDLL here in the parent so the handle is available pre-fork.
        # Primary orphan-reap coverage is bwrap's own --die-with-parent
        # (prctl PR_SET_PDEATHSIG tied to the Python parent). This pre-execvp
        # call closes only the microsecond startup race window before bwrap
        # registers its own handler. Safe only when bwrap is not setuid/setcap
        # (probed by the regression test — those executables clear PDEATHSIG on execve).
        _libc = ctypes.CDLL("libc.so.6", use_errno=True)
        _pr_set_pdeathsig = 1  # prctl constant PR_SET_PDEATHSIG (linux/prctl.h)

        try:
            pid, master_fd = pty.fork()
        except OSError as exc:
            # ``pty.fork()`` can fail under resource limits (RLIMIT_NPROC,
            # FD exhaustion). Surface with context so the caller can tell
            # this from a downstream ``send`` failure.
            raise RuntimeError(f"pty.fork() failed: {exc}") from exc

        if pid == 0:
            # Child branch — ``os._exit`` on any failure to avoid running
            # parent atexit handlers / pytest cleanup. Errors written to
            # the slave PTY surface to the parent via the master_fd read.
            try:
                # passthrough: real effect on cwd; bwrap: redundant (--chdir
                # in spec) but harmless and required for passthrough — do not
                # remove (DD1).
                if spec.cwd is not None:
                    os.chdir(spec.cwd)
                os.environ.clear()
                os.environ.update(spec.env)
                # Defense-in-depth: set PR_SET_PDEATHSIG so this child (and
                # everything it execs) receives SIGKILL if the Python parent
                # dies. The pre-loaded _libc handle is safe to use here (no
                # new import/dlopen — loaded in the parent above). signal is
                # already imported at module level.
                _libc.prctl(_pr_set_pdeathsig, signal.SIGKILL)
                os.execvp(spec.command, [spec.command, *spec.args])
            except Exception:  # pragma: no cover — exec replaces image
                # Unreachable under normal operation: ``execvp`` either
                # replaces the image or raises; on raise we exit so the
                # parent sees a quick EOF. ``BaseException`` would catch
                # ``SystemExit`` from ``os._exit``; we explicitly want
                # ``Exception`` to let ``SystemExit`` propagate out.
                os._exit(127)
            # Should never reach here.
            os._exit(127)  # pragma: no cover

        # Parent branch
        self._pid = pid
        self._master_fd = master_fd
        # Non-blocking master_fd so ``os.read`` raises ``BlockingIOError``
        # rather than blocking when the buffer is empty. ``select.select``
        # remains the wait primitive.
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Drain the prompt. Discard the bytes — we only care that the
        # shell has gone idle. Use the leg-spec readiness window: 100ms
        # idle, hard 2s cap.
        try:
            await self._read_until_idle(
                timeout=_DEFAULT_START_TIMEOUT,
                idle_window=_DEFAULT_IDLE_WINDOW,
            )
        except asyncio.TimeoutError:
            # No bytes at all in 2s — accepted. Some shells in some
            # configurations don't emit a prompt on stdout (notably
            # non-interactive ``sh``). The session is still usable.
            pass

        self._last_activity = time.monotonic()

    async def send(self, input: str, timeout: float = 30.0) -> bytes:
        """Write ``input`` (newline-appended if not already terminated)
        to the shell; read response until idle or timeout.

        Returns raw bytes. Raises ``asyncio.TimeoutError`` on no-output
        windows. Raises ``RuntimeError`` if the session is closed or
        the subprocess has exited.
        """
        if self._closed or not self.is_alive:
            raise RuntimeError("session not active")
        if not input.endswith("\n"):
            input = input + "\n"
        payload = input.encode()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            self._send_blocking,
            payload,
            timeout,
        )
        self._last_activity = time.monotonic()
        return result

    async def close(self) -> None:
        """Idempotent teardown. Closes ``master_fd``.

        SIGKILL-fast on bwrap-wrapped sessions (bwrap doesn't forward
        SIGTERM to the inner shell; the 1s grace is wasted — DD9).
        SIGTERM→1s→SIGKILL on passthrough sessions (preserves graceful
        behavior). No in-close settle — the orphan-assertion settle lives
        test-side where the async-teardown-vs-/proc race actually needs
        covering.
        """
        if self._closed:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._close_blocking)

    @property
    def is_alive(self) -> bool:
        """True if the subprocess is still running.

        Returns False after ``close()`` or once ``os.waitpid`` reports
        the child has exited. Catches ``ChildProcessError`` (kernel
        removed the entry between calls) and treats as dead.
        """
        if self._closed or self._pid is None:
            return False
        try:
            done, _status = os.waitpid(self._pid, os.WNOHANG)
        except ChildProcessError:
            # Kernel removed the entry between calls; treat as dead.
            self._closed = True
            return False
        if done == 0:
            return True
        # ``done == self._pid`` means the child has exited.
        self._closed = True
        return False

    @property
    def last_activity(self) -> float:
        """Monotonic timestamp of the most recent ``send`` return (or
        ``start()`` completion if no ``send`` has happened yet)."""
        return self._last_activity

    # ------------------------------------------------------------------
    # Blocking helpers (run via ``loop.run_in_executor``)
    # ------------------------------------------------------------------

    def _send_blocking(self, payload: bytes, timeout: float) -> bytes:
        """Synchronous write-then-read. Caller wraps in
        ``run_in_executor``."""
        assert self._master_fd is not None  # set by ``start``
        os.write(self._master_fd, payload)
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
        """Read from ``master_fd`` until the stream goes idle for
        ``idle_window`` seconds (and the buffer is non-empty) OR the
        ``timeout`` budget is exhausted.

        Returns the accumulated bytes. Raises ``asyncio.TimeoutError``
        if the timeout elapses with no bytes received.

        Edge cases:
        * On ``OSError(EIO)`` (slave PTY closed when shell exited): returns
          the buffer accumulated so far (may be empty).
        * On ``BlockingIOError`` / ``OSError(EAGAIN)`` from ``os.read``:
          treats as no-data this iteration and continues.
        * ``select.select`` timeout is clamped to ``max(0.0, ...)`` to
          avoid ``ValueError`` once the budget is exhausted.
        """
        assert self._master_fd is not None  # set by ``start``
        master_fd = self._master_fd
        buffer = bytearray()
        start_time = time.monotonic()
        last_byte_time = start_time

        while True:
            now = time.monotonic()
            elapsed = now - start_time
            remaining = timeout - elapsed
            # Clamp non-negative — ``select.select`` raises ``ValueError``
            # on negative timeouts.
            select_timeout = max(0.0, min(idle_window, remaining))

            try:
                ready, _, _ = select.select([master_fd], [], [], select_timeout)
            except (OSError, ValueError):
                # ``ValueError`` means master_fd was already closed;
                # ``OSError`` (e.g. EBADF) covers the same. Return what
                # we have.
                return bytes(buffer)

            if ready:
                try:
                    chunk = os.read(master_fd, _READ_CHUNK)
                except BlockingIOError:
                    # No data despite ``select`` returning ready (rare,
                    # but possible on some PTY implementations under
                    # contention). Continue.
                    continue
                except OSError as exc:
                    # EIO: slave PTY closed (shell exited). Return
                    # accumulated bytes — caller decides whether the
                    # partial read is enough.
                    if exc.errno in (5,):  # EIO
                        return bytes(buffer)
                    # EAGAIN under non-blocking is harmless; re-loop.
                    if exc.errno in (11, 35):  # EAGAIN / EWOULDBLOCK
                        continue
                    raise
                if chunk:
                    buffer.extend(chunk)
                    last_byte_time = time.monotonic()
                else:
                    # Zero-byte read → EOF on the master fd (unusual).
                    return bytes(buffer)
            else:
                # No data this window. If buffer is non-empty AND the
                # last-byte time is at least ``idle_window`` ago, we're
                # idle-stable: return.
                if buffer and (time.monotonic() - last_byte_time) >= idle_window:
                    return bytes(buffer)

            # Timeout budget check (after each iteration so a single
            # idle-window doesn't busy-loop past the cap).
            if time.monotonic() - start_time >= timeout:
                if buffer:
                    return bytes(buffer)
                raise asyncio.TimeoutError(f"PTY read timed out after {timeout}s with no output")

    def _close_blocking(self) -> None:
        """Path-dependent teardown. Caller wraps in ``run_in_executor``.

        Idempotent: every step catches ``ProcessLookupError`` (child
        already exited) and ``OSError`` (fd already closed).

        Kill strategy (operates on the LOCAL ``pid`` variable — never on
        ``self._pid``, which is nilled at the end of this method before
        close returns):

        * **bwrap-wrapped** (``self._wrapped``): SIGKILL immediately
          (bwrap does not forward SIGTERM to the inner shell, so the 1s
          grace period is wasted — DD9), then blocking ``os.waitpid``.
          Single-pid SIGKILL reaps the whole bwrap PID namespace via
          ``--die-with-parent`` (bubblewrap.py) — do not switch to
          killpg; do not drop ``--die-with-parent`` from the
          profile/backend (DD9).
        * **passthrough**: SIGTERM → 1s poll → SIGKILL if still alive
          (preserves graceful behavior; no extra settle — there's no
          PID namespace to drain).
        """
        # Mark closed FIRST so concurrent ``is_alive`` checks short-circuit.
        if self._closed:
            return
        self._closed = True

        # Capture local copies BEFORE nilling instance state — callers
        # must never use self._pid after _close_blocking starts (reviewer medium).
        pid = self._pid
        master_fd = self._master_fd

        if pid is not None:
            if self._wrapped:
                # bwrap-wrapped path: SIGKILL-fast (no SIGTERM grace).
                # Single-pid SIGKILL reaps the whole bwrap PID namespace via
                # --die-with-parent (bubblewrap.py) — do not switch to
                # killpg; do not drop --die-with-parent from the
                # profile/backend (DD9).
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
            else:
                # Passthrough path: SIGTERM-first (preserve graceful behavior).
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pid = None  # already gone

                # Poll up to 1s for graceful exit.
                if pid is not None:
                    deadline = time.monotonic() + 1.0
                    reaped = False
                    while time.monotonic() < deadline:
                        try:
                            done, _status = os.waitpid(pid, os.WNOHANG)
                        except ChildProcessError:
                            reaped = True
                            break
                        if done != 0:
                            reaped = True
                            break
                        time.sleep(0.05)
                    if not reaped:
                        # SIGKILL + blocking reap.
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            os.waitpid(pid, 0)
                        except ChildProcessError:
                            pass

        # Close master_fd last — once closed, any concurrent reads return
        # immediately.
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

        self._pid = None
        self._master_fd = None


def create_pty_session(
    cwd: Path | None = None,
    shell: str | None = None,
    profile: SandboxProfile | None = None,
) -> PtySession:
    """Platform-dispatching factory.

    On POSIX (``os.name == "posix"``) returns a ``UnixPtySession``.
    On other platforms the import-time guard at the top of this module
    already raised, so this branch is unreachable; the explicit check
    here is belt-and-suspenders for defensive programming.

    Args:
        cwd: Optional working directory for the spawned shell.
        shell: Optional explicit shell path override.
        profile: Optional ``SandboxProfile`` controlling sandbox policy.
            When ``None`` on a bubblewrap host a strict-floor profile is
            used (no writable paths). The tool layer always supplies a
            real profile; unit tests pin to passthrough via
            ``THE_ONE_SANDBOX_DISABLED=1``.
    """
    if os.name == "posix":
        return UnixPtySession(cwd=cwd, shell=shell, profile=profile)
    raise NotImplementedError(f"PTY sessions not supported on os.name={os.name!r}")
