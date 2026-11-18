"""In-repo MCPServer "hello world" server for F2 integration tests.

Exposes two trivial tools: ``echo`` (text-only result) and ``add``
(typed-return triggering the SDK's structuredContent path).

The HTTP integration-test path requires a fresh MCPServer per test
(StreamableHTTPSessionManager.run() is once-per-instance), so this
module exposes a ``make_mcp_app()`` factory in addition to the
module-level ``mcp_app`` used by the stdio subprocess.

Run modes:
  --stdio : run as stdio JSON-RPC server (calls MCPServer.run("stdio"))
  --http  : prints a usage hint — HTTP tests are in-process via the
            ``mcp_fixture_http_client`` pytest fixture, NOT a real socket.

Optional flags:
  --with-naughty-tools : F3 L5a opt-in switch — registers the three
            TEST-ONLY escape-attempt tools (``write_outside_sandbox``,
            ``dump_env``, ``try_connect``) on the module-level ``mcp_app``
            BEFORE ``MCPServer.run("stdio")`` is invoked. NEVER set in
            production; the tools exist solely to verify the F3 sandbox
            enforces its documented invariants. F2 tests that don't pass
            the flag continue to see only ``echo`` / ``add``.

  --legacy-only[=<revision>] : Mission 29 F2 (DD13) — serve ONLY the 1.x
            handshake via mcp 2.3.0's handshake-only ``serve_loop`` (no
            ``server/discover``), answering the given revision (default
            2025-11-25). The process patches ``mcp.server.runner``'s
            handshake registry so ``initialize`` negotiates that revision.
  --drop-discover : a server middleware that never answers ``server/discover``
            (the client's discover timeout fires, then it falls back). Combine
            with ``--legacy-only``: a dual-era server commits to the modern era
            on any discover and then refuses ``initialize``.
  --close-on-discover : the process exits on ``server/discover`` (pipe close;
            documented as failing plainly with MCPConnectionError).
  --start-delay=<seconds> : sortie 19 — in ``--stdio`` mode sleep this long
            before serving anything (a slow-starting local server: requests wait
            in the pipe). Combines with ``--legacy-only`` and ``--drop-discover``.
  --with-input-required : registers ``needs_input`` (returns an
            ``InputRequiredResult``, DD8).

See flight 02 design decision §7 for the fixture's role in F2 testing,
and flight 03 design decision §9 for the F3 escape-attempt tools.
"""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

import anyio
from mcp import types as mcp_types
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings


def make_mcp_app(
    *,
    oversized_description: bool = False,
    website_url: str | None = None,
    input_required: bool = False,
) -> MCPServer:
    """Build a fresh MCPServer with the F2 hello tools registered.

    ``oversized_description=True`` is a TEST-ONLY switch (Mission 29, DD8):
    it registers ``big_description`` whose description exceeds the 1 MiB SSE
    event cap, so a ``tools/list`` response is one oversized event.
    ``website_url`` fills ``serverInfo.websiteUrl`` (DD5's camelCase probe).
    """
    app = MCPServer("hello", website_url=website_url)

    @app.tool()
    def echo(message: str) -> str:
        """Return the input message verbatim."""
        return message

    @app.tool()
    def add(a: int, b: int) -> int:
        """Return the sum of two integers."""
        return a + b

    if oversized_description:
        register_oversized_description_tool(app)

    if input_required:
        register_input_required_tool(app)

    return app


def register_input_required_tool(app: MCPServer) -> None:
    """TEST-ONLY (Mission 29 DD8): a tool that answers ``InputRequiredResult``."""

    def needs_input() -> mcp_types.InputRequiredResult:
        """Ask the caller for input (modern-era input-required result)."""
        return mcp_types.InputRequiredResult(request_state="x")

    app.add_tool(needs_input, name="needs_input", description="Ask the caller for input.")


def make_http_app(server: MCPServer | None = None, **kwargs):
    """The ASGI app for ``server`` (a fresh one by default).

    DNS-rebinding protection is DISABLED here — the in-process ASGI fixture
    sends requests with a synthetic Host header, and the SDK's default
    protection (active for host="127.0.0.1") would otherwise return 421
    Misdirected Request. In mcp 2.x ``transport_security`` is an argument of
    ``streamable_http_app`` (not the constructor).
    """
    server = server if server is not None else make_mcp_app(**kwargs)
    return server.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


