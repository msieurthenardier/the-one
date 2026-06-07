"""Unit tests for BubblewrapSandbox.prepare_spawn (F3 L3).

Pure arg-compilation testing — no real subprocess executes in any test.
L1a's 5-assertion probe stake-tested that the argv shape compiled here
actually executes inside the dev container; L4's /bin/echo integration
test is the next-leg surface.
"""

from __future__ import annotations

import shutil

import pytest

from the_one.mcp.errors import SandboxError
from the_one.platform.sandbox import (
    BubblewrapSandbox,
    SandboxProfile,
    SpawnSpec,
)

_BWRAP_NOT_FOUND_MSG = (
    "MCP sandbox setup failed: bubblewrap binary not found in PATH. "
    "Install with: apt-get install bubblewrap. "
    "In test environments only, set THE_ONE_SANDBOX_DISABLED=1 "
    "with THE_ONE_TEST_MODE=1."
)


@pytest.fixture(autouse=True)
def _bwrap_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend bwrap is installed for every test except the missing-bwrap one.

    The missing-bwrap test re-monkeypatches ``shutil.which`` locally to return
    ``None``; pytest's ``MonkeyPatch`` instance is shared between fixture and
    test body, so the test-body's ``setattr`` stacks on top and wins for that
    test's duration.
    """
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )


def test_init_raises_when_bwrap_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """__init__ raises SandboxError with the §6 verbatim message when bwrap missing."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(SandboxError) as exc_info:
        BubblewrapSandbox()
    # Verbatim §6 invariant — locks the message text against future drift.
    assert str(exc_info.value) == _BWRAP_NOT_FOUND_MSG


def test_init_succeeds_when_bwrap_present() -> None:
    """__init__ constructs without raising when bwrap is on PATH."""
    sb = BubblewrapSandbox()
    assert sb.name == "bubblewrap"


def test_prepare_spawn_default_profile_argv_shape() -> None:
    """Default profile produces all the floor flags + HOME override + sentinel."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(),
        "/bin/echo",
        ["hello"],
        {"PATH": "/usr/bin"},
    )
    assert spec.command == "bwrap"
    a = spec.args
    # Floor flags (always present)
    assert "--die-with-parent" in a
    assert "--unshare-user" in a
    assert "--unshare-pid" in a
    assert "--unshare-ipc" in a
    assert "--unshare-uts" in a
    assert "--unshare-net" in a  # network OFF by default
    assert "--clearenv" in a
    # HOME forced to /tmp even though operator didn't supply HOME
    assert "--setenv" in a
    home_idx = a.index("HOME")
    assert a[home_idx + 1] == "/tmp"
    # PATH from operator env round-trips
    path_idx = a.index("PATH")
    assert a[path_idx + 1] == "/usr/bin"
    # Floor mounts
    assert "--ro-bind" in a
    assert "--proc" in a
    assert "--dev" in a
    assert "--tmpfs" in a
    # Command + args at end
    assert a[-3] == "--"
    assert a[-2] == "/bin/echo"
    assert a[-1] == "hello"
    # SpawnSpec invariants
    assert spec.env["HOME"] == "/tmp"
    assert spec.cwd is None


def test_prepare_spawn_with_writable_paths() -> None:
    """Each writable path emits --bind PATH PATH; operator order preserved."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(writable_paths=["/data", "/cache"]),
        "/bin/echo",
        [],
        {},
    )
    a = spec.args
    # Each writable path emits --bind PATH PATH
    d_idx = a.index("/data")
    assert a[d_idx - 1] == "--bind"
    assert a[d_idx + 1] == "/data"
    c_idx = a.index("/cache")
    assert a[c_idx - 1] == "--bind"
    assert a[c_idx + 1] == "/cache"
    # Operator order preserved
    assert d_idx < c_idx


def test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind() -> None:
    """A03 fix: --ro-bind / / precedes --tmpfs /tmp precedes --bind PATH PATH.

    This locks the post-A03 ordering so a future refactor can't
    silently re-introduce the shadowing bug where writable paths
    under /tmp got overlaid by the tmpfs.
    """
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(writable_paths=["/data"]),
        "/bin/echo",
        [],
        {},
    )
    a = spec.args
    ro_bind_idx = a.index("--ro-bind")
    tmpfs_idx = a.index("--tmpfs")
    data_idx = a.index("/data")
    bind_idx = data_idx - 1  # --bind precedes the path
    assert a[bind_idx] == "--bind"
    assert ro_bind_idx < tmpfs_idx < bind_idx, (
        f"Expected --ro-bind ({ro_bind_idx}) < --tmpfs ({tmpfs_idx}) "
        f"< --bind ({bind_idx}); got argv: {a}"
    )


