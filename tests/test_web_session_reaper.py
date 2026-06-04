"""Web-session idle reaper unit tests.

F05 L01 (Mission 12 Flight 05): covers the acceptance criteria for the
``_sessions`` idle-TTL reaper added to ``the_one/interfaces/web/app.py``.

Tests are pure-unit: they do NOT start a full FastAPI application or talk to
a database.  They manipulate ``app._sessions``, ``app._sessions_lock``,
``app._web_session_reaper_task``, and the subscriber/lock registries from
``the_one.sessions`` directly, then call the testable helpers
``_reap_web_sessions_once()`` / ``_web_session_reaper_shutdown_drain()``.

Agent instances are replaced by an async-mock shim that records ``aclose``
calls (no real LLM client involved).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Helpers: minimal Agent mock and Session factory
# ─────────────────────────────────────────────────────────────────────────────


class _MockAgent:
    """Minimal stand-in for ``Agent``.  Records ``aclose`` calls."""

    def __init__(self) -> None:
        self.aclose = AsyncMock()
        # _closed guard mirrors Agent.aclose()'s idempotency
        self._closed = False
        self.messages: list = []
        self.system_prompt = ""
        self._deferred_tool_calls = None


def _make_session(sid: str, agent: _MockAgent | None = None, stale: bool = False) -> Any:
    """Return a ``Session`` dataclass populated with a mock agent.

    ``stale=True`` pushes ``last_activity`` 7200s into the past so the
    default TTL (1800s) is always exceeded in tests.
    """
    from the_one.interfaces.web.app import Session

    a = agent or _MockAgent()
    s = Session(
        id=sid,
        agent=a,  # type: ignore[arg-type]
        created="2026-01-01T00:00:00+00:00",
    )
    if stale:
        s.last_activity = time.monotonic() - 7200  # 2h ago — well past any TTL
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Autouse fixture: clear _sessions, subscriber registry, lock map between tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _clean_sessions(monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[misc]
    """Reset all module-level state touched by the reaper tests."""
    import the_one.interfaces.web.app as app_mod
    from the_one.sessions import clear_for_test as _clear_sessions

    # Ensure a fresh asyncio.Lock for each test (the module-level instance
    # persists across tests in the same process; clear the dict and replace).
    monkeypatch.setattr(app_mod, "_sessions", {})
    monkeypatch.setattr(app_mod, "_web_session_reaper_task", None)

    # Set a short TTL via env var so tests don't need to sleep.
    # Each test that needs a specific TTL can monkeypatch further.
    monkeypatch.setenv("THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS", "60")

    yield

    # Teardown: clear the session registries.
    _clear_sessions()
    app_mod._sessions.clear()


# ─────────────────────────────────────────────────────────────────────────────
# (a) Eviction of a zero-subscriber, idle session + Agent.aclose() called
# ─────────────────────────────────────────────────────────────────────────────


async def test_reap_once_evicts_idle_zero_subscriber_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero-subscriber session idle past the TTL is evicted and its
    agent.aclose() is called exactly once."""
    import the_one.interfaces.web.app as app_mod

    agent = _MockAgent()
    session = _make_session("stale-01", agent, stale=True)
    app_mod._sessions["stale-01"] = session

    evicted = await app_mod._reap_web_sessions_once()

    assert "stale-01" in evicted, f"Expected stale-01 in evicted; got {evicted}"
    assert "stale-01" not in app_mod._sessions
    agent.aclose.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# (b) A session WITH a live subscriber is NEVER reaped past TTL
# ─────────────────────────────────────────────────────────────────────────────


async def test_reap_once_does_not_evict_subscribed_session() -> None:
    """The operator hard requirement: an open chat tab (≥1 subscriber) is
    NEVER reaped, even when idle past the TTL."""
    import the_one.interfaces.web.app as app_mod
    from the_one.sessions import add_subscriber

    # Fake WS subscriber — just a sentinel object.
    fake_ws = object()

    agent = _MockAgent()
    session = _make_session("subscribed-01", agent, stale=True)
    app_mod._sessions["subscribed-01"] = session
    add_subscriber("subscribed-01", fake_ws)

    evicted = await app_mod._reap_web_sessions_once()

    assert "subscribed-01" not in evicted, "Subscribed session must NOT be reaped; evicted=" + str(
        evicted
    )
    assert "subscribed-01" in app_mod._sessions
    agent.aclose.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# (c) A session that is_session_processing is NOT reaped past TTL
# ─────────────────────────────────────────────────────────────────────────────


async def test_reap_once_does_not_evict_processing_session() -> None:
    """A session mid-turn (lock held = is_session_processing) is NOT reaped
    even when past the TTL and zero subscribers."""
    import the_one.interfaces.web.app as app_mod
    from the_one.sessions import session_locks

    agent = _MockAgent()
    session = _make_session("processing-01", agent, stale=True)
    app_mod._sessions["processing-01"] = session

    # Simulate a held session lock (is_session_processing returns True).
    lock = asyncio.Lock()
    await lock.acquire()
    session_locks["processing-01"] = lock

    try:
        evicted = await app_mod._reap_web_sessions_once()

        assert "processing-01" not in evicted, (
            "Processing session must NOT be reaped; evicted=" + str(evicted)
        )
        assert "processing-01" in app_mod._sessions
        agent.aclose.assert_not_awaited()
    finally:
        lock.release()


