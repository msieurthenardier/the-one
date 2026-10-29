"""Unit tests for the pure daily-purge sweep service (M13 F03 L3).

Covers ``the_one.retention``: the ``is_purge_due`` due-check matrix and the
``run_purge_sweep`` per-agent age-based purge. These are pure DB-layer tests
— they build a fresh ``ensure_schema``'d connection and never import
``app.py`` or touch the in-memory ``_sessions`` registry.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession
from the_one.db.repositories import (
    AppMetadataRepository,
    ChatSessionRepository,
    SQLiteAgentStore,
)
from the_one.retention import (
    LAST_PURGE_KEY,
    get_last_purge_at,
    is_purge_due,
    run_purge_sweep,
)


@pytest.fixture
async def conn(tmp_path):
    """Fresh schema-applied SQLite connection (mirrors test_db_repositories)."""

    db_path = tmp_path / "test.db"
    connection = await connect_template_db(db_path)
    yield connection
    await connection.close()


def _aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ── is_purge_due matrix ───────────────────────────────────────────────────


def test_is_purge_due_never_purged_is_due() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert is_purge_due(None, now) is True


def test_is_purge_due_23h_not_due() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    last = (now - timedelta(hours=23)).isoformat()
    assert is_purge_due(last, now) is False


def test_is_purge_due_25h_is_due() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    last = (now - timedelta(hours=25)).isoformat()
    assert is_purge_due(last, now) is True


def test_is_purge_due_exactly_24h_is_due() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    last = (now - timedelta(hours=24)).isoformat()
    assert is_purge_due(last, now) is True


# ── run_purge_sweep ───────────────────────────────────────────────────────


async def test_run_purge_sweep_per_agent_windows(conn) -> None:
    """Two agents with DIFFERENT retention windows each purge by their own
    window: a 30-day-aged session is swept for the 7-day agent but survives
    for the 90-day agent."""
    store = SQLiteAgentStore(conn)
    chat_repo = ChatSessionRepository(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=7))
    await store.save(AgentConfig(name="b", chat_history_retention_days=90))

    aged = _aged_iso(30)
    await chat_repo.create(
        ChatSession(id="a-old", agent_name="a", created_at=aged, updated_at=aged)
    )
    await chat_repo.create(
        ChatSession(id="b-old", agent_name="b", created_at=aged, updated_at=aged)
    )

    result = await run_purge_sweep(conn)

    assert result["ids"] == ["a-old"]
    assert result["deleted"] == 1
    assert result["deleted"] == len(result["ids"])
    # a-old removed; b-old survives (within its 90-day window).
    remaining = {s.id for s in await chat_repo.list()}
    assert remaining == {"b-old"}


async def test_run_purge_sweep_connector_aged_swept_active_kept(conn) -> None:
    """An aged connector-keyed row is swept; a recent (active) connector row
    is kept — same agent, age is the only discriminator."""
    store = SQLiteAgentStore(conn)
    chat_repo = ChatSessionRepository(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=7))

    aged = _aged_iso(30)
    recent = datetime.now(timezone.utc).isoformat()
    await chat_repo.create(
        ChatSession(
            id="conn-old",
            agent_name="a",
            platform="discord",
            connector_id="c1",
            channel_id="ch1",
            created_at=aged,
            updated_at=aged,
        )
    )
    await chat_repo.create(
        ChatSession(
            id="conn-active",
            agent_name="a",
            platform="discord",
            connector_id="c1",
            channel_id="ch2",
            created_at=recent,
            updated_at=recent,
        )
    )
    # An aged interactive row too — also swept.
    await chat_repo.create(
        ChatSession(id="chat-old", agent_name="a", created_at=aged, updated_at=aged)
    )

    result = await run_purge_sweep(conn)

    assert set(result["ids"]) == {"conn-old", "chat-old"}
    remaining = {s.id for s in await chat_repo.list()}
    assert remaining == {"conn-active"}


async def test_run_purge_sweep_cross_agent_isolation(conn) -> None:
    """Agent a's narrow window does NOT delete agent b's aged sessions."""
    store = SQLiteAgentStore(conn)
    chat_repo = ChatSessionRepository(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=7))
    await store.save(AgentConfig(name="b", chat_history_retention_days=90))

    aged = _aged_iso(30)
    await chat_repo.create(
        ChatSession(id="a-old", agent_name="a", created_at=aged, updated_at=aged)
    )
    await chat_repo.create(
        ChatSession(id="b-old", agent_name="b", created_at=aged, updated_at=aged)
    )

    result = await run_purge_sweep(conn)

    assert "b-old" not in result["ids"]
    assert {s.id for s in await chat_repo.list("b")} == {"b-old"}


async def test_run_purge_sweep_advances_last_purge_at(conn) -> None:
    """last_purge_at is written (and round-trips via get_last_purge_at) even
    when nothing is deleted."""
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=7))

    assert await get_last_purge_at(conn) is None
    result = await run_purge_sweep(conn)
    assert result["deleted"] == 0
    stored = await AppMetadataRepository(conn).get(LAST_PURGE_KEY)
    assert stored == result["last_purge_at"]
    assert await get_last_purge_at(conn) == result["last_purge_at"]


async def test_run_purge_sweep_empty_agents_table_advances_timestamp(conn) -> None:
    """No agents → deletes nothing but still advances last_purge_at (a due
    sweep ran; record it so it isn't re-run every wake)."""
    result = await run_purge_sweep(conn)
    assert result == {
        "deleted": 0,
        "ids": [],
        "runs_deleted": 0,
        "last_purge_at": result["last_purge_at"],
    }
    assert await get_last_purge_at(conn) is not None


# ── routine run history (M33 F1, DD1; AC19) ───────────────────────────────


async def test_run_purge_sweep_deletes_old_finished_runs_per_agent(conn) -> None:
    """Finished runs older than the agent's own window go; newer runs, running
    rows and other agents' runs (inside their window) stay."""
    from the_one.routines.models import RoutineRun
    from the_one.routines.repository import AgentRoutineRepository, RoutineRunRepository

    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=7))
    await store.save(AgentConfig(name="b", chat_history_retention_days=90))
    routines = AgentRoutineRepository(conn)
    runs = RoutineRunRepository(conn)
    fields = {
        "name": "r",
        "prompt": "p",
        "schedule": {"kind": "daily", "time": "09:00"},
        "target_kind": "new",
    }
    ra = await routines.create("a", fields)
    rb = await routines.create("b", fields)

    async def put(routine_id, run_id, finished, outcome="ok"):
        await runs.insert(
            RoutineRun(
                id=run_id,
                routine_id=routine_id,
                trigger_kind="schedule",
                outcome=outcome,
                started_at=_aged_iso(40),
                finished_at=finished,
            )
        )

    await put(ra.id, "a-old", _aged_iso(30))
    await put(ra.id, "a-new", _aged_iso(1))
    await put(ra.id, "a-running", None, "running")
    await put(rb.id, "b-30d", _aged_iso(30))
    result = await run_purge_sweep(conn)
    assert result["runs_deleted"] == 1
    async with conn.execute("SELECT id FROM agent_routine_runs ORDER BY id") as cur:
        assert [r[0] for r in await cur.fetchall()] == ["a-new", "a-running", "b-30d"]
    assert len(await routines.list_for_agent("a")) == 1  # routines untouched


async def test_run_purge_sweep_leaves_routine_proposals(conn) -> None:
    """M33 F2 DD10: the sweep never touches the agent's routine proposals."""
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=1))
    old = _aged_iso(400)
    await conn.execute(
        "INSERT INTO agent_routine_proposals (id, agent_name, routine_name, action, payload, "
        "status, created_at, resolved_at) VALUES ('p1', 'a', 'n', 'create', '{}', 'applied', "
        "?, ?)",
        (old, old),
    )
    await conn.commit()
    await run_purge_sweep(conn)
    async with conn.execute("SELECT COUNT(*) FROM agent_routine_proposals") as cur:
        assert (await cur.fetchone())[0] == 1
