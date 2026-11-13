"""Telegram ``send_photo`` / ``send_visual`` / ``send_visual_fallback`` and the 429 retry
behind them (M35 F3 L4: AC4-AC9). A purpose-built ``httpx.MockTransport`` handler with a
per-call script; no network."""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from unittest.mock import MagicMock

import httpx
import pytest

from tests import _multipart
from the_one.connectors.base import (
    ChannelTarget,
    ConnectorClientError,
    OutboundImage,
    PeerTarget,
)
from the_one.connectors.telegram import _api as api_mod
from the_one.connectors.telegram import plugin as plugin_mod
from the_one.connectors.telegram._api import (
    TelegramApiClient,
    TelegramApiError,
    TelegramTransportError,
)
from the_one.connectors.telegram.plugin import TelegramClient, TelegramPlugin, _AccountState
from the_one.db.models import Connector
from the_one.encryption import get_encryptor

TOKEN = "SECRET-TOKEN-123"
CHANNEL = ChannelTarget(connector_id="c", channel_id="-100", thread_id="7")
PLAIN_CHANNEL = ChannelTarget(connector_id="c", channel_id="-100")
PNG = b"\x89PNG\r\n\x1a\n" + b"\r\n\x00Z" * 8
SECRET_TITLE = "Quarterly secret title"


def _images(n: int = 2, title: str = SECRET_TITLE) -> list[OutboundImage]:
    return [
        OutboundImage(
            filename=f"chart-{i + 1}.png",
            data=PNG,
            title=title,
            width=10,
            height=10,
            fallback=f"FALLBACK-SOURCE-{i + 1}",
        )
        for i in range(n)
    ]


def _429(retry_after) -> tuple[int, dict]:
    return 429, {"ok": False, "error_code": 429, "parameters": {"retry_after": retry_after}}


class Server:
    """Records every request as ``(method, fields)`` and plays per-method scripts.

    A script entry is a status int, ``(status, body)``, an exception instance, or ``"slow"``
    (sleeps 5 s, for the ``wait_for`` tests). The last entry repeats. ``on_call`` is an
    optional hook run on every request."""

    def __init__(self, *, message=None, photo=None, on_call=None):
        self.scripts = {"sendMessage": message or [200], "sendPhoto": photo or [200]}
        self.on_call = on_call
        self.calls: list[tuple[str, dict]] = []
        self.counts: dict[str, int] = {}
        self.paths: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        method = request.url.path.rsplit("/", 1)[-1]
        self.paths.append(request.url.path)
        if request.headers["content-type"].startswith("multipart/"):
            fields: dict = _multipart.parse(request)
        else:
            fields = json.loads(request.content)
        self.calls.append((method, fields))
        if self.on_call:
            self.on_call(method)
        script = self.scripts.get(method, [200])
        n = self.counts.get(method, 0)
        self.counts[method] = n + 1
        entry = script[min(n, len(script) - 1)]
        if isinstance(entry, Exception):
            raise entry
        if entry == "slow":
            await asyncio.sleep(5)
            entry = 200
        status, body = entry if isinstance(entry, tuple) else (entry, None)
        if body is None:
            if status < 300:
                body = {"ok": True, "result": {"message_id": 100 + len(self.calls)}}
            else:
                body = {"ok": False, "error_code": status, "description": f"fake {status}"}
        return httpx.Response(status, json=body)

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


def _client(server: Server) -> TelegramClient:
    api = TelegramApiClient(
        TOKEN, base_url="https://tg.test", transport=httpx.MockTransport(server)
    )
    return TelegramClient(_task=MagicMock(), _api=api, account_id="a", _state=_AccountState())


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []

    async def fake_sleep(delay):
        recorded.append(delay)

    monkeypatch.setattr("the_one.connectors.telegram._api.asyncio.sleep", fake_sleep)
    return recorded


class Clock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(api_mod, "monotonic", c)
    return c


def _text_of(fields: dict) -> str:
    return fields["text"]


# ── AC4: shapes ─────────────────────────────────────────────────────────


async def test_send_photo_multipart_shape():
    server = Server()
    client = _client(server)
    await client._api.send_photo(
        chat_id="-100", photo=PNG, filename="chart-1.png", caption="Cap", message_thread_id="7"
    )
    assert server.paths == [f"/bot{TOKEN}/sendPhoto"]
    parts = server.calls[0][1]
    assert parts["chat_id"][2] == b"-100"
    assert parts["caption"][2] == b"Cap"
    assert parts["message_thread_id"][2] == b"7"
    assert parts["photo"] == ("chart-1.png", "image/png", PNG)
    assert "parse_mode" not in parts


