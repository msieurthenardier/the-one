"""Contract tests for ``the_one.platform.sandbox`` (F3 L2).

Covers:
  * ``SandboxProfile`` defaults, frozen invariant, and ``from_dict`` factory
    semantics (unknown keys ignored, missing keys defaulted, type-mismatch
    raises ``ValueError``, ``writable_paths`` coercion + ``None`` rejection,
    bool-vs-int strictness).
  * ``SpawnSpec`` frozen invariant + Windows-only field defaults.
  * ``MCPSandbox`` Protocol structural-satisfaction check (positive on
    ``BubblewrapSandbox``, two-direction negative on classes missing each
    of the two required attributes).
  * ``MCPSandboxError`` subclass relationship + canonical/convenience
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
from the_one.mcp.errors import MCPSandboxError as CanonicalMCPSandboxError
from the_one.platform.sandbox import (
    BubblewrapSandbox,
    MCPSandbox,
    MCPSandboxError,
    SandboxProfile,
    SpawnSpec,
)


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


# --- MCPSandbox Protocol ------------------------------------------------------


def test_mcpsandbox_protocol_runtime_check_bubblewrap() -> None:
    """BubblewrapSandbox structurally satisfies MCPSandbox (positive)."""
    assert isinstance(BubblewrapSandbox(), MCPSandbox)


def test_mcpsandbox_protocol_runtime_check_negative_missing_prepare_spawn() -> None:
    """A class with ``name`` but no ``prepare_spawn`` does NOT satisfy MCPSandbox."""

    class MissingPrepareSpawn:
        name: str = "missing-prepare"

    assert not isinstance(MissingPrepareSpawn(), MCPSandbox)


def test_mcpsandbox_protocol_runtime_check_negative_missing_name() -> None:
    """A class with ``prepare_spawn`` but no ``name`` does NOT satisfy MCPSandbox."""

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

    assert not isinstance(MissingName(), MCPSandbox)


# --- MCPSandboxError ----------------------------------------------------------


def test_mcpsandbox_error_subclass_of_mcpclient_error() -> None:
    """Subclass relationship + canonical-and-convenience import paths agree."""
    assert issubclass(MCPSandboxError, MCPClientError)
    assert MCPSandboxError is CanonicalMCPSandboxError, (
        "Convenience re-export must alias the canonical class, not redeclare it."
    )
