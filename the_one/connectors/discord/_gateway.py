"""Discord Gateway v10 client — hello/heartbeat/identify/resume/dispatch
(DD-2). One :class:`GatewayConnection` per connection attempt; the caller
(``plugin.py``) owns reconnect/backoff via the manager's existing loop —
this module never retries internally.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import websockets
from websockets.exceptions import ConnectionClosed

from the_one.connectors.base import ConnectorClientError, PermanentConnectorFailure

logger = logging.getLogger(__name__)

API_VERSION = 10
GATEWAY_QUERY = f"/?v={API_VERSION}&encoding=json"

# Opcodes (DD-2).
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RESUME = 6
OP_RECONNECT = 7
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

# GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT = 37377.
INTENTS = 1 | 512 | 4096 | 32768

# Non-reconnectable close codes (Discord docs): auth failed, or a
# shard/intent misconfiguration that will never self-resolve. Anything
# else is transient — the manager's normal reconnect path.
PERMANENT_CLOSE_CODES = frozenset({4004, 4010, 4011, 4012, 4013, 4014})

DispatchHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class _GatewayState(Protocol):
    """Duck-typed per-account state this module reads/writes directly.
    ``plugin.py``'s ``_AccountState`` satisfies this structurally — one
    instance per account, shared across reconnects, so ``last_seq`` and
    the resume identifiers survive a dropped connection."""

    session_id: str | None
    resume_gateway_url: str | None
    last_seq: int | None
    bot_user_id: str | None
    channel_type_cache: dict[str, int]


class GatewayConnection:
    """One gateway connection attempt/lifetime.

    ``run()`` performs the handshake (resume-if-possible, with the
    stale-resume-URL fallback) then loops handling frames until the
    socket closes. It resolves ``ready_future`` the moment READY/RESUMED
    lands — the caller's ``plugin.connect()`` unblocks at that point —
    and keeps running as the background listener afterward.

    Close-code policy (AC-4) is checked ONLY pre-READY: a permanent close
    code observed while the initial handshake is still in flight raises
    ``PermanentConnectorFailure`` through ``ready_future``. A permanent
    code observed mid-session (post-READY) is deliberately NOT raised
    here — it surfaces at the NEXT handshake instead (design review
    2026-09-01, see ``plugin.py``'s ``connect()`` docstring for the
    accepted-latency rationale): the read-loop-signals-``_run``
    alternative adds machinery for no recovery benefit, since the token
    is equally bad one backoff cycle later.
    """

    def __init__(
        self,
        *,
        token: str,
        state: _GatewayState,
        default_url_provider: Callable[[], Awaitable[str]],
        reidentify_delay: Callable[[], float] | None = None,
    ) -> None:
        self._token = token
        self._state = state
        self._default_url_provider = default_url_provider
        self._reidentify_delay = reidentify_delay or (lambda: random.uniform(1, 5))
        self._resuming = False
        self._ack_received = True
        self._self_initiated_close = False
        self._alive = True
        self.ws: Any = None

    def is_alive(self) -> bool:
        return self._alive

    def sever_for_test(self) -> None:
        """Controlled-disconnect test seam (DD-7, AC-1): abort the
        underlying ws transport with NO close handshake and NO state
        cleanup — simulates an abrupt network drop so the normal
        death-detection (``_read_loop``'s ``ConnectionClosed`` catch) and
        the manager's reconnect path run exactly as they would after a
        real disconnect. NEVER ``self.ws.close()`` in any form here — a
        close handshake always completes regardless of arguments (see
        ``tests/_discord_gateway_fixture.py``'s ``close_abrupt()`` for the
        server-side precedent this mirrors). Deliberately does NOT set
        ``_self_initiated_close`` — an abrupt severed connection must be
        indistinguishable, to this process, from a real network drop.
        Reached only via ``manager.client_for`` + ``getattr`` from the
        dual-gated ``/_test/discord/sever`` route; never a production kill
        switch."""
        if self.ws is not None:
            self.ws.transport.abort()

    async def close(self) -> None:
        """Client-initiated teardown (manager-driven disconnect/stop)."""
        self._alive = False
        self._self_initiated_close = True
        if self.ws is not None:
            with contextlib.suppress(Exception):
                await self.ws.close()

    async def run(
        self,
        on_dispatch: DispatchHandler,
        ready_future: "asyncio.Future[None]",
        ready_info: dict[str, Any],
    ) -> None:
        """Handshake, then read-loop until the socket dies.

        ``ready_info`` is mutated in place with the READY dispatch's ``d``
        payload (empty for a RESUMED handshake) so the caller can pull
        ``user``/``private_channels`` out after ``ready_future`` resolves.
        """
        hb_task: asyncio.Task | None = None
        try:
            await self._open()
            hello = json.loads(await self.ws.recv())
            if hello.get("op") != OP_HELLO:
                raise ConnectorClientError(f"expected HELLO, got op={hello.get('op')}")
            interval = hello["d"]["heartbeat_interval"] / 1000.0
            hb_task = asyncio.create_task(self._heartbeat_loop(interval))
            if self._resuming:
                await self._send_resume()
            else:
                await self._send_identify()
            await self._read_loop(on_dispatch, ready_future, ready_info)
        except BaseException as exc:  # must resolve ready_future on every exit path
            if not ready_future.done():
                ready_future.set_exception(exc)
            if isinstance(exc, (PermanentConnectorFailure, asyncio.CancelledError)):
                raise
        finally:
            self._alive = False
            if hb_task is not None:
                hb_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await hb_task
            if not ready_future.done():
                ready_future.set_exception(ConnectorClientError("gateway closed before ready"))

    async def _read_loop(
        self,
        on_dispatch: DispatchHandler,
        ready_future: "asyncio.Future[None]",
        ready_info: dict[str, Any],
    ) -> None:
        ready_reached = False
        while True:
            try:
                raw = await self.ws.recv()
            except ConnectionClosed as exc:
                if not ready_reached and not self._self_initiated_close:
                    code = exc.rcvd.code if exc.rcvd else None
                    if code in PERMANENT_CLOSE_CODES:
                        raise PermanentConnectorFailure(
                            f"discord gateway closed with permanent code {code}"
                        ) from exc
                return
            payload = json.loads(raw)
            op = payload.get("op")
            if op == OP_DISPATCH:
                if payload.get("s") is not None:
                    self._state.last_seq = payload["s"]
                t = payload.get("t")
                d = payload.get("d") or {}
                if t == "READY":
                    # Captured synchronously, BEFORE ready_future resolves
                    # (edge case): a MESSAGE_CREATE dispatched immediately
                    # after READY is handled by this SAME loop iteration
                    # sequence, not by the caller's `connect()` coroutine
                    # (which only resumes on a later event-loop tick) — so
                    # `bot_user_id` must already be set here or the first
                    # post-READY dispatch would race it and be dropped.
                    self._state.session_id = d.get("session_id")
                    self._state.resume_gateway_url = d.get("resume_gateway_url")
                    user = d.get("user") or {}
                    if user.get("id"):
                        self._state.bot_user_id = user["id"]
                    for channel in d.get("private_channels") or []:
                        if channel.get("id"):
                            self._state.channel_type_cache[channel["id"]] = channel.get("type", 1)
                    ready_info.update(d)
                    ready_reached = True
                    if not ready_future.done():
                        ready_future.set_result(None)
                elif t == "RESUMED":
                    ready_reached = True
                    if not ready_future.done():
                        ready_future.set_result(None)
                else:
                    await on_dispatch(t, d)
            elif op == OP_HEARTBEAT:
                await self._send_heartbeat()
            elif op == OP_HEARTBEAT_ACK:
                self._ack_received = True
            elif op == OP_RECONNECT:
                # Self-initiated close responding to op 7 — must NOT run
                # through the close-code-policy check above (edge case).
                self._self_initiated_close = True
                await self.ws.close(code=1000)
                return
            elif op == OP_INVALID_SESSION:
                await asyncio.sleep(self._reidentify_delay())
                self._resuming = False
                await self._send_identify()

    async def _open(self) -> None:
        self._resuming = False
        if self._state.session_id and self._state.resume_gateway_url:
            url = self._state.resume_gateway_url.rstrip("/") + GATEWAY_QUERY
            try:
                self.ws = await websockets.connect(url)
                self._resuming = True
                return
            except OSError:
                # Stale resume URL — clear so a later connect() never
                # retries the dead host, and fall back within THIS call.
                logger.warning("discord gateway: stale resume_gateway_url %s; falling back", url)
                self._state.session_id = None
                self._state.resume_gateway_url = None
        url = (await self._default_url_provider()).rstrip("/") + GATEWAY_QUERY
        self.ws = await websockets.connect(url)

    async def _send_identify(self) -> None:
        await self.ws.send(
            json.dumps(
                {
                    "op": OP_IDENTIFY,
                    "d": {
                        "token": self._token,
                        "intents": INTENTS,
                        "properties": {
                            "os": "linux",
                            "browser": "the-one",
                            "device": "the-one",
                        },
                    },
                }
            )
        )

    async def _send_resume(self) -> None:
        await self.ws.send(
            json.dumps(
                {
                    "op": OP_RESUME,
                    "d": {
                        "token": self._token,
                        "session_id": self._state.session_id,
                        "seq": self._state.last_seq,
                    },
                }
            )
        )

    async def _send_heartbeat(self) -> None:
        await self.ws.send(json.dumps({"op": OP_HEARTBEAT, "d": self._state.last_seq}))

    async def _heartbeat_loop(self, interval: float) -> None:
        await asyncio.sleep(interval * random.random())
        while True:
            self._ack_received = False
            await self._send_heartbeat()
            await asyncio.sleep(interval)
            if not self._ack_received:
                self._self_initiated_close = True
                with contextlib.suppress(Exception):
                    await self.ws.close(code=1000)
                return
