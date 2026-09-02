"""Tests for ``the_one.connectors.discord._gateway`` — hello/heartbeat/
identify/resume/dispatch/close-code-policy (DD-2). Mission 23 Flight 3
Leg 1. All against the fake gateway (``tests/_discord_gateway_fixture.py``)
— no real network.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from tests._discord_gateway_fixture import FakeGateway
from the_one.connectors.base import ConnectorClientError, PermanentConnectorFailure
from the_one.connectors.discord._gateway import INTENTS, GatewayConnection
from the_one.connectors.discord.plugin import _AccountState


def _fixed_url(url: str):
    async def _provider() -> str:
        return url

    return _provider


def _unreachable_url():
    async def _provider() -> str:
        raise AssertionError("default_url_provider must not be called while resuming")

    return _provider


async def _noop_dispatch(t: str, d: dict) -> None:  # pragma: no cover - overridden per test
    pass


async def _run_conn(state, url_provider, *, reidentify_delay=None, on_dispatch=_noop_dispatch):
    conn = GatewayConnection(
        token="tok",
        state=state,
        default_url_provider=url_provider,
        reidentify_delay=reidentify_delay,
    )
    ready_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    ready_info: dict = {}
    task = asyncio.create_task(conn.run(on_dispatch, ready_future, ready_info))
    return conn, task, ready_future, ready_info


async def _teardown(conn, task):
    await conn.close()
    if not task.done():
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


# ── AC-1: happy path ─────────────────────────────────────────────────────


async def test_happy_path_identify_ready_and_dispatch():
    dispatched = []

    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        identify = await session.recv_json(timeout=5)
        assert identify["op"] == 2
        assert identify["d"]["intents"] == INTENTS == 37377
        assert identify["d"]["token"] == "tok"
        await session.send_ready(session_id="sess-1", resume_gateway_url="ws://resume-host")
        await session.send_message_create(
            {"channel_id": "c1", "content": "hi", "author": {"id": "u1", "username": "Alice"}},
            seq=2,
        )
        await asyncio.sleep(0.3)

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState()

    async def on_dispatch(t, d):
        dispatched.append((t, d))

    conn, task, ready_future, ready_info = await _run_conn(
        state, _fixed_url(url), on_dispatch=on_dispatch
    )
    try:
        await asyncio.wait_for(ready_future, timeout=5)
        assert state.session_id == "sess-1"
        assert state.resume_gateway_url == "ws://resume-host"
        assert ready_info["user"]["id"] == "bot-1"
        await asyncio.sleep(0.2)
        assert dispatched == [("MESSAGE_CREATE", dispatched[0][1])]
        assert dispatched[0][1]["channel_id"] == "c1"
        assert state.last_seq == 2
    finally:
        await _teardown(conn, task)
        await gw.stop()


# ── AC-2: heartbeat discipline + sequence tracking ──────────────────────


async def test_heartbeat_payload_carries_last_seq_not_just_opcode():
    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=60)
        await session.recv_json(timeout=5)  # identify
        await session.send_ready(session_id="s1", resume_gateway_url="ws://x", seq=1)
        first = await session.recv_json(timeout=2)
        # READY (seq=1) already advanced last_seq — the heartbeat payload
        # tracks it immediately, not just post-MESSAGE_CREATE dispatches.
        assert first == {"op": 1, "d": 1}
        await session.send_heartbeat_ack()
        await session.send_dispatch("MESSAGE_REACTION_ADD", {}, seq=7)
        second = await session.recv_json(timeout=2)
        assert second == {"op": 1, "d": 7}
        await session.send_heartbeat_ack()
        await asyncio.sleep(0.1)

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState()
    conn, task, ready_future, _ = await _run_conn(state, _fixed_url(url))
    try:
        await asyncio.wait_for(ready_future, timeout=5)
        await asyncio.sleep(0.3)
        assert not gw.errors
    finally:
        await _teardown(conn, task)
        await gw.stop()


async def test_heartbeat_before_any_dispatch_carries_null_seq():
    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=40)
        await session.recv_json(timeout=5)  # identify — no dispatch has landed yet
        first = await session.recv_json(timeout=2)
        assert first == {"op": 1, "d": None}
        await session.send_heartbeat_ack()
        await session.send_ready(session_id="s1", resume_gateway_url="ws://x", seq=1)
        await asyncio.sleep(0.1)

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState()
    conn, task, ready_future, _ = await _run_conn(state, _fixed_url(url))
    try:
        await asyncio.wait_for(ready_future, timeout=5)
        assert not gw.errors
    finally:
        await _teardown(conn, task)
        await gw.stop()


async def test_missed_heartbeat_ack_closes_socket_and_kills_connection():
    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=40)
        await session.recv_json(timeout=5)
        await session.send_ready(session_id="s1", resume_gateway_url="ws://x")
        await session.recv_json(timeout=2)  # first heartbeat — withhold the ACK
        await asyncio.sleep(1.0)

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState()
    conn, task, ready_future, _ = await _run_conn(state, _fixed_url(url))
    try:
        await asyncio.wait_for(ready_future, timeout=5)
        await asyncio.wait_for(task, timeout=5)
        assert conn.is_alive() is False
    finally:
        await _teardown(conn, task)
        await gw.stop()


# ── AC-3: resume path — payload AND address ─────────────────────────────


async def test_resume_after_abrupt_close_lands_on_advertised_listener_with_full_payload():
    resume_payloads = []

    async def handler_b(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        resume = await session.recv_json(timeout=5)
        resume_payloads.append(resume)
        await session.send_resumed(seq=resume["d"]["seq"])
        await asyncio.sleep(0.3)

    gw_b = FakeGateway(handler_b)
    url_b = await gw_b.start()

    async def handler_a(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)  # identify
        await session.send_ready(session_id="sess-A", resume_gateway_url=url_b, seq=1)
        await session.send_dispatch("MESSAGE_REACTION_ADD", {}, seq=42)
        await asyncio.sleep(0.1)
        await session.close_abrupt()

    gw_a = FakeGateway(handler_a)
    url_a = await gw_a.start()

    state = _AccountState()
    conn1, task1, ready1, _ = await _run_conn(state, _fixed_url(url_a))
    try:
        await asyncio.wait_for(ready1, timeout=5)
        await asyncio.wait_for(task1, timeout=5)
        assert conn1.is_alive() is False
        assert state.resume_gateway_url == url_b
        assert state.last_seq == 42

        # The NEXT connect() must resume against listener B specifically —
        # default_url_provider is never called, so a bug that ignores
        # resume_gateway_url and falls back to the default cannot pass
        # incidentally.
        conn2, task2, ready2, _ = await _run_conn(state, _unreachable_url())
        try:
            await asyncio.wait_for(ready2, timeout=5)
            assert resume_payloads == [
                {"op": 6, "d": {"token": "tok", "session_id": "sess-A", "seq": 42}}
            ]
        finally:
            await _teardown(conn2, task2)
    finally:
        await _teardown(conn1, task1)
        await gw_a.stop()
        await gw_b.stop()


# ── AC-1 (leg 3, DD-7): sever_for_test — controlled-disconnect seam ──────


async def test_sever_for_test_aborts_transport_and_next_connect_resumes():
    """``sever_for_test()`` kills the transport with no close handshake;
    the gateway's normal death-detection (the ``_read_loop``'s
    ``ConnectionClosed`` catch) then drives ``is_alive()`` -> False and
    the resume state survives for the next ``connect()`` — symmetric to
    the already-passing abrupt-close resume test above, but triggered
    from the CLIENT side (as the real sever route does) rather than the
    fake server closing on us."""
    resume_payloads = []

    async def handler_b(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        resume = await session.recv_json(timeout=5)
        resume_payloads.append(resume)
        await session.send_resumed(seq=resume["d"]["seq"])
        await asyncio.sleep(0.3)

    gw_b = FakeGateway(handler_b)
    url_b = await gw_b.start()

    async def handler_a(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)  # identify
        await session.send_ready(session_id="sess-A", resume_gateway_url=url_b, seq=1)
        await session.send_dispatch("MESSAGE_REACTION_ADD", {}, seq=42)
        # Stays open on the server side — the TEST severs the client's own
        # transport below, simulating a network drop the server never sees.
        await asyncio.sleep(1.0)

    gw_a = FakeGateway(handler_a)
    url_a = await gw_a.start()

    state = _AccountState()
    conn1, task1, ready1, _ = await _run_conn(state, _fixed_url(url_a))
    try:
        await asyncio.wait_for(ready1, timeout=5)
        assert conn1.is_alive() is True

        # Deterministically wait for the read loop to have consumed the
        # seq=42 dispatch BEFORE severing — ready1 only guarantees READY
        # (seq=1) was processed; the MESSAGE_REACTION_ADD dispatch sent
        # right after it is a separate frame the read loop picks up on a
        # later iteration. Poll rather than a fixed sleep — cheap and
        # exact under any scheduler load.
        for _ in range(200):
            if state.last_seq == 42:
                break
            await asyncio.sleep(0.01)
        assert state.last_seq == 42, "seq=42 dispatch never observed before sever"

        conn1.sever_for_test()
        await asyncio.wait_for(task1, timeout=5)
        assert conn1.is_alive() is False
        assert state.resume_gateway_url == url_b
        assert state.last_seq == 42

        # The next connect() resumes against listener B specifically, per
        # the surviving session_id/resume_gateway_url/last_seq — proves
        # sever_for_test left state intact rather than clearing it.
        conn2, task2, ready2, _ = await _run_conn(state, _unreachable_url())
        try:
            await asyncio.wait_for(ready2, timeout=5)
            assert resume_payloads == [
                {"op": 6, "d": {"token": "tok", "session_id": "sess-A", "seq": 42}}
            ]
        finally:
            await _teardown(conn2, task2)
    finally:
        await _teardown(conn1, task1)
        await gw_a.stop()
        await gw_b.stop()


# ── AC-3b: op 7 RECONNECT ────────────────────────────────────────────────


async def test_op7_reconnect_closes_promptly_and_next_connect_resumes():
    resume_payloads = []

    async def handler_b(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        resume = await session.recv_json(timeout=5)
        resume_payloads.append(resume)
        await session.send_resumed(seq=resume["d"]["seq"])
        await asyncio.sleep(0.3)

    gw_b = FakeGateway(handler_b)
    url_b = await gw_b.start()

    async def handler_a(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.send_ready(session_id="sess-A", resume_gateway_url=url_b, seq=1)
        await session.send_json({"op": 7})
        await asyncio.sleep(0.3)

    gw_a = FakeGateway(handler_a)
    url_a = await gw_a.start()

    state = _AccountState()
    conn1, task1, ready1, _ = await _run_conn(state, _fixed_url(url_a))
    try:
        await asyncio.wait_for(ready1, timeout=5)
        await asyncio.wait_for(task1, timeout=5)
        assert conn1.is_alive() is False

        conn2, task2, ready2, _ = await _run_conn(state, _unreachable_url())
        try:
            await asyncio.wait_for(ready2, timeout=5)
            assert resume_payloads[0]["op"] == 6
        finally:
            await _teardown(conn2, task2)
    finally:
        await _teardown(conn1, task1)
        await gw_a.stop()
        await gw_b.stop()


# ── Edge case: op 9 invalid session mid-resume-replay ───────────────────


async def test_invalid_session_during_resume_reidentifies_on_same_connection():
    ops_seen = []

    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        first = await session.recv_json(timeout=5)
        ops_seen.append(first["op"])
        assert first["op"] == 6  # RESUME attempted first
        await session.send_json({"op": 9, "d": False})
        second = await session.recv_json(timeout=5)
        ops_seen.append(second["op"])
        assert second["op"] == 2  # fresh IDENTIFY, same connection
        await session.send_ready(session_id="sess-new", resume_gateway_url="ws://ignored", seq=1)
        await asyncio.sleep(0.2)

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState(session_id="stale-sess", resume_gateway_url=url, last_seq=9)
    conn, task, ready_future, _ = await _run_conn(
        state, _unreachable_url(), reidentify_delay=lambda: 0.0
    )
    try:
        await asyncio.wait_for(ready_future, timeout=5)
        assert ops_seen == [6, 2]
        assert state.session_id == "sess-new"
    finally:
        await _teardown(conn, task)
        await gw.stop()


# ── Edge case: stale resume_gateway_url falls back within the same connect() ──


async def test_stale_resume_url_clears_state_and_falls_back_same_call():
    import socket

    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        identify = await session.recv_json(timeout=5)
        assert identify["op"] == 2  # fresh identify, NOT a resume against the dead host
        await session.send_ready(session_id="sess-fresh", resume_gateway_url="ws://ignored", seq=1)
        await asyncio.sleep(0.2)

    gw = FakeGateway(handler)
    default_url = await gw.start()

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()
    dead_url = f"ws://127.0.0.1:{dead_port}"

    state = _AccountState(session_id="stale", resume_gateway_url=dead_url, last_seq=3)
    conn, task, ready_future, _ = await _run_conn(state, _fixed_url(default_url))
    try:
        await asyncio.wait_for(ready_future, timeout=5)
        assert state.session_id == "sess-fresh"  # overwritten by the fallback identify's READY
    finally:
        await _teardown(conn, task)
        await gw.stop()


# ── AC-4: close-code policy ──────────────────────────────────────────────


@pytest.mark.parametrize("code", [4004, 4011])
async def test_permanent_close_code_during_handshake_raises(code):
    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.close_with_code(code, "permanent")

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState()
    conn, task, ready_future, _ = await _run_conn(state, _fixed_url(url))
    try:
        with pytest.raises(PermanentConnectorFailure):
            await asyncio.wait_for(ready_future, timeout=5)
        with pytest.raises(PermanentConnectorFailure):
            await asyncio.wait_for(task, timeout=5)
    finally:
        await _teardown(conn, task)
        await gw.stop()


async def test_ordinary_close_code_does_not_raise_permanent_failure():
    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.close_with_code(4000, "transient")

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState()
    conn, task, ready_future, _ = await _run_conn(state, _fixed_url(url))
    try:
        with pytest.raises(ConnectorClientError) as excinfo:
            await asyncio.wait_for(ready_future, timeout=5)
        assert not isinstance(excinfo.value, PermanentConnectorFailure)
    finally:
        await _teardown(conn, task)
        await gw.stop()


async def test_permanent_close_code_mid_session_does_not_raise():
    """AC-4's stated (not accidental) behavior: a permanent code observed
    AFTER connect() has already returned (post-READY) does not raise —
    it just ends the connection like any other disconnect. The SAME code
    surfaces at the caller's NEXT handshake instead (see plugin.py)."""

    async def handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)
        await session.send_ready(session_id="sess-1", resume_gateway_url="ws://ignored", seq=1)
        await asyncio.sleep(0.05)
        await session.close_with_code(4004, "token revoked mid-session")

    gw = FakeGateway(handler)
    url = await gw.start()
    state = _AccountState()
    conn, task, ready_future, _ = await _run_conn(state, _fixed_url(url))
    try:
        await asyncio.wait_for(ready_future, timeout=5)  # resolves cleanly
        await asyncio.wait_for(task, timeout=5)  # task ends with no exception
        assert conn.is_alive() is False
    finally:
        await _teardown(conn, task)
        await gw.stop()
