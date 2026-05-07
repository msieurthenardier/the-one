"""F3 L5a real-subprocess sandbox integration tests.

Drives ``MCPClient.call_tool`` through the L4 sandbox-wrapped
``connect_stdio`` path against a real bwrap-spawned FastMCP subprocess
(``tests/fixtures/mcp/hello_server.py --stdio --with-naughty-tools``).
Each test exercises one of the F3 sandbox invariants by calling a
TEST-ONLY escape-attempt tool that the sandbox should refuse.

Coverage matrix:

* #1   FS scope refusal — ``write_outside_sandbox("/etc/...")`` under
       strict-floor profile raises ``MCPCallError`` (read-only via
       ``--ro-bind / /``).
* #2   Writable-path mechanism — ``writable_paths=["/var/tmp/..."]``
       grants write access; the host-visible bind mount persists the
       bytes. Uses ``/var/tmp`` to avoid the L3 ``--bind`` / ``--tmpfs
       /tmp`` ordering edge case.
* #3   Env-allowlist invariant — ``dump_env()`` returns only allowlist +
       operator-config + HOME-override keys; host-only keys (e.g.,
       PYTEST_CURRENT_TEST) are filtered. Filtering attribution: 8-key
       allowlist via ``_build_subprocess_env`` (NOT primarily
       ``--clearenv`` — that's defense-in-depth).
* #4   Network refusal — ``try_connect("8.8.8.8", 53)`` under
       ``network_allowed=False`` + ``--unshare-net`` returns a
       network-unreachable error string (IP-literal avoids DNS).
* #5   Network allowed — same call under ``network_allowed=True``
       returns ``"connected"``. Skipped if test-runner has no outbound.
* #6   Writable-path nonexistent — surfaces as ``MCPConnectionError``
       per L4 Anomaly A02 (deferred bwrap-side translation; NOT
       ``MCPSandboxError``). Locks the deferred-translation gap as a
       positive test.
* #7   No host-env leakage — process-env-only sentinel key is filtered
       by the 8-key allowlist + ``--clearenv`` defense-in-depth.
* #8   ``--with-naughty-tools`` opt-in registers all five tools.
* #9   Without ``--with-naughty-tools`` the three escape-attempt tools
       are absent (only ``echo`` / ``add`` remain).
* #10  In-process unit test on ``register_naughty_tools`` — runs
       unconditionally, no subprocess, no sandbox; gives early CI
       signal for accidental autoregistration regressions before the
       slow integration tests run.

Edge case documented in the flight log: L3's argv compiler emits
``--bind`` BEFORE ``--tmpfs /tmp``, so any ``writable_paths`` entry
under ``/tmp`` is shadowed by the later ``--tmpfs /tmp``. Operators
must use writable_paths OUTSIDE ``/tmp`` for persistent scratch.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.mcp.hello_server import (
    make_mcp_app,
    register_naughty_tools,
)
from the_one.db.models import MCPSource
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPCallError, MCPConnectionError, MCPSandboxError

# ---------------------------------------------------------------------------
# Module-level constants + helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BWRAP_REQUIRED_REASON = "bwrap required for real-subprocess sandbox integration"

# Tests #1-9 are real-subprocess; gate at module scope so collection still
# works on hosts without bwrap. Test #10 is in-process and runs unconditionally.
requires_bwrap = pytest.mark.skipif(
    shutil.which("bwrap") is None, reason=_BWRAP_REQUIRED_REASON
)


def _build_naughty_source(
    *,
    sandbox: dict[str, Any] | None = None,
    extra_env: dict[str, str] | None = None,
    with_naughty: bool = True,
) -> MCPSource:
    """Build an MCPSource that launches the hello fixture under sandbox.

    The subprocess running INSIDE the sandbox needs PYTHONPATH = project
    root so the ``tests.fixtures.mcp.hello_server`` module is
    importable. ``--ro-bind / /`` makes the dev container's
    site-packages visible, but the fixture path itself requires
    PYTHONPATH for the module-search machinery.

    The returned source is constructed via ``MCPSource(...)`` directly
    (bypassing the L1b API validator) so tests can probe profile shapes
    without round-tripping through the API layer.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(_PROJECT_ROOT),
    }
    if extra_env:
        env.update(extra_env)
    args = ["-m", "tests.fixtures.mcp.hello_server", "--stdio"]
    if with_naughty:
        args.append("--with-naughty-tools")
    config: dict[str, Any] = {
        "command": sys.executable,
        "args": args,
        "env": env,
        "cwd": str(_PROJECT_ROOT),
    }
    if sandbox is not None:
        config["sandbox"] = sandbox
    return MCPSource(
        id="src-l5a-naughty",
        name="naughty",
        type="stdio",
        config=config,
        secrets={},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def writable_scratch_dir() -> Any:
    """Session-scoped writable scratch dir at /var/tmp/sandbox_l5a_<uuid>.

    Uses /var/tmp (NOT /tmp) to dodge the L3 argv-compilation edge case:
    L3 emits ``--bind`` BEFORE ``--tmpfs /tmp``, so a
    ``writable_paths=["/tmp/foo"]`` entry would be shadowed by the
    later ``--tmpfs /tmp`` (the bind mount becomes invisible).
    Operators wanting persistent writable scratch must use paths
    outside ``/tmp`` until L3's argv is reordered.

    UUID-suffixed for parallel safety under pytest-xdist; teardown
    removes the directory tree even if individual probe files remain.
    """
    scratch = Path(f"/var/tmp/sandbox_l5a_{uuid.uuid4().hex}")
    scratch.mkdir(parents=True, exist_ok=False)
    try:
        yield scratch
    finally:
        # Best-effort cleanup; bwrap-bound bind mounts are torn down
        # automatically when bwrap exits (--die-with-parent). Any residue
        # is just regular host files at this point.
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)


