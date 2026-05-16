"""Tests for the FastAPI ``/api/oauth/callback`` route."""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.api import router
from the_one.interfaces.web.app import Session
from the_one.mcp.oauth import _state


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    _state._pending.clear()
    yield
    _state._pending.clear()


@pytest.fixture
async def client(tmp_path):
    """FastAPI TestClient with isolated DB + Encryptor patch.

    Mirrors ``tests/test_db_api.py:18-44``.
    """
    db_path = tmp_path / "callback.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


@pytest.fixture
def chat_session_in_app(monkeypatch):
    """Place a stub Session in app._sessions and capture broadcasts.

    Per cycle-2 NEW-M2: the route does
    ``from the_one.interfaces.web.app import _sessions, _send_to_session``
    inside the body — that resolves to the real app.py module's
    globals, NOT a test_app's. So the stub Session must live in
    ``web_app._sessions`` and ``web_app._send_to_session`` must be
    patched.
    """
    broadcasts: list[tuple[str, dict]] = []

    async def capture(session, payload, exclude=None):
        broadcasts.append((session.id, payload))

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    sess = Session(
        id="cs-callback-1",
        agent=None,  # type: ignore[arg-type]
        created="2026-05-07T00:00:00+00:00",
    )
    web_app._sessions["cs-callback-1"] = sess
    try:
        yield sess, broadcasts
    finally:
        web_app._sessions.pop("cs-callback-1", None)


async def test_callback_success_resolves_and_broadcasts(
    client: AsyncClient, chat_session_in_app
) -> None:
    sess, broadcasts = chat_session_in_app
    fut = _state.register(
        "S-OK",
        source_id="src-1",
        tool_call_id="tc-1",
        chat_session_id="cs-callback-1",
    )
    resp = await client.get("/api/oauth/callback", params={"state": "S-OK", "code": "code-1"})
    assert resp.status_code == 200
    assert "Login successful. You may close this tab." in resp.text
    assert fut.done()
    assert await fut == ("code-1", "S-OK")

    assert broadcasts == [
        (
            "cs-callback-1",
            {
                "type": "auth_resolved",
                "source_id": "src-1",
                "tool_call_id": "tc-1",
            },
        )
    ]


async def test_callback_error_fails_and_broadcasts(
    client: AsyncClient, chat_session_in_app
) -> None:
    sess, broadcasts = chat_session_in_app
    fut = _state.register(
        "S-ERR",
        source_id="src-2",
        tool_call_id=None,
        chat_session_id="cs-callback-1",
    )
    resp = await client.get(
        "/api/oauth/callback",
        params={
            "state": "S-ERR",
            "error": "access_denied",
            "error_description": "user denied <consent>",
        },
    )
    assert resp.status_code == 200
    assert "Login failed" in resp.text
    # HTML-escaped error description
    assert "user denied &lt;consent&gt;" in resp.text
    assert fut.done()
    from mcp.client.auth.exceptions import OAuthFlowError

    with pytest.raises(OAuthFlowError, match="user denied"):
        await fut

    assert broadcasts == [
        (
            "cs-callback-1",
            {
                "type": "auth_failed",
                "source_id": "src-2",
                "error": "access_denied",
                "description": "user denied <consent>",
            },
        )
    ]


async def test_callback_unknown_or_missing_state_returns_401_no_broadcast(
    client: AsyncClient, chat_session_in_app
) -> None:
    """A9 — both unknown-state and missing-state return 401, no broadcast."""
    sess, broadcasts = chat_session_in_app
    # Unknown state
    resp = await client.get("/api/oauth/callback", params={"state": "MISSING", "code": "x"})
    assert resp.status_code == 401
    # Missing-state param
    resp = await client.get("/api/oauth/callback", params={"code": "x"})
    assert resp.status_code == 401
    assert broadcasts == []


async def test_callback_sweep_race_returns_login_expired(
    client: AsyncClient, chat_session_in_app
) -> None:
    """A7b — cycle-2 NEW-H2: peek finds entry but resolve races sweep."""
    import time as _time

    sess, broadcasts = chat_session_in_app
    fut = _state.register(
        "S-RACE",
        source_id="src-3",
        tool_call_id=None,
        chat_session_id="cs-callback-1",
    )
    # Backdate the entry so the next sweep removes it. We trigger the
    # sweep MANUALLY mid-test to simulate the race:
    _state._pending["S-RACE"].created_at = _time.time() - _state._TTL_SECONDS - 1

    # Patch _state.resolve to first sweep then call the real resolve,
    # mimicking the race window between peek and resolve in the route.
    real_resolve = _state.resolve
    sweeps: list[int] = []

    def racing_resolve(state, code, returned_state):
        # Run the sweep BEFORE the actual resolve — emulates the race.
        # ``_sweep_expired`` is async; wrap with a sync drive.
        import asyncio as _asyncio

        loop = _asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async call — schedule sync via a new task
            # is not safe here. Instead: directly mutate _pending by
            # calling the sync logic. We'll manually pop+fail the
            # entry to simulate the sweep's effect.
            entry = _state._pending.pop(state, None)
            if entry is not None:
                from mcp.client.auth.exceptions import OAuthFlowError

                if not entry.code_future.done():
                    entry.code_future.set_exception(
                        OAuthFlowError("OAuth flow timed out (10-minute TTL)")
                    )
                sweeps.append(1)
        return real_resolve(state, code, returned_state)

    with patch.object(_state, "resolve", side_effect=racing_resolve):
        resp = await client.get(
            "/api/oauth/callback",
            params={"state": "S-RACE", "code": "code-race"},
        )

    assert resp.status_code == 200
    assert "Login expired" in resp.text
    assert "Login successful" not in resp.text
    # No auth_resolved broadcast — chat UI must not see success
    assert broadcasts == []
    assert sweeps == [1]
    # The future was failed by the simulated sweep
    from mcp.client.auth.exceptions import OAuthFlowError

    with pytest.raises(OAuthFlowError, match="timed out"):
        await fut
