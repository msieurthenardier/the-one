"""The proposal change shape (M36 F2 L2, DD1 and DD2): validation, names to ids, base."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests._gleepglorp_seed import seed
from the_one.agent.config import AgentConfig
from the_one.gleepglorp import kinds
from the_one.gleepglorp.proposals import shape
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.routines.repository import AgentRoutineRepository

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
async def world(tmp_path):
    ns = await seed(tmp_path)
    yield ns
    await ns.conn.close()


async def norm(world, kind, action, changes, **target):
    return await shape.normalize(
        kind,
        action,
        target,
        changes,
        conn=world.conn,
        now=NOW,
        zone=UTC,
        enc=world.enc,
    )


async def refused(world, kind, action, changes, **target) -> str:
    with pytest.raises(ShapeError) as e:
        await norm(world, kind, action, changes, **target)
    return str(e.value)


async def id_of(world, table: str, name: str) -> str:
    async with world.conn.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)) as cur:  # noqa: S608
        return (await cur.fetchone())[0]


# --- the declared shape ---------------------------------------------------------------


def test_the_operator_only_fields_are_in_no_spec() -> None:
    names = {f.name for specs in shape.SPECS.values() for f in specs}
    stored = {f.stored for specs in shape.SPECS.values() for f in specs}
    for forbidden in shape.OPERATOR_ONLY_FIELDS:
        assert forbidden not in names and forbidden not in stored
    # The agent's six, the MCP server's three (Leg 4a), then the provider's api_key (Leg 5a;
    # its ``secrets`` is the MCP server's too), the knowledge base's folders, items and path and
    # the secret's values and keys (its ``secret_ids`` is the agent's) (M36 F5 L3a).
    assert set(shape.OPERATOR_ONLY_FIELDS) == {
        "folders",
        "items",
        "path",
        "values",
        "keys",
        "api_key",
        "secret_ids",
        "tool_overrides",
        "mcp_overrides",
        "self_revision_requires_approval",
        "routines_self_config_enabled",
        "routines_require_approval",
        "cwd",
        "sandbox",
        "secrets",
    }


def test_every_agent_field_maps_to_an_agent_config_field_of_a_compatible_type() -> None:
    fields = AgentConfig.model_fields
    expected = {
        "name": "name",
        "description": "description",
        "provider": "provider_config_id",
        "model": "llm_model",
        "system_prompt": "system_prompt",
        "enabled_tools": "enabled_tools",
        "disabled_tools": "disabled_tools",
        "mcp_servers": "mcp_source_ids",
        "knowledge_bases": "kb_ids",
        "rich_visuals": "rich_visuals",
        "notes_enabled": "notes_enabled",
        "max_iterations": "max_iterations",
        "chat_history_retention_days": "chat_history_retention_days",
    }
    assert {f.name: f.stored for f in shape.AGENT_FIELDS} == expected
    compatible = {
        "text": (str,),
        "boolean": (bool,),
        "integer": (int,),
        "names": (list,),
    }
    for f in shape.AGENT_FIELDS:
        assert f.stored in fields, f.name
        annotation = str(fields[f.stored].annotation)
        want = compatible[f.type][0].__name__
        assert want in annotation or (f.ref == "provider" and "str" in annotation), (
            f.name,
            annotation,
        )
    # Never looser: the shape's bounds sit inside the model's.
    retention = next(f for f in shape.AGENT_FIELDS if f.name == "chat_history_retention_days")
    assert (retention.min, retention.max) == (1, 365)


def test_describe_is_generated_from_the_specs() -> None:
    listing = shape.describe()
    assert [e["name"] for e in listing] == [
        "agent",
        "rule",
        "routine",
        "mcp_server",
        "provider",
        "knowledge_base",
        "secret",
    ]
    detail = shape.describe("rule")
    by = {f["name"]: f for f in detail["fields"]}
    assert by["text"]["required_on_create"] is True
    assert by["position"]["create_only"] is True and by["position"]["min"] == 1
    agent = {f["name"]: f for f in shape.describe("agent")["fields"]}
    assert agent["provider"]["reference"] == "a model provider's name"
    assert agent["max_iterations"]["max"] == 200


async def test_the_fields_kind_of_read_app_config_comes_from_the_shape(world) -> None:
    from the_one.gleepglorp import views

    listing = await views.read(world.conn, world.enc, "fields")
    assert [e["name"] for e in listing] == [
        "agent",
        "rule",
        "routine",
        "mcp_server",
        "provider",
        "knowledge_base",
        "secret",
    ]
    detail = await views.read(world.conn, world.enc, "fields", "agent")
    assert detail == shape.describe("agent")
    assert {f["name"] for f in detail["fields"]} == {f.name for f in shape.AGENT_FIELDS}
    with pytest.raises(views.PlainMessage) as e:
        await views.read(world.conn, world.enc, "fields", "does-not-exist")
    assert "Valid names: agent, rule, routine, mcp_server, provider, knowledge_base, secret" in str(
        e.value
    )
    with pytest.raises(views.PlainMessage):
        await views.read(world.conn, world.enc, "fields", "x" * 500)


# --- refusals --------------------------------------------------------------------------


async def test_unknown_kind_action_and_field(world) -> None:
    assert "Unknown kind" in await refused(world, "widget", "create", {})
    assert "Unknown action" in await refused(world, "agent", "delete", {}, agent="plain")
    msg = await refused(world, "agent", "change", {"secret_ids": ["x"]}, agent="plain")
    assert "secret_ids" in msg and "Allowed fields:" in msg and "system_prompt" in msg
    for key in shape.OPERATOR_ONLY_FIELDS:
        assert "Allowed fields:" in await refused(world, "agent", "change", {key: 1}, agent="plain")
    assert "object" in await refused(world, "agent", "change", "text", agent="plain")


async def test_missing_required_create_only_and_empty(world) -> None:
    assert "needs name" in await refused(world, "agent", "create", {"description": "d"})
    assert "needs text" in await refused(world, "rule", "create", {"enabled": True}, agent="plain")
    msg = await refused(world, "routine", "create", {"name": "x"}, agent="plain")
    assert "prompt" in msg and "schedule" in msg
    assert "only be set when creating" in await refused(
        world, "agent", "change", {"name": "other"}, agent="plain"
    )
    assert "only be set when creating" in await refused(
        world, "rule", "change", {"position": 1}, agent="wide", rule=1
    )
    assert "Nothing to change" in await refused(world, "agent", "change", {}, agent="plain")


async def test_wrong_types_and_ranges(world) -> None:
    assert "text" in await refused(world, "agent", "change", {"description": 3}, agent="plain")
    assert "true or false" in await refused(
        world, "agent", "change", {"rich_visuals": "yes"}, agent="plain"
    )
    assert "whole number" in await refused(
        world, "agent", "change", {"max_iterations": True}, agent="plain"
    )
    assert "from 1 to 200" in await refused(
        world, "agent", "change", {"max_iterations": 500}, agent="plain"
    )
    assert "from 1 to 365" in await refused(
        world, "agent", "change", {"chat_history_retention_days": 0}, agent="plain"
    )
    assert "list of names" in await refused(
        world, "agent", "change", {"enabled_tools": "shell"}, agent="plain"
    )
    assert "list of names" in await refused(
        world, "agent", "change", {"enabled_tools": None}, agent="plain"
    )
    assert "limited to" in await refused(
        world, "agent", "change", {"description": "x" * 1001}, agent="plain"
    )


async def test_provider_and_model_pairing(world) -> None:
    both = await norm(world, "agent", "change", {"provider": "Local", "model": "m2"}, agent="plain")
    assert both.changes == {"provider_config_id": "p-local", "llm_model": "m2"}
    only_model = await norm(world, "agent", "change", {"model": "m3"}, agent="plain")
    assert only_model.changes == {"llm_model": "m3"}
    assert only_model.base == {"llm_model": "m"}
    assert await refused(world, "agent", "change", {"provider": "Local"}, agent="plain") == (
        "Give the model too."
    )
    assert "both provider and model, or neither" in await refused(
        world, "agent", "create", {"name": "new", "provider": "Local"}
    )
    assert "both provider and model, or neither" in await refused(
        world, "agent", "create", {"name": "new", "model": "m"}
    )
    neither = await norm(world, "agent", "create", {"name": "bare"})
    assert "provider_config_id" not in neither.changes


async def test_built_in_tool_names_are_checked_and_current_time_is_valid(world) -> None:
    ok = await norm(
        world,
        "agent",
        "change",
        {"enabled_tools": ["shell", "current_time"], "disabled_tools": ["current_time"]},
        agent="plain",
    )
    assert ok.changes["enabled_tools"] == ["shell", "current_time"]
    assert ok.changes["disabled_tools"] == ["current_time"]
    assert "No built-in tool named nope" in await refused(
        world, "agent", "change", {"enabled_tools": ["nope"]}, agent="plain"
    )
    assert "No built-in tool named" in await refused(
        world, "agent", "change", {"disabled_tools": ["kb__x__search"]}, agent="plain"
    )
    empty = await norm(world, "agent", "change", {"enabled_tools": []}, agent="plain")
    assert empty.changes["enabled_tools"] == []


# --- names to ids ----------------------------------------------------------------------


async def test_names_resolve_to_ids(world) -> None:
    n = await norm(
        world,
        "agent",
        "change",
        {
            "provider": "OpenAI main",
            "model": "gpt-y",
            "mcp_servers": ["Docs server"],
            "knowledge_bases": ["Docs KB"],
        },
        agent="plain",
    )
    assert n.changes == {
        "provider_config_id": "p-openai",
        "llm_model": "gpt-y",
        "mcp_source_ids": ["m-http"],
        "kb_ids": ["kb1"],
    }


async def test_unknown_and_ambiguous_names(world) -> None:
    assert await refused(
        world, "agent", "change", {"provider": "Nope", "model": "m"}, agent="plain"
    ) == ("No model provider named Nope.")
    assert await refused(world, "agent", "change", {"mcp_servers": ["Missing"]}, agent="plain") == (
        "No MCP server named Missing."
    )
    assert await refused(
        world, "agent", "change", {"knowledge_bases": ["Missing"]}, agent="plain"
    ) == ("No knowledge base named Missing.")
    # Names are unique only for agents and secrets: a second one makes the name ambiguous.
    await world.conn.execute(
        "INSERT INTO knowledge_bases (id, name, description, created_at, updated_at) "
        "VALUES ('kb2', 'Docs KB', '', 't', 't')"
    )
    await world.conn.commit()
    assert await refused(
        world, "agent", "change", {"knowledge_bases": ["Docs KB"]}, agent="plain"
    ) == ("More than one knowledge base is named Docs KB; rename one first.")


async def test_the_surface_row_is_never_an_mcp_server(world) -> None:
    msg = await refused(
        world, "agent", "change", {"mcp_servers": ["self-configuration"]}, agent="plain"
    )
    assert msg == "No MCP server named self-configuration."
    # A source merely named like the surface row (no marker) is excluded by name too.
    await world.conn.execute(
        "INSERT INTO mcp_sources (id, name, type, config, secrets, created_at, updated_at) "
        "VALUES ('m-fake', 'self-configuration', 'stdio', '{}', '', 't', 't')"
    )
    await world.conn.commit()
    assert "No MCP server named self-configuration." == await refused(
        world, "agent", "change", {"mcp_servers": ["self-configuration"]}, agent="plain"
    )


# --- targets ----------------------------------------------------------------------------


async def test_a_refusal_quotes_a_model_supplied_value_only_short(world) -> None:
    """The tool's output is trusted: a refusal cuts a model-chosen string to a short quote."""
    long = "x" * 500
    msg = await refused(world, "agent", "change", {"model": "m"}, agent=long)
    assert msg == f"No agent named {'x' * shape._ECHO_MAX}…."
    msg = await refused(world, "agent", "change", {long: "v"}, agent="wide")
    assert long not in msg and "x" * shape._ECHO_MAX in msg


