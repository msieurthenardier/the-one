from __future__ import annotations

import asyncio
from typing import Any

from the_one.tools.base import Tool


class PythonExecTool(Tool):
    name = "python_exec"
    description = "Execute Python code and return the output. Runs in a subprocess."
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute."},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 60).", "default": 60},
        },
        "required": ["code"],
    }

    async def execute(self, code: str, timeout: int = 60, **kwargs: Any) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace")
            if stderr:
                output += f"\n[stderr]\n{stderr.decode(errors='replace')}"
            return output.strip() or "(no output)"
        except asyncio.TimeoutError:
            proc.kill()
            return f"[error] Timed out after {timeout}s"
        except Exception as e:
            return f"[error] {e}"
