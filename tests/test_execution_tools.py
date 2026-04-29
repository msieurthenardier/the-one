"""Direct unit tests for execution tools after L5 migration to platform helpers.

These tests cover the regression invariant for L5: routing through
`the_one.platform.run_shell` / `the_one.platform.run_python` preserves the
previous return-string formatting (`[stderr]`, `[exit code: N]`,
`[error] ...`, `(no output)`) byte-for-byte at the call sites in
`the_one/tools/shell.py` and `the_one/tools/python_exec.py`.

Note the deliberate divergence between the two tools:
  - ShellTool error string:        "[error] Command timed out after Ns"
  - PythonExecTool error string:   "[error] Timed out after Ns"
  - ShellTool appends [exit code: N] for non-zero rc; PythonExecTool does NOT.
These divergences existed pre-migration and must be preserved.
"""

from __future__ import annotations

import time

from the_one.tools.python_exec import PythonExecTool
from the_one.tools.resolver import _EmptyConfig
from the_one.tools.shell import ShellTool


class TestShellTool:
    async def test_happy_path(self) -> None:
        result = await ShellTool().execute(command="echo hi")
        assert result == "hi"

    async def test_stderr_appended(self) -> None:
        result = await ShellTool().execute(command="echo err >&2")
        assert "[stderr]" in result and "err" in result

    async def test_nonzero_exit_code_appended(self) -> None:
        result = await ShellTool().execute(command="exit 7")
        assert "[exit code: 7]" in result

    async def test_empty_output(self) -> None:
        result = await ShellTool().execute(command="true")
        assert result == "(no output)"

    async def test_timeout_returns_promptly(self) -> None:
        # Budget: 3s absorbs tool->platform asyncio overhead and slow-CI
        # scheduler latency. Broken kill+reap blocks for the full 5s sleep,
        # well over this sentinel (regression net, not a tightness target).
        t0 = time.monotonic()
        result = await ShellTool().execute(command="sleep 5", timeout=0.5)
        elapsed = time.monotonic() - t0
        assert result == "[error] Command timed out after 0.5s"
        assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"


class TestPythonExecTool:
    async def test_happy_path(self) -> None:
        result = await PythonExecTool().execute(code="print(2+2)")
        assert result == "4"

    async def test_stderr_appended(self) -> None:
        result = await PythonExecTool().execute(
            code="import sys; print('err', file=sys.stderr)"
        )
        assert "[stderr]" in result and "err" in result

    async def test_nonzero_exit_no_exit_code_suffix(self) -> None:
        # Deliberate divergence from ShellTool: PythonExecTool does NOT
        # append [exit code: N]. Preserve this behavior.
        result = await PythonExecTool().execute(
            code="import sys; sys.exit(3)"
        )
        assert "[exit code" not in result
        assert result == "(no output)"

    async def test_empty_output(self) -> None:
        result = await PythonExecTool().execute(code="pass")
        assert result == "(no output)"

    async def test_timeout_returns_promptly(self) -> None:
        # See TestShellTool.test_timeout_returns_promptly for budget rationale.
        t0 = time.monotonic()
        result = await PythonExecTool().execute(
            code="import time; time.sleep(5)", timeout=0.5
        )
        elapsed = time.monotonic() - t0
        assert result == "[error] Timed out after 0.5s"
        assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"


class TestExecutionToolInstantiation:
    def test_each_tool_has_empty_config(self) -> None:
        for cls in (ShellTool, PythonExecTool):
            t1 = cls()
            t2 = cls(_EmptyConfig())
            assert isinstance(t1._config, _EmptyConfig)
            assert isinstance(t2._config, _EmptyConfig)