async def test_agent_targets(world) -> None:
    assert "Say which agent" in await refused(world, "agent", "change", {"model": "m"})
    assert await refused(world, "agent", "change", {"model": "m"}, agent="ghost") == (
        "No agent named ghost."
    )
    for reserved in ("GleepGlorp", "default", "GLEEPGLORP"):
        assert "can't be changed here" in await refused(
            world, "agent", "change", {"model": "m"}, agent=reserved
        )
        assert "can't be changed here" in await refused(
            world, "rule", "create", {"text": "t"}, agent=reserved
        )
        msg = await refused(world, "agent", "create", {"name": reserved})
        assert "built-in assistant" in msg or "reserved name" in msg
    assert "already exists" in await refused(world, "agent", "create", {"name": "WIDE"})
    assert await refused(world, "agent", "create", {"name": "a/b"})  # the naming rule
    created = await norm(world, "agent", "create", {"name": "Fresh", "description": "d"})
    assert (created.agent_name, created.target_key, created.base) == ("Fresh", "agent:Fresh", None)
    assert created.changes["name"] == "Fresh"


async def test_rule_targets_and_base(world) -> None:
    n = await norm(world, "rule", "change", {"text": "Be terse."}, agent="wide", rule=1)
    assert n.target_id and n.target_key == f"rule:wide:{n.target_id}"
    assert n.base == {"text": "Always answer briefly."}
    assert "no rule 2" in await refused(
        world, "rule", "change", {"text": "x"}, agent="wide", rule=2
    )
    assert "no rule 0" in await refused(
        world, "rule", "change", {"text": "x"}, agent="wide", rule=0
    )
    assert "Say which rule" in await refused(world, "rule", "change", {"text": "x"}, agent="wide")
    assert "Say which rule" in await refused(
        world, "rule", "change", {"text": "x"}, agent="wide", rule=True
    )
    assert "no rule 1" in await refused(
        world, "rule", "change", {"text": "x"}, agent="plain", rule=1
    )
    created = await norm(world, "rule", "create", {"text": "Rule", "position": 1}, agent="plain")
    assert created.target_key == "rule:plain:new" and created.changes["position"] == 1
    assert created.base is None
    assert "cannot be empty" in await refused(
        world, "rule", "create", {"text": "  "}, agent="plain"
    )


