from __future__ import annotations

import asyncio
from typing import Any

from the_one.config import settings
from the_one.tools.base import Tool


class RollbackTool(Tool):
    name = "rollback"
    description = (
        "Roll back to the previous deployment by triggering the Concourse rollback job. "
        "This restores the previous Docker image and restarts the container."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        concourse = settings.concourse_target
        pipeline = settings.concourse_pipeline

        result = await _run(
            f"fly -t {concourse} trigger-job -j {pipeline}/rollback -w 2>&1",
            timeout=120,
        )

        if "error" in result.lower() or "not authorized" in result.lower():
            return f"[ROLLBACK FAILED] Could not trigger rollback:\n{result}"

        if "succeeded" in result.lower():
            return f"[ROLLED BACK] Rollback completed successfully.\n{result[-500:]}"
        elif "failed" in result.lower():
            return f"[ROLLBACK FAILED]\n{result[-1000:]}"
        else:
            return f"[ROLLBACK STATUS UNKNOWN]\n{result[-1000:]}"


async def _run(cmd: str, timeout: int = 60) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        return f"{out}\n{err}".strip() if err else out
    except asyncio.TimeoutError:
        return "[timed out]"
