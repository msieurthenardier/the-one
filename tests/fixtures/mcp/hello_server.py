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

Optional flags:
  --with-naughty-tools : F3 L5a opt-in switch — registers the three
            TEST-ONLY escape-attempt tools (``write_outside_sandbox``,
            ``dump_env``, ``try_connect``) on the module-level ``mcp_app``
            BEFORE ``FastMCP.run("stdio")`` is invoked. NEVER set in
            production; the tools exist solely to verify the F3 sandbox
            enforces its documented invariants. F2 tests that don't pass
            the flag continue to see only ``echo`` / ``add``.

See flight 02 design decision §7 for the fixture's role in F2 testing,
and flight 03 design decision §9 for the F3 escape-attempt tools.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

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


def register_naughty_tools(app: FastMCP) -> None:
    """Register TEST-ONLY escape-attempt tools on the app (F3 L5a).

    These tools exist solely to verify the F3 sandbox enforces its
    documented invariants (FS scope, env-allowlist, network policy).
    NEVER call this from production paths — registration is opt-in via
    the ``--with-naughty-tools`` CLI flag (consumed in ``main()``) and
    is NEVER invoked by ``make_mcp_app()`` automatically. F2 tests that
    don't pass the flag continue to see only ``echo`` / ``add``.

    Each tool carries a ``# TEST-ONLY (F3 escape-attempt fixture): DO
    NOT REMOVE OR PROMOTE TO PRODUCTION`` marker comment immediately
    above its ``@app.tool()`` decorator so future readers / refactoring
    agents don't accidentally repurpose them.
    """

    # TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION
    @app.tool()
    def write_outside_sandbox(path: str, content: str) -> str:
        """Write content to path. Used to verify FS scope refusal under sandbox.

        Under the strict-floor sandbox (writable_paths=[]), every host
        path outside /tmp is read-only via ``--ro-bind / /``; the
        ``write_text`` call raises OSError (EROFS or EACCES) inside the
        FastMCP runtime, which surfaces as a tool-call error to the MCP
        client. Tests assert ``MCPCallError`` with strerror text.
        """
        Path(path).write_text(content)
        return f"wrote {len(content)} bytes to {path}"

    # TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION
    @app.tool()
    def dump_env() -> dict[str, str]:
        """Return os.environ. Used to verify env-allowlist invariant under sandbox.

        Filtering attribution: ``_build_subprocess_env()`` at
        ``the_one/platform/env.py`` filters ``os.environ`` to the 8-key
        allowlist (PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ)
        BEFORE the env reaches ``BubblewrapSandbox.prepare_spawn``, so
        host-only keys (PYTEST_CURRENT_TEST, LD_PRELOAD, PYTHONHOME,
        etc.) are dropped by the platform-env allowlist. bwrap's
        ``--clearenv`` is defense-in-depth (it strips bwrap's own
        inherited env, plus re-asserts the allowlist via ``--setenv``).
        """
        return dict(os.environ)

    # TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION
    @app.tool()
    def try_connect(host: str, port: int) -> str:
        """Attempt TCP connect. Used to verify network policy under sandbox.

        Under default ``network_allowed=False`` + ``--unshare-net``,
        network calls fail with OSError (ENETUNREACH or similar).
        Returns a formatted error string (does NOT raise) so callers can
        assert on the value directly without mediating through
        FastMCP's tool-error translation.
        """
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return "connected"
        except OSError as e:
            return f"connect failed: {type(e).__name__}: {e}"


# Module-level instance — reserved for the stdio subprocess path
# (see __main__). HTTP fixture must call make_mcp_app() per-test
# because StreamableHTTPSessionManager.run() enforces once-per-instance.
mcp_app: FastMCP = make_mcp_app()


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    # Strip the F3 L5a opt-in flag BEFORE mode dispatch so it doesn't
    # collide with positional mode parsing. F3 §9: the flag is only ever
    # set by L5a tests; never by production callers.
    with_naughty = "--with-naughty-tools" in args
    args = [a for a in args if a != "--with-naughty-tools"]
    mode = args[0] if args else "--stdio"

    if mode == "--stdio":
        if with_naughty:
            register_naughty_tools(mcp_app)
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
