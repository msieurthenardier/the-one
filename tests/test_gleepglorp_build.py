"""AgentFactory builds GleepGlorp from its settings (M36 F1 L03, DD1)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from conftest import FakeLLM

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.agent.factory import (
    AgentFactory,
    AgentNotFoundError,
    GleepGlorpUnavailableError,
    ProviderNotConfiguredError,
)
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import (
    LLMProviderRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import get_encryptor
from the_one.gleepglorp import GleepGlorpSettings, save_settings
from the_one.gleepglorp.prompt import base_prompt
from the_one.tools.builtins import BuiltinToolProvider


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    fake_settings = SimpleNamespace(
        data_dir=tmp_path, agents_dir=tmp_path / "agents", ensure_dirs=lambda: None
    )
    llm_args: dict[str, Any] = {}

    def _get_provider(name: str, **kwargs: Any) -> FakeLLM:
        llm_args.update(kwargs)
        return FakeLLM(responses=[])

    async def _conn():
        return conn

    with (
        patch("the_one.agent.factory.settings", fake_settings),
        patch("the_one.agent.factory.get_provider", _get_provider),
        patch("the_one.db.connection.get_connection", _conn),
    ):
        enc = get_encryptor(tmp_path)
        await LLMProviderRepository(conn, enc).create(
            LLMProviderConfig(id="p1", name="P", type="ollama", base_url="http://x/v1")
        )
        yield SimpleNamespace(conn=conn, llm_args=llm_args, enc=enc)
    await conn.close()


async def _ready(env, **over) -> None:
    # The minimal set: memory and web access are off unless a test turns them on (L06).
    over = {"memory": False, "web_access": False, **over}
    await save_settings(
        env.conn, GleepGlorpSettings(provider_config_id="p1", model="small-model", **over)
    )


def _factory(env, **kwargs) -> AgentFactory:
    return AgentFactory(
        store=SQLiteAgentStore(env.conn), tool_providers=[BuiltinToolProvider()], **kwargs
    )


async def test_the_minimal_allowlist(env, monkeypatch) -> None:
    """Whatever the operator's tools, agents, MCP servers or exposure, GleepGlorp has
    exactly search_tools and current_time, and current_time is in its starting set."""
    # Another agent with a wide toolset and an attachment must not leak into GleepGlorp.
    await SQLiteAgentStore(env.conn).save(
        AgentConfig(
            name="wide",
            provider_config_id="p1",
            llm_model="m",
            enabled_tools=None,
            kb_ids=["kb-1"],
            mcp_source_ids=["mcp-1"],
            notes_enabled=True,
        )
    )
    await _ready(env)
    monkeypatch.setenv("THE_ONE_TOOL_EXPOSURE_FRACTION", "0")
    agent = await _factory(env).create("GleepGlorp")

    assert set(agent.tools.tool_names) == {
        "search_tools",
        "current_time",
        "read_app_config",
        "get_app_guide",
    }
    assert env.llm_args["model"] == "small-model"
    assert "current_time" in agent._loaded_tool_names
    # Each is in the starting set whatever the exposure decision (exposure is off here).
    assert {s["name"] for s in agent._loaded_schemas} == {
        "current_time",
        "read_app_config",
        "get_app_guide",
    }
    assert len(agent._loaded_schemas) == 3
    prompt = agent.system_prompt
    assert prompt.startswith(base_prompt(web=False))  # the helper's default: web access off
    assert "current_time" in prompt  # the tool-wording date line
    # No platform text, rules, persona, notes or secrets layers.
    for banned in ("search_tools", "saved_notes", "{{secret:", "Rich visuals"):
        assert banned not in prompt
    assert agent.tool_exposure.decided is False


async def test_the_allowlist_holds_with_current_time_off_app_wide(env) -> None:
    await _ready(env)
    await ToolConfigRepository(env.conn, env.enc).upsert("current_time", {}, enabled=False)
    agent = await _factory(env).create("GleepGlorp")
    assert set(agent.tools.tool_names) == {"search_tools", "read_app_config", "get_app_guide"}
    assert "current_time" not in agent.system_prompt


async def test_the_allowlist_holds_when_the_factory_has_a_store_of_none(env) -> None:
    await _ready(env)
    agent = await AgentFactory(store=None, tool_providers=[BuiltinToolProvider()]).create(
        "GleepGlorp"
    )
    assert set(agent.tools.tool_names) == {
        "search_tools",
        "current_time",
        "read_app_config",
        "get_app_guide",
    }


async def test_no_other_agent_gains_read_app_config(env) -> None:
    """The tool is registered for GleepGlorp alone, whatever another agent's toolset."""
    await _ready(env)
    await SQLiteAgentStore(env.conn).save(
        AgentConfig(name="plain", provider_config_id="p1", llm_model="m", enabled_tools=None)
    )
    agent = await _factory(env).create("plain")
    assert "read_app_config" not in agent.tools.tool_names
    assert "get_app_guide" not in agent.tools.tool_names
    from the_one.tools.builtins import _TOOL_CLASSES

    assert "read_app_config" not in _TOOL_CLASSES
    assert "get_app_guide" not in _TOOL_CLASSES


async def test_create_with_no_name_builds_gleepglorp(env) -> None:
    await _ready(env)
    agent = await _factory(env).create()
    assert agent.system_prompt.startswith(base_prompt(web=False))


