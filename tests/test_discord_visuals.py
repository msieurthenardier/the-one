"""Discord ``send_visual`` / ``send_visual_fallback`` and the REST policy behind them
(M35 F3 L4: AC1, AC2, AC3, AC8, AC9). All on ``httpx.MockTransport``; no network."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import httpx
import pytest

from tests import _multipart
from the_one.connectors.base import (
    ChannelTarget,
    ConnectorClientError,
    OutboundImage,
    PeerTarget,
    VisualUploadError,
)
from the_one.connectors.discord._rest import DiscordRestError, DiscordTransportError, RestClient
from the_one.connectors.discord.plugin import DiscordClient, DiscordPlugin
from the_one.db.models import Connector
from the_one.encryption import get_encryptor

_BASE = "https://discord.test/api/v10"
CHANNEL = ChannelTarget(connector_id="c", channel_id="chan-1")
PNG_A = b"\x89PNG\r\n\x1a\n" + b"\r\n\x00A" * 10
PNG_B = b"\x89PNG\r\n\x1a\n" + b"B\r\n" * 10
SECRET_TITLE = "Quarterly secret title"
SECRET_FALLBACK = '```chart\n{"secret": "fallback source"}\n```'


def _images(n: int = 2, title: str = SECRET_TITLE) -> list[OutboundImage]:
    datas = [PNG_A, PNG_B, PNG_A]
    return [
        OutboundImage(
            filename=f"chart-{i + 1}.png",
            data=datas[i],
            title=title,
            width=10,
            height=10,
            fallback=SECRET_FALLBACK,
        )
        for i in range(n)
    ]


class Script:
    """A MockTransport handler that records requests and plays a per-call script.

    Each script entry is a status int, ``(status, json_body)``, or an exception instance."""

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        entry = self.script[min(len(self.requests) - 1, len(self.script) - 1)]
        if isinstance(entry, Exception):
            raise entry
        status, body = entry if isinstance(entry, tuple) else (entry, None)
        if body is None:
            body = {"id": "m-1"} if status < 300 else {"message": f"fake {status}"}
        return httpx.Response(status, json=body)


def _client(script) -> tuple[DiscordClient, Script]:
    handler = Script(script)
    rest = RestClient("tok", base_url=_BASE, transport=httpx.MockTransport(handler))
    return DiscordClient(MagicMock(), rest, MagicMock(), "acc"), handler


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []

    async def fake_sleep(delay):
        recorded.append(delay)

    monkeypatch.setattr("the_one.connectors.discord._rest.asyncio.sleep", fake_sleep)
    return recorded


async def test_send_visual_one_multipart_message_with_every_file():
    client, h = _client([200])
    result = await client.send_visual(CHANNEL, "the text", _images(2))
    assert len(h.requests) == 1
    req = h.requests[0]
    assert req.method == "POST" and req.url.path == "/api/v10/channels/chan-1/messages"
    assert req.headers["content-type"].startswith("multipart/form-data")
    parts = _multipart.parse(req)
    assert set(parts) == {"payload_json", "files[0]", "files[1]"}
    name, ctype, raw = parts["payload_json"]
    assert ctype is not None and ctype.startswith("application/json")
    assert json.loads(raw) == {
        "content": "the text",
        "attachments": [
            {"id": 0, "filename": "chart-1.png", "description": SECRET_TITLE},
            {"id": 1, "filename": "chart-2.png", "description": SECRET_TITLE},
        ],
    }
    assert parts["files[0]"] == ("chart-1.png", "image/png", PNG_A)
    assert parts["files[1]"] == ("chart-2.png", "image/png", PNG_B)
    assert result.platform_message_id == "m-1"
    assert result.details == {"images_sent": 2, "images_failed": 0}


async def test_send_visual_description_is_cut_to_1024():
    client, h = _client([200])
    await client.send_visual(CHANNEL, "t", _images(1, title="x" * 1500))
    payload = json.loads(_multipart.parse(h.requests[0])["payload_json"][2])
    assert payload["attachments"][0]["description"] == "x" * 1024


async def test_send_visual_peer_target_resolves_through_create_dm():
    client, h = _client([(200, {"id": "dm-9"}), (200, {"id": "m-7"})])
    result = await client.send_visual(PeerTarget(connector_id="c", peer_id="u1"), "t", _images(1))
    assert [r.url.path for r in h.requests] == [
        "/api/v10/users/@me/channels",
        "/api/v10/channels/dm-9/messages",
    ]
    assert h.requests[1].headers["content-type"].startswith("multipart/form-data")
    assert result.platform_message_id == "m-7"


async def test_send_visual_empty_images_is_a_value_error():
    client, h = _client([200])
    with pytest.raises(ValueError):
        await client.send_visual(CHANNEL, "t", [])
    assert h.requests == []


async def test_retried_429_post_carries_identical_parts(sleeps):
    client, h = _client([(429, {"retry_after": 2.0}), 200])
    result = await client.send_visual(CHANNEL, "t", _images(2))
    assert len(h.requests) == 2
    assert _multipart.parse(h.requests[0]) == _multipart.parse(h.requests[1])
    assert sleeps == [2.0]
    assert result.details["images_sent"] == 2


@pytest.mark.parametrize("status", [400, 413])
async def test_4xx_raises_visual_upload_error(status, caplog):
    client, h = _client([status])
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VisualUploadError) as info:
            await client.send_visual(CHANNEL, "t", _images(2))
    assert str(status) in str(info.value)
    assert info.value.status == status
    assert len(h.requests) == 1
    _no_payload_in_logs(caplog)


async def test_413_through_send_reply_logs_exactly_one_fallback_warning(caplog):
    from the_one.connectors import delivery

    title = "Quarterly secret chart title"
    chart_json = json.dumps(
        {
            "type": "bar",
            "title": title,
            "x": {"values": ["a", "b"]},
            "series": [{"values": [1, 2]}],
        }
    )
    client, h = _client([(413, {"message": "RESPONSE-BODY-SECRET"}), 200])
    with caplog.at_level(logging.DEBUG):
        await delivery.send_reply(
            client, CHANNEL, f"hi\n```chart\n{chart_json}\n```\n", connector_id="disc1"
        )
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    fallback = [r for r in warns if "falling back" in r.getMessage()]
    assert len(fallback) == 1 and len(warns) == 1
    msg = fallback[0].getMessage()
    assert "[0]" in msg and "413" in msg and "disc1" in msg and "falling back to text" in msg
    for text in (title, chart_json, "RESPONSE-BODY-SECRET"):
        assert text not in caplog.text


async def test_413_then_failed_resend_logs_no_upload_response_body(caplog):
    """The resend failure's logged traceback must not chain the 413 response body."""
    from the_one.connectors import delivery
    from the_one.llm.base import Message, Role

    chart_json = json.dumps(
        {"type": "bar", "x": {"values": ["a", "b"]}, "series": [{"values": [1, 2]}]}
    )
    client, _h = _client([(413, {"message": "UPLOAD-BODY-SECRET"}), (500, {"message": "x"})])

    class _Manager:
        def client_for(self, connector_id):
            return client

    msgs = [
        Message(role=Role.USER, content="hi"),
        Message(role=Role.ASSISTANT, content=f"hi\n```chart\n{chart_json}\n```\n"),
    ]
    with caplog.at_level(logging.DEBUG):
        await delivery.deliver_final_reply(msgs, 1, CHANNEL, "disc1", _Manager())
    assert any(r.exc_info for r in caplog.records)  # the resend failure was logged
    for record in caplog.records:
        assert "UPLOAD-BODY-SECRET" not in record.getMessage()
    assert "UPLOAD-BODY-SECRET" not in caplog.text


