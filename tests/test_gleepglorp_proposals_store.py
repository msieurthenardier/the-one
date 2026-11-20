"""The proposal store (M36 F2 L2, DD4 and DD5): the one-open rule, transitions, cascades."""

from __future__ import annotations

import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    ProposalOpen,
    mark_op,
    proposal_view,
)


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "p.db")
    yield c
    await c.close()


@pytest.fixture
def repo(conn):
    return GleepGlorpProposalRepository(conn)


def new(session="s1", key="agent:a", kind="agent", agent="a", **kw) -> NewProposal:
    return NewProposal(
        session_id=session,
        kind=kind,
        action=kw.pop("action", "change"),
        agent_name=agent,
        target_key=key,
        changes=kw.pop("changes", {"description": "d"}),
        **kw,
    )


async def statuses(conn, session="s1") -> list[tuple[int, str]]:
    async with conn.execute(
        "SELECT id, status FROM gleepglorp_proposals WHERE session_id = ? ORDER BY id", (session,)
    ) as cur:
        return [(r[0], r[1]) for r in await cur.fetchall()]


async def count(conn) -> int:
    async with conn.execute("SELECT COUNT(*) FROM gleepglorp_proposals") as cur:
        return (await cur.fetchone())[0]


# --- insert and reads --------------------------------------------------------------------


async def test_insert_and_reads_round_trip(repo) -> None:
    pid = await repo.insert(
        new(
            changes={"description": "d"},
            base={"description": "old"},
            target_id="t1",
            tool_call_id="call-1",
            untrusted=True,
            untrusted_sources=["read_app_config"],
        )
    )
    p = await repo.get(pid)
    assert p.status == "pending" and p.result is None and p.resolved_at is None
    assert p.changes == {"description": "d"} and p.base == {"description": "old"}
    assert p.untrusted is True and p.untrusted_sources == ["read_app_config"]
    assert p.tool_call_id == "call-1" and p.target_id == "t1"
    assert (await repo.open_for_session("s1")).id == pid
    assert [x.id for x in await repo.list_for_session("s1")] == [pid]
    assert await repo.get(999) is None and await repo.open_for_session("none") is None


async def test_ids_only_go_up(repo, conn) -> None:
    a = await repo.insert(new())
    await repo.mark(a, "dismissed", from_statuses=("pending",))
    await conn.execute("DELETE FROM gleepglorp_proposals")
    await conn.commit()
    b = await repo.insert(new())
    assert b > a  # AUTOINCREMENT: a number is never reused


async def test_create_has_a_null_base(repo) -> None:
    pid = await repo.insert(new(action="create", base=None))
    assert (await repo.get(pid)).base is None


# --- one open proposal per chat ---------------------------------------------------------


async def test_a_second_proposal_for_something_else_is_refused(repo, conn) -> None:
    first = await repo.insert(new(key="agent:a"))
    with pytest.raises(ProposalOpen) as e:
        await repo.insert(new(key="agent:b", agent="b"))
    assert e.value.open_id == first
    assert await statuses(conn) == [(first, "pending")]


async def test_the_same_target_replaces_the_open_one(repo, conn) -> None:
    first = await repo.insert(new(key="agent:a", changes={"description": "one"}))
    second = await repo.insert(new(key="agent:a", changes={"description": "two"}))
    assert await statuses(conn) == [(first, "withdrawn"), (second, "pending")]
    old = await repo.get(first)
    assert old.result == {"reason": "replaced", "by": second} and old.resolved_at
    assert (await repo.open_for_session("s1")).id == second


async def test_a_failed_proposal_is_replaced_by_any_next_one(repo, conn) -> None:
    first = await repo.insert(new(key="agent:a"))
    assert await repo.mark(first, "failed", result={"error": "x"}, from_statuses=("pending",))
    assert (await repo.open_for_session("s1")).id == first  # failed is still open
    second = await repo.insert(new(key="rule:a:new", kind="rule"))
    assert await statuses(conn) == [(first, "withdrawn"), (second, "pending")]


async def test_resolved_proposals_do_not_block_and_chats_are_independent(repo, conn) -> None:
    a = await repo.insert(new(key="agent:a"))
    await repo.mark(a, "applied", from_statuses=("pending",))
    b = await repo.insert(new(key="agent:b", agent="b"))
    other = await repo.insert(new(session="s2", key="agent:c", agent="c"))
    assert await statuses(conn) == [(a, "applied"), (b, "pending")]
    assert (await repo.open_for_session("s2")).id == other


# --- mark ----------------------------------------------------------------------------------


async def test_mark_writes_only_from_an_allowed_status(repo, conn) -> None:
    pid = await repo.insert(new())
    assert await repo.mark(pid, "applied", result={"ok": 1}, from_statuses=("pending",))
    # Already applied: neither a dismissal nor a failure from "pending" may overwrite it.
    assert not await repo.mark(pid, "dismissed", from_statuses=("pending",))
    assert not await repo.mark(pid, "failed", from_statuses=("pending", "failed"))
    p = await repo.get(pid)
    assert p.status == "applied" and p.result == {"ok": 1} and p.resolved_at
    assert not await repo.mark(pid, "dismissed", from_statuses=())
    assert not await repo.mark(12345, "dismissed", from_statuses=("pending",))
    with pytest.raises(ValueError):
        await repo.mark(pid, "bogus", from_statuses=("applied",))


