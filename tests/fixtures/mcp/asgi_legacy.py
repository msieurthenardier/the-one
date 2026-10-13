"""ASGI wrapper that makes ``server/discover`` fail like an older server (Mission 29, DD13).

Wraps the dual-era ``hello_server`` ASGI app. It intercepts ONLY ``server/discover``
POSTs and passes everything else (notably ``initialize``) straight through, so what
it proves over HTTP is the 2025-11-25 handshake after a failed discover - NOT a
handshake-only HTTP server (the wrapped app still speaks both eras).

Modes (what a pre-2026 server does to an unknown ``server/discover``):
  ``fast400``  HTTP 400 with a 1.x-style JSON-RPC error body (method not found)
  ``bare404``  HTTP 404, empty body
  ``drop``     never answers (the client's discover timeout fires)

``discover_calls`` counts the intercepted discovers (a structural latency check).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


class LegacyDiscoverWrapper:
    def __init__(self, app: Any, *, mode: str) -> None:
        if mode not in ("fast400", "bare404", "drop"):
            raise ValueError(mode)
        self.app = app
        self.mode = mode
        self.discover_calls = 0
        self.initialize_calls = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)

        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        try:
            method = json.loads(body).get("method")
        except (ValueError, AttributeError):
            method = None

        if method == "server/discover":
            self.discover_calls += 1
            if self.mode == "drop":
                await asyncio.sleep(3600)
                return None
            if self.mode == "fast400":
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32601, "message": "Method not found"},
                    }
                ).encode()
                status, ctype = 400, b"application/json"
            else:
                payload, status, ctype = b"", 404, b"text/plain"
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", ctype),
                        (b"content-length", str(len(payload)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})
            return None

        if method == "initialize":
            self.initialize_calls += 1

        # Replay the buffered body to the wrapped app.
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
