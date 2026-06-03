"""Tests for ``the_one/connectors/_discord.py`` — gateway client + reconnect.

M10 F8 L3 coverage:

1. ``DiscordClient.is_alive()`` happy path (alive after connect, dead after close).
2. Intent construction — ``message_content`` + ``members`` + ``guilds`` all True;
   everything else default.
3. Reconnect with 2 transient failures then success → 3rd attempt connects.
4. Reconnect exhaustion: 5 failures → :class:`ConnectorConnectionError`.
5. Fail-fast: ``LoginFailure`` → no retry; :class:`ConnectorConnectionError`
   propagated on attempt #1.
6. Fail-fast: ``PrivilegedIntentsRequired`` raised from ``connect()`` (not
   ``login()``) → no retry.
7. Presence default ("Watching agent traffic" / ``ActivityType.watching``)
   when ``account.config["presence"]`` is absent.
8. Presence override honored when ``account.config["presence"]`` is set.
9. Token plaintext lifecycle — passed to ``login(token)``; NOT retained
   as an instance attribute on the plugin or client.
10. ``send`` placeholder raises ``NotImplementedError`` with the L5 marker.
11. ``connect`` does NOT return until simulated ``on_ready`` fires.
12. ``disconnect`` is idempotent — second call is a no-op.
13. ``on_ready`` timeout cancels spawned task and is retryable.

The discord SDK is patched at the consumer-import site
(``the_one.connectors._discord.discord``) — mirroring the pattern in
``tests/test_connectors_pool.py`` which monkeypatches
``pool_mod._load_account``. NO real Discord connection; NO network.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from the_one.connectors import _discord as discord_mod
from the_one.connectors._discord import DiscordClient, DiscordPlugin
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import (
    DiscoverableEntities,
    DiscoverableEntity,
    NeedsPairing,
    OutboundTarget,
    Permit,
)
from the_one.connectors.errors import ConnectorConnectionError
from the_one.db.models import Connector
from the_one.encryption import Encryptor


# ─────────────────────────────────────────────────────────────────
# Fixtures / stubs
# ─────────────────────────────────────────────────────────────────


class _StubIntents:
    """Mirrors the subset of ``discord.Intents`` we exercise.

    ``message_content`` / ``members`` / ``guilds`` are the three the
    plugin sets explicitly; the rest stay at their default (False here
    to make the "everything else default" assertion easy).
    """

    def __init__(self) -> None:
        self.message_content = False
        self.members = False
        self.guilds = False
        # A handful of other intents we leave default-False so the
        # assertion in test_intent_construction can compare against
        # them.
        self.presences = False
        self.typing = False
        self.bans = False

    @classmethod
    def default(cls) -> "_StubIntents":
        return cls()


class _StubActivityType:
    playing = "playing"
    watching = "watching"
    listening = "listening"
    competing = "competing"


class _StubChannelType:
    """Mirrors ``discord.ChannelType`` for the translate helper.

    The L4 helper compares ``message.channel.type`` against
    ``ChannelType.public_thread`` / ``private_thread`` / ``private``.
    Stub provides those plus a ``text`` sentinel for guild text channels.
    """

    text = "text"
    public_thread = "public_thread"
    private_thread = "private_thread"
    private = "private"


class _StubActivity:
    """Mirrors ``discord.Activity(**kwargs)`` — we only need name/type."""

    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs.get("name")
        self.type = kwargs.get("type")


class _StubLoginFailure(Exception):
    pass


class _StubPrivilegedIntentsRequired(Exception):
    pass


class _StubGatewayNotFound(Exception):
    pass


class _StubConnectionClosed(Exception):
    pass


class _StubHTTPException(Exception):
    pass


class _StubErrors:
    LoginFailure = _StubLoginFailure
    PrivilegedIntentsRequired = _StubPrivilegedIntentsRequired
    GatewayNotFound = _StubGatewayNotFound
    ConnectionClosed = _StubConnectionClosed
    HTTPException = _StubHTTPException


class _StubClientUser:
    """Stand-in for ``discord.ClientUser`` — only ``id`` + ``name``
    matter for tests that touch ``_user``."""

    def __init__(self, user_id: str = "bot-123", name: str = "test-bot") -> None:
        self.id = user_id
        self.name = name


class _StubDiscordClient:
    """Records constructor + method calls.

    Each instance simulates the lifecycle: ``login(token)`` succeeds;
    ``connect(reconnect=...)`` is a coroutine that awaits an internal
    event (firing it externally simulates "gateway closes"). Tests can
    pre-inject failures via class-level knobs.

    ``event`` decorator captures the ``on_ready`` coroutine; tests fire
    it externally to simulate the gateway emitting the READY event.
    """

    # Per-test instances captured here so tests can introspect.
    instances: list["_StubDiscordClient"] = []

    # Knobs (set by tests BEFORE instantiating the plugin):
    #
    # ``login_failures`` is a list of exceptions to raise on successive
    # ``login`` calls (consumed left-to-right; once empty, login succeeds).
    login_failures: list[BaseException] = []
    # ``connect_failures`` is a list of exceptions to raise on successive
    # ``connect`` calls (consumed left-to-right; once empty, connect blocks
    # on the close event, simulating the SDK's persistent connect loop).
    connect_failures: list[BaseException] = []
    # When True, the next ``connect`` call hangs indefinitely without
    # firing on_ready — exercises the ready-timeout branch.
    hang_connect: bool = False
    # When True, the ``on_ready`` handler is fired automatically as soon
    # as ``connect`` starts running. Default for happy-path tests.
    auto_fire_ready: bool = True

    def __init__(self, *, intents: _StubIntents, **kwargs: Any) -> None:
        self.intents = intents
        self.kwargs = kwargs
        self._closed = False
        self._close_event = asyncio.Event()
        self._on_ready_handler: Any | None = None
        self._on_message_handler: Any | None = None
        self.user: _StubClientUser | None = None
        self.login_calls: list[str] = []
        self.connect_calls: list[dict[str, Any]] = []
        self.close_calls = 0
        self.change_presence_calls: list[_StubActivity | None] = []
        # M11 F3 L3: live-cache surface the plugin's
        # ``enumerate_discoverable_entities`` reads. Tests that exercise
        # the hook populate these post-connect on the wrapped SDK stub;
        # all other tests leave them empty (no observable difference for
        # paths that never touch ``users`` / ``guilds`` /
        # ``get_all_channels()``).
        self.users: list[Any] = []
        self.guilds: list[Any] = []
        type(self).instances.append(self)

    # --- discord.Client surface the plugin actually touches ----------

    def event(self, coro: Any) -> Any:
        """Capture event handlers so tests can fire them on demand.

        Both ``on_ready`` and ``on_message`` (M10 F8 L4) are recorded.
        """
        if coro.__name__ == "on_ready":
            self._on_ready_handler = coro
        elif coro.__name__ == "on_message":
            self._on_message_handler = coro
        return coro

    async def login(self, token: str) -> None:
        self.login_calls.append(token)
        cls = type(self)
        if cls.login_failures:
            raise cls.login_failures.pop(0)

    async def connect(self, *, reconnect: bool = True) -> None:
        cls = type(self)
        self.connect_calls.append({"reconnect": reconnect})
        if cls.connect_failures:
            raise cls.connect_failures.pop(0)
        if cls.auto_fire_ready and self._on_ready_handler is not None:
            # Simulate the SDK firing on_ready as part of the gateway
            # handshake. Set user before firing so the wrapper captures it.
            self.user = _StubClientUser()
            await self._on_ready_handler()
        if cls.hang_connect:
            # Wait forever (until cancelled by the plugin's cleanup path).
            await asyncio.Event().wait()
        # Block until close() is called to simulate the long-running
        # gateway pump.
        await self._close_event.wait()

    async def close(self) -> None:
        self.close_calls += 1
        self._closed = True
        self._close_event.set()

    def is_closed(self) -> bool:
        return self._closed

    def is_ready(self) -> bool:
        # Not used by the plugin (we use ready_event directly), but the
        # SDK has it; defensive.
        return self.user is not None

    async def change_presence(
        self, *, activity: _StubActivity | None = None, **_: Any
    ) -> None:
        self.change_presence_calls.append(activity)

    def get_all_channels(self) -> Any:
        """Yield every guild channel — matches the real SDK shape.

        The real ``discord.Client.get_all_channels`` iterates
        ``for g in self.guilds: yield from g.channels``. The stub
        mirrors that so the plugin's hook receives a fresh generator
        each call.
        """
        for guild in self.guilds:
            yield from guild.channels


class _StubObject:
    """Mirrors ``discord.Object(id=...)`` — guild snowflake holder.

    The plugin's ``tree.sync`` call wraps each operator-configured guild
    id in ``discord.Object(id=int(g))``. We only need to round-trip the
    id for assertion purposes.
    """

    def __init__(self, *, id: int) -> None:  # noqa: A002 — mirrors SDK
        self.id = id


class _StubCommandTree:
    """Mirrors ``discord.app_commands.CommandTree(client)`` for L9 tests.

    Records registered commands + per-guild sync invocations so tests
    can assert the 6-command shape AND the per-guild PUT-style replace
    semantic without spinning up the real Interactions API.

    Class-level knobs:

    - ``sync_should_raise``: tuple of exceptions to raise on successive
      ``sync`` calls (consumed left-to-right). Once empty, sync succeeds.
    """

    instances: list["_StubCommandTree"] = []
    sync_should_raise: list[BaseException] = []

    def __init__(self, client: Any) -> None:
        self.client = client
        # Each entry: {"name": str, "description": str, "callback": coro}.
        self.commands: list[dict[str, Any]] = []
        # Each entry: ``discord.Object`` wrapper instance.
        self.sync_calls: list[Any] = []
        # Ordered log of ALL calls (copy_global_to + sync) for ordering
        # assertions.  Each entry is a tuple: ("copy", guild_obj) or
        # ("sync", guild_obj).
        self.call_log: list[tuple[str, Any]] = []
        # Per-guild buckets populated by copy_global_to; keyed by guild id.
        self.guild_buckets: dict[int, list[dict[str, Any]]] = {}
        type(self).instances.append(self)

    def command(self, *, name: str, description: str) -> Any:
        """Decorator capturing the registered slash-command callback."""
        def _decorator(coro: Any) -> Any:
            self.commands.append(
                {"name": name, "description": description, "callback": coro}
            )
            return coro
        return _decorator

    def copy_global_to(self, *, guild: Any) -> None:
        """Copy the global command list into the per-guild bucket.

        Mirrors ``discord.app_commands.CommandTree.copy_global_to`` — copies
        the current global commands into the guild-scoped registry so that a
        subsequent ``tree.sync(guild=guild)`` includes them.
        """
        self.call_log.append(("copy", guild))
        self.guild_buckets[guild.id] = list(self.commands)

    async def sync(self, *, guild: Any = None) -> list[Any]:
        cls = type(self)
        self.sync_calls.append(guild)
        self.call_log.append(("sync", guild))
        if cls.sync_should_raise:
            raise cls.sync_should_raise.pop(0)
        return []


class _StubAppCommandsModule:
    """Mirrors ``discord.app_commands`` — only ``CommandTree`` is touched."""

    CommandTree = _StubCommandTree


class _StubDiscordModule:
    """Stand-in for the ``discord`` SDK module attached to
    ``the_one.connectors._discord.discord``.
    """

    Client = _StubDiscordClient
    Intents = _StubIntents
    Activity = _StubActivity
    ActivityType = _StubActivityType
    ChannelType = _StubChannelType
    Object = _StubObject
    errors = _StubErrors
    app_commands = _StubAppCommandsModule


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _reset_stub_state() -> None:
    _StubDiscordClient.instances = []
    _StubDiscordClient.login_failures = []
    _StubDiscordClient.connect_failures = []
    _StubDiscordClient.hang_connect = False
    _StubDiscordClient.auto_fire_ready = True
    _StubCommandTree.instances = []
    _StubCommandTree.sync_should_raise = []


def _patch_discord(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the consumer-side ``discord`` symbol on the plugin module."""
    _reset_stub_state()
    monkeypatch.setattr(discord_mod, "discord", _StubDiscordModule)
    # The plugin also imports ``aiohttp`` at module-load — keep the real
    # one (we just rely on its ClientError type for the retryable-error
    # tuple; tests don't raise ClientError directly).


def _make_encryptor() -> Encryptor:
    """Construct a real Encryptor with a one-shot Fernet key.

    The plugin receives :class:`Encryptor` to satisfy the F1
    :class:`ConnectorPlugin` Protocol but does not consume it for
    per-value decryption — the repository
    (``ConnectorRepository._ciphertext_to_secrets``) decrypts
    the whole ``secrets`` blob at row-load time, so
    ``account.secrets["BOT_TOKEN"]`` already arrives as plaintext. We
    still construct a real Encryptor here so any test that passes it
    in exercises the same object shape the runtime uses.
    """
    from cryptography.fernet import Fernet

    return Encryptor(Fernet.generate_key())


def _make_account(
    encryptor: Encryptor,
    *,
    bot_token_plaintext: str = "discord-bot-token-secret",
    presence: dict[str, str] | None = None,
    ready_timeout_seconds: float | None = None,
    intents: dict[str, bool] | None = None,
) -> Connector:
    config: dict[str, Any] = {}
    if presence is not None:
        config["presence"] = presence
    if ready_timeout_seconds is not None:
        config["ready_timeout_seconds"] = ready_timeout_seconds
    if intents is not None:
        config["intents"] = intents
    return Connector(
        id="acct-discord-test",
        name="Discord Test",
        type="discord",
        config=config,
        # The repository decrypts the whole ``secrets`` blob at row-load
        # time, so ``account.secrets["BOT_TOKEN"]`` arrives at the plugin
        # as plaintext. The fixture mirrors that post-load shape.
        secrets={"BOT_TOKEN": bot_token_plaintext},
    )


def _shrink_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the reconnect backoff so retry tests run in <1s.

    Tests that exercise the reconnect schedule do NOT care about the
    real wall-clock delays; they care about the ATTEMPT COUNT and the
    ordering. Shrinking the schedule keeps the test suite fast.
    """
    monkeypatch.setattr(
        discord_mod,
        "_RECONNECT_BACKOFF_SECONDS",
        (0.0, 0.0, 0.0, 0.0, 0.0),
    )


# ─────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────


async def test_is_alive_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """``is_alive`` is True after a successful connect; False after close."""
    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        assert isinstance(client, DiscordClient)
        assert client.is_alive() is True
    finally:
        await plugin.disconnect(client)

    assert client.is_alive() is False


async def test_intent_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """``message_content`` + ``members`` + ``guilds`` True; rest default-False."""
    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        intents = client._intents
        assert intents.message_content is True
        assert intents.members is True
        assert intents.guilds is True
        # Everything else stays default-False on the stub Intents.
        assert intents.presences is False
        assert intents.typing is False
        assert intents.bans is False
    finally:
        await plugin.disconnect(client)


async def test_intents_from_config_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    """All three gateway intents are always-on regardless of config["intents"].

    M11 F17 L6 (Leg B): the config-driven intent knob is removed. Even with
    ``config["intents"]`` disabling message_content, the constructed
    ``discord.Client`` must have all three intents True — the backend always
    requests the full privileged-intent set; PrivilegedIntentsRequired from
    the portal surfaces via Leg A's connect-error path.
    """
    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(
        encryptor,
        intents={"message_content": False, "members": True, "guilds": True},
    )

    client = await plugin.connect(account, encryptor)
    try:
        intents = client._intents
        # All three must be True regardless of the config["intents"] value.
        assert intents.message_content is True
        assert intents.members is True
        assert intents.guilds is True
    finally:
        await plugin.disconnect(client)


@pytest.mark.asyncio
async def test_probe_gateway_intents_from_config_honored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe always requests all three intents regardless of intents_cfg.

    M11 F17 L6 (Leg B): mirrors :func:`test_intents_from_config_honored` on
    the doctor/Validate gateway-probe path. Even with ``message_content``
    explicitly disabled in ``intents_cfg``, the probe's underlying
    ``discord.Client`` must have all three True.
    """
    _patch_discord(monkeypatch)
    intents_cfg = {"message_content": False, "members": True, "guilds": True}
    await DiscordPlugin._probe_gateway_connect(
        "test-token", intents_cfg=intents_cfg
    )
    # Most recently constructed stub client carries the intents.
    last_intents = _StubDiscordClient.instances[-1].intents
    # All three must be True regardless of the intents_cfg value.
    assert last_intents.message_content is True
    assert last_intents.members is True
    assert last_intents.guilds is True


