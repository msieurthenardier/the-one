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

`CredentialGateMiddleware` (Mission 20 / Flight 1 / Leg 2) is the credential
gate itself — see its own docstring below. It was built and unit-tested in
that leg against a throwaway app, deliberately NOT yet registered on the
real one; Mission 20 / Flight 1 / Leg 4 (`enforce-gate`) registered it on
`app` in `the_one/interfaces/web/app.py`, flipping enforcement live.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Awaitable, Callable, Iterable
from urllib.parse import parse_qs

from the_one.api_credential import (
    CredentialFileError,
    IdentifiedCaller,
    lookup_credential,
    resolve_caller,
)
from the_one.interfaces.web.handoff_store import (
    HANDOFF_QUERY_PARAM,
    HandoffStore,
    get_default_handoff_store,
)
from the_one.self_configuration.constants import CONFINED_SOURCE_PATHS

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


# ---------------------------------------------------------------------------
# Credential gate (Mission 20 / Flight 1 / Leg 2 — DD3-DD8, DD12, LD1-LD4)
# ---------------------------------------------------------------------------

# The exemption set (DD5) — data, not an `if` chain, per leg Implementation
# Guidance #6, so the exemption count has something to enumerate (now two —
# see below). Method-agnostic: exempted by path only, any method — mirroring the Origin
# middleware's stance that gating OPTIONS without CORS headers would break a
# future preflight (its `GATED_METHODS` comment), and because the liveness
# endpoint (see `the_one/interfaces/web/app.py`) is registered GET-only and
# returns nothing sensitive by construction, so there is nothing a POST/PUT/
# etc. to this same path could expose even if routing ever grew one.
#
# Mission 22 / Flight 01 / Leg 03 (`oauth-callback-reachability`, flight
# Design Decision Q3) adds a second member: the external-IdP OAuth callback
# (`GET /api/oauth/callback`). The IdP's redirect back to this path is a
# cross-site top-level navigation, on which the `SameSite=Strict` session
# cookie (`_build_set_cookie_header` above) is withheld by spec — so without
# this exemption the gate 401s the redirect before the handler ever runs
# and the pending OAuth flow times out. The route needs no session: its own
# single-use, SDK-generated, unguessable `state` token IS the credential —
# the handler 401s on a missing/unknown `state` (`api.py:oauth_callback`),
# mints no credential, sets no cookie, reads/writes no DB row, and consumes
# `state` on first use (`the_one/mcp/oauth/_state.py:resolve` pops the
# entry), so a replay reaches "Unknown or expired state", not a second
# success. Same method-agnostic-by-path reasoning as liveness above: the
# route is registered GET-only (`@router.get("/oauth/callback")`), so a
# POST/PUT/etc. to this path 405s at routing rather than reaching the
# handler.
LIVENESS_PATH = "/api/live"
OAUTH_CALLBACK_PATH = "/api/oauth/callback"
EXEMPT_PATHS = frozenset({LIVENESS_PATH, OAUTH_CALLBACK_PATH})

# The `HttpOnly` session cookie's name (LD1's second channel).
SESSION_COOKIE_NAME = "the_one_session"

# Where a successful resolution is stashed on `scope` for downstream readers
# (leg Implementation Guidance #3) — namespaced to avoid colliding with
# Starlette/ASGI's own scope keys.
CALLER_SCOPE_KEY = "the_one.caller"

_NONCE_NBYTES = 16


