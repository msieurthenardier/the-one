"""Fake Discord Gateway v10 double (DD-8) — a scriptable ``websockets.serve``
server for the discord client's unit tests. No real network: every test
binds its own ``FakeGateway`` on an ephemeral localhost port and drives a
test-specific scenario script against ``FakeGatewaySession`` helpers.
Composable by construction — a test just writes a small async handler
coroutine; nothing here prescribes scenario shape.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve

Handler = Callable[["FakeGatewaySession"], Awaitable[None]]


class FakeGatewaySession:
    """One accepted connection — thin JSON send/recv helpers, plus a log
    of every frame received so a test can assert identify/resume payload
    CONTENT (not just opcode)."""

    def __init__(self, ws: ServerConnection) -> None:
        self.ws = ws
        self.received: list[dict[str, Any]] = []

    async def recv_json(self, timeout: float = 5.0) -> dict[str, Any]:
        raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
        payload = json.loads(raw)
        self.received.append(payload)
        return payload

    async def send_json(self, payload: dict[str, Any]) -> None:
        await self.ws.send(json.dumps(payload))

    async def send_hello(self, *, heartbeat_interval_ms: int = 50) -> None:
        await self.send_json({"op": 10, "d": {"heartbeat_interval": heartbeat_interval_ms}})

    async def send_dispatch(self, t: str, d: dict[str, Any], *, seq: int) -> None:
        await self.send_json({"op": 0, "t": t, "s": seq, "d": d})

    async def send_ready(
        self,
        *,
        session_id: str,
        resume_gateway_url: str,
        seq: int = 1,
        user_id: str = "bot-1",
        username: str = "TestBot",
        private_channels: list[dict[str, Any]] | None = None,
    ) -> None:
        await self.send_dispatch(
            "READY",
            {
                "session_id": session_id,
                "resume_gateway_url": resume_gateway_url,
                "user": {"id": user_id, "username": username, "global_name": None},
                "private_channels": private_channels or [],
                "guilds": [],
            },
            seq=seq,
        )

    async def send_resumed(self, *, seq: int) -> None:
        await self.send_dispatch("RESUMED", {}, seq=seq)

    async def send_message_create(self, d: dict[str, Any], *, seq: int) -> None:
        await self.send_dispatch("MESSAGE_CREATE", d, seq=seq)

    async def send_heartbeat_ack(self) -> None:
        await self.send_json({"op": 11})

    async def close_with_code(self, code: int, reason: str = "") -> None:
        await self.ws.close(code=code, reason=reason)

    async def close_abrupt(self) -> None:
        """Drop the connection with NO close handshake (AC-3's abrupt
        server-side close, and the fixture's default "just vanish" for
        heartbeat-ACK-withholding scenarios)."""
        self.ws.transport.abort()


class FakeGateway:
    """One scripted listener bound to an ephemeral localhost port."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self._server: Server | None = None
        self.sessions: list[FakeGatewaySession] = []
        self.errors: list[BaseException] = []

    async def start(self, host: str = "127.0.0.1") -> str:
        async def _accept(ws: ServerConnection) -> None:
            session = FakeGatewaySession(ws)
            self.sessions.append(session)
            try:
                await self._handler(session)
            except Exception as exc:  # surfaced via .errors for test assertions
                self.errors.append(exc)

        self._server = await serve(_accept, host, 0)
        port = self._server.sockets[0].getsockname()[1]
        return f"ws://{host}:{port}"

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
