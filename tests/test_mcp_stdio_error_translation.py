"""F9 L2 D3 — operator-actionable spawn-error translation tests.

Covers:
  - FileNotFoundError (command not on PATH) → MCPConnectionError with
    host-native operator-actionable message: names the missing executable,
    gives a per-runtime install hint (node/npx/uv/uvx/python/python3
    known; generic fallback for other commands), no Docker references.
  - Inner-process ModuleNotFoundError surfaced via stderr →
    MCPConnectionError with `command=uvx args=[<pkg>]` guidance.
  - Generic non-zero exit (no FileNotFoundError, no ModuleNotFoundError
    in stderr) → falls through to MCPClient's existing translation
    UNCHANGED.
  - Bwrap-discriminator gate: a bwrap-side FileNotFoundError-shaped
    failure (bwrap can't find the inner command) is NOT mistranslated
    as a host-native "missing on PATH" message — it surfaces as
    SandboxError per F3 §6 directionality contract.
"""

from __future__ import annotations

import pytest

from the_one.mcp.errors import MCPConnectionError
from the_one.mcp.transports import stdio as stdio_module
from the_one.mcp.transports.stdio import _translate_inner_spawn_error
from the_one.platform.sandbox.errors import SandboxError

# ── Unit tests on _translate_inner_spawn_error ──────────────────────────

_DOCKER_TOKENS = ("Dockerfile", "make rebuild", "docker compose exec", "in the container")


def test_translate_filenotfounderror_returns_actionable_connection_error() -> None:
    """FileNotFoundError → MCPConnectionError: names the runtime, host-native hint, no Docker."""
    exc = FileNotFoundError(2, "No such file or directory", "uvx")
    err = _translate_inner_spawn_error(exc=exc, stderr_text="", command="uvx")
    assert isinstance(err, MCPConnectionError)
    msg = str(err)
    # Must name the missing command and give the runtime-fetch shape tip.
    assert "uvx" in msg
    # Must NOT contain Docker guidance.
    for token in _DOCKER_TOKENS:
        assert token not in msg, f"Docker token {token!r} found in message: {msg!r}"
    # Must contain a host-native install hint (astral.sh/uv for uvx).
    assert "astral.sh/uv" in msg


@pytest.mark.parametrize(
    "command, filename, hint_fragment",
    [
        ("node", "node", "nodejs.org"),
        ("npx", "npx", "nodejs.org"),
        ("uv", "uv", "astral.sh/uv"),
        ("uvx", "uvx", "astral.sh/uv"),
        ("python", "python", "python.org"),
        ("python3", "python3", "python.org"),
        ("my-custom-mcp", "my-custom-mcp", "my-custom-mcp"),  # generic fallback
    ],
)
def test_translate_filenotfounderror_per_runtime(
    command: str, filename: str, hint_fragment: str
) -> None:
    """Each known runtime gets a host-native hint; unknown commands get the generic fallback."""
    exc = FileNotFoundError(2, "No such file or directory", filename)
    err = _translate_inner_spawn_error(exc=exc, stderr_text="", command=command)
    assert isinstance(err, MCPConnectionError)
    msg = str(err)
    # Missing runtime is named.
    assert filename in msg
    # Host-native hint fragment present.
    assert hint_fragment in msg, f"Expected {hint_fragment!r} in message for {command!r}: {msg!r}"
    # No Docker tokens.
    for token in _DOCKER_TOKENS:
        assert token not in msg, f"Docker token {token!r} found for {command!r}: {msg!r}"


def test_translate_filenotfounderror_falls_back_to_command_when_filename_missing() -> None:
    """FileNotFoundError without `.filename` falls back to the configured command."""
    exc = FileNotFoundError("synthetic — no filename")
    err = _translate_inner_spawn_error(
        exc=exc,
        stderr_text="",
        command="my-custom-mcp",
    )
    assert isinstance(err, MCPConnectionError)
    assert "my-custom-mcp" in str(err)


def test_translate_module_not_found_in_stderr_returns_actionable_error() -> None:
    """Inner-process ModuleNotFoundError → MCPConnectionError with uvx guidance."""
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "/usr/lib/python3.11/runpy.py", line 226, in _run_module_as_main\n'
        "ModuleNotFoundError: No module named 'mcp_server_nonexistent'\n"
    )
    err = _translate_inner_spawn_error(
        exc=None,
        stderr_text=stderr,
        command="python",
    )
    assert isinstance(err, MCPConnectionError)
    msg = str(err)
    # Must name the missing module AND propose the runtime-fetch shape.
    assert "mcp_server_nonexistent" in msg
    assert "uvx" in msg
    assert "pip install" in msg


def test_translate_runpy_cli_no_module_named() -> None:
    """`python -m foo` when foo isn't installed → `<argv0>: No module named foo`.

    F9 L2 regression: operator hit `MCPConnectionError: MCP connect failed:
    McpError: Connection closed` because D3's _MODULE_NOT_FOUND_RE only
    matched the import-statement form, not the runpy CLI form. The
    broadened regex now catches both surfaces.
    """
    stderr = "/usr/local/bin/python: No module named mcp_server_time\n"
    err = _translate_inner_spawn_error(
        exc=None,
        stderr_text=stderr,
        command="python",
    )
    assert isinstance(err, MCPConnectionError)
    assert "mcp_server_time" in str(err)
    assert "uvx" in str(err)


