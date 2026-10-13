"""In-memory pending-flow registry for OAuth authorization-code grant.

The SDK's ``OAuthClientProvider._perform_authorization_code_grant`` calls
``redirect_handler(authorization_url)`` and then ``callback_handler()``
across a yield boundary — the operator's browser tab opens the IDP
consent UI, then redirects to ``/api/oauth/callback?code=...&state=...``,
and that route must hand the ``(code, state)`` back to whichever
``callback_handler`` is awaiting it.

The link between the two halves is the ``state`` token issued by the AS
(round-tripped through the IDP). On registration, ``redirect_handler``
parses ``state`` from the authorization URL and registers it here; on
callback, the FastAPI route looks up the same ``state`` and resolves
the per-state Future.

Non-persistence trade-off: ``_pending`` is process-local and in-memory
ONLY. A FastAPI restart mid-flow drops every pending entry. The
operator's browser-tab redirect lands at ``/api/oauth/callback`` and
gets a 401 unknown-state; the chat UI surfaces "OAuth flow timed out"
and the operator re-triggers the original action. This is consistent
with the F5 §10 pause/resume not-persisted-across-restart trade-off.

TTL sweep: a periodic task started at FastAPI lifespan startup walks
``_pending`` every ``_TTL_SECONDS`` and resolves stale futures with
``OAuthFlowError("OAuth flow timed out (10-minute TTL)")``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable

from mcp.client.auth.exceptions import OAuthFlowError
from mcp.shared.auth import AuthorizationCodeResult

# 10-minute TTL per F5 §9.
_TTL_SECONDS: float = 600.0


@dataclass
class PendingFlow:
    """One entry in the pending-flow registry.

    ``code_future`` is resolved by ``resolve(state, code, returned_state, iss)``
    with an ``AuthorizationCodeResult(code, state, iss)`` on success or by ``fail(state, exc)``
    with the supplied exception. Awaiters in ``callback_handler`` get the
    code or the exception.

    ``chat_session_id`` is the originating chat session's ID (i.e.
    ``Session.id``), NOT the MCP source ID. The callback route uses it
    to look up the WebSocket subscriber set for the broadcast targeted
    by the chat UI.
    """

    code_future: asyncio.Future[AuthorizationCodeResult]
    created_at: float
    source_id: str
    tool_call_id: str | None
    chat_session_id: str


# Module-private. Tests reset via fixture.
_pending: dict[str, PendingFlow] = {}
_sweep_task: asyncio.Task | None = None


def register(
    state: str,
    *,
    source_id: str,
    tool_call_id: str | None,
    chat_session_id: str,
) -> asyncio.Future[AuthorizationCodeResult]:
    """Register a new pending flow, returning the future ``callback_handler``
    will await.

    Raises ``RuntimeError`` on collision (same ``state`` token already
    registered). The SDK generates URL-safe random state tokens; collision
    is a programming error, not a runtime concern.
    """
    if state in _pending:
        raise RuntimeError(f"Duplicate pending OAuth flow for state token: {state!r}")
    loop = asyncio.get_running_loop()
    future: asyncio.Future[AuthorizationCodeResult] = loop.create_future()
    _pending[state] = PendingFlow(
        code_future=future,
        created_at=time.time(),
        source_id=source_id,
        tool_call_id=tool_call_id,
        chat_session_id=chat_session_id,
    )
    return future


def peek(state: str) -> PendingFlow | None:
    """Return the entry for ``state`` without popping.

    Used by the FastAPI ``/api/oauth/callback`` route to look up
    ``chat_session_id`` for the WebSocket broadcast BEFORE calling
    ``resolve`` / ``fail``.
    """
    return _pending.get(state)


def resolve(state: str, code: str, returned_state: str | None, iss: str | None = None) -> bool:
    """Resolve the pending flow's future with
    ``AuthorizationCodeResult(code, returned_state, iss)``.

    ``iss`` is the RFC 9207 authorization-response issuer from the redirect's
    optional ``iss`` query parameter (None when absent); the SDK validates it
    against the authorization server's metadata (mcp 2.x).

    Pops the entry and sets the future's result. Returns True on
    success; False if ``state`` is unknown or already popped.

    The ``if not future.done()`` guard handles the race with
    ``_sweep_expired``: if the sweep popped + failed the entry between
    the route's ``peek`` and ``resolve``, this returns False and the
    callback route returns a "Login expired" HTML response (cycle-2
    NEW-H2).
    """
    entry = _pending.pop(state, None)
    if entry is None:
        return False
    if not entry.code_future.done():
        entry.code_future.set_result(
            AuthorizationCodeResult(code=code, state=returned_state, iss=iss)
        )
        return True
    # Race with _sweep_expired: future already resolved with timeout.
    # The pop already happened so we're consistent; just signal failure.
    return False


def fail(state: str, error: Exception) -> bool:
    """Fail the pending flow's future with ``error``.

    Pops the entry and sets the future's exception. Returns True on
    success; False if ``state`` is unknown or already popped (or the
    future was already resolved by a sweep).
    """
    entry = _pending.pop(state, None)
    if entry is None:
        return False
    if not entry.code_future.done():
        entry.code_future.set_exception(error)
        return True
    return False


async def _sweep_expired() -> int:
    """Walk ``_pending`` and remove entries older than ``_TTL_SECONDS``.

    Resolves each removed entry's future with
    ``OAuthFlowError("OAuth flow timed out (10-minute TTL)")``. Idempotent:
    a second call with no new entries returns 0.

    The ``if not future.done()`` guard protects against the race where
    a successful callback resolved the future BEFORE the sweep walked it
    (the future is already done; we only need to remove the entry).
    """
    now = time.time()
    removed = 0
    for state, entry in list(_pending.items()):
        if now - entry.created_at >= _TTL_SECONDS:
            del _pending[state]
            if not entry.code_future.done():
                entry.code_future.set_exception(
                    OAuthFlowError("OAuth flow timed out (10-minute TTL)")
                )
            removed += 1
    return removed


async def _periodic_sweep_loop() -> None:
    """Body of the lifespan-managed periodic sweep task.

    Wakes once per ``_TTL_SECONDS`` and calls ``_sweep_expired``. On
    ``CancelledError`` (lifespan shutdown), exits cleanly so the
    task's ``await task`` in ``stop_periodic_sweep`` returns.
    """
    try:
        while True:
            await asyncio.sleep(_TTL_SECONDS)
            await _sweep_expired()
    except asyncio.CancelledError:
        return


def start_periodic_sweep() -> asyncio.Task:
    """Start the periodic sweep loop, returning the running task.

    Idempotent: if the task is already running, returns it without
    spawning a duplicate. Lifespan integration calls this exactly
    once at startup (before the F4 pool drain registration).
    """
    global _sweep_task
    if _sweep_task is not None and not _sweep_task.done():
        return _sweep_task
    loop = asyncio.get_running_loop()
    _sweep_task = loop.create_task(_periodic_sweep_loop())
    return _sweep_task


def stop_periodic_sweep() -> Awaitable[None]:
    """Cancel the periodic sweep task and return an awaitable that
    completes when the task is fully torn down.

    Lifespan integration awaits the returned coroutine at shutdown
    AFTER the F4 pool drain. If no task is running, the returned
    coroutine resolves immediately.
    """
    return _stop_periodic_sweep()


async def _stop_periodic_sweep() -> None:
    global _sweep_task
    task = _sweep_task
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        # The loop body suppresses CancelledError; any other exception
        # is surfaced for diagnostic visibility but does not block
        # shutdown.
        pass
    finally:
        _sweep_task = None