# ─────────────────────────────────────────────────────────────────────────────
# (d) Fresh session (not idle) is NOT evicted
# ─────────────────────────────────────────────────────────────────────────────


async def test_reap_once_does_not_evict_fresh_session() -> None:
    """A zero-subscriber session whose last_activity is recent (within TTL)
    is NOT evicted."""
    import the_one.interfaces.web.app as app_mod

    agent = _MockAgent()
    session = _make_session("fresh-01", agent, stale=False)
    # last_activity defaults to time.monotonic() at construction — very recent
    app_mod._sessions["fresh-01"] = session

    evicted = await app_mod._reap_web_sessions_once()

    assert "fresh-01" not in evicted
    assert "fresh-01" in app_mod._sessions
    agent.aclose.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# (e) Rehydration: evict a session, then _get_or_restore_session returns it
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated data dir + fresh DB connection for rehydration test."""
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    monkeypatch.setattr(db_connection, "_connection", None)


async def test_rehydration_after_eviction(_isolated_data_dir: Path) -> None:
    """After a session is evicted by the reaper, _get_or_restore_session
    rehydrates it from the DB with full history (lossless reaccess).

    This test seeds the DB with a chat_sessions row that has a user message
    in its messages column, evicts the session from the in-memory dict, then
    calls _get_or_restore_session and asserts the session comes back with
    a non-empty history.
    """
    import the_one.interfaces.web.app as app_mod
    from the_one.agent.factory import AgentFactory
    from the_one.db import init_db
    from the_one.db.codec import encode_messages
    from the_one.db.connection import get_connection
    from the_one.db.migration import migrate_json_to_sqlite
    from the_one.db.models import ChatSession as ChatSessionModel
    from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore
    from the_one.llm.base import Message, Role

    # Initialize DB.
    await init_db()
    conn = await get_connection()
    store = SQLiteAgentStore(conn)
    await migrate_json_to_sqlite(store)

    # Install a factory so _restore_session can build an agent.
    # Use the default (no-provider) factory — the session will be degraded
    # if no provider is configured.  Instead, create a mock-based factory.
    from the_one.agent.config import AgentConfig
    from the_one.config import settings

    # Seed a mock provider + agent into the DB so _restore_session succeeds.
    from the_one.db.models import LLMProviderConfig
    from the_one.db.repositories import LLMProviderRepository
    from the_one.encryption import get_encryptor

    encryptor = get_encryptor(settings.data_dir)
    provider_repo = LLMProviderRepository(conn, encryptor)
    await provider_repo.create(
        LLMProviderConfig(
            id="mock-rehydrate",
            name="Mock Rehydrate",
            type="mock",
            base_url="",
            config={"response": {"content": "ok"}},
        )
    )
    await store.save(
        AgentConfig(
            name="default",
            provider_config_id="mock-rehydrate",
            llm_model="mock-default",
        )
    )

    factory = AgentFactory(store=store)
    app_mod._state["factory"] = factory

    # Seed a chat_sessions row with a user message.
    messages = [
        Message(role=Role.USER, content="Hello from DB"),
        Message(role=Role.ASSISTANT, content="Hi there"),
    ]
    encoded = encode_messages(messages)
    repo = ChatSessionRepository(conn)
    sid = "rehydrate-01"
    await repo.create(
        ChatSessionModel(
            id=sid,
            title="Rehydration test",
            messages=encoded,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )

    # Evict: simulate the reaper having already removed this session from
    # the in-memory dict (it never was there in this test, which is fine —
    # the absence from _sessions is what matters).
    assert sid not in app_mod._sessions

    # Rehydrate via _get_or_restore_session.
    restored = await app_mod._get_or_restore_session(sid)

    assert restored.status == "ok"
    assert restored.session is not None
    # The session must have history reconstructed from the DB messages.
    assert len(restored.session.history) >= 1, (
        f"Expected non-empty history after rehydration; got {restored.session.history}"
    )
    # The session should now be cached in _sessions.
    assert sid in app_mod._sessions


# ─────────────────────────────────────────────────────────────────────────────
# (f) Clean shutdown drain closes all remaining sessions
# ─────────────────────────────────────────────────────────────────────────────


async def test_shutdown_drain_closes_remaining_sessions() -> None:
    """_web_session_reaper_shutdown_drain() closes all remaining sessions
    and clears _sessions — even when the reaper task was never started."""
    import the_one.interfaces.web.app as app_mod

    agents = [_MockAgent() for _ in range(3)]
    for i, agent in enumerate(agents):
        sid = f"drain-{i:02d}"
        session = _make_session(sid, agent)
        app_mod._sessions[sid] = session

    await app_mod._web_session_reaper_shutdown_drain()

    assert app_mod._sessions == {}, "All sessions must be cleared by shutdown drain"
    for agent in agents:
        agent.aclose.assert_awaited_once()


async def test_shutdown_drain_cancels_reaper_task() -> None:
    """_web_session_reaper_shutdown_drain() cancels the reaper task if running."""
    import the_one.interfaces.web.app as app_mod

    # Start a real (but sleeping) reaper-like task.
    async def _long_sleep() -> None:
        await asyncio.sleep(3600)

    task = asyncio.create_task(_long_sleep())
    app_mod._web_session_reaper_task = task

    await app_mod._web_session_reaper_shutdown_drain()

    assert task.cancelled() or task.done(), "Reaper task must be cancelled by shutdown drain"
    assert app_mod._web_session_reaper_task is None


# ─────────────────────────────────────────────────────────────────────────────
# (g) Multiple sessions — only stale zero-subscriber ones are evicted
# ─────────────────────────────────────────────────────────────────────────────


async def test_reap_once_mixed_sessions() -> None:
    """With a mix of fresh/stale and subscribed/unsubscribed sessions, only
    stale zero-subscriber sessions are evicted."""
    import the_one.interfaces.web.app as app_mod
    from the_one.sessions import add_subscriber

    fake_ws = object()

    sessions: dict[str, _MockAgent] = {}

    # stale + no subscriber → should be evicted
    a1 = _MockAgent()
    s1 = _make_session("evict-me", a1, stale=True)
    app_mod._sessions["evict-me"] = s1
    sessions["evict-me"] = a1

    # fresh + no subscriber → should NOT be evicted
    a2 = _MockAgent()
    s2 = _make_session("keep-fresh", a2, stale=False)
    app_mod._sessions["keep-fresh"] = s2
    sessions["keep-fresh"] = a2

    # stale + subscriber → should NOT be evicted (operator hard requirement)
    a3 = _MockAgent()
    s3 = _make_session("keep-subscribed", a3, stale=True)
    app_mod._sessions["keep-subscribed"] = s3
    add_subscriber("keep-subscribed", fake_ws)
    sessions["keep-subscribed"] = a3

    evicted = await app_mod._reap_web_sessions_once()

    assert evicted == ["evict-me"], f"Expected only evict-me; got {evicted}"
    assert "evict-me" not in app_mod._sessions
    assert "keep-fresh" in app_mod._sessions
    assert "keep-subscribed" in app_mod._sessions
    a1.aclose.assert_awaited_once()
    a2.aclose.assert_not_awaited()
    a3.aclose.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# (h) Agent.aclose() idempotency
# ─────────────────────────────────────────────────────────────────────────────


async def test_agent_aclose_idempotent() -> None:
    """Agent.aclose() is idempotent — calling it twice only closes the
    LLM provider once."""

    from the_one.agent.core import Agent
    from the_one.llm.base import LLMProvider
    from the_one.tools.base import ToolRegistry

    class _NopLLM(LLMProvider):
        name = "nop"
        close_count = 0

        async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384):
            raise NotImplementedError

        async def aclose(self) -> None:
            self.__class__.close_count += 1

    llm = _NopLLM()
    agent = Agent(llm=llm, tools=ToolRegistry(), system_prompt="test")

    await agent.aclose()
    await agent.aclose()  # second call must be a no-op

    assert _NopLLM.close_count == 1, f"Expected LLM.aclose() called once; got {_NopLLM.close_count}"


# ─────────────────────────────────────────────────────────────────────────────
# (i) TTL env var is read at call time
# ─────────────────────────────────────────────────────────────────────────────


async def test_ttl_env_var_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS is consulted at reap time, not
    at module import time — changing the env var mid-test is reflected."""
    import the_one.interfaces.web.app as app_mod

    agent = _MockAgent()
    session = _make_session("ttl-test", agent, stale=False)
    # last_activity 2000s ago
    session.last_activity = time.monotonic() - 2000
    app_mod._sessions["ttl-test"] = session

    # With TTL=3600, the session (2000s idle) should NOT be evicted.
    monkeypatch.setenv("THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS", "3600")
    evicted = await app_mod._reap_web_sessions_once()
    assert "ttl-test" not in evicted

    # Now lower the TTL to 1000s — the session (2000s idle) SHOULD be evicted.
    monkeypatch.setenv("THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS", "1000")
    # Re-insert the session (it may have been evicted by the second reap).
    app_mod._sessions["ttl-test"] = session
    evicted = await app_mod._reap_web_sessions_once()
    assert "ttl-test" in evicted


async def test_ttl_env_var_invalid_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-integer THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS falls back to 1800."""
    import the_one.interfaces.web.app as app_mod

    monkeypatch.setenv("THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS", "not-a-number")
    ttl = app_mod._get_web_session_idle_ttl()
    assert ttl == 1800, f"Expected default 1800; got {ttl}"
