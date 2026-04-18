from __future__ import annotations

import asyncio
import json
from typing import Any

from the_one.tools.base import Tool
from the_one.config import settings


class SelfDeployTool(Tool):
    name = "self_deploy"
    description = (
        "Deploy a new version of the agent by triggering the Concourse CI pipeline. "
        "This runs: test → build → deploy (with automatic rollback on health check failure). "
        "Commits and pushes workspace changes first, then triggers the pipeline."
    )
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Deploy message for the git commit.",
            },
            "skip_tests": {
                "type": "boolean",
                "description": "Start from the build job, skipping the test job. Default false.",
            },
        },
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        message = kwargs.get("message", "self-deploy")
        skip_tests = kwargs.get("skip_tests", False)
        workspace = settings.workspace_dir
        concourse = settings.concourse_target
        pipeline = settings.concourse_pipeline
        steps: list[str] = []

        # Step 1: Check for uncommitted changes
        status = await _run(f"git -C {workspace} status --porcelain")
        if status.strip():
            return (
                f"[DEPLOY ABORTED] Uncommitted changes in workspace:\n{status}\n\n"
                "Commit changes with the git tool first, then deploy."
            )
        steps.append("Working tree clean")

        # Step 2: Trigger the pipeline
        job = "build" if skip_tests else "test"
        trigger_result = await _run(
            f"fly -t {concourse} trigger-job -j {pipeline}/{job} -w 2>&1",
            timeout=600,
        )

        if "error" in trigger_result.lower() or "not authorized" in trigger_result.lower():
            return f"[DEPLOY FAILED] Could not trigger pipeline:\n{trigger_result}"

        steps.append(f"Pipeline triggered: {pipeline}/{job}")
        steps.append(f"Build output:\n{trigger_result[-2000:]}")

        if "succeeded" in trigger_result.lower():
            return "[DEPLOY COMPLETE]\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
        elif "failed" in trigger_result.lower():
            return "[DEPLOY FAILED]\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps)) + \
                "\n\nCheck Concourse UI for details. Auto-rollback may have triggered."
        else:
            return "[DEPLOY STATUS UNKNOWN]\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))


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
