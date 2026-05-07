"""Pydantic models for database entities (KnowledgeBase, KBItem, MCPSource, ChatSession)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, get_args

from pydantic import BaseModel, Field

from the_one.db._provider_types import PROVIDER_TYPES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LLMProviderConfig(BaseModel):
    """An LLM provider connection configuration."""

    id: str
    name: str
    # NOTE: keep this ``Literal[...]`` spelled out explicitly — Pydantic /
    # static type checkers cannot consume ``Literal[*PROVIDER_TYPES]``
    # unpacking. The module-load assertion below pins the two in sync.
    type: Literal["ollama", "openai-compatible", "openai", "anthropic", "mock", "openrouter"]
    base_url: str
    api_key: str | None = None
    config: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


# Pin the explicit ``Literal`` arg-set to ``PROVIDER_TYPES`` at import time so
# any future drift between ``_provider_types.py`` and the model annotation
# trips immediately rather than at first DB write.
assert set(get_args(LLMProviderConfig.model_fields["type"].annotation)) == set(
    PROVIDER_TYPES
), (
    "LLMProviderConfig.type Literal drifted from PROVIDER_TYPES — "
    "update both in lockstep."
)


class KnowledgeBase(BaseModel):
    """A knowledge base — stub for future RAG pipeline."""

    id: str
    name: str
    description: str = ""
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class KBItem(BaseModel):
    """An item within a knowledge base (file or URL)."""

    id: str
    kb_id: str
    parent_id: str | None = None
    type: Literal["file", "url"]
    path_or_url: str
    status: str = "pending"
    created_at: str = Field(default_factory=_now_iso)


class MCPSource(BaseModel):
    """An MCP source definition — stub for future protocol connection."""

    id: str
    name: str
    type: Literal["stdio", "sse"]
    config: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class ToolConfig(BaseModel):
    """A tool-level config row — operator-set defaults for a built-in tool.

    Mirrors `MCPSource` shape but keyed by `name` (the tool's stable
    identifier). The resolver composes this with a per-agent override
    dict from `AgentConfig.tool_overrides` at `AgentFactory.create()`
    time (session-bound; mid-session edits do not affect running agents).

    `enabled` (added in schema v9) is operator-set tool-level on/off.
    Disabled tools are filtered out of the registry at L1's enforcement
    point — independent of per-agent enabled_tools / disabled_tools.
    """

    name: str
    config: dict = Field(default_factory=dict)
    enabled: bool = True
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class ChatSession(BaseModel):
    """A chat session with message history."""

    id: str
    agent_name: str | None = None
    title: str = "New chat"
    messages: str = "[]"  # JSON-encoded via codec
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
