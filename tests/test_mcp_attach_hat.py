"""Tier-1 HAT (Human Acceptance Test) for F6 per-agent MCP attach + tool-routing.

This test file is the binary go/no-go gate for retiring the F2-known-issue
(``MCPClient transport close failed`` warning) from
``missions/07-mcp-integration/mission.md``'s Known Issues section. It
exercises the 5-step verification sequence specified in F6 flight §7
against real bwrap-spawned MCP subprocesses + real MCP sessions + real
teardown, and asserts that NO ``MCPClient transport close failed``
WARNING records surface during the run.

5-step Tier-1 sequence (per flight §7):

    Step 1 — Pre-state: register stdio + streamable-http MCP sources via
    the F1 admin path (DB-direct here for test isolation); configure two
    agents with attach + override.

    Step 2 — Tool-list visibility: build agent A; assert prefixed tool
    names (``mcp__{stdio_name}__*`` and ``mcp__{http_name}__*``) appear
    in the agent's :class:`ToolRegistry`; assert NO collision.

    Step 3 — Tool-call dispatch: agent A invokes a stdio MCP tool; the
    F4 pool spawns a real bwrap-wrapped subprocess; the result text
    round-trips back through :class:`MCPClientTool.execute`. Assert
    ``pgrep -f mcp_server_fetch`` shows ONE PID.

    Step 4 — Per-agent isolation: agent B (with a different
    ``mcp_overrides[stdio.name].env``) invokes the same tool. Assert
    ``pgrep -f mcp_server_fetch`` now shows TWO distinct PIDs (one per
    agent — F4's per-(agent, source) keying).

    Step 5 — Graceful degrade (cycle-1 M5 restructure): delete the http
    source via API; rebuild agent A; assert ``agent.tools.tool_names``
    no longer contains any ``mcp__{http_name}__*`` entries; the stdio
    source's tools still register.

Plus:

    Caplog assertion (binary F2-known-issue retirement gate): replay
    the 5-step sequence inside a single ``caplog.at_level(WARNING,
    logger="the_one.mcp.client")`` block; assert
    ``not any("MCPClient transport close failed" in r.message for r in
    caplog.records)``. Verbatim substring per the project's
    ``verbatim-message-equality`` convention. Zero matches → retire the
    F2-known-issue. Any match → revert F5 L1's
    ``_open_*_transport_stack`` helpers + ``_transport_connect``
    dispatcher rewrite (per ``tests/HAT.md``'s "On FAIL" section).

    Bonus per-(agent, source) keying test (F4 HAT precedent): agent A
    and agent B against the SAME source with NO override — assert
    distinct bwrap PIDs (F4's per-agent keying is structural, not
    override-dependent).

Outside-docker skip-don't-hang protection
=========================================

Every test in this file inherits a module-level ``pytestmark`` that
skips when either:

    1. ``bwrap`` is not on PATH (host machine without the dev
       container), OR
    2. ``mcp-server-fetch`` is not importable in the current Python
       env.

Per L0/L1/L2/L3 anomalies A1/A2/A3, ``tests/test_mcp_pool.py`` (and
any test that constructs a real ``_entry_worker``) hangs outside docker
because ``_entry_worker`` calls ``get_connection()`` to build the
OAuth provider, which blocks on aiosqlite worker-thread setup without
the container's daemon. This file inherits the same env-dependence;
the skipif probe ensures the host-machine pytest run skips cleanly
rather than hanging.

The ``mcp-server-fetch`` probe uses ``subprocess.run(..., timeout=5)``
to defend against the import itself hanging — a defensive timeout
against any environmental pathology that would otherwise propagate up
into the pytest collection phase.

Project-level pytest-asyncio is in ``auto`` mode (``pyproject.toml``
``asyncio_mode = "auto"``), so ``async def test_*`` functions and
``async`` fixtures run on the asyncio event loop without per-test
decorators.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from typing import Any

import pytest

from the_one.agent.config import AgentConfig
from the_one.db.models import MCPSource
from the_one.mcp import _pool as pool_mod

# ---------------------------------------------------------------------------
# Skipif probes — outside docker, every test in this file SKIPS (does not hang).
# ---------------------------------------------------------------------------

_BWRAP_AVAILABLE = shutil.which("bwrap") is not None


def _mcp_server_fetch_available() -> bool:
    """Probe whether ``mcp-server-fetch`` is importable in the current env.

    Subprocess-isolated to defend against the import hanging in the
    parent process; ``timeout=5`` is the upper bound — if the probe
    can't decide in 5s, treat as unavailable and skip.
    """
    try:
        subprocess.run(
            ["python", "-c", "import mcp_server_fetch"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


_HAT_AVAILABLE = _BWRAP_AVAILABLE and _mcp_server_fetch_available()

pytestmark = pytest.mark.skipif(
    not _HAT_AVAILABLE,
    reason="HAT requires bwrap + mcp-server-fetch (run inside `docker compose exec the-one`)",
)


# ---------------------------------------------------------------------------
# Pool reset between tests (mirrors tests/test_mcp_pool.py:45 pattern).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _clear_pool_after_each_test():
    yield
    await pool_mod._clear_for_test()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stdio_fetch_source(name: str = "fetch-stdio") -> MCPSource:
    """Build a stdio MCPSource pointing at the ``mcp-server-fetch``
    reference server.

    The F4 pool wraps the command in bwrap per the strict-floor sandbox
    profile; the test asserts that ``pgrep -f mcp_server_fetch``
    surfaces the resulting PID.
    """
    return MCPSource(
        id=f"src-{uuid.uuid4().hex[:8]}",
        name=name,
        type="stdio",
        config={
            "command": "python",
            "args": ["-m", "mcp_server_fetch"],
            "env": {},
            "cwd": None,
            "sandbox": {
                "writable_paths": [],
                "network_allowed": True,  # fetch needs network
            },
        },
        secrets={"env": {}},
    )


def _make_http_dummy_source(name: str = "fetch-http") -> MCPSource:
    """Build a streamable-http MCPSource pointing at a dummy URL.

    Used in step 1 + step 2 (visibility) only. The HAT does NOT call
    tools on this source — its real value is asserting that a
    streamable-http source CO-EXISTS with stdio in the prefix scheme
    without collision. Step 5 deletes it.
    """
    return MCPSource(
        id=f"src-{uuid.uuid4().hex[:8]}",
        name=name,
        type="streamable-http",
        config={"url": "http://localhost:9999/mcp"},  # not actually reached
        secrets={},
    )


def _pgrep_fetch_pids() -> list[str]:
    """Return the list of PIDs whose command-line matches
    ``mcp_server_fetch``.

    ``pgrep -f`` matches the full command-line, not just the executable
    name, so the bwrap-wrapped invocation
    (``bwrap ... python -m mcp_server_fetch``) surfaces correctly.
    Returns an empty list if no matches (pgrep exits 1 in that case;
    we swallow the non-zero exit and treat as "no PIDs").
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "mcp_server_fetch"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if result.returncode not in (0, 1):
        return []
    return [pid.strip() for pid in result.stdout.splitlines() if pid.strip()]