@pytest.mark.asyncio
async def test_probe_gateway_intents_none_defaults_to_all_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11 F2 L5: probe with ``intents_cfg=None`` → all True.

    Byte-identical legacy behavior (M10 F8 baseline) preserved for any
    caller that doesn't pass the new ``intents_cfg`` arg.
    """
    _patch_discord(monkeypatch)
    await DiscordPlugin._probe_gateway_connect("test-token")
    last_intents = _StubDiscordClient.instances[-1].intents
    assert last_intents.message_content is True
    assert last_intents.members is True
    assert last_intents.guilds is True


@pytest.mark.asyncio
async def test_probe_gateway_intents_empty_dict_defaults_to_all_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11 F2 L5: probe with ``intents_cfg={}`` → all True.

    M10 F8 round-trip: accounts without a ``config['intents']`` key
    surface ``{}`` from ``account.config.get('intents', {})`` and the
    probe still applies per-axis ``True`` defaults.
    """
    _patch_discord(monkeypatch)
    await DiscordPlugin._probe_gateway_connect("test-token", intents_cfg={})
    last_intents = _StubDiscordClient.instances[-1].intents
    assert last_intents.message_content is True
    assert last_intents.members is True
    assert last_intents.guilds is True


async def test_reconnect_recovers_after_two_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2 transient failures + success on attempt 3 → connect returns."""
    _patch_discord(monkeypatch)
    _shrink_backoff(monkeypatch)

    _StubDiscordClient.connect_failures = [
        _StubGatewayNotFound("simulated transient #1"),
        _StubConnectionClosed("simulated transient #2"),
    ]

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        # Three Client instances constructed — two failed + one success.
        assert len(_StubDiscordClient.instances) == 3
        assert client.is_alive() is True
    finally:
        await plugin.disconnect(client)


async def test_reconnect_exhaustion_raises_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5 consecutive transient failures → :class:`ConnectorConnectionError`."""
    _patch_discord(monkeypatch)
    _shrink_backoff(monkeypatch)

    _StubDiscordClient.connect_failures = [
        _StubGatewayNotFound(f"simulated failure #{i}") for i in range(5)
    ]

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    with pytest.raises(
        ConnectorConnectionError, match="exceeded 5-attempt reconnect budget"
    ):
        await plugin.connect(account, encryptor)

    # Five attempts consumed.
    assert len(_StubDiscordClient.instances) == 5


async def test_fail_fast_login_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """``LoginFailure`` on attempt #1 → immediate raise; no retry."""
    _patch_discord(monkeypatch)
    _shrink_backoff(monkeypatch)

    _StubDiscordClient.login_failures = [_StubLoginFailure("token revoked")]

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    with pytest.raises(ConnectorConnectionError, match="LoginFailure|token"):
        await plugin.connect(account, encryptor)

    # Only one Client instance constructed — no retry.
    assert len(_StubDiscordClient.instances) == 1


async def test_fail_fast_privileged_intents_required_from_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PrivilegedIntentsRequired`` raised from ``connect()`` → no retry.

    Per the L3 spec edge case: discord.py 2.4+ raises
    ``PrivilegedIntentsRequired`` from ``Client.connect()`` (gateway
    IDENTIFY), NOT from ``Client.login()``. The fail-fast catch in the
    outer reconnect loop MUST wrap the connect step, not just login.
    """
    _patch_discord(monkeypatch)
    _shrink_backoff(monkeypatch)

    _StubDiscordClient.connect_failures = [
        _StubPrivilegedIntentsRequired("intent not enabled in portal")
    ]

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    with pytest.raises(
        ConnectorConnectionError,
        match="PrivilegedIntentsRequired|privileged intent",
    ):
        await plugin.connect(account, encryptor)

    # Only one attempt — fail-fast.
    assert len(_StubDiscordClient.instances) == 1


async def test_presence_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``presence`` is absent, default activity is set on the client."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        sdk_client = _StubDiscordClient.instances[-1]
        assert len(sdk_client.change_presence_calls) == 1
        activity = sdk_client.change_presence_calls[0]
        assert activity is not None
        assert activity.name == "Watching agent traffic"
        assert activity.type == _StubActivityType.watching
    finally:
        await plugin.disconnect(client)


async def test_presence_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``account.config['presence']`` override is honored."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(
        encryptor, presence={"name": "Playing chess", "type": "playing"}
    )

    client = await plugin.connect(account, encryptor)
    try:
        sdk_client = _StubDiscordClient.instances[-1]
        activity = sdk_client.change_presence_calls[0]
        assert activity is not None
        assert activity.name == "Playing chess"
        assert activity.type == _StubActivityType.playing
    finally:
        await plugin.disconnect(client)


async def test_presence_malformed_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed presence config does NOT fail connect — falls back to default."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(
        encryptor, presence={"name": 123, "type": "not-a-real-type"}  # type: ignore[dict-item]
    )

    client = await plugin.connect(account, encryptor)
    try:
        sdk_client = _StubDiscordClient.instances[-1]
        activity = sdk_client.change_presence_calls[0]
        # Name fell back to the default (the int didn't pass validation);
        # type fell back to 'watching' (the unknown type was rejected).
        assert activity is not None
        assert activity.name == "Watching agent traffic"
        assert activity.type == _StubActivityType.watching
    finally:
        await plugin.disconnect(client)


async def test_token_plaintext_not_retained(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plaintext token is passed to ``login`` but NOT held on plugin/client."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    plaintext = "super-secret-discord-token-xyz"
    account = _make_account(encryptor, bot_token_plaintext=plaintext)

    client = await plugin.connect(account, encryptor)
    try:
        # Plaintext WAS passed to login (the SDK needs it).
        sdk_client = _StubDiscordClient.instances[-1]
        assert sdk_client.login_calls == [plaintext]

        # Plaintext is NOT held as an attribute on the plugin or client.
        for obj in (plugin, client):
            for attr_name in dir(obj):
                if attr_name.startswith("__"):
                    continue
                try:
                    value = getattr(obj, attr_name)
                except Exception:
                    continue
                if isinstance(value, str) and value == plaintext:
                    pytest.fail(
                        f"{type(obj).__name__}.{attr_name} retained plaintext token"
                    )

        # Specifically the conventional attribute names that an
        # incautious impl might use are absent.
        for attr_name in ("_token", "_bot_token", "token", "bot_token"):
            assert not hasattr(plugin, attr_name), (
                f"DiscordPlugin must not retain a {attr_name!r} attribute"
            )
            assert not hasattr(client, attr_name), (
                f"DiscordClient must not retain a {attr_name!r} attribute"
            )
    finally:
        await plugin.disconnect(client)


async def test_send_placeholder_is_removed_in_l5() -> None:
    """L5 replaces the L3 placeholder — calling :meth:`DiscordClient.send`
    no longer raises :class:`NotImplementedError`.

    This test exists to make the L3→L5 transition explicit: the
    historical L3 marker test asserted ``NotImplementedError("...L5...")``;
    L5 lands the real implementation. The remaining L5 outbound tests
    below pin the new behavior (resolution ladder, error mapping,
    SendResult shape).
    """
    # Construct a DiscordClient directly with a mock SDK client so we
    # avoid the gateway-startup machinery — the placeholder check is
    # local to send().
    import discord as _real_discord

    sdk = MagicMock(spec=_real_discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = MagicMock()
    channel.id = 1
    channel.type = MagicMock()
    channel.type.name = "text"
    sent_message = MagicMock()
    sent_message.id = 999
    channel.send = AsyncMock(return_value=sent_message)
    sdk.get_channel = MagicMock(return_value=channel)

    task = asyncio.create_task(asyncio.sleep(0))
    await task
    ready = asyncio.Event()
    ready.set()
    client = DiscordClient(
        client=sdk,
        connection_task=task,
        ready_event=ready,
        intents=MagicMock(),
        account_id="acct-l5",
    )

    target = OutboundTarget(channel_id="1", thread_id=None)
    # MUST NOT raise NotImplementedError.
    result = await client.send(target, "hi")
    assert result.platform_message_id == "999"


async def test_connect_blocks_until_on_ready_fires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``connect`` does NOT return until the simulated ``on_ready`` fires."""
    _patch_discord(monkeypatch)
    _shrink_backoff(monkeypatch)

    # Disable auto-fire; we will fire on_ready manually after a delay.
    _StubDiscordClient.auto_fire_ready = False

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor, ready_timeout_seconds=5.0)

    connect_task = asyncio.create_task(plugin.connect(account, encryptor))
    # Yield until the stub Client has been constructed and its connect
    # coroutine is running.
    for _ in range(200):
        await asyncio.sleep(0)
        if _StubDiscordClient.instances and _StubDiscordClient.instances[
            -1
        ].connect_calls:
            break
    sdk_client = _StubDiscordClient.instances[-1]

    # At this point, connect_task MUST still be pending — on_ready
    # hasn't fired.
    assert not connect_task.done()

    # Fire on_ready externally.
    sdk_client.user = _StubClientUser()
    assert sdk_client._on_ready_handler is not None
    await sdk_client._on_ready_handler()

    client = await asyncio.wait_for(connect_task, timeout=2.0)
    try:
        assert client.is_alive() is True
    finally:
        await plugin.disconnect(client)


async def test_disconnect_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second ``disconnect`` on an already-closed client is a no-op."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    await plugin.disconnect(client)
    # Second call MUST NOT raise.
    await plugin.disconnect(client)

    sdk_client = _StubDiscordClient.instances[-1]
    # close() was only effectively called once on the SDK (the first
    # disconnect closed it; the second saw ``is_closed()`` True and
    # skipped).
    assert sdk_client.close_calls == 1


async def test_on_ready_timeout_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """on_ready never fires → attempt times out, cancels spawned task,
    next attempt succeeds.

    Per the L3 spec edge case: if ``on_ready`` never fires, the connect
    call would block indefinitely. We wrap with ``asyncio.wait_for`` /
    equivalent at ``ready_timeout_seconds``; on timeout, the spawned
    background task is cancelled and the attempt is treated as
    retryable. Next attempt succeeds.
    """
    _patch_discord(monkeypatch)
    _shrink_backoff(monkeypatch)

    # First attempt: hang_connect = True (no on_ready, connect blocks).
    # After the first timeout, we flip hang_connect back to False so the
    # SECOND attempt's _StubDiscordClient instance auto-fires on_ready.
    _StubDiscordClient.auto_fire_ready = False
    _StubDiscordClient.hang_connect = True

    original_init = _StubDiscordClient.__init__

    call_count = {"value": 0}

    def _counting_init(self: _StubDiscordClient, **kwargs: Any) -> None:
        original_init(self, **kwargs)
        call_count["value"] += 1
        if call_count["value"] >= 2:
            # Second client onwards: behave normally (auto-fire on_ready
            # in connect()).
            type(self).hang_connect = False
            type(self).auto_fire_ready = True

    monkeypatch.setattr(_StubDiscordClient, "__init__", _counting_init)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    # Tight ready_timeout so the test runs in <1s.
    account = _make_account(encryptor, ready_timeout_seconds=0.05)

    client = await plugin.connect(account, encryptor)
    try:
        assert client.is_alive() is True
        # Two attempts: the first timed out; the second succeeded.
        assert len(_StubDiscordClient.instances) == 2
        # The first attempt's background task was cancelled (no leak).
        first = _StubDiscordClient.instances[0]
        # First-attempt SDK client was closed on cleanup.
        assert first.is_closed() is True
    finally:
        await plugin.disconnect(client)


async def test_plugin_satisfies_connector_plugin_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """:class:`DiscordPlugin` structurally satisfies the
    :class:`ConnectorPlugin` Protocol via ``isinstance``."""
    from the_one.connectors.base import ConnectorPlugin

    assert isinstance(DiscordPlugin(), ConnectorPlugin)


# ─────────────────────────────────────────────────────────────────
# M10 F8 L4 — on_message ingestion + normalize_session_key
# ─────────────────────────────────────────────────────────────────


def _make_msg_author(
    *,
    author_id: int = 4242,
    display_name: str = "Alice",
    is_bot: bool = False,
) -> Any:
    """Synthetic message-author for on_message integration tests."""
    from types import SimpleNamespace

    return SimpleNamespace(
        id=author_id,
        display_name=display_name,
        bot=is_bot,
        roles=[],
    )


def _make_guild_text_msg(
    *,
    author: Any,
    content: str = "hello",
    channel_id: int = 1001,
    guild_id: int = 7777,
) -> Any:
    """Synthetic message in a guild text channel.

    The translate helper imports the REAL ``discord`` package at
    function-runtime, so we use the real ``discord.ChannelType`` values
    for the channel type to make the helper's thread/DM detection work
    correctly.
    """
    import discord
    from types import SimpleNamespace

    channel = SimpleNamespace(
        id=channel_id, type=discord.ChannelType.text, parent=None
    )
    guild = SimpleNamespace(id=guild_id)
    return SimpleNamespace(
        author=author,
        channel=channel,
        content=content,
        attachments=[],
        guild=guild,
    )


async def _connect_and_get_handler(
    plugin: DiscordPlugin,
    encryptor: Encryptor,
    *,
    ingest_bots: bool = False,
) -> tuple[DiscordClient, _StubDiscordClient]:
    """Helper: connect and return the wrapper + stub SDK client."""
    config: dict[str, Any] = {}
    if ingest_bots:
        config["ingest_bots"] = True
    account = Connector(
        id="acct-ingest-test",
        name="Discord Ingest Test",
        type="discord",
        config=config,
        secrets={"BOT_TOKEN": "token-xyz"},
    )
    client = await plugin.connect(account, encryptor)
    sdk_client = _StubDiscordClient.instances[-1]
    return client, sdk_client


async def test_on_message_filters_bot_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot-authored message + no ``ingest_bots`` override → skip dispatch."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    client, sdk_client = await _connect_and_get_handler(plugin, encryptor)
    try:
        dispatch_calls: list[tuple] = []

        async def _fake_dispatch(account_id: str, envelope: Any, *, factory: Any) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: object()
        )

        bot_author = _make_msg_author(author_id=99, is_bot=True)
        msg = _make_guild_text_msg(author=bot_author, content="bot speaking")

        assert sdk_client._on_message_handler is not None
        await sdk_client._on_message_handler(msg)

        # Dispatcher MUST NOT be called.
        assert dispatch_calls == []
    finally:
        await plugin.disconnect(client)


async def test_on_message_allows_bot_with_ingest_bots_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot-authored message + ``ingest_bots=True`` → dispatcher IS called."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    client, sdk_client = await _connect_and_get_handler(
        plugin, encryptor, ingest_bots=True
    )
    try:
        dispatch_calls: list[tuple] = []

        async def _fake_dispatch(account_id: str, envelope: Any, *, factory: Any) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        sentinel_factory = object()
        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: sentinel_factory
        )

        # A different bot — NOT our own (self-filter still applies).
        bot_author = _make_msg_author(author_id=12345, is_bot=True)
        msg = _make_guild_text_msg(author=bot_author, content="bot allowed")

        await sdk_client._on_message_handler(msg)

        assert len(dispatch_calls) == 1
        account_id, envelope, factory = dispatch_calls[0]
        assert account_id == "acct-ingest-test"
        assert factory is sentinel_factory
        assert envelope.platform == "discord"
        assert envelope.peer_id == "12345"
        assert envelope.text == "bot allowed"
    finally:
        await plugin.disconnect(client)


