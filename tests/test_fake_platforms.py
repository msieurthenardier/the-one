"""scripts/fake_platforms.py (M35 F3 L5): the real Discord and Telegram plugins run in-process
against the fake, and the fake's records, failures, save dir and privacy rules are proved."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import httpx
import pytest

from the_one.connectors import registry
from the_one.connectors.base import OutboundImage, PeerTarget, VisualUploadError
from the_one.connectors.discord.plugin import DiscordPlugin
from the_one.connectors.telegram.plugin import TelegramPlugin
from the_one.db.models import Connector
from the_one.encryption import get_encryptor
from the_one.visuals import chart_image
from the_one.visuals.chart_spec import parse_chart

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fake_platforms.py"
TOKEN = "123456:SECRET-TOKEN-ABC"
_spec = importlib.util.spec_from_file_location("fake_platforms", SCRIPT)
fake_platforms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_platforms)


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.clear_for_test()
    yield
    registry.clear_for_test()


class Running:
    def __init__(self, base: str, app, http: httpx.AsyncClient) -> None:
        self.base = base
        self.state = app.state.fake
        self.http = http

    async def received(self) -> list[dict]:
        return (await self.http.get("/_control/received")).json()["records"]

    async def post(self, path: str, body: dict) -> httpx.Response:
        return await self.http.post(path, json=body)

    async def fail_next(self, count=1, status=413, kind="upload") -> None:
        r = await self.post("/_control/fail-next", {"count": count, "status": status, "kind": kind})
        assert r.status_code == 200


async def _start(save_dir=None, heartbeat_ms=30000):
    import uvicorn

    app = fake_platforms.create_app(save_dir, heartbeat_ms)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=0, log_level="warning", timeout_graceful_shutdown=1
        )
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    http = httpx.AsyncClient(base_url=base, timeout=10)
    return Running(base, app, http), server, task


@pytest.fixture
async def fake():
    running, server, task = await _start()
    try:
        yield running
    finally:
        await running.http.aclose()
        server.should_exit = True
        await asyncio.wait_for(task, 10)


def _images(n: int = 2) -> list[OutboundImage]:
    out = []
    for i in range(n):
        spec = parse_chart(
            json.dumps(
                {
                    "type": "bar",
                    "title": f"Chart {i + 1}",
                    "x": {"values": ["A", "B", "C"]},
                    "series": [{"values": [1 + i, 3, 2]}],
                }
            )
        )
        rendered = chart_image.render_png(spec)
        out.append(
            OutboundImage(
                filename=f"chart-{i + 1}.png",
                data=rendered.data,
                title=f"Chart {i + 1}",
                width=rendered.width,
                height=rendered.height,
                fallback=f"```chart\nsource {i + 1}\n```",
            )
        )
    return out


def _discord_account() -> Connector:
    return Connector(id="d-1", name="D", type="discord", secrets={"token": "dtok"})


def _telegram_account() -> Connector:
    return Connector(id="t-1", name="T", type="telegram", secrets={"token": TOKEN})


@contextlib.asynccontextmanager
async def discord_client(fake: Running, tmp_path: Path):
    inbound: list = []

    async def on_inbound(env):
        inbound.append(env)

    plugin = DiscordPlugin(
        rest_base_url=f"{fake.base}/discord/api/v10",
        gateway_url=f"ws://{fake.base.removeprefix('http://')}/discord/gateway",
    )
    client = await asyncio.wait_for(
        plugin.connect(_discord_account(), get_encryptor(tmp_path), on_inbound), 10
    )
    try:
        yield client, inbound
    finally:
        await plugin.disconnect(client)


@contextlib.asynccontextmanager
async def telegram_client(fake: Running, tmp_path: Path):
    inbound: list = []

    async def on_inbound(env):
        inbound.append(env)

    plugin = TelegramPlugin(base_url=f"{fake.base}/telegram")
    client = await asyncio.wait_for(
        plugin.connect(_telegram_account(), get_encryptor(tmp_path), on_inbound), 10
    )
    try:
        yield client, inbound
    finally:
        await plugin.disconnect(client)


async def _until(predicate, timeout=5.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


# ── AC1: Discord round trip ─────────────────────────────────────────────


async def test_discord_round_trip(fake, tmp_path):
    async with discord_client(fake, tmp_path) as (client, inbound):
        r = await fake.post(
            "/_control/discord/inject",
            {"author_id": "42", "author_name": "Ann", "content": "hello bot"},
        )
        assert r.status_code == 200
        await _until(lambda: inbound)
        env = inbound[0]
        assert env.is_dm is True and env.peer_id == "42" and env.text == "hello bot"
        await client.send(PeerTarget(connector_id="d-1", peer_id="42"), "hi back")
    recs = [r for r in await fake.received() if r["platform"] == "discord"]
    sent = [r for r in recs if r["json"] and r["json"].get("content") == "hi back"]
    assert len(sent) == 1
    assert sent[0]["method"].startswith("POST /channels/")
    assert sent[0]["method"].endswith("/messages")


async def test_discord_inject_without_a_client_is_409(fake):
    r = await fake.post("/_control/discord/inject", {"author_id": "1", "content": "x"})
    assert r.status_code == 409 and r.json() == {"error": "no gateway client"}


# ── AC2: Discord multipart ──────────────────────────────────────────────


async def test_discord_multipart_records_two_files(fake, tmp_path):
    images = _images(2)
    target = PeerTarget(connector_id="d-1", peer_id="42")
    async with discord_client(fake, tmp_path) as (client, _inbound):
        await client.send_visual(target, "see charts", images)
    (rec,) = [r for r in await fake.received() if r["files"]]
    payload = json.loads(rec["fields"]["payload_json"])
    assert payload["content"] == "see charts"
    assert [a["description"] for a in payload["attachments"]] == ["Chart 1", "Chart 2"]
    assert [a["filename"] for a in payload["attachments"]] == ["chart-1.png", "chart-2.png"]
    assert [f["name"] for f in rec["files"]] == ["files[0]", "files[1]"]
    for f, img in zip(rec["files"], images, strict=True):
        assert f["content_type"] == "image/png"
        assert f["size"] == len(img.data)
        assert f["sha256"] == hashlib.sha256(img.data).hexdigest()
        assert f["png"] == {"width": img.width, "height": img.height}
    assert "payload_json" not in [f["name"] for f in rec["files"]]


# ── AC3: Discord heartbeat ──────────────────────────────────────────────


async def test_discord_stays_connected_through_heartbeats(tmp_path):
    running, server, task = await _start(heartbeat_ms=100)
    try:
        async with discord_client(running, tmp_path) as (client, _inbound):
            sock = running.state.sockets[0]
            await asyncio.sleep(0.9)  # at least 5 intervals with jitter
            assert client.is_alive()
            assert running.state.sockets == [sock]
    finally:
        await running.http.aclose()
        server.should_exit = True
        await asyncio.wait_for(task, 10)


async def test_resume_gets_invalid_session(fake):
    from websockets.asyncio.client import connect

    async with connect(f"ws://{fake.base.removeprefix('http://')}/discord/gateway/") as ws:
        assert json.loads(await ws.recv())["op"] == 10
        await ws.send(json.dumps({"op": 6, "d": {}}))
        assert json.loads(await ws.recv()) == {"op": 9, "d": False}


# ── AC4: Telegram round trip ────────────────────────────────────────────


async def test_telegram_round_trip_and_no_redelivery(fake, tmp_path):
    images = _images(2)
    async with telegram_client(fake, tmp_path) as (client, inbound):
        await asyncio.sleep(0.2)  # the next poll is now held
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        r = await fake.post(
            "/_control/telegram/inject", {"from_id": 77, "text": "ping", "first_name": "Bo"}
        )
        update_id = r.json()["update_id"]
        await _until(lambda: inbound, timeout=2)
        assert loop.time() - t0 < 2
        assert inbound[0].peer_id == "77" and inbound[0].is_dm and inbound[0].text == "ping"
        await asyncio.sleep(0.5)  # the offset advanced: never redelivered
        assert len(inbound) == 1
        r = await fake.http.post(
            "/telegram/bot1:x/getUpdates", json={"offset": update_id + 1, "timeout": 0}
        )
        assert r.json()["result"] == []
        r = await fake.http.post(
            "/telegram/bot1:x/getUpdates", json={"offset": update_id, "timeout": 0}
        )
        assert len(r.json()["result"]) == 1  # not deleted, as the real API
        await client.send_visual(PeerTarget(connector_id="t-1", peer_id="77"), "look", images)
    recs = await fake.received()
    assert [r["method"] for r in recs] == ["sendMessage", "sendPhoto", "sendPhoto"]
    assert recs[0]["json"]["chat_id"] == "77"
    for rec, img in zip(recs[1:], images, strict=True):
        assert rec["fields"]["chat_id"] == "77"
        assert rec["fields"]["caption"]
        (f,) = rec["files"]
        assert f["name"] == "photo" and f["png"] == {"width": img.width, "height": img.height}
        assert f["sha256"] == hashlib.sha256(img.data).hexdigest()


# ── AC5: fail-next ──────────────────────────────────────────────────────


async def test_fail_next_upload_discord(fake, tmp_path):
    target = PeerTarget(connector_id="d-1", peer_id="42")
    async with discord_client(fake, tmp_path) as (client, _inbound):
        await fake.fail_next(count=1, status=413, kind="upload")
        # a JSON send is not an upload: it is not failed and does not consume the failure
        await client.send(target, "plain")
        with pytest.raises(VisualUploadError):
            await client.send_visual(target, "charts", _images(1))
        await client.send(target, "after")
    recs = [r for r in await fake.received() if r["platform"] == "discord"]
    by = [(bool(r["files"]), r["status"]) for r in recs]
    assert by == [(False, 200), (True, 413), (False, 200)]


async def test_fail_next_500_discord_is_not_retried(fake, tmp_path):
    async with discord_client(fake, tmp_path) as (client, _inbound):
        await fake.fail_next(count=1, status=500, kind="upload")
        with pytest.raises(Exception) as info:
            await client.send_visual(PeerTarget(connector_id="d-1", peer_id="42"), "c", _images(1))
        assert not isinstance(info.value, VisualUploadError)
    posts = [r for r in await fake.received() if r["files"]]
    assert len(posts) == 1


async def test_fail_next_upload_telegram_falls_back_to_text(fake, tmp_path):
    images = _images(1)
    async with telegram_client(fake, tmp_path) as (client, _inbound):
        await fake.fail_next(count=1, status=413, kind="upload")
        await client.send_visual(PeerTarget(connector_id="t-1", peer_id="77"), "look", images)
    recs = await fake.received()
    assert [(r["method"], r["status"]) for r in recs] == [
        ("sendMessage", 200),
        ("sendPhoto", 413),
        ("sendMessage", 200),
    ]
    assert images[0].fallback.split("\n")[1] in json.dumps(recs[2]["json"])


async def test_fail_next_any_fails_json_and_429_carries_retry_after(fake):
    await fake.fail_next(count=1, status=429, kind="any")
    r = await fake.http.post(
        "/discord/api/v10/channels/9/messages", json={"content": "x"}, headers={}
    )
    assert r.status_code == 429 and r.json()["retry_after"] == 1
    await fake.fail_next(count=1, status=429, kind="any")
    r = await fake.http.post("/telegram/bot1:x/sendMessage", json={"chat_id": "1", "text": "x"})
    assert r.status_code == 429 and r.json()["parameters"] == {"retry_after": 1}
    r = await fake.http.post("/telegram/bot1:x/sendMessage", json={"chat_id": "1", "text": "x"})
    assert r.status_code == 200


async def test_unknown_telegram_method_is_404(fake):
    r = await fake.http.post("/telegram/bot1:x/nope", json={})
    assert r.status_code == 404 and r.json()["ok"] is False


# ── AC6: save dir and privacy ───────────────────────────────────────────


async def test_save_dir_writes_the_bytes_and_received_has_none(tmp_path):
    save = tmp_path / "saved"
    running, server, task = await _start(save_dir=save)
    try:
        images = _images(2)
        async with discord_client(running, tmp_path) as (client, _i):
            await client.send_visual(PeerTarget(connector_id="d-1", peer_id="42"), "c", images)
        async with telegram_client(running, tmp_path) as (tclient, _ti):
            await tclient.send_visual(PeerTarget(connector_id="t-1", peer_id="7"), "c", images[:1])
        recs = await running.received()
        discord_rec = next(r for r in recs if r["platform"] == "discord" and r["files"])
        for f, img in zip(discord_rec["files"], images, strict=True):
            name = f"{discord_rec['seq']:04d}-files_{f['name'][6]}_-{f['filename']}"
            assert (save / name).read_bytes() == img.data
        photo = next(r for r in recs if r["method"] == "sendPhoto")
        saved = save / f"{photo['seq']:04d}-photo-chart-1.png"
        assert saved.read_bytes() == images[0].data
        blob = json.dumps(recs)
        assert TOKEN not in blob and "SECRET-TOKEN" not in blob
        assert photo["path"] == "/bot<token>/sendPhoto"
        for img in images:
            assert "iVBOR" not in blob  # no base64 of a PNG
            assert img.data.hex() not in blob
        r = await running.http.post("/_control/reset")
        assert r.status_code == 200
        assert await running.received() == []
    finally:
        await running.http.aclose()
        server.should_exit = True
        await asyncio.wait_for(task, 10)


async def test_reset_keeps_telegram_update_ids_monotonic(fake, tmp_path):
    async with telegram_client(fake, tmp_path) as (_client, inbound):
        await asyncio.sleep(0.2)
        r = await fake.post("/_control/telegram/inject", {"from_id": 77, "text": "one"})
        first = r.json()["update_id"]
        await _until(lambda: len(inbound) == 1, timeout=2)
        await asyncio.sleep(0.3)  # the poll offset has advanced past the first update
        await fake.post("/_control/reset", {})
        r = await fake.post("/_control/telegram/inject", {"from_id": 77, "text": "two"})
        assert r.json()["update_id"] > first
        await _until(lambda: len(inbound) == 2, timeout=3)
        assert inbound[1].text == "two"


async def test_reset_keeps_live_sockets_and_polls(fake, tmp_path):
    async with discord_client(fake, tmp_path) as (_client, inbound):
        await fake.post("/_control/reset", {})
        r = await fake.post("/_control/discord/inject", {"author_id": "5", "content": "still"})
        assert r.status_code == 200
        await _until(lambda: inbound)


# ── AC8: the app never imports the fake ─────────────────────────────────


def test_the_one_does_not_import_the_fake():
    root = Path(__file__).resolve().parent.parent / "the_one"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # The Leg 6 seam module is ``fake_platforms_seam``; only the tool itself is banned.
        assert not re.search(r"\b(import|from)\s+(scripts\.)?fake_platforms\b", text), path
        assert "scripts/fake_platforms" not in text, path
