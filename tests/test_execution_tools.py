"""Direct unit tests for execution tools.

L5 invariant (preserved): routing through `the_one.platform.run_shell` /
`the_one.platform.run_python` preserves the previous return-string formatting
(`[stderr]`, `[exit code: N]`, `[error] ...`, `(no output)`) byte-for-byte at
the call sites in `the_one/tools/shell.py` and `the_one/tools/python_exec.py`.

F4 L3 (this file): ``ShellTool`` migrated to the F4 constraint surface —
``Config = ExecutionConfig``, ``Requires = (FilesystemConfig,)``, plus a
seven-test surface (denylist, cwd default/refusal, timeout clipping, output
cap, env allowlist, two-clause envelope, relative-cwd refusal).

F4 L4: ``PythonExecTool`` migrated to the same constraint surface — declares
``Config = PythonExecConfig`` (a 90s-default subclass of ``ExecutionConfig``)
and ``Requires = (FilesystemConfig,)``. Same seven-test surface adapted for
the ``code`` argument.

Note the deliberate divergence between the two tools (still preserved):
  - ShellTool error string:        "[error] Command timed out after Ns"
  - PythonExecTool error string:   "[error] Timed out after Ns"
F4 L4 closes the previous ``[exit code: N]`` divergence — both tools now
append ``[exit code: N]`` for non-zero returncodes (alignment via
``_truncate_output`` as the single source of truth).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from the_one.tools.execution import ExecutionConfig, PythonExecConfig, _build_tool_profile
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.python_exec import PythonExecTool
from the_one.tools.shell import ShellTool


@pytest.fixture(autouse=True)
def _force_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin every test in this file to the passthrough sandbox backend.

    F14 L4: the tools now route through ``get_sandbox_backend()``.  Without
    this fixture, tests running inside the container (which has bwrap) would
    silently run under bubblewrap and produce different output (e.g. the env
    allowlist test would see bubblewrap-filtered env; timeout handling would
    go through bwrap's process tree).  These unit tests assert today's
    unwrapped behaviour byte-for-byte — passthrough is the right backend for
    that contract.  Real bwrap behaviour is asserted in
    ``tests/test_builtin_tool_sandbox.py`` via ``@requires_bwrap`` tests.

    Mirrors ``test_mcp_stdio_sandbox.py``'s bypass usage (both THE_ONE_SANDBOX_DISABLED
    and THE_ONE_TEST_MODE must be set; the factory checks both).
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    # THE_ONE_TEST_MODE is already set by conftest.py; re-set here for clarity
    # and to ensure the double-flag requirement is always satisfied locally.
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")


def _make_shell(
    exec_cfg: ExecutionConfig | None = None,
    fs_cfg: FilesystemConfig | None = None,
) -> ShellTool:
    """Construction helper for the F4 ShellTool surface.

    Default ``ExecutionConfig()`` and ``FilesystemConfig()`` mirror what
    ``BuiltinToolProvider`` resolves on the introspection path (no operator
    or agent overrides applied).
    """
    return ShellTool(
        exec_cfg or ExecutionConfig(),
        cross_configs={FilesystemConfig: fs_cfg or FilesystemConfig()},
    )


class TestShellTool:
    async def test_happy_path(self) -> None:
        result = await _make_shell().execute(command="echo hi")
        assert result == "hi"

    async def test_stderr_appended(self) -> None:
        result = await _make_shell().execute(command="echo err >&2")
        assert "[stderr]" in result and "err" in result

    async def test_nonzero_exit_code_appended(self) -> None:
        result = await _make_shell().execute(command="exit 7")
        assert "[exit code: 7]" in result

    async def test_empty_output(self) -> None:
        result = await _make_shell().execute(command="true")
        assert result == "(no output)"

    async def test_timeout_returns_promptly(self) -> None:
        # Budget: 3s absorbs tool->platform asyncio overhead and slow-CI
        # scheduler latency. Broken kill+reap blocks for the full 5s sleep,
        # well over this sentinel (regression net, not a tightness target).
        # ``timeout=0.5`` exercises the float-preserving clip — the tool
        # MUST NOT floor 0.5 to 1 (the existing F2 contract this test pins).
        t0 = time.monotonic()
        result = await _make_shell().execute(command="sleep 5", timeout=0.5)
        elapsed = time.monotonic() - t0
        assert result == "[error] Command timed out after 0.5s"
        assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"

    # ------------------------------------------------------------------
    # F4 L3 constraint surface (seven new tests)
    # ------------------------------------------------------------------

    async def test_class_attrs_pin_constraint_surface(self) -> None:
        """Pin ``Config`` and ``Requires`` so a future tool refactor cannot
        silently drop the F4 wiring."""
        assert ShellTool.Config is ExecutionConfig
        assert ShellTool.Requires == (FilesystemConfig,)

    async def test_denylist_command_refused(self) -> None:
        """A denylisted token in the command surfaces as
        ``[error] [constraint] command contains denylisted token '...'``
        BEFORE any subprocess is spawned."""
        result = await _make_shell().execute(command="sudo whoami")
        assert result == "[error] [constraint] command contains denylisted token 'sudo '"

    async def test_cwd_outside_allowlist_refused(self) -> None:
        """``cwd='/etc'`` hits the default denylist; refused with the
        constraint prefix BEFORE any subprocess is spawned."""
        result = await _make_shell().execute(command="ls", cwd="/etc")
        assert result.startswith("[error] [constraint]")
        assert "/etc" in result

    async def test_cwd_default_is_home(self) -> None:
        """When ``cwd`` is omitted, the tool uses ``Path.home()`` — the
        default ``FilesystemConfig.path_allowlist=["~"]`` accepts it."""
        result = await _make_shell().execute(command="pwd")
        assert result == str(Path.home().resolve())

    async def test_relative_cwd_refused_when_outside_allowlist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``cwd='.'`` resolves against the process CWD; the test must
        guarantee that CWD is OUTSIDE the configured ``path_allowlist``.

        Previously this test relied on the implicit assumption that the
        process CWD was the FastAPI dev-container path (``/app``), which
        the default ``path_allowlist=["~"]`` rejects. On host runs from
        the project root (under ``~``), the default allowlist accepts the
        CWD and the assertion flips. Reparametrized to be CWD-independent
        by construction:

        - ``monkeypatch.chdir(tmp_path)`` pins the process CWD to a known
          tmpdir (under ``/tmp``).
        - ``FilesystemConfig(path_allowlist=["/nonexistent"])`` excludes
          ``tmp_path`` explicitly so the resolved cwd is guaranteed to
          fall outside the allowlist.
        """
        monkeypatch.chdir(tmp_path)
        fs_cfg = FilesystemConfig(path_allowlist=["/nonexistent"])
        result = await _make_shell(fs_cfg=fs_cfg).execute(command="ls", cwd=".")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_timeout_clipped_to_max(self) -> None:
        """Agent passes ``timeout=10`` against an operator
        ``timeout_seconds_max=2`` → silent clip to 2 (Decision 1's
        default-and-clip framing). The error message reflects the CLIPPED
        value, not the agent's raw value."""
        exec_cfg = ExecutionConfig(timeout_seconds_default=2, timeout_seconds_max=2)
        result = await _make_shell(exec_cfg=exec_cfg).execute(command="sleep 5", timeout=10)
        assert result == "[error] Command timed out after 2s"

    async def test_output_truncated_at_cap(self) -> None:
        """A burst of output exceeding ``output_cap_bytes`` produces the
        ``[... truncated`` marker line per F4 Decision 2."""
        exec_cfg = ExecutionConfig(output_cap_bytes=1024)
        result = await _make_shell(exec_cfg=exec_cfg).execute(
            command='for i in $(seq 1 200); do echo "line $i"; done'
        )
        assert "[... truncated" in result

    async def test_env_allowlist_invariant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """End-to-end: spawn ``env`` and assert the subprocess sees ONLY
        the eight-key allowlist. Hermetic — sets a leak key first and
        asserts it is absent in the child env."""
        monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret")
        result = await _make_shell().execute(command="env")
        keys = {
            line.split("=", 1)[0]
            for line in result.splitlines()
            if "=" in line and not line.startswith("[")
        }
        # ``_ENV_ALLOWLIST`` is what the helper passes in; the SHELL itself
        # synthesizes ``PWD`` (mirrors the ``cwd`` we set on the subprocess)
        # and ``SHLVL`` (shell nesting depth). Both are benign — neither
        # leaks host config — but they are not in the helper's allowlist.
        expected = {
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "LANG",
            "LC_ALL",
            "TERM",
            "TZ",
        }
        shell_added = {"PWD", "SHLVL", "_"}
        # Guard against an empty-env false-pass: ``set().issubset(expected)``
        # is vacuously True. Real subprocess always inherits at least PATH.
        assert len(keys) > 0, f"no env keys parsed from output: {result!r}"
        assert "THE_ONE_TEST_LEAK" not in keys, f"leak: {keys}"
        assert keys.issubset(expected | shell_added), f"extras: {keys - expected - shell_added}"

    async def test_constraint_error_two_clause_envelope(self) -> None:
        """Pin the ``[error] [constraint] ...`` prefix for ConstraintError
        paths — distinct from the bare ``[error] ...`` prefix used by the
        generic Exception clause. Small-model agents key on the prefix to
        distinguish policy refusals from runtime failures."""
        # Denylist trip is the simplest ConstraintError path; the assertion
        # is on the prefix shape, not the message body.
        result = await _make_shell().execute(command="sudo whoami")
        assert result.startswith("[error] [constraint] ")
        # Double-check the bare prefix is NOT what we got — guards against
        # a regression where the constraint clause silently drops to the
        # generic clause.
        assert not result.startswith("[error] command")


