"""M18 F02 L01/L02 — WS message-branch crash guard + image attachment cap.

Drives the real ``websocket_endpoint`` coroutine directly against a fake
``WebSocket`` (accept/receive_text/send_json only — the surface the
handler actually touches), rather than standing up the full ASGI/DB stack.
This is the same "drive the helper directly" idiom as
``tests/test_ws_responsiveness.py`` — session creation is monkeypatched to
a stub so the test isolates the WS loop's control flow.

Covers:
- L01: a malformed ``images`` payload (unexpected key -> ``TypeError``
  from ``ImageContent(**img)``; both ``data``/``url`` absent -> the
  ``ImageContent`` guard) degrades to a ``system`` error event and the
  loop survives to process the NEXT message — not a dropped connection.
- L01: a mid-loop disconnect (``receive_text`` raising
  ``WebSocketDisconnect``) still exits ``websocket_endpoint`` cleanly
  (no exception escapes).
- L01: text-only and well-formed image sends are unaffected (still reach
  ``_spawn_message_processing``).
- L02: an over-count or over-size ``images`` payload is rejected via the
  same error-surfacing path, BEFORE a session is auto-created, and the
  loop survives.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from starlette.websockets import WebSocketDisconnect

from the_one.interfaces.web import app as app_module
from the_one.interfaces.web.app import (
    IMAGE_ATTACHMENT_CAP_BYTES,
    IMAGE_ATTACHMENT_MAX_COUNT,
    Session,
    websocket_endpoint,
)


class _FakeAgent:
    """Stand-in for `the_one.agent.Agent` — only what the WS loop touches."""

    def __init__(self) -> None:
        self.messages = []
        # Read by `_send_pause_snapshot_if_needed` (called on every
        # auto-join) — None means "no pending pause", short-circuiting
        # before it touches `.messages` further.
        self._deferred_tool_calls = None


class FakeWebSocket:
    """Minimal fake covering the ``websocket_endpoint`` surface.

    ``receive_text`` pops from a scripted queue of raw JSON strings and
    raises ``WebSocketDisconnect`` once exhausted — mirroring a client
    disconnect after its last message. ``send_json`` records every
    outbound event so tests can assert on the error-surfacing shape.
    """

    def __init__(self, incoming: list[dict]) -> None:
        self._incoming = [json.dumps(msg) for msg in incoming]
        self.sent: list[dict] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        # Real `receive_text()` is a genuine asyncio I/O await, which
        # yields control back to the loop — giving any just-scheduled
        # `asyncio.create_task(...)` (the message-processing spawn) a
        # chance to run before the loop reads the NEXT message. A fake
        # with no internal await point would starve that task until
        # `websocket_endpoint` returns and the loop is torn down, making
        # `_spawn_message_processing` calls appear to "never happen" from
        # the test's perspective. `asyncio.sleep(0)` reproduces the yield.
        await asyncio.sleep(0)
        if not self._incoming:
            raise WebSocketDisconnect()
        return self._incoming.pop(0)

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


def _make_session(session_id: str = "s1") -> Session:
    return Session(
        id=session_id,
        agent=_FakeAgent(),  # type: ignore[arg-type]
        created=datetime.now(timezone.utc).isoformat(),
    )


class _Harness:
    """Records everything the WS loop hands off to session-creation and
    message-processing, so tests can assert on both without a real
    Agent/LLM/DB stack."""

    def __init__(self) -> None:
        self.create_calls: list[tuple[tuple, dict]] = []
        self.spawned: list[tuple[str, object]] = []

    async def create_session(self, *a, **kw):  # noqa: ANN001
        self.create_calls.append((a, kw))
        return _make_session()

    async def spawn(self, session, content, source, ws):  # noqa: ANN001
        self.spawned.append((session.id, content))


@pytest.fixture(autouse=True)
def _stub_session_and_spawn(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    """Auto-create returns a fresh stub session; message processing is a
    recording no-op so the loop doesn't need a real Agent/LLM/DB."""
    harness = _Harness()
    monkeypatch.setattr(app_module, "_create_session", harness.create_session)
    monkeypatch.setattr(app_module, "_spawn_message_processing", harness.spawn)
    return harness


