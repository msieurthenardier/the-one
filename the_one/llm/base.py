from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False
    metadata: dict[str, Any] | None = None  # F5 L3: generic cross-provider payload


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_result: ToolResult | None = None
    usage: TokenUsage | None = None
    # M10 F03 L02: visibility tag for two-layer connector-session model.
    # None = no operator-only restriction (platform-visible for connector
    # sessions; the only layer for non-connector sessions).
    # "operator" = operator-console only; never propagated to the platform.
    # Constant published as ``OPERATOR_VISIBILITY`` from
    # ``the_one.connectors`` — use it at every production set site
    # (dispatcher in F3 L4; platform-send tool in F4; Chat-UI
    # operator-input path in F5).
    visibility: str | None = None
    # M11 F06 L01: peer_name attribution for connector-attached sessions.
    # None = no peer attribution (operator-typed, agent-internal, or
    # non-connector session — the default for every Message constructed
    # without an explicit peer_name kwarg). When non-None, this is the
    # platform's display name for the peer who sent the inbound message
    # (e.g. a Discord username); the Chat UI renders it as the bubble's
    # attribution. The codec emits the key only when non-None — pre-F6
    # rows decode with peer_name=None unchanged. Meaningful only on
    # Role.USER messages; assistant/tool messages leave it at the default.
    # Invariant (per dispatcher contract): when populated, the string is
    # non-empty — the Discord plugin falls back to ``str(user.id)`` when
    # display_name is blank (`_discord.py:218`).
    peer_name: str | None = None
    # M11 F07 L02: channel_id — platform-native channel identifier string
    # (e.g. a Discord channel snowflake; the convention is plugin-agnostic
    # and any connector plugin supplies its own platform-native id string).
    # The canonical key; the channel_name field below is the human-readable
    # label resolved from this id via the F3 discoverable-entities cache.
    # The pair travels together because the L4 provider projection uses the
    # name for the LLM prefix while the dispatcher's routing audit and the
    # F9 audit-log inspector use the id. The codec emits the key only when
    # non-None — pre-F7 rows decode with channel_id=None unchanged.
    # Meaningful only on Role.USER messages; assistant/tool messages leave
    # it at the default. Either field may be absent independently (cold-pool
    # case: id resolved but name not yet cached); the codec emits each
    # independently when non-None.
    channel_id: str | None = None
    # M11 F07 L02: channel_name — platform-resolved human-readable channel
    # label (e.g. a Discord channel name like "general"). Resolved from
    # channel_id via the F3 discoverable-entities cache by L3's
    # bind_channel_context; the L4 provider adapters project it as
    # `[from {peer_name} in #{channel_name}]: ...` on user-role content so
    # the engaged agent sees multi-user context naturally. Same back-compat
    # discipline as channel_id above (emit-when-non-None; legacy rows
    # decode to None). May be present without channel_id only in
    # corner-case malformed envelopes — the standard flow binds both
    # together; either may be absent independently (cold-pool case: id
    # resolved but name not yet cached). Meaningful only on Role.USER
    # messages; assistant/tool messages leave it at the default.
    channel_name: str | None = None

    @classmethod
    def system(cls, content: str, *, visibility: str | None = None) -> Message:
        return cls(role=Role.SYSTEM, content=content, visibility=visibility)

    @classmethod
    def user(
        cls,
        content: str,
        *,
        visibility: str | None = None,
        peer_name: str | None = None,
        channel_id: str | None = None,
        channel_name: str | None = None,
    ) -> Message:
        return cls(
            role=Role.USER,
            content=content,
            visibility=visibility,
            peer_name=peer_name,
            channel_id=channel_id,
            channel_name=channel_name,
        )

    @classmethod
    def assistant(
        cls,
        content: str,
        tool_calls: list[ToolCall] | None = None,
        usage: TokenUsage | None = None,
        *,
        visibility: str | None = None,
    ) -> Message:
        return cls(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=tool_calls or [],
            usage=usage,
            visibility=visibility,
        )

    @classmethod
    def tool(cls, result: ToolResult, *, visibility: str | None = None) -> Message:
        return cls(
            role=Role.TOOL,
            content=result.content,
            tool_result=result,
            visibility=visibility,
        )


