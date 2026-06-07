"""Bubblewrap-backed Linux sandbox (F3 §8 + §11).

Implements ``ToolSandbox.prepare_spawn`` by compiling a ``SandboxProfile``
plus operator-supplied (command, args, env, cwd) into a bwrap-wrapped
``SpawnSpec``. L4's ``connect_stdio`` feeds the result into
``mcp.client.stdio.StdioServerParameters`` for the SDK's transport layer.

Trust contract:
  * ``--clearenv`` + per-key ``--setenv`` enforces the env-allowlist invariant.
  * ``--ro-bind / /`` + per-path ``--bind`` defines the FS scope.
  * ``--unshare-net`` (when ``network_allowed`` is False) defines network policy.
  * ``--die-with-parent`` defines process supervision.

§13 HOME: HOME defaults to ``/tmp`` (MCP safe default — inherited ``/root``
would be read-only-but-not-writable under ``--ro-bind / /``).  Callers with a
real workspace pass ``profile.home`` to override (e.g. built-in tools in leg 4
pass the real ``$HOME``).  Operators cannot override HOME via the kv-table —
``SandboxProfile.from_dict`` intentionally omits ``home`` from the parsed-key
set.
"""

from __future__ import annotations

import shutil

from the_one.mcp.errors import SandboxError
from the_one.platform.sandbox.base import SandboxProfile, SpawnSpec


class BubblewrapSandbox:
    """Linux sandbox backend using bubblewrap (``bwrap``).

    Structurally satisfies ``the_one.platform.sandbox.base.ToolSandbox`` (does
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
        ``profile.writable_paths`` entry,
        ``--ro-bind-try PATH PATH`` per ``profile.readonly_overlay_paths`` entry
        (re-mounts secrets under a writable root read-only; must be AFTER the
        writable ``--bind`` loop so the overlay wins; ``--ro-bind-try`` skips
        absent optional-secret paths without crashing the spawn),
        ``--proc /proc``, ``--dev /dev``,
        ``[--chdir cwd]``, ``--``, ``command``, ``*args``.

    HOME defaults to ``/tmp`` (MCP safe default); set ``profile.home`` to
    override (e.g. built-in tools pass the real ``$HOME``).  Operator-supplied
    HOME values in the ``env`` dict are always overridden by the profile value.
    Operators cannot set HOME via the kv-table (``from_dict`` omits it).

    Errors raised:
      * ``SandboxError`` at construction time if ``bwrap`` is not on PATH;
        message text matches the F3 §6 catalog verbatim.
    """

    name: str = "bubblewrap"

    def __init__(self) -> None:
        """Validate bwrap presence; raise SandboxError per §6 if missing."""
        if shutil.which("bwrap") is None:
            raise SandboxError(
                "sandbox setup failed: bubblewrap binary not found in PATH. "
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
            ``--ro-bind-try PATH PATH`` per readonly_overlay_paths entry
            (AFTER writable ``--bind`` loop so overlays win; ``--ro-bind-try``
            silently skips absent optional-secret paths),
            ``--proc /proc``, ``--dev /dev``,
            ``[--chdir cwd]``, ``--``, ``command``, ``*args``.

        HOME is set from ``profile.home`` when provided, else ``/tmp``
        (MCP safe default — inherited ``/root`` would be read-only under
        ``--ro-bind / /``).  Operator-supplied HOME in the ``env`` dict is
        always overridden by the profile value.  ``--setenv`` flags are emitted
        in sorted-by-key order for test determinism; bwrap itself doesn't care
        about flag order.

        The operator's input ``env`` dict is not mutated — ``dict(env)`` makes
        a copy before applying the HOME override.
        """
        assembled_env = dict(env)
        assembled_env["HOME"] = profile.home if profile.home is not None else "/tmp"

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
        # readonly_overlay_paths AFTER the writable --bind loop: re-mounts paths
        # under a writable root as read-only, so secrets nested there are
        # re-protected. Bind order is last-wins for overlapping mounts.
        # ``--ro-bind-try`` (not ``--ro-bind``) so a non-existent denylist
        # path (e.g. ~/.aws, ~/.kube when not configured) is silently skipped
        # rather than crashing the spawn. F14 L4 refinement; the base-mount
        # ``--ro-bind / /`` above stays ``--ro-bind`` (root always exists).
        for path in profile.readonly_overlay_paths:
            bwrap_args.extend(["--ro-bind-try", path, path])
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
