"""ASGI wrapper that answers chosen MCP POSTs with a real HTTP 401 (Mission 29, DD1).

Wraps the ``hello_server`` ASGI app so tests can reach the 401-detection paths
(``list_tools`` / ``call_tool``) against a REAL HTTP response with a real
``WWW-Authenticate`` header, not an injected ``HTTPStatusError``. ``initialize``
and the other handshake POSTs pass through; only POSTs whose JSON-RPC ``method``
is in ``fail_methods`` (while ``remaining`` > 0, when set) get the 401.

Lifespan and non-POST scopes pass through untouched.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

RESOURCE_METADATA = "https://example.test/.well-known/oauth-protected-resource"


class Auth401Wrapper:
    def __init__(
        self,
        app: Any,
        *,
        fail_methods: set[str] | None = None,
        remaining: int | None = None,
        resource_metadata: str = RESOURCE_METADATA,
        json_rpc_body: bool = False,
    ) -> None:
        self.app = app
        self.fail_methods: set[str] = set(fail_methods or ())
        self.remaining = remaining
        self.resource_metadata = resource_metadata
        self.json_rpc_body = json_rpc_body
        # POSTs whose method is listed here never get a response (the client's
        # own timeout fires): used to fail an operation with NO new response.
        self.hang_methods: set[str] = set()
        self.seen: list[tuple[str | None, int]] = []  # (method, status)

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

        if method in self.hang_methods:
            self.seen.append((method, -1))
            await asyncio.sleep(3600)
            return None

        if method in self.fail_methods and (self.remaining is None or self.remaining > 0):
            if self.remaining is not None:
                self.remaining -= 1
            self.seen.append((method, 401))
            payload = b""
            headers = [
                (
                    b"www-authenticate",
                    f'Bearer resource_metadata="{self.resource_metadata}"'.encode(),
                ),
                (b"content-length", b"0"),
            ]
            if self.json_rpc_body:
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32001, "message": "server says unauthorized"},
                    }
                ).encode()
                headers = [
                    (
                        b"www-authenticate",
                        f'Bearer resource_metadata="{self.resource_metadata}"'.encode(),
                    ),
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ]
            await send({"type": "http.response.start", "status": 401, "headers": headers})
            await send({"type": "http.response.body", "body": payload})
            return None

        self.seen.append((method, 0))
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
