"""Shared helpers for @requires_bwrap sandbox tests.

This is a plain importable module (not a conftest plugin).  The leading
underscore keeps pytest from collecting it as a test module.

Helpers provided:

- ``sleep_pids()`` — snapshot of 'sleep 30' PIDs visible in /proc.
- ``home_workspace(suffix)`` — context manager; creates ~/.the-one-test-{suffix},
  yields the Path, rmtrees on exit.
- ``loopback_server()`` — context manager; binds 127.0.0.1:0, starts a daemon
  accept-thread that sends b"hello" to each client, yields the bound port, tears
  down the socket and thread on exit.
- ``make_denylist_secret(workspace)`` — materializes workspace/secret/key with
  "original-content"; returns (secret_dir, secret_file).

Scope: ``test_builtin_tool_sandbox.py`` + ``test_pty_sandbox.py`` only.
``test_mcp_sandbox_integration.py`` uses a different shape (``/var/tmp`` +
``writable_scratch_dir`` fixture + ``MCPClient`` + external DNS probe) — no
shared helper applies there.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def sleep_pids() -> set[str]:
    """Return PIDs of any 'sleep 30' processes visible in /proc."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "sleep 30"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return set(out.strip().split())
    except subprocess.CalledProcessError:
        return set()


@contextmanager
def home_workspace(suffix: str) -> Iterator[Path]:
    """Create ``~/.the-one-test-{suffix}``, yield it, then remove it on exit.

    All sandbox tests must create workspaces under HOME (not /tmp) because bwrap
    mounts a fresh tmpfs at /tmp, making any /tmp path invisible inside the sandbox.
    """
    workspace = Path.home() / f".the-one-test-{suffix}"
    workspace.mkdir(exist_ok=True)
    try:
        yield workspace
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@contextmanager
def loopback_server() -> Iterator[int]:
    """Bind a minimal TCP server on 127.0.0.1:0, yield the bound port.

    The server runs a daemon accept-thread that sends b"hello" to each
    connecting client.  On exit, the stop-event is set, the socket is
    closed, and the thread is joined (no leaked threads).

    Note: this CM wraps only the server (socket + thread lifetime).  The
    workspace cleanup is the caller's responsibility (use ``home_workspace``).
    The probe code/cmd is intentionally NOT shared — the builtin test uses an
    inline Python ``connect_code`` string; the PTY test uses a single-line
    ``connect_cmd`` with the ``"con"+"nected"`` echo-avoidance trick.
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(5)
    server_port = server_sock.getsockname()[1]
    server_sock.settimeout(5.0)

    stop_event = threading.Event()

    def _serve() -> None:
        while not stop_event.is_set():
            try:
                conn, _ = server_sock.accept()
                conn.sendall(b"hello")
                conn.close()
            except Exception:
                break

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    try:
        yield server_port
    finally:
        stop_event.set()
        server_sock.close()
        t.join(timeout=2)


def make_denylist_secret(workspace: Path) -> tuple[Path, Path]:
    """Materialize ``workspace/secret/key`` = ``"original-content"``.

    Returns ``(secret_dir, secret_file)``.

    **Footgun — ``--ro-bind-try`` silently skips absent paths**: the denylist
    directory MUST exist on the host before bwrap is launched.  If the path is
    absent, ``--ro-bind-try`` silently skips it, the directory is NOT mounted
    read-only inside the sandbox, and any write-protection check will
    false-pass.  This helper creates the directory and file before control
    returns to the caller, satisfying that contract.

    Cross-reference: the full operator-facing documentation of this footgun
    lives in ``debt-and-docs``; the canonical note lives here (on the helper
    whose contract depends on pre-existence).
    """
    secret_dir = workspace / "secret"
    secret_dir.mkdir(exist_ok=True)
    secret_file = secret_dir / "key"
    secret_file.write_text("original-content")
    return secret_dir, secret_file
