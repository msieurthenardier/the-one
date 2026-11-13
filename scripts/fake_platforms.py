#!/usr/bin/env python3
"""A loopback fake of the Discord REST API and gateway and the Telegram Bot API (M35 F3 L5, DD2).

The app's real Discord and Telegram clients are pointed at this server, never at the platforms.
It proves what the app SENDS (JSON bodies, multipart fields, and per file the size, SHA-256 and
PNG dimensions); it does not model what Discord or Telegram show, nor their size limits.

Routes (everything is under one port)::

    /discord/api/v10/...                 Discord REST (gateway/bot, users/@me, channels, messages)
    ws /discord/gateway[/]               Discord gateway (HELLO, IDENTIFY -> READY, heartbeats)
    /telegram/bot{token}/{method}        Telegram Bot API (getMe, getUpdates, sendMessage,
                                         sendPhoto)
    /_control/...                        health, discord/inject, telegram/inject, received,
                                         fail-next, reset

``GET /_control/received`` returns ``{"records": [...]}``: one record per send (a Discord
``POST`` or a Telegram ``sendMessage`` / ``sendPhoto``; polls and reads are not recorded) with
``seq``, ``platform``, ``method``, ``path`` (the Telegram token is replaced by ``<token>``),
``json``, ``fields``, ``files`` (name, filename, content_type, size, sha256, png dimensions;
never the bytes) and the ``status`` the fake answered. ``POST /_control/fail-next``
``{"count", "status", "kind": "upload" | "any"}`` fails the next matching sends.

The first stdout line is JSON: ``{"port": P, "pid": N}``. It refuses a non-loopback ``--host``,
a ``--port`` that is not 0 or at least 8490 (8484 and 8485 are never allowed) and a
``--save-dir`` inside the repository (all exit 2), and stops on SIGTERM or SIGINT. Run it with
the repo venv::

    .venv/bin/python scripts/fake_platforms.py [--port 0] [--save-dir DIR] [--heartbeat-ms N]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import struct
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

REPO = Path(__file__).resolve().parent.parent
LOOPBACK_NAMES = {"localhost"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BOT_ID = "900000000000000001"
BOT_NAME = "FakeBot"
TELEGRAM_BOT_ID = 111
MAX_POLL_SECONDS = 60.0
FIRST_CHANNEL_ID = 700000000000000000
FIRST_UPDATE_ID = 1000


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def png_dimensions(data: bytes) -> dict[str, int] | None:
    """Width and height from the IHDR chunk, or None when it is not a PNG."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return {"width": width, "height": height}


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(part)) or "_"


