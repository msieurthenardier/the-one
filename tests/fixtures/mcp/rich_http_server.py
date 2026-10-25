"""A rich streamable-HTTP MCP fixture server (M31 F5 L01), for the UI capture tool.

``make_rich_app()`` builds an ``MCPServer`` named "docs-search" with a title, a version, a website
URL, multi-paragraph instructions and four tools (one with a long description), so the MCP editor's
Server section and Tools list have something real to show. ``main()`` serves it, or one of two
wrappers around the plain hello server, on a real loopback socket in a subprocess:

    python -m tests.fixtures.mcp.rich_http_server --mode ok|legacy|401 [--port N]

``--port 0`` (the default) binds a free port and prints ``PORT <n>`` on stdout as soon as the
socket is bound; the parent reads the port back, so no port is ever hard-coded. Modes:

- ``ok``: the rich server, answering both protocol eras;
- ``legacy``: the hello server behind ``LegacyDiscoverWrapper(mode="fast400")`` (a 400 to
  ``server/discover``, so the client falls back to the older handshake);
- ``401``: the hello server behind ``Auth401Wrapper`` with bare 401s (no ``resource_metadata``),
  the "server rejected the configured credentials" case.

Test-only: never part of the product.
"""

from __future__ import annotations

import argparse
import socket
import sys

from mcp.server.mcpserver import MCPServer

from tests.fixtures.mcp.asgi_401 import Auth401Wrapper
from tests.fixtures.mcp.asgi_legacy import LegacyDiscoverWrapper
from tests.fixtures.mcp.hello_server import make_http_app

RICH_INSTRUCTIONS = (
    "Use search_docs first, then get_page for the full text.\n\n"
    "Pages are Markdown. Paths are case-sensitive and start with a slash."
)


def make_rich_app() -> MCPServer:
    """A fresh MCPServer with title, version, website, instructions and four tools."""
    app = MCPServer(
        "docs-search",
        title="Docs Search",
        version="1.4.2",
        website_url="https://docs.example.com/mcp-docs-search",
        instructions=RICH_INSTRUCTIONS,
    )

    @app.tool()
    def search_docs(query: str, limit: int = 10) -> str:
        """Search the documentation index by keyword and return the best-matching pages with a short excerpt for each one, ranked by relevance. Use this before get_page whenever you do not already know the exact path."""  # noqa: E501
        return query

    @app.tool()
    def get_page(path: str) -> str:
        """Fetch one page by its path."""
        return path

    @app.tool()
    def list_spaces() -> str:
        """List the available documentation spaces."""
        return ""

    @app.tool()
    def create_ticket(title: str, body: str, priority: str = "normal") -> str:
        """Open a ticket in the tracker."""
        return title

    return app


def make_app(mode: str):
    """The ASGI app for a ``--mode``."""
    if mode == "ok":
        return make_http_app(make_rich_app())
    if mode == "legacy":
        return LegacyDiscoverWrapper(make_http_app(), mode="fast400")
    if mode == "401":
        return Auth401Wrapper(
            make_http_app(),
            fail_methods={
                "initialize",
                "server/discover",
                "tools/list",
                "notifications/initialized",
            },
            resource_metadata=None,
        )
    raise SystemExit(f"unknown --mode {mode!r}")


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("ok", "legacy", "401"), default="ok")
    p.add_argument("--port", type=int, default=0)
    args = p.parse_args(argv)
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(64)
    print(f"PORT {sock.getsockname()[1]}", flush=True)
    config = uvicorn.Config(make_app(args.mode), log_level="warning")
    uvicorn.Server(config).run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
