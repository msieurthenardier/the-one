"""Tests for CredentialGateMiddleware — Mission 20 / Flight 1 / Leg 2
(`gate-middleware`).

Built and unit-tested against a throwaway app (`_make_app`, mirroring the
precedent at `tests/test_origin_allowlist.py`) — most of this module's
tests exercise the middleware in isolation this way. Mission 20 / Flight 1
/ Leg 4 (`enforce-gate`) registered the gate on the real app; `TestBlastRadius`
below asserts the real app's middleware stack contains it, exactly once,
outermost.

Isolation: every test in this module resets `the_one.api_credential`'s
process-local `_cache`/`_sources` and repoints `settings.data_dir` at a
fresh `tmp_path`, mirroring `tests/test_api_credential.py`'s
`_isolated_credential_module` fixture. This is load-bearing, not
decorative — `TestSeam` below calls `register_source()`, and without this
reset that registration would leak into every later test in the same
pytest process (the leg artifact calls this out explicitly as required
precedent, not optional).
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Iterable
from unittest import mock

import pytest
from fastapi import FastAPI, Request, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from the_one import api_credential
from the_one.api_credential import (
    FileCredentialSource,
    IdentifiedCaller,
    LocalApiCredential,
    get_credential,
    register_source,
    rotate_credential,
)
from the_one.config import settings
from the_one.interfaces.web import middleware as gate_module
from the_one.interfaces.web.handoff_store import (
    HANDOFF_QUERY_PARAM,
    HandoffStore,
    get_default_handoff_store,
)
from the_one.interfaces.web.middleware import (
    CALLER_SCOPE_KEY,
    EXEMPT_PATHS,
    LIVENESS_PATH,
    SESSION_COOKIE_NAME,
    CredentialGateMiddleware,
    OriginAllowlistMiddleware,
)
from the_one.self_configuration.constants import CONFINED_SOURCE_PATHS, MOUNT_PATH


@pytest.fixture(autouse=True)
def _isolated_credential_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Required precedent (leg artifact `Inputs`): reset `api_credential`'s
    process-local caches so `register_source()` calls in `TestSeam` don't
    leak into other tests in this run, and isolate `settings.data_dir` so
    every test reads/writes its own credential file."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(api_credential, "_cache", {})
    monkeypatch.setattr(api_credential, "_sources", [FileCredentialSource()])
    yield


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _make_app(
    tmp_path: Path,
    allowlist: Iterable[str] = ("http://127.0.0.1:*",),
    handoff_store: HandoffStore | None = None,
) -> FastAPI:
    """Build a minimal FastAPI app carrying BOTH `OriginAllowlistMiddleware`
    (registered first) and `CredentialGateMiddleware` (registered second) —
    exercising DD4's layering requires both; the gate alone cannot
    demonstrate 401-before-origin versus valid-credential-wrong-origin-403.
    """
    app = FastAPI()
    app.state.ws_accepted = []
    app.add_middleware(OriginAllowlistMiddleware, allowlist=list(allowlist))
    app.add_middleware(CredentialGateMiddleware, handoff_store=handoff_store)

    static_dir = tmp_path / "static_assets"
    static_dir.mkdir(exist_ok=True)
    (static_dir / "app.js").write_text("console.log('hi');")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index() -> dict[str, str]:
        return {"page": "document"}

    @app.get(LIVENESS_PATH)
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/info")
    async def info() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/mutate")
    async def mutate() -> dict[str, str]:
        return {"status": "mutated"}

    @app.get("/api/whoami")
    async def whoami(request: Request) -> dict[str, str | None]:
        caller = request.scope.get(CALLER_SCOPE_KEY)
        if caller is None:
            return {"identifier": None, "source": None}
        return {"identifier": caller.identifier, "source": caller.source}

    @app.delete("/api/things/{thing_id}")
    async def delete_thing(thing_id: str) -> dict[str, str]:
        return {"deleted": thing_id}

    @app.api_route(MOUNT_PATH + "/{rest:path}", methods=["GET", "POST"])
    async def surface_stub(rest: str) -> dict[str, str]:
        return {"mounted": rest}

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket) -> None:
        await ws.accept()
        ws.app.state.ws_accepted.append(True)
        try:
            while True:
                msg = await ws.receive_text()
                await ws.send_text(f"echo:{msg}")
        except WebSocketDisconnect:
            return

    return app


def _bearer(cred: LocalApiCredential) -> dict[str, str]:
    return {"Authorization": f"Bearer {cred.encode()}"}


# ── Blast radius ─────────────────────────────────────────────────────────


class TestBlastRadius:
    def test_gate_middleware_is_registered_on_the_real_app_and_outermost(self) -> None:
        """Mission 20 / Flight 1 / Leg 4 (`enforce-gate`) inverted this test:
        it used to guard against *premature* registration
        (`test_gate_middleware_is_not_registered_on_the_real_app`); this leg
        made that registration real, so the guard now pins the opposite
        fact. Renamed rather than deleted-and-re-added so `git blame` shows
        the intent shift instead of a vanished test and an unrelated new
        one. Also asserts registered-exactly-once, guarding against an
        accidental double-registration (e.g. a stray `add_middleware` call
        added alongside this one in a future edit) doubling every request's
        credential-resolution cost silently."""
        from the_one.interfaces.web.app import app as real_app

        classes = [m.cls for m in real_app.user_middleware]
        assert classes.count(CredentialGateMiddleware) == 1
        # Last-added is outermost (index 0) — DD4.
        assert classes[0] is CredentialGateMiddleware


# ── Exemption (DD5) ─────────────────────────────────────────────────────


class TestExemption:
    def test_liveness_reachable_with_no_credential(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(LIVENESS_PATH)
        assert resp.status_code == 200

    def test_liveness_body_carries_no_version_or_prompt(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(LIVENESS_PATH)
        body_text = resp.text.lower()
        assert "version" not in body_text
        assert "base_prompt" not in body_text
        assert "prompt" not in body_text

    def test_exempt_set_has_exactly_one_member(self) -> None:
        assert EXEMPT_PATHS == frozenset({LIVENESS_PATH})

    def test_head_on_liveness_path_is_exempt(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.head(LIVENESS_PATH)
        assert resp.status_code != 401

    def test_options_on_liveness_path_is_exempt(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.options(LIVENESS_PATH)
        assert resp.status_code != 401

    def test_non_liveness_path_is_not_exempt(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/api/info")
        assert resp.status_code == 401


# ── HTTP enforcement ─────────────────────────────────────────────────────


class TestHttpEnforcementNoCredential:
    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
    def test_gated_path_refused_401_with_no_credential(self, tmp_path: Path, method: str) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.request(method, "/api/info")
        assert resp.status_code == 401


class TestHttpEnforcementValidCredential:
    def test_valid_header_credential_is_allowed_through(self, tmp_path: Path) -> None:
        cred = get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/api/info", headers=_bearer(cred))
        assert resp.status_code == 200

    def test_resolved_caller_is_stashed_on_scope_not_discarded(self, tmp_path: Path) -> None:
        cred = get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/api/whoami", headers=_bearer(cred))
        assert resp.status_code == 200
        body = resp.json()
        assert body["identifier"] == cred.identifier
        assert body["source"] == "file"

    def test_malformed_authorization_header_yields_same_401_as_absent(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/api/info", headers={"Authorization": "garbage not a bearer"})
        assert resp.status_code == 401

    def test_missing_credential_file_refuses_cleanly_not_500(self, tmp_path: Path) -> None:
        # No get_credential()/rotate_credential() called — no file exists.
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/api/info", headers={"Authorization": "Bearer loc_x.y"})
        assert resp.status_code == 401


class TestMalformedCredentialFile:
    def test_malformed_existing_credential_file_yields_500_not_traceback(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "api-credential").write_text("not-a-valid-credential")
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/api/info", headers={"Authorization": "Bearer loc_x.y"})
        assert resp.status_code == 500
        # The file path must never leak into the response body.
        assert str(tmp_path) not in resp.text


# ── WebSocket enforcement ────────────────────────────────────────────────


class TestWebSocketEnforcement:
    def test_no_credential_closes_1008_before_accept(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as ws:
                    ws.receive_text()
            assert exc_info.value.code == 1008
        assert app.state.ws_accepted == []

    def test_valid_header_credential_allows_upgrade(self, tmp_path: Path) -> None:
        cred = get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            with client.websocket_connect("/ws", headers=_bearer(cred)) as ws:
                ws.send_text("hi")
                assert ws.receive_text() == "echo:hi"
        assert app.state.ws_accepted == [True]

    def test_valid_session_cookie_allows_upgrade(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            client.get("/", params={HANDOFF_QUERY_PARAM: token})  # establishes session cookie
            with client.websocket_connect("/ws") as ws:
                ws.send_text("hi")
                assert ws.receive_text() == "echo:hi"


# ── Static gating (DD6) ──────────────────────────────────────────────────


class TestStaticGating:
    def test_static_asset_refused_without_credential(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/static/app.js")
        assert resp.status_code == 401

    def test_static_asset_allowed_with_credential(self, tmp_path: Path) -> None:
        cred = get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/static/app.js", headers=_bearer(cred))
        assert resp.status_code == 200


# ── Layering (DD4) ────────────────────────────────────────────────────────


class TestLayering:
    def test_registration_order_matches_app_py(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path)
        classes = [m.cls for m in app.user_middleware]
        # Last-added is outermost (index 0) — the gate must be outermost.
        assert classes[0] is CredentialGateMiddleware
        assert classes[1] is OriginAllowlistMiddleware

    def test_no_credential_and_disallowed_origin_returns_401_origin_logic_never_runs(
        self, tmp_path: Path
    ) -> None:
        app = _make_app(tmp_path, allowlist=["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.post("/api/mutate", headers={"Origin": "http://evil.example.com"})
        # 401 (gate), not 403 (origin) — proves the gate ran first and the
        # request never reached OriginAllowlistMiddleware.
        assert resp.status_code == 401

    def test_valid_credential_and_disallowed_origin_returns_403(self, tmp_path: Path) -> None:
        cred = get_credential()
        app = _make_app(tmp_path, allowlist=["http://127.0.0.1:8484"])
        with TestClient(app) as client:
            resp = client.post(
                "/api/mutate",
                headers={**_bearer(cred), "Origin": "http://evil.example.com"},
            )
        assert resp.status_code == 403


# ── Handoff exchange (DD7, DD12) ──────────────────────────────────────────


class TestHandoffExchange:
    def test_document_request_with_valid_token_redirects_and_sets_cookie(
        self, tmp_path: Path
    ) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert resp.headers.get("location") == "/"
        set_cookie = resp.headers.get("set-cookie", "")
        assert SESSION_COOKIE_NAME in set_cookie
        assert token not in set_cookie

    def test_redirect_location_contains_no_credential(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False)
        location = resp.headers.get("location", "")
        assert token not in location
        assert "handoff" not in location

    def test_cookie_is_httponly(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False)
        set_cookie = resp.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()

    def test_samesite_is_strict(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False)
        set_cookie = resp.headers.get("set-cookie", "")
        assert "samesite=strict" in set_cookie.lower()
        # `Lax` reopened exactly the gap this mission closes (LD5) — pin
        # explicitly against a regression to the unexamined default.
        assert "samesite=lax" not in set_cookie.lower()

    def test_subsequent_request_with_only_the_cookie_is_authorized(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            client.get("/", params={HANDOFF_QUERY_PARAM: token})  # follows redirect, stores cookie
            resp = client.get("/api/info")  # cookie only, no header
        assert resp.status_code == 200

    def test_cookie_set_on_redirect_hop_not_on_final_document_response(
        self, tmp_path: Path
    ) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=True)
        assert len(resp.history) == 1
        assert "set-cookie" in resp.history[0].headers
        assert "set-cookie" not in resp.headers


# ── Session binding (LD3) ─────────────────────────────────────────────────


class TestSessionBinding:
    def test_session_survives_a_second_freshly_constructed_instance(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app1 = _make_app(tmp_path, handoff_store=store)
        with TestClient(app1) as client1:
            client1.get("/", params={HANDOFF_QUERY_PARAM: token})
            cookie_value = client1.cookies.get(SESSION_COOKIE_NAME)

        assert cookie_value is not None

        # A second, freshly constructed middleware instance (via a second
        # app), backed by the SAME on-disk credential (same tmp_path) —
        # the restart stand-in.
        app2 = _make_app(tmp_path, handoff_store=HandoffStore())
        with TestClient(app2) as client2:
            client2.cookies.set(SESSION_COOKIE_NAME, cookie_value)
            resp = client2.get("/api/info")
        assert resp.status_code == 200

    def test_cookie_refused_immediately_after_rotation_no_restart(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            client.get("/", params={HANDOFF_QUERY_PARAM: token})
            pre_rotation = client.get("/api/info")
            assert pre_rotation.status_code == 200

            rotate_credential()

            post_rotation = client.get("/api/info")
        assert post_rotation.status_code == 401

    def test_cookie_with_bad_hmac_is_refused(self, tmp_path: Path) -> None:
        get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE_NAME, "deadbeef.notarealmac")
            resp = client.get("/api/info")
        assert resp.status_code == 401

    def test_cookie_verification_uses_constant_time_comparison(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        spy = mock.Mock(side_effect=hmac.compare_digest)
        with mock.patch.object(gate_module.hmac, "compare_digest", spy):
            with TestClient(app) as client:
                client.get("/", params={HANDOFF_QUERY_PARAM: token})
                client.get("/api/info")
        assert spy.called

    def test_single_use_replay_with_no_cookie_present_is_refused(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as first_client:
            first_client.get("/", params={HANDOFF_QUERY_PARAM: token})  # consumes it

        with TestClient(app) as second_client:  # fresh cookie jar — no cookie
            resp = second_client.get(
                "/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False
            )
        assert resp.status_code == 401

    def test_single_use_replay_with_existing_valid_session_does_not_reestablish(
        self, tmp_path: Path
    ) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            first = client.get("/", params={HANDOFF_QUERY_PARAM: token})
            assert first.status_code == 200
            # Replay the SAME (already-consumed) token; the client's jar now
            # carries the valid session cookie from the first exchange.
            second = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False)
        # Authorized via the pre-existing cookie (not via the replayed
        # token) — no redirect, no fresh Set-Cookie was minted for this
        # replay.
        assert second.status_code == 200
        assert "set-cookie" not in second.headers

    def test_ttl_refuses_an_expired_unused_token(self, tmp_path: Path) -> None:
        get_credential()
        clock = _FakeClock()
        store = HandoffStore(ttl_seconds=30.0, clock=clock)
        token = store.mint()
        clock.advance(31.0)
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False)
        assert resp.status_code == 401

    def test_fixed_redirect_target_ignores_next_parameter(self, tmp_path: Path) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get(
                "/",
                params={HANDOFF_QUERY_PARAM: token, "next": "/evil"},
                follow_redirects=False,
            )
        assert resp.headers.get("location") == "/"

    def test_per_process_store_fresh_store_rejects_outstanding_and_spent_values(
        self, tmp_path: Path
    ) -> None:
        get_credential()
        store_a = HandoffStore()
        outstanding_token = store_a.mint()
        spent_token = store_a.mint()
        app_a = _make_app(tmp_path, handoff_store=store_a)
        with TestClient(app_a) as client_a:
            spend_resp = client_a.get(
                "/", params={HANDOFF_QUERY_PARAM: spent_token}, follow_redirects=False
            )
        assert spend_resp.status_code in (302, 303)

        # A fresh store/app stands in for a restarted process.
        store_b = HandoffStore()
        app_b = _make_app(tmp_path, handoff_store=store_b)
        with TestClient(app_b) as client_b:
            outstanding_resp = client_b.get(
                "/", params={HANDOFF_QUERY_PARAM: outstanding_token}, follow_redirects=False
            )
            spent_resp = client_b.get(
                "/", params={HANDOFF_QUERY_PARAM: spent_token}, follow_redirects=False
            )
        assert outstanding_resp.status_code == 401
        assert spent_resp.status_code == 401

    def test_long_lived_credential_in_query_parameter_is_refused(self, tmp_path: Path) -> None:
        cred = get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(
                "/", params={HANDOFF_QUERY_PARAM: cred.encode()}, follow_redirects=False
            )
        assert resp.status_code == 401


# ── Query channel restricted to document requests ─────────────────────────


class TestQueryChannelDocumentRequestsOnly:
    def test_static_asset_with_token_in_query_is_refused_and_does_not_consume(
        self, tmp_path: Path
    ) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get(f"/static/app.js?{HANDOFF_QUERY_PARAM}={token}")
        assert resp.status_code == 401
        # Not consumed: the token still works on a genuine document request.
        with TestClient(app) as client2:
            follow_up = client2.get(
                "/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False
            )
        assert follow_up.status_code in (302, 303)

    def test_api_call_with_token_in_query_is_refused_and_does_not_consume(
        self, tmp_path: Path
    ) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            resp = client.get(f"/api/info?{HANDOFF_QUERY_PARAM}={token}")
        assert resp.status_code == 401
        with TestClient(app) as client2:
            follow_up = client2.get(
                "/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False
            )
        assert follow_up.status_code in (302, 303)


# ── Caller identity (LD4) ──────────────────────────────────────────────────


class TestCallerIdentity:
    def test_cookie_authenticated_request_names_session_source(self, tmp_path: Path) -> None:
        cred = get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            client.get("/", params={HANDOFF_QUERY_PARAM: token})
            resp = client.get("/api/whoami")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "session"
        assert body["identifier"] == cred.identifier

    def test_header_authenticated_request_keeps_lookup_seam_result_unchanged(
        self, tmp_path: Path
    ) -> None:
        cred = get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/api/whoami", headers=_bearer(cred))
        body = resp.json()
        assert body["source"] == "file"
        assert body["identifier"] == cred.identifier


# ── Seam (mission criterion 7 — the half this leg owes) ────────────────────


class _InMemorySource:
    name = "in-memory-test-source"

    def __init__(self, owned: LocalApiCredential) -> None:
        self._owned = owned

    def resolve(self, presented: str) -> IdentifiedCaller | None:
        parsed = LocalApiCredential.parse(presented)
        if parsed is None:
            return None
        if parsed.identifier != self._owned.identifier:
            return None
        if not hmac.compare_digest(parsed.secret, self._owned.secret):
            return None
        return IdentifiedCaller(identifier=self._owned.identifier, source=self.name)


class _ConfinedTestSource:
    """Stand-in for `SelfConfigurationCredentialSource` — resolves any
    credential matching `owned` to `source="self-configuration"`, the one
    name present in `CONFINED_SOURCE_PATHS`. Mirrors `_InMemorySource`
    above; kept separate because it always reports the confined source
    name regardless of what the caller constructs it with."""

    name = "self-configuration"

    def __init__(self, owned: LocalApiCredential) -> None:
        self._owned = owned

    def resolve(self, presented: str) -> IdentifiedCaller | None:
        parsed = LocalApiCredential.parse(presented)
        if parsed is None:
            return None
        if parsed.identifier != self._owned.identifier:
            return None
        if not hmac.compare_digest(parsed.secret, self._owned.secret):
            return None
        return IdentifiedCaller(identifier=self._owned.identifier, source=self.name)


class TestConfinedSourceScoping:
    """AC5 (LD2 / Decision D5): a caller from a CONFINED source is admitted
    ONLY under its mapped path prefix; `file` and `session` callers are
    unaffected everywhere — the matrix this class locks."""

    def test_confined_map_has_exactly_the_self_configuration_entry(self) -> None:
        assert CONFINED_SOURCE_PATHS == {"self-configuration": MOUNT_PATH}

    def test_confined_caller_admitted_under_its_mount_path(self, tmp_path: Path) -> None:
        confined_cred = LocalApiCredential.generate()
        register_source(_ConfinedTestSource(confined_cred))
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(f"{MOUNT_PATH}/tools", headers=_bearer(confined_cred))
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "path,method",
        [
            ("/api/agents", "GET"),
            ("/api/info", "GET"),
            ("/", "GET"),
            ("/static/app.js", "GET"),
            ("/api/mutate", "POST"),
        ],
    )
    def test_confined_caller_refused_403_outside_mount_path(
        self, tmp_path: Path, path: str, method: str
    ) -> None:
        confined_cred = LocalApiCredential.generate()
        register_source(_ConfinedTestSource(confined_cred))
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.request(method, path, headers=_bearer(confined_cred))
        assert resp.status_code == 403

    def test_confined_caller_websocket_upgrade_refused(self, tmp_path: Path) -> None:
        confined_cred = LocalApiCredential.generate()
        register_source(_ConfinedTestSource(confined_cred))
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws", headers=_bearer(confined_cred)):
                    pass
        assert app.state.ws_accepted == []

    def test_confined_caller_refused_403_on_sibling_prefix_path(self, tmp_path: Path) -> None:
        """Flight-end review fix: a sibling route that merely shares the
        mount path as a STRING PREFIX (e.g. `/mcp/self-configuration-admin`)
        must NOT be treated as "under" the mount path — the confinement
        check must match a route boundary (`path == prefix` or
        `path.startswith(prefix + "/")`), not a bare `str.startswith`."""
        confined_cred = LocalApiCredential.generate()
        register_source(_ConfinedTestSource(confined_cred))
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(f"{MOUNT_PATH}-admin/x", headers=_bearer(confined_cred))
        assert resp.status_code == 403

    def test_confined_caller_admitted_on_bare_mount_path(self, tmp_path: Path) -> None:
        """The bare mount path with no trailing slash and nothing after it
        must still be admitted (not 403'd by the gate) — a 404 from
        downstream routing (no route registered for the bare path in this
        test app) is a separate, acceptable outcome."""
        confined_cred = LocalApiCredential.generate()
        register_source(_ConfinedTestSource(confined_cred))
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(MOUNT_PATH, headers=_bearer(confined_cred))
        assert resp.status_code != 403

    def test_confined_caller_admitted_on_mount_path_with_trailing_slash(
        self, tmp_path: Path
    ) -> None:
        confined_cred = LocalApiCredential.generate()
        register_source(_ConfinedTestSource(confined_cred))
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(f"{MOUNT_PATH}/", headers=_bearer(confined_cred))
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "path",
        ["/api/info", "/", "/static/app.js", f"{MOUNT_PATH}/tools"],
    )
    def test_file_credential_unaffected_on_every_path(self, tmp_path: Path, path: str) -> None:
        """The AC5 matrix's load-bearing negative control: a check phrased
        as "source is not file" would 403 the session cookie everywhere —
        this and the next test assert `file`/`session` pass through
        unaffected on every path, including the confined mount path."""
        cred = get_credential()
        app = _make_app(tmp_path)
        with TestClient(app) as client:
            resp = client.get(path, headers=_bearer(cred))
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "path",
        ["/api/info", "/", "/static/app.js", f"{MOUNT_PATH}/tools"],
    )
    def test_session_cookie_unaffected_on_every_path(self, tmp_path: Path, path: str) -> None:
        get_credential()
        store = HandoffStore()
        token = store.mint()
        app = _make_app(tmp_path, handoff_store=store)
        with TestClient(app) as client:
            client.get("/", params={HANDOFF_QUERY_PARAM: token})
            resp = client.get(path)
        assert resp.status_code == 200


class TestSeam:
    def test_second_source_honoured_by_gate_with_no_code_change(self, tmp_path: Path) -> None:
        file_cred = get_credential()
        second_cred = LocalApiCredential.generate()
        register_source(_InMemorySource(second_cred))

        app = _make_app(tmp_path)
        with TestClient(app) as client:
            file_resp = client.get("/api/whoami", headers=_bearer(file_cred))
            second_resp = client.get("/api/whoami", headers=_bearer(second_cred))

        assert file_resp.status_code == 200
        assert second_resp.status_code == 200
        assert file_resp.json()["source"] == "file"
        assert second_resp.json()["source"] == "in-memory-test-source"


# ── Mint endpoint + liveness route on the REAL app (LD2) ───────────────────
#
# These drive `the_one.interfaces.web.app.app` directly via TestClient. The
# gate middleware IS registered there as of Leg 4 (`enforce-gate`;
# TestBlastRadius above pins that) and outermost, so every request below now
# actually passes through it — including the mint endpoint's own in-route
# `_require_long_lived_caller` dependency, exercised end-to-end rather than
# "verified while the middleware is still unregistered" as it was pre-Leg-4.


@pytest.mark.usefixtures("reset_lifespan_singletons")
class TestMintEndpointOnRealApp:
    def test_liveness_route_exists_on_real_app(self, tmp_path: Path) -> None:
        from the_one.interfaces.web.app import app as real_app

        with TestClient(real_app) as client:
            resp = client.get(LIVENESS_PATH)
        assert resp.status_code == 200
        body_text = resp.text.lower()
        assert "version" not in body_text
        assert "base_prompt" not in body_text

    def test_mint_endpoint_refuses_without_long_lived_credential(self, tmp_path: Path) -> None:
        from the_one.interfaces.web.app import app as real_app

        with TestClient(real_app) as client:
            resp = client.post("/api/session/handoff")
        assert resp.status_code == 401

    def test_mint_endpoint_returns_usable_handoff_url(self, tmp_path: Path) -> None:
        from the_one.interfaces.web.app import app as real_app

        cred = get_credential()
        with TestClient(real_app) as client:
            resp = client.post("/api/session/handoff", headers=_bearer(cred))
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert HANDOFF_QUERY_PARAM in url

        token = url.split(f"{HANDOFF_QUERY_PARAM}=", 1)[1]

        # Drive the returned token through a throwaway gate-carrying app
        # backed by the SAME (default) store the mint endpoint wrote into,
        # proving the URL is a genuinely usable one-time credential.
        gate_app = _make_app(tmp_path, handoff_store=get_default_handoff_store())
        with TestClient(gate_app) as gate_client:
            exchange = gate_client.get(
                "/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False
            )
        assert exchange.status_code in (302, 303)

    def test_mint_endpoint_does_not_accept_a_handoff_credential_as_its_own_auth(
        self, tmp_path: Path
    ) -> None:
        from the_one.interfaces.web.app import app as real_app

        cred = get_credential()
        with TestClient(real_app) as client:
            first = client.post("/api/session/handoff", headers=_bearer(cred))
            assert first.status_code == 200
            handoff_token = first.json()["url"].split("handoff=", 1)[1]

            second = client.post(
                "/api/session/handoff",
                headers={"Authorization": f"Bearer {handoff_token}"},
            )
        assert second.status_code == 401

    def test_cookie_only_websocket_upgrade_succeeds_on_real_app(self, tmp_path: Path) -> None:
        """Mission 20 / Flight 1 / Leg 4 (`enforce-gate`) Pre-Flip Harness
        Fix — regression test: a session cookie ALONE (no `Authorization`
        header on the WS handshake) must authorize a WebSocket upgrade on
        the real app. Before this leg, that combination was exercised only
        against the throwaway `_make_app` (`TestWebSocketEnforcement.
        test_valid_session_cookie_allows_upgrade`), which is why the gap in
        `tests/browser/conftest.py` — never establishing a session cookie,
        only ever attaching the header — survived Leg 3's own acceptance
        test: that test asserts the header on the *document* request and
        never opens a socket. A native browser `WebSocket` cannot set an
        `Authorization` header (WHATWG restriction), so this exact
        cookie-only path is what the real chat UI depends on.
        """
        from the_one.interfaces.web.app import app as real_app

        cred = get_credential()
        with TestClient(real_app) as client:
            mint_resp = client.post("/api/session/handoff", headers=_bearer(cred))
            assert mint_resp.status_code == 200
            url = mint_resp.json()["url"]
            token = url.split(f"{HANDOFF_QUERY_PARAM}=", 1)[1]

            exchange = client.get("/", params={HANDOFF_QUERY_PARAM: token}, follow_redirects=False)
            assert exchange.status_code in (302, 303)
            assert client.cookies.get(SESSION_COOKIE_NAME) is not None

            # No Authorization header here — the session cookie in the
            # client's jar (carried automatically on the WS handshake, a
            # same-origin HTTP Upgrade request) must be sufficient on its
            # own. A refusal would raise WebSocketDisconnect on `__enter__`,
            # before `ws.accept()` — see `TestWebSocketEnforcement.
            # test_no_credential_closes_1008_before_accept` for that
            # failure-mode shape.
            with client.websocket_connect("/ws"):
                pass
