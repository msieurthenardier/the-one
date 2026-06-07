"""No-op passthrough sandbox backend (forward-compat for non-Linux hosts).

``PassthroughSandbox`` satisfies the ``ToolSandbox`` Protocol without applying
any sandbox enforcement.  It is selected by ``get_sandbox_backend()`` when:
  * the test double-flag bypass is active (highest priority), OR
  * the host is not Linux, OR
  * ``bwrap`` is absent on Linux (enforcement expected but not available).

This backend is a forward-compatibility shim: macOS and Windows sandbox
backends are planned follow-on work.  ``PassthroughSandbox`` accepts and
silently drops all profile fields (writable, network, namespace, overlay,
home) per the mission constraint: "profile fields a backend cannot honour must
be silently ignored, never error."  The one-time WARNING about the unsandboxed
state lives in ``get_sandbox_backend()`` rather than here so the factory can
include the *reason* (non-Linux vs bwrap-missing vs test-bypass) and set the
correct log level — the WARNING is observably equivalent to DD3.
"""

from __future__ import annotations

from the_one.platform.sandbox.base import SandboxProfile, SpawnSpec


class PassthroughSandbox:
    """No-op sandbox backend that forwards spawn arguments unchanged.

    Structurally satisfies ``ToolSandbox`` (does NOT inherit from it;
    ``runtime_checkable`` Protocols are checked structurally).  Constructs
    without raising on any platform regardless of ``bwrap`` availability.

    ``prepare_spawn`` returns a ``SpawnSpec`` with the same command, args, env,
    and cwd as supplied — no wrapping, no env mutation.  All profile fields
    (writable_paths, network_allowed, namespace unshare flags, overlay paths,
    home) are accepted and silently dropped (mission constraint: a backend
    cannot enforce them on this host; errors would break forward-compat).
    """

    name: str = "passthrough"

    def __init__(self) -> None:
        """Construct without raising — no platform checks, no binary validation."""

    def prepare_spawn(
        self,
        profile: SandboxProfile,
        command: str,
        args: list[str],
        env: dict[str, str],
        cwd: str | None = None,
    ) -> SpawnSpec:
        """Return a SpawnSpec with command/args/env/cwd forwarded unchanged.

        All ``profile`` fields are accepted and silently dropped — enforcement
        is absent on this backend.  ``args`` and ``env`` are copied defensively
        (mirrors ``BubblewrapSandbox``'s no-mutation contract; callers must not
        assume the returned collections share identity with the inputs).
        """
        return SpawnSpec(command=command, args=list(args), env=dict(env), cwd=cwd)
