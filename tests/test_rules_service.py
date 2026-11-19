"""The rule write service and the rule repository's hooks (Mission 36 Flight 2 Leg 1)."""

from __future__ import annotations

import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.agent.rules_service import change_rule, create_rule
from the_one.agent.service import AgentStaleError, AgentWriteError
from the_one.db._rules import RULES_TOTAL_MAX_CHARS
from the_one.db.repositories import AgentRuleRepository, SQLiteAgentStore
from the_one.encryption import Encryptor


@pytest.fixture
async def repo(tmp_path):
    from cryptography.fernet import Fernet

    conn = await connect_template_db(tmp_path / "r.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "r.key")
    await SQLiteAgentStore(conn, enc).save(AgentConfig(name="a"))
    yield AgentRuleRepository(conn)
    await conn.close()


async def _texts(repo) -> list[tuple[str, int]]:
    return [(r.text, r.position) for r in await repo.list_for_agent("a")]


async def test_create_appends_by_default(repo) -> None:
    await create_rule(repo, "a", "one")
    await create_rule(repo, "a", "two")
    assert await _texts(repo) == [("one", 0), ("two", 1)]


async def test_create_at_position_zero_inserts_first_with_dense_positions(repo) -> None:
    await create_rule(repo, "a", "one")
    await create_rule(repo, "a", "two")
    new = await create_rule(repo, "a", "first", position=0)
    assert new.position == 0
    assert await _texts(repo) == [("first", 0), ("one", 1), ("two", 2)]


async def test_create_position_is_clamped(repo) -> None:
    await create_rule(repo, "a", "one")
    last = await create_rule(repo, "a", "last", position=99)
    first = await create_rule(repo, "a", "first", position=-5)
    assert (first.position, last.position) == (0, 1)  # `last` was clamped to the end (n=1)
    assert await _texts(repo) == [("first", 0), ("one", 1), ("last", 2)]


async def test_a_raising_on_commit_rolls_back_a_create(repo) -> None:
    await create_rule(repo, "a", "one")

    async def boom(conn) -> None:
        raise RuntimeError("hook failed")

    with pytest.raises(RuntimeError):
        await create_rule(repo, "a", "two", position=0, on_commit=boom)
    assert await _texts(repo) == [("one", 0)]


async def test_a_raising_precheck_rolls_back_a_create(repo) -> None:
    def precheck(current) -> None:
        assert current is None
        raise ValueError("no")

    with pytest.raises(ValueError):
        await repo.create("a", "two", True, position=0, precheck=precheck)
    assert await _texts(repo) == []


async def test_the_total_limit_is_the_route_422(repo) -> None:
    await create_rule(repo, "a", "x" * 500)
    with pytest.raises(AgentWriteError) as exc:
        for _ in range(RULES_TOTAL_MAX_CHARS // 500 + 1):
            await create_rule(repo, "a", "x" * 500)
    assert exc.value.status == 422


async def test_change_rule_changes_only_what_it_is_told(repo) -> None:
    rule = await create_rule(repo, "a", "text", enabled=True)
    changed = await change_rule(repo, "a", rule.id, {"enabled": False})
    assert (changed.text, changed.enabled) == ("text", False)
    changed = await change_rule(repo, "a", rule.id, {"text": "new"})
    assert (changed.text, changed.enabled) == ("new", False)


async def test_change_rule_missing_is_a_404(repo) -> None:
    with pytest.raises(AgentWriteError) as exc:
        await change_rule(repo, "a", "nope", {"text": "x"})
    assert (exc.value.status, exc.value.detail) == (404, "Rule not found: nope")


async def test_change_rule_stale_names_the_field_and_writes_nothing(repo) -> None:
    rule = await create_rule(repo, "a", "stored")
    with pytest.raises(AgentStaleError) as exc:
        await change_rule(repo, "a", rule.id, {"text": "mine"}, base={"text": "what I saw"})
    assert exc.value.fields == [{"field": "text", "current": "stored", "proposed": "mine"}]
    assert (await repo.get("a", rule.id)).text == "stored"


async def test_change_rule_override_and_matching_base_apply(repo) -> None:
    rule = await create_rule(repo, "a", "stored")
    await change_rule(repo, "a", rule.id, {"text": "one"}, base={"text": "stored"})
    await change_rule(repo, "a", rule.id, {"text": "two"}, base={"text": "stale"}, override=True)
    assert (await repo.get("a", rule.id)).text == "two"


async def test_a_raising_on_commit_rolls_back_a_change(repo) -> None:
    rule = await create_rule(repo, "a", "stored")

    async def boom(conn) -> None:
        raise RuntimeError("hook failed")

    with pytest.raises(RuntimeError):
        await change_rule(repo, "a", rule.id, {"text": "mine"}, on_commit=boom)
    assert (await repo.get("a", rule.id)).text == "stored"


async def test_change_rule_refuses_a_move(repo) -> None:
    rule = await create_rule(repo, "a", "stored")
    with pytest.raises(AgentWriteError) as exc:
        await change_rule(repo, "a", rule.id, {"position": 0})
    assert exc.value.status == 422
    assert exc.value.detail[0]["loc"] == ["position"]