async def test_mark_op_runs_inside_another_transaction(repo, conn) -> None:
    from the_one.db._write_lock import write_transaction

    pid = await repo.insert(new())
    with pytest.raises(RuntimeError):
        async with write_transaction(conn):
            assert await mark_op(conn, pid, "applied", from_statuses=("pending",))
            raise RuntimeError("rolls back with the caller's transaction")
    assert (await repo.get(pid)).status == "pending"


# --- the payload ---------------------------------------------------------------------------


async def test_the_view_shows_names_and_removed_references(repo, conn) -> None:
    await conn.execute(
        "INSERT INTO llm_providers (id, name, type, base_url, created_at, updated_at) "
        "VALUES ('p1', 'Local', 'ollama', 'http://localhost:11434', 't', 't')"
    )
    await conn.commit()
    pid = await repo.insert(
        new(
            changes={"provider_config_id": "p1", "kb_ids": ["gone"], "description": "d"},
            base={"provider_config_id": "p2"},
        )
    )
    v = await proposal_view(conn, await repo.get(pid))
    assert v["changes"] == {
        "provider_config_id": "Local",
        "kb_ids": ["(removed)"],
        "description": "d",
    }
    assert v["base"] == {"provider_config_id": "(removed)"}
    assert v["labels"]["description"] == "Description" and v["id"] == pid
    assert {
        "status",
        "result",
        "untrusted",
        "untrusted_sources",
        "created_at",
        "tool_call_id",
    } <= set(v)


# --- deleting and renaming -------------------------------------------------------------------


async def add_chat(conn, sid, agent="a", updated_at=None) -> None:
    kw = {"updated_at": updated_at} if updated_at else {}
    await ChatSessionRepository(conn).create(ChatSession(id=sid, agent_name=agent, title="t", **kw))


async def test_deleting_a_chat_deletes_its_proposals(conn, repo) -> None:
    await add_chat(conn, "s1")
    await add_chat(conn, "s2")
    await repo.insert(new(session="s1"))
    await repo.insert(new(session="s2"))
    await ChatSessionRepository(conn).delete("s1")
    assert await statuses(conn, "s1") == [] and len(await statuses(conn, "s2")) == 1


async def test_deleting_all_of_an_agents_chats_deletes_their_proposals(conn, repo) -> None:
    await add_chat(conn, "s1", "a")
    await add_chat(conn, "s2", "b")
    await repo.insert(new(session="s1"))
    await repo.insert(new(session="s2"))
    await ChatSessionRepository(conn).delete_all_for_agent("a")
    assert await statuses(conn, "s1") == [] and len(await statuses(conn, "s2")) == 1


async def test_the_age_purge_deletes_proposals_of_old_chats_only(conn, repo) -> None:
    await add_chat(conn, "old", "a", updated_at="2020-01-01T00:00:00+00:00")
    await add_chat(conn, "recent", "a")
    await repo.insert(new(session="old"))
    await repo.insert(new(session="recent"))
    ids = await ChatSessionRepository(conn).delete_older_than("a", "2021-01-01T00:00:00+00:00")
    assert ids == ["old"]
    assert await statuses(conn, "old") == [] and len(await statuses(conn, "recent")) == 1


async def test_the_gleepglorp_retention_purge_deletes_its_proposals(conn, repo) -> None:
    from the_one.retention import run_purge_sweep

    await add_chat(conn, "gg-old", "GleepGlorp", updated_at="2020-01-01T00:00:00+00:00")
    await add_chat(conn, "gg-new", "GleepGlorp")
    await repo.insert(new(session="gg-old", agent="x"))
    await repo.insert(new(session="gg-new", agent="x"))
    swept = await run_purge_sweep(conn)
    assert "gg-old" in swept["ids"]
    assert await statuses(conn, "gg-old") == [] and len(await statuses(conn, "gg-new")) == 1


async def test_purging_a_chats_messages_deletes_its_proposals(conn, repo) -> None:
    await add_chat(conn, "s1")
    await repo.insert(new(session="s1"))
    await ChatSessionRepository(conn).purge_messages("s1")
    assert await statuses(conn, "s1") == []


async def test_renaming_an_agent_rewrites_its_proposals(conn, tmp_path) -> None:
    from the_one.encryption import get_encryptor

    store = SQLiteAgentStore(conn, get_encryptor(tmp_path))
    await store.save(AgentConfig(name="old"))
    await store.save(AgentConfig(name="oldie"))  # a prefix-sharing agent is left alone
    repo = GleepGlorpProposalRepository(conn)
    keys = [
        ("s1", "agent", "agent:old", "old"),
        ("s2", "rule", "rule:old:abc", "old"),
        ("s3", "rule", "rule:old:new", "old"),
        ("s4", "routine", "routine:old:new:Daily", "old"),
        ("s5", "routine", "routine:old:rid", "old"),
        ("s6", "agent", "agent:oldie", "oldie"),
    ]
    for sid, kind, key, agent in keys:
        await repo.insert(new(session=sid, kind=kind, key=key, agent=agent))
    await store.rename("old", "newer")
    async with conn.execute(
        "SELECT session_id, agent_name, target_key FROM gleepglorp_proposals ORDER BY session_id"
    ) as cur:
        got = [tuple(r) for r in await cur.fetchall()]
    assert got == [
        ("s1", "newer", "agent:newer"),
        ("s2", "newer", "rule:newer:abc"),
        ("s3", "newer", "rule:newer:new"),
        ("s4", "newer", "routine:newer:new:Daily"),
        ("s5", "newer", "routine:newer:rid"),
        ("s6", "oldie", "agent:oldie"),
    ]
