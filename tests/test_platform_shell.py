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