class FakeState:
    """All mutable state of one fake: records, sockets, DM channels, updates, failures."""

    def __init__(self, save_dir: Path | None, heartbeat_ms: int) -> None:
        self.save_dir = save_dir
        self.heartbeat_ms = heartbeat_ms
        self.lock = asyncio.Lock()
        # Never reset: update ids stay monotonic for the life of the process, so a client whose
        # poll offset has advanced still receives updates injected after a reset.
        self.tg_next_update = FIRST_UPDATE_ID
        self.reset()
        self.sockets: list[WebSocket] = []  # identified sockets, newest last
        self.tg_event = asyncio.Event()

    def reset(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.seq = 0
        self.dm_channels: dict[str, str] = {}
        self.dm_ids: set[str] = set()
        self.next_channel = FIRST_CHANNEL_ID
        self.next_message = 0
        self.gateway_seq = 1
        self.tg_updates: list[dict[str, Any]] = []
        self.tg_next_message = 0
        self.tg_fresh = False
        self.fail: dict[str, Any] = {"count": 0, "status": 500, "kind": "upload"}

    def new_channel(self) -> str:
        self.next_channel += 1
        return str(self.next_channel)

    def dm_for(self, user_id: str) -> str:
        if user_id not in self.dm_channels:
            cid = self.new_channel()
            self.dm_channels[user_id] = cid
            self.dm_ids.add(cid)
        return self.dm_channels[user_id]

    def take_failure(self, *, upload: bool) -> int | None:
        """The status to fail this send with, or None. ``upload`` marks a multipart upload."""
        f = self.fail
        if f["count"] <= 0:
            return None
        if f["kind"] == "upload" and not upload:
            return None
        f["count"] -= 1
        return int(f["status"])

    def release_polls(self) -> None:
        event, self.tg_event = self.tg_event, asyncio.Event()
        event.set()


async def _describe_form(
    state: FakeState, form: Any, seq: int
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    fields: dict[str, str] = {}
    files: list[dict[str, Any]] = []
    for name, value in form.multi_items():
        if hasattr(value, "filename") and hasattr(value, "read"):
            data = await value.read()
            files.append(
                {
                    "name": name,
                    "filename": value.filename,
                    "content_type": value.content_type,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "png": png_dimensions(data),
                }
            )
            if state.save_dir is not None:
                state.save_dir.mkdir(parents=True, exist_ok=True)
                target = state.save_dir / f"{seq:04d}-{_safe(name)}-{_safe(value.filename or '')}"
                target.write_bytes(data)
        else:
            fields[name] = str(value)
    return fields, files


def _discord_error(status: int) -> JSONResponse:
    if status == 429:
        body = {"message": "You are being rate limited.", "retry_after": 1, "global": False}
    else:
        body = {"message": f"fake {status}", "code": 0}
    return JSONResponse(body, status_code=status)


def _telegram_error(status: int) -> JSONResponse:
    body: dict[str, Any] = {"ok": False, "error_code": status, "description": f"fake {status}"}
    if status == 429:
        body["parameters"] = {"retry_after": 1}
    return JSONResponse(body, status_code=status)


def create_app(save_dir: Path | None = None, heartbeat_ms: int = 30000) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    state = FakeState(save_dir, heartbeat_ms)
    app.state.fake = state

    async def record(
        request: Request,
        *,
        platform: str,
        method: str,
        path: str,
        status_for: Any,
    ) -> tuple[dict[str, Any], int | None]:
        """Parse the request body, append its record and decide whether to fail it."""
        ctype = request.headers.get("content-type", "")
        body_json: Any = None
        fields: dict[str, str] = {}
        files: list[dict[str, Any]] = []
        multipart = ctype.startswith("multipart/")
        async with state.lock:
            state.seq += 1
            seq = state.seq
            if multipart:
                fields, files = await _describe_form(state, await request.form(), seq)
            else:
                raw = await request.body()
                if raw:
                    try:
                        body_json = json.loads(raw)
                    except ValueError:
                        body_json = None
            fail_status = status_for(multipart)
            rec = {
                "seq": seq,
                "platform": platform,
                "method": method,
                "path": path,
                "json": body_json,
                "fields": fields,
                "files": files,
                "status": fail_status or 200,
            }
            state.records.append(rec)
        return rec, fail_status

    # ── Discord REST ────────────────────────────────────────────────
    discord = "/discord/api/v10"

    @app.get(f"{discord}/gateway/bot")
    async def d_gateway(request: Request) -> dict[str, Any]:
        return {"url": f"ws://{request.url.netloc}/discord/gateway", "shards": 1}

    @app.get(f"{discord}/users/@me")
    async def d_me() -> dict[str, Any]:
        return {"id": BOT_ID, "username": BOT_NAME, "bot": True}

    @app.get(f"{discord}/channels/{{channel_id}}")
    async def d_channel(channel_id: str) -> dict[str, Any]:
        if channel_id in state.dm_ids:
            return {"id": channel_id, "type": 1}
        return {"id": channel_id, "type": 0, "name": f"channel-{channel_id}"}

    @app.post(f"{discord}/users/@me/channels")
    async def d_create_dm(request: Request) -> dict[str, Any]:
        body = await request.json()
        cid = state.dm_for(str(body.get("recipient_id", "")))
        return {"id": cid, "type": 1}

    @app.post(f"{discord}/channels/{{channel_id}}/messages")
    async def d_message(channel_id: str, request: Request) -> Response:
        rec, fail = await record(
            request,
            platform="discord",
            method=f"POST /channels/{channel_id}/messages",
            path=f"/channels/{channel_id}/messages",
            status_for=lambda upload: state.take_failure(upload=upload),
        )
        if fail is not None:
            return _discord_error(fail)
        state.next_message += 1
        return JSONResponse({"id": str(state.next_message), "channel_id": channel_id})

    # ── Discord gateway ─────────────────────────────────────────────
    async def gateway(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_json({"op": 10, "d": {"heartbeat_interval": state.heartbeat_ms}})
        try:
            while True:
                frame = await ws.receive_json()
                op = frame.get("op")
                if op == 2:
                    state.sockets.append(ws)
                    await ws.send_json(
                        {
                            "op": 0,
                            "t": "READY",
                            "s": 1,
                            "d": {
                                "session_id": "fake-session",
                                "user": {"id": BOT_ID, "username": BOT_NAME},
                                "private_channels": [],
                                "guilds": [],
                            },
                        }
                    )
                elif op == 1:
                    await ws.send_json({"op": 11})
                elif op == 6:
                    await ws.send_json({"op": 9, "d": False})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if ws in state.sockets:
                state.sockets.remove(ws)

    app.add_api_websocket_route("/discord/gateway", gateway)
    app.add_api_websocket_route("/discord/gateway/", gateway)

    # ── Telegram ────────────────────────────────────────────────────
    @app.post("/telegram/bot{token}/{method}")
    async def telegram(token: str, method: str, request: Request) -> Response:
        if method == "getMe":
            state.tg_fresh = True
            return JSONResponse(
                {
                    "ok": True,
                    "result": {"id": TELEGRAM_BOT_ID, "is_bot": True, "username": "FakeBot"},
                }
            )
        if method == "getUpdates":
            payload = await request.json() if await request.body() else {}
            return await _get_updates(payload)
        if method in ("sendMessage", "sendPhoto"):
            rec, fail = await record(
                request,
                platform="telegram",
                method=method,
                path=f"/bot<token>/{method}",
                status_for=lambda upload: state.take_failure(upload=method == "sendPhoto"),
            )
            if fail is not None:
                return _telegram_error(fail)
            state.tg_next_message += 1
            return JSONResponse({"ok": True, "result": {"message_id": state.tg_next_message}})
        return JSONResponse(
            {"ok": False, "error_code": 404, "description": "Not Found"}, status_code=404
        )

    async def _get_updates(payload: dict[str, Any]) -> Response:
        offset = payload.get("offset")
        timeout = min(float(payload.get("timeout") or 0), MAX_POLL_SECONDS)

        def batch() -> list[dict[str, Any]]:
            if offset is None:
                return list(state.tg_updates)
            return [u for u in state.tg_updates if u["update_id"] >= offset]

        found = batch()
        # The first poll after a getMe answers at once (the real client's connect() waits for
        # it, and the real API holds it up to 50 s): only later empty polls are held.
        fresh, state.tg_fresh = state.tg_fresh, False
        if not found and timeout > 0 and not fresh:
            event = state.tg_event
            try:
                await asyncio.wait_for(event.wait(), timeout)
            except TimeoutError:
                pass
            found = batch()
        return JSONResponse({"ok": True, "result": found})

    # ── Control ─────────────────────────────────────────────────────
    @app.get("/_control/health")
    async def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/_control/discord/inject")
    async def inject_discord(request: Request) -> Response:
        body = await request.json()
        if not state.sockets:
            return JSONResponse({"error": "no gateway client"}, status_code=409)
        author_id = str(body["author_id"])
        channel_id = str(body.get("channel_id") or state.dm_for(author_id))
        state.next_message += 1
        state.gateway_seq += 1
        author_name = body.get("author_name") or f"user-{author_id}"
        frame = {
            "op": 0,
            "t": "MESSAGE_CREATE",
            "s": state.gateway_seq,
            "d": {
                "id": str(state.next_message),
                "channel_id": channel_id,
                "author": {"id": author_id, "username": author_name, "global_name": author_name},
                "content": body["content"],
                "mentions": [],
            },
        }
        await state.sockets[-1].send_json(frame)
        return JSONResponse({"ok": True, "channel_id": channel_id})

    @app.post("/_control/telegram/inject")
    async def inject_telegram(request: Request) -> Response:
        body = await request.json()
        from_id = int(body["from_id"])
        state.tg_next_update += 1
        state.tg_next_message += 1
        update = {
            "update_id": state.tg_next_update,
            "message": {
                "message_id": state.tg_next_message,
                "from": {
                    "id": from_id,
                    "is_bot": False,
                    "first_name": body.get("first_name") or f"User{from_id}",
                },
                "chat": {
                    "id": int(body.get("chat_id") or from_id),
                    "type": body.get("chat_type") or "private",
                },
                "text": body["text"],
            },
        }
        state.tg_updates.append(update)
        state.release_polls()
        return JSONResponse({"ok": True, "update_id": update["update_id"]})

    @app.get("/_control/received")
    async def received() -> dict[str, Any]:
        return {"records": state.records}

    @app.post("/_control/fail-next")
    async def fail_next(request: Request) -> dict[str, Any]:
        body = await request.json()
        kind = body.get("kind", "upload")
        if kind not in ("upload", "any"):
            return JSONResponse({"error": "kind must be upload or any"}, status_code=422)  # type: ignore[return-value]
        state.fail = {
            "count": int(body.get("count", 1)),
            "status": int(body.get("status", 500)),
            "kind": kind,
        }
        return {"ok": True}

    @app.post("/_control/reset")
    async def reset() -> dict[str, Any]:
        state.reset()
        return {"ok": True}

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="loopback only (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="0 or >= 8490 (never 8484/8485)")
    parser.add_argument("--save-dir", type=Path, default=None, help="write received files here")
    parser.add_argument("--heartbeat-ms", type=int, default=30000)
    args = parser.parse_args(argv)
    if not is_loopback(args.host):
        print(f"fake_platforms: refusing non-loopback host {args.host!r}", file=sys.stderr)
        return 2
    if args.port in (8484, 8485) or not (args.port == 0 or args.port >= 8490):
        print(
            f"fake_platforms: refusing port {args.port} (use 0 or 8490 and above)", file=sys.stderr
        )
        return 2
    save_dir = None
    if args.save_dir is not None:
        save_dir = args.save_dir.expanduser().resolve()
        if save_dir == REPO or REPO in save_dir.parents:
            print("fake_platforms: refusing a --save-dir inside the repository", file=sys.stderr)
            return 2
    return asyncio.run(_serve(args, save_dir))


async def _serve(args: argparse.Namespace, save_dir: Path | None) -> int:
    import uvicorn

    class _Server(uvicorn.Server):
        def handle_exit(self, sig: int, frame: Any) -> None:
            # No re-raise of the signal after shutdown: a clean stop exits 0.
            self.should_exit = True

    config = uvicorn.Config(
        create_app(save_dir, args.heartbeat_ms),
        host=args.host,
        port=args.port,
        log_level="warning",
        timeout_graceful_shutdown=2,
    )
    server = _Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started and not task.done():
        await asyncio.sleep(0.02)
    if task.done():
        await task
        return 1
    port = server.servers[0].sockets[0].getsockname()[1]
    print(json.dumps({"port": port, "pid": os.getpid()}), flush=True)
    await task
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