async def test_routine_targets_and_base(world) -> None:
    n = await norm(
        world, "routine", "change", {"enabled": False}, agent="wide", routine="morning digest"
    )
    assert n.target_key == f"routine:wide:{n.target_id}"
    assert n.base == {"enabled": True}
    assert "no routine named Ghost" in await refused(
        world, "routine", "change", {"enabled": False}, agent="wide", routine="Ghost"
    )
    assert "Say which routine" in await refused(
        world, "routine", "change", {"enabled": False}, agent="wide"
    )
    assert "already has a routine named" in await refused(
        world,
        "routine",
        "create",
        {"name": "Morning digest", "prompt": "p", "schedule": _in(2)},
        agent="wide",
    )
    renamed = await refused(
        world, "routine", "change", {"name": "Morning digest"}, agent="plain", routine="x"
    )
    assert "no routine named x" in renamed


def _in(hours: int) -> dict:
    return {"start": {"in": {"amount": hours, "unit": "hours"}}}


async def test_routine_schedule_is_normalised_once_with_the_anchor(world) -> None:
    n = await norm(
        world,
        "routine",
        "create",
        {"name": "Later", "prompt": "Do it", "schedule": _in(3), "enabled": True},
        agent="plain",
    )
    assert n.target_key == "routine:plain:new:Later"
    assert n.changes["schedule"]["start"]["date"] and n.changes["schedule"]["repeat"] is None
    anchor = datetime.fromisoformat(n.changes["anchor_at"])
    assert 2.9 * 3600 < (anchor - NOW).total_seconds() < 3.1 * 3600
    weekly = await norm(
        world,
        "routine",
        "create",
        {
            "name": "Wall",
            "prompt": "p",
            "schedule": {
                "start": {"date": "2026-12-01", "time": "09:00"},
                "repeat": {"every": 1, "unit": "day"},
            },
        },
        agent="plain",
    )
    assert weekly.changes["anchor_at"] is None
    # The change form carries the pair and its base too.
    ch = await norm(
        world, "routine", "change", {"schedule": _in(3)}, agent="wide", routine="Morning digest"
    )
    assert set(ch.changes) == {"schedule", "anchor_at"}
    assert set(ch.base) == {"schedule", "anchor_at"}


