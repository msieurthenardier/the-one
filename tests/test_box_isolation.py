"""@requires_bwrap DD2 gate: boxed (minimal_rootfs) isolation tests (F04 L01).

These tests verify that ``SandboxProfile(minimal_rootfs=True, ...)`` in the
bubblewrap backend produces genuine isolation — the user filesystem is absent,
a planted host canary is unreadable, and the system runtime (python3 + /bin/sh)
still executes.

Key design decisions (from leg spec):
  * Drive the python3 runtime check via ``run_python`` (NOT run_shell) — under
    ``--clearenv`` there is no PATH, so ``run_shell("python3 …")`` would fail
    "not found".  ``run_python`` passes ``sys.executable``
    (``/usr/local/bin/python3``, inside ``/usr`` → bound) directly as the
    command.
  * Workspaces are created under HOME (not /tmp) — bwrap mounts a fresh tmpfs
    at /tmp, making any /tmp path invisible inside the sandbox.
  * THE_ONE_SANDBOX_DISABLED must be UNSET so the factory selects
    BubblewrapSandbox.

Assertions:
  (a) python3 runtime: ``import sys, json, os, ssl, sqlite3; print('ok')`` → ok
  (b) /bin/sh exec: ``/bin/sh -c "echo hi"`` → hi
  (c) host-home canary is NOT present / unreadable inside the box
  (d) ls / has no root, home, app, var
  (e) scratch writable inside the box AND visible on the host fs
  (f) /proc/net/dev shows loopback only (--unshare-net)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._sandbox_fixtures import home_workspace
from the_one.platform.interpreter import run_python
from the_one.platform.sandbox.base import SandboxProfile
from the_one.platform.shell import run_shell


def _boxed_profile(scratch: Path) -> SandboxProfile:
    """Return a boxed SandboxProfile with ``scratch`` as the only writable path."""
    return SandboxProfile(
        minimal_rootfs=True,
        writable_paths=[str(scratch)],
        home=str(scratch),
        network_allowed=False,
    )


# ---------------------------------------------------------------------------
# Helper: run a command synchronously inside the test (all tests are async
# but the helper is used only from within async test bodies).
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
async def test_boxed_python_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """(a) python3 runtime works inside a boxed spawn (import stdlib modules)."""
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("box-python") as scratch:
        profile = _boxed_profile(scratch)
        code = "import sys, json, os, ssl, sqlite3; print('ok')"
        stdout, stderr, rc = await run_python(code, timeout=30.0, env={}, profile=profile)
        output = stdout.decode(errors="replace").strip()
        assert output == "ok", (
            f"python3 runtime check failed inside boxed spawn; "
            f"rc={rc!r} stdout={stdout!r} stderr={stderr!r}"
        )


@pytest.mark.requires_bwrap
async def test_boxed_sh_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    """(b) /bin/sh executes via run_shell inside a boxed spawn."""
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("box-sh") as scratch:
        profile = _boxed_profile(scratch)
        # Use full path /bin/sh so --clearenv (no PATH) is not a problem.
        stdout, stderr, rc = await run_shell(
            "/bin/sh -c 'echo hi'",
            timeout=30.0,
            env={},
            profile=profile,
        )
        output = stdout.decode(errors="replace").strip()
        assert output == "hi", (
            f"/bin/sh exec check failed inside boxed spawn; "
            f"rc={rc!r} stdout={stdout!r} stderr={stderr!r}"
        )


@pytest.mark.requires_bwrap
async def test_boxed_canary_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) A canary file planted in a host-home dir is unreadable inside the box.

    The canary dir is NOT in writable_paths and NOT in the minimal mount set,
    so it must be absent/unreadable inside the sandbox.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("box-scratch") as scratch:
        with home_workspace("box-canary") as canary_dir:
            # Plant a canary file in the canary dir (outside the sandbox writable set).
            canary_file = canary_dir / "canary.txt"
            canary_file.write_text("canary-secret")

            profile = _boxed_profile(scratch)
            # Try to read the canary — should fail (file not present in box).
            stdout, _stderr, rc = await run_shell(
                f"/bin/sh -c 'cat {canary_file} 2>/dev/null || echo absent'",
                timeout=30.0,
                env={},
                profile=profile,
            )
            output = stdout.decode(errors="replace").strip()
            assert "canary-secret" not in output, (
                f"Canary should be unreadable inside the box; got: {output!r}"
            )
            # Canary should still exist on the host.
            assert canary_file.exists(), "Canary file must still exist on the host"
            assert canary_file.read_text() == "canary-secret"


@pytest.mark.requires_bwrap
async def test_boxed_root_ls_no_user_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    """(d) ls / inside the box contains no app or var; home/root presence is host-conditional.

    bwrap auto-creates parent directories of any ``--bind`` target.  The scratch
    workspace (the only ``writable_paths`` entry) lives under the current user's
    HOME: inside the Docker container that is ``/root``, so bwrap creates ``/root``
    at ``ls /``.  On a host-native run the workspace lives under ``/home``, so
    bwrap creates ``/home`` instead.  Both are expected — the bind merely forces
    the parent directory to be visible, not the content of other subdirectories.

    The meaningful isolation property — that the CONTENT of the home hierarchy
    (canary files, credentials) is not visible inside the box — is verified
    separately by test_boxed_canary_unreadable (test c).

    We therefore exclude ``/root`` and ``/home`` from the unconditional forbidden
    set and assert only that ``/app`` and ``/var`` are absent (no bind target
    forces either into existence under any expected deployment).
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("box-rootls") as scratch:
        profile = _boxed_profile(scratch)
        code = "import os; print('\\n'.join(os.listdir('/')))"
        stdout, stderr, rc = await run_python(code, timeout=30.0, env={}, profile=profile)
        entries = stdout.decode(errors="replace").strip().splitlines()
        # /app and /var must not be present (no bind forces them into existence).
        # /root is excluded: on a container run the scratch workspace lives under
        # /root/, so bwrap auto-creates /root as the parent of the writable --bind
        # mount.  /home is excluded for the analogous host-native reason — the
        # scratch workspace lives under /home/<user>/ and bwrap auto-creates /home.
        for forbidden in ("app", "var"):
            assert forbidden not in entries, (
                f"Forbidden dir /{forbidden} is present in boxed ls /; ls output: {entries!r}"
            )
        # Verify the expected system dirs ARE present (sanity check the mount set).
        for expected in ("usr", "bin", "lib", "proc", "dev", "tmp"):
            assert expected in entries, (
                f"Expected system dir /{expected} is absent from boxed ls /; ls output: {entries!r}"
            )


