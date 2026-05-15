"""Test the WS ping/pong RTT primitive (L6.4).

Verifies the server's WebSocket dispatch short-circuits ``{"type":"ping"}``
to ``{"type":"pong"}`` without touching session state. The client-side
RTT measurement that consumes these pongs lives in
``the_one/interfaces/web/static/js/areas/chat.js`` and is covered by
the L6.5 smoke check in the operator HAT.

Uses Starlette's ``TestClient.websocket_connect`` against the real
FastAPI app — no live daemon required.
"""

from __future__ import annotations

import json

from starlette.testclient import TestClient

from the_one.interfaces.web.app import app


def test_ws_ping_returns_pong() -> None:
    """``{"type":"ping"}`` triggers an immediate ``{"type":"pong"}``."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            data = json.loads(ws.receive_text())
            assert data["type"] == "pong"


def test_ws_ping_does_not_create_session() -> None:
    """A bare ping must not auto-create a session or send `session_joined`.

    Locks in the short-circuit semantic — pings are health checks,
    not implicit joins. The server returns ONLY the pong frame; any
    additional frame on the same socket would mean ping leaked into
    the action dispatch below it.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            first = json.loads(ws.receive_text())
            assert first == {"type": "pong"}

            # A second ping should yield exactly a second pong — proves
            # the receive loop is still serving and the prior frame
            # didn't push the connection into a session-bound state.
            ws.send_text(json.dumps({"type": "ping"}))
            second = json.loads(ws.receive_text())
            assert second == {"type": "pong"}
