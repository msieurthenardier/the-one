"""Contract tests for ``the_one.platform.sandbox`` (F3 L2).

Covers:
  * ``SandboxProfile`` defaults, frozen invariant, and ``from_dict`` factory
    semantics (unknown keys ignored, missing keys defaulted, type-mismatch
    raises ``ValueError``, ``writable_paths`` coercion + ``None`` rejection,
    bool-vs-int strictness).
  * ``SpawnSpec`` frozen invariant + Windows-only field defaults.
  * ``ToolSandbox`` Protocol structural-satisfaction check (positive on
    ``BubblewrapSandbox``, two-direction negative on classes missing each
    of the two required attributes).
  * ``SandboxError`` subclass relationship + canonical/convenience
    import paths.

A module-level autouse fixture monkeypatches ``shutil.which("bwrap")`` so
``BubblewrapSandbox()``-instantiating tests construct successfully even in
environments without ``bwrap`` actually installed; the contract logic is
bwrap-independent and shouldn't depend on the host's installation state.

All tests are synchronous and contract-only (no real subprocess). Total
wall-clock should be well under 1 second.
"""

from __future__ import annotations

import dataclasses
import shutil

import pytest

from the_one.mcp.errors import MCPClientError
from the_one.platform.sandbox import (
    BubblewrapSandbox,
    PassthroughSandbox,
    SandboxError,
    SandboxProfile,
    SpawnSpec,
    ToolSandbox,
)
from the_one.platform.sandbox.errors import SandboxError as CanonicalSandboxError