def _make_python(
    exec_cfg: PythonExecConfig | None = None,
    fs_cfg: FilesystemConfig | None = None,
) -> PythonExecTool:
    """Construction helper for the F4 PythonExecTool surface.

    Default ``PythonExecConfig()`` and ``FilesystemConfig()`` mirror what
    ``BuiltinToolProvider`` resolves on the introspection path (no operator
    or agent overrides applied).
    """
    return PythonExecTool(
        exec_cfg or PythonExecConfig(),
        cross_configs={FilesystemConfig: fs_cfg or FilesystemConfig()},
    )


class TestPythonExecTool:
    async def test_happy_path(self) -> None:
        result = await _make_python().execute(code="print(2+2)")
        assert result == "4"

    async def test_stderr_appended(self) -> None:
        result = await _make_python().execute(code="import sys; print('err', file=sys.stderr)")
        assert "[stderr]" in result and "err" in result

    async def test_nonzero_exit_appends_exit_code_suffix(self) -> None:
        # F4 L4 alignment: both Python and Shell now append [exit code: N]
        # for diagnostic clarity (was a deliberate divergence pre-F4; the
        # _truncate_output helper is now the single source of truth for
        # this formatting).
        result = await _make_python().execute(code="import sys; sys.exit(3)")
        assert "[exit code: 3]" in result

    async def test_empty_output(self) -> None:
        result = await _make_python().execute(code="pass")
        assert result == "(no output)"

    async def test_timeout_returns_promptly(self) -> None:
        # See TestShellTool.test_timeout_returns_promptly for budget rationale.
        # PRESERVED divergence: PythonExecTool says "Timed out after Ns"
        # (not "Command timed out after Ns" like ShellTool).
        t0 = time.monotonic()
        result = await _make_python().execute(code="import time; time.sleep(5)", timeout=0.5)
        elapsed = time.monotonic() - t0
        assert result == "[error] Timed out after 0.5s"
        assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"

    # ------------------------------------------------------------------
    # F4 L4 constraint surface (mirrors L3's ShellTool surface)
    # ------------------------------------------------------------------

    async def test_class_attrs_pin_constraint_surface(self) -> None:
        """Pin ``Config`` and ``Requires`` so a future tool refactor cannot
        silently drop the F4 wiring."""
        assert PythonExecTool.Config is PythonExecConfig
        assert PythonExecTool.Requires == (FilesystemConfig,)

    async def test_denylist_command_refused(self) -> None:
        """A denylisted token in ``code`` (here ``"sudo "`` matched
        substring-wise inside an ``os.system`` call) surfaces as
        ``[error] [constraint] command contains denylisted token '...'``
        BEFORE any subprocess is spawned."""
        result = await _make_python().execute(code="import os; os.system('sudo whoami')")
        assert result == "[error] [constraint] command contains denylisted token 'sudo '"

    async def test_cwd_outside_allowlist_refused(self) -> None:
        """``cwd='/etc'`` hits the default denylist; refused with the
        constraint prefix BEFORE any subprocess is spawned."""
        result = await _make_python().execute(code="import os; print(os.getcwd())", cwd="/etc")
        assert result.startswith("[error] [constraint]")
        assert "/etc" in result

    async def test_cwd_default_is_home(self) -> None:
        """When ``cwd`` is omitted, the tool uses ``Path.home()`` — the
        default ``FilesystemConfig.path_allowlist=["~"]`` accepts it."""
        result = await _make_python().execute(code="import os; print(os.getcwd())")
        assert result == str(Path.home().resolve())

    async def test_timeout_clipped_to_max(self) -> None:
        """Agent passes ``timeout=10`` against an operator
        ``timeout_seconds_max=2`` → silent clip to 2 (Decision 1's
        default-and-clip framing). The error message reflects the CLIPPED
        value, not the agent's raw value. PRESERVED Python wording."""
        exec_cfg = PythonExecConfig(timeout_seconds_default=2, timeout_seconds_max=2)
        result = await _make_python(exec_cfg=exec_cfg).execute(
            code="import time; time.sleep(5)", timeout=10
        )
        assert result == "[error] Timed out after 2s"

    async def test_output_truncated_at_cap(self) -> None:
        """A burst of output exceeding ``output_cap_bytes`` produces the
        ``[... truncated`` marker line per F4 Decision 2."""
        exec_cfg = PythonExecConfig(output_cap_bytes=1024)
        result = await _make_python(exec_cfg=exec_cfg).execute(
            code="for i in range(200): print('line', i)"
        )
        assert "[... truncated" in result

    async def test_env_allowlist_invariant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """End-to-end: spawn a Python child that dumps ``os.environ`` and
        assert the subprocess sees ONLY the eight-key allowlist (plus a
        small set of C-runtime-injected extras: ``PWD`` from ``cwd=``,
        ``_`` injected by exec). Hermetic — sets a leak key first and
        asserts it is absent in the child env."""
        monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret")
        result = await _make_python().execute(
            code=("import os; print('\\n'.join(f'{k}={v}' for k, v in sorted(os.environ.items())))")
        )
        keys = {
            line.split("=", 1)[0]
            for line in result.splitlines()
            if "=" in line and not line.startswith("[")
        }
        # The allowlist proper.
        expected = {
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "LANG",
            "LC_ALL",
            "TERM",
            "TZ",
        }
        # Runtime-injected extras: ``PWD`` because ``create_subprocess_exec``
        # passes ``cwd=`` (C runtime sets ``PWD`` to mirror it); ``_`` because
        # exec sometimes injects the invocation path. Both benign.
        runtime_added = {"PWD", "_"}
        # Guard against an empty-env false-pass: ``set().issubset(expected)``
        # is vacuously True. Real subprocess always inherits at least PATH.
        assert len(keys) > 0, f"no env keys parsed from output: {result!r}"
        assert "THE_ONE_TEST_LEAK" not in keys, f"leak: {keys}"
        assert keys.issubset(expected | runtime_added), f"extras: {keys - expected - runtime_added}"

    async def test_constraint_error_two_clause_envelope(self) -> None:
        """Pin the ``[error] [constraint] ...`` prefix for ConstraintError
        paths — distinct from the bare ``[error] ...`` prefix used by the
        generic Exception clause. Small-model agents key on the prefix to
        distinguish policy refusals from runtime failures."""
        result = await _make_python().execute(code="import os; os.system('sudo whoami')")
        assert result.startswith("[error] [constraint] ")
        assert not result.startswith("[error] command")


