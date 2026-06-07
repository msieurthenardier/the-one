"""CLI/web sandbox parity test: construction path does not drop the policy.

Verifies that building a built-in tool via the same call AgentFactory uses —
``BuiltinToolProvider().get_tools(tool_configs_by_name, {}, agent_name=…)`` —
produces a ShellTool that:

  (a) actually contains writes under real bwrap  [@requires_bwrap]
  (b) carries the operator-supplied FilesystemConfig, not the default ["~"]

Context:

  Both CLI (``interfaces/cli.py:38``) and web (``interfaces/web/app.py:97``)
  construct tools through the identical ``AgentFactory(store=store)`` →
  ``BuiltinToolProvider.get_tools(tool_configs_by_name, …)`` path.  Parity is
  therefore a property of that shared path, not a diff between two interface
  profiles.  Testing through ``get_tools`` is the faithful, hermetic stand-in.

  Cross-config keying:  ``ShellTool.Config`` is ``ExecutionConfig``; the shell
  tool reads its filesystem policy from the *shared cross-config*
  ``self._cross_configs[FilesystemConfig]``.  In ``get_tools``, the shared
  ``FilesystemConfig`` is resolved from the **first** tool whose ``Config IS
  FilesystemConfig`` — which is ``read_file`` (declared after ``shell`` in
  ``_TOOL_CLASSES``, but ``shell``'s Config is ``ExecutionConfig``).  Therefore
  the operator FilesystemConfig must be keyed under ``"read_file"``, NOT
  ``"shell"`` (keying under ``"shell"`` routes those fields into
  ``ExecutionConfig``, silently dropped via ``extra="ignore"``, leaving the
  shared config at the default ``["~"]`` — a vacuous pass for assertion (b)).

Flight: 03 — Uniform Policy, CLI Parity & Seam Hardening
Leg: 01 — cli-parity
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.filesystem import DEFAULT_PATH_DENYLIST, FilesystemConfig
from the_one.tools.shell import ShellTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_shell_tool_via_factory_path(workspace: Path) -> ShellTool:
    """Build a ShellTool the same way AgentFactory.create() does.

    Keys the FilesystemConfig fields under ``"read_file"`` — the first tool
    in ``_TOOL_CLASSES`` whose ``Config IS FilesystemConfig``.  This is the
    load-bearing detail: keying under ``"shell"`` would route the fields into
    ``ExecutionConfig`` (silently dropped) and leave the shared FilesystemConfig
    at the default ``["~"]``.
    """
    tool_configs_by_name: dict[str, dict] = {
        "read_file": {
            "path_allowlist": [str(workspace)],
            "path_denylist": list(DEFAULT_PATH_DENYLIST),
        },
    }
    tools = BuiltinToolProvider().get_tools(
        tool_configs_by_name,
        {},
        agent_name="default",
    )
    matches = [t for t in tools if t.name == "shell"]
    assert matches, "get_tools() must return a shell tool"
    shell_tool = matches[0]
    assert isinstance(shell_tool, ShellTool)
    return shell_tool


# ---------------------------------------------------------------------------
# (b) Real policy sourced — no bwrap required
# ---------------------------------------------------------------------------


def test_factory_path_wires_real_filesystem_config() -> None:
    """(b) The shared FilesystemConfig carries the operator-supplied allowlist.

    Proves that ``get_tools`` → ``resolve()`` threads the operator config
    through to the shell tool's cross-config, rather than silently falling
    back to the default ``["~"]``.

    Observable at construction time — no bwrap or filesystem I/O required.
    """
    home = Path.home()
    # Use a distinctive, non-home path so a default-["~"] fallback would fail.
    workspace = home / ".the-one-test-cli-parity-policy"

    shell_tool = _build_shell_tool_via_factory_path(workspace)

    fs_cfg: FilesystemConfig = shell_tool._cross_configs[FilesystemConfig]  # type: ignore[index]
    allowlist = fs_cfg.path_allowlist
    assert allowlist, "path_allowlist must be non-empty"
    assert str(workspace) in allowlist, (
        f"Operator allowlist {allowlist!r} must contain the distinctive "
        f"workspace path {workspace!r}; a default-['~'] fallback would not."
    )


# ---------------------------------------------------------------------------
# (a) Containment under real bwrap
# ---------------------------------------------------------------------------


@pytest.mark.requires_bwrap
async def test_write_outside_allowlist_contained_via_factory_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a) A write outside the allowlist is denied when the tool is built via
    the factory's construction path (``get_tools``).

    The real invariant: the shared construction path produces a genuinely
    sandboxed tool.  bwrap's ``--ro-bind / /`` default makes everything outside
    ``writable_paths`` read-only inside the sandbox; a write to an
    out-of-allowlist target does not persist on the host.

    Workspace lives under HOME (not /tmp) because bwrap mounts a fresh tmpfs at
    /tmp, making /tmp paths invisible inside the sandbox.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    home = Path.home()
    workspace = home / ".the-one-test-cli-parity-workspace"
    # Sibling dir: in-scope for the host, but NOT in the allowlist.
    sibling = home / ".the-one-test-cli-parity-sibling"

    workspace.mkdir(exist_ok=True)
    sibling.mkdir(exist_ok=True)
    try:
        outside_file = sibling / "should-not-exist.txt"
        outside_file.unlink(missing_ok=True)

        shell_tool = _build_shell_tool_via_factory_path(workspace)

        await shell_tool.execute(
            command=f"echo forbidden > {outside_file}",
            cwd=str(workspace),
        )

        # Assert host-filesystem state — the real containment proof.
        # Do NOT parse the tool's returned error string.
        assert not outside_file.exists(), (
            f"Write outside allowlist must be contained by bwrap; "
            f"file exists on host: {outside_file}"
        )
    finally:
        shutil.rmtree(sibling, ignore_errors=True)
        shutil.rmtree(workspace, ignore_errors=True)