async def test_on_message_self_filtered_even_when_ingest_bots_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``message.author.id == client.user.id`` is always filtered."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    client, sdk_client = await _connect_and_get_handler(
        plugin, encryptor, ingest_bots=True
    )
    try:
        dispatch_calls: list[tuple] = []

        async def _fake_dispatch(account_id: str, envelope: Any, *, factory: Any) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: object()
        )

        # client.user.id is "bot-123" per _StubClientUser default.
        assert sdk_client.user is not None
        self_id = sdk_client.user.id
        self_author = _make_msg_author(author_id=self_id, is_bot=True)
        msg = _make_guild_text_msg(author=self_author, content="own echo")

        await sdk_client._on_message_handler(msg)

        # Self-filter kicks even with ingest_bots=True.
        assert dispatch_calls == []
    finally:
        await plugin.disconnect(client)


async def test_on_message_happy_path_dispatches_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Human user → dispatch_inbound called with the translated envelope."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    client, sdk_client = await _connect_and_get_handler(plugin, encryptor)
    try:
        dispatch_calls: list[tuple] = []

        async def _fake_dispatch(account_id: str, envelope: Any, *, factory: Any) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        sentinel_factory = object()
        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: sentinel_factory
        )

        human = _make_msg_author(author_id=555, display_name="Alice", is_bot=False)
        msg = _make_guild_text_msg(
            author=human, content="hello world", channel_id=8888, guild_id=4242
        )

        await sdk_client._on_message_handler(msg)

        assert len(dispatch_calls) == 1
        account_id, envelope, factory = dispatch_calls[0]
        assert account_id == "acct-ingest-test"
        assert factory is sentinel_factory
        assert envelope.platform == "discord"
        assert envelope.account_id == "acct-ingest-test"
        assert envelope.channel_id == "8888"
        assert envelope.thread_id is None
        assert envelope.peer_id == "555"
        assert envelope.peer_name == "Alice"
        assert envelope.text == "hello world"
        assert envelope.raw["is_dm"] is False
        assert envelope.raw["guild_id"] == "4242"
    finally:
        await plugin.disconnect(client)


async def test_on_message_swallows_dispatcher_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatcher raises → handler logs and returns; gateway loop continues."""
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    client, sdk_client = await _connect_and_get_handler(plugin, encryptor)
    try:
        async def _raising_dispatch(account_id: str, envelope: Any, *, factory: Any) -> None:
            raise RuntimeError("simulated dispatcher failure")

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _raising_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: object()
        )

        human = _make_msg_author(author_id=777)
        msg = _make_guild_text_msg(author=human, content="will crash")

        # MUST NOT raise — the handler's try/except + logger.exception
        # contract keeps the SDK gateway loop alive.
        await sdk_client._on_message_handler(msg)
    finally:
        await plugin.disconnect(client)


async def test_on_message_returns_when_factory_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``get_factory()`` returns None → handler logs WARNING and returns."""
    import logging

    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    client, sdk_client = await _connect_and_get_handler(plugin, encryptor)
    try:
        dispatch_calls: list[tuple] = []

        async def _fake_dispatch(account_id: str, envelope: Any, *, factory: Any) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        # Force pre-startup / post-shutdown null factory.
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: None
        )

        human = _make_msg_author(author_id=888)
        msg = _make_guild_text_msg(author=human, content="lifespan race")

        with caplog.at_level(logging.WARNING, logger="the_one.connectors._discord"):
            await sdk_client._on_message_handler(msg)

        # Dispatcher MUST NOT be called.
        assert dispatch_calls == []
        # A WARNING was logged about the missing factory.
        warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "AgentFactory" in r.message
        ]
        assert warnings, "expected a WARNING log when factory is unavailable"
    finally:
        await plugin.disconnect(client)


def test_normalize_session_key_pins_five_field_construction() -> None:
    """:meth:`DiscordPlugin.normalize_session_key` returns the canonical 5-field key."""
    from the_one.connectors.base import InboundEnvelope, SessionKey

    plugin = DiscordPlugin()
    envelope = InboundEnvelope(
        platform="discord",
        account_id="acct-1",
        channel_id="ch-1",
        thread_id="thr-1",
        peer_id="peer-1",
        peer_name="Alice",
        text="hi",
        raw={},
    )
    key = plugin.normalize_session_key(envelope)

    assert isinstance(key, SessionKey)
    assert key.platform == "discord"
    assert key.account_id == "acct-1"
    assert key.channel_id == "ch-1"
    assert key.thread_id == "thr-1"
    assert key.peer_id == "peer-1"

    # Hashable / equality contract — frozen dataclass, slots=True.
    key2 = plugin.normalize_session_key(envelope)
    assert key == key2
    assert hash(key) == hash(key2)


def test_normalize_session_key_handles_none_thread_id() -> None:
    """Top-level channel messages produce a SessionKey with ``thread_id=None``."""
    from the_one.connectors.base import InboundEnvelope, SessionKey

    plugin = DiscordPlugin()
    envelope = InboundEnvelope(
        platform="discord",
        account_id="acct-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        peer_name="Alice",
        text="hi",
        raw={},
    )
    key = plugin.normalize_session_key(envelope)

    assert key.thread_id is None
    assert isinstance(key, SessionKey)


# ─────────────────────────────────────────────────────────────────
# M10 F8 L6 — DM classification hook (``DiscordPlugin.is_dm``)
# ─────────────────────────────────────────────────────────────────


def _dm_test_envelope(raw: dict, peer_id: str = "peer-1") -> "InboundEnvelope":  # noqa: F821
    """Build a minimal :class:`InboundEnvelope` for ``is_dm`` / ``resolve`` tests.

    The ``is_dm`` hook reads only ``raw["is_dm"]``; the ``resolve`` hook
    (F9 L1) additionally consults ``envelope.peer_id`` against the
    account allowlist, so callers exercising the resolver pass the
    ``peer_id`` kwarg (default ``"peer-1"`` preserves the historical
    ``is_dm``-only callers' behavior).
    """
    from the_one.connectors.base import InboundEnvelope

    return InboundEnvelope(
        platform="discord",
        account_id="acct-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id=peer_id,
        peer_name="Alice",
        text="hi",
        raw=raw,
    )


def test_is_dm_raw_is_dm_true_returns_true() -> None:
    """``raw["is_dm"]=True`` → :meth:`DiscordPlugin.is_dm` returns
    True. This is the canonical Discord-DM case after L4's translate
    helper sets the key from ``message.channel.type == private``."""
    plugin = DiscordPlugin()
    assert plugin.is_dm(_dm_test_envelope({"is_dm": True})) is True


def test_is_dm_raw_is_dm_false_returns_false() -> None:
    """``raw["is_dm"]=False`` → False. Canonical Discord-guild-channel
    case (any ChannelType other than private)."""
    plugin = DiscordPlugin()
    assert plugin.is_dm(_dm_test_envelope({"is_dm": False})) is False


def test_is_dm_raw_missing_is_dm_key_returns_false() -> None:
    """Defensive: missing ``raw["is_dm"]`` key → False (not raise).
    ``raw.get("is_dm", False)`` handles malformed dicts so a future
    translator regression — or a hand-constructed test envelope —
    doesn't surface a confusing ``KeyError`` through the consult
    site."""
    plugin = DiscordPlugin()
    assert plugin.is_dm(_dm_test_envelope({})) is False


# ─────────────────────────────────────────────────────────────────
# M11 F9 L1 — DM-from-stranger resolver hook (``DiscordPlugin.resolve``)
# ─────────────────────────────────────────────────────────────────


def _resolve_test_account(
    *,
    allowlist_peers: list[str] | None = None,
    allowlist_missing: bool = False,
) -> Connector:
    """Build a minimal :class:`Connector` for ``resolve`` tests.

    ``resolve`` reads only ``account.config["allowlist"]["peers"]``;
    ``secrets`` is not consulted, so we let the Pydantic default apply.
    The ``Connector`` config-shape validator at
    ``db/models.py:190`` requires ``allowlist`` (when present) to
    contain both ``peers`` and ``channels`` keys (and lists of strings
    for each) — ``channels`` is pinned to ``[]`` as an
    irrelevant-to-resolver axis.

    - ``allowlist_missing=True`` → ``config={}`` (no ``allowlist`` key);
      drives the AC #5 "older account, never paired" branch.
    - ``allowlist_peers`` as a list (incl. ``[]``) →
      ``config={"allowlist": {"peers": <list>, "channels": []}}``.
    """
    if allowlist_missing:
        config: dict[str, Any] = {}
    else:
        # M11 F17 L8 (Leg D) — peers stored as bare ``{id}`` dicts
        # post-v28; the resolver hook reads only the ``id`` field.
        config = {
            "allowlist": {
                "peers": [
                    {"id": peer_id}
                    for peer_id in (allowlist_peers or [])
                ],
                "channels": [],
            }
        }
    return Connector(
        id="acc-1",
        name="discord-resolve-test",
        type="discord",
        config=config,
    )


def test_resolve_dm_from_stranger_returns_needs_pairing() -> None:
    """DM + peer not in ``allowlist["peers"]`` → ``NeedsPairing`` with
    the contractual reason literal ``"discord_dm_unknown_peer"``.

    The reason literal is pinned per AC #2 — L2's pending-approval emit
    path and the dispatcher audit-log entry both grep for this exact
    value, so a typo here would silently break the downstream wiring.
    """
    plugin = DiscordPlugin()
    account = _resolve_test_account(allowlist_peers=[])
    envelope = _dm_test_envelope({"is_dm": True}, peer_id="stranger-99")

    outcome = plugin.resolve(account, envelope)

    assert outcome == NeedsPairing(reason="discord_dm_unknown_peer")


def test_resolve_dm_from_allowlisted_peer_returns_permit() -> None:
    """DM + peer in ``allowlist["peers"]`` → ``Permit()``. Canonical
    "already paired" branch — the dispatcher proceeds to ``agent.step``
    without the pairing/approval detour."""
    plugin = DiscordPlugin()
    account = _resolve_test_account(allowlist_peers=["peer-1"])
    envelope = _dm_test_envelope({"is_dm": True}, peer_id="peer-1")

    outcome = plugin.resolve(account, envelope)

    assert outcome == Permit()


def test_resolve_guild_message_returns_permit_regardless_of_allowlist() -> None:
    """Guild messages (``raw["is_dm"]=False``) → ``Permit()`` regardless
    of allowlist contents. F9 §1 design decision pins the pairing gate
    to DMs only; guild-mention scoping is a separate concern."""
    plugin = DiscordPlugin()
    # Empty allowlist would gate a DM, but a guild message is unconditionally permitted.
    account = _resolve_test_account(allowlist_peers=[])
    envelope = _dm_test_envelope({"is_dm": False}, peer_id="stranger-99")

    outcome = plugin.resolve(account, envelope)

    assert outcome == Permit()


def test_resolve_missing_allowlist_treats_as_empty_returns_needs_pairing_for_dm() -> None:
    """Missing ``config["allowlist"]`` (older account, never paired) →
    treated as "no allowlist entries"; the DM-from-stranger branch
    fires (not a crash, not a Permit-by-default).

    Covers AC #5: defensive handling of the absent allowlist key.
    """
    plugin = DiscordPlugin()
    account = _resolve_test_account(allowlist_missing=True)
    envelope = _dm_test_envelope({"is_dm": True}, peer_id="stranger-99")

    outcome = plugin.resolve(account, envelope)

    assert outcome == NeedsPairing(reason="discord_dm_unknown_peer")


def test_resolve_missing_is_dm_key_defaults_to_permit() -> None:
    """Defensive: malformed ``envelope.raw`` (missing ``is_dm`` key) →
    ``Permit()``, matching the existing ``is_dm`` method's defensive
    contract (``raw.get("is_dm", False)`` at ``_discord.py:1617``).

    Covers AC #6: hand-constructed test envelopes / future translator
    regressions do not surface a confusing ``KeyError`` here.
    """
    plugin = DiscordPlugin()
    account = _resolve_test_account(allowlist_peers=[])
    envelope = _dm_test_envelope({}, peer_id="stranger-99")

    outcome = plugin.resolve(account, envelope)

    assert outcome == Permit()


# ─────────────────────────────────────────────────────────────────
# M11 F7 L1 — Mention classification hook (``DiscordPlugin.is_mention``)
# ─────────────────────────────────────────────────────────────────


def _make_discord_message_stub(
    *,
    guild_me_id: int | None,
    mention_ids: list[int] | None,
) -> MagicMock:
    """Build a ``discord.Message`` stub for ``is_mention`` tests.

    Shape mirrors how the SDK exposes the fields the hook reads:

    - ``guild_me_id=None`` simulates DM context (``message.guild is
      None``) when ``mention_ids is None`` AND ``guild_me_id is
      None``; otherwise a ``guild`` is attached with ``guild.me=None``
      to exercise the "guild present but bot not synced" branch
      (caller passes ``guild_me_id=None`` AND a non-None
      ``mention_ids`` list to reach the guild-me-missing branch).
    - ``mention_ids=None`` is a sentinel for the "no mentions list at
      all" envelope shape used by the missing-discord_message test
      (the test omits the stub entirely; this helper does not
      produce that shape).
    """
    msg = MagicMock()
    msg.mentions = [
        MagicMock(id=mid) for mid in (mention_ids or [])
    ]
    if guild_me_id is None and mention_ids is None:
        # DM-shaped: no guild attached.
        msg.guild = None
    else:
        guild = MagicMock()
        if guild_me_id is None:
            # Guild present, bot not yet synced (``guild.me is None``).
            guild.me = None
        else:
            guild.me = MagicMock(id=guild_me_id)
        msg.guild = guild
    return msg


def _mention_test_envelope(raw: dict) -> "InboundEnvelope":  # noqa: F821
    """Build a minimal :class:`InboundEnvelope` for ``is_mention`` tests.

    Only ``raw["discord_message"]`` is load-bearing; the other fields
    carry stable placeholder values.
    """
    from the_one.connectors.base import InboundEnvelope

    return InboundEnvelope(
        platform="discord",
        account_id="acct-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        peer_name="Alice",
        text="hey",
        raw=raw,
    )


def test_is_mention_returns_true_when_bot_in_mentions() -> None:
    """Canonical mention case: ``guild.me.id`` appears in
    ``message.mentions`` → True. The bot was @mentioned in a guild
    channel message."""
    stub = _make_discord_message_stub(guild_me_id=42, mention_ids=[42])
    plugin = DiscordPlugin()
    assert plugin.is_mention(_mention_test_envelope({"discord_message": stub})) is True


def test_is_mention_returns_false_when_bot_not_in_mentions() -> None:
    """``guild.me.id`` is NOT in ``message.mentions`` (other users
    mentioned) → False. The bot was not @mentioned; the policy gate's
    mention branch must not engage."""
    stub = _make_discord_message_stub(guild_me_id=42, mention_ids=[7, 8, 9])
    plugin = DiscordPlugin()
    assert plugin.is_mention(_mention_test_envelope({"discord_message": stub})) is False


def test_is_mention_returns_false_on_empty_mentions() -> None:
    """``message.mentions`` is an empty list → False. No mention
    semantics at all on the inbound message."""
    stub = _make_discord_message_stub(guild_me_id=42, mention_ids=[])
    plugin = DiscordPlugin()
    assert plugin.is_mention(_mention_test_envelope({"discord_message": stub})) is False


