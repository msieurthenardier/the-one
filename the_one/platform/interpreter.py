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

F14 L4: ``run_python`` gains an optional ``profile`` keyword (``SandboxProfile
| None = None``). With ``profile is None`` the behavior is byte-for-byte
identical to the pre-F14 implementation (platform tests call with no profile).
With a profile the sandboxed seam path is taken: ``get_sandbox_backend()`` +
``prepare_spawn`` + ``create_subprocess_exec``. Same kill/session semantics on
both paths.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from the_one.platform.env import _build_subprocess_env, is_frozen

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import SandboxProfile

# Operator override for the external interpreter (M15 F5 L1, DD3). Read from raw
# ``os.environ`` — same plumbing-level convention as ``THE_ONE_EXTRA_PATH``.
_PYTHON_OVERRIDE_ENV = "THE_ONE_PYTHON"


class FrozenInterpreterError(RuntimeError):
    """No external Python interpreter could be resolved from a frozen app.

    Raised by :func:`resolve_python` when running frozen and neither
    ``THE_ONE_PYTHON`` nor a ``python``/``python3`` on the (augmented) PATH
    resolves to a real interpreter. The message is operator-actionable and
    deliberately non-Docker (Mission 15 retired Docker).
    """


def resolve_python() -> str:
    """Return the path of the Python interpreter to use for subprocess invocations.

    **Frozen app (M15 F5 L1, DD3):** ``sys.executable`` is the frozen app
    binary, NOT a Python interpreter — returning it would re-launch the app.
    Instead resolve a *real external* interpreter by absolute path: honor the
    ``THE_ONE_PYTHON`` override, else search the frozen-augmented PATH (via the
    cleaned subprocess env) for ``python3``/``python`` with ``shutil.which``. If
    none is found, raise :class:`FrozenInterpreterError` with actionable,
    non-Docker guidance (install Python or set ``THE_ONE_PYTHON``).

    **Non-frozen (unchanged):** returns the *resolved* real path of
    ``sys.executable``: follows symlinks so that a venv interpreter (e.g.
    ``.venv/bin/python`` → ``/usr/bin/python3.12``) resolves to the real system
    path.  This is required for boxed (``minimal_rootfs=True``) bwrap spawns: the
    box mounts only ``/usr``, so the interpreter must resolve to a path inside
    ``/usr``.  A symlink under ``/home`` or ``/app`` (as produced by
    ``python -m venv``) is NOT visible inside the box and would cause
    ``bwrap: execvp …: No such file or directory``.

    On merged-usr Debian/Ubuntu hosts (the deployment target), venv symlinks
    always resolve into ``/usr``, so no new bind-mount is needed.  If a future
    host has an interpreter genuinely outside ``/usr``, the boxed spawn will
    fail at ``execvp`` with a clear error — surfacing the need to add a
    read-only interpreter bind rather than silently widening the box.

    Works on Windows (``python.exe`` has no symlinks to resolve),
    macOS, and Linux.  Single site for future venv-aware logic.
    """
    if is_frozen():
        return _resolve_frozen_python()
    return str(Path(sys.executable).resolve())


def _resolve_frozen_python() -> str:
    """Resolve a real external interpreter for a frozen app, or raise.

    Searches ``THE_ONE_PYTHON`` then ``python3``/``python`` on the
    frozen-augmented PATH. Returns an absolute path. Raises
    :class:`FrozenInterpreterError` (actionable, non-Docker) when none is found.
    """
    # The cleaned subprocess env carries the frozen-augmented, bundle-stripped
    # PATH; resolve interpreters against it (not the app's stripped GUI PATH).
    search_path = _build_subprocess_env().get("PATH") or None

    override = os.environ.get(_PYTHON_OVERRIDE_ENV, "").strip()
    candidates: list[str]
    if override:
        candidates = [override]
    else:
        candidates = ["python3", "python"]

    for cand in candidates:
        # An override given as an absolute/relative path resolves directly;
        # a bare name resolves against the augmented PATH.
        found = shutil.which(cand, path=search_path)
        if found:
            return str(Path(found).resolve())

    if override:
        detail = (
            f"the interpreter set in {_PYTHON_OVERRIDE_ENV}={override!r} was not "
            f"found or is not executable"
        )
    else:
        detail = "no `python3`/`python` interpreter was found on PATH"
    raise FrozenInterpreterError(
        "The packaged app needs an external Python interpreter to run Python "
        f"tools, but {detail}. Install Python 3.11+ (https://python.org or your "
        f"system package manager) so `python`/`python3` is on PATH, or set "
        f"{_PYTHON_OVERRIDE_ENV} to the absolute path of a Python interpreter."
    )


async def run_python(
    code: str,
    *,
    timeout: float,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    profile: "SandboxProfile | None" = None,
) -> tuple[bytes, bytes, int]:
    """Run ``code`` via ``python -c``; return ``(stdout, stderr, returncode)``.

    **Legacy path (``profile is None``):** uses
    ``asyncio.create_subprocess_exec`` with the interpreter from
    ``resolve_python()``. Behavior is byte-for-byte identical to the pre-F14
    implementation; platform tests calling with no profile continue to work
    unchanged.

    **Sandboxed path (``profile is not None``):** obtains the sandbox backend
    via ``get_sandbox_backend()``, calls ``backend.prepare_spawn(profile,
    resolve_python(), ["-c", code], ...)`` then spawns via
    ``create_subprocess_exec``. Same kill/session semantics as the legacy path.

    ``env=None`` means inherit the parent environment (legacy path only); a
    dict replaces the environment entirely. ``cwd=None`` (default) inherits
    the agent server's CWD; a value is coerced via ``str(cwd)`` and passed
    to ``create_subprocess_exec``.

    On timeout, kills the subprocess, re-drains pipes via a second
    ``communicate()`` call, and re-raises ``asyncio.TimeoutError``.
    """
    if profile is None:
        # Legacy path — unchanged behavior (platform tests call here with no profile).
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

    # Sandboxed seam path (profile is not None).
    # Function-level import to avoid any platform↔platform.sandbox import cycle.
    from the_one.platform.sandbox import get_sandbox_backend
    from the_one.platform.sandbox._seam import warn_if_isolation_unenforced

    backend = get_sandbox_backend()
    warn_if_isolation_unenforced(profile, backend)
    spec = backend.prepare_spawn(
        profile,
        resolve_python(),
        ["-c", code],
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
    we ``killpg`` the whole group with SIGKILL.
    """
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError):
            pass
    proc.kill()
