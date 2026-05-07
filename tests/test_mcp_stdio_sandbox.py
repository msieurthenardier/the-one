"""F3 L4: ``connect_stdio`` sandbox-integration tests.

Verifies that the stdio transport wraps every spawn through
``BubblewrapSandbox.prepare_spawn`` unless the F3 §10 double-flag bypass
(``THE_ONE_SANDBOX_DISABLED=1`` AND ``THE_ONE_TEST_MODE=1``) is set.

Coverage matrix:

* §1   bwrap CLI shape — sandbox is invoked when bypass is OFF and the
       resulting ``StdioServerParameters`` carries the bwrap-wrapped
       command/args/env/cwd.
* §2   ``config.sandbox`` round-trip — operator-supplied profile flows
       through ``SandboxProfile.from_dict`` into ``prepare_spawn``.
* §3   double-flag bypass works — both flags set → sandbox is skipped.
* §4/5 single-flag does NOT bypass — only ``SANDBOX_DISABLED=1`` (no
       ``TEST_MODE``) and only ``TEST_MODE=1`` (no ``SANDBOX_DISABLED``)
       both keep the sandbox active.
* §6   ``MCPSandboxError`` propagates — when ``BubblewrapSandbox()``
       raises (bwrap missing AND bypass not active), ``connect_stdio``
       does NOT swallow or translate.
* §7   SDK env preservation — operator's allowlist + config.env +
       secrets all survive the bwrap ``--clearenv`` + per-key
       ``--setenv`` round-trip; HOME forced to ``/tmp``.
* §8   real-subprocess integration — drives ``connect_stdio`` against
       ``/bin/cat`` under real bwrap; success criterion is "anything
       except ``MCPSandboxError``" (the wrapped target is not a real
       MCP server, so post-spawn handshake will fail; we only assert
       the sandbox boundary was crossed). Skipped if ``bwrap`` not
       available on the test runner.
* §9   ``SandboxProfile`` validation error propagation — operator
       submits a type-mismatched ``config.sandbox`` field; ``ValueError``
       propagates from ``SandboxProfile.from_dict`` and is NOT
       translated to ``MCPSandboxError`` (programmer/validator
       boundary, not sandbox-setup boundary).
"""

from __future__ import annotations

import asyncio
import shutil
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from the_one.db.models import MCPSource
from the_one.mcp.errors import MCPSandboxError
from the_one.mcp.transports import stdio as stdio_module
from the_one.mcp.transports.stdio import connect_stdio
from the_one.platform.sandbox import SandboxProfile, SpawnSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(**config_overrides: Any) -> MCPSource:
    """Build an in-test stdio MCPSource with sensible defaults.

    Bypasses the L1b API validator so test cases can probe the
    transport's behaviour with malformed sandbox sub-blocks (per §9's
    "programmer/validator boundary" test).
    """
    config: dict[str, Any] = {
        "command": "/bin/echo",
        "args": ["hello"],
        "env": {},
        "cwd": None,
    }
    config.update(config_overrides)
    return MCPSource(
        id="src-l4-test",
        name="l4-test-source",
        type="stdio",
        config=config,
        secrets={},
    )


def _stub_stdio_client_factory(
    captured: dict[str, Any],
) -> Any:
    """Build a stub ``stdio_client`` that captures the StdioServerParameters
    it receives and yields a (read, write) pair of MagicMocks.

    The yielded mocks are async-context-manager-compatible so they
    interoperate with ``async with stdio_client(params) as (read, write)``.
    The ``ClientSession`` constructed downstream is also patched (via the
    caller-side ``patch``); this stub only needs to provide the read/write
    slots and capture ``params``.
    """

    @asynccontextmanager
    async def _stub(params: Any) -> Any:
        captured["params"] = params
        yield (MagicMock(name="read"), MagicMock(name="write"))

    return _stub


