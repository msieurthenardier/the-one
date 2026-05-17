"""Tests for ``the_one.connectors._session`` — M10 F03 L03.

Covers:
- ``_resolve_continuation_seconds`` resolution order (override → env var
  → default), env-var read-at-call-time, non-int fallback.
- ``resolve_session`` paths: first-contact creation, within-window reuse,
  outside-window supersession (old row preserved), per-thread distinct
  sessions, DM-shaped envelopes (thread_id=None), ``display_channel``
  fallbacks (hook missing, hook raises), plugin authority over key shape,
  and ``peer_id`` stored-but-not-in-lookup.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from the_one.agent.config import AgentConfig
from the_one.connectors._session import (
    _DEFAULT_CONTINUATION_SECONDS,
    _resolve_continuation_seconds,
    resolve_session,
)
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import InboundEnvelope, SessionKey
from the_one.db.models import ChatSession, ConnectorAccount
from the_one.db.repositories import (
    ChatSessionRepository,
    SQLiteAgentStore,
)
from the_one.db.schema import ensure_schema

# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
async def conn(tmp_path):
    """Fresh DB connection with schema applied. Mirrors
    ``tests/test_db_repositories.py``'s ``conn`` fixture."""
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


@pytest.fixture
def chat_repo(conn):
    return ChatSessionRepository(conn)


@pytest.fixture
def agent_store(conn):
    return SQLiteAgentStore(conn)


@pytest.fixture
async def seeded_agent(agent_store):
    """An agent row exists so chat_sessions FK references resolve.

    chat_sessions has no FK CASCADE on ``agent_name`` since schema v5
    (see ``test_agent_delete_does_not_cascade_to_sessions``), but the
    other table-level constraints want a real agent row when present.
    """
    await agent_store.save(AgentConfig(name="agent1"))
    return "agent1"


@pytest.fixture
def stub_plugin():
    return StubPlugin()


def _envelope(
    *,
    channel_id: str = "ch-1",
    thread_id: str | None = None,
    peer_id: str = "peer-1",
    account_id: str = "acc-1",
    platform: str = "stub",
) -> InboundEnvelope:
    return InboundEnvelope(
        platform=platform,
        account_id=account_id,
        channel_id=channel_id,
        thread_id=thread_id,
        peer_id=peer_id,
        peer_name="Alice",
        text="hello",
        raw={},
    )


def _account(
    *,
    session_continuation_seconds: int | None = None,
    account_id: str = "acc-1",
) -> ConnectorAccount:
    return ConnectorAccount(
        id=account_id,
        name="Test Account",
        type="stub",
        session_continuation_seconds=session_continuation_seconds,
    )


# ─── _resolve_continuation_seconds ───────────────────────────────────────


def test_resolve_continuation_seconds_override_beats_env_and_default(monkeypatch) -> None:
    """Explicit override wins over both env-var and default."""
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "120")
    assert _resolve_continuation_seconds(override=60) == 60


def test_resolve_continuation_seconds_env_beats_default(monkeypatch) -> None:
    """Env var beats default when no override."""
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "120")
    assert _resolve_continuation_seconds() == 120


def test_resolve_continuation_seconds_default_when_no_env(monkeypatch) -> None:
    """No override, no env var → default 86400."""
    monkeypatch.delenv("THE_ONE_SESSION_CONTINUATION_SECONDS", raising=False)
    assert _resolve_continuation_seconds() == _DEFAULT_CONTINUATION_SECONDS == 86400


def test_resolve_continuation_seconds_non_int_env_falls_back_to_default(
    monkeypatch,
) -> None:
    """Non-int env var → default with a warning (no raise)."""
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "not-a-number")
    assert _resolve_continuation_seconds() == _DEFAULT_CONTINUATION_SECONDS