def _has_outbound_network() -> bool:
    """Probe whether the test runner can make an outbound TCP connect.

    Used by test #5 to skip when the test-runner has no outbound
    network — proves the test failure (when it happens) was caused by
    ``--unshare-net``, not by a missing route on the runner itself.
    """
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=2.0):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# #1 — FS scope refusal under strict-floor profile
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_refuses_fs_write_outside_writable_paths() -> None:
    """Strict-floor profile (writable_paths=[]) refuses writes outside /tmp.

    Calls ``write_outside_sandbox(path="/etc/test_escape", content="x")``
    through the sandbox; expects ``MCPCallError`` (F2's translation of
    FastMCP's ``isError=true`` envelope) with strerror text in the
    message. Python's OSError.__str__ uses strerror (e.g.,
    ``"Read-only file system"`` / ``"Permission denied"``) rather than
    symbolic names like EROFS / EACCES, so the substring match looks
    for the strerror forms only.
    """
    source = _build_naughty_source(
        sandbox={"writable_paths": [], "network_allowed": False},
    )
    async with MCPClient(source) as client:
        with pytest.raises(MCPCallError) as exc_info:
            await client.call_tool(
                "write_outside_sandbox",
                {"path": "/etc/test_escape", "content": "x"},
            )

    message = str(exc_info.value)
    assert (
        "Read-only" in message or "Permission denied" in message
    ), f"expected strerror text in error message, got: {message!r}"


# ---------------------------------------------------------------------------
# #2 — Writable-path mechanism actually works
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_allows_fs_write_when_path_in_writable_paths(
    writable_scratch_dir: Path,
) -> None:
    """A writable_paths entry grants write access; bytes persist on host.

    Uses /var/tmp (NOT /tmp) per the L3 argv-shadowing edge case
    documented in the module docstring + flight log. After the tool
    call succeeds, reads the file from the HOST filesystem to prove
    the write actually persisted to the host-visible bind mount, not
    just to a sandbox-internal tmpfs.
    """
    probe_path = writable_scratch_dir / "probe"
    source = _build_naughty_source(
        sandbox={
            "writable_paths": [str(writable_scratch_dir)],
            "network_allowed": False,
        },
    )
    async with MCPClient(source) as client:
        result = await client.call_tool(
            "write_outside_sandbox",
            {"path": str(probe_path), "content": "hello"},
        )

    assert "wrote 5 bytes" in result.text
    # Verify on HOST that the bytes actually landed on the bind-mounted file.
    assert probe_path.read_text() == "hello"


