"""Middleware-inclusive tests for `GET /api/oauth/callback`'s credential-gate
exemption — Mission 22 / Flight 01 / Leg 03 (`oauth-callback-reachability`).

`tests/test_oauth_callback_route.py` proves the handler's own logic against
a bare `FastAPI()` + `router` with **no** middleware — it never exercises
`CredentialGateMiddleware` at all. This module wraps the real `router` in
`OriginAllowlistMiddleware` + `CredentialGateMiddleware` (the actual stack
the callback passes through in production) so it is the one place the
gate's exemption for this one path (flight Design Decision Q3) is proven
end-to-end, with **no cookie and no `Authorization` header** on the client
— exactly the shape of the unauthenticated cross-site redirect the IdP
sends back.

Isolation mirrors two existing modules:
- `tests/test_credential_gate.py`'s `_isolated_credential_module` — resets
  `api_credential`'s process-local `_cache`/`_sources` and repoints
  `settings.data_dir` at a fresh `tmp_path`, so `register_source()` /
  credential-file reads in `TestSeam` below don't leak across tests.
- `tests/test_oauth_callback_route.py`'s `_reset_oauth_state` — clears
  `_state._pending` before/after each test.

`TestSeam` covers the dual-gated `POST /api/_test/oauth/pending` seam
(AC5) that only a browser-lane test (a separate process, unable to call
`_state.register` in-process) actually needs; the tests in this module
seed pending flows directly via `_state.register`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one import api_credential
from the_one.api_credential import FileCredentialSource
from the_one.config import settings
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.interfaces.web.middleware import (
    CredentialGateMiddleware,
    OriginAllowlistMiddleware,
)
from the_one.mcp.oauth import _state


@pytest.fixture(autouse=True)
def _isolated_credential_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Required precedent (leg artifact `Inputs`, mirroring
    `tests/test_credential_gate.py`): reset `api_credential`'s
    process-local caches so this module's tests don't leak state into
    other tests in the same pytest process, and isolate `settings.data_dir`
    so the gate reads/writes its own credential file."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(api_credential, "_cache", {})
    monkeypatch.setattr(api_credential, "_sources", [FileCredentialSource()])
    yield


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    _state._pending.clear()
    yield
    _state._pending.clear()


@pytest.fixture
async def client(tmp_path):
    """The real `router` wrapped in the real gate stack:
    `OriginAllowlistMiddleware` + `CredentialGateMiddleware`.

    Patches `get_connection`/`get_encryptor` the same way
    `tests/test_oauth_callback_route.py`'s `client` fixture does — the
    callback handler itself touches neither, but other routes reachable
    through the same router resolve these at import/dependency time, so
    satisfying them is cheap insurance against an unrelated collection
    error.
    """
    db_path = tmp_path / "callback_gate.db"
    conn = await connect_template_db(db_path)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = FastAPI()
        app.add_middleware(OriginAllowlistMiddleware, allowlist=["http://127.0.0.1:*"])
        app.add_middleware(CredentialGateMiddleware)
        app.include_router(router)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


# ── AC3 — the exempted path completes with no credential ────────────────


class TestExemptionAllowsCallback:
    async def test_callback_succeeds_through_gate_with_no_credential(
        self, client: AsyncClient
    ) -> None:
        """The middleware-inclusive positive path (AC3): a pending flow
        seeded via `_state.register`, then `GET /api/oauth/callback` with
        **no cookie and no `Authorization` header** — the exact shape of
        the unauthenticated cross-site IdP redirect — must reach the
        handler and resolve the future, not be turned away by the gate.

        This is the leg's designated red-first test (AC1): before the
        exemption exists, the gate 401s this request before it ever
        reaches the handler.
        """
        fut = _state.register(
            "S-GATE-OK",
            source_id="src-gate-1",
            tool_call_id="tc-gate-1",
            chat_session_id="cs-gate-1",
        )
        resp = await client.get(
            "/api/oauth/callback", params={"state": "S-GATE-OK", "code": "code-gate-1"}
        )
        assert resp.status_code == 200
        assert "Login successful. You may close this tab." in resp.text
        assert fut.done()
        assert await fut == ("code-gate-1", "S-GATE-OK")


# ── AC4 — the exemption opened exactly one path, nothing more ───────────


class TestExemptionScope:
    async def test_replayed_state_is_401_with_handler_detail(self, client: AsyncClient) -> None:
        """A consumed `state` is popped by `resolve` (`_state.py:106`,
        `:118`) — replaying it hits `peek → None` and the handler's own
        401, not a 200."""
        _state.register(
            "S-GATE-REPLAY",
            source_id="src-gate-2",
            tool_call_id=None,
            chat_session_id="cs-gate-2",
        )
        first = await client.get(
            "/api/oauth/callback", params={"state": "S-GATE-REPLAY", "code": "c"}
        )
        assert first.status_code == 200

        replay = await client.get(
            "/api/oauth/callback", params={"state": "S-GATE-REPLAY", "code": "c"}
        )
        assert replay.status_code == 401
        assert replay.json()["detail"] == "Unknown or expired state"

    async def test_unknown_state_is_401_with_handler_detail(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/oauth/callback", params={"state": "S-NEVER-REGISTERED", "code": "c"}
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unknown or expired state"

    async def test_missing_state_is_401_with_handler_detail(self, client: AsyncClient) -> None:
        resp = await client.get("/api/oauth/callback", params={"code": "c"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Missing state parameter"

    async def test_post_to_callback_path_is_405_not_admitted(self, client: AsyncClient) -> None:
        """`EXEMPT_PATHS` is path-only, but the route is registered
        GET-only (`@router.get("/oauth/callback")`) — other methods 405 at
        FastAPI routing, never reaching any handler logic (M20 rationale,
        `middleware.py:~178-184`)."""
        resp = await client.post("/api/oauth/callback", params={"state": "x", "code": "c"})
        assert resp.status_code == 405

    async def test_trailing_slash_stays_gated(self, client: AsyncClient) -> None:
        """`EXEMPT_PATHS` is exact-match — `/api/oauth/callback/` (trailing
        slash) is a different path string and stays behind the gate."""
        resp = await client.get(
            "/api/oauth/callback/", params={"state": "x", "code": "c"}, follow_redirects=False
        )
        assert resp.status_code == 401

    async def test_unrelated_gated_path_still_401s(self, client: AsyncClient) -> None:
        """Proves the exemption opened exactly one path: an unrelated
        gated path with no credential still 401s from the gate itself
        (the gate's own body — not the oauth handler's `detail` strings
        above), confirming the callback's exemption didn't broaden."""
        resp = await client.get("/api/info")
        assert resp.status_code == 401
        assert resp.json().get("detail") not in {
            "Unknown or expired state",
            "Missing state parameter",
        }


# ── AC5 — dev-mode test seam: POST /api/_test/oauth/pending ─────────────


class TestSeam:
    """Unlike `TestExemptionAllowsCallback`/`TestExemptionScope` above, the
    seam route `/_test/oauth/pending` is NOT itself gate-exempt — it is an
    ordinary route that requires a valid credential to reach its own
    dev-mode check, exactly like every other `/_test/...` seam. So these
    tests attach `auth_headers()`, unlike the no-credential requests
    above."""

    async def test_seam_registers_pending_flow_in_dev_mode(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "dev_mode", True)
        monkeypatch.setenv("THE_ONE_OAUTH_TEST_ENDPOINT", "1")
        resp = await client.post(
            "/api/_test/oauth/pending",
            json={
                "state": "S-SEAM-1",
                "source_id": "src-seam-1",
                "chat_session_id": "cs-seam-1",
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json() == {"state": "S-SEAM-1"}
        assert _state.peek("S-SEAM-1") is not None

    async def test_seam_403s_without_flag(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dev mode on but THE_ONE_OAUTH_TEST_ENDPOINT unset: still 403 (squawk 0146)."""
        monkeypatch.setattr(settings, "dev_mode", True)
        monkeypatch.delenv("THE_ONE_OAUTH_TEST_ENDPOINT", raising=False)
        resp = await client.post(
            "/api/_test/oauth/pending",
            json={
                "state": "S-SEAM-NOFLAG",
                "source_id": "src-seam-nf",
                "chat_session_id": "cs-seam-nf",
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 403
        assert _state.peek("S-SEAM-NOFLAG") is None

    async def test_seam_403s_without_dev_mode(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "dev_mode", False)
        monkeypatch.setenv("THE_ONE_OAUTH_TEST_ENDPOINT", "1")
        resp = await client.post(
            "/api/_test/oauth/pending",
            json={
                "state": "S-SEAM-2",
                "source_id": "src-seam-2",
                "chat_session_id": "cs-seam-2",
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 403
        assert _state.peek("S-SEAM-2") is None

    async def test_seam_409s_on_duplicate_state(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "dev_mode", True)
        monkeypatch.setenv("THE_ONE_OAUTH_TEST_ENDPOINT", "1")
        body = {
            "state": "S-SEAM-DUP",
            "source_id": "src-seam-3",
            "chat_session_id": "cs-seam-3",
        }
        first = await client.post("/api/_test/oauth/pending", json=body, headers=auth_headers())
        assert first.status_code == 200
        second = await client.post("/api/_test/oauth/pending", json=body, headers=auth_headers())
        assert second.status_code == 409
