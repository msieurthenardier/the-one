"""Bubblewrap-backed Linux sandbox (F3 §8 + §11).

Implements ``MCPSandbox.prepare_spawn`` by compiling a ``SandboxProfile``
plus operator-supplied (command, args, env, cwd) into a bwrap-wrapped
``SpawnSpec``. L4's ``connect_stdio`` feeds the result into
``mcp.client.stdio.StdioServerParameters`` for the SDK's transport layer.

Trust contract:
  * ``--clearenv`` + per-key ``--setenv`` enforces the env-allowlist invariant.
  * ``--ro-bind / /`` + per-path ``--bind`` defines the FS scope.
  * ``--unshare-net`` (when ``network_allowed`` is False) defines network policy.
  * ``--die-with-parent`` defines process supervision.

§13 HOME override: HOME is unconditionally set to ``/tmp`` regardless of
operator-supplied env. Operators cannot override HOME via the kv-table —
sandbox policy, not operator-configurable.
"""

from __future__ import annotations

import shutil

from the_one.mcp.errors import MCPSandboxError
from the_one.platform.sandbox.base import SandboxProfile, SpawnSpec


class BubblewrapSandbox:
    """Linux sandbox backend using bubblewrap (``bwrap``).

    Structurally satisfies ``the_one.platform.sandbox.base.MCPSandbox`` (does
    NOT inherit from it; ``runtime_checkable`` Protocols are checked
    structurally). Validates ``bwrap`` presence at construction;
    ``prepare_spawn`` compiles a ``SandboxProfile`` plus operator
    command/args/env/cwd into a bwrap-wrapped ``SpawnSpec``.

    Argv structure (in order):
        ``--die-with-parent``, ``--unshare-user``, ``[--unshare-pid]``,
        ``[--unshare-ipc]``, ``[--unshare-uts]``, ``[--unshare-net]``,
        ``--clearenv``, ``--setenv KEY VALUE`` per assembled-env entry
        (sorted by key for test determinism), ``--ro-bind / /``,
        ``--tmpfs /tmp``, ``--bind PATH PATH`` per
        ``profile.writable_paths`` entry, ``--proc /proc``,
        ``--dev /dev``, ``[--chdir cwd]``, ``--``, ``command``, ``*args``.

    HOME is unconditionally overridden to ``/tmp`` (sandbox policy, not
    operator-configurable). Operator-supplied HOME values are silently
    overridden.

    Errors raised:
      * ``MCPSandboxError`` at construction time if ``bwrap`` is not on PATH;
        message text matches the F3 §6 catalog verbatim.
    """

    name: str = "bubblewrap"

    def __init__(self) -> None:
        """Validate bwrap presence; raise MCPSandboxError per §6 if missing."""
        if shutil.which("bwrap") is None:
            raise MCPSandboxError(
                "MCP sandbox setup failed: bubblewrap binary not found in PATH. "
                "Install with: apt-get install bubblewrap. "
                "In test environments only, set THE_ONE_SANDBOX_DISABLED=1 "
                "with THE_ONE_TEST_MODE=1."
            )

    def prepare_spawn(
        self,
        profile: SandboxProfile,
        command: str,
        args: list[str],
        env: dict[str, str],
        cwd: str | None = None,
    ) -> SpawnSpec:
        """Compile a bwrap-wrapped SpawnSpec.

        Argv structure (in order):
            ``--die-with-parent``, ``--unshare-user``, ``[--unshare-pid]``,
            ``[--unshare-ipc]``, ``[--unshare-uts]``, ``[--unshare-net]``,
            ``--clearenv``, ``--setenv KEY VALUE`` per assembled-env entry,
            ``--ro-bind / /``, ``--tmpfs /tmp``,
            ``--bind PATH PATH`` per writable_paths entry,
            ``--proc /proc``, ``--dev /dev``,
            ``[--chdir cwd]``, ``--``, ``command``, ``*args``.

        HOME is unconditionally overridden to ``/tmp`` (sandbox policy).
        ``--setenv`` flags are emitted in sorted-by-key order for test
        determinism; bwrap itself doesn't care about flag order.

        The operator's input ``env`` dict is not mutated — ``dict(env)`` makes
        a copy before applying the HOME override.
        """
        assembled_env = dict(env)
        assembled_env["HOME"] = "/tmp"

        bwrap_args: list[str] = ["--die-with-parent", "--unshare-user"]
        if profile.pid_unshare:
            bwrap_args.append("--unshare-pid")
        if profile.ipc_unshare:
            bwrap_args.append("--unshare-ipc")
        if profile.uts_unshare:
            bwrap_args.append("--unshare-uts")
        if not profile.network_allowed:
            bwrap_args.append("--unshare-net")
        bwrap_args.append("--clearenv")
        # Sorted iteration for test determinism; bwrap doesn't care about order.
        for key in sorted(assembled_env):
            bwrap_args.extend(["--setenv", key, assembled_env[key]])
        bwrap_args.extend(["--ro-bind", "/", "/"])
        # --tmpfs /tmp BEFORE the --bind loop so writable_paths under /tmp
        # actually persist (the tmpfs lays /tmp first; the --bind layers on
        # top). Pre-A03 ordering had --tmpfs after --bind, silently shadowing
        # operator-configured writable paths under /tmp. See F3 anomaly A03.
        bwrap_args.extend(["--tmpfs", "/tmp"])
        for path in profile.writable_paths:
            bwrap_args.extend(["--bind", path, path])
        bwrap_args.extend(["--proc", "/proc"])
        bwrap_args.extend(["--dev", "/dev"])
        if cwd is not None:
            bwrap_args.extend(["--chdir", cwd])
        bwrap_args.append("--")
        bwrap_args.append(command)
        bwrap_args.extend(args)

        return SpawnSpec(
            command="bwrap",
            args=bwrap_args,
            env=assembled_env,
            cwd=cwd,
        )
