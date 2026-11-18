"""GleepGlorp's in-memory agent config (M36 F1 L03, DD1; L06 memory and web).

GleepGlorp has no ``agents`` row; the factory builds it from its settings. The config
carries a provider, a model, the retention window, the notes switch (the ``memory``
setting) and, behind the ``web_access`` setting, the two web tools: no other tools beyond
the whitelist-exempt ``current_time``, and no knowledge bases, MCP servers or routines.
"""

from __future__ import annotations

from the_one.agent.config import AgentConfig
from the_one.gleepglorp.settings import GleepGlorpSettings
from the_one.naming import GLEEPGLORP_AGENT_NAME


def gleepglorp_config(settings: GleepGlorpSettings) -> AgentConfig:
    """The factory drops ``web_search`` from the whitelist when no engine is set up
    (``the_one.gleepglorp.web.search_configured``), since only it sees the tool configs."""
    web_tools = ["fetch_url", "web_search"] if settings.web_access else []
    return AgentConfig(
        name=GLEEPGLORP_AGENT_NAME,
        provider_config_id=settings.provider_config_id,
        llm_model=settings.model or "",
        system_prompt="",
        enabled_tools=web_tools,
        disabled_tools=[],
        notes_enabled=settings.memory,
        rich_visuals=False,
        routines_self_config_enabled=False,
        chat_history_retention_days=settings.retention_days,
    )