def test_is_mention_returns_false_when_raw_discord_message_missing() -> None:
    """Defensive: ``raw`` missing the ``"discord_message"`` key →
    False AND no exception raised.

    Pinning that a future refactor to "raise on malformed envelope"
    doesn't pass silently — the test asserts BOTH the False return
    AND the no-exception contract."""
    plugin = DiscordPlugin()
    raised: BaseException | None = None
    result: bool | None = None
    try:
        result = plugin.is_mention(_mention_test_envelope({}))
    except BaseException as exc:  # noqa: BLE001 — pin no-exception
        raised = exc
    assert raised is None, f"is_mention raised unexpectedly: {raised!r}"
    assert result is False


def test_is_mention_returns_false_when_guild_missing() -> None:
    """DM-shaped envelope (``raw_msg.guild is None``) → False.

    The F7 policy gate short-circuits on ``is_dm`` at decision-tree
    step 1 before consulting ``is_mention``, so this branch fires
    only for out-of-order callers; the defensive return keeps the
    hook correctness-safe."""
    stub = _make_discord_message_stub(guild_me_id=None, mention_ids=None)
    plugin = DiscordPlugin()
    assert plugin.is_mention(_mention_test_envelope({"discord_message": stub})) is False


def test_is_mention_returns_false_when_guild_me_missing() -> None:
    """Guild present but ``guild.me is None`` (bot not yet synced in
    this guild) → False. Defensive against the discord.py race where
    the bot has joined a guild but the per-guild Member cache has
    not populated."""
    stub = _make_discord_message_stub(guild_me_id=None, mention_ids=[42])
    plugin = DiscordPlugin()
    assert plugin.is_mention(_mention_test_envelope({"discord_message": stub})) is False


async def test_connect_error_cancels_spawned_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the connect handshake raises mid-flight (after the spawned task
    has started), the task MUST be cancelled — the pool's BaseException
    catch at ``_pool.py:211`` would otherwise leak the task.

    We arrange: 5 hung-connect attempts (each times out at 0.05s). The
    plugin then gives up and raises :class:`ConnectorConnectionError`.
    For each spawned Client instance, ``close()`` must have been called
    on it (cleanup path) so no aiohttp session leaks either.
    """
    _patch_discord(monkeypatch)
    _shrink_backoff(monkeypatch)
    _StubDiscordClient.auto_fire_ready = False
    _StubDiscordClient.hang_connect = True

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor, ready_timeout_seconds=0.05)

    with pytest.raises(ConnectorConnectionError):
        await plugin.connect(account, encryptor)

    # All 5 SDK Client instances had close() called on them during the
    # connect-error cleanup path.
    assert len(_StubDiscordClient.instances) == 5
    for inst in _StubDiscordClient.instances:
        assert inst.is_closed() is True, (
            "Spawned-but-failed SDK Client must be closed during cleanup"
        )


# ─────────────────────────────────────────────────────────────────
# M10 F8 L5 — outbound adapter (DiscordClient.send)
# ─────────────────────────────────────────────────────────────────
#
# These tests do NOT patch ``discord_mod.discord`` — they exercise
# ``DiscordClient.send`` against the REAL discord.py exception classes
# (so the ``except discord.errors.Forbidden`` / ``NotFound`` / ``HTTPException``
# blocks in the implementation bind correctly) and use ``MagicMock`` to
# stand in for the SDK Client + Channel + Thread surfaces. We avoid
# spinning up ``plugin.connect`` because L5 only cares about the send
# path; the gateway-startup machinery is unrelated.


def _make_discord_client_with_sdk(sdk: Any) -> DiscordClient:
    """Construct a :class:`DiscordClient` wired to ``sdk``.

    The wrapper is built directly (NOT via ``plugin.connect``) so we
    don't need to fire the gateway pump or simulate ``on_ready``. The
    connection task is a dead ``asyncio.sleep(0)`` so ``is_alive`` can
    report whatever the ready_event says.
    """
    loop = asyncio.get_event_loop()
    task: asyncio.Task[None] = loop.create_task(asyncio.sleep(0))
    ready = asyncio.Event()
    ready.set()
    return DiscordClient(
        client=sdk,
        connection_task=task,
        ready_event=ready,
        intents=MagicMock(),
        account_id="acct-l5-test",
    )


def _make_text_channel_mock(
    *, channel_id: int = 4242, sent_message_id: int = 999111
) -> Any:
    """Mock that mirrors the ``discord.TextChannel`` surface ``send`` touches.

    ``send`` is an :class:`AsyncMock` that returns a Message-shaped
    object with ``.id``. ``type.name`` is the channel-type string our
    code projects into ``SendResult.details["channel_type"]``.
    """
    channel = MagicMock()
    channel.id = channel_id
    channel.type = MagicMock()
    channel.type.name = "text"
    sent = MagicMock()
    sent.id = sent_message_id
    channel.send = AsyncMock(return_value=sent)
    return channel


def _make_thread_mock(
    *, thread_id: int = 8888, sent_message_id: int = 999222
) -> Any:
    """Mock that satisfies ``isinstance(obj, discord.Thread)``.

    The implementation does ``isinstance(thread_candidate, discord.Thread)``
    on the real ``discord.Thread`` class, so we use ``MagicMock(spec=...)``
    against the real class — ``isinstance`` against a ``spec``-bound
    Mock returns True.
    """
    import discord

    thread = MagicMock(spec=discord.Thread)
    thread.id = thread_id
    thread.type = MagicMock()
    thread.type.name = "public_thread"
    sent = MagicMock()
    sent.id = sent_message_id
    thread.send = AsyncMock(return_value=sent)
    return thread


def _make_http_exception(
    exc_cls: type, *, status: int, retry_after: float | None = None,
) -> Exception:
    """Construct a real ``discord.errors.HTTPException`` subclass.

    The constructor wants a response object with ``.status`` and
    ``.reason`` attributes plus a message. We synthesize a minimal
    namespace that satisfies the ``__init__`` body.
    """
    from types import SimpleNamespace

    response = SimpleNamespace(status=status, reason="rate-limited")
    exc = exc_cls(response, "synthetic")
    # discord.py 2.4+ exposes ``retry_after`` as a float on
    # HTTPException for 429 responses (parsed from X-RateLimit-Reset-After).
    # The class doesn't set it in __init__; we attach it directly.
    if retry_after is not None:
        exc.retry_after = retry_after  # type: ignore[attr-defined]
    return exc


async def test_send_channel_happy_path() -> None:
    """Cached text channel send → returns :class:`SendResult` with the
    Discord message id and the channel-type-name details."""
    import discord

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = _make_text_channel_mock(channel_id=11111, sent_message_id=22222)
    sdk.get_channel = MagicMock(return_value=channel)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="11111", thread_id=None)

    result = await client.send(target, "hello world")

    assert result.platform_message_id == "22222"
    assert result.details == {"channel_id": "11111", "channel_type": "text"}
    # get_channel called once (cache hit); fetch_channel NOT called.
    sdk.get_channel.assert_called_once_with(11111)
    channel.send.assert_awaited_once_with("hello world")


async def test_send_thread_happy_path() -> None:
    """``target.thread_id`` set + resolves to a :class:`discord.Thread`
    → send via the thread (NOT the channel)."""
    import discord

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    thread = _make_thread_mock(thread_id=33333, sent_message_id=44444)
    # If the impl ever asks for the channel by id, it would short-circuit
    # to a non-Thread; make it explicit that the thread path won by
    # making get_channel return the thread when called with the thread id
    # AND a channel when called with the channel id (it shouldn't reach
    # the latter on this test, but the assertion below pins that).
    fallback_channel = _make_text_channel_mock(channel_id=99999)
    def _route(cid: int) -> Any:
        if cid == 33333:
            return thread
        return fallback_channel
    sdk.get_channel = MagicMock(side_effect=_route)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="99999", thread_id="33333")

    result = await client.send(target, "in the thread")

    assert result.platform_message_id == "44444"
    assert result.details == {"channel_id": "33333", "channel_type": "public_thread"}
    # The thread's send was used.
    thread.send.assert_awaited_once_with("in the thread")
    # The fallback channel's send was NOT used.
    fallback_channel.send.assert_not_called()


async def test_send_thread_id_resolves_to_non_thread_falls_back_to_channel() -> None:
    """``target.thread_id`` resolves to something that is NOT a Thread
    (operator misconfigured) → fall through to the channel-only path.

    Edge case from the leg spec: tolerant resolution — don't raise.
    """
    import discord

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    # get_channel(thread_id) returns a non-Thread channel-like object.
    # get_channel(channel_id) returns the real channel.
    non_thread = _make_text_channel_mock(channel_id=55555)  # NOT a Thread.
    real_channel = _make_text_channel_mock(channel_id=66666, sent_message_id=77777)
    def _route(cid: int) -> Any:
        if cid == 55555:
            return non_thread
        if cid == 66666:
            return real_channel
        return None
    sdk.get_channel = MagicMock(side_effect=_route)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="66666", thread_id="55555")

    result = await client.send(target, "fallback path")

    assert result.platform_message_id == "77777"
    assert result.details["channel_id"] == "66666"
    real_channel.send.assert_awaited_once_with("fallback path")
    # The non-Thread "thread" candidate must NOT have been sent to.
    non_thread.send.assert_not_called()


async def test_send_cache_miss_triggers_fetch_channel() -> None:
    """``get_channel`` returns None (cache miss) → ``fetch_channel`` is
    awaited and its result is used."""
    import discord

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    sdk.get_channel = MagicMock(return_value=None)  # cache miss
    fetched = _make_text_channel_mock(channel_id=88888, sent_message_id=99999)
    sdk.fetch_channel = AsyncMock(return_value=fetched)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="88888", thread_id=None)

    result = await client.send(target, "rest-resolved")

    assert result.platform_message_id == "99999"
    sdk.fetch_channel.assert_awaited_once_with(88888)
    fetched.send.assert_awaited_once_with("rest-resolved")


async def test_send_channel_not_found_raises_connection_error() -> None:
    """``get_channel`` returns None AND ``fetch_channel`` raises
    :class:`discord.errors.NotFound` → :class:`ConnectorConnectionError`."""
    import discord
    from the_one.connectors.errors import ConnectorConnectionError as _Conn

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    sdk.get_channel = MagicMock(return_value=None)
    sdk.fetch_channel = AsyncMock(
        side_effect=_make_http_exception(discord.errors.NotFound, status=404)
    )

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="404040", thread_id=None)

    with pytest.raises(_Conn, match="404040"):
        await client.send(target, "to nowhere")


async def test_send_channel_fetch_returns_none_raises_connection_error() -> None:
    """``get_channel`` returns None AND ``fetch_channel`` returns None
    (no exception) → :class:`ConnectorConnectionError`.

    Defensive against an SDK contract violation; covers the second
    branch of the channel-not-found path documented in the leg spec.
    """
    import discord
    from the_one.connectors.errors import ConnectorConnectionError as _Conn

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    sdk.get_channel = MagicMock(return_value=None)
    sdk.fetch_channel = AsyncMock(return_value=None)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="404041", thread_id=None)

    with pytest.raises(_Conn, match="404041"):
        await client.send(target, "to nowhere")


async def test_send_forbidden_raises_config_error() -> None:
    """``destination.send`` raises :class:`discord.errors.Forbidden`
    → :class:`ConnectorConfigError`."""
    import discord
    from the_one.connectors.errors import ConnectorConfigError as _Cfg

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = _make_text_channel_mock(channel_id=70001)
    channel.send = AsyncMock(
        side_effect=_make_http_exception(discord.errors.Forbidden, status=403)
    )
    sdk.get_channel = MagicMock(return_value=channel)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="70001", thread_id=None)

    with pytest.raises(_Cfg) as exc_info:
        await client.send(target, "muted")
    # account_id flows through the wrapper.
    assert exc_info.value.account_id == "acct-l5-test"
    # The validation_message references the channel.
    assert "70001" in exc_info.value.validation_message
    assert "permission" in exc_info.value.validation_message.lower()


async def test_send_not_found_on_send_raises_connection_error() -> None:
    """``destination.send`` raises :class:`discord.errors.NotFound`
    (channel deleted between resolution and send) →
    :class:`ConnectorConnectionError`."""
    import discord
    from the_one.connectors.errors import ConnectorConnectionError as _Conn

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = _make_text_channel_mock(channel_id=70002)
    channel.send = AsyncMock(
        side_effect=_make_http_exception(discord.errors.NotFound, status=404)
    )
    sdk.get_channel = MagicMock(return_value=channel)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="70002", thread_id=None)

    with pytest.raises(_Conn, match="70002"):
        await client.send(target, "to deleted")


async def test_send_rate_limit_raises_rate_limit_error_with_retry_after() -> None:
    """HTTPException(status=429) with ``retry_after`` populated →
    :class:`ConnectorRateLimitError` carrying the hint."""
    import discord
    from the_one.connectors.errors import ConnectorRateLimitError as _Rate

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = _make_text_channel_mock(channel_id=70003)
    channel.send = AsyncMock(
        side_effect=_make_http_exception(
            discord.errors.HTTPException, status=429, retry_after=2.5
        )
    )
    sdk.get_channel = MagicMock(return_value=channel)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="70003", thread_id=None)

    with pytest.raises(_Rate) as exc_info:
        await client.send(target, "too fast")
    assert exc_info.value.account_id == "acct-l5-test"
    assert exc_info.value.retry_after_seconds == 2.5
    # The retry_after hint must surface in the rendered error message.
    assert "2.5" in str(exc_info.value)


async def test_send_rate_limit_without_retry_after() -> None:
    """HTTPException(status=429) without a ``retry_after`` hint →
    :class:`ConnectorRateLimitError` with ``retry_after_seconds=None``."""
    import discord
    from the_one.connectors.errors import ConnectorRateLimitError as _Rate

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = _make_text_channel_mock(channel_id=70004)
    channel.send = AsyncMock(
        side_effect=_make_http_exception(
            discord.errors.HTTPException, status=429, retry_after=None
        )
    )
    sdk.get_channel = MagicMock(return_value=channel)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="70004", thread_id=None)

    with pytest.raises(_Rate) as exc_info:
        await client.send(target, "no hint")
    assert exc_info.value.retry_after_seconds is None


async def test_send_generic_http_exception_raises_connection_error() -> None:
    """A non-429 HTTPException → :class:`ConnectorConnectionError`.

    Covers Discord rejecting empty content (400), 2000-char overflow
    (400), 5xx, etc. — the SDK surfaces all as HTTPException with a
    non-429 status; L5 maps them all to ConnectorConnectionError so
    the F4 tool produces a clean ``[error] ...`` envelope.
    """
    import discord
    from the_one.connectors.errors import ConnectorConnectionError as _Conn

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = _make_text_channel_mock(channel_id=70005)
    channel.send = AsyncMock(
        side_effect=_make_http_exception(
            discord.errors.HTTPException, status=400
        )
    )
    sdk.get_channel = MagicMock(return_value=channel)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="70005", thread_id=None)

    with pytest.raises(_Conn, match="Discord send failed"):
        await client.send(target, "")


async def test_send_propagates_unknown_exception() -> None:
    """A non-discord exception (e.g. a programmer-error TypeError)
    propagates unwrapped — the F4 tool's ``ConnectorClientError`` catch
    will NOT swallow it; the outer BaseException handler does.
    """
    import discord

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    channel = _make_text_channel_mock(channel_id=70006)
    channel.send = AsyncMock(side_effect=TypeError("not a discord error"))
    sdk.get_channel = MagicMock(return_value=channel)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="70006", thread_id=None)

    with pytest.raises(TypeError, match="not a discord error"):
        await client.send(target, "boom")


# ─────────────────────────────────────────────────────────────────
# M10 F8 L7 — doctor probe
# ─────────────────────────────────────────────────────────────────


# Intent flag bits (per Discord developer docs):
#   GATEWAY_MESSAGE_CONTENT = 1 << 18 = 262144
#   GATEWAY_GUILD_MEMBERS   = 1 << 14 = 16384
_FLAG_MESSAGE_CONTENT = 1 << 18
_FLAG_GUILD_MEMBERS = 1 << 14


class _StubAiohttpResponse:
    """Mock response object — supports the async-context-manager
    pattern and async ``json()``."""

    def __init__(self, status: int, body: Any | None = None) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> "_StubAiohttpResponse":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def json(self) -> Any:
        if isinstance(self._body, BaseException):
            raise self._body
        return self._body


class _StubAiohttpSession:
    """Mock ``aiohttp.ClientSession`` — supports ``async with`` + ``.get``.

    Tests configure a per-URL response map keyed by exact URL (or by a
    prefix-match fallback). ``get`` returns a context manager whose
    ``__aenter__`` returns a ``_StubAiohttpResponse``. Records every
    ``.get`` call (url + headers) in ``calls`` for assertion.
    """

    # Per-instance: stash the configured response map + recorded calls.
    def __init__(
        self,
        url_responses: dict[str, _StubAiohttpResponse | BaseException],
    ) -> None:
        self.url_responses = url_responses
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    async def __aenter__(self) -> "_StubAiohttpSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        self.closed = True
        return None

    def get(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> _StubAiohttpResponse:
        self.calls.append((url, headers or {}))
        # Exact match first; then longest-prefix match.
        if url in self.url_responses:
            target = self.url_responses[url]
        else:
            target = None
            best = -1
            for key, value in self.url_responses.items():
                if url.startswith(key) and len(key) > best:
                    target = value
                    best = len(key)
            if target is None:
                # Default 200 with empty body to surface unexpected URLs
                # rather than the test silently passing.
                raise AssertionError(
                    f"_StubAiohttpSession: no configured response for {url}; "
                    f"configured URLs: {sorted(self.url_responses)}"
                )
        if isinstance(target, BaseException):
            raise target
        return target


class _StubDoctorGatewayClient:
    """Stand-in for ``discord.Client`` in the gateway smoke test.

    Knobs (class-level so the doctor's fresh-instance construction
    inside the probe picks them up):

    - ``login_should_raise``: when set, ``login`` raises this exception.
    - ``connect_should_raise``: when set, ``connect`` raises this
      exception after being awaited.
    - ``connect_hangs``: when True, ``connect`` blocks forever (until
      cancelled) and does NOT fire on_ready — exercises the timeout.
    - ``connect_ends_before_ready``: when True, ``connect`` returns
      cleanly WITHOUT firing on_ready — surface as failed.
    - ``auto_fire_ready``: when True (default), ``connect`` fires
      on_ready synchronously then awaits a close-event so the gateway
      task remains alive until close() is called.
    """

    instances: list["_StubDoctorGatewayClient"] = []
    login_should_raise: BaseException | None = None
    connect_should_raise: BaseException | None = None
    connect_hangs: bool = False
    connect_ends_before_ready: bool = False
    auto_fire_ready: bool = True

    def __init__(self, *, intents: Any, **kwargs: Any) -> None:
        self.intents = intents
        self._closed = False
        self._on_ready_handler: Any | None = None
        self._on_message_handler: Any | None = None
        self._close_event = asyncio.Event()
        self.login_calls: list[str] = []
        self.connect_calls: list[dict[str, Any]] = []
        self.close_calls = 0
        self.user: _StubClientUser | None = None
        type(self).instances.append(self)

    def event(self, coro: Any) -> Any:
        if coro.__name__ == "on_ready":
            self._on_ready_handler = coro
        elif coro.__name__ == "on_message":
            self._on_message_handler = coro
        return coro

    async def login(self, token: str) -> None:
        self.login_calls.append(token)
        cls = type(self)
        if cls.login_should_raise is not None:
            raise cls.login_should_raise

    async def connect(self, *, reconnect: bool = True) -> None:
        cls = type(self)
        self.connect_calls.append({"reconnect": reconnect})
        if cls.connect_should_raise is not None:
            raise cls.connect_should_raise
        if cls.connect_hangs:
            # Block forever — the probe cancels this on cleanup.
            await asyncio.Event().wait()
            return
        if cls.connect_ends_before_ready:
            return  # do NOT fire on_ready
        if cls.auto_fire_ready and self._on_ready_handler is not None:
            self.user = _StubClientUser()
            await self._on_ready_handler()
        await self._close_event.wait()

    async def close(self) -> None:
        self.close_calls += 1
        self._closed = True
        self._close_event.set()

    def is_closed(self) -> bool:
        return self._closed


def _reset_doctor_gateway_stub_state() -> None:
    _StubDoctorGatewayClient.instances = []
    _StubDoctorGatewayClient.login_should_raise = None
    _StubDoctorGatewayClient.connect_should_raise = None
    _StubDoctorGatewayClient.connect_hangs = False
    _StubDoctorGatewayClient.connect_ends_before_ready = False
    _StubDoctorGatewayClient.auto_fire_ready = True


def _patch_discord_for_doctor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url_responses: dict[str, _StubAiohttpResponse | BaseException],
) -> list[_StubAiohttpSession]:
    """Patch the discord SDK + aiohttp.ClientSession at the consumer module.

    Returns a list that gets appended each time the doctor calls
    ``aiohttp.ClientSession()`` so tests can inspect the recorded
    request URLs.
    """
    _reset_stub_state()
    _reset_doctor_gateway_stub_state()
    # Patch the discord SDK — for the doctor we use the dedicated
    # gateway stub so each probe gets its own fresh-state instance.
    doctor_discord = type(
        "_DoctorDiscordModule",
        (),
        {
            "Client": _StubDoctorGatewayClient,
            "Intents": _StubIntents,
            "Activity": _StubActivity,
            "ActivityType": _StubActivityType,
            "ChannelType": _StubChannelType,
            "Object": _StubObject,
            "errors": _StubErrors,
            "app_commands": _StubAppCommandsModule,
        },
    )
    monkeypatch.setattr(discord_mod, "discord", doctor_discord)

    sessions: list[_StubAiohttpSession] = []

    def _session_factory() -> _StubAiohttpSession:
        session = _StubAiohttpSession(url_responses)
        sessions.append(session)
        return session

    stub_aiohttp = type(
        "_StubAiohttpModule",
        (),
        {
            "ClientSession": _session_factory,
            "ClientError": discord_mod.aiohttp.ClientError,
        },
    )
    monkeypatch.setattr(discord_mod, "aiohttp", stub_aiohttp)
    return sessions


def _happy_url_responses(
    *,
    flags: int = _FLAG_MESSAGE_CONTENT | _FLAG_GUILD_MEMBERS,
    bot_user_id: str = "bot-user-42",
    bot_username: str = "the-one-bot",
    application_id: str = "app-id-1234",
    guild_responses: dict[str, _StubAiohttpResponse] | None = None,
) -> dict[str, _StubAiohttpResponse | BaseException]:
    """Default URL→response map for the happy path."""
    responses: dict[str, _StubAiohttpResponse | BaseException] = {
        "https://discord.com/api/v10/users/@me": _StubAiohttpResponse(
            200, {"id": bot_user_id, "username": bot_username}
        ),
        "https://discord.com/api/v10/oauth2/applications/@me": (
            _StubAiohttpResponse(
                200,
                {
                    "id": application_id,
                    "name": "The One",
                    "flags": flags,
                },
            )
        ),
    }
    if guild_responses:
        responses.update(guild_responses)
    return responses


async def test_doctor_happy_path_all_checks_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All 5 probes succeed → status='ok', message='Discord probe ok'."""
    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses()
    )

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)

    assert report.status == "ok"
    assert report.message == "Discord probe ok"
    assert report.details["bot_user_id"] == "bot-user-42"
    assert report.details["bot_username"] == "the-one-bot"
    assert report.details["application_id"] == "app-id-1234"
    assert report.details["unreachable_guilds"] == []
    # All five per-check sub-results present + ok.
    checks = report.details["checks"]
    assert set(checks) == {
        "token",
        "application",
        "intents",
        "gateway",
        "allowlist",
    }
    assert all(checks[name]["status"] == "ok" for name in checks)
    # Gateway smoke test ran — exactly one stub gateway client instance,
    # and it WAS closed (read-only — no on_message handler registered).
    assert len(_StubDoctorGatewayClient.instances) == 1
    smoke_client = _StubDoctorGatewayClient.instances[0]
    assert smoke_client._on_message_handler is None
    assert smoke_client.close_calls == 1


