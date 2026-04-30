"""Python interpreter helpers — cross-platform contract.

The current ``python_exec.py`` hardcodes ``"python3"``, which is the most
blatant Linux-only assumption in the tool layer (Windows has ``python.exe``,
not ``python3``). This module replaces that with ``sys.executable``: the same
interpreter the agent itself runs under, deterministic across platforms.

We deliberately do NOT use ``shutil.which("python3")`` — that depends on PATH
order and gives wrong answers in venvs.

Forward-reference: if a later flight introduces a project-bound venv distinct
from the agent's interpreter, ``resolve_python()`` is the single site to
upgrade.

Subprocess lifecycle (timeout handling) mirrors ``shell.run_shell`` — see that
module's docstring for the kill+reap pattern and rationale.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path


def resolve_python() -> str:
    """Return the path of the Python interpreter to use for subprocess invocations.

    Returns ``sys.executable``: deterministic, matches the interpreter the
    agent itself runs under, works on Windows (``python.exe``), macOS, and
    Linux. Single site for future venv-aware logic.
    """
    return sys.executable


async def run_python(
    code: str,
    *,
    timeout: float,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> tuple[bytes, bytes, int]:
    """Run ``code`` via ``python -c``; return ``(stdout, stderr, returncode)``.

    Uses ``asyncio.create_subprocess_exec`` with the interpreter from
    ``resolve_python()``. Returns raw bytes; caller decides decode policy.

    ``env=None`` means inherit the parent environment (today's behavior); a
    dict replaces the environment entirely. ``cwd=None`` (default) inherits
    the agent server's CWD; a value is coerced via ``str(cwd)`` and passed
    to ``create_subprocess_exec``. F4 L4 widening for ``PythonExecTool``'s
    cwd argument — same shape as ``run_shell``'s widening.

    On timeout, kills the subprocess, re-drains pipes via a second
    ``communicate()`` call, and re-raises ``asyncio.TimeoutError``.
    """
    # ``start_new_session=True`` (POSIX) lets us kill the whole process group
    # on timeout — protects against runaway child processes spawned by the
    # supplied ``code``. See ``shell.run_shell`` for the full rationale.
    popen_kwargs: dict[str, object] = {}
    if env is not None:
        popen_kwargs["env"] = env
    if cwd is not None:
        popen_kwargs["cwd"] = str(cwd)
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    proc = await asyncio.create_subprocess_exec(
        resolve_python(),
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **popen_kwargs,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        _kill_process_tree(proc)
        # See shell.run_shell for the rationale: a second communicate() is
        # required to drain StreamReaders left attached by the cancelled wait.
        await proc.communicate()
        raise
    return stdout, stderr, proc.returncode


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Best-effort kill of the subprocess and any descendants.

    On POSIX, the subprocess was launched with ``start_new_session=True``, so
    we ``killpg`` the whole group with SIGKILL.
    """
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError):
            pass
    proc.kill()
