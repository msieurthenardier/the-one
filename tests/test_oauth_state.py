"""Pending-flow registry tests for the_one.mcp.oauth._state."""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp.client.auth.exceptions import OAuthFlowError

from the_one.mcp.oauth import _state


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    _state._pending.clear()
    yield
    _state._pending.clear()


async def test_pending_registry_full_contract() -> None:
    """A3 — happy path + edges:

      - register returns a fresh future and records the entry;
      - peek does NOT pop and a second peek returns the same entry;
      - register on the same state raises ``RuntimeError``;
      - resolve returns True the first time and False after popping;
      - resolve on unknown state returns False;
      - fail sets the future's exception and returns True; unknown
        state returns False;
      - distinct register calls return independent futures.
    """
    fut = _state.register(
        "S1", source_id="src1", tool_call_id="tc1", chat_session_id="cs1"
    )
    assert isinstance(fut, asyncio.Future) and not fut.done()

    entry = _state.peek("S1")
    assert entry is not None
    assert entry.source_id == "src1"
    assert entry.tool_call_id == "tc1"
    assert entry.chat_session_id == "cs1"
    # peek does not pop
    assert _state.peek("S1") is entry

    with pytest.raises(RuntimeError):
        _state.register("S1", source_id="x", tool_call_id=None, chat_session_id="c")

    assert _state.resolve("S1", "code-123", "S1") is True
    assert await fut == ("code-123", "S1")
    # second resolve returns False (already popped)
    assert _state.resolve("S1", "x", "S1") is False
    # unknown state
    assert _state.resolve("MISSING", "x", "MISSING") is False

    # fail path on a fresh state
    fut2 = _state.register(
        "S2", source_id="s", tool_call_id=None, chat_session_id="c"
    )
    assert _state.fail("S2", OAuthFlowError("operator denied")) is True
    with pytest.raises(OAuthFlowError, match="operator denied"):
        await fut2
    assert _state.fail("MISSING", OAuthFlowError("x")) is False

    # distinct futures (concurrent flows don't alias)
    fut_a = _state.register(
        "A", source_id="s", tool_call_id=None, chat_session_id="c"
    )
    fut_b = _state.register(
        "B", source_id="s", tool_call_id=None, chat_session_id="c"
    )
    assert fut_a is not fut_b
    _state.resolve("A", "code-a", "A")
    assert await fut_a == ("code-a", "A")
    assert not fut_b.done()


async def test_sweep_and_lifespan_lifecycle() -> None:
    """A3 + A4 — sweep removes expired entries (resolving futures with
    ``OAuthFlowError("OAuth flow timed out (10-minute TTL)")``) and is
    idempotent; ``start_periodic_sweep`` spawns a task and is
    idempotent on second call; ``stop_periodic_sweep`` cancels and
    clears state, and is a no-op on a second call.
    """
    # Sweep behavior
    fut = _state.register(
        "S3", source_id="s", tool_call_id=None, chat_session_id="c"
    )
    _state._pending["S3"].created_at = time.time() - _state._TTL_SECONDS - 1

    removed = await _state._sweep_expired()
    assert removed == 1
    assert _state.peek("S3") is None
    with pytest.raises(OAuthFlowError, match="timed out"):
        await fut
    assert await _state._sweep_expired() == 0  # idempotent

    # Lifespan hooks
    task1 = _state.start_periodic_sweep()
    assert isinstance(task1, asyncio.Task)
    assert not task1.done()
    assert task1 in asyncio.all_tasks()

    task2 = _state.start_periodic_sweep()
    assert task2 is task1  # idempotent

    await _state.stop_periodic_sweep()
    assert task1.done()
    assert _state._sweep_task is None
    await _state.stop_periodic_sweep()  # no-op
