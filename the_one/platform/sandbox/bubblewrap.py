"""Bubblewrap-backed Linux sandbox (F3 §8 + §11).

Implements ``ToolSandbox.prepare_spawn`` by compiling a ``SandboxProfile``
plus operator-supplied (command, args, env, cwd) into a bwrap-wrapped
``SpawnSpec``. L4's ``connect_stdio`` feeds the result into
``mcp.client.stdio.StdioServerParameters`` for the SDK's transport layer.

Trust contract:
  * ``--clearenv`` + per-key ``--setenv`` enforces the env-allowlist invariant.
  * Base FS scope (conditional on ``profile.minimal_rootfs``):
    - ``False`` (host mode, default): ``--ro-bind / /`` binds the full host
      rootfs read-only.  Byte-identical to the pre-F04 behavior.
    - ``True`` (boxed mode): replaces ``--ro-bind / /`` with a minimal RO
      system set — ``--ro-bind /usr /usr``, merged-usr symlinks for
      ``/bin``/``/sbin``/``/lib``/``/lib64``, ``--ro-bind-try`` for
      ``/lib32``/``/libx32``, and a narrowed ``/etc`` set via
      ``--ro-bind-try``.  The host user filesystem (``/root``, ``/home``,
      ``/app``, ``/var``, etc.) is NOT bound; only paths explicitly listed
      in ``writable_paths`` are writable.
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
        (sorted by key for test determinism),
        **base FS scope** (conditional on ``profile.minimal_rootfs``):
          - ``False`` (host mode): ``--ro-bind / /`` — full host rootfs RO.
          - ``True`` (boxed mode): ``--ro-bind /usr /usr``,
            ``--symlink usr/bin /bin``, ``--symlink usr/sbin /sbin``,
            ``--symlink usr/lib /lib``, ``--symlink usr/lib64 /lib64``,
            ``--ro-bind-try /lib32 /lib32``, ``--ro-bind-try /libx32 /libx32``,
            ``--ro-bind-try /etc/ssl /etc/ssl``, ...(narrowed /etc set).
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
            **base FS scope** (conditional on ``profile.minimal_rootfs``):
              - ``False`` (host mode, default): ``--ro-bind / /``.
              - ``True`` (boxed mode): minimal RO system set — ``--ro-bind
                /usr /usr``, merged-usr ``--symlink`` entries for
                ``/bin``/``/sbin``/``/lib``/``/lib64``, ``--ro-bind-try``
                for ``/lib32``/``/libx32``, and narrowed ``/etc`` entries via
                ``--ro-bind-try``.
            ``--tmpfs /tmp``,
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
        if profile.minimal_rootfs:
            # Boxed mode: bind only the minimal RO system runtime — no host
            # user filesystem.  The deployment base is merged-usr (Debian
            # bookworm / python:3.11-slim), so /bin, /sbin, /lib, /lib64 are
            # already symlinks to the usr/* counterparts on the host.
            # ``--symlink SRC DEST`` recreates those symlinks inside the box.
            # If a non-merged-usr host had a real /bin, --symlink would shadow
            # it — acceptable; the deployment target is merged-usr only.
            bwrap_args.extend(["--ro-bind", "/usr", "/usr"])
            for src, dest in (
                ("usr/bin", "/bin"),
                ("usr/sbin", "/sbin"),
                ("usr/lib", "/lib"),
                ("usr/lib64", "/lib64"),
            ):
                bwrap_args.extend(["--symlink", src, dest])
            # 32-bit compat dirs may be absent; --ro-bind-try skips silently.
            for opt in ("/lib32", "/libx32"):
                bwrap_args.extend(["--ro-bind-try", opt, opt])
            # Narrowed /etc: only the entries required for runtime and name
            # resolution.  --ro-bind-try skips absent entries (e.g. resolv.conf
            # when network is off, ld.so.conf.d when not present).
            for etc in (
                "/etc/ssl",
                "/etc/passwd",
                "/etc/group",
                "/etc/nsswitch.conf",
                "/etc/resolv.conf",
                "/etc/alternatives",
                "/etc/ld.so.cache",
                "/etc/ld.so.conf",
                "/etc/ld.so.conf.d",
            ):
                bwrap_args.extend(["--ro-bind-try", etc, etc])
        else:
            # Host mode (default): full host rootfs RO.  Byte-identical to
            # pre-F04 behavior — must not change this branch (contract test).
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