async def test_send_photo_omits_thread_when_not_given():
    server = Server()
    client = _client(server)
    await client._api.send_photo(chat_id="5", photo=PNG, filename="c.png", caption="")
    assert "message_thread_id" not in server.calls[0][1]


async def test_send_visual_text_then_one_photo_per_image_in_order():
    server = Server()
    client = _client(server)
    result = await client.send_visual(CHANNEL, "hello **there**", _images(2))
    assert server.methods() == ["sendMessage", "sendPhoto", "sendPhoto"]
    text = server.calls[0][1]
    assert text["chat_id"] == "-100" and text["message_thread_id"] == "7"
    assert text["parse_mode"] == "HTML"
    for i, (_, parts) in enumerate(server.calls[1:], start=1):
        assert parts["chat_id"][2] == b"-100"
        assert parts["message_thread_id"][2] == b"7"
        assert parts["photo"][0] == f"chart-{i}.png"
        assert parts["caption"][2] == SECRET_TITLE.encode()
        assert "parse_mode" not in parts
    assert result.platform_message_id == "101"
    assert result.details == {"images_sent": 2, "images_failed": 0}


async def test_send_visual_text_keeps_its_plain_retry_on_rejection():
    server = Server(message=[400, 200])
    client = _client(server)
    await client.send_visual(PeerTarget(connector_id="c", peer_id="42"), "hi", _images(1))
    assert server.methods() == ["sendMessage", "sendMessage", "sendPhoto"]
    assert "parse_mode" not in server.calls[1][1]
    assert server.calls[2][1]["chat_id"][2] == b"42"
    assert "message_thread_id" not in server.calls[2][1]


async def test_caption_is_cut_to_1024_code_points_with_an_ellipsis():
    server = Server()
    client = _client(server)
    await client.send_visual(PLAIN_CHANNEL, "t", _images(1, title="é" * 1500))
    caption = server.calls[1][1]["caption"][2].decode()
    assert len(caption) == 1024
    assert caption == "é" * 1023 + "…"


async def test_send_visual_empty_images_is_a_value_error():
    server = Server()
    with pytest.raises(ValueError):
        await _client(server).send_visual(PLAIN_CHANNEL, "t", [])
    assert server.calls == []


# ── AC5: failures ───────────────────────────────────────────────────────


async def test_5a_text_failure_propagates_and_no_photo_is_attempted():
    server = Server(message=[500])
    with pytest.raises(ConnectorClientError) as info:
        await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(2))
    assert isinstance(info.value, TelegramApiError)
    assert "sendPhoto" not in server.methods()


@pytest.mark.parametrize("status", [400, 413])
async def test_5b_4xx_photo_sends_its_fallback_text_straight_after(status):
    server = Server(photo=[status, 200])  # photo 1 refused, photo 2 accepted
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(2))
    assert server.methods() == ["sendMessage", "sendPhoto", "sendMessage", "sendPhoto"]
    # the fallback is plain source text, straight after the failed photo, same thread-less chat
    assert "FALLBACK-SOURCE-1" in _text_of(server.calls[2][1])
    assert result.details == {"images_sent": 1, "images_failed": 1}


async def test_5b_429_twice_sends_the_fallback(sleeps):
    server = Server(photo=[_429(1), _429(1), 200])
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(2))
    assert server.methods() == [
        "sendMessage",
        "sendPhoto",
        "sendPhoto",
        "sendMessage",
        "sendPhoto",
    ]
    assert "FALLBACK-SOURCE-1" in _text_of(server.calls[3][1])
    assert sleeps == [1.0]
    assert result.details == {"images_sent": 1, "images_failed": 1}


@pytest.mark.parametrize(
    "bad", [500, httpx.ConnectError("boom"), httpx.ReadTimeout("slow")], ids=["500", "conn", "read"]
)
async def test_5c_5xx_or_transport_error_is_skipped_without_fallback_and_5d_rest_continue(bad):
    server = Server(photo=[bad, 200])
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(3))
    assert server.methods() == ["sendMessage", "sendPhoto", "sendPhoto", "sendPhoto"]
    assert result.details == {"images_sent": 2, "images_failed": 1}


async def test_5d_remaining_photos_attempted_after_a_4xx_too():
    server = Server(photo=[400, 200, 200])
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(3))
    assert server.methods().count("sendPhoto") == 3
    assert result.details == {"images_sent": 2, "images_failed": 1}


