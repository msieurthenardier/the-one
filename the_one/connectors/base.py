"""Connector plugin contract.

The single file every future connector author opens to implement support
for a new third-party communication platform. The four-method
:class:`ConnectorPlugin` Protocol below is the type-level adapter contract;
:class:`ConnectorClient` is the per-instance live-connection wrapper that
each plugin's :meth:`connect` returns.

Per ``agents.md`` ``structural-Protocol-satisfaction``: implementations
satisfy the Protocols structurally and DO NOT inherit from them. A connector
that supports per-(peer, channel) gating implements the OPTIONAL
``resolve(account, envelope) -> ResolveOutcome`` hook (introduced by
flight 6 of mission 10). The hook is discovered by consumers via
:func:`getattr` with :func:`_default_permit` as the fallback — same
convention as F3's ``display_channel``. It is NOT declared on the
:class:`ConnectorPlugin` Protocol; plugins opt in by exposing the method.
The three-outcome ADT (:class:`Permit`, :class:`NeedsPairing`,
:class:`Deny`, exposed as :data:`ResolveOutcome`) and the
:class:`CommandHandler` Protocol (F7 L1) live alongside the Protocols in
this file — "single contract file" is the mission criterion, not "single
Protocol".

Per ``agents.md`` ``optional-plugin-hook-via-getattr-sentinel`` (L1-codified
by flight 1 of mission 11): connectors that can enumerate the platform
entities the bot has live visibility into implement the OPTIONAL
``enumerate_discoverable_entities(client: ConnectorClient) -> DiscoverableEntities``
hook (introduced by flight 3 of mission 11 for live-data discoverable
dropdowns). Discovered via ``getattr(plugin, "enumerate_discoverable_entities", None)``
with ``None`` as the fallback sentinel — consumers (the L4 pool cache
refresh sweep and the per-account Studio API endpoint) treat the
``None`` return as "this plugin doesn't expose live data; fall back to
the chip-list editor."

Per ``agents.md`` ``canonical-import + convenience-re-export``: code that
touches Protocol identity (``isinstance(...)`` or subclass checks) MUST use
the canonical import path from this module, not from ``the_one.connectors``
(the package-level ``__init__.py`` re-exports for convenience only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from the_one.db.models import Connector
from the_one.encryption import Encryptor


@dataclass(frozen=True, slots=True)
class InboundEnvelope:
    """A message received from the external platform, normalized for routing.

    The plugin's gateway-listener / webhook-receiver constructs one of
    these per inbound message and hands it to the connector subsystem.
    """

    platform: str
    """The connector's ``type`` value (e.g. ``"discord"``, ``"slack"``)."""

    account_id: str
    """The :class:`Connector.id` whose gateway delivered this message."""

    channel_id: str
    """Platform-native channel identifier (Discord channel snowflake, Slack
    channel id). For DMs, this is the DM channel; for guild messages, the
    text channel."""

    thread_id: str | None
    """Platform-native thread identifier when the message is in a thread;
    ``None`` for top-level channel messages."""

    peer_id: str
    """Platform-native peer identifier (the sender's Discord user id, Slack
    user id, etc.)."""

    peer_name: str
    """The sender's display name on the platform at the moment of inbound."""

    text: str
    """The message body as plain text (platform-specific markup stripped)."""

    raw: dict[str, Any] = field(hash=False, compare=False)
    """The platform-native payload, untransformed. Plugins may consult this
    for fields not yet promoted to first-class envelope attributes
    (attachments, embeds, etc.).

    Required at construction time. Excluded from ``__hash__`` and ``__eq__``
    via ``field(hash=False, compare=False)`` — bare ``frozen=True, slots=True``
    on a dataclass with a ``dict`` field constructs fine but ``hash()`` raises
    ``TypeError: unhashable type: 'dict'``. Hashability is preserved on the
    scalar fields; dict contents are not part of the envelope's identity.
    """


@dataclass(frozen=True, slots=True)
class FetchedMessage:
    """A message fetched from channel/thread/DM history via plugin hook.

    Returned by the substrate-generic ``fetch_history`` and
    ``fetch_dm_history`` plugin hooks (optional via
    ``optional-plugin-hook-via-getattr-sentinel`` — M11 F7 L10). The L10
    fetch tools convert each instance to a dict via
    ``dataclasses.asdict`` before emitting to the LLM.

    The five-field shape is platform-neutral: Discord's plugin fills
    these from ``discord.Message`` attributes; future Slack/Matrix
    plugins emit the same fields from their own SDK objects.
    ``thread_id`` is ``None`` for top-level channel messages and for
    every DM (DMs have no thread concept).
    """

    peer_id: str
    """Platform-native peer identifier (the sender's Discord user id,
    Slack user id, etc.)."""

    peer_name: str
    """The sender's display name on the platform at the moment the
    message was sent."""

    content: str
    """The message body as plain text (platform-specific markup
    stripped)."""

    ts: str
    """ISO 8601 timestamp of the message's creation on the platform."""

    thread_id: str | None
    """Platform-native thread identifier when the message lives in a
    thread; ``None`` for top-level channel messages and for all DMs."""