async def test_doctor_token_invalid_401_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 on /users/@me → failed; later checks short-circuited."""
    responses: dict[str, _StubAiohttpResponse | BaseException] = {
        "https://discord.com/api/v10/users/@me": _StubAiohttpResponse(401),
    }
    sessions = _patch_discord_for_doctor(monkeypatch, url_responses=responses)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)

    assert report.status == "failed"
    assert "401" in report.message
    # Short-circuit: only the token URL was queried.
    assert sessions[0].calls == [
        (
            "https://discord.com/api/v10/users/@me",
            {"Authorization": f"Bot {account.secrets['BOT_TOKEN']}"},
        )
    ]
    # Gateway smoke test must NOT have been attempted.
    assert _StubDoctorGatewayClient.instances == []
    # Per-check surfaces only the token sub-result.
    assert "token" in report.details["checks"]
    assert "gateway" not in report.details["checks"]


async def test_doctor_missing_message_content_intent_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One missing intent → degraded; both missing → failed.

    L7 spec: "Both required → ok. One missing → degraded with the missing
    intent in message. Both missing → failed."
    """
    # Case A: only Message Content missing → degraded.
    _patch_discord_for_doctor(
        monkeypatch,
        url_responses=_happy_url_responses(flags=_FLAG_GUILD_MEMBERS),
    )

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)
    assert report.status == "degraded"
    assert "Message Content" in report.message


async def test_doctor_both_intents_missing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both intents missing → failed (short-circuits gateway + allowlist)."""
    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses(flags=0)
    )

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)
    assert report.status == "failed"
    assert "intent" in report.message.lower()
    # Gateway smoke test must NOT have been attempted.
    assert _StubDoctorGatewayClient.instances == []


async def test_doctor_gateway_timeout_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway smoke test never sees on_ready → failed.

    We shrink the doctor's 30s timeout via monkeypatching
    ``asyncio.wait`` to use a much smaller bound — but the cleaner
    approach is to patch the literal timeout. The probe hard-codes
    30.0; instead, we ARRANGE for the gateway stub to immediately
    end the connection without firing on_ready (the "connection ends
    before ready" path). That covers the same failed-aggregation
    branch without waiting 30 seconds.
    """
    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses()
    )
    _StubDoctorGatewayClient.auto_fire_ready = False
    _StubDoctorGatewayClient.connect_ends_before_ready = True

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)
    assert report.status == "failed"
    # The gateway sub-result should be present with status=failed.
    assert report.details["checks"]["gateway"]["status"] == "failed"
    # And allowlist must NOT have run (short-circuit on gateway).
    assert "allowlist" not in report.details["checks"]


async def test_doctor_gateway_real_timeout_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway connect hangs → asyncio.wait timeout fires → failed.

    Patches the gateway-probe timeout to a tiny value so the test runs
    in <1s. Confirms the actual timeout branch (no done tasks) is
    reachable and surfaces as failed.
    """
    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses()
    )
    _StubDoctorGatewayClient.auto_fire_ready = False
    _StubDoctorGatewayClient.connect_hangs = True

    # Patch asyncio.wait at the doctor's call site to use a tight
    # timeout. We do this by wrapping the function — the doctor calls
    # ``asyncio.wait(..., timeout=30.0, ...)``; we override the timeout.
    real_wait = asyncio.wait

    async def _short_wait(
        tasks: Any, *, timeout: float | None = None, return_when: Any
    ) -> Any:
        return await real_wait(
            tasks, timeout=0.1, return_when=return_when
        )

    monkeypatch.setattr(asyncio, "wait", _short_wait)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)
    assert report.status == "failed"
    assert report.details["checks"]["gateway"]["status"] == "failed"
    # The gateway stub's connect task got cancelled; close() was called.
    smoke_client = _StubDoctorGatewayClient.instances[0]
    assert smoke_client.close_calls == 1


async def test_doctor_allowlist_unreachable_guild_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One guild reachable + one 404 → degraded with unreachable_guilds populated."""
    bot_id = "bot-user-42"
    guild_responses = {
        f"https://discord.com/api/v10/guilds/G1/members/{bot_id}": (
            _StubAiohttpResponse(200, {"user": {"id": bot_id}})
        ),
        f"https://discord.com/api/v10/guilds/G2/members/{bot_id}": (
            _StubAiohttpResponse(404)
        ),
    }
    _patch_discord_for_doctor(
        monkeypatch,
        url_responses=_happy_url_responses(
            bot_user_id=bot_id, guild_responses=guild_responses
        ),
    )

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    # Use SimpleNamespace because the L7 leg probes defensively against
    # an allowlist["guilds"] key that the L8 axis extension has not yet
    # added to the Connector pydantic validator. SimpleNamespace
    # bypasses validation and gives us the duck-typed surface the doctor
    # consumes (.config / .secrets / .id).
    from types import SimpleNamespace

    account = SimpleNamespace(
        id="acct-doctor-allowlist",
        name="Discord Doctor",
        type="discord",
        config={"allowlist": {"guilds": ["G1", "G2"]}},
        secrets={"BOT_TOKEN": "tok"},
    )

    report = await plugin.doctor(account, encryptor)

    assert report.status == "degraded"
    assert "2" in report.message or "guilds are unreachable" in report.message
    assert report.details["unreachable_guilds"] == ["G2"]
    allowlist = report.details["checks"]["allowlist"]
    assert allowlist["status"] == "degraded"
    assert allowlist["reachable_guilds"] == ["G1"]


async def test_doctor_empty_allowlist_returns_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allowlist absent or empty → skip; 1-4 pass → ok."""
    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses()
    )

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    # No allowlist key.
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)
    assert report.status == "ok"
    assert report.details["unreachable_guilds"] == []

    # Also: empty guilds list → ok. SimpleNamespace bypasses the
    # pydantic validator that rejects the L8-future 'guilds' key.
    _reset_doctor_gateway_stub_state()
    from types import SimpleNamespace

    account_empty = SimpleNamespace(
        id="acct-doctor-empty",
        name="Discord Doctor",
        type="discord",
        config={"allowlist": {"guilds": []}},
        secrets={"BOT_TOKEN": "tok"},
    )
    report2 = await plugin.doctor(account_empty, encryptor)
    assert report2.status == "ok"


async def test_doctor_receives_encryptor_per_call_without_caching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor receives ``encryptor`` per-call via the F1 Protocol; the
    plugin does NOT capture or cache the encryptor across calls.

    The encryption-rotation invariant is preserved at the REPOSITORY
    layer (``ConnectorRepository._ciphertext_to_secrets``
    decrypts the whole ``secrets`` blob at row-load time), so by the
    time the plugin sees ``account.secrets["BOT_TOKEN"]`` it is
    already plaintext and the plugin does not consume ``encryptor``.

    This test pins the no-caching half of the invariant: passing
    different :class:`Encryptor` instances on different doctor calls
    must work — the plugin must not have stashed the first one. The
    rotation half of the invariant is exercised at the repository
    layer, not here.
    """
    from cryptography.fernet import Fernet

    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses()
    )

    plugin = DiscordPlugin()

    # First call: encryptor A. Secrets arrive plaintext (the repository
    # decrypts the blob at load time).
    enc_a = Encryptor(Fernet.generate_key())
    account_a = Connector(
        id="acct-doctor-live-a",
        name="Discord Doctor A",
        type="discord",
        config={},
        secrets={"BOT_TOKEN": "token-A"},
    )
    report_a = await plugin.doctor(account_a, enc_a)
    assert report_a.status == "ok"

    # Second call: completely distinct encryptor instance. If the
    # plugin had stashed `enc_a` (it MUST NOT — the Protocol passes
    # encryptor per call), this would still pass because the plugin
    # doesn't consume the encryptor — but the assertion below pins
    # the contract regardless.
    _reset_doctor_gateway_stub_state()
    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses()
    )
    enc_b = Encryptor(Fernet.generate_key())
    assert enc_b is not enc_a
    account_b = Connector(
        id="acct-doctor-live-b",
        name="Discord Doctor B",
        type="discord",
        config={},
        secrets={"BOT_TOKEN": "token-B"},
    )
    report_b = await plugin.doctor(account_b, enc_b)
    assert report_b.status == "ok"


