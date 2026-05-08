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

NOT a security boundary. Do NOT use outside the test suite.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        parsed = urlsplit(self.path)
        path = parsed.path
        base = f"http://127.0.0.1:{self.server.server_port}"
        if path == "/.well-known/oauth-authorization-server":
            return self._json(
                200,
                {
                    "issuer": base,
                    "authorization_endpoint": f"{base}/authorize",
                    "token_endpoint": f"{base}/token",
                    "registration_endpoint": f"{base}/register",
                    "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code", "refresh_token"],
                    "code_challenge_methods_supported": ["S256"],
                },
            )
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
            # for end-to-end integration via /api/oauth/start.
            self.send_response(401)
            prm_url = f"{base}/.well-known/oauth-protected-resource"
            self.send_header(
                "WWW-Authenticate",
                f'Bearer realm="mcp", resource_metadata="{prm_url}"',
            )
            self.end_headers()
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
        if path == "/register":
            return self._json(
                201,
                {
                    "client_id": "stub-client-1",
                    "redirect_uris": body.get("redirect_uris", []),
                },
            )
        if path == "/token":
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

    def __init__(self) -> None:
        self._server = HTTPServer(("127.0.0.1", 0), _OAuthASHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

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
