"""Sortie 20 leg 1: deleting an agent deletes its chats (DD1 to DD3, DD9).

Covers the store's single cascading transaction (rows, connector clearing, atomicity), the
route (``chats_deleted``, checkpoint, PTY release, one ``sessions_changed``), the shared
eviction helper (cancel, tell, evict) and the on-disk scrub (``secure_delete`` plus the WAL
checkpoint). The v57 migration test lives in ``tests/test_db_migration.py``.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore
from the_one.encryption import Encryptor


@pytest.fixture
async def conn(tmp_path):
    connection = await connect_template_db(tmp_path / "cascade.db")
    yield connection
    await connection.close()


@pytest.fixture
def store(conn, tmp_path):
    key = Fernet.generate_key()
    return SQLiteAgentStore(conn, Encryptor(key, key_path=tmp_path / "cascade.key"))


async def _count(conn, sql: str, *args) -> int:
    async with conn.execute(sql, args) as cur:
        return (await cur.fetchone())[0]


async def _seed_agent_rows(conn, agent: str, tag: str) -> None:
    """Chats (one with a proposal and a fill), a rule, a note, a routine with a finished run,
    a routine proposal and a connector binding, all keyed to ``agent``."""
    for sid in (f"{tag}-c1", f"{tag}-c2"):
        await conn.execute("INSERT INTO chat_sessions (id, agent_name) VALUES (?, ?)", (sid, agent))
    await conn.execute(
        "INSERT INTO gleepglorp_proposals (session_id, kind, action, target_key, changes, "
        "created_at) VALUES (?, 'rule', 'create', 'k', '{}', 't')",
        (f"{tag}-c1",),
    )
    await conn.execute(
        "INSERT INTO gleepglorp_fills (session_id, kind, action, agent_name, target_key, "
        "changes, status, created_at) VALUES (?, 'agent', 'change', ?, 'k', '{}', 'sent', 't')",
        (f"{tag}-c1", agent),
    )
    await conn.execute(
        "INSERT INTO agent_rules (id, agent_name, text, position, created_at, updated_at) "
        "VALUES (?, ?, 'rule', 0, 't', 't')",
        (f"{tag}-r", agent),
    )
    await conn.execute(
        "INSERT INTO agent_notes (id, agent_name, number, text, origin_kind, created_at, "
        "updated_at, updated_by) VALUES (?, ?, 1, 'note', 'web', 't', 't', 'agent')",
        (f"{tag}-n", agent),
    )
    await conn.execute(
        "INSERT INTO agent_routines (id, agent_name, name, prompt, schedule, "
        "created_at, updated_at) VALUES (?, ?, 'daily', 'p', '{}', 't', 't')",
        (f"{tag}-rt", agent),
    )
    await conn.execute(
        "INSERT INTO agent_routine_runs (id, routine_id, trigger_kind, outcome) "
        "VALUES (?, ?, 'manual', 'ok')",
        (f"{tag}-run", f"{tag}-rt"),
    )
    await conn.execute(
        "INSERT INTO agent_routine_proposals (id, agent_name, routine_id, routine_name, action, "
        "payload, status, created_at) VALUES (?, ?, ?, 'daily', 'create', '{}', 'pending', 't')",
        (f"{tag}-rp", agent, f"{tag}-rt"),
    )
    cfg = json.dumps({"default_agent": agent, "channel_map": {"c1": agent}})
    await conn.execute(
        "INSERT INTO connectors (id, type, config) VALUES (?, 'stub', ?)", (f"{tag}-conn", cfg)
    )
    await conn.commit()


_TABLES = (
    "chat_sessions",
    "gleepglorp_proposals",
    "gleepglorp_fills",
    "agent_rules",
    "agent_notes",
    "agent_routines",
    "agent_routine_runs",
    "agent_routine_proposals",
)


async def _snapshot(conn) -> dict[str, list]:
    out: dict[str, list] = {}
    for table in _TABLES:
        async with conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2") as cur:
            out[table] = [tuple(r) for r in await cur.fetchall()]
    async with conn.execute("SELECT id, config FROM connectors ORDER BY id") as cur:
        out["connectors"] = [tuple(r) for r in await cur.fetchall()]
    return out


# --- AC1, AC2: the cascade ------------------------------------------------------------------


async def test_delete_cascades_every_row_keyed_to_the_agent(conn, store) -> None:
    await store.save(AgentConfig(name="doomed"))
    await store.save(AgentConfig(name="other"))
    await conn.execute("INSERT INTO chat_sessions (id, agent_name) VALUES ('g1', 'GleepGlorp')")
    await _seed_agent_rows(conn, "doomed", "d")
    await _seed_agent_rows(conn, "other", "o")
    await conn.commit()
    other_before = {
        t: [r for r in rows if "o-" in repr(r)] for t, rows in (await _snapshot(conn)).items()
    }

    ids = await store.delete("doomed")

    assert sorted(ids) == ["d-c1", "d-c2"]
    assert await _count(conn, "SELECT COUNT(*) FROM agents WHERE name = 'doomed'") == 0
    for table, column in (
        ("chat_sessions", "agent_name = 'doomed'"),
        ("gleepglorp_proposals", "session_id LIKE 'd-%'"),
        ("gleepglorp_fills", "session_id LIKE 'd-%'"),
        ("agent_rules", "agent_name = 'doomed'"),
        ("agent_notes", "agent_name = 'doomed'"),
        ("agent_routines", "agent_name = 'doomed'"),
        ("agent_routine_runs", "id = 'd-run'"),
        ("agent_routine_proposals", "agent_name = 'doomed'"),
    ):
        assert await _count(conn, f"SELECT COUNT(*) FROM {table} WHERE {column}") == 0, table
    # Another agent's rows, its connector binding and GleepGlorp's own chat are untouched.
    after = await _snapshot(conn)
    other_after = {t: [r for r in rows if "o-" in repr(r)] for t, rows in after.items()}
    assert other_after == other_before
    assert await _count(conn, "SELECT COUNT(*) FROM chat_sessions WHERE agent_name='other'") == 2
    assert await _count(conn, "SELECT COUNT(*) FROM chat_sessions WHERE id = 'g1'") == 1


async def test_a_missing_agent_raises_before_any_write(conn, store) -> None:
    await store.save(AgentConfig(name="kept"))
    await _seed_agent_rows(conn, "kept", "k")
    before = await _snapshot(conn)
    with pytest.raises(KeyError):
        await store.delete("nope")
    assert await _snapshot(conn) == before


async def test_store_delete_does_not_notify(conn, store) -> None:
    await store.save(AgentConfig(name="doomed"))
    await _seed_agent_rows(conn, "doomed", "d")
    calls: list[int] = []
    with patch("the_one.db.repositories.notify_sessions_changed", lambda: calls.append(1)):
        await store.delete("doomed")
    assert calls == []


# --- DD3: connector clearing ----------------------------------------------------------------


async def test_connector_bindings_are_cleared_byte_exact_for_the_rest(conn, store) -> None:
    await store.save(AgentConfig(name="doomed"))
    await store.save(AgentConfig(name="other"))
    mixed = json.dumps(
        {"default_agent": "doomed", "channel_map": {"c1": "doomed", "c2": "other"}, "x": 1}
    )
    untouched = json.dumps({"default_agent": "other", "channel_map": {"c9": "other"}})
    for cid, cfg in (("mixed", mixed), ("untouched", untouched)):
        await conn.execute(
            "INSERT INTO connectors (id, type, config, updated_at) VALUES (?, 'stub', ?, 'u0')",
            (cid, cfg),
        )
    await conn.execute(
        "INSERT INTO connectors (id, type, config) VALUES ('bad', 'stub', 'not json')"
    )
    await conn.commit()

    await store.delete("doomed")

    async with conn.execute("SELECT id, config, updated_at FROM connectors ORDER BY id") as cur:
        rows = {r["id"]: (r["config"], r["updated_at"]) for r in await cur.fetchall()}
    assert json.loads(rows["mixed"][0]) == {"channel_map": {"c2": "other"}, "x": 1}
    assert "default_agent" not in json.loads(rows["mixed"][0])  # key removed, never None
    assert rows["untouched"] == (untouched, "u0")
    assert rows["bad"][0] == "not json"


# --- AC3: atomicity -------------------------------------------------------------------------


async def test_a_failure_mid_transaction_leaves_everything_unchanged(conn, store) -> None:
    await store.save(AgentConfig(name="doomed"))
    await _seed_agent_rows(conn, "doomed", "d")
    # The connector update is the last statement before the agents delete: make it raise.
    await conn.execute(
        "CREATE TRIGGER boom BEFORE UPDATE ON connectors "
        "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END"
    )
    await conn.commit()
    before = await _snapshot(conn)

    with pytest.raises(Exception, match="simulated failure"):
        await store.delete("doomed")

    assert await _count(conn, "SELECT COUNT(*) FROM agents WHERE name = 'doomed'") == 1
    assert await _snapshot(conn) == before


# --- AC4: rename still carries chats --------------------------------------------------------


async def test_rename_still_carries_chats(conn, store) -> None:
    await store.save(AgentConfig(name="old"))
    await conn.execute("INSERT INTO chat_sessions (id, agent_name) VALUES ('s1', 'old')")
    await conn.commit()
    await store.rename("old", "new")
    assert await _count(conn, "SELECT COUNT(*) FROM chat_sessions WHERE agent_name='new'") == 1


# --- AC5, AC7: the route --------------------------------------------------------------------


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "api.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "api.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        transport = ASGITransport(app=shared_app())
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


async def test_route_reports_chats_deleted_and_runs_the_followups(client, monkeypatch) -> None:
    import the_one.db.connection as db_connection
    import the_one.interfaces.web.api as api_mod
    from the_one.tools import _session_registry

    checkpoints: list[int] = []

    async def fake_checkpoint(_conn):
        checkpoints.append(1)
        return 0

    notified: list[int] = []
    closed: list[tuple[str, str]] = []

    async def fake_list(agent_name: str) -> list[str]:
        return ["pty-1", "pty-2"] if agent_name == "doomed" else []

    async def fake_close(agent_name: str, session_id: str) -> bool:
        closed.append((agent_name, session_id))
        return True

    monkeypatch.setattr(db_connection, "checkpoint_wal", fake_checkpoint)
    monkeypatch.setattr(api_mod, "notify_sessions_changed", lambda: notified.append(1))
    monkeypatch.setattr(_session_registry, "list_for_agent", fake_list)
    monkeypatch.setattr(_session_registry, "close", fake_close)

    assert (await client.post("/api/agents", json={"name": "doomed"})).status_code == 201
    for sid in ("s1", "s2", "s3"):
        resp = await client.post("/api/chat/sessions", json={"id": sid, "agent_name": "doomed"})
        assert resp.status_code == 201
    notified.clear()

    resp = await client.delete("/api/agents/doomed")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "chats_deleted": 3}
    assert (await client.get("/api/chat/sessions")).json() == []
    assert checkpoints == [1]
    assert notified == [1]  # once, not once per chat
    assert closed == [("doomed", "pty-1"), ("doomed", "pty-2")]


async def test_route_with_no_chats_reports_zero_and_does_not_notify(client, monkeypatch) -> None:
    import the_one.interfaces.web.api as api_mod

    notified: list[int] = []
    monkeypatch.setattr(api_mod, "notify_sessions_changed", lambda: notified.append(1))
    await client.post("/api/agents", json={"name": "empty"})
    resp = await client.delete("/api/agents/empty")
    assert resp.json() == {"status": "ok", "chats_deleted": 0}
    assert notified == []


async def test_route_404_runs_no_checkpoint(client, monkeypatch) -> None:
    import the_one.db.connection as db_connection

    checkpoints: list[int] = []

    async def fake_checkpoint(_conn):
        checkpoints.append(1)
        return 0

    monkeypatch.setattr(db_connection, "checkpoint_wal", fake_checkpoint)
    resp = await client.delete("/api/agents/never-existed")
    assert resp.status_code == 404
    assert checkpoints == []


# --- AC8: the eviction helper ---------------------------------------------------------------


class _FakeAgent:
    def __init__(self) -> None:
        self.aclose = AsyncMock()


class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.fixture
def app_mod(monkeypatch):
    import the_one.interfaces.web.app as mod
    from the_one.sessions import _broadcast
    from the_one.sessions._locks import session_locks

    monkeypatch.setattr(mod, "_sessions", {})
    monkeypatch.setattr(mod, "_session_inflight", {})
    monkeypatch.setattr(mod, "_cancel_tokens", {})
    session_locks.clear()
    _broadcast.clear_subscribers_for_test()
    yield mod
    session_locks.clear()
    _broadcast.clear_subscribers_for_test()


async def test_eviction_cancels_tells_and_evicts_a_live_chat(app_mod) -> None:
    from the_one.sessions._broadcast import add_subscriber
    from the_one.sessions._locks import session_locks

    agent = _FakeAgent()
    session = app_mod.Session(id="live", agent=agent, created="t")
    app_mod._sessions["live"] = session
    session_locks["live"] = asyncio.Lock()
    ws = _FakeSocket()
    add_subscriber("live", ws)

    async def turn() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(turn())
    await asyncio.sleep(0)  # let it start waiting
    app_mod._register_turn_task(session, task)

    evicted = await app_mod._evict_deleted_sessions(["live"])

    assert evicted == ["live"]
    assert task.cancelled()
    assert {"type": "session_deleted", "session_id": "live"} in ws.sent
    assert "live" not in app_mod._sessions
    assert "live" not in session_locks
    agent.aclose.assert_awaited_once()


async def test_eviction_is_a_no_op_for_an_id_with_nothing_live(app_mod) -> None:
    assert await app_mod._evict_deleted_sessions(["ghost"]) == []
    assert await app_mod._evict_deleted_sessions([]) == []


# --- DD9: scrubbing (AC12, AC14) ------------------------------------------------------------


async def test_the_app_connection_has_secure_delete_on(isolated_db) -> None:
    from the_one.db.connection import get_connection

    conn = await get_connection()
    async with conn.execute("PRAGMA secure_delete") as cur:
        assert (await cur.fetchone())[0] == 1


async def test_deleted_chat_content_is_gone_from_the_db_and_wal_files(isolated_db) -> None:
    """Raw bytes: the marker is on disk before the delete and in neither file after it."""
    from the_one.config import settings
    from the_one.db.connection import checkpoint_wal, get_connection

    conn = await get_connection()
    store = SQLiteAgentStore(
        conn, Encryptor(Fernet.generate_key(), key_path=settings.data_dir / "scrub.key")
    )
    marker = "ZXQ-SCRUB-MARKER-7f3a91c2"
    await store.save(AgentConfig(name="doomed"))
    messages = json.dumps(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": f"the secret is {marker}"},
        ]
    )
    # A surviving neighbour keeps the table's leaf page alive, so the deleted cell's bytes
    # would stay in the page's free space unless secure_delete zeroes them (a page emptied by
    # the delete is reset by SQLite regardless, which would make this test vacuous).
    await store.save(AgentConfig(name="keeper"))
    chats = ChatSessionRepository(conn)
    await chats.create(ChatSession(id="keep-1", agent_name="keeper", title="Keep"))
    await chats.create(
        ChatSession(id="scrub-1", agent_name="doomed", title="Scrub test", messages=messages)
    )
    await chats.create(ChatSession(id="keep-2", agent_name="keeper", title="Keep too"))

    db = settings.db_path
    wal = db.with_name(db.name + "-wal")

    def on_disk() -> bool:
        needle = marker.encode()
        return any(p.exists() and needle in p.read_bytes() for p in (db, wal))

    assert on_disk(), "the marker must be on disk before the delete (else the test is vacuous)"

    ids = await store.delete("doomed")
    busy = await checkpoint_wal(conn)

    assert ids == ["scrub-1"]
    assert busy == 0
    assert not on_disk()
    for p in (db, wal):
        if p.exists():
            assert marker.encode() not in p.read_bytes()
