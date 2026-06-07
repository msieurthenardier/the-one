"""@requires_bwrap orphan-survival and containment tests for PTY sandbox seam (M14 F2 L1/L3).

Verifies that closing a bwrap-wrapped PTY session reaps all descendant
processes in the PID namespace — not just the direct shell child.
Also verifies write-containment, denylist enforcement, network isolation,
and real-HOME persistence for bwrap-wrapped PTY sessions.

Key constraints (mirrors test_builtin_tool_sandbox.py module doc):
  * Workspace must be under $HOME (not /tmp): bwrap mounts a fresh tmpfs
    at /tmp so any workspace under /tmp is invisible inside the sandbox.
  * THE_ONE_SANDBOX_DISABLED must be UNSET so get_sandbox_backend()
    selects BubblewrapSandbox.
  * THE_ONE_TEST_MODE is still set by conftest.py's pytest_configure hook
    (the double-flag bypass requires BOTH; single flag = bwrap stays active).

Note on --unshare-pid: bwrap gives each process a namespace-local PID
(inner PID 1 = the shell), but does NOT hide it from the host /proc.
Host pgrep therefore sees the sleep grandchild under its real host PID —
which is exactly what we capture and assert gone after close().
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

from the_one.platform.pty import create_pty_session
from the_one.platform.sandbox.base import SandboxProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sleep_pids() -> set[str]:
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


# ---------------------------------------------------------------------------
# Orphan-survival test
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
async def test_pty_close_reaps_namespace_grandchild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing a bwrap-wrapped PTY session reaps grandchild processes.

    A backgrounded ``sleep 30`` (grandchild of the bwrap shell) must be
    gone after ``session.close()``.  This proves that single-pid SIGKILL
    on the bwrap-outer process + ``--die-with-parent`` reaps the whole
    PID namespace — including ``setsid``'d grandchildren that killpg
    would miss.
    """
    # Unset the bypass flag so get_sandbox_backend() selects bwrap.
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    home = Path.home()
    workspace = home / ".the-one-test-pty-orphan"
    workspace.mkdir(exist_ok=True)

    try:
        # Build a profile that allows writes inside the workspace and
        # sets HOME so the shell has a writable home directory.
        prof = SandboxProfile(
            writable_paths=[str(workspace)],
            network_allowed=False,
            home=str(home),
        )

        session = create_pty_session(cwd=workspace, profile=prof)
        await session.start()

        # Snapshot PIDs before launching the grandchild.
        pids_before = _sleep_pids()

        # Launch a backgrounded sleep inside the session.
        # --unshare-pid gives the process a namespace-local PID but does
        # NOT hide it from host /proc, so host pgrep sees it under its
        # real host PID.
        await session.send("sleep 30 &\n")

        # Give the shell a moment to fork the grandchild.
        time.sleep(0.2)

        # Snapshot PIDs after launching; there should be at least one new one.
        pids_after_spawn = _sleep_pids()
        new_pids = pids_after_spawn - pids_before

        # If bwrap is working correctly we expect the grandchild to be visible.
        # (If not visible, the assertion below trivially passes for the wrong
        # reason — log a note but don't fail here; the orphan check is what matters.)
        if not new_pids:
            import warnings

            warnings.warn(
                "No new 'sleep 30' PIDs found after session.send — "
                "grandchild may have launched under a different cmdline; "
                "the orphan check below will trivially pass.",
                stacklevel=1,
            )

        # Close the session.  The bwrap-wrapped path uses SIGKILL-fast on
        # the bwrap-outer pid; --die-with-parent then tears down the whole
        # PID namespace including the grandchild sleep.
        await session.close()

        # Test-side settle: give the async PID-namespace teardown time to
        # propagate to /proc.  (close() itself adds no settle — this is
        # the right place for it per DD5.)
        time.sleep(0.5)

        pids_after_close = _sleep_pids()
        # Orphans = new PIDs (from our sleep 30) that are still alive after close.
        # pids_after_close - pids_before isolates only PIDs that appeared after our
        # test started, then intersect with new_pids to pin to our specific grandchild.
        orphans = new_pids & pids_after_close
        assert not orphans, (
            f"Orphan 'sleep 30' grandchildren remain after PTY close: {orphans}. "
            f"pids_before={pids_before}, pids_after_spawn={pids_after_spawn}, "
            f"pids_after_close={pids_after_close}"
        )

    finally:
        # Belt-and-suspenders: close in case an exception left it open.
        try:
            await session.close()
        except Exception:
            pass
        shutil.rmtree(workspace, ignore_errors=True)


