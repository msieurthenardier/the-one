"""Minimal OAuth Authorization Server stub for L5 browser tests.

NOT a full implementation — L6 HAT extends this with full RFC 9728 PRM,
RFC 8414 OAuth Authorization Server Metadata, RFC 7591 Dynamic Client
Registration, and refresh-token flows. L5's stub provides only the surface
the browser tests need to drive the UI flow without hitting a real IDP:

  - GET ``/.well-known/oauth-authorization-server`` — minimal RFC 8414
    metadata advertising ``authorization_endpoint`` + ``token_endpoint``.
  - POST ``/register`` — RFC 7591 DCR; returns an opaque ``client_id``.
  - GET ``/authorize`` — emits a 302 to the loopback redirect with a
    fixed authorization code and the original state.
  - POST ``/token`` — issues a fixed access token; ignores PKCE
    verifier (test-only).

Spawned in a thread by the browser-test fixture; binds to a random
local port so multiple tests can run in parallel without collision.

Mission 29 (mcp 2.x port) extensions - configurable modes, all off by default
so the original surface is unchanged. ``OAuthASStub(**config)`` accepts:

  - ``iss_param_supported`` - advertise
    ``authorization_response_iss_parameter_supported`` (RFC 9207) in the AS
    metadata.
  - ``metadata_issuer`` - override the ``issuer`` the AS metadata names (a
    mismatch against the discovery issuer fails sign-in, DD12.2).
  - ``token_status`` - HTTP status of ``POST /token`` (``400`` answers
    ``invalid_grant``); ``refresh_status`` overrides it for refresh grants.
  - ``auth_required_methods`` - the set of JSON-RPC methods that need a bearer
    token (default: every method), so a test can make only ``tools/list`` 401
    and have the sign-in happen mid-operation (AC7c).
  - ``mcp_after_signin`` - what an authenticated ``tools/list`` answers:
    ``"ok"`` (an empty tool list) or ``"rpc_error"`` (an ordinary JSON-RPC
    error, AC7c).

The server also answers a minimal MCP JSON-RPC endpoint on ``POST /mcp``: 401
with ``WWW-Authenticate: Bearer resource_metadata=...`` until the request
carries ``Authorization: Bearer <valid_token>``, then ``initialize`` /
``notifications/initialized`` / ``tools/list`` / ``tools/call`` answers. The
protected-resource metadata is served at
``/.well-known/oauth-protected-resource``. ``stub.mcp_requests`` records
``(method, authorized)`` for every MCP POST.

NOT a security boundary. Do NOT use outside the test suite.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit


class _OAuthASHandler(BaseHTTPRequestHandler):
    """HTTP handler for the minimal OAuth AS endpoints."""

    server_version = "OAuthASStub/0.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Silence the BaseHTTPRequestHandler default logging — keeps
        # pytest output clean. Browser tests assert on the network
        # round-trip via the UI; we don't need server logs.
        return

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        token = self.server.cfg.get("valid_token", "stub-access-token")
        return self.headers.get("Authorization", "") == f"Bearer {token}"

    def _send_401(self, base: str) -> None:
        self.send_response(401)
        prm_url = f"{base}/.well-known/oauth-protected-resource"
        self.send_header(
            "WWW-Authenticate",
            f'Bearer realm="mcp", resource_metadata="{prm_url}"',
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_mcp_post(self, base: str, body_raw: bytes) -> None:
        authorized = self._authorized()
        try:
            rpc = json.loads(body_raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            rpc = {}
        method = rpc.get("method")
        self.server.mcp_requests.append((method, authorized))
        needs_auth = self.server.cfg.get("auth_required_methods")
        if not authorized and (needs_auth is None or method in needs_auth):
            return self._send_401(base)
        rpc_id = rpc.get("id")
        if method == "initialize":
            return self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "oauth-stub", "version": "1"},
                    },
                },
            )
        if method == "tools/list":
            if self.server.cfg.get("mcp_after_signin") == "rpc_error":
                return self._json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {"code": -32001, "message": "stub ordinary rpc error"},
                    },
                )
            return self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]},
                },
            )
        if method == "tools/call":
            return self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {"content": [{"type": "text", "text": "ok"}]},
                },
            )
        # notifications (no id) and anything else: accepted, no body.
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return None

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        parsed = urlsplit(self.path)
        path = parsed.path
        base = f"http://127.0.0.1:{self.server.server_port}"
        cfg = self.server.cfg
        if path == "/.well-known/oauth-protected-resource":
            return self._json(200, {"resource": f"{base}/mcp", "authorization_servers": [base]})
        if path == "/.well-known/oauth-authorization-server":
            metadata = {
                "issuer": cfg.get("metadata_issuer") or base,
                "authorization_endpoint": f"{base}/authorize",
                "token_endpoint": f"{base}/token",
                "registration_endpoint": f"{base}/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
            }
            if cfg.get("iss_param_supported"):
                metadata["authorization_response_iss_parameter_supported"] = True
            return self._json(200, metadata)
        if path == "/authorize":
            qs = parse_qs(parsed.query)
            redirect_uri = qs.get("redirect_uri", [""])[0]
            state = qs.get("state", [""])[0]
            if not redirect_uri:
                return self._json(400, {"error": "missing redirect_uri"})
            location = f"{redirect_uri}?{urlencode({'code': 'fake-auth-code', 'state': state})}"
            self.send_response(302)
            self.send_header("Location", location)
            self.end_headers()
            return None
        if path == "/mcp":
            # The MCP server itself — return 401 with WWW-Authenticate so
            # the SDK's auth flow kicks in. Not strictly required for
            # browser tests (which exercise the UI flow only), but useful
            # for end-to-end integration via /api/oauth/start. An
            # authenticated GET (the SDK's listen stream) is a 405.
            if self._authorized():
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            self._send_401(base)
            return None
        self._json(404, {"error": "not_found", "path": path})
        return None

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        parsed = urlsplit(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0"))
        body_raw = self.rfile.read(length) if length else b""
        try:
            content_type = self.headers.get("Content-Type", "")
            if "application/json" in content_type:
                body = json.loads(body_raw.decode("utf-8") or "{}")
            else:
                body = {k: v[0] for k, v in parse_qs(body_raw.decode("utf-8")).items()}
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {}
        base = f"http://127.0.0.1:{self.server.server_port}"
        cfg = self.server.cfg
        if path == "/mcp":
            return self._handle_mcp_post(base, body_raw)
        if path == "/register":
            return self._json(
                201,
                {
                    "client_id": "stub-client-1",
                    "redirect_uris": body.get("redirect_uris", []),
                },
            )
        if path == "/token":
            self.server.token_requests.append(body.get("grant_type"))
            status = cfg.get("token_status", 200)
            if body.get("grant_type") == "refresh_token":
                status = cfg.get("refresh_status", status)
            if status != 200:
                return self._json(status, {"error": "invalid_grant"})
            return self._json(
                200,
                {
                    "access_token": "stub-access-token",
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "refresh_token": "stub-refresh-token",
                },
            )
        self._json(404, {"error": "not_found", "path": path})
        return None


class OAuthASStub:
    """Minimal OAuth Authorization Server stub running in a background thread.

    Usage:
        with OAuthASStub() as stub:
            print(stub.base_url)
            # ... drive UI tests against stub.base_url ...

    The server binds to 127.0.0.1 on an OS-assigned port and shuts down
    cleanly on context exit. Calling code asserts via the chat UI's
    network calls — there is no introspection API on the stub itself.
    """

    def __init__(self, **config) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _OAuthASHandler)
        self._server.cfg = config  # type: ignore[attr-defined]
        self._server.mcp_requests = []  # type: ignore[attr-defined]
        self._server.token_requests = []  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def mcp_requests(self) -> list[tuple[str | None, bool]]:
        """``(method, authorized)`` for every ``POST /mcp`` seen."""
        return self._server.mcp_requests  # type: ignore[attr-defined]

    @property
    def token_requests(self) -> list[str | None]:
        """``grant_type`` of every ``POST /token`` seen."""
        return self._server.token_requests  # type: ignore[attr-defined]

    @property
    def config(self) -> dict:
        """Live config; tests may flip modes between operations."""
        return self._server.cfg  # type: ignore[attr-defined]

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)

    def __enter__(self) -> OAuthASStub:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