def _stub_client_session_factory() -> Any:
    """Build a stub ``ClientSession`` that yields a MagicMock session.

    The transport entered-but-not-initialized contract means we never
    drive ``initialize()`` from inside ``connect_stdio`` itself, so a
    plain MagicMock suffices. The mock is async-context-manager-aware
    (``__aenter__`` / ``__aexit__`` provided by MagicMock-on-async-cm).
    """

    @asynccontextmanager
    async def _session_stub(read: Any, write: Any) -> Any:
        del read, write  # transport stubs already captured what we needed
        yield MagicMock(name="session")

    return _session_stub


# ---------------------------------------------------------------------------
# §1 — bwrap CLI shape
# ---------------------------------------------------------------------------


async def test_connect_stdio_invokes_bubblewrap_when_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the double-flag bypass is OFF, ``BubblewrapSandbox`` is
    instantiated and ``prepare_spawn`` is called with a strict-floor
    profile + the operator's command/args/env/cwd.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    # THE_ONE_TEST_MODE may be set by conftest; that's fine — single
    # flag is not enough to bypass.

    captured: dict[str, Any] = {}
    sandbox_instance = MagicMock(name="sandbox-instance")
    sandbox_instance.prepare_spawn.return_value = SpawnSpec(
        command="bwrap",
        args=["--die-with-parent", "--", "/bin/echo", "hello"],
        env={"PATH": "/usr/bin"},
        cwd=None,
    )
    sandbox_cls = MagicMock(name="BubblewrapSandbox", return_value=sandbox_instance)

    source = _make_source()

    with (
        patch.object(stdio_module, "BubblewrapSandbox", sandbox_cls),
        patch.object(
            stdio_module, "stdio_client", _stub_stdio_client_factory(captured)
        ),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source) as session:
            assert session is not None

    sandbox_cls.assert_called_once_with()  # zero-arg construction
    sandbox_instance.prepare_spawn.assert_called_once()
    call_args = sandbox_instance.prepare_spawn.call_args
    profile_arg = call_args.args[0]
    command_arg = call_args.args[1]
    args_arg = call_args.args[2]
    cwd_arg = call_args.args[4]
    assert isinstance(profile_arg, SandboxProfile)
    assert profile_arg == SandboxProfile()  # strict-floor (config.sandbox absent)
    assert command_arg == "/bin/echo"
    assert args_arg == ["hello"]
    assert cwd_arg is None
    # The StdioServerParameters that reached stdio_client uses bwrap's
    # wrapped command/args, not the bare /bin/echo.
    assert captured["params"].command == "bwrap"
    assert "/bin/echo" in captured["params"].args


# ---------------------------------------------------------------------------
# §2 — config.sandbox round-trip
# ---------------------------------------------------------------------------