async def test_5e_failing_fallback_text_is_logged_not_raised(caplog):
    server = Server(photo=[400, 200], message=[200, 500])
    with caplog.at_level(logging.WARNING):
        result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(2))
    assert result.details == {"images_sent": 1, "images_failed": 1}
    assert any("text resend failed" in r.getMessage() for r in caplog.records)


async def test_permanent_401_on_a_photo_is_a_4xx_and_takes_the_fallback():
    server = Server(photo=[401, 200])
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(2))
    assert server.methods() == ["sendMessage", "sendPhoto", "sendMessage", "sendPhoto"]
    assert result.details == {"images_sent": 1, "images_failed": 1}


# ── AC6: the 45 s budget ────────────────────────────────────────────────


async def test_budget_exhaustion_sends_the_unattempted_as_one_joined_text(clock):
    def tick(method):
        if method == "sendPhoto":
            clock.now += 30.0  # each photo "takes" 30 s on the fake clock

    server = Server(on_call=tick)
    imgs = _images(4)
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", imgs)
    # photo 1 (45 s left), photo 2 (15 s left), then 0 left: images 3 and 4 go as one text
    assert server.methods() == ["sendMessage", "sendPhoto", "sendPhoto", "sendMessage"]
    assert _text_of(server.calls[3][1]) == "FALLBACK-SOURCE-3\n\nFALLBACK-SOURCE-4"
    assert result.details == {"images_sent": 2, "images_failed": 2}


async def test_budget_wait_for_ends_a_slow_photo_and_skips_it_as_budget(monkeypatch, caplog):
    monkeypatch.setattr(plugin_mod, "_PHOTO_BUDGET_SECONDS", 0.2)
    server = Server(photo=["slow"])
    with caplog.at_level(logging.WARNING):
        result = await asyncio.wait_for(
            _client(server).send_visual(PLAIN_CHANNEL, "t", _images(3)), timeout=3
        )
    # photo 1 timed out (maybe posted: no fallback); 2 and 3 were never attempted: one text
    assert server.methods() == ["sendMessage", "sendPhoto", "sendMessage"]
    assert _text_of(server.calls[2][1]) == "FALLBACK-SOURCE-2\n\nFALLBACK-SOURCE-3"
    assert result.details == {"images_sent": 0, "images_failed": 3}
    assert any("budget" in r.getMessage() for r in caplog.records)


async def test_429_with_retry_after_over_the_remaining_budget_gives_up_at_once(
    monkeypatch, clock, sleeps
):
    monkeypatch.setattr(plugin_mod, "_PHOTO_BUDGET_SECONDS", 3.0)
    server = Server(photo=[_429(7), 200])
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(2))
    assert sleeps == []  # no sleep: 7 >= 3 remaining
    assert server.methods() == ["sendMessage", "sendPhoto", "sendMessage", "sendPhoto"]
    assert "FALLBACK-SOURCE-1" in _text_of(server.calls[2][1])
    assert result.details == {"images_sent": 1, "images_failed": 1}


async def test_429_with_room_sleeps_ten_then_retries_once(clock, sleeps):
    server = Server(photo=[_429(30), 200])
    result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(1))
    assert sleeps == [10.0]
    assert server.methods() == ["sendMessage", "sendPhoto", "sendPhoto"]
    assert result.details == {"images_sent": 1, "images_failed": 0}


async def test_each_photo_request_timeout_is_capped_to_the_remaining_time(monkeypatch, clock):
    seen: list[float] = []
    server = Server()
    client = _client(server)
    original = client._api._client.post

    async def spy(path, **kwargs):
        seen.append(kwargs["timeout"])
        return await original(path, **kwargs)

    monkeypatch.setattr(client._api._client, "post", spy)
    monkeypatch.setattr(plugin_mod, "_PHOTO_BUDGET_SECONDS", 4.0)
    await client.send_visual(PLAIN_CHANNEL, "t", _images(1))
    assert seen[0] == 15.0  # the text request keeps its ordinary timeout
    assert seen[1] == 4.0  # min(15, remaining)


# ── AC7: retry factoring ────────────────────────────────────────────────


async def test_send_photo_clamps_retry_after_to_ten_and_warns(sleeps, caplog):
    server = Server(photo=[_429(99999), 200])
    client = _client(server)
    with caplog.at_level(logging.WARNING):
        await client._api.send_photo(chat_id="1", photo=PNG, filename="c.png", caption="")
    assert sleeps == [10.0]
    assert any("clamped" in r.getMessage() for r in caplog.records)


