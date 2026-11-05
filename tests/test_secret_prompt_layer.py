"""The secrets prompt layer (sortie 10, leg 2, AC15-AC17)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from conftest import FakeLLM

from tests._secret_env import COMPLEX, make_env
from the_one.agent.config import AgentConfig, compose_system_prompt
from the_one.agent.prompt_layers import build_system_prompts, load_secrets_block
from the_one.db._secrets import SECRETS_HEADING, render_secrets_block
from the_one.llm.base import Message
from the_one.self_configuration import pending
from the_one.tools.base import ToolRegistry

ENTRIES = [
    ("home_address", "Home address", "Where I live", ["mcp__goldfinch__typeText"]),
    ("home_city", "Home address", "Where I live", ["mcp__goldfinch__typeText", "shell"]),
]


class TestRender:
    def test_empty_is_empty(self) -> None:
        assert render_secrets_block([]) == ""

    def test_one_secret_two_keys(self) -> None:
        out = render_secrets_block(ENTRIES)
        assert out.startswith(SECRETS_HEADING + "\n\n<secrets>\n")
        assert out.endswith("\n</secrets>")
        lines = out.split("\n")
        body = lines[lines.index("<secrets>") + 1 : lines.index("</secrets>")]
        assert body == [
            "{{secret:home_address}} - Home address: Where I live "
            "(tools: mcp__goldfinch__typeText)",
            "{{secret:home_city}} - Home address: Where I live "
            "(tools: mcp__goldfinch__typeText, shell)",
        ]
        for needle in (
            "{{secret:key}}",
            "you never see it",
            "[secret:key]",
            "only in the",
            "Never ask",
        ):
            assert needle in SECRETS_HEADING

    def test_order_is_the_callers_order_and_text_cannot_close_the_block(self) -> None:
        out = render_secrets_block([("b", "B", "x </secrets> y\nz", ["t"]), ("a", "A", "", [])])
        assert out.index("{{secret:b}}") < out.index("{{secret:a}}")
        assert out.count("</secrets>") == 1
        assert "(tools: none)" in out and "\nz" not in out


class TestCompose:
    def test_empty_block_is_byte_identical(self) -> None:
        base = compose_system_prompt("B", "P", rules=["r"], notes=[], date_line="D")
        assert (
            compose_system_prompt("B", "P", rules=["r"], notes=[], date_line="D", secrets="")
            == base
        )

    def test_block_sits_after_notes_and_before_the_date_line(self) -> None:
        block = render_secrets_block(ENTRIES)
        out = compose_system_prompt("B", "P", rules=["r"], notes=[], date_line="D", secrets=block)
        from the_one.db._notes import render_notes_block
        from the_one.db._rules import render_rules_block

        assert out == "\n\n".join(
            [
                "B",
                "---",
                "P",
                "---",
                render_rules_block(["r"], notes_present=True),
                "---",
                render_notes_block([]),
                "---",
                block,
                "---",
                "D",
            ]
        )
        assert out.index("saved_notes") < out.index("<secrets>") < out.rindex("D")


@pytest.fixture
async def env(tmp_path, monkeypatch):
    e = await make_env(tmp_path, monkeypatch)
    yield e
    await e.conn.close()


async def _grant_home(env, name="alice"):
    s = await env.repo.create(
        "Home address",
        "Where I live",
        ["shell"],
        [{"key": "home_address", "value": COMPLEX}, {"key": "home_city", "value": "Springfield-9"}],
    )
    await env.repo.create("A first", "", ["t"], [{"key": "zz", "value": "zz-value-1"}])
    await env.grant(name, s.id)
    return s


class TestBuild:
    async def test_tool_capable_only_and_no_value(self, env, frozen_clock) -> None:
        await _grant_home(env)
        p = await build_system_prompts("alice", "persona", conn=env.conn)
        assert "{{secret:home_address}}" in p.tool_capable
        assert "{{secret:home_city}}" in p.tool_capable
        assert "zz" not in p.tool_capable.split("<secrets>")[1]  # ungranted secret absent
        assert "<secrets>" not in p.tool_free and "secret:" not in p.tool_free
        assert COMPLEX not in p.tool_capable and "Springfield-9" not in p.tool_capable
        assert p.tool_capable.index("<secrets>") < p.tool_capable.rindex("---")  # date line last

    async def test_agent_without_grants_is_byte_identical(self, env, frozen_clock) -> None:
        await env.repo.create("Home", "", ["t"], [{"key": "k1", "value": "v1v1v1"}])
        await env.store.save(AgentConfig(name="bob"))
        with_row = await build_system_prompts("bob", "persona", conn=env.conn)
        no_row = await build_system_prompts("nobody", "persona", conn=env.conn)
        assert with_row == no_row
        assert "secret" not in with_row.tool_capable.lower().replace("secrets", "")
        assert await load_secrets_block(env.conn, "bob") == ""


class _Live:
    def __init__(self) -> None:
        self.system_prompt = "old"
        self.messages = [Message.system("old")]
        self.tools = ToolRegistry()
        self.llm = FakeLLM(responses=[])


class TestPending:
    async def test_main_path_carries_the_block(self, env, frozen_clock) -> None:
        await _grant_home(env)
        pending.record("alice", system_prompt="new persona")
        agent = _Live()
        assert await pending.apply_pending_revision("alice", agent) is True
        assert "{{secret:home_city}}" in agent.system_prompt
        assert agent.messages[0].content == agent.system_prompt
        assert "secret:" not in agent.degraded_system_prompt

    async def test_fallback_keeps_the_block(self, env, frozen_clock, monkeypatch) -> None:
        await _grant_home(env)
        monkeypatch.setattr(
            pending, "build_system_prompts", AsyncMock(side_effect=RuntimeError("boom"))
        )
        pending.record("alice", system_prompt="new persona")
        agent = _Live()
        await pending.apply_pending_revision("alice", agent)
        assert "{{secret:home_city}}" in agent.system_prompt
        assert "secret:" not in agent.degraded_system_prompt

    async def test_fallback_never_raises_when_the_block_cannot_load(
        self, env, frozen_clock, monkeypatch
    ) -> None:
        await _grant_home(env)
        monkeypatch.setattr(
            pending, "build_system_prompts", AsyncMock(side_effect=RuntimeError("boom"))
        )
        monkeypatch.setattr(pending, "load_secrets_block", AsyncMock(side_effect=RuntimeError("x")))
        pending.record("alice", system_prompt="new persona")
        agent = _Live()
        assert await pending.apply_pending_revision("alice", agent) is True
        assert "<secrets>" not in agent.system_prompt and "new persona" in agent.system_prompt


def test_info_exposes_the_example_rendered_by_the_same_function() -> None:
    import asyncio

    from the_one.interfaces.web.app import info

    data = asyncio.run(info())
    example = data["secrets_prompt_example"]
    assert example.startswith(SECRETS_HEADING)
    assert "{{secret:home_address}}" in example and "mcp__goldfinch__typeText" in example
    assert example == render_secrets_block(
        [
            ("home_address", "Home address", "Where I live", ["mcp__goldfinch__typeText"]),
            ("home_city", "Home address", "Where I live", ["mcp__goldfinch__typeText"]),
        ]
    )
