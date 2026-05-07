"""OS-level sandbox layer for MCP server subprocesses (F3).

Public API:
    MCPSandbox: Protocol contract (runtime_checkable)
    SandboxProfile: frozen dataclass (sandbox policy per source)
    SpawnSpec: frozen dataclass (process-creation parameters)
    BubblewrapSandbox: Linux backend (L2 stub, L3 implements)
    MCPSandboxError: exception (canonical home: the_one/mcp/errors.py)

See ``base.py`` module docstring for the cross-platform capability matrix.
"""

from __future__ import annotations

from the_one.mcp.errors import MCPSandboxError
from the_one.platform.sandbox.base import MCPSandbox, SandboxProfile, SpawnSpec
from the_one.platform.sandbox.bubblewrap import BubblewrapSandbox

__all__ = [
    "BubblewrapSandbox",
    "MCPSandbox",
    "MCPSandboxError",
    "SandboxProfile",
    "SpawnSpec",
]