async def test_the_now_start_and_bad_schedules_are_refused(world) -> None:
    now_start = {"start": {"now": True}, "repeat": {"every": 5, "unit": "minute"}}
    msg = await refused(
        world,
        "routine",
        "create",
        {"name": "N", "prompt": "p", "schedule": now_start},
        agent="plain",
    )
    assert msg  # a plain sentence, never a now-start
    assert "object like {start, repeat, ends}" in await refused(
        world,
        "routine",
        "create",
        {"name": "N", "prompt": "p", "schedule": "every day at nine"},
        agent="plain",
    )
    past = {"start": {"date": "2026-01-01", "time": "09:00"}}
    assert "no runs left" in await refused(
        world, "routine", "create", {"name": "N", "prompt": "p", "schedule": past}, agent="plain"
    )
    assert (
        "prompt"
        in (
            await refused(
                world,
                "routine",
                "create",
                {"name": "N", "prompt": " ", "schedule": _in(2)},
                agent="plain",
            )
        ).lower()
    )


# --- base ---------------------------------------------------------------------------------


async def test_agent_base_is_the_stored_value_without_the_surface_id(world) -> None:
    n = await norm(
        world,
        "agent",
        "change",
        {
            "description": "new",
            "mcp_servers": ["Local tool"],
            "system_prompt": "s",
            "enabled_tools": ["shell"],
        },
        agent="wide",
    )
    assert set(n.base) == {"description", "mcp_source_ids", "system_prompt", "enabled_tools"}
    assert n.base["description"] == "The wide agent"
    assert n.base["enabled_tools"] is None
    # "wide" has the surface row m-surface attached; the base leaves it out (Leg 1's form).
    assert n.base["mcp_source_ids"] == ["m-http"]
    assert "mcp_overrides" not in n.base and "mcp_overrides" not in n.changes