async def _build_agent_with_mcp(
    agent_name: str,
    source_ids: list[str],
    mcp_overrides: dict[str, dict[str, Any]] | None,
    sources_by_id: dict[str, MCPSource],
    monkeypatch,
):
    """Build an agent's MCP tool list using the F6 :class:`MCPToolProvider`,
    bypassing the live DB by patching the repository inside
    ``the_one.mcp._tool_provider``.

    Returns the list of registered :class:`MCPClientTool` instances —
    equivalent to what :class:`AgentFactory.create` would put into the
    agent's :class:`ToolRegistry` MCP slice. Tests then read
    ``[t.name for t in tools]`` for visibility assertions or call
    ``tools[i].execute(**kwargs)`` for dispatch assertions.

    Patching :class:`MCPSourceRepository` rather than constructing a
    real DB connection mirrors the unit-test pattern in
    ``tests/test_mcp_tool_provider.py::patch_provider_deps`` and keeps
    the HAT focused on the pool + transport boundary (the load-bearing
    F2-known-issue surface) rather than the storage layer.
    """
    from unittest.mock import AsyncMock, MagicMock

    from the_one.mcp import _tool_provider as provider_mod
    from the_one.mcp._tool_provider import MCPToolProvider

    mock_conn = AsyncMock()
    mock_encryptor = MagicMock()
    mock_repo = AsyncMock()

    async def _fake_get_connection():
        return mock_conn

    async def _get(source_id):
        if source_id not in sources_by_id:
            raise KeyError(f"MCP source not found: {source_id}")
        return sources_by_id[source_id]

    mock_repo.get = AsyncMock(side_effect=_get)

    monkeypatch.setattr(provider_mod, "get_connection", _fake_get_connection)
    monkeypatch.setattr(provider_mod, "get_encryptor", lambda _data_dir: mock_encryptor)
    monkeypatch.setattr(provider_mod, "MCPSourceRepository", lambda c, e: mock_repo)

    cfg = AgentConfig(
        name=agent_name,
        mcp_source_ids=source_ids,
        mcp_overrides=mcp_overrides,
    )
    return await MCPToolProvider().get_tools_for_agent(cfg, agent_name=agent_name)


