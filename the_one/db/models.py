"""Pydantic models for database entities (KnowledgeBase, KBItem, MCPSource, ChatSession)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, field_validator

from the_one.db._provider_types import PROVIDER_TYPES


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LLMProviderConfig(BaseModel):
    """An LLM provider connection configuration."""

    id: str
    name: str
    # NOTE: keep this ``Literal[...]`` spelled out explicitly — Pydantic /
    # static type checkers cannot consume ``Literal[*PROVIDER_TYPES]``
    # unpacking. The module-load assertion below pins the two in sync.
    type: Literal[
        "ollama",
        "openai-compatible",
        "openai",
        "anthropic",
        "mock",
        "openrouter",
        "anthropic-plan",
    ]
    base_url: str
    api_key: str | None = None
    config: dict = Field(default_factory=dict)
    # M19 F01 L01 — OAuth-managed credential blob for ``anthropic-plan``
    # providers (access_token / refresh_token / token_expires_at / scope /
    # token_type). Encrypted at rest as a whole-dict Fernet blob by
    # ``LLMProviderRepository`` (DD-2); stripped from every API response
    # (``_provider_response`` exposes an ``oauth_active`` boolean instead).
    secrets: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

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
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class KBItem(BaseModel):
    """An item within a knowledge base (file or URL)."""

    id: str
    kb_id: str
    parent_id: str | None = None
    type: Literal["file", "url"]
    path_or_url: str
    status: str = "pending"
    created_at: str = Field(default_factory=now_iso)


class MCPSource(BaseModel):
    """An MCP source definition — operator-registered server entry."""

    id: str
    name: str
    type: Literal["stdio", "streamable-http"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def merged_config(self) -> dict[str, Any]:
        """Return a flat dict combining `config` and `secrets`.

        Used by F2's bearer-token-from-config / env-var resolution path at
        MCP-process spawn time. F4's resolver path keeps the split — do not
        call this method from the resolver.

        Secrets win on key collision so an operator-marked-sensitive field
        overrides any plaintext default of the same name.
        """
        return {**self.config, **self.secrets}


# Hoisted module-level so the F7 L7 Studio editor (and any future routing UI)
# can import the enum without going through the validator.
VALID_ROUTING_SCOPES = frozenset({"channel", "thread", "dm", "peer"})


class Connector(BaseModel):
    """A connector — operator-registered third-party-platform identity.

    Mirrors :class:`MCPSource` shape. Stored in ``connectors``
    (v13 table originally named ``connector_accounts``; v14 added the
    ``name`` column to match MCPSource; v19 added the
    ``CHECK (type IN ('discord', 'stub'))`` constraint via the F8 L2
    table-rename ceremony; v23 renamed the table to ``connectors`` and
    the ``Connector`` Pydantic class to ``Connector`` via M11
    F11 L1).

    ``type`` is narrowed to ``Literal["discord", "stub"]`` (F8 L2). The
    module-load assertion below pins the Literal arg-set to
    ``_CONNECTOR_TYPES`` (this module's own frozen constant, Mission 23
    Flight 1) so the two cannot drift, paralleling
    :class:`LLMProviderConfig`'s assert at the top of this module.
    """

    id: str
    name: str
    # NOTE: keep this ``Literal[...]`` spelled out explicitly — Pydantic /
    # static type checkers cannot consume ``Literal[*_CONNECTOR_TYPES]``
    # unpacking. The module-load assertion below pins the two in sync.
    type: Literal["discord", "stub"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    idle_timeout_seconds: int | None = None
    session_continuation_seconds: int | None = None  # M10 F03 L01
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @field_validator("config", mode="after")
    @classmethod
    def _validate_connector_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Mission 23 Flight 2 DD-2: compact reserved-key validator.

        Replaces the pre-reset 430-line routing/ACL schema. Unknown
        top-level keys are rejected; ``default_agent`` is validated for
        shape only — a dangling reference (renamed/deleted agent) is a
        doctor-reported condition, not a validator error (DD-2
        trade-off: agents are project-local, not worth the FK-style
        coupling).
        """
        allowed = {"default_agent", "channel_map", "allowlist", "always_listen", "enabled"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Connector.config has unknown key(s): {sorted(unknown)}")
        if "default_agent" in value and not isinstance(value["default_agent"], str):
            raise ValueError("Connector.config['default_agent'] must be a string")
        if "enabled" in value and not isinstance(value["enabled"], bool):
            raise ValueError("Connector.config['enabled'] must be a bool")
        if "channel_map" in value:
            channel_map = value["channel_map"]
            if not isinstance(channel_map, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in channel_map.items()
            ):
                raise ValueError("Connector.config['channel_map'] must be a dict[str, str]")
        if "allowlist" in value:
            allowlist = value["allowlist"]
            if not isinstance(allowlist, dict) or set(allowlist) - {"peers", "channels"}:
                raise ValueError(
                    "Connector.config['allowlist'] must be a dict with only 'peers'/'channels' keys"
                )
            for axis in ("peers", "channels"):
                if axis in allowlist and (
                    not isinstance(allowlist[axis], list)
                    or not all(isinstance(v, str) for v in allowlist[axis])
                ):
                    raise ValueError(f"Connector.config['allowlist'][{axis!r}] must be list[str]")
        if "always_listen" in value:
            always_listen = value["always_listen"]
            if not isinstance(always_listen, list) or not all(
                isinstance(v, str) for v in always_listen
            ):
                raise ValueError("Connector.config['always_listen'] must be list[str]")
        return value


# Mission 23 Flight 1 (backend-removal leg): ``db/_connector_types.py`` is
# deleted with the connector package. Its ``CONNECTOR_TYPES`` derivation fed
# TWO independent consumers with different lifecycles — this model's
# ``Literal`` (a living model, changes when Flight 2 changes the type set)
# and ``db/schema.py``'s frozen historical DDL (append-only, never changes
# once written). Collapsing them onto one shared import was the coupling;
# each now owns its own constant. This one is the model's own — deliberately
# duplicated, not re-imported.
_CONNECTOR_TYPES = ("discord", "stub")

# Pin the explicit ``Literal`` arg-set to ``_CONNECTOR_TYPES`` at import time
# so any future drift trips immediately rather than at first DB write.
# M10 F8 L2 — paralleling ``LLMProviderConfig``'s assert above (mirrors the
# M07 ``'mock'``-in-``PROVIDER_TYPES`` precedent; ``'stub'`` is the test-only
# carve-out formerly documented in ``_connector_types.py``).
assert set(get_args(Connector.model_fields["type"].annotation)) == set(_CONNECTOR_TYPES), (
    "Connector.type Literal drifted from _CONNECTOR_TYPES — update both in lockstep."
)


class AgentRevision(BaseModel):
    """A row in the ``agent_revisions`` revision log (M21 F02).

    One status-bearing table serves three consumers (DD1): the
    applied-revision log (F02 L01 — this leg), the pending-approval queue
    (L02), and restore provenance (L03). The full ``status`` / ``source``
    domains ship in the schema from v34, but L01 writes only
    ``status='applied', source='self'`` — a direct self-revision recorded
    with its before-image (``base_value``) and after-image
    (``proposed_value``). No encryptor: ``description`` / ``system_prompt``
    are plaintext columns, so the log holds no secret material.

    An ``applied`` row is resolved at creation, so ``resolved_at`` equals
    ``created_at``. ``restored_from`` (a self-FK to the revision a restore
    reinstated) is L03's; it is ``None`` here.
    """

    id: str
    agent_name: str
    field: Literal["description", "system_prompt"]
    proposed_value: str
    base_value: str
    status: Literal["applied", "pending", "dismissed", "superseded"]
    source: Literal["self", "restore", "external"]
    # M21 F03 L02 (DD3): the external credential identifier for ``external``
    # rows, ``None`` for ``self`` / ``restore``. Safe to store and log by
    # Mission 20's id/secret split — this is the credential IDENTIFIER, never
    # the secret.
    source_principal: str | None = None
    restored_from: str | None = None
    created_at: str
    resolved_at: str | None = None


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
    secrets: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def merged_config(self) -> dict[str, Any]:
        """Return a flat dict combining `config` and `secrets`.

        Used by the agent factory's resolver feed (`factory.py`) so the
        tool-policy resolver / `build_search_backend` receive the REAL
        decrypted secret values (api keys), not the masked admin-GET view.

        Secrets win on key collision so an operator-marked-secret field
        overrides any plaintext default of the same name. Mirrors
        `MCPSource.merged_config()`.
        """
        return {**self.config, **self.secrets}


class ChatSession(BaseModel):
    """A chat session with message history.

    Mission 10 Flight 3 Leg 1: connector-keyed sessions add the
    (platform, connector_id, channel_id, thread_id, peer_id)
    quintuple plus a JSON metadata column and a last_inbound_at
    timestamp. All seven default to None for non-connector sessions
    (back-compat) and are populated by the inbound dispatcher
    (leg 4) for connector-driven sessions.

    The (platform, connector_id, channel_id, COALESCE(thread_id, ''))
    4-tuple is the lookup key consumed by leg 3's resolver against the
    partial expression index ``idx_chat_sessions_external_key``.
    ``peer_id`` is stored for audit and future per-peer-scoped sessions
    (Flight 6 territory) but is NOT part of the lookup key.
    """

    id: str
    agent_name: str | None = None
    title: str = "New chat"
    messages: str = "[]"  # JSON-encoded via codec
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    # M10 F03 L01: connector-session external key + metadata.
    # ``session_metadata`` is a dict at the model layer; the repository
    # encodes via ``json.dumps`` on write and decodes via ``json.loads``
    # on read (parallel to how ``messages`` is a JSON-encoded string in
    # the column but a Python list at the codec layer).
    platform: str | None = None
    connector_id: str | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    peer_id: str | None = None
    session_metadata: dict[str, Any] | None = None
    last_inbound_at: str | None = None
