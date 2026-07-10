"""M16 F12 L08 — content_to_text projection at the live-broadcast site.

``_process_and_broadcast`` builds ``user_event["content"]`` directly from
``user_input``, which may now be a ``list[ContentBlock]`` (an image-bearing
turn). Without projecting through ``content_to_text`` first, the raw
dataclass list reaches ``ws.send_json`` (stdlib ``json.dumps``, no custom
encoder) and raises ``TypeError`` — caught by ``_send_to_session``'s broad
except and silently treated as a "dead" socket, desyncing the SENDER from
their own session on the very first image send (they never see the
assistant reply). It also corrupts ``Session.add_event``'s title-slice
(``event["content"][:50]`` on a list slices to a list, not a string).

This test pins BOTH fixes at their single shared choke point: the
``user_event`` construction in ``_process_and_broadcast``, BEFORE
``session.add_event`` and ``_send_to_session`` consume it.

Test scaffolding mirrors ``tests/test_process_and_broadcast_live_read.py``
(minimal stub Agent + monkeypatched ``_send_to_session`` capture).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest

from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import Session, _process_and_broadcast
from the_one.llm.base import ImageContent, Message, TextContent


class _NoOpStubAgent:
    """Minimal stub Agent — ``step()`` yields nothing. Only
    ``llm``/``messages``/``_deferred_tool_calls`` are consumed by
    ``_process_and_broadcast`` outside of the step loop itself."""

    def __init__(self) -> None:
        class _LLMShim:
            max_context_tokens = 128_000

        self.llm = _LLMShim()
        self.messages: list[Message] = []
        self._deferred_tool_calls = None

    async def step(
        self,
        user_input: Any,  # noqa: ARG002
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        return
        yield  # pragma: no cover — makes this an async generator

    def reset(self) -> None:  # pragma: no cover
        self.messages = []


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    """Every test in this module drives ``_process_and_broadcast`` directly
    (not through the WS handler), so the Ollama auto-load and DB-persist
    side effects are stubbed out uniformly."""
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))


def _make_session(session_id: str) -> Session:
    return Session(
        id=session_id,
        agent=_NoOpStubAgent(),  # type: ignore[arg-type]
        created="2026-07-09T00:00:00+00:00",
    )


async def test_list_content_user_event_projects_to_string(monkeypatch) -> None:
    """Text + image list content -> user_event["content"] is a plain str
    ("text [image]"), not a raw dataclass list."""
    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    session = _make_session("cs-image-content-1")
    content = [
        TextContent(text="what is in this image?"),
        ImageContent(media_type="image/png", data="abc"),
    ]
    await _process_and_broadcast(session, content)

    user_events = [p for p in captured if p.get("type") == "user"]
    assert len(user_events) == 1
    assert user_events[0]["content"] == "what is in this image? [image]"
    assert isinstance(user_events[0]["content"], str)


async def test_image_only_list_content_user_event_projects_to_string(monkeypatch) -> None:
    """Image-only (no text) list content -> "[image]", still a plain str."""
    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    session = _make_session("cs-image-content-2")
    content = [ImageContent(media_type="image/png", data="abc")]
    await _process_and_broadcast(session, content)

    user_events = [p for p in captured if p.get("type") == "user"]
    assert user_events[0]["content"] == "[image]"


async def test_session_title_derived_from_list_content_is_a_string(monkeypatch) -> None:
    """Session.add_event derives ``session.title`` from
    ``event["content"][:50]``. On unprojected list content this silently
    slices to a LIST (the in-memory dataclass assignment doesn't
    revalidate), corrupting the history sidebar. With the content_to_text
    projection in place, the title is a plain str.
    """
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    session = _make_session("cs-image-content-3")
    assert session.title == "New chat"
    content = [TextContent(text="describe this"), ImageContent(media_type="image/jpeg", data="xyz")]
    await _process_and_broadcast(session, content)

    assert isinstance(session.title, str)
    assert session.title == "describe this [image]"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