async def test_the_secret_resolver_is_gleepglorps(env) -> None:
    await _ready(env)
    agent = await _factory(env).create("GleepGlorp")
    assert agent._secrets.agent_name == "GleepGlorp"


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"enabled": False}, "off"),
        ({"model": None}, "needs_model"),
        ({"provider_config_id": None}, "needs_model"),
        ({"provider_config_id": "gone"}, "provider_missing"),
    ],
)
async def test_an_unready_setting_raises_with_its_state(env, over, expected) -> None:
    base = {"provider_config_id": "p1", "model": "m"}
    await save_settings(env.conn, GleepGlorpSettings(**{**base, **over}))
    with pytest.raises(GleepGlorpUnavailableError) as info:
        await _factory(env).create("GleepGlorp")
    assert info.value.state == expected
    assert isinstance(info.value, ProviderNotConfiguredError)
    assert isinstance(info.value, ValueError)
    assert str(info.value)


async def test_only_the_exact_spelling_is_gleepglorp(env) -> None:
    await _ready(env)
    for name in ("gleepglorp", "GLEEPGLORP", "default"):
        with pytest.raises(AgentNotFoundError):
            await _factory(env).create(name)


_BASE = {"search_tools", "current_time", "read_app_config", "get_app_guide"}
_NOTES = {"save_note", "update_note", "forget_note"}


@pytest.mark.parametrize("memory", [True, False])
@pytest.mark.parametrize("web_access", [True, False])
@pytest.mark.parametrize("search_ok", [True, False])
@pytest.mark.parametrize("off", [None, "fetch_url", "web_search", "current_time"])
async def test_the_allowlist_matrix(env, memory, web_access, search_ok, off) -> None:
    """Every combination of the two switches, the search engine and an app-wide off."""
    await _ready(env, memory=memory, web_access=web_access)
    repo = ToolConfigRepository(env.conn, env.enc)
    if not search_ok:
        await repo.upsert("web_search", {"search_backend": "brave"}, enabled=True)
    if off:
        await repo.upsert(off, {}, enabled=False)
    agent = await _factory(env).create("GleepGlorp")

    expected = set(_BASE)
    if memory:
        expected |= _NOTES
    if web_access:
        expected |= {"fetch_url"}
        if search_ok:
            expected |= {"web_search"}
    expected.discard(off)
    assert set(agent.tools.tool_names) == expected
    # Every one of them is in the starting set.
    assert {s["name"] for s in agent._loaded_schemas} == expected - {"search_tools"}
    # The notes layer follows the memory switch alone.
    assert ("<saved_notes>" in agent.system_prompt) is memory


async def test_a_keyed_engine_needs_every_required_field(env) -> None:
    await _ready(env, web_access=True)
    repo = ToolConfigRepository(env.conn, env.enc)
    await repo.upsert(
        "web_search", {"search_backend": "google_pse", "google_pse_cse_id": "cx"}, enabled=True
    )
    assert "web_search" not in (await _factory(env).create("GleepGlorp")).tools.tool_names
    await repo.upsert(
        "web_search",
        {"search_backend": "google_pse", "google_pse_cse_id": "cx"},
        secrets={"google_pse_api_key": "k"},
        enabled=True,
    )
    assert "web_search" in (await _factory(env).create("GleepGlorp")).tools.tool_names


async def test_the_settings_response_and_the_build_share_one_search_decision(env) -> None:
    from the_one.gleepglorp import response

    await _ready(env, web_access=True)
    assert (await response(env.conn))["web_search_available"] is True
    await ToolConfigRepository(env.conn, env.enc).upsert(
        "web_search", {"search_backend": "tavily"}, enabled=True
    )
    assert (await response(env.conn))["web_search_available"] is False
    assert "web_search" not in (await _factory(env).create("GleepGlorp")).tools.tool_names


async def test_web_search_switched_off_app_wide_is_not_available(env) -> None:
    from the_one.gleepglorp import response

    await _ready(env, web_access=True)
    repo = ToolConfigRepository(env.conn, env.enc)
    await repo.upsert("web_search", {"search_backend": "duckduckgo"}, enabled=False)
    assert (await response(env.conn))["web_search_available"] is False
    assert "web_search" not in (await _factory(env).create("GleepGlorp")).tools.tool_names
    await repo.upsert("web_search", {"search_backend": "duckduckgo"}, enabled=True)
    assert (await response(env.conn))["web_search_available"] is True


def test_search_configured_decisions() -> None:
    from the_one.gleepglorp.web import search_configured

    assert not search_configured({"search_backend": "duckduckgo"}, enabled=False)
    assert search_configured(None) and search_configured({})
    assert search_configured({"search_backend": "duckduckgo"})
    assert search_configured({"search_backend": "unknown-engine"})
    assert not search_configured({"search_backend": "searxng"})
    assert search_configured({"search_backend": "searxng", "searxng_base_url": "http://s"})
    assert not search_configured({"search_backend": "searxng", "searxng_base_url": "  "})
    assert not search_configured({"search_backend": "brave", "brave_api_key": ""})
    assert search_configured({"search_backend": "brave", "brave_api_key": "k"})
    assert not search_configured({"search_backend": "google_pse", "google_pse_api_key": "k"})


async def test_memory_adds_nothing_to_another_agents_tools(env) -> None:
    await _ready(env, memory=True, web_access=True)
    await SQLiteAgentStore(env.conn).save(
        AgentConfig(name="plain", provider_config_id="p1", llm_model="m", enabled_tools=[])
    )
    agent = await _factory(env).create("plain")
    assert not _NOTES & set(agent.tools.tool_names)


async def test_the_context_window_route_answers_404_for_gleepglorp(env) -> None:
    from fastapi import HTTPException

    from the_one.interfaces.web import api

    await _ready(env)
    with pytest.raises(HTTPException) as info:
        await api.get_agent_context_window("GleepGlorp")
    assert info.value.status_code == 404