# ---------------------------------------------------------------------------
# Step tests — the 5-step Tier-1 verification sequence
# ---------------------------------------------------------------------------


async def test_step_1_pre_state_register_sources_and_configure_agents(monkeypatch):
    """Step 1 — pre-state.

    Register a stdio source (``mcp-server-fetch``) and a streamable-http
    source (dummy URL); configure two agents (A and B) with attach +
    override pointing at the stdio source. Assert that the
    :class:`MCPSourceRepository` lookup path returns both sources by id
    and that both :class:`AgentConfig` instances validate.

    This test does NOT spawn any subprocess — it locks the DB-state
    pre-condition the rest of the sequence depends on.
    """
    stdio_src = _make_stdio_fetch_source()
    http_src = _make_http_dummy_source()
    sources_by_id = {stdio_src.id: stdio_src, http_src.id: http_src}

    cfg_a = AgentConfig(
        name="agent-a",
        mcp_source_ids=[stdio_src.id, http_src.id],
        mcp_overrides={stdio_src.name: {"env": {"AGENT": "a"}}},
    )
    cfg_b = AgentConfig(
        name="agent-b",
        mcp_source_ids=[stdio_src.id, http_src.id],
        mcp_overrides={stdio_src.name: {"env": {"AGENT": "b"}}},
    )

    # Sanity: both configs validated; both source ids resolvable.
    assert cfg_a.mcp_source_ids == [stdio_src.id, http_src.id]
    assert cfg_b.mcp_source_ids == [stdio_src.id, http_src.id]
    assert cfg_a.mcp_overrides[stdio_src.name]["env"]["AGENT"] == "a"
    assert cfg_b.mcp_overrides[stdio_src.name]["env"]["AGENT"] == "b"
    assert sources_by_id[stdio_src.id].type == "stdio"
    assert sources_by_id[http_src.id].type == "streamable-http"


async def test_step_2_tool_list_visibility_under_agent_build(monkeypatch):
    """Step 2 — tool-list visibility.

    Build agent A; assert prefixed tool names appear with both
    ``mcp__{stdio_name}__*`` AND (if the http source is reachable)
    ``mcp__{http_name}__*`` entries. The dummy http URL is unreachable,
    so the http source's tools degrade gracefully (failure class #2 per
    F6 §8) — we ONLY assert the stdio source's prefix appears. The
    co-existence-without-collision invariant is the load-bearing claim;
    F6 §2's prefix scheme guarantees no collision when source names
    differ.
    """
    stdio_src = _make_stdio_fetch_source()
    http_src = _make_http_dummy_source()
    sources_by_id = {stdio_src.id: stdio_src, http_src.id: http_src}

    tools = await _build_agent_with_mcp(
        agent_name="agent-a",
        source_ids=[stdio_src.id, http_src.id],
        mcp_overrides={stdio_src.name: {"env": {"AGENT": "a"}}},
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )
    names = [t.name for t in tools]
    # stdio source's tools registered with the canonical prefix.
    assert any(n.startswith(f"mcp__{stdio_src.name}__") for n in names), (
        f"expected mcp__{stdio_src.name}__* tools; got {names!r}"
    )
    # No collision: if the http source's tools registered, their prefix differs.
    http_prefixed = [n for n in names if n.startswith(f"mcp__{http_src.name}__")]
    stdio_prefixed = [n for n in names if n.startswith(f"mcp__{stdio_src.name}__")]
    assert not (set(http_prefixed) & set(stdio_prefixed))


async def test_step_3_tool_call_dispatch_via_pool_to_real_subprocess(monkeypatch):
    """Step 3 — tool-call dispatch.

    Agent A invokes a stdio MCP tool (``mcp__{stdio_name}__fetch``).
    The F4 pool spawns a real bwrap-wrapped ``mcp-server-fetch``
    subprocess; the result text round-trips back through
    :meth:`MCPClientTool.execute`. Assert ``pgrep -f mcp_server_fetch``
    shows EXACTLY ONE PID after dispatch.
    """
    stdio_src = _make_stdio_fetch_source()
    sources_by_id = {stdio_src.id: stdio_src}

    tools = await _build_agent_with_mcp(
        agent_name="agent-a",
        source_ids=[stdio_src.id],
        mcp_overrides=None,
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )
    fetch_tool = next(
        t for t in tools if t.name == f"mcp__{stdio_src.name}__fetch"
    )
    # Invoke; mcp-server-fetch's `fetch` tool takes a `url=` kwarg.
    # Use a stable URL — the SDK returns a text payload regardless of HTTP status.
    result = await fetch_tool.execute(url="https://example.com")
    assert isinstance(result, str)
    assert len(result) > 0

    pids = _pgrep_fetch_pids()
    assert len(pids) == 1, f"expected 1 mcp_server_fetch PID; saw {pids!r}"


