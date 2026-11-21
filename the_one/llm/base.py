from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """Current UTC time as an ISO 8601 string, used to stamp ``Message.created_at``.

    Fix: message-timestamp-on-replay. Single source of truth for the "now"
    used by ``Message.user``/``Message.assistant`` when the caller doesn't
    supply an explicit ``created_at`` (e.g. a codec decode reconstructing a
    historical row). Timezone-aware (UTC) so the frontend's ``fmtTs`` (which
    reads ``getUTCHours``/etc.) renders a stable value regardless of host
    timezone.
    """
    return datetime.now(timezone.utc).isoformat()


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
class ThinkingBlock:
    """A single extended-thinking block from a provider response.

    Mirrors Anthropic's two content-block variants (anthropic SDK 0.79.0):
      - type="thinking": `thinking` (reasoning text) + `signature` (opaque,
        server-issued; MUST be replayed verbatim or the follow-up turn 400s).
      - type="redacted_thinking": `data` (opaque; no text).
    Provider-agnostic — Ollama/OpenAI adapters may populate this later (DD5).
    """

    type: str
    thinking: str | None = None
    signature: str | None = None
    data: str | None = None


@dataclass
class TextContent:
    """A plain-text content block within a `list[ContentBlock]` user message.

    M16 F12 L01 (DD2): load-bearing, not a convenience wrapper — content is
    `str` XOR `list[ContentBlock]`, so a user's typed text becomes a block
    (this type) when an image is present alongside it. Also used by
    ``build_user_message_content`` to carry the peer/channel bracket prefix
    as a separate prepended block on the list path (DD4).
    """

    text: str


@dataclass
class ImageContent:
    """A single image content block within a `list[ContentBlock]` user message.

    M16 F12 L01 (DD2): provider-neutral — mirrors the `ThinkingBlock`
    precedent (a canonical dataclass each provider maps to its native wire
    shape at `_to_api_message`; see `the_one/agents.md` →
    `provider-shape-portability`). `data` (base64) is the universal path;
    `url` is native on Anthropic/OpenAI but a documented gap on Ollama (no
    remote-URL fetch — DD5). Both may be set simultaneously (provider
    mapping prefers `data`); at least one is required.
    """

    media_type: str  # e.g. "image/png", "image/jpeg"
    data: str | None = None  # base64 (universal path)
    url: str | None = None  # native on Anthropic/OpenAI; Ollama = documented gap (DD5)

    def __post_init__(self) -> None:
        """Require at least one of ``data``/``url``.

        Uses an explicit ``raise AssertionError`` rather than a bare
        ``assert`` statement — a bare ``assert`` is stripped under
        ``python -O``, which would silently let a fully-empty
        ``ImageContent`` through. Matches the sibling convention in
        ``Message.__post_init__`` above.
        """
        if self.data is None and self.url is None:
            raise AssertionError("ImageContent requires one of data (base64) or url")


ContentBlock = TextContent | ImageContent


@dataclass
class ToolResult:
    tool_call_id: str
    # M11 F8 L2: annotation widened from `str` to `str | dict | list[Any]`
    # to permit structured returns from L10 channel-context tools at the
    # construction-site boundary; ``__post_init__`` normalizes to ``str``
    # so every downstream consumer reads ``str`` uniformly. See
    # ``the_one/agents.md`` → ``provider-shape-portability``.
    content: str | dict | list[Any]
    is_error: bool = False
    metadata: dict[str, Any] | None = None  # F5 L3: generic cross-provider payload

    def __post_init__(self) -> None:
        """Normalize non-str content to JSON-str at construction.

        M11 F8 L2: the canonical wire-shape for tool_result content is
        ``str``. The agent loop at ``the_one/agent/core.py:336`` wraps
        tool returns as ``ToolResult(content=output)`` where ``output``
        may be a structured ``dict``/``list`` (e.g. L10 channel-context
        tools return ``list[dict]``). Normalizing here means every
        downstream consumer — provider ``_to_api_message``, codec
        encoding, telemetry projection, CLI rendering — reads ``str``
        uniformly. Removes the need for F7 12.l's per-encoder coercion.

        See ``the_one/agents.md`` → ``provider-shape-portability``.
        """
        if not isinstance(self.content, str):
            self.content = json.dumps(self.content)


