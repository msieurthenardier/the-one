"""@requires_bwrap containment tests for built-in tool sandbox seam (F14 L4).

These tests verify real bubblewrap containment via the ShellTool / PythonExecTool
seam introduced in F14 leg 4.  They complement the unit tests in
``test_execution_tools.py`` (which run under passthrough) by exercising the actual
bwrap path with OS-level enforcement.

Key constraints:
  * bwrap mounts a fresh tmpfs at /tmp so any workspace under /tmp is invisible
    inside the sandbox.  All workspaces are created under HOME (outside /tmp).
  * THE_ONE_SANDBOX_DISABLED must be UNSET so the factory selects BubblewrapSandbox.
  * THE_ONE_TEST_MODE is still set (by conftest.py's pytest_configure hook).

Flight Director resolution (DD4/DD5 contradiction):
  The overlay enforces write-protection (--ro-bind-try = read-only remount), NOT
  read-blocking.  Criterion (b) asserts the denylist path is not writable; it does
  NOT assert unreadable.  See leg-04 spec for the full resolution note.

F4 L3 additions (boxed one-shot):
  The ``host_access`` flag (default ``False``) makes every tool call boxed by
  default.  The new tests in this file verify:
    (f) boxed shell: cannot read a host canary; scratch is writable; cleanup runs.
    (g) boxed python_exec: same via the python_exec tool.
    (h) host_access=True restores the original host-workspace behavior.
    (i) no cross-call state: two boxed calls get different scratch dirs.
    (j) cleanup-on-timeout: timed-out boxed call still removes scratch.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests._sandbox_fixtures import (
    home_workspace,
    loopback_server,
    make_denylist_secret,
    sleep_pids,
)
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.python_exec import PythonExecTool
from the_one.tools.shell import ShellTool


def _make_python(
    exec_cfg: ExecutionConfig | None = None,
    fs_cfg: FilesystemConfig | None = None,
) -> PythonExecTool:
    return PythonExecTool(
        exec_cfg or ExecutionConfig(),
        cross_configs={FilesystemConfig: fs_cfg or FilesystemConfig()},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_shell(
    exec_cfg: ExecutionConfig | None = None,
    fs_cfg: FilesystemConfig | None = None,
) -> ShellTool:
    return ShellTool(
        exec_cfg or ExecutionConfig(),
        cross_configs={FilesystemConfig: fs_cfg or FilesystemConfig()},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
async def test_write_outside_allowlist_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a) A write to a path outside the FilesystemConfig allowlist is denied.

    The sandbox wraps the tool spawn with bwrap; the FS outside the allowlist
    is read-only under ``--ro-bind / /``.  A write to a path not in
    ``writable_paths`` fails inside the sandbox.

    Workspace is created under HOME (outside /tmp) because bwrap mounts a fresh
    tmpfs at /tmp, making any /tmp path invisible inside the sandbox.
    """
    # Ensure the factory selects BubblewrapSandbox (not passthrough).
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("allowlist-denied") as workspace:
        with home_workspace("allowlist-sibling") as sibling:
            outside_file = sibling / "should-not-exist.txt"
            outside_file.unlink(missing_ok=True)

            fs_cfg = FilesystemConfig(
                path_allowlist=[str(workspace)],
                path_denylist=[],
            )
            tool = _make_shell(fs_cfg=fs_cfg)
            result = await tool.execute(
                command=f"echo forbidden > {outside_file}",
                cwd=str(workspace),
                host_access=True,
            )
            # The write should not persist on the host — bwrap's rootfs is separate.
            assert not outside_file.exists(), (
                f"Write outside allowlist should be contained by bwrap; result: {result!r}"
            )


