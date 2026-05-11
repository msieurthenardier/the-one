"""Tests for the_one.mcp.oauth.handlers.make_oauth_handlers."""

from __future__ import annotations

import asyncio

import pytest
from mcp.client.auth.exceptions import OAuthFlowError

from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import Session
from the_one.mcp.oauth import _state
from the_one.mcp.oauth.handlers import make_oauth_handlers


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    _state._pending.clear()
    yield
    _state._pending.clear()


@pytest.fixture
def stub_session(monkeypatch):
    """Place a stub Session in app._sessions and capture broadcasts.

    Per the leg's NEW-M2 fix: the lazy
    ``from the_one.interfaces.web.app import _sessions, _send_to_session``
    inside the handler resolves to the real ``app.py`` module's
    globals, not any test-app's. So we patch ``web_app._send_to_session``
    and write into ``web_app._sessions``.
    """
    broadcasts: list[tuple[str, dict]] = []

    async def capture(session, payload, exclude=None):
        broadcasts.append((session.id, payload))

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    sess = Session(
        id="cs-handlers-1",
        agent=None,  # type: ignore[arg-type]
        created="2026-05-07T00:00:00+00:00",
    )
    web_app._sessions["cs-handlers-1"] = sess
    try:
        yield sess, broadcasts
    finally:
        web_app._sessions.pop("cs-handlers-1", None)


async def test_redirect_registers_state_broadcasts_and_callback_returns_code(
    stub_session,
) -> None:
    """A5 — paired-factory contract:

      - redirect parses ``state`` from URL, registers in ``_state``
        with the right metadata, and broadcasts ``auth_required`` to
        the chat session;
      - callback awaits both the state-box and the per-state
        code_future, returning ``(code, returned_state)``;
      - missing-``state`` URL raises ``OAuthFlowError`` (no broadcast).

    Also covers the cycle-2 M5 closure-capture invariant: three
    distinct calls to ``make_oauth_handlers`` produce independent
    closures with non-aliased ``state_box`` and ``source_id``.
    """
    sess, broadcasts = stub_session

    redirect, callback = make_oauth_handlers(
        chat_session_id="cs-handlers-1",
        source_id="src-1",
        tool_call_id="tc-1",
        resource_metadata_url="https://idp/.well-known/oauth-protected-resource",
    )

    auth_url = (
        "https://idp.example.com/authorize?"
        "client_id=cid&state=STATE-X&redirect_uri=http://127.0.0.1:8484/callback"
        "&code_challenge=abc&code_challenge_method=S256"
    )
    await redirect(auth_url)

    entry = _state.peek("STATE-X")
    assert entry is not None
    assert entry.source_id == "src-1"
    assert entry.tool_call_id == "tc-1"
    assert entry.chat_session_id == "cs-handlers-1"

    assert broadcasts == [
        (
            "cs-handlers-1",
            {
                "type": "auth_required",
                "source_id": "src-1",
                "source_name": None,
                "resource_metadata_url": (
                    "https://idp/.well-known/oauth-protected-resource"
                ),
                "tool_call_id": "tc-1",
                "consent_url": auth_url,
            },
        )
    ]

    async def driver():
        await asyncio.sleep(0)
        _state.resolve("STATE-X", "code-X", "STATE-X")

    cb_result, _ = await asyncio.gather(callback(), driver())
    assert cb_result == ("code-X", "STATE-X")

    # Missing-state URL on a fresh factory raises (and does NOT broadcast).
    broadcasts.clear()
    redirect2, _ = make_oauth_handlers(
        chat_session_id="cs-handlers-1",
        source_id="s",
        tool_call_id=None,
        resource_metadata_url=None,
    )
    with pytest.raises(OAuthFlowError, match="missing state"):
        await redirect2("https://idp/authorize?client_id=c")
    assert broadcasts == []

    # Closure-capture invariant: three concurrent flows register three
    # independent state tokens with distinct source_ids.
    pairs = []
    for i in range(3):
        r, c = make_oauth_handlers(
            chat_session_id="cs-handlers-1",
            source_id=f"src-{i}",
            tool_call_id=f"tc-{i}",
            resource_metadata_url=None,
        )
        pairs.append((r, c, i))
    for r, _, i in pairs:
        await r(f"https://idp/authorize?state=ST{i}&client_id=c")
    for _, _, i in pairs:
        e = _state.peek(f"ST{i}")
        assert e is not None
        assert e.source_id == f"src-{i}"
        assert e.tool_call_id == f"tc-{i}"


async def test_make_oauth_handlers_resolves_consent_url_future() -> None:
    """F6.5 L3 — redirect_handler resolves consent_url_future with the
    authorization_url AFTER registering the state token.

    Verifies:
    - future.result() == authorization_url after redirect fires
    - _state.register ran BEFORE future resolved (register-before-resolve
      invariant: entry is peeked-able as soon as the future is done)
    - double-call (SDK retry) does NOT raise InvalidStateError
    """
    consent_url_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    redirect_handler, _ = make_oauth_handlers(
        chat_session_id="test-csid",
        source_id="src-1",
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=consent_url_future,
    )

    auth_url = "https://example.com/auth?state=abc123&client_id=x"
    await redirect_handler(auth_url)

    assert consent_url_future.done()
    assert consent_url_future.result() == auth_url

    # Register-before-resolve: state entry must be peeked immediately.
    entry = _state.peek("abc123")
    assert entry is not None
    assert entry.source_id == "src-1"

    # Double-call (SDK retry) with a DIFFERENT state token (same URL structure
    # but new state) must NOT raise InvalidStateError on the future — the guard
    # `if not consent_url_future.done()` is a no-op so the future is not
    # double-resolved. We use a different state to avoid _state.register's
    # duplicate-state-token guard (which is a separate protection layer).
    auth_url2 = "https://example.com/auth?state=abc124&client_id=x"
    await redirect_handler(auth_url2)  # guard: future already done → no-op


async def test_callback_propagates_state_failure(stub_session) -> None:
    """A6 — when ``_state.fail`` is called by another task, the awaiting
    ``callback_handler`` re-raises the SDK's actual ``OAuthFlowError``
    (not a translated wrapper).
    """
    sess, _ = stub_session
    redirect, callback = make_oauth_handlers(
        chat_session_id="cs-handlers-1",
        source_id="src-1",
        tool_call_id=None,
        resource_metadata_url=None,
    )
    await redirect("https://idp.example.com/authorize?state=ERR-S&client_id=c")

    async def driver():
        await asyncio.sleep(0)
        _state.fail("ERR-S", OAuthFlowError("operator denied"))

    with pytest.raises(OAuthFlowError, match="operator denied"):
        await asyncio.gather(callback(), driver())
