"""Tests for ``the_one.connectors.telegram._api`` -- the Bot API client's
own request/error-mapping layer, independent of the plugin/poll loop.
Mission 23 Flight 4 Leg 2. Fixture-only networking (``httpx.MockTransport``
via ``tests._telegram_api_fixture``), never a real host.
"""

from __future__ import annotations

import pytest

from tests._telegram_api_fixture import FakeTelegramApi
from the_one.connectors.base import ConnectorClientError, PermanentConnectorFailure
from the_one.connectors.telegram._api import TelegramApiClient, TelegramApiError


def _client(fake: FakeTelegramApi) -> TelegramApiClient:
    return TelegramApiClient("tok", transport=fake.transport)


async def test_get_me_happy_path():
    fake = FakeTelegramApi(me={"id": 42, "is_bot": True, "username": "MyBot"})
    client = _client(fake)
    try:
        me = await client.get_me()
        assert me == {"id": 42, "is_bot": True, "username": "MyBot"}
        assert fake.calls[0][0] == "getMe"
    finally:
        await client.aclose()


async def test_get_updates_sends_offset_timeout_allowed_updates():
    fake = FakeTelegramApi(updates=[{"update_id": 5, "message": {"text": "hi"}}])
    client = _client(fake)
    try:
        result = await client.get_updates(offset=5, timeout=50)
        assert result == [{"update_id": 5, "message": {"text": "hi"}}]
        method, payload = fake.calls[0]
        assert method == "getUpdates"
        assert payload == {"timeout": 50, "allowed_updates": ["message"], "offset": 5}
    finally:
        await client.aclose()


async def test_get_updates_omits_offset_when_none():
    fake = FakeTelegramApi()
    client = _client(fake)
    try:
        await client.get_updates(offset=None, timeout=50)
        _, payload = fake.calls[0]
        assert "offset" not in payload
    finally:
        await client.aclose()


async def test_send_message_shape_channel_and_thread():
    fake = FakeTelegramApi(send_message_result={"message_id": 777})
    client = _client(fake)
    try:
        result = await client.send_message(chat_id="chan-1", text="hey", message_thread_id="t1")
        assert result == {"message_id": 777}
        assert fake.sent_messages[0] == {
            "chat_id": "chan-1",
            "text": "hey",
            "message_thread_id": "t1",
        }
    finally:
        await client.aclose()


async def test_send_message_shape_peer_no_thread():
    fake = FakeTelegramApi()
    client = _client(fake)
    try:
        await client.send_message(chat_id="peer-1", text="hey")
        assert fake.sent_messages[0] == {"chat_id": "peer-1", "text": "hey"}
        assert "message_thread_id" not in fake.sent_messages[0]
    finally:
        await client.aclose()


@pytest.mark.parametrize("status", [401, 404, 409])
async def test_permanent_statuses_raise_permanent_connector_failure(status):
    fake = FakeTelegramApi(error_status={"getMe": status})
    client = _client(fake)
    try:
        with pytest.raises(PermanentConnectorFailure):
            await client.get_me()
    finally:
        await client.aclose()


async def test_ordinary_error_status_raises_telegram_api_error_not_permanent():
    fake = FakeTelegramApi(error_status={"getMe": 500})
    client = _client(fake)
    try:
        with pytest.raises(TelegramApiError) as exc_info:
            await client.get_me()
        assert not isinstance(exc_info.value, PermanentConnectorFailure)
        assert isinstance(exc_info.value, ConnectorClientError)
    finally:
        await client.aclose()


async def test_send_message_parse_mode_included_when_set():
    fake = FakeTelegramApi()
    client = _client(fake)
    try:
        await client.send_message(chat_id="c1", text="hey", parse_mode="HTML")
        assert fake.sent_messages[0] == {"chat_id": "c1", "text": "hey", "parse_mode": "HTML"}
    finally:
        await client.aclose()


async def test_send_message_429_retries_once_then_succeeds():
    fake = FakeTelegramApi(error_status={"sendMessage": 429})
    client = _client(fake)
    try:
        result = await client.send_message(chat_id="c1", text="hi")
        assert result == {"message_id": 999}
        # First call hit the scripted 429; the retry succeeded.
        assert len([c for c in fake.calls if c[0] == "sendMessage"]) == 2
    finally:
        await client.aclose()