@pytest.mark.requires_bwrap
async def test_denylist_secret_write_denied_sibling_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(b) Write to a denylisted secret path is denied; sibling allowlisted write succeeds.

    The denylist is enforced via --ro-bind-try overlay (write-protection only).
    Criterion (b) asserts the denylist path is NOT writable.  It does NOT assert
    unreadable — the overlay is a read-only remount, not a visibility block.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("denylist-write") as workspace:
        secret_dir, secret_file = make_denylist_secret(workspace)

        ok_file = workspace / "ok.txt"
        ok_file.unlink(missing_ok=True)

        fs_cfg = FilesystemConfig(
            path_allowlist=[str(workspace)],
            path_denylist=[str(secret_dir)],
        )
        tool = _make_shell(fs_cfg=fs_cfg)

        # Attempt to overwrite the secret file — should fail (ro overlay).
        await tool.execute(
            command=f"echo tampered > {secret_file}",
            cwd=str(workspace),
            host_access=True,
        )
        # The secret file's content on the HOST must be unchanged.
        assert secret_file.read_text() == "original-content", (
            "Denylist overlay must protect the secret file from writes; "
            f"content is now: {secret_file.read_text()!r}"
        )

        # Writing to an allowlisted sibling MUST succeed.
        result = await tool.execute(
            command=f"echo allowed > {ok_file}",
            cwd=str(workspace),
            host_access=True,
        )
        assert ok_file.exists(), f"Write to allowlisted sibling must succeed; result: {result!r}"


@pytest.mark.requires_bwrap
async def test_network_denied_by_default_allowed_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(c) Network is isolated by default; reachable when sandbox_network_allowed=True.

    With --unshare-net the sandbox has its own isolated network namespace.  Its
    127.0.0.1 loopback is a DIFFERENT loopback from the host's, so a host server
    on 127.0.0.1 is unreachable from inside the sandbox (ECONNREFUSED — the
    sandbox's lo interface is up but has no listener on that port).

    Without --unshare-net (network_allowed=True) the sandbox shares the host net
    namespace and the host server is reachable.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with loopback_server() as server_port:
        with home_workspace("network") as workspace:
            fs_cfg = FilesystemConfig(path_allowlist=[str(workspace)], path_denylist=[])

            # Python code that attempts a TCP connect and prints success or failure.
            connect_code = f"""
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(('127.0.0.1', {server_port}))
    s.close()
    print('connected')
except Exception as e:
    print(f'failed: {{e}}')
"""

            # --- Network denied (default: sandbox_network_allowed=False) ---
            exec_cfg_deny = ExecutionConfig()  # sandbox_network_allowed=False by default
            assert exec_cfg_deny.sandbox_network_allowed is False
            tool_deny = PythonExecTool(
                exec_cfg_deny,
                cross_configs={FilesystemConfig: fs_cfg},
            )
            result_deny = await tool_deny.execute(
                code=connect_code,
                cwd=str(workspace),
                host_access=True,
            )
            assert "failed" in result_deny, (
                f"Network should be denied when sandbox_network_allowed=False; got: {result_deny!r}"
            )

            # --- Network allowed (sandbox_network_allowed=True) ---
            exec_cfg_allow = ExecutionConfig(sandbox_network_allowed=True)
            tool_allow = PythonExecTool(
                exec_cfg_allow,
                cross_configs={FilesystemConfig: fs_cfg},
            )
            result_allow = await tool_allow.execute(
                code=connect_code,
                cwd=str(workspace),
                host_access=True,
            )
            assert "connected" in result_allow, (
                "Network should be reachable when sandbox_network_allowed=True; "
                f"got: {result_allow!r}"
            )


@pytest.mark.requires_bwrap
async def test_real_home_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d) A write to $HOME/f inside the sandbox persists on the host workspace.

    On Linux, Path.home() reads the HOME env var.  _build_tool_profile calls
    str(Path.home()) at tool-call time, so patching HOME before the call is
    sufficient to redirect the profile's home field.  The sandbox then mounts
    the workspace as writable AND sets HOME to the workspace, so echo x > ~/f
    writes to workspace/f.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    # Create workspace under the real home (not /tmp).
    real_home = Path.home()
    with home_workspace("home-persist") as workspace:
        target_file = workspace / "f"
        target_file.unlink(missing_ok=True)

        # Redirect HOME to workspace so _build_tool_profile uses it.
        monkeypatch.setenv("HOME", str(workspace))

        fs_cfg = FilesystemConfig(path_allowlist=[str(workspace)], path_denylist=[])
        tool = _make_shell(fs_cfg=fs_cfg)

        result = await tool.execute(
            command="echo x > ~/f",
            cwd=str(workspace),
            host_access=True,
        )
        assert target_file.exists(), (
            f"~/f should exist on host after sandbox write; result: {result!r}"
        )
        assert target_file.read_text().strip() == "x", (
            f"~/f content mismatch: {target_file.read_text()!r}"
        )

    # Restore real home so subsequent tests see the correct Path.home().
    monkeypatch.setenv("HOME", str(real_home))


