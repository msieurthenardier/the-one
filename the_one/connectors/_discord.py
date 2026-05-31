"""Discord connector plugin — gateway adapter.

M10 F8 L3 lands the :class:`DiscordClient` wrapper + the
:meth:`DiscordPlugin.connect` / :meth:`DiscordPlugin.disconnect`
implementations against ``discord.py 2.4+``. L4 wires ``on_message``
inbound, L5 fills in the outbound :meth:`DiscordClient.send` adapter,
and L7 lands the :meth:`DiscordPlugin.doctor` probe.

Cross-references:

- ``discord.py>=2.4,<2.5`` pinned in ``pyproject.toml`` (M10 F8 L2).
- The v19 CHECK constraint on ``connectors.type`` admits
  ``'discord'`` rows (see ``db/schema.py``'s v19 migration block).
- The registry binding ``register("discord", DiscordPlugin)`` lives at
  ``the_one.connectors.registry.register_builtin_connectors`` (function-
  local import to break the load cycle).

Per ``agents.md`` ``structural-Protocol-satisfaction``: :class:`DiscordPlugin`
does NOT inherit from :class:`ConnectorPlugin`; it satisfies the Protocol
structurally via the method names. Same convention for :class:`DiscordClient`
vs :class:`ConnectorClient`.

**Stateless plugin** — no ``__init__``. Mirrors :class:`StubPlugin` at
``_stub.py:72+``. Per-connection state lives on the
:class:`DiscordClient` instance returned by :meth:`connect`. The
F1 registry construction contract is ``cls()`` (zero-arg) at
``registry.py:76``.

**Gateway lifecycle** — :meth:`DiscordPlugin.connect` spawns a
background asyncio task running the SDK's
``Client.connect(reconnect=True)`` loop (the SDK's blocking-until-
disconnect gateway pump). The spawned task is owned by the returned
:class:`DiscordClient` instance. :meth:`DiscordPlugin.disconnect`
delegates to :meth:`DiscordClient.close` which closes the SDK client
and awaits the background task with a 5-second timeout.

**Reconnect division of labor** — outer (this module): 5-attempt
exponential backoff (1s, 2s, 4s, 8s, 16s) around the INITIAL
pre-READY connect handshake. Inner (SDK): ``Client.connect(reconnect=True)``
auto-resumes indefinitely for post-READY transient disconnects. After
READY, terminal SDK failures surface via ``is_alive()`` returning False;
the pool reaper respawns on next acquire.

**Token plaintext invariant** — neither :class:`DiscordPlugin` nor
:class:`DiscordClient` retains the decrypted bot token as an instance
attribute. The SDK retains it internally for HTTP REST calls; pool
eviction on credential change destroys the SDK client + its retained
token via :func:`the_one.connectors._pool._evict_all_for_account`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, cast

import aiohttp
import discord

from the_one.connectors.base import (
    CommandResponse,
    ConnectorClient,
    DiscoverableEntities,
    DiscoverableEntity,
    DoctorReport,
    FetchedMessage,
    InboundEnvelope,
    NeedsPairing,
    OutboundTarget,
    Permit,
    ResolveOutcome,
    SendResult,
    SessionKey,
)
from the_one.connectors.errors import (
    ConnectorConfigError,
    ConnectorConnectionError,
    ConnectorRateLimitError,
)
from the_one.db.models import Connector
from the_one.encryption import Encryptor

__all__ = ("DiscordPlugin", "DiscordClient")

logger = logging.getLogger(__name__)


# Outer reconnect schedule — applies to the INITIAL pre-READY connect
# handshake only. Post-READY transient disconnects are handled by the
# SDK's own ``Client.connect(reconnect=True)`` resume loop. See module
# docstring for the outer-vs-inner division of labor.
_RECONNECT_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)

# Default on_ready timeout. 60s accommodates cold-start with
# ``members=True`` chunking on large guilds. Override per-account via
# ``account.config["ready_timeout_seconds"]``.
_DEFAULT_READY_TIMEOUT_SECONDS: float = 60.0

# Default presence — operator-overridable via ``account.config["presence"]``.
_DEFAULT_PRESENCE: dict[str, str] = {
    "name": "Watching agent traffic",
    "type": "watching",
}

# Time we give the spawned gateway task to wind down after
# ``Client.close()`` in :meth:`DiscordClient.close`. Beyond this we cancel.
_CLOSE_TASK_TIMEOUT_SECONDS: float = 5.0


# M10 F8 L9: the 6 v1 commands surfaced as Discord application (slash)
# commands. Discord application command names CANNOT contain hyphens
# (regex ``^[-_\p{L}\p{N}\p{Devanagari}\p{Thai}]{1,32}$`` per the API
# rejects the literal hyphen for ASCII names) — ``talk-to`` is therefore
# registered as ``talk_to``. The F7 ``_parse_command`` text parser
# whitespace-splits the envelope text we synthesize (``/talk_to my-agent``)
# so the registered name and the dispatcher-side ``command_name`` agree.
# ``handle_command`` itself returns ``None`` for all six in L9 — the
# dispatcher falls through to the F7 built-in handler; native ephemeral
# customization (e.g. ephemeral ``/help``) is deferred to F10 hardening.
_SLASH_COMMAND_VOCAB: tuple[tuple[str, str], ...] = (
    ("agents", "List agents you can talk to in this channel"),
    ("talk_to", "Switch your active agent (args: <agent-slug>)"),
    ("whoami", "Show the agent currently routing your messages"),
    ("new", "Start a fresh session — drops the prior conversation"),
    ("reset", "Alias for /new — start a fresh session"),
    ("help", "Show available commands"),
)


def _resolve_activity_type(type_name: str) -> discord.ActivityType:
    """Map an operator-supplied activity-type string to ``discord.ActivityType``.

    Defaults to ``watching`` for unknown / malformed values — presence is
    cosmetic; do NOT fail ``connect`` over a typo.
    """
    try:
        return getattr(discord.ActivityType, type_name)
    except (AttributeError, TypeError):
        logger.warning(
            "Unknown Discord activity type %r; falling back to 'watching'",
            type_name,
        )
        return discord.ActivityType.watching


def _build_slash_envelope(
    *,
    interaction: "discord.Interaction",
    account_id: str,
    command_name: str,
    args: str,
) -> InboundEnvelope:
    """Translate a slash-command ``discord.Interaction`` → :class:`InboundEnvelope`.

    Mirrors L4's ``on_message`` envelope shape so the dispatcher's step
    11 sees the same fields it does for text-prefix commands:

    - ``text`` synthesizes the F7 text-prefix form (``/<name>`` plus the
      whitespace-prefixed ``args`` payload when non-empty). The F7
      ``_parse_command`` is whitespace-split, so a registered name of
      ``talk_to`` with ``args="my-agent"`` produces the envelope text
      ``/talk_to my-agent`` and the dispatcher pulls ``command_name=
      "talk_to"``, ``args=["my-agent"]``.
    - ``peer_id`` / ``peer_name`` from ``interaction.user``.
    - ``channel_id`` from ``interaction.channel_id`` (the channel /
      thread / DM channel the interaction was invoked in). When the
      invocation channel is a thread, ``interaction.channel_id`` is the
      thread id and the parent channel id is on
      ``interaction.channel.parent`` if accessible; ``thread_id`` is
      ``None`` for non-thread invocations and the thread id for
      thread-scoped slash invocations.
    - ``raw`` carries ``is_dm`` (``interaction.guild_id is None``) so
      F8 L6's DM-classification consult site sees the canonical key;
      ``guild_id`` and ``member_roles`` so F8 L8's 4-axis allowlist
      threading works identically to the on_message path.
    """
    import discord as _discord  # local — mirrors translate helper's pattern

    channel = getattr(interaction, "channel", None)
    channel_type = getattr(channel, "type", None) if channel is not None else None
    is_thread = channel_type in (
        getattr(_discord.ChannelType, "public_thread", None),
        getattr(_discord.ChannelType, "private_thread", None),
    )

    if is_thread:
        parent = getattr(channel, "parent", None)
        channel_id_str = (
            str(parent.id)
            if parent is not None and getattr(parent, "id", None) is not None
            else str(interaction.channel_id)
        )
        thread_id_str: str | None = str(interaction.channel_id)
    else:
        channel_id_str = str(interaction.channel_id)
        thread_id_str = None

    guild_id_raw = getattr(interaction, "guild_id", None)
    guild_id_str: str | None = (
        str(guild_id_raw) if guild_id_raw is not None else None
    )
    is_dm = guild_id_raw is None

    user = interaction.user
    roles = getattr(user, "roles", []) or []
    member_roles = [str(r.id) for r in roles if getattr(r, "id", None) is not None]

    # Synthesize the F7 text-prefix form. Whitespace-strip the args so
    # ``/help`` with no argument becomes ``/help`` (not ``/help ``); the
    # dispatcher's parser tolerates trailing whitespace either way but
    # the canonical form avoids audit-log noise.
    args_str = (args or "").strip()
    text = f"/{command_name}" if not args_str else f"/{command_name} {args_str}"

    return InboundEnvelope(
        platform="discord",
        account_id=account_id,
        channel_id=channel_id_str,
        thread_id=thread_id_str,
        peer_id=str(user.id),
        peer_name=getattr(user, "display_name", None) or str(user.id),
        text=text,
        raw={
            "is_dm": is_dm,
            "guild_id": guild_id_str,
            "attachments": [],
            "member_roles": member_roles,
            "discord_interaction": interaction,
        },
    )


async def _sync_slash_commands(
    tree: "discord.app_commands.CommandTree", account: Connector
) -> None:
    """Sync the ``tree`` against each guild in ``account.config["guilds"]``.

    PUT-style replace per call. Empty or absent ``guilds`` skips with an
    INFO log; per-guild sync failures (``discord.errors.Forbidden`` when
    the bot lacks the ``applications.commands`` scope, network blip,
    guild not found) log at WARNING and continue — the gateway
    connection MUST still go live. Global registration is deferred to
    F10 (per-guild registers in ≤5 minutes vs ≤1 hour for global; F8
    HAT iteration is faster on per-guild).
    """
    guild_ids_raw = account.config.get("guilds") or []
    if not guild_ids_raw:
        logger.info(
            "Discord: no guilds configured for slash command sync on "
            "account %s; skipping",
            account.id,
        )
        return

    for guild_id in guild_ids_raw:
        try:
            await tree.sync(guild=discord.Object(id=int(guild_id)))
        except Exception as exc:
            # Forbidden (missing applications.commands scope), HTTP
            # errors, guild not found — none of these should crash the
            # gateway connect. Log + continue.
            logger.warning(
                "Discord: tree.sync for account %s guild %s failed "
                "(%s: %s); slash commands will not appear in this "
                "guild until the next successful sync",
                account.id,
                guild_id,
                type(exc).__name__,
                exc,
            )


def _build_activity(presence_config: Any) -> discord.Activity:
    """Build a ``discord.Activity`` from the operator's presence config.

    Falls back to the default activity for malformed values. Presence is
    cosmetic — do NOT fail ``connect`` over a typo. A warning is logged
    for malformed input.
    """
    name: str = _DEFAULT_PRESENCE["name"]
    type_name: str = _DEFAULT_PRESENCE["type"]
    if isinstance(presence_config, dict):
        candidate_name = presence_config.get("name")
        candidate_type = presence_config.get("type")
        if isinstance(candidate_name, str) and candidate_name:
            name = candidate_name
        else:
            if candidate_name is not None:
                logger.warning(
                    "Discord presence 'name' must be a non-empty string; "
                    "got %r — falling back to default",
                    candidate_name,
                )
        if isinstance(candidate_type, str) and candidate_type:
            type_name = candidate_type
        else:
            if candidate_type is not None:
                logger.warning(
                    "Discord presence 'type' must be a non-empty string; "
                    "got %r — falling back to default",
                    candidate_type,
                )
    elif presence_config is not None:
        logger.warning(
            "Discord presence config must be a dict; got %r — falling back to "
            "default activity",
            type(presence_config).__name__,
        )
    return discord.Activity(name=name, type=_resolve_activity_type(type_name))


class DiscordClient:
    """Live-connection wrapper for a single Discord account.

    Wraps an SDK :class:`discord.Client` instance plus the background
    asyncio task running the gateway pump. Structurally satisfies the
    :class:`ConnectorClient` Protocol via :meth:`is_alive` + :meth:`send`.

    **Instance fields** (per the L3 spec; L5 added ``_account_id``):

    - ``_client``: the wrapped SDK instance.
    - ``_connection_task``: the spawned background task running
      ``Client.connect(reconnect=True)`` until disconnect.
    - ``_ready_event``: ``asyncio.Event`` set by the SDK's ``on_ready``
      handler. ``is_alive()`` reports True only after this fires.
    - ``_user``: ``client.user`` snapshot captured at READY (for the L7
      doctor probe and debug surfaces).
    - ``_intents``: the intents the client was constructed with (debug
      surface).
    - ``_account_id``: connector account id this client serves. L5's
      :meth:`send` uses it to construct
      :class:`ConnectorConfigError` /
      :class:`ConnectorRateLimitError` envelopes whose constructors
      require an account-id argument.

    Plaintext bot token NOT retained — see module docstring.
    """

    def __init__(
        self,
        client: discord.Client,
        connection_task: asyncio.Task[None],
        ready_event: asyncio.Event,
        intents: discord.Intents,
        account_id: str,
    ) -> None:
        self._client: discord.Client = client
        self._connection_task: asyncio.Task[None] = connection_task
        self._ready_event: asyncio.Event = ready_event
        self._intents: discord.Intents = intents
        self._account_id: str = account_id
        # Captured at READY by the on_ready handler installed in
        # :meth:`DiscordPlugin.connect`; the handler reaches across into
        # this instance via closure. ``ClientUser | None`` because the
        # SDK's ``client.user`` is ``None`` pre-READY.
        self._user: discord.ClientUser | None = client.user

    def is_alive(self) -> bool:
        """Return True iff the gateway connection is healthy.

        Healthy ≡ READY fired AND the SDK client is not closed AND the
        background gateway task has not crashed with an exception.
        """
        # Task crashed terminally → not alive.
        if self._connection_task.done():
            # If the task finished with an exception, it terminated
            # abnormally; if it finished cleanly (e.g. SDK closed itself
            # on shutdown), is_closed() will report True below.
            if self._connection_task.exception() is not None:
                return False
        if self._client.is_closed():
            return False
        return self._ready_event.is_set()

    async def send(
        self,
        target: OutboundTarget,
        content: str,
    ) -> SendResult:
        """Deliver ``content`` to ``target`` via the SDK.

        Channel-resolution ladder (M10 F8 L5):

        1. If ``target.thread_id`` is set, try ``client.get_channel(int(thread_id))``.
           If it returns a :class:`discord.Thread`, send via the thread.
           If it returns anything else (or ``None``) — operator
           misconfigured, or the thread is no longer cached — fall
           through to the channel-only path. Be tolerant; don't raise.
        2. Channel-only path: ``client.get_channel(int(channel_id))``
           reads the SDK's in-process cache. On cache miss (None), we
           call ``await client.fetch_channel(int(channel_id))`` which
           makes a REST GET to ``/channels/{id}``. If the fetch returns
           ``None`` or raises :class:`discord.errors.NotFound`, raise
           :class:`ConnectorConnectionError` — the channel is genuinely
           unreachable.

        Error mapping (each maps a discord.py exception class to a
        :class:`ConnectorClientError` subclass; the F4 platform-send
        tool catches the base ``ConnectorClientError`` and translates
        to an ``[error] ...`` envelope):

        - :class:`discord.errors.Forbidden` → :class:`ConnectorConfigError`
          ("bot lacks send permission in channel X")
        - :class:`discord.errors.NotFound` → :class:`ConnectorConnectionError`
          ("channel X not found")
        - :class:`discord.errors.HTTPException` with ``status == 429`` →
          :class:`ConnectorRateLimitError` (carrying ``retry_after``
          when the SDK populates it)
        - Other :class:`discord.errors.HTTPException` →
          :class:`ConnectorConnectionError` ("send failed: …")
        - All other exceptions propagate — the F4 tool's
          :class:`ConnectorClientError` catch lets them surface to the
          caller's BaseException handler.

        Returns a :class:`SendResult` with ``platform_message_id`` set
        to the Discord message snowflake (as a string) and ``details``
        carrying the destination channel id + channel-type name.
        """
        destination = await self._resolve_destination(target)

        try:
            sent_message = await destination.send(content)
        except discord.errors.Forbidden as exc:
            raise ConnectorConfigError(
                self._account_id,
                f"Discord bot lacks send permission in channel {target.channel_id}",
            ) from exc
        except discord.errors.NotFound as exc:
            raise ConnectorConnectionError(
                f"Discord channel {target.channel_id} not found"
            ) from exc
        except discord.errors.HTTPException as exc:
            # discord.py 2.4+ surfaces ``status`` as the HTTP status
            # code on :class:`HTTPException`. 429 is the rate-limit
            # status; retry_after is the SDK-parsed hint (None if the
            # platform didn't supply one).
            if getattr(exc, "status", None) == 429:
                retry_after_raw = getattr(exc, "retry_after", None)
                retry_after_seconds: float | None
                if retry_after_raw is None:
                    retry_after_seconds = None
                else:
                    try:
                        retry_after_seconds = float(retry_after_raw)
                    except (TypeError, ValueError):
                        retry_after_seconds = None
                raise ConnectorRateLimitError(
                    self._account_id,
                    retry_after_seconds=retry_after_seconds,
                ) from exc
            raise ConnectorConnectionError(
                f"Discord send failed: {exc}"
            ) from exc

        # Defensive — the SDK contract guarantees a Message back from
        # ``channel.send`` on success. If it ever returns None we'd
        # rather surface a typed connector error than a confusing
        # AttributeError downstream.
        if sent_message is None:
            raise ConnectorConnectionError("Discord send returned None")

        return SendResult(
            platform_message_id=str(sent_message.id),
            details={
                "channel_id": str(destination.id),
                "channel_type": destination.type.name,
            },
        )

    async def _resolve_destination(self, target: OutboundTarget) -> Any:
        """Walk the thread-first / channel-second resolution ladder.

        Returns the SDK channel / thread object to ``send`` to. Raises
        :class:`ConnectorConnectionError` if no destination can be
        resolved (cache miss AND ``fetch_channel`` returns ``None`` or
        raises :class:`discord.errors.NotFound`).

        Resolution order:

        1. ``target.thread_id`` is set: ``client.get_channel(int(thread_id))``.
           If it returns a :class:`discord.Thread`, use it. Otherwise
           (None or non-Thread object — operator misconfiguration or
           thread no longer cached) fall through to the channel path.
        2. Channel path: ``client.get_channel(int(channel_id))`` first
           (cache hit, instant). On ``None``, ``await
           client.fetch_channel(int(channel_id))`` (one REST GET).
           Translate :class:`discord.errors.NotFound` from the REST
           layer into :class:`ConnectorConnectionError` so the channel-
           not-found surface looks the same as the
           :meth:`destination.send` NotFound path.
        """
        # 1. Thread-first preference.
        if target.thread_id is not None:
            thread_candidate = self._client.get_channel(int(target.thread_id))
            if isinstance(thread_candidate, discord.Thread):
                return thread_candidate

        # 2. Channel-only path.
        channel = self._client.get_channel(int(target.channel_id))
        if channel is not None:
            return channel

        try:
            channel = await self._client.fetch_channel(int(target.channel_id))
        except discord.errors.NotFound as exc:
            raise ConnectorConnectionError(
                f"Discord channel {target.channel_id} not found"
            ) from exc

        if channel is None:
            raise ConnectorConnectionError(
                f"Discord channel {target.channel_id} not found"
            )
        return channel

    async def close(self) -> None:
        """Close the SDK client and wind down the spawned gateway task.

        Idempotent — calling ``close`` on an already-closed client is a
        no-op (we still ``await`` the task once to ensure it has
        terminated). The background task is given up to
        :data:`_CLOSE_TASK_TIMEOUT_SECONDS` to wind down on its own;
        beyond that, it is cancelled.

        :meth:`DiscordPlugin.disconnect` delegates to this method so the
        SDK-handle reach-through stays encapsulated on the wrapper.
        """
        # Closing an already-closed SDK client is a no-op per discord.py.
        if not self._client.is_closed():
            try:
                await self._client.close()
            except Exception:
                logger.exception(
                    "Discord SDK Client.close raised during DiscordClient.close"
                )

        if self._connection_task.done():
            # Task already finished; drain any unobserved exception so
            # asyncio's "task exception was never retrieved" warning is
            # quiet. We swallow it because close() is supposed to be
            # idempotent / non-raising.
            try:
                exc = self._connection_task.exception()
                if exc is not None:
                    logger.debug(
                        "Discord gateway task ended with exception "
                        "(observed during close): %r",
                        exc,
                    )
            except asyncio.CancelledError:
                pass
            return

        try:
            await asyncio.wait_for(
                asyncio.shield(self._connection_task),
                timeout=_CLOSE_TASK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Discord gateway task did not wind down within %ss after "
                "close; cancelling",
                _CLOSE_TASK_TIMEOUT_SECONDS,
            )
            self._connection_task.cancel()
            try:
                await self._connection_task
            except (asyncio.CancelledError, Exception):
                pass
        except asyncio.CancelledError:
            # The task was cancelled mid-wait — propagate the cancel
            # silently; close() is a teardown surface, not a place to
            # surface CancelledError to callers.
            pass
        except Exception:
            logger.exception(
                "Discord gateway task raised during DiscordClient.close drain"
            )


class DiscordPlugin:
    """:class:`ConnectorPlugin` adapter for Discord.

    Structurally satisfies the Protocol via the four method names below.
    Stateless at the type level — per-connection state lives on the
    :class:`DiscordClient` instance returned by :meth:`connect`.

    :meth:`doctor` (L7) and :meth:`normalize_session_key` (L4) still
    raise :class:`NotImplementedError`; L3 fills in :meth:`connect` and
    :meth:`disconnect`.
    """

    async def connect(
        self,
        account: Connector,
        encryptor: Encryptor,
    ) -> DiscordClient:
        """Open the Discord gateway connection and return a wrapper.

        Reads ``account.secrets['BOT_TOKEN']`` (already-decrypted
        plaintext per the repository's secrets-blob envelope; the
        ``encryptor`` parameter is received to satisfy the F1 Protocol
        but not consumed at this site). Constructs a
        :class:`discord.Client` with the required intents
        (``message_content``, ``members``, ``guilds``), spawns a
        background task running ``Client.connect(reconnect=True)``, and
        awaits the SDK's ``on_ready`` event.

        Outer reconnect: 5 attempts with exponential backoff
        (1s, 2s, 4s, 8s, 16s). Retryable errors:
        :class:`discord.errors.GatewayNotFound`,
        :class:`discord.errors.ConnectionClosed`,
        :class:`aiohttp.ClientError`, :class:`asyncio.TimeoutError`,
        :class:`discord.errors.HTTPException` (e.g. rate-limit 429).
        Fail-fast errors: :class:`discord.errors.LoginFailure`,
        :class:`discord.errors.PrivilegedIntentsRequired`.

        On budget exhaustion, raises
        :class:`ConnectorConnectionError`. The spawned background task
        is always cancelled before propagating any error so the pool's
        ``_entry_worker`` ``BaseException`` catch at ``_pool.py:211``
        does not see a leaked task.
        """
        token = account.secrets["BOT_TOKEN"]
        intents = discord.Intents.default()
        # M11 F1 L2: intents flow through ``account.config["intents"]``
        # with True-fallback defaults. The fallback preserves M10 F8
        # backward compatibility byte-identically — accounts without
        # ``config["intents"]`` get all three intents True, matching the
        # pre-L2 hardcoded behavior. The API-layer validator
        # (:func:`_validate_connector_config`) gates the shape at
        # write time, so any malformed ``config["intents"]`` reaching the
        # plugin originated from a direct DB edit outside the API write
        # path (the F1 single-user local-tool trust posture treats that
        # as the operator's problem).
        intents_cfg = account.config.get("intents", {})
        intents.message_content = intents_cfg.get("message_content", True)
        intents.members = intents_cfg.get("members", True)
        intents.guilds = intents_cfg.get("guilds", True)
        if intents.message_content is False:
            # M11 F1 L2 deviation note: the M10 F8 baseline had no log
            # for disabled intents because they couldn't be disabled
            # (hardcoded True). The WARNING-log is novel and surfaces
            # what would otherwise be a silent silence — a bot whose
            # message_content intent is False reads every channel
            # message as an empty string with no observable error.
            logger.warning(
                "Discord intents.message_content disabled in config for "
                "account %s; bot will silently receive no channel messages",
                account.id,
            )

        activity = _build_activity(account.config.get("presence"))
        ready_timeout = float(
            account.config.get(
                "ready_timeout_seconds", _DEFAULT_READY_TIMEOUT_SECONDS
            )
        )

        last_error: BaseException | None = None
        for attempt_idx, backoff_seconds in enumerate(
            _RECONNECT_BACKOFF_SECONDS
        ):
            try:
                discord_client = await self._attempt_connect(
                    token=token,
                    intents=intents,
                    activity=activity,
                    ready_timeout=ready_timeout,
                    account=account,
                )
            except (
                discord.errors.LoginFailure,
                discord.errors.PrivilegedIntentsRequired,
            ) as exc:
                # Fail-fast — config errors, not transient. Surface as
                # ConnectorConnectionError with a small-model-friendly
                # message; the typed exception subclass is preserved in
                # __cause__ for richer debug surfaces.
                hint = self._fail_fast_hint(exc)
                raise ConnectorConnectionError(
                    f"Discord gateway connect rejected: {hint}"
                ) from exc
            except (
                discord.errors.GatewayNotFound,
                discord.errors.ConnectionClosed,
                discord.errors.HTTPException,
                aiohttp.ClientError,
                asyncio.TimeoutError,
            ) as exc:
                last_error = exc
                if attempt_idx < len(_RECONNECT_BACKOFF_SECONDS) - 1:
                    logger.warning(
                        "Discord gateway connect attempt %d/%d failed "
                        "(%s: %s); retrying in %ss",
                        attempt_idx + 1,
                        len(_RECONNECT_BACKOFF_SECONDS),
                        type(exc).__name__,
                        exc,
                        backoff_seconds,
                    )
                    await asyncio.sleep(backoff_seconds)
                    continue
                # Final attempt — fall through to budget-exhausted raise.
            else:
                # Success: token reference released here when the
                # function returns. Plaintext was passed to client.login
                # and is held by the SDK only.
                del token
                return discord_client

        budget_msg = (
            "Discord gateway connect exceeded 5-attempt reconnect budget; "
            "check token validity and intent configuration in the Discord "
            "Developer Portal (the platform may also be rate-limiting; "
            "retry later)"
        )
        raise ConnectorConnectionError(budget_msg) from last_error

    async def _attempt_connect(
        self,
        *,
        token: str,
        intents: discord.Intents,
        activity: discord.Activity,
        ready_timeout: float,
        account: Connector,
    ) -> DiscordClient:
        """Run one connect attempt.

        Constructs a fresh :class:`discord.Client`, installs the
        ``on_ready`` AND ``on_message`` handlers, calls
        ``client.login(token)``, spawns the background
        ``client.connect()`` task, awaits the ``on_ready`` event with
        ``ready_timeout`` seconds, and returns the :class:`DiscordClient`
        wrapper.

        ``account`` is closed-over by the ``on_message`` handler so it
        can resolve ``account.id`` (for the dispatcher entry point) and
        ``account.config["ingest_bots"]`` (the bot-filter operator
        override). The handler resolves the :class:`AgentFactory` via
        :func:`the_one.agent.factory.get_factory` at dispatch time —
        the module-level accessor pattern (M10 F8 L4) decouples the
        gateway-listener's factory access from the pool's
        per-(agent, account) acquire signature.

        On any error after the background task has been spawned, the
        task is cancelled and awaited before re-raising so the caller
        does not leak it. This is the L3 invariant called out in the
        cycle-1 design review.
        """
        client = discord.Client(intents=intents)
        ready_event = asyncio.Event()

        @client.event  # type: ignore[misc]  # event decorator returns the coroutine
        async def on_ready() -> None:
            ready_event.set()

        @client.event  # type: ignore[misc]
        async def on_message(message: discord.Message) -> None:
            """Translate inbound Discord messages → F7 dispatcher.

            Wraps the dispatcher entry in try/except + ``logger.exception``
            so a handler failure does NOT kill the gateway loop (the SDK
            re-fires ``on_message`` per inbound; a single dispatch
            failure should isolate to that envelope). Mirrors the
            graceful-failure isolation contract documented at
            ``_inbound.py``'s dispatcher BaseException catch.

            Filter order (per the L4 spec):

            1. ``message.author.bot`` AND not ``account.config["ingest_bots"]``
               → skip (default-filter; prevents bot-feedback loops).
            2. ``message.author.id == client.user.id`` → skip (defensive
               self-filter, always-on even with ``ingest_bots=True``).
            3. Translate via L4's pure-function helper.
            4. Dispatch via :func:`dispatch_inbound`.

            The factory is resolved at dispatch time via
            :func:`get_factory`. ``None`` means the lifespan hasn't yet
            called :func:`set_factory` (or has torn down) — log at
            WARNING and return; the platform message is effectively
            dropped for the brief race window.
            """
            try:
                # Default-filter: ignore bot authors (including this bot
                # itself, which IS the most common case — every outbound
                # message the bot delivers gets re-fired as on_message).
                author = message.author
                if getattr(author, "bot", False) and not account.config.get(
                    "ingest_bots", False
                ):
                    return

                # Defensive self-filter: even with ``ingest_bots=True``,
                # never ingest our own messages. Guarded against the
                # pre-READY ``client.user is None`` window for paranoia
                # (on_ready fires before on_message in practice, but
                # the SDK does not guarantee strict ordering and the
                # AttributeError would be ugly).
                if (
                    client.user is not None
                    and getattr(author, "id", None) == client.user.id
                ):
                    return

                # Factory access — module-level accessor (M10 F8 L4
                # option (b)). Returns None pre-startup / post-shutdown;
                # log + return gracefully.
                from the_one.agent.factory import get_factory

                factory = get_factory()
                if factory is None:
                    logger.warning(
                        "Discord on_message: AgentFactory not yet installed "
                        "(lifespan startup may not have run); dropping "
                        "inbound for account %s",
                        account.id,
                    )
                    return

                # Local imports — translate helper and dispatcher both
                # live behind import paths that may transitively touch
                # the DB connection layer; defer import until handler
                # runtime to mirror the load-cycle-safety convention
                # used elsewhere in the connectors subsystem (e.g.
                # ``_inbound.dispatch_inbound``'s function-local imports).
                from the_one.connectors._discord_translate import (
                    _translate_discord_message_to_envelope,
                )
                from the_one.connectors._inbound import dispatch_inbound

                envelope = _translate_discord_message_to_envelope(
                    message, account.id
                )
                await dispatch_inbound(account.id, envelope, factory=factory)
            except Exception:
                # Graceful-failure isolation: log and return so the SDK
                # gateway loop keeps running for the next inbound.
                logger.exception(
                    "Discord on_message handler failed for account %s",
                    account.id,
                )

        # ── M10 F8 L9: slash-command tree construction ───────────────
        #
        # Build a :class:`discord.app_commands.CommandTree` bound to the
        # client and register the 6 v1 commands. The decorator captures
        # ``account`` + ``client`` via closure; each body translates the
        # ``discord.Interaction`` into an :class:`InboundEnvelope` whose
        # text mirrors the F7 text-prefix form (``/<name> <args>``) and
        # routes through the same :func:`dispatch_inbound` path the
        # ``on_message`` handler uses. The dispatcher's step 11 consults
        # :meth:`DiscordPlugin.handle_command` (returns ``None`` for all
        # commands in L9) and falls through to the F7 built-in handlers
        # — slash invocations therefore inherit the v1 vocabulary
        # byte-for-byte; ephemeral-response customizations are deferred
        # to F10 hardening.
        #
        # Each body acknowledges via ``interaction.response.defer()`` to
        # satisfy Discord's 3-second interaction timeout; the visible
        # reply is posted by the dispatcher's outbound ``client.send``
        # path in the same channel. The acknowledgement is ephemeral so
        # only the invoking peer sees the placeholder.
        tree = discord.app_commands.CommandTree(client)

        def _make_slash_body(name: str) -> Any:
            async def _slash_command(
                interaction: discord.Interaction,
                args: str = "",
            ) -> None:
                try:
                    # Ack first so Discord doesn't fail the interaction
                    # while we run dispatch (which may make REST calls).
                    try:
                        await interaction.response.defer(ephemeral=True)
                    except Exception:
                        # If the interaction was already responded to
                        # (defensive — should not happen in our flow),
                        # log and continue with dispatch so the operator
                        # still gets a reply via the outbound path.
                        logger.exception(
                            "Discord slash /%s: defer failed for "
                            "interaction on account %s",
                            name,
                            account.id,
                        )

                    from the_one.agent.factory import get_factory

                    factory = get_factory()
                    if factory is None:
                        logger.warning(
                            "Discord slash /%s: AgentFactory not yet "
                            "installed (lifespan startup may not have "
                            "run); dropping interaction for account %s",
                            name,
                            account.id,
                        )
                        return

                    from the_one.connectors._inbound import dispatch_inbound

                    envelope = _build_slash_envelope(
                        interaction=interaction,
                        account_id=account.id,
                        command_name=name,
                        args=args,
                    )
                    await dispatch_inbound(
                        account.id, envelope, factory=factory
                    )
                except Exception:
                    # Graceful-failure isolation: log and return; a
                    # single slash failure must not crash the gateway.
                    logger.exception(
                        "Discord slash /%s: handler failed for account %s",
                        name,
                        account.id,
                    )

            _slash_command.__name__ = f"slash_{name}"
            return _slash_command

        for _cmd_name, _cmd_desc in _SLASH_COMMAND_VOCAB:
            tree.command(name=_cmd_name, description=_cmd_desc)(
                _make_slash_body(_cmd_name)
            )

        connection_task: asyncio.Task[None] | None = None
        try:
            # ``login`` exchanges the token for an auth session; raises
            # LoginFailure on a rejected token. PrivilegedIntentsRequired
            # is raised from ``connect`` (gateway IDENTIFY), NOT from
            # ``login`` — the outer try/except still catches both
            # because the gateway task surfaces them.
            await client.login(token)

            connection_task = asyncio.create_task(
                client.connect(reconnect=True),
                name="discord-gateway-pump",
            )

            # Race the ready event against the connection task. If the
            # connection task finishes (or raises) before READY, we want
            # to observe it rather than block on the ready event for the
            # full ready_timeout.
            ready_waiter = asyncio.create_task(
                ready_event.wait(), name="discord-ready-wait"
            )
            try:
                done, _pending = await asyncio.wait(
                    {ready_waiter, connection_task},
                    timeout=ready_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not ready_waiter.done():
                    ready_waiter.cancel()
                    try:
                        await ready_waiter
                    except (asyncio.CancelledError, Exception):
                        pass

            if not done:
                # Neither task completed within ready_timeout — treat
                # as a transient connect failure (retryable).
                raise asyncio.TimeoutError(
                    f"Discord on_ready did not fire within {ready_timeout}s"
                )

            if connection_task in done and not ready_event.is_set():
                # The gateway task ended (or raised) before READY fired
                # — surface its exception so the outer reconnect loop
                # can classify it.
                exc = connection_task.exception()
                if exc is not None:
                    raise exc
                # Task ended cleanly without READY — odd but treat as
                # transient.
                raise ConnectorConnectionError(
                    "Discord gateway closed before READY fired"
                )

            # READY fired — set presence and return the wrapper.
            try:
                await client.change_presence(activity=activity)
            except Exception:
                # Presence is cosmetic — log and continue.
                logger.warning(
                    "Discord change_presence failed; activity not set",
                    exc_info=True,
                )

            # ── M10 F8 L9: per-guild slash-command sync ──────────────
            #
            # PUT-style replace of the guild-scoped command list against
            # the current ``tree`` contents. Operator-configured guild
            # list (``account.config["guilds"]``); absent or empty list
            # → no guilds get the slash commands registered. Sync
            # failures (network blip, missing ``applications.commands``
            # scope → :class:`discord.errors.Forbidden`, guild not
            # found) are logged at WARNING and DO NOT propagate — the
            # gateway connection still goes live; slash commands just
            # won't appear in that guild until the next successful sync.
            await _sync_slash_commands(tree, account)

            wrapper = DiscordClient(
                client=client,
                connection_task=connection_task,
                ready_event=ready_event,
                intents=intents,
                account_id=account.id,
            )
            # Refresh the captured user after READY (constructor saw
            # pre-READY None).
            wrapper._user = client.user
            return wrapper
        except BaseException:
            # Cleanup on any error path AFTER the background task was
            # spawned — the pool's _entry_worker BaseException catch
            # would otherwise leak this task. See L3 spec edge case
            # "Spawned-task cleanup on connect error".
            if connection_task is not None and not connection_task.done():
                connection_task.cancel()
                try:
                    await connection_task
                except (asyncio.CancelledError, Exception):
                    pass
            # Also close the SDK client to release the aiohttp session
            # opened by ``login``. ``close`` is idempotent in discord.py.
            try:
                if not client.is_closed():
                    await client.close()
            except Exception:
                logger.exception(
                    "Discord SDK close raised during connect-error cleanup"
                )
            raise

    @staticmethod
    def _fail_fast_hint(exc: BaseException) -> str:
        """Render a small-model-friendly hint for fail-fast connect errors."""
        if isinstance(exc, discord.errors.LoginFailure):
            return (
                "the bot token was rejected by Discord (LoginFailure); "
                "rotate the token in the Discord Developer Portal and "
                "update the connector account's BOT_TOKEN secret"
            )
        if isinstance(exc, discord.errors.PrivilegedIntentsRequired):
            return (
                "the bot is missing a required privileged intent "
                "(PrivilegedIntentsRequired); enable Message Content and "
                "Guild Members intents in the Discord Developer Portal "
                "for this application"
            )
        return f"{type(exc).__name__}: {exc}"

    async def disconnect(self, client: ConnectorClient) -> None:
        """Close the Discord gateway and wind down the background task.

        Delegates to :meth:`DiscordClient.close` so SDK access stays
        encapsulated on the wrapper. Idempotent — a second call on an
        already-closed client is a no-op.

        The pool guarantees ``disconnect`` runs on the same task as
        ``connect`` per :func:`the_one.connectors._pool._entry_worker`.
        """
        # The Protocol allows any ConnectorClient; in practice the pool
        # only ever passes back the DiscordClient instance we returned
        # from connect. Cast to silence the type checker without
        # introducing a runtime isinstance gate (the pool's contract
        # already ensures the shape).
        await cast(DiscordClient, client).close()

    async def doctor(
        self,
        account: Connector,
        encryptor: Encryptor,
    ) -> DoctorReport:
        """Run five read-only probes against the operator's Discord credentials.

        Mirrors the M07 MCP inspector shape: ``status`` ∈
        {ok, degraded, failed}; a one-sentence ``message``; structured
        ``details`` with per-check sub-results.

        Probes (short-circuit on the first FAILED step among 1-4):

        1. **token-valid** — HTTP GET ``/users/@me`` with ``Bot <token>``.
        2. **application-summary** — HTTP GET ``/oauth2/applications/@me``.
        3. **intent-coverage** — parse the application's ``flags``
           bitfield for ``GATEWAY_MESSAGE_CONTENT`` (bit 18) and
           ``GATEWAY_GUILD_MEMBERS`` (bit 14).
        4. **gateway-connect** — short-lived :class:`discord.Client`
           session with the same intents as :meth:`connect`; await
           ``on_ready`` with a 30s timeout; close immediately. NO
           ``on_message`` handler registered → no message dispatch.
        5. **allowlist-resolution** — for each
           ``account.config["allowlist"]["guilds"]`` (defensive; empty /
           absent → skip): HTTP GET
           ``/guilds/{id}/members/{bot_user_id}``. 200 = reachable;
           403/404 = unreachable.

        Reads ``account.secrets['BOT_TOKEN']`` (already-decrypted
        plaintext per the repository's secrets-blob envelope; the
        ``encryptor`` parameter is received to satisfy the F1 Protocol
        but not consumed at this site). The encryption-rotation
        invariant is preserved at the repository layer
        (``ConnectorRepository._ciphertext_to_secrets``
        decrypts the whole ``secrets`` blob at row-load time), so the
        plugin does not capture or call the encryptor.
        """
        # Per-check accumulator. Each entry: {status: ok|degraded|failed,
        # message?, ...platform-fields}.
        checks: dict[str, dict[str, Any]] = {}
        details: dict[str, Any] = {
            "checks": checks,
            "application_id": None,
            "bot_user_id": None,
            "bot_username": None,
            "unreachable_guilds": [],
        }

        # ``account.secrets`` arrives plaintext — the repository decrypts
        # the whole blob at row-load time. We pass-through here and let
        # ``del token`` release the local reference when probes complete.
        token = account.secrets["BOT_TOKEN"]

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bot {token}"}

            # ---- 1. Token-valid probe -------------------------------
            token_result = await self._probe_token_valid(session, headers)
            checks["token"] = token_result
            if token_result["status"] == "ok":
                details["bot_user_id"] = token_result.get("bot_user_id")
                details["bot_username"] = token_result.get("bot_username")
            if token_result["status"] == "failed":
                # Release the plaintext reference and return early.
                del token
                return DoctorReport(
                    status="failed",
                    message=f"Discord probe failed: {token_result['message']}",
                    details=details,
                )

            # ---- 2. Application-summary probe -----------------------
            app_result = await self._probe_application_summary(
                session, headers
            )
            checks["application"] = app_result
            if app_result["status"] == "ok":
                details["application_id"] = app_result.get("application_id")
            if app_result["status"] == "failed":
                del token
                return DoctorReport(
                    status="failed",
                    message=f"Discord probe failed: {app_result['message']}",
                    details=details,
                )

            # ---- 3. Intent-coverage probe ---------------------------
            flags = app_result.get("flags", 0)
            intent_result = self._probe_intent_coverage(flags)
            checks["intents"] = intent_result
            if intent_result["status"] == "failed":
                del token
                return DoctorReport(
                    status="failed",
                    message=(
                        f"Discord probe failed: {intent_result['message']}"
                    ),
                    details=details,
                )

            # ---- 4. Gateway-connect smoke test ----------------------
            # M11 F2 L5: pass per-account intents so the probe tests
            # against the same intents connect() will use — closes the
            # F1 L2 known gap where probe-says-OK could mask a
            # connect()-silently-receives-nothing case when
            # message_content is operator-disabled.
            gateway_result = await self._probe_gateway_connect(
                token, account.config.get("intents")
            )
            checks["gateway"] = gateway_result
            if gateway_result["status"] == "failed":
                del token
                return DoctorReport(
                    status="failed",
                    message=(
                        f"Discord probe failed: {gateway_result['message']}"
                    ),
                    details=details,
                )

            # ---- 5. Allowlist-resolution probe ----------------------
            allowlist_cfg = account.config.get("allowlist") or {}
            guild_ids: list[Any] = []
            if isinstance(allowlist_cfg, dict):
                raw_guilds = allowlist_cfg.get("guilds") or []
                if isinstance(raw_guilds, list):
                    guild_ids = list(raw_guilds)

            bot_user_id = details["bot_user_id"]
            allowlist_result = await self._probe_allowlist_resolution(
                session, headers, guild_ids, bot_user_id
            )
            checks["allowlist"] = allowlist_result
            details["unreachable_guilds"] = allowlist_result.get(
                "unreachable_guilds", []
            )

            # Release token plaintext reference before composing the
            # final result.
            del token

        # ---- Aggregation -------------------------------------------
        # Determine overall status: failed > degraded > ok.
        # Intent-coverage "degraded" (one missing) → overall degraded.
        # Allowlist with any unreachable guilds → degraded.
        if intent_result["status"] == "degraded":
            return DoctorReport(
                status="degraded",
                message=(
                    f"Discord probe degraded: {intent_result['message']}"
                ),
                details=details,
            )
        if allowlist_result["status"] == "degraded":
            unreachable = allowlist_result.get("unreachable_guilds", [])
            total = len(guild_ids)
            return DoctorReport(
                status="degraded",
                message=(
                    f"Discord probe degraded: {len(unreachable)} of {total} "
                    f"configured guilds are unreachable"
                ),
                details=details,
            )

        return DoctorReport(
            status="ok",
            message="Discord probe ok",
            details=details,
        )

    @staticmethod
    async def _probe_token_valid(
        session: aiohttp.ClientSession, headers: dict[str, str]
    ) -> dict[str, Any]:
        """Probe ``GET /users/@me`` — token authenticates against the REST API."""
        url = "https://discord.com/api/v10/users/@me"
        try:
            async with session.get(url, headers=headers) as response:
                status_code = response.status
                if status_code == 200:
                    try:
                        body = await response.json()
                    except Exception:
                        return {
                            "status": "degraded",
                            "message": (
                                "/users/@me returned 200 but a malformed body"
                            ),
                        }
                    bot_user_id = body.get("id") if isinstance(body, dict) else None
                    bot_username = (
                        body.get("username") if isinstance(body, dict) else None
                    )
                    if bot_user_id is None:
                        # Defensive: malformed Discord response.
                        return {
                            "status": "degraded",
                            "message": (
                                "/users/@me returned 200 but missing 'id' field"
                            ),
                        }
                    return {
                        "status": "ok",
                        "message": "token valid",
                        "bot_user_id": str(bot_user_id),
                        "bot_username": (
                            str(bot_username) if bot_username is not None else None
                        ),
                    }
                if status_code == 401:
                    return {
                        "status": "failed",
                        "message": "token authentication 401",
                    }
                if status_code == 429:
                    return {
                        "status": "degraded",
                        "message": "token check rate-limited (429)",
                    }
                return {
                    "status": "degraded",
                    "message": f"token check returned HTTP {status_code}",
                }
        except aiohttp.ClientError as exc:
            return {
                "status": "failed",
                "message": f"token check transport error: {exc}",
            }

    @staticmethod
    async def _probe_application_summary(
        session: aiohttp.ClientSession, headers: dict[str, str]
    ) -> dict[str, Any]:
        """Probe ``GET /oauth2/applications/@me`` — application metadata."""
        url = "https://discord.com/api/v10/oauth2/applications/@me"
        try:
            async with session.get(url, headers=headers) as response:
                status_code = response.status
                if status_code == 200:
                    try:
                        body = await response.json()
                    except Exception:
                        return {
                            "status": "degraded",
                            "message": (
                                "/oauth2/applications/@me returned 200 but "
                                "a malformed body"
                            ),
                        }
                    if not isinstance(body, dict):
                        return {
                            "status": "degraded",
                            "message": (
                                "/oauth2/applications/@me returned 200 but "
                                "a non-object body"
                            ),
                        }
                    return {
                        "status": "ok",
                        "message": "application metadata reachable",
                        "application_id": (
                            str(body["id"]) if "id" in body else None
                        ),
                        "application_name": body.get("name"),
                        "flags": int(body.get("flags") or 0),
                    }
                if status_code in (401, 404):
                    return {
                        "status": "failed",
                        "message": (
                            f"application metadata unreachable (HTTP "
                            f"{status_code})"
                        ),
                    }
                if status_code == 429:
                    return {
                        "status": "degraded",
                        "message": "application probe rate-limited (429)",
                    }
                return {
                    "status": "degraded",
                    "message": (
                        f"application probe returned HTTP {status_code}"
                    ),
                }
        except aiohttp.ClientError as exc:
            return {
                "status": "failed",
                "message": f"application probe transport error: {exc}",
            }

    @staticmethod
    def _probe_intent_coverage(flags: int) -> dict[str, Any]:
        """Parse the application's ``flags`` for Message-Content / Guild-Members.

        Bit assignments per the Discord developer docs:

        - ``GATEWAY_MESSAGE_CONTENT`` = ``1 << 18`` (262144)
        - ``GATEWAY_GUILD_MEMBERS`` = ``1 << 14`` (16384)

        The application's ``flags`` field bitwise-ORs these two bits when
        the bot is approved for the corresponding privileged intent.
        We also accept the ``_LIMITED`` variants (the bits Discord
        toggles BEFORE the application is verified for >100 guilds —
        same effective meaning for the probe).
        """
        # The "approved" bits — set once Discord allows the privileged
        # intent OR when the bot is in <100 guilds (LIMITED variant).
        # We accept either form. _LIMITED bits per Discord docs:
        # MESSAGE_CONTENT_LIMITED = 1 << 19, GUILD_MEMBERS_LIMITED = 1 << 15.
        gateway_message_content = bool(flags & (1 << 18)) or bool(
            flags & (1 << 19)
        )
        gateway_guild_members = bool(flags & (1 << 14)) or bool(
            flags & (1 << 15)
        )

        if gateway_message_content and gateway_guild_members:
            return {
                "status": "ok",
                "message": "intents approved",
                "message_content": True,
                "guild_members": True,
            }
        if not gateway_message_content and not gateway_guild_members:
            return {
                "status": "failed",
                "message": (
                    "intents Message Content and Guild Members both missing"
                ),
                "message_content": False,
                "guild_members": False,
            }
        # Exactly one of the two is missing → degraded.
        missing = (
            "Message Content"
            if not gateway_message_content
            else "Guild Members"
        )
        return {
            "status": "degraded",
            "message": f"intent {missing} not approved",
            "message_content": gateway_message_content,
            "guild_members": gateway_guild_members,
        }

    @staticmethod
    async def _probe_gateway_connect(
        token: str,
        intents_cfg: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Open a short-lived gateway session; await on_ready with a 30s timeout.

        Constructs a fresh :class:`discord.Client` with intents read from
        ``intents_cfg`` (M11 F2 L5; mirrors :meth:`connect`'s F1 L2
        shape). ``intents_cfg=None`` / ``{}`` → all three intents True
        (M10 F8 byte-identical fallback). Per-axis fallback shape:
        ``intents_cfg.get("<axis>", True)`` for ``message_content``,
        ``members``, ``guilds``. Registers ``on_ready`` only — NO
        ``on_message`` — so the probe dispatches no inbound traffic.
        Closes the SDK client (and awaits the connect task) regardless
        of outcome.
        """
        intents = discord.Intents.default()
        # M11 F2 L5: read intents from per-account config with the same
        # fallback shape as DiscordPlugin.connect (F1 L2). Default None →
        # empty dict → all three intents True (M10 F8 byte-identical).
        cfg = intents_cfg or {}
        intents.message_content = cfg.get("message_content", True)
        intents.members = cfg.get("members", True)
        intents.guilds = cfg.get("guilds", True)

        client = discord.Client(intents=intents)
        ready_event = asyncio.Event()

        @client.event  # type: ignore[misc]
        async def on_ready() -> None:
            ready_event.set()

        connection_task: asyncio.Task[None] | None = None
        try:
            try:
                await client.login(token)
            except discord.errors.LoginFailure as exc:
                return {
                    "status": "failed",
                    "message": f"gateway login rejected: {exc}",
                }
            except Exception as exc:
                return {
                    "status": "failed",
                    "message": f"gateway login error: {exc}",
                }

            connection_task = asyncio.create_task(
                client.connect(reconnect=False),
                name="discord-doctor-gateway-probe",
            )

            ready_waiter = asyncio.create_task(
                ready_event.wait(), name="discord-doctor-ready-wait"
            )
            try:
                done, _pending = await asyncio.wait(
                    {ready_waiter, connection_task},
                    timeout=30.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not ready_waiter.done():
                    ready_waiter.cancel()
                    try:
                        await ready_waiter
                    except (asyncio.CancelledError, Exception):
                        pass

            if not done:
                return {
                    "status": "failed",
                    "message": (
                        "gateway smoke test timed out waiting for on_ready"
                    ),
                }

            if connection_task in done and not ready_event.is_set():
                exc = connection_task.exception()
                if exc is not None:
                    return {
                        "status": "failed",
                        "message": f"gateway connect error: {exc}",
                    }
                return {
                    "status": "failed",
                    "message": (
                        "gateway connection ended before on_ready fired"
                    ),
                }

            return {"status": "ok", "message": "gateway reachable"}
        finally:
            # Always tear down — the probe is short-lived.
            if connection_task is not None and not connection_task.done():
                connection_task.cancel()
                try:
                    await connection_task
                except (asyncio.CancelledError, Exception):
                    pass
            try:
                if not client.is_closed():
                    await client.close()
            except Exception:
                logger.exception(
                    "Discord doctor probe: SDK close raised during cleanup"
                )

    @staticmethod
    async def _probe_allowlist_resolution(
        session: aiohttp.ClientSession,
        headers: dict[str, str],
        guild_ids: list[Any],
        bot_user_id: str | None,
    ) -> dict[str, Any]:
        """Verify the bot is a member of each guild_id in the allowlist."""
        if not guild_ids:
            return {
                "status": "ok",
                "message": "allowlist empty — no guilds to probe",
                "unreachable_guilds": [],
                "reachable_guilds": [],
            }
        if bot_user_id is None:
            # Cannot probe membership without the bot user id; treat as
            # degraded so the operator sees the gap without misclassifying
            # the whole probe as failed (the prior checks already passed).
            return {
                "status": "degraded",
                "message": (
                    "allowlist probe skipped: bot user id unavailable"
                ),
                "unreachable_guilds": [str(g) for g in guild_ids],
                "reachable_guilds": [],
            }

        unreachable: list[str] = []
        reachable: list[str] = []
        for guild_id in guild_ids:
            url = (
                f"https://discord.com/api/v10/guilds/{guild_id}/"
                f"members/{bot_user_id}"
            )
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        reachable.append(str(guild_id))
                    elif response.status in (403, 404):
                        unreachable.append(str(guild_id))
                    else:
                        # Other statuses — treat as unreachable so the
                        # operator investigates.
                        unreachable.append(str(guild_id))
            except aiohttp.ClientError:
                unreachable.append(str(guild_id))

        if unreachable:
            return {
                "status": "degraded",
                "message": (
                    f"{len(unreachable)} of {len(guild_ids)} configured "
                    "guilds are unreachable"
                ),
                "unreachable_guilds": unreachable,
                "reachable_guilds": reachable,
            }
        return {
            "status": "ok",
            "message": "all configured guilds reachable",
            "unreachable_guilds": [],
            "reachable_guilds": reachable,
        }

    def is_dm(self, envelope: InboundEnvelope) -> bool:
        """Return True if the envelope represents a Discord DM.

        Reads ``envelope.raw["is_dm"]``, populated by L4's
        :func:`the_one.connectors._discord_translate._translate_discord_message_to_envelope`
        from ``message.channel.type == discord.ChannelType.private``.

        Defensive: ``raw.get("is_dm", False)`` handles malformed raw
        dicts (the SDK contract should always populate the key, but a
        future translator regression — or hand-constructed test
        envelopes — should not raise here). Coerces to ``bool`` so
        non-bool truthy/falsy values produce a strict bool return.

        Consumed at the inbound-routing consult site
        (:func:`the_one.connectors._routing._agent_admits`) via the
        ``optional-plugin-hook-via-getattr-sentinel`` convention; the
        sentinel default
        (:func:`the_one.connectors._acl._default_not_dm`) returns
        ``False`` for plugins that do not implement this hook (e.g.
        the test-only stub plugin), preserving the historical fail-
        closed behavior of the DMs-only ACL branch for those plugins.
        """
        return bool(envelope.raw.get("is_dm", False))

    def resolve(
        self,
        account: Connector,
        envelope: InboundEnvelope,
    ) -> ResolveOutcome:
        """Discord resolver: DM-from-stranger gates on pairing/approval.

        F9 L1 (M11 mission 11). Returns ``NeedsPairing`` ONLY when the
        envelope is a DM AND the peer is not in
        ``account.config["allowlist"]["peers"]``. Guild messages and
        already-allowlisted peers return ``Permit``. Scope is DM-only
        per F9 §1 design decision; guild-mention scoping is deferred to
        a future flight.

        The dispatcher (``_inbound.py:392``) discovers this method via
        ``getattr(plugin, "resolve", _default_permit)`` and consults its
        outcome at dispatcher step 6, BEFORE routing and the per-session
        lock. The downstream ``NeedsPairing`` arm handles PAIR-prefix
        validation; F9 L2 extends that arm with the pending-approval
        emit path.

        The ``"discord_dm_unknown_peer"`` reason literal is contractual
        — L2's pending-approval emit path and the existing dispatcher
        audit-log entry both rely on a stable, greppable value.
        """
        is_dm = bool(envelope.raw.get("is_dm", False))
        if not is_dm:
            return Permit()
        allowlist = account.config.get("allowlist") or {}
        # M11 F12 L3 — peers stored as structured ``{id, dm_allowed}``
        # dicts; consume the ``id`` field for membership check.
        peers = allowlist.get("peers") or []
        if any(p["id"] == envelope.peer_id for p in peers):
            return Permit()
        return NeedsPairing(reason="discord_dm_unknown_peer")

    def is_mention(self, envelope: InboundEnvelope) -> bool:
        """Return True if the bot is @mentioned in the inbound channel message.

        Reads the raw :class:`discord.Message` from
        ``envelope.raw["discord_message"]`` (populated by L4's
        :func:`the_one.connectors._discord_translate._translate_discord_message_to_envelope`)
        and checks whether the bot's user id (resolved via
        ``message.guild.me.id`` for guild messages — the plugin is
        stateless, the per-guild Member object carries the bot's id)
        appears in ``message.mentions``.

        Defensive:

        - Missing ``discord_message`` key → False (malformed envelope;
          should not occur in practice because the SDK contract is
          enforced by the translator, not by the type system).
        - Missing ``guild`` or ``guild.me`` → False (DM channels lack
          a guild; the F7 policy gate short-circuits ``is_dm`` at
          decision-tree step 1 before consulting ``is_mention``, so
          this fallback only fires for malformed DMs or for guild
          messages where the per-guild Member has not yet synced).

        Consumed at the F7 policy-gate consult site
        (:func:`the_one.connectors._inbound.dispatch_inbound`,
        forthcoming at L8) via the
        ``optional-plugin-hook-via-getattr-sentinel`` convention; the
        sentinel default
        (:func:`the_one.connectors._acl._default_no_mention`) returns
        ``False`` for plugins without this hook (e.g. the test-only
        stub plugin), preserving the silent-by-default branch.
        """
        raw_msg = envelope.raw.get("discord_message")
        if raw_msg is None:
            return False
        guild = getattr(raw_msg, "guild", None)
        if guild is None:
            return False
        me = getattr(guild, "me", None)
        if me is None:
            return False
        bot_id = me.id
        return any(
            getattr(user, "id", None) == bot_id for user in raw_msg.mentions
        )

    async def handle_command(
        self,
        envelope: InboundEnvelope,
        command_name: str,
        args: list[str],
    ) -> CommandResponse | None:
        """Optional plugin-side command handler (M10 F8 L9).

        Structurally satisfies the :class:`CommandHandler` Protocol so
        ``isinstance(DiscordPlugin(), CommandHandler)`` returns True
        (the dispatcher's step 11 consult site at ``_inbound.py:494``
        reaches us via the ``getattr(plugin, "handle_command", None)``
        sentinel). DiscordPlugin opts in to the Protocol additively
        without inheriting from it — per ``agents.md``
        ``structural-Protocol-satisfaction``.

        **L9 behavior**: returns ``None`` for every command (the six v1
        commands ``agents`` / ``talk_to`` / ``whoami`` / ``new`` /
        ``reset`` / ``help`` AND unknown command names). The dispatcher
        falls through to ``_dispatch_builtin_command`` and the F7 v1
        handlers produce the response text — slash invocations inherit
        the text-prefix vocabulary byte-for-byte. Discord-native
        customizations (e.g. ephemeral ``/help``) are deferred to F10
        hardening; the simpler fall-through path keeps L9 scope tight
        and avoids the "two response paths" branching that would have
        to learn the dispatcher's outbound shape.

        ``envelope.text`` already carries the synthesized
        ``/<name> <args>`` form (built in :func:`_build_slash_envelope`
        from the slash interaction); ``command_name`` is the parsed
        command word (``talk_to`` for the registered hyphen-free name,
        OR ``talk-to`` if a user types the text-prefix form into a
        regular channel message).
        """
        # F10 hardening hook — when ephemeral customization lands, the
        # branch below picks a subset of commands to handle natively
        # and returns a ``CommandResponse`` for them. L9 ships the
        # simple uniform fall-through.
        del envelope, command_name, args  # explicit "not consumed"
        return None

    def enumerate_discoverable_entities(
        self, client: ConnectorClient
    ) -> DiscoverableEntities:
        """Snapshot Discord's live cache for the four discoverable axes.

        OPTIONAL plugin hook (M11 F3 L3) — discovered by consumers via
        ``getattr(plugin, "enumerate_discoverable_entities", None)`` with
        ``None`` as the fallback sentinel per ``agents.md``
        ``optional-plugin-hook-via-getattr-sentinel``. The hook is NOT
        declared on the :class:`ConnectorPlugin` Protocol; plugins opt
        in by exposing the method.

        Reads the SDK's gateway-populated caches synchronously
        (``Client.users``, ``Client.guilds``, ``Client.get_all_channels()``,
        ``Guild.roles`` are all in-memory data the SDK's gateway listener
        maintains). The L4 cache sweep is an asyncio task that calls
        this hook directly without ``await`` — see the design decision
        in the leg artifact for the sync-vs-async rationale.

        Axes populated:

        - ``peers``: every user in ``Client.users``. Labels use
          ``@{global_name or name}`` (Discord's username-system
          migration: ``global_name`` is the new display field; older
          accounts still expose only ``name``). Defensively
          deduplicated by id — the SDK's
          ``return list(self._connection._users.values())`` already
          guarantees uniqueness, but the dict-keyed-by-id loop guards
          against scaffold-only duplication and future SDK churn.
        - ``channels``: every ``GuildChannel`` subclass yielded by
          ``Client.get_all_channels()`` — TextChannel, VoiceChannel,
          CategoryChannel, ForumChannel, StageChannel. ``metadata["type"]``
          carries the channel-type token so L5/L6 can filter to
          text-postable channels at the render layer. Thread channels
          are NOT included (``Thread`` is not a ``GuildChannel``); F3
          defers thread-target discoverability to a future leg.
        - ``groups``: every guild in ``Client.guilds``.
          ``metadata["member_count"]`` falls back to ``0`` when the
          intent-gated ``Guild.member_count`` is ``None``.
        - ``roles``: every role of every guild, with
          ``group=f"guild:{guild.id}"`` so the render layer can cluster
          roles by guild.

        Returns a :class:`DiscoverableEntities` snapshot with
        ``fetched_at`` set to ``datetime.now(UTC).isoformat()`` (emits
        the ``+00:00`` offset form).
        """
        # M11 F3 L3: ``discord.Client`` cache read — same ``_client``-access
        # practice as ``disconnect`` at L1068 and the ``_user`` capture at
        # L350. The SDK's gateway listener populates ``users``, ``guilds``,
        # and per-guild ``channels``/``roles``; we read from those caches
        # under the plugin's existing connection-lifetime guarantees. The
        # Protocol allows any ConnectorClient; in practice the pool only
        # ever passes back the DiscordClient instance we returned from
        # connect, so ``cast`` silences the type checker without a runtime
        # isinstance gate (matches the disconnect precedent).
        discord_client = cast(DiscordClient, client)._client

        peers_by_id: dict[str, DiscoverableEntity] = {}
        for user in discord_client.users:
            uid = str(user.id)
            if uid in peers_by_id:
                # Defensive dedup; SDK's ``Client.users`` is already
                # unique-by-id via ``_users.values()``. Pinned by
                # ``test_discord_plugin_enumerate_dedupes_users_defensively``.
                continue
            peers_by_id[uid] = DiscoverableEntity(
                id=uid,
                label=f"@{user.global_name or user.name}",
                group=None,
                metadata={"bot": bool(user.bot)},
            )

        channels: list[DiscoverableEntity] = []
        for channel in discord_client.get_all_channels():
            # Every channel from ``get_all_channels()`` has a guild
            # (the SDK iterates ``for g in self.guilds: yield from
            # g.channels``); no defensive ``getattr`` needed.
            channels.append(
                DiscoverableEntity(
                    id=str(channel.id),
                    label=f"#{channel.name}",
                    group=f"guild:{channel.guild.id}",
                    metadata={"type": str(channel.type)},
                )
            )

        groups: list[DiscoverableEntity] = []
        roles: list[DiscoverableEntity] = []
        for guild in discord_client.guilds:
            groups.append(
                DiscoverableEntity(
                    id=str(guild.id),
                    label=guild.name,
                    group=None,
                    # ``member_count`` is intent-gated; collapse ``None``
                    # to ``0`` for shape stability at the API layer.
                    metadata={"member_count": guild.member_count or 0},
                )
            )
            for role in guild.roles:
                roles.append(
                    DiscoverableEntity(
                        id=str(role.id),
                        label=f"@{role.name}",
                        group=f"guild:{guild.id}",
                        metadata={
                            "position": role.position,
                            "mentionable": role.mentionable,
                        },
                    )
                )

        return DiscoverableEntities(
            peers=list(peers_by_id.values()),
            channels=channels,
            groups=groups,
            roles=roles,
            fetched_at=datetime.now(UTC).isoformat(),
        )

    async def fetch_history(
        self,
        client: ConnectorClient,
        channel_id: str,
        thread_id: str | None,
        limit: int,
    ) -> list[FetchedMessage]:
        """Fetch recent messages from a channel or thread.

        OPTIONAL plugin hook (M11 F7 L10) — discovered by the
        :class:`the_one.tools.connector_history.FetchChannelHistoryTool`
        and :class:`the_one.tools.connector_history.FetchThreadHistoryTool`
        via ``getattr(plugin, "fetch_history", None)`` with ``None`` as
        the fallback sentinel per ``agents.md``
        ``optional-plugin-hook-via-getattr-sentinel``. The hook is NOT
        declared on the :class:`ConnectorPlugin` Protocol; plugins opt
        in by exposing the method.

        Resolution ladder:

        1. When ``thread_id`` is set, resolve the thread via
           ``client._client.get_channel(int(thread_id))`` — Discord's
           SDK exposes threads through the same ``get_channel`` cache
           as channels.
        2. Otherwise resolve the channel via
           ``client._client.get_channel(int(channel_id))``.

        Returns an empty list when the destination cannot be resolved
        (cache miss; deleted channel; thread cleaned up). The L10
        tool's try/except envelope catches SDK-raised exceptions
        propagated from this method.
        """
        discord_client = cast(DiscordClient, client)._client
        target_id = thread_id if thread_id else channel_id
        try:
            destination = discord_client.get_channel(int(target_id))
        except (TypeError, ValueError):
            return []
        if destination is None:
            return []

        history_iter = destination.history(limit=limit)
        messages: list[FetchedMessage] = []
        async for msg in history_iter:
            msg_thread = getattr(msg, "thread", None)
            messages.append(
                FetchedMessage(
                    peer_id=str(msg.author.id),
                    peer_name=getattr(
                        msg.author, "display_name", msg.author.name
                    ),
                    content=msg.content,
                    ts=msg.created_at.isoformat(),
                    thread_id=str(msg_thread.id) if msg_thread else None,
                )
            )
        return messages

    async def fetch_dm_history(
        self,
        client: ConnectorClient,
        peer_id: str,
        limit: int,
    ) -> list[FetchedMessage]:
        """Fetch recent messages from the DM with ``peer_id``.

        OPTIONAL plugin hook (M11 F7 L10) — discovered by
        :class:`the_one.tools.connector_history.FetchDmHistoryTool`
        via ``getattr(plugin, "fetch_dm_history", None)`` with ``None``
        as the fallback sentinel.

        Resolves the :class:`discord.User` via the SDK
        (``fetch_user`` makes a REST GET if the user isn't cached),
        opens the DM channel via ``user.create_dm()`` (idempotent; the
        SDK returns the existing DM if one is open), and iterates
        ``.history(limit=limit)``. ``thread_id`` on the returned
        :class:`FetchedMessage` entries is always ``None`` — DMs do
        not carry the thread concept on Discord.

        Returns an empty list if the user resolution returns ``None``
        (deleted account; unreachable user). SDK-raised exceptions
        propagate to the caller — the L10 tool wraps them in an
        error-envelope dict.
        """
        discord_client = cast(DiscordClient, client)._client
        try:
            user = await discord_client.fetch_user(int(peer_id))
        except (TypeError, ValueError):
            return []
        if user is None:
            return []

        dm_channel = await user.create_dm()
        history_iter = dm_channel.history(limit=limit)
        messages: list[FetchedMessage] = []
        async for msg in history_iter:
            messages.append(
                FetchedMessage(
                    peer_id=str(msg.author.id),
                    peer_name=getattr(
                        msg.author, "display_name", msg.author.name
                    ),
                    content=msg.content,
                    ts=msg.created_at.isoformat(),
                    thread_id=None,
                )
            )
        return messages

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        """Build the canonical :class:`SessionKey` for ``inbound``.

        Five-field shape per F3's normalization decision — channel,
        thread, and peer all participate in the binding. Mirrors
        :meth:`StubPlugin.normalize_session_key` at
        ``_stub.py:200-207`` verbatim. Sync function (matches the
        StubPlugin precedent + the Protocol's ``def`` signature at
        ``base.py:345``).
        """
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
            thread_id=inbound.thread_id,
            peer_id=inbound.peer_id,
        )