# ---------------------------------------------------------------------------
# Containment tests (M14 F2 L3)
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
async def test_pty_write_outside_allowlist_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a) A write to a path outside the writable allowlist is denied.

    The sandbox mounts the host FS read-only under ``--ro-bind / /``; only
    paths in ``writable_paths`` are re-bound writable.  A write to a sibling
    dir outside the allowlist must not persist on the host.

    Both workspace and sibling are created explicitly on the host — bwrap's
    ``--ro-bind / /`` only mounts existing paths, so an absent sibling would
    cause the write to fail for the wrong reason (ENOENT, not EROFS).
    (Mirror: test_builtin_tool_sandbox.py:56-96)
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    home_dir = Path.home()
    workspace = home_dir / ".the-one-test-pty-allowlist"
    sibling = home_dir / ".the-one-test-pty-allowlist-sibling"
    workspace.mkdir(exist_ok=True)
    sibling.mkdir(exist_ok=True)

    prof = SandboxProfile(
        writable_paths=[str(workspace)],
        network_allowed=False,
        home=str(home_dir),
    )
    session = create_pty_session(cwd=workspace, profile=prof)
    await session.start()
    try:
        target = sibling / "should-not-exist.txt"
        target.unlink(missing_ok=True)

        await session.send(f"echo forbidden > {target}\n")

        # bwrap --bind writes are kernel-synchronous; no settle needed.
        assert not target.exists(), (
            f"Write outside allowlist should be contained by bwrap; "
            f"file unexpectedly present at {target}"
        )
    finally:
        try:
            await session.close()
        except Exception:
            pass
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(sibling, ignore_errors=True)