@pytest.mark.requires_bwrap
async def test_timeout_kills_promptly_no_orphan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(e) A timed-out command is killed promptly and leaves no orphan process.

    The killpg-based kill strategy (start_new_session=True + SIGKILL the group)
    must reap the bwrap tree within the deadline.  This is the gate for the
    kill-strategy decision in the leg spec.

    Orphan check: snapshot PIDs with 'sleep 30' before and after, assert no new
    survivors.  bwrap may alter the visible cmdline but the sleep grandchild
    should still show up in /proc.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    with home_workspace("timeout-orphan") as workspace:
        fs_cfg = FilesystemConfig(path_allowlist=[str(workspace)], path_denylist=[])
        tool = _make_shell(fs_cfg=fs_cfg)

        pids_before = sleep_pids()

        t0 = time.monotonic()
        result = await tool.execute(
            command="sleep 30",
            timeout=1,
            cwd=str(workspace),
            host_access=True,
        )
        elapsed = time.monotonic() - t0

        # Prompt return: must come back well within the 30s sleep.
        assert elapsed < 5.0, f"kill+reap blocked: {elapsed:.2f}s"
        assert "timed out" in result.lower(), f"Expected timeout message; got: {result!r}"

        # Give the process tree a moment to be fully reaped.
        time.sleep(0.5)

        pids_after = sleep_pids()
        new_pids = pids_after - pids_before
        assert not new_pids, f"Orphan 'sleep 30' processes remain after timeout kill: {new_pids}"


# ---------------------------------------------------------------------------
# F4 L3: Boxed one-shot tests (host_access=False default)
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
async def test_boxed_shell_canary_unreadable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(f) Boxed shell: cannot read a host canary; scratch writable; cleanup runs.

    monkeypatch THE_ONE_DATA_DIR to ``tmp_path`` so scratch dirs are created
    under the test's isolated directory (not the real ``~/.the-one``).
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))

    with home_workspace("box-shell-canary") as canary_dir:
        # Plant a canary file in a host dir (outside the box).
        canary_file = canary_dir / "canary.txt"
        canary_file.write_text("shell-canary-secret")

        tool = _make_shell()

        # (i) Cannot read the canary — it lives outside the box.
        result = await tool.execute(
            command=f"/bin/sh -c 'cat {canary_file} 2>/dev/null || echo absent'",
        )
        assert "shell-canary-secret" not in result, (
            f"Boxed shell must not read host canary; got: {result!r}"
        )
        assert "absent" in result, f"Expected 'absent'; got: {result!r}"

        # (ii) Can write within its scratch box (bwrap mounts a fresh tmpfs at /tmp
        # that IS writable inside the box; test via $HOME which maps to scratch).
        write_result = await tool.execute(
            command="/bin/sh -c 'echo box-hello > $HOME/test.txt && echo scratch-ok'",
        )
        # The scratch dir is writable — no [error] prefix.
        assert not write_result.startswith("[error]"), (
            f"Boxed shell write to scratch must succeed; got: {write_result!r}"
        )

    # (iii) Scratch dir is gone after the call returns.
    boxes_dir = tmp_path / "boxes"
    if boxes_dir.exists():
        remaining = list(boxes_dir.iterdir())
        assert not remaining, (
            f"Scratch dirs must be cleaned up after boxed call; found: {remaining!r}"
        )


