"""Sortie 11 leg 3 Part A: the exposure decision, the build-time lookup, the seeding,
the wording that follows the decision and the settle re-render."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from conftest import FakeLLM

import the_one.vectors  # noqa: F401  (bind its get_connection before the build patches it)
from the_one.agent import factory as factory_module
from the_one.agent.config import AgentConfig
from the_one.agent.core import CONTINUE_SCHEMA, SEARCH_TOOLS_SCHEMA
from the_one.agent.factory import AgentFactory
from the_one.agent.platform_prompt import (
    PRELOADED_KB_LINE,
    PRELOADED_TOOL_DISCOVERY,
    Capabilities,
    render_platform,
)
from the_one.agent.tool_exposure import (
    CEILING_ENV,
    FRACTION_ENV,
    ToolExposure,
    decide_exposure,
    exposure_defaults,
)
from the_one.db.models import LLMProviderConfig
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.connector_history import FETCH_CHANNEL_HISTORY_TOOL_NAME
from the_one.tools.connector_lookup import FIND_PLATFORM_DESTINATION_TOOL_NAME
from the_one.tools.connector_send import SEND_TO_PLATFORM_CHANNEL_TOOL_NAME

# A narrowed built-in whitelist that fits a 16384 window's budget; the full built-in set
# (every tool enabled) does not at 3.5 bytes per token (see the leg's AC12b table).
SMALL_TOOLSET = (
    "send_to_platform_channel",
    "find_platform_destination",
    "fetch_channel_history",
    "read_file",
    "list_dir",
    "fetch_url",
)
CONNECTOR_TRIO = {
    SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
    FIND_PLATFORM_DESTINATION_TOOL_NAME,
    FETCH_CHANNEL_HISTORY_TOOL_NAME,
}


@pytest.fixture(autouse=True)
def _clean_exposure_env(monkeypatch):
    monkeypatch.delenv(FRACTION_ENV, raising=False)
    monkeypatch.delenv(CEILING_ENV, raising=False)


# ── AC2: exposure_defaults ────────────────────────────────────────────────


def test_defaults_without_environment():
    assert exposure_defaults() == (0.25, 8000)


def test_defaults_read_the_environment_at_call_time(monkeypatch):
    monkeypatch.setenv(FRACTION_ENV, "0.5")
    monkeypatch.setenv(CEILING_ENV, "1234")
    assert exposure_defaults() == (0.5, 1234)
    monkeypatch.setenv(FRACTION_ENV, "0.1")
    assert exposure_defaults()[0] == 0.1


def test_fraction_is_clamped_to_one(monkeypatch):
    monkeypatch.setenv(FRACTION_ENV, "7")
    assert exposure_defaults()[0] == 1.0


def test_fraction_zero_is_kept_and_disables_exposure(monkeypatch):
    monkeypatch.setenv(FRACTION_ENV, "0")
    assert exposure_defaults()[0] == 0.0
    exposure, to_add = decide_exposure(
        window_known=True,
        window=100_000,
        bytes_per_token=4.0,
        starting=[{"name": "a"}],
        candidates=[{"name": "b"}],
    )
    assert exposure.decided is False and to_add == [] and exposure.budget == 0


@pytest.mark.parametrize("bad", ["abc", "-0.5", "nan", ""])
def test_a_bad_fraction_falls_back_with_a_warning(monkeypatch, caplog, bad):
    monkeypatch.setenv(FRACTION_ENV, bad)
    with caplog.at_level(logging.WARNING, logger="the_one.agent.tool_exposure"):
        assert exposure_defaults()[0] == 0.25
    assert bool(caplog.records) is (bad != "")


@pytest.mark.parametrize("bad", ["abc", "-5", "1.5"])
def test_a_bad_ceiling_falls_back_with_a_warning(monkeypatch, caplog, bad):
    monkeypatch.setenv(CEILING_ENV, bad)
    with caplog.at_level(logging.WARNING, logger="the_one.agent.tool_exposure"):
        assert exposure_defaults()[1] == 8000
    assert caplog.records


# ── The pure decision ─────────────────────────────────────────────────────


def _s(name: str, pad: int = 0) -> dict:
    return {"name": name, "description": "x" * pad, "parameters": {}}


def test_estimate_is_the_json_bytes_over_density_rounded_up():
    start, cand = [_s("a")], [_s("b", 100)]
    exposure, to_add = decide_exposure(
        window_known=True,
        window=16384,
        bytes_per_token=3.5,
        starting=start,
        candidates=cand,
    )
    assert exposure.estimate == math.ceil(len(json.dumps(start + cand).encode()) / 3.5)
    assert exposure.budget == 4096 and exposure.window == 16384 and exposure.window_known
    assert exposure.decided is True and to_add == cand


def test_budget_is_min_of_fraction_and_ceiling():
    args = dict(bytes_per_token=4.0, starting=[], candidates=[])
    assert decide_exposure(window_known=True, window=16384, **args)[0].budget == 4096
    assert decide_exposure(window_known=True, window=200_000, **args)[0].budget == 8000
    assert decide_exposure(window_known=True, window=4096, **args)[0].budget == 1024


def test_over_budget_is_not_exposed_and_adds_nothing():
    big = [_s("b", 5000)]
    exposure, to_add = decide_exposure(
        window_known=True, window=4096, bytes_per_token=4.0, starting=[], candidates=big
    )
    assert exposure.decided is False and to_add == []
    assert exposure.estimate > exposure.budget


def test_an_estimate_equal_to_the_budget_fits():
    start = [_s("a")]
    est = decide_exposure(
        window_known=True, window=16384, bytes_per_token=4.0, starting=start, candidates=[]
    )[0].estimate
    exposure, _ = decide_exposure(
        window_known=True,
        window=16384,
        bytes_per_token=4.0,
        starting=start,
        candidates=[],
        fraction=est / 16384,
        ceiling=est,
    )
    assert exposure.budget == est and exposure.decided is True


def test_an_unknown_window_is_never_exposed_and_records_no_budget():
    exposure, to_add = decide_exposure(
        window_known=False, window=999_999, bytes_per_token=4.0, starting=[], candidates=[_s("b")]
    )
    assert exposure == ToolExposure(False, None, exposure.estimate, False, None)
    assert exposure.estimate > 0 and to_add == []


# ── Factory harness ───────────────────────────────────────────────────────


class InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, AgentConfig] = {}

    async def list_agents(self) -> list[str]:
        return sorted(self._data)

    async def load(self, name: str) -> AgentConfig:
        return self._data[name]

    async def save(self, config: AgentConfig) -> None:
        self._data[config.name] = config

    async def exists(self, name: str) -> bool:
        return name in self._data


class WindowLLM(FakeLLM):
    """A provider double with real provider state and a pinned (or resolving) window."""

    def __init__(
        self,
        *,
        window: int = 16384,
        known: bool = True,
        bytes_per_token: float = 3.5,
        resolve_delay: float = 0.0,
        resolve_raises: bool = False,
        resolve_sets_known: bool = False,
    ) -> None:
        super().__init__([])
        self._init_provider_state()
        self.max_context_tokens = window
        self.context_window_known = known
        self.bytes_per_token = bytes_per_token
        self._delay = resolve_delay
        self._raises = resolve_raises
        self._sets_known = resolve_sets_known
        self.resolver_finished = False

    async def _resolve_max_context_tokens(self) -> None:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises:
            raise RuntimeError("metadata unreachable")
        if self._sets_known:
            self.context_window_known = True
        self.resolver_finished = True


class _Everyone:
    def __contains__(self, _name: object) -> bool:
        return True


@pytest.fixture
def build(monkeypatch):
    """``await build(llm, bound=True, **config)`` -> an Agent built by the real factory over
    the real built-in tools, with ``llm`` as its provider."""
    stack = ExitStack()

    async def _build(llm: Any, *, bound: bool = True, name: str = "a", **config: Any):
        async def _names(_conn):
            return _Everyone() if bound else set()

        monkeypatch.setattr("the_one.db.repositories.agent_names_in_use", _names)
        store = InMemoryStore()
        config.setdefault("enabled_tools", list(SMALL_TOOLSET))  # None means every built-in
        await store.save(AgentConfig(name=name, provider_config_id="p", llm_model="m", **config))
        repo = AsyncMock()
        repo.get = AsyncMock(
            return_value=LLMProviderConfig(
                id="p", name="P", type="ollama", base_url="http://localhost:11434/v1"
            )
        )
        tool_repo = AsyncMock()
        tool_repo.list = AsyncMock(return_value=[])
        rules = AsyncMock()
        rules.list_for_agent = AsyncMock(return_value=[])
        with (
            patch("the_one.agent.factory.get_provider", lambda *_a, **_k: llm),
            patch("the_one.agent.factory.settings") as settings,
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch("the_one.db.repositories.LLMProviderRepository", return_value=repo),
            patch("the_one.db.repositories.ToolConfigRepository", return_value=tool_repo),
            patch("the_one.db.repositories.AgentRuleRepository", return_value=rules),
            patch(
                "the_one.db.repositories.AgentNoteRepository",
                return_value=AsyncMock(list_if_enabled=AsyncMock(return_value=None)),
            ),
            patch("the_one.agent.prompt_layers.load_secrets_block", AsyncMock(return_value="")),
        ):
            settings.agents_dir = Path("/tmp/test-agents")
            settings.data_dir = Path("/tmp/test-data")
            settings.ensure_dirs = lambda: None
            return await AgentFactory(store=store, tool_providers=[BuiltinToolProvider()]).create(
                name
            )

    yield _build
    stack.close()


def _names(schemas: list[dict]) -> list[str]:
    return [s["name"] for s in schemas]


def _expected_discovery(agent, *, bound: bool) -> list[dict]:
    seeds = ["current_time"]
    if bound:
        seeds = [
            SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
            FIND_PLATFORM_DESTINATION_TOOL_NAME,
            "current_time",
        ]
    return [SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] + [
        agent.tools.get(n).to_schema() for n in seeds if n in agent.tools.tool_names
    ]


# ── AC3: the bounded lookup ───────────────────────────────────────────────


async def test_a_slow_resolver_gives_discovery_and_still_finishes(build, monkeypatch):
    monkeypatch.setattr(factory_module, "WINDOW_LOOKUP_TIMEOUT_S", 0.05)
    llm = WindowLLM(known=False, resolve_delay=0.3, resolve_sets_known=True)
    agent = await build(llm)
    assert agent.tool_exposure.decided is False
    assert agent.tool_exposure.window_known is False and agent.tool_exposure.budget is None
    assert llm._max_context_tokens_resolved is False  # not cached as resolved by the timeout
    assert factory_module._WINDOW_LOOKUP_TASKS  # held by a strong reference
    pending = list(factory_module._WINDOW_LOOKUP_TASKS)
    await asyncio.gather(*pending)  # no "Task was destroyed but pending" at teardown
    await asyncio.sleep(0)
    assert llm.resolver_finished and llm.context_window_known is True
    assert llm._max_context_tokens_resolved is True
    assert not factory_module._WINDOW_LOOKUP_TASKS  # discarded by the done callback
    assert _names(agent._compute_visible_schemas()) == _names(
        _expected_discovery(agent, bound=True)
    )


async def test_a_raising_resolver_gives_discovery(build):
    agent = await build(WindowLLM(known=False, resolve_raises=True))
    assert agent.tool_exposure.decided is False and agent.tool_exposure.window_known is False


async def test_a_double_that_skips_the_provider_init_gives_discovery(build):
    agent = await build(FakeLLM([]))  # no `_max_context_tokens_resolved` attribute at all
    assert agent.tool_exposure.decided is False
    assert agent.tool_exposure.window_known is False
    assert agent.tool_exposure.window is None and agent.tool_exposure.budget is None
    assert agent.tool_exposure.estimate > 0


async def test_a_late_failure_leaves_no_unretrieved_exception(build, monkeypatch):
    monkeypatch.setattr(factory_module, "WINDOW_LOOKUP_TIMEOUT_S", 0.01)
    llm = WindowLLM(known=False, resolve_delay=0.05, resolve_raises=True)
    await build(llm)
    await asyncio.gather(*list(factory_module._WINDOW_LOOKUP_TASKS), return_exceptions=True)
    await asyncio.sleep(0)
    assert not factory_module._WINDOW_LOOKUP_TASKS


# ── AC4-AC7: the decision and the seeding ─────────────────────────────────


async def test_unknown_window_is_byte_identical_discovery(build):
    agent = await build(WindowLLM(known=False))
    assert agent._compute_visible_schemas() == _expected_discovery(agent, bound=True)
    assert agent.tool_exposure.decided is False and agent.tool_exposure.window_known is False


async def test_over_budget_is_byte_identical_discovery(build):
    agent = await build(WindowLLM(window=2000))  # budget 500
    assert agent._compute_visible_schemas() == _expected_discovery(agent, bound=True)
    e = agent.tool_exposure
    assert e.decided is False and e.window_known is True
    assert e.budget == 500 and e.estimate > 500 and e.window == 2000


async def test_fraction_zero_is_byte_identical_discovery(build, monkeypatch):
    monkeypatch.setenv(FRACTION_ENV, "0")
    agent = await build(WindowLLM())
    assert agent._compute_visible_schemas() == _expected_discovery(agent, bound=True)
    assert agent.tool_exposure.decided is False and agent.tool_exposure.budget == 0


@pytest.mark.parametrize("window", [4096, 8192])
async def test_small_ollama_windows_stay_on_discovery(build, window):
    """The divert criterion: an all-on-like agent on a 4k or 8k window is not exposed."""
    agent = await build(WindowLLM(window=window), enabled_tools=None)  # every built-in tool
    assert agent._compute_visible_schemas() == _expected_discovery(agent, bound=True)
    assert agent.tool_exposure.decided is False
    assert agent.tool_exposure.budget == window // 4


async def test_a_known_window_exposes_every_enabled_tool_in_registry_order(build):
    agent = await build(WindowLLM(), bound=True)
    e = agent.tool_exposure
    assert e.decided is True and e.window == 16384 and e.budget == 4096
    assert e.estimate <= e.budget
    seeds = [
        SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
        FIND_PLATFORM_DESTINATION_TOOL_NAME,
        "current_time",
    ]
    rest = [n for n in agent.tools.tool_names if n not in seeds and n != "search_tools"]
    visible = agent._compute_visible_schemas()
    assert _names(visible) == ["search_tools", "continue", *seeds, *rest]
    assert visible[: 2 + len(seeds)] == _expected_discovery(agent, bound=True)
    assert visible[2 + len(seeds) :] == [agent.tools.get(n).to_schema() for n in rest]
    assert CONNECTOR_TRIO <= set(_names(visible))  # a bound agent gets all three


async def test_an_unbound_agent_gets_none_of_the_connector_tools(build):
    agent = await build(WindowLLM(), bound=False)
    assert agent.tool_exposure.decided is True
    assert not CONNECTOR_TRIO & set(_names(agent._compute_visible_schemas()))
    # ... though they stay in the registry, found through search_tools as before
    assert CONNECTOR_TRIO <= set(agent.tools.tool_names)


async def test_a_whitelisted_agent_exposes_only_what_it_enabled(build):
    agent = await build(WindowLLM(), enabled_tools=["read_file"])
    names = _names(agent._compute_visible_schemas())
    assert "read_file" in names and "shell" not in names and "current_time" in names


async def test_reset_keeps_the_full_seed(build):
    agent = await build(WindowLLM())
    before = agent._compute_visible_schemas()
    agent.reset()
    assert agent._compute_visible_schemas() == before


async def test_the_record_is_set_on_every_agent(build):
    agent = await build(WindowLLM(known=False))
    assert isinstance(agent.tool_exposure, ToolExposure)


# ── AC8: the wording follows the decision ─────────────────────────────────


async def test_an_exposed_agent_gets_the_preloaded_wording(build):
    agent = await build(WindowLLM())
    assert PRELOADED_TOOL_DISCOVERY in agent.system_prompt
    assert "You start with `search_tools`" not in agent.system_prompt
    assert PRELOADED_KB_LINE not in agent.system_prompt  # no knowledge base attached
    assert "All your tools are available now" not in agent.degraded_system_prompt


async def test_a_discovery_agent_keeps_todays_wording(build):
    agent = await build(WindowLLM(known=False))
    assert agent.system_prompt.startswith(
        render_platform(Capabilities(knowledge=False, exec_tools=False))
    )
    assert "All your tools are available now" not in agent.system_prompt


# ── AC9: the settle re-render keeps the wording ───────────────────────────


class _Registry:
    tool_names = ["search_tools", "shell", "kb__x__search"]


class _LiveAgent:
    def __init__(self, exposure):
        from the_one.llm.base import Message

        self.tools = _Registry()
        self.llm = None
        self.tool_exposure = exposure
        self.system_prompt = "old"
        self.degraded_system_prompt = "old"
        self.messages = [Message.system("old")]


@pytest.mark.parametrize("preloaded", [True, False])
@pytest.mark.parametrize("rules_read_fails", [False, True])
async def test_apply_pending_revision_keeps_the_wording(monkeypatch, preloaded, rules_read_fails):
    from the_one.self_configuration import pending

    pending.clear_for_test()
    seen: dict[str, Any] = {}

    async def fake_build(agent_name, persona, **kw):
        seen.update(kw)
        if rules_read_fails:
            raise RuntimeError("rules unreadable")
        caps = Capabilities(
            knowledge=kw["knowledge"],
            exec_tools=kw["exec_tools"],
            tools_preloaded=kw["tools_preloaded"],
        )
        return pending.SystemPrompts(render_platform(caps) + persona, "free")

    monkeypatch.setattr(pending, "build_system_prompts", fake_build)
    monkeypatch.setattr(pending, "load_secrets_block", AsyncMock(return_value=""))
    monkeypatch.setattr(pending, "time_tool_available", AsyncMock(return_value=False))
    exposure = ToolExposure(preloaded, 4096, 100, True, 16384)
    agent = _LiveAgent(exposure)
    pending.record("a", system_prompt="PERSONA")
    assert await pending.apply_pending_revision("a", agent) is True
    text = agent.system_prompt
    assert ("All your tools are available now" in text) is preloaded
    assert ("You start with `search_tools`" in text) is (not preloaded)
    if preloaded:
        assert PRELOADED_KB_LINE in text  # the registry holds a knowledge-base tool
    assert text.endswith("PERSONA")
    if not rules_read_fails:
        assert seen["tools_preloaded"] is preloaded


async def test_apply_pending_revision_without_a_record_is_discovery(monkeypatch):
    from the_one.self_configuration import pending

    pending.clear_for_test()
    monkeypatch.setattr(pending, "time_tool_available", AsyncMock(return_value=False))
    monkeypatch.setattr(pending, "load_secrets_block", AsyncMock(return_value=""))
    monkeypatch.setattr(
        pending, "build_system_prompts", AsyncMock(side_effect=RuntimeError("no rules"))
    )
    agent = _LiveAgent(None)
    del agent.tool_exposure
    pending.record("b", system_prompt="P")
    await pending.apply_pending_revision("b", agent)
    assert "You start with `search_tools`" in agent.system_prompt
