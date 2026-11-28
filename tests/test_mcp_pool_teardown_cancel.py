"""Sortie 22 DD2: what reaches the caller when a pool worker is torn down mid-connect.

The pool's ``_teardown_entry`` waits ``_WORKER_TEARDOWN_TIMEOUT_SECONDS`` and then
cancels a worker that is still connecting. These tests drive the REAL pool, the real
``MCPClient`` and ``OAuthASStub`` (no fake worker) and pin what the ``acquire``
caller and the agent turn observe. The reproduction found that a raw
``CancelledError`` never reaches either, so DD2's translation in ``_entry_worker``
was dropped; these tests pin that observed behaviour.

Two triggers:
  - the sign-in wait. Pool connections no longer wait (``interactive=False``), so
    the test forces an interactive pool provider to keep driving the in-band wait;
  - a slow server (no sign-in wait), the only trigger left in production.
"""

from __future__ import annotations

import asyncio

import pytest

from tests._mcp_pool_helpers import (
    CSID,
    SOURCE_ID,
    build_registry,
    build_tool,
    oauth_source,
    pool_db,
    reset_pool_state,
    tool_call_script,
)
from tests._mcp_signin_helpers import serve_asgi
from tests.conftest import FakeLLM
from tests.fixtures.oauth import OAuthASStub
from the_one.agent._context import current_chat_session_id
from the_one.agent.core import Agent
from the_one.db.models import MCPSource
from the_one.mcp import _pool
from the_one.mcp.errors import MCPAuthRequired
from the_one.mcp.oauth import _state


@pytest.fixture(autouse=True)
async def _clean():
    await reset_pool_state()
    yield
    await reset_pool_state()


@pytest.fixture
def interactive_pool(monkeypatch):
    """Force the pool's provider interactive, so the in-band sign-in wait still happens."""
    import the_one.mcp.oauth as oauth_pkg

    original = oauth_pkg.build_oauth_provider_for_source

    def wrapper(*args, **kwargs):
        kwargs["interactive"] = True
        return original(*args, **kwargs)

    monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", wrapper)


@pytest.fixture(autouse=True)
def _timeouts(monkeypatch):
    # The connect timeout strictly exceeds the teardown timeout, so the worker is
    # cancelled by the teardown, not by the connect timeout.
    monkeypatch.setattr("the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS", 20.0)
    monkeypatch.setattr(_pool, "_WORKER_TEARDOWN_TIMEOUT_SECONDS", 0.3)


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition never became true"
        await asyncio.sleep(0.02)


def _turn_runner(agent: Agent):
    async def run_turn():
        token = current_chat_session_id.set(CSID)
        try:
            return [m async for m in agent.step("go")]
        finally:
            current_chat_session_id.reset(token)

    return run_turn


async def test_acquire_caller_gets_auth_required_when_torn_down_in_the_signin_wait(
    tmp_path, monkeypatch, interactive_pool
) -> None:
    with OAuthASStub(refresh_status=400) as stub:
        source = oauth_source(stub.base_url)
        async with pool_db(tmp_path, monkeypatch, source):
            token = current_chat_session_id.set(CSID)
            try:
                task = asyncio.ensure_future(_pool.acquire("a", SOURCE_ID, source_override=source))
            finally:
                current_chat_session_id.reset(token)
            await _wait_until(lambda: bool(_state._pending))  # worker is in the sign-in wait
            await _pool._evict_all_for_source(SOURCE_ID)
            done, _ = await asyncio.wait({task}, timeout=5.0)
            assert done, "acquire never returned"
            assert not task.cancelled()  # never a raw CancelledError
            assert isinstance(task.exception(), MCPAuthRequired)


async def test_turn_pauses_when_the_worker_is_torn_down_in_the_signin_wait(
    tmp_path, monkeypatch, interactive_pool
) -> None:
    with OAuthASStub(refresh_status=400) as stub:
        source = oauth_source(stub.base_url)
        async with pool_db(tmp_path, monkeypatch, source):
            tool = build_tool(source)
            agent = Agent(FakeLLM(tool_call_script(tool)), build_registry(tool), "sys")
            task = asyncio.ensure_future(_turn_runner(agent)())
            await _wait_until(lambda: bool(_state._pending))
            await _pool._evict_all_for_source(SOURCE_ID)
            done, _ = await asyncio.wait({task}, timeout=5.0)
            assert done, "the turn never ended"
            assert not task.cancelled()
            assert task.exception() is None
            tool_msg = task.result()[-1]
            assert tool_msg.tool_result.metadata["is_auth_required"] is True
            assert agent._deferred_tool_calls is not None


async def _slow_initialize_app(scope, receive, send):
    """An ASGI app that never answers (a server stuck before its initialize reply)."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            else:
                await send({"type": "lifespan.shutdown.complete"})
                return
    await asyncio.sleep(60)


async def test_turn_gets_a_tool_error_when_a_slow_server_worker_is_torn_down(
    tmp_path, monkeypatch
) -> None:
    source = MCPSource(
        id=SOURCE_ID,
        name="pool-slow",
        type="streamable-http",
        config={"url": "http://localhost/mcp", "_cache": {"auth_posture": "no_auth"}},
        secrets={},
    )
    async with serve_asgi(monkeypatch, _slow_initialize_app):
        async with pool_db(tmp_path, monkeypatch, source):
            tool = build_tool(source)
            agent = Agent(FakeLLM(tool_call_script(tool)), build_registry(tool), "sys")
            task = asyncio.ensure_future(_turn_runner(agent)())
            await _wait_until(lambda: bool(_pool._pool))
            await asyncio.sleep(0.3)  # the worker is mid-connect
            await _pool._evict_all_for_source(SOURCE_ID)
            done, _ = await asyncio.wait({task}, timeout=5.0)
            assert done, "the turn never ended"
            assert not task.cancelled()  # never a raw CancelledError
            assert task.exception() is None
            messages = task.result()
            tool_msg = next(m for m in messages if m.tool_result is not None)
            assert not (tool_msg.tool_result.metadata or {}).get("is_auth_required")
            assert "unavailable" in tool_msg.tool_result.content
            assert "MCPConnectionError" in tool_msg.tool_result.content