@pytest.mark.requires_bwrap
async def test_boxed_python_exec_canary_unreadable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(g) Boxed python_exec: cannot read a host canary; scratch writable; cleanup runs."""
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))

    with home_workspace("box-py-canary") as canary_dir:
        canary_file = canary_dir / "canary.py"
        canary_file.write_text("python-canary-secret")

        tool = _make_python()

        # Cannot read canary.
        result = await tool.execute(
            code=(
                f"import os\n"
                f"try:\n"
                f"    print(open('{canary_file}').read())\n"
                f"except Exception:\n"
                f"    print('absent')\n"
            ),
        )
        assert "python-canary-secret" not in result, (
            f"Boxed python_exec must not read host canary; got: {result!r}"
        )
        assert "absent" in result, f"Expected 'absent'; got: {result!r}"

        # Can write within scratch.
        write_result = await tool.execute(
            code=(
                "import os\n"
                "home = os.environ.get('HOME', '/')\n"
                "path = os.path.join(home, 'box-test.txt')\n"
                "open(path, 'w').write('box-py-hello')\n"
                "print('wrote', path)\n"
            ),
        )
        assert not write_result.startswith("[error]"), (
            f"Boxed python_exec write to scratch must succeed; got: {write_result!r}"
        )

    # Scratch cleanup.
    boxes_dir = tmp_path / "boxes"
    if boxes_dir.exists():
        remaining = list(boxes_dir.iterdir())
        assert not remaining, (
            f"Scratch dirs must be cleaned up after boxed call; found: {remaining!r}"
        )


@pytest.mark.requires_bwrap
async def test_boxed_host_access_true_reads_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(h) host_access=True restores the original host-workspace behavior.

    A file planted on the host is readable when ``host_access=True`` is passed
    (the tool mounts the real home FS via ``_build_tool_profile``).
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))

    with home_workspace("host-access-canary") as canary_dir:
        canary_file = canary_dir / "host-canary.txt"
        canary_file.write_text("host-access-secret")

        fs_cfg = FilesystemConfig(
            path_allowlist=[str(canary_dir)],
            path_denylist=[],
        )
        tool = _make_shell(fs_cfg=fs_cfg)

        result = await tool.execute(
            command=f"cat {canary_file}",
            cwd=str(canary_dir),
            host_access=True,
        )
        assert "host-access-secret" in result, (
            f"host_access=True must be able to read the host canary; got: {result!r}"
        )


@pytest.mark.requires_bwrap
async def test_boxed_no_cross_call_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(i) No cross-call state: two boxed calls get different scratch dirs.

    A file written in call 1 is absent in call 2 (fresh ephemeral scratch).
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))

    tool = _make_shell()

    # Call 1: write a sentinel file to the scratch HOME.
    result1 = await tool.execute(
        command="/bin/sh -c 'echo call1 > $HOME/sentinel.txt; echo wrote'",
    )
    assert not result1.startswith("[error]"), f"Call 1 write failed: {result1!r}"

    # Call 2: check if the sentinel is present — it must NOT be (fresh scratch).
    result2 = await tool.execute(
        command="/bin/sh -c 'test -f $HOME/sentinel.txt && echo found || echo absent'",
    )
    assert "absent" in result2, f"Call 2 must not see call 1's scratch; got: {result2!r}"


@pytest.mark.requires_bwrap
async def test_boxed_cleanup_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(j) Cleanup-on-timeout: timed-out boxed call still removes scratch dir.

    The ``with _ephemeral_box_scratch()`` block is inside the tool's ``try``,
    so the CM's ``finally`` fires before the ``except asyncio.TimeoutError``
    clause formats the error — scratch is removed regardless.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))

    tool = _make_shell()

    result = await tool.execute(
        command="sleep 30",
        timeout=1,
    )
    assert "timed out" in result.lower(), f"Expected timeout message; got: {result!r}"

    # Scratch must be gone.
    boxes_dir = tmp_path / "boxes"
    if boxes_dir.exists():
        remaining = list(boxes_dir.iterdir())
        assert not remaining, (
            f"Scratch dir must be cleaned up even after timeout; found: {remaining!r}"
        )
