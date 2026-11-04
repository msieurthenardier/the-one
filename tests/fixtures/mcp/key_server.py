"""A key-checking streamable-HTTP MCP server (sortie 09 DD11), test-only.

The server requires a request header (default ``X-Api-Key``) whose value is one
of a configured set of keys. Each key sees only its own tools, so two agents
sharing one Library server with different keys see different tool lists.

Tools (both optional per key):

- ``echo(message: str) -> str``: returns ``message``.
- ``add(a: int, b: int) -> int``: returns ``a + b``.

Behaviour:

- A request to the MCP path without a matching key gets a BARE 401 (no
  ``WWW-Authenticate`` header, so no ``resource_metadata``). So do
  ``/.well-known/*`` and ``/register``: there is no OAuth metadata to find.
- ``tools/list`` returns only the tools mapped to the presented key.
- ``GET /_log`` (no key needed) returns a JSON list of ``{seq, method, key_tail,
  status}``: one entry per MCP request, in order. ``method`` is the JSON-RPC
  method (``tools/call`` is told apart from ``tools/list``), ``key_tail`` is ONLY the
  last 4 characters of the presented key (``null`` when none was sent), ``status``
  is 200 or 401. ``DELETE /_log`` clears it. Keys must be at least 8
  characters, and the factory refuses shorter ones, so a tail never reveals a
  whole key.

In-process (an ASGI app; drive its lifespan with ``asgi_lifespan.LifespanManager``)::

    app = make_key_app("X-Api-Key", {"alpha-key-1": ["echo"], "beta-key-22": ["echo", "add"]})
    async with LifespanManager(app):
        ...                       # app.log is the same list GET /_log serves

As a subprocess (``--port 0``, the default, binds a free port and prints
``PORT <n>`` on stdout as soon as the socket is bound)::

    python -m tests.fixtures.mcp.key_server --header X-Api-Key \
        --keys "alpha-key-1:echo;beta-key-22:echo,add" [--port N]

``--keys`` is ``key:tool,tool;key:tool``. It shuts down within about a second on
SIGTERM.

Test-only: never part of the product.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import sys
from typing import Any

from asgi_lifespan import LifespanManager
from mcp.server.mcpserver import MCPServer

from tests.fixtures.mcp.hello_server import make_http_app

MIN_KEY_LENGTH = 8
KNOWN_TOOLS = ("echo", "add")


def _server_for(tools: list[str]) -> MCPServer:
    unknown = [t for t in tools if t not in KNOWN_TOOLS]
    if unknown:
        raise ValueError(f"unknown tool name(s): {', '.join(unknown)}")
    app = MCPServer("keyed")
    if "echo" in tools:

        @app.tool()
        def echo(message: str) -> str:
            """Return the input message verbatim."""
            return message

    if "add" in tools:

        @app.tool()
        def add(a: int, b: int) -> int:
            """Return the sum of two integers."""
            return a + b

    return app


class KeyServerApp:
    """ASGI dispatcher: checks the key header, routes to that key's MCP app."""

    def __init__(self, header: str, keys: dict[str, list[str]]) -> None:
        for key in keys:
            if len(key) < MIN_KEY_LENGTH:
                raise ValueError(f"keys must be at least {MIN_KEY_LENGTH} characters")
        self.header = header
        self.keys = {k: list(v) for k, v in keys.items()}
        self.log: list[dict[str, Any]] = []
        self._header_bytes = header.lower().encode("latin-1")
        self._apps = {key: make_http_app(_server_for(tools)) for key, tools in keys.items()}

    def _key_of(self, scope: dict[str, Any]) -> str | None:
        for name, value in scope.get("headers", []):
            if name == self._header_bytes:
                return value.decode("latin-1").strip()
        return None

    async def _lifespan(self, receive, send) -> None:
        stack = contextlib.AsyncExitStack()
        await receive()  # lifespan.startup
        try:
            for sub in self._apps.values():
                await stack.enter_async_context(LifespanManager(sub))
        except BaseException:
            await send({"type": "lifespan.startup.failed", "message": "sub-app startup failed"})
            await stack.aclose()
            return
        await send({"type": "lifespan.startup.complete"})
        await receive()  # lifespan.shutdown
        await stack.aclose()
        await send({"type": "lifespan.shutdown.complete"})

    @staticmethod
    async def _respond(send, status: int, body: bytes = b"", content_type: bytes | None = None):
        headers = [(b"content-length", str(len(body)).encode())]
        if content_type:
            headers.append((b"content-type", content_type))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self._lifespan(receive, send)
        if scope["type"] != "http":
            return None

        path = scope.get("path", "")
        if path == "/_log":
            if scope["method"] == "DELETE":
                self.log.clear()
                return await self._respond(send, 204)
            return await self._respond(
                send, 200, json.dumps(self.log).encode(), b"application/json"
            )

        key = self._key_of(scope)
        body = b""
        more = scope["method"] == "POST"
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        method = None
        if body:
            try:
                method = json.loads(body).get("method")
            except (ValueError, AttributeError):
                method = None

        entry = {
            "seq": len(self.log) + 1,
            "method": method or scope["method"],
            "key_tail": key[-4:] if key else None,
            "status": 200,
        }
        if key not in self._apps:
            entry["status"] = 401
            self.log.append(entry)
            return await self._respond(send, 401)
        self.log.append(entry)

        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self._apps[key](scope, replay if scope["method"] == "POST" else receive, send)


def make_key_app(header: str, keys: dict[str, list[str]]) -> KeyServerApp:
    """The in-process ASGI app: ``header`` names the key header, ``keys`` maps
    each key (at least 8 characters) to the tool names it can see."""
    return KeyServerApp(header, keys)


def parse_keys(spec: str) -> dict[str, list[str]]:
    """``key:tool,tool;key:tool`` to ``{key: [tools]}``."""
    out: dict[str, list[str]] = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        key, _, tools = part.partition(":")
        out[key.strip()] = [t.strip() for t in tools.split(",") if t.strip()]
    return out


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--header", default="X-Api-Key")
    p.add_argument("--keys", required=True, help="key:tool,tool;key:tool")
    p.add_argument("--port", type=int, default=0)
    args = p.parse_args(argv)
    app = make_key_app(args.header, parse_keys(args.keys))
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(64)
    print(f"PORT {sock.getsockname()[1]}", flush=True)
    config = uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=1)
    uvicorn.Server(config).run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