@dataclass
class TokenUsage:
    """Token counts for one model call.

    ``input_tokens`` is the WHOLE prompt. For Anthropic it is uncached input
    plus cache writes plus cache reads. ``cache_read_tokens`` and
    ``cache_write_tokens`` are a breakdown of that total, not extra tokens:
    no consumer adds them to ``input_tokens`` again. A future provider mapping
    (for example OpenAI ``cached_tokens``) must keep ``input_tokens`` as the
    whole prompt and report the cached part only in the breakdown.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    # Sortie 14 DD2: prompt-cache counts. ``input_tokens`` stays the WHOLE prompt
    # (uncached + cache writes + cache reads); these two say how much of it was
    # written to / read from the provider's prompt cache. Zero when not cached.
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


# M10 F03 L02: visibility tag literal for ``Message.visibility`` (below).
# A typo like ``"opperator"`` at a production set-site is caught at import
# / IDE time rather than persisting silently. Plain assignment (not
# ``Final[str]``) matches the project's existing module-level-constant
# style; the codebase has zero existing ``typing.Final`` usages.
OPERATOR_VISIBILITY = "operator"


@dataclass
class Message:
    role: Role
    content: str | list[ContentBlock] = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # M16 F10 L01 (DD1/DD2): structured extended-thinking blocks. A list —
    # NOT a scalar — because criterion #1 replays blocks WITH their signatures
    # and redacted_thinking blocks carry opaque `data` with no text; a bare
    # `str` can carry neither. A structural sibling of ``tool_calls``: it
    # defaults to ``[]`` and the codec emits it with a TRUTHY guard
    # (``if msg.thinking:``), so an empty list emits no key and legacy rows
    # decode byte-identically. Deliberately OUTSIDE the
    # ``message-additive-back-compat-via-emit-when-non-none`` convention
    # (``agents.md``) — an always-non-None empty list under an ``is not None``
    # guard would emit ``"thinking": []`` unconditionally and break the
    # byte-identity tripwire. ``StreamChunk`` gets no thinking field (DD2):
    # capture is from the final message (Leg 02), not intermediate chunks.
    thinking: list[ThinkingBlock] = field(default_factory=list)
    tool_result: ToolResult | None = None
    usage: TokenUsage | None = None
    # M10 F03 L02: visibility tag for two-layer connector-session model.
    # None = no operator-only restriction (platform-visible for connector
    # sessions; the only layer for non-connector sessions).
    # "operator" = operator-console only; never propagated to the platform.
    # Constant published as ``OPERATOR_VISIBILITY`` (below, this module) —
    # use it at every production set site.
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
    # M33 F1 L3: routine marker. USER-only: set on the typed message of a
    # routine run (the routine's id and display name). Stored and shown in UI
    # events; never sent to a provider (each converter builds its payload from
    # a whitelist). Absent in legacy rows (None).
    routine_id: str | None = None
    routine_name: str | None = None
    # M33 F2 L3 (DD7): the routine's untrusted sources AS THEY WERE when this run was
    # posted (a snapshot; ``[]`` = unflagged, ``None`` = not a routine turn or a legacy
    # marker). USER-only; stored; never sent to a provider and not spread into UI events.
    routine_untrusted_sources: list[str] | None = None
    # M36 F2 L5: GleepGlorp proposal marks. USER-only; stored and shown in UI events, never
    # sent to a provider. ``approved`` marks a continuation turn's message,
    # ``approved_no_turn`` an approval appended with no turn, ``dismissed`` a dismissal.
    proposal_id: int | None = None
    proposal_event: Literal["approved", "approved_no_turn", "dismissed"] | None = None
    # M36 F3 L4: the page the operator was on when a drawer message was sent, ``{"line": str}``
    # only (the resolved, sanitised line, never re-resolved). USER-only; stored, shown in UI
    # events, and projected to the provider as one leading ``[Page: ...]`` line by
    # ``build_user_message_content``.
    page: dict | None = None
    # Fix: message-timestamp-on-replay. Per-message creation timestamp (ISO
    # 8601, UTC) so historical USER/ASSISTANT turns can render a "You ·
    # HH:MM UTC" / "<agent> · HH:MM UTC" attribution on session replay —
    # today the live UI shows a client-render-time timestamp
    # (``new Date()`` in chat.js) but nothing is persisted, so replayed
    # turns show no time at all. None on the dataclass itself (a bare
    # ``Message(role=..., content=...)`` is unchanged); only the
    # ``Message.user``/``Message.assistant`` factories default it to
    # ``_utcnow_iso()`` when not explicitly provided. Deliberately NOT set
    # by ``Message.system``/``Message.tool`` — those roles never render a
    # timestamp. The codec emits the key only when non-None — pre-fix rows
    # decode with created_at=None unchanged (message-additive-back-compat-
    # via-emit-when-non-none convention, ``the_one/agents.md``).
    created_at: str | None = None

    def __post_init__(self) -> None:
        """Assert content is str, or a USER-only list[ContentBlock].

        M11 F8 L2: ``Message.content`` is constructed at three classes
        of sites — provider response parsers (build str from API
        response), codec decoders (decode str from JSON), and factory
        methods (``Message.system``/``user``/``assistant``/``tool``).
        A non-str/non-list arriving here means a provider-parser defect,
        NOT a legitimate structured payload (compare ``ToolResult.content``
        which CAN be structured pre-normalization). Assert rather than
        normalize so the defect surfaces loudly.

        M16 F12 L01 (DD2/DD3): widened to also accept
        ``list[ContentBlock]`` (``TextContent`` | ``ImageContent``) — but
        ONLY on ``Role.USER`` messages (images/documents are inputs;
        SYSTEM/ASSISTANT/TOOL content stays ``str``). Both invalid branches
        use an explicit ``raise AssertionError`` rather than a bare
        ``assert`` statement — a bare ``assert`` is stripped under
        ``python -O``, which would silently let a non-USER block-list
        through and break the DD3 invariant. Empty ``list`` content on
        USER is allowed by design: this validates shape + role, not
        content semantics (mirrors the empty-``str`` precedent).

        See ``the_one/agents.md`` → ``provider-shape-portability``.
        """
        c = self.content
        if isinstance(c, str):
            pass
        elif isinstance(c, list) and all(isinstance(b, (TextContent, ImageContent)) for b in c):
            if self.role != Role.USER:
                raise AssertionError(
                    f"list[ContentBlock] content is only valid on USER messages, got {self.role}"
                )
        else:
            raise AssertionError(
                f"Message.content must be str or list[ContentBlock], got {type(c).__name__}"
            )

    @classmethod
    def system(cls, content: str, *, visibility: str | None = None) -> Message:
        return cls(role=Role.SYSTEM, content=content, visibility=visibility)

    @classmethod
    def user(
        cls,
        content: str | list[ContentBlock],
        *,
        visibility: str | None = None,
        peer_name: str | None = None,
        channel_id: str | None = None,
        channel_name: str | None = None,
        created_at: str | None = None,
        routine_id: str | None = None,
        routine_name: str | None = None,
    ) -> Message:
        return cls(
            role=Role.USER,
            content=content,
            visibility=visibility,
            peer_name=peer_name,
            channel_id=channel_id,
            channel_name=channel_name,
            routine_id=routine_id,
            routine_name=routine_name,
            created_at=created_at if created_at is not None else _utcnow_iso(),
        )

    @classmethod
    def assistant(
        cls,
        content: str,
        tool_calls: list[ToolCall] | None = None,
        usage: TokenUsage | None = None,
        *,
        visibility: str | None = None,
        thinking: list[ThinkingBlock] | None = None,
        created_at: str | None = None,
    ) -> Message:
        return cls(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=tool_calls or [],
            usage=usage,
            visibility=visibility,
            thinking=thinking or [],
            created_at=created_at if created_at is not None else _utcnow_iso(),
        )

    @classmethod
    def tool(cls, result: ToolResult, *, visibility: str | None = None) -> Message:
        return cls(
            role=Role.TOOL,
            content=result.content,
            tool_result=result,
            visibility=visibility,
        )


def tag_post_step_visibility(
    messages: list[Message],
    pre_step_len: int,
) -> None:
    """Apply post-step visibility rules to messages appended by ``agent.step``.

    Relocated here (Mission 23 Flight 1, backend-removal leg) from the
    connector package's deleted ``post_step_metadata`` module — the
    connector dispatcher's other call sites there (``bind_peer_name``,
    ``bind_channel_context``, ``resolve_channel_name``) go with the
    package, but this mutator has a surviving caller: the WS-storage-edge
    shim in ``the_one/interfaces/web/app.py`` (``_process_and_broadcast``
    / ``_resume_paused_session``), pinned by
    ``tests/test_ws_storage_edge_shim_visibility.py``. Its home is now
    ``llm/base.py`` alongside ``OPERATOR_VISIBILITY`` and ``Message``.

    **Touches**: every ``Role`` EXCEPT ``Role.USER`` — i.e.
    ``Role.ASSISTANT`` and ``Role.TOOL`` messages at or after
    ``pre_step_len`` have their ``visibility`` overwritten.

    **Skips**: ``Role.USER`` messages at or after ``pre_step_len``.
    The peer-inbound dispatcher constructs USER with
    ``visibility=None`` (peer-visible); the operator-input WS shim
    constructs USER with ``visibility=OPERATOR_VISIBILITY``. Either
    way, the post-step pass does not touch the USER message — its
    visibility is the caller's contract.

    Mutates ``messages`` in place. Returns ``None``. Caller is
    responsible for tagging the entry-point USER message at
    construction time (BEFORE ``agent.step``); this helper does not
    touch it.

    ``pre_step_len`` is the length of ``messages`` BEFORE the
    ``agent.step`` call. The helper iterates
    ``messages[pre_step_len:]`` and applies the rules below.

    Tagging rules (preserved verbatim from M10 F4 L4):

    - ``Role.USER`` messages at or after ``pre_step_len`` are
      SKIPPED (see above).
    - ``Role.TOOL`` whose parent ``tool_call.name ==
      "send_to_platform_channel"`` AND content starts with the
      platform-send success prefix → ``visibility=None`` (peer-visible;
      the platform-send tool already pushed the content to peers). The
      send tool was re-attached in Mission 23 Flight 2 Leg 1
      (``the_one/tools/connector_send.py``) — this branch is live again,
      exercised end-to-end by the connector inbound pipeline
      (``the_one/connectors/inbound.py::dispatch_inbound``), and the
      tagging contract stays pinned by the test above plus
      ``tests/test_connector_send_tool.py::test_shared_constants_pin_llm_base_literals``.
    - Everything else → ``OPERATOR_VISIBILITY`` (assistant text +
      intermediate tool calls/results stay operator-only).
    - Messages at indices ``< pre_step_len`` (the pre-existing
      history) are NEVER touched.
    """
    # "[platform-send-ok]" is ``PLATFORM_SEND_OK_PREFIX``, now defined in
    # ``the_one/tools/connector_send.py`` (re-attached Mission 23 Flight 2
    # Leg 1). Inlined here rather than imported — ``the_one/llm/`` does not
    # import from ``the_one/tools/`` (tools depend on llm-adjacent layers,
    # not the reverse; see this flight's flight-log Deviations for Leg 1's
    # explicit "assert, not import" call). Agreement between the two
    # literals is pinned by
    # ``tests/test_connector_send_tool.py::test_shared_constants_pin_llm_base_literals``
    # instead of a shared import.
    platform_send_ok_prefix = "[platform-send-ok]"
    new_msgs = messages[pre_step_len:]
    tool_call_names: dict[str, str] = {}
    for msg in new_msgs:
        if msg.role == Role.ASSISTANT:
            for tc in msg.tool_calls:
                tool_call_names[tc.id] = tc.name
    for msg in new_msgs:
        if msg.role == Role.USER:
            continue
        is_successful_platform_send = (
            msg.role == Role.TOOL
            and msg.tool_result is not None
            and tool_call_names.get(msg.tool_result.tool_call_id) == "send_to_platform_channel"
            and msg.content.startswith(platform_send_ok_prefix)
        )
        msg.visibility = None if is_successful_platform_send else OPERATOR_VISIBILITY


def build_user_message_content(msg: Message) -> str | list[ContentBlock]:
    """Build the LLM-payload content for a user message, projecting
    peer_name and channel_name as an inline bracket prefix.

    Format depends on which fields are set (all use ``is not None``,
    NOT truthiness — empty strings round-trip as-is per the
    ``message-additive-back-compat-via-emit-when-non-none`` convention):

    - peer_name + channel_name both set → ``[from {peer} in #{ch}]: {content}``
    - peer_name only                    → ``[from {peer}]: {content}``
    - channel_name only                 → ``[in #{ch}]: {content}``
    - neither set                       → ``{content}`` (byte-identical
      to pre-F6 + pre-F7 payload — legacy back-compat)

    M16 F12 L01 (DD4): ``list[ContentBlock]`` content is shape-aware — the
    prefix (when applicable) is a SEPARATE prepended ``TextContent`` block,
    not merged into the user's own text block (the user's blocks are never
    rewritten). When no prefix applies, returns a fresh copy
    (``list(msg.content)``) rather than the same list reference, so a
    downstream provider adapter can't mutate the caller's list — mirrors
    the str path, which is aliasing-immune by construction (a new str is
    always built).

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
    page_line = msg.page.get("line") if isinstance(msg.page, dict) else None
    if isinstance(page_line, str) and page_line:
        # M36 F3 L4: lead with the page line; the rest is today's result, untouched.
        page_prefix = f"[Page: {page_line}]"
        inner = _project_user_content(msg)
        if isinstance(inner, list):
            return [TextContent(text=page_prefix), *inner]
        return f"{page_prefix}\n{inner}"
    return _project_user_content(msg)


def _project_user_content(msg: Message) -> str | list[ContentBlock]:
    """The peer/channel projection of ``build_user_message_content`` (no page)."""
    peer = msg.peer_name
    ch = msg.channel_name
    if isinstance(msg.content, list):
        prefix = None
        if peer is not None and ch is not None:
            prefix = f"[from {peer} in #{ch}]:"
        elif peer is not None:
            prefix = f"[from {peer}]:"
        elif ch is not None:
            prefix = f"[in #{ch}]:"
        return [TextContent(text=prefix), *msg.content] if prefix else list(msg.content)
    if peer is not None and ch is not None:
        return f"[from {peer} in #{ch}]: {msg.content}"
    if peer is not None:
        return f"[from {peer}]: {msg.content}"
    if ch is not None:
        return f"[in #{ch}]: {msg.content}"
    return msg.content


def content_to_text(content: str | list[ContentBlock]) -> str:
    """Flatten message content to a plain-text projection for str-only consumers.

    ``str`` → returned as-is. ``list`` → ``TextContent`` texts joined by a single
    space; each ``ImageContent`` → a ``"[image]"`` placeholder (mirrors the MCP
    layer's image→placeholder flattening in ``mcp/client.py``). For consumers that
    need a text view of content and cannot render blocks (e.g. the inference
    classifier's history render).

    M16 F12 L03: dispatch is by ``isinstance`` — NOT a ``type`` string — per the
    F10 Rec 5 no-hardcoded-type-filter guidance. The union is closed
    (``ContentBlock = TextContent | ImageContent``), so this is exhaustive; empty
    list → ``""``.
    """
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for b in content:
        if isinstance(b, TextContent):
            parts.append(b.text)
        elif isinstance(b, ImageContent):
            parts.append("[image]")
    return " ".join(parts)


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

    # M16 F08 L01 (MEDIUM-1): the SINGLE public bytes-per-token accessor.
    # Consumed by BOTH the context-budget governor (``_execute_tool`` →
    # ``govern_tool_content``) and the streaming usage heuristic
    # (``_StreamAccumulator``). Default 4.0 (OpenAI/OpenRouter cl100k density);
    # Anthropic (3.7) and Ollama (3.5) override the class attribute. Replaces
    # the prior subclass-only ``_bytes_per_token_for_interim()`` so the two
    # consumers can't drift apart.
    bytes_per_token: float = 4.0

    # Sortie 11 DD2: True only when a resolver assigned ``max_context_tokens`` from real
    # provider metadata (a catalog hit, ``/api/show``, a listed ``context_length``), so
    # ``max_context_tokens`` is the model's actual window and not the class default.
    context_window_known: bool = False

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
        *,
        enable_thinking: bool | None = None,
    ) -> Message:
        """Send messages to the LLM and get a response.

        M16 F10 L02 (DD4): ``enable_thinking`` is a provider-neutral opt-out
        for extended thinking. ``None`` = use the provider's configured budget;
        ``False`` = force thinking OFF regardless of config (the connector
        inference classifier passes ``False`` so its cheap yes/no probe never
        pays the thinking premium). Only the Anthropic adapter acts on it this
        flight (DD5); other adapters accept-and-ignore.
        """
        ...

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Default streaming implementation: call ``complete()``, yield one final chunk.

        Providers SHOULD override with native streaming for better UX.
        Forward-compat for any future provider that doesn't natively stream.

        M16 F10 L02 (DD5): forwards ``enable_thinking`` into ``complete()`` so a
        complete-only provider relying on this default stream path honors the
        signal instead of silently dropping it.
        """
        msg = await self.complete(
            messages, tools, temperature, max_tokens, enable_thinking=enable_thinking
        )
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

    async def aclose(self) -> None:
        """Release any persistent HTTP client held by this provider.

        Default no-op — providers without a persistent client inherit this.
        Providers that hold an ``httpx.AsyncClient`` (Anthropic, OpenAI)
        override to call ``await self.client.aclose()``. Called by
        ``Agent.aclose()`` during web-session idle-reaper eviction.
        F05 L01: idempotent by design (httpx's own aclose is idempotent).
        """
