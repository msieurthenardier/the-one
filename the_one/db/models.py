"""Pydantic models for database entities (KnowledgeBase, KBItem, MCPSource, ChatSession)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, field_validator

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

    @field_validator("api_key", mode="after")
    @classmethod
    def _normalize_api_key(cls, value: str | None) -> str | None:
        """Strip whitespace and collapse empty results to ``None``.

        This is the canonical-form contract for ``api_key``. Callers
        (``/test``, ``/models``, chat-create, the SDK constructors) MUST
        NOT re-strip — the stored value is already canonical, so any
        downstream ``.strip()`` is a sign that an old code path is
        defending against a bug that's already fixed at this layer.

        The ``__MASKED__`` sentinel path in
        ``the_one/interfaces/web/api.py::update_provider`` runs BEFORE
        this validator (it overwrites ``data["api_key"]`` with the
        existing-stored value, which is itself already canonical), so the
        sentinel literal is never asked to round-trip through this
        validator. Verified by ``test_masked_sentinel_path_unchanged``.
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


# Pin the explicit ``Literal`` arg-set to ``PROVIDER_TYPES`` at import time so
# any future drift between ``_provider_types.py`` and the model annotation
# trips immediately rather than at first DB write.
assert set(get_args(LLMProviderConfig.model_fields["type"].annotation)) == set(PROVIDER_TYPES), (
    "LLMProviderConfig.type Literal drifted from PROVIDER_TYPES — update both in lockstep."
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
    """An MCP source definition — operator-registered server entry."""

    id: str
    name: str
    type: Literal["stdio", "streamable-http"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def merged_config(self) -> dict[str, Any]:
        """Return a flat dict combining `config` and `secrets`.

        Used by F2's bearer-token-from-config / env-var resolution path at
        MCP-process spawn time. F4's resolver path keeps the split — do not
        call this method from the resolver.

        Secrets win on key collision so an operator-marked-sensitive field
        overrides any plaintext default of the same name.
        """
        return {**self.config, **self.secrets}


# NOTE: ``CONNECTOR_TYPES`` from ``the_one.db._connector_types`` is intentionally
# NOT imported here yet. ``CONNECTOR_TYPES`` is an empty tuple in flight 01
# (mission 10) — a ``Literal[*()]`` is invalid Python syntax, and a no-op
# pinning assert against an empty tuple is misleading. Flight 08 (Discord)
# adds the first real connector type, at which point ``ConnectorAccount.type``
# narrows to ``Literal[...]`` and the canonical
# ``assert set(get_args(...)) == set(CONNECTOR_TYPES)`` invariant lands —
# paralleling ``LLMProviderConfig``'s assert above.
class ConnectorAccount(BaseModel):
    """A connector account — operator-registered third-party-platform identity.

    Mirrors :class:`MCPSource` shape. Stored in ``connector_accounts``
    (v13 table; v14 added the ``name`` column to match MCPSource).

    ``type`` is currently :class:`str` (unconstrained). When the first real
    connector type lands in flight 08, the spec is to narrow this to
    ``Literal[...]`` and add a ``get_args``-based pinning assert against
    ``CONNECTOR_TYPES`` from ``the_one.db._connector_types``, paralleling
    :class:`LLMProviderConfig`'s assert at the top of this module.
    """

    id: str
    name: str
    type: str  # narrows to Literal in flight 08 when CONNECTOR_TYPES is non-empty
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    idle_timeout_seconds: int | None = None
    session_continuation_seconds: int | None = None  # M10 F03 L01
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    @field_validator("idle_timeout_seconds")
    @classmethod
    def _validate_idle_timeout_seconds(cls, value: int | None) -> int | None:
        """Bound the per-account pool idle TTL to ``[1, 604800]`` seconds.

        ``None`` means "no per-account override — fall through to the env
        var / default in ``_resolve_ttl_seconds``." The 7-day upper bound
        catches the milliseconds-vs-seconds typo (a value like
        ``31_536_000_000`` is suspiciously high for "keep the connection
        warm"); the lower bound rejects zero / negative which would make
        the warm entry immediately reapable.
        """
        if value is None:
            return value
        if not (1 <= value <= 604800):
            raise ValueError(
                "idle_timeout_seconds must be between 1 and 604800 seconds (7 days)"
            )
        return value

    @field_validator("session_continuation_seconds")
    @classmethod
    def _validate_session_continuation_seconds(cls, value: int | None) -> int | None:
        """Bound the per-account chat-session continuation window to
        ``[1, 604800]`` seconds.

        ``None`` means "no per-account override — fall through to the
        env var / default in
        ``the_one.connectors._session._resolve_continuation_seconds``"
        (the resolver lands in F3 L3; the field exists from this leg
        so the repository round-trip is complete before the resolver
        consumes it).

        Same `1 ≤ value ≤ 604800` bounds as ``idle_timeout_seconds``
        (the 7-day upper bound catches the ms-vs-s typo; the lower
        bound rejects zero / negative). These two are independent
        timeouts — pool warm-entry TTL vs. chat-session continuation
        window — that happen to share an envelope.
        """
        if value is None:
            return value
        if not (1 <= value <= 604800):
            raise ValueError(
                "session_continuation_seconds must be between 1 and 604800 seconds (7 days)"
            )
        return value


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
    """A chat session with message history.

    Mission 10 Flight 3 Leg 1: connector-keyed sessions add the
    (platform, connector_account_id, channel_id, thread_id, peer_id)
    quintuple plus a JSON metadata column and a last_inbound_at
    timestamp. All seven default to None for non-connector sessions
    (back-compat) and are populated by the inbound dispatcher
    (leg 4) for connector-driven sessions.

    The (platform, connector_account_id, channel_id, COALESCE(thread_id, ''))
    4-tuple is the lookup key consumed by leg 3's resolver against the
    partial expression index ``idx_chat_sessions_external_key``.
    ``peer_id`` is stored for audit and future per-peer-scoped sessions
    (Flight 6 territory) but is NOT part of the lookup key.
    """

    id: str
    agent_name: str | None = None
    title: str = "New chat"
    messages: str = "[]"  # JSON-encoded via codec
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    # M10 F03 L01: connector-session external key + metadata.
    # ``session_metadata`` is a dict at the model layer; the repository
    # encodes via ``json.dumps`` on write and decodes via ``json.loads``
    # on read (parallel to how ``messages`` is a JSON-encoded string in
    # the column but a Python list at the codec layer).
    platform: str | None = None
    connector_account_id: str | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    peer_id: str | None = None
    session_metadata: dict[str, Any] | None = None
    last_inbound_at: str | None = None