# ────────────────────────────────────────────────────────────────────────────
# _build_tool_profile — default-allowlist production path (M14 F2 L2)
# ────────────────────────────────────────────────────────────────────────────


def test_build_tool_profile_default_allowlist() -> None:
    """``_build_tool_profile(FilesystemConfig(), ExecutionConfig())`` produces
    the expected host-workspace profile on the default-allowlist production
    path (DD10).

    * ``writable_paths`` — canonical default allowlist: ``[str(Path.home())]``.
    * ``readonly_overlay_paths`` — canonical default denylist
      (resolved absolute paths, NOT the ``~/.ssh`` tilde form).
    * ``network_allowed`` is ``False`` (deny-by-default, DD6).
    * ``home`` — ``str(Path.home())``.

    ``_build_tool_profile`` never calls the sandbox factory, so the
    passthrough autouse fixture in this file is irrelevant here — this is a
    pure unit test of the profile construction logic.
    """
    fs_cfg = FilesystemConfig()
    exec_cfg = ExecutionConfig()
    profile = _build_tool_profile(fs_cfg, exec_cfg)

    assert profile.writable_paths == [str(Path.home())]
    assert profile.readonly_overlay_paths == [str(p) for p in fs_cfg._canonical_denylist]
    assert profile.network_allowed is False
    assert profile.home == str(Path.home())


