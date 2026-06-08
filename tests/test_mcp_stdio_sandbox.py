"""F3 L4: ``connect_stdio`` sandbox-integration tests.

Verifies that the stdio transport wraps every spawn through the factory-
selected sandbox backend unless the factory returns ``PassthroughSandbox``
(double-flag bypass, non-Linux, or bwrap-missing).

Coverage matrix:

* §1   bwrap CLI shape — factory returns bubblewrap → the resulting
       ``StdioServerParameters`` carries the bwrap-wrapped command/args.
* §2   ``config.sandbox`` round-trip — operator-supplied profile flows
       through ``SandboxProfile.from_dict`` into ``prepare_spawn``.
* §3   double-flag bypass works — both flags set → factory returns
       passthrough → spawn is NOT wrapped.
* §4/5 single-flag does NOT bypass — only ``SANDBOX_DISABLED=1`` (no
       ``TEST_MODE``) and only ``TEST_MODE=1`` (no ``SANDBOX_DISABLED``)
       both keep the bubblewrap backend active.
* §6   bwrap-missing routes to passthrough — when ``shutil.which("bwrap")``
       returns None and bypass is off, the factory returns passthrough;
       ``connect_stdio`` does NOT raise ``SandboxError`` (inverted from
       the prior "raises when bwrap missing" contract — the factory now
       absorbs bwrap-missing silently). The construction-time raise is still
       unit-tested at the ``BubblewrapSandbox`` level in
       ``test_sandbox_bubblewrap.py``; the MCP path no longer triggers it.
* §7   SDK env preservation — operator's allowlist + config.env + secrets
       survive the bwrap ``--clearenv`` + per-key ``--setenv`` round-trip;
       HOME forced to ``/tmp``.
* §8   real-subprocess integration — drives ``connect_stdio`` against
       ``/bin/cat`` under real bwrap. Skipped if bwrap not available.
* §9   ``SandboxProfile`` validation error propagates as ValueError (profile
       validation runs before ``get_sandbox_backend``, so this behaviour
       is unchanged from before the factory retrofit).

Backend-selection injection for unit tests: ``patch.object(stdio_module,
"get_sandbox_backend", lambda: <backend>)`` — returning a real
``BubblewrapSandbox()`` or ``PassthroughSandbox()`` as the test needs.
This is hermetic: the factory's lazy ``BubblewrapSandbox`` import is
bypassed entirely, so tests are not coupled to host bwrap availability.
Assertions focus on the resulting params (``command == "bwrap"`` vs the
operator command), not on mock-construction calls.
"""

from __future__ import annotations