# ---------------------------------------------------------------------------
# #3 — Env-allowlist invariant (with HOME=/tmp override)
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_env_allowlist_invariant_with_home_override() -> None:
    """dump_env() returns only allowlist + operator-config + HOME=/tmp.

    Filtering attribution per L5a leg spec: ``_build_subprocess_env``
    filters ``os.environ`` to the 8-key allowlist BEFORE the env
    reaches ``BubblewrapSandbox.prepare_spawn``. PYTEST_CURRENT_TEST /
    LD_PRELOAD / PYTHONHOME / etc. are dropped by the platform-env
    allowlist; bwrap's ``--clearenv`` is defense-in-depth.
    """
    source = _build_naughty_source(
        sandbox={"writable_paths": [], "network_allowed": False},
    )
    async with MCPClient(source) as client:
        result = await client.call_tool("dump_env", {})

    # FastMCP serializes dict[str, str] returns; the structured payload
    # is the dict directly (no "result" wrapper for already-dict returns).
    assert result.structured is not None
    env_dict = result.structured
    assert isinstance(env_dict, dict)

    # HOME forced to /tmp by the §13 sandbox-policy override.
    assert env_dict.get("HOME") == "/tmp"
    # PATH from the operator-supplied env (also a member of the 8-key
    # allowlist; passed through unchanged).
    assert "PATH" in env_dict
    # PYTHONPATH from the operator config.env — not in the 8-key
    # allowlist but passed through as an operator-supplied key.
    assert "PYTHONPATH" in env_dict
    # Host-only keys that pytest sets in the test process MUST NOT leak.
    # PYTEST_CURRENT_TEST is set by pytest itself for every running test;
    # if the allowlist filter or --clearenv worked, it's absent here.
    assert "PYTEST_CURRENT_TEST" not in env_dict


# ---------------------------------------------------------------------------
# #4 — Network refusal under --unshare-net
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_network_refused_under_unshare_net() -> None:
    """try_connect under network_allowed=False returns network-unreachable.

    IP-literal target (8.8.8.8:53) avoids DNS resolution being the
    failure cause; under ``--unshare-net``, the OS-level network
    namespace is empty so connect raises ENETUNREACH or similar.
    The tool returns the error as a string (does NOT raise) so we
    assert on the value directly.
    """
    source = _build_naughty_source(
        sandbox={"writable_paths": [], "network_allowed": False},
    )
    async with MCPClient(source) as client:
        result = await client.call_tool(
            "try_connect", {"host": "8.8.8.8", "port": 53}
        )

    text = result.text
    # Different kernels emit different strerror text for the
    # network-namespace-empty case; accept any of the canonical forms.
    assert (
        "Network is unreachable" in text
        or "ENETUNREACH" in text
        or "Network unreachable" in text
        or "Connection refused" in text
        or "No route to host" in text
        or "connect failed" in text
    ), f"expected network-failure text, got: {text!r}"


# ---------------------------------------------------------------------------
# #5 — Network allowed when network_allowed=True
# ---------------------------------------------------------------------------


@requires_bwrap
@pytest.mark.skipif(
    not _has_outbound_network(),
    reason="test runner has no outbound network; can't validate network_allowed=True",
)
async def test_sandbox_network_allowed_when_network_allowed_true() -> None:
    """Under network_allowed=True the connect succeeds (no --unshare-net).

    Skip-gated on the test-runner's own outbound capability — proves
    the failure (if any) is in the sandbox-allowed path, not in the
    runner's missing route. Targets 8.8.8.8:53 (Google DNS) as a
    well-known always-up TCP endpoint with low ambient flake.
    """
    source = _build_naughty_source(
        sandbox={"writable_paths": [], "network_allowed": True},
    )
    async with MCPClient(source) as client:
        result = await client.call_tool(
            "try_connect", {"host": "8.8.8.8", "port": 53}
        )

    assert result.text == "connected"


# ---------------------------------------------------------------------------
# #6 — Writable_paths nonexistent → MCPConnectionError per L4 Anomaly A02
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_writable_paths_nonexistent_raises_at_connect() -> None:
    """Nonexistent writable_paths entry surfaces as MCPConnectionError.

    Per L4 Anomaly A02: bwrap-side post-setup errors (writable_paths
    nonexistent, EPERM on unshare, etc.) are NOT translated to
    ``MCPSandboxError`` in F3 — they surface as F2's
    ``MCPConnectionError`` via ``MCPClient.connect``'s
    ``except Exception`` translation. Empirically: bwrap exits non-zero
    with ``bwrap: Can't find source path /var/does/not/exist_<uuid>``;
    stdio_client sees broken pipe; SDK initialize() raises;
    MCPClient.connect catches and translates.

    Locks the deferred-translation gap as a positive test (rather than
    skipping). The substring assertion on bwrap stderr is omitted —
    whether stderr propagates up the stdio_client chain to the
    exception message is empirically variable.
    """
    nonexistent = f"/var/does/not/exist_{uuid.uuid4().hex}"
    source = _build_naughty_source(
        sandbox={"writable_paths": [nonexistent], "network_allowed": False},
    )

    with pytest.raises(MCPConnectionError) as exc_info:
        async with MCPClient(source):
            pass

    # Critical directionality: MCPSandboxError is a sibling of
    # MCPConnectionError (both subclass MCPClientError), NOT a parent —
    # so an MCPSandboxError instance would NOT satisfy isinstance(...,
    # MCPConnectionError) anyway. We still assert NOT MCPSandboxError to
    # lock the directionality explicitly per L4 Anomaly A02.
    assert not isinstance(exc_info.value, MCPSandboxError)


