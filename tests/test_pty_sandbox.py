"""@requires_bwrap orphan-survival and containment tests for PTY sandbox seam (M14 F2 L1/L3).

Verifies that closing a bwrap-wrapped PTY session reaps all descendant
processes in the PID namespace — not just the direct shell child.
Also verifies write-containment, denylist enforcement, network isolation,
and real-HOME persistence for bwrap-wrapped PTY sessions.

Also covers boxed PTY session properties (M14 F4 L4):
  * scratch persists across sends (install-then-use semantics).
  * cleanup on explicit close: scratch dir is gone after close().
  * host file canary is unreadable from inside a boxed session.
  * host_access=True session reads the host canary (escalated mode intact).

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

import errno
import os
import signal
import stat
import sys
import time
from pathlib import Path

import pytest

from tests._sandbox_fixtures import (
    home_workspace,
    loopback_server,
    make_denylist_secret,
    sleep_pids,
)
from the_one.platform.pty import create_pty_session
from the_one.platform.sandbox.base import SandboxProfile
from the_one.tools.execution import _build_boxed_profile

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
    with home_workspace("pty-orphan") as workspace:
        # Build a profile that allows writes inside the workspace and
        # sets HOME so the shell has a writable home directory.
        prof = SandboxProfile(
            writable_paths=[str(workspace)],
            network_allowed=False,
            home=str(home),
        )

        session = create_pty_session(cwd=workspace, profile=prof)
        await session.start()

        try:
            # Snapshot PIDs before launching the grandchild.
            pids_before = sleep_pids()

            # Launch a backgrounded sleep inside the session.
            # --unshare-pid gives the process a namespace-local PID but does
            # NOT hide it from host /proc, so host pgrep sees it under its
            # real host PID.
            await session.send("sleep 30 &\n")

            # Give the shell a moment to fork the grandchild.
            time.sleep(0.2)

            # Snapshot PIDs after launching; there should be at least one new one.
            pids_after_spawn = sleep_pids()
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

            pids_after_close = sleep_pids()
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


# ---------------------------------------------------------------------------
# App-crash regression test (M14 F3 L3)
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
def test_pty_app_crash_reaps_grandchild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Killing the PTY session's parent process (without calling close()) reaps grandchildren.

    This test proves the INVARIANT: when the process that owns a bwrap-wrapped PTY session
    dies (simulating an app crash, SIGKILL, or unhandled exception), the sandboxed
    grandchild processes are reaped within ~1s.

    It does NOT attribute the reap to our pre-execvp prctl(PR_SET_PDEATHSIG) call vs
    bwrap's own --die-with-parent.  Both mechanisms are in play; this is a regression
    guard — if either mechanism stops working, this test catches it.

    Probe: first verifies /bin/bwrap is not setuid and has no file capabilities.
    If bwrap is setuid/setcap on this host, prctl(PR_SET_PDEATHSIG) is cleared on
    execve of bwrap, making the attribution ambiguous and this test unreliable —
    pytest.skip rather than false-pass.
    """
    # --- Probe: /bin/bwrap must NOT be setuid or file-capped ---
    bwrap_stat = os.stat("/bin/bwrap")
    if bwrap_stat.st_mode & stat.S_ISUID:
        pytest.skip("/bin/bwrap is setuid — pdeathsig cleared on execve; test would be unreliable")

    try:
        cap_data = os.getxattr("/bin/bwrap", "security.capability")
        if cap_data:
            pytest.skip(
                "/bin/bwrap has file capabilities — pdeathsig cleared on execve; "
                "test would be unreliable"
            )
    except OSError as e:
        # errno.ENODATA (61) or errno.ENOTSUP (95) → no capabilities → proceed
        if e.errno not in (errno.ENODATA, errno.ENOTSUP):
            raise

    # Unset bypass flag so the driver process selects BubblewrapSandbox.
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    home = Path.home()
    with home_workspace("pty-app-crash") as workspace:
        # Build the driver script that starts a PTY session and signals readiness.
        # The driver CANNOT use top-level await — it wraps async in asyncio.run().
        # It then stays alive via time.sleep(9999) until the test SIGKILLs it.
        # The driver inherits the test's environment (including the monkeypatched
        # THE_ONE_SANDBOX_DISABLED absence) via subprocess.Popen default inherit.
        driver_script = (
            "import asyncio, time, sys\n"
            "from pathlib import Path\n"
            "from the_one.platform.pty import create_pty_session\n"
            "from the_one.platform.sandbox.base import SandboxProfile\n"
            "async def main():\n"
            f"    ws = Path({str(workspace)!r})\n"
            f"    home = Path({str(home)!r})\n"
            "    prof = SandboxProfile(\n"
            "        writable_paths=[str(ws)],\n"
            "        network_allowed=False,\n"
            "        home=str(home),\n"
            "    )\n"
            "    s = create_pty_session(cwd=ws, profile=prof)\n"
            "    await s.start()\n"
            "    await s.send('sleep 30 &\\n')\n"
            "    print('READY', flush=True)  # readiness signal to the test\n"
            "asyncio.run(main())\n"
            "time.sleep(9999)  # stay alive until SIGKILLed\n"
        )

        import subprocess

        # Snapshot BEFORE launching the driver — this is the pre-test baseline.
        # The driver prints READY only after sleep 30 is already backgrounded, so
        # capturing here ensures new_pids is non-empty when sleep 30 is running.
        pids_before = sleep_pids()

        driver = subprocess.Popen(
            [sys.executable, "-c", driver_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            # Wait for the READY line (driver has started the PTY and launched sleep 30).
            # Use a timeout to avoid hanging if the driver crashes.
            ready_line = driver.stdout.readline()  # type: ignore[union-attr]
            assert ready_line.strip() == "READY", (
                f"Driver did not emit READY; got: {ready_line!r}. stderr: {driver.stderr.read()!r}"  # type: ignore[union-attr]
            )

            # Brief settle so the grandchild sleep 30 is fully visible in /proc.
            time.sleep(0.3)

            pids_after_driver_ready = sleep_pids()

            # New PIDs = those that appeared after the test started (our grandchild).
            new_pids = pids_after_driver_ready - pids_before

            # Assert the grandchild was actually captured — otherwise the subsequent
            # "gone" assertion trivially passes for the wrong reason.
            assert new_pids, (
                "No new 'sleep 30' PIDs found after driver sent READY. "
                "The grandchild may have failed to launch; check the driver stderr. "
                f"pids_before={pids_before}, pids_after_driver_ready={pids_after_driver_ready}"
            )

            # SIGKILL the driver without calling session.close() — simulates an app crash.
            # bwrap's --die-with-parent (prctl PR_SET_PDEATHSIG) is tied to the driver
            # process (bwrap's direct parent), so killing the driver fires bwrap's own
            # pdeathsig, collapsing the PID namespace and reaping grandchildren.
            os.kill(driver.pid, signal.SIGKILL)
            driver.wait(timeout=5)

            # Give the PID-namespace teardown time to propagate to /proc (~300ms for bwrap 0.9.0).
            time.sleep(1.0)

            pids_after_kill = sleep_pids()
            orphans = new_pids & pids_after_kill
            assert not orphans, (
                f"Orphan 'sleep 30' grandchildren remain after app-crash SIGKILL: {orphans}. "
                f"pids_before={pids_before}, new_pids={new_pids}, "
                f"pids_after_kill={pids_after_kill}. "
                "bwrap --die-with-parent or pre-execvp pdeathsig may not be firing."
            )

        finally:
            if driver.poll() is None:
                driver.kill()
                driver.wait(timeout=5)


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
    with home_workspace("pty-allowlist") as workspace:
        with home_workspace("pty-allowlist-sibling") as sibling:
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
    with home_workspace("pty-denylist") as workspace:
        secret_dir, secret_file = make_denylist_secret(workspace)

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

    home_dir = Path.home()
    with loopback_server() as server_port:
        with home_workspace("pty-network") as workspace:
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

            # --- Network denied (network_allowed=False) ---
            prof_deny = SandboxProfile(
                writable_paths=[str(workspace)],
                network_allowed=False,
                home=str(home_dir),
            )
            session_deny = create_pty_session(shell="/bin/sh", cwd=workspace, profile=prof_deny)
            await session_deny.start()
            try:
                out_deny = (await session_deny.send(connect_cmd, timeout=15.0)).decode(
                    errors="replace"
                )
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

    with home_workspace("pty-home") as workspace:
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
            assert canary.exists(), (
                f"~/canary.txt should exist on host at {canary} after sandbox write"
            )
            assert "pty-home-canary" in canary.read_text(), (
                f"~/canary.txt content mismatch: {canary.read_text()!r}"
            )
        finally:
            try:
                await session.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Boxed PTY session tests (M14 F4 L4)
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
async def test_boxed_pty_session_scratch_persists_across_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scratch persists across sends: write in send 1, read in send 2.

    The boxed session's scratch dir must survive for the whole session
    lifetime — not be removed between sends (unlike one-shot ephemeral scratch).
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("pty-box-persist") as scratch:
        profile = _build_boxed_profile(scratch)
        session = create_pty_session(cwd=scratch, profile=profile, cleanup_dir=scratch)
        await session.start()
        try:
            # Send 1: write a file into scratch.
            target = scratch / "session-file.txt"
            await session.send(f"echo session-data > {target}\n")
            # Give the shell a moment for the write to propagate to the host bind mount.
            time.sleep(0.1)

            # Intermediate check: file must be visible on the host before send 2.
            assert target.exists(), (
                f"File written in send 1 should exist on host before send 2; {target} not found"
            )

            # Send 2: verify the file is still present inside the session.
            out = (await session.send(f"cat {target}\n")).decode(errors="replace")
            assert "session-data" in out, (
                f"File written in send 1 must be readable in send 2; got: {out!r}"
            )
        finally:
            try:
                await session.close()
            except Exception:
                pass


@pytest.mark.requires_bwrap
async def test_boxed_pty_session_cleanup_on_explicit_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After explicit close(), the boxed session's scratch dir is gone from the host fs."""
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("pty-box-cleanup") as scratch_parent:
        # Create a unique scratch dir inside the workspace to serve as cleanup_dir.
        scratch = scratch_parent / "session-scratch"
        scratch.mkdir()

        profile = _build_boxed_profile(scratch)
        # Pass cleanup_dir=scratch so close() removes it.
        session = create_pty_session(cwd=scratch, profile=profile, cleanup_dir=scratch)
        await session.start()
        try:
            # Write something to confirm the session was live.
            await session.send("echo alive\n")
        finally:
            await session.close()

        # Scratch must be gone — cleanup_dir rmtree ran in _close_blocking.
        assert not scratch.exists(), (
            f"Scratch dir must be removed after session.close(); {scratch} still exists"
        )


@pytest.mark.requires_bwrap
async def test_boxed_pty_session_cannot_read_host_home_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A boxed session cannot read a file planted in the host home directory.

    The host home dir is NOT in the boxed session's writable_paths and is
    NOT in the minimal mount set, so it must be absent/unreadable inside
    the sandbox.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("pty-box-canary-scratch") as scratch:
        with home_workspace("pty-box-canary-host") as canary_dir:
            # Plant a canary on the host, outside the sandbox mount set.
            canary_file = canary_dir / "host-secret.txt"
            canary_file.write_text("host-secret-content")

            profile = _build_boxed_profile(scratch)
            session = create_pty_session(cwd=scratch, profile=profile, cleanup_dir=scratch)
            await session.start()
            try:
                out = (
                    await session.send(f"cat {canary_file} 2>/dev/null || echo absent\n")
                ).decode(errors="replace")
                assert "host-secret-content" not in out, (
                    f"Boxed session must not read host canary; got: {out!r}"
                )
            finally:
                try:
                    await session.close()
                except Exception:
                    pass

            # Canary must still exist on the host.
            assert canary_file.exists(), "Host canary must be unaffected by boxed session"
            assert canary_file.read_text() == "host-secret-content"


@pytest.mark.requires_bwrap
async def test_host_access_pty_session_reads_host_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host-mode PTY session (cleanup_dir=None) can read a file in the host workspace.

    Verify that the host-mode PTY path (cleanup_dir=None, writable_paths
    covers workspace) is intact after the boxed-mode branching was added.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    home_dir = Path.home()
    with home_workspace("pty-host-canary") as workspace:
        # Plant a canary in the allowlisted workspace (host mode).
        canary_file = workspace / "host-canary.txt"
        canary_file.write_text("host-mode-content")

        # Host profile: workspace is writable, home is real HOME.
        prof = SandboxProfile(
            writable_paths=[str(workspace)],
            network_allowed=False,
            home=str(home_dir),
        )
        # cleanup_dir=None — host session, no scratch cleanup.
        session = create_pty_session(cwd=workspace, profile=prof, cleanup_dir=None)
        await session.start()
        try:
            out = (await session.send(f"cat {canary_file}\n")).decode(errors="replace")
            assert "host-mode-content" in out, (
                f"Host-access session must read the host canary; got: {out!r}"
            )
        finally:
            try:
                await session.close()
            except Exception:
                pass

        # Canary must still exist after the session closes (cleanup_dir=None).
        assert canary_file.exists(), "Host canary must persist after host-access session close"
        assert canary_file.read_text() == "host-mode-content"


@pytest.mark.requires_bwrap
async def test_boxed_pty_session_can_write_within_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A boxed session can write files within its scratch directory."""
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("pty-box-write") as scratch:
        profile = _build_boxed_profile(scratch)
        session = create_pty_session(cwd=scratch, profile=profile, cleanup_dir=scratch)
        await session.start()
        try:
            target = scratch / "box-written.txt"
            await session.send(f"echo box-content > {target}\n")
            time.sleep(0.1)

            assert target.exists(), (
                f"File written inside boxed session must be visible on host; {target} not found"
            )
            content = target.read_text()
            assert "box-content" in content, f"Unexpected content in box-written file: {content!r}"
        finally:
            try:
                await session.close()
            except Exception:
                pass
