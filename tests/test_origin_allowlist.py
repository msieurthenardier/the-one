"""Tests for the OriginAllowlistMiddleware ASGI gate.

Covers:
  - Safe HTTP methods (GET/HEAD/OPTIONS) are never gated, even from a
    foreign origin.
  - State-mutating HTTP methods (POST/PUT/PATCH/DELETE) return 403 when
    the ``Origin`` header is foreign.
  - State-mutating HTTP methods pass when the ``Origin`` is allow-listed
    (exact match), missing entirely (curl/server-to-server), or matches
    via the port-wildcard rule (used by the ``app_clean`` fixture's
    randomly-allocated port).
  - WebSocket upgrades from a foreign origin close with code 1008 BEFORE
    ``ws.accept()`` runs.
  - WebSocket upgrades from an allow-listed origin proceed normally.
  - The ``THE_ONE_ORIGIN_ALLOWLIST`` env var extends the default list.

Uses ``starlette.testclient.TestClient`` (already transitive via FastAPI;
no new ``httpx_ws`` dependency).
"""

from __future__ import annotations

from typing import Iterable

import pytest
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from the_one.interfaces.web.middleware import (
    OriginAllowlistMiddleware,
    build_default_allowlist,
)


def _make_app(allowlist: Iterable[str]) -> FastAPI:
    """Build a minimal FastAPI app wrapped in the middleware under test."""
    app = FastAPI()
    app.add_middleware(OriginAllowlistMiddleware, allowlist=list(allowlist))

    @app.get("/api/info")
    async def info() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/mutate")
    async def mutate() -> dict[str, str]:
        return {"status": "mutated"}

    @app.put("/api/things/{thing_id}")
    async def update_thing(thing_id: str) -> dict[str, str]:
        return {"id": thing_id}

    @app.delete("/api/things/{thing_id}")
    async def delete_thing(thing_id: str) -> dict[str, str]:
        return {"deleted": thing_id}

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_text()
                await ws.send_text(f"echo:{msg}")
        except WebSocketDisconnect:
            return

    return app


# ── HTTP gating ──────────────────────────────────────────────────────────


class TestHttpGating:
    def test_get_with_foreign_origin_passes(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.get("/api/info", headers={"Origin": "http://evil.example.com"})
        assert resp.status_code == 200

    def test_head_with_foreign_origin_passes(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.head("/api/info", headers={"Origin": "http://evil.example.com"})
        # HEAD is not gated by the middleware (proven by status != 403).
        # Starlette may answer 405 for routes registered as @app.get only —
        # the point is that the gate does NOT fire on HEAD.
        assert resp.status_code != 403

    def test_options_with_foreign_origin_passes(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.options("/api/info", headers={"Origin": "http://evil.example.com"})
        # OPTIONS is not gated; status depends on whether the route handles
        # OPTIONS — Starlette returns 405 Method Not Allowed when no handler
        # is registered, but importantly NOT 403.
        assert resp.status_code != 403

    def test_post_with_foreign_origin_returns_403(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.post("/api/mutate", headers={"Origin": "http://evil.example.com"})
        assert resp.status_code == 403
        assert "Origin" in resp.json()["detail"]

    def test_put_with_foreign_origin_returns_403(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.put("/api/things/abc", headers={"Origin": "http://evil.example.com"})
        assert resp.status_code == 403

    def test_delete_with_foreign_origin_returns_403(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.delete("/api/things/abc", headers={"Origin": "http://evil.example.com"})
        assert resp.status_code == 403

    def test_post_with_allowed_origin_passes(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.post("/api/mutate", headers={"Origin": "http://127.0.0.1:8484"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "mutated"}

    def test_post_with_no_origin_passes(self) -> None:
        """curl / server-to-server callers omit Origin and must pass."""
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.post("/api/mutate")  # no Origin header
        assert resp.status_code == 200

    def test_post_with_port_wildcard_match_passes(self) -> None:
        """app_clean fixture uses a random OS-allocated port — wildcard must cover it."""
        app = _make_app(["http://127.0.0.1:*", "http://localhost:*"])
        with TestClient(app) as client:
            resp = client.post("/api/mutate", headers={"Origin": "http://127.0.0.1:54321"})
        assert resp.status_code == 200

    def test_port_wildcard_does_not_false_positive_on_subdomain(self) -> None:
        """``http://127.0.0.1.evil.com`` must NOT match ``http://127.0.0.1:*``."""
        app = _make_app(["http://127.0.0.1:*"])
        with TestClient(app) as client:
            resp = client.post("/api/mutate", headers={"Origin": "http://127.0.0.1.evil.com"})
        assert resp.status_code == 403


# ── WebSocket gating ─────────────────────────────────────────────────────


class TestWebSocketGating:
    def test_websocket_with_foreign_origin_closes_1008(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(
                    "/ws", headers={"Origin": "http://evil.example.com"}
                ) as ws:
                    # If the middleware closed pre-accept, the connect itself
                    # raises WebSocketDisconnect on entry; a recv() never
                    # returns. Force a recv to surface the close code if
                    # entering the block doesn't already raise.
                    ws.receive_text()
        assert exc_info.value.code == 1008

    def test_websocket_with_allowed_origin_accepts(self) -> None:
        app = _make_app(["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            with client.websocket_connect("/ws", headers={"Origin": "http://127.0.0.1:8484"}) as ws:
                ws.send_text("hello")
                assert ws.receive_text() == "echo:hello"

    def test_websocket_with_port_wildcard_origin_accepts(self) -> None:
        app = _make_app(["http://127.0.0.1:*"])
        with TestClient(app) as client:
            with client.websocket_connect(
                "/ws", headers={"Origin": "http://127.0.0.1:54321"}
            ) as ws:
                ws.send_text("hi")
                assert ws.receive_text() == "echo:hi"


# ── Default allowlist + env var extension ────────────────────────────────


class TestBuildDefaultAllowlist:
    def test_includes_localhost_wildcards(self) -> None:
        items = build_default_allowlist("127.0.0.1", 8484)
        assert "http://127.0.0.1:*" in items
        assert "http://localhost:*" in items
        assert "http://[::1]:*" in items

    def test_includes_configured_host_port(self) -> None:
        items = build_default_allowlist("0.0.0.0", 9999)
        assert "http://0.0.0.0:9999" in items

    def test_env_var_extension(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "THE_ONE_ORIGIN_ALLOWLIST",
            "http://example.local:8484, http://proxy.internal",
        )
        items = build_default_allowlist("127.0.0.1", 8484)
        assert "http://example.local:8484" in items
        assert "http://proxy.internal" in items

    def test_env_var_extension_gates_origin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """End-to-end: env var entry actually unblocks a POST from that origin."""
        monkeypatch.setenv("THE_ONE_ORIGIN_ALLOWLIST", "http://example.local:8484")
        allowlist = build_default_allowlist("127.0.0.1", 8484)
        app = _make_app(allowlist)
        with TestClient(app) as client:
            resp = client.post("/api/mutate", headers={"Origin": "http://example.local:8484"})
        assert resp.status_code == 200

    def test_env_var_empty_no_extras(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THE_ONE_ORIGIN_ALLOWLIST", "")
        items = build_default_allowlist("127.0.0.1", 8484)
        # Should still contain the four defaults exactly.
        assert items == [
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            "http://127.0.0.1:8484",
        ]