class TestMalformedImagesPayloadSurvivesLoop:
    async def test_both_data_and_url_absent_surfaces_error_and_continues(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        ws = FakeWebSocket(
            [
                {"action": "message", "message": "", "images": [{"media_type": "image/png"}]},
                {"action": "message", "message": "still alive"},
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        # The malformed turn surfaced a system error — NOT a crash.
        system_events = [e for e in ws.sent if e.get("type") == "system"]
        assert any("Cannot process message" in e["content"] for e in system_events)
        # The loop survived: the well-formed second message reached
        # _spawn_message_processing.
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "still alive"

    async def test_unexpected_image_key_surfaces_error_and_continues(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        ws = FakeWebSocket(
            [
                {
                    "action": "message",
                    "message": "",
                    "images": [{"media_type": "image/png", "data": "abc", "bogus_key": "x"}],
                },
                {"action": "message", "message": "still alive"},
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        system_events = [e for e in ws.sent if e.get("type") == "system"]
        assert any("Cannot process message" in e["content"] for e in system_events)
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "still alive"

    async def test_mid_loop_disconnect_exits_cleanly(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        """A real WebSocketDisconnect (from receive_text, OUTSIDE the L01
        guard) must still end the loop without raising — the inner guard
        must not be so broad it changes this behavior."""
        ws = FakeWebSocket([{"action": "message", "message": "hello"}])
        # Should return normally — WebSocketDisconnect is caught by the
        # OUTER try, not propagated.
        await websocket_endpoint(ws)  # type: ignore[arg-type]
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "hello"


class TestHappyPathUnaffected:
    async def test_text_only_send_reaches_spawn(self, _stub_session_and_spawn: _Harness) -> None:
        ws = FakeWebSocket([{"action": "message", "message": "hi there"}])
        await websocket_endpoint(ws)  # type: ignore[arg-type]
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "hi there"
        # No spurious system-error event.
        assert not [e for e in ws.sent if e.get("type") == "system"]

    async def test_well_formed_image_send_reaches_spawn(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        ws = FakeWebSocket(
            [
                {
                    "action": "message",
                    "message": "what is this",
                    "images": [{"media_type": "image/png", "data": "Zm9v"}],
                }
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]
        assert len(_stub_session_and_spawn.spawned) == 1
        _, content = _stub_session_and_spawn.spawned[0]
        assert isinstance(content, list)
        assert not [e for e in ws.sent if e.get("type") == "system"]


class TestImageAttachmentCap:
    """M18 F02 L02: server-side count + per-image byte cap."""

    async def test_over_count_rejected_before_session_create(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        too_many = [{"media_type": "image/png", "data": "Zm9v"}] * (IMAGE_ATTACHMENT_MAX_COUNT + 1)
        ws = FakeWebSocket(
            [
                {"action": "message", "message": "", "images": too_many},
                {"action": "message", "message": "still alive"},
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        system_events = [e for e in ws.sent if e.get("type") == "system"]
        assert any("Too many images" in e["content"] for e in system_events)
        # Loop survived: the well-formed follow-up reached spawn (which DOES
        # need a session, proving auto-create still works after a rejection).
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "still alive"
        # The REJECTED turn must not have triggered session-create — only
        # the follow-up's own auto-join did (exactly one call, not two).
        assert len(_stub_session_and_spawn.create_calls) == 1

    async def test_over_size_image_rejected(self, _stub_session_and_spawn: _Harness) -> None:
        # base64 length ~4/3 of decoded bytes; comfortably exceed the cap.
        oversized_b64_len = int((IMAGE_ATTACHMENT_CAP_BYTES + 1) * 4 / 3) + 4
        oversized_data = "A" * oversized_b64_len
        ws = FakeWebSocket(
            [
                {
                    "action": "message",
                    "message": "",
                    "images": [{"media_type": "image/png", "data": oversized_data}],
                },
                {"action": "message", "message": "still alive"},
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        system_events = [e for e in ws.sent if e.get("type") == "system"]
        assert any("per-image limit" in e["content"] for e in system_events)
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "still alive"
        # The REJECTED turn must not have triggered session-create.
        assert len(_stub_session_and_spawn.create_calls) == 1

    async def test_within_limit_images_unaffected(self, _stub_session_and_spawn: _Harness) -> None:
        ok_images = [{"media_type": "image/png", "data": "Zm9v"}] * IMAGE_ATTACHMENT_MAX_COUNT
        ws = FakeWebSocket([{"action": "message", "message": "compare these", "images": ok_images}])
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        assert not [e for e in ws.sent if e.get("type") == "system"]
        assert len(_stub_session_and_spawn.spawned) == 1


class TestMalformedImagesShapeSurvivesLoop:
    """Review fix (post-L02): the cap-check block ran BEFORE the Leg-1
    guard and was itself unguarded, so a malformed ``images`` SHAPE (not
    just a malformed per-image dict) crashed the loop:

    - ``images`` as a non-list (e.g. an int) -> ``len(images)`` raises
      ``TypeError``.
    - ``images`` as a string -> iterating hands ``_approx_image_bytes``
      individual chars -> ``AttributeError`` (``str`` has no ``.get``).
    - ``images`` as a list of non-dicts -> ``img.get("data")`` ->
      ``AttributeError``.

    Each must now surface a system error and keep the loop alive, mirroring
    ``TestMalformedImagesPayloadSurvivesLoop`` above.
    """

    async def test_non_list_images_int_surfaces_error_and_continues(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        ws = FakeWebSocket(
            [
                {"action": "message", "message": "", "images": 123},
                {"action": "message", "message": "still alive"},
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        system_events = [e for e in ws.sent if e.get("type") == "system"]
        assert any("Malformed images payload" in e["content"] for e in system_events)
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "still alive"
        # The REJECTED turn must not have triggered session-create.
        assert len(_stub_session_and_spawn.create_calls) == 1

    async def test_string_images_surfaces_error_and_continues(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        ws = FakeWebSocket(
            [
                {"action": "message", "message": "", "images": "hello"},
                {"action": "message", "message": "still alive"},
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        system_events = [e for e in ws.sent if e.get("type") == "system"]
        assert any("Malformed images payload" in e["content"] for e in system_events)
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "still alive"
        assert len(_stub_session_and_spawn.create_calls) == 1

    async def test_list_of_non_dicts_surfaces_error_and_continues(
        self, _stub_session_and_spawn: _Harness
    ) -> None:
        ws = FakeWebSocket(
            [
                {"action": "message", "message": "", "images": ["not-a-dict", "also-not"]},
                {"action": "message", "message": "still alive"},
            ]
        )
        await websocket_endpoint(ws)  # type: ignore[arg-type]

        system_events = [e for e in ws.sent if e.get("type") == "system"]
        assert any("Malformed images payload" in e["content"] for e in system_events)
        assert len(_stub_session_and_spawn.spawned) == 1
        assert _stub_session_and_spawn.spawned[0][1] == "still alive"
        assert len(_stub_session_and_spawn.create_calls) == 1
