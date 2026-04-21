from __future__ import annotations

import asyncio
from typing import Any

from the_one.config import settings
from the_one.tools.base import Tool

ALLOWED_COMMANDS = {
    "status", "log", "diff", "add", "commit", "branch", "checkout",
    "revert", "tag", "show", "stash", "merge", "push",
}

DENIED_PATTERNS = {"push --force", "push -f", "reset --hard", "clean -f", "clean -fd"}


class GitTool(Tool):
    name = "git"
    description = (
        "Run git operations on the workspace repository. "
        "Supports: status, log, diff, add, commit, branch, "
        "checkout, revert, tag, show, stash, merge. "
        "Dangerous operations (force push, reset --hard) are blocked."
    )
    parameters = {
        "type": "object",
        "properties": {
            "args": {
                "type": "string",
                "description": (
                    "Git subcommand and arguments, e.g. 'status', "
                    "'commit -m \"fix bug\"', 'log --oneline -10'"
                ),
            },
        },
        "required": ["args"],
    }

    async def execute(self, **kwargs: Any) -> str:
        args: str = kwargs["args"]
        parts = args.split()

        if not parts:
            return "[error] No git subcommand provided."

        subcommand = parts[0]
        if subcommand not in ALLOWED_COMMANDS:
            allowed = ', '.join(sorted(ALLOWED_COMMANDS))
            return (
                f"[error] Git subcommand '{subcommand}' "
                f"is not allowed. Allowed: {allowed}"
            )

        for pattern in DENIED_PATTERNS:
            if pattern in args:
                return f"[error] Dangerous operation detected: '{pattern}' is blocked for safety."

        cmd = f"git -C {settings.workspace_dir} {args}"

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            return "[error] Git command timed out after 30s."

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()

        result = ""
        if out:
            result += out
        if err:
            result += f"\n[stderr] {err}" if result else f"[stderr] {err}"
        if not result:
            result = "(no output)"
        result += f"\n[exit code: {proc.returncode}]"
        return result
