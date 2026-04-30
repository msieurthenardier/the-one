"""Shell helpers — cross-platform contract.

Two helpers with a deliberate divergence:

    select_shell() reports the shell *the agent or operator would prefer*.
        On POSIX it honors ``$SHELL`` (falling back to ``/bin/sh`` when unset
        or empty); on Windows it returns ``cmd.exe``. F4 may use this to
        construct an explicit shell invocation via ``create_subprocess_exec``.

    run_shell() lets the OS pick the shell — it calls
        ``asyncio.create_subprocess_shell`` which uses ``/bin/sh`` on POSIX
        and ``cmd.exe`` on Windows regardless of ``$SHELL``. This preserves
        today's ``ShellTool`` semantics byte-for-byte; F4 may unify these by
        passing the selected shell explicitly.

Both return raw bytes; decoding is the caller's responsibility (preserving
the existing ``decode(errors="replace")`` policy in ``ShellTool``).

Subprocess lifecycle (timeout handling):
    On ``asyncio.TimeoutError`` the helper kills the subprocess and re-drains
    pipes with a second ``proc.communicate()`` before re-raising. The second
    ``communicate`` (rather than ``proc.wait()``) is necessary because the
    cancelled first ``communicate`` left ``StreamReader`` tasks attached to
    the pipes; a bare ``wait()`` can hang waiting for those readers to drain.
    Callers cannot leak zombies even if they fail to handle the exception.
"""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path


def select_shell() -> tuple[str, list[str]]:
    """Return ``(shell_executable, args_prefix)`` for this platform.

    On POSIX (``os.name == "posix"``): honors ``$SHELL``, falling back to
    ``/bin/sh`` when the variable is unset *or* empty (``""``). Returns
    ``(shell, ["-c"])``.

    On Windows (``os.name == "nt"``): returns ``("cmd.exe", ["/c"])``.

    ``os.name`` is used (not ``sys.platform``) because it cleanly maps
    Linux/macOS/WSL to ``"posix"`` and Windows to ``"nt"``.
    """
    if os.name == "nt":
        return ("cmd.exe", ["/c"])
    # POSIX (Linux, macOS, WSL).
    shell = os.environ.get("SHELL") or "/bin/sh"
    return (shell, ["-c"])


async def run_shell(
    command: str,
    *,
    timeout: float,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> tuple[bytes, bytes, int]:
    """Run ``command`` via the OS shell; return ``(stdout, stderr, returncode)``.

    Uses ``asyncio.create_subprocess_shell`` (the OS picks the shell — see
    module docstring for the deliberate divergence from ``select_shell``).
    Returns raw bytes; the caller decides decode policy.

    ``env=None`` means inherit the parent environment (today's behavior); a
    dict replaces the environment entirely.

    ``cwd=None`` means inherit the parent process's cwd (today's behavior); a
    str or Path is passed to ``create_subprocess_shell`` (coerced to ``str``
    for cross-platform safety). F4 callers pass a canonicalized cwd validated
    via ``the_one.tools.execution._cwd_check``.

    On timeout, kills the subprocess, re-drains pipes via a second
    ``communicate()`` call, and re-raises ``asyncio.TimeoutError``.
    """
    # ``start_new_session=True`` (POSIX) puts the subprocess in its own
    # process group so we can SIGKILL the entire group on timeout — otherwise
    # killing only the shell leaves grandchildren (e.g. the ``sleep`` in
    # ``sh -c "sleep 5"``) holding the stdout/stderr pipes open, and the
    # subsequent ``communicate()`` blocks until those grandchildren exit.
    popen_kwargs: dict[str, object] = {}
    if env is not None:
        popen_kwargs["env"] = env
    if cwd is not None:
        # ``str(cwd)`` is the safe cross-platform default —
        # ``create_subprocess_shell`` accepts both str and Path on POSIX, but
        # str is the common-denominator type Python's subprocess plumbing
        # handles uniformly across platforms.
        popen_kwargs["cwd"] = str(cwd)
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **popen_kwargs,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        _kill_process_tree(proc)
        # Re-drain pipes and reap the process. ``await proc.wait()`` can hang
        # here because the cancelled ``communicate()`` left ``StreamReader``
        # tasks attached to the pipes; a second ``communicate()`` drains and
        # reaps in one call.
        await proc.communicate()
        raise
    return stdout, stderr, proc.returncode


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Best-effort kill of the subprocess and any descendants.

    On POSIX, the subprocess was launched with ``start_new_session=True``, so
    we ``killpg`` the whole group with SIGKILL. On Windows, ``proc.kill`` on
    the top-level process is the platform-appropriate behavior (Job-object
    based tree-kill is a future-flight concern).
    """
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError):
            # Fall through to proc.kill() — the group may have already exited.
            pass
    proc.kill()