@pytest.fixture(autouse=True)
def _bwrap_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend bwrap is installed so BubblewrapSandbox() constructs in any env."""
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )


# --- SandboxProfile -----------------------------------------------------------


def test_sandbox_profile_defaults() -> None:
    """Strict-floor defaults: empty writable_paths, network off, all unshare flags on."""
    profile = SandboxProfile()
    assert profile.writable_paths == []
    assert profile.network_allowed is False
    assert profile.pid_unshare is True
    assert profile.ipc_unshare is True
    assert profile.uts_unshare is True


def test_sandbox_profile_is_frozen() -> None:
    """Mutating a field on a frozen dataclass raises FrozenInstanceError."""
    profile = SandboxProfile()
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.network_allowed = True  # type: ignore[misc]


def test_sandbox_profile_from_dict_unknown_keys_ignored() -> None:
    """Unknown keys do not raise; known keys (when absent) get defaults."""
    profile = SandboxProfile.from_dict({"writable_paths": [], "extra_key": "ignored"})
    assert profile.writable_paths == []
    assert profile.network_allowed is False
    assert profile.pid_unshare is True
    assert profile.ipc_unshare is True
    assert profile.uts_unshare is True


def test_sandbox_profile_from_dict_missing_keys_use_defaults() -> None:
    """Empty dict yields the strict-floor profile."""
    profile = SandboxProfile.from_dict({})
    assert profile == SandboxProfile()


def test_sandbox_profile_from_dict_type_mismatch_raises() -> None:
    """Type mismatch on a known field raises ValueError naming the field + expected type."""
    with pytest.raises(ValueError, match="network_allowed.*bool"):
        SandboxProfile.from_dict({"network_allowed": "yes"})

    with pytest.raises(ValueError, match="writable_paths.*list"):
        SandboxProfile.from_dict({"writable_paths": "not-a-list"})


def test_sandbox_profile_from_dict_rejects_int_for_bool() -> None:
    """JSON ``1`` for a bool-typed field raises (locks isinstance(bool) strictness)."""
    with pytest.raises(ValueError, match="network_allowed.*bool"):
        SandboxProfile.from_dict({"network_allowed": 1})


def test_sandbox_profile_from_dict_writable_paths_coerce_str() -> None:
    """Non-string entries in writable_paths are coerced via str()."""
    profile = SandboxProfile.from_dict({"writable_paths": ["/data", 42]})
    assert profile.writable_paths == ["/data", "42"]


def test_sandbox_profile_from_dict_writable_paths_none_raises() -> None:
    """None entry in writable_paths raises ValueError (despite str(None) == 'None')."""
    with pytest.raises(ValueError, match="writable_paths"):
        SandboxProfile.from_dict({"writable_paths": [None]})


# --- SpawnSpec ----------------------------------------------------------------


def test_spawn_spec_is_frozen() -> None:
    """Mutating a SpawnSpec field raises FrozenInstanceError."""
    spec = SpawnSpec(command="/bin/echo", args=["hello"], env={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.command = "/bin/cat"  # type: ignore[misc]


def test_spawn_spec_default_windows_fields() -> None:
    """creation_flags=0, attribute_list=None, cwd=None when not specified."""
    spec = SpawnSpec(command="/bin/echo", args=["hello"], env={})
    assert spec.cwd is None
    assert spec.creation_flags == 0
    assert spec.attribute_list is None


# --- ToolSandbox Protocol ------------------------------------------------------


def test_toolsandbox_protocol_runtime_check_bubblewrap() -> None:
    """BubblewrapSandbox structurally satisfies ToolSandbox (positive)."""
    assert isinstance(BubblewrapSandbox(), ToolSandbox)


def test_toolsandbox_protocol_runtime_check_passthrough() -> None:
    """PassthroughSandbox structurally satisfies ToolSandbox (positive)."""
    assert isinstance(PassthroughSandbox(), ToolSandbox)


def test_toolsandbox_protocol_runtime_check_negative_missing_prepare_spawn() -> None:
    """A class with ``name`` but no ``prepare_spawn`` does NOT satisfy ToolSandbox."""

    class MissingPrepareSpawn:
        name: str = "missing-prepare"

    assert not isinstance(MissingPrepareSpawn(), ToolSandbox)


def test_toolsandbox_protocol_runtime_check_negative_missing_name() -> None:
    """A class with ``prepare_spawn`` but no ``name`` does NOT satisfy ToolSandbox."""

    class MissingName:
        def prepare_spawn(
            self,
            profile: SandboxProfile,
            command: str,
            args: list[str],
            env: dict[str, str],
            cwd: str | None = None,
        ) -> SpawnSpec:
            return SpawnSpec(command=command, args=args, env=env, cwd=cwd)

    assert not isinstance(MissingName(), ToolSandbox)


# --- SandboxError ----------------------------------------------------------


def test_sandbox_error_subclass_of_mcpclient_error() -> None:
    """Subclass relationship + canonical-and-convenience import paths agree."""
    assert issubclass(SandboxError, MCPClientError)
    assert SandboxError is CanonicalSandboxError, (
        "Convenience re-export must alias the canonical class, not redeclare it."
    )


# --- minimal_rootfs field + argv contract (F04 L01) -----------------------


def test_sandbox_profile_minimal_rootfs_default() -> None:
    """minimal_rootfs defaults to False (host mode)."""
    profile = SandboxProfile()
    assert profile.minimal_rootfs is False


def test_sandbox_profile_minimal_rootfs_settable_programmatically() -> None:
    """minimal_rootfs=True can be set directly on the dataclass."""
    profile = SandboxProfile(minimal_rootfs=True)
    assert profile.minimal_rootfs is True


def test_sandbox_profile_from_dict_ignores_minimal_rootfs() -> None:
    """from_dict ignores 'minimal_rootfs' (programmatic-only — like 'home').

    The key must fall through to the unknown-key debug log, not be parsed.
    The resulting profile must have minimal_rootfs at its default (False).
    """
    profile = SandboxProfile.from_dict({"minimal_rootfs": True})
    assert profile.minimal_rootfs is False, (
        "from_dict must NOT parse minimal_rootfs; it must remain at default False"
    )


def test_bubblewrap_host_mode_argv_unchanged() -> None:
    """Host mode (minimal_rootfs=False) argv is byte-identical to pre-F04.

    The else-branch must keep '--ro-bind / /' exactly; this is the regression
    guard preventing accidental breakage of the non-boxed path.
    """
    backend = BubblewrapSandbox()
    profile = SandboxProfile(writable_paths=["/tmp/w"], network_allowed=False)
    spec = backend.prepare_spawn(profile, "/bin/sh", ["-c", "echo hi"], {"HOME": "/tmp"})

    assert "--ro-bind" in spec.args
    ro_bind_idx = spec.args.index("--ro-bind")
    assert spec.args[ro_bind_idx + 1] == "/", "Host mode: --ro-bind source must be '/' (root)"
    assert spec.args[ro_bind_idx + 2] == "/", "Host mode: --ro-bind dest must be '/' (root)"
    # Must not contain any minimal-rootfs-specific flags.
    assert "--symlink" not in spec.args, "Host mode must not contain --symlink"
    # The /usr bind must not appear as an independent --ro-bind entry.
    usr_bind_indices = [
        i
        for i, v in enumerate(spec.args)
        if v == "--ro-bind" and i + 1 < len(spec.args) and spec.args[i + 1] == "/usr"
    ]
    assert not usr_bind_indices, "Host mode must not contain --ro-bind /usr /usr (boxed-mode only)"


def test_bubblewrap_boxed_mode_argv_has_minimal_set_no_full_bind() -> None:
    """Boxed mode (minimal_rootfs=True) argv has minimal set and no --ro-bind / /.

    Verifies:
      * --ro-bind /usr /usr present
      * merged-usr --symlink entries present for /bin, /sbin, /lib, /lib64
      * --ro-bind-try entries for /lib32, /libx32
      * at least some narrowed /etc entries present
      * no --ro-bind / / (full-rootfs bind absent)
    """
    backend = BubblewrapSandbox()
    profile = SandboxProfile(
        minimal_rootfs=True,
        writable_paths=["/tmp/w"],
        network_allowed=False,
    )
    spec = backend.prepare_spawn(profile, "/bin/sh", ["-c", "echo hi"], {"HOME": "/tmp"})
    args = spec.args

    # Must NOT contain full-rootfs bind.
    full_bind_indices = [
        i
        for i, v in enumerate(args)
        if v == "--ro-bind" and i + 2 < len(args) and args[i + 1] == "/" and args[i + 2] == "/"
    ]
    assert not full_bind_indices, "Boxed mode must not contain '--ro-bind / /' (full rootfs bind)"

    # Must contain --ro-bind /usr /usr.
    usr_bind_indices = [
        i
        for i, v in enumerate(args)
        if v == "--ro-bind"
        and i + 2 < len(args)
        and args[i + 1] == "/usr"
        and args[i + 2] == "/usr"
    ]
    assert usr_bind_indices, "Boxed mode must contain '--ro-bind /usr /usr'"

    # Must contain --symlink entries for merged-usr dirs.
    symlink_dests = set()
    for i, v in enumerate(args):
        if v == "--symlink" and i + 2 < len(args):
            symlink_dests.add(args[i + 2])
    for expected_dest in ("/bin", "/sbin", "/lib", "/lib64"):
        assert expected_dest in symlink_dests, (
            f"Boxed mode must contain '--symlink ... {expected_dest}'; "
            f"symlink dests found: {symlink_dests!r}"
        )

    # Must contain --ro-bind-try for optional compat dirs.
    ro_bind_try_srcs = set()
    for i, v in enumerate(args):
        if v == "--ro-bind-try" and i + 1 < len(args):
            ro_bind_try_srcs.add(args[i + 1])
    assert "/lib32" in ro_bind_try_srcs, (
        f"Boxed mode must contain '--ro-bind-try /lib32 /lib32'; "
        f"ro-bind-try srcs: {ro_bind_try_srcs!r}"
    )

    # Must contain at least one narrowed /etc entry.
    etc_entries = [s for s in ro_bind_try_srcs if s.startswith("/etc/")]
    assert etc_entries, (
        f"Boxed mode must contain narrowed /etc entries via --ro-bind-try; "
        f"ro-bind-try srcs: {ro_bind_try_srcs!r}"
    )
