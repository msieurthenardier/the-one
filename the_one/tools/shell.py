from __future__ import annotations

import asyncio
from typing import Any

from the_one.platform import run_shell
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
            stdout, stderr, returncode = await run_shell(command, timeout=timeout)
            output = stdout.decode(errors="replace")
            if stderr:
                output += f"\n[stderr]\n{stderr.decode(errors='replace')}"
            if returncode != 0:
                output += f"\n[exit code: {returncode}]"
            return output.strip() or "(no output)"
        except asyncio.TimeoutError:
            return f"[error] Command timed out after {timeout}s"
        except Exception as e:
            return f"[error] {e}"