def test_translate_returns_none_for_generic_failure() -> None:
    """Generic stderr (no D3 pattern matches) → None (caller falls back)."""
    stderr = "[error] server crashed: SIGSEGV\n"
    err = _translate_inner_spawn_error(
        exc=None,
        stderr_text=stderr,
        command="some-mcp",
    )
    assert err is None


def test_translate_returns_none_for_empty_stderr_and_no_exc() -> None:
    """No exc + empty stderr → None."""
    assert _translate_inner_spawn_error(exc=None, stderr_text="", command="foo") is None


# ── Bwrap-discriminator gate (F3 §6 directionality contract) ────────────


def test_bwrap_side_filenotfounderror_does_not_get_mistranslated() -> None:
    """A bwrap-side failure is gated to SandboxError, not D3.

    Simulates the case where bwrap itself reports it cannot find the
    inner command (bwrap's own `bwrap: ...` line in stderr). The bwrap-
    discriminator gate must fire BEFORE D3 translation runs, so the
    output is SandboxError, not the D3 "missing in container"
    MCPConnectionError.

    Verified by routing through the same translation surface used by the
    actual unwind path: when bwrap stderr is bwrap-prefixed, the upstream
    helper (`_translate_bwrap_stderr`) returns a `SandboxError`, and
    callers gate `_translate_inner_spawn_error` behind `not
    _BWRAP_OWN_PREFIX_RE.search(stderr)`. This test asserts both halves
    of that contract.
    """
    bwrap_stderr = "bwrap: execvp some-missing-command: No such file or directory\n"
    # 1. The bwrap-stderr translator returns a SandboxError for this
    #    text (catalog #2 — generic bwrap failure, prefix-gated).
    sandbox_err = stdio_module._translate_bwrap_stderr(bwrap_stderr)
    assert isinstance(sandbox_err, SandboxError)

    # 2. The bwrap-prefix discriminator fires for this text — meaning the
    #    `_translate_on_unwind` callback in `_open_stdio_transport_stack`
    #    (and the `connect_stdio` `finally:` block) will NOT call
    #    `_translate_inner_spawn_error` for this stderr at all. The D3
    #    helper is gated behind `not _BWRAP_OWN_PREFIX_RE.search(stderr)`.
    assert stdio_module._BWRAP_OWN_PREFIX_RE.search(bwrap_stderr) is not None


def test_inner_process_filenotfounderror_does_not_appear_with_bwrap_prefix() -> None:
    """Inner-process stderr without bwrap-prefix → D3 fires.

    Mirror image of the above: when stderr has NO `bwrap:` prefix line,
    the discriminator does NOT fire, so D3 translation runs. This is the
    operator-friendly path the leg artifact is targeting.
    """
    inner_stderr = (
        "Traceback (most recent call last):\nModuleNotFoundError: No module named 'foo'\n"
    )
    # No bwrap prefix → discriminator does NOT match → D3 runs.
    assert stdio_module._BWRAP_OWN_PREFIX_RE.search(inner_stderr) is None
    err = _translate_inner_spawn_error(
        exc=None,
        stderr_text=inner_stderr,
        command="python",
    )
    assert isinstance(err, MCPConnectionError)
    assert "foo" in str(err)


# ── Pattern 3 (F9 L2 vibing): python: can't open file ──────────────────


def test_translate_python_cant_open_file_returns_actionable_error() -> None:
    """`python: can't open file '<path>'` → MCPConnectionError with operator guidance.

    Fires when the operator's `command=python args=[<bad-script-arg>]`
    resolves to a non-existent script — most commonly because args carry
    literal quote characters around values (e.g., args=["\\"-m\\""]) so
    Python interprets the quoted token as a script filename and exits 2
    before any module is even resolved.
    """
    stderr = "python: can't open file '\"-m\"': [Errno 2] No such file or directory\n"
    err = _translate_inner_spawn_error(
        exc=None,
        stderr_text=stderr,
        command="python",
    )
    assert isinstance(err, MCPConnectionError)
    msg = str(err)
    # Must name the offending path AND propose the actionable fixes.
    assert '"-m"' in msg
    assert "literal quote characters" in msg
    assert "uvx" in msg


def test_translate_python_cant_open_file_with_real_path() -> None:
    """Variant: a real-looking path that doesn't exist still triggers D3."""
    stderr = (
        "python: can't open file '/srv/missing_script.py': [Errno 2] No such file or directory\n"
    )
    err = _translate_inner_spawn_error(
        exc=None,
        stderr_text=stderr,
        command="python",
    )
    assert isinstance(err, MCPConnectionError)
    assert "/srv/missing_script.py" in str(err)


def test_python_cant_open_file_does_not_fire_when_bwrap_prefixed() -> None:
    """Bwrap-prefixed stderr → discriminator gates D3 (including Pattern 3).

    The bwrap-discriminator gate is upstream of `_translate_inner_spawn_error`
    in the unwind callbacks (`_open_stdio_transport_stack` and the
    `connect_stdio` `finally:` block). If a bwrap-side failure happens to
    contain a `can't open file` substring (unlikely in practice but
    important for the directionality contract), the gate prevents D3 from
    mistranslating it.
    """
    bwrap_stderr = "bwrap: execvp python: can't open file 'foo': No such file or directory\n"
    # Discriminator MUST match — caller gates D3 behind
    # `not _BWRAP_OWN_PREFIX_RE.search(stderr)`.
    assert stdio_module._BWRAP_OWN_PREFIX_RE.search(bwrap_stderr) is not None