async def test_connect_stdio_passes_config_sandbox_to_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``config.sandbox`` is parsed via ``SandboxProfile.from_dict``
    and the resulting profile is handed to ``prepare_spawn``.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    captured: dict[str, Any] = {}
    sandbox_instance = MagicMock(name="sandbox-instance")
    sandbox_instance.prepare_spawn.return_value = SpawnSpec(
        command="bwrap",
        args=["--", "/bin/echo"],
        env={},
        cwd=None,
    )
    sandbox_cls = MagicMock(name="BubblewrapSandbox", return_value=sandbox_instance)

    source = _make_source(
        sandbox={"writable_paths": ["/data"], "network_allowed": True},
    )

    with (
        patch.object(stdio_module, "BubblewrapSandbox", sandbox_cls),
        patch.object(
            stdio_module, "stdio_client", _stub_stdio_client_factory(captured)
        ),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    profile_arg = sandbox_instance.prepare_spawn.call_args.args[0]
    assert profile_arg.writable_paths == ["/data"]
    assert profile_arg.network_allowed is True
    # Defaults preserved for the namespace flags we didn't override.
    assert profile_arg.pid_unshare is True
    assert profile_arg.ipc_unshare is True
    assert profile_arg.uts_unshare is True


# ---------------------------------------------------------------------------
# §3 — double-flag bypass WORKS
# ---------------------------------------------------------------------------


async def test_connect_stdio_double_flag_bypass_skips_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting BOTH ``THE_ONE_SANDBOX_DISABLED=1`` AND
    ``THE_ONE_TEST_MODE=1`` skips the sandbox wrap. ``stdio_client``
    receives the bare ``command/args/env/cwd``, and
    ``BubblewrapSandbox`` is never instantiated.
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")

    captured: dict[str, Any] = {}
    sandbox_cls = MagicMock(name="BubblewrapSandbox")

    source = _make_source()

    with (
        patch.object(stdio_module, "BubblewrapSandbox", sandbox_cls),
        patch.object(
            stdio_module, "stdio_client", _stub_stdio_client_factory(captured)
        ),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    sandbox_cls.assert_not_called()
    assert captured["params"].command == "/bin/echo"
    assert captured["params"].args == ["hello"]


# ---------------------------------------------------------------------------
# §4 — only SANDBOX_DISABLED does NOT bypass
# ---------------------------------------------------------------------------


async def test_connect_stdio_only_sandbox_disabled_flag_does_not_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting only ``THE_ONE_SANDBOX_DISABLED=1`` (without
    ``THE_ONE_TEST_MODE``) does NOT bypass the sandbox.
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    captured: dict[str, Any] = {}
    sandbox_instance = MagicMock(name="sandbox-instance")
    sandbox_instance.prepare_spawn.return_value = SpawnSpec(
        command="bwrap", args=["--", "/bin/echo"], env={}, cwd=None
    )
    sandbox_cls = MagicMock(name="BubblewrapSandbox", return_value=sandbox_instance)

    source = _make_source()

    with (
        patch.object(stdio_module, "BubblewrapSandbox", sandbox_cls),
        patch.object(
            stdio_module, "stdio_client", _stub_stdio_client_factory(captured)
        ),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    sandbox_cls.assert_called_once_with()


# ---------------------------------------------------------------------------
# §5 — only TEST_MODE does NOT bypass (clean-room directionality)
# ---------------------------------------------------------------------------


async def test_connect_stdio_only_test_mode_flag_does_not_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting only ``THE_ONE_TEST_MODE=1`` (without
    ``THE_ONE_SANDBOX_DISABLED``) does NOT bypass the sandbox.

    Clean-room directionality assertion: the conftest's
    ``pytest_configure`` already sets ``THE_ONE_TEST_MODE=1``, so this
    test only needs to ensure ``THE_ONE_SANDBOX_DISABLED`` is absent
    via ``monkeypatch.delenv(..., raising=False)``.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")

    captured: dict[str, Any] = {}
    sandbox_instance = MagicMock(name="sandbox-instance")
    sandbox_instance.prepare_spawn.return_value = SpawnSpec(
        command="bwrap", args=["--", "/bin/echo"], env={}, cwd=None
    )
    sandbox_cls = MagicMock(name="BubblewrapSandbox", return_value=sandbox_instance)

    source = _make_source()

    with (
        patch.object(stdio_module, "BubblewrapSandbox", sandbox_cls),
        patch.object(
            stdio_module, "stdio_client", _stub_stdio_client_factory(captured)
        ),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    sandbox_cls.assert_called_once_with()


# ---------------------------------------------------------------------------
# §6 — MCPSandboxError propagates from BubblewrapSandbox() construction
# ---------------------------------------------------------------------------


async def test_connect_stdio_propagates_mcpsandbox_error_when_bwrap_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``shutil.which("bwrap")`` returns None and the bypass is
    NOT active, ``BubblewrapSandbox()`` raises ``MCPSandboxError``;
    ``connect_stdio`` propagates it without swallowing or translating.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    # Force BubblewrapSandbox.__init__ to think bwrap is missing.
    # The import path inside bubblewrap.py is `import shutil` then
    # `shutil.which("bwrap")` — patch the `shutil.which` attribute on
    # the bubblewrap module's bound `shutil`.
    from the_one.platform.sandbox import bubblewrap as bwrap_module

    monkeypatch.setattr(bwrap_module.shutil, "which", lambda _name: None)

    source = _make_source()

    with pytest.raises(MCPSandboxError) as exc_info:
        async with connect_stdio(source):
            pass

    assert "bubblewrap binary not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# §7 — SDK env preservation through bwrap --clearenv + --setenv
# ---------------------------------------------------------------------------


async def test_connect_stdio_sdk_default_env_preserved_through_setenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The env passed into ``stdio_client`` (via
    ``StdioServerParameters.env``) carries the operator's allowlist +
    ``config.env`` + secrets, and HOME is forced to ``/tmp`` by the
    sandbox layer. Assertion shape: capture the params reaching
    ``stdio_client`` and assert env-key presence post-bwrap.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    # Provide a stable allowlist underlay regardless of host env shape.
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin:/bin")
    monkeypatch.setenv("LANG", "C.UTF-8")

    captured: dict[str, Any] = {}
    # Use a real BubblewrapSandbox so the --clearenv/--setenv round-trip
    # is exercised end-to-end, but force `shutil.which("bwrap")` to
    # return a known truthy value so __init__ doesn't raise even on
    # hosts without bwrap.
    from the_one.platform.sandbox import bubblewrap as bwrap_module

    monkeypatch.setattr(bwrap_module.shutil, "which", lambda _name: "/usr/bin/bwrap")

    source = _make_source(
        env={"MY_PLAIN": "plain-value"},
    )
    source = source.model_copy(update={"secrets": {"MY_SECRET": "secret-value"}})

    with (
        patch.object(
            stdio_module, "stdio_client", _stub_stdio_client_factory(captured)
        ),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    spec_env: dict[str, str] = captured["params"].env
    # Operator's plaintext + secret env keys survived.
    assert spec_env.get("MY_PLAIN") == "plain-value"
    assert spec_env.get("MY_SECRET") == "secret-value"
    # Allowlist keys present (we monkeypatched PATH and LANG above).
    assert spec_env.get("PATH") == "/usr/local/bin:/usr/bin:/bin"
    assert spec_env.get("LANG") == "C.UTF-8"
    # HOME forced to /tmp by the sandbox policy override (§13).
    assert spec_env.get("HOME") == "/tmp"


# ---------------------------------------------------------------------------
# §8 — real-subprocess integration test (requires real bwrap)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not available")
async def test_connect_stdio_real_subprocess_cat_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real-subprocess integration test: drive ``connect_stdio`` against
    a bwrap-wrapped ``/bin/cat``. The wrapped target is not a real MCP
    server, so the SDK's initialize handshake will fail; the success
    criterion is "anything except ``MCPSandboxError``" (proves the
    sandbox boundary was crossed and the failure is post-spawn).

    Uses ``/bin/cat`` (NOT ``/bin/echo``) because cat reads stdin
    indefinitely — avoids a race condition where echo exits before
    ``stdio_client`` opens its read end.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    source = MCPSource(
        id="src-l4-cat",
        name="cat-real-subprocess",
        type="stdio",
        config={"command": "/bin/cat", "args": [], "env": {}, "cwd": None},
        secrets={},
    )

    with pytest.raises(BaseException) as exc_info:
        async with connect_stdio(source) as session:
            await asyncio.wait_for(session.initialize(), timeout=2.0)

    assert not isinstance(exc_info.value, MCPSandboxError), (
        f"Sandbox setup failed (expected to be crossed): {exc_info.value}"
    )


# ---------------------------------------------------------------------------
# §9 — SandboxProfile validation error propagates as ValueError
# ---------------------------------------------------------------------------


async def test_connect_stdio_propagates_sandbox_profile_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``config.sandbox`` carries a type-mismatched field (e.g.,
    ``network_allowed=42`` instead of bool), ``SandboxProfile.from_dict``
    raises ``ValueError``; ``connect_stdio`` propagates it without
    translating to ``MCPSandboxError``. Anchors the F3 §6 boundary:
    profile-shape errors are programmer/validator boundary, not
    sandbox-setup errors.

    In production, L1b's API validator would reject this config before
    persistence; the test bypasses the validator by constructing
    ``MCPSource`` directly.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    source = _make_source(sandbox={"network_allowed": 42})

    with pytest.raises(ValueError) as exc_info:
        async with connect_stdio(source):
            pass

    assert "network_allowed" in str(exc_info.value)
    assert not isinstance(exc_info.value, MCPSandboxError)
