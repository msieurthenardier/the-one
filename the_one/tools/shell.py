from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from the_one.platform import run_shell
from the_one.tools.base import ConstraintError, Tool
from the_one.tools.execution import (
    ExecutionConfig,
    _boxed_cwd_check,
    _build_boxed_profile,
    _build_subprocess_env,
    _build_tool_profile,
    _command_check,
    _cwd_check,
    _ephemeral_box_scratch,
    _truncate_output,
)
from the_one.tools.filesystem import FilesystemConfig


class ShellTool(Tool):
    name = "shell"
    summary = "Runs a shell command in a sandbox and returns its output."
    config_fields = (
        "timeout_seconds_default",
        "timeout_seconds_max",
        "output_cap_bytes",
        "command_denylist",
        "sandbox_network_allowed",
    )
    # M16 F08 L01 (HIGH-2): tail-preserve under the context-budget governor —
    # the [exit code: N] suffix + stderr tail (the diagnostic part) must survive.
    truncation_direction = "tail"
    description = (
        "Execute a shell command and return its output. Runs in an isolated "
        "box by default (fresh scratch workspace, no access to the user's "
        "files or the network); set host_access=true only when the command "
        "needs the user's real files or network access. Default cwd is $HOME; "
        "the cwd argument may narrow to any directory inside the path "
        "allowlist (absolute paths recommended — relative paths resolve "
        "against the agent server's CWD). Subprocess environment is a "
        "hardcoded minimal allowlist (no host secrets). Timeout is clipped "
        "to the operator-set max."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "cwd": {
                "type": "string",
                "description": (
                    "Working directory; defaults to $HOME if omitted. "
                    "Refused if outside the path allowlist."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Timeout in seconds. Uses the resolved default if "
                    "omitted; clipped to the operator-set max."
                ),
            },
            "host_access": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Default false: run in an isolated box (no access to the "
                    "user's files or network; fresh scratch workspace). Set "
                    "true only when the task concretely needs the user's real "
                    "files or network access."
                ),
            },
        },
        "required": ["command"],
    }

    Config = ExecutionConfig
    Requires = (FilesystemConfig,)

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float | None = None,
        host_access: bool = False,
        **kwargs: Any,
    ) -> str:
        exec_cfg: ExecutionConfig = self._config  # type: ignore[assignment]
        fs_cfg: FilesystemConfig = self._cross_configs[FilesystemConfig]  # type: ignore[index]
        # Compute the clipped timeout BEFORE the try/except so the timeout
        # error message reflects the value the subprocess actually saw
        # (Decision 1: agent passing 999 → clipped to 120 → message says 120s).
        if timeout is None:
            clipped_timeout: float = exec_cfg.timeout_seconds_default
        else:
            # NB: float-preserving — agent passing ``timeout=0.5`` keeps
            # ``0.5`` (the existing F2 ``test_timeout_returns_promptly``
            # asserts ``"after 0.5s"``). Only zero/negative values are
            # floored to 1. ``min(timeout, max)`` clips above. The
            # ``Field(ge=1)`` constraint on the Config field constrains
            # operator/agent Config values, NOT the per-call agent kwarg.
            clipped_timeout = min(timeout, exec_cfg.timeout_seconds_max)
            if clipped_timeout <= 0:
                clipped_timeout = 1
        # Three-clause envelope (deliberate F4 deviation from F3's
        # two-clause filesystem pattern): ConstraintError → asyncio.TimeoutError
        # → Exception. Order matters because ``asyncio.TimeoutError`` IS an
        # ``Exception`` subclass; the timeout-message wording
        # (``[error] Command timed out after Ns``) is asserted by an
        # existing test (test_timeout_returns_promptly) so the timeout
        # branch must precede the generic clause. L4 (PythonExecTool) and
        # L6 (pty session tools) follow the same shape.
        try:
            _command_check(command, exec_cfg)
            if host_access:
                canonical_cwd = _cwd_check(cwd or str(Path.home()), fs_cfg)
                profile = _build_tool_profile(fs_cfg, exec_cfg)
                env = _build_subprocess_env()
                stdout, stderr, returncode = await run_shell(
                    command,
                    timeout=clipped_timeout,
                    env=env,
                    cwd=canonical_cwd,
                    profile=profile,
                )
            else:
                with _ephemeral_box_scratch() as scratch:
                    canonical_cwd = _boxed_cwd_check(cwd, scratch)
                    profile = _build_boxed_profile(scratch)
                    env = _build_subprocess_env()
                    env["HOME"] = str(scratch)
                    stdout, stderr, returncode = await run_shell(
                        command,
                        timeout=clipped_timeout,
                        env=env,
                        cwd=canonical_cwd,
                        profile=profile,
                    )
            text, _ = _truncate_output(stdout, stderr, returncode, exec_cfg)
            return text
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except asyncio.TimeoutError:
            return f"[error] Command timed out after {clipped_timeout}s"
        except Exception as e:
            return f"[error] {e}"