async def test_base_uses_the_same_normaliser_as_the_precheck(monkeypatch, world) -> None:
    from the_one.agent import service

    seen = []
    real = service.comparable_value

    def spy(field, value, ids):
        seen.append(field)
        return real(field, value, ids)

    monkeypatch.setattr(kinds.agent, "comparable_value", spy)
    await norm(world, "agent", "change", {"description": "d"}, agent="wide")
    assert seen == ["description"]


async def test_routine_name_not_taken_by_another(world) -> None:
    repo = AgentRoutineRepository(world.conn)
    await repo.create(
        "wide",
        {
            "name": "Second",
            "prompt": "p",
            "schedule": {"start": {"date": "2026-12-01", "time": "09:00"}},
        },
    )
    msg = await refused(
        world, "routine", "change", {"name": "second"}, agent="wide", routine="Morning digest"
    )
    assert "already has a routine named" in msg


# --- the routine schedule hint (M36 F2 L10 fairness fix) ----------------------------------


def test_the_routine_schedule_hint_states_the_full_canonical_shape() -> None:
    from the_one.routines import recurrence

    fields = {f["name"]: f for f in shape.describe("routine")["fields"]}
    hint = fields["schedule"]["hint"]
    assert "0 = Monday" in hint
    assert "repeat" in hint and "every: N" in hint and "days:" in hint
    assert "ends" in hint and "kind: after, count" in hint
    for unit in recurrence.UNITS:  # driven by the recurrence module's own units
        assert unit in hint
    assert '"days": [0, 1, 2, 3, 4]' in hint  # the one weekday example


async def test_the_schedule_example_round_trips_through_the_routine_service(world) -> None:
    import copy

    from the_one.routines import service as routine_service

    example = copy.deepcopy(shape.SCHEDULE_EXAMPLE)
    example["start"]["date"] = "2026-11-23"  # a Monday after NOW
    sched, _anchor = routine_service.validate_schedule(example, NOW, UTC)
    assert sched["repeat"]["days"] == [0, 1, 2, 3, 4]
    # the placeholder itself is refused, so it cannot be mistaken for a date
    with pytest.raises(Exception):  # noqa: B017 - RoutineFieldError
        routine_service.validate_schedule(shape.SCHEDULE_EXAMPLE, NOW, UTC)
    n = await norm(
        world,
        "routine",
        "create",
        {"name": "weekdays", "prompt": "p", "schedule": example},
        agent="wide",
    )
    assert n.changes["schedule"]["repeat"]["days"] == [0, 1, 2, 3, 4]
