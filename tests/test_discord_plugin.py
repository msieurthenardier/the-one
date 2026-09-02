"""Tests for ``the_one.connectors.discord.plugin`` — envelope translation
(AC-7), Protocol conformance (AC-8), production registration (AC-9), and
the close-code-policy chain through ``ConnectorManager`` (AC-4/AC-5).
Mission 23 Flight 3 Leg 1. All against the fake gateway + a mocked
``httpx`` transport — no live network.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from tests._discord_gateway_fixture import FakeGateway
from the_one.connectors import registry
from the_one.connectors.base import ConnectorClient, ConnectorPlugin
from the_one.connectors.discord._rest import RestClient
from the_one.connectors.discord.plugin import DiscordClient, DiscordPlugin, _AccountState
from the_one.connectors.manager import ConnectorManager
from the_one.db.models import Connector
from the_one.encryption import get_encryptor

BOT_ID = "bot-1"


def _account(account_id: str = "acc-1", token: str = "tok") -> Connector:
    return Connector(id=account_id, name="Test Discord", type="discord", secrets={"token": token})


async def _channel_type_handler(request: httpx.Request) -> httpx.Response:
    channel_id = request.url.path.rsplit("/", 1)[-1]
    types = {"guild-text-1": 0, "thread-1": 11}
    return httpx.Response(200, json={"id": channel_id, "type": types.get(channel_id, 0)})


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.clear_for_test()
    yield
    registry.clear_for_test()


# ── AC-7: envelope translation ──────────────────────────────────────────


async def test_translate_message_create_fields_and_self_webhook_unallowlisted_bot_drop(
    tmp_path: Path,
):
    """DD-4 amended 2026-09-01: self/webhook drop unconditionally; a
    foreign bot with no `config.allowlist.peers` entry (this account has
    none configured) also drops — see
    ``test_foreign_bot_on_allowlist_is_translated_like_a_peer`` for the
    admitted-bot counterpart, which this test used to blanket-forbid."""

    async def gw_handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.send_ready(
            session_id="s1",
            resume_gateway_url="ws://ignored",
            user_id=BOT_ID,
            username="TestBot",
            private_channels=[{"id": "dm-channel-1", "type": 1}],
        )
        await session.send_message_create(
            {
                "channel_id": "dm-channel-1",
                "content": "hello dm",
                "author": {"id": "peer-1", "username": "Alice", "global_name": "Alice G"},
                "mentions": [],
            },
            seq=2,
        )
        await session.send_message_create(
            {
                "channel_id": "guild-text-1",
                "content": "hey <@bot-1>",
                "author": {"id": "peer-2", "username": "Bob"},
                "mentions": [{"id": BOT_ID}],
            },
            seq=3,
        )
        await session.send_message_create(
            {
                "channel_id": "thread-1",
                "content": "in a thread",
                "author": {"id": "peer-3", "username": "Carl"},
                "mentions": [],
            },
            seq=4,
        )
        await session.send_message_create(
            {
                "channel_id": "guild-text-1",
                "content": "bot noise",
                "author": {"id": "other-bot", "username": "OtherBot", "bot": True},
                "mentions": [],
            },
            seq=5,
        )
        await session.send_message_create(
            {
                "channel_id": "guild-text-1",
                "content": "webhook noise",
                "author": {"id": "webhook-user", "username": "Webhook"},
                "webhook_id": "wh-1",
                "mentions": [],
            },
            seq=6,
        )
        await session.send_message_create(
            {
                "channel_id": "guild-text-1",
                "content": "self echo",
                "author": {"id": BOT_ID, "username": "TestBot"},
                "mentions": [],
            },
            seq=7,
        )
        await asyncio.sleep(0.4)

    gw = FakeGateway(gw_handler)
    url = await gw.start()
    plugin = DiscordPlugin(
        gateway_url=url, rest_transport=httpx.MockTransport(_channel_type_handler)
    )
    encryptor = get_encryptor(tmp_path)
    account = _account()
    inbound = []

    async def on_inbound(envelope):
        inbound.append(envelope)

    client = await plugin.connect(account, encryptor, on_inbound)
    try:
        await asyncio.sleep(0.3)
        assert len(inbound) == 3  # unallowlisted-bot/self/webhook messages dropped
        dm, mention, thread_msg = inbound

        assert dm.is_dm is True
        assert dm.thread_id is None
        assert dm.mentions_bot is False
        assert dm.peer_name == "Alice G"
        assert dm.peer_id == "peer-1"
        assert dm.text == "hello dm"

        assert mention.is_dm is False
        assert mention.mentions_bot is True
        assert mention.peer_name == "Bob"  # no global_name -> username fallback
        assert mention.thread_id is None

        assert thread_msg.is_dm is False
        assert thread_msg.thread_id == "thread-1"
        assert thread_msg.channel_id == "thread-1"
    finally:
        await plugin.disconnect(client)
        await gw.stop()


async def test_message_create_before_ready_processed_is_dropped_not_dispatched(tmp_path: Path):
    """Edge case: a fresh ``_AccountState`` has no ``bot_user_id`` yet — a
    translate call in that state must drop cleanly rather than emit an
    envelope with a wrong ``mentions_bot``."""
    from the_one.connectors.discord.plugin import _translate_message_create

    state = _AccountState()  # bot_user_id still None
    rest = RestClient("tok", base_url="https://discord.test/api/v10")
    try:
        envelope = await _translate_message_create(
            state,
            rest,
            {"channel_id": "c1", "content": "hi", "author": {"id": "u1"}, "mentions": []},
            "acc-1",
        )
        assert envelope is None
    finally:
        await rest.aclose()


# ── DD-4 amendment (2026-09-01): self/webhook vs. allowlisted-bot admission ──


async def test_self_authored_message_is_dropped_unconditionally():
    """(a) The bot's own author id drops even when (implausibly)
    allowlisted — self-drop is unconditional, checked before the
    allowlist."""
    from the_one.connectors.discord.plugin import _translate_message_create

    state = _AccountState(bot_user_id=BOT_ID, allowlist_peers=frozenset({BOT_ID}))
    rest = RestClient("tok", base_url="https://discord.test/api/v10")
    try:
        envelope = await _translate_message_create(
            state,
            rest,
            {
                "channel_id": "c1",
                "content": "self echo",
                "author": {"id": BOT_ID, "username": "TestBot"},
                "mentions": [],
            },
            "acc-1",
        )
        assert envelope is None
    finally:
        await rest.aclose()


async def test_webhook_authored_message_is_dropped_unconditionally():
    """(b) A webhook-authored message drops even when its author id is
    allowlisted — webhook-drop is unconditional, same as self."""
    from the_one.connectors.discord.plugin import _translate_message_create

    state = _AccountState(bot_user_id=BOT_ID, allowlist_peers=frozenset({"webhook-user"}))
    rest = RestClient("tok", base_url="https://discord.test/api/v10")
    try:
        envelope = await _translate_message_create(
            state,
            rest,
            {
                "channel_id": "c1",
                "content": "webhook noise",
                "author": {"id": "webhook-user", "username": "Webhook"},
                "webhook_id": "wh-1",
                "mentions": [],
            },
            "acc-1",
        )
        assert envelope is None
    finally:
        await rest.aclose()


async def test_foreign_bot_not_on_allowlist_is_dropped():
    """(c) A foreign bot author absent from ``allowlist_peers`` drops."""
    from the_one.connectors.discord.plugin import _translate_message_create

    state = _AccountState(bot_user_id=BOT_ID, allowlist_peers=frozenset({"some-other-bot"}))
    rest = RestClient("tok", base_url="https://discord.test/api/v10")
    try:
        envelope = await _translate_message_create(
            state,
            rest,
            {
                "channel_id": "c1",
                "content": "bot noise",
                "author": {"id": "other-bot", "username": "OtherBot", "bot": True},
                "mentions": [],
            },
            "acc-1",
        )
        assert envelope is None
    finally:
        await rest.aclose()


async def test_foreign_bot_on_allowlist_is_translated_like_a_peer():
    """(d) A foreign bot author present in ``allowlist_peers`` is
    translated into an ``InboundEnvelope`` exactly like a human peer —
    the pipeline's own ``is_admitted`` allowlist check then applies from
    there, as usual."""
    from the_one.connectors.discord.plugin import _translate_message_create

    state = _AccountState(bot_user_id=BOT_ID, allowlist_peers=frozenset({"driver-bot"}))
    rest = RestClient(
        "tok",
        base_url="https://discord.test/api/v10",
        transport=httpx.MockTransport(_channel_type_handler),
    )
    try:
        envelope = await _translate_message_create(
            state,
            rest,
            {
                "channel_id": "guild-text-1",
                "content": "driver says hi <@bot-1>",
                "author": {"id": "driver-bot", "username": "DriverBot", "bot": True},
                "mentions": [{"id": BOT_ID}],
            },
            "acc-1",
        )
        assert envelope is not None
        assert envelope.peer_id == "driver-bot"
        assert envelope.peer_name == "DriverBot"
        assert envelope.mentions_bot is True
    finally:
        await rest.aclose()


async def test_human_authored_message_is_unaffected_by_the_amendment():
    """(e) A non-bot author's message is translated exactly as before —
    the amendment only touches bot/webhook authors."""
    from the_one.connectors.discord.plugin import _translate_message_create

    state = _AccountState(bot_user_id=BOT_ID)  # allowlist_peers empty
    rest = RestClient(
        "tok",
        base_url="https://discord.test/api/v10",
        transport=httpx.MockTransport(_channel_type_handler),
    )
    try:
        envelope = await _translate_message_create(
            state,
            rest,
            {
                "channel_id": "guild-text-1",
                "content": "hi",
                "author": {"id": "peer-9", "username": "Dana"},
                "mentions": [],
            },
            "acc-1",
        )
        assert envelope is not None
        assert envelope.peer_id == "peer-9"
        assert envelope.peer_name == "Dana"
    finally:
        await rest.aclose()


async def test_connect_threads_config_allowlist_peers_into_account_state(tmp_path: Path):
    """Wiring: ``connect()`` populates ``_AccountState.allowlist_peers``
    from ``account.config.allowlist.peers`` on every (re)connect, so a
    PUT-driven allowlist change takes effect on the listener restart the
    PUT already performs."""

    async def gw_handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.send_ready(session_id="s1", resume_gateway_url="ws://ignored")
        await asyncio.sleep(0.3)

    gw = FakeGateway(gw_handler)
    url = await gw.start()
    plugin = DiscordPlugin(gateway_url=url)
    encryptor = get_encryptor(tmp_path)
    account = Connector(
        id="acc-1",
        name="Test Discord",
        type="discord",
        secrets={"token": "tok"},
        config={"allowlist": {"peers": ["driver-bot"]}},
    )
    client = await plugin.connect(account, encryptor, lambda _e: asyncio.sleep(0))
    try:
        assert plugin._state_for(account.id).allowlist_peers == frozenset({"driver-bot"})
    finally:
        await plugin.disconnect(client)
        await gw.stop()


# ── AC-8: Protocol conformance ───────────────────────────────────────────


def test_discord_plugin_satisfies_connector_plugin_protocol():
    assert isinstance(DiscordPlugin(), ConnectorPlugin)


async def test_discord_client_satisfies_connector_client_protocol_and_history_hook(
    tmp_path: Path,
):
    async def gw_handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.send_ready(session_id="s1", resume_gateway_url="ws://ignored")
        await asyncio.sleep(0.3)

    async def rest_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v10/channels/c1/messages"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "m1",
                    "content": "hey",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "author": {"id": "peer-1", "username": "Alice"},
                }
            ],
        )

    gw = FakeGateway(gw_handler)
    url = await gw.start()
    plugin = DiscordPlugin(gateway_url=url, rest_transport=httpx.MockTransport(rest_handler))
    encryptor = get_encryptor(tmp_path)
    client = await plugin.connect(_account(), encryptor, lambda _e: asyncio.sleep(0))
    try:
        assert isinstance(client, ConnectorClient)
        assert isinstance(client, DiscordClient)
        assert client.is_alive() is True

        from the_one.connectors.base import ChannelTarget

        history = await client.history(ChannelTarget(connector_id="acc-1", channel_id="c1"), 10)
        assert len(history) == 1
        assert history[0].peer_name == "Alice"
        assert history[0].content == "hey"
    finally:
        await plugin.disconnect(client)
        await gw.stop()


async def test_disconnect_is_idempotent(tmp_path: Path):
    async def gw_handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.send_ready(session_id="s1", resume_gateway_url="ws://ignored")
        await asyncio.sleep(0.3)

    gw = FakeGateway(gw_handler)
    url = await gw.start()
    plugin = DiscordPlugin(gateway_url=url)
    encryptor = get_encryptor(tmp_path)
    client = await plugin.connect(_account(), encryptor, lambda _e: asyncio.sleep(0))
    try:
        await plugin.disconnect(client)
        await plugin.disconnect(client)  # must not raise
    finally:
        await gw.stop()


async def test_doctor_ok_when_gateway_connected(tmp_path: Path):
    async def gw_handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.send_ready(session_id="s1", resume_gateway_url="ws://ignored")
        await asyncio.sleep(0.3)

    async def rest_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": BOT_ID, "username": "TestBot"})

    gw = FakeGateway(gw_handler)
    url = await gw.start()
    plugin = DiscordPlugin(gateway_url=url, rest_transport=httpx.MockTransport(rest_handler))
    encryptor = get_encryptor(tmp_path)
    account = _account()
    client = await plugin.connect(account, encryptor, lambda _e: asyncio.sleep(0))
    try:
        report = await plugin.doctor(account, encryptor)
        assert report.status == "ok"
        assert report.details["gateway_connected"] is True
    finally:
        await plugin.disconnect(client)
        await gw.stop()


async def test_doctor_degraded_when_rest_ok_but_not_connected(tmp_path: Path):
    async def rest_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": BOT_ID, "username": "TestBot"})

    plugin = DiscordPlugin(rest_transport=httpx.MockTransport(rest_handler))
    encryptor = get_encryptor(tmp_path)
    report = await plugin.doctor(_account(), encryptor)
    assert report.status == "degraded"


async def test_doctor_failed_on_bad_token(tmp_path: Path):
    async def rest_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    plugin = DiscordPlugin(rest_transport=httpx.MockTransport(rest_handler))
    encryptor = get_encryptor(tmp_path)
    report = await plugin.doctor(_account(), encryptor)
    assert report.status == "failed"


async def test_doctor_short_circuits_on_failure_marker_without_a_rest_call(tmp_path: Path):
    async def rest_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("doctor must short-circuit before making a REST call")

    plugin = DiscordPlugin(rest_transport=httpx.MockTransport(rest_handler))
    account = _account()
    plugin._state_for(account.id).failure = "discord gateway closed with permanent code 4004"
    encryptor = get_encryptor(tmp_path)
    report = await plugin.doctor(account, encryptor)
    assert report.status == "failed"
    assert "4004" in report.message


# ── AC-4/AC-5: close-code policy through ConnectorManager ───────────────


async def test_manager_stops_retrying_on_permanent_close(tmp_path: Path):
    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.close_with_code(4004, "bad token")

    gw = FakeGateway(handler)
    url = await gw.start()
    plugin = DiscordPlugin(gateway_url=url)
    registry.register_for_test("discord", plugin)
    encryptor = get_encryptor(tmp_path)
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    account = _account(token="bad")
    try:
        mgr.start(account, encryptor)
        listener_task = mgr._listeners[account.id].task
        await asyncio.wait_for(listener_task, timeout=5)
        assert listener_task.done()
        state = plugin._state_for(account.id)
        assert state.failure is not None
        report = await plugin.doctor(account, encryptor)
        assert report.status == "failed"
    finally:
        await mgr.drain()
        await gw.stop()


async def test_manager_keeps_backing_off_on_ordinary_connect_failure(tmp_path: Path):
    # Nothing listens on this port — an ordinary, non-permanent connect failure.
    plugin = DiscordPlugin(gateway_url="ws://127.0.0.1:1")
    registry.register_for_test("discord", plugin)
    encryptor = get_encryptor(tmp_path)
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    account = _account(account_id="acc-2")
    try:
        mgr.start(account, encryptor)
        await asyncio.sleep(0.2)
        listener_task = mgr._listeners[account.id].task
        assert not listener_task.done()  # still backing off, unlike the permanent-failure case
    finally:
        await mgr.drain()


# ── AC-9: production registration ────────────────────────────────────────


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    monkeypatch.setattr(db_connection, "_connection", None)


@pytest.mark.usefixtures("reset_lifespan_singletons")
async def test_lifespan_registers_discord_unconditionally(_isolated_data_dir):
    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        assert registry.get_plugin("discord") is not None

    assert registry.get_plugin("discord") is None


@pytest.mark.usefixtures("reset_lifespan_singletons")
async def test_lifespan_registers_discord_across_two_cycles(_isolated_data_dir):
    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        assert registry.get_plugin("discord") is not None
    assert registry.get_plugin("discord") is None

    async with lifespan(app):
        assert registry.get_plugin("discord") is not None
    assert registry.get_plugin("discord") is None
