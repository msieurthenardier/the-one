"""ASGI middleware for cheap browser-side hardening.

`OriginAllowlistMiddleware` rejects state-mutating HTTP requests and WebSocket
upgrades whose ``Origin`` header is not in the configured allow-list. This
closes the browser-mediated cross-origin POST attack surface that the
maintenance report (2026-05-04, finding 1.2) flagged: SOP blocks the attacker
from reading the response, but does not prevent side-effecting writes hitting
``http://127.0.0.1:8484/api/...`` from a malicious page open in the operator's
browser.

WebSocket upgrades MUST be intercepted at the ASGI layer — `Depends()` runs
*after* ``ws.accept()`` and is therefore too late to gate the upgrade
handshake.
"""

from __future__ import annotations

import os
from typing import Awaitable, Callable, Iterable

# ASGI types — keep loose to avoid pulling starlette types into a hot path.
Scope = dict
Message = dict
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class OriginAllowlistMiddleware:
    """Reject state-mutating HTTP and WebSocket upgrades from foreign origins.

    Construction:
        ``app.add_middleware(OriginAllowlistMiddleware, allowlist=[...])``

    Behavior:
        - HTTP ``GET``/``HEAD``/``OPTIONS``: never gated (SOP already protects
          read responses; gating would break ordinary browser navigation).
        - HTTP ``POST``/``PUT``/``PATCH``/``DELETE``: if ``Origin`` is present
          AND not allow-listed → 403.
        - HTTP without an ``Origin`` header: passes (curl, server-to-server
          callers; the threat is browser-mediated requests, which always
          include ``Origin`` for cross-origin state-mutating fetches).
        - WebSocket: if ``Origin`` is present AND not allow-listed → close
          with code 1008 (RFC 6455 "policy violation") *before* ``accept()``.
        - WebSocket without ``Origin``: passes (non-browser clients).

    Allow-list entries:
        - Exact match: ``"http://127.0.0.1:8484"`` matches only that exact
          ``scheme://host:port`` triple.
        - Port-wildcard: ``"http://127.0.0.1:*"`` matches any port. Strict
          rule: the part after the last colon must be digits-only, which
          prevents false positives like ``http://127.0.0.1.evil.com``.
    """

    # OPTIONS intentionally NOT gated — see SECURITY-MODEL.md "Future Work"
    # (CORS / OPTIONS preflight). Gating without Access-Control-Allow-Origin
    # headers would silently break any future preflight.
    GATED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(self, app, allowlist: Iterable[str]):
        self.app = app
        self._allowlist: tuple[str, ...] = tuple(allowlist)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        origin = self._extract_origin(scope)

        if scope_type == "websocket":
            if origin and not self._is_allowed(origin):
                # Close BEFORE the route handler can call ws.accept().
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return

        # http
        method = (scope.get("method") or "GET").upper()
        if method in self.GATED_METHODS and origin and not self._is_allowed(origin):
            await self._send_403(send)
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _extract_origin(scope: Scope) -> str:
        for name, value in scope.get("headers") or []:
            if name == b"origin":
                try:
                    return value.decode("latin-1")
                except Exception:
                    return ""
        return ""

    def _is_allowed(self, origin: str) -> bool:
        for entry in self._allowlist:
            if entry.endswith(":*"):
                prefix = entry[:-1]  # e.g. "http://127.0.0.1:"
                if origin.startswith(prefix):
                    rest = origin[len(prefix) :]
                    # Strip any path so we compare the port segment cleanly.
                    port_part = rest.split("/", 1)[0]
                    # Strict digits-only — blocks "127.0.0.1.evil.com" style
                    # false positives where the next character is a dot.
                    if port_part.isdigit():
                        return True
            elif origin == entry:
                return True
        return False

    @staticmethod
    async def _send_403(send: Send) -> None:
        body = b'{"detail":"Origin not allowed"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def build_default_allowlist(host: str, port: int) -> list[str]:
    """Build the default Origin allow-list for the running server.

    Includes:
      - Port-wildcards for ``127.0.0.1``/``localhost``/``[::1]`` (the
        ``app_clean`` browser-test fixture binds uvicorn on a random
        OS-allocated port, so the allowlist must accept any port).
      - The configured ``settings.host``/``settings.port`` exact match.
      - Comma-separated extension via the ``THE_ONE_ORIGIN_ALLOWLIST`` env
        var (e.g. for a reverse-proxy hostname).
    """
    items = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
        f"http://{host}:{port}",
    ]
    extra = os.environ.get("THE_ONE_ORIGIN_ALLOWLIST", "")
    items.extend(s.strip() for s in extra.split(",") if s.strip())
    return items
