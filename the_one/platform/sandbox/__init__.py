"""OS-level sandbox layer for tool subprocesses (F3).

Public API:
    ToolSandbox: Protocol contract (runtime_checkable)
    SandboxProfile: frozen dataclass (sandbox policy per source)
    SpawnSpec: frozen dataclass (process-creation parameters)
    BubblewrapSandbox: Linux backend
    PassthroughSandbox: no-op backend (non-Linux / test-bypass / bwrap-missing)
    get_sandbox_backend: factory — selects BubblewrapSandbox or PassthroughSandbox
    SandboxError: exception (canonical home: the_one/platform/sandbox/errors.py)

See ``base.py`` module docstring for the cross-platform capability matrix.
"""

from __future__ import annotations

from the_one.platform.sandbox.base import SandboxProfile, SpawnSpec, ToolSandbox
from the_one.platform.sandbox.bubblewrap import BubblewrapSandbox
from the_one.platform.sandbox.errors import SandboxError
from the_one.platform.sandbox.factory import get_sandbox_backend
from the_one.platform.sandbox.passthrough import PassthroughSandbox

__all__ = [
    "BubblewrapSandbox",
    "PassthroughSandbox",
    "SandboxError",
    "SandboxProfile",
    "SpawnSpec",
    "ToolSandbox",
    "get_sandbox_backend",
]