async def test_429_after_one_clamped_retry_raises_visual_upload_error(sleeps):
    client, h = _client([(429, {"retry_after": 30.0})])
    with pytest.raises(VisualUploadError) as info:
        await client.send_visual(CHANNEL, "t", _images(1))
    assert "-> 429 (rate limited)" in str(info.value)
    assert info.value.status == 429
    assert len(h.requests) == 2  # one retry only
    assert sleeps == [10.0]  # retry_after 30 clamped to 10


async def test_5xx_raises_rest_error_without_resend():
    client, h = _client([500])
    with pytest.raises(DiscordRestError) as info:
        await client.send_visual(CHANNEL, "t", _images(1))
    assert not isinstance(info.value, VisualUploadError)
    assert info.value.status == 500
    assert len(h.requests) == 1


@pytest.mark.parametrize(
    "exc", [httpx.ConnectError("boom"), httpx.ReadTimeout("slow")], ids=["connect", "timeout"]
)
async def test_transport_error_raises_transport_error_without_resend(exc):
    client, h = _client([exc])
    with pytest.raises(DiscordTransportError) as info:
        await client.send_visual(CHANNEL, "t", _images(1))
    assert isinstance(info.value, ConnectorClientError)
    assert not isinstance(info.value, (DiscordRestError, VisualUploadError))
    assert len(h.requests) == 1


