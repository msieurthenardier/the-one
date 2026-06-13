"""PTY session helpers — cross-platform contract.

This module is the platform-neutral dispatcher.  It defines the
``PtySession`` ABC and the ``create_pty_session`` factory; it contains
NO module-scope POSIX stdlib imports (no ``fcntl``, ``pty``, ``select``,
``signal``, or ``ctypes``).  The module therefore imports cleanly on
every OS (Windows, macOS, Linux).

The Unix backend (``UnixPtySession``, ``_get_libc``/``_libc`` fork-safety
singleton) lives in ``the_one.platform.pty_unix`` and is imported lazily
by ``create_pty_session()`` only on POSIX.  The Windows backend lands in
M15 F3 Leg 2.

Public surface:

    PtySession (ABC)        — async session contract: start / send / close /
                              is_alive / last_activity
    UnixPtySession          — POSIX back-compat re-export (available on
                              ``os.name == "posix"``; see re-export at
                              the bottom of this module).
    create_pty_session(...) — platform-dispatching factory; on POSIX returns
                              ``UnixPtySession``; on Windows raises
                              ``NotImplementedError`` naming Leg 2 (the module
                              still imports — that is the Leg 1 contract).

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

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import SandboxProfile


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


def create_pty_session(
    cwd: Path | None = None,
    shell: str | None = None,
    profile: SandboxProfile | None = None,
    cleanup_dir: Path | None = None,
) -> PtySession:
    """Platform-dispatching factory.

    On POSIX (``os.name == "posix"``) returns a ``UnixPtySession``
    (imported lazily so this module carries no POSIX stdlib at module scope).
    On Windows raises ``NotImplementedError`` naming Leg 2 — the module
    itself imports cleanly (that is the Leg 1 contract; DD6 cascade unblock).

    Args:
        cwd: Optional working directory for the spawned shell.
        shell: Optional explicit shell path override.
        profile: Optional ``SandboxProfile`` controlling sandbox policy.
            When ``None`` on a bubblewrap host a strict-floor profile is
            used (no writable paths). The tool layer always supplies a
            real profile; unit tests pin to passthrough via
            ``THE_ONE_SANDBOX_DISABLED=1``.
        cleanup_dir: Optional directory to remove (via ``shutil.rmtree``)
            when the session closes.  Used by boxed sessions to clean up
            their persistent scratch directory.  ``None`` for host
            sessions (no cleanup).
    """
    if os.name == "nt":
        raise NotImplementedError("WindowsPtySession lands in M15 F3 Leg 2")
    from the_one.platform.pty_unix import UnixPtySession

    return UnixPtySession(cwd=cwd, shell=shell, profile=profile, cleanup_dir=cleanup_dir)


# Back-compat re-export: ``UnixPtySession`` was previously defined directly
# in this module; existing imports (``from the_one.platform.pty import
# UnixPtySession``) must continue to work on POSIX.
#
# ORDERING CONSTRAINT — load-bearing: ``PtySession`` ABC and
# ``create_pty_session`` MUST be fully defined above this line before the
# conditional import fires.  ``pty_unix`` imports ``PtySession`` from THIS
# module (one-way edge: pty.py(ABC) ← pty_unix); the re-export below closes
# a cycle ONLY on POSIX.  Python resolves it safely because the ABC is
# already in the module's namespace by the time ``pty_unix`` tries to import
# it.  Reordering this block above the ABC definition would deadlock the
# POSIX import — do not move.  (A neutral ``pty_abc.py`` was considered and
# declined for minimal surface; revisit in Leg 2 if the cycle proves fragile.)
if os.name == "posix":
    from the_one.platform.pty_unix import UnixPtySession  # noqa: F401  (back-compat re-export)