def test_prepare_spawn_with_network_allowed() -> None:
    """network_allowed=True omits --unshare-net."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(network_allowed=True),
        "/bin/echo",
        [],
        {},
    )
    assert "--unshare-net" not in spec.args


@pytest.mark.parametrize(
    ("field", "flag"),
    [
        ("pid_unshare", "--unshare-pid"),
        ("ipc_unshare", "--unshare-ipc"),
        ("uts_unshare", "--unshare-uts"),
    ],
)
def test_prepare_spawn_namespace_flags_individually_disabled(field: str, flag: str) -> None:
    """Each *_unshare=False omits the corresponding --unshare-* flag."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(**{field: False}),
        "/bin/echo",
        [],
        {},
    )
    assert flag not in spec.args


def test_prepare_spawn_cwd_is_set() -> None:
    """cwd='/workdir' produces --chdir /workdir immediately before the -- separator."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(),
        "/bin/echo",
        [],
        {},
        cwd="/workdir",
    )
    chdir_idx = spec.args.index("--chdir")
    assert spec.args[chdir_idx + 1] == "/workdir"
    # --chdir comes before --
    sep_idx = spec.args.index("--")
    assert chdir_idx < sep_idx
    assert spec.cwd == "/workdir"


def test_prepare_spawn_cwd_is_none() -> None:
    """cwd=None omits --chdir; SpawnSpec.cwd is None."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(SandboxProfile(), "/bin/echo", [], {}, cwd=None)
    assert "--chdir" not in spec.args
    assert spec.cwd is None


def test_prepare_spawn_home_override_unconditional() -> None:
    """With the default profile (home=None), HOME is still forced to /tmp.

    Operator-supplied HOME in the env dict is silently overridden; with no
    profile.home set the backend falls back to '/tmp'.  This invariant holds
    for MCP servers (which always use the default profile).  A profile with
    ``home`` set to a real path is tested separately by
    ``test_prepare_spawn_profile_driven_home``.
    """
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(),
        "/bin/echo",
        [],
        {"HOME": "/operator/home"},
    )
    a = spec.args
    home_idx = a.index("HOME")
    assert a[home_idx + 1] == "/tmp", "HOME override must win over operator-supplied HOME"
    assert spec.env["HOME"] == "/tmp"
    # Verify only ONE --setenv HOME pair (no duplicates from the override path)
    home_count = sum(1 for i, x in enumerate(a) if x == "HOME" and i > 0 and a[i - 1] == "--setenv")
    assert home_count == 1


def test_prepare_spawn_empty_env_still_emits_home() -> None:
    """Empty operator env still emits --setenv HOME /tmp; spec.env == {'HOME': '/tmp'}."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(SandboxProfile(), "/bin/echo", [], {})
    assert "HOME" in spec.args
    assert spec.env == {"HOME": "/tmp"}


def test_prepare_spawn_setenv_sorted_for_determinism() -> None:
    """--setenv KEY pairs appear in sorted-by-key order so tests can stake on it."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(),
        "/bin/echo",
        [],
        {"PATH": "/p", "USER": "u", "TERM": "xterm"},
    )
    # Collect --setenv KEY pairs in order
    a = spec.args
    setenv_keys: list[str] = []
    for i, tok in enumerate(a):
        if tok == "--setenv" and i + 1 < len(a):
            setenv_keys.append(a[i + 1])
    # Sorted alphabetically — HOME forced first, then PATH, TERM, USER
    assert setenv_keys == sorted(setenv_keys)
    assert "HOME" in setenv_keys
    assert "PATH" in setenv_keys
    assert "TERM" in setenv_keys
    assert "USER" in setenv_keys