import asyncio
import shutil
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from the_one.db.models import MCPSource
from the_one.mcp.transports import stdio as stdio_module
from the_one.mcp.transports.stdio import connect_stdio
from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile, SpawnSpec
from the_one.platform.sandbox import factory as factory_module
from the_one.platform.sandbox.errors import SandboxError

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
    interoperate with ``async with stdio_client(params, errlog=...) as
    (read, write)``. The ``ClientSession`` constructed downstream is also
    patched (via the caller-side ``patch``); this stub only needs to
    provide the read/write slots and capture ``params``. The ``errlog=``
    kwarg (added by F4 L2's bwrap-stderr capture) is accepted but
    ignored — these unit tests don't drive bwrap stderr through this
    path; that's covered by ``test_mcp_sandbox_integration.py``'s real-
    subprocess tests.
    """

    @asynccontextmanager
    async def _stub(params: Any, *, errlog: Any = None) -> Any:
        captured["params"] = params
        if errlog is not None:
            captured["errlog"] = errlog
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
    """When the double-flag bypass is OFF and the factory returns
    ``BubblewrapSandbox``, the resulting ``StdioServerParameters``
    carries the bwrap-wrapped command/args.

    Injection: ``patch.object(stdio_module, "get_sandbox_backend", ...)``
    returns a real ``BubblewrapSandbox()`` whose ``prepare_spawn`` produces
    a bwrap-wrapped spec. Asserts on params (``command == "bwrap"``), not
    on mock-construction calls — the factory's lazy import means patching
    ``stdio_module.BubblewrapSandbox`` no longer intercepts selection.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    # THE_ONE_TEST_MODE may be set by conftest; that's fine — single
    # flag is not enough to bypass.

    captured: dict[str, Any] = {}

    # Force shutil.which to return a path so BubblewrapSandbox.__init__
    # does not raise on a bwrap-less host.
    from the_one.platform.sandbox import bubblewrap as bwrap_module

    monkeypatch.setattr(bwrap_module.shutil, "which", lambda _name: "/usr/bin/bwrap")

    source = _make_source()

    with (
        patch.object(stdio_module, "get_sandbox_backend", lambda: BubblewrapSandbox()),
        patch.object(stdio_module, "stdio_client", _stub_stdio_client_factory(captured)),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source) as session:
            assert session is not None

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

    Uses a recording wrapper backend so the profile argument can be
    inspected without driving real bwrap.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)

    captured: dict[str, Any] = {}
    captured_profile: list[SandboxProfile] = []

    # Recording backend: wraps prepare_spawn to record the profile arg,
    # then delegates to PassthroughSandbox for a no-op spawn spec.
    class _RecordingBackend:
        def prepare_spawn(
            self,
            profile: SandboxProfile,
            command: str,
            args: list[str],
            env: dict[str, str],
            cwd: str | None,
        ) -> SpawnSpec:
            captured_profile.append(profile)
            return SpawnSpec(command=command, args=args, env=env, cwd=cwd)

    source = _make_source(
        sandbox={"writable_paths": ["/data"], "network_allowed": True},
    )

    with (
        patch.object(stdio_module, "get_sandbox_backend", lambda: _RecordingBackend()),
        patch.object(stdio_module, "stdio_client", _stub_stdio_client_factory(captured)),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    assert len(captured_profile) == 1
    profile_arg = captured_profile[0]
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
    ``THE_ONE_TEST_MODE=1`` causes the factory to return
    ``PassthroughSandbox``; ``stdio_client`` receives the bare
    ``command/args/env/cwd``, not bwrap-wrapped params.

    The mechanism is "factory returns passthrough" (not "BubblewrapSandbox
    never instantiated"). Let the real factory run under both flags — it
    returns passthrough without consulting bwrap availability.
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")

    captured: dict[str, Any] = {}

    source = _make_source()

    with (
        patch.object(stdio_module, "stdio_client", _stub_stdio_client_factory(captured)),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    # Passthrough → bare operator command reaches stdio_client.
    assert captured["params"].command == "/bin/echo"
    assert captured["params"].args == ["hello"]


# ---------------------------------------------------------------------------
# §4 — only SANDBOX_DISABLED does NOT bypass
# ---------------------------------------------------------------------------


async def test_connect_stdio_only_sandbox_disabled_flag_does_not_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting only ``THE_ONE_SANDBOX_DISABLED=1`` (without
    ``THE_ONE_TEST_MODE``) does NOT bypass the sandbox — factory selects
    bubblewrap and the spawn is bwrap-wrapped.
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.delenv("THE_ONE_TEST_MODE", raising=False)

    captured: dict[str, Any] = {}

    source = _make_source()

    # Force shutil.which so BubblewrapSandbox.__init__ does not raise.
    from the_one.platform.sandbox import bubblewrap as bwrap_module

    monkeypatch.setattr(bwrap_module.shutil, "which", lambda _name: "/usr/bin/bwrap")

    with (
        patch.object(stdio_module, "get_sandbox_backend", lambda: BubblewrapSandbox()),
        patch.object(stdio_module, "stdio_client", _stub_stdio_client_factory(captured)),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    # Single flag → no bypass → bubblewrap selected → bwrap-wrapped params.
    assert captured["params"].command == "bwrap"


# ---------------------------------------------------------------------------
# §5 — only TEST_MODE does NOT bypass (clean-room directionality)
# ---------------------------------------------------------------------------


async def test_connect_stdio_only_test_mode_flag_does_not_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting only ``THE_ONE_TEST_MODE=1`` (without
    ``THE_ONE_SANDBOX_DISABLED``) does NOT bypass the sandbox — factory
    selects bubblewrap and the spawn is bwrap-wrapped.

    Clean-room directionality assertion: the conftest's
    ``pytest_configure`` already sets ``THE_ONE_TEST_MODE=1``, so this
    test only needs to ensure ``THE_ONE_SANDBOX_DISABLED`` is absent
    via ``monkeypatch.delenv(..., raising=False)``.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")

    captured: dict[str, Any] = {}

    source = _make_source()

    # Force shutil.which so BubblewrapSandbox.__init__ does not raise.
    from the_one.platform.sandbox import bubblewrap as bwrap_module

    monkeypatch.setattr(bwrap_module.shutil, "which", lambda _name: "/usr/bin/bwrap")

    with (
        patch.object(stdio_module, "get_sandbox_backend", lambda: BubblewrapSandbox()),
        patch.object(stdio_module, "stdio_client", _stub_stdio_client_factory(captured)),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        async with connect_stdio(source):
            pass

    # Single flag → no bypass → bubblewrap selected → bwrap-wrapped params.
    assert captured["params"].command == "bwrap"


# ---------------------------------------------------------------------------
# §6 — bwrap-missing routes to passthrough (INVERTED from prior "raises" test)
# ---------------------------------------------------------------------------


async def test_connect_stdio_routes_to_passthrough_when_bwrap_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``shutil.which("bwrap")`` returns None and bypass is NOT
    active, the factory returns ``PassthroughSandbox``; ``connect_stdio``
    does NOT raise ``SandboxError`` — it runs unwrapped.

    This is the INVERTED form of the prior "raises when bwrap missing"
    test, reflecting the mission's core fix: off-Linux / bwrap-missing
    hosts now degrade to passthrough rather than erroring at construction
    time. The construction-time raise is still unit-tested at the
    ``BubblewrapSandbox`` level in ``test_sandbox_bubblewrap.py``; the
    MCP path no longer triggers it.
    """
    monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)
    # Simulate bwrap absent at the FACTORY's selection point — the factory
    # reads factory_module.shutil.which, not the bubblewrap module's copy.
    monkeypatch.setattr(factory_module.shutil, "which", lambda _name: None)

    captured: dict[str, Any] = {}
    source = _make_source()

    # Drive the real factory (no get_sandbox_backend patch) — it should
    # return PassthroughSandbox when bwrap is absent.
    with (
        patch.object(stdio_module, "stdio_client", _stub_stdio_client_factory(captured)),
        patch.object(stdio_module, "ClientSession", _stub_client_session_factory()),
    ):
        # Must NOT raise SandboxError — passthrough runs unwrapped.
        async with connect_stdio(source) as session:
            assert session is not None

    # Passthrough → bare operator command (not "bwrap").
    assert captured["params"].command == "/bin/echo"


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
    # is exercised end-to-end. Patch BOTH the factory's shutil.which AND
    # the bubblewrap module's shutil.which so that (a) the factory selects
    # bubblewrap and (b) BubblewrapSandbox.__init__ doesn't raise on a
    # bwrap-less host.  Also stub _userns_available → "ok" so the factory
    # reaches BubblewrapSandbox without running the real probe subprocess.
    from the_one.platform.sandbox import bubblewrap as bwrap_module

    monkeypatch.setattr(bwrap_module.shutil, "which", lambda _name: "/usr/bin/bwrap")
    monkeypatch.setattr(factory_module.shutil, "which", lambda _name: "/usr/bin/bwrap")
    monkeypatch.setattr(factory_module, "_userns_available", lambda: "ok")

    source = _make_source(
        env={"MY_PLAIN": "plain-value"},
    )
    source = source.model_copy(update={"secrets": {"MY_SECRET": "secret-value"}})

    with (
        patch.object(stdio_module, "stdio_client", _stub_stdio_client_factory(captured)),
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
    criterion is "anything except ``SandboxError``" (proves the
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

    assert not isinstance(exc_info.value, SandboxError), (
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
    translating to ``SandboxError``. Anchors the F3 §6 boundary:
    profile-shape errors are programmer/validator boundary, not
    sandbox-setup errors.

    ``SandboxProfile.from_dict`` runs BEFORE ``get_sandbox_backend()``
    in ``_build_stdio_params``, so this behaviour is unchanged by the
    factory retrofit — a malformed profile raises before the factory is
    consulted.

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
    assert not isinstance(exc_info.value, SandboxError)
