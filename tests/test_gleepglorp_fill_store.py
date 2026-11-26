"""The fill store (M36 F3 L5, DD6): schema, replacement, claim and lease, outcome, the view,
and the chat cascades."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests._gleepglorp_seed import seed
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore
from the_one.gleepglorp.fill.store import (
    CLAIM_LEASE_SECONDS,
    FillClaimRefused,
    FillNotFound,
    FillOutcomeRefused,
    GleepGlorpFillRepository,
    NewFill,
    fill_view,
)

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "f.db")
    yield c
    await c.close()


@pytest.fixture
def repo(conn):
    return GleepGlorpFillRepository(conn)


def new(session="s1", agent="a", **kw) -> NewFill:
    return NewFill(
        session_id=session,
        kind=kw.pop("kind", "agent"),
        action=kw.pop("action", "change"),
        agent_name=agent,
        target_key=kw.pop("key", f"agent:{agent}"),
        changes=kw.pop("changes", {"description": "d"}),
        **kw,
    )


# --- schema (AC1) ----------------------------------------------------------------------------


async def test_the_table_has_its_columns_and_indexes(conn) -> None:
    from the_one.db.schema import CURRENT_VERSION

    assert CURRENT_VERSION == 57
    async with conn.execute("PRAGMA table_info(gleepglorp_fills)") as cur:
        cols = [r[1] for r in await cur.fetchall()]
    assert cols == [
        "id",
        "session_id",
        "tool_call_id",
        "kind",
        "action",
        "agent_name",
        "target_id",
        "target_key",
        "changes",
        "base",
        "status",
        "outcome",
        "claim_token",
        "untrusted",
        "untrusted_sources",
        "created_at",
        "claimed_at",
        "resolved_at",
    ]
    async with conn.execute("PRAGMA index_list(gleepglorp_fills)") as cur:
        names = {r[1] for r in await cur.fetchall()}
    assert {"idx_gleepglorp_fills_session", "idx_gleepglorp_fills_agent"} <= names


async def test_the_status_check_rejects_an_unknown_status(conn) -> None:
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO gleepglorp_fills (session_id, kind, action, agent_name, target_key, "
            "changes, status, created_at) VALUES ('s', 'agent', 'change', 'a', 'k', '{}', "
            "'bogus', 'now')"
        )


# --- insert, get, list, replacement (AC2) ----------------------------------------------------


async def test_insert_round_trips(repo) -> None:
    fid, replaced = await repo.insert(
        new(
            changes={"description": "d", "provider_config_id": "p1"},
            base={"description": "old"},
            tool_call_id="tc1",
            untrusted=True,
            untrusted_sources=["read_app_config"],
        )
    )
    assert replaced == []
    f = await repo.get(fid)
    assert f.status == "sent" and f.tool_call_id == "tc1" and f.claim_token is None
    assert f.changes == {"description": "d", "provider_config_id": "p1"}
    assert f.base == {"description": "old"}
    assert f.untrusted is True and f.untrusted_sources == ["read_app_config"]
    assert [x.id for x in await repo.list_for_session("s1")] == [fid]
    assert await repo.get(999) is None


async def test_only_agent_kind_is_stored(repo) -> None:
    with pytest.raises(ValueError):
        await repo.insert(new(kind="rule"))


async def test_a_newer_fill_replaces_unapplied_ones_only(repo) -> None:
    sent, _ = await repo.insert(new())
    nf, _ = await repo.insert(new())  # replaces `sent`
    await repo.claim(nf, T0)  # applying
    a, _ = await repo.insert(new(session="s3"))
    _, tok = await repo.claim(a, T0)
    await repo.record_outcome(a, tok, "not_filled", [], "stay")
    b, _ = await repo.insert(new(session="s3"))  # replaces a (not_filled)
    assert (await repo.get(a)).status == "replaced"
    _, tok = await repo.claim(b, T0)
    await repo.record_outcome(b, tok, "filled", [], None)
    c, _ = await repo.insert(new(session="s3"))
    _, tok = await repo.claim(c, T0)
    await repo.record_outcome(c, tok, "partly_filled", ["description"], None)
    d, _ = await repo.insert(new(session="s3"))
    e, _ = await repo.insert(new(session="s3"))
    assert [(await repo.get(i)).status for i in (b, c, d, e)] == [
        "filled",
        "partly_filled",
        "replaced",
        "sent",
    ]
    assert (await repo.get(sent)).status == "replaced"
    assert (await repo.get(nf)).status == "applying"  # an applying fill is left alone
    _, replaced = await repo.insert(new(session="s1"))
    assert replaced == [] and (await repo.get(nf)).status == "applying"


async def test_insert_returns_the_replaced_ids(repo) -> None:
    a, _ = await repo.insert(new())
    b, _ = await repo.insert(new())
    c, replaced = await repo.insert(new())
    assert replaced == [b] and (await repo.get(a)).status == "replaced"
    assert c > b > a


# --- claim and lease (AC2) -------------------------------------------------------------------


async def test_claim_moves_sent_to_applying_with_a_token(repo) -> None:
    fid, _ = await repo.insert(new())
    fill, token = await repo.claim(fid, T0)
    assert fill.status == "applying" and fill.claim_token == token and token
    assert fill.claimed_at == T0.isoformat()


async def test_a_second_claim_inside_the_lease_is_refused(repo) -> None:
    fid, _ = await repo.insert(new())
    await repo.claim(fid, T0)
    with pytest.raises(FillClaimRefused) as e:
        await repo.claim(fid, T0 + timedelta(seconds=CLAIM_LEASE_SECONDS - 1))
    assert e.value.status == "applying"


async def test_a_claim_after_the_lease_succeeds_and_voids_the_old_token(repo) -> None:
    fid, _ = await repo.insert(new())
    _, old = await repo.claim(fid, T0)
    _, new_token = await repo.claim(fid, T0 + timedelta(seconds=CLAIM_LEASE_SECONDS + 1))
    assert new_token != old
    with pytest.raises(FillOutcomeRefused):
        await repo.record_outcome(fid, old, "filled", [], None)
    assert (await repo.get(fid)).status == "applying"
    await repo.record_outcome(fid, new_token, "filled", [], None)


async def test_a_not_filled_fill_can_be_claimed_again(repo) -> None:
    fid, _ = await repo.insert(new())
    _, tok = await repo.claim(fid, T0)
    await repo.record_outcome(fid, tok, "not_filled", [], "stay")
    fill, _ = await repo.claim(fid, T0)
    assert fill.status == "applying"


async def test_final_and_replaced_fills_cannot_be_claimed(repo) -> None:
    a, _ = await repo.insert(new())
    await repo.insert(new())  # a is replaced
    with pytest.raises(FillClaimRefused) as e:
        await repo.claim(a, T0)
    assert e.value.status == "replaced"
    b, _ = await repo.insert(new(session="s2"))
    _, tok = await repo.claim(b, T0)
    await repo.record_outcome(b, tok, "filled", [], None)
    with pytest.raises(FillClaimRefused):
        await repo.claim(b, T0 + timedelta(hours=1))
    with pytest.raises(FillNotFound):
        await repo.claim(999, T0)


# --- outcome (AC2) ---------------------------------------------------------------------------


async def test_an_outcome_needs_the_token_and_applying(repo) -> None:
    fid, _ = await repo.insert(new())
    with pytest.raises(FillOutcomeRefused):  # still sent
        await repo.record_outcome(fid, "nope", "filled", [], None)
    _, tok = await repo.claim(fid, T0)
    with pytest.raises(FillOutcomeRefused):
        await repo.record_outcome(fid, "wrong", "filled", [], None)
    f = await repo.record_outcome(fid, tok, "partly_filled", ["description"], None)
    assert f.status == "partly_filled" and f.resolved_at
    assert f.outcome == {"kept": ["description"], "reason": None}
    with pytest.raises(FillOutcomeRefused):  # no second write
        await repo.record_outcome(fid, tok, "filled", [], None)
    with pytest.raises(FillNotFound):
        await repo.record_outcome(999, tok, "filled", [], None)


# --- the view (AC2) --------------------------------------------------------------------------


async def test_the_view_shows_names_keeps_ids_and_hides_the_token(tmp_path) -> None:
    ns = await seed(tmp_path)
    try:
        repo = GleepGlorpFillRepository(ns.conn)
        fid, _ = await repo.insert(
            new(
                agent="plain",
                changes={"description": "new", "provider_config_id": "p-openai"},
                base={"description": "nothing here"},
            )
        )
        _, token = await repo.claim(fid, T0)
        view = await fill_view(ns.conn, await repo.get(fid))
        assert "claim_token" not in view and token not in str(view)
        assert view["values"]["provider_config_id"] == "p-openai"
        assert view["changes"]["provider_config_id"] == "OpenAI main"
        assert view["title"] == "Change agent “plain”" and view["field_count"] == 2
        assert view["target_gone"] is False
        assert view["labels"]["description"] == "Description"
        # The stored description is not "nothing here": the field moved since base.
        assert [s["field"] for s in view["stale"]] == ["description"]
        assert view["stale"][0]["proposed"] == "new" and view["stale"][0]["label"]
    finally:
        await ns.conn.close()


async def test_a_change_to_a_deleted_agent_is_target_gone_and_a_create_is_never_stale(
    conn, repo
) -> None:
    fid, _ = await repo.insert(new(agent="ghost", base={"description": "x"}))
    v = await fill_view(conn, await repo.get(fid))
    assert v["target_gone"] is True and v["stale"] == []
    cid, _ = await repo.insert(new(session="s2", agent="Fresh", action="create", key="agent:Fresh"))
    v = await fill_view(conn, await repo.get(cid))
    assert v["target_gone"] is False and v["stale"] == [] and v["base"] is None
    assert v["title"] == "Create agent “Fresh”"


# --- the chat cascades (AC8) -----------------------------------------------------------------


async def add_chat(conn, sid, agent="a", updated_at=None) -> None:
    kw = {"updated_at": updated_at} if updated_at else {}
    await ChatSessionRepository(conn).create(ChatSession(id=sid, agent_name=agent, title="t", **kw))


async def count(conn, sid) -> int:
    async with conn.execute(
        "SELECT COUNT(*) FROM gleepglorp_fills WHERE session_id = ?", (sid,)
    ) as cur:
        return (await cur.fetchone())[0]


async def test_deleting_a_chat_deletes_its_fills(conn, repo) -> None:
    await add_chat(conn, "s1")
    await add_chat(conn, "s2")
    await repo.insert(new(session="s1"))
    await repo.insert(new(session="s2"))
    await ChatSessionRepository(conn).delete("s1")
    assert await count(conn, "s1") == 0 and await count(conn, "s2") == 1


async def test_deleting_all_of_an_agents_chats_deletes_their_fills(conn, repo) -> None:
    await add_chat(conn, "s1", "a")
    await add_chat(conn, "s2", "b")
    await repo.insert(new(session="s1"))
    await repo.insert(new(session="s2"))
    await ChatSessionRepository(conn).delete_all_for_agent("a")
    assert await count(conn, "s1") == 0 and await count(conn, "s2") == 1


async def test_the_age_purge_deletes_fills_of_old_chats_only(conn, repo) -> None:
    await add_chat(conn, "old", "a", updated_at="2020-01-01T00:00:00+00:00")
    await add_chat(conn, "recent", "a")
    await repo.insert(new(session="old"))
    await repo.insert(new(session="recent"))
    ids = await ChatSessionRepository(conn).delete_older_than("a", "2021-01-01T00:00:00+00:00")
    assert ids == ["old"]
    assert await count(conn, "old") == 0 and await count(conn, "recent") == 1


async def test_purging_a_chats_messages_deletes_its_fills(conn, repo) -> None:
    await add_chat(conn, "s1")
    await repo.insert(new(session="s1"))
    await ChatSessionRepository(conn).purge_messages("s1")
    assert await count(conn, "s1") == 0


async def test_renaming_an_agent_rewrites_its_fills(conn, tmp_path) -> None:
    from the_one.encryption import get_encryptor

    store = SQLiteAgentStore(conn, get_encryptor(tmp_path))
    await store.save(AgentConfig(name="old"))
    await store.save(AgentConfig(name="oldie"))
    repo = GleepGlorpFillRepository(conn)
    await repo.insert(new(session="s1", agent="old"))
    await repo.insert(new(session="s2", agent="oldie"))
    await store.rename("old", "newer")
    async with conn.execute(
        "SELECT session_id, agent_name, target_key FROM gleepglorp_fills ORDER BY session_id"
    ) as cur:
        got = [tuple(r) for r in await cur.fetchall()]
    assert got == [("s1", "newer", "agent:newer"), ("s2", "oldie", "agent:oldie")]