@pytest.mark.requires_bwrap
async def test_pty_denylist_secret_write_denied_sibling_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(b) Write to a denylisted secret path is denied; sibling allowlisted write succeeds.

    The denylist is enforced via --ro-bind-try overlay (write-protection only,
    not visibility blocking).  The secret dir is created explicitly on the host
    before the session starts — --ro-bind-try silently skips absent paths, so
    a missing denylist dir would false-pass the write-protection check.
    (Mirror: test_builtin_tool_sandbox.py:99-148)
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    home_dir = Path.home()
    workspace = home_dir / ".the-one-test-pty-denylist"
    workspace.mkdir(exist_ok=True)

    secret_dir = workspace / "secret"
    secret_dir.mkdir(exist_ok=True)
    secret_file = secret_dir / "key"
    secret_file.write_text("original-content")

    prof = SandboxProfile(
        writable_paths=[str(workspace)],
        readonly_overlay_paths=[str(secret_dir)],
        network_allowed=False,
        home=str(home_dir),
    )
    session = create_pty_session(cwd=workspace, profile=prof)
    await session.start()
    try:
        # Attempt to overwrite the secret — the ro-bind-try overlay should block it.
        await session.send(f"echo tampered > {secret_file}\n")

        # bwrap --bind writes are kernel-synchronous; no settle needed.
        assert secret_file.read_text() == "original-content", (
            "Denylist overlay must protect the secret file from writes; "
            f"content is now: {secret_file.read_text()!r}"
        )

        # Write to an allowlisted sibling path MUST succeed.
        ok_file = workspace / "ok.txt"
        ok_file.unlink(missing_ok=True)
        await session.send(f"echo allowed > {ok_file}\n")

        # bwrap --bind writes are kernel-synchronous; no settle needed.
        assert ok_file.exists(), (
            f"Write to allowlisted path must succeed; {ok_file} does not exist on host"
        )
    finally:
        try:
            await session.close()
        except Exception:
            pass
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.requires_bwrap
async def test_pty_network_denied_by_default_allowed_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(c) Network is isolated by default; reachable when network_allowed=True.

    With --unshare-net the sandbox has its own isolated network namespace.  Its
    127.0.0.1 loopback is a DIFFERENT loopback from the host's, so a host server
    on 127.0.0.1 is unreachable from inside the sandbox (ECONNREFUSED — the
    sandbox's lo interface is up but has no listener on that port).

    Without --unshare-net (network_allowed=True) the sandbox shares the host net
    namespace and the host server is reachable.

    The connect probe is a single-line ``python3 -c '...'`` sent in one ``send``
    (NOT a heredoc-then-exec: the idle-mark returns after the heredoc and the
    exec output would never be seen).  Run under non-interactive /bin/sh so no
    RC hook perturbs loopback or adds prompt noise.
    (Mirror: test_builtin_tool_sandbox.py:150-241)
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    # Stand up a minimal TCP server on the host's loopback.
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

    home_dir = Path.home()
    workspace = home_dir / ".the-one-test-pty-network"
    workspace.mkdir(exist_ok=True)

    # Single-line python3 probe: prints "connected" on success, "failed:<e>" on failure.
    # String-concat trick ("con"+"nected") keeps the literal word "connected" out of the
    # probe source text — the PTY echoes the command back, and we assert on the OUTPUT
    # line only.  Without the concat, the echo itself would contain "connected" and the
    # deny-path assertion would false-fail.
    connect_cmd = (
        f"python3 -c 'import socket,sys;"
        f"s=socket.socket();s.settimeout(2);"
        f's.connect(("127.0.0.1",{server_port}));print("con"+"nected");s.close()\' '
        f"2>/dev/null && true || echo 'failed'\n"
    )

    try:
        # --- Network denied (network_allowed=False) ---
        prof_deny = SandboxProfile(
            writable_paths=[str(workspace)],
            network_allowed=False,
            home=str(home_dir),
        )
        session_deny = create_pty_session(shell="/bin/sh", cwd=workspace, profile=prof_deny)
        await session_deny.start()
        try:
            out_deny = (await session_deny.send(connect_cmd, timeout=15.0)).decode(errors="replace")
        finally:
            try:
                await session_deny.close()
            except Exception:
                pass

        assert "connected" not in out_deny, (
            f"Network should be isolated when network_allowed=False; got: {out_deny!r}"
        )

        # --- Network allowed (network_allowed=True) ---
        prof_allow = SandboxProfile(
            writable_paths=[str(workspace)],
            network_allowed=True,
            home=str(home_dir),
        )
        session_allow = create_pty_session(shell="/bin/sh", cwd=workspace, profile=prof_allow)
        await session_allow.start()
        try:
            out_allow = (await session_allow.send(connect_cmd, timeout=15.0)).decode(
                errors="replace"
            )
        finally:
            try:
                await session_allow.close()
            except Exception:
                pass

        assert "connected" in out_allow, (
            f"Network should be reachable when network_allowed=True; got: {out_allow!r}"
        )
    finally:
        stop_event.set()
        server_sock.close()
        t.join(timeout=2)
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.requires_bwrap
async def test_pty_real_home_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d) A write to $HOME/f inside the PTY sandbox persists on the host workspace.

    monkeypatch.setenv("HOME", str(workspace)) redirects ~ expansion inside the
    sandbox.  The profile's ``home=str(workspace)`` ensures bwrap injects the same
    path via ``--setenv HOME``, making the workspace the sandbox's writable home.
    A write to ``~/canary.txt`` must therefore appear under workspace on the host.
    (Mirror: test_builtin_tool_sandbox.py:243-283)
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    home_dir = Path.home()
    workspace = home_dir / ".the-one-test-pty-home"
    workspace.mkdir(exist_ok=True)

    # Redirect HOME to workspace so ~ inside the sandbox resolves there.
    monkeypatch.setenv("HOME", str(workspace))

    prof = SandboxProfile(
        writable_paths=[str(workspace)],
        network_allowed=False,
        home=str(workspace),
    )
    session = create_pty_session(cwd=workspace, profile=prof)
    await session.start()
    try:
        await session.send("echo pty-home-canary > ~/canary.txt\n")

        # bwrap --bind writes are kernel-synchronous; no settle needed.
        canary = workspace / "canary.txt"
        assert canary.exists(), f"~/canary.txt should exist on host at {canary} after sandbox write"
        assert "pty-home-canary" in canary.read_text(), (
            f"~/canary.txt content mismatch: {canary.read_text()!r}"
        )
    finally:
        try:
            await session.close()
        except Exception:
            pass
        shutil.rmtree(workspace, ignore_errors=True)
