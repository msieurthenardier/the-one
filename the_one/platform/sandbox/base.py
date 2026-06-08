"""OS-agnostic sandbox-spawn contract for local MCP stdio servers (F3).

This module defines the cross-platform-ready contract surface for sandboxing
locally-spawned MCP server subprocesses: the ``ToolSandbox`` ``Protocol``,
the ``SandboxProfile`` policy dataclass, and the ``SpawnSpec`` process-creation
dataclass. Linux is the only verified backend in this mission (``BubblewrapSandbox``,
landed by L3); macOS ``sandbox-exec`` and Windows ``AppContainer`` backends
are explicit follow-on work. The contract is shaped to accept those backends
without rewrite — the Windows-only ``creation_flags`` and ``attribute_list``
fields on ``SpawnSpec`` carry the AppContainer-specific knobs through, and
the Protocol's ``prepare_spawn`` method returns a typed dataclass rather
than a tuple so future fields can land additively.

Capability matrix
-----------------

The following 4x3 matrix paper-exercises the contract against the documented
capabilities of the three target backends. Rows are the four minimum
guarantees the Protocol must support; columns are the binary names so a
future routine-maintenance reviewer can grep for ``bubblewrap``,
``sandbox-exec``, ``AppContainer`` directly. Each cell summarises one
documented capability mechanism per the cited references. Cells are split
across multiple lines per row to keep the matrix linewidth-friendly while
preserving the row/column structure visually.

Row 1: env-allowlist
  * bubblewrap   — ``--clearenv`` + per-key ``--setenv`` at process start.
  * sandbox-exec — NOT directly supported; env-clearing is the caller's
    responsibility before invocation.
  * AppContainer — ``CreateProcess`` ``lpEnvironment`` parameter at
    process-creation time.

Row 2: FS scope
  * bubblewrap   — ``--ro-bind`` / ``--bind`` / ``--tmpfs`` mounts compose
    the child rootfs.
  * sandbox-exec — SBPL ``(allow file-read*)`` / ``(allow file-write*)``
    rules with regex matching.
  * AppContainer — AppContainer SID + capability ACLs per-folder, OS-managed.

Row 3: network policy
  * bubblewrap   — ``--unshare-net`` (binary on/off; no per-host filtering).
  * sandbox-exec — SBPL ``(allow network*)`` rules with optional
    per-port/per-protocol filtering.
  * AppContainer — AppContainer capabilities (``internetClient``,
    ``privateNetworkClientServer``) granted at container creation.

Row 4: process supervision
  * bubblewrap   — ``--die-with-parent`` ties child lifetime to the
    spawning shell.
  * sandbox-exec — NOT built-in; parent-death handling is the caller's
    responsibility.
  * AppContainer — Job Objects (``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``,
    ``JobObjectExtendedLimitInformation``).

Citations
---------

- bubblewrap: ``bwrap(1)`` man page; ``@anthropic-ai/sandbox-runtime`` reference
  implementation for the wrapper-flag conventions.
- sandbox-exec: Apple Developer documentation "App Sandbox Design Guide";
  ``sandbox-exec(1)`` man page; SBPL (Sandbox Profile Language) reference.
- AppContainer: Microsoft Learn "AppContainer Isolation"; Microsoft Learn
  "Job Objects" reference.

Key implication for the contract: the four guarantees are achievable on all
three platforms with different mechanisms, so the Protocol must NOT lock to
bubblewrap's Linux-namespace shape (``--unshare-pid`` has no Windows
equivalent; AppContainer's capability-based network model has no bubblewrap
equivalent). ``prepare_spawn`` returns a ``SpawnSpec`` triple-plus dataclass
where backend-specific machinery is hidden inside the wrapped ``command`` /
``args`` / ``env``; callers (``connect_stdio``) only see the wrapped result.

Error class
-----------

``SandboxError`` canonical home is ``the_one/platform/sandbox/errors.py``; this
package re-exports it via ``the_one/platform/sandbox/__init__.py`` for convenience.
The canonical import path is
``from the_one.platform.sandbox.errors import SandboxError``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SandboxProfile:
    """Sandbox policy for a local MCP server (F3 §12).

    Strict-floor defaults: empty ``writable_paths``, ``network_allowed=False``,
    all three namespace-unshare flags True. ``from_dict`` constructs from a
    plain dict (typically ``MCPSource.config['sandbox']``) per §12 contract.

    New fields (leg 2):
      * ``readonly_overlay_paths`` — list of paths the bubblewrap backend
        remounts read-only *on top of* the writable ``--bind`` mounts, so
        secrets nested under a writable root are re-protected.  Parsed by
        ``from_dict`` with the same coercion/validation as ``writable_paths``.
      * ``home`` — HOME value the bubblewrap backend injects via ``--setenv
        HOME``.  Defaults to ``None``; the backend falls back to ``"/tmp"``
        when ``None`` (preserving the historical MCP default).  This field is
        **programmatic-only**: ``from_dict`` does NOT parse it from the dict so
        operators cannot override HOME via the kv-table (§13 contract).

    New fields (leg 1 / F04):
      * ``minimal_rootfs`` — when True, the bubblewrap backend replaces the
        blanket ``--ro-bind / /`` with a minimal RO system set (``/usr`` +
        merged-usr symlinks + narrowed ``/etc`` entries) and skips mounting the
        host user filesystem.  This is the "boxed" isolation mode: the spawned
        process cannot read ``/root``, ``/home``, or any user directory not
        explicitly listed in ``writable_paths``.  Defaults to ``False``
        (host-mode: ``--ro-bind / /``; byte-identical to pre-F04 behavior).
        **Programmatic-only**: ``from_dict`` does NOT parse this field —
        operators cannot enable boxed mode via the kv-table; the tool layer
        (legs 2–4) sets it directly on the dataclass.
    """

    writable_paths: list[str] = field(default_factory=list)
    network_allowed: bool = False
    pid_unshare: bool = True
    ipc_unshare: bool = True
    uts_unshare: bool = True
    readonly_overlay_paths: list[str] = field(default_factory=list)
    home: str | None = None
    minimal_rootfs: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SandboxProfile:
        """Construct a ``SandboxProfile`` from a plain dict.

        Per F3 §12:
          * Unknown keys ignored (debug-logged).
          * Missing keys default to dataclass defaults.
          * Type mismatch on a known field raises ``ValueError`` at
            construction time with a small-model-friendly message naming the
            offending field and the expected type.
          * ``writable_paths`` and ``readonly_overlay_paths`` entries are
            coerced to ``str`` via ``str(...)``.  Despite Python's permissive
            ``str(None)`` returning ``"None"``, ``None`` entries are explicitly
            rejected as non-meaningful path values per the §12 spec.
          * ``isinstance(value, bool)`` is used (NOT ``int``) for the four
            bool fields, so a JSON ``1`` / ``0`` is rejected — matches L1b's
            API-validator strictness.
          * ``home`` is intentionally absent from ``known``: operators cannot
            set HOME via the kv-table (§13 contract); any ``home`` key in the
            dict falls through to the unknown-key debug log, not to the field.
            Use the dataclass directly (``SandboxProfile(home=...)``
            programmatically) when a caller needs to override HOME.
        """
        known = {
            "writable_paths",
            "network_allowed",
            "pid_unshare",
            "ipc_unshare",
            "uts_unshare",
            "readonly_overlay_paths",
        }
        extra = set(data) - known
        if extra:
            _logger.debug(
                "SandboxProfile.from_dict ignoring unknown keys: %s",
                sorted(extra),
            )

        writable_paths_raw = data.get("writable_paths")
        if writable_paths_raw is None:
            writable_paths: list[str] = []
        elif isinstance(writable_paths_raw, list):
            writable_paths = []
            for entry in writable_paths_raw:
                if entry is None:
                    raise ValueError(
                        "SandboxProfile.writable_paths: None is not a valid path entry."
                    )
                writable_paths.append(str(entry))
        else:
            raise ValueError(
                "SandboxProfile.writable_paths must be a list, got "
                f"{type(writable_paths_raw).__name__}."
            )

        readonly_overlay_paths_raw = data.get("readonly_overlay_paths")
        if readonly_overlay_paths_raw is None:
            readonly_overlay_paths: list[str] = []
        elif isinstance(readonly_overlay_paths_raw, list):
            readonly_overlay_paths = []
            for entry in readonly_overlay_paths_raw:
                if entry is None:
                    raise ValueError(
                        "SandboxProfile.readonly_overlay_paths: None is not a valid path entry."
                    )
                readonly_overlay_paths.append(str(entry))
        else:
            raise ValueError(
                "SandboxProfile.readonly_overlay_paths must be a list, got "
                f"{type(readonly_overlay_paths_raw).__name__}."
            )

        network_allowed = data.get("network_allowed", False)
        if not isinstance(network_allowed, bool):
            raise ValueError(
                "SandboxProfile.network_allowed must be a bool, got "
                f"{type(network_allowed).__name__}."
            )

        pid_unshare = data.get("pid_unshare", True)
        if not isinstance(pid_unshare, bool):
            raise ValueError(
                f"SandboxProfile.pid_unshare must be a bool, got {type(pid_unshare).__name__}."
            )

        ipc_unshare = data.get("ipc_unshare", True)
        if not isinstance(ipc_unshare, bool):
            raise ValueError(
                f"SandboxProfile.ipc_unshare must be a bool, got {type(ipc_unshare).__name__}."
            )

        uts_unshare = data.get("uts_unshare", True)
        if not isinstance(uts_unshare, bool):
            raise ValueError(
                f"SandboxProfile.uts_unshare must be a bool, got {type(uts_unshare).__name__}."
            )

        return cls(
            writable_paths=writable_paths,
            network_allowed=network_allowed,
            pid_unshare=pid_unshare,
            ipc_unshare=ipc_unshare,
            uts_unshare=uts_unshare,
            readonly_overlay_paths=readonly_overlay_paths,
            # home is intentionally omitted — programmatic-only (§13 contract).
        )


@dataclass(frozen=True)
class SpawnSpec:
    """Process-creation parameters spanning Linux/macOS/Windows backends (F3 §11).

    Linux/macOS callers feed ``command`` / ``args`` / ``env`` / ``cwd``
    directly into ``mcp.client.stdio.StdioServerParameters(...)``. The
    Windows-only ``creation_flags`` and ``attribute_list`` fields exist so
    a future ``AppContainerSandbox`` backend can populate them without
    changing the Protocol; Linux/macOS backends leave them at their defaults.
    """

    command: str
    args: list[str]
    env: dict[str, str]
    cwd: str | None = None
    creation_flags: int = 0  # Windows AppContainer; ignored on Linux/macOS.
    attribute_list: dict[str, Any] | None = None  # Windows AppContainer; ignored on Linux/macOS.


@runtime_checkable
class ToolSandbox(Protocol):
    """OS-agnostic adapter contract for sandboxing tool subprocesses (F3 §11).

    Implementations satisfy the contract structurally; subclassing is not
    required (and is unidiomatic for ``runtime_checkable`` Protocols).
    Backends declare a stable ``name`` and a ``prepare_spawn`` method that
    compiles a ``SandboxProfile`` plus the operator-supplied command into a
    ``SpawnSpec`` ready for the platform's process-creation primitive.
    """

    @property
    def name(self) -> str: ...

    def prepare_spawn(
        self,
        profile: SandboxProfile,
        command: str,
        args: list[str],
        env: dict[str, str],
        cwd: str | None = None,
    ) -> SpawnSpec: ...
