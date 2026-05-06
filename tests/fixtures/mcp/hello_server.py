"""In-repo FastMCP "hello world" server for F2 integration tests.

Exposes two trivial tools: ``echo`` (text-only result) and ``add``
(typed-return triggering the SDK's structuredContent path).

The HTTP integration-test path requires a fresh FastMCP per test
(StreamableHTTPSessionManager.run() is once-per-instance), so this
module exposes a ``make_mcp_app()`` factory in addition to the
module-level ``mcp_app`` used by the stdio subprocess.

Run modes:
  --stdio : run as stdio JSON-RPC server (calls FastMCP.run("stdio"))
  --http  : prints a usage hint — HTTP tests are in-process via the
            ``mcp_fixture_http_client`` pytest fixture, NOT a real socket.

See flight 02 design decision §7 for the fixture's role in F2 testing.
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


def make_mcp_app() -> FastMCP:
    """Build a fresh FastMCP server with the F2 hello tools registered.

    DNS-rebinding protection is DISABLED here — the in-process ASGI
    fixture sends requests with a synthetic Host header, and FastMCP's
    default protection (active for host="127.0.0.1") would otherwise
    return 421 Misdirected Request.
    """
    app = FastMCP(
        "hello",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )

    @app.tool()
    def echo(message: str) -> str:
        """Return the input message verbatim."""
        return message

    @app.tool()
    def add(a: int, b: int) -> int:
        """Return the sum of two integers."""
        return a + b

    return app


# Module-level instance — reserved for the stdio subprocess path
# (see __main__). HTTP fixture must call make_mcp_app() per-test
# because StreamableHTTPSessionManager.run() enforces once-per-instance.
mcp_app: FastMCP = make_mcp_app()


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    mode = args[0] if args else "--stdio"

    if mode == "--stdio":
        mcp_app.run("stdio")
        return 0

    if mode == "--http":
        print(
            "tests/fixtures/mcp/hello_server.py: --http is documentation only.",
            file=sys.stderr,
        )
        print(
            "HTTP tests run in-process via the mcp_fixture_http_client pytest "
            "fixture (no real socket).",
            file=sys.stderr,
        )
        return 0

    print(
        f"unknown mode: {mode!r}; expected --stdio or --http",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
