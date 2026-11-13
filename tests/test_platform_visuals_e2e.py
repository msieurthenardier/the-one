"""End to end: one reply with two charts and a widget through ``deliver_final_reply`` to a
real Discord and a real Telegram client on mock transports, with ``render_png`` real
(M35 F3 L4, AC10)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx

from tests import _multipart
from tests.test_discord_visuals import Script
from tests.test_telegram_visuals import Server
from the_one.connectors import delivery
from the_one.connectors.base import ChannelTarget
from the_one.connectors.discord._rest import RestClient
from the_one.connectors.discord.plugin import DiscordClient
from the_one.connectors.telegram._api import TelegramApiClient
from the_one.connectors.telegram.plugin import TelegramClient, _AccountState
from the_one.llm.base import Message, Role
from the_one.visuals.outbound import WIDGET_NOTE

TARGET = ChannelTarget(connector_id="conn-1", channel_id="chan-1")


def _chart(title: str) -> str:
    spec = {
        "type": "bar",
        "title": title,
        "x": {"values": ["A", "B", "C"]},
        "series": [{"values": [1, 3, 2]}],
    }
    return "```chart\n" + json.dumps(spec) + "\n```\n"


REPLY = (
    "Here you go.\n"
    + _chart("First chart")
    + "Middle text.\n"
    + _chart("Second chart")
    + "```widget\n<p>hi</p>\n```\n"
    + "Done."
)


class _Manager:
    def __init__(self, client):
        self.client = client

    def client_for(self, connector_id):
        return self.client


def _messages() -> list[Message]:
    msgs = [
        Message(role=Role.USER, content="chart please"),
        Message(role=Role.ASSISTANT, content=REPLY),
    ]
    msgs[-1].visibility = "operator"
    return msgs


async def test_discord_gets_one_multipart_message_with_two_files():
    handler = Script([200])
    rest = RestClient(
        "tok", base_url="https://discord.test/api/v10", transport=httpx.MockTransport(handler)
    )
    client = DiscordClient(MagicMock(), rest, MagicMock(), "acc")
    msgs = _messages()
    await delivery.deliver_final_reply(msgs, 1, TARGET, "conn-1", _Manager(client))
    assert len(handler.requests) == 1
    parts = _multipart.parse(handler.requests[0])
    assert set(parts) == {"payload_json", "files[0]", "files[1]"}
    for key in ("files[0]", "files[1]"):
        assert parts[key][1] == "image/png"
        assert parts[key][2].startswith(b"\x89PNG\r\n\x1a\n")
    payload = json.loads(parts["payload_json"][2])
    assert [a["description"] for a in payload["attachments"]] == ["First chart", "Second chart"]
    assert "Here you go." in payload["content"] and WIDGET_NOTE in payload["content"]
    assert "```chart" not in payload["content"]
    assert msgs[-1].visibility is None


async def test_telegram_gets_send_message_then_two_photos():
    server = Server()
    api = TelegramApiClient(
        "tok", base_url="https://tg.test", transport=httpx.MockTransport(server)
    )
    client = TelegramClient(_task=MagicMock(), _api=api, account_id="a", _state=_AccountState())
    msgs = _messages()
    await delivery.deliver_final_reply(msgs, 1, TARGET, "conn-1", _Manager(client))
    assert server.methods() == ["sendMessage", "sendPhoto", "sendPhoto"]
    assert "```chart" not in server.calls[0][1]["text"]
    assert [c[1]["caption"][2] for c in server.calls[1:]] == [b"First chart", b"Second chart"]
    assert msgs[-1].visibility is None
