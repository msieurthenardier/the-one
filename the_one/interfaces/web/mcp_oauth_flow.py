"""The chat's **Sign in** flow: who owns its outcome (sortie 22, DD3).

``POST /api/oauth/start`` builds a provider and hands it to :func:`start_chat_sign_in`,
which drives the SDK auth flow on a background task and is the ONLY sender of the
chat-facing ``auth_resolved`` / ``auth_failed`` frames and the ONLY scheduler of the
paused turn's resume. ``GET /api/oauth/callback`` just resolves the code and renders the
popup; it can no longer resume a turn before the new tokens are saved.

Completion rule (the SDK saves before it retries the original request, so
``client.post`` returns only after the save and the retry):

* **Resolved**: the flow's storage recorded a save made after its last redirect
  (``MCPSourceTokenStorage.tokens_saved``, reset by a wrapper on the redirect handler),
  even if the retried request then raised or answered non-2xx; or the final response is
  2xx with no save (a valid stored token).
* **Failed**: an exception before any save, or a non-2xx final response with no save.
  ``auth_failed`` carries ``str(exc)``, or :data:`START_FAILED_DESCRIPTION` for a response.

Exactly once: :func:`_schedule_resume` checks the paused state, claims the session id in a
module-level set and creates the task with no await in between; the task's done-callback
releases the id. Two flows for the same session finishing together (two tabs) cannot both
resume.

Superseded flows: flows are tracked per (chat session id, source id). A resolved flow
always reports and resumes (claimed), then cancels the other in-flight flows for its key.
A failed flow stays silent when it is no longer the latest for its key or another flow for
the key resolved since it started, so a stale TTL failure cannot close a newer popup.
Accepted: a late-resolving flow after a resume that re-paused resumes the new pause.

Known limitation: the flow replays ``initialize``. When the pause came from something
``initialize`` cannot reproduce (a 403 step-up on a tool call, or a server that 401s one
method only) the flow sees 2xx with no save and resolves; the resumed call refuses again
and the chat shows **Sign in** again.

``app.py`` imports ``api`` at load, so ``app`` names are imported at call time only.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

import httpx2

logger = logging.getLogger(__name__)

#: ``auth_failed.description`` when the final response was not 2xx and nothing was saved.
START_FAILED_DESCRIPTION = "The server did not accept the sign-in (HTTP {status})."
#: ``auth_failed.description`` when no usable provider exists for the source.
NO_PROVIDER_DESCRIPTION = "Sign-in is not available for this source."

_FlowKey = tuple[str, str]


class _Flow:
    """One in-flight chat sign-in flow."""

    def __init__(self, key: _FlowKey, resolved_base: int) -> None:
        self.key = key
        self.resolved_base = resolved_base
        self.task: asyncio.Task[None] | None = None


# key -> in-flight flows, oldest first; key -> number of flows that resolved.
_flows: dict[_FlowKey, list[_Flow]] = {}
_resolved_count: dict[_FlowKey, int] = {}
# Session ids with a resume scheduled and not yet finished.
_resuming: set[str] = set()


def _schedule_resume(chat_session_id: str, session: Any) -> None:
    """Resume the paused turn once: check, claim and schedule with no await between."""
    from the_one.interfaces.web import app as web_app

    agent = session.agent
    if agent is None or agent._deferred_tool_calls is None:
        return
    if chat_session_id in _resuming:
        return
    _resuming.add(chat_session_id)
    task = asyncio.create_task(web_app._resume_paused_session(session))
    web_app._inflight_resume_tasks.add(task)
    task.add_done_callback(web_app._inflight_resume_tasks.discard)
    task.add_done_callback(lambda _t: _resuming.discard(chat_session_id))


async def _send(chat_session_id: str, frame: dict[str, Any]) -> Any:
    """Send ``frame`` to the chat session if it is still open; returns the session."""
    from the_one.interfaces.web import app as web_app

    session = web_app._sessions.get(chat_session_id)
    if session is not None:
        with contextlib.suppress(Exception):
            await web_app._send_to_session(session, frame)
    return session


async def _report_resolved(
    flow: _Flow, chat_session_id: str, source_id: str, tool_call_id: str | None
) -> None:
    key = flow.key
    _resolved_count[key] = _resolved_count.get(key, 0) + 1
    for other in list(_flows.get(key, ())):
        if other is not flow and other.task is not None:
            other.task.cancel()
    session = await _send(
        chat_session_id,
        {"type": "auth_resolved", "source_id": source_id, "tool_call_id": tool_call_id},
    )
    if session is not None:
        _schedule_resume(chat_session_id, session)


async def _report_failed(
    flow: _Flow, chat_session_id: str, source_id: str, description: str
) -> None:
    flows = _flows.get(flow.key, [])
    superseded = (flows and flows[-1] is not flow) or (
        _resolved_count.get(flow.key, 0) > flow.resolved_base
    )
    if superseded:
        return
    await _send(
        chat_session_id,
        {
            "type": "auth_failed",
            "source_id": source_id,
            "error": "start_failed",
            "description": description,
        },
    )


def _wrap_redirect_handler(provider: Any, storage: Any) -> None:
    """Reset the save flag at each redirect, so only a later save counts."""
    original = provider.context.redirect_handler

    async def redirect_handler(authorization_url: str) -> None:
        storage.tokens_saved = False
        await original(authorization_url)

    provider.context.redirect_handler = redirect_handler


async def _drive(
    flow: _Flow,
    provider: Any,
    server_url: str,
    chat_session_id: str,
    source_id: str,
    tool_call_id: str | None,
    headers_for: Callable[[str], dict[str, str]],
) -> None:
    """Hit the source URL with the provider attached (the SDK runs the auth flow),
    classify the outcome and report it."""
    try:
        context = getattr(provider, "context", None)
        storage = getattr(context, "storage", None)
        if storage is None or getattr(context, "redirect_handler", None) is None:
            await _report_failed(flow, chat_session_id, source_id, NO_PROVIDER_DESCRIPTION)
            return
        _wrap_redirect_handler(provider, storage)
        failure: str | None = None
        try:
            async with httpx2.AsyncClient(auth=provider, timeout=30.0) as client:
                # ``initialize`` returns 401 when no token is present; the provider's
                # ``async_auth_flow`` runs PRM/OASM/DCR/auth and its ``redirect_handler``
                # broadcasts ``auth_required`` with the real ``consent_url``. DD10: read
                # the handshake offer at call time; the header makes the SDK's 401
                # handling include the RFC 8707 ``resource``.
                from the_one import mcp as the_one_mcp

                version = the_one_mcp._HANDSHAKE_OFFER_VERSION
                response = await client.post(
                    server_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": version,
                            "clientInfo": {"name": "the-one", "version": "0.1"},
                            "capabilities": {},
                        },
                    },
                    headers=headers_for(version),
                )
            if not getattr(storage, "tokens_saved", False) and not (
                200 <= response.status_code < 300
            ):
                failure = START_FAILED_DESCRIPTION.format(status=response.status_code)
        except Exception as exc:
            if not getattr(storage, "tokens_saved", False):
                failure = str(exc) or type(exc).__name__
                logger.info("chat sign-in flow for %s failed: %s", source_id, failure)
        if failure is None:
            await _report_resolved(flow, chat_session_id, source_id, tool_call_id)
        else:
            await _report_failed(flow, chat_session_id, source_id, failure)
    finally:
        flows = _flows.get(flow.key)
        if flows is not None:
            with contextlib.suppress(ValueError):
                flows.remove(flow)
            if not flows:
                del _flows[flow.key]


def start_chat_sign_in(
    provider: Any,
    *,
    server_url: str,
    chat_session_id: str,
    source_id: str,
    tool_call_id: str | None,
    headers_for: Callable[[str], dict[str, str]],
) -> None:
    """Schedule the chat sign-in flow for ``provider`` and return at once."""
    from the_one.interfaces.web import app as web_app

    key = (chat_session_id, source_id)
    flow = _Flow(key, _resolved_count.get(key, 0))
    _flows.setdefault(key, []).append(flow)
    flow.task = asyncio.create_task(
        _drive(flow, provider, server_url, chat_session_id, source_id, tool_call_id, headers_for)
    )
    web_app._inflight_resume_tasks.add(flow.task)
    flow.task.add_done_callback(web_app._inflight_resume_tasks.discard)