class TestExecutionToolInstantiation:
    def test_python_exec_zero_arg_uses_python_exec_config(self) -> None:
        """``PythonExecTool`` post-migration (F4 L4): zero-arg construction
        falls back to ``PythonExecConfig()`` (operator-default baseline)
        with ``_cross_configs={}``. Calling ``execute`` against this
        instance WOULD raise on the missing ``FilesystemConfig`` cross_config
        — the introspection path (``BuiltinToolProvider().get_tools()`` with
        no args) does NOT exercise execute, so this is acceptable.
        Mirrors ``test_shell_zero_arg_uses_execution_config``."""
        t = PythonExecTool()
        assert isinstance(t._config, PythonExecConfig)
        # PythonExecConfig is a subclass of ExecutionConfig — sanity-check
        # the inherited fields are also present.
        assert isinstance(t._config, ExecutionConfig)
        assert t._config.timeout_seconds_default == 90

    def test_shell_zero_arg_uses_execution_config(self) -> None:
        """``ShellTool`` post-migration: zero-arg construction falls back to
        ``ExecutionConfig()`` (operator-default baseline) with
        ``_cross_configs={}``. Calling ``execute`` against this instance
        WOULD raise on the missing ``FilesystemConfig`` cross_config — the
        introspection path (``BuiltinToolProvider().get_tools()`` with no
        args) does NOT exercise execute, so this is acceptable."""
        t = ShellTool()
        assert isinstance(t._config, ExecutionConfig)
        # Ensure HOME is set so Path.home() resolves; container usually has it.
        assert os.environ.get("HOME") is not None