# ---------------------------------------------------------------------------
# #7 — No host-env leakage via process-env-only sentinel
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_dump_env_no_secret_leakage_via_test_runner_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process-env-only sentinel key is filtered by the env-allowlist.

    Sets a sentinel key in the TEST PROCESS env (via monkeypatch); does
    NOT add it to ``config.env``. Under the strict-floor profile, the
    8-key allowlist filter at ``_build_subprocess_env`` drops it before
    the env reaches the sandbox; bwrap's ``--clearenv`` is
    defense-in-depth. Asserts the sentinel is absent from
    ``dump_env()``'s returned dict — locks the env-allowlist invariant
    against host-env leakage.
    """
    sentinel_key = f"F3_TEST_LEAK_SENTINEL_{uuid.uuid4().hex.upper()}"
    monkeypatch.setenv(sentinel_key, "should_not_leak")

    source = _build_naughty_source(
        sandbox={"writable_paths": [], "network_allowed": False},
    )
    async with MCPClient(source) as client:
        result = await client.call_tool("dump_env", {})

    assert result.structured is not None
    env_dict = result.structured
    assert isinstance(env_dict, dict)
    assert (
        sentinel_key not in env_dict
    ), f"sentinel {sentinel_key!r} leaked through to sandboxed subprocess"


# ---------------------------------------------------------------------------
# #8 — --with-naughty-tools registers all five tools
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_with_naughty_tools_flag_registers_three_tools() -> None:
    """list_tools with --with-naughty-tools sees all 5 tools.

    Locks the opt-in registration mechanism: the three escape-attempt
    tools plus the original two F2 tools (echo + add) MUST all be
    present when the flag is passed.
    """
    source = _build_naughty_source(
        sandbox={"writable_paths": [], "network_allowed": False},
        with_naughty=True,
    )
    async with MCPClient(source) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "echo",
        "add",
        "write_outside_sandbox",
        "dump_env",
        "try_connect",
    }


# ---------------------------------------------------------------------------
# #9 — without --with-naughty-tools the naughty tools are absent
# ---------------------------------------------------------------------------


@requires_bwrap
async def test_sandbox_without_naughty_tools_flag_omits_naughty_tools() -> None:
    """list_tools WITHOUT --with-naughty-tools sees only echo + add.

    Locks the opt-in mechanism's directionality — the existing F2
    hello tests (which never pass the flag) keep working because the
    naughty tools don't appear in their tool list.
    """
    source = _build_naughty_source(
        sandbox={"writable_paths": [], "network_allowed": False},
        with_naughty=False,
    )
    async with MCPClient(source) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert names == {"echo", "add"}


# ---------------------------------------------------------------------------
# #10 — In-process unit test on register_naughty_tools (no subprocess)
# ---------------------------------------------------------------------------


def test_register_naughty_tools_in_process() -> None:
    """register_naughty_tools is opt-in; make_mcp_app() never auto-registers.

    Pure-Python introspection on FastMCP's tool manager — no subprocess,
    no sandbox. Fast (<10ms) early signal for accidental
    autoregistration regressions before the slow integration tests
    run. Runs unconditionally (no bwrap requirement).
    """
    # First app: explicitly register the naughty tools.
    app_with = make_mcp_app()
    register_naughty_tools(app_with)
    names_with = {t.name for t in app_with._tool_manager.list_tools()}
    assert names_with == {
        "echo",
        "add",
        "write_outside_sandbox",
        "dump_env",
        "try_connect",
    }

    # Second app: do NOT call register_naughty_tools — must contain only
    # the F2 tools. Locks the "make_mcp_app never auto-registers" invariant.
    app_without = make_mcp_app()
    names_without = {t.name for t in app_without._tool_manager.list_tools()}
    assert names_without == {"echo", "add"}
