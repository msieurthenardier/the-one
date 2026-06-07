from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from the_one.platform import run_python
from the_one.tools.base import ConstraintError, Tool
from the_one.tools.execution import (
    PythonExecConfig,
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


class PythonExecTool(Tool):
    name = "python_exec"
    description = (
        "Execute Python code in a one-shot subprocess. Prefer this over `shell` "
        "for computation, parsing, or any multi-line Python; use "
        "`shell_session_send` for interactive REPL work. Runs in an isolated "
        "box by default (fresh scratch workspace, no access to the user's files "
        "or the network) — ideal for untrusted or self-generated code and "
        "computation; set host_access=true only when the code needs the user's "
        "real files or network access. Default cwd is $HOME; subprocess "
        "environment is a hardcoded minimal allowlist (no host secrets). "
        "Timeout is clipped to the operator-set max."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute."},
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
                    "Timeout in seconds. Uses the resolved default "
                    "(90s for python_exec) if omitted; clipped to the "
                    "operator-set max."
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
        "required": ["code"],
    }

    Config = PythonExecConfig
    Requires = (FilesystemConfig,)

    async def execute(
        self,
        code: str,
        cwd: str | None = None,
        timeout: float | None = None,
        host_access: bool = False,
        **kwargs: Any,
    ) -> str:
        exec_cfg: PythonExecConfig = self._config  # type: ignore[assignment]
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
        # (``[error] Timed out after Ns`` — note: NO ``"Command "`` prefix,
        # which is a deliberate divergence from ShellTool preserved per F4
        # leg-spec) is asserted by an existing test
        # (``test_timeout_returns_promptly``) so the timeout branch must
        # precede the generic clause.
        try:
            _command_check(code, exec_cfg)
            if host_access:
                canonical_cwd = _cwd_check(cwd or str(Path.home()), fs_cfg)
                profile = _build_tool_profile(fs_cfg, exec_cfg)
                env = _build_subprocess_env()
                stdout, stderr, returncode = await run_python(
                    code,
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
                    stdout, stderr, returncode = await run_python(
                        code,
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
            return f"[error] Timed out after {clipped_timeout}s"
        except Exception as e:
            return f"[error] {e}"