@dataclass(frozen=True, slots=True)
class OutboundTarget:
    """Where on the platform an agent's reply is being sent."""

    channel_id: str
    """The platform-native channel id to deliver the message to."""

    thread_id: str | None = None
    """Optional thread to post into; ``None`` posts in the channel itself."""

    interaction_followup_token: str | None = None
    """Discord interaction-followup token (a plain string) threaded from the
    inbound slash envelope. When set together with ``ephemeral``, the Discord
    adapter reconstructs an application webhook and delivers the reply as an
    ephemeral interaction followup instead of a channel send. ``None`` for all
    non-slash callers (agent replies, the platform-send tool, etc.)."""

    ephemeral: bool = False
    """When ``True`` (and an interaction-followup token is present), the reply
    is delivered ephemerally (only the invoker sees it). Defaults to ``False``
    so every existing caller is unaffected."""


@dataclass(frozen=True, slots=True)
class SessionKey:
    """Normalized binding between an external conversation and an internal
    ``chat_sessions`` row.

    Built by :meth:`ConnectorPlugin.normalize_session_key`. Hashable
    (``frozen=True``, ``slots=True``) so it can be used as a dict key in
    the agent-session mapping that flight 3 of mission 10 introduces.

    The exact set of fields that participate in the key (e.g. does
    ``thread_id`` separate the binding or fold into the channel?) is a
    flight-3 design decision. This dataclass carries all candidate fields;
    flight 3's normalization logic decides which to populate.
    """

    platform: str
    account_id: str
    channel_id: str
    thread_id: str | None = None
    peer_id: str | None = None


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Result of a :meth:`ConnectorPlugin.doctor` probe.

    Mirrors the diagnostic shape M07's MCP inspector established (status
    plus a human-readable message plus optional structured details for the
    admin UI).
    """

    status: Literal["ok", "degraded", "failed"]
    """The probe outcome — ``ok`` if every check passed, ``degraded`` if the
    connection works but a non-critical check failed, ``failed`` if the
    plugin cannot use this account."""

    message: str
    """One-sentence human-readable summary suitable for the admin UI's
    inline status. Mirrors the small-model-friendly convention of
    ``the_one/mcp/errors.py``."""

    details: dict[str, Any] = field(hash=False, compare=False)
    """Required structured detail surface for the admin UI's expanded
    probe view. Plugins MAY pass an empty dict when there is nothing
    platform-specific to surface. Plugins MAY populate platform-specific
    fields (token fingerprint, intent coverage, gateway endpoint, etc.).
    The shape is not standardized across plugins.

    Excluded from ``__hash__`` and ``__eq__`` — same rationale as
    :attr:`InboundEnvelope.raw`.
    """


@dataclass(frozen=True, slots=True)
class SendResult:
    """Result of a successful :meth:`ConnectorClient.send` call.

    Returned by every connector's outbound-send implementation. Mirrors
    the diagnostic shape of :class:`DoctorReport` — a small scalar
    surface plus a structured ``details`` dict for platform-specific
    overflow (rate-limit headers, edit timestamps, attachment id
    arrays, etc.).
    """

    platform_message_id: str | None
    """Best-effort platform-native message id for the delivered message.
    Some platforms return one (Discord); others don't (webhooks-only
    flows). ``None`` is a valid value, not an error signal.
    """

    details: dict[str, Any] = field(hash=False, compare=False)
    """Required structured detail surface mirroring :attr:`DoctorReport.details`
    — rate-limit headers, edit timestamps, attachment id arrays, etc.
    Plugins MAY pass an empty dict when there is nothing platform-specific
    to surface. Excluded from ``__hash__`` and ``__eq__`` — same rationale
    as :attr:`InboundEnvelope.raw`.
    """


@dataclass(frozen=True, slots=True)
class Permit:
    """Resolver outcome: the envelope is admitted; agent.step proceeds normally."""


@dataclass(frozen=True, slots=True)
class NeedsPairing:
    """Resolver outcome: the peer is unknown; the dispatcher must validate a pairing prefix.

    The plugin signals the SHAPE ("this peer isn't on the allowlist; pair-or-deny");
    the dispatcher (F6 leg 2) owns prefix validation against
    ``account.config["pairing"]["code"]``. ``reason`` surfaces in audit log
    entries written to ``chat_sessions.session_metadata``.
    """

    reason: str


@dataclass(frozen=True, slots=True)
class Deny:
    """Resolver outcome: the envelope is rejected outright; no pairing path.

    The dispatcher logs the outcome to ``session_metadata`` and returns
    without invoking ``agent.step``. From the peer's perspective the bot
    is silent. ``reason`` surfaces in audit log entries.
    """

    reason: str


ResolveOutcome = Permit | NeedsPairing | Deny
"""Union of the three resolver outcomes produced by the optional ``resolve`` hook.