def test_resolve_continuation_seconds_env_read_at_call_time(monkeypatch) -> None:
    """Live-read invariant: env var changes between calls are observed.

    A naive cache-at-import implementation would fail this test — the
    first call returns the default, then the second call (after setenv)
    returns the override.
    """
    monkeypatch.delenv("THE_ONE_SESSION_CONTINUATION_SECONDS", raising=False)
    assert _resolve_continuation_seconds() == 86400
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "3600")
    assert _resolve_continuation_seconds() == 3600


# ─── resolve_session — happy paths ───────────────────────────────────────


async def test_resolve_session_creates_new_row_on_first_contact(
    chat_repo, seeded_agent, stub_plugin
) -> None:
    """No existing row → create a fresh chat_session with all external-key
    columns populated, ``agent_name`` set, ``last_inbound_at`` ≈ now, title
    derived via ``plugin.display_channel``."""
    envelope = _envelope(channel_id="ch-1", thread_id=None, peer_id="peer-1")
    account = _account()

    before = datetime.now(timezone.utc)
    session = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )
    after = datetime.now(timezone.utc)

    assert session.agent_name == "agent1"
    assert session.platform == "stub"
    assert session.connector_account_id == "acc-1"
    assert session.channel_id == "ch-1"
    assert session.thread_id is None
    assert session.peer_id == "peer-1"
    assert session.session_metadata is None
    assert session.messages == "[]"
    # Title from StubPlugin.display_channel: f"stub:{envelope.channel_id}".
    assert session.title == "stub:ch-1"
    # uuid4().hex is 32 hex chars — NOT truncated to 12.
    assert len(session.id) == 32
    assert session.last_inbound_at is not None
    parsed = datetime.fromisoformat(session.last_inbound_at)
    assert before <= parsed <= after

    # Row was persisted (round-trips via repo.get).
    loaded = await chat_repo.get(session.id)
    assert loaded.id == session.id
    assert loaded.title == "stub:ch-1"


async def test_resolve_session_reuses_row_within_window(
    chat_repo, seeded_agent, stub_plugin
) -> None:
    """Existing row inside the continuation window → returned untouched;
    no new row is created."""
    envelope = _envelope()
    account = _account()

    first = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )
    second = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )

    assert second.id == first.id
    # Only one row for this external key.
    sessions = await chat_repo.list()
    assert len(sessions) == 1


async def test_resolve_session_creates_new_row_outside_window(
    chat_repo, seeded_agent, stub_plugin
) -> None:
    """Existing row outside the continuation window → create a new row;
    the old row is preserved untouched."""
    envelope = _envelope()
    # Tight 1s window so the seeded stale row is "outside".
    account = _account(session_continuation_seconds=1)

    stale_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    stale = ChatSession(
        id="stale-1",
        agent_name=seeded_agent,
        title="stale-title",
        platform="stub",
        connector_account_id="acc-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        last_inbound_at=stale_iso,
        created_at=stale_iso,
        updated_at=stale_iso,
    )
    await chat_repo.create(stale)

    fresh = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )

    assert fresh.id != "stale-1"
    # Old row preserved untouched (title, last_inbound_at unchanged).
    old = await chat_repo.get("stale-1")
    assert old.title == "stale-title"
    assert old.last_inbound_at == stale_iso

    # Both rows exist for this external key.
    sessions = await chat_repo.list()
    assert len(sessions) == 2


async def test_resolve_session_per_thread_distinct(
    chat_repo, seeded_agent, stub_plugin
) -> None:
    """Envelopes for thread A vs. thread B (same channel) get distinct sessions."""
    env_a = _envelope(thread_id="A")
    env_b = _envelope(thread_id="B")
    account = _account()

    s_a = await resolve_session(
        env_a, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )
    s_b = await resolve_session(
        env_b, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )

    assert s_a.id != s_b.id
    assert s_a.thread_id == "A"
    assert s_b.thread_id == "B"


async def test_resolve_session_dm_shape(
    chat_repo, seeded_agent, stub_plugin
) -> None:
    """DM-shaped envelope (no thread, channel encodes peer pair) → session
    created with ``thread_id=None``."""
    envelope = _envelope(channel_id="dm-alice", thread_id=None, peer_id="alice")
    account = _account()

    session = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )

    assert session.thread_id is None
    assert session.channel_id == "dm-alice"
    assert session.peer_id == "alice"