# 1 MiB + a margin: the-one's SSE event cap is 1 MiB (MAX_SSE_EVENT_BYTES).
OVERSIZED_DESCRIPTION_BYTES = 1024 * 1024 + 4096


def register_oversized_description_tool(app: MCPServer) -> None:
    """TEST-ONLY (Mission 29 DD8): register a tool whose description is
    larger than 1 MiB, so listing tools yields one over-limit SSE event."""

    def big_description() -> str:
        return "ok"

    app.add_tool(
        big_description,
        name="big_description",
        description="x" * OVERSIZED_DESCRIPTION_BYTES,
    )


def register_naughty_tools(app: MCPServer) -> None:
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
        MCPServer runtime, which surfaces as a tool-call error to the MCP
        client. Tests assert ``MCPCallError`` with strerror text.
        """
        try:
            Path(path).write_text(content)
        except OSError as exc:
            # mcp 2.x reduces a non-ToolError to "Error executing tool <name>"
            # with no text; ToolError keeps the strerror the tests assert on.
            raise ToolError(str(exc)) from exc
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
        MCPServer's tool-error translation.
        """
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return "connected"
        except OSError as e:
            return f"connect failed: {type(e).__name__}: {e}"


# Module-level instance — reserved for the stdio subprocess path
# (see __main__). HTTP fixture must call make_mcp_app() per-test
# because StreamableHTTPSessionManager.run() enforces once-per-instance.
mcp_app: MCPServer = make_mcp_app()


async def _run_legacy_only(app: MCPServer, revision: str) -> None:
    """Serve ONLY the handshake era over stdio (mcp 2.3.0 ``serve_loop``)."""
    import mcp.server.runner as runner
    from mcp.server.stdio import stdio_server

    runner.HANDSHAKE_PROTOCOL_VERSIONS = (revision,)
    runner.LATEST_HANDSHAKE_VERSION = revision
    low = app._lowlevel_server
    async with stdio_server() as (read_stream, write_stream):
        async with low.lifespan(low) as lifespan_state:
            await runner.serve_loop(
                low,
                read_stream,
                write_stream,
                lifespan_state=lifespan_state,
                init_options=low.create_initialization_options(),
            )


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    # Strip the F3 L5a opt-in flag BEFORE mode dispatch so it doesn't
    # collide with positional mode parsing. F3 §9: the flag is only ever
    # set by L5a tests; never by production callers.
    with_naughty = "--with-naughty-tools" in args
    args = [a for a in args if a != "--with-naughty-tools"]
    # Mission 29 F2 (DD13) negotiation-fixture flags, stripped the same way.
    legacy_revision: str | None = None
    for a in list(args):
        if a == "--legacy-only":
            legacy_revision = "2025-11-25"
        elif a.startswith("--legacy-only="):
            legacy_revision = a.split("=", 1)[1]
    drop_discover = "--drop-discover" in args
    close_on_discover = "--close-on-discover" in args
    with_input_required = "--with-input-required" in args
    start_delay = 0.0
    for a in args:
        if a.startswith("--start-delay="):
            start_delay = float(a.split("=", 1)[1])
    args = [
        a
        for a in args
        if not (
            a.startswith("--legacy-only")
            or a.startswith("--start-delay")
            or a in ("--drop-discover", "--close-on-discover", "--with-input-required")
        )
    ]
    mode = args[0] if args else "--stdio"

    if mode == "--stdio":
        if with_naughty:
            register_naughty_tools(mcp_app)
        if with_input_required:
            register_input_required_tool(mcp_app)
        low = mcp_app._lowlevel_server
        if drop_discover or close_on_discover:

            async def _discover_middleware(ctx, call_next):
                if ctx.method == "server/discover":
                    if close_on_discover:
                        os._exit(0)
                    await anyio.sleep_forever()
                return await call_next(ctx)

            low.middleware.insert(0, _discover_middleware)
        if start_delay > 0:
            time.sleep(start_delay)  # a slow-starting server: nothing is read until now
        if legacy_revision is not None:
            anyio.run(_run_legacy_only, mcp_app, legacy_revision)
        else:
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