async def test_transport_error_does_not_chain_the_httpx_cause():
    client, _ = _client([httpx.ConnectError("boom")])
    with pytest.raises(DiscordTransportError) as info:
        await client.send_visual(CHANNEL, "t", _images(1))
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


async def test_create_dm_failure_propagates_unchanged():
    client, h = _client([(403, {"message": "no dm"})])
    with pytest.raises(DiscordRestError) as info:
        await client.send_visual(PeerTarget(connector_id="c", peer_id="u1"), "t", _images(1))
    assert not isinstance(info.value, VisualUploadError)
    assert len(h.requests) == 1  # no multipart attempted


# ── AC3: retry policy ───────────────────────────────────────────────────


async def test_create_message_unclamped_keeps_three_retries_and_raw_retry_after(sleeps):
    handler = Script([(429, {"retry_after": 30.0})])
    rest = RestClient("tok", base_url=_BASE, transport=httpx.MockTransport(handler))
    with pytest.raises(DiscordRestError) as info:
        await rest.create_message("c1", "hi")
    assert info.value.status == 429
    assert len(handler.requests) == 4
    assert sleeps == [30.0, 30.0, 30.0]


async def test_fallback_post_is_clamped_to_one_retry_and_ten_seconds(sleeps):
    client, h = _client([(429, {"retry_after": 30.0}), 200])
    result = await client.send_visual_fallback(CHANNEL, "plain text")
    assert len(h.requests) == 2
    assert sleeps == [10.0]
    assert json.loads(h.requests[1].content) == {"content": "plain text"}
    assert result.platform_message_id == "m-1"


async def test_fallback_gives_up_after_one_retry(sleeps):
    client, h = _client([(429, {"retry_after": 1.0})])
    with pytest.raises(DiscordRestError):
        await client.send_visual_fallback(CHANNEL, "plain text")
    assert len(h.requests) == 2


async def test_global_429_is_recorded_on_the_multipart_and_fallback_paths(sleeps):
    for send in ("visual", "fallback"):
        client, h = _client([(429, {"retry_after": 30.0, "global": True}), 200])
        before = client._rest._limiter._global_reset_at
        if send == "visual":
            await client.send_visual(CHANNEL, "t", _images(1))
        else:
            await client.send_visual_fallback(CHANNEL, "t")
        assert client._rest._limiter._global_reset_at > before


# ── AC8 / AC9 ───────────────────────────────────────────────────────────


async def test_rest_transport_error_is_not_a_rest_error_on_any_call():
    handler = Script([httpx.ConnectError("boom")])
    rest = RestClient("tok", base_url=_BASE, transport=httpx.MockTransport(handler))
    with pytest.raises(DiscordTransportError):
        await rest.get_current_user()


async def test_doctor_reports_failed_on_a_transport_error(tmp_path):
    handler = Script([httpx.ConnectError("boom")])
    plugin = DiscordPlugin(rest_transport=httpx.MockTransport(handler))
    account = Connector(id="a", name="d", type="discord", secrets={"token": "tok"}, config={})
    report = await plugin.doctor(account, get_encryptor(tmp_path))
    assert report.status == "failed"
    assert "REST check failed" in report.message


def _no_payload_in_logs(caplog) -> None:
    for record in caplog.records:
        text = record.getMessage()
        assert SECRET_TITLE not in text
        assert "fallback source" not in text
        assert "PNG" not in text