# ─── resolve_session — display_channel fallback paths ────────────────────


class _MinimalPlugin:
    """A connector plugin WITHOUT ``display_channel`` — exercises the
    ``getattr`` sentinel-None fallback path."""

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
            thread_id=inbound.thread_id,
            peer_id=inbound.peer_id,
        )


class _RaisingPlugin:
    """A plugin whose ``display_channel`` raises — resolver must catch
    and use the envelope.channel_id fallback."""

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
            thread_id=inbound.thread_id,
            peer_id=inbound.peer_id,
        )

    def display_channel(self, envelope: InboundEnvelope) -> str:
        raise RuntimeError("plugin author bug")


async def test_resolve_session_display_channel_missing_falls_back_to_channel_id(
    chat_repo, seeded_agent
) -> None:
    """Plugin without ``display_channel`` → title is ``envelope.channel_id``."""
    envelope = _envelope(channel_id="ch-fallback")
    account = _account()
    plugin = _MinimalPlugin()

    session = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=plugin
    )

    assert session.title == "ch-fallback"


async def test_resolve_session_display_channel_raises_falls_back_to_channel_id(
    chat_repo, seeded_agent
) -> None:
    """Plugin's ``display_channel`` raises → resolver catches, returns
    successfully with title from envelope."""
    envelope = _envelope(channel_id="ch-raises")
    account = _account()
    plugin = _RaisingPlugin()

    session = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=plugin
    )

    assert session.title == "ch-raises"


# ─── resolve_session — plugin authority over key shape ───────────────────


class _ThreadCollapsingPlugin:
    """A plugin that collapses threads into the parent channel by
    returning a SessionKey with ``thread_id=None`` regardless of what the
    envelope carries. Exercises the resolver respecting plugin authority."""

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
            thread_id=None,  # collapse — ignore envelope.thread_id
            peer_id=inbound.peer_id,
        )

    def display_channel(self, envelope: InboundEnvelope) -> str:
        return f"collapsed:{envelope.channel_id}"


async def test_resolve_session_plugin_decides_key_shape(
    chat_repo, seeded_agent
) -> None:
    """Plugin returns ``thread_id=None`` despite envelope having a thread;
    resolver stores ``thread_id=None`` on the new row (uses None for lookup
    AND for the stored column)."""
    envelope = _envelope(thread_id="ignored-by-plugin")
    account = _account()
    plugin = _ThreadCollapsingPlugin()

    session = await resolve_session(
        envelope, account, chat_repo, agent_name=seeded_agent, plugin=plugin
    )

    assert session.thread_id is None
    # And a second call with a different thread on the envelope should
    # resolve to the SAME row (because the plugin collapses threads).
    env2 = _envelope(thread_id="another-thread")
    session2 = await resolve_session(
        env2, account, chat_repo, agent_name=seeded_agent, plugin=plugin
    )
    assert session2.id == session.id


# ─── resolve_session — peer_id audit semantics ───────────────────────────


async def test_resolve_session_peer_id_stored_but_not_in_lookup(
    chat_repo, seeded_agent, stub_plugin
) -> None:
    """Two envelopes with same (platform, account, channel, thread) but
    different ``peer_id`` resolve to the SAME row — peer_id doesn't
    participate in the lookup. The first row's peer_id is preserved
    (the second call's peer_id is NOT stored on the row)."""
    env1 = _envelope(peer_id="peer-A")
    env2 = _envelope(peer_id="peer-B")
    account = _account()

    s1 = await resolve_session(
        env1, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )
    s2 = await resolve_session(
        env2, account, chat_repo, agent_name=seeded_agent, plugin=stub_plugin
    )

    assert s2.id == s1.id
    # The stored peer_id is from the FIRST envelope (resolver did NOT
    # rewrite it on the reuse path).
    loaded = await chat_repo.get(s1.id)
    assert loaded.peer_id == "peer-A"