async def test_doctor_gateway_smoke_test_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gateway smoke test does NOT register an on_message handler
    and does NOT dispatch any messages.

    Pins the "read-only — no message dispatch" acceptance criterion.
    """
    _patch_discord_for_doctor(
        monkeypatch, url_responses=_happy_url_responses()
    )

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    report = await plugin.doctor(account, encryptor)
    assert report.status == "ok"

    assert len(_StubDoctorGatewayClient.instances) == 1
    smoke = _StubDoctorGatewayClient.instances[0]
    # NO on_message handler — only on_ready.
    assert smoke._on_message_handler is None
    assert smoke._on_ready_handler is not None
    # SDK was closed cleanly after the probe.
    assert smoke.close_calls == 1


# ─────────────────────────────────────────────────────────────────
# M10 F8 L9 — slash commands via CommandHandler
# ─────────────────────────────────────────────────────────────────
#
# The plugin satisfies :class:`CommandHandler` structurally
# (``handle_command`` returns ``None`` for every command in L9, so
# slash invocations fall through to the F7 built-in dispatcher). The
# tests pin:
#
# 1. ``handle_command`` returns ``None`` for each of the 6 v1 commands
#    AND for unknown commands.
# 2. ``isinstance(DiscordPlugin(), CommandHandler)`` returns True.
# 3. Tree construction registers the 6 v1 commands (hyphen-free names).
# 4. Per-guild ``tree.sync`` invocation: once per configured guild;
#    empty / absent guilds skipped silently; failure logs WARNING and
#    connect proceeds.
# 5. Slash-command body translates ``interaction`` → ``InboundEnvelope``
#    and calls ``dispatch_inbound`` with the synthesized ``text``.
#
# The slash-command tests reuse the L3/L4 ``_patch_discord`` fixture —
# the stub module now exposes ``app_commands.CommandTree`` and
# ``Object`` (added with L9 — see the helper section above).


_L9_EXPECTED_COMMAND_NAMES: tuple[str, ...] = (
    "agents",
    "talk_to",
    "whoami",
    "new",
    "reset",
    "help",
)


def _make_interaction(
    *,
    user_id: int = 4242,
    display_name: str = "Alice",
    channel_id: int = 1001,
    guild_id: int | None = 7777,
    roles: list[Any] | None = None,
    token: str = "interaction-token-stub",
) -> Any:
    """Synthetic ``discord.Interaction`` stand-in for the slash-command body.

    Mirrors the surface ``_build_slash_envelope`` consults:
    ``user.{id, display_name, roles}``, ``channel_id``, ``guild_id``,
    ``channel.{type, parent}``, ``token`` (M11 F14 L7 followup token),
    ``response.defer(ephemeral=...)``.
    """
    import discord
    from types import SimpleNamespace

    user = SimpleNamespace(
        id=user_id,
        display_name=display_name,
        roles=roles or [],
    )
    channel = SimpleNamespace(
        id=channel_id, type=discord.ChannelType.text, parent=None
    )
    # The interaction.response must support ``defer(ephemeral=...)``.
    response = SimpleNamespace(defer=AsyncMock(return_value=None))
    interaction = SimpleNamespace(
        user=user,
        channel=channel,
        channel_id=channel_id,
        guild_id=guild_id,
        token=token,
        response=response,
    )
    return interaction


async def test_handle_command_returns_none_for_v1_vocabulary() -> None:
    """``DiscordPlugin.handle_command`` returns ``None`` for each of the
    6 v1 command names. The dispatcher's step 11 consult site falls
    through to ``_dispatch_builtin_command`` for the v1 vocabulary.

    Pins the L9 spec acceptance: "Returns None for all commands (v1 +
    unknown) in L9; ephemeral-customizations deferred to F10."
    """
    from the_one.connectors.base import InboundEnvelope

    plugin = DiscordPlugin()
    # Build a minimal envelope — the L9 handler does not consult its
    # fields, but the Protocol signature requires it.
    envelope = InboundEnvelope(
        platform="discord",
        account_id="acct-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        peer_name="Alice",
        text="/agents",
        raw={},
    )
    for name in _L9_EXPECTED_COMMAND_NAMES:
        # Test both the hyphen-free registered name AND, for ``talk_to``,
        # the text-prefix hyphenated form the F7 parser produces from
        # ``/talk-to ...`` text messages — both must return None so the
        # dispatcher always falls through to the built-in handler.
        result = await plugin.handle_command(envelope, name, [])
        assert result is None, f"handle_command({name!r}) should return None"
    # talk-to (hyphen, the F7 text-prefix form) — also None.
    result_dash = await plugin.handle_command(envelope, "talk-to", ["some-agent"])
    assert result_dash is None


async def test_handle_command_returns_none_for_unknown_command() -> None:
    """Unknown command names also return ``None``. The dispatcher's
    step 11 then falls through to ``_dispatch_builtin_command``, which
    also returns ``None`` for unknown names; step 11 falls through to
    step 12 (``agent.step``) and the agent sees the text as a regular
    user message.
    """
    from the_one.connectors.base import InboundEnvelope

    plugin = DiscordPlugin()
    envelope = InboundEnvelope(
        platform="discord",
        account_id="acct-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        peer_name="Alice",
        text="/foo bar",
        raw={},
    )
    result = await plugin.handle_command(envelope, "foo", ["bar"])
    assert result is None


def test_plugin_satisfies_command_handler_protocol() -> None:
    """``isinstance(DiscordPlugin(), CommandHandler)`` returns True.

    DiscordPlugin structurally satisfies BOTH ``ConnectorPlugin`` and
    ``CommandHandler`` Protocols after L9 — the L1-wired dispatcher
    consult site at ``_inbound.py:494`` therefore reaches the plugin's
    handler via the ``getattr(plugin, "handle_command", None)``
    sentinel.
    """
    from the_one.connectors.base import CommandHandler

    assert isinstance(DiscordPlugin(), CommandHandler) is True


async def test_connect_registers_six_v1_commands_in_command_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``DiscordPlugin.connect`` builds a ``CommandTree`` and registers
    the 6 v1 commands as application commands.

    Names: ``agents``, ``talk_to``, ``whoami``, ``new``, ``reset``,
    ``help``. Pinning the hyphen-free ``talk_to`` (NOT ``talk-to``)
    matches the Discord API's name regex (which rejects hyphens for
    ASCII names); the F7 ``_parse_command`` whitespace-split still
    accepts the synthesized text either way.
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        # Exactly one CommandTree was constructed against this client.
        assert len(_StubCommandTree.instances) == 1
        tree = _StubCommandTree.instances[0]

        # Six commands registered with the expected names + non-empty
        # descriptions.
        registered_names = [c["name"] for c in tree.commands]
        assert registered_names == list(_L9_EXPECTED_COMMAND_NAMES)
        for entry in tree.commands:
            assert isinstance(entry["description"], str)
            assert entry["description"], (
                f"command {entry['name']!r} must have a non-empty description"
            )
            # The callback is a coroutine function (async def).
            assert asyncio.iscoroutinefunction(entry["callback"])

        # Hyphen-free invariant — confirms the Discord API constraint.
        for name in registered_names:
            assert "-" not in name, (
                f"command name {name!r} contains a hyphen; Discord rejects "
                f"hyphens in ASCII command names"
            )
    finally:
        await plugin.disconnect(client)


async def test_connect_syncs_once_per_configured_guild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``tree.sync(guild=...)`` is called exactly once per guild in
    ``account.config["allowlist"]["guilds"]``. Each sync receives a
    ``discord.Object`` wrapping the int-coerced guild id.

    M11 F14 L02: guild scoping unified onto the allowlist "Servers"
    axis; slash-sync reads ``config.allowlist.guilds``, not the retired
    top-level ``config.guilds``.
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = Connector(
        id="acct-l9-guilds",
        name="Discord L9 Guilds",
        type="discord",
        # int-coercible guild ids (strings on the wire; the plugin
        # casts to int when wrapping in discord.Object).
        config={
            "allowlist": {
                "guilds": ["111222333", "444555666"],
                "peers": [],
                "channels": [],
            }
        },
        secrets={"BOT_TOKEN": "token"},
    )

    client = await plugin.connect(account, encryptor)
    try:
        tree = _StubCommandTree.instances[0]
        assert len(tree.sync_calls) == 2
        # Each sync_call carries an Object wrapping the int-coerced id.
        seen_ids = sorted(o.id for o in tree.sync_calls)
        assert seen_ids == [111222333, 444555666]
    finally:
        await plugin.disconnect(client)


async def test_connect_with_empty_guilds_skips_sync(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Empty / absent ``account.config["allowlist"]["guilds"]`` → no sync
    calls; INFO log."""
    import logging

    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    # No allowlist.guilds at all (absent === empty list).
    account = _make_account(encryptor)

    with caplog.at_level(logging.INFO, logger="the_one.connectors._discord"):
        client = await plugin.connect(account, encryptor)
    try:
        tree = _StubCommandTree.instances[0]
        # Tree built; commands registered; sync NOT called.
        assert len(tree.commands) == 6
        assert tree.sync_calls == []
        # INFO log about no guilds configured.
        infos = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO
            and "no guilds configured" in r.message.lower()
        ]
        assert infos, (
            "expected an INFO log when the guilds list is empty or absent"
        )
    finally:
        await plugin.disconnect(client)