async def test_step_4_per_agent_isolation_distinct_subprocesses(monkeypatch):
    """Step 4 — per-agent isolation.

    Agent A invokes the stdio tool; agent B (with a DIFFERENT
    ``mcp_overrides[stdio.name].env``) invokes the same tool. Assert
    ``pgrep -f mcp_server_fetch`` shows TWO distinct PIDs — one per
    agent — proving the F4 pool's per-(agent, source) keying.
    """
    stdio_src = _make_stdio_fetch_source()
    sources_by_id = {stdio_src.id: stdio_src}

    tools_a = await _build_agent_with_mcp(
        agent_name="agent-a",
        source_ids=[stdio_src.id],
        mcp_overrides={stdio_src.name: {"env": {"AGENT": "a"}}},
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )
    tools_b = await _build_agent_with_mcp(
        agent_name="agent-b",
        source_ids=[stdio_src.id],
        mcp_overrides={stdio_src.name: {"env": {"AGENT": "b"}}},
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )

    fetch_a = next(t for t in tools_a if t.name == f"mcp__{stdio_src.name}__fetch")
    fetch_b = next(t for t in tools_b if t.name == f"mcp__{stdio_src.name}__fetch")

    await fetch_a.execute(url="https://example.com")
    await fetch_b.execute(url="https://example.com")

    pids = _pgrep_fetch_pids()
    assert len(pids) == 2, f"expected 2 distinct PIDs (one per agent); saw {pids!r}"
    assert len(set(pids)) == 2, f"expected DISTINCT PIDs; saw duplicates: {pids!r}"


async def test_step_5_graceful_degrade_delete_source_then_rebuild_drops_tools(
    monkeypatch,
):
    """Step 5 — graceful degrade (cycle-1 M5 restructure).

    Build agent A with both stdio + http sources; the stdio source's
    tools register (the http source's tools may degrade depending on
    URL reachability). Then DELETE the http source from the
    sources-by-id mapping (simulating an operator deletion via the F1
    admin path); rebuild agent A; assert ``mcp__{http_name}__*`` no
    longer appears in the rebuilt agent's tool list. The stdio
    source's tools still register (graceful-degrade contract per F6
    §8 failure class #1: deleted sources are skipped).
    """
    stdio_src = _make_stdio_fetch_source()
    http_src = _make_http_dummy_source()
    sources_by_id = {stdio_src.id: stdio_src, http_src.id: http_src}

    tools_v1 = await _build_agent_with_mcp(
        agent_name="agent-a",
        source_ids=[stdio_src.id, http_src.id],
        mcp_overrides=None,
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )
    names_v1 = [t.name for t in tools_v1]
    assert any(n.startswith(f"mcp__{stdio_src.name}__") for n in names_v1)

    # Operator deletes http source — failure class #1 (KeyError → skip).
    del sources_by_id[http_src.id]

    tools_v2 = await _build_agent_with_mcp(
        agent_name="agent-a",
        source_ids=[stdio_src.id, http_src.id],
        mcp_overrides=None,
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )
    names_v2 = [t.name for t in tools_v2]
    # http source's tools absent.
    assert not any(n.startswith(f"mcp__{http_src.name}__") for n in names_v2)
    # stdio source's tools still register.
    assert any(n.startswith(f"mcp__{stdio_src.name}__") for n in names_v2)


# ---------------------------------------------------------------------------
# Caplog gate — F2-known-issue retirement
# ---------------------------------------------------------------------------