def _mint_session_cookie_value(secret: str) -> str:
    """Build a fresh stateless session cookie value (LD3):
    ``<nonce>.<HMAC-SHA256(key=secret, msg=nonce)>``.

    The nonce carries no verifiable security property of its own — nothing
    ever checks it against anything, and correctness rests entirely on the
    secrecy of *secret*. It exists only so a captured cookie is not one
    constant blob for the lifetime of an install, and to leave room to bind
    something meaningful into the message later. Do not mistake it for a
    security control.
    """
    nonce = secrets.token_hex(_NONCE_NBYTES)
    mac = hmac.new(secret.encode("ascii"), nonce.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{nonce}.{mac}"


def _verify_session_cookie_value(value: str, secret: str) -> bool:
    """Recompute the HMAC over the cookie's nonce against *secret* and
    compare with `hmac.compare_digest` (constant-time, per LD3 — the same
    reason Leg 1 pins one on the long-lived credential's secret)."""
    nonce, sep, mac = value.partition(".")
    if not sep or not nonce or not mac:
        return False
    expected = hmac.new(secret.encode("ascii"), nonce.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


def _build_set_cookie_header(value: str) -> bytes:
    """The `Set-Cookie` header for a freshly-minted session (LD3, LD5).

    - `HttpOnly`: JavaScript must never be able to read or set this value —
      it is also the reason the browser handoff cannot be done client-side
      (see DD7's rejected alternative in the flight log).
    - `SameSite=Strict`, not the `Lax` default: `Lax` still attaches the
      cookie to a cross-site top-level navigation using a safe method, which
      is exactly the GET-side rebinding hole this mission exists to close
      (LD5's rationale, in the flight log). Verified to break nothing: the
      redirect that sets this cookie has nothing to send yet, the launcher's
      initial handoff navigation is browser/OS-initiated with no cross-site
      initiator, and every later request (reload, static assets, the WS
      handshake) originates from the app's own loaded page.
    - No `Max-Age`: a browser-session cookie, deliberately unbounded — the
      mission's restart-survival criterion wants durable sessions, and
      revocation routes through `rotate_credential()` (LD3), not expiry.
    - Not `Secure`: loopback is plain HTTP by design here (no TLS).
    - `Path=/`: sent on every request this gate wraps — routes, `/static`,
      and the `/ws` upgrade alike.
    """
    return f"{SESSION_COOKIE_NAME}={value}; HttpOnly; SameSite=Strict; Path=/".encode("ascii")


class CredentialGateMiddleware:
    """Enforce an identified caller (DD8) on every HTTP request, WebSocket
    upgrade, and `/static` path (DD6) — with exactly two unauthenticated
    exemptions (`EXEMPT_PATHS`, DD5; liveness and the OAuth callback, the
    latter added by Mission 22 / Flight 01 / Leg 03 per Q3 — see the
    rationale comment above `EXEMPT_PATHS`) and the one-time browser-handoff
    exchange (DD7, DD12).

    Construction:
        ``app.add_middleware(CredentialGateMiddleware)`` — takes an optional
        ``handoff_store`` (defaults to the shared per-process store in
        `the_one.interfaces.web.handoff_store`); tests that need TTL/clock
        control or store isolation pass their own instance.

    Layering (DD4): register this middleware AFTER `OriginAllowlistMiddleware`
    so it wraps it — Starlette's `add_middleware` inserts at index 0, so
    last-added is outermost, and this one must run first: missing/invalid
    credential -> 401 before the origin check ever runs; valid credential
    from a disallowed origin -> 403 (reaching the inner middleware).

    Channels checked, in order (LD1, leg Implementation Guidance #4) — cookie,
    then header, then query, with the query check gated on the request being
    a *document* request (GET to ``/``) so the common authenticated case
    costs one dict lookup:
      1. Session cookie (`SESSION_COOKIE_NAME`) — the browser, post-handoff.
      2. ``Authorization: Bearer <credential>`` — every non-browser caller.
      3. A one-time handoff credential in the query string, on a document
         request only. Never the long-lived credential (LD1) — the store
         only recognises values it minted itself, so presenting the
         long-lived credential (or anything else) here simply fails to
         consume and falls through to (1)/(2) or a 401.

    A malformed *existing* credential file (`CredentialFileError`, Leg 1's
    deliberate design for a corrupt-but-present file) is a server
    misconfiguration, not a client error — this returns a 401 for
    unauthenticated callers... except it converts to a bare 500 with no path
    or file detail in the body, since continuing to serve would be silently
    wrong and the exception carries a filesystem path that must not leak.
    An absent credential file is NOT this case — `lookup_credential()`
    returns ``None`` for that and the gate refuses cleanly with a normal 401.
    """

    def __init__(self, app, handoff_store: HandoffStore | None = None) -> None:
        self.app = app
        self._handoff_store = handoff_store or get_default_handoff_store()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
            return

        await self._handle_http(scope, receive, send)

    # ── HTTP ────────────────────────────────────────────────────────────

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if path in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        method = (scope.get("method") or "GET").upper()

        try:
            caller = self._resolve_cookie(scope)
            if caller is None:
                caller = self._resolve_header(scope)
        except CredentialFileError:
            await self._send_500(send)
            return

        # The handoff exchange is checked LAST, and only for document
        # requests (a GET to the app root) — never for `/static/*` or
        # `/api/*`, so a URL like `/static/x.js?handoff=...` or a stray
        # `/api/...?handoff=...` neither authorizes (LD1 restricts the
        # channel to document requests) nor consumes the token (leg Edge
        # Cases — consuming it there would let a subresource request or a
        # pasted full URL silently burn the credential before the real
        # document request arrives).
        is_document_request = method == "GET" and path == "/"
        if is_document_request:
            token = self._extract_handoff_token(scope)
            if token is not None and self._handoff_store.consume(token):
                # DD12 is explicit: a valid, unexpired, unconsumed token is
                # burned on presentation regardless of whether an existing
                # session cookie already authorized this same request — it
                # must not survive to be replayed. Decision (leg Edge
                # Cases): the exchange always (re)establishes a session
                # here rather than silently keeping whatever cookie was
                # already present, so "the token was honoured" and "the
                # response carries a fresh session" stay in lockstep.
                try:
                    stored = lookup_credential()
                except CredentialFileError:
                    await self._send_500(send)
                    return
                if stored is None:
                    # Token was valid but there is nothing to bind a
                    # session to — misconfiguration, not a client error.
                    await self._send_500(send)
                    return
                cookie_value = _mint_session_cookie_value(stored.secret)
                await self._send_handoff_redirect(send, cookie_value)
                return
            # Unknown/expired/already-consumed token: does NOT authorize.
            # Fall through to whatever `caller` cookie/header resolution
            # already produced (possibly None -> 401 below).

        if caller is not None:
            # LD2 / Decision D5: a caller from a CONFINED source (currently
            # only "self-configuration") is admitted ONLY to paths under its
            # mapped prefix — every other path gets 403. `file` and the
            # cookie channel's `session` are absent from the map and reach
            # this point unaffected, exactly as before this leg.
            #
            # Flight-end review fix: match the mount path as a ROUTE
            # BOUNDARY, not a bare string prefix. A plain
            # ``path.startswith(confined_prefix)`` would also admit a
            # sibling route that merely shares the string prefix (e.g.
            # ``/mcp/self-configuration-admin``), which is not actually
            # under the mounted surface. Only ``path == confined_prefix``
            # (bare mount path, no trailing slash) or
            # ``path.startswith(confined_prefix + "/")`` (anything under
            # it) count as "under its mapped prefix."
            confined_prefix = CONFINED_SOURCE_PATHS.get(caller.source)
            if confined_prefix is not None and not (
                path == confined_prefix or path.startswith(confined_prefix + "/")
            ):
                await self._send_403(send)
                return
            scope[CALLER_SCOPE_KEY] = caller
            await self.app(scope, receive, send)
            return

        await self._send_401(send)

    # ── WebSocket ───────────────────────────────────────────────────────

    async def _handle_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        # No query-parameter handoff channel for WebSocket upgrades — LD1
        # scopes that channel to document requests only. Cookies DO travel
        # on a same-origin WS handshake (it is an HTTP Upgrade request), so
        # an established browser session authorizes the upgrade for free.
        try:
            caller = self._resolve_cookie(scope)
            if caller is None:
                caller = self._resolve_header(scope)
        except CredentialFileError:
            # No 401/500 distinction exists for a WebSocket handshake;
            # 1011 ("Internal Error") is the closest RFC 6455 code to "the
            # server is misconfigured," distinct from the 1008 ("Policy
            # Violation") used for an ordinary missing/invalid credential.
            await send({"type": "websocket.close", "code": 1011})
            return

        if caller is None:
            # MUST close before the route handler's `ws.accept()` runs —
            # `Depends()` runs after accept and is too late (see this
            # module's top docstring and `OriginAllowlistMiddleware`'s
            # identical constraint). Code 1008 mirrors the Origin
            # middleware's choice for "policy violation."
            await send({"type": "websocket.close", "code": 1008})
            return

        # LD2 / Decision D5: a caller from a CONFINED source is refused
        # outright for EVERY WebSocket upgrade — there is no WS endpoint
        # under the surface's HTTP-only mount prefix to admit it to.
        if caller.source in CONFINED_SOURCE_PATHS:
            await send({"type": "websocket.close", "code": 1008})
            return

        scope[CALLER_SCOPE_KEY] = caller
        await self.app(scope, receive, send)

    # ── Channel resolution ─────────────────────────────────────────────

    def _resolve_cookie(self, scope: Scope) -> IdentifiedCaller | None:
        """LD1 channel 2, LD3/LD4: verify the session cookie's HMAC against
        whatever `lookup_credential()` returns *right now* — no session
        store, so this is correct immediately after a restart (a fresh
        process reads the same file and recomputes the same HMAC) and
        immediately after a rotation (the secret changed, so the HMAC no
        longer matches, no restart required).

        May raise `CredentialFileError` — deliberately not caught here; see
        the callers, which decide the 401-vs-500 split.
        """
        value = self._extract_cookie(scope, SESSION_COOKIE_NAME)
        if value is None:
            return None
        stored = lookup_credential()
        if stored is None:
            return None
        if not _verify_session_cookie_value(value, stored.secret):
            return None
        # LD4: name the channel honestly. An HMAC check recovers no source
        # or identity on its own — reporting `source="file"` would claim
        # the request presented the file credential when it did not.
        return IdentifiedCaller(identifier=stored.identifier, source="session")

    @staticmethod
    def _resolve_header(scope: Scope) -> IdentifiedCaller | None:
        """LD1 channel 1: ``Authorization: Bearer <long-lived credential>``,
        resolved through `resolve_caller` — the single entry point Leg 1's
        seam walks, with no per-source branching here or anywhere else in
        this class (mission criterion 7, the half this leg owes)."""
        raw = None
        for name, value in scope.get("headers") or []:
            if name == b"authorization":
                try:
                    raw = value.decode("latin-1")
                except Exception:
                    return None
                break
        if raw is None:
            return None
        prefix = "Bearer "
        if not raw.startswith(prefix):
            return None
        return resolve_caller(raw[len(prefix) :])

    @staticmethod
    def _extract_cookie(scope: Scope, name: str) -> str | None:
        for header_name, header_value in scope.get("headers") or []:
            if header_name != b"cookie":
                continue
            try:
                raw = header_value.decode("latin-1")
            except Exception:
                return None
            for part in raw.split(";"):
                part = part.strip()
                if part.startswith(f"{name}="):
                    return part[len(name) + 1 :]
        return None

    @staticmethod
    def _extract_handoff_token(scope: Scope) -> str | None:
        qs = scope.get("query_string") or b""
        if not qs:
            return None
        try:
            parsed = parse_qs(qs.decode("latin-1"))
        except Exception:
            return None
        values = parsed.get(HANDOFF_QUERY_PARAM)
        if not values:
            return None
        return values[0]

    # ── Responses ───────────────────────────────────────────────────────

    @staticmethod
    async def _send_401(send: Send) -> None:
        # Explicitly scoped to "Local API" — a HAT surfaced this as
        # genuinely ambiguous: the same 401 serves a browser (stale/absent
        # session cookie; remedy is "reopen the app") and a non-browser
        # caller (curl, `make verify-serving`, CI smoke, the AIAT lane;
        # remedy is "fix the Authorization header") — no single remedy
        # phrase fits both, so the message stays a neutral noun phrase and
        # leaves the remedy to the caller. Unqualified "credential" reads
        # as a provider API key (Anthropic/OpenAI/OpenRouter) in the
        # provider-setup UI; the operator rotated *this* credential,
        # correctly lost their session, and then spent a cycle re-checking
        # a provider key that was never the problem. "Local API" is the
        # disambiguator — do not drop it.
        body = b'{"detail":"Local API credential missing or invalid"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _send_403(send: Send) -> None:
        # LD2 / Decision D5: a confined-source caller (e.g. an agent's
        # per-agent `agt` credential) presenting a path outside its mapped
        # prefix. Distinct from `_send_401` — the credential IS valid, it
        # is simply not admitted here.
        body = b'{"detail":"Credential not permitted on this path"}'
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

    @staticmethod
    async def _send_500(send: Send) -> None:
        # Deliberately generic — the triggering `CredentialFileError`
        # carries a filesystem path in its message, which must not leak
        # into a response body (leg Edge Cases: "must not be an unhandled
        # traceback leaking file paths").
        body = b'{"detail":"Server misconfiguration"}'
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _send_handoff_redirect(send: Send, cookie_value: str) -> None:
        # Fixed redirect target (DD12) — never read from any request-
        # controlled input (e.g. a `next` parameter), which is the open-
        # redirect guardrail DD12 asks for. The cookie is set HERE, on the
        # redirect response, one hop before the document — the browser
        # stores it, follows the redirect as a fresh top-level navigation
        # that already carries it, and only then parses
        # `<script src="/static/...">` tags, so every subsequent
        # subresource request is already credentialed (DD6 safety net).
        set_cookie = _build_set_cookie_header(cookie_value)
        await send(
            {
                "type": "http.response.start",
                "status": 302,
                "headers": [
                    (b"location", b"/"),
                    (b"set-cookie", set_cookie),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})