def test_prepare_spawn_command_and_args_at_end() -> None:
    """Compiled argv ends with --, command, *args (in that order)."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(),
        "/bin/echo",
        ["hello", "world"],
        {},
    )
    assert spec.args[-4:] == ["--", "/bin/echo", "hello", "world"]


def test_prepare_spawn_writable_paths_with_relative_path() -> None:
    """Trust-the-runtime: relative path emitted verbatim; bwrap fails at exec time."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(
        SandboxProfile(writable_paths=["data/foo"]),
        "/bin/echo",
        [],
        {},
    )
    idx = spec.args.index("data/foo")
    assert spec.args[idx - 1] == "--bind"
    assert spec.args[idx + 1] == "data/foo"


def test_prepare_spawn_returns_spawnspec_with_correct_field_types() -> None:
    """Returned SpawnSpec has the correct field types and Linux-only field defaults."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(SandboxProfile(), "/bin/echo", [], {})
    assert isinstance(spec, SpawnSpec)
    assert spec.command == "bwrap"
    assert spec.creation_flags == 0
    assert spec.attribute_list is None


def test_prepare_spawn_readonly_overlay_after_writable_bind_before_proc() -> None:
    """--ro-bind overlay entries appear after the writable --bind loop and before --proc.

    A secret path under a writable root (e.g. /home/u/.ssh under /home/u)
    must be re-mounted read-only on top: bind order is last-wins for
    overlapping mounts, so the overlay --ro-bind must come AFTER --bind.
    Also asserts it appears BEFORE --proc (i.e. in the FS mount section).
    """
    sb = BubblewrapSandbox()
    profile = SandboxProfile(
        writable_paths=["/home/u"],
        readonly_overlay_paths=["/home/u/.ssh"],
    )
    spec = sb.prepare_spawn(profile, "/bin/echo", [], {})
    a = spec.args

    # Locate --bind /home/u /home/u (writable bind)
    bind_u_idx = None
    for i, tok in enumerate(a):
        if tok == "--bind" and i + 2 < len(a) and a[i + 1] == "/home/u":
            bind_u_idx = i
            break
    assert bind_u_idx is not None, "--bind /home/u /home/u not found in argv"

    # Locate --ro-bind-try /home/u/.ssh /home/u/.ssh (overlay)
    ro_bind_ssh_idx = None
    for i, tok in enumerate(a):
        if tok == "--ro-bind-try" and i + 2 < len(a) and a[i + 1] == "/home/u/.ssh":
            ro_bind_ssh_idx = i
            break
    assert ro_bind_ssh_idx is not None, "--ro-bind-try /home/u/.ssh /home/u/.ssh not found in argv"

    proc_idx = a.index("--proc")

    assert bind_u_idx < ro_bind_ssh_idx, (
        f"--bind /home/u ({bind_u_idx}) must precede --ro-bind-try /home/u/.ssh ({ro_bind_ssh_idx})"
    )
    assert ro_bind_ssh_idx < proc_idx, (
        f"--ro-bind-try /home/u/.ssh ({ro_bind_ssh_idx}) must precede --proc ({proc_idx})"
    )
    # Also assert the overlay values are correct (--ro-bind-try PATH PATH)
    assert a[ro_bind_ssh_idx + 1] == "/home/u/.ssh"
    assert a[ro_bind_ssh_idx + 2] == "/home/u/.ssh"


def test_prepare_spawn_profile_driven_home() -> None:
    """profile.home overrides the /tmp default; spec.env['HOME'] and argv both reflect it."""
    sb = BubblewrapSandbox()
    profile = SandboxProfile(home="/home/u")
    spec = sb.prepare_spawn(profile, "/bin/echo", [], {})
    a = spec.args

    assert spec.env["HOME"] == "/home/u"
    home_idx = a.index("HOME")
    assert a[home_idx + 1] == "/home/u"
    # Only one --setenv HOME pair
    home_count = sum(1 for i, x in enumerate(a) if x == "HOME" and i > 0 and a[i - 1] == "--setenv")
    assert home_count == 1


def test_prepare_spawn_default_profile_home_still_tmp() -> None:
    """Default profile (home=None) still yields HOME=/tmp — no regression."""
    sb = BubblewrapSandbox()
    spec = sb.prepare_spawn(SandboxProfile(), "/bin/echo", [], {})
    assert spec.env["HOME"] == "/tmp"
    a = spec.args
    home_idx = a.index("HOME")
    assert a[home_idx + 1] == "/tmp"