async def test_send_message_keeps_its_sixty_second_clamp(sleeps):
    server = Server(message=[_429(99999), 200])
    await _client(server)._api.send_message(chat_id="1", text="x")
    assert sleeps == [60.0]


async def test_fallback_text_path_clamps_at_ten(sleeps):
    server = Server(message=[_429(99999), 200])
    await _client(server).send_visual_fallback(PLAIN_CHANNEL, "plain")
    assert sleeps == [10.0]


async def test_one_function_implements_the_retry_for_both_callers(monkeypatch):
    names: list[str] = []
    original = TelegramApiClient._post_with_429_retry

    async def spy(self, method, **kwargs):
        names.append(method)
        return await original(self, method, **kwargs)

    monkeypatch.setattr(TelegramApiClient, "_post_with_429_retry", spy)
    client = _client(Server())
    await client._api.send_message(chat_id="1", text="x")
    await client._api.send_photo(chat_id="1", photo=PNG, filename="c.png", caption="")
    assert names == ["sendMessage", "sendPhoto"]


# ── AC8: transport mapping and token safety ─────────────────────────────


def _leaky_connect_error() -> httpx.ConnectError:
    return httpx.ConnectError(f"cannot reach https://tg.test/bot{TOKEN}/sendMessage")


def test_transport_error_is_a_sibling_not_an_api_error():
    assert issubclass(TelegramTransportError, ConnectorClientError)
    assert not issubclass(TelegramTransportError, TelegramApiError)


async def test_send_does_not_run_the_plain_retry_after_a_transport_error():
    server = Server(message=[_leaky_connect_error(), 200])
    with pytest.raises(TelegramTransportError):
        await _client(server).send(PLAIN_CHANNEL, "hello")
    assert server.methods() == ["sendMessage"]  # one request only


def _assert_token_absent(caplog) -> None:
    # The app's own records only: httpx's INFO request log names the URL (token included)
    # on a successful request, which predates this leg and is not ours to change here.
    for record in caplog.records:
        if record.name.startswith("the_one"):
            text = record.getMessage() + (record.exc_text or "")
            if record.exc_info:
                text += "".join(traceback.format_exception(*record.exc_info))
            assert TOKEN not in text


async def test_transport_error_carries_no_cause_and_no_token():
    server = Server(message=[_leaky_connect_error()])
    with pytest.raises(TelegramTransportError) as info:
        await _client(server)._api.send_message(chat_id="1", text="x")
    exc = info.value
    assert exc.__cause__ is None and exc.__suppress_context__
    assert TOKEN not in "".join(traceback.format_exception(exc))


async def test_token_is_absent_from_logs_after_a_transport_error_on_send(caplog):
    server = Server(message=[_leaky_connect_error()])
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(TelegramTransportError):
            await _client(server).send(PLAIN_CHANNEL, "hello")
    _assert_token_absent(caplog)


async def test_token_is_absent_from_logs_after_a_transport_error_on_send_visual(caplog):
    server = Server(photo=[_leaky_connect_error()])
    with caplog.at_level(logging.DEBUG):
        result = await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(1))
    assert result.details == {"images_sent": 0, "images_failed": 1}
    _assert_token_absent(caplog)
    assert "transport" in caplog.text


async def test_doctor_reports_failed_on_a_transport_error(tmp_path):
    server = Server()
    server.scripts["getMe"] = [httpx.ConnectError("boom")]
    plugin = TelegramPlugin(api_transport=httpx.MockTransport(server))
    account = Connector(id="a", name="t", type="telegram", secrets={"token": TOKEN}, config={})
    report = await plugin.doctor(account, get_encryptor(tmp_path))
    assert report.status == "failed"
    assert "API check failed" in report.message


# ── AC9: logging ────────────────────────────────────────────────────────


async def test_logs_never_carry_title_caption_fallback_or_bytes(caplog):
    server = Server(photo=[400, 500, 200], message=[200, 200])
    with caplog.at_level(logging.DEBUG):
        await _client(server).send_visual(PLAIN_CHANNEL, "t", _images(3))
    assert caplog.records
    for record in caplog.records:
        text = record.getMessage()
        assert SECRET_TITLE not in text
        assert "FALLBACK-SOURCE" not in text
        assert "PNG" not in text
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "-100" in messages and "400" in messages and "500" in messages
