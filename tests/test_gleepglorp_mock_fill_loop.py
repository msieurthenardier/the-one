"""A scripted mock GleepGlorp makes one ``fill_form`` call through the real loop (M36 F3 L9).

The desktop-engine runs drive GleepGlorp with a mock provider whose ``responses`` list is a
``fill_form`` create call, then closing text. This proves the whole path server-side: the
factory-built GleepGlorp agent, the real ``Agent.step`` loop (no step-limit stop), the real tool
and its one ``gleepglorp_fills`` row.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tests._schema_template import connect_template_db
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository, SQLiteAgentStore
from the_one.encryption import get_encryptor
from the_one.gleepglorp import GleepGlorpSettings, save_settings
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository
from the_one.llm.mock import MockProvider
from the_one.tools.builtins import BuiltinToolProvider

PAGE = {"line": "Settings › Appearance", "descriptor": {"destination": "settings"}}
CHANGES = {
    "name": "Filled by mock",
    "description": "Written by the scripted mock.",
    "system_prompt": "You are a scripted example.",
}
FINAL = "The form is filled, not saved. Click Save."
RESPONSES = [
    {
        "content": "",
        "tool_calls": [
            {
                "id": "fill-1",
                "name": "fill_form",
                "arguments": {"kind": "agent", "action": "create", "changes": CHANGES},
            }
        ],
    },
    {"content": FINAL},
]


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    fake_settings = SimpleNamespace(
        data_dir=tmp_path, agents_dir=tmp_path / "agents", ensure_dirs=lambda: None
    )

    def _get_provider(name: str, **kwargs: Any) -> MockProvider:
        return MockProvider(
            model=kwargs.get("model") or "mock-default", config=kwargs.get("config")
        )

    async def _conn():
        return conn

    with (
        patch("the_one.agent.factory.settings", fake_settings),
        patch("the_one.agent.factory.get_provider", _get_provider),
        patch("the_one.db.connection.get_connection", _conn),
        patch("the_one.config.settings.data_dir", tmp_path),
    ):
        enc = get_encryptor(tmp_path)
        await LLMProviderRepository(conn, enc).create(
            LLMProviderConfig(
                id="mock1",
                name="Mock",
                type="mock",
                base_url="",
                config={"models": ["mock-default"], "responses": RESPONSES},
            )
        )
        await save_settings(
            conn,
            GleepGlorpSettings(
                provider_config_id="mock1", model="mock-default", memory=False, web_access=False
            ),
        )
        yield SimpleNamespace(conn=conn)
    await conn.close()


async def _step(agent, text: str, page=PAGE):
    token = current_turn.set(TurnContext(session_id="drawer-1", page=page))
    try:
        return [m async for m in agent.step(text, page=page)]
    finally:
        current_turn.reset(token)


async def test_the_mock_drives_one_fill_through_the_real_loop(env) -> None:
    factory = AgentFactory(store=SQLiteAgentStore(env.conn), tool_providers=[BuiltinToolProvider()])
    agent = await factory.create("GleepGlorp")
    assert "fill_form" in agent.tools.tool_names
    assert "fill_form" in {s["name"] for s in agent._loaded_schemas}  # in the starting set

    out = await _step(agent, "Fill in a new agent for me.")

    rows = await GleepGlorpFillRepository(env.conn).list_for_session("drawer-1")
    assert len(rows) == 1
    [row] = rows
    assert (row.kind, row.action, row.status) == ("agent", "create", "sent")
    assert row.changes["name"] == "Filled by mock"
    assert row.changes["description"] == CHANGES["description"]
    assert row.changes["system_prompt"] == CHANGES["system_prompt"]
    # The loop ended on the scripted text, not on the step limit, with one tool result.
    assert out[-1].content == FINAL
    tool_results = [m.content for m in out if m.role.value == "tool"]
    assert len(tool_results) == 1 and tool_results[0].startswith("Fill ")
    assert not any("step limit" in str(m.content).lower() for m in out)
    # No agent was created.
    assert await SQLiteAgentStore(env.conn).list_agents() == []


async def test_without_a_page_the_scripted_call_is_refused_and_the_loop_still_ends(env) -> None:
    factory = AgentFactory(store=SQLiteAgentStore(env.conn), tool_providers=[BuiltinToolProvider()])
    agent = await factory.create("GleepGlorp")
    out = await _step(agent, "Fill in a new agent for me.", page=None)
    assert await GleepGlorpFillRepository(env.conn).list_for_session("drawer-1") == []
    assert out[-1].content == FINAL
