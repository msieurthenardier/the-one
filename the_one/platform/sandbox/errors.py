"""Sandbox-domain error hierarchy (F3).

Canonical home for ``SandboxError``. Imported one-way from
``the_one.mcp.errors`` for the base class only; no back-edge export.
"""

from the_one.mcp.errors import MCPClientError


class SandboxError(MCPClientError):
    """Local sandbox setup failed before the sandbox successfully wraps-and-execs
    the target command: bwrap binary missing, ``writable_paths`` entry
    nonexistent, ``EPERM`` on ``unshare``, container lacks the §10 privilege
    grants, or other pre-spawn failure (F3 §6).
    """
