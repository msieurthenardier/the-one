"""Direct tests for ``the_one.platform.interpreter``.

The async tests below use ``async def`` rather than ``asyncio.run`` so the
project's ``asyncio_mode = "auto"`` pytest-asyncio config runs each in a
fresh event loop. ``asyncio.run`` closes the main thread's event loop on
exit, which breaks downstream tests that rely on
``asyncio.get_event_loop().run_until_complete(...)``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from the_one.platform.interpreter import resolve_python, run_python


class TestResolvePython:
    def test_returns_non_empty_string(self) -> None:
        result = resolve_python()
        assert isinstance(result, str)
        assert result != ""


class TestRunPython:
    async def test_happy_path(self) -> None:
        stdout, stderr, returncode = await run_python("print(2+2)", timeout=5)
        assert stdout.strip() == b"4"
        assert stderr == b""
        assert returncode == 0

    async def test_nonzero_exit_propagates(self) -> None:
        _, _, returncode = await run_python("import sys; sys.exit(3)", timeout=5)
        assert returncode == 3

    async def test_timeout_raises_and_is_prompt(self) -> None:
        start = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            await run_python("import time; time.sleep(5)", timeout=0.1)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"run_python timeout took {elapsed:.3f}s; kill+reap likely broken"