async def test_connect_proceeds_when_tree_sync_raises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``tree.sync`` raises (e.g. Forbidden, network blip) → connect
    completes; WARNING logged; subsequent guilds still get attempted.
    """
    import logging

    _patch_discord(monkeypatch)
    # First guild sync raises; second succeeds — both should attempt.
    _StubCommandTree.sync_should_raise = [
        _StubHTTPException("missing applications.commands scope")
    ]

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = Connector(
        id="acct-l9-sync-fail",
        name="Discord L9 Sync Fail",
        type="discord",
        config={
            "allowlist": {
                "guilds": ["1111", "2222"],
                "peers": [],
                "channels": [],
            }
        },
        secrets={"BOT_TOKEN": "token"},
    )

    with caplog.at_level(logging.WARNING, logger="the_one.connectors._discord"):
        client = await plugin.connect(account, encryptor)
    try:
        # Connect succeeded — wrapper is alive.
        assert client.is_alive() is True
        tree = _StubCommandTree.instances[0]
        # Both guilds were ATTEMPTED — sync failure on one doesn't
        # short-circuit subsequent guilds.
        assert len(tree.sync_calls) == 2
        # A WARNING was logged describing the sync failure.
        warnings_logged = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "sync" in r.message.lower()
        ]
        assert warnings_logged, (
            "expected a WARNING log when tree.sync raises"
        )
    finally:
        await plugin.disconnect(client)


async def test_connect_int_coerces_string_guild_id_for_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single string guild id in ``config.allowlist.guilds`` is
    int-coerced for ``discord.Object(id=int(g))`` during sync.

    M11 F14 L02: int-id support is intentionally dropped under guild
    unification — the ``allowlist.guilds`` model validator
    (``db/models.py``) enforces ``list[str]`` at ``Connector(...)``
    construction (matches the ``agent/config.py`` + doctor convention).
    The plugin still ``int()``-coerces each string id when wrapping it
    in a ``discord.Object``.
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = Connector(
        id="acct-l9-str-guild",
        name="Discord L9 Str Guild",
        type="discord",
        config={
            "allowlist": {
                "guilds": ["987654321"],
                "peers": [],
                "channels": [],
            }
        },
        secrets={"BOT_TOKEN": "token"},
    )

    client = await plugin.connect(account, encryptor)
    try:
        tree = _StubCommandTree.instances[0]
        assert len(tree.sync_calls) == 1
        assert tree.sync_calls[0].id == 987654321
    finally:
        await plugin.disconnect(client)


async def test_sync_copies_global_commands_into_each_guild_before_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for Bug F (M11 F14 L11): ``tree.copy_global_to(guild=g)``
    must be called before ``tree.sync(guild=g)`` for every configured guild.

    Root cause: commands are registered globally via ``tree.command(...)``
    (no ``guild=``).  ``tree.sync(guild=g)`` PUTs only the per-guild bucket
    for ``g``, which starts empty — so without the copy, Discord receives 0
    commands ("This application has no commands").

    This test would FAIL against the pre-fix code:
    - Pre-fix: ``copy_global_to`` is never called → guild buckets remain empty
      → assertion on ``guild_buckets[id]`` fails (KeyError) or contains [].
    - Post-fix: ``copy_global_to`` populates each bucket with the 6 global
      commands before ``tree.sync`` is called → assertion passes.

    Also asserts call ORDER: copy must precede sync per guild.
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    guild_ids = ["111000111", "222000222"]
    account = Connector(
        id="acct-l11-bug-f",
        name="Discord L11 Bug F",
        type="discord",
        config={
            "allowlist": {
                "guilds": guild_ids,
                "peers": [],
                "channels": [],
            }
        },
        secrets={"BOT_TOKEN": "token"},
    )

    client = await plugin.connect(account, encryptor)
    try:
        tree = _StubCommandTree.instances[0]

        # 6 global commands were registered (mirrors :1064-1067).
        assert len(tree.commands) == 6, (
            f"expected 6 globally registered commands, got {len(tree.commands)}"
        )

        # Every configured guild must have had its bucket populated BEFORE sync.
        for gid_str in guild_ids:
            gid = int(gid_str)
            assert gid in tree.guild_buckets, (
                f"guild {gid}: copy_global_to was never called "
                "(guild bucket missing — pre-fix behaviour)"
            )
            assert len(tree.guild_buckets[gid]) == 6, (
                f"guild {gid}: expected 6 commands in guild bucket after "
                f"copy_global_to, got {len(tree.guild_buckets[gid])}"
            )

        # Call ordering: for each guild, copy must appear before sync in the
        # call_log.  Both must appear exactly once per guild.
        for gid_str in guild_ids:
            gid = int(gid_str)
            copy_indices = [
                i for i, (op, g) in enumerate(tree.call_log)
                if op == "copy" and g.id == gid
            ]
            sync_indices = [
                i for i, (op, g) in enumerate(tree.call_log)
                if op == "sync" and g.id == gid
            ]
            assert len(copy_indices) == 1, (
                f"guild {gid}: expected exactly 1 copy_global_to call, "
                f"got {len(copy_indices)}"
            )
            assert len(sync_indices) == 1, (
                f"guild {gid}: expected exactly 1 sync call, "
                f"got {len(sync_indices)}"
            )
            assert copy_indices[0] < sync_indices[0], (
                f"guild {gid}: copy_global_to must be called BEFORE sync "
                f"(copy at log index {copy_indices[0]}, "
                f"sync at log index {sync_indices[0]})"
            )
    finally:
        await plugin.disconnect(client)


async def test_slash_command_body_dispatches_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invoking a registered slash-command callback translates the
    Discord ``Interaction`` into an :class:`InboundEnvelope` (``text``
    synthesizes ``/<name> <args>``) and calls
    :func:`dispatch_inbound` with it.

    Also confirms ``interaction.response.defer(ephemeral=True)`` is
    awaited — the Discord 3-second timeout requires an early ack.
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = Connector(
        id="acct-l9-dispatch",
        name="Discord L9 Dispatch",
        type="discord",
        config={},
        secrets={"BOT_TOKEN": "token"},
    )

    client = await plugin.connect(account, encryptor)
    try:
        # Capture dispatcher calls + provide a factory.
        dispatch_calls: list[tuple[str, Any, Any]] = []

        async def _fake_dispatch(
            account_id: str, envelope: Any, *, factory: Any
        ) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        sentinel_factory = object()
        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: sentinel_factory
        )

        # Pull the ``talk_to`` callback off the tree and invoke it as
        # the SDK would.
        tree = _StubCommandTree.instances[0]
        talk_to_entry = next(
            c for c in tree.commands if c["name"] == "talk_to"
        )
        callback = talk_to_entry["callback"]

        interaction = _make_interaction(
            user_id=555,
            display_name="Alice",
            channel_id=8888,
            guild_id=4242,
            token="tok-talk-to",
        )
        await callback(interaction, "my-agent")

        # The defer ack fired (3-second timeout discipline). M11 F14 L7:
        # ``talk_to`` is a channel-affecting command → PUBLIC ack
        # (``ephemeral=False``), so there's no ephemeral-then-channel flip.
        interaction.response.defer.assert_awaited_once_with(ephemeral=False)

        # Exactly one dispatcher call with the synthesized envelope.
        assert len(dispatch_calls) == 1
        account_id, envelope, factory = dispatch_calls[0]
        assert account_id == "acct-l9-dispatch"
        assert factory is sentinel_factory
        assert envelope.platform == "discord"
        assert envelope.account_id == "acct-l9-dispatch"
        assert envelope.channel_id == "8888"
        assert envelope.thread_id is None
        assert envelope.peer_id == "555"
        assert envelope.peer_name == "Alice"
        # Synthesized F7 text-prefix form — args appended after a single
        # space; the dispatcher's ``_parse_command`` whitespace-splits.
        # Bug H fix: the envelope text uses the HYPHENATED form (``/talk-to``,
        # not ``/talk_to``) so ``_parse_command`` can parse it — underscore
        # is outside ``_NAME_TAIL_CHARS`` and would cause parse → None.
        assert envelope.text == "/talk-to my-agent"
        # raw carries the F8 L6 + L8 keys.
        assert envelope.raw["is_dm"] is False
        assert envelope.raw["guild_id"] == "4242"
        assert envelope.raw["member_roles"] == []
        # M11 F14 L7: the interaction-followup token is threaded onto raw
        # as a plain string for the dispatcher to copy onto OutboundTarget.
        assert envelope.raw["interaction_followup_token"] == "tok-talk-to"
    finally:
        await plugin.disconnect(client)


def test_build_slash_envelope_talk_to_hyphenates_command_name() -> None:
    """``_build_slash_envelope`` with ``command_name="talk_to"`` produces
    envelope text ``/talk-to ...`` (hyphen, not underscore).

    Bug H root cause: ``_parse_command`` accepts only ``[a-z0-9-]`` in the
    command name tail — underscore is outside that set and causes
    ``_parse_command`` to return ``None``, so the envelope never reaches the
    built-in handler.  The fix is in ``_build_slash_envelope``: hyphenate the
    ``command_name`` before synthesising the text.

    This test exercises the REAL parse path (G.1's blind spot): it calls
    ``_build_slash_envelope`` and then feeds the resulting text through
    ``_parse_command``, asserting the round-trip succeeds.

    Would FAIL pre-fix (text ``/talk_to Sonos Agent`` → _parse_command → None).
    PASSes post-fix (text ``/talk-to Sonos Agent`` → _parse_command → ok).
    """
    from the_one.connectors._commands import _parse_command
    from the_one.connectors._discord import _build_slash_envelope

    interaction = _make_interaction(
        user_id=999,
        display_name="Tester",
        channel_id=1234,
        guild_id=5678,
        token="tok-regression",
    )

    envelope = _build_slash_envelope(
        interaction=interaction,
        account_id="acct-regression",
        command_name="talk_to",
        args="Sonos Agent",
    )

    # 1. The envelope text must be hyphenated so _parse_command can parse it.
    assert envelope.text == "/talk-to Sonos Agent", (
        f"Expected '/talk-to Sonos Agent' but got {envelope.text!r}; "
        "Bug H: underscore in command_name breaks _parse_command"
    )

    # 2. Feed the text through _parse_command — must parse cleanly (not None).
    parsed = _parse_command(envelope.text)
    assert parsed is not None, (
        f"_parse_command({envelope.text!r}) returned None; "
        "the envelope text must survive the parse layer to reach the handler"
    )
    cmd_name, cmd_args = parsed
    assert cmd_name == "talk-to"
    assert cmd_args == ["Sonos", "Agent"]


def test_build_slash_envelope_non_underscore_commands_unchanged() -> None:
    """Commands without underscores (``agents``, ``whoami``, etc.) are
    unaffected by the Bug H hyphenation — ``replace("_", "-")`` is a no-op
    when there are no underscores.
    """
    from the_one.connectors._commands import _parse_command
    from the_one.connectors._discord import _build_slash_envelope

    for cmd in ("agents", "whoami", "new", "reset", "help"):
        interaction = _make_interaction()
        envelope = _build_slash_envelope(
            interaction=interaction,
            account_id="acct-test",
            command_name=cmd,
            args="",
        )
        # text must be ``/agents``, ``/whoami``, etc. — no transformation.
        assert envelope.text == f"/{cmd}", (
            f"Expected '/{cmd}' but got {envelope.text!r}"
        )
        # And it must still parse cleanly.
        parsed = _parse_command(envelope.text)
        assert parsed is not None
        assert parsed[0] == cmd


async def test_slash_command_body_handles_empty_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``args=""`` (or unset) → envelope text is just ``/<name>`` with
    no trailing whitespace. Pins the canonical form so audit-log keys
    stay tidy.
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        dispatch_calls: list[tuple[str, Any, Any]] = []

        async def _fake_dispatch(
            account_id: str, envelope: Any, *, factory: Any
        ) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: object()
        )

        # Invoke ``/help`` with no args — slash command default.
        tree = _StubCommandTree.instances[0]
        help_entry = next(c for c in tree.commands if c["name"] == "help")
        interaction = _make_interaction(user_id=111, display_name="Bob")
        # Call without passing args (default = "").
        await help_entry["callback"](interaction)

        assert len(dispatch_calls) == 1
        envelope = dispatch_calls[0][1]
        assert envelope.text == "/help"
    finally:
        await plugin.disconnect(client)


async def test_slash_command_body_marks_dm_in_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DM slash invocation (``interaction.guild_id is None``) →
    ``envelope.raw["is_dm"]=True`` and ``raw["guild_id"]=None``. The
    dispatcher's L6 ``is_dm`` consult site reads this and behaves
    correctly.
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        dispatch_calls: list[tuple[str, Any, Any]] = []

        async def _fake_dispatch(
            account_id: str, envelope: Any, *, factory: Any
        ) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: object()
        )

        tree = _StubCommandTree.instances[0]
        whoami_entry = next(c for c in tree.commands if c["name"] == "whoami")
        # DM channel: guild_id=None.
        interaction = _make_interaction(
            user_id=222, display_name="Cara", channel_id=999, guild_id=None
        )
        await whoami_entry["callback"](interaction)

        assert len(dispatch_calls) == 1
        envelope = dispatch_calls[0][1]
        assert envelope.raw["is_dm"] is True
        assert envelope.raw["guild_id"] is None
    finally:
        await plugin.disconnect(client)


async def test_slash_command_body_swallows_dispatcher_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatcher raises → handler logs and returns; the SDK's
    interaction handler MUST NOT propagate (a single slash failure
    must not crash the gateway).
    """
    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        async def _raising_dispatch(
            account_id: str, envelope: Any, *, factory: Any
        ) -> None:
            raise RuntimeError("simulated dispatcher failure")

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _raising_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: object()
        )

        tree = _StubCommandTree.instances[0]
        agents_entry = next(c for c in tree.commands if c["name"] == "agents")
        interaction = _make_interaction()
        # MUST NOT raise.
        await agents_entry["callback"](interaction)
    finally:
        await plugin.disconnect(client)


async def test_slash_command_body_returns_when_factory_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``get_factory()`` returns None → defer fires, dispatcher is NOT
    called, a WARNING is logged.

    Mirrors the L4 on_message factory-race posture for the slash path.
    """
    import logging

    _patch_discord(monkeypatch)

    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        dispatch_calls: list[tuple[str, Any, Any]] = []

        async def _fake_dispatch(
            account_id: str, envelope: Any, *, factory: Any
        ) -> None:
            dispatch_calls.append((account_id, envelope, factory))

        monkeypatch.setattr(
            "the_one.connectors._inbound.dispatch_inbound", _fake_dispatch
        )
        monkeypatch.setattr(
            "the_one.agent.factory.get_factory", lambda: None
        )

        tree = _StubCommandTree.instances[0]
        new_entry = next(c for c in tree.commands if c["name"] == "new")
        interaction = _make_interaction()
        with caplog.at_level(
            logging.WARNING, logger="the_one.connectors._discord"
        ):
            await new_entry["callback"](interaction)

        # Dispatcher MUST NOT be called.
        assert dispatch_calls == []
        # WARNING about the unavailable factory.
        warnings_logged = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "AgentFactory" in r.message
        ]
        assert warnings_logged, (
            "expected a WARNING log when the factory is unavailable"
        )
    finally:
        await plugin.disconnect(client)


# ─────────────────────────────────────────────────────────────────
# M11 F3 L3: enumerate_discoverable_entities — substrate hook
# ─────────────────────────────────────────────────────────────────
#
# Path B: extend ``_StubDiscordClient`` (the SDK-stub the test file
# already uses for ``plugin.connect``) to populate ``users`` / ``guilds``
# / ``get_all_channels()``; then call ``plugin.enumerate_discoverable_entities(client)``
# on the real ``DiscordClient`` produced by ``plugin.connect(...)``.
# This reuses the established connect-path fixture pattern and avoids
# hand-constructing ``DiscordClient`` with its 5 internal fields.


class _StubDiscoverableUser:
    """Mirrors the subset of ``discord.User`` the hook touches.

    The hook reads ``id``, ``name``, ``global_name``, ``bot``.
    """

    def __init__(
        self,
        *,
        id: int,  # noqa: A002 — mirrors SDK
        name: str,
        global_name: str | None = None,
        bot: bool = False,
    ) -> None:
        self.id = id
        self.name = name
        self.global_name = global_name
        self.bot = bot


class _StubDiscoverableRole:
    """Mirrors the subset of ``discord.Role`` the hook touches.

    The hook reads ``id``, ``name``, ``position``, ``mentionable``.
    """

    def __init__(
        self,
        *,
        id: int,  # noqa: A002 — mirrors SDK
        name: str,
        position: int = 0,
        mentionable: bool = False,
    ) -> None:
        self.id = id
        self.name = name
        self.position = position
        self.mentionable = mentionable


class _StubDiscoverableChannel:
    """Mirrors the subset of ``discord.GuildChannel`` the hook touches.

    The hook reads ``id``, ``name``, ``type``, ``guild.id``. ``guild``
    is back-linked from the parent ``_StubDiscoverableGuild``.
    """

    def __init__(
        self,
        *,
        id: int,  # noqa: A002 — mirrors SDK
        name: str,
        type: str,  # noqa: A002 — mirrors SDK
    ) -> None:
        self.id = id
        self.name = name
        self.type = type
        self.guild: _StubDiscoverableGuild | None = None  # back-linked


class _StubDiscoverableGuild:
    """Mirrors the subset of ``discord.Guild`` the hook touches.

    The hook reads ``id``, ``name``, ``member_count``, iterates
    ``channels`` (via ``Client.get_all_channels``) and ``roles``.
    Back-links ``channel.guild = self`` so the hook's
    ``channel.guild.id`` access resolves.
    """

    def __init__(
        self,
        *,
        id: int,  # noqa: A002 — mirrors SDK
        name: str,
        member_count: int | None,
        channels: list[_StubDiscoverableChannel] | None = None,
        roles: list[_StubDiscoverableRole] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.member_count = member_count
        self.channels = channels or []
        self.roles = roles or []
        for ch in self.channels:
            ch.guild = self


def _populate_discoverable_caches(stub_sdk_client: _StubDiscordClient) -> None:
    """Populate the connected stub SDK client with two guilds + users.

    Matches the shape the hook expects to read from:

    - 2 users (one with ``global_name``, one without; mix of bot/human)
    - 2 guilds, each with 2 channels (text + voice) and 2 roles
    - ``get_all_channels()`` iterates ``for g in self.guilds: yield from g.channels``
      via the method already defined on ``_StubDiscordClient``.
    """
    users = [
        _StubDiscoverableUser(
            id=1001,
            name="alice_legacy",
            global_name="Alice",
            bot=False,
        ),
        _StubDiscoverableUser(
            id=1002,
            name="oldname_bob",
            global_name=None,  # exercises the ``global_name or name`` fallback
            bot=False,
        ),
        _StubDiscoverableUser(
            id=1003,
            name="helper_bot",
            global_name="Helper",
            bot=True,
        ),
    ]
    guild_a = _StubDiscoverableGuild(
        id=2001,
        name="Test Guild A",
        member_count=42,
        channels=[
            _StubDiscoverableChannel(id=3001, name="general", type="text"),
            _StubDiscoverableChannel(id=3002, name="voice-lobby", type="voice"),
        ],
        roles=[
            _StubDiscoverableRole(
                id=4001, name="moderators", position=2, mentionable=True
            ),
            _StubDiscoverableRole(
                id=4002, name="everyone", position=0, mentionable=False
            ),
        ],
    )
    guild_b = _StubDiscoverableGuild(
        id=2002,
        name="Test Guild B",
        member_count=7,
        channels=[
            _StubDiscoverableChannel(id=3003, name="lounge", type="text"),
        ],
        roles=[
            _StubDiscoverableRole(
                id=4003, name="vip", position=1, mentionable=True
            ),
        ],
    )
    stub_sdk_client.users = list(users)
    stub_sdk_client.guilds = [guild_a, guild_b]


def test_discord_plugin_implements_enumerate_discoverable_entities() -> None:
    """The plugin exposes the OPTIONAL hook discoverable via ``getattr``.

    Pins the substrate-side contract: ``hasattr`` is True, the resolved
    attribute is not None, and it is callable. The L4 cache sweep and
    Studio API endpoint will dispatch via this same ``getattr`` shape.
    """
    plugin = DiscordPlugin()
    assert hasattr(plugin, "enumerate_discoverable_entities") is True
    hook = getattr(plugin, "enumerate_discoverable_entities", None)
    assert hook is not None
    assert callable(hook)


async def test_discord_plugin_enumerate_returns_populated_axes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy-path: the hook returns a fully-populated snapshot.

    Path B fixture: ``plugin.connect`` produces the real ``DiscordClient``
    wrapping a stub SDK client; the test then populates the stub's
    ``users`` / ``guilds`` / ``get_all_channels()`` caches and invokes
    the hook. Asserts the four axes, the ``@``/``#`` label prefixes,
    the ``guild:{id}`` grouping for channels and roles, and the
    ``+00:00``-offset ISO 8601 ``fetched_at`` shape.
    """
    import re

    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        stub_sdk = _StubDiscordClient.instances[-1]
        _populate_discoverable_caches(stub_sdk)

        result = plugin.enumerate_discoverable_entities(client)

        assert isinstance(result, DiscoverableEntities)

        # Peers — 3 users, all with @-prefixed labels. ``global_name`` is
        # preferred when present (alice → "@Alice"; helper_bot → "@Helper");
        # falls back to ``name`` when None (oldname_bob → "@oldname_bob").
        peer_by_id = {p.id: p for p in result.peers}
        assert set(peer_by_id) == {"1001", "1002", "1003"}
        assert peer_by_id["1001"].label == "@Alice"
        assert peer_by_id["1002"].label == "@oldname_bob"
        assert peer_by_id["1003"].label == "@Helper"
        assert peer_by_id["1003"].metadata == {"bot": True}
        assert peer_by_id["1001"].metadata == {"bot": False}
        assert all(p.group is None for p in result.peers)

        # Channels — 3 total (2 from guild A, 1 from guild B), all with
        # ``#`` labels and ``guild:{id}`` group keys.
        channel_by_id = {c.id: c for c in result.channels}
        assert set(channel_by_id) == {"3001", "3002", "3003"}
        assert channel_by_id["3001"].label == "#general"
        assert channel_by_id["3001"].group == "guild:2001"
        assert channel_by_id["3001"].metadata == {"type": "text"}
        assert channel_by_id["3002"].metadata == {"type": "voice"}
        assert channel_by_id["3003"].group == "guild:2002"

        # Groups — 2 guilds, bare names as labels.
        group_by_id = {g.id: g for g in result.groups}
        assert set(group_by_id) == {"2001", "2002"}
        assert group_by_id["2001"].label == "Test Guild A"
        assert group_by_id["2001"].metadata == {"member_count": 42}
        assert group_by_id["2002"].metadata == {"member_count": 7}
        assert all(g.group is None for g in result.groups)

        # Roles — 3 total (2 from guild A, 1 from guild B), ``@``-prefixed
        # labels, ``guild:{id}`` group keys, full metadata.
        role_by_id = {r.id: r for r in result.roles}
        assert set(role_by_id) == {"4001", "4002", "4003"}
        assert role_by_id["4001"].label == "@moderators"
        assert role_by_id["4001"].group == "guild:2001"
        assert role_by_id["4001"].metadata == {
            "position": 2,
            "mentionable": True,
        }
        assert role_by_id["4003"].group == "guild:2002"

        # ``fetched_at`` — ISO 8601 with ``+00:00`` offset (the substrate
        # stays with ``datetime.now(UTC).isoformat()``'s default form; no
        # ``Z``-suffix substitution).
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$",
            result.fetched_at,
        ), result.fetched_at
    finally:
        await plugin.disconnect(client)


