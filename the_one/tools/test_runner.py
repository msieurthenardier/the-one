from __future__ import annotations

import asyncio
from typing import Any

from the_one.tools.base import Tool
from the_one.config import settings


class TestRunnerTool(Tool):
    name = "run_tests"
    description = (
        "Run pytest against the workspace source code. "
        "Performs a syntax check first, then runs the test suite. "
        "Use this before deploying to verify changes are safe."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Specific test file or directory to run (relative to workspace). Defaults to 'tests/'.",
            },
            "args": {
                "type": "string",
                "description": "Additional pytest arguments, e.g. '-x -v' for verbose stop-on-first-failure.",
            },
        },
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        workspace = settings.workspace_dir
        test_path = kwargs.get("path", "tests/")
        extra_args = kwargs.get("args", "")

        # Step 1: Syntax check the source code
        syntax_cmd = f"python3 -m py_compile {workspace}/the_one/__init__.py"
        try:
            proc = await asyncio.create_subprocess_shell(
                f"python3 -c \"import py_compile, pathlib; "
                f"errors = []; "
                f"[errors.append(str(f)) for f in pathlib.Path('{workspace}/the_one').rglob('*.py') "
                f"if not _try_compile(f, errors)]; "
                f"print('ok' if not errors else chr(10).join(errors))\" 2>&1 || "
                f"cd {workspace} && python3 -m compileall -q the_one/",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            pass  # Non-fatal, proceed to tests

        # Simpler syntax check: just try to compile the package
        syntax_proc = await asyncio.create_subprocess_shell(
            f"cd {workspace} && python3 -m compileall -q the_one/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        syn_out, syn_err = await asyncio.wait_for(syntax_proc.communicate(), timeout=30)

        if syntax_proc.returncode != 0:
            err_text = syn_err.decode(errors="replace") + syn_out.decode(errors="replace")
            return f"[SYNTAX CHECK FAILED]\n{err_text.strip()}\n\nFix syntax errors before running tests."

        # Step 2: Run pytest
        full_path = f"{workspace}/{test_path}"
        cmd = f"cd {workspace} && python3 -m pytest {full_path} {extra_args} --tb=short -q 2>&1"

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            return "[error] Tests timed out after 120s."

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()

        result = "[SYNTAX CHECK PASSED]\n\n"
        if out:
            result += out
        if err:
            result += f"\n{err}"
        result += f"\n\n[exit code: {proc.returncode}]"

        if proc.returncode == 0:
            result += "\n✓ All tests passed."
        elif proc.returncode == 5:
            result += "\n⚠ No tests found (exit code 5). Consider adding tests."
        else:
            result += "\n✗ Tests failed."

        return result
