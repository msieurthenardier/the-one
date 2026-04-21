from __future__ import annotations

import asyncio
from typing import Any

from the_one.tools.base import Tool


class ShellTool(Tool):
    name = "shell"
    description = (
        "Execute a shell command and return its output. "
        "Use for system commands, scripts, git, "
        "package managers, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": ["command"],
    }

    async def execute(self, command: str, timeout: int = 120, **kwargs: Any) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace")
            if stderr:
                output += f"\n[stderr]\n{stderr.decode(errors='replace')}"
            if proc.returncode != 0:
                output += f"\n[exit code: {proc.returncode}]"
            return output.strip() or "(no output)"
        except asyncio.TimeoutError:
            proc.kill()
            return f"[error] Command timed out after {timeout}s"
        except Exception as e:
            return f"[error] {e}"