async def test_discord_plugin_enumerate_excludes_category_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug E (F14 L3): categories are dropped, every other type is kept.

    ``CategoryChannel`` is a container, never a message's channel — the
    ACL channel-match can never accept its id, so offering it in any
    picker silently denies all inbound. The substrate excludes
    ``str(channel.type) == "category"`` at the enumerate site. This test
    pins BOTH directions: a mixed-type guild yields no category id AND
    retains its text/voice/forum/announcement ids — the inclusion half
    guards against a future over-broad positive allowlist that would
    wrongly drop message-bearing types.
    """
    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        stub_sdk = _StubDiscordClient.instances[-1]
        stub_sdk.users = []
        stub_sdk.guilds = [
            _StubDiscoverableGuild(
                id=6001,
                name="Mixed-Type Guild",
                member_count=10,
                channels=[
                    _StubDiscoverableChannel(
                        id=7001, name="Section", type="category"
                    ),
                    _StubDiscoverableChannel(
                        id=7002, name="general", type="text"
                    ),
                    _StubDiscoverableChannel(
                        id=7003, name="voice-lobby", type="voice"
                    ),
                    _StubDiscoverableChannel(
                        id=7004, name="ideas", type="forum"
                    ),
                    _StubDiscoverableChannel(
                        id=7005, name="news", type="news"
                    ),
                ],
            ),
        ]

        result = plugin.enumerate_discoverable_entities(client)

        channel_ids = {c.id for c in result.channels}
        # Exclusion half: the category id is gone.
        assert "7001" not in channel_ids
        # Inclusion half: every message-bearing type survives.
        assert {"7002", "7003", "7004", "7005"} <= channel_ids
        assert channel_ids == {"7002", "7003", "7004", "7005"}
    finally:
        await plugin.disconnect(client)


def test_stub_plugin_does_not_implement_enumerate_discoverable_entities() -> None:
    """The stub plugin pins the fallback contract — hook is absent.

    Per the substrate design: ``StubPlugin`` deliberately does NOT
    implement ``enumerate_discoverable_entities``. Consumers reach via
    ``getattr(plugin, "enumerate_discoverable_entities", None)`` and
    fall back to the chip-list editor when ``None`` comes back. This
    test pins that the stub stays absent so future maintenance does
    not silently add the hook and break the fallback regression net.
    """
    plugin = StubPlugin()
    assert getattr(plugin, "enumerate_discoverable_entities", None) is None


async def test_discord_plugin_enumerate_tolerates_unknown_member_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Guild.member_count is None`` collapses to ``metadata["member_count"] == 0``.

    Discord's ``Guild.member_count`` is intent-gated — without the
    ``members`` intent (or under partial-chunking) it can be ``None``.
    The substrate stays defensive and reports 0 to keep the JSON shape
    stable at the API layer.
    """
    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        stub_sdk = _StubDiscordClient.instances[-1]
        stub_sdk.users = []
        stub_sdk.guilds = [
            _StubDiscoverableGuild(
                id=5001,
                name="Member-Count-Unknown Guild",
                member_count=None,  # the intent-gated case
                channels=[],
                roles=[],
            ),
        ]

        result = plugin.enumerate_discoverable_entities(client)

        assert len(result.groups) == 1
        assert result.groups[0].id == "5001"
        assert result.groups[0].metadata == {"member_count": 0}
    finally:
        await plugin.disconnect(client)


async def test_discord_plugin_enumerate_user_label_falls_back_to_name_when_global_name_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``user.global_name`` None → label uses ``user.name``; present → uses ``global_name``.

    Discord's username-system migration: newer accounts expose
    ``global_name`` (the display name); older accounts only have
    ``name``. The substrate exercises ``global_name or name`` and
    prefixes with ``@``.
    """
    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        stub_sdk = _StubDiscordClient.instances[-1]
        stub_sdk.users = [
            _StubDiscoverableUser(
                id=6001,
                name="legacy_user",
                global_name=None,
                bot=False,
            ),
            _StubDiscoverableUser(
                id=6002,
                name="raw_handle",
                global_name="Display Name",
                bot=False,
            ),
        ]
        stub_sdk.guilds = []

        result = plugin.enumerate_discoverable_entities(client)

        peer_by_id = {p.id: p for p in result.peers}
        assert peer_by_id["6001"].label == "@legacy_user"
        assert peer_by_id["6002"].label == "@Display Name"
    finally:
        await plugin.disconnect(client)


async def test_discord_plugin_enumerate_dedupes_users_defensively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive id-keyed dedup — first occurrence wins.

    The SDK's ``Client.users`` is already unique-by-id (via
    ``list(self._connection._users.values())``). The hook nevertheless
    deduplicates via a dict keyed by id to guard against
    scaffold-only duplication in tests and future SDK behavior change.
    This test passes a stub ``users`` list with two entries sharing an
    id; only the first occurrence appears in the result.
    """
    _patch_discord(monkeypatch)
    encryptor = _make_encryptor()
    plugin = DiscordPlugin()
    account = _make_account(encryptor)

    client = await plugin.connect(account, encryptor)
    try:
        stub_sdk = _StubDiscordClient.instances[-1]
        stub_sdk.users = [
            _StubDiscoverableUser(
                id=7001,
                name="first_appearance",
                global_name="First",
                bot=False,
            ),
            _StubDiscoverableUser(
                # Same id; different name. First-occurrence wins.
                id=7001,
                name="second_appearance",
                global_name="Second",
                bot=True,
            ),
            _StubDiscoverableUser(
                id=7002,
                name="unique_user",
                global_name="Unique",
                bot=False,
            ),
        ]
        stub_sdk.guilds = []

        result = plugin.enumerate_discoverable_entities(client)

        peers_by_id = {p.id: p for p in result.peers}
        assert set(peers_by_id) == {"7001", "7002"}
        # First-occurrence wins: ``@First`` not ``@Second``.
        assert peers_by_id["7001"].label == "@First"
        assert peers_by_id["7001"].metadata == {"bot": False}
        # Result list length matches dedup expectation.
        assert len(result.peers) == 2
    finally:
        await plugin.disconnect(client)


# --- M11 F14 L7: ephemeral interaction-followup routing ----------------------


def _make_followup_sdk(*, application_id: int | None = 5550001) -> Any:
    """A ``discord.Client``-spec SDK mock wired for the followup branch.

    ``application_id`` is the bot's app id (real ``discord.Client`` attr,
    populated at READY); ``None`` simulates the pre-READY window.
    ``_connection`` is the private ConnectionState the webhook needs — a
    sentinel here, since we patch ``Webhook.from_state`` and never touch it.
    """
    import discord

    sdk = MagicMock(spec=discord.Client)
    sdk.user = None
    sdk.is_closed = MagicMock(return_value=False)
    sdk.application_id = application_id
    sdk._connection = MagicMock(name="connection-state-sentinel")
    return sdk


def _patch_from_state(
    monkeypatch: pytest.MonkeyPatch, *, sent_message_id: int = 808080
) -> tuple[Any, dict[str, Any]]:
    """Patch ``discord.Webhook.from_state`` with a recorder.

    Returns ``(webhook_mock, captured)`` where ``captured`` records the
    ``data``/``state`` kwargs ``from_state`` was called with, and the
    webhook's ``send`` is an AsyncMock returning a Message-shaped object.
    NO real network.
    """
    import discord

    sent = MagicMock()
    sent.id = sent_message_id
    webhook = MagicMock(name="application-webhook")
    webhook.send = AsyncMock(return_value=sent)

    captured: dict[str, Any] = {}

    def _fake_from_state(*, data: Any, state: Any) -> Any:
        captured["data"] = data
        captured["state"] = state
        return webhook

    monkeypatch.setattr(discord.Webhook, "from_state", _fake_from_state)
    return webhook, captured


async def test_send_ephemeral_with_token_fires_followup_not_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ephemeral=True + token present + application_id set → followup path
    fires (channel send NOT)."""
    sdk = _make_followup_sdk(application_id=5550001)
    channel = _make_text_channel_mock(channel_id=11111)
    sdk.get_channel = MagicMock(return_value=channel)
    webhook, captured = _patch_from_state(monkeypatch, sent_message_id=808080)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(
        channel_id="11111",
        thread_id=None,
        ephemeral=True,
        interaction_followup_token="tok-abc",
    )

    result = await client.send(target, "only you can see this")

    # Followup fired with the reconstructed application (type=3) webhook.
    webhook.send.assert_awaited_once_with("only you can see this", ephemeral=True)
    assert captured["data"] == {"id": 5550001, "type": 3, "token": "tok-abc"}
    assert captured["state"] is sdk._connection
    # Channel send NOT used.
    channel.send.assert_not_called()
    # Result marks the ephemeral path.
    assert result.platform_message_id == "808080"
    assert result.details == {"channel_type": "ephemeral_followup"}


async def test_send_ephemeral_without_token_fires_channel_not_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ephemeral=True but NO token → channel path fires (followup NOT)."""
    sdk = _make_followup_sdk()
    channel = _make_text_channel_mock(channel_id=11111, sent_message_id=22222)
    sdk.get_channel = MagicMock(return_value=channel)
    webhook, _ = _patch_from_state(monkeypatch)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(
        channel_id="11111",
        thread_id=None,
        ephemeral=True,
        interaction_followup_token=None,
    )

    result = await client.send(target, "channel visible")

    channel.send.assert_awaited_once_with("channel visible")
    webhook.send.assert_not_called()
    assert result.platform_message_id == "22222"
    assert result.details == {"channel_id": "11111", "channel_type": "text"}


async def test_send_non_ephemeral_with_token_fires_channel_not_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ephemeral=False but token present → channel path fires (followup NOT).

    A channel-affecting command (talk_to/new/reset) carries a token but
    keeps the default ephemeral=False → must go to the channel.
    """
    sdk = _make_followup_sdk()
    channel = _make_text_channel_mock(channel_id=11111, sent_message_id=33333)
    sdk.get_channel = MagicMock(return_value=channel)
    webhook, _ = _patch_from_state(monkeypatch)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(
        channel_id="11111",
        thread_id=None,
        ephemeral=False,
        interaction_followup_token="tok-abc",
    )

    result = await client.send(target, "channel visible")

    channel.send.assert_awaited_once_with("channel visible")
    webhook.send.assert_not_called()
    assert result.platform_message_id == "33333"
    assert result.details == {"channel_id": "11111", "channel_type": "text"}


async def test_send_non_ephemeral_without_token_fires_channel_not_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ephemeral=False + NO token (the ordinary agent-reply path) → channel
    path fires (followup NOT)."""
    sdk = _make_followup_sdk()
    channel = _make_text_channel_mock(channel_id=11111, sent_message_id=44444)
    sdk.get_channel = MagicMock(return_value=channel)
    webhook, _ = _patch_from_state(monkeypatch)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(channel_id="11111", thread_id=None)

    result = await client.send(target, "agent reply")

    channel.send.assert_awaited_once_with("agent reply")
    webhook.send.assert_not_called()
    assert result.platform_message_id == "44444"
    assert result.details == {"channel_id": "11111", "channel_type": "text"}


async def test_send_ephemeral_token_expired_falls_back_to_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ephemeral followup raises NotFound (expired token) → fall back to the
    channel path with a ``[ephemeral fallback]`` prefix; no exception."""
    import discord

    sdk = _make_followup_sdk(application_id=5550001)
    channel = _make_text_channel_mock(channel_id=11111, sent_message_id=55555)
    sdk.get_channel = MagicMock(return_value=channel)

    # Webhook reconstructs fine, but .send raises NotFound (404).
    not_found = _make_http_exception(discord.errors.NotFound, status=404)
    webhook = MagicMock(name="application-webhook")
    webhook.send = AsyncMock(side_effect=not_found)
    monkeypatch.setattr(
        discord.Webhook, "from_state", lambda *, data, state: webhook
    )

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(
        channel_id="11111",
        thread_id=None,
        ephemeral=True,
        interaction_followup_token="tok-expired",
    )

    result = await client.send(target, "self only")

    # Followup attempted, then channel fallback with the marker prefix.
    webhook.send.assert_awaited_once()
    channel.send.assert_awaited_once_with("[ephemeral fallback] self only")
    assert result.platform_message_id == "55555"
    assert result.details == {"channel_id": "11111", "channel_type": "text"}


async def test_send_ephemeral_pre_ready_no_application_id_uses_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """application_id is None (pre-READY) → channel send (the accepted
    channel-leak edge), followup NOT attempted."""
    sdk = _make_followup_sdk(application_id=None)
    channel = _make_text_channel_mock(channel_id=11111, sent_message_id=66666)
    sdk.get_channel = MagicMock(return_value=channel)
    webhook, _ = _patch_from_state(monkeypatch)

    client = _make_discord_client_with_sdk(sdk)
    target = OutboundTarget(
        channel_id="11111",
        thread_id=None,
        ephemeral=True,
        interaction_followup_token="tok-abc",
    )

    result = await client.send(target, "self only")

    webhook.send.assert_not_called()
    channel.send.assert_awaited_once_with("self only")
    assert result.platform_message_id == "66666"
