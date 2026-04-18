from __future__ import annotations

import asyncio
from typing import Any

from the_one.tools.base import Tool
from the_one.config import settings


class RestartTool(Tool):
    name = "restart"
    description = (
        "Restart the agent container by triggering the Concourse restart job. "
        "No rebuild — just restarts the container with the same image."
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
            f"fly -t {concourse} trigger-job -j {pipeline}/restart -w 2>&1",
            timeout=60,
        )

        if "error" in result.lower() or "not authorized" in result.lower():
            return f"[RESTART FAILED] Could not trigger restart:\n{result}"

        if "succeeded" in result.lower():
            return "[RESTARTED] Container restart completed."
        else:
            return f"[RESTART STATUS UNKNOWN]\n{result[-500:]}"


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
