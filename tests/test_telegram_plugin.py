"""Tests for ``the_one.connectors.telegram.plugin`` -- envelope translation
(AC-5), directory capture (AC-6), poll-loop/offset semantics (AC-1/AC-2),
permanent-failure/liveness (AC-3/AC-4), outbound shapes (AC-7), Protocol
conformance (AC-8), and production registration (AC-9). Mission 23 Flight
4 Leg 2. All against ``tests._telegram_api_fixture`` -- no live network.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from tests._telegram_api_fixture import FakeTelegramApi
from the_one.connectors import registry
from the_one.connectors.base import (
    ChannelTarget,
    ConnectorClient,
    ConnectorPlugin,
    PeerTarget,
    PermanentConnectorFailure,
)
from the_one.connectors.manager import ConnectorManager
from the_one.connectors.telegram.plugin import (
    TelegramClient,
    TelegramPlugin,
    _AccountState,
    _translate_message,
)
from the_one.db.models import Connector
from the_one.encryption import get_encryptor

BOT_ID = 111
BOT_USERNAME = "TestBot"


def _account(
    account_id: str = "acc-1", token: str = "tok", allowlist: list[str] | None = None
) -> Connector:
    config = {"allowlist": {"peers": allowlist}} if allowlist else {}
    return Connector(
        id=account_id,
        name="Test Telegram",
        type="telegram",
        secrets={"token": token},
        config=config,
    )


def _plugin(fake: FakeTelegramApi) -> TelegramPlugin:
    return TelegramPlugin(api_transport=fake.transport)


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.clear_for_test()
    yield
    registry.clear_for_test()


# ── AC-1 / AC-2: poll loop + offset semantics ───────────────────────────


async def test_poll_loop_happy_path_dispatches_and_advances_offset(tmp_path: Path):
    fake = FakeTelegramApi(
        me={"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME},
        updates=[
            {
                "update_id": 5,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 999, "type": "private"},
                    "from": {"id": 42, "first_name": "Alice"},
                    "text": "hi",
                },
            }
        ],
    )
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    inbound = []

    async def on_inbound(envelope):
        inbound.append(envelope)

    client = await plugin.connect(_account(), encryptor, on_inbound)
    try:
        await asyncio.sleep(0.05)  # let the first batch's dispatch settle
        assert len(inbound) == 1
        assert inbound[0].text == "hi"
        get_updates_calls = [c for c in fake.calls if c[0] == "getUpdates"]
        assert get_updates_calls[0][1].get("offset") is None  # first call: no offset
        await asyncio.sleep(0.15)  # let a second (now-empty) poll cycle fire
        get_updates_calls = [c for c in fake.calls if c[0] == "getUpdates"]
        assert len(get_updates_calls) >= 2
        assert get_updates_calls[1][1]["offset"] == 6  # last_update_id(5) + 1
        assert len(inbound) == 1  # empty-timeout poll dispatched nothing new
    finally:
        await plugin.disconnect(client)


async def test_redelivery_after_simulated_restart(tmp_path: Path):
    """AC-2: a batch dispatched but not re-polled is REDELIVERED to a
    fresh connect() with fresh in-memory state -- at-least-once, asserted
    not hidden."""
    fake = FakeTelegramApi(
        me={"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME},
        updates=[
            {
                "update_id": 1,
                "message": {
                    "chat": {"id": 1, "type": "private"},
                    "from": {"id": 7, "first_name": "Bob"},
                    "text": "once",
                },
            }
        ],
    )
    encryptor = get_encryptor(tmp_path)
    account = _account()

    first_inbound = []
    plugin1 = _plugin(fake)
    client1 = await plugin1.connect(
        account, encryptor, lambda e: first_inbound.append(e) or asyncio.sleep(0)
    )
    await asyncio.sleep(0.05)  # let the first batch's dispatch settle
    await plugin1.disconnect(client1)
    assert len(first_inbound) == 1

    # Simulated restart: a fresh plugin instance -> fresh _AccountState,
    # same fixture (Telegram-side state persists across the "restart").
    second_inbound = []
    plugin2 = _plugin(fake)
    client2 = await plugin2.connect(
        account, encryptor, lambda e: second_inbound.append(e) or asyncio.sleep(0)
    )
    try:
        await asyncio.sleep(0.05)  # let the second batch's dispatch settle
        assert len(second_inbound) == 1  # redelivered, not deduped
        assert second_inbound[0].text == "once"
    finally:
        await plugin2.disconnect(client2)


# ── AC-3: permanent failures ─────────────────────────────────────────────


@pytest.mark.parametrize("status", [401, 404, 409])
async def test_connect_raises_permanent_failure_on_get_me(tmp_path: Path, status):
    fake = FakeTelegramApi(error_status={"getMe": status})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    with pytest.raises(PermanentConnectorFailure):
        await plugin.connect(_account(), encryptor, lambda e: asyncio.sleep(0))
    assert plugin._state_for("acc-1").failure is not None


async def test_connect_raises_permanent_failure_on_first_get_updates_409(tmp_path: Path):
    fake = FakeTelegramApi(error_status={"getUpdates": 409})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    with pytest.raises(PermanentConnectorFailure):
        await plugin.connect(_account(), encryptor, lambda e: asyncio.sleep(0))


async def test_connect_ordinary_get_me_failure_is_not_permanent(tmp_path: Path):
    """Edge case: a transient getMe failure (network/500) is an ORDINARY
    failure -> manager backoff, not PermanentConnectorFailure."""
    fake = FakeTelegramApi(error_status={"getMe": 500})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    with pytest.raises(Exception) as exc_info:
        await plugin.connect(_account(), encryptor, lambda e: asyncio.sleep(0))
    assert not isinstance(exc_info.value, PermanentConnectorFailure)
    assert plugin._state_for("acc-1").failure is None


async def test_doctor_short_circuits_on_failure_marker_without_api_call(tmp_path: Path):
    async def handler(request):
        raise AssertionError("doctor must short-circuit before making an API call")

    import httpx

    plugin = TelegramPlugin(api_transport=httpx.MockTransport(handler))
    account = _account()
    plugin._state_for(account.id).failure = "telegram getMe -> 401: unauthorized"
    encryptor = get_encryptor(tmp_path)
    report = await plugin.doctor(account, encryptor)
    assert report.status == "failed"
    assert "401" in report.message


async def test_connect_clears_failure_marker(tmp_path: Path):
    fake = FakeTelegramApi(me={"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME})
    plugin = _plugin(fake)
    account = _account()
    plugin._state_for(account.id).failure = "stale marker"
    encryptor = get_encryptor(tmp_path)
    client = await plugin.connect(account, encryptor, lambda e: asyncio.sleep(0))
    try:
        assert plugin._state_for(account.id).failure is None
    finally:
        await plugin.disconnect(client)


async def test_manager_stops_retrying_on_permanent_failure(tmp_path: Path):
    fake = FakeTelegramApi(error_status={"getMe": 401})
    plugin = _plugin(fake)
    registry.register_for_test("telegram", plugin)
    encryptor = get_encryptor(tmp_path)
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    account = _account(token="bad")
    try:
        mgr.start(account, encryptor)
        listener_task = mgr._listeners[account.id].task
        await asyncio.wait_for(listener_task, timeout=5)
        assert listener_task.done()
        assert plugin._state_for(account.id).failure is not None
    finally:
        await mgr.drain()


async def test_manager_keeps_backing_off_on_ordinary_failure(tmp_path: Path):
    fake = FakeTelegramApi(error_status={"getMe": 500})
    plugin = _plugin(fake)
    registry.register_for_test("telegram", plugin)
    encryptor = get_encryptor(tmp_path)
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    account = _account(account_id="acc-2")
    try:
        mgr.start(account, encryptor)
        await asyncio.sleep(0.2)
        listener_task = mgr._listeners[account.id].task
        assert not listener_task.done()  # still backing off, unlike the permanent case
    finally:
        await mgr.drain()


# ── AC-4: liveness ────────────────────────────────────────────────────────


async def test_is_alive_false_when_task_done():
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    client = TelegramClient(task, None, "acc-1", _AccountState())
    assert client.is_alive() is False


async def test_is_alive_false_when_last_poll_exceeds_window():
    task = asyncio.create_task(asyncio.sleep(10))
    try:
        state = _AccountState(last_poll_at=time.monotonic() - 10_000)
        client = TelegramClient(task, None, "acc-1", state)
        assert client.is_alive() is False
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_is_alive_true_before_first_poll_completes():
    task = asyncio.create_task(asyncio.sleep(10))
    try:
        client = TelegramClient(task, None, "acc-1", _AccountState())
        assert client.is_alive() is True
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ── AC-5: translation ────────────────────────────────────────────────────


def _msg(**overrides):
    base_msg = {
        "chat": {"id": 555, "type": "private"},
        "from": {"id": 1, "first_name": "Dana"},
        "text": "hello",
    }
    base_msg.update(overrides)
    return base_msg


async def test_translate_is_dm_true_for_private_chat():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    envelope = await _translate_message(state, _msg(), "acc-1")
    assert envelope.is_dm is True
    assert envelope.channel_id == "555"  # str(chat.id) keys, even from an int


async def test_translate_is_dm_false_for_group_chat(isolated_db):
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(chat={"id": -1, "type": "group", "title": "Squad"})
    envelope = await _translate_message(state, msg, "acc-1")
    assert envelope.is_dm is False


async def test_translate_mention_via_mention_entity():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(
        text="hey @TestBot",
        entities=[{"type": "mention", "offset": 4, "length": 8}],
    )
    envelope = await _translate_message(state, msg, "acc-1")
    assert envelope.mentions_bot is True


async def test_translate_mention_via_text_mention_entity():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(
        text="hey you",
        entities=[{"type": "text_mention", "offset": 4, "length": 3, "user": {"id": BOT_ID}}],
    )
    envelope = await _translate_message(state, msg, "acc-1")
    assert envelope.mentions_bot is True


async def test_translate_non_matching_mention_not_flagged():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(
        text="hey @OtherBot",
        entities=[{"type": "mention", "offset": 4, "length": 9}],
    )
    envelope = await _translate_message(state, msg, "acc-1")
    assert envelope.mentions_bot is False


async def test_translate_peer_name_first_and_last():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(**{"from": {"id": 1, "first_name": "Dana", "last_name": "G"}})
    envelope = await _translate_message(state, msg, "acc-1")
    assert envelope.peer_name == "Dana G"


async def test_translate_peer_name_first_only():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    envelope = await _translate_message(state, _msg(), "acc-1")
    assert envelope.peer_name == "Dana"


async def test_translate_peer_username_present_and_absent():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    with_username = _msg(**{"from": {"id": 1, "first_name": "Dana", "username": "dana_h"}})
    envelope = await _translate_message(state, with_username, "acc-1")
    assert envelope.peer_username == "dana_h"

    without_username = _msg()
    envelope2 = await _translate_message(state, without_username, "acc-1")
    assert envelope2.peer_username is None


async def test_translate_forum_topic_thread_id(isolated_db):
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(
        chat={"id": -100, "type": "supergroup", "title": "Forum"},
        message_thread_id=42,
    )
    envelope = await _translate_message(state, msg, "acc-1")
    assert envelope.thread_id == "42"


async def test_translate_bot_authored_dropped_unless_allowlisted():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(**{"from": {"id": 9, "is_bot": True, "first_name": "OtherBot"}})
    dropped = await _translate_message(state, msg, "acc-1")
    assert dropped is None

    state.allowlist_peers = frozenset({"9"})
    admitted = await _translate_message(state, msg, "acc-1")
    assert admitted is not None
    assert admitted.peer_id == "9"


async def test_translate_text_less_message_dropped():
    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = {"chat": {"id": 1, "type": "private"}, "from": {"id": 1, "first_name": "X"}}
    assert await _translate_message(state, msg, "acc-1") is None


# ── AC-6: directory channel capture ──────────────────────────────────────


async def test_group_message_upserts_directory_channel_entry(isolated_db):
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorDirectoryRepository

    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(chat={"id": -55, "type": "group", "title": "General"})
    envelope = await _translate_message(state, msg, "acc-1")
    assert envelope is not None

    conn = await get_connection()
    entry = await ConnectorDirectoryRepository(conn).get("acc-1", "channel", "-55")
    assert entry is not None
    assert entry.display_name == "General"
    assert entry.thread_id is None


async def test_group_message_with_thread_stores_thread_shape(isolated_db):
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorDirectoryRepository

    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(chat={"id": -60, "type": "supergroup", "title": "Topics"}, message_thread_id=3)
    await _translate_message(state, msg, "acc-1")

    conn = await get_connection()
    entry = await ConnectorDirectoryRepository(conn).get("acc-1", "channel", "-60")
    assert entry is not None
    assert entry.thread_id == "3"


async def test_repeated_identical_title_upsert_on_change_is_a_noop(isolated_db):
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorDirectoryRepository

    state = _AccountState(bot_id=str(BOT_ID), bot_username=BOT_USERNAME)
    msg = _msg(chat={"id": -70, "type": "group", "title": "Same Name"})
    await _translate_message(state, msg, "acc-1")
    await _translate_message(state, dict(msg, text="second message"), "acc-1")  # same title

    conn = await get_connection()
    entry = await ConnectorDirectoryRepository(conn).get("acc-1", "channel", "-70")
    assert entry is not None
    assert entry.display_name == "Same Name"


# ── AC-7: outbound ────────────────────────────────────────────────────────


def _client_for_send(fake: FakeTelegramApi) -> TelegramClient:
    from the_one.connectors.telegram._api import TelegramApiClient

    api = TelegramApiClient("tok", transport=fake.transport)
    return TelegramClient(asyncio.current_task(), api, "acc-1", _AccountState())


async def test_send_channel_target_with_thread():
    fake = FakeTelegramApi(send_message_result={"message_id": 321})
    client = _client_for_send(fake)
    target = ChannelTarget(connector_id="acc-1", channel_id="c1", thread_id="t1")
    result = await client.send(target, "hi")
    assert result.platform_message_id == "321"
    assert fake.sent_messages[0] == {"chat_id": "c1", "text": "hi", "message_thread_id": "t1"}


async def test_send_channel_target_without_thread():
    fake = FakeTelegramApi()
    client = _client_for_send(fake)
    await client.send(ChannelTarget(connector_id="acc-1", channel_id="c1"), "hi")
    assert "message_thread_id" not in fake.sent_messages[0]


async def test_send_peer_target():
    fake = FakeTelegramApi()
    client = _client_for_send(fake)
    await client.send(PeerTarget(connector_id="acc-1", peer_id="peer-9"), "hi")
    assert fake.sent_messages[0]["chat_id"] == "peer-9"
    assert "message_thread_id" not in fake.sent_messages[0]


# ── AC-8: Protocol conformance ───────────────────────────────────────────


def test_telegram_plugin_satisfies_connector_plugin_protocol():
    assert isinstance(TelegramPlugin(), ConnectorPlugin)


async def test_telegram_client_satisfies_connector_client_and_has_no_history(tmp_path: Path):
    fake = FakeTelegramApi(me={"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    client = await plugin.connect(_account(), encryptor, lambda e: asyncio.sleep(0))
    try:
        assert isinstance(client, ConnectorClient)
        assert isinstance(client, TelegramClient)
        assert client.is_alive() is True
        assert getattr(client, "history", None) is None
    finally:
        await plugin.disconnect(client)


async def test_disconnect_is_idempotent(tmp_path: Path):
    fake = FakeTelegramApi(me={"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    client = await plugin.connect(_account(), encryptor, lambda e: asyncio.sleep(0))
    await plugin.disconnect(client)
    await plugin.disconnect(client)  # must not raise


async def test_doctor_ok_when_poll_connected(tmp_path: Path):
    fake = FakeTelegramApi(me={"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    account = _account()
    client = await plugin.connect(account, encryptor, lambda e: asyncio.sleep(0))
    try:
        report = await plugin.doctor(account, encryptor)
        assert report.status == "ok"
        assert report.details["poll_connected"] is True
    finally:
        await plugin.disconnect(client)


async def test_doctor_degraded_when_api_ok_but_not_connected(tmp_path: Path):
    fake = FakeTelegramApi(me={"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    report = await plugin.doctor(_account(), encryptor)
    assert report.status == "degraded"


async def test_doctor_failed_on_bad_token(tmp_path: Path):
    fake = FakeTelegramApi(error_status={"getMe": 401})
    plugin = _plugin(fake)
    encryptor = get_encryptor(tmp_path)
    report = await plugin.doctor(_account(), encryptor)
    assert report.status == "failed"


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
async def test_lifespan_registers_telegram_unconditionally(_isolated_data_dir):
    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        assert registry.get_plugin("telegram") is not None

    assert registry.get_plugin("telegram") is None


@pytest.mark.usefixtures("reset_lifespan_singletons")
async def test_lifespan_registers_telegram_across_two_cycles(_isolated_data_dir):
    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        assert registry.get_plugin("telegram") is not None
    assert registry.get_plugin("telegram") is None

    async with lifespan(app):
        assert registry.get_plugin("telegram") is not None
    assert registry.get_plugin("telegram") is None