Consumers (``connectors/_inbound.py`` in F6 leg 2,
``tools/connector_send.py`` in F6 leg 3) discover the hook via
``getattr(plugin, "resolve", _default_permit)``; the fallback is
:func:`_default_permit` which returns :class:`Permit` unconditionally.
``Permit()`` instances are frozen-dataclass-equal so callers may compare
against a sentinel without identity reliance.
"""


def _default_permit(
    account: Connector,
    envelope: InboundEnvelope,
) -> Permit:
    """Default resolver fallback when a plugin does not implement ``resolve``.

    Used by F6's inbound dispatcher (``connectors/_inbound.py``) and
    outbound tool (``tools/connector_send.py``) via
    ``getattr(plugin, "resolve", _default_permit)``. Returns ``Permit()``
    unconditionally — the plugin opted not to gate, so the subsystem
    does not gate either.

    Private to the connector package: consumers import via the canonical
    path ``the_one.connectors.base._default_permit``, not via the
    ``__init__.py`` convenience re-export.
    """
    return Permit()


@runtime_checkable
class ConnectorClient(Protocol):
    """Live-connection wrapper for a single connector account.

    Each :meth:`ConnectorPlugin.connect` invocation produces a
    :class:`ConnectorClient`. The per-(agent, account) lifecycle pool
    (legs 5+6 of this flight) holds one client per warm entry and calls
    :meth:`is_alive` to decide whether the client needs respawn.

    ``runtime_checkable`` Protocol checks method NAMES only. Flight 4
    widened this Protocol with :meth:`send` to carry outbound
    platform-bound messages. The widening is additive — existing
    ``isinstance(client, ConnectorClient)`` checks remain valid for
    clients that implement BOTH ``is_alive`` and ``send``; clients
    missing ``send`` after F4 now fail the Protocol check at runtime.
    """

    def is_alive(self) -> bool:
        """Return ``True`` if the underlying platform connection is healthy.

        Called periodically by the lifecycle pool's reaper. ``False``
        triggers an evict-and-respawn; a raised exception is treated as
        ``False`` plus logged.
        """
        ...

    async def send(
        self,
        target: OutboundTarget,
        content: str,
    ) -> SendResult:
        """Deliver ``content`` to ``target`` on the underlying platform.

        Called by the ``platform_send`` built-in tool (F4 leg 2) when an
        agent emits an outbound message. Returns a :class:`SendResult`
        carrying the platform-native message id (when available) and any
        platform-specific details. Raises on platform-side failures so
        the tool can convert the error into a tool-result message.
        """
        ...


@runtime_checkable
class ConnectorPlugin(Protocol):
    """Type-level adapter for a third-party communication platform.

    Implementations (one per platform — ``DiscordPlugin``, ``SlackPlugin``,
    ``StubPlugin``) structurally satisfy this Protocol WITHOUT inheriting
    from it. Each plugin is stateless at the type level — per-account
    state lives on the :class:`ConnectorClient` instances returned by
    :meth:`connect`.

    ``runtime_checkable`` Protocol checks method NAMES only. Widening this
    Protocol is non-breaking for existing
    ``isinstance(plugin, ConnectorPlugin)`` consumers, so subsequent flights
    can add methods deliberately. Flight 6 introduces the OPTIONAL
    ``resolve(account, envelope) -> ResolveOutcome`` hook discoverable via
    :func:`getattr` with :func:`_default_permit` as the fallback — NOT a
    Protocol widening; plugins opt in by exposing the method (same
    convention as F3's ``display_channel``). F7 L1 declares a separate
    :class:`CommandHandler` Protocol in this file that command-aware
    connectors structurally satisfy in addition to
    :class:`ConnectorPlugin`.
    """

    async def connect(
        self,
        account: Connector,
        encryptor: Encryptor,
    ) -> ConnectorClient:
        """Open a live platform connection for ``account`` and return the client.

        ``encryptor`` is the system-wide :class:`Encryptor` instance used
        to decrypt ``account.secrets`` at call time. The plugin MUST NOT
        retain a reference to the decrypted plaintext past the call; the
        ``encryptor`` reference may be retained (rotation propagates
        through it).

        Raises :class:`ConnectorConfigError` if the account's config or
        secrets are invalid for this plugin; :class:`ConnectorConnectionError`
        if the platform is unreachable.
        """
        ...

    async def disconnect(self, client: ConnectorClient) -> None:
        """Cleanly tear down ``client``'s platform connection.

        Called by the lifecycle pool at evict time and at shutdown drain.
        Should be best-effort idempotent — calling ``disconnect`` on a
        client that is already disconnected MUST NOT raise.
        """
        ...

    async def doctor(
        self,
        account: Connector,
        encryptor: Encryptor,
    ) -> DoctorReport:
        """Probe ``account`` without dispatching messages to peers.

        Verifies the connection lifecycle, token validity, and any
        plugin-specific capability/permission preconditions. Returns a
        :class:`DoctorReport` rather than raising — failure is a normal
        outcome the admin UI renders, not an exception that crashes the
        request.
        """
        ...

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        """Compute the canonical :class:`SessionKey` for ``inbound``.

        The plugin decides which fields of the inbound envelope participate
        in the key (does ``thread_id`` separate the binding or fold into
        the channel? does the peer participate in a DM-only context?). The
        connector subsystem treats the returned key as opaque and uses it
        as a dict-lookup primitive against the agent-session mapping in
        flight 3 of mission 10.
        """
        ...


@dataclass(frozen=True, slots=True)
class CommandResponse:
    """Result of a :class:`CommandHandler` handling a platform-side command.

    The handler returns this value; the dispatcher (F7 L5) emits ``text``
    via the system-outbound path (``account_acquire(account_id) →
    client.send(target, text)``) — the same path the platform-send tool
    uses, invoked dispatcher-internally rather than via the tool
    registry.

    Returning ``None`` from :meth:`CommandHandler.handle_command` is
    distinct from returning ``CommandResponse(text="")`` — ``None`` means
    "fall through to the dispatcher's built-in handler"; an empty-text
    response means "this handler handled the command and the response is
    intentionally empty" (and the dispatcher MUST NOT fall through).
    """

    text: str

    ephemeral: bool = False
    """When ``True``, the dispatcher requests an ephemeral delivery (only the
    invoker sees the reply) for command responses that arrived via an
    interaction (e.g. a Discord slash command). Opt-in: existing and future
    handlers default to ``False`` (channel-visible), so there is no behavior
    change unless a handler explicitly sets it. Ephemeral delivery is
    best-effort — it requires an interaction-followup token to be present on
    the inbound envelope; a text-prefix invocation with no interaction falls
    back to a channel send."""


@dataclass(frozen=True, slots=True)
class DiscoverableEntity:
    """A single platform entity the bot has live visibility into.

    Returned in axis-keyed lists by the OPTIONAL
    :meth:`ConnectorPlugin.enumerate_discoverable_entities` hook (the
    name appears on the plugin only — :class:`ConnectorPlugin` Protocol
    body is NOT widened; see module docstring). The substrate treats
    this dataclass as opaque except for :attr:`id`, which is the
    platform-native ID used to round-trip a selection back into
    ``account.config.allowlist`` entries.

    The dataclass is platform-neutral: Discord's plugin emits
    ``@username`` peer labels and ``#channel-name`` channel labels;
    future Slack/Matrix plugins emit their own native forms. Vocabulary
    substitution (Discord renders ``groups`` as "servers", Slack as
    "workspaces") happens at the Studio render layer (M11 F3 L5/L6),
    NOT at this substrate layer.
    """

    id: str
    """Platform-native identifier (Discord snowflake string, Slack user
    id, etc.). Used as the dict key when the consumer round-trips a
    selection back into ``account.config.allowlist`` entries."""

    label: str
    """Platform-native display form, suitable for direct display in a
    dropdown chip without further transformation: e.g. ``@alice`` for
    Discord peers, ``#general`` for Discord channels, the bare guild
    name for Discord groups, ``@moderators`` for Discord roles."""

    group: str | None = None
    """Optional cross-axis grouping key the Studio render layer uses to
    visually cluster entities (e.g. ``"guild:123456789"`` for channels
    and roles belonging to the same Discord guild). ``None`` when the
    axis is naturally flat (peers span guilds; groups don't nest)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Platform-specific extras the substrate carries opaquely through
    to the render layer. Discord uses ``{"bot": bool}`` on peers,
    ``{"type": str}`` on channels (the channel-type token so the render
    layer can filter to text-postable channels), ``{"member_count":
    int}`` on groups, ``{"position": int, "mentionable": bool}`` on
    roles. The L4 API layer JSON-serializes this dict; plugins should
    keep the values JSON-friendly (str / int / bool / None)."""


@dataclass(frozen=True, slots=True)
class DiscoverableEntities:
    """A snapshot of the four discoverable axes for one connector account.

    Returned by :meth:`ConnectorPlugin.enumerate_discoverable_entities`
    (when the plugin implements the hook). The four axes match the
    existing ``account.config.allowlist`` shape so a Studio-layer
    dropdown selection round-trips directly into the allowlist without
    a name-translation step.

    Axes at the substrate layer:

    - :attr:`peers` — platform users the bot can see (Discord's
      ``Client.users``, Slack's reachable users, etc.).
    - :attr:`channels` — platform channels the bot has visibility into
      (Discord's guild channels via ``get_all_channels()``, Slack's
      channels, etc.). DMs and threads are NOT included at this layer.
    - :attr:`groups` — platform-level containers (Discord guilds,
      Slack workspaces, Matrix spaces). The Studio render layer
      substitutes the platform-native vocabulary at display time.
    - :attr:`roles` — platform role / permission-group entities
      (Discord guild roles; Slack user groups; etc.).

    :attr:`fetched_at` is the ISO 8601 timestamp at which the plugin
    read the live caches. The substrate stays neutral on staleness
    policy; the L4 pool cache decides when to re-sweep.
    """

    peers: list[DiscoverableEntity] = field(default_factory=list)
    """Platform users the bot can see. Discord populates from
    ``Client.users``."""

    channels: list[DiscoverableEntity] = field(default_factory=list)
    """Platform channels the bot has visibility into. Discord populates
    from ``Client.get_all_channels()`` (guild channels only — DMs and
    threads are out of scope at the substrate layer)."""

    groups: list[DiscoverableEntity] = field(default_factory=list)
    """Platform-level containers (Discord guilds, Slack workspaces).
    Discord populates from ``Client.guilds``."""

    roles: list[DiscoverableEntity] = field(default_factory=list)
    """Platform role / permission-group entities. Discord populates by
    iterating ``Guild.roles`` for each guild in ``Client.guilds``."""

    fetched_at: str = ""
    """ISO 8601 timestamp of the live read, produced by
    ``datetime.now(UTC).isoformat()`` at the plugin's call site
    (emitting the ``+00:00`` offset form). Defaults to the empty
    string so the dataclass is constructable in tests without a
    timestamp; plugins always populate this in production."""


@runtime_checkable
class CommandHandler(Protocol):
    """Optional platform-side command handler.

    Declared as a SEPARATE Protocol from :class:`ConnectorPlugin` — not a
    widening — so the existing 4-method plugin contract stays stable and
    plugins opt into command-handling additively. Connectors that want to
    register platform-native command surfaces (Discord slash commands via
    the Interactions API in F8; Slack slash commands via app manifest in
    F9) structurally satisfy this Protocol in addition to
    :class:`ConnectorPlugin`. Connectors that do NOT implement it (the
    stub plugin in this flight; the F8 / F9 plugins until they opt in)
    fall through to the dispatcher's built-in text-prefix command parser
    (F7 L5).

    Returning ``None`` from :meth:`handle_command` means "I don't handle
    this command; let the dispatcher's built-in handler take over." This
    lets plugins handle a subset of platform-native commands while still
    inheriting the v1 text-prefix vocabulary for the remainder.

    Per ``agents.md`` ``structural-Protocol-satisfaction``: implementations
    do NOT inherit from this Protocol. ``runtime_checkable`` Protocol
    checks method NAMES only.
    """

    async def handle_command(
        self,
        envelope: InboundEnvelope,
        command_name: str,
        args: list[str],
    ) -> CommandResponse | None:
        """Handle ``command_name`` parsed from ``envelope.text``.

        ``command_name`` is the bare command word (e.g. ``"agents"``,
        ``"talk-to"`` — no leading slash). ``args`` is the
        whitespace-separated remainder (empty list when the command has
        no args).

        Returns :class:`CommandResponse` if this plugin handles the
        command and the dispatcher should emit the response via the
        system-outbound path. Returns ``None`` to fall through to the
        dispatcher's built-in handler (F7 L5).
        """
        ...
