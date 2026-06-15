"""Direct tests for ``the_one.platform.shell``."""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from the_one.platform.shell import run_shell, select_shell

# OS-specific command substitutes for platform-divergent operations.
_SLEEP_5 = "timeout /t 5 /nobreak >nul" if os.name == "nt" else "sleep 5"

# ---------------------------------------------------------------------------
# select_shell
# ---------------------------------------------------------------------------


class TestSelectShell:
    def test_returns_2_tuple_of_str_and_list(self) -> None:
        result = select_shell()
        assert isinstance(result, tuple)
        assert len(result) == 2
        shell, args = result
        assert isinstance(shell, str)
        assert isinstance(args, list)
        assert all(isinstance(a, str) for a in args)

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only behavior")
    def test_posix_honors_shell_env(self, monkeypatch) -> None:
        monkeypatch.setenv("SHELL", "/bin/bash")
        assert select_shell() == ("/bin/bash", ["-c"])

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only behavior")
    def test_posix_unset_shell_falls_back(self, monkeypatch) -> None:
        monkeypatch.delenv("SHELL", raising=False)
        assert select_shell() == ("/bin/sh", ["-c"])

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only behavior")
    def test_posix_empty_shell_falls_back(self, monkeypatch) -> None:
        # The ``or "/bin/sh"`` clause should treat empty string the same as
        # unset.
        monkeypatch.setenv("SHELL", "")
        assert select_shell() == ("/bin/sh", ["-c"])

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only frozen posture")
    def test_posix_frozen_resolves_bare_shell_to_absolute(self, monkeypatch) -> None:
        """M15 F5 L1 (DD3): when frozen, a bare-name $SHELL must resolve to an
        absolute path so the post-fork execvp doesn't hit a stripped PATH."""
        from the_one.platform import env as env_mod
        from the_one.platform import shell as shell_mod

        monkeypatch.setattr(env_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(env_mod.sys, "_MEIPASS", "/bundle", raising=False)
        monkeypatch.setenv("SHELL", "bash")  # bare name
        monkeypatch.setattr(
            shell_mod.shutil,
            "which",
            lambda cmd, path=None: "/usr/bin/bash" if cmd == "bash" else None,
        )
        shell, args = select_shell()
        assert shell == "/usr/bin/bash"
        assert os.path.isabs(shell)
        assert args == ["-c"]

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only frozen posture")
    def test_posix_frozen_unresolvable_falls_back_to_bin_sh(self, monkeypatch) -> None:
        from the_one.platform import env as env_mod
        from the_one.platform import shell as shell_mod

        monkeypatch.setattr(env_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(env_mod.sys, "_MEIPASS", "/bundle", raising=False)
        monkeypatch.setenv("SHELL", "nonexistent-shell")
        monkeypatch.setattr(shell_mod.shutil, "which", lambda cmd, path=None: None)
        shell, _ = select_shell()
        assert shell == "/bin/sh"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only frozen posture")
    def test_posix_non_frozen_leaves_bare_shell(self, monkeypatch) -> None:
        from the_one.platform import env as env_mod

        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        monkeypatch.setenv("SHELL", "/bin/bash")
        assert select_shell() == ("/bin/bash", ["-c"])


# ---------------------------------------------------------------------------
# run_shell
#
# These tests are ``async def`` so the project's ``asyncio_mode = "auto"``
# pytest-asyncio config runs each in a fresh event loop. We deliberately do
# NOT use ``asyncio.run`` here because it closes the main thread's event loop
# on exit, which breaks downstream tests that call
# ``asyncio.get_event_loop().run_until_complete(...)`` (e.g.
# ``test_provider_repository.py``).
# ---------------------------------------------------------------------------


class TestRunShell:
    async def test_happy_path(self) -> None:
        stdout, stderr, returncode = await run_shell("echo hi", timeout=5)
        # Tolerate \n vs \r\n line endings.
        assert stdout.strip() == b"hi"
        assert stderr == b""
        assert returncode == 0

    async def test_nonzero_exit_propagates(self) -> None:
        _, _, returncode = await run_shell("exit 7", timeout=5)
        assert returncode == 7

    @pytest.mark.skipif(
        os.name != "posix",
        reason=(
            "POSIX-only: asserts PROMPT timeout kill+reap. On Windows the "
            "run_shell timeout-kill does not promptly reap the spawned child "
            "tree (killing cmd.exe leaves the child running — no process-group/"
            "tree kill); and `timeout.exe` errors under redirected stdin so it "
            "wouldn't even sleep. Known run_shell Windows gap (mission Known "
            "Issues, Flight-5 follow-up), parallel to the PTY Job Object. Twin "
            "of test_execution_tools::test_timeout_returns_promptly."
        ),
    )
    async def test_timeout_raises_and_is_prompt(self) -> None:
        start = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            await run_shell(_SLEEP_5, timeout=0.1)
        elapsed = time.monotonic() - start
        # The kill+reap path must not block — must return well under 1s for a
        # 0.1s timeout against a 5s sleep.
        assert elapsed < 1.0, f"run_shell timeout took {elapsed:.3f}s; kill+reap likely broken"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX shell syntax ($FOO variable expansion)")
    async def test_env_override(self) -> None:
        stdout, _, returncode = await run_shell("echo $FOO", timeout=5, env={"FOO": "bar"})
        assert returncode == 0
        assert stdout.strip() == b"bar"
