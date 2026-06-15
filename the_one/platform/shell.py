"""Shell helpers — cross-platform contract.

Two helpers with a deliberate divergence:

    select_shell() reports the shell *the agent or operator would prefer*.
        On POSIX it honors ``$SHELL`` (falling back to ``/bin/sh`` when unset
        or empty); on Windows it returns ``cmd.exe``. F14 L4 uses this to
        construct an explicit shell invocation via ``create_subprocess_exec``
        on the sandboxed path (DD7).

    run_shell() lets the OS pick the shell on the legacy (no-profile) path —
        it calls ``asyncio.create_subprocess_shell`` which uses ``/bin/sh`` on
        POSIX and ``cmd.exe`` on Windows regardless of ``$SHELL``. This
        preserves today's ``ShellTool`` semantics byte-for-byte when
        ``profile is None``.

        When ``profile`` is provided, run_shell() takes the sandboxed seam
        path: calls ``get_sandbox_backend().prepare_spawn()`` and spawns via
        ``create_subprocess_exec`` using ``select_shell()`` (DD7 — $SHELL-
        honoring, falls back to /bin/sh). The same kill/session pattern is
        used on both paths.

Both return raw bytes; decoding is the caller's responsibility (preserving
the existing ``decode(errors="replace")`` policy in ``ShellTool``).

Subprocess lifecycle (timeout handling):
    On ``asyncio.TimeoutError`` the helper kills the subprocess and re-drains
    pipes with a second ``communicate()`` before re-raising. The second
    ``communicate`` (rather than ``proc.wait()``) is necessary because the
    cancelled first ``communicate`` left ``StreamReader`` tasks attached to
    the pipes; a bare ``wait()`` can hang waiting for those readers to drain.
    Callers cannot leak zombies even if they fail to handle the exception.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from the_one.platform.env import _build_subprocess_env, is_frozen

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import SandboxProfile


def select_shell() -> tuple[str, list[str]]:
    """Return ``(shell_executable, args_prefix)`` for this platform.

    On POSIX (``os.name == "posix"``): honors ``$SHELL``, falling back to
    ``/bin/sh`` when the variable is unset *or* empty (``""``). Returns
    ``(shell, ["-c"])``.

    On Windows (``os.name == "nt"``): returns ``("cmd.exe", ["/c"])``.

    **Frozen posture (M15 F5 L1, DD3):** on POSIX, when frozen, resolve the
    shell to an *absolute path* (via the frozen-augmented PATH, falling back to
    ``/bin/sh``) so there is no bare-name exec against a stripped GUI PATH. The
    Windows ``cmd.exe`` path already resolves via Win32 and is left unchanged.
    Non-frozen behavior is byte-for-byte identical to before.

    ``os.name`` is used (not ``sys.platform``) because it cleanly maps
    Linux/macOS/WSL to ``"posix"`` and Windows to ``"nt"``.
    """
    if os.name == "nt":
        return ("cmd.exe", ["/c"])
    # POSIX (Linux, macOS, WSL).
    shell = os.environ.get("SHELL") or "/bin/sh"
    if is_frozen() and not os.path.isabs(shell):
        # Resolve the bare shell name against the frozen-augmented PATH so the
        # post-fork execvp doesn't hit a stripped PATH. Fall back to /bin/sh
        # (an absolute, ~universally-present POSIX shell).
        search_path = _build_subprocess_env().get("PATH") or None
        resolved = shutil.which(shell, path=search_path)
        shell = resolved or "/bin/sh"
    return (shell, ["-c"])


async def run_shell(
    command: str,
    *,
    timeout: float,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    profile: "SandboxProfile | None" = None,
) -> tuple[bytes, bytes, int]:
    """Run ``command`` via the OS shell; return ``(stdout, stderr, returncode)``.

    **Legacy path (``profile is None``):** uses
    ``asyncio.create_subprocess_shell`` (the OS picks the shell — see module
    docstring for the deliberate divergence from ``select_shell``). Behavior
    is byte-for-byte identical to the pre-F14 implementation; platform tests
    calling with no profile continue to work unchanged.

    **Sandboxed path (``profile is not None``):** obtains the sandbox backend
    via ``get_sandbox_backend()``, calls ``backend.prepare_spawn(profile,
    shell, ["-c", command], ...)`` where ``shell`` comes from
    ``select_shell()`` (DD7 — honors ``$SHELL``, fallback ``/bin/sh``), then
    spawns via ``create_subprocess_exec``. Kill/session semantics are
    identical to the legacy path.

    ``env=None`` means inherit the parent environment (legacy path only); a
    dict replaces the environment entirely.

    ``cwd=None`` means inherit the parent process's cwd; a str or Path is
    coerced to ``str`` and passed to the subprocess creation call.

    On timeout, kills the subprocess, re-drains pipes via a second
    ``communicate()`` call, and re-raises ``asyncio.TimeoutError``.
    """
    if profile is None:
        # Legacy path — unchanged behavior (platform tests call here with no profile).
        popen_kwargs: dict[str, object] = {}
        if env is not None:
            popen_kwargs["env"] = env
        if cwd is not None:
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
            await proc.communicate()
            raise
        return stdout, stderr, proc.returncode

    # Sandboxed seam path (profile is not None).
    # Function-level import to avoid any platform↔platform.sandbox import cycle.
    from the_one.platform.sandbox import get_sandbox_backend
    from the_one.platform.sandbox._seam import warn_if_isolation_unenforced

    shell_exe, prefix = select_shell()
    backend = get_sandbox_backend()
    warn_if_isolation_unenforced(profile, backend)
    spec = backend.prepare_spawn(
        profile,
        shell_exe,
        [*prefix, command],
        env or {},
        str(cwd) if cwd is not None else None,
    )

    session_kwargs: dict[str, object] = {}
    if os.name == "posix":
        session_kwargs["start_new_session"] = True

    proc = await asyncio.create_subprocess_exec(
        spec.command,
        *spec.args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=spec.env,
        cwd=spec.cwd,
        **session_kwargs,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        _kill_process_tree(proc)
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