@pytest.mark.requires_bwrap
async def test_boxed_scratch_writable_and_visible_on_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(e) A file written to scratch inside the box is visible on the host fs."""
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("box-write") as scratch:
        profile = _boxed_profile(scratch)
        target = scratch / "written-in-box.txt"
        target.unlink(missing_ok=True)

        code = f"open('{target}', 'w').write('box-hello')"
        stdout, stderr, rc = await run_python(code, timeout=30.0, env={}, profile=profile)
        assert rc == 0, f"Write to scratch inside box failed; rc={rc!r} stderr={stderr!r}"
        assert target.exists(), "File written inside box must be visible on the host fs"
        assert target.read_text() == "box-hello"


@pytest.mark.requires_bwrap
async def test_boxed_loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """(f) /proc/net/dev inside the box shows loopback only (--unshare-net)."""
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("box-net") as scratch:
        profile = _boxed_profile(scratch)
        code = (
            "with open('/proc/net/dev') as f: "
            "    lines = f.readlines(); "
            "ifaces = [l.split(':')[0].strip() for l in lines[2:] if ':' in l]; "
            "print('\\n'.join(ifaces))"
        )
        stdout, stderr, rc = await run_python(code, timeout=30.0, env={}, profile=profile)
        assert rc == 0, f"Reading /proc/net/dev failed; rc={rc!r} stderr={stderr!r}"
        ifaces = [i for i in stdout.decode(errors="replace").strip().splitlines() if i]
        # Only loopback (lo) should be present — unshare-net isolates the namespace.
        non_lo = [i for i in ifaces if i != "lo"]
        assert not non_lo, f"Non-loopback interfaces present in boxed network namespace: {non_lo!r}"
        assert "lo" in ifaces, f"Expected loopback (lo) in /proc/net/dev; got: {ifaces!r}"


@pytest.mark.requires_bwrap
async def test_boxed_passthrough_does_not_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DD6: a boxed profile through passthrough backend runs unisolated without raising.

    Force passthrough via both bypass flags, then run a trivial command.
    The boxed profile's minimal_rootfs=True field must be silently ignored.
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")

    with home_workspace("box-passthrough") as scratch:
        profile = _boxed_profile(scratch)
        code = "print('passthrough-ok')"
        stdout, stderr, rc = await run_python(code, timeout=30.0, env=None, profile=profile)
        output = stdout.decode(errors="replace").strip()
        assert output == "passthrough-ok", (
            f"Boxed profile through passthrough should run unisolated; "
            f"rc={rc!r} stdout={stdout!r} stderr={stderr!r}"
        )