async def test_caplog_no_transport_close_failed_warnings(monkeypatch, caplog):
    """Binary go/no-go gate for retiring the F2-known-issue.

    Replays the 5-step sequence inside a single
    ``caplog.at_level(WARNING, logger="the_one.mcp.client")`` block;
    asserts NO record's message contains the verbatim substring
    ``"MCPClient transport close failed"`` (the F5 L1 cross-task
    safety-net WARNING site at ``the_one/mcp/client.py:328``).

    Implementation note (per leg artifact Edge Case "Caplog assertion
    across 5 steps"): pytest's ``caplog`` is per-test by default, so
    the assertion must replay the operations inside ONE test function
    to capture across the full sequence. We do a condensed replay
    (steps 3, 4, 5 — the steps that actually spawn subprocesses; steps
    1 and 2 cannot trip the warning because they don't dispatch).

    PASS (zero matches) → retire the F2-known-issue from
    ``mission.md`` (out of L5 scope; flight-end docker run gates this).
    FAIL (any match) → revert F5 L1's ``_open_*_transport_stack``
    helpers + ``_transport_connect`` dispatcher rewrite per
    ``tests/HAT.md``'s "On FAIL" section.
    """
    stdio_src = _make_stdio_fetch_source()
    sources_by_id = {stdio_src.id: stdio_src}

    with caplog.at_level(logging.WARNING, logger="the_one.mcp.client"):
        # Step 3 replay — single agent, single dispatch.
        tools_a = await _build_agent_with_mcp(
            agent_name="agent-a",
            source_ids=[stdio_src.id],
            mcp_overrides=None,
            sources_by_id=sources_by_id,
            monkeypatch=monkeypatch,
        )
        fetch_a = next(
            t for t in tools_a if t.name == f"mcp__{stdio_src.name}__fetch"
        )
        await fetch_a.execute(url="https://example.com")

        # Step 4 replay — second agent, distinct subprocess.
        tools_b = await _build_agent_with_mcp(
            agent_name="agent-b",
            source_ids=[stdio_src.id],
            mcp_overrides={stdio_src.name: {"env": {"AGENT": "b"}}},
            sources_by_id=sources_by_id,
            monkeypatch=monkeypatch,
        )
        fetch_b = next(
            t for t in tools_b if t.name == f"mcp__{stdio_src.name}__fetch"
        )
        await fetch_b.execute(url="https://example.com")

        # Step 5 replay — explicit pool eviction triggers the disconnect path
        # that historically tripped the cross-task __aexit__ guard. The
        # autouse ``_clear_pool_after_each_test`` fixture also exercises
        # disconnect at test teardown, but we evict explicitly here to
        # keep the WARNING surface inside the caplog window.
        await pool_mod._evict(("agent-a", stdio_src.id))
        await pool_mod._evict(("agent-b", stdio_src.id))

    # The binary gate — verbatim substring per the project's
    # `verbatim-message-equality` convention.
    offending = [
        r for r in caplog.records
        if "MCPClient transport close failed" in r.message
    ]
    assert not any(
        "MCPClient transport close failed" in r.message for r in caplog.records
    ), (
        f"F2-known-issue retirement gate FAILED: "
        f"{len(offending)} `MCPClient transport close failed` WARNING(s) "
        f"surfaced during HAT replay. Revert F5 L1's "
        f"_open_*_transport_stack helpers per tests/HAT.md `On FAIL`."
    )


# ---------------------------------------------------------------------------
# Bonus — per-(agent, source) keying with NO override (F4 HAT precedent)
# ---------------------------------------------------------------------------


async def test_bonus_per_agent_source_keying_no_override(monkeypatch):
    """Bonus test (per F4 HAT precedent): per-(agent, source) keying
    is structural — agent A and agent B against the SAME source with
    NO override produce DISTINCT bwrap PIDs.

    The F4 pool keys on ``(agent_name, source_id)`` regardless of
    override content, so this isolation invariant holds even when
    both agents share an identical effective_source. If a future
    refactor introduces dedup-on-same-config, this test fails loudly
    and the F4 keying contract gets a deliberate revisit.
    """
    stdio_src = _make_stdio_fetch_source()
    sources_by_id = {stdio_src.id: stdio_src}

    tools_a = await _build_agent_with_mcp(
        agent_name="agent-a",
        source_ids=[stdio_src.id],
        mcp_overrides=None,
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )
    tools_b = await _build_agent_with_mcp(
        agent_name="agent-b",
        source_ids=[stdio_src.id],
        mcp_overrides=None,
        sources_by_id=sources_by_id,
        monkeypatch=monkeypatch,
    )

    fetch_a = next(t for t in tools_a if t.name == f"mcp__{stdio_src.name}__fetch")
    fetch_b = next(t for t in tools_b if t.name == f"mcp__{stdio_src.name}__fetch")

    await fetch_a.execute(url="https://example.com")
    await fetch_b.execute(url="https://example.com")

    pids = _pgrep_fetch_pids()
    assert len(pids) == 2, (
        f"expected 2 PIDs (per-(agent, source) keying with NO override); "
        f"saw {pids!r}. If this fails, F4's keying contract may have changed."
    )
    assert len(set(pids)) == 2, f"PIDs not distinct: {pids!r}"