def build_user_message_content(msg: Message) -> str:
    """Build the LLM-payload content string for a user message,
    projecting peer_name and channel_name as an inline bracket prefix.

    Format depends on which fields are set (all use ``is not None``,
    NOT truthiness — empty strings round-trip as-is per the
    ``message-additive-back-compat-via-emit-when-non-none`` convention):

    - peer_name + channel_name both set → ``[from {peer} in #{ch}]: {content}``
    - peer_name only                    → ``[from {peer}]: {content}``
    - channel_name only                 → ``[in #{ch}]: {content}``
    - neither set                       → ``{content}`` (byte-identical
      to pre-F6 + pre-F7 payload — legacy back-compat)

    Defensive: returns ``msg.content`` unchanged for any non-USER
    role (the projection is meaningful only on inbound user turns;
    assistant/tool messages should never reach this helper, but the
    safety branch prevents accidental leakage if a future caller
    violates the contract).

    M11 F7 L4: closes F6 Rec #4 / M11 criterion #13 (LLM-side
    projection of peer_name + channel_name). The prefix IS the
    projection — the F6 audit's "no leak" guarantee becomes
    "intentional projection at this single site"; the fields
    never appear as separate keys on the API payload.
    """
    if msg.role != Role.USER:
        return msg.content
    peer = msg.peer_name
    ch = msg.channel_name
    if peer is not None and ch is not None:
        return f"[from {peer} in #{ch}]: {msg.content}"
    if peer is not None:
        return f"[from {peer}]: {msg.content}"
    if ch is not None:
        return f"[in #{ch}]: {msg.content}"
    return msg.content


@dataclass
class StreamChunk:
    """Single chunk emitted by ``LLMProvider.stream``.

    ``content`` carries the NEW tokens since the last chunk (delta semantics —
    NOT cumulative). On the final chunk, ``is_final=True``; ``tool_calls``,
    ``usage`` and ``message`` are populated where the provider exposes them.
    The ``message`` field carries the synthesized assistant ``Message`` and
    is what ``Agent.step`` appends to its history.
    """

    content: str = ""
    is_final: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage | None = None
    message: Message | None = None


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: str
    max_context_tokens: int = 128_000

    def __init__(self) -> None:
        self._init_provider_state()

    def _init_provider_state(self) -> None:
        """Initialize per-instance provider state.

        Called by ``LLMProvider.__init__``. Subclasses that override
        ``__init__`` AND skip ``super().__init__()`` (e.g.,
        ``OpenRouterProvider`` — see its docstring at lines 63-65)
        MUST call ``self._init_provider_state()`` directly to inherit
        this state. Adding new instance attributes here keeps the
        contract single-source-of-truth: future state additions land
        here, and both the normal super-calling path and the OpenRouter
        opt-out path pick them up without manual mirroring.

        M08 F7 L05 (F6.5 debrief AI #1): replaces the prior
        "manually mirror every state addition in OpenRouter" tripwire.
        """
        # Sentinel for lazy max_context_tokens resolution. Set True after
        # first _resolve_max_context_tokens_if_needed() call (regardless
        # of fetch outcome) to prevent retry storms on metadata-fetch
        # failure. M08 F6.5 L01.
        self._max_context_tokens_resolved: bool = False

    async def _resolve_max_context_tokens(self) -> None:
        """Subclasses override to query provider metadata and set
        ``self.max_context_tokens`` to the per-model value. Default no-op
        (class attribute is the resolved value)."""

    async def _resolve_max_context_tokens_if_needed(self) -> None:
        """Lazy resolver. Idempotent — short-circuits after first call.

        Catches all exceptions so a metadata-fetch failure falls back
        to the class default without breaking the LLM call. ALWAYS
        flips the sentinel — failure-path caching prevents retry-on-
        every-call when metadata is unreachable. M08 F6.5 L01.
        """
        if self._max_context_tokens_resolved:
            return
        try:
            await self._resolve_max_context_tokens()
        except Exception:
            logger.debug(
                "max_context_tokens resolution failed for %s; using default %d",
                self.name,
                self.max_context_tokens,
                exc_info=True,
            )
        finally:
            self._max_context_tokens_resolved = True

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        """Send messages to the LLM and get a response."""
        ...

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        """Default streaming implementation: call ``complete()``, yield one final chunk.

        Providers SHOULD override with native streaming for better UX.
        Forward-compat for any future provider that doesn't natively stream.
        """
        msg = await self.complete(messages, tools, temperature, max_tokens)
        yield StreamChunk(
            content=msg.content,
            is_final=True,
            tool_calls=msg.tool_calls,
            usage=msg.usage,
            message=msg,
        )

    async def supports_tools(self) -> bool:
        """Whether this provider/model can accept a `tools` payload.

        Default ``True`` covers the cloud providers (OpenAI, Anthropic) and
        any model whose capabilities aren't queryable. Ollama overrides this
        to consult ``/api/show`` per-model — Gemma variants, for example,
        report no ``tools`` capability and reject the request with 400 if
        any tool (including the agent's virtual ``continue`` signal) is
        included in the payload.
        """
        return True

    def tool_schema(self, tool_def: dict[str, Any]) -> dict[str, Any]:
        """Convert a canonical tool definition to this provider's format.

        Override in subclasses if the provider uses a different schema.
        Default assumes OpenAI-style function calling format.
        """
        return {
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def["description"],
                "parameters": tool_def["parameters"],
            },
        }
