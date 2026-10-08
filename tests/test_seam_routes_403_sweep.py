"""Squawk 0020 — one sweep asserting every `/_test/` seam route 403s.

Each dev-mode-gated `/_test/...` route already has its own targeted 403
test (`tests/test_db_api.py`, `tests/test_chat_history_purge.py`,
`tests/test_oauth_callback_gate.py::TestSeam`). None of those tests assert
the *set* of gated seams — a fifth seam added by copy-paste without the
`if not settings.dev_mode: raise HTTPException(403, ...)` guard at the top
of its handler would not be caught by any existing test. This module
closes that gap: it discovers every route mounted under `/api/_test/` by
walking `router.routes` (not a hardcoded list) and parametrizes one 403
assertion per (method, path), plus a set-comparison test that fails loudly
if the discovered seam set drifts from what this test currently knows
about.

Bare `FastAPI()` + `router`, no `CredentialGateMiddleware` — mirrors
`tests/test_db_api.py`/`tests/test_chat_history_purge.py`, not
`tests/test_oauth_callback_gate.py`. These seam handlers each gate on
`settings.dev_mode` as the FIRST statement in the function body, so the
credential-gate middleware is irrelevant to what this sweep is proving;
the simpler bare-router client is sufficient and avoids coupling this
test to the gate's own isolation fixtures.
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.config import settings
from the_one.interfaces.web.api import router

_SEAM_PREFIX = "/api/_test/"

_PLACEHOLDER = "placeholder-id"

# Some seams require query params or a request-body shape that FastAPI's
# own parameter/body validation checks BEFORE the handler's first line
# runs — without these, the request would 422 on missing required fields
# and never reach the handler's `dev_mode` gate at all, which would make
# the 403 assertion below pass for the wrong reason (or not fire). Keyed
# by (method, raw route path — with `{param}` placeholders still in it).
_EXTRA_REQUEST_KWARGS: dict[tuple[str, str], dict[str, object]] = {
    ("POST", "/api/_test/oauth/pending"): {
        "json": {
            "state": _PLACEHOLDER,
            "source_id": _PLACEHOLDER,
            "chat_session_id": _PLACEHOLDER,
        },
    },
}

# The known seam set as of this writing (squawk 0020's evidence). Update
# this deliberately — not by widening the assertion — when a seam is
# intentionally added, removed, renamed, or gains/loses an HTTP method.
# This set existing alongside the discovery walk is the point: a route
# that starts matching `_SEAM_PREFIX` without anyone updating this set is
# exactly the accidental-un-registration (or accidental-addition-without-
# a-gate) scenario the squawk is closing.
#
# Mission 23 Flight 1 (backend-removal leg, DD-6): the two connector
# seams — POST /chat/sessions/{id}/routing-audit and
# GET /chat/sessions/lookup — are deleted; their only callers were
# connector browser tests being deleted, and the session-keying columns
# they read are kept, so Flight 2 or 3 can restore them verbatim.
#
# Mission 23 Flight 2 Leg 2 (DD-10): two NEW connector seams —
# POST /_test/stub/inbound (act path) and GET /_test/stub/outbound
# (observe path) — dual-gated (dev_mode AND THE_ONE_STUB_TEST_ENDPOINT=1)
# like purge-sweep, NOT the (then) single-gate oauth/pending shape. The old
# THE_ONE_REGISTER_STUB_CONNECTOR name is not resurrected.
#
# Mission 23 Flight 3 Leg 3 (DD-7): one NEW connector seam —
# POST /_test/discord/sever — the controlled-disconnect hook for the
# discord-live-round-trip behavior test's resume step. Dual-gated
# (dev_mode AND THE_ONE_DISCORD_TEST_ENDPOINT=1), its own env name, not
# the stub gate.
#
# Squawk 0146: POST /_test/oauth/pending is now dual-gated too
# (dev_mode AND THE_ONE_OAUTH_TEST_ENDPOINT=1).
_EXPECTED_SEAMS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/_test/purge-sweep"),
        ("POST", "/api/_test/oauth/pending"),
        ("POST", "/api/_test/stub/inbound"),
        ("GET", "/api/_test/stub/outbound"),
        ("POST", "/api/_test/discord/sever"),
    }
)


def _discover_seam_routes() -> list[tuple[str, str]]:
    """Every (method, path) pair for a route mounted under `/api/_test/`.

    Walks `router.routes` directly (the router this app mounts under
    `/api` — see `the_one/interfaces/web/app.py`'s
    `app.include_router(api_router)`), not a hardcoded list, so a new
    seam route is picked up automatically rather than requiring this
    test file to be remembered.
    """
    seams: list[tuple[str, str]] = []
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith(_SEAM_PREFIX):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            seams.append((method, route.path))
    return sorted(seams)


_DISCOVERED_SEAMS = _discover_seam_routes()


def test_discovered_seam_set_matches_expected() -> None:
    """Non-empty, and matches `_EXPECTED_SEAMS` exactly.

    A route added under `/api/_test/` without updating `_EXPECTED_SEAMS`
    here fails this test — the prompt to go update the set (and confirm
    the new route also gates on `dev_mode`) rather than let it slide by
    silently. Likewise a seam quietly disappearing (e.g. an accidental
    un-registration) fails here too.
    """
    discovered = set(_DISCOVERED_SEAMS)
    assert discovered, "no routes discovered under '/api/_test/' — check the router mount"
    assert discovered == _EXPECTED_SEAMS, (
        "the set of /_test/ seam routes changed (added, removed, renamed, or an "
        "HTTP method was added/dropped on one). If this is deliberate, update "
        "_EXPECTED_SEAMS in tests/test_seam_routes_403_sweep.py to match — don't "
        "just widen or drop this assertion. "
        f"discovered={sorted(discovered)!r} expected={sorted(_EXPECTED_SEAMS)!r}"
    )


@pytest.fixture
async def client():
    """Bare router, no DB/encryptor patching — these handlers gate on
    `settings.dev_mode` before touching any repository, so none of that
    machinery is reachable in the 403 path this test exercises."""
    test_app = FastAPI()
    test_app.include_router(router)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers()
    ) as c:
        yield c


def _fill_path_params(path: str) -> str:
    """Replace every `{param}` path segment with a placeholder value, so
    the request resolves to a real route instead of 404ing on an
    unfilled template."""
    return re.sub(r"\{[^}]+\}", _PLACEHOLDER, path)


@pytest.mark.parametrize(
    "method,path",
    _DISCOVERED_SEAMS,
    ids=[f"{m}:{p}" for m, p in _DISCOVERED_SEAMS],
)
async def test_seam_route_403s_without_dev_mode(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    """Every discovered `/_test/` seam route returns exactly 403 — not
    422, not 404, not 200 — when `settings.dev_mode` is explicitly False.

    A minimal valid-looking request is sent (empty JSON body for
    POST/PUT/PATCH, placeholder path params, plus any extra query/body
    fields a given route's own request validation requires — see
    `_EXTRA_REQUEST_KWARGS`) so the gate has to fire on its own dev_mode
    check, not on a validation failure that would 422 before the handler
    ever runs. A 422 or 404 here is a failure of the test's premise, not
    a pass — hence the exact `== 403`, not `!= 200`.
    """
    monkeypatch.setattr(settings, "dev_mode", False)

    resolved_path = _fill_path_params(path)
    request_kwargs: dict[str, object] = {}
    if method in {"POST", "PUT", "PATCH"}:
        request_kwargs["json"] = {}
    request_kwargs.update(_EXTRA_REQUEST_KWARGS.get((method, path), {}))

    resp = await client.request(method, resolved_path, **request_kwargs)

    assert resp.status_code == 403, (
        f"{method} {resolved_path} returned {resp.status_code}, expected 403. "
        "A 422/404 here means the request was rejected by FastAPI's own "
        "validation before the handler's dev_mode gate ever ran — the test's "
        "premise (a minimal valid-looking request) doesn't hold for this "
        "route; check _EXTRA_REQUEST_KWARGS. Any other non-403 means the "
        "route is not actually gated on settings.dev_mode."
    )
